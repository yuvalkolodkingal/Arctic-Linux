"""Observed per-vCPU compatibility controls; source-only, no QEMU or VM."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

SPEC=importlib.util.spec_from_file_location('coherent_cpu_guest',Path(__file__).with_name('guest_check.py'))
guest=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(guest)

# Independent x86-64-v1/v2 ABI feature fixture. Extra Linux mitigation flags
# are intentionally present; an exact model-name string is not accepted as proof.
FLOOR='fpu cx8 cmov mmx fxsr sse sse2 lm syscall pni ssse3 sse4_1 sse4_2 popcnt cx16 lahf_lm'
FLAGS=FLOOR+' nx pclmulqdq aes arat spec_ctrl pti'

def cpuinfo(flags=(FLAGS,FLAGS),processors=('0','1')):
    return '\n\n'.join('processor\t: '+pid+'\nmodel name\t: public-synthetic-cpu\nflags\t\t: '+value
                       for pid,value in zip(processors,flags)).encode()+b'\n\n'

class CpuControls(unittest.TestCase):
    def rejects(self,value):
        with self.assertRaises(guest.Invalid) as caught:guest.verify_small_cpu_fixture(value)
        self.assertEqual(BaseException.args.__get__(caught.exception),('actual-compatibility-cpu-fixture',))

    def test_all_two_vcpus_observed_floor_and_extra_mitigation_flags_are_accepted(self):
        self.assertIsNone(guest.verify_small_cpu_fixture(cpuinfo()))
        self.assertIsNone(guest.verify_small_cpu_fixture(cpuinfo(processors=('1','0'))))

    def test_canonical_digit_leading_linux_flag_preserves_floor_and_isa_controls(self):
        extra=FLAGS+' 3dnowprefetch'
        self.assertIsNone(guest.verify_small_cpu_fixture(cpuinfo(flags=(extra,extra))))
        self.rejects(cpuinfo(flags=(extra,extra+' avx512f')))
        self.rejects(cpuinfo(flags=(extra,' '.join(x for x in extra.split() if x!='sse4_2'))))
        for token in ('_private','3PRIVATE','3private-path','3private/path'):
            with self.subTest(token=token):self.rejects(cpuinfo(flags=(extra,extra+' '+token)))

    def test_floor_on_only_first_vcpu_cannot_supply_second_cpu_evidence(self):
        for token in FLOOR.split():
            with self.subTest(token=token):self.rejects(cpuinfo(flags=(FLAGS,' '.join(x for x in FLAGS.split() if x!=token))))

    def test_high_isa_on_either_cpu_is_rejected_even_if_other_cpu_compatible(self):
        for token in ('avx','avx2','avx512f','avx512bw','avx10','avx10_512','avx_vnni','fma','f16c',
                      'bmi1','bmi2','xsave','xsaveopt','xsavec','xsaves','osxsave','amx_tile','apx_f'):
            for at in (0,1):
                with self.subTest(token=token,cpu=at):
                    values=[FLAGS,FLAGS];values[at]+=' '+token;self.rejects(cpuinfo(flags=values))

    def test_missing_duplicate_or_ambiguous_processor_and_flags_fail_closed(self):
        variants=(cpuinfo(flags=(FLAGS,),processors=('0',)),cpuinfo(flags=(FLAGS,FLAGS,FLAGS),processors=('0','1','2')),
                  cpuinfo(processors=('0','0')),cpuinfo(processors=('0','2')),cpuinfo(processors=('00','1')),
                  cpuinfo().replace(b'processor\t: 0\n',b''),cpuinfo().replace(b'processor\t: 0\n',b'processor: 0\nprocessor: 0\n'),
                  cpuinfo().replace(b'flags\t\t: '+FLAGS.encode(),b'flags: ',1),
                  cpuinfo().replace(b'flags\t\t: ',b'flags: '+FLAGS.encode()+b'\nflags: ',1),
                  cpuinfo().replace(b'flags\t\t: '+FLAGS.encode(),b'',1),cpuinfo(flags=(FLAGS+' fpu',FLAGS)))
        for value in variants:
            with self.subTest(value_sha=guest.hashlib.sha256(value).hexdigest()):self.rejects(value)

    def test_bounded_ascii_flags_strict_bytes_and_unknown_private_values_never_export(self):
        class Private:
            def __str__(self):raise AssertionError('private conversion')
            def __repr__(self):raise AssertionError('private conversion')
        class PrivateBytes(bytes):
            def decode(self,*args,**kwargs):raise AssertionError('private conversion')
        for value in (Private(),PrivateBytes(cpuinfo()),None,'private-transcript',b'',b'x'*(1024*1024+1),
                      cpuinfo()+b'\xff',cpuinfo(flags=(FLAGS+' PRIVATE-PATH',FLAGS)),
                      cpuinfo(flags=(FLAGS+' '+'a'*65,FLAGS)),
                      cpuinfo(flags=(FLAGS+' '+ ' '.join('f'+str(i) for i in range(513)),FLAGS))):
            self.rejects(value)

    def test_constructor_rejects_bad_cpu_before_profile_application_or_desktop_gates(self):
        controller=Mock(desired_profile=Mock(return_value={'id':'small-v2'}))
        with patch.object(guest,'installed_controller',return_value=controller),patch.object(guest.Path,'read_bytes',return_value=cpuinfo(flags=(FLAGS,FLAGS+' avx512f'))),patch.object(guest,'desktop') as desktop,patch.object(guest,'gates') as gates:
            with self.assertRaises(guest.Invalid):guest.Checker({'hardware_profile':'small-v2'})
        controller.profile_selection.assert_not_called();controller.recommended_profile.assert_not_called()
        desktop.assert_not_called();gates.assert_not_called()

    def test_good_cpu_reaches_original_profile_guard_while_turbo_skips_small_fixture(self):
        class OriginalProfileGuardReached(Exception):pass
        for profile,observed in (('small-v2',cpuinfo()),('turbo-q5-v3',b'not-a-Small-fixture')):
            controller=Mock(desired_profile=Mock(return_value={'id':profile}),
                            profile_selection=Mock(side_effect=OriginalProfileGuardReached))
            with patch.object(guest,'installed_controller',return_value=controller),patch.object(guest.Path,'read_bytes',return_value=observed):
                with self.assertRaises(OriginalProfileGuardReached):guest.Checker({'hardware_profile':profile})
            controller.profile_selection.assert_called_once_with()

    def test_complete_source_rollback_preserves_original_schema_gates_and_budgets(self):
        text=Path(guest.__file__).read_text()
        from test_status_protocol import restore_status_protocol
        text=restore_status_protocol(text)
        start=text.index('\ndef verify_small_cpu_fixture(')
        end=text.index('\ndef authenticated_capture_nodes(',start)
        restored=(text[:start]+text[end:]).replace(
            "        if self.profile_id == 'small-v2':\n            verify_small_cpu_fixture(cpuinfo)\n",'')
        self.assertEqual(guest.hashlib.sha256(restored.encode()).hexdigest(),
                         'efba7e5e6483f3b75a9f27f8baf7fd6d42edddc65d3df96419cf4e8517a6ae0d')

if __name__=='__main__':unittest.main()
