"""Host source/IO and explicitly synthetic proof controls; no guest/VM result."""
import ast
import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import shutil
import stat
import signal
import time
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PRIOR=HERE.parent/'precision-feasibility'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


def candidate_source_inputs(runner):
    candidate=Path(os.environ.get('ARCTIC_BROWSER_ROUTE_TEST_SOURCE',str(ROOT.parent/'candidate-source')))
    result={}
    for relative,sha in runner.R.SOURCE_PINS.items():
        runner.R.pinned_file(candidate/relative,sha)
        result[relative]=(candidate/relative).read_bytes()
    return result


check=load('new_native_argv_checker',HERE/'check-browser-route.py')
composer=load('new_native_argv_composer',HERE/'compose-browser-route.py')
old_fixture=load('frozen_native_argv_fixture',PRIOR/'test_feasibility_check.py')


def addon_namespace():
    ns={'__name__':'owned_host_addon_control','__file__':'/run/t/guest-check.py'}
    exec(compile((HERE.parent/'performance/guest.py').read_text(),'<frozen-guest>','exec'),ns)
    exec(compile((PRIOR/'dual-observer.py').read_text(),'<frozen-dual>','exec'),ns)
    exec(compile((HERE/'browser-route-addon.py').read_text(),'<route-addon>','exec'),ns)
    return ns


def compose_identity():
    return composer.components((HERE.parent/'performance/guest.py').read_text(),
        (PRIOR/'dual-observer.py').read_text(),(HERE/'browser-route-addon.py').read_text())


def synthetic_arms(native_latency_ns=None):
    """Invented protocol/session arms: never labelled actual guest evidence."""
    old,_,_,_=old_fixture.synthetic_pair()
    _,identity,parts=compose_identity()
    result={}
    for index,arm in enumerate(check.ARMS):
        run=copy.deepcopy(old['candidate'][0])
        uuid='00000000-0000-0000-0000-00000000000'+str(index+2)
        run['identity']['boot_id']=uuid
        context=run['app_roles']['boot_context']
        context.update(iso_sha256=check.ISO,install_profile_sha256=check.PROFILE,
            browser_route_arm=arm,browser_route_schema=check.SCHEMA)
        run['observer_source_sha256']=identity;run['observer_implementation']=parts
        run['role_measurement_order']=['pristine_idle','cold:browser','precondition:browser','warm:browser']
        run['browser_route_diagnostic']=dict(schema=check.SCHEMA,arm=arm,planned_invocations=5,
            measured_roles=['browser'],declared_core_roles=['terminal','files','browser'],
            direct_native_argv_only=True,detached_arctic_open_timing_included=False,
            session_reads_outside_mapping_interval=True,session_read_cache_overhead_declared=True,
            observer_and_cleanup_unchanged=True,full_six_boot_performance_acceptance=False,release_acceptance=False)
        for key in list(run):
            if any(key.startswith(prefix+role) for role in ('terminal','files')
                   for prefix in ('startup_role_','precondition_role_','dual_invocation_role_')):
                run.pop(key)
        for n in range(1,6):
            bound=run['dual_invocation_role_browser_'+str(n)]
            if index==1 and native_latency_ns is not None:
                bound=old_fixture.synthetic_role_bound(run,'browser',n,bound['launch_started_monotonic_ns'],
                    latency_ns=native_latency_ns)
                run['dual_invocation_role_browser_'+str(n)]=bound
            bound['dual_stream_evidence']['declaration']['boot_id']=uuid
            final=copy.deepcopy(bound['selected_window']);final.update(title='Arctic startup fixture',is_focused=index==1)
            clients=[final]
            if index==0:
                extra=copy.deepcopy(final);extra.update(id=final['id']+1000,is_focused=True);clients.append(extra)
            bound['final_present_window']=final
            bound['final_present_query']['raw']=json.dumps(dict(clients=clients))+'\n'
            e=bound['dual_stream_evidence']
            e['counter']['socket_bytes']=sum(len(q['raw'].encode()) for q in e['query_roundtrips'])+sum(len(v['raw'].encode()) for v in e['watch_events'])
            e['closure']['counter']=e['counter']
            launch=bound['launch_started_monotonic_ns'];returned=e['closure']['parent_received_ns']+1
            absent=lambda a,b:dict(path='/home/synthetic/.local/share/epiphany/session_state.xml',uid=1000,
                exists=False,started_ns=a,finished_ns=b,scope='synthetic source control')
            trace=dict(schema=check.SCHEMA,arm=arm,invocation=n,
                argv=['epiphany',*(['--new-window'] if index==0 else []),run['role_workload']['url']],
                direct_native_argv_only=True,detached_arctic_open_timing_included=False,
                session_before=absent(launch-2,launch-1),session_after=absent(returned+1,returned+2),
                mapped_upper_seconds=bound['upper_seconds'],observer_returned_ns=returned,
                launcher_exit_status_observed=False,launcher_grace_outcome_observed=False,
                supplemental_collection_errors=[],stderr=dict(exists=True,offset=0,bytes=0,total_bytes=0,
                sha256=hashlib.sha256(b'').hexdigest(),text='',raw_base64='',started_ns=returned+3,finished_ns=returned+4,
                file_identity=dict(device=1,inode=5,size=0,mtime_ns=1,ctime_ns=1)))
            run['browser_route_invocation_'+str(n)]=trace
        # Bind summary arrays to the same synthetic raw objects after edits.
        run['startup_role_browser_cold_seconds']['observation_bounds']=[run['dual_invocation_role_browser_1']]
        run['startup_role_browser_warm_seconds']['observation_bounds']=[run['dual_invocation_role_browser_'+str(n)] for n in (3,4,5)]
        run['startup_role_browser_cold_seconds']['first']=run['dual_invocation_role_browser_1']['upper_seconds']
        run['startup_role_browser_warm_seconds']['first']=run['dual_invocation_role_browser_3']['upper_seconds']
        run['startup_role_browser_warm_seconds']['warm']=[run['dual_invocation_role_browser_'+str(n)]['upper_seconds'] for n in (4,5)]
        b=run['dual_invocation_role_browser_1'];end=run['browser_route_invocation_1']['stderr']['finished_ns']+1
        run['role_payload_integrity'].update(boot_id=uuid,first_gui_launch_ns=b['launch_started_monotonic_ns'],
            first_gui_map_upper_ns=b['selected_upper_ns'],measurement_returned_ns=end,hash_started_ns=end+1,hash_finished_ns=end+2)
        result[arm]=run
    return result,identity,parts


class ProofTest(unittest.TestCase):
    def evaluate(self,runs=None):
        if runs is None:runs,identity,parts=synthetic_arms()
        else:_,identity,parts=synthetic_arms()
        prior,backend,namespace=check.dependencies()
        return check.check(runs,prior,backend,namespace,identity,parts)

    def test_complete_synthetic_scope_is_explicit_and_history_not_cleared(self):
        result=self.evaluate()
        self.assertEqual(result['status'],'native-argv-diagnostic-gates-passed')
        self.assertEqual(result['observed_invocations'],10)
        self.assertFalse(result['historical_failures_cleared'])
        self.assertFalse(result['full_six_boot_performance_acceptance'])
        self.assertFalse(result['detached_arctic_open_timing_included'])

    def test_missing_raw_completion_idle_and_payload_reject(self):
        for arm in check.ARMS:
            for key in ('done','measured_payload','installed_bytes','pristine_idle_samples','role_payload_integrity'):
                runs,_,_=synthetic_arms();runs[arm].pop(key)
                with self.subTest(arm=arm,key=key),self.assertRaises((ValueError,KeyError)):self.evaluate(runs)

    def test_pristine_security_context_and_core_preferences_reject(self):
        faults=('same_boot','wrong_arm','wrong_image','wrong_iso','wrong_profile','dirty_profile','wrong_uid',
                'wrong_browser','missing_terminal','changed_files','not_enforcing','helper_scope')
        for fault in faults:
            runs,_,_=synthetic_arms();run=runs[check.ARMS[1]];a=run['app_roles'];c=a['boot_context']
            if fault=='same_boot':run['identity']['boot_id']=runs[check.ARMS[0]]['identity']['boot_id']
            elif fault=='wrong_arm':c['browser_route_arm']=check.ARMS[0]
            elif fault=='wrong_image':c['image']='baseline'
            elif fault=='wrong_iso':c['iso_sha256']='a'*64
            elif fault=='wrong_profile':c['install_profile_sha256']='a'*64
            elif fault=='dirty_profile':a['pristine_state']['prior_role_state_paths']=['profile']
            elif fault=='wrong_uid':a['pristine_state']['uid']=True
            elif fault=='wrong_browser':a['roles']['browser']['configured_command']='gtk-launch org.gnome.Epiphany'
            elif fault=='missing_terminal':a['roles'].pop('terminal')
            elif fault=='changed_files':a['roles']['files']['package']['binary_owner']='foreign-1:1-1.x86_64'
            elif fault=='not_enforcing':run['security']='Permissive'
            else:run['browser_route_diagnostic']['detached_arctic_open_timing_included']=True
            with self.subTest(fault=fault),self.assertRaises((ValueError,KeyError)):self.evaluate(runs)

    def test_foreign_argv_remote_uri_and_unfiltered_count_reject(self):
        for fault in ('flag','remote','app','missing','extra_role','extra_trace'):
            runs,_,_=synthetic_arms();run=runs[check.ARMS[1]];t=run['browser_route_invocation_3']
            if fault=='flag':t['argv'].insert(1,'--new-window')
            elif fault=='remote':t['argv'][-1]='https://example.com/'
            elif fault=='app':t['argv'][0]='firefox'
            elif fault=='missing':run.pop('dual_invocation_role_browser_5')
            elif fault=='extra_role':run['startup_role_terminal_cold_seconds']={}
            else:run['browser_route_invocation_6']={}
            with self.subTest(fault=fault),self.assertRaises((ValueError,KeyError)):self.evaluate(runs)

    def test_raw_peer_eof_hold_and_identity_negative_controls_remain(self):
        for fault in ('peer','partial','exit','hold','early_final','bool_id'):
            runs,_,_=synthetic_arms();b=runs[check.ARMS[1]]['dual_invocation_role_browser_2']
            if fault=='peer':b['dual_stream_evidence']['ready']['peer']['pid']=99
            elif fault=='partial':b['dual_stream_evidence']['closure']['partial_watch_bytes']=1
            elif fault=='exit':b['dual_stream_evidence']['worker_exit']=3
            elif fault=='hold':b['hold_seconds']=5
            elif fault=='early_final':b['final_present_query']=b['dual_stream_evidence']['query_roundtrips'][2]
            else:b['selected_window']['id']=True
            with self.subTest(fault=fault),self.assertRaises((ValueError,KeyError)):self.evaluate(runs)

    def test_session_order_integrity_and_read_bounds_reject(self):
        for fault in ('before_late','after_early','path','uid','bool_clock','read_failure','early_hash','session_caps'):
            runs,_,_=synthetic_arms();run=runs[check.ARMS[1]];t=run['browser_route_invocation_1'];b=run['dual_invocation_role_browser_1']
            if fault=='before_late':t['session_before']['finished_ns']=b['launch_started_monotonic_ns']+1
            elif fault=='after_early':t['session_after']['started_ns']=b['selected_upper_ns']
            elif fault=='path':t['session_after']['path']='/tmp/foreign/session_state.xml'
            elif fault=='uid':t['session_after']['uid']=0
            elif fault=='bool_clock':t['session_before']['started_ns']=True
            elif fault=='read_failure':t['supplemental_collection_errors']=[dict(field='session_after')]
            elif fault=='early_hash':run['role_payload_integrity']['measurement_returned_ns']=t['stderr']['finished_ns']-1
            else:t['session_after'].update(exists=True,bytes=1024*1024+1,sha256='a'*64)
            with self.subTest(fault=fault),self.assertRaises((ValueError,KeyError)):self.evaluate(runs)

    def test_stderr_bytes_identity_scope_and_claims_reject(self):
        for fault in ('sha','offset','size','replacement','encoded','invented_exit','clock'):
            runs,_,_=synthetic_arms();t=runs[check.ARMS[1]]['browser_route_invocation_2'];s=t['stderr']
            if fault=='sha':s['sha256']='a'*64
            elif fault=='offset':s['offset']=1
            elif fault=='size':s['bytes']=True
            elif fault=='replacement':s['file_identity']['inode']=6
            elif fault=='encoded':s['raw_base64']='!'
            elif fault=='invented_exit':t['launcher_exit_status_observed']=True
            else:s['started_ns']=t['observer_returned_ns']-1
            with self.subTest(fault=fault),self.assertRaises((ValueError,KeyError)):self.evaluate(runs)

    def test_one_window_title_focus_semantics_do_not_become_skips(self):
        for fault in ('count','title','focus'):
            runs,_,_=synthetic_arms();b=runs[check.ARMS[1]]['dual_invocation_role_browser_3']
            client=b['final_present_window']
            if fault=='title':client['title']='New Tab'
            elif fault=='focus':client['is_focused']=False
            clients=[client]
            if fault=='count':clients.append(dict(client,id=999))
            b['final_present_query']['raw']=json.dumps(dict(clients=clients))+'\n'
            e=b['dual_stream_evidence'];e['counter']['socket_bytes']=sum(len(q['raw'].encode()) for q in e['query_roundtrips'])+sum(len(v['raw'].encode()) for v in e['watch_events'])
            e['closure']['counter']=e['counter']
            result=self.evaluate(runs)
            with self.subTest(fault=fault):
                self.assertFalse(result['window_semantics_valid']);self.assertEqual(result['status'],'native-argv-diagnostic-gates-failed')

    def test_precision_width_fails_without_relaxing_original_budget(self):
        runs,_,_=synthetic_arms();run=runs[check.ARMS[1]]
        # Rebuild all browser bounds with a conservative6ms interval at200ms.
        for n in range(1,6):
            b=run['dual_invocation_role_browser_'+str(n)];q=b['last_absent_query'];delta=5_000_000
            for key in ('parent_started_ns','worker_started_ns','worker_sent_ns'):q[key]-=delta
            b['lower_seconds']-=.005;b['interval_seconds']+=.005
        result=self.evaluate(runs)
        self.assertFalse(result['precision_valid']);self.assertEqual(result['failed_observations'],5)
        self.assertEqual(result['unfiltered_precision_checks'][check.ARMS[1]][0]['maximum_interval_seconds'],.005)

    def test_memory_boolean_holes_and_five_percent_guard_remain(self):
        for fault in ('boolean','hole','large'):
            runs,_,_=synthetic_arms();samples=runs[check.ARMS[1]]['idle_samples']
            if fault=='boolean':samples[0]['process_pss_bytes']=True
            elif fault=='hole':samples[5].pop('process_private_bytes')
            else:
                for s in samples:
                    if 'process_pss_bytes' in s:s['process_pss_bytes']=int(s['process_pss_bytes']*1.051)
            if fault=='large':self.assertFalse(self.evaluate(runs)['memory_gates_valid'])
            else:
                with self.subTest(fault=fault),self.assertRaises(ValueError):self.evaluate(runs)

    def test_ten_percent_point_and_enclosure_thresholds_are_unchanged(self):
        for value,point_failed,enclosure_failed in ((200_000_000,False,False),(219_000_000,False,True),
                                                    (220_000_000,False,True),(220_010_000,True,True)):
            runs,_,_=synthetic_arms(native_latency_ns=value);result=self.evaluate(runs)
            with self.subTest(value=value):
                self.assertEqual(not result['point_latency_gates_valid'],point_failed)
                self.assertEqual(not result['median_enclosure_valid'],enclosure_failed)
                self.assertTrue(all(v['regression_threshold_percent']==10 for v in result['point_latency_gates'].values()))


class AddonIOTest(unittest.TestCase):
    def setUp(self):self.ns=addon_namespace()

    def reader(self,home,url='http://127.0.0.1:1234/benchmark.html',extra=None):
        env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
        env.update(HOME=str(home),XDG_DATA_HOME=str(home/'.local/share'))
        if extra:env.update(extra)
        return subprocess.run([sys.executable,'-B','-c',self.ns['ROUTE_SESSION_READER'],url],env=env,
            capture_output=True,text=True,timeout=15)

    def test_reader_absent_default_and_normalized_owned_xml(self):
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory)
            p=self.reader(home);self.assertEqual(p.returncode,0,p.stderr);self.assertFalse(json.loads(p.stdout)['exists'])
            folder=home/'.local/share/epiphany';folder.mkdir(parents=True)
            secret='https://user:secret@example.invalid/'
            file=folder/'session_state.xml';file.write_text('<session><window><embed url="'+secret+'"/></window></session>')
            p=self.reader(home);self.assertEqual(p.returncode,0,p.stderr)
            data=json.loads(p.stdout);self.assertEqual(data['window_count'],1)
            self.assertEqual(data['tabs'][0]['uri_kind'],'other-uri');self.assertNotIn(secret,p.stdout)
            self.assertEqual(data['sha256'],hashlib.sha256(file.read_bytes()).hexdigest())

    def test_reader_rejects_path_links_special_oversize_bad_xml(self):
        for fault in ('outside_data','directory_link','file_link','fifo','oversize','xml'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as directory:
                home=Path(directory);folder=home/'.local/share/epiphany';folder.mkdir(parents=True)
                file=folder/'session_state.xml';extra=None
                if fault=='outside_data':extra={'XDG_DATA_HOME':'/tmp/foreign'}
                elif fault=='directory_link':folder.rmdir();folder.symlink_to('/tmp')
                elif fault=='file_link':file.symlink_to('/etc/passwd')
                elif fault=='fifo':os.mkfifo(file)
                elif fault=='oversize':file.write_bytes(b'x'*(1024*1024+1))
                else:file.write_text('<session>')
                p=self.reader(home,extra=extra);self.assertNotEqual(p.returncode,0)

    def test_exact_argv_is_the_only_arm_command_difference(self):
        for arm in check.ARMS:
            ns=addon_namespace();ns['ROUTE_LOG']=Path('/tmp/nonexistent-native-argv-host-control')
            ns['route_context']=lambda:dict(browser_route_arm=arm)
            ns['emit']=lambda *a:None
            ns['install_browser_route']()
            app=dict(id='gnome-web',role='browser',configured_command='epiphany')
            actual=ns['role_command'](app,dict(url='http://127.0.0.1:1234/benchmark.html'))
            self.assertEqual(actual,['epiphany',*(['--new-window'] if arm==check.ARMS[0] else []),'http://127.0.0.1:1234/benchmark.html'])
            for fault in ('id','role','configured_command'):
                broken=dict(app);broken[fault]='foreign'
                with self.subTest(arm=arm,fault=fault),self.assertRaises(RuntimeError):ns['role_command'](broken,dict(url='local'))

    def test_scope_restores_global_order_on_success_and_primary_exception(self):
        for error in (False,True):
            ns=addon_namespace();observed=[]
            def first(*a,**kw):
                observed.append(ns['ROLE_ORDER'])
                if error:raise RuntimeError('primary first-use')
                return 'ok'
            ns.update(first_use_and_precondition=first,route_context=lambda:dict(browser_route_arm=check.ARMS[1]),
                ROUTE_LOG=Path('/tmp/nonexistent-native-argv-host-control'),emit=lambda *a:None)
            ns['install_browser_route']()
            if error:
                with self.assertRaisesRegex(RuntimeError,'primary first-use'):ns['first_use_and_precondition']()
            else:self.assertEqual(ns['first_use_and_precondition'](),'ok')
            self.assertEqual(observed,[('browser',)]);self.assertEqual(ns['ROLE_ORDER'],('terminal','files','browser'))

    def test_supplemental_cleanup_attempts_both_and_preserves_original_failure(self):
        for primary in (False,True):
            ns=addon_namespace();attempts=[];emitted=[]
            def session(*a):
                attempts.append('session')
                if attempts.count('session')>1:raise RuntimeError('session after failed')
                return {}
            def stderr(offset):
                attempts.append('stderr')
                if attempts.count('stderr')>1:raise RuntimeError('stderr after failed')
                return dict(exists=False)
            def startup(*a,**kw):
                if primary:raise RuntimeError('original observer error')
                return .2
            ns.update(startup=startup,route_context=lambda:dict(browser_route_arm=check.ARMS[1]),
                ROUTE_LOG=Path('/tmp/nonexistent-native-argv-host-control'),
                route_session=session,route_stderr=stderr,emit=lambda *a:emitted.append(a))
            ns['install_browser_route']()
            with self.assertRaisesRegex(RuntimeError,'original observer error' if primary else 'Bounded browser evidence'):
                ns['startup']([],['epiphany','url'],('org.gnome.epiphany','epiphany'),label='role_browser')
            self.assertEqual(attempts,['stderr','session','session','stderr'])
            self.assertEqual(len(emitted[-1][1]['supplemental_collection_errors']),2)

    def test_stderr_actual_bytes_transport_with_explicit_synthetic_root_stat(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'apps.log';path.write_bytes(b'owned stderr\xff\n')
            self.ns['ROUTE_LOG']=path
            real=Path.lstat
            def synthetic_root_stat(p):
                s=real(p)
                fields=('st_mode','st_ino','st_dev','st_nlink','st_gid','st_size','st_atime_ns','st_mtime_ns','st_ctime_ns')
                return types.SimpleNamespace(st_uid=0,**{k:getattr(s,k) for k in fields})
            # Only root UID metadata is synthetic; actual bounded IO/hash is exercised.
            with patch.object(Path,'lstat',synthetic_root_stat):
                result=self.ns['route_stderr'](0)
            self.assertEqual(base64.b64decode(result['raw_base64']),path.read_bytes())
            self.assertEqual(result['sha256'],hashlib.sha256(path.read_bytes()).hexdigest())

    def test_stderr_nonroot_symlink_special_and_caps_fail(self):
        for fault in ('uid','link','fifo','oversize','bad_offset'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'apps.log';self.ns['ROUTE_LOG']=path
                if fault=='link':path.symlink_to('/etc/passwd')
                elif fault=='fifo':os.mkfifo(path)
                else:path.write_bytes(b'x'*(512*1024+1 if fault=='oversize' else 1))
                if fault=='uid' and os.getuid()==0:continue
                with self.assertRaises(RuntimeError):self.ns['route_stderr'](2 if fault=='bad_offset' else 0)


class SourceTest(unittest.TestCase):
    def test_compose_retains_exact_guest_dual_and_callback(self):
        guest=(HERE.parent/'performance/guest.py').read_text();dual=(PRIOR/'dual-observer.py').read_text();addon=(HERE/'browser-route-addon.py').read_text()
        source=composer.compose(guest,dual,addon);ast.parse(source)
        self.assertIn(repr(guest),source);self.assertIn(repr(dual),source)
        prior=load('prior_compose_parity',PRIOR/'compose-feasibility.py')
        callback,_,_=prior.components(guest,dual)
        self.assertIn(repr(callback),source)
        self.assertIn('Exact disposable harness stage required',source)
        for g,d in ((guest+'\n',dual),(guest,dual+'\n')):
            with self.assertRaises(ValueError):composer.compose(g,d,addon)

    def test_registered_mode_disables_every_other_job_and_uses_no_build(self):
        import yaml
        workflow=yaml.safe_load((ROOT/'.github/workflows/iso.yml').read_text())
        jobs=workflow['jobs']
        for name in ('iso','same-iso-installs','same-iso-boot-evidence','same-iso-performance','same-iso-precision-feasibility'):
            self.assertIn('!inputs.same_iso_browser_route',jobs[name]['if'])
        job=jobs['same-iso-browser-route'];self.assertEqual(job['permissions'],dict(contents='read',actions='read'))
        self.assertEqual(job['timeout-minutes'],200)
        checkouts=[s for s in job['steps'] if s.get('uses','').startswith('actions/checkout@')]
        self.assertEqual(checkouts[1]['with']['fetch-depth'],0)
        self.assertIn('profiles/ci',checkouts[1]['with']['sparse-checkout'])
        downloads=[s for s in job['steps'] if s.get('uses','').startswith('actions/download-artifact@')]
        self.assertEqual(len(downloads),1);self.assertEqual(downloads[0]['with']['artifact-ids'],11434226349)
        self.assertFalse(any('build-iso' in s.get('run','') or 'gh release' in s.get('run','') for s in job['steps']))

    def test_controller_plan_is_two_candidate_installs_no_baseline_or_updates(self):
        controller=load('new_browser_controller',HERE/'run-browser-route.py')
        self.assertEqual(controller.paired_boot_order(),[(1,arm) for arm in check.ARMS])
        source=(HERE/'run-browser-route.py').read_text()
        self.assertNotIn('--baseline',source);self.assertNotIn('download_baseline',source)
        self.assertIn("context = dict(image='candidate'",source)
        self.assertIn("'--collect-via', 'console'",source)
        self.assertIn("'--stage', 'install'",source)
        self.assertIn('ARCTIC-PRISTINE-INSTALL-POWEROFF=clean',source)
        self.assertIn('Owned Docker cleanup failed',source)
        self.assertNotIn('dnf update',source)

    def test_source_guard_ci_mode_and_prior_metadata_fail_closed(self):
        runner=load('new_browser_runner',HERE/'browser-route-runner.py')
        env=dict(GITHUB_ACTIONS='true',GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REPOSITORY='yuvalkolodkingal/Arctic-Linux',
            GITHUB_API_URL='https://api.github.com',GITHUB_SHA='e'*40,GITHUB_RUN_ID='99999999',GITHUB_RUN_ATTEMPT='1',
            CONTAINER_ENGINE='docker',BROWSER_ROUTE_MODE='true',RECOVERY_MODE='false',PERFORMANCE_MODE='false',
            PRECISION_FEASIBILITY_MODE='false',NIX_ACCEPTANCE='false',PERFORMANCE_ACCEPTANCE='false',RELEASE_REQUESTED='false')
        runner.validate_ci(env)
        for key,value in (('CONTAINER_ENGINE','podman'),('PRECISION_FEASIBILITY_MODE','true'),('RELEASE_REQUESTED','true'),
                          ('GITHUB_SHA',runner.BASE),('BROWSER_ROUTE_MODE','false')):
            with self.subTest(key=key),self.assertRaises(RuntimeError):runner.validate_ci(dict(env,**{key:value}))
        run=dict(id=runner.RUN,head_sha=runner.BASE,status='completed',conclusion='failure',run_attempt=1)
        jobs=[dict(id=runner.JOB,run_id=runner.RUN,head_sha=runner.BASE,status='completed',conclusion='failure',
            steps=[dict(name='One fresh boot per fixed image with24 unfiltered startup observations',status='completed',conclusion='failure')])]
        artifact=dict(id=runner.ARTIFACT,size_in_bytes=runner.ZIP_BYTES,digest='sha256:'+runner.ZIP_SHA,expired=False,
            workflow_run=dict(id=runner.RUN,head_sha=runner.BASE))
        runner.validate_prior(run,jobs,artifact)
        for key,value in (('id',1),('size_in_bytes',1),('expired',True),('digest','sha256:'+'a'*64)):
            with self.subTest(key=key),self.assertRaises(RuntimeError):runner.validate_prior(run,jobs,dict(artifact,**{key:value}))

    def test_exact_execution_file_set_and_all_frozen_runtime_pins(self):
        runner=load('native_route_source_controls',HERE/'browser-route-runner.py')
        # No Git command is executed: readonly Git responses are explicitly simulated.
        # Files are copied to a private temporary fixture before any mutation.
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);execution=base/'execution';source=base/'source'
            shutil.copytree(ROOT,execution,ignore=shutil.ignore_patterns('__pycache__','.git'))
            for relative,raw in candidate_source_inputs(runner).items():
                p=source/relative;p.parent.mkdir(parents=True,exist_ok=True)
                p.write_bytes(raw)
            args=types.SimpleNamespace(source=source,bundle=execution/'tools/browser-route')
            git_blobs={relative:(ROOT/relative).read_bytes() for relative in runner.RUNTIME_FILES}
            changed=['tools/browser-route/browser-route-addon.py']
            def git(argv,**kwargs):
                if argv[-2:]==['rev-parse','HEAD']:
                    return runner.R.SOURCE+'\n' if argv[2]==str(source) else 'e'*40+'\n'
                if argv[-2:]==['status','--porcelain']:return ''
                if 'diff' in argv:return '\n'.join(changed)+'\n'
                if 'show' in argv:return git_blobs[argv[-1].split(':',1)[1]]
                raise AssertionError('Unexpected readonly Git argv: '+repr(argv))
            env=dict(GITHUB_SHA='e'*40)
            with patch.dict(os.environ,env),patch.object(runner.subprocess,'check_output',git),patch.object(runner.subprocess,'run'):
                runner.verify_sources(args)
                for relative in sorted(runner.RUNTIME_FILES):
                    path=execution/relative;raw=path.read_bytes()
                    try:
                        path.write_bytes(raw+b'\n')
                        with self.subTest(relative=relative),self.assertRaises(RuntimeError):runner.verify_sources(args)
                    finally:path.write_bytes(raw)
                for relative in sorted(runner.FILES):
                    path=execution/relative;raw=path.read_bytes()
                    try:
                        path.write_bytes(raw+b'\n')
                        with self.subTest(new=relative),self.assertRaises(RuntimeError):runner.verify_sources(args)
                    finally:path.write_bytes(raw)
                changed.append('packaging/desktop/live-default-apps')
                with self.assertRaises(RuntimeError):runner.verify_sources(args)

    def test_stage_marker_and_boolean_exit_cannot_hide_failure(self):
        runs,_,_=synthetic_arms();run=runs[check.ARMS[1]]
        prior,backend,_=check.dependencies()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'serial.log'
            records='\n'.join('ARCTIC-PERFORMANCE '+json.dumps(dict(stage='installed',check=k,value=v)) for k,v in run.items())
            for status in ('3','True','-15',''):
                path.write_text(records+'\nARCTIC-INSTALLED-SMOKE-EXIT='+status+'\n')
                with self.subTest(status=status),self.assertRaises(ValueError):prior.read_run(path,backend)
            path.write_text(records+'\nARCTIC-INSTALLED-SMOKE-EXIT=0\n')
            self.assertTrue(prior.read_run(path,backend)['done'])

    def test_controller_deadlines_and_provenance_are_real_and_finite(self):
        runner=(HERE/'browser-route-runner.py').read_text()
        controller=(HERE/'run-browser-route.py').read_text()
        self.assertIn('seconds=150*60',runner)
        self.assertIn("'--install-timeout', '2400'",controller)
        self.assertIn("'-install-harness.log'), 3600, vm=True",controller)
        self.assertIn("archive / 'harness.log', 2400, vm=True",controller)
        self.assertIn('Actual copied guest probe differs',controller)
        self.assertIn('Actual copied fresh-arm context differs',controller)

    def test_candidate_source_lookup_is_portable_and_rejects_every_wrong_input_hash(self):
        runner=load('portable_browser_route_fixture',HERE/'browser-route-runner.py')
        real=candidate_source_inputs(runner)
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);candidate=base/'candidate-source'
            for relative,raw in real.items():
                p=candidate/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
            with patch.dict(globals(),ROOT=base/'qualification-source'),\
                    patch.dict(os.environ,{},clear=False):
                old=os.environ.pop('ARCTIC_BROWSER_ROUTE_TEST_SOURCE',None)
                try:
                    self.assertEqual(candidate_source_inputs(runner),real)
                    for relative,raw in real.items():
                        path=candidate/relative;path.write_bytes(raw+b'\n')
                        try:
                            with self.subTest(relative=relative),self.assertRaises(RuntimeError):candidate_source_inputs(runner)
                        finally:path.write_bytes(raw)
                finally:
                    if old is not None:os.environ['ARCTIC_BROWSER_ROUTE_TEST_SOURCE']=old
        self.assertNotIn('/workspace/Arctic-Linux',(HERE/'test_browser_route.py').read_text().split('def test_candidate_source_lookup')[0])


class EmergencyCleanupControls(unittest.TestCase):
    """Synthetic Docker responses; actual timeout actors are solely owned children."""
    def setUp(self):
        self.runner=load('native_argv_emergency_'+str(id(self)),HERE/'browser-route-runner.py')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)
        self.measurement=self.folder/'measurement';self.measurement.mkdir()
        self.probe=self.measurement/'frozen-observer.py';self.probe.write_text('synthetic-owned-probe\n')
        self.env=dict(GITHUB_SHA='e'*40,GITHUB_RUN_ID='99999999',GITHUB_RUN_ATTEMPT='1')
        self.ownership=dict(schema='arctic-browser-route-task-v2',mode='browser-native-argv-diagnostic',
            task_id='a'*32,candidate_source=self.runner.R.SOURCE,execution_checker_head='e'*40,
            github_run_id='99999999',github_run_attempt='1',observer_sha256=self.runner.R.digest(self.probe),
            candidate_iso_path='/synthetic-fixed-candidate.iso',candidate_iso_bytes=self.runner.R.ISO_BYTES,
            candidate_iso_sha256=self.runner.R.ISO_SHA256,arms=list(self.runner.ARMS))
        self.prefix='arctic-paired-'+'a'*32+'-';self.names=[self.prefix+'b'*8,self.prefix+'c'*8]
        self.state=dict(mode='browser-native-argv-diagnostic',ownership=copy.deepcopy(self.ownership),
            task_id=self.ownership['task_id'],candidate_image_source=dict(commit=self.runner.R.SOURCE),
            execution_checker_commit='e'*40,observer_sha256=self.ownership['observer_sha256'],
            owned_container_names=self.names,images={arm:dict(path=self.ownership['candidate_iso_path'],
                bytes=self.runner.R.ISO_BYTES,sha256=self.runner.R.ISO_SHA256) for arm in self.runner.ARMS})
        self.save()
        self.ids={self.names[0]:'d'*64,self.names[1]:'f'*64}

    def save(self):
        (self.measurement/'status.json').write_text(json.dumps(self.state))

    def docker(self,argv,**kwargs):
        self.assertEqual(argv[0],'docker')
        if argv[1]=='ps':
            self.assertEqual(argv[-1],'name=^/'+self.prefix)
            return '\n'.join(self.names)+'\n'
        self.assertEqual(argv[1:4],['inspect','--type','container'])
        name=argv[-1];return self.ids[name]+' /'+name+'\n'

    def invoke(self,query=None):
        with patch.dict(os.environ,self.env),patch.object(self.runner.subprocess,'check_output',side_effect=query or self.docker) as read,\
                patch.object(self.runner.subprocess,'run') as remove, (self.folder/'cleanup.log').open('w') as output:
            self.runner.cleanup_task_containers(self.measurement,output,self.ownership)
            return read.call_args_list,remove.call_args_list

    def test_actual_two_candidate_arm_state_removes_only_registered_immutable_ids(self):
        reads,removes=self.invoke()
        self.assertEqual(len(reads),3);self.assertEqual(len(removes),2)
        self.assertEqual([v.args[0] for v in removes],[['docker','rm','--force',self.ids[name]] for name in self.names])
        self.assertTrue(all(v.kwargs['check'] is True and v.kwargs['timeout']==30 for v in removes))
        self.assertNotIn('baseline',self.state['images'])

    def test_task_source_head_run_attempt_and_actual_arm_guards_fail_before_docker(self):
        original=copy.deepcopy(self.state)
        mutations=[lambda s:s.update(task_id='b'*32),lambda s:s.update(mode='other'),
            lambda s:s['ownership'].update(github_run_id='1'),lambda s:s['ownership'].update(github_run_attempt='2'),
            lambda s:s['ownership'].update(execution_checker_head='b'*40),
            lambda s:s['candidate_image_source'].update(commit='b'*40),
            lambda s:s.update(execution_checker_commit='b'*40),lambda s:s.update(observer_sha256='b'*64),
            lambda s:s['images'].update(baseline=s['images'].pop(self.runner.ARMS[0])),
            lambda s:s['images'][self.runner.ARMS[0]].update(bytes=True),
            lambda s:s['images'][self.runner.ARMS[0]].update(bytes=1),
            lambda s:s['images'][self.runner.ARMS[1]].update(sha256='054db5c43cae47fb60f8f43efc8e052b569aa1b14e8f15adcb15cdc48265182f'),
            lambda s:s['images'][self.runner.ARMS[0]].update(path='/foreign.iso'),
            lambda s:s.pop('ownership')]
        for index,mutate in enumerate(mutations):
            self.state=copy.deepcopy(original);mutate(self.state);self.save()
            with self.subTest(index=index),patch.dict(os.environ,self.env),patch.object(self.runner.subprocess,'check_output') as read,\
                    patch.object(self.runner.subprocess,'run') as remove,(self.folder/'cleanup.log').open('w') as output:
                with self.assertRaises((RuntimeError,ValueError)):
                    self.runner.cleanup_task_containers(self.measurement,output,self.ownership)
                read.assert_not_called();remove.assert_not_called()

    def test_missing_linked_changed_or_unbounded_state_and_probe_are_refused(self):
        for target in (self.measurement/'status.json',self.probe):
            original=target.read_bytes()
            for kind in ('missing','symlink','changed','oversize'):
                target.unlink(missing_ok=True)
                if kind=='symlink':target.symlink_to(self.folder/'missing')
                elif kind=='changed':target.write_bytes(b'bad')
                elif kind=='oversize':target.write_bytes(b'x'*(2*1024*1024+1))
                with self.subTest(path=target.name,kind=kind),patch.dict(os.environ,self.env),\
                        patch.object(self.runner.subprocess,'check_output') as read,(self.folder/'cleanup.log').open('w') as output:
                    with self.assertRaises((RuntimeError,ValueError)):
                        self.runner.cleanup_task_containers(self.measurement,output,self.ownership)
                    read.assert_not_called()
                target.unlink(missing_ok=True);target.write_bytes(original)

    def test_foreign_duplicate_missing_or_oversize_registry_is_refused(self):
        for names in (None,[],[self.prefix+'z'*8],[self.names[0]]*2,[self.prefix+f'{n:08x}' for n in range(6)]):
            self.state['owned_container_names']=names;self.save()
            with self.subTest(names=names),patch.dict(os.environ,self.env),patch.object(self.runner.subprocess,'check_output') as read,\
                    (self.folder/'cleanup.log').open('w') as output:
                with self.assertRaises(RuntimeError):self.runner.cleanup_task_containers(self.measurement,output,self.ownership)
                read.assert_not_called()

    def test_docker_foreign_namespace_unregistered_or_duplicate_names_are_refused(self):
        for names in ([self.prefix+'0'*8],['foreign'],[self.names[0]]*2,self.names*3):
            with self.subTest(names=names),patch.dict(os.environ,self.env),\
                    patch.object(self.runner.subprocess,'check_output',return_value='\n'.join(names)+'\n') as read,\
                    patch.object(self.runner.subprocess,'run') as remove,(self.folder/'cleanup.log').open('w') as output:
                with self.assertRaises(RuntimeError):self.runner.cleanup_task_containers(self.measurement,output,self.ownership)
                self.assertEqual(read.call_count,1);remove.assert_not_called()

    def test_container_inspect_wrong_name_id_and_duplicate_ids_precede_any_removal(self):
        for kind in ('name','id','duplicate'):
            def query(argv,**kwargs):
                if argv[1]=='ps':return '\n'.join(self.names)+'\n'
                if kind=='name':return 'd'*64+' /foreign\n'
                if kind=='id':return 'bad /'+argv[-1]+'\n'
                return 'd'*64+' /'+argv[-1]+'\n'
            with self.subTest(kind=kind),patch.dict(os.environ,self.env),patch.object(self.runner.subprocess,'check_output',side_effect=query),\
                    patch.object(self.runner.subprocess,'run') as remove,(self.folder/'cleanup.log').open('w') as output:
                with self.assertRaises(RuntimeError):self.runner.cleanup_task_containers(self.measurement,output,self.ownership)
                remove.assert_not_called()

    def test_docker_inspect_or_owned_remove_error_is_fatal(self):
        for phase in ('inspect','remove'):
            def query(argv,**kwargs):
                if phase=='inspect' and argv[1]=='inspect':raise subprocess.CalledProcessError(3,argv)
                return self.docker(argv,**kwargs)
            with self.subTest(phase=phase),patch.dict(os.environ,self.env),\
                    patch.object(self.runner.subprocess,'check_output',side_effect=query),\
                    patch.object(self.runner.subprocess,'run',side_effect=subprocess.CalledProcessError(3,['docker','rm'])) as remove,\
                    (self.folder/'cleanup.log').open('w') as output:
                with self.assertRaises(subprocess.CalledProcessError):self.runner.cleanup_task_containers(self.measurement,output,self.ownership)
                if phase=='inspect':remove.assert_not_called()

    def actor(self,ignore_term):
        ready=self.folder/('ready-ignore' if ignore_term else 'ready-normal')
        script='import signal,time;from pathlib import Path;'+('signal.signal(signal.SIGTERM,signal.SIG_IGN);' if ignore_term else '')+\
            'Path('+repr(str(ready))+').write_text("ready");time.sleep(30)'
        process=subprocess.Popen([sys.executable,'-c',script],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        self.addCleanup(lambda:process.poll() is None and (process.kill(),process.wait(timeout=5)))
        deadline=time.monotonic()+5
        while not ready.exists() and time.monotonic()<deadline:time.sleep(.001)
        self.assertTrue(ready.exists(),'Owned actor readiness missing')
        return process

    def test_actual_owned_child_natural_term_reaps_without_emergency_docker(self):
        actor=self.actor(False)
        with patch.object(self.runner.subprocess,'Popen',return_value=actor),\
                patch.object(self.runner,'cleanup_task_containers') as cleanup:
            with self.assertRaises(subprocess.TimeoutExpired):
                self.runner.execute_controller(['synthetic-owned-controller'],self.folder/'controller.log',self.folder,
                    {},self.ownership,seconds=.025,measurement=self.measurement)
            cleanup.assert_not_called()
        self.assertEqual(actor.returncode,-signal.SIGTERM)

    def test_actual_retained_owned_child_killed_reaped_before_bound_emergency_cleanup(self):
        actor=self.actor(True);observed=[]
        real_cleanup=self.runner.cleanup_task_containers
        class ShortenedGrace:
            def wait(_,timeout):observed.append(timeout);return actor.wait(timeout=.025 if timeout==100 else timeout)
            def send_signal(_,value):actor.send_signal(value)
            def kill(_):actor.kill()
        with patch.object(self.runner.subprocess,'Popen',return_value=ShortenedGrace()),\
                patch.object(self.runner,'cleanup_task_containers') as emergency:
            def use_real(measurement,output,ownership):
                self.assertEqual(actor.returncode,-signal.SIGKILL)
                self.assertEqual(measurement,self.measurement);self.assertEqual(ownership,self.ownership)
                with patch.dict(os.environ,self.env),patch.object(self.runner.subprocess,'check_output',side_effect=self.docker),\
                        patch.object(self.runner.subprocess,'run') as remove:
                    real_cleanup(measurement,output,ownership);self.assertEqual(remove.call_count,2)
            emergency.side_effect=use_real
            with self.assertRaises(subprocess.TimeoutExpired):
                self.runner.execute_controller(['synthetic-owned-controller'],self.folder/'controller.log',self.folder,
                    {},self.ownership,seconds=.025,measurement=self.measurement)
            self.assertEqual(emergency.call_count,1)
        self.assertEqual(observed,[.025,100,15]);self.assertEqual(actor.returncode,-signal.SIGKILL)

    def test_emergency_refusal_preserves_primary_timeout_with_cleanup_note(self):
        actor=self.actor(True)
        class ShortenedGrace:
            def wait(_,timeout):return actor.wait(timeout=.025 if timeout==100 else timeout)
            def send_signal(_,value):actor.send_signal(value)
            def kill(_):actor.kill()
        with patch.object(self.runner.subprocess,'Popen',return_value=ShortenedGrace()),\
                patch.object(self.runner,'cleanup_task_containers',side_effect=RuntimeError('foreign scope refused')):
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                self.runner.execute_controller(['synthetic-owned-controller'],self.folder/'controller.log',self.folder,
                    {},self.ownership,seconds=.025,measurement=self.measurement)
            self.assertTrue(any('foreign scope refused' in note for note in caught.exception.__notes__))
        self.assertEqual(actor.returncode,-signal.SIGKILL)

    def test_controller_registers_before_creation_and_atomic_state_keeps_exact_scope(self):
        source=(HERE/'run-browser-route.py').read_text();tree=ast.parse(source)
        main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        execute=next(n for n in main.body if isinstance(n,ast.FunctionDef) and n.name=='execute')
        code=ast.get_source_segment(source,execute)
        self.assertLess(code.index("state['owned_container_names'].append(name)"),code.index('subprocess.Popen('))
        self.assertLess(code.index("save(state.get('phase'"),code.index('subprocess.Popen('))
        self.assertIn("state['task_id'] = ownership['task_id']",source)
        self.assertIn("temporary.replace(args.out/'status.json')",source)
        self.assertIn("ownership.get('observer_sha256')!=sha256(probe)",source)
        self.assertIn("ownership.get('github_run_attempt')!=os.environ.get('GITHUB_RUN_ATTEMPT')",source)
        self.assertNotIn('V3.execute_controller(', (HERE/'browser-route-runner.py').read_text())

    def test_normal_controller_absent_present_foreign_and_error_cleanup_states(self):
        controller=load('native_route_normal_cleanup',HERE/'run-browser-route.py')
        name=self.names[0];task=self.ownership['task_id']
        with (self.folder/'normal-cleanup.log').open('w') as output:
            with patch.object(controller.subprocess,'check_output',return_value='') as query,\
                    patch.object(controller.subprocess,'run') as remove:
                result=controller.cleanup_owned_container('docker',name,task,output)
                self.assertEqual(result['status'],'owned-name-confirmed-absent')
                self.assertEqual(query.call_args.args[0][-1],'name=^/'+name+'$');remove.assert_not_called()
            with patch.object(controller.subprocess,'check_output',side_effect=[name+'\n','d'*64+' /'+name+'\n']),\
                    patch.object(controller.subprocess,'run') as remove:
                result=controller.cleanup_owned_container('docker',name,task,output)
                self.assertEqual(result['status'],'owned-immutable-id-removed')
                self.assertEqual(remove.call_args.args[0],['docker','rm','--force','d'*64])
                self.assertTrue(remove.call_args.kwargs['check'])
            for replies in ([name+'extra\n'],[name+'\n','d'*64+' /foreign\n'],[name+'\n','bad /'+name+'\n']):
                with self.subTest(replies=replies),patch.object(controller.subprocess,'check_output',side_effect=replies),\
                        patch.object(controller.subprocess,'run') as remove:
                    with self.assertRaises(RuntimeError):controller.cleanup_owned_container('docker',name,task,output)
                    remove.assert_not_called()
            for operation in ('query','inspect','remove'):
                replies=[name+'\n','d'*64+' /'+name+'\n']
                if operation=='query':replies=[subprocess.CalledProcessError(3,['docker','ps'])]
                elif operation=='inspect':replies[1]=subprocess.CalledProcessError(3,['docker','inspect'])
                with self.subTest(operation=operation),patch.object(controller.subprocess,'check_output',side_effect=replies),\
                        patch.object(controller.subprocess,'run',side_effect=subprocess.CalledProcessError(3,['docker','rm'])):
                    with self.assertRaises(subprocess.CalledProcessError):controller.cleanup_owned_container('docker',name,task,output)
            with patch.object(controller.subprocess,'check_output') as query:
                with self.assertRaises(RuntimeError):controller.cleanup_owned_container('docker',name+'a',task,output)
                query.assert_not_called()
        # The real inherited commands have two normal already-absent lifecycles.
        self.assertIn('run --rm',(ROOT/'tools/test-install.sh').read_text())
        self.assertIn('trap cleanup EXIT',(ROOT/'tools/performance/prepare-vm-tools.sh').read_text())


if __name__=='__main__':unittest.main()
