#!/usr/bin/env python3
"""Pair exact transported wire/producer/GTK/security proofs; never native acceptance."""
import hashlib,importlib.util,json,math,re
from pathlib import Path
HERE=Path(__file__).resolve().parent
ARMS=[('original-warm',False,True),('original-cold',False,False),('sentinel-warm',True,True),('sentinel-cold',True,False)]
def require(value,message):
 if not value:raise RuntimeError(message)
def load(name):
 spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'));mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
def libraries(values,expected_paths,allowlist):
 require(isinstance(values,list) and len(values)==len(expected_paths),'complete library receipt set required')
 require({v['path'] for v in values}==set(expected_paths),'library path set differs')
 for row in values:
  expected=allowlist['files'][row['path']]
  require(row['sha256']==expected['sha256'] and row['owner']==expected['rpm_nevra']
          and type(row.get('epoch')) is int and row['epoch']==expected['epoch'] and isinstance(row['verification'],list) and len(row['verification'])==3 and type(row['verification'][0]) is int and row['verification']==[0,'',''] and type(row['bytes']) is int and row['bytes']>0,'loaded signed candidate library differs')
def desktop_prefix(value,user,uid,home):
 require(isinstance(value,list) and value[:5]==['runuser','-u',user,'--','env'] and len(value)<=24
         and all(isinstance(x,str) and 0<len(x.encode())<=4096 and '\0' not in x and '\n' not in x and '\r' not in x for x in value),
         'exact bounded desktop prefix unavailable')
 required=['HOME='+home,'XDG_RUNTIME_DIR=/run/user/'+str(uid)]
 require(value[5:7]==required and Path(home).is_absolute() and home==Path(home).as_posix(),'actual desktop HOME/runtime differs')
 require(len(value)>=11 and re.fullmatch('WAYLAND_DISPLAY=wayland-[0-9]+',value[7]) and value[8]=='DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/%d/bus'%uid
         and value[9]=='XDG_SESSION_TYPE=wayland' and value[10].startswith('MANGO_INSTANCE_SIGNATURE=') and value[10].split('=',1)[1],
         'actual desktop display/bus/Mango signature differs')
 allowed=('PATH','XDG_DATA_DIRS','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','DISPLAY','XAUTHORITY','LANG','XDG_CURRENT_DESKTOP','XDG_SESSION_ID','QT_QPA_PLATFORM','GDK_BACKEND','MANGO_SOCKET')
 fields=[]
 for token in value[11:]:
  require('=' in token,'unexpected desktop executable token')
  key,content=token.split('=',1);require(key in allowed and content and key not in fields,'unapproved/duplicate desktop assignment')
  fields.append(key)
 require('PATH' in fields and 'XDG_DATA_DIRS' in fields and fields==sorted(fields,key=allowed.index),'desktop inherited field order/content differs')
 return value

def input_command(record,raw,actual,user,prefix):
 require(record['complete'] is True and record['error'] is None and record['timed_out'] is False
         and record['only_owned_child_reaped'] is True and type(record['exit_status']) is int and record['exit_status']==0
         and type(record.get('child_pid')) is int and record['child_pid']>1
         and all(type(record.get(k)) in (int,float) and math.isfinite(record[k]) for k in ('monotonic_start_seconds','monotonic_end_seconds'))
         and 0<=record['monotonic_start_seconds']<=record['monotonic_end_seconds']
         and record['timeout_seconds']==30 and record['stdout_bound_bytes']==record['stderr_bound_bytes']==65536,
         'bounded owned input command incomplete')
 require(type(record['stdout_observed_bytes']) is int and record['stdout_observed_bytes']==0
         and record['stdout_observed_sha256']==hashlib.sha256(b'').hexdigest()
         and type(record['stderr_observed_bytes']) is int and record['stderr_observed_bytes']==len(raw)
         and type(record['stderr_retained_bytes']) is int and record['stderr_retained_bytes']==len(raw)
         and record['stderr_observed_sha256']==hashlib.sha256(raw).hexdigest(),'complete raw input stream pairing differs')
 argv=record['argv'];suffix=['env','WAYLAND_DEBUG=client',*actual]
 require(argv==prefix+suffix and all(isinstance(x,str) for x in argv),'exact desktop/isolation/per-process observation command differs')
def checked(data,console,target,events,expected,R,V,expected_runtime,security_check):
 B=load('bulk-channel');P=load('preflight-proof');W=load('wire-input');X=load('extract-preflight')
 rows=data.splitlines();prefixes=['ARCTIC-PCMANFM-DIAG-BEGIN ','ARCTIC-PCMANFM-DIAG-REPORT ','ARCTIC-NATIVE-EVIDENCE-MANIFEST ','ARCTIC-PCMANFM-DIAG-END ']
 def marked(prefix):return [(i,B.strict_json(row[len(prefix):])) for i,row in enumerate(rows) if row.startswith(prefix)]
 marked_rows=[marked(prefix) for prefix in prefixes]
 require(all(len(items)==1 for items in marked_rows),'one complete strict bulk outer frame required')
 (begin,),(report_row,),(manifest,),(end,)=marked_rows
 require(begin[0]<report_row[0]<manifest[0]<end[0] and begin[1]['checker_sha256']==expected
         and begin[1]['schema']=='arctic-gtk-input-preflight-begin-v1' and begin[1]['release_acceptance'] is False
         and begin[1]['native_qualification'] is False,'finite bulk identity/order differs')
 chunks=[i for i,row in enumerate(rows) if row.startswith('ARCTIC-NATIVE-EVIDENCE-CHUNK ')]
 require(all(report_row[0]<i<manifest[0] for i in chunks),'required bulk chunk order differs')
 copied=X.extract_preflight(rows[begin[0]+1:end[0]],'live',target)
 report=report_row[1];require(B.strict_json((target/'report.json').read_bytes())==report,'raw report differs')
 provenance=B.strict_json((target/'provenance.json').read_bytes())
 require(provenance['schema']==begin[1]['schema'] and provenance['checker_sha256']==expected
         and provenance['native_source_sha256']==expected_runtime['native_smoke.py']
         and provenance['runtime_pins']==expected_runtime and provenance['release_acceptance'] is False
         and provenance['native_qualification'] is False and type(provenance['desktop_uid']) is int and provenance['desktop_uid']>0
         and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',provenance['boot_id'])
         and 'rd.live.image' in provenance['cmdline'].split(),'guest boot/source/runtime differs')
 port=provenance['bulk_port']
 require(port['name']==port['sysfs_name']=='org.arctic.diagnostic.bulk' and port['kind']=='character-device'
         and port['named_path']=='/dev/virtio-ports/org.arctic.diagnostic.bulk' and re.fullmatch('/dev/vport[0-9]+p[0-9]+',port['resolved_device'])
         and all(type(port.get(k)) is int and port[k]>=0 for k in ('device_major','device_minor')),'actual guest bulk device proof differs')
 gone=[B.strict_json(row[len('ARCTIC-NATIVE-LAUNCHER-GONE '):]) for row in console.splitlines() if row.startswith('ARCTIC-NATIVE-LAUNCHER-GONE ')]
 require(len(gone)==1 and gone[0]==provenance['launcher'] and gone[0]['owned_launcher_gone'] is True
         and gone[0]['stage']=='live' and gone[0]['boot_id']==provenance['boot_id']
         and gone[0]['launcher_sha256']==expected_runtime['native-launcher.py']
         and gone[0]['foot']['uid']==gone[0]['shell']['uid']==provenance['desktop_uid'] and gone[0]['probe']['uid']==0,
         'actual same-boot owned launcher barrier differs')
 for name in ('foot','shell','probe'):
  item=gone[0][name]
  require(all(type(item.get(k)) is int and item[k]>0 for k in ('pid','start_ticks')) and type(item.get('uid')) is int and item['uid']>=0
          and isinstance(item.get('executable'),str) and re.fullmatch('[0-9a-f]{64}',item['executable_sha256']),'launcher PID/start/ELF proof differs')
 require(gone[0]['foot']['executable']=='/usr/bin/foot' and Path(gone[0]['shell']['executable']).name in {'bash','fish','zsh','dash','sh'},'owned launcher executable differs')
 require(not any(prefix in console for prefix in ('ARCTIC-PCMANFM-PHYSICAL-REQUEST ','ARCTIC-GTK-PHYSICAL-REQUEST '))
         and not any(e.get('event') in ('physical-host-ack','gtk-physical-host-ack') for e in events),'physical app input forbidden')
 require(report['schema']=='arctic-gtk-input-preflight-v1' and report['status'] in ('preflight-passed','failed')
         and report['errors']==[] and report['release_acceptance'] is False and report['native_qualification'] is False,
         'finite collector failed or asserted native/release acceptance')
 require(report['security'].get('complete') is True and report['security'].get('selinux')=='Enforcing'
         and report['security'].get('audit')=={'enabled':1,'lost':0} and type(report['security'].get('observed_new_avcs')) is int
         and report['security']['observed_new_avcs']==0,'complete enforcing security interval required')
 security_check(target,report['security'],provenance['boot_id'])
 metadata=B.strict_json((HERE/'build-payload-pins.json').read_bytes());allowlist=B.strict_json((HERE/'candidate-input-libraries.json').read_bytes())
 libraries(B.strict_json((target/'original-wtype-identity.json').read_bytes()),['/usr/bin/wtype'],allowlist)
 require([a['name'] for a in report['arms']]==[x[0] for x in ARMS],'finite arm order/completeness differs')
 user=provenance['desktop_user'];require(isinstance(user,str) and re.fullmatch('[a-z_][a-z0-9_-]{0,31}',user),'desktop user identity absent')
 prefix=desktop_prefix(provenance['desktop_prefix'],user,provenance['desktop_uid'],provenance['desktop_home'])
 for arm,(name,corrected,warm) in zip(report['arms'],ARMS):
  root=target/name;raw_arm=B.strict_json((root/'arm-report.json').read_bytes())
  require(raw_arm['name']==name and raw_arm['result']==arm and raw_arm['error'] is None
          and raw_arm['cleanup']['only_proved_new_processes_signalled'] is True
          and raw_arm['cleanup']['original_copied_configs_unchanged'] is True
          and type(raw_arm['trace_omitted']) is int and raw_arm['trace_omitted']==0
          and type(raw_arm['trace_bytes']) is int and raw_arm['trace_bytes']==(root/'gui-trace.log').stat().st_size<=2*1024*1024,
          'raw arm/owned cleanup/trace pairing differs')
  proof=arm['process'];uid=provenance['desktop_uid']
  require(all(type(proof.get(k)) is int and proof[k]>1 for k in ('pid','start_ticks')) and proof.get('is_xwayland') is False
          and proof.get('executable')=='/usr/bin/python3.14' and re.fullmatch('[0-9a-f]{64}',proof['executable_sha256']),
          'owned native GTK process/executable/hash differs')
  runtime=B.strict_json(P.regular(root/'gtk-runtime.json',65536));maps=P.regular(root/'gtk-loaded-maps.txt',262144)
  require(maps.endswith(b'\n') and runtime['maps_bytes']==len(maps) and runtime['maps_sha256']==hashlib.sha256(maps).hexdigest()
          and runtime['before']==runtime['after']=={key:proof[key] for key in ('pid','start_ticks','executable')}
          and type(runtime['uid']) is int and runtime['uid']==uid,'raw GTK maps/process pairing differs')
  process_stat=runtime['process_stat'];require(isinstance(process_stat,str) and 0<len(process_stat.encode())<=4096
          and process_stat.split(' ',1)[0]==str(proof['pid']) and ')' in process_stat,'raw GTK stat PID differs')
  require(process_stat[process_stat.rindex(')')+2:].split()[0] not in ('Z','X') and int(process_stat[process_stat.rindex(')')+2:].split()[19])==proof['start_ticks'],'raw GTK start identity differs')
  native=runtime['main_executable'];require(native['path']==proof['executable'] and native['sha256']==proof['executable_sha256']
          and native['uid']==native['gid']==0 and native['mode']==0o755 and native['bytes']>0 and all(type(native.get(k)) is int and native[k]>=0 for k in ('bytes','inode','device','uid','gid','mode'))
          and isinstance(native['verification'],list) and type(native['verification'][0]) is int and native['verification']==[0,'','']
          and isinstance(native['owner_epoch'],str) and re.fullmatch(r'python3-[^\t\r\n]+\t0',native['owner_epoch'])
          and native['signed_content_allowlist'] is False,'current native Python proof differs or signed claim introduced')
  paths=set()
  for line in maps.decode('utf-8','strict').splitlines():
   fields=line.split(maxsplit=5)
   if len(fields)==6 and fields[5].startswith('/'):
    require(not fields[5].endswith(' (deleted)') and '\\' not in fields[5],'raw GTK mapped path unavailable');paths.add(fields[5])
  required_input={'/usr/lib64/libgtk-3.so.0.2420.32','/usr/lib64/libgdk-3.so.0.2420.32','/usr/lib64/libxkbcommon.so.0.13.1'}
  require(proof['executable'] in paths and {path for path in paths if re.search(r'/lib(?:gtk-3|gdk-3|xkbcommon)\.so',path)}==required_input,
          'raw main/input GTK map paths differ from native proof/signed receipts')
  event_bytes=P.regular(root/'gtk-events.log',2*1024*1024);require(event_bytes.endswith(b'\n'),'GTK event EOF differs')
  gtk=[P.strict_json(row) for row in event_bytes[:-1].split(b'\n')];mapped=[row for row in gtk if row.get('event')=='mapped']
  require(len(mapped)==1 and re.fullmatch(r'org\.arctic\.Diagnostic\.Entry\.a[0-9a-f]{16}',mapped[0]['appid'])
          and mapped[0]['appid']==mapped[0]['program_name'] and mapped[0]['backend']=='GdkWaylandDisplay','GTK nonce/backend differs')
  appid=mapped[0]['appid']
  guest_root=Path(raw_arm['cleanup']['retained_tmp_evidence'])
  require(guest_root.parent==Path('/tmp') and guest_root.name.startswith('arctic-native-smoke-') and guest_root.as_posix()==str(guest_root),'exact isolated guest root differs')
  isolated=prefix+['HOME='+str(guest_root/'home'),'XDG_CONFIG_HOME='+str(guest_root/'config'),'XDG_DATA_HOME='+str(guest_root/'data'),'XDG_CACHE_HOME='+str(guest_root/'cache')]
  require(arm['isolated_prefix']==isolated,'recorded isolated arm prefix differs from exact actual desktop prefix')
  trace_summary=B.strict_json((root/'gui-trace-summary.json').read_bytes())
  require(trace_summary['bytes']==raw_arm['trace_bytes'] and type(trace_summary['omitted_records']) is int and trace_summary['omitted_records']==0,
          'final raw trace summary differs')
  trace_data=P.regular(root/'gui-trace.log',2*1024*1024);require(trace_data.endswith(b'\n'),'GUI trace incomplete EOF')
  trace=[B.strict_json(row) for row in trace_data[:-1].split(b'\n')]
  labels=['gtk-before-input',*[('gtk-after-turn-'+str(i)) for i in range(3)],'gtk-final']
  for index,label in enumerate(labels):
   shots=[r for r in trace if r.get('event')=='diagnostic' and r.get('label')==label]
   require(len(shots)==1 and 'collector_error' not in shots[0],'required GUI capture trace missing/failed')
   client=shots[0]['clients'].get(proof['client_id'])
   require(client and type(client.get('pid')) is int and client['pid']==proof['pid'] and type(client.get('id')) is int and str(client['id'])==proof['client_id'] and client.get('is_visible') is True
           and client.get('is_xwayland') is False and client['appid']==appid
           and client['title']=='Arctic Gtk3 diagnostic '+appid,'capture owned native GTK client differs')
   image=P.regular(root/('gui-%02d-'%index+label+'.png'),4*1024*1024)
   require(image.startswith(b'\x89PNG\r\n\x1a\n') and shots[0]['screenshot']['sha256']==hashlib.sha256(image).hexdigest(),
           'required screenshot byte/hash pairing differs')
  require(arm['corrected'] is corrected and arm['warmup'] is warm,'arm producer selection differs')
  proof=arm['process'];uid=provenance['desktop_uid']
  require(all(type(proof.get(k)) is int and proof[k]>1 for k in ('pid','start_ticks')),'owned GTK PID/start absent')
  libraries(arm['gtk_loaded_libraries'],['/usr/lib64/libgtk-3.so.0.2420.32','/usr/lib64/libgdk-3.so.0.2420.32','/usr/lib64/libxkbcommon.so.0.13.1'],allowlist)
  event_bytes=P.regular(root/'gtk-events.log',2*1024*1024);require(event_bytes.endswith(b'\n'),'GTK event EOF differs')
  gtk=[P.strict_json(row) for row in event_bytes[:-1].split(b'\n')]
  mapped=[row for row in gtk if row.get('event')=='mapped']
  require(len(mapped)==1 and re.fullmatch(r'org\.arctic\.Diagnostic\.Entry\.a[0-9a-f]{16}',mapped[0]['appid'])
          and mapped[0]['appid']==mapped[0]['program_name'] and mapped[0]['backend']=='GdkWaylandDisplay','GTK nonce/backend differs')
  command_data=P.regular(root/'input-commands.log',65536)
  require(command_data.endswith(b'\n'),'input command framing EOF differs')
  command_rows=[B.strict_json(row) for row in command_data[:-1].split(b'\n')]
  require(len(command_rows)==3 and all(set(row)=={'turn','command'} and type(row['turn']) is int and row['turn']==index for index,row in enumerate(command_rows)),
          'all three ordered bounded input command records required')
  expected_proofs=[]
  for index,args in enumerate((['-M','ctrl','-k','a','-m','ctrl'],[W.TEXT],['-k','Return'])):
   original=['-s','200',*(['-k','Shift_L'] if warm else []),'-s','150',*args]
   if corrected:
    local=root/('producer-turn-%d'%index)
    guest_root=Path(raw_arm['cleanup']['retained_tmp_evidence'])/('producer-turn-%d'%index)
    require(guest_root.parent.parent==Path('/tmp') and guest_root.parent.name.startswith('arctic-native-smoke-'),'private guest proof root differs')
    actual=['/run/t/arctic-wtype-sentinel','--arctic-proof-dir',str(guest_root),'--',*original]
    producer=P.producer(local,Path(actual[0]),metadata['source_pair_sha256'],actual,uid)
    saved=B.strict_json((root/('producer-turn-%d-verified.json'%index)).read_bytes())
    require(all(saved[k]==v for k,v in producer.items()),'producer raw/stat/map pairing differs')
    elf=[p for p in producer['mapped_files'] if p!=actual[0] and p in allowlist['files']]
    libraries(saved['loaded_libraries'],elf,allowlist)
    unknown=set(producer['mapped_files'])-{actual[0],*elf}
    locales=saved['locale_mappings'];require({v['path'] for v in locales}==unknown,'mapped data hidden or extra')
    for item in locales:
     require((item['path']=='/usr/lib/locale/locale-archive' or item['path']=='/usr/lib/locale/en_US.utf8/LC_CTYPE')
             and item['uid']==item['gid']==0 and item['mode']==0o644 and all(type(item.get(k)) is int and item[k]>=0 for k in ('device','inode')) and type(item['bytes']) is int and 0<=item['bytes']<=256*1024*1024
             and re.fullmatch('[0-9a-f]{64}',item['sha256']) and item['signed_content_allowlist'] is False,'unknown locale mapping or signed-content claim')
   else:actual=['/usr/bin/wtype',*original];producer=None
   raw=P.regular(root/('input-turn-%d.stderr.log'%index),65536)
   command=command_rows[index]['command'];input_command(command,raw,actual,user,isolated)
   wire=W.parse(raw,index,warm,corrected,producer)
   expected_proofs.append(saved if corrected else None)
   saved_wire=saved['wire'] if corrected else B.strict_json((root/('original-turn-%d-wire.json'%index)).read_bytes())
   require(wire==saved_wire,'raw wire parser differs from guest summary')
  require(arm['producer_proofs']==expected_proofs,'reported producer proof array differs from paired raw files')
  natural=P.natural_activation(gtk,proof,uid,W.TEXT,corrected,saved['identity']['return_codes'] if corrected else None)
  require(natural['key']['hardware_keycode']==W.expected(2,warm)[0].index('Return')+9,'GTK Return does not pair with emitted virtual request')
  require(arm['map_observation']==('exact private uploaded map and compiled endpoint' if corrected else 'original map bytes/endpoint unobserved'),'map observation scope differs')
  require(natural==arm['activation'],'raw natural GTK activation differs')
 passed=all(a['activation']['status']=='natural-entry-activated' for a in report['arms'] if a['corrected'])
 require((report['status']=='preflight-passed') is passed,'finite corrected-only outcome differs')
 require(end[1]['status']=='diagnostic-collected' and end[1]['error'] is None
         and end[1]['evidence_export_complete'] is True and end[1]['release_acceptance'] is False
         and end[1]['native_qualification'] is False,'complete bounded export/collector end differs')
 return dict(report=report,provenance=provenance,files=copied,
             scope='corrected helper functional input proof only; original map endpoint/cause unobserved; all native/release gates open')
