"""Finite owned synthetic host controls; no actual GUI, VM or security authority."""
import ast,copy,hashlib,importlib.util,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
def load(name,file):
 s=importlib.util.spec_from_file_location(name,HERE/file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
C=load('desktop_editor_control','native-physical-controller.py');S=load('desktop_smoke_control','native_smoke.py')
class Clock:
 def __init__(self):self.now=10.
 def __call__(self):return self.now
 def sleep(self,n):self.now+=n
class VM:
 def __init__(self,out):self.out=out;self.calls=[];self.answer={'return':{}};self.live=True
 def alive(self):return self.live
 def shot(self,name):p=self.out/(name+'.png');p.write_bytes(b'\x89PNG\r\n\x1a\nsynthetic');return str(p)
 def cmd(self,name,**kw):self.calls.append((name,kw));return self.answer
def editor_request():
 root='/tmp/arctic-native-smoke-test';file=root+'/files with spaces/editor fixture.txt'
 return dict(schema='arctic-native-editor-save-v1',stage='live',nonce='9'*32,boot_id='11111111-1111-1111-1111-111111111111',desktop_uid=1000,
  process=dict(pid=61,start_ticks=610,uid=1000,executable='/usr/bin/featherpad',executable_sha256='1'*64,is_xwayland=False,client_id='3'),
  client=dict(id=3,pid=61,is_focused=True,is_visible=True,is_xwayland=False,appid='featherpad',title='*'+file,foreign_toplevel_id='owned-editor'),
  action='save-editor',path=file,evidence_root=root,monotonic_ns=1_000_000_000,client_monotonic_ns=999_000_000,release_acceptance=False,accessibility_proof=False)
def serial(r):
 l=dict(stage='live',boot_id=r['boot_id'],launcher_sha256='e948f2ff9c7273f20b0d42e67cc891e3a3f6e0954dfc1ac3afca2aa7c3d7df4c',owned_launcher_gone=True,foot={'uid':1000},shell={'uid':1000},probe={'uid':0})
 return '\n'.join(['ARCTIC-NATIVE-LAUNCHER-GONE '+json.dumps(l),'ARCTIC-NATIVE-RUNNER-BEGIN '+json.dumps(dict(stage='live',checker_sha256='2'*64,release_acceptance=False)),C.EDITOR_PREFIX+json.dumps(r,sort_keys=True)])+'\n'
def fullscreen_fixture(value,visual,moving_shot):
 """Data-only synthetic positive proof; never claims real GUI or activation."""
 turns=[];caps=[];owned=[];root=value['evidence_root'];monitor=dict(name='FIXTURE',x=0,y=0,width=160,height=120,scale=1,is_hdr=False)
 for i in range(2):
  p=dict(client_id=str(7+i),pid=70+i,start_ticks=700+i,executable='/usr/bin/celluloid',executable_sha256='1'*64,is_xwayland=False)
  owned.append(p);full=dict(id=7+i,pid=70+i,appid='celluloid',foreign_toplevel_id='owned-'+str(i),monitor='FIXTURE',is_xwayland=False,is_focused=True,is_visible=True,is_fullscreen=True,x=0,y=0,width=160,height=120)
  tiled=dict(full,is_fullscreen=False,x=0,y=0,width=160,height=120)
  for j,enabled in enumerate((True,False)):
   turns.append(dict(player=dict(p,uid=1000),enabled=enabled,before=copy.deepcopy(tiled if enabled else full),after=copy.deepcopy(full if enabled else tiled),monitors_before=dict(monitors=[monitor]),monitors_after=dict(monitors=[monitor]),action=dict(argv=['mmsg','dispatch','togglefullscreen','client,'+p['client_id']],returncode=0,stdout='{"success":true}',stderr=''),monotonic_ns=100+i*100+j*20,completed_monotonic_ns=110+i*100+j*20,release_acceptance=False))
  shot=moving_shot if i==0 else visual['screenshot'];caps.append(dict(player=dict(p,uid=1000),before=copy.deepcopy(full),after=copy.deepcopy(full),screenshot=shot,release_acceptance=False))
 visual['player']=owned[1];value['proven_new_processes']=owned
 value['diagnostic_controls']=dict(gui_v6=True,editor_physical_save=True,owned_player_fullscreen=True,accessibility_proof=False)
 trace=[dict(event='owned-player-fullscreen',receipt=x) for x in turns]+[dict(event='owned-fullscreen-capture',receipt=x) for x in caps]
 return {'fullscreen-player-receipts.json':json.dumps(turns).encode(),'fullscreen-player-captures.json':json.dumps(caps).encode(),'gui-trace.log':''.join(json.dumps(x)+'\n' for x in trace).encode(),'gui-trace-summary.json':b'{"omitted_records":0}','moving-player-proof.json':json.dumps(dict(player=owned[0],screenshot=moving_shot)).encode()}
class EditorControls(unittest.TestCase):
 def fixture(self,d):
  clock=Clock();vm=VM(Path(d));c=C.EditorSaveController(vm,d,'live','2'*64,clock=clock,sleep=clock.sleep);return c,vm,clock
 def test_actual_single_ctrl_s_press_release_one_use(self):
  with tempfile.TemporaryDirectory() as d:
   c,vm,_=self.fixture(d);r=editor_request();c.poll(serial(r));c.poll(serial(r))
   self.assertEqual(len(vm.calls),1);self.assertEqual(vm.calls[0][0],'input-send-event')
   self.assertEqual([e['data']['key']['data'] for e in vm.calls[0][1]['events']],['ctrl','s','s','ctrl'])
   self.assertEqual([e['data']['down'] for e in vm.calls[0][1]['events']],[True,True,False,False])
   self.assertEqual([x['event'] for x in map(json.loads,c.log.read_text().splitlines())],['editor-save-consumed','capture','qmp-key','capture','editor-save-delivered'])
 def test_identity_file_focus_start_uid_negative_no_input(self):
  mutations=[lambda r:r['client'].update(is_focused=False),lambda r:r['client'].update(is_visible=False),lambda r:r['client'].update(pid=99),lambda r:(r['client'].update(id=0),r['process'].update(client_id='0')),lambda r:r['client'].update(id=True),lambda r:r['client'].update(is_xwayland=True),lambda r:r['client'].update(appid='other'),lambda r:r['client'].update(title='*other.txt'),lambda r:r['process'].update(start_ticks=True),lambda r:r['process'].update(uid=1001),lambda r:r['process'].update(executable='/tmp/featherpad'),lambda r:r.update(path='/tmp/other'),lambda r:r.update(monotonic_ns=4_000_000_000),lambda r:r.update(accessibility_proof=True)]
  for mutate in mutations:
   with tempfile.TemporaryDirectory() as d:
    c,vm,_=self.fixture(d);r=editor_request();mutate(r)
    with self.assertRaises(RuntimeError):c.poll(serial(r))
    self.assertEqual(vm.calls,[])
 def test_failed_qmp_no_retry_and_after_capture_deadline(self):
  with tempfile.TemporaryDirectory() as d:
   c,vm,_=self.fixture(d);vm.answer={'return':False}
   with self.assertRaises(RuntimeError):c.poll(serial(editor_request()))
   vm.answer={'return':{}};c.poll(serial(editor_request()));self.assertEqual(len(vm.calls),1)
  with tempfile.TemporaryDirectory() as d:
   c,vm,clock=self.fixture(d);old=vm.shot
   def shot(name):
    if name.endswith('-after'):clock.sleep(26)
    return old(name)
   vm.shot=shot
   with self.assertRaisesRegex(RuntimeError,'exceeded'):c.poll(serial(editor_request()))
   self.assertNotIn('editor-save-delivered',c.log.read_text())
 def test_duplicate_changed_missing_source_and_early_focus_stale(self):
  with tempfile.TemporaryDirectory() as d:
   c,vm,_=self.fixture(d);r=editor_request()
   with self.assertRaises(RuntimeError):c.poll(serial(r)+C.EDITOR_PREFIX+json.dumps(r,sort_keys=True)+'\n')
   with self.assertRaises(RuntimeError):c.poll(serial(r).replace('ARCTIC-NATIVE-RUNNER-BEGIN ','MISSING '))
   self.assertEqual(vm.calls,[])
   c.poll(serial(r));r['client']['foreign_toplevel_id']='changed'
   with self.assertRaises(RuntimeError):c.poll(serial(r))
  with tempfile.TemporaryDirectory() as d:
   c,vm,clock=self.fixture(d);old=vm.shot
   def shot(name):clock.sleep(2.1);return old(name)
   vm.shot=shot
   with self.assertRaisesRegex(RuntimeError,'stale'):c.poll(serial(editor_request()))
   self.assertEqual(vm.calls,[])
 def test_guest_emits_no_focus_repair_and_requires_current_document(self):
  with tempfile.TemporaryDirectory() as d,patch.object(S.Path,'read_text',return_value=editor_request()['boot_id']),patch.object(S,'digest',return_value='1'*64):
   smoke=S.Smoke.__new__(S.Smoke);smoke.root=Path('/tmp/arctic-native-smoke-test');smoke.stage='live';smoke.uid=1000;smoke.trace=lambda *a,**k:None
   r=editor_request();smoke.alive=lambda _:r['client'];smoke.cmd=lambda _:self.fail('focus repair forbidden')
   import contextlib,io
   with contextlib.redirect_stdout(io.StringIO()):smoke.physical_editor_save(r['process'],Path(r['path']))
   with self.assertRaises(RuntimeError):smoke.physical_editor_save(r['process'],Path(r['path']))

 def test_host_actual_save_receipt_pairing_elapsed_and_saved_bytes(self):
  N=load('desktop_editor_raw','evidence.py');F=load('desktop_pc_fixture','test_native_physical_v6.py')
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);out=d/'host';out.mkdir();target=d/'guest';target.mkdir();c,vm,_=self.fixture(out);r=editor_request();c.poll(serial(r))
   pc=[F.request(i) for i in range(5)];raw=F.serial(pc[:3])+C.EDITOR_PREFIX+json.dumps(r,sort_keys=True)+'\n'+''.join(C.PREFIX+json.dumps(x,sort_keys=True)+'\n' for x in pc[3:])
   report=dict(evidence_root=r['evidence_root'],proven_new_processes=[dict(r['process'])]);proof=dict(boot_id=r['boot_id'],desktop_uid=1000)
   (target/'serial-native-report.json').write_text(json.dumps(report));(target/'serial-native-provenance.json').write_text(json.dumps(proof))
   (target/'gui-trace.log').write_text(json.dumps(dict(event='editor-physical-request',request=r))+'\n');(target/'gui-trace-summary.json').write_text('{"omitted_records":0}')
   fixture=target/'files with spaces/editor fixture.txt';fixture.parent.mkdir();wanted=('Arctic GUI saved fixture '+Path(r['evidence_root']).name+'\nUnicode: שלום λ 日本語\n').encode();fixture.write_bytes(wanted)
   self.assertEqual(N.check_editor_save(raw,'live',out,target)['requests'],1)
   log=c.log.read_text();rows=[json.loads(x) for x in log.splitlines()]
   for mutate in (lambda rs:rs[-1].update(monotonic_seconds=rs[0]['monotonic_seconds']+26),lambda rs:rs[1].update(monotonic_seconds=rs[0]['monotonic_seconds']+2.1),lambda rs:rs[2].update(chord=['ret']),lambda rs:rs[-1]['request']['process'].update(start_ticks=999),lambda rs:rs[2].update(response={'return':False})):
    altered=copy.deepcopy(rows);mutate(altered);c.log.write_text(''.join(json.dumps(x)+'\n' for x in altered))
    with self.assertRaises(RuntimeError):N.check_editor_save(raw,'live',out,target)
   c.log.write_text(log)
   for name,content in [('gui-trace-summary.json','{"omitted_records":1}'),('serial-native-provenance.json',json.dumps(dict(proof,desktop_uid=1001))),('serial-native-report.json',json.dumps(dict(report,proven_new_processes=[])))]:
    path=target/name;old=path.read_text();path.write_text(content)
    with self.assertRaises(RuntimeError):N.check_editor_save(raw,'live',out,target)
    path.write_text(old)
   fixture.write_bytes(b'original unsaved bytes')
   with self.assertRaises(RuntimeError):N.check_editor_save(raw,'live',out,target)
   fixture.write_bytes(wanted)
   with self.assertRaises(RuntimeError):N.check_editor_save(raw.replace(C.EDITOR_PREFIX,'MISSING '),'live',out,target)
   bad=F.serial(pc)+C.EDITOR_PREFIX+json.dumps(r,sort_keys=True)+'\n'
   with self.assertRaises(RuntimeError):N.check_editor_save(bad,'live',out,target)

class FullscreenControls(unittest.TestCase):
 def test_supported_owned_action_complete_viewport_restore_no_focus_repair(self):
  with tempfile.TemporaryDirectory() as d:
   s=S.Smoke.__new__(S.Smoke);s.root=Path(d);s.uid=1000;s.trace=lambda *a,**k:None
   p=dict(executable='/usr/bin/celluloid',is_xwayland=False,client_id='7',pid=70,start_ticks=700)
   current=dict(id=7,pid=70,appid='celluloid',foreign_toplevel_id='own',monitor='M',is_focused=True,is_visible=True,is_fullscreen=False,x=0,y=0,width=160,height=120)
   monitor=dict(name='M',x=0,y=0,width=640,height=480,scale=1,is_hdr=False);calls=[]
   s.alive=lambda _:copy.deepcopy(current);s.wait=lambda fn,*a:fn()
   def cmd(argv):
    calls.append(argv)
    if argv==['mmsg','get','all-monitors']:return 0,json.dumps(dict(monitors=[monitor])),''
    self.assertEqual(argv,['mmsg','dispatch','togglefullscreen','client,7']);current['is_fullscreen']=not current['is_fullscreen'];current.update(width=640 if current['is_fullscreen'] else 160,height=480 if current['is_fullscreen'] else 120);return 0,'{"success":true}',''
   s.cmd=cmd;s.player_fullscreen(p,True);self.assertTrue(current['is_fullscreen']);s.player_fullscreen(p,False);self.assertFalse(current['is_fullscreen'])
   self.assertFalse(any('focusid' in x for x in calls))
 def test_fullscreen_unfocused_or_incomplete_viewport_rejects(self):
  with tempfile.TemporaryDirectory() as d:
   s=S.Smoke.__new__(S.Smoke);s.root=Path(d);s.uid=1000;s.trace=lambda *a,**k:None
   p=dict(executable='/usr/bin/celluloid',is_xwayland=False,client_id='7',pid=70,start_ticks=700)
   c=dict(id=7,pid=70,appid='celluloid',foreign_toplevel_id='own',monitor='M',is_focused=False,is_visible=True,is_fullscreen=False,x=0,y=0,width=160,height=120)
   m=dict(name='M',x=0,y=0,width=640,height=480,scale=1,is_hdr=False);calls=[];s.alive=lambda _:c;s.cmd=lambda a:(calls.append(a) or (0,json.dumps(dict(monitors=[m])),''))
   with self.assertRaises(RuntimeError):s.player_fullscreen(p,True)
   self.assertFalse(any('dispatch' in a for a in calls))
   c['is_focused']=True
   def dispatch(argv):
    calls.append(argv)
    if argv==['mmsg','get','all-monitors']:return 0,json.dumps(dict(monitors=[m])),''
    c['is_fullscreen']=True;return 0,'{"success":true}',''
   s.cmd=dispatch;s.wait=lambda fn,*a:fn()
   with self.assertRaisesRegex(RuntimeError,'complete'):s.player_fullscreen(p,True)

 def test_capture_pair_rejects_focus_identity_geometry_and_failed_restore(self):
  with tempfile.TemporaryDirectory() as d:
   s=S.Smoke.__new__(S.Smoke);s.root=Path(d);s.uid=1000;s.trace=lambda *a,**k:None
   p=dict(executable='/usr/bin/celluloid',is_xwayland=False,client_id='7',pid=70,start_ticks=700)
   c=dict(id=7,pid=70,appid='celluloid',foreign_toplevel_id='own',monitor='M',is_focused=True,is_visible=True,is_fullscreen=True,x=0,y=0,width=640,height=480)
   shot=dict(path=str(s.root/'frame.png'),sha256='1'*64)
   for k,v in [('is_focused',False),('is_visible',False),('pid',71),('foreign_toplevel_id','other'),('width',639),('is_fullscreen',False)]:
    after=dict(c);after[k]=v
    with self.assertRaises(RuntimeError):s.fullscreen_capture_pair(p,c,after,shot)
   s.fullscreen_capture_pair(p,c,c,shot)
   self.assertEqual(len(s.fullscreen_captures),1)
   monitor=dict(name='M',x=0,y=0,width=640,height=480,scale=1,is_hdr=False);s.alive=lambda _:c
   s.cmd=lambda argv:(0,json.dumps(dict(monitors=[monitor])),'') if argv==['mmsg','get','all-monitors'] else (1,'{"success":false}','explicit synthetic failure')
   with self.assertRaises(RuntimeError):s.player_fullscreen(p,False)

 def test_actual_host_fullscreen_raw_pairing_and_adverses(self):
  N=load('desktop_host_fullscreen','evidence.py')
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);root='/tmp/arctic-native-smoke-test';png=b'\x89PNG\r\n\x1a\nsynthetic';(d/'moving.png').write_bytes(png);(d/'static.png').write_bytes(png)
   shot=lambda n:dict(path=root+'/'+n,sha256=hashlib.sha256(png).hexdigest())
   value=dict(evidence_root=root);visual=dict(screenshot=shot('static.png'));files=fullscreen_fixture(value,visual,shot('moving.png'));files['visual-oracle.json']=json.dumps(visual).encode()
   for n,b in files.items():(d/n).write_bytes(b)
   self.assertEqual(N.check_fullscreen(d,value,1000)['captures'],2)
   turns=json.loads(files['fullscreen-player-receipts.json'])
   def rerun(mutate):
    v=copy.deepcopy(value);ts=copy.deepcopy(turns);cs=json.loads(files['fullscreen-player-captures.json']);mutate(v,ts,cs)
    trace=[dict(event='owned-player-fullscreen',receipt=x) for x in ts]+[dict(event='owned-fullscreen-capture',receipt=x) for x in cs]
    (d/'fullscreen-player-receipts.json').write_text(json.dumps(ts));(d/'fullscreen-player-captures.json').write_text(json.dumps(cs));(d/'gui-trace.log').write_text(''.join(json.dumps(x)+'\n' for x in trace))
    with self.assertRaises((RuntimeError,KeyError)):N.check_fullscreen(d,v,1000)
   for mutate in [lambda v,t,c:t[0]['action'].update(argv=['mmsg','dispatch','focusid','client,7']),lambda v,t,c:t[0]['after'].update(width=159),lambda v,t,c:t[3].update(enabled=True),lambda v,t,c:c[0]['before'].update(is_focused=False),lambda v,t,c:t[0]['player'].update(start_ticks=True),lambda v,t,c:t[0]['player'].update(uid=1001),lambda v,t,c:t[0].update(monotonic_ns=False),lambda v,t,c:v.update(proven_new_processes=[]),lambda v,t,c:c[0]['after'].update(foreign_toplevel_id='changed'),lambda v,t,c:t[0]['after'].update(foreign_toplevel_id='changed'),lambda v,t,c:t[1]['action'].update(returncode=1)]:rerun(mutate)

class HarnessControls(unittest.TestCase):
 def test_original_five_controller_and_default_false_guest_remain_exact(self):
  prior=HERE/'predecessor-native-v5.txt';new=(HERE/'native_smoke.py').read_text();tree=ast.parse(new)
  call=next(n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='run_checks')
  self.assertFalse(any(k.arg=='gui_v6' for k in call.keywords))
  fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_checks')
  self.assertIs(fn.args.kw_defaults[-1].value,False)
  self.assertEqual(hashlib.sha256((HERE/'native-physical-controller.py').read_text().split("EDITOR_PREFIX=",1)[0].rstrip().encode()).hexdigest(),'5a8cc6436335a8ea49feca8bcd8dd40746f9f2811f6976d3f3ebbd200f1eec6c')
 def test_actual_generated_poll_default_off_and_selected_editor_path(self):
  import os
  F=load('desktop_poll_fixture','test_native_physical_v6.py')
  harness=HERE.parents[1]/'tools/test-install.sh'
  if not harness.is_file():harness=HERE.parent/'registered-test-install-native-v6.sh'
  text=harness.read_text();driver=text.split("read -r -d '' DRIVER <<'PY' || true\n",1)[1].split('\nPY\n',1)[0]
  node=next(n for n in ast.parse(driver).body if isinstance(n,ast.FunctionDef) and n.name=='physical_poll')
  self.assertIn('case "$NATIVE_EDITOR_SAVE_FIXTURE" in 0|1)',text)
  self.assertIn('${ARCTIC_NATIVE_EDITOR_SAVE_FIXTURE:-0}',text)
  for mode in ('0','1'):
   with tempfile.TemporaryDirectory() as d:
    d=Path(d);rawfile=d/'serial-install.log';vm=VM(d);rawfile.write_text(serial(editor_request()))
    env=dict(os=os,E={'NATIVE_PHYSICAL_CHECKER_SHA':'2'*64,'NATIVE_EDITOR_SAVE_FIXTURE':mode},physical_module=C,physical_controllers={},out=str(d),serial=lambda name:str(rawfile),vmtest=SimpleNamespace(chord_for=F.chord))
    exec(compile(ast.Module(body=[node],type_ignores=[]),'actual-generated-poll','exec'),env)
    self.assertTrue(env['physical_poll'](vm,'install'));self.assertEqual(len(vm.calls),0 if mode=='0' else 1)
    env['physical_poll'](vm,'install');self.assertEqual(len(vm.calls),0 if mode=='0' else 1)

if __name__=='__main__':unittest.main()
