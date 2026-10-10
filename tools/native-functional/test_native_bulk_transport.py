"""Synthetic original-byte bulk handoff controls; never boots or qualifies an image."""
import ast
import base64
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import zlib

HERE=Path(__file__).resolve().parent

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

E=load('native_bulk_evidence_checked',HERE/'evidence.py')
G=load('native_bulk_guest_checked',HERE/'guest-check-native-v6.py')
BOOT='11111111-2222-4333-8444-555555555555'

def sha(data):return hashlib.sha256(data).hexdigest()
def line(prefix,value):return prefix+' '+json.dumps(value,sort_keys=True)+'\n'

def fixture(stage='live',data=b'synthetic original evidence'):
    begin=dict(stage=stage,native_source_sha256=E.NATIVE_SOURCE_SHA,checker_sha256=E.CHECKERS['native-functional'][1],release_acceptance=False)
    proof=dict(begin,boot_id=BOOT)
    end=dict(stage=stage,status='passed',error=None,evidence_export_complete=True,release_acceptance=False)
    compressed=zlib.compress(data,9)
    entry=dict(path='owned.txt',bytes=len(data),sha256=sha(data),compressed_bytes=len(compressed),chunks=1,encoding='zlib+base64')
    manifest=dict(schema='arctic-native-evidence-v1',stage=stage,files=[entry],bytes=len(data),evidence_root='/tmp/arctic-native-smoke-fixture')
    stream=io.StringIO()
    class Port:
        def write(self,s):return stream.write(s)
        def close(self):pass
    with patch.object(G,'open_native_bulk_port',return_value=(Port(),{})):
        G.native_bulk_export([(entry,[compressed])],manifest,proof,begin)
    serial=('original UART preamble\n'+line('ARCTIC-NATIVE-RUNNER-BEGIN',begin)+line('ARCTIC-NATIVE-PROVENANCE',proof)
            +'ARCTIC-NATIVE-FUNCTIONAL {"original":"unchanged"}\n'+line('ARCTIC-NATIVE-RUNNER-END',end)+'original UART trailer\n')
    return serial,stream.getvalue().encode(),begin,proof,end

def refooter(rows):
    body=b''.join(rows[1:-1]);footer=json.loads(rows[-1].split(b' ',1)[1])
    footer.update(bytes=len(body),lines=len(rows)-2,sha256=sha(body))
    rows[-1]=line('ARCTIC-NATIVE-BULK-END',footer).encode();return b''.join(rows)


class BulkTransportControls(unittest.TestCase):
    def test_missing_port_and_secondary_close_error_preserve_primary_no_fallback(self):
        _,_,begin,proof,_=fixture()
        manifest=dict(schema='arctic-native-evidence-v1',stage='live',files=[],bytes=0,evidence_root=None)
        with patch.object(G,'open_native_bulk_port',side_effect=FileNotFoundError('mandatory port')), \
             patch('builtins.print') as uart:
            with self.assertRaises(FileNotFoundError):G.native_bulk_export([],manifest,proof,begin)
            uart.assert_not_called()
        class Port:
            closed=False
            def write(self,_):raise RuntimeError('original write failed')
            def close(self):self.closed=True;raise OSError('secondary close failed')
        port=Port()
        with patch.object(G,'open_native_bulk_port',return_value=(port,{})):
            with self.assertRaisesRegex(RuntimeError,'original write failed'):G.native_bulk_export([],manifest,proof,begin)
        self.assertTrue(port.closed)

    def test_protected_named_character_port_guards_and_output_only_open(self):
        expected={'/sys/class/virtio-ports/vport9p9/name':'arctic-native-evidence',
                  '/sys/class/virtio-ports/vport9p9/dev':'10:200'}
        metadata=SimpleNamespace(st_uid=0,st_mode=stat.S_IFDIR|0o755)
        class ModelPath:
            def __init__(self,value):self.value=str(value)
            def __truediv__(self,value):return ModelPath(self.value+'/'+value)
            @property
            def parent(self):return ModelPath(str(Path(self.value).parent))
            def resolve(self,strict):return Path('/dev/vport9p9')
            def stat(self):return metadata
            def read_text(self):return expected[self.value]
        actual=G.Path
        def paths(value):return ModelPath(value) if str(value).startswith(('/dev/virtio-ports','/sys/class/virtio-ports')) else actual(value)
        info=dict(st_uid=0,st_mode=stat.S_IFCHR|0o600,st_rdev=os.makedev(10,200))
        for mutated in [None,dict(st_uid=1000),dict(st_mode=stat.S_IFREG|0o600),dict(st_mode=stat.S_IFCHR|0o622),dict(st_rdev=os.makedev(10,201))]:
            value=SimpleNamespace(**dict(info,**(mutated or {})))
            with patch.object(G,'Path',side_effect=paths),patch.object(G.os,'open',return_value=17) as opened, \
                 patch.object(G.os,'fstat',return_value=value),patch.object(G.os,'close') as closed:
                if mutated is None:
                    writer,receipt=G.open_native_bulk_port();self.assertEqual(receipt['name'],'arctic-native-evidence');writer.close()
                    self.assertEqual(opened.call_args.args[1],os.O_WRONLY|os.O_NOFOLLOW|os.O_NOCTTY|os.O_NONBLOCK)
                else:
                    with self.assertRaises(RuntimeError):G.open_native_bulk_port()
                closed.assert_called_once_with(17)

    def test_failure_only_owned_QEMU_stop_record_closed_metadata(self):
        text=(HERE.parents[1]/'tools/test-install.sh').read_text();a=text.index('def record_native_stop(');z=text.index('\ndef close_taskbar_vm(',a)
        with tempfile.TemporaryDirectory() as tmp:
            for code,elapsed,reason in [(-11,104,'process-exited'),(0,104,'process-exited'),(None,2401,'deadline-expired'),(None,104,'exit-marker-missing')]:
                target=Path(tmp)/(str(code)+'-'+str(elapsed));target.mkdir()
                context=dict(E={'NATIVE_PHYSICAL_FIXTURE':'1','NATIVE_TASKBAR_FIXTURE':'1'},out=str(target),os=os,
                             time=SimpleNamespace(time=lambda:elapsed))
                exec(text[a:z],context)
                vm=SimpleNamespace(proc=SimpleNamespace(poll=lambda:code))
                context['record_native_stop'](vm,'install',0,2400,None)
                path=target/'native-stop-install.json';value=json.loads(path.read_text())
                self.assertEqual(set(value),{'schema','phase','qemu_returncode','elapsed_seconds','deadline_seconds','deadline_reached','exit_marker_present','reason','release_acceptance'})
                self.assertEqual(value['reason'],reason);self.assertEqual(value['qemu_returncode'],code)
                self.assertFalse(value['release_acceptance']);self.assertFalse(value['exit_marker_present'])
                self.assertEqual(value['deadline_reached'],elapsed>=2400)
                original=path.read_bytes();context['record_native_stop'](vm,'install',0,2400,None)
                self.assertEqual(path.read_bytes(),original)

    def test_exact_original_body_inserted_only_before_actual_END_for_both_stages(self):
        for stage in ('live','installed'):
            serial,wire,*_=fixture(stage)
            merged=E.reconcile_native_bulk(serial,wire,stage)
            body=b''.join(wire.splitlines(keepends=True)[1:-1]).decode()
            self.assertEqual(merged.replace(body,'',1),serial)
            self.assertTrue(merged.index(body)<merged.index('ARCTIC-NATIVE-RUNNER-END '))
            with tempfile.TemporaryDirectory() as tmp:
                copied=E.extract_evidence(E.native_block(merged,stage)[0],stage,Path(tmp)/'extract')
                self.assertEqual(copied['owned.txt']['sha256'],sha(b'synthetic original evidence'))

    def test_actual_guest_writer_uses_owned_nonblocking_pipe_no_UART(self):
        reader,writer=os.pipe2(os.O_NONBLOCK)
        port=G.NativeBulkWriter(writer)
        try:
            port.write('bounded original\n')
            self.assertEqual(os.read(reader,100),b'bounded original\n')
            port.close();port.close()
            with self.assertRaises(OSError):os.fstat(writer)
        finally:
            port.close();os.close(reader)

    def test_context_mutations_replay_and_typed_flags_reject(self):
        serial,wire,*_=fixture()
        for which in (0,-1):
            for key,value in [('stage','installed'),('boot_id','aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'),
                              ('native_source_sha256','0'*64),('checker_sha256','0'*64),
                              ('release_acceptance',True),('release_acceptance',0),('schema','other')]:
                rows=wire.splitlines(keepends=True);prefix,raw=rows[which].split(b' ',1);record=json.loads(raw);record[key]=value
                rows[which]=prefix+b' '+json.dumps(record).encode()+b'\n'
                with self.subTest(which=which,key=key,value=value),self.assertRaises(RuntimeError):
                    E.reconcile_native_bulk(serial,b''.join(rows),'live')

    def test_END_required_and_original_failure_never_becomes_pass(self):
        serial,wire,begin,proof,end=fixture()
        original=line('ARCTIC-NATIVE-RUNNER-END',end)
        for altered in [serial.replace(original,''),serial+original,serial.replace(original,line('ARCTIC-NATIVE-RUNNER-END',dict(end,evidence_export_complete=False))),
                        serial.replace(original,line('ARCTIC-NATIVE-RUNNER-END',dict(end,stage='installed')))]:
            with self.assertRaises(RuntimeError):E.reconcile_native_bulk(altered,wire,'live')
        failed=dict(end,status='failed',error='original primary failure')
        merged=E.reconcile_native_bulk(serial.replace(original,line('ARCTIC-NATIVE-RUNNER-END',failed)),wire,'live')
        self.assertEqual(E.native_block(merged,'live')[2],failed)
        with self.assertRaises(RuntimeError):E.reconcile_native_bulk(serial+'ARCTIC-NATIVE-EVIDENCE-MANIFEST {}\n',wire,'live')

    def test_missing_truncated_duplicate_and_unknown_framing_reject(self):
        serial,wire,*_=fixture();rows=wire.splitlines(keepends=True)
        for bad in [b'',wire[:-1],b''.join(rows[1:]),b''.join(rows[:-1]),wire+rows[-1],wire+wire,
                    b'kernel intrusion\n'+wire,wire.replace(b'ARCTIC-NATIVE-EVIDENCE-CHUNK',b'ARCTIC-NATIVE-UNKNOWN',1),
                    wire.replace(b'owned.txt',b'private-invalid-path.txt',1)]:
            with self.subTest(digest=sha(bad)),self.assertRaises((RuntimeError,ValueError)):
                E.reconcile_native_bulk(serial,bad,'live')

    def test_json_duplicates_control_nonASCII_and_unknown_fields_reject(self):
        serial,wire,*_=fixture();rows=wire.splitlines(keepends=True)
        header=rows[0]
        for bad in [wire.replace(header,header.replace(b'{',b'{"stage":"live",',1),1),
                    wire.replace(b'"stage": "live"',b'"stage": NaN',1),
                    wire.replace(b'owned.txt',b'owned\x00.txt',1),wire.replace(b'owned.txt',b'owned\xff.txt',1)]:
            with self.assertRaises((RuntimeError,ValueError,UnicodeError)):
                E.reconcile_native_bulk(serial,bad,'live')
        chunk=json.loads(rows[1].split(b' ',1)[1]);chunk['private']='unreviewed'
        rows[1]=line('ARCTIC-NATIVE-EVIDENCE-CHUNK',chunk).encode()
        with self.assertRaises(RuntimeError):E.reconcile_native_bulk(serial,refooter(rows),'live')
        rows=wire.splitlines(keepends=True);manifest=json.loads(rows[-2].split(b' ',1)[1])
        manifest['files'][0]['private_unreviewed']='private synthetic field'
        rows[-2]=line('ARCTIC-NATIVE-EVIDENCE-MANIFEST',manifest).encode()
        with self.assertRaisesRegex(RuntimeError,'file-entry grammar'):
            E.reconcile_native_bulk(serial,refooter(rows),'live')

    def test_duplicate_reordered_corrupt_chunks_still_fail_unchanged_validator(self):
        serial,wire,*_=fixture();base=wire.splitlines(keepends=True)
        cases=[]
        rows=base.copy();rows.insert(2,rows[1]);cases.append(refooter(rows))
        for key,value in [('index',1),('data',base64.b64encode(b'corrupt zlib').decode())]:
            rows=base.copy();record=json.loads(rows[1].split(b' ',1)[1]);record[key]=value
            rows[1]=line('ARCTIC-NATIVE-EVIDENCE-CHUNK',record).encode();cases.append(refooter(rows))
        for wire in cases:
            merged=E.reconcile_native_bulk(serial,wire,'live')
            with tempfile.TemporaryDirectory() as tmp,self.assertRaises((RuntimeError,zlib.error)):
                E.extract_evidence(E.native_block(merged,'live')[0],'live',Path(tmp)/'out')

    def test_private_content_remains_rejected_by_original_upload_scanner(self):
        serial,wire,*_=fixture(data=b'transcript: private synthetic text\n')
        merged=E.reconcile_native_bulk(serial,wire,'live')
        screen=load('native_bulk_original_screen',HERE/'screen-evidence.py')
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'out';E.extract_evidence(E.native_block(merged,'live')[0],'live',target)
            with self.assertRaises(RuntimeError):screen.screen_external(target,Path(tmp)/'public')
            self.assertFalse((Path(tmp)/'public').exists())

    def test_original_size_line_and_file_limits_not_relaxed(self):
        serial,wire,*_=fixture();rows=wire.splitlines(keepends=True)
        huge=rows.copy();huge[1]=b'x'*65537+b'\n'
        with self.assertRaises(RuntimeError):E.reconcile_native_bulk(serial,refooter(huge),'live')
        for field,value in [('bytes',E.MAX_FILE+1),('chunks',173),('compressed_bytes',E.MAX_FILE+65537),('sha256','0'*64)]:
            altered=rows.copy();m=json.loads(altered[-2].split(b' ',1)[1]);m['files'][0][field]=value
            altered[-2]=line('ARCTIC-NATIVE-EVIDENCE-MANIFEST',m).encode()
            merged=E.reconcile_native_bulk(serial,refooter(altered),'live')
            with tempfile.TemporaryDirectory() as tmp,self.assertRaises(RuntimeError):
                E.extract_evidence(E.native_block(merged,'live')[0],'live',Path(tmp)/'out')

    def test_sidecar_read_rejects_symlink_FIFO_and_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);original=root/'original';original.write_bytes(b'whole original\n')
            self.assertEqual(E.read_native_bulk(original),original.read_bytes())
            alias=root/'alias';alias.symlink_to(original)
            with self.assertRaises(OSError):E.read_native_bulk(alias)
            fifo=root/'fifo';os.mkfifo(fifo)
            with self.assertRaises(RuntimeError):E.read_native_bulk(fifo)
            old=E.os.fstat
            def changed(fd):
                value=old(fd)
                if getattr(changed,'called',False):
                    return type('Changed',(),{k:getattr(value,k)+(1 if k=='st_ino' else 0) for k in
                        ('st_dev','st_ino','st_uid','st_mode','st_size','st_nlink','st_mtime_ns','st_ctime_ns')})()
                changed.called=True;return value
            with patch.object(E.os,'fstat',side_effect=changed),self.assertRaises(RuntimeError):E.read_native_bulk(original)

    def test_actual_QEMU_function_requires_original_fixture_and_outputonly_bus(self):
        text=(HERE.parents[1]/'tools/test-install.sh').read_text();start=text.index('def native_taskbar_argv(');end=text.index('\ndef enable_taskbar_display(',start)
        context=dict(E=dict(NATIVE_TWO_OUTPUTS='1',NATIVE_TASKBAR_FIXTURE='1',NATIVE_PHYSICAL_FIXTURE='1',NATIVE_AUDIO_FIXTURE='1',NATIVE_LAUNCHER_FIXTURE='1',GUEST_CHECK='original'),out='/owned,fixture')
        exec(text[start:end],context)
        argv=['qemu','-display','none','-vga','std'];display='dbus,addr=unix:path=/tmp/arctic-tb-display-fixture/bus,gl=off'
        value=context['native_taskbar_argv'](argv,'install',display)
        self.assertIn('virtserialport,bus=taskbar_serial.0,chardev=native_evidence,name=arctic-native-evidence',value)
        self.assertIn('file,id=native_evidence,path=/owned,,fixture/native-evidence-install.log',value)
        self.assertEqual(value.count('virtio-serial-pci,id=taskbar_serial'),1)
        self.assertNotIn('-fsdev',value);self.assertNotIn('-virtfs',value)
        context['E']['NATIVE_PHYSICAL_FIXTURE']='0'
        self.assertNotIn('arctic-native-evidence',' '.join(context['native_taskbar_argv'](argv,'boot',display)))
        context['E']['NATIVE_PHYSICAL_FIXTURE']='1';context['E']['NATIVE_LAUNCHER_FIXTURE']='0'
        with self.assertRaises(RuntimeError):context['native_taskbar_argv'](argv,'install',display)

    def test_original_UART_and_sidecar_preserved_whole_private(self):
        import sys
        with patch.dict(sys.modules,evidence=E,apps=load('native_bulk_apps',HERE/'apps.py')):
            runner=load('native_bulk_runner',HERE/'runner.py')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);vm=root/'vm';vm.mkdir();evidence=root/'evidence';evidence.mkdir()
            originals={'serial-install.log':b'original UART\n','native-evidence-install.log':fixture()[1]}
            for name,data in originals.items():(vm/name).write_bytes(data)
            copied=runner.R.preserve_phase(vm,evidence,'harness')
            for name,data in originals.items():
                out=evidence/'harness'/name
                self.assertEqual(out.read_bytes(),data);self.assertEqual(stat.S_IMODE(out.stat().st_mode),0o600)
                self.assertEqual(copied[name]['sha256'],sha(data));self.assertTrue(copied[name]['private_original'])

if __name__=='__main__':unittest.main()
