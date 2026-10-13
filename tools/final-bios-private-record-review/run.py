#!/usr/bin/env python3
"""Disabled entry point for exact BIOS failure-only encrypted private review."""
import argparse,hashlib,json,os,stat,subprocess,sys
from pathlib import Path
import common as C
HERE=Path(__file__).resolve().parent
CLOSED_HOST_STAGE_SCHEMA='arctic-private-bios-closed-host-stage-v1'
CLOSED_HOST_STAGE_FILE='closed-host-stage.json'
CLOSED_HOST_STAGE_UNKNOWN='bios-host-stage-unknown'
CLOSED_HOST_STAGE_INITIAL='bios-host-no-reviewed-marker-present'
CLOSED_HOST_STAGE_PATHS=(
    ('bios-host-prepared-image-id-present','private/vm-prepared-image-id.txt','regular'),
    ('bios-host-workspace-directory-present','private/vm','directory'),
    ('bios-host-harness-log-created','private/harness.log','regular'),
    ('bios-host-data-staging-directory-present','private/vm/data','directory'),
    ('bios-host-sysarea-output-created','private/vm/sysarea.sh','regular'),
    ('bios-host-toolchain-output-created','private/vm/vm-toolchain.txt','regular'),
    ('bios-host-data-image-creation-started','private/vm/data.iso','regular'),
    ('bios-host-target-disk-creation-started','private/vm/target.qcow2','regular'),
    ('bios-host-qemu-launch-attempted','private/vm/qemu-install.log','regular'),
    ('bios-host-install-serial-log-created','private/vm/serial-install.log','regular'))
CLOSED_HOST_STAGE_AFTER=CLOSED_HOST_STAGE_PATHS[-1][0]
CLOSED_HOST_STAGE_LABELS=frozenset(
    {label for label,unused_path,unused_kind in CLOSED_HOST_STAGE_PATHS}
    |{CLOSED_HOST_STAGE_INITIAL,CLOSED_HOST_STAGE_UNKNOWN})

def _closed_path_kind(path):
    try:
        mode=os.lstat(path).st_mode
    except FileNotFoundError:
        return 'missing'
    except BaseException:
        return 'error'
    if stat.S_ISREG(mode):return 'regular'
    if stat.S_ISDIR(mode):return 'directory'
    return 'invalid'

def closed_host_stage(out):
    """Return only the latest finite fixed-path presence state; never inspect file data or size."""
    root=Path(out)
    for rel in ('','private','public'):
        if _closed_path_kind(root/rel if rel else root)!='directory':
            return CLOSED_HOST_STAGE_UNKNOWN
    latest=CLOSED_HOST_STAGE_INITIAL
    gap=False
    for label,rel,required_kind in CLOSED_HOST_STAGE_PATHS:
        kind=_closed_path_kind(root/rel)
        if kind=='missing':
            gap=True
            continue
        if kind!=required_kind or gap:
            return CLOSED_HOST_STAGE_UNKNOWN
        latest=label
    return latest

def publish_closed_host_stage(out,value):
    label=closed_host_stage(out)
    if type(label)is not str or label not in CLOSED_HOST_STAGE_LABELS:
        label=CLOSED_HOST_STAGE_UNKNOWN
    report={'schema':CLOSED_HOST_STAGE_SCHEMA,'label':label,'release_acceptance':False}
    raw=(json.dumps(report,sort_keys=True,separators=(',',':'))+'\n').encode()
    scanner_path=C.ROOT/'tools/native-functional/screen-evidence.py'
    expected=value['execution_files']['tools/native-functional/screen-evidence.py']
    scanner=C.load(scanner_path,'private_review_closed_host_stage_scanner',expected)
    C.require(scanner.external_text(raw)==raw,'Closed host stage privacy rejected')
    C.exclusive(Path(out)/'public'/CLOSED_HOST_STAGE_FILE,raw)
    return label
def run_private(private,out,value):
    try:
        result=private()
    except BaseException:
        try:publish_closed_host_stage(out,value)
        except BaseException:pass
        raise
    if type(result)is int and result!=0:
        try:publish_closed_host_stage(out,value)
        except BaseException:pass
    return result

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
        return run_private(private,args.out,value)
    finally:sys.argv=saved
if __name__=='__main__':raise SystemExit(main())
