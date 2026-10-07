#!/usr/bin/env python3
"""Bounded host controls: source/transport contracts only; no VM/GUI claims."""
import ast,copy,hashlib,importlib.util,json,os,subprocess,sys,tempfile,types,unittest
from pathlib import Path
from unittest import mock
HERE=Path(__file__).resolve().parent
for name in list(os.environ):
 if name.startswith('GIT_'):os.environ.pop(name)
def load(name):
 spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'));mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
W=load('wire-input');I=load('input-collector');C=load('checked-preflight');X=load('extract-preflight');G=load('prepare-integration');E=load('guest-preflight');Q=load('preflight-core');D=load('preflight-runner')
def workflow_path(root=HERE):
 audit=root/'registered-iso-preflight.yml'
 try:audit.lstat();selected=audit
 except FileNotFoundError:selected=root.parents[1]/'.github/workflows/iso.yml'
 if selected.is_symlink() or not selected.is_file():raise RuntimeError('selected workflow must be regular')
 return selected
def wire(turn,warm):
 symbols,emissions=W.expected(turn,warm)
 lines=[' -> wl_display#1.get_registry(new id wl_registry#2)',
        'wl_registry#2.global(1, "wl_seat", 9)','wl_registry#2.global(2, "zwp_virtual_keyboard_manager_v1", 1)',
        ' -> zwp_virtual_keyboard_manager_v1#4.create_virtual_keyboard(wl_seat#3, new id zwp_virtual_keyboard_v1#5)',
        ' -> zwp_virtual_keyboard_v1#5.keymap(1, fd 6, 600)']
 lines+=[' -> zwp_virtual_keyboard_v1#5.%s(%s)'%(item[0],', '.join(str(x) for x in item[1:])) for item in emissions]
 lines+=[' -> zwp_virtual_keyboard_v1#5.destroy()']
 return ''.join('[01:38:13.687597] {Default Queue} '+x+'\n' for x in lines).encode()
def producer(turn,warm):
 symbols,_=W.expected(turn,warm)
 return dict(identity=dict(map_bytes=600,maximum=len(symbols)+9,last_emitted_named_code=len(symbols)+8,
 return_codes=[dict(keycode=symbols.index('Return')+9,group=0,level=0)] if turn==2 else []))
class Source(unittest.TestCase):
 def test_pure_fixed_base_harness_reproduction(self):self.assertEqual(G.harness((HERE/'base-test-iso.sh').read_text()),(HERE/'registered-test-iso.sh').read_text() if (HERE/'registered-test-iso.sh').exists() else (HERE.parents[1]/'tools/test-iso.sh').read_text())
 def test_pure_fixed_base_workflow_reproduction(self):self.assertEqual(G.workflow((HERE/'base-iso.yml').read_text()),workflow_path().read_text())
 def test_default_original_harness_bytes_recover(self):
  before=(HERE/'base-test-iso.sh').read_text();after=G.harness(before)
  self.assertEqual(after.count('bulk_module.run_owned('),2)
  start=before.index('if os.environ.get("PCMANFM_DIAGNOSTIC") == "1":');end=before.index('\n# 2. Splash and boot:',start)
  self.assertIn(before[start:end],after)
  self.assertIn('-serial "file:$OUT/serial.log"',after)
  self.assertNotIn('forward_to_console=0',after)
 def test_extractor_only_six_map_path_adaptation(self):
  node=next(n for n in ast.parse((HERE/'extract-preflight.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='extract_preflight')
  node.name='extract_evidence'
  boolean=next(n for n in ast.walk(node) if isinstance(n,ast.BoolOp) and isinstance(n.op,ast.Or) and any(isinstance(v,ast.Call) and isinstance(v.func,ast.Attribute) and v.func.attr=='fullmatch' for v in n.values))
  parent=next(n for n in ast.walk(node) if hasattr(n,'values') and boolean in n.values);parent.values[parent.values.index(boolean)]=boolean.values[0]
  self.assertEqual(hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest(),'f38ab7dd0e6b2ba9048212138bbdcc9fa3463806ef0073d60f0714be2efac984')
 def test_candidate_signed_receipts_bind_all_eight_headers(self):
  receipts=json.loads((HERE/'candidate-rpm-receipts.json').read_text());allow=json.loads((HERE/'candidate-input-libraries.json').read_text())
  self.assertEqual(len(receipts),6);self.assertEqual(len(allow['files']),8);self.assertEqual(sum(row['bytes'] for row in receipts.values()),9133072)
  for path,expected in allow['files'].items():
   row=receipts[expected['package']]
   self.assertEqual(row['signature']['exit_status'],0);self.assertEqual(row['signature']['stderr'],'')
   self.assertIn('36f612dcf27f7d1a48a835e4dbfcf71c6d9f90a6: OK',row['signature']['stdout']);self.assertIn('Payload SHA256 digest: OK',row['signature']['stdout'])
   header=[line.split('\t') for line in row['file_header']['stdout'].splitlines() if line.split('\t')[0]==path];self.assertEqual(len(header),1)
   self.assertEqual(header[0][1],expected['sha256']);self.assertEqual(int(header[0][2])&0o777,expected['mode']);self.assertEqual(header[0][3:5],['root','root'])
 def test_no_input_override_or_physical_app_control(self):
  for name in ('preflight-core.py','guest-preflight.py','preflight-controller.py'):
   text=(HERE/name).read_text()
   for token in ('GTK_IM_MODULE=','LANG=','LC_ALL=','NO_AT_BRIDGE=','GTK_A11Y=','emit("activate"','emit(\'activate\'','qmp_return','physical_request('):self.assertNotIn(token,text)
  self.assertEqual(Q.ARMS,[('original-warm',False,True),('original-cold',False,False),('sentinel-warm',True,True),('sentinel-cold',True,False)])
 def test_frozen_security_and_bulk_bytes(self):
  for name,sha in {'security-collector.py':'0384cea315112d7cab56129ef43fd5aa92966e25b0e3e35f54f795628ee08527','bulk-channel.py':'5131e3ed5d50d285508d4dc74d8dc8c7e412da17fd0f7072e81e70c3dde36bda','gtk-entry-control.py':'4da8767f466bd8bcc9e55b4ee15400dc4f33fda9d9390a43c059a8e9259b1da3','native_smoke.py':'ed382ab80a4918118370253c383b0fefde116ba34d55e977bcd34607ad2632d0'}.items():self.assertEqual(hashlib.sha256((HERE/name).read_bytes()).hexdigest(),sha)
 def test_input_stream_adaptation_exact(self):
  old=ast.parse((HERE/'security-collector.py').read_text());new=ast.parse((HERE/'input-collector.py').read_text())
  original=next(x for x in old.body if isinstance(x,ast.FunctionDef) and x.name=='run_stream');adapted=next(x for x in new.body if isinstance(x,ast.FunctionDef) and x.name=='run_input_stream')
  original=copy.deepcopy(original);original.name='run_input_stream'
  original.body[-1:] # comparison excludes only the explicit debug-stderr rejection
  test=next(x for x in ast.walk(original) if isinstance(x,ast.Expr) and isinstance(x.value,ast.Call) and isinstance(x.value.func,ast.Name) and x.value.func.id=='require' and len(x.value.args)>1 and isinstance(x.value.args[1],ast.Constant) and x.value.args[1].value=='security command stderr is nonempty; cursor/output validity unproved')
  parent=next(x for x in ast.walk(original) if hasattr(x,'body') and test in x.body);parent.body.remove(test)
  self.assertEqual(ast.dump(original,include_attributes=False),ast.dump(adapted,include_attributes=False))
 def test_workflow_modes_and_fixed_iso(self):
  import yaml
  doc=yaml.safe_load(workflow_path().read_text());trigger=doc.get('on',doc.get(True))
  self.assertIs(trigger['workflow_dispatch']['inputs']['same_iso_gtk_input_preflight']['default'],False)
  jobs=doc['jobs'];self.assertEqual(set(jobs),{'iso','same-iso-installs','same-iso-boot-evidence','same-iso-native-functional','same-iso-pcmanfm-diagnostic','same-iso-gtk-input-preflight'})
  for name,job in jobs.items():
   if name!='same-iso-gtk-input-preflight':self.assertIn('!inputs.same_iso_gtk_input_preflight',job['if'])
  selected=jobs['same-iso-gtk-input-preflight'];self.assertEqual(selected['permissions'],{'contents':'read','actions':'read'})
  env=selected['env'];self.assertEqual(env['GTK_INPUT_PREFLIGHT_MODE'],'true')
  self.assertIn('same_iso_pcmanfm_diagnostic',env['PCMANFM_DIAGNOSTIC_MODE'])
  downloads=[s for s in selected['steps'] if 'download-artifact@' in s.get('uses','')]
  self.assertEqual(len(downloads),1);self.assertEqual(downloads[0]['with']['run-id'],37507582946);self.assertEqual(downloads[0]['with']['artifact-ids'],11434226349)
  self.assertEqual(sum('One fresh live-only finite' in s.get('name','') for s in selected['steps']),1)
 def test_ci_all_mixed_modes_rejected(self):
  R=types.SimpleNamespace(validate_ci=lambda env:None)
  env=dict(GTK_INPUT_PREFLIGHT_MODE='true',PCMANFM_DIAGNOSTIC_MODE='false',RECOVERY_MODE='false',NATIVE_SMOKE_MODE='false',NIX_REQUESTED='false',PERFORMANCE_REQUESTED='false',BOOT_TEST_REQUESTED='false',GITHUB_SHA='f'*40,GITHUB_RUN_ID='123')
  D.validate_ci(env,R)
  for key in ('PCMANFM_DIAGNOSTIC_MODE','RECOVERY_MODE','NATIVE_SMOKE_MODE','NIX_REQUESTED','PERFORMANCE_REQUESTED','BOOT_TEST_REQUESTED'):
   with self.subTest(key=key),self.assertRaises(RuntimeError):D.validate_ci(dict(env,**{key:'true'}),R)
 def test_post_provision_failed_identity_never_executes_vm(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);evidence=root/'evidence';evidence.mkdir();calls=[]
   args=types.SimpleNamespace(evidence=evidence,source=root,bundle=root/'tools/gtk-input-preflight',inputs=root/'inputs')
   R=types.SimpleNamespace(ISO='Arctic-Linux-1.2-x86_64.iso',require_docker=lambda:None,write_json=lambda p,v:p.write_text(json.dumps(v)),execute=lambda *a,**k:((evidence/'vm-prepared-image-id.txt').write_text('a'*64),calls.append(a[0])))
   with mock.patch.object(D,'verify',lambda *x:None),mock.patch.object(D,'proof',lambda *x:{}),mock.patch.object(D,'verify_before_vm',side_effect=RuntimeError('changed source or ISO')),mock.patch.object(Path,'is_char_device',return_value=True),mock.patch.object(D.subprocess,'run'):
    with self.assertRaisesRegex(RuntimeError,'changed source or ISO'):D.run(args,R,None)
   self.assertEqual(len(calls),1);self.assertIn('prepare-vm-tools.sh',calls[0][1])
class Wire(unittest.TestCase):
 def test_all_six_turns_exact_wire_and_endpoint(self):
  for turn in range(3):
   for warm in (False,True):
    for corrected in (False,True):self.assertEqual(W.parse(wire(turn,warm),turn,warm,corrected,producer(turn,warm) if corrected else None)['emissions'],[list(x) for x in W.expected(turn,warm)[1]])
 def test_no_named_sentinel_emission(self):
  for turn in range(3):
   for warm in (False,True):self.assertLess(max(x[2] for x in W.expected(turn,warm)[1] if x[0]=='key')+8,producer(turn,warm)['identity']['maximum'])
 def test_missing_duplicate_wrong_foreign_or_unframed_rejected(self):
  good=wire(2,True)
  for bad in (good[:-1],good+b'not Wayland debug\n',good.replace(b'.destroy()',b'.destroy(1)'),good.replace(b'.key(0, 2, 1)',b'.key(0, 3, 1)'),good.replace(b'keyboard_v1#5.key(0, 2, 1)',b'keyboard_v1#9.key(0, 2, 1)'),good+good,good.replace(b'.keymap(1, fd 6, 600)',b'.keymap(0, fd 6, 600)'),good+b'x'*65536):
   with self.subTest(length=len(bad)),self.assertRaises(RuntimeError):W.parse(bad,2,True,False)
 def test_corrected_wrong_size_or_endpoint_rejected(self):
  for key,value in [('map_bytes',601),('maximum',12),('last_emitted_named_code',8),('return_codes',[])]:
   p=producer(2,True);p['identity'][key]=value
   with self.subTest(key=key),self.assertRaises(RuntimeError):W.parse(wire(2,True),2,True,True,p)
 def test_original_endpoint_explicitly_unobserved(self):
  value=W.parse(wire(2,True),2,True,False)
  self.assertNotIn('maximum',value);self.assertNotIn('map_sha256',value)
class Collector(unittest.TestCase):
 def run_command(self,code,**kwargs):
  temp=tempfile.TemporaryDirectory();root=Path(temp.name);out=bytearray()
  try:
   try:I.run_input_stream([sys.executable,'-c',code],out.extend,root/'command.json',**kwargs);error=None
   except BaseException as exc:error=str(exc)
   return json.loads((root/'command.json').read_text()),(root/'command.stderr.log').read_bytes(),bytes(out),error
  finally:temp.cleanup()
 def test_real_child_complete_debug_stderr_preserved(self):
  r,raw,out,error=self.run_command('import sys;sys.stderr.write("debug\\n")')
  self.assertIsNone(error);self.assertTrue(r['complete']);self.assertEqual(raw,b'debug\n');self.assertEqual(r['stderr_observed_sha256'],hashlib.sha256(raw).hexdigest());self.assertTrue(r['only_owned_child_reaped'])
 def test_real_owned_child_overflow_nonzero_deadline_rejected(self):
  for code,kwargs in [('import sys;sys.stderr.write("x"*200)',dict(stderr_limit=100)),('raise SystemExit(3)',{}),('import time;time.sleep(10)',dict(timeout=.1))]:
   with self.subTest(code=code):
    r,raw,out,error=self.run_command(code,**kwargs);self.assertIsNotNone(error);self.assertFalse(r['complete']);self.assertTrue(r['only_owned_child_reaped'])
 def test_real_pidfd_setup_failure_reaps_child(self):
  with mock.patch.object(I.os,'pidfd_open',side_effect=OSError('controlled setup failure')):
   r,raw,out,error=self.run_command('import time;time.sleep(10)')
  self.assertIn('controlled setup failure',error);self.assertTrue(r['only_owned_child_reaped'])
 def test_raw_command_requires_pid_time_raw_hash(self):
  r,raw,out,error=self.run_command('import sys;sys.stderr.write("debug\\n")');actual=['/usr/bin/wtype','-k','Return'];r['argv']=['runuser','-u','liveuser','--','env','PATH=/usr/bin','env','WAYLAND_DEBUG=client',*actual]
  C.input_command(r,raw,actual,'liveuser',r['argv'][:-len(['env','WAYLAND_DEBUG=client',*actual])])
  for key,value in [('child_pid',True),('monotonic_start_seconds',-1),('monotonic_end_seconds',0),('stderr_observed_sha256','0'*64),('complete',False)]:
   changed=copy.deepcopy(r);changed[key]=value
   with self.subTest(key=key),self.assertRaises(RuntimeError):C.input_command(changed,raw,actual,'liveuser',r['argv'][:-len(['env','WAYLAND_DEBUG=client',*actual])])
class Export(unittest.TestCase):
 def test_six_map_paths_only_and_original_caps(self):
  class Writer:
   def __init__(self):self.rows=[]
   def write(self,*args):self.rows.append(args)
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'sentinel-warm/producer-turn-0').mkdir(parents=True);(root/'sentinel-warm/producer-turn-0/uploaded-map.xkb').write_bytes(b'map\0');writer=Writer();E.export(root,writer)
   self.assertEqual(writer.rows[-1][1]['files'][0]['path'],'sentinel-warm/producer-turn-0/uploaded-map.xkb')
   (root/'other.xkb').write_bytes(b'x')
   with self.assertRaises(RuntimeError):E.export(root,Writer())
 def test_symlink_and_129_file_bound(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'bad.json').symlink_to('/etc/passwd')
   with self.assertRaises(RuntimeError):E.export(root,types.SimpleNamespace(write=lambda *x:None))
   (root/'bad.json').unlink()
   for i in range(129):(root/('%03d.json'%i)).write_bytes(b'{}')
   with self.assertRaises(RuntimeError):E.export(root,types.SimpleNamespace(write=lambda *x:None))
 def test_expected_four_arm_worst_required_member_budget(self):
  # Raw GTK runtime proof adds1 to each prior arm:20 original/32 corrected, with128-file cap unchanged.
  arm_files=2*20+2*32
  security_files=1+1+1+1+1+11+1 # states, framing, report, whole command/stderr, chunks, audit metadata; audit log adds1
  total=arm_files+security_files+1+3 # audit log + provenance/original identity/report
  self.assertLessEqual(total,128);self.assertEqual(total,125)
 def test_real_export_aggregate_limit_and_125_file_layout(self):
  class Writer:
   def __init__(self):self.rows=[]
   def write(self,*args):self.rows.append(args)
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   for i in range(125):(root/('%03d.log'%i)).write_bytes(b'evidence\n')
   writer=Writer();E.export(root,writer);self.assertEqual(len(writer.rows[-1][1]['files']),125)
   # Each file alone is within4MiB, but their aggregate violates16MiB; export must reject before writing any chunks.
   for i in range(5):(root/('%03d.log'%i)).write_bytes(b'x'*(4*1024*1024))
   writer=Writer()
   with self.assertRaises(RuntimeError):E.export(root,writer)
   self.assertEqual(writer.rows,[])
class WorkflowLocation(unittest.TestCase):
 def test_mapped_location_and_invalid_selected_no_fallback(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);bundle=root/'tools/gtk-input-preflight';bundle.mkdir(parents=True);deployed=root/'.github/workflows/iso.yml';deployed.parent.mkdir(parents=True);deployed.write_text('real')
   self.assertEqual(workflow_path(bundle),deployed)
   audit=bundle/'registered-iso-preflight.yml';audit.mkdir()
   with self.assertRaises(RuntimeError):workflow_path(bundle)
   audit.rmdir();audit.symlink_to(bundle/'missing')
   with self.assertRaises(RuntimeError):workflow_path(bundle)
class FullProof(unittest.TestCase):
 def fixture(self,root):
  # Entire GUI/wire/security authority is explicitly synthetic. The real C offline map suite is separate.
  build=json.loads((HERE/'build-payload-pins.json').read_text());allow=json.loads((HERE/'candidate-input-libraries.json').read_text());pins=json.loads((HERE/'runtime-pins.json').read_text())
  dump=lambda path,value:(path.parent.mkdir(parents=True,exist_ok=True),path.write_text(json.dumps(value)+'\n'))
  def receipt(paths):return [dict(path=path,sha256=allow['files'][path]['sha256'],owner=allow['files'][path]['rpm_nevra'],epoch=0,verification=[0,'',''],bytes=100) for path in paths]
  launcher=dict(schema='arctic-native-launcher-v1',stage='live',boot_id='11111111-2222-3333-4444-555555555555',launcher_sha256=pins['native-launcher.py'],owned_launcher_gone=True)
  for name,pid,uid,exe in [('foot',20,1000,'/usr/bin/foot'),('shell',21,1000,'/usr/bin/fish'),('probe',22,0,'/usr/bin/python3.14')]:launcher[name]=dict(pid=pid,start_ticks=123,uid=uid,executable=exe,executable_sha256='a'*64)
  begin=dict(schema='arctic-gtk-input-preflight-begin-v1',checker_sha256='b'*64,native_source_sha256=pins['native_smoke.py'],release_acceptance=False,native_qualification=False)
  prefix=['runuser','-u','liveuser','--','env','HOME=/home/liveuser','XDG_RUNTIME_DIR=/run/user/1000','WAYLAND_DISPLAY=wayland-0','DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus','XDG_SESSION_TYPE=wayland','MANGO_INSTANCE_SIGNATURE=synthetic-sole-signature','PATH=/usr/bin','XDG_DATA_DIRS=/usr/share','LANG=en_US.UTF-8']
  provenance=dict(**begin,desktop_home='/home/liveuser',desktop_prefix=prefix,boot_id=launcher['boot_id'],cmdline='rd.live.image',desktop_uid=1000,desktop_user='liveuser',launcher=launcher,runtime_pins=pins,bulk_port=dict(name='org.arctic.diagnostic.bulk',sysfs_name='org.arctic.diagnostic.bulk',kind='character-device',named_path='/dev/virtio-ports/org.arctic.diagnostic.bulk',resolved_device='/dev/vport0p1',device_major=241,device_minor=1))
  dump(root/'provenance.json',provenance);dump(root/'original-wtype-identity.json',receipt(['/usr/bin/wtype']))
  security=dict(complete=True,selinux='Enforcing',audit={'enabled':1,'lost':0},observed_new_avcs=0)
  arms=[]
  for number,(name,corrected,warm) in enumerate(C.ARMS):
   arm=root/name;arm.mkdir();proof=dict(pid=40+number,start_ticks=123,client_id=str(number+4),executable='/usr/bin/python3.14',executable_sha256='c'*64,is_xwayland=False);appid='org.arctic.Diagnostic.Entry.a'+('%016x'%number)
   process={key:proof[key] for key in ('pid','start_ticks','executable')};gtk_paths=['/usr/bin/python3.14','/usr/lib64/libgtk-3.so.0.2420.32','/usr/lib64/libgdk-3.so.0.2420.32','/usr/lib64/libxkbcommon.so.0.13.1']
   maps=''.join('1-2 r-xp 0000 00:00 1 '+path+'\n' for path in gtk_paths).encode();(arm/'gtk-loaded-maps.txt').write_bytes(maps)
   dump(arm/'gtk-runtime.json',dict(before=process,after=process,uid=1000,process_stat=str(proof['pid'])+' (python3) '+' '.join(['S']+['0']*18+['123']),maps_bytes=len(maps),maps_sha256=hashlib.sha256(maps).hexdigest(),main_executable=dict(path=proof['executable'],sha256=proof['executable_sha256'],uid=0,gid=0,mode=0o755,bytes=200,inode=1,device=2,owner_epoch='python3-SYNTHETIC\t0',verification=[0,'',''],signed_content_allowlist=False)))
   common=dict(pid=proof['pid'],start_ticks=123,uid=1000)
   rows=[dict(common,event='mapped',monotonic_ns=100,appid=appid,program_name=appid,backend='GdkWaylandDisplay')]
   final=producer(2,warm)['identity']['return_codes'];key=dict(common,event='key-press',monotonic_ns=101,keyval=65293,hardware_keycode=10 if warm else 9,state=0,group=0,has_focus=True,is_focus=True,text=W.TEXT,current_map=dict(return_entries_valid=corrected,return_entries=final if corrected else [],event_current_translation=dict(valid=True,keyval=65293,level=0)))
   rows.append(key)
   if corrected:rows.append(dict(common,event='activate',monotonic_ns=102,count=1,has_focus=True,text=W.TEXT))
   (arm/'gtk-events.log').write_text(''.join(json.dumps(row)+'\n' for row in rows))
   trace=[]
   for index,label in enumerate(['gtk-before-input',*[('gtk-after-turn-'+str(i)) for i in range(3)],'gtk-final']):
    image=b'\x89PNG\r\n\x1a\nSYNTHETIC-NOT-A-PIXEL-CLAIM';filename='gui-%02d-'%index+label+'.png';(arm/filename).write_bytes(image)
    client=dict(pid=proof['pid'],id=number+4,appid=appid,title='Arctic Gtk3 diagnostic '+appid,is_visible=True,is_xwayland=False)
    trace.append(dict(event='diagnostic',label=label,clients={proof['client_id']:client},screenshot=dict(path='/tmp/'+filename,sha256=hashlib.sha256(image).hexdigest())))
   raw_trace=''.join(json.dumps(row)+'\n' for row in trace).encode();(arm/'gui-trace.log').write_bytes(raw_trace);dump(arm/'gui-trace-summary.json',dict(bytes=len(raw_trace),omitted_records=0))
   guest_root='/tmp/arctic-native-smoke-fixture-'+name
   isolated=prefix+['HOME='+guest_root+'/home','XDG_CONFIG_HOME='+guest_root+'/config','XDG_DATA_HOME='+guest_root+'/data','XDG_CACHE_HOME='+guest_root+'/cache']
   proofs=[];commands=[]
   for index,args in enumerate((['-M','ctrl','-k','a','-m','ctrl'],[W.TEXT],['-k','Return'])):
    original=['-s','200',*(['-k','Shift_L'] if warm else []),'-s','150',*args];guest_root='/tmp/arctic-native-smoke-fixture-'+name;private='/run/t/arctic-wtype-sentinel'
    if corrected:
     local=arm/('producer-turn-%d'%index);local.mkdir();actual=[private,'--arctic-proof-dir',guest_root+'/producer-turn-'+str(index),'--',*original]
     symbols,_=W.expected(index,warm);identity=dict(schema='arctic-private-input-v1',source_sha256=build['source_pair_sha256'],map_only=False,argv=actual,pid=100+index,uid=1000,gid=1000,monotonic_ns=100,minimum=9,maximum=len(symbols)+9,last_emitted_named_code=len(symbols)+8,sentinel=len(symbols)+9,map_bytes=600,return_codes=producer(index,warm)['identity']['return_codes'])
     raw_map=('xkb_keymap { <ARCTIC_UNUSED> = %d; };'%identity['sentinel']).encode();raw_map+=b' '*(599-len(raw_map))+b'\0';(local/'uploaded-map.xkb').write_bytes(raw_map)
     dump(local/'producer-identity.json',identity);(local/'producer-stat.txt').write_text(str(identity['pid'])+' (wtype) '+' '.join(['0']*19+['123']))
     loaded=['/usr/lib64/libc.so.6','/usr/lib64/ld-linux-x86-64.so.2','/usr/lib64/libwayland-client.so.0.26.0','/usr/lib64/libxkbcommon.so.0.13.1','/usr/lib64/libffi.so.8.2.0']
     (local/'producer-maps.txt').write_text(''.join('1-2 r-xp 0000 00:00 1 '+path+'\n' for path in [private,*loaded]))
     saved=C.load('preflight-proof').producer(local,Path(private),build['source_pair_sha256'],actual,1000);saved['loaded_libraries']=receipt(loaded);saved['locale_mappings']=[];saved['wire']=W.parse(wire(index,warm),index,warm,True,saved);dump(arm/('producer-turn-%d-verified.json'%index),saved);proofs.append(saved)
    else:actual=['/usr/bin/wtype',*original];dump(arm/('original-turn-%d-wire.json'%index),W.parse(wire(index,warm),index,warm,False));proofs.append(None)
    raw=wire(index,warm);(arm/('input-turn-%d.stderr.log'%index)).write_bytes(raw)
    command=dict(argv=isolated+['env','WAYLAND_DEBUG=client',*actual],complete=True,error=None,timed_out=False,only_owned_child_reaped=True,exit_status=0,child_pid=123,monotonic_start_seconds=1,monotonic_end_seconds=2,timeout_seconds=30,stdout_bound_bytes=65536,stderr_bound_bytes=65536,stdout_observed_bytes=0,stdout_observed_sha256=hashlib.sha256(b'').hexdigest(),stderr_observed_bytes=len(raw),stderr_retained_bytes=len(raw),stderr_observed_sha256=hashlib.sha256(raw).hexdigest());commands.append(dict(turn=index,command=command))
   (arm/'input-commands.log').write_text(''.join(json.dumps(row)+'\n' for row in commands))
   natural=C.load('preflight-proof').natural_activation(rows,proof,1000,W.TEXT,corrected,final if corrected else None)
   result=dict(name=name,corrected=corrected,warmup=warm,process=proof,isolated_prefix=isolated,gtk_loaded_libraries=receipt(['/usr/lib64/libgtk-3.so.0.2420.32','/usr/lib64/libgdk-3.so.0.2420.32','/usr/lib64/libxkbcommon.so.0.13.1']),map_observation='exact private uploaded map and compiled endpoint' if corrected else 'original map bytes/endpoint unobserved',activation=natural,wait_elapsed_seconds=0 if corrected else 30,producer_proofs=proofs)
   dump(arm/'arm-report.json',dict(name=name,result=result,error=None,cleanup=dict(only_proved_new_processes_signalled=True,original_copied_configs_unchanged=True,retained_tmp_evidence=guest_root),trace_bytes=len(raw_trace),trace_omitted=0));arms.append(result)
  report=dict(schema='arctic-gtk-input-preflight-v1',status='preflight-passed',arms=arms,errors=[],security=security,release_acceptance=False,native_qualification=False);dump(root/'report.json',report)
  return begin,launcher,report,pins
 def replay(self,root,info):
  begin,launcher,report,pins=info
  class Writer:
   def __init__(self):self.rows=[]
   def write(self,prefix,value):self.rows.append(prefix+json.dumps(value,sort_keys=True))
  writer=Writer();writer.write('ARCTIC-PCMANFM-DIAG-BEGIN ',begin);writer.write('ARCTIC-PCMANFM-DIAG-REPORT ',report);E.export(root,writer);writer.write('ARCTIC-PCMANFM-DIAG-END ',dict(status='diagnostic-collected',error=None,evidence_export_complete=True,release_acceptance=False,native_qualification=False))
  with tempfile.TemporaryDirectory() as tmp:
   target=Path(tmp)/'decoded'
   return C.checked('\n'.join(writer.rows)+'\n','ARCTIC-NATIVE-LAUNCHER-GONE '+json.dumps(launcher)+'\n',target,[],'b'*64,None,None,pins,lambda *args:None)
 def test_full_synthetic_protocol_pairing_positive_original_failure_retained(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);info=self.fixture(root);answer=self.replay(root,info)
   self.assertEqual([a['activation']['status'] for a in answer['report']['arms']],['entry-not-activated','entry-not-activated','natural-entry-activated','natural-entry-activated'])
   self.assertFalse(answer['report']['native_qualification'])
 def test_missing_raw_map_command_capture_or_wrong_elf_rejected(self):
  for case in ('map','command','capture','elf'):
   with self.subTest(case=case),tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);info=self.fixture(root)
    if case=='map':(root/'sentinel-warm/producer-turn-2/uploaded-map.xkb').unlink()
    if case=='command':(root/'original-warm/input-commands.log').write_text('{}\n')
    if case=='capture':(root/'sentinel-cold/gui-04-gtk-final.png').unlink()
    if case=='elf':
     path=root/'sentinel-warm/producer-turn-0-verified.json';value=json.loads(path.read_text());value['loaded_libraries'][0]['sha256']='0'*64;path.write_text(json.dumps(value))
    with self.assertRaises((RuntimeError,FileNotFoundError)):self.replay(root,info)
 def test_false_security_or_changed_wire_rejected(self):
  for case in ('security','wire'):
   with self.subTest(case=case),tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);info=self.fixture(root)
    if case=='security':info[2]['security']['complete']=False;(root/'report.json').write_text(json.dumps(info[2]))
    else:
     path=root/'sentinel-warm/input-turn-2.stderr.log';path.write_bytes(path.read_bytes().replace(b'.key(0, 2, 1)',b'.key(0, 3, 1)'))
    with self.assertRaises(RuntimeError):self.replay(root,info)
 def test_all_six_historical_raw_pairing_false_passes_reject(self):
  for case in ('missingmaps','nonce','exe','im','preload','shell'):
   with self.subTest(case=case),tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);info=self.fixture(root)
    if case=='missingmaps':
     for name,_,_ in C.ARMS:(root/name/'gtk-loaded-maps.txt').unlink()
    elif case=='nonce':
     arm=root/'sentinel-cold';path=arm/'gui-trace.log';rows=[json.loads(row) for row in path.read_text().splitlines()];rows[0]['clients']['7']['appid']='org.arctic.Diagnostic.Entry.aeeeeeeeeeeeeeeee';rows[0]['clients']['7']['title']='Arctic Gtk3 diagnostic org.arctic.Diagnostic.Entry.aeeeeeeeeeeeeeeee';raw=''.join(json.dumps(row)+'\n' for row in rows).encode();path.write_bytes(raw)
     summary=json.loads((arm/'gui-trace-summary.json').read_text());summary['bytes']=len(raw);(arm/'gui-trace-summary.json').write_text(json.dumps(summary));raw_arm=json.loads((arm/'arm-report.json').read_text());raw_arm['trace_bytes']=len(raw);(arm/'arm-report.json').write_text(json.dumps(raw_arm))
    elif case=='exe':
     info[2]['arms'][0]['process'].update(executable='/tmp/unqualified-program',is_xwayland=True);(root/'report.json').write_text(json.dumps(info[2]));arm=root/'original-warm/arm-report.json';value=json.loads(arm.read_text());value['result']=info[2]['arms'][0];arm.write_text(json.dumps(value))
    else:
     path=root/'original-warm/input-commands.log';rows=[json.loads(row) for row in path.read_text().splitlines()];token={'im':'GTK_IM_MODULE=ibus','preload':'LD_PRELOAD=/tmp/unqualified.so','shell':'/usr/bin/sh'}[case];rows[0]['command']['argv'].insert(5,token);path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    with self.assertRaises((RuntimeError,FileNotFoundError)):self.replay(root,info)
 def test_raw_main_stat_library_path_or_prefix_identity_reject(self):
  for case in ('stat','maps','uid','prefix'):
   with self.subTest(case=case),tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);info=self.fixture(root);path=root/'sentinel-warm/gtk-runtime.json';value=json.loads(path.read_text())
    if case=='stat':value['process_stat']=value['process_stat'].replace('123','124')
    elif case=='uid':value['uid']=1001
    elif case=='maps':
     raw=(root/'sentinel-warm/gtk-loaded-maps.txt').read_bytes().replace(b'/usr/bin/python3.14',b'/tmp/elsewhere');(root/'sentinel-warm/gtk-loaded-maps.txt').write_bytes(raw);value['maps_bytes']=len(raw);value['maps_sha256']=hashlib.sha256(raw).hexdigest()
    elif case=='prefix':
     prov=root/'provenance.json';v=json.loads(prov.read_text());v['desktop_prefix'].append('GTK_IM_MODULE=ibus');prov.write_text(json.dumps(v))
    path.write_text(json.dumps(value))
    with self.assertRaises(RuntimeError):self.replay(root,info)
 def test_exact_xkb_extraction_guard_rejects_other_map(self):
  class Writer:
   def __init__(self):self.rows=[]
   def write(self,prefix,value):self.rows.append(prefix+json.dumps(value))
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'in';root.mkdir();(root/'sentinel-warm/producer-turn-0').mkdir(parents=True);(root/'sentinel-warm/producer-turn-0/uploaded-map.xkb').write_bytes(b'map\0');writer=Writer();E.export(root,writer)
   X.extract_preflight(writer.rows,'live',Path(tmp)/'good')
   bad=[row.replace('sentinel-warm/producer-turn-0/uploaded-map.xkb','original-warm/producer-turn-0/uploaded-map.xkb') for row in writer.rows]
   with self.assertRaises(RuntimeError):X.extract_preflight(bad,'live',Path(tmp)/'bad')
if __name__=='__main__':unittest.main(verbosity=2)
