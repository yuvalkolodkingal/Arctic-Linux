"""Actual rejected Match controls; no private original UART or runtime cause."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tracemalloc
import unittest
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('integrated_serial_fragment_actual',HERE/'screen-diagnostic.py')
D=importlib.util.module_from_spec(spec);spec.loader.exec_module(D)

class SerialSourceFragment(unittest.TestCase):
    def observe(self,raw):
        m=D.scanner();passed,reason,rows=D.screened_text(m,raw)
        self.assertFalse(passed);self.assertEqual(reason,'sensitive-text');self.assertTrue(rows)
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(RuntimeError,'^Sensitive text in external evidence$'):m.external_text(raw)
        return rows[0]
    def test_exact_same_rejected_literal_and_slash_fragment_observation_only(self):
        for raw in (b'serial-getty@ttyS0.service\n',b'/serial-getty@ttyS0.service\n',b'\x1b[32m/serial-getty@ttyS0.service\x1b[0m\n'):
            row=self.observe(raw);self.assertEqual(row['known_source_fragment'],'serial-getty-ttyS0-source-fragment')
            self.assertTrue(row['original_contiguous'])
        row=self.observe(b'/serial-getty@ttyS0.service\n')
        self.assertFalse(row['delimiter_bounded']);self.assertEqual(row['public_candidate'],'unknown');self.assertIsNone(row['public_candidate_sha256'])
    def test_other_exact_lengths_embedded_and_contiguity_breaks_unknown(self):
        for raw in (b'serial-getty@ttyS1.service\n',b'private-probe@tty0.service\n',b'serial-getty@ttyS0.service.private.invalid\n',b'private-serial-getty@ttyS0.service\n',b'serial-getty@tty\x1b[31mS0.service\n',b'serial-getty@tty\x1b[1CS0.service\n'):
            row=self.observe(raw);self.assertEqual(row['known_source_fragment'],'unknown')
            self.assertNotIn('private-probe',json.dumps(row))
    def test_terminal_or_foreign_mapping_and_phase_cannot_attest(self):
        m=D.scanner();match=m.EXTERNAL_SENSITIVE.search(D.PUBLIC_LITERAL);empty=m.array('I')
        for phase,original,bounds,removed in [('terminal-payload',None,None,None),('foreign',D.PUBLIC_LITERAL,empty,empty),('source-view','x'*26,empty,empty),('source-view',D.PUBLIC_LITERAL,[],[]),('source-view',D.PUBLIC_LITERAL,m.array('I',[1]),empty)]:
            row=D.serial_source_fragment(m,match,phase,original,bounds,removed)
            self.assertEqual(row['candidate'],'unknown');self.assertFalse(row['privacy_admitted']);self.assertIsNone(row['operand_digest'])
    def test_long_real_scanner_match_returns_before_operand_allocation(self):
        m=D.scanner();text='https://public.invalid/?'+'x'*262144+'\n';match=m.EXTERNAL_SENSITIVE.search(text)
        self.assertGreater(match.end()-match.start(),262000)
        tracemalloc.start();result=D.serial_source_fragment(m,match,'source-view',text,m.array('I'),m.array('I'));_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        self.assertEqual(result['candidate'],'unknown');self.assertLess(peak,8192)
    def test_exact_original_scanner_hash_and_all_other_helper_bytes_rollback(self):
        source=(HERE/'screen-diagnostic.py').read_text();start=source.index('PUBLIC_LITERAL =');end=source.index('def classify_match(',start);source=source[:start]+source[end:]
        source=source.replace("public_candidate='unknown', public_candidate_sha256=None,\n        known_source_fragment='unknown')","public_candidate='unknown', public_candidate_sha256=None)",1)
        source=source.replace("    fragment = serial_source_fragment(m, match, phase, original, boundaries, removed)\n    result['known_source_fragment'] = fragment['candidate']\n",'',1)
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),'94ce0fb0ca86ad83fb37c6c5867cae840dffd8569196260d290e8db3911649f2')
        self.assertEqual(hashlib.sha256((HERE.parent/'native-functional/screen-evidence.py').read_bytes()).hexdigest(),D.SCANNER_SHA256)
    def test_partial_diagnostic_still_omits_rejected_UART_and_stays_unqualified(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix='arctic-serial-fragment-owned-') as temporary:
            source=Path(temporary)/'source';(source/'host').mkdir(parents=True);uart=source/'host/serial.log';raw=b'/serial-getty@ttyS0.service\n';uart.write_bytes(raw)
            out=Path(temporary)/'out';report=D.prepare(source,out,'idle')
            self.assertFalse(report['release_acceptance']);self.assertFalse(report['image_qualified']);self.assertFalse((out/'host/serial.log').exists());self.assertEqual(uart.read_bytes(),raw)
            self.assertEqual(report['rejected_members'][0]['matches'][0]['known_source_fragment'],'serial-getty-ttyS0-source-fragment')
            D.scanner().external_text((out/'diagnostic-partial.json').read_bytes())
if __name__=='__main__':unittest.main(verbosity=2)
