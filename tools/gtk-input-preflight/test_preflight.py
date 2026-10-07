#!/usr/bin/env python3
import copy,ctypes,hashlib,importlib.util,json,os,re,subprocess,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
def load(name):
 spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'));mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
G=load('generate-helper');P=load('preflight-proof')
def function(text,name):
 match=re.search(r'^(?:static )?(?:void|int|unsigned int) '+name+r'\([^;]*?\)\n\{',text,re.M)
 if not match:raise RuntimeError('function unavailable '+name)
 start=match.start();end=match.end();depth=1
 while depth:
  if text[end]=='{':depth+=1
  elif text[end]=='}':depth-=1
  end+=1
 return text[start:end]
class Source(unittest.TestCase):
 def test_exact_reproduction(self):self.assertEqual(G.generate((HERE/'original-wtype-v0.4.c').read_bytes()),(HERE/'sentinel-wtype.c').read_bytes())
 def test_changed_base_rejected(self):
  with self.assertRaises(ValueError):G.generate((HERE/'original-wtype-v0.4.c').read_bytes()+b'\n')
 def test_all_emitted_input_functions_exact(self):
  original=(HERE/'original-wtype-v0.4.c').read_text();changed=(HERE/'sentinel-wtype.c').read_text()
  for name in ('parse_args','append_keymap_entry','run_sleep','run_mod','run_key','type_keycode','run_text','run_text_stdin','run_commands','print_keysym_name'):
   self.assertEqual(function(original,name),function(changed,name),name)
 def test_original_main_emission_suffix_exact(self):
  original=(HERE/'original-wtype-v0.4.c').read_text();changed=(HERE/'sentinel-wtype.c').read_text()
  self.assertEqual(original[original.index('\twtype.display ='):],changed[changed.index('\twtype.display ='):])
 def test_no_sentinal_emitted_command_or_symbol(self):
  changed=(HERE/'sentinel-wtype.c').read_text()
  self.assertEqual(changed.count('ARCTIC_UNUSED'),1)
  self.assertNotIn('key <ARCTIC_UNUSED>',changed)
 def test_guest_has_no_physical_or_activation_call(self):
  text=(HERE/'guest-preflight.py').read_text()
  for term in ('qmp','gtk_physical','setenv','GTK_IM_MODULE','emit("activate"','emit(\'activate\''):
   self.assertNotIn(term,text)
class Oracle(unittest.TestCase):
 def fixture(self):
  process=dict(pid=22,start_ticks=123);uid=1000;text='Arctic isolated GTK3 entry'
  entry=dict(keycode=10,group=0,level=0)
  common=dict(pid=22,start_ticks=123,uid=1000)
  key=dict(common,event='key-press',monotonic_ns=100,keyval=65293,hardware_keycode=10,state=0,
           group=0,has_focus=True,is_focus=True,text=text,current_map=dict(return_entries_valid=True,return_entries=[entry],
             event_current_translation=dict(valid=True,keyval=65293,level=0)))
  activate=dict(common,event='activate',monotonic_ns=101,count=1,has_focus=True,text=text)
  return [key,activate],process,uid,text,[entry]
 def test_positive_natural_oracle(self):
  rows,p,u,t,m=self.fixture();self.assertEqual(P.natural_activation(rows,p,u,t,True,m)['status'],'natural-entry-activated')
 def test_original_failure_retained(self):
  rows,p,u,t,m=self.fixture();rows=rows[:1];rows[0]['current_map']['return_entries_valid']=False;rows[0]['current_map']['return_entries']=[]
  self.assertEqual(P.natural_activation(rows,p,u,t,False)['status'],'entry-not-activated')
 def test_reverse_entry_and_identity_adversarial(self):
  rows,p,u,t,m=self.fixture()
  for path,value in [('has_focus',False),('is_focus',False),('state',1),('pid',23),('start_ticks',124),('text','wrong'),('monotonic_ns',-1)]:
   changed=copy.deepcopy(rows);changed[0][path]=value
   with self.subTest(path=path),self.assertRaises(RuntimeError):P.natural_activation(changed,p,u,t,True,m)
  for valid,entries in [(False,[]),(True,[dict(keycode=36,group=0,level=0)])]:
   changed=copy.deepcopy(rows);changed[0]['current_map'].update(return_entries_valid=valid,return_entries=entries)
   with self.assertRaises(RuntimeError):P.natural_activation(changed,p,u,t,True,m)
 def test_no_synthetic_or_duplicate_activation_acceptance(self):
  rows,p,u,t,m=self.fixture()
  for change in ('before','wrongtext','duplicate'):
   changed=copy.deepcopy(rows)
   if change=='before':changed[1]['monotonic_ns']=99
   elif change=='wrongtext':changed[1]['text']='wrong'
   else:changed.append(changed[1])
   with self.assertRaises(RuntimeError):P.natural_activation(changed,p,u,t,True,m)
 def test_json_duplicates_nonfinite(self):
  for raw in (b'{"a":1,"a":2}',b'{"a":NaN}'):
   with self.assertRaises(RuntimeError):P.strict_json(raw)
class RealMap(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.binary=Path(os.environ.get('ARCTIC_PREFLIGHT_BINARY',''))
  if not cls.binary.is_file():raise unittest.SkipTest('real private Fedora ELF execution requires explicit audit binary path')
  cls.lib=ctypes.CDLL('libxkbcommon.so.0')
  cls.lib.xkb_context_new.argtypes=[ctypes.c_int];cls.lib.xkb_context_new.restype=ctypes.c_void_p
  cls.lib.xkb_keymap_new_from_string.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_int,ctypes.c_int];cls.lib.xkb_keymap_new_from_string.restype=ctypes.c_void_p
  for name in ('min','max'):
   fn=getattr(cls.lib,'xkb_keymap_'+name+'_keycode');fn.argtypes=[ctypes.c_void_p];fn.restype=ctypes.c_uint
  cls.lib.xkb_keymap_unref.argtypes=[ctypes.c_void_p];cls.lib.xkb_context_unref.argtypes=[ctypes.c_void_p]
 def endpoint(self,raw):
  ctx=self.lib.xkb_context_new(0);self.assertTrue(ctx)
  map=self.lib.xkb_keymap_new_from_string(ctx,raw,1,0);self.assertTrue(map)
  try:return self.lib.xkb_keymap_min_keycode(map),self.lib.xkb_keymap_max_keycode(map)
  finally:self.lib.xkb_keymap_unref(map);self.lib.xkb_context_unref(ctx)
 def invoke(self,args):
  temp=tempfile.TemporaryDirectory(prefix='sentinel-control-');path=Path(temp.name)
  result=subprocess.run([str(self.binary),'--arctic-map-only',str(path),'--',*args],capture_output=True,timeout=5)
  return temp,path,result
 def test_actual_cold_warm_and_text_endpoint(self):
  for args in (['-k','Return'],['-s','200','-k','Shift_L','-s','150','-k','Return'],['spaced fixture'],['-M','ctrl','-k','a','-m','ctrl']):
   temp,path,result=self.invoke(args)
   try:
    self.assertEqual(result.returncode,0,result.stderr)
    data=json.loads((path/'producer-identity.json').read_text());raw=(path/'uploaded-map.xkb').read_bytes()
    self.assertEqual(self.endpoint(raw),(9,data['sentinel']))
    original=re.sub(rb'<ARCTIC_UNUSED> = [0-9]+;\n',b'',raw)
    self.assertEqual(self.endpoint(original),(9,data['last_emitted_named_code']))
    if args[-1]=='Return':
     code=data['return_codes'][0]['keycode'];self.assertEqual(code,data['last_emitted_named_code'])
     self.assertLess(code,data['sentinel']);self.assertFalse(code<data['last_emitted_named_code'])
   finally:temp.cleanup()
 def test_actual_cli_bound_unused_directory_and_nul_proof(self):
  with tempfile.TemporaryDirectory(prefix='sentinel-negative-') as t:
   path=Path(t)
   for command in ([str(self.binary)], [str(self.binary),'--arctic-map-only',t,'wrong','-k','Return'],
       [str(self.binary),'--arctic-map-only','relative','--','-k','Return']):
    self.assertNotEqual(subprocess.run(command,capture_output=True,timeout=5).returncode,0)
   path.chmod(0o755)
   self.assertNotEqual(subprocess.run([str(self.binary),'--arctic-map-only',t,'--','-k','Return'],capture_output=True,timeout=5).returncode,0)
   path.chmod(0o700)
   (path/'uploaded-map.xkb').write_bytes(b'old')
   self.assertNotEqual(subprocess.run([str(self.binary),'--arctic-map-only',t,'--','-k','Return'],capture_output=True,timeout=5).returncode,0)
 def test_real_producer_pair_and_adverse_proof(self):
  temp,path,result=self.invoke(['-k','Return'])
  try:
   self.assertEqual(result.returncode,0,result.stderr)
   argv=[str(self.binary),'--arctic-map-only',str(path),'--','-k','Return']
   source_pair=hashlib.sha256((HERE/'sentinel-wtype.c').read_bytes()+(HERE/'arctic-proof.h').read_bytes()).hexdigest()
   proof=P.producer(path,self.binary,source_pair,argv,os.getuid(),True)
   self.assertEqual(proof['identity']['return_codes'],[dict(keycode=9,group=0,level=0)])
   original=(path/'producer-identity.json').read_bytes()
   for key,value in [('pid',True),('uid',os.getuid()+1),('sentinel',9),('maximum',True),('map_only',False),('source_sha256','0'*64)]:
    changed=json.loads(original);changed[key]=value
    (path/'producer-identity.json').write_text(json.dumps(changed))
    with self.subTest(key=key),self.assertRaises(RuntimeError):P.producer(path,self.binary,source_pair,argv,os.getuid(),True)
   (path/'producer-identity.json').write_bytes(original)
   raw=(path/'uploaded-map.xkb').read_bytes();(path/'uploaded-map.xkb').write_bytes(raw[:-1])
   with self.assertRaises(RuntimeError):P.producer(path,self.binary,source_pair,argv,os.getuid(),True)
  finally:temp.cleanup()
 def test_actual_identity_and_escaped_argv_cap_before_map_or_input(self):
  # Independent historical reproducer: 18 ordinary 4096-byte text args.
  # Quotes/backslashes and control characters consume their actual JSON escape sizes.
  for args in ([*(['a'*4096]*18),'-k','Return'],[*(['\\"'*2048]*5),'-k','Return'],
               [*(['\t'*4096]*2),'-k','Return']):
   temp,path,result=self.invoke(args)
   try:
    self.assertEqual(result.returncode,112)
    self.assertIn(b'escaped argument proof bound exceeded before parse/input',result.stderr)
    self.assertEqual(list(path.iterdir()),[],'must reject before map/proof/input')
   finally:temp.cleanup()
  temp,path,result=self.invoke([*(['a'*4096]*6),'-k','Return'])
  try:
   self.assertEqual(result.returncode,0,result.stderr)
   self.assertLessEqual((path/'producer-identity.json').stat().st_size,65536)
  finally:temp.cleanup()
if __name__=='__main__':unittest.main(verbosity=2)
