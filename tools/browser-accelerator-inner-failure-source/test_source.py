import ast,base64,hashlib,inspect,json,os,subprocess,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent;DB='/tmp/arctic-final-functional-git-mdmg9v01/objects.git';BASE='4cf178c4a8cd5fb5e539b18d92b1a8db5c651b48'
def raw(role):return (HERE/(role+'.py')).read_bytes()
def module(role):
 m=types.ModuleType('actual_proposed_'+role);m.__file__=str(HERE/(role+'.py'));exec(compile(raw(role),m.__file__,'exec'),m.__dict__);return m

def error_from(action):
 try:action()
 except BaseException as error:return error
 raise AssertionError('expected failure')
def record(p,phase='unknown',reason='unknown'):
 return {'schema':'arctic-epiphany-producer-finite-failure-v1','status':'failed_unqualified','source_body_sha256':p.FAILURE_BODY_SHA256,'phase':phase,'reason':reason}
def line(p,v):return p.FAILURE_PREFIX+json.dumps(v,sort_keys=True,separators=(',',':')).encode()+b'\n'
class Controls(unittest.TestCase):
 def test_original_main_whole_signature_only_and_all_ownership_caps(self):
  meta=json.loads((HERE/'source-inverse.json').read_bytes());old=subprocess.check_output(['git','--git-dir',DB,'show',BASE+':'+meta['producer_original']['path']]);b=raw('producer');append=b.index(b'\n# Diagnostic observation only.')
  inv=b[:append]+b"if __name__=='__main__':main()\n"
  for a,z in meta['signature_literal_changes']:inv=inv.replace(z.encode(),a.encode())
  self.assertEqual(inv,old);ot=ast.parse(old);nt=ast.parse(b)
  for node in ot.body:
   if isinstance(node,(ast.FunctionDef,ast.Import,ast.ImportFrom)):
    other=next(v for v in nt.body if type(v)is type(node) and (getattr(v,'name',None)==getattr(node,'name',None)) and (ast.dump(v,include_attributes=False)==ast.dump(node,include_attributes=False) if not isinstance(node,ast.FunctionDef) else True))
    x=ast.get_source_segment(b.decode(),other)
    for a,z in meta['signature_literal_changes']:x=x.replace(z,a)
    self.assertEqual(x,ast.get_source_segment(old.decode(),node))
 def test_actual_signature_expression_exact_full_fingerprint_status_and_denials(self):
  p=module('producer');fn=next(v for v in ast.parse(raw('producer')).body if isinstance(v,ast.FunctionDef)and v.name=='main');node=next(v for v in ast.walk(fn) if isinstance(v,ast.Call)and isinstance(v.func,ast.Name)and v.func.id=='require'and len(v.args)>1 and isinstance(v.args[1],ast.Constant)and v.args[1].value=='producer_source_signature')
  code=compile(ast.fix_missing_locations(ast.Expression(node.args[0])),'actual_source_signature_guard','eval');fp=b'36f612dcf27f7d1a48a835e4dbfcf71c6d9f90a6'
  good=b'    Header V4 RSA/SHA256 Signature, key fingerprint: '+fp+b': OK\n'
  self.assertTrue(eval(code,dict(p.__dict__,verification=types.SimpleNamespace(returncode=0,stdout=good,stderr=b''))))
  for rc,out,err in [(1,good,b''),(0,good.replace(fp,b'0'*40),b''),(0,good.replace(b': OK',b': BAD'),b''),(0,good+b'NOKEY\n',b''),(0,good,b'NOT OK'),(0,b'    Payload SHA256 digest: OK\n',b''),(0,b'key ID 6d9f90a6: OK\n',b'')]:
   with self.subTest(rc=rc):self.assertFalse(eval(code,dict(p.__dict__,verification=types.SimpleNamespace(returncode=rc,stdout=out,stderr=err))))
 def test_actual_require_Source_owner_and_foreign_Code_globals_unknown(self):
  p=module('producer');actual=error_from(lambda:p.validate_context({}));self.assertEqual(p.finite_producer_failure(actual),('context','producer_context_schema'))
  foreign=dict(p.__dict__);cloned=types.FunctionType(p.validate_context.__code__.replace(),foreign)
  self.assertEqual(p.finite_producer_failure(error_from(lambda:cloned({}))),('unknown','unknown'))
  same=types.FunctionType(p.validate_context.__code__,foreign)
  self.assertEqual(p.finite_producer_failure(error_from(lambda:same({}))),('unknown','unknown'))
  class Opaque(RuntimeError):
   def __str__(self):raise AssertionError('opaque')
   def __repr__(self):raise AssertionError('opaque')
  self.assertEqual(p.finite_producer_failure(error_from(lambda:(_ for _ in ()).throw(Opaque('private-sentinel')))),('unknown','unknown'))
 def test_actual_subprocess_static_callsite_category_and_sameCode_foreignglobals(self):
  p=module('producer');primary=subprocess.CalledProcessError(1,['private-operand'],stderr=b'private-sentinel')
  def failed(*a,**k):raise primary
  with patch.object(p.subprocess,'check_output',side_effect=failed):
   actual=error_from(p.runtime_devel);self.assertIs(actual,primary);self.assertEqual(p.finite_producer_failure(actual),('environment_inventory','command_failed'))
   foreign=types.FunctionType(p.runtime_devel.__code__,dict(p.__dict__))
   other=error_from(foreign);self.assertEqual(p.finite_producer_failure(other),('unknown','unknown'))
 def test_marker_schema_catalog_duplicate_nul_private_suffix_denials(self):
  p=module('producer');v=record(p,'source_signature','producer_source_signature');good=line(p,v)
  self.assertEqual(p.parse_failure_record(b'opaque private child output\n'+good+b'opaque private traceback\n'),v)
  rejects=[good+good,good+p.FAILURE_PREFIX.rstrip(b' ')+b'\tmalformed\n',b'prefix '+good,good.replace(b'{',b'{"phase":"unknown",',1),good.replace(b'unknown',b'\x00',1) if b'unknown'in good else good.replace(b'source_signature',b'\x00',1),line(p,dict(v,reason='private-sentinel')),line(p,dict(v,source_body_sha256='0'*64)),line(p,dict(v,extra='private-sentinel')),good.rstrip(b'\n')+b' private-sentinel\n']
  for value in rejects:
   with self.subTest(case=rejects.index(value)):
    with self.assertRaises((RuntimeError,ValueError)):p.parse_failure_record(value)
 def test_one_owned_log_parse_failed_record_clears_previous_and_opaque_error(self):
  p=module('producer');r=module('runner')
  with tempfile.TemporaryDirectory(dir=HERE) as d:
   path=Path(d)/'private-producer.log';path.write_bytes(line(p,record(p)));path.chmod(0o600)
   reads=[];read=r.read_owned
   def observed(*args):reads.append(args);return read(*args)
   with patch.object(r,'read_owned',side_effect=observed):r.observe_producer_failure(p,path)
   self.assertEqual(len(reads),1);self.assertEqual(r.inner_failure_status,'source_record_observed');self.assertEqual(r.inner_failure_record,record(p))
   path.write_bytes(line(p,record(p))+line(p,record(p)))
   with patch.object(r,'read_owned',side_effect=observed):r.observe_producer_failure(p,path)
   self.assertIsNone(r.inner_failure_record);self.assertEqual(r.inner_failure_status,'unavailable');self.assertEqual(len(reads),2)
 def test_original_failed_command_exception_is_same_after_observation_SIGINT(self):
  r=module('runner');p=module('producer');fn=next(v for v in ast.parse(raw('runner')).body if isinstance(v,ast.FunctionDef)and v.name=='main');node=next(v for v in ast.walk(fn) if isinstance(v,ast.Try)and len(v.body)==1 and isinstance(v.body[0],ast.Expr) and isinstance(v.body[0].value,ast.Call) and isinstance(v.body[0].value.func,ast.Name) and v.body[0].value.func.id=='run' and [getattr(x,'id',None) for x in v.body[0].value.args]==['argv','tag','deadline'])
  compiled=compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),'actual_failure_handoff','exec');primary=subprocess.CalledProcessError(1,['owned-command'],stderr=b'private-sentinel')
  def failed(*a):raise primary
  with tempfile.TemporaryDirectory(dir=HERE) as d:
   g=dict(r.__dict__,run=failed,script='producer.py',producer=p,logs=Path(d),argv=['owned-command'],tag='producer',deadline=7000)
   with patch.dict(r.__dict__,read_owned=lambda *a:(_ for _ in ()).throw(KeyboardInterrupt())):
    actual=error_from(lambda:exec(compiled,g));self.assertIs(actual,primary);self.assertIsNone(r.inner_failure_record)
 def test_actual_finite_writer_private_source_screened_exclusive_output(self):
  r=module('runner');p=module('producer');mf=json.loads(subprocess.check_output(['git','--git-dir',DB,'show',BASE+':tools/browser-accelerator-host-armored-20261011/execution-manifest.json']))
  old='tools/browser-accelerator-armored-key-source/producer.py';new='tools/browser-accelerator-inner-failure-source/producer.py';mf['observer_files'][new]=hashlib.sha256(raw('producer')).hexdigest();del mf['observer_files'][old]
  scannerraw=subprocess.check_output(['git','--git-dir',DB,'show',BASE+':tools/native-functional/screen-evidence.py']);s=types.ModuleType('whole_original_scanner');exec(compile(scannerraw,'scanner','exec'),s.__dict__)
  r.inner_failure_status='source_record_observed';r.inner_failure_record=record(p,'source_signature','producer_source_signature')
  def tracked(root,name,*args):self.assertEqual(name,r.MANIFEST);return json.dumps(mf).encode()
  def loaded(root,name,*args):return p if name==new else s
  with tempfile.TemporaryDirectory(dir=HERE) as d,patch.dict(os.environ,RUNNER_TEMP=d),patch.object(r,'verify_tracked',side_effect=tracked),patch.object(r,'load_verified',side_effect=loaded):
   r.retain_finite_failure('producer_builds','owned_command_failed');f=Path(d)/'arctic-accelerator-ab-finite-failure/finite-failure.json';b=f.read_bytes();self.assertEqual(f.stat().st_mode&0o777,0o600);self.assertEqual(f.parent.stat().st_mode&0o777,0o700);self.assertEqual(s.external_text(b),b)
   value=json.loads(b);self.assertFalse(value['original_private_log_admission']);self.assertFalse(value['authenticated_runtime_frame_attribution']);self.assertFalse(value['build_performance_release_acceptance'])
   with self.assertRaises(FileExistsError):r.retain_finite_failure('producer_builds','owned_command_failed')
 def test_untouched_host_functions_primary_cleanup_caps_and_success_recipe(self):
  old=subprocess.check_output(['git','--git-dir',DB,'show',BASE+':tools/browser-accelerator-host-armored-20261011/runner.py']);ot=ast.parse(old);nt=ast.parse(raw('runner'))
  for node in ot.body:
   if isinstance(node,ast.FunctionDef)and node.name!='main':
    actual=next(n for n in nt.body if isinstance(n,ast.FunctionDef)and n.name==node.name);self.assertEqual(ast.dump(node,include_attributes=False),ast.dump(actual,include_attributes=False))
  recipe=(HERE/'failure-upload-recipe.yml').read_text();self.assertIn('if: failure()',recipe);self.assertIn('finite-failure.json',recipe);self.assertNotIn('producer.log',recipe)
if __name__=='__main__':unittest.main()
