#!/usr/bin/env python3
"""Default-off boot controller; one physical Return at most, no input fallback."""
import hashlib
import json
from pathlib import Path
import re
import time


def require(value, message):
    if not value:
        raise RuntimeError(message)


def canonical(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def physical_request(value):
    require(isinstance(value,dict) and value.get('schema')=='arctic-pcmanfm-physical-request-v1'
            and value.get('release_acceptance') is False and value.get('virtual_status')=='failed-30s-title-gate'
            and re.fullmatch('[0-9a-f]{32}',value.get('nonce',''))
            and value.get('arm')=='observed-route'
            and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',value.get('boot_id',''))
            and re.fullmatch('[0-9a-f]{64}',value.get('entry_evidence_sha256','')),
            'invalid physical request identity/status')
    proof,client,entry=value.get('process',{}),value.get('client',{}),value.get('entry',{})
    require(all(type(proof.get(k)) is int and proof[k]>1 for k in ('pid','start_ticks'))
            and proof.get('executable')=='/usr/bin/pcmanfm' and proof.get('is_xwayland') is False
            and isinstance(proof.get('client_id'),str) and proof['client_id'].isdigit()
            and re.fullmatch('[0-9a-f]{64}',proof.get('executable_sha256','')),
            'invalid physical owned native process')
    require(type(client.get('id')) is int and type(client.get('pid')) is int
            and client['pid']==proof['pid'] and str(client['id'])==proof['client_id']
            and client.get('is_xwayland') is False and client.get('is_focused') is True
            and client.get('is_visible') is True and isinstance(client.get('foreign_toplevel_id'),str)
            and 0<len(client['foreign_toplevel_id'])<=128, 'physical client binding/focus differs')
    require(isinstance(value.get('fixture_path'),str)
            and re.fullmatch(r'/tmp/arctic-native-smoke-[a-zA-Z0-9_-]+/files with spaces',value['fixture_path'])
            and entry.get('description')=='Folder location bar' and entry.get('text')==value['fixture_path']
            and entry.get('state',{}).get('focused') is True
            and entry['state'].get('showing') is True and entry['state'].get('visible') is True,
            'physical exact owned entry text/focus differs')
    return value


def qmp_return(answer):
    # vmtest.cmd sends no request ID. input-send-event has an empty successful result.
    require(type(answer) is dict and set(answer)=={'return'} and type(answer['return']) is dict
            and answer['return']=={}, 'strict physical QMP Return failed; no send-key/focus fallback')
    return answer


def run(vm,out,menu_seen,checker_sha,clock=time.monotonic,sleep=time.sleep):
    require(menu_seen,'diagnostic requires detected normal boot entry; no fallback boot')
    out=Path(out);events=out/'pcmanfm-host-events.log'
    require(not events.exists(),'host event output must be unused')
    started=clock();deadline=started+900;used=set()
    def record(event,**fields):
        sample=clock()
        value=dict(event=event,monotonic_seconds=sample,controller_elapsed_seconds=sample-started,**fields)
        with events.open('a') as stream:stream.write(json.dumps(value,sort_keys=True)+'\n')
        return value
    def capture(name):
        require(vm.alive(),'owned VM exited before capture')
        path=vm.shot(name);require(path and Path(path).is_file(),'required QMP screenshot failed')
        record('capture',name=Path(path).name,sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())
    def pause(seconds):
        end=clock()+seconds
        while clock()<end:
            require(vm.alive() and clock()<deadline,'bounded diagnostic VM exited/timed out')
            sleep(min(.5,end-clock()))
    def serial():
        path=out/'serial.log'
        require(path.exists() and path.stat().st_size<=128*1024*1024,'serial unavailable/unbounded')
        return path.read_text(errors='replace')
    def rows(text,prefix):
        return [json.loads(line[len(prefix):]) for line in text.splitlines() if line.startswith(prefix)]
    record('diagnostic-start',release_acceptance=False,host_physical_ack_is_guest_input=False)
    boot_until=clock()+180
    while clock()<boot_until:
        require(vm.alive(),'VM exited before live session marker')
        if 'live session mode:' in serial():break
        pause(1)
    else:raise RuntimeError('bounded live session mode marker absent; no blind input')
    pause(120);capture('pcmanfm-10-desktop-before-bootstrap')
    # Retain the existing native harness bootstrap prompt sequence once, without retries.
    vm.keys('meta_l-ret');pause(75);capture('pcmanfm-11-bootstrap-terminal')
    vm.keys('ret');pause(15);vm.keys('ret');pause(5)
    vm.type_text('sudo sh /dev/sr0; exit',gap=.3);vm.keys('ret')
    record('bootstrap-command-sent',command='sudo sh /dev/sr0; exit',retry_count=0)
    begins=[];last_capture=clock()
    while clock()<deadline:
        require(vm.alive(),'VM exited before diagnostic end')
        text=serial()
        require('ARCTIC-NATIVE-LAUNCHER-FAILED ' not in text,'owned launcher failed; no retry')
        begins=rows(text,'ARCTIC-PCMANFM-DIAG-BEGIN ')
        require(len(begins)<=1,'duplicate guest begin')
        if begins:
            require(begins[0].get('checker_sha256')==checker_sha
                    and begins[0].get('native_source_sha256')=='ed382ab80a4918118370253c383b0fefde116ba34d55e977bcd34607ad2632d0'
                    and begins[0].get('release_acceptance') is False,'guest source begin mismatch')
        requests=rows(text,'ARCTIC-PCMANFM-PHYSICAL-REQUEST ')
        require(len(requests)<=1,'duplicate physical request; no resend')
        if requests:
            require(begins and text.index('ARCTIC-PCMANFM-DIAG-BEGIN ')<text.index('ARCTIC-PCMANFM-PHYSICAL-REQUEST '),
                    'physical request before proved guest begin')
            request=physical_request(requests[0]);nonce=request['nonce']
            if nonce not in used:
                gone=rows(text,'ARCTIC-NATIVE-LAUNCHER-GONE ')
                require(len(gone)==1 and gone[0].get('boot_id')==request['boot_id']
                        and gone[0].get('launcher_sha256')=='e948f2ff9c7273f20b0d42e67cc891e3a3f6e0954dfc1ac3afca2aa7c3d7df4c'
                        and gone[0].get('owned_launcher_gone') is True,'physical request same-boot launcher binding absent')
                used.add(nonce) # Consume before attempting input; a thrown/failed QMP call is never retried.
                received=clock()
                record('physical-one-use-consumed',nonce=nonce,request_sha256=canonical(request),
                       receipt_monotonic_seconds=received,release_acceptance=False)
                capture('pcmanfm-20-before-physical-return')
                origin=clock()
                require(origin-received<=2,'physical host handling exceeded 2 s; no stale injection')
                answer=vm.cmd('input-send-event',events=[
                    {'type':'key','data':{'down':True,'key':{'type':'qcode','data':'ret'}}},
                    {'type':'key','data':{'down':False,'key':{'type':'qcode','data':'ret'}}}])
                qmp_return(answer)
                record('physical-host-ack',nonce=nonce,boot_id=request['boot_id'],process=request['process'],
                       request_sha256=canonical(request),response=answer,input_start_monotonic_seconds=origin,
                       receipt_monotonic_seconds=received,
                       input_end_monotonic_seconds=clock(),exactly_one_press_release=True,release_acceptance=False)
                capture('pcmanfm-21-after-physical-return')
        ends=rows(text,'ARCTIC-PCMANFM-DIAG-END ')
        require(len(ends)<=1,'duplicate diagnostic end')
        if ends:
            require(len(begins)==1 and ends[0].get('release_acceptance') is False,
                    'guest end without one source begin')
            capture('pcmanfm-99-final');record('diagnostic-end',value=ends[0],physical_requests=len(requests))
            require(ends[0].get('status')=='diagnostic-collected' and ends[0].get('error') is None
                    and ends[0].get('evidence_export_complete') is True,'guest collector/security/preservation failed')
            return
        if clock()-last_capture>=30:
            capture('pcmanfm-running-%04ds'%int(clock()-started));last_capture=clock()
        pause(.5)
    raise RuntimeError('900-second boot/controller deadline; no repeated input')
