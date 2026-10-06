#!/usr/bin/env python3
"""Fail closed on incomplete paired runs; report effects without claiming speedups."""
import argparse
import json
import math
from pathlib import Path
import re
import statistics


def read_run(path):
    records = {}
    for line in path.read_text(errors='replace').splitlines():
        if 'ARCTIC-PERFORMANCE ' not in line:
            continue
        value = json.loads(line.split('ARCTIC-PERFORMANCE ', 1)[1])
        if value['stage'] == 'installed':
            records[value['check']] = value['value']
    if records.get('done') is not True or records.get('security') != 'Enforcing':
        raise ValueError(f'{path}: incomplete probe or SELinux not enforcing')
    samples = records.get('idle_samples', [])
    if len(samples) != 30 or sum('process_pss_bytes' in s for s in samples) != 6:
        raise ValueError(f'{path}: missing CPU/PSS samples')
    if records['measurement_conditions']['initial_keep_awake'].get('on') is not False:
        raise ValueError(f'{path}: non-default initial Keep awake state')
    if records['keep_awake_restored'].get('on') is not False:
        raise ValueError(f'{path}: Keep awake was not restored')
    for app in ('kitty', 'org.gnome.nautilus', 'zen'):
        if records['precondition_' + app]['persistent_hold_seconds'] != 45:
            raise ValueError(f'{path}: inconsistent mapped-app preconditioning')
    return records


def boot_seconds(run):
    text = run['boot']['analyze'].split('=', 1)[1].splitlines()[0]
    parts = re.findall(r'([0-9]+(?:\.[0-9]+)?)\s*(min|ms|us|µs|h|s)', text)
    if not parts:
        raise ValueError('Unrecognized systemd boot timing: ' + text)
    factors = {'h': 3600, 'min': 60, 's': 1, 'ms': .001, 'us': .000001, 'µs': .000001}
    return sum(float(value) * factors[unit] for value, unit in parts)


def compare(runs):
    if set(runs) != {'baseline', 'candidate'} or any(len(group) != 3 for group in runs.values()):
        raise ValueError('Exactly three completed boots of each image are required')
    all_runs = [r for group in runs.values() for r in group]
    if len({r['identity']['boot_id'] for r in all_runs}) != 6:
        raise ValueError('Repeated/missing boot IDs')
    if len({r['observer_source_sha256'] for r in all_runs}) != 1:
        raise ValueError('Different observer sources')
    metrics = [('boot_systemd_total', 'seconds', boot_seconds, .10),
               ('root_filesystem_du_allocation', 'bytes', lambda r: int(r['installed_bytes'].split()[0]), None)]
    for name in ('process_pss_bytes', 'process_private_bytes', 'cpu_busy_percent'):
        metrics.append((name, 'percent' if name == 'cpu_busy_percent' else 'bytes',
                        lambda r, name=name: statistics.median(s[name] for s in r['idle_samples'] if name in s),
                        None if name == 'cpu_busy_percent' else .05))
    metrics.append(('MemAvailable_bytes', 'bytes',
                    lambda r: statistics.median(s['memory_bytes']['MemAvailable'] for s in r['idle_samples']), None))
    for app in ('fish', 'bash', 'shell_ipc'):
        metrics.append((app + '_launch_or_roundtrip', 'seconds',
                        lambda r, app=app: r[app + '_seconds']['median'], .10))
    for app in ('kitty', 'org.gnome.nautilus', 'zen'):
        metrics.append((app + '_first_mapped_after_preconditioning', 'seconds',
                        lambda r, app=app: r['startup_' + app + '_seconds']['first'], .10))
        metrics.append((app + '_subsequent_mapped', 'seconds',
                        lambda r, app=app: statistics.median(r['startup_' + app + '_seconds']['warm']), .10))
    results = []
    for name, unit, extract, gate in metrics:
        values = {name: [extract(r) for r in group] for name, group in runs.items()}
        if any(not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0
               or (unit != 'percent' and value == 0) for group in values.values() for value in group):
            raise ValueError('Invalid or missing numerical measurement: ' + name)
        median = {name: statistics.median(numbers) for name, numbers in values.items()}
        ranges = {name: [min(numbers), max(numbers)] for name, numbers in values.items()}
        delta = median['candidate'] / median['baseline'] - 1 if median['baseline'] else None
        overlap = max(v[0] for v in ranges.values()) <= min(v[1] for v in ranges.values())
        results.append(dict(metric=name, unit=unit, per_boot=values, median=median, range=ranges,
                            percent_difference=100 * delta if delta is not None else None,
                            range_overlap=overlap, regression_threshold_percent=100 * gate if gate else None,
                            regression=gate is not None and median['candidate'] > median['baseline'] * (1 + gate)
                            and not math.isclose(median['candidate'], median['baseline'] * (1 + gate), rel_tol=1e-12)))
    return dict(status='regression_gate_failed' if any(r['regression'] for r in results) else 'regression_gate_passed',
                metrics=results, identity={name: [r['identity'] for r in group] for name, group in runs.items()},
                measured_payload={name: [r['measured_payload'] for r in group] for name, group in runs.items()},
                startup_observation={name: [{app: r['startup_' + app + '_seconds'] for app in
                    ('kitty', 'org.gnome.nautilus', 'zen')} for r in group] for name, group in runs.items()},
                installed_mount_allocations={name: [r.get('installed_mount_allocations') for r in group]
                                             for name, group in runs.items()},
                limitations=['Three boots per image; distributions are small and no confidence interval is implied',
                             '45-second mapped-app preconditioning; these are warmed launches, not first-ever cold starts',
                             'KVM/QEMU with virtual graphics; no physical laptop or gaming performance claim',
                             'Mapped-window timings are sampled with 10ms sleeps plus IPC cost; each observation interval is reported',
                             'Passing a regression gate does not establish a substantial optimization'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-log', type=Path, action='append', required=True)
    parser.add_argument('--candidate-log', type=Path, action='append', required=True)
    parser.add_argument('--candidate-commit', required=True)
    parser.add_argument('--candidate-catalog-sha256', required=True)
    parser.add_argument('--candidate-battery-sha256', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    try:
        runs = {name: [read_run(path) for path in getattr(args, name + '_log')] for name in ('baseline', 'candidate')}
        for run in runs['candidate']:
            payload = run['measured_payload']
            if '.git' + args.candidate_commit not in payload['arctic_shell']:
                raise ValueError('Candidate RPM source differs from requested commit')
            if payload['catalog_sha256'].split()[0] != args.candidate_catalog_sha256:
                raise ValueError('Candidate catalog source changed or was replaced by an update')
            if payload['battery_sha256'].split()[0] != args.candidate_battery_sha256:
                raise ValueError('Candidate battery source changed or was replaced by an update')
        result = compare(runs)
    except Exception as error:
        result = dict(status='incomplete_or_inconsistent_measurement', error=str(error))
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'regression_gate_passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
