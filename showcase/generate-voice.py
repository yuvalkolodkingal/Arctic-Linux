"""Generate sentence-aligned Kokoro narration and reproducible scene timing."""
import argparse
import json
import re
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--model', type=Path, default=Path.home()/'.cache/hyperframes/tts/models/kokoro-v1.0.onnx')
parser.add_argument('--voices', type=Path, default=Path.home()/'.cache/hyperframes/tts/voices/voices-v1.0.bin')
parser.add_argument('--voice', default='af_heart')
parser.add_argument('--speed', type=float, default=1.0)
args = parser.parse_args()
model = Kokoro(str(args.model), str(args.voices))
story = json.loads((ROOT/'storyboard.json').read_text())
cache = ROOT/'.hyperframes/voice'
cache.mkdir(parents=True, exist_ok=True)
(ROOT/'audio').mkdir(exist_ok=True)
rate = 24000
pieces = []
cursor = 0
captions = []
scenes = []

def append(samples):
    global cursor
    pieces.append(samples)
    cursor += len(samples)

def silence(seconds):
    append(np.zeros(round(seconds * rate), dtype=np.float32))

for scene in story:
    start = cursor / rate
    silence(0.8)
    sentences = re.split(r'(?<=[.!?])\s+', scene['narration'])
    for n, text in enumerate(sentences):
        key = f"{scene['id']}-{n}-{args.voice}-{args.speed}"
        p = cache/(key+'.npz')
        if p.exists():
            item = np.load(p)
            samples = item['samples'] if str(item['text']) == text else None
        else:
            samples = None
        if samples is None:
            samples, sr = model.create(text, voice=args.voice, speed=args.speed, lang='en-us')
            if sr != rate:
                raise RuntimeError(f'Unexpected sample rate {sr}')
            samples = np.asarray(samples, dtype=np.float32)
            # Remove generator padding while preserving a short natural lead/tail.
            active = np.flatnonzero(np.abs(samples) > 0.004)
            if len(active):
                samples = samples[max(0, active[0]-round(0.05*rate)):min(len(samples), active[-1]+round(0.12*rate))]
            np.savez_compressed(p, samples=samples, text=text)
        caption_start = cursor / rate
        append(samples)
        captions.append({'start':round(caption_start,3),'end':round(cursor/rate+0.16,3),'text':text,'scene':scene['id']})
        silence(0.23)
    silence(0.55)
    scenes.append({**scene,'start':round(start,3),'duration':round(cursor/rate-start,3)})
    print(f"{len(scenes):02d}/{len(story)} {scene['id']}: {cursor/rate-start:.1f}s", flush=True)

silence(1.2)
total = cursor / rate
audio = np.concatenate(pieces)
audio *= 0.9 / max(0.9,float(np.max(np.abs(audio))))
sf.write(ROOT/'.hyperframes/narration.wav', audio, rate, subtype='PCM_16')
subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(ROOT/'.hyperframes/narration.wav'),'-af','loudnorm=I=-16:TP=-1.5:LRA=9','-c:a','libmp3lame','-b:a','192k',str(ROOT/'audio/narration.mp3')],check=True)
(ROOT/'timing.json').write_text(json.dumps({'duration':round(total,3),'voice':args.voice,'speed':args.speed,'scenes':scenes,'captions':captions},indent=2)+'\n')
(ROOT/'narration.txt').write_text('\n\n'.join(s['narration'] for s in story)+'\n')

def stamp(t,comma=False):
    ms=round(t*1000)
    h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000)
    return f'{h:02}:{m:02}:{s:02}{"," if comma else "."}{ms:03}'

srt=[];vtt=['WEBVTT','']
for i,c in enumerate(captions,1):
    srt.extend([str(i),f"{stamp(c['start'],True)} --> {stamp(c['end'],True)}",c['text'],''])
    vtt.extend([f"{stamp(c['start'])} --> {stamp(c['end'])}",c['text'],''])
(ROOT/'captions.srt').write_text('\n'.join(srt))
(ROOT/'captions.vtt').write_text('\n'.join(vtt))
print(f'Total {total:.2f}s, {len(captions)} caption cues',flush=True)
