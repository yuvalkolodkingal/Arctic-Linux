#!/usr/bin/env python3
"""Read-only filesystem payload inventory; bytes, hardlinks and exact duplicates.

Run on an offline image root, never on a running system's /proc or /sys.
Reports logical sizes separately from allocated blocks. Hashes only unique
inodes whose sizes are repeated, and never follows symlinks.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import stat


def inventory(root):
    seen = set()
    buckets = defaultdict(list)
    totals = defaultdict(lambda: dict(logical_bytes=0, allocated_bytes=0, files=0))
    errors = []
    largest = []
    links = 0
    paths = (Path(directory) / name
             for directory, _, names in os.walk(root, followlinks=False,
                 onerror=lambda error: errors.append(dict(path=error.filename, error=str(error))))
             for name in names)
    for path in paths:
        try:
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode):
                continue
            inode = (info.st_dev, info.st_ino)
            if inode in seen:
                links += 1
                continue
            seen.add(inode)
            rel = str(path.relative_to(root))
            for key in ('/', '/' + rel.split('/')[0], '/' + '/'.join(rel.split('/')[:3])):
                totals[key]['logical_bytes'] += info.st_size
                totals[key]['allocated_bytes'] += info.st_blocks * 512
                totals[key]['files'] += 1
            largest.append((info.st_size, '/' + rel))
            if info.st_size:
                buckets[info.st_size].append(path)
        except OSError as error:
            errors.append(dict(path=str(path), error=str(error)))
    duplicates = []
    for size, paths in buckets.items():
        if len(paths) < 2:
            continue
        digests = defaultdict(list)
        for path in paths:
            try:
                with path.open('rb') as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                digests[digest].append('/' + str(path.relative_to(root)))
            except OSError as error:
                errors.append(dict(path=str(path), error=str(error)))
        for digest, identical in digests.items():
            if len(identical) > 1:
                duplicates.append(dict(size=size, redundant_logical_bytes=size * (len(identical) - 1),
                                       sha256=digest, paths=identical))
    duplicates.sort(key=lambda row: row['redundant_logical_bytes'], reverse=True)
    return dict(root=str(root), units='bytes', unique_inodes=len(seen),
                additional_hardlink_paths=links, directories=dict(totals),
                duplicate_redundant_logical_bytes=sum(d['redundant_logical_bytes'] for d in duplicates),
                duplicate_groups=duplicates, largest_files=sorted(largest, reverse=True)[:100],
                errors=errors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if root == Path('/') or not root.is_dir():
        parser.error('root must be an offline image directory, not /')
    report = inventory(root)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in
                     ('duplicate_groups', 'largest_files', 'directories')}, indent=2))
    if report['errors']:
        raise SystemExit('Incomplete inventory: see errors in the report')


if __name__ == '__main__':
    main()
