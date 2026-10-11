"""Actual pinned Source functions, synthetic strings only; no original input."""
import contextlib,hashlib,io,json,sys,types,unittest
from pathlib import Path
from unittest import mock
HERE=Path(__file__).resolve().parent
PUBLIC=Path('/tmp/arctic-root-bios-format-public-20261011/actual-public-execution')
def load(path,name):
    raw=path.read_bytes();m=types.ModuleType(name);m.__file__=str(path)
    exec(compile(raw,str(path),'exec'),m.__dict__);return m,raw

def modules():
    o,oraw=load(HERE/'observer.py','shape_owned_observer')
    h,hraw=load(HERE/'match-diagnostic.py','shape_owned_helper')
    p=PUBLIC/'tools/final-bios-format-compatible-install/scanner.py'
    s,sraw=load(p,'shape_original_scanner')
    assert hashlib.sha256(sraw).hexdigest()=='b3d56536397ff1c46caf082b97a070ff3eae383c2c277898c572cb34eb76f336'
    c,craw=load(PUBLIC/'tools/final-bios-install/common.py','shape_original_common')
    so=o.OwnedSource(s.__dict__,sraw,str(p),'original-scanner')
    co=o.OwnedSource(c.__dict__,craw,c.__file__,'bios-common')
    ho=o.OwnedSource(h.__dict__,hraw,h.__file__,'match-diagnostic')
    vocabulary=frozenset({n.value for n in o.ast.walk(o.ast.parse(hraw))if isinstance(n,o.ast.Constant)and type(n.value)is str}
        |{'external-rule-'+format(n,'03d')for n in range(1,11)})
    return o,h,s,co,so,ho,vocabulary

def capture(s,text):
    with contextlib.redirect_stdout(io.StringIO()):
        try:s.external_text(text.encode('utf-8'))
        except RuntimeError as error:return error
    raise AssertionError('Actual strict scanner unexpectedly admitted synthetic rejected evidence')

def observe(text,mutate=None):
    o,h,s,co,so,ho,vocabulary=modules();error=capture(s,text)
    if mutate:mutate(o,h,s,co,so,ho,error)
    value=o.describe(error,(),co,[(s,so)],h,ho,vocabulary,())
    return value,error,(o,h,s,co,so,ho,vocabulary)

def frame(unit='user-runtime-dir@1000.service',comm='(agetty)',**changes):
    d=dict(start='a'*32,user='root',hostname='arctic-ci',machineid='b'*32,bootid='c'*32,
        pid='123',pidfdid='456',comm=comm,servicename=unit,invocationid='d'*32,type='service')
    d.update(changes)
    return '\x1b]3008;'+ ';'.join(k+'='+v for k,v in d.items())+'\x1b\\'

def shape(value):return value['same_rejected_match']['public_source_shape']

class Controls(unittest.TestCase):
    def test_actual_same_raising_source_and_exact_known_unit(self):
        value,error,_=observe(' user-runtime-dir@1000.service ')
        row=shape(value)
        self.assertEqual(row['canonical_unit_id'],'unit-008')
        self.assertTrue(row['same_source_match_aligned']);self.assertTrue(row['match_original_contiguous'])
        self.assertFalse(row['osc3008_complete_bounded_frame'])
        self.assertEqual(value['original_source_site']['function'],'reject_sensitive_match')
        self.assertEqual(value['original_source_site']['source_line'],139)
        self.assertEqual(error.args,('Sensitive text in external evidence',))
        self.assertFalse(row['privacy_admitted']);self.assertFalse(row['runtime_cause_proven'])
    def test_complete_known_service_frame_is_observed_but_rejected(self):
        value,error,_=observe(frame())
        row=shape(value)
        for key in ('same_source_match_aligned','match_original_contiguous','osc3008_prefix_near_match',
                    'osc3008_complete_bounded_frame','match_within_osc3008_frame','source_field_keys_known_unique',
                    'source_optional_field_order','required_source_fields_present','match_equals_servicename_field',
                    'start_id_hex32','machine_id_hex32','boot_id_hex32','invocation_id_hex32',
                    'pid_canonical_in_range','pidfdid_canonical_in_range','user_root_exact',
                    'hostname_known_public','comm_agetty_exact','type_service_exact'):
            self.assertTrue(row[key],key)
        self.assertEqual(row['canonical_unit_id'],'unit-008')
        self.assertFalse(row['current_scanner_service_schema'])
        self.assertIs(type(error),RuntimeError)
    def test_unknown_unit_and_comm_never_escape_as_values(self):
        value,_,_=observe(frame(unit='private-service@private.example',comm='private process argument'))
        row=shape(value)
        self.assertEqual(row['canonical_unit_id'],'unknown')
        self.assertTrue(row['match_equals_servicename_field']);self.assertFalse(row['comm_agetty_exact'])
        raw=json.dumps(value)
        for forbidden in ('private-service','private.example','private process','codepoints','operand_sha256'):
            self.assertNotIn(forbidden,raw)
    def test_lookalike_case_affix_and_sgr_split_remain_unknown(self):
        for text in (' User-runtime-dir@1000.service ',' prefixuser-runtime-dir@1000.service ',
                     ' user-runtime-dir@1000.serviceSuffix ',
                     ' user-runtime-\x1b[31mdir@1000.service '):
            value,_,_=observe(text)
            self.assertEqual(shape(value)['canonical_unit_id'],'unknown',repr(text))
        value,_,_=observe(' user-runtime-\x1b[31mdir@1000.service ')
        self.assertFalse(shape(value)['match_original_contiguous'])
    def test_incomplete_and_oversize_osc_cannot_attest_complete_frame(self):
        for text in (frame()[:-2],frame().replace('comm=(agetty)','comm='+'x'*513)):
            value,_,_=observe(text)
            row=shape(value)
            self.assertFalse(row['osc3008_complete_bounded_frame'])
    def test_duplicate_foreign_key_order_and_numeric_boundaries(self):
        for text in (frame().replace(';type=service',';comm=(agetty);type=service'),
                     frame().replace(';type=service',';foreign=private;type=service')):
            value,_,_=observe(text);self.assertFalse(shape(value)['source_field_keys_known_unique'])
        value,_,_=observe(frame().replace(';user=root;hostname=arctic-ci',';hostname=arctic-ci;user=root'))
        self.assertFalse(shape(value)['source_optional_field_order'])
        for changes,key in (({'pid':'2147483648'},'pid_canonical_in_range'),
                            ({'pid':'01'},'pid_canonical_in_range'),
                            ({'pidfdid':'18446744073709551616'},'pidfdid_canonical_in_range'),
                            ({'start':'A'*32},'start_id_hex32')):
            value,_,_=observe(frame(**changes));self.assertFalse(shape(value)[key])
    def test_match_in_other_field_and_prior_frame_has_no_service_join(self):
        value,_,_=observe(frame(unit='public',comm='user-runtime-dir@1000.service'))
        self.assertFalse(shape(value)['match_equals_servicename_field'])
        value,_,_=observe(frame(unit='public')+' user-runtime-dir@1000.service ')
        self.assertFalse(shape(value)['match_within_osc3008_frame'])
    def test_foreign_code_globals_and_table_mutation_cannot_project(self):
        for mutate in (
            lambda o,h,s,*rest:setattr(s.reject_sensitive_match,'__code__',s.reject_sensitive_match.__code__.replace()),
            lambda o,h,s,*rest:setattr(h,'DIAGNOSTIC_PUBLIC_UNITS',tuple(list(h.DIAGNOSTIC_PUBLIC_UNITS))),
            lambda o,h,s,*rest:setattr(s,'EXTERNAL_EMAIL_CANDIDATES',(('private@private.service','unit-008'),)),
            lambda o,h,s,*rest:setattr(s,'OSC3008_SERVICE',s.re.compile('.*'))):
            value,error,_=observe(' user-runtime-dir@1000.service ',mutate)
            self.assertIsNone(value);self.assertIs(type(error),RuntimeError)
    def test_alignment_denies_foreign_regex_window_and_map(self):
        _,h,s,_,_,_,_=modules();text=' user-runtime-dir@1000.service '
        view,bounds,removed=s.classification_view(text);actual=s.EXTERNAL_SENSITIVE.search(view)
        foreign=s.re.compile(s.EXTERNAL_SENSITIVE.pattern,s.EXTERNAL_SENSITIVE.flags).search(view)
        # re.compile may return the cached same object; force a distinct object.
        s.re.purge();foreign=s.re.compile(s.EXTERNAL_SENSITIVE.pattern,s.EXTERNAL_SENSITIVE.flags).search(view)
        for match,original,b,r in ((foreign,text,bounds,removed),
                (s.EXTERNAL_SENSITIVE.search(view,1),text,bounds,removed),
                (actual,'X'+text,bounds,removed)):
            row=h.diagnostic_public_source_shape(s,match,'source-view',original,b,r)
            self.assertFalse(row['same_source_match_aligned']);self.assertEqual(row['canonical_unit_id'],'unknown')
    def test_canonical_prefix_with_numeric_right_affix_stays_unknown(self):
        value,_,_=observe(' user-runtime-dir@1000.service7 ')
        self.assertEqual(value['same_rejected_match']['candidate_reason'],'match-delimiter-differs')
        self.assertEqual(shape(value)['canonical_unit_id'],'unknown')
    def test_canonical_prefix_with_underscore_right_affix_stays_unknown(self):
        value,_,_=observe(' user-runtime-dir@1000.service_suffix ')
        self.assertEqual(value['same_rejected_match']['candidate_reason'],'match-delimiter-differs')
        self.assertEqual(shape(value)['canonical_unit_id'],'unknown')
    def test_canonical_prefix_with_unicode_right_affix_stays_unknown(self):
        value,_,_=observe(' user-runtime-dir@1000.serviceא ')
        self.assertEqual(value['same_rejected_match']['candidate_reason'],'match-delimiter-differs')
        self.assertEqual(shape(value)['canonical_unit_id'],'unknown')
    def test_canonical_id_requires_entire_bounded_osc_servicename(self):
        value,_,_=observe(frame(unit='user-runtime-dir@1000.service7'))
        self.assertFalse(shape(value)['match_equals_servicename_field'])
        self.assertEqual(shape(value)['canonical_unit_id'],'unknown')
        value,_,_=observe(frame())
        self.assertTrue(shape(value)['match_equals_servicename_field'])
        self.assertEqual(shape(value)['canonical_unit_id'],'unit-008')
    def test_optional_shape_failure_preserves_original_exception_in_attach(self):
        o,h,s,co,so,ho,vocabulary=modules();original=[]
        # This is an explicit Source-only dependency fixture. Original execute
        # and publication do not run; attach retains the original entry Code.
        raw=b"def original_evidence(vm,context,guest_sha):\n    raise captured_error\ndef publish(out,files):\n    return files\ndef entry(vm,context,guest_sha):\n    return original_evidence(vm,context,guest_sha)\n"
        fixture=types.ModuleType('synthetic_attach_dependencies')
        fixture.__file__=str(HERE/'synthetic_attach_fixture.py')
        common=types.ModuleType('synthetic_common_container')
        common.__dict__.update(co.namespace)
        captured=capture(s,frame());original.append(captured)
        fixture.__dict__.update(C=common,captured_error=captured)
        exec(compile(raw,fixture.__file__,'exec'),fixture.__dict__)
        observed,state=o.attach(fixture.entry,raw,(PUBLIC/'tools/final-bios-install/common.py').read_bytes(),
            (PUBLIC/'tools/final-bios-format-compatible-install/scanner.py').read_bytes(),
            (HERE/'match-diagnostic.py').read_bytes(),HERE/'match-diagnostic.py')
        with mock.patch.object(o,'describe',side_effect=OSError('Synthetic optional failure')):
            with self.assertRaises(RuntimeError)as caught:observed(None,{},None)
        self.assertIs(caught.exception,original[0]);self.assertIsNone(state['finite'])

if __name__=='__main__':unittest.main(verbosity=2)
