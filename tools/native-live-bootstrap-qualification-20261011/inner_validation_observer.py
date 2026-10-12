"""Disabled Source-only original Native inner validation observations.
No acquisition, VM, API, original input CLI, UART/audio bytes or qualification.
"""
import ast,builtins,contextlib,hashlib,io,json,signal,sys,types
from pathlib import Path
SOURCE_HEAD='253fade741e319b37f659ae25a5d1091eab6d9ab'
CONSUMER=Path('/tmp/arctic-native-terminal-consumer-Source-preparation-20261011/native_terminal_admission.py')
CONSUMER_SHA='de0e4c049072187d15949724fcedb3848e0814e58103626c628985d271f312cb'
ROLES=('native-live','native-installed','live-harness','installed-harness','boot-identity')
WAV_FIELDS=('stereo','rate-48000','width-16bit','uncompressed','frames-positive')
ERROR_CLASSES=('runtime-error','value-error','os-error','file-missing','permission-error','timeout-error','process-deadline',
 'process-failed','interrupted','cancelled','system-exit','other')
def require(value):
 if not value:raise ValueError('Closed disabled Native inner Source observer differs')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def module(raw,path,name):
 value=types.ModuleType(name);value.__file__=str(path)
 exec(compile(raw,str(path),'exec',dont_inherit=True,optimize=0),value.__dict__)
 return value
def build(execution):
 """Only whole already-accepted public Source loads; no original function runs."""
 execution=Path(execution);raw=CONSUMER.read_bytes();require(sha(raw)==CONSUMER_SHA)
 C=module(raw,CONSUMER,'native_inner_accepted_Source_consumer')
 F,scanner,public=C.load_source(execution)
 E=module(public['tools/native-functional/evidence.py'],execution/'tools/native-functional/evidence.py','native_inner_original_evidence')
 A=module(public['tools/native-functional/apps.py'],execution/'tools/native-functional/apps.py','native_inner_original_apps')
 saved={name:sys.modules.get(name)for name in('evidence','failure_evidence','apps')}
 missing={name for name in saved if name not in sys.modules}
 try:
  sys.modules.update(evidence=E,failure_evidence=F,apps=A)
  R=module(public['tools/native-functional/runner.py'],execution/'tools/native-functional/runner.py','native_inner_original_runner')
 finally:
  for name,value in saved.items():
   if name in missing:sys.modules.pop(name,None)
   else:sys.modules[name]=value
 registry=F.Registry(R,public['tools/native-functional/runner.py'],sha(public['tools/native-functional/runner.py']),
  E,public['tools/native-functional/evidence.py'],sha(public['tools/native-functional/evidence.py']))
 require(tuple(len(o.sites)for o in registry.owners)==(50,113))
 return Capture(F,scanner,registry,public),R,E

def functions(cls):
 return {name:(value,value.__code__,value.__globals__)for name,value in vars(cls).items()if type(value)is types.FunctionType}
def functions_unchanged(cls,bound):
 return(set(bound)=={n for n,v in vars(cls).items()if type(v)is types.FunctionType}
  and all(vars(cls).get(n)is f and f.__code__ is c and f.__globals__ is g for n,(f,c,g)in bound.items()))
def namespace_functions(namespace):
 return {name:(value,value.__code__,value.__globals__)for name,value in namespace.items()if type(value)is types.FunctionType}
def namespace_unchanged(namespace,cells,bound):
 return(set(namespace)==set(cells)and all(namespace[n]is v for n,v in cells.items())
  and set(bound)=={n for n,v in namespace.items()if type(v)is types.FunctionType}
  and all(namespace[n]is f and f.__code__ is c and f.__globals__ is g for n,(f,c,g)in bound.items()))

class Capture:
 def __init__(self,F,scanner,registry,public):
  self.F=F;self.scanner=scanner;self.registry=registry;self.public=public
  self.runner=registry.owners[0];self.evidence=registry.owners[1]
  E=self.evidence.module
  node=next(n for n in self.evidence.tree.body if isinstance(n,ast.FunctionDef)and n.name=='validate_harness_serial')
  self.tries=sorted((n for n in ast.walk(node)if isinstance(n,ast.Try)),key=lambda n:n.lineno)
  require(len(self.tries)==4)
  self.validator=E.validate_harness_serial.__code__;self.audio=E.preserve_audio.__code__
  self.wave_type=E.wave._wave_params
  self.rows={};self.wav={};self.status='not-armed';self.hook=self.trace;self.armed=False;self.previous=None
  self.namespaces=[(ns,dict(ns),namespace_functions(ns))for ns in(globals(),F.__dict__,scanner.__dict__)]
  self.capture_functions=functions(type(self));self.registry_functions=functions(type(registry));self.owner_functions=functions(F.Owner)
  self.module_cells=[(sys,'settrace',sys.settrace),(sys,'gettrace',sys.gettrace),(sys,'_getframe',sys._getframe),
   (signal,'pthread_sigmask',signal.pthread_sigmask)]
 def bound(self):
  return(all(namespace_unchanged(ns,cells,bound)for ns,cells,bound in self.namespaces)
   and functions_unchanged(type(self),self.capture_functions)
   and functions_unchanged(type(self.registry),self.registry_functions)
   and functions_unchanged(self.F.Owner,self.owner_functions)
   and all(getattr(m,n)is v for m,n,v in self.module_cells)
   and all(o.unchanged()for o in self.registry.owners)
   and self.evidence.module.wave._wave_params is self.wave_type)
 def __enter__(self):
  require(self.bound());self.previous=sys.gettrace()
  if self.previous is not None:self.status='existing-trace-unobserved';return self
  try:
   # Declare ownership before the setter, including cancellation after the
   # real hook was installed but before its Python call returns.
   self.status='armed';self.armed=True;sys.settrace(self.hook)
  except BaseException:
   self.__exit__(*sys.exc_info());raise
  return self
 def role(self,frame):
  if frame.f_code is not self.validator:return None
  positions=self.evidence.bound[frame.f_code][2].get(frame.f_lasti)
  if positions is None:return None
  found=[i for i,node in enumerate(self.tries)if self.F.inside(positions.positions,node)]
  if len(found)!=1:return None
  index=found[0]
  if index==0:
   stage=frame.f_locals.get('stage');return 'native-'+stage if type(stage)is str and stage in('live','installed')else None
  return ROLES[index+1]if index in(1,2,3)else None
 def wav_checks(self,frame):
  params=frame.f_locals.get('params')
  if type(params)is not self.wave_type:return {name:'unknown'for name in WAV_FIELDS}
  pairs=(('stereo','nchannels',2),('rate-48000','framerate',48000),('width-16bit','sampwidth',2),('uncompressed','comptype','NONE'))
  result={name:(getattr(params,key)==expected if type(getattr(params,key))is type(expected)else'unknown')for name,key,expected in pairs}
  result['frames-positive']=params.nframes>0 if type(params.nframes)is int else'unknown'
  return result
 def audio_stage(self,frame):
  caller=frame.f_back
  if(caller is None or not self.runner.owns(caller)or caller.f_code is not self.runner.module.run.__code__):return 'unknown'
  stage=caller.f_locals.get('stage');return stage if type(stage)is str and stage in('install','boot')else'unknown'
 def trace(self,frame,event,arg):
  if event=='call':
   if frame.f_code in(self.validator,self.audio):
    frame.f_trace_lines=False;frame.f_trace_opcodes=False;return self.hook
   return None
  if event!='exception':return self.hook
  # An existing original exception is the primary; an optional observer cannot
  # replace it, including cancellation during these finite-only checks.
  try:
   require(self.bound()and sys.gettrace()is self.hook and sys._getframe().f_back is frame
    and type(frame)is types.FrameType and type(arg)is tuple and len(arg)==3
    and isinstance(arg[1],builtins.BaseException)and arg[0]is type(arg[1])and type(arg[2])is types.TracebackType
    and arg[2].tb_frame is frame and arg[2].tb_lasti==frame.f_lasti
    and BaseException.__traceback__.__get__(arg[1])is arg[2])
   require(self.evidence.owns(frame))
   site=self.registry.describe(arg[1],arg[2])
   if frame.f_code is self.validator:
    role=self.role(frame)
    if role is not None and role not in self.rows:
     self.rows[role]=dict(Source_guard_site=site if site in self.F.GUARD_SITES else'unknown',error_class=self.F.error_class(arg[1]))
   elif frame.f_code is self.audio:
    stage=self.audio_stage(frame)
    if stage not in self.wav:
     self.wav[stage]=dict(Source_guard_site=site if site in self.F.GUARD_SITES else'unknown',error_class=self.F.error_class(arg[1]),
      predicates=self.wav_checks(frame)if site=='native-evidence-require-111'else{name:'unknown'for name in WAV_FIELDS})
  except BaseException:pass
  return self.hook
 def __exit__(self,kind,error,tb):
  saved=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
  try:
   try:
    if self.armed:
     try:
      if sys.gettrace()is not self.hook:
       self.status='hook-changed-unobserved';self.rows={};self.wav={}
     finally:
      # Protect getter, restoration and ownership transition as one cleanup.
      sys.settrace(self.previous);self.armed=False
    if not self.bound():self.status='binding-denied';self.rows={};self.wav={}
    elif self.status=='armed':self.status='closed-source-observed'
   except BaseException:
    if error is None:raise
  finally:
   try:signal.pthread_sigmask(signal.SIG_SETMASK,saved)
   except BaseException:
    if error is None:raise
  return False
 def result(self):
  require(self.bound()and self.status!='armed')
  value=dict(schema='arctic-native-inner-source-observation-v1',status=self.status,
   original_validation_roles=self.rows,original_WAV_predicates=self.wav,
   private_UART_audio_report_values_counts_digests_or_excerpts_exported=False,
   actual_VM_phase_PAM_or_guest_Code_ownership=False,runtime_cause=False,
   runtime_acceptance=False,release_acceptance=False)
  closed(value,self.F);raw=self.F.encode_json(value)
  require(len(raw)<=32*1024)
  with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):require(self.scanner.external_text(raw)is raw)
  return value

def closed(value,F):
 require(type(value)is dict and set(value)=={'schema','status','original_validation_roles','original_WAV_predicates',
  'private_UART_audio_report_values_counts_digests_or_excerpts_exported','actual_VM_phase_PAM_or_guest_Code_ownership',
  'runtime_cause','runtime_acceptance','release_acceptance'}and value['schema']=='arctic-native-inner-source-observation-v1'
  and value['status']in('not-armed','closed-source-observed','existing-trace-unobserved','hook-changed-unobserved','binding-denied')
  and all(value[k]is False for k in('private_UART_audio_report_values_counts_digests_or_excerpts_exported',
   'actual_VM_phase_PAM_or_guest_Code_ownership','runtime_cause','runtime_acceptance','release_acceptance')))
 rows=value['original_validation_roles'];wav=value['original_WAV_predicates']
 require(type(rows)is dict and set(rows)<=set(ROLES)and type(wav)is dict and set(wav)<=set(('install','boot','unknown')))
 for row in rows.values():require(type(row)is dict and set(row)=={'Source_guard_site','error_class'}
  and type(row['error_class'])is str and row['error_class']in ERROR_CLASSES
  and(row['Source_guard_site']=='unknown'or row['Source_guard_site']in F.GUARD_SITES))
 for row in wav.values():
  require(type(row)is dict and set(row)=={'Source_guard_site','error_class','predicates'}
   and type(row['error_class'])is str and row['error_class']in ERROR_CLASSES
   and(row['Source_guard_site']=='unknown'or row['Source_guard_site']in F.GUARD_SITES)
   and type(row['predicates'])is dict and set(row['predicates'])==set(WAV_FIELDS)
   and all(type(v)is bool or type(v)is str and v=='unknown'for v in row['predicates'].values()))
 return value

def main():raise SystemExit('Native inner observer remains disabled Source preparation')
if __name__=='__main__':main()
