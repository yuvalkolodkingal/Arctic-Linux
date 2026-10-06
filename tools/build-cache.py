#!/usr/bin/env python3
"""Key a trusted builder's Go cache by image and native RPM inventory.

Go validates source, compiler and flag changes itself. It does not detect changed
C libraries, so the image identity and native RPM NEVRAs fence cgo reuse.
This caches compilation only: RPM assembly, %check and signing still run.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


def manifest(image_id, inventory):
    if not re.fullmatch(r'(?:sha256:)?[0-9a-f]{64}', image_id):
        raise ValueError('Expected a resolved container image SHA-256 identity')
    native = []
    for line in inventory.splitlines():
        if not line.strip():
            continue
        fields = line.split('\t')
        if len(fields) != 2 or not all(fields):
            raise ValueError('Expected NAME<TAB>NEVRA RPM inventory')
        name, nevra = fields
        # Mango is an executable used by %check, not a library linked by Go.
        # Keep every other RPM: even a future project-native library must fence cgo.
        if name == 'mangowm':
            continue
        native.append(nevra)
    if not native:
        raise ValueError('Empty native RPM inventory; refusing persistent compiler reuse')
    inputs = dict(schema=1, image_id=image_id.removeprefix('sha256:'),
                  native_rpms=sorted(set(native)))
    key = hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return dict(inputs, cache_key=key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image-id', required=True)
    parser.add_argument('--manifest', type=Path)
    args = parser.parse_args()
    data = manifest(args.image_id, sys.stdin.read())
    if args.manifest:
        args.manifest.write_text(json.dumps(data, indent=2)+'\n')
    print(data['cache_key'])


if __name__ == '__main__':
    main()
