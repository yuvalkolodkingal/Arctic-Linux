"""Owned synthetic environment fixture only. Imports no startup collector."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
def require(value,message):
    if not value:raise RuntimeError(message)
require(os.environ=={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},'Unexpected fixture interpreter environment')
require(len(sys.argv)==2 and sys.argv[1].isdecimal(),'Unexpected fixture descriptor argument')
fd=int(sys.argv[1]);require(fd>=3,'Unexpected fixture descriptor')
def load(name):
    spec=importlib.util.spec_from_file_location('synthetic_'+name,HERE/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
E=load('sealed_environment');T=load('toolkit')
environment=E.consume(fd,os.getuid())
# Complete close is required before the target fixture is launched.
try:os.fstat(fd)
except OSError:pass
else:raise RuntimeError('Owned environment descriptor survived consumption')
exe=Path('/run/arctic-safe/env-native-v1')
with tempfile.TemporaryDirectory(prefix='sealed-handoff-',dir='/tmp') as tmp:
    logger=T.OwnedLog(Path(tmp)/'log',max_raw=65536,max_seconds=5)
    logger.capture(str(exe),[str(exe)],T.sha(exe.read_bytes()),exe.stat().st_uid,environment=environment)
