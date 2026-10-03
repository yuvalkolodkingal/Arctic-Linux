#!/usr/bin/env python3
"""Fetch a pinned GitHub release ISO (including split assets), verify its SHA-256."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def fetch(repo, tag, dest):
    if tag.lower() == 'latest' or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]*', tag):
        raise ValueError('an explicit release tag is required')
    assets = json.loads(subprocess.check_output(
        ['gh', 'release', 'view', tag, '--repo', repo, '--json', 'assets'], text=True))['assets']
    names = [a['name'] for a in assets]
    sums = [n for n in names if re.fullmatch(r'Arctic-Linux-[0-9.]+-x86_64\.iso\.sha256', n)]
    if len(sums) != 1:
        raise ValueError('expected exactly one Arctic ISO checksum')
    checksum = sums[0]
    iso = checksum[:-7]
    parts = sorted(n for n in names if re.fullmatch(re.escape(iso) + r'\.part[0-9]{2}', n))
    downloads = [iso] if iso in names else parts
    if not downloads or (iso not in names and parts != [f'{iso}.part{i:02}' for i in range(len(parts))]):
        raise ValueError('missing ISO or non-contiguous split parts')
    dest.mkdir(parents=True, exist_ok=False)
    for name in [checksum] + downloads:
        subprocess.run(['gh', 'release', 'download', tag, '--repo', repo,
                        '--pattern', name, '--dir', str(dest)], check=True)
    if iso not in names:
        with (dest / iso).open('wb') as out:
            for part in parts:
                with (dest / part).open('rb') as src:
                    while chunk := src.read(1024 * 1024):
                        out.write(chunk)
                (dest / part).unlink()
    fields = (dest / checksum).read_text().strip().split()
    if len(fields) != 2 or fields[1].lstrip('*') != iso or not re.fullmatch('[0-9a-fA-F]{64}', fields[0]):
        raise ValueError('invalid checksum record')
    with (dest / iso).open('rb') as src:
        digest = hashlib.file_digest(src, 'sha256').hexdigest()
    if digest != fields[0].lower():
        raise ValueError('ISO checksum mismatch')
    (dest / 'provenance.json').write_text(json.dumps(dict(repo=repo, tag=tag, iso=iso, sha256=digest), indent=2))
    print(dest / iso)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('tag')
    p.add_argument('destination', type=Path)
    p.add_argument('--repo', default='yuvalkolodkingal/Arctic-Linux')
    a = p.parse_args()
    fetch(a.repo, a.tag, a.destination)
