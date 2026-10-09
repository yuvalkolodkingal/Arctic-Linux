#!/usr/bin/env python3
"""Prepare a frozen external plan from clean image and execution checkouts."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def git(root, *args, binary=False):
    return subprocess.check_output(['git', '-C', str(root), *args],
                                   text=not binary, timeout=120)


def checkout(path, expected=None):
    root = path.resolve(strict=True)
    require(root.is_dir() and git(root, 'rev-parse', '--show-toplevel').strip() == str(root),
            'Requires an exact Git checkout root')
    require(not git(root, 'status', '--porcelain', '--untracked-files=all').strip(),
            'Source checkout is not clean')
    head = git(root, 'rev-parse', 'HEAD').strip()
    require(expected is None or head == expected, 'Image source checkout differs from the pinned producer')
    return root


def tracked_hashes(root, names):
    result = {}
    for name in sorted(names):
        path = root / name
        require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root),
                'Unsafe or missing tracked plan source: ' + name)
        data = path.read_bytes()
        require(data == git(root, 'show', 'HEAD:' + name, binary=True),
                'Plan source differs from the clean tracked blob: ' + name)
        result[name] = hashlib.sha256(data).hexdigest()
    return result


def image_pin(content):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate image pin key: ' + key)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Non-finite image pin number: ' + value)
    return json.loads(content, object_pairs_hook=pairs, parse_constant=invalid)


def compose(source, execution, image, *, ready=False):
    require(type(image) is dict and type(ready) is bool, 'Invalid plan input types')
    source = checkout(source, image['source_sha'])
    execution = checkout(execution)
    contract_path = execution / 'tools/performance/contract.py'
    contract_hash = tracked_hashes(execution, {'tools/performance/contract.py'})['tools/performance/contract.py']
    spec = importlib.util.spec_from_file_location('frozen_plan_contract', contract_path)
    contract = importlib.util.module_from_spec(spec)
    contract_bytes = contract_path.read_bytes()
    require(hashlib.sha256(contract_bytes).hexdigest() == contract_hash, 'Plan contract changed before loading')
    exec(compile(contract_bytes, str(contract_path), 'exec'), contract.__dict__)
    source_files = tracked_hashes(source, contract.CANDIDATE_SOURCE_FILES)
    files = tracked_hashes(execution, contract.EXECUTION_FILES)
    observer = contract.observer_hashes(execution)
    plan = dict(schema='arctic-external-paired-plan-v1', ready=ready,
                release_acceptance=False, performance_mode=contract.MODE,
                image=image, baseline=contract.BASELINE,
                candidate_source_files=source_files, observer=observer,
                execution_files=files)
    contract.validate_plan(plan, candidate_source_files=source_files,
                           execution_files=files, observer=observer)
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--execution', type=Path, required=True)
    parser.add_argument('--image-pin', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--ready', action='store_true',
                        help='Mark the plan reviewed; does not activate or publish anything')
    args = parser.parse_args()
    require(not args.out.exists() and not args.out.is_symlink(), 'Plan output must be unused')
    plan = compose(args.source, args.execution, image_pin(args.image_pin.read_text()), ready=args.ready)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x') as output:
        output.write(json.dumps(plan, indent=2) + '\n')


if __name__ == '__main__':
    main()
