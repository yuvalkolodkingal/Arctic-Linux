"""Exercise the real embedded harness decisions without starting a guest."""
import ast
import json
import subprocess
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
DRIVER = (ROOT / 'tools/test-install.sh').read_text().split("DRIVER <<'PY' || true\n", 1)[1].split('\nPY\n', 1)[0]


def functions(names, env):
    nodes = [node for node in ast.parse(DRIVER).body if isinstance(node, ast.FunctionDef) and node.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<actual VM harness>', 'exec'), env)
    return env


class HarnessControls(unittest.TestCase):
    def test_fixture_cleanup_stops_owned_qemu_and_bus_after_qmp_deadline(self):
        order = []
        failure = RuntimeError('owned QMP absolute deadline exceeded')
        class Process:
            dead = False
            def poll(self): return -9 if self.dead else None
            def wait(self, timeout):
                order.append('bounded-wait')
                if not self.dead: raise subprocess.TimeoutExpired('owned-qemu', timeout)
            def terminate(self): order.append('terminate')
            def kill(self):
                order.append('kill')
                self.dead = True
        class Display:
            def close(self): order.append('private-bus-cleanup')
        def query(vm, command, seconds):
            order.append('bounded-qmp-quit')
            raise failure
        env = functions({'close_taskbar_vm'}, {'taskbar_display_module': type('Module', (), {'qmp_query':staticmethod(query)})})
        vm = type('VM', (), {'proc':Process(), 'quit':lambda self: (_ for _ in ()).throw(AssertionError('unbounded legacy quit'))})()
        with self.assertRaisesRegex(RuntimeError, 'absolute deadline'):
            env['close_taskbar_vm'](vm, Display())
        self.assertTrue(vm.proc.dead)
        self.assertEqual(order, ['bounded-qmp-quit', 'bounded-wait', 'terminate', 'bounded-wait', 'kill', 'private-bus-cleanup'])

    def test_fixture_free_cleanup_uses_the_original_vm_quit(self):
        calls = []
        env = functions({'close_taskbar_vm'}, {})
        vm = type('VM', (), {'quit':lambda self: calls.append('original-quit')})()
        env['close_taskbar_vm'](vm, None)
        self.assertEqual(calls, ['original-quit'])

    def test_native_dual_output_fixture_preserves_default_gpu_and_network_choices(self):
        for flags, expected in (({}, 'virtio'), ({'NATIVE_TWO_OUTPUTS': '1', 'NATIVE_TASKBAR_FIXTURE': '1'}, 'none')):
            env = functions({'qemu_argv', 'native_taskbar_argv'}, dict(E=flags, accel='kvm', mem='4096', smp='2', out='/fixture', fw='bios'))
            base = env['qemu_argv']('fixture', True)
            self.assertEqual(base[base.index('-vga') + 1], 'virtio')
            argv = env['native_taskbar_argv'](base, 'fixture', 'dbus,addr=unix:path=/tmp/arctic-tb-display-fixture/bus,gl=off')
            self.assertEqual(argv[argv.index('-vga') + 1], expected)
            self.assertEqual(argv.count('virtio-vga,id=arctic_taskbar_gpu,max_outputs=2'), 1 if expected == 'none' else 0)
            self.assertEqual(sum('name=arctic-taskbar-evidence' in x for x in argv), 1 if expected == 'none' else 0)
            if expected == 'none':
                self.assertEqual(argv[argv.index('-chardev')+1], 'file,id=taskbar_evidence,path=/fixture/taskbar-fixture.log')
                self.assertEqual(argv[argv.index('-display')+1], 'dbus,addr=unix:path=/tmp/arctic-tb-display-fixture/bus,gl=off')
                self.assertEqual(argv.count('-S'), 1)
            else:
                self.assertEqual(argv, base)
            self.assertEqual(argv[argv.index('-netdev') + 1], 'user,id=net0,restrict=on')

    def test_two_output_fixture_rejects_unbound_or_nonprivate_display(self):
        for flags, address in (({'NATIVE_TWO_OUTPUTS': '1'}, 'dbus,addr=unix:path=/tmp/arctic-tb-display-fixture/bus,gl=off'),
                               ({'NATIVE_TWO_OUTPUTS': '1', 'NATIVE_TASKBAR_FIXTURE': '1'}, None),
                               ({'NATIVE_TWO_OUTPUTS': '1', 'NATIVE_TASKBAR_FIXTURE': '1'}, 'none')):
            env = functions({'qemu_argv', 'native_taskbar_argv'}, dict(E=flags, accel='kvm', mem='4096', smp='2', out='/fixture', fw='bios'))
            with self.assertRaisesRegex(RuntimeError, 'private taskbar'):
                env['native_taskbar_argv'](env['qemu_argv']('fixture', False), 'fixture', address)

    def test_uiinfo_completion_precedes_bounded_continue_and_preserves_timeout(self):
        with tempfile.TemporaryDirectory() as temp:
            order = []
            class VM:
                def cmd(self, command):
                    order.append(command)
                    return {'return': {'running': True}} if command == 'query-status' else {'return': {}}
            def query(vm, command, seconds):
                self.assertEqual(seconds, 10)
                return vm.cmd(command)['return']
            module = type('Module', (), {'qmp_query':staticmethod(query)})
            env = functions({'enable_taskbar_display'}, dict(E={'NATIVE_TASKBAR_DISPLAY_SHA': 'a'*64}, out=temp,
                taskbar_display_module=module))
            class Display:
                def enable(self, vm):
                    order.append('two-owned-heads-prepared')
                    return {'schema': 'source-control-fixture'}
            vm = VM()
            env['enable_taskbar_display'](vm, Display(), 'boot')
            self.assertEqual(order, ['two-owned-heads-prepared', 'cont', 'query-status'])
            proof = json.loads(Path(temp, 'taskbar-display-boot.json').read_text())
            self.assertEqual(proof['controller_sha256'], 'a'*64)

    def test_failed_continue_cannot_reach_original_guest_driver(self):
        with tempfile.TemporaryDirectory() as temp:
            class VM:
                calls = []
                def cmd(self, command):
                    self.calls.append(command)
                    return {'error': {'class': 'fixture-failure'}}
            def query(vm, command, seconds):
                self.assertEqual(seconds, 10)
                answer = vm.cmd(command)
                if 'error' in answer: raise RuntimeError('owned QMP command failed')
                return answer['return']
            module = type('Module', (), {'qmp_query':staticmethod(query)})
            env = functions({'enable_taskbar_display'}, dict(E={'NATIVE_TASKBAR_DISPLAY_SHA': 'a'*64}, out=temp,
                taskbar_display_module=module))
            class Display:
                def enable(self, vm): return {'schema': 'source-control-fixture'}
            vm = VM()
            with self.assertRaisesRegex(RuntimeError, 'QMP command failed'):
                env['enable_taskbar_display'](vm, Display(), 'boot')
            self.assertEqual(vm.calls, ['cont'])

    def test_default_boot_only_online_and_install_only_online_networks_remain_independent(self):
        for flags, expected in (({}, (False, False)), ({'BOOT_NETWORK': 'online'}, (False, True)),
                                ({'INSTALL_NETWORK': 'online'}, (True, False)),
                                ({'ONLINE_PROXY': '1'}, (True, True))):
            env = functions({'qemu_argv', 'dictation_network_argv'}, dict(E=flags, accel='kvm', mem='4096', smp='2', out='/fixture', fw='bios'))
            for with_iso, online in zip((True, False), expected):
                argv = env['dictation_network_argv'](env['qemu_argv']('fixture', with_iso), with_iso)
                self.assertEqual(argv[argv.index('-netdev') + 1], 'user,id=net0' + ('' if online else ',restrict=on'))

    def test_legacy_cpu_fixture_masks_only_fixed_features_and_keeps_original_input(self):
        for cpu in ('host', 'max'):
            original = ['qemu-system-x86_64', '-cpu', cpu, '-netdev', 'user,id=net0,restrict=on']
            env = functions({'dictation_cpu_argv'}, {'E': {'NATIVE_DICTATION_CPU_PROFILE': 'small-v2', 'DICTATION_FIXTURE': '1'}})
            changed = env['dictation_cpu_argv'](original)
            self.assertEqual(changed, [original[0], '-cpu', cpu + ',-avx,-avx2,-fma,-f16c,-bmi1,-bmi2', *original[3:]])
            self.assertEqual(original[2], cpu)

    def test_modern_and_default_cpu_fixture_preserve_original_model(self):
        original = ['qemu-system-x86_64', '-cpu', 'host', '-smp', '2']
        for flags in ({}, {'NATIVE_DICTATION_CPU_PROFILE': 'turbo-q5-v3', 'DICTATION_FIXTURE': '1'}):
            env = functions({'dictation_cpu_argv'}, {'E': flags})
            self.assertEqual(env['dictation_cpu_argv'](original), original)

    def test_cpu_fixture_rejects_unknown_profile_or_missing_actual_dictation_bundle(self):
        original = ['qemu-system-x86_64', '-cpu', 'host']
        for flags in ({'NATIVE_DICTATION_CPU_PROFILE': 'small-v2'},
                      {'NATIVE_DICTATION_CPU_PROFILE': 'max,+avx512', 'DICTATION_FIXTURE': '1'}):
            env = functions({'dictation_cpu_argv'}, {'E': flags})
            with self.assertRaisesRegex(RuntimeError, 'Invalid dictation CPU fixture'):
                env['dictation_cpu_argv'](original)

    def indicator_env(self, root, request):
        (root / 'data').mkdir()
        (root / 'data/dictation-context.json').write_text(json.dumps(dict(phase='online-installed',
            installation_id='11111111-1111-1111-1111-111111111111', iso_sha256='a' * 64)))
        serial = root / 'serial-boot.log'
        serial.write_text('ARCTIC-DICTATION-RECORDING-INDICATOR-REQUESTED ' + json.dumps(request) + '\n')
        return functions({'dictation_indicator_poll'}, dict(E={'DICTATION_FIXTURE': '1'}, out=str(root),
                         dictation_indicator_seen=False, serial=lambda stage: str(serial)))

    def test_indicator_request_rejects_nonempty_receiver_before_capture(self):
        request = dict(phase='online-installed', installation_id='11111111-1111-1111-1111-111111111111',
                       boot_id='22222222-2222-2222-2222-222222222222', desktop_uid=1000,
                       receiver_empty=False, capture_nonce='a' * 32)
        with tempfile.TemporaryDirectory() as temp:
            env = self.indicator_env(Path(temp), request)
            with self.assertRaisesRegex(RuntimeError, 'Invalid dictation indicator'):
                env['dictation_indicator_poll'](None)
            self.assertFalse(env['dictation_indicator_seen'])

    def test_indicator_capture_is_hashed_and_exactly_once(self):
        request = dict(phase='online-installed', installation_id='11111111-1111-1111-1111-111111111111',
                       boot_id='22222222-2222-2222-2222-222222222222', desktop_uid=1000,
                       receiver_empty=True, capture_nonce='a' * 32)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            env = self.indicator_env(root, request)
            class VM:
                calls = []
                sequence = []
                def shot(self, name):
                    self.calls.append(name)
                    self.sequence.append('capture-complete')
                    path = root / (name + '.png')
                    path.write_bytes(b'\x89PNG\r\n\x1a\nfixture-transport')
                    return path
                def type_text(self, text, gap):
                    self.sequence.append('ack-delivered')
                    self.ack = text
            vm = VM()
            env['dictation_indicator_poll'](vm)
            env['dictation_indicator_poll'](vm)
            self.assertEqual(vm.calls, ['dictation-indicator-online-installed'])
            self.assertEqual(vm.sequence, ['capture-complete', 'ack-delivered'])
            self.assertEqual(vm.ack, request['capture_nonce'])
            receipt = json.loads((root / 'dictation-indicator-receipt.json').read_text())
            self.assertEqual(receipt['request'], request)
            self.assertEqual(receipt['iso_sha256'], 'a' * 64)
            self.assertEqual(len(receipt['sha256']), 64)
