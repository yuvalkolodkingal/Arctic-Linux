#!/usr/bin/env python3
"""Fail-closed one-pair observer feasibility, never six-boot acceptance."""
import argparse
import ast
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import statistics

HERE=Path(__file__).resolve().parent
BASE_COMPARE_SHA='6565ebac71dd8f32fd08c0fdae3bdfe95677d6f487294fe7269a812bac4a87e3'
OBSERVER='mango-dual-stream-worker-v1'
FRAME_BYTES=4*1024*1024
TOTAL_BYTES=64*1024*1024
WATCH_FRAMES=4096
UUID=r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
ISO=dict(baseline='054db5c43cae47fb60f8f43efc8e052b569aa1b14e8f15adcb15cdc48265182f',
         candidate='84c9c88ebcbcaf69dbabf56509a9ceb2db58e5dc41d7bae12093edba12f60718')


def need(condition,message):
    if not condition:raise ValueError(message)


def integer(value,positive=True):
    return type(value) is int and (value>0 if positive else value>=0)


def native_identity(value):
    return (isinstance(value,dict) and set(value)=={'pid','uid','start_ticks','exe'}
            and integer(value['pid']) and integer(value['uid'],False)
            and integer(value['start_ticks']) and isinstance(value['exe'],str)
            and value['exe'].startswith('/') and not value['exe'].endswith(' (deleted)'))


def raw_snapshot(raw):
    need(isinstance(raw,str) and raw.endswith('\n') and len(raw.encode())<=FRAME_BYTES,'Missing bounded newline frame')
    need('\n' not in raw[:-1],'Multiple/trailing protocol frames')
    value=json.loads(raw)
    need(isinstance(value,dict) and set(value)=={'clients'} and isinstance(value['clients'],list),'Malformed clients frame')
    ids=[]
    for client in value['clients']:
        need(isinstance(client,dict) and integer(client.get('id')),'Malformed client ID')
        ids.append(client['id'])
    need(len(set(ids))==len(ids),'Duplicate client IDs')
    return value['clients']


def peer_evidence(peer,declaration):
    process=declaration['process']
    need(isinstance(peer,dict) and set(peer)=={'pid','uid','gid','start_ticks','exe'},'Malformed socket peer')
    need(all(integer(peer[k],k!='gid') for k in ('pid','uid','gid','start_ticks')),'Invalid peer PID/UID/start')
    need(peer['pid']==declaration['pid'] and peer['uid']==declaration['uid']
         and peer['start_ticks']==process['start_ticks'] and peer['exe']==process['exe'],'Actual socket peer changed')


def query_evidence(proof,declaration):
    need(isinstance(proof,dict),'Missing GET proof')
    fields=('parent_started_ns','worker_started_ns','worker_sent_ns','worker_frame_received_ns','worker_received_ns','parent_received_ns')
    need(all(integer(proof.get(k)) for k in fields),'Missing full GET monotonic envelope')
    need([proof[k] for k in fields]==sorted(proof[k] for k in fields),'GET clock envelope contradicts')
    need(type(proof.get('uid')) is int and proof['uid']==declaration['uid'],'GET used wrong actual UID')
    peer_evidence(proof.get('peer'),declaration)
    return raw_snapshot(proof.get('raw'))


def ownership_evidence(bound,uid,registered):
    proof=bound.get('window_ownership');window=bound['selected_window'];launch=bound.get('launch_process')
    need(isinstance(proof,dict) and native_identity(launch),'Missing actual launch/window ownership')
    process=proof.get('process');chain=proof.get('ancestry')
    need(native_identity(process) and process['uid']==uid and process['pid']==window.get('pid'),
         'Window PID/start/UID proof differs')
    need(integer(proof.get('window_id')) and proof.get('window_id')==window['id']
         and proof.get('window_pid')==window['pid']
         and proof.get('uid')==uid and proof.get('launch_wrapper_pid')==launch['pid']
         and proof.get('invocation')==bound['invocation'],'Window ownership/launch binding differs')
    need(isinstance(chain,list) and 1<=len(chain)<=64,'Missing bounded ancestry')
    core=[]
    for entry in chain:
        need(isinstance(entry,dict) and integer(entry.get('parent_pid'),False),'Missing actual parent PID')
        identity={k:v for k,v in entry.items() if k!='parent_pid'}
        need(native_identity(identity),'Malformed ancestry identity')
        core.append(identity)
    need(core[0]==process and all(a['parent_pid']==b['pid'] for a,b in zip(chain,chain[1:])),
         'Saved actual ancestry does not connect')
    origin=proof.get('origin')
    if proof.get('model')=='same-invocation-ancestry':
        need(core[-1]==launch and proof.get('retained_identity') is None,'Current launch ancestry does not reach exact wrapper')
        expected=dict(invocation=bound['invocation'],process=process,ancestry=chain,launch_wrapper_pid=launch['pid'])
        need(origin==expected,'Current invocation origin is forged')
    elif proof.get('model')=='earlier-owned-role-process':
        retained=proof.get('retained_identity')
        need(native_identity(retained) and core[-1]==retained,'Retained role ancestry does not reach exact old process')
        old=registered.get(retained['pid'])
        need(old is not None and old['process']==retained and old['origin']==origin
             and old['invocation']<bound['invocation'],'Retained process was never proved owned by this role')
    else:raise ValueError('Unapproved role ownership model')
    registered[process['pid']]=dict(process=process,origin=origin,invocation=bound['invocation'])


def dual_bound(bound,run,app,registered):
    need(isinstance(bound,dict) and bound.get('observer')==OBSERVER
         and bound.get('bound_basis')=='dual-stream-send-to-complete-frame-v1','Unknown observer proof')
    launch=bound.get('launch_started_monotonic_ns');upper=bound.get('selected_upper_ns')
    need(integer(launch) and integer(upper) and launch<=upper,'Missing launch/selected upper clocks')
    e=bound.get('dual_stream_evidence');need(isinstance(e,dict),'Missing dual-stream lifecycle evidence')
    declaration=e.get('declaration');need(isinstance(declaration,dict),'Missing compositor declaration')
    process=declaration.get('process');uid=run['app_roles']['pristine_state']['uid']
    need(integer(uid) and declaration.get('uid')==uid and native_identity(process)
         and process['uid']==uid and process['pid']==declaration.get('pid')
         and process['exe']=='/usr/bin/mango','Wrong actual compositor process/UID')
    context=run['app_roles']['boot_context'];image=run['app_roles']['image']
    need(declaration.get('boot_id')==run['identity']['boot_id'] and re.fullmatch(UUID,declaration['boot_id'])
         and declaration.get('image')==image and type(declaration.get('boot')) is int
         and declaration['boot']==context['boot']==1,'Wrong boot/image proof')
    need(isinstance(declaration.get('session_id'),str) and declaration['session_id']
         and isinstance(declaration.get('wayland_display'),str) and declaration['wayland_display'],'Missing actual session identity')
    need(declaration.get('socket_path','').startswith('/run/user/'+str(uid)+'/')
         and isinstance(declaration.get('socket_identity'),list) and len(declaration['socket_identity'])==3
         and all(integer(n) for n in declaration['socket_identity'])
         and declaration['socket_identity'][2]==uid,'Wrong actual socket identity')
    expected='d13da6c' if image=='baseline' else 'fe4742c' if image=='candidate' else ''
    owner=declaration.get('rpm_owner','')
    need(expected and re.fullmatch(r'mangowm-0:0\.17\.3-[^\s]+\.git'+expected+r'\.fc44\.x86_64',owner)
         and owner in run['rpm_inventory']['nevra'],'Compositor RPM/source ownership differs')
    file=declaration.get('executable_identity',{})
    need(set(file)=={'device','inode','size','mtime_ns','ctime_ns'}
         and all(integer(v,k!='device') for k,v in file.items()),'Compositor executable metadata proof missing')
    worker=e.get('worker');need(native_identity(worker) and worker['uid']==uid,'Missing actual worker identity')
    ready=e.get('ready');closure=e.get('closure')
    need(isinstance(ready,dict) and ready.get('kind')=='ready' and isinstance(closure,dict)
         and closure.get('kind')=='closed' and type(e.get('worker_exit')) is int and e['worker_exit']==0
         and e.get('failed_worker_evidence') is None and e.get('cleanup_errors')==[],
         'Observer failed or lacks mandatory closure/cleanup proof')
    for state in (ready,closure):
        need(state.get('uid')==uid and state.get('worker_process')==worker
             and state.get('worker_pid')==worker['pid'],'Worker identity changed during lifecycle')
        need(integer(state.get('parent_started_ns')) and integer(state.get('parent_received_ns'))
             and state['parent_started_ns']<=state['parent_received_ns'],'Lifecycle clocks malformed')
        usage=state.get('worker_usage',{})
        need(set(usage)=={'user_seconds','system_seconds','maximum_rss_kib'}
             and all(isinstance(n,(int,float)) and not isinstance(n,bool) and math.isfinite(n) and n>=0 for n in usage.values())
             and integer(usage['maximum_rss_kib']),'Missing helper overhead accounting')
        need(isinstance(state.get('cpu_seconds'),(int,float)) and not isinstance(state['cpu_seconds'],bool)
             and math.isclose(state['cpu_seconds'],usage['user_seconds']+usage['system_seconds'],abs_tol=1e-12),
             'Worker CPU accounting differs')
    peer_evidence(ready.get('peer'),declaration)
    queries=e.get('query_roundtrips');events=e.get('watch_events')
    need(isinstance(queries,list) and queries and len(queries)<=1000000 and isinstance(events,list)
         and 1<=len(events)<=WATCH_FRAMES,'Missing bounded GET/watch records')
    query_clients=[];socket_bytes=0
    for index,proof in enumerate(queries):
        query_clients.append(query_evidence(proof,declaration));socket_bytes+=len(proof['raw'].encode())
        if index:need(queries[index-1]['parent_received_ns']<=proof['parent_started_ns'],'GET requests overlap or reorder')
    for index,event in enumerate(events):
        need(isinstance(event,dict) and event.get('sequence')==index+1 and type(event.get('sequence')) is int
             and integer(event.get('received_ns')) and ready['parent_started_ns']<=event['received_ns']<=closure['parent_received_ns'],
             'Malformed/reordered watch clock or sequence')
        if index:need(events[index-1]['received_ns']<=event['received_ns'],'Watch clocks regress')
        peer_evidence(event.get('peer'),declaration)
        clients=raw_snapshot(event.get('raw'))
        need(event.get('payload')==dict(clients=clients),'Watch raw bytes differ from payload')
        socket_bytes+=len(event['raw'].encode())
    need(events[0]['received_ns']<=ready['parent_received_ns']<launch,'Initial watch readiness follows launch')
    need(closure.get('partial_watch_bytes')==0 and type(closure.get('partial_watch_bytes')) is int
         and integer(closure.get('watch_eof_ns')) and closure['parent_started_ns']<=closure['watch_eof_ns']<=closure['parent_received_ns']
         and events[-1]['received_ns']<=closure['watch_eof_ns'],'Mandatory watch EOF/partial-frame proof differs')
    counter=e.get('counter')
    need(isinstance(counter,dict) and set(counter)=={'socket_bytes','watch_frames','get_frames','get_queries'}
         and all(integer(n,False) for n in counter.values())
         and counter==dict(socket_bytes=socket_bytes,watch_frames=len(events),get_frames=len(queries),get_queries=len(queries))
         and socket_bytes<=TOTAL_BYTES and closure.get('counter')==counter,'Raw bytes/frame/query counters differ')
    memory=e.get('worker_memory_before_close',{})
    need(memory.get('process')==worker and memory.get('phase')=='post-hold-before-worker-close'
         and integer(memory.get('pss_bytes')) and integer(memory.get('private_bytes')),'Missing actual helper PSS/private scope')
    before=bound.get('before_client_ids');need(isinstance(before,list) and before==sorted(set(before))
         and all(isinstance(n,str) and n.isdigit() for n in before),'Malformed initial IDs')
    need(set(before)=={str(c['id']) for c in query_clients[0]}=={str(c['id']) for c in events[0]['payload']['clients']}
         and queries[0]['parent_received_ns']<launch,'CLI/GET/watch initial membership proof differs')
    window=bound.get('selected_window');need(isinstance(window,dict) and integer(window.get('id'))
         and str(window.get('id')) not in before
         and integer(window.get('pid')) and str(window.get('appid','')).lower() in app['appids'],'Selected window is stale or wrong role')
    wid=window['id'];possibilities=[]
    def represented(clients):
        return any(c.get('id')==wid and c.get('pid')==window['pid']
                   and str(c.get('appid','')).lower() in app['appids'] for c in clients)
    for event in events:
        if event['received_ns']>=launch and represented(event['payload']['clients']):
            possibilities.append((event['received_ns'],'watch',event))
    for query,clients in zip(queries,query_clients):
        if query['worker_frame_received_ns']>=launch and represented(clients):
            possibilities.append((query['worker_frame_received_ns'],'get',query))
    need(possibilities,'Selected positive frame never contained that actual client')
    selected=min(possibilities,key=lambda row:row[0])
    need((upper,bound.get('selected_stream'),bound.get('selected_positive'))==selected,'Selected upper is not the earliest valid represented positive')
    need(window in (selected[2]['payload']['clients'] if selected[1]=='watch' else raw_snapshot(selected[2]['raw'])),
         'Selected exact window differs from its positive frame')
    if selected[1]=='get':need(bound.get('first_present_query')==selected[2],'Actual selected GET differs')
    else:need(bound.get('first_present_query') is None,'Watch receipt was disguised as a GET')
    negatives=[q for q,clients in zip(queries,query_clients) if launch<=q['worker_sent_ns']<=upper
               and all(c['id']!=wid for c in clients)]
    negative=max(negatives,key=lambda q:q['worker_sent_ns']) if negatives else None
    need(bound.get('last_absent_query')==negative,'Selected negative SEND is missing, stale or receipt-based')
    lower=negative['worker_sent_ns'] if negative else launch
    values=[bound.get(k) for k in ('lower_seconds','upper_seconds','interval_seconds')]
    need(all(isinstance(n,(float,int)) and not isinstance(n,bool) and math.isfinite(n) and n>=0 for n in values),
         'Malformed numerical bound')
    need(all(math.isclose(bound[key],value,abs_tol=1e-9,rel_tol=1e-9) for key,value in
         [('lower_seconds',(lower-launch)/1e9),('upper_seconds',(upper-launch)/1e9),('interval_seconds',(upper-lower)/1e9)]),
         'Raw selected clocks and reported bracket differ')
    held=bound.get('hold_verified_ns');hold=bound.get('hold_seconds');invocation=bound.get('invocation')
    need(integer(invocation),'Missing per-role invocation identity')
    required_hold=45 if invocation==2 else 5
    need(type(hold) is int and hold==required_hold and integer(held) and held>=upper+required_hold*1_000_000_000,
         'Persistent-window hold was weakened')
    final=bound.get('final_present_query')
    need(final in queries and final['worker_started_ns']>=upper+required_hold*1_000_000_000
         and final['worker_sent_ns']>=upper+required_hold*1_000_000_000 and final['worker_received_ns']<=held,
         'Missing final actual GET after required hold')
    final_window=bound.get('final_present_window')
    need(isinstance(final_window,dict) and integer(final_window.get('id'))
         and final_window in raw_snapshot(final['raw'])
         and final_window.get('id')==wid and final_window.get('pid')==window['pid']
         and str(final_window.get('appid','')).lower() in app['appids'],'Final mapped role/window differs')
    need(held<=closure['parent_started_ns'],'Observer closure preceded hold')
    need(integer(bound.get('invocation')),'Missing per-role invocation identity')
    ownership_evidence(bound,uid,registered)
    limit=min(.005,bound['upper_seconds']*.025)
    return dict(interval_seconds=bound['interval_seconds'],maximum_interval_seconds=limit,
        valid=bound['interval_seconds']<=limit,selected_stream=bound['selected_stream'],
        selected_upper_ns=upper,lower_ns=lower,window_id=wid,invocation=bound['invocation'])


def load_backend(path):
    source=path.read_text();need(hashlib.sha256(source.encode()).hexdigest()==BASE_COMPARE_SHA,'Original comparator source differs')
    spec=importlib.util.spec_from_file_location('unchanged_full_comparison',path)
    backend=importlib.util.module_from_spec(spec);spec.loader.exec_module(backend)
    namespace=dict(vars(backend));tree=ast.parse(source)
    # Only this separate one-pair diagnostic adapts cardinality and the explicit
    # selected-upper endpoint. The original compare(), thresholds and all other
    # role/payload guards stay unchanged and cannot accept a two-boot release.
    for name,old,new in (
        ('role_evidence',"if len({context['boot'] for context in contexts}) != 3:",
                         "if len({context['boot'] for context in contexts}) != 1:"),
        ('deferred_payload_evidence',"bound.get('first_present_query',{}).get('worker_received_ns')", "bound.get('selected_upper_ns')")):
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
        fragment=ast.get_source_segment(source,node);need(fragment.count(old)==1,'Expected diagnostic adaptation differs: '+name)
        exec(compile(fragment.replace(old,new,1),'<declared-one-pair-'+name+'>','exec'),namespace)
    return backend,namespace


def read_run(path,backend):
    text=path.read_text(errors='strict');counts={};records={}
    exits=[]
    for line in text.splitlines():
        line=line.strip('\r')
        if line.startswith('ARCTIC-INSTALLED-SMOKE-EXIT='):exits.append(line.split('=',1)[1])
        if not line.startswith('ARCTIC-PERFORMANCE '):continue
        value=json.loads(line[len('ARCTIC-PERFORMANCE '):]);need(value.get('stage')=='installed','Wrong diagnostic stage')
        check=value['check'];counts[check]=counts.get(check,0)+1;records[check]=value['value']
    need(exits==['0'],'Missing/duplicate/nonzero actual installed smoke exit')
    need(all(n==1 or key.startswith(('mapped_window_','app_workload_')) for key,n in counts.items()),'Duplicate critical diagnostic record')
    original=backend.read_run(path)
    need(records==original,'Anchored diagnostic records differ from original parser')
    need(not any(key.startswith('dual_observer_failure_') for key in records),'A failed observer was hidden by later DONE')
    return records



def raw_completeness(run):
    raw=run.get('installed_bytes')
    need(isinstance(raw,str),'Missing installed root allocation record')
    try:
        allocation=int(raw.split()[0])
        finite=math.isfinite(allocation)
    except (IndexError,TypeError,ValueError,OverflowError) as error:
        raise ValueError('Malformed installed root allocation record') from error
    need(finite and allocation>0,'Installed root allocation must be positive and finite')
    payload=run.get('measured_payload')
    need(isinstance(payload,dict) and payload,'Missing/malformed measured payload record')
    return allocation,payload


def check_pair(runs,backend,namespace,observer_identity):
    need(set(runs)=={'baseline','candidate'} and all(len(group)==1 for group in runs.values()),'Exactly one fresh boot of each fixed image required')
    flat=[runs[name][0] for name in ('baseline','candidate')]
    spec=importlib.util.spec_from_file_location('diagnostic_composer',HERE/'compose-feasibility.py')
    composer=importlib.util.module_from_spec(spec);spec.loader.exec_module(composer)
    _,expected_identity,parts=composer.components(Path(backend.__file__).with_name('guest.py').read_text(),
        (HERE/'dual-observer.py').read_text())
    need(observer_identity==expected_identity,'Expected composed observer identity differs from pinned sources')
    need(all(r.get('done') is True and r.get('security')=='Enforcing'
        and r.get('measurement_conditions',{}).get('initial_keep_awake',{}).get('on') is False
        and r.get('keep_awake_restored',{}).get('on') is False
        and r.get('observer_implementation')==parts for r in flat),
        'Missing completion/security/default-preferences or exact observer component proof')
    need(len({r['identity']['boot_id'] for r in flat})==2,'Repeated/missing boot IDs')
    need(all(r.get('observer_source_sha256')==observer_identity for r in flat),'Observer composition identity differs')
    raw_records={image:raw_completeness(runs[image][0]) for image in runs}
    attribution=backend.package_attribution(runs);roles=namespace['role_evidence'](runs)
    checks={};cpu={};invocations={}
    for image in ('baseline','candidate'):
        run=runs[image][0];context=run['app_roles']['boot_context']
        need(context['boot']==1 and context['iso_sha256']==ISO[image],'Wrong fixed-image fresh boot context')
        backend.idle_sample_layout(run['pristine_idle_samples']);backend.idle_sample_layout(run['idle_samples'])
        cpu[image]=dict(pristine=backend.cpu_validity(run,'pristine_idle_samples'),
            normalized=backend.cpu_validity(run,worker=run['role_workload']))
        selected=[];invocations[image]=[]
        expected_invocations={'dual_invocation_role_'+role+'_'+str(n) for role in backend.ROLE_ORDER for n in range(1,6)}
        need({key for key in run if key.startswith('dual_invocation_')}==expected_invocations,'Extra/missing role invocations')
        for role in backend.ROLE_ORDER:
            registry={};app=run['app_roles']['roles'][role]
            bounds=[]
            for n in range(1,6):
                key='dual_invocation_role_'+role+'_'+str(n)
                need(key in run,'Missing unfiltered role invocation: '+key)
                bound=run[key];need(bound.get('invocation')==n,'Role invocation order differs')
                proof=dual_bound(bound,run,app,registry);invocations[image].append(dict(role=role,**proof));bounds.append(bound)
            cold=run['startup_role_'+role+'_cold_seconds'];warm=run['startup_role_'+role+'_warm_seconds']
            need(cold.get('observer')==warm.get('observer')==OBSERVER
                 and cold.get('observation_bounds')==bounds[:1] and warm.get('observation_bounds')==bounds[2:]
                 and cold.get('poll_sleep_seconds')==warm.get('poll_sleep_seconds')==.00025,
                 'Cold/warm observations differ from complete raw invocations')
            values=[cold['first'],warm['first'],*warm.get('warm',[])]
            need(len(values)==4 and all(not isinstance(value,bool) and isinstance(value,(int,float)) and math.isfinite(value)
                 and value==bound['upper_seconds'] for value,bound in zip(values,[bounds[0],*bounds[2:]])),
                 'Point latency must equal selected conservative upper')
            for phase,indices in [('cold',[0]),('warm',[2,3,4])]:
                for index in indices:
                    bound=bounds[index];limit=min(.005,bound['upper_seconds']*.025)
                    selected.append(dict(role=role,phase=phase,invocation=index+1,
                        upper_seconds=bound['upper_seconds'],interval_seconds=bound['interval_seconds'],
                        maximum_interval_seconds=limit,valid=bound['interval_seconds']<=limit,
                        selected_stream=bound['selected_stream']))
        need(len(selected)==12,'Unexpected role-observation count')
        cold=[run['dual_invocation_role_'+role+'_1'] for role in backend.ROLE_ORDER]
        preparation=[run['dual_invocation_role_'+role+'_2'] for role in backend.ROLE_ORDER]
        warmed=[run['dual_invocation_role_'+role+'_'+str(n)] for role in backend.ROLE_ORDER for n in (3,4,5)]
        need(max(b['hold_verified_ns'] for b in cold)<=min(b['launch_started_monotonic_ns'] for b in preparation)
             and max(b['hold_verified_ns'] for b in preparation)<=min(b['launch_started_monotonic_ns'] for b in warmed),
             'First GUI/preconditioning/warm execution ordering changed')
        checks[image]=selected
    enclosures=backend.mapping_enclosures(runs)
    memory={}
    for phase,key in [('pristine','pristine_idle_samples'),('normalized','idle_samples')]:
        for metric in ('process_pss_bytes','process_private_bytes'):
            values={image:statistics.median(s[metric] for s in runs[image][0][key] if metric in s) for image in runs}
            memory[phase+'_'+metric]=dict(values=values,regression_threshold_percent=5,
                regression=values['candidate']>values['baseline']*1.05 and not math.isclose(values['candidate'],values['baseline']*1.05,rel_tol=1e-12))
    valid=all(row['valid'] for group in checks.values() for row in group)
    enclosure=all(row['threshold_enclosure_valid'] for row in enclosures.values())
    memory_valid=not any(row['regression'] for row in memory.values())
    latency={}
    def point_gate(name,values):
        need(all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and v>0 for v in values.values()),
             'Invalid point latency: '+name)
        latency[name]=dict(values=values,regression_threshold_percent=10,
            regression=values['candidate']>values['baseline']*1.10
            and not math.isclose(values['candidate'],values['baseline']*1.10,rel_tol=1e-12))
    point_gate('boot_systemd_total',{image:backend.boot_seconds(runs[image][0]) for image in runs})
    for app in ('fish','bash','shell_ipc'):
        values={}
        for image in runs:
            timing=runs[image][0][app+'_seconds'];samples=timing.get('samples')
            need(isinstance(samples,list) and len(samples)==10 and all(isinstance(n,(int,float))
                 and not isinstance(n,bool) and math.isfinite(n) and n>0 for n in samples),
                 'Missing raw shell latency samples')
            need(timing.get('median')==statistics.median(samples),'Shell point median differs from raw samples')
            values[image]=timing['median']
        point_gate(app+'_launch_or_roundtrip',values)
    for metric,key,indices in backend.mapped_metrics(True):
        values={image:statistics.median([runs[image][0][key]['first'],*runs[image][0][key].get('warm',[])][index]
            for index in indices) for image in runs}
        point_gate(metric,values)
    latency_valid=not any(row['regression'] for row in latency.values())
    return dict(schema='arctic-one-pair-precision-feasibility-v1',
        status='feasibility-gates-passed' if valid and enclosure and memory_valid and latency_valid else 'feasibility-gates-failed',
        individual_precision_valid=valid,checks=checks,total_observations=24,
        failed_observations=sum(not row['valid'] for group in checks.values() for row in group),
        all_invocations=invocations,median_enclosures=enclosures,median_enclosure_valid=enclosure,
        memory_gate=memory,memory_gate_valid=memory_valid,cpu_validity=cpu,
        point_latency_gates=latency,point_latency_gates_valid=latency_valid,
        application_roles=roles,package_attribution=attribution,
        root_filesystem_du_allocation_bytes={image:value[0] for image,value in raw_records.items()},
        measured_payload={image:value[1] for image,value in raw_records.items()},
        full_six_boot_performance_acceptance=False,release_acceptance=False,
        interpretation='One boot per fixed image is an instrumentation feasibility diagnostic; all 24 planned observations are retained, and no full performance or gain claim follows')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-log',type=Path,required=True);parser.add_argument('--candidate-log',type=Path,required=True)
    parser.add_argument('--original-compare',type=Path,default=HERE.parent/'performance/compare.py')
    parser.add_argument('--observer-identity',required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    try:
        backend,namespace=load_backend(args.original_compare)
        runs={image:[read_run(getattr(args,image+'_log'),backend)] for image in ('baseline','candidate')}
        payload=runs['candidate'][0]['measured_payload']
        need('.gitfe4742c' in payload['arctic_shell']
             and payload['catalog_sha256'].split()[0]=='3d5c34c6a79fd5c24c1f733792ef56816089f38678a187337a13f2964c92116e'
             and payload['battery_sha256'].split()[0]=='e33a7dd29ef10cf5671b6984aaa1a690a994baa460ffdcacf0f49adfabffea35',
             'Candidate source/core payload differs')
        result=check_pair(runs,backend,namespace,args.observer_identity)
    except Exception as error:result=dict(status='incomplete-or-inconsistent-feasibility',error=str(error),release_acceptance=False,full_six_boot_performance_acceptance=False)
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('package_attribution','application_roles')},indent=2))
    return 0 if result['status']=='feasibility-gates-passed' else 1


if __name__=='__main__':raise SystemExit(main())
