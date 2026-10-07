#!/usr/bin/env python3
"""Compose a dedicated diagnostic without changing the original guest source."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

BASE_GUEST_SHA='767ce65341ca1a2ddac397f9a8d04fe9804e424e21a519a6b076e24f4e97cf3b'
HERE=Path(__file__).resolve().parent


def components(guest,dual):
    if hashlib.sha256(guest.encode()).hexdigest()!=BASE_GUEST_SHA:
        raise ValueError('Original frozen performance guest differs')
    tree=ast.parse(guest)
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='verify_role_payload_after_first_gui')
    callback=ast.get_source_segment(guest,node)
    old="bound['first_present_query']['worker_received_ns']"
    if callback.count(old)!=1:
        raise ValueError('Integrity callback upper endpoint differs')
    callback=callback.replace('def verify_role_payload_after_first_gui(',
        'def dual_verify_role_payload_after_first_gui(',1).replace(old,"bound['selected_upper_ns']",1)
    identity=hashlib.sha256(guest.encode()+b'\0'+dual.encode()+b'\0'+callback.encode()).hexdigest()
    parts=dict(base_guest_sha256=BASE_GUEST_SHA,dual_observer_sha256=hashlib.sha256(dual.encode()).hexdigest(),
               integrity_callback_sha256=hashlib.sha256(callback.encode()).hexdigest(),
               observer='mango-dual-stream-worker-v1',scope='one-pair-feasibility-only')
    return callback,identity,parts


def compose(guest,dual):
    callback,identity,parts=components(guest,dual)
    return ('#!/usr/bin/env python3\nimport sys\n'
        'measurement={"__name__":"arctic_precision_feasibility","__file__":__file__}\n'
        f'exec(compile({guest!r},__file__,"exec"),measurement)\n'
        f'exec(compile({dual!r},__file__,"exec"),measurement)\n'
        f'exec(compile({callback!r},__file__,"exec"),measurement)\n'
        'if sys.argv[1]=="installed":\n'
        '    measurement["install_dual_observer"]()\n'
        f'    measurement["emit"]("observer_source_sha256",{identity!r})\n'
        f'    measurement["emit"]("observer_implementation",{parts!r})\n'
        '    measurement["main"](preconditioned=True)\n'
        'else:\n'
        '    print("ARCTIC-PERFORMANCE-SKIPPED: live stage; diagnostic installed comparison only",flush=True)\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--guest',type=Path,default=HERE.parent/'performance/guest.py')
    parser.add_argument('--identity-out',type=Path,required=True)
    args=parser.parse_args()
    guest=args.guest.read_text();dual=(HERE/'dual-observer.py').read_text()
    source=compose(guest,dual)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(source)
    callback,identity,parts=components(guest,dual)
    args.identity_out.parent.mkdir(parents=True,exist_ok=True)
    args.identity_out.write_text(json.dumps(dict(observer_source_sha256=identity,components=parts,
        frozen_probe_sha256=hashlib.sha256(source.encode()).hexdigest()),indent=2)+'\n')


if __name__=='__main__':main()
