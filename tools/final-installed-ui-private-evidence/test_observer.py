"""Public Source and small synthetic fixtures only; no VM or old originals."""
import ast,base64,contextlib,hashlib,io,json,os,signal,subprocess,sys,tempfile,types,unittest,zlib
from pathlib import Path
from unittest import mock
from PIL import Image,ImageDraw,ImageFont
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import observer as A,originals as O
CACHE=HERE.parents[1]/'out/ui-private-evidence/public'
if not CACHE.is_dir():CACHE=HERE.parents[1]
P=A.PREFIX

def modules():
    C=A.load((CACHE/P/'common.py').read_bytes(),CACHE/P/'common.py','ui_fixture_common')
    saved={n:sys.modules.get(n,A.ABSENT)for n in('common','compose')}
    try:
        sys.modules['common']=C;sys.modules['compose']=A.load((CACHE/P/'compose.py').read_bytes(),CACHE/P/'compose.py','ui_fixture_compose')
        R=A.load((CACHE/P/'run.py').read_bytes(),CACHE/P/'run.py','ui_fixture_run')
    finally:
        for n,v in saved.items():
            if v is A.ABSENT:sys.modules.pop(n,None)
            else:sys.modules[n]=v
    S=A.load((CACHE/A.SCANNER).read_bytes(),CACHE/A.SCANNER,'ui_fixture_scanner')
    H=A.load((HERE/'match-diagnostic.py').read_bytes(),HERE/'match-diagnostic.py','ui_fixture_match')
    return C,R,S,H

def context():
    return dict(schema='arctic-final-installed-ui-context-v1',nonce='1'*32,execution_sha=A.BASE,
        source_sha='326690f173d4dc4f049f43e046c8380e66825a07',
        iso_sha256='807eaaa64ab8480ec2b18bc8434fd5e37d82c41b73a3e0a6f002c35d152ba54c',
        native_sha256='d7c69563a4a9908d4e4c8c937222f7e814440bfbb6c06de07fbd32b7e0caa4f8',
        ui_sha256='06767f6d03660c8eafdb163505958f130c5a7be212ed49f49aafb8fded325fa7')

def png(text=None):
    image=Image.new('RGB',(1280,720),'white')
    if text:ImageDraw.Draw(image).text((90,150),text,fill='black',font=ImageFont.truetype('DejaVuSans.ttf',44))
    raw=io.BytesIO();image.save(raw,format='PNG');return raw.getvalue()

def wire(ctx=None,members=None):
    ctx=context()if ctx is None else ctx
    report=dict(schema='arctic-final-installed-ui-report-v1',context=ctx,status='failed',phase='appearance',
        error_class='RuntimeError',checks=[],selinux='Enforcing',visual_review_required=True,release_acceptance=False)
    members={'report.json':json.dumps(report).encode(),'01-appearance.png':png()}if members is None else members
    chunks=[];inventory=[]
    for name,data in members.items():
        compressed=zlib.compress(data);parts=[compressed[i:i+32768]for i in range(0,len(compressed),32768)]
        inventory.append(dict(name=name,bytes=len(data),sha256=O.sha(data),compressed_bytes=len(compressed),chunks=len(parts)))
        for i,part in enumerate(parts):chunks.append('ARCTIC-FINAL-UI-CHUNK '+json.dumps(dict(name=name,index=i,data=base64.b64encode(part).decode())))
    return ('public-user@example.invalid\nARCTIC-FINAL-UI-BEGIN '+json.dumps(ctx)+'\n'+'\n'.join(chunks)+
        '\nARCTIC-FINAL-UI-MANIFEST '+json.dumps(inventory)+'\nARCTIC-FINAL-UI-END '+json.dumps(ctx)+'\n').encode()

def finite(S,H):
    raw=b'public-user@example.invalid\n'
    try:
        with contextlib.redirect_stdout(io.StringIO()):S.external_text(raw)
    except RuntimeError as error:
        owner=A.OwnedSource(S.__dict__,(CACHE/A.SCANNER).read_bytes(),S.__file__,'original-scanner')
        tb=error.__traceback__
        while tb is not None:
            if tb.tb_frame.f_code is S.reject_sensitive_match.__code__:
                vocabulary={n.value for n in ast.walk(ast.parse((HERE/'match-diagnostic.py').read_bytes()))if isinstance(n,ast.Constant)and type(n.value)is str}|{'external-rule-'+format(n,'03d')for n in range(1,11)}
                return dict(schema='arctic-ui-strict-original-source-failure-v1',original_source_site=owner.site(tb.tb_frame,tb.tb_lasti,{'raise'}),
                    original_uart_stage='live',same_rejected_match=A.finite_match(H,vocabulary,S,tb.tb_frame),
                    actual_raising_Source_Code_globals_owned=True,exception_unchanged=True,
                    actual_runtime_cause_proven=False,complete_uart_admitted=False,release_acceptance=False)
            tb=tb.tb_next
    raise AssertionError('Synthetic original scanner did not reject')

class Controls(unittest.TestCase):
    def test_disabled_build_whole_main_code_and_namespace(self):
        manifest=json.loads((HERE/'execution-manifest.json').read_bytes())
        (staged,state),original=A.build(manifest,CACHE)
        self.assertIs(staged.main.__code__,original.main.__code__)
        self.assertIsNot(staged.main.__globals__,original.main.__globals__)
        self.assertIs(staged.C.decode,original.C.decode)
        self.assertIsNone(state['finite'])
        with self.assertRaises(SystemExit):A.main()
        bad=dict(manifest,ready=True)
        with self.assertRaises(ValueError):A.build(bad,CACHE)

    def test_exact_separate_transport_inverse_preserves_whole_gate(self):
        C,R,S,H=modules();raw=(CACHE/P/'common.py').read_bytes()
        parser,derived,replacements=A.diagnostic_transport(C,raw)
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(RuntimeError):C.decode(wire(),context(),S,Path('/unused'))
        value,inventory,decoded=parser(wire(),context(),S)
        self.assertEqual(value['status'],'failed');self.assertEqual(set(decoded),{'report.json','01-appearance.png'})
        original=''.join(raw.decode().splitlines(keepends=True)[next(n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef)and n.name=='decode').lineno-1:next(n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef)and n.name=='decode').end_lineno])
        # The deleted gate is inserted at the exact original byte position.
        restored=derived.replace(replacements[0][1],replacements[0][0],1)
        anchor="    require(type(wire) is bytes and 0 < len(wire) <= 256*1024*1024, 'UART bound differs')\n"
        restored=restored.replace(anchor,anchor+replacements[1][0],1).replace(replacements[2][1],replacements[2][0],1)
        self.assertEqual(restored,original)
        for changed in (wire().replace(b'"index": 0',b'"index": true',1),wire().replace(b'"chunks": 1',b'"chunks": 2',1),wire().replace(b'"selinux": "Enforcing"',b'"selinux": "Permissive"',1)):
            if changed==wire():continue
            with self.assertRaises((RuntimeError,ValueError)):parser(changed,context(),S)

    def test_original_screen_no_ocr_counterexample_and_corrected_success_denial(self):
        C,R,S,H=modules()
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);source=root/'public';source.mkdir(mode=0o700);(source/'original-ui').mkdir(mode=0o700)
            O.write_exclusive(source/'host-status.json',b'{"status":"failed"}\n')
            original=png('password = synthetic-private-fixture');O.write_exclusive(source/'original-ui/01-appearance.png',original)
            R.screen(source,root/'old');self.assertEqual((root/'old/original-ui/01-appearance.png').read_bytes(),original)
            admitted=[]
            with self.assertRaises(ValueError):A.screen(R.screen,source,root/'new',root/'absent',C,(CACHE/P/'common.py').read_bytes(),S,(CACHE/A.SCANNER).read_bytes(),(HERE/'match-diagnostic.py').read_bytes(),on_ready=lambda:admitted.append(True))
            self.assertFalse(admitted);self.assertFalse((root/'new').exists())

    def test_snapshot_fixed_complete_parser_partial_whole_qualification_false(self):
        C,R,S,H=modules();f=finite(S,H)
        with tempfile.TemporaryDirectory()as d:
            private=Path(d)/'private';private.mkdir(mode=0o700);(private/'vm').mkdir(mode=0o700)
            O.write_exclusive(private/'vm/serial-install.log',b'public-user@example.invalid\n')
            O.write_exclusive(private/'vm/serial-boot.log',wire())
            holder=A.snapshot(private,context(),f)
            files=A.snapshot_members(holder,C,(CACHE/P/'common.py').read_bytes(),S,(CACHE/A.SCANNER).read_bytes(),(HERE/'match-diagnostic.py').read_bytes())
            self.assertEqual(set(files),{'original-ui/report.json','original-ui/01-appearance.png','incomplete-evidence.json'})
            ledger=O.strict_json(files['incomplete-evidence.json'])
            self.assertIs(ledger['complete_uart_admitted'],False);self.assertIs(ledger['complete_ui_or_pam_proven'],False)
            original=RuntimeError('synthetic-primary');admitted=[]
            def failed(a,b):raise original
            with self.assertRaises(RuntimeError)as result:A.screen(failed,private,Path(d)/'published',holder,C,(CACHE/P/'common.py').read_bytes(),S,(CACHE/A.SCANNER).read_bytes(),(HERE/'match-diagnostic.py').read_bytes(),on_ready=lambda:admitted.append(True))
            self.assertIs(result.exception,original);self.assertEqual(admitted,[True])

    def test_publication_postrename_holder_swap_withholds_admission(self):
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);stage=root/'stage';target=root/'target';admitted=[];rename=os.rename
            def replaced(a,b):
                rename(a,b);rename(b,root/'detached');b.mkdir(mode=0o700)
            with mock.patch.object(A.os,'rename',side_effect=replaced),self.assertRaises(ValueError):A.publish_members(stage,target,{'incomplete-evidence.json':b'{}\n'},lambda:admitted.append(True))
            self.assertFalse(admitted)

    def test_actual_owned_code_clone_and_late_global_change_deny(self):
        C,R,S,H=modules();owner=A.OwnedSource(S.__dict__,(CACHE/A.SCANNER).read_bytes(),S.__file__,'original-scanner')
        actual=S.reject_sensitive_match.__code__;S.reject_sensitive_match.__code__=actual.replace()
        self.assertFalse(owner.unchanged());S.reject_sensitive_match.__code__=actual
        self.assertTrue(owner.unchanged());self.assertNotIn('RuntimeError',S.__dict__)
        S.RuntimeError=type('Foreign',(RuntimeError,),{})
        self.assertFalse(owner.unchanged())

    def test_private_harness_only_tail_inverse_no_filename_root_change(self):
        raw=(CACHE/'tools/test-install.sh').read_bytes();changed=A.private_harness(raw)
        self.assertEqual(changed.replace(A.PRIVATE_TAIL.encode(),A.FAILED_TAIL.encode(),1),raw)
        self.assertIn(b'source "$HERE/lib/container.sh"',changed)
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);(root/'serial-one.log').write_text('password = synthetic-private-fixture\n')
            result=subprocess.run(['bash','-c','rc=1; '+A.PRIVATE_TAIL],env=dict(os.environ,OUT=d),capture_output=True,check=True)
            self.assertEqual(result.stdout,b'')

    def test_actual_original_main_scanner_frame_snapshot_before_cleanup(self):
        C,R,S,H=modules();raw_run=(CACHE/P/'run.py').read_bytes();raw_common=(CACHE/P/'common.py').read_bytes()
        staged,state=A.bind(R,raw_run,raw_common,(CACHE/A.SCANNER).read_bytes(),(HERE/'match-diagnostic.py').read_bytes(),HERE/'match-diagnostic.py',(CACHE/'tools/test-install.sh').read_bytes(),admitted_guard=lambda *args:None)
        self.assertIs(staged.main.__code__,R.main.__code__)
        original_popen=subprocess.Popen;launched=[];metadata={};saved={s:signal.getsignal(s)for s in(signal.SIGINT,signal.SIGTERM)}
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);source=root/'source';(source/'tools/native-functional').mkdir(parents=True)
            native=b'# Explicit synthetic Source fixture; no guest assertions executed.\n'
            (source/'tools/native-functional/native_smoke.py').write_bytes(native)
            inputs=root/'inputs';inputs.mkdir();out=root/'evidence'
            def child(argv,**kwargs):
                private=out/'private';ctx=json.loads((private/'context.json').read_bytes());launched.append(argv.copy())
                if len(launched)==1:
                    (private/'vm-prepared-image-id.txt').write_text('sha256:'+'2'*64)
                    metadata.update(task=ctx['nonce'],container=kwargs['env']['ARCTIC_VM_CONTAINER_NAME'])
                else:
                    vm=private/'vm';vm.mkdir(mode=0o700)
                    O.write_exclusive(vm/'serial-install.log',b'public-user@example.invalid\n')
                    O.write_exclusive(vm/'serial-boot.log',wire(ctx))
                    self.assertTrue(Path(argv[1]).name.startswith('.test-install-private-uart-'))
                    self.assertEqual(Path(argv[1]).parent,C.ROOT/'tools')
                    self.assertEqual(Path(argv[1]).read_bytes().replace(A.PRIVATE_TAIL.encode(),A.FAILED_TAIL.encode(),1),(CACHE/'tools/test-install.sh').read_bytes())
                return original_popen(['/bin/true'],**kwargs)
            def checked(argv,**kwargs):
                if argv[0]=='git':return A.BASE
                if argv[:3]==['docker','image','inspect']:
                    return json.dumps({'org.arctic.test.vm-tools.task':metadata['task'],'org.arctic.test.vm-tools.container':metadata['container'],'org.arctic.test.vm-tools.scope':'paired-v1'}).encode()
                raise AssertionError('Unexpected synthetic tool route')
            def tool(argv,**kwargs):return subprocess.CompletedProcess(argv,1 if argv[:3]==['docker','container','inspect']else 0,b'',b'')
            try:
                with mock.patch.object(Path,'is_char_device',return_value=True),mock.patch.object(subprocess,'Popen',side_effect=child),mock.patch.object(subprocess,'check_output',side_effect=checked),mock.patch.object(subprocess,'run',side_effect=tool),mock.patch.object(sys,'argv',['ui','--source',str(source),'--inputs',str(inputs),'--out',str(out)]),contextlib.redirect_stdout(io.StringIO()):
                    result=staged.main()
            finally:
                for sig,handler in saved.items():signal.signal(sig,handler)
            self.assertEqual(result,1);self.assertEqual(len(launched),2)
            self.assertEqual(state['finite']['original_uart_stage'],'live')
            self.assertIs(state['finite']['actual_raising_Source_Code_globals_owned'],True)
            self.assertTrue(state['snapshot'].is_dir())
            self.assertEqual((state['snapshot']/'serial-boot.log').read_bytes(),wire(json.loads((out/'private/context.json').read_bytes())))
            self.assertFalse(list((C.ROOT/'tools').glob('.test-install-private-uart-*.sh')))
            self.assertEqual(json.loads((out/'public/host-status.json').read_bytes())['phase'],'original-screening')

    def test_partial_private_png_omitted_and_unknown_members_rejected(self):
        C,R,S,H=modules();ctx=context();f=finite(S,H)
        report=dict(schema='arctic-final-installed-ui-report-v1',context=ctx,status='failed',phase='appearance',error_class='RuntimeError',checks=[],selinux='Enforcing',visual_review_required=True,release_acceptance=False)
        members={'report.json':json.dumps(report).encode(),'01-appearance.png':png('password = synthetic-private-fixture')}
        with tempfile.TemporaryDirectory()as d:
            private=Path(d)/'private';private.mkdir(mode=0o700);(private/'vm').mkdir(mode=0o700)
            O.write_exclusive(private/'vm/serial-boot.log',wire(ctx,members))
            holder=A.snapshot(private,ctx,f)
            files=A.snapshot_members(holder,C,(CACHE/P/'common.py').read_bytes(),S,(CACHE/A.SCANNER).read_bytes(),(HERE/'match-diagnostic.py').read_bytes())
            self.assertNotIn('original-ui/01-appearance.png',files)
            self.assertEqual(O.strict_json(files['incomplete-evidence.json'])['denied_fixed_png_members'],['01-appearance.png'])
        parser,_,_=A.diagnostic_transport(C,(CACHE/P/'common.py').read_bytes())
        members['foreign.png']=png()
        with self.assertRaises(RuntimeError):parser(wire(ctx,members),ctx,S)

    def test_optional_partial_failure_preserves_same_primary_and_cancellation(self):
        C,R,S,H=modules()
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);primary=RuntimeError('synthetic primary')
            def failed(*args):raise primary
            with self.assertRaises(RuntimeError)as caught:A.screen(failed,root,root/'target',root/'missing',C,(CACHE/P/'common.py').read_bytes(),S,(CACHE/A.SCANNER).read_bytes(),(HERE/'match-diagnostic.py').read_bytes())
            self.assertIs(caught.exception,primary);self.assertFalse((root/'target').exists())
            cancel=KeyboardInterrupt()
            def canceled(*args):raise cancel
            with self.assertRaises(KeyboardInterrupt)as caught:A.screen(canceled,root,root/'other',root/'missing',C,(CACHE/P/'common.py').read_bytes(),S,(CACHE/A.SCANNER).read_bytes(),(HERE/'match-diagnostic.py').read_bytes())
            self.assertIs(caught.exception,cancel)

    def test_private_snapshot_actual_sigint_acquisition_closed_before_delivery(self):
        with tempfile.TemporaryDirectory()as d:
            target=Path(d)/'uart';real=os.open;seen=[]
            def acquired(*args,**kwargs):
                fd=real(*args,**kwargs)
                if Path(args[0])==target:seen.append(fd);os.kill(os.getpid(),signal.SIGINT)
                return fd
            old=signal.getsignal(signal.SIGINT)
            try:
                with mock.patch.object(O.os,'open',side_effect=acquired),self.assertRaises(KeyboardInterrupt):A.write_snapshot(target,b'public UART\n',16*1024*1024)
                with self.assertRaises(OSError):os.fstat(seen[0])
                self.assertEqual(target.read_bytes(),b'public UART\n');self.assertIs(signal.getsignal(signal.SIGINT),old)
            finally:signal.signal(signal.SIGINT,old)

if __name__=='__main__':unittest.main()
