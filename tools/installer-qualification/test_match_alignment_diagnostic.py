"""Owned synthetic first-rejection controls; no private original or VM admission."""
import ast, contextlib, hashlib, importlib.util, io, json, re, tempfile, types, unittest
from pathlib import Path
from unittest import mock
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('match_alignment_under_test',HERE/'screen-diagnostic.py')
D=importlib.util.module_from_spec(spec);spec.loader.exec_module(D)
BASE_SHA='464a5d49324368c00315d77a9e1b8cf48f535396fa3004b24b8151d543fcf3c4'

def restored_source():
    raw=(HERE/'screen-diagnostic.py').read_text()
    first=raw.index('# BEGIN EXACT_REJECTED_MATCH_ALIGNMENT')
    last=raw.index('def classify_match(',first)
    raw=raw[:first]+raw[last:]
    raw=raw.replace('observations.append(annotated_match(m, match, phase, original, boundaries, removed))',
                    'observations.append(classify_match(m, match, phase, original, boundaries, removed))',1)
    assert hashlib.sha256(raw.encode()).hexdigest()==BASE_SHA
    return raw

class MatchAlignmentDiagnostic(unittest.TestCase):
    def observe(self, text):
        raw=text.encode() if type(text) is str else text
        m=D.scanner();prior=m.diagnose_sensitive_match;out=io.StringIO()
        with contextlib.redirect_stdout(out): passed,reason,rows=D.screened_text(m,raw)
        self.assertFalse(passed);self.assertEqual(reason,'sensitive-text');self.assertEqual(len(rows),1)
        self.assertEqual(out.getvalue(),'');self.assertIs(m.diagnose_sensitive_match,prior)
        a=rows[0]['source_match_diagnostic']
        self.assertTrue(a['source_text_observation_only'])
        for k in ('actual_code_ownership','privacy_admitted','runtime_cause_proven'):self.assertIs(a[k],False)
        return rows[0]
    def test_complete_helper_inverse_scanner_and_original_predicate_AST(self):
        old=restored_source();new=(HERE/'screen-diagnostic.py').read_text()
        old_functions={x.name:x for x in ast.parse(old).body if isinstance(x,ast.FunctionDef)}
        new_functions={x.name:x for x in ast.parse(new).body if isinstance(x,ast.FunctionDef)}
        for name,node in old_functions.items():
            if name!='screened_text':self.assertEqual(ast.dump(node),ast.dump(new_functions[name]))
        self.assertEqual(hashlib.sha256((HERE.parent/'native-functional/screen-evidence.py').read_bytes()).hexdigest(),D.SCANNER_SHA256)
    def test_same_first_rejection_and_all_original_row_fields_for_actual_views(self):
        old=types.ModuleType('exact_464a_replay');old.__file__=str(HERE/'screen-diagnostic.py')
        exec(compile(restored_source(),old.__file__,'exec'),old.__dict__)
        cases=['getty@tty2.service\n','modprobe@nvmet_tcp.service\n','modprobe@thunderbolt_net.service\n',
          'dbus-:1.2-org.freedesktop.Notifications@0.service\n','private-probe@unknown.instance.service\n',
          '/serial-getty@ttyS0.service\n','password=SYNTHETIC_SENTINEL\ngetty@tty2.service\n',
          'getty@tt\x1b[31my2.service\n','getty@tt\x1b[1Cy2.service\n','\x1b]0;getty@tty2.service\x07\n']
        for n,text in enumerate(cases):
            with self.subTest(public_case=n):
                row=self.observe(text);row.pop('source_match_diagnostic')
                with contextlib.redirect_stdout(io.StringIO()): prior=old.screened_text(old.scanner(),text.encode())
                self.assertEqual((False,'sensitive-text',[row]),prior)
    def test_known_literals_family_and_unknown_unit_reason_remain_strict_rejections(self):
        for literal,label in D.EXTRA_UNIT_CANDIDATES:
            r=self.observe(literal+'\n');self.assertEqual(r['public_candidate'],label)
            self.assertEqual(r['source_match_diagnostic']['candidate_reason'],'known-public-literal')
        r=self.observe('dbus-:1.2-org.freedesktop.Notifications@0.service\n')
        self.assertEqual(r['generated_source_family'],'broker-public-notifications')
        self.assertEqual(r['source_match_diagnostic']['family_reason'],'known-public-family')
        r=self.observe('private-probe@unknown.instance.service\n')
        self.assertTrue(r['unit_like']);self.assertTrue(r['original_contiguous']);self.assertTrue(r['delimiter_bounded'])
        self.assertEqual(r['public_candidate'],'unknown');self.assertEqual(r['generated_source_family'],'unknown')
        self.assertEqual(r['source_match_diagnostic']['candidate_reason'],'not-catalogued-public-literal')
        self.assertEqual(r['source_match_diagnostic']['family_reason'],'not-known-public-family-fragment')
        self.assertEqual(r['source_match_diagnostic']['source_rule'],'external-rule-004')
        self.assertNotIn('private-probe',json.dumps(r));self.assertNotIn('unknown.instance',json.dumps(r))
    def test_foreign_regex_pattern_flags_and_truncated_window_fail_closed(self):
        m=D.scanner();text='getty@tty2.service suffix';empty=m.array('I');re.purge()
        foreign=re.compile(m.EXTERNAL_SENSITIVE.pattern,m.EXTERNAL_SENSITIVE.flags)
        self.assertIsNot(foreign,m.EXTERNAL_SENSITIVE)
        row=D.annotated_match(m,foreign.search(text),'source-view',text,empty,empty)
        self.assertEqual(row['source_match_diagnostic']['regex'],'foreign-regex-match')
        for key in ('public_candidate','generated_source_family','known_source_fragment'):self.assertEqual(row[key],'unknown')
        row=D.annotated_match(m,m.EXTERNAL_SENSITIVE.search(text,0,len('getty@tty2.service')),'source-view',text,empty,empty)
        self.assertEqual(row['source_match_diagnostic']['offsets'],'match-window-differs');self.assertEqual(row['public_candidate'],'unknown')
        for rx in (re.compile('getty@tty2.service'),re.compile(m.EXTERNAL_SENSITIVE.pattern,re.IGNORECASE|re.ASCII)):
            with mock.patch.object(m,'EXTERNAL_SENSITIVE',rx):
                row=D.annotated_match(m,rx.search(text),'source-view',text,empty,empty)
                self.assertEqual(row['source_match_diagnostic']['regex'],'scanner-pattern-differs');self.assertEqual(row['public_candidate'],'unknown')
    def test_exact_full_view_map_and_unknown_offsets_never_receive_public_label(self):
        m=D.scanner();original='\x1b[32mgetty@tty2.service\x1b[0m\n';view,bounds,removed=m.classification_view(original)
        match=m.EXTERNAL_SENSITIVE.search(view)
        good=D.annotated_match(m,match,'source-view',original,bounds,removed)
        self.assertEqual(good['public_candidate'],'getty-template-tty2');self.assertEqual(good['source_match_diagnostic']['mapping'],'exact-source-view')
        cases=[(original,m.array('I',[0,0]),removed),(original,bounds,m.array('I',[4,9])),
          (original,m.array('I'),m.array('I')),(original,m.array('Q',bounds),m.array('Q',removed)),
          ('different-prefix '+original,bounds,removed),(original+'different-suffix',bounds,removed),
          (original,[],[])]
        for n,(raw,a,b) in enumerate(cases):
            with self.subTest(public_case=n):
                row=D.annotated_match(m,match,'source-view',raw,a,b)
                self.assertEqual(row['public_candidate'],'unknown');self.assertEqual(row['source_match_diagnostic']['candidate_reason'],'source-alignment-unverified')
    def test_broker_reason_numeric_prefix_boundary_and_original_split_are_closed(self):
        token='dbus-:1.2-org.freedesktop.Notifications@0.service'
        cases=[(token.replace('1.2','1.02'),'noncanonical-source-numeric-shape'),
          (token.replace('@0','@00'),'noncanonical-source-numeric-shape'),
          (token.replace('1.2','1.18446744073709551615'),'source-numeric-range-differs'),
          (token.replace('@0','@18446744073709551616'),'source-numeric-range-differs'),
          (token.replace('dbus-:','other-:'),'known-family-prefix-differs'),
          (token.replace('dbus-:','dbus-\x1b[31m:'),'known-family-prefix-differs'),
          ('/'+token,'whole-family-delimiter-differs'),
          (token.replace('Notifications','Notifi\x1b[31mcations'),'family-fragment-not-contiguous'),
          (token.replace('Notifications','Other'),'not-known-public-family-fragment')]
        for n,(text,reason) in enumerate(cases):
            with self.subTest(public_case=n):
                r=self.observe(text+'\n');self.assertEqual(r['generated_source_family'],'unknown');self.assertEqual(r['source_match_diagnostic']['family_reason'],reason)
        encoded=json.dumps([self.observe(text+'\n')['source_match_diagnostic'] for text,_ in cases])
        for x in ('18446744073709551615','18446744073709551616','dbus-:','Other','Notifi'):self.assertNotIn(x,encoded)
    def test_first_rejection_named_secret_payload_terminal_views_and_utf8_unchanged(self):
        token='dbus-:1.2-org.freedesktop.Notifications@0.service'
        r=self.observe('password=SYNTHETIC_SENTINEL\n'+token)
        self.assertEqual(r['source_match_diagnostic']['source_rule'],'external-rule-007');self.assertEqual(r['generated_source_family'],'unknown')
        r=self.observe('getty@tt\x1b[1Cy2.service\n')
        self.assertEqual(r['phase'],'terminal-view');self.assertEqual(r['source_match_diagnostic']['mapping'],'exact-terminal-view')
        r=self.observe('\x1b]0;'+token+'\x07\n');self.assertEqual(r['generated_source_family'],'unknown')
        with contextlib.redirect_stdout(io.StringIO()):passed,reason,rows=D.screened_text(D.scanner(),b'\xff\n')
        self.assertEqual((passed,reason,rows),(False,'invalid-utf8',[]))
        r=self.observe('סינתטי@example.invalid\n');self.assertEqual(r['public_candidate'],'unknown');self.assertNotIn('סינתטי',json.dumps(r))
    def test_actual_original_exception_cancellation_and_prior_hook_are_preserved(self):
        m=D.scanner();original=RuntimeError('Sensitive text in external evidence')
        with mock.patch.object(m,'RuntimeError',create=True,return_value=original),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError) as caught:m.external_text(b'getty@tty2.service\n')
        self.assertIs(caught.exception,original)
        for error in (KeyboardInterrupt(),SystemExit()):
            m=D.scanner();prior=m.diagnose_sensitive_match
            with mock.patch.object(D,'annotated_match',side_effect=error):
                with self.assertRaises(type(error)) as caught:D.screened_text(m,b'getty@tty2.service\n')
            self.assertIs(caught.exception,error);self.assertIs(m.diagnose_sensitive_match,prior)
    def test_prepare_sidecar_safe_finite_fields_without_rejected_original_upload(self):
        for profile in ('idle','active'):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);source=root/'source';(source/'host').mkdir(parents=True)
                raw=b'private-probe@unknown.instance.service\n';(source/'host/serial.log').write_bytes(raw)
                report=D.prepare(source,root/'out',profile)
                self.assertEqual(report['full_strict_screen'],'REJECTED');self.assertFalse(report['release_acceptance']);self.assertFalse(report['image_qualified'])
                self.assertFalse((root/'out/host/serial.log').exists());self.assertEqual((source/'host/serial.log').read_bytes(),raw)
                self.assertNotIn('private-probe',json.dumps(report));self.assertNotIn('unknown.instance',json.dumps(report))
                D.scanner().external_text((root/'out/diagnostic-partial.json').read_bytes())
    def test_oversize_match_does_not_copy_operand_or_claim_alignment(self):
        import tracemalloc
        m=D.scanner();text='https://public.invalid/?'+'x'*262144+'\n';match=m.EXTERNAL_SENSITIVE.search(text)
        tracemalloc.start();row=D.annotated_match(m,match,'source-view',text,m.array('I'),m.array('I'));_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        self.assertEqual(row['source_match_diagnostic']['offsets'],'match-outside-diagnostic-bound');self.assertEqual(row['public_candidate'],'unknown');self.assertLess(peak,8192)

if __name__=='__main__':unittest.main(verbosity=2)
