"""First-use role qualification must fail closed without launching real GUI apps."""
import copy
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
from urllib.request import urlopen

ROOT = Path(__file__).parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guest = load('role_guest', ROOT/'tools/performance/guest.py')
comparison = load('role_compare', ROOT/'tools/performance/compare.py')
legacy = load('legacy_fixture', ROOT/'tools/tests/test_performance_compare.py')


def role_run(image, number):
    result = legacy.run(image + str(number))
    result['identity']['sampler'] = comparison.ROLE_SAMPLER
    records = sorted(['kitty-0:1-1.x86_64', 'nautilus-0:1-1.x86_64'] if image == 'baseline'
                     else ['foot-0:1-1.x86_64', 'pcmanfm-0:1-1.x86_64', 'epiphany-0:1-1.x86_64', 'epiphany-runtime-0:1-1.x86_64'])
    result['rpm_inventory'] = dict(nevra=records,
        sha256=hashlib.sha256(('\n'.join(records)+'\n').encode()).hexdigest())
    roles, configured, programs = {}, {}, {}
    for role, ident in guest.EXPECTED_ROLES[image].items():
        app = guest.ROLE_APPS[ident]
        configured[role] = app['configured'][0]
        programs[app['program']] = '/usr/bin/' + app['program']
        package = (dict(kind='flatpak', ref=app['flatpak'], commit='a'*64) if ident == 'zen' else
                   dict(kind='rpm', nevra=next(value for value in records if value.startswith(app['rpm']+'-'))))
        if package['kind'] == 'rpm':
            package['binary_owner'] = package['nevra']
            if ident=='gnome-web':
                runtime='epiphany-runtime-0:1-1.x86_64'
                package.update(binary_owner=runtime,runtime_nevra=runtime,ownership_model='epiphany-frontend-runtime-v1',executable_path='/usr/bin/epiphany',rpm_header_sha256=comparison.EPIPHANY_EXPECTED_NATIVE_ELF_SHA256,prelaunch_content_bytes_read=0,elf_magic_checked_bytes=0,payload_integrity_model='full-hash-after-first-gui-v1',prelaunch_file_identity=dict(device=1,inode=2,size=4096,mtime_ns=3,ctime_ns=4))
        roles[role] = dict(id=ident, role=role, configured_command=configured[role],
            legacy_system_mime_fallback=False, program_path=programs[app['program']],
            appids=list(app['appids']), package=package)
        for phase in ('cold', 'warm'):
            values = [.04] if phase == 'cold' else [.03, .029, .031]
            result['startup_role_'+role+'_'+phase+'_seconds'] = dict(first=values[0],
                **({'warm': values[1:]} if phase == 'warm' else {}),
                observation_bounds=[dict(lower_seconds=value-.00025, upper_seconds=value,
                    interval_seconds=.00025, observer=guest.MAPPING_OBSERVER) for value in values],
                observer=guest.MAPPING_OBSERVER, poll_sleep_seconds=guest.ROLE_POLL_SECONDS,
                app_id=ident, phase=('first_gui_role_execution_from_pristine_install' if phase == 'cold'
                                    else 'after_45_second_preconditioning'))
        result['precondition_role_'+role] = dict(persistent_hold_seconds=45, app_id=ident,launch_started_monotonic_ns=1_002_000_000_000)
    result['app_roles'] = dict(image=image, roles=roles,
        configuration_sources=[dict(path='/etc/arctic/default-apps', sha256='c'*64)],
        default_browser_desktop=guest.ROLE_APPS[guest.EXPECTED_ROLES[image]['browser']]['desktop'],
        pristine_state=dict(uid=1000, configured=configured, programs=programs,
                            prior_role_state_paths=[], running_role_apps=[]),
        boot_context=dict(image=image, boot=number, fresh_installed_overlay=True, collector='console',
            installed_base_sha256=('b' if image == 'baseline' else 'c')*64,
            firmware_variables_sha256='d'*64,
            install_profile_sha256=(comparison.BASELINE_PROFILE_SHA256 if image == 'baseline' else 'f'*64),
            iso_sha256=(comparison.BASELINE_ISO_SHA256 if image == 'baseline' else 'e'*64)))
    result['role_workload'] = dict(uid=1000, files='/tmp/arctic-performance-files-fixture',
        pid=4242, start_ticks=100,
        url='http://127.0.0.1:1234/benchmark.html', page_sha256=comparison.WORKLOAD_PAGE_SHA256,
        file_count=16, file_payload_sha256=hashlib.sha256(b'Arctic file fixture\n').hexdigest())
    result['role_measurement_order'] = ['pristine_idle', *[phase+':'+role for phase in ('cold', 'precondition', 'warm')
                                       for role in guest.ROLE_ORDER]]
    result['pristine_idle_measurement_scope'] = dict(phase='before_any_gui_role_or_workload_worker',
        collector_present=True, workload_worker_present=False)
    result['pristine_idle_samples'] = copy.deepcopy(result['idle_samples'])
    for sample in result['idle_samples']:
        sample.update(cpu_clock_ticks_per_second=100, sample_elapsed_seconds=1,
                      benchmark_worker_cpu=dict(pid=4242,uid=1000,start_ticks=100,ticks_delta=1,
                                                percent_one_core=1,resolution_percent_one_core=1))
    for role in guest.ROLE_ORDER:
        for phase in ('cold','warm'):
            for bound in result['startup_role_'+role+'_'+phase+'_seconds']['observation_bounds']:legacy.worker_proof(bound)
    if image=='candidate':
        package=roles['browser']['package'];bound=result['startup_role_browser_cold_seconds']['observation_bounds'][0]
        result['role_payload_integrity']=dict(status='verified',boot_id=result['identity']['boot_id'],image=image,boot=number,desktop_uid=1000,role='browser',app_id='gnome-web',path='/usr/bin/epiphany',
            phase='immediately_after_first_gui_before_any_preconditioning',executable_sha256=package['rpm_header_sha256'],
            rpm_header_sha256=package['rpm_header_sha256'],declaration_identity=package['prelaunch_file_identity'],
            before_hash_identity=copy.deepcopy(package['prelaunch_file_identity']),after_hash_identity=copy.deepcopy(package['prelaunch_file_identity']),
            first_gui_launch_ns=bound['launch_started_monotonic_ns'],first_gui_map_upper_ns=bound['first_present_query']['worker_received_ns'],
            measurement_returned_ns=1_000_100_000_000,hash_started_ns=1_000_100_000_001,hash_finished_ns=1_000_100_000_002)
    return result


def paired_roles():
    return {image: [role_run(image, number) for number in (1, 2, 3)] for image in ('baseline', 'candidate')}


def qualified_compare(runs):
    return comparison.compare(legacy.with_worker_proofs(runs))

class RoleQualificationTest(unittest.TestCase):
    def test_normalized_private_samples_cannot_be_dropped_or_moved(self):
        for image in ('baseline','candidate'):
            for fault in ('drop','move'):
                runs=paired_roles();samples=runs[image][0]['idle_samples']
                if fault=='drop':
                    for sample in samples[5::5]:sample.pop('process_private_bytes')
                else:samples[1]['process_private_bytes']=samples[0].pop('process_private_bytes')
                with self.subTest(image=image,fault=fault),self.assertRaises(ValueError):qualified_compare(runs)

    def test_explicit_failed_probe_marker_cannot_be_hidden_by_a_done_record(self):
        fixture=role_run('candidate',1)
        lines='\n'.join('ARCTIC-PERFORMANCE '+json.dumps(dict(stage='installed',check=key,value=value))
                        for key,value in fixture.items())
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'serial.log'
            for status in ('3','-15','', 'True'):
                path.write_text(lines+'\nARCTIC-INSTALLED-SMOKE-EXIT='+status+'\n')
                with self.subTest(status=status),self.assertRaises(ValueError):comparison.read_run(path)
            path.write_text(lines+'\nARCTIC-INSTALLED-SMOKE-EXIT=0\n')
            self.assertTrue(comparison.read_run(path)['done'])

    def test_both_idle_phases_validate_raw_memory_before_median_boolean_coercion(self):
        for phase in ('pristine_idle_samples','idle_samples'):
            for name in ('process_pss_bytes','process_private_bytes','MemAvailable'):
                runs=paired_roles()
                for run in runs['candidate']:
                    for sample in run[phase]:
                        if name=='MemAvailable':sample['memory_bytes'][name]=True
                        elif name in sample:sample[name]=True
                with self.subTest(phase=phase,name=name),self.assertRaises(ValueError):qualified_compare(runs)

    def test_pristine_idle_has_distinct_memory_gate_and_raw_cpu_accounting(self):
        for factor, expected in ((1.05, 'regression_gate_passed'), (1.05001, 'regression_gate_failed')):
            runs = paired_roles()
            for run in runs['candidate']:
                for sample in run['pristine_idle_samples'][::5]:
                    sample['process_pss_bytes'] = int(sample['process_pss_bytes'] * factor)
            result = qualified_compare(runs)
            self.assertEqual(result['status'], expected)
            metric = next(row for row in result['metrics'] if row['metric']=='pristine_process_pss_bytes')
            self.assertEqual(metric['regression_threshold_percent'], 5)
            self.assertEqual(result['pristine_idle_cpu_validity']['baseline'][0]['busy_ticks'], 90)
            self.assertEqual(result['idle_cpu_validity']['candidate'][0]['temporary_worker_cpu'][0]['ticks_delta'], 1)
            normalized = next(row for row in result['metrics'] if row['metric']=='process_pss_bytes')
            self.assertFalse(normalized['regression'])

    def test_missing_contaminated_pristine_and_forged_worker_cpu_fail_closed(self):
        for fault in ('missing','short','no_private','contaminated','worker_present','after_roles',
                      'missing_worker','wrong_pid','negative_ticks','forged_percent','bad_resolution','frozen_pristine'):
            runs = paired_roles(); run = runs['candidate'][0]
            if fault=='missing': run.pop('pristine_idle_samples')
            elif fault=='short': run['pristine_idle_samples'].pop()
            elif fault=='no_private': run['pristine_idle_samples'][0].pop('process_private_bytes')
            elif fault=='contaminated': run['pristine_idle_samples'][0]['benchmark_worker_cpu'] = {}
            elif fault=='worker_present': run['pristine_idle_measurement_scope']['workload_worker_present'] = True
            elif fault=='after_roles': run['role_measurement_order'].append(run['role_measurement_order'].pop(0))
            elif fault=='missing_worker': run['idle_samples'][0].pop('benchmark_worker_cpu')
            elif fault=='wrong_pid': run['idle_samples'][0]['benchmark_worker_cpu']['pid'] += 1
            elif fault=='negative_ticks': run['idle_samples'][0]['benchmark_worker_cpu']['ticks_delta'] = -1
            elif fault=='forged_percent': run['idle_samples'][0]['benchmark_worker_cpu']['percent_one_core'] = 0
            elif fault=='bad_resolution': run['idle_samples'][0]['benchmark_worker_cpu']['resolution_percent_one_core'] = 0
            else: run['pristine_idle_samples'][0].update(cpu_ticks_delta=0,cpu_idle_ticks_delta=0)
            with self.subTest(fault=fault), self.assertRaises(ValueError): qualified_compare(runs)

    def test_declared_different_applications_have_distinct_cold_and_warm_metrics(self):
        result = qualified_compare(paired_roles())
        self.assertEqual(result['status'], 'regression_gate_passed')
        metrics = {metric['metric']: metric for metric in result['metrics']}
        self.assertEqual(metrics['terminal_first_gui_role_mapped']['application_identity'],
                         dict(baseline='kitty', candidate='foot'))
        self.assertEqual(metrics['files_subsequent_mapped']['application_identity'],
                         dict(baseline='nautilus', candidate='pcmanfm'))
        self.assertEqual(metrics['browser_first_mapped_after_preconditioning']['application_identity'],
                         dict(baseline='zen', candidate='gnome-web'))
        self.assertEqual(len(result['startup_observation']['candidate'][0]), 6)
        self.assertNotIn('kitty_subsequent_mapped', metrics)
        self.assertTrue(any('historical Kitty regression' in text for text in result['limitations']))

    def test_missing_app_wrong_default_and_wrong_package_cannot_pass(self):
        for fault in ('missing_role', 'wrong_app', 'wrong_command', 'wrong_mime', 'missing_rpm',
                      'wrong_owner', 'missing_cold', 'missing_warm', 'mixed_legacy', 'wrong_flatpak'):
            runs = paired_roles()
            run = runs['candidate'][0]
            app = run['app_roles']['roles']['files']
            if fault == 'missing_role': run['app_roles']['roles'].pop('files')
            elif fault == 'wrong_app': app['id'] = 'nautilus'
            elif fault == 'wrong_command': app['configured_command'] = 'missing-app'
            elif fault == 'wrong_mime': run['app_roles']['default_browser_desktop'] = 'chromium.desktop'
            elif fault == 'missing_rpm': app['package']['nevra'] = 'pcmanfm-0:99-99.x86_64'
            elif fault == 'wrong_owner': app['package']['binary_owner'] = 'nix-foot'
            elif fault == 'missing_cold': run.pop('startup_role_files_cold_seconds')
            elif fault == 'missing_warm': run.pop('startup_role_files_warm_seconds')
            elif fault == 'mixed_legacy': run.pop('app_roles')
            else: runs['baseline'][0]['app_roles']['roles']['browser']['package']['commit'] = ''
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                qualified_compare(runs)

    def test_reused_profiles_preconditioned_cold_and_changed_source_are_rejected(self):
        for fault in ('running', 'profile', 'dirty', 'terminal_collector', 'order', 'cold_label',
                      'duplicate_boot', 'base_changed', 'profile_changed', 'historical_profile', 'remote_page'):
            runs = paired_roles()
            run = runs['candidate'][0]
            declared = run['app_roles']
            if fault == 'running': declared['pristine_state']['running_role_apps'] = [dict(pid=42, name='foot')]
            elif fault == 'profile': declared['pristine_state']['prior_role_state_paths'] = ['/home/ci/.cache/foot']
            elif fault == 'dirty': declared['boot_context']['fresh_installed_overlay'] = False
            elif fault == 'terminal_collector': declared['boot_context']['collector'] = 'terminal'
            elif fault == 'order': run['role_measurement_order'][:2] = ['precondition:terminal', 'cold:terminal']
            elif fault == 'cold_label': run['startup_role_files_cold_seconds']['phase'] = 'after_45_second_preconditioning'
            elif fault == 'duplicate_boot': declared['boot_context']['boot'] = 2
            elif fault == 'base_changed': declared['boot_context']['installed_base_sha256'] = '9'*64
            elif fault == 'profile_changed': declared['boot_context']['install_profile_sha256'] = '9'*64
            elif fault == 'historical_profile': runs['baseline'][0]['app_roles']['boot_context']['install_profile_sha256'] = '9'*64
            else: run['role_workload']['url'] = 'https://example.com/'
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                qualified_compare(runs)

    def test_cold_and_warm_regressions_and_fast_precision_are_independent(self):
        for phase in ('cold', 'warm'):
            runs = paired_roles()
            for run in runs['candidate']:
                timing = run['startup_role_terminal_'+phase+'_seconds']
                values = [.06] if phase == 'cold' else [.04, .04, .04]
                timing['first'] = values[0]
                if phase == 'warm': timing['warm'] = values[1:]
                timing['observation_bounds'] = [dict(lower_seconds=value-.00025, upper_seconds=value,
                    interval_seconds=.00025, observer=guest.MAPPING_OBSERVER) for value in values]
            result = qualified_compare(runs)
            self.assertEqual(result['status'], 'regression_gate_failed')
            suffix = 'first_gui_role_mapped' if phase == 'cold' else 'subsequent_mapped'
            self.assertTrue(next(row for row in result['metrics'] if row['metric']=='terminal_'+suffix)['regression'])
        runs = paired_roles()
        bound = runs['candidate'][0]['startup_role_terminal_cold_seconds']['observation_bounds'][0]
        bound.update(lower_seconds=.0389, interval_seconds=.0011)
        result = qualified_compare(runs)
        self.assertEqual(result['status'], 'measurement_precision_gate_failed')
        self.assertFalse(result['measurement_precision']['valid'])
        self.assertFalse(any(row['regression'] for row in result['metrics']))

    def test_role_cold_near_threshold_uncertainty_does_not_invent_or_clear_regression(self):
        runs = paired_roles()
        for image, group in runs.items():
            lower, upper = ((.03992, .04) if image == 'baseline' else (.04392, .04396))
            for run in group:
                timing = run['startup_role_terminal_cold_seconds']
                timing.update(first=upper, observation_bounds=[dict(lower_seconds=lower, upper_seconds=upper,
                    interval_seconds=upper-lower, observer=guest.MAPPING_OBSERVER)])
        result = qualified_compare(runs)
        self.assertEqual(result['status'], 'measurement_precision_gate_failed')
        self.assertTrue(result['measurement_precision']['valid'])
        self.assertFalse(result['measurement_precision']['threshold_enclosure_valid'])
        metric = next(row for row in result['metrics'] if row['metric']=='terminal_first_gui_role_mapped')
        self.assertFalse(metric['regression'])
        self.assertGreater(metric['observation_enclosure']['possible_percent_difference_upper'], 10)


class RoleDeclarationTest(unittest.TestCase):
    def main_fixture(self, fault=None):
        fixture = role_run('candidate',1)
        events, emissions = [], {}
        actual_path = Path
        def path(value):
            if str(value)=='/run/t/performance-context.json':
                return types.SimpleNamespace(read_text=lambda:json.dumps(fixture['app_roles']['boot_context']))
            return actual_path(value)
        def run(argv, **kwargs):
            if argv[0]=='systemd-detect-virt': return 'qemu'
            if 'arctic-keep-awake' in argv:
                return '{"on":true}' if fault=='awake' and 'off' in argv else '{"on":false}'
            return 'fixture'
        def idle(*args, **kwargs):
            events.append('pristine_idle')
            return fixture['pristine_idle_samples']
        @contextmanager
        def workload(prefix):
            events.append('worker_start')
            yield fixture['role_workload']
            events.append('worker_stop')
            if fault=='cleanup':raise RuntimeError('Injected workload cleanup error')
        def cold(*args):
            events.append('cold_and_precondition')
            if fault!='integrity':args[1]['roles']['browser']['package']['post_first_gui_integrity']=fixture['role_payload_integrity']
            return [phase+':'+role for phase in ('cold','precondition') for role in guest.ROLE_ORDER]
        def measure(prefix,declared,worker,order,complete=True):
            self.assertFalse(complete)
            events.append('normalized_and_warm')
            if fault=='measure':raise RuntimeError('Injected measurement error')
            order.extend('warm:'+role for role in guest.ROLE_ORDER)
        error=None
        with patch.object(guest,'__file__','/run/t/frozen-observer.py'), patch.object(guest,'Path',side_effect=path), \
                patch.object(guest.os,'geteuid',return_value=0), patch.object(guest,'run',side_effect=run), \
                patch.object(guest,'desktop',return_value=['actual-user']), \
                patch.object(guest,'rpm_inventory',return_value=fixture['rpm_inventory']), \
                patch.object(guest,'declare_roles',return_value=fixture['app_roles']), \
                patch.object(guest,'collect_idle',side_effect=idle), patch.object(guest,'role_workload',side_effect=workload), \
                patch.object(guest,'first_use_and_precondition',side_effect=cold), patch.object(guest,'measure',side_effect=measure), \
                patch.object(guest,'emit',side_effect=lambda key,value:emissions.update({key:value})):
            try:guest.main(preconditioned=True)
            except RuntimeError as raised:error=raised
        return events,emissions,error,fixture

    def test_production_main_samples_pristine_idle_before_worker_or_role_execution(self):
        events,emissions,error,fixture=self.main_fixture()
        self.assertIsNone(error)
        self.assertEqual(events,['pristine_idle','worker_start','cold_and_precondition','normalized_and_warm','worker_stop'])
        self.assertEqual(emissions['role_measurement_order'],fixture['role_measurement_order'])
        self.assertFalse(emissions['pristine_idle_measurement_scope']['workload_worker_present'])
        self.assertTrue(emissions['done'])

    def test_final_completion_is_absent_after_measure_worker_or_session_restore_failure(self):
        for fault in ('measure','cleanup','awake','integrity'):
            events,emissions,error,_=self.main_fixture(fault)
            self.assertIsInstance(error,RuntimeError)
            self.assertNotIn('done',emissions)
            self.assertIn('keep_awake_restored',emissions)

    def test_all_embedded_worker_programs_compile(self):
        for program in (guest.CLIENT_QUERY_WORKER,guest.ROLE_STATE_READER,guest.WORKLOAD_WORKER):
            compile(program,'<actual embedded worker>','exec')

    def test_live_helper_cpu_reader_rejects_recycled_pid_wrong_uid_and_zombie(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); proc=root/'42';proc.mkdir()
            worker=dict(pid=42,uid=proc.stat().st_uid,start_ticks=100)
            values=['S']+['0']*19;values[11]='7';values[12]='3';values[19]='100'
            (proc/'stat').write_text('42 (python (fixture)) '+' '.join(values))
            self.assertEqual(guest.worker_cpu_ticks(worker,root),10)
            for fault in ('uid','recycled','zombie'):
                changed=dict(worker)
                if fault=='uid': changed['uid']+=1
                elif fault=='recycled':changed['start_ticks']+=1
                else:
                    values[0]='Z';(proc/'stat').write_text('42 (python (fixture)) '+' '.join(values))
                with self.subTest(fault=fault),self.assertRaises(RuntimeError): guest.worker_cpu_ticks(changed,root)

    def declare(self, image, mutation=None):
        fixture = role_run(image, 1)
        state = copy.deepcopy(fixture['app_roles']['pristine_state'])
        state['sources'] = fixture['app_roles']['configuration_sources']
        if mutation: mutation(state)
        calls = []
        def run(argv, **kwargs):
            calls.append(argv)
            if 'python3' in argv: return json.dumps(state)
            if 'xdg-settings' in argv: return fixture['app_roles']['default_browser_desktop']
            if 'flatpak' in argv: return 'a'*64
            if argv[:2] == ['rpm', '-qf']:
                program = Path(argv[-1]).name
                if program=='epiphany':
                    if '[' in argv[3]:return '/usr/bin/epiphany\t'+hashlib.sha256(b'\x7fELFfixture').hexdigest()+'\t\n'
                    return 'epiphany-runtime-0:1-1.x86_64'
                return next(value for value in fixture['rpm_inventory']['nevra'] if value.startswith(program+'-'))
            raise AssertionError('Unexpected command: '+repr(argv))
        with patch.object(guest, 'run', side_effect=run), \
                patch.object(guest,'EPIPHANY_EXPECTED_NATIVE_ELF_SHA256',hashlib.sha256(b'\x7fELFfixture').hexdigest()),patch.object(guest.pwd, 'getpwnam', return_value=types.SimpleNamespace(pw_uid=1000)), patch.object(guest,'epiphany_file_identity',return_value=dict(device=1,inode=2,size=4096,mtime_ns=3,ctime_ns=4)), patch.object(guest,'Path',side_effect=lambda value:types.SimpleNamespace(is_symlink=lambda:False,is_file=lambda:True,resolve=lambda strict:Path('/usr/bin/epiphany'),open=lambda mode:__import__('io').BytesIO(b'\x7fELFfixture'),read_bytes=lambda:b'\x7fELFfixture') if str(value)=='/usr/bin/epiphany' else Path(value)):
            result = guest.declare_roles(['runuser', '-u', 'ci', '--', 'env'],
                                         fixture['app_roles']['boot_context'], fixture['rpm_inventory'])
        return result, calls

    def test_actual_installed_defaults_and_owned_executables_are_declared_without_gui_launch(self):
        for image in ('baseline', 'candidate'):
            result, calls = self.declare(image)
            self.assertEqual({role: app['id'] for role, app in result['roles'].items()}, guest.EXPECTED_ROLES[image])
            self.assertFalse(any('run' in call[call.index('flatpak')+1:] for call in calls if 'flatpak' in call))
            self.assertTrue(any(call[:2] == ['rpm', '-qf'] for call in calls))
        result, _ = self.declare('baseline', lambda state: state['configured'].pop('browser'))
        self.assertTrue(result['roles']['browser']['legacy_system_mime_fallback'])

    def test_missing_selected_program_and_arbitrary_installed_browser_never_substitute(self):
        mutations = [lambda state: state['programs'].update(foot=None),
                     lambda state: state['configured'].pop('browser'),
                     lambda state: state['configured'].update(browser='chromium'),
                     lambda state: state['prior_role_state_paths'].append('/home/ci/.local/share/epiphany'),
                     lambda state: state['running_role_apps'].append(dict(pid=42, name='pcmanfm'))]
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(RuntimeError):
                self.declare('candidate', mutation)

    def test_first_gui_execution_precedes_all_preconditioning_with_same_offline_workload(self):
        declared = role_run('candidate', 1)['app_roles']
        workload = dict(files='/tmp/arctic-performance-files-fixture', url='http://127.0.0.1:1234/benchmark.html')
        calls, emitted = [], {}
        def start(prefix, command, appids, **kwargs):
            calls.append((command, kwargs.get('hold_seconds', 5)))
            if 'observations' in kwargs: kwargs['observations'].append(dict(lower_seconds=.03975,upper_seconds=.04,launch_started_monotonic_ns=1_000_000_000,first_present_query=dict(worker_received_ns=1_040_000_000)))
            return .04
        with patch.object(guest,'epiphany_file_identity',return_value=declared['roles']['browser']['package']['prelaunch_file_identity']),patch.object(guest,'verify_role_payload_after_first_gui'),patch.object(guest, 'startup', side_effect=start), \
                patch.object(guest, 'emit', side_effect=lambda key,value: emitted.update({key:value})):
            order = guest.first_use_and_precondition(['actual-user'], declared, workload)
        self.assertEqual([hold for _,hold in calls], [5,5,5,45,45,45])
        self.assertEqual(order, ['cold:terminal','cold:files','cold:browser',
                                 'precondition:terminal','precondition:files','precondition:browser'])
        self.assertEqual(calls[1][0], ['pcmanfm','--new-win',workload['files']])
        self.assertEqual(calls[2][0], ['epiphany','--new-window',workload['url']])
        self.assertEqual(calls[:3], [(command,5) for command,_ in calls[3:]])
        self.assertTrue(all(emitted['startup_role_'+role+'_cold_seconds']['phase'].startswith('first_gui')
                            for role in guest.ROLE_ORDER))

    def test_preseed_pcmanfm_configuration_is_not_runtime_use_but_cache_is(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = home/'.config/pcmanfm/default'
            config.mkdir(parents=True)
            (config/'pcmanfm.conf').write_text('[ui]\nview_mode=icon\n')
            argv = ['env', 'HOME='+directory, 'XDG_CONFIG_HOME='+str(home/'.config'),
                    'XDG_DATA_HOME='+str(home/'.local/share'), 'XDG_CACHE_HOME='+str(home/'.cache'),
                    'python3', '-c', guest.ROLE_STATE_READER, json.dumps(guest.ROLE_APPS['pcmanfm']['cold_paths'])]
            before = json.loads(subprocess.check_output(argv, text=True))
            self.assertEqual(before['prior_role_state_paths'], [])
            (home/'.cache/pcmanfm').mkdir(parents=True)
            after = json.loads(subprocess.check_output(argv, text=True))
            self.assertEqual(after['prior_role_state_paths'], [str(home/'.cache/pcmanfm')])

    def test_real_loopback_workload_serves_no_remote_payload_and_reaps_fixture(self):
        username = pwd.getpwuid(os.getuid()).pw_name
        prefix = ['runuser','-u',username,'--','env'] if os.getuid() == 0 else ['env','--',username]
        # Non-root hosts cannot run runuser; keep production launch and UID
        # validation while replacing only its prefix with the current process.
        if os.getuid() != 0:
            prefix = ['env','ARCTIC_TEST=current',username]
        original = guest.subprocess.Popen
        processes = []
        def start(argv, **kwargs):
            command = argv if os.getuid() == 0 else argv[len(prefix):]
            process = original(command, **kwargs)
            processes.append(process)
            return process
        with patch.object(guest.subprocess, 'Popen', side_effect=start):
            with guest.role_workload(prefix) as workload:
                folder = Path(workload['files'])
                self.assertEqual(len(list(folder.glob('*.txt'))), 16)
                self.assertTrue((folder/'Folder').is_dir())
                with urlopen(workload['url'], timeout=2) as page:
                    body = page.read()
                self.assertEqual(body, guest.WORKLOAD_PAGE.encode())
                self.assertNotIn(b'src=', body)
            self.assertFalse(folder.exists())
        self.assertIsNotNone(processes[0].poll())

    def test_real_worker_nonzero_exit_after_valid_ready_and_cleanup_is_fatal(self):
        username=pwd.getpwuid(os.getuid()).pw_name
        prefix=['runuser','-u',username,'--','env'] if os.getuid()==0 else ['env','ARCTIC_TEST=current',username]
        original=guest.subprocess.Popen;processes=[];folder=None
        def start(argv,**kwargs):
            process=original(argv if os.getuid()==0 else argv[len(prefix):],**kwargs)
            processes.append(process);return process
        with patch.object(guest,'WORKLOAD_WORKER',guest.WORKLOAD_WORKER+'\nraise SystemExit(3)\n'), \
                patch.object(guest.subprocess,'Popen',side_effect=start):
            with self.assertRaisesRegex(RuntimeError,'cleanup failed: exit 3'):
                with guest.role_workload(prefix) as workload:folder=Path(workload['files'])
        self.assertEqual(processes[0].returncode,3)
        self.assertFalse(folder.exists())


if __name__ == '__main__':
    unittest.main()
