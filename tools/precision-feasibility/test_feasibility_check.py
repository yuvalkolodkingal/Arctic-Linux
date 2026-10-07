"""Synthetic proof negatives, explicitly separate from actual VM evidence."""
import copy
import importlib.util
import json
import hashlib
import tempfile
import subprocess
import sys
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
BASE=HERE/'unchanged-base' if (HERE/'unchanged-base').exists() else HERE.parents[1]
spec=importlib.util.spec_from_file_location('strict_feasibility_check',HERE/'feasibility-check.py')
check=importlib.util.module_from_spec(spec);spec.loader.exec_module(check)


def synthetic_bound(latency_ns=200_000_000,width_ns=1_000_000):
    """Invented protocol metadata exercises gates; this is no actual guest proof."""
    launch=1_000_000_000;upper=launch+latency_ns;uid=1000
    window=dict(id=1,pid=31,appid='kitty',title='Synthetic proof control')
    process=dict(pid=10,uid=uid,start_ticks=5,exe='/usr/bin/mango')
    peer=dict(process,gid=1000)
    declaration=dict(uid=uid,pid=10,process=process,socket_path='/run/user/1000/mango-fixture.sock',
        socket_identity=[1,2,uid],executable_identity=dict(device=1,inode=2,size=100,mtime_ns=1,ctime_ns=1),
        rpm_owner='mangowm-0:0.17.3-1.fixture.gitd13da6c.fc44.x86_64',
        boot_id='00000000-0000-0000-0000-000000000001',image='baseline',boot=1,
        session_id='synthetic',wayland_display='wayland-0')
    def raw(clients):return json.dumps(dict(clients=clients))+'\n'
    def query(sent,frame,clients):
        return dict(parent_started_ns=sent-20,worker_started_ns=sent-10,worker_sent_ns=sent,
            worker_frame_received_ns=frame,worker_received_ns=frame+10,parent_received_ns=frame+20,
            uid=uid,peer=peer,raw=raw(clients))
    queries=[query(950_000_000,950_000_010,[]),query(upper-width_ns,upper+300_000,[]),
             query(upper+600_000,upper+650_000,[window]),
             query(upper+5_000_200_000,upper+5_000_210_000,[window])]
    events=[dict(sequence=1,received_ns=900_000_050,raw=raw([]),payload=dict(clients=[]),peer=peer),
            dict(sequence=2,received_ns=upper,raw=raw([window]),payload=dict(clients=[window]),peer=peer),
            dict(sequence=3,received_ns=upper+5_000_310_000,raw=raw([]),payload=dict(clients=[]),peer=peer)]
    worker=dict(pid=20,uid=uid,start_ticks=6,exe='/usr/bin/python3')
    counter=dict(socket_bytes=sum(len(q['raw'].encode()) for q in queries)+sum(len(e['raw'].encode()) for e in events),
                 watch_frames=3,get_frames=4,get_queries=4)
    ready=dict(kind='ready',uid=uid,worker_pid=20,worker_process=worker,peer=peer,
        parent_started_ns=900_000_000,parent_received_ns=900_000_100,
        worker_usage=dict(user_seconds=.0008,system_seconds=.0002,maximum_rss_kib=1024),cpu_seconds=.001,
        watch_events=events[:1],counter=dict(socket_bytes=len(events[0]['raw'].encode()),watch_frames=1,get_frames=0,get_queries=0))
    closure=dict(kind='closed',uid=uid,worker_pid=20,worker_process=worker,
        parent_started_ns=upper+5_000_300_000,parent_received_ns=upper+5_000_410_000,
        watch_eof_ns=upper+5_000_400_000,partial_watch_bytes=0,
        worker_usage=dict(user_seconds=.004,system_seconds=.001,maximum_rss_kib=1024),cpu_seconds=.005,
        watch_events=events[-1:],counter=counter)
    e=dict(declaration=declaration,worker=worker,ready=ready,watch_events=events,query_roundtrips=queries,
        counter=counter,closure=closure,worker_exit=0,failed_worker_evidence=None,
        worker_memory_before_close=dict(pss_bytes=4096,private_bytes=2048,phase='post-hold-before-worker-close',process=worker),cleanup_errors=[])
    wrapper=dict(pid=30,uid=0,start_ticks=10,exe='/usr/sbin/runuser')
    leaf=dict(pid=31,uid=uid,start_ticks=11,exe='/usr/bin/kitty')
    chain=[dict(leaf,parent_pid=30),dict(wrapper,parent_pid=500)]
    origin=dict(invocation=1,process=leaf,ancestry=chain,launch_wrapper_pid=30)
    owner=dict(window_id=1,window_pid=31,uid=uid,process=leaf,launch_wrapper_pid=30,
        ancestry=chain,retained_identity=None,model='same-invocation-ancestry',invocation=1,origin=origin)
    bound=dict(observer=check.OBSERVER,bound_basis='dual-stream-send-to-complete-frame-v1',
        launch_started_monotonic_ns=launch,selected_upper_ns=upper,
        selected_stream='watch',selected_positive=events[1],selected_window=window,
        window_ownership=owner,launch_process=wrapper,invocation=1,before_client_ids=[],
        last_absent_query=queries[1],first_present_query=None,hold_seconds=5,
        hold_verified_ns=upper+5_000_240_000,final_present_query=queries[-1],final_present_window=window,
        lower_seconds=(latency_ns-width_ns)/1e9,upper_seconds=latency_ns/1e9,interval_seconds=width_ns/1e9,
        dual_stream_evidence=e)
    run=dict(identity=dict(boot_id=declaration['boot_id']),
        app_roles=dict(image='baseline',pristine_state=dict(uid=uid),boot_context=dict(boot=1)),
        rpm_inventory=dict(nevra=[declaration['rpm_owner']]))
    return bound,run,dict(appids=['kitty'])


CLOCK_KEYS={'launch_started_monotonic_ns','selected_upper_ns','parent_started_ns','parent_received_ns',
            'worker_started_ns','worker_sent_ns','worker_frame_received_ns','worker_received_ns',
            'received_ns','watch_eof_ns','hold_verified_ns'}


def synthetic_role_bound(run,role,invocation,launch_ns,latency_ns=200_000_000,width_ns=1_000_000):
    bound,_,_=synthetic_bound(latency_ns,width_ns)
    shift=launch_ns-bound['launch_started_monotonic_ns']
    visited=set()
    def shift_clocks(value):
        if isinstance(value,(dict,list)):
            if id(value) in visited:return
            visited.add(id(value))
        if isinstance(value,dict):
            for key,item in value.items():
                if key in CLOCK_KEYS:value[key]=item+shift
                else:shift_clocks(item)
        elif isinstance(value,list):
            for item in value:shift_clocks(item)
    shift_clocks(bound)
    e=bound['dual_stream_evidence'];d=e['declaration'];image=run['app_roles']['image']
    d.update(image=image,boot_id=run['identity']['boot_id'],
        rpm_owner='mangowm-0:0.17.3-1.fixture.git'+('d13da6c' if image=='baseline' else 'fe4742c')+'.fc44.x86_64')
    appid=run['app_roles']['roles'][role]['appids'][0]
    # These client/proc identities are synthetic controls, never reported as guests.
    pid=100+10*check_namespace_role_index(role)+invocation
    wrapper=500+pid
    def rewrite_snapshot(raw):
        value=json.loads(raw)
        for client in value['clients']:client.update(pid=pid,appid=appid)
        return json.dumps(value)+'\n'
    for query in e['query_roundtrips']:query['raw']=rewrite_snapshot(query['raw'])
    for event in e['watch_events']:
        event['raw']=rewrite_snapshot(event['raw']);event['payload']=json.loads(event['raw'])
    for key in ('selected_window','final_present_window'):bound[key].update(pid=pid,appid=appid)
    owner=bound['window_ownership'];owner.update(window_pid=pid,launch_wrapper_pid=wrapper,invocation=invocation)
    owner['process'].update(pid=pid,exe='/usr/bin/'+run['app_roles']['roles'][role]['id'])
    owner['ancestry'][0].update(pid=pid,exe=owner['process']['exe'],parent_pid=wrapper)
    owner['ancestry'][1]['pid']=wrapper
    owner['origin'].update(invocation=invocation,launch_wrapper_pid=wrapper)
    bound['launch_process']['pid']=wrapper;bound['invocation']=invocation
    if invocation==2:
        delta=40_000_000_000
        bound['hold_seconds']=45
        for key in ('hold_verified_ns',):bound[key]+=delta
        for q in e['query_roundtrips'][-1:]:
            for key in CLOCK_KEYS & set(q):q[key]+=delta
        for event in e['watch_events'][-1:]:event['received_ns']+=delta
        for key in ('parent_started_ns','parent_received_ns','watch_eof_ns'):e['closure'][key]+=delta
    total=sum(len(q['raw'].encode()) for q in e['query_roundtrips'])+sum(len(v['raw'].encode()) for v in e['watch_events'])
    e['counter']['socket_bytes']=total;e['closure']['counter']['socket_bytes']=total
    e['ready']['counter']['socket_bytes']=len(e['watch_events'][0]['raw'].encode())
    return bound


def check_namespace_role_index(role):return ('terminal','files','browser').index(role)


def synthetic_pair():
    """Exact old host-fixture baseline plus invented dual transport; not VM evidence."""
    spec=importlib.util.spec_from_file_location('unchanged_role_fixture',BASE/'tools/tests/test_performance_roles.py')
    legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
    backend,namespace=check.load_backend(BASE/'tools/performance/compare.py')
    spec=importlib.util.spec_from_file_location('diagnostic_fixture_composer',HERE/'compose-feasibility.py')
    composer=importlib.util.module_from_spec(spec);spec.loader.exec_module(composer)
    _,identity,parts=composer.components((BASE/'tools/performance/guest.py').read_text(),(HERE/'dual-observer.py').read_text())
    runs={image:[legacy.role_run(image,1)] for image in ('baseline','candidate')}
    for image,group in runs.items():
        run=group[0];run['identity']['boot_id']='00000000-0000-0000-0000-00000000000'+('1' if image=='baseline' else '2')
        run['app_roles']['boot_context']['iso_sha256']=check.ISO[image]
        run['observer_source_sha256']=identity;run['observer_implementation']=parts
        owner='mangowm-0:0.17.3-1.fixture.git'+('d13da6c' if image=='baseline' else 'fe4742c')+'.fc44.x86_64'
        records=sorted(run['rpm_inventory']['nevra']+[owner]);run['rpm_inventory']=dict(nevra=records,
            sha256=hashlib.sha256(('\n'.join(records)+'\n').encode()).hexdigest())
        for name in ('fish','bash','shell_ipc'):run[name+'_seconds']['samples']=[run[name+'_seconds']['median']]*10
        for index,role in enumerate(backend.ROLE_ORDER):
            bounds=[]
            for n in range(1,6):
                launch=(2+8*index if n==1 else 30+50*index if n==2 else 190+8*(index*3+n-3))*1_000_000_000
                bound=synthetic_role_bound(run,role,n,launch);bounds.append(bound)
                run['dual_invocation_role_'+role+'_'+str(n)]=bound
            for phase,selected in [('cold',bounds[:1]),('warm',bounds[2:])]:
                timing=run['startup_role_'+role+'_'+phase+'_seconds']
                timing.update(first=selected[0]['upper_seconds'],observation_bounds=selected,
                    observer=check.OBSERVER,poll_sleep_seconds=.00025)
                if phase=='warm':timing['warm']=[b['upper_seconds'] for b in selected[1:]]
            run['precondition_role_'+role]['launch_started_monotonic_ns']=bounds[1]['launch_started_monotonic_ns']
        if image=='candidate':
            run['measured_payload'].update(arctic_shell='arctic-shell-0.2.0-1.fixture.gitfe4742c.x86_64',
                catalog_sha256='3d5c34c6a79fd5c24c1f733792ef56816089f38678a187337a13f2964c92116e  /usr/share/arctic/shell/AppsService.qml',
                battery_sha256='e33a7dd29ef10cf5671b6984aaa1a690a994baa460ffdcacf0f49adfabffea35  /usr/share/arctic/shell/BatteryService.qml')
            b=run['dual_invocation_role_browser_1'];returned=b['dual_stream_evidence']['closure']['parent_received_ns']+1
            run['role_payload_integrity'].update(boot_id=run['identity']['boot_id'],
                first_gui_launch_ns=b['launch_started_monotonic_ns'],first_gui_map_upper_ns=b['selected_upper_ns'],
                measurement_returned_ns=returned,hash_started_ns=returned+1,hash_finished_ns=returned+2)
    return runs,backend,namespace,identity


class CompletePairTest(unittest.TestCase):
    def test_exact_two_boots_and_all_twenty_four_unfiltered_observations(self):
        runs,backend,namespace,identity=synthetic_pair()
        result=check.check_pair(runs,backend,namespace,identity)
        self.assertEqual(result['status'],'feasibility-gates-passed')
        self.assertEqual(result['total_observations'],24)
        self.assertEqual([len(g) for g in result['checks'].values()],[12,12])
        self.assertEqual([len(g) for g in result['all_invocations'].values()],[15,15])
        self.assertEqual(len(result['median_enclosures']),9)
        self.assertEqual(len(result['point_latency_gates']),13)
        self.assertFalse(result['release_acceptance']);self.assertFalse(result['full_six_boot_performance_acceptance'])
        with self.assertRaises(ValueError):backend.compare(runs)

    def test_missing_extra_reordered_point_or_completion_cannot_qualify(self):
        faults={
            'missing_observation':lambda r:r.pop('dual_invocation_role_terminal_3'),
            'extra_observation':lambda r:r.update(dual_invocation_role_terminal_6=r['dual_invocation_role_terminal_5']),
            'filtered_warm':lambda r:r['startup_role_terminal_warm_seconds']['observation_bounds'].pop(),
            'point_not_upper':lambda r:r['startup_role_terminal_cold_seconds'].update(first=.199),
            'first_after_precondition':lambda r:r['role_measurement_order'].reverse(),
            'done_false':lambda r:r.update(done=False),
            'security':lambda r:r.update(security='Permissive'),
            'awake':lambda r:r['keep_awake_restored'].update(on=True),
            'missing_component':lambda r:r.pop('observer_implementation'),
            'component_mutation':lambda r:r['observer_implementation'].update(scope='release'),
            'missing_posthash':lambda r:r.pop('role_payload_integrity'),
            'early_posthash':lambda r:r['role_payload_integrity'].update(hash_started_ns=1),
            'wrong_posthash':lambda r:r['role_payload_integrity'].update(executable_sha256='0'*64),
            'wrong_boot':lambda r:r['role_payload_integrity'].update(boot_id='00000000-0000-0000-0000-000000000009'),
            'bool_memory':lambda r:r['pristine_idle_samples'][0].update(process_pss_bytes=True),
            'missing_cpu':lambda r:r['idle_samples'].pop(),
            'bool_shell':lambda r:r['fish_seconds']['samples'].__setitem__(0,True),
            'missing_shell':lambda r:r['fish_seconds'].pop('samples'),
            'median_shell':lambda r:r['fish_seconds'].update(median=.1),
        }
        for name,change in faults.items():
            runs,backend,namespace,identity=synthetic_pair();change(runs['candidate'][0])
            with self.subTest(name=name),self.assertRaises((ValueError,KeyError,TypeError)):
                check.check_pair(runs,backend,namespace,identity)

    def test_unchanged_memory_five_and_boot_shell_ten_percent_gates(self):
        for metric in ('memory','boot','fish','bash','shell_ipc'):
            runs,backend,namespace,identity=synthetic_pair();run=runs['candidate'][0]
            if metric=='memory':
                for sample in run['pristine_idle_samples'][::5]:sample['process_pss_bytes']=1_050_010_000
            elif metric=='boot':run['boot']['analyze']='Startup finished = 11.001s'
            else:run[metric+'_seconds']=dict(median=1.1001*runs['baseline'][0][metric+'_seconds']['median'],
                samples=[1.1001*runs['baseline'][0][metric+'_seconds']['median']]*10)
            result=check.check_pair(runs,backend,namespace,identity)
            with self.subTest(metric=metric):
                self.assertEqual(result['status'],'feasibility-gates-failed')
                self.assertTrue(result['individual_precision_valid']);self.assertTrue(result['median_enclosure_valid'])
                self.assertFalse(result['memory_gate_valid'] if metric=='memory' else result['point_latency_gates_valid'])

    def test_foot_relative_budget_and_enclosure_remain_independent(self):
        runs,backend,namespace,identity=synthetic_pair();run=runs['candidate'][0]
        bound=synthetic_role_bound(run,'terminal',1,2_000_000_000,50_000_000,3_000_000)
        run['dual_invocation_role_terminal_1']=bound
        run['startup_role_terminal_cold_seconds'].update(first=.05,observation_bounds=[bound])
        result=check.check_pair(runs,backend,namespace,identity)
        self.assertEqual(result['failed_observations'],1);self.assertFalse(result['individual_precision_valid'])
        self.assertTrue(result['median_enclosure_valid']);self.assertTrue(result['point_latency_gates_valid'])
        self.assertEqual(result['checks']['candidate'][0]['maximum_interval_seconds'],.05*.025)

    def test_both_images_require_positive_finite_root_allocation_and_payload_record(self):
        faults=[('allocation_missing',None),('allocation_malformed','invalid allocation'),
            ('allocation_zero','0 /'),('allocation_negative','-1 /'),('allocation_nonfinite','9'*400+' /'),
            ('allocation_boolean',True),('payload_missing',None),('payload_empty',{}),
            ('payload_malformed','not a payload'),('payload_boolean',True)]
        for image in ('baseline','candidate'):
            for fault,value in faults:
                runs,backend,namespace,identity=synthetic_pair();run=runs[image][0]
                key='installed_bytes' if fault.startswith('allocation') else 'measured_payload'
                if value is None:run.pop(key)
                else:run[key]=value
                with self.subTest(image=image,fault=fault),self.assertRaises(ValueError):
                    check.check_pair(runs,backend,namespace,identity)

    def test_actual_checker_cli_requires_both_raw_records_and_retains_failed_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for image in ('baseline','candidate'):
                for fault in (None,'allocation_missing','allocation_zero','allocation_negative','allocation_malformed','payload_missing'):
                    runs,backend,namespace,identity=synthetic_pair();run=runs[image][0]
                    if fault=='allocation_missing':run.pop('installed_bytes')
                    elif fault=='allocation_zero':run['installed_bytes']='0 /'
                    elif fault=='allocation_negative':run['installed_bytes']='-1 /'
                    elif fault=='allocation_malformed':run['installed_bytes']='wrong /'
                    elif fault=='payload_missing':run.pop('measured_payload')
                    for name,group in runs.items():
                        (root/(name+'.log')).write_text(''.join('ARCTIC-PERFORMANCE '+json.dumps(dict(stage='installed',check=k,value=v))+'\n'
                            for k,v in group[0].items())+'ARCTIC-INSTALLED-SMOKE-EXIT=0\n')
                    result=subprocess.run([sys.executable,str(HERE/'feasibility-check.py'),'--baseline-log',str(root/'baseline.log'),
                        '--candidate-log',str(root/'candidate.log'),'--original-compare',str(BASE/'tools/performance/compare.py'),
                        '--observer-identity',identity,'--out',str(root/'result.json')],capture_output=True,text=True,timeout=10)
                    saved=json.loads((root/'result.json').read_text())
                    with self.subTest(image=image,fault=fault):
                        self.assertEqual(result.returncode,1 if fault else 0,result.stderr)
                        self.assertFalse(saved['release_acceptance']);self.assertFalse(saved['full_six_boot_performance_acceptance'])
                        self.assertEqual(saved['status'],'incomplete-or-inconsistent-feasibility' if fault else 'feasibility-gates-passed')
                        if fault:self.assertIn('error',saved)

    def test_invocation_two_requires_actual_forty_five_second_final_query(self):
        runs,backend,namespace,identity=synthetic_pair();run=runs['candidate'][0]
        b=run['dual_invocation_role_terminal_2'];app=run['app_roles']['roles']['terminal']
        self.assertTrue(check.dual_bound(b,run,app,{})['valid'])
        # Declared preconditioning metadata remains45. The raw observation alone
        # is changed, proving it cannot qualify with a five-second wait.
        b['hold_seconds']=5
        with self.assertRaisesRegex(ValueError,'hold'):check.dual_bound(b,run,app,{})
        with self.assertRaisesRegex(ValueError,'hold'):check.check_pair(runs,backend,namespace,identity)

    def test_serial_completion_markers_and_hidden_observer_failure_reject(self):
        runs,backend,namespace,identity=synthetic_pair();run=runs['candidate'][0]
        lines=''.join('ARCTIC-PERFORMANCE '+json.dumps(dict(stage='installed',check=k,value=v))+'\n' for k,v in run.items())
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'serial.log';path.write_text(lines+'ARCTIC-INSTALLED-SMOKE-EXIT=0\n')
            self.assertEqual(check.read_run(path,backend),run)
            for suffix in ('ARCTIC-INSTALLED-SMOKE-EXIT=3\n','ARCTIC-INSTALLED-SMOKE-EXIT=0\nARCTIC-INSTALLED-SMOKE-EXIT=0\n',
                'ARCTIC-PERFORMANCE '+json.dumps(dict(stage='installed',check='dual_observer_failure_role_terminal',value={}))+ '\nARCTIC-INSTALLED-SMOKE-EXIT=0\n'):
                path.write_text(lines+suffix)
                with self.subTest(suffix=suffix[:70]),self.assertRaises(ValueError):check.read_run(path,backend)


class ProofTest(unittest.TestCase):
    def accepted(self,bound=None,run=None,app=None,registry=None):
        if bound is None:bound,run,app=synthetic_bound()
        return check.dual_bound(bound,run,app,{} if registry is None else registry)

    def test_synthetic_valid_delayed_negative_cross_stream_proof(self):
        bound,run,app=synthetic_bound();result=self.accepted(bound,run,app)
        self.assertTrue(result['valid']);self.assertEqual(result['selected_stream'],'watch')
        self.assertGreater(bound['last_absent_query']['worker_received_ns'],bound['selected_upper_ns'])

    def test_fast_app_still_requires_two_point_five_percent(self):
        bound,run,app=synthetic_bound(latency_ns=50_000_000,width_ns=3_000_000)
        result=self.accepted(bound,run,app)
        self.assertFalse(result['valid']);self.assertEqual(result['maximum_interval_seconds'],.05*.025)
        self.assertLess(bound['interval_seconds'],.005)

    def test_every_raw_clock_peer_boot_ownership_and_lifecycle_mutation_rejects(self):
        faults={
            'root_uid':lambda b,r:r['app_roles']['pristine_state'].update(uid=0),
            'boolean_uid':lambda b,r:r['app_roles']['pristine_state'].update(uid=True),
            'wrong_boot':lambda b,r:b['dual_stream_evidence']['declaration'].update(boot_id='00000000-0000-0000-0000-000000000002'),
            'malformed_boot':lambda b,r:b['dual_stream_evidence']['declaration'].update(boot_id='-'*36),
            'foreign_owner':lambda b,r:b['dual_stream_evidence']['declaration'].update(rpm_owner='foreign-0:1-1.x86_64'),
            'wrong_exe':lambda b,r:b['dual_stream_evidence']['declaration']['process'].update(exe='/opt/mango'),
            'negative_receipt_lower':lambda b,r:b.update(lower_seconds=(b['last_absent_query']['worker_received_ns']-b['launch_started_monotonic_ns'])/1e9),
            'stale_negative':lambda b,r:b.update(last_absent_query=None),
            'query_clock_reorder':lambda b,r:b['dual_stream_evidence']['query_roundtrips'][1].update(worker_started_ns=b['selected_upper_ns']+1_000_000),
            'bool_clock':lambda b,r:b['dual_stream_evidence']['query_roundtrips'][1].update(worker_sent_ns=True),
            'peer_pid':lambda b,r:b['dual_stream_evidence']['ready']['peer'].update(pid=999),
            'missing_eof':lambda b,r:b['dual_stream_evidence'].update(closure=None),
            'worker_exit3':lambda b,r:b['dual_stream_evidence'].update(worker_exit=3),
            'worker_bool_exit':lambda b,r:b['dual_stream_evidence'].update(worker_exit=False),
            'partial_watch':lambda b,r:b['dual_stream_evidence']['closure'].update(partial_watch_bytes=1),
            'eof_before_hold':lambda b,r:b['dual_stream_evidence']['closure'].update(watch_eof_ns=b['selected_upper_ns']),
            'frame_counter':lambda b,r:b['dual_stream_evidence']['counter'].update(watch_frames=4),
            'byte_counter':lambda b,r:b['dual_stream_evidence']['counter'].update(socket_bytes=True),
            'raw_frame_mutation':lambda b,r:b['dual_stream_evidence']['watch_events'][1].update(raw='{"clients":[]}\n'),
            'trailing_watch':lambda b,r:b['dual_stream_evidence']['watch_events'][1].update(raw=b['dual_stream_evidence']['watch_events'][1]['raw']+'x'),
            'sequence_gap':lambda b,r:b['dual_stream_evidence']['watch_events'][1].update(sequence=3),
            'clock_regression':lambda b,r:b['dual_stream_evidence']['watch_events'][1].update(received_ns=800_000_000),
            'fake_get_for_watch':lambda b,r:b.update(first_present_query=b['last_absent_query']),
            'wrong_role':lambda b,r:b['selected_window'].update(appid='foreign'),
            'wrong_pid':lambda b,r:b['window_ownership']['process'].update(start_ticks=999),
            'disconnected_ancestry':lambda b,r:b['window_ownership']['ancestry'][0].update(parent_pid=777),
            'unowned_retained':lambda b,r:b['window_ownership'].update(model='earlier-owned-role-process'),
            'hold_weakened':lambda b,r:b.update(hold_seconds=1),
            'hold_unrun':lambda b,r:b.update(hold_verified_ns=b['selected_upper_ns']+1),
            'final_window_missing':lambda b,r:b.update(final_present_window=None),
            'helper_pss_missing':lambda b,r:b['dual_stream_evidence'].update(worker_memory_before_close=None),
        }
        for name,mutate in faults.items():
            bound,run,app=synthetic_bound();mutate(bound,run)
            with self.subTest(name=name),self.assertRaises((ValueError,TypeError,KeyError,AttributeError)):
                self.accepted(bound,run,app)

    def test_watch_stale_before_launch_or_later_upper_cannot_manufacture_precision(self):
        for stamp in (999_999_999,1_200_000_001):
            bound,run,app=synthetic_bound();bound['selected_upper_ns']=stamp
            with self.subTest(stamp=stamp),self.assertRaises(ValueError):self.accepted(bound,run,app)

    def test_retained_role_requires_previous_same_role_origin_not_foreign_registry(self):
        bound,run,app=synthetic_bound();registry={};self.accepted(bound,run,app,registry)
        warm=copy.deepcopy(bound);warm['invocation']=3
        owner=warm['window_ownership'];owner.update(invocation=3,model='earlier-owned-role-process',
            retained_identity=copy.deepcopy(owner['process']),ancestry=[owner['ancestry'][0]])
        self.accepted(warm,run,app,registry)
        with self.assertRaises(ValueError):self.accepted(warm,run,app,{})
        registry[31]['process']['start_ticks']+=1
        with self.assertRaises(ValueError):self.accepted(warm,run,app,registry)

    def test_final_get_must_start_and_send_after_required_hold_not_just_return_late(self):
        for fault in ('earlier_positive','early_started','early_send'):
            bound,run,app=synthetic_bound();upper=bound['selected_upper_ns'];final=bound['final_present_query']
            if fault=='earlier_positive':bound['final_present_query']=bound['dual_stream_evidence']['query_roundtrips'][2]
            elif fault=='early_started':
                final['parent_started_ns']=upper+4_999_999_998
                final['worker_started_ns']=upper+4_999_999_999
            else:
                final['parent_started_ns']=upper+4_999_999_997
                final['worker_started_ns']=upper+4_999_999_998;final['worker_sent_ns']=upper+4_999_999_999
            with self.subTest(fault=fault),self.assertRaisesRegex(ValueError,'hold'):
                self.accepted(bound,run,app)

    def test_boolean_window_ids_and_saved_cleanup_errors_never_alias_valid_proof(self):
        for fault in ('selected','final','ownership','cleanup'):
            bound,run,app=synthetic_bound()
            if fault=='selected':bound['selected_window']['id']=True
            elif fault=='final':bound['final_present_window']=dict(bound['final_present_window'],id=True)
            elif fault=='ownership':bound['window_ownership']['window_id']=True
            else:bound['dual_stream_evidence']['cleanup_errors']=[dict(operation='stdout-close',error='injected')]
            with self.subTest(fault=fault),self.assertRaises(ValueError):self.accepted(bound,run,app)

    def test_original_backend_is_unchanged_and_adaptations_are_exact(self):
        backend,namespace=check.load_backend(BASE/'tools/performance/compare.py')
        self.assertIsNot(namespace['role_evidence'],backend.role_evidence)
        self.assertIsNot(namespace['deferred_payload_evidence'],backend.deferred_payload_evidence)
        self.assertIs(namespace['compare'],backend.compare)
        with self.assertRaises(ValueError):backend.compare(dict(baseline=[],candidate=[]))


if __name__=='__main__':unittest.main()
