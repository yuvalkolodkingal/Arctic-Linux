"""Native Dodge windows acceptance on two Mango outputs, using a disposable Kitty.

Requires an isolated BarHarness entry point. The runner launches/stops its own preview, selects empty workspaces, hides
the installed bar, changes one output scale, then restores all of those states.
Do not run another input automation or use the tested outputs during this check.
"""
import argparse
import json
import pathlib
import subprocess
import time
import signal
import sys
import os
import selectors
import math

signal.signal(signal.SIGTERM,lambda *_: sys.exit(143))
signal.signal(signal.SIGHUP,lambda *_: sys.exit(129))

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--preview',required=True)
parser.add_argument('--pointer',required=True)
parser.add_argument('--out',required=True,type=pathlib.Path)
parser.add_argument('--monitor',required=True)
parser.add_argument('--other-monitor',required=True)
parser.add_argument('--isolated',action='store_true',help='For a separate headless Mango only; do not contact the user production shell')
args=parser.parse_args()
args.out.mkdir(parents=True,exist_ok=True)
def query(kind): return json.loads(subprocess.check_output(['mmsg','get',kind]))
def dispatch(command,client=None):
    cmd=['mmsg','dispatch',command]+([f'client,{client}'] if client else [])
    result=json.loads(subprocess.check_output(cmd));assert result.get('success'),(cmd,result)
def ipc(*words):
    return subprocess.check_output(['quickshell','ipc','-p',args.preview,'call','testbar',*map(str,words)],text=True).strip()
def state(name=args.monitor): return next(b for b in json.loads(ipc('state')) if b['screen']==name)
def record(name,value):
    results.append(dict(test=name,value=value));print(name,json.dumps(value),flush=True)
def until(predicate,timeout=2):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if predicate(): return
        time.sleep(.04)
    (args.out/'failed-geometry.json').write_text(json.dumps({'mangoClients':query('all-clients'),'mangoMonitors':query('all-monitors'),'cursor':query('cursorpos'),'layers':query('all-layers'),'bridge':json.loads(ipc('geometry'))},indent=2))
    shot('failed-state')
    raise AssertionError('State did not settle: '+ipc('state'))
def shot(name,monitor=args.monitor):
    subprocess.run(['grim','-o',monitor,str(args.out/f'{name}.png')],check=True)
def output(name): return next(m for m in query('all-monitors')['monitors'] if m['name']==name)
def view(name,tag): dispatch('focusmon,'+name);dispatch(f'view,{tag},0')
def cursor(x,y):
    monitors=query('all-monitors')['monitors']
    W=max(m['x']+m['width'] for m in monitors);H=max(m['y']+m['height'] for m in monitors)
    pointer.stdin.write(f'move {x} {y} {W} {H}\n');pointer.stdin.flush()
    assert pointer.stdout.readline().strip()=='OK'
def button(value):
    pointer.stdin.write(f'button {value}\n');pointer.stdin.flush();assert pointer.stdout.readline().strip()=='OK'
def center(name):
    m=output(name);cursor(m['x']+m['width']//2,m['y']+m['height']//2)
def geometry(name,x,y):
    m=output(name)
    dispatch(f'movewin,{m["x"]+x},{m["y"]+y}',client)
    dispatch('resizewin,320,220',client)
def clear(name): geometry(name,200,200)
def overlap(name,edge):
    m=output(name)
    x,y={'left':(10,200),'right':(m['width']-330,200),
         'top':(200,10),'bottom':(200,m['height']-230)}[edge]
    geometry(name,x,y)
def physical_edge(name,edge):
    m=output(name)
    x,y={'left':(0,m['height']//2),'right':(m['width']-1,m['height']//2),
         'top':(m['width']//2,0),'bottom':(m['width']//2,m['height']-1)}[edge]
    cursor(m['x']+x,m['y']+y)
def make_window():
    proc=subprocess.Popen(['kitty','--class','ArcticDodgeTest','--title','Arctic Dodge test','sh','-c','sleep 600'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    windows.append(proc)
    until(lambda:any(c.get('appid')=='ArcticDodgeTest' for c in query('all-clients')['clients']))
    c=next(c for c in query('all-clients')['clients'] if c.get('appid')=='ArcticDodgeTest')
    dispatch('movewin,2200,200',c['id'])
    return proc,c['id']
original_monitors=query('all-monitors')['monitors']
original_clients=query('all-clients')['clients']
original_outputs=json.loads(subprocess.check_output(['wlr-randr','--json']))
assert not any(l['name']=='arctic-polkit' for l in query('all-layers')['layers']),'Finish native authentication before input automation.'
selected=[next(m for m in original_monitors if m['name']==name) for name in (args.monitor,args.other_monitor)]
assert pathlib.Path(args.preview).resolve().name=='bar-test.qml','Use the dedicated isolated harness entry point.'
if args.isolated:
    assert all(m['name'].startswith('HEADLESS-') for m in original_monitors),'Isolated checks require headless outputs.'
assert all(len(m['active_tags'])==1 for m in selected),'Preserve multi-tag sessions; use a disposable single-tag session for this test.'
empty={m['name']:next(t['index'] for t in reversed(m['tags']) if not t['client_count']) for m in selected}
original_hidden='true' if args.isolated else subprocess.check_output(['arctic-shell-ipc','bar','hidden'],text=True).strip()
pointer=subprocess.Popen([args.pointer],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
assert pointer.stdout.readline().strip()=='READY'
results=[];windows=[];client=None
try:
    if original_hidden=='false': subprocess.run(['arctic-shell-ipc','bar','toggleHidden'],check=True)
    subprocess.run(['quickshell','-n','-d','-p',args.preview],check=True)
    until(lambda: bool(ipc('state')))
    for name in empty: view(name,empty[name])
    view(args.monitor,empty[args.monitor])
    proc,client=make_window();clear(args.monitor);center(args.monitor)
    for scale in (1,1.5):
        subprocess.run(['wlr-randr','--output',args.monitor,'--scale',str(scale)],check=True)
        time.sleep(.4)
        for edge in ('left','right','top','bottom'):
            clear(args.monitor);center(args.monitor)
            ipc('configure',edge,56,'false');ipc('mode','dodge')
            until(lambda:state()['geometryReady'] and not state()['overlap'] and state()['reveal']==1)
            time.sleep(.8);assert state()['reveal']==1
            overlap(args.monitor,edge)
            until(lambda:state()['overlap'])
            time.sleep(.25);assert state()['reveal']==1
            until(lambda:state()['reveal']==0)
            shot(f'scale{scale}-{edge}-overlap-hidden')
            physical_edge(args.monitor,edge);until(lambda:state()['reveal']==1)
            shot(f'scale{scale}-{edge}-edge-revealed')
            center(args.monitor);until(lambda:state()['reveal']==0)
            ipc('open',args.monitor,'calendar');time.sleep(.9)
            assert state()['reveal']==1 and state()['popupHere']
            popup=state()['popup'];m=output(args.monitor)
            assert popup['x']>=0 and popup['x']+popup['width']<=m['width']
            assert popup['y']>=0 and popup['y']+popup['height']<=m['height']
            ipc('close');until(lambda:state()['reveal']==0)
            clear(args.monitor);until(lambda:not state()['overlap'] and state()['reveal']==1)
            shot(f'scale{scale}-{edge}-clear-visible')
            record(f'scale{scale}-{edge}',{'clearVisible':True,'overlapHidden':True,'edgeReveal':True,'delay':True,'menuPinnedAndInBounds':popup})
    # Thickness uses the full potential region, independent of animated exposed pixels.
    clear(args.monitor);center(args.monitor);geometry(args.monitor,40,200)
    ipc('configure','left',28,'false');ipc('mode','dodge');until(lambda:not state()['overlap'] and state()['reveal']==1)
    ipc('configure','left',56,'false');ipc('mode','dodge');until(lambda:state()['overlap'] and state()['reveal']==0)
    record('thickness-change','28px clear, 56px overlapped without moving window')
    # Inactive workspace and minimized clients must not keep the bar hidden.
    alternative=next(t['index'] for t in output(args.monitor)['tags'] if not t['client_count'] and t['index']!=empty[args.monitor])
    view(args.monitor,alternative);until(lambda:not state()['overlap'] and state()['reveal']==1)
    view(args.monitor,empty[args.monitor]);until(lambda:state()['overlap'] and state()['reveal']==0)
    record('inactive-workspace','visible on empty workspace; hidden when returning to overlap')
    dispatch('minimized',client);until(lambda:not state()['overlap'] and state()['reveal']==1)
    record('minimized-window','excluded without restoring any other user window')
    proc.terminate();proc.wait(timeout=3)
    proc,client=make_window();overlap(args.monitor,'left');center(args.monitor)
    until(lambda:state()['overlap'] and state()['reveal']==0)
    ipc('separate',args.monitor);time.sleep(.9);assert state()['reveal']==1
    ipc('close');until(lambda:state()['reveal']==0);record('separate-popup','pins bar')
    physical_edge(args.monitor,'left');until(lambda:state()['reveal']==1)
    m=output(args.monitor);cursor(m['x']+16,m['y']+int(m['height']*.6));button(1);center(args.monitor);time.sleep(1)
    assert state()['reveal']==1 and state()['heldOpen'];button(0);until(lambda:state()['reveal']==0)
    record('press-drag-release','held outside until release; hides without further pointer movement')
    ipc('focus',args.monitor);until(lambda:state()['reveal']==1)
    subprocess.run(['wtype','-k','End','-k','End'],check=True);time.sleep(.2)
    focus=state()['focused'];assert focus['y']>=0 and focus['y']+focus['height']<=m['height']
    ipc('focus',args.monitor);until(lambda:state()['reveal']==0);record('keyboard','reveal and End scrolling')
    dispatch('togglefullscreen',client)
    for edge in ('left','right','top','bottom'):
        center(args.monitor);ipc('configure',edge,32,'false');ipc('mode','dodge')
        until(lambda:state()['overlap'] and state()['reveal']==0)
        physical_edge(args.monitor,edge);until(lambda:state()['reveal']==1)
        shot(f'fullscreen-{edge}-revealed')
        center(args.monitor);until(lambda:state()['reveal']==0)
    dispatch('togglefullscreen',client);record('fullscreen','all edges hide and reveal')
    dispatch('tagmon,'+args.other_monitor,client);center(args.other_monitor)
    for edge in ('left','right','top','bottom'):
        clear(args.other_monitor);ipc('configure',edge,32,'false');ipc('mode','dodge')
        until(lambda:not state()['overlap'] and state()['reveal']==1)
        overlap(args.other_monitor,edge);until(lambda:state(args.other_monitor)['overlap'] and state(args.other_monitor)['reveal']==0)
        assert not state()['overlap'] and state()['reveal']==1
        physical_edge(args.other_monitor,edge);until(lambda:state(args.other_monitor)['reveal']==1)
        center(args.other_monitor);record('second-monitor-'+edge,'independent overlap/physical reveal')
    clear(args.other_monitor);center(args.other_monitor);ipc('mode','auto')
    until(lambda:state()['reveal']==0 and state(args.other_monitor)['reveal']==0)
    ipc('mode','always');until(lambda:state()['reveal']==1 and state(args.other_monitor)['reveal']==1)
    record('existing-modes','Auto-hide and Always visible remain separate')
    if args.isolated:
        ipc('configure','left',32,'false');ipc('mode','dodge')
        until(lambda:state()['geometryReady'])
        processes=subprocess.check_output(['ps','-eo','pid,ppid,args'],text=True)
        bridge=next(int(line.split(None,2)[0]) for line in processes.splitlines()
                    if str(pathlib.Path(args.preview).parent/'scripts/window_geometry.py') in line)
        compositor=int(pathlib.Path(os.environ['MANGO_INSTANCE_SIGNATURE']).stem.split('-')[-1])
        def resource(pid):
            fields=pathlib.Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
            return {'cpuSeconds':(int(fields[11])+int(fields[12]))/os.sysconf('SC_CLK_TCK'),
                    'rssBytes':int(fields[21])*os.sysconf('SC_PAGE_SIZE')}
        # Exercise real compositor events rather than manufacturing bridge rectangles.
        stream=subprocess.Popen(['mmsg','watch','all-clients'],stdout=subprocess.PIPE)
        watch=selectors.DefaultSelector();watch.register(stream.stdout,selectors.EVENT_READ)
        def drain(timeout):
            data=b'';deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                for key,_ in watch.select(max(0,deadline-time.monotonic())):data+=os.read(key.fd,65536)
            return data.count(b'\n')
        try:
            drain(.2)
            before={p:resource(p) for p in (bridge,compositor)}
            idle=drain(1)
            assert idle==0,idle
            after_idle={p:resource(p) for p in before}
            begin=time.monotonic()
            for i in range(120):
                geometry(args.other_monitor,200+(i%100),200)
                time.sleep(.008)
            duration=time.monotonic()-begin
            events=drain(.2)
            after_moves={p:resource(p) for p in before}
            assert 1<events<=math.ceil(duration/.06)+4,(events,duration)
            record('event-volume',{'idleEventsPerSecond':idle,'movesAndResizes':240,
                   'seconds':duration,'events':events,'maximumHz':1/.06,
                   'resources':{label:{'idleCpuSeconds':after_idle[p]['cpuSeconds']-before[p]['cpuSeconds'],
                         'moveCpuSeconds':after_moves[p]['cpuSeconds']-after_idle[p]['cpuSeconds'],
                         'rssBytes':after_moves[p]['rssBytes']} for label,p in [('bridge',bridge),('compositor',compositor)]}})
        finally:
            watch.close();stream.terminate();stream.wait(timeout=3)
        ipc('configure','left',32,'false');ipc('mode','dodge');overlap(args.other_monitor,'left');center(args.other_monitor)
        until(lambda:state(args.other_monitor)['overlap'] and state(args.other_monitor)['reveal']==0)
        processes=subprocess.check_output(['ps','-eo','pid,ppid,args'],text=True)
        bridge=next(int(line.split(None,2)[0]) for line in processes.splitlines()
                    if str(pathlib.Path(args.preview).parent/'scripts/window_geometry.py') in line)
        children=[int(line.split(None,2)[0]) for line in processes.splitlines()
                  if len(line.split(None,2))==3 and line.split(None,2)[1]==str(bridge)
                  and 'mmsg watch ' in line]
        assert len(children)==2,children
        os.kill(children[0],signal.SIGTERM)
        until(lambda:not state(args.other_monitor)['geometryReady'] and state(args.other_monitor)['reveal']==1)
        until(lambda:state(args.other_monitor)['geometryReady'] and state(args.other_monitor)['reveal']==0,timeout=8)
        record('ipc-disconnect-reconnect','fails visible immediately; reconnects after5s without polling')
finally:
    try: button(0)
    except (BrokenPipeError,AssertionError): pass
    # Do this first: a later output/workspace restoration failure must never leave
    # a second visible bar behind. SIGTERM/SIGHUP also run this finally block.
    subprocess.run(['quickshell','kill','-p',args.preview],check=False)
    for proc in windows:
        if proc.poll() is None: proc.terminate();proc.wait(timeout=3)
    for original in original_outputs:
        if original['name']==args.monitor:
            pos=original['position'];subprocess.run(['wlr-randr','--output',args.monitor,'--scale',str(original['scale']),'--pos',f'{pos["x"]},{pos["y"]}'],check=True)
    for m in selected: view(m['name'],m['active_tags'][0])
    active=next(m for m in original_monitors if m['active']);dispatch('focusmon,'+active['name'])
    if original_hidden=='false' and subprocess.check_output(['arctic-shell-ipc','bar','hidden'],text=True).strip()=='true':
        subprocess.run(['arctic-shell-ipc','bar','toggleHidden'],check=True)
    pointer.stdin.write('quit\n');pointer.stdin.flush();pointer.wait(timeout=3)
    assert json.loads(subprocess.check_output(['wlr-randr','--json']))==original_outputs
    after=query('all-clients')['clients'];assert {(c['id'],c['pid']) for c in original_clients}<={(c['id'],c['pid']) for c in after}
    (args.out/'results.json').write_text(json.dumps(results,indent=2))
    print('Outputs, workspaces, installed bar and original application processes restored.',flush=True)
