"""Finite adapter negatives; no Git, Docker, VM or network mutation."""
import sys
sys.dont_write_bytecode=True
import base64,hashlib,importlib.util,json,os,pathlib,re,shutil,subprocess,tempfile,types,unittest
P=pathlib.Path;HERE=P(__file__).resolve().parent;ROOT=HERE.parents[1]
def load(name,file):
    spec=importlib.util.spec_from_file_location(name,HERE/file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
ST=load('tested_trace_stage','stage.py');D=load('tested_trace_stop','stop-driver.py');R=load('tested_trace_runner','trace-runner.py')
class Adapter(unittest.TestCase):
    def env(self):
        raw=dict(mango_startup_trace=True,safe_visual_diagnostic=True,same_iso_recovery=False,release=False,tag='',prerelease=True,draft=False,nix_acceptance=False,performance_acceptance=False,boot_test=False)
        return dict(SAFE_DIAGNOSTIC_MODE='true',MANGO_STARTUP_TRACE_MODE='true',RECOVERY_MODE='false',NATIVE_SMOKE_MODE='false',NIX_REQUESTED='false',PERFORMANCE_REQUESTED='false',BOOT_TEST_REQUESTED='false',GITHUB_SHA='1'*40,GITHUB_RUN_ID='100',MANGO_TRACE_ALL_INPUTS=json.dumps(raw))
    def flags(self,env):R.flags(env,types.SimpleNamespace(validate_ci=lambda e:None))
    def test_selected_mode(self):self.flags(self.env())
    def test_absent_optional_tag(self):
        env=self.env();raw=json.loads(env['MANGO_TRACE_ALL_INPUTS']);del raw['tag'];env['MANGO_TRACE_ALL_INPUTS']=json.dumps(raw);self.flags(env)
    def test_missing_typed_and_mixed_modes(self):
        for key in json.loads(self.env()['MANGO_TRACE_ALL_INPUTS']):
            if key=='tag':continue
            for value in (None,'false',0,[]):
                env=self.env();raw=json.loads(env['MANGO_TRACE_ALL_INPUTS']);raw[key]=value;env['MANGO_TRACE_ALL_INPUTS']=json.dumps(raw)
                with self.assertRaises(RuntimeError):self.flags(env)
        for key in ('same_iso_recovery','release','draft','nix_acceptance','performance_acceptance','boot_test'):
            env=self.env();raw=json.loads(env['MANGO_TRACE_ALL_INPUTS']);raw[key]=True;env['MANGO_TRACE_ALL_INPUTS']=json.dumps(raw)
            with self.assertRaises(RuntimeError):self.flags(env)
    def test_unknown_and_invalid_tag(self):
        for key,value in [('extra',False),('tag','v1'),('tag',None),('tag',False)]:
            env=self.env();raw=json.loads(env['MANGO_TRACE_ALL_INPUTS']);raw[key]=value;env['MANGO_TRACE_ALL_INPUTS']=json.dumps(raw)
            with self.assertRaises(RuntimeError):self.flags(env)
    def test_default_off(self):
        env=self.env();env['MANGO_STARTUP_TRACE_MODE']='false'
        with self.assertRaises(RuntimeError):self.flags(env)
    def test_exact_materialized_sources(self):
        m=R.material(types.SimpleNamespace(bundle=HERE));self.assertEqual(set(m['files']),R.FILES)
    def test_core_and_normal_pins(self):
        normal=json.loads((HERE/'normal-base-pins.json').read_text())
        for path,sha in normal.items():
            if path not in ('tools/test-iso.sh','.github/workflows/iso.yml'):self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),sha)
    def test_staging_exact13(self):
        values=ST.entries(HERE.parent/'safe-visual-diagnostic',HERE);self.assertEqual(len(values),13);self.assertEqual(sum(v[0]['mode']==0o755 for v in values),1)
    def test_readback_missing_extra_changed_modes(self):
        expected=ST.entries(HERE.parent/'safe-visual-diagnostic',HERE)
        with tempfile.TemporaryDirectory() as td:
            tree=P(td)/'payload';tree.mkdir()
            for row,p in expected:q=tree/row['cd_name'];q.write_bytes(p.read_bytes());q.chmod(row['mode'])
            ST.verify_tree(tree,expected)
            extra=tree/'extra';extra.write_bytes(b'x')
            with self.assertRaises(RuntimeError):ST.verify_tree(tree,expected)
            extra.unlink();node=tree/'request-stop.py';node.chmod(0o755)
            with self.assertRaises(RuntimeError):ST.verify_tree(tree,expected)
            node.chmod(0o644);node.write_bytes(b'changed')
            with self.assertRaises(RuntimeError):ST.verify_tree(tree,expected)
            node.unlink()
            with self.assertRaises(RuntimeError):ST.verify_tree(tree,expected)
    def test_completed_unicode_pending_and_final_bad(self):
        self.assertEqual(D.completed(b'complete\n'+b'\xd7'),('complete\n',[]))
        with self.assertRaises(UnicodeDecodeError):D.completed(b'bad\xff\n')
        with self.assertRaises(RuntimeError):D.completed(b'x'*262145)
    def test_stop_requires_actual34(self):
        with tempfile.TemporaryDirectory() as td:
            p=P(td);(p/'safe-events.log').write_text(json.dumps(dict(event='diagnostic-complete'))+'\n')
            with self.assertRaises(RuntimeError):D.run(None,p)
    def test_stop_one_input_failed_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            p=P(td);(p/'safe-events.log').write_text(''.join(json.dumps(dict(event='capture'))+'\n' for i in range(34))+json.dumps(dict(event='diagnostic-complete'))+'\n');(p/'serial.log').write_bytes(b'')
            calls=[]
            class VM:
                def alive(self):return True
                def type_text(self,c,gap):calls.append(('type',c,gap))
                def keys(self,k):calls.append(('key',k));(p/'serial.log').write_text('ARCTIC-RENDER-END {"status":"failed"}\n')
            with self.assertRaises(RuntimeError):D.run(VM(),p)
            self.assertEqual(calls,[('type',D.COMMAND,.2),('key','ret')]);self.assertEqual(json.loads((p/'mango-trace-events.log').read_text().splitlines()[-1])['event'],'trace-stop-failed')
    def test_deadline_and_owned_exit_no_retry(self):
        with tempfile.TemporaryDirectory() as td:
            p=P(td);(p/'safe-events.log').write_text(''.join(json.dumps(dict(event='capture'))+'\n' for i in range(34))+json.dumps(dict(event='diagnostic-complete'))+'\n');(p/'serial.log').write_bytes(b'')
            now=[0.];calls=[]
            class VM:
                def alive(self):return True
                def type_text(self,c,gap):calls.append(c);now[0]=181
                def keys(self,k):calls.append(k)
            with self.assertRaisesRegex(RuntimeError,'180s'):D.run(VM(),p,clock=lambda:now[0],sleep=lambda _:None)
            self.assertEqual(calls,[D.COMMAND,'ret'])
    def test_stop_actual_frozen_wire_success_and_duplicate_failure(self):
        # The runtime owner's explicit synthetic fixture is used unchanged;
        # this is protocol/lifecycle proof, never guest renderer qualification.
        F=load('frozen_trace_wire_fixture','test_trace_transport.py')
        report,bodies=F.fixture();frames=F.H.export(report,bodies)
        for duplicate in (False,True):
            with tempfile.TemporaryDirectory() as td:
                p=P(td);(p/'safe-events.log').write_text(''.join(json.dumps(dict(event='capture'))+'\n' for i in range(34))+json.dumps(dict(event='diagnostic-complete'))+'\n');(p/'serial.log').write_bytes(b'');calls=[]
                class VM:
                    def alive(self):return True
                    def type_text(self,c,gap):calls.append(c)
                    def keys(self,k):calls.append(k);(p/'serial.log').write_bytes(b''.join(frames[:-1])+frames[-1][:-1])
                def finish(_):(p/'serial.log').write_bytes(b''.join(frames)+(frames[-1] if duplicate else b''))
                if duplicate:
                    with self.assertRaisesRegex(RuntimeError,'Duplicate'):D.run(VM(),p,sleep=finish)
                else:D.run(VM(),p,sleep=finish)
                self.assertEqual(calls,[D.COMMAND,'ret'])
    def test_normal_assertion_snapshot_exact_and_changed_fixture_rejects(self):
        N=load('actual_normal_assertion_snapshot','normal-controls.py')
        with tempfile.TemporaryDirectory() as td:
            root=P(td)/'normal';bundle=N.snapshot(root)
            self.assertEqual(hashlib.sha256((root/'tools/test-iso.sh').read_bytes()).hexdigest(),N.FIXTURES['normal-test-iso.sh'])
            self.assertEqual((bundle/'test_safe_v1.py').read_bytes(),(HERE.parent/'safe-visual-diagnostic/test_safe_v1.py').read_bytes())
            self.assertEqual((bundle/'test_render_v1.py').read_bytes(),(HERE.parent/'safe-visual-diagnostic/test_render_v1.py').read_bytes())
            altered=P(td)/'altered';altered.mkdir();shutil.copytree(HERE/'normal-control-sources',altered/'normal-control-sources');(altered/'normal-control-sources/base-test-iso.sh').write_bytes(b'wrong base')
            with self.assertRaisesRegex(RuntimeError,'Pinned normal'):N.snapshot(P(td)/'bad',altered)
    @unittest.skipUnless(shutil.which('xorriso'),'xorriso absent: actual route runs in existing Fedora helper')
    def test_actual_generated_shell_CD13_and_credentials(self):
        # Exercise the literal generated staging path and argument framing.
        harness=(ROOT/'tools/test-iso.sh').read_text();begin=harness.index('  if [ "$ARCTIC_MANGO_STARTUP_TRACE" = 1 ]; then');finish=harness.index('  else\n',begin);body=harness[begin:finish]+'  fi\n'
        with tempfile.TemporaryDirectory() as td:
            temp=P(td);body=body.replace('/safe-diagnostic',str(HERE.parent/'safe-visual-diagnostic')).replace('/mango-trace',str(HERE)).replace('/tmp/safe-data',str(temp/'safe-data')).replace('/tmp/trace-CD-readback',str(temp/'readback')).replace('/tmp/trace-credentials.json',str(temp/'credentials.json'))
            script='set -euo pipefail\nARCTIC_MANGO_STARTUP_TRACE=1\nOUT='+str(temp)+'\nargs=()\n'+body+'\npython3 -c \'import json,sys;print(json.dumps(sys.argv[1:]))\' "${args[@]}"\n'
            value=subprocess.run(['bash','-c',script],check=True,capture_output=True,text=True,timeout=120)
            args=json.loads(value.stdout);receipt=json.loads((temp/'mango-CD-receipt.json').read_text());self.assertEqual(len(receipt['members']),13)
            self.assertEqual(args,ST.load(HERE/'credential-units.py').qemu_args(receipt['sha256'],receipt['bytes']))
            self.assertEqual((temp/'safe-data.iso').read_bytes()[:534],(HERE.parent/'safe-visual-diagnostic/bootstrap-safe-v1.sh').read_bytes())
            self.assertEqual(len(args),4);self.assertEqual(args[0::2],['-smbios','-smbios'])
            print('ACTUAL-CD13-RECEIPT '+json.dumps(receipt,sort_keys=True))
if __name__=='__main__':unittest.main(verbosity=2)
