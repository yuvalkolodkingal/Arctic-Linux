"""Owned reference controls source/IPC fixtures; no display or VM proof."""
import ast
import hashlib
import importlib.util
import json
import os
import contextlib
import io
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('capture_controls_tested',HERE/'native_smoke.py')
N=importlib.util.module_from_spec(spec);spec.loader.exec_module(N)


def restore_capture_source(text):
    text=text.replace("json.dumps(report,ensure_ascii=False,separators=(',',':'))","json.dumps(report,ensure_ascii=False)")
    a=text.index('    def launch_reference_player('); z=text.index('    def visual_media(',a)
    text=text[:a]+text[z:]
    text=text.replace("lambda:self.launch_reference_player(['/usr/bin/celluloid','--no-existing-session',\n"
        "            '--new-window','--mpv-input-ipc-server='+str(ipc),'--mpv-loop-file=inf',str(fixture)],\n"
        "            self.launch_protocol_player if getattr(self,'gui_v6',False) else self.launch)",
        "lambda:(self.launch_protocol_player if getattr(self,'gui_v6',False) else self.launch)(['/usr/bin/celluloid','--no-existing-session',\n"
        "            '--new-window','--mpv-input-ipc-server='+str(ipc),'--mpv-loop-file=inf',str(fixture)])")
    text=text.replace('            controls=self.hide_reference_controls(player,ipc)\n','')
    text=text.replace("        if getattr(self,'gui_v6',False):\n            info['capture_precondition']=controls\n",'')
    text=text.replace("lambda:self.launch_reference_player(['/usr/bin/celluloid','--no-existing-session',\n"
        "                '--new-window','--mpv-input-ipc-server='+str(ipc),'--mpv-loop-file=inf',str(fixture)],self.launch_renderer)",
        "lambda:self.launch_renderer(['/usr/bin/celluloid','--no-existing-session',\n"
        "                '--new-window','--mpv-input-ipc-server='+str(ipc),'--mpv-loop-file=inf',str(fixture)])")
    text=text.replace("            value['capture_precondition']=self.hide_reference_controls(player,ipc)\n",'')
    a=text.index('def mpv_hide_reference_controls('); z=text.index('def mpv_property(',a)
    return text[:a]+text[z:]


class CompactFunctionalReport(unittest.TestCase):
    def serializer(self):
        source=(HERE/'native_smoke.py').read_text()
        function=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='run_checks')
        node=next(n for n in function.body if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call)
                  and isinstance(n.value.func,ast.Name) and n.value.func.id=='print')
        return compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(HERE/'native_smoke.py'),'exec')

    def emit(self,report):
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):
            exec(self.serializer(),{'json':json,'report':report})
        return stream.getvalue().encode('utf8')

    def test_compact_source_serializer_preserves_every_report_value(self):
        report={'schema':'synthetic','stage':'live','release_acceptance':False,
                'steps':[{'stdout':'שלום: whitespace  stays\\nquoted "text"','returncode':0}],
                'gates':[{'status':'failed','value':None}],'remaining':['unqualified']}
        row=self.emit(report)
        self.assertEqual(json.loads(row.split(b' ',1)[1]),report)
        self.assertEqual(row,b'ARCTIC-NATIVE-FUNCTIONAL '+json.dumps(report,ensure_ascii=False,separators=(',',':')).encode('utf8')+b'\n')

    def test_actual_physical_poll_keeps_original_pending_boundary(self):
        driver=(HERE.parent/'test-install.sh').read_text().split("read -r -d '' DRIVER <<'PY' || true\n",1)[1].split('\nPY\n',1)[0]
        node=next(n for n in ast.parse(driver).body if isinstance(n,ast.FunctionDef) and n.name=='physical_poll')
        code=compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),'original-physical-poll','exec')
        report={'schema':'synthetic','release_acceptance':False,'steps':[]}
        step={'argv':['mmsg','get','all'],'returncode':0,'stdout':'synthetic observer data','stderr':''}
        while len(('ARCTIC-NATIVE-FUNCTIONAL '+json.dumps(report,ensure_ascii=False)+'\n').encode())<=65536:
            report['steps'].append(dict(step))
        old=('ARCTIC-NATIVE-FUNCTIONAL '+json.dumps(report,ensure_ascii=False)+'\n').encode()
        compact=self.emit(report)
        self.assertGreater(len(old),65536);self.assertLessEqual(len(compact),65536)
        self.assertEqual(json.loads(compact.split(b' ',1)[1]),report)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'synthetic-uart';env={'os':os,'physical_module':object(),'serial':lambda name:str(path)}
            exec(code,env)
            path.write_bytes(old[:-1])
            with self.assertRaisesRegex(RuntimeError,'physical unfinished line bound exceeded'):env['physical_poll'](None,'install')
            path.write_bytes(compact[:-1]);self.assertTrue(env['physical_poll'](None,'install'))
            path.write_bytes(b'x'*65536);self.assertTrue(env['physical_poll'](None,'install'))
            path.write_bytes(b'x'*65537)
            with self.assertRaisesRegex(RuntimeError,'physical unfinished line bound exceeded'):env['physical_poll'](None,'install')


class CaptureControls(unittest.TestCase):
    def test_whole_source_rollback_restores_original_oracles_and_trials(self):
        source=(HERE/'native_smoke.py').read_text()
        restored=restore_capture_source(source)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),
                         '63ef27ec411ba6c629143e318ef6fab2cd17e3c1f827ae374ebbb374b30d6507')
        ast.parse(restored)
        for name in ('visual_reference_frame','visual_capture_geometry','evaluate_reference_rgb','mpv_property'):
            def segment(text):
                return ast.get_source_segment(text,next(n for n in ast.parse(text).body
                    if isinstance(n,ast.FunctionDef) and n.name==name))
            self.assertEqual(segment(source),segment(restored))
        self.assertIn("require(info['oracle']['status']=='matched'",source)

    def test_backend_is_only_owned_launch_and_restored_on_success_or_failure(self):
        for fail in (False,True):
          with tempfile.TemporaryDirectory() as t:
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=Path(t);smoke.uid=os.getuid();smoke.gui_v6=True;(smoke.root/'config').mkdir()
            smoke.prefix=['synthetic-prefix','XDG_CONFIG_HOME=/original/config','XDG_CONFIG_HOME='+str(smoke.root/'config')]
            initial=smoke.prefix; seen=[]
            def launch(argv):
                seen.append((list(smoke.prefix),list(argv)))
                if fail:raise RuntimeError('synthetic launch failure')
            if fail:
                with self.assertRaises(RuntimeError):smoke.launch_reference_player(['/usr/bin/celluloid'],launch)
            else:smoke.launch_reference_player(['/usr/bin/celluloid'],launch)
            self.assertIs(smoke.prefix,initial)
            self.assertEqual(seen[0][0],initial+['GSETTINGS_BACKEND=keyfile'])
            self.assertEqual(seen[0][1],['/usr/bin/celluloid'])
            smoke.prefix=['GSETTINGS_BACKEND=dconf']; launch=Mock()
            with self.assertRaises(RuntimeError):smoke.launch_reference_player(['/usr/bin/celluloid'],launch)
            launch.assert_not_called()

    def test_non_gui_v6_launch_keeps_original_environment(self):
        smoke=N.Smoke.__new__(N.Smoke);smoke.prefix=['original-prefix'];smoke.reference_settings_config=Mock()
        launch=Mock();smoke.launch_reference_player(['/usr/bin/celluloid','fixed-fixture'],launch)
        self.assertEqual(smoke.prefix,['original-prefix']);smoke.reference_settings_config.assert_not_called()
        launch.assert_called_once_with(['/usr/bin/celluloid','fixed-fixture'])

    def socket_control(self,reply,expected_pid=None,expected_uid=None):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'owned.sock'; server=socket.socket(socket.AF_UNIX); server.bind(str(path)); server.listen(1)
            request=[]; errors=[]
            def handle():
                try:
                    peer,_=server.accept()
                    with peer:
                        peer.settimeout(2); request.append(peer.recv(4096))
                        if request[-1]:peer.sendall(reply)
                except (BrokenPipeError,ConnectionResetError):pass
                except Exception as error:errors.append(error)
            worker=threading.Thread(target=handle); worker.start()
            try:
                result=None
                try:N.mpv_hide_reference_controls(path,expected_pid or os.getpid(),
                        os.getuid() if expected_uid is None else expected_uid)
                except Exception as error:result=error
            finally:
                server.close(); worker.join(3)
            self.assertFalse(worker.is_alive()); self.assertEqual(errors,[])
            return result,request

    def test_real_owned_unix_peer_receives_only_fixed_supported_hide_action(self):
        error,request=self.socket_control(b'{"request_id":43,"error":"success","data":null}\n')
        self.assertIsNone(error)
        self.assertEqual(json.loads(request[0]),dict(command=['script-message','celluloid-action',
            'win.set-controls-visible(false)'],request_id=43))

    def test_wrong_peer_is_rejected_before_command_write(self):
        error,request=self.socket_control(b'',expected_pid=os.getpid()+100000)
        self.assertIsInstance(error,RuntimeError); self.assertEqual(request,[b''])

    def test_failed_duplicate_oversized_and_closed_replies_cannot_hide(self):
        for reply in (b'{"request_id":43,"error":"failure"}\n',
                b'{"request_id":43,"request_id":43,"error":"success"}\n',
                b'{"request_id":43,"error":"success","data":false}\n',
                b'[]\n',b'x'*4097,b''):
            with self.subTest(reply_bytes=len(reply)):
                error,request=self.socket_control(reply)
                self.assertIsNotNone(error); self.assertEqual(len(request),1)

    def test_socket_path_owner_type_and_identity_guard_never_connect(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'foreign';path.write_bytes(b'unchanged')
            with patch.object(N.socket,'socket') as connect:
                for pid,uid in ((True,os.getuid()),(os.getpid(),0),(os.getpid(),os.getuid())):
                    with self.assertRaises(RuntimeError):N.mpv_hide_reference_controls(path,pid,uid)
                connect.assert_not_called()
            self.assertEqual(path.read_bytes(),b'unchanged')

    def fixture(self,t,*,env=None,focused=True,after=None,readbacks=('true','false')):
        root=Path(t); config=root/'config';config.mkdir()
        proc=root/'fake-proc'/'71';proc.mkdir(parents=True)
        (proc/'environ').write_bytes(env if env is not None else
            b'GSETTINGS_BACKEND=keyfile\0XDG_CONFIG_HOME='+os.fsencode(config)+b'\0')
        smoke=N.Smoke.__new__(N.Smoke);smoke.uid=os.getuid();smoke.root=root
        smoke.prefix=['synthetic-prefix','XDG_CONFIG_HOME='+str(config)]
        client=dict(id=10,pid=71,is_focused=focused,is_visible=True,is_fullscreen=True,
                    appid='celluloid',foreign_toplevel_id='owned',monitor='owned',x=0,y=0,width=1280,height=720)
        smoke.alive=Mock(side_effect=[client,client if after is None else dict(client,**after)])
        smoke.cmd=Mock(side_effect=[(0,v,'') for v in readbacks]);smoke.trace=Mock()
        def wait(fn,*args):
            if not fn():raise RuntimeError('synthetic readiness failure')
        smoke.wait=wait
        player=dict(executable='/usr/bin/celluloid',is_xwayland=False,pid=71)
        path=lambda value:Path(root/'fake-proc' if str(value)=='/proc' else value)
        return smoke,player,path

    def test_action_readback_is_same_private_config_and_after_widget_update(self):
        with tempfile.TemporaryDirectory() as t:
            smoke,player,path=self.fixture(t)
            with patch.object(N,'Path',side_effect=path),patch.object(N,'mpv_hide_reference_controls') as action:
                value=smoke.hide_reference_controls(player,'owned.sock')
            action.assert_called_once_with('owned.sock',71,os.getuid())
            self.assertEqual(value['action'],'win.set-controls-visible(false)')
            self.assertTrue(value['before_visible']);self.assertFalse(value['after_visible'])
            for call in smoke.cmd.call_args_list:
                self.assertEqual(call.args[0],['/usr/bin/env','GSETTINGS_BACKEND=keyfile','/usr/bin/gsettings','get',
                    'io.github.celluloid-player.Celluloid.window-state','show-controls'])
            self.assertFalse(value['release_acceptance'])

    def test_poisoned_backend_config_or_focus_cannot_send_action(self):
        for env,focus in ((b'GSETTINGS_BACKEND=dconf\0XDG_CONFIG_HOME=/private\0',True),
                         (b'GSETTINGS_BACKEND=keyfile\0XDG_CONFIG_HOME=/foreign\0',True),
                         (None,False)):
            with tempfile.TemporaryDirectory() as t:
                smoke,player,path=self.fixture(t,env=env,focused=focus)
                with patch.object(N,'Path',side_effect=path),patch.object(N,'mpv_hide_reference_controls') as action:
                    with self.assertRaises(RuntimeError):smoke.hide_reference_controls(player,'owned.sock')
                action.assert_not_called()

    def test_private_config_cannot_escape_to_another_owned_directory_or_symlink(self):
        for kind in ('other-owned','symlink','writable'):
            with tempfile.TemporaryDirectory() as t:
                smoke,player,path=self.fixture(t)
                config=Path(t)/'config'
                if kind=='other-owned':
                    other=Path(t)/'other';other.mkdir();smoke.prefix[-1]='XDG_CONFIG_HOME='+str(other)
                elif kind=='symlink':
                    config.rmdir();other=Path(t)/'other';other.mkdir();config.symlink_to(other)
                else:config.chmod(0o777)
                with patch.object(N,'mpv_hide_reference_controls') as action:
                    with self.assertRaises(RuntimeError):smoke.hide_reference_controls(player,'owned.sock')
                action.assert_not_called()

    def test_failed_readback_and_identity_change_fail_before_capture(self):
        for readbacks,after in ((('true','true'),None),(('true','maybe'),None),(('true','false'),dict(pid=72))):
            with tempfile.TemporaryDirectory() as t:
                smoke,player,path=self.fixture(t,readbacks=readbacks,after=after)
                with patch.object(N,'Path',side_effect=path),patch.object(N,'mpv_hide_reference_controls'):
                    with self.assertRaises(RuntimeError):smoke.hide_reference_controls(player,'owned.sock')
                smoke.trace.assert_not_called()

    def test_both_actual_capture_paths_hide_before_original_half_second(self):
        source=(HERE/'native_smoke.py').read_text(); tree=ast.parse(source)
        for klass,name in (('Smoke','visual_media'),('RendererTrialSmoke','observe')):
            node=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name==klass)
            method=ast.get_source_segment(source,next(x for x in node.body if isinstance(x,ast.FunctionDef) and x.name==name))
            self.assertLess(method.index('self.hide_reference_controls(player,ipc)'),method.index('time.sleep(.5)'))
            self.assertLess(method.index('time.sleep(.5)'),method.index("['grim'"))
            self.assertEqual(method.count('time.sleep(.5)'),1)
            self.assertEqual(method.count('self.hide_reference_controls(player,ipc)'),1)
            self.assertIn('evaluate_reference_rgb(',method)


if __name__=='__main__':unittest.main()
