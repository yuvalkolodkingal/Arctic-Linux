"""Owned host-only QMP fixtures; no actual VM/input and no guest qualification."""
import ast,copy,hashlib,importlib.util,json,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('tested_native_physical',HERE/'native-physical-controller.py');C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
class Clock:
 def __init__(self):self.now=10.
 def __call__(self):return self.now
 def sleep(self,n):self.now+=n
class VM:
 def __init__(self,out):self.out=out;self.calls=[];self.answer={'return':{}};self.live=True
 def alive(self):return self.live
 def shot(self,name):p=self.out/(name+'.png');p.write_bytes(b'\x89PNG\r\n\x1a\nsynthetic');return str(p)
 def cmd(self,name,**kw):self.calls.append((name,kw));return self.answer
def chord(c):
 if c.isascii() and c.isalnum():return ['shift',c.lower()] if c.isupper() else [c]
 return {'/':['slash'],'-':['minus'],'_':['shift','minus'],' ':['spc']}[c]
def request(index=0):
 actions=[('navigate','files with spaces'),('f4',None),('open-first',None),('navigate','archive file opener'),('open-first',None)]
 action,folder=actions[index];root='/tmp/arctic-native-smoke-test'
 return dict(schema='arctic-native-pcmanfm-physical-v1',stage='live',nonce=f'{index+1:032x}',boot_id='11111111-1111-1111-1111-111111111111',desktop_uid=1000,
  process=dict(pid=60,start_ticks=600,uid=1000,executable='/usr/bin/pcmanfm',executable_sha256='1'*64,is_xwayland=False,client_id='4'),
  client=dict(id=4,pid=60,is_focused=True,is_visible=True,is_xwayland=False,appid='pcmanfm',title='Home',foreign_toplevel_id='own'),
  action=action,path=root+'/'+folder if folder else None,evidence_root=root,monotonic_ns=1000000000,client_monotonic_ns=999000000,release_acceptance=False,accessibility_proof=False)
def serial(values,launcher_mutation=None):
 launch=dict(stage='live',boot_id=values[0]['boot_id'],launcher_sha256='e948f2ff9c7273f20b0d42e67cc891e3a3f6e0954dfc1ac3afca2aa7c3d7df4c',owned_launcher_gone=True,foot={'uid':1000},shell={'uid':1000},probe={'uid':0})
 if launcher_mutation:launcher_mutation(launch)
 return '\n'.join(['ARCTIC-NATIVE-LAUNCHER-GONE '+json.dumps(launch),'ARCTIC-NATIVE-RUNNER-BEGIN '+json.dumps(dict(stage='live',checker_sha256='2'*64,release_acceptance=False))]+[C.PREFIX+json.dumps(r,sort_keys=True) for r in values])+'\n'
class PhysicalControls(unittest.TestCase):
 def fixture(self,folder):
  clock=Clock();vm=VM(Path(folder));c=C.Controller(vm,folder,'live','2'*64,clock=clock,sleep=clock.sleep,chord_for=chord);return c,vm,clock
 def test_actual_five_requests_keys_captures_and_one_use(self):
  with tempfile.TemporaryDirectory() as d:
   c,vm,_=self.fixture(d);values=[request(i) for i in range(5)]
   for i in range(5):c.poll(serial(values[:i+1]))
   old=len(vm.calls);c.poll(serial(values));self.assertEqual(len(vm.calls),old)
   self.assertEqual(len(c.used),5);rows=[json.loads(x) for x in c.log.read_text().splitlines()]
   self.assertEqual(sum(x['event']=='capture' for x in rows),12)
   self.assertEqual(sum(x['event']=='physical-delivered' for x in rows),5)
   for name,kw in vm.calls:
    self.assertEqual(name,'input-send-event');events=kw['events'];half=len(events)//2
    self.assertTrue(all(e['data']['down'] is True for e in events[:half]))
    self.assertEqual([e['data']['key'] for e in events[:half]],list(reversed([e['data']['key'] for e in events[half:]])))
 def test_partial_last_request_waits_for_newline(self):
  with tempfile.TemporaryDirectory() as d:
   c,vm,_=self.fixture(d);raw=serial([request()]);c.poll(raw[:-5]);self.assertEqual(vm.calls,[]);c.poll(raw);self.assertTrue(vm.calls)
 def test_all_strict_qmp_adverses_refused(self):
  for value in (None,False,{}, {'return':None},{'return':False},{'return':{'unexpected':1}},{'return':{},'id':1},{'return':{},'error':{}}):
   with self.subTest(value=value),self.assertRaises(RuntimeError):C.qmp_return(value)
 def test_failed_attempt_consumed_never_resends(self):
  with tempfile.TemporaryDirectory() as d:
   c,vm,_=self.fixture(d);vm.answer={'error':{}}
   with self.assertRaises(RuntimeError):c.poll(serial([request()]))
   self.assertEqual(len(c.used),1);old=len(vm.calls);vm.answer={'return':{}};c.poll(serial([request()]));self.assertEqual(len(vm.calls),old)
 def test_native_identity_focus_uid_timing_adverses(self):
  mutations=[lambda r:r['process'].update(uid=1001),lambda r:r['process'].update(pid=True),lambda r:r['process'].update(start_ticks=0),lambda r:r['client'].update(is_focused=False),lambda r:r['client'].update(is_xwayland=True),lambda r:r['client'].update(pid=61),lambda r:r['client'].update(appid='other'),lambda r:r.update(client_monotonic_ns=False),lambda r:r.update(monotonic_ns=3_000_000_000),lambda r:r.update(accessibility_proof=True),lambda r:r.update(path='/tmp/other'),lambda r:r.update(path=r['path']+'שלום')]
  for mutation in mutations:
   r=request();mutation(r)
   with self.subTest(r=r),self.assertRaises(RuntimeError):C.validate(r,'live')
 def test_launcher_boot_uid_hash_source_adverses(self):
  for mutation in (lambda l:l.update(boot_id='2'*36),lambda l:l.update(launcher_sha256='3'*64),lambda l:l['shell'].update(uid=1001),lambda l:l['probe'].update(uid=1000)):
   with tempfile.TemporaryDirectory() as d:
    c,vm,_=self.fixture(d)
    with self.assertRaises(RuntimeError):c.poll(serial([request()],mutation))
    self.assertEqual(vm.calls,[])
 def test_duplicate_changed_and_out_of_order_requests(self):
  with tempfile.TemporaryDirectory() as d:
   c,vm,_=self.fixture(d)
   with self.assertRaises(RuntimeError):c.poll(serial([request(),request()]))
   with self.assertRaises(RuntimeError):c.poll(serial([request(1)]))
   self.assertEqual(vm.calls,[]);c.poll(serial([request()]));r=request();r['client']['title']='changed'
   with self.assertRaises(RuntimeError):c.poll(serial([r]))
 def test_dead_vm_and_missing_capture_refused(self):
  with tempfile.TemporaryDirectory() as d:
   c,vm,_=self.fixture(d);vm.live=False
   with self.assertRaises(RuntimeError):c.poll(serial([request()]))
   self.assertEqual(vm.calls,[])
  with tempfile.TemporaryDirectory() as d:
   c,vm,_=self.fixture(d);vm.shot=lambda _:None
   with self.assertRaises(RuntimeError):c.poll(serial([request()]))
   self.assertEqual(vm.calls,[])
 def test_stale_capture_and_deadline_refused(self):
  with tempfile.TemporaryDirectory() as d:
   c,vm,clock=self.fixture(d);old=vm.shot
   def shot(n):clock.sleep(2.1);return old(n)
   vm.shot=shot
   with self.assertRaises(RuntimeError):c.poll(serial([request()]))
   self.assertEqual(vm.calls,[])
  with tempfile.TemporaryDirectory() as d:
   c,vm,clock=self.fixture(d);clock.sleep(30)
   with self.assertRaises(RuntimeError):c.press(['ret'],'n',20)
   self.assertEqual(vm.calls,[])
 def test_original_unicode_and_eight_gates_unchanged(self):
  # Preserve the entire recovered v6 workload, including all old gate thresholds.
  new=(HERE/'native_smoke.py').read_text()
  spec=importlib.util.spec_from_file_location('native_diagnostic_byte_reversal',HERE/'test_native_protocol_diagnostics.py')
  controls=importlib.util.module_from_spec(spec);spec.loader.exec_module(controls)
  self.assertEqual(hashlib.sha256(controls.restore_native_source(new).encode()).hexdigest(),'99d5814d438f8777ea5292205b1b70b9c3c3bd12eeefc5ddc77d002693c8a73b')
  self.assertIn('Unicode:',new)
  self.assertIn("self.wait(lambda:directory.name in self.alive(proof).get('title',''),30,",new)


 def test_real_host_receipt_pairing_and_missing_hash_nonce_focus_negatives(self):
  spec=importlib.util.spec_from_file_location('physical_native_runner',HERE/'evidence.py');N=importlib.util.module_from_spec(spec);spec.loader.exec_module(N)
  # Audit-only fixture binds the exact deployed library copy; production has its normal tools/lib path.
  mapped=HERE.parent/'execution-tree/tools/native-functional-v6'
  if mapped.is_dir():N.HERE=mapped
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);vmout=d/'vm';vmout.mkdir();target=d/'native';target.mkdir();c,vm,_=self.fixture(vmout);values=[request(i) for i in range(5)]
   for i in range(5):c.poll(serial(values[:i+1]))
   trace=''.join(json.dumps(dict(event='physical-request',request=r))+'\n' for r in values)
   (target/'gui-trace.log').write_text(trace);(target/'gui-trace-summary.json').write_text('{"omitted_records":0}')
   self.assertEqual(N.check_physical(serial(values),'live',vmout,target)['requests'],5)
   (target/'gui-trace-summary.json').write_text('{"omitted_records":1}')
   with self.assertRaises(RuntimeError):N.check_physical(serial(values),'live',vmout,target)
   (target/'gui-trace-summary.json').write_text('{"omitted_records":0}')
   rows=c.log.read_text();c.log.write_text(rows.replace('"exact_press_release": true','"exact_press_release": false',1))
   with self.assertRaises(RuntimeError):N.check_physical(serial(values),'live',vmout,target)
   c.log.write_text(rows);(vmout/'native-physical-live-1-before.png').write_bytes(b'wrong')
   with self.assertRaises(RuntimeError):N.check_physical(serial(values),'live',vmout,target)


 def test_generated_harness_default_qemu_devices_unchanged(self):
  new=HERE.parents[1]/'tools/test-install.sh'
  if not new.is_file():new=HERE.parent/'registered-test-install-native-v6.sh'
  b=new.read_text().split("read -r -d '' DRIVER <<'PY' || true\n",1)[1].split('\nPY\n',1)[0]
  pins={'qemu_argv': '1affda551d62e21bbe29c824dea918b52e21ac92ddc5dc4477acb944050fa69e', 'open_terminal': 'bf2e81e51ff3abad73b3399e40e0b73522a9eee065f754bf94f9a38144ba6042'}
  tree=ast.parse(b)
  for name,expected in pins.items():
   node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
   self.assertEqual(hashlib.sha256(ast.get_source_segment(b,node).encode()).hexdigest(),expected)
  self.assertIn('if physical_module is None:return False',b)
  self.assertNotIn('activate',b[b.index('def physical_poll'):b.index('def qemu_argv')])


 def test_actual_poll_partial_utf8_waits_complete_invalid_and_final_data_reject(self):
  import os
  from types import SimpleNamespace
  new=HERE.parents[1]/'tools/test-install.sh'
  if not new.is_file():new=HERE.parent/'registered-test-install-native-v6.sh'
  driver=new.read_text().split("read -r -d '' DRIVER <<'PY' || true\n",1)[1].split('\nPY\n',1)[0]
  node=next(n for n in ast.parse(driver).body if isinstance(n,ast.FunctionDef) and n.name=='physical_poll')
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);serialfile=d/'serial-install.log';vm=VM(d)
   env=dict(os=os,E={'NATIVE_PHYSICAL_CHECKER_SHA':'2'*64},physical_module=C,physical_controllers={},out=str(d),serial=lambda name:str(serialfile),vmtest=SimpleNamespace(chord_for=chord))
   exec(compile(ast.Module(body=[node],type_ignores=[]),'actual-generated-physical-poll','exec'),env)
   begin='ARCTIC-NATIVE-RUNNER-BEGIN '+json.dumps(dict(stage='live',checker_sha256='2'*64,release_acceptance=False))+'\n'
   for pending in (b'\xd7',b'gui: \xd7',b'ARCTIC-NATIVE-PCMANFM-PHYSICAL {"nonce":'):
    serialfile.write_bytes(begin.encode()+pending);self.assertTrue(env['physical_poll'](vm,'install'));self.assertEqual(vm.calls,[])
   serialfile.write_bytes(begin.encode()+'gui: שלום\n'.encode());self.assertTrue(env['physical_poll'](vm,'install'))
   serialfile.write_bytes(begin.encode()+b'gui: \xff\n')
   with self.assertRaises(UnicodeDecodeError):env['physical_poll'](vm,'install')
   serialfile.write_bytes(begin.encode()+b'x'*65537)
   with self.assertRaisesRegex(RuntimeError,'unfinished line bound'):env['physical_poll'](vm,'install')
   serialfile.write_bytes(begin.encode()+b'gui: \xd7')
   with self.assertRaises(UnicodeDecodeError):serialfile.read_text() # actual final run uses this strict reader
   spec=importlib.util.spec_from_file_location('native_final_malformed',HERE/'evidence.py');N=importlib.util.module_from_spec(spec);spec.loader.exec_module(N)
   malformed=serial([request(i) for i in range(5)])+C.PREFIX+'{"nonce":'
   with self.assertRaises(json.JSONDecodeError):N.check_physical(malformed,'live',d,d)


class ActualPayloadControls(unittest.TestCase):
 """Execute the actual generated staging prefix, then existing xorriso; never QEMU."""
 def test_real_harness_staging_cd_readback_and_missing_input(self):
  import os,subprocess,shutil
  harness=HERE.parents[1]/'tools/test-install.sh'
  if not harness.is_file():harness=HERE.parent/'registered-test-install-native-v6.sh'
  text=harness.read_text();prefix=text.split('\narctic_ensure_engine\n',1)[0]
  lib=HERE.parents[1]/'tools'
  if not (lib/'lib/container.sh').is_file():lib=Path('/workspace/arctic-native-v4-qualification/tools')
  prefix=prefix.replace('HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"','HERE='+repr(str(lib)))
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);iso=d/'unused-fixture.iso';iso.write_bytes(b'fixture');profile=d/'profile.toml';profile.write_text('[account]\nusername="arctic"\n')
   args=['bash','-c',prefix,'native-staging-control','--iso',str(iso),'--profile',str(profile),'--out',str(d/'stage'),'--guest-check',str(HERE/'guest-check-native-v6.py')]
   env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
   env.update(ARCTIC_NATIVE_AUDIO_FIXTURE='1',ARCTIC_NATIVE_EDITOR_SAVE_FIXTURE='1',ARCTIC_NATIVE_LAUNCHER=str(HERE/'native-launcher-v6.py'),ARCTIC_NATIVE_PHYSICAL_CONTROLLER=str(HERE/'native-physical-controller.py'),ARCTIC_NATIVE_PHYSICAL_SHA=hashlib.sha256((HERE/'native-physical-controller.py').read_bytes()).hexdigest(),ARCTIC_NATIVE_PHYSICAL_CHECKER_SHA=hashlib.sha256((HERE/'guest-check-native-v6.py').read_bytes()).hexdigest())
   done=subprocess.run(args,env=env,capture_output=True,timeout=30);self.assertEqual(done.returncode,0,done.stderr.decode())
   expected={'profile.toml','guest-check.py','native-launcher.py','run.sh','collect.sh'}
   self.assertEqual({p.name for p in (d/'stage/data').iterdir()},expected)
   self.assertEqual((d/'stage/data/guest-check.py').read_bytes(),(HERE/'guest-check-native-v6.py').read_bytes())
   self.assertEqual((d/'stage/data/native-launcher.py').read_bytes(),(HERE/'native-launcher-v6.py').read_bytes())
   env['ARCTIC_NATIVE_PHYSICAL_CONTROLLER']=str(d/'missing.py')
   bad=subprocess.run(args,env=env,capture_output=True,timeout=30);self.assertNotEqual(bad.returncode,0)
   if not shutil.which('xorriso'):self.skipTest('Host xorriso absent; actual staging passed, real CD readback remains separately required')
   cmd=['xorriso','-as','mkisofs','-quiet','-V','ARCTICTEST','-J','-R','-G',str(d/'stage/sysarea.sh'),'-o',str(d/'data.iso'),str(d/'stage/data')]
   subprocess.run(cmd,check=True,capture_output=True,timeout=30)
   readback=d/'readback';subprocess.run(['xorriso','-osirrox','on','-indev',str(d/'data.iso'),'-extract','/',str(readback)],check=True,capture_output=True,timeout=30)
   self.assertEqual({p.name for p in readback.iterdir()},expected)
   for name in expected:self.assertEqual((readback/name).read_bytes(),(d/'stage/data'/name).read_bytes())

if __name__=='__main__':unittest.main()
