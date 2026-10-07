"""Finite synthetic source controls; no Docker/RPM/DNF/ISO/network operation."""
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase,mock
import ast
import copy
import hashlib
import json
import os
import stat
import tempfile
import time
import unittest
import yaml
import contract as c
import prepare
import tool_checks

HERE=Path(__file__).resolve().parent

def workflow():
    audit=HERE/'registered-iso-codec-tools-discovery-v3.yml'
    selected=audit if audit.exists() else HERE.parents[1]/'.github/workflows/iso.yml'
    return selected.read_text()


def registered_inputs(source='1'*40):
    return {'same_iso_pcmanfm_diagnostic':False,'same_iso_native_smoke':False,'same_iso_recovery':False,
        'release':False,'draft':False,'nix_acceptance':False,'performance_acceptance':False,'boot_test':False,
        'tag':'','prerelease':True,'codec_tools_discovery':True,'codec_tools_metadata_check':False,'codec_tools_source_sha':source}


def bound(stage='discovery'):
    data=json.loads((HERE/'runtime-binding.json').read_text())
    data.update(status='SOURCE_REVIEW_BOUND',execution_review_sha256='1'*64)
    if stage in ('closure','image'):
        data['bootstrap']={'review_sha256':'2'*64,'report_sha256':'3'*64,'base_image_id':c.BASE_ID,
            'rpm_version':'6.0.2','dnf5_version':'5.4.6.0','file_hashes':{k:'4'*64 for k in c.BOOTSTRAP_TOOLS},
            'metadata_cache_mode':'cacheonly-metadata-verified-layout-v1','API_controls_sha256':'5'*64,
            'zstd_file_sha256':'8'*64,'cached_metadata_paths':{name:{kind:'cache/'+name+'/'+kind for kind in ('repomd','primary','filelists')} for name in data['repositories']}}
    if stage=='image':
        data['closure']={k:'6'*64 for k in ('review_sha256','report_sha256','payload_manifest_sha256','before_headers_sha256','state_manifest_sha256')}
        data['closure'].update(artifact_id=123,run_id=456,source_sha='7'*40,removal_policy='ONLY_SAME_NAME_UPGRADE_REPLACED',
            scriptless_flags=['--noscripts','--notriggers','--noplugins','--nosysusers'])
    return data


def goal_fixture():
    old=[('keep','0:1-1.fc44','x86_64','keep-1-1.fc44.src.rpm','MIT'),
        ('tool','0:1-1.fc44','x86_64','tool-1-1.fc44.src.rpm','MIT')]
    catalog={'tool-2-1.fc44.x86_64':{'name':'tool','evr':'0:2-1.fc44','arch':'x86_64','repo':'updates',
        'bytes':100,'sha256':'a'*64,'location':'Packages/t/tool-2-1.fc44.x86_64.rpm','source_RPM':'tool-2-1.fc44.src.rpm','license':'MIT'}}
    obj={'version':'1.0','rpms':[{'nevra':'tool-1-1.fc44.x86_64','action':'Replaced','reason':'User','repo_id':'@System'},
        {'nevra':'tool-2-1.fc44.x86_64','action':'Upgrade','reason':'User','repo_id':'@stored_transaction(updates)',
         'package_path':'./packages/tool-2-1.fc44.x86_64.rpm'}]}
    return obj,old,catalog,{'tool':'2-1.fc44.x86_64'}


class SourceGuards(TestCase):
    def test_supplied_binding_admits_only_source_review_bound_discovery(self):
        obj=json.loads((HERE/'runtime-binding.json').read_text())
        self.assertIsNone(c.binding_for('discovery',obj)['bootstrap'])
        for stage in ('closure','image'):
            with self.subTest(stage=stage),self.assertRaisesRegex(c.GuardError,'BLOCKED'):c.binding_for(stage,obj)
    def test_explicit_source_bound_discovery_never_needs_bootstrap(self):
        self.assertIsNone(c.binding_for('discovery',bound())['bootstrap'])
    def test_closure_cannot_follow_discovery_automatically(self):
        with self.assertRaisesRegex(c.GuardError,'STOP'):c.binding_for('closure',bound())
    def test_image_cannot_follow_closure_automatically(self):
        with self.assertRaisesRegex(c.GuardError,'STOP'):c.binding_for('image',bound('closure'))
    def test_complete_synthetic_binding_all_three_modes(self):
        for stage in c.STAGES:c.binding_for(stage,bound(stage))
    def test_unknown_version_mutable_base_or_wrong_key_fail(self):
        for field,value in (('dnf5_version','5.3.0'),('rpm_version','6.0.1'),('API_controls_sha256',None),('file_hashes',{})):
            data=bound('closure');data['bootstrap'][field]=value
            with self.subTest(field=field),self.assertRaises(c.GuardError):c.binding_for('closure',data)
        for part,key,value in (('base','image_id','fedora:44'),('keys','fedora','short-id'),('keys','fusion_preserved_not_enabled','0'*40)):
            data=bound();data[part][key]=value
            with self.assertRaises(c.GuardError):c.binding_for('discovery',data)
    def test_image_scripts_missing_flag_or_unreviewed_artifact_fail(self):
        for field,value in (('scriptless_flags',['--noscripts']),('artifact_id',0),('review_sha256',None),('source_sha','main'),('removal_policy','all')):
            data=bound('image');data['closure'][field]=value
            with self.subTest(field=field),self.assertRaises(c.GuardError):c.binding_for('image',data)
    def test_exact_input_schema_rejects_every_mixed_known_mode(self):
        base={'tools_binding':True,'preparation':'discovery','source_sha':'1'*40}
        modes=('release','nix_acceptance','performance_acceptance','boot_test','same_iso_recovery',
            'offline_cycle_recovery','same_iso_native_smoke','same_iso_pcmanfm_diagnostic','safe_visual_diagnostic','codec_evaluation')
        for mode in modes:
            with self.subTest(mode=mode),self.assertRaises(c.GuardError):c.inputs({**base,mode:False},'1'*40)
        for change in ({'tools_binding':False},{'preparation':'all'},{'source_sha':'main'}):
            with self.assertRaises(c.GuardError):c.inputs({**base,**change},'1'*40)
    def test_source_bound_keys_match_preserved_proposal(self):
        p=json.loads((HERE/'proposal-preserved.json').read_text())
        self.assertEqual(c.FEDORA,p['official_Fedora44_primary_fingerprint']);self.assertEqual(c.FUSION,'E9A491A3DE247814E7E067EAE06F8ECDD651FF2E')
    def test_phase_bounds_preserve_original_proposal(self):
        p=json.loads((HERE/'proposal-preserved.json').read_text())
        for stage,part in (('discovery','preparation_A'),('closure','preparation_A'),('image','preparation_B')):
            self.assertEqual(c.MODE[stage],tuple(p[part][k] for k in ('overall_seconds','initial_free_bytes','scratch_bytes')))


    def test_missing_cache_reader_or_snapshot_preflight_guard(self):
        for key in ('cached_metadata_paths','zstd_file_sha256'):
            data=bound('closure');data['bootstrap'].pop(key)
            with self.assertRaises(c.GuardError):c.binding_for('closure',data)
        data=bound('closure');data['repositories']['updates']['baseurl']='https://unapproved/'
        with self.assertRaises(c.GuardError):c.binding_for('closure',data)
        data=bound('image');data['tool_root_goals']['ffmpeg']='8.1.3-1.fc44.x86_64'
        with self.assertRaises(c.GuardError):c.binding_for('image',data)
    def test_effective_dump_bool1_and_exact_paths_fail_closed(self):
        expected={'plugins':'false','install_weak_deps':'true','metadata_expire':'never','reposdir':'/work/config/repos'}
        c.config_dump_verify('plugins = 0\ninstall_weak_deps = 1\nmetadata_expire = -1\nreposdir = /work/config/repos',expected)
        for text in ('plugins = 1','plugins = 0\ninstall_weak_deps = 0','plugins = 0\nplugins = 0'):
            with self.assertRaises(c.GuardError):c.config_dump_verify(text,expected)

class GoalControls(TestCase):
    def test_full_upgrade_goal_preserves_base_and_exact_roots(self):
        incoming,replaced,after=c.stored_goal(*goal_fixture())
        self.assertEqual(incoming[0]['reason'],'User');self.assertEqual(replaced[0][0],'tool')
        self.assertIn(('keep','0:1-1.fc44','x86_64','keep-1-1.fc44.src.rpm','MIT'),after)
    def test_remove_downgrade_replay_reinstall_reasonchange_fail(self):
        for action in ('Remove','Downgrade','Reinstall','Reason Change','Replaced'):
            obj,old,cat,goals=goal_fixture();obj['rpms'][1]['action']=action
            with self.subTest(action=action),self.assertRaises(c.GuardError):c.stored_goal(obj,old,cat,goals)
    def test_wrong_version_groups_or_unknown_fields_fail(self):
        for change in ({'version':'2.0'},{'groups':[{}]},{'environments':[{}]},{'unexpected':True}):
            obj,old,cat,goals=goal_fixture();obj.update(change)
            with self.assertRaises(c.GuardError):c.stored_goal(obj,old,cat,goals)
    def test_wrong_repo_path_reason_and_full_nevra_fail(self):
        for key,value in (('repo_id','https://evil'),('package_path','../outside.rpm'),('reason','unknown'),('nevra','absent')):
            obj,old,cat,goals=goal_fixture();obj['rpms'][1][key]=value
            with self.subTest(key=key),self.assertRaises(c.GuardError):c.stored_goal(obj,old,cat,goals)
    def test_duplicate_full_and_duplicate_name_different_arch_fail(self):
        obj,old,cat,goals=goal_fixture();obj['rpms'].append(copy.deepcopy(obj['rpms'][1]))
        with self.assertRaises(c.GuardError):c.stored_goal(obj,old,cat,goals)
        obj,old,cat,goals=goal_fixture();item=copy.deepcopy(cat['tool-2-1.fc44.x86_64']);item['arch']='noarch';cat['tool-2-1.fc44.noarch']=item
        row=copy.deepcopy(obj['rpms'][1]);row['nevra']='tool-2-1.fc44.noarch';obj['rpms'].append(row)
        with self.assertRaises(c.GuardError):c.stored_goal(obj,old,cat,goals)
    def test_payload_cap_missing_upgrade_pair_and_missing_root_fail(self):
        obj,old,cat,goals=goal_fixture();cat[next(iter(cat))]['bytes']=100000001
        with self.assertRaises(c.GuardError):c.stored_goal(obj,old,cat,goals)
        obj,old,cat,goals=goal_fixture();obj['rpms'].pop(0)
        with self.assertRaises(c.GuardError):c.stored_goal(obj,old,cat,goals)
        obj,old,cat,goals=goal_fixture();goals['absent']='1-1.x86_64'
        with self.assertRaises(c.GuardError):c.stored_goal(obj,old,cat,goals)
    def test_header_rows_JSON_normalization_and_multiversion_negative(self):
        data='tool\t0:2-1.fc44\tx86_64\tt.src.rpm\tMIT\n'
        rows=c.rows(data);self.assertEqual(rows,[tuple(r) for r in json.loads(json.dumps(rows))])
        with self.assertRaises(c.GuardError):c.rows(data+data.replace('x86_64','noarch'))
    def test_signed_file_json_literal_type_owner_and_path_controls(self):
        row=['/usr/lib64/test.so',stat.S_IFREG|0o644,'a'*64,'',0,'root','root']
        text='\t'.join(json.dumps(x) for x in row)+'\n'
        files=c.file_table(text,'sha256',{'root':0},{'root':0});self.assertEqual(files['usr/lib64/test.so']['uid'],0)
        for value in ('/../../outside','relative'):
            row[0]=value
            with self.assertRaises(c.GuardError):c.file_table('\t'.join(json.dumps(x) for x in row),'sha256',{'root':0},{'root':0})
        with self.assertRaises(c.GuardError):c.file_table(text,'unknown',{'root':0},{'root':0})
    def test_literal_filename_quotes_are_JSON_data(self):
        row=['/usr/share/a b\t$(no-exec)',stat.S_IFREG|0o644,'a'*64,'',0,'root','root']
        files=c.file_table('\t'.join(json.dumps(x) for x in row),'sha256',{'root':0},{'root':0})
        self.assertIn('usr/share/a b\t$(no-exec)',files)

class MemberAndRuntimeControls(TestCase):
    def test_listing_discovers_actual_member_without_old_hash(self):
        self.assertEqual(c.iso_member_listing("xorriso diagnostic\n'/LiveOS/squashfs.img'\n'/EFI/BOOT/BOOTX64.EFI'"),'LiveOS/squashfs.img')
    def test_missing_ambiguous_bad_quote_path_escape_member_fail(self):
        for text in ('none',"'/LiveOS/a.img'\n'/LiveOS/b.img'","'/LiveOS/a'b.img'","'/LiveOS/../outside.img'"):
            with self.subTest(text=text),self.assertRaises(c.GuardError):c.iso_member_listing(text)
    def test_wrong_small_ISO_fails_actual_bytes_gate(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'not.iso';p.write_bytes(b'wrong')
            with self.assertRaises(c.GuardError):c.iso_identity(p)
    def test_scratch_links_special_or_byte_overflow_fail(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'data').write_bytes(b'xx')
            with self.assertRaises(c.GuardError):prepare.safe_tree(p,1)
            (p/'data').unlink();(p/'linked').symlink_to('/outside')
            with self.assertRaises(c.GuardError):prepare.safe_tree(p,100)
    def test_DNF_private_paths_command_priority_and_no_runner(self):
        argv=prepare.dnf_args('do','--store=/work/goal','--action=install','tool-2-1.x86_64')
        for value in ('--no-plugins','--config=/work/config/dnf.conf','--setopt=reposdir=/work/config/repos',
            '--setopt=varsdir=/work/config/empty-vars','--setopt=install_weak_deps=true','--setopt=cacheonly=metadata'):
            self.assertIn(value,argv)
        self.assertNotIn('--offline',argv);self.assertNotIn('replay',argv);self.assertNotIn('--allowerasing',argv)
    def test_all_waits_finite_and_source_no_shell_eval(self):
        for filename in ('prepare.py','tool_checks.py','contract.py'):
            tree=ast.parse((HERE/filename).read_text())
            for node in ast.walk(tree):
                if isinstance(node,ast.Call):
                    name=node.func.attr if isinstance(node.func,ast.Attribute) else node.func.id if isinstance(node.func,ast.Name) else ''
                    self.assertNotIn(name,('eval','system'))
                    if isinstance(node.func,ast.Name):self.assertNotEqual(name,'exec')
                    if name=='wait':self.assertIn('timeout',{k.arg for k in node.keywords})
                    self.assertFalse(any(k.arg=='shell' and isinstance(k.value,ast.Constant) and k.value.value for k in node.keywords))
    def test_exact_store_and_scriptless_source_semantics_pinned(self):
        context=(HERE/'sources/dnf5-5.4.6.0-context.cpp').read_text();store=context.split('if (!transaction_store_path.empty()) {',1)[1].split('if (should_store_offline)',1)[0]
        self.assertIn('transaction.download()',store);self.assertIn('return;',store);self.assertNotIn('transaction.run()',store)
        rpm=(HERE/'sources/rpm-poptI.c').read_text();self.assertIn('(_noTransScripts | _noTransTriggers)',rpm)
        for flag in ('noscripts','notriggers','nosysusers'):self.assertIn('"'+flag+'"',rpm)
        self.assertIn('"noplugins"',(HERE/'sources/rpm-poptALL.cc').read_text())
    def test_no_actual_imports_or_build_on_module_import(self):
        self.assertNotIn('libdnf5.base',__import__('sys').modules)
        self.assertNotIn('rpm',__import__('sys').modules)
    def test_workflow_default_off_registered_discovery_job_only(self):
        text=workflow();obj=yaml.safe_load(text)
        event=obj.get('on',obj.get(True))['workflow_dispatch']['inputs']
        self.assertFalse(event['codec_tools_discovery']['default']);self.assertEqual(set(event),set(registered_inputs()))
        self.assertIn('codec-tools-discovery',obj['jobs'])
        self.assertEqual(obj['permissions'],{'contents':'read','actions':'read'})
        job=obj['jobs']['codec-tools-discovery'];self.assertEqual(job['permissions'],{'contents':'read','actions':'read'})
        self.assertFalse(any('download-artifact@' in step.get('uses','') for step in job['steps']))
        self.assertNotIn('git push',json.dumps(job));self.assertNotIn('secrets.',json.dumps(job))


    def test_actual_deployed_workflow_layout_and_audit_precedence(self):
        saved=workflow()
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);here=root/'tools/codec-tools-binding';here.mkdir(parents=True)
            deployed=root/'.github/workflows/iso.yml';deployed.parent.mkdir(parents=True);deployed.write_text(saved)
            with mock.patch.dict(globals(),{'HERE':here}):
                self.assertEqual(workflow(),saved)
                audit=here/'registered-iso-codec-tools-discovery-v3.yml';audit.write_text('MALFORMED-SELECTED-AUDIT')
                self.assertEqual(workflow(),'MALFORMED-SELECTED-AUDIT')
                self.assertNotIsInstance(yaml.safe_load(workflow()),dict)
                audit.unlink();deployed.unlink()
                with self.assertRaises(FileNotFoundError):workflow()

class OwnedHostControls(TestCase):
    def test_real_owned_python_success_and_monitor(self):
        with tempfile.TemporaryDirectory() as t:
            monitor=mock.Mock();out=prepare.invoke(['/usr/bin/python3','-c','print("ok")'],c.Deadline(time.monotonic(),10),Path(t)/'log',1,monitor)
            self.assertEqual(out,'ok\n');self.assertTrue(monitor.called)
    def test_real_owned_python_timeout_finite_records_primary(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'log'
            with self.assertRaises(prepare.PhaseFailure):prepare.invoke(['/usr/bin/python3','-c','import time;time.sleep(2)'],c.Deadline(time.monotonic(),10),p,.15)
            obj=json.loads(p.with_name('log.phase.json').read_text());self.assertIn('timeout',obj['primary_failure']['message']);self.assertEqual(obj['cleanup_failures'],[])
    def test_monitor_failure_stops_owned_child_and_keeps_primary(self):
        def monitor():raise c.GuardError('synthetic payload count cap')
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(prepare.PhaseFailure,'synthetic payload count cap'):
                prepare.invoke(['/usr/bin/python3','-c','import time;time.sleep(2)'],c.Deadline(time.monotonic(),10),Path(t)/'log',1,monitor)
    def test_failed_evidence_write_keeps_primary_and_secondary(self):
        with tempfile.TemporaryDirectory() as t,mock.patch.object(prepare,'write_json',side_effect=OSError('synthetic evidence close')):
            with self.assertRaises(prepare.PhaseFailure) as caught:
                prepare.invoke(['/usr/bin/python3','-c','raise SystemExit(2)'],c.Deadline(time.monotonic(),10),Path(t)/'log',1)
            self.assertIsNotNone(caught.exception.primary);self.assertEqual(caught.exception.secondary[0]['type'],'OSError')
    def test_partial_writer_acquisition_actual_binary_closes_first(self):
        original=Path.open;handles=[]
        def open_control(path,mode='r',*a,**kw):
            if path.name=='binary.stderr.log' and mode=='xb':raise OSError('synthetic second binary writer open')
            stream=original(path,mode,*a,**kw)
            if path.name=='raw' and mode=='xb':handles.append(stream)
            return stream
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'evidence').mkdir();(root/'work').mkdir()
            ctx={'source':'1'*40,'stage':'discovery','run':'1','attempt':'1','started':time.monotonic(),'initial_free':10**12}
            session=prepare.Session(root,ctx,bound());session.inspect=mock.Mock();session.limits=mock.Mock()
            with mock.patch.object(Path,'open',new=open_control),mock.patch.object(prepare.subprocess,'Popen') as child:
                with self.assertRaises(prepare.PhaseFailure):session.binary(['/usr/bin/rpm2cpio','/never'],root/'raw','binary')
            self.assertEqual(len(handles),1);self.assertTrue(handles[0].closed);child.assert_not_called()
    def test_real_owned_binary_bytes_do_not_decode_as_text(self):
        original=prepare.subprocess.Popen
        def own_python(argv,**kw):return original(['/usr/bin/python3','-c','import sys;sys.stdout.buffer.write(bytes([0,255,10]))'],**kw)
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'evidence').mkdir();(root/'work').mkdir()
            ctx={'source':'1'*40,'stage':'discovery','run':'1','attempt':'1','started':time.monotonic(),'initial_free':10**12}
            session=prepare.Session(root,ctx,bound());session.inspect=mock.Mock();session.limits=mock.Mock()
            with mock.patch.object(prepare.subprocess,'Popen',side_effect=own_python):session.binary(['/usr/bin/rpm2cpio','/never'],root/'raw','binary',maximum=10,timeout=1)
            self.assertEqual((root/'raw').read_bytes(),bytes([0,255,10]))


class IsolationAndPhaseControls(TestCase):
    def fixture(self,root,stage='discovery'):
        (root/'work').mkdir();(root/'work').chmod(0o777 if stage=='image' else 0o700);(root/'inputs').mkdir();(root/'inputs').chmod(0o755);root.chmod(0o700)
        data=[{'Name':'/owned','Image':c.BASE_ID,'HostConfig':{'NetworkMode':'bridge' if stage in ('metadata','closure') else 'none',
            'Privileged':False,'PidMode':'','IpcMode':'private','CapDrop':['ALL'],'ReadonlyRootfs':stage!='image',
            'PidsLimit':512,'Memory':8000000000,'MemorySwap':8000000000,'NanoCpus':4000000000,'SecurityOpt':['no-new-privileges:true']},
            'Config':{'Labels':{'arctic.tools.source':'1'*40,'arctic.tools.context':'2'*64},'User':'0:0' if stage=='image' else str(os.getuid())+':'+str(os.getgid()),'Env':['PATH=/usr/bin']},
            'Mounts':[{'Type':'bind','Source':str(src),'Destination':dst,'RW':rw} for src,dst,rw in
                ((HERE,'/source',False),(root/'work','/work',True),(root/'inputs','/input',False))]}]
        if stage=='metadata':
            aliases=root/'inputs/empty-aliases';aliases.mkdir()
            data[0]['Config']['Env']+=['DNF5_PLUGINS_DIR=/work/config/empty-cli-plugins','XDG_CONFIG_HOME=/work/config']
            data[0]['Mounts'] += [{'Type':'bind','Source':str(aliases),'Destination':target,'RW':False}
                for target in ('/usr/share/dnf5/aliases.d','/etc/dnf/dnf5-aliases.d')]
        return data
    def test_exact_three_modes_host_ancestor_and_mount_boundaries(self):
        for stage in c.STAGES:
            with tempfile.TemporaryDirectory() as t:
                root=Path(t);obj=self.fixture(root,stage)
                c.owned_container(obj,'owned','1'*40,'2'*64,c.BASE_ID,stage,root,HERE)
    def test_foreign_host_secret_cache_or_writable_source_mount_fail(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);original=self.fixture(root)
            for destination in ('/var/run/docker.sock','/root/.config','/root/.cache'):
                obj=copy.deepcopy(original);obj[0]['Mounts'].append({'Type':'bind','Source':'/host','Destination':destination,'RW':False})
                with self.assertRaises(c.GuardError):c.owned_container(obj,'owned','1'*40,'2'*64,c.BASE_ID,'discovery',root,HERE)
            for index,key,value in ((0,'RW',True),(1,'Source','/some/other/work')):
                obj=copy.deepcopy(original);obj[0]['Mounts'][index][key]=value
                with self.assertRaises(c.GuardError):c.owned_container(obj,'owned','1'*40,'2'*64,c.BASE_ID,'discovery',root,HERE)
    def test_network_policy_identity_resource_or_secret_change_fail(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);original=self.fixture(root)
            for key,value in (('NetworkMode','host'),('Privileged',True),('ReadonlyRootfs',False),('PidsLimit',513),('CapDrop',[])):
                obj=copy.deepcopy(original);obj[0]['HostConfig'][key]=value
                with self.assertRaises(c.GuardError):c.owned_container(obj,'owned','1'*40,'2'*64,c.BASE_ID,'discovery',root,HERE)
            for key,value in (('User','1001:1001'),('Env',['GH_TOKEN=synthetic']),('Env',['HTTPS_PROXY=synthetic'])):
                obj=copy.deepcopy(original);obj[0]['Config'][key]=value
                with self.assertRaises(c.GuardError):c.owned_container(obj,'owned','1'*40,'2'*64,c.BASE_ID,'discovery',root,HERE)
            obj=copy.deepcopy(original);obj[0]['Image']='sha256:'+'f'*64
            with self.assertRaises(c.GuardError):c.owned_container(obj,'owned','1'*40,'2'*64,c.BASE_ID,'discovery',root,HERE)
    def test_nonprivate_parent_and_linked_scratch_fail(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);obj=self.fixture(root);root.chmod(0o755)
            with self.assertRaises(c.GuardError):c.owned_container(obj,'owned','1'*40,'2'*64,c.BASE_ID,'discovery',root,HERE)
            root.chmod(0o700);(root/'work').rmdir();(root/'work').symlink_to(root/'inputs')
            with self.assertRaises(c.GuardError):c.owned_container(obj,'owned','1'*40,'2'*64,c.BASE_ID,'discovery',root,HERE)
    def test_mixed_discovery_preflight_has_no_metadata_Docker_read(self):
        with tempfile.TemporaryDirectory() as t:
            env={'RUNNER_TEMP':t,'TOOLS_ALL_INPUTS':json.dumps({**registered_inputs(),'release':True}),
                'GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_SHA':'1'*40}
            with mock.patch.dict(os.environ,env),mock.patch.object(prepare,'source_guard'),mock.patch.object(prepare,'official_metadata') as network, \
                    mock.patch.object(prepare.subprocess,'Popen') as docker:
                with self.assertRaisesRegex(c.GuardError,'discovery only'):prepare.preflight(Path(t)/'owned','1'*40)
            network.assert_not_called();docker.assert_not_called()
            obj=json.loads((Path(t)/'owned/evidence/preflight.json').read_text());self.assertFalse(obj['passed']);self.assertEqual(obj['actual_work'],'UNRUN')
    def test_missing_cache_layout_fails_before_any_reader(self):
        with tempfile.TemporaryDirectory() as t:
            binding=bound('closure');binding['bootstrap'].pop('cached_metadata_paths')
            session=SimpleNamespace(root=Path(t),binding=binding,copy=mock.Mock(),exec=mock.Mock())
            with self.assertRaisesRegex(c.GuardError,'unbound'):prepare.cache_catalog(session)
            session.copy.assert_not_called();session.exec.assert_not_called()
    def test_live_payload_count_bound_without_any_large_files(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);packages=root/'work/goal/packages';packages.mkdir(parents=True)
            for i in range(201):(packages/str(i)).write_bytes(b'x')
            ctx={'source':'1'*40,'stage':'closure','run':'1','attempt':'1','started':time.monotonic(),'initial_free':100000000000}
            session=prepare.Session(root,ctx,bound('closure'))
            with mock.patch.object(prepare.shutil,'disk_usage',return_value=SimpleNamespace(free=100000000000)),self.assertRaisesRegex(c.GuardError,'payload'):
                session.limits()
    def test_cleanup_uses_reserved_global_deadline_and_exact_labels(self):
        tree=ast.parse((HERE/'prepare.py').read_text());method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='cleanup')
        source=ast.get_source_segment((HERE/'prepare.py').read_text(),method)
        self.assertIn('c.MODE[self.ctx',source);self.assertIn('deadline.end-=300',source);self.assertIn('c.owned_container',source)
        self.assertNotIn('self.call(',source)


class LifecycleStopControls(TestCase):
    def run_case(self,stage,error=None,cleanup_error=None):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            for name in ('evidence','work','inputs','outputs'):(root/name).mkdir()
            ctx={'stage':stage,'source':'1'*40,'started':time.monotonic()}
            fake=SimpleNamespace(create=mock.Mock(),cleanup=mock.Mock(side_effect=cleanup_error))
            phases={name:mock.Mock(side_effect=error if name==stage else None) for name in c.STAGES}
            with mock.patch.object(prepare,'context',return_value=(root,ctx)),mock.patch.object(c,'binding_for'), \
                    mock.patch.object(prepare,'Session',return_value=fake), \
                    mock.patch.object(prepare,'discovery',phases['discovery']),mock.patch.object(prepare,'metadata',phases['metadata']),mock.patch.object(prepare,'closure',phases['closure']),mock.patch.object(prepare,'image',phases['image']):
                caught=None
                try:prepare.run(root)
                except c.GuardError as exception:caught=exception
            obj=json.loads((root/'evidence/final-observed-status.json').read_text())
            self.assertEqual({name:phase.call_count for name,phase in phases.items()},
                {name:1 if name==stage else 0 for name in c.STAGES})
            fake.create.assert_called_once();fake.cleanup.assert_called_once()
            return caught,obj
    def test_each_explicit_phase_stops_without_automatic_chain(self):
        for stage in c.STAGES:
            caught,obj=self.run_case(stage)
            self.assertIsNone(caught);self.assertTrue(obj['passed']);self.assertTrue(obj['external_review_STOP'])
    def test_failed_selected_phase_does_not_run_later_phase(self):
        for stage in c.STAGES:
            caught,obj=self.run_case(stage,c.GuardError('synthetic selected phase failure'))
            self.assertIsNotNone(caught);self.assertFalse(obj['passed']);self.assertIn('selected phase',obj['primary_failure']['message'])
    def test_primary_and_cleanup_failure_both_retained(self):
        caught,obj=self.run_case('closure',c.GuardError('original closure failed'),OSError('actual cleanup failed'))
        self.assertFalse(obj['passed']);self.assertIn('original closure failed',obj['primary_failure']['message'])
        self.assertEqual(obj['cleanup_failures'],[{'type':'OSError','message':'actual cleanup failed'}])
        self.assertIn('original closure failed',str(caught));self.assertIn('actual cleanup failed',str(caught))
    def test_cleanup_error_cannot_create_qualified_pass(self):
        caught,obj=self.run_case('discovery',cleanup_error=OSError('synthetic cleanup failure'))
        self.assertFalse(obj['passed']);self.assertIsNotNone(caught);self.assertIsNone(obj['primary_failure'])
    def test_workflow_shell_receives_source_via_literal_env_only(self):
        text=workflow();obj=yaml.safe_load(text)
        for step in obj['jobs']['codec-tools-discovery']['steps']:
            if 'run' in step:
                self.assertNotIn('${{ inputs.codec_tools_source_sha }}',step['run'])
                self.assertIn('--source "$TOOLS_SOURCE_SHA"',step['run'])
                self.assertEqual(step['env']['TOOLS_SOURCE_SHA'],'${{ inputs.codec_tools_source_sha }}')


class ImageInputAndAttemptControls(TestCase):
    def controlled_image(self,mutation=None,already_attempted=False):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            for name in ('work','inputs/closure/packages','outputs','evidence'):(root/name).mkdir(parents=True,exist_ok=True)
            goal,old,catalog,goals=goal_fixture();item=catalog[next(iter(catalog))]
            payload=b'synthetic signed-input bytes (crypto mocked)';item['bytes']=len(payload);item['sha256']=hashlib.sha256(payload).hexdigest()
            incoming,replaced,after=c.stored_goal(goal,old,catalog,goals)
            state={name:c.manifest_digest([]) for name in ('usr/lib/sysimage/rpm','usr/lib/sysimage/libdnf5')}
            data={'status':'SIGNED_CLOSURE_EXTERNAL_REVIEW_STOP','before_headers':old,'expected_after_headers':after,
                'state_manifest':state,'goal':goal,'selected_catalog':catalog}
            manifest=[{'name':item['name'],'evr':item['evr'],'arch':item['arch'],'filename':Path(item['location']).name,
                'bytes':item['bytes'],'sha256':item['sha256'],'expected_full_signer':c.FEDORA}]
            inside=root/'inputs/closure';(inside/'packages'/manifest[0]['filename']).write_bytes(payload)
            for name,obj in (('closure-report.json',data),('payload-manifest.json',manifest),('before-headers.json',old),('state-manifest.json',state)):
                c.write_json(inside/name,obj)
            binding=bound('image');binding['tool_root_goals']=goals
            for name,key in (('closure-report.json','report_sha256'),('payload-manifest.json','payload_manifest_sha256'),
                    ('before-headers.json','before_headers_sha256'),('state-manifest.json','state_manifest_sha256')):
                binding['closure'][key]=c.sha_file(inside/name)
            if mutation:mutation(root,binding)
            if already_attempted:c.write_json(root/'work/single-tools-transaction.json',{'attempts':1})
            calls=[]
            def copy(inside,dest,tag):dest.mkdir()
            def execute(argv,tag,timeout=120):
                calls.append(argv)
                if argv[0]=='/usr/bin/mkdir':(root/'work/keys').mkdir()
                if '-U' in argv:
                    self.assertTrue((root/'work/single-tools-transaction.json').is_file())
                    for flag in ('--noscripts','--notriggers','--noplugins','--nosysusers'):self.assertIn(flag,argv)
                    raise c.GuardError('synthetic single transaction failure')
                return 'synthetic crypto mocked'
            session=SimpleNamespace(root=root,binding=binding,name='owned-image',copy=copy,exec=execute)
            with mock.patch.object(prepare,'bootstrap_guard'),mock.patch.object(prepare,'header_rows',return_value=old), \
                    mock.patch.object(c,'iso_identity') as iso,mock.patch.object(prepare,'verify_signature_result') as crypto:
                caught=None
                try:prepare.image(session)
                except c.GuardError as error:caught=error
            self.assertIsNotNone(caught)
            return str(caught),len([argv for argv in calls if '-U' in argv]),crypto.call_count,iso.call_count
    def test_only_one_transaction_uses_marker_and_exact_scriptless_flags(self):
        error,count,crypto,iso=self.controlled_image()
        self.assertIn('single transaction failure',error);self.assertEqual((count,crypto,iso),(1,1,1))
    def test_stale_attempt_never_submits_again(self):
        error,count,crypto,iso=self.controlled_image(already_attempted=True)
        self.assertIn('already attempted',error);self.assertEqual((count,crypto),(0,0))
    def test_wrong_payload_bytes_fail_before_any_signature_or_transaction(self):
        def mutate(root,binding):next((root/'inputs/closure/packages').iterdir()).write_bytes(b'wrong')
        error,count,crypto,iso=self.controlled_image(mutation=mutate)
        self.assertIn('payload bytes differ',error);self.assertEqual((count,crypto,iso),(0,0,0))
    def test_wrong_bound_report_or_extra_RPM_fail_before_transaction(self):
        def bad_hash(root,binding):binding['closure']['report_sha256']='0'*64
        error,count,crypto,iso=self.controlled_image(mutation=bad_hash);self.assertIn('identities differ',error);self.assertEqual(count,0)
        def extra(root,binding):(root/'inputs/closure/packages/extra.rpm').write_bytes(b'x')
        error,count,crypto,iso=self.controlled_image(mutation=extra);self.assertIn('extra/missing',error);self.assertEqual((count,crypto),(0,0))
    def test_missing_before_state_identity_never_reaches_transaction(self):
        def mutate(root,binding):(root/'inputs/closure/state-manifest.json').write_text('{}')
        error,count,crypto,iso=self.controlled_image(mutation=mutate)
        self.assertIn('state binding differs',error);self.assertEqual((count,crypto),(0,0))

class SuccessorBoundaryControls(TestCase):
    def catalog(self, arches=('x86_64','i686','noarch','src'), checksum='sha256'):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);work=root/'work';cache=work/'cache';cache.mkdir(parents=True)
            packages=[]
            for arch in arches:
                packages.append('<package><name>unrelated-'+arch+'</name><arch>'+arch+'</arch>'+
                    '<version epoch="0" ver="1" rel="1.fc44"/><checksum type="'+checksum+'">'+'a'*64+'</checksum>'+
                    '<size package="10"/><location href="Packages/u/unrelated-'+arch+'-1-1.fc44.'+arch+'.rpm"/>'+
                    '<format><rpm:license>MIT</rpm:license><rpm:sourcerpm>unrelated-1-1.fc44.src.rpm</rpm:sourcerpm></format></package>')
            primary=('<metadata xmlns="http://linux.duke.edu/metadata/common" xmlns:rpm="http://linux.duke.edu/metadata/rpm">'+''.join(packages)+'</metadata>').encode()
            compressed={'repomd':b'synthetic repomd','primary':b'compressed fixture','filelists':b'compressed filelists'}
            expanded={'primary':primary,'filelists':b'<filelists/>'}
            for name,data in compressed.items():(cache/name).write_bytes(data)
            digest=lambda data:hashlib.sha256(data).hexdigest()
            metadata={'repomd_bytes':len(compressed['repomd']),'repomd_sha256':digest(compressed['repomd']),
                'metadata':{n:{'bytes':len(compressed[n]),'sha256':digest(compressed[n]),'open_bytes':len(expanded[n]),
                    'open_sha256':digest(expanded[n])} for n in expanded}}
            session=SimpleNamespace(root=root,binding={'repositories':{'only':metadata},'bootstrap':{
                'cached_metadata_paths':{'only':{n:'cache/'+n for n in compressed}},'zstd_file_sha256':digest(b'synthetic zstd')}},count=0,limits=mock.Mock())
            def copy_binary(relative,path,tag):session.count+=1;path.write_bytes(b'synthetic zstd')
            def execute(argv,tag,timeout):
                kind=argv[-1].rsplit('/',1)[-1];(work/('only-'+kind+'.xml')).write_bytes(expanded[kind]);return ''
            session.copy_binary=copy_binary;session.exec=execute
            return prepare.cache_catalog(session)
    def test_actual_catalog_ignores_only_unselected_multilib_and_source_rows(self):
        catalog=self.catalog()
        self.assertEqual({r['arch'] for r in catalog.values()},{'x86_64','noarch'})
        self.assertEqual(len(catalog),2)
        self.assertEqual(self.catalog(('i686','src')), {})
    def test_catalog_checksum_gate_is_retained_for_unselected_rows(self):
        with self.assertRaisesRegex(c.GuardError,'checksum'):self.catalog(('i686',),checksum='sha1')
    def test_selected_unsupported_arch_fails_even_if_catalog_includes_it(self):
        for arch in ('i686','src','aarch64'):
            obj,old,catalog,goals=goal_fixture();item=catalog.pop('tool-2-1.fc44.x86_64');item['arch']=arch
            identity=c.nevra((item['name'],item['evr'],arch));catalog[identity]=item;obj['rpms'][1]['nevra']=identity
            obj['rpms'][1]['package_path']='./packages/'+Path(item['location']).name
            with self.subTest(arch=arch),self.assertRaisesRegex(c.GuardError,'selected tools architecture'):
                c.stored_goal(obj,old,catalog,goals)
    def test_shared_json_has_exact_readable_mode_under_restrictive_umask(self):
        previous=os.umask(0o077)
        try:
            with tempfile.TemporaryDirectory() as t:
                root=Path(t);root.chmod(0o700);work=root/'work';work.mkdir();work.chmod(0o777)
                p=work/'shared.json';c.readable_json(p,{'non_secret':'literal'})
                self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o644)
                self.assertEqual(p.stat().st_uid,os.getuid());self.assertEqual(stat.S_IMODE(root.stat().st_mode),0o700)
                self.assertEqual(json.loads(p.read_text()),{'non_secret':'literal'})
        finally:os.umask(previous)
    def test_shared_json_rejects_stale_link_or_failed_permission_change(self):
        previous=os.umask(0o077)
        try:
            with tempfile.TemporaryDirectory() as t:
                root=Path(t);p=root/'data';c.readable_json(p,{'first':True})
                with self.assertRaises(FileExistsError):c.readable_json(p,{'overwrite':True})
                link=root/'link';link.symlink_to(p)
                with self.assertRaisesRegex(c.GuardError,'linked evidence'):c.readable_json(link,{})
                fresh=root/'failed'
                with mock.patch.object(Path,'chmod',side_effect=OSError('synthetic mode failure')),self.assertRaisesRegex(OSError,'mode failure'):
                    c.readable_json(fresh,{})
                self.assertEqual(stat.S_IMODE(fresh.stat().st_mode),0o600)
                self.assertEqual(json.loads(p.read_text()),{'first':True})
        finally:os.umask(previous)
    def test_actual_image_handoffs_are_readable_under_umask0077(self):
        previous=os.umask(0o077);observed=[];original=c.readable_json
        def record(path,data):
            original(path,data);observed.append((Path(path).name,stat.S_IMODE(Path(path).stat().st_mode)))
        try:
            with mock.patch.object(c,'readable_json',side_effect=record):
                ImageInputAndAttemptControls().controlled_image()
            self.assertEqual(observed,[('approved-closure-report.json',0o644),('approved-payload-manifest.json',0o644)])
        finally:os.umask(previous)
    def test_actual_image_run_context_and_root_output_are_readable(self):
        previous=os.umask(0o077);observed=[];original=c.readable_json
        def record(path,data):
            original(path,data);observed.append((Path(path).name,stat.S_IMODE(Path(path).stat().st_mode)))
        try:
            with mock.patch.object(c,'readable_json',side_effect=record):LifecycleStopControls().run_case('image')
            self.assertEqual(observed,[('host-context.json',0o644)])
            with tempfile.TemporaryDirectory() as t:
                root=Path(t);c.write_json(root/'host-context.json',{'started':time.monotonic()})
                with mock.patch.dict(os.environ,{'GH_TOKEN':'','GITHUB_TOKEN':'','HTTP_PROXY':'','HTTPS_PROXY':''}), \
                        mock.patch.object(tool_checks,'WORK',root),mock.patch.object(tool_checks,'package_file_proofs',return_value=({}, {}, {})), \
                        mock.patch.object(tool_checks,'private_API_checks',return_value={}),mock.patch.object(tool_checks,'reader_and_crypto_controls',return_value={}):
                    tool_checks.main()
                self.assertEqual(stat.S_IMODE((root/'tool-image-manifest.json').stat().st_mode),0o644)
        finally:os.umask(previous)
    def creation_fixture(self,root):
        obj=IsolationAndPhaseControls().fixture(root)
        ctx={'source':'1'*40,'stage':'discovery','run':'finite-synthetic','attempt':'1','started':time.monotonic(),'initial_free':10**12}
        (root/'evidence').mkdir();c.write_json(root/'context.json',ctx)
        session=prepare.Session(root,ctx,bound());session.name='owned';session.limits=mock.Mock()
        obj[0]['Config']['Labels']['arctic.tools.context']=c.sha_file(root/'context.json')
        config=json.loads((HERE/'sources/tools-base-amd64-config.json').read_text())
        image={'Id':c.BASE_ID,'Architecture':'amd64','Os':'linux','RootFS':{'Layers':config['rootfs']['diff_ids']}}
        return session,obj,image
    def test_successful_side_effect_then_phase_report_failure_still_exactly_cleans(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);session,obj,image=self.creation_fixture(root);owned=root/'owned-side-effect'
            original=prepare.invoke;write=prepare.write_json;calls=[]
            def broken_report(path,data):
                if Path(path).name=='synthetic-create.log.phase.json':raise OSError('synthetic post-create evidence failure')
                return write(path,data)
            def call(argv,tag,timeout=180):
                if tag=='immutable-base-inspect':return json.dumps([image])
                if tag=='create':
                    with mock.patch.object(prepare,'write_json',side_effect=broken_report):
                        return original(['/usr/bin/python3','-B','-c','from pathlib import Path;Path(__import__("sys").argv[1]).write_text("owned")',str(owned)],
                            session.deadline,root/'evidence/synthetic-create.log',1)
                return ''
            def cleanup_invoke(argv,deadline,path,limit=300,monitor=None):
                calls.append(argv)
                if 'inspect' in argv:self.assertTrue(owned.exists());return json.dumps(obj)
                self.assertIn('rm',argv);owned.unlink();return ''
            session.call=call
            with self.assertRaisesRegex(prepare.PhaseFailure,'post-create evidence failure'):session.create()
            self.assertTrue(session.created);self.assertTrue(owned.exists())
            with mock.patch.object(prepare,'invoke',side_effect=cleanup_invoke):session.cleanup()
            self.assertFalse(owned.exists());self.assertFalse(session.created);self.assertEqual(len(calls),2)
    def test_provisional_create_cleanup_never_removes_unproved_foreign_resource(self):
        for fault in ('absent','foreign','linked'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as t:
                root=Path(t);session,obj,image=self.creation_fixture(root);session.created=True;calls=[]
                if fault=='foreign':obj[0]['Config']['Labels']['arctic.tools.source']='2'*40
                if fault=='linked':(root/'work').rmdir();(root/'work').symlink_to(root/'inputs')
                def inspect(argv,deadline,path,limit=300,monitor=None):
                    calls.append(argv)
                    if fault=='absent':raise prepare.PhaseFailure(c.GuardError('synthetic no such owned container'),[])
                    return json.dumps(obj)
                with mock.patch.object(prepare,'invoke',side_effect=inspect),self.assertRaises((c.GuardError,prepare.PhaseFailure)):
                    session.cleanup()
                self.assertEqual(len(calls),1);self.assertNotIn('rm',calls[0]);self.assertTrue(session.created)

class RegisteredDiscoveryControls(TestCase):
    def test_only_exact_registered_discovery_inputs_are_admitted(self):
        self.assertEqual(c.registered_discovery_inputs(registered_inputs(),'1'*40),'discovery')
        for key in ('release','draft','boot_test','nix_acceptance','performance_acceptance',
                'same_iso_recovery','same_iso_native_smoke','same_iso_pcmanfm_diagnostic'):
            with self.subTest(key=key),self.assertRaisesRegex(c.GuardError,'discovery only'):
                c.registered_discovery_inputs({**registered_inputs(),key:True},'1'*40)
        for key in ('offline_cycle_recovery','safe_visual_diagnostic','codec_evaluation','tools_binding','preparation'):
            with self.subTest(key=key),self.assertRaisesRegex(c.GuardError,'unknown/missing/mixed'):
                c.registered_discovery_inputs({**registered_inputs(),key:False},'1'*40)
    def test_malformed_source_tag_bool_or_missing_input_fails(self):
        for key,value in (('codec_tools_discovery',False),('boot_test','false'),('tag','v1'),('prerelease','true'),
                ('codec_tools_source_sha','2'*40),('codec_tools_source_sha','$(unsafe)')):
            with self.subTest(key=key),self.assertRaises(c.GuardError):
                c.registered_discovery_inputs({**registered_inputs(),key:value},'1'*40)
        data=registered_inputs();data.pop('draft')
        with self.assertRaises(c.GuardError):c.registered_discovery_inputs(data,'1'*40)
    def test_all_old_workflow_steps_inputs_and_default_behavior_are_preserved(self):
        baseline=(HERE/'sources/registered-iso-baseline-aee90aea.yml').read_text();old=yaml.safe_load(baseline)
        selected=workflow();new=yaml.safe_load(selected)
        old_inputs=old.get('on',old.get(True))['workflow_dispatch']['inputs']
        new_inputs=new.get('on',new.get(True))['workflow_dispatch']['inputs']
        self.assertEqual({k:new_inputs[k] for k in old_inputs},old_inputs)
        self.assertEqual(set(new_inputs)-set(old_inputs),{'codec_tools_discovery','codec_tools_source_sha','codec_tools_metadata_check'})
        self.assertEqual(len(new['jobs']),len(old['jobs'])+2)
        reconstructed=selected.split('\n  codec-tools-discovery:\n',1)[0]
        for name,before in old['jobs'].items():
            after=copy.deepcopy(new['jobs'][name]);old_if=before['if']
            expression=old_if.removeprefix('${{').removesuffix('}}').strip()
            expected='${{ ('+expression+') && !inputs.codec_tools_discovery && !inputs.codec_tools_metadata_check }}'
            self.assertEqual(after.pop('if'),expected);expected_before=copy.deepcopy(before);expected_before.pop('if')
            self.assertEqual(after,expected_before)
            reconstructed=reconstructed.replace('    if: '+expected,'    if: '+old_if,1)
        addition='''      codec_tools_metadata_check:
        description: Private DNF plugin/alias/config/cache metadata identities only; external review STOP (no RPM download or solve)
        type: boolean
        default: false
      codec_tools_discovery:
        description: Read immutable tools base identity only; artifact-only external review STOP
        type: boolean
        default: false
      codec_tools_source_sha:
        description: Exact reviewed discovery execution commit
        type: string
        default: ''
'''
        reconstructed=reconstructed.replace(addition,'',1)
        self.assertEqual(reconstructed,baseline)
        for key in old:
            if key not in ('jobs','on',True):self.assertEqual(new[key],old[key])
    def test_discovery_job_cannot_download_fixed_ISO_or_run_later_stages(self):
        job=yaml.safe_load(workflow())['jobs']['codec-tools-discovery']
        self.assertEqual(job['if'],"${{ github.event_name == 'workflow_dispatch' && inputs.codec_tools_discovery && !inputs.codec_tools_metadata_check }}")
        self.assertEqual(job['timeout-minutes'],35)
        self.assertFalse(any('download-artifact@' in step.get('uses','') for step in job['steps']))
        for step in job['steps']:
            if 'run' in step:
                self.assertNotIn('closure',step['run']);self.assertNotIn('image',step['run']);self.assertNotIn('build',step['run'])
        preflight=job['steps'][1]
        self.assertEqual(preflight['env']['TOOLS_ALL_INPUTS'],'${{ toJSON(inputs) }}')
        self.assertEqual([step['timeout-minutes'] for step in job['steps'] if 'upload-artifact@' in step.get('uses','')],[1,4])
    def test_exact_prior_review_binding_and_later_nulls_are_preserved(self):
        data=json.loads((HERE/'runtime-binding.json').read_text())
        self.assertEqual(data['status'],'SOURCE_REVIEW_BOUND');self.assertEqual(data['execution_review_sha256'],c.sha_file(HERE/'independent-source-review.json'))
        self.assertEqual(data['execution_review_sha256'],'458e4d0e1256b3a8e0d5dbb4d74c7cb862f18c9c8c3337b1cdf249d7a726b476')
        self.assertIsNone(data['bootstrap']);self.assertIsNone(data['closure'])
        self.assertIsNone(data['candidate']['archived_member_path']);self.assertIsNone(data['candidate']['archived_member_sha256'])
        for stage in ('closure','image'):
            with self.assertRaisesRegex(c.GuardError,'STOP'):c.binding_for(stage,data)
    def test_changed_bound_review_fails_before_any_Docker_or_metadata_read(self):
        with tempfile.TemporaryDirectory() as t:
            here=Path(t)/'source';here.mkdir();shutil=__import__('shutil')
            shutil.copyfile(HERE/'runtime-binding.json',here/'runtime-binding.json')
            (here/'independent-source-review.json').write_text('{}')
            env={'RUNNER_TEMP':t,'TOOLS_ALL_INPUTS':json.dumps(registered_inputs()),'GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_SHA':'1'*40}
            with mock.patch.dict(os.environ,env),mock.patch.object(prepare,'HERE',here),mock.patch.object(prepare,'source_guard'), \
                    mock.patch.object(prepare,'official_metadata') as network,mock.patch.object(prepare.subprocess,'Popen') as process:
                with self.assertRaisesRegex(c.GuardError,'review bytes'):prepare.preflight(Path(t)/'owned','1'*40)
            network.assert_not_called();process.assert_not_called()
    def test_source_guard_requires_actual_head_cleanliness_bytes_and_Git_modes(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);here=root/'tools/codec-tools-binding';here.mkdir(parents=True)
            names=['tools/codec-tools-binding/prepare.py','.github/workflows/iso.yml']+['tools/codec-tools-binding/data'+str(i) for i in range(8)]
            files={}
            for name in names:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('literal owned source\n');p.chmod(0o755 if name.endswith('prepare.py') else 0o644)
                files[name]={'sha256':c.sha_file(p),'git_mode':'100755' if name.endswith('prepare.py') else '100644'}
            c.write_json(here/'execution-pins.json',{'schema':'arctic-codec-tools-preparation-execution-v1','files':files})
            def git(directory,*args):
                if args[0]=='rev-parse':return '1'*40
                if args[0]=='status':return ''
                return files[args[-1]]['git_mode']+' '+('0'*40)+' 0 '+args[-1]
            with mock.patch.object(prepare,'HERE',here),mock.patch.object(prepare,'git',side_effect=git):prepare.source_guard('1'*40)
            with mock.patch.object(prepare,'HERE',here),mock.patch.object(prepare,'git',return_value='2'*40),self.assertRaisesRegex(c.GuardError,'dirty/wrong'):
                prepare.source_guard('1'*40)
            (root/names[0]).write_text('changed source')
            with mock.patch.object(prepare,'HERE',here),mock.patch.object(prepare,'git',side_effect=git),self.assertRaisesRegex(c.GuardError,'changed/unsafe'):
                prepare.source_guard('1'*40)
            (root/names[0]).write_text('literal owned source\n')
            for fault in ('dirty','mode'):
                def bad_git(directory,*args):
                    if fault=='dirty' and args[0]=='status':return ' M tracked-source'
                    if fault=='mode' and args[0]=='ls-files':return '100600 '+('0'*40)+' 0 '+args[-1]
                    return git(directory,*args)
                with self.subTest(fault=fault),mock.patch.object(prepare,'HERE',here),mock.patch.object(prepare,'git',side_effect=bad_git),self.assertRaises(c.GuardError):
                    prepare.source_guard('1'*40)

class ObservedOptionalTagControls(TestCase):
    def actual(self):
        path=HERE/'sources/actual-inputs-37573011277.json'
        self.assertEqual(c.sha_file(path),'b0844bba5fc4d5b89664ce29c81ab04dbd417e0e1415dba6d39f2a008be8f922')
        return json.loads(path.read_text())
    def test_exact_actual_logged_context_and_explicit_empty_default_both_pass(self):
        data=self.actual();before=copy.deepcopy(data);source=data['codec_tools_source_sha']
        self.assertEqual(len(data),11);self.assertNotIn('tag',data)
        self.assertEqual(c.registered_discovery_inputs(data,source),'discovery')
        self.assertEqual(c.registered_discovery_inputs({**data,'tag':''},source),'discovery')
        self.assertEqual(data,before)
    def test_optional_default_does_not_admit_invalid_explicit_tags(self):
        data=self.actual();source=data['codec_tools_source_sha']
        for tag in (None,False,0,[],{},'v1',' ','\x00','$(literal)'):
            with self.subTest(tag_type=type(tag).__name__),self.assertRaisesRegex(c.GuardError,'tag/metadata'):
                c.registered_discovery_inputs({**data,'tag':tag},source)
    def test_every_missing_required_field_unknown_key_and_selected_mode_still_fails(self):
        data=self.actual();source=data['codec_tools_source_sha']
        for name in data:
            modified={k:v for k,v in data.items() if k!=name}
            with self.subTest(missing=name),self.assertRaisesRegex(c.GuardError,'unknown/missing/mixed'):
                c.registered_discovery_inputs(modified,source)
        for name in ('unexpected','safe_visual_diagnostic','offline_cycle_recovery','preparation','bootstrap'):
            with self.subTest(extra=name),self.assertRaisesRegex(c.GuardError,'unknown/missing/mixed'):
                c.registered_discovery_inputs({**data,name:False},source)
        for name in ('release','draft','boot_test','nix_acceptance','performance_acceptance',
                'same_iso_recovery','same_iso_native_smoke','same_iso_pcmanfm_diagnostic'):
            with self.subTest(selected=name),self.assertRaisesRegex(c.GuardError,'discovery only'):
                c.registered_discovery_inputs({**data,name:True},source)
    def test_actual_context_reaches_only_preflight_with_real_prior_review_bytes(self):
        data=self.actual();source=data['codec_tools_source_sha']
        with tempfile.TemporaryDirectory() as t:
            envfile=Path(t)/'env';env={'RUNNER_TEMP':t,'TOOLS_ALL_INPUTS':json.dumps(data),
                'GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_SHA':source,'GITHUB_RUN_ID':'actual-context-fixture',
                'GITHUB_RUN_ATTEMPT':'1','GITHUB_ENV':str(envfile),**{k:'' for k in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH','DOCKER_CONFIG')}}
            with mock.patch.dict(os.environ,env),mock.patch.object(prepare,'source_guard') as guard, \
                    mock.patch.object(prepare.shutil,'disk_usage',return_value=SimpleNamespace(free=24000000000)), \
                    mock.patch.object(prepare,'official_metadata') as network,mock.patch.object(prepare.subprocess,'Popen') as process:
                prepare.preflight(Path(t)/'owned',source)
            guard.assert_called_once_with(source);network.assert_not_called();process.assert_not_called()
            observed=json.loads((Path(t)/'owned/evidence/preflight.json').read_text())
            self.assertTrue(observed['passed']);self.assertEqual(observed['actual_work'],'UNRUN')
            context=json.loads((Path(t)/'owned/context.json').read_text());self.assertEqual(context['stage'],'discovery')
            self.assertIn('TOOLS_ROOT=',envfile.read_text());self.assertNotIn('TOOLS_CLOSURE',envfile.read_text())

class MetadataPrerequisiteControls(TestCase):
    def selected(self):
        return {**registered_inputs(),'codec_tools_discovery':False,'codec_tools_metadata_check':True}
    def test_actual_optional_tag_defaults_and_metadata_route_are_literal(self):
        data=self.selected();self.assertEqual(c.registered_discovery_inputs(data,'1'*40),'metadata')
        data.pop('tag');self.assertEqual(c.registered_discovery_inputs(data,'1'*40),'metadata')
        for value in (None,False,0,[],{},'v1',' ','\x00'):
            with self.subTest(tag=value),self.assertRaises(c.GuardError):
                c.registered_discovery_inputs({**data,'tag':value},'1'*40)
        actual=json.loads((HERE/'sources/actual-inputs-37573011277.json').read_text())
        self.assertEqual(c.registered_discovery_inputs(actual,actual['codec_tools_source_sha']),'discovery')
    def test_metadata_selectors_missing_required_unknown_and_mixed_fail(self):
        original=self.selected()
        for key in original:
            if key=='tag':continue
            data={k:v for k,v in original.items() if k!=key}
            with self.subTest(missing=key),self.assertRaises(c.GuardError):c.registered_discovery_inputs(data,'1'*40)
        for key,value in (('codec_tools_discovery',True),('codec_tools_metadata_check',False),('codec_tools_metadata_check','true'),
                ('codec_tools_metadata_check',None),('codec_tools_metadata_check',1),('release',True),('boot_test',True),
                ('same_iso_recovery',True),('same_iso_native_smoke',True),('same_iso_pcmanfm_diagnostic',True),
                ('draft',True),('performance_acceptance',True),('nix_acceptance',True),('codec_tools_source_sha','2'*40)):
            with self.subTest(key=key,value=value),self.assertRaises(c.GuardError):c.registered_discovery_inputs({**original,key:value},'1'*40)
        for key in ('offline_cycle_recovery','safe_visual_diagnostic','codec_evaluation','preparation','bootstrap'):
            with self.assertRaises(c.GuardError):c.registered_discovery_inputs({**original,key:False},'1'*40)
    def test_metadata_binding_admits_only_reviewed_discovery_and_no_later_permission(self):
        data=json.loads((HERE/'runtime-binding.json').read_text());c.binding_for('metadata',data)
        for key,value in (('scope','SIGNED_CLOSURE'),('report_sha256',None),('review_sha256','bad'),
                ('report_file','../report.json'),('rpm_version','6.0.1'),('dnf5_version','5.3'),('file_hashes',{})):
            changed=copy.deepcopy(data);changed['metadata_prerequisite'][key]=value
            with self.subTest(key=key),self.assertRaises(c.GuardError):c.binding_for('metadata',changed)
        for key in ('bootstrap','closure'):
            changed=copy.deepcopy(data);changed[key]={}
            with self.assertRaises(c.GuardError):c.binding_for('metadata',changed)
        for stage in ('closure','image'):
            with self.assertRaisesRegex(c.GuardError,'STOP'):c.binding_for(stage,data)
    def test_actual_metadata_preflight_has_no_Docker_or_metadata_side_effect(self):
        with tempfile.TemporaryDirectory() as t:
            env={'RUNNER_TEMP':t,'TOOLS_ALL_INPUTS':json.dumps(self.selected()),'GITHUB_EVENT_NAME':'workflow_dispatch',
                'GITHUB_SHA':'1'*40,'GITHUB_RUN_ID':'metadata-fixture','GITHUB_RUN_ATTEMPT':'1','GITHUB_ENV':str(Path(t)/'env'),
                **{k:'' for k in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH','DOCKER_CONFIG')}}
            with mock.patch.dict(os.environ,env),mock.patch.object(prepare,'source_guard'), \
                    mock.patch.object(prepare.shutil,'disk_usage',return_value=SimpleNamespace(free=24000000000)), \
                    mock.patch.object(prepare,'official_metadata') as network,mock.patch.object(prepare.subprocess,'Popen') as process:
                prepare.preflight(Path(t)/'fresh','1'*40)
            process.assert_not_called();network.assert_not_called()
            root=Path(t)/'fresh';self.assertEqual(json.loads((root/'context.json').read_text())['stage'],'metadata')
            self.assertTrue(json.loads((root/'evidence/preflight.json').read_text())['passed'])
    def test_metadata_create_sets_preparse_paths_and_only_owned_alias_overlays(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            for relative in ('work','inputs'):(root/relative).mkdir()
            session=prepare.Session(root,{'run':'finite','attempt':'1','stage':'metadata','source':'1'*40,'started':time.monotonic()},bound('metadata'))
            (root/'context.json').write_text('{}');calls=[]
            def call(argv,tag,timeout):
                calls.append((argv,tag))
                if tag=='immutable-base-inspect':return json.dumps([{'Id':c.BASE_ID,'Architecture':'amd64','Os':'linux',
                    'RootFS':{'Layers':json.loads((HERE/'sources/tools-base-amd64-config.json').read_text())['rootfs']['diff_ids']}}])
                return ''
            session.call=call;session.inspect=mock.Mock();session.create()
            argv=next(argv for argv,tag in calls if tag=='create')
            self.assertIn('DNF5_PLUGINS_DIR=/work/config/empty-cli-plugins',argv)
            self.assertEqual(argv[argv.index('--network')+1],'bridge');self.assertIn('--read-only',argv)
            for target in ('/usr/share/dnf5/aliases.d','/etc/dnf/dnf5-aliases.d'):
                self.assertIn('type=bind,src='+str(root/'inputs/empty-aliases')+',dst='+target+',readonly',argv)
            self.assertFalse(any((root/'inputs/empty-aliases').iterdir()))
    def test_metadata_inspection_rejects_nonempty_writable_wrong_alias_or_duplicate_environment(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);obj=IsolationAndPhaseControls().fixture(root,'metadata')
            for change in ('nonempty','writable','wrong-target','missing','duplicate-env','wrong-plugin-dir'):
                row=copy.deepcopy(obj)
                if change=='nonempty':(root/'inputs/empty-aliases/untrusted').write_text('synthetic')
                if change=='writable':row[0]['Mounts'][-1]['RW']=True
                if change=='wrong-target':row[0]['Mounts'][-1]['Destination']='/other'
                if change=='missing':row[0]['Mounts'].pop()
                if change=='duplicate-env':row[0]['Config']['Env'].append('DNF5_PLUGINS_DIR=/work/config/empty-cli-plugins')
                if change=='wrong-plugin-dir':row[0]['Config']['Env'][-2]='DNF5_PLUGINS_DIR=/usr/lib64/dnf5/plugins'
                with self.subTest(change=change),self.assertRaises(c.GuardError):c.owned_container(row,'owned','1'*40,'2'*64,c.BASE_ID,'metadata',root,HERE)
                if change=='nonempty':(root/'inputs/empty-aliases/untrusted').unlink()
    def fixture_cache(self,work):
        repositories={}
        for repo in ('fedora','updates'):
            cache=work/'cache'/repo;cache.mkdir(parents=True)
            plain={kind:('<'+kind+'>'+repo+'</'+kind+'>').encode() for kind in ('primary','filelists')}
            compressed={kind:('synthetic compressed '+repo+' '+kind).encode() for kind in plain}
            repomd=('<repomd>'+repo+'</repomd>').encode();(cache/'repomd.xml').write_bytes(repomd)
            for kind,body in compressed.items():(cache/(kind+'.zst')).write_bytes(body)
            (cache/'primary.xml').write_bytes(plain['primary'])
            digest=lambda value:hashlib.sha256(value).hexdigest()
            repositories[repo]={'repomd_bytes':len(repomd),'repomd_sha256':digest(repomd),'metadata':{kind:{
                'bytes':len(compressed[kind]),'sha256':digest(compressed[kind]),'open_bytes':len(plain[kind]),
                'open_sha256':digest(plain[kind])} for kind in plain}}
        return repositories
    def test_cache_receipts_match_exact_compressed_and_plain_bytes_separately(self):
        with tempfile.TemporaryDirectory() as t:
            work=Path(t);repos=self.fixture_cache(work)
            proof=prepare.metadata_cache_receipts(work,repos,c.Deadline(time.monotonic(),10),mock.Mock())
            self.assertEqual(len(proof['private_cache_entries']),8)
            for repo in repos:
                self.assertEqual({row['representation'] for row in proof['matching_snapshot_files'][repo]['primary']},{'compressed','plain-XML'})
                self.assertEqual(proof['matching_snapshot_files'][repo]['filelists'][0]['representation'],'compressed')
                self.assertEqual(proof['matching_snapshot_files'][repo]['repomd'][0]['representation'],'repomd-XML')
    def test_cache_missing_corrupt_duplicate_snapshot_link_and_expired_deadline_fail_or_remain_unmatched(self):
        with tempfile.TemporaryDirectory() as t:
            work=Path(t);repos=self.fixture_cache(work)
            (work/'cache/fedora/filelists.zst').write_bytes(b'corrupt')
            proof=prepare.metadata_cache_receipts(work,repos,c.Deadline(time.monotonic(),10),mock.Mock())
            self.assertEqual(proof['matching_snapshot_files']['fedora']['filelists'],[])
            (work/'cache/linked').symlink_to(work/'cache/fedora/repomd.xml')
            with self.assertRaises(c.GuardError):prepare.metadata_cache_receipts(work,repos,c.Deadline(time.monotonic(),10),mock.Mock())
            (work/'cache/linked').unlink()
            with self.assertRaises(c.GuardError):prepare.metadata_cache_receipts(work,repos,c.Deadline(time.monotonic()-10,1),mock.Mock())
    def chain(self,change=None):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);here=root/'source';here.mkdir()
            for relative in ('outputs','evidence','inputs/empty-aliases','work/config/empty-cli-plugins','work/config/dnf5/aliases.d'):
                (root/relative).mkdir(parents=True,exist_ok=True)
            bodies={name:('synthetic inert '+name).encode() for name in c.BOOTSTRAP_TOOLS}
            if change!='alias-literals':bodies['usr/bin/dnf5']+=b'/usr/share/dnf5/aliases.d\x00/etc/dnf/dnf5-aliases.d\x00'
            headers=[['fixture','0:1-1.fc44','noarch','fixture.src.rpm','MIT']]
            report={'status':'DISCOVERY_ONLY_EXTERNAL_REVIEW_STOP','observed_only':True,'resolve_download_transaction':False,
                'member_work':'UNRUN','base_image_id':c.BASE_ID,'headers':headers,'file_identities':{
                name:{'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body)} for name,body in bodies.items()}}
            review={'status':'PASS_ACTUAL_DISCOVERY_OBSERVATIONS_EXTERNAL_REVIEW_STOP','run_id':123,'source':'2'*40}
            if change=='review-source':review['source']='3'*40
            if change=='review-status':review['status']='UNREVIEWED'
            if change=='review-run':review['run_id']=124
            for name,data in (('discovery-report.json',report),('discovery-review.json',review)):(here/name).write_text(json.dumps(data))
            binding=bound('metadata');binding['metadata_prerequisite'].update(report_sha256=c.sha_file(here/'discovery-report.json'),
                review_sha256=c.sha_file(here/'discovery-review.json'),file_hashes={name:row['sha256'] for name,row in report['file_identities'].items()},
                run_id=123,source='2'*40)
            state={'usr/lib/sysimage/rpm':b'private rpm state','usr/lib/sysimage/libdnf5':b'private dnf state'}
            calls=[];session=SimpleNamespace(root=root,binding=binding,deadline=c.Deadline(time.monotonic(),10),limits=mock.Mock())
            def copy(inside,destination,tag):
                if inside.lstrip('/') in state:
                    destination.mkdir();(destination/'fixture-state').write_bytes(state[inside.lstrip('/')])
                else:destination.write_bytes(b'synthetic system identity')
            session.copy=copy
            session.copy_os_release=lambda destination,tag:copy('/etc/os-release',destination,tag)
            def body(relative,destination,tag):
                destination.write_bytes((b'wrong body' if change=='body' and relative=='usr/bin/dnf5' else bodies.get(relative,b'synthetic zstd')))
            session.copy_binary=body
            def execute(argv,tag,timeout=120):
                calls.append((argv,tag))
                if argv[0]=='/usr/bin/rpm':return '\n'.join('\t'.join(row) for row in headers)+'\n'
                if tag=='isolated-CLI-version':
                    return 'dnf5 version 5.4.6.0\ndnf5 plugin API version 2.0\nlibdnf5 version 5.4.6.0\nlibdnf5 plugin API version 2.2\n'+('Loaded dnf5 plugins:\n' if change=='plugins' else '')
                if 'config' in tag:
                    parser=prepare.configparser.ConfigParser();parser.read(root/'work/config/dnf.conf');values=dict(parser['main']);values['config_file_path']='/work/config/dnf.conf'
                    if change=='config':values['plugins']='true'
                    if change=='after-config' and tag.endswith('after-metadata'):values['best']='false'
                    return ''.join(key+' = '+value+'\n' for key,value in values.items())
                self.assertEqual(tag,'fixed-Fedora-metadata-only-cache')
                binding['repositories']=self.fixture_cache(root/'work')
                if change=='cache':(root/'work/cache/fedora/filelists.zst').write_bytes(b'corrupt')
                if change=='duplicate':(root/'work/cache/fedora/duplicate.zst').write_bytes((root/'work/cache/fedora/filelists.zst').read_bytes())
                if change=='state':(root/'work/installroot/usr/lib/sysimage/rpm/fixture-state').write_bytes(b'changed state')
                if change=='goal':(root/'work/goal/packages').mkdir()
                if change=='aliases':(root/'inputs/empty-aliases/untrusted').write_bytes(b'changed alias')
                return 'metadata cached\n'
            session.exec=execute
            caught=None
            with mock.patch.object(prepare,'HERE',here):
                try:prepare.metadata(session)
                except c.GuardError as error:caught=error
            outputs=list((root/'outputs').iterdir());result=json.loads(outputs[0].read_text()) if outputs else None
            return caught,result,calls
    def test_complete_actual_function_chain_stops_without_goal_package_or_later_phase(self):
        caught,result,calls=self.chain();self.assertIsNone(caught)
        self.assertEqual(result['status'],'METADATA_CONFIG_EXTERNAL_REVIEW_STOP')
        self.assertFalse(result['RPM_payload_downloads']);self.assertFalse(result['solve_store_transaction_scripts'])
        self.assertFalse(result['later_bootstrap_closure_bindings_automatically_written'])
        self.assertEqual(result['Python_libdnf5_API_controls'],'UNRUN_until_separately_reviewed_signed_tools_image')
        self.assertEqual(len([tag for argv,tag in calls if tag=='fixed-Fedora-metadata-only-cache']),1)
        for argv,tag in calls:
            self.assertNotIn('do',argv);self.assertFalse(any('--store=' in arg or arg=='--import' for arg in argv))
    def test_body_plugin_config_failures_occur_before_any_metadata_access(self):
        for change in ('body','alias-literals','review-source','review-status','review-run','plugins','config'):
            with self.subTest(change=change):
                caught,result,calls=self.chain(change);self.assertIsNotNone(caught);self.assertIsNone(result)
                self.assertFalse(any(tag=='fixed-Fedora-metadata-only-cache' for argv,tag in calls))
    def test_snapshot_private_state_goal_alias_or_after_config_failure_never_yields_STOP_pass(self):
        for change in ('cache','duplicate','state','goal','aliases','after-config'):
            with self.subTest(change=change):
                caught,result,calls=self.chain(change);self.assertIsNotNone(caught);self.assertIsNone(result)
    def test_generated_metadata_job_is_default_off_exclusive_artifact_only_and_uses_actual_preflight(self):
        obj=yaml.safe_load(workflow());inputs=obj.get('on',obj.get(True))['workflow_dispatch']['inputs']
        self.assertFalse(inputs['codec_tools_metadata_check']['default'])
        job=obj['jobs']['codec-tools-metadata']
        self.assertEqual(job['if'],"${{ github.event_name == 'workflow_dispatch' && inputs.codec_tools_metadata_check }}")
        self.assertEqual(job['timeout-minutes'],35);self.assertEqual(job['permissions'],{'contents':'read','actions':'read'})
        for name,old in obj['jobs'].items():
            if name not in ('codec-tools-metadata','codec-tools-discovery'):self.assertIn('!inputs.codec_tools_metadata_check',old['if'])
        self.assertIn('!inputs.codec_tools_metadata_check',obj['jobs']['codec-tools-discovery']['if'])
        self.assertEqual(job['steps'][1]['env']['TOOLS_ALL_INPUTS'],'${{ toJSON(inputs) }}')
        for step in job['steps']:
            self.assertNotIn('download-artifact@',step.get('uses',''))
            if 'run' in step:self.assertIn('tools/codec-tools-binding/prepare.py',step['run'])
        text=ast.get_source_segment(Path(prepare.__file__).read_text(),next(node for node in ast.parse(Path(prepare.__file__).read_text()).body if isinstance(node,ast.FunctionDef) and node.name=='metadata'))
        for forbidden in ('closure(session)','image(session)','--store=','do\'',"'--import'",'official_metadata'):
            self.assertNotIn(forbidden,text)

if __name__=='__main__':unittest.main()
