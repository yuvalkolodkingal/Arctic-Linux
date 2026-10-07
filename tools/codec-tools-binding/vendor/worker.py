#!/usr/bin/env python3
"""Finite CI scratch codec evaluation. Never run RPM/package/target scripts."""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import os
import resource
import shutil
import stat
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET
from core import (C, KEYS, ROOTS, EXPECTED_REMOVALS, Deadline, require, sha_file,
    INVENTORY_SHA, write_json, private_dir, relative_member, safe_child, repomd_entries,
    validate_binding, validate_actions, verify_signature_result, tree_manifest, manifest_digest, image_member, provider_proof, PhaseFailure, failure_detail, reap_owned, close_observed)
from solver import solve
from cpio import unpack

WORK = Path("/work")
IMAGE = Path("/image")
SOURCE = Path("/source")
EXTRACTED = Path("/extracted")
STAGES = ("archive", "extract", "metadata", "solve", "payloads", "compress")
LIMITS = {"archive": 300, "extract": 900, "metadata": 900, "solve": 900, "payloads": 600, "compress": 600}


def resources():
    context = json.loads((WORK / "context.json").read_text())
    free = shutil.disk_usage(WORK).free
    require(context["initial_free_disk_bytes"] - free <= 24000000000,
        "total owned CI scratch/disk limit")
    require(free >= 1000000000, "CI scratch free-space reserve")


def command(argv, deadline, name, stdout_limit=20000000, timeout=300):
    require(argv[0] in ("/usr/bin/rpmkeys", "/usr/bin/gpg", "/usr/bin/zstd",
        "/usr/bin/rpm2cpio", "/usr/bin/xorriso", "/usr/bin/mkfs.erofs", "/usr/bin/fsck.erofs"),
        "unapproved reader/compressor command")
    out, err = WORK / (name + ".stdout"), WORK / (name + ".stderr")
    start = time.monotonic()
    budget = deadline.remaining(timeout)
    end = start + budget
    work_end = end - min(5., budget / 2.)
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    process, stdout, stderr, primary, secondary = None, None, None, None, []
    try:
        stdout = out.open("xb")
        stderr = err.open("xb")
        process = subprocess.Popen(argv, stdout=stdout, stderr=stderr,
            stdin=subprocess.DEVNULL, cwd=WORK, start_new_session=True,
            env={"PATH": "/usr/bin:/usr/sbin", "LANG": "C.UTF-8", "HOME": str(WORK / "home")})
        while process.poll() is None:
            require(time.monotonic() < work_end, "bounded reader timeout:" + name)
            resources()
            require(out.stat().st_size <= stdout_limit and err.stat().st_size <= 20000000,
                "bounded reader output:" + name)
            time.sleep(min(.05, max(.001, work_end - time.monotonic())))
        require(time.monotonic() <= work_end, "post-exit reader timeout:" + name)
        require(out.stat().st_size <= stdout_limit and err.stat().st_size <= 20000000,
            "post-exit reader output limit")
        require(process.returncode == 0, "reader failed:" + name)
    except BaseException as error:
        primary = error
        reap_owned(process, end, secondary)
    finally:
        close_observed(stdout, secondary)
        close_observed(stderr, secondary)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    record = {"argv": argv, "exit_status": process.returncode if process is not None else None,
        "wall_seconds": time.monotonic() - start, "phase_end_monotonic": end,
        "primary_failure": failure_detail(primary) if primary else None,
        "cleanup_or_close_failures": secondary,
        "CPU_seconds": after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime,
        "peak_RSS_KiB_process_family_high_water": after.ru_maxrss,
        "stdout_bytes": out.stat().st_size if out.exists() else None,
        "stdout_sha256": sha_file(out) if out.exists() else None,
        "stderr_bytes": err.stat().st_size if err.exists() else None,
        "stderr_sha256": sha_file(err) if err.exists() else None}
    try:
        write_json(WORK / (name + ".command.json"), record)
    except Exception as error:
        secondary.append(failure_detail(error))
    if primary is not None or secondary:
        raise PhaseFailure(primary, secondary) from primary
    return out, record


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError("redirect outside exact reviewed source request")


def fetch(url, path, expected_size, expected_sha, deadline):
    require(url.startswith(("https://dl.fedoraproject.org/pub/fedora/linux/",
        "https://download1.rpmfusion.org/free/fedora/")), "unapproved download URL")
    require(not path.exists() and not path.is_symlink(), "stale download")
    path.parent.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    start = time.monotonic()
    with opener.open(url, timeout=deadline.remaining(120)) as stream, path.open("xb") as dest:
        total = 0
        while True:
            deadline.remaining(120)
            resources()
            require(time.monotonic() - start < 120, "download total deadline")
            chunk = stream.read(65536)
            if not chunk:
                break
            total += len(chunk)
            require(total <= expected_size, "download byte bound")
            dest.write(chunk)
    require(total == expected_size and sha_file(path) == expected_sha, "download checksum/size mismatch")
    return {"url": url, "attempts": 1, "bytes": total, "sha256": expected_sha}


def installed_headers(root):
    import rpm
    rpm.addMacro("_dbpath", "/usr/lib/sysimage/rpm")
    ts = rpm.TransactionSet(str(root))
    headers = list(ts.dbMatch())
    rows = []
    for h in headers:
        if h["name"] == "gpg-pubkey":
            continue
        rows.append((h["name"], str(h["epoch"] or 0) + ":" + h["version"] + "-" + h["release"], h["arch"]))
    require(rows and len(rows) <= 3000 and len(rows) == len(set(rows)), "RPMdb header population")
    return headers, sorted(rows)


def header_files(header):
    # Ownership comes from the unchanged image, not the tools container's users.
    users = {row.split(":")[0]: int(row.split(":")[2]) for row in
        image_member(IMAGE, "etc/passwd").read_text().splitlines() if row and not row.startswith("#")}
    groups = {row.split(":")[0]: int(row.split(":")[2]) for row in
        image_member(IMAGE, "etc/group").read_text().splitlines() if row and not row.startswith("#")}
    names = header["filenames"] or []
    arrays = {k: list(header[k] or []) for k in ("filemodes", "filedigests", "filelinktos",
        "fileflags", "fileusername", "filegroupname")}
    require(all(len(v) == len(names) for v in arrays.values()), "RPM file-array length mismatch")
    algorithm = {1: "md5", 2: "sha1", 8: "sha256", 9: "sha384", 10: "sha512"}.get(
        int(header["filedigestalgo"] or 1))
    require(algorithm is not None, "unsupported file digest algorithm")
    result = {}
    for index, name in enumerate(names):
        require(name.startswith("/") and not name.startswith("//"), "nonabsolute RPM file path")
        relative = relative_member(name[1:]).as_posix()
        require(relative not in result, "duplicate RPM file")
        result[relative] = {"mode": int(arrays["filemodes"][index]),
            "digest": arrays["filedigests"][index], "digest_algorithm": algorithm,
            "link": arrays["filelinktos"][index], "flags": int(arrays["fileflags"][index]),
            "uid": users[arrays["fileusername"][index]],
            "gid": groups[arrays["filegroupname"][index]]}
    return result


def readonly_image():
    entries = [line.split() for line in Path("/proc/self/mountinfo").read_text().splitlines()]
    require(any(row[4] == "/image" and "ro" in row[5].split(",") for row in entries),
        "actual image mount is not read-only")
    require(not os.environ.get("GH_TOKEN") and not os.environ.get("GITHUB_TOKEN"),
        "workflow credential leaked into worker")


def original_state():
    return {relative: manifest_digest(tree_manifest(image_member(IMAGE, relative)))
        for relative in ("usr/lib/sysimage/rpm", "usr/lib/sysimage/libdnf5", "etc/yum.repos.d")}


def copy_state(origin, target):
    # Database/state must not contain a link or special file that could resolve
    # against the tools container or escape this copied image.
    manifest = tree_manifest(origin)
    require(all(row["type"] in ("regular", "directory") for row in manifest), "linked/special RPM/DNF state")
    shutil.copytree(origin, target, symlinks=True)
    require(tree_manifest(target) == manifest, "state copy differs")


def tool_identity(binding):
    headers, _ = installed_headers(Path("/"))
    for name, expected in binding["tool_packages"].items():
        actual = [h["version"] + "-" + h["release"] + "." + h["arch"]
            for h in headers if h["name"] == name]
        require(actual == [expected], "actual tool package differs:" + name)
    for name, expected in binding["tool_file_hashes"].items():
        path = image_member(Path("/"), name)
        require(path.is_file() and sha_file(path) == expected, "actual tool file differs:" + name)


def prepare_private_solver(deadline):
    readonly_image()
    destination = private_dir(WORK / "solver-root", WORK, fresh=True)
    for relative in ("usr/lib/sysimage/rpm", "usr/lib/sysimage/libdnf5"):
        origin = image_member(IMAGE, relative)
        require(origin.is_dir() and not origin.is_symlink(), "actual RPM/DNF state missing")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_state(origin, target)
    # Preserve installed reasons/state rather than treating all RPMs as user-installed.
    for relative in ("etc/os-release", "usr/lib/os-release"):
        origin = image_member(IMAGE, relative)
        if origin.is_file():
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin, target)
    headers, rows = installed_headers(destination)
    require(sha_file(SOURCE / "candidate-inventory.tsv") == INVENTORY_SHA, "candidate inventory source pin")
    expected = sorted(tuple(line.split("\t")) for line in
        (SOURCE / "candidate-inventory.tsv").read_text().splitlines() if line)
    require(rows == expected, "actual copied RPMdb differs from exact image inventory")
    write_json(WORK / "actual-installed-headers.json", rows)
    write_json(WORK / "original-rpmdb-and-DNF-state.json", original_state())
    config = WORK / "config"
    config.mkdir(mode=0o700)
    for name in ("repos", "empty-vars", "empty-plugins"):
        (config / name).mkdir(mode=0o700)
    (config / "dnf.conf").write_text("[main]\nplugins=0\ninstall_weak_deps=1\n")
    return headers, rows


def metadata(binding, deadline):
    headers, installed = prepare_private_solver(deadline)
    records = []
    for repo_id, repo in binding["repositories"].items():
        mirror = WORK / "mirrors" / repo_id
        mirror.mkdir(parents=True, mode=0o700)
        target = mirror / "repodata/repomd.xml"
        records.append(fetch(repo["baseurl"] + "repodata/repomd.xml", target,
            repo["repomd_bytes"], repo["repomd_sha256"], deadline))
        entries = repomd_entries(target.read_bytes())
        require(entries == repo["metadata"], "repomd differs from pinned complete metadata entries")
        for kind, entry in entries.items():
            path = safe_child(mirror, entry["href"])
            records.append(fetch(repo["baseurl"] + entry["href"], path,
                entry["bytes"], entry["sha256"], deadline))
            # An exact checksum and open-size bound also controls decompression.
            if path.suffix == ".zst":
                output, _ = command(["/usr/bin/zstd", "--decompress", "--stdout", str(path)],
                    deadline, repo_id + "-" + kind + "-open", entry["open_bytes"], 300)
            elif path.suffix == ".gz":
                output = WORK / (repo_id + "-" + kind + "-open.stdout")
                with gzip.open(path, "rb") as stream, output.open("xb") as dest:
                    size = 0
                    while chunk := stream.read(65536):
                        deadline.remaining(300)
                        size += len(chunk)
                        require(size <= entry["open_bytes"], "metadata expanded bound")
                        dest.write(chunk)
            else:
                raise RuntimeError("unsupported compressed metadata")
            require(output.stat().st_size == entry["open_bytes"] and
                sha_file(output) == entry["open_sha256"], "expanded metadata mismatch")
        # A private, unsigned metadata snapshot is traced exactly to verified
        # official repomd checksums; payload signatures are independently mandatory.
        (WORK / "config/repos" / (repo_id + ".repo")).write_text(
            f"[{repo_id}]\nname={repo_id}\nbaseurl={mirror.as_uri()}/\nenabled=1\n"
            "gpgcheck=1\nrepo_gpgcheck=0\nskip_if_unavailable=0\nzchunk=0\n")
    write_json(WORK / "metadata-downloads.json", records)


def catalog(repo_id):
    path = WORK / (repo_id + "-primary-open.stdout")
    result = {}
    for event, item in ET.iterparse(path, events=("end",)):
        if item.tag != "{" + C["c"] + "}package":
            continue
        version = item.find("c:version", C).attrib
        key = (item.find("c:name", C).text, version["epoch"] + ":" + version["ver"] + "-" + version["rel"],
            item.find("c:arch", C).text)
        checksum = item.find("c:checksum", C)
        require(checksum.attrib["type"] == "sha256", "unsupported RPM payload digest")
        location = item.find("c:location", C).attrib["href"]
        relative_member(location)
        require(key not in result, "duplicate primary package identity")
        result[key] = {"sha256": checksum.text, "location": location,
            "bytes": int(item.find("c:size", C).attrib["package"])}
        item.clear()
    return result


def resolve(deadline):
    readonly_image()
    rows = sorted(tuple(row) for row in json.loads((WORK / "actual-installed-headers.json").read_text()))
    installed = {(name, arch): evr for name, evr, arch in rows}
    require(len(installed) == len(rows), "multiversion installed identity unsupported")
    actions, inbound, serialized, config = solve(WORK, installed)
    enriched = []
    catalogs = {name: catalog(name) for name in {row["repo"] for row in inbound}}
    for row in inbound:
        key = (row["name"], row["evr"], row["arch"])
        entry = catalogs[row["repo"]].get(key)
        require(entry and entry["location"] == row["location"] and entry["bytes"] == row["download_bytes"],
            "resolved goal/official primary identity mismatch")
        enriched.append({**row, **entry})
    write_json(WORK / "all-actions.json", actions)
    write_json(WORK / "validated-inbound.json", enriched)
    write_json(WORK / "actual-solver-config.json", config)
    (WORK / "transaction-serialized-NOT-REPLAYED.json").write_text(serialized)
    require(installed_headers(WORK / "solver-root")[1] == rows, "solver changed installed headers")
    deadline.remaining(1)


def key_fingerprints(path, deadline, name):
    output, _ = command(["/usr/bin/gpg", "--homedir", str(WORK / "gpg-home"), "--batch",
        "--with-colons", "--show-keys", str(path)], deadline, name, 100000, 30)
    return [line.split(":")[9] for line in output.read_text().splitlines() if line.startswith("fpr:")]


def payloads(binding, deadline):
    import rpm
    readonly_image()
    private_dir(WORK / "gpg-home", WORK, fresh=True)
    trust = private_dir(WORK / "trust-keys", WORK, fresh=True)
    paths = {
        "fedora": IMAGE / "etc/pki/rpm-gpg/RPM-GPG-KEY-fedora-44-primary",
        "fusion": IMAGE / "usr/share/distribution-gpg-keys/rpmfusion/RPM-GPG-KEY-rpmfusion-free-fedora-44",
    }
    key_records = []
    image_headers, _ = installed_headers(IMAGE)
    for name, key in paths.items():
        key = image_member(IMAGE, key.relative_to(IMAGE).as_posix())
        require(key.is_file(), "candidate key file missing")
        require(key.stat().st_size <= 100000, "candidate key size")
        logical = key.relative_to(IMAGE).as_posix()
        owners = [h for h in image_headers if "/" + logical in (h["filenames"] or [])]
        require(len(owners) == 1 and owners[0]["name"] ==
            ("distribution-gpg-keys" if name == "fusion" else "fedora-gpg-keys"), "candidate key header owner")
        entry = header_files(owners[0])[logical]
        require(hashlib.new(entry["digest_algorithm"], key.read_bytes()).hexdigest() == entry["digest"],
            "candidate key/header digest")
        require(key_fingerprints(key, deadline, "key-" + name) == [KEYS[name]], "actual image key fingerprint")
        key_records.append({"logical_file": logical, "sha256": sha_file(key), "fingerprint": KEYS[name],
            "installed_header_owner": owners[0]["name"]})
        command(["/usr/bin/rpmkeys", "--noplugins", "--define", "_keyring fs", "--define",
            "_keyringpath " + str(trust), "--import", str(key)], deadline, "key-import-" + name, 100000, 30)
    write_json(WORK / "actual-key-provenance.json", key_records)
    rpm.addMacro("_keyring", "fs")
    rpm.addMacro("_keyringpath", str(trust))
    rpm.addMacro("_pkgverify_level", "all")
    selected = json.loads((WORK / "validated-inbound.json").read_text())
    all_selected = {}
    signature_records = []
    require(len({row["name"] for row in selected}) == len(selected), "duplicate inbound name unsupported")
    total = sum(row["bytes"] for row in selected)
    require(total <= 128000000 and len(selected) <= 64, "validated payload bounds changed")
    for index, row in enumerate(selected):
        path = WORK / "payloads" / (str(index) + ".rpm")
        record = fetch(binding["repositories"][row["repo"]]["baseurl"] + row["location"],
            path, row["bytes"], row["sha256"], deadline)
        output, crypto = command(["/usr/bin/rpmkeys", "--noplugins", "--define", "_keyring fs",
            "--define", "_keyringpath " + str(trust), "--define", "_pkgverify_level all",
            "--checksig", "--verbose", str(path)], deadline, "signature-" + str(index), 100000, 30)
        fp = KEYS["fusion" if row["repo"].startswith("rpmfusion-") else "fedora"]
        verify_signature_result(crypto["exit_status"], output.read_text(), fp)
        require(sha_file(path) == row["sha256"], "payload changed after crypto")
        with path.open("rb") as stream:
            header = rpm.TransactionSet().hdrFromFdno(stream.fileno())
        require((header["name"], str(header["epoch"] or 0) + ":" + header["version"] + "-" + header["release"],
            header["arch"]) == (row["name"], row["evr"], row["arch"]), "signed header identity mismatch")
        files = header_files(header)
        identity = {key: row[key] for key in ("name", "evr", "arch")}
        all_selected[row["name"]] = {"identity": identity, "payload": str(path), "files": files,
            "license": header["license"], "source_RPM": header["sourcerpm"], "payload_sha256": row["sha256"]}
        signature_records.append({**record, "package": row["name"], "identity": identity, "expected_full_signer": fp,
            "actual_crypto_record": crypto})
    old_headers, rows = installed_headers(IMAGE)
    retained = {}
    for header in old_headers:
        if header["name"] in EXPECTED_REMOVALS or header["name"] == "gpg-pubkey":
            continue
        for path, entry in header_files(header).items():
            retained.setdefault(path, []).append({"owner": header["name"], **entry})
    inbound_files = {}
    for package_name, package in all_selected.items():
        for path, entry in package["files"].items():
            for other in retained.get(path, []) + inbound_files.get(path, []):
                both_directories = stat.S_ISDIR(entry["mode"]) and stat.S_ISDIR(other["mode"])
                same = (entry["mode"], entry["digest"], entry["link"], entry["uid"], entry["gid"]) == (
                    other["mode"], other["digest"], other["link"], other["uid"], other["gid"])
                require(both_directories or same, "file conflict with retained owner:" + path)
            inbound_files.setdefault(path, []).append({"owner": package_name, **entry})
    proof = provider_proof("usr/lib64/libOpenCL.so.1", all_selected, retained, IMAGE)
    providers = proof["initial_header_owners"]
    write_json(WORK / "signed-selected-headers.json", all_selected)
    write_json(WORK / "every-payload-signature.json", signature_records)
    write_json(WORK / "file-collision-and-provider.json", {"passed": True, "OpenCL_actual_header_owners": providers,
        "exact_provider_proof": proof, "RPM_transaction_test_or_runner_called": False})


def copy_actual_component(old_headers, destination):
    members, hardlinks = {}, {}
    for header in old_headers:
        if header["name"] in EXPECTED_REMOVALS:
            for name, entry in header_files(header).items():
                if entry["flags"] & 64:
                    continue
                if name in members:
                    require(members[name] == entry, "old shared-owner disagreement")
                members[name] = entry
    for name, entry in sorted(members.items()):
        logical = relative_member(name)
        parent = IMAGE if str(logical.parent) == "." else image_member(IMAGE, str(logical.parent))
        origin, target = parent / logical.name, safe_child(destination, name)
        require(origin.exists() or origin.is_symlink(), "missing actual old component member:" + name)
        s = origin.lstat()
        require(stat.S_IFMT(s.st_mode) == stat.S_IFMT(entry["mode"]), "actual old member type mismatch")
        target.parent.mkdir(parents=True, exist_ok=True)
        if stat.S_ISDIR(s.st_mode):
            target.mkdir(exist_ok=True)
        elif stat.S_ISLNK(s.st_mode):
            require(os.readlink(origin) == entry["link"], "actual old symlink/header mismatch")
            os.symlink(entry["link"], target)
        elif stat.S_ISREG(s.st_mode):
            require(hashlib.new(entry["digest_algorithm"], origin.read_bytes()).hexdigest() == entry["digest"],
                "actual old file/header mismatch")
            inode = (s.st_dev, s.st_ino)
            metadata = (entry["mode"], entry["uid"], entry["gid"], entry["digest_algorithm"], entry["digest"])
            if inode in hardlinks:
                require(hardlinks[inode][1] == metadata, "old hardlink signed metadata disagreement")
                os.link(hardlinks[inode][0], target, follow_symlinks=False)
            else:
                shutil.copyfile(origin, target)
                hardlinks[inode] = (target, metadata)
            target.chmod(stat.S_IMODE(entry["mode"]))
        else:
            raise RuntimeError("special old component member unsupported")
    for name, entry in sorted(members.items(), key=lambda row: row[0].count("/"), reverse=True):
        if stat.S_ISDIR(entry["mode"]):
            safe_child(destination, name).chmod(stat.S_IMODE(entry["mode"]))
    return members


def compress(deadline):
    readonly_image()
    components = private_dir(WORK / "components", WORK, fresh=True)
    old, new = components / "old", components / "new"
    old.mkdir(); new.mkdir()
    old_headers, _ = installed_headers(IMAGE)
    copy_actual_component(old_headers, old)
    selected = json.loads((WORK / "signed-selected-headers.json").read_text())
    hardlinks, directory_modes = {}, {}
    for index, package in enumerate(selected.values()):
        path = Path(package["payload"])
        require(sha_file(path) == package["payload_sha256"], "changed payload before extraction")
        output, _ = command(["/usr/bin/rpm2cpio", str(path)], deadline, "cpio-" + str(index), 1000000000, 120)
        stage = components / ("pkg-" + str(index)); stage.mkdir()
        with output.open("rb") as stream:
            unpack(stream, stage, {name: entry for name, entry in package["files"].items()
                if not entry["flags"] & 64})
        for current, dirs, files in os.walk(stage, followlinks=False):
            for name in dirs + files:
                source = Path(current) / name
                target = safe_child(new, source.relative_to(stage).as_posix())
                if source.is_dir() and not source.is_symlink():
                    require(not target.is_symlink(), "component directory collision")
                    target.mkdir(parents=True, exist_ok=True)
                    relative = source.relative_to(stage).as_posix()
                    mode = stat.S_IMODE(source.stat().st_mode)
                    require(relative not in directory_modes or directory_modes[relative] == mode, "new directory mode collision")
                    directory_modes[relative] = mode
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists() or target.is_symlink():
                        require(source.is_symlink() == target.is_symlink(), "new-package member type collision")
                        require((os.readlink(source) == os.readlink(target)) if source.is_symlink()
                            else (stat.S_IMODE(source.stat().st_mode) == stat.S_IMODE(target.stat().st_mode)
                                and sha_file(source) == sha_file(target)), "new-package member collision")
                        continue
                    if source.is_symlink():
                        os.symlink(os.readlink(source), target)
                    else:
                        inode = (source.stat().st_dev, source.stat().st_ino)
                        if inode in hardlinks:
                            os.link(hardlinks[inode], target, follow_symlinks=False)
                        else:
                            shutil.copyfile(source, target)
                            hardlinks[inode] = target
                        target.chmod(stat.S_IMODE(source.stat().st_mode))
    for name, mode in sorted(directory_modes.items(), key=lambda row: row[0].count("/"), reverse=True):
        safe_child(new, name).chmod(mode)
    notices = {}
    for row in tree_manifest(new):
        if row["type"] == "regular" and row["path"].startswith("usr/share/licenses/"):
            require(row["bytes"] <= 1000000, "license text bound")
            notices[row["path"]] = {"sha256": row["sha256"],
                "text": (new / row["path"]).read_text(encoding="utf-8", errors="strict")}
    require(sum(len(v["text"].encode()) for v in notices.values()) <= 3000000, "all license notices bound")
    write_json(WORK / "signed-payload-license-notices.json", notices)
    records = []
    for name, tree in (("old", old), ("new", new)):
        manifest = tree_manifest(tree)
        logical = sum(row.get("bytes", 0) for row in manifest)
        require(logical <= 1000000000, "component logical bound")
        write_json(WORK / (name + "-component-members.json"), manifest)
        image = WORK / (name + "-component.erofs")
        _, metrics = command(["/usr/bin/mkfs.erofs", "-z", "lzma,level=6", "-Efragments", "-C", "1048576",
            "--workers=1", "--all-root", "-T", "1791309429", "-U", "00000000-0000-0000-0000-000000000000",
            str(image), str(tree)], deadline, "compress-" + name, 20000000, 300)
        roundtrip = WORK / (name + "-roundtrip")
        command(["/usr/bin/fsck.erofs", "--no-preserve-owner", "--preserve-perms", "--extract=" + str(roundtrip),
            str(image)], deadline, "roundtrip-" + name, 20000000, 300)
        require(tree_manifest(roundtrip) == manifest, "EROFS content/type/directory roundtrip differs")
        records.append({"side": name, "logical_regular_bytes": logical, "EROFS_bytes": image.stat().st_size,
            "EROFS_sha256": sha_file(image), "metrics": metrics, "member_sha256": manifest_digest(manifest)})
    write_json(WORK / "component-metrics-PROVISIONAL.json", {"sides": records,
        "standalone_component_delta_bytes": records[1]["EROFS_bytes"] - records[0]["EROFS_bytes"],
        "valid_updated_root": False, "valid_ISO": False, "whole_ISO_delta_proved": False,
        "runtime_playback": "UNRUN", "normalization": "mkfs all-root/fixed-time; no xattrs or target scripts/caches; identical parameters"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=STAGES)
    args = parser.parse_args()
    private_dir(WORK, Path("/"))
    binding = json.loads((SOURCE / "runtime-binding.json").read_text())
    validate_binding(binding)
    tool_identity(binding)
    context = json.loads((WORK / "context.json").read_text())
    deadline = Deadline(context["started_monotonic"], 3600)
    # Reserve finite time for evidence and host cleanup inside the global bound.
    require(deadline.remaining(3600) > 30, "global evidence reserve exhausted")
    deadline.end = min(deadline.end - 30, time.monotonic() + deadline.remaining(LIMITS[args.stage]))
    resources()
    index = STAGES.index(args.stage)
    require(not (WORK / (args.stage + "-observed.json")).exists(), "stage replay")
    if index:
        previous = json.loads((WORK / (STAGES[index-1] + "-observed.json")).read_text())
        require(previous["passed"] and previous["context_sha256"] == sha_file(WORK / "context.json"),
            "previous phase absent/failed/stale")
    passed = False
    reason = None
    try:
        if args.stage == "archive":
            from core import ISO_SHA, ISO_BYTES
            image = Path("/input/iso/Arctic-Linux-1.2-candidate-37507582946-1-x86_64.iso")
            require(image.is_file() and not image.is_symlink() and image.stat().st_size == ISO_BYTES
                and sha_file(image) == ISO_SHA, "immediate actual ISO bytes")
            command(["/usr/bin/xorriso", "-osirrox", "on", "-indev", str(image), "-extract",
                "/" + binding["root_member"], str(WORK / "archive-root.img")], deadline,
                "actual-ISO-member-extract", 20000000, 300)
        elif args.stage == "extract":
            member = WORK / "archive-root.img"
            require(member.is_file() and not member.is_symlink() and
                sha_file(member) == binding["root_member_sha256"], "exact archived root member")
            command(["/usr/bin/fsck.erofs", "--no-preserve-owner", "--no-preserve-perms", "--extract=" + str(EXTRACTED / "root"),
                str(member)], deadline, "actual-root-extract", 20000000, 900)
            # Type-aware census without following target-image symlinks.
            logical = 0
            count = 0
            for current, dirs, files in os.walk(EXTRACTED / "root", followlinks=False):
                deadline.remaining(1)
                for name in dirs + files:
                    s = (Path(current) / name).lstat()
                    count += 1
                    if stat.S_ISREG(s.st_mode):
                        logical += s.st_size
                    require(count <= 500000 and logical <= 16000000000, "actual extracted root bound")
            write_json(WORK / "actual-root-census.json", {"members": count, "logical_regular_bytes": logical})
        else:
            {"metadata": metadata, "solve": lambda b, d: resolve(d),
                "payloads": payloads, "compress": lambda b, d: compress(d)}[args.stage](binding, deadline)
        if args.stage not in ("archive", "extract", "metadata"):
            require(original_state() == json.loads((WORK / "original-rpmdb-and-DNF-state.json").read_text()),
                "original image RPMdb/state/repos changed")
            write_json(WORK / (args.stage + "-original-state-unchanged.json"), {"passed": True,
                "actual_state_sha256": manifest_digest(original_state())})
        deadline.remaining(1)
        passed = True
    except Exception as error:
        reason = failure_detail(error)
        raise
    finally:
        write_json(WORK / (args.stage + "-observed.json"), {"stage": args.stage, "passed": passed,
            "failure": reason, "context_sha256": sha_file(WORK / "context.json"),
            "binding_sha256": sha_file(SOURCE / "runtime-binding.json"),
            "finished_monotonic": time.monotonic(), "valid_ISO": False, "runtime_playback": "UNRUN"})


if __name__ == "__main__":
    main()
