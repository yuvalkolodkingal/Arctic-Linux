"""Original strict rejection, private bytes and pending cancellation stay intact."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('owned_screen_failure_control', Path(__file__).with_name('screen-evidence.py'))
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)
PRIVATE = 'password=private-value תמלול:private-text https://private.invalid/?token=private'


class ScreenFailureControls(unittest.TestCase):
    def screen(self, member, raw, *, failure=None, output_failure=None):
        with tempfile.TemporaryDirectory(prefix='arctic-owned-screen-control-') as temp:
            source, target = Path(temp)/'source', Path(temp)/'out'
            p=source/member;p.parent.mkdir(parents=True);p.write_bytes(raw)
            stream=io.StringIO()
            with contextlib.ExitStack() as stack:
                stack.enter_context(contextlib.redirect_stdout(stream))
                if failure is not None: stack.enter_context(patch.object(S,'external_text',side_effect=failure))
                if output_failure is not None: stack.enter_context(patch('builtins.print',side_effect=output_failure))
                try: S.screen_external(source,target)
                except BaseException as error:
                    self.assertFalse(target.exists())
                    self.assertEqual(p.read_bytes(),raw)
                    self.assertEqual(list(Path(temp).glob('arctic-screening-*')),[])
                    return error,stream.getvalue()
            self.fail('Strict screening must reject this control')

    def test_actual_member_rejections_are_closed_and_preserve_original_private_bytes(self):
        for member,role in S.EXTERNAL_MEMBER_DIAGNOSTICS.items():
            error,line=self.screen(member,PRIVATE.encode())
            self.assertIs(type(error),RuntimeError)
            self.assertEqual(error.args,('Sensitive text in external evidence',))
            self.assertEqual(line,'ARCTIC-EVIDENCE-DIAGNOSTIC=external-text-'+role+'-rejection-sensitive-text\n')
            observed=line.encode()
            self.assertIs(S.external_text(observed),observed)
            self.assertNotIn(PRIVATE,line);self.assertNotIn(member,line)

    def test_unknown_member_name_and_arbitrary_error_text_are_never_exported(self):
        error=ValueError(PRIVATE)
        caught,line=self.screen('private-filename.log',b'public-control',failure=error)
        self.assertIs(caught,error)
        self.assertEqual(line,'ARCTIC-EVIDENCE-DIAGNOSTIC=external-text-other-text-rejection-other-error\n')
        self.assertNotIn('private-filename',line)

    def test_incomplete_terminal_and_other_reasons_remain_fatal(self):
        caught,line=self.screen('host/serial.log',b'public\x1b[')
        self.assertEqual(caught.args,('Incomplete terminal escape in external evidence',))
        self.assertEqual(line,'ARCTIC-EVIDENCE-DIAGNOSTIC=external-text-installer-live-uart-rejection-incomplete-terminal\n')

    def test_observer_stdout_failure_retains_exact_primary_exception_and_args(self):
        for output in (OSError(PRIVATE),RuntimeError(PRIVATE),TypeError(PRIVATE)):
            primary=RuntimeError('Sensitive text in external evidence')
            caught,line=self.screen('execution.json',b'public-control',failure=primary,output_failure=output)
            self.assertIs(caught,primary);self.assertEqual(caught.args,('Sensitive text in external evidence',));self.assertEqual(line,'')

    def test_hostile_subclass_args_and_string_getters_are_never_read(self):
        class Hostile(RuntimeError):
            @property
            def args(self): raise AssertionError('private args read')
            def __str__(self): raise AssertionError('private error string read')
        class HostilePath(str):
            def __hash__(self): raise AssertionError('private path hashed')
        output=io.StringIO();error=Hostile()
        with contextlib.redirect_stdout(output):S.diagnose_external_member(HostilePath('host/serial.log'),error)
        self.assertEqual(output.getvalue(),'ARCTIC-EVIDENCE-DIAGNOSTIC=external-text-other-text-rejection-other-error\n')
        caught,_=self.screen('host/serial.log',b'public-control',failure=error)
        self.assertIs(caught,error)

    def test_real_and_observer_baseexception_cancellation_propagate_exact_identity(self):
        for cancellation in (KeyboardInterrupt(PRIVATE),SystemExit(PRIVATE)):
            caught,line=self.screen('host/serial.log',b'public-control',failure=cancellation)
            self.assertIs(caught,cancellation);self.assertEqual(line,'')
            primary=RuntimeError('Sensitive text in external evidence')
            caught,line=self.screen('host/serial.log',b'public-control',failure=primary,output_failure=cancellation)
            self.assertIs(caught,cancellation);self.assertEqual(line,'')

    def test_success_original_bytes_and_generic_redacting_mode_do_not_emit_observations(self):
        for external,raw in ((True,b'public UART\r\n'),(False,b'private@example.invalid')):
            with tempfile.TemporaryDirectory() as temp:
                source,target=Path(temp)/'source',Path(temp)/'out';source.mkdir();(source/'serial.log').write_bytes(raw)
                stream=io.StringIO()
                with contextlib.redirect_stdout(stream):S.screen(source,target,external=external)
                self.assertEqual(stream.getvalue(),'')
                self.assertEqual((source/'serial.log').read_bytes(),raw)
                self.assertEqual((target/'serial.log').read_bytes(),raw if external else b'[redacted]')

    def test_real_cli_rejection_discloses_only_fixed_observation_and_no_partial_upload(self):
        with tempfile.TemporaryDirectory() as temp:
            source,target=Path(temp)/'source',Path(temp)/'out';source.mkdir();(source/'execution.json').write_bytes(PRIVATE.encode())
            result=subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('screen-evidence.py')),
                '--preserve-original','--source',str(source),'--out',str(target)],capture_output=True,timeout=10)
            self.assertNotEqual(result.returncode,0);self.assertFalse(target.exists())
            self.assertEqual(result.stdout,b'ARCTIC-EVIDENCE-DIAGNOSTIC=external-text-execution-rejection-sensitive-text\n')
            self.assertNotIn(PRIVATE.encode(),result.stdout+result.stderr)
            self.assertEqual((source/'execution.json').read_bytes(),PRIVATE.encode())


if __name__=='__main__':unittest.main()
