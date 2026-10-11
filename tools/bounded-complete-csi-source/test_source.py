"""Actual Source functions on declared synthetic buffers only."""
from pathlib import Path
import ast
import contextlib
import hashlib
import io
import json
import tracemalloc
import types
import unittest

HERE = Path(__file__).resolve().parent
BASE = Path('/workspace/arctic-complete-csi-boundary-Source-20261011/tools/complete-csi-boundary-source')

def load(path, name):
    raw = path.read_bytes()
    module = types.ModuleType(name); module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module, raw

S, RAW = load(HERE / 'scanner.py', 'owned_bounded_complete_CSI_scanner')
H, HRAW = load(HERE / 'match-diagnostic.py', 'owned_bounded_complete_CSI_helper')
B, OLD = load(BASE / 'scanner.py', 'owned_current8b9_scanner')
BH, HOLD = load(BASE / 'match-diagnostic.py', 'owned_current_a92_helper')
assert hashlib.sha256(OLD).hexdigest() == '8b9fbbe3bb9241dca8232e7cee61e05fec10bfbb0bc1e9d0d62dbfb7bda8e8ea'
assert hashlib.sha256(HOLD).hexdigest() == 'a92c57e53172efe8fbed8fce076341184e293ff9d525c1fda87678d6a9ba36c6'

def failure(text, module=S):
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            module.external_text(text.encode())
        except RuntimeError as error:
            tb = error.__traceback__
            while tb:
                frame = tb.tb_frame
                if frame.f_code is module.reject_sensitive_match.__code__ and frame.f_globals is module.__dict__:
                    assert tb.tb_lineno == 139
                    return error, {key: frame.f_locals[key] for key in ('match', 'phase', 'original', 'boundaries', 'removed')}
                tb = tb.tb_next
            return error, None
    raise AssertionError('Synthetic rejection was expected')

def alignment(values):
    return H.diagnostic_view_alignment(S, *(values[key] for key in ('match', 'phase', 'original', 'boundaries', 'removed')))

class Controls(unittest.TestCase):
    def test_three_actual_current_counterexamples_and_all_bounded_CSI_finals(self):
        for control in ('\x1b[1A', '\x1b[?25h', '\x1b[1B'):
            error, values = failure(control + '@public.example', B)
            self.assertEqual(error.args, ('Sensitive text in external evidence',))
            self.assertEqual(values['phase'], 'source-view')
            content = (control + '@public.example').encode()
            self.assertIs(S.external_text(content), content)
        for final in ('@', 'A', 'B', 'C', 'h', 'l', '~'):
            control = '\x1b[12;34' + final
            view, _, _ = S.classification_view(control + '@public.example')
            self.assertEqual(view, '\x1b' + ' ' * (len(control) - 1) + '@public.example')
        # Plain exact public fixture remains unchanged by the scanner policy.
        content = b'arcticqual@arctic-qual ~ >'
        self.assertIs(S.external_text(content), content)

    def test_genuine_ordinary_and_display_joined_sensitive_text_still_rejects(self):
        for text in ('synthetic-user@synthetic.example', 'password=synthetic-private',
                     'ghp_syntheticprivate', 'authorization: Bearer synthetic-private',
                     'https://public.example/?private=value',
                     'synthetic-user@\x1b[1Asynthetic.example',
                     'synthetic-\x1b[?25huser@synthetic.example',
                     'pass\x1b[1Bword=synthetic-private',
                     'ghp_\x1b[1Asyntheticprivate'):
            error, _ = failure(text)
            self.assertEqual(error.args, ('Sensitive text in external evidence',))

    def test_OSC_DCS_and_non_CSI_payloads_remain_byte_exact_and_private(self):
        for start, end in (('\x1b]0;', '\x07'), ('\x1b]7;', '\x1b\\'),
                           ('\x1bP', '\x1b\\'), ('\x1bX', '\x1b\\'),
                           ('\x1b^', '\x1b\\'), ('\x1b_', '\x1b\\')):
            public = start + 'public title 12@public.example' + end
            self.assertEqual(S.classification_view(public), B.classification_view(public))
            error, _ = failure(start + 'synthetic-user@synthetic.example' + end)
            self.assertEqual(error.args, ('Sensitive text in external evidence',))
        for text in ('\x1b(0', '\x1bM', 'ordinary@public.example'):
            self.assertEqual(S.classification_view(text), B.classification_view(text))

    def test_incomplete_malformed_order_and_4096_bound_stay_closed(self):
        for text in ('\x1b[1', '\x1b[1\npublic.example', '\x1b[1\x00@public.example',
                     '\x1b[1😀@public.example', '\x1b[ 1A@public.example',
                     '\x1b]0;public title', '\x1b[1A\x1b'):
            failure(text)
        exact = '\x1b[' + '1' * 4093 + 'A'
        self.assertEqual(S.classification_view(exact)[0], '\x1b' + ' ' * 4095)
        oversize = '\x1b[' + '1' * 4094 + 'A'
        self.assertEqual(S.classification_view(oversize)[0], oversize)
        failure(oversize + '@public.example')

    def test_scanner_whole_inverse_one_function_original_raise_and_rules(self):
        start = RAW.index(b'def classification_view('); end = RAW.index(b'\n\ndef original_span(', start)
        old_start = OLD.index(b'def classification_view('); old_end = OLD.index(b'\n\ndef original_span(', old_start)
        self.assertEqual(RAW[:start] + OLD[old_start:old_end] + RAW[end:], OLD)
        self.assertEqual(RAW[:start], OLD[:old_start])
        old_ast = ast.parse(OLD); new_ast = ast.parse(RAW)
        before = {n.name: ast.dump(n) for n in old_ast.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        after = {n.name: ast.dump(n) for n in new_ast.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        self.assertEqual([name for name in before if before[name] != after[name]], ['classification_view'])
        for name in ('SENSITIVE','EXTERNAL_SENSITIVE','TERMINAL','SGR','STRING_PAYLOADS','OSC3008_SERVICE'):
            self.assertEqual((getattr(S,name).pattern,getattr(S,name).flags),(getattr(B,name).pattern,getattr(B,name).flags))
        for name in ('EXTERNAL_EMAIL_CANDIDATES','CANONICAL_UNITS','OSC3008_SERVICE_MAX_CHARS','MAX_DIAGNOSTIC_MATCH_BYTES'):
            self.assertEqual(getattr(S,name),getattr(B,name))

    def test_actual_alignment_SGR_Unicode_control_and_chunk_boundaries(self):
        for text in ('אב\x1b[31m \x1b[1A ordinary synthetic-user@synthetic.example',
                     'x' * 4090 + '\x1b[12;34A synthetic-user@synthetic.example',
                     'x' * 4094 + '\x1b[?25h synthetic-user@synthetic.example',
                     '\x1b[1\x1b[31mA synthetic-user@synthetic.example',
                     '\x1b[' + '1' * 4093 + 'A synthetic-user@synthetic.example',
                     '\x1b[1\x1b[2A@public.example synthetic-user@synthetic.example'):
            error, values = failure(text)
            self.assertEqual(error.args, ('Sensitive text in external evidence',))
            self.assertEqual(values['phase'], 'source-view')
            self.assertEqual(alignment(values), dict(regex='exact-scanner-regex',offsets='exact-scanner-span',mapping='exact-source-view'))
        # The independent original terminal view and its mapping are unchanged.
        text = 'synthetic-user@\x1b[1Asynthetic.example'
        error, values = failure(text)
        self.assertEqual(values['phase'],'terminal-view')
        self.assertEqual(alignment(values)['mapping'],'exact-terminal-view')
        self.assertEqual(S.classification_view(text,escapes=S.TERMINAL),B.classification_view(text,escapes=B.TERMINAL))

    def test_alignment_rejects_foreign_match_forged_map_and_incomplete_mask(self):
        import re
        text = '\x1b[1A synthetic-user@synthetic.example'
        _, values = failure(text)
        changed = dict(values,match=re.compile(S.EXTERNAL_SENSITIVE.pattern,S.EXTERNAL_SENSITIVE.flags).search(values['match'].string))
        # re caches identical regex objects; purge makes this genuinely foreign.
        re.purge();changed['match']=re.compile(S.EXTERNAL_SENSITIVE.pattern,S.EXTERNAL_SENSITIVE.flags).search(values['match'].string)
        self.assertEqual(alignment(changed)['regex'],'foreign-regex-match')
        changed = dict(values,boundaries=S.array('I',[0]),removed=S.array('I',[1]))
        self.assertEqual(alignment(changed)['mapping'],'original-map-differs')
        changed = dict(values,original=text.replace('\x1b[1A','\x1b[1\x00A'))
        self.assertEqual(alignment(changed)['mapping'],'scanner-view-differs')

    def test_helper_whole_inverse_only_alignment_and_scanner_hash(self):
        start = HRAW.index(b'def diagnostic_view_alignment(');end = HRAW.index(b'\n\ndef diagnostic_candidate_reason(',start)
        old_start = HOLD.index(b'def diagnostic_view_alignment(');old_end = HOLD.index(b'\n\ndef diagnostic_candidate_reason(',old_start)
        restored = HRAW[:start]+HOLD[old_start:old_end]+HRAW[end:]
        restored=restored.replace(hashlib.sha256(RAW).hexdigest().encode(),hashlib.sha256(OLD).hexdigest().encode())
        self.assertEqual(restored,HOLD)
        old_ast={n.name:ast.dump(n) for n in ast.parse(HOLD).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
        new_ast={n.name:ast.dump(n) for n in ast.parse(HRAW).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
        self.assertEqual([name for name in old_ast if old_ast[name]!=new_ast[name]],['diagnostic_view_alignment'])

    def test_bounded_stream_replay_memory_and_unsigned_original_positions(self):
        text='אב'+('\x1b[1A'*131072)+' synthetic-user@synthetic.example'
        _,values=failure(text)
        self.assertEqual(values['boundaries'].typecode,'I');self.assertEqual(values['removed'].typecode,'I')
        tracemalloc.start()
        try:
            self.assertEqual(alignment(values)['mapping'],'exact-source-view')
            _,peak=tracemalloc.get_traced_memory()
        finally:tracemalloc.stop()
        self.assertLess(peak,256*1024)
        first,last=S.original_span(*values['match'].span(),values['boundaries'],values['removed'])
        self.assertEqual(text[first:last],'synthetic-user@synthetic.example')

    def test_actual_owned_Code_global_original_primary_and_finite_shape(self):
        parent=Path('/workspace/arctic-bios-public-shape-fields-consumer-Source-0d267-20261011/public-execution/tools')
        observer,_=load(parent/'final-bios-same-match-public-shape-source/observer.py','owned_original_observer')
        common,craw=load(parent/'final-bios-install/common.py','owned_original_common')
        so=observer.OwnedSource(S.__dict__,RAW,str(HERE/'scanner.py'),'original-scanner')
        ho=observer.OwnedSource(H.__dict__,HRAW,str(HERE/'match-diagnostic.py'),'match-diagnostic')
        co=observer.OwnedSource(common.__dict__,craw,common.__file__,'bios-common')
        vocabulary=frozenset({n.value for n in ast.walk(ast.parse(HRAW)) if isinstance(n,ast.Constant) and type(n.value)is str}|{'external-rule-'+format(n,'03d') for n in range(1,11)})
        error,values=failure('\x1b[1A synthetic-user@synthetic.example')
        actual=observer.describe(error,(),co,[(S,so)],H,ho,vocabulary,())
        self.assertEqual(actual['original_source_site']['source_line'],139)
        self.assertEqual(actual['original_source_site']['source_sha256'],hashlib.sha256(RAW).hexdigest())
        self.assertEqual(actual['same_rejected_match']['mapping'],'exact-source-view')
        self.assertNotIn('synthetic-user',json.dumps(actual));self.assertIs(type(error),RuntimeError)
        old_code=S.reject_sensitive_match.__code__
        try:
            S.reject_sensitive_match.__code__=old_code.replace(co_name='foreign_static_reject')
            self.assertFalse(so.unchanged())
            self.assertIsNone(observer.describe(error,(),co,[(S,so)],H,ho,vocabulary,()))
        finally:S.reject_sensitive_match.__code__=old_code

if __name__ == '__main__':
    unittest.main(verbosity=2)
