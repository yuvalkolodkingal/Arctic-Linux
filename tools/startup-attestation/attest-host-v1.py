"""Strict decoder only: no VM, shell, package, startup or network action."""
import base64
import hashlib
import json
from pathlib import Path
import re
import stat
import zlib
MAX_FILE=4*1024*1024
MAX_TOTAL=16*1024*1024
MAX_SERIAL=24*1024*1024
HERE=Path(__file__).resolve().parent
def require(value,message):
    if not value:raise RuntimeError(message)

def sha(data):return hashlib.sha256(data).hexdigest()

def object_pairs(pairs):
    value={}
    for k,v in pairs:
        require(k not in value,'Duplicate JSON key');value[k]=v
    return value

def parse(value):return json.loads(value,object_pairs_hook=object_pairs,parse_constant=lambda value:(_ for _ in ()).throw(RuntimeError('Nonfinite JSON constant')))

def protocol(serial,live=False):
    require(type(serial) is str and len(serial.encode())<=MAX_SERIAL,'Attestation serial exceeds bound')
    lines=serial.split('\n');tail=lines[-1];prefix='ARCTIC-ATTEST-'
    require(live or not tail or not (tail.startswith(prefix) or prefix.startswith(tail)),
            'Unterminated/ambiguous attestation record')
    values=[];phases=['BEGIN','REPORT','MANIFEST'];position=0;ended=False
    for line in lines[:-1]:
        if not line.startswith('ARCTIC-ATTEST-'):continue
        parts=line[len('ARCTIC-ATTEST-'):].split(' ',1);require(len(parts)==2,'Malformed attestation header')
        name,text=parts;value=parse(text);require(type(value) is dict,'Attestation record must be object')
        if position<len(phases):require(name==phases[position],'Duplicate/reordered/missing attestation phase');position+=1
        else:require(not ended and name in ('CHUNK','END'),'Unexpected/duplicate attestation transport phase');ended=name=='END'
        values.append((name,value))
    return values,ended

def integer(value,lower=0,upper=2**64):
    require(type(value) is int and lower<=value<upper,'Untyped/outside integer bounds')
    return value

def digest(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}',value),'Untyped digest')
    return value

def namespace(value,observer):
    require(type(value) is dict and value.get('observer_pid')==observer and type(value.get('observer_pid')) is int
            and value.get('NSpid')==[observer] and all(type(v) is int for v in value['NSpid']), 'Namespace observer/PID type differs')
    require(type(value.get('pid_namespace')) is str and re.fullmatch(r'pid:\[[1-9][0-9]*\]',value['pid_namespace'])
            and value.get('pid_namespace')==value.get('init_pid_namespace'),'Actual PID namespace ambiguity')
    raw=base64.b64decode(value['status_base64'],validate=True);mount=base64.b64decode(value['mountinfo_base64'],validate=True)
    require(len(raw)<=65536 and len(mount)<=65536 and sha(raw)==digest(value['status_sha256'])
            and sha(mount)==digest(value['mountinfo_sha256']),'Namespace raw bytes/hash/bounds differ')
    fields={}
    for row in raw.splitlines():
        if b':' in row:
            key,content=row.split(b':',1);require(key not in fields,'Duplicate actual process status');fields[key]=content.strip()
    require(fields.get(b'NSpid')==str(observer).encode() and fields.get(b'Pid')==str(observer).encode()
            and fields.get(b'Uid')==fields.get(b'Gid')==b'0\t0\t0\t0','Raw procfs root/PID namespace differs')
    entries=[]
    for row in mount.decode().splitlines():
        left,sep,right=row.partition(' - ');parts=left.split();tail=right.split()
        if len(parts)>=6 and parts[4]=='/proc':
            require(sep and len(tail)>=3 and tail[0]=='proc' and parts[3]=='/','Raw procfs mount differs')
            entries.append(dict(mount_id=parts[0],parent_id=parts[1],device=parts[2],root=parts[3],target=parts[4],filesystem=tail[0]))
    require(len(entries)==1 and entries[0]==value.get('proc_mount'),'Raw procfs mount identity missing/ambiguous')

def security(report,decoded,label,key):
    value=report[key];require(type(value) is dict,'Security object type differs')
    audit=dict(line.split(None,1) for line in value['audit_status'].splitlines() if len(line.split(None,1))==2)
    require(value['selinux']=='Enforcing' and value['avc_records']==[] and audit.get('enabled') in ('1','2') and audit.get('lost')=='0','Security/AVC/lost audit failure')
    path='system-journal-'+label+'.log';raw=decoded[path]
    require(len(raw)==integer(value['journal_retained_bytes']) and sha(raw)==digest(value['journal_retained_sha256']),'Journal proof differs')
    rows=[parse(line) for line in raw.splitlines() if line]
    require(rows and all(type(v) is dict and v.get('_BOOT_ID')==report['boot_id'].replace('-','') and 'MESSAGE' in v for v in rows),'Journal type/boot differs')
    require(integer(value['journal_total_bytes'])==len(raw) and integer(value['current_boot_journal_records'])==len(rows),'Journal truncated/count differs')
    require(not any(v.get('_TRANSPORT') in ('kernel','audit') and re.search(r'\bavc:\s*denied\b|\btype=(?:USER_)?AVC\b',str(v['MESSAGE']),re.I) for v in rows),'Raw trusted journal denial')

def validate_report(report,decoded):
    require(set(decoded)=={'report.json','namespace-context.json','system-journal-prereq-before.log','system-journal-prereq-after.log'},'Runtime evidence set differs')
    require(len(decoded['report.json'])+len(decoded['namespace-context.json'])<=262144,'AddedJSON exceeds cap')
    require(report.get('schema')=='arctic-runtime-prerequisite-report-v1' and report.get('status')=='runtime-prerequisite-collected','Runtime meaning differs')
    for key in ('complete_startup_chain','exact_startup_target_bound','actual_final_startup_handoff_qualified','startup_hook_executed',
                'Mango_launched_or_restarted','Mango_d','release_acceptance'):
        require(report.get(key) is False,'Unqualified runtime/startup claim')
    require(report.get('safe_visual_gate')=='open' and report.get('renderer')=='unobserved' and report.get('active_scanout_pixels')=='unavailable'
            and report.get('normal_environment_unchanged') is True,'Visual/renderer/normal session meaning differs')
    require(report.get('candidate_source')=='fe4742c8b9414c45f0bcbb0a4191f116383c60d1'
            and report.get('intended_iso_sha256')=='84c9c88ebcbcaf69dbabf56509a9ceb2db58e5dc41d7bae12093edba12f60718'
            and report.get('mango_executable_sha256')=='ce11ee5cfd24b0393c933e22f7365910d498772e186bb078b9d63a2b42313866','Candidate/ISO identity differs')
    boot=report.get('boot_id');require(type(boot) is str and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',boot),'Boot ID differs')
    require(type(report.get('cmdline')) is str and {'rd.live.image','nomodeset'}<=set(report['cmdline'].split()),'Safe boot mode differs')
    begin,ab,ae,end=[integer(report.get(k)) for k in ('begin_monotonic_ns','added_probe_begin_ns','added_probe_end_ns','end_monotonic_ns')]
    require(begin<=ab<=ae<=end and end-begin<=110*10**9 and ae-ab<=60*10**9,'Runtime clock/deadline differs')
    require(integer(report.get('own_fixture_attempts'))==11 and integer(report.get('own_fixture_processes'))==16,'Owned fixture bound differs')
    selected=report.get('selected_user');require(type(selected) is dict and set(selected)=={'uid','gid','shell','home'} and
            integer(selected['uid'])==integer(selected['gid'])==1000 and selected['shell']=='/bin/bash' and selected['home']=='/home/liveuser','Actual selected user differs')
    observer=integer(report.get('observer_pid'),1,2**32);digest(report.get('normal_environment_sha256'))
    context=parse(decoded['namespace-context.json']);require(type(context) is dict and context.get('non_atomic') is True
            and sha(decoded['namespace-context.json'])==digest(report.get('namespace_context_sha256')),'Namespace output differs')
    for name in ('before','after'):namespace(context[name],observer)
    for k in ('observer_pid','pid_namespace','init_pid_namespace','NSpid','proc_mount'):
        require(context['before'][k]==context['after'][k],'Namespace brackets changed')
    expected={'/usr/libexec/sddm-helper':'93ab003b0453179eb1f0e6a7a51a20ee322af4992300d095403c5f728b7a68e4',
              '/usr/bin/bash':'379c1bfc53d08815975c647ad7da5d19d8e8a8566ce8097c50231c8b116e5e7b',
              '/usr/bin/python3.14':'0d64bd6d66d68dac91cdadafc46e22d4f09f22bdc997aaae870f42865b024a3e'}
    providers=report.get('providers');require(type(providers) is list and len(providers)==3 and [v.get('path') for v in providers]==list(expected),'Fixed provider set/order differs')
    for row in providers:
        require(type(row) is dict and integer(row['uid'])==integer(row['gid'])==0 and row['sha256']==expected[row['path']]
                and 0<integer(row['bytes'])<=2097152 and integer(row['mode'])<=0o7777 and not row['mode']&0o6022,'Provider ownership/hash/bounds differ')
        stable=row.get('stable_identity');require(type(stable) is list and len(stable)==8,'Provider stat shape differs')
        for value in stable:integer(value)
        require(stable[2:4]==[0,0] and stat.S_ISREG(stable[4]) and stat.S_IMODE(stable[4])==row['mode'] and stable[5]==row['bytes'],'Provider stable stat differs')
    require(report['CD_pins_sha256']==sha((HERE/'runtime-probe-pins-v1.json').read_bytes()),'ReadonlyCD graph differs')
    processes=report.get('processes');require(type(processes) is dict and set(processes)=={'mango','quickshell'},'Normal process set differs')
    normal=[]
    for name,row in processes.items():
        normal.append(integer(row.get('pid'),1,2**32));require(integer(row.get('uid'))==1000 and integer(row.get('start_ticks'),1)>0,'Normal process identity differs')
        digest(row.get('executable_sha256'))
    require(len(set(normal))==2 and observer not in normal and processes['mango'].get('cmdline')==['mango']
            and processes['mango']['executable_sha256']==report['mango_executable_sha256'],'Normal Mango/process identity differs')
    credential=report.get('credential_control');require(type(credential) is dict and credential.get('status')=='owned-fixture-credential-primitive-collected'
            and credential.get('provider_sha256')==expected['/usr/bin/python3.14'] and credential.get('raw_sha256')=='28fc7f0fe284eabe5c08b3e9422ac51d9bd18372c859faf5b51a6f2f6d1a44b8','Credential primitive bytes/provider differ')
    direct=integer(credential.get('direct_pid'),1,2**32);integer(credential.get('direct_start_ticks'),1)
    require(direct not in normal+[observer] and integer(credential.get('selected_uid'))==integer(credential.get('selected_gid'))==1000,'Owned sender collides/credentials differ')
    for key in ('pidfd_before_release','owned_child_reaped','all_owned_FDs_closed'):require(credential.get(key) is True,'Owned sender lifecycle unproven')
    for key in ('actual_guest','Mango_or_renderer_qualification','release_acceptance'):require(credential.get(key) is False,'Primitive self-scope changed')
    identity=credential.get('owned_pidfd_identity');require(type(identity) is dict and set(identity)=={'pid','kernel_fdinfo_bound','signal0_permission_checked'}
            and integer(identity['pid'])==direct and identity['kernel_fdinfo_bound'] is True and identity['signal0_permission_checked'] is True,'Pidfd binding differs')
    rows=credential.get('rows');require(type(rows) is list and len(rows)==2,'Credential range count differs')
    for index,(row,start,stop,text) in enumerate(zip(rows,(0,12),(12,25),(b'OTHER-CHILD\n',b'OWNED-DIRECT\n'))):
        require(type(row) is dict and integer(row['begin'])==start and integer(row['end'])==stop and row['sha256']==sha(text)
                and integer(row['uid'])==integer(row['gid'])==1000 and ab<=integer(row['received_monotonic_ns'])<=ae,'Credential bytes/types/time differ')
        pid=integer(row['pid'],1,2**32)
        require(pid not in normal+[observer] and ((index==0 and pid!=direct and row['origin']=='other-sender-unqualified') or
                (index==1 and pid==direct and row['origin']=='owned-launch-process')),'Direct/inherited sender attribution differs')
    seals=report.get('seal_controls');require(type(seals) is list and [v.get('label') for v in seals]==['valid','duplicate','unterminated','unsealed','wrong-owner'],'Seal case set differs')
    for index,row in enumerate(seals):
        require(set(row)=={'label','status','FD_closed','error'} and row['FD_closed'] is True
                and ((index==0 and row['status']=='accepted-exact' and row['error'] is None) or
                (index>0 and row['status']=='rejected-expected' and type(row['error']) is str and 0<len(row['error'])<=256)),'Seal outcome/lifecycle differs')
    env=report.get('environment_controls');require(type(env) is list and [v.get('label') for v in env]==['ordinary','locale','bytes','quoted-final-bash'],'Environment case set differs')
    for index,row in enumerate(env):
        require(row.get('byte_exact') is True and row.get('actual_session_environment') is False and 0<integer(row.get('bytes'))<=1048576
                and digest(row['direct_sha256'])==digest(row['handoff_sha256']) and row.get('boundary')==('owned-quoted-final-Bash-only' if index==3 else 'direct-native-only'),'Synthetic environment outcome/scope differs')
    argv=report.get('quoted_argument_control');require(type(argv) is dict and argv.get('status')=='owned-quoted-argv-byte-exact','Quoted argv outcome differs')
    cwd=argv.get('cwd');require(type(cwd) is str and re.fullmatch('/tmp/arctic-owned-runtime-[A-Za-z0-9_-]{1,64}',cwd),'Owned fixture cwd scope differs')
    arguments=['space value','line1\nline2','literal;$(touch '+cwd+'/must-not-be-created);`echo literal`']
    command=['/usr/bin/bash','--noprofile','--norc','-c','exec "$@"','owned-final-exec-fixture','/run/arctic-safe/argv-native-v1',*arguments]
    raw=b''.join(v.encode()+b'\0' for v in arguments)
    require(argv.get('arguments')==arguments and argv.get('bash_argv')==command and argv.get('HOME')==cwd and argv.get('BASH_ENV')==cwd+'/never-source'
            and argv.get('absent_BASH_ENV') is True and argv.get('marker_absent') is True and argv.get('actual_session_argument_fidelity') is False
            and argv.get('carrier_argument_forwarding') is False and argv.get('direct_sha256')==argv.get('quoted_sha256')==sha(raw)
            and integer(argv.get('bytes'))==len(raw),'Quoted synthetic argv/cwd/environment proof differs')
    security(report,decoded,'prereq-before','security_before');security(report,decoded,'prereq-after','security_after')

def extract(serial,target,collector_sha):
    values,ended=protocol(serial);require(ended,'Attestation END missing')
    require(type(collector_sha) is str and re.fullmatch('[0-9a-f]{64}',collector_sha),'Invalid collector pin')
    require(values[0][1]==dict(collector_sha256=collector_sha,candidate_source='fe4742c8b9414c45f0bcbb0a4191f116383c60d1',release_acceptance=False)
            and values[0][1].get('release_acceptance') is False,'Collector/candidate pin differs')
    report,manifest,end=values[1][1],values[2][1],values[-1][1]
    require(end==dict(status='attestation-collected-unreviewed',error=None,release_acceptance=False)
            and end.get('release_acceptance') is False,'Attestation failed; preserve raw failure')
    require(manifest.get('schema')=='arctic-startup-attestation-files-v1' and manifest.get('encoding')=='zlib+base64'
            and type(manifest.get('files')) is list and 1<=len(manifest['files'])<=32,'Invalid manifest')
    decoded={};total=0;chunks=[v for n,v in values if n=='CHUNK']
    for item in manifest['files']:
        path=item['path'];require(type(path) is str and re.fullmatch(r'[a-z0-9][a-z0-9.-]*\.(json|log|txt)',path)
                and path not in decoded and path!='serial-report.json','Unsafe/duplicate/reserved evidence path')
        require(type(item['bytes']) is int and 0<=item['bytes']<=MAX_FILE and type(item['compressed_bytes']) is int
                and 0<item['compressed_bytes']<=MAX_FILE+65536 and type(item['chunks']) is int and 1<=item['chunks']<=3600,'Invalid payload bounds')
        parts=[v for v in chunks if v.get('path')==path]
        require(len(parts)==item['chunks'] and all(type(v.get('index')) is int for v in parts)
                and [v['index'] for v in parts]==list(range(item['chunks'])),'Missing/duplicate/reordered chunks')
        packed=b''.join(base64.b64decode(v['data'],validate=True) for v in parts);require(len(packed)==item['compressed_bytes'],'Compressed bytes differ')
        d=zlib.decompressobj();data=d.decompress(packed,MAX_FILE+1)
        require(d.eof and not d.unused_data and not d.unconsumed_tail and len(data)==item['bytes'] and sha(data)==item['sha256'],'Payload integrity/bound mismatch')
        decoded[path]=data;total+=len(data);require(total<=MAX_TOTAL,'Total evidence exceeds bound')
    require(all(v.get('path') in decoded for v in chunks) and type(manifest.get('bytes')) is int and total==manifest['bytes'],'Extra chunks/total mismatch')
    require('report.json' in decoded and parse(decoded['report.json'])==report,'Retained report differs')
    validate_report(report,decoded)
    destination=Path(target);require(destination.is_absolute() and destination==destination.resolve() and not destination.exists(),'Unsafe/colliding destination')
    destination.mkdir(mode=0o700)
    for name,data in decoded.items():
        with (destination/name).open('xb') as file:file.write(data)
    return dict(status='attestation-collected-requires-independent-review',files={k:dict(bytes=len(v),sha256=sha(v)) for k,v in decoded.items()},
                exact_startup_target_bound=False,release_acceptance=False,safe_visual_gate='open',report=report)

def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('serial',type=Path);p.add_argument('destination',type=Path);p.add_argument('--collector-sha256',required=True);args=p.parse_args()
    require(not args.serial.is_symlink() and args.serial.stat().st_size<=MAX_SERIAL,'Unsafe serial')
    value=extract(args.serial.read_text(),args.destination,args.collector_sha256);print(json.dumps(value,sort_keys=True))

if __name__=='__main__':main()
