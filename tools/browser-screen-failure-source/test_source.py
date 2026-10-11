"""Public Source and owned synthetic controls; never read build originals."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import signal
import types
import unittest
from unittest.mock import patch
import observer as O

HERE=Path(__file__).parent
SCANNER=(HERE/'scanner.py').read_bytes()
OWNERSHIP=(HERE/'ownership.py').read_bytes()
PRIVATE='synthetic-private-operand'

def probe():
    return O.ScreenProbe(SCANNER,OWNERSHIP,'tools/browser-screen-failure-source/scanner.py')

class Controls(unittest.TestCase):
    def rejected(self,raw,category,family='unknown',phase='not-observed',role='command-producer'):
        p=probe();seen=[];outer=io.StringIO()
        def trace(frame,event,value):
            if event=='exception' and frame.f_code is p.module.external_text.__code__:seen.append(value[1])
            return trace
        previous=sys.gettrace();sys.settrace(trace)
        try:
            with contextlib.redirect_stdout(outer):
                with self.assertRaises(BaseException) as caught:p.screen(raw,'logs/producer.log')
        finally:sys.settrace(previous)
        self.assertTrue(seen);self.assertIs(caught.exception,seen[-1])
        self.assertEqual(outer.getvalue(),'')
        row=p.last_failure
        self.assertEqual((row['member_role'],row['scanner_category'],row['scanner_family'],row['scanner_phase']),
            (role,category,family,phase))
        self.assertTrue(row['original_exception_preserved'])
        self.assertTrue(row['observer_owned_scanner_site'])
        for flag in ('privacy_admitted','authenticated_runtime_frame_attribution','build_performance_release_acceptance'):
            self.assertIs(row[flag],False)
        self.assertNotIn(PRIVATE,json.dumps(row))
        self.assertIs(p.module.external_text.__globals__,p.module.__dict__)
        return p

    def test_success_returns_same_whole_bytes_and_closed_role_inventory(self):
        p=probe()
        for raw in (b'',b'public build output\n',b'\x1b[2Ksystemd-zram-setup@zram0.service\n'):
            self.assertIs(p.screen(raw,'logs/bootstrap.log'),raw);self.assertIsNone(p.last_failure)
        for path,role in O.ROLE_TABLE:self.assertEqual(p.unknown(path)['member_role'],role)
        self.assertEqual(p.unknown('/unknown/'+PRIVATE)['member_role'],'other-text')

    def test_source_terminal_and_payload_use_actual_rejecting_sites(self):
        for raw,family,phase in (
            (('password='+PRIVATE).encode(),'named-secret','source-view'),
            (b'private@example.invalid','email-shape','source-view'),
            (('https://example.invalid/?query='+PRIVATE).encode(),'queried-url','source-view'),
            (('pa\x1b[2Jssword='+PRIVATE).encode(),'named-secret','terminal-view'),
            (('\x1bPpassword='+PRIVATE+'\x1b\\').encode(),'named-secret','terminal-payload')):
            with self.subTest(family=family,phase=phase):self.rejected(raw,'sensitive-text',family,phase)

    def test_invalid_utf8_and_incomplete_terminal_remain_fatal(self):
        self.rejected(b'\xff','invalid-utf8')
        self.rejected(b'public\x1b[','incomplete-terminal')

    def test_foreign_code_or_globals_never_attest_even_structurally_equal(self):
        p=probe();real=p.module.reject_sensitive_match
        for code,globals_ in ((real.__code__.replace(),p.module.__dict__),
                (real.__code__,dict(p.module.__dict__)),(real.__code__.replace(),dict(p.module.__dict__))):
            foreign=types.FunctionType(code,globals_,argdefs=real.__defaults__);sink=O.BoundedDiagnostic()
            with contextlib.redirect_stdout(sink):
                try:foreign(p.module.EXTERNAL_SENSITIVE.search('password='+PRIVATE),'source-view')
                except RuntimeError as error:row=p.describe(error,'logs/producer.log',b'public',sink)
            self.assertEqual(row['scanner_category'],'unknown');self.assertFalse(row['observer_owned_scanner_site'])

    def test_namespace_function_kwdefault_and_ownership_mutations_fail_before_input(self):
        for mutate in (
            lambda p:setattr(p.module.external_text,'__code__',p.module.external_text.__code__.replace()),
            lambda p:p.module.__dict__.__setitem__('external_text',types.FunctionType(p.module.external_text.__code__,dict(p.module.__dict__))),
            lambda p:p.module.classification_view.__kwdefaults__.__setitem__('escapes',object()),
            lambda p:setattr(p.ownership.OwnedSource,'site',lambda *a:None),
            lambda p:p.module.__dict__.__setitem__('RuntimeError',lambda *a:None)):
            p=probe();mutate(p)
            with self.assertRaises(RuntimeError):p.screen(b'public','logs/producer.log')
            self.assertEqual(p.last_failure['scanner_category'],'unknown')
            self.assertFalse(p.last_failure['observer_owned_scanner_site'])

    def test_optional_projection_failure_cannot_replace_actual_primary(self):
        p=probe();seen=[]
        def trace(frame,event,value):
            if event=='exception' and frame.f_code is p.module.external_text.__code__:seen.append(value[1])
            return trace
        previous=sys.gettrace();sys.settrace(trace)
        try:
            with patch.object(p,'describe',side_effect=KeyboardInterrupt(PRIVATE)):
                with self.assertRaises(RuntimeError) as caught:p.screen(b'password=synthetic','logs/producer.log')
        finally:sys.settrace(previous)
        self.assertIs(caught.exception,seen[-1]);self.assertEqual(p.last_failure['scanner_category'],'unknown')

    def test_actual_diagnostic_write_cancellation_keeps_same_exception(self):
        for cancellation in (KeyboardInterrupt(PRIVATE),SystemExit(PRIVATE)):
            p=probe()
            with patch.object(O.BoundedDiagnostic,'write',side_effect=cancellation):
                with self.assertRaises(type(cancellation)) as caught:p.screen(b'password=synthetic','logs/producer.log')
            self.assertIs(caught.exception,cancellation)
            self.assertEqual(p.last_failure['scanner_category'],'unknown')

    def test_opaque_exception_and_untrusted_role_or_malformed_diagnostic_stay_unknown(self):
        class Opaque(RuntimeError):
            @property
            def __traceback__(self):raise AssertionError('opaque traceback accessed')
            def __str__(self):raise AssertionError('opaque string accessed')
            def __repr__(self):raise AssertionError('opaque repr accessed')
        p=probe();sink=O.BoundedDiagnostic()
        for error in (Opaque(PRIVATE),ValueError(PRIVATE),KeyError(PRIVATE),OSError(PRIVATE)):
            self.assertEqual(p.describe(error,PRIVATE,b'public',sink)['scanner_category'],'unknown')
        p.roles['logs/producer.log']=PRIVATE
        row=p.unknown('logs/producer.log');self.assertEqual(row['member_role'],'other-text')
        self.assertNotIn(PRIVATE,json.dumps(row))
        sink=O.BoundedDiagnostic();sink.write('x'*(O.MAX_DIAGNOSTIC+1));self.assertIsNone(sink.captured())

    def test_actual_trace_frame_cap_keeps_oversized_stack_unknown(self):
        p=probe();sink=O.BoundedDiagnostic();raw=b'password=synthetic'
        def descend(depth):
            if depth:return descend(depth-1)
            return p.module.external_text(raw)
        for depth,expected in ((0,'sensitive-text'),(O.MAX_FRAMES,'unknown')):
            with contextlib.redirect_stdout(sink):
                try:descend(depth)
                except RuntimeError as error:row=p.describe(error,'logs/producer.log',raw,sink)
            self.assertEqual(row['scanner_category'],expected)

    def test_selection_keeps_private_split_and_public_uid_rejected(self):
        p=probe()
        for raw in (b'private\x1b[2K-person@example.invalid\n',
                b' UserID     : "Fedora (44) <fedora-44-primary@fedoraproject.org>"\n'):
            with self.assertRaises(RuntimeError):p.screen(raw,'logs/bootstrap.log')
            self.assertEqual(p.last_failure['scanner_category'],'sensitive-text')
        for raw in (SCANNER+b'\n',SCANNER.replace(b'def external_text',b'def changed_text',1)):
            with self.assertRaises(RuntimeError):O.ScreenProbe(raw,OWNERSHIP,'scanner.py')

    def test_private_print_forwarding_never_acquires_process_stdout(self):
        p=probe();before=sys.stdout
        p.module.print('alpha','beta',sep='/',end='!',flush=True)
        self.assertEqual(p.sink.captured(),'alpha/beta!');self.assertIs(sys.stdout,before)
        raw=b'public';self.assertIs(p.screen(raw,'logs/producer.log'),raw)
        self.assertEqual(p.sink.captured(),'');self.assertIs(sys.stdout,before)
        with self.assertRaises(RuntimeError):p.module.print('public',file=io.StringIO())

    def test_real_SIGINT_optional_observation_keeps_primary_without_stdout_restore(self):
        p=probe();before=sys.stdout;previous=sys.gettrace();seen=[];sent=[]
        def trace(frame,event,value):
            if event=='exception' and frame.f_code is p.module.external_text.__code__:seen.append(value[1])
            if event=='line' and frame.f_code is p.describe.__code__ and not sent:
                sent.append(True);os.kill(os.getpid(),signal.SIGINT)
            return trace
        try:
            sys.settrace(trace)
            with self.assertRaises(RuntimeError) as caught:p.screen(b'password=synthetic','logs/producer.log')
        finally:sys.settrace(previous)
        self.assertTrue(sent);self.assertIs(caught.exception,seen[-1]);self.assertIs(sys.stdout,before)
        self.assertEqual(p.last_failure['scanner_category'],'unknown')

    def test_real_SIGINT_during_scanner_print_is_same_interrupt_and_context_closed(self):
        p=probe();before=sys.stdout;previous=sys.gettrace();sent=[]
        cancellation=KeyboardInterrupt(PRIVATE)
        def cancelled(_signal,_frame):raise cancellation
        previous_handler=signal.signal(signal.SIGINT,cancelled)
        def trace(frame,event,value):
            if event=='line' and frame.f_code is O.BoundedDiagnostic.write.__code__ and not sent:
                sent.append(True);os.kill(os.getpid(),signal.SIGINT)
            return trace
        try:
            sys.settrace(trace)
            with self.assertRaises(KeyboardInterrupt) as caught:p.screen(b'password=synthetic','logs/producer.log')
        finally:
            sys.settrace(previous);signal.signal(signal.SIGINT,previous_handler)
        self.assertTrue(sent);self.assertIs(caught.exception,cancellation);self.assertIs(sys.stdout,before)
        self.assertEqual(p.last_failure['scanner_category'],'unknown')
        self.assertTrue(p.unchanged())
        for cell in p.module.print.__closure__:
            if cell.cell_contents is p.sink:
                cell.cell_contents=O.BoundedDiagnostic();break
        self.assertFalse(p.unchanged())
        with self.assertRaises(RuntimeError):p.screen(b'public','logs/producer.log')

if __name__=='__main__':unittest.main()
