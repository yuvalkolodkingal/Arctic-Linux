"""Exact final-image Mango static profile binding; no runtime acceptance claim."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[2]
AUDIT = ROOT / ('tools/performance/mango-audits/'
    'f19e61512a2dbfc97b470edc7ae302fd442c1bbaa03487453935c3ae24853b28.json')
AUDIT_SHA256 = 'ac2f38f3095efcfeac1bf859d45fe1f8717c37566c55df1f75fbefd4c301059b'
EXECUTABLE_SHA256 = 'f19e61512a2dbfc97b470edc7ae302fd442c1bbaa03487453935c3ae24853b28'


def load(name, relative):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


causal = load('final_candidate_causal', 'tools/performance/causal.py')
comparison = load('final_candidate_compare', 'tools/performance/compare.py')


class FinalCandidateMangoProfileControls(unittest.TestCase):
    def test_closed_audit_binds_exact_image_elf_rpms_and_review(self):
        raw = AUDIT.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), AUDIT_SHA256)
        record = json.loads(raw)
        self.assertEqual(record['schema'], 'arctic-mango-native-profile-audit-v1')
        self.assertEqual(record['status'], 'candidate-specific-static-profile-admitted-pending-runtime')
        self.assertEqual(record['candidate'], {
            'build_id': 'd8926ee6b8dfa0781ad7882ebef49c0faf0f274d',
            'bytes': 530824,
            'elf_class': 'ELF64',
            'machine': 'x86_64',
            'path': '/usr/bin/mango',
            'rpm_nevra': 'mangowm-0.17.3-1.preview.38489618652.1.gite556b8a.fc44.x86_64',
            'rpmdb_file_digest_verified': True,
            'sha256': EXECUTABLE_SHA256,
        })
        provenance = record['provenance']
        self.assertEqual((provenance['producer_run_id'], provenance['artifact_id'],
                          provenance['iso_sha256']),
            (38489618652, 11862999301,
             '97a6b905640ce6782ae303992e4b292c744ff7abedf7ea26f4b28f918568f140'))
        self.assertEqual((provenance['static_run_id'], provenance['static_execution_sha'],
                          provenance['static_artifact_id'], provenance['static_artifact_bytes'],
                          provenance['static_artifact_sha256']),
            (38510027685, '7d787d874db41451ec4c1875f95362bcc614788b',
             11869024003, 3731666,
             'a07f4c94afcee62dc81900793463c0f9f2d7b171764733de57b35260cd5a4047'))
        self.assertEqual((provenance['review_run_id'], provenance['review_execution_sha']),
            (38510351441, 'cd172a451c7783813be7caeddd4abad8086af21d'))
        self.assertEqual(record['acceptance'], {
            'performance_acceptance': False,
            'release_acceptance': False,
            'runtime_profile_admitted': False,
            'static_profile_admitted': True,
        })

    def test_all_function_getter_abi_and_cfg_proofs_are_exact(self):
        record = json.loads(AUDIT.read_bytes())
        mapping = record['mapping_function']
        self.assertEqual((mapping['file_offset'], mapping['bytes'], mapping['sha256']),
            (0x43110, 4109,
             '3955d4a7db3fac1b5f0f17833562299ab299b2250eb2a4a66e7ac390f2dcb9bc'))
        self.assertEqual(mapping['inherited_cfg_audit_sha256'],
            'dacb0de958e7ba90099a70b2e66f49756916ed3d42f4e70ac6280f7d4b6a571c')
        self.assertEqual(mapping['insertion_sites'], {
            'common_post': {'file_offset': 0x4361e, 'instruction_bytes': '488d3d33bd0300'},
            'head': {'file_offset': 0x43773, 'call_bytes': 'e8d8f7fbff',
                     'successor_jump_target': 0x4361e, 'target': 'wl_list_insert@plt'},
            'scroller': {'file_offset': 0x43da3, 'call_bytes': 'e8a8f1fbff',
                         'successor_jump_target': 0x4361e, 'target': 'wl_list_insert@plt'},
            'tail': {'file_offset': 0x43619, 'call_bytes': 'e832f9fbff',
                     'position': 'server.clients tail predecessor', 'target': 'wl_list_insert@plt'},
        })
        getter = record['original_appid_getter']
        self.assertEqual((getter['file_offset'], getter['bytes'], getter['sha256']),
            (0x6b00, 1234,
             '11c0701eafb910c98f526a26d1926077f94bd411c7739db7066b6ba0742f7ead'))
        self.assertEqual(record['abi']['offsets'], {
            'client_ext_foreign_toplevel': 1584, 'client_surface': 328, 'client_type': 0,
            'foreign_app_id': 48, 'foreign_identifier': 56, 'foreign_owner': 80,
            'xdg_app_id': 192, 'xdg_toplevel': 56, 'xwayland_class': 144,
        })
        self.assertEqual(record['abi']['wlroots_runtime_sha256'],
            'a1223d6311c31c18a00e64169e869cce0a128457c0113701f68b65c0c6cb4147')

    def test_only_one_exact_whole_elf_profile_is_admitted_in_both_consumers(self):
        self.assertEqual(causal.MAPPING_PROFILES, comparison.MAPPING_PROFILES)
        profiles = [item for item in causal.MAPPING_PROFILES
                    if item['executable_sha256'] == EXECUTABLE_SHA256]
        self.assertEqual(len(profiles), 1)
        profile = profiles[0]
        self.assertEqual(profile, {
            'executable_sha256': EXECUTABLE_SHA256,
            'native_audit_sha256': AUDIT_SHA256,
            'function_file_offset': 0x43110,
            'function_size': 4109,
            'function_sha256': '3955d4a7db3fac1b5f0f17833562299ab299b2250eb2a4a66e7ac390f2dcb9bc',
            'instruction_file_offset': 0x4361e,
            'client_ext_offset': 1584,
            'lower_instruction_file_offsets': {'tail': 0x43619, 'head': 0x43773,
                                               'scroller': 0x43da3},
            'ipc_function_file_offset': 0x6b00,
            'ipc_function_size': 1234,
            'ipc_function_sha256': '11c0701eafb910c98f526a26d1926077f94bd411c7739db7066b6ba0742f7ead',
            'client_type_offset': 0, 'client_surface_offset': 328, 'xdg_type': 0,
            'xdg_toplevel_offset': 56, 'xdg_appid_offset': 192,
            'xwayland_type': 2, 'xwayland_class_offset': 144,
        })
        # A same-code packaging rebuild remains unknown until its own exact ELF
        # identity and audit record are appended.
        changed = dict(profile, executable_sha256='0' * 64)
        self.assertNotIn(changed, causal.MAPPING_PROFILES)
        mutated = bytearray(AUDIT.read_bytes())
        mutated[-2] ^= 1
        self.assertNotEqual(hashlib.sha256(mutated).hexdigest(), profile['native_audit_sha256'])


if __name__ == '__main__':
    unittest.main()
