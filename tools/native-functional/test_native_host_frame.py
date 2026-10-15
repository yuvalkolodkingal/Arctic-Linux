"""Failure-only guest request and native host-frame controller controls."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

HERE=Path(__file__).resolve().parent

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

N=load('native_host_frame_guest',HERE/'guest-check-native-v6.py')
P=load('native_host_frame_controller',HERE/'native-physical-controller.py')


def restore_host_frame_controller(source):
    """Reverse the native-only controller integration to its exact parent bytes."""
    replacements=((
        '"""One-use physical controls and failure-only Native frame observation."""\n'
        'import hashlib,importlib.util,io,json,os,re,stat,tempfile,time\n',
        '"""One-use physical PCManFM controls; no AT-SPI/focus/delivery fallback."""\n'
        'import hashlib,json,re,time\n'),
        ("HOST_FRAME_PREFIX='ARCTIC-NATIVE-HOST-FRAME-REQUEST '\n",''),
        ('  self.used={};self.started=clock();self.host_frame=HostFrameController(vm,out,stage)\n',
         '  self.used={};self.started=clock()\n'),
        ('  self.host_frame.poll(serial)\n',''))
    for current,previous in replacements:
        if source.count(current)!=1:raise AssertionError('Host frame controller inverse differs')
        source=source.replace(current,previous,1)
    begin='# BEGIN HOST_FRAME_CONTROLLER\n';end='# END HOST_FRAME_CONTROLLER\n'
    if source.count(begin)!=1 or source.count(end)!=1:raise AssertionError('Host controller block inverse differs')
    first=source.index(begin);last=source.index(end,first)+len(end)
    return source[:first]+source[last:]


class GuestRequestControls(unittest.TestCase):
    def test_capture_order_is_guest_oracle_then_host_same_frame_then_fullscreen_exit(self):
        for name in ('guest-check-native-v6.py',):
            with self.subTest(name=name):
                source=(HERE/name).read_text()
                primary=source.rindex("info['oracle']=oracle")
                protocol=source.rindex('            self.native_protocol_diagnostic(player,state,screenshot,client)')
                host=source.rindex('            self.host_frame_diagnostic(player,expected,info)')
                fullscreen_exit=source.rindex('            self.player_fullscreen(player,False)')
                failure=source.rindex("        require(info['oracle']['status']=='matched',")
                self.assertLess(primary,protocol);self.assertLess(protocol,host)
                self.assertLess(host,fullscreen_exit);self.assertLess(fullscreen_exit,failure)

    def test_failed_primary_requests_held_frame_and_process_bound_offload_readback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);config=root/'config';config.mkdir(mode=0o700)
            expected=root/'expected.rgb';expected.write_bytes(N.visual_reference_frame())
            environment=dict(os.environ,GSETTINGS_BACKEND='keyfile',XDG_CONFIG_HOME=str(config))
            child=subprocess.Popen(['/bin/sleep','30'],env=environment)
            try:
                smoke=N.Smoke.__new__(N.Smoke);smoke.root=root;smoke.uid=os.getuid();smoke.stage='installed'
                smoke.prefix=['XDG_CONFIG_HOME='+str(config)];smoke.original_prefix=list(smoke.prefix)
                player=dict(client_id='7',pid=child.pid,start_ticks=1,executable='/usr/bin/celluloid',
                    executable_sha256='1'*64,is_xwayland=False)
                client=dict(id=7,pid=child.pid,monitor='Virtual-1',is_visible=True,is_focused=True,
                    is_fullscreen=True,x=0,y=0,width=1280,height=720)
                monitor=dict(name='Virtual-1',x=0,y=0,width=1280,height=720,scale=1,is_hdr=False)
                primary=dict(screenshot=dict(sha256='a'*64),oracle=dict(status='unmatched'),
                    playback_clock=dict(capture_paused=True,paused_seconds=.8,settled_seconds=.8),
                    client_after=copy.deepcopy(client),client_pixel_crop=dict(x=0,y=0,width=1280,height=720),
                    expected_rgb_sha256=N.digest(expected))
                smoke.alive=Mock(return_value=client)
                def command(argv,**kwargs):
                    if argv==['mmsg','get','all-monitors']:
                        return (0,json.dumps(dict(monitors=[monitor])),'')
                    self.assertEqual(argv[-3:],['get','io.github.celluloid-player.Celluloid','graphics-offload-enable'])
                    self.assertTrue(kwargs.get('original'));return (0,'false','')
                smoke.cmd=Mock(side_effect=command)
                with patch.object(N,'mpv_property',side_effect=[True,.8]),patch.object(N.time,'sleep') as sleep, \
                        patch('builtins.print') as output:
                    smoke.host_frame_diagnostic(player,expected,primary)
                receipt=json.loads((root/'0-host-frame-request.json').read_text());request=receipt['request']
                self.assertEqual(receipt['status'],'request-held');self.assertEqual(request['hold_seconds'],20)
                self.assertFalse(request['graphics_offload']['effective_value'])
                self.assertTrue(request['graphics_offload']['private_config_process_bound'])
                self.assertEqual(len(request['expected_palette']),16);sleep.assert_called_once_with(20)
                self.assertTrue(output.call_args.args[0].startswith(P.HOST_FRAME_PREFIX))
                self.assertFalse(receipt['release_acceptance'])
            finally:
                child.terminate();child.wait(timeout=5)


class HostCaptureControls(unittest.TestCase):
    def request(self,reference):
        palette=[list(reference[((row*30+15)*160+column*40+20)*3:
                                ((row*30+15)*160+column*40+20)*3+3])
                 for row in range(4) for column in range(4)]
        return dict(schema='arctic-native-host-frame-request-v1',stage='installed',nonce='1'*32,
            boot_id='11111111-1111-1111-1111-111111111111',
            player=dict(client_id='7',pid=77,start_ticks=88,executable='/usr/bin/celluloid',
                executable_sha256='2'*64,is_xwayland=False),
            monitor=dict(name='Virtual-2',x=1280,y=0,width=1280,height=720,scale=1,is_hdr=False),
            client_geometry=dict(x=1280,y=0,width=1280,height=720),
            client_pixel_crop=dict(x=0,y=0,width=1280,height=720),expected_palette=palette,
            expected_rgb_sha256='3'*64,primary_screenshot_sha256='4'*64,
            primary_oracle_status='unmatched',playback_paused=True,playback_time_seconds=.8,
            graphics_offload=dict(schema='io.github.celluloid-player.Celluloid',key='graphics-offload-enable',
                effective_value=False,settings_backend='keyfile',private_config_process_bound=True),
            hold_seconds=20,release_acceptance=False)

    def test_selected_head_identical_oracle_crop_export_and_raw_delete(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);data=root/'data';data.mkdir()
            native=data/'native_smoke.py';native.write_bytes((HERE/'native_smoke.py').read_bytes())
            (data/'taskbar-context.json').write_text(json.dumps(dict(schema='arctic-taskbar-context-v1',
                native_sha256=hashlib.sha256(native.read_bytes()).hexdigest())))
            pid=os.getpid();(root/'taskbar-display-boot.json').write_text(json.dumps(dict(
                schema='arctic-qemu-taskbar-display-v1',status='uiinfo_applied_pending_guest_two_output_evidence',
                qemu_pid=pid,qemu_uid=os.geteuid(),gpu_id='arctic_taskbar_gpu',display_backend='dbus',heads=[
                    dict(head=0,xoff=0,yoff=0,width=1280,height=720),
                    dict(head=1,xoff=1280,yoff=0,width=1280,height=720)])))
            reference=N.visual_reference_frame();screen=Image.new('RGB',(1280,720),'black')
            fixture=Image.frombytes('RGB',(160,120),reference).resize((960,720),Image.Resampling.NEAREST)
            screen.paste(fixture,(160,0));calls=[]
            class VM:
                proc=types.SimpleNamespace(pid=pid)
                def cmd(self,command,**arguments):
                    calls.append((command,arguments));screen.save(arguments['filename']);return {'return':{}}
            controller=P.HostFrameController(VM(),root,'installed');request=self.request(reference)
            serial=P.HOST_FRAME_PREFIX+json.dumps(request,sort_keys=True)+'\n'
            self.assertTrue(controller.poll(serial));self.assertFalse(controller.poll(serial))
            receipt=json.loads((root/'native-host-frame-installed.json').read_text())
            self.assertEqual(receipt['status'],'captured');self.assertEqual(receipt['oracle']['status'],'matched')
            self.assertEqual(receipt['comparison'],'host-matched-guest-unmatched')
            self.assertEqual(receipt['interpretation'],'guest-screencopy-divergence-observed')
            self.assertTrue(receipt['identical_palette_oracle']);self.assertFalse(receipt['release_acceptance'])
            self.assertFalse(receipt['product_change_authorized']);self.assertEqual(receipt['capture']['head'],1)
            self.assertEqual(calls[0][0],'screendump');self.assertEqual(calls[0][1]['device'],'arctic_taskbar_gpu')
            self.assertEqual(calls[0][1]['head'],1);self.assertFalse(Path(calls[0][1]['filename']).exists())
            self.assertTrue((root/'native-host-celluloid-installed.png').is_file())

    def test_duplicate_request_stays_closed_without_capture(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);vm=Mock();vm.proc.pid=os.getpid()
            controller=P.HostFrameController(vm,root,'live');row=P.HOST_FRAME_PREFIX+'{}\n'
            self.assertTrue(controller.poll(row+row));vm.cmd.assert_not_called()
            receipt=json.loads((root/'native-host-frame-live.json').read_text())
            self.assertEqual(receipt['status'],'unknown');self.assertFalse(receipt['release_acceptance'])
            self.assertFalse(receipt['product_change_authorized'])


if __name__=='__main__':unittest.main()
