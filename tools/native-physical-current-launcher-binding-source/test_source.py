import copy,hashlib,inspect,json,pathlib,tempfile,types,unittest
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parents[1];OUT=ROOT/'out'
CURRENT='8dd43bfd2df74c619efa65ef272345fc8517ffd619ecb54a40edfb3aab0cc4a3'
LEGACY='e948f2ff9c7273f20b0d42e67cc891e3a3f6e0954dfc1ac3afca2aa7c3d7df4c'
CHECKER='15a065ae8ea95b918b973918534361b1b49de268db09d85cc96f2a4136595b3c'
BOOT='11111111-2222-3333-4444-555555555555'
MANIFEST=json.loads((HERE/'source-manifest.json').read_bytes())
def load(path,digest):
 raw=path.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Source whole pin differs')
 m=types.ModuleType('owned_Source_'+path.stem);m.__file__=str(path);exec(compile(raw,str(path),'exec',dont_inherit=True,optimize=0),m.__dict__);return m
OLD=load(OUT/'source-only-original-controller.py',MANIFEST['original_controller']['sha256'])
NEW=load(HERE/'physical-controller.py',MANIFEST['selected_mirror']['sha256'])
def records(editor=False,launcher=CURRENT):
 root='/tmp/arctic-native-smoke-SourceFixture';path=root+'/files with spaces/editor fixture.txt'if editor else root+'/files with spaces'
 uid=1000;app='featherpad'if editor else'pcmanfm';exe='/usr/bin/'+app
 req=dict(schema='arctic-native-editor-save-v1'if editor else'arctic-native-pcmanfm-physical-v1',stage='live',nonce='a'*32,boot_id=BOOT,desktop_uid=uid,
 process=dict(pid=123,start_ticks=456,uid=uid,executable=exe,is_xwayland=False,client_id='7',executable_sha256='b'*64),
 client=dict(pid=123,id=7,is_focused=True,is_visible=True,is_xwayland=False,appid=app,title=path if editor else'Files',foreign_toplevel_id='SourceFixture'),
 action='save-editor'if editor else'navigate',path=path,evidence_root=root,monotonic_ns=20,client_monotonic_ns=10,release_acceptance=False,accessibility_proof=False)
 begin=dict(stage='live',checker_sha256=CHECKER,release_acceptance=False)
 gone=dict(stage='live',boot_id=BOOT,launcher_sha256=launcher,owned_launcher_gone=True,foot={'uid':uid},shell={'uid':uid},probe={'uid':0})
 return req,begin,gone

def text(req,begin,gone,editor=False):
 return ''.join(prefix+json.dumps(value,sort_keys=True)+'\n'for prefix,value in [('ARCTIC-NATIVE-RUNNER-BEGIN ',begin),('ARCTIC-NATIVE-LAUNCHER-GONE ',gone),('ARCTIC-NATIVE-EDITOR-PHYSICAL 'if editor else'ARCTIC-NATIVE-PCMANFM-PHYSICAL ',req)])
class BeforeFirstQMP(BaseException):pass
class ActualBindingDenied(BaseException):pass
class VM:
 def __init__(self,root,module,*,error=False,boundary=True):self.root=root;self.module=module;self.error=error;self.boundary=boundary;self.calls=[];self.probes=[]
 def alive(self):self.probes.append('alive');return True
 def shot(self,label):
  self.probes.append('shot');p=self.root/'SourceSyntheticCapture';p.write_bytes(b'owned Source synthetic pixels, no original or VM');return str(p)
 def cmd(self,command,**kwargs):
  frame=inspect.currentframe().f_back
  if frame.f_code is not self.module.Controller.press.__code__ or frame.f_globals is not self.module.__dict__:raise ActualBindingDenied()
  self.calls.append((command,kwargs))
  if self.boundary:raise BeforeFirstQMP()
  return {'error':{}}if self.error else{'return':{}}

class SourceControls(unittest.TestCase):
 def setup_case(self,module,root,editor=False,**kwargs):
  vm=VM(root,module,**kwargs);cls=module.EditorSaveController if editor else module.Controller
  c=cls(vm,root,'live',CHECKER,clock=lambda:1.0,sleep=lambda n:None,chord_for=lambda ch:[ch]);return c,vm
 def test_actual_original_both_current_requests_reject_before_VM_or_QMP(self):
  for editor in(False,True):
   with self.subTest(editor=editor),tempfile.TemporaryDirectory(dir=OUT)as d:
    c,v=self.setup_case(OLD,pathlib.Path(d),editor);r,b,g=records(editor)
    with self.assertRaisesRegex(RuntimeError,'physical same-boot/UID launcher absent'if not editor else'editor same-boot launcher absent'):c.poll(text(r,b,g,editor))
    self.assertEqual(v.probes,[]);self.assertEqual(v.calls,[]);self.assertEqual(c.used,{})
 def test_actual_corrected_both_current_requests_reach_original_first_QMP_boundary(self):
  for editor in(False,True):
   with self.subTest(editor=editor),tempfile.TemporaryDirectory(dir=OUT)as d:
    c,v=self.setup_case(NEW,pathlib.Path(d),editor);r,b,g=records(editor)
    with self.assertRaises(BeforeFirstQMP):c.poll(text(r,b,g,editor))
    self.assertEqual(len(v.calls),1);self.assertEqual(v.calls[0][0],'input-send-event');self.assertEqual(len(c.used),1)
    keys=[x['data']['key']['data']for x in v.calls[0][1]['events']];self.assertEqual(keys,['ctrl','s','s','ctrl']if editor else['ctrl','l','l','ctrl'])
    c.poll(text(r,b,g,editor));self.assertEqual(len(v.calls),1)
 def test_corrected_legacy_identity_refused_before_VM_and_QMP(self):
  for editor in(False,True):
   with self.subTest(editor=editor),tempfile.TemporaryDirectory(dir=OUT)as d:
    c,v=self.setup_case(NEW,pathlib.Path(d),editor);r,b,g=records(editor,LEGACY)
    with self.assertRaises(RuntimeError):c.poll(text(r,b,g,editor))
    self.assertEqual(v.probes,[]);self.assertEqual(v.calls,[]);self.assertEqual(c.used,{})
 def test_original_sameboot_UID_nonce_focus_checker_and_time_gates_still_deny(self):
  for editor in(False,True):
   for mutation in('boot','uid','nonce','focus','checker','time'):
    with self.subTest(editor=editor,mutation=mutation),tempfile.TemporaryDirectory(dir=OUT)as d:
     c,v=self.setup_case(NEW,pathlib.Path(d),editor);r,b,g=records(editor)
     if mutation=='boot':g['boot_id']='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
     elif mutation=='uid':g['foot']['uid']=1001
     elif mutation=='nonce':r['nonce']='invalid'
     elif mutation=='focus':r['client']['is_focused']=False
     elif mutation=='checker':b['checker_sha256']='c'*64
     else:r['monotonic_ns']=2_000_000_000
     with self.assertRaises(RuntimeError):c.poll(text(r,b,g,editor))
     self.assertEqual(v.probes,[]);self.assertEqual(v.calls,[])
 def test_strict_original_QMP_response_and_oneuse_survive_repair(self):
  for editor in(False,True):
   with self.subTest(editor=editor),tempfile.TemporaryDirectory(dir=OUT)as d:
    c,v=self.setup_case(NEW,pathlib.Path(d),editor,error=True,boundary=False);r,b,g=records(editor)
    with self.assertRaisesRegex(RuntimeError,'strict physical QMP Return failed'):c.poll(text(r,b,g,editor))
    self.assertEqual(len(v.calls),1);self.assertEqual(len(c.used),1)
    c.poll(text(r,b,g,editor));self.assertEqual(len(v.calls),1)
 def test_source_pin_drift_denies_before_import_and_actual_callback_checks_foreign_globals(self):
  with tempfile.TemporaryDirectory(dir=OUT)as d:
   root=pathlib.Path(d);p=root/'changed-Source.py';p.write_bytes((HERE/'physical-controller.py').read_bytes()+b'\n')
   with self.assertRaises(ValueError):load(p,MANIFEST['selected_mirror']['sha256'])
   c,v=self.setup_case(NEW,root);r,b,g=records();fn=NEW.Controller.press;c.press=types.MethodType(types.FunctionType(fn.__code__,dict(fn.__globals__),fn.__name__,fn.__defaults__,fn.__closure__),c)
   with self.assertRaises(ActualBindingDenied):c.poll(text(r,b,g))
   self.assertEqual(v.calls,[])
if __name__=='__main__':unittest.main(verbosity=2)
