"""Fail-closed retrieval for immutable showcase build assets."""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable


def _matches(payload: bytes, expected_bytes: int, expected_sha256: str) -> bool:
    return (
        len(payload) == expected_bytes
        and hashlib.sha256(payload).hexdigest() == expected_sha256
    )


def _read_bounded(path: Path, expected_bytes: int) -> bytes:
    with path.open("rb") as source:
        return source.read(expected_bytes + 1)


def ensure_exact_asset(
    path: Path,
    *,
    url: str,
    expected_bytes: int,
    expected_sha256: str,
    opener: Callable[..., object] = urllib.request.urlopen,
) -> str:
    """Reuse or fetch one regular file only when its exact bytes match the pin."""
    if expected_bytes <= 0 or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("asset integrity pin is invalid")
    if path.is_symlink():
        raise ValueError(f"refusing symlinked build asset: {path}")
    if path.is_file() and _matches(_read_bounded(path, expected_bytes), expected_bytes, expected_sha256):
        return "verified-existing"

    with opener(url, timeout=30) as response:
        payload = response.read(expected_bytes + 1)
    if not _matches(payload, expected_bytes, expected_sha256):
        raise ValueError(f"downloaded build asset differs from its immutable pin: {url}")

    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", delete=False) as output:
        temporary = Path(output.name)
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())
    try:
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    if path.is_symlink() or not _matches(_read_bounded(path, expected_bytes), expected_bytes, expected_sha256):
        raise ValueError(f"installed build asset differs from its immutable pin: {path}")
    return "verified-download"
