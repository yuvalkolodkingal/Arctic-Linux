"""Focused actual Source composition controls; synthetic evidence only."""
import contextlib,hashlib,importlib.util,io,json,sys,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def module(path,name):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
H=module(HERE/'composition.py','public_shape_test_composer')
C=module(HERE/'common.py','public_shape_test_common')
class Controls(unittest.TestCase):
 def value(self):return C.strict_json((HERE/'execution-manifest.json').read_bytes())
 def build(self,value=None):
  value=self.value()if value is None else value
  def loader(path,expected):
   raw=path.read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),expected);return raw
  return H.build(ROOT,value,loader,lambda *a:None)
 def records(self,raw,mutate=None):
  wrapped,observed,original,state=self.build()
  if mutate:mutate(observed,state)
  with tempfile.TemporaryDirectory()as folder:
   vm=Path(folder);(vm/'serial-install.log').write_bytes(raw);(vm/'serial-boot.log').write_bytes(b'public\n')
   caught=[]
   def tracer(frame,event,arg):
    if event=='exception'and frame.f_code.co_name=='reject_sensitive_match':caught.append(arg[1])
    return tracer
   old=sys.gettrace()
   try:
    sys.settrace(tracer)
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(RuntimeError)as raised:
     observed.__globals__['original_evidence'](vm,{},'0'*64)
   finally:sys.settrace(old)
   self.assertEqual(len(caught),1);self.assertIs(raised.exception,caught[0])
  return state['strict']['finite'],state
 def test_exact_original_main_code_and_disabled_admission(self):
  value=self.value();C.manifest(value)
  with self.assertRaises(RuntimeError):C.manifest(value,True)
  wrapped,observed,original,state=self.build()
  self.assertIs(wrapped.__code__,original.__code__);self.assertIs(observed.__code__,original.__code__)
  self.assertEqual(state['mapping'],C.SCANNER_BINDING);self.assertEqual(state['public_shape_mapping'],C.PUBLIC_SHAPE_BINDING)
  self.assertFalse(state['release_acceptance']);self.assertFalse(state['runtime_cause_proven'])
  for b in state['Source_boundaries']:self.assertIs(b.function.__code__,b.code)
 def test_actual_original_records_same_exception_and_known_literal(self):
  finite,state=self.records(b' user-runtime-dir@1000.service \n')
  self.assertTrue(finite['actual_raising_Source_Code_globals_owned'])
  self.assertEqual(finite['original_source_site']['source_sha256'],H.SELECTED_SHA)
  self.assertEqual(finite['original_source_site']['source_line'],139)
  self.assertEqual(finite['original_records_stage'],'live')
  shape=finite['same_rejected_match']['public_source_shape']
  self.assertEqual(shape['canonical_unit_id'],'unit-008');self.assertTrue(shape['same_source_match_aligned'])
  self.assertFalse(shape['privacy_admitted']);self.assertFalse(shape['runtime_cause_proven'])
 def test_actual_complete_osc_shape_is_observation_not_admission(self):
  frame=(b'\x1b]3008;start='+b'a'*32+b';user=root;hostname=arctic-ci;machineid='+b'b'*32+b';bootid='+b'c'*32+b';pid=123;pidfdid=456;comm=(agetty);servicename=user-runtime-dir@1000.service;invocationid='+b'd'*32+b';type=service\x1b\\')
  finite,_=self.records(frame);shape=finite['same_rejected_match']['public_source_shape']
  self.assertTrue(shape['osc3008_complete_bounded_frame']);self.assertTrue(shape['match_equals_servicename_field'])
  self.assertEqual(shape['canonical_unit_id'],'unit-008');self.assertFalse(shape['current_scanner_service_schema'])
  self.assertFalse(shape['privacy_admitted'])
 def test_unknown_and_affixed_tokens_do_not_export_values_or_ids(self):
  for raw in(b'private@example.invalid\n',b' user-runtime-dir@1000.service7 \n'):
   finite,_=self.records(raw);shape=finite['same_rejected_match']['public_source_shape']
   self.assertEqual(shape['canonical_unit_id'],'unknown');encoded=json.dumps(finite)
   self.assertNotIn('private@example',encoded);self.assertNotIn('operand_sha256',encoded)
 def test_optional_observer_fault_preserves_original_primary(self):
  def mutate(observed,state):
   helper=observed.__globals__['original_evidence'].__closure__
   # The exact helper object is held by the describe closure. A changed function
   # makes its OwnedSource guard decline observation; it must not replace error.
   staged=H.cell(observed.__globals__['original_evidence'],'helper')
   staged.diagnostic_public_source_shape=lambda *a:(_ for _ in()).throw(OSError('synthetic Source-only fault'))
  finite,_=self.records(b' user-runtime-dir@1000.service ',mutate)
  self.assertIsNone(finite)
 def test_foreign_scanner_calls_and_whole_source_drift_deny(self):
  wrapped,observed,original,state=self.build()
  with self.assertRaises(RuntimeError):wrapped.__globals__['C'].load(ROOT/H.ORIGINAL_PATH,'bios_host_screen',H.ORIGINAL_SHA)
  for role in('observer','helper'):
   value=self.value();path=value['public_shape_binding']['selected_'+role+'_path'];value['execution_files'][path]='0'*64
   with self.subTest(role=role),self.assertRaises(AssertionError):self.build(value)
 def test_typed_public_shape_binding_and_original_gate_projection(self):
  for key,changed in(('runtime_cause_proven',0),('selected_helper_sha256','0'*64),('selected_observer_path','tools/final-bios-strict-screen-observer/observer.py')):
   value=self.value();value['public_shape_binding'][key]=changed
   with self.subTest(key=key),self.assertRaises(RuntimeError):C.manifest(value)
   with self.subTest(key=key),self.assertRaises(RuntimeError):self.build(value)
  wrapped,_,_,_=self.build();admission=wrapped.__globals__['C']
  old=admission.manifest(admission.strict_json((ROOT/'tools/final-bios-install/execution-manifest.json').read_bytes()),True)
  self.assertIsNone(admission.guard(old,Path('/synthetic-Source-only')))
  for key,changed in(('install_timeout',2401),('harness_seconds',6601),('boot_network','online')):
   with self.subTest(key=key),self.assertRaises(RuntimeError):admission.guard(dict(old,**{key:changed}),Path('/synthetic-Source-only'))
 def test_existing_public_scanner_frame_and_private_neighbor_gates_exact(self):
  _,_,original,_=self.build();scanner=H.cell(original.__globals__['execute'],'scanner')
  frame=(b'\x1b]3008;start='+b'a'*32+b';user=root;hostname=arctic-ci;machineid='+b'b'*32+b';bootid='+b'c'*32+b';pid=123;pidfdid=456;comm=(agetty);servicename=serial-getty@ttyS0.service;invocationid='+b'd'*32+b';type=service\x1b\\')
  self.assertEqual(scanner.external_text(frame),frame)
  for raw in(frame+b'\npassword=synthetic\n',frame.replace(b'arctic-ci',b'foreign-host'),frame.replace(b'pid=123;',b'pid=2147483648;')):
   with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(RuntimeError):scanner.external_text(raw)
if __name__=='__main__':unittest.main(verbosity=2)
