#!/usr/bin/env python3
"""Replay a separately frozen paired lane without changing its numeric gates."""
import hashlib
import json
from pathlib import Path
import re
import tempfile

MODE = 'frozen-external-paired-v1'
WORKFLOW = '.github/workflows/paired-candidate-20261009.yml'
MARKER = '.github/qualification-20261010.performance'
MANIFEST = 'tools/performance/execution-manifest.json'
ARTIFACT = 'external-paired-performance'
BRANCH = 'codex/qualification-dispatch-20261010'
BASELINE = dict(name='Arctic-Linux-1.2-x86_64.iso', bytes=2322073600,
    sha256='054db5c43cae47fb60f8f43efc8e052b569aa1b14e8f15adcb15cdc48265182f',
    profile_sha256='e6b9aa317521bdaaaf343629bc5de8b914b0a5f58387a0c9fe31754f17c0d20d')
CANDIDATE_SOURCE_FILES = frozenset(('profiles/ci/offline.toml', 'shell/AppsService.qml', 'shell/BatteryService.qml'))
EXECUTION_FILES = frozenset((WORKFLOW, 'tools/performance/qualification.py',
    'tools/performance/contract.py', 'tools/performance/compose-plan.py',
    'tools/performance/run-paired.py', 'tools/performance/compare.py',
    'tools/performance/compose-paired-probe.py', 'tools/performance/guest.py',
    'tools/performance/causal.py', 'tools/performance/prepare-vm-tools.sh',
    'tools/performance/fixtures/v1.2-offline.toml', 'tools/performance/producer-receipt.py',
    'tools/test-install.sh', 'tools/lib/container.sh', 'tools/lib/vmtest.py',
    'tools/native-functional/fetch-image.py', 'tools/native-functional/screen-evidence.py'))
ORDER = (('baseline', 1), ('candidate', 1), ('candidate', 2),
         ('baseline', 2), ('baseline', 3), ('candidate', 3))


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(content):
    return hashlib.sha256(content).hexdigest()


def same(left, right):
    """JSON equality which never equates a boolean with a numeric gate input."""
    return json.dumps(left, sort_keys=True, separators=(',', ':'), allow_nan=False) == json.dumps(
        right, sort_keys=True, separators=(',', ':'), allow_nan=False)


def observer_hashes_from_sources(guest_bytes, causal_bytes):
    """Reconstruct the pinned composer's exact output, without executing sources."""
    source, causal = guest_bytes.decode('utf-8'), causal_bytes.decode('utf-8')
    require('\r' not in source and '\r' not in causal, 'Observer sources must use LF newlines')
    combined = digest(guest_bytes + b'\0' + causal_bytes)
    frozen = ('#!/usr/bin/env python3\nimport sys, types\n'
        'causal = types.ModuleType("arctic_performance_causal")\n'
        'causal.__file__ = __file__\n'
        'sys.modules[causal.__name__] = causal\n'
        f'exec(compile({causal!r}, __file__, "exec"), causal.__dict__)\n'
        'measurement = {"__name__": "arctic_measurement", "__file__": __file__}\n'
        f'exec(compile({source!r}, __file__, "exec"), measurement)\n'
        'if sys.argv[1] == "installed":\n'
        f'    measurement["emit"]("observer_source_sha256", {combined!r})\n'
        '    measurement["main"](preconditioned=True, causal_precision=True)\n'
        'else:\n'
        '    print("ARCTIC-PERFORMANCE-SKIPPED: live stage; installed comparison only", flush=True)\n').encode()
    return dict(source_sha256=combined, frozen_sha256=digest(frozen))


def observer_hashes(root):
    root = Path(root)
    result = observer_hashes_from_sources((root/'tools/performance/guest.py').read_bytes(),
                                         (root/'tools/performance/causal.py').read_bytes())
    result['comparator_sha256'] = digest((root/'tools/performance/compare.py').read_bytes())
    return result


def validate_plan(plan, *, candidate_source_files, execution_files, observer):
    require(type(plan) is dict and set(plan) == {'schema', 'ready', 'release_acceptance',
        'performance_mode', 'image', 'baseline', 'candidate_source_files', 'observer', 'execution_files'},
        'External paired plan fields differ')
    require(plan['schema'] == 'arctic-external-paired-plan-v1' and type(plan['ready']) is bool
        and plan['release_acceptance'] is False and plan['performance_mode'] == MODE,
        'External paired plan mode/readiness differs')
    image = plan['image']
    require(type(image) is dict and image.get('producer_mode') == MODE
        and re.fullmatch('[0-9a-f]{40}', image.get('source_sha', ''))
        and re.fullmatch('[0-9a-f]{64}', image.get('sha256', ''))
        and re.fullmatch('[0-9a-f]{64}', image.get('producer_receipt_sha256', ''))
        and type(image.get('bytes')) is int and 0 < image['bytes'] < 2_000_000_000,
        'External paired image identity differs')
    require(same(plan['baseline'], BASELINE), 'Immutable original baseline differs')
    for name, declared, actual, keys in (
        ('candidate sources', plan['candidate_source_files'], candidate_source_files, CANDIDATE_SOURCE_FILES),
        ('execution sources', plan['execution_files'], execution_files, EXECUTION_FILES),
        ('observer', plan['observer'], observer, {'source_sha256', 'frozen_sha256', 'comparator_sha256'})):
        require(type(declared) is dict and set(declared) == keys and declared == actual
            and all(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) for value in declared.values()),
            'Pinned ' + name + ' differ')
    require(plan['execution_files']['tools/performance/compare.py'] == plan['observer']['comparator_sha256']
        and plan['execution_files']['tools/performance/fixtures/v1.2-offline.toml'] == BASELINE['profile_sha256'],
        'Comparator/baseline profile source pins differ')
    return plan


def parse_json(content):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Non-finite JSON number: ' + value)
    return json.loads(content, object_pairs_hook=pairs, parse_constant=invalid)


def required_files():
    result = {'status.json', 'comparison.json', 'producer-receipt.json', 'observer-source.txt',
              'vm-base-image-id.txt', 'vm-prepared-image-id.txt'}
    for image in ('baseline', 'candidate'):
        result |= {image + '-install-harness.log', image + '/serial-install.log', image + '/vm-toolchain.txt'}
    for image, boot in ORDER:
        result |= {'runs/' + image + '/' + str(boot) + '/' + name for name in
            ('serial-boot.log', 'harness.log', 'performance-context.json', 'vm-toolchain.txt')}
    return result


def validate_evidence(archive, *, plan, plan_sha256, image, execution_source_sha,
                      reviewed_parent_sha, execution_run_id, comparator, producer_receipt):
    """Verify full original inputs and independently recompute all six boots."""
    validate_plan(plan, candidate_source_files=plan['candidate_source_files'],
        execution_files=plan['execution_files'], observer=plan['observer'])
    require(plan['ready'] is True and same(plan['image'], image), 'Unready/mismatched execution plan')
    for value in (execution_source_sha, reviewed_parent_sha):
        require(type(value) is str and re.fullmatch('[0-9a-f]{40}', value), 'Invalid execution commit')
    require(type(execution_run_id) is int and execution_run_id > 0
        and re.fullmatch('[0-9a-f]{64}', plan_sha256), 'Invalid execution run/plan identity')
    entries = [entry for entry in archive.infolist() if not entry.is_dir()]
    names = [entry.filename for entry in entries]
    require(len(names) == len(set(names)) and len(names) <= 1000
        and sum(entry.file_size for entry in entries) <= 512 * 1024 * 1024, 'Unsafe/oversized paired evidence')
    for entry in entries:
        path = Path(entry.filename)
        require(not path.is_absolute() and '..' not in path.parts
            and (entry.external_attr >> 16 & 0o170000) in (0, 0o100000)
            and path.suffix in {'.json', '.log', '.txt', '.tsv', '.png'}
            and entry.file_size <= 128 * 1024 * 1024, 'Unsafe paired evidence member')
    require(required_files() | {'execution.json', 'upload-screening.json'} <= set(names),
        'Missing full original paired inputs')
    require(0 < archive.getinfo('producer-receipt.json').file_size <= 32_768,
        'Oversized producer receipt member')
    def raw(name):
        return archive.read(name)
    def value(name):
        require(archive.getinfo(name).file_size <= 4 * 1024 * 1024, 'Oversized paired JSON')
        return parse_json(raw(name))
    execution = value('execution.json')
    expected = dict(schema='arctic-external-paired-execution-v1',
        status='frozen_external_paired_regression_gate_passed', release_acceptance=False,
        run_id=execution_run_id, run_attempt=1, execution_source_sha=execution_source_sha,
        reviewed_parent_sha=reviewed_parent_sha, image=image, baseline=BASELINE,
        plan_sha256=plan_sha256, observer=plan['observer'],
        candidate_source_files=plan['candidate_source_files'], execution_files=plan['execution_files'])
    require(set(execution) == set(expected) | {'files'}
        and all(same(execution.get(key), val) for key, val in expected.items()), 'External execution provenance differs')
    files = execution.get('files')
    require(type(files) is dict and set(files) == set(names) - {'execution.json', 'upload-screening.json'},
        'Exact paired input inventory differs')
    screening = value('upload-screening.json')
    require(set(screening.get('files', {})) == set(names) - {'upload-screening.json'}, 'Screening inventory differs')
    for name in set(names) - {'upload-screening.json'}:
        content = raw(name)
        receipt = screening['files'][name]
        require(same(receipt, dict(original_sha256=digest(content), uploaded_sha256=digest(content),
            bytes=len(content), redactions=0)), 'Paired evidence was redacted/truncated: ' + name)
        if name != 'execution.json':
            require(same(files[name], dict(bytes=len(content), sha256=digest(content))), 'Paired input bytes differ: ' + name)
    require(0 < len(raw('producer-receipt.json')) <= 32_768
        and digest(raw('producer-receipt.json')) == image['producer_receipt_sha256']
        and same(value('producer-receipt.json'), producer_receipt), 'Producer receipt bytes differ')
    require(digest(raw('observer-source.txt')) == plan['observer']['frozen_sha256'], 'Frozen observer bytes differ')
    state = value('status.json')
    require(state.get('phase') == 'complete_regression_gate_passed' and state.get('acceleration') == 'kvm'
        and state.get('memory_mib') == 4096 and state.get('vcpus') == 2
        and state.get('restricted_network') is True and state.get('input_images_rechecked') is True
        and state.get('observer_sha256') == plan['observer']['frozen_sha256'], 'Paired host execution differs')
    for key, name in (('vm_base_image_id', 'vm-base-image-id.txt'),
                      ('vm_prepared_image_id', 'vm-prepared-image-id.txt')):
        require(type(state.get(key)) is str and re.fullmatch('(?:sha256:)?[0-9a-f]{64}', state[key])
            and raw(name) == (state[key] + '\n').encode(), 'Immutable VM container identity differs')
    for name, expected_image in (('baseline', BASELINE), ('candidate', image)):
        actual = state.get('images', {}).get(name, {})
        require(same(actual.get('bytes'), expected_image['bytes']) and actual.get('sha256') == expected_image['sha256'],
            'Measured ISO differs: ' + name)
        profile = BASELINE['profile_sha256'] if name == 'baseline' else plan['candidate_source_files']['profiles/ci/offline.toml']
        require(state.get('profiles', {}).get(name, {}).get('sha256') == profile, 'Measured install profile differs')
        require(raw(name + '-install-harness.log').count(b'ARCTIC-PRISTINE-INSTALL-POWEROFF=clean') == 1,
            'Missing/duplicate clean offline installation')
        exits = [line.split(b'ARCTIC-INSTALL-EXIT=', 1)[1].strip()
            for line in raw(name + '/serial-install.log').splitlines() if b'ARCTIC-INSTALL-EXIT=' in line]
        require(exits == [b'0'], 'Missing/duplicate successful offline installation exit')
        pristine = state.get('pristine_installed_sources', {}).get(name, {})
        require(set(pristine) == {'target.qcow2', 'OVMF_VARS.fd'}
            and all(re.fullmatch('[0-9a-f]{64}', val) for val in pristine.values()), 'Missing pristine source identities')
        require(digest(raw(name + '/vm-toolchain.txt')) == state.get('vm_toolchain_sha256'), 'Install toolchain differs')
    require(same(state.get('planned_boot_order'), [dict(image=name, boot=boot) for name, boot in ORDER])
        and same([(row.get('image'), row.get('boot')) for row in state.get('runs', [])], list(ORDER))
        and all(type(row.get('harness_exit')) is int and row['harness_exit'] == 0 for row in state['runs']),
        'Six-boot order/completion differs')
    expected_external = dict(schema='arctic-external-paired-context-v1', run_id=execution_run_id,
        execution_source_sha=execution_source_sha, reviewed_parent_sha=reviewed_parent_sha,
        plan_sha256=plan_sha256, observer=plan['observer'], image_source_sha=image['source_sha'],
        candidate_iso_sha256=image['sha256'])
    runs = dict(baseline=[], candidate=[])
    context_ids = set()
    with tempfile.TemporaryDirectory(prefix='arctic-replay-') as temp:
        for name, boot in ORDER:
            prefix = 'runs/' + name + '/' + str(boot) + '/'
            context = value(prefix + 'performance-context.json')
            require(same(context.get('external_execution'), expected_external)
                and re.fullmatch('[0-9a-f]{32}', context.get('context_id', ''))
                and context['context_id'] not in context_ids, 'Repeated/mismatched external boot context')
            context_ids.add(context['context_id'])
            pristine = state['pristine_installed_sources'][name]
            require(context.get('image') == name and type(context.get('boot')) is int and context['boot'] == boot
                and context.get('collector') == 'console' and context.get('fresh_installed_overlay') is True
                and context.get('installed_base_sha256') == pristine['target.qcow2']
                and context.get('firmware_variables_sha256') == pristine['OVMF_VARS.fd']
                and context.get('iso_sha256') == state['images'][name]['sha256']
                and context.get('install_profile_sha256') == state['profiles'][name]['sha256'], 'Boot source context differs')
            require(digest(raw(prefix + 'vm-toolchain.txt')) == state['vm_toolchain_sha256'], 'Boot toolchain differs')
            log = Path(temp) / (name + '-' + str(boot) + '.log')
            log.write_bytes(raw(prefix + 'serial-boot.log'))
            run = comparator.read_run(log, strict=True)
            require(run.get('observer_source_sha256') == plan['observer']['source_sha256']
                and same(run.get('external_execution'), dict(context=context,
                    observer_file_sha256=plan['observer']['frozen_sha256']))
                and same(run.get('app_roles', {}).get('boot_context'), context),
                'Guest observer/source context differs')
            require(re.fullmatch('[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}',
                run.get('identity', {}).get('boot_id', '')), 'Invalid boot identity')
            runs[name].append(run)
    comparison = comparator.compare_checked(runs, candidate_commit=image['source_sha'][:7],
        candidate_catalog_sha256=plan['candidate_source_files']['shell/AppsService.qml'],
        candidate_battery_sha256=plan['candidate_source_files']['shell/BatteryService.qml'])
    require(same(comparison, value('comparison.json')) and comparison['status'] == 'regression_gate_passed'
        and comparison['measurement_precision']['valid'] is True
        and comparison['measurement_precision']['threshold_enclosure_valid'] is True,
        'Full replay differs or original paired gates failed')
    return dict(performance_mode=MODE, execution_run_id=execution_run_id,
        execution_source_sha=execution_source_sha, image_source_sha=image['source_sha'],
        iso_sha256=image['sha256'], observer=plan['observer'], comparison=comparison,
        original_serials_replayed=6, release_acceptance=False)
