#!/usr/bin/env python3
"""Disabled entry point for exact BIOS failure-only encrypted private review."""
import argparse,hashlib,subprocess,sys
from pathlib import Path
import common as C
HERE=Path(__file__).resolve().parent
def main_adapter(value,prior_root,age_binary,sealed_out):
    C.manifest(value)
    for path,expected in value['execution_files'].items():
        C.require(C.digest_file(C.ROOT/path)==expected,'Private review runtime pin differs')
    helper=C.load(HERE/'composition.py','private_review_composition',
        value['execution_files']['tools/final-bios-private-record-review/composition.py'])
    def source_loader(path,expected):
        raw=C.regular(path,1024*1024)
        C.require(hashlib.sha256(raw).hexdigest()==expected,'Private review Source buffer differs')
        return raw
    prior_root=Path(prior_root).resolve();binding=value['private_review_binding']
    def git(*args):
        return subprocess.run(['git','-C',str(prior_root),*args],stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=True,timeout=10).stdout.decode('ascii').strip()
    C.require(git('rev-parse','HEAD')==binding['prior_execution_commit']
        and git('rev-parse','HEAD^{tree}')==binding['prior_execution_tree'],
        'Private review prior execution checkout differs')
    def prior_loader(path,expected):
        raw=C.regular(path,1024*1024)
        C.require(hashlib.sha256(raw).hexdigest()==expected,'Private review prior Source buffer differs')
        return raw
    return helper.build(C.ROOT,value,source_loader,prior_root,prior_loader,C.guard,
        Path(age_binary),Path(sealed_out))
def main():
    value=C.manifest(C.strict_json(C.regular(HERE/'execution-manifest.json',1024*1024)),True)
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',required=True);parser.add_argument('--inputs',required=True)
    parser.add_argument('--prior-execution',required=True)
    parser.add_argument('--out',required=True);parser.add_argument('--age-binary',required=True)
    parser.add_argument('--sealed-out',required=True)
    args=parser.parse_args()
    private,*_=main_adapter(value,args.prior_execution,args.age_binary,args.sealed_out)
    saved=sys.argv
    try:
        sys.argv=[saved[0],'--source',args.source,'--inputs',args.inputs,'--out',args.out]
        return private()
    finally:sys.argv=saved
if __name__=='__main__':raise SystemExit(main())
