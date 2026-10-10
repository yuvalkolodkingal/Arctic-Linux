"""Fixed host launch facts only; no VM, audio or installation acceptance claims."""
import ast
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zlib

from test_host_diagnostics import DRIVER, ROOT, SHELL, driver_functions, r
from test_contract import declared, c

BASE = '210f76ed599f5b2c51b16dcb97be3fb6c709cfd8'
ADDED = frozenset({
    'install-live-observed', 'install-live-unobserved',
    'install-terminal-attempt-one', 'install-terminal-attempt-two', 'install-terminal-attempt-three',
    'install-command-type-before', 'install-command-type-after',
    'install-command-enter-before', 'install-command-enter-after',
    'install-marker-wait-observed', 'install-marker-wait-unobserved',
    'install-marker-vm-running', 'install-marker-vm-exited', 'install-marker-vm-unknown',
    'install-command-shot-before', 'install-command-shot-after',
    'install-preterminal-capture-preserved', 'install-preterminal-capture-unavailable'})

class PrivateError(RuntimeError):
    def __str__(self): raise AssertionError('private message formatted')
    def __repr__(self): raise AssertionError('private message formatted')

def chunk(kind, body):
    return struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body)&0xffffffff)

def png(width=2, height=2, color=2, depth=8, filtering=0, interlace=0, raw=None, extra=b''):
    if raw is None: raw=(b'\x00'+b'\x00\x60\x80'*width)*height
    header=struct.pack('>IIBBBBB',width,height,depth,color,0,filtering,interlace)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',header)+extra+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')

class LaunchDiagnostics(unittest.TestCase):
    def stage(self, vm, token='a'*32):
        out = io.StringIO()
        env = driver_functions({'dictation_host_stage', 'dictation_install_wait_vm_stage'},
                               {'E': {'ARCTIC_DICTATION_HOST_TOKEN': token}})
        with contextlib.redirect_stdout(out):
            env['dictation_install_wait_vm_stage'](vm)
        return out.getvalue()

    def test_optional_owned_process_observation_has_closed_types_and_no_qmp(self):
        for value, label in ((None, 'running'), (0, 'exited'), (-9, 'exited'),
                             (False, 'unknown'), (1.0, 'unknown'), ('private', 'unknown'),
                             (object(), 'unknown')):
            vm = SimpleNamespace(proc=SimpleNamespace(poll=Mock(return_value=value)),
                                 cmd=Mock(side_effect=AssertionError('QMP must not be called')))
            self.assertEqual(self.stage(vm), 'ARCTIC-DICTATION-HOST-STAGE '+'a'*32+
                             ' install-marker-vm-'+label+'\n')
            vm.proc.poll.assert_called_once_with(); vm.cmd.assert_not_called()

    def test_missing_nonce_closed_stdout_and_private_getters_cannot_change_control(self):
        class PrivateVM:
            @property
            def proc(self): raise PrivateError('private argv transcript')
        for token in ('', 'bad', 'a'*32+'\n'):
            self.assertEqual(self.stage(PrivateVM(), token), '')
        self.assertIn('install-marker-vm-unknown\n', self.stage(PrivateVM()))
        with patch('builtins.print', side_effect=BrokenPipeError('private')):
            self.assertEqual(self.stage(PrivateVM()), '')

    def harness(self, live=True, started=False, fault=None, engine_dead=False):
        events, cleanup, clock = [], [], [0]
        def tick():
            value = clock[0]; clock[0] += 1000; return value
        alive_calls = [0]
        def alive():
            alive_calls[0] += 1
            return not engine_dead or alive_calls[0] < 3
        def typed(*args, **kwargs):
            events.append('typed-command')
            if fault == 'type': raise PrivateError('private command')
        def keys(*args):
            events.append('entered-command')
            if fault == 'enter': raise PrivateError('private keyboard')
        def shot(name):
            if name.endswith('-command-typed'):
                events.append('command-shot')
                if fault == 'shot': raise PrivateError('private screenshot')
        vm = SimpleNamespace(alive=alive, proc=SimpleNamespace(poll=lambda:17 if engine_dead else None),
                             type_text=typed, keys=keys, shot=shot)
        def marker(path, value):
            return (value == 'live session mode:' and live) or (value == 'ARCTIC-TEST-STARTED' and started)
        env = driver_functions({'stage_install', 'dictation_install_wait_vm_stage'}, {
            'E': {'GUEST_CHECK':'fixture', 'ARCTIC_DICTATION_HOST_TOKEN':'a'*32},
            'taskbar_display_module':None, 'vmtest':SimpleNamespace(VM=lambda *a:vm,
                serial_has=marker, serial_value=lambda *a:None),
            'time':SimpleNamespace(time=tick, sleep=lambda *a:None),
            'dictation_host_stage':events.append, 'dictation_cpu_argv':lambda a:a,
            'native_taskbar_argv':lambda *a:a[0], 'dictation_network_argv':lambda *a:a[0],
            'qemu_argv':lambda *a:[], 'wait_menu':lambda *a:False,
            'open_terminal':lambda *a:None, 'serial':lambda name:name,
            'log':lambda *a:None, 'install_timeout':2400,
            'close_taskbar_vm':lambda *a:cleanup.append(a), 'dictation_launch_desktop':lambda *a:None})
        return env, vm, events, cleanup

    def test_live_result_three_attempts_and_marker_wait_failure_preserve_rc90(self):
        for live in (True, False):
            env, vm, events, cleanup = self.harness(live=live)
            self.assertEqual(env['stage_install'](), 90)
            self.assertIn('install-live-observed' if live else 'install-live-unobserved', events)
            for attempt in ('one','two','three'):
                self.assertEqual(events.count('install-terminal-attempt-'+attempt), 1)
            self.assertEqual(events.count('typed-command'), 3)
            self.assertEqual(events.count('install-marker-wait-unobserved'), 3)
            self.assertEqual(events.count('install-marker-vm-running'), 3)
            self.assertNotIn('install-engine', events)
            self.assertEqual(events[-1], 'install-cleanup'); self.assertEqual(cleanup, [(vm,None)])

    def test_observed_marker_is_emitted_before_shot_and_engine_failure_preserves_rc91(self):
        for dead in (False, True):
            env, vm, events, cleanup = self.harness(started=True, engine_dead=dead)
            self.assertEqual(env['stage_install'](), 91)
            self.assertLess(events.index('install-marker-wait-observed'), events.index('command-shot'))
            self.assertLess(events.index('install-command-shot-before'), events.index('command-shot'))
            self.assertLess(events.index('command-shot'), events.index('install-command-shot-after'))
            self.assertIn('install-marker-vm-exited' if dead else 'install-marker-vm-running', events)
            self.assertNotIn('install-terminal-attempt-two', events)
            self.assertEqual(events[-1], 'install-cleanup'); self.assertEqual(cleanup, [(vm,None)])

    def test_failed_keyboard_or_capture_boundary_propagates_original_error_and_cleanup(self):
        for boundary in ('type','enter','shot'):
            env, vm, events, cleanup = self.harness(started=True, fault=boundary)
            with self.assertRaises(PrivateError):
                env['stage_install']()
            self.assertIn('install-command-'+('shot' if boundary=='shot' else boundary)+'-before', events)
            self.assertNotIn('install-command-'+('shot' if boundary=='shot' else boundary)+'-after', events)
            self.assertEqual(events[-1], 'install-cleanup'); self.assertEqual(cleanup, [(vm,None)])

    def test_all_new_codes_relay_only_exact_host_nonce_complete_lines(self):
        import tempfile
        self.assertTrue(ADDED <= r.HOST_STAGES)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'private.log'
            good = ''.join('ARCTIC-DICTATION-HOST-STAGE '+'a'*32+' '+code+'\n' for code in sorted(ADDED))
            hostile = ''.join('ARCTIC-DICTATION-HOST-STAGE '+'b'*32+' '+code+'\n' for code in sorted(ADDED))
            hostile += ''.join('guest '+line for line in good.splitlines(keepends=True)) + 'ARCTIC-DICTATION-HOST-STAGE '+'a'*32+' private-transcript\n'
            path.write_text(hostile+good)
            out=io.StringIO()
            with contextlib.redirect_stdout(out): r.relay_host_stages(path,'a'*32,'online-installed')
            expected=''.join('ARCTIC-DICTATION-HOST-PROGRESS online-installed '+code+'\n' for code in sorted(ADDED))
            self.assertEqual(out.getvalue(),expected)
            self.assertEqual(path.read_text(),hostile+good)

    def test_whole_shell_driver_runner_bytes_roll_back_only_added_observers(self):
        old_shell=subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':tools/test-install.sh']).decode()
        old_driver=old_shell.split("DRIVER <<'PY' || true\n",1)[1].split('\nPY\n',1)[0]
        old_tree,new_tree=ast.parse(old_driver),ast.parse(DRIVER)
        old_enum=next(n for n in old_tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='DICTATION_HOST_STAGES' for t in n.targets))
        edits=[]
        helpers=[n for n in new_tree.body if isinstance(n,ast.FunctionDef) and n.name in ('dictation_install_wait_vm_stage', 'dictation_launch_desktop')]
        for n in ast.walk(new_tree):
            if any(helper.lineno < getattr(n,'lineno',0) <= helper.end_lineno for helper in helpers):
                continue
            if isinstance(n,ast.FunctionDef) and n.name in ('dictation_install_wait_vm_stage', 'dictation_launch_desktop'):
                edits.append((n.lineno-1,n.end_lineno+1,[]))
            if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='DICTATION_HOST_STAGES' for t in n.targets):
                edits.append((n.lineno-1,n.end_lineno,old_driver.splitlines(keepends=True)[old_enum.lineno-1:old_enum.end_lineno]))
            if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name):
                call=n.value
                strings={v.value for v in ast.walk(call) if isinstance(v,ast.Constant) and type(v.value) is str}
                if call.func.id=='dictation_install_wait_vm_stage' or (call.func.id=='dictation_host_stage' and strings and strings<=ADDED):
                    edits.append((n.lineno-1,n.end_lineno,[]))
                if call.func.id=='dictation_launch_desktop':
                    self.assertEqual(ast.unparse(call.args[0]), "vm.shot('install-20-live-desktop')")
                    edits.append((n.lineno-1,n.end_lineno,['        vm.shot("install-20-live-desktop")\n']))
        lines=DRIVER.splitlines(keepends=True)
        for begin,end,replacement in sorted(edits,reverse=True): lines[begin:end]=replacement
        rolled=''.join(lines)
        coherent = ('        # A versioned coherent v2 floor, without partially masked host XSAVE.\n'
                    "        # QEMU Westmere-v2 adds spec-ctrl to Westmere's pre-AVX CPU model;\n"
                    '        # enforce rejects unsupported requested features before guest execution.\n'
                    '        argv[at] = "Westmere-v2,enforce"\n')
        self.assertEqual(rolled.count(coherent),1)
        rolled=rolled.replace(coherent, '        argv[at] += ",-avx,-avx2,-fma,-f16c,-bmi1,-bmi2"\n',1)
        self.assertEqual(rolled,old_driver)
        self.assertEqual(SHELL.replace(DRIVER,rolled,1),old_shell)
        self.assertEqual(ast.dump(ast.parse(rolled),include_attributes=False),ast.dump(old_tree,include_attributes=False))
        old_runner=subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':tools/dictation-qualification/runner.py']).decode()
        new_runner=Path(r.__file__).read_text()
        def assignment(text):
            return next(n for n in ast.parse(text).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='HOST_STAGES' for t in n.targets))
        a,b=assignment(old_runner),assignment(new_runner); lines=new_runner.splitlines(keepends=True)
        edits=[(b.lineno-1,b.end_lineno,old_runner.splitlines(keepends=True)[a.lineno-1:a.end_lineno])]
        for node in ast.walk(ast.parse(new_runner)):
            if isinstance(node,ast.FunctionDef) and node.name in ('launch_diagnostic_read', 'launch_diagnostic_png', 'preserve_launch_diagnostic'):
                edits.append((node.lineno-1,node.end_lineno+2,[]))
            if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=='preserve_launch_diagnostic':
                edits.append((node.lineno-1,node.end_lineno,[]))
        for begin,end,replacement in sorted(edits,reverse=True): lines[begin:end]=replacement
        self.assertEqual(''.join(lines),old_runner)

class LaunchCaptureDiagnostics(unittest.TestCase):
    def driver(self, root, path, token='a'*32):
        env=driver_functions({'dictation_launch_desktop','dictation_host_stage'},
            {'E':{'ARCTIC_DICTATION_HOST_TOKEN':token},'out':str(root),'os':os})
        output=io.StringIO()
        with contextlib.redirect_stdout(output): env['dictation_launch_desktop'](path)
        return output.getvalue()

    def prepared(self, root):
        vm=root/'vm';vm.mkdir();evidence=root/'evidence';evidence.mkdir()
        path=vm/'install-20-live-desktop.png';path.write_bytes(png())
        self.assertIn('capture-preserved',self.driver(vm,str(path)))
        log=root/'private.log'
        log.write_text('ARCTIC-DICTATION-HOST-STAGE '+'a'*32+' install-preterminal-capture-preserved\n')
        return vm,log,evidence,declared('online-installed'),path.read_bytes()

    def test_driver_copies_exact_original_preterminal_bytes_and_fresh_host_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'install-20-live-desktop.png';data=png();path.write_bytes(data)
            output=self.driver(root,str(path))
            self.assertEqual(output,'ARCTIC-DICTATION-HOST-STAGE '+'a'*32+' install-preterminal-capture-preserved\n')
            self.assertEqual((root/'dictation-launch-desktop.png').read_bytes(),data)
            proof=json.loads((root/'dictation-launch-desktop-receipt.json').read_text())
            self.assertEqual(proof,dict(schema='arctic-dictation-preterminal-capture-v1',capture_stage='before-first-terminal',
                path='dictation-launch-desktop.png',bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
                token_sha256=hashlib.sha256(('a'*32).encode()).hexdigest()))
            for name in ('dictation-launch-desktop.png','dictation-launch-desktop-receipt.json'):
                self.assertEqual(stat.S_IMODE((root/name).stat().st_mode),0o600)

    def test_driver_optional_nonce_and_closed_stdout_do_not_change_control(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for token in ('','bad','a'*32+'\n'):
                self.assertEqual(self.driver(root,None,token),'');self.assertEqual(list(root.iterdir()),[])
            with patch('builtins.print',side_effect=BrokenPipeError('private transcript')):
                self.assertEqual(self.driver(root,None),'')

    def test_driver_nofollow_nonregular_cap_and_exclusive_outputs_fail_closed(self):
        for kind in ('none','private-path','symlink','fifo','oversized','writable','existing-output'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);path=root/'install-20-live-desktop.png'
                if kind=='symlink':
                    target=root/'target';target.write_bytes(png());path.symlink_to(target)
                elif kind=='fifo': os.mkfifo(path)
                else:path.write_bytes(png())
                if kind=='oversized':
                    with path.open('wb') as stream:stream.truncate(4*1024*1024+1)
                if kind=='writable':path.chmod(0o666)
                if kind=='existing-output':(root/'dictation-launch-desktop-receipt.json').write_bytes(b'private sentinel')
                output=self.driver(root,None if kind=='none' else str(root/'private') if kind=='private-path' else str(path))
                self.assertIn('capture-unavailable',output);self.assertNotIn('private',output)
                self.assertFalse((root/'dictation-launch-desktop.png').exists())
                if kind=='existing-output':self.assertEqual((root/'dictation-launch-desktop-receipt.json').read_bytes(),b'private sentinel')

    def test_driver_signal_propagates_and_original_source_is_not_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'install-20-live-desktop.png';path.write_bytes(png())
            with patch('os.open',side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):self.driver(root,str(path))
            self.assertEqual(path.read_bytes(),png());self.assertEqual(len(list(root.iterdir())),1)

    def test_png_original_rgb_rgba_bounds_crc_and_private_metadata_rejections(self):
        self.assertEqual(r.launch_diagnostic_png(png()),(2,2))
        self.assertEqual(r.launch_diagnostic_png(png(color=6,raw=(b'\x00'+b'\x10\x20\x30\xff'*2)*2)),(2,2))
        cases=[png(width=1921),png(height=1081),png(width=0),png(depth=16),png(color=3),png(filtering=1),
            png(interlace=1),png(raw=b'\x05'+b'\x00'*13),png(raw=b'\x00'*15),png(raw=b'\x00'*1000000),
            png(extra=chunk(b'tEXt',b'transcript\x00private')),png()+b'private',png()[:-1],
            b'\x89PNG\r\n\x1a\n'+chunk(b'IDAT',b'x')+chunk(b'IEND',b'')]
        broken=bytearray(png());broken[-1]^=1;cases.append(bytes(broken))
        for value in cases:
            with self.subTest(bytes=len(value)),self.assertRaises((RuntimeError,zlib.error)):
                r.launch_diagnostic_png(value)

    def test_reader_regular_owned_modes_symlinks_fifos_and_path_races(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'file';path.write_bytes(b'fixed')
            self.assertEqual(r.launch_diagnostic_read(root,'file',5),b'fixed')
            for name,limit in (('../file',5),('file',True),('file',16*1024*1024+1)):
                with self.assertRaises(RuntimeError):r.launch_diagnostic_read(root,name,limit)
            with self.assertRaises(RuntimeError):r.launch_diagnostic_read(root,'file',4)
            path.chmod(0o666)
            with self.assertRaises(RuntimeError):r.launch_diagnostic_read(root,'file',5)
            path.chmod(0o600);(root/'link').symlink_to(path);os.mkfifo(root/'fifo')
            for name in ('link','fifo'):
                with self.assertRaises((OSError,RuntimeError)):r.launch_diagnostic_read(root,name,5)
            original_stat=os.stat
            def raced(name,*args,**kwargs):
                info=original_stat(name,*args,**kwargs)
                if name=='file':return SimpleNamespace(**{key:getattr(info,key) for key in
                    ('st_dev','st_uid','st_mode','st_size','st_mtime_ns','st_ctime_ns')},st_ino=info.st_ino+1)
                return info
            with patch.object(r.os,'stat',side_effect=raced):
                with self.assertRaises(RuntimeError):r.launch_diagnostic_read(root,'file',5)
            original_fstat=os.fstat
            def wrong_owner(fd):
                info=original_fstat(fd)
                if stat.S_ISREG(info.st_mode):return SimpleNamespace(st_mode=info.st_mode,st_uid=os.geteuid()+1)
                return info
            with patch.object(r.os,'fstat',side_effect=wrong_owner):
                with self.assertRaises(RuntimeError):r.launch_diagnostic_read(root,'file',5)
            self.assertEqual(path.read_bytes(),b'fixed')

    def test_failure_only_capture_has_context_source_original_bytes_and_no_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            vm,log,evidence,ctx,data=self.prepared(Path(tmp))
            self.assertTrue(r.preserve_launch_diagnostic(vm,log,'a'*32,ctx,evidence,c))
            self.assertEqual((evidence/'launch-preterminal-online-installed.png').read_bytes(),data)
            record=json.loads((evidence/'launch-preterminal-online-installed.json').read_text())
            self.assertEqual(record['context'],ctx);self.assertFalse(record['release_acceptance'])
            self.assertEqual(record['status'],'diagnostic_only');self.assertEqual(record['guest_command_start'],'unobserved')
            self.assertEqual(record['image'],dict(path='launch-preterminal-online-installed.png',bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),width=2,height=2))
            self.assertEqual(record['execution_files'],{name:r.sha(ROOT/name) for name in
                ('tools/test-install.sh','tools/dictation-qualification/runner.py')})
            with self.assertRaises(c.Invalid):c.validate_execution(record,{})
            self.assertFalse(r.preserve_launch_diagnostic(vm,log,'a'*32,ctx,evidence,c))
            self.assertEqual((evidence/'launch-preterminal-online-installed.png').read_bytes(),data)

    def test_guest_stage_forgery_nonce_incomplete_line_and_command_start_block_export(self):
        for line in ('guest ARCTIC-DICTATION-HOST-STAGE '+'a'*32+' install-preterminal-capture-preserved\n',
                     'ARCTIC-DICTATION-HOST-STAGE '+'b'*32+' install-preterminal-capture-preserved\n',
                     'ARCTIC-DICTATION-HOST-STAGE '+'a'*32+' install-preterminal-capture-preserved',
                     'ARCTIC-DICTATION-HOST-STAGE '+'a'*32+' install-preterminal-capture-preserved\r\n'):
            with self.subTest(line=line[:30]),tempfile.TemporaryDirectory() as tmp:
                vm,log,evidence,ctx,_=self.prepared(Path(tmp));log.write_text(line)
                self.assertFalse(r.preserve_launch_diagnostic(vm,log,'a'*32,ctx,evidence,c));self.assertEqual(list(evidence.iterdir()),[])
        for stage in ('install-marker-wait-observed','install-start-observed','install-engine','install-exit-observed'):
            with self.subTest(stage=stage),tempfile.TemporaryDirectory() as tmp:
                vm,log,evidence,ctx,_=self.prepared(Path(tmp))
                with log.open('a') as stream:stream.write('ARCTIC-DICTATION-HOST-STAGE '+'a'*32+' '+stage+'\n')
                self.assertFalse(r.preserve_launch_diagnostic(vm,log,'a'*32,ctx,evidence,c));self.assertEqual(list(evidence.iterdir()),[])

    def test_receipt_types_extra_private_keys_duplicates_hash_context_and_mutation_reject(self):
        cases=('extra','boolean-bytes','wrong-path','wrong-token','wrong-hash','duplicate','image-race','context','non-online')
        for case in cases:
            with self.subTest(case=case),tempfile.TemporaryDirectory() as tmp:
                vm,log,evidence,ctx,_=self.prepared(Path(tmp));path=vm/'dictation-launch-desktop-receipt.json'
                proof=json.loads(path.read_text())
                if case=='extra':proof['transcript']='private'
                if case=='boolean-bytes':proof['bytes']=True
                if case=='wrong-path':proof['path']='install-21-command-typed.png'
                if case=='wrong-token':proof['token_sha256']='b'*64
                if case=='wrong-hash':proof['sha256']='c'*64
                if case=='image-race':(vm/'dictation-launch-desktop.png').write_bytes(png(width=3))
                if case=='context':ctx['transcript']='private'
                if case=='non-online':ctx['phase']='recovery'
                path.write_text(json.dumps(proof) if case!='duplicate' else json.dumps(proof)[:-1]+',"bytes":1}')
                output=io.StringIO()
                with contextlib.redirect_stdout(output):result=r.preserve_launch_diagnostic(vm,log,'a'*32,ctx,evidence,c)
                self.assertFalse(result);self.assertEqual(output.getvalue(),'');self.assertEqual(list(evidence.iterdir()),[])

if __name__=='__main__':
    unittest.main()
