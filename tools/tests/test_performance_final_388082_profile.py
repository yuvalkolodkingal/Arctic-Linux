#!/usr/bin/env python3
"""Exact 388082 static Mango profile remains fail closed pending runtime evidence."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[2]
EXECUTABLE_SHA256 = '6c2bc9fe4191a55f3214b1206a1aa878c01987fa621cd877aa87f9964ca5d37f'
AUDIT = ROOT / 'tools/performance/mango-audits' / (EXECUTABLE_SHA256 + '.json')
AUDIT_SHA256 = '415020b8bf8354fb031838cb30c842f4b49a788a4c840774cd82dc65e727b247'

def load(name, relative):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

causal = load('final_388082_causal', 'tools/performance/causal.py')
comparison = load('final_388082_compare', 'tools/performance/compare.py')

class Final388082MangoProfileControls(unittest.TestCase):
    def record(self):
        raw = AUDIT.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), AUDIT_SHA256)
        return json.loads(raw)

    def test_exact_image_artifact_and_static_report_are_bound(self):
        record = self.record()
        self.assertEqual(record['schema'], 'arctic-mango-native-profile-audit-v1')
        self.assertEqual(record['status'],
                         'candidate-specific-static-profile-admitted-pending-runtime')
        candidate = record['candidate']
        self.assertEqual((candidate['sha256'], candidate['bytes'], candidate['build_id']),
            (EXECUTABLE_SHA256, 530784,
             '4d5d87f7777d29548573e5f222fa0efeaf0f274d'))
        self.assertEqual(candidate['rpm_nevra'],
            'mangowm-0.17.3-1.preview.38808271154.1.git10b94bf.fc44.x86_64')
        provenance = record['provenance']
        self.assertEqual({key: provenance[key] for key in (
            'producer_run_id', 'producer_run_attempt', 'producer_source_sha',
            'producer_artifact_id', 'producer_artifact_bytes', 'producer_artifact_sha256',
            'producer_receipt_sha256', 'iso_bytes', 'iso_sha256')}, {
            'producer_run_id': 38808271154,
            'producer_run_attempt': 1,
            'producer_source_sha': '10b94bf1f6aef4950889d4a498c9e1138cf7973d',
            'producer_artifact_id': 12011000602,
            'producer_artifact_bytes': 1936516406,
            'producer_artifact_sha256':
                '4abe1d00b7b48ff1b16609e8e24e3adb440409cd0186dee2482fff1dbb566db6',
            'producer_receipt_sha256':
                '85fe05d5394253cfb96e8c5fc38054171218a9e93c17c318670040d76be5c6c6',
            'iso_bytes': 1936328704,
            'iso_sha256':
                '304ae134793773f7a4d58ebe4dc4a5428a49754f474749d0d0a025032da70b23',
        })
        self.assertEqual(provenance['root_filesystem_sha256'],
                         '83645730759973c44606394084d95fa6e13a9089e7d0b6d6c966b81aa98983d9')
        static = provenance['static_evidence']
        self.assertEqual((static['execution_run_id'], static['execution_sha'],
                          static['artifact_id'], static['artifact_archive_sha256'],
                          static['report_sha256']),
            (38816249906, '28e8cc72a7ea9440b384bd76cc19c7cf6f32aeab',
             12010344440,
             'e0cccf6db2962293f4268dca3a43bfa146c3e9bf582694547648fcb8fe02c107',
             '9b0a4735c6b42b4ec9717b155d7223cec7b9875a5e4eb09b0d39261a9de85d88'))
        self.assertIs(static['observer_profile_admitted'], False)
        self.assertIs(static['performance_acceptance'], False)
        self.assertIs(static['release_acceptance'], False)

    def test_whole_elf_executable_sections_slices_sources_and_wlroots_are_exact(self):
        record = self.record()
        self.assertEqual(record['candidate']['executable_sections'], {
            '.init': {'address': 828, 'allocated': True, 'bytes': 27,
                'executable': True, 'file_offset': 828, 'flags': 6,
                'sha256': '62c9157c9ec8ca820ba15eb592f22fc166161cd2fa0d786eb624f17c846509a0'},
            '.plt': {'address': 864, 'allocated': True, 'bytes': 10224,
                'executable': True, 'file_offset': 864, 'flags': 6,
                'sha256': '6088bc6143ac061f9a15139f023192636b12ad22126e3396c2f67e5d80e0b177'},
            '.plt.sec': {'address': 11088, 'allocated': True, 'bytes': 10208,
                'executable': True, 'file_offset': 11088, 'flags': 6,
                'sha256': '529a99044ee850380167cdcb79bb012bbfff537b6849a67dc9f8401c2bfdfcbc'},
            '.text': {'address': 21312, 'allocated': True, 'bytes': 375664,
                'executable': True, 'file_offset': 21312, 'flags': 6,
                'sha256': 'a39a19bcaeab7fd3b516d9a6ef4551e162604a500624a1cb4677ea6ea0cdf37f'},
            '.fini': {'address': 396976, 'allocated': True, 'bytes': 13,
                'executable': True, 'file_offset': 396976, 'flags': 6,
                'sha256': '6a4f3e5efc7c1f7ee7d6f21afd9ed040ba1d7f0b97bb12b016f5b176cc558bd8'},
        })
        mapping = record['mapping_function']
        self.assertEqual((mapping['file_offset'], mapping['bytes'], mapping['sha256']),
            (0x43110, 4109,
             '3955d4a7db3fac1b5f0f17833562299ab299b2250eb2a4a66e7ac390f2dcb9bc'))
        getter = record['original_appid_getter']
        self.assertEqual((getter['file_offset'], getter['bytes'], getter['sha256']),
            (0x6b00, 1234,
             '11c0701eafb910c98f526a26d1926077f94bd411c7739db7066b6ba0742f7ead'))
        wlroots = record['wlroots_runtime']
        self.assertEqual((wlroots['sha256'], wlroots['build_id'], wlroots['text']['sha256']),
            ('a1223d6311c31c18a00e64169e869cce0a128457c0113701f68b65c0c6cb4147',
             '94f7586649c4560dce6eb8edbf12927dcd318e8c',
             '813e4f046ee3678bcdec53b9295124866155dc13cf728589bcdb4ac2f815306b'))
        source = record['provenance']['producer_source']
        self.assertEqual(source['tree'], '0427047ce4dc65d31e2826f4f1efffa7bb453b0a')
        self.assertEqual(len(source['files']), 7)
        self.assertEqual(source['files']['packaging/mangowm.spec']['sha256'],
                         'f9bc844457bc4d37a1a2456da12695b4120b6e82a53841472ed254732c322212')

    def test_one_exact_profile_is_identical_and_fails_closed(self):
        self.assertEqual(causal.MAPPING_PROFILES, comparison.MAPPING_PROFILES)
        profiles = [profile for profile in causal.MAPPING_PROFILES
                    if profile['executable_sha256'] == EXECUTABLE_SHA256]
        self.assertEqual(len(profiles), 1)
        profile = profiles[0]
        self.assertEqual(profile['native_audit_sha256'], AUDIT_SHA256)
        self.assertEqual(profile['lower_instruction_file_offsets'],
                         {'tail': 0x43619, 'head': 0x43773, 'scroller': 0x43da3})
        self.assertNotIn(dict(profile, executable_sha256='f' * 64),
                         causal.MAPPING_PROFILES)
        mutated = bytearray(AUDIT.read_bytes())
        mutated[-2] ^= 1
        self.assertNotEqual(hashlib.sha256(mutated).hexdigest(), AUDIT_SHA256)

    def test_runtime_acceptance_remains_unclaimed_and_gates_unchanged(self):
        record = self.record()
        self.assertEqual(record['acceptance'], {
            'performance_acceptance': False, 'release_acceptance': False,
            'runtime_profile_admitted': False, 'static_profile_admitted': True})
        gates = record['contracts']['acceptance_gates']
        self.assertEqual(gates['application_regression_percent'], 10)
        self.assertEqual(gates['precision'],
                         'interval <= min(0.005 seconds, observed * 0.025)')
        self.assertTrue(gates['exactly_six_boots_required'])
        self.assertTrue(gates['zero_event_loss_required'])
        self.assertFalse(gates['samples_dropped'])
        manifest = json.loads((ROOT / 'tools/performance/execution-manifest.json').read_text())
        self.assertIs(manifest['ready'], False)
        self.assertIsNone(manifest['image'])
        self.assertEqual(manifest['execution_files'], {})
        self.assertEqual(manifest['observer'], {})
        self.assertIs(manifest['release_acceptance'], False)
        self.assertFalse((ROOT / '.github/qualification-20261010.performance').exists())
        source = (ROOT / 'tools/performance/compare.py').read_text()
        self.assertIn('limit = min(.005, sample * .025)', source)
        self.assertIn("if set(runs) != {'baseline', 'candidate'} or any(len(group) != 3", source)
        self.assertIn("median['candidate'] > median['baseline'] * (1 + gate)", source)

if __name__ == '__main__':
    unittest.main()
