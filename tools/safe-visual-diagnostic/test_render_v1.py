#!/usr/bin/env python3
"""Host-only tests; no framebuffer, client, VM, Docker or network execution."""
import ast
import base64
import ctypes
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zlib

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), HERE / name)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
D = load('safe-driver-v1.py'); H = load('safe-runner-v1.py'); T = load('test_safe_v1.py')
R = load('render-driver-v1.py'); G = load('guest-render-collector-v1.py')


def valid_geometry():
    var, fix = G.Variable(), G.Fixed()
    var.xres = var.xres_virtual = 2; var.yres = var.yres_virtual = 2; var.bits_per_pixel = 32
    for field, offset in [('red', 16), ('green', 8), ('blue', 0)]:
        getattr(var, field).offset = offset; getattr(var, field).length = 8
    fix.line_length = 8; fix.smem_len = 16; fix.visual = 2
    return var, fix


class TickingClock(T.Clock):
    def __init__(self, tick): super().__init__(); self.tick = tick
    def time(self):
        now = self.now; self.now += self.tick; return now


def original(root, tick=0):
    clock = TickingClock(tick); vm = T.FakeVM(root, clock)
    def sleep(seconds): clock.sleep(seconds); vm.update()
    D.run(vm, root, dict(monotonic_estimate_seconds=0, start_ticks=0, ticks_per_second=100, precision_seconds=.01), 20.0, True, clock.time, sleep)
    H.validate_events(root / 'safe-events.log')
    return clock


class RenderVM:
    def __init__(self, root, clock, failure=None):
        self.root, self.clock, self.failure = root, clock, failure
        self.oldserial = (root / 'serial.log').read_text(); self.start = None; self.inputs = []
    def alive(self): return self.failure != 'dead'
    def shot(self, name):
        if self.failure in ('screenshot', 'failure-screenshot'):
            if self.failure == 'screenshot' or name == 'render-98-failure': return None
        p = self.root / (name + '.png'); p.write_bytes(b'fixture'); return str(p)
    def type_text(self, text, gap): self.inputs.append(('type', text))
    def keys(self, key): self.inputs.append(('key', key)); self.start = self.clock.time(); self.update()
    def update(self):
        if self.start is None: return
        elapsed = self.clock.time() - self.start
        markers = [('BEGIN', 0, dict(release_acceptance=False)), ('FB-READY', 0, dict(wait_seconds=10)), ('FB-DONE', 10, {}), ('FOOT-START', 15, {})]
        markers += [('FOOT-FB', 15 + s, dict(label='foot-%02ds' % s, seconds_after_owned_launch=s)) for s in (1, 5, 60)]
        markers += [('GRIM-READY', 77, dict(wait_seconds=10)), ('GRIM-BEGIN', 87, {}), ('GRIM-DONE', 88, {}), ('END', 95, dict(status='collected-inconclusive', error=None, release_acceptance=False))]
        if self.failure in ('early-foot',): markers[3] = ('FOOT-START', 10, {})
        if self.failure == 'early-grim': markers[-3] = ('GRIM-BEGIN', 77, {})
        if self.failure in ('failed-end', 'failure-screenshot'): markers[-1][2]['status'] = 'failed'; markers[-1][2]['error'] = 'fixture preserved original failure'
        if self.failure == 'timeout': markers = markers[:-1]
        text = self.oldserial
        for name, when, value in markers:
            if elapsed >= when:
                line = 'ARCTIC-RENDER-' + name + ' ' + json.dumps(value) + '\n'; text += line
                if self.failure == 'duplicate' and name == 'FB-READY': text += line
        (self.root / 'serial.log').write_text(text)


def run_new(root, failure=None, tick=0):
    clock = original(root, tick); vm = RenderVM(root, clock, failure)
    def sleep(seconds): clock.sleep(seconds); vm.update()
    R.run(vm, root, clock.time, sleep)
    return vm


def transport(report_change=None, file_change=None, message='host fixture only', channel='kernel', journal_boot='123456781234123412341234567890ab'):
    journal = (json.dumps(dict(_TRANSPORT=channel, _BOOT_ID=journal_boot, MESSAGE=message)) + '\n').encode()
    var, fix = valid_geometry(); meta = G.metadata(var, fix); image = G.png(bytes(16), meta)
    security = dict(selinux='Enforcing', avc_records=[], audit_status='enabled 1\nlost 0\n', journal_retained_bytes=len(journal), journal_retained_sha256=G.sha(journal), current_boot_journal_records=1)
    frames = [dict(label=name, status='read-only-snapshot', active_scanout='unproven', guest_begin_ns=1, guest_end_ns=2, metadata=meta, raw_bytes=16, raw_sha256=G.sha(bytes(16)), png='framebuffer-' + name + '.png', png_sha256=G.sha(image), png_bytes=len(image)) for name in ['baseline', 'foot-01s', 'foot-05s', 'foot-60s', 'after-grim']]
    for value, seconds in zip(frames[1:4], (1, 5, 60)): value['seconds_after_owned_launch'] = seconds
    tail = ['/usr/bin/foot', '--app-id=arctic-safe-render-arctic-render-evidence-fixture', '/usr/bin/python3', '/run/arctic-safe/fixed-rows-v1.py', 'arctic-safe-render-arctic-render-evidence-fixture']
    report = dict(schema='arctic-render-telemetry-v1', collector_sha256='a' * 64, status='diagnostic-collected-inconclusive', release_acceptance=False, safe_visual_gate='open', effective_render_loop='unobserved', compositor_gl_renderer='unobserved', desktop_uid=1000, boot_id='12345678-1234-1234-1234-1234567890ab', cmdline='rd.live.image nomodeset', cleanup=dict(status='owned-launch-exited'), framebuffers=frames, unavailable=[], grim=dict(sha256=G.sha(image)), owned_launch=dict(foot=dict(pid=4, uid=1000, start_ticks=5, executable='/usr/bin/foot', cmdline=tail), wrapper=dict(pid=3, uid=0, start_ticks=4, executable='/usr/bin/runuser'), rows=dict(pid=5, uid=1000, start_ticks=6, executable='/usr/bin/python3.14', cmdline=tail[-3:]), fixed_rows_sha256=G.sha((HERE / 'fixed-rows-v1.py').read_bytes()), argv=['/usr/sbin/runuser', '-u', 'liveuser', '--', '/usr/bin/env', '-i'] + tail))
    report['owned_launch']['foot_process_group'] = 3
    for key in ('security_before', 'security_before_grim', 'security_after'): report[key] = json.loads(json.dumps(security))
    if report_change: report_change(report)
    files = {'report.json': json.dumps(report).encode(), 'render-grim.png': image}
    files.update({v['png']: image for v in frames if 'png' in v})
    files.update({'system-journal-' + label + '.log': journal for label in ('render-before', 'render-before-grim', 'render-after')})
    if file_change: file_change(files)
    manifest = dict(schema='arctic-render-files-v1', encoding='zlib+base64', files=[], bytes=sum(len(v) for v in files.values()))
    chunks = []
    for name, data in files.items():
        packed = zlib.compress(data); manifest['files'].append(dict(path=name, bytes=len(data), sha256=G.sha(data), compressed_bytes=len(packed), chunks=1))
        chunks.append(('CHUNK', dict(path=name, index=0, data=base64.b64encode(packed).decode())))
    return [('BEGIN', dict(collector_sha256='a' * 64, release_acceptance=False)), ('REPORT', report), ('MANIFEST', manifest), *chunks, ('END', dict(status='collected-inconclusive', error=None, release_acceptance=False))]


def serial(protocol): return '\n'.join('ARCTIC-RENDER-' + name + ' ' + json.dumps(value) for name, value in protocol)


class GeometryTests(unittest.TestCase):
    def test_bounded_elf_build_id_metadata_and_adverse_note_headers(self):
        head = bytearray(64); head[:6] = b'\x7fELF\x02\x01'; struct.pack_into('<Q', head, 32, 64); struct.pack_into('<HH', head, 54, 56, 1)
        note = struct.pack('<III', 4, 20, 3) + b'GNU\0' + bytes(range(20))
        header = struct.pack('<IIQQQQQQ', 4, 0, 120, 0, 0, len(note), len(note), 4)
        for mode in ('valid', 'wrong-abi', 'bad-ph-size', 'note-overflow', 'note-offset', 'note-record'):
            data = bytearray(head + header + note)
            if mode == 'wrong-abi': data[4] = 1
            elif mode == 'bad-ph-size': struct.pack_into('<H', data, 54, 64)
            elif mode == 'note-overflow': struct.pack_into('<Q', data, 64 + 32, 65537)
            elif mode == 'note-offset': struct.pack_into('<Q', data, 64 + 8, len(data))
            elif mode == 'note-record': struct.pack_into('<I', data, 120 + 4, 999)
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                p = Path(temp) / 'library.so'; p.write_bytes(data)
                if mode == 'valid': self.assertEqual(G.elf_build_id(p), bytes(range(20)).hex())
                else:
                    with self.assertRaises(RuntimeError): G.elf_build_id(p)
    def test_normal_device_reader_uses_only_getters_and_readonly_open(self):
        v, f = valid_geometry(); info = types.SimpleNamespace(st_mode=0o020600, st_rdev=os.makedev(29, 0), st_ino=3)
        calls = []
        def ioctl(fd, request, buffer, mutate):
            calls.append(request); buffer[:] = bytes(v if request == G.FBIOGET_VSCREENINFO else f)
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(G.os, 'lstat', return_value=info), patch.object(G.Path, 'read_text', return_value='29:0'), patch.object(G.os, 'open', return_value=99) as opened, patch.object(G.os, 'fstat', return_value=info), patch.object(G.fcntl, 'ioctl', side_effect=ioctl), patch.object(G.os, 'pread', return_value=bytes(16)) as read, patch.object(G.os, 'close'):
                result = G.framebuffer(Path(temp), 'fixture')
                self.assertEqual(opened.call_args.args[1] & os.O_ACCMODE, os.O_RDONLY)
                read.assert_called_once_with(99, 16, 0)
            self.assertEqual(calls, [G.FBIOGET_VSCREENINFO, G.FBIOGET_FSCREENINFO] * 2)
            self.assertEqual(result['status'], 'read-only-snapshot'); self.assertEqual(result['active_scanout'], 'unproven')
            self.assertEqual(result['raw_sha256'], hashlib.sha256(bytes(16)).hexdigest())
            self.assertTrue((Path(temp) / result['png']).is_file())
    def test_abi_and_decoded_pixels(self):
        self.assertEqual(ctypes.sizeof(G.Variable), 160); self.assertEqual(ctypes.sizeof(G.Fixed), 80)
        var, fix = valid_geometry(); meta = G.metadata(var, fix)
        image = G.png(bytes([3, 2, 1, 255] * 4), meta)
        self.assertEqual(struct.unpack('>II', image[16:24]), (2, 2))
        offset = 8; content = b''
        while offset < len(image):
            size = struct.unpack_from('>I', image, offset)[0]; kind = image[offset + 4:offset + 8]; payload = image[offset + 8:offset + 8 + size]
            self.assertEqual(zlib.crc32(kind + payload) & 0xffffffff, struct.unpack_from('>I', image, offset + 8 + size)[0])
            if kind == b'IDAT': content += payload
            offset += 12 + size
        self.assertEqual(zlib.decompress(content), b'\0' + bytes([1, 2, 3] * 2) + b'\0' + bytes([1, 2, 3] * 2))
    def test_invalid_geometry_and_short_reads(self):
        cases = [('width', lambda v, f: setattr(v, 'xres', 4097)), ('height', lambda v, f: setattr(v, 'yres', 2161)), ('bpp', lambda v, f: setattr(v, 'bits_per_pixel', 24)), ('offset', lambda v, f: setattr(v, 'xoffset', 1)), ('stride', lambda v, f: setattr(f, 'line_length', 7)), ('allocation', lambda v, f: setattr(f, 'smem_len', G.MAX_RAW + 1)), ('shortalloc', lambda v, f: setattr(f, 'smem_len', 15)), ('channel-overlap', lambda v, f: setattr(v.red, 'offset', 8)), ('channel-msb', lambda v, f: setattr(v.red, 'msb_right', 1)), ('nonstd', lambda v, f: setattr(v, 'nonstd', 1)), ('pseudocolor', lambda v, f: setattr(f, 'visual', 3)), ('rotation', lambda v, f: setattr(v, 'rotate', 1))]
        for name, mutate in cases:
            with self.subTest(name=name):
                v, f = valid_geometry(); mutate(v, f)
                with self.assertRaises(RuntimeError): G.metadata(v, f)
        v, f = valid_geometry()
        with self.assertRaises(RuntimeError): G.png(bytes(15), G.metadata(v, f))
    def test_permission_device_and_getter_failures_have_no_pixels(self):
        for mode in ('denied', 'wrong-device', 'getter'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                info = types.SimpleNamespace(st_mode=0o020600, st_rdev=os.makedev(29 if mode != 'wrong-device' else 1, 0), st_ino=3)
                with patch.object(G.os, 'lstat', return_value=info), patch.object(G.Path, 'read_text', return_value='29:0'), patch.object(G.os, 'open', side_effect=PermissionError('fixture denied') if mode == 'denied' else None, return_value=99), patch.object(G.os, 'fstat', return_value=info), patch.object(G.fcntl, 'ioctl', side_effect=OSError('fixture unsupported getter')), patch.object(G.os, 'close'):
                    result = G.framebuffer(Path(temp), 'fixture')
                self.assertEqual(result['status'], 'unavailable'); self.assertIn('error', result); self.assertNotIn('png', result); self.assertEqual(list(Path(temp).iterdir()), [])


class DriverTests(unittest.TestCase):
    def test_arm_begin_single_sample_survives_realistic_clock_call_latency(self):
        for tick in (.000005, .005):
            with self.subTest(tick=tick), tempfile.TemporaryDirectory() as temp:
                p = Path(temp); run_new(p, tick=tick); H.validate_events(p / 'safe-events.log'); R.validate_events(p / 'render-events.log', p / 'safe-events.log')
                first = json.loads((p / 'render-events.log').read_text().splitlines()[0])
                self.assertEqual(first['arm_elapsed_seconds'], 0)
    def test_all_original_phases_precede_added_inputs_and_captures(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp); vm = run_new(p); H.validate_events(p / 'safe-events.log'); R.validate_events(p / 'render-events.log', p / 'safe-events.log')
            self.assertEqual(vm.inputs, [('type', R.COMMAND), ('key', 'ret')])
            self.assertEqual(len([e for e in (p / 'safe-events.log').read_text().splitlines() if json.loads(e)['event'] == 'capture']), 34)
    def test_missing_original_and_early_execution_have_no_side_effects(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp); clock = original(p); vm = RenderVM(p, clock)
            rows = [json.loads(line) for line in (p / 'safe-events.log').read_text().splitlines()]; rows.pop()
            (p / 'safe-events.log').write_text('\n'.join(json.dumps(v) for v in rows))
            with self.assertRaises(RuntimeError): R.run(vm, p, clock.time, clock.sleep)
            self.assertEqual(vm.inputs, []); self.assertFalse((p / 'render-events.log').exists())
    def test_failures_preserve_original_and_error(self):
        for failure in ('dead', 'screenshot', 'duplicate', 'early-foot', 'early-grim', 'failed-end', 'timeout', 'failure-screenshot'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                p = Path(temp)
                with self.assertRaises(RuntimeError): run_new(p, failure)
                H.validate_events(p / 'safe-events.log')
                log = (p / 'render-events.log').read_text(); self.assertIn('arm-failure', log)
                if failure == 'failure-screenshot': self.assertIn('fixture preserved original failure', log); self.assertIn('failure-capture-error', log)
    def test_capture_marker_clock_and_meaning_controls(self):
        for mode in ('capture', 'marker', 'early-origin', 'elapsed', 'nonfinite', 'timeout', 'acceptance'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                p = Path(temp); run_new(p); rows = [json.loads(line) for line in (p / 'render-events.log').read_text().splitlines()]
                if mode == 'capture': rows = [v for v in rows if v.get('name') != 'render-10-foot-60s.png']
                elif mode == 'marker': rows.insert(2, dict(next(v for v in rows if v['event'] == 'guest-marker')))
                elif mode == 'early-origin': rows[0]['original_complete_monotonic_seconds'] -= 1
                elif mode == 'elapsed': rows[2]['arm_elapsed_seconds'] += .01
                elif mode == 'nonfinite': rows[2]['monotonic_seconds'] = math.nan
                elif mode == 'timeout': rows[-1]['monotonic_seconds'] += 180
                else: rows[-1]['release_acceptance'] = True
                (p / 'render-events.log').write_text('\n'.join(json.dumps(v) for v in rows))
                with self.assertRaises(RuntimeError): R.validate_events(p / 'render-events.log', p / 'safe-events.log')


class TransportTests(unittest.TestCase):
    def test_strict_uid_pid_time_and_elapsed_types(self):
        cases = [('bool-root', lambda r: r['owned_launch']['wrapper'].update(uid=False)), ('float-user', lambda r: r['owned_launch']['foot'].update(uid=1000.0)), ('float-child', lambda r: r['owned_launch']['rows'].update(uid=1000.0)), ('negative-interval', lambda r: r['framebuffers'][0].update(guest_begin_ns=-2, guest_end_ns=-1)), ('bool-interval', lambda r: r['framebuffers'][0].update(guest_begin_ns=True)), ('overlapping-child', lambda r: r['owned_launch']['rows'].update(pid=r['owned_launch']['foot']['pid'])), ('overlapping-wrapper', lambda r: r['owned_launch']['wrapper'].update(pid=r['owned_launch']['foot']['pid'])), ('bool-group', lambda r: r['owned_launch'].update(foot_process_group=True)), ('nan-sample', lambda r: r['framebuffers'][1].update(seconds_after_owned_launch=math.nan)), ('infinite-sample', lambda r: r['framebuffers'][1].update(seconds_after_owned_launch=math.inf))]
        for name, mutate in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                with self.assertRaises(RuntimeError): R.extract(serial(transport(mutate)), Path(temp) / 'output', 'a' * 64)
    def test_raw_trusted_avc_and_wrong_boot_are_not_hidden_by_report(self):
        for name, options, rejected in [('kernel', dict(message='avc: denied { read }'), True), ('audit', dict(message='type=USER_AVC denied', channel='audit'), True), ('sudo-command-literal', dict(message="COMMAND=grep 'avc:.*denied'", channel='syslog'), False), ('wrong-boot', dict(journal_boot='0' * 32), True)]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                if rejected:
                    with self.assertRaises(RuntimeError): R.extract(serial(transport(**options)), Path(temp) / 'output', 'a' * 64)
                else:
                    self.assertEqual(R.extract(serial(transport(**options)), Path(temp) / 'output', 'a' * 64)['status'], 'diagnostic_only_inconclusive')
    def test_positive_protocol_and_explicit_unavailable(self):
        for unavailable in (False, True):
            def change(report):
                if unavailable:
                    value = report['framebuffers'][0]; value.update(status='unavailable', error='fixture EACCES')
                    for key in ('png', 'png_sha256', 'png_bytes', 'raw_bytes', 'raw_sha256', 'metadata'): value.pop(key)
                    report['unavailable'] = ['baseline']
            with self.subTest(unavailable=unavailable), tempfile.TemporaryDirectory() as temp:
                value = R.extract(serial(transport(change)), Path(temp) / 'output', 'a' * 64)
                self.assertEqual(value['status'], 'diagnostic_only_inconclusive'); self.assertFalse(value['release_acceptance'])
    def test_security_owned_identity_missing_evidence_and_false_claims(self):
        cases = [('avc', lambda r: r['security_after'].update(avc_records=[{'MESSAGE': 'avc: denied'}])), ('lost', lambda r: r['security_before'].update(audit_status='enabled 1\nlost 1\n')), ('permissive', lambda r: r['security_after'].update(selinux='Permissive')), ('uid', lambda r: r['owned_launch']['foot'].update(uid=0)), ('exec', lambda r: r['owned_launch']['foot'].update(executable='/usr/bin/sh')), ('starttick', lambda r: r['owned_launch']['foot'].update(start_ticks=0)), ('cleanup', lambda r: r['cleanup'].update(status='refused')), ('metadata-overflow', lambda r: r['framebuffers'][0]['metadata'].update(xres=2 ** 32)), ('metadata-format', lambda r: r['framebuffers'][0]['metadata'].update(bits_per_pixel=24)), ('boot-id', lambda r: r.update(boot_id='bad')), ('scanout-claim', lambda r: r['framebuffers'][0].update(active_scanout='proven')), ('fake-unavailable', lambda r: r['framebuffers'][0].update(status='unavailable', error='fixture')), ('missing-unavailable', lambda r: r.update(unavailable=['baseline'])), ('renderer-claim', lambda r: r.update(compositor_gl_renderer='llvmpipe')), ('acceptance', lambda r: r.update(release_acceptance=True)), ('config-flag', lambda r: r['owned_launch']['argv'].insert(-1, '--config=/tmp/override'))]
        for mode, mutate in cases:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                with self.assertRaises(RuntimeError): R.extract(serial(transport(mutate)), Path(temp) / 'output', 'a' * 64)
    def test_protocol_path_chunk_and_bounds_controls(self):
        for mode in ('duplicate', 'order', 'path', 'reserved', 'chunks', 'sha', 'bound', 'missing-pixels', 'end-error'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                values = transport()
                if mode == 'duplicate': values.insert(0, values[0])
                elif mode == 'order': values[1], values[2] = values[2], values[1]
                elif mode in ('path', 'reserved'): values[2][1]['files'][0]['path'] = '../bad.json' if mode == 'path' else 'serial-report.json'
                elif mode == 'chunks': values.insert(-1, next(v for v in values if v[0] == 'CHUNK'))
                elif mode == 'sha': values[2][1]['files'][0]['sha256'] = 'b' * 64
                elif mode == 'bound': values[2][1]['files'][0]['bytes'] = R.MAX_FILE + 1
                elif mode == 'missing-pixels': values = transport(file_change=lambda f: f.pop('render-grim.png'))
                else: values[-1][1]['error'] = 'actual preserved fixture error'
                with self.assertRaises(RuntimeError): R.extract(serial(values), Path(temp) / 'output', 'a' * 64)


class CleanupTests(unittest.TestCase):
    def test_real_owned_popen_pipe_closed_on_all_cleanup_paths(self):
        import gc, subprocess, warnings
        for mode in ('already-exited', 'owned-cleanup', 'primary-failure'):
            with self.subTest(mode=mode), warnings.catch_warnings():
                warnings.simplefilter('error', ResourceWarning)
                child = subprocess.Popen([sys.executable, '-c', 'import sys,time;sys.stderr.write("owned fixture\\n");sys.stderr.flush();time.sleep(0 if sys.argv[1] == "exit" else 10)', 'exit' if mode == 'already-exited' else 'wait'], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, start_new_session=True)
                try:
                    if mode == 'already-exited': child.wait(timeout=3)
                    os.set_blocking(child.stderr.fileno(), False)
                    obj = G.OwnedFoot(T.G, types.SimpleNamespace(pw_uid=os.getuid()), {}, 'owned-host-pipe-only')
                    obj.child = child
                    if mode != 'already-exited': obj.wrapper = T.G.process(child.pid)
                    if mode == 'primary-failure':
                        obj.wrapper['start_ticks'] += 1
                        with self.assertRaisesRegex(RuntimeError, 'wrapper reused/changed'): obj.cleanup()
                    else:
                        result = obj.cleanup(); self.assertIn(result['status'], ('already-exited', 'owned-launch-exited'))
                    self.assertTrue(child.stderr.closed)
                finally:
                    if child.poll() is None: child.terminate(); child.wait(timeout=3)
                    child.stderr.close()
                del child, obj; gc.collect()
    def test_pipe_close_error_does_not_replace_primary_cleanup_error(self):
        proof = dict(pid=3, start_ticks=1)
        pipe = types.SimpleNamespace(closed=False, close=lambda: (_ for _ in ()).throw(OSError('secondary close error')))
        C = types.SimpleNamespace(process=lambda pid: {**proof, 'start_ticks': 2})
        obj = G.OwnedFoot(C, types.SimpleNamespace(pw_uid=1000), {}, 'fixture'); obj.wrapper=proof; obj.child=types.SimpleNamespace(pid=3, stderr=pipe, poll=lambda: None)
        with self.assertRaisesRegex(RuntimeError, 'wrapper reused/changed'): obj.cleanup()
    def test_pidfd_target_is_pinned_and_rechecked_without_pid_signal_fallback(self):
        proof = dict(pid=4, uid=1000, start_ticks=2)
        for reuse in (False, True):
            C = types.SimpleNamespace(process=lambda pid: {**proof, 'start_ticks': 3} if reuse else proof)
            with self.subTest(reuse=reuse), patch.object(G.os, 'pidfd_open', return_value=99) as opened, patch.object(G.os, 'close') as closed, patch.object(G.signal, 'pidfd_send_signal') as sent, patch.object(G.os, 'kill') as raw:
                if reuse:
                    with self.assertRaises(RuntimeError): G.signal_owned(C, proof)
                    sent.assert_not_called()
                else:
                    G.signal_owned(C, proof); sent.assert_called_once_with(99, signal.SIGTERM, None, 0)
                opened.assert_called_once_with(4, 0); closed.assert_called_once_with(99); raw.assert_not_called()
    def test_rows_child_identity_refuses_changed_child_before_signalling_it(self):
        wrapper = dict(pid=3, uid=0, start_ticks=1); foot = dict(pid=4, uid=1000, start_ticks=2); rows = dict(pid=5, uid=1000, start_ticks=3)
        C = types.SimpleNamespace(process=lambda pid: wrapper if pid == 3 else foot if pid == 4 else {**rows, 'start_ticks': 4})
        obj = G.OwnedFoot(C, types.SimpleNamespace(pw_uid=1000), {}, 'fixture'); obj.wrapper=wrapper; obj.foot=foot; obj.foot_group=3; obj.rows=rows
        obj.child = types.SimpleNamespace(pid=3, stderr=None, poll=lambda: None)
        with patch.object(G.os, 'getpgid', return_value=3), patch.object(G, 'signal_owned') as sent:
            with self.assertRaises(RuntimeError): obj.cleanup()
            sent.assert_called_once_with(C, foot)
    def test_cleanup_timeout_and_surviving_group_remain_failures(self):
        import subprocess
        wrapper = dict(pid=3, uid=0, start_ticks=1); foot = dict(pid=4, uid=1000, start_ticks=2)
        for failure in ('timeout', 'survivor'):
            C = types.SimpleNamespace(process=lambda pid: wrapper if pid == 3 else foot)
            obj = G.OwnedFoot(C, types.SimpleNamespace(pw_uid=1000), {}, 'fixture'); obj.wrapper = wrapper; obj.foot = foot; obj.foot_group = 3
            def wait(timeout):
                if failure == 'timeout': raise subprocess.TimeoutExpired('fixture', timeout)
            obj.child = types.SimpleNamespace(pid=3, stderr=None, poll=lambda: None, wait=wait, returncode=0)
            with self.subTest(failure=failure), patch.object(G.os, 'getpgid', return_value=3), patch.object(G.Path, 'glob', return_value=[Path('/proc/7')]), patch.object(G, 'signal_owned') as sent:
                with self.assertRaises(RuntimeError): obj.cleanup()
                sent.assert_called_once_with(C, foot)
    def test_pid_reuse_wrong_uid_or_group_never_signals(self):
        wrapper = dict(pid=3, uid=0, start_ticks=1, executable='/usr/bin/runuser')
        foot = dict(pid=4, uid=1000, start_ticks=2, executable='/usr/bin/foot')
        for mode in ('wrapper-reused', 'foot-reused', 'uid', 'group'):
            C = types.SimpleNamespace(process=lambda pid: ({**wrapper, 'start_ticks': 10} if mode == 'wrapper-reused' and pid == 3 else {**foot, 'start_ticks': 10} if mode == 'foot-reused' and pid == 4 else wrapper if pid == 3 else foot))
            obj = G.OwnedFoot(C, types.SimpleNamespace(pw_uid=1000), {}, 'fixture'); obj.wrapper = wrapper; obj.foot = dict(foot); obj.foot_group = 3; obj.child = types.SimpleNamespace(pid=3, stderr=None, poll=lambda: None)
            if mode == 'uid': obj.foot['uid'] = 0
            with self.subTest(mode=mode), patch.object(G.os, 'getpgid', return_value=5 if mode == 'group' else 3), patch.object(G, 'signal_owned') as sent:
                with self.assertRaises(RuntimeError): obj.cleanup()
                sent.assert_not_called()
    def test_owned_cleanup_only_signals_proved_client(self):
        wrapper = dict(pid=3, uid=0, start_ticks=1); foot = dict(pid=4, uid=1000, start_ticks=2)
        C = types.SimpleNamespace(process=lambda pid: wrapper if pid == 3 else foot)
        obj = G.OwnedFoot(C, types.SimpleNamespace(pw_uid=1000), {}, 'fixture'); obj.wrapper = wrapper; obj.foot = foot; obj.foot_group = 3
        obj.child = types.SimpleNamespace(pid=3, stderr=None, poll=lambda: None, wait=lambda timeout: None, returncode=0)
        with patch.object(G.os, 'getpgid', return_value=3), patch.object(G.Path, 'glob', return_value=[]), patch.object(G, 'signal_owned') as sent:
            self.assertEqual(obj.cleanup()['status'], 'owned-launch-exited'); sent.assert_called_once_with(C, foot)


if __name__ == '__main__': unittest.main(verbosity=2)
