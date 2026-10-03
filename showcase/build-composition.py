"""Build a self-contained HyperFrames composition from the storyboard and timing."""
import argparse
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--static', action='store_true', help='Build end-state layout before animation')
args=parser.parse_args()
timing_path=ROOT/'timing.json'
if timing_path.exists():
    timing=json.loads(timing_path.read_text())
else:
    story=json.loads((ROOT/'storyboard.json').read_text())
    timing={'duration':len(story)*12,'scenes':[{**s,'start':i*12,'duration':12} for i,s in enumerate(story)],'captions':[]}
scenes=timing['scenes']
escape=html.escape

css='''
@font-face{font-family:Figtree;src:url(assets/Figtree-400.woff2);font-weight:400}
@font-face{font-family:Figtree;src:url(assets/Figtree-500.woff2);font-weight:500}
@font-face{font-family:Figtree;src:url(assets/Figtree-600.woff2);font-weight:600}
@font-face{font-family:Figtree;src:url(assets/Figtree-700.woff2);font-weight:700}
@font-face{font-family:'JetBrains Mono';src:url(assets/JetBrainsMono-400.woff2);font-weight:400}
*{box-sizing:border-box}body{margin:0;width:1920px;height:1080px;overflow:hidden;font-family:Figtree,sans-serif;background:#12171e}
#arctic-showcase{position:relative;width:1920px;height:1080px;overflow:hidden;color:#e9eef3}
.scene{position:absolute;inset:0;width:1920px;height:1080px;background:#12171e;opacity:0}
.scene:first-child{opacity:1}
.scene.light{background:#eef2f5;color:#151a21}
.scene-content{width:100%;height:100%;padding:44px 72px 220px;display:flex;flex-direction:column;gap:30px}
.brand-bar{display:flex;align-items:center;justify-content:space-between;height:48px;flex-shrink:0;color:#aeb9c5}
.brand{display:flex;align-items:center;gap:15px;font-size:28px;letter-spacing:-.02em;color:#e9eef3}
.brand svg{width:44px;height:44px;object-fit:contain}.brand strong{font-weight:600}.brand span{font-weight:400;color:#aeb9c5}
.chapter-count{font-family:'JetBrains Mono',monospace;font-size:20px;font-variant-numeric:tabular-nums;letter-spacing:.02em}
.main{display:flex;align-items:center;gap:56px;flex:1;min-height:0;width:100%}
.copy{display:flex;flex-direction:column;gap:22px;width:458px;flex-shrink:0;max-height:100%}
.chapter{margin:0;color:#aeb9c5;font-size:24px;line-height:1.4;font-weight:500}
h1{margin:0;font-size:68px;line-height:1.05;letter-spacing:-.025em;font-weight:600;overflow-wrap:normal}
.body{margin:0;font-size:30px;line-height:1.4;color:#aeb9c5;max-width:440px}
.shortcut{margin-top:5px;border:1px solid #6b7a8a;border-radius:14px;padding:14px 18px;background:#1a212a;color:#e9eef3;font-family:'JetBrains Mono',monospace;font-size:22px;line-height:1.6;max-width:458px;overflow-wrap:anywhere}
.tag{font-size:21px;color:#c9bcad;line-height:1.4;margin-top:6px}
.media{flex:1;min-width:0;height:100%;display:flex;align-items:center;justify-content:center}
.screen{display:block;max-width:100%;max-height:100%;width:auto;height:auto;object-fit:contain;border-radius:18px;border:1px solid #6b7a8a;box-shadow:0 18px 60px #00000026}
.detail .screen{width:100%;height:auto}\n.light .brand,.light .shortcut{color:#151a21}.light .brand span,.light .brand-bar,.light .chapter,.light .body{color:#4a5663}.light .shortcut{background:#fbfcfd;border-color:#7c8a99}.light .screen{border-color:#7c8a99}
.hero h1{font-size:83px}.hero .copy{width:530px}.hero .body{max-width:510px}.hero .main{gap:40px}
.outro h1{font-size:80px}.outro .shortcut{font-size:20px}
.app-grid{display:grid;grid-template-columns:1fr 1fr;gap:24px;width:100%;max-width:1100px}
.app-card{display:flex;flex-direction:column;gap:22px;padding:36px;background:#1a212a;border:1px solid #6b7a8a;border-radius:20px;min-height:245px}
.app-symbol{font-family:'JetBrains Mono',monospace;font-size:24px;color:#aeb9c5}.app-name{font-size:44px;font-weight:600;line-height:1.1}.app-use{font-size:26px;color:#aeb9c5;line-height:1.4}
.caption{position:absolute;left:136px;bottom:70px;width:1648px;min-height:110px;display:flex;align-items:center;justify-content:center;text-align:center;color:#e9eef3;background:#12171e;padding:12px 24px;border-radius:14px;font-size:29px;line-height:1.4;z-index:100;}
.caption-text{max-width:1550px}
.progress-track{position:absolute;bottom:32px;left:72px;width:1776px;height:3px;background:#2f3945;z-index:110}
.progress-fill{width:100%;height:100%;background:#f6bd55;transform-origin:left center}
.footer-note{position:absolute;bottom:38px;left:72px;color:#aeb9c5;font-size:17px;line-height:1.2;z-index:110}
'''
markup=[]
for i,s in enumerate(scenes):
    classes=['scene']
    if s.get('theme')=='light':classes.append('light')
    if s.get('crop') and s['crop'][2]>s['crop'][3]:classes.append('detail')
    if s.get('type') in ['hero','outro']:classes.append(s['type'])
    mark='winter' if s.get('theme')=='light' else 'polar-night'
    logo=(ROOT/'assets'/f'arctic-mark-{mark}.svg').read_text()
    extra=''
    if s.get('shortcut'):extra+=f'<div class="shortcut entrance-key">{escape(s["shortcut"])}</div>'
    if s.get('tag'):extra+=f'<div class="tag entrance-tag">{escape(s["tag"])}</div>'
    if s.get('type')=='apps':
        apps=[('01 · Browse','Zen','A browser for your everyday web.'),('02 · Create','Zed','An editor for code and projects.'),('03 · Write','Collabora Office','Documents, sheets, and slides.'),('04 · Play','VLC','Video and music, at your desk.')]
        media='<div class="app-grid">'+''.join(f'<div class="app-card entrance-card"><div class="app-symbol">{escape(k)}</div><div class="app-name">{escape(n)}</div><div class="app-use">{escape(d)}</div></div>' for k,n,d in apps)+'</div>'
    else:
        media=f'<img class="screen entrance-screen" src="assets/{s["id"]}.png" alt="{escape(s["title"])}">'
    markup.append(f'''<section id="scene-{s['id']}" class="{' '.join(classes)}" aria-label="{escape(s['title'])}">
      <div class="scene-content">
        <div class="brand-bar entrance-brand"><div class="brand">{logo}<strong>arctic <span>linux</span></strong></div><div class="chapter-count">{i+1:02} / {len(scenes):02}</div></div>
        <div class="main"><div class="copy"><p class="chapter entrance-chapter">{escape(s['chapter'])}</p><h1 class="entrance-title">{escape(s['title'])}</h1><p class="body entrance-body">{escape(s['body'])}</p>{extra}</div><div class="media">{media}</div></div>
      </div>
    </section>''')
captions=[]
for i,c in enumerate(timing['captions']):
    # Captions use their own timed lane. The framework handles visibility at
    # each exact cue boundary, with a short GSAP entrance.
    captions.append(f'<div id="caption-{i}" class="caption clip" data-start="{c["start"]}" data-duration="{round(c["end"]-c["start"],3)}" data-track-index="2"><span class="caption-text">{escape(c["text"])}</span></div>')
script=''
if not args.static:
    script=f'''
const scenes={json.dumps([{'id':s['id'],'start':s['start'],'duration':s['duration']} for s in scenes])};
const cues={json.dumps(timing['captions'])};
const tl=gsap.timeline({{paused:true}});
scenes.forEach((scene,i)=>{{
  const sel='#scene-'+scene.id;
  const t=scene.start;
  tl.set('.footer-note',{{color:scene.id==='winter'?'#4a5663':'#aeb9c5'}},t+.6);
  if(i>0){{
    // Scene crossfade is the transition; scene contents never exit early.
    tl.to('#scene-'+scenes[i-1].id,{{opacity:0,duration:.6,ease:'sine.inOut'}},t);
    tl.to(sel,{{opacity:1,duration:.6,ease:'sine.inOut'}},t);
  }}
  tl.from(sel+' .entrance-brand',{{opacity:0,duration:.42,ease:'sine.out'}},t+.12);
  tl.from(sel+' .entrance-chapter',{{opacity:0,y:4,duration:.45,ease:'power1.out'}},t+.18);
  tl.from(sel+' .entrance-title',{{opacity:0,y:8,duration:.58,ease:'power3.out'}},t+.23);
  tl.from(sel+' .entrance-body',{{opacity:0,x:-6,duration:.5,ease:'power2.out'}},t+.37);
  if(document.querySelector(sel+' .entrance-key'))tl.from(sel+' .entrance-key',{{opacity:0,y:5,duration:.45,ease:'sine.out'}},t+.49);
  if(document.querySelector(sel+' .entrance-tag'))tl.from(sel+' .entrance-tag',{{opacity:0,duration:.4,ease:'power1.out'}},t+.58);
  if(document.querySelector(sel+' .entrance-screen'))tl.from(sel+' .entrance-screen',{{opacity:0,x:8,duration:.65,ease:'power2.out'}},t+.27);
  if(document.querySelector(sel+' .entrance-card'))tl.from(sel+' .entrance-card',{{opacity:0,y:8,duration:.55,stagger:.13,ease:'power3.out'}},t+.35);
}});
cues.forEach((c,i)=>{{
  tl.from('#caption-'+i,{{y:4,duration:.14,ease:'sine.out'}},c.start);
  tl.set('#caption-'+i,{{opacity:0}},c.end);
}});
tl.from('.footer-note',{{opacity:0,duration:.5,ease:'sine.out'}},.2);
tl.from('.progress-fill',{{scaleX:0,duration:{timing['duration']},ease:'none'}},0);
tl.to('#scene-{scenes[-1]['id']}',{{opacity:0,duration:.85,ease:'sine.inOut'}},{timing['duration']-.85});
window.__timelines=window.__timelines||{{}};
window.__timelines['arctic-showcase']=tl;
'''
audio='' if args.static else f'<audio id="narration" src="audio/narration.mp3" data-start="0" data-duration="{timing["duration"]}" data-track-index="3" data-volume="1"></audio>'
page=f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Arctic Linux — installer and daily-use showcase</title><script src="assets/gsap.min.js"></script><style>{css}</style></head>
<body><div id="arctic-showcase" data-composition-id="arctic-showcase" data-width="1920" data-height="1080" data-start="0" data-duration="{timing['duration']}" data-fps="30">
{''.join(markup)}
{''.join(captions) if not args.static else ''}
<div class="footer-note">Arctic Linux · Installer and daily-use showcase</div><div class="progress-track" data-layout-ignore><div class="progress-fill"></div></div>
{audio}
</div><script>{script}</script></body></html>'''
dest=ROOT/('.hyperframes/layout.html' if args.static else 'index.html')
dest.parent.mkdir(exist_ok=True)
if args.static:
    # Keep assets resolvable from the temporary layout file.
    page=page.replace('assets/','../assets/')
dest.write_text(page)
print(f'Built {dest.name}: {len(scenes)} scenes, {timing["duration"]:.2f}s')
