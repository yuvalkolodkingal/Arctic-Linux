#!/usr/bin/env python3
"""Guarded CI-only tools binding. No phase runs during source/host tests."""
from pathlib import Path
import argparse
import configparser
import hashlib
import json
import os
import shutil
import stat
import subprocess
import time
import xml.etree.ElementTree as ET
import contract as c
from contract import require, sha_file, write_json, private_dir, tree_manifest, manifest_digest
from cli import bounded_host, official_metadata
from core import verify_signature_result, check_artifact, reap_owned, close_observed, PhaseFailure
from cpio import unpack

HERE=Path(__file__).resolve().parent


def git(root,*args):
    env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
    return subprocess.check_output(['git','-C',str(root),*args],env=env,text=True,timeout=10).strip()


def source_guard(expected):
    root=HERE.parents[1];pins=json.loads((HERE/'execution-pins.json').read_text())
    require(pins.get('schema')=='arctic-codec-tools-preparation-execution-v1' and
        len(pins.get('files',{}))>=10 and 'tools/codec-tools-binding/prepare.py' in pins['files'] and
        '.github/workflows/iso.yml' in pins['files'],'missing/empty execution map')
    require(git(root,'rev-parse','HEAD')==expected and not git(root,'status','--porcelain','--untracked-files=no'), 'dirty/wrong execution source')
    for logical,row in pins['files'].items():
        path=root/logical
        require(path.is_file() and not path.is_symlink() and sha_file(path)==row['sha256'] and
            not path.stat().st_mode & 0o022, 'changed/unsafe execution source:'+logical)
        index=git(root,'ls-files','--stage','--',logical).split()
        require(len(index)>=4 and index[0]==row['git_mode'],'canonical Git mode differs')
    return pins


def invoke(argv, deadline, path, limit=300, monitor=None):
    budget=deadline.remaining(limit);end=time.monotonic()+budget
    work_end=end-min(5.,budget/2.)
    stream=None;process=None;primary=None;secondary=[]
    try:
        stream=path.open('xb')
        process=subprocess.Popen(argv,stdout=stream,stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,start_new_session=True)
        while process.poll() is None:
            require(time.monotonic()<work_end,'bounded tools command timeout')
            require(path.stat().st_size<=1000000,'tools command log cap')
            if monitor:monitor()
            time.sleep(.05)
        require(time.monotonic()<=work_end and process.returncode==0,'tools command failed/deadline')
        require(path.stat().st_size<=1000000,'post-exit tools log cap')
        if monitor:monitor()
    except BaseException as error:
        primary=error;reap_owned(process,end,secondary)
    finally:close_observed(stream,secondary)
    try:
        write_json(path.with_name(path.name+'.phase.json'),{'argv':argv,'exit_status':process.returncode if process else None,
            'primary_failure':c.failure_detail(primary) if primary else None,'cleanup_failures':secondary,'phase_end_monotonic':end})
    except Exception as error:secondary.append(c.failure_detail(error))
    if primary or secondary:raise PhaseFailure(primary,secondary) from primary
    return path.read_text(errors='strict')


def safe_tree(root, maximum):
    total=0;count=0
    for path in Path(root).rglob('*'):
        st=path.lstat();count+=1
        require(not stat.S_ISLNK(st.st_mode) and (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)),'linked/special scratch member')
        if path.is_file():total+=st.st_size
        require(total<=maximum and count<=500000,'scratch tree byte/member cap')
    return total


def context(root):
    root=private_dir(root,Path(os.environ['RUNNER_TEMP']).resolve())
    obj=json.loads((root/'context.json').read_text())
    require(obj['run']==os.environ['GITHUB_RUN_ID'] and obj['attempt']==os.environ['GITHUB_RUN_ATTEMPT'] and
        obj['uid']==os.getuid() and obj['gid']==os.getgid() and
        obj['host_boot']==Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'stale owner/run/boot')
    source_guard(obj['source'])
    require(sha_file(HERE/'runtime-binding.json')==obj['binding_sha'],'binding changed')
    return root,obj


def preflight(root, source):
    root=private_dir(root,Path(os.environ['RUNNER_TEMP']).resolve(),fresh=True)
    for name in ('evidence','work','inputs','outputs','host-docker-config'): (root/name).mkdir(mode=0o700)
    (root/'inputs').chmod(0o755)
    passed=False;failure=None;started=time.monotonic()
    try:
        source_guard(source)
        require(not any(os.environ.get(k) for k in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH','DOCKER_CONFIG')),
            'Docker host/context/config override not authorized')
        stage=c.registered_discovery_inputs(json.loads(os.environ['TOOLS_ALL_INPUTS']),source)
        require(os.environ['GITHUB_EVENT_NAME']=='workflow_dispatch' and os.environ['GITHUB_SHA']==source,'explicit same-source dispatch required')
        binding=json.loads((HERE/'runtime-binding.json').read_text());c.binding_for(stage,binding)
        review=HERE/binding['execution_review_file']
        require(review.is_file() and not review.is_symlink() and sha_file(review)==binding['execution_review_sha256'],'execution review bytes missing')
        # Cross-phase reports are actual files in reviewed source, not caller inputs.
        if stage=='metadata':
            actual=binding['metadata_prerequisite']
            for field,key in (('report_file','report_sha256'),('review_file','review_sha256')):
                require(sha_file(HERE/actual[field])==actual[key], 'actual discovery report/review bytes differ')
        if stage in ('closure','image'):
            for filename,key in (('bootstrap-review.json','review_sha256'),('bootstrap-report.json','report_sha256')):
                require(sha_file(HERE/filename)==binding['bootstrap'][key],'bootstrap report/review source differs')
        if stage=='image':
            for filename,key in (('closure-review.json','review_sha256'),('closure-report.json','report_sha256')):
                require(sha_file(HERE/filename)==binding['closure'][key],'closure report/review source differs')
            meta=official_metadata('actions/artifacts/'+str(binding['closure']['artifact_id']),os.environ.get('GH_TOKEN',''))
            require(meta['id']==binding['closure']['artifact_id'] and not meta['expired'] and
                meta['workflow_run']['id']==binding['closure']['run_id'] and
                meta['workflow_run']['head_sha']==binding['closure']['source_sha'],'official closure provenance differs')
            write_json(root/'evidence/official-closure-artifact.json',meta)
            iso=official_metadata('actions/artifacts/11434226349',os.environ.get('GH_TOKEN',''));check_artifact(iso)
            write_json(root/'evidence/official-ISO-artifact.json',iso)
        if stage=='image':
            # Sole fresh writable mount for disposable container UID0; every
            # host path above it remains private0700. A uses the host UID and
            # keeps all scratch paths0700. No existing host data is exposed.
            (root/'work').chmod(0o777)
        initial=shutil.disk_usage(root).free
        require(initial>=c.MODE[stage][1],'initial CI disk minimum')
        ctx={'source':source,'stage':stage,'run':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],
            'uid':os.getuid(),'gid':os.getgid(),'host_boot':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'started':started,'initial_free':initial,'binding_sha':sha_file(HERE/'runtime-binding.json')}
        write_json(root/'context.json',ctx)
        with Path(os.environ['GITHUB_ENV']).open('a') as env:
            env.write('TOOLS_ROOT='+str(root)+'\n')
            if stage=='image':
                env.write('TOOLS_CLOSURE_RUN='+str(binding['closure']['run_id'])+'\n')
                env.write('TOOLS_CLOSURE_ARTIFACT='+str(binding['closure']['artifact_id'])+'\n')
        passed=True
    except Exception as error:
        failure=c.failure_detail(error);raise
    finally:write_json(root/'evidence/preflight.json',{'passed':passed,'failure':failure,'actual_work':'UNRUN','source':source})


class Session:
    def __init__(self,root,ctx,binding):
        self.root,self.ctx,self.binding=root,ctx,binding
        self.deadline=c.Deadline(ctx['started'],c.MODE[ctx['stage']][0]);self.deadline.end-=360
        self.name='arctic-tools-'+ctx['run']+'-'+ctx['attempt']+'-'+ctx['stage']
        self.count=0;self.created=False;self.committed=None
    def limits(self):
        self.deadline.remaining(1)
        free=shutil.disk_usage(self.root).free
        require(free>=1000000000 and self.ctx['initial_free']-free<=c.MODE[self.ctx['stage']][2],'owned scratch/global disk reserve')
        packages=self.root/'work/goal/packages'
        if packages.exists():
            files=list(packages.iterdir())
            require(len(files)<=200 and all(p.is_file() and not p.is_symlink() and p.stat().st_size<=100000000 for p in files) and
                sum(p.stat().st_size for p in files)<=1000000000,'live selected payload byte/count bound')
    def docker(self,args):
        return ['/usr/bin/docker','--config',str(self.root/'host-docker-config'),'--host','unix:///var/run/docker.sock',*args]
    def call(self,argv,tag,timeout=180):
        if argv[0]=='docker':argv=self.docker(argv[1:])
        self.limits();self.count+=1
        return invoke(argv,self.deadline,self.root/'evidence'/('%03d-'%self.count+tag+'.log'),timeout,self.limits)
    def inspect(self):
        obj=json.loads(self.call(['docker','inspect',self.name],'inspect',15))
        c.owned_container(obj,self.name,self.ctx['source'],sha_file(self.root/'context.json'),c.BASE_ID,self.ctx['stage'],self.root,HERE)
        return obj[0]
    def create(self):
        self.call(['docker','pull','--platform=linux/amd64',c.BASE_REF],'immutable-base-pull',240)
        image=json.loads(self.call(['docker','image','inspect',c.BASE_ID],'immutable-base-inspect',15))[0]
        config=json.loads((HERE/'sources/tools-base-amd64-config.json').read_text())
        require(image['Id']==c.BASE_ID and image['Architecture']=='amd64' and image['Os']=='linux' and
            image['RootFS']['Layers']==config['rootfs']['diff_ids'],'base image/config/diff identities differ')
        write_json(self.root/'evidence/actual-base-image.json',image)
        stage=self.ctx['stage']
        argv=['docker','create','--pull=never','--name',self.name,'--user',
            '0:0' if stage=='image' else str(os.getuid())+':'+str(os.getgid()),
            '--label','arctic.tools.source='+self.ctx['source'],'--label','arctic.tools.context='+sha_file(self.root/'context.json'),
            '--cap-drop=ALL','--security-opt=no-new-privileges:true','--pids-limit=512',
            '--memory=8000000000','--memory-swap=8000000000','--cpus=4','--ipc=private','--network','bridge' if stage in ('metadata','closure') else 'none',
            '--env','HOME=/work/home','--env','XDG_CONFIG_HOME=/work/config','--env','LANG=C.UTF-8',
            '--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=268435456',
            '--mount','type=bind,src='+str(HERE)+',dst=/source,readonly',
            '--mount','type=bind,src='+str(self.root/'work')+',dst=/work',
            '--mount','type=bind,src='+str(self.root/'inputs')+',dst=/input,readonly',
            '--entrypoint','/usr/bin/sleep']
        if stage!='image':argv+=['--read-only']
        if stage=='metadata':
            aliases=self.root/'inputs/empty-aliases';aliases.mkdir(mode=0o755)
            for relative in ('config/empty-cli-plugins','config/dnf5/aliases.d'):
                (self.root/'work'/relative).mkdir(mode=0o755,parents=True)
            argv+=['--env','DNF5_PLUGINS_DIR=/work/config/empty-cli-plugins']
            for target in ('/usr/share/dnf5/aliases.d','/etc/dnf/dnf5-aliases.d'):
                argv+=['--mount','type=bind,src='+str(aliases)+',dst='+target+',readonly']
        argv += [c.BASE_ID,str(c.MODE[stage][0])]
        # A successful daemon side effect can precede a phase-log failure.
        # Track the attempted acquisition first; cleanup may remove only a
        # subsequently inspected exact owned resource, never an unknown name.
        self.created=True
        self.call(argv,'create',30);self.inspect()
        self.call(['docker','start',self.name],'start',15)
    def exec(self,argv,tag,timeout=120):
        self.inspect()
        return self.call(['docker','exec',self.name,*argv],tag,timeout)
    def binary(self,argv,destination,tag,maximum=4000000000,timeout=120):
        self.inspect();self.limits()
        budget=self.deadline.remaining(timeout);end=time.monotonic()+budget
        work_end=end-min(5.,budget/2.)
        error_path=self.root/'evidence'/(tag+'.stderr.log')
        primary=None;secondary=[];child=None;out=None;err=None
        try:
            out=destination.open('xb')
            err=error_path.open('xb')
            child=subprocess.Popen(self.docker(['exec',self.name,*argv]),stdout=out,stderr=err,
                stdin=subprocess.DEVNULL,start_new_session=True)
            while child.poll() is None:
                require(time.monotonic()<work_end,'bounded binary reader timeout')
                self.limits()
                require(destination.stat().st_size<=maximum and error_path.stat().st_size<=1000000,'binary byte cap')
                time.sleep(.05)
            require(time.monotonic()<=work_end and child.returncode==0,'binary reader failed/deadline')
            require(destination.stat().st_size<=maximum and error_path.stat().st_size<=1000000,'post-exit binary byte cap')
        except BaseException as error:
            primary=error;reap_owned(child,end,secondary)
        finally:
            close_observed(out,secondary);close_observed(err,secondary)
        try:
            write_json(self.root/'evidence'/(tag+'.binary.json'),{'argv':self.docker(['exec',self.name,*argv]),
                'exit_status':child.returncode if child else None,'maximum':maximum,
                'primary_failure':c.failure_detail(primary) if primary else None,'cleanup_failures':secondary,
                'actual_bytes':destination.stat().st_size if destination.exists() else None})
        except Exception as error:secondary.append(c.failure_detail(error))
        if primary or secondary:raise PhaseFailure(primary,secondary) from primary
    def copy(self,inside,destination,tag):
        require(not destination.exists() and not destination.is_symlink(),'stale copied base path')
        self.inspect();self.call(['docker','cp',self.name+':'+inside,str(destination)],tag,60)
    def copy_os_release(self,destination,tag):
        # This one immutable-base identity is a Fedora relative alias. Only
        # its fixed source is resolved; state trees and other copies retain
        # their original type-preserving route and manifest checks.
        require(not destination.exists() and not destination.is_symlink(),'stale copied OS release path')
        self.inspect();self.call(['docker','cp','-L',self.name+':/etc/os-release',str(destination)],tag,60)
        require(destination.is_file() and not destination.is_symlink(),'resolved OS release is not a regular file')
    def copy_binary(self,relative,destination,tag):
        require(relative in (*c.BOOTSTRAP_TOOLS,'usr/bin/zstd'),'unapproved immutable-base executable data path')
        require(not destination.exists() and not destination.is_symlink(),'stale executable data path')
        self.inspect()
        self.call(['docker','cp','-L',self.name+':/'+relative,str(destination)],tag,60)
        require(destination.is_file() and not destination.is_symlink(),'resolved executable body unavailable')
    def cleanup(self):
        if self.created:
            # Cleanup uses only the remaining reserved global interval. It still
            # verifies complete labels/image/isolation before one owned rm.
            deadline=c.Deadline(self.ctx['started'],c.MODE[self.ctx['stage']][0]);deadline.end-=300
            raw=invoke(self.docker(['inspect',self.name]),deadline,self.root/'evidence/cleanup-inspect.log',15)
            c.owned_container(json.loads(raw),self.name,self.ctx['source'],sha_file(self.root/'context.json'),
                c.BASE_ID,self.ctx['stage'],self.root,HERE)
            invoke(self.docker(['rm','-f',self.name]),deadline,self.root/'evidence/cleanup-owned-container.log',15)
            self.created=False


def header_rows(session,root='/'):
    result=session.exec(['/usr/bin/rpm','--noplugins','--root',root,'--define','_dbpath /usr/lib/sysimage/rpm',
        '-qa','--qf',c.IDENTITY_QF],'header-identities',30)
    return c.rows(result)


def discovery(session):
    installed=header_rows(session)
    versions={}
    for exe,flag in (('/usr/bin/rpm','--noplugins'),('/usr/bin/dnf5','--no-plugins')):
        versions[exe]=session.exec([exe,flag,'--version'],'discovery-version-'+Path(exe).name,15)
    hashes={}
    for relative in c.BOOTSTRAP_TOOLS:
        path=session.root/'work'/('bootstrap-'+Path(relative).name)
        session.copy_binary(relative,path,'bootstrap-data-'+Path(relative).name)
        require(path.is_file() and not path.is_symlink(),'bootstrap executable alias needs explicit source-reviewed route')
        hashes[relative]={'sha256':sha_file(path),'bytes':path.stat().st_size}
    write_json(session.root/'outputs/bootstrap-report.json',{'status':'DISCOVERY_ONLY_EXTERNAL_REVIEW_STOP',
        'base_image_id':c.BASE_ID,'headers':installed,'versions':versions,'file_identities':hashes,
        'resolve_download_transaction':False,'member_work':'UNRUN','observed_only':True})
    # No bootstrap identity is automatically written into runtime binding.


def metadata_identity_guard(session):
    bound=session.binding['metadata_prerequisite']
    for field,key in (('report_file','report_sha256'),('review_file','review_sha256')):
        path=HERE/bound[field]
        require(path.is_file() and not path.is_symlink() and sha_file(path)==bound[key], 'reviewed discovery bytes differ')
    report=json.loads((HERE/bound['report_file']).read_text())
    review=json.loads((HERE/bound['review_file']).read_text())
    require(report['status']=='DISCOVERY_ONLY_EXTERNAL_REVIEW_STOP' and report['observed_only'] is True and
        report['resolve_download_transaction'] is False and report['member_work']=='UNRUN' and
        report['base_image_id']==c.BASE_ID, 'actual discovery STOP scope differs')
    require(review['status']=='PASS_ACTUAL_DISCOVERY_OBSERVATIONS_EXTERNAL_REVIEW_STOP' and
        review['run_id']==bound['run_id'] and review['source']==bound['source'], 'independent actual review scope differs')
    require({name:row['sha256'] for name,row in report['file_identities'].items()}==bound['file_hashes'], 'actual body receipt binding differs')
    for relative,digest in bound['file_hashes'].items():
        path=session.root/'work'/('metadata-guard-'+Path(relative).name)
        session.copy_binary(relative,path,'metadata-base-body-'+Path(relative).name)
        require(sha_file(path)==digest and path.stat().st_size==report['file_identities'][relative]['bytes'], 'actual base body changed')
    dnf_body=(session.root/'work/metadata-guard-dnf5').read_bytes()
    require(all(path.encode()+b'\x00' in dnf_body for path in ('/usr/share/dnf5/aliases.d','/etc/dnf/dnf5-aliases.d')),
        'actual DNF body alias-route literals unsupported; no metadata permission')
    require(header_rows(session)==[tuple(row) for row in report['headers']], 'reviewed base ordinary headers changed')
    return report


def metadata_cache_receipts(work, repositories, deadline, monitor):
    # This observes exact private cache representations without installing or
    # solving. Plain XML and compressed bytes have separately pinned hashes.
    cache=work/'cache';entries=[];total=0
    require(cache.is_dir() and not cache.is_symlink(), 'private metadata cache missing/linked')
    for index,path in enumerate(cache.rglob('*')):
        require(index<5000, 'private cache member bound')
        deadline.remaining(30);monitor();st=path.lstat()
        require(not stat.S_ISLNK(st.st_mode) and (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)), 'special/linked private cache entry')
        if stat.S_ISREG(st.st_mode):
            total+=st.st_size
            require(st.st_size<=1000000000 and total<=4000000000 and len(entries)<1000, 'metadata cache receipt bound')
            entries.append({'path':path.relative_to(work).as_posix(),'bytes':st.st_size,'sha256':sha_file(path)})
            deadline.remaining(30);monitor()
    entries.sort(key=lambda row:row['path'])
    matches={}
    for repo,expected in repositories.items():
        matches[repo]={}
        for kind in ('repomd','primary','filelists'):
            identities=[('repomd-XML',expected['repomd_bytes'],expected['repomd_sha256'])] if kind=='repomd' else [
                ('compressed',expected['metadata'][kind]['bytes'],expected['metadata'][kind]['sha256']),
                ('plain-XML',expected['metadata'][kind]['open_bytes'],expected['metadata'][kind]['open_sha256'])]
            matches[repo][kind]=[{**row,'representation':representation} for row in entries
                for representation,size,digest in identities if row['bytes']==size and row['sha256']==digest]
    return {'private_cache_entries':entries,'matching_snapshot_files':matches,'total_bytes':total,
        'source_of_trust':'Exact already reviewed HTTPS Fedora repomd/compressed/open XML hash and size snapshots; metadata signatures not claimed.'}


def metadata(session):
    report=metadata_identity_guard(session)
    before,config=prepare_root(session)
    # All three alias routes are empty before the first DNF process. The two
    # compiled system routes are exact read-only bind overlays in inspect().
    routes=[]
    for relative in ('inputs/empty-aliases','work/config/empty-cli-plugins','work/config/dnf5/aliases.d'):
        path=session.root/relative
        require(path.is_dir() and not path.is_symlink() and not any(path.iterdir()), 'CLI plugin/alias route is not empty')
        st=path.stat();routes.append({'private_relative_path':relative,'uid':st.st_uid,'gid':st.st_gid,
            'mode':oct(stat.S_IMODE(st.st_mode)),'empty':True})
    isolated=session.exec(['/usr/bin/dnf5','--no-plugins','--version'],'isolated-CLI-version',30)
    expected='dnf5 version 5.4.6.0\ndnf5 plugin API version 2.0\nlibdnf5 version 5.4.6.0\nlibdnf5 plugin API version 2.2\n'
    require(isolated==expected, 'isolated version/plugin observation differs; no metadata permission')
    effective=session.exec(dnf_args('--dump-main-config'),'isolated-private-config-before-metadata',30)
    effective_rows=c.config_dump_verify(effective,config)
    require(effective_rows.get('config_file_path')=='/work/config/dnf.conf', 'effective explicit config file differs')
    zstd=session.root/'work/metadata-zstd-body'
    session.copy_binary('usr/bin/zstd',zstd,'metadata-zstd-body')
    zstd_receipt={'sha256':sha_file(zstd),'bytes':zstd.stat().st_size}
    require(0<zstd_receipt['bytes']<=100000000, 'zstd body empty/overbound')
    installed=header_rows(session,'/work/installroot')
    require(installed==[tuple(row) for row in report['headers']], 'copied private RPM headers differ')
    # Metadata-only network work. No do/store/goal/package or key import route.
    session.exec(dnf_args('makecache',cacheonly='none'),'fixed-Fedora-metadata-only-cache',600)
    proof=metadata_cache_receipts(session.root/'work',session.binding['repositories'],session.deadline,session.limits)
    write_json(session.root/'evidence/metadata-cache-receipts.json',proof)
    for repo,kinds in proof['matching_snapshot_files'].items():
        for kind,rows in kinds.items():
            require(rows and len({row['representation'] for row in rows})==len(rows),
                'fixed snapshot missing/ambiguous in actual cache:'+repo+'/'+kind)
    final_config=session.exec(dnf_args('--dump-main-config'),'isolated-private-config-after-metadata',30)
    require(final_config==effective, 'effective private config changed during metadata-only work')
    require(header_rows(session,'/work/installroot')==installed, 'metadata-only work changed private RPM headers')
    for relative,digest in before.items():
        require(manifest_digest(tree_manifest(session.root/'work/installroot'/relative))==digest, 'metadata-only work changed copied state')
    require(not (session.root/'work/goal/packages').exists() and not (session.root/'work/goal/transaction.json').exists(), 'unexpected package/goal output')
    for relative in ('inputs/empty-aliases','work/config/empty-cli-plugins','work/config/dnf5/aliases.d'):
        require(not any((session.root/relative).iterdir()), 'plugin/alias route changed during metadata-only work')
    write_json(session.root/'outputs/metadata-report.json',{'status':'METADATA_CONFIG_EXTERNAL_REVIEW_STOP',
        'actual_discovery_report_sha256':session.binding['metadata_prerequisite']['report_sha256'],
        'actual_discovery_review_sha256':session.binding['metadata_prerequisite']['review_sha256'],
        'base_image_id':c.BASE_ID,'zstd_executable_body_receipt':zstd_receipt,'isolated_CLI_version':isolated,
        'CLI_plugin_and_alias_routes_before_after_empty':routes,
        'effective_private_config':effective,'effective_private_config_rows':effective_rows,'metadata_cache':proof,
        'private_state_before_and_after_equal':before,'before_headers':installed,'only_network_reads':'fixed Fedora metadata',
        'RPM_payload_downloads':False,'solve_store_transaction_scripts':False,'ISO_member_work':'UNRUN',
        'Python_libdnf5_API_controls':'UNRUN_until_separately_reviewed_signed_tools_image',
        'body_receipt_limit':'Source-calculated inert zstd receipt; body not exported. No package-signature or ELF-format claim.',
        'system_alias_route_binding':'Both expected compiled route literals present in unchanged copied DNF body; pinned upstream calls plus exact empty read-only overlays. No Fedora build reproduction claim.',
        'later_bootstrap_closure_bindings_automatically_written':False})


def bootstrap_guard(session):
    expected=session.binding['bootstrap']
    for relative,digest in expected['file_hashes'].items():
        file=session.root/'work'/('guard-'+Path(relative).name)
        session.copy_binary(relative,file,'bootstrap-guard-'+Path(relative).name)
        require(sha_file(file)==digest,'actual bootstrap executable differs:'+relative)
    report=json.loads((HERE/'bootstrap-report.json').read_text())
    require('RPM version 6.0.2' in report['versions']['/usr/bin/rpm'] and
        '5.4.6.0' in report['versions']['/usr/bin/dnf5'],'reviewed actual bootstrap version output differs')
    require(header_rows(session)==[tuple(row) for row in report['headers']],'actual immutable base headers differ')
    return report


def prepare_root(session):
    work=session.root/'work';target=work/'installroot';target.mkdir(mode=0o755)
    before={}
    for rel in ('usr/lib/sysimage/rpm','usr/lib/sysimage/libdnf5'):
        dest=target/rel;dest.parent.mkdir(parents=True,exist_ok=True)
        session.copy('/'+rel,dest,'copy-state-'+Path(rel).name)
        before[rel]=manifest_digest(tree_manifest(dest))
        safe_tree(dest,1000000000)
    for rel in ('etc/os-release','etc/passwd','etc/group'):
        dest=target/rel;dest.parent.mkdir(parents=True,exist_ok=True)
        if rel=='etc/os-release':session.copy_os_release(dest,'copy-os-release')
        else:session.copy('/'+rel,dest,'copy-'+Path(rel).name)
    for rel in ('config/repos','config/empty-plugins','config/empty-vars','home','cache','logs','keys','goal'):
        (work/rel).mkdir(mode=0o755,parents=True,exist_ok=True)
    config={'installroot':'/work/installroot','use_host_config':'false','plugins':'false',
        'pluginpath':'/work/config/empty-plugins','plugin_conf_dir':'/work/config/empty-plugins',
        'varsdir':'/work/config/empty-vars','reposdir':'/work/config/repos','cachedir':'/work/cache','system_cachedir':'/work/cache',
        'logdir':'/work/logs','persistdir':'/audit/persist','system_state_dir':'/usr/lib/sysimage/libdnf5',
        'transaction_history_dir':'/audit/history','install_weak_deps':'true','clean_requirements_on_remove':'false',
        'best':'true','pkg_gpgcheck':'true','retries':'1','max_parallel_downloads':'1','optional_metadata_types':'filelists',
        'zchunk':'false','cacheonly':'metadata','metadata_expire':'never','skip_if_unavailable':'false'}
    parser=configparser.ConfigParser();parser['main']=config
    with (work/'config/dnf.conf').open('x') as stream:parser.write(stream)
    for repo,entry in session.binding['repositories'].items():
        parser=configparser.ConfigParser();parser[repo]={'name':repo,'baseurl':entry['baseurl'],'enabled':'true',
            'pkg_gpgcheck':'true','repo_gpgcheck':'false','gpgkey':'file:///source/sources/fedora.gpg',
            'metadata_expire':'never','skip_if_unavailable':'false','retries':'1','max_parallel_downloads':'1'}
        with (work/'config/repos'/(repo+'.repo')).open('x') as stream:parser.write(stream)
    return before,config


def dnf_args(command, *args, cacheonly='metadata'):
    options={'use_host_config':'false','plugins':'false','pluginpath':'/work/config/empty-plugins',
        'plugin_conf_dir':'/work/config/empty-plugins','varsdir':'/work/config/empty-vars','reposdir':'/work/config/repos',
        'cachedir':'/work/cache','system_cachedir':'/work/cache','logdir':'/work/logs','persistdir':'/audit/persist',
        'system_state_dir':'/usr/lib/sysimage/libdnf5','transaction_history_dir':'/audit/history',
        'install_weak_deps':'true','clean_requirements_on_remove':'false','best':'true','pkg_gpgcheck':'true',
        'optional_metadata_types':'filelists','zchunk':'false','retries':'1','max_parallel_downloads':'1',
        'cacheonly':cacheonly,'skip_if_unavailable':'false'}
    setopts=['--setopt='+k+'='+v for k,v in options.items()]
    setopts.insert(setopts.index('--setopt=optional_metadata_types=filelists'),'--setopt=optional_metadata_types=')
    return ['/usr/bin/dnf5','--no-plugins','--config=/work/config/dnf.conf','--installroot=/work/installroot',
        '--releasever=44',*setopts,'--assumeyes',command,*args]


def cache_catalog(session):
    # Resolve against these exact cached repodata bytes; their libdnf5 cache
    # placement is a separate reviewed bootstrap API binding, never inferred.
    catalog={};proof={};work=session.root/'work'
    layout=session.binding['bootstrap'].get('cached_metadata_paths')
    require(type(layout) is dict and set(layout)==set(session.binding['repositories']),'cache layout unbound')
    for repo,metadata in session.binding['repositories'].items():
        row=layout[repo];require(set(row)=={'repomd','primary','filelists'},'cache layout fields differ')
        repomd=c.relative_member(row['repomd']);path=work/repomd
        require(str(repomd).startswith('cache/') and path.stat().st_size==metadata['repomd_bytes'] and
            sha_file(path)==metadata['repomd_sha256'],'cached repomd differs')
        proof[repo]={'repomd_sha256':sha_file(path)}
        for kind in ('primary','filelists'):
            rel=c.relative_member(row[kind]);path=work/rel;expected=metadata['metadata'][kind]
            require(str(rel).startswith('cache/') and path.stat().st_size==expected['bytes'] and sha_file(path)==expected['sha256'],
                'cached exact compressed metadata differs')
            out=work/(repo+'-'+kind+'.xml')
            # zstd is an extra bootstrap reader and must be separately bound.
            require(c.hash64(session.binding['bootstrap'].get('zstd_file_sha256')),'bootstrap zstd reader unbound')
            probe=work/(repo+'-'+kind+'-zstd-'+str(session.count))
            session.copy_binary('usr/bin/zstd',probe,'zstd-guard-'+repo+'-'+kind)
            require(sha_file(probe)==session.binding['bootstrap']['zstd_file_sha256'],'zstd bootstrap reader differs')
            # -o explicit owned output; command deadline and disk monitor apply.
            session.exec(['/usr/bin/zstd','-d','-f','-o','/work/'+out.name,'/work/'+str(rel)],'metadata-expand-'+repo+'-'+kind,120)
            require(out.stat().st_size==expected['open_bytes'] and sha_file(out)==expected['open_sha256'],'metadata expanded bytes differ')
            if kind=='primary':
                for event,node in ET.iterparse(out,events=('end',)):
                    if node.tag!='{http://linux.duke.edu/metadata/common}package':continue
                    ns={'m':'http://linux.duke.edu/metadata/common','r':'http://linux.duke.edu/metadata/rpm'}
                    ver=node.find('m:version',ns);checksum=node.find('m:checksum',ns);size=node.find('m:size',ns)
                    evr=ver.attrib['epoch']+':'+ver.attrib['ver']+'-'+ver.attrib['rel']
                    item={'name':node.findtext('m:name',namespaces=ns),'evr':evr,'arch':node.findtext('m:arch',namespaces=ns),
                        'bytes':int(size.attrib['package']),'sha256':checksum.text,'repo':repo,
                        'location':c.relative_member(node.find('m:location',ns).attrib['href']).as_posix(),
                        'license':node.findtext('m:format/r:license',namespaces=ns),'source_RPM':node.findtext('m:format/r:sourcerpm',namespaces=ns)}
                    require(checksum.attrib['type']=='sha256','unsupported metadata checksum')
                    # Fedora x86_64 snapshots also contain unrelated multilib
                    # rows. They are not eligible for this tools goal; their
                    # presence must not reject the supported catalog itself.
                    if item['arch'] not in ('x86_64','noarch'):
                        node.clear();session.limits();continue
                    identity=c.nevra((item['name'],evr,item['arch']))
                    if identity in catalog:require(catalog[identity]['sha256']==item['sha256'],'same NEVRA different snapshot body')
                    catalog[identity]=item;node.clear();session.limits()
    write_json(work/'verified-cache-snapshots.json',proof)
    return catalog


def signed_files(session,payload,index):
    args=['/usr/bin/rpm','--noplugins','-qp',payload]
    identity=c.rows(session.exec([*args,'--qf',c.IDENTITY_QF],'signed-header-'+str(index),30))
    require(len(identity)==1,'payload header population')
    text=session.exec([*args,'--qf',c.FILE_QF],'signed-files-'+str(index),30)
    algorithm=session.exec([*args,'--qf','%{FILEDIGESTALGO}'],'signed-digest-'+str(index),15).strip()
    names={8:'sha256',9:'sha384',10:'sha512'}
    require(algorithm.isdigit() and int(algorithm) in names,'unsupported strong file digest')
    root=session.root/'work/installroot'
    users={r.split(':')[0]:int(r.split(':')[2]) for r in (root/'etc/passwd').read_text().splitlines()}
    groups={r.split(':')[0]:int(r.split(':')[2]) for r in (root/'etc/group').read_text().splitlines()}
    return identity[0],c.file_table(text,names[int(algorithm)],users,groups)


def closure(session):
    bootstrap_guard(session);before,config=prepare_root(session)
    installed=header_rows(session,'/work/installroot')
    # Only makecache may fetch metadata. The source-bound cached layout is then
    # verified twice; store uses cacheonly=metadata and immutable cached bytes.
    session.exec(dnf_args('makecache',cacheonly='none'),'private-makecache',300)
    catalog=cache_catalog(session)
    config_dump=session.exec(dnf_args('--dump-main-config'),'private-config-dump',30)
    c.config_dump_verify(config_dump,config)
    goals=session.binding['tool_root_goals']
    specs=[name+'-'+version for name,version in goals.items()]
    # --store branch returns before transaction.run in pinned Context source.
    session.exec(dnf_args('do','--action=install','--type=package','--store=/work/goal',*specs),'resolve-store-download-only',600)
    catalog=cache_catalog(session)
    goal=json.loads((session.root/'work/goal/transaction.json').read_text())
    incoming,replaced,expected_after=c.stored_goal(goal,installed,catalog,goals)
    require(header_rows(session,'/work/installroot')==installed,'private RPMdb changed during no-runner solve')
    for rel,digest in before.items():require(manifest_digest(tree_manifest(session.root/'work/installroot'/rel))==digest,'private base state mutated')
    session.exec(['/usr/bin/rpmkeys','--noplugins','--define','_keyring fs','--define','_keyringpath /work/keys',
        '--import','/source/sources/fedora.gpg'],'owned-fs-key-import',30)
    selected=[];actual_files=set();package_dir=session.root/'work/goal/packages'
    for index,row in enumerate(incoming):
        filename=Path(row['location']).name;require(filename not in actual_files,'basename collision unsupported');actual_files.add(filename)
        path=package_dir/filename
        require(path.is_file() and not path.is_symlink() and path.stat().st_size==row['bytes'] and sha_file(path)==row['sha256'],'payload snapshot checksum/size differs')
        inside='/work/goal/packages/'+filename
        output=session.exec(['/usr/bin/rpmkeys','--noplugins','--define','_keyring fs','--define','_keyringpath /work/keys',
            '--define','_pkgverify_level all','--checksig','--verbose',inside],'payload-signature-'+str(index),30)
        verify_signature_result(0,output,c.FEDORA)
        identity,files=signed_files(session,inside,index)
        require(identity[:3]==(row['name'],row['evr'],row['arch']) and identity[3:]==(row['source_RPM'],row['license']),'signed header/metadata identity differs')
        # Inert extraction provides actual signed body/hardlink proof; no scripts.
        raw=session.root/'work'/('payload-'+str(index)+'.cpio')
        session.binary(['/usr/bin/rpm2cpio',inside],raw,'payload-cpio-'+str(index),timeout=60)
        destination=session.root/'work'/('inert-package-'+str(index));destination.mkdir(mode=0o700)
        with raw.open('rb') as stream:
            body=unpack(stream,destination,{name:entry for name,entry in files.items() if not entry['flags'] & 64},max_bytes=4000000000)
        selected.append({**row,'filename':filename,'signed_identity':list(identity),'files':files,
            'inert_body_proof':body,'expected_full_signer':c.FEDORA,'payload_sha256':sha_file(path)})
        raw.unlink()
        # Inert bodies are proof only, not a loader/system root; remove them after
        # a complete type-aware manifest. The signed payload stays for B.
        shutil.rmtree(destination)
        session.limits()
    require({p.name for p in package_dir.iterdir()}==actual_files,'extra payload not in selected goal')
    output=session.root/'outputs';(output/'packages').mkdir(mode=0o700)
    for row in selected:shutil.copyfile(package_dir/row['filename'],output/'packages'/row['filename'])
    write_json(output/'payload-manifest.json',[{k:row[k] for k in ('name','evr','arch','filename','bytes','sha256','expected_full_signer')} for row in selected])
    write_json(output/'before-headers.json',installed);write_json(output/'state-manifest.json',before)
    write_json(output/'closure-report.json',{'status':'SIGNED_CLOSURE_EXTERNAL_REVIEW_STOP','selected':selected,
        'before_headers':installed,'expected_after_headers':expected_after,'replaced':replaced,'state_manifest':before,'config':config,'goal':goal,
        'selected_catalog':{c.nevra((r['name'],r['evr'],r['arch'])):r for r in selected},
        'normal_weak_dependencies':True,'RPM_runner_test_replay_scripts':False,
        'source_RPM_license_obligations':'Every signed source RPM/license recorded; package notices retained in payloads. No legal compliance conclusion.'})


def image(session):
    # Exact-source future composition consumes externally reviewed real closure.
    bootstrap_guard(session)
    root=session.root;closure=session.binding['closure'];inputs=root/'inputs/closure'
    report=inputs/'closure-report.json';manifest=inputs/'payload-manifest.json'
    require(sha_file(report)==closure['report_sha256'] and sha_file(manifest)==closure['payload_manifest_sha256'],'reviewed closure report/payload identities differ')
    data=json.loads(report.read_text());payloads=json.loads(manifest.read_text())
    require(data['status']=='SIGNED_CLOSURE_EXTERNAL_REVIEW_STOP' and data['before_headers']==[list(r) for r in header_rows(session)],'base headers differ from reviewed closure')
    require(sha_file(inputs/'before-headers.json')==closure['before_headers_sha256'] and
        sha_file(inputs/'state-manifest.json')==closure['state_manifest_sha256'],'before/state binding differs')
    require(json.loads((inputs/'before-headers.json').read_text())==data['before_headers'] and
        json.loads((inputs/'state-manifest.json').read_text())==data['state_manifest'],'state/header report membership differs')
    require(set(data['state_manifest'])=={'usr/lib/sysimage/rpm','usr/lib/sysimage/libdnf5'},'approved base state incomplete')
    for relative,digest in data['state_manifest'].items():
        require(relative in ('usr/lib/sysimage/rpm','usr/lib/sysimage/libdnf5'),'unknown approved base state path')
        copied=root/'work'/('before-'+Path(relative).name)
        session.copy('/'+relative,copied,'B-before-state-'+Path(relative).name)
        require(manifest_digest(tree_manifest(copied))==digest,'B same immutable base state differs')
    incoming,replaced,after=c.stored_goal(data['goal'],[tuple(r) for r in data['before_headers']],data['selected_catalog'],session.binding['tool_root_goals'])
    require([list(r) for r in after]==data['expected_after_headers'],'reviewed after headers differ')
    require(len(payloads)==len(incoming) and len({r['name'] for r in payloads})==len(payloads),'payload membership differs')
    expected_payloads={r['name']:r for r in incoming}
    require({r['name'] for r in payloads}==set(expected_payloads),'payload set differs from exact resolved goal')
    require({p.name for p in (inputs/'packages').iterdir()}=={r['filename'] for r in payloads},'extra/missing closure payload')
    for row in payloads:
        expected=expected_payloads[row['name']]
        require(all(row[k]==expected[k] for k in ('name','evr','arch','bytes','sha256')) and
            row['filename']==Path(expected['location']).name and row['expected_full_signer']==c.FEDORA,
            'signed payload/header/goal identity differs')
        path=inputs/'packages'/c.relative_member(row['filename'])
        require(path.parent==inputs/'packages' and path.is_file() and not path.is_symlink() and
            path.stat().st_size==row['bytes'] and sha_file(path)==row['sha256'],'reviewed payload bytes differ')
    iso=root/'inputs/iso/Arctic-Linux-1.2-candidate-37507582946-1-x86_64.iso';c.iso_identity(iso)
    # Only one scriptless transaction. Marker is irrevocably set before the call.
    # No retry/alternate script flag on failure; default RPM ordering/dependencies
    # and cryptographic checks are retained. It runs solely in this disposable root.
    c.readable_json(root/'work/approved-closure-report.json',data)
    c.readable_json(root/'work/approved-payload-manifest.json',payloads)
    marker=root/'work/single-tools-transaction.json'
    require(not marker.exists() and not marker.is_symlink(),'tools transaction already attempted/unsafe marker')
    write_json(marker,{'attempts':1,'root':'/','container':session.name,'flags':closure['scriptless_flags']})
    require(not (root/'work/keys').exists() and not (root/'work/keys').is_symlink(),'stale B keyring directory')
    session.exec(['/usr/bin/mkdir','-m','700','/work/keys'],'B-fresh-owned-keyring-directory',15)
    session.exec(['/usr/bin/rpmkeys','--noplugins','--define','_keyring fs','--define','_keyringpath /work/keys',
        '--import','/source/sources/fedora.gpg'],'B-owned-key-import',30)
    for index,row in enumerate(payloads):
        output=session.exec(['/usr/bin/rpmkeys','--noplugins','--define','_keyring fs','--define','_keyringpath /work/keys',
            '--define','_pkgverify_level all','--checksig','--verbose','/input/closure/packages/'+row['filename']],
            'B-full-signature-'+str(index),30)
        verify_signature_result(0,output,c.FEDORA)
    argv=['/usr/bin/rpm','--root','/','--define','_dbpath /usr/lib/sysimage/rpm','--define','_keyring fs',
        '--define','_keyringpath /work/keys','--define','_pkgverify_level all',*closure['scriptless_flags'],'-U',
        *['/input/closure/packages/'+row['filename'] for row in payloads]]
    session.exec(argv,'single-scriptless-tools-transaction',300)
    require(header_rows(session)==after,'actual after tools headers differ')
    session.exec(['/usr/bin/python3','-B','/source/tool_checks.py'],'actual-tools-files-API-reader-controls',300)
    post_state=root/'work/after-libdnf5-state'
    session.copy('/usr/lib/sysimage/libdnf5',post_state,'actual-post-tools-reason-state')
    after_state=manifest_digest(tree_manifest(post_state))
    # Read exact current archived member only after tools checks; no root/ISO build.
    listing=session.exec(['/usr/bin/xorriso','-indev','/input/iso/'+iso.name,'-find','/','-type','f','-exec','echo','--'],
        'exact-ISO-list',120)
    member=c.iso_member_listing(listing)
    session.exec(['/usr/bin/xorriso','-osirrox','on','-indev','/input/iso/'+iso.name,'-extract','/'+member,'/work/current-member.img'],
        'exact-ISO-member-extract',180)
    current=root/'work/current-member.img'
    require(current.is_file() and not current.is_symlink() and current.stat().st_size<=c.ISO_BYTES,'archived member byte bound')
    with current.open('rb') as stream:stream.seek(1024);magic=stream.read(4)
    require(magic==b'\xe2\xe1\xf5\xe0','current archived member is not expected EROFS; source reviewed successor required')
    write_json(root/'outputs/current-member-report.json',{'ISO_bytes':c.ISO_BYTES,'ISO_sha256':c.ISO_SHA,
        'archived_member':member,'archived_member_bytes':current.stat().st_size,'archived_member_sha256':sha_file(current),
        'format':'EROFS','resolved_root':'UNEXTRACTED_UNPROVED','valid_new_ISO':False})
    manifest=json.loads((root/'work/tool-image-manifest.json').read_text())
    require(manifest['status']=='SIGNED_INPUTS_AND_API_CONTROLS_PASS','tools API/file proof failed')
    image_id=session.call(['docker','commit','--change','ENTRYPOINT []','--change','CMD ["/usr/bin/python3"]',
        '--change','USER 0:0','--change','WORKDIR /',session.name],'commit-owned-tools-image',120).strip()
    require(image_id.startswith('sha256:') and c.hash64(image_id[7:]),'actual local image ID malformed')
    session.committed=image_id
    config=json.loads(session.call(['docker','image','inspect',image_id],'produced-image-inspect',15))[0]
    require(config['Id']==image_id,'produced image ID differs')
    archive=root/'outputs/tool-image.tar'
    session.call(['docker','save','--output',str(archive),image_id],'save-local-tools-image',180)
    require(archive.stat().st_size<=2000000000,'tools image tar cap')
    manifest.update(image_id=image_id,archive_sha256=sha_file(archive),archive_bytes=archive.stat().st_size,
        image_config=config,source=session.ctx['source'],signed_closure_report_sha256=sha_file(report),
        current_member_report_sha256=sha_file(root/'outputs/current-member-report.json'),
        observed_after_DNF_reason_state_sha256=after_state,
        DNF_reason_limit='RPM-only tools transaction; copied reason state observed, no DNF reason/history reconstruction claimed.')
    write_json(root/'outputs/tool-image-manifest.json',manifest)


def run(root):
    root,ctx=context(root);binding=json.loads((HERE/'runtime-binding.json').read_text());c.binding_for(ctx['stage'],binding)
    session=Session(root,ctx,binding);primary=None;secondary=[];passed=False
    try:
        if ctx['stage']=='image':c.readable_json(root/'work/host-context.json',ctx)
        else:write_json(root/'work/host-context.json',ctx)
        if ctx['stage']=='image':
            # Downloaded artifact files are exposed read-only; private0700 host
            # parent preserves host isolation while container UID0 can read data.
            for p in (root/'inputs').rglob('*'):
                require(not p.is_symlink() and (p.is_file() or p.is_dir()),'linked/special downloaded input')
                p.chmod(0o755 if p.is_dir() else 0o644)
        session.create()
        {'discovery':discovery,'metadata':metadata,'closure':closure,'image':image}[ctx['stage']](session)
        safe_tree(root/'outputs',(2000000000 if ctx['stage']=='image' else 1000000000 if ctx['stage']=='closure' else 0)+20000000)
        passed=True
    except BaseException as error:primary=error
    finally:
        try:session.cleanup()
        except Exception as error:secondary.append(c.failure_detail(error))
        try:
            write_json(root/'evidence/final-observed-status.json',{'preparation':ctx['stage'],'passed':passed and not secondary,
                'primary_failure':c.failure_detail(primary) if primary else None,'cleanup_failures':secondary,
                'external_review_STOP':True,'codec_solver_adoption_playback_ISO_build':'UNRUN','source':ctx['source']})
            safe_tree(root/'evidence',20000000)
        except Exception as error:secondary.append(c.failure_detail(error))
    if primary or secondary:raise c.GuardError(json.dumps({'primary':c.failure_detail(primary) if primary else None,'secondary':secondary},sort_keys=True)) from primary


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('preflight','run'))
    parser.add_argument('--root',type=Path,required=True);parser.add_argument('--source',required=True)
    args=parser.parse_args()
    if args.action=='preflight':preflight(args.root,args.source)
    else:
        _,ctx=context(args.root);require(ctx['source']==args.source,'caller source differs');run(args.root)

if __name__=='__main__':main()
