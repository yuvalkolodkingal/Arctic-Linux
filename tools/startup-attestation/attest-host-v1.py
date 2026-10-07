"""Strict decoder only: no VM, shell, network, package or source action."""
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
FOLLOWUP_FILES=('/etc/sddm/wayland-session','/usr/lib/systemd/system/service.d/10-timeout-abort.conf',
    '/etc/sysconfig/sddm','/usr/libexec/livesys/functions','/usr/libexec/livesys/sessions.d/livesys-arctic',
    '/usr/libexec/livesys/livesys-late','/var/lib/livesys/livesys-session-extra',
    '/usr/lib/systemd/profile.d/70-systemd-shell-extra.sh','/usr/lib/systemd/profile.d/80-systemd-osc-context.sh',
    '/etc/locale.conf','/home/liveuser/.i18n','/home/liveuser/.config/bash_completion',
    '/usr/share/bash-completion/bash_completion','/etc/sysconfig/bash-prompt-xterm',
    '/etc/sysconfig/bash-prompt-screen','/etc/sysconfig/bash-prompt-default','/usr/libexec/grepconf.sh','/usr/bin/lesspipe.sh')
FOLLOWUP_TREES=('/home/liveuser/.bashrc.d','/etc/debuginfod')
PROFILE_TARGETS=(
    ('/etc/profile.d/70-systemd-shell-extra.sh','../../usr/lib/systemd/profile.d/70-systemd-shell-extra.sh','/usr/lib/systemd/profile.d/70-systemd-shell-extra.sh'),
    ('/etc/profile.d/80-systemd-osc-context.sh','../../usr/lib/systemd/profile.d/80-systemd-osc-context.sh','/usr/lib/systemd/profile.d/80-systemd-osc-context.sh'))
DYNAMIC_IDS=('bash-env-inherited-startup','bash-conditional-runtime-state','colorls-term-include-eval','debuginfod-recursive-discovery',
             'flatpak-helper-output','nix-environment-dependent-data','helper-runtime-resolution','new-script-semantic-review')
UNIT_ARGV=['systemctl','show','sddm.service','--no-pager','--property=FragmentPath,DropInPaths,ExecStart,ExecStartPre,User,EnvironmentFiles']

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

def followup(report,decoded):
    value=report.get('missing_chain_followup');require(type(value) is dict,'Missing followup proof')
    require(value.get('schema')=='arctic-missing-chain-raw-v1' and value.get('actual_login_shell')=='/bin/bash'
            and report['selected_startup_chain']['shell']=='/bin/bash' and value.get('complete_startup_chain') is False
            and value.get('non_atomic_observations') is True,'Followup meaning/shell differs')
    require(value.get('raw_file_inventory')==sorted(FOLLOWUP_FILES) and value.get('directory_inventory')==sorted(FOLLOWUP_TREES),
            'Followup inventory differs')
    sources={v['path']:v for v in report['source_files']['files']}
    require(all(p in sources for p in FOLLOWUP_FILES),'Missing declared followup source record')
    for path in FOLLOWUP_FILES:
        item=sources[path]
        if item['status']=='absent':require(set(item)=={'path','status'},'Absence record contains prior-present metadata')
        elif item['status'] in ('read-raw','symlink-unread'):
            require(all(type(item.get(k)) is int and 0<=item[k]<2**64 for k in ('device','inode','uid','gid','mode','bytes'))
                    and item['uid']<2**32 and item['gid']<2**32 and item['mode']<=0o7777,'Optional source ownership/stat differs')
            if item['status']=='symlink-unread':require(type(item.get('target')) is str,'Optional source link target type differs')
    proofs=value.get('profile_target_proofs');require(type(proofs) is list and len(proofs)==len(PROFILE_TARGETS),'Profile proof count differs')
    for index,(proof,(node,literal,target)) in enumerate(zip(proofs,PROFILE_TARGETS)):
        require(type(proof) is dict and proof.get('node')==node and proof.get('literal_target')==literal and proof.get('fixed_target')==target,
                'Profile proof node/literal/target differs')
        for key in ('node_before','node_after','target_before','target_after'):
            row=proof.get(key);require(type(row) is list and len(row)==8 and all(type(v) is int and 0<=v<2**64 for v in row),
                                     'Profile stable-stat type/bound differs')
        require(proof['node_before']==proof['node_after'] and proof['target_before']==proof['target_after'],
                'Profile node/target bracket identity differs')
        alias=next((value['fixed_target'] for value in proofs[:index] if value['target_before'][:2]==proof['target_before'][:2]),None)
        require('target_alias_of' in proof and proof['target_alias_of']==alias,'Profile hardlink identity observation differs')
        n=sources.get(node);t=sources[target];ns=proof['node_before'];ts=proof['target_before']
        require(type(n) is dict and n.get('status')=='symlink-unread' and n.get('target')==literal
                and stat.S_ISLNK(ns[4]) and t['status']=='read-raw' and stat.S_ISREG(ts[4]),'Profile node/regular target differs')
        for row,item in ((ns,n),(ts,t)):
            require(all(type(item.get(k)) is int for k in ('device','inode','uid','gid','mode','bytes'))
                    and row[:4]==[item['device'],item['inode'],item['uid'],item['gid']]
                    and stat.S_IMODE(row[4])==item['mode'] and row[5]==item['bytes'] and row[2:4]==[0,0],
                    'Profile actual source/stat/owner differs')
        require(not t['mode']&0o22 and proof.get('target_sha256')==t['sha256'],'Profile target mode/hash differs')
    trees=report['source_files'].get('trees');require(type(trees) is list and all(type(v) is dict and type(v.get('path')) is str for v in trees),
                                                   'Followup directory inventory type differs')
    require(len({v['path'] for v in trees})==len(trees),'Duplicate source directory')
    for tree in trees:
        if tree.get('status')=='absent':require(set(tree)=={'path','status'},'Absent directory contains prior-present children/stat metadata')
    for path in FOLLOWUP_TREES:
        rows=[v for v in trees if v['path']==path];require(len(rows)==1,'Missing followup directory')
        tree=rows[0];require(tree.get('status') in ('absent','listed'),'Followup directory status differs')
        if tree['status']=='listed':
            require(all(type(tree.get(k)) is int and 0<=tree[k]<2**64 for k in ('uid','gid','mode','device','inode','mtime_ns','ctime_ns'))
                    and tree['uid']<2**32 and tree['gid']<2**32 and tree['mode']<=0o7777,'Directory ownership/stat differs')
            children=tree.get('children');require(type(children) is list and len(children)<=512
                    and all(type(v) is str and v and v not in ('.','..') and '/' not in v and '\x00' not in v for v in children)
                    and children==sorted(set(children)) and all(path+'/'+v in sources for v in children),'Directory children/source proof differs')
    before=value.get('effective_unit_before');after=value.get('effective_unit_after')
    require(before=='sddm-effective-unit.txt' and after=='sddm-effective-unit-after.txt' and before in decoded and after in decoded
            and decoded[before]==decoded[after] and value.get('effective_unit_sha256')==sha(decoded[before]),'Effective unit before/after bytes differ')
    lines=decoded[before].decode('utf-8').splitlines()
    for expected in ('FragmentPath=/usr/lib/systemd/system/sddm.service','DropInPaths=/usr/lib/systemd/system/service.d/10-timeout-abort.conf',
                     'EnvironmentFiles=/etc/sysconfig/sddm (ignore_errors=yes)'):
        require(lines.count(expected)==1 and sum(v.startswith(expected.split('=',1)[0]+'=') for v in lines)==1,'Effective unit fixed paths differ')
    for key,path in (('sddm-effective-unit',before),('sddm-effective-unit-after',after)):
        command=report.get('commands',{}).get(key)
        require(type(command) is dict and command.get('argv')==UNIT_ARGV and command.get('path')==path
                and type(command.get('bytes')) is int and command['bytes']==len(decoded[path]) and command.get('sha256')==sha(decoded[path]),
                'Effective unit command/payload proof differs')
    blockers=value.get('unsupported_dynamic_chain');require(type(blockers) is list and [v.get('id') for v in blockers if type(v) is dict]==list(DYNAMIC_IDS)
            and all(v.get('status')=='unreviewed' and type(v.get('reason')) is str and 0<len(v['reason'])<=512 for v in blockers),
            'Explicit dynamic-chain blockers differ')

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
    require(report.get('schema')=='arctic-startup-attestation-v1' and report.get('status')=='exact-startup-attestation-collected'
            and report.get('release_acceptance') is False and report.get('safe_visual_gate')=='open'
            and report.get('startup_hook_executed') is False and report.get('renderer')=='unobserved'
            and report.get('active_scanout_pixels')=='unavailable','Attestation meaning differs')
    require(report.get('candidate_source')=='fe4742c8b9414c45f0bcbb0a4191f116383c60d1'
            and report.get('intended_iso_sha256')=='84c9c88ebcbcaf69dbabf56509a9ceb2db58e5dc41d7bae12093edba12f60718'
            and report.get('mango_executable_sha256')=='ce11ee5cfd24b0393c933e22f7365910d498772e186bb078b9d63a2b42313866','Candidate/ISO/process identity differs')
    chain=report.get('selected_startup_chain')
    require(type(chain) is dict and chain.get('independently_reviewed_complete_chain') is False
            and chain.get('unresolved_links_are_startup_binding_blockers') is True
            and chain.get('shell') in ('/usr/bin/fish','/bin/fish','/usr/bin/bash','/bin/bash')
            and chain.get('actual_SHELL')==chain['shell'] and chain.get('home')=='/home/liveuser'
            and type(chain.get('uid')) is int and chain['uid']>0,'Selected shell identity/unreviewed scope differs')
    require(type(report.get('startup_binding_blockers')) is list and
            dict(path='semantic-startup-chain',status='unreviewed') in report['startup_binding_blockers'],
            'Semantic startup-chain blocker missing')
    require(type(report.get('begin_monotonic_ns')) is int and type(report.get('end_monotonic_ns')) is int
            and 0<=report['begin_monotonic_ns']<=report['end_monotonic_ns'] and report['end_monotonic_ns']-report['begin_monotonic_ns']<=110*10**9,'Attestation interval invalid')
    boot=report.get('boot_id');require(type(boot) is str and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',boot),'Invalid boot identity')
    for label,key in [('attest-before','security_before'),('attest-after','security_after')]:
        value=report[key];audit=dict(line.split(None,1) for line in value['audit_status'].splitlines() if len(line.split(None,1))==2)
        require(value['selinux']=='Enforcing' and value['avc_records']==[] and audit.get('enabled') in ('1','2') and audit.get('lost')=='0','Security/AVC/lost audit failure')
        path='system-journal-'+label+'.log';require(path in decoded and type(value.get('journal_retained_bytes')) is int
                and len(decoded[path])==value['journal_retained_bytes'] and sha(decoded[path])==value['journal_retained_sha256'],'Journal proof differs')
        rows=[parse(line) for line in decoded[path].splitlines() if line]
        require(rows and all(type(v) is dict and v.get('_BOOT_ID')==boot.replace('-','') and 'MESSAGE' in v for v in rows),'Journal type/boot differs')
        require(type(value.get('journal_total_bytes')) is int and value['journal_total_bytes']==value['journal_retained_bytes']
                and type(value.get('current_boot_journal_records')) is int and value['current_boot_journal_records']==len(rows),
                'Journal truncated/count differs')
        require(not any(v.get('_TRANSPORT') in ('kernel','audit') and re.search(r'\bavc:\s*denied\b|\btype=(?:USER_)?AVC\b',str(v['MESSAGE']),re.I) for v in rows),'Raw trusted journal denial')
    sources=report['source_files'];require(type(sources.get('files')) is list and len(sources['files'])<=512,'Source count bound differs')
    paths=set();raw_total=0
    for value in sources['files']:
        path=value['path'];require(type(path) is str and path.startswith('/') and '..' not in Path(path).parts and path not in paths,'Unsafe/duplicate source path');paths.add(path)
        require(value.get('status') in ('read-raw','absent','symlink-unread','unavailable'),'Unknown source status')
        if value['status']=='read-raw':
            require(all(type(value.get(k)) is int and 0<=value[k]<2**32 for k in ('uid','gid','mode','bytes')) and value['mode']<=0o7777 and value['bytes']<=65536,'Source owner/mode/size type differs')
            raw=base64.b64decode(value['base64'],validate=True);require(len(raw)==value['bytes'] and sha(raw)==value['sha256'],'Raw source bytes differ');raw_total+=len(raw)
    require(raw_total<=2*1024*1024 and type(sources.get('raw_source_bytes')) is int and raw_total==sources['raw_source_bytes'],'Raw source aggregate differs')
    followup(report,decoded)
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
