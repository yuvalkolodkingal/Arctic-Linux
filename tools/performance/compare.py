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
CAUSAL_MAPPING_OBSERVER = 'mango-socket-worker-v6-original-appid-preinsert-bracket-raw-clock-autonomous'
SAMPLER = 'cpu-30-pss-6-v6-bounded-native-query'
ROLE_SAMPLER = 'cpu-30-pss-6-v13-original-appid-preinsert-bracket-role-first-use'
ROLE_ORDER = ('terminal', 'files', 'browser')
MAPPING_PROFILES = (
    dict(executable_sha256='1c66767fc0d814e9002306c983524b476edc671de544f3b2a6f755ea7a52dcb1',
         native_audit_sha256='dacb0de958e7ba90099a70b2e66f49756916ed3d42f4e70ac6280f7d4b6a571c',
         function_file_offset=0x430d0, function_size=4109,
         function_sha256='d48615861b8819d95e30fbbf74db46e24f8e3d738e20824e0e598578972004a2',
         instruction_file_offset=0x435de,
         lower_instruction_file_offsets=dict(tail=0x435d9, head=0x43733, scroller=0x43d63),
         client_ext_offset=1584,
         ipc_function_file_offset=0x6b00, ipc_function_size=1234,
         ipc_function_sha256='11c0701eafb910c98f526a26d1926077f94bd411c7739db7066b6ba0742f7ead',
         client_type_offset=0, client_surface_offset=328, xdg_type=0,
         xdg_toplevel_offset=56, xdg_appid_offset=192,
         xwayland_type=2, xwayland_class_offset=144),
    dict(executable_sha256='2f1107221157f47418cfda87dd091a3bb81ecd97dc2945184d0c42de7bbd254b',
         native_audit_sha256='dacb0de958e7ba90099a70b2e66f49756916ed3d42f4e70ac6280f7d4b6a571c',
         function_file_offset=0x43110, function_size=4109,
         function_sha256='3955d4a7db3fac1b5f0f17833562299ab299b2250eb2a4a66e7ac390f2dcb9bc',
         instruction_file_offset=0x4361e,
         lower_instruction_file_offsets=dict(tail=0x43619, head=0x43773, scroller=0x43da3),
         client_ext_offset=1584,
         ipc_function_file_offset=0x6b00, ipc_function_size=1234,
         ipc_function_sha256='11c0701eafb910c98f526a26d1926077f94bd411c7739db7066b6ba0742f7ead',
         client_type_offset=0, client_surface_offset=328, xdg_type=0,
         xdg_toplevel_offset=56, xdg_appid_offset=192,
         xwayland_type=2, xwayland_class_offset=144),
    dict(executable_sha256='67ba9d6d7831e35d028f15acad4cb71575489d26d3e23462f3879b6efa1f7b35',
         native_audit_sha256='dacb0de958e7ba90099a70b2e66f49756916ed3d42f4e70ac6280f7d4b6a571c',
         function_file_offset=0x430d0, function_size=4109,
         function_sha256='11a56d467fe7e444f46fa6da1f91a88ecf1a26bc3c54e4965727438e078a47dd',
         instruction_file_offset=0x435de,
         lower_instruction_file_offsets=dict(tail=0x435d9, head=0x43733, scroller=0x43d63),
         client_ext_offset=1584,
         ipc_function_file_offset=0x6b00, ipc_function_size=1234,
         ipc_function_sha256='11c0701eafb910c98f526a26d1926077f94bd411c7739db7066b6ba0742f7ead',
         client_type_offset=0, client_surface_offset=328, xdg_type=0,
         xdg_toplevel_offset=56, xdg_appid_offset=192,
         xwayland_type=2, xwayland_class_offset=144),
    dict(executable_sha256='98582eccb610fc83282d1e64e975968aff2ddcfd5124d783a2bab78b98f681ca',
         native_audit_sha256='eef982194692b3a10412de30a47afcb3bdc675dec00d29f7840bdaf01d54d80c',
         function_file_offset=0x43110, function_size=4109,
         function_sha256='3955d4a7db3fac1b5f0f17833562299ab299b2250eb2a4a66e7ac390f2dcb9bc',
         instruction_file_offset=0x4361e,
         lower_instruction_file_offsets=dict(tail=0x43619, head=0x43773, scroller=0x43da3),
         client_ext_offset=1584,
         ipc_function_file_offset=0x6b00, ipc_function_size=1234,
         ipc_function_sha256='11c0701eafb910c98f526a26d1926077f94bd411c7739db7066b6ba0742f7ead',
         client_type_offset=0, client_surface_offset=328, xdg_type=0,
         xdg_toplevel_offset=56, xdg_appid_offset=192,
         xwayland_type=2, xwayland_class_offset=144),
    dict(executable_sha256='52e6072d93970d48c067b148a696edd5cb85a3504f1f855fdffaf123b8f7a58f', native_audit_sha256='8b2b265bce2765cfc43a60605fae714c9bae7f0cd3659d1839df84e58708afa8', function_file_offset=0x43110, function_size=4109, function_sha256='3955d4a7db3fac1b5f0f17833562299ab299b2250eb2a4a66e7ac390f2dcb9bc', instruction_file_offset=0x4361e, lower_instruction_file_offsets=dict(tail=0x43619, head=0x43773, scroller=0x43da3), client_ext_offset=1584, ipc_function_file_offset=0x6b00, ipc_function_size=1234, ipc_function_sha256='11c0701eafb910c98f526a26d1926077f94bd411c7739db7066b6ba0742f7ead', client_type_offset=0, client_surface_offset=328, xdg_type=0, xdg_toplevel_offset=56, xdg_appid_offset=192, xwayland_type=2, xwayland_class_offset=144),)
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


def kernel_readbacks_valid(readbacks, pid):
    """Validate literal kernel schemas and effective filters, without tracefs IO."""
    if type(pid) is not int or not 0 < pid < 2**31 or not isinstance(readbacks, dict):
        return False
    names = {'map_create', 'map_listed_xdg', 'map_listed_x11'} | {
        'map_before_' + branch + '_' + kind
        for branch in ('tail', 'head', 'scroller') for kind in ('xdg', 'x11')}
    if set(readbacks) != names:
        return False
    common = [('unsigned short', 'common_type', 0, 2, 0),
              ('unsigned char', 'common_flags', 2, 1, 0),
              ('unsigned char', 'common_preempt_count', 3, 1, 0),
              ('int', 'common_pid', 4, 4, 1)]
    identity = [('unsigned long', '__probe_func', 8, 8, 0),
                ('unsigned long', '__probe_ret_ip', 16, 8, 0),
                ('__data_loc char[]', 'foreign_id', 24, 4, 1)]
    native = [('unsigned long', '__probe_ip', 8, 8, 0),
              ('u32', 'client_type', 16, 4, 0),
              ('__data_loc char[]', 'original_app_id', 20, 4, 1),
              ('__data_loc char[]', 'foreign_id', 24, 4, 1),
              ('__data_loc char[]', 'app_id', 28, 4, 1),
              ('u64', 'client', 32, 8, 0), ('u64', 'handle', 40, 8, 0),
              ('u64', 'owner', 48, 8, 0)]
    event_ids = set()
    field_pattern = re.compile(
        r'[ \t]*field:([^;\n]+);[ \t]*offset:([0-9]{1,5});[ \t]*'
        r'size:([0-9]{1,5});[ \t]*signed:([01]);[ \t]*')
    for name, record in readbacks.items():
        if (not isinstance(record, dict) or set(record) != {
                'format_text', 'format_sha256', 'filter_text', 'filter_sha256'}):
            return False
        for key, limit in (('format', 16384), ('filter', 1024)):
            raw = record[key + '_text']
            if (not isinstance(raw, str) or not 0 < len(raw) <= limit or not raw.endswith('\n')
                    or any(char != '\n' and char != '\t' and not ' ' <= char <= '~' for char in raw)
                    or record[key + '_sha256'] != hashlib.sha256(raw.encode('ascii')).hexdigest()):
                return False
        lines = record['format_text'].splitlines()
        if (len(lines) < 5 or lines[0] != 'name: ' + name
                or not re.fullmatch(r'ID: [1-9][0-9]{0,4}', lines[1])
                or lines[2] != 'format:'):
            return False
        event_id = int(lines[1][4:])
        if event_id > 65535 or event_id in event_ids:
            return False
        event_ids.add(event_id)
        fields, footer = [], None
        for line in lines[3:]:
            if footer is not None:
                return False
            if not line.strip(' \t'):
                continue
            if line.startswith('print fmt: '):
                if footer is not None or not re.fullmatch(r'print fmt: "(?:[^"\\]|\\.)*"(?:, [^\n]+)?', line):
                    return False
                footer = line
                continue
            match = field_pattern.fullmatch(line)
            if footer is not None or not match:
                return False
            declaration = match[1].rsplit(' ', 1)
            if len(declaration) != 2:
                return False
            fields.append((declaration[0], declaration[1], int(match[2]), int(match[3]), int(match[4])))
        expected_footer = (r'print fmt: "(%lx <- %lx) foreign_id=\"%s\"", REC->__probe_func, REC->__probe_ret_ip, __get_str(foreign_id)'
                           if name == 'map_create' else
                           r'print fmt: "(%lx) client_type=%u original_app_id=\"%s\" foreign_id=\"%s\" app_id=\"%s\" client=0x%Lx handle=0x%Lx owner=0x%Lx", REC->__probe_ip, REC->client_type, __get_str(original_app_id), __get_str(foreign_id), __get_str(app_id), REC->client, REC->handle, REC->owner')
        if footer != expected_footer or fields != common + (identity if name == 'map_create' else native):
            return False
        expected_filter = 'common_pid==' + str(pid)
        if name != 'map_create':
            expected_filter += '&&client_type==' + ('0' if name.endswith('_xdg') else '2')
        filter_text = record['filter_text']
        if ('\n' in filter_text[:-1]
                or re.sub(r'[ \t\n]', '', filter_text) != expected_filter
                or not re.fullmatch(r'[ \t]*common_pid[ \t]*==[ \t]*' + str(pid)
                                    + (r'[ \t]*&&[ \t]*client_type[ \t]*==[ \t]*'
                                       + ('0' if name.endswith('_xdg') else '2')
                                       if name != 'map_create' else '') + r'[ \t]*\n', filter_text)):
            return False
    return True


def causal_precision(bound, expected_appids):
    """Require identity provenance, the native insertion bracket and original IPC."""
    if (not isinstance(bound, dict) or not isinstance(expected_appids, (tuple, list))
            or not 0 < len(expected_appids) <= 8
            or any(not isinstance(appid, str) or not re.fullmatch('[a-z0-9._-]{1,128}', appid)
                   or re.fullmatch('[0-9a-f]{32}', appid) for appid in expected_appids)
            or len(set(expected_appids)) != len(expected_appids)):
        return False
    proof = bound.get('causal_lower_bound')
    if not isinstance(proof, dict):
        return False
    if (proof.get('method') != 'wlroots-0.20-and-mango-managed-list-original-appid-preinsert-bracket-raw-v5'
            or proof.get('clock') != 'mono_raw' or proof.get('userspace_clock') != 'CLOCK_MONOTONIC_RAW'
            or bound.get('clock') != 'CLOCK_MONOTONIC_RAW' or proof.get('status') != 'bounded-managed-list-insertion'
            or proof.get('exported_symbol') != 'wlr_ext_foreign_toplevel_handle_v1_create'
            or proof.get('identifier_offset') != 56
            or proof.get('audited_header_sha256') != '9253b1ac1b68011cb304c0c9b84a6678779acc820994131a31f170d26945d0f3'
            or proof.get('audited_source_sha256') != '5580d4b6c803fb3548bbe104f5b0bdbfd5a17b42dd173358aa526ca0e958a088'
            or proof.get('upper_appid_offset') != 48 or proof.get('upper_handle_data_offset') != 80
            or proof.get('audited_original_appid_sha256') != '3c6e8e8582215a02b16ebc24e85c8ca807df70dd6bc1c33f57684f656fc9b692'
            or proof.get('audited_mango_source_sha256') != '586627878578a2545655d4accb790a73112be7eaf6b1dab9d162b4195d962eef'
            or proof.get('audited_mango_header_sha256') != '0c76fd2a2f677170ad9ef27df9296444bfdf1c69cb40a05dadadd51e050d3428'):
        return False
    profile = proof.get('upper_mapping_profile')
    if (not isinstance(profile, dict) or profile not in MAPPING_PROFILES
            or any(type(profile.get(key)) is not int for key in
                   ('function_file_offset','function_size','instruction_file_offset','client_ext_offset',
                    'ipc_function_file_offset','ipc_function_size','client_type_offset','client_surface_offset',
                    'xdg_type','xdg_toplevel_offset','xdg_appid_offset','xwayland_type','xwayland_class_offset'))
            or not isinstance(profile.get('lower_instruction_file_offsets'), dict)
            or set(profile['lower_instruction_file_offsets']) != {'tail', 'head', 'scroller'}
            or any(type(offset) is not int for offset in profile['lower_instruction_file_offsets'].values())
            or proof.get('mango_sha256') != profile['executable_sha256']):
        return False

    def mapping_valid(mapping, offset):
        return (isinstance(mapping, dict)
                and set(mapping) == {'start', 'end', 'file_offset', 'instruction_address'}
                and all(type(value) is int and value >= 0 for value in mapping.values())
                and 0 < mapping['start'] <= mapping['instruction_address'] < mapping['end']
                and mapping['file_offset'] <= offset < mapping['file_offset']+mapping['end']-mapping['start']
                and mapping['instruction_address'] == mapping['start']+offset-mapping['file_offset'])

    mapping = proof.get('upper_executable_mapping')
    lower_mappings = proof.get('lower_executable_mappings')
    if (not mapping_valid(mapping, profile['instruction_file_offset'])
            or proof.get('upper_instruction_address') != mapping['instruction_address']
            or type(proof.get('upper_instruction_address')) is not int
            or not isinstance(lower_mappings, dict) or set(lower_mappings) != {'tail', 'head', 'scroller'}
            or any(not mapping_valid(lower_mappings[branch], offset)
                   for branch, offset in profile['lower_instruction_file_offsets'].items())
            or any(any(lower_mappings[branch][key] != mapping[key] for key in ('start', 'end', 'file_offset'))
                   for branch in lower_mappings)):
        return False
    if any(not isinstance(proof.get(key), str) or not re.fullmatch('[0-9a-f]{64}', proof[key])
           for key in ('library_sha256', 'mango_sha256')):
        return False
    if any(type(proof.get(key)) is not int or proof[key] <= 0
           for key in ('kernel_pid', 'desktop_uid', 'mango_start_ticks', 'exported_file_offset')):
        return False
    if not kernel_readbacks_valid(proof.get('kernel_event_readbacks'), proof['kernel_pid']):
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
    ipc_upper = proof.get('ipc_upper_monotonic_ns')
    identity_events = proof.get('matched_identity_events')
    events = proof.get('matched_events')
    upper_events = proof.get('matched_upper_events')
    ipc_clients = proof.get('matched_ipc_clients')
    if (type(started) is not int or started <= 0 or type(ipc_lower) is not int
            or type(ipc_upper) is not int or not started <= ipc_lower <= ipc_upper
            or not isinstance(events, list) or not 0 < len(events) <= 64
            or not isinstance(identity_events, list) or len(identity_events) != len(events)
            or not isinstance(upper_events, list) or len(upper_events) != len(events)
            or proof.get('application_id_predicate') != list(expected_appids)
            or not isinstance(ipc_clients, list) or len(ipc_clients) != len(events)):
        return False

    def timestamp_valid(event, edge):
        text = event.get('kernel_timestamp_text')
        token = re.fullmatch(r'([0-9]{1,20})\.([0-9]{1,9})', text) if isinstance(text, str) else None
        if not token:
            return False
        literal = int(token[1])*1_000_000_000 + int(token[2].ljust(9, '0'))
        resolution = 10 ** (9-len(token[2]))
        return (resolution in (1, 10, 100, 1000)
                and type(event.get('timestamp_resolution_ns')) is int
                and event['timestamp_resolution_ns'] == resolution
                and type(event.get('kernel_text_monotonic_ns')) is int
                and event['kernel_text_monotonic_ns'] == literal
                and type(event.get('timestamp_rounding_allowance_ns')) is int
                and event['timestamp_rounding_allowance_ns'] == resolution
                and type(event.get(edge + '_monotonic_ns')) is int
                and event[edge + '_monotonic_ns'] == literal + (resolution if edge == 'upper' else -resolution))

    identities = []
    for identity, before, after, ipc_client in zip(identity_events, events, upper_events, ipc_clients):
        if any(not isinstance(event, dict) for event in (identity, before, after, ipc_client)):
            return False
        if (identity.get('event') != 'map_create'
                or not isinstance(identity.get('foreign_toplevel_id'), str)
                or not re.fullmatch('[0-9a-f]{32}', identity['foreign_toplevel_id'])
                or any(type(event.get('kernel_pid')) is not int or event['kernel_pid'] != proof['kernel_pid']
                       for event in (identity, before, after))
                or not timestamp_valid(identity, 'lower') or not timestamp_valid(before, 'lower')
                or not timestamp_valid(after, 'upper')
                or not started <= identity['lower_monotonic_ns'] <= before['lower_monotonic_ns'] <= after['upper_monotonic_ns']
                or before['lower_monotonic_ns'] > ipc_upper
                or after['kernel_text_monotonic_ns']-after['timestamp_resolution_ns'] > ipc_upper
                or any(event.get('foreign_toplevel_id') != identity['foreign_toplevel_id']
                       for event in (before, after, ipc_client))
                or type(ipc_client.get('id')) is not int or ipc_client['id'] <= 0
                or not isinstance(ipc_client.get('appid'), str)
                or not re.fullmatch('[A-Za-z0-9._-]{1,128}', ipc_client['appid'])
                or ipc_client['appid'].lower() not in expected_appids):
            return False
        branch = re.fullmatch(r'map_before_(tail|head|scroller)_(xdg|x11)', before.get('event', '')) if isinstance(before.get('event'), str) else None
        if (not branch or type(before.get('client_type')) is not int or type(after.get('client_type')) is not int
                or before['client_type'] != (profile['xdg_type'] if branch[2] == 'xdg' else profile['xwayland_type'])
                or after.get('event') != 'map_listed_' + branch[2]
                or type(before.get('instruction_address')) is not int
                or before['instruction_address'] != lower_mappings[branch[1]]['instruction_address']
                or type(after.get('instruction_address')) is not int
                or after['instruction_address'] != proof['upper_instruction_address']
                or any(before.get(key) != after.get(key) for key in
                       ('client_type', 'original_app_id', 'app_id', 'client_address', 'handle_address', 'handle_owner_address'))
                or any(not isinstance(before.get(key), str) or not re.fullmatch('[A-Za-z0-9._-]{1,128}', before[key])
                       for key in ('original_app_id', 'app_id'))
                or before['original_app_id'] != before['app_id'] or before['original_app_id'] != ipc_client['appid']
                or any(type(event.get(key)) is not int or not 0 < event[key] < 2**64
                       for event in (before, after) for key in ('client_address', 'handle_address', 'handle_owner_address'))
                or before['handle_owner_address'] != before['client_address']):
            return False
        identities.append(identity['foreign_toplevel_id'])
    lower = max(ipc_lower, min(event['lower_monotonic_ns'] for event in events))
    native_upper = min(ipc_upper, min(event['upper_monotonic_ns'] for event in upper_events))
    return (len(identities) == len(set(identities))
            and len({client['id'] for client in ipc_clients}) == len(events)
            and len({event['client_address'] for event in events}) == len(events)
            and len({event['handle_address'] for event in events}) == len(events)
            and started <= lower <= native_upper
            and all(isinstance(bound.get(key), (float, int)) and not isinstance(bound[key], bool)
                    and math.isfinite(bound[key]) for key in ('lower_seconds', 'upper_seconds'))
            and math.isclose((lower - started) / 1e9, bound['lower_seconds'], abs_tol=1e-9, rel_tol=1e-9)
            and math.isclose((native_upper - started) / 1e9, bound['upper_seconds'], abs_tol=1e-9, rel_tol=1e-9))


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
            causal_valid = (forward_causal_precision(bound, ROLE_APPIDS.get(timing.get('app_id'), ()))
                            if sampler == ROLE_SAMPLER else True)
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


def read_run(path, strict=False):
    records = {}
    exits = []
    text = path.read_text(errors='strict' if strict else 'replace')
    for line in text.splitlines():
        if 'ARCTIC-INSTALLED-SMOKE-EXIT=' in line:
            status = line.split('ARCTIC-INSTALLED-SMOKE-EXIT=', 1)[1].strip()
            exits.append(status)
            if status != '0':
                raise ValueError(f'{path}: installed probe exit was not successful: {status}')
        if 'ARCTIC-PERFORMANCE ' not in line:
            continue
        content = line.split('ARCTIC-PERFORMANCE ', 1)[1]
        if strict:
            def unique(pairs):
                result = {}
                for key, item in pairs:
                    if key in result:
                        raise ValueError('Duplicate canonical JSON field: ' + key)
                    result[key] = item
                return result
            def invalid(number):
                raise ValueError('Non-finite canonical JSON number: ' + number)
            value = json.loads(content, object_pairs_hook=unique, parse_constant=invalid)
            if value.get('stage') != 'installed':
                raise ValueError('Unexpected canonical probe stage')
        else:
            value = json.loads(content)
        if value['stage'] == 'installed':
            if strict and value['check'] in records and not (value['check'].startswith(
                    ('mapped_window_', 'app_workload_')) or value['check'].endswith('_diagnostic')):
                raise ValueError(f'{path}: duplicate canonical probe record: {value["check"]}')
            records[value['check']] = value['value']
    if strict and (exits != ['0'] or any(text.count(marker) != 1 for marker in (
            'ARCTIC-COLLECT-BEGIN', 'ARCTIC-COLLECT-END', 'ARCTIC-PERFORMANCE-CONSOLE-RESTORED'))):
        raise ValueError(f'{path}: missing/duplicate completed original console collection')
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


def compare_checked(runs, *, candidate_commit, candidate_catalog_sha256, candidate_battery_sha256):
    """Use image-source expectations for both the runner and independent replay."""
    for run in runs['candidate']:
        payload = run['measured_payload']
        if '.git' + candidate_commit not in payload['arctic_shell']:
            raise ValueError('Candidate RPM source differs from requested commit')
        if payload['catalog_sha256'].split()[0] != candidate_catalog_sha256:
            raise ValueError('Candidate catalog source changed or was replaced by an update')
        if payload['battery_sha256'].split()[0] != candidate_battery_sha256:
            raise ValueError('Candidate battery source changed or was replaced by an update')
    return compare(runs)


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
        result = compare_checked(runs, candidate_commit=args.candidate_commit,
            candidate_catalog_sha256=args.candidate_catalog_sha256,
            candidate_battery_sha256=args.candidate_battery_sha256)
    except Exception as error:
        result = dict(status='incomplete_or_inconsistent_measurement', error=str(error))
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'regression_gate_passed' else 1



FORWARD_AUDIT_SHA256 = 'd9344fb1fb3a7129871f5a36c710951085e9fe07faa490cf04fd168afe1d00e9'


FORWARD_PEER_SHA256 = 'a3dedf94835b8ab4190d639d6a3c17350e6ada860f7b764a0fdb0facd0bdc3ff'


FORWARD_METHOD = 'wlroots-mango-original-appid-wayland-forward-store-bracket-raw-v6'


FORWARD_PROFILES = (
    dict(path='/usr/lib64/libwayland-server.so.0.26.0', bytes=87160,
         sha256='6f27c2fc1589f9d8e5525ea7729fbf35cbd27d5501f36b068cad4213a665736d',
         owner='libwayland-server\t0\t1.26.0\t1.fc44\tx86_64', offset=0x4290),
    dict(path='/usr/lib64/libwayland-client.so.0.26.0', bytes=66168,
         sha256='cb517c02f6e808257932a4b3f1a4bd1232ce415cdd8e41a854ff0f0e918b51c9',
         owner='libwayland-client\t0\t1.26.0\t1.fc44\tx86_64', offset=0x2f90),
)


def forward_callers(proof):
    return [proof['lower_executable_mappings'][branch]['instruction_address'] + 5
            for branch in ('tail', 'head', 'scroller')]


def forward_readbacks_valid(readbacks, pid, callers):
    """Validate all nine original schemas and four exact store/PID/type/caller schemas."""
    names = {'map_store_' + phase + '_' + kind for phase in ('before', 'after') for kind in ('xdg', 'x11')}
    if (type(readbacks) is not dict or type(callers) is not list or len(callers) != 3
            or len(set(callers)) != 3 or any(type(value) is not int or not 0 < value < 2**64 for value in callers)):
        return False
    outer = {name: record for name, record in readbacks.items() if name not in names}
    if set(readbacks) != set(outer) | names or not kernel_readbacks_valid(outer, pid):
        return False
    ids = [re.search(r'^ID: ([0-9]+)$', record['format_text'], re.M) for record in readbacks.values()]
    if any(value is None for value in ids) or len({value[1] for value in ids}) != 13:
        return False
    old_footer = r'print fmt: "(%lx) client_type=%u original_app_id=\"%s\" foreign_id=\"%s\" app_id=\"%s\" client=0x%Lx handle=0x%Lx owner=0x%Lx", REC->__probe_ip, REC->client_type, __get_str(original_app_id), __get_str(foreign_id), __get_str(app_id), REC->client, REC->handle, REC->owner'
    new_footer = old_footer.replace('owner=0x%Lx"', 'owner=0x%Lx position=0x%Lx link=0x%Lx caller=0x%Lx"') + ', REC->position, REC->link, REC->caller'
    for name in sorted(names):
        record = readbacks[name]
        if type(record) is not dict or set(record) != {'format_text', 'format_sha256', 'filter_text', 'filter_sha256'}:
            return False
        for key, maximum in (('format', 16384), ('filter', 1024)):
            text = record[key + '_text']
            if (type(text) is not str or not 0 < len(text) <= maximum or not text.endswith('\n')
                    or any(c not in '\n\t' and not ' ' <= c <= '~' for c in text)
                    or hashlib.sha256(text.encode('ascii')).hexdigest() != record[key + '_sha256']):
                return False
        kind = name.rsplit('_', 1)[1]
        expected = 'common_pid==' + str(pid) + '&&client_type==' + ('0' if kind == 'xdg' else '2')
        expected += '&&(' + '||'.join('caller==' + str(value) for value in callers) + ')'
        if re.sub(r'[ \t\n]', '', record['filter_text']) != expected or '\n' in record['filter_text'][:-1]:
            return False
        text = record['format_text']
        for field, offset in (('position', 56), ('link', 64), ('caller', 72)):
            pattern = r'^[ \t]*field:u64 ' + field + r';[ \t]*offset:' + str(offset) + r';[ \t]*size:8;[ \t]*signed:0;[ \t]*\n'
            text, count = re.subn(pattern, '', text, flags=re.M)
            if count != 1:
                return False
        if text.count(new_footer) != 1:
            return False
        text = text.replace(new_footer, old_footer).replace('name: ' + name + '\n', 'name: map_listed_' + kind + '\n', 1)
        filter_text = 'common_pid == ' + str(pid) + ' && client_type == ' + ('0' if kind == 'xdg' else '2') + '\n'
        trial = dict(outer)
        trial['map_listed_' + kind] = dict(format_text=text, format_sha256=hashlib.sha256(text.encode()).hexdigest(),
            filter_text=filter_text, filter_sha256=hashlib.sha256(filter_text.encode()).hexdigest())
        if not kernel_readbacks_valid(trial, pid):
            return False
    return True


def forward_events_valid(proof, started, lower, upper):
    """Strict shared producer/replay validation; outer caller/identity checks are additional."""
    provider = proof.get('forward_provider')
    if (type(provider) is not dict or set(provider) != {'profile', 'entry_mapping', 'before_mapping', 'after_mapping',
            'got_address', 'got_virtual_address', 'got_file_offset', 'got_mapping', 'resolved_target', 'inode', 'device', 'rpm_owner', 'audit_sha256', 'peer_sha256'}
            or provider.get('profile') not in FORWARD_PROFILES
            or proof.get('mango_sha256') not in {'67ba9d6d7831e35d028f15acad4cb71575489d26d3e23462f3879b6efa1f7b35',
                '52e6072d93970d48c067b148a696edd5cb85a3504f1f855fdffaf123b8f7a58f'}
            or provider.get('audit_sha256') != FORWARD_AUDIT_SHA256 or provider.get('peer_sha256') != FORWARD_PEER_SHA256
            or provider.get('rpm_owner') != provider['profile']['owner']
            or any(type(provider.get(key)) is not int or provider[key] <= 0 for key in
                   ('got_address', 'got_virtual_address', 'got_file_offset', 'resolved_target', 'inode'))
            or not isinstance(provider.get('device'), str) or not re.fullmatch('[0-9a-f]{2,8}:[0-9a-f]{2,8}', provider['device'])
            or provider['got_virtual_address'] != 0x7ddb8 or provider['got_file_offset'] != 0x7cdb8):
        return False
    got = provider['got_mapping']
    if (type(got) is not dict or set(got) != {'start', 'end', 'file_offset', 'address'}
            or any(type(value) is not int or value < 0 for value in got.values())
            or not (0 < got['start'] <= got['address'] and got['address'] + 8 <= got['end'])
            or got['address'] != provider['got_address']
            or got['address'] != got['start'] + provider['got_file_offset'] - got['file_offset']):
        return False
    for key, delta in (('entry_mapping', 0), ('before_mapping', 15), ('after_mapping', 19)):
        mapping = provider.get(key)
        offset = provider['profile']['offset'] + delta
        if (type(mapping) is not dict or set(mapping) != {'start', 'end', 'file_offset', 'instruction_address'}
                or any(type(value) is not int or value < 0 for value in mapping.values())
                or not 0 < mapping['start'] <= mapping['instruction_address'] < mapping['end']
                or not mapping['file_offset'] <= offset < mapping['file_offset'] + mapping['end'] - mapping['start']
                or mapping['instruction_address'] != mapping['start'] + offset - mapping['file_offset']
                or any(mapping[field] != provider['entry_mapping'][field] for field in ('start', 'end', 'file_offset'))):
            return False
    mango = proof.get('upper_executable_mapping', {})
    if (provider['resolved_target'] != provider['entry_mapping']['instruction_address']
            or provider['got_address'] != mango.get('start', 0) - mango.get('file_offset', 0) + provider['got_virtual_address']
            or not forward_readbacks_valid(proof.get('kernel_event_readbacks'), proof.get('kernel_pid'), forward_callers(proof))):
        return False
    outer_before, outer_after = proof.get('matched_events'), proof.get('matched_upper_events')
    before, after = proof.get('matched_store_before_events'), proof.get('matched_store_after_events')
    if (any(type(events) is not list for events in (outer_before, outer_after, before, after))
            or not 0 < len(before) <= 64 or len({len(events) for events in (outer_before, outer_after, before, after)}) != 1):
        return False
    for old_before, old_after, first, second in zip(outer_before, outer_after, before, after):
        if any(type(event) is not dict for event in (old_before, old_after, first, second)):
            return False
        branch = re.fullmatch('map_before_(tail|head|scroller)_(xdg|x11)', old_before.get('event', ''))
        if not branch:
            return False
        for phase, edge, event in (('before', 'lower', first), ('after', 'upper', second)):
            text = event.get('kernel_timestamp_text')
            token = re.fullmatch(r'([0-9]{1,20})\.([0-9]{1,9})', text) if type(text) is str else None
            if not token:
                return False
            resolution = 10 ** (9 - len(token[2]))
            literal = int(token[1])*1_000_000_000 + int(token[2].ljust(9, '0'))
            if (resolution > 1000 or event.get('event') != 'map_store_' + phase + '_' + branch[2]
                    or any(type(event.get(key)) is not int for key in ('kernel_pid', 'instruction_address', 'client_type',
                        'client_address', 'handle_address', 'handle_owner_address', 'position_address', 'link_address', 'caller_address',
                        'kernel_text_monotonic_ns', 'timestamp_resolution_ns', 'timestamp_rounding_allowance_ns', edge + '_monotonic_ns'))
                    or event['kernel_text_monotonic_ns'] != literal or event['timestamp_resolution_ns'] != resolution
                    or event['timestamp_rounding_allowance_ns'] != resolution
                    or event[edge + '_monotonic_ns'] != literal + (resolution if edge == 'upper' else -resolution)
                    or event['instruction_address'] != provider[phase + '_mapping']['instruction_address']
                    or event['caller_address'] != proof['lower_executable_mappings'][branch[1]]['instruction_address'] + 5
                    or event['link_address'] != old_before['client_address'] + 280
                    or not 0 < event['position_address'] < 2**64
                    or (branch[1] == 'head' and event['position_address'] != mango['start'] - mango['file_offset'] + 0x7f348)
                    or any(event.get(key) != old_before.get(key) for key in ('kernel_pid', 'foreign_toplevel_id',
                        'client_type', 'original_app_id', 'app_id', 'client_address', 'handle_address', 'handle_owner_address'))):
                return False
        if (first['position_address'] != second['position_address']
                or not old_before['kernel_text_monotonic_ns'] <= first['kernel_text_monotonic_ns'] <= second['kernel_text_monotonic_ns'] <= old_after['kernel_text_monotonic_ns']):
            return False
    expected_lower = max(proof['ipc_lower_monotonic_ns'], min(event['lower_monotonic_ns'] for event in before))
    expected_upper = min(proof['ipc_upper_monotonic_ns'], min(event['upper_monotonic_ns'] for event in after))
    return (all(type(value) is int for value in (started, lower, upper))
            and started <= lower <= upper <= proof['ipc_upper_monotonic_ns']
            and lower == expected_lower and upper == expected_upper)


def forward_causal_precision(bound, expected_appids):
    """A genuine inner instruction bracket plus every original outer witness."""
    try:
        if type(bound) is not dict or type(bound.get('causal_lower_bound')) is not dict:
            return False
        proof = bound['causal_lower_bound']
        if proof.get('method') != FORWARD_METHOD:
            return False
        started = bound.get('launch_started_monotonic_ns')
        first, last = bound.get('lower_seconds'), bound.get('upper_seconds')
        if (type(started) is not int or started <= 0
                or any(type(value) not in (int, float) or not math.isfinite(value) for value in (first, last))):
            return False
        lower = max(proof['ipc_lower_monotonic_ns'], min(event['lower_monotonic_ns'] for event in proof['matched_store_before_events']))
        upper = min(proof['ipc_upper_monotonic_ns'], min(event['upper_monotonic_ns'] for event in proof['matched_store_after_events']))
        if (not forward_events_valid(proof, started, lower, upper)
                or not math.isclose((lower-started)/1e9, first, abs_tol=1e-9, rel_tol=1e-9)
                or not math.isclose((upper-started)/1e9, last, abs_tol=1e-9, rel_tol=1e-9)):
            return False
        outer_proof = dict(proof, method='wlroots-0.20-and-mango-managed-list-original-appid-preinsert-bracket-raw-v5',
            kernel_event_readbacks={name: record for name, record in proof['kernel_event_readbacks'].items() if not name.startswith('map_store_')})
        outer_lower = max(proof['ipc_lower_monotonic_ns'], min(event['lower_monotonic_ns'] for event in proof['matched_events']))
        outer_upper = min(proof['ipc_upper_monotonic_ns'], min(event['upper_monotonic_ns'] for event in proof['matched_upper_events']))
        outer = dict(bound, causal_lower_bound=outer_proof, lower_seconds=(outer_lower-started)/1e9, upper_seconds=(outer_upper-started)/1e9)
        return causal_precision(outer, expected_appids)
    except (KeyError, TypeError, ValueError, IndexError):
        return False


if __name__ == '__main__':
    raise SystemExit(main())
