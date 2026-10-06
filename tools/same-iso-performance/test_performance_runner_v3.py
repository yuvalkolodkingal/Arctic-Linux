"""No VM/API controls for the fixed-image performance mode and source identity."""
import copy
import importlib.util
import json
import os
from pathlib import Path
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
        text=(HERE/'iso-performance-v3.yml').read_text() if (HERE/'iso-performance-v3.yml').exists() else (
            HERE.parents[1]/'.github/workflows/iso.yml').read_text()
        self.assertIn('!inputs.same_iso_recovery && !inputs.same_iso_performance',text)
        self.assertEqual(text.count("inputs.same_iso_recovery && !inputs.same_iso_performance }}"),2)
        block=text.split('  same-iso-performance:\n',1)[1]
        self.assertIn('artifact-ids: 11434226349',block)
        self.assertIn('run-id: 37507582946',block)
        self.assertNotIn('contents: write',block)
        self.assertNotIn('build-iso',block);self.assertNotIn('test-iso.sh',block)
        self.assertIn('timeout-minutes: 230',block)
        self.assertIn('!${{ env.PERFORMANCE_ROOT }}/evidence/**/*.qcow2',block)


if __name__=='__main__':unittest.main()
