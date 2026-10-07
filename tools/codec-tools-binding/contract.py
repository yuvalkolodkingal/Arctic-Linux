"""Pure source/identity contracts for finite tools binding, never workload actions."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import re
import stat
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / 'vendor'))
from core import (require, GuardError, Deadline, sha_file, write_json, private_dir,
    relative_member, tree_manifest, manifest_digest, image_member, failure_detail)

HERE = Path(__file__).resolve().parent
STAGES = ('discovery', 'closure', 'image')
FEDORA = '36F612DCF27F7D1A48A835E4DBFCF71C6D9F90A6'
FUSION = 'E9A491A3DE247814E7E067EAE06F8ECDD651FF2E'
BASE_ID = 'sha256:bdc8554ed5c9fc8b772c1f6756918e83672745c76512e38efdffce366effdff8'
BASE_MANIFEST = '86289176d4a4af5c9b9c9df225eed4489f075bb67549411da2e0d4c121854491'
BASE_REF = 'registry.fedoraproject.org/fedora@sha256:' + BASE_MANIFEST
ISO_BYTES = 1880244224
ISO_SHA = '84c9c88ebcbcaf69dbabf56509a9ceb2db58e5dc41d7bae12093edba12f60718'
BOOTSTRAP_TOOLS = ('usr/bin/rpm', 'usr/bin/rpmkeys', 'usr/bin/rpm2cpio', 'usr/bin/dnf5')
IDENTITY_QF = '%{NAME}\t%{EPOCHNUM}:%{VERSION}-%{RELEASE}\t%{ARCH}\t%{SOURCERPM}\t%{LICENSE}\n'
FILE_QF = '[%{FILENAMES:json}\t%{FILEMODES:json}\t%{FILEDIGESTS:json}\t%{FILELINKTOS:json}\t%{FILEFLAGS:json}\t%{FILEUSERNAME:json}\t%{FILEGROUPNAME:json}\n]'
MODE = {'discovery': (2100, 24000000000, 16000000000),
    'closure': (2100, 24000000000, 16000000000), 'image': (1800, 16000000000, 12000000000)}


def hash64(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def readable_json(path, obj):
    # Only fresh non-secret handoff data under the already guarded private
    # ancestor is shared between host UID and the capless disposable B UID0.
    # Explicit modes avoid depending on either process's ambient umask.
    path=Path(path)
    write_json(path,obj)
    st=path.lstat()
    require(stat.S_ISREG(st.st_mode) and st.st_uid==os.getuid(), 'unsafe fresh JSON handoff')
    path.chmod(0o644)
    require(stat.S_IMODE(path.stat().st_mode)==0o644, 'fresh JSON handoff mode differs')


def inputs(obj, source_sha):
    require(type(obj) is dict and set(obj) == {'tools_binding', 'preparation', 'source_sha'}, 'unknown/mixed workflow inputs')
    require(obj['tools_binding'] is True and obj['preparation'] in STAGES, 'explicit tools-only selection required')
    require(obj['source_sha'] == source_sha and re.fullmatch('[0-9a-f]{40}', source_sha), 'explicit execution source differs')
    return obj['preparation']


def registered_discovery_inputs(obj, source_sha):
    # This existing-workflow arm admits discovery only. Later stage bindings
    # are intentionally null and cannot be supplied through workflow inputs.
    denied=('same_iso_pcmanfm_diagnostic','same_iso_native_smoke','same_iso_recovery',
        'release','draft','nix_acceptance','performance_acceptance','boot_test')
    expected=set(denied)|{'tag','prerelease','codec_tools_discovery','codec_tools_source_sha'}
    require(type(obj) is dict and set(obj)==expected, 'unknown/missing/mixed registered workflow inputs')
    require(obj['codec_tools_discovery'] is True and all(obj[k] is False for k in denied),
        'explicit discovery only; build/release/VM modes must be disabled')
    require(obj['tag']=='' and type(obj['prerelease']) is bool, 'tag/metadata inputs differ')
    require(obj['codec_tools_source_sha']==source_sha and re.fullmatch('[0-9a-f]{40}',source_sha),
        'explicit registered discovery source differs')
    return 'discovery'


def binding_for(stage, binding):
    require(stage in STAGES and binding['schema'] == 'arctic-codec-tools-preparation-runtime-v1', 'stage/schema differs')
    proposal=json.loads((HERE/'proposal-preserved.json').read_text())
    require(binding['repositories']==proposal['repositories'] and binding['tool_root_goals']==proposal['tool_root_goals'],
        'fixed Fedora snapshots or exact tools-only roots differ')
    require(binding['base']['image_id'] == BASE_ID and binding['base']['platform_manifest_sha256'] == BASE_MANIFEST,
        'immutable base differs')
    require(binding['keys'] == {'fedora': FEDORA, 'fusion_preserved_not_enabled': FUSION}, 'full original keys differ')
    require(hash64(binding['execution_review_sha256']) and binding['status'] == 'SOURCE_REVIEW_BOUND',
        'BLOCKED: executable source review not bound')
    # Discovery has no version/API/closure permission. Its report must be reviewed
    # and explicitly copied into a successor binding before any other stage.
    if stage != 'discovery':
        bootstrap = binding.get('bootstrap')
        require(type(bootstrap) is dict and hash64(bootstrap.get('review_sha256')) and
            hash64(bootstrap.get('report_sha256')), 'BLOCKED: bootstrap external-review STOP')
        require(bootstrap.get('base_image_id') == BASE_ID and bootstrap.get('rpm_version') == '6.0.2' and
            bootstrap.get('dnf5_version') == '5.4.6.0', 'unsupported bootstrap version; source-reviewed successor required')
        require(set(bootstrap.get('file_hashes', {})) == set(BOOTSTRAP_TOOLS) and
            all(hash64(v) for v in bootstrap['file_hashes'].values()), 'bootstrap executable hashes unbound')
        require(bootstrap.get('metadata_cache_mode') == 'cacheonly-metadata-verified-layout-v1',
            'private cache/config API source guard unbound')
        require(hash64(bootstrap.get('API_controls_sha256')), 'bootstrap API/control proof unbound')
        require(hash64(bootstrap.get('zstd_file_sha256')), 'bootstrap zstd reader unbound')
        layout=bootstrap.get('cached_metadata_paths')
        require(type(layout) is dict and set(layout)==set(binding['repositories']), 'bootstrap cached layout unbound')
        for paths in layout.values():
            require(type(paths) is dict and set(paths)=={'repomd','primary','filelists'}, 'cached layout field identity differs')
            for path in paths.values():
                require(type(path) is str and relative_member(path).as_posix().startswith('cache/'), 'cached metadata escaped private root')
    if stage == 'image':
        closure = binding.get('closure')
        require(type(closure) is dict and all(hash64(closure.get(k)) for k in
            ('review_sha256','report_sha256','payload_manifest_sha256','before_headers_sha256','state_manifest_sha256')),
            'BLOCKED: signed closure external-review STOP')
        require(type(closure.get('artifact_id')) is int and closure['artifact_id'] > 0 and
            type(closure.get('run_id')) is int and closure['run_id'] > 0 and
            re.fullmatch('[0-9a-f]{40}', closure.get('source_sha','')), 'official reviewed closure artifact unbound')
        require(closure.get('removal_policy') == 'ONLY_SAME_NAME_UPGRADE_REPLACED' and
            closure.get('scriptless_flags') == ['--noscripts','--notriggers','--noplugins','--nosysusers'],
            'exact scriptless/removal contract differs')
    return binding


def rows(text):
    result=[]
    for line in text.splitlines():
        fields=line.split('\t')
        if fields[0]=='gpg-pubkey': continue
        require(len(fields)==5 and fields[0] and fields[2] in ('x86_64','noarch') and
            re.fullmatch(r'\d+:[^\s]+',fields[1]), 'unsupported installed/header identity row')
        if fields[0]=='gpg-pubkey': continue
        result.append(tuple(fields))
    require(result and len(result)<=3000 and len({r[:3] for r in result})==len(result), 'duplicate/empty header identities')
    require(len({r[0] for r in result})==len(result), 'multiversion/multiarch base unsupported')
    return sorted(result)


def nevra(identity):
    name,evr,arch=identity[:3]
    epoch,vr=evr.split(':',1)
    return name+'-'+('' if epoch=='0' else epoch+':')+vr+'.'+arch


def stored_goal(obj, installed, catalog, goals):
    require(type(obj) is dict and obj.get('version') == '1.0' and
        set(obj) <= {'version','rpms','groups','environments'} and
        not obj.get('groups') and not obj.get('environments'), 'unsupported stored goal schema/comps')
    require(type(obj.get('rpms')) is list and 0<len(obj['rpms'])<=400, 'stored goal bound')
    base={nevra(r):r for r in installed}
    inbound=[]; replaced=[]; seen=set(); names=set()
    for row in obj['rpms']:
        require(type(row) is dict and set(row) <= {'nevra','action','reason','repo_id','package_path','group_id'}, 'unknown goal field')
        identity=row.get('nevra')
        require(identity not in seen, 'duplicate full goal identity');seen.add(identity)
        require(row.get('reason') in ('User','Dependency','Weak Dependency','Group','External User'), 'unsupported/unknown reason')
        action=row.get('action')
        if action=='Replaced':
            require(identity in base and row.get('repo_id') == '@System' and not row.get('package_path'), 'unbound replaced header')
            replaced.append(base[identity]);continue
        require(action in ('Install','Upgrade'), 'unsupported tools removal/downgrade/reinstall/reason action')
        require(identity in catalog, 'goal absent from exact snapshots')
        item=catalog[identity]
        require(item['arch'] in ('x86_64','noarch'), 'unsupported selected tools architecture')
        require(row.get('repo_id') == '@stored_transaction('+item['repo']+')', 'goal repo differs')
        require(row.get('package_path') == './packages/'+PurePosixPath(item['location']).name, 'goal payload path differs')
        require(item['name'] not in names, 'duplicate inbound package name unsupported');names.add(item['name'])
        require(0<item['bytes']<=100000000 and hash64(item['sha256']), 'payload bound/hash unsupported')
        inbound.append({**item, 'action':action, 'reason':row['reason']})
    require(len(inbound)<=200 and sum(i['bytes'] for i in inbound)<=1000000000, 'aggregate payload cap')
    incoming={i['name']:i for i in inbound}
    for old in replaced:
        require(old[0] in incoming and incoming[old[0]]['action']=='Upgrade', 'non-upgrade removal unsupported')
    replaced_names={r[0] for r in replaced}
    for i in inbound:
        if i['action']=='Upgrade': require(i['name'] in replaced_names, 'upgrade lacks exact replaced base header')
    after={r[0]:r for r in installed}
    for i in inbound: after[i['name']]=(i['name'],i['evr'],i['arch'],i['source_RPM'],i['license'])
    for name,version in goals.items():
        require(name in after and (after[name][1][2:] if after[name][1].startswith('0:') else after[name][1])+'.'+after[name][2]==version,
            'exact root absent from final goal:'+name)
    return inbound, replaced, sorted(after.values())


def file_table(text, algorithm, users, groups):
    require(algorithm in ('md5','sha1','sha256','sha384','sha512'), 'unsupported signed digest algorithm')
    files={}
    for line in text.splitlines():
        row=[json.loads(part) for part in line.split('\t')]
        require(len(row)==7 and type(row[0]) is str and row[0].startswith('/'), 'signed file row malformed')
        path=relative_member(row[0][1:]).as_posix()
        require(path not in files and row[5] in users and row[6] in groups, 'file duplicate or unknown signed owner')
        files[path]={'mode':int(row[1]),'digest':row[2],'link':row[3],'flags':int(row[4]),
            'uid':users[row[5]],'gid':groups[row[6]],'digest_algorithm':algorithm}
    require(files and len(files)<=200000, 'header file bound')
    return files


def iso_identity(path):
    path=Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size==ISO_BYTES and sha_file(path)==ISO_SHA,
        'exact fixed ISO bytes differ')


def iso_member_listing(text):
    # xorriso -find prints literal paths enclosed in single quotes. Unsupported
    # quoting, newline names, multiple candidates or non-LiveOS paths fail.
    candidates=[]
    for line in text.splitlines():
        if not (line.startswith("'/") and line.endswith("'")): continue
        path=line[2:-1]
        require("'" not in path and '\\' not in path, 'unsupported archive path quoting')
        relative_member(path)
        if path.startswith('LiveOS/') and path.endswith(('.img','.erofs','.squashfs')): candidates.append(path)
    require(len(candidates)==1, 'current live-root member absent/ambiguous')
    return candidates[0]


def owned_container(inspect, name, source, context_sha, base_id, writable, root, source_dir):
    require(len(inspect)==1,'container inspection count')
    obj=inspect[0];host=obj['HostConfig'];config=obj['Config']
    require(obj['Name']=='/'+name and obj['Image']==base_id and
        config['Labels'].get('arctic.tools.source')==source and config['Labels'].get('arctic.tools.context')==context_sha,
        'owned container source/context/image differs')
    require(host['NetworkMode']==('bridge' if writable=='closure' else 'none') and
        host['Privileged'] is False and host['PidMode']=='' and host['IpcMode']=='private' and
        host['CapDrop']==['ALL'] and host['ReadonlyRootfs'] is (writable!='image') and
        host['PidsLimit']==512 and host['Memory']==8000000000 and host['MemorySwap']==8000000000 and host['NanoCpus']==4000000000,
        'container network/isolation/resource flags differ')
    require('no-new-privileges:true' in host['SecurityOpt'] and config['User']==('0:0' if writable=='image' else str(os.getuid())+':'+str(os.getgid())), 'container policy/user differs')
    expected={'/source':(str(source_dir),False),'/work':(str(root/'work'),True),'/input':(str(root/'inputs'),False)}
    actual={m['Destination']:(m['Source'],m['RW']) for m in obj['Mounts'] if m['Type']=='bind'}
    require(actual==expected and len([m for m in obj['Mounts'] if m['Type']=='bind'])==3 and
        all(m['Type'] in ('bind','tmpfs') for m in obj['Mounts']), 'unsupported host mount/source/writability')
    require(root.stat().st_uid==os.getuid() and stat.S_IMODE(root.stat().st_mode)==0o700 and
        stat.S_IMODE((root/'work').stat().st_mode)==(0o777 if writable=='image' else 0o700) and not (root/'work').is_symlink(),
        'private host ancestor or exact mounted scratch boundary differs')
    require(not any(k.split('=',1)[0] in ('GH_TOKEN','GITHUB_TOKEN','AWS_ACCESS_KEY_ID','HTTP_PROXY','HTTPS_PROXY')
        for k in config['Env']), 'secret/proxy environment exposed')
    return obj


def config_dump_verify(text, expected):
    rows={}
    for line in text.splitlines():
        if '=' not in line or line.lstrip().startswith('#'):continue
        key,value=line.split('=',1);key=key.strip();value=value.strip()
        require(key not in rows, 'duplicate effective config value')
        rows[key]=value
    for key,value in expected.items():
        require(key in rows, 'effective private option missing:'+key)
        actual=rows[key]
        if value in ('true','false'):
            require(actual.lower() in (('true','1') if value=='true' else ('false','0')), 'effective private bool differs:'+key)
        elif value=='never':require(actual in ('never','-1'), 'effective metadata expiry differs')
        elif actual.startswith('['):
            require(json.loads(actual)==[value], 'effective private list differs:'+key)
        else:require(actual==value, 'effective private config differs:'+key)
    return rows
