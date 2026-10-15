#!/usr/bin/env python3
"""Static observer profile for producer 38684683083; runtime acceptance remains pending."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[2]
EXECUTABLE_SHA256 = '0d5fec706197207d735c0c5f640d049f334e1ea495f0005bcedfb27911afc51e'
AUDIT = ROOT / 'tools/performance/mango-audits' / (EXECUTABLE_SHA256 + '.json')
AUDIT_SHA256 = '26c5b33251d2cfcf242d39762ca98ab70e3995062a2cb58c41729c6a2e121a04'


def load(name, relative):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


causal = load('release_image_causal', 'tools/performance/causal.py')
comparison = load('release_image_compare', 'tools/performance/compare.py')


class ReleaseImageMangoProfileControls(unittest.TestCase):
    def record(self):
        raw = AUDIT.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), AUDIT_SHA256)
        return json.loads(raw)

    def test_exact_producer_image_and_static_artifact_are_closed(self):
        record = self.record()
        self.assertEqual(record['schema'], 'arctic-mango-native-profile-audit-v1')
        self.assertEqual(record['status'],
                         'candidate-specific-static-profile-admitted-pending-runtime')
        self.assertEqual(record['candidate'], {
            'build_id': '1e1f8b3767e99f77dbfe7a0e008f596daf0f274d',
            'bytes': 530784,
            'elf_class': 'ELF64',
            'executable_pt_load': {'file_bytes': 396989, 'file_offset': 0,
                'flags': 'R E', 'memory_bytes': 396989, 'virtual_address': 0},
            'machine': 'x86_64',
            'path': '/usr/bin/mango',
            'rpm_nevra': 'mangowm-0.17.3-1.preview.38684683083.1.git3152dbf.fc44.x86_64',
            'rpmdb_file_digest_verified': True,
            'sha256': EXECUTABLE_SHA256,
            'text': {'bytes': 375664, 'file_offset': 21312,
                'sha256': 'a39a19bcaeab7fd3b516d9a6ef4551e162604a500624a1cb4677ea6ea0cdf37f'},
        })
        provenance = record['provenance']
        self.assertEqual({key: provenance[key] for key in (
            'producer_run_id', 'producer_run_attempt', 'producer_source_sha',
            'producer_artifact_id', 'producer_artifact_bytes', 'producer_artifact_sha256',
            'producer_receipt_sha256', 'iso_bytes', 'iso_sha256')}, {
            'producer_run_id': 38684683083,
            'producer_run_attempt': 1,
            'producer_source_sha': '3152dbfd7a1844117dfb15aa8dd160bb811e8b54',
            'producer_artifact_id': 11951877248,
            'producer_artifact_bytes': 1936360758,
            'producer_artifact_sha256':
                'b632e49c06a6b2ac04b0ba1899aea7e5db0523799d51b0205cb6646683338182',
            'producer_receipt_sha256':
                '73ebd64e72fe5ec39e705a517104f9970e36b0007379a35ebe40e718c83a3c59',
            'iso_bytes': 1936173056,
            'iso_sha256':
                '55ecbc54c12b0445c354d5c00aaab2ca97deee289003b65fc0da24f4a31a09a4',
        })
        self.assertEqual({key: provenance[key] for key in (
            'static_run_id', 'static_run_attempt', 'static_execution_sha',
            'static_parent_sha', 'static_artifact_id', 'static_artifact_bytes',
            'static_artifact_sha256', 'static_report_sha256',
            'static_execution_manifest_sha256')}, {
            'static_run_id': 38690632439,
            'static_run_attempt': 1,
            'static_execution_sha': 'cb9e5dc5159339b58b8506ec4d257367e61b4b0e',
            'static_parent_sha': '9376204abfcfa06eac58e14b9e5838af475fc724',
            'static_artifact_id': 11951454279,
            'static_artifact_bytes': 3731640,
            'static_artifact_sha256':
                '93c46c5950e5bf97837ae2093f98b07c711cd9df91f0ff3fba8ceb542ab3153e',
            'static_report_sha256':
                '37893518dbb49f9b2e44c71869b1fcfc37aca7b05299ee3938fa9c97bd612160',
            'static_execution_manifest_sha256':
                'b0a8e90b9ef644f47e7c5944b93d3fea07679a0e6bdabfbc936285d6daa27165',
        })

    def test_machine_code_cfg_role_getter_and_abi_are_exact(self):
        record = self.record()
        mapping = record['mapping_function']
        self.assertEqual((mapping['file_offset'], mapping['bytes'], mapping['sha256'],
                          mapping['instruction_count'], mapping['artifact_excerpt_sha256']),
            (0x43110, 4109,
             '3955d4a7db3fac1b5f0f17833562299ab299b2250eb2a4a66e7ac390f2dcb9bc',
             796, 'b465bc2156bbc5c83429bbda9212a01dcf1323a0c14125b844c6d0791702fb50'))
        self.assertEqual(mapping['insertion_sites'], {
            'common_post': {'file_offset': 0x4361e, 'instruction_bytes': '488d3d33bd0300',
                'post_insert_call_bytes': 'e821f9fbff',
                'post_insert_call_file_offset': 0x4362a,
                'post_insert_target': 'wl_list_insert@plt', 'rip_relative_target': 0x7f358},
            'head': {'call_bytes': 'e8d8f7fbff', 'file_offset': 0x43773,
                'successor_jump_target': 0x4361e, 'target': 'wl_list_insert@plt'},
            'scroller': {'call_bytes': 'e8a8f1fbff', 'file_offset': 0x43da3,
                'successor_jump_target': 0x4361e, 'target': 'wl_list_insert@plt'},
            'tail': {'call_bytes': 'e832f9fbff', 'file_offset': 0x43619,
                'position': 'server.clients tail predecessor',
                'successor_fallthrough_target': 0x4361e, 'target': 'wl_list_insert@plt'},
        })
        getter = record['original_appid_getter']
        self.assertEqual((getter['file_offset'], getter['bytes'], getter['sha256'],
                          getter['instruction_count'], getter['artifact_excerpt_sha256']),
            (0x6b00, 1234,
             '11c0701eafb910c98f526a26d1926077f94bd411c7739db7066b6ba0742f7ead',
             246, 'b5022d81a58c70fe43d745d3ce98df4e7cc66b8a26c31df9a60479e398ffda6d'))
        self.assertEqual(record['abi']['offsets'], {
            'client_ext_foreign_toplevel': 1584, 'client_link': 280,
            'client_map_listener': 360, 'client_surface': 328, 'client_type': 0,
            'foreign_app_id': 48, 'foreign_identifier': 56, 'foreign_owner': 80,
            'foreign_title': 40, 'xdg_app_id': 192, 'xdg_title': 184,
            'xdg_toplevel': 56, 'xwayland_class': 144, 'xwayland_title': 136})
        wlroots = record['wlroots_runtime']
        self.assertEqual((wlroots['sha256'], wlroots['build_id'], wlroots['soname']),
            ('a1223d6311c31c18a00e64169e869cce0a128457c0113701f68b65c0c6cb4147',
             '94f7586649c4560dce6eb8edbf12927dcd318e8c', 'libwlroots-0.20.so'))
        self.assertEqual(wlroots['required_symbol'], {
            'bytes': 385, 'name': 'wlr_ext_foreign_toplevel_handle_v1_create',
            'sha256': 'daa924a5f9aa15ccf84ca2abacaa9519b5a09bc25824186f852c7a02dc186ac7',
            'value': 0x80a70})

    def test_one_exact_profile_is_identical_and_fails_closed(self):
        self.assertEqual(causal.MAPPING_PROFILES, comparison.MAPPING_PROFILES)
        profiles = [profile for profile in causal.MAPPING_PROFILES
                    if profile['executable_sha256'] == EXECUTABLE_SHA256]
        self.assertEqual(len(profiles), 1)
        profile = profiles[0]
        self.assertEqual(profile['native_audit_sha256'], AUDIT_SHA256)
        self.assertEqual(profile['lower_instruction_file_offsets'],
                         {'tail': 0x43619, 'head': 0x43773, 'scroller': 0x43da3})
        changed = dict(profile, executable_sha256='f' * 64)
        self.assertNotIn(changed, causal.MAPPING_PROFILES)
        mutated = bytearray(AUDIT.read_bytes())
        mutated[-2] ^= 1
        self.assertNotEqual(hashlib.sha256(mutated).hexdigest(),
                            profile['native_audit_sha256'])

    def test_profile_does_not_weaken_acceptance_or_claim_runtime_results(self):
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
