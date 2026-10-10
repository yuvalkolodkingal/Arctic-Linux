#!/usr/bin/env python3
"""Additional host-only source/interaction/visual controls; never a guest or VM."""
import ast
import hashlib
import copy
import importlib.util
import json
import os
import pwd
import shutil
import socket
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('native_v4_tested',HERE/'native_smoke.py')
N=importlib.util.module_from_spec(spec);spec.loader.exec_module(N)


def image(reference, scale=1, width=420, height=340, x=37, y=61):
    data=bytearray(width*height*3)
    for yy in range(120*scale):
        for xx in range(160*scale):
            start=((y+yy)*width+x+xx)*3; origin=((yy//scale)*160+xx//scale)*3
            data[start:start+3]=reference[origin:origin+3]
    return bytes(data)


class NewControls(unittest.TestCase):
    def test_known_static_pattern_and_scaled_offset_match(self):
        ref=N.visual_reference_frame()
        for scale in (1,2):
            actual=image(ref,scale)
            result=N.evaluate_reference_rgb(actual,420,340,ref)
            self.assertEqual(result['status'],'matched')
            self.assertGreaterEqual(result['checked_interior_pixels'],2000)
            self.assertEqual(result['roi_client_pixels'],dict(x=37,y=61,width=160*scale,height=120*scale))
            self.assertEqual(result['scale'],[scale,scale])
    def test_black_flat_wrong_orientation_and_sparse_marks_do_not_pass(self):
        ref=N.visual_reference_frame()
        reversed_frame=b''.join(ref[(y*160+x)*3:(y*160+x)*3+3] for y in range(120) for x in reversed(range(160)))
        sparse=bytearray(160*120*3)
        for row in range(4):
            for col in range(4):
                offset=((row*30+15)*160+col*40+20)*3
                sparse[offset:offset+3]=ref[offset:offset+3]
        for value in (b'\0'*len(ref),b'\x80'*len(ref),reversed_frame,bytes(sparse)):
            with self.subTest(value_hash=hash(value)):
                self.assertEqual(N.evaluate_reference_rgb(value,160,120,ref)['status'],'unmatched')
    def test_corrupted_content_and_clipped_frame_do_not_pass(self):
        ref=N.visual_reference_frame(); damaged=bytearray(ref)
        # Corrupt a complete interior band in every cell, beyond the one percent bound.
        for r in range(4):
            for c in range(4):
                for y in range(r*30+10,r*30+14):
                    for x in range(c*40+10,c*40+30):
                        offset=(y*160+x)*3; damaged[offset:offset+3]=b'\0'*3
        self.assertEqual(N.evaluate_reference_rgb(bytes(damaged),160,120,ref)['status'],'unmatched')
        clipped=b''.join(ref[y*160*3:y*160*3+80*3] for y in range(120))
        self.assertEqual(N.evaluate_reference_rgb(clipped,80,120,ref)['status'],'unmatched')
    def test_malformed_reference_dimensions_and_bounds_fail(self):
        ref=N.visual_reference_frame()
        for data,w,h,expected in ((ref,True,120,ref),(ref,160,120,ref[:-1]),(ref[:-1],160,120,ref),
                                  (b'\0'*len(ref),160,120,b'\0'*len(ref)),(ref,4096,4096,ref)):
            with self.subTest(w=w,h=h),self.assertRaises(RuntimeError):N.evaluate_reference_rgb(data,w,h,expected)
    def test_approved_physical_navigation_keeps_actual_title_and_thirty_second_gate(self):
        with tempfile.TemporaryDirectory() as t:
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=Path(t);directory=smoke.root/'files with spaces';directory.mkdir()
            smoke.physical_pcmanfm=Mock();smoke.diagnostic=Mock();smoke.alive=Mock(return_value=dict(title=directory.name))
            def wait(fn,timeout,label):
                self.assertEqual(timeout,30);self.assertTrue(fn());self.assertIn(directory.name,label)
            smoke.wait=Mock(side_effect=wait);proof=dict(client_id='4',pid=3046,start_ticks=11,executable='/usr/bin/pcmanfm')
            smoke.navigate(proof,directory,'control')
            smoke.physical_pcmanfm.assert_called_once_with(proof,'navigate',str(directory))
            self.assertEqual(smoke.diagnostic.call_count,2)
            smoke.wait.side_effect=RuntimeError('strict30secondfailure')
            with self.assertRaisesRegex(RuntimeError,'strict30secondfailure'):smoke.navigate(proof,directory,'control')
    def test_failed_focus_never_sends_unproved_keyboard_input(self):
        smoke=N.Smoke.__new__(N.Smoke);smoke.trace=Mock();smoke.alive=Mock(return_value=dict(is_focused=True))
        smoke.cmd=Mock(return_value=(0,'{"success":false}',''));smoke.wait=Mock()
        with self.assertRaisesRegex(RuntimeError,'acknowledge'):
            smoke.keys(dict(client_id='4',pid=3046),'-k','Return')
        self.assertEqual(smoke.cmd.call_count,1)
        self.assertEqual(smoke.cmd.call_args.args[0][:2],['mmsg','dispatch'])
    def test_failure_collects_before_gate_returns_without_turning_it_into_pass(self):
        smoke=N.Smoke.__new__(N.Smoke);smoke.trace=Mock();smoke.diagnostic=Mock(return_value=dict(screenshot='failure-frame'))
        smoke.gates=[]
        self.assertIsNone(smoke.gate('actual-role-file-manager-terminal-editor',Mock(side_effect=RuntimeError('navigation failed'))))
        self.assertEqual(smoke.gates[0]['status'],'failed')
        self.assertEqual(smoke.gates[0]['diagnostic']['screenshot'],'failure-frame')
        smoke.diagnostic.assert_called_once()
    def test_required_diagnostic_collector_error_cannot_pass(self):
        smoke=N.Smoke.__new__(N.Smoke);smoke.trace=Mock();smoke.clients=Mock(side_effect=RuntimeError('client IPC unavailable'))
        with self.assertRaisesRegex(RuntimeError,'required GUI diagnostic'):
            smoke.diagnostic('decisive')
        result=smoke.diagnostic('already-failed',required=False)
        self.assertIn('client IPC unavailable',result['collector_error'])
    def test_bounded_trace_retains_last_and_declares_omission(self):
        with tempfile.TemporaryDirectory() as t:
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=Path(t);smoke.active_gate='control';smoke.client_observations=3
            smoke.trace_bytes=2*1024*1024;smoke.trace_omitted=0
            smoke.trace('final',client=dict(pid=3046))
            summary=json.loads((smoke.root/'gui-trace-summary.json').read_text())
            self.assertEqual(summary['omitted_records'],1);self.assertEqual(summary['last']['event'],'final')
            self.assertFalse((smoke.root/'gui-trace.log').exists())
    def test_protected_functions_and_original_moving_workload_bytes_unchanged(self):
        # Exact source-segment pins from inherited immutable 2ba880 object; Python-version independent.
        pins={'guest_guard': '93ad96259dfcece98446936ccd061e5f3d75838cbdd220471a1678ad2a2e7395', 'discover_desktop': '31f494b3a4c2388fe1c33ecd6cf38a689c35239d602df3f631d140f4660a69d1', 'identity': '3e6d810c3b7a5ab50be2832b9747d8b308089e5692339b0d7a4b1efc3d2c3167', 'window_proof': '999af0a0ec525ae2696722b6d42c15af1dea972229036eb22f07e951a85fb517', 'process_snapshot': '14335a4d68d3c48004418e17fca26b6f83bcaba3cd61d513a91b220d1c3a61d2', 'SecurityInterval': '758146e5c438fa54cd3ead6f14dbc0c4e4355df5f7ee343f47f873b49ab14e8f', 'parse_audit_status': '3b013f73994a6edc6385177841652469cd74e7d33dde1df3f52301233e7b42ed', 'verify_security': '7692c85a86c80cb2caf55da5e782df872bd3a9788eb4f6703b5b496b146dc614', 'tree_hashes': '2168b8be108e2d23ad89fd98b1e4e603616851db4653b8dc7ea4da219881f151', 'verify_tree': 'c88312738b2588278b8ae6e3fb3f8ec28bb78149bef32cfdeff7076a0f25a8f1', 'mpv_property': 'fedb6890c75dd285d36ae394ae934952efe0f5b13bdd3800c3cefb03a7aeea00', 'validate_player_samples': 'c5f08296489639a91437a630c6beac9754b015f3d098377156298e5dcfcefd12', 'Smoke.cleanup': '9cca15076be8638c7cf1404149af3bb251c73bbbf995616d7181c5fbc5045149', 'Smoke.setup': 'f8591ca150aa7662ce6f5705e341b1398bbc9b7c4f7cc0d0be3ba2b27e3806d0', 'Smoke.archives': '11c97e5241a939fc3b949fbfc00eb099a22b12d8857eb5c95ff90631ac0c6144', 'Smoke.desktop_services': '35b06727f23cc9d43bcacd6c03175dbe1a0c8be5ebdd4e9647021184f7bfc672', 'Smoke.media_fixture': '02537ef8550b0e15e95e273c28888ff3a02c1c7b051d2161a019aaf1f639eb12'}
        current=(HERE/'native_smoke.py').read_text()
        def nodes(text):
            result={}
            for n in ast.parse(text).body:
                if isinstance(n,(ast.FunctionDef,ast.ClassDef)):
                    result[n.name]=ast.get_source_segment(text,n)
                    if isinstance(n,ast.ClassDef):
                        for item in n.body:
                            if isinstance(item,ast.FunctionDef):result[n.name+'.'+item.name]=ast.get_source_segment(text,item)
            return result
        after=nodes(current)
        for name in ('guest_guard','discover_desktop','identity','window_proof','process_snapshot','SecurityInterval',
                     'parse_audit_status','verify_security','tree_hashes','verify_tree','mpv_property','validate_player_samples',
                     'Smoke.cleanup','Smoke.setup','Smoke.archives','Smoke.desktop_services','Smoke.media_fixture'):
            with self.subTest(name=name):self.assertEqual(pins[name],hashlib.sha256(after[name].encode()).hexdigest())
    def test_all_eight_original_checks_remain_required(self):
        text=(HERE/'native_smoke.py').read_text()
        names={node.args[0].value for node in ast.walk(ast.parse(text)) if isinstance(node,ast.Call)
               and isinstance(node.func,ast.Attribute) and node.func.attr=='gate' and node.args
               and isinstance(node.args[0],ast.Constant)}
        self.assertEqual(names,{'fresh-defaults-and-isolation','archive-content-roundtrips','actual-role-file-manager-terminal-editor',
            'open-codec-content-and-player-state','portal-and-accessibility-reachability','owned-process-cleanup-config-preservation','selinux-and-new-avcs'})
        self.assertIn("check='open-codec-lossless-command-decode'",text)

    def test_capture_geometry_rejects_unfocused_bool_nonfinite_and_invalid_monitor(self):
        client=dict(id=1,pid=123,is_visible=True,is_focused=True,monitor='FIXTURE',x=0,y=0,width=160,height=120)
        monitor=dict(name='FIXTURE',x=0,y=0,width=160,height=120,scale=1,is_hdr=False)
        self.assertEqual(N.visual_capture_geometry(client,dict(monitors=[monitor]))[2],dict(x=0,y=0,width=160,height=120))
        invalid=[('client','is_focused',False),('client','id',True),('client','width',True),
                 ('monitor','scale',True),('monitor','scale',float('nan')),('monitor','scale',float('inf')),
                 ('monitor','scale',0),('monitor','scale',2),('monitor','x',True),('monitor','x',float('nan')),
                 ('monitor','y',1.0),('monitor','width',False),('monitor','width',0),('monitor','height',9000)]
        for target,key,value in invalid:
            with self.subTest(target=target,key=key,value=value),self.assertRaises(RuntimeError):
                c,m=copy.deepcopy(client),copy.deepcopy(monitor)
                (c if target=='client' else m)[key]=value
                N.visual_capture_geometry(c,dict(monitors=[m]))
        with self.assertRaisesRegex(RuntimeError,'ambiguous'):
            N.visual_capture_geometry(client,dict(monitors=[monitor,monitor]))

    @unittest.skipUnless(shutil.which('ffmpeg'),'host FFmpeg absent; actual guest gate remains mandatory')
    def test_actual_visual_method_positive_and_black_capture_failure(self):
        # Actual visual_media method + real FFmpeg fixture/PNG/crop. Only GUI,
        # window authority and mpv responses are explicit host-only fixtures.
        for case in ('positive','black','unfocused-before','unfocused-after','boolean-scale','boolean-coordinate','monitor-changed','identity-changed'):
            black=case=='black'
            with self.subTest(case=case),tempfile.TemporaryDirectory() as t:
                root=Path(t);smoke=N.Smoke.__new__(N.Smoke);smoke.root=root;smoke.uid=os.getuid();smoke.user=pwd.getpwuid(os.getuid())
                smoke.prefix=[];smoke.original_prefix=[];smoke.steps=[]
                smoke.trace=Mock();proof=dict(client_id='1',pid=123,start_ticks=1,executable='/usr/bin/celluloid')
                client=dict(id=1,pid=123,is_visible=True,is_focused=True,monitor='FIXTURE',x=0,y=0,width=160,height=120)
                smoke.fresh_window=Mock(return_value=proof)
                before,after=copy.deepcopy(client),copy.deepcopy(client)
                monitor=dict(name='FIXTURE',x=0,y=0,width=160,height=120,scale=1,is_hdr=False)
                if case=='unfocused-before':before['is_focused']=False
                if case=='unfocused-after':after['is_focused']=False
                if case=='boolean-scale':monitor['scale']=True
                if case=='boolean-coordinate':monitor['x']=True;before['x']=after['x']=1
                if case=='identity-changed':after['id']=2
                smoke.alive=Mock(side_effect=[client,before,after])
                monitor_calls=[]
                def wait(fn,*args,**kwargs):
                    value=fn();self.assertTrue(value);return value
                smoke.wait=Mock(side_effect=wait)
                props={'path':str(root/'visual-reference.mkv'),'pause':False,'video-params':dict(w=160,h=120),'current-vo':'libmpv','time-pos':.5}
                pixels=b'\0'*(160*120*3) if black else N.visual_reference_frame()
                raw=root/'fake-capture.raw';raw.write_bytes(pixels)
                capture=root/'fake-capture.png'
                N.execute(['ffmpeg','-nostdin','-loglevel','error','-y','-f','rawvideo','-pixel_format','rgb24','-video_size','160x120',
                           '-i',str(raw),'-frames:v','1',str(capture)])
                original=smoke.cmd
                def cmd(argv,**kwargs):
                    if argv[:2]==['mmsg','dispatch']:return (0,'{"success":true}','')
                    if argv==['mmsg','get','all-monitors']:
                        monitor_calls.append(True)
                        observed=copy.deepcopy(monitor)
                        if case=='monitor-changed' and len(monitor_calls)==2:observed['width']=161
                        return (0,json.dumps(dict(monitors=[observed])),'')
                    if argv[0]=='grim':shutil.copyfile(capture,argv[-1]);return (0,'','')
                    return original(argv,**kwargs)
                smoke.cmd=Mock(side_effect=cmd)
                with socket.socket(socket.AF_UNIX) as peer:
                    peer.bind(str(root/'visual-reference-ipc.sock'))
                    with patch.object(N,'mpv_property',side_effect=lambda path,key,*args:props[key]),patch.object(N.time,'sleep'):
                        if case=='positive':
                            value=smoke.visual_media();self.assertEqual(value['oracle']['status'],'matched')
                        else:
                            with self.assertRaises(RuntimeError):smoke.visual_media()
                if case in ('positive','black'):
                    value=json.loads((root/'visual-oracle.json').read_text())
                    self.assertEqual(value['oracle']['status'],'unmatched' if black else 'matched')
                    self.assertTrue((root/'celluloid-reference.png').is_file());self.assertTrue((root/'visual-owned-window.rgb').is_file())
                    self.assertEqual(len(monitor_calls),2)
                elif case in ('unfocused-after','monitor-changed','identity-changed'):
                    self.assertTrue((root/'celluloid-reference.png').is_file())
                    self.assertFalse((root/'visual-oracle.json').exists())
                else:
                    self.assertFalse((root/'celluloid-reference.png').exists())


if __name__=='__main__':unittest.main(verbosity=2)
