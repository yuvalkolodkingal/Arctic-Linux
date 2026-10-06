#!/usr/bin/env python3
"""Host controls: synthetic UI/bus authority, real owned subprocesses; no VM/network."""
import ast
import base64
import copy
import contextlib
import io
import hashlib
import importlib.util
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
import warnings
import zlib

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent

def load(name,file):
    spec=importlib.util.spec_from_file_location(name,HERE/file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

A=load('owner_atspi','atspi-snapshot.py')
G=load('owner_guest','guest-pcmanfm-diagnostic.py')
C=load('owner_controller','pcmanfm-controller.py')
B=load('owner_bounded','bounded-launch.py')
R=load('owner_runner','diagnostic-runner.py')
P=load('owner_prepare','prepare-diagnostic.py')

# Faithful signed wire-type adapters: not a claim that host owns a guest bus.
UInt32=type('UInt32',(int,),{'__module__':'dbus'})
Int32=type('Int32',(int,),{'__module__':'dbus'})
Boolean=type('Boolean',(int,),{'__module__':'dbus'})
PROOF=dict(pid=3053,start_ticks=111,executable='/usr/bin/pcmanfm',executable_sha256='a'*64,
           is_xwayland=False,client_id='4')
CLIENT=dict(id=4,pid=3053,foreign_toplevel_id='owned-4',appid='pcmanfm',x=0,y=0,width=600,height=400,
            monitor='Virtual-1',is_xwayland=False,is_focused=True,is_visible=True)
FIXTURE='/tmp/arctic-native-smoke-control/files with spaces'
BOOT='11111111-2222-3333-4444-555555555555'

class BusError(Exception):
    def __init__(self,name):self.name=name;super().__init__(name)
    def get_dbus_name(self):return self.name

class FakeBus:
    def __init__(self):
        self.methods=[];self.change=None;self.calls=0
        flags=sum(1<<x for x in (7,11,12,25,30))
        self.nodes={'/app':dict(role=75,state=[0,0],children=['/frame']),
                    '/frame':dict(role=23,state=[flags,0],children=['/entry']),
                    '/entry':dict(role=61,state=[flags,0],children=[],description='Folder location bar',text=FIXTURE)}
        self.roots=[(':1.8','/app')]
    def get_object(self,bus,path,introspect=False):
        outer=self
        class Proxy:
            def get_dbus_method(self,method,interface):
                def invoke(*args,timeout):
                    outer.methods.append((bus,path,interface,method,args));outer.calls+=1
                    if outer.change:
                        replaced=outer.change(bus,path,interface,method,args)
                        if replaced is not None:return replaced
                    if method=='GetNameOwner':return args[0]
                    if method=='GetConnectionUnixProcessID':return UInt32(PROOF['pid'])
                    if bus=='org.a11y.atspi.Registry':return outer.roots
                    node=outer.nodes[path]
                    if method=='GetRole':return UInt32(node['role'])
                    if method=='GetState':return [UInt32(v) for v in node['state']]
                    if method=='GetInterfaces':return [A.ACCESSIBLE]+([A.TEXT,A.ACTION] if 'text' in node else [])
                    if method=='GetChildren':return [(':1.8',p) for p in node['children']]
                    if method=='Get':
                        prop=args[1]
                        if prop=='Name':return 'control'
                        if prop=='Description':return node.get('description','')
                        if prop=='CharacterCount':return Int32(len(node['text']))
                        if prop=='CaretOffset':return Int32(len(node['text']))
                    if method=='GetText':return node['text']
                    if method=='GetNSelections':return Int32(0)
                    if method=='GetActions':return [('activate','control description','Return')]
                    raise AssertionError('unexpected/mutating bus method '+method)
                return invoke
        return Proxy()

def snapshot(bus):
    with patch.object(A,'identity') as identity:
        result=A.snapshot(copy.deepcopy(PROOF),bus)
        return result,identity.call_count

def entry_snapshot():
    value,_=snapshot(FakeBus());return value

def request():
    return dict(schema='arctic-pcmanfm-physical-request-v1',arm='observed-route',nonce='b'*32,boot_id=BOOT,
                process=copy.deepcopy(PROOF),client=copy.deepcopy(CLIENT),entry=entry_snapshot()['entry'],
                entry_evidence_sha256='c'*64,fixture_path=FIXTURE,virtual_status='failed-30s-title-gate',
                monotonic_ns=123,release_acceptance=False)

class BusControls(unittest.TestCase):
    def test_signed_wire_types_reject_boolean_and_wrong_integer_signature(self):
        self.assertEqual(A.uint(UInt32(3)),3);self.assertEqual(A.nonnegative_int(Int32(3)),3)
        self.assertIs(A.boolean(Boolean(1)),True)
        for value in (True,Boolean(1),Int32(1),-1,2**32):
            with self.subTest(value=repr(value),kind=type(value).__name__),self.assertRaises(RuntimeError):A.uint(value)
        for value in (True,Boolean(1),UInt32(1),-1,2**31):
            with self.assertRaises(RuntimeError):A.nonnegative_int(value)
        for value in ('false',0,UInt32(1),Boolean(2)):
            with self.assertRaises(RuntimeError):A.boolean(value)
    def test_actual_dbus_boolean_if_host_dependency_available(self):
        try:import dbus
        except ImportError:self.skipTest('host python-dbus absent; faithful signature adapters run separately')
        for function in (A.uint,A.nonnegative_int):
            with self.assertRaises(RuntimeError):function(dbus.Boolean(True))
        self.assertTrue(A.boolean(dbus.Boolean(True)))
    def test_two_word_state_mask_not_enum_list(self):
        value=A.state_words([UInt32((1<<12)|(1<<30)),UInt32(1)])
        self.assertTrue(value['focused']);self.assertTrue(value['visible']);self.assertFalse(value['editable'])
        for value in ([1], [1,2,3],[Boolean(1),UInt32(0)]):
            with self.assertRaises(RuntimeError):A.state_words(value)
    def test_observed_owned_location_and_read_only_methods(self):
        bus=FakeBus();value,count=snapshot(bus)
        self.assertEqual(value['status'],'observed');self.assertEqual(value['process'],PROOF)
        self.assertEqual(value['entry']['text'],FIXTURE);self.assertGreaterEqual(count,3)
        self.assertTrue(all(m[3] in {'GetNameOwner','GetConnectionUnixProcessID','GetChildren','GetRole','GetState',
            'GetInterfaces','Get','GetText','GetNSelections','GetActions'} for m in bus.methods))
    def test_location_description_missing_or_localized_is_unavailable(self):
        for desc in ('','Search field','Folder location bar translated'):
            bus=FakeBus();bus.nodes['/entry']['description']=desc
            value,_=snapshot(bus);self.assertEqual(value['status'],'unavailable');self.assertIsNone(value['entry'])
    def test_unexported_application_is_unavailable(self):
        bus=FakeBus();bus.roots=[];self.assertEqual(snapshot(bus)[0]['status'],'unavailable')
    def test_ambiguous_application_frame_entry_and_cycle_rejected(self):
        for mutation in ('app','frame','entry','cycle'):
            bus=FakeBus()
            if mutation=='app':bus.roots.append((':1.8','/other'))
            elif mutation=='cycle':bus.nodes['/entry']['children']=['/entry']
            else:
                origin='/frame' if mutation=='frame' else '/entry'
                bus.nodes['/duplicate']=copy.deepcopy(bus.nodes[origin]);bus.nodes['/app' if mutation=='frame' else '/frame']['children'].append('/duplicate')
            with self.subTest(mutation=mutation),self.assertRaises(RuntimeError):snapshot(bus)
    def test_foreign_child_and_changed_current_owner_pid_rejected(self):
        for mutation in ('foreign','owner','pid'):
            bus=FakeBus()
            def change(busname,path,interface,method,args):
                if mutation=='foreign' and method=='GetChildren' and path=='/frame':return [(':9.9','/entry')]
                if mutation=='owner' and method=='GetNameOwner':return ':1.9'
                if mutation=='pid' and method=='GetConnectionUnixProcessID' and bus.calls>8:return UInt32(9999)
            bus.change=change
            with self.subTest(mutation=mutation),self.assertRaises(RuntimeError):snapshot(bus)
    def test_recycled_process_and_snapshot_deadline_rejected(self):
        with patch.object(A,'identity',side_effect=[None,None,RuntimeError('recycled')]):
            with self.assertRaises(RuntimeError):A.snapshot(PROOF,FakeBus())
        with patch.object(A,'identity'),patch.object(A.time,'monotonic',return_value=6):
            with self.assertRaises(RuntimeError):A.snapshot(PROOF,FakeBus(),started=0)
    def test_boolean_role_pid_count_and_malformed_text_rejected(self):
        for case in ('role','pid','count','text'):
            bus=FakeBus()
            def change(busname,path,interface,method,args):
                if case=='role' and method=='GetRole':return Boolean(1)
                if case=='pid' and method=='GetConnectionUnixProcessID':return Boolean(1)
                if case=='count' and method=='Get' and args[-1]=='CharacterCount':return Boolean(1)
                if case=='text' and method=='GetText':return 'wrong length'
            bus.change=change
            with self.subTest(case=case),self.assertRaises(RuntimeError):snapshot(bus)
    def test_valid_optional_unsupported_is_distinct_from_timeout(self):
        for method in ('GetNSelections','GetActions'):
            bus=FakeBus()
            def change(b,p,i,m,a):
                if m==method:raise BusError('org.freedesktop.DBus.Error.UnknownMethod')
            bus.change=change
            value,_=snapshot(bus);self.assertEqual(value['status'],'observed')
        for name in ('org.freedesktop.DBus.Error.Timeout','org.freedesktop.DBus.Error.NoReply'):
            with self.assertRaises(BusError):A.optional(lambda:(_ for _ in ()).throw(BusError(name)))
    def test_disabled_bridge_is_read_without_enabling_or_address_start(self):
        methods=[]
        class Service:
            def get_dbus_method(self,method,interface):
                methods.append(method)
                return lambda *a,**kw:Boolean(0)
        dbus=types.SimpleNamespace(SessionBus=lambda **kw:types.SimpleNamespace(get_object=lambda *a,**kw:Service()))
        value=A.bus_snapshot(PROOF,dbus,0)
        self.assertEqual(methods,['Get']);self.assertEqual(value['status'],'unavailable')
    def test_missing_bridge_owner_unavailable_but_malformed_enabled_fails(self):
        for result in ('owner','string'):
            class Service:
                def get_dbus_method(self,m,i):
                    def call(*a,**kw):
                        if result=='owner':raise BusError('org.freedesktop.DBus.Error.ServiceUnknown')
                        return 'false'
                    return call
            dbus=types.SimpleNamespace(SessionBus=lambda **kw:types.SimpleNamespace(get_object=lambda *a,**kw:Service()))
            if result=='owner':self.assertEqual(A.bus_snapshot(PROOF,dbus,0)['status'],'unavailable')
            else:
                with self.assertRaises(RuntimeError):A.bus_snapshot(PROOF,dbus,0)

class FakeSmoke:
    def __init__(self,root):self.root=root;self.calls=[]
    def diagnostic(self,label,**kw):self.calls.append(('diagnostic',label))
    def keys(self,proof,*argv):self.calls.append(('keys',list(argv)))
    def alive(self,proof):return dict(CLIENT,title='files with spaces')
    def wait(self,fn,timeout=30,label=None):self.calls.append(('wait',timeout,label));return fn()

class GuestControls(unittest.TestCase):
    def test_frozen_library_hash_and_exact_original_route_inputs(self):
        self.assertEqual(hashlib.sha256((HERE/'native_smoke.py').read_bytes()).hexdigest(),G.NATIVE_SHA)
        with tempfile.TemporaryDirectory() as tmp:
            smoke=FakeSmoke(Path(tmp));directory=smoke.root/'files with spaces';directory.mkdir()
            with patch.object(G.N.time,'sleep') as sleep:G.N.Smoke.navigate(smoke,PROOF,directory,'text-fixture')
            self.assertEqual([r[1] for r in smoke.calls if r[0]=='keys'],[
                ['-M','ctrl','-k','l','-m','ctrl'],['-M','ctrl','-k','a','-m','ctrl'],[str(directory)],['-k','Return']])
            self.assertEqual(sleep.call_args_list,[unittest.mock.call(.3),unittest.mock.call(.3)])
            self.assertEqual([r[1] for r in smoke.calls if r[0]=='wait'],[30])
    def test_observed_route_retains_literal_inputs_and_gate_with_separate_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            smoke=FakeSmoke(Path(tmp));directory=smoke.root/'files with spaces';directory.mkdir()
            with patch.object(G,'observe') as observe,patch.object(G.time,'sleep'):
                G.observed_navigate(smoke,PROOF,directory)
            self.assertEqual(observe.call_count,8)
            self.assertEqual([r[1] for r in smoke.calls if r[0]=='keys'],[
                ['-M','ctrl','-k','l','-m','ctrl'],['-M','ctrl','-k','a','-m','ctrl'],[str(directory)],['-k','Return']])
            self.assertEqual([r[1] for r in smoke.calls if r[0]=='wait'],[30])
    def test_frozen_keys_warmup_ast_and_guest_direct_call_not_monkeypatch(self):
        tree=ast.parse((HERE/'native_smoke.py').read_text());keys=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='keys')
        self.assertIn("['wtype', '-s', '200', '-k', 'Shift_L', '-s', '150', *argv]",ast.unparse(keys))
        guest=ast.parse((HERE/'guest-pcmanfm-diagnostic.py').read_text())
        self.assertTrue(any(isinstance(n,ast.Call) and ast.unparse(n.func)=='smoke.navigate' for n in ast.walk(guest)))
        self.assertFalse(any(isinstance(n,ast.Assign) and any(ast.unparse(t).startswith('N.') for t in n.targets) for n in ast.walk(guest)))
    def test_only_exact_original_timeout_becomes_diagnostic_outcome(self):
        smoke=FakeSmoke(Path('/tmp'))
        def throw(text):return lambda:(_ for _ in ()).throw(RuntimeError(text))
        value=G.navigation_result(smoke,throw('bounded functional gate timed out: PCManFM directory title after Return: files with spaces'),'original-route')
        self.assertEqual(value['status'],'failed-30s-title-gate')
        with self.assertRaises(RuntimeError):G.navigation_result(smoke,throw('missing GUI collector'),'original-route')
    def test_owned_client_focus_identity_visibility_geometry_and_native_guards(self):
        G.stable_client(CLIENT,CLIENT,PROOF)
        for key,value in [('pid',999),('id',8),('foreign_toplevel_id','foreign'),('is_focused',False),('is_visible',False),('width',700),('is_xwayland',True)]:
            other=dict(CLIENT,**{key:value})
            with self.subTest(key=key),self.assertRaises(RuntimeError):G.stable_client(CLIENT,other,PROOF)
    def test_physical_entry_proof_focus_frame_exact_text_and_unavailability(self):
        value={'snapshot':entry_snapshot()};self.assertTrue(G.physical_precondition(value,PROOF,Path(FIXTURE)))
        for case in ('process','description','focus','text','frame','unavailable'):
            changed=copy.deepcopy(value)
            if case=='process':changed['snapshot']['process']['pid']=999
            elif case=='frame':changed['snapshot']['frames']=['/other']
            elif case=='unavailable':changed['snapshot']['status']='unavailable'
            else:changed['snapshot']['entry'][{'focus':'state','text':'text','description':'description'}[case]]=({'focused':False} if case=='focus' else 'different')
            self.assertFalse(G.physical_precondition(changed,PROOF,Path(FIXTURE)))
    def test_no_physical_request_without_failed_virtual_or_exported_entry(self):
        smoke=FakeSmoke(Path('/tmp'))
        self.assertEqual(G.physical(smoke,PROOF,Path(FIXTURE),{'status':'matched-directory'})['status'],'unrun')
        with patch.object(G,'observe',return_value={'snapshot':{'status':'unavailable'}}),patch('builtins.print') as printed:
            self.assertEqual(G.physical(smoke,PROOF,Path(FIXTURE),{'status':'failed-30s-title-gate'})['status'],'unrun')
            printed.assert_not_called()
    def test_changed_second_physical_snapshot_rejected_before_request(self):
        good={'snapshot':entry_snapshot()}
        with patch.object(G,'observe',side_effect=[good,{'snapshot':{'status':'unavailable'}}]),patch('builtins.print') as printed:
            with self.assertRaises(RuntimeError):G.physical(FakeSmoke(Path('/tmp')),PROOF,Path(FIXTURE),{'status':'failed-30s-title-gate'})
            printed.assert_not_called()
    def test_security_actual_enforcing_enabled_one_lost_zero(self):
        G.strict_security({'selinux':'Enforcing','audit':{'enabled':1,'lost':0}})
        for value in ({'selinux':'Permissive','audit':{'enabled':1,'lost':0}},
                      {'selinux':'Enforcing','audit':{'enabled':0,'lost':0}},
                      {'selinux':'Enforcing','audit':{'enabled':1,'lost':1}}):
            with self.assertRaises(RuntimeError):G.strict_security(value)
    def test_post_arm_codec_only_after_four_arms_and_fixture_is_pinned(self):
        tree=ast.parse((HERE/'guest-pcmanfm-diagnostic.py').read_text())
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_diagnosis')
        block=next(n for n in function.body if isinstance(n,ast.Try)).body
        codec=next(i for i,n in enumerate(block) if isinstance(n,ast.Assign) and isinstance(n.value,ast.Call) and ast.unparse(n.value.func)=='codec_diagnostic')
        self.assertEqual(sum(isinstance(n,ast.For) for n in block[:codec]),2)
        self.assertEqual(hashlib.sha256((HERE/'original-h264-aac-1s.mp4').read_bytes()).hexdigest(),
                         '24fcb595e3c63e836a9ebae43c05c902b88b954aea73abde35de8c6fc86497b8')
    def test_role_fixture_original60_observed180_explicit(self):
        text=ast.unparse(ast.parse((HERE/'guest-pcmanfm-diagnostic.py').read_text()))
        self.assertIn("code.replace('time.sleep(60)', 'time.sleep(180)')",text)
        self.assertIn('terminal_fixture_lifetime_seconds=180 if observed else 60',text)


class FinalPreservationControls(unittest.TestCase):
    def test_actual_frozen_trace_overflow_fails_run_diagnosis_and_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);aggregate=base/'aggregate';aggregate.mkdir()
            instances=[];actual_trace=G.N.Smoke.trace
            class SyntheticSmoke:
                def __init__(self,*args):
                    self.root=base/('arm-'+str(len(instances)));self.root.mkdir();instances.append(self)
                    self.steps=[];self.owned=[];self.trace_bytes=0;self.trace_omitted=0;self.active_gate=None;self.client_observations=0
                def setup(self):return {'scope':'synthetic GUI authority only'}
                def navigate(self,*args):pass
                def cleanup(self):
                    # Exercise actual immutable optional trace implementation, not a mirrored omission counter.
                    actual_trace(self,'required-lifecycle',payload='a'*(2*1024*1024+1))
                    return {'only_proved_new_processes_signalled':True,'original_copied_configs_unchanged':True}
                def write(self,name,data):p=self.root/name;p.write_bytes(data);return p
            security=types.SimpleNamespace(before={'selinux':'Enforcing','audit':{'enabled':1,'lost':0}},
                state=lambda:{'selinux':'Enforcing','audit':{'enabled':1,'lost':0}},
                finish=lambda:{'selinux':'Enforcing','audit':{'enabled':1,'lost':0},'observed_new_avcs':0})
            def scenario(smoke,observed):return smoke.root/'files with spaces',PROOF,{}
            with patch.object(G.N,'Smoke',SyntheticSmoke),patch.object(G.N,'SecurityInterval',return_value=security),\
                 patch.object(G,'scenario',side_effect=scenario),patch.object(G,'target_environment',return_value={}),\
                 patch.object(G,'navigation_result',return_value={'status':'matched-directory'}),\
                 patch.object(G,'role_lifecycle',return_value={}),patch.object(G,'bounded_journals',return_value={}),\
                 contextlib.redirect_stderr(io.StringIO()):
                result=G.run_diagnosis(['synthetic-no-UI'],aggregate)
            self.assertEqual(result['status'],'failed');self.assertTrue(any('trace omitted' in e for e in result['errors']))
            self.assertGreater(instances[0].trace_omitted,0)
            saved=json.loads((aggregate/'original-route/arm-report.json').read_text())
            self.assertEqual(saved['trace']['omitted_records'],instances[0].trace_omitted)
            self.assertEqual(saved['preservation_phase'],'final-cleanup-preservation')
            raw=json.loads((aggregate/'original-route/gui-trace-summary.json').read_text())
            self.assertEqual(raw['omitted_records'],instances[0].trace_omitted)
    def test_immediate_pre_vm_reverification_actual_helper_and_mismatch_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);bundle=root/'bundle';bundle.mkdir();evidence=root/'evidence';evidence.mkdir()
            actual=dict(bytes=1880244224,sha256='a'*64,metadata_sha256={'fixture':'b'*64})
            expected={'source':'reviewed'}
            (evidence/'verified-input.json').write_text(json.dumps(dict(expected,iso=actual)))
            calls=[]
            common=types.SimpleNamespace(verify_iso=lambda p:(calls.append('actual-byte-metadata-check') or copy.deepcopy(actual)),
                                         digest=lambda p:'c'*64)
            args=types.SimpleNamespace(bundle=bundle,inputs=root/'inputs',evidence=evidence)
            with patch.object(R,'validate_ci',side_effect=lambda e,c:calls.append('CI')),\
                 patch.object(R,'verify_sources',side_effect=lambda a,c:(calls.append('exact-clean-sources') or {'files':{'a':'b'}})),\
                 patch.object(R,'proof',return_value=expected):
                result=R.verify_before_vm(args,common,None)
                self.assertEqual(calls,['CI','exact-clean-sources','actual-byte-metadata-check'])
                self.assertIn('immediately-before-vm',result['status'])
                (evidence/'verified-input.json').write_text(json.dumps(dict(expected,iso=dict(actual,bytes=1))))
                with self.assertRaises(RuntimeError):R.verify_before_vm(args,common,None)
            tree=ast.parse((HERE/'diagnostic-runner.py').read_text())
            run=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run')
            text=ast.unparse(run)
            self.assertLess(text.index("prepared = (args.evidence / 'vm-prepared-image-id.txt')"),text.index('verify_before_vm(args, R, V)'))
            self.assertLess(text.index('verify_before_vm(args, R, V)'),text.index('R.execute(argv'))
    def test_ffmpeg_rpm_verification_records_full_return_exit_stdout_stderr(self):
        tree=ast.parse((HERE/'guest-pcmanfm-diagnostic.py').read_text())
        method=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='codec_diagnostic')
        text=ast.unparse(method)
        self.assertIn('rpm_verification=dict(exit_status=verification[0], stdout=verification[1], stderr=verification[2])',text)

class FakeClock:
    def __init__(self):self.value=0
    def __call__(self):return self.value
    def sleep(self,n):self.value+=n

class FakeVM:
    def __init__(self,root,clock,variant='pass',qmp=None):
        self.root=root;self.clock=clock;self.variant=variant;self.answer={'return':{}} if qmp is None else qmp
        self.inputs=[];self.qmp=[];self.bootstrapped=None
        (root/'serial.log').write_text('live session mode: try\n')
    def alive(self):
        self.update();return self.variant!='dead'
    def update(self):
        if self.bootstrapped is None:return
        begin=dict(checker_sha256='d'*64,native_source_sha256=G.NATIVE_SHA,release_acceptance=False)
        gone=dict(boot_id=BOOT,launcher_sha256=G.LAUNCHER_SHA,owned_launcher_gone=True)
        req=request();parts=['live session mode: try','ARCTIC-NATIVE-LAUNCHER-GONE '+json.dumps(gone)]
        if self.variant!='missing-begin':parts.append('ARCTIC-PCMANFM-DIAG-BEGIN '+json.dumps(begin))
        if self.variant=='bad-begin':parts[-1]=parts[-1].replace('d'*64,'e'*64)
        if self.variant=='wrong-boot':req['boot_id']='99999999-2222-3333-4444-555555555555'
        if self.variant=='unfocused':req['client']['is_focused']=False
        if self.variant!='no-request':parts.append('ARCTIC-PCMANFM-PHYSICAL-REQUEST '+json.dumps(req))
        if self.variant=='duplicate-request':parts.append(parts[-1])
        if self.variant=='duplicate-begin':parts.insert(3,parts[2])
        if self.clock.value>=self.bootstrapped+1:
            end=dict(status='diagnostic-collected',error=None,evidence_export_complete=True,release_acceptance=False)
            if self.variant=='failed-end':end['status']='failed'
            if self.variant!='missing-end':parts.append('ARCTIC-PCMANFM-DIAG-END '+json.dumps(end))
        (self.root/'serial.log').write_text('\n'.join(parts)+'\n')
    def shot(self,name):
        if self.variant=='missing-shot':return None
        if self.variant=='stale-shot' and name=='pcmanfm-20-before-physical-return':self.clock.sleep(3)
        p=self.root/(name+'.png');p.write_bytes(b'host synthetic screenshot; no visual authority');return str(p)
    def keys(self,key):self.inputs.append(('keys',key,self.clock.value))
    def type_text(self,text,gap):self.inputs.append(('type',text,self.clock.value));self.bootstrapped=self.clock.value
    def cmd(self,name,**kwargs):self.qmp.append((name,kwargs));return self.answer

class ControllerControls(unittest.TestCase):
    def invoke(self,variant='pass',qmp=None):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
        clock=FakeClock();vm=FakeVM(root,clock,variant,qmp)
        return vm,root,clock
    def test_positive_single_ordered_bootstrap_physical_and_one_clock_per_event(self):
        vm,root,clock=self.invoke();C.run(vm,root,True,'d'*64,clock,clock.sleep)
        self.assertEqual([r[:2] for r in vm.inputs],[('keys','meta_l-ret'),('keys','ret'),('keys','ret'),
            ('type','sudo sh /dev/sr0; exit'),('keys','ret')])
        self.assertEqual(len(vm.qmp),1)
        self.assertEqual(vm.qmp[0],('input-send-event',{'events':[
            {'type':'key','data':{'down':True,'key':{'type':'qcode','data':'ret'}}},
            {'type':'key','data':{'down':False,'key':{'type':'qcode','data':'ret'}}}]}))
        events=[json.loads(r) for r in (root/'pcmanfm-host-events.log').read_text().splitlines()]
        self.assertEqual(sum(e['event']=='physical-host-ack' for e in events),1)
        self.assertTrue(all(e['monotonic_seconds']==e['controller_elapsed_seconds'] for e in events))
    def test_strict_qmp_empty_result_only_and_no_retry_after_failure(self):
        for answer in ({'return':False},{'return':None},{'return':{'unexpected':1}},{'return':{},'id':1},
                       {'return':{},'error':{}},{'error':{}},[],{'return':True}):
            vm,root,clock=self.invoke(qmp=answer)
            with self.subTest(answer=answer),self.assertRaises(RuntimeError):C.run(vm,root,True,'d'*64,clock,clock.sleep)
            self.assertEqual(len(vm.qmp),1)
            self.assertIn('physical-one-use-consumed',(root/'pcmanfm-host-events.log').read_text())
            self.assertNotIn('physical-host-ack',(root/'pcmanfm-host-events.log').read_text())
    def test_missing_source_launcher_focus_duplicate_or_dead_rejects_before_input(self):
        for variant in ('dead','missing-begin','bad-begin','wrong-boot','unfocused','duplicate-request','duplicate-begin','missing-shot','stale-shot'):
            vm,root,clock=self.invoke(variant)
            with self.subTest(variant=variant),self.assertRaises(RuntimeError):C.run(vm,root,True,'d'*64,clock,clock.sleep)
            self.assertEqual(len(vm.qmp),0)
    def test_missing_end_is_bounded_no_second_physical_send(self):
        vm,root,clock=self.invoke('missing-end')
        with self.assertRaises(RuntimeError):C.run(vm,root,True,'d'*64,clock,clock.sleep)
        self.assertEqual(len(vm.qmp),1);self.assertLessEqual(clock.value,900)
    def test_failed_end_and_missing_menu_do_not_pass(self):
        vm,root,clock=self.invoke('failed-end')
        with self.assertRaises(RuntimeError):C.run(vm,root,True,'d'*64,clock,clock.sleep)
        vm,root,clock=self.invoke()
        with self.assertRaises(RuntimeError):C.run(vm,root,False,'d'*64,clock,clock.sleep)
        self.assertEqual(vm.inputs,[])
    def test_request_requires_valid_uuid_arm_native_process_exact_text(self):
        C.physical_request(request())
        for path,value in [(('boot_id',),'a'*36),(('arm',),'original-route'),(('process','pid'),True),
                           (('process','is_xwayland'),True),(('entry','text'),'other'),(('client','foreign_toplevel_id'),'')]:
            changed=request();obj=changed
            for key in path[:-1]:obj=obj[key]
            obj[path[-1]]=value
            with self.subTest(path=path),self.assertRaises(RuntimeError):C.physical_request(changed)

class OwnedSubprocessControls(unittest.TestCase):
    def test_real_raw_stdout_stderr_separate_with_combined_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);code=B.run_owned(root,[sys.executable,'-c',"import sys;print('stdout');print('stderr',file=sys.stderr)"])
            self.assertEqual(code,0);self.assertEqual((root/'pcmanfm-stdout.log').read_bytes(),b'stdout\n')
            self.assertEqual((root/'pcmanfm-wayland-stderr.log').read_bytes(),b'stderr\n');self.assertFalse((root/'pcmanfm-wayland-error.json').exists())
    def test_real_output_overflow_is_failure_not_silent_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);code=B.run_owned(root,[sys.executable,'-c',"import sys;sys.stderr.write('a'*4096)"],limit=1024)
            self.assertEqual(code,74);self.assertFalse(json.loads((root/'pcmanfm-wayland-error.json').read_text())['preservation_complete'])
    def setup_failure(self,failure):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);children=[];real=B.subprocess.Popen
            def child(*a,**kw):
                value=real(*a,**kw);children.append(value);return value
            with warnings.catch_warnings():
                warnings.simplefilter('error',ResourceWarning)
                with patch.object(B.subprocess,'Popen',side_effect=child),failure:
                    with self.assertRaises(OSError):B.run_owned(root,[sys.executable,'-c','import time;time.sleep(20)'])
            self.assertEqual(len(children),1);self.assertIsNotNone(children[0].poll())
            self.assertTrue(children[0].stdout.closed and children[0].stderr.closed)
            self.assertTrue((root/'pcmanfm-wayland-error.json').exists())
    def test_real_pidfd_setup_failure_reaps_direct_child(self):
        self.setup_failure(patch.object(B.os,'pidfd_open',side_effect=OSError('fixture setup')))
    def test_real_selector_setup_failure_reaps_direct_child(self):
        self.setup_failure(patch.object(B.selectors,'DefaultSelector',side_effect=OSError('fixture setup')))
    def test_real_register_failure_reaps_direct_child(self):
        original=B.selectors.DefaultSelector
        class Broken:
            def __init__(self):self.inner=original()
            def register(self,*a,**kw):raise OSError('fixture register')
            def close(self):self.inner.close()
        self.setup_failure(patch.object(B.selectors,'DefaultSelector',Broken))
    def test_real_deadline_reaps_owned_child_and_reports_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            code=B.run_owned(Path(tmp),[sys.executable,'-c','import time;time.sleep(20)'],deadline=.05)
            self.assertEqual(code,74);self.assertIn('deadline',(Path(tmp)/'pcmanfm-wayland-error.json').read_text())
    def test_real_interruption_reaps_child_and_preserves_separate_streams(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            argv=[sys.executable,'-c',"import os,signal,time;time.sleep(.1);os.kill(os.getppid(),signal.SIGTERM);time.sleep(20)"]
            self.assertEqual(B.run_owned(root,argv),74)
            self.assertIn('interrupted',(root/'pcmanfm-wayland-error.json').read_text())
    def test_bounded_post_arm_command_real_output_timeout_and_overflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            result=G.bounded_command([sys.executable,'-c',"print('fixture')"],root,'one',1024,.5)
            self.assertEqual(result['exit_status'],0);self.assertEqual(result['stdout']['bytes'],8)
            result=G.bounded_command([sys.executable,'-c','import time;time.sleep(20)'],root,'two',1024,.1)
            self.assertTrue(result['timed_out'])
            with self.assertRaises(RuntimeError):G.bounded_command([sys.executable,'-c',"print('a'*3000)"],root,'three',1024,.5)
    def test_existing_evidence_output_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'pcmanfm-wayland-stderr.log').write_text('prior')
            with self.assertRaises(RuntimeError):B.run_owned(Path(tmp),['false'])



def transport_fixture(physical=False, mutate=None):
    temp=tempfile.TemporaryDirectory(prefix='arctic-pcmanfm-diagnostic-')
    root=Path(temp.name)
    launcher=dict(schema='arctic-native-launcher-v1',stage='live',boot_id=BOOT,owned_launcher_gone=True,
                  launcher_sha256=G.LAUNCHER_SHA)
    for index,name in enumerate(('shell','foot','probe')):
        launcher[name]=dict(pid=100+index,start_ticks=200+index,uid=0 if name=='probe' else 1000,
                           executable={'shell':'/usr/bin/bash','foot':'/usr/bin/foot','probe':'/usr/bin/python3'}[name],
                           executable_sha256='a'*64)
    runtime=json.loads((HERE/'runtime-pins.json').read_text())
    provenance=dict(checker_sha256='d'*64,native_source_sha256=G.NATIVE_SHA,release_acceptance=False,
                    cmdline='rd.live.image',boot_id=BOOT,desktop_uid=1000,launcher=launcher,runtime_pins=copy.deepcopy(runtime))
    report=dict(schema='arctic-pcmanfm-diagnostic-v1',status='diagnostic-collected',release_acceptance=False,
                original_run=37535425230,original_status='failed-7-of-8-live',errors=[],evidence_root=str(root),
                security={'selinux':'Enforcing','audit':{'enabled':1,'lost':0},'observed_new_avcs':0},
                arms=[dict(name=n) for n in ('original-route','observed-route','gtk-warmup','gtk-no-warmup')])
    report['arms'][1]['physical']=dict(status='unrun')
    events=[];req=None
    for arm in report['arms']:
        (root/arm['name']).mkdir()
        cleanup=dict(only_proved_new_processes_signalled=True,original_copied_configs_unchanged=True)
        (root/arm['name']/'arm-report.json').write_text(json.dumps(dict(name=arm['name'],cleanup=cleanup,preservation_phase='final-cleanup-preservation',trace=dict(bytes=0,omitted_records=0))))
        (root/arm['name']/'gui-trace-summary.json').write_text(json.dumps(dict(bytes=0,omitted_records=0)))
        (root/arm['name']/'gui-trace.log').write_bytes(b'')
    if physical:
        req=request()
        value=dict(process=PROOF,before=CLIENT,after=CLIENT,snapshot=entry_snapshot())
        path=root/'observed-route/entry-09-physical-immediate-precondition.json';path.write_text(json.dumps(value))
        req['entry_evidence_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        report['arms'][1]['physical']=dict(status='title-unchanged-after-request',request=req,
            delivery='unknown until separately paired host acknowledgement')
        events=[dict(event='physical-host-ack',nonce=req['nonce'],boot_id=BOOT,process=PROOF,request_sha256=C.canonical(req),
                     response={'return':{}},receipt_monotonic_seconds=1,input_start_monotonic_seconds=1.1,
                     exactly_one_press_release=True,release_acceptance=False)]
    if mutate:mutate(root,report,provenance,events,req)
    (root/'report.json').write_text(json.dumps(report));(root/'provenance.json').write_text(json.dumps(provenance))
    output=io.StringIO()
    with contextlib.redirect_stdout(output):G.export(root)
    lines=['ARCTIC-NATIVE-LAUNCHER-GONE '+json.dumps(launcher),
           'ARCTIC-PCMANFM-DIAG-BEGIN '+json.dumps(dict(checker_sha256='d'*64,release_acceptance=False))]
    if req:lines.append('ARCTIC-PCMANFM-PHYSICAL-REQUEST '+json.dumps(req))
    lines+=['ARCTIC-PCMANFM-DIAG-REPORT '+json.dumps(report),*output.getvalue().splitlines(),
            'ARCTIC-PCMANFM-DIAG-END '+json.dumps(dict(status='diagnostic-collected',error=None,evidence_export_complete=True,release_acceptance=False))]
    return temp,'\n'.join(lines),events,runtime,report

class TransportControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=HERE/'execution-tree/tools/pcmanfm-diagnostic' if (HERE/'execution-tree').exists() else HERE
        cls.common,cls.native=R.dependencies(types.SimpleNamespace(bundle=root))
    def check(self,serial,events,runtime):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        return R.checked_report(serial,Path(temp.name)/'unused',events,'d'*64,self.common,self.native,runtime)
    def fixture(self,physical=False,mutate=None):
        temp,*values=transport_fixture(physical,mutate);self.addCleanup(temp.cleanup);return values
    def test_actual_export_extract_full_positive_unrun_physical(self):
        serial,events,runtime,report=self.fixture()
        value=self.check(serial,events,runtime)
        self.assertEqual(value['report'],report);self.assertEqual(value['physical_host_delivery'],'unrun')
    def test_actual_paired_host_delivery_never_mutates_guest_report(self):
        serial,events,runtime,report=self.fixture(True)
        value=self.check(serial,events,runtime)
        self.assertEqual(value['report'],report)
        self.assertIn('separately paired',value['physical_host_delivery'])
        self.assertIn('unknown until',value['report']['arms'][1]['physical']['delivery'])
    def test_missing_duplicate_reordered_begin_end_manifest_and_chunks_rejected(self):
        serial,events,runtime,_=self.fixture()
        rows=serial.splitlines()
        begin=next(i for i,r in enumerate(rows) if r.startswith('ARCTIC-PCMANFM-DIAG-BEGIN '))
        manifest=next(i for i,r in enumerate(rows) if r.startswith('ARCTIC-NATIVE-EVIDENCE-MANIFEST '))
        chunk=next(i for i,r in enumerate(rows) if r.startswith('ARCTIC-NATIVE-EVIDENCE-CHUNK '))
        variants=[rows[:begin]+rows[begin+1:],rows+[rows[begin]],rows[-1:]+rows[:-1],
                  rows[:manifest]+rows[manifest+1:],rows+[rows[manifest]],rows[:chunk]+rows[chunk+1:],rows+[rows[chunk]]]
        for changed in variants:
            with self.subTest(case=variants.index(changed)),self.assertRaises((RuntimeError,ValueError)):self.check('\n'.join(changed),events,runtime)
    def test_transport_bad_hash_base64_length_traversal_reserved_name_unknown_chunk(self):
        serial,events,runtime,_=self.fixture()
        rows=serial.splitlines()
        for mode in ('hash','base64','length','traversal','reserved','unknown'):
            changed=rows.copy()
            index=next(i for i,r in enumerate(changed) if r.startswith('ARCTIC-NATIVE-EVIDENCE-MANIFEST '))
            manifest=json.loads(changed[index].split(' ',1)[1]);entry=manifest['files'][0]
            if mode=='hash':entry['sha256']='0'*64
            elif mode=='length':entry['bytes']+=1
            elif mode=='traversal':entry['path']='../outside.json'
            elif mode=='reserved':entry['path']='transport-manifest.json'
            elif mode in ('base64','unknown'):
                ci=next(i for i,r in enumerate(changed) if r.startswith('ARCTIC-NATIVE-EVIDENCE-CHUNK '))
                value=json.loads(changed[ci].split(' ',1)[1]);value['data']='%%%' if mode=='base64' else value['data']
                if mode=='unknown':value['path']='unknown.json'
                changed[ci]='ARCTIC-NATIVE-EVIDENCE-CHUNK '+json.dumps(value)
            changed[index]='ARCTIC-NATIVE-EVIDENCE-MANIFEST '+json.dumps(manifest)
            with self.subTest(mode=mode),self.assertRaises((RuntimeError,ValueError)):self.check('\n'.join(changed),events,runtime)
    def test_original_failure_source_runtime_security_cleanup_root_claims_fail_closed(self):
        def mutations(case):
            def mutate(root,report,provenance,events,req):
                if case=='original':report['original_status']='passed'
                elif case=='release':report['release_acceptance']=True
                elif case=='source':provenance['native_source_sha256']='0'*64
                elif case=='runtime':provenance['runtime_pins']['native_smoke.py']='0'*64
                elif case=='root':report['evidence_root']='/tmp/arbitrary'
                elif case=='uid':provenance['desktop_uid']=True
                elif case=='permissive':report['security']['selinux']='Permissive'
                elif case=='audit':report['security']['audit']['enabled']=False
                elif case=='boolaudit':report['security']['audit']['enabled']=True
                elif case=='lost':report['security']['audit']['lost']=1
                elif case=='avc':report['security']['observed_new_avcs']=1
                elif case=='first-cleanup':
                    path=root/'original-route/arm-report.json';value=json.loads(path.read_text());value['preservation_phase']='arm-cleanup';path.write_text(json.dumps(value))
                elif case in ('omitted','late-trace'):
                    path=root/'original-route/gui-trace-summary.json';value=json.loads(path.read_text());value['omitted_records']=1;path.write_text(json.dumps(value))
                    if case=='omitted':
                        path=root/'original-route/arm-report.json';value=json.loads(path.read_text());value['trace']['omitted_records']=1;path.write_text(json.dumps(value))
                elif case=='cleanup':
                    path=root/'original-route/arm-report.json';value=json.loads(path.read_text())
                    value['cleanup']['original_copied_configs_unchanged']=False;path.write_text(json.dumps(value))
            return mutate
        for case in ('original','release','source','runtime','root','uid','permissive','audit','boolaudit','lost','avc','cleanup','omitted','late-trace','first-cleanup'):
            serial,events,runtime,_=self.fixture(mutate=mutations(case))
            with self.subTest(case=case),self.assertRaises(RuntimeError):self.check(serial,events,runtime)
    def test_physical_ack_response_nonce_boot_process_age_and_raw_entry_pairing(self):
        for case in ('none','duplicate','nonce','boot','pid','response','age','entry'):
            serial,events,runtime,_=self.fixture(True)
            changed=copy.deepcopy(events)
            if case=='none':changed=[]
            elif case=='duplicate':changed+=copy.deepcopy(changed)
            elif case=='nonce':changed[0]['nonce']='e'*32
            elif case=='boot':changed[0]['boot_id']='99999999-2222-3333-4444-555555555555'
            elif case=='pid':changed[0]['process']['pid']=999
            elif case=='response':changed[0]['response']={'return':False}
            elif case=='age':changed[0]['input_start_monotonic_seconds']=4
            elif case=='entry':
                # Signed/hash-valid transport containing a mismatched immediate entry must still fail.
                def mutate(root,report,provenance,events,req):
                    p=root/'observed-route/entry-09-physical-immediate-precondition.json';value=json.loads(p.read_text())
                    value['after']['foreign_toplevel_id']='foreign';p.write_text(json.dumps(value))
                    req['entry_evidence_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
                    events[0]['request_sha256']=C.canonical(req)
                serial,changed,runtime,_=self.fixture(True,mutate)
            with self.subTest(case=case),self.assertRaises(RuntimeError):self.check(serial,changed,runtime)
    def test_preexisting_extraction_is_preserved_not_overwritten(self):
        serial,events,runtime,_=self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'used';target.mkdir();(target/'sentinel.txt').write_text('keep')
            with self.assertRaises(RuntimeError):R.checked_report(serial,target,events,'d'*64,self.common,self.native,runtime)
            self.assertEqual((target/'sentinel.txt').read_text(),'keep')

def workflow_path(root=HERE):
    audit=root/'registered-iso-diagnostic.yml'
    try: info=audit.lstat()
    except FileNotFoundError:
        selected=root.parents[1]/'.github/workflows/iso.yml'
        info=selected.lstat()
    else:selected=audit
    if not stat.S_ISREG(info.st_mode):
        raise RuntimeError('selected workflow must be a regular file, never symlink/directory: '+str(selected))
    return selected

class SourceControls(unittest.TestCase):
    def test_workflow_default_off_all_other_jobs_skipped_read_only_fixed_artifact(self):
        import yaml
        workflow=yaml.safe_load(workflow_path().read_text())
        inputs=workflow['on' if 'on' in workflow else True]['workflow_dispatch']['inputs']
        self.assertEqual(inputs['same_iso_pcmanfm_diagnostic']['type'],'boolean')
        self.assertIs(inputs['same_iso_pcmanfm_diagnostic']['default'],False)
        jobs=workflow['jobs']
        for name in ('iso','same-iso-installs','same-iso-boot-evidence','same-iso-native-functional'):
            self.assertIn('!inputs.same_iso_pcmanfm_diagnostic',jobs[name]['if'])
        job=jobs['same-iso-pcmanfm-diagnostic'];self.assertEqual(job['permissions'],{'contents':'read','actions':'read'})
        self.assertIn('inputs.same_iso_pcmanfm_diagnostic',job['if']);self.assertEqual(job['timeout-minutes'],45)
        steps=job['steps'];checkout=[s for s in steps if 'uses' in s and s['uses'].startswith('actions/checkout@')]
        self.assertEqual([s['with']['ref'] for s in checkout],['fe4742c8b9414c45f0bcbb0a4191f116383c60d1',R.RECOVERY_BASE,'${{ github.sha }}'])
        self.assertTrue(all(s['with']['persist-credentials'] is False for s in checkout))
        download=next(s for s in steps if s.get('uses','').startswith('actions/download-artifact@'))
        self.assertEqual(download['with']['run-id'],37507582946);self.assertEqual(download['with']['artifact-ids'],11434226349)
        self.assertFalse(any('release' in s.get('uses','') for s in steps))
    def test_workflow_lookup_audit_precedence_and_missing_deployed_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'tools/pcmanfm-diagnostic';root.mkdir(parents=True)
            with self.assertRaises(FileNotFoundError):workflow_path(root).read_bytes()
            deployed=Path(tmp)/'.github/workflows/iso.yml';deployed.parent.mkdir(parents=True);deployed.write_text('deployed')
            self.assertEqual(workflow_path(root).read_text(),'deployed')
            audit=root/'registered-iso-diagnostic.yml';audit.write_text('audit');self.assertEqual(workflow_path(root).read_text(),'audit')
    def test_workflow_selected_directory_symlink_and_malformed_never_fall_back(self):
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'tools/pcmanfm-diagnostic';root.mkdir(parents=True)
            deployed=Path(tmp)/'.github/workflows/iso.yml';deployed.parent.mkdir(parents=True);deployed.write_text('jobs: {}')
            audit=root/'registered-iso-diagnostic.yml';audit.mkdir()
            with self.assertRaises(RuntimeError):workflow_path(root)
            audit.rmdir();audit.symlink_to('missing-file')
            with self.assertRaises(RuntimeError):workflow_path(root)
            audit.unlink();audit.symlink_to(deployed)
            with self.assertRaises(RuntimeError):workflow_path(root)
            audit.unlink();audit.write_text('jobs: [unterminated')
            with self.assertRaises(yaml.YAMLError):yaml.safe_load(workflow_path(root).read_text())
            audit.unlink();deployed.unlink();deployed.symlink_to('missing-file')
            with self.assertRaises(RuntimeError):workflow_path(root)
    def test_manifest_every_exact_execution_and_runtime_file(self):
        manifest=json.loads((HERE/'execution-pins.json').read_text())
        root=HERE/'execution-tree' if (HERE/'execution-tree').exists() else HERE.parents[1]
        self.assertEqual(set(manifest['files']),R.EXECUTION_FILES)
        for path,expected in manifest['files'].items():
            self.assertEqual(hashlib.sha256((root/path).read_bytes()).hexdigest(),expected,path)
        runtime=json.loads((HERE/'runtime-pins.json').read_text());self.assertEqual(len(runtime),10)
        for name,expected in runtime.items():
            data=b'#!/bin/bash\nset -euo pipefail\nexec python3 /run/t/guest-check.py\n' if name=='run.sh' else (HERE/('guest-pcmanfm-diagnostic.py' if name=='guest-check.py' else name)).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(),expected,name)
    def test_original_predecessor_all19_pins_unchanged(self):
        root=HERE/'execution-tree' if (HERE/'execution-tree').exists() else HERE.parents[1]
        pins=json.loads((HERE/'frozen-base-pins.json').read_text());self.assertEqual(len(pins['files']),19)
        for path,expected in pins['files'].items():self.assertEqual(hashlib.sha256((root/path).read_bytes()).hexdigest(),expected,path)
    def test_generator_pure_reproduction_and_default_off_harness_guards(self):
        base=HERE/'base-test-iso.sh';workflow=HERE/'base-iso.yml'
        if not base.exists():self.skipTest('base Git snapshots are audit-only; mapped controls verify deployed execution pins')
        root=HERE/'execution-tree'
        self.assertEqual(P.harness(base.read_text()),(root/'tools/test-iso.sh').read_text())
        self.assertEqual(P.workflow(workflow.read_text()),(root/'.github/workflows/iso.yml').read_text())
        value=P.harness(base.read_text())
        self.assertIn('PCMANFM_DIAGNOSTIC=""',value);self.assertIn('diagnostic output must be unused',value)
        self.assertIn('"$COLLECT" == 0',value);self.assertIn('"$SECUREBOOT" == 0',value)
        self.assertIn('"$TIMEOUT" == 900',value);self.assertIn('"$VGA" == virtio',value)
        self.assertIn('rpm -q "${pkgs[@]}"',value);self.assertIn('vm.quit()',value)
    def test_cleanup_primitives_and_original_transport_library_are_not_monkeypatched(self):
        root=HERE/'execution-tree' if (HERE/'execution-tree').exists() else HERE.parents[1]
        self.assertEqual(hashlib.sha256((root/'tools/same-iso-recovery/vm-only-recovery-v2.py').read_bytes()).hexdigest(),R.COMMON_SHA)
        self.assertEqual(hashlib.sha256((root/'tools/native-functional-v4/native-runner-v4.py').read_bytes()).hexdigest(),R.V4_LIBRARY_SHA)
        tree=ast.parse((HERE/'diagnostic-runner.py').read_text())
        assigned=[ast.unparse(t) for n in ast.walk(tree) if isinstance(n,ast.Assign) for t in n.targets]
        self.assertFalse(any(t.startswith(('R.','V.')) for t in assigned))

if __name__=='__main__':unittest.main(verbosity=2)
