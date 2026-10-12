"""Actual original UI main/decode Code with disclosed synthetic setup dependencies."""
import ast,contextlib,hashlib,io,json,os,pathlib,signal,subprocess,sys,tempfile,types,unittest
from unittest import mock
HERE=pathlib.Path(__file__).resolve().parent;BASE='1cf129331831f697d6a8831140f715cde75e043c';DB='/dev/shm/arctic-Root-complete-Source-DB-20261012/objects.git'
OLD='tools/final-ui-bootstrap-csi-20261011';ORIGINAL='tools/final-installed-ui-settings-readiness';LINE=b' UserID     : "Fedora (44) <fedora-44-primary@fedoraproject.org>"\n'
def raw(p):return subprocess.check_output(['git','--git-dir='+DB,'show',BASE+':'+p])
def module(b,path,name):
 m=types.ModuleType(name);m.__file__=str(path);exec(compile(b,str(path),'exec',optimize=0),m.__dict__);return m
class Controls(unittest.TestCase):
 def setUp(self):
  self.utils=module((HERE/'originals.py').read_bytes(),HERE/'originals.py','fixed_originals')
  prior=sys.modules.get('originals');sys.modules['originals']=self.utils
  try:self.obs=module((HERE/'observer.py').read_bytes(),HERE/'observer.py','new_observer')
  finally:
   if prior is None:sys.modules.pop('originals',None)
   else:sys.modules['originals']=prior
  self.helper_raw=(HERE/'match-diagnostic.py').read_bytes();self.helper=module(self.helper_raw,HERE/'match-diagnostic.py','new_helper')
  self.sc_raw=raw(OLD+'/scanner.py');self.sc=module(self.sc_raw,OLD+'/scanner.py','actual_selected_scanner')
  self.c_raw=raw(ORIGINAL+'/common.py');self.c=module(self.c_raw,ORIGINAL+'/common.py','original_common')
  self.r_raw=raw(ORIGINAL+'/run.py');saved={n:(n in sys.modules,sys.modules.get(n))for n in('common','compose')}
  sys.modules['common']=self.c;sys.modules['compose']=types.SimpleNamespace(compose=lambda *a:None)
  try:self.run=module(self.r_raw,ORIGINAL+'/run.py','actual_original_UI_run')
  finally:
   for n,(present,v)in saved.items():
    if present:sys.modules[n]=v
    else:sys.modules.pop(n,None)
  self.sc_owner=self.obs.OwnedSource(self.sc.__dict__,self.sc_raw,self.sc.__file__,'original-scanner')
  self.common_owner=self.obs.OwnedSource(self.c.__dict__,self.c_raw,self.c.__file__,'original-ui-common')
  self.helper_owner=self.obs.OwnedSource(self.helper.__dict__,self.helper_raw,self.helper.__file__,'match-diagnostic')
  self.vocabulary=frozenset({n.value for n in ast.walk(ast.parse(self.helper_raw))if isinstance(n,ast.Constant)and type(n.value)is str}|{'external-rule-'+format(n,'03d')for n in range(1,11)})
 def invoke(self,content,stage='live',foreign=False,no_text_args=False):
  # Original main Code is unchanged. Only setup/hardware/child dependencies
  # are synthetic; no KVM, Docker, real input/ISO or Source guard is claimed.
  caught=[];results=[];owner=None;observed_error=[]
  proxy=types.ModuleType('selected_scanner_proxy');proxy.__dict__.update(self.sc.__dict__)
  def observe(wire):
   caller=sys._getframe(1)
   try:return self.sc.external_text(wire)
   except RuntimeError as error:
    before=(error,error.__traceback__);observed_error.append(error)
    if no_text_args:
     class NoText:
      def __str__(self):raise AssertionError('synthetic operands must not format')
      def __repr__(self):raise AssertionError('synthetic operands must not format')
     error.args=(NoText(),)
    value=self.obs.observed_failure(error,self.sc,self.sc_owner,owner,self.common_owner,self.helper,self.helper_owner,self.vocabulary,wire,caller)
    self.assertIs(error,before[0]);self.assertIs(error.__traceback__,before[1]);results.append(value);raise
  proxy.external_text=observe
  fakepath=type('SyntheticKVMPath',(type(pathlib.Path()),),{'is_char_device':lambda p:str(p)=='/dev/kvm'})
  ns=self.run.__dict__.copy();C=types.SimpleNamespace(**self.c.__dict__)
  manifest=json.loads(raw(ORIGINAL+'/execution-manifest.json'))
  def regular(p,limit):
   name=p.name
   if name=='execution-manifest.json':return json.dumps(manifest).encode()
   if name=='vm-prepared-image-id.txt':return ('sha256:'+'1'*64+'\n').encode()
   if name=='serial-install.log':return content if stage=='live'else b'ARCTIC-FINAL-UI-LIVE-PRECHECK=PASS\n'
   if name=='serial-boot.log':return content
   raise OSError('synthetic unread private member')
  C.regular=regular;C.guard=lambda *a:None;C.digest_file=lambda *a:'2'*64;C.git=lambda *a:BASE
  C.load=lambda p,n:proxy if p.name=='screen-evidence.py'else types.SimpleNamespace(validate_context=lambda *a:None)
  ns.update(C=C,Path=fakepath,compose=types.SimpleNamespace(compose=lambda *a:None),execute=lambda *a:None,remove_owned_container=lambda *a:None)
  for name,f in tuple(ns.items()):
   if type(f)is types.FunctionType and f.__globals__ is self.run.__dict__:ns[name]=types.FunctionType(f.__code__,ns,f.__name__,f.__defaults__,f.__closure__)
  owner=self.obs.OwnedSource(ns,self.r_raw,self.run.__file__,'original-ui-host')
  def docker(argv,*a,**k):
   self.assertEqual(argv[:3],['docker','image','inspect']);task=ns['uuid'].uuid4().hex
   return json.dumps({'org.arctic.test.vm-tools.task':task,'org.arctic.test.vm-tools.container':'arctic-paired-'+task+'-'+task[:8],'org.arctic.test.vm-tools.scope':'paired-v1'}).encode()
  fixed=types.SimpleNamespace(hex='0'*32)
  chosen=ns['main'] if not foreign else types.FunctionType(ns['main'].__code__,ns.copy())
  with tempfile.TemporaryDirectory(dir='/dev/shm')as folder:
   root=pathlib.Path(folder);args=['source-test','--source',str(root/'source'),'--inputs',str(root/'inputs'),'--out',str(root/'out')]
   prior_handlers={s:signal.getsignal(s)for s in(signal.SIGINT,signal.SIGTERM)}
   try:
    with mock.patch.object(sys,'argv',args),mock.patch.object(ns['uuid'],'uuid4',return_value=fixed),mock.patch.object(ns['subprocess'],'check_output',docker),mock.patch.object(ns['subprocess'],'run',return_value=types.SimpleNamespace(returncode=0)),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
     result=chosen()
   finally:
    for s,h in prior_handlers.items():signal.signal(s,h)
  self.assertEqual(result,1);self.assertTrue(observed_error)
  return next((v[0]for v in results if v is not None),None),observed_error[0]
 def bit(self,value):return value is not None and value['same_rejected_match']['known_public_Fedora44_UID_DNF_line']
 def test_actual_original_main_and_decode_both_same_primary_public_line(self):
  for stage in('live','installed'):
   finite,error=self.invoke(LINE,stage);self.assertTrue(self.bit(finite));self.assertEqual(finite['original_uart_stage'],stage)
   self.assertEqual(finite['original_source_site']['source_line'],139);self.assertFalse(finite['complete_uart_admitted'])
   self.obs.validate_finite(finite,self.sc_raw,self.helper_raw);self.assertNotIn('fedora-44-primary@',json.dumps(finite))
 def test_unknown_first_Match_and_complete_line_boundaries(self):
  for wire in(b'unknown@example.invalid\n'+LINE,b'prefix'+LINE,LINE.rstrip(b'\n'),LINE.replace(b' UserID',b'  UserID'),LINE.replace(b'Fedora (44)',b'Fedora (43)'),LINE.replace(b'\n',b'\r\n')):
   self.assertFalse(self.bit(self.invoke(wire)[0]))
 def test_source_transforms_foreign_original_globals_and_helper_drift(self):
  self.assertFalse(self.bit(self.invoke(b'\x1b[31m'+LINE)[0]));self.assertIsNone(self.invoke(LINE,foreign=True)[0])
  function=self.helper.diagnostic_known_public_Fedora44_UID_DNF_line_UI;code=function.__code__;function.__code__=code.replace()
  self.assertIsNone(self.invoke(LINE)[0]);function.__code__=code
 def test_typed_boolean_and_same_unknown_exception_args_never_exported(self):
  finite,error=self.invoke(LINE);self.assertTrue(self.bit(finite))
  for alias in(1,0,1.0,None,'true'):
   changed=json.loads(json.dumps(finite));changed['same_rejected_match']['known_public_Fedora44_UID_DNF_line']=alias
   with self.assertRaises(ValueError):self.obs.validate_finite(changed,self.sc_raw,self.helper_raw)
 def test_actual_optional_observation_never_formats_same_primary_args(self):
  finite,error=self.invoke(b'unknown@example.invalid\n',no_text_args=True)
  self.assertFalse(self.bit(finite));self.assertFalse(finite['actual_runtime_cause_proven'])
  self.assertNotIn('unknown@example',json.dumps(finite))
if __name__=='__main__':unittest.main(verbosity=2)
