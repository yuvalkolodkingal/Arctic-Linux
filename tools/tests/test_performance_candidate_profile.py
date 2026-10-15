"""Candidate-specific static Mango profile controls; no VM or timing claims."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[2]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

causal = load('candidate_profile_causal', ROOT / 'tools/performance/causal.py')
comparison = load('candidate_profile_compare', ROOT / 'tools/performance/compare.py')
contract = load('candidate_profile_contract', ROOT / 'tools/performance/contract.py')
AUDIT = ROOT / 'tools/performance/mango-audits/315bc239be1a8a4bc1f0b113e39aa9c959201b26eca2123c75ceb10f01bbb2ab.json'
AUDIT_SHA256 = '45b14e12747b81f2133d812339267e7460a222d5c9a4e7cb6cc3dd5019c2bba7'
EXECUTABLE_SHA256 = '315bc239be1a8a4bc1f0b113e39aa9c959201b26eca2123c75ceb10f01bbb2ab'

class CandidateMangoProfileControls(unittest.TestCase):
    def test_profile_append_preserves_historical_source_and_pins_current_observer(self):
        additions = (
            (b'\n# candidate-profile-315bc-begin\n', b'# candidate-profile-315bc-end\n'),
            (b'\n# candidate-profile-f19e-begin\n', b'# candidate-profile-f19e-end\n'),
            (b'\n# candidate-profile-9c442-begin\n', b'# candidate-profile-9c442-end\n'),
            (b'\n# candidate-profile-9a88-begin\n', b'# candidate-profile-9a88-end\n'),
        )
        old_hashes = {
            'causal.py': '3195ee9137ca9dbd908c9021336a1f262c298ef51725bc8b2a8619d26c54e4d9',
            'compare.py': '8a6097348162d9b58563accbc4a2648b24e1172863b8d9a2e404feaaffaaf86a',
        }
        for name, expected in old_hashes.items():
            historical = (ROOT / 'tools/performance' / name).read_bytes()
            for marker, ending in additions:
                self.assertEqual(historical.count(marker), 1)
                before, addition = historical.split(marker)
                self.assertEqual(addition.count(ending), 1)
                profile, after = addition.split(ending)
                self.assertTrue(profile.startswith(b'MAPPING_PROFILES += (\n'))
                historical = before + after
            self.assertEqual(hashlib.sha256(historical).hexdigest(), expected)
        observer = contract.observer_hashes(ROOT)
        runner = (ROOT / 'tools/performance/run-paired.py').read_bytes()
        self.assertEqual(runner.count(hashlib.sha256(
            (ROOT / 'tools/performance/causal.py').read_bytes()).hexdigest().encode()), 1)
        for key in ('source_sha256', 'frozen_sha256', 'comparator_sha256'):
            self.assertEqual(runner.count(observer[key].encode()), 1)

    def test_audit_bytes_and_exact_profile_are_bound_in_both_consumers(self):
        raw = AUDIT.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), AUDIT_SHA256)
        record = json.loads(raw)
        self.assertEqual(record['schema'], 'arctic-mango-native-profile-audit-v1')
        self.assertEqual(record['status'], 'candidate-specific-static-profile-admitted-pending-runtime')
        self.assertEqual(record['candidate']['sha256'], EXECUTABLE_SHA256)
        self.assertEqual(record['candidate']['bytes'], 530776)
        profiles = [p for p in causal.MAPPING_PROFILES if p['executable_sha256'] == EXECUTABLE_SHA256]
        self.assertEqual(len(profiles), 1)
        self.assertEqual(causal.MAPPING_PROFILES, comparison.MAPPING_PROFILES)
        profile = profiles[0]
        self.assertEqual(profile['native_audit_sha256'], AUDIT_SHA256)
        self.assertEqual((profile['function_file_offset'], profile['function_size'], profile['function_sha256']),
            (0x43110, 4109, '3955d4a7db3fac1b5f0f17833562299ab299b2250eb2a4a66e7ac390f2dcb9bc'))
        self.assertEqual(profile['lower_instruction_file_offsets'],
            {'tail': 0x43619, 'head': 0x43773, 'scroller': 0x43da3})
        self.assertEqual(profile['instruction_file_offset'], 0x4361e)
        self.assertEqual((profile['ipc_function_file_offset'], profile['ipc_function_size'],
                          profile['ipc_function_sha256']),
            (0x6b00, 1234, '11c0701eafb910c98f526a26d1926077f94bd411c7739db7066b6ba0742f7ead'))
        self.assertEqual(record['acceptance'], {
            'static_profile_admitted': True,
            'runtime_profile_admitted': False,
            'performance_acceptance': False,
            'release_acceptance': False,
        })

    def test_audit_binds_exact_artifact_sources_abi_and_runtime_limits(self):
        record = json.loads(AUDIT.read_bytes())
        self.assertEqual(record['provenance']['static_artifact_sha256'],
            '43f6399ed713d0a4da4efa51bb67b2df73eb7652b07835cd8749d3ebc4ee82f0')
        self.assertEqual(record['provenance']['iso_sha256'],
            'df261c33bb782f4c0e5f4f6d742f2068cd018a98467fe325b6d41fe72dabef4f')
        self.assertEqual(record['mapping_function']['inherited_cfg_audit_sha256'],
            'dacb0de958e7ba90099a70b2e66f49756916ed3d42f4e70ac6280f7d4b6a571c')
        self.assertEqual(record['abi']['wlroots_runtime_sha256'],
            'a1223d6311c31c18a00e64169e869cce0a128457c0113701f68b65c0c6cb4147')
        self.assertEqual(record['abi']['wlroots_header_sha256'], causal.HEADER_SHA256)
        self.assertEqual(record['abi']['wlroots_source_sha256'], causal.SOURCE_SHA256)
        self.assertEqual(record['abi']['mango_header_sha256'], causal.MANGO_HEADER_SHA256)
        self.assertEqual(record['abi']['mango_source_sha256'], causal.MANGO_SOURCE_SHA256)
        self.assertIn('all six fresh paired boots must pass unchanged precision, enclosure and regression limits',
                      record['runtime_requirements'])

if __name__ == '__main__':
    unittest.main()
