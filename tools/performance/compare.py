#!/usr/bin/env python3
"""Fail closed on incomplete paired runs; report effects without claiming speedups."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import statistics


MAPPING_OBSERVER = 'mango-socket-worker-v2-autonomous'
CAUSAL_MAPPING_OBSERVER = 'mango-socket-worker-v3-raw-clock-autonomous'
SAMPLER = 'cpu-30-pss-6-v6-bounded-native-query'
ROLE_SAMPLER = 'cpu-30-pss-6-v10-raw-causal-role-first-use'
ROLE_ORDER = ('terminal', 'files', 'browser')
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
                    rpm = 'epiphany-runtime' if ident == 'gnome-web' else ident
                    nevra = package.get('nevra', '')
                    if (package.get('kind') != 'rpm' or package.get('binary_owner') != nevra
                            or not re.match(re.escape(rpm) + r'-[0-9]+:', nevra)
                            or nevra not in run['rpm_inventory']['nevra']):
                        raise ValueError('Declared application RPM is absent or does not own the executable: ' + role)
                    if ident == 'gnome-web':
                        launcher = package.get('desktop_owner', '')
                        if (not re.match(r'epiphany-[0-9]+:', launcher)
                                or launcher not in run['rpm_inventory']['nevra']):
                            raise ValueError('Declared Epiphany desktop launcher RPM is absent or wrong')
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
                 1 if phase == 'cold' else 3, ROLE_SAMPLER, .00005)
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


def causal_precision(bound):
    """The stronger lower endpoint requires a same-launch kernel receipt."""
    proof = bound.get('causal_lower_bound')
    if not isinstance(proof, dict):
        return False
    if (proof.get('method') != 'wlroots-0.20-return-before-mango-list-insertion-raw-v2'
            or proof.get('clock') != 'mono_raw' or proof.get('userspace_clock') != 'CLOCK_MONOTONIC_RAW'
            or bound.get('clock') != 'CLOCK_MONOTONIC_RAW' or proof.get('status') != 'bound-before-mapping'
            or proof.get('exported_symbol') != 'wlr_ext_foreign_toplevel_handle_v1_create'
            or proof.get('identifier_offset') != 56
            or proof.get('audited_header_sha256') != '9253b1ac1b68011cb304c0c9b84a6678779acc820994131a31f170d26945d0f3'
            or proof.get('audited_source_sha256') != '5580d4b6c803fb3548bbe104f5b0bdbfd5a17b42dd173358aa526ca0e958a088'):
        return False
    if any(not isinstance(proof.get(key), str) or not re.fullmatch('[0-9a-f]{64}', proof[key])
           for key in ('library_sha256', 'mango_sha256')):
        return False
    if any(type(proof.get(key)) is not int or proof[key] <= 0
           for key in ('kernel_pid', 'desktop_uid', 'mango_start_ticks', 'exported_file_offset')):
        return False
    if (not isinstance(proof.get('library_rpm'), str) or not re.fullmatch(
            r'wlroots(?:0\.20)?-0\.20\.2-[A-Za-z0-9._+]+\.x86_64', proof['library_rpm'])
            or not isinstance(proof.get('library_path'), str) or not re.fullmatch(
            r'/usr/lib64/libwlroots-0\.20\.so(?:\.[0-9]+)*', proof['library_path'])):
        return False
    if not isinstance(proof.get('mango_rpm'), str) or not re.fullmatch(
            r'mangowm-0\.17\.3-[A-Za-z0-9._+]+\.x86_64', proof['mango_rpm']):
        return False
    losses = proof.get('loss_counts')
    if not isinstance(losses, dict) or not losses or any(
            not isinstance(cpu, str) or not re.fullmatch(r'cpu[0-9]+', cpu) or not isinstance(counts, dict)
            or set(counts) != {'overrun', 'commit overrun', 'dropped events'}
            or any(type(value) is not int or value != 0 for value in counts.values())
            for cpu, counts in losses.items()):
        return False
    started = bound.get('launch_started_monotonic_ns')
    ipc_lower = proof.get('ipc_lower_monotonic_ns')
    events = proof.get('matched_events')
    if (type(started) is not int or started <= 0 or type(ipc_lower) is not int
            or not isinstance(events, list) or not 0 < len(events) <= 64):
        return False
    upper = started + round(bound['upper_seconds'] * 1e9)
    identities = []
    for event in events:
        if not isinstance(event, dict):
            return False
        text = event.get('kernel_timestamp_text')
        token = re.fullmatch(r'([0-9]{1,20})\.([0-9]{1,9})', text) if isinstance(text, str) else None
        if not token:
            return False
        literal = int(token[1])*1_000_000_000 + int(token[2].ljust(9, '0'))
        resolution = 10 ** (9-len(token[2]))
        if (not isinstance(event, dict) or type(event.get('kernel_pid')) is not int
                or event.get('kernel_pid') != proof['kernel_pid']
                or not isinstance(event.get('foreign_toplevel_id'), str)
                or not re.fullmatch('[0-9a-f]{32}', event['foreign_toplevel_id'])
                or type(event.get('lower_monotonic_ns')) is not int
                or not started <= event['lower_monotonic_ns'] <= upper
                or type(event.get('timestamp_resolution_ns')) is not int
                or event.get('timestamp_resolution_ns') not in (1, 10, 100, 1000)
                or type(event.get('kernel_text_monotonic_ns')) is not int
                or event['kernel_text_monotonic_ns'] != literal
                or event['timestamp_resolution_ns'] != resolution
                or type(event.get('timestamp_rounding_allowance_ns')) is not int
                or event['timestamp_rounding_allowance_ns'] != event['timestamp_resolution_ns']
                or event['lower_monotonic_ns'] != event['kernel_text_monotonic_ns'] - event['timestamp_rounding_allowance_ns']):
            return False
        identities.append(event['foreign_toplevel_id'])
    lower = max(ipc_lower, min(event['lower_monotonic_ns'] for event in events))
    return (len(identities) == len(set(identities)) and started <= ipc_lower <= upper
            and math.isclose((lower - started) / 1e9, bound['lower_seconds'], abs_tol=1e-9, rel_tol=1e-9))


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
            expected_observer = CAUSAL_MAPPING_OBSERVER if sampler == ROLE_SAMPLER else MAPPING_OBSERVER
            current_observer = (run['identity'].get('sampler') == sampler
                                and timing.get('observer') == expected_observer
                                and bound.get('observer') == expected_observer
                                and (sampler != ROLE_SAMPLER or timing.get('clock') == 'CLOCK_MONOTONIC_RAW')
                                and timing.get('poll_sleep_seconds') == poll)
            causal_valid = causal_precision(bound) if sampler == ROLE_SAMPLER else True
            result.append(dict(app=app, launch=index, lower_seconds=lower, upper_seconds=upper,
                               interval_seconds=width, maximum_interval_seconds=limit,
                               current_observer=current_observer,
                               causal_lower_bound_valid=causal_valid,
                               valid=current_observer and causal_valid and width <= limit))
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
                    rule='Each mapped-window bracket <= min(5ms, 2.5% of observed time); all six boots use the same current observer; role bounds require loss-free same-launch causal receipts',
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
                startup_observation={name: [{app: compact_startup_observation(timing) for app, timing, *_ in mapped_timings(r)}
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


def compact_startup_observation(timing):
    """Keep every bracket; hash raw traces retained in the source guest logs.

    Traces are diagnostics rather than gate inputs. Large raw traces previously
    made the comparison exceed the release preparer's 4 MiB JSON limit.
    """
    result = dict(timing)
    result['observation_bounds'] = []
    for bound in timing.get('observation_bounds', []):
        compact = dict(bound)
        traces = compact.pop('query_roundtrips', None)
        if traces is not None:
            raw = json.dumps(traces, sort_keys=True, separators=(',', ':')).encode()
            durations = sorted(t['socket_seconds'] for t in traces)
            compact['query_roundtrip_summary'] = dict(count=len(traces),
                sha256=hashlib.sha256(raw).hexdigest(), raw_trace_location='source guest log',
                socket_seconds=dict(min=min(durations), median=statistics.median(durations),
                    p95=durations[min(len(durations)-1, math.ceil(len(durations)*.95)-1)],
                    max=max(durations)) if durations else None)
        result['observation_bounds'].append(compact)
    return result


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
