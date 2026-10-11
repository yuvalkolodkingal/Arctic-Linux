"""Disabled hosted A/B build runner. No build or acquisition on import."""
import argparse
from contextlib import contextmanager, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import re
import resource
import signal
import stat
import subprocess
import sys
import tarfile
import time
import types
import urllib.request
import urllib.error
import uuid

REPO='yuvalkolodkingal/Arctic-Linux'
BRANCH='codex/browser-accelerator-hosted-build-meson-20261011'
MARKER='.github/browser-accelerator-hosted-build-meson-20261011.activate'
WORKFLOW='.github/workflows/browser-accelerator-hosted-build-meson-20261011.yml'
MANIFEST='tools/browser-accelerator-host-meson-20261011/execution-manifest.json'
PREFIX='tools/browser-accelerator-host-meson-20261011/'
IMAGE='registry.fedoraproject.org/fedora@sha256:05e3c351a7e762aca8fb067a9a92c1f775a7c4fbb1382c97cdd87bd6fb5b162c'
CONFIG='sha256:2888cc2c2cc0ad4bfcf46799719b91e9fb1224fad8d122a519c71ea9a58ce5fa'
SOURCE_URL='https://download-ib01.fedoraproject.org/pub/fedora/linux/updates/44/Everything/source/tree/Packages/e/epiphany-50.6-1.fc44.src.rpm'
KEY_URL='https://fedoraproject.org/fedora.gpg'
KEY_BODY_SHA='3b8a3660cca4851a67f67f56819e37e2f6b37ac8e905cb571b25d2127d1b7618'
FINGERPRINT='36F612DCF27F7D1A48A835E4DBFCF71C6D9F90A6'
IMAGE_PROVENANCE={'archive_bytes': 1929907101, 'archive_sha256': '3a8132aa4578fdb62b2aa1e3bf5c340229f1a483678d03ddf2c565fb39afadcd', 'artifact_id': 11689591362, 'bytes': 1929719808, 'name': 'Arctic-Linux-1.2-candidate-38102474066-1-x86_64.iso', 'producer_mode': 'frozen-external-paired-v1', 'producer_receipt_sha256': '3034ea88d4ba1d1e434942f90c42b8057d3667ad2e7f6ee739b895ebdfc86d1d', 'run_id': 38102474066, 'sha256': '807eaaa64ab8480ec2b18bc8434fd5e37d82c41b73a3e0a6f002c35d152ba54c', 'source_sha': '326690f173d4dc4f049f43e046c8380e66825a07'}
MAX_LOG=64*1024*1024
MAX_TOTAL=256*1024*1024
EXECUTION_FILES={'tools/browser-accelerator-host-meson-20261011/collect.py', 'tools/browser-accelerator-host-meson-20261011/README.md', 'tools/browser-accelerator-host-meson-20261011/test_execution.py', 'tools/browser-accelerator-host-meson-20261011/registry-provenance.json', '.github/workflows/browser-accelerator-hosted-build-meson-20261011.yml', 'tools/browser-accelerator-host-meson-20261011/runner.py'}
OBSERVER_FILES={'tools/browser-accelerator-ab-source/build_recipe.py', 'tools/browser-accelerator-ab-source/execution-context.json', 'tools/browser-accelerator-hosted-source/gtk-control.c', 'tools/browser-accelerator-ab-source/profile.py', 'tools/browser-accelerator-ab-source/source-inverse.json', 'tools/browser-accelerator-hosted-source/source-manifest.json', 'tools/browser-accelerator-ab-source/test_source.py', 'tools/browser-accelerator-hosted-source/producer.py', 'tools/browser-accelerator-hosted-source/producer-context.json', 'tools/browser-accelerator-hosted-source/README.md', 'tools/native-functional/screen-evidence.py', 'tools/browser-accelerator-hosted-source/test_producer.py', 'tools/browser-accelerator-ab-source/candidate.py', 'tools/browser-accelerator-ab-source/source-manifest.json', 'tools/browser-accelerator-ab-source/README.md'}
def require(value, code):
    if not value:
        raise RuntimeError(code)

def typed_equal(left, right):
    if type(left) is not type(right): return False
    if type(right) is dict:
        return set(left) == set(right) and all(typed_equal(left[key], value) for key, value in right.items())
    if type(right) is list:
        return len(left) == len(right) and all(typed_equal(a, b) for a, b in zip(left, right))
    return left == right

def read_json(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, 'duplicate_json')
            value[key] = item
        return value
    def reject(_):
        raise RuntimeError('nonfinite_json')
    return json.loads(raw, object_pairs_hook=unique, parse_constant=reject)

def sha(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()

def safe_file(root, relative, limit):
    root = Path(root).absolute()
    path = root / relative
    require(path.resolve() == path and root.resolve() == root and path.is_relative_to(root), 'contained_file')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as source:
        before = os.fstat(source.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid()
                and 0 < before.st_size <= limit, 'owned_file')
        raw = source.read(limit + 1)
        after = os.fstat(source.fileno())
        identity = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        require(len(raw) == before.st_size and identity(before) == identity(after), 'stable_file')
    return raw

def capture(argv, timeout=60, limit=2 * 1024 * 1024):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=timeout, check=True)
    require(len(result.stdout) <= limit and len(result.stderr) <= limit, 'command_bound')
    return result.stdout

def verify_tracked(root, name, expected=None, revision='HEAD'):
    raw = safe_file(root, name, 2 * 1024 * 1024)
    tracked = capture(['git', '-C', str(root), 'show', revision + ':' + name])
    row = capture(['git', '-C', str(root), 'ls-tree', revision, '--', name]).decode().strip().split()
    require(len(row) == 4 and row[0] in ('100644', '100755') and row[1] == 'blob'
            and raw == tracked and (expected is None or hashlib.sha256(raw).hexdigest() == expected), 'tracked_bytes')
    return raw

def activation_guard(root, manifest):
    validate_manifest(manifest, executable=True)  # No API/container/image acquisition before this.
    require(os.environ.get('GITHUB_REPOSITORY') == REPO and os.environ.get('GITHUB_EVENT_NAME') == 'push'
            and os.environ.get('GITHUB_REF') == 'refs/heads/' + BRANCH
            and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and os.environ.get('GITHUB_RUN_ATTEMPT') == '1', 'hosted_lane')
    event = read_json(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes())
    head = capture(['git', '-C', str(root), 'rev-parse', 'HEAD']).decode().strip()
    parents = capture(['git', '-C', str(root), 'show', '-s', '--format=%P', 'HEAD']).decode().split()
    require(len(parents) == 1 and event['before'] == parents[0]
            and event['after'] == head == os.environ['GITHUB_SHA'], 'sole_reviewed_parent')
    require(not capture(['git', '-C', str(root), 'ls-tree', parents[0], '--', MARKER]).strip(),
            'activation_marker_must_be_new')
    addition = capture(['git', '-C', str(root), 'diff', '--raw', '--no-abbrev', parents[0], head, '--', MARKER])
    require(re.fullmatch(rb':000000 100644 0{40} [0-9a-f]{40} A\t' + re.escape(MARKER.encode()) + rb'\n', addition),
            'activation_marker_regular_add')
    require(capture(['git', '-C', str(root), 'diff', '--name-only', parents[0], head]).decode().splitlines() == [MARKER]
            and verify_tracked(root, MARKER) == (parents[0] + '\n').encode(), 'sole_activation_child')
    require(not capture(['git', '-C', str(root), 'status', '--porcelain']).strip(), 'clean_execution')
    require(read_json(verify_tracked(root, MANIFEST)) == manifest, 'manifest_blob')
    for key in ('execution_files', 'observer_files'):
        for name, checksum in manifest[key].items():
            verify_tracked(root, name, checksum)
    for name, checksum in manifest['helper_files'].items():
        verify_tracked(root, 'tools/performance/' + name, checksum)
    ref = read_json(capture(['gh', 'api', 'repos/' + REPO + '/git/ref/heads/' + BRANCH]))
    require(ref['ref'] == 'refs/heads/' + BRANCH and ref['object']['sha'] == head, 'unchanged_branch')
    return {'schema': 'arctic-browser-diagnostic-activation-v1', 'parent_sha': parents[0],
            'execution_sha': head, 'run_id': int(os.environ['GITHUB_RUN_ID']), 'run_attempt': 1,
            'release_acceptance': False, 'performance_acceptance': False}

@contextmanager
def handoff():
    old=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM,signal.SIGALRM})
    try:yield
    finally:signal.pthread_sigmask(signal.SIG_SETMASK,old)

def ident(info):
    return (info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid,info.st_size,info.st_mtime_ns,info.st_ctime_ns)

def read_owned(path,limit):
    fd=None;before=None
    try:
        with handoff():
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC);before=ident(os.fstat(fd))
        require(stat.S_ISREG(before[2]) and before[3]==os.geteuid() and not before[2]&0o077 and 0<=before[5]<=limit,'private_file')
        raw=os.pread(fd,before[5]+1,0)
        require(len(raw)==before[5] and ident(os.fstat(fd))==before==ident(path.lstat()),'private_file_changed')
        return raw
    finally:
        with handoff():
            if fd is not None and before is not None:
                try:now=ident(os.fstat(fd))
                except OSError:now=None
                if now is not None and now[:5]==before[:5]:os.close(fd)

def write_private(path,raw):
    fd=None;before=None
    try:
        with handoff():
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600);before=ident(os.fstat(fd))
        view=memoryview(raw)
        while view:
            require(ident(os.fstat(fd))[:5]==before[:5],'output_generation')
            n=os.write(fd,view);require(n>0,'short_write');view=view[n:]
        now=ident(os.fstat(fd));require(now[:5]==before[:5] and now[5]==len(raw) and ident(path.lstat())==now,'output_changed')
    finally:
        with handoff():
            if fd is not None and before is not None:
                try:now=ident(os.fstat(fd))
                except OSError:now=None
                if now is not None and now[:5]==before[:5]:os.close(fd)

def validate_manifest(value,executable=False):
    keys={'schema','ready','release_acceptance','performance_acceptance','container','config','producer_context','execution_files','observer_files','helper_files','source_files','image_provenance'}
    require(type(value) is dict and set(value)==keys and value['schema']=='arctic-accelerator-hosted-execution-v1','manifest_schema')
    require(type(value['ready']) is bool and value['release_acceptance'] is False and value['performance_acceptance'] is False,'manifest_acceptance')
    require(value['container']==IMAGE and value['config']==CONFIG,'container_context')
    require(value['helper_files']=={},'helper_scope')
    for key in ('execution_files','observer_files','source_files'):
        require(type(value[key]) is dict and value[key] and all(type(n) is str and type(s) is str and re.fullmatch('[0-9a-f]{64}',s) for n,s in value[key].items()),'file_pins')
    require(set(value['execution_files'])==EXECUTION_FILES and set(value['observer_files'])==OBSERVER_FILES,'pin_inventory')
    require(value['source_files']=={'tools/native-functional/screen-evidence.py':'b3d56536397ff1c46caf082b97a070ff3eae383c2c277898c572cb34eb76f336'},'scanner_pin')
    require(typed_equal(value['image_provenance'],IMAGE_PROVENANCE),'F10_provenance')
    require(type(value['producer_context']) is dict and value['producer_context'].get('ready') is False and value['producer_context'].get('container') is None,'frozen_disabled_context')
    if executable:require(value['ready'] is True,'disabled')

def load_verified(root,name,pins,label):
    raw=verify_tracked(root,name,pins[name]);module=types.ModuleType(label);module.__file__=str(root/name)
    exec(compile(raw,str(root/name),'exec'),module.__dict__);return module

def command(argv,log,timeout):
    fd=None;identity=None;process=None
    inherited_mask=signal.pthread_sigmask(signal.SIG_BLOCK,set())
    def prepare_child():
        signal.pthread_sigmask(signal.SIG_SETMASK,inherited_mask)
        resource.setrlimit(resource.RLIMIT_FSIZE,(MAX_LOG,MAX_LOG))
    try:
        with handoff():
            fd=os.open(log,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600);identity=ident(os.fstat(fd))
            process=subprocess.Popen(argv,stdout=fd,stderr=subprocess.STDOUT,start_new_session=True,
                preexec_fn=prepare_child)
        end=time.monotonic()+timeout
        while process.poll() is None:
            require(time.monotonic()<end,'owned_command_timeout')
            require(ident(os.fstat(fd))[:5]==identity[:5] and os.fstat(fd).st_size<MAX_LOG,'owned_command_log_limit')
            time.sleep(.2)
        require(process.returncode==0 and os.fstat(fd).st_size<MAX_LOG,'owned_command_failed')
    finally:
        with handoff():
            if process is not None and process.poll() is None:
                try:os.killpg(process.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    process.wait(timeout=10)
            if fd is not None and identity is not None:
                try:now=ident(os.fstat(fd))
                except OSError:now=None
                if now is not None and now[:5]==identity[:5]:os.close(fd)

def acquire(url,size,sha256):
    with urllib.request.urlopen(url,timeout=30) as response:
        require(response.status==200,'official_HTTP_status')
        raw=response.read(size+1)
    require(len(raw)==size and hashlib.sha256(raw).hexdigest()==sha256,'official_input_binding')
    return raw

def image_identity(value):
    require(type(value) is list and len(value)==1,'image_identity')
    info=value[0]
    require(info['Id']==CONFIG and info['Os']=='linux' and info['Architecture']=='amd64'
            and IMAGE in info['RepoDigests'] and info['Config']['Labels']['org.opencontainers.image.version']=='44','immutable_image_identity')
    return {'image_id':info['Id'],'RepoDigests':info['RepoDigests'],'os':info['Os'],'architecture':info['Architecture']}

def container_identity(value,name,nonce):
    require(type(value) is list and len(value)==1,'container_identity')
    info=value[0]
    require(re.fullmatch('[0-9a-f]{64}',info['Id']) and info['Image']==CONFIG
        and info['Name']=='/'+name and info['Config']['Labels'].get('arctic.capture-nonce')==nonce,'owned_container_identity')
    require(not info['HostConfig']['Privileged'] and not info['HostConfig'].get('Binds') and not info.get('Mounts'),'container_mount_boundary')
    return info['Id']

def remove_container(name,nonce,expected=None):
    # Exact generated name + immutable label/image identity allow recovery if
    # cancellation occurs after docker create but before its returned ID binds.
    result=subprocess.run(['docker','container','inspect',name],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30)
    if result.returncode:
        require(result.returncode==1,'cleanup_inspection')
        listed=capture(['docker','ps','--all','--no-trunc','--filter','name=^/'+name+'$','--format','{{.ID}}'])
        require(not listed.strip(),'cleanup_absence_unproved');return
    require(len(result.stdout)<=2*1024*1024,'cleanup_metadata_bound')
    cid=container_identity(read_json(result.stdout),name,nonce)
    require(expected is None or cid==expected,'cleanup_generation')
    subprocess.run(['docker','rm','--force',cid],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30,check=True)
    check=capture(['docker','ps','--all','--no-trunc','--filter','id='+cid,'--format','{{.ID}}'])
    require(not check.strip(),'owned_container_remains')

def screen_originals(root,manifest,private,output):
    scanner=load_verified(root,'tools/native-functional/screen-evidence.py',manifest['source_files'],'whole_original_build_scanner')
    inventory=read_json(read_owned(private/'products/custom-ELF-inventory.json',4*1024*1024))
    binary={}
    for variant,record in inventory['variants'].items():
        require(variant in ('baseline','candidate'),'inventory_variant')
        for name,info in record['packages'].items():binary['products/'+variant+'/'+name]=info
        for info in record['ELFs'].values():binary['products/'+variant+'/ELF/'+info['file']]=info
    require(set(inventory['variants'])=={'baseline','candidate'} and inventory['actual_runtime_mapping_admission'] is False and inventory['performance_acceptance'] is False,'inventory_scope')
    files={};total=0
    for path in sorted(private.rglob('*')):
        require(not path.is_symlink(),'retention_symlink')
        if path.is_dir():continue
        relative=path.relative_to(private).as_posix()
        # Inputs contain only exact public Source/SRPM/key and remain private;
        # every original command log and product is retained without filtering.
        if relative.startswith('inputs/') or relative.startswith('keyring/'):continue
        raw=read_owned(path,MAX_LOG);total+=len(raw);require(total<=MAX_TOTAL,'retention_total_bound')
        if relative in binary:
            info=binary[relative];require(info['bytes']==len(raw) and info['sha256']==hashlib.sha256(raw).hexdigest(),'binary_whole_binding')
            require(raw.startswith(b'\xed\xab\xee\xdb') if relative.endswith('.rpm') else raw.startswith(b'\x7fELF'),'binary_format')
        else:
            require(path.suffix in ('.json','.txt','.log'),'unknown_retention_member')
            with redirect_stdout(io.StringIO()):require(scanner.external_text(raw)==raw,'whole_original_privacy')
        files[relative]=raw
    require(set(binary)<=set(files) and {'products/ab-build-receipt.json','products/custom-ELF-inventory.json','logs/producer.log','logs/collector.log'}<=set(files),'whole_group_retention')
    require(not output.exists(),'fresh_screened_output')
    stage=private/'screening-stage'
    with handoff():stage.mkdir(mode=0o700)
    for name,raw in files.items():
        target=stage/name;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700);write_private(target,raw)
    proof={'schema':'arctic-accelerator-ab-whole-original-retention-v1','files':{name:{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'redactions':0} for name,raw in files.items()},'original_whole_text_privacy':True,'binary_scope':'exact_owned_Fedora_build_RPM_and_ELF_inventory','performance_acceptance':False,'release_acceptance':False}
    write_private(stage/'retention-proof.json',(json.dumps(proof,sort_keys=True,indent=2)+'\n').encode())
    with handoff():stage.rename(output)

def main():
    global failure_phase
    failure_phase="arguments"
    parser=argparse.ArgumentParser();parser.add_argument('--guard-only',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[2];manifest=read_json(verify_tracked(root,MANIFEST));failure_phase="activation";activation=activation_guard(root,manifest)
    failure_phase="source_bindings"
    for name,checksum in manifest['source_files'].items():verify_tracked(root,name,checksum)
    if args.guard_only:return
    failure_phase="host_staging"
    base=Path(os.environ['RUNNER_TEMP']);private=base/'arctic-accelerator-ab-private';output=base/'arctic-accelerator-ab-screened'
    require(base.is_dir() and not base.is_symlink() and not private.exists() and not output.exists(),'fresh_host_paths')
    with handoff():
        private.mkdir(mode=0o700);(private/'inputs').mkdir(mode=0o700);(private/'logs').mkdir(mode=0o700)
    inputs=private/'inputs';logs=private/'logs';nonce=uuid.uuid4().hex;name='arctic-accelerator-'+nonce;cid=None
    def run(argv,tag,timeout):
        global failure_phase
        failure_phase=COMMAND_PHASES[tag]
        command(argv,logs/(tag+'.log'),timeout)
    failure_phase='producer_source'
    producer=load_verified(root,'tools/browser-accelerator-hosted-source/producer.py',manifest['observer_files'],'accepted_build_producer')
    context=read_json(verify_tracked(root,'tools/browser-accelerator-hosted-source/producer-context.json',manifest['observer_files']['tools/browser-accelerator-hosted-source/producer-context.json']))
    require(context==manifest['producer_context'],'original_producer_context');context=dict(context,ready=True,container=IMAGE);producer.validate_context(context)
    failure_phase='official_srpm'
    srpm=acquire(SOURCE_URL,4603759,producer.SRPM_SHA);members=producer.source_members(srpm)
    failure_phase='official_key_bundle'
    keybody=acquire(KEY_URL,4704,KEY_BODY_SHA);write_private(inputs/'official-fedora.gpg',keybody)
    (private/'keyring').mkdir(mode=0o700)
    run(['gpg','--homedir',str(private/'keyring'),'--batch','--quiet','--no-autostart','--import',str(inputs/'official-fedora.gpg')],'key-import',30)
    failure_phase='key_export'
    key=capture(['gpg','--homedir',str(private/'keyring'),'--batch','--no-autostart','--export',FINGERPRINT],limit=16384)
    require(len(key)==1176 and hashlib.sha256(key).hexdigest()==producer.KEY_SHA,'exact_public_key_export')
    failure_phase='source_archive'
    with tarfile.open(fileobj=io.BytesIO(members['epiphany-50.6.tar.xz']),mode='r:xz') as archive:
        file=archive.getmember('epiphany-50.6/src/ephy-window.c');require(file.isfile() and file.size==producer.WINDOW_BYTES,'source_window_member')
        window=archive.extractfile(file).read(producer.WINDOW_BYTES+1)
    require(hashlib.sha256(window).hexdigest()==producer.WINDOW_SHA,'exact_window_source')
    staged={'producer.py':verify_tracked(root,'tools/browser-accelerator-hosted-source/producer.py',manifest['observer_files']['tools/browser-accelerator-hosted-source/producer.py']),
        'collect.py':verify_tracked(root,PREFIX+'collect.py',manifest['execution_files'][PREFIX+'collect.py']),
        'candidate.py':verify_tracked(root,'tools/browser-accelerator-ab-source/candidate.py',manifest['observer_files']['tools/browser-accelerator-ab-source/candidate.py']),
        'gtk-control.c':verify_tracked(root,'tools/browser-accelerator-hosted-source/gtk-control.c',manifest['observer_files']['tools/browser-accelerator-hosted-source/gtk-control.c']),
        producer.SRPM_NAME:srpm,'Fedora44-primary.gpg':key,'ephy-window.c':window,
        'producer-context.json':(json.dumps(context,sort_keys=True,indent=2)+'\n').encode()}
    failure_phase='input_staging'
    for file,raw in staged.items():write_private(inputs/file,raw)
    write_private(private/'activation.json',(json.dumps(activation,sort_keys=True,indent=2)+'\n').encode())
    try:
        run(['docker','pull','--platform','linux/amd64',IMAGE],'image-pull',300)
        image=image_identity(read_json(capture(['docker','image','inspect',IMAGE])))
        write_private(private/'image-identity.json',(json.dumps(image,sort_keys=True,indent=2)+'\n').encode())
        run(['docker','create','--name',name,'--label','arctic.capture-nonce='+nonce,'--platform','linux/amd64','--network','bridge','--entrypoint','/bin/sleep',IMAGE,'infinity'],'container-create',60)
        cid=container_identity(read_json(capture(['docker','container','inspect',name])),name,nonce)
        write_private(private/'container-identity.json',(json.dumps({'container_id':cid,'capture_nonce':nonce,'name':name,'image_id':CONFIG,'no_host_mounts':True,'privileged':False},sort_keys=True,indent=2)+'\n').encode())
        run(['docker','start',cid],'container-start',30)
        run(['docker','exec',cid,'dnf5','install','--assumeyes','python3','rpm-build','redhat-rpm-config','dnf5-plugins','gcc','pkgconf-pkg-config','dbus-x11','xorg-x11-server-Xvfb','meson','elfutils'],'bootstrap',900)
        run(['docker','exec',cid,'install','-d','-m','700','/inputs','/out','/build'],'input-directories',30)
        run(['docker','cp',str(inputs)+ '/.',cid+':/inputs'],'input-copy',60)
        run(['docker','exec',cid,'chown','-R','0:0','/inputs'],'input-ownership',30)
        run(['docker','exec',cid,'chmod','-R','u=rX,go=','/inputs'],'input-readonly',30)
        for script,tag,deadline in (('producer.py','producer',7000),('collect.py','collector',300)):
            checksum=hashlib.sha256(staged[script]).hexdigest()
            loader="import hashlib; p='/inputs/"+script+"'; r=open(p,'rb').read(); assert hashlib.sha256(r).hexdigest()=='"+checksum+"'; exec(compile(r,p,'exec'),{'__name__':'__main__','__file__':p})"
            argv=['docker','exec',cid,'python3','-B','-c',loader]
            if script=='producer.py':argv+=['--context','/inputs/producer-context.json']
            run(argv,tag,deadline)
        run(['docker','cp',cid+':/out',str(private/'products')],'output-copy',120)
        # docker cp creates host files owned by the invoking runner; privacy
        # modes are retained. No bind mount exposes a host path to the build.
    finally:
        original_phase=failure_phase
        failure_phase="container_cleanup"
        with handoff():remove_container(name,nonce,cid)
        failure_phase=original_phase
    failure_phase='post_source_bindings'
    require(read_json(verify_tracked(root,MANIFEST))==manifest,'execution_manifest_unchanged')
    for key in ('execution_files','observer_files','source_files'):
        for path,checksum in manifest[key].items():verify_tracked(root,path,checksum)
    failure_phase='whole_original_privacy'
    screen_originals(root,manifest,private,output)

failure_phase = "unknown"
COMMAND_PHASES = {'key-import': 'key_import', 'image-pull': 'image_pull', 'container-create': 'container_create', 'container-start': 'container_start', 'bootstrap': 'bootstrap', 'input-directories': 'input_directories', 'input-copy': 'input_copy', 'input-ownership': 'input_ownership', 'input-readonly': 'input_readonly', 'producer': 'producer_builds', 'collector': 'collector', 'output-copy': 'output_copy'}
FAILURE_PHASES = frozenset(('unknown', 'arguments', 'activation', 'source_bindings', 'host_staging', 'producer_source', 'official_srpm', 'official_key_bundle', 'key_import', 'key_export', 'source_archive', 'input_staging', 'image_pull', 'container_create', 'container_start', 'bootstrap', 'input_directories', 'input_copy', 'input_ownership', 'input_readonly', 'producer_builds', 'collector', 'output_copy', 'container_cleanup', 'post_source_bindings', 'whole_original_privacy'))
FAILURE_CATEGORIES = frozenset(("unknown", "interrupted", "http_error", "network_error", "command_failed", "command_timeout", "os_error"))

def finite_host_failure(error):
    """No exception operands, stderr, paths, lengths or unknown values leave here."""
    phase = failure_phase if type(failure_phase) is str and failure_phase in FAILURE_PHASES else "unknown"
    category = "unknown"
    if type(error) is RuntimeError:
        trace = BaseException.__dict__["__traceback__"].__get__(error, type(error))
        frames = []
        for _ in range(64):
            if trace is None:
                break
            frames.append((trace.tb_frame.f_code, trace.tb_frame.f_globals, trace.tb_lineno))
            trace = trace.tb_next
        if trace is not None:
            return phase, "unknown"
        for index, (code, context, line) in enumerate(frames):
            if code is FAILURE_REQUIRE_OWNER[0] and context is FAILURE_REQUIRE_OWNER[1]:
                if index == 0:
                    continue
                caller, namespace, caller_line = frames[index - 1]
                for owner, globals_owner, sites in FAILURE_SITE_OWNERS:
                    if caller is owner and namespace is globals_owner and caller_line in sites:
                        reason=sites[caller_line]
                        if type(reason) is str and reason in FAILURE_REQUIRE_CODES:
                            return phase, reason
    elif type(error) in (KeyboardInterrupt, InterruptedError, SystemExit):
        category = "interrupted"
    elif type(error) is urllib.error.HTTPError:
        category = "http_error"
    elif type(error) is urllib.error.URLError:
        category = "network_error"
    elif type(error) is subprocess.CalledProcessError:
        category = "command_failed"
    elif type(error) is subprocess.TimeoutExpired:
        category = "command_timeout"
    elif isinstance(error, OSError):
        category = "os_error"
    return phase, category

FAILURE_REQUIRE_CODES = frozenset(('F10_provenance', 'activation_marker_must_be_new', 'activation_marker_regular_add', 'binary_format', 'binary_whole_binding', 'clean_execution', 'cleanup_absence_unproved', 'cleanup_generation', 'cleanup_inspection', 'cleanup_metadata_bound', 'command_bound', 'contained_file', 'container_context', 'container_identity', 'container_mount_boundary', 'disabled', 'duplicate_json', 'exact_public_key_export', 'exact_window_source', 'execution_manifest_unchanged', 'file_pins', 'fresh_host_paths', 'fresh_screened_output', 'frozen_disabled_context', 'helper_scope', 'hosted_lane', 'image_identity', 'immutable_image_identity', 'inventory_scope', 'inventory_variant', 'manifest_acceptance', 'manifest_blob', 'manifest_schema', 'official_HTTP_status', 'official_input_binding', 'original_producer_context', 'output_changed', 'output_generation', 'owned_command_failed', 'owned_command_log_limit', 'owned_command_timeout', 'owned_container_identity', 'owned_container_remains', 'owned_file', 'pin_inventory', 'private_file', 'private_file_changed', 'retention_symlink', 'retention_total_bound', 'scanner_pin', 'short_write', 'sole_activation_child', 'sole_reviewed_parent', 'source_window_member', 'stable_file', 'tracked_bytes', 'unchanged_branch', 'unknown_retention_member', 'whole_group_retention', 'whole_original_privacy'))
FAILURE_REQUIRE_OWNER = (require.__code__, require.__globals__)
FAILURE_SITE_OWNERS = (
    (read_json.__code__, read_json.__globals__, {55: 'duplicate_json'}),
    (safe_file.__code__, safe_file.__globals__, {69: 'contained_file', 73: 'owned_file', 74: 'owned_file', 78: 'stable_file'}),
    (capture.__code__, capture.__globals__, {84: 'command_bound'}),
    (verify_tracked.__code__, verify_tracked.__globals__, {91: 'tracked_bytes', 92: 'tracked_bytes'}),
    (activation_guard.__code__, activation_guard.__globals__, {97: 'hosted_lane', 98: 'hosted_lane', 99: 'hosted_lane', 100: 'hosted_lane', 104: 'sole_reviewed_parent', 105: 'sole_reviewed_parent', 106: 'activation_marker_must_be_new', 107: 'activation_marker_must_be_new', 109: 'activation_marker_regular_add', 110: 'activation_marker_regular_add', 111: 'sole_activation_child', 112: 'sole_activation_child', 113: 'clean_execution', 114: 'manifest_blob', 121: 'unchanged_branch'}),
    (read_owned.__code__, read_owned.__globals__, {140: 'private_file', 142: 'private_file_changed'}),
    (write_private.__code__, write_private.__globals__, {160: 'output_changed', 158: 'output_generation', 159: 'short_write'}),
    (validate_manifest.__code__, validate_manifest.__globals__, {170: 'manifest_schema', 171: 'manifest_acceptance', 172: 'container_context', 173: 'helper_scope', 176: 'pin_inventory', 177: 'scanner_pin', 178: 'F10_provenance', 179: 'frozen_disabled_context', 175: 'file_pins', 180: 'disabled'}),
    (command.__code__, command.__globals__, {202: 'owned_command_failed', 199: 'owned_command_timeout', 200: 'owned_command_log_limit'}),
    (acquire.__code__, acquire.__globals__, {222: 'official_input_binding', 220: 'official_HTTP_status'}),
    (image_identity.__code__, image_identity.__globals__, {226: 'image_identity', 228: 'immutable_image_identity', 229: 'immutable_image_identity'}),
    (container_identity.__code__, container_identity.__globals__, {233: 'container_identity', 235: 'owned_container_identity', 236: 'owned_container_identity', 237: 'container_mount_boundary'}),
    (remove_container.__code__, remove_container.__globals__, {248: 'cleanup_metadata_bound', 250: 'cleanup_generation', 253: 'owned_container_remains', 245: 'cleanup_inspection', 247: 'cleanup_absence_unproved'}),
    (screen_originals.__code__, screen_originals.__globals__, {263: 'inventory_scope', 280: 'whole_group_retention', 281: 'fresh_screened_output', 260: 'inventory_variant', 266: 'retention_symlink', 272: 'retention_total_bound', 274: 'binary_whole_binding', 275: 'binary_format', 277: 'unknown_retention_member', 278: 'whole_original_privacy'}),
    (main.__code__, main.__globals__, {300: 'fresh_host_paths', 311: 'original_producer_context', 320: 'exact_public_key_export', 325: 'exact_window_source', 363: 'execution_manifest_unchanged', 323: 'source_window_member'}),
)

if __name__=='__main__':
    def cancelled(_signum,_frame):raise KeyboardInterrupt()
    signals=(signal.SIGINT,signal.SIGTERM,signal.SIGALRM)
    old={sig:signal.getsignal(sig) for sig in signals}
    for sig in signals:signal.signal(sig,cancelled)
    try:main()
    except BaseException as error:
        print('ARCTIC-ACCELERATOR-BUILD-STATUS failed_unqualified',flush=True)
        try:
            phase,reason=finite_host_failure(error)
            print("ARCTIC-ACCELERATOR-BUILD-FAILURE "+phase+" "+reason,flush=True)
        except BaseException:
            pass
        raise SystemExit(1)
    finally:
        for sig,handler in old.items():signal.signal(sig,handler)
