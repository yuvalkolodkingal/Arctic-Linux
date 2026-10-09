#!/usr/bin/env python3
"""Execute the recovered limited native smoke against an explicitly pinned ISO.

The prepared manifest is disabled until a rebuilt image has been identified and
this execution code has passed independent review. Never dispatches or publishes.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import uuid

import evidence as E

HERE = Path(__file__).resolve().parent
CHECKERS = E.CHECKERS
LAUNCHER_SHA = E.LAUNCHER_SHA

class R(E.R):
    @staticmethod
    def pinned_file(path, expected):
        path = Path(path)
        R.require(path.is_file() and not path.is_symlink() and R.digest(path) == expected,
                  'Pinned source bytes differ: ' + str(path))

    @staticmethod
    def require_docker():
        return subprocess.check_output(['docker', 'info', '--format', '{{.ServerVersion}}'], text=True, timeout=30).strip()

    @staticmethod
    def execute(argv, log, seconds, cwd, env, container):
        log = Path(log)
        log.parent.mkdir(parents=True, exist_ok=True)
        R.require(re.fullmatch('arctic-paired-native-[0-9a-f]{32}', container), 'Invalid owned container name')
        with log.open('xb') as output:
            child = subprocess.Popen(argv, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT,
                                     start_new_session=True)
            try:
                status = child.wait(timeout=seconds)
                R.require(status == 0, 'Native command failed (' + str(status) + '); see ' + log.name)
            except BaseException:
                subprocess.run(['docker', 'rm', '-f', container], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=30)
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGTERM)
                    try:
                        child.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait(timeout=15)
                raise

    @staticmethod
    def preserve_phase(vm, evidence, name):
        target = evidence / name
        target.mkdir(parents=True, exist_ok=True)
        copied = {}
        if vm.exists():
            for path in vm.iterdir():
                if path.is_file() and not path.is_symlink() and path.suffix in ('.log', '.png', '.txt'):
                    R.require(path.stat().st_size < 128 * 1024 * 1024, 'Oversized diagnostic ' + path.name)
                    shutil.copyfile(path, target / path.name)
                    copied[path.name] = dict(bytes=path.stat().st_size, sha256=R.digest(path))
        return copied

    @staticmethod
    def verify_iso(inputs):
        path = inputs / 'iso' / R.ISO
        R.require(path.is_file() and not path.is_symlink(), 'ISO is absent or a symlink')
        R.require(path.stat().st_size == R.ISO_BYTES and R.ISO_BYTES < 2_000_000_000,
                  'ISO byte count differs or exceeds release limit')
        R.require(R.digest(path) == R.ISO_SHA256, 'Actual ISO SHA256 differs')
        return dict(name=R.ISO, bytes=R.ISO_BYTES, sha256=R.ISO_SHA256, source=R.SOURCE)

def verify(args):
    manifest = json.loads(args.manifest.read_text())
    R.require(manifest.get('ready') is True and manifest.get('release_acceptance') is False,
              'Prepared native execution is disabled until the rebuilt ISO is pinned and reviewed')
    R.require(os.environ.get('GITHUB_ACTIONS') == 'true'
              and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
              and os.environ.get('GITHUB_REPOSITORY') == 'yuvalkolodkingal/Arctic-Linux'
              and os.environ.get('GITHUB_REF') == 'refs/heads/codex/qualification-dispatch-20261008'
              and os.environ.get('GITHUB_WORKFLOW') == 'Candidate native image qualification'
              and os.environ.get('GITHUB_EVENT_NAME') == 'push'
              and os.environ.get('GITHUB_RUN_ATTEMPT') == '1', 'Requires the reviewed disposable Arctic Actions lane')
    image = manifest['image']
    R.SOURCE, R.ISO, R.ISO_BYTES, R.ISO_SHA256 = image['source_sha'], image['name'], image['bytes'], image['sha256']
    R.ORIGINAL_RUN = image['run_id']
    R.require(re.fullmatch('[0-9a-f]{40}', R.SOURCE) and re.fullmatch('[0-9a-f]{64}', R.ISO_SHA256),
              'Invalid full source/hash identity')
    R.require(re.fullmatch(r'Arctic-Linux-1\.2-candidate-[0-9]+-1-x86_64\.iso', R.ISO), 'Invalid candidate filename')
    R.require(type(R.ISO_BYTES) is int and type(R.ORIGINAL_RUN) is int, 'Invalid image numeric identities')
    source_head = subprocess.check_output(['git', '-C', str(args.source), 'rev-parse', 'HEAD'], text=True).strip()
    execution = args.bundle.parents[1]
    execution_head = subprocess.check_output(['git', '-C', str(execution), 'rev-parse', 'HEAD'], text=True).strip()
    R.require(source_head == R.SOURCE and execution_head == os.environ['GITHUB_SHA'], 'Source/execution head differs')
    for tree in (args.source, execution):
        R.require(not subprocess.check_output(['git', '-C', str(tree), 'status', '--porcelain'], text=True).strip(),
                  'Dirty qualification checkout')
    provenance = json.loads((args.bundle / 'source-provenance.json').read_text())
    for name, expected in provenance['files'].items():
        R.require(Path(name).name == name, 'Unsafe source filename')
        R.pinned_file(args.bundle / name, expected)
    for name, expected in manifest['execution_files'].items():
        R.require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'Unsafe execution source path')
        R.pinned_file(execution / name, expected)
    R.require(set(manifest['execution_files']) == {'.github/workflows/native-candidate-20261008.yml',
              'tools/test-install.sh', 'tools/lib/vmtest.py', 'tools/lib/container.sh',
              'tools/native-functional/fetch-image.py', 'tools/native-functional/screen-evidence.py',
              'tools/native-functional/compose-photo-probe.py',
              'tools/native-functional/runner.py', 'tools/native-functional/evidence.py',
              'tools/native-functional/source-provenance.json'}, 'Execution pin set differs')
    R.verify_iso(args.inputs)

def checker_proof():
    return dict(method='native-functional', checker_sha256=CHECKERS['native-functional'][1],
                native_source_sha256=E.NATIVE_SOURCE_SHA, release_acceptance=False)

validate_harness_serial = E.validate_harness_serial
check_physical = E.check_physical
check_editor_save = E.check_editor_save
preserve_audio = E.preserve_audio

def run(args):
    verify(args) # Rehash the actual unsplit ISO immediately before any VM.
    docker=R.require_docker();R.require(Path('/dev/kvm').is_char_device(),'KVM disappeared')
    vm=args.evidence.parent/'native-vm';R.require(not vm.exists(),'Native VM output must be unused')
    state=dict(status='prepared',candidate_iso_source=R.SOURCE,execution_checker_head=os.environ['GITHUB_SHA'],
               iso_bytes=R.ISO_BYTES,iso_sha256=R.ISO_SHA256,checker=checker_proof(),docker_server_version=docker,
               release_acceptance=False,source_image_run=R.ORIGINAL_RUN,
               recovered_native_source_commit='bdf797b19833fc8fe4002a328333edfc3777dfed')
    prepared=None
    def save():
        state['recorded_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        R.write_json(args.evidence/'execution.json',state)
    def interrupted(signum,frame):raise InterruptedError('Native run interrupted by signal '+str(signum))
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    try:
        save();container='arctic-paired-native-'+uuid.uuid4().hex
        env=dict(os.environ,CONTAINER_ENGINE='docker',ARCTIC_VM_CONTAINER_NAME=container)
        R.execute(['bash',str(args.source/'tools/performance/prepare-vm-tools.sh'),str(args.evidence)],
                  args.evidence/'provision.log',20*60,args.source,env,container)
        prepared=(args.evidence/'vm-prepared-image-id.txt').read_text().strip()
        R.require(re.fullmatch(r'(sha256:)?[0-9a-f]{64}',prepared),'Immutable test-tool image ID missing')
        verify(args) # refuse changed source before preparing any guest payload
        state.update(status='running_live_install_first_boot',vm_tool_image_id=prepared);save()
        payload = args.evidence.parent / 'native-payload'
        R.require(not payload.exists(), 'Native payload must be unused')
        payload.mkdir()
        spec = importlib.util.spec_from_file_location('native_photo_composer', args.bundle / 'compose-photo-probe.py')
        composer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(composer)
        photo_probe = payload / 'photo-check.py'
        photo_collection_sha = composer.compose(args.source, photo_probe)
        state['photo_probe'] = dict(sha256=R.digest(photo_probe), collection_sha256=photo_collection_sha);save()
        name,sha=CHECKERS['native-functional'];R.pinned_file(args.bundle/name,sha)
        container='arctic-paired-native-'+uuid.uuid4().hex
        env=dict(os.environ,CONTAINER_ENGINE='docker',ARCTIC_VM_CONTAINER_NAME=container,
                 ARCTIC_FEDORA_IMAGE=prepared,ARCTIC_VM_TOOLS_PREPARED='1',ARCTIC_NATIVE_AUDIO_FIXTURE='1',
                 ARCTIC_NATIVE_LAUNCHER=str(args.bundle/'native-launcher-v6.py'),
                 ARCTIC_NATIVE_EDITOR_SAVE_FIXTURE='1',ARCTIC_NATIVE_PHYSICAL_CONTROLLER=str(args.bundle/'native-physical-controller.py'),
                 ARCTIC_NATIVE_PHOTO_CHECKER=str(photo_probe),
                 ARCTIC_NATIVE_PHYSICAL_SHA=R.digest(args.bundle/'native-physical-controller.py'),
                 ARCTIC_NATIVE_PHYSICAL_CHECKER_SHA=sha)
        argv=['bash',str(args.bundle.parents[1]/'tools/test-install.sh'),'--iso',str(args.inputs/'iso'/R.ISO),
              '--kvm','--memory','4096','--smp','2','--boot-append','','--install-timeout','2400',
              '--boot-network','offline','--guest-check',str(args.bundle/name),
              '--profile',str(args.source/'profiles/ci/offline.toml'),'--out',str(vm)]
        verify(args) # recheck actual source/ISO after provisioning, immediately before the sole VM
        state['immediate_pre_vm_verification']=dict(iso=R.verify_iso(args.inputs),execution_manifest_sha256=R.digest(args.manifest));save()
        errors=[]
        try:R.execute(argv,args.evidence/'native-harness.log',110*60,args.bundle.parents[1],env,container)
        except BaseException as error:errors.append('harness: '+str(error))
        finally:state['harness_evidence']=R.preserve_phase(vm,args.evidence,'harness');save()
        # Extract complete available native files and bounded WAV even on failed probes.
        try:
            state['native_stages']=validate_harness_serial(vm,args.evidence)
            state['physical_stages']={stage:check_physical((vm/name).read_text(),stage,vm,args.evidence/('native-'+stage))
                for stage,name in (('live','serial-install.log'),('installed','serial-boot.log'))}
            state['editor_save_stages']={stage:check_editor_save((vm/name).read_text(),stage,vm,args.evidence/('native-'+stage))
                 for stage,name in (('live','serial-install.log'),('installed','serial-boot.log'))}
            state['photos'] = {}
            for stage, name in (('live', 'serial-install.log'), ('installed', 'serial-boot.log')):
                rows = E.records((vm/name).read_text().splitlines(), 'ARCTIC-NATIVE-PHOTOS ')
                R.require(len(rows) == 1 and rows[0]['stage'] == stage and rows[0]['status'] == 'passed'
                          and rows[0]['collection_sha256'] == photo_collection_sha
                          and rows[0]['release_acceptance'] is False, 'Missing/failed pinned photo image verification: ' + stage)
                state['photos'][stage] = rows[0]
        except BaseException as error:errors.append('native stages: '+str(error))
        state['audio']={}
        for stage in ('install','boot'):
            try:state['audio'][stage]=preserve_audio(vm/('native-audio-'+stage+'.wav'),args.evidence/'virtual-audio')
            except BaseException as error:errors.append(stage+' audio: '+str(error))
        R.require(not errors,'; '.join(errors))
        state['status']='limited_native_live_installed_smoke_passed_pending_visual_audio_review';save()
    except BaseException as error:
        state.update(status='failed_or_unrun',error=str(error));save();raise
    finally:
        if prepared:subprocess.run(['docker','image','rm',prepared],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'inputs', 'evidence', 'manifest'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    args.bundle = HERE
    for name in ('source', 'inputs', 'evidence', 'manifest'):
        setattr(args, name, getattr(args, name).resolve())
    R.require(not args.evidence.exists(), 'Evidence directory must be unused')
    # Fail the disabled manifest and real source/ISO checks before provisioning.
    verify(args)
    args.evidence.mkdir(parents=True)
    run(args)

if __name__ == '__main__':
    main()
