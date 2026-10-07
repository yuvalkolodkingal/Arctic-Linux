#!/usr/bin/env python3
"""Two-arm native argv mechanism diagnostic; never clears prior performance failures."""
import argparse
import ast
import base64
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import statistics

HERE=Path(__file__).resolve().parent
PRIOR=HERE.parent/'precision-feasibility'
PRIOR_CHECK_SHA='28eeb383bd0eafaddd8a0d23c331dd58578dc2323f7e41115901579debe54925'
ARMS=('historical-new-window','native-product-argv')
SCHEMA='arctic-browser-native-argv-v1'
ISO='84c9c88ebcbcaf69dbabf56509a9ceb2db58e5dc41d7bae12093edba12f60718'
PROFILE='6f65135a62c397c374f367de459aed784519c2040195ee41d88300996c9b7b2b'


def require(condition,message):
    if not condition:raise ValueError(message)


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


def dependencies():
    path=PRIOR/'feasibility-check.py'
    require(hashlib.sha256(path.read_bytes()).hexdigest()==PRIOR_CHECK_SHA,'Frozen checker differs')
    prior=load(path,'frozen_route_proof_checker')
    backend,namespace=prior.load_backend(HERE.parent/'performance/compare.py')
    source=Path(backend.__file__).read_text();tree=ast.parse(source)
    for name,replacements in (
        ('role_evidence',(
            ("if len({context['boot'] for context in contexts}) != 3:","if len({context['boot'] for context in contexts}) != 1:"),
            ("                for phase in ('cold', 'warm'):","                if role != 'browser':\n                    continue\n                for phase in ('cold', 'warm'):"),
            ("for role in ROLE_ORDER]\n            if run.get('role_measurement_order')", "for role in ('browser',)]\n            if run.get('role_measurement_order')"))),
        ('deferred_payload_evidence',(
            ("bound.get('first_present_query',{}).get('worker_received_ns')","bound.get('selected_upper_ns')"),
            ("for role in ROLE_ORDER]","for role in ('browser',)]")))):
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
        fragment=ast.get_source_segment(source,node)
        for old,new in replacements:
            require(fragment.count(old)==1,'Transparent browser-only validation delta differs: '+name)
            fragment=fragment.replace(old,new,1)
        exec(compile(fragment,'<browser-only-validation-'+name+'>','exec'),namespace)
    # This private import is used only for the three browser metric enclosures.
    # Full core-role identities are still checked by the separate namespace.
    backend.ROLE_ORDER=('browser',)
    return prior,backend,namespace


def session_evidence(value,uid):
    require(isinstance(value,dict) and value.get('uid')==uid and type(value.get('uid')) is int
        and type(value.get('exists')) is bool,'Missing actual-user session evidence')
    require(isinstance(value.get('path'),str) and re.fullmatch(r'/home/[^/]+/\.local/share/epiphany/session_state\.xml',value['path']),
        'Unexpected default-profile session path')
    require(all(type(value.get(k)) is int and value[k]>0 for k in ('started_ns','finished_ns'))
        and value['started_ns']<=value['finished_ns'],'Missing ordered session read clocks')
    if value['exists']:
        require(type(value.get('bytes')) is int and 0<value['bytes']<=1024*1024
            and re.fullmatch('[0-9a-f]{64}',value.get('sha256','')),'Unbounded/missing session bytes')
        identity=value.get('file_identity',{})
        require(set(identity)=={'device','inode','size','mtime_ns','ctime_ns'}
            and all(type(v) is int and v>=0 for v in identity.values())
            and identity['inode']>0 and identity['size']==value['bytes'],'Missing session stat identity')
        require(type(value.get('window_count')) is int and 0<=value['window_count']<=16
            and isinstance(value.get('tabs'),list) and len(value['tabs'])<=256,'Unbounded session XML counts')
        require(all(isinstance(t,dict) and set(t)=={'uri_kind','uri_sha256'}
            and t['uri_kind'] in ('local-fixture','internal-page','other-uri')
            and re.fullmatch('[0-9a-f]{64}',t['uri_sha256']) for t in value['tabs']),
            'Unbounded/unclassified session URI export')
    else:
        require(not any(k in value for k in ('bytes','sha256','file_identity','window_count','tabs')),
            'Absent session carries substituted file content')


def supplemental_evidence(trace,arm,n,bound,uid,url,last_offset,last_inode):
    require(isinstance(trace,dict) and trace.get('schema')==SCHEMA and trace.get('arm')==arm
        and type(trace.get('invocation')) is int and trace['invocation']==n
        and trace.get('direct_native_argv_only') is True
        and trace.get('detached_arctic_open_timing_included') is False,'Missing exact native argv scope')
    expected=['epiphany','--new-window',url] if arm==ARMS[0] else ['epiphany',url]
    require(trace.get('argv')==expected,'Another argument/remote URI differs')
    require(trace.get('launcher_exit_status_observed') is False
        and trace.get('launcher_grace_outcome_observed') is False
        and trace.get('supplemental_collection_errors')==[],'Hidden supplemental failure or invented exit proof')
    require(trace.get('mapped_upper_seconds')==bound['upper_seconds']
        and type(trace.get('observer_returned_ns')) is int
        and trace['observer_returned_ns']>=bound['hold_verified_ns'],'Supplemental map/return clocks differ')
    before=trace.get('session_before');after=trace.get('session_after')
    session_evidence(before,uid);session_evidence(after,uid)
    require(before['path']==after['path'] and before['finished_ns']<=bound['launch_started_monotonic_ns']
        and after['started_ns']>=trace['observer_returned_ns'],'Session read entered the mapping/hold interval')
    stderr=trace.get('stderr')
    require(isinstance(stderr,dict) and stderr.get('exists') is True
        and type(stderr.get('offset')) is int and stderr['offset']==last_offset
        and type(stderr.get('bytes')) is int and stderr['bytes']>=0
        and type(stderr.get('total_bytes')) is int and stderr['total_bytes']==stderr['offset']+stderr['bytes']
        and stderr['total_bytes']<=512*1024 and re.fullmatch('[0-9a-f]{64}',stderr.get('sha256',''))
        and isinstance(stderr.get('text'),str) and len(stderr['text'].encode())<=3*512*1024,
        'Missing/capped/discontinuous application stderr evidence')
    identity=stderr.get('file_identity',{})
    require(all(type(stderr.get(k)) is int and stderr[k]>0 for k in ('started_ns','finished_ns'))
        and trace['observer_returned_ns']<=stderr['started_ns']<=stderr['finished_ns'],
        'Stderr read entered measurement or lacks its timing scope')
    try:
        encoded=stderr.get('raw_base64')
        require(isinstance(encoded,str) and len(encoded)<=4*((512*1024+2)//3),'Unbounded raw stderr transport')
        raw=base64.b64decode(encoded,validate=True)
    except (TypeError,ValueError) as error:
        raise ValueError('Malformed raw stderr transport') from error
    require(len(raw)==stderr['bytes'] and hashlib.sha256(raw).hexdigest()==stderr['sha256']
        and raw.decode('utf-8',errors='replace')==stderr['text'],'Application stderr bytes/hash/text differ')
    require(set(identity)=={'device','inode','size','mtime_ns','ctime_ns'}
        and all(type(v) is int and v>=0 for v in identity.values())
        and identity['inode']>0 and identity['size']==stderr['total_bytes'],'Missing app log identity')
    current={k:identity[k] for k in ('device','inode')}
    require(last_inode is None or current==last_inode,'Owned app log replaced')
    return stderr['total_bytes'],current


def check(runs,prior,backend,namespace,identity,parts):
    require(set(runs)==set(ARMS),'Exactly two native argv arms required')
    require(len({run['identity']['boot_id'] for run in runs.values()})==2,'Distinct fresh boots required')
    summaries={};raw={};checks={};all_bounds={};cpu={};semantic={}
    for arm in ARMS:
        run=runs[arm]
        require(run.get('done') is True and run.get('security')=='Enforcing'
            and run.get('observer_source_sha256')==identity and run.get('observer_implementation')==parts,
            'Missing exact completion/security/composition proof')
        marker=run.get('browser_route_diagnostic',{})
        require(marker==dict(schema=SCHEMA,arm=arm,planned_invocations=5,measured_roles=['browser'],
            declared_core_roles=['terminal','files','browser'],direct_native_argv_only=True,
            detached_arctic_open_timing_included=False,session_reads_outside_mapping_interval=True,
            session_read_cache_overhead_declared=True,observer_and_cleanup_unchanged=True,
            full_six_boot_performance_acceptance=False,release_acceptance=False),'Diagnostic scope marker differs')
        declaration=run['app_roles'];context=declaration['boot_context']
        require(context.get('browser_route_arm')==arm and context.get('browser_route_schema')==SCHEMA
            and context.get('image')==declaration.get('image')=='candidate'
            and type(context.get('boot')) is int and context['boot']==1
            and context.get('iso_sha256')==ISO and context.get('install_profile_sha256')==PROFILE,
            'Fixed candidate/profile/arm context differs')
        raw[arm]=prior.raw_completeness(run)
        summaries[arm]=namespace['role_evidence']({'candidate':[run]})['candidate']
        require(declaration['roles']['browser']['configured_command']=='epiphany','Direct configured native selection required')
        backend.idle_sample_layout(run['pristine_idle_samples']);backend.idle_sample_layout(run['idle_samples'])
        cpu[arm]=dict(pristine=backend.cpu_validity(run,'pristine_idle_samples'),
            normalized=backend.cpu_validity(run,worker=run['role_workload']))
        require({key for key in run if key.startswith('dual_invocation_')}==
            {'dual_invocation_role_browser_'+str(n) for n in range(1,6)},'Extra/missing browser invocations')
        require({key for key in run if key.startswith('browser_route_invocation_')}==
            {'browser_route_invocation_'+str(n) for n in range(1,6)},'Extra/missing supplemental invocation evidence')
        registry={};bounds=[];selected=[];semantics=[];last_offset=0;last_inode=None
        require({key for key in run if key.startswith('startup_role_')}==
            {'startup_role_browser_cold_seconds','startup_role_browser_warm_seconds'}
            and {key for key in run if key.startswith('precondition_role_')}=={'precondition_role_browser'},
            'Unexpected GUI role or hidden timing record')
        uid=declaration['pristine_state']['uid'];url=run['role_workload']['url']
        for n in range(1,6):
            b=run['dual_invocation_role_browser_'+str(n)]
            require(type(b.get('invocation')) is int and b['invocation']==n,'Raw invocation index differs')
            prior.dual_bound(b,run,declaration['roles']['browser'],registry)
            last_offset,last_inode=supplemental_evidence(run['browser_route_invocation_'+str(n)],arm,n,b,uid,url,last_offset,last_inode)
            bounds.append(b)
            clients=prior.raw_snapshot(b['final_present_query']['raw'])
            owned=[w for w in clients if w.get('pid')==b['selected_window']['pid']
                and str(w.get('appid','')).lower() in ('org.gnome.epiphany','epiphany')]
            expected_count=2 if arm==ARMS[0] else 1
            correct_fixture=any(w.get('title')=='Arctic startup fixture' and w.get('is_focused') is True for w in owned)
            semantics.append(dict(invocation=n,windows=owned,observed_window_count=len(owned),
                expected_window_count=expected_count,expected_window_semantics=len(owned)==expected_count,
                focused_fixture_title_observed=correct_fixture,
                page_ready_or_rendered_content_qualified=False))
            limit=min(.005,b['upper_seconds']*.025)
            selected.append(dict(invocation=n,upper_seconds=b['upper_seconds'],interval_seconds=b['interval_seconds'],
                maximum_interval_seconds=limit,valid=b['interval_seconds']<=limit,selected_stream=b['selected_stream']))
        cold=run['startup_role_browser_cold_seconds'];warm=run['startup_role_browser_warm_seconds']
        require(cold.get('observer')==warm.get('observer')==prior.OBSERVER
            and cold.get('observation_bounds')==bounds[:1] and warm.get('observation_bounds')==bounds[2:]
            and cold.get('poll_sleep_seconds')==warm.get('poll_sleep_seconds')==.00025,'Cold/warm raw bounds differ')
        values=[cold.get('first'),warm.get('first'),*warm.get('warm',[])]
        require(len(values)==4 and all(type(v) in (int,float) and math.isfinite(v)
            and v==b['upper_seconds'] for v,b in zip(values,[bounds[0],*bounds[2:]])),
            'Point timing is not the selected conservative upper')
        require(bounds[0]['hold_verified_ns']<=bounds[1]['launch_started_monotonic_ns']
            and bounds[1]['hold_verified_ns']<=bounds[2]['launch_started_monotonic_ns']
            and all(a['hold_verified_ns']<=b['launch_started_monotonic_ns'] for a,b in zip(bounds,bounds[1:])),
            'First-use/precondition/warm order differs')
        first_trace=run['browser_route_invocation_1']
        require(run['role_payload_integrity']['measurement_returned_ns']>=max(
            first_trace['session_after']['finished_ns'],first_trace['stderr']['finished_ns']),
            'First-GUI integrity verification preceded supplemental return/cleanup')
        checks[arm]=selected;semantic[arm]=semantics;all_bounds[arm]=bounds
    comparison={'baseline':[runs[ARMS[0]]],'candidate':[runs[ARMS[1]]]}
    enclosures=backend.mapping_enclosures(comparison)
    point={}
    for metric,key,indices in backend.mapped_metrics(True):
        values={arm:statistics.median([runs[arm][key]['first'],*runs[arm][key].get('warm',[])][i] for i in indices) for arm in ARMS}
        require(all(type(v) in (int,float) and math.isfinite(v) and v>0 for v in values.values()),'Invalid browser point timing')
        point[metric]=dict(values=values,reference_arm=ARMS[0],comparison_arm=ARMS[1],regression_threshold_percent=10,
            regression=values[ARMS[1]]>1.10*values[ARMS[0]] and not math.isclose(values[ARMS[1]],1.10*values[ARMS[0]],rel_tol=1e-12))
    memory={}
    for phase,key in (('pristine','pristine_idle_samples'),('normalized','idle_samples')):
        for field in ('process_pss_bytes','process_private_bytes'):
            values={arm:statistics.median(s[field] for s in runs[arm][key] if field in s) for arm in ARMS}
            memory[phase+'_'+field]=dict(values=values,regression_threshold_percent=5,
                regression=values[ARMS[1]]>values[ARMS[0]]*1.05 and not math.isclose(values[ARMS[1]],values[ARMS[0]]*1.05,rel_tol=1e-12))
    precision=all(row['valid'] for group in checks.values() for row in group)
    semantic_valid=all(row['expected_window_semantics'] and row['focused_fixture_title_observed'] for group in semantic.values() for row in group)
    enclosure=all(row['threshold_enclosure_valid'] for row in enclosures.values())
    point_valid=not any(row['regression'] for row in point.values())
    memory_valid=not any(row['regression'] for row in memory.values())
    passed=precision and semantic_valid and enclosure and point_valid and memory_valid
    return dict(schema=SCHEMA,status='native-argv-diagnostic-gates-passed' if passed else 'native-argv-diagnostic-gates-failed',
        planned_invocations=10,observed_invocations=10,unfiltered_precision_checks=checks,
        precision_valid=precision,failed_observations=sum(not row['valid'] for group in checks.values() for row in group),
        window_semantics=semantic,window_semantics_valid=semantic_valid,point_latency_gates=point,
        point_latency_gates_valid=point_valid,median_enclosures=enclosures,median_enclosure_valid=enclosure,
        enclosure_labels_to_arms=dict(baseline=ARMS[0],candidate=ARMS[1]),
        memory_gates=memory,memory_gates_valid=memory_valid,cpu_validity=cpu,
        root_allocation_bytes={arm:v[0] for arm,v in raw.items()},measured_payload={arm:v[1] for arm,v in raw.items()},
        configured_core_roles=summaries,direct_native_argv_only=True,detached_arctic_open_timing_included=False,
        historical_failures_cleared=False,full_six_boot_performance_acceptance=False,release_acceptance=False,
        attribution='One fresh candidate boot per arm, fixed order without replication; descriptive direct native argv mechanism evidence only. Session reads add declared cache overhead. Original failures remain failed.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--historical-log',type=Path,required=True)
    parser.add_argument('--native-log',type=Path,required=True)
    parser.add_argument('--identity',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    prior,backend,namespace=dependencies()
    composer=load(HERE/'compose-browser-route.py','trusted_route_composer_check')
    _,identity,parts=composer.components((HERE.parent/'performance/guest.py').read_text(),
        (PRIOR/'dual-observer.py').read_text(),(HERE/'browser-route-addon.py').read_text())
    evidence=json.loads(args.identity.read_text())
    composed=composer.compose((HERE.parent/'performance/guest.py').read_text(),
        (PRIOR/'dual-observer.py').read_text(),(HERE/'browser-route-addon.py').read_text())
    require(evidence.get('observer_source_sha256')==identity and evidence.get('components')==parts
        and evidence.get('frozen_probe_sha256')==hashlib.sha256(composed.encode()).hexdigest(),'Unexpected composed identity')
    runs={ARMS[0]:prior.read_run(args.historical_log,backend),ARMS[1]:prior.read_run(args.native_log,backend)}
    result=check(runs,prior,backend,namespace,identity,parts)
    require(not args.out.exists(),'Preserve previous diagnostic result')
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    return 0 if result['status']=='native-argv-diagnostic-gates-passed' else 1


if __name__=='__main__':raise SystemExit(main())
