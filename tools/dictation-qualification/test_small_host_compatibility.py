"""The diagnosed optional host feature must not weaken the actual v2 ISA gate."""
import ast
from pathlib import Path
import unittest
from test_coherent_cpu_fixture import cpuinfo, FLOOR, guest

SHELL=Path(__file__).parents[1].joinpath('test-install.sh').read_text()
DRIVER=SHELL.split("DRIVER <<'PY' || true\n",1)[1].split('\nPY\n',1)[0]
FUNCTION=next(n for n in ast.parse(DRIVER).body if isinstance(n,ast.FunctionDef) and n.name=='dictation_cpu_argv')

class HostCompatibility(unittest.TestCase):
    def apply(self,profile,fixture='1'):
        env={'NATIVE_DICTATION_CPU_PROFILE':profile,'DICTATION_FIXTURE':fixture}
        scope={'E':env};module=ast.Module(body=[FUNCTION],type_ignores=[])
        exec(compile(ast.fix_missing_locations(module),'public-source-function','exec'),scope)
        original=['qemu-system-x86_64','-cpu','host','-smp','2']
        return original,scope['dictation_cpu_argv'](original)

    def test_only_small_fixture_masks_diagnosed_optional_feature_and_retains_enforcement(self):
        old,new=self.apply('small-v2')
        self.assertEqual(old,['qemu-system-x86_64','-cpu','host','-smp','2'])
        self.assertEqual(new,['qemu-system-x86_64','-cpu','Westmere-v2,-spec-ctrl,enforce','-smp','2'])
        self.assertIsNot(old,new)
        for profile in ('','turbo-q5-v3'):
            old,new=self.apply(profile);self.assertEqual(new,old)
        with self.assertRaises(RuntimeError):self.apply('small-v2','0')
        with self.assertRaises(RuntimeError):self.apply('unknown')

    def test_observed_floor_without_optional_feature_passes_but_missing_isa_or_avx_fails(self):
        self.assertIsNone(guest.verify_small_cpu_fixture(cpuinfo(flags=(FLOOR,FLOOR))))
        for flag in FLOOR.split():
            bad=' '.join(word for word in FLOOR.split() if word!=flag)
            with self.subTest(flag=flag),self.assertRaises(guest.Invalid):
                guest.verify_small_cpu_fixture(cpuinfo(flags=(FLOOR,bad)))
        with self.assertRaises(guest.Invalid):
            guest.verify_small_cpu_fixture(cpuinfo(flags=(FLOOR,FLOOR+' avx')))

if __name__=='__main__':unittest.main()
