#!/usr/bin/env python3
"""Return this workflow's qualified release to draft after a post-publish failure."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

REPOSITORY = 'yuvalkolodkingal/Arctic-Linux'
TAG = 'v1.2.1'
WORKFLOW = 'Publish the qualified retained Arctic ISO'
BRANCH = 'refs/heads/codex/publish-qualified-20261010'
SCHEMA = 'arctic-owned-qualified-release-v1'


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate release receipt field: ' + key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def api(path):
    return json.loads(subprocess.check_output(
        ['gh', 'api', 'repos/' + REPOSITORY + path], text=True, timeout=60))


def tag_target(call_api):
    obj = call_api('/git/ref/tags/' + TAG)['object']
    seen = set()
    for _ in range(10):
        require(type(obj) is dict and re.fullmatch('[0-9a-f]{40}', obj.get('sha', ''))
                and obj['sha'] not in seen, 'Release tag object is malformed or cyclic')
        seen.add(obj['sha'])
        if obj.get('type') == 'commit':
            return obj['sha']
        require(obj.get('type') == 'tag', 'Release tag resolves to a non-commit object')
        obj = call_api('/git/tags/' + obj['sha'])['object']
    raise RuntimeError('Annotated release tag chain exceeds verification bound')


def validate_receipt(value, environ):
    require(type(value) is dict and set(value) == {
        'schema', 'repository', 'workflow_run_id', 'workflow_run_attempt',
        'release_id', 'tag', 'target', 'assets'}, 'Owned release receipt fields differ')
    require(value['schema'] == SCHEMA and value['repository'] == REPOSITORY
            and value['tag'] == TAG and re.fullmatch('[0-9a-f]{40}', value['target']),
            'Owned release receipt identity differs')
    require(type(value['workflow_run_id']) is int and value['workflow_run_id'] > 0
            and type(value['workflow_run_attempt']) is int and value['workflow_run_attempt'] == 1
            and type(value['release_id']) is int and value['release_id'] > 0,
            'Owned release receipt run or release ID differs')
    require(environ.get('GITHUB_ACTIONS') == 'true'
            and environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and environ.get('GITHUB_REPOSITORY') == REPOSITORY
            and environ.get('GITHUB_WORKFLOW') == WORKFLOW
            and environ.get('GITHUB_REF') == BRANCH
            and environ.get('GITHUB_RUN_ID') == str(value['workflow_run_id'])
            and environ.get('GITHUB_RUN_ATTEMPT') == str(value['workflow_run_attempt']),
            'Release retraction requires the owning first-attempt publication run')
    assets = value['assets']
    require(type(assets) is dict and len(assets) == 5, 'Owned release asset inventory differs')
    for name, item in assets.items():
        require(type(name) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,199}', name)
                and type(item) is dict and set(item) == {'bytes', 'digest'}
                and type(item['bytes']) is int and item['bytes'] > 0
                and re.fullmatch(r'sha256:[0-9a-f]{64}', item['digest']),
                'Owned release asset receipt is malformed')
    return value


def retract(receipt_path, environ=None, call_api=api, run=subprocess.run):
    environ = os.environ if environ is None else environ
    receipt_path = Path(receipt_path)
    if not receipt_path.exists():
        print('No owned release receipt exists; no release was changed.', flush=True)
        return False
    require(receipt_path.is_file() and not receipt_path.is_symlink()
            and 0 < receipt_path.stat().st_size <= 16_384,
            'Owned release receipt is unsafe or oversized')
    receipt = validate_receipt(strict_json(receipt_path.read_text()), environ)
    release = call_api('/releases/' + str(receipt['release_id']))
    require(type(release) is dict and release.get('id') == receipt['release_id']
            and release.get('tag_name') == TAG
            and release.get('target_commitish') == receipt['target']
            and release.get('prerelease') is False
            and release.get('draft') in (True, False)
            and tag_target(call_api) == receipt['target'],
            'Actual release no longer matches the owned publication receipt')
    rows = release.get('assets')
    require(type(rows) is list and len(rows) == len(receipt['assets'])
            and all(type(item) is dict and {'name', 'size', 'digest', 'state'} <= set(item)
                    and item['state'] == 'uploaded' for item in rows),
            'Actual release asset inventory is malformed')
    actual_assets = {item['name']: {'bytes': item['size'], 'digest': item['digest']}
                     for item in rows}
    require(len(actual_assets) == len(rows) and actual_assets == receipt['assets'],
            'Actual release assets no longer match the owned publication receipt')
    if release['draft'] is True:
        print('Owned release is already a draft.', flush=True)
        return True
    run(['gh', 'release', 'edit', TAG, '--repo', REPOSITORY, '--draft=true'],
        check=True, timeout=60)
    changed = call_api('/releases/' + str(receipt['release_id']))
    require(changed.get('id') == receipt['release_id'] and changed.get('tag_name') == TAG
            and changed.get('target_commitish') == receipt['target']
            and changed.get('draft') is True,
            'Owned release could not be returned to draft')
    print('Returned the owned v1.2.1 release to draft after publication verification failed.',
          flush=True)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    retract(args.receipt)


if __name__ == '__main__':
    main()
