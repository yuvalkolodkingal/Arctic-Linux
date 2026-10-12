"""Public/synthetic buffers only; all historical originals are closed."""
import json,os,signal,sys,types,unittest
from pathlib import Path
import observer as O
HERE=Path(__file__).parent
SCANNER=(HERE/'scanner.py').read_bytes();OWNER=(HERE/'ownership.py').read_bytes()
EMAIL=b'fedora-44-primary@fedoraproject.org'
LINE=b' UserID     : "Fedora (44) <fedora-44-primary@fedoraproject.org>"\n'
def probe():return O.ScreenProbe(SCANNER,OWNER,'tools/browser-fedora-UID-first-Match-Source/scanner.py')
class Controls(unittest.TestCase):
 def rejected(self,raw,expected,relative='logs/producer.log',phase='source-view'):
  p=probe();errors=[];before=sys.stdout;prior=sys.gettrace()
  def trace(frame,event,arg):
   if event=='exception' and frame.f_code is p.module.external_text.__code__:errors.append(arg[1])
   return trace
  try:
   sys.settrace(trace)
   with self.assertRaises(RuntimeError) as caught:p.screen(raw,relative)
  finally:sys.settrace(prior)
  self.assertIs(caught.exception,errors[-1]);self.assertIs(sys.stdout,before)
  row=p.last_failure
  self.assertEqual(row['schema'],'arctic-accelerator-screen-finite-observation-v3')
  self.assertIs(row['known_public_Fedora44_UID_email'],expected)
  self.assertIs(row['known_public_Fedora44_UID_DNF_line'],False)
  self.assertIs(row['original_exception_preserved'],True)
  self.assertEqual(row['scanner_phase'],phase)
  for key in ('privacy_admitted','authenticated_runtime_frame_attribution','build_performance_release_acceptance'):self.assertIs(row[key],False)
  self.assertNotIn(EMAIL,json.dumps(row).encode())
  return p
 def test_same_fixed_email_vs_whole_line_context_are_distinct(self):
  for raw in (EMAIL+b'\n',LINE.replace(b'\n',b'\r\n'),b' '+LINE,LINE.rstrip(b'\n'),b'\x1b[31m'+LINE+b'\x1b[0m'):
   with self.subTest(public_case=raw[:8]):self.rejected(raw,True)
  p=probe();self.assertIs(p.screen(LINE,'logs/producer.log'),LINE);self.assertIsNone(p.last_failure)
 def test_first_rejected_Match_only_and_all_remaining_privacy_rules_preserved(self):
  CRLF=LINE.replace(b'\n',b'\r\n')
  for raw,want in ((b'other@example.invalid\n'+CRLF,False),(CRLF+b'other@example.invalid\n',True),(LINE+b'other@example.invalid\n',False),(b'password=synthetic\n'+CRLF,False),(b'transcription: synthetic\n'+CRLF,False)):
   with self.subTest(want=want):self.rejected(raw,want)
 def test_contiguous_raw_role_phase_family_gates_preserved(self):
  self.rejected(EMAIL.replace(b'primary@',b'primary\x1b[31m@')+b'\n',False)
  for relative in ('logs/bootstrap.log','logs/collector.log','activation.json','unknown'):
   self.rejected(EMAIL+b'\n',False,relative)
  self.rejected(LINE+b'\x1b[2Kpublic\n',False,phase='terminal-view')
  self.rejected(b'\x1bPpassword=synthetic\x1b\\',False,phase='terminal-payload')
 def test_equal_Code_foreign_globals_and_binding_aliases_fail_closed(self):
  for kind in ('Code','globals','binding','roles'):
   p=probe();fn=O.ScreenProbe.known_uid_email;original_code=fn.__code__;original_method=fn
   try:
    if kind=='Code':fn.__code__=fn.__code__.replace()
    elif kind=='globals':O.ScreenProbe.known_uid_email=types.FunctionType(fn.__code__,dict(fn.__globals__))
    elif kind=='binding':p.uid_email_binding=tuple(list(p.uid_email_binding))
    else:p.roles['logs/producer.log']='other-text'
    with self.assertRaises(RuntimeError):p.screen(EMAIL+b'\n','logs/producer.log')
    self.assertFalse(p.last_failure['observer_owned_scanner_site']);self.assertIs(p.last_failure['known_public_Fedora44_UID_email'],False)
   finally:fn.__code__=original_code;O.ScreenProbe.known_uid_email=original_method
 def test_new_method_real_TERM_diagnostic_preserves_same_primary_stdout(self):
  p=probe();before=sys.stdout;prior=sys.gettrace();primaries=[];sent=[];cancel=KeyboardInterrupt('owned Source-only cancellation')
  def handler(_sig,_frame):raise cancel
  old=signal.signal(signal.SIGTERM,handler)
  def trace(frame,event,arg):
   if event=='exception' and frame.f_code is p.module.external_text.__code__:primaries.append(arg[1])
   if event=='line' and frame.f_code is p.uid_email_binding[1] and not sent:sent.append(True);os.kill(os.getpid(),signal.SIGTERM)
   return trace
  try:
   sys.settrace(trace)
   with self.assertRaises(RuntimeError) as caught:p.screen(EMAIL+b'\n','logs/producer.log')
  finally:sys.settrace(prior);signal.signal(signal.SIGTERM,old)
  self.assertTrue(sent);self.assertIs(caught.exception,primaries[-1]);self.assertIs(sys.stdout,before)
  self.assertIs(p.last_failure['known_public_Fedora44_UID_email'],False);self.assertIs(p.last_failure['known_public_Fedora44_UID_DNF_line'],False)
  self.assertFalse(p.last_failure['observer_owned_scanner_site']);self.assertTrue(p.unchanged())
 def test_instance_shadow_cannot_fabricate_or_suppress_frozen_email_value(self):
  for raw,shadow,want in ((b'unknown@example.invalid\n',True,False),(EMAIL+b'\n',False,True)):
   p=probe();original_stdout=sys.stdout;seen=[];prior=sys.gettrace()
   p.known_uid_email=types.MethodType(lambda self,*args:shadow,p)
   self.assertTrue(p.unchanged())
   def trace(frame,event,arg):
    if event=='exception' and frame.f_code is p.module.external_text.__code__:seen.append(arg[1])
    return trace
   try:
    sys.settrace(trace)
    with self.assertRaises(RuntimeError) as caught:p.screen(raw,'logs/producer.log')
   finally:sys.settrace(prior)
   self.assertIs(caught.exception,seen[-1]);self.assertIs(sys.stdout,original_stdout)
   self.assertIs(p.last_failure['known_public_Fedora44_UID_email'],want)
   self.assertIs(p.last_failure['known_public_Fedora44_UID_DNF_line'],False)
   self.assertFalse(p.last_failure['privacy_admitted'])
 def test_late_helper_Code_or_class_slot_drift_after_first_helper_denies(self):
  for kind in ('Code','class-foreign-globals'):
   p=probe();fn=O.ScreenProbe.known_uid_email;oldcode=fn.__code__;oldslot=fn;seen=[];sent=[];prior=sys.gettrace()
   def trace(frame,event,arg):
    if event=='exception' and frame.f_code is p.module.external_text.__code__:seen.append(arg[1])
    if event=='call' and frame.f_code is O.ScreenProbe.known_uid_line.__code__ and not sent:
     sent.append(True)
     if kind=='Code':fn.__code__=(lambda self,*args:True).__code__
     else:O.ScreenProbe.known_uid_email=types.FunctionType(fn.__code__,dict(fn.__globals__))
    return trace
   try:
    sys.settrace(trace)
    with self.assertRaises(RuntimeError) as caught:p.screen(b'unknown@example.invalid\n','logs/producer.log')
   finally:sys.settrace(prior);fn.__code__=oldcode;O.ScreenProbe.known_uid_email=oldslot
   self.assertTrue(sent);self.assertIs(caught.exception,seen[-1])
   self.assertFalse(p.last_failure['observer_owned_scanner_site'])
   self.assertIs(p.last_failure['known_public_Fedora44_UID_email'],False);self.assertIs(p.last_failure['known_public_Fedora44_UID_DNF_line'],False)
 def test_mutation_at_new_helper_return_withholds_computed_true(self):
  p=probe();fn=O.ScreenProbe.known_uid_email;oldcode=fn.__code__;sent=[];seen=[];prior=sys.gettrace();stdout=sys.stdout
  def trace(frame,event,arg):
   if event=='exception' and frame.f_code is p.module.external_text.__code__:seen.append(arg[1])
   if event=='return' and frame.f_code is oldcode and not sent:
    self.assertIs(arg,True);sent.append(True);fn.__code__=oldcode.replace()
   return trace
  try:
   sys.settrace(trace)
   with self.assertRaises(RuntimeError) as caught:p.screen(EMAIL+b'\n','logs/producer.log')
  finally:sys.settrace(prior);fn.__code__=oldcode
  self.assertTrue(sent);self.assertIs(caught.exception,seen[-1]);self.assertIs(sys.stdout,stdout)
  self.assertFalse(p.last_failure['observer_owned_scanner_site']);self.assertIs(p.last_failure['known_public_Fedora44_UID_email'],False)
  self.assertIs(p.last_failure['known_public_Fedora44_UID_DNF_line'],False);self.assertTrue(p.unchanged())
if __name__=='__main__':unittest.main(verbosity=2)
