"""Source-only actual function controls; no SDK build, hosted input or RPM install."""
from pathlib import Path
import hashlib,subprocess,types,unittest
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
BASE='4a95bc93108cda963a7c90a6ada8f515b35d36bd'
OLD='tools/browser-accelerator-inner-failure-source/producer.py'
QUERY=['rpm','-qa','--qf','%{NAME}-%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}\n']
CANONICAL=b'gpg-pubkey-0:6d9f90a6-6786af3b.(none)\n'
def load(raw,name):
 m=types.ModuleType(name);m.__file__=str(HERE/(name+'.py'));exec(compile(raw,m.__file__,'exec'),m.__dict__);return m
class Controls(unittest.TestCase):
 def setUp(self):self.new=load((HERE/'producer.py').read_bytes(),'new_census')
 def census(self,raw):
  with patch.object(self.new.subprocess,'check_output',return_value=raw) as command:
   result=self.new.package_census();command.assert_called_once_with(QUERY,timeout=60);return result
 def deny(self,raw):
  with patch.object(self.new.subprocess,'check_output',return_value=raw) as command:
   with self.assertRaises(RuntimeError) as caught:self.new.package_census()
   command.assert_called_once_with(QUERY,timeout=60)
  self.assertEqual(self.new.failure_record(caught.exception)['phase'],'unknown') # assertRaises clears the traceback.
  return caught.exception
 def test_real_public_owned_key_query_reproduces_original_and_accepts_exact_new_row(self):
  raw=subprocess.check_output(['git','-C',str(HERE),'show',BASE+':'+OLD])
  self.assertEqual(hashlib.sha256(raw).hexdigest(),'ffcd85e7066f1c272d2c98fca54c7ce969284e14ee8b5cc1a58757be12cb6d47')
  old=load(raw,'old_census')
  with patch.object(old.subprocess,'check_output',return_value=CANONICAL) as command:
   try:old.package_census()
   except RuntimeError as error:
    self.assertEqual(error.args,('producer_package_shape',));self.assertEqual(old.failure_record(error)['phase'],'environment_inventory')
   else:self.fail('historical Source must reject canonical key record')
   command.assert_called_once_with(QUERY,timeout=60)
  self.assertEqual(self.census(CANONICAL),CANONICAL)
 def test_full_normal_and_multiple_key_inventory_kept_sorted_without_filter_or_reformat(self):
  rows=[b'z-devel-0:1.2.3-4.fc44.x86_64',b'gpg-pubkey-0:6d9f90a6-6786af3b.(none)',b'a-1:2~rc^git+1-2.fc44.noarch',b'gpg-pubkey-0:1234abcd-00000000.(none)',b'a-1:2~rc^git+1-2.fc44.noarch']
  raw=b'\n'.join(rows)+b'\n';self.assertEqual(self.census(raw),b'\n'.join(sorted(rows))+b'\n')
 def test_absent_arch_is_only_canonical_public_key_record_not_any_package(self):
  bad=[b'other-0:6d9f90a6-6786af3b.(none)',b'gpg-pubkey-1:6d9f90a6-6786af3b.(none)',b'gpg-pubkey-0:6D9F90A6-6786af3b.(none)',b'gpg-pubkey-0:6d9f90a-6786af3b.(none)',b'gpg-pubkey-0:6d9f90a6-6786af3bc.(none)',b'gpg-pubkey-0:6d9f90a6-6786af3b.(unknown)',b'gpg-pubkey-0:6d9f90a6-6786af3b.(none)extra',b'gpg-pubkey-0:6d9f90a6-6786af3b.(none) private@example.invalid',b'gpg-pubkey-0:6d9f90a6-6786af3b.(none)\x00']
  for row in bad:
   with self.subTest(row=row):
    with patch.object(self.new.subprocess,'check_output',return_value=CANONICAL+row+b'\n'):
     try:self.new.package_census()
     except RuntimeError as error:
      self.assertEqual(error.args,('producer_package_shape',));record=self.new.failure_record(error);self.assertEqual((record['phase'],record['reason']),('environment_inventory','producer_package_shape'))
     else:self.fail('unknown record accepted')
 def test_same_original_command_error_and_cancellation_propagate_without_operand_inspection(self):
  errors=[subprocess.CalledProcessError(1,['public-fixture'],stderr=b'private fixture not exported'),subprocess.TimeoutExpired(['public-fixture'],60),KeyboardInterrupt()]
  for error in errors:
   with patch.object(self.new.subprocess,'check_output',side_effect=error) as command:
    try:self.new.package_census()
    except BaseException as actual:self.assertIs(actual,error)
    else:self.fail('primary exception replaced')
    command.assert_called_once_with(QUERY,timeout=60)
 def test_original_empty_size_ascii_and_blank_row_denials_preserved(self):
  for raw,kind,reason in [(b'',RuntimeError,'producer_package_census'),(b'x'*(self.new.MAX_COMMAND_OUTPUT+1),RuntimeError,'producer_package_census'),(b'\xff\n',UnicodeDecodeError,None),(CANONICAL+b'\n',RuntimeError,'producer_package_shape')]:
   with patch.object(self.new.subprocess,'check_output',return_value=raw):
    try:self.new.package_census()
    except BaseException as error:
     self.assertIs(type(error),kind)
     if reason is not None:self.assertEqual(error.args,(reason,))
    else:self.fail('original bound/shape denial relaxed')
 def test_public_RPM6_full_Fedora44_fingerprint_and_unpadded_uint32_release(self):
  fingerprint=b'36f612dcf27f7d1a48a835e4dbfcf71c6d9f90a6'
  for stamp in (b'0',b'1',b'abc',b'6786af3b',b'ffffffff'):
   raw=b'gpg-pubkey-0:'+fingerprint+b'-'+stamp+b'.(none)\n';self.assertEqual(self.census(raw),raw)
  for version,stamp in ((fingerprint[:-1],b'1'),(fingerprint+b'a',b'1'),(b'a'*64,b'1'),(fingerprint,b''),(fingerprint,b'100000000'),(fingerprint,b'ABC')):
   raw=b'gpg-pubkey-0:'+version+b'-'+stamp+b'.(none)\n'
   with patch.object(self.new.subprocess,'check_output',return_value=raw):
    try:self.new.package_census()
    except RuntimeError as error:self.assertEqual(error.args,('producer_package_shape',))
    else:self.fail('unproved fingerprint or timestamp format accepted')
 def test_source_body_pin_and_finite_failure_table_use_actual_new_census(self):
  raw=(HERE/'producer.py').read_bytes();body=raw[:raw.index(b'\n# Diagnostic observation only.')]
  self.assertEqual(hashlib.sha256(body).hexdigest(),self.new.FAILURE_BODY_SHA256)
  site=[x for x in self.new.FAILURE_REQUIRE_SITES if x[0] is self.new.package_census.__code__]
  self.assertEqual(len(site),1);self.assertIs(site[0][1],self.new.__dict__);self.assertEqual(site[0][2],{188:('environment_inventory','producer_package_census'),190:('environment_inventory','producer_package_shape')})
if __name__=='__main__':unittest.main(verbosity=2)
