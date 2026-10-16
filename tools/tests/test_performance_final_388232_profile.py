#!/usr/bin/env python3
"""Final 388232 static Mango profile remains fail closed pending runtime evidence."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[2]
EXECUTABLE_SHA256 = '84f13102da4271ab86dc652b2bf1835dc78ffb4a498f4fc7262567c4bc2ab266'
AUDIT = ROOT / 'tools/performance/mango-audits' / (EXECUTABLE_SHA256 + '.json')
AUDIT_SHA256 = 'e315f9341cf7a6d100fd9cec02276578ce7ef27c3f5e18bd2aa724bd7ec229c3'


def load(name, relative):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


causal = load('final_388232_causal', 'tools/performance/causal.py')
comparison = load('final_388232_compare', 'tools/performance/compare.py')


class Final388232MangoProfileControls(unittest.TestCase):
    def record(self):
        raw = AUDIT.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), AUDIT_SHA256)
        return json.loads(raw)

    def test_exact_final_image_and_safe_static_reader_are_bound(self):
        record = self.record()
        self.assertEqual(record['schema'], 'arctic-mango-native-profile-audit-v1')
        self.assertEqual(record['status'],
                         'candidate-specific-static-profile-admitted-pending-runtime')
        candidate = record['candidate']
        self.assertEqual((candidate['sha256'], candidate['bytes'], candidate['build_id']),
            (EXECUTABLE_SHA256, 530784,
             '7dd5c01049045b3af174f4d0e94292abaf0f274d'))
        self.assertEqual(candidate['rpm_nevra'],
            'mangowm-0.17.3-1.preview.38823208615.1.gitcfc39da.fc44.x86_64')
        provenance = record['provenance']
        self.assertEqual({key: provenance[key] for key in (
            'producer_run_id', 'producer_source_sha', 'producer_artifact_id',
            'producer_artifact_bytes', 'producer_artifact_sha256',
            'producer_receipt_sha256', 'iso_bytes', 'iso_sha256')}, {
            'producer_run_id': 38823208615,
            'producer_source_sha': 'cfc39dad61125e4fa8fb7906ac14f4c360b58228',
            'producer_artifact_id': 12016177474,
            'producer_artifact_bytes': 1936459062,
            'producer_artifact_sha256':
                '5f77dbf607abdada5ed140ae8635314554d5d2f03f88f1f5831e3d53bc18cf23',
            'producer_receipt_sha256':
                '82d102432819e8cc2f9d27b020f54a21021a176daa930e675c75229273ab7330',
            'iso_bytes': 1936271360,
            'iso_sha256':
                'c13c4589d7b522fec7dbd5eeafec00cf9088d8788cdfb6771a7382285846d7c7',
        })
        static = provenance['static_evidence']
        self.assertEqual((static['execution_run_id'], static['execution_sha'],
                          static['artifact_id'], static['artifact_archive_sha256'],
                          static['report_sha256']),
            (38829784760, 'ba382e06a497bb155a4894ed7f557e687fbdadad',
             12017031204,
             'c7747505bb335abf03152340b9822ecb9678892386cb36f58e982b847c089052',
             'e9dd0aad8785f414c61d1d561612297782cf4b96ba7c5a54929fbe0d9d24d8d1'))
        review = provenance['independent_review']
        self.assertEqual((review['reader_run_id'], review['reader_source_sha'],
                          review['safe_profile_sha256']),
            (38839175195, 'b517c83b76826a94e040ecc058c261447592da6b',
             '1f5b414ede1047bdbdd7031bcf54de5232917eab0f6d2c4a2e0cb688598c37cd'))
        self.assertTrue(review['mango_executable_sections_match_prior'])
        self.assertFalse(review['mango_whole_elf_matches_prior'])
        self.assertFalse(review['runtime_or_private_data_emitted'])

    def test_machine_code_getter_wlroots_and_abi_are_exact(self):
        record = self.record()
        sections = record['candidate']['executable_sections']
        self.assertEqual({name: (value['file_offset'], value['bytes'], value['sha256'])
                          for name, value in sections.items()}, {
            '.init': (828, 27, '62c9157c9ec8ca820ba15eb592f22fc166161cd2fa0d786eb624f17c846509a0'),
            '.plt': (864, 10224, '6088bc6143ac061f9a15139f023192636b12ad22126e3396c2f67e5d80e0b177'),
            '.plt.sec': (11088, 10208, '529a99044ee850380167cdcb79bb012bbfff537b6849a67dc9f8401c2bfdfcbc'),
            '.text': (21312, 375664, 'a39a19bcaeab7fd3b516d9a6ef4551e162604a500624a1cb4677ea6ea0cdf37f'),
            '.fini': (396976, 13, '6a4f3e5efc7c1f7ee7d6f21afd9ed040ba1d7f0b97bb12b016f5b176cc558bd8'),
        })
        mapping = record['mapping_function']
        self.assertEqual((mapping['file_offset'], mapping['bytes'], mapping['sha256']),
            (0x43110, 4109,
             '3955d4a7db3fac1b5f0f17833562299ab299b2250eb2a4a66e7ac390f2dcb9bc'))
        getter = record['original_appid_getter']
        self.assertEqual((getter['file_offset'], getter['bytes'], getter['sha256']),
            (0x6b00, 1234,
             '11c0701eafb910c98f526a26d1926077f94bd411c7739db7066b6ba0742f7ead'))
        self.assertEqual(record['abi']['offsets']['client_ext_foreign_toplevel'], 1584)
        self.assertEqual(record['abi']['offsets']['client_surface'], 328)
        wlroots = record['wlroots_runtime']
        self.assertEqual((wlroots['sha256'], wlroots['build_id']),
            ('a1223d6311c31c18a00e64169e869cce0a128457c0113701f68b65c0c6cb4147',
             '94f7586649c4560dce6eb8edbf12927dcd318e8c'))

    def test_one_symmetric_exact_profile_is_fail_closed(self):
        self.assertEqual(causal.MAPPING_PROFILES, comparison.MAPPING_PROFILES)
        profiles = [profile for profile in causal.MAPPING_PROFILES
                    if profile['executable_sha256'] == EXECUTABLE_SHA256]
        self.assertEqual(len(profiles), 1)
        profile = profiles[0]
        self.assertEqual(profile['native_audit_sha256'], AUDIT_SHA256)
        self.assertEqual(profile['lower_instruction_file_offsets'],
                         {'tail': 0x43619, 'head': 0x43773, 'scroller': 0x43da3})
        self.assertNotIn(dict(profile, executable_sha256='f' * 64), causal.MAPPING_PROFILES)

    def test_acceptance_and_precision_gates_are_unchanged(self):
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
        source = (ROOT / 'tools/performance/compare.py').read_text()
        self.assertIn('limit = min(.005, sample * .025)', source)
        self.assertIn("if set(runs) != {'baseline', 'candidate'} or any(len(group) != 3", source)
        self.assertIn("median['candidate'] > median['baseline'] * (1 + gate)", source)


if __name__ == '__main__':
    unittest.main()
