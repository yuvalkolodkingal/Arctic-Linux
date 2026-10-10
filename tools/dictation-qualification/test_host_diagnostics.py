"""Exercise actual host failure paths without booting VMs or exporting private data."""
import ast
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location('dictation_host_diagnostic_runner', HERE / 'runner.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
SHELL = (ROOT / 'tools/test-install.sh').read_text()
DRIVER = SHELL.split("DRIVER <<'PY' || true\n", 1)[1].split('\nPY\n', 1)[0]


class Invalid(Exception):
    pass


class PrivateError(RuntimeError):
    def __str__(self):
        raise AssertionError('private exception must never be formatted')

    @property
    def args(self):
        raise AssertionError('untrusted override must never be read')


def driver_functions(names, env):
    nodes = [node for node in ast.parse(DRIVER).body
             if (isinstance(node, ast.FunctionDef) and node.name in names)
             or (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name)
                     and t.id == 'DICTATION_HOST_STAGES' for t in node.targets))]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<actual host driver>', 'exec'), env)
    return env


class HostDiagnostics(unittest.TestCase):
    def test_failure_selector_never_formats_private_args_or_exports_unknown_literals(self):
        contract = SimpleNamespace(Invalid=Invalid)
        out = io.StringIO()
        errors = [PrivateError('private transcript'), RuntimeError('private transcript'),
                  Invalid('private transcript'), FileNotFoundError('private transcript'),
                  subprocess.TimeoutExpired(['private argv'], 5100, output=b'private transcript'),
                  InterruptedError('private transcript')]
        with contextlib.redirect_stdout(out):
            for error in errors:
                r.diagnostic('online-installed', 'harness', error, contract)
            for reason, code in r.TRUSTED_ERRORS.items():
                r.diagnostic('offline-installed', 'report-live', RuntimeError(reason), contract)
            for code in r.TRUSTED_CONTRACT_ERRORS:
                r.diagnostic('recovery', 'report-installed', Invalid(code), contract)
        text = out.getvalue()
        self.assertNotIn('private', text)
        self.assertIn('harness other-error\n', text)
        self.assertIn('harness runtime-error\n', text)
        self.assertIn('harness contract-invalid\n', text)
        self.assertIn('harness timeout-expired\n', text)
        self.assertIn('report-installed report-context-boot\n', text)
        self.assertIn('report-live serial-missing-or-oversized\n', text)
        for stage, phase in (('private', 'online-installed'), ('harness', 'private')):
            rejected = io.StringIO()
            with contextlib.redirect_stdout(rejected):
                r.diagnostic(phase, stage, RuntimeError('private'), contract)
            self.assertEqual(rejected.getvalue(), '')

    def test_closed_stdout_does_not_replace_failure_or_read_private_args(self):
        with patch('builtins.print', side_effect=ValueError('closed private stream')):
            r.diagnostic('online-installed', 'harness', PrivateError('private'), SimpleNamespace(Invalid=Invalid))

    def test_relay_requires_exact_nonce_fixed_complete_lf_lines_and_deduplicates(self):
        token = 'a' * 32
        prefix = 'ARCTIC-DICTATION-HOST-STAGE '
        raw = (prefix + token + ' install-menu\n' + prefix + token + ' install-menu\n'
               + prefix + 'b' * 32 + ' boot-login\n' + 'guest ' + prefix + token + ' boot-login\n'
               + prefix + token + ' private-transcript\n' + prefix + token + ' boot-login\r\n'
               + prefix + token + ' boot-collect\n' + prefix + token + ' install-engine').encode()
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'private.log'
            log.write_bytes(raw)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                r.relay_host_stages(log, token, 'online-installed')
            self.assertEqual(out.getvalue(),
                'ARCTIC-DICTATION-HOST-PROGRESS online-installed install-menu\n'
                'ARCTIC-DICTATION-HOST-PROGRESS online-installed boot-collect\n')
            for value in ('', 'x' * 32, token + '\n', None):
                with patch.object(r.os, 'open') as opened:
                    r.relay_host_stages(log, value, 'online-installed')
                    opened.assert_not_called()
            with patch('builtins.print', side_effect=BrokenPipeError('private stream')):
                r.relay_host_stages(log, token, 'online-installed')
            self.assertEqual(log.read_bytes(), raw)

    def test_relay_rejects_actual_nonregular_symlink_missing_and_oversized_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            regular = root / 'regular'
            regular.write_text('ARCTIC-DICTATION-HOST-STAGE ' + 'a' * 32 + ' install-menu\n')
            link = root / 'link'; link.symlink_to(regular)
            fifo = root / 'fifo'; os.mkfifo(fifo)
            sock = socket.socket(socket.AF_UNIX)
            sock.bind(str(root / 'socket'))
            huge = root / 'huge'
            with huge.open('wb') as stream:
                stream.truncate(16 * 1024 * 1024 + 1)
            try:
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    for path in (root, link, fifo, root / 'socket', root / 'missing', huge):
                        r.relay_host_stages(path, 'a' * 32, 'online-installed')
                self.assertEqual(out.getvalue(), '')
            finally:
                sock.close()

    def test_actual_embedded_driver_and_shell_stage_emission_is_fixed_and_optional(self):
        env = driver_functions({'dictation_host_stage'}, {'E': {}})
        self.assertEqual(env['DICTATION_HOST_STAGES'], r.HOST_STAGES - {
            'host-data', 'host-container', 'container-packages', 'container-audio',
            'container-data', 'container-disk', 'container-profile', 'container-driver', 'container-complete'})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            env['dictation_host_stage']('install-menu')
            env['E']['ARCTIC_DICTATION_HOST_TOKEN'] = 'a' * 32
            env['dictation_host_stage']('private transcript')
            env['dictation_host_stage']('install-menu')
        self.assertEqual(out.getvalue(), 'ARCTIC-DICTATION-HOST-STAGE ' + 'a' * 32 + ' install-menu\n')
        with patch('builtins.print', side_effect=BrokenPipeError('private')):
            env['dictation_host_stage']('install-menu')
        function = SHELL.split('dictation_host_stage() {', 1)[1].split('\n}\n', 1)[0]
        program = 'dictation_host_stage() {' + function + '\n}\n'
        for token, expected in (('', ''), ('bad', ''), ('a' * 32,
                'ARCTIC-DICTATION-HOST-STAGE ' + 'a' * 32 + ' host-data\n')):
            result = subprocess.run(['bash', '-c', program + '\ndictation_host_stage host-data\ndictation_host_stage "private transcript"\n'],
                env=dict(os.environ, ARCTIC_DICTATION_HOST_TOKEN=token), capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, expected)
        result = subprocess.run(['bash', '-c', program + '\nexec 1>&-\ndictation_host_stage host-data\n'],
            env=dict(os.environ, ARCTIC_DICTATION_HOST_TOKEN='a' * 32), capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0)

    def test_actual_install_loop_distinguishes_process_exit_from_budget_without_changing_rc(self):
        for dead in (False, True):
            codes, cleanup = [], []
            ticks = iter((0, 1, 2, 3, 4, 5, 6 if dead else 3006, 3007))
            alive = iter((True, True, False))
            vm = SimpleNamespace(keys=lambda *a:None, type_text=lambda *a, **kw:None,
                shot=lambda *a:None, alive=lambda:next(alive),
                proc=SimpleNamespace(poll=lambda:17 if dead else None))
            serial_has = lambda path, marker: marker in ('live session mode:', 'ARCTIC-TEST-STARTED')
            env = driver_functions({'stage_install', 'dictation_install_wait_vm_stage', 'dictation_launch_desktop'}, dict(E={'GUEST_CHECK':'fixture'},
                taskbar_display_module=None, vmtest=SimpleNamespace(VM=lambda *a:vm,
                    serial_has=serial_has, serial_value=lambda *a:None),
                time=SimpleNamespace(time=lambda:next(ticks), sleep=lambda seconds:None),
                dictation_host_stage=codes.append, dictation_cpu_argv=lambda x:x,
                native_taskbar_argv=lambda *a:a[0], dictation_network_argv=lambda *a:a[0],
                qemu_argv=lambda *a:[], wait_menu=lambda *a:False, open_terminal=lambda *a:None,
                serial=lambda name:name, log=lambda msg:None, install_timeout=2400,
                close_taskbar_vm=lambda vm, display:cleanup.append((vm, display))))
            self.assertEqual(env['stage_install'](), 91)
            self.assertIn('install-start-observed', codes)
            self.assertIn('install-exit-missing-vm-exited' if dead else 'install-exit-missing-vm-running', codes)
            self.assertEqual(codes[-1], 'install-cleanup')
            self.assertEqual(cleanup, [(vm, None)])

    def test_actual_boot_acquire_failure_still_runs_original_owned_cleanup(self):
        codes, cleanup = [], []
        def fail(*args):
            raise RuntimeError('private QEMU stderr')
        env = driver_functions({'stage_boot'}, dict(E={}, taskbar_display_module=None,
            vmtest=SimpleNamespace(VM=fail), dictation_host_stage=codes.append,
            dictation_cpu_argv=lambda x:x, native_taskbar_argv=lambda *a:a[0],
            dictation_network_argv=lambda *a:a[0], qemu_argv=lambda *a:[],
            close_taskbar_vm=lambda vm, display:cleanup.append((vm, display))))
        with self.assertRaisesRegex(RuntimeError, 'private QEMU'):
            env['stage_boot']()
        self.assertEqual(codes, ['boot-acquire', 'boot-cleanup'])
        self.assertEqual(cleanup, [(None, None)])

    def test_run_actual_catches_save_failure_and_keep_owned_cleanup_for_every_phase(self):
        for target in ('online-installed', 'offline-installed', 'recovery', 'recovered-offline'):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); here = root / 'tools/dictation-qualification'; here.mkdir(parents=True)
                (root / 'tools/dictation-accuracy').mkdir()
                fixtures = root / 'fixtures'; fixtures.mkdir(); (fixtures/'fixtures.json').write_text('{}')
                evidence = root / 'evidence'; evidence.mkdir()
                args = SimpleNamespace(evidence=evidence, fixtures=fixtures, source=root,
                    inputs=root, hardware_profile='small-v2')
                manifest = dict(image={'name':'candidate.iso'}, fixture_manifest_sha256='a'*64)
                private = evidence.parent / 'dictation-private-small-v2'
                tokens = []
                def execute(argv, log, timeout, env, container):
                    if log.name == 'provision.log':
                        (private/'vm-prepared-image-id.txt').write_text('b'*64)
                        return
                    phase = log.stem
                    token = env['ARCTIC_DICTATION_HOST_TOKEN']; tokens.append(token)
                    self.assertRegex(token, '^[0-9a-f]{32}$')
                    self.assertNotIn(token, (private/('payload-'+phase)/'dictation-context.json').read_text())
                    if phase == target:
                        log.write_text('ARCTIC-DICTATION-HOST-STAGE '+token+' install-start-marker\n')
                        raise subprocess.TimeoutExpired(['private argv'], timeout, output=b'private transcript')
                def reports(vm, stage, ctx, *other):
                    if ctx['phase'] == target:
                        raise Invalid('report-context-boot' if stage == 'live' else 'private transcript')
                    return {'path':'synthetic.json'}
                def indicator(vm, ctx, evidence):
                    if ctx['phase'] == target:
                        raise FileNotFoundError('private transcript')
                    return {'synthetic':True}
                out = io.StringIO(); contract = SimpleNamespace(Invalid=Invalid)
                with patch.object(r,'ROOT',root), patch.object(r,'HERE',here), \
                     patch.object(r,'verify',return_value=manifest), patch.object(r.Path,'is_char_device',return_value=True), \
                     patch.object(r.subprocess,'check_output'), patch.object(r,'load_module',return_value=contract), \
                     patch.object(r.signal,'signal'), patch.object(r,'execute',side_effect=execute), \
                     patch.object(r,'context',side_effect=lambda m,i,p,s,h:{'phase':p}), \
                     patch.object(r,'reports',side_effect=reports), patch.object(r,'indicator',side_effect=indicator), \
                     patch.object(r.subprocess,'run') as cleanup, patch.dict(os.environ,{'GITHUB_SHA':'c'*40}), \
                     contextlib.redirect_stdout(out):
                    with self.assertRaisesRegex(RuntimeError,'Exact image dictation phase failed'):
                        r.run(args)
                state=json.loads((evidence/'execution.json').read_text())
                self.assertEqual(state['status'],'failed_or_unrun')
                self.assertEqual(state['current_phase'],target)
                self.assertIs(state['release_acceptance'],False)
                self.assertEqual(state['error'],'Qualification failed; inspect private Actions harness logs')
                self.assertIn(' '+target+' harness timeout-expired\n',out.getvalue())
                self.assertIn(' '+target+' install-start-marker\n',out.getvalue())
                self.assertIn(' '+target+' report-installed contract-invalid\n',out.getvalue())
                self.assertNotIn('private',out.getvalue())
                self.assertEqual(len(tokens),len(set(tokens)))
                cleanup.assert_called_once_with(['docker','image','rm','b'*64], stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, timeout=30)

    def test_actual_execute_signal_cleanup_is_unchanged_and_propagates_original_exception(self):
        failure = InterruptedError('private signal text')
        child = Mock(pid=123, poll=Mock(return_value=None), wait=Mock(side_effect=[failure, 0]))
        with tempfile.TemporaryDirectory() as tmp, patch.object(r.subprocess,'Popen',return_value=child), \
             patch.object(r.subprocess,'run',side_effect=subprocess.TimeoutExpired(['private argv'],30)), \
             patch.object(r.os,'killpg') as kill:
            with self.assertRaises(InterruptedError) as caught:
                r.execute(['private argv'],Path(tmp)/'private.log',1,{},'arctic-paired-dictation-'+'a'*32)
            self.assertIs(caught.exception,failure)
            kill.assert_called_once_with(123,r.signal.SIGTERM)


if __name__ == '__main__':
    unittest.main()
