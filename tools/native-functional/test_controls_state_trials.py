"""Source/owned-host controls for default-player control-state diagnostics; no VM."""
import ast
import copy
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import pwd
import socket
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import zlib

HERE=Path(__file__).resolve().parent
BASE_NATIVE_SHA='51198d994db37cf4b6df95b25d25e8e7aa83e66fa525968eab37bc2211da9532'
BASE_GUEST_SHA='5cbf0c6385465cfa5f94fd3addaa36729e030a10b2864af5424f09438c4580ec'
spec=importlib.util.spec_from_file_location('controls_trial_tested',HERE/'native_smoke.py')
N=importlib.util.module_from_spec(spec);spec.loader.exec_module(N)


def restore_controls_native(source):
    for start,end in (
        ('    # BEGIN CONTROLLED_CONTROLS_INVOCATION\n','    # END CONTROLLED_CONTROLS_INVOCATION\n\n'),
        ('# BEGIN CONTROLLED_CONTROLS_STUDY\n','# END CONTROLLED_CONTROLS_STUDY\n\n\n'),
    ):
        if source.count(start)!=1 or source.count(end)!=1:raise AssertionError('Controls inverse markers differ')
        a=source.index(start);z=source.index(end,a)+len(end);source=source[:a]+source[z:]
    new='            self.controlled_controls_trials(fixture,expected,source_sha,info)\n'
    if source.count(new)!=1:raise AssertionError('Controls inverse call differs')
    source=source.replace(new,'            self.controlled_renderer_trials(fixture,expected,source_sha,info)\n')
    if hashlib.sha256(source.encode()).hexdigest()!=BASE_NATIVE_SHA:raise AssertionError('Original whole Native source differs')
    return source


def restore_controls_guest(source):
    native=(HERE/'native_smoke.py').read_text()
    boundary='\n\n# BEGIN NATIVE_BULK_TRANSPORT\n'
    original=restore_controls_native(native)
    if not source.startswith(native[:native.index('def main():\n')]):raise AssertionError('Controls guest prefix differs')
    # The bundle inherits the original Native prefix through run_checks, then
    # the original bulk/export entrypoint. No off-branch Git object is required.
    head=native[:native.index('def main():\n')]
    source=original[:original.index('def main():\n')]+source[len(head):]
    substitutions=(
        ('0-controls-state-trials.json','0-controlled-renderer-trials.json'),
        ('controls-trial-transition/reference.png','renderer-trial-default/reference.png'),
        ('controls-trial-hidden/reference.png','renderer-trial-gl/reference.png'),
        (hashlib.sha256(native.encode()).hexdigest(),BASE_NATIVE_SHA),
    )
    for new,old in substitutions:
        if source.count(new)!=1:raise AssertionError('Controls guest inverse occurrence differs')
        source=source.replace(new,old)
    if hashlib.sha256(source.encode()).hexdigest()!=BASE_GUEST_SHA:raise AssertionError('Original whole guest differs')
    return source


class ControlsStateTrials(unittest.TestCase):
    def parent(self,root):
        config=root/'config';config.mkdir(mode=0o700)
        return Mock(root=root,user=pwd.getpwuid(os.getuid()),uid=os.getuid(),stage='live',
                    prefix=['synthetic-owned-prefix','XDG_CONFIG_HOME='+str(config)],
                    original_prefix=['synthetic-owned-prefix'])

    def test_whole_source_guest_and_unchanged_capture_oracle_rollback(self):
        new=(HERE/'native_smoke.py').read_text();old=restore_controls_native(new)
        restored=restore_controls_guest((HERE/'guest-check-native-v6.py').read_text())
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),BASE_GUEST_SHA)
        def segment(text,name,klass=None):
            nodes=ast.parse(text).body
            if klass:nodes=next(n for n in nodes if isinstance(n,ast.ClassDef) and n.name==klass).body
            return ast.get_source_segment(text,next(n for n in nodes if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name==name))
        for name in ('visual_reference_frame','evaluate_reference_rgb','visual_capture_geometry','mpv_property','mpv_hide_reference_controls'):
            self.assertEqual(segment(new,name),segment(old,name))
        self.assertEqual(segment(new,'RendererTrialSmoke'),segment(old,'RendererTrialSmoke'))
        for name in ('launch_reference_player','hide_reference_controls','cleanup','setup'):
            self.assertEqual(segment(new,name,'Smoke'),segment(old,name,'Smoke'))
        self.assertEqual(segment(new,'visual_media','Smoke').replace('self.controlled_controls_trials(', 'self.controlled_renderer_trials('),segment(old,'visual_media','Smoke'))
        for text in (new.replace("time.sleep(.5)","time.sleep(.6)",1),new+'\n# unknown mutation\n'):
            with self.assertRaises(AssertionError):restore_controls_native(text)

    def test_private_seed_exact_commands_and_nonzero_or_poison_readbacks_abort(self):
        for state in ('transition','hidden'):
            with tempfile.TemporaryDirectory() as temporary:
                trial=N.ControlsTrialSmoke(self.parent(Path(temporary)),state)
                wanted='true' if state=='transition' else 'false'
                trial.cmd=Mock(side_effect=[(0,'',''),(0,wanted,'')])
                proof=trial.seed_controls()
                self.assertEqual(proof['initial_visible'],state=='transition')
                calls=[c.args[0] for c in trial.cmd.call_args_list]
                prefix=['/usr/bin/env','GSETTINGS_BACKEND=keyfile','/usr/bin/gsettings']
                schema=['io.github.celluloid-player.Celluloid.window-state','show-controls']
                self.assertEqual(calls,[prefix+['set']+schema+[wanted],prefix+['get']+schema])
                for call in trial.cmd.call_args_list:self.assertEqual(call.kwargs['timeout'],5)
                for replies in ([(1,'','')],[(0,'',''),(1,wanted,'')],[(0,'',''),(0,'maybe','')],[(0,'',''),(0,'false' if wanted=='true' else 'true','')]):
                    trial.cmd=Mock(side_effect=replies)
                    with self.assertRaises(RuntimeError):trial.seed_controls()
                trial.prefix.append('GSETTINGS_BACKEND=dconf');trial.cmd=Mock()
                with self.assertRaises(RuntimeError):trial.seed_controls()
                trial.cmd.assert_not_called()

    def test_private_seed_foreign_directory_symlink_and_write_permission_reject(self):
        for poison in ('foreign','symlink','writable'):
            with tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);trial=N.ControlsTrialSmoke(self.parent(root),'hidden');trial.cmd=Mock()
                config=root/'config'
                if poison=='foreign':
                    other=root/'other';other.mkdir(mode=0o700);trial.prefix[-1]='XDG_CONFIG_HOME='+str(other)
                elif poison=='symlink':
                    config.rmdir();other=root/'other';other.mkdir();config.symlink_to(other)
                else:config.chmod(0o777)
                with self.assertRaises(RuntimeError):trial.seed_controls()
                trial.cmd.assert_not_called()

    def test_same_owned_default_launcher_and_half_second_capture_for_both_states(self):
        for state in ('transition','hidden'):
            with tempfile.TemporaryDirectory() as temporary:
                trial=N.ControlsTrialSmoke(self.parent(Path(temporary)),state);drain=Mock()
                with patch.object(N,'NativeProtocolDrain',return_value=drain),patch.object(N.subprocess,'Popen',return_value=Mock()) as popen:
                    trial.launch_reference_player(['/usr/bin/celluloid','--no-existing-session','--new-window','same-fixture'],trial.launch_renderer)
                argv=popen.call_args.args[0]
                self.assertEqual(argv[:3],['synthetic-owned-prefix',trial.prefix[1],'GSETTINGS_BACKEND=keyfile'])
                self.assertEqual(argv[3:9],['env','-u','GSK_RENDERER','GSK_DEBUG=renderer','WAYLAND_DEBUG=client','/usr/bin/celluloid'])
                self.assertNotIn('GSK_RENDERER=gl',argv);self.assertNotIn('GSETTINGS_BACKEND=keyfile',trial.prefix)
                drain.start.call_args.args[0].close()
        method=ast.get_source_segment((HERE/'native_smoke.py').read_text(),next(n for n in ast.parse((HERE/'native_smoke.py').read_text()).body if isinstance(n,ast.ClassDef) and n.name=='RendererTrialSmoke'))
        self.assertEqual(method.count('time.sleep(.5)'),1)
        self.assertLess(method.index('self.hide_reference_controls(player,ipc)'),method.index('time.sleep(.5)'))
        self.assertLess(method.index('time.sleep(.5)'),method.index("['grim'"))

    def test_bound_actual_action_readback_must_match_seed_and_hidden_state(self):
        for state in ('transition','hidden'):
            with tempfile.TemporaryDirectory() as temporary:
                trial=N.ControlsTrialSmoke(self.parent(Path(temporary)),state)
                good=dict(before_visible=state=='transition',after_visible=False,private_config_process_bound=True)
                with patch.object(N.Smoke,'hide_reference_controls',return_value=good):
                    self.assertEqual(trial.hide_reference_controls({},'owned.sock'),good)
                for poison in (dict(before_visible=not good['before_visible']),dict(before_visible=1),dict(after_visible=True),dict(private_config_process_bound=False)):
                    with patch.object(N.Smoke,'hide_reference_controls',return_value=dict(good,**poison)),self.assertRaises(RuntimeError):
                        trial.hide_reference_controls({},'owned.sock')

    def test_seed_failure_aborts_before_launch_and_retains_primary_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial=N.ControlsTrialSmoke(self.parent(Path(temporary)),'transition')
            trial.seed_controls=Mock(side_effect=RuntimeError('private source-known failure'))
            with patch.object(N.RendererTrialSmoke,'observe') as launch:
                with self.assertRaises(RuntimeError):trial.observe('fixture','expected','a'*64)
                launch.assert_not_called()

    def test_actual_observe_runs_seed_bound_hide_half_second_and_unchanged_rgb_oracle(self):
        for state,palette in (('transition',True),('hidden',True),('hidden',False)):
            with self.subTest(state=state,palette=palette),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);trial=N.ControlsTrialSmoke(self.parent(root),state)
                fixture=root/'fixture';fixture.write_bytes(b'source-fixed-synthetic-media')
                expected=root/'expected';expected.write_bytes(N.visual_reference_frame())
                pixels=expected.read_bytes() if palette else b'\0'*(160*120*3)
                player=dict(pid=71,start_ticks=3,client_id='10',executable='/usr/bin/celluloid',
                            executable_sha256='a'*64,is_xwayland=False)
                client=dict(id=10,pid=71,appid='celluloid',foreign_toplevel_id='owned',
                    x=0,y=0,width=160,height=120,monitor='synthetic-monitor',
                    is_focused=True,is_visible=True,is_fullscreen=True)
                monitors=dict(monitors=[dict(name='synthetic-monitor',x=0,y=0,width=160,height=120,scale=1,is_hdr=False)])
                environ=root/'synthetic-proc'/'71'/'environ';environ.parent.mkdir(parents=True)
                environ.write_bytes(b'GSETTINGS_BACKEND=keyfile\0XDG_CONFIG_HOME='+os.fsencode(root/'config')+b'\0')
                selected={'show-controls':None};events=[]
                trial.fresh_window=Mock(return_value=player);trial.alive=Mock(return_value=client);trial.fullscreen=Mock()
                trial.gtk_binding=Mock(return_value=dict(package='gtk4',version='4.22.5',mapped_library_sha256='b'*64))
                trial.native_protocol_drain=Mock(bind=Mock(return_value=True),snapshot=Mock(return_value=dict(
                    realized_renderer=dict(status='reported-realized',renderer='vulkan',release_acceptance=False,
                        video_widget_or_framebuffer_attested=False))))
                def command(argv,**kwargs):
                    if argv[:3]==['/usr/bin/env','GSETTINGS_BACKEND=keyfile','/usr/bin/gsettings']:
                        events.append(argv[3])
                        if argv[3]=='set':selected['show-controls']=argv[-1];return 0,'',''
                        return 0,selected['show-controls'],''
                    if argv[:3]==['mmsg','get','all-monitors']:return 0,json.dumps(monitors),''
                    if argv[:2]==['mmsg','dispatch']:return 0,'{"success":true}',''
                    if argv[0]=='grim':
                        events.append('capture')
                        def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
                        scan=b''.join(b'\0'+pixels[y*160*3:(y+1)*160*3] for y in range(120))
                        Path(argv[-1]).write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',160,120,8,2,0,0,0))
                            +chunk(b'IDAT',zlib.compress(scan))+chunk(b'IEND',b''))
                        return 0,'',''
                    if argv[0]=='ffmpeg':Path(argv[-1]).write_bytes(pixels);return 0,'',''
                    raise AssertionError('Unexpected fixture command')
                trial.cmd=Mock(side_effect=command)
                media={'path':str(fixture),'pause':False,'video-params':dict(w=160,h=120),'current-vo':'libmpv','time-pos':.7}
                endpoint=socket.socket(socket.AF_UNIX);endpoint.bind(str(trial.root/'player.sock'))
                def action(*args):events.append('bound-hide-action');selected['show-controls']='false'
                def slept(seconds):self.assertEqual(seconds,.5);events.append('settle')
                original_path=Path
                def mapped(value):return original_path(root/'synthetic-proc' if str(value)=='/proc' else value)
                try:
                    with patch.object(N,'Path',side_effect=mapped),patch.object(N,'mpv_property',side_effect=lambda path,key,pid,uid:media[key]), \
                            patch.object(N,'mpv_hide_reference_controls',side_effect=action),patch.object(N.time,'sleep',side_effect=slept):
                        value=trial.observe(fixture,expected,'c'*64)
                    self.assertEqual(value['oracle']['status'],'matched' if palette else 'unmatched')
                    self.assertEqual(value['capture_precondition']['before_visible'],state=='transition')
                    self.assertFalse(value['capture_precondition']['after_visible'])
                    self.assertTrue(value['capture_precondition']['private_config_process_bound'])
                    self.assertEqual(value['intervention'],state)
                    self.assertEqual(value['capture']['path'],'controls-trial-'+state+'/reference.png')
                    self.assertEqual(value['requested_gsk_renderer'],'unset');self.assertIsNone(value['requested_renderer_matched'])
                    self.assertFalse(value['release_acceptance']);self.assertFalse(value['rendering_cause_proven'])
                    self.assertLess(events.index('set'),events.index('bound-hide-action'))
                    self.assertLess(events.index('bound-hide-action'),events.index('settle'))
                    self.assertLess(events.index('settle'),events.index('capture'))
                finally:endpoint.close()

    def study(self,root,trials):
        fixture=root/'same-fixture';fixture.write_bytes(b'source-owned synthetic fixed fixture')
        expected=root/'expected';expected.write_bytes(N.visual_reference_frame())
        smoke=N.Smoke.__new__(N.Smoke);smoke.root=root;smoke.uid=os.getuid();smoke.stage='live'
        smoke.owned=[dict(executable='/usr/bin/celluloid',pid=11,start_ticks=1)];smoke.launches=[];smoke.finish_native_protocol=Mock()
        smoke.gates=[dict(check='open-codec-content-and-player-state',status='failed',detail='original primary failure')]
        primary=dict(oracle=dict(status='unmatched'),screenshot=dict(sha256='a'*64),capture_precondition=dict(before_visible=True,after_visible=False),
                     fixture_sha256=N.digest(fixture),expected_rgb_sha256=N.digest(expected))
        before=copy.deepcopy((smoke.gates,primary))
        with patch.object(N,'ControlsTrialSmoke',side_effect=trials) as constructor,patch.object(N,'retire_renderer_player'):
            smoke.controlled_controls_trials(fixture,expected,'b'*64,primary)
        self.assertEqual((smoke.gates,primary),before)
        return json.loads((root/'0-controls-state-trials.json').read_bytes()),constructor

    def test_actual_two_arm_glue_preserves_primary_and_fixed_order_no_extra_slots(self):
        with tempfile.TemporaryDirectory() as temporary:
            trials=[Mock(owned=[],launches=[],observe=Mock(return_value=dict(intervention=state,status='observed',
                player=dict(pid=20+i,start_ticks=2+i),oracle=dict(status='matched'),release_acceptance=False))) for i,state in enumerate(('transition','hidden'))]
            value,constructor=self.study(Path(temporary),trials)
            self.assertEqual([c.args[1] for c in constructor.call_args_list],['transition','hidden'])
            self.assertTrue(value['primary_failure_preserved']);self.assertFalse(value['release_acceptance'])
            self.assertFalse(value['rendering_cause_proven']);self.assertEqual(value['controls']['initial_controls_visible'],[True,False])
            self.assertEqual(value['controls']['diagnostic_time_bound_seconds_each'],120)
            self.assertEqual([r['status'] for r in value['trials']],['observed','observed'])
            self.assertEqual(set(p.name for p in Path(temporary).glob('0-*.json')),{'0-controls-state-trials.json'})

    def test_actual_primary_capture_still_fails_after_successful_controls_diagnostics(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);fixture=root/'fixture';fixture.write_bytes(b'source-fixed-synthetic-media')
            expected=root/'expected';expected.write_bytes(N.visual_reference_frame())
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=root;smoke.uid=os.getuid();smoke.gui_v6=True
            smoke.visual_fixture=Mock(return_value=(fixture,expected,'c'*64));smoke.trace=Mock()
            player=dict(pid=71,start_ticks=3,client_id='10',executable='/usr/bin/celluloid',executable_sha256='a'*64)
            client=dict(id=10,pid=71,x=0,y=0,width=160,height=120,monitor='synthetic-monitor',
                        is_focused=True,is_visible=True,is_fullscreen=True)
            monitors=dict(monitors=[dict(name='synthetic-monitor',x=0,y=0,width=160,height=120,scale=1,is_hdr=False)])
            smoke.fresh_window=Mock(return_value=player);smoke.alive=Mock(return_value=client)
            smoke.player_fullscreen=Mock();smoke.fullscreen_capture_pair=Mock();smoke.native_protocol_diagnostic=Mock()
            smoke.hide_reference_controls=Mock(return_value=dict(before_visible=True,after_visible=False))
            smoke.controlled_controls_trials=Mock(return_value=dict(oracle=dict(status='matched'),release_acceptance=False))
            smoke.controlled_renderer_trials=Mock()
            smoke.wait=lambda fn,*args:fn()
            def command(argv,**kwargs):
                if argv[:3]==['mmsg','get','all-monitors']:return 0,json.dumps(monitors),''
                if argv[:2]==['mmsg','dispatch']:return 0,'{"success":true}',''
                if argv[0]=='grim':
                    Path(argv[-1]).write_bytes(b'\x89PNG\r\n\x1a\n'+struct.pack('>I',13)+b'IHDR'+struct.pack('>II',160,120))
                    return 0,'',''
                if argv[0]=='ffmpeg':Path(argv[-1]).write_bytes(b'\0'*(160*120*3));return 0,'',''
                raise AssertionError('Unexpected fixture command')
            smoke.cmd=Mock(side_effect=command)
            media={'path':str(fixture),'pause':False,'video-params':dict(w=160,h=120),'current-vo':'libmpv','time-pos':0.0}
            endpoint=socket.socket(socket.AF_UNIX);endpoint.bind(str(root/'visual-reference-ipc.sock'))
            try:
                with patch.object(N,'mpv_property',side_effect=lambda path,key,pid,uid:media[key]),patch.object(N.time,'sleep') as sleep:
                    with self.assertRaisesRegex(RuntimeError,'^actual static visual fixture content unmatched; rendered-content gate remains open$'):
                        smoke.visual_media()
                sleep.assert_called_once_with(.5);smoke.controlled_controls_trials.assert_called_once()
                smoke.controlled_renderer_trials.assert_not_called()
                actual=json.loads((root/'visual-oracle.json').read_bytes())
                self.assertEqual(actual['oracle']['status'],'unmatched')
                self.assertEqual(smoke.controlled_controls_trials.call_args.args[3]['oracle'],actual['oracle'])
            finally:endpoint.close()

    def test_first_failure_still_attempts_second_fixed_error_and_duplicate_player_unknown(self):
        for failure in ('exception','reused-player'):
            with tempfile.TemporaryDirectory() as temporary:
                first=Mock(owned=[],launches=[],observe=Mock(return_value=dict(player=dict(pid=20,start_ticks=2),status='observed')))
                second=Mock(owned=[],launches=[],observe=Mock(return_value=dict(player=dict(pid=20,start_ticks=2),status='observed')))
                if failure=='exception':first.observe.side_effect=RuntimeError('private unknown error')
                value,_=self.study(Path(temporary),[first,second])
                second.observe.assert_called_once();self.assertNotIn('private unknown',json.dumps(value))
                row=value['trials'][0 if failure=='exception' else 1]
                self.assertEqual(row['status'],'unknown');self.assertEqual(row['error'],'guard-error')

    def test_unretired_first_owned_player_prevents_second_arm(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);fixture=root/'fixture';fixture.write_bytes(b'fixed');expected=root/'expected';expected.write_bytes(b'fixed')
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=root;smoke.uid=os.getuid();smoke.stage='live'
            primary_player=dict(executable='/usr/bin/celluloid',pid=11,start_ticks=1)
            smoke.owned=[primary_player];smoke.launches=[];smoke.finish_native_protocol=Mock()
            trial_player=dict(executable='/usr/bin/celluloid',pid=20,start_ticks=2)
            first=Mock(owned=[trial_player],launches=[],observe=Mock(return_value=dict(status='observed')))
            second=Mock(owned=[],launches=[],observe=Mock())
            primary=dict(oracle=dict(status='unmatched'),screenshot=dict(sha256='a'*64),capture_precondition={},
                fixture_sha256=N.digest(fixture),expected_rgb_sha256=N.digest(expected))
            def retire(player,uid):
                if player is trial_player:raise RuntimeError('private optional cleanup')
            with patch.object(N,'ControlsTrialSmoke',side_effect=[first,second]) as constructor,patch.object(N,'retire_renderer_player',side_effect=retire):
                smoke.controlled_controls_trials(fixture,expected,'b'*64,primary)
            second.observe.assert_not_called();self.assertEqual(constructor.call_count,1)
            value=json.loads((root/'0-controls-state-trials.json').read_bytes())
            self.assertFalse(value['trials'][0]['owned_trial_cleanup_completed'])
            self.assertEqual(value['trials'][1]['status'],'unrun');self.assertEqual(value['preparation_error'],'guard-error')
            self.assertNotIn('private optional',json.dumps(value));self.assertTrue(value['primary_failure_preserved'])

    def test_new_receipt_cannot_follow_symlink_overwrite_or_exceed_old_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);sentinel=root/'foreign';sentinel.write_bytes(b'unchanged')
            path=root/'0-controls-state-trials.json';path.symlink_to(sentinel)
            with self.assertRaises(OSError):N.write_controls_receipt(root,os.getuid(),{})
            self.assertEqual(sentinel.read_bytes(),b'unchanged');path.unlink()
            N.write_controls_receipt(root,os.getuid(),dict(release_acceptance=False));before=path.read_bytes()
            with self.assertRaises(OSError):N.write_controls_receipt(root,os.getuid(),{})
            self.assertEqual(path.read_bytes(),before)
            with self.assertRaises(RuntimeError):N.write_controls_receipt(root,os.getuid(),{'test':'x'*(512*1024)})

    def test_finite_public_inventory_swaps_only_three_optional_slots(self):
        spec=importlib.util.spec_from_file_location('controls_inventory_guest',HERE/'guest-check-native-v6.py')
        guest=importlib.util.module_from_spec(spec);spec.loader.exec_module(guest)
        new=guest.NATIVE_PUBLIC_EVIDENCE_FILES
        old=restore_controls_guest((HERE/'guest-check-native-v6.py').read_text())
        env={};exec(compile(old,'strict-rolled-back-source','exec'),env)
        removed={'0-controlled-renderer-trials.json','renderer-trial-default/reference.png','renderer-trial-gl/reference.png'}
        added={'0-controls-state-trials.json','controls-trial-transition/reference.png','controls-trial-hidden/reference.png'}
        self.assertEqual(set(new)-set(env['NATIVE_PUBLIC_EVIDENCE_FILES']),added)
        self.assertEqual(set(env['NATIVE_PUBLIC_EVIDENCE_FILES'])-set(new),removed)
        self.assertEqual(len(new),len(env['NATIVE_PUBLIC_EVIDENCE_FILES']))
        for name in added:self.assertTrue(guest.native_public_evidence_member(name))
        for name in removed|{'controls-trial-private/reference.png','controls-trial-transition/private.png'}:
            with self.assertRaises(RuntimeError):guest.native_public_evidence_member(name)

    def test_actual_emitted_guest_begin_matches_consumer_and_stale_identities_reject(self):
        guest_path=HERE/'guest-check-native-v6.py';raw=guest_path.read_text()
        spec=importlib.util.spec_from_file_location('controls_guest_begin',guest_path)
        guest=importlib.util.module_from_spec(spec);spec.loader.exec_module(guest)
        main=next(n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name=='main')
        first_try=next(i for i,n in enumerate(main.body) if isinstance(n,ast.Try))
        prefix=ast.Module(body=main.body[:first_try],type_ignores=[])
        output=io.StringIO()
        with patch('sys.argv',['labelled-source-fixture','live']),contextlib.redirect_stdout(output):
            exec(compile(ast.fix_missing_locations(prefix),str(guest_path),'exec'),guest.__dict__)
        begin=output.getvalue().strip()
        spec=importlib.util.spec_from_file_location('controls_consumer',HERE/'evidence.py')
        evidence=importlib.util.module_from_spec(spec);spec.loader.exec_module(evidence)
        end='ARCTIC-NATIVE-RUNNER-END '+json.dumps(dict(stage='live',status='failed',error='source fixture',evidence_export_complete=False,release_acceptance=False))
        _,identity,terminal=evidence.native_block(begin+'\n'+end+'\n','live')
        self.assertEqual(identity['native_source_sha256'],hashlib.sha256((HERE/'native_smoke.py').read_bytes()).hexdigest())
        self.assertEqual(identity['checker_sha256'],hashlib.sha256(guest_path.read_bytes()).hexdigest())
        self.assertEqual(terminal['status'],'failed')
        for field,old in (('native_source_sha256',BASE_NATIVE_SHA),('checker_sha256',BASE_GUEST_SHA)):
            stale=dict(identity,**{field:old})
            with self.assertRaises(RuntimeError):evidence.native_block('ARCTIC-NATIVE-RUNNER-BEGIN '+json.dumps(stale)+'\n'+end+'\n','live')


if __name__=='__main__':unittest.main()
