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
    def test_real_source_tree_absence_has_no_prior_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'home/liveuser/.bashrc.d';path.mkdir(parents=True);(path/'owned.sh').write_bytes(b'true\n')
            initial=A.source_set(root);tree=next(v for v in initial['trees'] if v['path']=='/home/liveuser/.bashrc.d');self.assertEqual(tree['status'],'listed')
            (path/'owned.sh').unlink();path.rmdir()
            final=A.source_set(root)
            for tree in final['trees']:
                if tree['status']=='absent':self.assertEqual(set(tree),{'path','status'})
            self.assertEqual(next(v for v in final['trees'] if v['path']=='/home/liveuser/.bashrc.d'),dict(path='/home/liveuser/.bashrc.d',status='absent'))
    def test_real_fixed_target_hardlink_is_recorded_without_symlink_substitution(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.profile_fixture(root);first=root/A.PROFILE_TARGETS[0][2].lstrip('/');second=root/A.PROFILE_TARGETS[1][2].lstrip('/')
            second.unlink();os.link(first,second)
            proofs=A.profile_target_proofs(root,os.getuid(),os.getgid());self.assertIsNone(proofs[0]['target_alias_of'])
            self.assertEqual(proofs[1]['target_alias_of'],A.PROFILE_TARGETS[0][2]);self.assertEqual(proofs[0]['target_before'][:2],proofs[1]['target_before'][:2])
    def profile_fixture(self,root):
        for node,literal,target in A.PROFILE_TARGETS:
            p=root/node.lstrip('/');t=root/target.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True);t.parent.mkdir(parents=True,exist_ok=True)
            t.write_bytes(b'owned target\n');t.chmod(0o600);p.symlink_to(literal)
    def test_real_literal_node_brackets_and_independent_target_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.profile_fixture(root);proof=A.profile_target_proofs(root,os.getuid(),os.getgid())
            self.assertEqual(len(proof),2)
            for p in proof:
                self.assertEqual(p['node_before'],p['node_after']);self.assertEqual(p['target_before'],p['target_after'])
                self.assertEqual(p['target_sha256'],A.sha(b'owned target\n'))
            self.assertEqual(proof,A.profile_target_proofs(root,os.getuid(),os.getgid()))
            result=A.source_set(root)
            self.assertEqual({v['path'] for v in result['files']}>=set(A.FOLLOWUP_FILES),True)
            self.assertEqual({v['path'] for v in result['trees']}>=set(A.FOLLOWUP_TREES),True)
    def test_real_profile_literal_dangling_target_parent_alias_and_writable_refuse(self):
        for kind in ('literal','missing-node','dangling-target','target-link','parent-alias','writable'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);self.profile_fixture(root);node,literal,target=A.PROFILE_TARGETS[0];p=root/node.lstrip('/');t=root/target.lstrip('/')
                if kind=='literal':p.unlink();p.symlink_to('../../different')
                elif kind=='missing-node':p.unlink()
                elif kind=='dangling-target':t.unlink()
                elif kind=='target-link':t.unlink();t.symlink_to(root/'missing')
                elif kind=='parent-alias':
                    original=t.parent;other=original.with_name('owned-alternate');original.rename(other);original.symlink_to(other)
                elif kind=='writable':t.chmod(0o666)
                with self.assertRaises((RuntimeError,FileNotFoundError)):A.profile_target_proofs(root,os.getuid(),os.getgid())
    def test_real_node_and_target_substitution_inside_bracket_refuse(self):
        for kind in ('node','target'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);self.profile_fixture(root);node,literal,target=A.PROFILE_TARGETS[0];p=root/node.lstrip('/');t=root/target.lstrip('/');real=A.source_file;changed=False
                def capture(path):
                    nonlocal changed
                    value=real(path)
                    if Path(path)==t and not changed:
                        changed=True
                        if kind=='node':p.unlink();p.symlink_to(literal)
                        else:t.write_bytes(b'changed target\n')
                    return value
                with patch.object(A,'source_file',side_effect=capture),self.assertRaisesRegex(RuntimeError,'identity changed'):
                    A.profile_target_proofs(root,os.getuid(),os.getgid())
    def test_conditional_locale_completion_prompt_helper_paths_and_caps(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/'home/liveuser/.bashrc.d';p.mkdir(parents=True);(p/'one.sh').write_text('owned fixture\n')
            completion=root/'usr/share/bash-completion/bash_completion';completion.parent.mkdir(parents=True);completion.write_bytes(b'x'*(A.MAX_FILE+1))
            result=A.source_set(root);by={v['path']:v for v in result['files']}
            self.assertEqual(by['/home/liveuser/.bashrc.d/one.sh']['status'],'read-raw')
            self.assertEqual(by['/usr/share/bash-completion/bash_completion']['status'],'unavailable')
            self.assertEqual(by['/etc/locale.conf']['status'],'absent');self.assertEqual(by['/etc/sysconfig/bash-prompt-xterm']['status'],'absent')
            alias=root/'etc/debuginfod';alias.parent.mkdir(parents=True);alias.symlink_to(root/'absent')
            with self.assertRaisesRegex(RuntimeError,'directory type/link'):A.source_set(root)
    def test_effective_unit_raw_fixed_scope_no_normalization(self):
        value=b'FragmentPath=/usr/lib/systemd/system/sddm.service\nDropInPaths=/usr/lib/systemd/system/service.d/10-timeout-abort.conf\nEnvironmentFiles=/etc/sysconfig/sddm (ignore_errors=yes)\n'
        self.assertEqual(A.effective_unit(value),value)
        for altered in (value+b'DropInPaths=/extra\n',value.replace(b'/etc/sysconfig/sddm',b'/other'),value.decode(),b'x'*(1024*1024+1)):
            with self.subTest(kind=type(altered)),self.assertRaises(RuntimeError):A.effective_unit(altered)
        for uid,gid in ((False,0),(0,False),(-1,0)):
            with self.assertRaises(RuntimeError):A.profile_target_proofs(expected_uid=uid,expected_gid=gid)
    def test_present_optional_source_vanishing_after_lstat_is_not_absent(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'optional';p.write_bytes(b'owned present source')
            with patch.object(A.os,'open',side_effect=FileNotFoundError('owned disappearance')):
                value=A.source_file(p)
                self.assertEqual(value['status'],'unavailable');self.assertIn('after lstat',value['error'])
    def test_collect_actual_function_effective_unit_and_profile_changes_are_fatal(self):
        unit=b'FragmentPath=/usr/lib/systemd/system/sddm.service\nDropInPaths=/usr/lib/systemd/system/service.d/10-timeout-abort.conf\nEnvironmentFiles=/etc/sysconfig/sddm (ignore_errors=yes)\nUser=\n'
        for kind in ('stable','unit-change','profile-change'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp:
                user=types.SimpleNamespace(pw_uid=1000,pw_dir='/home/liveuser',pw_shell='/bin/bash')
                proofs=dict(mango=dict(pid=1,cmdline=['mango'],executable_sha256=A.MANGO_SHA),quickshell=dict(pid=2))
                class Original:
                    count=0
                    def desktop(self):return user,proofs,{'SHELL':'/bin/bash'}
                    def environment(self,pid):return {'SHELL':'/bin/bash'}
                    def process(self,pid):return proofs['mango' if pid==1 else 'quickshell']
                    def security(self,root,label):return dict(selinux='Enforcing',avc_records=[],journal_total_bytes=0,journal_retained_bytes=0,scope='HOST FIXTURE ONLY')
                    def execute(self,argv,timeout):
                        if argv==A.UNIT_ARGV:
                            self.count+=1;return unit+(b'User=changed\n' if kind=='unit-change' and self.count==2 else b'')
                        self.assert_allowed(argv);return b'HOST FIXTURE ONLY\n'
                    def assert_allowed(self,argv):
                        if argv[0] not in ('uname','/usr/lib/systemd/systemd','rpm'):raise AssertionError(argv)
                links=[dict(fixed_target=p[2],target_sha256='a'*64) for p in A.PROFILE_TARGETS]
                sources=dict(files=[dict(path=p[2],status='read-raw',sha256='a'*64) for p in A.PROFILE_TARGETS],trees=[],raw_source_bytes=0)
                after=json.loads(json.dumps(links))
                if kind=='profile-change':after[0]['target_sha256']='b'*64
                read=Path.read_text
                def source_text(path,*args,**kwargs):
                    if str(path)=='/proc/sys/kernel/random/boot_id':return '12345678-1234-1234-1234-1234567890ab'
                    if str(path)=='/proc/cmdline':return 'HOST FIXTURE ONLY'
                    return read(path,*args,**kwargs)
                with patch.object(A,'source_set',return_value=sources),patch.object(A,'profile_target_proofs',side_effect=[links,after]),patch.object(A,'binary',return_value=dict(scope='HOST FIXTURE ONLY')),patch.object(A.Path,'read_text',source_text):
                    root=Path(temp)
                    if kind=='stable':
                        report=A.collect(Original(),root);self.assertFalse(report['missing_chain_followup']['complete_startup_chain'])
                        self.assertEqual((root/'sddm-effective-unit.txt').read_bytes(),(root/'sddm-effective-unit-after.txt').read_bytes())
                    else:
                        with self.assertRaisesRegex(RuntimeError,'observations changed'):A.collect(Original(),root)
                        self.assertFalse((root/'report.json').exists())
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
