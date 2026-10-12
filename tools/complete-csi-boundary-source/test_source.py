"""Actual corrected/parent scanner functions on owned synthetic input only."""
import ast
import contextlib
import hashlib
import io
from pathlib import Path
import tracemalloc
import types
import unittest

HERE = Path(__file__).resolve().parent
PARENT = Path('/workspace/arctic-bios-public-shape-fields-consumer-Source-0d267-20261011/public-execution/tools/final-bios-format-compatible-install/scanner.py')
PARENT_SHA = 'b3d56536397ff1c46caf082b97a070ff3eae383c2c277898c572cb34eb76f336'

def load(path, name):
    raw = path.read_bytes()
    module = types.ModuleType(name); module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module, raw

S, RAW = load(HERE / 'scanner.py', 'owned_complete_csi_scanner')
B, OLD = load(PARENT, 'owned_parent_b3_scanner')
assert hashlib.sha256(OLD).hexdigest() == PARENT_SHA

def reject(module, raw):
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            module.external_text(raw)
        except RuntimeError as error:
            return error
    raise AssertionError('Synthetic sensitive or malformed input was admitted')

class Controls(unittest.TestCase):
    def test_exact_one_function_inverse_and_original_rules_unchanged(self):
        old = ast.parse(OLD); new = ast.parse(RAW)
        before = {n.name: ast.dump(n, include_attributes=False) for n in old.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        after = {n.name: ast.dump(n, include_attributes=False) for n in new.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        self.assertEqual(set(before), set(after))
        self.assertEqual([k for k in before if before[k] != after[k]], ['classification_view'])
        begin = RAW.index(b'def classification_view('); end = RAW.index(b'\n\ndef original_span(', begin)
        obegin = OLD.index(b'def classification_view('); oend = OLD.index(b'\n\ndef original_span(', obegin)
        self.assertEqual(RAW[:begin] + OLD[obegin:oend] + RAW[end:], OLD)
        for key in ('SENSITIVE', 'EXTERNAL_SENSITIVE', 'SGR', 'TERMINAL', 'STRING_PAYLOADS', 'OSC3008_SERVICE'):
            self.assertEqual((getattr(S, key).pattern, getattr(S, key).flags), (getattr(B, key).pattern, getattr(B, key).flags))
        for key in ('MAX_DIAGNOSTIC_MATCH_BYTES', 'OSC3008_SERVICE_MAX_CHARS', 'CANONICAL_UNITS', 'EXTERNAL_EMAIL_CANDIDATES', 'EXTERNAL_RULE_ALTERNATIVES'):
            self.assertEqual(getattr(S, key), getattr(B, key))

    def test_deterministic_parent_counterexample_is_corrected_without_raw_repair(self):
        for csi in ('\x1b[1@', '\x1b[1;2@', '\x1b[?1@', '\x1b[1 @', '\x1b[@'):
            raw = (csi + 'public.example').encode()
            if csi in ('\x1b[1 @', '\x1b[@'):
                self.assertIs(B.external_text(raw), raw)
            else:
                self.assertEqual(reject(B, raw).args, ('Sensitive text in external evidence',))
            self.assertIs(S.external_text(raw), raw)
            view, _, _ = S.classification_view(raw.decode())
            self.assertEqual(len(view), len(raw))
            self.assertEqual(view[-len('public.example'):], 'public.example')
            self.assertEqual(view[len(csi) - 1], ' ')

    def test_genuine_plain_and_csi_split_email_credentials_remain_fatal(self):
        for text in ('synthetic-user@synthetic.example',
                     'synthetic-user@\x1b[1@synthetic.example',
                     'synthetic-\x1b[1@user@synthetic.example',
                     'password=synthetic-private', 'pass\x1b[1@word=synthetic-private',
                     'ghp_syntheticprivate', 'ghp_\x1b[1@syntheticprivate',
                     'authorization: Bearer synthetic-private',
                     'transcript: synthetic-private', 'https://public.example/?private=value'):
            self.assertEqual(reject(S, text.encode()).args, ('Sensitive text in external evidence',))

    def test_string_payloads_and_adjacent_private_content_are_not_dropped(self):
        for prefix, suffix in (('\x1b]0;', '\x07'), ('\x1b]7;', '\x1b\\'),
                               ('\x1bP', '\x1b\\'), ('\x1bX', '\x1b\\'),
                               ('\x1b^', '\x1b\\'), ('\x1b_', '\x1b\\')):
            for text in ('synthetic-user@synthetic.example', 'password=synthetic-private'):
                raw = (prefix + text + suffix).encode()
                self.assertEqual(reject(S, raw).args, ('Sensitive text in external evidence',))
        for text in ('\x1b[1@synthetic-user@synthetic.example',
                     '\x1b[1@public.example password=synthetic-private'):
            self.assertEqual(reject(S, text.encode()).args, ('Sensitive text in external evidence',))

    def test_incomplete_malformed_and_oversized_control_frames_fail_closed(self):
        for text in ('\x1b[1', '\x1b[1;@\x1b', '\x1b[1\npublic.example',
                     '\x1b[1\x00@public.example', '\x1b]0;public.example',
                     '\x1b[1😀@public.example'):
            reject(S, text.encode())
        oversized = '\x1b[' + '1' * 4094 + '@public.example'
        self.assertEqual(reject(S, oversized.encode()).args, ('Sensitive text in external evidence',))
        exact = '\x1b[' + '1' * 4093 + '@public.example'
        self.assertEqual(S.external_text(exact.encode()), exact.encode())

    def test_parameters_unicode_and_original_offset_mapping_are_preserved(self):
        text = 'אב\x1b[31m prefix \x1b[12;34@ synthetic-user@synthetic.example'
        view, boundaries, removed = S.classification_view(text)
        self.assertIn('12;34 ', view); self.assertIn('אב', view)
        match = S.EXTERNAL_SENSITIVE.search(view)
        self.assertEqual(match.group(), 'synthetic-user@synthetic.example')
        first, last = S.original_span(*match.span(), boundaries, removed)
        self.assertEqual(text[first:last], match.group())
        self.assertEqual((list(boundaries), list(removed)), ([2], [5]))
        self.assertEqual(reject(S, text.encode()).args, ('Sensitive text in external evidence',))

    def test_original_terminal_view_and_explicit_escape_parameter_are_identical(self):
        for text in ('אב\x1b[1@x\x1b]0;public title\x07',
                     'user@\x1b[1@public.example', '\x1b[31mplain\x1b[0m'):
            got = S.classification_view(text, escapes=S.TERMINAL)
            expected = B.classification_view(text, escapes=B.TERMINAL)
            self.assertEqual((got[0], list(got[1]), list(got[2])), (expected[0], list(expected[1]), list(expected[2])))
        self.assertEqual(S.classification_view('\x1b[123456789;42@')[0], '\x1b[123456789;42 ')

    def test_only_proven_csi_final_at_is_changed_and_not_payload_at(self):
        for text in ('\x1b[1A', '\x1b[1L', '\x1b[1P', '\x1b]0;literal@\x07',
                     '\x1bP1@\x1b\\', 'ordinary@text', '\x1b[@'):
            got = S.classification_view(text)[0]
            self.assertEqual(got, text[:-1] + ' ' if text == '\x1b[@' else text)

    def test_old_public_token_contiguity_and_all_rule_rejections_are_preserved(self):
        safe = ('$ useradd --root /mnt --create-home --user-group --groups wheel --shell /usr/bin/fish '
                "--comment 'Arctic CI' --password [secret: password hash] ci")
        for text in ('plain public text', safe, 'arcticqual@arctic-qual ~ >'):
            raw = text.encode(); self.assertEqual(S.external_text(raw), B.external_text(raw))
        for literal, _ in S.EXTERNAL_EMAIL_CANDIDATES:
            raw = (' ' + literal + ' ').encode()
            try:
                before = B.external_text(raw)
            except RuntimeError as error:
                self.assertEqual(reject(S, raw).args, error.args)
            else:
                self.assertEqual(S.external_text(raw), before)
        for text in ('ghp_syntheticprivate', 'AKIAABCDEFGHIJKLMNOP', 'authorization: Bearer private',
                     'synthetic-user@synthetic.example', 'https://public.example/?q=private',
                     'https://user@public.example', 'password=private', '--token private',
                     'cryptsetup open private < private', 'transcription: private'):
            self.assertEqual(reject(S, text.encode()).args, reject(B, text.encode()).args)
        reject(S, b' user-runtime-\x1b[1@dir@1000.service ')

    def test_many_csi_controls_have_compact_bounded_memory(self):
        raw = b'\x1b[1@' * 131072
        tracemalloc.start()
        try:
            self.assertIs(S.external_text(raw), raw)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(peak, 16 * len(raw))

    def test_loaded_source_code_globals_original_raise_and_alignment_are_bound(self):
        folder = PARENT.parents[1] / 'final-bios-same-match-public-shape-source'
        observer, oraw = load(folder / 'observer.py', 'owned_original_shape_observer')
        helper, hraw = load(HERE / 'match-diagnostic.py', 'owned_corrected_shape_helper')
        common, craw = load(PARENT.parents[1] / 'final-bios-install/common.py', 'owned_original_shape_common')
        so = observer.OwnedSource(S.__dict__, RAW, str(HERE / 'scanner.py'), 'original-scanner')
        ho = observer.OwnedSource(helper.__dict__, hraw, helper.__file__, 'match-diagnostic')
        co = observer.OwnedSource(common.__dict__, craw, common.__file__, 'bios-common')
        vocabulary = frozenset({n.value for n in ast.walk(ast.parse(hraw))
            if isinstance(n, ast.Constant) and type(n.value) is str}
            | {'external-rule-' + format(n, '03d') for n in range(1, 11)})
        error = reject(S, b'\x1b[1@public.example synthetic-user@synthetic.example')
        value = observer.describe(error, (), co, [(S, so)], helper, ho, vocabulary, ())
        self.assertEqual(value['original_source_site']['source_sha256'], hashlib.sha256(RAW).hexdigest())
        self.assertEqual(value['original_source_site']['source_line'], 139)
        self.assertEqual(value['original_source_site']['function'], 'reject_sensitive_match')
        self.assertEqual(value['same_rejected_match']['regex'], 'exact-scanner-regex')
        self.assertEqual(value['same_rejected_match']['offsets'], 'exact-scanner-span')
        self.assertEqual(value['same_rejected_match']['mapping'], 'exact-source-view')
        self.assertIs(type(error), RuntimeError); self.assertTrue(so.unchanged()); self.assertTrue(ho.unchanged())
        self.assertNotIn('synthetic-user', __import__('json').dumps(value))

    def test_helper_whole_inverse_only_alignment_function_and_scanner_literal(self):
        before = (PARENT.parents[1] / 'final-bios-same-match-public-shape-source/match-diagnostic.py').read_bytes()
        after = (HERE / 'match-diagnostic.py').read_bytes()
        bstart = before.index(b'def diagnostic_view_alignment('); bend = before.index(b'\n\ndef diagnostic_candidate_reason(', bstart)
        astart = after.index(b'def diagnostic_view_alignment('); aend = after.index(b'\n\ndef diagnostic_candidate_reason(', astart)
        restored = after[:astart] + before[bstart:bend] + after[aend:]
        restored = restored.replace(hashlib.sha256(RAW).hexdigest().encode(), PARENT_SHA.encode())
        self.assertEqual(restored, before)
        old_nodes = {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(before).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        new_nodes = {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(after).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        self.assertEqual(set(old_nodes), set(new_nodes))
        self.assertEqual([k for k in old_nodes if old_nodes[k] != new_nodes[k]], ['diagnostic_view_alignment'])

    def test_helper_replay_accepts_only_the_exact_new_same_position_projection(self):
        helper, _ = load(HERE / 'match-diagnostic.py', 'owned_replay_corrected_helper')
        for original in ('\x1b[1@public.example synthetic-user@synthetic.example',
                         'אב\x1b[31m\x1b[12;34@public.example synthetic-user@synthetic.example',
                         '\x1b[1\x1b[31m@public.example synthetic-user@synthetic.example',
                         '\x1b]0;synthetic-user@synthetic.example\x07'):
            view, boundaries, removed = S.classification_view(original)
            match = S.EXTERNAL_SENSITIVE.search(view)
            row = helper.diagnostic_view_alignment(S, match, 'source-view', original, boundaries, removed)
            self.assertEqual(row['mapping'], 'exact-source-view')
        original = '\x1b[1@public.example synthetic-user@synthetic.example'
        view, boundaries, removed = S.classification_view(original)
        for forged in (view.replace('1 ', '2 ', 1), view.replace('public.example', 'foreign.example'),
                       view.replace('\x1b[1 ', '\x1b[1@')):
            match = S.EXTERNAL_SENSITIVE.search(forged)
            row = helper.diagnostic_view_alignment(S, match, 'source-view', original, boundaries, removed)
            self.assertNotEqual(row['mapping'], 'exact-source-view')
        oversized = '\x1b[' + '1' * 4094 + '@public.example synthetic-user@synthetic.example'
        original_view, bounds, removed = S.classification_view(oversized)
        forged = original_view[:4096] + ' ' + original_view[4097:]
        match = S.EXTERNAL_SENSITIVE.search(forged)
        self.assertIsNotNone(match)
        self.assertNotEqual(helper.diagnostic_view_alignment(S, match, 'source-view', oversized, bounds, removed)['mapping'], 'exact-source-view')

    def test_helper_replay_keeps_terminal_phase_maps_and_foreign_regex_denial(self):
        helper, _ = load(HERE / 'match-diagnostic.py', 'owned_replay_terminal_helper')
        original = 'synthetic-user@\x1b[1@synthetic.example'
        view, boundaries, removed = S.classification_view(original, escapes=S.TERMINAL)
        match = S.EXTERNAL_SENSITIVE.search(view)
        self.assertEqual(helper.diagnostic_view_alignment(S, match, 'terminal-view', original, boundaries, removed)['mapping'], 'exact-terminal-view')
        S.re.purge(); foreign = S.re.compile(S.EXTERNAL_SENSITIVE.pattern, S.EXTERNAL_SENSITIVE.flags).search(view)
        self.assertIsNot(foreign.re, S.EXTERNAL_SENSITIVE)
        self.assertEqual(helper.diagnostic_view_alignment(S, foreign, 'terminal-view', original, boundaries, removed)['regex'], 'foreign-regex-match')

if __name__ == '__main__':
    unittest.main(verbosity=2)
