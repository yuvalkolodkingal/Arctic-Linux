#!/usr/bin/env python3
"""Copy only bounded, owned synthetic VM diagnostics, screening text for uploads."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile

TEXT = {'.json', '.log', '.txt', '.tsv'}
BINARY = {'.png', '.rgb', '.wav'}
SENSITIVE = re.compile(r'(?i)(?:gh[pousr]_|github_pat_)[a-z0-9_]+'
                       r'|AKIA[A-Z0-9]{16}|authorization:\s*\S+(?:\s+\S+)?'
                       r'|[\w.+-]+@[\w.-]+\.[a-z]{2,}'
                       r'|https?://[^\s"<>]*\?[^\s"<>]*')


def copy_screened(source, target):
    files = sorted(source.rglob('*'))
    if len(files) > 1000:
        raise RuntimeError('Too many diagnostic members')
    manifest = dict(scope='Owned synthetic QEMU VM only; no host desktop, VM disks or credentials', files={})
    total = 0
    for path in files:
        if path.is_symlink():
            raise RuntimeError('Diagnostic symlinks are forbidden')
        if path.is_dir():
            continue
        if not path.is_file():
            raise RuntimeError('Diagnostic members must be regular files')
        if path.suffix not in TEXT | BINARY and not path.name.endswith('.bounded-prefix.bin'):
            raise RuntimeError('Unexpected diagnostic file type: ' + path.name)
        size = path.stat().st_size
        total += size
        if size > 128 * 1024 * 1024 or total > 512 * 1024 * 1024:
            raise RuntimeError('Diagnostic byte bounds exceeded')
        content = path.read_bytes()
        original = hashlib.sha256(content).hexdigest()
        redactions = 0
        if path.suffix in TEXT:
            value, redactions = SENSITIVE.subn('[redacted]', content.decode('utf-8'))
            content = value.encode()
        relative = path.relative_to(source)
        output = target / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(content)
        manifest['files'][relative.as_posix()] = dict(original_sha256=original,
                uploaded_sha256=hashlib.sha256(content).hexdigest(), bytes=len(content), redactions=redactions)
    (target / 'upload-screening.json').write_text(json.dumps(manifest, indent=2) + '\n')


def screen(source, target):
    if not source.exists():
        return
    if source.is_symlink() or not source.is_dir() or target.exists():
        raise RuntimeError('Diagnostics must be an owned directory and upload path unused')
    # No partial directory is published if any screening or bounds check fails.
    with tempfile.TemporaryDirectory(prefix='arctic-screening-', dir=target.parent) as staging:
        stage = Path(staging)
        copy_screened(source, stage)
        stage.rename(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    screen(args.source, args.out)


if __name__ == '__main__':
    main()
