#!/usr/bin/env python3
"""Explicit v4-derived extractor: only six exact sentinel .xkb paths are added."""
import base64,hashlib,json,re,zlib
from pathlib import Path
MAX_FILE=4*1024*1024
MAX_TOTAL=16*1024*1024
class Guard:
 @staticmethod
 def require(value,message):
  if not value:raise RuntimeError(message)
 @staticmethod
 def write_json(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
R=Guard()
def records(lines,prefix):
 return [json.loads(row[len(prefix):]) for row in lines if row.startswith(prefix)]

def extract_preflight(lines,stage,target):
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
                  and (Path(relative).suffix.lower() in ('.json','.png','.log','.txt','.tsv','.rgb') or
                       re.fullmatch(r'sentinel-(?:warm|cold)/producer-turn-[012]/uploaded-map\.xkb',relative)),
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
