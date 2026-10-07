"""Actual host/source controls; no API, VM, dispatch or artifact download."""
import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
spec=importlib.util.spec_from_file_location('diagnostic_runner',HERE/'feasibility-runner.py')
P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)
spec=importlib.util.spec_from_file_location('diagnostic_controller',HERE/'run-feasibility.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
WORKFLOW_BASE_SHA='610dd5839369e75d55da53e4e899e66f9b5c6a85733a4238cb9751b13b9dd177'


def ci():
    return dict(GITHUB_ACTIONS='true',GITHUB_EVENT_NAME='workflow_dispatch',
        GITHUB_REPOSITORY=P.R.REPOSITORY,GITHUB_API_URL='https://api.github.com',
        GITHUB_SHA='b'*40,GITHUB_RUN_ID='9999',GITHUB_RUN_ATTEMPT='1',
        PRECISION_FEASIBILITY_MODE='true',PERFORMANCE_MODE='false',RECOVERY_MODE='false',
        NIX_ACCEPTANCE='false',PERFORMANCE_ACCEPTANCE='false',RELEASE_REQUESTED='false',CONTAINER_ENGINE='docker')


def prior():
    run=dict(id=P.PRIOR_RUN,head_sha=P.PRIOR_HEAD,status='completed',conclusion='failure',run_attempt=1)
    job=dict(id=P.PRIOR_JOB,run_id=P.PRIOR_RUN,head_sha=P.PRIOR_HEAD,status='completed',conclusion='failure',
        steps=[dict(name='Six fresh paired boots of unchanged images',status='completed',conclusion='failure')])
    artifact=dict(id=P.PRIOR_ARTIFACT,size_in_bytes=P.PRIOR_ZIP_BYTES,digest='sha256:'+P.PRIOR_ZIP_SHA,
        expired=False,workflow_run=dict(id=P.PRIOR_RUN,head_sha=P.PRIOR_HEAD))
    return run,[job],artifact


def historical_workflow():
    value=subprocess.check_output(['git','-C',str(ROOT),'show',P.EXECUTION_BASE+':.github/workflows/iso.yml'],text=True)
    if hashlib.sha256(value.encode()).hexdigest()!=WORKFLOW_BASE_SHA:raise RuntimeError('Historical workflow fixture differs')
    return value


def unchanged_controls():
    file=ROOT/'tools/same-iso-performance/test_performance_runner_v3.py'
    spec=importlib.util.spec_from_file_location('unchanged_v3_host_controls',file)
    original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
    suite=unittest.defaultTestLoader.loadTestsFromModule(original)
    with patch.object(original,'workflow_text',return_value=historical_workflow()):
        result=unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def workflow():return (ROOT/'.github/workflows/iso.yml').read_text()
def new_job(text):return text.split('  same-iso-precision-feasibility:\n',1)[1]
def step(text,name):return new_job(text).split('      - name: '+name+'\n',1)[1].split('      - name: ',1)[0]


class RunnerTest(unittest.TestCase):
    def test_only_reviewed_diagnostic_mode_and_supported_engine(self):
        P.validate_ci(ci())
        bad=[('PRECISION_FEASIBILITY_MODE','false'),('RECOVERY_MODE','true'),('PERFORMANCE_MODE','true'),
             ('NIX_ACCEPTANCE','true'),('PERFORMANCE_ACCEPTANCE','true'),('RELEASE_REQUESTED','true'),
             ('CONTAINER_ENGINE','podman'),('CONTAINER_ENGINE','/tmp/fake-engine'),('GITHUB_EVENT_NAME','push'),
             ('GITHUB_REPOSITORY','foreign/repo'),('GITHUB_SHA',P.EXECUTION_BASE),('GITHUB_SHA',P.PRIOR_HEAD),
             ('GITHUB_SHA',P.R.SOURCE),('GITHUB_RUN_ID',str(P.R.ORIGINAL_RUN))]
        for key,value in bad:
            env=ci();env[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(RuntimeError):P.validate_ci(env)

    def test_exact_historical_failure_metadata_cannot_be_replaced(self):
        self.assertEqual(P.validate_prior(*prior())['artifact'],P.PRIOR_ARTIFACT)
        for fault in ('active','passed','attempt','job_active','job_id','duplicate','missing_step','pass_step','bytes','hash','expired','head'):
            run,jobs,artifact=prior()
            if fault=='active':run['status']='in_progress'
            elif fault=='passed':run['conclusion']='success'
            elif fault=='attempt':run['run_attempt']=2
            elif fault=='job_active':jobs[0]['status']='in_progress'
            elif fault=='job_id':jobs[0]['id']+=1
            elif fault=='duplicate':jobs.append(copy.deepcopy(jobs[0]))
            elif fault=='missing_step':jobs[0]['steps']=[]
            elif fault=='pass_step':jobs[0]['steps'][0]['conclusion']='success'
            elif fault=='bytes':artifact['size_in_bytes']-=1
            elif fault=='hash':artifact['digest']='sha256:'+'0'*64
            elif fault=='expired':artifact['expired']=True
            else:artifact['workflow_run']['head_sha']='0'*40
            with self.subTest(fault=fault),self.assertRaises(RuntimeError):P.validate_prior(run,jobs,artifact)

    def test_controller_is_exactly_two_images_and_preserves_harness_stage_deadlines(self):
        self.assertEqual(C.paired_boot_order(),[(1,'baseline'),(1,'candidate')])
        source=(HERE/'run-feasibility.py').read_text()
        for token in ('1880244224',P.R.ISO_SHA256,P.R.SOURCE,"3600, vm=True","2400, vm=True",
                      "'--install-timeout', '2400'",'installed_base_sha256','firmware_variables_sha256',
                      'fresh_installed_overlay',"'--collect-via', 'console'",'identity-out','feasibility-check.py'):
            self.assertIn(token,source)
        self.assertNotIn("save('complete_regression_gate_passed'",source)
        self.assertIn("full_six_boot_performance_acceptance=False",source)
        with self.assertRaises((RuntimeError,FileNotFoundError)):
            C.candidate_source_identity(Path('/tmp/nonexistent-precision-source'))

    def test_registered_workflow_disables_every_old_job_and_keeps_read_only_artifact_mode(self):
        text=workflow();block=new_job(text)
        prior_block=text.split('jobs:\n',1)[1].split('  same-iso-precision-feasibility:\n',1)[0]
        names=[]
        for line in prior_block.splitlines():
            if line.startswith('  ') and not line.startswith('   ') and line.endswith(':'):names.append(line.strip()[:-1])
            if line.startswith('    if: ${{ '):self.assertTrue(line.endswith(' && !inputs.same_iso_precision_feasibility }}'))
        self.assertEqual(set(names),{'iso','same-iso-installs','same-iso-boot-evidence','same-iso-performance'})
        self.assertEqual(sum(line.startswith('    if: ${{ ') for line in prior_block.splitlines()),len(names))
        self.assertIn('timeout-minutes: 200',block)
        self.assertIn('contents: read',block);self.assertIn('actions: read',block)
        self.assertNotIn('contents: write',block);self.assertNotIn('build-iso',block);self.assertNotIn('test-iso.sh',block)
        self.assertIn('artifact-ids: 11434226349',block);self.assertIn('run-id: 37507582946',block)
        self.assertNotIn('inputs.artifact',block);self.assertNotIn('inputs.run_id',block)
        self.assertLess(block.index('Verify actual image bytes before any VM'),block.index('One fresh boot per fixed image'))
        self.assertIn('!${{ env.FEASIBILITY_ROOT }}/evidence/**/*.qcow2',block)
        self.assertIn('--unchanged-runner-controls',block)

    def test_full_history_profiles_and_no_other_checkout_guard(self):
        block=step(workflow(),'Checkout separate reviewed diagnostic execution')
        self.assertIn('          fetch-depth: 0\n',block)
        sparse=block.split('          sparse-checkout: |\n',1)[1]
        for path in ('tools','.github/workflows','profiles/ci'):self.assertIn('            '+path+'\n',sparse)
        self.assertIn('          persist-credentials: false\n',block)
        self.assertIn('          ref: ${{ github.sha }}\n',block)
        self.assertIn(P.R.SOURCE,step(workflow(),'Checkout immutable candidate image source'))

    def test_new_disk_prep_only_fixed_fresh_runner_tools_and_same_space_gate(self):
        block=step(workflow(),'Prepare disk space on the fresh hosted runner')
        script='\n'.join(line[10:] for line in block.split('        run: |\n',1)[1].splitlines())
        subprocess.run(['bash','-n'],input=script,text=True,check=True,capture_output=True)
        self.assertIn('free>=40_000_000_000',(HERE/'feasibility-runner.py').read_text())
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);fake=root/'bin';fake.mkdir();calls=root/'calls.jsonl'
            code="#!/usr/bin/env python3\nimport json,os,sys\nwith open(os.environ['FIXTURE_CALLS'],'a') as out:out.write(json.dumps([os.path.basename(sys.argv[0]),*sys.argv[1:]])+'\\n')\n"
            for name in ('sudo','df'):
                file=fake/name;file.write_text(code);file.chmod(0o755)
            for fault in (None,'GITHUB_ACTIONS','RUNNER_ENVIRONMENT','RUNNER_OS'):
                folder=root/str(fault);folder.mkdir();calls.unlink(missing_ok=True)
                env=dict(os.environ,PATH=str(fake)+os.pathsep+os.environ['PATH'],FIXTURE_CALLS=str(calls),
                    FEASIBILITY_ROOT=str(folder),RUNNER_TEMP=str(root),GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',RUNNER_OS='Linux')
                if fault:env[fault]='unsupported'
                result=subprocess.run(['bash','-c',script],env=env,text=True,capture_output=True,timeout=10)
                if fault:
                    self.assertNotEqual(result.returncode,0);self.assertFalse(calls.exists())
                else:
                    self.assertEqual(result.returncode,0,result.stderr)
                    rows=[json.loads(row) for row in calls.read_text().splitlines()]
                    self.assertEqual(rows[1],['sudo','rm','-rf','--','/usr/share/dotnet','/usr/local/lib/android','/opt/ghc',
                        '/opt/hostedtoolcache/CodeQL','/usr/local/share/boost','/usr/local/share/powershell','/usr/share/swift'])
                    self.assertEqual(rows[0],rows[2]);self.assertEqual(rows[0],['df','-B1','/',str(root)])

    def test_actual_owned_controller_timeout_and_cleanup_contract_still_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);actual=subprocess.Popen;children=[]
            def record(*args,**kwargs):
                child=actual(*args,**kwargs);children.append(child);return child
            with patch.object(P.V3.subprocess,'Popen',side_effect=record):
                with self.assertRaises(subprocess.TimeoutExpired):
                    P.V3.execute_controller([sys.executable,'-c','import time;time.sleep(30)'],root/'log',root,dict(os.environ),seconds=.05)
            self.assertEqual(len(children),1);self.assertIsNotNone(children[0].poll())

    def test_run_rejects_incomplete_failed_or_forged_counts_and_never_claims_release(self):
        state=dict(mode='precision-feasibility-one-pair',phase='complete_feasibility_gates_passed',
            planned_boot_order=[dict(image='baseline',boot=1),dict(image='candidate',boot=1)],
            runs=[dict(image='baseline',boot=1,harness_exit=0),dict(image='candidate',boot=1,harness_exit=0)])
        result=dict(status='feasibility-gates-passed',total_observations=24,failed_observations=0,
            individual_precision_valid=True,median_enclosure_valid=True,memory_gate_valid=True,point_latency_gates_valid=True,
            checks={image:[dict(valid=True)]*12 for image in ('baseline','candidate')},
            full_six_boot_performance_acceptance=False,release_acceptance=False)
        for fault in (None,'few','filtered','precision','enclosure','memory','latency','bool_exit','bool_failed','release','sixboot'):
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);evidence=root/'evidence';evidence.mkdir();s=copy.deepcopy(state);r=copy.deepcopy(result)
                if fault=='few':s['runs'].pop()
                elif fault=='filtered':r['checks']['candidate'].pop()
                elif fault in ('precision','enclosure','memory','latency'):
                    r[{'precision':'individual_precision_valid','enclosure':'median_enclosure_valid','memory':'memory_gate_valid','latency':'point_latency_gates_valid'}[fault]]=False
                elif fault=='bool_exit':s['runs'][0]['harness_exit']=False
                elif fault=='bool_failed':r['failed_observations']=False
                elif fault=='release':r['release_acceptance']=True
                elif fault=='sixboot':r['full_six_boot_performance_acceptance']=True
                args=types.SimpleNamespace(bundle=HERE,source=root/'source',inputs=root/'inputs',evidence=evidence)
                def controller(argv,log,execution,env,*,seconds,measurement):
                    self.assertEqual(seconds,150*60);self.assertEqual(env['CONTAINER_ENGINE'],'docker')
                    self.assertIn('run-feasibility.py',argv[1]);measurement.mkdir()
                    (measurement/'status.json').write_text(json.dumps(s));(measurement/'feasibility.json').write_text(json.dumps(r))
                with patch.dict(os.environ,ci()),patch.object(P,'verify'),patch.object(P.R,'require_docker'),patch.object(P.Path,'is_char_device',return_value=True),\
                     patch.object(P.V3,'download_baseline',return_value=root/'baseline.iso'),patch.object(P.V3,'execute_controller',side_effect=controller):
                    if fault:
                        with self.assertRaises(RuntimeError):P.run(args)
                        self.assertFalse((evidence/'result.json').exists())
                    else:
                        P.run(args);proof=json.loads((evidence/'result.json').read_text())
                        self.assertFalse(proof['release_acceptance']);self.assertFalse(proof['full_six_boot_performance_acceptance'])

    def test_actual_source_verifier_rejects_runtime_manifest_scope_and_source_mutations(self):
        # Git head/history responses are synthetic; every pin is checked against
        # actual copied file bytes and the exact declared base blob bytes.
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);execution=root/'execution';source=root/'image-source'
            runtime=json.loads((HERE/'runtime-pins.json').read_text())
            manifest=json.loads((HERE/'execution-pins.json').read_text())
            base_bytes={name:(ROOT/name).read_bytes() for name in runtime['files']}
            source_bytes={name:subprocess.check_output(['git','-C',str(ROOT),'show',P.R.SOURCE+':'+name]) for name in P.R.SOURCE_PINS}
            for name in set(runtime['files'])|P.ALLOWED_CHANGES:
                file=execution/name;file.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,file)
            for name,data in source_bytes.items():
                file=source/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(data)
            args=types.SimpleNamespace(bundle=execution/'tools/precision-feasibility',source=source)
            fault=[None]
            def query(argv,**kwargs):
                op=argv[3:];folder=Path(argv[2])
                if op==['rev-parse','HEAD']:
                    return (P.R.SOURCE if folder==source else ci()['GITHUB_SHA'])+'\n'
                if op==['status','--porcelain']:return ' M shell/AppsService.qml\n' if fault[0]=='dirty' else ''
                if op[:2]==['diff','--name-only']:
                    return 'tools/performance/guest.py\n' if fault[0]=='product_scope' else '.github/workflows/iso.yml\n'
                if op[0]=='show':
                    head,name=op[1].split(':',1);self.assertEqual(head,P.EXECUTION_BASE)
                    data=base_bytes[name]
                    return data.decode() if kwargs.get('text') else data
                raise AssertionError('Unexpected synthetic Git query: '+str(argv))
            def history(argv,**kwargs):
                self.assertEqual(argv[3:6],['merge-base','--is-ancestor',P.EXECUTION_BASE])
                if fault[0]=='missing_history':raise subprocess.CalledProcessError(128,argv)
                return subprocess.CompletedProcess(argv,0)
            with patch.dict(os.environ,ci()),patch.object(P.subprocess,'check_output',side_effect=query),patch.object(P.subprocess,'run',side_effect=history):
                self.assertEqual(P.verify_sources(args),manifest)
                for name in ('dirty','product_scope','missing_history','runtime_hash','runtime_missing','manifest_missing','manifest_scope','source_hash'):
                    fault[0]=name;runtime_file=args.bundle/'runtime-pins.json';manifest_file=args.bundle/'execution-pins.json'
                    changed_runtime=copy.deepcopy(runtime);changed_manifest=copy.deepcopy(manifest)
                    if name=='runtime_hash':changed_runtime['files']['tools/performance/guest.py']='0'*64
                    elif name=='runtime_missing':changed_runtime['files'].pop('tools/performance/guest.py')
                    elif name=='manifest_missing':changed_manifest['files'].pop('tools/precision-feasibility/dual-observer.py')
                    elif name=='manifest_scope':changed_manifest['files']['shell/AppsService.qml']='0'*64
                    elif name=='source_hash':(source/'profiles/ci/offline.toml').write_text('changed profile')
                    runtime_file.write_text(json.dumps(changed_runtime));manifest_file.write_text(json.dumps(changed_manifest))
                    with self.subTest(name=name),self.assertRaises((RuntimeError,subprocess.CalledProcessError)):
                        P.verify_sources(args)
                    runtime_file.write_bytes((HERE/'runtime-pins.json').read_bytes())
                    manifest_file.write_bytes((HERE/'execution-pins.json').read_bytes())
                    for relative,data in source_bytes.items():(source/relative).write_bytes(data)

    def test_source_pin_file_set_paths_and_product_allowlist_are_bounded(self):
        runtime=json.loads((HERE/'runtime-pins.json').read_text())
        frozen=json.loads((ROOT/'tools/same-iso-performance/frozen-v2-pins-v3.json').read_text())
        expected=(P.V3.EXECUTION_FILES-{'.github/workflows/iso.yml'})|set(frozen['files'])|{'tools/same-iso-performance/execution-pins-v3.json'}
        self.assertEqual(set(runtime['files']),expected)
        for relative,digest in runtime['files'].items():self.assertEqual(P.R.digest(ROOT/relative),digest)
        self.assertNotIn('tools/performance/guest.py',P.ALLOWED_CHANGES)
        self.assertNotIn('tools/performance/compare.py',P.ALLOWED_CHANGES)
        self.assertNotIn('shell/AppsService.qml',P.ALLOWED_CHANGES)
        manifest=json.loads((HERE/'execution-pins.json').read_text());self.assertEqual(set(manifest['files']),P.EXECUTION_FILES)
        for relative,digest in manifest['files'].items():self.assertEqual(P.R.digest(ROOT/relative),digest)
        self.assertNotIn('tools/precision-feasibility/execution-pins.json',manifest['files'])


if __name__=='__main__':
    if '--unchanged-runner-controls' in sys.argv:
        sys.argv.remove('--unchanged-runner-controls');raise SystemExit(unchanged_controls())
    unittest.main()
