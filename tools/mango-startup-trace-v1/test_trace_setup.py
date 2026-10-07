"""Private owned filesystem/unit controls; no service, VM or target execution."""
import base64,copy,hashlib,importlib.util,json,os,stat,subprocess,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
HERE=Path(__file__).parent

def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
P=load('trace_prepare_controls',HERE/'prepare.py');C=load('trace_root_controls',HERE/'controller.py');U=load('trace_unit_controls',HERE/'credential-units.py')
ORIGINAL=Path(os.environ.get('TRACE_ORIGINAL_SESSION',str(HERE/'candidate-wayland-session.fixture'))).read_bytes()

class Setup(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='private-setup-',dir=HERE)
        self.base=Path(self.tmp.name);self.cd=self.base/'cd';self.cd.mkdir(mode=0o755);self.root=self.base/'runtime';self.overlay=self.base/'overlay'
        self.oldroot,self.oldoverlay,self.oldwrapper=P.ROOT,P.OVERLAY,P.WRAPPER;self.oldc=C.ROOT
        P.ROOT=self.root;P.OVERLAY=self.overlay;P.WRAPPER=self.root/'session-wrapper';C.ROOT=self.root
        runtime={}
        for name in P.PAYLOAD:
            if name=='runtime-pins.json':continue
            raw=(HERE/name).read_bytes();(self.cd/name).write_bytes(raw);runtime[name]={'sha256':P.sha(raw),'mode':493 if name=='native-handoff' else 420}
        (self.cd/'runtime-pins.json').write_text(json.dumps({'runtime':runtime,'candidate_boundary':{'directories':[],'files':[],'providers':[],'unit_files':[]}}))
        self.read=P.read
        def read(path,*args,**kwargs):
            if str(path)=='/etc/sddm/wayland-session':return ORIGINAL,{'sha256':P.sha(ORIGINAL)}
            return self.read(path,*args,**kwargs)
        security={'qualified':True,'selinux':'Enforcing','full_unfiltered':True}
        self.patches=[patch.object(P,'read',side_effect=read),patch.object(P,'discover',return_value=[]),patch.object(P,'unit_binding',return_value={'generated_files':[]}),patch.object(P.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=1000,pw_gid=1000,pw_dir='/home/liveuser',pw_shell='/bin/bash')),patch.object(P,'security',return_value=(security,b'{"MESSAGE":"full"}\n'))]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        P.ROOT,P.OVERLAY,P.WRAPPER=self.oldroot,self.oldoverlay,self.oldwrapper;C.ROOT=self.oldc;self.tmp.cleanup()
    def install(self):return P.install(self.cd,'a'*64,2048,[1,2,0,0,0o700])
    def outputs(self):
        d=self.root/'user/capture';d.mkdir(mode=0o700);os.chown(d,1000,1000)
        for p in [d/'stderr.raw',d/'log-report.json',self.root/'user/attempt',self.root/'user/terminal.json']:
            p.write_bytes(b'kept\n');p.chmod(0o600);os.chown(p,1000,1000)
        P.fresh_write(self.root/'stop',b'ARCTIC_TRACE_END_V1\n',0o644)
    def test_real_install_and_exact_owned_rollback(self):
        state=self.install();self.assertEqual(self.root.stat().st_mode&0o777,0o755);self.assertEqual((self.root/'user').stat().st_uid,1000)
        self.assertEqual((self.root/'session-wrapper').read_bytes(),P.wrapper(ORIGINAL));self.assertFalse(any('state.json'==Path(v['path']).name for v in state['owned']))
        self.outputs()
        with patch.object(C,'module',return_value=P):result=C.rollback(state)
        self.assertTrue(result['runtime_and_one_config_removed']);self.assertFalse(self.root.exists());self.assertFalse(self.overlay.exists())
    def test_real_partial_write_failure_removes_fresh_owned_set(self):
        real=P.os.write;count=[0]
        def write(fd,raw):
            count[0]+=1
            if count[0]==2:raise OSError('owned write failed')
            return real(fd,raw)
        with patch.object(P.os,'write',side_effect=write),self.assertRaisesRegex(OSError,'owned write'):self.install()
        self.assertFalse(self.root.exists());self.assertFalse(self.overlay.exists())
    def test_real_user_chown_close_after_transition_failure_rolls_back(self):
        real=P.os.chown
        def chown(path,*a,**kw):real(path,*a,**kw);raise OSError('post-chown failure')
        with patch.object(P.os,'chown',side_effect=chown),self.assertRaisesRegex(OSError,'post-chown'):self.install()
        self.assertFalse(self.root.exists());self.assertFalse(self.overlay.exists())
    def test_collision_and_changed_owned_node_fail_before_deletion(self):
        self.overlay.symlink_to(self.base/'absent')
        with self.assertRaisesRegex(RuntimeError,'collision'):self.install()
        self.overlay.unlink();state=self.install();self.outputs();target=self.root/'controller.py';target.write_bytes(b'changed')
        with patch.object(C,'module',return_value=P),self.assertRaisesRegex(RuntimeError,'content changed'):C.rollback(state)
        self.assertTrue(target.exists());self.assertTrue((self.root/'user/terminal.json').exists());self.assertTrue(self.overlay.exists())
    def test_real_unsafe_parent_link_and_missing_optional_parent(self):
        alias=self.base/'alias';alias.symlink_to(self.cd,target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError,'parent'):self.read(alias/'prepare.py')
        with self.assertRaisesRegex(RuntimeError,'parent'):P.parents(alias/'missing')
    def test_only_exact_wrapper_handoff_replacement(self):
        result=P.wrapper(ORIGINAL);self.assertEqual(result.replace(b'exec /run/arctic-mango-trace/native-handoff $@',b'exec $@'),ORIGINAL)
        for raw in [ORIGINAL+b'\n',ORIGINAL.replace(b'exec $@',b'exec "$@"'),ORIGINAL.replace(b'exec $@',b'exec other $@')]:
            with self.subTest(raw=raw),self.assertRaises(RuntimeError):P.wrapper(raw)
    def test_unqualified_before_security_exports_full_failed_body_before_cleanup(self):
        security={'qualified':False,'selinux':'Permissive'};journal=b'{"MESSAGE":"avc: denied","PRIORITY":"3"}\n'
        with patch.object(P,'security',return_value=(security,journal)),patch.object(P,'preserve_failure') as send,self.assertRaisesRegex(RuntimeError,'security'):self.install()
        self.assertEqual(send.call_args.args[1],{'journal-before.log':journal});self.assertEqual(send.call_args.args[0]['status'],'failed-before-native-security');self.assertFalse(self.root.exists())
    def test_failed_root_path_retains_full_bodies_without_success_decoder(self):
        H=load('trace_transport_failure_control',HERE/'transport.py');sent=[]
        fake=SimpleNamespace(read=lambda *a,**kw:(_ for _ in ()).throw(FileNotFoundError('fixture absent')),fresh_write=lambda *a,**kw:None,security=lambda **kw:({'qualified':False},b'{"MESSAGE":"all kernel warnings retained"}\n'))
        with patch.object(C,'observed_logger',return_value=None),patch.object(C,'SECURITY_HELPER',None,create=True),patch.object(H,'send',side_effect=lambda frames:sent.extend(frames)):
            C.failure(fake,H,RuntimeError('original diagnostic failure'))
        self.assertTrue(sent);wire=b''.join(sent).decode();self.assertIn('failed-owned-trace',wire);self.assertIn('"status": "failed"',wire)
        with self.assertRaisesRegex(RuntimeError,'END'):H.decode(wire)

    def retained_after_cleanup(self,final_qualified,export_fails):
        H=load('trace_retained_transport_control',HERE/'transport.py');initial={n:(n+' full original bytes\n').encode() for n in ('terminal.json','log-report.json','stderr.raw','line-proofs.json')}
        before=b'{"MESSAGE":"full before journal"}\n';after=b'{"MESSAGE":"full after journal"}\n';snapshot={'qualified':final_qualified}
        state={'security_before':{'journal_total_bytes':len(before),'journal_retained_sha256':P.sha(before)},'config_after':[],'CD':str(self.cd),'CD_sha256':'a'*64,'CD_bytes':2048}
        cleaned=[];security_calls=[];exports=[];retained={}
        def read(path,*a,**kw):
            if cleaned:raise AssertionError('Deleted source reread after successful cleanup')
            if Path(path)==self.root/'journal-before.log':return before,{}
            if Path(path)==self.root/'runtime-pins.json':return b'{"candidate_boundary":{"directories":[]}}',{}
            raise AssertionError('Unexpected synthetic source read')
        def security(**kw):security_calls.append(1);return snapshot,after
        fake=SimpleNamespace(read=read,sha=P.sha,discover=lambda *a:[],unit_binding=lambda *a:{},security=security)
        real_export=H.export
        def export(report,bodies):
            exports.append((report,dict(bodies)))
            if export_fails and len(exports)==1:raise OSError('injected final success export failure')
            return real_export(report,bodies)
        with patch.object(C,'collect',return_value=({'schema':'arctic-one-mango-trace-v1'},dict(initial),state)),patch.object(C,'final_cleanup',side_effect=lambda *a:cleaned.append(1) or {'owned_runtime_config_removed':True}),patch.object(C,'SECURITY_HELPER',None,create=True),patch.object(H,'export',side_effect=export),patch.object(H,'send') as send:
            with self.assertRaisesRegex((RuntimeError,OSError),'security|export') as error:C.success(fake,H,retained)
            C.failure(fake,H,error.exception,retained)
        report,bodies=exports[-1]
        self.assertEqual(len(cleaned),1);self.assertEqual(len(security_calls),1);self.assertEqual(report['status'],'failed-owned-trace')
        self.assertEqual(report['security_after'],snapshot);self.assertEqual(report['root_cleanup'],{'owned_runtime_config_removed':True})
        self.assertEqual(set(bodies),set(initial)|{'journal-before.log','journal-after.log','owned-state.json'})
        for name,raw in initial.items():self.assertEqual(bodies[name],raw)
        self.assertEqual(bodies['journal-before.log'],before);self.assertEqual(bodies['journal-after.log'],after);self.assertEqual(json.loads(bodies['owned-state.json']),state)
        with self.assertRaisesRegex(RuntimeError,'END'):H.decode(b''.join(send.call_args.args[0]).decode())
    def test_final_security_failure_retains_all_already_read_bodies(self):self.retained_after_cleanup(False,False)
    def test_final_export_failure_retains_all_already_read_bodies(self):self.retained_after_cleanup(True,True)

class Units(unittest.TestCase):
    def test_fixed_nonsecret_credentials_and_exact_bootstrap_command_syntax(self):
        values=U.values('a'*64,2048);args=U.qemu_args('a'*64,2048);self.assertEqual(len(args),4)
        for i,(name,value) in enumerate(values.items()):
            self.assertEqual(args[2*i],'-smbios');self.assertEqual(base64.b64decode(args[2*i+1].split(name+'=',1)[1]),value.encode());self.assertTrue(value.endswith('\n'))
        unit=values[U.DROP];raw=unit.split(' -ec "',1)[1][:-2]
        command=raw.replace('\\"','"').replace('\\\\','\\').replace('%%','%').replace('$$','$')
        subprocess.run(['bash','-n'],input=command.encode(),check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.assertIn('trap ',command);self.assertNotIn('exec /usr/bin/python3.14',command);self.assertIn('mounted=1',command);self.assertIn('> /dev/ttyS0',command)
    def test_invalid_credentials_never_construct_command(self):
        for digest,size in [('A'*64,2048),('a'*63,2048),('$(x)',2048),('a'*64,True),('a'*64,2049),('a'*64,16777217),('a'*64,0)]:
            with self.subTest(digest=digest,size=size),self.assertRaises(RuntimeError):U.values(digest,size)

if __name__=='__main__':unittest.main()
