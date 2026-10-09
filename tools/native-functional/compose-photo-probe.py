#!/usr/bin/env python3
"""Embed the existing photo verifier and the image source's pinned collection."""
import argparse
import hashlib
from pathlib import Path


def compose(source, output):
    library = (source / 'tools/reliability/guest.py').read_text()
    expected = (source / 'design/backgrounds/collection.json').read_bytes()
    sha = hashlib.sha256(expected).hexdigest()
    output.write_text('#!/usr/bin/env python3\n' +
        'import json,os,sys,subprocess\nfrom pathlib import Path\n' +
        'if Path(__file__).parent != Path("/run/t") or os.geteuid() != 0 or '
        'subprocess.check_output(["systemd-detect-virt", "--vm"],text=True).strip() not in ("qemu","kvm"):\n'
        '    raise RuntimeError("Requires root in the owned QEMU test guest")\n'
        'if subprocess.check_output(["getenforce"],text=True).strip() != "Enforcing":\n'
        '    raise RuntimeError("Requires enforcing guest SELinux")\n'
        'stage=sys.argv[1]\n'
        'if stage not in ("live","installed") or ("rd.live.image" in Path("/proc/cmdline").read_text().split()) != (stage=="live"):\n'
        '    raise RuntimeError("Photo probe medium/stage differs")\n'
        'library={"__name__":"arctic_photo_library","__file__":__file__}\n' +
        f'exec(compile({library!r},__file__,"exec"),library)\n' +
        f'expected=json.loads({expected.decode()!r})\n' +
        f'record=dict(stage=stage,collection_sha256={sha!r},revision=expected["revision"],release_acceptance=False)\n' +
        'try:\n'
        '    record.update(status="passed",detail=library["wallpapers"](library["desktop"](),expected))\n'
        'except Exception as error:\n'
        '    record.update(status="failed",detail=str(error))\n'
        'print("ARCTIC-NATIVE-PHOTOS "+json.dumps(record),flush=True)\n'
        'raise SystemExit(0 if record["status"]=="passed" else 1)\n')
    return sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    compose(args.source, args.output)


if __name__ == '__main__':
    main()
