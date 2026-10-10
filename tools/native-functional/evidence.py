"""Retained v6 native evidence validators; no VM or dispatch on import."""
import base64
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import wave
import zlib

HERE = Path(__file__).resolve().parent
NATIVE_SOURCE_SHA = '51198d994db37cf4b6df95b25d25e8e7aa83e66fa525968eab37bc2211da9532'
LAUNCHER_SHA = 'e948f2ff9c7273f20b0d42e67cc891e3a3f6e0954dfc1ac3afca2aa7c3d7df4c'
CHECKERS = {'native-functional': ('guest-check-native-v6.py', 'aab4323815e239b5debeccf93c4b73f727cd9ed54715f519b8bb1e99915a1d78')}
MAX_FILE = 4 * 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024
GATES = {'fresh-defaults-and-isolation', 'archive-content-roundtrips', 'actual-role-file-manager-terminal-editor', 'open-codec-content-and-player-state', 'portal-and-accessibility-reachability', 'owned-process-cleanup-config-preservation', 'selinux-and-new-avcs', 'open-codec-lossless-command-decode'}

class R:
    @staticmethod
    def require(value, message):
        if not value:
            raise RuntimeError(message)

    @staticmethod
    def digest(path):
        value = hashlib.sha256()
        with Path(path).open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                value.update(block)
        return value.hexdigest()

    @staticmethod
    def write_json(path, value):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

def records(lines,prefix):
    return [json.loads(line[len(prefix):]) for line in lines if line.startswith(prefix)]

def native_block(serial,stage):
    lines=serial.splitlines()
    starts=[i for i,line in enumerate(lines) if line.startswith('ARCTIC-NATIVE-RUNNER-BEGIN ')]
    ends=[i for i,line in enumerate(lines) if line.startswith('ARCTIC-NATIVE-RUNNER-END ')]
    R.require(len(starts)==len(ends)==1 and starts[0]<ends[0],'Missing/duplicate/reversed native runner block')
    begin=json.loads(lines[starts[0]].split(' ',1)[1]);end=json.loads(lines[ends[0]].split(' ',1)[1])
    R.require(begin['stage']==end['stage']==stage and begin['native_source_sha256']==NATIVE_SOURCE_SHA
              and begin['checker_sha256']==CHECKERS['native-functional'][1]
              and begin['release_acceptance'] is False and end['release_acceptance'] is False,'Native block identity differs')
    return lines[starts[0]+1:ends[0]],begin,end

def extract_evidence(lines,stage,target):
    R.require(not target.exists(),'Native extracted evidence must be unused');target.mkdir(parents=True)
    manifests=records(lines,'ARCTIC-NATIVE-EVIDENCE-MANIFEST ')
    R.require(len(manifests)==1,'Missing/duplicate native evidence manifest')
    manifest=manifests[0]
    R.require(manifest['schema']=='arctic-native-evidence-v1' and manifest['stage']==stage
              and isinstance(manifest['files'],list) and len(manifest['files'])<=128,'Native evidence schema/bounds differ')
    chunks=records(lines,'ARCTIC-NATIVE-EVIDENCE-CHUNK ')
    known=set();total=0;copied={}
    for entry in manifest['files']:
        relative=entry['path'];parts=Path(relative).parts
        R.require(isinstance(relative,str) and relative and not Path(relative).is_absolute()
                  and '..' not in parts and '.' not in parts and relative==Path(relative).as_posix()
                  and relative not in known
                  and relative not in {'transport-manifest.json','serial-native-report.json','serial-native-provenance.json'}
                  and Path(relative).suffix.lower() in ('.json','.png','.log','.txt','.tsv','.rgb'),
                  'Unsafe/duplicate native evidence path')
        known.add(relative)
        R.require(type(entry['bytes']) is int and 0<=entry['bytes']<=MAX_FILE
                  and type(entry['compressed_bytes']) is int and 0<entry['compressed_bytes']<=MAX_FILE+65536
                  and type(entry['chunks']) is int and 1<=entry['chunks']<=172
                  and entry['encoding']=='zlib+base64' and re.fullmatch('[0-9a-f]{64}',entry['sha256']),
                  'Native evidence byte/chunk bound differs')
        selected=[chunk for chunk in chunks if chunk['path']==relative]
        R.require(len(selected)==entry['chunks'] and [chunk['index'] for chunk in selected]==list(range(entry['chunks']))
                  and all(type(chunk['index']) is int for chunk in selected),'Missing/duplicate/reordered chunks')
        compressed=b''.join(base64.b64decode(chunk['data'],validate=True) for chunk in selected)
        R.require(len(compressed)==entry['compressed_bytes'],'Compressed byte count differs')
        decoder=zlib.decompressobj();data=decoder.decompress(compressed,MAX_FILE+1)
        R.require(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail
                  and len(data)==entry['bytes'] and hashlib.sha256(data).hexdigest()==entry['sha256'],
                  'Native evidence content/length/hash differs')
        total+=len(data);R.require(total<=MAX_TOTAL,'Native total evidence bound exceeded')
        output=target/relative;output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(data)
        copied[relative]=dict(bytes=len(data),sha256=entry['sha256'])
    R.require(all(chunk['path'] in known for chunk in chunks),'Unexpected evidence chunk')
    R.require(type(manifest['bytes']) is int and manifest['bytes']==total,'Manifest aggregate bytes differ')
    R.write_json(target/'transport-manifest.json',manifest)
    return copied

def check_native(serial,stage,target):
    lines,begin,end=native_block(serial,stage)
    copied=extract_evidence(lines,stage,target) # Preserve complete files before asserting success.
    reports=records(lines,'ARCTIC-NATIVE-FUNCTIONAL ')
    R.require(len(reports)==1,'Missing/duplicate actual native report')
    report=reports[0];R.write_json(target/'serial-native-report.json',report)
    provenance=records(lines,'ARCTIC-NATIVE-PROVENANCE ')
    R.require(len(provenance)==1,'Missing/duplicate native provenance')
    proof=provenance[0];R.write_json(target/'serial-native-provenance.json',proof)
    R.require(proof['stage']==stage and proof['native_source_sha256']==NATIVE_SOURCE_SHA
              and proof['checker_sha256']==begin['checker_sha256'] and proof['release_acceptance'] is False
              and type(proof['desktop_uid']) is int and proof['desktop_uid']>0
              and re.fullmatch('[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',proof['boot_id']),'Native runtime provenance differs')
    launcher=proof['launcher']
    R.require(launcher['schema']=='arctic-native-launcher-v1' and launcher['stage']==stage
              and launcher['boot_id']==proof['boot_id'] and launcher['launcher_sha256']==LAUNCHER_SHA
              and launcher['owned_launcher_gone'] is True and isinstance(proof['active_desktop_session'],str)
              and bool(proof['active_desktop_session']),'Owned launcher same-boot disappearance proof missing')
    for name in ('shell','foot','probe'):
        item=launcher[name]
        R.require(all(type(item[k]) is int and item[k]>0 for k in ('pid','start_ticks'))
                  and type(item['uid']) is int and item['uid']>=0
                  and re.fullmatch('[0-9a-f]{64}',item['executable_sha256']),'Owned launcher process identity differs')
    R.require(launcher['foot']['uid']==launcher['shell']['uid']==proof['desktop_uid']
              and launcher['foot']['executable']=='/usr/bin/foot'
              and Path(launcher['shell']['executable']).name in {'bash','fish','zsh','dash','sh'}
              and launcher['probe']['uid']==0,'Owned launcher UID/ELF binding differs')
    R.require(('rd.live.image' in proof['cmdline'].split())==(stage=='live'),'Actual native stage command line differs')
    R.require(re.search(r'^\s*\d+\s+\[[^]]+\]',proof['virtual_audio_cards'],re.M),'Guest virtual audio card unobserved')
    if stage=='installed':
        R.require(proof['encrypted_root']['device'].startswith('/dev/mapper/')
                  and proof['encrypted_root']['type']=='LUKS2'
                  and re.search(r'^\s*type:\s+LUKS2\s*$',proof['encrypted_root']['status'],re.M),
                  'Installed root encryption proof is missing')
    R.require(report['schema']=='arctic-native-functional-smoke-v4' and report['stage']==stage
              and report['release_acceptance'] is False and isinstance(report['gates'],list),'Native report identity differs')
    names=[gate['check'] for gate in report['gates']]
    R.require(len(names)==len(set(names)) and set(names)==GATES,'Missing/extra/duplicate native gate')
    R.require('report.json' in copied and json.loads((target/'report.json').read_text())==report,
              'Guest temp report and actual serial report differ')
    R.require(end['status']=='passed' and end['error'] is None and end['evidence_export_complete'] is True
              and report['status']=='limited-smoke-passed' and all(gate['status']=='passed' for gate in report['gates']),
              'Native guard/collector/functional/GUI/cleanup gate failed')
    root=Path(report['evidence_root'])
    transport=json.loads((target/'transport-manifest.json').read_text())
    R.require(root.parent==Path('/tmp') and root.name.startswith('arctic-native-smoke-')
              and transport['evidence_root']==str(root),'Native report/transport evidence root differs')
    byname={gate['check']:gate for gate in report['gates']}
    screenshots=byname['actual-role-file-manager-terminal-editor']['value']['screenshots']+[byname['open-codec-content-and-player-state']['value']['screenshot']]
    visual=byname['open-codec-content-and-player-state']['value']['visual_reference']
    screenshots.append(visual['screenshot'])
    R.require(len(screenshots)==4,'Required native moving/editor/archive/static screenshots missing')
    for shot in screenshots:
        relative=Path(shot['path']).relative_to(root).as_posix()
        R.require(relative in copied and relative.endswith('.png') and shot['sha256']==copied[relative]['sha256'],
                  'Actual native screenshot/report hash differs')
        R.require((target/relative).read_bytes().startswith(b'\x89PNG\r\n\x1a\n'),'Native screenshot is not PNG')
    raw={}
    for key in ('expected_rgb','actual_rgb'):
        relative=Path(visual[key+'_path']).relative_to(root).as_posix()
        R.require(relative in copied and relative.endswith('.rgb') and visual[key+'_sha256']==copied[relative]['sha256'],
                  'Actual visual RGB evidence absent/differs')
        raw[key]=(target/relative).read_bytes()
    spec=importlib.util.spec_from_file_location('native_v4_visual_oracle',HERE/'native_smoke.py')
    native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
    crop=visual['client_pixel_crop']
    result=native.evaluate_reference_rgb(raw['actual_rgb'],crop['width'],crop['height'],raw['expected_rgb'])
    R.require(result==visual['oracle'] and result['status']=='matched','Independent actual RGB visual oracle differs/fails')
    R.require('gui-trace.log' in copied and 'gui-trace-summary.json' in copied and 'final-clients.json' in copied
              and 'visual-oracle.json' in copied and 'moving-player-proof.json' in copied,'Required diagnostic/visual proof files missing')
    R.require(json.loads((target/'visual-oracle.json').read_text())==visual,'Actual visual report/file identity differs')
    check_fullscreen(target,report,proof['desktop_uid'])
    return dict(stage=stage,status='limited-smoke-passed',release_acceptance=False,files=copied,provenance=proof,
                screenshot_review='REQUIRED; no visual pass inferred')

def check_physical(serial,stage,vm,target):
    """Pair literal guest requests with one-use QMP and actual capture receipts."""
    spec=importlib.util.spec_from_file_location('native_physical_checked',HERE/'native-physical-controller.py')
    controller=importlib.util.module_from_spec(spec);spec.loader.exec_module(controller)
    requests=records(serial.splitlines(),controller.PREFIX)
    R.require(len(requests)==5,'Exactly five physical PCManFM requests required')
    host=vm/('native-physical-'+stage+'.log')
    R.require(host.is_file() and not host.is_symlink() and host.stat().st_size<=2*1024*1024,'Physical host receipt missing/unsafe/oversized')
    rows=[controller.strict_json(line) for line in host.read_text().splitlines()]
    R.require(len(rows)<=2000 and all(row['stage']==stage for row in rows),'Physical host receipt bound/stage differs')
    times=[row.get('monotonic_seconds') for row in rows]
    R.require(all(type(t) in (int,float) and math.isfinite(t) and t>=0 for t in times) and times==sorted(times),'Physical host clock malformed/reversed')
    consumed=[row for row in rows if row['event']=='physical-consumed']
    delivered=[row for row in rows if row['event']=='physical-delivered']
    R.require(len(consumed)==len(delivered)==5,'Physical request attempt/delivery count differs')
    trace=(target/'gui-trace.log').read_text().splitlines()
    guest=[controller.strict_json(line)['request'] for line in trace if controller.strict_json(line).get('event')=='physical-request']
    summary=json.loads((target/'gui-trace-summary.json').read_text())
    R.require(guest==requests and summary['omitted_records']==0,'Physical guest trace missing/omitted/differs')
    spec=importlib.util.spec_from_file_location('native_supported_qcode',HERE.parents[1]/'tools/lib/vmtest.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    roots=set();owners=set();nonces=set();expected_actions=['navigate','f4','open-first','navigate','open-first']
    for index,request in enumerate(requests):
        controller.validate(request,stage)
        R.require(request['action']==expected_actions[index] and request['nonce'] not in nonces,'Physical action/order/nonce differs')
        nonces.add(request['nonce']);roots.add(request['evidence_root']);owners.add((request['boot_id'],request['desktop_uid'],request['process']['pid'],request['process']['start_ticks']))
        if request['action']=='navigate':R.require(request['path']==request['evidence_root']+('/files with spaces' if index==0 else '/archive file opener'),'Physical fixture/order differs')
        digest=controller.canonical(request)
        R.require(consumed[index]['request']==delivered[index]['request']==request
                  and consumed[index]['request_sha256']==delivered[index]['request_sha256']==digest
                  and consumed[index]['accessibility_proof'] is delivered[index]['accessibility_proof'] is False,
                  'Physical raw request/host delivery mismatch')
        keyrows=[row for row in rows if row['event']=='qmp-key' and row['nonce']==request['nonce']]
        chords=([['ctrl','l'],['ctrl','a']]+[helper.chord_for(c) for c in request['path']]+[['ret']] if request['action']=='navigate'
                else [['f4']] if request['action']=='f4' else [['home'],['ret']])
        R.require([row['chord'] for row in keyrows]==chords and all(row['exact_press_release'] is True for row in keyrows),'Physical actual key sequence differs')
        for row in keyrows:controller.qmp_return(row['response'])
        R.require(rows.index(consumed[index])<min(rows.index(row) for row in keyrows)<max(rows.index(row) for row in keyrows)+1<=rows.index(delivered[index]),'Physical actual delivery order differs')
    R.require(len(roots)==len(owners)==1 and len([row for row in rows if row['event']=='qmp-key'])==sum(len([r for r in rows if r['event']=='qmp-key' and r['nonce']==n]) for n in nonces),'Physical identity or unknown key differs')
    captures=[row for row in rows if row['event']=='capture']
    R.require(len(captures)==12,'Required physical before/path/after screenshots missing')
    expected_names=[]
    for index,request in enumerate(requests,1):
        prefix='native-physical-'+stage+'-'+str(index)
        expected_names.append(prefix+'-before.png')
        if request['action']=='navigate':expected_names.append(prefix+'-path-before-return.png')
        expected_names.append(prefix+'-after.png')
    R.require([row['name'] for row in captures]==expected_names,'Physical screenshot order differs')
    for row in captures:
        path=vm/row['name'];R.require(path.is_file() and not path.is_symlink() and path.stat().st_size<=MAX_FILE
            and path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n') and R.digest(path)==row['sha256'],'Physical actual screenshot differs')
    R.write_json(target/'physical-host-receipt.json',dict(stage=stage,requests=5,captures=captures,accessibility_proof=False,release_acceptance=False))
    return dict(stage=stage,requests=5,input_route='direct supported QMP physical keyboard',accessibility_proof=False,release_acceptance=False)

def desktop_controller():
    spec=importlib.util.spec_from_file_location('native_desktop_checked',HERE/'native-physical-controller.py')
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result

def check_editor_save(serial,stage,vm,target):
    C=desktop_controller()
    requests=[C.strict_json(line[len(C.EDITOR_PREFIX):]) for line in serial.splitlines() if line.startswith(C.EDITOR_PREFIX)]
    R.require(len(requests)==1,'Exactly one owned physical editor save required')
    r=C.validate_editor(requests[0],stage)
    provenance=json.loads((target/'serial-native-provenance.json').read_text())
    report=json.loads((target/'serial-native-report.json').read_text())
    R.require(r['boot_id']==provenance['boot_id'] and r['desktop_uid']==provenance['desktop_uid']
              and r['evidence_root']==report['evidence_root'],'Editor save boot/UID/root differs')
    owned=[p for p in report['proven_new_processes'] if p.get('pid')==r['process']['pid']]
    R.require(len(owned)==1 and all(owned[0].get(k)==r['process'].get(k) for k in
              ('pid','start_ticks','executable','executable_sha256','client_id','is_xwayland')),'Editor save process was not the proved fresh app')
    trace=[C.strict_json(line) for line in (target/'gui-trace.log').read_text().splitlines()]
    R.require([x['request'] for x in trace if x.get('event')=='editor-physical-request']==requests
              and json.loads((target/'gui-trace-summary.json').read_text())['omitted_records']==0,'Editor save trace differs/omitted')
    host=vm/('native-editor-save-'+stage+'.log')
    R.require(host.is_file() and not host.is_symlink() and host.stat().st_size<=2*1024*1024,'Editor save host evidence missing/unsafe')
    rows=[C.strict_json(line) for line in host.read_text().splitlines()]
    R.require(len(rows)==5 and all(x['stage']==stage for x in rows),'Editor save event count/stage differs')
    times=[x.get('monotonic_seconds') for x in rows]
    R.require(all(type(t) in (int,float) and math.isfinite(t) and t>=0 for t in times) and times==sorted(times) and times[1]-times[0]<=2 and times[-1]-times[0]<=25,'Editor save time differs')
    R.require([x['event'] for x in rows]==['editor-save-consumed','capture','qmp-key','capture','editor-save-delivered'],'Editor save event sequence differs')
    for item in (rows[0],rows[-1]):
        R.require(item['request']==r and item['request_sha256']==C.canonical(r)
                  and item['accessibility_proof'] is False,'Editor save raw request/delivery differs')
    key=rows[2];R.require(key['nonce']==r['nonce'] and key['chord']==['ctrl','s']
                         and key['exact_press_release'] is True,'Editor save exact CtrlS differs')
    C.qmp_return(key['response'])
    for item,label in ((rows[1],'before'),(rows[3],'after')):
        name='native-editor-save-'+stage+'-'+label+'.png';p=vm/name
        R.require(item['name']==name and p.is_file() and not p.is_symlink() and p.stat().st_size<=MAX_FILE
                  and p.read_bytes().startswith(b'\x89PNG\r\n\x1a\n') and R.digest(p)==item['sha256'],'Editor save capture differs')
    pc=records(serial.splitlines(),C.PREFIX)
    R.require(len(pc)==5 and serial.index(C.PREFIX+json.dumps(pc[2],sort_keys=True))
              <serial.index(C.EDITOR_PREFIX+json.dumps(r,sort_keys=True))
              <serial.index(C.PREFIX+json.dumps(pc[3],sort_keys=True)),'Editor save must stay between text open and archive navigation')
    fixture=target/'files with spaces/editor fixture.txt'
    wanted=('Arctic GUI saved fixture '+Path(report['evidence_root']).name+'\nUnicode: \u05e9\u05dc\u05d5\u05dd \u03bb \u65e5\u672c\u8a9e\n').encode()
    R.require(fixture.is_file() and fixture.read_bytes()==wanted,'Actual GUI saved Unicode bytes differ')
    R.write_json(target/'editor-save-host-receipt.json',dict(stage=stage,requests=1,action='physical Ctrl+S',
                 saved_fixture_sha256=hashlib.sha256(wanted).hexdigest(),accessibility_proof=False,release_acceptance=False))
    return dict(stage=stage,requests=1,accessibility_proof=False,release_acceptance=False)

def check_fullscreen(target,report,uid):
    C=desktop_controller()
    R.require(report.get('diagnostic_controls')==dict(gui_v6=True,editor_physical_save=True,owned_player_fullscreen=True,accessibility_proof=False),'V6 controls were not selected')
    spec=importlib.util.spec_from_file_location('native_fullscreen_geometry',HERE/'native_smoke.py')
    native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
    turns=json.loads((target/'fullscreen-player-receipts.json').read_text())
    captures=json.loads((target/'fullscreen-player-captures.json').read_text())
    moving=json.loads((target/'moving-player-proof.json').read_text())
    visual=json.loads((target/'visual-oracle.json').read_text())
    expected=[moving['player'],visual['player']]
    R.require(type(turns) is list and len(turns)==4 and type(captures) is list and len(captures)==2,'Fullscreen exact turn/capture count differs')
    trace=[C.strict_json(line) for line in (target/'gui-trace.log').read_text().splitlines()]
    R.require([x['receipt'] for x in trace if x.get('event')=='owned-player-fullscreen']==turns
              and [x['receipt'] for x in trace if x.get('event')=='owned-fullscreen-capture']==captures,'Fullscreen raw trace/file differs')
    R.require(json.loads((target/'gui-trace-summary.json').read_text())['omitted_records']==0,'Fullscreen required trace omitted')
    for index,turn in enumerate(turns):
        player=expected[index//2];enabled=index%2==0
        R.require(type(turn) is dict and turn['enabled'] is enabled and turn['release_acceptance'] is False
                  and turn['player']==dict(player,uid=uid),'Fullscreen actual owned identity/control differs')
        p=turn['player']
        owned=[item for item in report['proven_new_processes'] if item.get('pid')==p['pid']]
        R.require(len(owned)==1 and all(owned[0].get(k)==p.get(k) for k in ('pid','start_ticks','executable','executable_sha256','client_id','is_xwayland')),'Fullscreen player was not a proved fresh process')
        R.require(p['executable']=='/usr/bin/celluloid' and p['is_xwayland'] is False
                                 and all(type(p[k]) is int and p[k]>1 for k in ('pid','start_ticks')),'Fullscreen native PID/start differs')
        clocks=[turn['monotonic_ns'],turn['completed_monotonic_ns']]
        R.require(all(type(x) is int and x>0 for x in clocks) and clocks[0]<=clocks[1],'Fullscreen action clocks invalid')
        action=turn['action'];R.require(action['argv']==['mmsg','dispatch','togglefullscreen','client,'+p['client_id']]
            and type(action['returncode']) is int and action['returncode']==0
            and C.strict_json(action['stdout'])=={'success':True} and action['stderr']=='','Fullscreen supported action/response differs')
        before,after=turn['before'],turn['after']
        bm,_,_=native.visual_capture_geometry(before,turn['monitors_before'])
        am,_,crop=native.visual_capture_geometry(after,turn['monitors_after'])
        R.require(before.get('is_fullscreen') is (not enabled) and after.get('is_fullscreen') is enabled
            and str(after['id'])==p['client_id'] and after['pid']==p['pid']
            and after.get('is_xwayland') is False and before.get('is_xwayland') is False
            and all(before.get(k)==after.get(k) for k in ('id','pid','appid','foreign_toplevel_id','monitor'))
            and all(bm.get(k)==am.get(k) for k in ('name','x','y','width','height','scale','is_hdr')),'Fullscreen binding/monitor/state differs')
        if enabled:R.require(crop==dict(x=0,y=0,width=am['width'],height=am['height']),'Actual complete fullscreen viewport absent')
    for index,item in enumerate(captures):
        player=expected[index];shot=moving['screenshot'] if index==0 else visual['screenshot']
        R.require(item['player']==dict(player,uid=uid) and item['release_acceptance'] is False and item['screenshot']==shot,'Fullscreen capture owner/shot differs')
        before,after=item['before'],item['after']
        R.require(all(before.get(k)==after.get(k) for k in ('id','pid','appid','foreign_toplevel_id','monitor',
            'is_focused','is_visible','is_fullscreen','x','y','width','height')) and before.get('is_focused') is True
            and before.get('is_visible') is True and before.get('is_fullscreen') is True
            and str(before['id'])==player['client_id'] and before['pid']==player['pid'],'Fullscreen actual capture identity/focus differs')
        R.require(all(before.get(k)==turns[index*2]['after'].get(k) for k in ('id','pid','appid','foreign_toplevel_id',
            'monitor','is_focused','is_visible','is_fullscreen','x','y','width','height')),'Fullscreen capture differs from entered viewport')
        relative=Path(shot['path']).relative_to(report['evidence_root']);p=target/relative
        R.require(p.is_file() and R.digest(p)==shot['sha256'],'Fullscreen screenshot hash differs')
    R.require(turns[0]['completed_monotonic_ns']<=turns[1]['monotonic_ns']
              <=turns[1]['completed_monotonic_ns']<=turns[2]['monotonic_ns']
              <=turns[2]['completed_monotonic_ns']<=turns[3]['monotonic_ns'],'Fullscreen enter/restore order differs')
    return dict(owned_players=2,fullscreen_actions=4,captures=2,oracle_unchanged=True,release_acceptance=False)

def exactly_zero(serial,label):
    values=re.findall(r'^'+re.escape(label)+r'=(.*)$',serial,re.M)
    R.require(values==['0'],'Missing/duplicate/nonzero '+label)

def installed_scope(serial):
    lines=serial.splitlines()
    R.require(lines.count('ARCTIC-COLLECT-BEGIN')==lines.count('ARCTIC-COLLECT-END')==1
              and lines.index('ARCTIC-COLLECT-BEGIN')<lines.index('ARCTIC-COLLECT-END'),
              'Installed collection incomplete')
    return '\n'.join(lines[lines.index('ARCTIC-COLLECT-BEGIN')+1:lines.index('ARCTIC-COLLECT-END')])

# BEGIN NATIVE_BULK_RECONCILIATION
def native_bulk_json(text):
    def pairs(items):
        result={}
        for key,value in items:
            R.require(key not in result,'Duplicate native bulk JSON key')
            result[key]=value
        return result
    def constant(_):
        raise RuntimeError('Nonfinite native bulk JSON value')
    return json.loads(text,object_pairs_hook=pairs,parse_constant=constant)

def read_native_bulk(path):
    # Retain the original sidecar independently; this read never modifies it.
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        R.require(stat.S_ISREG(before.st_mode) and before.st_nlink==1
                  and 0<before.st_size<=32*1024*1024,'Missing/unsafe/oversized native bulk sidecar')
        chunks=[];count=0
        while count<=32*1024*1024:
            part=os.read(fd,min(65536,32*1024*1024+1-count))
            if not part:break
            count+=len(part);chunks.append(part)
        after=os.fstat(fd)
        current=os.stat(path,follow_symlinks=False)
        R.require(count==before.st_size and count<=32*1024*1024
                  and all(getattr(before,k)==getattr(after,k) for k in
                    ('st_dev','st_ino','st_uid','st_mode','st_size','st_mtime_ns','st_ctime_ns')),
                  'Native bulk sidecar changed during read')
        R.require(stat.S_ISREG(current.st_mode) and (current.st_dev,current.st_ino)==(before.st_dev,before.st_ino),
                  'Native bulk sidecar path changed during read')
        return b''.join(chunks)
    finally:os.close(fd)

def reconcile_native_bulk(serial,wire,stage):
    # First require the actual original UART END, pinned BEGIN, and same-boot
    # provenance. A complete sidecar alone cannot manufacture a native result.
    R.require(type(stage) is str and stage in ('live','installed'),'Native bulk stage differs')
    block,begin,end=native_block(serial,stage)
    uart=serial.splitlines()
    strict_begin=native_bulk_json(next(line.split(' ',1)[1] for line in uart if line.startswith('ARCTIC-NATIVE-RUNNER-BEGIN ')))
    strict_end=native_bulk_json(next(line.split(' ',1)[1] for line in uart if line.startswith('ARCTIC-NATIVE-RUNNER-END ')))
    R.require(type(strict_begin) is dict and set(strict_begin)=={'stage','native_source_sha256','checker_sha256','release_acceptance'}
              and strict_begin==begin and strict_begin['release_acceptance'] is False and strict_end==end,
              'Native bulk UART framing grammar differs')
    R.require(set(end)=={'stage','status','error','evidence_export_complete','release_acceptance'}
              and end['status'] in ('passed','failed') and end['evidence_export_complete'] is True
              and (end['error'] is None or type(end['error']) is str)
              and ((end['status']=='passed')==(end['error'] is None)), 'Incomplete native UART END')
    proofs=[native_bulk_json(line.split(' ',1)[1]) for line in block if line.startswith('ARCTIC-NATIVE-PROVENANCE ')]
    R.require(len(proofs)==1,'Missing/duplicate native bulk UART provenance')
    proof=proofs[0]
    context=dict(schema='arctic-native-bulk-v1',stage=stage,boot_id=proof.get('boot_id'),
                 native_source_sha256=NATIVE_SOURCE_SHA,checker_sha256=CHECKERS['native-functional'][1],
                 release_acceptance=False)
    R.require(proof.get('stage')==stage and proof.get('native_source_sha256')==context['native_source_sha256']
              and proof.get('checker_sha256')==context['checker_sha256'] and proof.get('release_acceptance') is False
              and type(context['boot_id']) is str and re.fullmatch(
                  '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',context['boot_id']), 'Native bulk UART context differs')
    R.require(not any(line.startswith(('ARCTIC-NATIVE-EVIDENCE-CHUNK ','ARCTIC-NATIVE-EVIDENCE-MANIFEST '))
                      for line in serial.splitlines()), 'Mixed UART/bulk native evidence forbidden')
    R.require(type(wire) is bytes and 0<len(wire)<=32*1024*1024 and wire.endswith(b'\n')
              and b'\r' not in wire and b'\x00' not in wire,'Incomplete/oversized native bulk wire')
    rows=wire.splitlines(keepends=True)
    R.require(3<=len(rows)<=128*172+3 and all(len(row)-1<=65536 and row.endswith(b'\n') for row in rows),
              'Native bulk line/count bound differs')
    text=[row[:-1].decode('ascii',errors='strict') for row in rows]
    R.require(text[0].startswith('ARCTIC-NATIVE-BULK-BEGIN ') and text[-1].startswith('ARCTIC-NATIVE-BULK-END '),
              'Native bulk framing differs')
    header=native_bulk_json(text[0].split(' ',1)[1]);footer=native_bulk_json(text[-1].split(' ',1)[1])
    R.require(type(header) is dict and set(header)==set(context) and header==context
              and header['release_acceptance'] is False,'Native bulk header context differs')
    body=b''.join(rows[1:-1])
    R.require(type(footer) is dict and set(footer)==set(context)|{'bytes','lines','sha256'}
              and all(footer[k]==v for k,v in context.items()) and footer['release_acceptance'] is False
              and type(footer['bytes']) is int and footer['bytes']==len(body)
              and type(footer['lines']) is int and footer['lines']==len(rows)-2
              and footer['sha256']==hashlib.sha256(body).hexdigest(),'Native bulk footer/hash differs')
    R.require(text[-2].startswith('ARCTIC-NATIVE-EVIDENCE-MANIFEST '),'Native bulk final manifest missing')
    for line in text[1:-2]:
        R.require(line.startswith('ARCTIC-NATIVE-EVIDENCE-CHUNK '),'Unknown/replayed native bulk record')
        value=native_bulk_json(line.split(' ',1)[1])
        R.require(type(value) is dict and set(value)=={'path','index','data'}
                  and type(value['path']) is str and 0<len(value['path'])<=4096
                  and not any(ord(c)<32 or ord(c)==127 for c in value['path']) and type(value['index']) is int
                  and 0<=value['index']<172 and type(value['data']) is str,'Native bulk chunk grammar differs')
        decoded=base64.b64decode(value['data'],validate=True)
        R.require(0<len(decoded)<=24576,'Native bulk original chunk byte bound differs')
    manifest=native_bulk_json(text[-2].split(' ',1)[1])
    R.require(type(manifest) is dict and set(manifest)=={'schema','stage','files','bytes','evidence_root'}
              and manifest['schema']=='arctic-native-evidence-v1' and manifest['stage']==stage
              and type(manifest['files']) is list and len(manifest['files'])<=128
              and type(manifest['bytes']) is int and 0<=manifest['bytes']<=MAX_TOTAL,
              'Native bulk original manifest grammar/bounds differ')
    for entry in manifest['files']:
        R.require(type(entry) is dict and set(entry)=={'path','bytes','sha256','compressed_bytes','chunks','encoding'}
                  and type(entry['path']) is str and 0<len(entry['path'])<=4096
                  and not any(ord(c)<32 or ord(c)==127 for c in entry['path']),
                  'Native bulk file-entry grammar differs')
    # No original UART byte is normalized or discarded. Insert only the exact
    # complete original body before its existing END, for unchanged check_native.
    marker='ARCTIC-NATIVE-RUNNER-END '
    at=serial.index(marker)
    R.require(at==0 or serial[at-1]=='\n','Native bulk END is not a complete UART line')
    return serial[:at]+body.decode('ascii')+serial[at:]
# END NATIVE_BULK_RECONCILIATION

def validate_harness_serial(vm,evidence):
    results={};errors=[];serials={}
    for stage,name in (('live','serial-install.log'),('installed','serial-boot.log')):
        try:
            serial=(vm/name).read_text(errors='replace')
            serials[stage]=serial
            scoped=installed_scope(serial) if stage=='installed' else serial
            scoped=reconcile_native_bulk(scoped,read_native_bulk(vm/('native-evidence-'+('install' if stage=='live' else 'boot')+'.log')),stage)
            results[stage]=check_native(scoped,stage,evidence/('native-'+stage))
            ready=records(serial.splitlines(),'ARCTIC-NATIVE-LAUNCHER-READY ')
            gone=records(serial.splitlines(),'ARCTIC-NATIVE-LAUNCHER-GONE ')
            proof=results[stage]['provenance']['launcher']
            expected_ready=dict(proof);expected_ready.pop('owned_launcher_gone')
            R.require(ready==[expected_ready] and gone==[proof]
                      and serial.index('ARCTIC-NATIVE-LAUNCHER-READY ')<serial.index('ARCTIC-NATIVE-LAUNCHER-GONE ')
                      <serial.index('ARCTIC-NATIVE-RUNNER-BEGIN ')
                      and 'ARCTIC-NATIVE-LAUNCHER-FAILED ' not in serial,
                      'Owned native launcher ready/disappearance/order evidence differs')
        except BaseException as error:errors.append(stage+': '+str(error))
    # A missing second stage never prevents preserving first-stage guest evidence.
    if 'live' in serials:
        try:
            live=serials['live']
            exactly_zero(live,'ARCTIC-LIVE-SMOKE-EXIT');exactly_zero(live,'ARCTIC-INSTALL-EXIT')
            R.require(re.findall(r'^ARCTIC-OFFLINE-HTTP-RESPONSE=(.*)$',live,re.M)==['000']
                      and re.findall(r'^ARCTIC-OFFLINE-GATE=(.*)$',live,re.M)==['passed: restricted QEMU network, no outside HTTP response'],
                      'Actual offline-install transport gate missing/failed')
            R.require(live.index('ARCTIC-OFFLINE-GATE=')<live.index('ARCTIC-NATIVE-RUNNER-BEGIN ')
                      <live.index('ARCTIC-NATIVE-RUNNER-END ')<live.index('ARCTIC-LIVE-SMOKE-EXIT=')
                      <live.index('ARCTIC-INSTALL-EXIT='),'Live native/install marker order differs')
        except BaseException as error:errors.append('live harness: '+str(error))
    if 'installed' in serials:
        try:
            installed=installed_scope(serials['installed'])
            exactly_zero(installed,'ARCTIC-INSTALLED-SMOKE-EXIT')
            R.require(installed.index('ARCTIC-NATIVE-RUNNER-END ')<installed.index('ARCTIC-INSTALLED-SMOKE-EXIT='),
                      'Installed native/probe exit marker order differs')
        except BaseException as error:errors.append('installed harness: '+str(error))
    if len(results)==2:
        try:R.require(results['live']['provenance']['boot_id']!=results['installed']['provenance']['boot_id'],
                      'Live/installed boot IDs are identical')
        except BaseException as error:errors.append('boot identity: '+str(error))
    R.write_json(evidence/'native-stages.json',dict(results=results,errors=errors,release_acceptance=False))
    R.require(not errors,'; '.join(errors))
    return results

def preserve_audio(path,target):
    R.require(path.is_file() and not path.is_symlink(),'Virtual output WAV absent: '+path.name)
    target.mkdir(parents=True,exist_ok=True)
    R.require(path.stat().st_size<=1_073_741_824,'Virtual WAV exceeds 1 GiB inspection bound')
    info=dict(source_name=path.name,source_bytes=path.stat().st_size,source_sha256=R.digest(path),
              scope='PCM delivered to an emulated output in this stage; attribution/perceived audio remains unqualified')
    try:
        with wave.open(str(path),'rb') as source:
            params=source.getparams();info.update(channels=params.nchannels,rate=params.framerate,width=params.sampwidth,
                                               frames=params.nframes,compression=params.comptype)
            R.require(params.nchannels==2 and params.framerate==48000 and params.sampwidth==2
                      and params.comptype=='NONE' and params.nframes>0,'Virtual WAV format/frames differ')
            first_nonzero=None;position=0;blocks=0;nonzero_blocks=0
            while data:=source.readframes(16384):
                if data!=b'\0'*len(data):
                    nonzero_blocks+=1
                    if first_nonzero is None:first_nonzero=position
                position+=len(data)//(params.nchannels*params.sampwidth);blocks+=1
            R.require(position==params.nframes,'Truncated virtual WAV PCM')
            info.update(blocks=blocks,nonzero_blocks=nonzero_blocks,first_nonzero_block_frame=first_nonzero)
            if path.stat().st_size<=32*1024*1024:
                shutil.copyfile(path,target/path.name);info['preserved_full']=True
            else:
                info['preserved_full']=False;info['excerpts']=[]
                offsets=sorted(set([0,max(0,params.nframes-2*params.framerate),first_nonzero or 0]))
                for index,offset in enumerate(offsets):
                    source.setpos(offset);pcm=source.readframes(2*params.framerate)
                    name=path.stem+'-excerpt-'+str(index)+'.wav'
                    with wave.open(str(target/name),'wb') as out:
                        out.setparams(params);out.writeframes(pcm)
                    info['excerpts'].append(dict(path=name,start_frame=offset,frames=len(pcm)//4,sha256=R.digest(target/name)))
            R.write_json(target/(path.stem+'.json'),info)
            R.require(first_nonzero is not None,'Virtual output contains only silent PCM; diagnose fixture/backend/app')
    except BaseException as error:
        with path.open('rb') as source:(target/(path.name+'.bounded-prefix.bin')).write_bytes(source.read(1024*1024))
        info['error']=str(error);R.write_json(target/(path.stem+'.json'),info)
        raise
    return info
