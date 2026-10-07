#!/usr/bin/env python3
"""Fail-closed proof pairing for the private producer and natural Gtk activation."""
import hashlib,json,math,re,stat
from pathlib import Path
def require(value,message):
 if not value:raise RuntimeError(message)
def strict_json(data):
 def pairs(items):
  result={}
  for key,value in items:
   require(key not in result,'duplicate JSON key');result[key]=value
  return result
 return json.loads(data,object_pairs_hook=pairs,parse_constant=lambda x: (_ for _ in ()).throw(RuntimeError('nonfinite JSON')))
def regular(path,maximum):
 info=path.lstat()
 require(stat.S_ISREG(info.st_mode) and info.st_size<=maximum,'regular bounded proof file required')
 return path.read_bytes()
def producer(root,expected_binary,source_pair,argv,uid,map_only=False):
 data=strict_json(regular(root/'producer-identity.json',65536))
 require(data['schema']=='arctic-private-input-v1' and data['source_sha256']==source_pair
         and type(data['map_only']) is bool and data['map_only'] is map_only and data['argv']==argv,'producer CLI/source differs')
 for key in ('pid','uid','gid','monotonic_ns','minimum','maximum','last_emitted_named_code','sentinel','map_bytes'):
  require(type(data[key]) is int and data[key]>=0,'producer integer type differs')
 require(data['pid']>1 and data['uid']==uid and data['monotonic_ns']>0 and data['minimum']==9
         and data['last_emitted_named_code']+1==data['maximum']==data['sentinel']
         and data['maximum']<=4105,'producer endpoint differs')
 raw_stat=regular(root/'producer-stat.txt',262144).decode('utf-8','strict')
 require(raw_stat.split(' ',1)[0]==str(data['pid']) and ')' in raw_stat,'producer PID differs')
 start=int(raw_stat[raw_stat.rindex(')')+2:].split()[19]);require(start>0,'producer start identity absent')
 raw=regular(root/'uploaded-map.xkb',262144)
 require(raw.endswith(b'\0') and b'\0' not in raw[:-1] and len(raw)==data['map_bytes'],'map framing/size differs')
 require(raw.count(b'<ARCTIC_UNUSED> = ')==1 and
         ('<ARCTIC_UNUSED> = %d;'%data['sentinel']).encode() in raw and b'key <ARCTIC_UNUSED>' not in raw,
         'named unused sentinel differs')
 returns=data['return_codes'];require(isinstance(returns,list) and len(returns)<=64,'Return enumeration malformed')
 for entry in returns:
  require(set(entry)=={'keycode','group','level'} and all(type(v) is int and v>=0 for v in entry.values())
          and 9<=entry['keycode']<data['sentinel'],'Return at excluded endpoint')
 mapped=[]
 for line in regular(root/'producer-maps.txt',262144).decode('utf-8','strict').splitlines():
  fields=line.split(maxsplit=5)
  if len(fields)<6 or not fields[5].startswith('/'):continue
  path=fields[5];require(not path.endswith(' (deleted)') and '\\' not in path,'mapped identity unavailable')
  if path not in mapped:mapped.append(path)
 require(str(expected_binary) in mapped and all(any(Path(p).name.startswith(n) for p in mapped)
         for n in ('libxkbcommon.so.','libwayland-client.so.','libc.so.','ld-linux-')),'producer mapped ELF set differs')
 return dict(identity=data,start_ticks=start,map_sha256=hashlib.sha256(raw).hexdigest(),mapped_files=mapped,
             endpoint_scope='exact uploaded producer map; no private GDK map pointer observation')
def natural_activation(rows,proof,uid,text,corrected,return_map=None):
 require(isinstance(rows,list) and len(rows)<=4096,'GTK event bound differs')
 for row in rows:
  require(isinstance(row,dict) and type(row.get('monotonic_ns')) is int and row['monotonic_ns']>0
          and row.get('pid')==proof['pid'] and row.get('start_ticks')==proof['start_ticks']
          and type(row.get('uid')) is int and row['uid']==uid,'GTK row identity differs')
 keys=[r for r in rows if r.get('event')=='key-press' and r.get('keyval')==65293]
 activations=[r for r in rows if r.get('event')=='activate']
 require(len(keys)==1,'exactly one natural Return key press required')
 key=keys[0];current=key['current_map'];translated=current['event_current_translation']
 require(key.get('has_focus') is True and key.get('is_focus') is True and key.get('text')==text
         and type(key['state']) is int and key['state']==0 and type(key['hardware_keycode']) is int
         and type(key['group']) is int and 0<=key['group']<=3
         and translated['valid'] is True and type(translated['keyval']) is int and translated['keyval']==65293
         and type(translated['level']) is int and translated['level']>=0,'actual Return/focus/text differs')
 if corrected:
  require(isinstance(current['return_entries'],list) and len(current['return_entries'])<=64
          and all(isinstance(e,dict) and set(e)=={'keycode','group','level'}
                  and all(type(v) is int and v>=0 for v in e.values()) for e in current['return_entries']),
          'current reverse entry integer types differ')
  require(return_map is not None and current['return_entries_valid'] is True
          and dict(keycode=key['hardware_keycode'],group=key['group'],level=translated['level']) in current['return_entries']
          and dict(keycode=key['hardware_keycode'],group=key['group'],level=translated['level']) in return_map,
          'current reverse Return entry does not pair with uploaded endpoint map')
 require(len(activations)<=1,'multiple natural activations')
 if activations:
  item=activations[0]
  require(item.get('count')==1 and type(item['count']) is int and item.get('has_focus') is True
          and item.get('text')==text and item['monotonic_ns']>=key['monotonic_ns'],'natural activation evidence differs')
 return dict(status='natural-entry-activated' if activations else 'entry-not-activated',key=key,
             activation=activations[0] if activations else None,native_qualification=False)
