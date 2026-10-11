import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent

def module(name):
 m=types.ModuleType(name);m.__file__=str(ROOT/(name+'.py'));exec(compile((ROOT/(name+'.py')).read_bytes(),m.__file__,'exec'),m.__dict__);return m

r=module('runner');c=module('collect')

class Execution(unittest.TestCase):
 def test_disabled_before_API_or_container(self):
  manifest=json.loads((ROOT/'execution-manifest.json').read_bytes())
  with patch.object(r,'capture',side_effect=AssertionError('must not reach API/process')):
   with self.assertRaisesRegex(RuntimeError,'disabled'):r.activation_guard(ROOT,manifest)
  for field in ('container','config'):
   bad=copy.deepcopy(manifest);bad[field]='unknown'
   with self.assertRaises(RuntimeError):r.validate_manifest(bad)

 def test_exact_image_and_container_identity(self):
  info={'Id':r.CONFIG,'Os':'linux','Architecture':'amd64','RepoDigests':[r.IMAGE],'Config':{'Labels':{'org.opencontainers.image.version':'44'}}}
  self.assertEqual(r.image_identity([info])['image_id'],r.CONFIG)
  for key,value in (('Architecture','arm64'),('Id','sha256:'+'0'*64),('RepoDigests',[])):
   bad=copy.deepcopy(info);bad[key]=value
   with self.assertRaises(RuntimeError):r.image_identity([bad])
  ci={'Id':'1'*64,'Image':r.CONFIG,'Name':'/owned','Config':{'Labels':{'arctic.capture-nonce':'publicfixture'}},'HostConfig':{'Privileged':False,'Binds':None},'Mounts':[]}
  self.assertEqual(r.container_identity([ci],'owned','publicfixture'),'1'*64)
  for key in ('Name','Image'):
   bad=copy.deepcopy(ci);bad[key]='foreign'
   with self.assertRaises(RuntimeError):r.container_identity([bad],'owned','publicfixture')
  for key,value in (('Privileged',True),('Binds',['/host:/host'])):
   bad=copy.deepcopy(ci);bad['HostConfig'][key]=value
   with self.assertRaises(RuntimeError):r.container_identity([bad],'owned','publicfixture')

 def test_cleanup_foreign_and_daemon_failure_are_not_absence(self):
  ci={'Id':'1'*64,'Image':r.CONFIG,'Name':'/owned','Config':{'Labels':{'arctic.capture-nonce':'publicfixture'}},'HostConfig':{'Privileged':False,'Binds':None},'Mounts':[]}
  calls=[]
  def run(argv,**kwargs):
   calls.append(argv)
   return subprocess.CompletedProcess(argv,0,json.dumps([ci]).encode())
  with patch.object(r.subprocess,'run',side_effect=run),patch.object(r,'capture',return_value=b''):
   r.remove_container('owned','publicfixture','1'*64)
  self.assertEqual(calls[1],['docker','rm','--force','1'*64])
  calls.clear()
  with patch.object(r.subprocess,'run',side_effect=run):
   with self.assertRaises(RuntimeError):r.remove_container('owned','wrong')
  self.assertEqual(len(calls),1)
  with patch.object(r.subprocess,'run',return_value=subprocess.CompletedProcess([],1,b'')),patch.object(r,'capture',side_effect=RuntimeError('daemon unavailable')):
   with self.assertRaises(RuntimeError):r.remove_container('owned','publicfixture')

 def test_real_private_generation_and_exclusive_output(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'data';r.write_private(p,b'complete original');self.assertEqual(r.read_owned(p,100),b'complete original')
   with self.assertRaises(FileExistsError):r.write_private(p,b'changed')
   q=Path(tmp)/'dangling';q.symlink_to(Path(tmp)/'outside')
   with self.assertRaises(FileExistsError):r.write_private(q,b'private')
   self.assertFalse((Path(tmp)/'outside').exists())
   original=r.os.pread
   def mutate(fd,n,offset):
    data=original(fd,n,offset);p.rename(Path(tmp)/'old');r.write_private(p,data);return data
   with patch.object(r.os,'pread',side_effect=mutate):
    with self.assertRaisesRegex(RuntimeError,'private_file_changed'):r.read_owned(p,100)
   self.assertEqual(p.read_bytes(),b'complete original')

 def test_real_command_timeout_and_complete_log(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'success.log';r.command([sys.executable,'-c','print("public controlled original")'],path,5)
   self.assertEqual(path.read_bytes(),b'public controlled original\n');self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
   marker=Path(tmp)/'pid';log=Path(tmp)/'timeout.log'
   code='import os,time,pathlib; pathlib.Path('+repr(str(marker))+').write_text(str(os.getpid())); time.sleep(30)'
   with self.assertRaisesRegex(RuntimeError,'owned_command_timeout'):r.command([sys.executable,'-c',code],log,.5)
   pid=int(marker.read_text())
   with self.assertRaises(ProcessLookupError):os.kill(pid,0)

 def test_real_command_signal_handoff_and_kernel_output_cap(self):
  with tempfile.TemporaryDirectory() as tmp:
   log=Path(tmp)/'bounded.log'
   with patch.object(r,'MAX_LOG',4096):
    with self.assertRaises(RuntimeError):r.command([sys.executable,'-c','import os; os.write(1,b"a"*100000)'],log,5)
   self.assertLessEqual(log.stat().st_size,4096)
   real=r.subprocess.Popen;owned=[];old=signal.getsignal(signal.SIGINT)
   def acquire(*args,**kwargs):
    p=real(*args,**kwargs);owned.append(p);os.kill(os.getpid(),signal.SIGINT);return p
   try:
    signal.signal(signal.SIGINT,signal.default_int_handler)
    with patch.object(r.subprocess,'Popen',side_effect=acquire):
     with self.assertRaises(KeyboardInterrupt):r.command([sys.executable,'-c','import time;time.sleep(30)'],Path(tmp)/'cancel.log',5)
    self.assertIsNotNone(owned[0].poll())
   finally:signal.signal(signal.SIGINT,old)

 def test_cpio_original_hardlink_group_and_malformed_reject(self):
  def item(name,data,ino=1,links=1):
   name=name.encode()+b'\0';fields=[ino,stat.S_IFREG|0o644,0,0,links,0,len(data),1,2,0,0,len(name),0]
   header=b'070701'+b''.join(format(x,'08x').encode() for x in fields);a=header+name;a+=b'\0'*((-len(a))%4);a+=data;a+=b'\0'*((-len(a))%4);return a
  raw=item('./usr/lib/debug/example.debug',b'',links=2)+item('./usr/lib/debug/link.debug',b'whole ELF',links=2)+item('TRAILER!!!',b'')
  self.assertEqual(c.cpio(raw)['./usr/lib/debug/example.debug'][1],b'whole ELF')
  for bad in (raw+b'private tail',item('../outside',b'private')+item('TRAILER!!!',b''),item('./same',b'a')+item('./same',b'b')+item('TRAILER!!!',b'')):
   with self.assertRaises(RuntimeError):c.cpio(bad)

 def test_original_guard_function_bytes(self):
  import ast
  old=subprocess.check_output(['git','-C',str(ROOT.parents[1]),'show','6f43d240643b00eeb44f7f3aab33415b326150e2:tools/browser-main-library-diagnostic-20261011/runner.py']).decode()
  current=(ROOT/'runner.py').read_text()
  find=lambda text:{n.name:ast.dump(n,include_attributes=False) for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)}
  a,b=find(old),find(current)
  for name in ('require','typed_equal','read_json','sha','safe_file','capture','verify_tracked','activation_guard'):self.assertEqual(a[name],b[name],name)


 def test_actual_screen_call_keeps_primary_stdout_and_closed_record(self):
  mf=json.loads((ROOT/'execution-manifest.json').read_bytes());repo=ROOT.parents[1]
  original_verify=r.verify_tracked
  def verified(_root,name,pin=None):
   raw=(repo/name).read_bytes();wanted=next(v[name] for v in (mf['execution_files'],mf['observer_files'],mf['source_files']) if name in v)
   self.assertEqual(hashlib.sha256(raw).hexdigest(),wanted);return raw
  with tempfile.TemporaryDirectory() as tmp:
   private=Path(tmp)/'private';private.mkdir(mode=0o700);(private/'products').mkdir();(private/'logs').mkdir()
   inventory={'variants':{v:{'packages':{},'ELFs':{}} for v in ('baseline','candidate')},'actual_runtime_mapping_admission':False,'performance_acceptance':False}
   for name,raw in {'products/custom-ELF-inventory.json':json.dumps(inventory).encode(),'products/ab-build-receipt.json':b'{}','logs/producer.log':b'password=synthetic-private','logs/collector.log':b'public'}.items():r.write_private(private/name,raw)
   seen=[];before=sys.stdout;previous=sys.gettrace()
   def trace(frame,event,value):
    if event=='exception' and frame.f_code.co_name=='external_text' and frame.f_code.co_filename==str(repo/'tools/browser-screen-failure-source/scanner.py'):seen.append(value[1])
    return trace
   try:
    sys.settrace(trace)
    with patch.object(r,'verify_tracked',side_effect=verified):
     with self.assertRaises(RuntimeError) as caught:r.screen_originals(repo,mf,private,Path(tmp)/'output')
   finally:sys.settrace(previous)
   self.assertIs(caught.exception,seen[-1]);self.assertIs(sys.stdout,before)
   self.assertEqual(r.screen_failure_record['member_role'],'command-producer');self.assertEqual(r.screen_failure_record['scanner_family'],'named-secret')
   self.assertFalse((Path(tmp)/'output').exists())

 def test_failure_screen_schema_cannot_add_or_weaken_fields(self):
  import importlib.util
  path=ROOT.parents[1]/'tools/browser-screen-failure-source/observer.py'
  spec=importlib.util.spec_from_file_location('owned_schema_observer',path);o=importlib.util.module_from_spec(spec);spec.loader.exec_module(o)
  p=o.ScreenProbe((path.parent/'scanner.py').read_bytes(),(path.parent/'ownership.py').read_bytes(),str(path.parent/'scanner.py'))
  row=p.unknown('logs/producer.log');self.assertIs(r.validate_screen_record(row,o),row)
  for key,value in (('privacy_admitted',True),('observer_owned_scanner_site',1),('member_role','unknown-private'),('scanner_family','unknown-private'),('extra','private')):
   bad=dict(row);bad[key]=value
   with self.assertRaises(RuntimeError):r.validate_screen_record(bad,o)

 def test_inventory_failure_has_no_fabricated_scanner_record(self):
  mf=json.loads((ROOT/'execution-manifest.json').read_bytes());repo=ROOT.parents[1]
  def verified(_root,name,pin=None):return (repo/name).read_bytes()
  with tempfile.TemporaryDirectory() as tmp:
   private=Path(tmp)/'private';private.mkdir(mode=0o700);(private/'products').mkdir()
   r.write_private(private/'products/custom-ELF-inventory.json',b'{}')
   r.screen_failure_record={'stale':'must clear'}
   with patch.object(r,'verify_tracked',side_effect=verified):
    with self.assertRaises(KeyError):r.screen_originals(repo,mf,private,Path(tmp)/'output')
   self.assertIsNone(r.screen_failure_record)

if __name__=='__main__':unittest.main()
