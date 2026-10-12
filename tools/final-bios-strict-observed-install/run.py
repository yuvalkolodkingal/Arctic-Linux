#!/usr/bin/env python3
"""New exact admission around accepted original BIOS evidence observation."""
from pathlib import Path
import types
import common as C
HERE=Path(__file__).resolve().parent
OBSERVER=C.ROOT/'tools/final-bios-strict-screen-observer'

def main_adapter(value):
    """Pure Source composition; actual guard still requires operational ready."""
    C.manifest(value)
    for name,expected in value['execution_files'].items():
        C.require(C.digest_file(C.ROOT/name)==expected,'Strict observed runtime pin differs')
    helper=C.load(OBSERVER/'observer.py','accepted_af135_bios_strict_observer',
        value['execution_files']['tools/final-bios-strict-screen-observer/observer.py'])
    source=C.strict_json(C.regular(OBSERVER/'execution-manifest.json',1024*1024))
    C.require(C.digest_file(OBSERVER/'execution-manifest.json')==value['strict_screen_binding']['source_manifest_sha256'],
        'Accepted strict observer manifest differs')
    observed,original,state=helper.build(source)
    original_admission=observed.__globals__['C']
    original_path=C.ROOT/'tools/final-bios-install/execution-manifest.json'
    original_manifest=original_admission.manifest(original_admission.strict_json(
        original_admission.regular(original_path,1024*1024)),True)
    def guard(projected,source_checkout,inputs=None):
        original_admission.require(projected==original_manifest,'Original observed main manifest projection differs')
        return C.guard(value,source_checkout,inputs)
    admission=types.SimpleNamespace(**original_admission.__dict__);admission.guard=guard
    dependencies=observed.__globals__.copy();dependencies['C']=admission
    wrapped=types.FunctionType(observed.__code__,dependencies,observed.__name__,observed.__defaults__,observed.__closure__)
    return wrapped,observed,original,state

def main():
    value=C.manifest(C.strict_json(C.regular(HERE/'execution-manifest.json',1024*1024)),True)
    wrapped,observed,original,state=main_adapter(value)
    return wrapped()
if __name__=='__main__':raise SystemExit(main())
