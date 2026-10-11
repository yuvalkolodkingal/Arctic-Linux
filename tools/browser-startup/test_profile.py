#!/usr/bin/env python3
"""Focused controls for finite diagnostic output and exact function attribution."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest

SPEC = importlib.util.spec_from_file_location('browser_startup_profile', Path(__file__).with_name('profile.py'))
PROFILE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROFILE)


def line(phase, point, timestamp='100.000000001', tid=1234, args=''):
    return f'epiphany-{tid} [000] .... {timestamp}: {phase}_{point}: (0x1234) {args}'


class FiniteTraceControls(unittest.TestCase):
    def test_known_portal_and_method_classification_without_raw_argument_output(self):
        value = PROFILE.parse_event(line('dbus_call_sync', 'enter', args=
            'destination="org.freedesktop.portal.Desktop" interface="org.freedesktop.portal.Settings" method="ReadAll"'))
        self.assertEqual((value['destination'], value['interface'], value['method']),
                         ('desktop_portal', 'settings', 'readall'))
        self.assertNotIn('org.freedesktop', json.dumps(value))
        self.assertNotIn('0x1234', json.dumps(value))

    def test_unknown_legal_identifiers_are_discarded(self):
        value = PROFILE.parse_event(line('dbus_call_sync', 'enter', args=
            'destination="org.example.private_service" interface="org.example.Private" method="PrivateOperation"'))
        self.assertEqual((value['destination'], value['interface'], value['method']), ('other_identifier',) * 3)
        self.assertNotIn('private_service', json.dumps(value))
        self.assertNotIn('PrivateOperation', json.dumps(value))

    def test_text_or_escaped_argument_is_rejected_without_echo(self):
        for sentinel in ('private transcript in a destination', 'http://127.0.0.1/private', r'bad\"quoted'):
            with self.subTest(sentinel=sentinel), self.assertRaisesRegex(RuntimeError, '^trace_bus_') as caught:
                PROFILE.parse_event(line('dbus_call_sync', 'enter', args=
                    f'destination="{sentinel}" interface="org.example.Valid" method="Get"'))
            self.assertNotIn(sentinel, str(caught.exception))

    def test_invalid_or_unknown_event_is_rejected(self):
        for raw in (line('invented_function', 'enter'), line('gtk_init', 'return', tid=0),
                    'arbitrary text', 'x' * (PROFILE.MAX_LINE + 1)):
            with self.subTest(raw=raw[:40]), self.assertRaises(RuntimeError):
                PROFILE.parse_event(raw)

    def test_timestamp_precision_is_preserved_and_disclosed(self):
        ns = PROFILE.parse_event(line('gtk_init', 'enter', '100.123456789'))
        us = PROFILE.parse_event(line('gtk_init', 'return', '100.123457'))
        self.assertEqual(ns['timestamp_ns'], 100123456789)
        self.assertEqual(ns['timestamp_resolution_ns'], 1)
        self.assertEqual(us['timestamp_resolution_ns'], 1000)

    def test_nested_same_thread_calls_and_different_threads_pair_separately(self):
        raw = [line('gtk_init', 'enter', '100.000000001', 12),
               line('gtk_init', 'enter', '100.000000002', 12),
               line('gtk_init', 'enter', '100.000000003', 13),
               line('gtk_init', 'return', '100.000000004', 12),
               line('gtk_init', 'return', '100.000000008', 13),
               line('gtk_init', 'return', '100.000000010', 12)]
        result = PROFILE.spans([PROFILE.parse_event(value) for value in raw], 100000000000, 100000000011)
        self.assertEqual([value['duration_ns'] for value in result], [9, 2, 5])
        self.assertTrue(all(value['completed'] for value in result))

    def test_incomplete_call_is_never_declared_completed(self):
        result = PROFILE.spans([PROFILE.parse_event(line('application_run', 'enter'))],
                               100000000000, 101000000000)
        self.assertFalse(result[0]['completed'])
        self.assertIsNone(result[0]['duration_ns'])

    def test_unmatched_return_clock_inversion_and_out_of_range_fail(self):
        enter = PROFILE.parse_event(line('gtk_init', 'enter', '100.000000003'))
        leave = PROFILE.parse_event(line('gtk_init', 'return', '100.000000002'))
        for events in ([leave], [enter, leave]):
            with self.assertRaises(RuntimeError):
                PROFILE.spans(events, 100000000000, 101000000000)
        with self.assertRaises(RuntimeError):
            PROFILE.spans([enter], 101000000000, 102000000000)

    def test_proxy_null_pointer_is_finite_and_not_a_portal_claim(self):
        value = PROFILE.parse_event(line('dbus_proxy_sync', 'enter', args=
            'destination=(fault) interface="org.freedesktop.DBus.Properties"'))
        self.assertEqual(value['destination'], 'unreadable_identifier')
        self.assertEqual(value['interface'], 'properties')
        self.assertEqual(value['method'], 'proxy_construction')


class BindingControls(unittest.TestCase):
    def context(self):
        return dict(schema='arctic-browser-startup-diagnostic-v1', ready=True,
                    boot_purpose='separate-browser-startup-diagnostic', source_sha=PROFILE.SOURCE_SHA,
                    image=dict(source_sha=PROFILE.SOURCE_SHA, run_id=1, artifact_id=2, name='candidate.iso',
                        bytes=1900000000, sha256='1' * 64, archive_bytes=1900000100,
                        archive_sha256='2' * 64, producer_mode='frozen-external-paired-v1',
                        producer_receipt_sha256='3' * 64),
                    modules={'guest.py': '4' * 64, 'causal.py': '5' * 64},
                    packages={name: name + '-0:1.2-1.fc44.x86_64' for name in
                        ('epiphany', 'epiphany-runtime', 'glib2', 'gtk4', 'libadwaita', 'webkitgtk6.0', 'libsecret')})

    def test_complete_diagnostic_context(self):
        PROFILE.validate_context(self.context())

    def test_disabled_incomplete_wrong_source_and_unpinned_contexts_reject(self):
        original = self.context()
        changes = [(('ready',), False), (('boot_purpose',), 'paired-acceptance'),
                   (('source_sha',), '0' * 40), (('image',), None),
                   (('image', 'run_id'), True), (('image', 'sha256'), 'broken'),
                   (('image', 'source_sha'), '0' * 40),
                   (('image', 'producer_mode'), 'release'),
                   (('modules', 'guest.py'), 'no-pin'),
                   (('packages', 'gtk4'), 'other-package-0:1.2-1.fc44.x86_64')]
        for keys, replacement in changes:
            value = copy.deepcopy(original)
            parent = value
            for key in keys[:-1]:
                parent = parent[key]
            parent[keys[-1]] = replacement
            with self.subTest(keys=keys), self.assertRaises((RuntimeError, TypeError)):
                PROFILE.validate_context(value)

    def test_actual_host_elf_export_matches_readelf(self):
        # A real locally installed GLib ELF is used only to verify parser
        # semantics, not to claim anything about Fedora or the candidate VM.
        candidates = sorted(Path('/usr/lib/x86_64-linux-gnu').glob('libglib-2.0.so.0.*'))
        if not candidates:
            self.skipTest('No local GLib ELF for independent parser cross-check')
        path = candidates[0]
        raw = path.read_bytes()
        offset = PROFILE.exported_offset(raw, 'g_spawn_sync')
        self.assertIsInstance(offset, int)
        listing = subprocess.check_output(['readelf', '-Ws', str(path)], text=True)
        addresses = {int(row.split()[1], 16) for row in listing.splitlines()
                     if row.split() and row.split()[-1].split('@')[0] == 'g_spawn_sync'}
        self.assertEqual(len(addresses), 1)
        segments = subprocess.check_output(['readelf', '-lW', str(path)], text=True)
        address = addresses.pop()
        loads = [row.split() for row in segments.splitlines() if row.strip().startswith('LOAD')]
        expected = [int(row[1], 16) + address - int(row[2], 16) for row in loads
                    if int(row[2], 16) <= address < int(row[2], 16) + int(row[4], 16) and 'E' in row[6:-1]]
        self.assertEqual(expected, [offset])
        self.assertIsNone(PROFILE.exported_offset(raw, 'definitely_not_a_real_exported_function'))

    def test_malformed_elf_does_not_guess_symbol(self):
        for value in (b'', b'\x7fELF\x01\x01' + b'\0' * 100, b'\x7fELF\x02\x02' + b'\0' * 100):
            with self.assertRaises(RuntimeError):
                PROFILE.exported_offset(value, 'g_spawn_sync')


class RealOwnedProcessControls(unittest.TestCase):
    def wait_stopped(self, child):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            record = PROFILE.process_record(child.pid)
            if record['state'] == 'T':
                return record
            time.sleep(.01)
        self.fail('Owned test process never reached its stop gate')

    def test_stopped_wrapper_and_live_child_are_bound_and_reaped(self):
        script = ('import os,signal;pid=os.fork();'
                  'print(os.getpid(),flush=True) if pid else None;'
                  'os.kill(os.getpid(),signal.SIGSTOP)')
        child = subprocess.Popen([sys.executable, '-u', '-c', script],
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
        wrapper = None
        try:
            child.stdout.readline(32)
            wrapper = self.wait_stopped(child)
            scope = PROFILE.owned_scope(wrapper, None)
            self.assertGreaterEqual(len(scope), 2)
            self.assertTrue(all(value['session'] == child.pid for value in scope))
            PROFILE.stop_owned_scope(scope, child)
            self.assertIsNotNone(child.poll())
            self.assertTrue(all(not PROFILE.same_live_process(value) for value in scope))
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGCONT)
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=2)
            if child.stdout and not child.stdout.closed:
                child.stdout.close()

    def test_recycled_generation_is_not_signal_owned(self):
        record = PROFILE.process_record(os.getpid())
        record['start_ticks'] += 1
        self.assertFalse(PROFILE.same_live_process(record))

    def test_app_stdout_cannot_block_the_fixed_gate(self):
        # Real local process counterfactual, not candidate or VM evidence.
        target = repr([sys.executable, '-c', 'import sys;sys.stdout.write("x"*1048576)'])
        launch = f'os.execv({sys.executable!r},{target})'
        fixed = PROFILE.GATE[:PROFILE.GATE.index('os.execv(')] + launch
        old = fixed.replace('fd=os.open("/dev/null",os.O_WRONLY);os.dup2(fd,1);os.close(fd);', '')
        for script, should_block in ((old, True), (fixed, False)):
            child = subprocess.Popen([sys.executable, '-u', '-c', script],
                                     stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, start_new_session=True)
            try:
                self.assertRegex(child.stdout.readline(32).decode('ascii'), r'^[1-9][0-9]*\n$')
                self.wait_stopped(child)
                os.kill(child.pid, signal.SIGCONT)
                if should_block:
                    with self.assertRaises(subprocess.TimeoutExpired):
                        child.wait(timeout=.2)
                else:
                    self.assertEqual(child.wait(timeout=2), 0)
            finally:
                if child.poll() is None:
                    child.kill(); child.wait(timeout=2)
                child.stdout.close()


class RealReaderDrainControls(unittest.TestCase):
    def test_actual_nonblocking_pipe_requires_reader_empty_acknowledgement(self):
        # Controlled pipe protocol; this is not a kernel tracefs execution.
        with tempfile.TemporaryDirectory(prefix='arctic-browser-reader-control-') as directory:
            root = Path(directory)
            (root / 'tracing_on').write_text('1')
            causal = types.SimpleNamespace(loss_counts=lambda _: {})
            value = PROFILE.PhaseProbe(causal, root, {}, os.getuid())
            value.instance = root
            read_fd, write_fd = os.pipe()
            try:
                os.set_blocking(read_fd, False)
                value.fd = read_fd
                value.thread = threading.Thread(target=value._read)
                value.thread.start()
                for number in range(500):
                    os.write(write_fd, (line('gtk_init', 'enter', f'100.{number:09d}') + '\n').encode())
                value.stop()
                self.assertTrue(value.drained.is_set())
                self.assertEqual(len(value.events), 500)
                self.assertFalse(value.thread.is_alive())
                self.assertFalse(value.pending)
            finally:
                value.stopped.set()
                if value.thread:
                    value.thread.join(timeout=2)
                os.close(read_fd); os.close(write_fd)

    def test_zero_loss_without_drain_ack_cannot_pass(self):
        with tempfile.TemporaryDirectory(prefix='arctic-browser-drain-deadline-') as directory:
            root = Path(directory)
            (root / 'tracing_on').write_text('1')
            value = PROFILE.PhaseProbe(types.SimpleNamespace(loss_counts=lambda _: {}), root, {}, os.getuid())
            value.instance = root
            with self.assertRaisesRegex(RuntimeError, '^trace_drain_timeout$'):
                value.stop()
            self.assertTrue(value.finish_requested.is_set())
            self.assertFalse(value.drained.is_set())


if __name__ == '__main__':
    unittest.main()
