import sys
import tomllib
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import gaming_setup as G
ROOT=Path(__file__).resolve().parents[2]
CAT={name:tomllib.loads((ROOT/'modules/drivers'/name/'module.toml').read_text()) for name in ('nvidia','nvidia-580xx')}


def gpu(vendor,device='0001'):
    return dict(vendor=vendor,device=device,kind='0300',driver='test')


class GamingTests(unittest.TestCase):
    def test_amd_and_intel_use_mesa_both_architectures(self):
        for vendor in ('1002','8086'):
            p=G.package_plan([gpu(vendor)],CAT)
            self.assertFalse(p['blocked'])
            self.assertIn('mesa-vulkan-drivers.i686',p['packages'])
            self.assertIn('vulkan-loader.x86_64',p['packages'])
            self.assertFalse(any('nvidia' in x for x in p['packages']))

    def test_nvidia_generation_matches_existing_installer_catalog(self):
        for device,driver in [('1e02','nvidia'),('1b80','nvidia-580xx')]:
            p=G.package_plan([gpu('10de',device)],CAT,secure_boot='disabled')
            self.assertIn('akmod-'+driver,p['packages'])
            self.assertIn('xorg-x11-drv-'+driver+'-libs.i686',p['packages'])
        self.assertTrue(G.package_plan([gpu('10de','1180')],CAT,secure_boot='disabled')['blocked'])

    def test_hybrid_keeps_both_drivers(self):
        p=G.package_plan([gpu('8086'),gpu('10de','1e02')],CAT,secure_boot='disabled')
        self.assertIn('mesa-vulkan-drivers.i686',p['packages'])
        self.assertIn('xorg-x11-drv-nvidia-libs.i686',p['packages'])
        self.assertTrue(any('Hybrid' in w for w in p['warnings']))

    def test_secure_boot_and_unknown_state_do_not_generate_keys(self):
        for state in ('enabled','unknown'):
            p=G.package_plan([gpu('10de','1e02')],CAT,secure_boot=state)
            self.assertTrue(p['blocked'])
            with self.assertRaises(ValueError): G.setup_argv(dict(repositories=True,**p))
        p=G.package_plan([gpu('10de','1e02')],CAT,installed=['akmod-nvidia'],secure_boot='enabled')
        self.assertFalse(p['blocked'])

    def test_freeworld_preserved_and_repositories_require_opt_in(self):
        p=G.package_plan([gpu('1002')],CAT,installed=['mesa-vulkan-drivers-freeworld'])
        self.assertIn('mesa-vulkan-drivers-freeworld.i686',p['packages'])
        self.assertNotIn('mesa-vulkan-drivers.i686',p['packages'])
        with self.assertRaises(ValueError): G.setup_argv(dict(repositories=False,**p))
        self.assertEqual(G.setup_argv(dict(repositories=True,**p))[:3],['pkexec','/usr/bin/dnf5','install'])
