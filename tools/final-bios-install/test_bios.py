#!/usr/bin/env python3
"""Source-only BIOS predicates, original protocol, and owned process boundaries."""
import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
import common as C
import guest as G
import run as R

UUID='11111111-1111-1111-1111-111111111111'
CTX=dict(schema='arctic-final-bios-context-v1',nonce='a'*32,execution_sha='b'*40,source_sha='326690f173d4dc4f049f43e046c8380e66825a07',iso_sha256='807eaaa64ab8480ec2b18bc8434fd5e37d82c41b73a3e0a6f002c35d152ba54c',probe_sha256='c'*64,native_sha256='d'*64,security_sha256='e'*64)

def report(stage):
    p=dict(firmware='bios',efi_present=False,live_medium=stage=='live',boot_id=UUID,desktop_uid=1000,security=dict(selinux='Enforcing',audit=dict(enabled=1,lost=0),observed_new_avcs=0,audit_enabled=True,scope=R.SECURITY_SCOPE))
    if stage=='installed':p.update(root=dict(fstype='btrfs',encrypted=True,target='vda',luks_uuid=UUID),offline_queue=G.queue_predicate(dict(ok=False,ready=False,state='error',download_bytes=506181191),dict(version='1.1.0'),False,'enabled'))
    return dict(schema='arctic-final-bios-report-v1',context=CTX,stage=stage,status='passed',guest_sha256='f'*64,proof=p,release_acceptance=False)

def wire(stage):
    row=('ARCTIC-FINAL-BIOS '+json.dumps(report(stage),separators=(',',':'))+'\n').encode()
    if stage=='live':return row+b'ARCTIC-OFFLINE-HTTP-RESPONSE=000\nARCTIC-OFFLINE-GATE=passed: restricted QEMU network, no outside HTTP response\nARCTIC-LIVE-SMOKE-EXIT=0\nARCTIC-INSTALL-EXIT=0\n'
    return b'ARCTIC-COLLECT-BEGIN\n'+row+b'ARCTIC-INSTALLED-SMOKE-EXIT=0\nARCTIC-COLLECT-END\n'

class BIOSControls(unittest.TestCase):
    def test_actual_qemu_constructor_bios_has_q35_kvm_no_pflash_and_only_owned_disk(self):
        raw=subprocess.check_output(['git','-C',str(C.ROOT),'show',CTX['source_sha']+':tools/test-install.sh']).decode()
        body=raw[raw.index("def qemu_argv("):raw.index("def dictation_network_argv(")]
        tree=ast.parse(body);node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='qemu_argv')
        env=dict(E={'INSTALL_NETWORK':'offline','BOOT_NETWORK':'offline'},out='/owned/vm',fw='bios',accel='kvm',smp='2',mem='4096')
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<actual SourceA qemu_argv>','exec'),env)
        for stage in ('install','boot'):
            argv=env['qemu_argv'](stage,stage=='install')
            self.assertEqual(argv[argv.index('-machine')+1],'q35');self.assertEqual(argv[argv.index('-accel')+1],'kvm')
            self.assertFalse(any('pflash' in x or 'OVMF' in x for x in argv));self.assertEqual(sum('target.qcow2' in x for x in argv),1)
        env['fw']='uefi';self.assertTrue(any('pflash' in x for x in env['qemu_argv']('boot',False)))

    def test_firmware_stage_and_efi_poison_are_actual_files(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);sr=p/'sys';pr=p/'proc';(sr/'firmware').mkdir(parents=True);(pr/'sys/kernel/random').mkdir(parents=True)
            (pr/'sys/kernel/random/boot_id').write_text(UUID);(pr/'cmdline').write_text('rd.live.image console=ttyS0')
            self.assertEqual(G.firmware('live',sr,pr)['efi_present'],False)
            with self.assertRaises(RuntimeError):G.firmware('installed',sr,pr)
            (pr/'cmdline').write_text('root=/dev/mapper/owned');self.assertFalse(G.firmware('installed',sr,pr)['live_medium'])
            (sr/'firmware/efi').symlink_to(p/'absent')
            with self.assertRaises(RuntimeError):G.firmware('installed',sr,pr)

    def test_root_binding_uses_real_sysfs_links_and_rejects_foreign_disk(self):
        with tempfile.TemporaryDirectory() as d:
            sr=Path(d);(sr/'class/block').mkdir(parents=True);disk=sr/'devices/pci/virtio/vda';(disk/'vda2').mkdir(parents=True)
            driver=sr/'drivers/virtio_blk';driver.mkdir(parents=True);(disk/'device').mkdir();(disk/'device/driver').symlink_to(driver)
            (sr/'class/block/vda').symlink_to(disk);(sr/'class/block/vda2').symlink_to(disk/'vda2')
            def output(argv):
                if argv[0]=='findmnt':return 'btrfs' if 'FSTYPE' in argv else '/dev/mapper/luks-owned'
                return UUID if argv[1]=='luksUUID' else ' type: LUKS2\n device: /dev/vda2\n'
            with patch.object(G,'text',output):self.assertEqual(G.encrypted_root(sr)['target'],'vda')
            (sr/'class/block/vda2').unlink();foreign=sr/'devices/foreign/vdb';(foreign/'vda2').mkdir(parents=True);(sr/'class/block/vda2').symlink_to(foreign/'vda2')
            with patch.object(G,'text',output),self.assertRaises(RuntimeError):G.encrypted_root(sr)

    def test_original_queue_predicates_reject_ready_missing_pending_payload_and_false_timer(self):
        good=dict(ok=False,ready=False,state='error',download_bytes=506181191)
        self.assertFalse(G.queue_predicate(good,{'version':'1.1.0'},False,'enabled')['ready'])
        variants=[({**good,'ready':True},{'version':'1.1.0'},False,'enabled'),(good,{},False,'enabled'),(good,{'version':'1.1.0'},True,'enabled'),(good,{'version':'1.1.0'},False,'disabled'),({**good,'download_bytes':1},{'version':'1.1.0'},False,'enabled')]
        for args in variants:
            with self.subTest(args=args),self.assertRaises(RuntimeError):G.queue_predicate(*args)

    def test_protected_fifo_is_nonblocking_and_symlink_never_opened(self):
        with tempfile.TemporaryDirectory() as d:
            fifo=Path(d)/'fifo';os.mkfifo(fifo)
            with self.assertRaises(RuntimeError):G.protected(fifo)
            link=Path(d)/'alias';link.symlink_to(fifo)
            with self.assertRaises(OSError):G.protected(link)

    def test_duplicate_nonfinite_context_and_replay_are_rejected(self):
        for data in ('{"a":1,"a":2}','{"a":NaN}'):
            with self.assertRaises((RuntimeError,ValueError)):G.strict_json(data)
        for key,value in (('source_sha','0'*40),('nonce',True),('iso_sha256','f'*64)):
            with self.assertRaises(RuntimeError):G.context({**CTX,key:value})

    def test_actual_live_and_installed_probe_finalize_security_on_primary_failure(self):
        for stage in ('live','installed'):
            calls=[]
            class Interval:
                def __init__(self):calls.append('begin')
                def finish(self):calls.append('finish');return report(stage)['proof']['security']
            native=types.SimpleNamespace(discover_desktop=lambda:(_ for _ in ()).throw(ValueError('private primary input')))
            def output(argv):return 'qemu' if argv[0]=='systemd-detect-virt' else 'Enforcing'
            with patch.object(G,'__file__','/run/t/guest-check.py'),patch.object(G.os,'geteuid',return_value=0),patch.object(G,'text',output),patch.object(G,'firmware',return_value=report(stage)['proof']),self.assertRaisesRegex(RuntimeError,'^bios-check-failed$'):
                G.main(stage,CTX,native,Interval)
            self.assertEqual(calls,['begin','finish'])

    def test_source_checker_cd_requires_actual_readonly_mount_and_permitted_owner(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'checker';p.write_bytes(b'public-source');p.chmod(0o600)
            self.assertEqual(G.protected(p,4096,owner=False),b'public-source')
            p.chmod(0o622)
            with self.assertRaises(RuntimeError):G.protected(p,4096,owner=False)
        import contextlib,io
        for fstype,options,passed in [('iso9660','ro,nosuid',True),('iso9660','rw',False),('tmpfs','ro',False)]:
            class Interval:
                def finish(self):return report('live')['proof']['security']
            native=types.SimpleNamespace(discover_desktop=lambda:['runuser','-u','liveuser','--','env'])
            def output(argv):
                if argv[0]=='systemd-detect-virt':return 'qemu'
                if argv[0]=='getenforce':return 'Enforcing'
                if argv[0]=='findmnt':return fstype if 'FSTYPE' in argv else options
                return '1000'
            stdout=io.StringIO()
            with patch.object(G,'__file__','/run/t/guest-check.py'),patch.object(G.os,'geteuid',return_value=0),patch.object(G,'text',output),patch.object(G,'firmware',return_value={k:v for k,v in report('live')['proof'].items() if k in ('firmware','efi_present','live_medium','boot_id')}),patch.object(G.pwd,'getpwnam',return_value=types.SimpleNamespace(pw_uid=1000)),patch.object(G,'protected',return_value=b'exact-checker'),contextlib.redirect_stdout(stdout):
                if passed:self.assertEqual(G.main('live',CTX,native,Interval),0)
                else:
                    with self.assertRaisesRegex(RuntimeError,'read-only-source-cd'):G.main('live',CTX,native,Interval)
            self.assertEqual(bool(stdout.getvalue()),passed)

    def test_original_protocol_accepts_both_stages_and_rejects_missing_duplicate_failure(self):
        scanner=types.SimpleNamespace(external_text=lambda x:x)
        for stage in ('live','installed'):
            self.assertEqual(R.records(wire(stage),CTX,stage,'f'*64,scanner)['stage'],stage)
            row=('ARCTIC-FINAL-BIOS '+json.dumps(report(stage))+'\n').encode()
            for raw in (wire(stage)+row,wire(stage)+b'ARCTIC-FINAL-BIOS-FAILED\n',wire(stage).replace(row.split(b' ',1)[0],b'UNKNOWN',1),wire(stage)+('ARCTIC-'+('LIVE' if stage=='live' else 'INSTALLED')+'-SMOKE-EXIT=1\n').encode()):
                with self.assertRaises(RuntimeError):R.records(raw,CTX,stage,'f'*64,scanner)
        with self.assertRaises(RuntimeError):R.records(wire('installed'),{**CTX,'nonce':'1'*32},'installed','f'*64,scanner)

    def test_whole_privacy_failure_precedes_protocol_and_never_repairs_uart(self):
        scanner=types.SimpleNamespace(external_text=lambda x:(_ for _ in ()).throw(RuntimeError('original private rejection')))
        with self.assertRaisesRegex(RuntimeError,'original private rejection'):R.records(wire('live'),CTX,'live','f'*64,scanner)
        scanner=types.SimpleNamespace(external_text=lambda x:x.replace(b'ARCTIC',b'REPAIRED'))
        with self.assertRaises(RuntimeError):R.records(wire('live'),CTX,'live','f'*64,scanner)

    def test_original_marker_order_and_outside_response_poison_fail(self):
        scanner=types.SimpleNamespace(external_text=lambda x:x)
        for raw in (wire('live')+b'ARCTIC-OFFLINE-HTTP-RESPONSE=200\n',wire('installed').replace(b'ARCTIC-COLLECT-BEGIN\n',b'')+b'ARCTIC-COLLECT-BEGIN\n'):
            stage='live' if b'ARCTIC-INSTALL-EXIT' in raw else 'installed'
            with self.assertRaises(RuntimeError):R.records(raw,CTX,stage,'f'*64,scanner)

    def test_actual_source_scanner_keeps_reports_original_and_private_append_fails(self):
        raw=subprocess.check_output(['git','-C',str(C.ROOT),'show',CTX['source_sha']+':tools/native-functional/screen-evidence.py'])
        module=types.ModuleType('actual_bios_privacy');module.__file__='<actual SourceA scanner>';exec(compile(raw,module.__file__,'exec'),module.__dict__)
        for stage in ('live','installed'):
            original=wire(stage);self.assertEqual(module.external_text(original),original)
            with self.assertRaises(RuntimeError):R.records(original+b'password=private-canary\n',CTX,stage,'f'*64,module)

    def test_security_bool_avc_enforcing_and_root_poison_reject(self):
        for mutate in (lambda p:p['security'].update(observed_new_avcs=1),lambda p:p['security'].update(selinux='Permissive'),lambda p:p['security']['audit'].update(lost=True),lambda p:p['root'].update(target='vdb'),lambda p:p['offline_queue'].update(ready=True)):
            value=report('installed');mutate(value['proof'])
            with self.assertRaises(RuntimeError):R.validate_report(value,CTX,'installed','f'*64)

    def test_compose_executes_pinned_snapshots_after_path_replacement_and_forwards_stage(self):
        import compose
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'tools/native-functional').mkdir(parents=True)
            native=root/'tools/native-functional/native_smoke.py';native.write_text('VALUE=23\n')
            probe=root/'probe.py';probe.write_text('def main(stage,ctx,native,interval):\n    print("COMPOSED-STAGE="+stage+" VALUE="+str(interval))\n    return 0\n')
            security=root/'security.py';security.write_text('def interval_type(native):return native.VALUE\n')
            ctx={**CTX,'probe_sha256':hashlib.sha256(probe.read_bytes()).hexdigest(),'native_sha256':hashlib.sha256(native.read_bytes()).hexdigest(),'security_sha256':hashlib.sha256(security.read_bytes()).hexdigest()}
            output=root/'generated.py';actual=compose.compose(root,probe,security,ctx,output)
            self.assertEqual(actual,hashlib.sha256(output.read_bytes()).hexdigest())
            probe.write_text('raise RuntimeError("foreign path reload")\n');native.write_text('raise RuntimeError("foreign path reload")\n')
            result=subprocess.run([sys.executable,'-B',str(output),'installed'],capture_output=True,timeout=3)
            self.assertEqual((result.returncode,result.stdout,result.stderr),(0,b'COMPOSED-STAGE=installed VALUE=23\n',b''))
            with self.assertRaises(RuntimeError):compose.compose(root,probe,security,ctx,root/'poisoned.py')
            self.assertFalse((root/'poisoned.py').exists())

    def test_actual_source_composition_binds_all_three_modules_without_guest_execution(self):
        import base64,compose
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'source';(source/'tools/native-functional').mkdir(parents=True)
            native=source/'tools/native-functional/native_smoke.py'
            native.write_bytes(subprocess.check_output(['git','-C',str(C.ROOT),'show',CTX['source_sha']+':tools/native-functional/native_smoke.py']))
            probe=Path(__file__).with_name('guest.py');security=Path(__file__).with_name('security.py')
            ctx={**CTX,'native_sha256':hashlib.sha256(native.read_bytes()).hexdigest(),'probe_sha256':hashlib.sha256(probe.read_bytes()).hexdigest(),'security_sha256':hashlib.sha256(security.read_bytes()).hexdigest()}
            output=Path(d)/'guest-check.py';actual=compose.compose(source,probe,security,ctx,output)
            self.assertEqual(actual,hashlib.sha256(output.read_bytes()).hexdigest())
            tree=ast.parse(output.read_bytes());encoded=[n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_raw' for t in n.targets)]
            self.assertEqual([base64.b64decode(ast.literal_eval(n.value.args[0]),validate=True) for n in encoded],[probe.read_bytes(),native.read_bytes(),security.read_bytes()])
            result=subprocess.run([sys.executable,'-B',str(output),'foreign-stage'],capture_output=True,timeout=3)
            self.assertEqual((result.returncode,result.stdout,result.stderr),(1,b'ARCTIC-FINAL-BIOS-FAILED\n',b''))
            with self.assertRaises(RuntimeError):compose.compose(source,probe,security,{**ctx,'security_sha256':'0'*64},Path(d)/'wrong.py')
            self.assertFalse((Path(d)/'wrong.py').exists())

    def test_snapshot_loader_executes_only_read_bytes_under_path_swap(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'m.py';raw=b'VALUE=17\n';p.write_bytes(raw);real=C.regular
            def acquired(path,limit):
                data=real(path,limit);p.write_text('raise RuntimeError("foreign source")\n');return data
            with patch.object(C,'regular',acquired):self.assertEqual(C.load(p,'owned_snapshot',hashlib.sha256(raw).hexdigest()).VALUE,17)

    def test_whole_original_png_structure_rejects_private_trailer_metadata_crc_and_missing_end(self):
        import io,struct,zlib
        from PIL import Image
        output=io.BytesIO();Image.new('RGB',(640,480)).save(output,format='PNG');raw=output.getvalue()
        self.assertEqual(R.original_png(raw),raw)
        body=b'password=private-canary';chunk=struct.pack('>I',len(body))+b'tEXt'+body+struct.pack('>I',zlib.crc32(b'tEXt'+body)&0xffffffff)
        variants=[raw+b'private-canary',raw[:-12],raw[:-12]+chunk+raw[-12:],raw[:29]+bytes([raw[29]^1])+raw[30:]]
        for data in variants:
            with self.subTest(bytes=len(data)),self.assertRaises(RuntimeError):R.original_png(data)

    def test_publication_is_atomic_under_second_file_write_failure(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);(out/'private').mkdir();real=C.exclusive;calls=[]
            def write(path,data):
                calls.append(path)
                if len(calls)==2:raise OSError('owned test write failure')
                real(path,data)
            with patch.object(C,'exclusive',write),self.assertRaises(OSError):R.publish(out,{'host-status.json':b'{}','boot-99-final.png':b'original'})
            self.assertFalse((out/'public').exists());self.assertEqual((out/'private/staged-public/host-status.json').read_bytes(),b'{}')

    def test_host_invocation_failed_child_and_timeout_remain_failures(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaises(RuntimeError):R.execute([sys.executable,'-c','raise SystemExit(7)'],root/'fail',3,root,os.environ.copy())
            with self.assertRaises(RuntimeError):R.execute([sys.executable,'-c','import time;time.sleep(30)'],root/'deadline',.2,root,os.environ.copy())

    def test_host_popen_signal_handoff_reaps_owned_child_and_preserves_canary(self):
        real=subprocess.Popen;owned=[]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);canary=real([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True)
            try:
                def launch(*a,**k):
                    child=real(*a,**k);owned.append(child);os.kill(os.getpid(),signal.SIGTERM);return child
                with patch.object(R.subprocess,'Popen',launch),self.assertRaisesRegex(RuntimeError,'interrupted'):
                    R.execute([sys.executable,'-c','import time;time.sleep(30)'],p/'handoff',3,p,os.environ.copy())
                self.assertIsNotNone(owned[0].returncode);self.assertIsNone(canary.poll())
            finally:canary.terminate();canary.wait(timeout=3)

    def test_repeated_acquisition_cleanup_transition_signals_stop_owned_child(self):
        real_launch=subprocess.Popen;real_signal=signal.signal;original_handlers={s:signal.getsignal(s) for s in (signal.SIGTERM,signal.SIGINT)}
        owned=[];changes=[];injected=[]
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);canary=real_launch([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True)
            try:
                def launch(*args,**kwargs):
                    child=real_launch(*args,**kwargs);owned.append(child);signal.raise_signal(signal.SIGTERM);return child
                def change(signum,handler):
                    result=real_signal(signum,handler);changes.append(signum)
                    if len(changes)==3:
                        injected.append(True);signal.raise_signal(signal.SIGINT)
                    return result
                with patch.object(R.subprocess,'Popen',side_effect=launch),patch.object(R.signal,'signal',side_effect=change),self.assertRaisesRegex(RuntimeError,'^Owned BIOS host invocation interrupted$'):
                    R.execute([sys.executable,'-c','import time;time.sleep(30)'],root/'repeated',3,root,os.environ.copy())
                self.assertEqual(injected,[True]);self.assertIsNotNone(owned[0].returncode);self.assertIsNone(canary.poll())
            finally:
                for s,handler in original_handlers.items():real_signal(s,handler)
                for child in owned:
                    if child.poll() is None:os.killpg(child.pid,signal.SIGKILL)
                    child.wait(timeout=3)
                canary.terminate();canary.wait(timeout=3)

    def test_cleanup_repeated_signals_preserve_original_failed_exit_and_own_group(self):
        real_kill=os.killpg;calls=[]
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);canary=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True)
            try:
                def stop(pid,signum):
                    calls.append((pid,signum));signal.raise_signal(signal.SIGTERM);signal.raise_signal(signal.SIGINT);return real_kill(pid,signum)
                with patch.object(R.os,'killpg',side_effect=stop),self.assertRaisesRegex(RuntimeError,'^BIOS host invocation failed$'):
                    R.execute([sys.executable,'-c','raise SystemExit(7)'],root/'failed-exit',3,root,os.environ.copy())
                self.assertTrue(calls);self.assertTrue(all(pid!=canary.pid for pid,_ in calls));self.assertIsNone(canary.poll())
            finally:canary.terminate();canary.wait(timeout=3)

    def test_cleanup_term_syscall_failure_still_kills_reaps_and_preserves_primary(self):
        import errno
        real_launch=subprocess.Popen;real_kill=os.killpg;owned=[];calls=[]
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);canary=real_launch([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True)
            try:
                def launch(*args,**kwargs):
                    child=real_launch(*args,**kwargs);owned.append(child);signal.raise_signal(signal.SIGTERM);return child
                def stop(pid,signum):
                    self.assertEqual(pid,owned[0].pid);calls.append(signum)
                    if signum==signal.SIGTERM:raise OSError(errno.EIO,'synthetic owned TERM syscall failure')
                    return real_kill(pid,signum)
                with patch.object(R.subprocess,'Popen',side_effect=launch),patch.object(R.os,'killpg',side_effect=stop),self.assertRaisesRegex(RuntimeError,'^Owned BIOS host invocation interrupted$'):
                    R.execute([sys.executable,'-c','import time;time.sleep(30)'],root/'term-fault',3,root,os.environ.copy())
                self.assertEqual(calls,[signal.SIGTERM,signal.SIGKILL]);self.assertIsNotNone(owned[0].returncode);self.assertIsNone(canary.poll())
            finally:
                for child in owned:
                    if child.poll() is None:real_kill(child.pid,signal.SIGKILL)
                    child.wait(timeout=3)
                canary.terminate();canary.wait(timeout=3)

    def test_already_reaped_leader_refuses_group_signal_without_reservation(self):
        real_launch=subprocess.Popen;owned=[]
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);canary=real_launch([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True)
            try:
                def launch(*args,**kwargs):
                    child=real_launch(*args,**kwargs);owned.append(child);child.wait(timeout=3);signal.raise_signal(signal.SIGTERM);return child
                with patch.object(R.subprocess,'Popen',side_effect=launch),patch.object(R.os,'killpg') as stop,self.assertRaisesRegex(RuntimeError,'^Owned BIOS host invocation interrupted$'):
                    R.execute([sys.executable,'-c','raise SystemExit(0)'],root/'foreign-reap',3,root,os.environ.copy())
                stop.assert_not_called();self.assertEqual(owned[0].returncode,0);self.assertIsNone(canary.poll())
            finally:
                for child in owned:child.wait(timeout=3)
                canary.terminate();canary.wait(timeout=3)

    def test_main_cleanup_transition_preserves_failure_and_recovers_only_owned_image(self):
        # Only hosted/KVM/tool metadata is simulated. Actual Python signal handlers,
        # Source composition, source privacy scanner and atomic publication execute.
        actual_regular=C.regular;actual_char=Path.is_char_device;real_signal=signal.signal;real_run=subprocess.run
        original_handlers={s:signal.getsignal(s) for s in (signal.SIGTERM,signal.SIGINT)};changes=[];cleaned=[]
        manifest=C.strict_json(Path(__file__).with_name('execution-manifest.json').read_bytes());manifest['ready']=True
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source';(source/'tools/native-functional').mkdir(parents=True)
            (source/'tools/native-functional/native_smoke.py').write_bytes(subprocess.check_output(['git','-C',str(C.ROOT),'show',CTX['source_sha']+':tools/native-functional/native_smoke.py']))
            out=root/'evidence';image='sha256:'+'a'*64
            def regular(path,limit):
                return json.dumps(manifest).encode() if Path(path)==Path(R.__file__).with_name('execution-manifest.json') else actual_regular(path,limit)
            def change(signum,handler):
                result=real_signal(signum,handler);changes.append(signum)
                if len(changes)==3 or (signum==signal.SIGTERM and getattr(handler,'__name__',None)=='<lambda>'):signal.raise_signal(signal.SIGINT)
                return result
            def recover(private,task,container):
                signal.raise_signal(signal.SIGTERM);signal.raise_signal(signal.SIGINT)
                self.assertEqual(private,out/'private');self.assertTrue(container.startswith('arctic-paired-'+task+'-'));return image
            def docker(argv,**kwargs):
                if argv[0]!='docker':return real_run(argv,**kwargs)
                self.assertEqual(argv,['docker','image','rm','--no-prune',image]);cleaned.append(image);return types.SimpleNamespace(returncode=0)
            try:
                with patch.object(sys,'argv',['bios','--source',str(source),'--inputs',str(root/'absent-inputs'),'--out',str(out)]),patch.object(C,'regular',side_effect=regular),patch.object(C,'guard',return_value={'Source_only_synthetic_host_metadata':True}),patch.object(Path,'is_char_device',lambda path:True if str(path)=='/dev/kvm' else actual_char(path)),patch.object(R,'execute',side_effect=RuntimeError('private synthetic original preparation failure')),patch.object(R,'recover_prepared_image',side_effect=recover),patch.object(R.subprocess,'run',side_effect=docker),patch.object(R.signal,'signal',side_effect=change):
                    self.assertEqual(R.main(),1)
                self.assertEqual(cleaned,[image]);state=json.loads((out/'public/host-status.json').read_bytes());self.assertEqual((state['status'],state['phase'],state['error_class']),('failed','provision','RuntimeError'));self.assertIsNone(state['result']);self.assertFalse(state['release_acceptance']);self.assertNotIn(b'private synthetic',(out/'public/host-status.json').read_bytes())
            finally:
                for s,handler in original_handlers.items():real_signal(s,handler)

    def test_inherited_fixture_and_secret_environment_cannot_change_original_harness(self):
        with patch.dict(os.environ,{'ARCTIC_NATIVE_AUDIO_FIXTURE':'1','ARCTIC_NATIVE_TASKBAR_BUNDLE':'/foreign','ARCTIC_FEDORA_IMAGE':'foreign-image','ARCTIC_CA_BUNDLE':'/foreign-ca','GH_TOKEN':'private-canary','GITHUB_TOKEN':'private-canary','CONTAINER_ENGINE':'podman'}):
            env=R.harness_environment('owned-name','sha256:'+'a'*64)
        self.assertEqual({k:v for k,v in env.items() if k.startswith('ARCTIC_')},{'ARCTIC_VM_CONTAINER_NAME':'owned-name','ARCTIC_FEDORA_IMAGE':'sha256:'+'a'*64,'ARCTIC_VM_TOOLS_PREPARED':'1'})
        self.assertEqual(env['CONTAINER_ENGINE'],'docker');self.assertNotIn('GH_TOKEN',env);self.assertNotIn('GITHUB_TOKEN',env)

    def test_owned_container_cleanup_rejects_foreign_identity_without_mutation(self):
        row={'Name':'/owned','Image':'sha256:'+'a'*64,'Id':'b'*64,'Mounts':[{'Source':'/foreign','Destination':'/vm'}]}
        result=types.SimpleNamespace(returncode=0,stdout=json.dumps([row]).encode())
        with patch.object(R.subprocess,'run',return_value=result) as call,self.assertRaises(RuntimeError):R.remove_owned_container('owned','sha256:'+'a'*64,Path('/vm'))
        self.assertEqual(call.call_count,1)

    def test_prepared_image_cancellation_recovers_only_exclusive_source_owner(self):
        task='a'*32;container='arctic-paired-'+task+'-12345678';image='sha256:'+'b'*64;base='sha256:'+'c'*64
        with tempfile.TemporaryDirectory() as d:
            private=Path(d)
            self.assertIsNone(R.recover_prepared_image(private,task,container))
            value=dict(schema='arctic-paired-test-image-owner-v1',release_acceptance=False,task_id=task,container=container,base_id=base)
            (private/'vm-prepared-image-owner.json').write_text(json.dumps(value))
            labels={'org.arctic.test.vm-tools.task':task,'org.arctic.test.vm-tools.container':container,'org.arctic.test.vm-tools.scope':'paired-v1','org.arctic.test.vm-tools.base':base}
            result=types.SimpleNamespace(stdout=(image+'\n').encode())
            with patch.object(R.subprocess,'run',return_value=result) as calls,patch.object(R.subprocess,'check_output',return_value=json.dumps(labels).encode()):
                self.assertEqual(R.recover_prepared_image(private,task,container),image)
                self.assertTrue(all('rm' not in call.args[0] for call in calls.call_args_list))
            for wrong in ({**labels,'org.arctic.test.vm-tools.base':'sha256:'+'d'*64},{**labels,'org.arctic.test.vm-tools.task':'f'*32}):
                with patch.object(R.subprocess,'run',return_value=result),patch.object(R.subprocess,'check_output',return_value=json.dumps(wrong).encode()),self.assertRaises(RuntimeError):R.recover_prepared_image(private,task,container)
            result.stdout=(image+'\nsha256:'+'d'*64+'\n').encode()
            with patch.object(R.subprocess,'run',return_value=result),patch.object(R.subprocess,'check_output') as inspect,self.assertRaises(RuntimeError):R.recover_prepared_image(private,task,container)
            inspect.assert_not_called()

    def test_security_adapter_isolates_exact_stream_and_retains_source_predicates(self):
        import security
        raw=subprocess.check_output(['git','-C',str(C.ROOT),'show',CTX['source_sha']+':tools/native-functional/native_smoke.py'])
        native=types.ModuleType('actual_source_a_bios_security');native.__file__='/run/t/guest-check.py'
        exec(compile(raw,native.__file__,'exec'),native.__dict__)
        original=dict(native.__dict__);interval=security.interval_type(native)
        self.assertEqual(native.__dict__,original)
        for name in ('verify_security','parse_audit_status','discover_desktop','guest_guard','execute','AVC','LIMIT'):
            self.assertIs(interval.finish.__globals__[name],original[name])
        self.assertIsNot(interval,original['SecurityInterval'])
        stream=interval.finish.__globals__['execute_journal_interval']
        for records,passed in [([{'MESSAGE':'ordinary public record'}],True),([{'MESSAGE':['ordinary','avc: denied public synthetic control']}],False)]:
            code='import json\nfor row in '+repr(records)+':print(json.dumps(row),flush=True)\n'
            with tempfile.TemporaryDirectory() as d:
                value=interval.__new__(interval);value.before={'selinux':'Enforcing','audit':{'enabled':1,'lost':0}}
                value.cursor='synthetic-owned-cursor';value.audit_file=Path(d)/'absent-audit';value.audit_offset=None
                namespace=interval.finish.__globals__;namespace['execute_journal_interval']=lambda argv,**kw:stream([sys.executable,'-c',code],timeout=2)
                with patch.object(interval,'state',return_value=copy.deepcopy(value.before)):
                    if passed:self.assertEqual(value.finish()['observed_new_avcs'],0)
                    else:
                        with self.assertRaisesRegex(RuntimeError,'new AVC requires investigation'):value.finish()
                namespace['execute_journal_interval']=stream
        poison=types.ModuleType('missing_original_security');poison.__dict__.update(native.__dict__);del poison.__dict__['verify_security']
        with self.assertRaisesRegex(RuntimeError,'Original SourceA security namespace differs'):security.interval_type(poison)

    def test_disabled_manifest_exact_image_budgets_pins_and_original_harness_arguments(self):
        value=C.strict_json(Path(__file__).with_name('execution-manifest.json').read_bytes())
        self.assertIs(C.manifest(value)['ready'],False)
        with self.assertRaisesRegex(RuntimeError,'remains disabled'):C.manifest(value,True)
        operational={**value,'ready':True}
        args=R.argv(Path('/owned/source'),Path('/owned/inputs'),Path('/owned/checker'),Path('/owned/vm'),operational)
        for option,wanted in (('--firmware','bios'),('--stage','all'),('--install-network','offline'),('--boot-network','offline'),('--install-timeout','2400')):
            self.assertEqual(args[args.index(option)+1],wanted)
        self.assertIn('--kvm',args);self.assertNotIn('--installer',args);self.assertNotIn('--guest-check-interactive',args)
        for change in ({'firmware':'uefi'},{'install_network':'online'},{'boot_network':'online'},{'install_timeout':True},{'harness_seconds':6601},{'release_acceptance':True},{'image':{**value['image'],'sha256':'0'*64}},{'execution_files':{}}):
            with self.subTest(change=tuple(change)),self.assertRaises(RuntimeError):C.manifest({**value,**change})

if __name__=='__main__':unittest.main(verbosity=2)
