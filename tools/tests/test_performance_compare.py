"""Qualification must retain regressions and reject missing/changed evidence."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('performance_compare', Path(__file__).parents[1]/'performance/compare.py')
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)


def run(boot_id, kitty=2.63):
    samples = [dict(cpu_busy_percent=1.5, cpu_ticks_delta=200, cpu_idle_ticks_delta=197,
                    memory_bytes={'MemAvailable': 2_800_000_000}) for _ in range(30)]
    for sample in samples[::5]:
        sample.update(process_pss_bytes=1_000_000_000, process_private_bytes=830_000_000)
    result = dict(done=True, security='Enforcing', idle_samples=samples,
                  identity={'boot_id': boot_id, 'sampler': comparison.SAMPLER}, observer_source_sha256='a' * 64,
                  measurement_conditions={'initial_keep_awake': {'on': False}}, keep_awake_restored={'on': False},
                  measured_payload={'arctic_shell': 'arctic-shell-0.2.0-1.preview.gitabc1234',
                                    'catalog_sha256': 'b' * 64 + '  /usr/share/arctic/shell/AppsService.qml'},
                  boot={'analyze': 'Startup finished in 1s (kernel) + 2s (initrd) + 7s (userspace) = 10s'},
                  installed_bytes='6000000000 /', fish_seconds={'median': .3}, bash_seconds={'median': .8},
                  shell_ipc_seconds={'median': .5})
    records = ['kitty-0:0.47.1-1.fc44.x86_64', 'mesa-libEGL-0:26.2.1-1.fc44.x86_64']
    result['rpm_inventory'] = dict(nevra=records,
        sha256=hashlib.sha256(('\n'.join(records)+'\n').encode()).hexdigest(),
        graphics_text_and_apps=records)
    for app in ('kitty', 'org.gnome.nautilus', 'zen'):
        result['precondition_' + app] = {'persistent_hold_seconds': 45}
        first = kitty if app == 'kitty' else 15
        warm = [3.2, 3.3] if app == 'kitty' else [15, 16]
        result['startup_' + app + '_seconds'] = dict(first=first, warm=warm,
            observer=comparison.MAPPING_OBSERVER, poll_sleep_seconds=.001,
            observation_bounds=[dict(lower_seconds=value-.001, upper_seconds=value,
                interval_seconds=.001, observer=comparison.MAPPING_OBSERVER) for value in [first, *warm]])
    return result


class QualificationTest(unittest.TestCase):
    def test_compact_report_retains_brackets_gates_and_hash_of_complete_raw_trace(self):
        runs = {'baseline': [run('b'+str(n)) for n in range(3)],
                'candidate': [run('c'+str(n)) for n in range(3)]}
        original = comparison.compare(runs)
        trace = [dict(socket_seconds=.00012, parent_seconds=.02, uid=1000)] * 10000
        for group in runs.values():
            for boot in group:
                for app in ('kitty', 'org.gnome.nautilus', 'zen'):
                    for bound in boot['startup_'+app+'_seconds']['observation_bounds']:
                        bound['query_roundtrips'] = trace
        large_input = json.dumps(runs)
        report = comparison.compare(runs)
        self.assertGreater(len(large_input), 4*1024*1024)
        self.assertLess(len(json.dumps(report)), 4*1024*1024)
        for key in ('status', 'metrics', 'measurement_precision'):
            self.assertEqual(report[key], original[key])
        bound = report['startup_observation']['candidate'][0]['kitty']['observation_bounds'][0]
        self.assertEqual(bound['query_roundtrip_summary']['count'], len(trace))
        self.assertEqual(bound['query_roundtrip_summary']['sha256'], hashlib.sha256(
            json.dumps(trace, sort_keys=True, separators=(',', ':')).encode()).hexdigest())
        self.assertIs(runs['candidate'][0]['startup_kitty_seconds']['observation_bounds'][0]['query_roundtrips'], trace)

    def test_legacy_memory_samples_must_remain_complete_and_paired(self):
        runs={'baseline':[run('b'+str(n)) for n in range(3)],'candidate':[run('c'+str(n)) for n in range(3)]}
        for sample in runs['candidate'][0]['idle_samples'][5::5]:sample.pop('process_private_bytes')
        with self.assertRaises(ValueError):comparison.compare(runs)

    def test_raw_memory_boolean_and_malformed_bytes_cannot_become_false_savings(self):
        for name in ('process_pss_bytes','process_private_bytes','MemAvailable'):
            for value in (True,False,-1,0,float('nan'),float('inf'),.5,2**64,'1000'):
                runs = {'baseline':[run('b'+str(n)) for n in range(3)],
                        'candidate':[run('c'+str(n)) for n in range(3)]}
                for record in runs['candidate']:
                    for sample in record['idle_samples']:
                        if name=='MemAvailable':sample['memory_bytes'][name]=value
                        elif name in sample:sample[name]=value
                with self.subTest(name=name,value=value),self.assertRaises(ValueError):comparison.compare(runs)

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
                    sample['process_pss_bytes'] = int(sample['process_pss_bytes'] * factor)
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

    def test_coarse_or_legacy_observer_cannot_qualify_even_without_regression(self):
        for fault in ('coarse', 'legacy', 'too_large_relative_to_fast_app'):
            runs = {'baseline': [run('b' + str(n)) for n in range(3)],
                    'candidate': [run('c' + str(n)) for n in range(3)]}
            observation = runs['candidate'][0]['startup_kitty_seconds']['observation_bounds'][1]
            if fault == 'legacy':
                runs['candidate'][0]['identity']['sampler'] = 'cpu-30-pss-6-v5-native-backend'
            elif fault == 'coarse':
                observation.update(lower_seconds=observation['upper_seconds']-.06, interval_seconds=.06)
            else:
                timing = runs['candidate'][0]['startup_kitty_seconds']
                timing['warm'][0] = .05
                observation.update(lower_seconds=.048, upper_seconds=.05, interval_seconds=.002)
            result = comparison.compare(runs)
            with self.subTest(fault=fault):
                self.assertEqual(result['status'], 'measurement_precision_gate_failed')
                self.assertFalse(result['measurement_precision']['valid'])

    def test_invalid_precision_does_not_erase_regression(self):
        runs = {'baseline': [run('b' + str(n)) for n in range(3)],
                'candidate': [run('c' + str(n), 3.5) for n in range(3)]}
        runs['candidate'][0]['identity']['sampler'] = 'legacy'
        result = comparison.compare(runs)
        self.assertEqual(result['status'], 'regression_gate_failed')
        self.assertFalse(result['measurement_precision']['valid'])
        self.assertTrue(next(r for r in result['metrics'] if r['metric'] == 'kitty_first_mapped_after_preconditioning')['regression'])

    def test_missing_malformed_and_inconsistent_brackets_fail_closed(self):
        for fault in ('missing', 'negative', 'nan', 'wrong_upper', 'wrong_width'):
            runs = {'baseline': [run('b' + str(n)) for n in range(3)],
                    'candidate': [run('c' + str(n)) for n in range(3)]}
            timing = runs['candidate'][0]['startup_kitty_seconds']
            observation = timing['observation_bounds'][0]
            if fault == 'missing':
                timing['observation_bounds'].pop()
            elif fault == 'negative':
                observation['lower_seconds'] = -1
            elif fault == 'nan':
                observation['upper_seconds'] = float('nan')
            elif fault == 'wrong_upper':
                observation['upper_seconds'] += .1
            else:
                observation['interval_seconds'] += .1
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                comparison.compare(runs)

    def test_rpm_inventory_changes_and_invalid_digests_fail_closed(self):
        for fault in ('missing', 'digest', 'sort', 'within_image_update'):
            runs = {'baseline': [run('b' + str(n)) for n in range(3)],
                    'candidate': [run('c' + str(n)) for n in range(3)]}
            inventory = runs['candidate'][0]['rpm_inventory']
            if fault == 'missing':
                runs['candidate'][0].pop('rpm_inventory')
            elif fault == 'digest':
                inventory['sha256'] = '0' * 64
            elif fault == 'sort':
                inventory['nevra'].reverse()
            else:
                inventory['nevra'][1] = 'mesa-libEGL-0:26.2.2-1.fc44.x86_64'
                inventory['sha256'] = hashlib.sha256(('\n'.join(inventory['nevra'])+'\n').encode()).hexdigest()
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                comparison.compare(runs)

    def test_between_image_versions_are_reported_without_causal_claim_or_gate_exemption(self):
        runs = {'baseline': [run('b' + str(n)) for n in range(3)],
                'candidate': [run('c' + str(n), 3.5) for n in range(3)]}
        for run_ in runs['candidate']:
            inventory = run_['rpm_inventory']
            inventory['nevra'][1] = 'mesa-libEGL-0:26.2.2-1.fc44.x86_64'
            inventory['sha256'] = hashlib.sha256(('\n'.join(inventory['nevra'])+'\n').encode()).hexdigest()
        result = comparison.compare(runs)
        self.assertEqual(result['status'], 'regression_gate_failed')
        self.assertEqual(result['package_attribution']['baseline_only'], ['mesa-libEGL-0:26.2.1-1.fc44.x86_64'])
        self.assertEqual(result['package_attribution']['candidate_only'], ['mesa-libEGL-0:26.2.2-1.fc44.x86_64'])

    def test_cpu_zero_median_does_not_hide_busy_ticks_and_bad_counters_fail(self):
        runs = {'baseline': [run('b' + str(n)) for n in range(3)],
                'candidate': [run('c' + str(n)) for n in range(3)]}
        for group in runs.values():
            for run_ in group:
                for sample in run_['idle_samples'][1:]:
                    sample.update(cpu_busy_percent=0, cpu_idle_ticks_delta=200)
        result = comparison.compare(runs)
        metric = next(row for row in result['metrics'] if row['metric'] == 'cpu_busy_percent')
        self.assertEqual(metric['median'], dict(baseline=0, candidate=0))
        self.assertEqual(result['idle_cpu_validity']['baseline'][0]['busy_ticks'], 3)
        self.assertEqual(result['idle_cpu_validity']['baseline'][0]['zero_busy_samples'], 29)
        for fault in ('missing', 'frozen', 'backwards', 'greater_idle', 'forged_percent'):
            sample = dict(cpu_busy_percent=1.5, cpu_ticks_delta=200, cpu_idle_ticks_delta=197)
            if fault == 'missing':
                sample.pop('cpu_ticks_delta')
            elif fault == 'frozen':
                sample.update(cpu_ticks_delta=0, cpu_idle_ticks_delta=0)
            elif fault == 'backwards':
                sample['cpu_idle_ticks_delta'] = -1
            elif fault == 'greater_idle':
                sample['cpu_idle_ticks_delta'] = 201
            else:
                sample['cpu_busy_percent'] = 0
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                comparison.cpu_validity(dict(idle_samples=[sample]))

    def test_threshold_enclosure_blocks_near_boundary_false_pass_without_fabricating_regression(self):
        runs = {'baseline': [run('b' + str(n)) for n in range(3)],
                'candidate': [run('c' + str(n)) for n in range(3)]}
        for name, group in runs.items():
            upper, lower = (1., .998) if name == 'baseline' else (1.099, 1.098)
            for run_ in group:
                timing = run_['startup_kitty_seconds']
                timing.update(first=upper, warm=[upper, upper], observation_bounds=[
                    dict(lower_seconds=lower, upper_seconds=upper, interval_seconds=upper-lower,
                         observer=comparison.MAPPING_OBSERVER) for _ in range(3)])
        result = comparison.compare(runs)
        self.assertEqual(result['status'], 'measurement_precision_gate_failed')
        self.assertTrue(result['measurement_precision']['valid'])
        self.assertFalse(result['measurement_precision']['threshold_enclosure_valid'])
        metric = next(r for r in result['metrics'] if r['metric'] == 'kitty_subsequent_mapped')
        self.assertFalse(metric['regression'])
        self.assertAlmostEqual(metric['percent_difference'], 9.9)
        self.assertGreater(metric['observation_enclosure']['possible_percent_difference_upper'], 10)

    def test_enclosure_exact_boundary_passes_just_over_fails_and_zero_lower_is_finite(self):
        runs = {'baseline': [run('b' + str(n)) for n in range(3)],
                'candidate': [run('c' + str(n)) for n in range(3)]}
        for run_ in runs['baseline']:
            timing = run_['startup_kitty_seconds']
            timing.update(first=1., warm=[1., 1.], observation_bounds=[
                dict(lower_seconds=.999, upper_seconds=1., interval_seconds=.001,
                     observer=comparison.MAPPING_OBSERVER) for _ in range(3)])
        for extra, expected in ((0, 'regression_gate_passed'), (.000001, 'measurement_precision_gate_failed')):
            upper = .999 * 1.10 + extra
            for run_ in runs['candidate']:
                timing = run_['startup_kitty_seconds']
                timing.update(first=upper, warm=[upper, upper], observation_bounds=[
                    dict(lower_seconds=upper-.001, upper_seconds=upper, interval_seconds=.001,
                         observer=comparison.MAPPING_OBSERVER) for _ in range(3)])
            with self.subTest(extra=extra):
                self.assertEqual(comparison.compare(runs)['status'], expected)
        for run_ in runs['baseline']:
            for observation in run_['startup_kitty_seconds']['observation_bounds']:
                observation.update(lower_seconds=0, interval_seconds=observation['upper_seconds'])
        result = comparison.compare(runs)
        self.assertEqual(result['status'], 'measurement_precision_gate_failed')
        metric = next(r for r in result['metrics'] if r['metric'] == 'kitty_subsequent_mapped')
        self.assertIsNone(metric['observation_enclosure']['possible_percent_difference_upper'])
        json.dumps(result, allow_nan=False)

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
