"""Host controls only. No guest, GUI, network, package installs or dispatch."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import pwd
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('native_smoke',HERE/'native_smoke.py')
s=importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class Controls(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='arctic-functional-host-controls-')
        self.root=Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def fake_proc(self,pid=99001,exe='native',ticks=100):
        directory=self.root/str(pid)
        directory.mkdir()
        binary=self.root/exe
        binary.write_bytes(b'\x7fELF fixture only; not executed')
        (directory/'exe').symlink_to(binary)
        # State is field 3; starttime is field 22, parsed index 19 after comm.
        fields=['S']+['0']*18+[str(ticks)]+['0']*5
        (directory/'stat').write_text(str(pid)+' (test with spaces) '+' '.join(fields))
        return binary,dict(id=1,pid=pid,is_xwayland=False,is_visible=True,width=160,height=120)

    def test_import_and_cli_guard_do_not_dispatch_on_host(self):
        result=subprocess.run(['python3',str(HERE/'native_smoke.py'),'--stage','live','--disposable-guest'],
            capture_output=True,text=True,timeout=5)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('reviewed /run/t guest bundle',result.stderr)
        with patch.object(s,'execute',side_effect=AssertionError('no command allowed')):
            with self.assertRaisesRegex(RuntimeError,'explicit disposable'):
                s.guest_guard('live',False)

    def test_full_tree_oracle_detects_modified_extra_and_symlink_members(self):
        original=self.root/'original';original.mkdir();(original/'payload').write_bytes(b'expected')
        expected=s.tree_hashes(original)
        target=self.root/'target';shutil.copytree(original,target)
        self.assertEqual(s.verify_tree(expected,target),expected)
        (target/'payload').write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError,'content mismatch'):s.verify_tree(expected,target)
        (target/'payload').write_bytes(b'expected');(target/'extra').write_bytes(b'not allowed')
        with self.assertRaisesRegex(RuntimeError,'content mismatch'):s.verify_tree(expected,target)
        (target/'extra').unlink();(target/'link').symlink_to(original/'payload')
        with self.assertRaisesRegex(RuntimeError,'non-regular'):s.verify_tree(expected,target)

    def test_directory_members_extra_missing_and_type_changes_fail(self):
        original=self.root/'original';original.mkdir();(original/'payload').write_bytes(b'expected')
        (original/'empty directory'/'nested empty').mkdir(parents=True)
        expected=s.tree_hashes(original)
        self.assertEqual(expected['empty directory'],{'type':'directory'})
        self.assertEqual(expected['empty directory/nested empty'],{'type':'directory'})
        self.assertEqual(expected['payload']['type'],'file')
        target=self.root/'target';shutil.copytree(original,target)
        self.assertEqual(s.verify_tree(expected,target),expected)
        (target/'extra empty directory').mkdir()
        with self.assertRaisesRegex(RuntimeError,'content mismatch'):s.verify_tree(expected,target)
        (target/'extra empty directory').rmdir();(target/'empty directory'/'nested empty').rmdir()
        with self.assertRaisesRegex(RuntimeError,'content mismatch'):s.verify_tree(expected,target)
        (target/'empty directory').rmdir();(target/'empty directory').write_bytes(b'')
        with self.assertRaisesRegex(RuntimeError,'content mismatch'):s.verify_tree(expected,target)

    def test_implicit_archive_root_dot_normalized_but_named_wrapper_rejected(self):
        original=self.root/'original';original.mkdir();(original/'payload').write_bytes(b'expected')
        (original/'empty directory').mkdir()
        expected=s.tree_hashes(original)
        self.assertEqual(s.tree_hashes(original/'.'),expected)
        self.assertNotIn('.',expected)
        target=self.root/'target';shutil.copytree(original,target)
        self.assertEqual(s.verify_tree(expected,target/'.'),expected)
        wrapped=self.root/'wrapped';wrapped.mkdir();shutil.copytree(original,wrapped/'named wrapper')
        with self.assertRaisesRegex(RuntimeError,'content mismatch'):s.verify_tree(expected,wrapped)

    def test_window_pid_owner_stale_binary_and_wayland_controls(self):
        binary,client=self.fake_proc()
        proof=s.window_proof(client,os.getuid(),binary,set(),proc_root=self.root)
        self.assertEqual(proof['start_ticks'],100)
        for bad,before,uid,expected,native in (
            (dict(client,pid=True),set(),os.getuid(),binary,True),
            (client,{(99001,100)},os.getuid(),binary,True),
            (client,set(),os.getuid()+1,binary,True),
            (dict(client,is_visible=False),set(),os.getuid(),binary,True),
            (dict(client,is_xwayland=True),set(),os.getuid(),binary,True),
        ):
            with self.assertRaises(RuntimeError):s.window_proof(bad,uid,expected,before,native,proc_root=self.root)
        other=self.root/'other';other.write_bytes(b'\x7fELF other')
        with self.assertRaisesRegex(RuntimeError,'different executable'):
            s.window_proof(client,os.getuid(),other,set(),proc_root=self.root)
        proof=s.window_proof(dict(client,is_xwayland=True),os.getuid(),binary,set(),native=False,proc_root=self.root)
        self.assertTrue(proof['is_xwayland'])

    def test_pid_recycle_cleanup_never_signals_new_or_unproved_process(self):
        smoke=s.Smoke.__new__(s.Smoke);smoke.uid=os.getuid();smoke.root=self.root
        smoke.active_gate=None;smoke.trace_bytes=smoke.trace_omitted=smoke.client_observations=0
        smoke.owned=[dict(pid=99001,start_ticks=100,executable='/usr/bin/foot')]
        smoke.launches=[];smoke.copied={}
        with patch.object(s,'identity',return_value=dict(pid=99001,start_ticks=101,executable='/usr/bin/foot')):
            with patch.object(s.os,'pidfd_open',return_value=1234),patch.object(s.os,'close'):
                with patch.object(s.signal,'pidfd_send_signal') as kill:
                    smoke.cleanup();kill.assert_not_called()

    def test_security_enforcing_avc_loss_and_disabled_telemetry_controls(self):
        before=dict(selinux='Enforcing',audit=dict(enabled=1,lost=0))
        self.assertEqual(s.verify_security(before,copy.deepcopy(before),'normal startup')['observed_new_avcs'],0)
        for after,text in (
            (dict(selinux='Permissive',audit=before['audit']),''),
            (dict(selinux='Enforcing',audit=dict(enabled=0,lost=0)),''),
            (dict(selinux='Enforcing',audit=dict(enabled=1,lost=1)),''),
            (copy.deepcopy(before),'kernel: avc: denied { read } for app=featherpad'),
            (copy.deepcopy(before),'type=USER_AVC msg=audit(42): denied'),
        ):
            with self.assertRaises(RuntimeError):s.verify_security(before,after,text)
        disabled=dict(selinux='Enforcing',audit=dict(enabled=0,lost=0))
        self.assertFalse(s.verify_security(disabled,copy.deepcopy(disabled),'')['audit_enabled'])
        with self.assertRaises(RuntimeError):s.parse_audit_status('enabled 1\n')

    def test_audit_file_only_avc_and_rotation_are_not_missed(self):
        interval=s.SecurityInterval.__new__(s.SecurityInterval)
        interval.before=dict(selinux='Enforcing',audit=dict(enabled=1,lost=0))
        interval.cursor='cursor';interval.audit_file=self.root/'audit.log'
        interval.audit_file.write_text('old record\n')
        info=interval.audit_file.stat();interval.audit_offset=(info.st_dev,info.st_ino,info.st_size)
        with patch.object(interval,'state',return_value=copy.deepcopy(interval.before)):
            with patch.object(s,'execute',return_value=(0,json.dumps(dict(MESSAGE='normal')),'')):
                with interval.audit_file.open('a') as f:f.write('type=AVC denied\n')
                with self.assertRaisesRegex(RuntimeError,'new AVC'):interval.finish()
                old=self.root/'old.log';interval.audit_file.rename(old);interval.audit_file.write_text('replacement')
                with self.assertRaisesRegex(RuntimeError,'rotated/truncated'):interval.finish()

    def good_samples(self):
        return [dict(path='/tmp/fixture.mkv',**{'time-pos':v,'pause':False,'current-vo':'libmpv',
            'current-ao':'pipewire','video-params':dict(w=160,h=120),
            'audio-params':dict(samplerate=48000),'audio-out-params':dict(samplerate=48000)}) for v in (.2,.6)]

    def test_player_requires_right_file_renderer_audio_and_advancing_clock(self):
        s.validate_player_samples(self.good_samples(),'/tmp/fixture.mkv')
        for field,value in (('path','/tmp/other.mkv'),('pause',True),('current-vo','null'),
                            ('current-ao','null'),('audio-out-params',None),('time-pos',.2),
                            ('time-pos',True),('time-pos',float('nan')),('time-pos',float('inf'))):
            samples=self.good_samples()
            for item in samples:item[field]=value
            with self.assertRaises(RuntimeError):s.validate_player_samples(samples,'/tmp/fixture.mkv')

    def test_player_ipc_rejects_different_peer_pid(self):
        path=self.root/'ipc.sock'
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
            server.bind(str(path));server.listen(1)
            def accept():
                peer,_=server.accept();peer.close()
            thread=threading.Thread(target=accept);thread.start()
            with self.assertRaisesRegex(RuntimeError,'different process/user'):
                s.mpv_property(path,'path',os.getpid()+1,os.getuid())
            thread.join(3);self.assertFalse(thread.is_alive())

    def test_nonzero_command_fails_without_shell(self):
        with self.assertRaisesRegex(RuntimeError,'command failed'):
            s.execute(['python3','-c','raise SystemExit(4)'])

    def host_smoke(self):
        smoke=s.Smoke.__new__(s.Smoke)
        smoke.root=self.root;smoke.uid=os.getuid();smoke.user=pwd.getpwuid(os.getuid())
        smoke.prefix=[];smoke.original_prefix=[];smoke.steps=[]
        smoke.active_gate=None;smoke.trace_bytes=smoke.trace_omitted=smoke.client_observations=0
        return smoke

    @unittest.skipUnless(all(shutil.which(x) for x in ('zip','unzip','tar','gzip','bzip2','xz','zstd')),
                         'host lacks some helpers; guest tests remain mandatory')
    def test_actual_host_helpers_roundtrip_nested_unicode_binary_content(self):
        result=self.host_smoke().archives(('zip','tar','tar.gz','tar.bz2','tar.xz','tar.zst',
                                         'gzip','bzip2','xz','zstd'))
        self.assertEqual(len(result['roundtrips']),10)

    @unittest.skipUnless(shutil.which('7z') or shutil.which('7zz'),'host lacks 7zip; guest test remains mandatory')
    def test_actual_host_7zip_encryption_and_wrong_password(self):
        self.assertEqual(len(self.host_smoke().archives(('7z','7z-encrypted'))['roundtrips']),2)

    @unittest.skipUnless(shutil.which('cpio'),'host lacks cpio; guest test remains mandatory')
    def test_actual_host_cpio_roundtrip(self):
        self.assertEqual(len(self.host_smoke().archives(('cpio',))['roundtrips']),1)

    @unittest.skipUnless(shutil.which('ffmpeg'),'host lacks ffmpeg; guest test remains mandatory')
    def test_actual_host_ffv1_and_pcm_lossless_content_roundtrip(self):
        fixture,decoder=self.host_smoke().media_fixture()
        self.assertGreater(fixture.stat().st_size,0)
        self.assertEqual(len(decoder['video_sha256']),64)
        self.assertEqual(len(decoder['audio_sha256']),64)

    @unittest.skipUnless(shutil.which('ffmpeg'),'host lacks ffmpeg; guest visual fixture remains mandatory')
    def test_actual_static_ffv1_rgb_reference_matches_known_palette(self):
        fixture,reference,source_hash=self.host_smoke().visual_fixture()
        self.assertTrue(fixture.is_file());self.assertEqual(len(source_hash),64)
        result=s.evaluate_reference_rgb(reference.read_bytes(),160,120,reference.read_bytes())
        self.assertEqual(result['status'],'matched')


if __name__=='__main__':unittest.main(verbosity=2)
