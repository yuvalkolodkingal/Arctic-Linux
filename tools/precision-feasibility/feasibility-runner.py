#!/usr/bin/env python3
"""Fixed-artifact two-boot diagnostic; no ISO build, release, or six-boot path."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parent
V3_FILE=HERE.parent/'same-iso-performance/performance-runner-v3.py'
V3_SHA='a4ea07951870cc01a66616e1d088382baa0443aa608baae9e81c49d816fac3a7'
if hashlib.sha256(V3_FILE.read_bytes()).hexdigest()!=V3_SHA:
    raise RuntimeError('Frozen performance dependency differs before import')
spec=importlib.util.spec_from_file_location('unchanged_performance_dependency',V3_FILE)
V3=importlib.util.module_from_spec(spec);spec.loader.exec_module(V3)
R=V3.R
EXECUTION_BASE='adb4e1e693badf0d072215bc4f50e7bea159c769'
PRIOR_HEAD='d7414d4c170feb9302f762e1812c9dca71a7af54'
PRIOR_RUN=37534194076
PRIOR_JOB=112510880126
PRIOR_ARTIFACT=11451121982
PRIOR_ZIP_BYTES=23453736
PRIOR_ZIP_SHA='8997607f89fe6adde1bd797afa3e1ed87ae541c9252649713322611e10224ed8'
DEPLOYED_NAMES={
    'dual-observer.py','compose-feasibility.py','feasibility-check.py','run-feasibility.py',
    'feasibility-runner.py','test_dual_observer.py','test_feasibility_check.py',
    'test_feasibility_runner.py','README.md','runtime-pins.json','provenance.json'}
EXECUTION_FILES={'.github/workflows/iso.yml',*('tools/precision-feasibility/'+name for name in DEPLOYED_NAMES)}
ALLOWED_CHANGES=EXECUTION_FILES|{'tools/precision-feasibility/execution-pins.json'}


def validate_ci(env):
    R.validate_ci(dict(env,RECOVERY_MODE='true'))
    R.require(env.get('PRECISION_FEASIBILITY_MODE')=='true'
        and env.get('RECOVERY_MODE')=='false' and env.get('PERFORMANCE_MODE')=='false'
        and env.get('NIX_ACCEPTANCE')=='false' and env.get('PERFORMANCE_ACCEPTANCE')=='false',
        'Select only the dedicated one-pair feasibility mode')
    R.require(env['GITHUB_SHA'] not in (EXECUTION_BASE,PRIOR_HEAD),
        'A separate reviewed feasibility execution commit is mandatory')


def validate_prior(run,jobs,artifact):
    R.require(run.get('id')==PRIOR_RUN and run.get('head_sha')==PRIOR_HEAD
        and run.get('status')=='completed' and run.get('conclusion')=='failure' and run.get('run_attempt')==1,
        'Exact preserved six-boot failure must be terminal')
    selected=[j for j in jobs if j.get('id')==PRIOR_JOB and j.get('run_id')==PRIOR_RUN and j.get('head_sha')==PRIOR_HEAD]
    R.require(len(selected)==1 and selected[0].get('status')=='completed' and selected[0].get('conclusion')=='failure'
        and any(s.get('name')=='Six fresh paired boots of unchanged images' and s.get('status')=='completed'
                and s.get('conclusion')=='failure' for s in selected[0].get('steps',[])),
        'Preserved exact six-boot job/step failure is missing')
    R.require(artifact.get('id')==PRIOR_ARTIFACT and artifact.get('size_in_bytes')==PRIOR_ZIP_BYTES
        and artifact.get('digest')=='sha256:'+PRIOR_ZIP_SHA and artifact.get('expired') is False
        and artifact.get('workflow_run',{}).get('id')==PRIOR_RUN
        and artifact['workflow_run'].get('head_sha')==PRIOR_HEAD,
        'Preserved precision-failure evidence artifact identity differs')
    return dict(run=PRIOR_RUN,head=PRIOR_HEAD,job=PRIOR_JOB,artifact=PRIOR_ARTIFACT,
        artifact_bytes=PRIOR_ZIP_BYTES,artifact_sha256=PRIOR_ZIP_SHA,
        scope='Historical result remains failed; metadata verification is no performance acceptance')


def verify_sources(args):
    execution=args.bundle.parents[1]
    R.require(args.bundle==execution/'tools/precision-feasibility','Unexpected deployment bundle path')
    for folder,wanted in ((args.source,R.SOURCE),(execution,os.environ['GITHUB_SHA'])):
        R.require(subprocess.check_output(['git','-C',str(folder),'rev-parse','HEAD'],text=True).strip()==wanted,
            'Source/execution commit differs')
        R.require(not subprocess.check_output(['git','-C',str(folder),'status','--porcelain'],text=True).strip(),
            'Source/execution checkout must be clean')
    subprocess.run(['git','-C',str(execution),'merge-base','--is-ancestor',EXECUTION_BASE,os.environ['GITHUB_SHA']],
        check=True,timeout=30)
    changed=set(subprocess.check_output(['git','-C',str(execution),'diff','--name-only',EXECUTION_BASE,os.environ['GITHUB_SHA']],text=True).splitlines())
    R.require(changed and changed<=ALLOWED_CHANGES,'Unexpected runtime/product/source change outside reviewed diagnostic')
    for relative,sha in R.SOURCE_PINS.items():R.pinned_file(args.source/relative,sha)
    runtime=json.loads((args.bundle/'runtime-pins.json').read_text())
    R.require(runtime.get('execution_base')==EXECUTION_BASE and runtime.get('prior_runtime_head')==PRIOR_HEAD,
        'Frozen execution/runtime provenance differs')
    frozen=json.loads(subprocess.check_output(['git','-C',str(execution),'show',
        EXECUTION_BASE+':tools/same-iso-performance/frozen-v2-pins-v3.json'],text=True))
    required=(V3.EXECUTION_FILES-{'.github/workflows/iso.yml'})|set(frozen['files'])|{'tools/same-iso-performance/execution-pins-v3.json'}
    R.require(set(runtime.get('files',{}))==required,'Frozen runtime pin set differs')
    for relative,sha in runtime['files'].items():
        R.require(not Path(relative).is_absolute() and '..' not in Path(relative).parts,'Unsafe runtime pin')
        expected=hashlib.sha256(subprocess.check_output(['git','-C',str(execution),'show',EXECUTION_BASE+':'+relative])).hexdigest()
        R.require(sha==expected,'Runtime pin is not the exact declared base Git blob')
        R.pinned_file(execution/relative,sha)
    manifest=json.loads((args.bundle/'execution-pins.json').read_text())
    R.require(type(manifest.get('schema')) is int and manifest['schema']==1
        and manifest.get('mode')=='same-iso-precision-feasibility' and manifest.get('candidate_source')==R.SOURCE
        and manifest.get('execution_base')==EXECUTION_BASE and set(manifest.get('files',{}))==EXECUTION_FILES,
        'Diagnostic execution manifest identity/file set differs')
    for relative,sha in manifest['files'].items():
        R.require(not Path(relative).is_absolute() and '..' not in Path(relative).parts,'Unsafe execution pin')
        R.pinned_file(execution/relative,sha)
    return manifest


def preflight(args):
    validate_ci(os.environ);verify_sources(args)
    R.require(not args.inputs.exists() and not args.evidence.exists(),'Use unused diagnostic input/evidence paths')
    args.evidence.mkdir(parents=True)
    docker=R.require_docker()
    R.require(Path('/dev/kvm').is_char_device(),'Native KVM mandatory; no host chmod/TCG fallback')
    R.require(shutil.disk_usage(args.evidence).free>=40_000_000_000,'At least40GB free required; space gate unchanged')
    run=R.api('actions/runs/'+str(R.ORIGINAL_RUN))
    pages=R.api('actions/runs/'+str(R.ORIGINAL_RUN)+'/jobs?filter=all&per_page=100',paginate=True)
    artifact=R.api('actions/artifacts/'+str(R.ARTIFACT_ID))
    original=V3.validate_performance_failure(run,[job for page in pages for job in page['jobs']],artifact)
    prior=R.api('actions/runs/'+str(PRIOR_RUN))
    pages=R.api('actions/runs/'+str(PRIOR_RUN)+'/jobs?filter=all&per_page=100',paginate=True)
    prior_artifact=R.api('actions/artifacts/'+str(PRIOR_ARTIFACT))
    preserved=validate_prior(prior,[job for page in pages for job in page['jobs']],prior_artifact)
    R.write_json(args.evidence/'preflight.json',dict(mode='one-pair-precision-feasibility',original_result=original,
        preserved_six_boot_failure=preserved,candidate_iso_source=R.SOURCE,execution_checker_head=os.environ['GITHUB_SHA'],
        execution_manifest_sha256=R.digest(args.bundle/'execution-pins.json'),
        artifact=dict(id=R.ARTIFACT_ID,archive_bytes=R.ARCHIVE_BYTES,archive_digest=R.ARCHIVE_DIGEST),
        baseline=dict(bytes=V3.BASELINE_BYTES,sha256=V3.BASELINE_SHA),docker_server_version=docker,
        planned_fresh_boots=2,planned_unfiltered_startup_observations=24,
        release_acceptance=False,full_six_boot_performance_acceptance=False))


def verify(args):
    validate_ci(os.environ);verify_sources(args)
    proof=json.loads((args.evidence/'preflight.json').read_text())
    R.require(proof.get('execution_checker_head')==os.environ['GITHUB_SHA'] and proof.get('candidate_iso_source')==R.SOURCE
        and proof.get('execution_manifest_sha256')==R.digest(args.bundle/'execution-pins.json')
        and proof.get('mode')=='one-pair-precision-feasibility','Preflight belongs to another source/mode/head')
    proof['iso']=R.verify_iso(args.inputs)
    R.write_json(args.evidence/'verified-input.json',proof)
    for relative in R.METADATA_PINS:
        target=args.evidence/'input-metadata'/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(args.inputs/relative,target)


def run(args):
    verify(args);R.require_docker()
    R.require(Path('/dev/kvm').is_char_device(),'Native KVM disappeared')
    execution=args.bundle.parents[1]
    baseline=V3.download_baseline(args.evidence.parent/'baseline-input')
    measurement=args.evidence/'feasibility'
    R.require(not measurement.exists(),'Previous results must remain untouched')
    argv=[sys.executable,str(args.bundle/'run-feasibility.py'),'--baseline',str(baseline),
        '--candidate',str(args.inputs/'iso'/R.ISO),'--candidate-source-root',str(args.source),'--out',str(measurement)]
    V3.execute_controller(argv,args.evidence/'feasibility-controller.log',execution,
        dict(os.environ,CONTAINER_ENGINE='docker'),seconds=150*60,measurement=measurement)
    state=json.loads((measurement/'status.json').read_text());result=json.loads((measurement/'feasibility.json').read_text())
    R.require(state.get('mode')=='precision-feasibility-one-pair' and state.get('phase')=='complete_feasibility_gates_passed'
        and state.get('planned_boot_order')==[dict(image='baseline',boot=1),dict(image='candidate',boot=1)]
        and [(r.get('image'),r.get('boot'),r.get('harness_exit')) for r in state.get('runs',[])]==[('baseline',1,0),('candidate',1,0)]
        and all(type(r.get('boot')) is int and type(r.get('harness_exit')) is int for r in state.get('runs',[]))
        and result.get('status')=='feasibility-gates-passed' and result.get('total_observations')==24
        and type(result.get('total_observations')) is int and type(result.get('failed_observations')) is int
        and result.get('failed_observations')==0 and result.get('individual_precision_valid') is True
        and result.get('median_enclosure_valid') is True and result.get('memory_gate_valid') is True
        and result.get('point_latency_gates_valid') is True
        and set(result.get('checks',{}))=={'baseline','candidate'}
        and all(len(group)==12 and all(row.get('valid') is True for row in group) for group in result['checks'].values())
        and result.get('full_six_boot_performance_acceptance') is False
        and result.get('release_acceptance') is False,'Incomplete or failed diagnostic gates')
    R.write_json(args.evidence/'result.json',dict(status='observer-feasibility-gates-passed',
        candidate_iso_source=R.SOURCE,execution_checker_head=os.environ['GITHUB_SHA'],
        release_acceptance=False,full_six_boot_performance_acceptance=False,requires_new_review_before_any_full_comparison=True))


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
