#!/usr/bin/env python3
"""Fresh disabled admission around exact reviewed BIOS scanner dependency selection."""
from pathlib import Path
import common as C
HERE=Path(__file__).resolve().parent

def main_adapter(value):
    C.manifest(value)
    for path,expected in value['execution_files'].items():
        C.require(C.digest_file(C.ROOT/path)==expected,'Reviewed format runtime pin differs')
    helper=C.load(HERE/'composition.py','bios_reviewed_format_composition',
        value['execution_files']['tools/final-bios-csi-boundary-install/composition.py'])
    def source_loader(path,expected):
        raw=C.regular(path,1024*1024)
        C.require(__import__('hashlib').sha256(raw).hexdigest()==expected,'Reviewed Source buffer differs')
        return raw
    return helper.build(C.ROOT,value,source_loader,C.guard)

def main():
    value=C.manifest(C.strict_json(C.regular(HERE/'execution-manifest.json',1024*1024)),True)
    wrapped,observed,original,state=main_adapter(value)
    return wrapped()
if __name__=='__main__':raise SystemExit(main())
