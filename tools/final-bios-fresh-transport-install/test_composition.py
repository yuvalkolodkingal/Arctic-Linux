"""Actual composed Source controls; synthetic bytes, no ISO or VM."""
import contextlib,hashlib,importlib.util,io,json,sys,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def module(path,name):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
H=module(HERE/'composition.py','dnf_uid_test_composer')
C=module(HERE/'common.py','dnf_uid_test_common')
class Controls(unittest.TestCase):
 def value(self):return C.strict_json((HERE/'execution-manifest.json').read_bytes())
 def build(self,value=None):
  value=self.value()if value is None else value
  def loader(path,expected):
   raw=path.read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),expected);return raw
  return H.build(ROOT,value,loader,lambda *a:None)
 def records(self,raw):
  wrapped,observed,original,state=self.build()
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
 def test_original_program_code_and_disabled_gate_stay_exact(self):
  value=self.value();C.manifest(value)
  with self.assertRaises(RuntimeError):C.manifest(value,True)
  wrapped,observed,original,state=self.build()
  self.assertIs(wrapped.__code__,original.__code__);self.assertIs(observed.__code__,original.__code__)
  self.assertEqual(state['mapping'],C.SCANNER_BINDING);self.assertEqual(state['public_shape_mapping'],C.PUBLIC_SHAPE_BINDING)
  for boundary in state['Source_boundaries']:self.assertIs(boundary.function.__code__,boundary.code)
  self.assertFalse(state['release_acceptance']);self.assertFalse(state['runtime_cause_proven'])
 def test_actual_selected_execute_scanner_corrects_boundary_but_denies_private(self):
  _,_,original,_=self.build();scanner=H.cell(original.__globals__['execute'],'scanner')
  control=b'\x1b[1A@public.example\n'
  self.assertEqual(scanner.external_text(control),control)
  for raw in(control+b'private@example.invalid\n',b'private@\x1b[1@public.example\n',b'\x1b]0;private@example.invalid\x07',b'\x1bPprivate@example.invalid\x1b\\'):
   with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(RuntimeError):scanner.external_text(raw)
 def test_same_original_reject_maps_after_corrected_csi_with_no_private_export(self):
  finite,state=self.records(b'\x1b[1@public.example\n private@example.invalid\n')
  self.assertTrue(finite['actual_raising_Source_Code_globals_owned'])
  self.assertEqual(finite['original_source_site']['source_sha256'],H.SELECTED_SHA)
  self.assertEqual(finite['original_source_site']['source_line'],139)
  row=finite['same_rejected_match'];self.assertEqual(row['offsets'],'exact-scanner-span')
  self.assertTrue(row['public_source_shape']['same_source_match_aligned'])
  self.assertEqual(row['public_source_shape']['canonical_unit_id'],'unknown')
  encoded=json.dumps(finite);self.assertNotIn('private@example',encoded);self.assertNotIn('operand_sha256',encoded)
 def test_new_source_maps_require_exact_typed_scanner_and_helper_pins(self):
  for group,key,changed in(('scanner_binding','raw_member_bytes_preserved',1),('public_shape_binding','runtime_cause_proven',0),('scanner_binding','selected_sha256','0'*64),('public_shape_binding','selected_helper_sha256','0'*64)):
   value=self.value();value[group][key]=changed
   with self.subTest(group=group,key=key),self.assertRaises(RuntimeError):C.manifest(value)
   with self.subTest(group=group,key=key),self.assertRaises(RuntimeError):self.build(value)
  for group in('scanner_binding','public_shape_binding'):
   value=self.value();path=value[group]['selected_path'if group=='scanner_binding'else'selected_helper_path'];value['execution_files'][path]='0'*64
   with self.subTest(group=group),self.assertRaises(AssertionError):self.build(value)
class NewJoins(Controls):
 def test_selected_original_records_add_only_same_match_fixed_bit(self):
  public=b' UserID     : "Fedora (44) <fedora-44-primary@fedoraproject.org>"\n'
  for raw,expected in((public,True),(b'unknown@example.invalid\n'+public,False),(public.replace(b' UserID',b'  UserID'),False)):
   finite,state=self.records(raw)
   row=finite['same_rejected_match'];self.assertIs(row['known_public_Fedora44_UID_DNF_line'],expected)
   self.assertFalse(row['privacy_admitted']);self.assertFalse(finite['actual_runtime_cause_proven'])
   encoded=json.dumps(finite);self.assertNotIn('fedora-44-primary@',encoded);self.assertNotIn('unknown@example',encoded)
 def test_actual_mapped_publish_preserves_finite_bit_without_admitting_uart(self):
  public=b' UserID     : "Fedora (44) <fedora-44-primary@fedoraproject.org>"\n'
  wrapped,observed,original,state=self.build()
  with tempfile.TemporaryDirectory()as folder:
   out=Path(folder);vm=out/'vm';vm.mkdir();(vm/'serial-install.log').write_bytes(public);(vm/'serial-boot.log').write_bytes(b'public\n')
   with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(RuntimeError):observed.__globals__['original_evidence'](vm,{},'0'*64)
   (out/'private').mkdir()
   status={'status':'failed','phase':'strict-original-evidence','context':{}}
   wrapped.__globals__['publish'](out,{'host-status.json':(json.dumps(status)+'\n').encode()})
   emitted=json.loads((out/'public/host-status.json').read_bytes())
   self.assertTrue(emitted['strict_original_Source_failure']['same_rejected_match']['known_public_Fedora44_UID_DNF_line'])
   self.assertEqual(set(p.name for p in(out/'public').iterdir()),{'host-status.json'})
   self.assertNotIn('fedora-44-primary@',json.dumps(emitted))
 def test_disabled_original_route_and_new_selected_map_type_aliases(self):
  self.test_original_program_code_and_disabled_gate_stay_exact()
  for key,changed in(('one_fixed_boolean_only',1),('privacy_allowance',0),('selected_observer_sha256','0'*64)):
   value=self.value();value['public_shape_binding'][key]=changed
   with self.assertRaises(RuntimeError):C.manifest(value)
   with self.assertRaises(RuntimeError):self.build(value)
if __name__=='__main__':unittest.main(verbosity=2)
