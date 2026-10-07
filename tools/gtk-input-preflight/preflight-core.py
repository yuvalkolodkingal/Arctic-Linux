#!/usr/bin/env python3
"""Finite disposable-live-GTK producer preflight; never native qualification."""
import hashlib,importlib.util,json,os,pwd,re,shutil,signal,stat,sys,tempfile,time,uuid
from pathlib import Path
HERE=Path(__file__).resolve().parent
TEXT='Arctic isolated GTK3 entry'
ARMS=[('original-warm',False,True),('original-cold',False,False),
      ('sentinel-warm',True,True),('sentinel-cold',True,False)]
def require(value,message):
 if not value:raise RuntimeError(message)
def load(name,path,digest):
 require(path.is_file() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest()==digest,'frozen dependency differs: '+path.name)
 spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
def library_proof(paths,N):
 result=[]
 allowlist=json.loads((HERE/'candidate-input-libraries.json').read_text())
 require(allowlist['schema']=='arctic-candidate-input-elf-v1' and allowlist['candidate_iso_sha256']=='84c9c88ebcbcaf69dbabf56509a9ceb2db58e5dc41d7bae12093edba12f60718','candidate library receipts differ')
 for text in paths:
  path=Path(text);info=path.lstat()
  require(stat.S_ISREG(info.st_mode) and path.read_bytes()[:4]==b'\x7fELF','loaded regular ELF unavailable')
  digest=N.digest(path)
  require(text in allowlist['files'],'unlisted actual input ELF path')
  expected=allowlist['files'][text]
  require(digest==expected['sha256'] and stat.S_IMODE(info.st_mode)==expected['mode'] and info.st_uid==info.st_gid==0,'actual input ELF differs from signed candidate header')
  status,owner,err=N.execute(['rpm','-qf','--qf','%{NEVRA}\t%{EPOCHNUM}\n',str(path)],timeout=15)
  require(status==0 and len(owner.splitlines())==1 and err=='' and owner==expected['rpm_nevra']+'\t'+str(expected['epoch']),'actual library owner/NEVRA/epoch differs from candidate')
  owner,epoch=owner.split('\t');epoch=int(epoch)
  verify=N.execute(['rpm','-V',owner],timeout=15)
  require(verify==(0,'',''),'actual loaded library RPM verification differs')
  require(N.digest(path)==digest and path.lstat().st_ino==info.st_ino,'loaded library changed while proving')
  result.append(dict(path=text,sha256=digest,bytes=info.st_size,owner=owner,epoch=epoch,verification=verify))
 return result
def mapping_proof(paths,N):
 elf=[];locale=[]
 for text in paths:
  path=Path(text);info=path.lstat()
  require(stat.S_ISREG(info.st_mode) and info.st_uid==info.st_gid==0,'mapped root file unavailable')
  with path.open('rb') as stream:magic=stream.read(4)
  if magic==b'\x7fELF':elf.append(text);continue
  require((text=='/usr/lib/locale/locale-archive' or re.fullmatch(r'/usr/lib/locale/en_US\.utf8/LC_CTYPE',text))
          and stat.S_IMODE(info.st_mode)==0o644 and info.st_size<=256*1024*1024,'unknown mapped data refused')
  before=N.digest(path)
  status,owner,err=N.execute(['rpm','-qf','--qf','%{NEVRA}\n',text],timeout=15,allow_failure=True)
  require(status==0 and err=='' and owner in ('glibc-all-langpacks-2.43-9.fc44.x86_64','glibc-langpack-en-2.43-9.fc44.x86_64'),
          'mapped locale origin unavailable/different')
  status,header,err=N.execute(['rpm','-q','--qf','[%{FILENAMES}\t%{FILEDIGESTS}\t%{FILEMODES}\n]',owner],timeout=15)
  matches=[line for line in header.splitlines() if line.split('\t',1)[0]==text]
  require(len(matches)==1 and err=='' and N.digest(path)==before and path.lstat().st_ino==info.st_ino,'locale header/identity changed')
  final=path.lstat();require((final.st_dev,final.st_ino,final.st_size,final.st_mode,final.st_uid,final.st_gid)==(info.st_dev,info.st_ino,info.st_size,info.st_mode,info.st_uid,info.st_gid),'locale stat identity changed')
  locale.append(dict(path=text,sha256=before,bytes=info.st_size,uid=info.st_uid,gid=info.st_gid,mode=stat.S_IMODE(info.st_mode),inode=info.st_ino,device=info.st_dev,
      rpm_nevra=owner,file_header=matches[0],signed_content_allowlist=False,
      scope='actual read-only locale bytes/header origin recorded; no signed locale-content equivalence or unobserved input assumption'))
 return library_proof(elf,N),locale
def rows(root,P):
 require(not (root/'gtk-control-error.json').exists(),'GTK telemetry collector failed')
 data=P.regular(root/'gtk-events.log',2*1024*1024)
 require(data.endswith(b'\n'),'GTK log incomplete framing')
 result=[P.strict_json(row) for row in data[:-1].split(b'\n')]
 require(len(result)<=4096,'GTK event record bound exceeded');return result
def gtk_identity(smoke,proof,appid,P):
 client=smoke.alive(proof)
 require(client['appid']==appid and client['title']=='Arctic Gtk3 diagnostic '+appid
         and client['is_xwayland'] is False,'owned native GTK nonce client differs')
 mapped=[r for r in rows(smoke.root,P) if r.get('event')=='mapped']
 require(len(mapped)==1 and mapped[0]['appid']==appid and mapped[0]['program_name']==appid
         and mapped[0]['backend']=='GdkWaylandDisplay' and mapped[0]['pid']==proof['pid']
         and mapped[0]['start_ticks']==proof['start_ticks'] and mapped[0]['uid']==smoke.uid,'mapped GTK identity differs')
 return client
def gtk_runtime(smoke,proof,N):
 before=N.identity(proof['pid'],smoke.uid)
 require(before=={key:proof[key] for key in ('pid','start_ticks','executable')} and proof['is_xwayland'] is False,
         'GTK native process identity differs before maps')
 process_stat=Path('/proc/%d/stat'%proof['pid']).read_text();require(len(process_stat.encode())<=4096,'GTK process stat bound')
 executable=Path(before['executable']);info=executable.lstat()
 with executable.open('rb') as stream:magic=stream.read(4)
 require(str(executable)=='/usr/bin/python3.14' and stat.S_ISREG(info.st_mode) and magic==b'\x7fELF'
         and info.st_uid==info.st_gid==0 and stat.S_IMODE(info.st_mode)==0o755,'GTK native main ELF path/stat differs')
 executable_hash=N.digest(executable);require(executable_hash==proof['executable_sha256'],'GTK main ELF changed after fresh-window proof')
 status,owner,err=N.execute(['rpm','-qf','--qf','%{NEVRA}\t%{EPOCHNUM}\n',str(executable)],timeout=15)
 require(status==0 and err=='' and len(owner.splitlines())==1 and owner.startswith('python3-') and owner.endswith('\t0'),'GTK current main RPM origin differs')
 verification=N.execute(['rpm','-V',owner.split('\t')[0]],timeout=15);require(verification==(0,'',''),'GTK current main RPM verification differs')
 raw=Path('/proc/%d/maps'%proof['pid']).read_bytes();require(len(raw)<=262144,'GTK maps bound')
 smoke.write('gtk-loaded-maps.txt',raw)
 paths=[]
 for line in raw.decode('utf-8','strict').splitlines():
  fields=line.split(maxsplit=5)
  if len(fields)==6 and fields[5].startswith('/') and re.search(r'/lib(?:gtk-3|gdk-3|xkbcommon)\.so',fields[5]):
   require(not fields[5].endswith(' (deleted)'),'GTK deleted library');paths.append(fields[5])
 paths=sorted(set(paths));require(len(paths)==3,'actual GTK/GDK/XKB loaded libraries unavailable')
 value=library_proof(paths,N)
 after=N.identity(proof['pid'],smoke.uid)
 require(after==before and N.digest(executable)==executable_hash and executable.lstat().st_ino==info.st_ino,'GTK identity changed during maps proof')
 smoke.write('gtk-runtime.json',(json.dumps(dict(before=before,after=after,uid=smoke.uid,process_stat=process_stat,
     maps_bytes=len(raw),maps_sha256=hashlib.sha256(raw).hexdigest(),main_executable=dict(path=str(executable),
      sha256=executable_hash,bytes=info.st_size,uid=info.st_uid,gid=info.st_gid,mode=stat.S_IMODE(info.st_mode),inode=info.st_ino,device=info.st_dev,
      owner_epoch=owner,verification=verification,signed_content_allowlist=False,
      scope='current owned native ELF/clean current RPM proof; no additional signed Python receipt claim')),indent=2)+'\n').encode())
 return value
def turn(smoke,proof,argv,warm,corrected,index,metadata,N,P):
 client=smoke.alive(proof)
 answer=json.loads(smoke.cmd(['mmsg','dispatch','focusid','client,'+proof['client_id']])[1])
 require(answer.get('success') is True,'owned focus dispatch failed')
 smoke.wait(lambda:smoke.alive(proof).get('is_focused') is True,10)
 original=['-s','200',*(['-k','Shift_L'] if warm else []),'-s','150',*argv]
 if corrected:
  target=smoke.root/('producer-turn-%d'%index);target.mkdir(mode=0o700);os.chown(target,smoke.uid,smoke.user.pw_gid)
  binary=HERE/'arctic-wtype-sentinel'
  require(binary.is_file() and not binary.is_symlink() and N.digest(binary)==metadata['binary']['sha256']
          and stat.S_IMODE(binary.stat().st_mode)==0o755,'explicit private ELF differs')
  actual=[str(binary),'--arctic-proof-dir',str(target),'--',*original]
 else:actual=['/usr/bin/wtype',*original]
 smoke.trace('input-preflight-turn-before',proof=proof,original_argv=original,actual_argv=actual,
             corrected=corrected,client=client)
 collector=load('bounded_input_stream',HERE/'input-collector.py',json.loads((HERE/'runtime-pins.json').read_text())['input-collector.py'])
 wire=load('strict_wire_input',HERE/'wire-input.py',json.loads((HERE/'runtime-pins.json').read_text())['wire-input.py'])
 meta=smoke.root/('input-turn-%d.json'%index);stdout=bytearray()
 command=collector.run_input_stream(smoke.prefix+['env','WAYLAND_DEBUG=client',*actual],stdout.extend,meta,timeout=30,limit=65536,stderr_limit=65536)
 require(stdout==b'','successful producer wrote unexpected stdout')
 raw=meta.with_suffix('.stderr.log').read_bytes()
 smoke.steps.append(dict(argv=actual,observation='per-process WAYLAND_DEBUG=client',command=command))
 smoke.alive(proof)
 if corrected:
  data=P.producer(target,binary,metadata['source_pair_sha256'],actual,smoke.uid)
  require(data['identity']['map_only'] is False,'runtime upload proof was offline')
  paths=[p for p in data['mapped_files'] if p!=str(binary)]
  data['loaded_libraries'],data['locale_mappings']=mapping_proof(paths,N)
  require(N.digest(binary)==metadata['binary']['sha256'],'private ELF changed after input')
  data['wire']=wire.parse(raw,index,warm,True,data)
  smoke.write('producer-turn-%d-verified.json'%index,(json.dumps(data,indent=2)+'\n').encode())
  return data
 smoke.write('original-turn-%d-wire.json'%index,(json.dumps(wire.parse(raw,index,warm,False),indent=2)+'\n').encode())
 return None
def arm(prefix,aggregate,name,corrected,warm,metadata,N,P):
 smoke=N.Smoke(prefix,'live');cleanup=None;result=None;error=None
 try:
  smoke.setup()
  appid='org.arctic.Diagnostic.Entry.a'+uuid.uuid4().hex[:16]
  proof=smoke.fresh_window(lambda:smoke.launch(['python3',str(HERE/'gtk-entry-control.py'),str(smoke.root),appid]),
                           'python3',re.escape(appid),native=True)
  gtk_identity(smoke,proof,appid,P);libraries=gtk_runtime(smoke,proof,N)
  smoke.diagnostic('gtk-before-input')
  proofs=[]
  for index,argv in enumerate((['-M','ctrl','-k','a','-m','ctrl'],[TEXT],['-k','Return'])):
   proofs.append(turn(smoke,proof,argv,warm,corrected,index,metadata,N,P))
   gtk_identity(smoke,proof,appid,P);smoke.diagnostic('gtk-after-turn-'+str(index))
  started=time.monotonic()
  def observed():
   smoke.alive(proof)
   return next((r for r in rows(smoke.root,P) if r.get('event')=='activate' and r.get('text')==TEXT),None)
  try:smoke.wait(observed,30,label='isolated Gtk3 entry activation')
  except RuntimeError as exc:
   require(str(exc)=='bounded functional gate timed out: isolated Gtk3 entry activation','activation collector failed: '+str(exc))
  elapsed=time.monotonic()-started
  data=P.natural_activation(rows(smoke.root,P),proof,smoke.uid,TEXT,corrected,
                           proofs[-1]['identity']['return_codes'] if corrected else None)
  smoke.diagnostic('gtk-final')
  result=dict(name=name,corrected=corrected,warmup=warm,process=proof,isolated_prefix=smoke.prefix,gtk_loaded_libraries=libraries,
              activation=data,wait_elapsed_seconds=elapsed,producer_proofs=proofs,
              map_observation='exact private uploaded map and compiled endpoint' if corrected else 'original map bytes/endpoint unobserved',
              scope='corrected helper functional input only; original causal diagnosis and PCManFM/native/installed qualification open')
 except BaseException as exc:error=type(exc).__name__+': '+str(exc)
 finally:
  try:cleanup=smoke.cleanup()
  except BaseException as exc:error=(error+'; ' if error else '')+'cleanup: '+str(exc)
  try:
   require(smoke.trace_omitted==0,'mandatory trace evidence omitted')
   files=list(smoke.root.rglob('*'));require(len(files)<=100 and all(not p.is_symlink() for p in files),'arm preservation file bound')
   target=aggregate/name;require(not target.exists(),'unused arm evidence target required');target.mkdir()
   omitted=[];commands=[]
   for path in sorted(smoke.root.rglob('*')):
    require(not path.is_symlink(),'owned arm symlink refused')
    if not path.is_file():continue
    relative=path.relative_to(smoke.root)
    if re.fullmatch(r'input-turn-[012]\.json',relative.as_posix()):
     raw=path.read_bytes();require(len(raw)<=65536,'input command metadata cap')
     commands.append(dict(turn=int(relative.name[11]),command=P.strict_json(raw)))
     omitted.append(dict(path=relative.as_posix(),bytes=len(raw),sha256=N.digest(path),scope='fully retained in input-commands.log framing'))
     continue
    include=path.suffix.lower() in ('.json','.png','.log','.txt','.tsv') or bool(re.fullmatch(r'producer-turn-[012]/uploaded-map\.xkb',relative.as_posix()))
    if not include:
     omitted.append(dict(path=relative.as_posix(),bytes=path.stat().st_size,sha256=N.digest(path),scope='copied isolated config/cache data; not a required proof'))
     continue
    require(path.stat().st_size<=4*1024*1024,'arm evidence file cap')
    destination=target/relative;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,destination)
   framed=b''.join((json.dumps(row,sort_keys=True)+'\n').encode() for row in commands)
   require(len(framed)<=65536,'consolidated input command framing cap')
   (target/'input-commands.log').write_bytes(framed)
   (target/'arm-report.json').write_text(json.dumps(dict(name=name,result=result,error=error,cleanup=cleanup,
      trace_bytes=smoke.trace_bytes,trace_omitted=smoke.trace_omitted,excluded_nonproof_files=omitted),indent=2)+'\n')
  except BaseException as exc:error=(error+'; ' if error else '')+'preservation: '+str(exc)
 if error:raise RuntimeError(name+': '+error)
 return result
def run(prefix,aggregate,N,P,S,metadata):
 # Called only after the exact same-image launcher/source guard. No transport, boot or VM action here.
 results=[];errors=[];security=None;security_value=None
 try:
  security=S.SecurityInterval(N,aggregate/'security-interval')
  for name,corrected,warm in ARMS:
   results.append(arm(prefix,aggregate,name,corrected,warm,metadata,N,P));security.state()
 except BaseException as exc:errors.append(type(exc).__name__+': '+str(exc))
 finally:
  if security is not None:
   try:security_value=security.finish()
   except BaseException as exc:security_value=security.failed(str(exc));errors.append('security: '+str(exc))
  else:security_value=dict(complete=False,error='security initialization failed')
 if not (security_value.get('complete') is True and security_value.get('selinux')=='Enforcing'
         and security_value.get('audit')=={'enabled':1,'lost':0}
         and all(type(security_value['audit'][k]) is int for k in ('enabled','lost'))
         and type(security_value.get('observed_new_avcs')) is int and security_value['observed_new_avcs']==0):
  errors.append('security interval not qualified')
 if security_value.get('complete') is True:
  if len(security_value['states'])!=6:errors.append('six complete raw security states required')
  for state in security_value['states']:
   if state['selinux']!='Enforcing' or state['audit']!={'enabled':1,'lost':0} or any(type(state['audit'][k]) is not int for k in ('enabled','lost')):
    errors.append('inter-arm security state differs')
 corrected=[a for a in results if a['corrected']]
 try:
  members=[p for p in aggregate.rglob('*') if p.is_file()]
  require(len(members)<=128 and all(not p.is_symlink() and p.stat().st_size<=4*1024*1024 for p in aggregate.rglob('*'))
          and sum(p.stat().st_size for p in members)<=16*1024*1024,'unchanged evidence count/file/total cap exceeded')
 except BaseException as exc:errors.append('evidence preservation: '+str(exc))
 passed=len(corrected)==2 and all(a['activation']['status']=='natural-entry-activated' for a in corrected)
 return dict(schema='arctic-gtk-input-preflight-v1',status='preflight-passed' if passed and not errors else 'failed',
             arms=results,errors=errors,security=security_value,release_acceptance=False,native_qualification=False,
             remaining='full native live/install/first-boot qualification conditional on passing finite preflight')
def main():
 require(Path(__file__).resolve()==Path('/run/t/guest-check.py') and sys.argv==[sys.argv[0]],'exact disposable guest entry/no CLI required')
 pins=json.loads((HERE/'runtime-pins.json').read_text())
 N=load('preflight_native',HERE/'native_smoke.py',pins['native_smoke.py']);N.guest_guard('live',True)
 P=load('preflight_proof',HERE/'preflight-proof.py',pins['preflight-proof.py'])
 S=load('preflight_security',HERE/'security-collector.py',pins['security-collector.py'])
 L=load('preflight_launcher',HERE/'native-launcher.py',pins['native-launcher.py'])
 for name,digest in pins.items():require(N.digest(HERE/name)==digest,'runtime source differs: '+name)
 barrier=L.verify_barrier('live',pins['native-launcher.py'])
 prefix=N.discover_desktop();uid=pwd.getpwnam(prefix[2]).pw_uid;require(barrier['foot']['uid']==uid,'launcher UID differs')
 original_identity=library_proof([str(Path('/usr/bin/wtype'))],N)
 root=Path(tempfile.mkdtemp(prefix='arctic-gtk-input-preflight-',dir='/tmp'))
 (root/'original-wtype-identity.json').write_text(json.dumps(original_identity,indent=2)+'\n')
 metadata=json.loads((HERE/'build-payload-pins.json').read_text())
 signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('unchanged600-second guest bound')))
 signal.setitimer(signal.ITIMER_REAL,600)
 try:result=run(prefix,root,N,P,S,metadata)
 finally:signal.setitimer(signal.ITIMER_REAL,0)
 require(library_proof([str(Path('/usr/bin/wtype'))],N)==original_identity,'original wtype changed')
 (root/'report.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(dict(evidence_root=str(root),status=result['status'],release_acceptance=False)))
 return 0 if result['status']=='preflight-passed' else 1
if __name__=='__main__':raise SystemExit(main())
