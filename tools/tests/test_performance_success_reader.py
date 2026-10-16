"""The success reader exports only the fixed contract-validated release fields."""
import importlib.util
import json
from pathlib import Path
import unittest

import performance_external_fixture as fixture


ROOT = Path(__file__).parents[2]
spec = importlib.util.spec_from_file_location(
    'performance_success_reader', ROOT / 'tools/performance/inspect-success-final-performance.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


def replay():
    entries, metadata = fixture.fixture()
    result = fixture.contract.validate_evidence(fixture.archive(entries), **metadata)
    result.update(execution_run_id=reader.RUN_ID, execution_source_sha=reader.SOURCE_SHA)
    return result


class BoundedSuccessProjection(unittest.TestCase):
    def test_projection_contains_only_bounded_metrics_and_binding_fields(self):
        result = reader.project(replay(), 'd' * 64, 'e' * 64)
        self.assertEqual(result['status'], 'regression_gate_passed')
        self.assertEqual(result['original_serials_replayed'], 6)
        self.assertEqual(len(result['metrics']), 22)
        self.assertEqual(len(result['limitations']), 9)
        self.assertLess(len(json.dumps(result, allow_nan=False).encode()), 32 * 1024)
        self.assertNotIn('identity', result)
        self.assertNotIn('package_attribution', result)
        self.assertNotIn('startup_observation', result)

    def test_failed_precision_regression_or_open_metric_is_rejected(self):
        for fault in ('precision', 'regression', 'metric'):
            value = replay()
            if fault == 'precision':
                value['comparison']['measurement_precision']['valid'] = False
            elif fault == 'regression':
                value['comparison']['status'] = 'regression_gate_failed'
            else:
                value['comparison']['metrics'][0]['metric'] = 'private_dynamic_name'
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                reader.project(value, 'd' * 64, 'e' * 64)

    def test_private_or_unbounded_shapes_cannot_enter_numeric_projection(self):
        for mutate in (
                lambda value: value['comparison']['metrics'][0]['per_boot']['candidate'].append(1),
                lambda value: value['comparison']['metrics'][0].update(percent_difference='secret'),
                lambda value: value['comparison']['limitations'].append('extra')):
            value = replay()
            mutate(value)
            with self.assertRaises(ValueError):
                reader.project(value, 'd' * 64, 'e' * 64)


if __name__ == '__main__':
    unittest.main()
