#!/usr/bin/env python3
"""Actual Source functions; owned ELF/pipe and explicit virtual RPM provider."""
import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).parent
BASE = '059ec55169c6e921a8ae516d85cd9dd1bdb58b72'
spec = importlib.util.spec_from_file_location('window_session_source', HERE / 'profile.py')
PROFILE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(PROFILE)
INVERSE = json.loads((HERE / 'source-inverse.json').read_bytes())
CONTEXT = json.loads((HERE / 'execution-context.json').read_bytes())
ORIGINAL = subprocess.check_output(['git', 'show', INVERSE['original_public_head'] + ':'
                                    + INVERSE['original_repository_path']], cwd=HERE)
assert hashlib.sha256(ORIGINAL).hexdigest() == INVERSE['original_collector_sha256']
old = types.ModuleType('reviewed_browser_source')
exec(compile(ORIGINAL, 'reviewed_browser_source.py', 'exec'), old.__dict__)
NEW = {key: value for key, value in PROFILE.PHASES.items() if key not in old.PHASES}


def event(phase, point, ns, tid=41, body=''):
    return f'epiphany-{tid} [001] .... 100.{ns:09d}: {phase}_{point}: (0x1234) {body}'


class VirtualRPMPath:
    """Paths are virtual candidate names; bytes belong to our real owned ELF."""
    actual = None

    def __init__(self, value):
        self.value = str(value)

    def __str__(self):
        return self.value

    def __eq__(self, other):
        return str(other) == self.value

    @property
    def parent(self):
        return VirtualRPMPath(str(Path(self.value).parent))

    @property
    def name(self):
        return Path(self.value).name

    def resolve(self, strict=False):
        return self

    def is_file(self):
        return True

    def is_symlink(self):
        return False

    def stat(self):
        return self.actual.stat()

    def read_bytes(self):
        return self.actual.read_bytes()


class NextRegionControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='arctic-window-session-source-')
        cls.root = Path(cls.temporary.name)
        cls.elf = cls.root / 'owned-synthetic-provider.so'
        names = sorted({symbol for _, symbol, _ in PROFILE.PHASES.values()})
        source = '\n'.join(('__attribute__((used)) static ' if name == 'ephy_window_new' else '')
                           + 'void ' + name + '(void) {}' for name in names) + '\n'
        (cls.root / 'provider.c').write_text(source)
        subprocess.run(['cc', '-shared', '-fPIC', '-o', str(cls.elf), str(cls.root / 'provider.c')],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        VirtualRPMPath.actual = cls.elf

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def inventory(self, before_symbol=None, owner_override=None):
        calls = []
        context = copy.deepcopy(CONTEXT)
        context['ready'] = True
        owners = {'/usr/bin/epiphany': context['packages']['epiphany-runtime']}
        paths = []
        for prefix, package in PROFILE.LIBRARIES.values():
            path = '/usr/lib64/' + prefix + '.owned-test'
            paths.append(path)
            owners[path] = context['packages'][package]
        if owner_override:
            owners['/usr/bin/epiphany'] = owner_override

        def output(argv, **kwargs):
            calls.append(tuple(argv))
            if argv[0] == 'ldd':
                return '\n'.join('provider => ' + path + ' (0x1234)' for path in paths)
            if argv[:2] == ['rpm', '-q']:
                return context['packages'][argv[-1]]
            if argv[:2] == ['rpm', '-qf']:
                return owners[argv[-1]]
            raise AssertionError('Unexpected virtual RPM provider invocation')

        real = PROFILE.exported_offset

        def resolve(raw, name):
            if before_symbol:
                before_symbol(name)
            return real(raw, name)

        with patch.object(PROFILE, 'Path', VirtualRPMPath), \
                patch.object(PROFILE.subprocess, 'check_output', side_effect=output), \
                patch.object(PROFILE.subprocess, 'run', return_value=types.SimpleNamespace(
                    returncode=0, stdout=b'', stderr=b'')), \
                patch.object(PROFILE, 'exported_offset', side_effect=resolve):
            result = PROFILE.inventory(context)
        return result, calls

    def test_whole_inverse_and_all_existing_function_asts(self):
        raw = (HERE / 'profile.py').read_text()
        self.assertEqual(raw.count(INVERSE['inverse_inserted_text']), 1)
        raw = raw.replace(INVERSE['inverse_inserted_text'], '')
        raw = raw.replace(INVERSE['inverse_new_browser_record'], INVERSE['inverse_old_browser_record'])
        self.assertEqual(raw.encode(), ORIGINAL)
        original_functions = {node.name: ast.dump(node) for node in ast.parse(ORIGINAL).body
                              if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
        prepared_functions = {node.name: ast.dump(node) for node in ast.parse(
            (HERE / 'profile.py').read_bytes()).body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
        for name in original_functions:
            if name != 'inventory':
                self.assertEqual(prepared_functions[name], original_functions[name], name)

    def test_existing_phases_exact_and_new_phases_have_no_argument_fetches(self):
        self.assertEqual({name: PROFILE.PHASES[name] for name in old.PHASES}, old.PHASES)
        self.assertEqual(len(NEW), 18)
        self.assertTrue(all(registers is None for _, _, registers in NEW.values()))
        self.assertEqual((PROFILE.MAX_EVENTS, PROFILE.MAX_LINE, PROFILE.MAX_ELF),
                         (old.MAX_EVENTS, old.MAX_LINE, old.MAX_ELF))
        self.assertEqual(PROFILE.GATE, old.GATE)

    def test_disabled_context_and_current_source_module_pins(self):
        self.assertIs(CONTEXT['ready'], False)
        self.assertIsNone(CONTEXT['image'])
        with self.assertRaisesRegex(RuntimeError, '^context_disabled_or_source$'):
            PROFILE.validate_context(CONTEXT)
        for name, sha in CONTEXT['modules'].items():
            raw = subprocess.check_output(['git', 'show', BASE + ':tools/performance/' + name], cwd=HERE)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), sha)

    def test_actual_changed_inventory_binds_real_elf_exports_without_private_symbol_guess(self):
        result, calls = self.inventory()
        raw = self.elf.read_bytes()
        browser = result['browser']
        self.assertEqual(browser['sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(browser['bytes'], len(raw))
        self.assertEqual(browser['owner'], CONTEXT['packages']['epiphany-runtime'])
        self.assertIsNone(browser['symbols']['ephy_window_new'])
        self.assertIsInstance(browser['symbols']['ephy_session_resume'], int)
        listing = subprocess.check_output(['readelf', '--dyn-syms', '-W', str(self.elf)], text=True)
        self.assertIn('ephy_session_resume', listing)
        self.assertNotIn('ephy_window_new', listing)
        self.assertTrue(any(argv[:2] == ('rpm', '-qf') and argv[-1] == '/usr/bin/epiphany' for argv in calls))
        self.assertEqual(set(browser['symbols']), {symbol for library, symbol, _ in NEW.values()
                                                  if library == 'browser'})
        for library, symbol, _ in NEW.values():
            self.assertEqual(result[library]['symbols'][symbol], PROFILE.exported_offset(raw, symbol))

    def test_wrong_browser_owner_denies_before_any_symbol_observation(self):
        seen = []
        with self.assertRaisesRegex(RuntimeError, '^browser_binary_owner$'):
            self.inventory(before_symbol=seen.append, owner_override='foreign-rpm-0:1-1.x86_64')
        self.assertEqual(seen, [])

    def test_changed_inventory_preserves_original_error_and_real_sigint(self):
        for original in (OSError('private-owned-sentinel'), KeyboardInterrupt('private-owned-sentinel')):
            def interrupt(_):
                raise original
            before = set(os.listdir('/proc/self/fd'))
            with self.assertRaises(type(original)) as caught:
                self.inventory(before_symbol=interrupt)
            self.assertIs(caught.exception, original)
            self.assertEqual(set(os.listdir('/proc/self/fd')), before)
        handler = signal.getsignal(signal.SIGINT)
        before = set(os.listdir('/proc/self/fd'))
        try:
            signal.signal(signal.SIGINT, signal.default_int_handler)
            with self.assertRaises(KeyboardInterrupt):
                self.inventory(before_symbol=lambda _: os.kill(os.getpid(), signal.SIGINT))
        finally:
            signal.signal(signal.SIGINT, handler)
        self.assertEqual(set(os.listdir('/proc/self/fd')), before)
        self.assertIs(signal.getsignal(signal.SIGINT), handler)

    def test_all_new_events_export_numeric_closed_fields_and_no_operands(self):
        for name in NEW:
            with self.subTest(phase=name):
                value = PROFILE.parse_event(event(name, 'enter', 1,
                    body='private_url=https://fixture.invalid/private title=PRIVATE_SENTINEL'))
                self.assertEqual(set(value), {'tid', 'timestamp_ns', 'timestamp_resolution_ns', 'phase', 'point'})
                self.assertEqual(value['phase'], name)
                self.assertNotIn('PRIVATE_SENTINEL', json.dumps(value))
                self.assertNotIn('fixture.invalid', json.dumps(value))
                self.assertNotIn('0x1234', json.dumps(value))

    def test_new_phase_nested_numeric_forwarding_incomplete_and_original_caps(self):
        events = [PROFILE.parse_event(event('session_resume', 'enter', 1)),
                  PROFILE.parse_event(event('session_resume', 'enter', 2)),
                  PROFILE.parse_event(event('session_resume', 'return', 3)),
                  PROFILE.parse_event(event('session_resume', 'return', 9)),
                  PROFILE.parse_event(event('file_read_async', 'enter', 10)),
                  PROFILE.parse_event(event('file_read_async', 'return', 11)),
                  PROFILE.parse_event(event('session_load', 'enter', 12))]
        spans = PROFILE.spans(events, 100000000000, 100000000020)
        self.assertEqual([value['duration_ns'] for value in spans], [8, 1, 1, None])
        self.assertFalse(spans[-1]['completed'])
        with self.assertRaisesRegex(RuntimeError, '^span_bounds$'):
            PROFILE.spans([events[0]] * (PROFILE.MAX_EVENTS + 1), 100000000000, 100000000020)
        with self.assertRaisesRegex(RuntimeError, '^span_unmatched_return$'):
            PROFILE.spans([events[2]], 100000000000, 100000000020)

    def test_real_pipe_reader_new_phase_forwarding_and_drain_ack(self):
        root = self.root / 'private-pipe-reader'
        root.mkdir(mode=0o700)
        (root / 'tracing_on').write_text('1')
        value = PROFILE.PhaseProbe(types.SimpleNamespace(loss_counts=lambda _: {}), root, {}, os.getuid())
        value.instance = root
        read_fd, write_fd = os.pipe()
        try:
            os.set_blocking(read_fd, False)
            value.fd = read_fd
            value.thread = threading.Thread(target=value._read)
            value.thread.start()
            raw = '\n'.join(event(name, point, index * 2 + delta)
                            for index, name in enumerate(NEW, 1)
                            for delta, point in ((0, 'enter'), (1, 'return'))) + '\n'
            os.write(write_fd, raw.encode('ascii'))
            value.stop()
            self.assertEqual(len(value.events), 36)
            self.assertTrue(value.drained.is_set())
            self.assertFalse(value.thread.is_alive())
            self.assertIsNone(value.failure)
            result = PROFILE.spans(value.events, 100000000000, 100000000100)
            self.assertEqual(len(result), 18)
            self.assertTrue(all(item['duration_ns'] == 1 for item in result))
        finally:
            value.stopped.set()
            if value.thread:
                value.thread.join(timeout=2)
            os.close(read_fd)
            os.close(write_fd)


if __name__ == '__main__':
    unittest.main(verbosity=2)
