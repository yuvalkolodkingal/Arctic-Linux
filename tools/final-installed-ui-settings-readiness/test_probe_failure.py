"""Actual Source functions on synthetic fixtures only; no original/VM reads."""
import contextlib,io,json,os,signal,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
import guest as G
import run as R
CONTEXT=dict(schema='arctic-final-installed-ui-context-v1',nonce='1'*32,execution_sha=R.C.git('rev-parse','HEAD'),source_sha='326690f173d4dc4f049f43e046c8380e66825a07',iso_sha256='807eaaa64ab8480ec2b18bc8434fd5e37d82c41b73a3e0a6f002c35d152ba54c',native_sha256='d7c69563a4a9908d4e4c8c937222f7e814440bfbb6c06de07fbd32b7e0caa4f8',ui_sha256=R.CATEGORY_GUEST_SHA256)
class Controls(unittest.TestCase):
 def probe(self):
  p=G.Probe.__new__(G.Probe);p.phase='appearance';p.context=CONTEXT;p.child=None;p.captures=[];p.checks=[]
  p.appearance=lambda:None;p.capture=lambda name:None;p.library=lambda:{'items':[]}
  return p
 def scope(self,p,out):
  s=contextlib.ExitStack();s.enter_context(patch.object(G,'_preprobe',return_value=p));s.enter_context(patch.object(G.signal,'signal'));s.enter_context(patch.object(G.signal,'alarm'));s.enter_context(contextlib.redirect_stdout(out));return s
 def records(self,out):return [json.loads(v[len(G.PROBE_FAILURE_PREFIX):]) for v in out.getvalue().splitlines() if v.startswith(G.PROBE_FAILURE_PREFIX)]
 def record(self,role='execute'):
  out=io.StringIO()
  with contextlib.redirect_stdout(out):G.emit_probe_failure(CONTEXT,'appearance',role,RuntimeError('PRIVATE_SYNTHETIC_SENTINEL'))
  return self.records(out)[0]
 def wire(self,records):return ('\n'.join(G.PROBE_FAILURE_PREFIX+json.dumps(v,sort_keys=True) for v in records)+'\n').encode()
 def test_actual_sites_wait_foreign_globals_and_unformatted_unknown(self):
  with patch.object(G.subprocess,'run',return_value=types.SimpleNamespace(returncode=1,stdout=b'',stderr=b'')):
   try:G.result(['PUBLIC_SYNTHETIC'])
   except RuntimeError as error:self.assertEqual(G.probe_failure_site(error),2)
   else:self.fail('Guard did not raise')
  with patch.object(G.time,'monotonic',side_effect=[0,2]):
   try:G.wait(lambda:False,1)
   except TimeoutError as error:self.assertEqual(G.probe_failure_site(error),3)
   else:self.fail('Timeout did not raise')
  foreign=dict(G.__dict__);foreign['subprocess']=types.SimpleNamespace(run=lambda *a,**k:types.SimpleNamespace(returncode=1,stdout=b'',stderr=b''))
  f=types.FunctionType(G.result.__code__,foreign);f.__defaults__=G.result.__defaults__
  try:f(['PUBLIC_SYNTHETIC'])
  except RuntimeError as error:self.assertEqual(G.probe_failure_site(error),0)
  class Poison:
   def __repr__(self):raise AssertionError('Operand formatted')
   def __str__(self):raise AssertionError('Operand formatted')
  out=io.StringIO()
  with contextlib.redirect_stdout(out):G.emit_probe_failure(CONTEXT,Poison(),'execute',RuntimeError(Poison()))
  self.assertEqual((self.records(out)[0]['phase'],self.records(out)[0]['site_id']),('unknown',0))
 def test_cloned_same_globals_Code_and_require_are_not_owned(self):
  clone=G.result.__code__.replace();self.assertIsNot(clone,G.result.__code__);self.assertEqual(clone,G.result.__code__)
  f=types.FunctionType(clone,G.__dict__);f.__defaults__=G.result.__defaults__
  with patch.object(G.subprocess,'run',return_value=types.SimpleNamespace(returncode=1,stdout=b'',stderr=b'')):
   try:f(['PUBLIC_SYNTHETIC'])
   except RuntimeError as error:self.assertEqual(G.probe_failure_site(error),0)
   else:self.fail('Cloned Code did not raise')
   foreign_require=types.FunctionType(G.require.__code__.replace(),G.__dict__)
   with patch.object(G,'require',foreign_require):
    try:G.result(['PUBLIC_SYNTHETIC'])
    except RuntimeError as error:self.assertEqual(G.probe_failure_site(error),0)
    else:self.fail('Cloned require did not raise')
 def test_actual_execute_failure_record_precedes_successful_export_original_return(self):
  p=self.probe();calls=[];p.export=lambda *args:calls.append(args);out=io.StringIO()
  with self.scope(p,out):self.assertEqual(G.main({},CONTEXT),1)
  self.assertEqual([(v['role'],v['site_id']) for v in self.records(out)],[('execute',16)])
  self.assertEqual(calls,[('failed','appearance','RuntimeError')])
 def test_both_actual_failures_keep_first_role_same_export_error_and_cleanup(self):
  p=self.probe();out=io.StringIO();errors=[];events=[]
  p.child=types.SimpleNamespace(poll=lambda:None,terminate=lambda:events.append('terminate'),wait=lambda seconds:events.append(('wait',seconds)))
  real=G.emit_probe_failure
  def emitting(context,phase,role,error):errors.append((role,error));return real(context,phase,role,error)
  with self.scope(p,out),patch.object(G,'emit_probe_failure',emitting),patch.object(G.subprocess,'run',return_value=types.SimpleNamespace(returncode=1,stdout=b'',stderr=b'')):
   try:G.main({},CONTEXT)
   except RuntimeError as error:self.assertIs(error,errors[1][1])
   else:self.fail('Export error swallowed')
  self.assertEqual([(v['role'],v['site_id']) for v in self.records(out)],[('execute',16),('export',2)])
  self.assertEqual(events,['terminate',('wait',5)]);self.assertIsNot(errors[0][1],errors[1][1])
 def test_export_only_error_identity_and_reporter_error_never_replaces_it(self):
  p=self.probe();p.execute=lambda:None;primary=OSError('PRIVATE_SYNTHETIC_SENTINEL')
  def exporting(*args):raise primary
  p.export=exporting;out=io.StringIO()
  with self.scope(p,out):
   try:G.main({},CONTEXT)
   except OSError as error:self.assertIs(error,primary)
   else:self.fail('Export error swallowed')
  self.assertEqual([v['role'] for v in self.records(out)],['export'])
  with self.scope(p,io.StringIO()),patch('builtins.print',side_effect=ValueError('PUBLIC_SYNTHETIC_WRITE_FAILURE')):
   try:G.main({},CONTEXT)
   except OSError as error:self.assertIs(error,primary)
   else:self.fail('Reporter changed failure')
 def test_original_keyboard_interrupt_export_and_child_cleanup_identity(self):
  p=self.probe();primary=KeyboardInterrupt('PRIVATE_SYNTHETIC_SENTINEL');events=[]
  def executing():raise primary
  p.execute=executing;p.export=lambda *args:events.append(('export',args))
  p.child=types.SimpleNamespace(poll=lambda:None,terminate=lambda:events.append('terminate'),wait=lambda seconds:events.append(('wait',seconds)))
  out=io.StringIO()
  with self.scope(p,out):
   try:G.main({},CONTEXT)
   except KeyboardInterrupt as error:self.assertIs(error,primary)
   else:self.fail('Interrupt swallowed')
  self.assertEqual(self.records(out),[]);self.assertEqual(events,[('export',('failed','appearance','none')),'terminate',('wait',5)])
 def test_host_strict_two_roles_duplicates_foreign_order_private_suffix(self):
  a=self.record();b=self.record('export');slot=R.probe_failure_slot(self.wire([a,b]),CONTEXT,G)
  self.assertEqual([v['role'] for v in slot['records']],['execute','export'])
  for records,reason in (([a,a],'duplicate-record'),([b,a],'sequence-denied')):self.assertEqual(R.probe_failure_slot(self.wire(records),CONTEXT,G)['reason'],reason)
  bad=dict(a,context=dict(CONTEXT,nonce='2'*32));self.assertEqual(R.probe_failure_slot(self.wire([bad]),CONTEXT,G)['reason'],'foreign-context')
  bad=dict(a,private='PRIVATE_SYNTHETIC_SENTINEL');self.assertEqual(R.probe_failure_slot(self.wire([bad]),CONTEXT,G)['reason'],'invalid-record')
  self.assertEqual(R.probe_failure_slot(b'prefix '+self.wire([a]),CONTEXT,G)['reason'],'ambiguous-prefix')
 def test_host_delivery_from_rejected_UART_harness_to_actual_screened_artifact(self):
  with tempfile.TemporaryDirectory(prefix='ui-probe-public-delivery-') as td:
   root=Path(td);private=root/'private';(private/'vm').mkdir(parents=True);public=root/'public';public.mkdir()
   p=self.probe();out=io.StringIO()
   with self.scope(p,out),patch.object(G.subprocess,'run',return_value=types.SimpleNamespace(returncode=1,stdout=b'',stderr=b'')):
    with self.assertRaises(RuntimeError):G.main({},CONTEXT)
   self.assertEqual([(v['role'],v['site_id']) for v in self.records(out)],[('execute',16),('export',2)])
   data=b'password=PRIVATE_SYNTHETIC_SENTINEL\n'+out.getvalue().encode()
   for path in (private/'vm/serial-boot.log',private/'harness.log'):path.write_bytes(data);path.chmod(0o600)
   result=R.guest_probe_failure_categories(private,CONTEXT);encoded=(json.dumps(result,sort_keys=True)+'\n').encode()
   self.assertTrue(all(v['status']=='observed' for v in result['sources'].values()))
   self.assertNotIn(CONTEXT['nonce'].encode(),encoded);self.assertNotIn(b'PRIVATE_SYNTHETIC_SENTINEL',encoded)
   scanner=R.C.load(R.C.ROOT/'tools/native-functional/screen-evidence.py','public_probe_screen')
   with self.assertRaises(RuntimeError):scanner.external_text(data)
   self.assertEqual(scanner.external_text(encoded),encoded)
   R.C.exclusive(public/'guest-probe-failure-categories.json',encoded)
   host=dict(status='failed',context=CONTEXT);R.C.exclusive(public/'host-status.json',(json.dumps(host,sort_keys=True)+'\n').encode())
   R.screen(public,root/'screened')
   self.assertEqual((root/'screened/guest-probe-failure-categories.json').read_bytes(),encoded)
   self.assertFalse(result['original_UART_admission_used']);self.assertFalse(result['ui_acceptance'])
 def test_source_drift_before_private_and_real_SIGINT_reader_cleanup(self):
  with patch.object(R,'CATEGORY_GUEST_SHA256','0'*64),patch.object(R,'probe_original',wraps=R.probe_original) as reads:
   with self.assertRaises(RuntimeError):R.guest_probe_failure_categories(Path('/PUBLIC_NEVER_READ'),CONTEXT)
   self.assertEqual(reads.call_count,2)
  with tempfile.TemporaryDirectory(prefix='ui-probe-public-sigint-') as td:
   path=Path(td)/'public.log';path.write_bytes(b'PUBLIC_SYNTHETIC');path.chmod(0o600)
   before=set(os.listdir('/proc/self/fd'));real=R.os.open;acquired=[]
   def opening(p,flags,*args,**kwargs):
    fd=real(p,flags,*args,**kwargs)
    if p==path:acquired.append(fd);os.kill(os.getpid(),signal.SIGINT)
    return fd
   with patch.object(R.os,'open',opening):
    with self.assertRaises(KeyboardInterrupt):R.probe_original(path,1024)
   self.assertEqual(set(os.listdir('/proc/self/fd')),before)
   with self.assertRaises(OSError):os.fstat(acquired[0])
 def test_private_reader_generation_mismatch_never_closes_foreign_FD(self):
  with tempfile.TemporaryDirectory(prefix='ui-probe-public-generation-') as td:
   root=Path(td);path=root/'one';foreign=root/'two';path.write_bytes(b'PUBLIC_ONE');foreign.write_bytes(b'PUBLIC_TWO')
   for p in (path,foreign):p.chmod(0o600)
   foreign_fd=os.open(foreign,os.O_RDONLY);real=R.os.read;held=[]
   def reading(fd,*args):
    if not held:held.append(fd);os.dup2(foreign_fd,fd)
    return real(fd,*args)
   try:
    with patch.object(R.os,'read',reading):
     with self.assertRaises(RuntimeError):R.probe_original(path,1024)
    self.assertEqual(os.fstat(held[0]).st_ino,foreign.stat().st_ino)
   finally:
    if held:os.close(held[0])
    os.close(foreign_fd)
SETTINGS_READY_SOURCE = """    def settings_ready(self):
        try:
            return result(self.settings + ['ready']).lower() == 'true'
        except RuntimeError as error:
            # The launcher starts asynchronously. Only this original owned
            # command-exit site means "not ready" inside the existing wait.
            # Bounds, timeouts, foreign Code and every other command still fail.
            if probe_failure_site(error) == 2:
                return False
            raise

"""
def without_settings_readiness(source):
 assert source.count(SETTINGS_READY_SOURCE)==1 and source.count('        wait(self.settings_ready)')==2
 source=source.replace(SETTINGS_READY_SOURCE,'').replace('        wait(self.settings_ready)',
     "        wait(lambda: result(self.settings + ['ready']).lower() == 'true')")
 # Removing the eleven-line method restores the original absolute Source
 # observation spans. Every role ID, condition and frame gate is unchanged.
 import re
 source,count=re.subn(r"(    \('Probe\.(?:appearance|execute|export)', )(\d+)(, )(\d+)(,)",
     lambda m:m[1]+str(int(m[2])-11)+m[3]+str(int(m[4])-11)+m[5],source)
 assert count==14
 return source.replace("GUEST_PREPROBE_SPANS = [(362, 362, 'guest-stage'), (364, 365, 'guest-owned-data-cd'), (375, 377, 'guest-prefix')]",
     "GUEST_PREPROBE_SPANS = [(351, 351, 'guest-stage'), (353, 354, 'guest-owned-data-cd'), (364, 366, 'guest-prefix')]")

class SettingsReadiness(unittest.TestCase):
 def probe(self,module=G):
  p=module.Probe.__new__(module.Probe);p.child=object();p.settings=['PUBLIC_SETTINGS_FIXTURE'];return p
 def failure(self,call,kind,module=G):
  # assertRaises clears traceback on exit; classify the original while caught.
  try:call()
  except BaseException as error:
   self.assertIs(type(error),kind)
   return error,module.probe_failure_site(error)
  self.fail('Required failure did not occur')
 def test_real_early_missing_endpoint_then_ready_and_original_counterfactual(self):
  import hashlib
  source=Path(G.__file__).read_text();old=without_settings_readiness(source)
  self.assertEqual(hashlib.sha256(old.encode()).hexdigest(),
      'b66ff979bcff7aaba0a2f172367c1189c9ea9b3f1f25ba709a8d0dc8b8f3f508')
  original=types.ModuleType('original_public_guest_counterfactual');original.__file__=G.__file__
  exec(compile(old,G.__file__,'exec'),original.__dict__)
  with tempfile.TemporaryDirectory(prefix='public-settings-startup-') as td:
   root=Path(td);program=root/'public_ipc.py';state=root/'calls'
   program.write_text("import pathlib,sys\np=pathlib.Path(sys.argv[1]);op=sys.argv[2]\nif op=='ready':\n n=int(p.read_text()) if p.exists() else 0;p.write_text(str(n+1))\n if n==0:raise SystemExit(1)\n print('true')\nelif op=='reveal':print('ok')\nelif op=='page':print('appearance')\nelse:raise SystemExit(2)\n")
   p=self.probe(original);p.settings=[sys.executable,str(program),str(state)]
   old_error,site=self.failure(lambda:original.Probe.appearance(p),RuntimeError,original)
   self.assertEqual(site,2)
   self.assertEqual(state.read_text(),'1');state.unlink()
   p=self.probe();p.settings=[sys.executable,str(program),str(state)]
   with patch.object(G.time,'sleep'):G.Probe.appearance(p)
   self.assertEqual(state.read_text(),'3')
 def test_real_permanent_command_exit_keeps_existing_wait_deadline(self):
  p=self.probe();p.settings=[sys.executable,'-c','raise SystemExit(1)']
  with patch.object(G.time,'monotonic',side_effect=[0,0,46]),patch.object(G.time,'sleep') as sleep:
   error,site=self.failure(lambda:G.wait(p.settings_ready),TimeoutError)
  self.assertEqual(site,3);sleep.assert_called_once_with(.25)
 def test_bounds_timeout_cancellation_foreign_Code_preserve_same_failure(self):
  p=self.probe();saved=[];real=G.result
  def capture(*args,**kwargs):
   try:return real(*args,**kwargs)
   except BaseException as error:saved.append(error);raise
  with patch.object(G,'result',capture),patch.object(G.subprocess,'run',return_value=
      types.SimpleNamespace(returncode=1,stdout=b'x'*(4*1024*1024+1),stderr=b'')):
   error,site=self.failure(p.settings_ready,RuntimeError)
  self.assertIs(error,saved[0]);self.assertEqual(site,1)
  for error in (TimeoutError('PUBLIC_SYNTHETIC'),KeyboardInterrupt(),SystemExit(7)):
   with patch.object(G,'result',side_effect=error):
    got,site=self.failure(p.settings_ready,type(error))
   self.assertIs(got,error)
  for foreign in (types.FunctionType(G.result.__code__.replace(),G.__dict__),
      types.FunctionType(G.result.__code__,dict(G.__dict__))):
   foreign.__defaults__=G.result.__defaults__;saved=[]
   def foreign_capture(*args):
    try:return foreign(*args)
    except BaseException as error:saved.append(error);raise
   with patch.object(G,'result',foreign_capture),patch.object(G.subprocess,'run',return_value=
       types.SimpleNamespace(returncode=1,stdout=b'',stderr=b'')):
    error,site=self.failure(p.settings_ready,RuntimeError)
   self.assertIs(error,saved[0]);self.assertEqual(site,0)
 def test_reveal_page_and_nontrue_responses_never_admit_UI(self):
  p=self.probe()
  for value in (b'false',b'PRIVATE_SYNTHETIC_UNKNOWN',b''):
   with patch.object(G.subprocess,'run',return_value=types.SimpleNamespace(returncode=0,stdout=value,stderr=b'')):
    self.assertFalse(p.settings_ready())
  for failed in ('reveal','page'):
   calls=[]
   def run(command,**kwargs):
    calls.append(command);op=command[1]
    return types.SimpleNamespace(returncode=1 if op==failed else 0,
      stdout=b'true' if op=='ready' else b'ok',stderr=b'')
   with patch.object(G.subprocess,'run',run),patch.object(G.time,'sleep'):
    error,site=self.failure(lambda:G.Probe.appearance(p),RuntimeError)
   self.assertEqual(site,2)
   self.assertEqual(calls[-1][1],failed)

 def test_all_original_literal_sites_and_preprobe_spans_match_actual_Source(self):
  import ast
  tree=ast.parse(Path(G.__file__).read_text());functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
  probe=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Probe')
  functions.update({'Probe.'+n.name:n for n in probe.body if isinstance(n,ast.FunctionDef)})
  for name,first,last,ident,kind,needs_require in G.PROBE_FAILURE_SITES:
   nodes=[n for n in ast.walk(functions[name]) if
     (isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='require')
     or (not needs_require and isinstance(n,ast.Raise))]
   self.assertEqual(len([n for n in nodes if (n.lineno,n.end_lineno)==(first,last)]),1,(name,ident))
  fn=functions['_preprobe'];calls=[n for n in ast.walk(fn) if isinstance(n,ast.Call)
      and isinstance(n.func,ast.Name) and n.func.id=='require']
  self.assertEqual([(n.lineno,n.end_lineno) for n in sorted(calls,key=lambda n:n.lineno)],
      [(first,last) for first,last,label in G.GUEST_PREPROBE_SPANS])
  p=G.Probe.__new__(G.Probe);p.phase='appearance';p.appearance=lambda:None;p.capture=lambda name:None
  p.library=lambda:{'items':[]}
  error,site=self.failure(p.execute,RuntimeError);self.assertEqual(site,16)
  for operation,expected in [('reveal',14),('page',15)]:
   p=self.probe()
   def running(command,**kwargs):
    op=command[1]
    return types.SimpleNamespace(returncode=0,stderr=b'',stdout=
      b'true' if op=='ready' else (b'wrong' if op==operation else b'ok'))
   with patch.object(G.subprocess,'run',running),patch.object(G.time,'sleep'):
    error,site=self.failure(lambda:G.Probe.appearance(p),RuntimeError)
   self.assertEqual(site,expected)
  out=io.StringIO()
  with patch.object(G.sys,'argv',['PUBLIC_GUEST']),contextlib.redirect_stdout(out):
   try:G._preprobe({},CONTEXT)
   except RuntimeError as error:self.assertEqual(G.guest_guard_label(error,{}),'guest-stage')
   else:self.fail('Original guest stage guard did not fail')

if __name__=='__main__':unittest.main(verbosity=2)
