"""Pure fail-closed policy and evidence helpers for a source-only codec audit."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import re
import stat
import time
import urllib.parse
import xml.etree.ElementTree as ET

CANDIDATE = "fe4742c8b9414c45f0bcbb0a4191f116383c60d1"
ISO_SHA = "84c9c88ebcbcaf69dbabf56509a9ceb2db58e5dc41d7bae12093edba12f60718"
ISO_BYTES = 1880244224
RUN = 37507582946
ARTIFACT = 11434226349
INVENTORY_SHA = "7a34adfa4bf7a9f4bd57f0b325a91202121dec9e9b2dca9766c0e7fdf091603a"
EXPECTED_REMOVALS = frozenset(("ffmpeg-free", "libavcodec-free", "libavdevice-free",
    "libavfilter-free", "libavformat-free", "libavutil-free", "libswresample-free", "libswscale-free"))
ROOTS = {"ffmpeg": "0:8.1.3-1.fc44", "ffmpeg-libs": "0:8.1.3-1.fc44",
    "libavdevice": "0:8.1.3-1.fc44", "gstreamer1-plugin-libav": "0:1.28.7-1.fc44"}
KEYS = {"fedora": "36F612DCF27F7D1A48A835E4DBFCF71C6D9F90A6",
    "fusion": "E9A491A3DE247814E7E067EAE06F8ECDD651FF2E"}
KNOWN_MODES = frozenset(("release", "draft", "boot_test", "nix_acceptance",
    "performance_acceptance", "same_iso_recovery", "offline_cycle_recovery",
    "same_iso_native_smoke", "same_iso_pcmanfm_diagnostic", "safe_visual_diagnostic"))
REPOS = frozenset(("fedora", "updates", "rpmfusion-free", "rpmfusion-free-updates"))
M = {"m": "http://linux.duke.edu/metadata/repo"}
C = {"c": "http://linux.duke.edu/metadata/common", "r": "http://linux.duke.edu/metadata/rpm"}


class GuardError(RuntimeError):
    pass


def require(ok, reason):
    if not ok:
        raise GuardError(reason)


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, data):
    path = Path(path)
    require(not path.is_symlink(), "linked evidence destination")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write("\n")


def relative_member(value):
    require(isinstance(value, str) and value and "\x00" not in value and "\\" not in value,
        "malformed member")
    if value.startswith("./"):
        value = value[2:]
    p = PurePosixPath(value)
    require(not p.is_absolute() and all(x not in ("", ".", "..") for x in p.parts)
        and p.as_posix() == value, "unsafe member path")
    return p


def safe_child(root, value):
    root = Path(root)
    path = root.joinpath(*relative_member(value).parts)
    cursor = path.parent
    while cursor != root:
        require(not cursor.is_symlink(), "symlink extraction ancestor")
        cursor = cursor.parent
    require(not root.is_symlink(), "linked extraction root")
    return path


def private_dir(path, parent, fresh=False):
    path, parent = Path(path), Path(parent)
    require(path.is_absolute() and path != parent and parent in path.parents, "outside private parent")
    cursor = path
    while cursor != parent.parent:
        require(not cursor.is_symlink(), "linked private path")
        cursor = cursor.parent
    if fresh:
        require(not path.exists(), "stale private path")
        path.mkdir(mode=0o700)
    require(path.is_dir(), "missing private path")
    s = path.stat()
    require(s.st_uid == os.getuid() and not s.st_mode & 0o022, "private path ownership/mode")
    return path


class Deadline:
    """Every phase and cleanup is subordinate to one finite host monotonic bound."""
    def __init__(self, started, total=3600, clock=time.monotonic):
        self.clock, self.end = clock, float(started) + total
        require(float(started) <= clock() < self.end, "stale/future global deadline")

    def remaining(self, phase_limit):
        left = min(float(phase_limit), self.end - self.clock())
        require(left > 0, "global deadline exceeded")
        return left


def validate_inputs(inputs, specification, source_sha, event):
    require(event == "workflow_dispatch", "diagnostic event required")
    require(set(inputs) == set(specification), "actual workflow inputs differ from reviewed input set")
    require(inputs["codec_evaluation"] is True, "explicit codec-only selection required")
    require(re.fullmatch(r"[0-9a-f]{40}", source_sha or "") is not None,
        "exact source SHA required")
    require(inputs["codec_source_sha"] == source_sha, "requested source SHA differs")
    for key, value in inputs.items():
        if specification[key]["type"] == "boolean":
            require(type(value) is bool, "non-boolean workflow input:" + key)
        else:
            require(type(value) is str, "non-string workflow input:" + key)
        if key in KNOWN_MODES:
            require(value is False, "mixed mode:" + key)
    require(inputs.get("tag", "") == "", "release tag requested")


def validate_binding(binding):
    require(binding.get("schema") == "arctic-codec-runtime-v1", "binding schema")
    require(binding.get("status") == "BOUND_REVIEW_REQUIRED", "runtime binding BLOCKED")
    require(re.fullmatch(r"(?:sha256:[0-9a-f]{64}|registry\.fedoraproject\.org/[a-zA-Z0-9/_-]+@sha256:[0-9a-f]{64})",
        binding.get("worker_image") or "") is not None, "unbound/mutable tools image")
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", binding.get("worker_image") or "") is not None,
        "runtime requires exact reviewed local image ID")
    tools = binding.get("tools_artifact")
    require(type(tools) is dict, "reviewed tools artifact BLOCKED")
    for field in ("review_sha256", "image_manifest_sha256", "archive_sha256"):
        require(re.fullmatch(r"[0-9a-f]{64}", tools.get(field) or "") is not None, "unbound tools artifact hash:" + field)
    require(type(tools.get("archive_bytes")) is int and 0 < tools["archive_bytes"] <= 2000000000, "tools archive bound")
    require(type(tools.get("artifact_id")) is int and tools["artifact_id"] > 0 and
        type(tools.get("run_id")) is int and tools["run_id"] > 0 and
        re.fullmatch(r"[0-9a-f]{40}", tools.get("source_sha") or "") is not None, "tools artifact provenance unbound")
    files = binding.get("tool_file_hashes")
    required = {"usr/bin/python3", "usr/bin/rpmkeys", "usr/bin/rpm2cpio", "usr/bin/gpg",
        "usr/bin/zstd", "usr/bin/xorriso", "usr/bin/mkfs.erofs", "usr/bin/fsck.erofs"}
    require(type(files) is dict and required <= set(files) and len(files) <= 128, "tool binary/module map unbound")
    require(any("libdnf5" in name and name.endswith(".so") for name in files) and
        any("rpm" in name and name.endswith(".so") for name in files), "Python extension files unbound")
    for name, digest in files.items():
        relative_member(name)
        require(re.fullmatch(r"[0-9a-f]{64}", digest or "") is not None, "unbound tool file hash")
    require(re.fullmatch(r"[0-9a-f]{64}", binding.get("execution_review_sha256") or "") is not None,
        "execution source review binding missing")
    require(binding.get("keys") == KEYS, "full independent key fingerprint mismatch")
    require(set(binding.get("repositories", {})) == REPOS, "unexpected repository set")
    for repo in binding["repositories"].values():
        u = urllib.parse.urlsplit(repo["baseurl"])
        require(u.scheme == "https" and u.hostname in ("dl.fedoraproject.org", "download1.rpmfusion.org")
            and not u.username and not u.password and u.port is None and not u.query and not u.fragment,
            "unapproved official repository URL")
        require(re.fullmatch(r"[0-9a-f]{64}", repo["repomd_sha256"]) is not None, "missing repomd pin")
        require(type(repo["repomd_bytes"]) is int and 0 < repo["repomd_bytes"] <= 100000, "repomd byte bound")
        require(set(repo["metadata"]) == {"primary", "filelists"}, "metadata types unbound")
        for entry in repo["metadata"].values():
            relative_member(entry["href"])
            require(re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is not None, "metadata checksum pin")
            require(type(entry["bytes"]) is int and 0 < entry["bytes"] < 1000000000, "metadata size pin")
            require(re.fullmatch(r"[0-9a-f]{64}", entry.get("open_sha256", "")) is not None and
                type(entry.get("open_bytes")) is int and 0 < entry["open_bytes"] <= 1000000000,
                "expanded metadata checksum/size pin")
    require(binding.get("root_member") == "LiveOS/squashfs.img", "unbound archived root member")
    require(re.fullmatch(r"[0-9a-f]{64}", binding.get("root_member_sha256") or "") is not None,
        "unbound archived root checksum")
    require(binding.get("tool_packages") == {
        "dnf5": "5.4.6.0-1.fc44.x86_64", "python3-libdnf5": "5.4.6.0-1.fc44.x86_64",
        "rpm": "6.0.2-1.fc44.x86_64", "python3-rpm": "6.0.2-1.fc44.x86_64",
        "erofs-utils": "1.9.4-1.fc44.x86_64", "xorriso": "1.5.8-2.fc44.x86_64",
        "zstd": "1.5.7-5.fc44.x86_64", "gnupg2": "2.4.9-16.fc44.x86_64"},
        "unbound tool API/package identities")


def repomd_entries(data):
    require(b"<!DOCTYPE" not in data and b"<!ENTITY" not in data, "XML entity declaration")
    out = {}
    for row in ET.fromstring(data).findall("m:data", M):
        kind = row.attrib["type"]
        if kind not in ("primary", "filelists"):
            continue
        checksum = row.find("m:checksum", M)
        require(checksum.attrib["type"] == "sha256", "unsupported metadata digest")
        require(kind not in out, "duplicate metadata type")
        href = row.find("m:location", M).attrib["href"]
        relative_member(href)
        require(row.find("m:open-checksum", M).attrib["type"] == "sha256", "unsupported expanded metadata digest")
        out[kind] = {"href": href, "sha256": checksum.text,
            "bytes": int(row.find("m:size", M).text),
            "open_sha256": row.find("m:open-checksum", M).text,
            "open_bytes": int(row.find("m:open-size", M).text)}
    require(set(out) == {"primary", "filelists"}, "missing primary/file-provider metadata")
    return out


def check_artifact(metadata):
    require(metadata["id"] == ARTIFACT and not metadata["expired"], "wrong/expired official artifact")
    r = metadata["workflow_run"]
    require(r["id"] == RUN and r["head_sha"] == CANDIDATE, "official artifact source/run")


def validate_actions(rows, installed):
    require(rows and len(rows) <= 128, "empty/oversized action set")
    removed, inbound, seen, inbound_names = set(), [], set(), set()
    for row in rows:
        key = (row["name"], row["evr"], row["arch"], row["action"])
        require(key not in seen, "duplicate action")
        seen.add(key)
        require(row["arch"] in ("x86_64", "noarch"), "unexpected architecture")
        if row["action"] == "Remove":
            require(row["name"] in EXPECTED_REMOVALS and
                installed.get((row["name"], row["arch"])) == row["evr"], "unexpected removal/header")
            removed.add(row["name"])
        elif row["action"] == "Install":
            require(row["name"] not in inbound_names, "duplicate inbound name unsupported")
            inbound_names.add(row["name"])
            require((row["name"], row["arch"]) not in installed, "retained package change")
            require(row["repo"] in REPOS, "unapproved inbound repository")
            require(type(row["download_bytes"]) is int and 0 < row["download_bytes"] <= 64000000,
                "single payload limit")
            inbound.append(row)
        else:
            raise GuardError("unexpected retained/action change:" + row["action"])
    require(removed == EXPECTED_REMOVALS, "expected eight removals differ")
    require(len(inbound) <= 64 and sum(x["download_bytes"] for x in inbound) <= 128000000,
        "payload count/total limit")
    for name, evr in ROOTS.items():
        require(sum(x["name"] == name and x["evr"] == evr and x["arch"] == "x86_64"
            for x in inbound) == 1, "exact mandatory root missing:" + name)
    return inbound


def verify_signature_result(returncode, output, fingerprint):
    require(returncode == 0, "RPM signature process failure")
    require(not re.search(r"NOKEY|NOT OK|NOTTRUSTED|BAD|UNSIGNED|NOT SIGNED", output, re.I),
        "bad/missing signature")
    signature_lines = [line for line in output.splitlines() if re.search(r"signature", line, re.I)
        and re.search(r"\bOK\s*$", line)]
    require(signature_lines, "digest-only verification")
    for line in signature_lines:
        m = re.search(r"key fingerprint:\s+([0-9a-f]{40})\b", line, re.I)
        require(m and m[1].lower() == fingerprint.lower(),
            "unexpected actual signer")


def tree_manifest(root):
    """Include directories, types and links, never follow symbolic links."""
    root = Path(root)
    rows, inodes = [], {}
    for current, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(current) / name
            s = path.lstat()
            row = {"path": path.relative_to(root).as_posix(), "mode": stat.S_IMODE(s.st_mode)}
            if stat.S_ISDIR(s.st_mode):
                row["type"] = "directory"
            elif stat.S_ISLNK(s.st_mode):
                row.update(type="symlink", target=os.readlink(path))
            elif stat.S_ISREG(s.st_mode):
                row.update(type="regular", bytes=s.st_size, sha256=sha_file(path))
                inodes.setdefault((s.st_dev, s.st_ino), []).append(row)
            else:
                raise GuardError("unsupported special member:" + row["path"])
            rows.append(row)
    for group in inodes.values():
        if len(group) > 1:
            first = min(row["path"] for row in group)
            for row in group:
                row["hardlink_group"] = first
    return sorted(rows, key=lambda x: x["path"])


def image_member(root, value):
    """Resolve logical image links inside root, including absolute image links."""
    root = Path(root)
    parts = list(relative_member(value).parts)
    resolved, links = [], 0
    while parts:
        part = parts.pop(0)
        if part == ".":
            continue
        if part == "..":
            require(resolved, "image link escapes logical root")
            resolved.pop()
            continue
        path = root.joinpath(*resolved, part)
        if path.is_symlink():
            links += 1
            require(links <= 32, "image symlink cycle")
            target = PurePosixPath(os.readlink(path))
            if target.is_absolute():
                resolved = []
                parts = list(target.parts[1:]) + parts
            else:
                parts = list(target.parts) + parts
        else:
            resolved.append(part)
    return root.joinpath(*resolved)


def manifest_digest(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class PhaseFailure(GuardError):
    """Preserve the first failure and every bounded cleanup/close failure."""
    def __init__(self, primary, secondary):
        self.primary = failure_detail(primary) if primary is not None else None
        self.secondary = list(secondary)
        first = (self.primary["type"] + ": " + self.primary["message"]) if self.primary else "phase cleanup failed"
        rest = "; cleanup: " + "; ".join(x["type"] + ": " + x["message"] for x in self.secondary) if self.secondary else ""
        super().__init__(first + rest)


def failure_detail(error):
    if isinstance(error, PhaseFailure):
        return {"type": type(error).__name__, "message": str(error),
            "primary": error.primary, "secondary": error.secondary}
    return {"type": type(error).__name__, "message": str(error)}


def reap_owned(process, end, secondary, clock=time.monotonic):
    """Only the Popen child/session created by the caller; never unbounded wait."""
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, 9)
    except ProcessLookupError:
        pass
    except Exception as error:
        secondary.append(failure_detail(error))
    if process.poll() is None:
        left = min(5., end - clock())
        if left <= 0:
            secondary.append({"type": "GuardError", "message": "owned-child reap deadline exhausted"})
        else:
            try:
                process.wait(timeout=left)
            except Exception as error:
                secondary.append(failure_detail(error))


def close_observed(stream, secondary):
    if stream is not None:
        try:
            stream.close()
        except Exception as error:
            secondary.append(failure_detail(error))


def link_destination(path, target):
    require(isinstance(target, str) and target and "\x00" not in target and "\\" not in target,
        "malformed provider symlink")
    parts = [] if target.startswith("/") else list(relative_member(path).parent.parts)
    if parts == ["."]:
        parts = []
    for part in PurePosixPath(target).parts:
        if part in ("/", "."):
            continue
        if part == "..":
            require(parts, "provider link escapes image")
            parts.pop()
        else:
            parts.append(part)
    require(parts, "provider link points to root")
    return relative_member("/".join(parts)).as_posix()


def provider_proof(path, selected, retained, image):
    """Actual retained body proof or signed inbound regular-target closure.

    Inbound body remains explicitly pending the mandatory CPIO/header gate.
    Directories, ghosts, unbound links and missing/changed retained bodies fail.
    """
    table = {name: [{"source": "retained", **entry} for entry in entries]
        for name, entries in retained.items()}
    for owner, package in selected.items():
        for name, entry in package["files"].items():
            table.setdefault(name, []).append({"source": "inbound", "owner": owner, **entry})
    first = path
    chain, visited = [], set()
    while True:
        require(path not in visited and len(visited) < 32, "provider symlink cycle/limit")
        visited.add(path)
        entries = [e for e in table.get(path, []) if not e["flags"] & 64]
        require(entries, "exact non-ghost provider target unbound:" + path)
        kinds = {stat.S_IFMT(e["mode"]) for e in entries}
        require(len(kinds) == 1 and kinds <= {stat.S_IFREG, stat.S_IFLNK},
            "unsupported provider member type:" + path)
        kind = next(iter(kinds))
        metadata = {(e["mode"], e["uid"], e["gid"], e["link"],
            e["digest"] if kind == stat.S_IFREG else None,
            e["digest_algorithm"] if kind == stat.S_IFREG else None) for e in entries}
        require(len(metadata) == 1, "provider header metadata disagreement")
        body_proofs = []
        for entry in entries:
            if kind == stat.S_IFREG:
                algorithm = entry["digest_algorithm"]
                require(algorithm in ("md5", "sha1", "sha256", "sha384", "sha512"), "provider digest algorithm")
                require(re.fullmatch(r"[0-9a-fA-F]{" + str(hashlib.new(algorithm).digest_size * 2) + r"}",
                    entry["digest"] or "") is not None, "provider regular digest unbound")
            if entry["source"] == "retained":
                logical = relative_member(path)
                parent = Path(image) if str(logical.parent) == "." else image_member(image, str(logical.parent))
                actual = parent / logical.name
                require(actual.exists() or actual.is_symlink(), "retained provider member absent")
                s = actual.lstat()
                require(stat.S_IFMT(s.st_mode) == kind, "retained provider physical type differs")
                if kind == stat.S_IFLNK:
                    require(os.readlink(actual) == entry["link"], "retained provider link/header differs")
                    body_proofs.append({"owner": entry["owner"], "literal_link": entry["link"]})
                else:
                    require(s.st_size <= 1000000000, "retained provider body bound")
                    h = hashlib.new(entry["digest_algorithm"])
                    with actual.open("rb") as stream:
                        for block in iter(lambda: stream.read(1048576), b""):
                            h.update(block)
                    require(h.hexdigest() == entry["digest"].lower(), "retained provider body/header differs")
                    body_proofs.append({"owner": entry["owner"], "body_bytes": s.st_size,
                        "header_digest": h.hexdigest(), "actual_body_sha256": sha_file(actual)})
        chain.append({"path": path, "type": "regular" if kind == stat.S_IFREG else "symlink",
            "header_owners": sorted({e["owner"] for e in entries}),
            "retained_actual_proofs": body_proofs,
            "inbound_signed_header_target_bound": any(e["source"] == "inbound" for e in entries)})
        if kind == stat.S_IFREG:
            return {"requested_path": first, "chain": chain,
                "initial_header_owners": chain[0]["header_owners"],
                "inbound_body_validation": "PENDING_MANDATORY_CPIO_HEADER_GATE" if
                    any(item["inbound_signed_header_target_bound"] for item in chain) else "NOT_APPLICABLE",
                "runtime_library_load": "UNRUN"}
        path = link_destination(path, entries[0]["link"])
