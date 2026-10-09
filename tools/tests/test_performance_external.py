"""Adversarial full replay controls; no VM or invented runtime result."""
import copy
import ast
import json
import os
from pathlib import Path
import py_compile
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import performance_external_fixture as F

runner = F.load('external_runner_controls', F.ROOT/'tools/performance/qualification.py')


class ExternalReplayTest(unittest.TestCase):
    def validate(self, entries, kwargs):
        with F.archive(entries) as archive:
            return F.contract.validate_evidence(archive, **kwargs)

    def test_real_composer_and_all_six_original_serials_replay(self):
        entries, kwargs = F.fixture()
        result = self.validate(entries, kwargs)
        self.assertEqual(result['original_serials_replayed'], 6)
        self.assertEqual(result['comparison']['status'], 'regression_gate_passed')
        self.assertFalse(result['release_acceptance'])

    def test_missing_truncated_or_redacted_original_inputs_fail(self):
        for fault in ('missing', 'truncated', 'redacted', 'observer_bytes'):
            entries, kwargs = F.fixture()
            name = 'runs/candidate/1/serial-boot.log'
            if fault == 'missing': entries.pop(name)
            elif fault == 'truncated': entries[name] = entries[name][:4000]
            elif fault == 'observer_bytes': entries['observer-source.txt'] += b'\n# replaced\n'
            F.reseal(entries)
            if fault == 'redacted':
                screen = json.loads(entries['upload-screening.json'])
                screen['files'][name]['redactions'] = 1
                entries['upload-screening.json'] = F.encoded(screen)
            with self.subTest(fault=fault), self.assertRaises(ValueError): self.validate(entries, kwargs)

    def test_source_attempt_resources_order_profiles_and_integer_types_are_bound(self):
        for fault in ('run', 'head', 'parent', 'attempt', 'bool_attempt', 'float_attempt', 'tcg',
                      'recheck', 'order', 'bool_boot', 'bool_exit', 'float_bytes', 'profile', 'toolchain', 'container'):
            entries, kwargs = F.fixture()
            execution, state = (json.loads(entries[name]) for name in ('execution.json','status.json'))
            if fault == 'run': execution['run_id'] += 1
            elif fault == 'head': execution['execution_source_sha'] = '3'*40
            elif fault == 'parent': execution['reviewed_parent_sha'] = '3'*40
            elif fault == 'attempt': execution['run_attempt'] = 2
            elif fault == 'bool_attempt': execution['run_attempt'] = True
            elif fault == 'float_attempt': execution['run_attempt'] = 1.0
            elif fault == 'tcg': state['acceleration'] = 'tcg'
            elif fault == 'recheck': state['input_images_rechecked'] = False
            elif fault == 'order': state['runs'][0],state['runs'][1]=state['runs'][1],state['runs'][0]
            elif fault == 'bool_boot': state['runs'][0]['boot'] = True
            elif fault == 'bool_exit': state['runs'][0]['harness_exit'] = False
            elif fault == 'float_bytes': state['images']['candidate']['bytes'] = 1000.0
            elif fault == 'profile': state['profiles']['candidate']['sha256'] = '6'*64
            elif fault == 'toolchain': entries['runs/candidate/1/vm-toolchain.txt'] += b'changed\n'
            elif fault == 'container':state['vm_prepared_image_id']='sha256:'+'6'*64
            entries['execution.json'],entries['status.json']=F.encoded(execution),F.encoded(state)
            F.reseal(entries)
            with self.subTest(fault=fault), self.assertRaises(ValueError): self.validate(entries, kwargs)

    def test_equal_attacker_observer_hashes_and_repeated_guest_boot_ids_fail(self):
        for fault in ('observer', 'boot_id', 'context', 'late_metadata'):
            entries, kwargs = F.fixture()
            for name in list(entries):
                if not name.endswith('/serial-boot.log'): continue
                text=entries[name].decode()
                if fault == 'observer':
                    text=text.replace(kwargs['plan']['observer']['source_sha256'],'6'*64)
                elif fault == 'boot_id':
                    import re
                    text=re.sub(r'00000000-0000-0000-0000-[0-9a-f]{12}',
                                '00000000-0000-0000-0000-000000000001',text)
                elif fault == 'context':
                    text=text.replace('"image_source_sha": "'+kwargs['image']['source_sha']+'"',
                                      '"image_source_sha": "'+'6'*40+'"')
                else:
                    text=text.replace('"app_id": "foot", "client_address"',
                                      '"app_id": "other-app", "client_address"')
                entries[name]=text.encode()
            F.reseal(entries)
            with self.subTest(fault=fault), self.assertRaises(ValueError): self.validate(entries,kwargs)

    def test_duplicate_json_canonical_records_nonfinite_and_completion_fail(self):
        name='runs/candidate/1/serial-boot.log'
        for fault in ('duplicate_json','duplicate_record','nan','exit_missing','exit_duplicate','collection_missing'):
            entries,kwargs=F.fixture(); text=entries[name].decode()
            if fault=='duplicate_json':text=text.replace('"check": "identity"','"check": "identity", "check": "identity"',1)
            elif fault=='duplicate_record':
                text+='\n'+next(line for line in text.splitlines() if '"check": "identity"' in line)+'\n'
            elif fault=='nan':text=text.replace('"median": 0.3','"median": NaN',1)
            elif fault=='exit_missing':text=text.replace('ARCTIC-INSTALLED-SMOKE-EXIT=0\n','')
            elif fault=='exit_duplicate':text+='ARCTIC-INSTALLED-SMOKE-EXIT=0\n'
            else:text=text.replace('ARCTIC-COLLECT-END\n','')
            entries[name]=text.encode(); F.reseal(entries)
            with self.subTest(fault=fault),self.assertRaises(ValueError):self.validate(entries,kwargs)

    def test_resealed_original_appid_removal_alias_or_getter_kind_cannot_qualify(self):
        name='runs/candidate/1/serial-boot.log'
        for fault in ('missing','malformed_alias','intermediate_alias','type','copied_only_v11'):
            entries,kwargs=F.fixture()
            lines=entries[name].decode().splitlines()
            for index,line in enumerate(lines):
                if not line.startswith('ARCTIC-PERFORMANCE '):continue
                record=json.loads(line[len('ARCTIC-PERFORMANCE '):])
                if record['check']!='startup_role_terminal_cold_seconds':continue
                proof=record['value']['observation_bounds'][0]['causal_lower_bound']
                event=proof['matched_upper_events'][0]
                if fault=='missing':event.pop('original_app_id')
                elif fault=='malformed_alias':event['original_app_id']='foot'+'\u0080'*4091
                elif fault=='intermediate_alias':event['original_app_id']=event['foreign_toplevel_id']
                elif fault=='type':event['client_type']=2
                else:proof['method']='wlroots-0.20-and-mango-managed-list-native-bracket-raw-v3'
                lines[index]='ARCTIC-PERFORMANCE '+json.dumps(record)
                break
            else:self.fail('Synthetic original serial lacks the native role bound')
            entries[name]=('\n'.join(lines)+'\n').encode()
            F.reseal(entries)
            with self.subTest(fault=fault),self.assertRaises(ValueError):self.validate(entries,kwargs)

    def test_forged_success_summary_cannot_hide_precision_or_regression(self):
        for fault in ('precision','regression','boolean_report'):
            entries,kwargs=F.fixture()
            if fault=='boolean_report':
                report=json.loads(entries['comparison.json'])
                report['metrics'][0]['per_boot']['candidate'][0]=True
                entries['comparison.json']=F.encoded(report)
            else:
                for name in list(entries):
                    if '/candidate/' not in name or not name.endswith('/serial-boot.log'):continue
                    text=entries[name].decode()
                    if fault=='regression':text=text.replace('"median": 0.3','"median": 0.331',1)
                    else:text=text.replace('"interval_seconds": 0.0002500000000000002',
                                           '"interval_seconds": 0.1')
                    entries[name]=text.encode()
            F.reseal(entries)
            with self.subTest(fault=fault),self.assertRaises(ValueError):self.validate(entries,kwargs)

    def test_oversized_producer_receipt_is_rejected_before_any_raw_read(self):
        entries,kwargs=F.fixture()
        with F.archive(entries) as original:
            class Oversized:
                def infolist(self):return original.infolist()
                def getinfo(self,name):
                    info=copy.copy(original.getinfo(name))
                    if name=='producer-receipt.json':info.file_size=32769
                    return info
                def read(self,name):
                    if name=='producer-receipt.json':raise AssertionError('Read oversized producer receipt')
                    return original.read(name)
            with self.assertRaisesRegex(ValueError,'Oversized producer receipt'):
                F.contract.validate_evidence(Oversized(),**kwargs)

    def test_preparation_plan_and_actual_source_hashes_have_distinct_checks(self):
        entries,kwargs=F.fixture(); plan=copy.deepcopy(kwargs['plan']); plan['ready']=False
        F.contract.validate_plan(plan,candidate_source_files=plan['candidate_source_files'],
            execution_files=plan['execution_files'],observer=plan['observer'])
        with self.assertRaises(ValueError):self.validate(entries,dict(kwargs,plan=plan))
        changed=dict(plan['candidate_source_files']);changed['shell/AppsService.qml']='5'*64
        with self.assertRaises(ValueError):F.contract.validate_plan(plan,candidate_source_files=changed,
            execution_files=plan['execution_files'],observer=plan['observer'])


class ActivationTest(unittest.TestCase):
    def git(self, root, *args):
        return subprocess.check_output(['git','-C',str(root),*args],text=True,stderr=subprocess.DEVNULL).strip()

    def bundle(self, root, fault):
        root.mkdir()
        self.git(root,'init','-q')
        self.git(root,'config','user.name','Performance fixture')
        self.git(root,'config','user.email','fixture@example.invalid')
        for name in F.contract.EXECUTION_FILES:
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
            if name in ('tools/performance/guest.py','tools/performance/causal.py','tools/performance/compare.py',
                        'tools/performance/contract.py','tools/performance/fixtures/v1.2-offline.toml'):
                path.write_bytes((F.ROOT/name).read_bytes())
            else:path.write_text('# synthetic activation fixture; never executed\n')
        _,kwargs=F.fixture();plan=copy.deepcopy(kwargs['plan'])
        plan['execution_files']={name:F.contract.digest((root/name).read_bytes()) for name in F.contract.EXECUTION_FILES}
        plan['observer']=F.contract.observer_hashes(root)
        manifest=root/F.contract.MANIFEST
        manifest.write_bytes(F.encoded(plan))
        self.git(root,'add','.')
        self.git(root,'commit','-qm','Reviewed fixture')
        parent=self.git(root,'rev-parse','HEAD')
        marker=root/F.contract.MARKER
        marker.write_bytes((parent+('' if fault=='newline' else '\n')).encode())
        self.git(root,'add',F.contract.MARKER)
        self.git(root,'commit','-qm','Single-marker fixture activation')
        head=self.git(root,'rev-parse','HEAD')
        if fault=='merge':
            tree=self.git(root,'rev-parse','HEAD^{tree}')
            other=self.git(root,'commit-tree',tree,'-p',parent,'-m','Another fixture parent')
            head=self.git(root,'commit-tree',tree,'-p',parent,'-p',other,'-m','Merge activation is invalid')
            self.git(root,'reset','--hard',head)
        elif fault=='hidden_source':
            self.git(root,'update-index','--assume-unchanged','tools/performance/guest.py')
            (root/'tools/performance/guest.py').write_text('# changed hidden source\n')
        elif fault=='hidden_manifest':
            self.git(root,'update-index','--assume-unchanged',F.contract.MANIFEST)
            manifest.write_bytes(F.encoded(plan)+b' \n')
        event=root.parent/'event.json';event.write_bytes(F.encoded(dict(before=parent,after=head)))
        env=dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',
            GITHUB_REPOSITORY='yuvalkolodkingal/Arctic-Linux',GITHUB_REF='refs/heads/'+F.contract.BRANCH,
            GITHUB_EVENT_NAME='push',GITHUB_RUN_ATTEMPT='2' if fault=='rerun' else '1',GITHUB_RUN_ID='31',
            GITHUB_WORKFLOW='Frozen exact-image paired performance qualification',GITHUB_SHA=head,GITHUB_EVENT_PATH=str(event))
        return manifest,env

    def test_actual_git_marker_child_passes_and_merge_rerun_or_hidden_blobs_fail(self):
        for fault in (None,'merge','newline','rerun','hidden_source','hidden_manifest'):
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory)/'execution';manifest,env=self.bundle(root,fault)
                with patch.object(runner,'ROOT',root),patch.dict(os.environ,env):
                    if fault:
                        with self.subTest(fault=fault),self.assertRaises(ValueError):runner.activation(manifest)
                    else:self.assertTrue(runner.activation(manifest)[0]['ready'])

    def test_loader_compiles_verified_bytes_despite_timestamp_matching_poisoned_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.git(root,'init','-q')
            self.git(root,'config','user.name','Performance fixture')
            self.git(root,'config','user.email','fixture@example.invalid')
            path=root/'helper.py';path.write_text('value="trusted"\n')
            self.git(root,'add','helper.py');self.git(root,'commit','-qm','Trusted helper fixture')
            path.write_text('value="poison!"\n')
            stat=path.stat();py_compile.compile(str(path),doraise=True)
            path.write_text('value="trusted"\n');os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
            with patch.object(runner,'ROOT',root):
                self.assertEqual(runner.load('verified_fixture_helper',path).value,'trusted')

    def test_loader_rejects_drift_and_symlink_before_executing_sentinel(self):
        for fault in ('drift','symlink'):
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);self.git(root,'init','-q')
                self.git(root,'config','user.name','Performance fixture')
                self.git(root,'config','user.email','fixture@example.invalid')
                path=root/'helper.py';path.write_text('value="trusted"\n')
                self.git(root,'add','helper.py');self.git(root,'commit','-qm','Trusted helper fixture')
                sentinel='raise AssertionError("unverified code executed")\n'
                if fault=='drift':path.write_text(sentinel)
                else:
                    other=root/'sentinel.py';other.write_text(sentinel)
                    path.unlink();path.symlink_to(other)
                with patch.object(runner,'ROOT',root),self.subTest(fault=fault),self.assertRaises(ValueError):
                    runner.load('unverified_fixture_helper',path)

    def test_dispatch_request_has_exact_nine_typed_external_fields_and_no_release(self):
        text=(F.ROOT/'.github/workflows/qualification-20261008-dispatch.yml').read_text()
        program=text.split("python3 -B - <<'PY'\n",1)[1].split('\n          PY',1)[0]
        import textwrap
        node=next(node for node in ast.parse(textwrap.dedent(program)).body if isinstance(node,ast.Assign)
            and any(isinstance(target,ast.Name) and target.id=='inputs' for target in node.targets))
        namespace=dict(source='a'*40)
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<actual reviewed dispatch request>','exec'),namespace)
        actual=namespace['inputs']
        expected=dict(release=False,tag='',prerelease=True,draft=False,boot_test=True,nix_acceptance=False,
            performance_acceptance=False,performance_mode=F.contract.MODE,expected_source_sha='a'*40)
        self.assertTrue(F.contract.same(actual,expected))


if __name__=='__main__':unittest.main()
