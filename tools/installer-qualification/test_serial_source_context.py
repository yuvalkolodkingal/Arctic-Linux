"""Actual rejected matches; fixed public context observations stay unqualified."""
import contextlib, hashlib, importlib.util, io, json
from pathlib import Path
import unittest
HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('source_context_under_test',HERE/'screen-diagnostic.py')
D=importlib.util.module_from_spec(sp);sp.loader.exec_module(D)
class SerialSourceContext(unittest.TestCase):
    def row(self,raw):
        m=D.scanner();passed,reason,rows=D.screened_text(m,raw)
        self.assertFalse(passed);self.assertEqual(reason,'sensitive-text');self.assertTrue(rows)
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(RuntimeError,'^Sensitive text in external evidence$'):m.external_text(raw)
        return rows[0]
    def test_exact_whole_official_unlink_records_are_observed_but_rejected(self):
        for label,path in D.SERIAL_CONTEXT_PATHS:
            row=self.row(("Removed '"+path+"'.\n").encode());v=row['source_context']
            self.assertEqual(v['whole_record'],'official-install-unlink-'+label)
            self.assertEqual((v['preceding'],v['following']),('ascii-slash','ascii-single-quotation'))
            self.assertFalse(v['privacy_admitted']);self.assertFalse(v['runtime_cause_proven'])
            self.assertEqual(row['known_source_fragment'],D.PUBLIC_LABEL)
    def test_exact_masked_unit_and_quote_neighbors(self):
        row=self.row(('Unit '+D.PUBLIC_LITERAL+' is masked, ignoring.\n').encode())
        self.assertEqual(row['source_context']['whole_record'],'official-install-masked-serial-unit')
        for left,right,expected in [('"','"',('ascii-double-quotation','ascii-double-quotation')),('[',']',('ascii-open-square','ascii-close-square')),('(',')',('ascii-open-parenthesis','ascii-close-parenthesis'))]:
            row=self.row((left+D.PUBLIC_LITERAL+right+'\n').encode())
            self.assertEqual(row['source_context']['whole_record'],'unknown')
            self.assertEqual((row['source_context']['preceding'],row['source_context']['following']),expected)
    def test_arbitrary_paths_prefixes_suffixes_and_changed_public_unit_never_attest(self):
        for raw in ["Removed '/private/"+D.PUBLIC_LITERAL+"'.", "prefix Removed '/etc/systemd/system/"+D.PUBLIC_LITERAL+"'.", "Removed '/etc/systemd/system/"+D.PUBLIC_LITERAL+"'. suffix", "Removed '/etc/systemd/system/serial-getty@ttyS1.service'.", "Removed '/etc/systemd/system/"+D.PUBLIC_LITERAL+".private.invalid'."]:
            row=self.row((raw+'\n').encode());self.assertEqual(row['source_context']['whole_record'],'unknown')
            self.assertNotIn('private',json.dumps(row));self.assertNotIn('operand_digest',row['source_context'])
    def test_complete_original_record_including_escapes_must_match(self):
        for raw in [b"\x1b[32mRemoved '/etc/systemd/system/serial-getty@ttyS0.service'.\x1b[0m\n",b"Removed '/etc/systemd/system/serial-getty@tty\x1b[31mS0.service'.\n"]:
            self.assertEqual(self.row(raw)['source_context']['whole_record'],'unknown')
    def test_unknown_matches_and_foreign_mapping_never_emit_neighbors(self):
        row=self.row(b'private-probe@tty0.service\n');self.assertEqual(row['source_context'],dict(whole_record='unknown',preceding='unknown',following='unknown',privacy_admitted=False,runtime_cause_proven=False))
        m=D.scanner();match=m.EXTERNAL_SENSITIVE.search(D.PUBLIC_LITERAL)
        for phase,original,bounds,removed in [('terminal-payload',None,None,None),('source-view',D.PUBLIC_LITERAL,[],[]),('foreign',D.PUBLIC_LITERAL,m.array('I'),m.array('I'))]:
            self.assertEqual(D.serial_source_context(m,match,phase,original,bounds,removed)['whole_record'],'unknown')
    def test_oversized_original_record_only_emits_closed_neighbors(self):
        row=self.row(('x'*8192+'/'+D.PUBLIC_LITERAL+'\n').encode());self.assertEqual(row['source_context']['whole_record'],'unknown');self.assertEqual(row['source_context']['preceding'],'ascii-slash')
    def test_whole_official_source_inputs_and_exact_format_statements(self):
        f=json.loads((HERE.parent/'tests/fixtures/serial-source-context-official-v259.json').read_bytes())
        self.assertEqual(f['peeled_commit'],'9ca433482f2281d71718718705ca8cd3bf562ad6')
        self.assertFalse(f['privacy_allowance']);self.assertFalse(f['runtime_source_version_proven']);self.assertFalse(f['actual_UART_context_observed'])
        for s in f['sources']:
            b=s['content'].encode();self.assertEqual(len(b),s['bytes']);self.assertEqual(hashlib.sha256(b).hexdigest(),s['sha256'])
        install=f['sources'][0]['content'];self.assertIn('return log_info("Removed \'%s\'.", change->path);',install);self.assertIn('return log_info("Unit %s is masked, ignoring.", change->path);',install)
    def test_partial_diagnostic_remains_original_rejected_and_unqualified(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix='source-context-owned-partial-') as t:
            root=Path(t)/'source';(root/'host').mkdir(parents=True);raw=b"Removed '/etc/systemd/system/serial-getty@ttyS0.service'.\n";(root/'host/serial.log').write_bytes(raw)
            out=Path(t)/'out';report=D.prepare(root,out,'idle');self.assertFalse((out/'host/serial.log').exists());self.assertEqual((root/'host/serial.log').read_bytes(),raw)
            self.assertFalse(report['release_acceptance']);self.assertFalse(report['image_qualified']);self.assertEqual(report['full_strict_screen'],'REJECTED')
            self.assertEqual(report['rejected_members'][0]['matches'][0]['source_context']['whole_record'],'official-install-unlink-etc-system-unit')
            D.scanner().external_text((out/'diagnostic-partial.json').read_bytes())
if __name__=='__main__':unittest.main(verbosity=2)
