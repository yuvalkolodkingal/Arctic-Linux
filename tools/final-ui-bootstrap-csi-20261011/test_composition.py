"""New UI joins only; accepted Native/CSI/conditional-snapshot controls reused."""
import ast,copy,hashlib,importlib.util,json,os,signal,subprocess,sys,tempfile,types,unittest
from pathlib import Path
from unittest import mock
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import common as C
import run as R

class NewJoins(unittest.TestCase):
    def value(self):return json.loads((HERE/'execution-manifest.json').read_bytes())
    def fixture(self):
        observed,published,state,helper,originals,buffers=R.main_adapter(self.value())
        context=dict(schema='arctic-final-installed-ui-context-v1',nonce='a'*32,execution_sha='0'*40,
            source_sha=C.IMAGE['source_sha'],iso_sha256=C.IMAGE['sha256'],native_sha256='0'*64,ui_sha256='0'*64)
        return observed,published,state,helper,originals,buffers,context
    def test_disabled_original_codes_budgets_and_whole_selected_modules(self):
        value=self.value();self.assertEqual(len(value['execution_files']),49);self.assertEqual(len(value['source_files']),20)
        self.assertIs(value['ready'],False)
        with self.assertRaises(RuntimeError):C.manifest(value,True)
        observed,published,state,h,o,b,c=self.fixture()
        self.assertIs(observed.main.__code__,published.main.__code__);self.assertIs(observed.screen.__code__,published.screen.__code__)
        self.assertIs(observed.C.decode,published.C.decode)
        self.assertEqual(hashlib.sha256(b[C.COMPONENT_PREFIX+'native_bootstrap_observer.py']).hexdigest(),'6b5627a78cda5a3c94ff9ec3dae4c7af667a6add70cc78b69942f91586fbe40c')
        self.assertEqual(hashlib.sha256(b[C.COMPONENT_PREFIX+'vmtest-observed.py']).hexdigest(),'e3e469bdfb3510c47aa51986cb09a3ef155c73b0496bc4a45dc2db07ebe670e6')
        self.assertEqual((value['ui_seconds'],value['install_timeout'],value['harness_seconds']),(720,2400,4200))
    def test_actual_UI_shell_inverse_and_Bash_syntax_only_host_forward_mount_changed(self):
        _,_,_,h,o,b,c=self.fixture();raw=b['tools/test-install.sh'];revised=h.private_harness(raw)
        forwarding=b'  -e ARCTIC_DICTATION_HOST_TOKEN="${ARCTIC_DICTATION_HOST_TOKEN:-}" '+bytes([92,10])
        forwarded=forwarding+b'  -e ARCTIC_NATIVE_BOOTSTRAP_TOKEN="${ARCTIC_NATIVE_BOOTSTRAP_TOKEN:-}" '+bytes([92,10])
        inverse=revised.replace(forwarded,forwarding,1).replace(b'-v "$ARCTIC_UI_BOOTSTRAP_LIB:/arctic-lib:ro"',b'-v "$HERE/lib:/arctic-lib:ro"',1).replace(h.PRIVATE_TAIL.encode(),h.FAILED_TAIL.encode(),1)
        self.assertEqual(inverse,raw);self.assertEqual(revised.count(b'-e ARCTIC_NATIVE_BOOTSTRAP_TOKEN='),1)
        self.assertEqual(subprocess.run(['bash','-n'],input=revised,stdout=subprocess.PIPE,stderr=subprocess.PIPE).returncode,0)
        self.assertNotIn(b'native-bootstrap-token',revised);self.assertNotIn(b'cp "$HERE/lib/native_bootstrap_observer.py"',revised)
    def test_owned_two_file_Lib_selection_and_mutated_or_foreign_cleanup_denied(self):
        _,p,_,h,o,b,c=self.fixture()
        with tempfile.TemporaryDirectory()as directory:
            private=Path(directory);os.chmod(private,0o700)
            holder,generation,files=h.bootstrap_library(private,p.C)
            self.assertEqual(set(files),{'vmtest.py','native_bootstrap_observer.py'})
            self.assertTrue(all((holder/n).stat().st_mode&0o777==0o600 for n in files))
            extra=holder/'foreign';extra.write_bytes(b'unowned-generation');extra.chmod(0o600)
            with self.assertRaises(ValueError):h.remove_bootstrap_library(holder,generation,files)
            extra.unlink();changed=holder/'vmtest.py';old=changed.read_bytes();changed.write_bytes(old+b'\n')
            with self.assertRaises(ValueError):h.remove_bootstrap_library(holder,generation,files)
            changed.write_bytes(old)
            # Restoration changes generation; release a newly acquired exact owned fixture.
            files['vmtest.py']=(old,changed.lstat());h.remove_bootstrap_library(holder,generation,files)
            self.assertFalse(holder.exists())
    def projected(self,h,p,o,b,c,raw,primary=None):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        private=Path(directory.name);os.chmod(private,0o700);log=private/'harness.log';o.write_exclusive(log,raw)
        output=h.project_ui_bootstrap(log,c,p.C,b[C.COMPONENT_PREFIX+'scanner.py'],primary)
        return output,log
    def test_actual_harness_whitelist_dedup_and_no_raw_UART_or_unknown_export(self):
        _,p,_,h,o,b,c=self.fixture()
        token=c['nonce'].encode();host=b'ARCTIC-DICTATION-HOST-STAGE '+token+b' install-terminal\n'
        row=b'ARCTIC-NATIVE-BOOTSTRAP '+token+b' {"role":"input","stage":"event-returned","error_class":"none","guard_site":"unknown"}\n'
        outputs=[];original=o.read_regular;seen=[]
        def audit(path,*args,**kwargs):seen.append(str(path));return original(path,*args,**kwargs)
        with mock.patch.object(o,'read_regular',audit):
            for raw in (host+row+b'password=synthetic-privateA\n',host*7+row*5+b'password=longer-privateB\n'):
                output,_=self.projected(h,p,o,b,c,raw);self.assertIsNotNone(output);outputs.append(json.loads(output.read_bytes()))
        self.assertEqual(outputs[0],outputs[1]);self.assertFalse(any('serial-'in name for name in seen))
        self.assertNotIn('private',json.dumps(outputs));self.assertFalse(outputs[0]['raw_UART_used'])
        native=outputs[0]['Source_harness_observation'];self.assertEqual(native['input_states'],{'harness':'projected','serial-install':'not-observed','serial-boot':'not-observed'})
        self.assertEqual(native['host_stages'],['install-terminal']);self.assertEqual(len(native['producer_categories']),1)
    def test_malformed_correlated_record_withholds_categories_and_typed_public_context_gate(self):
        _,p,_,h,o,b,c=self.fixture();raw=b'ARCTIC-NATIVE-BOOTSTRAP '+c['nonce'].encode()+b' {"role":"input","stage":"unknown","error_class":"none","guard_site":"unknown"}\n'
        output,_=self.projected(h,p,o,b,c,raw);self.assertIsNotNone(output);value=json.loads(output.read_bytes())
        self.assertEqual(value['Source_harness_observation']['input_states']['harness'],'rejected')
        self.assertEqual(value['Source_harness_observation']['producer_categories'],[])
        module,_=h.bootstrap_module()
        for mutate in (lambda v:v.update(runtime_acceptance=0),lambda v:v['context'].update(nonce='b'*32),lambda v:v['Source_harness_observation']['input_states'].update(**{'serial-boot':'projected'}),lambda v:v['Source_harness_observation'].update(host_stages=['unknown']),lambda v:v.update(private='unfiltered')):
            bad=copy.deepcopy(value);mutate(bad)
            with self.assertRaises(ValueError):h.validate_bootstrap_observation(bad,c,module)
    def test_real_deferred_SIGINT_closes_reader_and_original_primary_retained(self):
        _,p,_,h,o,b,c=self.fixture();raw=b'ARCTIC-DICTATION-HOST-STAGE '+c['nonce'].encode()+b' install-terminal\n'
        original_read=os.read;original_close=os.close;active=[];closed=[];sent=[False]
        # Exact owned-FD primitive remains real; inject a signal during its read.
        def read(fd,n):
            result=original_read(fd,n)
            if result==raw and not sent[0]:sent[0]=True;active.append(fd);os.kill(os.getpid(),signal.SIGINT)
            return result
        def close(fd):closed.append(fd);return original_close(fd)
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        private=Path(directory.name);os.chmod(private,0o700);log=private/'harness.log';o.write_exclusive(log,raw)
        with mock.patch.object(os,'read',read),mock.patch.object(os,'close',close),self.assertRaises(KeyboardInterrupt):
            h.project_ui_bootstrap(log,c,p.C,b[C.COMPONENT_PREFIX+'scanner.py'])
        self.assertTrue(sent[0]);self.assertTrue(active and active[0]in closed)
        sent[0]=False;primary=RuntimeError('owned synthetic primary')
        with mock.patch.object(os,'read',read),mock.patch.object(os,'close',close):
            result=h.project_ui_bootstrap(log,c,p.C,b[C.COMPONENT_PREFIX+'scanner.py'],primary)
        self.assertIsNone(result);self.assertTrue(sent[0]);self.assertEqual(str(primary),'owned synthetic primary')
    def test_actual_dispatch_changes_only_owned_Lib_env_and_attempts_all_cleanup(self):
        _,p,_,h,o,b,c=self.fixture();raw=b['tools/test-install.sh'];scanner=b[C.COMPONENT_PREFIX+'scanner.py']
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);os.chmod(root,0o700);(root/'tools/lib').mkdir(parents=True)
            o.write_exclusive(root/'tools/lib/vmtest.py',b['tools/lib/vmtest.py'])
            private=root/'private';private.mkdir(mode=0o700);log=private/'harness.log'
            common=types.SimpleNamespace(ROOT=root,load=p.C.load)
            argv=['bash',str(root/'tools/test-install.sh'),'--memory','4096'];env={'ARCTIC_DICTATION_HOST_TOKEN':c['nonce'],'preserved':'opaque'};obs={'stage':'unacquired'};state={};calls=[]
            primary=RuntimeError('exact source fixture primary');cancel=KeyboardInterrupt()
            def original(changed,received_log,seconds,cwd,selected,received_obs):
                calls.append(True);self.assertEqual(changed[:1]+changed[2:],argv[:1]+argv[2:]);self.assertEqual((seconds,cwd),(4200,root))
                self.assertIs(received_log,log);self.assertIs(received_obs,obs);self.assertEqual(selected['preserved'],'opaque')
                self.assertEqual(selected[h.BOOTSTRAP_ENV],c['nonce']);self.assertNotIn(h.BOOTSTRAP_ENV,env)
                library=Path(selected['ARCTIC_UI_BOOTSTRAP_LIB']);self.assertEqual({x.name for x in library.iterdir()},{'vmtest.py','native_bootstrap_observer.py'})
                self.assertEqual(Path(changed[1]).read_bytes(),h.private_harness(raw));raise primary
            # Optional projection cancellation cannot replace primary; both cleanups run.
            with mock.patch.object(h,'project_ui_bootstrap',side_effect=cancel),self.assertRaises(RuntimeError)as caught:
                h.invoke_bootstrap_harness(original,argv,log,4200,root,env,obs,c,common,raw,scanner,state)
            self.assertIs(caught.exception,primary);self.assertEqual(calls,[True]);self.assertFalse((private/'ui-bootstrap-lib').exists())
            self.assertFalse((root/'tools'/('.test-install-private-uart-'+c['nonce']+'.sh')).exists())
            # Foreign preexisting library refuses before the child and still removes our script.
            foreign=private/'ui-bootstrap-lib';foreign.mkdir(mode=0o700)
            with self.assertRaises(FileExistsError):h.invoke_bootstrap_harness(original,argv,log,4200,root,env,obs,c,common,raw,scanner,state)
            self.assertEqual(calls,[True]);self.assertTrue(foreign.exists())
            self.assertFalse((root/'tools'/('.test-install-private-uart-'+c['nonce']+'.sh')).exists())

    def test_second_Source_read_failure_cleans_partial_owned_setup_and_preserves_error(self):
        _,p,_,h,o,b,c=self.fixture();original_read=o.read_regular
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);root.chmod(0o700);(root/'tools/lib').mkdir(parents=True)
            o.write_exclusive(root/'tools/lib/vmtest.py',b['tools/lib/vmtest.py'])
            private=root/'private';private.mkdir(mode=0o700);log=private/'harness.log'
            primary=OSError('owned synthetic setup failure');called=[]
            def fail_second(path,limit):
                if Path(path)==Path(h.__file__).with_name('native_bootstrap_observer.py'):raise primary
                return original_read(path,limit)
            with mock.patch.object(o,'read_regular',fail_second),self.assertRaises(OSError)as caught:
                h.invoke_bootstrap_harness(lambda *args:called.append(True),['bash','unused'],log,4200,root,
                    {'ARCTIC_DICTATION_HOST_TOKEN':c['nonce']},None,c,types.SimpleNamespace(ROOT=root),
                    b['tools/test-install.sh'],b[C.COMPONENT_PREFIX+'scanner.py'],{})
            self.assertIs(caught.exception,primary);self.assertEqual(called,[])
            self.assertFalse((private/'ui-bootstrap-lib').exists())
            self.assertFalse((root/'tools'/('.test-install-private-uart-'+c['nonce']+'.sh')).exists())

    def test_real_SIGINT_during_each_owned_setup_write_closes_FD_and_cleans_all_setup(self):
        _,p,_,h,o,b,c=self.fixture();actual_write=os.write;actual_close=os.close
        for selected in (h.private_harness(b['tools/test-install.sh']),b[C.COMPONENT_PREFIX+'vmtest-observed.py']):
            with self.subTest(selected_script=selected.startswith(b'#!/usr/bin/env bash')):
                with tempfile.TemporaryDirectory()as directory:
                    root=Path(directory);root.chmod(0o700);(root/'tools/lib').mkdir(parents=True)
                    o.write_exclusive(root/'tools/lib/vmtest.py',b['tools/lib/vmtest.py'])
                    private=root/'private';private.mkdir(mode=0o700);log=private/'harness.log'
                    sent=[];closed=[];called=[]
                    def scheduled_write(fd,data):
                        count=actual_write(fd,data)
                        if bytes(data)==selected and not sent:sent.append(fd);os.kill(os.getpid(),signal.SIGINT)
                        return count
                    def close(fd):closed.append(fd);return actual_close(fd)
                    with mock.patch.object(os,'write',scheduled_write),mock.patch.object(os,'close',close),self.assertRaises(KeyboardInterrupt):
                        h.invoke_bootstrap_harness(lambda *args:called.append(True),['bash','unused'],log,4200,root,
                            {'ARCTIC_DICTATION_HOST_TOKEN':c['nonce']},None,c,types.SimpleNamespace(ROOT=root),
                            b['tools/test-install.sh'],b[C.COMPONENT_PREFIX+'scanner.py'],{})
                    self.assertTrue(sent);self.assertIn(sent[0],closed);self.assertEqual(called,[])
                    self.assertFalse((private/'ui-bootstrap-lib').exists())
                    self.assertFalse((root/'tools'/('.test-install-private-uart-'+c['nonce']+'.sh')).exists())

    def test_partial_write_failure_and_foreign_setup_paths_preserve_ownership(self):
        _,p,_,h,o,b,c=self.fixture();actual_write=os.write
        with tempfile.TemporaryDirectory()as directory:
            private=Path(directory);private.chmod(0o700);path=private/'owned-script';owned={};primary=OSError('owned partial write')
            calls=[]
            def short_then_fail(fd,data):
                if calls:raise primary
                calls.append(fd);return actual_write(fd,memoryview(data)[:7])
            with mock.patch.object(os,'write',short_then_fail),self.assertRaises(OSError)as caught:
                h.write_setup_owned(path,b'bounded-owned-Source',owned)
            self.assertIs(caught.exception,primary);self.assertFalse(path.exists());self.assertEqual(owned,{})
            o.write_exclusive(path,b'foreign-retained-Source');prior=path.lstat()
            with self.assertRaises(FileExistsError):h.write_setup_owned(path,b'new-Source',owned)
            self.assertEqual(path.read_bytes(),b'foreign-retained-Source');self.assertTrue(o.same(prior,path.lstat()))
            self.assertEqual(owned,{})

    def test_real_SIGINT_at_actual_Lib_return_registers_caller_ownership_before_delivery(self):
        _,p,_,h,o,b,c=self.fixture()
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);root.chmod(0o700);(root/'tools/lib').mkdir(parents=True)
            o.write_exclusive(root/'tools/lib/vmtest.py',b['tools/lib/vmtest.py'])
            private=root/'private';private.mkdir(mode=0o700);log=private/'harness.log';called=[];sent=[]
            library_code=h.bootstrap_library.__code__;invoke_code=h.invoke_bootstrap_harness.__code__
            def profile(frame,event,result):
                if event=='return'and frame.f_code is library_code and not sent:
                    self.assertIs(frame.f_globals,h.__dict__);self.assertIs(frame.f_back.f_code,invoke_code)
                    self.assertIs(frame.f_back.f_globals,h.__dict__);self.assertEqual(set(result[2]),{'vmtest.py','native_bootstrap_observer.py'})
                    sent.append(True);os.kill(os.getpid(),signal.SIGINT)
            previous=sys.getprofile()
            try:
                sys.setprofile(profile)
                with self.assertRaises(KeyboardInterrupt):
                    h.invoke_bootstrap_harness(lambda *args:called.append(True),['bash','unused'],log,4200,root,
                        {'ARCTIC_DICTATION_HOST_TOKEN':c['nonce']},None,c,types.SimpleNamespace(ROOT=root),
                        b['tools/test-install.sh'],b[C.COMPONENT_PREFIX+'scanner.py'],{})
            finally:sys.setprofile(previous)
            self.assertEqual(sent,[True]);self.assertEqual(called,[])
            self.assertFalse((private/'ui-bootstrap-lib').exists())
            self.assertFalse((root/'tools'/('.test-install-private-uart-'+c['nonce']+'.sh')).exists())

if __name__=='__main__':unittest.main()
