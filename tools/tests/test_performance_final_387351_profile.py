#!/usr/bin/env python3
"""Historical exact 387351 observer profile remains fail closed."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).parents[2]
EXECUTABLE_SHA256 = '11471553075f17b05411a8511b106a91d506100544d6f76400ce139c2ce0c99c'
AUDIT = ROOT / 'tools/performance/mango-audits' / (EXECUTABLE_SHA256 + '.json')
AUDIT_SHA256 = 'e39ce4f70ca131622ddff1f9341878107834b4a28ca2838a287cf66c202d77a0'


def load(name, relative):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


causal = load('historical_387351_causal', 'tools/performance/causal.py')
comparison = load('historical_387351_compare', 'tools/performance/compare.py')


class Historical387351MangoProfileControls(unittest.TestCase):
    def record(self):
        raw = AUDIT.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), AUDIT_SHA256)
        return json.loads(raw)

    def test_historical_image_and_rpm_identity_are_closed(self):
        record = self.record()
        self.assertEqual(record['schema'], 'arctic-mango-native-profile-audit-v1')
        self.assertEqual(record['status'],
                         'candidate-specific-static-profile-admitted-pending-runtime')
        self.assertEqual(record['candidate'], {
            'build_id': 'aebf5d21049f11a19bbdb10a2cf23d6daf0f274d',
            'bytes': 530776,
            'elf_class': 'ELF64',
            'executable_pt_load': {'file_bytes': 396989, 'file_offset': 0,
                'flags': 'R E', 'memory_bytes': 396989, 'virtual_address': 0},
            'machine': 'x86_64',
            'path': '/usr/bin/mango',
            'rpm_nevra':
                'mangowm-0.17.3-1.preview.38735141923.1.git14ba50a.fc44.x86_64',
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
            'producer_run_id': 38735141923,
            'producer_run_attempt': 1,
            'producer_source_sha': '14ba50a70783fec583a288d34ea233a5d7c9941a',
            'producer_artifact_id': 11976239386,
            'producer_artifact_bytes': 1936454966,
            'producer_artifact_sha256':
                '86b5f15a6eb3cfa467c1cd05531637915aee521364a1f0b83a7dc20b5e0462ee',
            'producer_receipt_sha256':
                'f21f1c1688c9e04c0a8a8d8a6f8b42fadaff59ff102ef03c4376e425614d956c',
            'iso_bytes': 1936267264,
            'iso_sha256':
                '1e76b747f3ec7f50adc84c3d36d46e9a40a1759ab97a41aebc9ca92609cf697a',
        })
        self.assertEqual(provenance['root_filesystem_sha256'],
                         'be7d7733a9d666a03b35b4237c6bf36297ac5e88cad1965d2d019ed5abd34b27')
        self.assertTrue(provenance['rpmdb_mango_file_digest_verified'])
        self.assertTrue(provenance['rpmdb_wlroots_file_digest_verified'])

    def test_machine_code_cfg_getter_and_runtime_abi_are_exact(self):
        record = self.record()
        mapping = record['mapping_function']
        self.assertEqual((mapping['file_offset'], mapping['bytes'], mapping['sha256']),
            (0x43110, 4109,
             '3955d4a7db3fac1b5f0f17833562299ab299b2250eb2a4a66e7ac390f2dcb9bc'))
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
        self.assertEqual((getter['file_offset'], getter['bytes'], getter['sha256']),
            (0x6b00, 1234,
             '11c0701eafb910c98f526a26d1926077f94bd411c7739db7066b6ba0742f7ead'))
        wlroots = record['wlroots_runtime']
        self.assertEqual((wlroots['sha256'], wlroots['build_id'], wlroots['soname']),
            ('a1223d6311c31c18a00e64169e869cce0a128457c0113701f68b65c0c6cb4147',
             '94f7586649c4560dce6eb8edbf12927dcd318e8c', 'libwlroots-0.20.so'))

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

    def test_profile_preserves_limits_and_has_no_acceptance_claim(self):
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
        self.assertIs(manifest['ready'], True)
        self.assertEqual(manifest['image']['run_id'], 38823208615)
        self.assertEqual(manifest['image']['source_sha'],
                         'cfc39dad61125e4fa8fb7906ac14f4c360b58228')
        self.assertEqual(manifest['image']['sha256'],
                         'c13c4589d7b522fec7dbd5eeafec00cf9088d8788cdfb6771a7382285846d7c7')
        self.assertTrue(manifest['execution_files'])
        self.assertTrue(manifest['observer'])
        self.assertIs(manifest['release_acceptance'], False)
        activation = (ROOT / '.github/qualification-20261010.performance').read_text().strip()
        self.assertEqual(len(activation), 40)
        self.assertTrue(all(char in '0123456789abcdef' for char in activation))
        source = (ROOT / 'tools/performance/compare.py').read_text()
        self.assertIn('limit = min(.005, sample * .025)', source)
        self.assertIn("if set(runs) != {'baseline', 'candidate'} or any(len(group) != 3", source)
        self.assertIn("median['candidate'] > median['baseline'] * (1 + gate)", source)


if __name__ == '__main__':
    unittest.main()
