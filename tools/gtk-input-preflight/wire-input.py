#!/usr/bin/env python3
"""Strict finite Wayland producer command proof; never generates input."""
import hashlib,re
TEXT='Arctic isolated GTK3 entry'
def require(value,message):
 if not value:raise RuntimeError(message)
def expected(turn,warm):
 symbols=[];messages=[]
 def key(sym):
  if sym not in symbols:symbols.append(sym)
  code=symbols.index(sym)+1
  messages.extend([('key',0,code,1),('key',0,code,0)])
 if warm:key('Shift_L')
 if turn==0:
  messages.append(('modifiers',4,0,0,0));key('a');messages.append(('modifiers',0,0,0,0))
 elif turn==1:
  for char in TEXT:key(char)
 elif turn==2:key('Return')
 else:raise RuntimeError('finite literal turn differs')
 return symbols,messages
def parse(data,turn,warm,corrected,producer=None):
 require(type(data) is bytes and 0<len(data)<=65536 and data.endswith(b'\n'),'wire raw stderr bound/framing differs')
 text=data.decode('utf-8','strict');rows=text[:-1].split('\n')
 require(len(rows)<=2048,'wire record count exceeded')
 for row in rows:
  require(re.fullmatch(r'\[\d{2}:\d{2}:\d{2}\.\d{6}\] \{(?:Default|Display) Queue\} .+',row),
          'unexpected stderr outside qualified Wayland-debug framing')
 creations=re.findall(r' -> zwp_virtual_keyboard_manager_v1#\d+\.create_virtual_keyboard\(wl_seat#\d+, new id zwp_virtual_keyboard_v1#(\d+)\)',text)
 require(len(creations)==1,'one owned virtual keyboard creation required')
 object_id=creations[0];prefix='zwp_virtual_keyboard_v1#'+object_id
 all_requests=re.findall(r' -> (zwp_virtual_keyboard_v1#\d+)\.(\w+)\(([^\n]*)\)',text)
 require(all(target==prefix for target,_,_ in all_requests),'foreign/ambiguous virtual producer')
 maps=[];actual=[];destroy=0;seen_key=False
 for target,method,args in all_requests:
  if method=='keymap':
   require(not seen_key and not maps and re.fullmatch(r'1, fd \d+, \d+',args),'wire keymap format/order differs')
   maps.append(int(args.rsplit(', ',1)[1]))
  elif method in ('key','modifiers'):
   require(len(maps)==1 and destroy==0 and re.fullmatch(r'\d+(?:, \d+){'+('2' if method=='key' else '3')+'}',args),'wire numeric request/order differs')
   seen_key=True;actual.append((method,*map(int,args.split(', '))))
  elif method=='destroy':
   require(args=='' and destroy==0,'wire destruction differs');destroy+=1
  else:raise RuntimeError('unknown virtual input request')
 symbols,messages=expected(turn,warm)
 require(actual==messages and len(maps)==1 and maps[0]>0 and destroy==1,'wire emitted keys/modifiers differ from literal source command')
 require('wl_display#1.get_registry(' in text and '"zwp_virtual_keyboard_manager_v1"' in text and '"wl_seat"' in text,
         'actual registry/seat/virtual initialization unavailable')
 if corrected:
  require(producer is not None and producer['identity']['map_bytes']==maps[0]
          and producer['identity']['maximum']==len(symbols)+9 and producer['identity']['last_emitted_named_code']==len(symbols)+8,
          'wire upload size/compiled producer endpoint differs')
  if turn==2:
   code=symbols.index('Return')+9
   require(producer['identity']['return_codes']==[dict(keycode=code,group=0,level=0)],'wire Return does not pair with map endpoint')
 return dict(raw_bytes=len(data),raw_sha256=hashlib.sha256(data).hexdigest(),virtual_object_id=object_id,
             keymap_upload_bytes=maps[0],symbols=symbols,emissions=[list(x) for x in actual],destroy_count=destroy,
             scope='actual producer wire requests; not compositor delivery or private GTK binding proof')
