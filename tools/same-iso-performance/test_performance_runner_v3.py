"""No VM/API controls for the fixed-image performance mode and source identity."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('performance_recovery',HERE/'performance-runner-v3.py')
P = importlib.util.module_from_spec(spec); spec.loader.exec_module(P)
controller_spec = importlib.util.spec_from_file_location('performance_controller',
    HERE/'tools/performance/run-paired.py' if (HERE/'tools').exists()
    else HERE.parents[1]/'tools/performance/run-paired.py')
C = importlib.util.module_from_spec(controller_spec); controller_spec.loader.exec_module(C)


def workflow_text():
    return (HERE/'iso-performance-v3.yml').read_text() if (HERE/'iso-performance-v3.yml').exists() else (
        HERE.parents[1]/'.github/workflows/iso.yml').read_text()


def workflow_step(text, name):
    block = text.split('  same-iso-performance:\n', 1)[1]
    return block.split('      - name: '+name+'\n', 1)[1].split('      - name: ', 1)[0]


def ci():
    return dict(GITHUB_ACTIONS='true',GITHUB_EVENT_NAME='workflow_dispatch',
        GITHUB_REPOSITORY=P.R.REPOSITORY,GITHUB_API_URL='https://api.github.com',
        GITHUB_SHA='b'*40,GITHUB_RUN_ID='9999',GITHUB_RUN_ATTEMPT='1',
        PERFORMANCE_MODE='true',RECOVERY_MODE='false',RELEASE_REQUESTED='false',CONTAINER_ENGINE='docker')


def original():
    run=dict(id=P.R.ORIGINAL_RUN,run_attempt=1,head_sha=P.R.SOURCE,name='ISO',
             status='completed',conclusion='failure')
    job=dict(id=112420067268,run_id=P.R.ORIGINAL_RUN,head_sha=P.R.SOURCE,steps=[
        dict(name='Nix enforcing VM acceptance',number=12,status='completed',conclusion='failure'),
        dict(name='Paired KVM performance acceptance',number=14,status='completed',conclusion='failure')])
    artifact=dict(id=P.R.ARTIFACT_ID,name=P.R.ARTIFACT_NAME,expired=False,
        size_in_bytes=P.R.ARCHIVE_BYTES,digest=P.R.ARCHIVE_DIGEST,
        workflow_run=dict(id=P.R.ORIGINAL_RUN,head_sha=P.R.SOURCE))
    return run,[job],artifact


class PerformanceRunnerTest(unittest.TestCase):
    def test_mode_requires_supported_ci_docker_and_single_selected_mode(self):
        P.validate_ci(ci())
        for key,value in [('PERFORMANCE_MODE','false'),('RECOVERY_MODE','true'),
                ('RELEASE_REQUESTED','true'),('CONTAINER_ENGINE','podman'),
                ('CONTAINER_ENGINE','/tmp/fake-engine'),('GITHUB_EVENT_NAME','push'),
                ('GITHUB_REPOSITORY','foreign/repo'),('GITHUB_SHA',P.R.SOURCE),
                ('GITHUB_SHA',P.QUALIFICATION_BASE),('GITHUB_RUN_ID',str(P.R.ORIGINAL_RUN))]:
            env=ci();env[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(RuntimeError):P.validate_ci(env)

    def test_recovery_requires_actual_original_paired_failure(self):
        proof=P.validate_performance_failure(*original())
        self.assertEqual(proof['performance_step_number'],14)
        for fault in ('active','pass','missing','duplicate','source','artifact','bytes'):
            run,jobs,artifact=original()
            if fault=='active':run.update(status='in_progress',conclusion=None)
            elif fault=='pass':jobs[0]['steps'][1]['conclusion']='success'
            elif fault=='missing':jobs[0]['steps'].pop()
            elif fault=='duplicate':jobs[0]['steps'].append(copy.deepcopy(jobs[0]['steps'][1]))
            elif fault=='source':run['head_sha']='c'*40
            elif fault=='artifact':artifact['id']+=1
            else:artifact['size_in_bytes']-=1
            with self.subTest(fault=fault),self.assertRaises(RuntimeError):P.validate_performance_failure(run,jobs,artifact)

    def test_image_source_identity_uses_clean_source_checkout_not_execution_head(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp);(source/'shell').mkdir()
            (source/'shell/AppsService.qml').write_text('image catalog')
            (source/'shell/BatteryService.qml').write_text('image battery')
            with patch.object(C.subprocess,'check_output',side_effect=[P.R.SOURCE,'',P.R.SOURCE[:7]]) as query:
                identity=C.candidate_source_identity(source)
            self.assertEqual(identity['commit'],P.R.SOURCE)
            self.assertEqual(identity['catalog_sha256'],P.R.digest(source/'shell/AppsService.qml'))
            self.assertTrue(all(call.kwargs['cwd']==source for call in query.call_args_list))
            with patch.object(C.subprocess,'check_output',side_effect=[P.R.SOURCE,' M shell/AppsService.qml']):
                with self.assertRaisesRegex(RuntimeError,'clean/pinned'):C.candidate_source_identity(source)

    def test_actual_controller_timeout_reaps_owned_child_and_propagates(self):
        with tempfile.TemporaryDirectory() as tmp:
            log=Path(tmp)/'timeout.log';observed=[];actual=subprocess.Popen
            def record(*a,**kw):
                child=actual(*a,**kw);observed.append(child);return child
            with patch.object(P.subprocess,'Popen',side_effect=record):
                with self.assertRaises(subprocess.TimeoutExpired):
                    P.execute_controller([sys.executable,'-c','import time;time.sleep(30)'],
                                         log,Path(tmp),dict(os.environ),seconds=.05)
            self.assertEqual(len(observed),1);self.assertIsNotNone(observed[0].poll())

    def test_baseline_download_is_fixed_and_hashes_actual_bytes_before_any_vm(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'baseline';calls=[]
            def download(argv,**kwargs):
                calls.append(argv)
                (folder/(P.BASELINE_ISO+'.part00')).write_bytes(b'part0')
                (folder/(P.BASELINE_ISO+'.part01')).write_bytes(b'part1')
                return subprocess.CompletedProcess(argv,0)
            with patch.object(P.subprocess,'run',side_effect=download):
                with self.assertRaisesRegex(RuntimeError,'byte count/hash'):P.download_baseline(folder)
            self.assertEqual(calls[0][:6],['gh','release','download','v1.2.0','--repo',P.R.REPOSITORY])
            self.assertEqual(calls[0][-4:],['--pattern',P.BASELINE_ISO+'.part00','--pattern',P.BASELINE_ISO+'.part01'])
            with self.assertRaisesRegex(RuntimeError,'unused'):P.download_baseline(folder)

    def test_emergency_cleanup_requires_exact_owned_task_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'frozen-observer.py').write_text('frozen observer')
            task='a'*32;name='arctic-paired-'+task+'-'+'b'*8
            state=dict(task_id=task,observer_sha256=P.R.digest(folder/'frozen-observer.py'),
                images=dict(candidate=dict(sha256=P.R.ISO_SHA256),baseline=dict(sha256=P.BASELINE_SHA)))
            (folder/'status.json').write_text(json.dumps(state))
            with (folder/'cleanup.log').open('w') as log:
                with patch.object(P.subprocess,'check_output',return_value=name+'\n'),patch.object(P.subprocess,'run') as removal:
                    P.cleanup_task_containers(folder,log)
                self.assertEqual(removal.call_args.args[0],['docker','rm','--force',name])
                for invalid in ('foreign-app','arctic-paired-'+'c'*32+'-'+'b'*8,name+'-foreign'):
                    with patch.object(P.subprocess,'check_output',return_value=invalid+'\n'),patch.object(P.subprocess,'run') as removal:
                        with self.subTest(invalid=invalid),self.assertRaises(RuntimeError):P.cleanup_task_containers(folder,log)
                        removal.assert_not_called()
                for key,value in [('task_id','../../foreign'),('observer_sha256','f'*64)]:
                    changed=dict(state);changed[key]=value;(folder/'status.json').write_text(json.dumps(changed))
                    with patch.object(P.subprocess,'check_output') as listing:
                        with self.subTest(key=key),self.assertRaises(RuntimeError):P.cleanup_task_containers(folder,log)
                        listing.assert_not_called()

    def test_workflow_skips_build_and_both_recovery_jobs_when_only_performance(self):
        text=workflow_text()
        self.assertIn('!inputs.same_iso_recovery && !inputs.same_iso_performance',text)
        self.assertEqual(text.count("inputs.same_iso_recovery && !inputs.same_iso_performance }}"),2)
        block=text.split('  same-iso-performance:\n',1)[1]
        self.assertIn('artifact-ids: 11434226349',block)
        self.assertIn('run-id: 37507582946',block)
        self.assertNotIn('contents: write',block)
        self.assertNotIn('build-iso',block);self.assertNotIn('test-iso.sh',block)
        self.assertIn('timeout-minutes: 230',block)
        self.assertIn('!${{ env.PERFORMANCE_ROOT }}/evidence/**/*.qcow2',block)

    def test_registered_execution_checkout_has_profile_and_full_ancestor_history(self):
        def guards(text):
            step=workflow_step(text,'Checkout separate reviewed execution checker')
            self.assertRegex(step,r'(?m)^          fetch-depth: 0$')
            sparse=step.split('          sparse-checkout: |\n',1)[1]
            self.assertIn('            profiles/ci\n',sparse)
            self.assertIn('            tools\n',sparse)
            self.assertIn('            .github/workflows\n',sparse)
        text=workflow_text();guards(text)
        for changed in (text.replace('          fetch-depth: 0\n','',1),
                        text.replace('          fetch-depth: 0\n','          fetch-depth: 1\n',1),
                        text.replace('            .github/workflows\n            profiles/ci\n',
                                     '            .github/workflows\n',1)):
            with self.subTest(change=changed[-200:]),self.assertRaises(AssertionError):guards(changed)

    def test_actual_missing_sparse_profile_fails_harness_before_container(self):
        tools=HERE/'tools' if (HERE/'tools').exists() else HERE.parents[1]/'tools'
        spec=importlib.util.spec_from_file_location('actual_sparse_harness',tools/'tests/test_performance_harness.py')
        harness=importlib.util.module_from_spec(spec);spec.loader.exec_module(harness)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'tools/lib').mkdir(parents=True)
            for relative in ('test-install.sh','lib/container.sh','performance/guest.py'):
                destination=root/'tools'/relative;destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(tools/relative,destination)
            case=harness.PerformanceHarnessTest()
            with patch.object(harness,'ROOT',root):
                result,call,_,_=case.capture()
                self.assertNotEqual(result.returncode,0);self.assertIsNone(call)
                self.assertIn('no profile at '+str(root/'profiles/ci/offline.toml'),result.stderr)
                (root/'profiles/ci').mkdir(parents=True)
                profile=(HERE/'profiles/ci/offline.toml' if (HERE/'profiles').exists()
                         else HERE.parents[1]/'profiles/ci/offline.toml')
                shutil.copy2(profile,root/'profiles/ci/offline.toml')
                result,call,values,_=case.capture()
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertIsNotNone(call);self.assertEqual(values['COLLECT_VIA'],'console')

    def test_actual_shallow_history_cannot_prove_existing_ancestor_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);origin=root/'origin'
            def git(*args,cwd=None):
                return subprocess.run(['git',*args],cwd=cwd,check=True,capture_output=True,text=True,timeout=20)
            git('init','--quiet',str(origin))
            git('config','user.name','Synthetic history control',cwd=origin)
            git('config','user.email','history-control@example.invalid',cwd=origin)
            for value in ('base','middle','execution'):
                (origin/'fixture').write_text(value);git('add','fixture',cwd=origin)
                git('commit','--quiet','-m',value,cwd=origin)
                if value=='base':ancestor=git('rev-parse','HEAD',cwd=origin).stdout.strip()
            head=git('rev-parse','HEAD',cwd=origin).stdout.strip()
            for depth in (1,0):
                checkout=root/('depth-'+str(depth))
                git('clone','--quiet',*(['--depth','1'] if depth else []),origin.as_uri(),str(checkout))
                result=subprocess.run(['git','-C',str(checkout),'merge-base','--is-ancestor',ancestor,head],
                    capture_output=True,text=True,timeout=20)
                self.assertEqual(result.returncode,128 if depth else 0,result.stderr)

    def test_actual_disk_preparation_has_fixed_hosted_scope_and_preserves_space_gate(self):
        text=workflow_text();step=workflow_step(text,'Prepare disk space on the fresh hosted runner')
        script='\n'.join(line[10:] for line in step.split('        run: |\n',1)[1].splitlines())
        subprocess.run(['bash','-n'],input=script,text=True,check=True,capture_output=True)
        self.assertLess(text.index('Prepare disk space on the fresh hosted runner'),
                        text.index('Require original failed comparison and exact frozen inputs'))
        self.assertIn('${{ env.PERFORMANCE_ROOT }}/runner-disk-preparation.log',text)
        self.assertIn('shutil.disk_usage(args.evidence).free >= 40_000_000_000',
                      (HERE/'performance-runner-v3.py').read_text())
        fixed=['/usr/share/dotnet','/usr/local/lib/android','/opt/ghc','/opt/hostedtoolcache/CodeQL',
               '/usr/local/share/boost','/usr/local/share/powershell','/usr/share/swift']
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fake=root/'bin';fake.mkdir();calls=root/'calls.jsonl'
            program='''#!/usr/bin/env python3
import json,os,sys
with open(os.environ['PREPARATION_CALLS'],'a') as output:
    output.write(json.dumps([os.path.basename(sys.argv[0]),*sys.argv[1:]])+'\\n')
'''
            for name in ('sudo','df'):
                path=fake/name;path.write_text(program);path.chmod(0o755)
            for fault in (None,'GITHUB_ACTIONS','RUNNER_ENVIRONMENT','RUNNER_OS'):
                folder=root/str(fault);folder.mkdir();calls.unlink(missing_ok=True)
                env=dict(os.environ,PATH=str(fake)+os.pathsep+os.environ['PATH'],
                    PREPARATION_CALLS=str(calls),PERFORMANCE_ROOT=str(folder),RUNNER_TEMP=str(root),
                    GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',RUNNER_OS='Linux',
                    AGENT_TOOLSDIRECTORY='/must-not-remove-dynamic-cache')
                if fault:env[fault]='unsupported'
                result=subprocess.run(['bash','-c',script],env=env,capture_output=True,text=True,timeout=10)
                if fault:
                    self.assertNotEqual(result.returncode,0);self.assertFalse(calls.exists())
                else:
                    self.assertEqual(result.returncode,0,result.stderr)
                    actual=[json.loads(row) for row in calls.read_text().splitlines()]
                    self.assertEqual(actual,[['df','-B1','/',str(root)],
                                            ['sudo','rm','-rf','--',*fixed],
                                            ['df','-B1','/',str(root)]])
                    self.assertTrue((folder/'runner-disk-preparation.log').is_file())


if __name__=='__main__':unittest.main()
