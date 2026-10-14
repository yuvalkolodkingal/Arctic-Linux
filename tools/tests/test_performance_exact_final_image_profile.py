"""Exact released-candidate Mango static profile; runtime gates remain pending."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[2]
EXECUTABLE_SHA256 = '9a88aa4b6e9bc47ee33a876e9f922af884f6d645abf063ef56874bdd30edee65'
AUDIT = ROOT / 'tools/performance/mango-audits' / (EXECUTABLE_SHA256 + '.json')
AUDIT_SHA256 = '2c4aa538589935b4b23b68007bb0b2ef5c667c61c5c7ddda98e8ab6aaa1701b4'


def load(name, relative):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


causal = load('exact_final_image_causal', 'tools/performance/causal.py')
comparison = load('exact_final_image_compare', 'tools/performance/compare.py')


class ExactFinalImageMangoProfileControls(unittest.TestCase):
    def record(self):
        raw = AUDIT.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), AUDIT_SHA256)
        return json.loads(raw)

    def test_exact_producer_iso_artifact_and_static_run_are_closed(self):
        record = self.record()
        self.assertEqual(record['schema'], 'arctic-mango-native-profile-audit-v1')
        self.assertEqual(record['status'],
                         'candidate-specific-static-profile-admitted-pending-runtime')
        candidate = record['candidate']
        self.assertEqual((candidate['sha256'], candidate['bytes'], candidate['build_id'],
                          candidate['rpm_nevra'], candidate['rpmdb_file_digest_verified']),
            (EXECUTABLE_SHA256, 530776, '20d90fa674cdea636aa58186b83eac33af0f274d',
             'mangowm-0.17.3-1.preview.38616494387.1.gitda59f68.fc44.x86_64', True))
        provenance = record['provenance']
        self.assertEqual({key: provenance[key] for key in (
            'producer_run_id', 'producer_run_attempt', 'producer_source_sha',
            'producer_artifact_id', 'producer_artifact_bytes', 'producer_artifact_sha256',
            'producer_receipt_sha256', 'iso_bytes', 'iso_sha256')}, {
            'producer_run_id': 38616494387,
            'producer_run_attempt': 1,
            'producer_source_sha': 'da59f68a967c39205b2aa7648f3c11224247982c',
            'producer_artifact_id': 11924131449,
            'producer_artifact_bytes': 1936409910,
            'producer_artifact_sha256':
                '78bdb23505a2d090f26433f019a52d9bae0b76945e2d21346cfe3e6b0100eb73',
            'producer_receipt_sha256':
                '03d0a8cdb4118e1985202951c0935b241cfbded037c723b76068f4e4624b9ccd',
            'iso_bytes': 1936222208,
            'iso_sha256':
                '743036565d70cb51856c68902d4c46383406b059d29870ce3b41eb709579589c',
        })
        self.assertEqual({key: provenance[key] for key in (
            'static_run_id', 'static_run_attempt', 'static_execution_sha',
            'static_parent_sha', 'static_artifact_id', 'static_artifact_bytes',
            'static_artifact_sha256', 'static_report_sha256',
            'static_execution_manifest_sha256')}, {
            'static_run_id': 38637532023,
            'static_run_attempt': 1,
            'static_execution_sha': 'ddf4d4251f313fd75f8934834fb6ea1af11b76c3',
            'static_parent_sha': '2332a3dc69b3f4a552c276d8a4da0d567c02861e',
            'static_artifact_id': 11928747028,
            'static_artifact_bytes': 3731612,
            'static_artifact_sha256':
                'e414c9822b9a9a4f66ea1b49e45c630f5c1386f20a8dcf6cc19f63d0805ec10c',
            'static_report_sha256':
                '223c4997489995e177d2fb0f9906af5c68ce08cf6fe08d8b5a198f66cade7580',
            'static_execution_manifest_sha256':
                '6c14c74318568feb4199e9dad1f8a7261dc521c5c92531e0f28d04f0b159c687',
        })

    def test_whole_elf_mapping_all_sites_role_getter_and_abi_are_exact(self):
        record = self.record()
        self.assertEqual(record['candidate']['executable_pt_load'], {
            'file_offset': 0, 'file_bytes': 396989, 'virtual_address': 0,
            'memory_bytes': 396989, 'flags': 'R E'})
        wlroots = record['wlroots_runtime']
        self.assertEqual((wlroots['sha256'], wlroots['build_id'], wlroots['soname'],
                          wlroots['rpm_nevra'], wlroots['rpmdb_file_digest_verified']),
            ('a1223d6311c31c18a00e64169e869cce0a128457c0113701f68b65c0c6cb4147',
             '94f7586649c4560dce6eb8edbf12927dcd318e8c', 'libwlroots-0.20.so',
             'wlroots-0.20.2-1.fc44.x86_64', True))
        self.assertEqual(wlroots['required_symbol'], {
            'name': 'wlr_ext_foreign_toplevel_handle_v1_create',
            'value': 0x80a70, 'bytes': 385,
            'sha256': 'daa924a5f9aa15ccf84ca2abacaa9519b5a09bc25824186f852c7a02dc186ac7'})
        mapping = record['mapping_function']
        self.assertEqual((mapping['file_offset'], mapping['bytes'], mapping['sha256'],
                          mapping['instruction_count']),
            (0x43110, 4109,
             '3955d4a7db3fac1b5f0f17833562299ab299b2250eb2a4a66e7ac390f2dcb9bc',
             796))
        self.assertEqual(mapping['insertion_sites'], {
            'common_post': {'file_offset': 0x4361e, 'instruction_bytes': '488d3d33bd0300',
                'rip_relative_target': 0x7f358, 'post_insert_call_file_offset': 0x4362a,
                'post_insert_call_bytes': 'e821f9fbff', 'post_insert_target': 'wl_list_insert@plt'},
            'head': {'file_offset': 0x43773, 'call_bytes': 'e8d8f7fbff',
                'target': 'wl_list_insert@plt', 'successor_jump_target': 0x4361e},
            'scroller': {'file_offset': 0x43da3, 'call_bytes': 'e8a8f1fbff',
                'target': 'wl_list_insert@plt', 'successor_jump_target': 0x4361e},
            'tail': {'file_offset': 0x43619, 'call_bytes': 'e832f9fbff',
                'target': 'wl_list_insert@plt', 'position': 'server.clients tail predecessor',
                'successor_fallthrough_target': 0x4361e},
        })
        self.assertEqual(mapping['register_and_list_contract']['derivation'], [
            'R12 receives map listener pointer at 0x43154',
            'RBX=R12-0x168 at 0x43157',
            'R14=R12-0x50 at 0x434e4, therefore Client+0x118'])
        getter = record['original_appid_getter']
        self.assertEqual((getter['file_offset'], getter['bytes'], getter['sha256'],
                          getter['instruction_count']),
            (0x6b00, 1234,
             '11c0701eafb910c98f526a26d1926077f94bd411c7739db7066b6ba0742f7ead',
             246))
        self.assertEqual(record['abi']['offsets'], {
            'client_type': 0, 'client_link': 280, 'client_surface': 328,
            'client_map_listener': 360, 'client_ext_foreign_toplevel': 1584,
            'xdg_toplevel': 56, 'xdg_title': 184, 'xdg_app_id': 192,
            'xwayland_title': 136, 'xwayland_class': 144,
            'foreign_title': 40, 'foreign_app_id': 48,
            'foreign_identifier': 56, 'foreign_owner': 80})
        self.assertEqual(record['abi']['types'], {'xdg': 0, 'xwayland': 2})

    def test_one_profile_is_identical_in_both_consumers_and_fails_closed(self):
        record = self.record()
        self.assertEqual(causal.MAPPING_PROFILES, comparison.MAPPING_PROFILES)
        profiles = [p for p in causal.MAPPING_PROFILES
                    if p['executable_sha256'] == EXECUTABLE_SHA256]
        self.assertEqual(len(profiles), 1)
        profile = profiles[0]
        self.assertEqual(profile['native_audit_sha256'], AUDIT_SHA256)
        self.assertEqual(profile['lower_instruction_file_offsets'],
                         {'tail': 0x43619, 'head': 0x43773, 'scroller': 0x43da3})
        self.assertEqual((profile['instruction_file_offset'], profile['client_ext_offset'],
                          profile['client_type_offset'], profile['client_surface_offset'],
                          profile['xdg_type'], profile['xdg_toplevel_offset'],
                          profile['xdg_appid_offset'], profile['xwayland_type'],
                          profile['xwayland_class_offset']),
            (0x4361e, 1584, 0, 328, 0, 56, 192, 2, 144))
        self.assertFalse(any(p['executable_sha256'] == '0' * 64
                             for p in causal.MAPPING_PROFILES))

    def test_size_privacy_and_performance_gates_are_not_acceptance(self):
        record = self.record()
        self.assertEqual(record['acceptance'], {
            'performance_acceptance': False, 'release_acceptance': False,
            'runtime_profile_admitted': False, 'static_profile_admitted': True})
        size = record['contracts']['size']
        self.assertTrue(size['strict_limit_passed'])
        self.assertFalse(size['preferred_limit_passed'])
        self.assertLess(size['iso_bytes'], size['iso_strict_limit_bytes'])
        privacy = record['contracts']['privacy']
        self.assertTrue(privacy['static_only'])
        self.assertFalse(privacy['audio_present'])
        self.assertFalse(privacy['transcript_present'])
        self.assertFalse(privacy['runtime_user_data_present'])
        gates = record['contracts']['acceptance_gates']
        self.assertEqual(gates['precision'],
                         'interval <= min(0.005 seconds, observed * 0.025)')
        self.assertEqual(gates['application_regression_percent'], 10)
        self.assertTrue(gates['role_identity_required'])
        self.assertTrue(gates['zero_event_loss_required'])
        self.assertTrue(gates['exactly_six_boots_required'])
        self.assertFalse(gates['samples_dropped'])
        source = (ROOT / 'tools/performance/compare.py').read_text()
        self.assertIn('limit = min(.005, sample * .025)', source)
        self.assertIn("if set(runs) != {'baseline', 'candidate'} or any(len(group) != 3", source)
        self.assertIn("or any(type(value) is not int or value != 0 for value in counts.values())", source)
        self.assertIn("median['candidate'] > median['baseline'] * (1 + gate)", source)


if __name__ == '__main__':
    unittest.main()
