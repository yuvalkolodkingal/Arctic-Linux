"""Public fixed-value fixtures only; no historical or current original input."""
import io,json,os,signal,sys,types,unittest
from pathlib import Path
import observer as O
HERE=Path(__file__).parent
SCANNER=(HERE/'scanner.py').read_bytes();OWNER=(HERE/'ownership.py').read_bytes()
UID=b' UserID     : "Fedora (44) <fedora-44-primary@fedoraproject.org>"\n'
EMAIL=b'fedora-44-primary@fedoraproject.org'
PRIVATE=b'synthetic-private-operand'
def probe():return O.ScreenProbe(SCANNER,OWNER,'tools/browser-screen-failure-source/scanner.py')
class Controls(unittest.TestCase):
    def rejected(self,raw,expected,relative='logs/producer.log'):
        p=probe();seen=[];before=sys.stdout;previous=sys.gettrace()
        def trace(frame,event,value):
            if event=='exception' and frame.f_code is p.module.external_text.__code__:seen.append(value[1])
            return trace
        try:
            sys.settrace(trace)
            with self.assertRaises(RuntimeError) as caught:p.screen(raw,relative)
        finally:sys.settrace(previous)
        self.assertIs(caught.exception,seen[-1]);self.assertIs(sys.stdout,before)
        row=p.last_failure;self.assertIs(row['known_public_Fedora44_UID_DNF_line'],expected)
        self.assertIs(row['original_exception_preserved'],True)
        for key in ('privacy_admitted','authenticated_runtime_frame_attribution','build_performance_release_acceptance'):self.assertIs(row[key],False)
        encoded=json.dumps(row).encode()
        for forbidden in (EMAIL,UID.strip(),PRIVATE):self.assertNotIn(forbidden,encoded)
        return p
    def test_exact_complete_line_is_one_bit_still_rejected_with_same_primary(self):
        for raw in (UID,b'Importing OpenPGP key 0x6d9f90a6:\n'+UID,UID+b'password='+PRIVATE):
            with self.subTest(raw=raw):self.rejected(raw,True)
    def test_unknown_email_uid_format_line_boundaries_and_split_match_deny(self):
        for raw in (EMAIL+b'\n',UID.replace(b'Fedora (44)',b'Fedora (43)'),
                UID.replace(b' UserID',b'UserID'),UID.replace(b' UserID',b'private UserID'),
                UID.replace(b'>"\n',b'>" extra\n'),UID.rstrip(b'\n'),UID.replace(b'\n',b'\r\n'),
                UID.replace(EMAIL,b'private@example.invalid'),UID.replace(b'primary@',b'primary\x1b[31m@'),
                b'password='+PRIVATE+b'\n'+UID):
            with self.subTest(raw=raw):self.rejected(raw,False)
    def test_wrong_roles_are_false_even_for_same_complete_public_line(self):
        for relative in ('logs/bootstrap.log','logs/collector.log','activation.json','/unknown'):
            with self.subTest(relative=relative):self.rejected(UID,False,relative)
    def test_actual_scanner_direct_throw_missing_caller_chain_is_false(self):
        p=probe();value=UID.decode();match=p.module.EXTERNAL_SENSITIVE.search(value)
        try:p.module.reject_sensitive_match(match,'source-view',value,None,None)
        except RuntimeError as error:row=p.describe(error,'logs/producer.log',UID,p.sink)
        self.assertTrue(row['observer_owned_scanner_site']);self.assertIs(row['known_public_Fedora44_UID_DNF_line'],False)
    def test_structurally_equal_nested_code_and_same_code_foreign_namespace_deny(self):
        for kind in ('nested-clone','foreign-global','binding-replacement'):
            p=probe();external=p.module.external_text
            if kind=='nested-clone':
                nested=p.uid_call_codes[1]
                external.__code__=external.__code__.replace(co_consts=tuple(c.replace() if c is nested else c for c in external.__code__.co_consts))
            elif kind=='foreign-global':p.module.external_text=types.FunctionType(external.__code__,dict(p.module.__dict__))
            else:p.uid_call_codes=tuple(list(p.uid_call_codes))
            with self.assertRaises(RuntimeError):p.screen(UID,'logs/producer.log')
            self.assertEqual(p.last_failure['scanner_category'],'unknown');self.assertIs(p.last_failure['known_public_Fedora44_UID_DNF_line'],False)
    def test_source_mutation_and_failed_snapshot_cannot_attest_public_value(self):
        p=probe();p.module.EXTERNAL_RULE_PHASES=('foreign',)
        with self.assertRaises(RuntimeError):p.screen(UID,'logs/producer.log')
        self.assertFalse(p.last_failure['observer_owned_scanner_site']);self.assertIs(p.last_failure['known_public_Fedora44_UID_DNF_line'],False)
        self.assertIs(probe().screen(b'public\n','logs/producer.log'),b'public\n')
    def test_actual_SIGINT_in_equality_helper_preserves_primary_stdout_and_false(self):
        p=probe();before=sys.stdout;seen=[];sent=[];previous=sys.gettrace()
        def trace(frame,event,value):
            if event=='exception' and frame.f_code is p.module.external_text.__code__:seen.append(value[1])
            if event=='line' and frame.f_code is p.known_uid_line.__code__ and not sent:
                sent.append(True);os.kill(os.getpid(),signal.SIGINT)
            return trace
        try:
            sys.settrace(trace)
            with self.assertRaises(RuntimeError) as caught:p.screen(UID,'logs/producer.log')
        finally:sys.settrace(previous)
        self.assertTrue(sent);self.assertIs(caught.exception,seen[-1]);self.assertIs(sys.stdout,before)
        self.assertIs(p.last_failure['known_public_Fedora44_UID_DNF_line'],False)
    def test_remaining_failures_and_caps_keep_original_closed_schema(self):
        p=probe()
        for raw in (b'\xff',b'public\x1b['):
            with self.assertRaises(BaseException):p.screen(raw,'logs/producer.log')
            self.assertIs(p.last_failure['known_public_Fedora44_UID_DNF_line'],False)
        self.assertEqual((O.MAX_ORIGINAL,O.MAX_DIAGNOSTIC,O.MAX_FRAMES),(64*1024*1024,1024,64))
        row=p.unknown('logs/producer.log')
        self.assertEqual(set(row),{'schema','member_role','scanner_category','scanner_phase','scanner_family','observer_owned_scanner_site','original_exception_preserved','known_public_Fedora44_UID_DNF_line','privacy_admitted','authenticated_runtime_frame_attribution','build_performance_release_acceptance'})
if __name__=='__main__':unittest.main()
