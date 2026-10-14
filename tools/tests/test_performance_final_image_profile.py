"""Exact final ISO Mango static profile binding; no runtime acceptance claim."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[2]
EXECUTABLE_SHA256 = '9c44252b7651a3fac5251c93e9aa82999f1b3008b71aae9e53a81497e9168e71'
AUDIT = ROOT / 'tools/performance/mango-audits' / (EXECUTABLE_SHA256 + '.json')
AUDIT_SHA256 = '9d26315c26453714c74004eae59b9c09a5fb2b5a4ab393c1846af521d5d4b5dc'


def load(name, relative):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


causal = load('final_image_causal', 'tools/performance/causal.py')
comparison = load('final_image_compare', 'tools/performance/compare.py')


class FinalImageMangoProfileControls(unittest.TestCase):
    def test_closed_audit_binds_exact_iso_elf_rpm_and_all_evidence_artifacts(self):
        raw = AUDIT.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), AUDIT_SHA256)
        record = json.loads(raw)
        self.assertEqual(record['schema'], 'arctic-mango-native-profile-audit-v1')
        self.assertEqual(record['status'],
                         'candidate-specific-static-profile-admitted-pending-runtime')
        self.assertEqual(record['candidate'], {
            'build_id': '1777a38791e33c265ef31ede50c770fbaf0f274d',
            'bytes': 530776,
            'elf_class': 'ELF64',
            'machine': 'x86_64',
            'path': '/usr/bin/mango',
            'rpm_nevra':
                'mangowm-0.17.3-1.preview.38536710765.1.gita13d911.fc44.x86_64',
            'rpmdb_file_digest_verified': True,
            'sha256': EXECUTABLE_SHA256,
        })
        provenance = record['provenance']
        self.assertEqual({key: provenance[key] for key in (
            'producer_run_id', 'producer_run_attempt', 'producer_source_sha',
            'producer_artifact_id', 'producer_artifact_bytes', 'producer_artifact_sha256',
            'iso_bytes', 'iso_sha256')}, {
            'producer_run_id': 38536710765,
            'producer_run_attempt': 1,
            'producer_source_sha': 'a13d91118fb90b99dbbf1899fadc3e184ea213ca',
            'producer_artifact_id': 11883891542,
            'producer_artifact_bytes': 1936466960,
            'producer_artifact_sha256':
                '83d86c18089e23ce76a0e93616f1b2b677feae2c7530b71b577ce46e6555752c',
            'iso_bytes': 1936279552,
            'iso_sha256': 'b6bbbea37bc761d783e71417878d047bf4d1805feb60d7bbaf2cf0c5a94d05ea',
        })
        self.assertEqual({key: provenance[key] for key in (
            'static_run_id', 'static_run_attempt', 'static_execution_sha',
            'static_parent_sha', 'static_artifact_id', 'static_artifact_bytes',
            'static_artifact_sha256')}, {
            'static_run_id': 38555067207,
            'static_run_attempt': 1,
            'static_execution_sha': '175fa5e0c88424cfc40fb34000b4b0aa00b30994',
            'static_parent_sha': '983d370c7e87fdfffb7ace4ca09c4c429051f92a',
            'static_artifact_id': 11889750776,
            'static_artifact_bytes': 3731625,
            'static_artifact_sha256':
                'faa120f5e57ed57d6c6e541c335f31497e1f46aabe7440884736fecbd25e842a',
        })
        self.assertEqual({key: provenance[key] for key in (
            'bounded_review_run_id', 'bounded_review_run_attempt',
            'bounded_review_execution_sha', 'bounded_review_parent_sha',
            'bounded_review_artifact_id', 'bounded_review_artifact_bytes',
            'bounded_review_artifact_sha256')}, {
            'bounded_review_run_id': 38556327794,
            'bounded_review_run_attempt': 1,
            'bounded_review_execution_sha': 'f84b856fcdf4efb268b879b45e1e797af7b9071a',
            'bounded_review_parent_sha': '183396c897776a268bc49b0555041f79ef5e3d68',
            'bounded_review_artifact_id': 11889243578,
            'bounded_review_artifact_bytes': 5792,
            'bounded_review_artifact_sha256':
                'ef2c4d832cb95f5e8ff54090acdddb0466522f53a0399de39a4e7f6562fa4f89',
        })
        self.assertEqual(record['acceptance'], {
            'performance_acceptance': False,
            'release_acceptance': False,
            'runtime_profile_admitted': False,
            'static_profile_admitted': True,
        })

    def test_mapping_getter_sites_cfg_and_abi_are_exact(self):
        record = json.loads(AUDIT.read_bytes())
        mapping = record['mapping_function']
        self.assertEqual((mapping['file_offset'], mapping['bytes'], mapping['sha256'],
                          mapping['instruction_count'], mapping['disassembly_sha256']),
            (0x43110, 4109,
             '3955d4a7db3fac1b5f0f17833562299ab299b2250eb2a4a66e7ac390f2dcb9bc',
             796, 'd33b1635632c56b7f447017e94332f0580a386fb99bfa4b38859d84f0d7010ba'))
        self.assertEqual(mapping['inherited_cfg_audit_sha256'],
            'dacb0de958e7ba90099a70b2e66f49756916ed3d42f4e70ac6280f7d4b6a571c')
        self.assertEqual(mapping['insertion_sites'], {
            'common_post': {
                'file_offset': 0x4361e, 'instruction_bytes': '488d3d33bd0300',
                'post_insert_call_bytes': 'e821f9fbff',
                'post_insert_call_file_offset': 0x4362a,
                'post_insert_target': 'wl_list_insert@plt',
                'rip_relative_target': 0x7f358,
            },
            'head': {'file_offset': 0x43773, 'call_bytes': 'e8d8f7fbff',
                     'successor_jump_target': 0x4361e, 'target': 'wl_list_insert@plt'},
            'scroller': {'file_offset': 0x43da3, 'call_bytes': 'e8a8f1fbff',
                         'successor_jump_target': 0x4361e,
                         'target': 'wl_list_insert@plt'},
            'tail': {'file_offset': 0x43619, 'call_bytes': 'e832f9fbff',
                     'position': 'server.clients tail predecessor',
                     'successor_fallthrough_target': 0x4361e,
                     'target': 'wl_list_insert@plt'},
        })
        getter = record['original_appid_getter']
        self.assertEqual((getter['file_offset'], getter['bytes'], getter['sha256'],
                          getter['instruction_count'], getter['disassembly_sha256']),
            (0x6b00, 1234,
             '11c0701eafb910c98f526a26d1926077f94bd411c7739db7066b6ba0742f7ead',
             246, '99c52d8432a42464ffc1fcff21fc15d77fdada1d2a43aecbead4097de44b68f1'))
        self.assertEqual(record['abi']['offsets'], {
            'client_ext_foreign_toplevel': 1584, 'client_surface': 328, 'client_type': 0,
            'foreign_app_id': 48, 'foreign_identifier': 56, 'foreign_owner': 80,
            'xdg_app_id': 192, 'xdg_toplevel': 56, 'xwayland_class': 144,
        })
        self.assertEqual({key: record['abi'][key] for key in (
            'wlroots_runtime_sha256', 'wlroots_runtime_build_id',
            'wlroots_runtime_nevra', 'wlroots_runtime_soname',
            'wlroots_required_foreign_toplevel_symbol_present')}, {
            'wlroots_runtime_sha256':
                'a1223d6311c31c18a00e64169e869cce0a128457c0113701f68b65c0c6cb4147',
            'wlroots_runtime_build_id': '94f7586649c4560dce6eb8edbf12927dcd318e8c',
            'wlroots_runtime_nevra': 'wlroots-0.20.2-1.fc44.x86_64',
            'wlroots_runtime_soname': 'libwlroots-0.20.so',
            'wlroots_required_foreign_toplevel_symbol_present': True,
        })

    def test_only_one_exact_whole_elf_profile_is_identical_in_both_consumers(self):
        self.assertEqual(causal.MAPPING_PROFILES, comparison.MAPPING_PROFILES)
        profiles = [item for item in causal.MAPPING_PROFILES
                    if item['executable_sha256'] == EXECUTABLE_SHA256]
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0], {
            'executable_sha256': EXECUTABLE_SHA256,
            'native_audit_sha256': AUDIT_SHA256,
            'function_file_offset': 0x43110,
            'function_size': 4109,
            'function_sha256':
                '3955d4a7db3fac1b5f0f17833562299ab299b2250eb2a4a66e7ac390f2dcb9bc',
            'instruction_file_offset': 0x4361e,
            'client_ext_offset': 1584,
            'lower_instruction_file_offsets': {
                'tail': 0x43619, 'head': 0x43773, 'scroller': 0x43da3},
            'ipc_function_file_offset': 0x6b00,
            'ipc_function_size': 1234,
            'ipc_function_sha256':
                '11c0701eafb910c98f526a26d1926077f94bd411c7739db7066b6ba0742f7ead',
            'client_type_offset': 0,
            'client_surface_offset': 328,
            'xdg_type': 0,
            'xdg_toplevel_offset': 56,
            'xdg_appid_offset': 192,
            'xwayland_type': 2,
            'xwayland_class_offset': 144,
        })
        changed = dict(profiles[0], executable_sha256='0' * 64)
        self.assertNotIn(changed, causal.MAPPING_PROFILES)
        mutated = bytearray(AUDIT.read_bytes())
        mutated[-2] ^= 1
        self.assertNotEqual(hashlib.sha256(mutated).hexdigest(),
                            profiles[0]['native_audit_sha256'])


if __name__ == '__main__':
    unittest.main()
