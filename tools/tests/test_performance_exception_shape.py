"""Unauthenticated class-token diagnostics retain every original failure gate."""
import copy
import hashlib
import json
import os
import re
import types
import unittest
from unittest.mock import patch

import test_performance_failure_phase as P


class ExceptionShapeTest(unittest.TestCase):
    def setUp(self):
        self.fixture = P.FixedFailurePhaseTest('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.prepare_guest()
        raw = (P.ROOT/'tools/performance/run-paired.py').read_bytes()
        raw = re.sub(rb'(?ms)^    # exception-shape-only-begin\n.*?^    # exception-shape-only-end\n', b'', raw)
        raw = b''.join(line for line in raw.splitlines(keepends=True) if b'# exception-shape-only # envelope-only' not in line)
        added = b"            last_observer_phase='unavailable',\n            # Class tokens are unauthenticated shape observations, not causes.\n            exception_shape=dict(reason='not_observed', count='unavailable',\n                exception_class='none', format='none')),\n"
        self.assertEqual(raw.count(added), 1)
        raw = raw.replace(added, b"            last_observer_phase='unavailable'),\n")
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
            'bb9006d12b5bb6e0cbae417c0301c2f529948eca63ccff57b915c9679abb5185')
        self.old = types.ModuleType('original_exception_shape_classifier')
        self.old.__file__ = str(P.ROOT/'tools/performance/run-paired.py')
        exec(compile(raw, self.old.__file__, 'exec'), self.old.__dict__)
        self.old.ROOT = P.inner.ROOT
        consumer = (P.ROOT/'tools/performance/qualification.py').read_bytes()
        consumer = re.sub(rb'(?ms)^    # exception-shape-only-begin\n.*?^    # exception-shape-only-end\n', b'', consumer)
        added = b"'control_status', 'last_observer_phase', 'exception_shape'}"
        self.assertEqual(consumer.count(added), 1)
        consumer = consumer.replace(added, b"'control_status', 'last_observer_phase'}")
        self.assertEqual(hashlib.sha256(consumer).hexdigest(),
            'dc6742c9f7e8c9b6d37cde5adce36f801f8799c68799427205dcffdd9a648175')

    def result(self, raw=None):
        if raw is not None:
            (self.fixture.work/'runs/baseline/1/serial-boot.log').write_bytes(raw.encode() if type(raw) is str else raw)
        result = self.fixture.summary()
        old = self.old.failure_phase_summary(self.fixture.work, 'sensitive_text')
        without = copy.deepcopy(result)
        without['guest_envelope'].pop('exception_shape')
        self.assertEqual(without, old)
        text = json.dumps(result).encode()
        for private in (b'do-not-export', b'private.invalid', 'מילים סודיות'.encode(), b'guest-check.py'):
            self.assertNotIn(private, text)
        self.assertEqual(P.screen.external_text(text), text)
        self.assertFalse(result['performance_acceptance'])
        self.assertFalse(result['release_acceptance'])
        return result

    def trace(self, line):
        return self.fixture.guest_trace().replace('RuntimeError: No unique non-root Mango session', line)

    def consumer(self, result):
        with patch.object(P.inner, 'failure_phase_summary', return_value=result):
            self.fixture.export(self.fixture.root/'screened')

    def test_all_104_original_classifications_identical_and_fixed_class_token(self):
        for site in self.fixture.sites:
            with self.subTest(source=site['source'], line=site['line']):
                result = self.result(self.fixture.guest_trace(site))
                self.assertEqual(result['guest_failure']['status'], 'source_known_shape')
                self.assertEqual(result['guest_envelope']['exception_shape'], dict(
                    reason='class_token_observed', count='one', exception_class=site['exception'], format='plain'))

    def test_builtin_plain_and_official_default_colors_observed_without_cause(self):
        for name in ('NameError', 'TypeError', 'KeyError', 'OSError', 'MemoryError', 'KeyboardInterrupt'):
            for line, form in ((name+': password=do-not-export', 'plain'),
                    ('\x1b[1;35m'+name+'\x1b[0m: \x1b[35mpassword=do-not-export\x1b[0m', 'python314_default')):
                with self.subTest(name=name, form=form):
                    result = self.result(self.trace(line))
                    self.assertEqual(result['guest_failure']['status'], 'unknown')
                    self.assertEqual(result['guest_failure']['code'], 'none')
                    self.assertEqual(result['guest_envelope']['exception_shape'], dict(
                        reason='class_token_observed', count='one', exception_class=name, format=form))

    def test_colored_existing_class_does_not_admit_original_source_code(self):
        result = self.result(self.trace('\x1b[1;35mRuntimeError\x1b[0m: \x1b[35mNo unique non-root Mango session\x1b[0m'))
        self.assertEqual(result['guest_failure']['status'], 'unknown')
        self.assertEqual(result['guest_envelope']['exception_shape']['exception_class'], 'RuntimeError')
        self.consumer(result)
        self.assertLessEqual((self.fixture.root/'screened/unqualified-failure-phase.json').stat().st_size, 4096)

    def test_empty_builtin_message_lf_and_crlf_are_shapes_only(self):
        for line in ('NameError', '\x1b[1;35mNameError\x1b[0m'):
            for newline in ('\n', '\r\n'):
                result = self.result(self.trace(line).replace('\n', newline))
                self.assertEqual(result['guest_envelope']['exception_shape']['exception_class'], 'NameError')
                self.assertEqual(result['guest_failure']['status'], 'unknown')

    def test_unknown_qualified_and_private_classes_are_not_exported(self):
        for name in ('PrivateError', 'subprocess.CalledProcessError', 'json.decoder.JSONDecodeError', 'private.NameError'):
            result = self.result(self.trace(name+': password=do-not-export'))
            self.assertEqual(result['guest_envelope']['exception_shape'], dict(
                reason='unsupported_class', count='one', exception_class='none', format='none'))
            self.assertNotIn(name, json.dumps(result))

    def test_missing_duplicate_chain_and_echoed_tokens_are_not_unique(self):
        for line, reason, count in (('$ echo NameError: private', 'exception_missing', 'zero'),
                ('NameError: private\nTypeError: private', 'exception_multiplicity', 'multiple'),
                ('NameError: private\nNameError: private', 'exception_multiplicity', 'multiple')):
            result = self.result(self.trace(line))
            self.assertEqual(result['guest_envelope']['exception_shape'], dict(
                reason=reason, count=count, exception_class='none', format='none'))
        trace = self.trace('NameError: private').replace('Traceback (most recent call last):',
            'Traceback (most recent call last):\nTraceback (most recent call last):')
        self.assertEqual(self.result(trace)['guest_envelope']['exception_shape']['reason'], 'traceback_not_unique')

    def test_changed_colors_extra_controls_and_nonterminal_reset_rejected(self):
        valid = '\x1b[1;35mNameError\x1b[0m: \x1b[35mprivate\x1b[0m'
        for line in (valid.replace('1;35', '31'), valid[:-4], valid+'suffix',
                valid.replace('private', 'pri\x1b[0mvate'), 'NameError: pri\x07vate',
                valid.replace('NameError', 'Na\x1b[0mmeError')):
            result = self.result(self.trace(line))
            self.assertEqual(result['guest_envelope']['exception_shape']['reason'], 'exception_control')
            self.assertEqual(result['guest_envelope']['exception_shape']['exception_class'], 'none')

    def test_current_utf8_termination_marker_and_source_gates_remain_unchanged(self):
        trace = self.trace('NameError: private')
        for raw in (trace.encode()+b'\xff\n', trace[:-1], trace+'\x00\n',
                trace.replace('ARCTIC-COLLECT-END', 'PRIVATE-COLLECT-END')):
            self.assertEqual(self.result(raw)['guest_envelope']['exception_shape']['reason'], 'not_observed')
        self.result(trace)
        source = P.inner.ROOT/'tools/performance/guest.py'
        original = source.read_bytes(); source.write_bytes(original+b'\n# mutation\n')
        self.assertEqual(self.result()['guest_envelope']['exception_shape']['reason'], 'not_observed')
        source.write_bytes(original)

    def test_forged_duplicate_or_missing_observer_identity_has_no_class(self):
        trace = self.trace('NameError: private')
        record = self.fixture.guest_record('observer_source_sha256', self.fixture.observer['source_sha256'])
        for raw in (trace.replace(record, ''), trace.replace(record, record+record),
                trace.replace(self.fixture.observer['source_sha256'], 'a'*64),
                trace.replace('"stage": "installed"', '"stage": "private"')):
            shape = self.result(raw)['guest_envelope']['exception_shape']
            self.assertEqual(shape['reason'], 'observer_not_unique')
            self.assertEqual(shape['count'], 'unavailable')

    def test_owned_uart_symlink_fifo_wrong_uid_and_oversize_remain_unobserved(self):
        self.result(self.trace('NameError: private'))
        uart = self.fixture.work/'runs/baseline/1/serial-boot.log'
        original = uart.read_bytes()
        private = self.fixture.root/'private-uart'; private.write_bytes(original)
        for kind in ('link', 'fifo', 'oversize', 'owner'):
            uart.unlink()
            if kind == 'link': uart.symlink_to(private)
            elif kind == 'fifo': os.mkfifo(uart)
            elif kind == 'oversize':
                with uart.open('wb') as f: f.truncate(8388609)
            else: uart.write_bytes(original)
            real = os.fstat
            def wrong(fd):
                info = real(fd)
                if info.st_ino == uart.lstat().st_ino:
                    fields = list(info); fields[4] = os.geteuid()+1
                    return os.stat_result(fields)
                return info
            with patch.object(P.inner.os, 'fstat', side_effect=wrong if kind == 'owner' else real):
                self.assertEqual(self.result()['guest_envelope']['exception_shape']['reason'], 'not_observed')

    def test_consumer_rejects_open_vocabulary_types_and_inconsistent_prerequisites(self):
        original = self.result(self.trace('NameError: private'))
        for fault in ('extra', 'reason', 'class', 'format', 'count', 'type', 'prerequisite', 'none'):
            result = copy.deepcopy(original); shape = result['guest_envelope']['exception_shape']
            if fault == 'extra': shape['message'] = 'password=do-not-export'
            elif fault == 'reason': shape['reason'] = 'private'
            elif fault == 'class': shape['exception_class'] = 'PrivateError'
            elif fault == 'format': shape['format'] = 'generic_ansi'
            elif fault == 'count': shape['count'] = 'multiple'
            elif fault == 'type': shape['exception_class'] = True
            elif fault == 'prerequisite': result['guest_envelope']['counts']['tracebacks'] = 'zero'
            else: shape['reason'] = 'unsupported_class'
            with self.subTest(fault=fault), self.assertRaises(ValueError): self.consumer(result)


if __name__ == '__main__':
    unittest.main()
