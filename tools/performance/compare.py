#!/usr/bin/env python3
"""Fail closed on incomplete paired runs; report effects without claiming speedups."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import statistics


MAPPING_OBSERVER = 'mango-socket-worker-v2-worker-clock'
SAMPLER = 'cpu-30-pss-6-v6-bounded-native-query'
ROLE_SAMPLER = 'cpu-30-pss-6-v7-declared-role-first-use'
ROLE_ORDER = ('terminal', 'files', 'browser')
EPIPHANY_EXPECTED_NATIVE_ELF_SHA256 = '1c91ba76182612fa4f6b9a768510d818d8b901888ee3f31bbb1452ad308b3b4d'
EXPECTED_ROLES = {'baseline': dict(terminal='kitty', files='nautilus', browser='zen'),
                  'candidate': dict(terminal='foot', files='pcmanfm', browser='gnome-web')}
ROLE_COMMANDS = {'kitty': ('kitty',), 'foot': ('foot',), 'nautilus': ('nautilus',),
                 'pcmanfm': ('pcmanfm',), 'zen': ('gtk-launch app.zen_browser.zen',),
                 'gnome-web': ('epiphany', 'gtk-launch org.gnome.Epiphany')}
ROLE_PROGRAMS = dict(kitty='kitty', foot='foot', nautilus='nautilus', pcmanfm='pcmanfm',
                     zen='flatpak', **{'gnome-web': 'epiphany'})
ROLE_APPIDS = dict(kitty=['kitty'], foot=['foot'], nautilus=['org.gnome.nautilus'], pcmanfm=['pcmanfm'],
                   zen=['zen', 'app.zen_browser.zen'], **{'gnome-web': ['org.gnome.epiphany', 'epiphany']})
BASELINE_ISO_SHA256 = '054db5c43cae47fb60f8f43efc8e052b569aa1b14e8f15adcb15cdc48265182f'
BASELINE_PROFILE_SHA256 = 'e6b9aa317521bdaaaf343629bc5de8b914b0a5f58387a0c9fe31754f17c0d20d'
WORKLOAD_PAGE_SHA256 = hashlib.sha256(b'<!doctype html><meta charset="utf-8"><title>Arctic startup fixture</title><h1>Arctic offline browser</h1><p>Local page, no remote resources.</p>').hexdigest()


def deferred_payload_evidence(run, app):
    package = app['package']
    expected = package.get('prelaunch_file_identity')
    fields = ('device','inode','size','mtime_ns','ctime_ns')
    if (not isinstance(expected,dict) or set(expected) != set(fields)
            or any(type(expected.get(key)) is not int or expected[key] < 0 for key in fields)
            or expected['inode'] <= 0 or expected['size'] < 4
            or package.get('payload_integrity_model') != 'full-hash-after-first-gui-v1'
            or type(package.get('prelaunch_content_bytes_read')) is not int or package['prelaunch_content_bytes_read'] != 0
            or type(package.get('elf_magic_checked_bytes')) is not int or package['elf_magic_checked_bytes'] != 0
            or package.get('rpm_header_sha256') != EPIPHANY_EXPECTED_NATIVE_ELF_SHA256
            or 'executable_sha256' in package or 'post_first_gui_integrity' in package):
        raise ValueError('Missing or pre-warmed declared GNOME Web file identity')
    proof = run.get('role_payload_integrity',{})
    bounds = run.get('startup_role_browser_cold_seconds',{}).get('observation_bounds')
    if not isinstance(bounds,list) or len(bounds) != 1 or not isinstance(bounds[0],dict):
        raise ValueError('Missing first-GUI browser bound for deferred payload proof')
    bound = bounds[0]
    def same_identity(value):
        return (isinstance(value,dict) and set(value) == set(fields)
                and all(type(value[key]) is int for key in fields) and value == expected)
    keys = ('first_gui_launch_ns','first_gui_map_upper_ns','measurement_returned_ns','hash_started_ns','hash_finished_ns')
    if (not isinstance(proof,dict) or proof.get('status') != 'verified'
            or proof.get('role') != 'browser' or proof.get('app_id') != 'gnome-web'
            or proof.get('boot_id') != run['identity']['boot_id']
            or proof.get('image') != run['app_roles']['image']
            or type(proof.get('boot')) is not int or proof['boot'] != run['app_roles']['boot_context']['boot']
            or type(proof.get('desktop_uid')) is not int or proof['desktop_uid'] != run['app_roles']['pristine_state']['uid']
            or proof.get('path') != app['program_path']
            or proof.get('phase') != 'immediately_after_first_gui_before_any_preconditioning'
            or proof.get('executable_sha256') != package.get('rpm_header_sha256')
            or proof.get('rpm_header_sha256') != package.get('rpm_header_sha256')
            or any(not same_identity(proof.get(key)) for key in ('declaration_identity','before_hash_identity','after_hash_identity'))
            or any(type(proof.get(key)) is not int or proof[key] <= 0 for key in keys)
            or [proof[key] for key in keys] != sorted(proof[key] for key in keys)
            or proof['first_gui_launch_ns'] != bound.get('launch_started_monotonic_ns')
            or proof['first_gui_map_upper_ns'] != bound.get('first_present_query',{}).get('worker_received_ns')):
        raise ValueError('Missing/invalid post-first-GUI GNOME Web actual payload proof')
    preconditioning = [run.get('precondition_role_'+role,{}).get('launch_started_monotonic_ns') for role in ROLE_ORDER]
    if (any(type(value) is not int or value <= 0 for value in preconditioning)
            or proof['hash_finished_ns'] > min(preconditioning)):
        raise ValueError('GNOME Web payload proof did not precede all role preconditioning')
    return proof


def role_evidence(runs):
    """Require installed identities and independent first-use boot provenance.

    A role replacement is an explicit cross-application comparison. It neither
    re-tests nor clears any historical measurement of the replaced binary.
    """
    present = ['app_roles' in run for group in runs.values() for run in group]
    if not any(present):
        return None
    if not all(present):
        raise ValueError('Mixed legacy/app-role evidence')
    result = {}
    for image, group in runs.items():
        identities, contexts = [], []
        for run in group:
            declared = run['app_roles']
            context = declared.get('boot_context', {})
            state = declared.get('pristine_state', {})
            if (declared.get('image') != image or run['identity'].get('sampler') != ROLE_SAMPLER
                    or context.get('image') != image or context.get('collector') != 'console'
                    or context.get('fresh_installed_overlay') is not True
                    or type(context.get('boot')) is not int or context.get('boot') not in (1, 2, 3)
                    or type(state.get('uid')) is not int or state['uid'] <= 0
                    or state.get('prior_role_state_paths') != [] or state.get('running_role_apps') != []):
                raise ValueError('Missing/invalid pristine installed role provenance: ' + image)
            for key in ('installed_base_sha256', 'firmware_variables_sha256',
                        'install_profile_sha256', 'iso_sha256'):
                if not re.fullmatch('[0-9a-f]{64}', context.get(key, '')):
                    raise ValueError('Missing first-use source identity: ' + key)
            if image == 'baseline' and (context['iso_sha256'] != BASELINE_ISO_SHA256
                    or context['install_profile_sha256'] != BASELINE_PROFILE_SHA256):
                raise ValueError('Original baseline image/profile identity differs')
            sources = declared.get('configuration_sources')
            if not isinstance(sources, list) or not sources or any(
                    not isinstance(source, dict) or not source.get('path')
                    or not re.fullmatch('[0-9a-f]{64}', source.get('sha256', '')) for source in sources):
                raise ValueError('Missing installed default-app configuration identity')
            roles = declared.get('roles', {})
            if set(roles) != set(ROLE_ORDER):
                raise ValueError('Missing installed application role')
            for role, ident in EXPECTED_ROLES[image].items():
                app = roles[role]
                configured = app.get('configured_command')
                legacy = image == 'baseline' and ident == 'zen' and configured == ''
                if (app.get('id') != ident or app.get('role') != role
                        or app.get('legacy_system_mime_fallback') is not legacy
                        or (configured not in ROLE_COMMANDS[ident] and not legacy)
                        or state.get('configured', {}).get(role, '') != configured
                        or not isinstance(app.get('program_path'), str) or not app['program_path'].startswith('/')
                        or state.get('programs', {}).get(ROLE_PROGRAMS[ident]) != app['program_path']
                        or app.get('appids') != ROLE_APPIDS[ident]):
                    raise ValueError('Application role differs from installed configured default: ' + role)
                package = app.get('package', {})
                if ident == 'zen':
                    if (package.get('kind') != 'flatpak' or package.get('ref') != 'app.zen_browser.zen'
                            or not re.fullmatch('[0-9a-f]{64}', package.get('commit', ''))):
                        raise ValueError('Missing declared Zen Flatpak identity')
                else:
                    rpm = 'epiphany' if ident == 'gnome-web' else ident
                    nevra = package.get('nevra', '')
                    if ident == 'gnome-web':
                        runtime = package.get('runtime_nevra', '')
                        if (package.get('kind') != 'rpm' or package.get('binary_owner') != runtime
                                or not re.match(r'epiphany-[0-9]+:',nevra)
                                or not re.match(r'epiphany-runtime-[0-9]+:',runtime)
                                or nevra[len('epiphany-'):] != runtime[len('epiphany-runtime-'):]
                                or nevra not in run['rpm_inventory']['nevra'] or runtime not in run['rpm_inventory']['nevra']
                                or package.get('ownership_model') != 'epiphany-frontend-runtime-v1'
                                or package.get('executable_path') != app['program_path'] or app['program_path'] != '/usr/bin/epiphany'
                                or not re.fullmatch('[0-9a-f]{64}',package.get('rpm_header_sha256',''))):
                            raise ValueError('Declared GNOME Web frontend/runtime or actual ELF ownership differs')
                        deferred_payload_evidence(run,app)
                    elif (package.get('kind') != 'rpm' or package.get('binary_owner') != nevra
                            or not re.match(re.escape(rpm) + r'-[0-9]+:', nevra)
                            or nevra not in run['rpm_inventory']['nevra']):
                        raise ValueError('Declared application RPM is absent or does not own the executable: ' + role)
                for phase in ('cold', 'warm'):
                    timing = run.get('startup_role_' + role + '_' + phase + '_seconds', {})
                    expected_phase = ('first_gui_role_execution_from_pristine_install' if phase == 'cold'
                                      else 'after_45_second_preconditioning')
                    if timing.get('app_id') != ident or timing.get('phase') != expected_phase:
                        raise ValueError('Missing or misidentified ' + phase + ' role measurement: ' + role)
                if (run.get('precondition_role_' + role, {}).get('persistent_hold_seconds') != 45
                        or run['precondition_role_' + role].get('app_id') != ident):
                    raise ValueError('Missing or inconsistent role preconditioning: ' + role)
            browser = ('app.zen_browser.zen.desktop' if image == 'baseline' else 'org.gnome.Epiphany.desktop')
            if declared.get('default_browser_desktop') != browser:
                raise ValueError('Declared browser differs from installed MIME default')
            expected_order = [phase + ':' + role for phase in ('cold', 'precondition', 'warm') for role in ROLE_ORDER]
            if run.get('role_measurement_order') != ['pristine_idle', *expected_order]:
                raise ValueError('First-use roles were missing or preconditioned before their cold launch')
            scope = run.get('pristine_idle_measurement_scope', {})
            samples = run.get('pristine_idle_samples', [])
            if (scope.get('phase') != 'before_any_gui_role_or_workload_worker'
                    or scope.get('collector_present') is not True or scope.get('workload_worker_present') is not False
                    or len(samples) != 30 or sum('process_pss_bytes' in sample for sample in samples) != 6
                    or sum('process_private_bytes' in sample for sample in samples) != 6
                    or any('benchmark_worker_cpu' in sample for sample in samples)):
                raise ValueError('Missing or contaminated pristine desktop idle measurement')
            workload = run.get('role_workload', {})
            if (workload.get('uid') != state['uid'] or workload.get('page_sha256') != WORKLOAD_PAGE_SHA256
                    or type(workload.get('pid')) is not int or workload['pid'] <= 0
                    or type(workload.get('start_ticks')) is not int or workload['start_ticks'] <= 0
                    or workload.get('file_count') != 16
                    or workload.get('file_payload_sha256') != hashlib.sha256(b'Arctic file fixture\n').hexdigest()
                    or not re.fullmatch(r'http://127\.0\.0\.1:[0-9]+/benchmark\.html', workload.get('url', ''))
                    or not workload.get('files', '').startswith('/tmp/arctic-performance-files-')):
                raise ValueError('Offline role workload is missing, changed or remote')
            identities.append(roles)
            contexts.append(context)
        if len({context['boot'] for context in contexts}) != 3:
            raise ValueError('Repeated first-use boot number: ' + image)
        for key in ('installed_base_sha256', 'firmware_variables_sha256', 'install_profile_sha256', 'iso_sha256'):
            if len({context[key] for context in contexts}) != 1:
                raise ValueError('First-use installed source changed across boots: ' + key)
        if len({json.dumps(roles, sort_keys=True) for roles in identities}) != 1:
            raise ValueError('Configured application identity changed across boots: ' + image)
        result[image] = dict(roles=identities[0], per_boot_context=contexts)
    return result


def mapped_timings(run):
    if 'app_roles' in run:
        return [('role_' + role + '_' + phase, run['startup_role_' + role + '_' + phase + '_seconds'],
                 1 if phase == 'cold' else 3, ROLE_SAMPLER, .00025)
                for role in ROLE_ORDER for phase in ('cold', 'warm')]
    return [(app, run['startup_' + app + '_seconds'], 3, SAMPLER, .001)
            for app in ('kitty', 'org.gnome.nautilus', 'zen')]


def mapped_metrics(role_mode):
    if role_mode:
        return [(role + '_' + suffix, 'startup_role_' + role + '_' + phase + '_seconds', indices)
                for role in ROLE_ORDER for suffix, phase, indices in (
                    ('first_gui_role_mapped', 'cold', (0,)),
                    ('first_mapped_after_preconditioning', 'warm', (0,)),
                    ('subsequent_mapped', 'warm', (1, 2)))]
    return [(app + '_' + suffix, 'startup_' + app + '_seconds', indices)
            for app in ('kitty', 'org.gnome.nautilus', 'zen') for suffix, indices in (
                ('first_mapped_after_preconditioning', (0,)), ('subsequent_mapped', (1, 2)))]


def package_attribution(runs):
    """Reject within-image updates; report between-image versions as context."""
    inventories = {}
    for name, group in runs.items():
        recorded = [run.get('rpm_inventory') for run in group]
        if any(not isinstance(value, dict) for value in recorded):
            raise ValueError('Missing full RPM inventory: ' + name)
        for inventory in recorded:
            records = inventory.get('nevra')
            if (not isinstance(records, list) or not records
                    or any(not isinstance(record, str) or not record or '\n' in record for record in records)
                    or sorted(records) != records
                    or hashlib.sha256(('\n'.join(records)+'\n').encode()).hexdigest() != inventory.get('sha256')):
                raise ValueError('Invalid full RPM inventory/digest: ' + name)
        if len({value['sha256'] for value in recorded}) != 1:
            raise ValueError('RPM versions changed between boots of the same image: ' + name)
        inventories[name] = recorded[0]
    packages = {name: set(value['nevra']) for name, value in inventories.items()}
    return dict(inventory=inventories, baseline_only=sorted(packages['baseline']-packages['candidate']),
                candidate_only=sorted(packages['candidate']-packages['baseline']),
                interpretation='Between-image RPM metadata differences are potential confounders, not causal proof; each image stayed unchanged across its three boots')


def cpu_validity(run, key='idle_samples', worker=None):
    samples = run[key]
    for sample in samples:
        total, idle = sample.get('cpu_ticks_delta'), sample.get('cpu_idle_ticks_delta')
        if (not isinstance(total, int) or isinstance(total, bool) or not isinstance(idle, int)
                or isinstance(idle, bool) or total <= 0 or not 0 <= idle <= total
                or not isinstance(sample.get('cpu_busy_percent'), (int, float))
                or isinstance(sample['cpu_busy_percent'], bool) or not math.isfinite(sample['cpu_busy_percent'])
                or not math.isclose(sample['cpu_busy_percent'], 100 * (total-idle) / total,
                                    rel_tol=1e-9, abs_tol=1e-9)):
            raise ValueError('Missing/invalid idle CPU counter interval')
        memory = sample.get('memory_bytes', {}).get('MemAvailable')
        if not valid_bytes(memory):
            raise ValueError('Missing/invalid raw MemAvailable byte value')
        for name in ('process_pss_bytes', 'process_private_bytes'):
            if name in sample and not valid_bytes(sample[name]):
                raise ValueError('Invalid raw memory byte value: ' + name)
        if worker:
            helper = sample.get('benchmark_worker_cpu', {})
            ticks, hz, elapsed = helper.get('ticks_delta'), sample.get('cpu_clock_ticks_per_second'), sample.get('sample_elapsed_seconds')
            if (any(helper.get(field) != worker[field] for field in ('pid', 'uid', 'start_ticks'))
                    or type(ticks) is not int or ticks < 0 or type(hz) is not int or hz <= 0
                    or not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool)
                    or not math.isfinite(elapsed) or elapsed <= 0
                    or not isinstance(helper.get('percent_one_core'), (int, float))
                    or isinstance(helper['percent_one_core'], bool)
                    or not math.isclose(helper['percent_one_core'], 100 * ticks / hz / elapsed, rel_tol=1e-9, abs_tol=1e-9)
                    or not isinstance(helper.get('resolution_percent_one_core'), (int, float))
                    or isinstance(helper['resolution_percent_one_core'], bool)
                    or not math.isclose(helper['resolution_percent_one_core'], 100 / hz / elapsed, rel_tol=1e-9, abs_tol=1e-9)):
                raise ValueError('Missing/invalid temporary worker CPU accounting')
    return dict(samples=len(samples), zero_busy_samples=sum(sample['cpu_busy_percent'] == 0 for sample in samples),
                busy_ticks=sum(sample['cpu_ticks_delta']-sample['cpu_idle_ticks_delta'] for sample in samples),
                observed_ticks=sum(sample['cpu_ticks_delta'] for sample in samples),
                observer_cpu_percent_one_core=[sample.get('observer_cpu_percent_one_core') for sample in samples],
                temporary_worker_cpu=[sample.get('benchmark_worker_cpu') for sample in samples] if worker else None,
                resolution_percent=[100 / sample['cpu_ticks_delta'] for sample in samples],
                interpretation='A zero median can hide bursts; zero counted ticks only bound utilization at the exported tick resolution and include observer cost')


def valid_bytes(value):
    # Validate before statistics.median, which coerces JSON true to a numeric 1.
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and 0 < value <= 2**63-1 and value == math.floor(value))


def idle_sample_layout(samples):
    if (not isinstance(samples, list) or len(samples) != 30
            or any(not isinstance(sample, dict) for sample in samples)
            or sum('process_pss_bytes' in sample for sample in samples) != 6
            or any(('process_pss_bytes' in sample) != ('process_private_bytes' in sample) for sample in samples)):
        raise ValueError('Missing or unpaired CPU/PSS/private samples')


def worker_mapping_proof(bound, expected_uid=None):
    launch = bound.get('launch_started_monotonic_ns')
    if type(launch) is not int or launch <= 0 or bound.get('bound_basis') != 'worker-sent-to-received':
        raise ValueError('Missing worker-clock launch/bound provenance')
    positive = bound.get('first_present_query')
    negative = bound.get('last_absent_query')
    for proof in (positive,negative) if negative is not None else (positive,):
        keys=('parent_started_ns','worker_started_ns','worker_sent_ns','worker_received_ns','parent_received_ns')
        if not isinstance(proof,dict) or any(type(proof.get(k)) is not int or proof[k] <= 0 for k in keys):
            raise ValueError('Malformed worker-clock query envelope')
        if [proof[k] for k in keys] != sorted(proof[k] for k in keys) or type(proof.get('uid')) is not int or proof['uid'] <= 0:
            raise ValueError('Worker-clock query envelope/UID differs')
    if expected_uid is not None and positive['uid'] != expected_uid:
        raise ValueError('Worker-clock query did not use the declared desktop UID')
    if negative is not None and (negative['uid'] != positive['uid']
            or negative['parent_received_ns'] > positive['parent_started_ns']):
        raise ValueError('Worker-clock negative/present query order or UID differs')
    lower_ns = negative['worker_sent_ns'] if negative is not None else launch
    upper_ns = positive['worker_received_ns']
    if not launch <= lower_ns <= upper_ns:
        raise ValueError('Worker-clock map bounds precede the launch')
    if not all(math.isclose(bound[key],(stamp-launch)/1e9,rel_tol=1e-9,abs_tol=1e-9)
               for key,stamp in (('lower_seconds',lower_ns),('upper_seconds',upper_ns))):
        raise ValueError('Worker-clock raw timestamps and relative map bounds differ')


def mapping_precision(run):
    """Sampling uncertainty is a separate fail-closed gate, never an exemption.

    Bound every observation to 5 ms and a quarter of the 10% app gate. Keeping
    the point-estimate regression gate unchanged prevents overlapping brackets
    or distributions from excusing a regression. Historical coarse runs remain
    reported but cannot qualify a new candidate.
    """
    result = []
    for app, timing, count, sampler, poll in mapped_timings(run):
        samples = [timing['first'], *timing.get('warm', [])]
        bounds = timing.get('observation_bounds', [])
        if len(samples) != count or len(bounds) != count:
            raise ValueError('Missing mapped-window observation bounds: ' + app)
        for index, (sample, bound) in enumerate(zip(samples, bounds)):
            lower, upper, width = (bound.get(k) for k in
                                   ('lower_seconds', 'upper_seconds', 'interval_seconds'))
            if any(not isinstance(n, (float, int)) or isinstance(n, bool) or not math.isfinite(n)
                   for n in (sample, lower, upper, width)) or not 0 <= lower <= upper or width < 0:
                raise ValueError('Invalid mapped-window observation bounds: ' + app)
            if (not math.isclose(upper, sample, abs_tol=1e-9, rel_tol=1e-9)
                    or not math.isclose(width, upper-lower, abs_tol=1e-9, rel_tol=1e-9)):
                raise ValueError('Inconsistent mapped-window observation bounds: ' + app)
            limit = min(.005, sample * .025)
            current_observer = (run['identity'].get('sampler') == sampler
                                and timing.get('observer') == MAPPING_OBSERVER
                                and bound.get('observer') == MAPPING_OBSERVER
                                and timing.get('poll_sleep_seconds') == poll)
            if current_observer:
                worker_mapping_proof(bound,run.get('app_roles',{}).get('pristine_state',{}).get('uid'))
            result.append(dict(app=app, launch=index, lower_seconds=lower, upper_seconds=upper,
                               interval_seconds=width, maximum_interval_seconds=limit,
                               current_observer=current_observer,
                               valid=current_observer and width <= limit))
    return result


def mapping_enclosures(runs):
    """Propagate deterministic observation bounds through both median levels.

    A point estimate below 10% must not qualify when its admissible timing
    interval still permits a >10% regression. This adds no statistical claim
    and never changes the original point-estimate regression flag.
    """
    result = {}
    role_mode = 'app_roles' in runs['baseline'][0]
    for metric, key, indices in mapped_metrics(role_mode):
        bounds = {}
        for name, group in runs.items():
            bounds[name] = {edge: statistics.median(statistics.median(
                run[key]['observation_bounds'][index][edge + '_seconds']
                for index in indices) for run in group) for edge in ('lower', 'upper')}
        baseline, candidate = bounds['baseline'], bounds['candidate']
        limit = baseline['lower'] * 1.10
        supported = baseline['lower'] > 0 and (candidate['upper'] <= limit
                    or math.isclose(candidate['upper'], limit, rel_tol=1e-12))
        result[metric] = dict(median_bounds_seconds=bounds,
            possible_percent_difference_lower=(100 * (candidate['lower']/baseline['upper']-1)
                                               if baseline['upper'] > 0 else None),
            possible_percent_difference_upper=(100 * (candidate['upper']/baseline['lower']-1)
                                               if baseline['lower'] > 0 else None),
            regression_threshold_percent=10, threshold_enclosure_valid=supported,
            interpretation='Deterministic sampling bounds, not a confidence interval; uncertainty cannot excuse the original point regression or certify a near-threshold pass')
    return result


def read_run(path):
    records = {}
    for line in path.read_text(errors='replace').splitlines():
        if 'ARCTIC-INSTALLED-SMOKE-EXIT=' in line:
            status = line.split('ARCTIC-INSTALLED-SMOKE-EXIT=', 1)[1].strip()
            if status != '0':
                raise ValueError(f'{path}: installed probe exit was not successful: {status}')
        if 'ARCTIC-PERFORMANCE ' not in line:
            continue
        value = json.loads(line.split('ARCTIC-PERFORMANCE ', 1)[1])
        if value['stage'] == 'installed':
            records[value['check']] = value['value']
    if records.get('done') is not True or records.get('security') != 'Enforcing':
        raise ValueError(f'{path}: incomplete probe or SELinux not enforcing')
    samples = records.get('idle_samples', [])
    idle_sample_layout(samples)
    if records['measurement_conditions']['initial_keep_awake'].get('on') is not False:
        raise ValueError(f'{path}: non-default initial Keep awake state')
    if records['keep_awake_restored'].get('on') is not False:
        raise ValueError(f'{path}: Keep awake was not restored')
    if 'app_roles' not in records:
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
    for run in all_runs:
        idle_sample_layout(run.get('idle_samples'))
        if 'app_roles' in run:
            idle_sample_layout(run.get('pristine_idle_samples'))
    if len({r['identity']['boot_id'] for r in all_runs}) != 6:
        raise ValueError('Repeated/missing boot IDs')
    if len({r['observer_source_sha256'] for r in all_runs}) != 1:
        raise ValueError('Different observer sources')
    attribution = package_attribution(runs)
    roles = role_evidence(runs)
    cpu_checks = {name: [cpu_validity(r, worker=r['role_workload'] if roles else None) for r in group]
                  for name, group in runs.items()}
    pristine_cpu_checks = ({name: [cpu_validity(r, 'pristine_idle_samples') for r in group]
                            for name, group in runs.items()} if roles else None)
    precision = {name: [mapping_precision(r) for r in group] for name, group in runs.items()}
    precision_valid = all(check['valid'] for group in precision.values() for boot in group for check in boot)
    enclosures = mapping_enclosures(runs)
    enclosure_valid = all(check['threshold_enclosure_valid'] for check in enclosures.values())
    metrics = [('boot_systemd_total', 'seconds', boot_seconds, .10),
               ('root_filesystem_du_allocation', 'bytes', lambda r: int(r['installed_bytes'].split()[0]), None)]
    for name in ('process_pss_bytes', 'process_private_bytes', 'cpu_busy_percent'):
        metrics.append((name, 'percent' if name == 'cpu_busy_percent' else 'bytes',
                        lambda r, name=name: statistics.median(s[name] for s in r['idle_samples'] if name in s),
                        None if name == 'cpu_busy_percent' else .05))
        if roles:
            metrics.append(('pristine_'+name, 'percent' if name == 'cpu_busy_percent' else 'bytes',
                lambda r, name=name: statistics.median(s[name] for s in r['pristine_idle_samples'] if name in s),
                None if name == 'cpu_busy_percent' else .05))
    metrics.append(('MemAvailable_bytes', 'bytes',
                    lambda r: statistics.median(s['memory_bytes']['MemAvailable'] for s in r['idle_samples']), None))
    if roles:
        metrics.append(('pristine_MemAvailable_bytes', 'bytes', lambda r: statistics.median(
            s['memory_bytes']['MemAvailable'] for s in r['pristine_idle_samples']), None))
    for app in ('fish', 'bash', 'shell_ipc'):
        metrics.append((app + '_launch_or_roundtrip', 'seconds',
                        lambda r, app=app: r[app + '_seconds']['median'], .10))
    for metric, key, indices in mapped_metrics(roles is not None):
        metrics.append((metric, 'seconds', lambda r, key=key, indices=indices:
            statistics.median([r[key]['first'], *r[key].get('warm', [])][index] for index in indices), .10))
    results = []
    for name, unit, extract, gate in metrics:
        values = {name: [extract(r) for r in group] for name, group in runs.items()}
        if any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0
               or (unit != 'percent' and value == 0) for group in values.values() for value in group):
            raise ValueError('Invalid or missing numerical measurement: ' + name)
        median = {name: statistics.median(numbers) for name, numbers in values.items()}
        ranges = {name: [min(numbers), max(numbers)] for name, numbers in values.items()}
        delta = median['candidate'] / median['baseline'] - 1 if median['baseline'] else None
        overlap = max(v[0] for v in ranges.values()) <= min(v[1] for v in ranges.values())
        results.append(dict(metric=name, unit=unit, per_boot=values, median=median, range=ranges,
                            percent_difference=100 * delta if delta is not None else None,
                            range_overlap=overlap, regression_threshold_percent=100 * gate if gate else None,
                            observation_enclosure=enclosures.get(name),
                            application_identity=({image: roles[image]['roles'][name.split('_', 1)[0]]['id']
                                for image in roles} if roles and name in enclosures else None),
                            regression=gate is not None and median['candidate'] > median['baseline'] * (1 + gate)
                            and not math.isclose(median['candidate'], median['baseline'] * (1 + gate), rel_tol=1e-12)))
    return dict(status=('regression_gate_failed' if any(r['regression'] for r in results)
                        else 'regression_gate_passed' if precision_valid and enclosure_valid
                        else 'measurement_precision_gate_failed'),
                metrics=results, identity={name: [r['identity'] for r in group] for name, group in runs.items()},
                measurement_precision=dict(valid=precision_valid, checks=precision,
                    threshold_enclosure_valid=enclosure_valid,
                    rule='Each mapped-window bracket <= min(5ms, 2.5% of observed time); all six boots use the same current observer',
                    enclosure_rule='For each mapped metric candidate median upper <= 1.10 * baseline median lower; zero baseline lower is unresolved and fails qualification'),
                package_attribution=attribution,
                application_role_comparison=roles,
                idle_cpu_validity=cpu_checks,
                pristine_idle_cpu_validity=pristine_cpu_checks,
                pristine_idle_measurement_scope={name: [r.get('pristine_idle_measurement_scope') for r in group]
                                                 for name, group in runs.items()} if roles else None,
                idle_measurement_scope={name: [r.get('idle_measurement_scope') for r in group]
                                        for name, group in runs.items()},
                measured_payload={name: [r['measured_payload'] for r in group] for name, group in runs.items()},
                startup_observation={name: [{app: timing for app, timing, *_ in mapped_timings(r)}
                    for r in group] for name, group in runs.items()},
                installed_mount_allocations={name: [r.get('installed_mount_allocations') for r in group]
                                             for name, group in runs.items()},
                limitations=['Three boots per image; distributions are small and no confidence interval is implied',
                             ('First GUI execution per role from pristine installed profiles precedes all 45-second preconditioning; shared OS libraries and host storage caches may already be warm'
                              if roles else '45-second mapped-app preconditioning; these are warmed launches, not first-ever cold starts'),
                             ('Different configured applications are compared by declared role; this does not resolve or overwrite the historical Kitty regression'
                              if roles else 'Same named application metrics retain their original regression gates'),
                             'KVM/QEMU with virtual graphics; no physical laptop or gaming performance claim',
                             'Normalized idle includes the collector and temporary benchmark processes; parent RUSAGE_SELF omits helper CPU and equal fixture code does not prove equal runtime overhead',
                             'Separate pristine desktop idle is before all GUI-role executions and the workload worker, but includes the frozen collector and normal console/session processes; worker CPU ticks are reported separately during normalized idle',
                             'Map timestamps are bounded observations, not exact compositor/first-frame timestamps; IPC roundtrips and brackets are reported',
                             'The app regression threshold remains 10%; precision failures cannot become passes or excuse an observed regression',
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
