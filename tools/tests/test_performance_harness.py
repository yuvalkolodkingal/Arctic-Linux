"""Exercise production collection decisions with fake QMP, without a VM/build."""
import ast
import json
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).parents[2]
SOURCE = (ROOT/'tools/test-install.sh').read_text()
DRIVER = SOURCE.split("read -r -d '' DRIVER <<'PY' || true\n", 1)[1].split('\nPY\n', 1)[0]


class PerformanceHarnessTest(unittest.TestCase):
    def capture(self, fresh=True, reuse=False, options=()):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, out = root/'clean-install', root/'boot'
            base.mkdir(); out.mkdir()
            (base/'target.qcow2').write_bytes(b'clean fixture, not a VM disk')
            (base/'OVMF_VARS.fd').write_bytes(b'fixture variables')
            if reuse or not fresh: (out/'target.qcow2').touch()
            context = root/'context.json'
            context.write_text('{"collector":"console"}\n')
            engine = root/'mock-engine'
            engine.write_text('''#!/usr/bin/env python3
import json,os,sys
assert sys.argv[1]=='run'
with open(os.environ['TEST_ENGINE_LOG'],'w') as target: json.dump(sys.argv[1:],target)
''')
            engine.chmod(0o755)
            env = dict(os.environ, CONTAINER_ENGINE=str(engine), TEST_ENGINE_LOG=str(root/'call.json'),
                       HTTPS_PROXY='', https_proxy='', HTTP_PROXY='', http_proxy='',
                       ARCTIC_VM_CONTAINER_NAME='')
            argv = [str(ROOT/'tools/test-install.sh'), '--stage','boot', '--out',str(out)]
            if fresh:
                argv += ['--collect-via','console', '--fresh-boot-from',str(base),
                         '--performance-context',str(context), '--guest-check',str(ROOT/'tools/performance/guest.py')]
            result = subprocess.run(argv+list(options), env=env, text=True, capture_output=True, timeout=20)
            call = json.loads((root/'call.json').read_text()) if (root/'call.json').exists() else None
            values = ({call[index+1].split('=',1)[0]:call[index+1].split('=',1)[1]
                       for index,value in enumerate(call[:-1]) if value=='-e'} if call else None)
            return result, call, values, (out/'data/collect.sh').read_text() if (out/'data/collect.sh').exists() else None

    def test_fresh_boot_accepts_no_existing_disk_and_mounts_backing_source_read_only(self):
        result, call, values, collect = self.capture()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(values['COLLECT_VIA'], 'console')
        base = values['FRESH_BOOT_FROM']
        self.assertIn(base+':'+base+':ro', call)
        self.assertIn('qemu-img check -q "$FRESH_BOOT_FROM/target.qcow2"', call[-1])
        self.assertIn('-F qcow2 -b "$FRESH_BOOT_FROM/target.qcow2"', call[-1])
        self.assertIn('cp "$FRESH_BOOT_FROM/OVMF_VARS.fd"', call[-1])
        self.assertIn('ARCTIC-PERFORMANCE-CONSOLE-RESTORED', collect)
        self.assertEqual(values['BOOT_NETWORK'], 'offline')
        self.assertNotIn('systemd.debug_shell', values['BOOT_APPEND'])

    def test_existing_overlay_or_terminal_collector_is_rejected_before_container(self):
        for kwargs in (dict(reuse=True), dict(options=('--collect-via','terminal'))):
            with self.subTest(kwargs=kwargs):
                result, call, _, _ = self.capture(**kwargs)
                self.assertNotEqual(result.returncode, 0)
                self.assertIsNone(call)
        result, _, values, _ = self.capture(fresh=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(values['COLLECT_VIA'], 'terminal')

    def test_actual_console_qmp_branch_never_opens_a_gui_terminal(self):
        function = next(node for node in ast.parse(DRIVER).body
                        if isinstance(node, ast.FunctionDef) and node.name=='stage_boot')
        loop = next(node for node in ast.walk(function) if isinstance(node, ast.For)
                    and isinstance(node.target, ast.Name) and node.target.id=='attempt'
                    and 'COLLECT_VIA' in ast.unparse(node.iter))
        # Execute the actual loop in its function context. Optional branches can
        # legitimately return early, and compiling them at module scope is invalid.
        wrapper = ast.parse('def collect_branch():\n    pass\n').body[0]
        wrapper.body = [loop, ast.Return(value=ast.Name(id='collected', ctx=ast.Load()))]
        ast.fix_missing_locations(wrapper)
        for mode, native_failed in (('console', False), ('terminal', False), ('terminal', True)):
            vm, terminal = Mock(), Mock()
            namespace = dict(E=dict(COLLECT_VIA=mode, PROFILE_USER='ci', GUEST_CHECK='probe',
                                    GUEST_CHECK_INTERACTIVE='0',
                                    NATIVE_LAUNCHER_FIXTURE='1' if native_failed else '0'),
                vm=vm, time=types.SimpleNamespace(time=lambda:0, sleep=lambda _:None),
                password='test-secret', open_terminal=terminal, serial=lambda _: 'fixture', log=Mock(),
                vmtest=types.SimpleNamespace(serial_has=lambda *_:True), lock_password_sent=False)
            exec(compile(ast.Module(body=[wrapper], type_ignores=[]), '<actual collection branch>','exec'), namespace)
            collected = namespace['collect_branch']()
            if mode=='console':
                terminal.assert_not_called()
                self.assertEqual(vm.keys.call_args_list[0].args, ('ctrl-alt-f3',))
                self.assertEqual([call.args[0] for call in vm.type_text.call_args_list],
                                 ['ci','test-secret','sudo sh /dev/sr0','test-secret'])
            else:
                terminal.assert_called_once()
            if native_failed:
                self.assertEqual(collected, 1)
                self.assertEqual(vm.type_text.call_args_list[0].args, ('sudo sh /dev/sr0; exit',))
                namespace['log'].assert_called_once_with('owned native launcher failed; no retry')
            else:
                self.assertIs(collected, True)

    def test_actual_console_restore_uses_session_vt_and_refuses_wrong_or_inactive_session(self):
        program = SOURCE.split("python3 - <<'PY' || exit 1\n",1)[1].split('\nPY\n',1)[0]
        nodes = [node for node in ast.parse(program).body if not isinstance(node,(ast.Import,ast.ImportFrom))]
        for fault in (None,'wrong_type','invalid_vt','inactive'):
            def child(name):
                return types.SimpleNamespace(read_text=lambda:'mango',
                    read_bytes=lambda:b'XDG_SESSION_ID=7\x00')
            path = Mock()
            # Magic methods require a real type, independent of pathlib's code.
            class Proc:
                def stat(self):return types.SimpleNamespace(st_uid=1000)
                def __truediv__(self,name):return child(name)
            path.glob.return_value = [Proc()]
            def output(argv, **kwargs):
                property = argv[-2]
                return {'Type': 'x11' if fault=='wrong_type' else 'wayland',
                        'VTNr': '0' if fault=='invalid_vt' else '5',
                        'Active': 'no' if fault=='inactive' else 'yes'}[property]
            switch = Mock()
            namespace = dict(Path=lambda _:path, subprocess=types.SimpleNamespace(check_output=output,run=switch),
                             time=types.SimpleNamespace(sleep=lambda _:None), print=Mock())
            if fault:
                with self.subTest(fault=fault), self.assertRaises(RuntimeError):
                    exec(compile(ast.Module(body=nodes,type_ignores=[]),'<actual VT restoration>','exec'),namespace)
                namespace['print'].assert_not_called()
            else:
                exec(compile(ast.Module(body=nodes,type_ignores=[]),'<actual VT restoration>','exec'),namespace)
                switch.assert_called_once_with(['chvt','5'],check=True,timeout=10)
                self.assertIn('session=7 vt=5', namespace['print'].call_args.args[0])

    def test_actual_clean_poweroff_fence_refuses_dirty_or_abnormal_install_source(self):
        function = next(node for node in ast.parse(DRIVER).body
                        if isinstance(node, ast.FunctionDef) and node.name=='stage_install')
        condition = next(node for node in ast.walk(function) if isinstance(node,ast.If)
                         and ast.unparse(node.test)=='not vm.wait_exit(600)')
        wrapper = ast.parse('def poweroff_gate():\n    pass\n').body[0]
        wrapper.body = [condition, ast.Return(value=ast.Constant(value=0))]
        ast.fix_missing_locations(wrapper)
        for exited, returncode, mode, expected in ((False,None,'console',93),(True,1,'console',94),
                                                 (True,0,'console',0),(False,None,'terminal',0)):
            vm = Mock(); vm.wait_exit.return_value=exited; vm.proc.returncode=returncode
            log = Mock()
            namespace = dict(vm=vm,E=dict(COLLECT_VIA=mode),log=log)
            exec(compile(ast.Module(body=[wrapper],type_ignores=[]),'<actual clean poweroff fence>','exec'),namespace)
            self.assertEqual(namespace['poweroff_gate'](),expected)
            clean = any('ARCTIC-PRISTINE-INSTALL-POWEROFF=clean' in call.args[0] for call in log.call_args_list)
            self.assertEqual(clean,exited and returncode==0 and mode=='console')

    def test_outer_and_embedded_shell_and_python_are_syntactically_valid(self):
        subprocess.run(['bash','-n',str(ROOT/'tools/test-install.sh')],check=True,capture_output=True)
        inner = SOURCE.split("inner=$(cat <<'INNER'\n",1)[1].split('\nINNER\n',1)[0]
        subprocess.run(['bash','-n'],input=inner,text=True,check=True,capture_output=True)
        compile(DRIVER,'<actual QMP driver>','exec')


if __name__=='__main__':unittest.main()
