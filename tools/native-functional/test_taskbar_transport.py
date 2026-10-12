"""Synthetic transport/negative controls only: no VM or release acceptance."""
import base64
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import stat
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import zlib

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('taskbar_evidence_controls', HERE/'taskbar-evidence.py')
e = importlib.util.module_from_spec(spec); spec.loader.exec_module(e)
r = e.runtime


def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


class Controls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = dict(schema='arctic-taskbar-context-v1', source_sha='1'*40, execution_sha='2'*40,
                           iso_sha256='3'*64, iso_bytes=1_900_000_000, token='4'*32,
                           checker_sha256='5'*64, runtime_sha256='6'*64, native_sha256='7'*64,
                           pointer_sha256='8'*64, capture_sha256='9'*64)
        cls.identity = dict(boot_id='01234567-89ab-cdef-0123-456789abcdef', desktop_uid=1000,
                            active_desktop_session='2')
        cls.root = '/tmp/arctic-native-smoke-sourcecontrol'
        cls.proof = dict(schema='arctic-taskbar-provenance-v1', stage='installed', context=cls.context,
                         **cls.identity, cmdline='ro quiet', virtualization='qemu', release_acceptance=False)
        cls.begin = dict(schema='arctic-taskbar-runner-v1', stage='installed', context=cls.context,
                         **cls.identity, release_acceptance=False)
        cls.end = dict(token=cls.context['token'], **cls.identity, status='passed', error=None,
                       evidence_export_complete=True, release_acceptance=False)
        cls.native = dict(stage='installed', native_source_sha256=cls.context['native_sha256'],
                          **cls.identity, cmdline='ro quiet', release_acceptance=False)
        cls.files = {}; cls.report = dict(schema='arctic-installed-taskbar-v1', stage='installed', status='passed',
            release_acceptance=False, evidence_root=cls.root, scope='synthetic control only',
            reservation_observer='synthetic control only', results=[],
            cleanup={k:True for k in ('settings_bytes_restored', 'outputs_restored', 'original_windows_retained',
                                     'bars_restored', 'only_proved_owned_processes_stopped')},
            security=dict(selinux='Enforcing', audit=dict(enabled=1, lost=0), observed_new_avcs=0, audit_enabled=True))
        cls.report['installed_inputs'] = {'/usr/share/arctic/shell/'+x:'a'*64 for x in
            ('Bar.qml', 'ScreenFrame.qml', 'Session.qml', 'Theme.qml', 'VerticalBar.qml', 'BarVisibility.js', 'scripts/window_geometry.py')}
        cls.report['installed_inputs'].update({'/usr/bin/foot':'b'*64, '/run/t/virtual-pointer':'8'*64,
            '/run/t/raw-screencopy':'9'*64, '/home/arctic/.config/arctic/current/theme.json':'c'*64})
        def layer_list(mode):
            values=[]
            for output in ('DP-1','DP-2'):
                for namespace, count, layer in (('arctic-bar',1,'top' if mode=='always' else 'overlay'),
                        ('arctic-frame',1,'bottom'), ('arctic-frame-reserve',3 if mode=='always' else 4,'bottom')):
                    values.extend(dict(name=namespace,monitor=output,layer=layer) for _ in range(count))
            return values
        pngs = {}
        def png(edge, scale, shown):
            key=edge,scale,shown
            if key not in pngs:
                image=Image.new('RGB',(512,384),e.FOOT)
                offset=max(4,round(22*scale)); radius=max(2,round(3*scale))
                x,y={'top':(256,offset),'bottom':(256,383-offset),'left':(offset,192),'right':(511-offset,192)}[edge]
                if shown: ImageDraw.Draw(image).rectangle((x-radius,y-radius,x+radius,y+radius),fill=(18,23,30))
                out=io.BytesIO();image.save(out,format='PNG')
                pngs[key]=(out.getvalue(),[x-radius,y-radius,x+radius+1,y+radius+1],(2*radius+1)**2)
            return pngs[key]
        def shot(label,edge,scale,shown):
            name=__import__('re').sub('[^a-zA-Z0-9_-]','_',label)+'.png'
            data,region,count=png(edge,scale,shown);cls.files[name]=data
            return dict(path=cls.root+'/'+name,sha256=hash_bytes(data),visible=shown,
                        non_foot_fraction=int(shown),sampled_pixels=count,region=region)
        for output in ('DP-1','DP-2'):
            for scale in e.SCALES:
                for edge in e.EDGES:
                    label=f'{output}-{scale}-{edge}'; base=dict(x=8,y=8,width=1008,height=752)
                    case=dict(output=output,scale=scale,edge=edge,baseline=base,
                        always_geometry=e.geometry(base,edge,'always'),hiding_geometry=e.geometry(base,edge,'auto'),
                        covered_windows=[],transitions=[])
                    for mode in ('auto','dodge'):
                        rest=shot(label+'-'+mode+'-covered-rest',edge,scale,False)
                        reveal=shot(label+'-'+mode+'-covered-reveal',edge,scale,True)
                        shot(label+'-'+mode+'-covered-conceal',edge,scale,False)
                        case['covered_windows'].append(dict(mode=mode,geometry=e.geometry(base,edge,mode),
                            rest=rest,reveal=reveal,layers=layer_list(mode)))
                    for index,mode in enumerate(('auto','dodge','always','auto','dodge')):
                        key=label+'-fullscreen-'+str(index)+'-'+mode
                        rest=shot(key+'-rest',edge,scale,False);reveal=None
                        if mode!='always':
                            reveal=shot(key+'-reveal',edge,scale,True);shot(key+'-conceal',edge,scale,False)
                        case['transitions'].append(dict(mode=mode,rest=rest,reveal=reveal,layers=layer_list(mode)))
                    exposed=shot(label+'-frame-exposed',edge,scale,False)
                    case['exposed_frame']=dict(path=exposed['path'],sha256=exposed['sha256'],scale=scale)
                    cls.report['results'].append(case)
        cls.refresh_report_files()

    @classmethod
    def refresh_report_files(cls):
        cls.files['taskbar-report.json']=(json.dumps(cls.report)+'\n').encode()
        trace=''.join(json.dumps(dict(event='taskbar-case-passed',case=case))+'\n' for case in cls.report['results']).encode()
        cls.files['gui-trace.log']=trace
        cls.files['gui-trace-summary.json']=json.dumps(dict(bytes=len(trace),omitted_records=0)).encode()
        cls.files['final-clients.json']=b'{"clients":[]}'

    def rows(self, files=None, report=None, end=None):
        files=files if files is not None else self.files
        report=self.report if report is None else report
        rows=[('BEGIN',copy.deepcopy(self.begin)),('PROVENANCE',copy.deepcopy(self.proof)),('REPORT',copy.deepcopy(report))]
        entries=[]
        for name,data in sorted(files.items()):
            compressed=zlib.compress(data,9);parts=[compressed[i:i+r.CHUNK] for i in range(0,len(compressed),r.CHUNK)]
            entries.append(dict(path=name,bytes=len(data),sha256=hash_bytes(data),compressed_bytes=len(compressed),
                                chunks=len(parts),encoding='zlib+base64'))
            rows.extend(('EVIDENCE-CHUNK',dict(token=self.context['token'],path=name,index=index,data=base64.b64encode(part).decode()))
                        for index,part in enumerate(parts))
        rows.append(('EVIDENCE-MANIFEST',dict(schema='arctic-taskbar-evidence-v1',token=self.context['token'],
                    evidence_root=self.root,files=entries,bytes=sum(map(len,files.values())))))
        rows.append(('END',copy.deepcopy(self.end if end is None else end)))
        return rows

    def serial(self, rows, native=None):
        return 'ARCTIC-NATIVE-PROVENANCE '+json.dumps(self.native if native is None else native)+'\n'+''.join(
            'ARCTIC-TASKBAR-'+kind+' '+json.dumps(value)+'\n' for kind,value in rows)

    def check(self, rows, native=None):
        with tempfile.TemporaryDirectory() as folder:
            return e.check_taskbar(self.serial(rows,native),self.context,Path(folder)/'taskbar')

    def test_complete_synthetic_24_case_480_png_transport_preserves_scope(self):
        state=self.check(self.rows())
        self.assertEqual(state['required_pngs'],480);self.assertFalse(state['release_acceptance'])

    def test_missing_duplicate_reordered_or_extra_records_fail(self):
        rows=self.rows()
        for values in (rows[1:], rows+[rows[-1]], [rows[1],rows[0],*rows[2:]], rows[:3]+[rows[2]]+rows[3:]):
            with self.assertRaises(RuntimeError):self.check(values)

    def test_native_boot_uid_session_image_and_token_are_bound(self):
        for field,value in (('boot_id','ffffffff-ffff-ffff-ffff-ffffffffffff'),('desktop_uid',1001),
                            ('active_desktop_session','3'),('native_source_sha256','0'*64),('cmdline','ro different')):
            native=dict(self.native,**{field:value})
            with self.assertRaises(RuntimeError):self.check(self.rows(),native)
        rows=self.rows();rows[0][1]['context']['token']='0'*32
        with self.assertRaises(RuntimeError):self.check(rows)

    def test_context_exact_fields_iso_bound_and_full_hashes(self):
        for mutate in (lambda c:c.update(extra=1),lambda c:c.update(iso_bytes=2_000_000_000),
                       lambda c:c.update(iso_bytes=True),lambda c:c.update(runtime_sha256='abcd'),
                       lambda c:c.update(token='4'*31),lambda c:c.update(execution_sha='2'*64)):
            value=copy.deepcopy(self.context);mutate(value)
            with self.assertRaises(RuntimeError):e.validate_context(value)

    def test_optional_runtime_sources_and_owned_window_are_validated(self):
        report=copy.deepcopy(self.report)
        report['installed_inputs'].update({name:'d'*64 for name in
            ('/usr/bin/mango','/usr/bin/mmsg','/usr/share/arctic/shell/shell.qml')})
        report['owned_window']=dict(pid=1234,start_ticks=5678,client_id='42',executable='/usr/bin/foot',is_xwayland=False)
        files=dict(self.files);files['taskbar-report.json']=json.dumps(report).encode()
        self.assertEqual(self.check(self.rows(files,report))['status'],'passed')
        for mutate in (lambda v:v['installed_inputs'].pop('/usr/bin/mmsg'),
                       lambda v:v['owned_window'].update(pid=True),
                       lambda v:v['owned_window'].update(executable='/usr/bin/sleep')):
            value=copy.deepcopy(report);mutate(value);files=dict(self.files)
            files['taskbar-report.json']=json.dumps(value).encode()
            with self.assertRaises(RuntimeError):self.check(self.rows(files,value))

    def test_chunk_order_duplicate_foreign_token_and_corruption_fail(self):
        rows=self.rows();indexes=[i for i,(k,_) in enumerate(rows) if k=='EVIDENCE-CHUNK']
        for mutation in ('swap','duplicate','token','data','index'):
            value=copy.deepcopy(rows);i=indexes[0]
            if mutation=='swap':value[i],value[i+1]=value[i+1],value[i]
            elif mutation=='duplicate':value.insert(i,value[i])
            elif mutation=='token':value[i][1]['token']='0'*32
            elif mutation=='data':value[i][1]['data']='!!!'
            else:value[i][1]['index']=True
            with self.assertRaises((RuntimeError,ValueError)):self.check(value)

    def test_manifest_unsafe_paths_order_duplicates_and_bounds_fail(self):
        for mutation in ('path','duplicate','order','filebytes','aggregate','count'):
            rows=self.rows();manifest=rows[-2][1]
            if mutation=='path':manifest['files'][0]['path']='../outside.png'
            elif mutation=='duplicate':manifest['files'].append(copy.deepcopy(manifest['files'][0]))
            elif mutation=='order':manifest['files'].reverse()
            elif mutation=='filebytes':manifest['files'][0]['bytes']=r.MAX_FILE+1
            elif mutation=='aggregate':manifest['bytes']=r.MAX_TOTAL+1
            else:manifest['files']*=2
            with self.assertRaises(RuntimeError):self.check(rows)

    def test_zlib_bomb_trailing_stream_and_wrong_hash_rejected(self):
        for mutation in ('expanded','trailing','hash'):
            rows=self.rows();entry=rows[-2][1]['files'][0];chunk=rows[3][1]
            if mutation=='hash':entry['sha256']='0'*64
            else:
                compressed=zlib.compress(b'x'*(r.MAX_FILE+1)) if mutation=='expanded' else base64.b64decode(chunk['data'])+zlib.compress(b'ignored')
                self.assertLess(len(compressed),r.CHUNK)
                chunk['data']=base64.b64encode(compressed).decode();entry['compressed_bytes']=len(compressed)
            with self.assertRaises(RuntimeError):self.check(rows)

    def test_failed_report_is_preserved_before_success_assertion(self):
        report=copy.deepcopy(self.report);report['status']='failed';report['error']='synthetic fault'
        files=dict(self.files);files['taskbar-report.json']=json.dumps(report).encode()
        end=dict(self.end,status='failed',error='synthetic fault')
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'taskbar'
            with self.assertRaises(RuntimeError):e.check_taskbar(self.serial(self.rows(files,report,end)),self.context,target)
            self.assertEqual(e.strict_json((target/'taskbar-report.json').read_bytes()),report)
            self.assertEqual(e.strict_json((target/'taskbar-state.json').read_bytes())['status'],'failed')

    def test_report_file_equality_cleanup_security_matrix_and_layers_are_required(self):
        for mutation in ('file','cleanup','security','matrix','duplicatebar'):
            report=copy.deepcopy(self.report);files=dict(self.files)
            if mutation=='cleanup':report['cleanup']['bars_restored']=False
            elif mutation=='security':report['security']['audit_enabled']=False
            elif mutation=='matrix':report['results'].pop()
            elif mutation=='duplicatebar':report['results'][0]['covered_windows'][0]['layers'].append(
                dict(name='arctic-bar',monitor='DP-1',layer='overlay'))
            if mutation!='file':files['taskbar-report.json']=json.dumps(report).encode()
            else:files['taskbar-report.json']=b'{}'
            with self.assertRaises(RuntimeError):self.check(self.rows(files,report))

    def test_missing_conceal_and_reveal_png_or_faked_pixel_metrics_fail(self):
        for mutation in ('conceal','reveal','pixels'):
            files=dict(self.files);report=copy.deepcopy(self.report)
            if mutation=='pixels':
                report['results'][0]['covered_windows'][0]['rest']['non_foot_fraction']=.01
                files['taskbar-report.json']=json.dumps(report).encode()
            else:files.pop(next(name for name in files if '-'+mutation+'.png' in name))
            with self.assertRaises(RuntimeError):self.check(self.rows(files,report))

    def test_trace_matrix_truncation_or_omission_cannot_pass(self):
        for mutation in ('omitted','truncated','matrix'):
            files=dict(self.files)
            if mutation=='omitted':files['gui-trace-summary.json']=json.dumps(dict(bytes=len(files['gui-trace.log']),omitted_records=1)).encode()
            elif mutation=='truncated':files['gui-trace.log']=files['gui-trace.log'][:-1]
            else:
                files['gui-trace.log']=b'{"event":"wrong"}\n'
                files['gui-trace-summary.json']=json.dumps(dict(bytes=len(files['gui-trace.log']),omitted_records=0)).encode()
            with self.assertRaises(RuntimeError):self.check(self.rows(files))

    def test_duplicate_json_nonfinite_and_host_cli_guard_fail(self):
        for text in ('{"a":1,"a":2}','{"a":NaN}','{"a":Infinity}'):
            with self.assertRaises(RuntimeError):e.strict_json(text)
        result=subprocess.run([sys.executable,str(HERE/'taskbar-runtime.py'),'--disposable-guest'],capture_output=True,text=True,timeout=10)
        self.assertNotEqual(result.returncode,0);self.assertEqual(result.stdout.strip(),'ARCTIC-TASKBAR-COLLECTOR-ERROR')

    def test_guest_inventory_rejects_symlink_special_file_and_changed_bounds(self):
        with tempfile.TemporaryDirectory(prefix='arctic-native-smoke-') as folder:
            root=Path(folder);(root/'taskbar-report.json').write_text('{}')
            files,total=r.inventory(root,os.getuid());self.assertEqual(total,2)
            (root/'physical-capture.ppm').write_bytes(b'raw diagnostic')
            self.assertEqual(r.inventory(root,os.getuid()),(files,total))
            (root/'bad.png').symlink_to('/etc/passwd')
            with self.assertRaises(RuntimeError):r.inventory(root,os.getuid())
            (root/'bad.png').unlink();os.mkfifo(root/'bad.png')
            with self.assertRaises(RuntimeError):r.inventory(root,os.getuid())
            (root/'bad.png').unlink()
            with patch.object(r,'MAX_TOTAL',1):
                with self.assertRaises(RuntimeError):r.inventory(root,os.getuid())
            with patch.object(r,'MAX_FILES',0):
                with self.assertRaises(RuntimeError):r.inventory(root,os.getuid())

    def port_serial(self, rows, marker_mutate=None, channel_mutate=None):
        rows=copy.deepcopy(rows)
        channel=dict(schema='arctic-taskbar-virtio-port-v1',name=r.PORT_NAME,device='/dev/vport0p1',
                     major=243,minor=1,uid=0,mode=0o600)
        if channel_mutate:channel_mutate(channel)
        for _,value in rows[:2]:value['transport']=copy.deepcopy(channel)
        end=rows[-1][1]
        marker=dict(schema='arctic-taskbar-port-end-v1',token=self.context['token'],**self.identity,
                    status=end['status'],release_acceptance=False,
                    end_sha256=hash_bytes(json.dumps(end,sort_keys=True,allow_nan=False).encode('ascii')))
        if marker_mutate:marker_mutate(marker)
        serial='ARCTIC-NATIVE-PROVENANCE '+json.dumps(self.native)+'\nARCTIC-TASKBAR-PORT-END '+json.dumps(marker)+'\n'
        port=''.join('ARCTIC-TASKBAR-'+kind+' '+json.dumps(value)+'\n' for kind,value in rows)
        return serial,port

    def check_port(self, serial, port):
        with tempfile.TemporaryDirectory() as folder:
            return e.check_taskbar(serial,self.context,Path(folder)/'taskbar',transport_serial=port)

    def test_separate_named_port_preserves_native_boot_binding_and_no_uart_evidence(self):
        serial,port=self.port_serial(self.rows())
        self.assertEqual(self.check_port(serial,port)['status'],'passed')
        for marker_mutate in (lambda v:v.update(token='0'*32),lambda v:v.update(end_sha256='0'*64),
                              lambda v:v.update(desktop_uid=1001),lambda v:v.update(status='failed')):
            serial,port=self.port_serial(self.rows(),marker_mutate=marker_mutate)
            with self.assertRaises(RuntimeError):self.check_port(serial,port)
        serial,port=self.port_serial(self.rows())
        for invalid in (serial+serial.splitlines()[-1]+'\n',serial.splitlines()[0]+'\n',
                        serial+'ARCTIC-TASKBAR-BEGIN {}\n','\n'.join(reversed(serial.splitlines()))+'\n'):
            with self.assertRaises(RuntimeError):self.check_port(invalid,port)

    def test_port_device_receipt_cannot_claim_other_name_device_owner_or_unsafe_mode(self):
        for mutate in (lambda v:v.update(name='another-port'),lambda v:v.update(device='/dev/ttyS0'),
                       lambda v:v.update(uid=1000),lambda v:v.update(mode=0o666),
                       lambda v:v.update(major=True),lambda v:v.update(minor=-1)):
            serial,port=self.port_serial(self.rows(),channel_mutate=mutate)
            with self.assertRaises(RuntimeError):self.check_port(serial,port)

    def test_guest_port_guard_binds_sysfs_and_opened_root_character_device(self):
        good=SimpleNamespace(st_uid=0,st_mode=stat.S_IFCHR|0o600,st_rdev=os.makedev(243,1))
        protected=SimpleNamespace(st_uid=0,st_mode=stat.S_IFREG|0o444)
        for fault in (None,'regular','uid','mode','rdev','name','resolve'):
            info=copy.copy(good)
            if fault=='regular':info.st_mode=stat.S_IFREG|0o600
            elif fault=='uid':info.st_uid=1000
            elif fault=='mode':info.st_mode=stat.S_IFCHR|0o666
            elif fault=='rdev':info.st_rdev=os.makedev(243,2)
            canonical=Path('/dev/ttyS0' if fault=='resolve' else '/dev/vport0p1')
            with patch.object(Path,'resolve',return_value=canonical),patch.object(Path,'stat',return_value=protected), \
                 patch.object(Path,'read_text',side_effect=['wrong\n' if fault=='name' else r.PORT_NAME+'\n','243:1\n']), \
                 patch.object(r.os,'open',return_value=123),patch.object(r.os,'fstat',return_value=info), \
                 patch.object(r.os,'close') as close:
                if fault is None:
                    writer,receipt=r.open_port();self.assertEqual(receipt['device'],'/dev/vport0p1')
                    self.assertEqual(receipt['major'],243);writer.close();close.assert_called_once_with(123)
                else:
                    with self.assertRaises(RuntimeError):r.open_port()

    def test_virtio_writer_actual_pipe_bytes_timeout_and_wire_bound(self):
        read_fd,write_fd=os.pipe()
        try:
            os.set_blocking(write_fd,False);writer=r.PortWriter(write_fd)
            r.emit('END',dict(status='source-control-only'),writer)
            self.assertEqual(os.read(read_fd,4096),b'ARCTIC-TASKBAR-END {"status": "source-control-only"}\n')
            writer.deadline=0
            with self.assertRaises(RuntimeError):writer.write('x')
            writer.deadline=__import__('time').monotonic()+10;writer.bytes=210*1024*1024
            with self.assertRaises(RuntimeError):writer.write('x')
        finally:
            os.close(read_fd);os.close(write_fd)


if __name__=='__main__':unittest.main()
