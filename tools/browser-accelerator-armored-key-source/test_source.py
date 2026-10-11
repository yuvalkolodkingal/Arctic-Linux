import ast,base64,hashlib,json,os,subprocess,tempfile,types,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
META=json.loads((HERE/'source-inverse.json').read_bytes())
DB='/tmp/arctic-final-functional-git-mdmg9v01/objects.git'
CACHE=Path('/workspace/Arctic-Linux/out/browser-rpm-key-source-research-20261011')
KEY=Path('/tmp/arctic-browser-fedora-signing-key-support-20261011/official-Fedora44-primary.gpg')
ARMOR=CACHE/'gpg-armored-same-public-key-export.stdout.original'
def original(role):return subprocess.check_output(['git','--git-dir',DB,'show',META['base']+':'+META[role]['path']])
def module(role):
 raw=(HERE/(role+'.py')).read_bytes();m=types.ModuleType('source_'+role);m.__file__=str(HERE/(role+'.py'));exec(compile(raw,m.__file__,'exec'),m.__dict__);return m
class Source(unittest.TestCase):
 def test_whole_inverse_only_format_fields(self):
  for role in ('runner','producer'):
   old=original(role);new=(HERE/(role+'.py')).read_bytes()
   self.assertEqual(hashlib.sha256(old).hexdigest(),META[role]['sha256'])
   for a,b in reversed(META[role]['changes']):self.assertEqual(new.count(b.encode()),1);new=new.replace(b.encode(),a.encode())
   self.assertEqual(new,old)
 def test_all_other_functions_caps_and_line_anchors_exact(self):
  for role in ('runner','producer'):
   old=original(role);new=(HERE/(role+'.py')).read_bytes()
   self.assertEqual(old.count(b'\n'),new.count(b'\n'))
   for a,b in reversed(META[role]['changes']):new=new.replace(b.encode(),a.encode())
   self.assertEqual(ast.dump(ast.parse(old),include_attributes=True),ast.dump(ast.parse(new),include_attributes=True))
 def test_actual_host_export_block_forwards_armor_exact_fingerprint(self):
  r=module('runner');p=module('producer');main=next(n for n in ast.parse((HERE/'runner.py').read_bytes()).body if isinstance(n,ast.FunctionDef) and n.name=='main')
  i=next(i for i,n in enumerate(main.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='key' for t in n.targets))
  code=compile(ast.fix_missing_locations(ast.Module(body=main.body[i:i+2],type_ignores=[])),'actual-host-key-export-block','exec')
  seen=[]
  def capture(argv,*,limit):seen.append((argv,limit));return ARMOR.read_bytes()
  g=dict(r.__dict__,capture=capture,producer=p,private=Path('/owned/public-key-home'))
  exec(code,g)
  self.assertEqual(seen,[(['gpg','--homedir','/owned/public-key-home/keyring','--batch','--no-autostart','--armor','--export',META['fingerprint']],16384)])
  self.assertEqual(g['key'],ARMOR.read_bytes())
 def test_actual_host_export_guard_rejects_binary_and_changed_armor(self):
  r=module('runner');p=module('producer');main=next(n for n in ast.parse((HERE/'runner.py').read_bytes()).body if isinstance(n,ast.FunctionDef) and n.name=='main')
  i=next(i for i,n in enumerate(main.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='key' for t in n.targets))
  code=compile(ast.fix_missing_locations(ast.Module(body=main.body[i:i+2],type_ignores=[])),'actual-host-key-export-block','exec')
  for raw in (KEY.read_bytes(),ARMOR.read_bytes()[:-1]+b'X',ARMOR.read_bytes()+b'X'):
   with self.subTest(bytes=len(raw)):
    with self.assertRaisesRegex(RuntimeError,'^exact_public_key_export$'):exec(code,dict(r.__dict__,capture=lambda *a,**k:raw,producer=p,private=Path('/owned/public-key-home')))
 def test_actual_owned_producer_binding_preserves_root_only_input(self):
  p=module('producer')
  with tempfile.TemporaryDirectory() as d:
   f=Path(d)/'key.gpg';f.write_bytes(ARMOR.read_bytes());f.chmod(0o600)
   if os.geteuid()==0:
    self.assertEqual(p.read_bound(f,1672,p.KEY_SHA),ARMOR.read_bytes())
   else:
    with self.assertRaisesRegex(RuntimeError,'^producer_input_identity$'):p.read_bound(f,1672,p.KEY_SHA)
   for raw in (KEY.read_bytes(),ARMOR.read_bytes()[:-1]+b'X'):
    f.write_bytes(raw)
    with self.assertRaises(RuntimeError):p.read_bound(f,1672,p.KEY_SHA)
 def test_same_packets_fingerprint_and_crc24(self):
  armor=ARMOR.read_bytes();key=KEY.read_bytes();lines=armor.splitlines()
  self.assertEqual(hashlib.sha256(key).hexdigest(),META['binary_key']['sha256'])
  self.assertEqual(hashlib.sha256(armor).hexdigest(),META['armored_key']['sha256'])
  self.assertEqual(base64.b64decode(b''.join(lines[2:-2]),validate=True),key)
  crc=0xB704CE
  for b in key:
   crc^=b<<16
   for _ in range(8):
    crc<<=1
    if crc&0x1000000:crc^=0x1864CFB
  self.assertEqual(base64.b64decode(lines[-2][1:],validate=True),(crc&0xffffff).to_bytes(3,'big'))
  original_gpg=(CACHE/'gpg-armored-full-key-identity.stdout.original').read_bytes()
  self.assertEqual(original_gpg.count(('fpr:::::::::'+META['fingerprint']+':').encode()),1)
 def test_full_original_srpm_signature_guard_and_witness_unchanged(self):
  old=ast.parse(original('producer'));new=ast.parse((HERE/'producer.py').read_bytes())
  def checks(tree):return [ast.dump(n,include_attributes=False) for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='require' and len(n.args)>1 and isinstance(n.args[1],ast.Constant) and n.args[1].value=='producer_source_signature']
  self.assertEqual(checks(old),checks(new));self.assertEqual(len(checks(new)),1)
  v=json.loads((CACHE/'armored-key-full-SRPM-witness.json').read_bytes());self.assertEqual(v['signature_exit'],0);self.assertTrue(v['full_signature_command_matches_original_producer']);self.assertFalse(v['package_payload_installed'])
if __name__=='__main__':unittest.main()
