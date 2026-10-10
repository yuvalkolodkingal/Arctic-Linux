"""Same-decision closed rule observations never grant a scanner exemption."""
import contextlib
import importlib.util
import io
from pathlib import Path
import unittest
import tracemalloc
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('owned_rule_observer',Path(__file__).with_name('screen-evidence.py'))
S=importlib.util.module_from_spec(spec);spec.loader.exec_module(S)
PRIVATE='private-value-תמליל'

class RuleControls(unittest.TestCase):
    def rejected(self,raw):
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):
            with self.assertRaises(RuntimeError) as caught:S.external_text(raw)
        self.assertEqual(caught.exception.args,('Sensitive text in external evidence',))
        self.assertNotIn(PRIVATE,stream.getvalue())
        return stream.getvalue()

    def test_diagnostic_budget_keeps_exact_boundary_and_same_fatal_rejection(self):
        budget = S.MAX_DIAGNOSTIC_MATCH_BYTES
        self.assertEqual(budget, 16384)
        for value, category in (
                ('password=' + 'x' * (budget - 9), 'named-secret'),
                ('password=' + 'x' * (budget - 8), 'unknown-rule'),
                ('password=' + 'ת' * (budget // 2), 'unknown-rule')):
            with self.subTest(category=category, bytes=len(value.encode())):
                self.assertEqual(self.rejected(value.encode()),
                    'ARCTIC-EVIDENCE-RULE=source-view-' + category + '\n')
        original = RuntimeError('Sensitive text in external evidence')
        with patch.object(S, 'RuntimeError', create=True, return_value=original):
            with self.assertRaises(RuntimeError) as caught:
                S.external_text(('password=' + 'x' * budget).encode())
        self.assertIs(caught.exception, original)

    def test_oversized_original_match_is_not_copied_for_diagnostics(self):
        # Construct the original regex Match before measuring. A copied group
        # would allocate over 2 MiB, exceeding this independent observer budget.
        value = 'prefix password=' + 'x' * (2 * 1024 * 1024) + ' suffix'
        match = S.EXTERNAL_SENSITIVE.search(value)
        self.assertGreater(match.end() - match.start(), 2 * 1024 * 1024)
        stream = io.StringIO()
        tracemalloc.start()
        try:
            with contextlib.redirect_stdout(stream):
                S.diagnose_sensitive_match(match, 'source-view')
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(peak, 128 * 1024)
        self.assertEqual(stream.getvalue(), 'ARCTIC-EVIDENCE-RULE=source-view-unknown-rule\n')

    def test_category_patterns_reconstruct_exact_original_alternatives(self):
        self.assertEqual('(?i)'+'|'.join(p for _,p in S.EXTERNAL_RULE_ALTERNATIVES),S.EXTERNAL_SENSITIVE.pattern)
        self.assertEqual(len(S.EXTERNAL_RULE_ALTERNATIVES),10)

    def test_each_original_rule_remains_fatal_and_discloses_only_fixed_category(self):
        cases={'github-credential':'ghp_private123','aws-credential':'AKIA0123456789ABCDEF',
            'authorization':'Authorization: Bearer '+PRIVATE,'email-shape':'private@example.invalid',
            'queried-url':'https://example.invalid/?query='+PRIVATE,
            'credential-url':'https://'+PRIVATE+'@example.invalid/',
            'named-secret':'password='+PRIVATE,'secret-option':'--token '+PRIVATE,
            'disk-secret-input':'cryptsetup open /dev/vda4 owned < '+PRIVATE,
            'transcription-label':'תמלול:'+PRIVATE}
        for category,value in cases.items():
            with self.subTest(category=category):
                self.assertEqual(self.rejected(value.encode()),'ARCTIC-EVIDENCE-RULE=source-view-'+category+'\n')

    def test_first_actual_rejecting_match_not_later_rule_or_exempted_token_is_observed(self):
        self.assertEqual(self.rejected(b'private@example.invalid password='+PRIVATE.encode()),
            'ARCTIC-EVIDENCE-RULE=source-view-email-shape\n')
        safe=b'2026-10-10T18:00:00.000Z [  OK  ] Stopped systemd-zram-setup@zram0.service - Create swap on /dev/zram0.\n'
        self.assertIs(S.external_text(safe),safe)
        self.assertEqual(self.rejected(safe+b'password='+PRIVATE.encode()),'ARCTIC-EVIDENCE-RULE=source-view-named-secret\n')

    def test_original_terminal_passes_have_distinct_bounded_phases(self):
        self.assertEqual(self.rejected(b'pa\x1b[2Jssword='+PRIVATE.encode()),'ARCTIC-EVIDENCE-RULE=terminal-view-named-secret\n')
        # DCS P conceals the original leading word boundary, which the original
        # payload scan already checks before removing terminal bookkeeping.
        self.assertEqual(self.rejected(b'\x1bPpassword='+PRIVATE.encode()+b'\x1b\\'),
            'ARCTIC-EVIDENCE-RULE=terminal-payload-named-secret\n')

    def test_ordinary_observer_failure_preserves_exact_original_primary(self):
        for failure in (RuntimeError(PRIVATE),TypeError(PRIVATE),OSError(PRIVATE)):
            original=RuntimeError('Sensitive text in external evidence')
            with patch.object(S,'RuntimeError',create=True,return_value=original), \
                    patch.object(S,'diagnose_sensitive_match',side_effect=failure):
                with self.assertRaises(RuntimeError) as caught:S.external_text(b'password='+PRIVATE.encode())
            self.assertIs(caught.exception,original)

    def test_pending_observer_or_original_cancellation_keeps_exact_identity(self):
        for cancellation in (KeyboardInterrupt(PRIVATE),SystemExit(PRIVATE)):
            with patch.object(S,'diagnose_sensitive_match',side_effect=cancellation):
                with self.assertRaises(type(cancellation)) as caught:S.external_text(b'password='+PRIVATE.encode())
            self.assertIs(caught.exception,cancellation)
            with patch.object(S,'classification_view',side_effect=cancellation):
                with self.assertRaises(type(cancellation)) as caught:S.external_text(b'public')
            self.assertIs(caught.exception,cancellation)

    def test_hostile_inputs_and_closed_output_never_export_match_values(self):
        class Hostile:
            def group(self,*_):raise AssertionError('private group accessed')
        class HostilePhase(str):
            def __eq__(self,*_):raise AssertionError('private phase compared')
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            S.diagnose_sensitive_match(Hostile(),'source-view')
            S.diagnose_sensitive_match(Hostile(),HostilePhase('source-view'))
        self.assertEqual(out.getvalue(),'ARCTIC-EVIDENCE-RULE=source-view-unknown-rule\n')
        for phase in S.EXTERNAL_RULE_PHASES:
            for category in (*[v[0] for v in S.EXTERNAL_RULE_ALTERNATIVES],'unknown-rule'):
                raw=('ARCTIC-EVIDENCE-RULE='+phase+'-'+category+'\n').encode()
                self.assertIs(S.external_text(raw),raw)

if __name__=='__main__':unittest.main()
