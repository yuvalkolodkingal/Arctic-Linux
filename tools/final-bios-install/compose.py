#!/usr/bin/env python3
"""Stage only exact byte-pinned Source modules in the existing single guest file."""
import base64
import hashlib
import json
from pathlib import Path
import common as C


def compose(source,probe,security,context,output):
    C.require(not output.exists() and not output.is_symlink(),'Guest output must be unused')
    modules={'bios_probe':C.regular(probe,128*1024),'native_bios_source':C.regular(source/'tools/native-functional/native_smoke.py',512*1024),'bios_security':C.regular(security,512*1024)}
    for name,key in (('bios_probe','probe_sha256'),('native_bios_source','native_sha256'),('bios_security','security_sha256')):
        C.require(hashlib.sha256(modules[name]).hexdigest()==context[key],'Composed exact source bytes differ')
    lines=['#!/usr/bin/env python3','import base64,hashlib,json,sys,types','from pathlib import Path','_modules={}']
    for name,raw in modules.items():
        lines.extend([f'_raw=base64.b64decode({base64.b64encode(raw).decode()!r},validate=True)',f'assert hashlib.sha256(_raw).hexdigest()=={hashlib.sha256(raw).hexdigest()!r}',f'_module=types.ModuleType({name!r})','_module.__file__="/run/t/guest-check.py"',f'_modules[{name!r}]=_module','exec(compile(_raw,_module.__file__,"exec"),_module.__dict__)'])
    lines.extend(['_context='+repr(context),'try:','    assert len(sys.argv)==2 and sys.argv[1] in ("live","installed")','    interval=_modules["bios_security"].interval_type(_modules["native_bios_source"])','    result=_modules["bios_probe"].main(sys.argv[1],_context,_modules["native_bios_source"],interval)','except BaseException:','    print("ARCTIC-FINAL-BIOS-FAILED",flush=True)','    result=1','raise SystemExit(result)'])
    data=('\n'.join(lines)+'\n').encode();C.require(len(data)<=1024*1024,'Guest source byte bound');C.exclusive(output,data)
    return hashlib.sha256(data).hexdigest()
