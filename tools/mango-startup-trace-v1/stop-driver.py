"""One labelled post-34 stop and unchanged strict trace transport validation."""
import sys
sys.dont_write_bytecode=True
import importlib.util,json,time
from pathlib import Path
COMMAND='sudo /usr/bin/python3.14 -I -S /run/arctic-mango-trace-cd/request-stop.py'
def require(v,m):
    if not v:raise RuntimeError(m)
def completed(raw):
    require(len(raw)<=33554432,'Existing trace serial byte bound exceeded')
    prefix,separator,pending=raw.rpartition(b'\n')
    require(len(pending)<=262144,'Pending trace row bound exceeded')
    data=(prefix+b'\n' if separator else b'').decode('utf-8',errors='strict')
    return data,[line for line in data.splitlines() if line.startswith('ARCTIC-RENDER-END ')]
def run(vm,out,clock=time.monotonic,sleep=time.sleep):
    out=Path(out);log=out/'mango-trace-events.log'
    require(not log.exists(),'Trace event output must be unused')
    safe=[json.loads(x) for x in (out/'safe-events.log').read_text().splitlines()]
    require(safe[-1]['event']=='diagnostic-complete' and sum(x['event']=='capture' for x in safe)==34,'Original34 must complete before labelled stop')
    def record(event,**values):
        with log.open('a') as f:f.write(json.dumps(dict(event=event,monotonic_seconds=clock(),startup_perturbation=True,release_acceptance=False,safe_visual_gate='OPEN',**values),sort_keys=True)+'\n')
    raw=(out/'serial.log').read_bytes();_,ends=completed(raw)
    require(not ends,'Trace ended before labelled stop')
    record('trace-stop-request',command=COMMAND,after_original34=True)
    deadline=clock()+180
    try:
        require(vm.alive(),'Owned VM exited before labelled stop')
        vm.type_text(COMMAND,gap=.2);vm.keys('ret')
        record('trace-stop-input-complete')
        while clock()<deadline:
            raw=(out/'serial.log').read_bytes();_,ends=completed(raw)
            if ends:
                require(len(ends)==1,'Duplicate completed trace END')
                # Final full strict decode includes a pending suffix: no final
                # repair, replacement, row drop or incomplete marker waiver.
                text=raw.decode('utf-8',errors='strict')
                spec=importlib.util.spec_from_file_location('mango_trace_transport',Path(__file__).with_name('transport.py'))
                transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport)
                report,bodies=transport.decode(text);transport.validate_evidence(report,bodies)
                record('trace-stop-complete',status=report['status'],semantic_bodies=len(bodies))
                return
            require(vm.alive(),'Owned VM exited before completed trace receipt')
            sleep(min(.25,max(0,deadline-clock())))
        raise RuntimeError('Trace terminal receipt exceeded180s')
    except BaseException as exc:
        record('trace-stop-failed',error=type(exc).__name__+': '+str(exc));raise
