"""Owned fixed stderr facts and original constructor/cleanup identity; no VM."""
import ast
import contextlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_host_diagnostics import DRIVER, ROOT, SHELL, driver_functions, r

BASE='222dc0f5a758d7682b192c3e035aaad450a22e88'
HELPERS={'dictation_qemu_startup','dictation_acquire_vm'}
FATAL=b"qemu-system-x86_64: Host doesn't support requested features\n"
TCG=b"qemu-system-x86_64: TCG doesn't support requested features\n"
SPEC=b"qemu-system-x86_64: warning: host doesn't support requested feature: CPUID[eax=07h,ecx=00h].EDX.spec-ctrl [bit 26]\n"
FLOOR=b"qemu-system-x86_64: warning: host doesn't support requested feature: CPUID[eax=01h].ECX.sse4.2 [bit 20]\n"

class QMPError(Exception):pass
class PrivateError(Exception):
    def __str__(self):raise AssertionError('private exception formatted')
    def __repr__(self):raise AssertionError('private exception formatted')

def diagnostic_env(root, token='a'*32, vm=None):
    return driver_functions(HELPERS|{'dictation_host_stage'}, {'E':{'ARCTIC_DICTATION_HOST_TOKEN':token},
        'out':str(root),'os':os,'time':time,'vmtest':SimpleNamespace(VM=vm or Mock(),QMPError=QMPError)})

def projected(output):
    prefix='ARCTIC-DICTATION-HOST-STAGE '+'a'*32+' '
    lines=output.splitlines()
    assert all(line.startswith(prefix) for line in lines)
    return [line[len(prefix):] for line in lines]

class StartupDiagnostics(unittest.TestCase):
    def observe(self,root,data,error=None,token='a'*32,started=None):
        if data is not None:(root/'qemu-install.log').write_bytes(data)
        env=diagnostic_env(root,token);out=io.StringIO()
        if started is None:started=1
        with contextlib.redirect_stdout(out):env['dictation_qemu_startup']('install',started,error or SystemExit('qemu exited: see qemu-install.log'))
        return projected(out.getvalue())

    def test_complete_owned_fresh_only_spec_ctrl_is_distinct_from_other_host_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.assertEqual(self.observe(root,SPEC+FATAL),['vm-acquire-qemu-exited','vm-acquire-enforce-host-unavailable','vm-acquire-enforce-only-spec-ctrl'])
            self.assertEqual(self.observe(root,SPEC+FLOOR+FATAL),['vm-acquire-qemu-exited','vm-acquire-enforce-host-unavailable','vm-acquire-enforce-floor-unavailable'])
            self.assertEqual(self.observe(root,SPEC+b'private unrelated line\n'+FATAL),['vm-acquire-qemu-exited','vm-acquire-enforce-host-unavailable'])
            self.assertEqual(self.observe(root,FATAL),['vm-acquire-qemu-exited','vm-acquire-enforce-host-unavailable'])
            self.assertEqual(self.observe(root,TCG),['vm-acquire-qemu-exited','vm-acquire-enforce-tcg-unavailable'])

    def test_unknown_truncated_crlf_prefixed_or_altered_literals_are_unobserved(self):
        values=[b'private argv/audio/transcript\n',SPEC,SPEC+FATAL[:-1],(SPEC+FATAL).replace(b'\n',b'\r\n'),
                b'guest '+SPEC+b'guest '+FATAL,b'prefix '+FATAL,SPEC+FATAL.replace(b'Host',b'host'),
                b'ARCTIC-DICTATION-HOST-STAGE '+'a'.encode()*32+b' vm-acquire-enforce-only-spec-ctrl\n',
                b'\xff private\n']
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for value in values:
                with self.subTest(case=len(value)):
                    self.assertEqual(self.observe(root,value),['vm-acquire-qemu-exited','vm-acquire-stderr-unobserved'])

    def test_private_exception_args_subclasses_and_wrong_source_exit_never_classify_stderr(self):
        class PrivateStr(str):
            def __str__(self):raise AssertionError('private string formatted')
            def __repr__(self):raise AssertionError('private string formatted')
        class PrivateExit(SystemExit):
            @property
            def args(self):raise AssertionError('private getter called')
        errors=[(PrivateError('private'),'vm-acquire-other-error'),(PrivateExit('private'),'vm-acquire-other-error'),
                (SystemExit(PrivateStr('qemu exited: see qemu-install.log')),'vm-acquire-system-exit'),
                (SystemExit('qemu exited: see private.log'),'vm-acquire-system-exit'),
                (SystemExit('qemu exited: see qemu-boot.log'),'vm-acquire-system-exit'),
                (SystemExit('no QMP socket'),'vm-acquire-no-qmp'),(QMPError('private'),'vm-acquire-qmp-error'),
                (FileNotFoundError('private'),'vm-acquire-file-missing'),(PermissionError('private'),'vm-acquire-permission-error'),
                (OSError('private'),'vm-acquire-os-error'),(KeyboardInterrupt('private'),'vm-acquire-keyboard-interrupt'),
                (json.JSONDecodeError('private','private',0),'vm-acquire-json-error')]
        with tempfile.TemporaryDirectory() as tmp:
            for error,code in errors:
                with self.subTest(code=code):self.assertEqual(self.observe(Path(tmp),SPEC+FATAL,error),[code,'vm-acquire-stderr-unobserved'])

    def test_missing_nonce_unknown_phase_and_hostile_nonce_cannot_read_or_emit(self):
        class PrivateStr(str):
            def __str__(self):raise AssertionError('private nonce formatted')
        with tempfile.TemporaryDirectory() as tmp:
            for token in ('','private','a'*32+'\n',PrivateStr('a'*32),None):
                env=diagnostic_env(Path(tmp),token);out=io.StringIO()
                with patch.object(os,'open',side_effect=AssertionError('observer must be inactive')),contextlib.redirect_stdout(out):
                    env['dictation_qemu_startup']('install',1,SystemExit('no QMP socket'))
                self.assertEqual(out.getvalue(),'')
            env=diagnostic_env(Path(tmp));out=io.StringIO()
            with contextlib.redirect_stdout(out):env['dictation_qemu_startup']('../private',1,SystemExit('private'))
            self.assertEqual(out.getvalue(),'')

    def test_constructor_returns_same_value_same_argument_objects_once_without_file_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            argv=object();qmp=object();name=object();value=object();ctor=Mock(return_value=value);env=diagnostic_env(Path(tmp),vm=ctor)
            with patch.object(os,'open',side_effect=AssertionError('success must not read stderr')):
                self.assertIs(env['dictation_acquire_vm'](argv,qmp,name),value)
            ctor.assert_called_once_with(argv,qmp,name)

    def test_constructor_original_exception_identity_survives_private_getters_closed_output_and_observer_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            original=PrivateError('private args');ctor=Mock(side_effect=original);env=diagnostic_env(Path(tmp),vm=ctor)
            with patch('builtins.print',side_effect=BrokenPipeError('private')):
                try:env['dictation_acquire_vm']([], '/tmp/qmp', 'install')
                except BaseException as caught:self.assertIs(caught,original)
                else:self.fail('original error swallowed')

    def test_pending_clock_interrupt_never_starts_qemu_and_original_stage_cleanup_runs(self):
        original=KeyboardInterrupt('private');ctor=Mock();cleanup=[]
        with tempfile.TemporaryDirectory() as tmp:
            env=driver_functions(HELPERS|{'stage_boot','dictation_host_stage'}, {
                'E':{'ARCTIC_DICTATION_HOST_TOKEN':'a'*32},'out':str(Path(tmp)), 'os':os,
                'time':SimpleNamespace(time_ns=Mock(side_effect=original)),
                'vmtest':SimpleNamespace(VM=ctor,QMPError=QMPError),
                'taskbar_display_module':None,'dictation_cpu_argv':lambda x:x,
                'native_taskbar_argv':lambda *args:args[0], 'dictation_network_argv':lambda *args:args[0],
                'qemu_argv':lambda *args:[], 'close_taskbar_vm':lambda *args:cleanup.append(args)})
            with contextlib.redirect_stdout(io.StringIO()):
                try:env['stage_boot']()
                except BaseException as caught:self.assertIs(caught,original)
                else:self.fail('pending interrupt swallowed')
            ctor.assert_not_called();self.assertEqual(cleanup,[(None,None)])
            for failure in (KeyboardInterrupt('private'),SystemExit('private'),PrivateError('private')):
                env['dictation_qemu_startup']=Mock(side_effect=failure)
                try:env['dictation_acquire_vm']([], '/tmp/qmp', 'install')
                except BaseException as caught:self.assertIs(caught,original)
                else:self.fail('original error swallowed')

    def test_stale_zero_oversized_writable_hardlinked_and_nonregular_files_are_unobserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'qemu-install.log';base=['vm-acquire-qemu-exited','vm-acquire-stderr-unobserved']
            self.assertEqual(self.observe(root,b''),base);self.assertEqual(self.observe(root,b'x'*65537),base)
            self.assertEqual(self.observe(root,SPEC+FATAL,started=time.time_ns()+10**9),base)
            path.write_bytes(SPEC+FATAL);path.chmod(0o666);self.assertEqual(self.observe(root,None),base);path.chmod(0o600)
            other=root/'alias';os.link(path,other);self.assertEqual(self.observe(root,None),base);other.unlink();path.unlink()
            actual=root/'real';actual.write_bytes(SPEC+FATAL);path.symlink_to(actual);self.assertEqual(self.observe(root,None),base);path.unlink()
            path.mkdir();self.assertEqual(self.observe(root,None),base);path.rmdir()
            os.mkfifo(path);self.assertEqual(self.observe(root,None),base);path.unlink()
            sock=socket.socket(socket.AF_UNIX);sock.bind(str(path))
            try:self.assertEqual(self.observe(root,None),base)
            finally:sock.close();path.unlink()
            self.assertEqual(self.observe(root,None),base)

    def test_wrong_uid_and_private_stat_getters_cannot_supply_a_trusted_owned_log(self):
        class PrivateStat:
            def __getattr__(self,name):raise PrivateError('private stat')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'qemu-install.log').write_bytes(SPEC+FATAL);original=os.fstat
            def info(fd):
                value=original(fd)
                if value.st_size==len(SPEC+FATAL):
                    fields=('st_mode','st_uid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
                    return SimpleNamespace(**{k:os.geteuid()+1 if k=='st_uid' else getattr(value,k) for k in fields})
                return value
            for replacement in (info,lambda fd:PrivateStat()):
                with patch.object(os,'fstat',side_effect=replacement):
                    self.assertEqual(self.observe(root,None),['vm-acquire-qemu-exited','vm-acquire-stderr-unobserved'])

    def test_log_and_directory_replacement_races_are_unobserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'qemu-install.log';path.write_bytes(SPEC+FATAL);original=os.stat
            changed=[False]
            def race(p,*args,**kwargs):
                if p=='qemu-install.log' and not changed[0]:
                    changed[0]=True;path.rename(root/'retained');path.write_bytes(SPEC+FATAL)
                return original(p,*args,**kwargs)
            with patch.object(os,'stat',side_effect=race):
                self.assertEqual(self.observe(root,None),['vm-acquire-qemu-exited','vm-acquire-stderr-unobserved'])
            self.assertTrue(changed[0])
            replacement=[False]
            def directory_race(p,*args,**kwargs):
                value=original(p,*args,**kwargs)
                if p==str(root):
                    replacement[0]=True
                    return SimpleNamespace(st_dev=value.st_dev,st_ino=value.st_ino+1,st_uid=value.st_uid,st_mode=value.st_mode)
                return value
            with patch.object(os,'stat',side_effect=directory_race):
                self.assertEqual(self.observe(root,None),['vm-acquire-qemu-exited','vm-acquire-stderr-unobserved'])
            self.assertTrue(replacement[0])

    def test_fresh_read_growth_metadata_race_and_closed_diagnostic_output_preserve_unobserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'qemu-install.log';path.write_bytes(SPEC+FATAL);original=os.fstat;calls=[0]
            def growth(fd):
                calls[0]+=1
                if calls[0]==3:
                    with path.open('ab') as f:f.write(b'private\n')
                return original(fd)
            with patch.object(os,'fstat',side_effect=growth):
                self.assertEqual(self.observe(root,None),['vm-acquire-qemu-exited','vm-acquire-stderr-unobserved'])
            self.assertEqual(calls[0],3)
            env=diagnostic_env(root)
            with patch('builtins.print',side_effect=BrokenPipeError('private')):env['dictation_qemu_startup']('install',1,SystemExit('qemu exited: see qemu-install.log'))

    def test_all_new_codes_are_exact_nonce_relay_only_and_guest_forgery_does_not_pass(self):
        old=subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':tools/dictation-qualification/runner.py']).decode()
        old_enum=next(n for n in ast.parse(old).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='HOST_STAGES' for t in n.targets))
        old_codes=ast.literal_eval(old_enum.value.args[0]);new_codes=r.HOST_STAGES-old_codes
        self.assertEqual(len(new_codes),15)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'private.log';good=''.join('ARCTIC-DICTATION-HOST-STAGE '+'a'*32+' '+code+'\n' for code in sorted(new_codes))
            bad=''.join('guest '+line for line in good.splitlines(keepends=True))+good.replace('a'*32,'b'*32)+good.replace('\n','\r\n')
            path.write_text(bad+good);out=io.StringIO()
            with contextlib.redirect_stdout(out):r.relay_host_stages(path,'a'*32,'online-installed')
            self.assertEqual(out.getvalue(),''.join('ARCTIC-DICTATION-HOST-PROGRESS online-installed '+code+'\n' for code in sorted(new_codes)))

    def test_whole_shell_driver_and_runner_rollback_to_accepted_b3_is_byte_exact(self):
        old_shell=subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':tools/test-install.sh']).decode()
        old_driver=old_shell.split("DRIVER <<'PY' || true\n",1)[1].split('\nPY\n',1)[0]
        def enum(text,name):return next(n for n in ast.parse(text).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets))
        old_enum,new_enum=enum(old_driver,'DICTATION_HOST_STAGES'),enum(DRIVER,'DICTATION_HOST_STAGES')
        edits=[(new_enum.lineno-1,new_enum.end_lineno,old_driver.splitlines(keepends=True)[old_enum.lineno-1:old_enum.end_lineno])]
        for node in ast.parse(DRIVER).body:
            if isinstance(node,ast.FunctionDef) and node.name in HELPERS:edits.append((node.lineno-1,node.end_lineno+1,[]))
        lines=DRIVER.splitlines(keepends=True)
        for start,end,replacement in sorted(edits,reverse=True):lines[start:end]=replacement
        restored=''.join(lines);self.assertEqual(restored.count('vm = dictation_acquire_vm('),2)
        restored=restored.replace('vm = dictation_acquire_vm(','vm = vmtest.VM(')
        self.assertEqual(restored,old_driver);self.assertEqual(SHELL.replace(DRIVER,restored,1),old_shell)
        self.assertEqual(ast.dump(ast.parse(restored),include_attributes=False),ast.dump(ast.parse(old_driver),include_attributes=False))
        old_runner=subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':tools/dictation-qualification/runner.py']).decode();new_runner=Path(r.__file__).read_text()
        a,b=enum(old_runner,'HOST_STAGES'),enum(new_runner,'HOST_STAGES');lines=new_runner.splitlines(keepends=True)
        lines[b.lineno-1:b.end_lineno]=old_runner.splitlines(keepends=True)[a.lineno-1:a.end_lineno]
        self.assertEqual(''.join(lines),old_runner)

if __name__=='__main__':unittest.main()
