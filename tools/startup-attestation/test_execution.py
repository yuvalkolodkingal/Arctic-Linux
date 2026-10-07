"""Host source/driver controls, owned fixture files/child only; never a VM."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import types
import hashlib
from unittest.mock import patch
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
def load(name,file):
    spec=importlib.util.spec_from_file_location(name,HERE/file);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
D=load('driver_control','attestation-driver-v1.py');G=load('generator_control','prepare-attestation-v1.py')
R=load('runner_control','attestation-runner-v1.py');T=load('fixture_transport','test_attest_host.py')

class Clock:
    def __init__(self):self.now=0
    def __call__(self):return self.now
    def sleep(self,seconds):self.now+=seconds

class VM:
    def __init__(self,out,text=None):self.out=out;self.calls=[];self.text=text if text is not None else T.serial(T.transport());self.running=True
    def alive(self):return self.running
    def shot(self,name):
        self.calls.append(('shot',name));p=self.out/(name+'.png');p.write_bytes(b'HOST FIXTURE ONLY');return p
    def keys(self,*values):self.calls.append(('keys',values))
    def type_text(self,text,gap):
        self.calls.append(('command',text,gap));(self.out/'serial.log').write_text(self.text)

class ExecutionTests(unittest.TestCase):
    def test_tiny_driver_exact_order_and_limits_no_original34_or_hook(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);clock=Clock();vm=VM(out)
            D.run(vm,out,dict(monotonic_estimate_seconds=0),0,True,clock,clock.sleep)
            result=D.validate_events(out/'attestation-events.log');self.assertFalse(result['original34_qualification'])
            self.assertFalse(result['release_acceptance']);self.assertEqual(clock.now,185)
            self.assertEqual([v for v in vm.calls if v[0]=='keys'],[('keys',('meta_l-ret',)),('keys',('ret',)),('keys',('ret',))])
            self.assertEqual([v[1] for v in vm.calls if v[0]=='command'],[D.COLLECTOR_COMMAND])
            rows=[json.loads(v) for v in (out/'attestation-events.log').read_text().splitlines()]
            rows[1]['entry_elapsed_seconds']-=.000002
            (out/'attestation-events.log').write_text(''.join(json.dumps(v)+'\n' for v in rows))
            with self.assertRaises(RuntimeError):D.validate_events(out/'attestation-events.log')
    def test_no_menu_vm_exit_malformed_or_truncated_collector_never_complete(self):
        for kind in ('menu','exit','malformed','truncated'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp:
                out=Path(temp);clock=Clock();text=T.serial(T.transport())
                if kind=='malformed':text='ARCTIC-ATTEST-BEGIN {\n'
                if kind=='truncated':text=text[:-2]
                vm=VM(out,text);vm.running=kind!='exit'
                with self.assertRaises((RuntimeError,ValueError)):
                    D.run(vm,out,dict(monotonic_estimate_seconds=0),0,kind!='menu',clock,clock.sleep)
                self.assertLessEqual(clock.now,365.5)
                if (out/'attestation-events.log').exists():self.assertNotIn('attestation-driver-complete',(out/'attestation-events.log').read_text())
    def test_mode_guard_exact_and_every_unrelated_mode_rejects(self):
        class Original:
            def validate_ci(self,env):
                self.seen=env
                if env.get('RELEASE_REQUESTED')!='false':raise RuntimeError('Release selected')
        original=Original();env=dict(STARTUP_ATTESTATION_MODE='true',RECOVERY_MODE='false',RELEASE_REQUESTED='false',
            NATIVE_SMOKE_MODE='false',SAFE_DIAGNOSTIC_MODE='false',NIX_REQUESTED='false',PERFORMANCE_REQUESTED='false',BOOT_TEST_REQUESTED='false',
            GITHUB_SHA='1'*40,GITHUB_RUN_ID='999')
        R.validate_ci(env,original);self.assertEqual(original.seen['RECOVERY_MODE'],'true');self.assertEqual(env['RECOVERY_MODE'],'false')
        for key in ['RECOVERY_MODE','RELEASE_REQUESTED','NATIVE_SMOKE_MODE','SAFE_DIAGNOSTIC_MODE','NIX_REQUESTED','PERFORMANCE_REQUESTED','BOOT_TEST_REQUESTED']:
            bad=dict(env);bad[key]='true'
            with self.subTest(key=key),self.assertRaises(RuntimeError):R.validate_ci(bad,original)
        with self.assertRaises(RuntimeError):R.validate_ci(dict(env,STARTUP_ATTESTATION_MODE='false'),original)
    def test_actual_base_generator_defaultoff_network_and_qemu_core_parity(self):
        base_test,base_workflow=G.P.base_sources();harness=G.harness(base_test);workflow=G.workflow(base_workflow)
        self.assertIn('STARTUP_ATTESTATION=""',harness);self.assertIn('--startup-attestation)',harness)
        self.assertNotIn('safe_driver_v1.run(',harness);self.assertNotIn('render_driver_v1.run(',harness)
        self.assertIn('finally:\n        vm.quit()',harness)
        self.assertIn('-netdev user,id=net0,restrict=on',harness);self.assertNotIn('restrict=off',harness)
        self.assertIn('-V ARCTICATTEST',harness);self.assertIn('readonly=on',harness)
        self.assertIn('type: boolean\n        default: false\n      same_iso_recovery:',workflow)
        self.assertIn('(!inputs.same_iso_recovery && !inputs.startup_attestation)',workflow)
        self.assertEqual(workflow.count("if: ${{ github.event_name == 'workflow_dispatch' && inputs.same_iso_recovery && !inputs.startup_attestation }}"),2)
        self.assertIn("SAFE_DIAGNOSTIC_MODE: 'false'",workflow);self.assertIn('fetch-depth: 0',workflow)
        self.assertIn('artifact-ids: 11434226349',workflow);self.assertIn('run-id: 37507582946',workflow)
        for needle in ['mount -o ro','test ! -L /run/arctic-safe','test "$(getenforce)" = Enforcing']:
            self.assertIn(needle,(HERE/'bootstrap-attest-v1.sh').read_text())
        self.assertIn('sys.dont_write_bytecode=True',(HERE/'attest-startup-v1.py').read_text())
    def test_real_owned_chunk_writer_live_tail_wait_and_final_byte_integrity(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'serial';data=T.serial(T.transport()).encode();fixture=Path(temp)/'fixture';fixture.write_bytes(data)
            code='''import pathlib,sys,time
data=pathlib.Path(sys.argv[1]).read_bytes()
with open(sys.argv[2],"wb",buffering=0) as f:
 for i in range(0,len(data),73):f.write(data[i:i+73]);time.sleep(.001)
'''
            process=subprocess.Popen([sys.executable,'-c',code,str(fixture),str(p)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                end=time.monotonic()+3;polls=0
                while process.poll() is None and time.monotonic()<end:
                    if p.exists():D.H.protocol(p.read_text(),live=True);polls+=1
                    time.sleep(.001)
                stdout,stderr=process.communicate(timeout=3);self.assertEqual(process.returncode,0,stderr)
                self.assertGreater(polls,0);self.assertEqual(p.read_bytes(),data)
                result=D.H.extract(p.read_text(),Path(temp)/'decoded','a'*64);self.assertFalse(result['exact_startup_target_bound'])
            finally:
                if process.poll() is None:process.kill();process.wait(timeout=3)
                process.stdout.close();process.stderr.close()
    def test_real_source_files_restricted_guard_hash_and_mode_negatives(self):
        class Frozen:
            SOURCE='fe4742c8b9414c45f0bcbb0a4191f116383c60d1'
            def verify_sources(self,source,recovery,base):self.original=(source,recovery,base)
            def pinned_file(self,path,expected):
                if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise RuntimeError('Pin differs')
        for kind in ('pass','head','dirty','extra-diff','mode','bool-mode','hash','link','extra-manifest'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);bundle=root/'tools/startup-attestation';bundle.mkdir(parents=True)
                manifest=dict(schema=R.SCHEMA,candidate_source=Frozen.SOURCE,qualification_base=R.BASE,files={},modes={})
                for name in R.EXECUTION_FILES:
                    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'owned source fixture\n');p.chmod(0o644)
                    manifest['files'][name]=hashlib.sha256(p.read_bytes()).hexdigest();manifest['modes'][name]=0o644
                target=root/'tools/lib/vmtest.py'
                if kind=='mode':target.chmod(0o600)
                elif kind=='bool-mode':manifest['modes']['tools/lib/vmtest.py']=True
                elif kind=='hash':target.write_bytes(b'CHANGED')
                elif kind=='link':target.unlink();target.symlink_to(root/'tools/test-iso.sh')
                elif kind=='extra-manifest':manifest['files']['unexpected']=manifest['modes']['unexpected']='extra'
                (bundle/'execution-pins-attestation-v1.json').write_text(json.dumps(manifest))
                def git(argv,**kwargs):
                    if 'rev-parse' in argv:return ('2'*40 if kind=='head' else '1'*40)+'\n'
                    if 'status' in argv:return ' M tracked' if kind=='dirty' else ''
                    if 'diff' in argv:return '.github/workflows/iso.yml\ntools/test-iso.sh\n'+('forbidden.txt\n' if kind=='extra-diff' else '')
                    raise AssertionError(argv)
                frozen=Frozen();args=types.SimpleNamespace(source=root/'candidate',recovery_bundle=root/'frozen',bundle=bundle)
                with patch.dict(os.environ,{'GITHUB_SHA':'1'*40}),patch.object(R.subprocess,'check_output',side_effect=git),patch.object(R.subprocess,'run'):
                    if kind=='pass':R.verify_sources(args,frozen)
                    else:
                        with self.assertRaises(RuntimeError):R.verify_sources(args,frozen)
                self.assertEqual(frozen.original,(args.source,args.recovery_bundle,R.BASE))
    def test_failure_screenshot_error_retains_original_collector_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);clock=Clock();vm=VM(out,'ARCTIC-ATTEST-BEGIN {\n');real=vm.shot
            def shot(name):
                if name=='attest-98-failure':raise OSError('owned screenshot failed')
                return real(name)
            vm.shot=shot
            with self.assertRaises(ValueError):D.run(vm,out,dict(monotonic_estimate_seconds=0),0,True,clock,clock.sleep)
            rows=[json.loads(v) for v in (out/'attestation-events.log').read_text().splitlines()]
            self.assertEqual(rows[-2]['event'],'attestation-driver-failure');self.assertEqual(rows[-1]['event'],'failure-capture-error')
            self.assertNotIn('attestation-driver-complete',[r['event'] for r in rows])
    def test_driver_final_event_gate_rejects_order_duplicates_scope_and_clocks(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);clock=Clock();D.run(VM(out),out,dict(monotonic_estimate_seconds=0),0,True,clock,clock.sleep)
            path=out/'attestation-events.log';original=[json.loads(v) for v in path.read_text().splitlines()]
            for kind in ('duplicate','order','bool','reverse','early','command','release'):
                rows=json.loads(json.dumps(original))
                if kind=='duplicate':rows.insert(0,rows[0])
                elif kind=='order':rows[1],rows[2]=rows[2],rows[1]
                elif kind=='bool':rows[0]['monotonic_seconds']=False
                elif kind=='reverse':rows[3]['monotonic_seconds']=-1
                elif kind=='early':rows[2]['entry_elapsed_seconds']=119
                elif kind=='command':rows[5]['command']='sudo MALFORMED'
                else:rows[-1]['release_acceptance']=True
                path.write_text(''.join(json.dumps(v)+'\n' for v in rows))
                with self.subTest(kind=kind),self.assertRaises(RuntimeError):D.validate_events(path)

if __name__=='__main__':unittest.main(verbosity=2)
