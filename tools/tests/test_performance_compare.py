"""Qualification must retain regressions and reject missing/changed evidence."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('performance_compare', Path(__file__).parents[1]/'performance/compare.py')
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)


def run(boot_id, kitty=2.63):
    samples = [dict(cpu_busy_percent=1.5, memory_bytes={'MemAvailable': 2_800_000_000}) for _ in range(30)]
    for sample in samples[::5]:
        sample.update(process_pss_bytes=1_000_000_000, process_private_bytes=830_000_000)
    result = dict(done=True, security='Enforcing', idle_samples=samples,
                  identity={'boot_id': boot_id}, observer_source_sha256='a' * 64,
                  measurement_conditions={'initial_keep_awake': {'on': False}}, keep_awake_restored={'on': False},
                  measured_payload={'arctic_shell': 'arctic-shell-0.2.0-1.preview.gitabc1234',
                                    'catalog_sha256': 'b' * 64 + '  /usr/share/arctic/shell/AppsService.qml'},
                  boot={'analyze': 'Startup finished in 1s (kernel) + 2s (initrd) + 7s (userspace) = 10s'},
                  installed_bytes='6000000000 /', fish_seconds={'median': .3}, bash_seconds={'median': .8},
                  shell_ipc_seconds={'median': .5})
    for app in ('kitty', 'org.gnome.nautilus', 'zen'):
        result['precondition_' + app] = {'persistent_hold_seconds': 45}
        result['startup_' + app + '_seconds'] = {'first': kitty if app == 'kitty' else 15,
                                               'warm': [3.2, 3.3] if app == 'kitty' else [15, 16]}
    return result


class QualificationTest(unittest.TestCase):
    def test_exact_boundaries_pass_and_just_over_fails(self):
        baseline = [run('b' + str(n)) for n in range(3)]
        for factor, expected in ((1.10, 'regression_gate_passed'), (1.10001, 'regression_gate_failed')):
            candidate = [run('c' + str(n)) for n in range(3)]
            for value in candidate:
                value['fish_seconds']['median'] = baseline[0]['fish_seconds']['median'] * factor
            self.assertEqual(comparison.compare(dict(baseline=baseline, candidate=candidate))['status'], expected)
        for factor, expected in ((1.05, 'regression_gate_passed'), (1.05001, 'regression_gate_failed')):
            candidate = [run('c' + str(n)) for n in range(3)]
            for value in candidate:
                for sample in value['idle_samples'][::5]:
                    sample['process_pss_bytes'] *= factor
            self.assertEqual(comparison.compare(dict(baseline=baseline, candidate=candidate))['status'], expected)

    def test_kitty_regression_is_retained_without_fabricated_speedup(self):
        runs = {'baseline': [run('b' + str(n), k) for n, k in enumerate((2.59, 2.63, 2.87))],
                'candidate': [run('c' + str(n), k) for n, k in enumerate((3.147, 3.183, 3.29))]}
        result = comparison.compare(runs)
        self.assertEqual(result['status'], 'regression_gate_failed')
        kitty = next(row for row in result['metrics'] if row['metric'] == 'kitty_first_mapped_after_preconditioning')
        self.assertTrue(kitty['regression'])
        self.assertFalse(kitty['range_overlap'])
        self.assertGreater(kitty['percent_difference'], 20)

    def test_missing_runs_duplicate_boots_and_changed_observers_are_rejected(self):
        valid = {'baseline': [run('b' + str(n)) for n in range(3)],
                 'candidate': [run('c' + str(n)) for n in range(3)]}
        for fault in ('missing', 'duplicate', 'observer', 'nan'):
            runs = copy.deepcopy(valid)
            if fault == 'missing':
                runs['candidate'].pop()
            elif fault == 'duplicate':
                runs['candidate'][0]['identity']['boot_id'] = 'b0'
            elif fault == 'observer':
                runs['candidate'][0]['observer_source_sha256'] = 'c' * 64
            else:
                runs['candidate'][0]['fish_seconds']['median'] = float('nan')
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                comparison.compare(runs)
        self.assertEqual(comparison.compare(valid)['status'], 'regression_gate_passed')

    def test_incomplete_security_sample_and_keep_awake_failures_do_not_disappear(self):
        valid = run('unique')
        faults = [dict(done=False), dict(security='Permissive'), dict(idle_samples=valid['idle_samples'][:-1]),
                  dict(keep_awake_restored={'on': True})]
        for fault in faults:
            records = dict(valid, **fault)
            with tempfile.TemporaryDirectory() as tmp:
                log = Path(tmp) / 'serial.log'
                log.write_text('\n'.join('ARCTIC-PERFORMANCE ' + json.dumps(
                    dict(stage='installed', check=check, value=value)) for check, value in records.items()))
                with self.subTest(fault=fault), self.assertRaises(ValueError):
                    comparison.read_run(log)
