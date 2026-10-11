"""Actual Source code-object observations and original failure/cleanup; no VM."""
import ast
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = 'ad6c4318226803f85cf6576765a350336dcd9218'
SHELL = (ROOT / 'tools/test-install.sh').read_text()
DRIVER = SHELL.split("DRIVER <<'PY' || true\n", 1)[1].split('\nPY\n', 1)[0]
TOKEN = 'a' * 32

def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

runner = module(HERE / 'runner.py', 'actual_inner_driver_runner')
vmtest = module(ROOT / 'tools/lib/vmtest.py', 'actual_inner_driver_vmtest')


def restore_driver_failure_diagnostics(driver):
    begin = '# Failure-only observations bind actual loaded function code and global identity.\n'
    assert driver.count(begin) == 1
    start = driver.index(begin)
    stop = driver.index('def stage_boot():\n', start)
    import hashlib
    assert hashlib.sha256(driver[start:stop].encode()).hexdigest() == '541da9e4a16d9833db1cc4ed1363ab6375089ccc669b168084b74982d4a02ad2'
    driver = driver[:start] + driver[stop:]
    old = '''        return 0 if ok else 1
    finally:
        dictation_host_stage("boot-cleanup")
        close_taskbar_vm(vm, display)

rc = 0
'''
    new = '''        return 0 if ok else 1
    except BaseException as error:
        try:
            dictation_driver_failure("boot-body", error)
        except BaseException:
            pass
        raise
    finally:
        dictation_host_stage("boot-cleanup")
        try:
            close_taskbar_vm(vm, display)
        except BaseException as error:
            try:
                dictation_driver_failure("boot-cleanup", error)
            except BaseException:
                pass
            raise

# Capture the real loaded Driver and VMtest once, before the original stage calls.
# Imports/setup failures before this point remain unobserved.
try:
    _DICTATION_DRIVER_BINDING = dictation_driver_binding()
except Exception:
    _DICTATION_DRIVER_BINDING = ()

rc = 0
'''
    assert driver.count(new) == 1
    return driver.replace(new, old, 1)


def restore_runner_driver_diagnostics(source):
    begin = '# These are Source observations, never a report gate or authenticated log origin.\n'
    assert source.count(begin) == 1
    start = source.index(begin)
    stop = source.index('def diagnostic(phase, stage, error, contract):\n', start)
    import hashlib
    assert hashlib.sha256(source[start:stop].encode()).hexdigest() == 'a89949673bfc57891efb08a34ae5c1708baf9345a766752d682ebe5d36d4b903'
    source = source[:start] + source[stop:]
    call = "                relay_driver_failures(private / (phase + '.log'), diagnostic_token, phase)\n"
    assert source.count(call) == 1
    return source.replace(call, '', 1)


def restore_native_login_observation(driver):
    """Compose the accepted Native256 exact inverse into historical rollback tests."""
    import hashlib
    begin = '# BEGIN NATIVE_LOGIN_INPUT_OBSERVATION\n'
    finish = '# END NATIVE_LOGIN_INPUT_OBSERVATION\n\n'
    assert driver.count(begin) == driver.count(finish) == 1
    start = driver.index(begin)
    end = driver.index(finish, start) + len(finish)
    assert hashlib.sha256(driver[start:end].encode()).hexdigest() == 'ca20dad9f313df3803c32cb74b64ae63110548b7a222a81fa70c4aeb25c774c8'
    driver = driver[:start] + driver[end:]
    replacements = (('            native_input = E.get("NATIVE_LAUNCHER_FIXTURE") == "1" and E.get("NATIVE_TASKBAR_FIXTURE") == "1" and E.get("NATIVE_AUDIO_FIXTURE") == "1"\n            if native_input:\n                before_input = vm.shot(f"boot-42-input-before-{attempt}")\n                pointer = "not-attempted-keyboard-only" if attempt == 1 else native_login_click(vm, before_input)\n                qmp_input = native_login_type(vm, password)\n            else:\n                vm.type_text(password, gap=0.3)\n            time.sleep(1)\n            typed_input = vm.shot(f"boot-42-password-typed-{attempt}")\n            if native_input:\n                native_login_record(before_input, typed_input, attempt, qmp_input, pointer)\n', '            vm.type_text(password, gap=0.3)\n            time.sleep(1)\n            vm.shot(f"boot-42-password-typed-{attempt}")\n'), ('            if native_input:\n                log("ARCTIC-NATIVE-LOGIN-AUTH " + json.dumps(dict(\n                    schema="arctic-native-login-auth-observation-v1", attempt=attempt,\n                    state="login-card-no-longer-classified" if gone else "login-card-still-classified",\n                    pam_result="not-observed", release_acceptance=False), sort_keys=True))\n', ''))
    for before, after in replacements:
        assert driver.count(before) == 1
        driver = driver.replace(before, after, 1)
    return driver


def restore_runner_collector_projection(source):
    """Compose the already accepted collector projection into older inverses."""
    import hashlib
    begin = 'COLLECTOR_FAILURE_PHASES = '
    assert source.count(begin) == 1
    start = source.index(begin)
    end = source.index('\ndef diagnostic(', start)
    assert hashlib.sha256(source[start:end].encode()).hexdigest() == 'fd318438ca74a680ce17d1d0052800f1e9c667753da236b5926fb43d8f9d303c'
    source = source[:start] + source[end:]
    call = "                relay_collector_failures(vm, phase)\n"
    assert source.count(call) == 1
    return source.replace(call, '', 1)


def environment(enabled=True):
    env = {'E': {'DICTATION_FIXTURE': '1', 'ARCTIC_DICTATION_HOST_TOKEN': TOKEN} if enabled else {},
           'vmtest': vmtest, 'os': os, 'time': types.SimpleNamespace(time=lambda: 1, sleep=lambda _: None),
           'taskbar_display_module': None, 'out': '/unused', 'boot_append': '', 'luks': 'fixture',
           'password': 'fixture', 'log': lambda _: None}
    nodes = [node for node in ast.parse(DRIVER).body if isinstance(node, ast.FunctionDef)
             or (isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
                 and target.id == 'DICTATION_HOST_STAGES' for target in node.targets))]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<actual generated Driver>', 'exec'), env)
    env['_DICTATION_DRIVER_BINDING'] = env['dictation_driver_binding']()
    return env


def records(text):
    prefix = 'ARCTIC-DICTATION-DRIVER-FAILURE ' + TOKEN + ' '
    return [json.loads(line[len(prefix):]) for line in text.splitlines() if line.startswith(prefix)]


class PrivateError(RuntimeError):
    def __str__(self):
        raise AssertionError('exception text read')
    def __repr__(self):
        raise AssertionError('exception text read')
    @property
    def args(self):
        raise AssertionError('exception args read')


class DriverFailureDiagnostics(unittest.TestCase):
    def test_whole_source_byte_and_ast_inverse_preserves_existing_driver_runner_and_vmtest(self):
        old_shell = subprocess.check_output(['git', '-C', str(ROOT), 'show', BASE + ':tools/test-install.sh']).decode()
        old_runner = subprocess.check_output(['git', '-C', str(ROOT), 'show', BASE + ':tools/dictation-qualification/runner.py']).decode()
        old_driver = old_shell.split("DRIVER <<'PY' || true\n", 1)[1].split('\nPY\n', 1)[0]
        restored = restore_driver_failure_diagnostics(DRIVER)
        self.assertEqual(restored, old_driver)
        self.assertEqual(SHELL.replace(DRIVER, restored, 1), old_shell)
        self.assertEqual(ast.dump(ast.parse(restored)), ast.dump(ast.parse(old_driver)))
        self.assertEqual(restore_runner_driver_diagnostics((HERE / 'runner.py').read_text()), old_runner)
        self.assertEqual((ROOT / 'tools/lib/vmtest.py').read_bytes(), subprocess.check_output(
            ['git', '-C', str(ROOT), 'show', BASE + ':tools/lib/vmtest.py']))
        with self.assertRaises(AssertionError):
            restore_driver_failure_diagnostics(DRIVER.replace('and tb.tb_frame.f_globals is namespace', 'and True', 1))
        with self.assertRaises(AssertionError):
            restore_runner_driver_diagnostics((HERE / 'runner.py').read_text().replace('value[name] not in lines', 'False', 1))

    def test_native_login_inverse_is_exact_881_source_and_mutated_observers_reject(self):
        restored = restore_driver_failure_diagnostics(DRIVER)
        prior = subprocess.check_output(['git', '-C', str(ROOT), 'show',
            '881476b588aaac097f7d1b5d2081af3f118f7c6b:tools/test-install.sh']).decode()
        native_restored = restore_native_login_observation(restored)
        self.assertEqual(SHELL.replace(DRIVER, native_restored, 1), prior)
        for before, after in (('pam_result="not-observed"', 'pam_result="passed"'),
                ('count >= 0.65', 'count >= 0.1'), ('qmp_input = native_login_type(vm, password)', 'qmp_input = "passed"')):
            self.assertEqual(restored.count(before), 1)
            with self.assertRaises(AssertionError):
                restore_native_login_observation(restored.replace(before, after, 1))

    def test_collector_runner_inverse_is_exact_53a_and_mutated_projection_rejects(self):
        restored = restore_runner_driver_diagnostics((HERE / 'runner.py').read_text())
        prior = subprocess.check_output(['git', '-C', str(ROOT), 'show',
            '53a97790670067f504addb749447592d81fb79b5:tools/dictation-qualification/runner.py']).decode()
        self.assertEqual(restore_runner_collector_projection(restored), prior)
        for before, after in (("or value['release_acceptance'] is not False", "or False"),
                ('raw = launch_diagnostic_read(vm,', 'raw = open(vm,'),
                ('relay_collector_failures(vm, phase)', 'relay_collector_failures(vm, "live")')):
            self.assertIn(before, restored)
            with self.assertRaises(AssertionError):
                restore_runner_collector_projection(restored.replace(before, after, 1))

    def test_real_loaded_vm_cmd_traceback_binds_exact_code_globals_and_line(self):
        env = environment()
        vm = object.__new__(vmtest.VM)
        vm.f = io.StringIO()
        out = io.StringIO()
        try:
            vm.cmd('query-status')
        except vmtest.QMPError as error:
            with contextlib.redirect_stdout(out):
                env['dictation_driver_failure']('boot-body', error)
        value, = records(out.getvalue())
        self.assertEqual(value['error'], 'qmp-error')
        self.assertEqual(value['frame'], 'vm-cmd')
        self.assertIn(value['frame_line'], runner.driver_failure_lines()['vm-cmd'])
        self.assertEqual(value['caller'], 'unknown')
        self.assertIs(value['release_acceptance'], False)
        self.assertNotIn('QMP closed', out.getvalue())

    def test_foreign_globals_same_code_clone_and_foreign_code_with_trusted_name_are_unknown(self):
        env = environment()
        clones = [types.FunctionType(vmtest.VM.cmd.__code__, dict(vmtest.__dict__))]
        other = {}
        exec('def cmd(self, name):\n    raise RuntimeError("private transcript")\n', other)
        clones.append(other['cmd'])
        for fn in clones:
            vm = types.SimpleNamespace(f=io.StringIO())
            out = io.StringIO()
            try:
                fn(vm, 'query-status')
            except BaseException as error:
                with contextlib.redirect_stdout(out):
                    env['dictation_driver_failure']('boot-body', error)
            value, = records(out.getvalue())
            self.assertEqual((value['frame'], value['frame_line']), ('unknown', 0))
            self.assertNotIn('private', out.getvalue())

    def test_actual_stage_boot_same_primary_identity_and_exactly_once_cleanup(self):
        for error in (PrivateError('private transcript'), KeyboardInterrupt('private'), SystemExit('private')):
            env = environment()
            cleaned = []
            def fail(*args):
                raise error
            env.update(qemu_argv=fail, close_taskbar_vm=lambda vm, display: cleaned.append((vm, display)))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                try:
                    env['stage_boot']()
                except BaseException as caught:
                    self.assertIs(caught, error)
                else:
                    self.fail('original failure swallowed')
            self.assertEqual(cleaned, [(None, None)])
            value, = records(out.getvalue())
            self.assertEqual(value['scope'], 'boot-body')
            self.assertEqual((value['frame'], value['frame_line']), ('unknown', 0))
            self.assertEqual(value['caller'], 'driver-stage-boot')
            self.assertNotIn('private', out.getvalue())

    def test_actual_stage_cleanup_preserves_original_override_identity_and_two_scopes(self):
        env = environment()
        primary, cleanup = PrivateError('private body'), KeyboardInterrupt('private cleanup')
        calls = []
        def fail(*args):
            raise primary
        def finish(vm, display):
            calls.append((vm, display))
            raise cleanup
        env.update(qemu_argv=fail, close_taskbar_vm=finish)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                env['stage_boot']()
            except BaseException as caught:
                self.assertIs(caught, cleanup)
                self.assertIs(caught.__context__, primary)
        self.assertEqual(calls, [(None, None)])
        self.assertEqual([item['scope'] for item in records(out.getvalue())], ['boot-body', 'boot-cleanup'])
        self.assertNotIn('private', out.getvalue())

    def test_failed_diagnostic_and_second_cancellation_never_replace_primary_or_skip_cleanup(self):
        for interruption in (BrokenPipeError('private'), KeyboardInterrupt('second cancellation')):
            env = environment()
            primary = PrivateError('private')
            calls = []
            def fail(*args):
                raise primary
            env.update(qemu_argv=fail, dictation_host_stage=lambda code: None,
                       close_taskbar_vm=lambda vm, display: calls.append((vm, display)))
            with patch('builtins.print', side_effect=interruption):
                try:
                    env['stage_boot']()
                except BaseException as caught:
                    self.assertIs(caught, primary)
                else:
                    self.fail('primary failure swallowed')
            self.assertEqual(calls, [(None, None)])

    def test_optional_fixture_binding_and_unknown_exception_are_closed(self):
        disabled = environment(False)
        self.assertEqual(disabled['_DICTATION_DRIVER_BINDING'], ())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            disabled['dictation_driver_failure']('boot-body', PrivateError('private'))
            env = environment()
            env['dictation_driver_failure']('private', PrivateError('private'))
            env['dictation_driver_failure']('boot-body', PrivateError('private'))
        value, = records(out.getvalue())
        self.assertEqual((value['error'], value['frame'], value['frame_line']), ('other-error', 'unknown', 0))
        self.assertNotIn('private', out.getvalue())

    def test_truncated_trace_and_incomplete_binding_never_export_partial_source_owner(self):
        env = environment()
        def recurse(depth):
            if depth:
                return recurse(depth - 1)
            raise PrivateError('private')
        out = io.StringIO()
        try:
            recurse(40)
        except BaseException as error:
            with contextlib.redirect_stdout(out):
                env['dictation_driver_failure']('boot-body', error)
        self.assertEqual(out.getvalue(), '')
        env['_DICTATION_DRIVER_BINDING'] = ()
        with contextlib.redirect_stdout(out):
            env['dictation_driver_failure']('boot-cleanup', PrivateError('private'))
        self.assertEqual(out.getvalue(), '')

    def test_actual_collect_loop_observes_vm_cmd_and_keeps_original_cleanup(self):
        env = environment()
        counts, stages = [], []
        ticks = iter(range(0, 20000, 100))
        env['time'] = types.SimpleNamespace(time=lambda: next(ticks), sleep=lambda _: None)
        fake = types.SimpleNamespace(alive=lambda: True, shot=lambda _: 'fixture.png',
            keys=lambda *args: None, type_text=lambda *args, **kwargs: None)
        qmp = object.__new__(vmtest.VM); qmp.f = io.StringIO()
        env.update(qemu_argv=lambda *args: [], dictation_acquire_vm=lambda *args: fake,
            wait_menu=lambda *args: False, wait_for=lambda *args: 'fixture.png',
            open_terminal=lambda *args: None, dictation_host_stage=stages.append,
            dictation_indicator_poll=lambda vm: qmp.cmd('query-status'),
            close_taskbar_vm=lambda vm, display: counts.append((vm, display)))
        with patch.object(vmtest, 'classify', side_effect=lambda _: 'login' if 'boot-login' not in stages else 'desktop'), \
             patch.object(vmtest, 'changed_fraction', return_value=0), contextlib.redirect_stdout(io.StringIO()) as out:
            with self.assertRaises(vmtest.QMPError):
                env['stage_boot']()
        value, = records(out.getvalue())
        self.assertIn('boot-collect', stages)
        self.assertEqual(value['scope'], 'boot-body')
        self.assertEqual(value['frame'], 'vm-cmd')
        self.assertEqual(value['caller'], 'driver-stage-boot')
        self.assertEqual(counts, [(fake, None)])

    def test_strict_source_line_json_parser_rejects_private_fields_types_duplicates_and_nonfinite(self):
        lines = runner.driver_failure_lines()
        value = dict(schema='arctic-dictation-driver-failure-v1', scope='boot-body', error='qmp-error',
                     frame='vm-cmd', frame_line=min(lines['vm-cmd']), caller='unknown', caller_line=0,
                     release_acceptance=False)
        encode = lambda v: json.dumps(v, sort_keys=True).encode()
        self.assertEqual(runner.driver_failure_record(encode(value), lines), value)
        variants = [dict(value, frame='private'), dict(value, frame_line=True), dict(value, frame_line=999999),
            dict(value, caller_line=1), dict(value, release_acceptance=0), dict(value, error='private'),
            dict(value, scope='private'), dict(value, transcript='private'), dict(value, frame_line=float('nan'))]
        for variant in variants:
            self.assertIsNone(runner.driver_failure_record(encode(variant), lines))
        for raw in (encode(value)[:-1] + b',"scope":"boot-body"}', b'\xff', b'{}', b'x'*2049):
            self.assertIsNone(runner.driver_failure_record(raw, lines))

    def test_owned_phase_relay_requires_exact_token_complete_lf_and_preserves_private_bytes(self):
        value = dict(schema='arctic-dictation-driver-failure-v1', scope='boot-body', error='other-error',
                     frame='unknown', frame_line=0, caller='unknown', caller_line=0, release_acceptance=False)
        line = b'ARCTIC-DICTATION-DRIVER-FAILURE ' + TOKEN.encode() + b' ' + json.dumps(value).encode() + b'\n'
        raw = b'private transcript\n' + line.replace(TOKEN.encode(), b'b'*32) + b'guest '+line + line.replace(b'\n', b'\r\n') + line + line + line[:-1]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'phase.log'; path.write_bytes(raw)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                runner.relay_driver_failures(path, TOKEN, 'recovered-offline')
            self.assertEqual(len(out.getvalue().splitlines()), 1)
            self.assertNotIn(TOKEN, out.getvalue())
            self.assertNotIn('private', out.getvalue())
            self.assertEqual(path.read_bytes(), raw)
            # A syntactically valid echo is an observation only, never authenticated origin.
            self.assertIn('OBSERVATION', out.getvalue())
            self.assertIn('"release_acceptance": false', out.getvalue())

    def test_relay_rejects_owned_directory_symlink_fifo_bounds_and_bad_phase_before_io(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root/'phase.log'; path.write_bytes(b'private\n')
            link = root/'link'; link.symlink_to(path)
            fifo = root/'fifo'; os.mkfifo(fifo)
            huge = root/'huge'; huge.touch()
            with huge.open('wb') as stream:
                stream.truncate(16*1024*1024+1)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                for bad in (root, link, fifo, huge, root/'missing'):
                    runner.relay_driver_failures(bad, TOKEN, 'online-installed')
            self.assertEqual(out.getvalue(), '')
            with patch.object(runner, 'launch_diagnostic_read') as read:
                runner.relay_driver_failures(path, TOKEN, 'private')
                runner.relay_driver_failures(path, 'bad', 'online-installed')
                read.assert_not_called()


if __name__ == '__main__':
    unittest.main()
