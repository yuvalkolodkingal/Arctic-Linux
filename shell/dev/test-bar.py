import argparse, json, pathlib, subprocess, time
import signal, sys
signal.signal(signal.SIGTERM,lambda *_: sys.exit(143))
signal.signal(signal.SIGHUP,lambda *_: sys.exit(129))
parser=argparse.ArgumentParser(description='Native Mango/Wayland acceptance checks for BarHarness.qml. Run against an isolated preview, with the installed bar hidden.')
parser.add_argument('--preview',required=True,type=pathlib.Path)
parser.add_argument('--pointer',required=True,type=pathlib.Path)
parser.add_argument('--out',required=True,type=pathlib.Path)
parser.add_argument('--monitor',required=True)
parser.add_argument('--other-monitor',required=True)
args=parser.parse_args()
args.out.mkdir(parents=True,exist_ok=True)
monitors=json.loads(subprocess.check_output(['mmsg','get','all-monitors']))['monitors']
primary=next(m for m in monitors if m['name']==args.monitor)
other=next(m for m in monitors if m['name']==args.other_monitor)
extentW=max(m['x']+m['width'] for m in monitors)
extentH=max(m['y']+m['height'] for m in monitors)
center=(primary['x']+primary['width']//2, primary['y']+primary['height']//2)
barMiddleY=primary['y']+int(primary['height']*.6)
preview=str(args.preview)
log=[]
class TestPointer:
    def __init__(self):
        self.proc=subprocess.Popen([str(args.pointer)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        assert self.proc.stdout.readline().strip()=='READY'
    def send(self,cmd):
        self.proc.stdin.write(cmd+'\n');self.proc.stdin.flush()
        assert self.proc.stdout.readline().strip()=='OK'
    def move(self,x,y): self.send(f'move {x} {y} {extentW} {extentH}')
    def button(self,state): self.send(f'button {state}')
    def close(self): self.proc.stdin.write('quit\n');self.proc.stdin.flush();self.proc.wait(timeout=3)
def ipc(*args):
    out=subprocess.check_output(['quickshell','ipc','-p',preview,'call','testbar',*map(str,args)],text=True).strip()
    return out
def state(name=args.monitor): return next(b for b in json.loads(ipc('state')) if b['screen']==name)
def record(name,value):
    log.append({'test':name,'value':value});print(name, json.dumps(value),flush=True)
def shot(name): subprocess.run(['grim','-o',args.monitor,str(args.out/f'{name}.png')],check=True)
def configure(edge,size,hide):
    ipc('configure',edge,size,str(hide).lower()); time.sleep(1.1)
def point(edge,monitor=args.monitor):
    m=next(m for m in monitors if m['name']==monitor)
    return {'left':(m['x'],m['y']+m['height']//2),
            'right':(m['x']+m['width']-1,m['y']+m['height']//2),
            'top':(m['x']+m['width']//2,m['y']),
            'bottom':(m['x']+m['width']//2,m['y']+m['height']-1)}[edge]
def trace(name,seconds=.45):
    points=[];until=time.monotonic()+seconds
    while time.monotonic()<until:
        s=state();points.append(round(s['reveal'],3));time.sleep(.015)
    record(name,points);return points
p=TestPointer()
try:
    p.move(*center);ipc('close');ipc('motion','false')
    for edge,size in [('right',32),('left',32),('left',56),('right',56),('left',28)]:
        configure(edge,size,False)
        s=state()
        assert s['width']==size and s['height']==primary['height'],s
        for item in s['stops']:
            assert item['x']>=0 and item['x']+item['width']<=size+.1,(edge,size,item)
        shot(f'after-{edge}-{size}')
        ipc('focus',args.monitor);subprocess.run(['wtype','-k','End','-k','End'],check=True);time.sleep(.2)
        focused=state()['focused'];assert focused['y']>=0 and focused['y']+focused['height']<=primary['height'],focused
        subprocess.run(['wtype','-k','Home','-k','Home'],check=True);ipc('focus',args.monitor);time.sleep(.2)
        record(f'layout-{edge}-{size}',{'controls':len(s['stops']),'powerVisibleAfterEnd':focused})
    for edge in ['right','left','top','bottom']:
        p.move(*center);configure(edge,32,True)
        assert state()['reveal']==0,state()
        p.move(*point(edge));opening=trace(f'reveal-{edge}');s=state()
        assert s['reveal']==1 and s['heldOpen'],s
        shot(f'auto-{edge}-revealed')
        p.move(*center);time.sleep(.45);assert state()['expanded'],state()
        time.sleep(.28);closing=trace(f'hide-{edge}')
        assert state()['reveal']==0,state()
        shot(f'auto-{edge}-hidden')
        assert any(0<x<1 for x in opening+closing),'No animation samples'
        for _ in range(3):
            p.move(*point(edge));time.sleep(.28);assert state()['reveal']==1
            p.move(*center);time.sleep(.3);assert state()['expanded']
        time.sleep(.9);assert state()['reveal']==0
        record(f'edge-{edge}','delayed hide and repeated reveal pass')
    configure('right',32,True);p.move(*point('right'));time.sleep(.3)
    s=state();p.move(primary['x']+primary['width']-16, primary['y']+int(s['anchors']['calendar']));p.button(1);p.button(0);time.sleep(.4)
    assert state()['popup'] is not None,state()
    p.move(*center);time.sleep(1.1)
    assert state()['expanded'] and state()['popupHere'],state()
    shot('right-calendar-popup');record('click-popup-pins-bar',state()['popup'])
    ipc('close');time.sleep(1.1);assert state()['reveal']==0
    ipc('separate',args.monitor);time.sleep(1)
    assert state()['expanded'] and state()['popupHere'],state()
    record('separate-host-pins-bar','pass');ipc('close');time.sleep(1.1);assert state()['reveal']==0
    p.move(*point('right'));time.sleep(.3);p.move(primary['x']+primary['width']-16,barMiddleY);p.button(1);p.move(*center);time.sleep(1.1)
    assert state()['expanded'] and state()['heldOpen'],state()
    record('press-outside-keeps-bar','pass');p.button(0);time.sleep(1.1);assert state()['reveal']==0
    p.move(other['x']+other['width']-16,other['y']+int(other['height']*.65));p.button(1);time.sleep(.1)
    assert not state(args.other_monitor)['heldOpen'],state(args.other_monitor)
    p.button(0);record('hidden-surface-click-through','bar receives no hover/press outside 3px trigger')
    p.move(*point('right',args.other_monitor));time.sleep(.4)
    assert state(args.other_monitor)['reveal']==1 and state()['reveal']==0
    record('independent-monitor-edge-reveal','pass')
    p.move(*center);time.sleep(1.1)
    ipc('focus',args.monitor);time.sleep(.4);assert state()['expanded'];record('keyboard-reveal','pass');ipc('focus',args.monitor);time.sleep(1.1)
    ipc('motion','true');p.move(*point('right'));time.sleep(.05);assert state()['reveal']==1
    p.move(*center);time.sleep(.75);assert state()['reveal']==0
    record('reduced-motion','instant reveal/hide pass');ipc('motion','false')
    configure('left',56,False);ipc('recording','true');time.sleep(.3)
    s=state();assert any(i['label'].startswith('Recording ') for i in s['stops'])
    assert all(i['x']>=0 and i['x']+i['width']<=56 for i in s['stops'])
    ipc('focus',args.monitor);subprocess.run(['wtype','-k','End','-k','End'],check=True);time.sleep(.2)
    focused=state()['focused'];assert focused['y']>=0 and focused['y']+focused['height']<=primary['height']
    shot('after-left-56-scrolled');ipc('focus',args.monitor);ipc('recording','false')
    record('recording-widget-and-overflow','pass with in-memory recording fixture')
finally:
    try:
        ipc('reset')
    finally:
        try:
            p.close()
            (args.out/'runtime-results.json').write_text(json.dumps(log,indent=2))
        finally:
            subprocess.run(['quickshell','kill','-p',preview],check=False)
