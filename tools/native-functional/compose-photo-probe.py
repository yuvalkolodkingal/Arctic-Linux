#!/usr/bin/env python3
"""Embed the existing photo verifier and the image source's pinned collection."""
import argparse
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET

import apps


def compose(source, output, context=None, execution=None):
    library = (source / 'tools/reliability/guest.py').read_text()
    expected = (source / 'design/backgrounds/collection.json').read_bytes()
    sha = hashlib.sha256(expected).hexdigest()
    supplement = ''
    if context is not None:
        execution = execution or Path(__file__).resolve().parents[2]
        app_source = (execution / 'tools/native-functional/apps.py').read_text()
        native_source = (execution / 'tools/native-functional/native_smoke.py').read_text()
        mime_source = (source / 'packaging/desktop/live-mimeapps.list').read_bytes()
        manifest = (source / 'iso/kiwi/config.kiwi').read_bytes()
        names = {item.attrib['name'] for item in ET.fromstring(manifest).iter('package')}
        apps.require(set(apps.PACKAGES) - {'bash'} <= names, 'Image manifest requested applications differ')
        context = dict(context, checker_sha256=hashlib.sha256(app_source.encode()).hexdigest(),
                       native_sha256=hashlib.sha256(native_source.encode()).hexdigest(),
                       manifest_sha256=hashlib.sha256(manifest).hexdigest(),
                       mimeapps_sha256=hashlib.sha256(mime_source).hexdigest())
        apps.context_check(context)
        mimes = apps.mime_defaults(mime_source)
        supplement = ('app_library={"__name__":"arctic_app_library","__file__":__file__}\n' +
            f'exec(compile({app_source!r},__file__,"exec"),app_library)\n' +
            'native_library={"__name__":"arctic_native_discovery","__file__":__file__}\n' +
            f'exec(compile({native_source!r},__file__,"exec"),native_library)\n' +
            'try:\n' +
            f'    app_record=app_library["probe"](native_library["discover_desktop"](),stage,{context!r},{mimes!r})\n' +
            'except Exception as error:\n' +
            f'    app_record=dict(schema="arctic-native-app-defaults-v1",stage=stage,status="failed",release_acceptance=False,context={context!r},error=type(error).__name__+": "+str(error))\n' +
            'print("ARCTIC-NATIVE-APP-DEFAULTS "+json.dumps(app_record),flush=True)\n' +
            'if app_record["status"] != "passed":\n'
            '    raise SystemExit(1)\n')
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
        'print("ARCTIC-NATIVE-PHOTOS "+json.dumps(record),flush=True)\n' +
        supplement +
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
