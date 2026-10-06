#!/usr/bin/env python3
"""Host-only negative controls. No VM/Docker/Git mutation or guest execution."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import types
import unittest
from unittest.mock import patch
import zlib

import yaml

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), HERE / name)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


D = load('safe-driver-v1.py'); G = load('guest-safe-collector-v1.py')
H = load('safe-runner-v1.py'); P = load('prepare-safe-v1.py')
R = load('../same-iso-recovery/vm-only-recovery-v2.py')


class Clock:
    def __init__(self): self.now = 20.0
    def time(self): return self.now
    def sleep(self, seconds): self.now += seconds


class FakeVM:
    def __init__(self, root, clock, failure=None):
        self.root, self.clock, self.failure = root, clock, failure
        self.inputs = []; self.sent = False; self.marker_clock = None
    def alive(self): return self.failure != 'dead'
    def shot(self, name):
        if self.failure == 'screenshot': return None
        path = self.root / (name + '.png'); path.write_bytes(b'fake-image'); return str(path)
    def cmd(self, name, **args):
        self.inputs.append((self.clock.time(), name, args)); return {'error': {}} if self.failure == 'pointer' else {'return': {}}
    def keys(self, *args):
        self.inputs.append((self.clock.time(), 'keys', args))
        self.clock.sleep(.3)  # actual frozen vmtest.keys default delay
        if self.sent and self.marker_clock is None:
            self.marker_clock = self.clock.time()
            self.update()
    def type_text(self, text, gap):
        self.inputs.append((self.clock.time(), 'type', text)); self.sent = True
    def update(self):
        if self.marker_clock is None: return
        ready = 'ARCTIC-SAFE-GRIM-READY ' + json.dumps(dict(wait_seconds=20)) + '\n'
        if self.failure == 'duplicate': ready += ready
        text = ready
        if self.failure == 'early' or self.clock.time() >= self.marker_clock+20:
            text += 'ARCTIC-SAFE-GRIM-BEGIN {}\nARCTIC-SAFE-GRIM-DONE {}\n'
        if self.clock.time() >= self.marker_clock+21 and self.failure != 'missing-end':
            text += 'ARCTIC-SAFE-END ' + json.dumps(dict(status='failed' if self.failure == 'failed-end' else 'collected',
                        error='test' if self.failure == 'failed-end' else None, release_acceptance=False)) + '\n'
        (self.root / 'serial.log').write_text(text)


def run_fake(root, failure=None, menu=True):
    clock = Clock(); vm = FakeVM(root, clock, failure)
    def sleep(seconds): clock.sleep(seconds); vm.update()
    D.run(vm, root, dict(monotonic_estimate_seconds=0, start_ticks=0, ticks_per_second=100,
          precision_seconds=.01), 20.0, menu, clock.time, sleep)
    return vm, [json.loads(v) for v in (root / 'safe-events.log').read_text().splitlines()]


def protocol(files=None, report_changes=None, end_changes=None):
    report = dict(schema='arctic-safe-telemetry-v1', collector_sha256='a'*64,
        release_acceptance=False, safe_visual_gate='open', live_welcome_opacity='unobserved',
        effective_render_loop='unobserved', status='read-only-telemetry-collected-visual-gate-open',
        cmdline='rd.live.image nomodeset', desktop_uid=1000,
        security_before_grim=dict(selinux='Enforcing', avc_records=[]),
        security_after_grim=dict(selinux='Enforcing', avc_records=[]))
    journal = b'{"_TRANSPORT":"kernel","MESSAGE":"fixture, not actual guest evidence"}\n'
    for name in ('security_before_grim', 'security_after_grim'):
        report[name].update(audit_status='enabled 1\nlost 0\n', current_boot_journal_records=1,
                            journal_retained_bytes=len(journal), journal_total_bytes=len(journal),
                            journal_retained_sha256=hashlib.sha256(journal).hexdigest())
    image = b'\x89PNG\r\n\x1a\nfixture'
    report['grim'] = dict(sha256=hashlib.sha256(image).hexdigest())
    report.update(report_changes or {})
    values = dict(files or {}, **{'report.json': json.dumps(report).encode(), 'guest-grim.png': image})
    values.update({'system-journal-before-grim.log': journal, 'system-journal-after-grim.log': journal})
    manifest = dict(schema='arctic-safe-files-v1', encoding='zlib+base64', files=[], bytes=sum(len(d) for d in values.values()))
    chunks = []
    for name, data in values.items():
        packed = zlib.compress(data)
        manifest['files'].append(dict(path=name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), compressed_bytes=len(packed), chunks=1))
        chunks.append(dict(path=name, index=0, data=base64.b64encode(packed).decode()))
    end = dict(status='collected', error=None, release_acceptance=False); end.update(end_changes or {})
    records = [('BEGIN', dict(collector_sha256='a'*64, release_acceptance=False)), ('REPORT', report), ('MANIFEST', manifest)]
    records += [('CHUNK', c) for c in chunks]; records.append(('END', end))
    return records


def serial(records):
    return '\n'.join('ARCTIC-SAFE-' + n + ' ' + json.dumps(v) for n, v in records)


class DriverControls(unittest.TestCase):
    def test_event_separation_and_minimum_quiet(self):
        with tempfile.TemporaryDirectory() as t:
            vm, events = run_fake(Path(t)); H.validate_events(Path(t) / 'safe-events.log')
            self.assertGreaterEqual(vm.inputs[0][0], 740)
            self.assertEqual([v[1] for v in vm.inputs], ['input-send-event', 'keys', 'keys', 'type', 'keys'])
            self.assertEqual(vm.inputs[1][2], ('meta_l-ret',)); self.assertEqual(vm.inputs[2][2], ('ret',))
            self.assertEqual({v['type'] for v in vm.inputs[0][2]['events']}, {'abs'})
            self.assertTrue(all('qemu_elapsed_seconds' in v and 'entry_elapsed_seconds' in v for v in events))
            for phase, filename in (('super-enter', 'safe-20-super-enter-01s.png'), ('return-only', 'safe-30-return-01s.png')):
                origin = next(v for v in events if v['event'] == phase)['monotonic_seconds']
                capture = next(v for v in events if v.get('name') == filename)['monotonic_seconds']
                self.assertAlmostEqual(capture-origin, 1)
    def test_fail_closed_on_driver_failures(self):
        for failure in ('dead', 'screenshot', 'pointer', 'duplicate', 'early', 'failed-end', 'missing-end'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as t:
                with self.assertRaises(RuntimeError): run_fake(Path(t), failure)
    def test_quiet_interval_includes_screenshot_call_latency(self):
        original = FakeVM.shot
        def delayed(vm, name):
            vm.clock.sleep(.2)
            return original(vm, name)
        with tempfile.TemporaryDirectory() as t, patch.object(FakeVM, 'shot', delayed):
            _, events = run_fake(Path(t)); H.validate_events(Path(t)/'safe-events.log')
            passive = next(e for e in events if e['event'] == 'passive-end')
            quiet = next(e for e in events if e['event'] == 'quiet-end')
            self.assertGreaterEqual(quiet['monotonic_seconds'] - passive['monotonic_seconds'], 120)
    def test_no_menu_or_reused_evidence(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(RuntimeError): run_fake(Path(t), menu=False)
            (Path(t) / 'safe-events.log').write_text('preserve me')
            with self.assertRaises(RuntimeError): run_fake(Path(t))
            self.assertEqual((Path(t) / 'safe-events.log').read_text(), 'preserve me')
    def test_shortened_passive_and_reversed_events_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            _, events = run_fake(Path(t)); path = Path(t) / 'safe-events.log'
            for mode in ('shortened', 'reversed', 'bad-origin', 'nan', 'missing-capture', 'duplicate-capture'):
                changed = json.loads(json.dumps(events))
                if mode == 'reversed': changed.reverse()
                elif mode == 'missing-capture': changed = [v for v in changed if v.get('name') != 'safe-30-return-05s.png']
                elif mode == 'duplicate-capture': changed.insert(-1, changed[-2])
                else:
                    for row in changed:
                        if row['event'] == 'passive-end':
                            if mode == 'shortened': row['entry_elapsed_seconds'] = 599
                            elif mode == 'bad-origin': row['qemu_elapsed_seconds'] += 1
                            elif mode == 'nan': row['monotonic_seconds'] = float('nan')
                path.write_text('\n'.join(json.dumps(v) for v in changed))
                with self.subTest(mode=mode), self.assertRaises(RuntimeError): H.validate_events(path)


class TransportControls(unittest.TestCase):
    def extract(self, data):
        with tempfile.TemporaryDirectory() as t:
            return H.extract(serial(data), Path(t) / 'guest', 'a'*64)
    def test_complete_transport_retains_open_gate(self):
        value = self.extract(protocol()); self.assertFalse(value['release_acceptance'])
        self.assertEqual(value['status'], 'collected_visual_gate_open')
    def test_traversal_and_reserved_overwrite_rejected(self):
        for name in ('../report.txt', '/tmp/file.txt', 'serial-report.json'):
            with self.subTest(name=name), self.assertRaises(RuntimeError): self.extract(protocol({name: b'control'}))
    def test_missing_duplicate_reordered_and_unknown_chunks(self):
        data = protocol()
        variants = [data[:-1], data + [data[-1]], data + [('CHUNK', dict(path='unknown.txt', index=0, data='AAAA'))],
                    data[-1:] + data[:-1]]
        for mode in ('index', 'hash', 'base64', 'size'):
            changed = json.loads(json.dumps(data))
            for name, value in changed:
                if name == 'CHUNK' and mode == 'index': value['index'] = 1; break
                if name == 'CHUNK' and mode == 'base64': value['data'] = '!!!!'; break
                if name == 'MANIFEST' and mode == 'hash': value['files'][0]['sha256'] = 'b'*64; break
                if name == 'MANIFEST' and mode == 'size': value['files'][0]['bytes'] = H.MAX_FILE+1; break
            variants.append(changed)
        for i, value in enumerate(variants):
            with self.subTest(variant=i), self.assertRaises((RuntimeError, ValueError)): self.extract(value)
    def test_security_failure_and_claim_changes_rejected(self):
        changes = [dict(release_acceptance=True), dict(safe_visual_gate='passed'), dict(live_welcome_opacity=1),
                   dict(effective_render_loop='basic'), dict(cmdline='rd.live.image'),
                   dict(security_after_grim=dict(selinux='Permissive', avc_records=[])),
                   dict(security_before_grim=dict(selinux='Enforcing', avc_records=['denied']))]
        for v in changes:
            with self.subTest(change=v), self.assertRaises(RuntimeError): self.extract(protocol(report_changes=v))
        for audit in ('enabled 0\nlost 0\n', 'enabled 1\nlost 1\n'):
            data = protocol()
            state = next(value for name, value in data if name == 'REPORT')['security_before_grim'].copy()
            state['audit_status'] = audit
            with self.subTest(audit=audit), self.assertRaises(RuntimeError):
                self.extract(protocol(report_changes=dict(security_before_grim=state)))


class SourceSecurityControls(unittest.TestCase):
    def test_sudo_avc_text_is_not_kernel_denial(self):
        samples = [dict(_TRANSPORT='syslog', SYSLOG_IDENTIFIER='sudo', MESSAGE='COMMAND=grep avc: denied'),
                   dict(_TRANSPORT='kernel', MESSAGE='audit: avc: denied { read } for pid=1'),
                   dict(_TRANSPORT='audit', MESSAGE='type=AVC msg=audit(1): denied')]
        self.assertEqual(G.kernel_avcs(samples), samples[1:])
    def test_whitelist_keeps_actual_motion_and_drops_secrets(self):
        self.assertEqual(G.whitelisted_env(dict(ARCTIC_REDUCE_MOTION='1', ARCTIC_SHELL='quickshell',
                         QT_QUICK_BACKEND='software', SECRET='secret', GH_TOKEN='secret', ARCTIC_TOKEN='secret')),
                         dict(ARCTIC_REDUCE_MOTION='1', ARCTIC_SHELL='quickshell', QT_QUICK_BACKEND='software'))
    def test_guard_before_temp_evidence_creation(self):
        with patch.object(G.os, 'geteuid', return_value=1000), patch.object(G.tempfile, 'mkdtemp', side_effect=AssertionError('unguarded write')):
            with patch('builtins.print'):
                self.assertEqual(G.main(), 1)
    def test_source_include_order_and_missing_optional(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); (root/'child.conf').write_text('animations=0\n')
            (root/'config.conf').write_text('source=child.conf\nsource-optional=absent.conf\n')
            value = G.mango_sources(root/'config.conf', str(root))
            self.assertEqual([v['declared'] for v in value], ['child.conf', 'absent.conf'])
            self.assertEqual(value[1]['status'], 'unavailable')
    def test_ci_rejects_all_other_modes_and_reused_identity(self):
        env = dict(GITHUB_ACTIONS='true', GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_REPOSITORY=R.REPOSITORY,
                   GITHUB_API_URL='https://api.github.com', GITHUB_SHA='b'*40, GITHUB_RUN_ID='40000000000',
                   GITHUB_RUN_ATTEMPT='1', RELEASE_REQUESTED='false', SAFE_DIAGNOSTIC_MODE='true', RECOVERY_MODE='false',
                   NATIVE_SMOKE_MODE='false', NIX_REQUESTED='false', PERFORMANCE_REQUESTED='false', BOOT_TEST_REQUESTED='false')
        H.validate_ci(env, R)
        for key in ('RECOVERY_MODE', 'RELEASE_REQUESTED', 'NATIVE_SMOKE_MODE', 'NIX_REQUESTED', 'PERFORMANCE_REQUESTED', 'BOOT_TEST_REQUESTED'):
            with self.subTest(key=key), self.assertRaises(RuntimeError): H.validate_ci(dict(env, **{key:'true'}), R)
        for values in (dict(GITHUB_SHA=H.BASE), dict(GITHUB_RUN_ID='37520174911'), dict(GITHUB_EVENT_NAME='push'),
                       dict(GITHUB_REPOSITORY='other/repo'), dict(SAFE_DIAGNOSTIC_MODE='false')):
            with self.subTest(values=values), self.assertRaises(RuntimeError): H.validate_ci(dict(env, **values), R)
    def test_preparation_reproduces_exact_patch(self):
        base_test, base_workflow = P.base_sources()
        prepared_test = HERE/'prepared-test-iso.sh' if (HERE/'prepared-test-iso.sh').exists() else HERE.parents[1]/'tools/test-iso.sh'
        prepared_workflow = HERE/'registered-iso-safe-v1.yml' if (HERE/'registered-iso-safe-v1.yml').exists() else HERE.parents[1]/'.github/workflows/iso.yml'
        self.assertEqual(P.harness(base_test), prepared_test.read_text())
        self.assertEqual(P.workflow(base_workflow), prepared_workflow.read_text())
        self.assertIn('SAFE_DIAGNOSTIC=""', prepared_test.read_text())
    def test_default_driver_retains_original_collect_block(self):
        original = P.base_sources()[0]; prepared = P.harness(original)
        start = 'if collect and vm.alive():'; end = '\nPY\n'
        self.assertEqual(original[original.index(start):original.index(end)], prepared[prepared.index(start):prepared.index(end)])
    def test_workflow_fixed_sources_and_other_job_guards(self):
        wf = yaml.load(P.workflow(P.base_sources()[1]), Loader=yaml.BaseLoader)
        self.assertEqual(wf['on']['workflow_dispatch']['inputs']['safe_visual_diagnostic']['default'], 'false')
        self.assertEqual(set(wf['jobs']), {'iso', 'same-iso-installs', 'same-iso-boot-evidence', 'safe-visual-diagnostic'})
        for name in ('iso', 'same-iso-installs', 'same-iso-boot-evidence'):
            self.assertIn('!inputs.safe_visual_diagnostic', wf['jobs'][name]['if'])
        job = wf['jobs']['safe-visual-diagnostic']; self.assertNotIn('matrix', job.get('strategy', {}))
        refs = [v['with']['ref'] for v in job['steps'] if v.get('uses', '').startswith('actions/checkout@')]
        self.assertEqual(refs, [R.SOURCE, H.BASE, '${{ github.sha }}'])
        execution = next(v for v in job['steps'] if v.get('with', {}).get('path') == 'safe-execution-source')
        self.assertEqual(execution['with']['fetch-depth'], '0')
        download = next(v for v in job['steps'] if v.get('uses', '').startswith('actions/download-artifact@'))
        self.assertEqual(download['with']['artifact-ids'], str(R.ARTIFACT_ID))
        self.assertEqual(job['permissions'], {'contents':'read', 'actions':'read'})
    def test_frozen_primitive_reuse_and_source_scope(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); bundle = root/'tools/safe-visual-diagnostic'; bundle.mkdir(parents=True)
            manifest = dict(schema=H.SCHEMA, candidate_source=R.SOURCE, qualification_base=H.BASE,
                            files={p:'a'*64 for p in H.EXECUTION_FILES})
            (bundle/'execution-pins-safe-v1.json').write_text(json.dumps(manifest))
            args = types.SimpleNamespace(bundle=bundle, source=Path('/fixture/candidate'), recovery_bundle=Path('/fixture/frozen/tools/same-iso-recovery'))
            fake = types.SimpleNamespace(SOURCE=R.SOURCE)
            with patch.dict(os.environ, GITHUB_SHA='b'*40), patch.object(H.subprocess, 'run') as git_run:
                with patch.object(H.subprocess, 'check_output', side_effect=['b'*40+'\n', '', '.github/workflows/iso.yml\ntools/test-iso.sh\n']):
                    fake.verify_sources = unittest.mock.Mock(); fake.pinned_file = unittest.mock.Mock()
                    H.verify_sources(args, fake)
                    fake.verify_sources.assert_called_once_with(args.source, args.recovery_bundle, H.BASE)
                    git_run.assert_called_once_with(['git','-C',str(root),'merge-base','--is-ancestor',H.BASE,'b'*40], check=True, timeout=30)
                    self.assertEqual(fake.pinned_file.call_count, len(H.EXECUTION_FILES))
                for changed in ('.github/workflows/iso.yml\ntools/test-iso.sh\nshell/Theme.qml\n', 'tools/test-iso.sh\n'):
                    with patch.object(H.subprocess, 'check_output', side_effect=['b'*40+'\n','',changed]), self.assertRaises(RuntimeError):
                        H.verify_sources(args, fake)
            poisoned = root/'frozen'; poisoned.mkdir(); (poisoned/'vm-only-recovery-v2.py').write_text('raise AssertionError("imported before hash guard")')
            with self.assertRaises(RuntimeError): H.recovery(types.SimpleNamespace(recovery_bundle=poisoned))


class DiagnosticCDControls(unittest.TestCase):
    """Execute the real inner Bash with inert command functions; never start QEMU."""
    @staticmethod
    def capture(source, out, safe, firmware='uefi', secureboot='0'):
        start = "inner=$(cat <<'INNER'\n"
        assert source.count(start) == 1
        inner = source.split(start, 1)[1].split('\nINNER\n', 1)[0]
        capture = out / 'qemu-argv.json'
        functions = r'''
dnf() { :; }
qemu-img() { :; }
cp() { :; }
mkdir() { :; }
xorriso() { :; }
rpm() { :; }
sha256sum() { :; }
qemu-system-x86_64() { printf '%s\n' 'mock QEMU version'; }
rm() { :; }
chown() { :; }
python3() {
  "$ARGV_PYTHON" -c 'import json,os,sys; open(os.environ["ARGV_CAPTURE"],"w").write(json.dumps(sys.argv[1:]))' "${@:3}"
}
'''
        env = dict(os.environ, ARGV_PYTHON=sys.executable, ARGV_CAPTURE=str(capture),
                   OUT=str(out), SAFE_DIAGNOSTIC=str(safe), FIRMWARE=firmware,
                   SECUREBOOT=secureboot, SMP='2', MEMORY='4096', VGA='virtio',
                   DRIVER='not executed', HOST_UID='0', HOST_GID='0')
        subprocess.run(['bash', '-euo', 'pipefail', '-c', functions + inner],
                       env=env, check=True, timeout=10, capture_output=True, text=True)
        return json.loads(capture.read_text())

    @staticmethod
    def require_separate_readonly_cd(argv):
        def values(flag):
            return [argv[i + 1] for i, value in enumerate(argv[:-1]) if value == flag]
        assert argv[0] == 'qemu-system-x86_64'
        assert values('-machine') == ['q35']
        assert values('-drive') == [
            'file=/iso,media=cdrom,readonly=on,if=none,id=cd',
            'file=/tmp/target.qcow2,if=none,id=disk',
            'if=pflash,format=raw,unit=0,readonly=on,file=/usr/share/edk2/ovmf/OVMF_CODE.fd',
            'if=pflash,format=raw,unit=1,file=/tmp/vars.fd',
            'file=/tmp/safe-data.iso,media=cdrom,readonly=on,if=none,id=safedata']
        assert values('-device') == [
            'ide-cd,drive=cd,bootindex=0', 'virtio-blk-pci,drive=disk,bootindex=1',
            'virtio-net-pci,netdev=net0', 'qemu-xhci', 'usb-tablet',
            'ide-cd,drive=safedata,bus=ide.1,unit=0']
        assert values('-netdev') == ['user,id=net0,restrict=on']

    def test_readonly_diagnostic_cd_uses_separate_q35_port(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / 'output with spaces'; out.mkdir()
            argv = self.capture(P.harness(P.base_sources()[0]), out, 1)
            self.require_separate_readonly_cd(argv)
            self.assertEqual(argv[argv.index('-qmp') + 1],
                             'unix:' + str(out) + '/qmp.sock,server=on,wait=off')

    def test_previous_and_invalid_cd_assignments_are_rejected(self):
        fixed = P.harness(P.base_sources()[0])
        selector = 'ide-cd,drive=safedata,bus=ide.1,unit=0'
        self.assertEqual(fixed.count(selector), 1)
        with tempfile.TemporaryDirectory() as t:
            out = Path(t)
            for bad in ('ide-cd,drive=safedata',
                        'ide-cd,drive=safedata,bus=ide.0,unit=0',
                        'ide-cd,drive=safedata,bus=ide.1,unit=1'):
                with self.subTest(selector=bad):
                    argv = self.capture(fixed.replace(selector, bad, 1), out, 1)
                    with self.assertRaises(AssertionError):
                        self.require_separate_readonly_cd(argv)
                    # The recorded failure used the first old selector exactly.
                    self.assertIn(bad, argv)

    def test_default_qemu_arguments_unchanged(self):
        original = P.base_sources()[0]; prepared = P.harness(original)
        with tempfile.TemporaryDirectory() as t:
            out = Path(t)
            for firmware, secureboot in (('bios', '0'), ('uefi', '0'), ('uefi', '1')):
                with self.subTest(firmware=firmware, secureboot=secureboot):
                    original_argv = self.capture(original, out, 0, firmware, secureboot)
                    prepared_argv = self.capture(prepared, out, 0, firmware, secureboot)
                    self.assertEqual(original_argv, prepared_argv)
                    self.assertFalse(any('safedata' in value for value in prepared_argv))


if __name__ == '__main__':
    unittest.main(verbosity=2)
