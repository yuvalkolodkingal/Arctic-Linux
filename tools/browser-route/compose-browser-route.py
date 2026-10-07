#!/usr/bin/env python3
"""Compose pinned historical functions plus a declared native-argv-only addon."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'precision-feasibility'
PRIOR_COMPOSER_SHA = '9586d5b32b5cd5a9c9ac563747604b68c08c3f26441437bfb863712c8240af7a'
DUAL_SHA = '9fd12277dda3e9f40775646046a8f687c5100343e7e8d360febc0983de1ff059'
BASE_GUEST_SHA = '767ce65341ca1a2ddac397f9a8d04fe9804e424e21a519a6b076e24f4e97cf3b'


def components(guest,dual,addon):
    path = PRIOR/'compose-feasibility.py'
    if (hashlib.sha256(path.read_bytes()).hexdigest() != PRIOR_COMPOSER_SHA
            or hashlib.sha256(guest.encode()).hexdigest() != BASE_GUEST_SHA
            or hashlib.sha256(dual.encode()).hexdigest() != DUAL_SHA):
        raise ValueError('Frozen guest/observer/composer differs')
    spec=importlib.util.spec_from_file_location('frozen_route_composer',path)
    composer=importlib.util.module_from_spec(spec);spec.loader.exec_module(composer)
    callback,prior_identity,parts=composer.components(guest,dual)
    identity=hashlib.sha256(guest.encode()+b'\0'+dual.encode()+b'\0'+callback.encode()+b'\0'+addon.encode()).hexdigest()
    parts=dict(parts,browser_route_addon_sha256=hashlib.sha256(addon.encode()).hexdigest(),
        frozen_observer_identity=prior_identity,scope='browser-native-argv-diagnostic-only')
    return callback,identity,parts


def compose(guest,dual,addon):
    callback,identity,parts=components(guest,dual,addon)
    return ('#!/usr/bin/env python3\nimport sys\n'
        'if len(sys.argv)!=2 or sys.argv[1] not in ("live","installed"):\n'
        '    raise SystemExit("Exact disposable harness stage required")\n'
        'measurement={"__name__":"arctic_browser_native_argv","__file__":__file__}\n'
        f'exec(compile({guest!r},__file__,"exec"),measurement)\n'
        f'exec(compile({dual!r},__file__,"exec"),measurement)\n'
        f'exec(compile({callback!r},__file__,"exec"),measurement)\n'
        f'exec(compile({addon!r},__file__,"exec"),measurement)\n'
        'if sys.argv[1]=="installed":\n'
        '    measurement["install_dual_observer"]()\n'
        f'    measurement["emit"]("observer_source_sha256",{identity!r})\n'
        f'    measurement["emit"]("observer_implementation",{parts!r})\n'
        '    measurement["install_browser_route"]()\n'
        '    measurement["main"](preconditioned=True)\n'
        'else:\n'
        '    print("ARCTIC-BROWSER-ROUTE-NO-LIVE-APP-LAUNCH",flush=True)\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--identity-out',type=Path,required=True)
    args=parser.parse_args()
    guest=(HERE.parent/'performance/guest.py').read_text()
    dual=(PRIOR/'dual-observer.py').read_text()
    addon=(HERE/'browser-route-addon.py').read_text()
    source=compose(guest,dual,addon)
    _,identity,parts=components(guest,dual,addon)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(source)
    args.identity_out.write_text(json.dumps(dict(observer_source_sha256=identity,components=parts,
        frozen_probe_sha256=hashlib.sha256(source.encode()).hexdigest()),indent=2)+'\n')


if __name__=='__main__':main()
