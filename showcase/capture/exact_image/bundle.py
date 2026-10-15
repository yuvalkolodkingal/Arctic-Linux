#!/usr/bin/env python3
"""Export and validate a closed, unreviewed exact-image capture bundle."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

from PIL import Image

try:
    from . import contract as c
    from . import host
except ImportError:
    import contract as c
    import host


BUNDLE_NAME = "bundle.json"
MANIFEST_KEYS = {"schema", "status", "release_acceptance", "image", "execution", "vm", "ocr", "controller",
                 "privacy", "scenes"}
DIGEST_KEYS = {"schema", "bundle_schema", "release_acceptance", "human_review", "manifest",
               "ocr", "members", "archive", "aggregate_sha256"}


def _regular(path: Path, maximum: int, *, private: bool = False, root_owner: bool = False):
    try:
        info = path.lstat()
    except OSError as error:
        raise c.Invalid("bundle member unavailable") from error
    owners = {0} if root_owner else {os.geteuid()}
    c.require(stat.S_ISREG(info.st_mode) and not path.is_symlink() and info.st_nlink == 1
              and info.st_uid in owners and not info.st_mode & 0o022
              and (not private or not info.st_mode & 0o077)
              and 0 < info.st_size <= maximum, "bundle member is not one bounded owned regular file")
    return info


def _directory(path: Path):
    try:
        info = path.lstat()
    except OSError as error:
        raise c.Invalid("bundle directory unavailable") from error
    c.require(stat.S_ISDIR(info.st_mode) and not path.is_symlink() and info.st_uid == os.geteuid()
              and not info.st_mode & 0o022, "bundle directory is not owned and protected")


def _write_all(fd: int, data: bytes) -> None:
    at = 0
    while at < len(data):
        written = os.write(fd, data[at:])
        c.require(written > 0, "bundle member write failed")
        at += written


def _json_bytes(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            + "\n").encode()


def _write_new(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        _write_all(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_new_json(path: Path, value) -> None:
    _write_new(path, _json_bytes(value))


def _copy_new(source: Path, target: Path) -> None:
    _regular(source, host.MAX_PNG_BYTES, private=True)
    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    target_fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                        | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        while True:
            block = os.read(source_fd, 1024 * 1024)
            if not block:
                break
            _write_all(target_fd, block)
        os.fsync(target_fd)
    finally:
        os.close(source_fd)
        os.close(target_fd)


def _read_json(path: Path, maximum: int, *, private=False):
    _regular(path, maximum, private=private)
    try:
        return c.strict_json(path.read_bytes())
    except OSError as error:
        raise c.Invalid("bundle member read failed") from error


def read_private_fragments(path):
    if path is None:
        return ()
    value = Path(path)
    _regular(value, 64 * 1024, private=True)
    try:
        fragments = tuple(line for line in value.read_text(encoding="utf-8").splitlines() if line)
    except (OSError, UnicodeError) as error:
        raise c.Invalid("private fragment file invalid") from error
    c.require(fragments and all(len(item) >= 12 for item in fragments),
              "private fragment file invalid")
    return fragments


def approved_ocr_identity():
    """Measure the single reviewed OCR implementation and its language data."""
    executable = Path(c.OCR_IDENTITY["path"])
    info = _regular(executable, 100 * 1024 * 1024, root_owner=True)
    c.require(info.st_mode & 0o111 and os.access(executable, os.X_OK), "approved OCR unavailable")
    measured = {"path": str(executable), "bytes": info.st_size, "sha256": c.sha256(executable)}
    try:
        version = subprocess.run([str(executable), "--version"], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15,
                                 check=False, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
        languages = subprocess.run([str(executable), "--list-langs"], stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15,
                                   check=False, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
    except (OSError, subprocess.TimeoutExpired) as error:
        raise c.Invalid("approved OCR identity unavailable") from error
    c.require(version.returncode == languages.returncode == 0, "approved OCR identity unavailable")
    try:
        measured["version"] = version.stdout.decode("utf-8", "strict").splitlines()[0]
        language_lines = languages.stdout.decode("utf-8", "strict").splitlines()
    except (UnicodeError, IndexError) as error:
        raise c.Invalid("approved OCR identity invalid") from error
    measured["languages"] = sorted(line.strip() for line in language_lines[1:] if line.strip())
    measured["traineddata"] = {}
    for language, expected in c.OCR_IDENTITY["traineddata"].items():
        path = Path(expected["path"])
        language_info = _regular(path, 64 * 1024 * 1024, root_owner=True)
        measured["traineddata"][language] = {"path": str(path), "bytes": language_info.st_size,
                                                "sha256": c.sha256(path)}
    measured["invocation"] = list(c.OCR_IDENTITY["invocation"])
    measured["shell_focus_invocation"] = list(c.OCR_IDENTITY["shell_focus_invocation"])
    measured["controller_invocation"] = list(c.OCR_IDENTITY["controller_invocation"])
    c.ocr_identity(measured)
    return measured


def tesseract_ocr(path: Path, timeout: int) -> str:
    approved_ocr_identity()
    executable = Path(c.OCR_IDENTITY["path"])
    try:
        result = subprocess.run([str(executable), str(path), *c.OCR_IDENTITY["invocation"]],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=timeout, check=False,
                                env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
    except (OSError, subprocess.TimeoutExpired) as error:
        raise c.Invalid("capture OCR failed") from error
    c.require(result.returncode == 0 and len(result.stdout) <= 256_000, "capture OCR failed")
    try:
        return result.stdout.decode("utf-8", "strict")
    except UnicodeError as error:
        raise c.Invalid("capture OCR output invalid") from error


def tesseract_shell_focus_ocr(path: Path, timeout: int) -> str:
    """Read only the private normalized shell block with its pinned PSM."""
    approved_ocr_identity()
    executable = Path(c.OCR_IDENTITY["path"])
    try:
        result = subprocess.run(
            [str(executable), str(path), *c.OCR_IDENTITY["shell_focus_invocation"]],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=timeout, check=False, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
    except (OSError, subprocess.TimeoutExpired) as error:
        raise c.Invalid("capture shell focus OCR failed") from error
    c.require(result.returncode == 0 and len(result.stdout) <= 256_000,
              "capture shell focus OCR failed")
    try:
        return result.stdout.decode("utf-8", "strict")
    except UnicodeError as error:
        raise c.Invalid("capture shell focus OCR output invalid") from error


def _inventory(root: Path):
    members = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        info = _regular(path, host.MAX_PNG_BYTES if relative.endswith(".png") else 256_000)
        members[relative] = {"bytes": info.st_size, "sha256": c.sha256(path)}
    return members


def _archive(root: Path, target: Path):
    c.require(not target.exists() and not target.is_symlink(), "refusing to replace capture archive")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(os.dup(fd), "wb") as stream, tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for name in ("captures", "receipts"):
                info = tarfile.TarInfo(name)
                info.type, info.mode, info.uid, info.gid, info.mtime = tarfile.DIRTYPE, 0o700, 0, 0, 0
                archive.addfile(info)
            for path in sorted(item for item in root.rglob("*") if item.is_file()):
                data = path.read_bytes()
                info = tarfile.TarInfo(path.relative_to(root).as_posix())
                info.size, info.mode, info.uid, info.gid, info.mtime = len(data), 0o600, 0, 0, 0
                archive.addfile(info, io.BytesIO(data))
        os.fsync(fd)
    finally:
        os.close(fd)
    info = _regular(target, 128 * 1024 * 1024, private=True)
    return {"name": target.name, "format": "ustar", "bytes": info.st_size,
            "sha256": c.sha256(target)}


def _digest_contract(root: Path, archive_record):
    members = _inventory(root)
    manifest = members[BUNDLE_NAME]
    core = {"manifest": manifest, "ocr": c.OCR_IDENTITY,
            "members": members, "archive": archive_record}
    return {"schema": "arctic-showcase-exact-capture-digest-v1",
            "bundle_schema": "arctic-showcase-exact-capture-bundle-v1",
            "release_acceptance": False, "human_review": "pending", **core,
            "aggregate_sha256": c.json_hash(core)}


def export(capture_root: Path, receipts, destination: Path, archive_path: Path, digest_path: Path,
           ocr_timeout=60, private_fragments=()):
    """Copy normalized pixels and exact receipts to a new, pinned transport."""
    c.require(type(receipts) is list and len(receipts) == len(c.SCENES),
              "bundle needs exactly three receipts")
    by_scene = {}
    for receipt in receipts:
        c.receipt(receipt)
        c.require(receipt["scene"] not in by_scene, "duplicate bundle scene")
        by_scene[receipt["scene"]] = receipt
    c.require(set(by_scene) == set(c.SCENES), "bundle scenes differ")
    first = by_scene[c.SCENES[0]]
    c.require(all(value["image"] == first["image"] and value["execution"] == first["execution"]
                  and value["vm"] == first["vm"] and value["ocr"] == first["ocr"]
                  and value["controller"] == first["controller"]
                  for value in by_scene.values()),
              "bundle provenance differs between scenes")
    for path in (destination, archive_path, digest_path):
        c.require(not path.exists() and not path.is_symlink(), "refusing to replace capture transport")
    created = []
    try:
        destination.mkdir(mode=0o700)
        created.append(destination)
        receipts_dir, captures_dir = destination / "receipts", destination / "captures"
        receipts_dir.mkdir(mode=0o700)
        captures_dir.mkdir(mode=0o700)
        scenes = {}
        for scene in c.SCENES:
            receipt = by_scene[scene]
            source = capture_root / receipt["output"]["path"]
            output_path = captures_dir / f"{scene}.png"
            _copy_new(source, output_path)
            c.require(c.sha256(output_path) == receipt["output"]["sha256"],
                      "normalized capture changed during export")
            receipt_path = receipts_dir / f"{scene}.json"
            _write_new_json(receipt_path, receipt)
            scenes[scene] = {"receipt": f"receipts/{scene}.json",
                             "receipt_bytes": receipt_path.stat().st_size,
                             "receipt_sha256": c.sha256(receipt_path),
                             "output": f"captures/{scene}.png",
                             "repository_target": c.OUTPUTS[scene],
                             "bytes": receipt["output"]["bytes"],
                             "sha256": receipt["output"]["sha256"]}
        manifest = {"schema": "arctic-showcase-exact-capture-bundle-v1",
                    "status": "captured_unreviewed", "release_acceptance": False,
                    "image": first["image"], "execution": first["execution"], "vm": first["vm"],
                    "ocr": first["ocr"], "controller": first["controller"],
                    "privacy": {"automated": "passed_and_rechecked_after_export",
                                "human": "pending"}, "scenes": scenes}
        _write_new_json(destination / BUNDLE_NAME, manifest)
        created.append(archive_path)
        archive_record = _archive(destination, archive_path)
        digest = _digest_contract(destination, archive_record)
        created.append(digest_path)
        _write_new_json(digest_path, digest)
        validate(destination, digest, archive_path, ocr_timeout, private_fragments)
        return manifest, digest
    except BaseException:
        for path in reversed(created):
            try:
                shutil.rmtree(path) if path.is_dir() and not path.is_symlink() else path.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def _validate_digest_contract(value, root: Path, archive_path: Path):
    c.require(type(value) is dict and set(value) == DIGEST_KEYS
              and value["schema"] == "arctic-showcase-exact-capture-digest-v1"
              and value["bundle_schema"] == "arctic-showcase-exact-capture-bundle-v1"
              and value["release_acceptance"] is False and value["human_review"] == "pending",
              "transport digest contract differs")
    c.ocr_identity(value["ocr"])
    members = _inventory(root)
    archive = value["archive"]
    c.require(type(archive) is dict and set(archive) == {"name", "format", "bytes", "sha256"}
              and archive["name"] == archive_path.name and archive["format"] == "ustar"
              and type(archive["bytes"]) is int and 0 < archive["bytes"] <= 128 * 1024 * 1024
              and c.fullmatch(c.HEX64, archive["sha256"]), "archive digest record differs")
    archive_info = _regular(archive_path, 128 * 1024 * 1024, private=True)
    c.require(archive_info.st_size == archive["bytes"] and c.sha256(archive_path) == archive["sha256"],
              "capture archive bytes differ")
    c.require(value["members"] == members and value["manifest"] == members[BUNDLE_NAME],
              "bundle member digest inventory differs")
    core = {"manifest": value["manifest"], "ocr": value["ocr"],
            "members": value["members"], "archive": archive}
    c.require(c.fullmatch(c.HEX64, value["aggregate_sha256"])
              and c.json_hash(core) == value["aggregate_sha256"],
              "transport aggregate digest differs")


def validate(root: Path, digest_contract, archive_path: Path, ocr_timeout=60, private_fragments=()):
    """Validate every byte, receipt field, privacy gate and transport digest."""
    measured_ocr = approved_ocr_identity()
    _directory(root)
    root = root.resolve(strict=True)
    _directory(root)
    c.require({path.name for path in root.iterdir()} == {BUNDLE_NAME, "receipts", "captures"},
              "bundle top-level members differ")
    receipts_dir, captures_dir = root / "receipts", root / "captures"
    _directory(receipts_dir)
    _directory(captures_dir)
    expected_json = {f"{scene}.json" for scene in c.SCENES}
    expected_png = {f"{scene}.png" for scene in c.SCENES}
    c.require({path.name for path in receipts_dir.iterdir()} == expected_json
              and {path.name for path in captures_dir.iterdir()} == expected_png,
              "bundle scene members differ")
    _validate_digest_contract(digest_contract, root, archive_path)
    manifest = _read_json(root / BUNDLE_NAME, 256_000)
    c.require(type(manifest) is dict and set(manifest) == MANIFEST_KEYS
              and manifest["schema"] == "arctic-showcase-exact-capture-bundle-v1"
              and manifest["status"] == "captured_unreviewed"
              and manifest["release_acceptance"] is False
              and manifest["privacy"] == {"automated": "passed_and_rechecked_after_export",
                                           "human": "pending"}, "bundle manifest identity differs")
    c.image_identity(manifest["image"])
    c.execution(manifest["execution"])
    c.vm_provenance(manifest["vm"])
    c.ocr_identity(manifest["ocr"])
    c.controller_trace(manifest["controller"])
    c.require(manifest["ocr"] == measured_ocr, "transport OCR differs from approved identity")
    c.require(type(manifest["scenes"]) is dict and set(manifest["scenes"]) == set(c.SCENES),
              "bundle manifest scenes differ")
    receipts = []
    for scene in c.SCENES:
        entry = manifest["scenes"][scene]
        receipt_name, output_name = f"receipts/{scene}.json", f"captures/{scene}.png"
        c.require(type(entry) is dict and set(entry) == {"receipt", "receipt_bytes",
                  "receipt_sha256", "output", "repository_target", "bytes", "sha256"}
                  and entry["receipt"] == receipt_name and entry["output"] == output_name
                  and entry["repository_target"] == c.OUTPUTS[scene]
                  and type(entry["receipt_bytes"]) is int and 0 < entry["receipt_bytes"] <= 256_000
                  and c.fullmatch(c.HEX64, entry["receipt_sha256"])
                  and type(entry["bytes"]) is int and 0 < entry["bytes"] <= host.MAX_PNG_BYTES
                  and c.fullmatch(c.HEX64, entry["sha256"]), "bundle scene entry differs")
        receipt_path = root / receipt_name
        receipt_info = _regular(receipt_path, 256_000)
        c.require(receipt_info.st_size == entry["receipt_bytes"]
                  and c.sha256(receipt_path) == entry["receipt_sha256"],
                  "bundle receipt bytes differ")
        receipt = _read_json(receipt_path, 256_000)
        c.receipt(receipt)
        c.require(receipt["scene"] == scene and receipt["image"] == manifest["image"]
                  and receipt["execution"] == manifest["execution"] and receipt["vm"] == manifest["vm"]
                  and receipt["ocr"] == manifest["ocr"]
                  and receipt["controller"] == manifest["controller"]
                  and receipt["output"]["bytes"] == entry["bytes"]
                  and receipt["output"]["sha256"] == entry["sha256"],
                  "bundle receipt binding differs")
        output_path = root / output_name
        info = _regular(output_path, host.MAX_PNG_BYTES)
        c.require(info.st_size == entry["bytes"] and c.sha256(output_path) == entry["sha256"],
                  "bundle output bytes differ")
        host._strict_png(output_path)
        try:
            with Image.open(output_path) as image:
                c.require(image.mode == "RGB" and image.size == (1280, 800) and image.info == {},
                          "bundle output image differs")
                image.load()
                pixel_sha256 = hashlib.sha256(image.tobytes()).hexdigest()
        except (OSError, ValueError) as error:
            raise c.Invalid("bundle output decode failed") from error
        c.require(pixel_sha256 == receipt["output"]["pixel_sha256"],
                  "bundle output pixels differ")
        c.privacy_text(tesseract_ocr(output_path, ocr_timeout), private_fragments)
        receipts.append(receipt)
    return manifest, receipts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("digest_contract", type=Path)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--expected-contract-sha256", required=True)
    parser.add_argument("--private-fragments", type=Path)
    parser.add_argument("--ocr-timeout", type=int, default=60)
    args = parser.parse_args(argv)
    try:
        c.require(1 <= args.ocr_timeout <= 300, "OCR timeout invalid")
        _regular(args.digest_contract, 256_000, private=True)
        c.require(c.fullmatch(c.HEX64, args.expected_contract_sha256)
                  and c.sha256(args.digest_contract) == args.expected_contract_sha256,
                  "external digest contract pin differs")
        digest = _read_json(args.digest_contract, 256_000, private=True)
        fragments = read_private_fragments(args.private_fragments)
        manifest, _ = validate(args.bundle, digest, args.archive, args.ocr_timeout, fragments)
    except (c.Invalid, OSError) as error:
        print(f"capture bundle invalid: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "schema": manifest["schema"], "status": manifest["status"],
                      "release_acceptance": False, "human_review": "pending",
                      "digest_contract_sha256": args.expected_contract_sha256},
                     sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
