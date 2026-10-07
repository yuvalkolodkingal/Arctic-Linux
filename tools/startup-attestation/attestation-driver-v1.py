"""Finite attestation-only input driver; no -d, session hook or visual gate."""
import importlib.util
import json
from pathlib import Path
import time

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('attestation_protocol',HERE/'attest-host-v1.py')
H=importlib.util.module_from_spec(spec);spec.loader.exec_module(H)
COLLECTOR_COMMAND="sudo sh -c 'exec >/dev/ttyS0 2>&1; exec sh /dev/disk/by-label/ARCTICATTEST'"

def require(value,message):
    if not value:raise RuntimeError(message)

def run(vm,out,qemu_origin,entry_origin,menu_seen,clock=time.monotonic,sleep=time.sleep):
    require(menu_seen is True and type(entry_origin) in (int,float),'Requires selected Safe boot entry')
    out=Path(out);events=out/'attestation-events.log';require(not events.exists(),'Event output collision')
    def record(event,**values):
        now=clock();value=dict(event=event,monotonic_seconds=now,entry_elapsed_seconds=now-entry_origin,**values)
        with events.open('a') as file:file.write(json.dumps(value,sort_keys=True)+'\n')
        return value
    def wait_until(end):
        while clock()<end:
            require(vm.alive(),'Owned VM exited during bounded wait');sleep(min(.5,end-clock()))
    def capture(name):
        require(vm.alive(),'Owned VM exited before evidence capture')
        path=vm.shot(name);require(path and Path(path).is_file(),'Required attestation screenshot failed')
        record('capture',name=name+'.png')
    record('normal-startup-wait',requested_seconds=120,qemu_origin=qemu_origin,no_input=True)
    try:
        wait_until(entry_origin+120);capture('attest-00-normal-startup')
        started=record('open-terminal')['monotonic_seconds'];vm.keys('meta_l-ret');wait_until(started+60)
        record('return-prompt');vm.keys('ret');wait_until(clock()+5)
        capture('attest-01-before-command')
        record('collector-command',command=COLLECTOR_COMMAND,no_session_hook=True)
        vm.type_text(COLLECTOR_COMMAND,gap=.2);vm.keys('ret')
        deadline=clock()+180
        while clock()<deadline:
            path=out/'serial.log';text=path.read_text(errors='replace') if path.exists() else ''
            values,ended=H.protocol(text,live=True)
            if ended:
                # Final strict parsing is still mandatory after VM completion;
                # this observation never binds a startup target or closes a gate.
                require(values[-1][1]==dict(status='attestation-collected-unreviewed',error=None,release_acceptance=False)
                        and values[-1][1].get('release_acceptance') is False,'Actual collector failed')
                record('end-observed',value=values[-1][1]);capture('attest-02-collected')
                record('attestation-driver-complete',release_acceptance=False,safe_visual_gate='open');return
            require(vm.alive(),'Owned VM exited before attestation END');sleep(.5)
        raise RuntimeError('Attestation END timeout180s')
    except BaseException as error:
        record('attestation-driver-failure',error=type(error).__name__+': '+str(error))
        if vm.alive():
            try:capture('attest-98-failure')
            except BaseException as extra:record('failure-capture-error',error=type(extra).__name__+': '+str(extra))
        raise

def validate_events(path):
    import math
    rows=[json.loads(v) for v in Path(path).read_text().splitlines()]
    require(rows and all(type(v.get('monotonic_seconds')) in (int,float) and math.isfinite(v['monotonic_seconds']) for v in rows),'Invalid event clocks')
    require(all(a['monotonic_seconds']<=b['monotonic_seconds'] for a,b in zip(rows,rows[1:])),'Event clocks reversed')
    phases=['normal-startup-wait','open-terminal','return-prompt','collector-command','end-observed','attestation-driver-complete']
    names=[v['event'] for v in rows];require(all(names.count(v)==1 for v in phases) and [names.index(v) for v in phases]==sorted(names.index(v) for v in phases),'Phase order/duplicates differ')
    require(names==['normal-startup-wait','capture','open-terminal','return-prompt','capture','collector-command','end-observed','capture','attestation-driver-complete'],
            'Unexpected or reordered attestation event')
    by={v:rows[names.index(v)] for v in phases};origin=by['normal-startup-wait']['monotonic_seconds']-by['normal-startup-wait']['entry_elapsed_seconds']
    require(all(type(v.get('entry_elapsed_seconds')) in (int,float) and math.isfinite(v['entry_elapsed_seconds'])
                and abs(v['entry_elapsed_seconds']-(v['monotonic_seconds']-origin))<1e-6 for v in rows),'Event origins differ')
    require(by['open-terminal']['entry_elapsed_seconds']>=120 and by['return-prompt']['monotonic_seconds']-by['open-terminal']['monotonic_seconds']>=60
            and by['collector-command']['monotonic_seconds']-by['return-prompt']['monotonic_seconds']>=5,'Required startup/prompt bounds differ')
    require(by['collector-command']['command']==COLLECTOR_COMMAND and by['collector-command']['no_session_hook'] is True
            and by['attestation-driver-complete']['release_acceptance'] is False,'Attestation scope differs')
    captures=[v['name'] for v in rows if v['event']=='capture'];require(captures==['attest-00-normal-startup.png','attest-01-before-command.png','attest-02-collected.png'],'Evidence captures differ')
    return dict(status='attestation-input-chronology-collected',capture_names=captures,original34_qualification=False,release_acceptance=False)
