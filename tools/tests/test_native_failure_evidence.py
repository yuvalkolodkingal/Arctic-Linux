import ast,hashlib,importlib.util,io,json,os,signal,subprocess,sys,tempfile,types,unittest,zlib
from pathlib import Path
from unittest.mock import patch
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
NATIVE=ROOT/'tools/native-functional'
sys.path.insert(0,str(NATIVE))
import failure_evidence as F
import runner as R
import evidence as E
def scanner():
 m=types.ModuleType('owned_original_Native_scanner');m.__file__=str(NATIVE/'screen-evidence.py');exec(compile((NATIVE/'screen-evidence.py').read_bytes(),m.__file__,'exec'),m.__dict__);return m
def stop():return dict(schema='arctic-native-harness-stop-v1',phase='install',qemu_returncode=1,elapsed_seconds=1.0,deadline_seconds=2400,deadline_reached=False,exit_marker_present=False,reason='process-exited',release_acceptance=False)
def host():return dict(schema='arctic-native-host-observation-v1',status='failed',milestones=['harness-execution'],handled_failures=[],error_class='runtime-error',guard_site='unknown',Source_Code_globals_direct_guard_binding=False,runtime_cause=False,VM_input_or_PAM_ownership=False,runtime_acceptance=False,release_acceptance=False)
def put(path,value):
 path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(value if type(value) is bytes else (json.dumps(value,sort_keys=True)+'\n').encode());path.chmod(0o600)
def registry():
 return F.Registry(R,(NATIVE/'runner.py').read_bytes(),F.sha((NATIVE/'runner.py').read_bytes()),E,(NATIVE/'evidence.py').read_bytes(),F.sha((NATIVE/'evidence.py').read_bytes()))
class Context:
 def __enter__(self):return self
 def __exit__(self,*args):return False
 def milestone(self,*args):pass
 def handled(self,*args):pass
class Controls(unittest.TestCase):
 def test_actual_original_privacy_failure_keeps_primary_and_new_partial_host_status(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);raw=root/'originals';raw.mkdir();target=root/'uploaded';put(raw/F.HOST,host());put(raw/'harness/native-stop-install.json',stop());put(raw/'harness/serial-boot.log',b'owned-secret@example.invalid\n');s=scanner()
   with self.assertRaisesRegex(RuntimeError,'Sensitive text in external evidence'):F.screen_with_partial(raw,target,s)
   self.assertEqual((target/F.HOST).read_bytes(),(raw/F.HOST).read_bytes());self.assertEqual((target/'harness/native-stop-install.json').read_bytes(),(raw/'harness/native-stop-install.json').read_bytes());self.assertFalse((target/'harness/serial-boot.log').exists())
   status=json.loads((target/'incomplete-evidence.json').read_bytes());self.assertFalse(status['complete']);self.assertFalse(status['whole_original_transport_acceptance']);self.assertTrue(status['host_observation_retained']);self.assertFalse(status['release_acceptance'])
   ledger=json.loads((target/'upload-screening.json').read_bytes())
   for name,row in ledger['files'].items():
    payload=(target/name).read_bytes();self.assertEqual(row['original_sha256'],row['uploaded_sha256']);self.assertEqual(F.sha(payload),row['original_sha256']);self.assertEqual(zlib.crc32(payload)&0xffffffff,row['crc32']);self.assertEqual(row['redactions'],0)
 def test_invalid_PNG_rejected_while_safe_host_survives_no_rejected_hash_or_length(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);raw=root/'originals';raw.mkdir();target=root/'uploaded';put(raw/F.HOST,host());bad=b'\x89PNG\r\n\x1a\nowned-malformed-private';put(raw/'harness/boot-41-login.png',bad)
   status=F.partial_screen(raw,target,scanner(),ocr=lambda *args:None);self.assertEqual(status['fixed_member_states']['screen-installed-login'],'rejected');self.assertTrue(status['host_observation_retained']);self.assertFalse((target/'harness/boot-41-login.png').exists());self.assertNotIn(F.sha(bad),(target/'upload-screening.json').read_text())
 def test_same_original_PNG_CRC_decode_and_three_OCR_modes_preserve_full_rejection(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'image.png';Image.new('RGB',(1280,720),'black').save(p);raw=p.read_bytes();self.assertEqual(F.original_png(raw),[1280,720]);modes=[]
   def run(argv,**kw):
    modes.append(argv[-1]);self.assertIs(kw['input'],raw);return types.SimpleNamespace(returncode=0,stdout=b'owned-private@example.invalid\n',stderr=b'')
   with patch.object(F.subprocess,'run',run),patch.dict(F.os.environ,{},clear=True):
    with self.assertRaises(ValueError):F.ocr_original(scanner(),raw)
   self.assertEqual(modes,['3'])
   def safe(argv,**kw):modes.append(argv[-1]);return types.SimpleNamespace(returncode=0,stdout=b'Arctic\n',stderr=b'')
   modes=[]
   with patch.object(F.subprocess,'run',safe),patch.dict(F.os.environ,{},clear=True):F.ocr_original(scanner(),raw)
   self.assertEqual(modes,['3','6','11'])
 def test_unknown_shapes_duplicate_nonfinite_and_false_acceptance_denied(self):
  for value in (dict(host(),credential='owned-private-value'),dict(host(),release_acceptance=True),dict(host(),guard_site='unknown-operands'),dict(host(),guard_site='native-runner-require-999',Source_Code_globals_direct_guard_binding=True),dict(host(),milestones=['foreign-source-phase'])):
   with self.assertRaises(ValueError):F.closed_host(value)
  for raw in (b'{"a":1,"a":2}',b'{"a":NaN}'):
   with self.assertRaises(ValueError):F.strict_json(raw)
  bad=stop();bad['qemu_returncode']=True
  with self.assertRaises(ValueError):F.stop_shape(json.dumps(bad).encode(),'install')
 def test_actual_guard_registry_known_metadata_reassignment_and_changed_type_or_value_deny(self):
  old={name:getattr(R.R,name,F.ABSENT) for name in ('SOURCE','ISO','ISO_BYTES','ISO_SHA256','ORIGINAL_RUN')}
  try:
   for name,value in {'SOURCE':'a'*40,'ISO':'Arctic-Linux-1.2-candidate-1-1-x86_64.iso','ISO_BYTES':100,'ISO_SHA256':'b'*64,'ORIGINAL_RUN':1}.items():setattr(R.R,name,value)
   held=registry()
   try:R.R.execute([],Path('/owned-unused.log'),1,Path('/owned'),{},'foreign-container')
   except RuntimeError as error:actual=error
   self.assertRegex(held.describe(actual),r'^native-runner-require-[0-9]{3}$')
   R.R.SOURCE=(' '+R.R.SOURCE)[1:];self.assertRegex(held.describe(actual),r'^native-runner-require-[0-9]{3}$')
   R.R.ISO_BYTES=True;self.assertIsNone(held.describe(actual));R.R.ISO_BYTES=101;self.assertIsNone(held.describe(actual))
  finally:
   for name,value in old.items():
    if value is F.ABSENT:delattr(R.R,name)
    else:setattr(R.R,name,value)
 def test_actual_run_preserves_primary_when_optional_state_write_raises_second_error(self):
  with tempfile.TemporaryDirectory() as folder:
   evidence=Path(folder)/'evidence';evidence.mkdir();args=types.SimpleNamespace(evidence=evidence,manifest=evidence/'manifest.json')
   primary=RuntimeError('owned primary exception');secondary=RuntimeError('owned secondary optional state failure');calls=[]
   def fail(*args):calls.append(1);raise primary if len(calls)==1 else secondary
   metadata=dict(SOURCE='a'*40,ISO_BYTES=100,ISO_SHA256='b'*64,ORIGINAL_RUN=1)
   with patch.dict(R.os.environ,{'GITHUB_SHA':'c'*40}),patch.object(R,'verify',lambda args:None),patch.object(R.F,'Observation',lambda *args:Context()),patch.object(R.R,'require_docker',lambda:'owned'),patch.object(R.Path,'is_char_device',lambda self:True),patch.multiple(R.R,create=True,**metadata),patch.object(R.R,'write_json',fail):
    with self.assertRaises(RuntimeError) as caught:R.run(args)
   self.assertIs(caught.exception,primary);self.assertEqual(len(calls),2)
 def test_failed_partial_output_never_retains_a_partial_member_or_replaces_primary(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);raw=root/'originals';raw.mkdir();put(raw/F.HOST,host());put(raw/'harness/serial-boot.log',b'owned-secret@example.invalid\n');target=root/'uploaded';original=F.write_exclusive
   def broken(path,data):
    if path.name=='original':path.write_bytes(data[:2]);path.chmod(0o600);raise OSError('owned disk fixture')
    return original(path,data)
   with patch.object(F,'write_exclusive',broken):
    with self.assertRaisesRegex(RuntimeError,'Sensitive text in external evidence'):F.screen_with_partial(raw,target,scanner())
   self.assertFalse((target/F.HOST).exists());self.assertFalse(any(p.name=='original' for p in target.rglob('*')))
 def test_actual_observer_and_mutated_serializer_fail_closed_preserve_primary(self):
  public={'tools/native-functional/runner.py':(NATIVE/'runner.py').read_bytes(),'tools/native-functional/evidence.py':(NATIVE/'evidence.py').read_bytes()}
  with tempfile.TemporaryDirectory() as folder,patch.object(F,'source_context',lambda path:(scanner(),public)):
   evidence=Path(folder);held=F.Observation(evidence,evidence/'ignored-manifest',R.__dict__,E.__dict__);held.milestone('harness-execution')
   primary=RuntimeError('owned private original exception operand')
   self.assertFalse(held.__exit__(RuntimeError,primary,primary.__traceback__))
   result=json.loads((evidence/F.HOST).read_bytes());F.closed_host(result)
   self.assertEqual(result['error_class'],'runtime-error');self.assertEqual(result['guard_site'],'unknown');self.assertNotIn('operand',(evidence/F.HOST).read_text())
  with tempfile.TemporaryDirectory() as folder,patch.object(F,'source_context',lambda path:(scanner(),public)):
   evidence=Path(folder);held=F.Observation(evidence,evidence/'ignored-manifest',R.__dict__,E.__dict__)
   original=F.json.dumps
   def foreign(value,**kw):return original(dict(value,unknown_private_field='owned foreign serializer value'),**kw)
   with patch.object(F.json,'dumps',foreign):self.assertFalse(held.__exit__(RuntimeError,primary,primary.__traceback__))
   self.assertFalse((evidence/F.HOST).exists())
 def test_cancelled_original_screen_has_no_fallback_or_replacement(self):
  primary=KeyboardInterrupt();s=types.SimpleNamespace(screen_external=lambda *args:(_ for _ in ()).throw(primary))
  with patch.object(F,'partial_screen') as partial:
   with self.assertRaises(KeyboardInterrupt) as caught:F.screen_with_partial(Path('/owned'),Path('/owned-target'),s)
  self.assertIs(caught.exception,primary);partial.assert_not_called()
 def test_staged_link_replacement_or_inplace_write_never_uploads_unchecked_bytes(self):
  for replace in (True,False):
   with tempfile.TemporaryDirectory() as folder:
    root=Path(folder);raw=root/'originals';raw.mkdir();target=root/'uploaded';put(raw/F.HOST,host());put(raw/'harness/serial-boot.log',b'owned-secret@example.invalid\n');original=F.os.link;changed=[]
    def attack(source,destination,**kw):
     result=original(source,destination,**kw)
     if Path(destination).name==F.HOST:
      if replace:Path(destination).unlink()
      put(Path(destination),b'{"password":"owned staged output fixture"}\n');changed.append(True)
     return result
    with patch.object(F.os,'link',attack):
     with self.assertRaisesRegex(RuntimeError,'Sensitive text in external evidence'):F.screen_with_partial(raw,target,scanner())
    self.assertEqual(changed,[True]);self.assertFalse(target.exists())
 def test_final_ledger_verifies_every_destination_and_rejects_unknown_symlink(self):
  for change in ('replace-known','add-symlink'):
   with tempfile.TemporaryDirectory() as folder:
    root=Path(folder);raw=root/'originals';raw.mkdir();target=root/'uploaded';put(raw/F.HOST,host());put(raw/'harness/serial-boot.log',b'owned-secret@example.invalid\n');outside=root/'outside';outside.mkdir();put(outside/'private.json',b'{"password":"owned outside fixture"}\n');original=F.write_exclusive;changed=[]
    def attack(path,data):
     result=original(path,data)
     if path.name=='upload-screening.json':
      if change=='replace-known':
       staged=path.parent/F.HOST;staged.unlink();put(staged,b'{"password":"owned final replacement fixture"}\n')
      else:(path.parent/'unknown-directory').symlink_to(outside,target_is_directory=True)
      changed.append(True)
     return result
    with patch.object(F,'write_exclusive',attack):
     with self.assertRaisesRegex(RuntimeError,'Sensitive text in external evidence'):F.screen_with_partial(raw,target,scanner())
    self.assertEqual(changed,[True]);self.assertFalse(target.exists())
 def test_real_SIGINT_milestone_and_completed_observer_preserve_cancellation(self):
  held=object.__new__(F.Observation);held.milestones=[];held.handled_failures=[];fired=[];old=signal.signal(signal.SIGINT,signal.default_int_handler);previous=sys.gettrace()
  def inject(frame,event,arg):
   if frame.f_code is F.Observation.milestone.__code__ and event=='line' and not fired:
    fired.append(True);os.kill(os.getpid(),signal.SIGINT)
   return inject
  try:
   sys.settrace(inject)
   with self.assertRaises(KeyboardInterrupt):held.milestone('harness-execution')
  finally:sys.settrace(previous);signal.signal(signal.SIGINT,old)
  self.assertEqual(fired,[True])
  public={'tools/native-functional/runner.py':(NATIVE/'runner.py').read_bytes(),'tools/native-functional/evidence.py':(NATIVE/'evidence.py').read_bytes()}
  for primary in (None,RuntimeError('owned original primary')):
   with tempfile.TemporaryDirectory() as folder,patch.object(F,'source_context',lambda path:(scanner(),public)):
    held=F.Observation(Path(folder),Path(folder)/'ignored',R.__dict__,E.__dict__)
    def cancelled(*args):os.kill(os.getpid(),signal.SIGINT)
    old=signal.signal(signal.SIGINT,signal.default_int_handler)
    try:
     with patch.object(F,'write_exclusive',cancelled):
      if primary is None:
       with self.assertRaises(KeyboardInterrupt):held.__exit__(None,None,None)
      else:self.assertFalse(held.__exit__(RuntimeError,primary,primary.__traceback__))
    finally:signal.signal(signal.SIGINT,old)
 def test_real_post_open_SIGINT_link_reader_owns_FD_and_restores_signal(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);pending=root/'original';output=root/'published';raw=b'owned safe original';put(pending,raw);before=set(os.listdir('/proc/self/fd'));opened=[];real=F.os.open;old=signal.signal(signal.SIGINT,signal.default_int_handler)
   def after_open(path,flags,*args):
    fd=real(path,flags,*args)
    if Path(path)==pending and (flags&os.O_ACCMODE)==os.O_RDONLY and not opened:opened.append(True);os.kill(os.getpid(),signal.SIGINT)
    return fd
   try:
    with patch.object(F.os,'open',after_open):
     with self.assertRaises(KeyboardInterrupt):F.link_owned_original(pending,output,raw)
    self.assertIs(signal.getsignal(signal.SIGINT),signal.default_int_handler)
   finally:signal.signal(signal.SIGINT,old)
   self.assertEqual(opened,[True]);self.assertEqual(before,set(os.listdir('/proc/self/fd')));self.assertEqual(output.read_bytes(),raw)
 def test_actual_final_rename_holder_swap_never_emits_upload_admission(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);raw=root/'originals';raw.mkdir();target=root/'uploaded';put(raw/F.HOST,host());put(raw/'harness/serial-boot.log',b'owned-secret@example.invalid\n');step=root/'step-output';put(step,b'');real=F.Path.rename;changed=[]
   def attack(stage,destination):
    if Path(destination)==target:
     aside=root/'validated-held-aside';real(stage,aside);stage.mkdir(mode=0o700)
     put(stage/F.HOST,b'{"password":"owned holder replacement fixture"}\n');put(stage/'upload-screening.json',(aside/'upload-screening.json').read_bytes());put(stage/'incomplete-evidence.json',(aside/'incomplete-evidence.json').read_bytes());changed.append(True)
    return real(stage,destination)
   with patch.object(F.Path,'rename',attack):
    with self.assertRaisesRegex(RuntimeError,'Sensitive text in external evidence'):F.screen_with_partial(raw,target,scanner(),on_ready=lambda:F.publication_output(step))
   self.assertEqual(changed,[True]);self.assertEqual(step.read_bytes(),b'')
 def test_publication_field_is_closed_and_only_emitted_after_success(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);raw=root/'originals';raw.mkdir();target=root/'uploaded';put(raw/F.HOST,host());put(raw/'harness/serial-boot.log',b'owned-secret@example.invalid\n');step=root/'step-output';put(step,b'')
   with self.assertRaisesRegex(RuntimeError,'Sensitive text in external evidence'):F.screen_with_partial(raw,target,scanner(),on_ready=lambda:F.publication_output(step))
   self.assertEqual(step.read_bytes(),b'upload_admitted=true\n');F.closed_host(json.loads((target/F.HOST).read_bytes()))
   with self.assertRaises(ValueError):F.publication_output(step)
   alias=root/'alias';alias.symlink_to(step)
   with self.assertRaises(ValueError):F.publication_output(alias)
 def test_after_real_rename_member_mutation_does_not_admit_upload(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);raw=root/'originals';raw.mkdir();target=root/'uploaded';put(raw/F.HOST,host());put(raw/'harness/serial-boot.log',b'owned-secret@example.invalid\n');step=root/'step-output';put(step,b'');real=F.Path.rename
   def attack(stage,destination):
    result=real(stage,destination)
    if Path(destination)==target:put(target/F.HOST,b'{"password":"owned post-rename fixture"}\n')
    return result
   with patch.object(F.Path,'rename',attack):
    with self.assertRaisesRegex(RuntimeError,'Sensitive text in external evidence'):F.screen_with_partial(raw,target,scanner(),on_ready=lambda:F.publication_output(step))
   self.assertEqual(step.read_bytes(),b'')
 def test_same_buffer_input_symlink_and_changed_generation_denied(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);p=root/'owned.json';put(p,host());link=root/'alias.json';link.symlink_to(p)
   with self.assertRaises(ValueError):F.read_regular(link,65536)
   raw,info=F.read_regular(p,65536);self.assertEqual(raw,p.read_bytes());self.assertTrue(F.same(info,p.lstat()))
if __name__=='__main__':unittest.main(verbosity=2)
