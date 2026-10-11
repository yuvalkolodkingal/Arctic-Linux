import ast,hashlib,importlib.util,io,json,subprocess,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
ROOT=Path(__file__).parent
ORIGINAL_SHA='9e53952045537af0ca67a95f618f3b010e54cbfba4df5bacb138ef216a9ef0bf'
NONCE='0123456789abcdef0123456789abcdef'
PRIVATE='ownedsyntheticprivatecredentialfixture'
HELPER="def installed_shell_ready(observed_line):\n    # F10's default Fish4.6 prompt_login + fish_prompt render the exact\n    # qualification account, hostname, home cwd and non-root suffix.\n    # OCR may omit the separating space before the suffix; neither fixed\n    # spelling accepts a greeting, getty, root or unrelated shell suffix.\n    return type(observed_line) is str and observed_line in (\n        'arcticqual@arctic-qual ~ >', 'arcticqual@arctic-qual ~>')\n\n\n"
OLD="        if not sent and observed_line is not None and observed_line != 'Password:':\n            require(time.monotonic() + len(command)*.08 + .3 < deadline,\n                    'installed user identity deadline exceeded')\n            vm.type_text(command, gap=.08); vm.keys('ret')\n            require(time.monotonic() < deadline, 'installed user identity deadline exceeded')\n            sent = True\n"
NEW="        if not sent and observed_line is not None and observed_line != 'Password:':\n            if not installed_shell_ready(observed_line):\n                # Fish's startup greeting owns/flushed terminal input before\n                # its prompt. One nonsecret Return dismisses that greeting;\n                # no nonce command or sudo input is sent without readiness.\n                if not greeting_exit_sent:\n                    require(time.monotonic() + .3 < deadline,\n                            'installed user identity deadline exceeded')\n                    vm.keys('ret')\n                    greeting_exit_sent = True\n            else:\n                require(time.monotonic() + len(command)*.08 + .3 < deadline,\n                        'installed user identity deadline exceeded')\n                vm.type_text(command, gap=.08); vm.keys('ret')\n                require(time.monotonic() < deadline, 'installed user identity deadline exceeded')\n                sent = True\n"
def load(source,name):
 m=types.ModuleType(name);m.__file__=str(ROOT/'driver.py');exec(compile(source,m.__file__,'exec'),m.__dict__);return m
SOURCE=(ROOT/'driver.py').read_text()
def original_source():
 body=SOURCE.replace(HELPER,'').replace('    greeting_exit_sent = False\n','').replace(NEW,OLD)
 if hashlib.sha256(body.encode()).hexdigest()!=ORIGINAL_SHA:raise AssertionError('Whole original Driver inverse differs')
 return body
class Clock:
 def __init__(self,start=0):self.now=start
 def monotonic(self):return self.now
 def monotonic_ns(self):return int(self.now*1e9)
 def sleep(self,seconds):self.now+=seconds
class VM:
 def __init__(self,module,clock,path,ready=False,never=False,returned=None):
  self.module=module;self.clock=clock;self.path=path;self.ready=ready;self.never=never;self.returned=returned;self.delivered=False;self.commands=[];self.keys_sent=[];self.initial_record=None
 def alive(self):return True
 def shot(self,name):self.clock.sleep(self.shot_delay);return str(self.path)
 def type_text(self,command,gap):
  self.commands.append((command,self.ready));self.clock.sleep(len(command)*gap)
  if self.ready:self.delivered=True
  elif not self.never:self.ready=True
 def keys(self,*names):
  self.keys_sent.append(names);self.clock.sleep(.3)
  if not self.never:self.ready=True
 def ocr(self,*args,**kwargs):
  if self.initial_record is not None:text=self.initial_record
  elif self.delivered:text=self.returned if self.returned is not None else self.module.installed_user_line(NONCE)
  elif self.ready:text='arcticqual@arctic-qual ~ >'
  else:text='Arctic Linux startup greeting'
  return types.SimpleNamespace(stdout=(text+'\n').encode(),stderr=b'',returncode=0)
class Controls(unittest.TestCase):
 def execute(self,module,ready=False,never=False,returned=None,initial=None,start=0,console=True,shot_delay=0):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'owned-Source-fixture.png';Image.new('RGB',(1280,720),'black').save(path)
   clock=Clock(start);vm=VM(module,clock,path,ready,never,returned);vm.initial_record=initial;vm.shot_delay=shot_delay
   startup=types.SimpleNamespace(console_screen=lambda p:console)
   with patch.object(module,'time',clock),patch.object(module.subprocess,'run',vm.ocr):
    try:result=module.console_user_identity(vm,startup,Path(folder),NONCE,PRIVATE)
    except Exception as e:return vm,clock,e
    return vm,clock,result
 def test_whole_original_inverse_and_every_other_auth_security_function_exact(self):
  old=ast.parse(original_source());new=ast.parse(SOURCE)
  self.assertEqual([ast.dump(n) for n in old.body if not isinstance(n,ast.FunctionDef) or n.name!='console_user_identity'],[ast.dump(n) for n in new.body if not isinstance(n,ast.FunctionDef) or n.name not in ('console_user_identity','installed_shell_ready')])
 def test_actual_original_banner_consumption_counterexample_corrected_ready_flow(self):
  old=load(original_source(),'actual_original_readiness_counterexample');vm,clock,result=self.execute(old)
  self.assertIsInstance(result,RuntimeError);self.assertEqual(str(result),'exact installed user identity was not observed; sudo input refused');self.assertEqual(vm.commands,[(old.installed_user_command(NONCE),False)]);self.assertFalse(vm.delivered);self.assertGreaterEqual(clock.now,45)
  new=load(SOURCE,'actual_corrected_readiness');vm,clock,result=self.execute(new)
  self.assertIsInstance(result,dict);self.assertEqual(vm.commands,[(new.installed_user_command(NONCE),True)]);self.assertEqual(vm.keys_sent,[('ret',),('ret',)]);self.assertTrue(vm.delivered);self.assertLess(clock.now,45);self.assertEqual((result['nonce'],result['uid'],result['username']),(NONCE,1000,'arcticqual'))
 def test_positive_ready_sends_original_single_command_no_greeting_key(self):
  m=load(SOURCE,'actual_ready_direct');vm,clock,result=self.execute(m,ready=True)
  self.assertIsInstance(result,dict);self.assertEqual(vm.keys_sent,[('ret',)]);self.assertEqual(vm.commands,[(m.installed_user_command(NONCE),True)])
 def test_unready_gets_only_one_nonsecret_return_no_command_deadline_extension(self):
  m=load(SOURCE,'actual_never_ready');vm,clock,result=self.execute(m,never=True)
  self.assertIsInstance(result,RuntimeError);self.assertEqual(str(result),'exact installed user identity was not observed; sudo input refused');self.assertEqual(vm.keys_sent,[('ret',)]);self.assertEqual(vm.commands,[]);self.assertGreaterEqual(clock.now,45);self.assertLess(clock.now,46)
 def test_exact_user_nonce_identity_wrong_replayed_duplicate_unchanged_denial(self):
  m=load(SOURCE,'actual_exact_identity_denial');expected=m.installed_user_line(NONCE)
  for returned in (expected.replace(NONCE,'f'*32),expected.replace('uid=1000','uid=0'),expected.replace('arcticqual','foreignuser'),expected+'\n'+expected):
   vm,clock,result=self.execute(m,ready=True,returned=returned);self.assertIsInstance(result,RuntimeError);self.assertEqual(str(result),'installed user identity response differs')
  vm,clock,result=self.execute(m,ready=True,initial=expected);self.assertIsInstance(result,RuntimeError);self.assertEqual(str(result),'installed user identity response differs');self.assertEqual(vm.commands,[])
 def test_secret_nonappearance_console_login_failure_and_deadline_unchanged(self):
  m=load(SOURCE,'actual_preserved_guards')
  for initial,console,label in ((PRIVATE,True,'private input unexpectedly appeared in console; image withheld'),('Login incorrect',True,'installed user login did not reach its identity challenge'),('arctic-qual login:',True,'installed user login did not reach its identity challenge'),(None,False,'actual password console disappeared')):
   vm,clock,result=self.execute(m,initial=initial,console=console);self.assertIsInstance(result,RuntimeError);self.assertEqual(str(result),label);self.assertEqual(vm.commands,[])
  vm,clock,result=self.execute(m,ready=True,shot_delay=44);self.assertIsInstance(result,RuntimeError);self.assertEqual(str(result),'installed user identity deadline exceeded');self.assertEqual(vm.commands,[])
 def test_closed_source_prompt_full_identity_and_home_only(self):
  m=load(SOURCE,'actual_closed_prompt')
  for value in ('arcticqual@arctic-qual ~ >','arcticqual@arctic-qual ~>'):self.assertTrue(m.installed_shell_ready(value))
  for value in (None,True,1000,[],{},'Password:','Arctic Linux','root@arctic-qual ~ >','arcticqual@foreign ~ >','arcticqual@arctic-qual /tmp >','anything arcticqual >','arcticqual@arctic-qual ~ > foreign','\x1b[31marcticqual@arctic-qual ~ >\x1b[0m'):
   self.assertFalse(m.installed_shell_ready(value))
 def test_same_driver_singleton_pins_and_disabled_preparation(self):
  digest=hashlib.sha256(SOURCE.encode()).hexdigest()
  for name in ('execution-manifest.json','active-execution-manifest.json'):
   v=json.loads((ROOT/name).read_bytes());self.assertEqual(v['execution_files']['tools/installer-qualification/driver.py'],digest);self.assertIs(v['ready'],False);self.assertIs(v['release_acceptance'],False)
if __name__=='__main__':unittest.main(verbosity=2)
