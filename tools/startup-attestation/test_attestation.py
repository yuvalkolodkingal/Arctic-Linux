"""Owned file/shell/transport fixtures only; no guest/root/CD execution."""
import base64
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import shutil
import types
import unittest
from unittest.mock import patch
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('startup_attester',HERE/'attest-startup-v1.py');A=importlib.util.module_from_spec(spec);spec.loader.exec_module(A)

class AttestationTests(unittest.TestCase):
    def test_real_raw_file_hash_mode_uid_gid_and_absence(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'input';data=b'profile\x00raw\xff\n';p.write_bytes(data);p.chmod(0o640)
            v=A.source_file(p);self.assertEqual(v['status'],'read-raw');self.assertEqual(base64.b64decode(v['base64']),data)
            self.assertEqual((v['uid'],v['gid'],v['mode'],v['sha256']),(os.getuid(),os.getgid(),0o640,A.sha(data)))
            self.assertEqual(A.source_file(Path(temp)/'absent')['status'],'absent')
    def test_symlink_directory_parent_and_oversize_are_not_read(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'data';p.write_bytes(b'x');link=Path(temp)/'link';link.symlink_to(p)
            self.assertEqual(A.source_file(link)['status'],'symlink-unread')
            directory=Path(temp)/'directory';directory.mkdir();alias=Path(temp)/'alias';alias.symlink_to(directory)
            file=directory/'inside';file.write_bytes(b'data')
            self.assertEqual(A.source_file(alias/'inside')['status'],'unavailable')
            self.assertEqual(A.source_file(directory)['status'],'unavailable')
            p.write_bytes(b'x'*(A.MAX_FILE+1));value=A.source_file(p);self.assertEqual(value['status'],'unavailable');self.assertNotIn('base64',value)
    def test_identity_mutation_and_permission_failure_are_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'data';p.write_bytes(b'x')
            with patch.object(A.os,'open',side_effect=PermissionError('owned fixture')):
                self.assertEqual(A.source_file(p)['status'],'unavailable')
            real=A.os.fstat
            def changed(fd):
                v=real(fd);fields={k:getattr(v,k) for k in ('st_dev','st_ino','st_uid','st_gid','st_mode','st_size','st_mtime_ns','st_ctime_ns')};fields['st_ino']+=1
                return types.SimpleNamespace(**fields)
            with patch.object(A.os,'fstat',side_effect=changed):
                v=A.source_file(p);self.assertEqual(v['status'],'unavailable');self.assertIn('identity changed',v['error'])
    def test_fish_actual_shell_search_inputs_and_unsupported_chain(self):
        user=types.SimpleNamespace(pw_uid=1000,pw_dir='/home/liveuser',pw_shell='/usr/bin/fish')
        chain=A.selected_chain(user,{'SHELL':'/usr/bin/fish'})
        self.assertIn('/home/liveuser/.config/fish/config.fish',chain['extra_files']);self.assertIn('/usr/share/fish/functions',chain['directories'])
        self.assertIn('/home/liveuser/.config/fish/config.local.fish',chain['extra_files'])
        self.assertIn('/nix/var/nix/profiles/default/etc/profile.d/nix-daemon.fish',chain['extra_files'])
        self.assertFalse(chain['independently_reviewed_complete_chain'])
        for shell,environment in [('/usr/bin/zsh',{'SHELL':'/usr/bin/zsh'}),('/usr/bin/fish',{'SHELL':'/usr/bin/bash'}),('/usr/bin/fish',{'SHELL':'/usr/bin/fish','XDG_CONFIG_HOME':'/elsewhere'})]:
            user.pw_shell=shell
            with self.subTest(shell=shell,environment=environment),self.assertRaises(RuntimeError):A.selected_chain(user,environment)
    def test_real_source_directory_lists_and_count_caps(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/'etc/profile.d';p.mkdir(parents=True);(p/'one.sh').write_text('true\n')
            result=A.source_set(root);item=next(v for v in result['files'] if v['path']=='/etc/profile.d/one.sh');self.assertEqual(item['status'],'read-raw')
            with patch.object(A,'MAX_SOURCES',1),self.assertRaises(RuntimeError):A.source_set(root)
            alias=root/'etc/sddm.conf.d';alias.symlink_to(p)
            with self.assertRaisesRegex(RuntimeError,'type/link'):A.source_set(root)
    def test_declared_nix_parent_link_remains_explicit_incomplete_chain(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/'nix/var/nix/profiles';p.mkdir(parents=True)
            store=root/'nix/store/profile/etc/profile.d';store.mkdir(parents=True);(store/'nix-daemon.fish').write_text('true\n')
            (p/'default').symlink_to(root/'nix/store/profile')
            user=types.SimpleNamespace(pw_uid=1000,pw_dir='/home/liveuser',pw_shell='/usr/bin/fish')
            result=A.source_set(root,A.selected_chain(user,{'SHELL':'/usr/bin/fish'}))
            obstacle=next(v for v in A.chain_obstacles(result) if v['path'].endswith('/nix-daemon.fish'))
            self.assertEqual(obstacle['status'],'unavailable');self.assertIn('parent symlink',obstacle['error'])
    def test_transport_preserves_only_bounded_owned_raw_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'report.json').write_text('{}');(root/'source.txt').write_bytes(b'raw\x00\xff')
            stream=io.StringIO()
            with contextlib.redirect_stdout(stream):A.transport(root,{})
            lines=stream.getvalue().splitlines();names=[line.split(' ',1)[0] for line in lines]
            self.assertEqual(names[:2],['ARCTIC-ATTEST-REPORT','ARCTIC-ATTEST-MANIFEST']);self.assertTrue(all(v=='ARCTIC-ATTEST-CHUNK' for v in names[2:]))
            (root/'bad').symlink_to(root/'report.json')
            with self.assertRaises(RuntimeError),contextlib.redirect_stdout(io.StringIO()):A.transport(root,{})
    def test_main_refuses_host_before_output_temp_or_commands(self):
        with patch.object(A.os,'geteuid',return_value=1000),patch.object(A.tempfile,'mkdtemp',side_effect=AssertionError('No write')):
            with contextlib.redirect_stdout(io.StringIO()) as out,self.assertRaises(SystemExit):A.main()
            end=json.loads(out.getvalue().splitlines()[-1].split(' ',1)[1]);self.assertEqual(end['status'],'failed');self.assertIn('root test-CD',end['error'])
    def test_real_read_atime_is_not_content_identity_change(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'old-atime';p.write_bytes(b'unchanged');os.utime(p,ns=(1,p.stat().st_mtime_ns))
            before=p.stat();value=A.source_file(p);after=p.stat()
            self.assertEqual(A.stable_stat(before),A.stable_stat(after));self.assertGreater(after.st_atime_ns,before.st_atime_ns)
            self.assertEqual(value['status'],'read-raw');self.assertEqual(base64.b64decode(value['base64']),b'unchanged')
    def test_real_elf_read_atime_and_default_root_owner_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'owned-elf';shutil.copyfile(Path(sys.executable).resolve(),p);p.chmod(0o755);os.utime(p,ns=(1,p.stat().st_mtime_ns))
            before=p.stat();value=A.binary(p,expected_uid=os.getuid());after=p.stat()
            self.assertEqual(A.stable_stat(before),A.stable_stat(after));self.assertGreater(after.st_atime_ns,before.st_atime_ns)
            self.assertEqual(value['bytes'],p.stat().st_size);self.assertEqual(value['sha256'],A.sha(p.read_bytes()))
            with self.assertRaises(RuntimeError):A.binary(p,expected_uid=True)
            if os.getuid()!=0:
                with self.assertRaisesRegex(RuntimeError,'owner'):A.binary(p)
    def test_dangling_startup_directory_link_is_not_absent(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'etc').mkdir();(root/'etc/profile.d').symlink_to(root/'missing-target')
            with self.assertRaisesRegex(RuntimeError,'directory type/link'):A.source_set(root)

if __name__=='__main__':unittest.main(verbosity=2)
