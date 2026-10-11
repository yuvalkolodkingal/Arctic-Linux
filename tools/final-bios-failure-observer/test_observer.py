#!/usr/bin/env python3
"""Owned Source controls only: no QEMU, container, API or original retrieval."""
import ast,base64,contextlib,hashlib,io,json,os,pathlib,subprocess,sys,tempfile,types,unittest
from unittest import mock
import observer as O
import composition as P

ROOT=pathlib.Path(__file__).resolve().parents[2]
OLD=ROOT/'tools/final-bios-install'

def load(path,name):
    raw=path.read_bytes();m=types.ModuleType(name);m.__file__=str(path);sys.modules[name]=m
    exec(compile(raw,m.__file__,'exec'),m.__dict__);return m,raw

def bound(raw,key='control'):
    ns={'__name__':'source_control'};exec(compile(raw,'source-control.py','exec'),ns)
    sites=O.SourceSites();sites.bind(ns,raw,P.sha(raw),'source-control.py',key);return ns,sites

class Controls(unittest.TestCase):
    def test_actual_source_exception_identity_and_foreign_traceback(self):
        raw=b'def require(value, label):\n if not value: raise RuntimeError(label)\ndef check():\n require(False,"fixed-source-assertion")\n'
        ns,sites=bound(raw);rows=[]
        try:sites.invoke(ns['check'],rows.append)
        except RuntimeError as e:error=e
        self.assertEqual(rows[0]['site']['fixed_assertion_label'],'fixed-source-assertion')
        self.assertIsNotNone(sites.describe(error))
        foreign=RuntimeError('private operand').with_traceback(error.__traceback__)
        self.assertIsNone(sites.describe(foreign))
        clone=types.FunctionType(ns['check'].__code__,ns)
        self.assertRaises(RuntimeError,sites.invoke,clone,rows.append)
        self.assertEqual(len(rows),1)

    def test_source_globals_and_code_identity_fail_closed(self):
        raw=b'def require(v,label):\n if not v:raise RuntimeError(label)\ndef check():\n require(False,"known")\n'
        ns,sites=bound(raw);rows=[];original=ns['require'];ns['require']=lambda v,label:(_ for _ in ()).throw(RuntimeError('private'))
        self.assertRaises(RuntimeError,sites.invoke,ns['check'],rows.append);self.assertEqual(rows,[])
        ns['require']=original
        ns['check'].__code__=ns['check'].__code__.replace(co_firstlineno=99)
        self.assertRaises(RuntimeError,sites.invoke,ns['check'],rows.append);self.assertEqual(rows,[])

    def test_exception_operands_are_never_formatted_or_read(self):
        class Poison:
            def __str__(self):raise AssertionError('operand accessed')
            def __repr__(self):raise AssertionError('operand accessed')
        raw=b'def require(v,label):\n if not v:raise RuntimeError(label)\ndef check(operand):\n require(False,operand)\n'
        ns,sites=bound(raw);rows=[]
        try:sites.invoke(ns['check'],rows.append,Poison())
        except RuntimeError as error:self.assertIsNotNone(sites.describe(error))
        self.assertEqual(rows[0]['site']['fixed_assertion_label'],'require-site-4')
        json.dumps(rows)

    def test_actual_common_late_absent_global_cannot_mint_source_assertion(self):
        c,raw=load(OLD/'common.py','peer_corrected_actual_common')
        sites=O.SourceSites();sites.bind(c.__dict__,raw,P.sha(raw),c.__file__,'bios-common')
        class ForeignError(Exception):pass
        self.assertNotIn('RuntimeError',c.__dict__)
        c.RuntimeError=ForeignError;rows=[]
        try:sites.invoke(c.manifest,rows.append,{})
        except ForeignError as error:self.assertIsNone(sites.describe(error))
        else:self.fail('original actual common manifest did not reject')
        self.assertEqual(rows,[])

    def test_builtin_resolution_identity_and_absence_are_bound(self):
        raw=b'def check():\n raise RuntimeError("fixed-source")\n'
        ns,sites=bound(raw);rows=[]
        # Use a private, equal-content builtins dictionary, never global Python
        # builtins mutation; then change only its previously bound resolution.
        copied=dict(ns['__builtins__']);ns={'__name__':'source_control','__builtins__':copied}
        exec(compile(raw,'source-control.py','exec'),ns)
        sites=O.SourceSites();sites.bind(ns,raw,P.sha(raw),'source-control.py','control')
        class ForeignError(Exception):pass
        copied['RuntimeError']=ForeignError
        try:sites.invoke(ns['check'],rows.append)
        except ForeignError as error:self.assertIsNone(sites.describe(error))
        else:self.fail('original code did not raise foreign resolution')
        self.assertEqual(rows,[])
        copied['RuntimeError']=RuntimeError
        ns['RuntimeError']=RuntimeError
        self.assertRaises(RuntimeError,sites.invoke,ns['check'],rows.append)
        self.assertEqual(rows,[])

    def test_foreign_builtin_resolution_before_binding_is_refused(self):
        import builtins
        class ForeignError(Exception):pass
        raw=b'def check():\n raise RuntimeError("fixed-source")\n'
        copied=dict(builtins.__dict__,RuntimeError=ForeignError)
        ns={'__builtins__':copied};exec(compile(raw,'source-control.py','exec'),ns)
        self.assertRaises(ValueError,O.SourceSites().bind,ns,raw,P.sha(raw),'source-control.py','control')

    def test_existing_trace_and_failed_sink_preserve_original(self):
        raw=b'def check():\n raise RuntimeError("known-source")\n'
        ns,sites=bound(raw);rows=[]
        previous=lambda frame,event,arg:previous
        sys.settrace(previous)
        try:self.assertRaises(RuntimeError,sites.invoke,ns['check'],rows.append);self.assertIs(sys.gettrace(),previous)
        finally:sys.settrace(None)
        self.assertEqual(rows,[])
        def broken(row):raise ValueError('sink')
        try:sites.invoke(ns['check'],broken)
        except RuntimeError as e:self.assertEqual(e.args,('known-source',));self.assertIsNotNone(sites.describe(e))
        self.assertIsNone(sys.gettrace())

    def test_trace_install_and_restoration_failure_preserve_same_primary(self):
        raw=b'def check(error):\n raise error\n';ns,sites=bound(raw);error=RuntimeError('control')
        with mock.patch.object(sys,'settrace',side_effect=ValueError('trace unavailable')):
            try:sites.invoke(ns['check'],lambda row:None,error)
            except RuntimeError as actual:self.assertIs(actual,error)
        original=sys.settrace;calls=[]
        def fail_restore(value):
            calls.append(value)
            if len(calls)>1:raise ValueError('restore unavailable')
            return original(value)
        try:
            with mock.patch.object(sys,'settrace',side_effect=fail_restore):
                try:sites.invoke(ns['check'],lambda row:None,error)
                except RuntimeError as actual:self.assertIs(actual,error)
        finally:original(None)

    def driver(self,temporary,serial_started=False):
        vmtest,vmraw=load(ROOT/'tools/lib/vmtest.py','vmtest')
        raw=P.embedded_driver((ROOT/'tools/test-install.sh').read_bytes())
        prefix=raw[:raw.index(b'rc = 0\nif stage in')]
        env={'OUT':str(temporary),'FIRMWARE':'bios','STAGE':'install','MEMORY':'4096','SMP':'2','ACCEL':'kvm','INSTALL_TIMEOUT':'2400','LUKS_PASSPHRASE':'control-only','USER_PASSWORD':'control-only'}
        with mock.patch.dict(os.environ,env,clear=True):
            ns={'__name__':'source_control'};exec(compile(prefix,'<string>','exec'),ns)
        class VM:
            proc=types.SimpleNamespace(poll=lambda:0,returncode=0)
            def alive(self):return False
            def shot(self,name):return None
            def keys(self,*args):pass
            def type_text(self,*args,**kwargs):pass
            def wait_exit(self,seconds):return True
        vm=VM();clean=[]
        ns.update(dictation_acquire_vm=lambda *a:vm,qemu_argv=lambda *a:[],wait_menu=lambda *a:False,
            open_terminal=lambda *a:None,dictation_launch_desktop=lambda *a:None,
            dictation_install_wait_vm_stage=lambda *a:None,close_taskbar_vm=lambda *a:clean.append(a),
            record_native_stop=lambda *a:None,wait_for=lambda *a:None,
            time=types.SimpleNamespace(time=lambda:0,sleep=lambda n:None),log=lambda msg:None,
            vmtest=types.SimpleNamespace(serial_has=lambda *a:serial_started,serial_value=lambda *a:None,classify=lambda *a:'login'))
        sites=O.SourceSites();sites.bind(ns,raw,P.sha(raw),'<string>','install-driver')
        return ns,sites,clean,raw

    def test_actual_original_install_nonstart_and_missing_exit_sites(self):
        with tempfile.TemporaryDirectory() as td:
            ns,sites,clean,raw=self.driver(pathlib.Path(td));rows=[]
            self.assertEqual(sites.invoke(ns['stage_install'],rows.append),90)
            self.assertEqual(rows[0]['site']['source_line'],553);self.assertEqual(len(clean),1)
            ns,sites,clean,raw=self.driver(pathlib.Path(td),True)
            # The original loop must execute once to observe its unchanged start marker.
            ns['dictation_acquire_vm']=lambda *a:types.SimpleNamespace(alive=lambda:True,shot=lambda *a:None,keys=lambda *a:None,type_text=lambda *a,**kw:None,proc=types.SimpleNamespace(poll=lambda:0))
            ns['time']=types.SimpleNamespace(time=iter([0,0,0,0,0,0,0,0,3000,3000,3000]).__next__,sleep=lambda n:None)
            sites=O.SourceSites();sites.bind(ns,raw,P.sha(raw),'<string>','install-driver');rows=[]
            self.assertEqual(sites.invoke(ns['stage_install'],rows.append),91)
            self.assertEqual(rows[0]['site']['source_line'],573);self.assertEqual(len(clean),1)

    def test_actual_original_boot_false_flags_and_return(self):
        with tempfile.TemporaryDirectory() as td:
            ns,sites,clean,raw=self.driver(pathlib.Path(td));rows=[]
            self.assertEqual(sites.invoke(ns['stage_boot'],rows.append),1)
            self.assertEqual(rows[0]['site']['source_line'],794)
            self.assertEqual([x['source_line'] for x in rows[0]['executed_false_flag_sites']],[634,671,786])
            self.assertEqual(len(clean),1)

    def test_whole_original_driver_entry_and_unchanged_vm_tuple(self):
        with tempfile.TemporaryDirectory() as td:
            vmtest,vmraw=load(ROOT/'tools/lib/vmtest.py','vmtest');calls=[]
            class NoVM:
                def __init__(self,argv,qmp,name):calls.append((argv,qmp,name))
                def alive(self):return False
                def shot(self,*args):return None
                def keys(self,*args):pass
                def type_text(self,*args,**kwargs):pass
                def quit(self):calls.append('quit')
            env={'OUT':td,'FIRMWARE':'bios','STAGE':'install','MEMORY':'4096','SMP':'2','ACCEL':'kvm','INSTALL_TIMEOUT':'2400','LUKS_PASSPHRASE':'control-only','USER_PASSWORD':'control-only'}
            raw=P.embedded_driver((ROOT/'tools/test-install.sh').read_bytes());rows=[]
            with mock.patch.dict(os.environ,env,clear=True),mock.patch.object(vmtest,'VM',NoVM),mock.patch.object(vmtest,'OUT',td),mock.patch('time.sleep',lambda n:None),contextlib.redirect_stdout(io.StringIO()):
                try:O.run_original_driver(raw,{'__name__':'__main__'},vmtest,rows.append,P.sha(raw),vmraw,P.sha(vmraw))
                except SystemExit as error:self.assertEqual(error.code,90)
            self.assertEqual(rows[0]['site']['source_line'],553);self.assertEqual(calls[-1],'quit')
            argv=calls[0][0];self.assertIn('user,id=net0,restrict=on',argv);self.assertNotIn('if=pflash',str(argv))
            self.assertEqual(argv[argv.index('-cpu')+1],'max');self.assertEqual(calls[0][1:],('/tmp/qmp-install.sock','install'))

    def test_exact_original_guest_primary_cause_before_generic_assertion(self):
        g,raw=load(OLD/'guest.py','bios_observer_guest_control')
        class FixedPath:
            def __init__(self,*args):pass
            @property
            def parent(self):return self
            def __eq__(self,other):return isinstance(other,FixedPath)
        g.Path=FixedPath;g.os=types.SimpleNamespace(geteuid=lambda:0)
        g.text=lambda argv:'qemu' if argv==['systemd-detect-virt'] else 'Disabled'
        g.firmware=lambda stage:{}
        manifest=json.loads((OLD/'execution-manifest.json').read_bytes());ctx={'schema':'arctic-final-bios-context-v1','nonce':'a'*32,'execution_sha':'b'*40,'source_sha':manifest['image']['source_sha'],'iso_sha256':manifest['image']['sha256'],'probe_sha256':P.sha(raw),'native_sha256':'c'*64,'security_sha256':'d'*64}
        sites=O.SourceSites();sites.bind(g.__dict__,raw,P.sha(raw),g.__file__,'bios-probe');rows=[];finish=[]
        interval=lambda:types.SimpleNamespace(finish=lambda:finish.append(True) or {})
        try:sites.invoke(g.main,rows.append,'live',ctx,object(),interval)
        except RuntimeError as e:error=e
        self.assertEqual(error.args,('bios-check-failed',));self.assertEqual(finish,[True])
        self.assertEqual(rows[0]['site']['fixed_assertion_label'],'bios-check-failed')
        self.assertEqual(rows[0]['retained_original_primary_site']['fixed_assertion_label'],'selinux-enforcing')

    def test_actual_owned_process_host_failure_and_finite_capture(self):
        c,craw=load(OLD/'common.py','common');load(OLD/'compose.py','compose');r,rraw=load(OLD/'run.py','bios_observer_run_control')
        sites=O.SourceSites();sites.bind(c.__dict__,craw,P.sha(craw),c.__file__,'bios-common');sites.bind(r.__dict__,rraw,P.sha(rraw),r.__file__,'bios-host')
        with tempfile.TemporaryDirectory() as td:
            rows=[];log=pathlib.Path(td)/'private.log';argv=[sys.executable,'-c','raise SystemExit(23)']
            try:P.capture_failed_execute(r.execute,sites,rows.append,argv,log,10,td,os.environ.copy(),'a'*32,[])
            except RuntimeError as e:error=e
            self.assertEqual(error.args,('BIOS host invocation failed',))
            self.assertEqual(rows[0]['outer_source_site']['fixed_assertion_label'],'BIOS host invocation failed')
            self.assertEqual(rows[0]['finite_inner_source_records'],[]);self.assertIsNotNone(sites.describe(error))

    def test_closed_parser_rejects_unknown_private_duplicate_and_wrong_nonce(self):
        raw=b'def stage_install():\n return 90\n';site=O.site_inventory(raw,'install-driver')[0];nonce='a'*32
        row={'schema':'arctic-bios-inner-source-cause-v1','nonce':nonce,'cause':{'event':'nonzero-original-stage-return','site':site,'executed_false_flag_sites':[]},'release_acceptance':False}
        encode=lambda x:b'ARCTIC-BIOS-INNER-CAUSE '+json.dumps(x).encode()+b'\n'
        self.assertEqual(P.finite_inner_rows(encode(row),nonce,[site]),[row])
        for value in (dict(row,nonce='b'*32),dict(row,private='operand'),dict(row,cause=dict(row['cause'],operand='private'))):self.assertEqual(P.finite_inner_rows(encode(value),nonce,[site]),[])
        duplicate=b'ARCTIC-BIOS-INNER-CAUSE '+json.dumps(row).encode().replace(b'"nonce":',b'"nonce":"bad","nonce":',1)
        self.assertEqual(P.finite_inner_rows(duplicate,nonce,[site]),[])
        wrong=dict(site,source_line=True);self.assertFalse(P.finite_site(wrong,[dict(site,source_line=1)]))

    def test_transport_only_shell_and_guest_modules_exact(self):
        old=json.loads((OLD/'execution-manifest.json').read_bytes());source_dir=pathlib.Path(__file__).parent
        manifest={'original_execution_files':old['execution_files'],'driver_sha256':P.sha(P.embedded_driver((ROOT/'tools/test-install.sh').read_bytes())),
            'observer_execution_files':{'tools/final-bios-failure-observer/'+n:P.sha((source_dir/n).read_bytes()) for n in ('observer.py','driver-entry.py')}}
        with tempfile.TemporaryDirectory() as td:
            staged=P.stage_harness(ROOT,pathlib.Path(td)/'owned',manifest,source_dir);raw=staged.read_bytes();original=(ROOT/'tools/test-install.sh').read_bytes()
            self.assertEqual(raw.replace(b'python3 /arctic-lib/driver-entry.py || rc=$?',b'python3 -c "$DRIVER" || rc=$?',1),original)
            self.assertEqual(P.embedded_driver(raw),P.embedded_driver(original))
        # Compose a real original Source CD program, but never execute its guest.
        c,_=load(OLD/'common.py','common');compose,_=load(OLD/'compose.py','compose')
        native=subprocess.check_output(['git','show',old['image']['source_sha']+':tools/native-functional/native_smoke.py'],cwd=ROOT)
        ctx={'probe_sha256':P.sha((OLD/'guest.py').read_bytes()),'native_sha256':P.sha(native),'security_sha256':P.sha((OLD/'security.py').read_bytes())}
        with tempfile.TemporaryDirectory() as td:
            source=pathlib.Path(td)/'source';(source/'tools/native-functional').mkdir(parents=True);(source/'tools/native-functional/native_smoke.py').write_bytes(native)
            output=pathlib.Path(td)/'guest.py';compose.compose(source,OLD/'guest.py',OLD/'security.py',ctx,output);original=output.read_bytes()
            derived=P.derive_guest(original,{'bios-probe':(OLD/'guest.py').read_bytes(),'native-source':native},(source_dir/'observer.py').read_bytes(),ctx,{'bios-probe':ctx['probe_sha256'],'native-source':ctx['native_sha256']})
            compile(derived,'guest-derived.py','exec')
            for node in ast.walk(ast.parse(original)):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='b64decode' and isinstance(node.args[0],ast.Constant):self.assertIn(node.args[0].value.encode(),derived)
            self.assertIn(b'print("ARCTIC-FINAL-BIOS-FAILED",flush=True)',derived)
            self.assertIn(b'raise SystemExit(result)',derived)

if __name__=='__main__':unittest.main()
