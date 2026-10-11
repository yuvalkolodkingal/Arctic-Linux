"""Controlled render diagnostics: local source/pipe/host fixtures, never a VM."""
import ast
import copy
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import socket
import struct
import subprocess
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import zlib

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('renderer_trials_tested',HERE/'native_smoke.py')
N=importlib.util.module_from_spec(spec);spec.loader.exec_module(N)
BASE_NATIVE_SHA='a9bed2b6f2cb71ffe944c60d0527c8bd14180a98cdccd31961574b911dfc82f9'


def renderer_line(name=b'GskGLRenderer',surface=b'GdkWaylandToplevel'):
    # GTK 4.22.5 gsk/gskrenderer.c: successful realization calls this exact
    # gdk_debug_message format. gdkdebugprivate.h vfprintf + newline is used
    # without a clock, process prefix, color sequence or arbitrary log suffix.
    buffer=ctypes.create_string_buffer(256)
    snprintf=ctypes.CDLL(None).snprintf;snprintf.restype=ctypes.c_int
    count=snprintf(buffer,ctypes.c_size_t(256),b"Using renderer '%s' for surface '%s'\n",name,surface)
    if not 0<count<256:raise AssertionError('renderer literal fixture bound')
    return buffer.raw[:count]


class RendererControls(unittest.TestCase):
    def test_official_formatter_known_success_types_and_unknown_messages(self):
        for name,expected in ((b'GskGLRenderer','gl'),(b'GskVulkanRenderer','vulkan'),(b'GskCairoRenderer','cairo')):
            p=N.NativeRendererProjection();p.feed(renderer_line(name))
            self.assertEqual(p.snapshot()['renderer'],expected)
            self.assertEqual(p.snapshot()['status'],'reported-realized')
            self.assertFalse(p.snapshot()['video_widget_or_framebuffer_attested'])
        for raw in (b'GSK_RENDERER=gl\n',renderer_line(b'private-renderer'),renderer_line(surface=b'GdkWaylandPopup'),
                    b'private-path: '+renderer_line(),renderer_line()+b'private-text',
                    renderer_line().replace(b'\n',b'\r\n'),b'\x1b[31m'+renderer_line(),
                    renderer_line().replace(b'Using',b'Failed to realize'),b'private-canary\n'):
            p=N.NativeRendererProjection();p.feed(raw)
            self.assertEqual(p.snapshot()['status'],'unknown')
            self.assertNotIn('private',json.dumps(p.snapshot()))

    def test_renderer_ambiguity_and_resource_caps_never_attest(self):
        p=N.NativeRendererProjection();p.feed(renderer_line());p.feed(renderer_line(b'GskVulkanRenderer'))
        self.assertIsNone(p.snapshot()['renderer'])
        p=N.NativeRendererProjection()
        for _ in range(17):p.feed(renderer_line())
        self.assertTrue(p.snapshot()['capped']);self.assertIsNone(p.snapshot()['renderer'])
        p=N.NativeRendererProjection();p.feed(renderer_line());p.feed(b'x'*(p.MAX_BYTES+1))
        self.assertIsNone(p.snapshot()['renderer'])

    def test_real_bounded_pipe_rejects_unowned_renderer_projection(self):
        drain=N.NativeProtocolDrain(renderer=True);read,write=os.pipe()
        try:
            drain.start(os.fdopen(read,'rb',buffering=0));os.write(write,renderer_line());os.close(write);write=None
            end=time.monotonic()+2
            while not drain.eof and time.monotonic()<end:time.sleep(.01)
            self.assertTrue(drain.eof)
            with patch.object(drain,'bind',return_value=False):value=drain.snapshot({},1000)
            self.assertEqual(value['realized_renderer']['status'],'unknown')
            self.assertIsNone(value['realized_renderer']['renderer'])
            self.assertFalse(value['realized_renderer']['owned_stderr_binding_verified'])
            self.assertFalse(value['private_raw_exported'])
        finally:
            if write is not None:os.close(write)
            drain.finish();drain.raw_path.unlink();drain.raw_path.parent.rmdir()

    def test_primary_drain_schema_stays_identical_without_renderer_option(self):
        drain=N.NativeProtocolDrain()
        try:
            with patch.object(drain,'bind',return_value=False):value=drain.snapshot({},1000)
            self.assertNotIn('realized_renderer',value)
        finally:drain.finish();drain.raw_path.unlink();drain.raw_path.parent.rmdir()

    def test_launch_uses_supported_lowercase_gl_and_same_owned_pipe(self):
        for mode in ('default','gl'):
            with tempfile.TemporaryDirectory() as t:
                parent=Mock(root=Path(t),user=pwd.getpwuid(os.getuid()),uid=os.getuid(),stage='live',
                            prefix=['synthetic-prefix'],original_prefix=['synthetic-prefix'])
                trial=N.RendererTrialSmoke(parent,mode);fake=Mock()
                with patch.object(N,'NativeProtocolDrain',return_value=fake),patch.object(N.subprocess,'Popen',return_value=Mock()) as popen:
                    trial.launch_renderer(['/usr/bin/celluloid','--no-existing-session','fixture.mkv'])
                argv=popen.call_args.args[0]
                self.assertEqual(argv[:6],['synthetic-prefix','env','-u','GSK_RENDERER','GSK_DEBUG=renderer','WAYLAND_DEBUG=client'])
                self.assertEqual('GSK_RENDERER=gl' in argv,mode=='gl')
                self.assertNotIn('GSK_RENDERER=GL',argv)
                self.assertIs(popen.call_args.kwargs['stdout'],subprocess.DEVNULL)
                self.assertIs(type(popen.call_args.kwargs['stderr']),int)
                fake.start.assert_called_once()
                fake.start.call_args.args[0].close()

    def test_retirement_never_signals_wrong_start_identity_and_closes_pidfd(self):
        proof=dict(pid=71,start_ticks=100,executable='/usr/bin/celluloid',executable_sha256='a'*64)
        with (patch.object(N.os,'pidfd_open',return_value=9),patch.object(N.os,'close') as close,
              patch.object(N,'identity',return_value=dict(pid=71,start_ticks=101,executable='/usr/bin/celluloid')),
              patch.object(N.signal,'pidfd_send_signal') as signal):
            with self.assertRaises(RuntimeError):N.retire_renderer_player(proof,1000)
            signal.assert_not_called();close.assert_called_once_with(9)

    def test_error_codes_do_not_inspect_or_format_private_arguments(self):
        class PrivateError(RuntimeError):
            def __str__(self):raise AssertionError('private conversion')
        class PrivateValue:
            def __str__(self):raise AssertionError('private conversion')
            def __repr__(self):raise AssertionError('private conversion')
        for error in (RuntimeError('private-text'),RuntimeError(PrivateValue()),PrivateError('private-text')):
            self.assertIn(N.renderer_trial_error(error),('guard-error','other-error'))
            self.assertNotIn('private',N.renderer_trial_error(error))

    def test_actual_observe_path_uses_same_half_second_oracle_and_reports_fallback(self):
        for mode,pixels,renderer in (('default','palette','vulkan'),('gl','palette','gl'),('gl','black','vulkan')):
            with self.subTest(mode=mode,pixels=pixels,renderer=renderer),tempfile.TemporaryDirectory() as t:
                root=Path(t);parent=Mock(root=root,user=pwd.getpwuid(os.getuid()),uid=os.getuid(),stage='live',
                                     prefix=['synthetic-prefix'],original_prefix=['synthetic-prefix'])
                trial=N.RendererTrialSmoke(parent,mode)
                fixture=root/'same-fixture.mkv';fixture.write_bytes(b'fixed-public-source-fixture')
                expected=root/'expected.rgb';expected.write_bytes(N.visual_reference_frame())
                raw=expected.read_bytes() if pixels=='palette' else b'\0'*(160*120*3)
                player=dict(pid=4242,start_ticks=123,client_id='10',executable='/usr/bin/celluloid',executable_sha256='a'*64)
                client=dict(id=10,pid=4242,x=0,y=0,width=160,height=120,monitor='synthetic-monitor',
                            is_focused=True,is_visible=True,is_fullscreen=True)
                monitors=dict(monitors=[dict(name='synthetic-monitor',x=0,y=0,width=160,height=120,scale=1,is_hdr=False)])
                trial.fresh_window=Mock(return_value=player);trial.alive=Mock(return_value=client)
                trial.fullscreen=Mock();trial.hide_reference_controls=Mock(return_value=dict(after_visible=False,release_acceptance=False))
                trial.gtk_binding=Mock(return_value=dict(package='gtk4',version='4.22.5',mapped_library_sha256='b'*64))
                trial.native_protocol_drain=Mock(bind=Mock(return_value=True),snapshot=Mock(return_value=dict(
                    realized_renderer=dict(status='reported-realized',renderer=renderer,release_acceptance=False,
                                           owned_stderr_binding_verified=True,video_widget_or_framebuffer_attested=False))))
                def command(argv,**kwargs):
                    if argv[:3]==['mmsg','get','all-monitors']:return (0,json.dumps(monitors),'')
                    if argv[:2]==['mmsg','dispatch']:return (0,'{"success":true}','')
                    if argv[0]=='grim':
                        def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
                        scan=b''.join(b'\0'+raw[y*160*3:(y+1)*160*3] for y in range(120))
                        Path(argv[-1]).write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',160,120,8,2,0,0,0))
                                                  +chunk(b'IDAT',zlib.compress(scan))+chunk(b'IEND',b''))
                        return (0,'','')
                    if argv[0]=='ffmpeg':Path(argv[-1]).write_bytes(raw);return (0,'','')
                    raise AssertionError('unexpected synthetic host command')
                trial.cmd=Mock(side_effect=command)
                state={'path':str(fixture),'pause':False,'video-params':dict(w=160,h=120),'current-vo':'libmpv','time-pos':.7}
                endpoint=socket.socket(socket.AF_UNIX);endpoint.bind(str(trial.root/'player.sock'))
                try:
                    with patch.object(N,'mpv_property',side_effect=lambda path,key,pid,uid:state[key]),patch.object(N.time,'sleep') as sleep:
                        value=trial.observe(fixture,expected,'c'*64)
                    sleep.assert_called_once_with(.5)
                    self.assertEqual(value['oracle']['status'],'matched' if pixels=='palette' else 'unmatched')
                    self.assertEqual(value['status'],'observed')
                    self.assertEqual(value['requested_renderer_matched'],renderer=='gl' if mode=='gl' else None)
                    self.assertFalse(value['release_acceptance']);self.assertFalse(value['rendering_cause_proven'])
                    self.assertEqual(value['media']['fixture_sha256'],N.digest(fixture))
                    self.assertTrue(value['capture']['complete_owned_viewport'])
                    self.assertFalse(value['realized_renderer']['video_widget_or_framebuffer_attested'])
                    self.assertNotIn('synthetic-monitor',json.dumps(value))
                finally:endpoint.close()

    def test_actual_observe_fails_closed_before_pixels_when_owned_pipe_unproved(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);parent=Mock(root=root,user=pwd.getpwuid(os.getuid()),uid=os.getuid(),stage='live',
                                 prefix=['synthetic-prefix'],original_prefix=['synthetic-prefix'])
            trial=N.RendererTrialSmoke(parent,'gl');trial.fresh_window=Mock(return_value={})
            trial.native_protocol_drain=Mock(bind=Mock(return_value=False));trial.cmd=Mock()
            value=trial.observe(root/'fixture',root/'expected','a'*64)
            self.assertEqual(value['status'],'unknown');self.assertEqual(value['error'],'guard-error')
            self.assertNotIn('capture',value);self.assertNotIn('oracle',value)
            trial.cmd.assert_not_called()

    def test_successful_trials_cannot_rewrite_primary_failure_or_gate(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);fixture=root/'fixture.mkv';fixture.write_bytes(b'fixed-public-fixture')
            expected=root/'expected.rgb';expected.write_bytes(N.visual_reference_frame())
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=root;smoke.uid=os.getuid();smoke.stage='live'
            smoke.owned=[dict(executable='/usr/bin/celluloid')];smoke.launches=[];smoke.finish_native_protocol=Mock()
            smoke.gates=[dict(check='open-codec-content-and-player-state',status='failed',detail='original primary failure')]
            primary=dict(oracle=dict(status='unmatched'),screenshot=dict(sha256='a'*64),
                         fixture_sha256=N.digest(fixture),expected_rgb_sha256=N.digest(expected))
            before=copy.deepcopy(smoke.gates)
            trials=[Mock(owned=[],launches=[],observe=Mock(return_value=dict(intervention=m,status='observed',
                       oracle=dict(status='matched'),release_acceptance=False))) for m in ('default','gl')]
            with patch.object(N,'RendererTrialSmoke',side_effect=trials),patch.object(N,'retire_renderer_player'):
                smoke.controlled_renderer_trials(fixture,expected,'b'*64,primary)
            value=json.loads((root/'0-controlled-renderer-trials.json').read_bytes())
            self.assertEqual([r['intervention'] for r in value['trials']],['default','gl'])
            self.assertEqual(smoke.gates,before);self.assertEqual(primary['oracle']['status'],'unmatched')
            self.assertTrue(value['primary_failure_preserved']);self.assertFalse(value['release_acceptance'])
            self.assertFalse(value['rendering_cause_proven'])
            self.assertTrue(value['controls']['preceding_primary_and_default_warm_cache_confound'])

    def test_trial_failure_still_attempts_second_and_fixed_error_only(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);fixture=root/'fixture';fixture.write_bytes(b'fixed');expected=root/'rgb';expected.write_bytes(b'fixed')
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=root;smoke.uid=os.getuid();smoke.stage='live'
            smoke.owned=[dict(executable='/usr/bin/celluloid')];smoke.launches=[];smoke.finish_native_protocol=Mock()
            first=Mock(owned=[],launches=[],observe=Mock(side_effect=RuntimeError('private-text-and-path')))
            second=Mock(owned=[],launches=[],observe=Mock(return_value=dict(intervention='gl',status='observed',release_acceptance=False)))
            primary=dict(oracle=dict(status='unmatched'),screenshot=dict(sha256='a'*64),fixture_sha256=N.digest(fixture),expected_rgb_sha256=N.digest(expected))
            with patch.object(N,'RendererTrialSmoke',side_effect=[first,second]),patch.object(N,'retire_renderer_player'):
                smoke.controlled_renderer_trials(fixture,expected,'b'*64,primary)
            value=(root/'0-controlled-renderer-trials.json').read_text()
            second.observe.assert_called_once();self.assertNotIn('private-text',value)
            self.assertEqual(json.loads(value)['trials'][0]['error'],'guard-error')

    def test_receipt_never_follows_symlink_or_overwrites_existing_file(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);target=root/'sentinel';target.write_text('unchanged')
            path=root/'0-controlled-renderer-trials.json';path.symlink_to(target)
            with self.assertRaises(OSError):N.write_renderer_receipt(root,os.getuid(),{})
            self.assertEqual(target.read_text(),'unchanged')
            path.unlink();path.write_text('unchanged')
            with self.assertRaises(OSError):N.write_renderer_receipt(root,os.getuid(),{})
            self.assertEqual(path.read_text(),'unchanged')

    def test_full_source_rollback_preserves_every_primary_function_and_bound(self):
        new=(HERE/'native_smoke.py').read_text()
        from test_native_capture_controls import restore_capture_source
        new=restore_capture_source(new)
        # Remove the complete new top-level diagnostic block and one new class.
        new=new[:new.index('# BEGIN CONTROLLED_RENDERER_TRIALS\n')]+new[new.index('# END CONTROLLED_RENDERER_TRIALS\n')+len('# END CONTROLLED_RENDERER_TRIALS\n\n\n'):]
        start=new.index('class NativeRendererProjection:');end=new.index('class NativeProtocolDrain:',start);new=new[:start]+new[end:]
        start=new.index('    def controlled_renderer_trials(');end=new.index('    def setup(',start);new=new[:start]+new[end:]
        new=new.replace('    def __init__(self,renderer=False):\n','    def __init__(self):\n')
        new=new.replace('        self.renderer=NativeRendererProjection() if renderer is True else None\n','')
        new=new.replace('                            if self.renderer is not None: self.renderer.feed(line+b\'\\n\')\n','')
        start=new.index('        if self.renderer is not None:\n            with self.lock: realized=');end=new.index('        return value\n',start);new=new[:start]+new[end:]
        new=new.replace("        if getattr(self,'gui_v6',False) and info['oracle']['status']=='unmatched':\n            self.controlled_renderer_trials(fixture,expected,source_sha,info)\n",'')
        self.assertEqual(hashlib.sha256(new.encode()).hexdigest(),BASE_NATIVE_SHA)
        ast.parse(new)


if __name__=='__main__':unittest.main()
