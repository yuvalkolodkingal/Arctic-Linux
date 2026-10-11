import ast
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
from contextlib import contextmanager

HERE=Path(__file__).parent
PREP=Path('/tmp/arctic-browser-accelerator-ab-source-preparation-20261011')
ROOT=Path('/tmp/arctic-browser-accelerator-hosted-source-20261011')
producer=types.ModuleType('hosted_producer_source');producer.__file__=str(HERE/'producer.py')
exec(compile((HERE/'producer.py').read_bytes(),producer.__file__,'exec'),producer.__dict__)
candidate_raw=subprocess.check_output(['git','show','a734288fc4c38040005d280b46e0dc4abba52bb2:tools/browser-accelerator-ab-source/candidate.py'],cwd=ROOT)
candidate=types.ModuleType('accepted_candidate');exec(compile(candidate_raw,'accepted_candidate.py','exec'),candidate.__dict__)
WINDOW=Path('/tmp/arctic-epiphany-static-symbols-20261011/epiphany-debugsource-member-0254').read_bytes()
SRPM=(PREP/producer.SRPM_NAME).read_bytes()


@contextmanager
def root_owner_fixture():
 # Local UID1000 owned files exercise actual FD/inode/mode/size/timestamps.
 # Only UID is normalized to the future rootful container's required0. No
 # actual root ownership, hosted container or build execution is attested.
 original=producer.identity
 def root_identity(info):
  values=list(original(info));values[3]=0;return tuple(values)
 with patch.object(producer,'identity',side_effect=root_identity):yield


class HostedSourceControls(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.members=producer.source_members(SRPM)

 def test_actual_signed_source_three_members_and_digests(self):
  receipt=json.loads((PREP/'signed-SRPM-members.json').read_bytes())
  self.assertEqual(set(self.members),set(producer.MEMBERS))
  for row in receipt['members']:
   raw=self.members[row['basename']]
   self.assertEqual(len(raw),row['bytes']);self.assertEqual(hashlib.sha256(raw).hexdigest(),row['sha256'])
  self.assertEqual(self.members['epiphany.spec'],(PREP/'official-epiphany-50.6.spec').read_bytes())

 def test_source_wrong_whole_input_denies_before_decoder(self):
  with patch.object(producer.gzip,'GzipFile') as decoder:
   for raw in (SRPM[:-1],SRPM+b'\n',b'',bytes(len(SRPM))):
    with self.assertRaisesRegex(RuntimeError,'producer_source_binding'):producer.source_members(raw)
   decoder.assert_not_called()

 def test_prepare_baseline_candidate_whole_source_and_spec_delta(self):
  with tempfile.TemporaryDirectory(prefix='owned-hosted-producer-') as tmp:
   paths=[]
   for variant in ('baseline','candidate'):
    top=Path(tmp)/variant;producer.prepare(top,self.members,variant,candidate,WINDOW);paths.append(top)
   for name in ('epiphany-50.6.tar.xz','epiphany-default-bookmarks.patch'):
    self.assertEqual((paths[0]/'SOURCES'/name).read_bytes(),self.members[name])
    self.assertEqual((paths[1]/'SOURCES'/name).read_bytes(),self.members[name])
   self.assertEqual((paths[0]/'SPECS/epiphany.spec').read_bytes(),self.members['epiphany.spec'])
   changed=(paths[1]/'SPECS/epiphany.spec').read_bytes()
   self.assertEqual(changed.replace(b'Patch1:         arctic-accelerator-candidate.patch\n',b''),self.members['epiphany.spec'])
   self.assertEqual((paths[1]/'SOURCES/arctic-accelerator-candidate.patch').read_bytes(),candidate.window_patch(WINDOW))
   for top in paths:
    self.assertEqual(top.stat().st_mode&0o777,0o700)
    for item in top.rglob('*'):
     self.assertFalse(item.is_symlink());self.assertEqual(item.stat().st_mode&0o777,0o700 if item.is_dir() else 0o600)

 def test_prepare_wrong_variant_members_or_existing_directory_denies(self):
  with tempfile.TemporaryDirectory(prefix='owned-hosted-producer-') as tmp:
   root=Path(tmp)
   for variant,members,top in (('foreign',self.members,root/'a'),('baseline',{},root/'b'),('baseline',self.members,root)):
    with self.assertRaises(RuntimeError):producer.prepare(top,members,variant,candidate,WINDOW)
   members=dict(self.members);members['epiphany.spec']=b'foreign'
   with self.assertRaisesRegex(RuntimeError,'producer_member_binding'):producer.prepare(root/'c',members,'baseline',candidate,WINDOW)
   self.assertFalse((root/'c').exists())

 def test_disabled_context_denies_before_container_identity(self):
  context=json.loads((HERE/'producer-context.json').read_bytes())
  self.assertIs(context['ready'],False);self.assertIsNone(context['container'])
  with self.assertRaisesRegex(RuntimeError,'producer_disabled'):producer.validate_context(context)
  context['ready']=True;context['container']='registry.fedoraproject.org/fedora@sha256:'+'1'*64
  producer.validate_context(context)
  for field in ('candidate','window_source'):
   poisoned=json.loads(json.dumps(context));poisoned[field]['sha256']='2'*64
   with self.assertRaisesRegex(RuntimeError,'producer_exact_source_context'):producer.validate_context(poisoned)
  for value in ('registry.fedoraproject.org/fedora:44','foreign',''):
   poisoned=dict(context,container=value)
   with self.assertRaisesRegex(RuntimeError,'producer_container'):producer.validate_context(poisoned)

 def test_actual_bounded_read_hash_path_and_symlink(self):
  with tempfile.TemporaryDirectory(prefix='owned-hosted-input-') as tmp:
   path=Path(tmp)/'input';path.write_bytes(b'owned finite Source');path.chmod(0o600)
   raw=path.read_bytes();h=hashlib.sha256(raw).hexdigest();before=set(os.listdir('/proc/self/fd'))
   with root_owner_fixture():self.assertEqual(producer.read_bound(path,len(raw),h),raw)
   for size,digest in ((len(raw)-1,h),(len(raw),'0'*64)):
    with root_owner_fixture(),self.assertRaises(RuntimeError):producer.read_bound(path,size,digest)
   link=Path(tmp)/'link';link.symlink_to(path)
   with self.assertRaises(OSError):producer.read_bound(link,len(raw),h)
   self.assertEqual(set(os.listdir('/proc/self/fd')),before)

 def test_context_same_buffer_identity_and_malformed_fields(self):
  with tempfile.TemporaryDirectory(prefix='owned-hosted-context-') as tmp:
   path=Path(tmp)/'context';context=json.loads((HERE/'producer-context.json').read_bytes())
   context['ready']=True;context['container']='registry.fedoraproject.org/fedora@sha256:'+'1'*64
   raw=(json.dumps(context)+'\n').encode();path.write_bytes(raw);path.chmod(0o600)
   with root_owner_fixture():self.assertEqual(producer.read_context(path),context)
   context['private_unknown_field']='opaque fixture'
   path.write_text(json.dumps(context))
   with root_owner_fixture(),self.assertRaisesRegex(RuntimeError,'producer_context_schema'):producer.read_context(path)
   path.chmod(0o666)
   with root_owner_fixture(),self.assertRaisesRegex(RuntimeError,'producer_context_file'):producer.read_context(path)

 def test_real_sigint_acquisition_handoff_restores_handler_mask_and_FDs(self):
  with tempfile.TemporaryDirectory(prefix='owned-hosted-signal-') as tmp:
   path=Path(tmp)/'input';path.write_bytes(b'finite');path.chmod(0o600)
   original=producer.os.open;before=set(os.listdir('/proc/self/fd'));handler=signal.getsignal(signal.SIGINT)
   mask=signal.pthread_sigmask(signal.SIG_BLOCK,set())
   def after_open(*args,**kwargs):
    fd=original(*args,**kwargs);os.kill(os.getpid(),signal.SIGINT);return fd
   try:
    signal.signal(signal.SIGINT,signal.default_int_handler)
    with patch.object(producer.os,'open',side_effect=after_open):
     with self.assertRaises(KeyboardInterrupt):producer.read_bound(path,6,hashlib.sha256(b'finite').hexdigest())
   finally:signal.signal(signal.SIGINT,handler)
   self.assertIs(signal.getsignal(signal.SIGINT),handler)
   self.assertEqual(signal.pthread_sigmask(signal.SIG_BLOCK,set()),mask)
   self.assertEqual(set(os.listdir('/proc/self/fd')),before)

 def test_real_alarm_output_handoff_keeps_deadline_and_closes_owned_FD(self):
  with tempfile.TemporaryDirectory(prefix='owned-hosted-alarm-') as tmp:
   path=Path(tmp)/'output';original=producer.os.open;before=set(os.listdir('/proc/self/fd'))
   handler=signal.getsignal(signal.SIGALRM);mask=signal.pthread_sigmask(signal.SIG_BLOCK,set())
   alarm=TimeoutError('owned deadline')
   def expired(*unused):raise alarm
   def after_open(*args,**kwargs):
    fd=original(*args,**kwargs);os.kill(os.getpid(),signal.SIGALRM);return fd
   try:
    signal.signal(signal.SIGALRM,expired)
    with patch.object(producer.os,'open',side_effect=after_open):
     with self.assertRaises(TimeoutError) as caught:producer.private_write(path,b'finite')
     self.assertIs(caught.exception,alarm)
   finally:signal.signal(signal.SIGALRM,handler)
   self.assertIs(signal.getsignal(signal.SIGALRM),handler)
   self.assertEqual(signal.pthread_sigmask(signal.SIG_BLOCK,set()),mask)
   self.assertEqual(set(os.listdir('/proc/self/fd')),before)

 def test_output_exclusive_symlink_existing_no_follow(self):
  with tempfile.TemporaryDirectory(prefix='owned-hosted-output-') as tmp:
   root=Path(tmp);path=root/'output';producer.private_write(path,b'finite')
   self.assertEqual(path.read_bytes(),b'finite');self.assertEqual(path.stat().st_mode&0o777,0o600)
   with self.assertRaises(FileExistsError):producer.private_write(path,b'foreign')
   link=root/'link';link.symlink_to(root/'outside')
   with self.assertRaises(FileExistsError):producer.private_write(link,b'foreign')
   self.assertFalse((root/'outside').exists());self.assertEqual(path.read_bytes(),b'finite')

 def test_input_replacement_same_bytes_rejects_without_foreign_cleanup(self):
  with tempfile.TemporaryDirectory(prefix='owned-hosted-replacement-') as tmp:
   root=Path(tmp);path=root/'input';path.write_bytes(b'finite');path.chmod(0o600)
   original=producer.os.pread;before=set(os.listdir('/proc/self/fd'));owned_inode=path.stat().st_ino
   def replace(fd,size,offset):
    value=original(fd,size,offset);path.rename(root/'owned-original');path.write_bytes(value);path.chmod(0o600);return value
   with root_owner_fixture(),patch.object(producer.os,'pread',side_effect=replace):
    with self.assertRaisesRegex(RuntimeError,'producer_input_binding'):producer.read_bound(path,6,hashlib.sha256(b'finite').hexdigest())
   self.assertNotEqual(path.stat().st_ino,owned_inode);self.assertEqual(path.read_bytes(),b'finite')
   self.assertEqual((root/'owned-original').stat().st_ino,owned_inode)
   self.assertEqual(set(os.listdir('/proc/self/fd')),before)

 def test_input_foreign_descriptor_generation_preserved(self):
  with tempfile.TemporaryDirectory(prefix='owned-hosted-FD-') as tmp:
   root=Path(tmp);path=root/'input';path.write_bytes(b'finite');path.chmod(0o600)
   other=root/'other';other.write_bytes(b'foreign');other.chmod(0o600);foreign=os.open(other,os.O_RDONLY);reused=[]
   original=producer.os.pread
   def changed(fd,size,offset):
    value=original(fd,size,offset);os.dup2(foreign,fd);reused.append(fd);return value
   try:
    with root_owner_fixture(),patch.object(producer.os,'pread',side_effect=changed):
     with self.assertRaisesRegex(RuntimeError,'producer_input_binding'):producer.read_bound(path,6,hashlib.sha256(b'finite').hexdigest())
    self.assertEqual(len(reused),1);self.assertEqual(os.fstat(reused[0]).st_ino,other.stat().st_ino)
    self.assertEqual(os.pread(reused[0],7,0),b'foreign')
   finally:
    for fd in reused:os.close(fd)
    os.close(foreign)

 def test_hosted_GTK_source_whole_exact_candidate_and_signed_table(self):
  raw=(HERE/'gtk-control.c').read_bytes()
  self.assertEqual(len(raw),producer.GTK_CONTROL_BYTES)
  self.assertEqual(hashlib.sha256(raw).hexdigest(),producer.GTK_CONTROL_SHA)
  text=WINDOW.decode();table=text[text.index('const struct {'):text.index('#define SETTINGS_CONNECTION_DATA_KEY')]
  self.assertIn(table.encode(),raw);self.assertEqual(raw.count(candidate.NEW.encode()),1)
  self.assertIn(b'gtk_widget_activate_action(first,"win.new-tab",NULL)',raw)
  self.assertIn(b'gtk_widget_activate_action(second,"win.new-tab",NULL)',raw)
  self.assertIn(b'gtk_accelerator_parse(actual[i],&a,&am)',raw)
  self.assertIn(b'gtk_accelerator_parse(expected[i],&b,&bm)',raw)
  self.assertNotIn(b'GDK_BACKEND',raw);self.assertNotIn(b'NO_AT_BRIDGE',raw)

 def test_no_build_or_install_commands_executed_by_import_and_context_gate(self):
  raw=(HERE/'producer.py').read_bytes();module=types.ModuleType('import_only');module.__file__=str(HERE/'producer.py')
  with patch.object(subprocess,'run') as run,patch.object(subprocess,'check_output') as output:
   exec(compile(raw,module.__file__,'exec'),module.__dict__)
   with self.assertRaisesRegex(RuntimeError,'producer_disabled'):module.validate_context(json.loads((HERE/'producer-context.json').read_bytes()))
   run.assert_not_called();output.assert_not_called()


if __name__=='__main__':unittest.main(verbosity=2)
