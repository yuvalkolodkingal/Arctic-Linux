import sys
sys.dont_write_bytecode=True
import importlib.util,os
from pathlib import Path
root=Path('/run/arctic-mango-trace')
if os.geteuid()!=0:raise RuntimeError('Root end request required')
s=importlib.util.spec_from_file_location('owned_stop_preparer',root/'prepare.py');p=importlib.util.module_from_spec(s);s.loader.exec_module(p)
p.fresh_write(root/'stop',b'ARCTIC_TRACE_END_V1\n',0o644)
