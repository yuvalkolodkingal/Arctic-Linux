#!/usr/bin/env python3
"""Focused controls for finite diagnostic output and exact function attribution."""
import copy
import ast
from contextlib import redirect_stderr
import importlib.util
import io
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


class FailureOnlyControls(unittest.TestCase):
    def test_original_functions_thresholds_and_scoped_visibility_substitution_AST(self):
        path = Path(__file__).with_name('profile.py'); root = path.parents[2]
        original = ast.parse(subprocess.check_output(['git', '-C', str(root), 'show',
            '0e9df53b9d101ea74acbaaa318c0d35d4330b25d:tools/browser-startup/profile.py']))
        current = ast.parse(path.read_bytes())
        new = {n.name: n for n in current.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        for old in original.body:
            if isinstance(old, (ast.FunctionDef, ast.ClassDef)):
                if old.name == 'PhaseProbe':
                    setup = next(n for n in old.body if isinstance(n, ast.FunctionDef) and n.name == '__enter__')
                    replaced = 0
                    for n in ast.walk(setup):
                        if isinstance(n, ast.Constant) and n.value == 'window_present':
                            n.value = 'widget_visibility'; replaced += 1
                    self.assertEqual(replaced, 1)
                elif old.name == 'launch':
                    class GuardSubstitution(ast.NodeTransformer):
                        def visit_Expr(self, node):
                            call = node.value
                            if (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                                    and call.func.id == 'require' and len(call.args) == 2
                                    and isinstance(call.args[1], ast.Constant)
                                    and call.args[1].value == 'required_phase_not_observed'):
                                return ast.parse('require_launch_phases(phases.events)').body[0]
                            return self.generic_visit(node)
                    old = GuardSubstitution().visit(old)
                self.assertEqual(ast.dump(old, include_attributes=False), ast.dump(new[old.name], include_attributes=False))
            elif not isinstance(old, ast.If):
                if (isinstance(old, ast.Assign) and any(isinstance(n, ast.Name) and n.id == 'PHASES'
                        for n in old.targets)):
                    index = next(i for i, n in enumerate(old.value.keys) if n.value == 'window_present') + 1
                    old.value.keys.insert(index, ast.Constant('widget_visibility'))
                    old.value.values.insert(index, ast.parse("('gtk', 'gtk_widget_set_visible', None)", mode='eval').body)
                self.assertIn(ast.dump(old, include_attributes=False),
                              {ast.dump(node, include_attributes=False) for node in current.body})
        codes = {n.args[1].value for n in ast.walk(current) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name) and n.func.id == 'require'
            and len(n.args) > 1 and isinstance(n.args[1], ast.Constant)}
        self.assertEqual(PROFILE.FAILURE_CODES, codes)

    def test_direct_visibility_path_succeeds_without_conditional_present_event(self):
        events = [PROFILE.parse_event(line('application_run', 'enter')),
                  PROFILE.parse_event(line('widget_visibility', 'enter', '100.000000002')),
                  PROFILE.parse_event(line('widget_visibility', 'return', '100.000000003'))]
        PROFILE.require_launch_phases(events)
        result = PROFILE.spans(events, 100000000000, 100000000010)
        visible = next(value for value in result if value['phase'] == 'widget_visibility')
        self.assertTrue(visible['completed']); self.assertEqual(visible['duration_ns'], 1)
        self.assertEqual(PROFILE.PHASES['widget_visibility'], ('gtk', 'gtk_widget_set_visible', None))
        self.assertEqual(PROFILE.PHASES['window_present'], ('gtk', 'gtk_window_present', None))

    def test_each_missing_direct_phase_and_both_have_distinct_owned_finite_reason(self):
        run = PROFILE.parse_event(line('application_run', 'enter'))
        visible = PROFILE.parse_event(line('widget_visibility', 'enter'))
        present = PROFILE.parse_event(line('window_present', 'enter'))
        for events, reason in (([visible], 'required_application_run_not_observed'),
                ([run, present], 'required_widget_visibility_not_observed'),
                ([], 'required_application_and_visibility_not_observed')):
            with self.subTest(reason=reason):
                try:
                    PROFILE.require_launch_phases(events)
                except RuntimeError as error:
                    record = PROFILE.finite_failure_record(error)
                    self.assertEqual(record, {'scope': 'collector', 'phase': 'browser_launch', 'reason': reason})
                    out = io.StringIO()
                    with redirect_stderr(out): PROFILE.emit_failure_record(error)
                    self.assertEqual(PROFILE.parse_failure_marker(out.getvalue().encode()), record)
                else:
                    self.fail('missing direct Source phase must fail')

    def test_return_only_events_cannot_satisfy_direct_entry_guards(self):
        events = [PROFILE.parse_event(line(phase, 'return'))
                  for phase in ('application_run', 'widget_visibility', 'window_present')]
        with self.assertRaisesRegex(RuntimeError, '^required_application_and_visibility_not_observed$'):
            PROFILE.require_launch_phases(events)

    def test_visibility_probe_does_not_read_or_export_widget_values(self):
        event = PROFILE.parse_event(line('widget_visibility', 'enter',
            args='widget=(0x1234) title="private transcript" visible=1'))
        self.assertEqual(set(event), {'tid', 'timestamp_ns', 'timestamp_resolution_ns', 'phase', 'point'})
        self.assertNotIn('private', json.dumps(event)); self.assertNotIn('0x1234', json.dumps(event))

    def test_actual_inventory_guard_and_ELF_parser_have_owned_phase_codes(self):
        from unittest.mock import patch
        with patch.object(PROFILE.subprocess, 'check_output', return_value='synthetic-private-value'):
            try: PROFILE.inventory({'packages': {'epiphany-runtime': 'expected'}})
            except RuntimeError as error:
                record = PROFILE.finite_failure_record(error)
        self.assertEqual(record, {'scope': 'collector', 'phase': 'runtime_inventory', 'reason': 'runtime_package_binding'})
        try: PROFILE.exported_offset(b'private transcript payload', 'g_application_run')
        except RuntimeError as error: record = PROFILE.finite_failure_record(error)
        self.assertEqual(record['phase'], 'elf_inventory'); self.assertEqual(record['reason'], 'elf_layout')

    def test_actual_probe_parser_failure_and_unowned_spoof_do_not_echo_values(self):
        try: PROFILE.parse_event('private transcript or queried URL')
        except RuntimeError as error:
            out = io.StringIO()
            with redirect_stderr(out): PROFILE.emit_failure_record(error)
        value = PROFILE.parse_failure_marker(out.getvalue().encode())
        self.assertEqual(value, {'scope': 'collector', 'phase': 'probe_decode', 'reason': 'trace_event_shape'})
        self.assertNotIn('private', out.getvalue())
        for error in (RuntimeError('runtime_package_binding'), RuntimeError('private transcript'),
                      subprocess.CalledProcessError(1, ['private'], stderr=b'private transcript')):
            value = PROFILE.finite_failure_record(error)
            self.assertEqual(value['phase'], 'unknown')
            self.assertNotIn('private', json.dumps(value))
        self.assertEqual(PROFILE.finite_failure_record(RuntimeError('runtime_package_binding'))['reason'], 'unclassified_exception')

    def test_marker_rejects_duplicates_unknowns_partial_extra_and_large_private_input(self):
        good = b'ARCTIC-BROWSER-STARTUP-FAILURE collector probe_decode trace_event_shape\n'
        self.assertIsNotNone(PROFILE.parse_failure_marker(b'private stderr\n' + good))
        for raw in (good + good, good.replace(b'probe_decode', b'private'),
                    good.replace(b'trace_event_shape', b'private'), good.rstrip() + b' extra',
                    good[:-4], b'x' * 4097):
            self.assertIsNone(PROFILE.parse_failure_marker(raw))

    def test_hostile_exception_representation_is_never_touched(self):
        class Hostile(RuntimeError):
            def __str__(self): raise AssertionError('private repr')
            def __repr__(self): raise AssertionError('private repr')
            def __getattribute__(self, name):
                if name in ('args', '__traceback__'): raise AssertionError('private field')
                return super().__getattribute__(name)
        out = io.StringIO()
        with redirect_stderr(out): PROFILE.emit_failure_record(Hostile('private transcript'))
        self.assertEqual(out.getvalue(), 'ARCTIC-BROWSER-STARTUP-FAILURE collector unknown unclassified_exception\n')

    def test_classifier_and_output_failure_cannot_expose_exception_chain(self):
        from unittest.mock import patch
        out = io.StringIO()
        with patch.object(PROFILE, 'finite_failure_record', side_effect=RuntimeError('private transcript')), redirect_stderr(out):
            PROFILE.emit_failure_record(RuntimeError('other private exception'))
        self.assertEqual(out.getvalue(), 'ARCTIC-BROWSER-STARTUP-FAILURE collector unknown unclassified_exception\n')
        class FaultySink:
            def write(self, _): raise OSError('private output failure')
            def flush(self): raise OSError('private output failure')
        with redirect_stderr(FaultySink()): PROFILE.emit_failure_record(RuntimeError('private exception'))


if __name__ == '__main__':
    unittest.main()
