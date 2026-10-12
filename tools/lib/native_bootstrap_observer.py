"""Default-off test-only closed bootstrap records; never a qualification oracle.

The token correlates a disposable Native fixture. It is not authentication of
VM input delivery, guest state, PAM or an actual failure cause. Readers discard
all other log contents. Repeated records collapse to unique finite categories.
"""
import ast
import contextlib
import io
import json
import os
from pathlib import Path
import re
import signal
from contextlib import contextmanager
import stat
import sys
import types

MEMBER = 'host-native-bootstrap-observation.json'
PREFIX = b'ARCTIC-NATIVE-BOOTSTRAP '
HOST_PREFIX = b'ARCTIC-DICTATION-HOST-STAGE '
TOKEN_ENV = 'ARCTIC_NATIVE_BOOTSTRAP_TOKEN'
PATH_TYPE = type(Path())
STAGES = {
 'input': ('event-returned', 'fallback-entered', 'fallback-returned', 'fallback-refused'),
 'launcher': ('entry', 'guest-guards-passed', 'ancestry-passed', 'pidfds-passed',
              'parent-ready', 'detached', 'ready-written', 'disappeared',
              'barrier-written', 'exec-entered', 'failed'),
}
ERRORS = ('none','runtime-error','os-error','file-missing','permission-error',
          'keyboard-interrupt','system-exit','other-error')
HOST_STAGES = ('boot-acquire', 'boot-cleanup', 'boot-collect', 'boot-collect-missing', 'boot-collect-observed', 'boot-login', 'boot-menu', 'boot-settle', 'boot-shutdown', 'boot-terminal', 'boot-unlock', 'container-audio', 'container-complete', 'container-data', 'container-disk', 'container-driver', 'container-packages', 'container-profile', 'host-container', 'host-data', 'install-acquire', 'install-cleanup', 'install-command-enter-after', 'install-command-enter-before', 'install-command-shot-after', 'install-command-shot-before', 'install-command-type-after', 'install-command-type-before', 'install-engine', 'install-exit-missing-vm-exited', 'install-exit-missing-vm-running', 'install-exit-observed', 'install-live', 'install-live-observed', 'install-live-unobserved', 'install-marker-vm-exited', 'install-marker-vm-running', 'install-marker-vm-unknown', 'install-marker-wait-observed', 'install-marker-wait-unobserved', 'install-menu', 'install-not-started', 'install-preterminal-capture-preserved', 'install-preterminal-capture-unavailable', 'install-settle', 'install-shutdown', 'install-start-marker', 'install-start-observed', 'install-terminal', 'install-terminal-attempt-one', 'install-terminal-attempt-three', 'install-terminal-attempt-two', 'vm-acquire-enforce-floor-unavailable', 'vm-acquire-enforce-host-unavailable', 'vm-acquire-enforce-only-spec-ctrl', 'vm-acquire-enforce-tcg-unavailable', 'vm-acquire-file-missing', 'vm-acquire-json-error', 'vm-acquire-keyboard-interrupt', 'vm-acquire-no-qmp', 'vm-acquire-os-error', 'vm-acquire-other-error', 'vm-acquire-permission-error', 'vm-acquire-qemu-exited', 'vm-acquire-qmp-error', 'vm-acquire-stderr-unobserved', 'vm-acquire-system-exit')
LAUNCHER_GUARDS = 19
FALSE_FIELDS = ('runtime_cause','VM_input_or_PAM_ownership','runtime_acceptance','release_acceptance')

# Exact inherited stable-deferred acquisition/read/write/cleanup primitive.
@contextmanager
def owned_fd(path,flags,mode=0o777):
 # Stable deferred handlers span acquisition, bounded IO and owned cleanup.
 # A repeated cancellation cannot interrupt the transition into close().
 signals=(signal.SIGINT,signal.SIGTERM)
 saved=signal.pthread_sigmask(signal.SIG_BLOCK,set(signals));fd=None;pending=[];handlers={}
 def deferred(signum,frame):pending.append(signum)
 try:
  for signum in signals:handlers[signum]=signal.signal(signum,deferred)
  signal.pthread_sigmask(signal.SIG_SETMASK,saved)
  fd=os.open(path,flags,mode)
  yield fd
 finally:
  signal.pthread_sigmask(signal.SIG_BLOCK,set(signals))
  try:
   if fd is not None:
    # Linux has released the number even on a close error; never retry it.
    try:os.close(fd)
    except OSError:pass
  finally:
   for signum,handler in handlers.items():signal.signal(signum,handler)
   # Queue each observed kind while blocked, then restore the caller's mask.
   for signum in signals:
    if signum in pending:os.kill(os.getpid(),signum)
   signal.pthread_sigmask(signal.SIG_SETMASK,saved)

def require(value):
 if not value: raise ValueError('Closed Native bootstrap observation rejected')

def token(value):
 return type(value) is str and re.fullmatch('[0-9a-f]{32}',value) is not None

def code_tree(code):
 yield code
 for value in code.co_consts:
  if type(value) is types.CodeType: yield from code_tree(value)

def error_class(error):
 for kind,label in ((RuntimeError,'runtime-error'),(FileNotFoundError,'file-missing'),
                    (PermissionError,'permission-error'),(OSError,'os-error'),
                    (KeyboardInterrupt,'keyboard-interrupt'),(SystemExit,'system-exit')):
  if type(error) is kind:return label
 return 'none' if error is None else 'other-error'

def shape(value):
 if type(value) in (str,bytes,int,float,bool,type(None)):return (type(value),value)
 if type(value) in (tuple,list):return (type(value),tuple(shape(item) for item in value))
 if type(value) in (set,frozenset):return (type(value),frozenset(shape(item) for item in value))
 if type(value) is dict:return (dict,tuple((shape(key),shape(item)) for key,item in value.items()))
 return (type(value),id(value))

class Binding:
 """Bind the actual physical module functions and immediate caller, not clones.

 The outer lane must pin this helper and the physical Source before execution.
 This local binding establishes only the producer's Source function namespace.
 """
 def __init__(self,namespace,role):
  require(type(namespace) is dict and role in STAGES)
  self.namespace=namespace;self.role=role;self.token=os.environ.get(TOKEN_ENV,'')
  supplied=namespace.get('__builtins__')
  require(type(supplied) in (dict,types.ModuleType))
  self.builtin_namespace=supplied if type(supplied) is dict else vars(supplied)
  self.builtin_cells=dict(self.builtin_namespace)
  require(token(self.token))
  raw=Path(namespace['__file__']).read_bytes()
  self.tree=ast.parse(raw,namespace['__file__'])
  compiled=list(code_tree(compile(raw,namespace['__file__'],'exec',dont_inherit=True,optimize=0)))
  self.functions=[];self.codes={};self.classes=[]
  for name,value in tuple(namespace.items()):
   if type(value) is types.FunctionType and value.__globals__ is namespace:
    self._function(namespace,name,value,compiled,name)
   elif type(value) is type and value.__module__==namespace['__name__']:
    attrs=dict(vars(value));self.classes.append((name,value,value.__bases__,attrs))
    for key,item in attrs.items():
     function=item.__func__ if type(item) in (staticmethod,classmethod) else item
     if type(function) is types.FunctionType:
      self._function(value,key,function,compiled,name+'.'+key,item)
  self.globals={key:value for key,value in namespace.items() if key!='_NATIVE_OBSERVATION'}
  self.global_shapes={key:shape(value) for key,value in self.globals.items()}
  self.serializer=json.dumps;self.serializer_code=json.dumps.__code__
  self.serializer_globals=json.dumps.__globals__;self.printer=print
  self.sites=sorted((n for n in ast.walk(self.tree) if isinstance(n,ast.Call)
    and isinstance(n.func,ast.Name) and n.func.id=='require'),key=lambda n:(n.lineno,n.col_offset))
  if role=='launcher':require(len(self.sites)==LAUNCHER_GUARDS)
 def _function(self,holder,name,function,compiled,label,descriptor=None):
  require(function.__globals__ is self.namespace and function.__builtins__ is self.builtin_namespace
    and sum(function.__code__==c for c in compiled)==1)
  self.functions.append((holder,name,function,descriptor or function,function.__code__,
                         function.__defaults__,function.__kwdefaults__))
  self.codes[function.__code__]=label
 def unchanged(self):
  ns=self.namespace
  if set(ns)-{'_NATIVE_OBSERVATION'}!=set(self.globals):return False
  if set(self.builtin_namespace)!=set(self.builtin_cells) \
    or any(self.builtin_namespace[key] is not value for key,value in self.builtin_cells.items()):return False
  if any(ns.get(key) is not value for key,value in self.globals.items()):return False
  if any(shape(ns[key])!=value for key,value in self.global_shapes.items()):return False
  if json.dumps is not self.serializer or self.serializer.__code__ is not self.serializer_code \
    or self.serializer.__globals__ is not self.serializer_globals or print is not self.printer:return False
  for name,cls,bases,attrs in self.classes:
   if ns.get(name) is not cls or cls.__bases__!=bases or set(vars(cls))!=set(attrs):return False
   if any(vars(cls)[key] is not value for key,value in attrs.items()):return False
  for holder,name,function,descriptor,code,defaults,kwdefaults in self.functions:
   current=holder.get(name) if type(holder) is dict else vars(holder).get(name)
   if current is not descriptor or function.__code__ is not code or function.__globals__ is not ns \
     or function.__defaults__ is not defaults or function.__kwdefaults__ is not kwdefaults \
     or function.__builtins__ is not self.builtin_namespace:return False
  return os.environ.get(TOKEN_ENV,'')==self.token
 def owns(self,frame):
  return any(frame.f_code is code for code in self.codes) and frame.f_globals is self.namespace \
    and frame.f_builtins is self.builtin_namespace
 def guard_site(self,error):
  if type(error) is not RuntimeError or not self.unchanged():return 'unknown'
  rows=[];current=BaseException.__traceback__.__get__(error)
  while current is not None and len(rows)<64:rows.append(current);current=current.tb_next
  if current is not None or len(rows)<2:return 'unknown'
  leaf,caller=rows[-1],rows[-2]
  if not self.owns(leaf.tb_frame) or self.codes[leaf.tb_frame.f_code]!='require' \
    or not self.owns(caller.tb_frame):return 'unknown'
  # A require call may span several lines; only one fixed public AST site is admitted.
  found=[i for i,node in enumerate(self.sites,1) if node.lineno<=caller.tb_lineno<=node.end_lineno]
  return 'launcher-require-'+format(found[0],'03d') if len(found)==1 else 'unknown'
 def emit(self,stage,error=None):
  if stage not in STAGES[self.role] or not self.unchanged():return
  frame=sys._getframe(1)
  if not self.owns(frame) or self.codes[frame.f_code] not in ('_native_input','_native_event'):return
  caller=frame.f_back
  if caller is None or not self.owns(caller) \
    or self.codes[caller.f_code]!=('VM.press' if self.role=='input' else 'main'):return
  row=dict(role=self.role,stage=stage,error_class=error_class(error),
           guard_site=self.guard_site(error) if self.role=='launcher' else 'unknown')
  closed_row(row)
  # Every key/value is a Source-closed ASCII enum. Avoid formatter hooks.
  raw='{'+','.join('"'+key+'":"'+row[key]+'"' for key in
    ('role','stage','error_class','guard_site'))+'}'
  line=PREFIX+self.token.encode('ascii')+b' '+raw.encode('ascii')+b'\n'
  try:
   if self.role=='launcher':
    with owned_fd('/dev/ttyS0',os.O_WRONLY|os.O_NOFOLLOW|os.O_NOCTTY) as fd:
     at=0
     while at<len(line):
      count=os.write(fd,memoryview(line)[at:]);require(type(count) is int and count>0);at+=count
   else:self.printer(line.decode('ascii').rstrip('\n'),flush=True)
  except (OSError,ValueError):pass

def closed_row(row):
 require(type(row) is dict and set(row)=={'role','stage','error_class','guard_site'})
 role=row['role'];stage=row['stage'];kind=row['error_class'];site=row['guard_site']
 require(type(role) is str and role in STAGES and type(stage) is str and stage in STAGES[role]
   and type(kind) is str and kind in ERRORS and type(site) is str)
 require(site=='unknown' or role=='launcher' and site in {
  'launcher-require-'+format(i,'03d') for i in range(1,LAUNCHER_GUARDS+1)})
 require((stage=='failed' and role=='launcher') or kind=='none' and site=='unknown')
 return row

def closed(value):
 require(type(value) is dict and set(value)=={'schema','input_states','host_stages','producer_categories','live_bootstrap',*FALSE_FIELDS})
 require(value['schema']=='arctic-native-bootstrap-observation-v2'
   and all(value[key] is False for key in FALSE_FIELDS))
 states=value['input_states']
 require(type(states) is dict and set(states)=={'harness','serial-install','serial-boot'}
   and all(type(item) is str and item in ('projected','not-observed','rejected') for item in states.values()))
 host=value['host_stages'];rows=value['producer_categories']
 require(type(host) is list and all(type(item) is str and item in HOST_STAGES for item in host)
   and host==sorted(set(host)) and type(rows) is list)
 keys=[]
 for row in rows:closed_row(row);keys.append(tuple(row[key] for key in ('role','stage','error_class','guard_site')))
 require(keys==sorted(set(keys)))
 guest=value['live_bootstrap']
 require(type(guest)is dict and set(guest)=={'offline_gate','runner_begin','provenance','runner_end','live_smoke_exit'})
 require(type(guest['offline_gate'])is str and guest['offline_gate']in ('not-observed','passed','failed','unknown')
   and type(guest['live_smoke_exit'])is str and guest['live_smoke_exit']in ('not-observed','zero','nonzero','unknown'))
 require(all(type(guest[key])is bool for key in ('runner_begin','provenance','runner_end')))
 return value

def parse_line(F,line,owned_token,host,rows,guest=None):
 # The additional live state records fixed labels only, never their payloads.
 if guest is not None:
  require(type(guest)is dict and set(guest)=={'offline_gate','runner_begin','provenance','runner_end','live_smoke_exit'})
  if line==b'ARCTIC-OFFLINE-GATE=passed: restricted QEMU network, no outside HTTP response':
   guest['offline_gate'].add('passed')
  elif line==b'ARCTIC-OFFLINE-GATE=failed: outside HTTP response received':
   guest['offline_gate'].add('failed')
  elif line.startswith(b'ARCTIC-OFFLINE-GATE='):
   guest['offline_gate'].add('unknown')
  for key,prefix_ in (('runner_begin',b'ARCTIC-NATIVE-RUNNER-BEGIN {'),
                       ('provenance',b'ARCTIC-NATIVE-PROVENANCE {'),
                       ('runner_end',b'ARCTIC-NATIVE-RUNNER-END {')):
   if line.startswith(prefix_) and line.endswith(b'}'):guest[key]=True
  prefix_=b'ARCTIC-LIVE-SMOKE-EXIT='
  if line.startswith(prefix_):
   value_=line[len(prefix_):]
   label_='unknown'
   if re.fullmatch(rb'(?:0|[1-9][0-9]{0,2})',value_) and int(value_)<=255:
    label_='zero'if value_==b'0'else'nonzero'
   guest['live_smoke_exit'].add(label_)
 # No arbitrary prefix scan: only exact, complete line records are candidates.
 prefix=HOST_PREFIX+owned_token.encode('ascii')+b' '
 if line.startswith(prefix):
  code=line[len(prefix):].decode('ascii','strict')
  require(code in HOST_STAGES);host.add(code);return
 prefix=PREFIX+owned_token.encode('ascii')+b' '
 if line.startswith(prefix):
  row=closed_row(F.strict_json(line[len(prefix):]));rows.add(tuple(row[key] for key in ('role','stage','error_class','guard_site')))

def scan_owned(F,path,owned_token,host,rows,guest=None):
 # Stream future owned logs only; no original/private bytes are copied or returned.
 require(token(owned_token) and type(path) is PATH_TYPE and path.is_absolute() and path.resolve()==path)
 if not path.exists():return 'not-observed'
 prior=path.lstat();require(stat.S_ISREG(prior.st_mode) and prior.st_nlink==1
   and prior.st_uid in (0,os.geteuid()) and not prior.st_mode&0o022 and prior.st_size<=128*1024*1024)
 local_host=set();local_rows=set();tail=b''
 local_guest=dict(offline_gate=set(),runner_begin=False,provenance=False,runner_end=False,live_smoke_exit=set())if guest is not None else None
 with F.owned_fd(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK) as fd:
  require(F.same(prior,os.fstat(fd)))
  remaining=prior.st_size
  while remaining:
   chunk=os.read(fd,min(65536,remaining));require(chunk);remaining-=len(chunk);tail+=chunk
   while b'\n' in tail:
    line,tail=tail.split(b'\n',1);require(len(line)<=65536)
    parse_line(F,line.rstrip(b'\r'),owned_token,local_host,local_rows,local_guest)
   require(len(tail)<=65536)
  require(not os.read(fd,1) and F.same(prior,os.fstat(fd)) and F.same(prior,path.lstat()))
 # Only LF-terminated fixed records are candidates; unrelated tail bytes stay ignored.
 if tail:
  require(not tail.startswith(PREFIX+owned_token.encode('ascii')+b' ')
    and not tail.startswith(HOST_PREFIX+owned_token.encode('ascii')+b' ')
    and not(guest is not None and tail.startswith((b'ARCTIC-OFFLINE-GATE=',
     b'ARCTIC-NATIVE-RUNNER-BEGIN ',b'ARCTIC-NATIVE-PROVENANCE ',b'ARCTIC-NATIVE-RUNNER-END ',b'ARCTIC-LIVE-SMOKE-EXIT='))))
 if guest is not None:
  guest['offline_gate'].update(local_guest['offline_gate']);guest['live_smoke_exit'].update(local_guest['live_smoke_exit'])
  for key in ('runner_begin','provenance','runner_end'):guest[key]=guest[key]or local_guest[key]
 host.update(local_host);rows.update(local_rows);return 'projected'

def project(F,scanner,paths,owned_token,output,primary=None):
 """Optional future-run diagnosis. The original failure always remains primary."""
 try:
  require(token(owned_token) and type(paths) is dict and set(paths)=={'harness','serial-install','serial-boot'})
  states={};host=set();rows=set()
  guest=dict(offline_gate=set(),runner_begin=False,provenance=False,runner_end=False,live_smoke_exit=set())
  for role,path in paths.items():
   try:states[role]=scan_owned(F,path,owned_token,host,rows,guest if role=='serial-install'else None)
   except Exception:states[role]='rejected'
  categories=[dict(zip(('role','stage','error_class','guard_site'),key)) for key in sorted(rows)]
  live=dict(offline_gate=next(iter(guest['offline_gate']))if len(guest['offline_gate'])==1 else'unknown'if guest['offline_gate']else'not-observed',
    runner_begin=guest['runner_begin'],provenance=guest['provenance'],runner_end=guest['runner_end'],
    live_smoke_exit=next(iter(guest['live_smoke_exit']))if len(guest['live_smoke_exit'])==1 else'unknown'if guest['live_smoke_exit']else'not-observed')
  value=closed(dict(schema='arctic-native-bootstrap-observation-v2',input_states=states,
    host_stages=sorted(host),producer_categories=categories,live_bootstrap=live,**{key:False for key in FALSE_FIELDS}))
  raw=F.encode_json(value);closed(F.strict_json(raw))
  with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
   require(scanner.external_text(raw) is raw)
  F.write_exclusive(output,raw)
 except BaseException as secondary:
  if primary is None and isinstance(secondary,(KeyboardInterrupt,InterruptedError,SystemExit)):raise
