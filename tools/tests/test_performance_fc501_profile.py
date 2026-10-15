#!/usr/bin/env python3
"""Static observer profile for diagnostic producer 38707130991; runtime acceptance remains pending."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[2]
EXECUTABLE_SHA256 = 'fe1541fc78c09ff31dceddd98bcd47533d2ed02450e6b47a3ef3fc515ca9bf7c'
AUDIT = ROOT / 'tools/performance/mango-audits' / (EXECUTABLE_SHA256 + '.json')
AUDIT_SHA256 = '58565fc381904752561f68b3246aeb38e85709b4d04b9f73282f01ada9e05646'


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
            'build_id': '279e666e61c0e40a15b4335301c36652af0f274d',
            'bytes': 530776,
            'elf_class': 'ELF64',
            'executable_pt_load': {'file_bytes': 396989, 'file_offset': 0,
                'flags': 'R E', 'memory_bytes': 396989, 'virtual_address': 0},
            'machine': 'x86_64',
            'path': '/usr/bin/mango',
            'rpm_nevra': 'mangowm-0.17.3-1.preview.38707130991.1.gitfc501fd.fc44.x86_64',
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
            'producer_run_id': 38707130991,
            'producer_run_attempt': 1,
            'producer_source_sha': 'fc501fdf90c17c617b15b8b13038d062d519fcc6',
            'producer_artifact_id': 11961831325,
            'producer_artifact_bytes': 1936373046,
            'producer_artifact_sha256':
                '1c1e3e34e240b9e6ec592e3bce23330378e6bc2a7815ab295080fa61925082c3',
            'producer_receipt_sha256':
                '9d755876dc45d143506da8b52cf98d92205ab1d2f014355de612db0bb04bc9b4',
            'iso_bytes': 1936185344,
            'iso_sha256':
                '92fe2a1bcb9a67b8ed72e7b38d065e7e68ae26a38e930042a752aae7146e8d66',
        })
        self.assertEqual({key: provenance[key] for key in (
            'static_run_id', 'static_run_attempt', 'static_execution_sha',
            'static_parent_sha', 'static_artifact_id', 'static_artifact_bytes',
            'static_artifact_sha256', 'static_report_sha256',
            'static_execution_manifest_sha256')}, {
            'static_run_id': 38715312294,
            'static_run_attempt': 1,
            'static_execution_sha': '0a1df4d9a24d8b21a0562b0bf3851feba2dffe6b',
            'static_parent_sha': '365eebced619cb12f74ab95ed2da937d8ecea42c',
            'static_artifact_id': 11962866705,
            'static_artifact_bytes': 3731615,
            'static_artifact_sha256':
                '95eca61a5c358dc28756293bd08da6a9fbdf5d96379d49f185e1d40488c9a24b',
            'static_report_sha256':
                '3320a1d0c82184e0337fdbb1512f3eebc04bf3f166ea33698bc6d73c94fe243e',
            'static_execution_manifest_sha256':
                '99f0e5a8e9e1a61c6b86987fe802094ac7a1188d1f87747074e7e69fce7af932',
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
        manifest = json.loads((ROOT / 'tools/performance/execution-manifest.json').read_text())
        self.assertIs(manifest['ready'], True)
        self.assertEqual(manifest['image'], {
            'run_id': 38735141923,
            'artifact_id': 11976239386,
            'archive_bytes': 1936454966,
            'archive_sha256': '86b5f15a6eb3cfa467c1cd05531637915aee521364a1f0b83a7dc20b5e0462ee',
            'source_sha': '14ba50a70783fec583a288d34ea233a5d7c9941a',
            'name': 'Arctic-Linux-1.2-candidate-38735141923-1-x86_64.iso',
            'bytes': 1936267264,
            'sha256': '1e76b747f3ec7f50adc84c3d36d46e9a40a1759ab97a41aebc9ca92609cf697a',
            'producer_mode': 'frozen-external-paired-v1',
            'producer_receipt_sha256': 'f21f1c1688c9e04c0a8a8d8a6f8b42fadaff59ff102ef03c4376e425614d956c',
        })
        self.assertIs(manifest['release_acceptance'], False)
        self.assertFalse((ROOT / '.github/qualification-20261010.performance').exists())
        source = (ROOT / 'tools/performance/compare.py').read_text()
        self.assertIn('limit = min(.005, sample * .025)', source)
        self.assertIn("if set(runs) != {'baseline', 'candidate'} or any(len(group) != 3", source)
        self.assertIn("median['candidate'] > median['baseline'] * (1 + gate)", source)


if __name__ == '__main__':
    unittest.main()
