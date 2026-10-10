"""Closed failure-only categories; original classification remains unchanged."""
import copy
import hashlib
import os
from pathlib import Path
import re
import types
import unittest
from unittest.mock import patch

import test_performance_failure_phase as P


class UARTEnvelopeTest(unittest.TestCase):
    def setUp(self):
        self.fixture = P.FixedFailurePhaseTest('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.prepare_guest()
        # Exact byte rollback, not a Git-history dependency in shallow CI.
        raw = (P.ROOT/'tools/performance/run-paired.py').read_bytes()
        raw = re.sub(rb'(?ms)^[ ]*# envelope-only-begin\n.*?^[ ]*# envelope-only-end\n', b'', raw)
        raw = b''.join(line for line in raw.splitlines(keepends=True)
            if not line.rstrip().endswith(b'# envelope-only'))
        # Preserve the original history digest through exactly three reviewed identity inverses.
        historical = raw
        for current, previous in (
                (b'f8e8e9d2cc7900607111f98d51c5071b09e2434aedb6eda9a000f3badd45c57c', b'5f3228d6f09a97e7640f522663bbfa32632f63387a3b59235caa3caab64bf92e'),
                (b'eb8ceacf12fd964651dc614c823773928b0fd13a17f32ffd3457659c01441cc9', b'1940fc7495315aa6ceff7b5fbff9554b081182404733f1443e2fee5bc8c5c8a2'),
                (b'57a256b79e362360e2fb1de39b65f007002765df6a02769e26042f5e7364ddea', b'7b7890ffdd227ae465ed856440e9bd03a36185a90cadbcb2926ad0eae2204bb7'),
        ):
            self.assertEqual(historical.count(current), 1)
            historical = historical.replace(current, previous)
        self.assertEqual(hashlib.sha256(historical).hexdigest(),
            '38f7d4dc1e9a3ff254e911f5a79bef26b422352f3faed7b21593bd4e49ce49c3')
        self.old = types.ModuleType('original_uart_classification')
        self.old.__file__ = str(P.ROOT/'tools/performance/run-paired.py')
        exec(compile(raw, self.old.__file__, 'exec'), self.old.__dict__)
        # The accepted UID fixture may supply its own exact source directory.
        self.old.ROOT = P.inner.ROOT

    def result(self, raw=None):
        if raw is not None:
            path = self.fixture.work/'runs/baseline/1/serial-boot.log'
            path.write_bytes(raw.encode() if type(raw) is str else raw)
        result = self.fixture.summary()
        original = self.old.failure_phase_summary(self.fixture.work, 'sensitive_text')
        without = {key:value for key,value in result.items() if key != 'guest_envelope'}
        self.assertEqual(without, original)
        content = P.json.dumps(result).encode()
        self.assertNotIn(b'do-not-export', content)
        self.assertNotIn('מילים סודיות'.encode(), content)
        self.assertEqual(P.screen.external_text(content), content)
        self.assertFalse(result['release_acceptance'])
        self.assertFalse(result['performance_acceptance'])
        return result

    def consumer(self, result):
        with patch.object(P.inner, 'failure_phase_summary', return_value=result):
            self.fixture.export(self.fixture.root/'screened')

    def test_all_original_104_codes_and_classes_remain_identical(self):
        for site in self.fixture.sites:
            with self.subTest(source=site['source'], line=site['line']):
                result = self.result(self.fixture.guest_trace(site))
                envelope = result['guest_envelope']
                self.assertEqual(envelope['reason'], 'source_known_shape')
                self.assertEqual(envelope['last_observer_phase'], 'measurement_conditions')
                self.assertEqual(envelope['collector_order'], 'ordered')
                self.assertEqual(envelope['frame_status'], 'recognized')
                self.assertEqual(envelope['control_status'], 'none')

    def test_closed_consumer_accepts_unqualified_source_shape_only(self):
        result = self.result(self.fixture.guest_trace())
        self.consumer(result)
        raw = (self.fixture.root/'screened/unqualified-failure-phase.json').read_bytes()
        self.assertLessEqual(len(raw), 4096)
        self.assertIn(b'"performance_acceptance": false', raw)

    def test_missing_traceback_and_unsupported_exception_remain_unknown(self):
        trace = self.fixture.guest_trace()
        for raw in (trace.replace('Traceback (most recent call last):', 'private traceback'),
                    trace.replace('RuntimeError:', 'PrivateError: password=do-not-export')):
            result = self.result(raw)
            self.assertEqual(result['guest_failure']['status'], 'unknown')
            self.assertEqual(result['guest_envelope']['reason'], 'traceback_missing')
            self.assertEqual(result['guest_envelope']['last_observer_phase'], 'measurement_conditions')
            self.assertEqual(result['guest_envelope']['counts']['unsupported_exception_like_lines'],
                'one' if 'PrivateError:' in raw else 'zero')

    def test_marker_multiplicity_order_and_exit_range_are_closed(self):
        trace = self.fixture.guest_trace()
        for raw, reason in ((trace+'ARCTIC-COLLECT-BEGIN\n', 'marker_multiplicity'),
                (trace.replace('ARCTIC-COLLECT-BEGIN\n', '')+'ARCTIC-COLLECT-BEGIN\n', 'marker_order'),
                (trace.replace('ARCTIC-INSTALLED-SMOKE-EXIT=1', 'ARCTIC-INSTALLED-SMOKE-EXIT=999'), 'smoke_exit_range')):
            self.assertEqual(self.result(raw)['guest_envelope']['reason'], reason)

    def test_duplicate_trace_and_supported_exceptions_remain_ambiguous(self):
        trace = self.fixture.guest_trace()
        for token in ('Traceback (most recent call last):', 'RuntimeError: private'):
            raw = trace.replace('ARCTIC-INSTALLED-SMOKE-EXIT=1', token+'\nARCTIC-INSTALLED-SMOKE-EXIT=1')
            result = self.result(raw)
            self.assertEqual(result['guest_envelope']['reason'], 'traceback_multiplicity')
            self.assertEqual(result['guest_failure']['status'], 'ambiguous')

    def test_missing_or_duplicate_observer_identity_never_admits_phase(self):
        trace = self.fixture.guest_trace()
        record = self.fixture.guest_record('observer_source_sha256', self.fixture.observer['source_sha256'])
        for raw, count in ((trace.replace(record, ''), 'zero'), (trace.replace(record, record+record), 'multiple')):
            envelope = self.result(raw)['guest_envelope']
            self.assertEqual(envelope['reason'], 'observer_record_count')
            self.assertEqual(envelope['counts']['admitted_observer_records'], count)
            self.assertEqual(envelope['last_observer_phase'], 'unavailable')

    def test_forged_source_identity_and_phase_records_fail_closed(self):
        trace = self.fixture.guest_trace()
        for raw, reason in ((trace.replace(self.fixture.observer['source_sha256'], 'a'*64), 'observer_source_mismatch'),
                (trace.replace('"stage": "installed"', '"stage": "private"'), 'observer_record_invalid'),
                (trace.replace('Traceback (most recent call last):',
                    self.fixture.guest_record('measurement_conditions', True)+'Traceback (most recent call last):'), 'observer_phase_duplicate')):
            envelope = self.result(raw)['guest_envelope']
            self.assertEqual(envelope['reason'], reason)
            self.assertEqual(envelope['last_observer_phase'], 'unavailable')

    def test_last_fixed_phase_survives_unknown_frame_without_exporting_value(self):
        # Use a replacement independent of the source site's function name.
        trace = self.fixture.guest_trace().replace('/run/t/guest-check.py', '/private/password=do-not-export.py', 1)
        result = self.result(trace)
        self.assertEqual(result['guest_failure']['status'], 'unknown')
        self.assertEqual(result['guest_envelope']['reason'], 'frame_unrecognized')
        self.assertEqual(result['guest_envelope']['last_observer_phase'], 'measurement_conditions')
        self.consumer(result)

    def test_frame_control_and_chain_categories_do_not_change_classification(self):
        trace = self.fixture.guest_trace()
        for raw, status, reason in ((trace.replace('  File ', '\x1b[31m  File ', 1), 'control', 'frame_unrecognized'),
                (trace.replace('line 11, in <module>', 'line 12, in <module>'), 'invalid_chain', 'frame_chain_invalid')):
            envelope = self.result(raw)['guest_envelope']
            self.assertEqual(envelope['frame_status'], status)
            self.assertEqual(envelope['reason'], reason)

    def test_private_tail_control_is_observed_without_changing_original_gate(self):
        raw = self.fixture.guest_trace().replace('password=do-not-export transcript:', '\x1bpassword=do-not-export transcript:')
        result = self.result(raw)
        self.assertEqual(result['guest_failure']['status'], 'source_known_shape')
        self.assertEqual(result['guest_envelope']['control_status'], 'present')
        self.consumer(result)

    def test_source_candidate_absence_remains_unknown_with_fixed_phase(self):
        # Actual default site function is fixed by the admitted source inventory.
        site = next(x for x in self.fixture.sites if (x['source'], x['line']) == ('guest', 360))
        trace = self.fixture.guest_trace().replace(f'line 360, in {site["function"]}', 'line 1, in private')
        envelope = self.result(trace)['guest_envelope']
        self.assertEqual(envelope['reason'], 'source_candidate_count')
        self.assertEqual(envelope['counts']['source_candidates'], 'zero')
        self.assertEqual(envelope['last_observer_phase'], 'measurement_conditions')

    def test_utf8_truncation_and_nul_produce_no_untrusted_phase(self):
        raw = self.fixture.guest_trace().encode()
        for content, reason in ((raw+b'\xff\n','uart_utf8'), (raw[:-1],'uart_termination'),
                (raw+b'\x00\n','uart_termination')):
            result = self.result(content)
            self.assertEqual(result['guest_envelope']['reason'], reason)
            self.assertEqual(result['guest_envelope']['last_observer_phase'], 'unavailable')

    def test_source_frozen_context_and_uid_faults_keep_original_fail_closed(self):
        self.result(self.fixture.guest_trace())
        frozen = self.fixture.work/'frozen-observer.py'
        original = frozen.read_bytes(); frozen.write_bytes(original+b'# private\n')
        self.assertEqual(self.result()['guest_envelope']['reason'], 'frozen_observer_mismatch')
        frozen.write_bytes(original)
        real = os.fstat
        inode = Path(P.inner.ROOT).stat().st_ino
        def wrong(fd):
            info = real(fd)
            if info.st_ino == inode:
                fields = list(info); fields[4] = os.geteuid()+1
                return os.stat_result(fields)
            return info
        with patch.object(P.inner.os, 'fstat', side_effect=wrong):
            self.assertEqual(self.result()['guest_envelope']['reason'], 'source_directory_owner')

    def test_actual_owned_uart_symlink_and_owner_failures_are_unobserved(self):
        self.result(self.fixture.guest_trace())
        uart = self.fixture.work/'runs/baseline/1/serial-boot.log'
        raw = uart.read_bytes(); uart.unlink()
        private = self.fixture.root/'private.log'; private.write_bytes(raw); uart.symlink_to(private)
        result = self.result()
        self.assertEqual(result['guest_envelope']['reason'], 'not_observed')
        self.assertEqual(result['guest_failure']['status'], 'unavailable')
        self.consumer(result)
        uart.unlink(); uart.write_bytes(raw)
        inode, real = uart.stat().st_ino, os.fstat
        def wrong_owner(fd):
            info = real(fd)
            if info.st_ino == inode:
                fields = list(info); fields[4] = os.geteuid()+1
                return os.stat_result(fields)
            return info
        with patch.object(P.inner.os, 'fstat', side_effect=wrong_owner):
            result = self.result()
            self.assertEqual(result['guest_envelope']['reason'], 'not_observed')
            self.assertEqual(result['guest_failure']['status'], 'unavailable')

    def test_consumer_rejects_unknown_fields_types_private_values_and_forged_phase(self):
        original = self.result(self.fixture.guest_trace())
        for fault in ('field','reason','count','count_type','order','frame','control','phase','phase_identity','status'):
            result = copy.deepcopy(original); envelope = result['guest_envelope']
            if fault == 'field': envelope['private'] = 'password=do-not-export'
            elif fault == 'reason': envelope['reason'] = 'password=do-not-export'
            elif fault == 'count': envelope['counts']['frames'] = '1048576'
            elif fault == 'count_type': envelope['counts']['frames'] = True
            elif fault == 'order': envelope['collector_order'] = 'private'
            elif fault == 'frame': envelope['frame_status'] = 'private'
            elif fault == 'control': envelope['control_status'] = 'private'
            elif fault == 'phase': envelope['last_observer_phase'] = 'private transcript'
            elif fault == 'phase_identity': envelope['counts']['admitted_observer_records'] = 'zero'
            else: envelope['reason'] = 'not_observed'
            with self.subTest(fault=fault), self.assertRaises(ValueError): self.consumer(result)


if __name__ == '__main__':
    unittest.main()
