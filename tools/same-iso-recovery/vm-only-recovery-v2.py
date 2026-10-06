#!/usr/bin/env python3
"""Fixed-artifact VM recovery driver. Preparation is not execution permission."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import uuid

REPOSITORY = 'yuvalkolodkingal/Arctic-Linux'
ORIGINAL_RUN = 37507582946
ORIGINAL_ATTEMPT = 1
ARTIFACT_ID = 11434226349
ARTIFACT_NAME = 'arctic-linux-iso'
ARCHIVE_BYTES = 1880429588
ARCHIVE_DIGEST = 'sha256:ea25d1ba5fc9b35b6141390825cf333b30b8bb3154b7bd3237a8d676d084740c'
SOURCE = 'fe4742c8b9414c45f0bcbb0a4191f116383c60d1'
ISO = 'Arctic-Linux-1.2-candidate-37507582946-1-x86_64.iso'
ISO_BYTES = 1880244224
ISO_SHA256 = '84c9c88ebcbcaf69dbabf56509a9ceb2db58e5dc41d7bae12093edba12f60718'
BOOT_METHODS = ('uefi-sb-try', 'uefi-safe', 'bios-try')
CHECKERS = {
    'dnf': ('guest-check-dnf-v1.py', '472c159452adad998f8833b1d03815ba5572ebf0394215ab146490c45fdbedb9'),
    'arctic-offline': ('guest-check-offline-v1.py', '967883e8467fb8bb5b5c6159707f8c9fd78d8d2850280344953c375df7ee3576'),
}
BUNDLE_PINS = {
    'README-v1.md': '530b210387da1f293590c9bd650900eb6286bbf0c367a84a7bcd0730e928de7f',
    'review-ready-v1.json': '0120117d1a0eedea033bfe9d239151ee0461c2f58efa2dc060141d2454554692',
    'independent-review-v1.json': '4e513bc75ae82eff7367d711b7f7a71a032eb50ee8ecb1caa5c2d0700fdf23fa',
}
SOURCE_PINS = {
    'tools/test-iso.sh': '98d39ad53097834b8ace9413b88f7db2ccdce8839cd8f8e32f29608c633b7286',
    'tools/test-install.sh': 'a3a0a11d41d184bec817d98b90a96d87309d253882d3113e6a32c1ab48d5008e',
    'tools/lib/container.sh': '603487240996b0b5bc089061fbf84a57c4c801b9d5f8141c867ea60ff6547b42',
    'tools/lib/vmtest.py': '8b5136dee77373aee27ec3a695ab712b2b1997adb7fda03dfcb4371fe0414717',
    'tools/performance/prepare-vm-tools.sh': 'be178c9666d59c246e3ca1d6b805eb3e9286e17c3d306b17bb703d2f1561edfe',
    'profiles/ci/offline.toml': '6f65135a62c397c374f367de459aed784519c2040195ee41d88300996c9b7b2b',
    'tools/nix-acceptance/guest.py': '717402f5437d0560c5c2b127bbb904b1b2c62d3a6f4e5c431b107406b3816f1e',
}
EXECUTION_FILES = {
    '.github/workflows/iso.yml', 'tools/test-iso.sh', 'tools/lib/container.sh', 'tools/lib/vmtest.py',
    *('tools/same-iso-recovery/' + name for name in (
        'vm-only-recovery-v2.py', 'boot-evidence-v2.py', 'README-v2.md', 'test_vm_only_v2.py',
        'test-iso-collector-v2.patch', 'collector-command-v2.txt')),
}
METADATA_PINS = {
    'BUILD-INFO': '3a45b8908beaab7bc0782eac036fe9dc19cb1f5a2f9329fece1870a47e624a3b',
    'iso/' + ISO[:-4] + '.build-info': '7e3bcd797c8fd1142292b81275b831215073205f843c944287be4eb4a58032df',
    'iso/' + ISO + '.sha256': '261922a836eb2fc467a4f7033c04ca968e89072898ebbfc60532759cda43bc31',
    'iso/' + ISO[:-4] + '.packages': '3990cbf8b9968180e526ac34a7054846c248340553770ec12d01db72624741f0',
    'iso/' + ISO[:-4] + '.rpm-inventory.tsv': '7a34adfa4bf7a9f4bd57f0b325a91202121dec9e9b2dca9766c0e7fdf091603a',
    'iso/' + ISO[:-4] + '.flatpak-refs.txt': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def pinned_file(path, expected):
    require(path.is_file() and not path.is_symlink(), 'Missing/linked pinned file: ' + str(path))
    require(digest(path) == expected, 'Pinned file changed: ' + str(path))


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def validate_ci(env):
    require(env.get('CONTAINER_ENGINE', '') in ('', 'docker'), 'Recovery cleanup requires Docker')
    require(env.get('GITHUB_ACTIONS') == 'true' and env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch',
            'Only an explicitly dispatched supported Actions test run is allowed')
    require(env.get('GITHUB_REPOSITORY') == REPOSITORY and env.get('GITHUB_API_URL') == 'https://api.github.com',
            'Unexpected repository or API host')
    require(env.get('RECOVERY_MODE') == 'true' and env.get('RELEASE_REQUESTED') == 'false',
            'Recovery must be explicitly selected and release must be false')
    require(re.fullmatch('[0-9a-f]{40}', env.get('GITHUB_SHA', '')) and env['GITHUB_SHA'] != SOURCE,
            'A distinct qualification execution-checker commit is required')
    require(re.fullmatch('[0-9]+', env.get('GITHUB_RUN_ID', '')) and int(env['GITHUB_RUN_ID']) != ORIGINAL_RUN,
            'A separate recovery run is mandatory')
    require(re.fullmatch('[1-9][0-9]*', env.get('GITHUB_RUN_ATTEMPT', '')), 'Missing recovery attempt')


def validate_original(run, jobs, artifact):
    require(type(run.get('id')) is int and run.get('id') == ORIGINAL_RUN
            and type(run.get('run_attempt')) is int and run.get('run_attempt') == ORIGINAL_ATTEMPT
            and run.get('head_sha') == SOURCE and run.get('name') == 'ISO', 'Original run/source/attempt differs')
    require((run.get('status') == 'completed' and run.get('conclusion') == 'failure')
            or (run.get('status') == 'in_progress' and run.get('conclusion') is None),
            'Original run must be active or failed, with the exact Nix failure confirmed below')
    failed = [(job, step) for job in jobs if job.get('run_id') == ORIGINAL_RUN and job.get('head_sha') == SOURCE
              for step in job.get('steps', []) if step.get('name') == 'Nix enforcing VM acceptance'
              and step.get('status') == 'completed' and step.get('conclusion') == 'failure']
    require(len(failed) == 1, 'Expected exactly one confirmed original Nix acceptance failure')
    require(artifact.get('id') == ARTIFACT_ID and artifact.get('name') == ARTIFACT_NAME
            and artifact.get('expired') is False and artifact.get('size_in_bytes') == ARCHIVE_BYTES
            and artifact.get('digest') == ARCHIVE_DIGEST
            and artifact.get('workflow_run', {}).get('id') == ORIGINAL_RUN
            and artifact['workflow_run'].get('head_sha') == SOURCE, 'Artifact metadata identity differs or expired')
    job, step = failed[0]
    return dict(run=ORIGINAL_RUN, attempt=ORIGINAL_ATTEMPT, source=SOURCE,
                status=run['status'], conclusion=run['conclusion'],
                nix_job_id=job['id'], nix_step_number=step['number'], nix_step_conclusion=step['conclusion'],
                meaning='Confirms recorded step failure; metadata alone does not prove its cause. Original result stays unchanged.')


def verify_sources(source, bundle, execution_head):
    for folder, wanted in ((source, SOURCE), (bundle.parents[1], execution_head)):
        actual = subprocess.check_output(['git', '-C', str(folder), 'rev-parse', 'HEAD'], text=True).strip()
        require(actual == wanted, 'Checkout identity differs: ' + str(folder))
        dirty = subprocess.check_output(['git', '-C', str(folder), 'status', '--porcelain'], text=True).strip()
        require(not dirty, 'Checkout contains tracked or untracked changes: ' + str(folder))
    execution_pins = json.loads((bundle/'execution-pins-v2.json').read_text())
    require(execution_pins['candidate_source'] == SOURCE and type(execution_pins['schema']) is int
            and execution_pins['schema'] == 2 and set(execution_pins['files']) == EXECUTION_FILES,
            'Execution manifest identity/file set differs')
    for relative, expected in execution_pins['files'].items():
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts, 'Unsafe execution manifest path')
        pinned_file(bundle.parents[1]/relative, expected)
    for relative, expected in SOURCE_PINS.items():
        pinned_file(source/relative, expected)
    for relative, expected in BUNDLE_PINS.items():
        pinned_file(bundle/relative, expected)
    for name, expected in CHECKERS.values():
        pinned_file(bundle/name, expected)
    ready = json.loads((bundle/'review-ready-v1.json').read_text())
    review = json.loads((bundle/'independent-review-v1.json').read_text())
    require(ready['base']['source'] == SOURCE and ready['iso']['build_reported_sha256'] == ISO_SHA256
            and ready['iso']['build_reported_bytes'] == ISO_BYTES, 'Frozen prototype candidate identity differs')
    require(review['blocking_source_findings'] == [] and review['tests']['all_passed'] is True
            and review['status'] == 'SOURCE AND FIXTURE REVIEW PASS; ACTUAL VM QUALIFICATION UNRUN',
            'Frozen prototype does not have a passing independent source review')


def verify_iso(inputs):
    # These are file-content pins, independently of the Actions ZIP digest.
    iso = inputs/'iso'/ISO
    require(iso.is_file() and not iso.is_symlink(), 'Exact unsplit candidate ISO is absent')
    require(iso.stat().st_size == ISO_BYTES, 'ISO byte count differs')
    require(digest(iso) == ISO_SHA256, 'Actual ISO checksum differs')
    for relative, expected in METADATA_PINS.items():
        pinned_file(inputs/relative, expected)
    allowed = set(METADATA_PINS) | {'iso/' + ISO}
    actual = set()
    for path in inputs.rglob('*'):
        require(not path.is_symlink(), 'Artifact contains a symlink')
        if path.is_file():
            actual.add(str(path.relative_to(inputs)))
    require(actual == allowed, 'Unexpected or missing artifact files')
    build = dict(line.split('=', 1) for line in (inputs/'BUILD-INFO').read_text().splitlines()
                 if '=' in line and not line.startswith('#'))
    iso_build = dict(line.split('=', 1) for line in (inputs/('iso/'+ISO[:-4]+'.build-info')).read_text().splitlines()
                     if '=' in line)
    require(build.get('git_commit') == SOURCE and build.get('git_dirty') == 'no'
            and build.get('release_suffix') == '.preview.37507582946.1.gitfe4742c'
            and build.get('arctic_repos') == 'enabled', 'Build provenance differs')
    require(iso_build.get('git_commit') == SOURCE and iso_build.get('build_tool_commit') == SOURCE
            and iso_build.get('iso_bytes') == str(ISO_BYTES) and iso_build.get('arctic_repos') == 'enabled',
            'ISO build-info provenance differs')
    return dict(path=str(iso), bytes=ISO_BYTES, sha256=ISO_SHA256, candidate_source=SOURCE,
                metadata_sha256=METADATA_PINS, byte_verified=True)


def api(relative, paginate=False):
    argv = ['gh', 'api', '--hostname', 'github.com', '-H', 'Accept: application/vnd.github+json',
            '-H', 'X-GitHub-Api-Version: 2022-11-28']
    if paginate:
        argv += ['--paginate', '--slurp']
    argv.append('repos/' + REPOSITORY + '/' + relative)
    return json.loads(subprocess.check_output(argv, text=True, timeout=120))


def checker_proof(args):
    if args.method in CHECKERS:
        name, sha = CHECKERS[args.method]
        return dict(method=args.method, name=name, sha256=sha)
    require(args.method in BOOT_METHODS, 'Unknown boot method')
    return dict(method=args.method, name='boot-evidence-v2.py',
                sha256=digest(args.bundle/'boot-evidence-v2.py'),
                collector_sha256=digest(args.bundle.parents[1]/'tools/test-iso.sh'))


def require_docker():
    require(shutil.which('docker') is not None, 'Docker CLI is required for owned container cleanup')
    version = subprocess.check_output(['docker', 'info', '--format', '{{.ServerVersion}}'],
                                      text=True, stderr=subprocess.STDOUT, timeout=30).strip()
    require(bool(version), 'Docker daemon is not available')
    return version


def preflight(args):
    validate_ci(os.environ)
    verify_sources(args.source, args.bundle, os.environ['GITHUB_SHA'])
    require(not args.inputs.exists(), 'Artifact destination must be unused')
    require(not args.evidence.exists(), 'Evidence destination must be unused')
    args.evidence.mkdir(parents=True)
    docker_version = require_docker()
    require(Path('/dev/kvm').is_char_device(), 'Native KVM required; no TCG fallback or host chmod')
    require(shutil.disk_usage(args.evidence).free >= 20_000_000_000, 'At least 20 GB free needed for download and fresh VM')
    run = api('actions/runs/' + str(ORIGINAL_RUN))
    pages = api('actions/runs/' + str(ORIGINAL_RUN) + '/jobs?filter=all&per_page=100', paginate=True)
    artifact = api('actions/artifacts/' + str(ARTIFACT_ID))
    original = validate_original(run, [job for page in pages for job in page['jobs']], artifact)
    proof = dict(original_result=original, artifact=dict(id=ARTIFACT_ID, name=ARTIFACT_NAME,
                 original_run=ORIGINAL_RUN, archive_bytes=ARCHIVE_BYTES, archive_digest=ARCHIVE_DIGEST),
                 execution_checker_head=os.environ['GITHUB_SHA'], candidate_iso_source=SOURCE,
                 driver_sha256=digest(Path(__file__)), checker=checker_proof(args),
                 execution_manifest_sha256=digest(args.bundle/'execution-pins-v2.json'),
                 source_pins=SOURCE_PINS, bundle_pins=BUNDLE_PINS, docker_server_version=docker_version,
                 recovery_run=int(os.environ['GITHUB_RUN_ID']), recovery_attempt=int(os.environ['GITHUB_RUN_ATTEMPT']))
    write_json(args.evidence/'preflight.json', proof)


def verify(args):
    validate_ci(os.environ)
    verify_sources(args.source, args.bundle, os.environ['GITHUB_SHA'])
    proof = json.loads((args.evidence/'preflight.json').read_text())
    require(proof['execution_checker_head'] == os.environ['GITHUB_SHA'] and proof['checker'] == checker_proof(args)
            and proof['execution_manifest_sha256'] == digest(args.bundle/'execution-pins-v2.json'),
            'Preflight belongs to another checker execution')
    proof['iso'] = verify_iso(args.inputs)
    write_json(args.evidence/'verified-input.json', proof)
    for relative in METADATA_PINS:
        target = args.evidence/'input-metadata'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.inputs/relative, target)


def preserve_phase(vm, evidence, phase):
    target = evidence/phase
    require(not target.exists(), 'Phase evidence must never be overwritten: ' + phase)
    target.mkdir()
    copied = {}
    if vm.exists():
        for path in sorted(vm.iterdir()):
            if path.is_file() and not path.is_symlink() and path.suffix in ('.log', '.png', '.txt'):
                shutil.copyfile(path, target/path.name)
                copied[path.name] = dict(bytes=path.stat().st_size, sha256=digest(target/path.name))
    write_json(target/'manifest.json', copied)
    return copied


def probe_success(vm):
    serial = vm/'serial-boot.log'
    require(serial.is_file(), 'No installed serial evidence')
    statuses = re.findall(r'^ARCTIC-INSTALLED-SMOKE-EXIT=(.*)$', serial.read_text(errors='replace'), re.M)
    require(statuses == ['0\r'] or statuses == ['0'], 'Missing, duplicate or failed installed probe exit')


def execute(argv, log, seconds, cwd, env, container):
    with log.open('w') as output:
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            returncode = process.wait(timeout=seconds)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=15)
            raise
        finally:
            # Only the uniquely owned test/provisioning container is affected.
            subprocess.run(['docker', 'rm', '--force', container], stdout=output, stderr=output, timeout=30)
    require(returncode == 0, 'Harness/provisioning failed: ' + log.name + ' exit=' + str(returncode))


def run(args):
    require(args.method in CHECKERS, 'Install driver only accepts explicit DNF/offline methods')
    # Re-hash the actual file immediately before any VM. No saved-label shortcut.
    verify(args)
    docker_version = require_docker()
    require(Path('/dev/kvm').is_char_device(), 'KVM disappeared before the VM run')
    vm = args.evidence.parent/'vm'
    require(not vm.exists(), 'Fresh method-specific VM output must be unused')
    checker = args.bundle/CHECKERS[args.method][0]
    state = dict(status='prepared', method=args.method, candidate_source=SOURCE,
                 execution_checker_head=os.environ['GITHUB_SHA'], iso_sha256=ISO_SHA256,
                 iso_bytes=ISO_BYTES, checker_sha256=CHECKERS[args.method][1], vm=str(vm),
                 docker_server_version=docker_version, coverage=('ordinary DNF upgrade/reboot only' if args.method == 'dnf' else
                           'explicit signed arctic-offline staging, completed reboot/history'), phases=[])
    prepared = None

    def save():
        state['recorded_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        write_json(args.evidence/'execution.json', state)

    def interrupted(signum, frame):
        raise InterruptedError('Recovery interrupted by signal ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        save()
        provision = 'arctic-paired-recovery-' + uuid.uuid4().hex
        env = dict(os.environ, CONTAINER_ENGINE='docker', ARCTIC_VM_CONTAINER_NAME=provision)
        execute(['bash', str(args.source/'tools/performance/prepare-vm-tools.sh'), str(args.evidence)],
                args.evidence/'provision.log', 20*60, args.source, env, provision)
        prepared = (args.evidence/'vm-prepared-image-id.txt').read_text().strip()
        require(re.fullmatch(r'(sha256:)?[0-9a-f]{64}', prepared), 'Invalid immutable VM tool image')
        state['vm_tool_image_id'] = prepared
        common = ['bash', str(args.source/'tools/test-install.sh'), '--kvm', '--memory', '4096', '--smp', '2',
                  '--boot-append', '', '--boot-network', 'online', '--guest-check', str(checker),
                  '--profile', str(args.source/'profiles/ci/offline.toml'), '--out', str(vm)]
        for phase, argv, seconds in (
                ('first-boot', common+['--iso', str(args.inputs/'iso'/ISO), '--install-timeout', '2400'], 100*60),
                ('after-update-reboot', common+['--stage', 'boot'], 60*60)):
            # Same frozen checker/tool image on both boots; second boot is
            # reached only after complete first-phase success and preservation.
            pinned_file(checker, CHECKERS[args.method][1])
            container = 'arctic-paired-recovery-' + uuid.uuid4().hex
            env = dict(os.environ, CONTAINER_ENGINE='docker', ARCTIC_FEDORA_IMAGE=prepared, ARCTIC_VM_TOOLS_PREPARED='1',
                       ARCTIC_VM_CONTAINER_NAME=container)
            state['status'] = 'running_' + phase
            save()
            try:
                execute(argv, args.evidence/(phase+'-harness.log'), seconds, args.source, env, container)
                probe_success(vm)
            finally:
                preserved = preserve_phase(vm, args.evidence, phase)
                state['phases'].append(dict(phase=phase, evidence=preserved))
                save()
            require('vm-toolchain.txt' in preserved and 'serial-boot.log' in preserved,
                    'Required first/reboot evidence absent')
            if phase == 'first-boot':
                toolchain = preserved['vm-toolchain.txt']['sha256']
            else:
                require(toolchain == preserved['vm-toolchain.txt']['sha256'], 'VM toolchain changed across reboot')
        state['status'] = 'revised_checker_vm_acceptance_passed'
        state['original_result_unchanged'] = True
        save()
    except BaseException as error:
        state['status'] = 'failed_or_unrun'
        state['error'] = str(error)
        save()
        raise
    finally:
        if prepared:
            subprocess.run(['docker', 'image', 'rm', prepared], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=30)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('preflight','verify','run'))
    parser.add_argument('--method', choices=tuple(CHECKERS), required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    for key in ('source','bundle','inputs','evidence'):
        setattr(args, key, getattr(args,key).resolve())
    try:
        globals()[args.phase](args)
    except BaseException as error:
        if args.evidence.exists():
            write_json(args.evidence/('blocked-'+args.phase+'.json'), dict(error=str(error),
                phase=args.phase, method=args.method, original_run=ORIGINAL_RUN,
                candidate_source=SOURCE, qualification='Failed/unrun; original outcome not changed'))
        raise


if __name__ == '__main__':
    main()
