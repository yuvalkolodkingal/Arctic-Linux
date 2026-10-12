"""Whole public/synthetic buffers only; no closed original or runtime input."""
import json,os,signal,sys,types,unittest
from pathlib import Path
import observer as O
HERE=Path(__file__).parent;SCANNER=(HERE/'scanner.py').read_bytes();OWNER=(HERE/'ownership.py').read_bytes()
UID=b' UserID     : "Fedora (44) <fedora-44-primary@fedoraproject.org>"\n'
EMAIL=b'fedora-44-primary@fedoraproject.org';PRIVATE=b'synthetic-private-value'
def probe():return O.ScreenProbe(SCANNER,OWNER,'tools/browser-fedora-uid-remedy-source/scanner.py')
class Controls(unittest.TestCase):
    def rejected(self,raw,relative='logs/producer.log',phase=None):
        p=probe();seen=[];before=sys.stdout;previous=sys.gettrace()
        def trace(frame,event,value):
            if event=='exception' and frame.f_code is p.module.external_text.__code__:seen.append(value[1])
            return trace
        try:
            sys.settrace(trace)
            with self.assertRaises(BaseException) as caught:p.screen(raw,relative)
        finally:sys.settrace(previous)
        self.assertTrue(seen);self.assertIs(caught.exception,seen[-1]);self.assertIs(sys.stdout,before)
        row=p.last_failure;self.assertIs(row['original_exception_preserved'],True)
        self.assertIs(row['known_public_Fedora44_UID_DNF_line'],False)
        for key in ('privacy_admitted','authenticated_runtime_frame_attribution','build_performance_release_acceptance'):self.assertIs(row[key],False)
        if phase is not None:self.assertEqual(row['scanner_phase'],phase)
        for forbidden in (EMAIL,UID.strip(),PRIVATE):self.assertNotIn(forbidden,json.dumps(row).encode())
        return p
    def test_complete_fixed_public_line_returns_same_entire_bytes(self):
        p=probe()
        for raw in (UID,b'Importing OpenPGP key 0x6d9f90a6:\n'+UID+b'public\n',UID+UID,b'public\n'):
            with self.subTest(raw=raw):self.assertIs(p.screen(raw,'logs/producer.log'),raw);self.assertIsNone(p.last_failure)
    def test_all_remaining_private_matches_before_and_after_still_fail(self):
        private=(b'private@example.invalid',b'password='+PRIVATE,b'transcription: '+PRIVATE,
            b'authorization: Bearer '+PRIVATE,b'https://example.invalid/?query='+PRIVATE,
            b'https://user@example.invalid/path',b'--token '+PRIVATE,
            b'ghp_syntheticPrivateCredential',b'AKIAABCDEFGHIJKLMNOP',
            b'cryptsetup open /dev/vda4 < '+PRIVATE)
        for value in private:
            for raw in (value+b'\n'+UID,UID+value+b'\n',UID+b'public\n'+value+b'\n'+UID):
                with self.subTest(value=value,first=raw.startswith(value)):self.rejected(raw,phase='source-view')
    def test_full_line_extra_malformed_decorated_split_unknown_UID_deny(self):
        for raw in (EMAIL+b'\n',UID.replace(b' UserID',b'UserID'),UID.replace(b'Fedora (44)',b'Fedora (43)'),
                UID.replace(b'>"\n',b'>" extra\n'),UID.rstrip(b'\n'),UID.replace(b'\n',b'\r\n'),
                b'prefix'+UID,UID.replace(b' UserID',b'\x1b[31m UserID'),
                UID.replace(b'primary@',b'primary\x1b[31m@'),UID.replace(EMAIL,b'private@example.invalid')):
            with self.subTest(raw=raw):self.rejected(raw,phase='source-view')
    def test_role_default_wrong_context_and_typed_aliases_deny(self):
        for relative in ('logs/bootstrap.log','logs/collector.log','activation.json','/unknown'):
            with self.subTest(relative=relative):self.rejected(UID,relative,phase='source-view')
        p=probe()
        for role in (None,True,1,'command-bootstrap','',object()):
            with self.subTest(role=type(role).__name__):
                with self.assertRaises(RuntimeError):p.module.external_text(UID,public_DNF_UID_role=role)
        # This declared Source policy permits only independently public bytes;
        # a direct literal role is not an authenticated-caller claim.
        self.assertIs(p.module.external_text(UID,public_DNF_UID_role='command-producer'),UID)
        with self.assertRaises(RuntimeError):p.module.external_text(UID+b'private@example.invalid',public_DNF_UID_role='command-producer')
    def test_unrelated_CSI_keeps_conservative_terminal_view_rejection(self):
        for raw in (UID+b'\x1b[2Kpublic\n',b'\x1b[2Kpublic\n'+UID):
            with self.subTest(first=raw.startswith(UID)):self.rejected(raw,phase='terminal-view')
        raw=b'\x1b[2Kpublic\n';p=probe();self.assertIs(p.screen(raw,'logs/producer.log'),raw)
    def test_OSC_DCS_payloads_and_incomplete_escapes_remain_rejected(self):
        # Original terminal grammar excludes CR/LF inside a control frame.
        for raw in (b'\x1bP\n'+UID+b'\x1b\\',b'\x1b]8;\n'+UID+b'\x1b\\'):
            with self.subTest(prefix=raw[:2]):
                p=self.rejected(raw);self.assertEqual(p.last_failure['scanner_category'],'incomplete-terminal')
        for raw in (b'\x1bP'+UID.rstrip(b'\n')+b'\x1b\\',b'\x1b]8;'+UID.rstrip(b'\n')+b'\x1b\\'):
            with self.subTest(prefix=raw[:2]):self.rejected(raw,phase='source-view')
        self.rejected(b'\x1bPpassword='+PRIVATE+b'\x1b\\',phase='terminal-payload')
        self.rejected(b'public\x1b[')
        self.rejected(b'\xff')
    def test_foreign_code_globals_namespace_and_role_map_cannot_borrow_binding(self):
        for mutate in (
            lambda p:setattr(p.module.external_text,'__code__',p.module.external_text.__code__.replace()),
            lambda p:setattr(p.module,'external_text',types.FunctionType(p.module.external_text.__code__,dict(p.module.__dict__))),
            lambda p:p.module.external_text.__kwdefaults__.__setitem__('public_DNF_UID_role','command-producer'),
            lambda p:setattr(p.module,'exact_public_Fedora44_DNF_UID_match',lambda *args:True),
            lambda p:p.roles.__setitem__('logs/producer.log','other-text')):
            p=probe();mutate(p)
            with self.assertRaises(RuntimeError):p.screen(UID,'logs/producer.log')
            self.assertFalse(p.last_failure['observer_owned_scanner_site']);self.assertIs(p.last_failure['known_public_Fedora44_UID_DNF_line'],False)
    def test_real_SIGINT_in_new_predicate_preserves_exact_cancellation_stdout(self):
        p=probe();before=sys.stdout;previous=sys.gettrace();sent=[];cancel=KeyboardInterrupt('synthetic cancellation')
        def handler(_sig,_frame):raise cancel
        old_handler=signal.signal(signal.SIGINT,handler)
        def trace(frame,event,value):
            if event=='line' and frame.f_code is p.module.exact_public_Fedora44_DNF_UID_match.__code__ and not sent:
                sent.append(True);os.kill(os.getpid(),signal.SIGINT)
            return trace
        try:
            sys.settrace(trace)
            with self.assertRaises(KeyboardInterrupt) as caught:p.screen(UID,'logs/producer.log')
        finally:sys.settrace(previous);signal.signal(signal.SIGINT,old_handler)
        self.assertTrue(sent);self.assertIs(caught.exception,cancel);self.assertIs(sys.stdout,before)
        self.assertFalse(p.last_failure['observer_owned_scanner_site']);self.assertIs(p.last_failure['known_public_Fedora44_UID_DNF_line'],False)
        self.assertTrue(p.unchanged())
        self.assertEqual((O.MAX_ORIGINAL,O.MAX_DIAGNOSTIC,O.MAX_FRAMES),(64*1024*1024,1024,64))
if __name__=='__main__':unittest.main()
