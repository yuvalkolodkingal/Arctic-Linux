#!/usr/bin/env python3
"""Summarize recorded guest measurements without guessing missing values."""
import argparse
import json
from pathlib import Path
import statistics


def summarize(path):
    stages = {}
    for line in path.read_text(errors='replace').splitlines():
        marker = 'ARCTIC-PERFORMANCE '
        if marker not in line:
            continue
        try:
            record = json.loads(line.split(marker, 1)[1])
        except json.JSONDecodeError:
            continue
        stage = stages.setdefault(record['stage'], {})
        stage[record['check']] = record['value']
    result = {}
    for stage, values in stages.items():
        summary = dict(complete=values.get('done', False), boot=values.get('boot'),
                       security=values.get('security'), installed_bytes=values.get('installed_bytes'))
        if 'identity' in values:
            summary['boot_id'] = values['identity']['boot_id']
        samples = values.get('idle_samples', [])
        summary['idle_sample_count'] = len(samples)
        if samples:
            metrics = {key: [s[key] for s in samples] for key in
                       ('process_pss_bytes', 'process_private_bytes', 'cpu_busy_percent')}
            metrics.update({key + '_bytes': [s['memory_bytes'][key] for s in samples]
                            for key in ('MemAvailable', 'Cached', 'SReclaimable')})
            for key in ('observer_cpu_percent_one_core', 'sample_elapsed_seconds'):
                if all(key in sample for sample in samples):
                    metrics[key] = [sample[key] for sample in samples]
            summary['idle'] = {key: dict(median=statistics.median(numbers), min=min(numbers),
                                       max=max(numbers)) for key, numbers in metrics.items()}
            summary['observer_pid'] = samples[0]['observer_pid']
            summary['top_processes'] = samples[-1]['top_processes']
        summary['timings_seconds'] = {key: value for key, value in values.items() if key.endswith('_seconds')}
        summary['unmeasured'] = {key: value for key, value in values.items() if key.endswith('_unmeasured')}
        summary['system_failed_units'] = values.get('system_failed_units')
        result[stage] = summary
    return dict(source=str(path), stages=result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('serial_logs', type=Path, nargs='+')
    args = parser.parse_args()
    print(json.dumps([summarize(path) for path in args.serial_logs], indent=2))
