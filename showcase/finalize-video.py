"""Add English subtitles, chapter metadata, and fast-start playback to the MP4."""
import argparse
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('video',nargs='?',type=Path,default=ROOT/'renders/Arctic-Linux-Showcase-1080p.mp4')
args=parser.parse_args()
timing=json.loads((ROOT/'timing.json').read_text())
entries=[];previous=None
for scene in timing['scenes']:
    if scene['chapter']!=previous:
        entries.append((round(scene['start']*1000),scene['chapter']))
        previous=scene['chapter']
metadata=[';FFMETADATA1','title=Arctic Linux — installer and daily-use showcase','artist=Arctic Linux','comment=HyperFrames showcase using authentic repository screenshots; installer details are demo data.']
for i,(start,title) in enumerate(entries):
    end=entries[i+1][0] if i+1<len(entries) else round(timing['duration']*1000)
    metadata.extend(['[CHAPTER]','TIMEBASE=1/1000',f'START={start}',f'END={end}',f'title={title}'])
(ROOT/'.hyperframes').mkdir(exist_ok=True)
meta=ROOT/'.hyperframes/chapters.ffmeta'
meta.write_text('\n'.join(metadata)+'\n')
output=args.video.with_name(args.video.stem+'-final.mp4')
subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(args.video),'-i',str(ROOT/'captions.srt'),'-i',str(meta),'-map','0:v','-map','0:a','-map','1:0','-map_metadata','2','-map_chapters','2','-c:v','copy','-c:a','copy','-c:s','mov_text','-metadata:s:s:0','language=eng','-metadata:s:s:0','title=English captions','-movflags','+faststart',str(output)],check=True)
output.replace(args.video)
print(args.video)
