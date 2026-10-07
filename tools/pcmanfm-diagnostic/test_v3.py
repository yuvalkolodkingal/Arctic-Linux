#!/usr/bin/env python3
"""Real bounded Unix stream controls plus synthetic widget/QMP authority; no VM."""
import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
BASE='92aa52c0ef324a2cb5ad4af9f0c47c5e8b273bec'


def load(name,file):
    spec=importlib.util.spec_from_file_location(name,HERE/file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


B=load('v3_bulk','bulk-channel.py');K=load('v3_gtk','gtk-physical.py')
C=load('v3_controller','pcmanfm-controller.py');G=load('v3_guest','guest-pcmanfm-diagnostic.py')


def stream():
    prefixes=('ARCTIC-PCMANFM-DIAG-BEGIN ','ARCTIC-PCMANFM-DIAG-REPORT ',
        'ARCTIC-NATIVE-EVIDENCE-CHUNK ','ARCTIC-NATIVE-EVIDENCE-MANIFEST ','ARCTIC-PCMANFM-DIAG-END ')
    return b''.join((p+json.dumps(dict(index=i))+'\n').encode() for i,p in enumerate(prefixes))


def record(data):
    return dict(schema='arctic-bulk-channel-v1',port_name=B.NAME,bytes=len(data),lines=data.count(b'\n'),
        sha256=hashlib.sha256(data).hexdigest(),actual_socket_eof=True,unfinished_record_bytes=0,
        encoded_limit_bytes=B.MAX_STREAM,newline_limit_bytes=B.MAX_LINE,console_unchanged=True,
        added_diagnostic_device=True,eof_origin='owned-QEMU-exit',socket_peer=dict(pid=os.getpid(),uid=os.getuid(),start_ticks=1),
        release_acceptance=False,shutdown_started=True,owned_vm_exit_status=0,resources_closed=True,close_errors=[])


def request():
    appid='org.arctic.Diagnostic.Entry.a'+'a'*16
    process=dict(pid=321,start_ticks=456,executable='/usr/bin/python3.14',executable_sha256='e'*64,
        is_xwayland=False,client_id='9')
    boot='11111111-2222-3333-4444-555555555555'
    client=dict(pid=321,id=9,appid=appid,title='Arctic Gtk3 diagnostic '+appid,foreign_toplevel_id='own',x=0,y=0,width=480,height=180,monitor='Virtual-1',
        is_xwayland=False,is_focused=True,is_visible=True)
    widget=dict(schema='arctic-gtk-widget-snapshot-v1',nonce='b'*32,appid=appid,title=client['title'],
        pid=321,start_ticks=456,uid=1000,boot_id=boot,monotonic_ns=1000000000,text=K.TEXT,
        has_focus=True,is_focus=True,window_active=True,activations=0)
    return dict(schema='arctic-gtk-physical-request-v1',arm='gtk-no-warmup',nonce='b'*32,appid=appid,
        boot_id=boot,process=process,client=client,widget=widget,widget_evidence_sha256='c'*64,
        virtual_status='own-entry-not-activated',monotonic_ns=1100000000,release_acceptance=False)


class BulkControls(unittest.TestCase):
    def test_actual_fragmented_unix_stream_hash_newline_and_eof(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.addCleanup(server.close)
            server.bind(str(root/'bulk.sock'));server.listen(1)
            receiver=B.Receiver(root,os.getpid());self.addCleanup(receiver.close)
            receiver.connect();peer,_=server.accept();self.addCleanup(peer.close)
            data=stream()
            for fragment in (data[:2],data[2:71],data[71:]):
                peer.sendall(fragment);receiver.pump()
            self.assertFalse(receiver.eof);receiver.begin_shutdown();peer.close();receiver.pump();self.assertTrue(receiver.eof);receiver.observed_vm_exit(0)
            receiver.close()
            self.assertEqual((root/'bulk-evidence.log').read_bytes(),data)
            self.assertEqual(len(B.validate(data,json.loads((root/'bulk-channel.txt').read_text()))),5)

    def test_real_partial_eof_and_owned_peer_mismatch_fail(self):
        for mode in ('partial','peer'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
                try:
                    server.bind(str(root/'bulk.sock'));server.listen(1)
                    receiver=B.Receiver(root,os.getpid())
                    try:
                        if mode=='peer':
                            receiver.expected_pid+=100000
                            with self.assertRaises(RuntimeError):receiver.connect()
                        else:
                            receiver.connect();peer,_=server.accept();receiver.begin_shutdown()
                            try:peer.sendall(b'partial');peer.close();
                            finally:peer.close()
                            with self.assertRaises(RuntimeError):receiver.pump()
                    finally:receiver.close()
                finally:server.close()

    def test_actual_stream_overflow_is_failure_with_raw_bytes_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
            try:
                server.bind(str(root/'bulk.sock'));server.listen(1);receiver=B.Receiver(root,os.getpid())
                try:
                    receiver.connect();peer,_=server.accept()
                    try:
                        peer.sendall(b'x'*100)
                        with patch.object(B,'MAX_STREAM',64),self.assertRaises(RuntimeError):receiver.pump()
                        self.assertEqual(receiver.bytes,100)
                        self.assertEqual((root/'bulk-evidence.log').read_bytes(),b'x'*100)
                    finally:peer.close()
                finally:receiver.close()
            finally:server.close()

    def test_protocol_order_duplicate_unknown_blank_nonfinite_and_json_duplicates_rejected(self):
        good=stream();rows=good.splitlines(keepends=True);B.validate(good,record(good))
        variants=[b''.join(rows[::-1]),b''.join(rows+rows[-1:]),b''.join(rows[1:]),b''.join(rows[:-1]),
            good+b'unknown {}\n',good.replace(rows[2],b'\n'),good.replace(rows[0],b'ARCTIC-PCMANFM-DIAG-BEGIN {"x":1,"x":2}\n'),
            good.replace(rows[0],b'ARCTIC-PCMANFM-DIAG-BEGIN {"x":NaN}\n'),
            good.replace(rows[0],b'ARCTIC-PCMANFM-DIAG-BEGIN []\n'),good[:-1]]
        for data in variants:
            with self.subTest(data=data[:80]),self.assertRaises((RuntimeError,ValueError)):B.validate(data,record(data))

    def test_raw_count_hash_eof_typed_pid_limits_and_device_provenance_reject(self):
        data=stream()
        for field,value in [('bytes',True),('bytes',len(data)+1),('lines',True),('sha256','a'*64),
            ('actual_socket_eof',False),('unfinished_record_bytes',1),('console_unchanged',False),
            ('added_diagnostic_device',False),('eof_origin','guest-fd-close'),('port_name','wrong'),('shutdown_started',False),('owned_vm_exit_status',None),('owned_vm_exit_status',True),('close_errors',['failure']),('resources_closed',False),
            ('encoded_limit_bytes',B.MAX_STREAM+1),('socket_peer',dict(pid=True,uid=0,start_ticks=1))]:
            metadata=record(data);metadata[field]=value
            with self.subTest(field=field),self.assertRaises(RuntimeError):B.validate(data,metadata)

    def test_real_writer_pipe_exact_bytes_and_bound_no_console_fallback(self):
        read,write=os.pipe();writer=object.__new__(B.Writer)
        writer.fd=write;writer.bytes=writer.lines=0;writer.digest=hashlib.sha256();writer.export_deadline=None
        try:
            writer.write('PREFIX ',dict(x='literal'))
            expected=b'PREFIX {"x": "literal"}\n'
            self.assertEqual(os.read(read,1024),expected);self.assertEqual(writer.digest.hexdigest(),hashlib.sha256(expected).hexdigest())
            with patch.object(B,'MAX_STREAM',1),self.assertRaises(RuntimeError):writer.write('PREFIX ',{})
        finally:writer.close();os.close(read)

    def test_guest_chunks_only_use_explicit_bulk_preserving_payload_caps(self):
        rows=[];fake=type('Sink',(),{'write':lambda self,p,v:rows.append((p,v))})()
        with tempfile.TemporaryDirectory() as tmp,patch.object(G,'BULK',fake),patch('builtins.print') as printed:
            root=Path(tmp);(root/'fixture.txt').write_bytes(b'literal evidence')
            G.export_bulk(root);printed.assert_not_called()
            self.assertEqual(rows[0][0],'ARCTIC-NATIVE-EVIDENCE-CHUNK ')
            self.assertEqual(rows[-1][0],'ARCTIC-NATIVE-EVIDENCE-MANIFEST ')
            self.assertEqual(G.MAX_FILE,4*1024*1024);self.assertEqual(G.MAX_TOTAL,16*1024*1024)


    def test_real_socket_and_raw_stream_close_failure_closes_both_and_preserves_first_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
                server.bind(str(root/'bulk.sock'));server.listen(1)
                receiver=B.Receiver(root,os.getpid());receiver.connect();peer,_=server.accept()
                with peer:
                    actual_stream=receiver.stream;actual_socket=receiver.socket
                    with patch.object(actual_stream,'close',side_effect=OSError('controlled flush-close failure')):
                        with self.assertRaisesRegex(RuntimeError,'controlled flush-close failure'):receiver.close()
                    self.assertTrue(actual_stream.closed);self.assertEqual(actual_socket.fileno(),-1)
                    receiver.close() # Idempotent only after all resource close attempts.
                value=json.loads((root/'bulk-channel.txt').read_text())
                self.assertTrue(value['resources_closed']);self.assertIn('controlled flush-close failure',value['close_errors'][0])

    def test_actual_owned_wrapper_quit_failure_preserves_primary_and_closes_connection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
                server.bind(str(root/'bulk.sock'));server.listen(1)
                vm=type('VM',(),{'proc':type('Proc',(),{'pid':os.getpid()})(),
                    'quit':lambda self:(_ for _ in ()).throw(RuntimeError('controlled quit failure'))})()
                def action(receiver):raise ValueError('primary controller failure')
                with self.assertRaisesRegex(ValueError,'primary controller failure'):
                    B.run_owned(vm,root,action,1)
                with server.accept()[0] as peer:self.assertEqual(peer.recv(1),b'')
                value=json.loads((root/'bulk-shutdown.txt').read_text())
                self.assertEqual(value['primary_error'],'ValueError: primary controller failure')
                self.assertIn('controlled quit failure',value['cleanup_errors'][0])
                self.assertTrue(json.loads((root/'bulk-channel.txt').read_text())['resources_closed'])

    def test_owned_wrapper_absolute_eof_allowance_is_anchored_before_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            class Clock:
                value=0
                def __call__(self):return self.value
                def sleep(self,seconds):self.value+=seconds
            clock=Clock();receivers=[]
            class Receiver:
                def __init__(self,*_):self.eof=False;self.pumps=self.closes=0;receivers.append(self)
                def connect(self):pass
                def begin_shutdown(self):pass
                def observed_vm_exit(self,status):self.status=status
                def pump(self):self.pumps+=1;self.eof=True
                def close(self):self.closes+=1
            vm=types.SimpleNamespace(proc=types.SimpleNamespace(pid=os.getpid(),poll=lambda:0),quit=lambda:None)
            with patch.object(B,'Receiver',Receiver),self.assertRaisesRegex(RuntimeError,'real data socket EOF absent'):
                B.run_owned(vm,Path(tmp),lambda _:clock.sleep(2),1,clock,clock.sleep)
            self.assertEqual(receivers[0].pumps,0);self.assertEqual(receivers[0].closes,1)
            self.assertEqual(clock.value,2)
            raw=json.loads((Path(tmp)/'bulk-shutdown.txt').read_text());self.assertIsNone(raw['primary_error'])
            self.assertIn('real data socket EOF absent',raw['cleanup_errors'][0])

    def test_owned_wrapper_validation_error_still_performs_owned_quit(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[];vm=types.SimpleNamespace(quit=lambda:calls.append('quit'))
            with self.assertRaisesRegex(RuntimeError,'remaining harness deadline differs'):
                B.run_owned(vm,Path(tmp),lambda _:None,True)
            self.assertEqual(calls,['quit'])
            value=json.loads((Path(tmp)/'bulk-shutdown.txt').read_text());self.assertIn('remaining harness deadline differs',value['primary_error'])

    def test_owned_wrapper_clock_setup_error_still_performs_owned_quit(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[];vm=types.SimpleNamespace(quit=lambda:calls.append('quit'))
            def clock():raise OSError('controlled monotonic setup error')
            with self.assertRaisesRegex(OSError,'monotonic setup error'):
                B.run_owned(vm,Path(tmp),lambda _:None,1,clock)
            self.assertEqual(calls,['quit'])
            self.assertIn('monotonic setup error',json.loads((Path(tmp)/'bulk-shutdown.txt').read_text())['primary_error'])

    def test_unexpected_real_socket_eof_before_shutdown_is_preserved_and_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
                server.bind(str(root/'bulk.sock'));server.listen(1)
                receiver=B.Receiver(root,os.getpid())
                try:
                    receiver.connect();peer,_=server.accept()
                    with peer:peer.sendall(stream())
                    with self.assertRaisesRegex(RuntimeError,'before owned QEMU shutdown'):receiver.pump()
                finally:receiver.close()
                meta=json.loads((root/'bulk-channel.txt').read_text())
                self.assertFalse(meta['shutdown_started']);self.assertIsNone(meta['owned_vm_exit_status'])
                with self.assertRaises(RuntimeError):B.validate((root/'bulk-evidence.log').read_bytes(),meta)

    def test_actual_full_pipe_writer_deadline_and_nonfinite_fail_without_fallback(self):
        read,write=os.pipe();os.set_blocking(write,False)
        writer=object.__new__(B.Writer);writer.fd=write;writer.bytes=writer.lines=0
        writer.digest=hashlib.sha256();writer.export_deadline=None
        try:
            with self.assertRaises(ValueError):writer.write('PREFIX ',dict(value=float('nan')))
            while True:
                try:os.write(write,b'x'*4096)
                except BlockingIOError:break
            with patch.object(B,'WRITE_SECONDS',.03),self.assertRaisesRegex(RuntimeError,'deadline'):
                writer.write('PREFIX ',dict(x=1))
            self.assertEqual(writer.lines,0);self.assertEqual(writer.bytes,0)
        finally:writer.close();os.close(read)

    def test_maximum_decoded_payload_reuses_frozen_content_extractor_under_encoded_cap(self):
        import random
        T=load('max_payload_v2_fixtures','test_diagnostic.py')
        R=load('maximum_payload_runner','diagnostic-runner.py')
        root=HERE/'execution-tree/tools/pcmanfm-diagnostic' if (HERE/'execution-tree').exists() else HERE
        _,V=R.dependencies(type('Args',(),dict(bundle=root))())
        random_source=random.Random(937)
        with tempfile.TemporaryDirectory() as tmp:
            evidence=Path(tmp)/'in';evidence.mkdir();rows=[]
            for i in range(4):(evidence/('max-%d.log'%i)).write_bytes(random_source.randbytes(G.MAX_FILE))
            sink=type('Sink',(),{'write':lambda self,p,v:rows.append(p+json.dumps(v,sort_keys=True))})()
            with patch.object(G,'BULK',sink):G.export_bulk(evidence)
            encoded=('\n'.join(rows)+'\n').encode()
            self.assertLess(len(encoded)+3*B.MAX_LINE,B.MAX_STREAM)
            copied=V.extract_evidence(rows,'live',Path(tmp)/'out')
            self.assertEqual(sum(row['bytes'] for row in copied.values()),G.MAX_TOTAL)
            for relative in copied:self.assertEqual((Path(tmp)/'out'/relative).read_bytes(),(evidence/relative).read_bytes())



class GTKControls(unittest.TestCase):
    def test_strict_own_physical_proof_positive_and_adverse_identity_focus_text_freshness(self):
        good=request();K.validate(good)
        cases=[('process','pid',True),('process','start_ticks',0),('process','executable','/tmp/python3'),
            ('client','pid',999),('client','is_focused',False),('client','is_xwayland',True),
            ('client','title','foreign'),('widget','text','wrong'),('widget','has_focus',False),
            ('widget','is_focus',False),('widget','window_active',False),('widget','activations',True),
            ('widget','activations',1),('widget','uid',0),('widget','pid',999),('widget','nonce','d'*32),
            ('widget','monotonic_ns',1),('widget','monotonic_ns',True),('widget','monotonic_ns',-1000)]
        for member,key,value in cases:
            changed=copy.deepcopy(good);changed[member][key]=value
            with self.subTest(member=member,key=key),self.assertRaises(RuntimeError):K.validate(changed)

    def test_callback_always_returns_false_and_never_mutates_binding_or_im(self):
        tree=ast.parse((HERE/'gtk-entry-control.py').read_text())
        event=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='event')
        self.assertEqual(ast.dump(event.body[-1]),ast.dump(ast.Return(value=ast.Constant(value=False))))
        calls=[ast.unparse(n.func) for n in ast.walk(event) if isinstance(n,ast.Call)]
        self.assertIn('current_map',calls)
        for banned in ('activate','emit','bindings_activate','filter_keypress','set_property','set_im_module'):
            self.assertFalse(any(banned in c for c in calls))
        read=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='read_map')
        text=ast.unparse(read)
        self.assertIn('keymap.translate_keyboard_state(value.hardware_keycode, value.state, value.group)',text)
        self.assertIn('keymap.get_entries_for_keyval(Gdk.KEY_Return)',text)

    def test_actual_gi_signature_if_host_dependency_available(self):
        try:import gi
        except ImportError:self.skipTest('host GI absent; actual guest GTK keymap translation remains unrun')
        gi.require_version('Gdk','3.0')
        from gi.repository import Gdk
        self.assertIn('hardware_keycode',Gdk.Keymap.translate_keyboard_state.__doc__)
        self.assertIn('keys',Gdk.Keymap.get_entries_for_keyval.__doc__)

    def test_no_extra_physical_input_when_virtual_pass_or_unfocused(self):
        smoke=type('Smoke',(),{'alive':lambda self,p:dict(is_focused=False)})()
        self.assertEqual(G.gtk_physical(smoke,{},'unused','own-entry-activated')['status'],'unrun')
        self.assertEqual(G.gtk_physical(smoke,{},'unused','own-entry-not-activated')['status'],'unrun')

    def test_both_original_gtk_virtual_key_turns_and_30s_gate_retained(self):
        tree=ast.parse((HERE/'guest-pcmanfm-diagnostic.py').read_text())
        control=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='gtk_control')
        source=ast.unparse(control)
        self.assertIn("(['-M', 'ctrl', '-k', 'a', '-m', 'ctrl'], [text], ['-k', 'Return'])",source)
        self.assertIn("smoke.wait(activated, 30, label='isolated Gtk3 entry activation')",source)
        self.assertLess(source.index('smoke.wait(activated, 30'),source.index('gtk_physical'))
        self.assertIn("if not warmup else dict(status='unrun'",source)

    def test_actual_new_controller_single_gtk_input_and_duplicate_stale_bad_qmp_reject(self):
        T=load('prior_v2_control_fixtures','test_diagnostic.py')
        for variant in ('pass','duplicate','stale','bad-qmp','wrong-boot','unfocused','foreign-uid','negative-time'):
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);clock=T.FakeClock()
                class VM(T.FakeVM):
                    def update(self):
                        super().update()
                        if self.bootstrapped is None:return
                        req=request()
                        if variant=='wrong-boot':req['boot_id']='99999999-2222-3333-4444-555555555555'
                        if variant=='unfocused':req['client']['is_focused']=False
                        if variant=='foreign-uid':req['widget']['uid']=1001
                        if variant=='negative-time':req['monotonic_ns']=-900;req['widget']['monotonic_ns']=-1000
                        text=(self.root/'serial.log').read_text()
                        lines=[]
                        for line in text.splitlines():
                            if line.startswith('ARCTIC-NATIVE-LAUNCHER-GONE '):
                                gone=json.loads(line.split(' ',1)[1]);gone.update(foot=dict(uid=1000),shell=dict(uid=1000))
                                line='ARCTIC-NATIVE-LAUNCHER-GONE '+json.dumps(gone)
                            lines.append(line)
                        text='\n'.join(lines)+'\n'
                        row='ARCTIC-GTK-PHYSICAL-REQUEST '+json.dumps(req)+'\n'
                        (self.root/'serial.log').write_text(text+row+(row if variant=='duplicate' else ''))
                    def shot(self,name):
                        if variant=='stale' and name=='gtk-physical-before-return':clock.sleep(3)
                        return super().shot(name)
                vm=VM(root,clock,'no-request',{'return':False} if variant=='bad-qmp' else None)
                class Bulk:
                    def pump(self):vm.update()
                    def text(self):vm.update();return (root/'serial.log').read_text()
                if variant=='pass':
                    C.run_v3(vm,root,True,'d'*64,Bulk(),clock,clock.sleep)
                    self.assertEqual(len(vm.qmp),1)
                    events=[json.loads(row) for row in (root/'pcmanfm-host-events.log').read_text().splitlines()]
                    self.assertEqual(sum(e['event']=='gtk-physical-host-ack' for e in events),1)
                    self.assertEqual(sum(e['event']=='physical-host-ack' for e in events),0)
                else:
                    with self.assertRaises(RuntimeError):C.run_v3(vm,root,True,'d'*64,Bulk(),clock,clock.sleep)
                    self.assertEqual(len(vm.qmp),1 if variant=='bad-qmp' else 0)

    def test_actual_paired_gtk_physical_raw_proof_positive_and_missing_changed_members_reject(self):
        T=load('gtk_positive_transport_fixtures','test_diagnostic.py');R=load('gtk_positive_runner','diagnostic-runner.py')
        root=HERE/'execution-tree/tools/pcmanfm-diagnostic' if (HERE/'execution-tree').exists() else HERE
        _,V=R.dependencies(type('Args',(),dict(bundle=root))())
        common=type('Common',(),{'digest':staticmethod(lambda p:hashlib.sha256(p.read_bytes()).hexdigest())})()
        for variant in ('pass','process','widget-file','mapped-log','bad-ack'):
            with self.subTest(variant=variant):
                temp,serial,events,runtime,report=T.transport_fixture()
                try:
                    evidence=Path(temp.name);req=request()
                    provenance=json.loads((evidence/'provenance.json').read_text())
                    provenance['bulk_port']=dict(name=B.NAME,sysfs_name=B.NAME,named_path='/dev/virtio-ports/'+B.NAME,
                        resolved_device='/dev/vport0p1',kind='character-device',device_major=243,device_minor=1)
                    (evidence/'provenance.json').write_text(json.dumps(provenance))
                    raw=dict(process=req['process'],before=req['client'],after=req['client'],widget=req['widget'])
                    proof=evidence/'gtk-no-warmup/gtk-immediate-proof.json';proof.write_text(json.dumps(raw))
                    req['widget_evidence_sha256']=hashlib.sha256(proof.read_bytes()).hexdigest()
                    widget_path=evidence/'gtk-no-warmup/gtk-widget-snapshot.json';widget_path.write_text(json.dumps(req['widget']))
                    mapped=dict(event='mapped',pid=req['process']['pid'],start_ticks=req['process']['start_ticks'],uid=1000,
                        appid=req['appid'],program_name=req['appid'],backend='GdkWaylandDisplay')
                    event_path=evidence/'gtk-no-warmup/gtk-events.log'
                    event_path.write_text(json.dumps(mapped)+'\n'+json.dumps(dict(event='owned-widget-snapshot',snapshot=req['widget']))+'\n')
                    report['arms'][3].update(status='own-entry-not-activated',process=copy.deepcopy(req['process']),
                        physical=dict(status='own-entry-not-activated-after-request',request=req))
                    ack=dict(event='gtk-physical-host-ack',nonce=req['nonce'],boot_id=req['boot_id'],process=req['process'],
                        request_sha256=K.canonical(req),exactly_one_press_release=True,release_acceptance=False,
                        receipt_monotonic_seconds=1,input_start_monotonic_seconds=1.1,input_end_monotonic_seconds=1.2,response={'return':{}})
                    if variant=='process':report['arms'][3]['process']['pid']+=1
                    if variant=='widget-file':widget_path.unlink()
                    if variant=='mapped-log':mapped['pid']+=1;event_path.write_text(json.dumps(mapped)+'\n')
                    if variant=='bad-ack':ack['response']={'return':False}
                    (evidence/'report.json').write_text(json.dumps(report))
                    output=[];sink=type('Sink',(),{'write':lambda self,p,v:output.append(p+json.dumps(v,sort_keys=True))})()
                    with patch.object(G,'BULK',sink):G.export_bulk(evidence)
                    begin=next(line for line in serial.splitlines() if line.startswith('ARCTIC-PCMANFM-DIAG-BEGIN '))
                    end=next(line for line in serial.splitlines() if line.startswith('ARCTIC-PCMANFM-DIAG-END '))
                    bulk='\n'.join([begin,'ARCTIC-PCMANFM-DIAG-REPORT '+json.dumps(report),*output,end])+'\n'
                    console=next(line for line in serial.splitlines() if line.startswith('ARCTIC-NATIVE-LAUNCHER-GONE '))+'\nARCTIC-GTK-PHYSICAL-REQUEST '+json.dumps(req)+'\n'
                    if variant=='pass':
                        result=R.checked_bulk_report(bulk,console,evidence/'paired-gtk',events+[ack],'d'*64,common,V,runtime)
                        self.assertIn('GTK QMP Return',result['gtk_physical_host_delivery'])
                    else:
                        with self.assertRaises((RuntimeError,ValueError,FileNotFoundError)):
                            R.checked_bulk_report(bulk,console,evidence/'paired-gtk',events+[ack],'d'*64,common,V,runtime)
                finally:temp.cleanup()

    def test_actual_new_host_bulk_validator_keeps_raw_origins_and_pairs_raw_widget(self):
        T=load('v2_transport_fixtures_for_bulk','test_diagnostic.py')
        R=load('v3_host_runner','diagnostic-runner.py')
        root=HERE/'execution-tree/tools/pcmanfm-diagnostic' if (HERE/'execution-tree').exists() else HERE
        _,V=R.dependencies(type('Args',(),dict(bundle=root))())
        common=type('Common',(),{'digest':staticmethod(lambda p:hashlib.sha256(p.read_bytes()).hexdigest())})()
        temp,serial,events,runtime,report=T.transport_fixture()
        try:
            # These are synthetic GUI/security proofs, not a actual guest pass.
            evidence=Path(temp.name)
            parsed=[]
            for line in serial.splitlines():
                if line.startswith('ARCTIC-PCMANFM-DIAG-REPORT '):
                    value=json.loads(line.split(' ',1)[1]);value['arms'][3]['physical']=dict(status='unrun')
                    line='ARCTIC-PCMANFM-DIAG-REPORT '+json.dumps(value,sort_keys=True)
                parsed.append(line)
            # Re-encode the report member to match the separately transported summary.
            report['arms'][3]['physical']=dict(status='unrun')
            provenance=json.loads((evidence/'provenance.json').read_text())
            provenance['bulk_port']=dict(name=B.NAME,sysfs_name=B.NAME,named_path='/dev/virtio-ports/'+B.NAME,
                resolved_device='/dev/vport0p1',kind='character-device',device_major=243,device_minor=1)
            (evidence/'provenance.json').write_text(json.dumps(provenance))
            (evidence/'report.json').write_text(json.dumps(report))
            output=[]
            fake=type('Sink',(),{'write':lambda self,p,v:output.append(p+json.dumps(v,sort_keys=True))})()
            with patch.object(G,'BULK',fake):G.export_bulk(evidence)
            begin=next(line for line in parsed if line.startswith('ARCTIC-PCMANFM-DIAG-BEGIN '))
            report_line=next(line for line in parsed if line.startswith('ARCTIC-PCMANFM-DIAG-REPORT '))
            end=next(line for line in parsed if line.startswith('ARCTIC-PCMANFM-DIAG-END '))
            bulk='\n'.join([begin,report_line,*output,end])+'\n'
            console='\n'.join(line for line in parsed if line.startswith('ARCTIC-NATIVE-LAUNCHER-GONE '))+'\n'
            result=R.checked_bulk_report(bulk,console,evidence/'bulk-result',events,'d'*64,common,V,runtime)
            self.assertEqual(result['gtk_physical_host_delivery'],'unrun')
            with self.assertRaises((RuntimeError,ValueError)):
                R.checked_bulk_report(bulk,'',evidence/'missing-console',events,'d'*64,common,V,runtime)
        finally:temp.cleanup()


class SourceParityControls(unittest.TestCase):
    def test_exact_prior_original_routes_old_console_decoder_and_controller_ast(self):
        base=HERE/'v2-source-snapshots'
        if not base.is_dir():self.skipTest('prior AST snapshots audit-only; mapped source pins checked separately')
        for file,names in [('guest-pcmanfm-diagnostic.py',('observed_navigate','physical','scenario','navigation_result','control_keys','export')),
            ('diagnostic-runner.py',('checked_report','checked_security')),
            ('pcmanfm-controller.py',('run','physical_request','qmp_return'))]:
            def funcs(path):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef)}
            current=funcs(HERE/file);prior=funcs(base/file)
            for name in names:self.assertEqual(current[name],prior[name],file+':'+name)

    def test_raw_inline_kernel_anomaly_offsets_are_preserved_not_filtered(self):
        R=load('kernel_console_observer','diagnostic-runner.py')
        raw=b'ARCTIC-NATIVE-EVIDENCE-CHUNK {"data":"abc[424.1] watchdog: BUG: soft lockup - CPU#0\n[424.2] 100% hardIRQ\n'
        value=R.console_observations(raw)
        self.assertEqual(value['bytes'],len(raw));self.assertEqual(value['sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(value['matches'][0]['byte_offset'],raw.index(b'watchdog:'))
        self.assertTrue(value['raw_console_unchanged']);self.assertFalse(value['release_acceptance'])
        self.assertEqual(raw[:value['matches'][0]['line_bytes']],raw.splitlines()[0])

    def test_actual_generated_import_failure_preserves_owned_vm_quit(self):
        P=load('import_failure_prepare','prepare-diagnostic.py')
        base=HERE/'base-test-iso.sh'
        if base.exists():harness=P.harness(base.read_text())
        else:harness=(HERE.parents[1]/'tools/test-iso.sh').read_text()
        start=harness.index("DRIVER <<'PY'");start=harness.index('\n',start)+1;end=harness.index('\nPY\n',start)
        tree=ast.parse(harness[start:end])
        node=next(n for n in tree.body if isinstance(n,ast.If) and 'PCMANFM_DIAGNOSTIC' in ast.unparse(n.test))
        code=compile(ast.Module(body=[node],type_ignores=[]),'actual-diagnostic-driver-branch','exec')
        for target in ('pcmanfm_controller','diagnostic_bulk_channel'):
            with self.subTest(target=target):
                calls=[]
                class Loader:
                    def __init__(self,name):self.name=name
                    def exec_module(self,module):
                        if self.name==target:raise RuntimeError('controlled actual import failure '+target)
                def spec(name,path):return types.SimpleNamespace(loader=Loader(name))
                vm=types.SimpleNamespace(quit=lambda:calls.append('quit'))
                namespace=dict(os=types.SimpleNamespace(environ={'PCMANFM_DIAGNOSTIC':'1','PCMANFM_CHECKER_SHA':'d'*64}),
                    vm=vm,out='/unused',menu_seen=True,sys=types.SimpleNamespace(exit=lambda _:None),
                    time=time,timeout=900,vmtest=types.SimpleNamespace(T0=time.time()))
                with patch('importlib.util.spec_from_file_location',side_effect=spec),patch('importlib.util.module_from_spec',side_effect=lambda _:types.SimpleNamespace()),self.assertRaisesRegex(RuntimeError,'actual import failure'):
                    exec(code,namespace)
                self.assertEqual(calls,['quit'])

    def test_extra_channel_only_diagnostic_branch_console_and_frozen_libraries_unchanged(self):
        P=load('v3_prepare','prepare-diagnostic.py')
        snapshots=HERE/'base-test-iso.sh'
        if not snapshots.exists():self.skipTest('base Git snapshots audit-only; mapped pin proof separate')
        base=snapshots.read_text();new=P.harness(base)
        self.assertIn('-serial "file:$OUT/serial.log" -monitor none -no-reboot',new)
        self.assertEqual(new.count('-device virtio-serial-pci,id=arctic_bulk_bus'),1)
        self.assertIn('bulk_module.run_owned(vm, out,',new)
        self.assertIn('vmtest.T0+timeout-time.time()',new)
        wrapper=ast.unparse(next(n for n in ast.parse((HERE/'bulk-channel.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='run_owned'))
        self.assertIn('receiver.begin_shutdown()',wrapper);self.assertIn('receiver.close()',wrapper)
        self.assertIn('receiver.observed_vm_exit(vm.proc.poll())',wrapper)
        # Restoring just explicit edits reproduces the whole prior source, including kernel args.
        prior=HERE/'v2-source-snapshots'
        self.assertEqual((prior/'native-launcher.py').read_bytes(),(HERE/'native-launcher.py').read_bytes())
        self.assertEqual((prior/'security-collector.py').read_bytes(),(HERE/'security-collector.py').read_bytes())


if __name__=='__main__':unittest.main(verbosity=2)
