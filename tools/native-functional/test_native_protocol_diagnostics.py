#!/usr/bin/env python3
"""Host-only protocol/privacy/resource controls; no guest, media or VM."""
import ast
import ctypes.util
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock,patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('native_protocol_controls',HERE/'native_smoke.py')
N=importlib.util.module_from_spec(spec);spec.loader.exec_module(N)


def restore_native_source(text):
    """Reverse only the explicit diagnostic instrumentation, byte for byte."""
    text=text.replace('import selectors\n','').replace('import threading\n','')
    a=text.index('# BEGIN NATIVE_PROTOCOL_DIAGNOSTICS\n')
    z=text.index('# END NATIVE_PROTOCOL_DIAGNOSTICS\n',a)+len('# END NATIVE_PROTOCOL_DIAGNOSTICS\n\n\n')
    text=text[:a]+text[z:]
    a=text.index('    def launch_protocol_player(');z=text.index('    def setup(',a)
    text=text[:a]+text[z:]
    text=text.replace('(self.launch_protocol_player if getattr(self,\'gui_v6\',False) else self.launch)(', 'self.launch(')
    text=text.replace("        if getattr(self,'gui_v6',False):\n            self.native_protocol_diagnostic(player,state,screenshot,client)\n",'')
    text=text.replace('        smoke.finish_native_protocol()\n','')
    return text


def line(iface,object_id,op,args='',send=True,queue=False):
    return (f'[ 123.456] '+('{Default Queue} ' if queue else '')+(' -> ' if send else '')
            +f'{iface}#{object_id}.{op}({args})\n').encode()


def positive():
    p=N.NativeProtocolProjection()
    data=[line('wl_display',1,'get_registry','new id wl_registry#2'),
          line('wl_registry',2,'bind','1, "wl_compositor", 6, new id [unknown]#3'),
          line('wl_registry',2,'bind','2, "xdg_wm_base", 6, new id [unknown]#4'),
          line('wl_registry',2,'bind','3, "wp_viewporter", 1, new id [unknown]#5'),
          line('wl_registry',2,'bind','4, "wl_shm", 1, new id [unknown]#6'),
          line('wl_compositor',3,'create_surface','new id wl_surface#7'),
          line('xdg_wm_base',4,'get_xdg_surface','new id xdg_surface#8, wl_surface#7'),
          line('xdg_surface',8,'get_toplevel','new id xdg_toplevel#9'),
          line('xdg_toplevel',9,'configure','1280, 720, array[4]',False),
          line('xdg_surface',8,'configure','77',False),line('xdg_surface',8,'ack_configure','77'),
          line('wp_viewporter',5,'get_viewport','new id wp_viewport#10, wl_surface#7'),
          line('wp_viewport',10,'set_destination','1280, 720'),
          line('wp_viewport',10,'set_source','0.00000000, 0.00000000, 1280.00000000, 720.00000000'),
          line('wl_shm',6,'create_pool','new id wl_shm_pool#11, fd 5, 3686400'),
          line('wl_shm_pool',11,'create_buffer','new id wl_buffer#12, 0, 1280, 720, 5120, 0'),
          line('wl_surface',7,'attach','wl_buffer#12, 0, 0'),line('wl_surface',7,'commit')]
    for row in data:p.feed(row)
    return p,data


def wayland_126_line(row, clock=(13,38,2,123456), queue=b'private-queue-label'):
    # Wayland 1.26.0 src/connection.c wl_closure_print, lines 1560-1582:
    # https://gitlab.freedesktop.org/wayland/wayland/-/raw/1.26.0/src/connection.c
    # SHA256 2db8435dfd051ee3f8b7fae5c37eb35d22c21cc158fc21f77bcf3d4b920a4f1f
    # Run its C formatter literals through libc; the diagnostic regex is not
    # used to produce this independent input. This exercises the uncolored
    # non-TTY path without optional thread IDs. FORCE_COLOR can still force
    # ANSI output; that format remains deliberately unprojected.
    buffer=ctypes.create_string_buffer(256)
    snprintf=ctypes.CDLL(None).snprintf;snprintf.restype=ctypes.c_int
    count=snprintf(buffer,ctypes.c_size_t(len(buffer)),b'%s[%02u:%02u:%02u.%06u] ',
                   b'',*(ctypes.c_uint(v) for v in clock))
    if not 0<count<len(buffer):raise AssertionError('formatter fixture byte bound')
    prefix=buffer.raw[:count]
    if queue is not None:
        count=snprintf(buffer,ctypes.c_size_t(len(buffer)),b'%s{%s} ',b'',queue)
        if not 0<count<len(buffer):raise AssertionError('queue fixture byte bound')
        prefix+=buffer.raw[:count]
    return prefix+row.split(b'] ',1)[1]


class ProtocolControls(unittest.TestCase):
    def test_byte_reversal_preserves_all_inherited_native_code(self):
        text=(HERE/'native_smoke.py').read_text(); restored=restore_native_source(text)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),
                         '99d5814d438f8777ea5292205b1b70b9c3c3bd12eeefc5ddc77d002693c8a73b')

    def test_positive_typed_geometry_is_not_video_or_display_acceptance(self):
        p,_=positive(); result=p.snapshot()
        self.assertEqual(result['status'],'observed');self.assertEqual(result['unique_xdg_root_id'],7)
        self.assertEqual(result['structural_surfaces'][0]['viewport_destination'],[1280,720])
        self.assertEqual(result['records'][-1]['client_transaction']['ack_serial'],77)
        self.assertFalse(result['video_surface_identified']);self.assertFalse(result['compositor_commit_or_display_proven'])
        self.assertEqual(p.buffers[12]['stride'],5120)

    def test_at_separator_old_format_and_queue_label_are_accepted_without_label_export(self):
        p,data=positive();q=N.NativeProtocolProjection()
        for row in data:q.feed(row.replace(b'#',b'@').replace(b'] ',b'] {private-queue-label} '))
        a,b=p.snapshot(),q.snapshot();a.pop('input_bytes');b.pop('input_bytes')
        self.assertEqual(a,b)
        self.assertNotIn('private-queue-label',json.dumps(q.snapshot()))

    def test_wayland_126_actual_C_clock_formatter_replays_same_typed_lifecycle(self):
        old,data=positive()
        for clock,queue in [((0,0,0,0),None),((13,38,2,123456),b'private-queue-label'),
                            ((23,59,59,999999),b'Default Queue')]:
            with self.subTest(clock=clock,queue_present=queue is not None):
                p=N.NativeProtocolProjection()
                for row in data:p.feed(wayland_126_line(row,clock,queue))
                expected,actual=old.snapshot(),p.snapshot()
                expected.pop('input_bytes');actual.pop('input_bytes')
                self.assertEqual(actual,expected)
                self.assertFalse(actual['video_surface_identified'])
                self.assertFalse(actual['compositor_commit_or_display_proven'])
                self.assertNotIn('private-queue-label',json.dumps(actual))
                self.assertNotIn('13:38:02',json.dumps(actual))

    def test_wayland_126_malformed_clock_prefixes_and_optional_thread_color_are_omitted(self):
        _,data=positive();message=data[0].split(b'] ',1)[1]
        for prefix in [b'[24:00:00.000000] ',b'[00:60:00.000000] ',b'[00:00:60.000000] ',
                       b'[00:00:00.00000] ',b'[00:00:00.0000000] ',b'[0:00:00.000000] ',
                       b'[00:00:00.000000] TID#secret ',b'\x1b[32m[00:00:00.000000] ',
                       b'[00:00:00.000000] {'+b'x'*81+b'} ',
                       b'[00:00:00.000000] {private\rqueue} ']:
            with self.subTest(prefix_hash=hashlib.sha256(prefix).hexdigest()):
                p=N.NativeProtocolProjection();p.feed(prefix+message)
                self.assertEqual(p.snapshot()['records'],[])
                self.assertEqual(p.snapshot()['omitted_lines'],1)
                self.assertEqual(p.snapshot()['status'],'unknown')

    def test_wayland_126_clock_does_not_bypass_identity_direction_or_geometry_checks(self):
        for row in [line('wl_surface',900,'commit'),
                    line('xdg_surface',8,'configure','88',True),
                    line('wl_shm_pool',11,'create_buffer','new id wl_buffer#13, 0, 1280, 720, 1279, 0'),
                    line('wp_viewport',10,'set_source','NaN, 0, 10, 10')]:
            p,_=positive();p.feed(wayland_126_line(row))
            self.assertTrue(p.rejected)

    def test_wayland_126_opaque_private_arguments_remain_unexported_and_bounded(self):
        p,_=positive()
        for row in [line('xdg_toplevel',9,'set_title','"private transcript"'),
                    line('wl_registry',2,'global','17, "private-interface", 1',False)]:
            p.feed(wayland_126_line(row))
        projected=json.dumps(p.snapshot())
        for value in ['private transcript','private-interface','private-queue-label']:
            self.assertNotIn(value,projected)
        self.assertEqual(p.snapshot()['status'],'observed')
        p.feed(wayland_126_line(line('xdg_toplevel',9,'set_title','"'+('x'*p.MAX_LINE)+'"')))
        self.assertTrue(p.capped)

    def test_foreign_unknown_receiver_buffer_ids_duplicate_objects_serials_and_ack_rejected(self):
        rows=[line('wl_surface',900,'commit'),line('wl_surface',7,'attach','wl_buffer#900, 0, 0'),
              line('wl_compositor',3,'create_surface','new id wl_surface#7'),
              line('xdg_surface',8,'configure','77',False),line('xdg_surface',8,'ack_configure','78'),
              line('xdg_toplevel',9,'configure','1280, 720, "secret text"',False)]
        for row in rows:
            with self.subTest(row_hash=hashlib.sha256(row).hexdigest()):
                p,_=positive();p.feed(row);self.assertEqual(p.snapshot()['status'],'rejected')
                self.assertNotIn('secret text',json.dumps(p.snapshot()))

    def test_stride_pool_bounds_nonfinite_viewport_and_wrong_direction_rejected(self):
        for row in [line('wp_viewport',10,'set_source','NaN, 0, 10, 10'),
                    line('wp_viewport',10,'set_destination','-1, 720'),
                    line('wl_shm_pool',11,'create_buffer','new id wl_buffer#13, 0, 1280, 720, 1279, 0'),
                    line('wl_shm_pool',11,'create_buffer','new id wl_buffer#13, 0, 1280, 720, 5121, 0'),
                    line('xdg_surface',8,'configure','88',True)]:
            p,_=positive();p.feed(row);self.assertTrue(p.rejected)

    def test_unknown_strings_and_app_errors_never_exported(self):
        p,_=positive()
        for row in [b'password=top-secret transcript=private\n',line('xdg_toplevel',9,'set_title','"private transcript"'),
                    line('wl_registry',2,'global','17, "private-interface", 1',False),b'\xff\xfeprivate\n']:
            p.feed(row)
        payload=json.dumps(p.snapshot())
        for secret in ['top-secret','transcript','private-interface']:self.assertNotIn(secret,payload)
        self.assertEqual(p.snapshot()['status'],'observed')

    def test_lines_bytes_records_and_surface_counts_bounded(self):
        p,_=positive();p.feed(b'x'*(p.MAX_LINE+1));self.assertTrue(p.capped)
        p,_=positive();p.MAX_INPUT=1;p.feed(b'x\n');self.assertTrue(p.capped)
        p,_=positive();p.MAX_RECORDS=len(p.records);p.feed(line('wl_surface',7,'commit'));self.assertTrue(p.capped)

    def test_opaque_registry_bind_objects_also_obey_object_count_cap(self):
        p,_=positive()
        for object_id in range(100,1200):
            p.feed(line('wl_registry',2,'bind',f'9, "unexported_unknown_interface", 1, new id [unknown]#{object_id}'))
        self.assertTrue(p.capped);self.assertLessEqual(len(p.objects),1024)
        self.assertNotIn('unexported_unknown_interface',json.dumps(p.snapshot()))

    def test_subsurface_root_chain_and_cycles_rejected_without_video_guess(self):
        p,_=positive()
        for row in [line('wl_registry',2,'bind','8, "wl_subcompositor", 1, new id [unknown]#20'),
                    line('wl_compositor',3,'create_surface','new id wl_surface#21'),
                    line('wl_subcompositor',20,'get_subsurface','new id wl_subsurface#22, wl_surface#21, wl_surface#7'),
                    line('wl_subsurface',22,'set_position','0, 715')]:p.feed(row)
        self.assertEqual(p.snapshot()['structural_surfaces'][1]['position'],[0,715])
        self.assertFalse(p.snapshot()['video_surface_identified'])
        p.feed(line('wl_subcompositor',20,'get_subsurface','new id wl_subsurface#23, wl_surface#7, wl_surface#21'))
        self.assertTrue(p.rejected)

    @unittest.skipUnless(ctypes.util.find_library('wayland-client'),'host libwayland-client absent')
    def test_real_local_libwayland_client_serialized_registry_surface_and_shm_records(self):
        # A local socketpair and host libwayland marshaller only: no compositor,
        # guest, VM, audio, renderer, external socket, target ELF or network.
        code='''import ctypes,ctypes.util,socket
c=ctypes.CDLL(ctypes.util.find_library("wayland-client"))
c.wl_display_connect_to_fd.argtypes=[ctypes.c_int];c.wl_display_connect_to_fd.restype=ctypes.c_void_p
c.wl_proxy_marshal_flags.restype=ctypes.c_void_p
c.wl_proxy_marshal_flags.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32]
c.wl_proxy_get_version.argtypes=[ctypes.c_void_p];c.wl_proxy_get_version.restype=ctypes.c_uint32
c.wl_display_disconnect.argtypes=[ctypes.c_void_p]
def interface(name):return ctypes.addressof((ctypes.c_byte*1).in_dll(c,name+"_interface"))
def request(obj,op,name,*args):return c.wl_proxy_marshal_flags(obj,op,interface(name),1,0,*args)
a,b=socket.socketpair();display=c.wl_display_connect_to_fd(a.detach())
registry=request(display,1,"wl_registry",ctypes.c_void_p(0))
comp=request(registry,0,"wl_compositor",ctypes.c_uint(1),ctypes.c_char_p(b"wl_compositor"),ctypes.c_uint(1),ctypes.c_void_p(0))
surface=request(comp,0,"wl_surface",ctypes.c_void_p(0))
shm=request(registry,0,"wl_shm",ctypes.c_uint(2),ctypes.c_char_p(b"wl_shm"),ctypes.c_uint(1),ctypes.c_void_p(0))
pool=request(shm,0,"wl_shm_pool",ctypes.c_void_p(0),ctypes.c_int(1),ctypes.c_int(4096))
buffer=request(pool,0,"wl_buffer",ctypes.c_void_p(0),ctypes.c_int(0),ctypes.c_int(16),ctypes.c_int(16),ctypes.c_int(64),ctypes.c_uint(0))
c.wl_display_disconnect(display);b.close()
'''
        env=os.environ.copy();env['WAYLAND_DEBUG']='client'
        result=subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,timeout=5)
        self.assertEqual(result.returncode,0)
        p=N.NativeProtocolProjection()
        for row in result.stderr.splitlines(keepends=True):p.feed(row)
        self.assertFalse(p.rejected);self.assertEqual(len(p.surfaces),1);self.assertEqual(len(p.buffers),1)
        self.assertEqual(next(iter(p.buffers.values()))['stride'],64)


class DrainAndExportControls(unittest.TestCase):
    def test_only_owned_static_player_env_is_instrumented_and_raw_stderr_is_separate(self):
        with tempfile.TemporaryDirectory() as t:
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=Path(t);smoke.gui_v6=True
            smoke.prefix=['runuser','-u','fixture','--','env'];smoke.launches=[];smoke.steps=[]
            child=Mock();drain=Mock();argv=['/usr/bin/celluloid','--no-existing-session','--new-window','fixture.mkv']
            order=[]
            drain.start.side_effect=lambda reader:order.append('drain-start')
            with patch.object(N,'NativeProtocolDrain',return_value=drain),patch.object(N.subprocess,'Popen',return_value=child) as popen:
                popen.side_effect=lambda *a,**kw:(order.append('app-launch') or child)
                smoke.launch_protocol_player(argv)
            self.assertEqual(popen.call_args.args[0],smoke.prefix+['WAYLAND_DEBUG=client']+argv)
            writer=popen.call_args.kwargs['stderr'];self.assertIs(type(writer),int)
            with self.assertRaises(OSError):os.fstat(writer)
            self.assertEqual(order,['drain-start','app-launch'])
            reader=drain.start.call_args.args[0];self.assertTrue(stat.S_ISFIFO(os.fstat(reader.fileno()).st_mode));reader.close()
            self.assertEqual(smoke.steps[0]['argv'],argv)
            with self.assertRaises(RuntimeError):smoke.launch_protocol_player(['/usr/bin/other'])

    def test_optional_thread_start_failure_reaches_original_visual_oracle_and_cleans_owned_fds(self):
        # Actual gate/visual/launch/drain methods; only app/process and GUI fixtures mocked.
        with tempfile.TemporaryDirectory() as t:
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=Path(t);smoke.gui_v6=True;smoke.uid=os.getuid();smoke.stage='live'
            smoke.prefix=['runuser','-u','fixture','--','env'];smoke.launches=[];smoke.steps=[];smoke.gates=[]
            fixture=smoke.root/'visual-reference.mkv';fixture.write_bytes(b'host-only')
            expected=smoke.root/'visual-reference-frame.rgb';expected.write_bytes(N.visual_reference_frame())
            proof=dict(pid=100,client_id='7');client=dict(id=7,pid=100,x=0,y=0,width=160,height=120,
                is_focused=True,is_visible=True,is_fullscreen=True,monitor='fixture')
            monitor=dict(name='fixture',x=0,y=0,width=160,height=120,scale=1,is_hdr=False)
            smoke.visual_fixture=Mock(return_value=(fixture,expected,'a'*64))
            smoke.fresh_window=Mock(side_effect=lambda start,*args:(start() or proof))
            smoke.alive=Mock(return_value=client);smoke.wait=Mock();smoke.trace=Mock();smoke.diagnostic=Mock(return_value=None)
            smoke.player_fullscreen=Mock();smoke.fullscreen_capture_pair=Mock()
            commands=[];captures=[];closed=[];original_close=os.close;original_pipe=os.pipe;original_drain=N.NativeProtocolDrain
            def command(argv):
                commands.append(argv)
                if argv[:3]==['mmsg','get','all-monitors']:return (0,json.dumps(dict(monitors=[monitor])),'')
                if argv[0]=='grim':Path(argv[-1]).write_bytes(b'\x89PNG\r\n\x1a\n'+b'\0\0\0\rIHDR'+struct.pack('>II',160,120))
                if argv[0]=='ffmpeg':Path(argv[-1]).write_bytes(b'\0'*(160*120*3))
                return (0,'{"success":true}','')
            def pipe():
                pair=original_pipe();captures.extend(pair);return pair
            def drain_factory():
                drain=original_drain();captures.append(drain.raw_fd);return drain
            def close(fd):closed.append(fd);original_close(fd)
            smoke.cmd=Mock(side_effect=command)
            def prop(path,key,pid,uid):return {'video-params':{'w':160,'h':120},'path':str(fixture),
                    'pause':False,'current-vo':'libmpv','time-pos':.5}[key]
            with patch.object(N,'NativeProtocolDrain',side_effect=drain_factory) as factory,\
                 patch.object(N.os,'pipe',side_effect=pipe),patch.object(N.os,'close',side_effect=close),\
                 patch.object(N.threading.Thread,'start',side_effect=RuntimeError('private optional setup text')),\
                 patch.object(N.subprocess,'Popen',return_value=Mock()) as popen,\
                 patch.object(N,'mpv_property',side_effect=prop),patch.object(N.time,'sleep') as sleep:
                self.assertIsNone(smoke.gate('open-codec-content-and-player-state',smoke.visual_media))
            self.assertEqual(factory.call_count,1);self.assertEqual(popen.call_count,1)
            self.assertNotIn('WAYLAND_DEBUG=client',popen.call_args.args[0])
            sleep.assert_called_once_with(.5)
            self.assertIn('actual static visual fixture content unmatched',smoke.gates[-1]['detail'])
            self.assertNotIn('private optional',json.dumps(smoke.gates))
            self.assertEqual(json.loads((smoke.root/'visual-oracle.json').read_bytes())['oracle']['status'],'unmatched')
            self.assertTrue((smoke.root/'celluloid-reference.png').is_file())
            self.assertEqual(json.loads((smoke.root/'0-native-protocol-viewport.json').read_bytes())['protocol']['status'],'unknown')
            for fd in captures:
                with self.assertRaises(OSError):os.fstat(fd)
            self.assertEqual(closed.count(captures[0]),1)
            self.assertEqual(closed.count(captures[2]),1)

    def test_start_failure_cleanup_is_idempotent_even_after_fd_reuse(self):
        read,write=os.pipe();reader=os.fdopen(read,'rb',buffering=0);drain=N.NativeProtocolDrain();raw=drain.raw_fd
        try:
            with patch.object(N.threading.Thread,'start',side_effect=RuntimeError('private exception')):
                with self.assertRaisesRegex(RuntimeError,'^owned protocol drainage unavailable$'):drain.start(reader)
            self.assertIsNone(drain.thread);self.assertIsNone(drain.raw_fd);self.assertTrue(reader.closed)
            with self.assertRaises(OSError):os.fstat(raw)
            replacement=os.open('/dev/null',os.O_RDONLY)
            try:
                drain.finish();drain.finish();self.assertTrue(stat.S_ISCHR(os.fstat(replacement).st_mode))
            finally:os.close(replacement)
        finally:os.close(write)

    def test_prestarted_writer_handoff_owns_actual_host_fd2_and_parent_closes_writer(self):
        # Actual host Python only; no Celluloid/guest/target ELF execution.
        with tempfile.TemporaryDirectory() as t:
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=Path(t);smoke.gui_v6=True;smoke.uid=os.getuid()
            smoke.prefix=['runuser','-u','fixture','--','env'];smoke.launches=[];smoke.steps=[]
            actual_popen=subprocess.Popen;writer=[];started=[];actual_start=N.NativeProtocolDrain.start
            def start(drain,reader):actual_start(drain,reader);started.append(drain)
            def popen(argv,**kw):
                self.assertEqual(len(started),1);self.assertTrue(started[0].thread.is_alive())
                writer.append(kw['stderr']);self.assertFalse(os.get_inheritable(kw['stderr']))
                return actual_popen([sys.executable,'-c','import sys,time;print("host fixture",file=sys.stderr,flush=True);time.sleep(2)'],**kw)
            with patch.object(N.NativeProtocolDrain,'start',start),patch.object(N.subprocess,'Popen',side_effect=popen):
                smoke.launch_protocol_player(['/usr/bin/celluloid','--no-existing-session','fixture.mkv'])
            child=smoke.launches[0];drain=smoke.native_protocol_drain
            try:
                with self.assertRaises(OSError):os.fstat(writer[0])
                proof=N.identity(child.pid,os.getuid());proof.update(executable_sha256=N.digest(proof['executable']),client_id='7')
                self.assertTrue(drain.bind(proof,os.getuid()))
            finally:
                child.terminate();child.wait(3);drain.finish()
            self.assertFalse(drain.thread.is_alive());self.assertIsNone(drain.raw_fd)

    def test_pipe_setup_falls_back_and_original_popen_failure_closes_prestarted_capture(self):
        with tempfile.TemporaryDirectory() as t:
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=Path(t);smoke.gui_v6=True
            smoke.prefix=['runuser','-u','fixture','--','env'];smoke.launches=[];smoke.steps=[]
            original=N.NativeProtocolDrain;captures=[]
            def factory():
                drain=original();captures.append(drain);return drain
            argv=['/usr/bin/celluloid','--no-existing-session','fixture.mkv']
            with patch.object(N,'NativeProtocolDrain',side_effect=factory),\
                 patch.object(N.os,'pipe',side_effect=OSError('host-only setup fault')),\
                 patch.object(N.subprocess,'Popen',return_value=Mock()) as popen:
                smoke.launch_protocol_player(argv)
            self.assertEqual(popen.call_args.args[0],smoke.prefix+argv)
            self.assertIsNone(captures[0].raw_fd)
            with patch.object(N,'NativeProtocolDrain',side_effect=factory),\
                 patch.object(N.subprocess,'Popen',side_effect=OSError('original process launch fault')):
                with self.assertRaisesRegex(OSError,'^original process launch fault$'):
                    smoke.launch_protocol_player(argv)
            self.assertFalse(captures[1].thread.is_alive());self.assertIsNone(captures[1].raw_fd)
            self.assertTrue(captures[1].stream.closed)

    def test_instrumented_primary_black_failure_keeps_capture_wait_commands_and_final_gate(self):
        # Execute actual visual_media with closed host fixtures. No renderer/VM.
        with tempfile.TemporaryDirectory() as t:
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=Path(t);smoke.gui_v6=True;smoke.uid=os.getuid();smoke.stage='live'
            fixture=smoke.root/'visual-reference.mkv';fixture.write_bytes(b'host-only')
            expected=smoke.root/'visual-reference-frame.rgb';expected.write_bytes(N.visual_reference_frame())
            proof=dict(pid=100,client_id='7');client=dict(id=7,pid=100,x=0,y=0,width=160,height=120,
                is_focused=True,is_visible=True,is_fullscreen=True,monitor='fixture')
            monitor=dict(name='fixture',x=0,y=0,width=160,height=120,scale=1,is_hdr=False)
            smoke.visual_fixture=Mock(return_value=(fixture,expected,'a'*64));smoke.fresh_window=Mock(return_value=proof)
            smoke.alive=Mock(return_value=client);smoke.wait=Mock();smoke.trace=Mock()
            smoke.player_fullscreen=Mock();smoke.fullscreen_capture_pair=Mock();smoke.native_protocol_drain=Mock()
            smoke.native_protocol_drain.snapshot.return_value=dict(status='unknown',ownership_verified=False)
            commands=[]
            def command(argv):
                commands.append(argv)
                if argv[:3]==['mmsg','get','all-monitors']:return (0,json.dumps(dict(monitors=[monitor])),'')
                if argv[0]=='grim':Path(argv[-1]).write_bytes(b'\x89PNG\r\n\x1a\n'+b'\0\0\0\rIHDR'+struct.pack('>II',160,120))
                if argv[0]=='ffmpeg':Path(argv[-1]).write_bytes(b'\0'*(160*120*3))
                return (0,'{"success":true}','')
            smoke.cmd=Mock(side_effect=command)
            def prop(path,key,pid,uid):return {'video-params':{'w':160,'h':120},'path':str(fixture),
                    'pause':False,'current-vo':'libmpv','time-pos':.5}[key]
            with patch.object(N,'mpv_property',side_effect=prop),patch.object(N.time,'sleep') as sleep:
                with self.assertRaisesRegex(RuntimeError,'actual static visual fixture content unmatched'):
                    smoke.visual_media()
            sleep.assert_called_once_with(.5)
            self.assertEqual(next(c for c in commands if c[0]=='grim')[:3],['grim','-o','fixture'])
            self.assertEqual(smoke.player_fullscreen.call_args_list[0].args,(proof,True))
            self.assertEqual(smoke.player_fullscreen.call_args_list[-1].args,(proof,False))
            oracle=json.loads((smoke.root/'visual-oracle.json').read_bytes());self.assertEqual(oracle['oracle']['status'],'unmatched')
            diagnostic=json.loads((smoke.root/'0-native-protocol-viewport.json').read_bytes())
            self.assertEqual(diagnostic['primary_screenshot_sha256'],oracle['screenshot']['sha256'])
            self.assertFalse(diagnostic['release_acceptance']);self.assertEqual(diagnostic['protocol']['status'],'unknown')

    def test_private_exclusive_regular_mode_and_continuing_bounded_pipe_drain(self):
        read,write=os.pipe();drain=N.NativeProtocolDrain();drain.RAW_CAP=16
        drain.start(os.fdopen(read,'rb',buffering=0))
        os.write(write,b'private transcript that must never export\n'*100);os.close(write)
        drain.thread.join(2)
        self.assertFalse(drain.thread.is_alive());self.assertTrue(drain.eof)
        self.assertEqual(drain.raw_path.stat().st_size,16);self.assertEqual(stat.S_IMODE(drain.raw_path.stat().st_mode),0o600)
        self.assertNotIn('private transcript',json.dumps(drain.projection.snapshot()))

    def test_private_capture_existing_symlink_fifo_and_regular_file_are_refused(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);target=root/'untouched';target.write_text('sentinel')
            for kind in ('symlink','fifo','file'):
                p=root/'stderr.private'
                if kind=='symlink':p.symlink_to(target)
                elif kind=='fifo':os.mkfifo(p)
                else:p.write_text('sentinel')
                with patch.object(N.tempfile,'mkdtemp',return_value=str(root)),self.assertRaises(OSError):N.NativeProtocolDrain()
                p.unlink()
            self.assertEqual(target.read_text(),'sentinel')
            alias=root/'alias';alias.symlink_to(root,target_is_directory=True)
            with patch.object(N.tempfile,'mkdtemp',return_value=str(alias)),self.assertRaises(OSError):N.NativeProtocolDrain()

    def test_partial_final_line_is_explicit_unknown_and_cannot_become_record(self):
        read,write=os.pipe();drain=N.NativeProtocolDrain();drain.start(os.fdopen(read,'rb',buffering=0))
        os.write(write,b'[ 1.1] -> wl_display#1.get_registry(');os.close(write);drain.thread.join(2)
        result=drain.snapshot({},os.getuid());self.assertTrue(result['partial_line']);self.assertEqual(result['status'],'unknown')
        self.assertEqual(result['records'],[])

    def test_wrong_proc_identity_or_pipe_and_missing_owner_are_unknown(self):
        read,write=os.pipe();drain=N.NativeProtocolDrain();drain.start(os.fdopen(read,'rb',buffering=0))
        proof=dict(pid=os.getpid(),start_ticks=1,executable='/wrong',executable_sha256='a'*64,client_id='7')
        self.assertFalse(drain.bind(proof,os.getuid()));self.assertFalse(drain.snapshot(proof,os.getuid())['ownership_verified'])
        os.close(write);drain.thread.join(2)

    def test_actual_host_process_fd2_pipe_binding_and_recycled_identity_rejection(self):
        # Host Python fixture only; this is not the target Celluloid or guest ELF.
        child=subprocess.Popen([sys.executable,'-c','import sys,time;print("host fixture",file=sys.stderr,flush=True);time.sleep(2)'],stderr=subprocess.PIPE)
        drain=N.NativeProtocolDrain();drain.start(child.stderr)
        proof=N.identity(child.pid,os.getuid());proof.update(executable_sha256=N.digest(proof['executable']),client_id='7')
        try:
            self.assertTrue(drain.bind(proof,os.getuid()))
            bad=dict(proof,start_ticks=proof['start_ticks']+1);self.assertFalse(drain.bind(bad,os.getuid()))
            bad=dict(proof,executable_sha256='0'*64);self.assertFalse(drain.bind(bad,os.getuid()))
            result=drain.snapshot(proof,os.getuid());self.assertTrue(result['ownership_verified'])
            self.assertFalse(result['protocol_sender_authenticated']);self.assertFalse(result['exclusive_stderr_writer_proven'])
        finally:
            child.terminate();child.wait(3);drain.thread.join(2)

    def test_pipe_time_cap_is_incomplete_and_short_private_writes_are_completed(self):
        read,write=os.pipe();drain=N.NativeProtocolDrain()
        with patch.object(N.time,'monotonic',side_effect=[0,301]):
            drain.start(os.fdopen(read,'rb',buffering=0));drain.thread.join(2)
        self.assertTrue(drain.timed_out);os.close(write)
        read,write=os.pipe();drain=N.NativeProtocolDrain();original=os.write
        with patch.object(N.os,'write',side_effect=lambda fd,data:original(fd,data[:2])):
            drain.start(os.fdopen(read,'rb',buffering=0));original(write,b'abcdef\n');os.close(write);drain.thread.join(2)
        self.assertEqual(drain.raw_path.read_bytes(),b'abcdef\n')

    def test_typed_projection_precedes_original_failure_and_private_raw_is_not_export_suffix(self):
        with tempfile.TemporaryDirectory() as t:
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=Path(t);smoke.uid=os.getuid();smoke.stage='live'
            smoke.alive=Mock(return_value=dict(id=7,pid=100,x=0,y=0,width=1280,height=720,is_fullscreen=True))
            smoke.native_protocol_drain=Mock();smoke.native_protocol_drain.snapshot.return_value=positive()[0].snapshot()
            smoke.native_protocol_diagnostic(dict(pid=100,client_id='7'),dict(**{'video-params':dict(w=160,h=120)}),dict(sha256='a'*64),smoke.alive())
            path=smoke.root/'0-native-protocol-viewport.json';value=json.loads(path.read_bytes())
            self.assertFalse(value['release_acceptance']);self.assertFalse(value['rendering_cause_proven'])
            self.assertEqual(value['decoded_video_dimensions'],dict(w=160,h=120))
            self.assertIsNone(value['video_widget_and_framebuffer_dimensions'])
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
            self.assertNotIn('.private',{'.json','.png','.log','.txt','.tsv','.rgb'})
            source=(HERE/'native_smoke.py').read_text()
            self.assertLess(source.index('self.native_protocol_diagnostic(player,state,screenshot,client)'),source.index("require(info['oracle']['status']=='matched'"))

    def test_export_existing_symlink_fifo_file_and_bad_strings_never_overwritten(self):
        with tempfile.TemporaryDirectory() as t:
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=Path(t);smoke.uid=os.getuid();smoke.stage='live'
            smoke.alive=Mock(side_effect=RuntimeError('private password transcript'))
            target=smoke.root/'sentinel';target.write_text('untouched');p=smoke.root/'0-native-protocol-viewport.json'
            for kind in ('symlink','fifo','file'):
                if kind=='symlink':p.symlink_to(target)
                elif kind=='fifo':os.mkfifo(p)
                else:p.write_text('untouched')
                smoke.native_protocol_diagnostic({}, {}, dict(sha256='a'*64),{});p.unlink()
            self.assertEqual(target.read_text(),'untouched')
            smoke.native_protocol_diagnostic({}, {}, dict(sha256='private transcript'),{})
            value=p.read_text();self.assertNotIn('private',value);self.assertNotIn('password',value)
            p.unlink();smoke.native_protocol_drain=Mock()
            smoke.native_protocol_drain.snapshot.side_effect=RuntimeError('private password transcript')
            smoke.native_protocol_diagnostic(dict(pid=100,client_id='7'),{},dict(sha256='a'*64),
                    dict(id=7,pid=100,x=0,y=0,width=1280,height=720,is_fullscreen=True))
            value=p.read_text();self.assertNotIn('private',value);self.assertNotIn('password',value)


if __name__=='__main__':unittest.main()
