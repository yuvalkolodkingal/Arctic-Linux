#!/usr/bin/env python3
"""Finite controller: original bootstrap only; no physical app input."""
import hashlib,json,time
from pathlib import Path

def require(value,message):
    if not value:raise RuntimeError(message)

def run_v3(vm,out,menu_seen,checker_sha,bulk,clock=time.monotonic,sleep=time.sleep):
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
            bulk.pump()
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
        data_text=bulk.text()
        begins=rows(data_text,'ARCTIC-PCMANFM-DIAG-BEGIN ')
        require(len(begins)<=1,'duplicate guest begin')
        if begins:
            require(begins[0].get('checker_sha256')==checker_sha
                    and begins[0].get('native_source_sha256')=='ed382ab80a4918118370253c383b0fefde116ba34d55e977bcd34607ad2632d0'
                    and begins[0].get('release_acceptance') is False,'guest source begin mismatch')
        requests=rows(text,'ARCTIC-PCMANFM-PHYSICAL-REQUEST ')
        gtk_requests=rows(text,'ARCTIC-GTK-PHYSICAL-REQUEST ')
        require(not requests and not gtk_requests,'finite preflight forbids physical app input')
        ends=rows(data_text,'ARCTIC-PCMANFM-DIAG-END ')
        require(len(ends)<=1,'duplicate diagnostic end')
        if ends:
            require(len(begins)==1 and ends[0].get('release_acceptance') is False,
                    'guest end without one source begin')
            capture('pcmanfm-99-final');record('diagnostic-end',value=ends[0],physical_requests=len(requests),gtk_physical_requests=len(gtk_requests),
                added_bulk_device=True,console_unchanged=True)
            require(ends[0].get('status')=='diagnostic-collected' and ends[0].get('error') is None
                    and ends[0].get('evidence_export_complete') is True,'guest collector/security/preservation failed')
            return
        if clock()-last_capture>=30:
            capture('pcmanfm-running-%04ds'%int(clock()-started));last_capture=clock()
        pause(.5)
    raise RuntimeError('900-second boot/controller deadline; no repeated input')
