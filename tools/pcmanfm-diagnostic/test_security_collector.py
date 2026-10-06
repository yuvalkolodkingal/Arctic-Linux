#!/usr/bin/env python3
"""Actual framed subprocess/scan controls; all UI, boot and journal authority synthetic."""
import ast
import copy
import hashlib
import importlib.util
import io
import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
def module(name,file):
    spec=importlib.util.spec_from_file_location(name,HERE/file)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
S=module('explicit_security_control','security-collector.py')
G=module('explicit_guest_control','guest-pcmanfm-diagnostic.py')
B=module('explicit_owned_control','bounded-launch.py')
BOOT='a'*32

def line(cursor='end',message='ordinary',transport='kernel',**fields):
    return (json.dumps(dict(_BOOT_ID=BOOT,__CURSOR=cursor,_TRANSPORT=transport,MESSAGE=message,**fields))+'\n').encode()


class FramingControls(unittest.TestCase):
    def test_real_callback_interruption_retains_error_counters_and_reaps_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def stop(_):raise KeyboardInterrupt('owned collector interruption fixture')
            with self.assertRaises(KeyboardInterrupt):
                S.run_stream([sys.executable,'-c',"import sys,time;print('record',flush=True);time.sleep(20)"],stop,root/'command.json')
            row=json.loads((root/'command.json').read_text())
            self.assertFalse(row['complete']);self.assertTrue(row['only_owned_child_reaped'])
            self.assertGreater(row['stdout_observed_bytes'],0);self.assertIn('KeyboardInterrupt',row['error'])
    def test_real_small_command_framing_fourteen_max_outputs_remains_one_bounded_member(self):
        with tempfile.TemporaryDirectory() as tmp:
            value=S.SecurityInterval.__new__(S.SecurityInterval);value.root=Path(tmp)
            for index in range(14):
                data,meta=value.small([sys.executable,'-c',"import sys;sys.stdout.buffer.write(b'x'*65536)"],'fixture-%02d'%index)
                self.assertEqual(len(data),65536);self.assertTrue(meta['complete'])
            files=list(value.root.iterdir());self.assertEqual([p.name for p in files],['small-commands.log'])
            data=files[0].read_bytes();self.assertLess(len(data),S.SMALL_COMMAND_BYTES);self.assertEqual(data.count(b'\n'),14)
            with self.assertRaisesRegex(RuntimeError,'count exceeded'):
                value.small([sys.executable,'-c','pass'],'unexpected-fifteenth')
            self.assertTrue((value.root/'unexpected-fifteenth.json').is_file())
    def test_real_small_failed_command_raw_error_and_stderr_are_consolidated(self):
        with tempfile.TemporaryDirectory() as tmp:
            value=S.SecurityInterval.__new__(S.SecurityInterval);value.root=Path(tmp)
            with self.assertRaisesRegex(RuntimeError,'stderr'):
                value.small([sys.executable,'-c',"import sys;sys.stderr.write('actual retained error')"],'failure')
            row=S.strict_json((value.root/'small-commands.log').read_bytes().rstrip(b'\n'))
            self.assertFalse(row['command']['complete']);self.assertTrue(row['command']['only_owned_child_reaped'])
            self.assertEqual(__import__('base64').b64decode(row['stderr_base64']),b'actual retained error')
    def test_real_split_framed_stream_roundtrip_digest_and_trusted_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);scan=S.JournalScan(root,BOOT,'end','start')
            data=line('one',transport='syslog')+line('two',transport='audit')+line('end')
            source=root/'fixture';source.write_bytes(data)
            argv=[sys.executable,'-c',"import sys;d=open(sys.argv[1],'rb').read();[sys.stdout.buffer.write(d[i:i+7]) for i in range(0,len(d),7)]",str(source)]
            result=S.run_stream(argv,scan.feed,root/'command.json',finish_callback=scan.finish)
            report=scan.report();self.assertTrue(result['complete']);self.assertTrue(report['complete'])
            self.assertEqual(result['stdout_observed_sha256'],hashlib.sha256(data).hexdigest())
            self.assertEqual(report['observed_records'],3);self.assertEqual(report['trusted_kernel_audit_records'],2)
            saved=b''.join((root/p['path']).read_bytes() for p in report['parts'])
            self.assertEqual(saved,line('two',transport='audit')+line('end'))
    def test_eof_partial_record_marks_actual_command_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);scan=S.JournalScan(root,BOOT,'end');data=line()[:-1]
            with self.assertRaisesRegex(RuntimeError,'partial newline'):
                S.run_stream([sys.executable,'-c','import sys;sys.stdout.buffer.write('+repr(data)+')'],scan.feed,
                             root/'command.json',finish_callback=scan.finish)
            record=json.loads((root/'command.json').read_text());self.assertFalse(record['complete'])
            self.assertEqual(record['stdout_observed_bytes'],len(data));self.assertFalse(scan.report()['complete'])
    def test_messages_string_binary_repeated_values_all_detect_denial(self):
        for message in ('avc: denied',list(b'avc: denied'),['ordinary','type=AVC'],[['a'[0].encode()[0]],list(b'avc: denied')]):
            with self.subTest(message=message),tempfile.TemporaryDirectory() as tmp:
                scan=S.JournalScan(Path(tmp),BOOT,'end');scan.feed(line(message=message));scan.finish()
                self.assertEqual(scan.report()['matching_denial_records'],1)
    def test_missing_null_mixed_bad_octets_invalid_utf8_fail_closed(self):
        for message in (None,True,3,{},[],[True],[256],[-1],[255],['ordinary',1],[['nested']]):
            with self.subTest(message=message),tempfile.TemporaryDirectory() as tmp:
                scan=S.JournalScan(Path(tmp),BOOT,'end')
                with self.assertRaises((RuntimeError,UnicodeDecodeError)):scan.feed(line(message=message))
                self.assertFalse(scan.report()['complete'])
    def test_duplicate_keys_nonfinite_wrong_boot_missing_cursor_transport_rejected(self):
        cases=[b'{"MESSAGE":"ordinary","MESSAGE":"avc: denied"}\n',b'{"a":NaN}\n',
               line().replace(BOOT.encode(),b'b'*32),line().replace(b'"__CURSOR": "end", ',b''),
               line().replace(b'"_TRANSPORT": "kernel", ',b'')]
        for data in cases:
            with tempfile.TemporaryDirectory() as tmp:
                scan=S.JournalScan(Path(tmp),BOOT,'end')
                with self.assertRaises((RuntimeError,json.JSONDecodeError)):scan.feed(data)
                self.assertFalse(scan.report()['complete'])
    def test_cursor_continuity_end_missing_repeat_and_start_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            scan=S.JournalScan(Path(tmp),BOOT,'end','start')
            with self.assertRaisesRegex(RuntimeError,'excluded initial'):scan.feed(line('start'))
        with tempfile.TemporaryDirectory() as tmp:
            scan=S.JournalScan(Path(tmp),BOOT,'end');scan.feed(line('one'))
            with self.assertRaisesRegex(RuntimeError,'end cursor'):scan.finish()
            with self.assertRaisesRegex(RuntimeError,'repeated'):scan.feed(line('one'))
            scan.report()
    def test_real_stream_nonzero_stderr_overflow_timeout_and_setup_cleanup(self):
        cases=[("import sys;sys.exit(2)",{},'nonzero'),("import sys;sys.stderr.write('bad')",{},'stderr'),
               ("print('x'*1024)",{'limit':100},'byte bound'),("import time;time.sleep(20)",{'timeout':.05},'deadline')]
        for code,options,wanted in cases:
            with self.subTest(code=code),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                with self.assertRaisesRegex(RuntimeError,wanted):S.run_stream([sys.executable,'-c',code],lambda _:None,root/'cmd.json',**options)
                record=json.loads((root/'cmd.json').read_text());self.assertFalse(record['complete']);self.assertTrue(record['only_owned_child_reaped'])
        with tempfile.TemporaryDirectory() as tmp,patch.object(S.os,'pidfd_open',side_effect=OSError('setup-control')):
            root=Path(tmp)
            with self.assertRaises(OSError):S.run_stream([sys.executable,'-c','import time;time.sleep(20)'],lambda _:None,root/'cmd.json')
            record=json.loads((root/'cmd.json').read_text());self.assertTrue(record['only_owned_child_reaped']);self.assertFalse(record['complete'])
    def test_record_count_record_byte_and_preservation_caps_fail(self):
        for setting,value,data in [('SCAN_RECORDS',1,line('one')+line('end')),
                                   ('RECORD_BYTES',100,line(message='x'*200)),
                                   ('PRESERVE_BYTES',100,line())]:
            with tempfile.TemporaryDirectory() as tmp,patch.object(S,setting,value):
                scan=S.JournalScan(Path(tmp),BOOT,'end')
                with self.assertRaises(RuntimeError):scan.feed(data)
                self.assertFalse(scan.report()['complete'])
    def test_chunks_never_split_a_complete_record_and_nontrusted_denials_retained(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(S,'CHUNK_BYTES',200):
            root=Path(tmp);scan=S.JournalScan(root,BOOT,'end')
            scan.feed(line('one',message='avc: denied',transport='syslog')+line('end'))
            scan.finish();parts=scan.report()['parts'];self.assertEqual(len(parts),2)
            self.assertEqual(json.loads((root/parts[0]['path']).read_bytes())['MESSAGE'],'avc: denied')
            self.assertTrue(all((root/p['path']).read_bytes().endswith(b'\n') for p in parts))
    def test_more_than_old_four_mib_stream_complete_under_new_finite_scan_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=b''.join(line(str(i),message='x'*1300) for i in range(3500));self.assertGreater(len(data),4*1024*1024)
            source=root/'fixture';source.write_bytes(data);scan=S.JournalScan(root,BOOT,'3499')
            result=S.run_stream([sys.executable,'-c',"import sys;sys.stdout.buffer.write(open(sys.argv[1],'rb').read())",str(source)],
                                scan.feed,root/'command.json',finish_callback=scan.finish)
            self.assertTrue(result['complete']);self.assertEqual(scan.report()['observed_records'],3500)


class AuditControls(unittest.TestCase):
    def test_actual_audit_write_during_read_is_rejected_not_a_complete_interval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);value=self.fixture(root);value.audit_file.write_bytes(b'original\n')
            actual=S.os.fstat;calls=[]
            def changed(fd):
                row=actual(fd);calls.append(fd)
                if len(calls)==1:
                    with value.audit_file.open('ab') as stream:stream.write(b'changed during read\n')
                return row
            with patch.object(S.os,'fstat',side_effect=changed),self.assertRaisesRegex(RuntimeError,'during interval read'):
                value.audit_interval()
            self.assertFalse(json.loads((value.root/'audit-interval.json').read_text())['complete'])
    def fixture(self,path):
        value=S.SecurityInterval.__new__(S.SecurityInterval);value.root=path/'evidence';value.root.mkdir()
        value.audit_file=path/'audit.log';value.audit_offset=None;return value
    def test_absent_present_full_interval_and_denials_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);value=self.fixture(root);self.assertEqual(value.audit_interval(),'')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);value=self.fixture(root);value.audit_file.write_bytes(b'type=AVC fixture\n')
            self.assertIn('type=AVC',value.audit_interval());record=json.loads((value.root/'audit-interval.json').read_text())
            self.assertTrue(record['complete']);self.assertEqual(record['observed_matching_denials'],1)
    def test_rotation_truncation_disappearance_and_partial_newline_fail(self):
        for change in ('rotate','truncate','missing','partial'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);value=self.fixture(root);value.audit_file.write_bytes(b'initial\n');value.audit_offset=value.audit_identity()
                if change=='rotate':value.audit_file.rename(root/'old');value.audit_file.write_bytes(b'new\n')
                elif change=='truncate':value.audit_file.write_bytes(b'')
                elif change=='missing':value.audit_file.unlink()
                else:
                    with value.audit_file.open('ab') as stream:stream.write(b'partial')
                with self.assertRaises(RuntimeError):value.audit_interval()
                self.assertFalse(json.loads((value.root/'audit-interval.json').read_text())['complete'])
    def test_audit_size_boundary_is_inherited_and_overflow_fails(self):
        self.assertEqual(S.AUDIT_BYTES,4*1024*1024)
        with tempfile.TemporaryDirectory() as tmp,patch.object(S,'AUDIT_BYTES',8):
            root=Path(tmp);value=self.fixture(root);value.audit_file.write_bytes(b'123456789\n')
            with self.assertRaisesRegex(RuntimeError,'byte bound'):value.audit_interval()


class IdentityControls(unittest.TestCase):
    def test_actual_direct_child_argv_pid_start_and_streams_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);binary=str(Path(sys.executable).resolve())
            role=dict(executable_sha256=B.digest(binary),direct_argv=[binary,'-c',
                "import sys,time;sys.stderr.write('owned stream\\n');sys.stderr.flush();time.sleep(.1)"])
            self.assertEqual(B.run_owned(root,role['direct_argv'],role=role),0)
            value=json.loads((root/'pcmanfm-owned-launch.json').read_text())
            self.assertEqual(value['role'],role);self.assertEqual(value['process']['uid'],os.getuid())
            self.assertEqual(value['process']['executable'],binary);self.assertGreater(value['process']['start_ticks'],0)
            self.assertEqual((root/'pcmanfm-wayland-stderr.log').read_bytes(),b'owned stream\n')
    def test_exact_helper_last_role_precedence_no_command_argument_broadening(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);system=root/'system';user=root/'user'
            system.write_text('files=nautilus\nfiles=pcmanfm\n');user.write_text('browser=epiphany\n')
            self.assertEqual(B.role_configuration([system,user])[0],'pcmanfm')
            for value in ('nautilus','pcmanfm --new-window','pcmanfm /tmp','pcmanfm;echo bad'):
                user.write_text('files='+value+'\n')
                with self.assertRaises(RuntimeError):B.role_configuration([system,user])
            user.unlink();user.symlink_to(system)
            with self.assertRaises(RuntimeError):B.role_configuration([system,user])
            user.unlink();user.symlink_to('absent')
            with self.assertRaises(RuntimeError):B.role_configuration([system,user])
    def test_role_parser_matches_literal_lf_helper_not_python_control_separators(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);system=root/'system';user=root/'user';system.write_bytes(b'files=nautilus\n')
            for separator in ('\r','\v','\f','\x1c','\x1d','\x1e','\x85','\u2028','\u2029'):
                for data in ('files=pcmanfm'+separator+'\n','files=nautilus'+separator+'files=pcmanfm\n'):
                    user.write_text(data)
                    with self.subTest(separator=repr(separator),data=repr(data)),self.assertRaises(RuntimeError):
                        B.role_configuration([system,user])
            user.write_bytes(b'ignored\nfiles=pcmanfm\n')
            self.assertEqual(B.role_configuration([system,user])[0],'pcmanfm')
    def test_nonce_program_identity_set_before_actual_gtk_initialization(self):
        tree=ast.parse((HERE/'gtk-entry-control.py').read_text())
        main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        calls=[n for n in ast.walk(main) if isinstance(n,ast.Call)]
        set_name=next(n for n in calls if ast.unparse(n.func)=='GLib.set_prgname')
        application=next(n for n in calls if ast.unparse(n.func)=='Gtk.Application')
        self.assertLess(set_name.lineno,application.lineno)
        self.assertIn('program_name=GLib.get_prgname()', (HERE/'gtk-entry-control.py').read_text())
    def test_gtk_nonce_pid_start_title_program_backend_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);appid='org.arctic.Diagnostic.Entry.a'+'b'*16;proof=dict(pid=10,start_ticks=20)
            client=dict(appid=appid,title='Arctic Gtk3 diagnostic '+appid,is_xwayland=False)
            mapped=dict(event='mapped',pid=10,uid=1000,start_ticks=20,appid=appid,program_name=appid,backend='GdkWaylandDisplay')
            smoke=types.SimpleNamespace(root=root,uid=1000,alive=lambda _:copy.deepcopy(client))
            path=root/'gtk-events.log';path.write_text(json.dumps(mapped)+'\n');G.validate_gtk_identity(smoke,proof,appid)
            for key,value in [('pid',11),('start_ticks',21),('program_name','gtk-entry-control.py'),('backend','GdkX11Display')]:
                bad=dict(mapped,**{key:value});path.write_text(json.dumps(bad)+'\n')
                with self.assertRaises(RuntimeError):G.validate_gtk_identity(smoke,proof,appid)
            path.write_text(json.dumps(mapped)+'\n');client['appid']='gtk-entry-control.py'
            with self.assertRaises(RuntimeError):G.validate_gtk_identity(smoke,proof,appid)
    def test_empty_redirected_wayland_streams_are_failure_not_telemetry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);smoke=types.SimpleNamespace(root=root)
            for name in ('pcmanfm-stdout.log','pcmanfm-wayland-stderr.log'):(root/name).write_bytes(b'')
            empty=dict(complete=True,error=None,only_owned_direct_child_reaped=True,bytes_observed=0,
                combined_limit_bytes=2*1024*1024,streams={k:dict(bytes=0,sha256=hashlib.sha256(b'').hexdigest()) for k in ('stdout','stderr')})
            (root/'pcmanfm-owned-completion.json').write_text(json.dumps(empty))
            with self.assertRaisesRegex(RuntimeError,'empty'):G.direct_capture(smoke)
            path=root/'pcmanfm-wayland-stderr.log';path.write_bytes(b'[1] wl_display#1.get_registry(2)\n[2] wl_keyboard#7.keymap(1,2,3)\n')
            completion=dict(complete=True,error=None,only_owned_direct_child_reaped=True,
                bytes_observed=path.stat().st_size,combined_limit_bytes=2*1024*1024,
                streams={'stdout':dict(bytes=0,sha256=B.digest(root/'pcmanfm-stdout.log')),
                         'stderr':dict(bytes=path.stat().st_size,sha256=B.digest(path))})
            (root/'pcmanfm-owned-completion.json').write_text(json.dumps(completion))
            self.assertTrue(G.direct_capture(smoke)['complete']);self.assertEqual(G.direct_capture(smoke)['received_keyboard_key_lines'],0)
            path.write_bytes(b'wl_keyboard#7.key(1,2,28,1)')
            completion['bytes_observed']=path.stat().st_size;completion['streams']['stderr']=dict(bytes=path.stat().st_size,sha256=B.digest(path))
            (root/'pcmanfm-owned-completion.json').write_text(json.dumps(completion))
            with self.assertRaisesRegex(RuntimeError,'partial'):G.direct_capture(smoke)
    def test_wrong_producer_completion_stream_hash_bytes_and_cleanup_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);smoke=types.SimpleNamespace(root=root)
            (root/'pcmanfm-stdout.log').write_bytes(b'')
            path=root/'pcmanfm-wayland-stderr.log';path.write_bytes(b'wl_display#1.get_registry(2)\nwl_keyboard#2.keymap(1,2,3)\n')
            good=dict(complete=True,error=None,only_owned_direct_child_reaped=True,bytes_observed=path.stat().st_size,
                combined_limit_bytes=2*1024*1024,streams={'stdout':dict(bytes=0,sha256=B.digest(root/'pcmanfm-stdout.log')),
                'stderr':dict(bytes=path.stat().st_size,sha256=B.digest(path))})
            for name in ('complete','error','reaped','boolean-bytes','hash'):
                row=copy.deepcopy(good)
                if name=='complete':row['complete']=False
                elif name=='error':row['error']='actual overflow'
                elif name=='reaped':row['only_owned_direct_child_reaped']=False
                elif name=='boolean-bytes':row['bytes_observed']=True
                else:row['streams']['stderr']['sha256']='0'*64
                (root/'pcmanfm-owned-completion.json').write_text(json.dumps(row))
                with self.subTest(case=name),self.assertRaises(RuntimeError):G.direct_capture(smoke)


if __name__=='__main__':
    unittest.main(verbosity=2)
