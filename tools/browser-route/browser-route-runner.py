#!/usr/bin/env python3
"""Fixed-ISO native argv mechanism check; no product change or full qualification."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import re
import signal
import uuid

HERE=Path(__file__).resolve().parent
DEPENDENCY=HERE.parent/'same-iso-performance/performance-runner-v3.py'
if hashlib.sha256(DEPENDENCY.read_bytes()).hexdigest()!='a4ea07951870cc01a66616e1d088382baa0443aa608baae9e81c49d816fac3a7':
    raise RuntimeError('Pinned execution/cleanup dependency differs before import')
spec=importlib.util.spec_from_file_location('frozen_browser_route_dependency',DEPENDENCY)
V3=importlib.util.module_from_spec(spec);spec.loader.exec_module(V3)
R=V3.R
BASE='d0a69f881b38eeead7c9131e4dacaded4440b058'
RUN=37563885487
JOB=112607099604
ARTIFACT=11460610239
ZIP_BYTES=6863384
ZIP_SHA='7d6ceb69f11575d9b00be23af54567b4a8614a9380a50fdc42d5c9a8562d742b'
ARMS=('historical-new-window','native-product-argv')
NAMES={'browser-route-addon.py','compose-browser-route.py','check-browser-route.py',
    'run-browser-route.py','browser-route-runner.py','test_browser_route.py','README.md',
    'frozen-runtime-pins.json','historical-evidence.json'}
FILES={'.github/workflows/iso.yml',*('tools/browser-route/'+name for name in NAMES)}
ALLOWED=FILES|{'tools/browser-route/execution-pins.json'}
RUNTIME_FILES = {'tools/precision-feasibility/dual-observer.py', 'tools/tests/test_performance_harness.py', 'tools/lib/container.sh', 'tools/same-iso-performance/epiphany-ownership-evidence.json', 'tools/precision-feasibility/provenance.json', 'tools/test-install.sh', 'tools/same-iso-recovery/collector-command-v2.txt', 'tools/same-iso-recovery/guest-check-dnf-v1.py', 'tools/same-iso-recovery/qualification-scope.json', 'tools/lib/vmtest.py', 'tools/tests/test_performance_roles.py', 'tools/precision-feasibility/README.md', 'tools/precision-feasibility/test_feasibility_check.py', 'tools/precision-feasibility/test_dual_observer.py', 'tools/performance/prepare-vm-tools.sh', 'tools/precision-feasibility/test_feasibility_runner.py', 'tools/same-iso-recovery/registered-iso-recovery-v2.yml', 'tools/precision-feasibility/feasibility-runner.py', 'tools/performance/guest.py', 'tools/performance/run-paired.py', 'tools/same-iso-performance/execution-pins-v3.json', 'tools/same-iso-recovery/review-ready-v2.json', 'tools/precision-feasibility/compose-feasibility.py', 'tools/tests/test_performance_observer.py', 'tools/same-iso-performance/frozen-v2-pins-v3.json', 'tools/same-iso-performance/README-v3.md', 'tools/same-iso-recovery/test-iso-collector-v2.patch', 'tools/same-iso-performance/performance-runner-v3.py', 'tools/same-iso-recovery/test_vm_only_v2.py', 'tools/same-iso-recovery/independent-review-v1.json', 'tools/tests/test_performance_compare.py', 'tools/same-iso-recovery/README-v1.md', 'tools/same-iso-recovery/README-v2.md', 'tools/same-iso-recovery/guest-check-offline-v1.py', 'tools/same-iso-recovery/review-ready-v1.json', 'tools/tests/test_performance_recovery.py', 'tools/performance/compose-paired-probe.py', 'tools/same-iso-performance/test_performance_runner_v3.py', 'tools/precision-feasibility/feasibility-check.py', 'tools/tests/test_performance_session.py', 'tools/precision-feasibility/run-feasibility.py', 'tools/performance/fixtures/v1.2-offline.toml', 'tools/same-iso-recovery/boot-evidence-v2.py', 'tools/same-iso-recovery/vm-only-recovery-v2.py', 'tools/same-iso-recovery/execution-pins-v2.json', 'tools/same-iso-recovery/v2-controls.log', 'tools/precision-feasibility/execution-pins.json', 'tools/precision-feasibility/runtime-pins.json', 'tools/same-iso-recovery/independent-review-v2.json', 'tools/performance/compare.py'}


def validate_ci(env):
    R.validate_ci(dict(env,RECOVERY_MODE='true'))
    R.require(env.get('BROWSER_ROUTE_MODE')=='true'
        and all(env.get(k)=='false' for k in ('RECOVERY_MODE','PERFORMANCE_MODE','PRECISION_FEASIBILITY_MODE',
                                             'NIX_ACCEPTANCE','PERFORMANCE_ACCEPTANCE')),
        'Select only the finite browser native argv mode')
    R.require(env.get('GITHUB_SHA')!=BASE,'A new clean reviewed execution head is required')


def verify_sources(args):
    execution=args.bundle.parents[1]
    R.require(args.bundle==execution/'tools/browser-route','Unexpected diagnostic bundle path')
    for folder,head in ((args.source,R.SOURCE),(execution,os.environ['GITHUB_SHA'])):
        R.require(subprocess.check_output(['git','-C',str(folder),'rev-parse','HEAD'],text=True).strip()==head,
            'Exact source/execution head differs')
        R.require(not subprocess.check_output(['git','-C',str(folder),'status','--porcelain'],text=True).strip(),
            'Use clean source/execution checkouts')
    subprocess.run(['git','-C',str(execution),'merge-base','--is-ancestor',BASE,os.environ['GITHUB_SHA']],check=True,timeout=30)
    changed=set(subprocess.check_output(['git','-C',str(execution),'diff','--name-only',BASE,os.environ['GITHUB_SHA']],text=True).splitlines())
    R.require(changed and changed<=ALLOWED,'Unexpected product/runtime/test change outside this new diagnostic')
    for relative,sha in R.SOURCE_PINS.items():R.pinned_file(args.source/relative,sha)
    frozen=json.loads((args.bundle/'frozen-runtime-pins.json').read_text())
    R.require(frozen.get('execution_base')==BASE and set(frozen.get('files',{}))==RUNTIME_FILES,'Prior runtime pin set differs')
    for relative,sha in frozen['files'].items():
        expected=hashlib.sha256(subprocess.check_output(['git','-C',str(execution),'show',BASE+':'+relative])).hexdigest()
        R.require(sha==expected,'Frozen runtime pin differs from the declared Git blob')
        R.pinned_file(execution/relative,sha)
    manifest=json.loads((args.bundle/'execution-pins.json').read_text())
    R.require(type(manifest.get('schema')) is int and manifest['schema']==1
        and manifest.get('mode')=='browser-native-argv-diagnostic' and manifest.get('candidate_source')==R.SOURCE
        and manifest.get('execution_base')==BASE and set(manifest.get('files',{}))==FILES,
        'Exact diagnostic execution manifest differs')
    for relative,sha in manifest['files'].items():R.pinned_file(execution/relative,sha)
    return manifest


def validate_prior(run,jobs,artifact):
    R.require(type(run.get('id')) is int and run['id']==RUN and run.get('head_sha')==BASE
        and run.get('status')=='completed' and run.get('conclusion')=='failure' and type(run.get('run_attempt')) is int
        and run['run_attempt']==1,'Exact completed prior diagnostic failure must remain preserved')
    selected=[j for j in jobs if j.get('id')==JOB and j.get('run_id')==RUN and j.get('head_sha')==BASE]
    R.require(len(selected)==1 and selected[0].get('status')=='completed' and selected[0].get('conclusion')=='failure'
        and any(s.get('name')=='One fresh boot per fixed image with24 unfiltered startup observations'
                and s.get('conclusion')=='failure' and s.get('status')=='completed' for s in selected[0].get('steps',[])),
        'Exact prior failed job/step differs')
    R.require(artifact.get('id')==ARTIFACT and artifact.get('size_in_bytes')==ZIP_BYTES
        and artifact.get('digest')=='sha256:'+ZIP_SHA and artifact.get('expired') is False
        and artifact.get('workflow_run',{}).get('id')==RUN and artifact['workflow_run'].get('head_sha')==BASE,
        'Exact preserved diagnostic artifact identity differs')
    return dict(run=RUN,head=BASE,job=JOB,artifact=ARTIFACT,artifact_bytes=ZIP_BYTES,artifact_sha256=ZIP_SHA,
        original_precision_failures='8/24',original_warm_browser_failed_gates=['first-after-preconditioning','subsequent'],
        scope='Preserved failed diagnostic; metadata verifies identity only, not cause')


def preflight(args):
    validate_ci(os.environ);verify_sources(args)
    R.require(not args.inputs.exists() and not args.evidence.exists(),'Use new input/evidence paths')
    args.evidence.mkdir(parents=True)
    docker=R.require_docker()
    R.require(Path('/dev/kvm').is_char_device(),'Native KVM required; no permission change or TCG fallback')
    R.require(shutil.disk_usage(args.evidence).free>=40_000_000_000,'Keep the40GB hosted-runner free-space gate')
    original=R.api('actions/runs/'+str(R.ORIGINAL_RUN))
    pages=R.api('actions/runs/'+str(R.ORIGINAL_RUN)+'/jobs?filter=all&per_page=100',paginate=True)
    iso_artifact=R.api('actions/artifacts/'+str(R.ARTIFACT_ID))
    preserved_original=V3.validate_performance_failure(original,[j for p in pages for j in p['jobs']],iso_artifact)
    prior=R.api('actions/runs/'+str(RUN))
    pages=R.api('actions/runs/'+str(RUN)+'/jobs?filter=all&per_page=100',paginate=True)
    prior_artifact=R.api('actions/artifacts/'+str(ARTIFACT))
    preserved=validate_prior(prior,[j for p in pages for j in p['jobs']],prior_artifact)
    R.write_json(args.evidence/'preflight.json',dict(mode='browser-native-argv-diagnostic',
        original_result=preserved_original,preserved_diagnostic_failure=preserved,
        candidate_iso_source=R.SOURCE,execution_checker_head=os.environ['GITHUB_SHA'],
        execution_manifest_sha256=R.digest(args.bundle/'execution-pins.json'),docker_server_version=docker,
        artifact=dict(id=R.ARTIFACT_ID,archive_bytes=R.ARCHIVE_BYTES,archive_digest=R.ARCHIVE_DIGEST),
        planned_fresh_installs=2,planned_fresh_boots=2,planned_unfiltered_invocations=10,
        direct_native_argv_only=True,detached_arctic_open_timing_included=False,
        release_acceptance=False,full_six_boot_performance_acceptance=False))


def verify(args):
    validate_ci(os.environ);verify_sources(args)
    proof=json.loads((args.evidence/'preflight.json').read_text())
    R.require(proof.get('mode')=='browser-native-argv-diagnostic'
        and proof.get('candidate_iso_source')==R.SOURCE and proof.get('execution_checker_head')==os.environ['GITHUB_SHA']
        and proof.get('execution_manifest_sha256')==R.digest(args.bundle/'execution-pins.json'),
        'Preflight belongs to another head/source/mode')
    proof['iso']=R.verify_iso(args.inputs)
    R.write_json(args.evidence/'verified-input.json',proof)
    for relative in R.METADATA_PINS:
        target=args.evidence/'input-metadata'/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(args.inputs/relative,target)


def controller_ownership(args):
    """Caller-owned nonce: no historical baseline or arbitrary cleanup scope."""
    path=args.bundle/'compose-browser-route.py'
    spec=importlib.util.spec_from_file_location('browser_route_owned_composer',path)
    composer=importlib.util.module_from_spec(spec);spec.loader.exec_module(composer)
    execution=args.bundle.parents[1]
    probe=composer.compose((execution/'tools/performance/guest.py').read_text(),
        (execution/'tools/precision-feasibility/dual-observer.py').read_text(),
        (args.bundle/'browser-route-addon.py').read_text())
    return dict(schema='arctic-browser-route-task-v2',mode='browser-native-argv-diagnostic',
        task_id=uuid.uuid4().hex,candidate_source=R.SOURCE,execution_checker_head=os.environ['GITHUB_SHA'],
        github_run_id=os.environ['GITHUB_RUN_ID'],github_run_attempt=os.environ['GITHUB_RUN_ATTEMPT'],
        observer_sha256=hashlib.sha256(probe.encode()).hexdigest(),
        candidate_iso_path=str((args.inputs/'iso'/R.ISO).resolve()),
        candidate_iso_bytes=R.ISO_BYTES,candidate_iso_sha256=R.ISO_SHA256,arms=list(ARMS))


def cleanup_task_containers(measurement,output,ownership):
    # Only after this exact controller is killed. Legacy V3 remains unchanged.
    # The immutable caller nonce/source/run binding is never read back from status.
    state_path=measurement/'status.json'
    R.require(state_path.is_file() and not state_path.is_symlink()
        and 0<state_path.stat().st_size<=128*1024,'No bounded owned task state for emergency cleanup')
    state=json.loads(state_path.read_text())
    task=ownership.get('task_id','')
    R.require(re.fullmatch('[0-9a-f]{32}',task) and ownership.get('schema')=='arctic-browser-route-task-v2'
        and ownership.get('mode')=='browser-native-argv-diagnostic'
        and ownership.get('candidate_source')==R.SOURCE and ownership.get('arms')==list(ARMS)
        and ownership.get('execution_checker_head')==os.environ['GITHUB_SHA']
        and ownership.get('github_run_id')==os.environ['GITHUB_RUN_ID']
        and ownership.get('github_run_attempt')==os.environ['GITHUB_RUN_ATTEMPT']
        and re.fullmatch('[0-9a-f]{40}',ownership['execution_checker_head'])
        and re.fullmatch('[1-9][0-9]*',ownership['github_run_id'])
        and re.fullmatch('[1-9][0-9]*',ownership['github_run_attempt'])
        and type(ownership.get('candidate_iso_bytes')) is int and ownership['candidate_iso_bytes']==R.ISO_BYTES
        and ownership.get('candidate_iso_sha256')==R.ISO_SHA256
        and state.get('ownership')==ownership and state.get('task_id')==task
        and state.get('mode')=='browser-native-argv-diagnostic'
        and state.get('candidate_image_source',{}).get('commit')==R.SOURCE
        and state.get('execution_checker_commit')==ownership['execution_checker_head'],
        'Emergency browser task/source/run identity differs')
    probe=measurement/'frozen-observer.py'
    R.require(probe.is_file() and not probe.is_symlink() and probe.stat().st_size<=2*1024*1024
        and state.get('observer_sha256')==ownership.get('observer_sha256')==R.digest(probe),
        'Emergency composed observer identity differs')
    images=state.get('images',{})
    R.require(set(images)==set(ARMS) and all(
        images[arm].get('path')==ownership['candidate_iso_path']
        and type(images[arm].get('bytes')) is int and images[arm]['bytes']==R.ISO_BYTES
        and images[arm].get('sha256')==R.ISO_SHA256 for arm in ARMS),
        'Emergency actual same-candidate arm identity differs')
    prefix='arctic-paired-'+task+'-'
    registered=state.get('owned_container_names')
    R.require(isinstance(registered,list) and 1<=len(registered)<=5
        and all(isinstance(name,str) and re.fullmatch(re.escape(prefix)+'[0-9a-f]{8}',name) for name in registered)
        and len(set(registered))==len(registered),'Emergency owned container registry differs')
    names=subprocess.check_output(['docker','ps','--all','--format','{{.Names}}',
        '--filter','name=^/'+prefix],text=True,timeout=30).splitlines()
    R.require(len(names)<=5 and len(names)==len(set(names)) and all(name in registered for name in names),
        'Refusing any container outside the exact current registered task')
    identities=[]
    for name in names:
        raw=subprocess.check_output(['docker','inspect','--type','container','--format','{{.Id}} {{.Name}}',name],
            text=True,timeout=30).strip()
        match=re.fullmatch('([0-9a-f]{64}) /'+re.escape(name),raw)
        R.require(match is not None,'Owned container name/immutable identity differs')
        identities.append(match[1])
    R.require(len(set(identities))==len(identities),'Duplicate owned container identity')
    for identity in identities:
        subprocess.run(['docker','rm','--force',identity],stdout=output,stderr=output,check=True,timeout=30)


def execute_controller(argv,log,cwd,env,ownership,seconds=150*60,measurement=None):
    # Same frozen controller deadline/grace; only emergency scope is adapted.
    with log.open('w') as output:
        process=subprocess.Popen(argv,cwd=cwd,env=env,stdout=output,
                                 stderr=subprocess.STDOUT,start_new_session=True)
        try:
            code=process.wait(timeout=seconds)
        except BaseException as primary:
            try:
                process.send_signal(signal.SIGTERM)
                try:process.wait(timeout=100)
                except subprocess.TimeoutExpired:
                    process.kill();process.wait(timeout=15)
                    R.require(measurement is not None,'Hung controller has no owned cleanup scope')
                    cleanup_task_containers(measurement,output,ownership)
            except BaseException as cleanup_error:
                primary.add_note('Owned browser emergency cleanup failed: '+repr(cleanup_error))
            raise
    R.require(code==0,'Browser diagnostic controller failed: exit='+str(code))


def run(args):
    verify(args);R.require_docker()
    R.require(Path('/dev/kvm').is_char_device(),'Native KVM disappeared')
    measurement=args.evidence/'browser-route'
    R.require(not measurement.exists(),'Preserve previous output')
    execution=args.bundle.parents[1]
    ownership=controller_ownership(args)
    R.write_json(args.evidence/'controller-ownership.json',ownership)
    execute_controller([sys.executable,str(args.bundle/'run-browser-route.py'),
        '--candidate',str(args.inputs/'iso'/R.ISO),'--candidate-source-root',str(args.source),'--out',str(measurement)],
        args.evidence/'browser-route-controller.log',execution,dict(os.environ,CONTAINER_ENGINE='docker',
            ARCTIC_BROWSER_ROUTE_OWNERSHIP=json.dumps(ownership,sort_keys=True)),ownership,
        seconds=150*60,measurement=measurement)
    state=json.loads((measurement/'status.json').read_text())
    result=json.loads((measurement/'browser-route.json').read_text())
    R.require(state.get('mode')=='browser-native-argv-diagnostic' and state.get('phase')=='complete_browser_route_gates_passed'
        and state.get('planned_boot_order')==[dict(image=arm,boot=1) for arm in ARMS]
        and [(r.get('image'),r.get('boot'),r.get('harness_exit')) for r in state.get('runs',[])]==[(arm,1,0) for arm in ARMS]
        and all(type(r.get('boot')) is int and type(r.get('harness_exit')) is int for r in state.get('runs',[]))
        and not state.get('cleanup_errors') and result.get('status')=='native-argv-diagnostic-gates-passed'
        and result.get('observed_invocations')==10 and type(result['observed_invocations']) is int
        and result.get('failed_observations')==0 and type(result['failed_observations']) is int
        and all(result.get(k) is True for k in ('precision_valid','window_semantics_valid','point_latency_gates_valid',
                                                'median_enclosure_valid','memory_gates_valid'))
        and result.get('direct_native_argv_only') is True and result.get('detached_arctic_open_timing_included') is False
        and result.get('historical_failures_cleared') is False
        and result.get('full_six_boot_performance_acceptance') is False and result.get('release_acceptance') is False,
        'Incomplete/failed native argv diagnostic; no result can clear prior failures')
    R.write_json(args.evidence/'result.json',dict(status='native-argv-mechanism-diagnostic-gates-passed',
        candidate_iso_source=R.SOURCE,execution_checker_head=os.environ['GITHUB_SHA'],
        direct_native_argv_only=True,detached_arctic_open_timing_included=False,
        historical_failures_cleared=False,release_acceptance=False,full_six_boot_performance_acceptance=False))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('preflight','verify','run'))
    for name in ('source','bundle','inputs','evidence'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    for name in ('source','bundle','inputs','evidence'):setattr(args,name,getattr(args,name).resolve())
    try:globals()[args.action](args)
    except Exception as error:
        if args.evidence.is_dir():R.write_json(args.evidence/('blocked-'+args.action+'.json'),dict(
            phase=args.action,error=str(error),release_acceptance=False,full_six_boot_performance_acceptance=False))
        raise


if __name__=='__main__':main()
