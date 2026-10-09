#!/usr/bin/env python3
"""One-use physical PCManFM controls; no AT-SPI/focus/delivery fallback."""
import hashlib,json,re,time
from pathlib import Path

PREFIX='ARCTIC-NATIVE-PCMANFM-PHYSICAL '
MAX_REQUESTS=5
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
  path=value['path'];require(isinstance(path,str) and len(path)<=128 and re.fullmatch(re.escape(root)+r'/(?:files with spaces|archive file opener)',path),'physical navigation path differs')
 else:require(value['path'] is None,'unexpected physical path')
 return value
class Controller:
 def __init__(self,vm,out,stage,checker_sha,clock=time.monotonic,sleep=time.sleep,chord_for=None):
  self.vm,self.stage,self.checker_sha,self.clock,self.sleep,self.chord_for=vm,stage,checker_sha,clock,sleep,chord_for
  self.log=Path(out)/('native-physical-'+stage+'.log');require(not self.log.exists(),'physical host log must be unused')
  self.used={};self.started=clock()
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
   expected=[('navigate','files with spaces'),('f4',None),('open-first',None),('navigate','archive file opener'),('open-first',None)][len(self.used)]
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
