#!/usr/bin/env python3
"""Host-side one-use QMP capture, normalization and privacy gate."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import struct
import zlib
from pathlib import Path

import PIL
from PIL import Image

try:
    from . import contract as c
except ImportError:
    import contract as c


MAX_PNG_BYTES = 10 * 1024 * 1024


def _regular_new(path: Path, maximum: int):
    info = path.lstat()
    c.require(stat.S_ISREG(info.st_mode) and not path.is_symlink() and info.st_nlink == 1
              and info.st_uid == os.geteuid() and not info.st_mode & 0o022
              and 0 < info.st_size <= maximum, "capture is not one bounded owned regular file")
    return info


def _strict_png(path: Path):
    """Accept only a metadata-free RGB PNG stream with valid structure and CRCs."""
    data = path.read_bytes()
    c.require(8 < len(data) <= MAX_PNG_BYTES, "PNG byte length is unbounded")
    c.require(data.startswith(b"\x89PNG\r\n\x1a\n"), "capture is not PNG")
    at, state, idats = 8, "ihdr", 0
    while at < len(data):
        c.require(state != "end" and at + 12 <= len(data), "PNG chunk framing or trailing bytes differ")
        length = struct.unpack(">I", data[at:at + 4])[0]
        c.require(length <= MAX_PNG_BYTES - 12, "PNG chunk length is unbounded")
        end = at + 12 + length
        c.require(end <= len(data), "PNG chunk length exceeds file")
        kind = data[at + 4:at + 8]
        body = data[at + 8:end - 4]
        expected_crc = struct.unpack(">I", data[end - 4:end])[0]
        c.require(zlib.crc32(kind + body) & 0xffffffff == expected_crc, "PNG chunk CRC differs")
        if kind == b"IHDR":
            c.require(state == "ihdr" and at == 8 and length == 13, "PNG IHDR order or length differs")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", body)
            c.require((width, height, depth, color, compression, filtering, interlace)
                      == (1280, 800, 8, 2, 0, 0, 0), "PNG IHDR differs")
            state = "idat"
        elif kind == b"IDAT":
            c.require(state == "idat" and length > 0, "PNG IDAT order or length differs")
            idats += 1
        elif kind == b"IEND":
            c.require(state == "idat" and idats > 0 and length == 0, "PNG IEND order or length differs")
            state = "end"
        else:
            raise c.Invalid("PNG contains an unapproved chunk")
        at = end
    c.require(state == "end" and at == len(data), "PNG is incomplete or has trailing bytes")


def _decode(path: Path):
    _strict_png(path)
    try:
        with Image.open(path) as image:
            c.require(image.format == "PNG" and image.mode == "RGB" and image.size == (1280, 800),
                      "capture dimensions, mode or format differ")
            c.require(image.info == {}, "capture PNG contains unreviewed metadata")
            image.load()
            return image.copy()
    except (OSError, ValueError) as error:
        raise c.Invalid("capture PNG decode failed") from error


def normalize(original: Path, target: Path):
    c.require(not target.exists(), "refusing to replace normalized capture")
    image = _decode(original)
    pixels = hashlib.sha256(image.tobytes()).hexdigest()
    image.save(target, format="PNG", optimize=True)
    os.chmod(target, 0o600)
    info = _regular_new(target, MAX_PNG_BYTES)
    saved = _decode(target)
    c.require(hashlib.sha256(saved.tobytes()).hexdigest() == pixels,
              "normalization changed pixels")
    return {"path": target.name, "bytes": info.st_size, "sha256": c.sha256(target),
            "pixel_sha256": pixels, "format": "PNG", "width": 1280, "height": 800,
            "transformation": "Pillow RGB lossless PNG re-encode; metadata stripped; no crop/resize/redaction",
            "pillow_version": PIL.__version__}


class Capture:
    """A host object consumes each scene marker once and never marks human review passed."""

    def __init__(self, root: Path, execution, vm_provenance, ocr_identity,
                 qmp_screendump, ocr,
                 private_fragments=()):
        self.root = root.resolve()
        c.execution(execution)
        c.vm_provenance(vm_provenance)
        c.ocr_identity(ocr_identity)
        self.execution = dict(execution)
        self.vm_provenance = dict(vm_provenance)
        self.ocr_identity = dict(ocr_identity)
        self.qmp_screendump = qmp_screendump
        self.ocr = ocr
        self.private_fragments = tuple(private_fragments)
        self.seen_nonces = set()
        self.seen_scenes = set()

    def _private_root(self):
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        info = self.root.lstat()
        c.require(stat.S_ISDIR(info.st_mode) and not self.root.is_symlink()
                  and info.st_uid == os.geteuid() and not info.st_mode & 0o077,
                  "capture directory is not private and owned")

    @staticmethod
    def _discard(*paths):
        failed = False
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                failed = True
        c.require(not failed, "private capture cleanup failed")

    def consume(self, line: str, expected_scene: str):
        c.require(type(line) is str and len(line) <= 65_536 and line.startswith(c.REQUEST_PREFIX),
                  "capture request marker missing or oversized")
        value = c.strict_json(line[len(c.REQUEST_PREFIX):])
        c.request(value)
        c.require(expected_scene in c.SCENES and value["scene"] == expected_scene,
                  "capture request scene differs from ready guest")
        scene, nonce = value["scene"], value["nonce"]
        c.require(scene not in self.seen_scenes and nonce not in self.seen_nonces,
                  "duplicate scene or nonce")
        # The request is only a bounded one-use capture trigger. Its diagnostics
        # neither authorize nor enter the acceptance receipt.
        self.seen_nonces.add(nonce)
        self._private_root()
        original = self.root / (scene + "-qmp-original.png")
        normalized = self.root / (scene + ".png")
        c.require(not original.exists() and not normalized.exists(), "capture path already exists")
        try:
            self.qmp_screendump(original)
            original_info = _regular_new(original, MAX_PNG_BYTES)
            _decode(original)
            text = self.ocr(original)
            c.privacy_text(text, self.private_fragments)
            result = normalize(original, normalized)
            c.privacy_text(self.ocr(normalized), self.private_fragments)
            original_sha = c.sha256(original)
            self._discard(original)
        except BaseException as error:
            try:
                self._discard(original, normalized)
            except BaseException:
                raise c.Invalid("private capture cleanup failed") from error
            raise
        self.seen_scenes.add(scene)
        ack = {"schema": "arctic-showcase-capture-ack-v1", "scene": scene, "nonce": nonce,
               "capture_sha256": original_sha, "release_acceptance": False}
        c.ack(ack, value)
        receipt = {"schema": "arctic-showcase-exact-capture-v1", "scene": scene,
                   "status": "captured_unreviewed", "release_acceptance": False,
                   "image": dict(c.IMAGE), "execution": self.execution,
                   "vm": self.vm_provenance, "ocr": self.ocr_identity,
                   "scene_contract": dict(c.SCENE_CONTRACTS[scene]),
                   "guest_context": {
                       "trust": "untrusted diagnostic input; excluded from this acceptance receipt",
                       "used_for_capture_gate": False, "used_for_release_acceptance": False,
                       "installed_marker": "guest-local contextual evidence only",
                   },
                   "capture": {"method": "host QMP screendump format=png for fixed reviewed scene contract",
                               "bytes": original_info.st_size,
                               "sha256": original_sha, "pixel_sha256": result["pixel_sha256"],
                               "format": "PNG", "width": 1280, "height": 800},
                   "output": result, "privacy": {"automated": "passed", "human": "pending",
                                                    "redactions": []},
                   "limitations": ["This showcase capture is not release acceptance.",
                                   "Human review of the exact normalized pixels remains pending.",
                                   "Guest facts and the installed marker are untrusted diagnostics and do not satisfy a capture or acceptance gate.",
                                   "The raw QMP PNG is omitted; only its procedural record and normalized review object remain."]}
        receipt["capture"].update(retained=False, exported=False,
            evidence_scope="procedural source record only; raw QMP PNG omitted after lossless normalization")
        return c.ACK_PREFIX + json.dumps(ack, sort_keys=True, separators=(",", ":")), receipt


def finalize_receipt(receipt, controller_trace):
    """Validate only host-derived capture evidence; guest completion is irrelevant."""
    c.require("controller" not in receipt, "controller trace already attached")
    c.controller_trace(controller_trace)
    receipt["controller"] = controller_trace
    c.receipt(receipt)
    return receipt
