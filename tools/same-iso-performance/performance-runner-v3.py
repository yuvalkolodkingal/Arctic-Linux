#!/usr/bin/env python3
"""Fixed-image performance recovery; no image build or publication path."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
COMMON_SHA = '0193c13bb9e17ac24bbf10681581262a2d3f2ec7512cab10a4ce92ac897d0633'
COMMON_FILE = HERE.parent/'same-iso-recovery/vm-only-recovery-v2.py'
if hashlib.sha256(COMMON_FILE.read_bytes()).hexdigest() != COMMON_SHA:
    raise RuntimeError('Frozen v2 common code differs before import')
spec = importlib.util.spec_from_file_location('frozen_performance_common', COMMON_FILE)
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

QUALIFICATION_BASE = 'ae55fbc9d48cec5ecc786cf61994ed986296d1bb'
BASELINE_BYTES = 2322073600
BASELINE_SHA = '054db5c43cae47fb60f8f43efc8e052b569aa1b14e8f15adcb15cdc48265182f'
BASELINE_ISO = 'Arctic-Linux-1.2-x86_64.iso'
PERFORMANCE_FILES = {
    'tools/performance/'+name for name in (
        'guest.py','compare.py','run-paired.py','compose-paired-probe.py','prepare-vm-tools.sh',
        'fixtures/v1.2-offline.toml')}
TEST_FILES = {'tools/tests/'+name for name in (
    'test_performance_compare.py','test_performance_harness.py','test_performance_observer.py',
    'test_performance_roles.py','test_performance_session.py','test_performance_recovery.py')}
BUNDLE_FILES = {'tools/same-iso-performance/'+name for name in (
    'performance-runner-v3.py','README-v3.md','frozen-v2-pins-v3.json','epiphany-ownership-evidence.json',
    'test_performance_runner_v3.py')}
EXECUTION_FILES = {'.github/workflows/iso.yml','tools/test-install.sh','tools/lib/container.sh',
                   'tools/lib/vmtest.py',*PERFORMANCE_FILES,*TEST_FILES,*BUNDLE_FILES}


def validate_ci(env):
    R.validate_ci(dict(env, RECOVERY_MODE='true'))
    R.require(env.get('PERFORMANCE_MODE') == 'true' and env.get('RECOVERY_MODE') == 'false',
              'Performance recovery must be selected alone')
    R.require(env['GITHUB_SHA'] != QUALIFICATION_BASE,
              'A distinct reviewed performance execution commit is mandatory')


def validate_performance_failure(run, jobs, artifact):
    original = R.validate_original(run, jobs, artifact)
    failed = [(job, step) for job in jobs
        if job.get('run_id') == R.ORIGINAL_RUN and job.get('head_sha') == R.SOURCE
        for step in job.get('steps', []) if step.get('name') == 'Paired KVM performance acceptance'
        and step.get('status') == 'completed' and step.get('conclusion') == 'failure']
    R.require(run.get('status') == 'completed' and run.get('conclusion') == 'failure'
              and len(failed) == 1, 'Exact original paired performance failure must be confirmed')
    job, step = failed[0]
    original.update(performance_job_id=job['id'], performance_step_number=step['number'],
                    performance_step_conclusion=step['conclusion'])
    return original


def verify_sources(args):
    execution = args.bundle.parents[1]
    for folder, wanted in ((args.source, R.SOURCE), (execution, os.environ['GITHUB_SHA'])):
        head = subprocess.check_output(['git','-C',str(folder),'rev-parse','HEAD'],text=True).strip()
        R.require(head == wanted, 'Source/execution commit differs: '+str(folder))
        R.require(not subprocess.check_output(['git','-C',str(folder),'status','--porcelain'],text=True).strip(),
                  'Source/execution checkout must be clean: '+str(folder))
    subprocess.run(['git','-C',str(execution),'merge-base','--is-ancestor',
                    QUALIFICATION_BASE,os.environ['GITHUB_SHA']],check=True,timeout=30)
    for relative, sha in R.SOURCE_PINS.items(): R.pinned_file(args.source/relative, sha)
    # Untouched execution harness remains the original image-source harness.
    for relative in ('tools/test-install.sh','tools/lib/container.sh','tools/lib/vmtest.py',
                     'tools/performance/prepare-vm-tools.sh'):
        R.pinned_file(execution/relative, R.SOURCE_PINS[relative])
    R.require(R.digest(execution/'tools/performance/fixtures/v1.2-offline.toml') ==
              'e6b9aa317521bdaaaf343629bc5de8b914b0a5f58387a0c9fe31754f17c0d20d',
              'Original immutable baseline install profile changed')
    manifest = json.loads((args.bundle/'execution-pins-v3.json').read_text())
    R.require(type(manifest.get('schema')) is int and manifest['schema'] == 3
              and manifest.get('mode') == 'same-iso-performance'
              and manifest.get('candidate_source') == R.SOURCE
              and manifest.get('qualification_base') == QUALIFICATION_BASE
              and set(manifest.get('files', {})) == EXECUTION_FILES,
              'Performance execution manifest identity/file set differs')
    for relative, sha in manifest['files'].items():
        R.require(not Path(relative).is_absolute() and '..' not in Path(relative).parts,
                  'Unsafe performance execution pin path')
        R.pinned_file(execution/relative, sha)
    frozen = json.loads((args.bundle/'frozen-v2-pins-v3.json').read_text())
    R.require(frozen['qualification_base'] == QUALIFICATION_BASE, 'Frozen common base differs')
    for relative, sha in frozen['files'].items(): R.pinned_file(execution/relative, sha)
    return manifest


def preflight(args):
    validate_ci(os.environ); verify_sources(args)
    R.require(not args.inputs.exists() and not args.evidence.exists(), 'Use fresh input/evidence paths')
    args.evidence.mkdir(parents=True)
    docker = R.require_docker()
    R.require(Path('/dev/kvm').is_char_device(), 'Native KVM mandatory; no host chmod/TCG fallback')
    R.require(shutil.disk_usage(args.evidence).free >= 40_000_000_000,
              'At least 40 GB free required for two installs and fresh overlays')
    run = R.api('actions/runs/'+str(R.ORIGINAL_RUN))
    pages = R.api('actions/runs/'+str(R.ORIGINAL_RUN)+'/jobs?filter=all&per_page=100',paginate=True)
    artifact = R.api('actions/artifacts/'+str(R.ARTIFACT_ID))
    original = validate_performance_failure(run,[job for page in pages for job in page['jobs']],artifact)
    R.write_json(args.evidence/'preflight.json', dict(original_result=original,
        candidate_iso_source=R.SOURCE,execution_checker_head=os.environ['GITHUB_SHA'],
        execution_manifest_sha256=R.digest(args.bundle/'execution-pins-v3.json'),
        artifact=dict(id=R.ARTIFACT_ID,archive_bytes=R.ARCHIVE_BYTES,archive_digest=R.ARCHIVE_DIGEST),
        baseline=dict(bytes=BASELINE_BYTES,sha256=BASELINE_SHA),docker_server_version=docker,
        release_acceptance=False))


def verify(args):
    validate_ci(os.environ); verify_sources(args)
    proof = json.loads((args.evidence/'preflight.json').read_text())
    R.require(proof['execution_checker_head'] == os.environ['GITHUB_SHA']
              and proof['candidate_iso_source'] == R.SOURCE
              and proof['execution_manifest_sha256'] == R.digest(args.bundle/'execution-pins-v3.json'),
              'Preflight belongs to another execution/source')
    proof['iso'] = R.verify_iso(args.inputs)
    R.write_json(args.evidence/'verified-input.json',proof)
    for relative in R.METADATA_PINS:
        target = args.evidence/'input-metadata'/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(args.inputs/relative,target)


def download_baseline(folder):
    R.require(not folder.exists(), 'Baseline destination must be unused')
    folder.mkdir()
    parts = [BASELINE_ISO+'.part00', BASELINE_ISO+'.part01']
    argv = ['gh','release','download','v1.2.0','--repo',R.REPOSITORY,'--dir',str(folder)]
    for name in parts: argv += ['--pattern',name]
    subprocess.run(argv,check=True,timeout=1200)
    destination = folder/BASELINE_ISO
    with destination.open('xb') as output:
        for name in parts:
            path = folder/name
            R.require(path.is_file() and not path.is_symlink(), 'Baseline release part absent/linked')
            with path.open('rb') as source: shutil.copyfileobj(source,output)
    R.require(destination.stat().st_size == BASELINE_BYTES and R.digest(destination) == BASELINE_SHA,
              'Original released baseline byte count/hash differs')
    for name in parts: (folder/name).unlink()
    return destination


def cleanup_task_containers(measurement, output):
    # Emergency cleanup only after a hung controller was killed. A verified
    # current-run state and exact UUID names bind this to its own containers.
    state_path = measurement/'status.json'
    R.require(state_path.is_file() and not state_path.is_symlink(), 'No owned task state for emergency cleanup')
    state = json.loads(state_path.read_text())
    task = state.get('task_id','')
    R.require(re.fullmatch('[0-9a-f]{32}',task) and state.get('observer_sha256') ==
              R.digest(measurement/'frozen-observer.py')
              and state.get('images',{}).get('candidate',{}).get('sha256') == R.ISO_SHA256
              and state.get('images',{}).get('baseline',{}).get('sha256') == BASELINE_SHA,
              'Emergency cleanup task/source identity differs')
    prefix = 'arctic-paired-'+task+'-'
    names = subprocess.check_output(['docker','ps','--all','--format','{{.Names}}',
        '--filter','name=^/'+prefix],text=True,timeout=30).splitlines()
    R.require(all(re.fullmatch(re.escape(prefix)+'[0-9a-f]{8}',name) for name in names),
              'Refusing any container outside the exact current task namespace')
    for name in names:
        subprocess.run(['docker','rm','--force',name],stdout=output,stderr=output,check=True,timeout=30)


def execute_controller(argv, log, cwd, env, seconds=180*60, measurement=None):
    # No synthetic Docker container: the reviewed controller owns every actual
    # per-stage container. Allow its SIGTERM handler to reap/clean those resources.
    with log.open('w') as output:
        process = subprocess.Popen(argv,cwd=cwd,env=env,stdout=output,
                                   stderr=subprocess.STDOUT,start_new_session=True)
        try:
            code = process.wait(timeout=seconds)
        except BaseException:
            process.send_signal(signal.SIGTERM)
            try: process.wait(timeout=100)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=15)
                R.require(measurement is not None, 'Hung controller has no owned cleanup scope')
                cleanup_task_containers(measurement,output)
            raise
    R.require(code == 0, 'Paired controller failed: exit='+str(code))


def run(args):
    # Hash the actual image again before downloading the VM baseline or starting any VM.
    verify(args); R.require_docker()
    R.require(Path('/dev/kvm').is_char_device(), 'Native KVM disappeared')
    execution = args.bundle.parents[1]
    baseline = download_baseline(args.evidence.parent/'baseline-input')
    measurement = args.evidence/'paired'
    R.require(not measurement.exists(), 'Previous paired measurements must remain intact')
    argv = [sys.executable,str(execution/'tools/performance/run-paired.py'),
        '--baseline',str(baseline),'--candidate',str(args.inputs/'iso'/R.ISO),
        '--candidate-source-root',str(args.source),'--out',str(measurement)]
    env = dict(os.environ,CONTAINER_ENGINE='docker')
    # The 180 min controller cap is inside a 230 min job, leaving time for fixed
    # artifact/baseline downloads, cleanup, and evidence upload. Outer job kills
    # can still interrupt finalization and never count as completed acceptance.
    execute_controller(argv,args.evidence/'paired-controller.log',execution,env,measurement=measurement)
    status = json.loads((measurement/'status.json').read_text())
    comparison = json.loads((measurement/'comparison.json').read_text())
    R.require(status['phase'] == 'complete_regression_gate_passed'
              and len(status['runs']) == 6 and comparison['status'] == 'regression_gate_passed',
              'Incomplete or failed paired precision/regression qualification')
    R.write_json(args.evidence/'result.json',dict(status='paired-gates-passed',
                 release_acceptance=False,candidate_iso_source=R.SOURCE,
                 execution_checker_head=os.environ['GITHUB_SHA']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('preflight','verify','run'))
    for name in ('source','bundle','inputs','evidence'):
        parser.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args()
    for name in ('source','bundle','inputs','evidence'): setattr(args,name,getattr(args,name).resolve())
    try: globals()[args.action](args)
    except Exception as error:
        if args.evidence.is_dir():
            R.write_json(args.evidence/('blocked-'+args.action+'.json'),
                         dict(phase=args.action,error=str(error),release_acceptance=False))
        raise


if __name__ == '__main__': main()
