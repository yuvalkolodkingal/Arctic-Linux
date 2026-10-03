#!/usr/bin/env python3
"""Fail closed on missing, malformed, duplicated or failed guest evidence."""
import argparse
import json
from pathlib import Path
import sys

CHECKS = ('identity', 'network', 'desktop', 'app-terminal', 'app-files',
          'app-browser', 'app-editor', 'app-settings', 'app-vlc')
PREFIX = 'ARCTIC-RELIABILITY '


def read_records(path):
    records = []
    for line in path.read_text(errors='replace').splitlines() if path.exists() else []:
        if line.startswith(PREFIX):
            value = json.loads(line[len(PREFIX):])
            if not isinstance(value, dict) or value.get('status') not in ('passed', 'failed', 'unrun'):
                raise ValueError('invalid guest record')
            records.append(value)
    return records


def evaluate(directory, upgrade=False):
    stages = [('live', 'serial-install.log', tuple(c for c in CHECKS if c != 'app-editor')),
              ('installed', 'serial-boot.log', CHECKS + (('upgrade',) if upgrade else ()))]
    if upgrade:
        stages.append(('installed', 'serial-upgrade.log', CHECKS + ('upgrade-transaction',)))
    results = []
    for stage, filename, checks in stages:
        try:
            records = read_records(directory / filename)
        except (ValueError, OSError) as exc:
            results.append(dict(stage=stage, check='evidence', status='failed', detail=str(exc)))
            records = []
        for check in checks:
            found = [r for r in records if r.get('stage') == stage and r.get('check') == check]
            status = found[0].get('status') if len(found) == 1 else 'unrun' if not found else 'failed'
            results.append(dict(stage=stage, check=check, status=status,
                                evidence=filename, detail=found or 'No complete guest record'))
    install = directory / 'serial-install.log'
    text = install.read_text(errors='replace') if install.exists() else ''
    markers = [line.strip() for line in text.splitlines() if line.startswith('ARCTIC-INSTALL-EXIT=')]
    results.append(dict(stage='install', check='installer-exit',
                        status='passed' if markers == ['ARCTIC-INSTALL-EXIT=0'] else 'failed' if markers else 'unrun',
                        detail=markers, evidence='serial-install.log'))
    harness = directory / 'test.log'
    log = harness.read_text(errors='replace') if harness.exists() else ''
    target = 'post-upgrade boot stage: exit 0' if upgrade else 'boot stage: exit 0'
    results.append(dict(stage='reboot', check='harness-exit',
                        status='passed' if any(line.endswith(target) for line in log.splitlines())
                        else 'failed' if 'boot stage: exit' in log else 'unrun',
                        evidence='test.log', detail=target))
    results.append(dict(stage='live', check='app-editor', status='unrun',
                        detail='Zed is downloaded at install time, not required in the live image'))
    for name in ('physical-hardware', 'visual-content-audio-calls', 'fedora-major-upgrade'):
        results.append(dict(stage=name, check='manual-or-unsupported', status='unrun'))
    if not upgrade:
        results.append(dict(stage='upgrade', check='previous-release', status='unrun'))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--upgrade', action='store_true')
    args = parser.parse_args()
    results = evaluate(args.directory, args.upgrade)
    args.directory.mkdir(parents=True, exist_ok=True)
    (args.directory / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    print('| Stage | Check | Result | Evidence |\n|---|---|---|---|')
    for r in results:
        print(f"| {r['stage']} | {r['check']} | {r['status']} | {r.get('evidence', 'manual / unsupported')} |")
    automated = [r for r in results if 'evidence' in r or r['check'] == 'evidence']
    return int(any(r['status'] != 'passed' for r in automated))


if __name__ == '__main__':
    sys.exit(main())
