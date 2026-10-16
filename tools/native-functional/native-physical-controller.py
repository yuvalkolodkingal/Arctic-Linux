#!/usr/bin/env python3
"""One-use physical controls and failure-only Native frame observation."""
import hashlib,importlib.util,io,json,os,re,stat,tempfile,time
from pathlib import Path

PREFIX='ARCTIC-NATIVE-PCMANFM-PHYSICAL '
HOST_FRAME_PREFIX='ARCTIC-NATIVE-HOST-FRAME-REQUEST '
MAX_REQUESTS=7
def require(value,message):
 if not value:raise RuntimeError(message)
def strict_json(data):
 def pairs(items):
  result={}
  for key,value in items:require(key not in result,'duplicate physical key');result[key]=value
  return result
 return json.loads(data,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(RuntimeError('nonfinite physical JSON')))
def canonical(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def qmp_return(answer):
 # Same strict response contract to the independently qualified physical Return handler.
 require(type(answer) is dict and set(answer)=={'return'} and type(answer['return']) is dict
         and answer['return']=={}, 'strict physical QMP Return failed; no send-key/focus fallback')
 return answer
def validate(value,stage):
 require(type(value) is dict and set(value)=={'schema','stage','nonce','boot_id','desktop_uid','process','client','action','path','evidence_root','monotonic_ns','client_monotonic_ns','release_acceptance','accessibility_proof'},'physical request schema differs')
 require(value['schema']=='arctic-native-pcmanfm-physical-v1' and value['stage']==stage and stage in ('live','installed')
         and value['release_acceptance'] is False and value['accessibility_proof'] is False
         and isinstance(value['nonce'],str) and re.fullmatch('[0-9a-f]{32}',value['nonce'])
         and isinstance(value['boot_id'],str) and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',value['boot_id'])
         and type(value['desktop_uid']) is int and value['desktop_uid']>0,'physical identity/stage differs')
 proof,client=value['process'],value['client']
 require(type(proof) is dict and all(type(proof.get(k)) is int and proof[k]>1 for k in ('pid','start_ticks'))
         and type(proof.get('uid')) is int and proof['uid']==value['desktop_uid']
         and proof.get('executable')=='/usr/bin/pcmanfm' and proof.get('is_xwayland') is False
         and isinstance(proof.get('client_id'),str) and proof['client_id'].isdigit()
         and isinstance(proof.get('executable_sha256'),str) and re.fullmatch('[0-9a-f]{64}',proof['executable_sha256']), 'owned native PCManFM proof differs')
 require(type(client) is dict and type(client.get('pid')) is int and client['pid']==proof['pid']
         and type(client.get('id')) is int and str(client['id'])==proof['client_id']
         and client.get('is_focused') is True and client.get('is_visible') is True and client.get('is_xwayland') is False
         and isinstance(client.get('appid'),str) and client['appid']=='pcmanfm'
         and isinstance(client.get('title'),str) and 0<len(client['title'])<=1024
         and isinstance(client.get('foreign_toplevel_id'),str) and 0<len(client['foreign_toplevel_id'])<=128,'current physical focus/client differs')
 require(all(type(value[k]) is int and value[k]>0 for k in ('monotonic_ns','client_monotonic_ns'))
         and 0<=value['monotonic_ns']-value['client_monotonic_ns']<=1_000_000_000,'physical observation timing differs')
 root=value['evidence_root'];require(isinstance(root,str) and re.fullmatch('/tmp/arctic-native-smoke-[a-zA-Z0-9_-]+',root),'physical fixture root differs')
 require(value['action'] in ('navigate','f4','open-first'),'physical action is not allowlisted')
 if value['action']=='navigate':
  path=value['path'];require(isinstance(path,str) and len(path)<=128 and re.fullmatch(re.escape(root)+r'/(?:files with spaces|archive file opener|media file opener)',path),'physical navigation path differs')
 else:require(value['path'] is None,'unexpected physical path')
 return value
# BEGIN HOST_FRAME_CONTROLLER
class HostFrameController:
 """Capture one failure-only selected QEMU head while the guest frame is held."""
 def __init__(self,vm,out,stage):
  self.vm,self.output,self.stage=vm,Path(out),stage;self.handled=False
  self.native_source=self.output/'data/native_smoke.py'
  self.context=self.output/'data/taskbar-context.json'
  self.display_receipt=self.output/('taskbar-display-'+('install' if stage=='live' else 'boot')+'.json')
 @staticmethod
 def digest(data):return hashlib.sha256(data).hexdigest()
 @staticmethod
 def error_code(error):
  if isinstance(error,json.JSONDecodeError):return 'json-error'
  if isinstance(error,(FileNotFoundError,PermissionError,OSError)):return 'filesystem-error'
  if isinstance(error,(ValueError,TypeError,KeyError,RuntimeError)):return 'value-error'
  return 'other-error'
 def module(self):
  require(self.native_source.is_file() and not self.native_source.is_symlink()
   and self.native_source.stat().st_size<=512*1024,'host frame native source differs')
  context=strict_json(self.context.read_text());source=self.native_source.read_bytes()
  require(context.get('schema')=='arctic-taskbar-context-v1'
   and context.get('native_sha256')==self.digest(source),'host frame native source/context differs')
  spec=importlib.util.spec_from_file_location('arctic_host_frame_native',self.native_source)
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  return module,self.digest(source)
 @staticmethod
 def request(value,stage):
  required={'schema','stage','nonce','boot_id','player','monitor','client_geometry',
   'client_pixel_crop','expected_palette','expected_rgb_sha256','primary_screenshot_sha256',
   'primary_oracle_status','playback_paused','playback_time_seconds','graphics_offload',
   'hold_seconds','release_acceptance'}
  require(type(value) is dict and set(value)==required
   and value['schema']=='arctic-native-host-frame-request-v1' and value['stage']==stage
   and value['primary_oracle_status']=='unmatched' and value['playback_paused'] is True
   and value['hold_seconds']==20 and value['release_acceptance'] is False
   and re.fullmatch(r'[0-9a-f]{32}',value['nonce'])
   and re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',value['boot_id'])
   and all(re.fullmatch(r'[0-9a-f]{64}',value[key]) for key in
    ('expected_rgb_sha256','primary_screenshot_sha256'))
   and type(value['playback_time_seconds']) in (int,float)
   and not isinstance(value['playback_time_seconds'],bool)
   and 0<=value['playback_time_seconds']<=2,'host frame request envelope differs')
  player=value['player']
  require(type(player) is dict and set(player)=={'client_id','pid','start_ticks','executable','executable_sha256','is_xwayland'}
   and re.fullmatch(r'[0-9]+',player['client_id']) and type(player['pid']) is int and player['pid']>1
   and type(player['start_ticks']) is int and player['start_ticks']>0
   and player['executable']=='/usr/bin/celluloid' and player['is_xwayland'] is False
   and re.fullmatch(r'[0-9a-f]{64}',player['executable_sha256']),'host frame player identity differs')
  monitor=value['monitor'];geometry=value['client_geometry'];crop=value['client_pixel_crop']
  require(type(monitor) is dict and set(monitor)=={'name','x','y','width','height','scale','is_hdr'}
   and re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',monitor['name'])
   and all(type(monitor[key]) is int and not isinstance(monitor[key],bool)
    for key in ('x','y','width','height','scale'))
   and monitor['width']==1280 and monitor['height']==720 and monitor['scale']==1
   and monitor['is_hdr'] is False,'host frame monitor differs')
  require(type(geometry) is dict and set(geometry)=={'x','y','width','height'}
   and type(crop) is dict and set(crop)=={'x','y','width','height'}
   and all(type(item[key]) is int and not isinstance(item[key],bool)
    for item in (geometry,crop) for key in ('x','y','width','height'))
   and geometry==dict(x=monitor['x'],y=monitor['y'],width=monitor['width'],height=monitor['height'])
   and crop==dict(x=0,y=0,width=monitor['width'],height=monitor['height']),
   'host frame client/crop geometry differs')
  palette=value['expected_palette']
  require(type(palette) is list and len(palette)==16
   and all(type(color) is list and len(color)==3
    and all(type(channel) is int and 0<=channel<=255 for channel in color) for color in palette),
   'host frame palette differs')
  offload=value['graphics_offload']
  require(type(offload) is dict and set(offload)=={'schema','key','effective_value','settings_backend','private_config_process_bound'}
   and offload['schema']=='io.github.celluloid-player.Celluloid'
   and offload['key']=='graphics-offload-enable' and type(offload['effective_value']) is bool
   and offload['settings_backend']=='keyfile' and offload['private_config_process_bound'] is True,
   'host frame graphics offload readback differs')
  return value
 def head(self,monitor):
  proof=strict_json(self.display_receipt.read_text())
  require(type(proof) is dict and proof.get('schema')=='arctic-qemu-taskbar-display-v1'
   and proof.get('status')=='uiinfo_applied_pending_guest_two_output_evidence'
   and proof.get('qemu_pid')==self.vm.proc.pid and proof.get('qemu_uid')==os.geteuid()
   and proof.get('gpu_id')=='arctic_taskbar_gpu' and proof.get('display_backend')=='dbus',
   'host frame display ownership differs')
  rows=[row for row in proof.get('heads',[]) if type(row) is dict
   and (row.get('xoff'),row.get('yoff'),row.get('width'),row.get('height'))==
    (monitor['x'],monitor['y'],monitor['width'],monitor['height'])]
  require(len(rows)==1 and type(rows[0].get('head')) is int and rows[0]['head'] in (0,1),
   'host frame monitor/head binding differs')
  return rows[0]['head']
 def write(self,name,data):
  require(type(data) is bytes and len(data)<=4*1024*1024,'host frame output exceeds bound')
  descriptor=os.open(self.output/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
  with os.fdopen(descriptor,'wb') as stream:stream.write(data)
 def capture(self,request):
  from PIL import Image
  module,source_sha=self.module();head=self.head(request['monitor'])
  private=Path(tempfile.mkdtemp(prefix='arctic-native-host-frame-',dir='/tmp'));raw=None
  try:
   info=private.lstat();require(stat.S_ISDIR(info.st_mode) and info.st_uid==os.geteuid()
    and stat.S_IMODE(info.st_mode)==0o700,'host frame private capture directory differs')
   raw=private/('native-host-frame-'+request['stage']+'-'+request['nonce']+'.png')
   require(not raw.exists() and not raw.is_symlink(),'host frame temporary path reused')
   answer=self.vm.cmd('screendump',filename=str(raw),format='png',device='arctic_taskbar_gpu',head=head)
   require(type(answer) is dict and set(answer)=={'return'} and answer['return']=={}
    and raw.is_file() and not raw.is_symlink() and 8<=raw.stat().st_size<=4*1024*1024,
    'host frame QMP capture differs')
   with Image.open(raw) as image:
    require(image.size==(request['monitor']['width'],request['monitor']['height']),
     'host frame physical dimensions differ')
    crop=request['client_pixel_crop'];x,y,w,h=[crop[key] for key in ('x','y','width','height')]
    selected=image.crop((x,y,x+w,y+h)).convert('RGB');pixels=selected.tobytes()
    output=io.BytesIO();selected.save(output,format='PNG',optimize=True);png=output.getvalue()
   reference=bytearray(160*120*3)
   for row in range(4):
    for column in range(4):
     color=bytes(request['expected_palette'][row*4+column])
     for line in range(row*30,(row+1)*30):
      start=(line*160+column*40)*3;reference[start:start+40*3]=color*40
   oracle=module.evaluate_reference_rgb(pixels,w,h,bytes(reference))
   image_name='native-host-celluloid-'+request['stage']+'.png';self.write(image_name,png)
   comparison='host-matched-guest-unmatched' if oracle.get('status')=='matched' else 'host-and-guest-unmatched'
   return dict(status='captured',request=request,
    capture=dict(path=image_name,bytes=len(png),sha256=self.digest(png),device='arctic_taskbar_gpu',
     head=head,physical_size=[request['monitor']['width'],request['monitor']['height']],exported_crop=[x,y,w,h]),
    oracle=oracle,comparison=comparison,
    interpretation=('guest-screencopy-divergence-observed' if comparison=='host-matched-guest-unmatched'
     else 'vm-display-presentation-failure-observed'),same_paused_player_hold=request['hold_seconds'],
    native_oracle_source_sha256=source_sha,identical_palette_oracle=True,
    release_acceptance=False,product_change_authorized=False)
  finally:
   if raw is not None:
    try:raw.unlink()
    except FileNotFoundError:pass
   try:private.rmdir()
   except OSError:pass
 def poll(self,serial):
  if self.handled:return False
  request=None;rows=[]
  try:
   require(type(serial) is str and len(serial.encode())<=128*1024*1024,'host frame serial scope differs')
   rows=[line[len(HOST_FRAME_PREFIX):] for line in serial.splitlines() if line.startswith(HOST_FRAME_PREFIX)]
   require(len(rows)<=1,'duplicate host frame request')
   if not rows:return False
   self.handled=True;request=self.request(strict_json(rows[0]),self.stage);receipt=self.capture(request)
  except BaseException as error:
   if not isinstance(error,Exception):raise
   if not rows:return False
   self.handled=True;receipt=dict(schema='arctic-native-host-frame-v1',stage=self.stage,status='unknown',
    error=self.error_code(error),request=request,release_acceptance=False,product_change_authorized=False)
  else:receipt.update(schema='arctic-native-host-frame-v1',stage=self.stage)
  data=(json.dumps(receipt,sort_keys=True)+'\n').encode();require(len(data)<=128*1024,'host frame receipt exceeds bound')
  try:self.write('native-host-frame-'+self.stage+'.json',data);return True
  except (OSError,ValueError,RuntimeError):return False
# END HOST_FRAME_CONTROLLER
class Controller:
 def __init__(self,vm,out,stage,checker_sha,clock=time.monotonic,sleep=time.sleep,chord_for=None):
  self.vm,self.stage,self.checker_sha,self.clock,self.sleep,self.chord_for=vm,stage,checker_sha,clock,sleep,chord_for
  self.log=Path(out)/('native-physical-'+stage+'.log');require(not self.log.exists(),'physical host log must be unused')
  self.used={};self.started=clock();self.host_frame=HostFrameController(vm,out,stage)
 def record(self,event,**fields):
  now=self.clock();row=dict(event=event,stage=self.stage,monotonic_seconds=now,elapsed_seconds=now-self.started,**fields)
  with self.log.open('a') as stream:stream.write(json.dumps(row,sort_keys=True)+'\n')
 def capture(self,label):
  require(self.vm.alive(),'owned VM died during physical route');path=self.vm.shot(label)
  require(path and Path(path).is_file(),'physical QMP screenshot absent');self.record('capture',name=Path(path).name,sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())
 def press(self,chord,nonce,deadline):
  require(self.vm.alive() and self.clock()<deadline,'physical input deadline/VM exited')
  down=[{'type':'key','data':{'down':True,'key':{'type':'qcode','data':x}}} for x in chord]
  up=[{'type':'key','data':{'down':False,'key':{'type':'qcode','data':x}}} for x in reversed(chord)]
  answer=self.vm.cmd('input-send-event',events=down+up);qmp_return(answer)
  self.record('qmp-key',nonce=nonce,chord=chord,response=answer,exact_press_release=True)
 def poll(self,serial):
  require(isinstance(serial,str) and len(serial.encode())<=128*1024*1024,'native physical serial bound')
  complete,separator,pending=serial.rpartition('\n')
  require(len(pending.encode())<=65536,'physical unfinished line bound')
  self.host_frame.poll(serial)
  lines=complete.splitlines() if separator else [];requests=[strict_json(x[len(PREFIX):]) for x in lines if x.startswith(PREFIX)]
  require(len(requests)<=MAX_REQUESTS and len({r.get('nonce') for r in requests})==len(requests),'duplicate/excess physical request')
  begins=[strict_json(x.split(' ',1)[1]) for x in lines if x.startswith('ARCTIC-NATIVE-RUNNER-BEGIN ')]
  launchers=[strict_json(x.split(' ',1)[1]) for x in lines if x.startswith('ARCTIC-NATIVE-LAUNCHER-GONE ')]
  for raw in requests:
   request=validate(raw,self.stage);nonce=request['nonce'];digest=canonical(request)
   if nonce in self.used:require(self.used[nonce]==digest,'changed consumed request');continue
   require(len(begins)==len(launchers)==1 and begins[0].get('stage')==self.stage
           and begins[0].get('checker_sha256')==self.checker_sha and begins[0].get('release_acceptance') is False,'physical current source begin absent')
   launcher=launchers[0];require(launcher.get('stage')==self.stage and launcher.get('boot_id')==request['boot_id']
           and launcher.get('launcher_sha256')=='e948f2ff9c7273f20b0d42e67cc891e3a3f6e0954dfc1ac3afca2aa7c3d7df4c'
           and launcher.get('owned_launcher_gone') is True and launcher.get('foot',{}).get('uid')==launcher.get('shell',{}).get('uid')==request['desktop_uid']
           and launcher.get('probe',{}).get('uid')==0,'physical same-boot/UID launcher absent')
   require(serial.index('ARCTIC-NATIVE-RUNNER-BEGIN ')<serial.index(PREFIX+json.dumps(raw,sort_keys=True)),'physical request precedes source begin')
   expected=[('navigate','files with spaces'),('f4',None),('open-first',None),('navigate','archive file opener'),('open-first',None),('navigate','media file opener'),('open-first',None)][len(self.used)]
   require(request['action']==expected[0] and request['path']==(request['evidence_root']+'/'+expected[1] if expected[1] else None),
           'physical request action/order differs')
   self.used[nonce]=digest # consume BEFORE any attempt; failure never resends
   received=self.clock();deadline=received+25
   self.record('physical-consumed',request=request,request_sha256=digest,release_acceptance=False,accessibility_proof=False)
   self.capture('native-physical-'+self.stage+'-'+str(len(self.used))+'-before')
   require(self.clock()-received<=2,'physical handling stale before injection')
   if request['action']=='navigate':
    self.press(['ctrl','l'],nonce,deadline);self.sleep(.3);self.press(['ctrl','a'],nonce,deadline);self.sleep(.3)
    require(self.chord_for is not None,'supported ASCII QMP helper unavailable')
    for character in request['path']:self.press(self.chord_for(character),nonce,deadline);self.sleep(.15)
    self.capture('native-physical-'+self.stage+'-'+str(len(self.used))+'-path-before-return')
    self.press(['ret'],nonce,deadline)
   elif request['action']=='f4':self.press(['f4'],nonce,deadline)
   else:self.press(['home'],nonce,deadline);self.sleep(.3);self.press(['ret'],nonce,deadline)
   self.capture('native-physical-'+self.stage+'-'+str(len(self.used))+'-after')
   require(self.clock()<=deadline,'physical delivery/capture exceeded unchanged guest title interval')
   self.record('physical-delivered',nonce=nonce,request_sha256=digest,request=request,accessibility_proof=False,release_acceptance=False)


EDITOR_PREFIX='ARCTIC-NATIVE-EDITOR-PHYSICAL '
def validate_editor(value,stage):
 require(type(value) is dict and set(value)=={'schema','stage','nonce','boot_id','desktop_uid','process','client','action','path','evidence_root','monotonic_ns','client_monotonic_ns','release_acceptance','accessibility_proof'},'editor save request schema differs')
 require(value['schema']=='arctic-native-editor-save-v1' and value['stage']==stage and stage in ('live','installed')
  and value['release_acceptance'] is False and value['accessibility_proof'] is False
  and isinstance(value['nonce'],str) and re.fullmatch('[0-9a-f]{32}',value['nonce'])
  and isinstance(value['boot_id'],str) and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',value['boot_id'])
  and type(value['desktop_uid']) is int and value['desktop_uid']>0,'editor save identity differs')
 p,c=value['process'],value['client'];root=value['evidence_root']
 require(type(p) is dict and all(type(p.get(k)) is int and p[k]>1 for k in ('pid','start_ticks'))
  and type(p.get('uid')) is int and p['uid']==value['desktop_uid'] and p.get('executable')=='/usr/bin/featherpad'
  and p.get('is_xwayland') is False and isinstance(p.get('client_id'),str) and p['client_id'].isdigit()
  and isinstance(p.get('executable_sha256'),str) and re.fullmatch('[0-9a-f]{64}',p['executable_sha256']),'editor save process differs')
 require(isinstance(root,str) and re.fullmatch('/tmp/arctic-native-smoke-[a-zA-Z0-9_-]+',root)
  and value['path']==root+'/files with spaces/editor fixture.txt' and value['action']=='save-editor','editor exact file/action differs')
 require(type(c) is dict and type(c.get('pid')) is int and c['pid']==p['pid'] and type(c.get('id')) is int
  and c['id']>0 and str(c['id'])==p['client_id'] and c.get('is_focused') is True and c.get('is_visible') is True
  and c.get('is_xwayland') is False and c.get('appid')=='featherpad'
  and isinstance(c.get('title'),str) and c['title'].lstrip('*')==value['path']
  and isinstance(c.get('foreign_toplevel_id'),str) and 0<len(c['foreign_toplevel_id'])<=128,'editor exact focus/file differs')
 require(all(type(value[k]) is int and value[k]>0 for k in ('monotonic_ns','client_monotonic_ns'))
  and 0<=value['monotonic_ns']-value['client_monotonic_ns']<=1_000_000_000,'editor fresh observation differs')
 return value
class EditorSaveController(Controller):
 def __init__(self,vm,out,stage,checker_sha,clock=time.monotonic,sleep=time.sleep,chord_for=None):
  self.vm,self.stage,self.checker_sha,self.clock,self.sleep,self.chord_for=vm,stage,checker_sha,clock,sleep,chord_for
  self.log=Path(out)/('native-editor-save-'+stage+'.log');require(not self.log.exists(),'editor save host log must be unused')
  self.used={};self.started=clock()
 def poll(self,serial):
  require(isinstance(serial,str) and len(serial.encode())<=128*1024*1024,'editor serial bound')
  complete,separator,pending=serial.rpartition('\n');require(len(pending.encode())<=65536,'editor unfinished line bound')
  lines=complete.splitlines() if separator else []
  requests=[strict_json(x[len(EDITOR_PREFIX):]) for x in lines if x.startswith(EDITOR_PREFIX)]
  require(len(requests)<=1,'only one editor save request per phase')
  begins=[strict_json(x.split(' ',1)[1]) for x in lines if x.startswith('ARCTIC-NATIVE-RUNNER-BEGIN ')]
  launchers=[strict_json(x.split(' ',1)[1]) for x in lines if x.startswith('ARCTIC-NATIVE-LAUNCHER-GONE ')]
  for raw in requests:
   r=validate_editor(raw,self.stage);nonce=r['nonce'];digest=canonical(r)
   if nonce in self.used:require(self.used[nonce]==digest,'changed consumed editor request');continue
   require(len(begins)==len(launchers)==1 and begins[0].get('stage')==self.stage
    and begins[0].get('checker_sha256')==self.checker_sha and begins[0].get('release_acceptance') is False,'editor source begin absent')
   l=launchers[0];require(l.get('stage')==self.stage and l.get('boot_id')==r['boot_id']
    and l.get('launcher_sha256')=='e948f2ff9c7273f20b0d42e67cc891e3a3f6e0954dfc1ac3afca2aa7c3d7df4c'
    and l.get('owned_launcher_gone') is True and l.get('foot',{}).get('uid')==l.get('shell',{}).get('uid')==r['desktop_uid']
    and l.get('probe',{}).get('uid')==0,'editor same-boot launcher absent')
   require(serial.index('ARCTIC-NATIVE-RUNNER-BEGIN ')<serial.index(EDITOR_PREFIX+json.dumps(raw,sort_keys=True)),'editor request precedes source')
   self.used[nonce]=digest;received=self.clock();deadline=received+25
   self.record('editor-save-consumed',request=r,request_sha256=digest,accessibility_proof=False)
   self.capture('native-editor-save-'+self.stage+'-before')
   require(self.clock()-received<=2,'editor capture stale; no input retry')
   self.press(['ctrl','s'],nonce,deadline)
   self.capture('native-editor-save-'+self.stage+'-after')
   require(self.clock()<=deadline,'editor delivery/capture exceeded bound')
   self.record('editor-save-delivered',request=r,request_sha256=digest,accessibility_proof=False)
