#!/usr/bin/env python3
"""Record actual artifact-only image startup provenance, never performance acceptance."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


F = load('producer_fetch_contract', ROOT / 'tools/native-functional/fetch-image.py')
STARTUP = load('producer_startup_contract', ROOT / 'tools/lib/iso_startup.py')


def unique(pairs):
    result = {}
    for key, value in pairs:
        F.require(key not in result, 'Duplicate producer dispatch JSON field')
        result[key] = value
    return result


def request(environment):
    source = environment['GITHUB_SHA']
    F.require(environment['GITHUB_REPOSITORY'] == 'yuvalkolodkingal/Arctic-Linux'
              and environment['GITHUB_EVENT_NAME'] == 'workflow_dispatch'
              and environment['GITHUB_WORKFLOW_REF'].startswith(
                  'yuvalkolodkingal/Arctic-Linux/.github/workflows/iso.yml@'),
              'External producer must run the canonical dispatched ISO workflow')
    F.require(re.fullmatch('[1-9][0-9]*', environment['GITHUB_RUN_ID'])
              and environment['GITHUB_RUN_ATTEMPT'] == '1', 'External producer must be a fresh first attempt')
    raw = environment['PRODUCER_INPUTS_JSON']
    F.require(len(raw.encode()) <= 16_384, 'Oversized producer inputs')
    inputs = json.loads(raw, object_pairs_hook=unique)
    F.validate_external_inputs(inputs, source)
    event_path = Path(environment['GITHUB_EVENT_PATH'])
    F.require(event_path.is_file() and not event_path.is_symlink()
              and event_path.stat().st_size <= 1_000_000, 'Invalid dispatch event file')
    event = json.loads(event_path.read_bytes(), object_pairs_hook=unique)
    dispatched = event.get('inputs')
    F.require(isinstance(dispatched, dict) and set(dispatched) == set(F.INPUT_TYPES),
              'Actual dispatch input inventory differs')
    # The event payload preserves booleans as strings; the Actions inputs
    # context preserves their declared types. Bind both representations.
    for key, kind in F.INPUT_TYPES.items():
        value = dispatched[key]
        expected = ('true' if inputs[key] else 'false') if kind is bool else inputs[key]
        F.require(type(value) is str and value == expected, 'Actual dispatched input differs: ' + key)
    return dict(schema='arctic-producer-performance-receipt-v1',
                repository=environment['GITHUB_REPOSITORY'], workflow='.github/workflows/iso.yml',
                event=environment['GITHUB_EVENT_NAME'], source_sha=source,
                run_id=int(environment['GITHUB_RUN_ID']), run_attempt=1, mode=F.EXTERNAL_MODE,
                release_acceptance=False, inputs=inputs)


def write_receipt(environment, image_path, startup_root, output):
    receipt = request(environment)
    F.require(not output.exists() and not output.is_symlink(), 'Producer receipt output must be unused')
    F.require(image_path.is_file() and not image_path.is_symlink()
              and 0 < image_path.stat().st_size < 2_000_000_000, 'Actual producer ISO is absent or oversized')
    image = dict(name=image_path.name, bytes=image_path.stat().st_size, sha256=F.digest(image_path))
    checksum = image_path.with_name(image_path.name + '.sha256')
    F.require(checksum.is_file() and not checksum.is_symlink() and checksum.stat().st_size < 4096
              and checksum.read_text().strip().split() == [image['sha256'], image['name']],
              'Actual producer ISO checksum metadata differs')
    receipt['image'] = image
    receipt['startup_results'] = {}
    for lane, (firmware, mode) in F.STARTUP_LANES.items():
        serial = startup_root / lane / 'serial.log'
        F.require(serial.is_file() and not serial.is_symlink()
                  and not serial.parent.is_symlink() and 0 < serial.stat().st_size <= 10_000_000
                  and STARTUP.collection_complete(serial, mode), 'Actual startup collection did not pass: ' + lane)
        F.require([line for line in serial.read_text(errors='replace').splitlines()
                   if line.startswith('ARCTIC-STARTUP-PASS=')] == ['ARCTIC-STARTUP-PASS=' + mode],
                  'Actual startup collection contains contradictory mode results: ' + lane)
        receipt['startup_results'][lane] = dict(firmware=firmware, mode=mode, status='passed',
                                              serial_bytes=serial.stat().st_size, serial_sha256=F.digest(serial))
    raw = (json.dumps(receipt, sort_keys=True, indent=2) + '\n').encode()
    pinned = dict(image, run_id=receipt['run_id'], source_sha=receipt['source_sha'],
                  producer_mode=F.EXTERNAL_MODE, producer_receipt_sha256=hashlib.sha256(raw).hexdigest())
    F.read_receipt(raw, pinned)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as destination:
        destination.write(raw)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request-only', action='store_true')
    parser.add_argument('--iso', type=Path)
    parser.add_argument('--startup', type=Path, default=ROOT / 'out/test')
    parser.add_argument('--out', type=Path, default=ROOT / 'out/PERFORMANCE-PLAN.json')
    args = parser.parse_args()
    receipt = request(os.environ)
    F.require(subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], timeout=30).decode().strip()
              == receipt['source_sha'], 'Actual checked-out producer source differs')
    F.require(not subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain',
                                          '--untracked-files=no'], timeout=30), 'Producer tracked source is dirty')
    if args.request_only:
        F.require(args.iso is None, 'Request-only guard cannot write an image receipt')
        return
    F.require(args.iso is not None, 'Actual ISO path is required')
    write_receipt(os.environ, args.iso, args.startup, args.out)


if __name__ == '__main__':
    main()
