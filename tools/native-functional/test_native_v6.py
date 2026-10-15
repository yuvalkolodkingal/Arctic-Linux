#!/usr/bin/env python3
"""Additional host-only source/interaction/visual controls; never a guest or VM."""
import ast
import contextlib
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
from types import SimpleNamespace
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
    def test_moving_player_retirement_requires_exact_owned_process_socket_and_unmap(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);ipc=root/'celluloid-ipc.sock'
            endpoint=socket.socket(socket.AF_UNIX);endpoint.bind(str(ipc));endpoint.listen(1)
            player=dict(client_id='11',pid=os.getpid(),start_ticks=7,executable='/usr/bin/celluloid',
                        executable_sha256='a'*64,is_xwayland=False)
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=root;smoke.uid=os.getuid();smoke.owned=[player]
            smoke.clients=Mock(return_value={})
            smoke.wait=Mock(side_effect=lambda fn,*args:fn() or (_ for _ in ()).throw(RuntimeError('not retired')))
            try:
                with patch.object(N,'retire_renderer_player') as retire:
                    value=smoke.retire_moving_player(player,ipc)
                retire.assert_called_once_with(player,os.getuid())
                self.assertFalse(ipc.exists())
                self.assertEqual(value,dict(process_identity_retired=True,owned_ipc_absent=True,
                    compositor_client_absent=True,release_acceptance=False))
                with patch.object(N,'retire_renderer_player') as retire:
                    with self.assertRaisesRegex(RuntimeError,'target differs'):
                        smoke.retire_moving_player(dict(player),ipc)
                    with self.assertRaisesRegex(RuntimeError,'target differs'):
                        smoke.retire_moving_player(player,root/'other.sock')
                    retire.assert_not_called()
            finally: endpoint.close()

    def test_moving_player_retirement_fails_closed_while_client_remains(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);ipc=root/'celluloid-ipc.sock'
            endpoint=socket.socket(socket.AF_UNIX);endpoint.bind(str(ipc));endpoint.listen(1)
            player=dict(client_id='11',pid=os.getpid(),start_ticks=7,executable='/usr/bin/celluloid',
                        executable_sha256='a'*64,is_xwayland=False)
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=root;smoke.uid=os.getuid();smoke.owned=[player]
            smoke.clients=Mock(return_value={'11':dict(pid=player['pid'])})
            smoke.wait=Mock(side_effect=lambda fn,*args:fn() or (_ for _ in ()).throw(RuntimeError('not retired')))
            try:
                with patch.object(N,'retire_renderer_player'):
                    with self.assertRaisesRegex(RuntimeError,'not retired'):
                        smoke.retire_moving_player(player,ipc)
                self.assertFalse(ipc.exists())
            finally: endpoint.close()

    def test_moving_player_retirement_rejects_pre_quarantine_replacement_and_inode_aba(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);ipc=root/'celluloid-ipc.sock'
            original=socket.socket(socket.AF_UNIX);original.bind(str(ipc));original.listen(1)
            original_inode=ipc.lstat().st_ino
            replacement=None
            player=dict(client_id='11',pid=os.getpid(),start_ticks=7,executable='/usr/bin/celluloid',
                        executable_sha256='a'*64,is_xwayland=False)
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=root;smoke.uid=os.getuid();smoke.owned=[player]
            smoke.clients=Mock(return_value={})
            actual=N.rename_noreplace
            def replace(source_directory,source_name,target_directory,target_name):
                nonlocal replacement
                if source_name==ipc.name and replacement is None:
                    ipc.unlink()
                    replacement=socket.socket(socket.AF_UNIX);replacement.bind(str(ipc));replacement.listen(1)
                    self.assertNotEqual(ipc.lstat().st_ino,original_inode)
                return actual(source_directory,source_name,target_directory,target_name)
            try:
                with patch.object(N,'retire_renderer_player'),patch.object(N,'rename_noreplace',side_effect=replace):
                    with self.assertRaisesRegex(RuntimeError,'identity changed before quarantine'):
                        smoke.retire_moving_player(player,ipc)
                self.assertTrue(ipc.is_socket())
            finally:
                original.close()
                if replacement is not None: replacement.close()

    def test_moving_player_retirement_rejects_post_quarantine_recreation_without_deleting_it(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);ipc=root/'celluloid-ipc.sock'
            original=socket.socket(socket.AF_UNIX);original.bind(str(ipc));original.listen(1)
            replacement=None
            player=dict(client_id='11',pid=os.getpid(),start_ticks=7,executable='/usr/bin/celluloid',
                        executable_sha256='a'*64,is_xwayland=False)
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=root;smoke.uid=os.getuid();smoke.owned=[player]
            smoke.clients=Mock(return_value={})
            actual=N.rename_noreplace
            def recreate(source_directory,source_name,target_directory,target_name):
                nonlocal replacement
                result=actual(source_directory,source_name,target_directory,target_name)
                if source_name==ipc.name and replacement is None:
                    replacement=socket.socket(socket.AF_UNIX);replacement.bind(str(ipc));replacement.listen(1)
                return result
            smoke.wait=Mock(side_effect=lambda fn,*args:fn() or (_ for _ in ()).throw(RuntimeError('not retired')))
            try:
                with patch.object(N,'retire_renderer_player'),patch.object(N,'rename_noreplace',side_effect=recreate):
                    with self.assertRaisesRegex(RuntimeError,'recreated after quarantine'):
                        smoke.retire_moving_player(player,ipc)
                self.assertTrue(ipc.is_socket())
            finally:
                original.close()
                if replacement is not None: replacement.close()

    def test_moving_player_retirement_rejects_parent_rename_and_moved_root_recreation(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t);root=base/'fixture';root.mkdir(mode=0o700)
            moved=base/'moved-fixture';ipc=root/'celluloid-ipc.sock'
            original=socket.socket(socket.AF_UNIX);original.bind(str(ipc));original.listen(1)
            replacement=None
            player=dict(client_id='11',pid=os.getpid(),start_ticks=7,executable='/usr/bin/celluloid',
                        executable_sha256='a'*64,is_xwayland=False)
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=root;smoke.uid=os.getuid();smoke.owned=[player]
            smoke.clients=Mock(return_value={})
            def relocate(fn,*_):
                nonlocal replacement
                root.rename(moved);root.mkdir(mode=0o700)
                replacement=socket.socket(socket.AF_UNIX)
                replacement.bind(str(moved/ipc.name));replacement.listen(1)
                return fn()
            smoke.wait=Mock(side_effect=relocate)
            try:
                with patch.object(N,'retire_renderer_player'):
                    with self.assertRaisesRegex(RuntimeError,'directory identity changed after quarantine'):
                        smoke.retire_moving_player(player,ipc)
                self.assertTrue((moved/ipc.name).is_socket())
            finally:
                original.close()
                if replacement is not None: replacement.close()

    def test_atomic_quarantine_never_replaces_existing_target(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);source=root/'source';target=root/'target'
            source.write_bytes(b'source');target.write_bytes(b'target')
            directory=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:
                with self.assertRaises(FileExistsError):
                    N.rename_noreplace(directory,source.name,directory,target.name)
            finally: os.close(directory)
            self.assertEqual(source.read_bytes(),b'source')
            self.assertEqual(target.read_bytes(),b'target')

    def test_moving_player_retirement_rejects_different_ipc_peer(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);ipc=root/'celluloid-ipc.sock'
            endpoint=socket.socket(socket.AF_UNIX);endpoint.bind(str(ipc));endpoint.listen(1)
            player=dict(client_id='11',pid=os.getpid()+100000,start_ticks=7,
                        executable='/usr/bin/celluloid',executable_sha256='a'*64,is_xwayland=False)
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=root;smoke.uid=os.getuid();smoke.owned=[player]
            try:
                with patch.object(N,'retire_renderer_player') as retire:
                    with self.assertRaisesRegex(RuntimeError,'IPC peer differs'):
                        smoke.retire_moving_player(player,ipc)
                    retire.assert_not_called()
            finally: endpoint.close()

    def test_media_reuses_visibly_proved_player_for_authenticated_static_transition(self):
        source=(HERE/'native_smoke.py').read_text();tree=ast.parse(source)
        klass=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='Smoke')
        method=ast.get_source_segment(source,next(node for node in klass.body
            if isinstance(node,ast.FunctionDef) and node.name=='media'))
        capture=method.index("self.screenshot('celluloid-playing')")
        restore=method.index('self.player_fullscreen(player,False,ipc)',capture)
        reuse=method.index("schema='arctic-native-player-fixture-continuity-v1'",capture)
        static=method.index("self.visual_media(reuse if getattr(self,'gui_v6',False) else None)",reuse)
        self.assertLess(capture,reuse);self.assertLess(reuse,restore);self.assertLess(restore,static)
        self.assertNotIn('self.retire_moving_player(player,ipc)',method)
        self.assertNotIn('self.finish_native_protocol()',method)

    def test_moving_capture_reorders_only_the_final_existing_sample_settle(self):
        source=(HERE/'native_smoke.py').read_text();tree=ast.parse(source)
        klass=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='Smoke')
        method=ast.get_source_segment(source,next(node for node in klass.body
            if isinstance(node,ast.FunctionDef) and node.name=='media'))
        sample_loop=method.index('for sample_index in range(8):')
        retained_intervals=method.index('if sample_index < 7: time.sleep(.35)',sample_loop)
        fullscreen=method.index('self.player_fullscreen(player,True,ipc)',retained_intervals)
        final_settle=method.index('time.sleep(.35)',fullscreen)
        capture=method.index("self.screenshot('celluloid-playing')",final_settle)
        self.assertLess(sample_loop,retained_intervals)
        self.assertLess(retained_intervals,fullscreen)
        self.assertLess(fullscreen,final_settle)
        self.assertLess(final_settle,capture)
        self.assertEqual(method.count('time.sleep(.35)'),2)
        self.assertNotIn('range(9)',method)

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
        from test_controls_state_trials import restore_same_player_recapture,restore_security_stream_native
        after=nodes(restore_security_stream_native(restore_same_player_recapture(current,verify=True)))
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
    def test_actual_visual_method_uses_one_player_and_bounded_recapture(self):
        # Actual visual_media method + real FFmpeg fixture/PNG/crop. GUI/window
        # authority and mpv responses are explicit host-only fixtures.
        for case in ('positive','corrupt-first-capture','unmatched-both','oracle-failed',
                     'retry-deadline','retry-geometry-change'):
          with self.subTest(case=case),tempfile.TemporaryDirectory() as t:
            root=Path(t);smoke=N.Smoke.__new__(N.Smoke);smoke.root=root;smoke.uid=os.getuid();smoke.user=pwd.getpwuid(os.getuid())
            smoke.prefix=[];smoke.original_prefix=[];smoke.steps=[];smoke.owned=[];smoke.gui_v6=True;smoke.stage='live'
            smoke.trace=Mock();smoke.fullscreen_capture_pair=Mock();smoke.native_protocol_diagnostic=Mock()
            smoke.controlled_controls_trials=Mock();smoke.finish_native_protocol=Mock()
            smoke.hide_reference_controls=Mock(return_value=dict(after_visible=False,release_acceptance=False))
            smoke.product_renderer_contract=Mock(return_value=dict(requested_renderer='gl',realized_renderer='gl'))
            proof=dict(client_id='1',pid=123,start_ticks=1,executable='/usr/bin/celluloid',
                       executable_sha256='1'*64,is_xwayland=False)
            launched=[]
            smoke.launch_reference_player=Mock(side_effect=lambda argv,launch:launched.append(list(argv)))
            def fresh(trigger,*args):
                trigger();smoke.owned.append(proof);return proof
            smoke.fresh_window=Mock(side_effect=fresh)
            client=dict(id=1,pid=123,is_visible=True,is_focused=True,is_fullscreen=False,
                        monitor='FIXTURE',x=0,y=0,width=160,height=120)
            smoke.alive=Mock(side_effect=lambda _:dict(client))
            def fullscreen(player,enabled,ipc):client['is_fullscreen']=enabled
            smoke.player_fullscreen=Mock(side_effect=fullscreen)
            def wait(fn,*args,**kwargs):
                value=fn()
                if not value:raise RuntimeError('synthetic bounded wait failure')
                return value
            smoke.wait=Mock(side_effect=wait)
            monitor=dict(name='FIXTURE',x=0,y=0,width=160,height=120,scale=1,is_hdr=False)
            monitor_calls=[]
            props={'pause':False,
                   'video-params':dict(w=160,h=120),'current-vo':'libmpv'}
            raw_good=root/'fake-good.raw';raw_good.write_bytes(N.visual_reference_frame())
            raw_bad=root/'fake-bad.raw';raw_bad.write_bytes(b'\0'*(160*120*3))
            captures=[]
            for raw,name in ((raw_good,'fake-good.png'),(raw_bad,'fake-bad.png')):
                capture=root/name
                N.execute(['ffmpeg','-nostdin','-loglevel','error','-y','-f','rawvideo','-pixel_format','rgb24','-video_size','160x120',
                           '-i',str(raw),'-frames:v','1',str(capture)])
                captures.append(capture)
            good_capture,bad_capture=captures;grim_calls=[]
            original=smoke.cmd
            def cmd(argv,**kwargs):
                if argv[:2]==['mmsg','dispatch']:return (0,'{"success":true}','')
                if argv==['mmsg','get','all-monitors']:
                    monitor_calls.append(True);observed=dict(monitor)
                    if case=='retry-geometry-change' and len(monitor_calls)==3:observed['width']=159
                    return (0,json.dumps(dict(monitors=[observed])),'')
                if argv[0]=='grim':
                    grim_calls.append(list(argv))
                    good=(case=='positive' or case=='corrupt-first-capture' and len(grim_calls)==2)
                    shutil.copyfile(good_capture if good else bad_capture,argv[-1]);return (0,'','')
                return original(argv,**kwargs)
            smoke.cmd=Mock(side_effect=cmd)
            time_values=iter((0,.2,.8,.8,.8,.8,.8));pause_values=iter((False,True));path_values=iter((str(root/'open-codec-fixture.mkv'),str(root/'visual-reference.mkv'),str(root/'visual-reference.mkv')))
            def prop(path,key,*args):
                if key=='pause':return next(pause_values)
                if key=='path':return next(path_values)
                if key!='time-pos':return props[key]
                return next(time_values)
            oracle_control=(patch.object(N,'evaluate_reference_rgb',side_effect=ValueError('synthetic oracle failure'))
                            if case=='oracle-failed' else contextlib.nullcontext())
            with socket.socket(socket.AF_UNIX) as peer:
                peer.bind(str(root/'celluloid-ipc.sock'))
                # Rebind only this tested module. Patching time.sleep on the
                # shared stdlib module also records unrelated background sleeps.
                sleep=Mock()
                monotonic=(Mock(side_effect=(0,0,0,9.1)) if case=='retry-deadline' else N.time.monotonic)
                tested_time=SimpleNamespace(sleep=sleep,monotonic=monotonic)
                transition=dict(schema='arctic-native-fixture-transition-v2',
                    transport='owned Celluloid MPRIS D-Bus with mpv IPC SO_PEERCRED binding',
                    source=str(root/'open-codec-fixture.mkv'),target=str(root/'visual-reference.mkv'),
                    target_uri=(root/'visual-reference.mkv').as_uri(),
                    bus_name='org.mpris.MediaPlayer2.io.github.celluloid_player.Celluloid.instance-7',
                    owner_pid=proof['pid'],ipc_peer_pid=proof['pid'],ipc_peer_uid=smoke.uid,
                    object_path='/org/mpris/MediaPlayer2',interface='org.mpris.MediaPlayer2.Player',
                    method='OpenUri',reply_signature='()',
                    same_process_renderer_required=True,release_acceptance=False)
                reuse=dict(schema='arctic-native-player-fixture-continuity-v1',player=proof,
                    ipc=str(root/'celluloid-ipc.sock'),moving_fixture=str(root/'open-codec-fixture.mkv'),
                    moving_screenshot_sha256='9'*64,product_renderer=smoke.product_renderer_contract.return_value,
                    same_process_renderer_required=True,release_acceptance=False)
                with oracle_control,patch.object(N,'mpv_property',side_effect=prop), \
                     patch.object(N,'mpv_pause_reference') as pause,patch.object(N,'celluloid_replace_fixture',return_value=transition) as replace,patch.object(N,'time',tested_time):
                    if case in ('positive','corrupt-first-capture'):
                        value=smoke.visual_media(reuse);self.assertEqual(value['oracle']['status'],'matched')
                    elif case=='retry-deadline':
                        with self.assertRaisesRegex(RuntimeError,'visual capture retry deadline exhausted'):
                            smoke.visual_media(reuse)
                    elif case=='retry-geometry-change':
                        with self.assertRaisesRegex(RuntimeError,'owned player client is clipped/too small/unbounded'):
                            smoke.visual_media(reuse)
                    else:
                        with self.assertRaisesRegex(RuntimeError,'actual static visual fixture content unmatched'):
                            smoke.visual_media(reuse)
                replace.assert_called_once_with(smoke.prefix,root/'celluloid-ipc.sock',proof['pid'],smoke.uid,
                    root/'open-codec-fixture.mkv',root/'visual-reference.mkv')
            self.assertEqual(smoke.fresh_window.call_count,0)
            self.assertEqual(len(launched),0)
            expected_captures=2 if case in ('corrupt-first-capture','unmatched-both') else 1
            self.assertEqual(len(grim_calls),expected_captures)
            delays=[call.args[0] for call in sleep.call_args_list]
            retried=case in ('corrupt-first-capture','unmatched-both','retry-geometry-change')
            self.assertEqual(delays.count(.5),1+retried)
            self.assertTrue(all(delay==.5 or 0<delay<=.05 for delay in delays),delays)
            receipt=json.loads((root/'visual-oracle.json').read_text())
            if case in ('retry-deadline','retry-geometry-change'):
                self.assertEqual(receipt['schema'],'arctic-native-visual-attempts-v1')
                self.assertEqual((receipt['capture_attempt_limit'],receipt['capture_deadline_seconds']),(2,9.5))
                self.assertEqual(len(receipt['capture_attempts']),1)
                self.assertEqual(smoke.player_fullscreen.call_args_list,
                                 [unittest.mock.call(proof,True,root/'celluloid-ipc.sock')])
                continue
            self.assertEqual((receipt['player_attempt'],receipt['player_attempt_limit']),(1,1))
            self.assertEqual(receipt['fixture_cadence'],N.visual_reference_cadence())
            self.assertEqual(receipt['accepted_player_attempt'],1 if case in ('positive','corrupt-first-capture') else None)
            self.assertEqual(len(receipt['player_attempts']),1)
            row=receipt['player_attempts'][0]
            self.assertEqual((row['capture_attempt_limit'],len(row['capture_attempts'])),(2,expected_captures))
            self.assertEqual(row['capture_deadline_seconds'],9.5)
            if case=='corrupt-first-capture':
                self.assertEqual([x['oracle']['status'] for x in row['capture_attempts']],['unmatched','matched'])
                self.assertEqual(row['accepted_capture_attempt'],2)
            elif case=='positive':self.assertEqual(row['accepted_capture_attempt'],1)
            else:self.assertIsNone(row['accepted_capture_attempt'])
            self.assertEqual(row['playback_clock'],dict(pre_geometry_seconds=0,initial_seconds=.2,
                advanced_seconds=.8,paused_seconds=.8,settled_seconds=.8,capture_paused=True,
                presentation_refresh='frame-step',
                maximum_settled_drift_seconds=.05,minimum_advance_seconds=.5,
                anchor='after fullscreen and controls transitions'))
            pause.assert_called_once_with(root/'celluloid-ipc.sock',proof['pid'],smoke.uid)
            self.assertFalse(row['restart_eligible']);self.assertFalse(row['owned_player_cleanup_completed'])
            self.assertEqual(Path(row['screenshot']['path']).name,'celluloid-reference.png')
            self.assertFalse((root/'celluloid-reference-player-2.png').exists())
            smoke.controlled_controls_trials.assert_not_called()
            smoke.native_protocol_diagnostic.assert_called_once()
            self.assertEqual(smoke.player_fullscreen.call_args_list,
                             [unittest.mock.call(proof,True,root/'celluloid-ipc.sock'),
                              unittest.mock.call(proof,False,root/'celluloid-ipc.sock')])


if __name__=='__main__':unittest.main(verbosity=2)
