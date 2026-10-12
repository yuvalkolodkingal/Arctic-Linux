#!/usr/bin/env python3
"""New first-ADD admission around the exact retained failure main factory."""
from pathlib import Path
import types
import common as C

HERE=Path(__file__).resolve().parent
RETAINED=C.ROOT/'tools/final-bios-failure-evidence'

def main_adapter(value):
    """Keep every accepted dependency except the explicitly copied guard."""
    C.manifest(value,True)
    for name,expected in value['execution_files'].items():
        C.require(C.digest_file(C.ROOT/name)==expected,'Retained operational runtime pin differs')
    helper=C.load(RETAINED/'evidence.py','retained_bios_f68_helper',
        value['execution_files']['tools/final-bios-failure-evidence/evidence.py'])
    source= C.strict_json(C.regular(RETAINED/'execution-manifest.json',1024*1024))
    C.require(C.digest_file(RETAINED/'execution-manifest.json')==value['retention_binding']['source_manifest_sha256'],
        'Accepted retained Source manifest differs')
    exact,state=helper.build(source)
    original_admission=exact.__globals__['C']
    original_path=C.ROOT/'tools/final-bios-install/execution-manifest.json'
    original=original_admission.manifest(original_admission.strict_json(
        original_admission.regular(original_path,1024*1024)),True)
    def guard(projected,source_checkout,inputs=None):
        original_admission.require(projected==original,'Original retained main manifest projection differs')
        return C.guard(value,source_checkout,inputs)
    admission=types.SimpleNamespace(**original_admission.__dict__)
    admission.guard=guard
    dependencies=exact.__globals__.copy();dependencies['C']=admission
    wrapped=types.FunctionType(exact.__code__,dependencies,exact.__name__,exact.__defaults__,exact.__closure__)
    return wrapped,exact,state

def main():
    value=C.manifest(C.strict_json(C.regular(HERE/'execution-manifest.json',1024*1024)),True)
    wrapped,exact,state=main_adapter(value)
    return wrapped()

if __name__=='__main__':raise SystemExit(main())
