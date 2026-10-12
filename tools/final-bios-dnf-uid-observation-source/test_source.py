import ast,contextlib,hashlib,io,json,pathlib,subprocess,sys,types,unittest
HERE=pathlib.Path(__file__).resolve().parent
BASE='da8bf13b4c207621fd1280ec7d02df777b6c4c5e'
DB='/tmp/arctic-final-functional-git-mdmg9v01/objects.git'
LINE=' UserID     : "Fedora (44) <fedora-44-primary@fedoraproject.org>"\n'
def raw(name):return subprocess.check_output(['git','--git-dir='+DB,'show',BASE+':'+name])
def module(content,path,name):
 m=types.ModuleType(name);m.__file__=path;exec(compile(content,path,'exec',optimize=0),m.__dict__);return m
class SourceControls(unittest.TestCase):
 def setUp(self):
  self.obs=module((HERE/'observer.py').read_bytes(),str(HERE/'observer.py'),'new_observer')
  self.helper_raw=(HERE/'match-diagnostic.py').read_bytes();self.helper=module(self.helper_raw,str(HERE/'match-diagnostic.py'),'new_helper')
  self.sc_raw=raw('tools/bounded-complete-csi-source/scanner.py');self.sc=module(self.sc_raw,'tools/bounded-complete-csi-source/scanner.py','selected_scanner')
  self.c_raw=raw('tools/final-bios-install/common.py');self.c=module(self.c_raw,'tools/final-bios-install/common.py','original_common')
  saved={n:(n in sys.modules,sys.modules.get(n))for n in ('common','compose')}
  sys.modules['common']=self.c
  self.compose_raw=raw('tools/final-bios-install/compose.py');self.compose=module(self.compose_raw,'tools/final-bios-install/compose.py','original_compose');sys.modules['compose']=self.compose
  self.run_raw=raw('tools/final-bios-install/run.py')
  try:self.run=module(self.run_raw,'tools/final-bios-install/run.py','original_run')
  finally:
   for n,(present,value)in saved.items():
    if present:sys.modules[n]=value
    else:sys.modules.pop(n,None)
  O=self.obs.OwnedSource
  self.run_owner=O(self.run.__dict__,self.run_raw,self.run.__file__,'bios-host')
  self.c_owner=O(self.c.__dict__,self.c_raw,self.c.__file__,'bios-common')
  self.sc_owner=O(self.sc.__dict__,self.sc_raw,self.sc.__file__,'original-scanner')
  self.helper_owner=O(self.helper.__dict__,self.helper_raw,self.helper.__file__,'match-diagnostic')
  self.vocab=frozenset({n.value for n in ast.walk(ast.parse(self.helper_raw))if isinstance(n,ast.Constant)and type(n.value)is str}|{'external-rule-'+format(n,'03d')for n in range(1,11)})
 def caught(self,content,stage='live',foreign=False,direct=False):
  with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
   try:
    if direct:self.sc.external_text(content)
    elif foreign:types.FunctionType(self.run.records.__code__,self.run.__dict__.copy())(content,{},stage,'a'*64,self.sc)
    else:self.run.records(content,{},stage,'a'*64,self.sc)
   except RuntimeError as error:
    before=(error,error.__traceback__)
    result=self.obs.describe(error,(self.run_owner,),self.c_owner,[(self.sc,self.sc_owner)],self.helper,self.helper_owner,self.vocab,(self.c,))
    self.assertIs(error,before[0]);self.assertIs(error.__traceback__,before[1]);return result,error
  self.fail('original scanner unexpectedly admitted synthetic evidence')
 def bit(self,result):
  return result['same_rejected_match']['known_public_Fedora44_UID_DNF_line'] if result is not None and result['same_rejected_match']is not None else False
 def test_actual_original_records_both_stages_same_primary(self):
  for stage in ('live','installed'):
   result,error=self.caught(LINE.encode(),stage);self.assertTrue(self.bit(result));self.assertEqual(result['original_records_stage'],stage)
   self.assertEqual(result['original_source_site']['source_line'],139);self.assertFalse(result['same_rejected_match']['privacy_admitted'])
 def test_actual_first_rejection_unknown_and_full_line_boundaries(self):
  for value in ('prefix'+LINE,LINE.replace(' UserID','  UserID'),LINE.rstrip('\n'),LINE.replace('>"','>" private'),
                'unknown@example.invalid\n'+LINE,LINE.replace('primary@','primary_extra@'),LINE.replace('Fedora (44)','Fedora (43)'),LINE.replace('\n','\r\n')):
   with self.subTest(shape=value==LINE):self.assertFalse(self.bit(self.caught(value.encode())[0]))
  result,error=self.caught((LINE+'unknown@example.invalid\n').encode());self.assertTrue(self.bit(result));self.assertIs(type(error),RuntimeError)
 def test_raw_escape_transforms_cannot_borrow_exact_public_line(self):
  for value in ('\x1b[31m'+LINE,LINE.replace('primary@','pri\x1b[31mmary@'),LINE.replace('Fedora (44)','Fedora \x1b[0m(44)'),LINE.replace(' UserID',' UserID\t')):
   self.assertFalse(self.bit(self.caught(value.encode())[0]))
 def test_original_records_wrong_or_type_spoof_role_denied(self):
  class Alias(str):
   def __eq__(self,other):return True
  for stage in ('unknown',True,Alias('live')):
   self.assertFalse(self.bit(self.caught(LINE.encode(),stage)[0]))
 def test_actual_foreign_records_or_no_records_parent_denied(self):
  self.assertFalse(self.bit(self.caught(LINE.encode(),foreign=True)[0]));self.assertFalse(self.bit(self.caught(LINE.encode(),direct=True)[0]))
 def test_actual_new_helper_Code_or_global_drift_no_observation(self):
  original=self.helper.diagnostic_known_public_Fedora44_UID_DNF_line
  code=original.__code__;original.__code__=code.replace();self.assertIsNone(self.caught(LINE.encode())[0]);original.__code__=code
  self.helper.diagnostic_known_public_Fedora44_UID_DNF_line=types.FunctionType(code,self.helper.__dict__.copy())
  self.assertIsNone(self.caught(LINE.encode())[0])
 def test_same_unknown_exception_args_never_formatted_and_scanner_unchanged(self):
  result,error=self.caught(b'unknown@example.invalid\n');self.assertFalse(self.bit(result))
  class Forbidden:
   def __repr__(self):raise AssertionError('synthetic operand repr must not execute')
   def __str__(self):raise AssertionError('synthetic operand str must not execute')
  error.args=(Forbidden(),)
  result=self.obs.describe(error,(self.run_owner,),self.c_owner,[(self.sc,self.sc_owner)],self.helper,self.helper_owner,self.vocab,(self.c,))
  self.assertFalse(self.bit(result));serialized=json.dumps(result);self.assertNotIn('unknown@example',serialized)
  self.assertTrue(self.sc_owner.unchanged());self.assertTrue(self.run_owner.unchanged())
if __name__=='__main__':unittest.main(verbosity=2)
