"""Actual offline tools-root checks, run only after the approved scriptless RPM-U."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import stat
import sys
import time
import contract as c
from core import (require, image_member, write_json, sha_file, tree_manifest, manifest_digest,
    verify_signature_result, provider_proof, KEYS)
import worker

WORK=Path('/work')
SOURCE=Path('/source')


def package_file_proofs():
    import rpm
    report=json.loads((WORK/'approved-closure-report.json').read_text())
    headers,rows=worker.installed_headers(Path('/'))
    require(rows==sorted(tuple(r[:3]) for r in report['expected_after_headers']),'actual tool RPMdb identity differs')
    # All selected files must match actual signed header type, literal symlink and
    # digest. Permission/ownership are asserted, not repaired through scripts.
    worker.IMAGE=Path('/')
    all_files={};owners={}
    selected={r['name']:r for r in report['selected']}
    for header in headers:
        if header['name'] not in selected:continue
        files=worker.header_files(header)
        require(files==selected[header['name']]['files'],'installed signed header file table differs')
        for relative,entry in files.items():
            if entry['flags'] & 64:continue
            logical=c.relative_member(relative)
            parent=Path('/') if str(logical.parent)=='.' else image_member(Path('/'),str(logical.parent))
            path=parent/logical.name;st=path.lstat()
            require(stat.S_IFMT(st.st_mode)==stat.S_IFMT(entry['mode']) and stat.S_IMODE(st.st_mode)==stat.S_IMODE(entry['mode']) and
                st.st_uid==entry['uid'] and st.st_gid==entry['gid'],'installed file metadata differs:'+relative)
            if stat.S_ISREG(st.st_mode):
                digest=hashlib.new(entry['digest_algorithm'])
                with path.open('rb') as stream:
                    for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
                require(digest.hexdigest()==entry['digest'],'installed signed body differs:'+relative)
                all_files[relative]=sha_file(path)
            elif stat.S_ISLNK(st.st_mode):require(os.readlink(path)==entry['link'],'installed literal link differs')
            elif not stat.S_ISDIR(st.st_mode):raise c.GuardError('unsupported actual installed file type')
            owners.setdefault(relative,[]).append(header['name'])
    root_goals=json.loads((SOURCE/'runtime-binding.json').read_text())['tool_root_goals']
    for name,version in root_goals.items():
        match=[h for h in headers if h['name']==name]
        require(len(match)==1 and match[0]['version']+'-'+match[0]['release']+'.'+match[0]['arch']==version,'actual root version differs')
    tools=('usr/bin/python3','usr/bin/rpmkeys','usr/bin/rpm2cpio','usr/bin/gpg','usr/bin/zstd','usr/bin/xorriso','usr/bin/mkfs.erofs','usr/bin/fsck.erofs',
        'usr/lib64/python3.14/site-packages/libdnf5/_base.so','usr/lib64/python3.14/site-packages/rpm/_rpm.so')
    tool_hashes={};tool_owners={}
    all_headers_files={}
    for header in headers:
        if header['name']=='gpg-pubkey':continue
        for relative,entry in worker.header_files(header).items():all_headers_files.setdefault(relative,[]).append({'owner':header['name'],**entry})
    for relative in tools:
        proof=provider_proof(relative,{},all_headers_files,Path('/'))
        resolved=image_member(Path('/'),relative)
        require(resolved.is_file(),'actual tool file absent')
        tool_hashes[relative]=sha_file(resolved);tool_owners[relative]=proof
    return root_goals,tool_hashes,tool_owners


def private_API_checks():
    import rpm
    import libdnf5.base as base_module
    import libdnf5.transaction as transaction_module
    root=WORK/'API-root';root.mkdir(mode=0o700)
    for relative in ('usr/lib/sysimage/rpm','usr/lib/sysimage/libdnf5'):
        origin=image_member(Path('/'),relative);target=root/relative;target.parent.mkdir(parents=True,exist_ok=True)
        before=tree_manifest(origin);require(all(r['type'] in ('regular','directory') for r in before),'unsupported linked base state')
        shutil.copytree(origin,target);require(tree_manifest(target)==before,'private API state copy differs')
    base=base_module.Base();config=base.get_config()
    values={'installroot':str(root),'config_file_path':str(WORK/'API-conf/dnf.conf'),'plugins':False,
        'pluginpath':str(WORK/'API-conf/empty'),'plugin_conf_dir':[str(WORK/'API-conf/empty')],
        'varsdir':[str(WORK/'API-conf/empty')],'reposdir':[str(WORK/'API-conf/repos')],
        'cachedir':str(WORK/'API-cache'),'system_cachedir':str(WORK/'API-cache'),'logdir':str(WORK/'API-logs'),
        'persistdir':'/audit/persist','system_state_dir':'/usr/lib/sysimage/libdnf5','transaction_history_dir':'/audit/history',
        'use_host_config':False,'optional_metadata_types':['filelists'],'zchunk':False,'install_weak_deps':True,
        'clean_requirements_on_remove':False,'best':True,'pkg_gpgcheck':True,'retries':1,'max_parallel_downloads':1}
    for sub in ('API-conf/empty','API-conf/repos','API-cache','API-logs'):(WORK/sub).mkdir(mode=0o700,parents=True,exist_ok=True)
    (WORK/'API-conf/dnf.conf').write_text('[main]\n')
    for name,value in values.items():getattr(config,'get_'+name+'_option')().set(value)
    base.get_vars().set('releasever','44');base.get_vars().set('basearch','x86_64');base.setup()
    for name,expected in values.items():
        actual=getattr(config,'get_'+name+'_option')().get_value()
        if isinstance(expected,list):actual=list(actual)
        require(actual==expected,'actual Python configuration API differs:'+name)
    require(not list(base.get_plugins_info()),'actual API plugins loaded')
    sack=base.get_repo_sack();sack.create_repos_from_system_configuration();sack.update_and_load_enabled_repos(True)
    goal=base_module.Goal(base);goal.set_allow_erasing(False)
    settings=base_module.GoalJobSettings();settings.set_from_repo_ids([])
    goal.add_rpm_install('dnf5-5.4.6.0-1.fc44.x86_64',settings)
    transaction=goal.resolve();require(int(transaction.get_problems())==0,'actual private installed-goal API fails')
    require(not list(transaction.get_transaction_packages()),'installed positive API goal unexpectedly changes package state')
    serialized=transaction.serialize();require(len(serialized)<=100000,'actual API serialization bound')
    ts=rpm.TransactionSet(str(root));require(list(ts.dbMatch()),'actual Python rpm header API fails')
    return {'passed':True,'private_installed_goal':True,'network':'none','transaction_run_download_replay':False,
        'plugins_loaded':False,'serialized':json.loads(serialized),'normal_weak_dependencies':True,
        'limit':'Installed positive no-op goal only; future codec closure remains separate actual qualification.'}


def reader_and_crypto_controls(deadline):
    worker.WORK=WORK;worker.SOURCE=SOURCE
    # Reader command resource guard needs the tool-specific context.
    worker.resources=lambda:require(shutil.disk_usage(WORK).free>=1000000000,'tool checks disk reserve')
    pair=WORK/'roundtrip';pair.mkdir(mode=0o700);old=pair/'old';old.mkdir()
    (old/'data').write_bytes(b'Arctic tools reader fixture\n'*100)
    (old/'empty').mkdir();(old/'link').symlink_to('data');os.link(old/'data',old/'alias')
    before=tree_manifest(old)
    output=pair/'fixture.erofs'
    worker.command(['/usr/bin/mkfs.erofs','-zlzma,6','-C1048576','-Efragments','-T0','-U00000000-0000-0000-0000-000000000000',str(output),str(old)],deadline,'EROFS-tool-fixture',100000,120)
    restored=pair/'restored'
    worker.command(['/usr/bin/fsck.erofs','--extract='+str(restored),str(output)],deadline,'EROFS-tool-readback',100000,120)
    require(tree_manifest(restored)==before,'EROFS actual type/link/hardlink/mode roundtrip differs')
    # Full-signature success is from every actual inbound payload, repeated here.
    # Two altered copies must fail actual verbose crypto; no synthetic signer or
    # digest-only success is accepted. Copies never enter RPM-U.
    selected=json.loads((WORK/'approved-payload-manifest.json').read_text())
    first=Path('/input/closure/packages')/selected[0]['filename']
    good,record=worker.command(['/usr/bin/rpmkeys','--noplugins','--define','_keyring fs','--define','_keyringpath /work/keys',
        '--define','_pkgverify_level all','--checksig','--verbose',str(first)],deadline,'crypto-positive',100000,30)
    verify_signature_result(record['exit_status'],good.read_text(),c.FEDORA)
    rejected=[]
    for label,data in (('truncated',first.read_bytes()[:64]),('altered',first.read_bytes()[:-1]+bytes([first.read_bytes()[-1]^1]))):
        path=WORK/(label+'.rpm');path.write_bytes(data)
        try:
            out,result=worker.command(['/usr/bin/rpmkeys','--noplugins','--define','_keyring fs','--define','_keyringpath /work/keys',
                '--define','_pkgverify_level all','--checksig','--verbose',str(path)],deadline,'crypto-negative-'+label,100000,30)
        except worker.PhaseFailure as error:
            result=json.loads((WORK/('crypto-negative-'+label+'.command.json')).read_text())
            require(result['exit_status'] is not None and result['exit_status']!=0 and
                result['primary_failure']['message']=='reader failed:crypto-negative-'+label and
                not result['cleanup_or_close_failures'],'crypto adverse control failed operationally')
            rejected.append(label);continue
        try:verify_signature_result(result['exit_status'],out.read_text(),c.FEDORA)
        except Exception:rejected.append(label)
    require(rejected==['truncated','altered'],'actual altered payload accepted')
    wrong=False
    try:verify_signature_result(record['exit_status'],good.read_text(),c.FUSION)
    except Exception:wrong=True
    require(wrong,'wrong full signer accepted')
    return {'EROFS_type_aware_roundtrip':True,'actual_altered_truncated_crypto_rejected':rejected,
        'wrong_full_fingerprint_rejected':True,'cipher_negative_limit':'Header/payload tampering only; no separate untrusted signer RPM created.',
        'whole_root_ISO_playback':'UNRUN'}


def main():
    require(not any(os.environ.get(k) for k in ('GH_TOKEN','GITHUB_TOKEN','HTTP_PROXY','HTTPS_PROXY')),'secret/proxy exposed to tools checks')
    context=json.loads((WORK/'host-context.json').read_text())
    deadline=c.Deadline(context['started'],1800);deadline.end-=360
    roots,files,owners=package_file_proofs();api=private_API_checks();controls=reader_and_crypto_controls(deadline)
    c.readable_json(WORK/'tool-image-manifest.json',{'status':'SIGNED_INPUTS_AND_API_CONTROLS_PASS','tool_packages':roots,
        'tool_file_hashes':files,'signed_header_actual_file_owners':owners,'API_controls':api,'reader_crypto_controls':controls,
        'single_scriptless_tools_root_transaction':True,'codec_adoption_solver_playback_ISO':'UNRUN'})

if __name__=='__main__':main()
