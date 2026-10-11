#!/usr/bin/env python3
"""Fresh sole-first-marker admission for exact accepted current UI evidence."""
import hashlib,types,sys,json,os,re,stat,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BASE='44c789f068a49d642b5122288ccccca767f1ddc0'
BRANCH='codex/final-installed-ui-retained-evidence-20261011'
MARKER='.github/final-installed-ui-retained-evidence-20261011.activate'
WORKFLOW='Final installed UI with strict retained originals'
ADDITIONS={'tools/final-installed-ui-private-evidence/originals.py', 'tools/final-installed-ui-private-evidence/observer.py', 'tools/final-installed-ui-private-evidence/execution-manifest.json', 'tools/final-installed-ui-retained-evidence/run.py', 'tools/final-installed-ui-private-evidence/README.md', 'tools/final-installed-ui-private-evidence/match-diagnostic.py', '.github/workflows/final-installed-ui-retained-evidence-20261011.yml', 'tools/final-installed-ui-retained-evidence/common.py', 'tools/final-installed-ui-retained-evidence/execution-manifest.json', 'tools/final-installed-ui-retained-evidence/README.md', 'tools/final-installed-ui-private-evidence/test_observer.py', 'tools/final-installed-ui-retained-evidence/test_composition.py'}
FILES={'tools/final-installed-ui-private-evidence/originals.py', 'tools/final-installed-ui-settings-readiness/run.py', 'tools/final-installed-ui-retained-evidence/run.py', 'tools/final-installed-ui-private-evidence/README.md', 'tools/final-installed-ui-private-evidence/match-diagnostic.py', 'tools/lib/vmtest.py', 'tools/native-functional/fetch-image.py', 'tools/performance/producer-receipt.py', 'tools/final-installed-ui-retained-evidence/test_composition.py', 'tools/native-functional/screen-evidence.py', 'tools/performance/prepare-vm-tools.sh', 'tools/final-installed-ui-settings-readiness/execution-manifest.json', '.github/workflows/final-installed-ui-settings-readiness-20261011.yml', 'tools/final-installed-ui-private-evidence/test_observer.py', 'tools/final-installed-ui-private-evidence/observer.py', 'tools/lib/container.sh', '.github/workflows/final-installed-ui-retained-evidence-20261011.yml', 'tools/final-installed-ui-retained-evidence/common.py', 'tools/final-installed-ui-settings-readiness/compose.py', 'tools/final-installed-ui-settings-readiness/common.py', 'tools/final-installed-ui-private-evidence/execution-manifest.json', 'tools/test-install.sh', 'tools/final-installed-ui-retained-evidence/README.md', 'tools/final-installed-ui-settings-readiness/guest.py'}
SOURCE_FILES={'shell/Wallpapers.qml', 'shell/shell.qml', 'shell/scripts/wallpapers.py', 'shell/Launcher.qml', 'shell/UpdateStatus.js', 'settings/pages/AppearancePage.qml', 'shell/getapps/ChooserPage.qml', 'shell/getapps/RemovePage.qml', 'settings/shell.qml', 'dotfiles/.local/bin/arctic-shell-ipc', 'settings/Backend.qml', 'profiles/ci/offline.toml', 'shell/getapps/GetApps.qml', 'dotfiles/.local/bin/arctic-theme', 'shell/LockScreen.qml', 'settings/Main.qml', 'settings/SearchIndex.js', 'shell/UpdateService.qml', 'shell/scripts/apps.py', 'tools/native-functional/native_smoke.py'}
COMPONENT_BINDING={'source_sha': '02b1f3f8c1d1fe9b1ce1c6339dc674990d39eaaf', 'source_tree': '5be52b521d189e668c48a0fa45241e847e1886f4', 'source_payload_sha256': '76794e414ad44effacbb267063b346929af23a747ae78cece90291cb85b437ee', 'source_author_sha256': '519c3a2f377cb9858826001d024f1caec670d97f9e745f6e0fcb99321dc6ef1b', 'independent_receipt_sha256': '0a55e3290b5c3a7de23d1b5fccfcab5b3677e9915fae70822607b8cdf72c5bb2', 'source_manifest_sha256': '883087df4c2410193ce001df73aadbf7fdebd4df661dcf2e0c580cd8bed5203e'}
COMPONENT_TEST_SHA256='84eef2cf185d669536243a79a6cc82a40e109f6b565c58364dc0fd9fb7544b2b'
ORIGINAL_MANIFEST_SHA256='00367506b0d0de2083ccd95fd42a7336e769210e51ab150f33a564f2f092abe7'
ORIGINAL_PREFIX='tools/final-installed-ui-settings-readiness/'
COMPONENT_PREFIX='tools/final-installed-ui-private-evidence/'
IMAGE={'archive_bytes': 1929907101, 'archive_sha256': '3a8132aa4578fdb62b2aa1e3bf5c340229f1a483678d03ddf2c565fb39afadcd', 'artifact_id': 11689591362, 'bytes': 1929719808, 'name': 'Arctic-Linux-1.2-candidate-38102474066-1-x86_64.iso', 'producer_mode': 'frozen-external-paired-v1', 'producer_receipt_sha256': '3034ea88d4ba1d1e434942f90c42b8057d3667ad2e7f6ee739b895ebdfc86d1d', 'run_id': 38102474066, 'sha256': '807eaaa64ab8480ec2b18bc8434fd5e37d82c41b73a3e0a6f002c35d152ba54c', 'source_sha': '326690f173d4dc4f049f43e046c8380e66825a07'}

def require(value, message):
    if not value:
        raise RuntimeError(message)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True, timeout=30).strip()

def load(path, name, expected=None):
    raw=regular(path,1024*1024)
    if expected is not None:require(hashlib.sha256(raw).hexdigest()==expected,'Loaded pinned source bytes differ')
    module=types.ModuleType(name);module.__file__=str(path);sys.modules[name]=module
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module

def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON field')
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))

def regular(path, limit):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= limit,
                'Missing/nonregular/oversized owned file')
        with os.fdopen(fd,'rb',closefd=False) as stream:data=stream.read(limit+1)
        after=os.fstat(fd)
        require(len(data)==info.st_size and (after.st_dev,after.st_ino,after.st_size)==
                (info.st_dev,info.st_ino,info.st_size),'Acquired original changed during read')
        return data
    finally:os.close(fd)

def guard(value, source, inputs=None):
    manifest(value, True)
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and os.environ.get('GITHUB_REPOSITORY') == 'yuvalkolodkingal/Arctic-Linux'
            and os.environ.get('GITHUB_REF') == 'refs/heads/' + BRANCH
            and os.environ.get('GITHUB_EVENT_NAME') == 'push' and os.environ.get('GITHUB_WORKFLOW') == WORKFLOW
            and os.environ.get('GITHUB_RUN_ATTEMPT') == '1', 'Requires owned first hosted UI push')
    event = strict_json(regular(Path(os.environ['GITHUB_EVENT_PATH']), 1024*1024))
    head = git('rev-parse', 'HEAD'); prep = git('rev-parse', 'HEAD^')
    require(git('rev-list', '--parents', '-n', '1', head).split() == [head, prep]
            and head == os.environ.get('GITHUB_SHA') == event.get('after') and prep == event.get('before')
            and regular(ROOT / MARKER, 41) == (prep + '\n').encode()
            and git('ls-tree', head, '--', MARKER).split()[0] == '100644'
            and git('diff', '--no-renames', '--name-status', prep, head) == 'A\t' + MARKER,
            'Requires sole first marker ADD')
    require(git('rev-list', '--parents', '-n', '1', prep).split() == [prep, BASE], 'Preparation base differs')
    paths = set(git('diff', '--no-renames', '--name-only', BASE, prep).splitlines())
    require(paths == ADDITIONS, 'Preparation scope differs')
    require(set(git('diff', '--no-renames', '--name-status', BASE, prep).splitlines()) ==
            {'A\t'+name for name in ADDITIONS}, 'Preparation modes/change kinds differ')
    expected_raw = set()
    for name in ADDITIONS:
        require(not git('ls-tree', BASE, '--', name), 'Preparation new path already exists')
        entry = git('ls-tree', prep, '--', name).split()
        require(len(entry) == 4 and entry[:2] == ['100644', 'blob'] and entry[3] == name,
                'Preparation regular mode/type differs')
        expected_raw.add(':000000 100644 ' + '0'*40 + ' ' + entry[2] + ' A\t' + name)
    require(not git('ls-tree', BASE, '--', MARKER) and not git('ls-tree', prep, '--', MARKER),
            'Preparation marker must be absent')
    require(set(git('diff', '--raw', '--no-abbrev', '--no-renames', BASE, prep).splitlines()) == expected_raw,
            'Preparation raw modes/change kinds differ')
    require(digest_file(ROOT/'tools/final-installed-ui-private-evidence/test_observer.py') == COMPONENT_TEST_SHA256,
            'Accepted UI component fixture bytes differ')
    require(not git('status', '--porcelain') and not subprocess.check_output(
            ['git', '-C', str(source), 'status', '--porcelain'], text=True), 'Tracked checkout dirty')
    require(subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
            == value['image']['source_sha'], 'Image source checkout differs')
    for group, tree in (('execution_files', ROOT), ('source_files', source)):
        for name, expected in value[group].items():
            require(digest_file(tree/name) == expected, 'Pinned execution/source bytes differ')
    fetch = load(ROOT/'tools/native-functional/fetch-image.py', 'final_bios_fetch', value['execution_files']['tools/native-functional/fetch-image.py'])
    image = value['image']
    run = fetch.api('/actions/runs/'+str(image['run_id']))
    artifact = fetch.api('/actions/artifacts/'+str(image['artifact_id']))
    fetch.validate(image, run, artifact)
    jobs = fetch.api('/actions/runs/'+str(image['run_id'])+'/jobs?filter=all&per_page=100')
    require(jobs['total_count'] == len(jobs['jobs']), 'Producer job inventory incomplete')
    fetch.validate_boot_steps(image, jobs['jobs'])
    if inputs is not None:
        image = inputs/'iso'/value['image']['name']
        require(image.is_file() and not image.is_symlink() and image.stat().st_size == value['image']['bytes']
                and digest_file(image) == value['image']['sha256'], 'Actual ISO bytes differ')
    return dict(image=value['image'], execution_sha=head, release_acceptance=False)

def digest_file(path):
    require(path.is_file() and not path.is_symlink(), 'Pinned source must be regular')
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1024*1024), b''): value.update(part)
    return value.hexdigest()

def exclusive(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream: stream.write(data)


def manifest(value,operational=False):
    require(type(value)is dict and set(value)=={'schema','ready','release_acceptance','image','execution_files',
        'source_files','ui_seconds','max_png','install_timeout','harness_seconds','install_network','boot_network',
        'component_binding','original_manifest_sha256'},'Fresh UI manifest schema differs')
    require(value['schema']=='arctic-final-ui-retained-evidence-v1'and type(value['ready'])is bool
        and value['release_acceptance']is False,'Fresh UI readiness/acceptance differs')
    if operational:require(value['ready']is True,'Fresh UI evidence lane remains disabled')
    require(value['image']==IMAGE and type(value['image'])is dict and set(value['image'])==set(IMAGE)
        and all(type(value['image'][k])is type(v)for k,v in IMAGE.items()),'Original exact F10 image differs')
    require(value['ui_seconds']==720 and type(value['ui_seconds'])is int and value['max_png']==16
        and type(value['max_png'])is int and value['install_timeout']==2400 and type(value['install_timeout'])is int
        and value['harness_seconds']==4200 and type(value['harness_seconds'])is int
        and value['install_network']==value['boot_network']=='offline','Original UI/install bounds differ')
    require(type(value['execution_files'])is dict and set(value['execution_files'])==FILES
        and type(value['source_files'])is dict and set(value['source_files'])==SOURCE_FILES,'Fresh UI closure differs')
    for group in('execution_files','source_files'):
        require(all(type(n)is str and not Path(n).is_absolute()and '..'not in Path(n).parts and n==Path(n).as_posix()
            and type(d)is str and re.fullmatch('[0-9a-f]{64}',d)for n,d in value[group].items()),'Fresh UI pin differs')
    require(type(value['component_binding'])is dict and value['component_binding']==COMPONENT_BINDING
        and value['original_manifest_sha256']==ORIGINAL_MANIFEST_SHA256,'Accepted UI component/original binding differs')
    return value
