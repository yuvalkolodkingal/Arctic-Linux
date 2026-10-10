"""Meaningful exact-source guard and bounded evidence negative controls; no VM."""
import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zlib

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
import common as c
import host


def git(root,*args):
    return subprocess.check_output(['git','-C',str(root),*args],stderr=subprocess.PIPE,timeout=30).decode().strip()


class Bindings(unittest.TestCase):
    def setUp(self):
        self.shipped_manifest=c.strict((HERE/'execution-manifest.json').read_bytes())
        self.assertIs(type(self.shipped_manifest['ready']),bool)
        # Strict binding negatives use a labelled private operational fixture.
        # This never enables or modifies a shipped disabled source manifest.
        self.manifest=copy.deepcopy(self.shipped_manifest);self.manifest['ready']=True

    def test_exact_manifest_and_all_execution_source_pins(self):
        if self.shipped_manifest['ready'] is False:
            with self.assertRaisesRegex(RuntimeError,'disabled'):c.validate_manifest(self.shipped_manifest)
        else:
            c.validate_manifest(self.shipped_manifest)
        c.validate_manifest(self.manifest)
        for name,expected in self.manifest['execution_files'].items():
            self.assertEqual(c.sha(ROOT/name),expected)
        for name,pin in self.manifest['source_files'].items():
            raw=subprocess.check_output(['git','-C',str(ROOT),'show',c.IMAGE['source_sha']+':'+name])
            self.assertEqual(dict(blob_sha=git(ROOT,'rev-parse',c.IMAGE['source_sha']+':'+name),
                      sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),mode=git(ROOT,'ls-tree',c.IMAGE['source_sha'],'--',name).split()[0]),pin)
        self.assertFalse((ROOT/c.MARKER).exists())
        self.assertEqual(c.sha(ROOT/'tools/native-functional/fetch-image.py'),
             '5a45175dfe055400a9871a78ca4e3fdd6eb973d567cec80c229dd93c03111c97')

    def test_every_image_pin_and_type_is_fail_closed(self):
        for name,value in c.IMAGE.items():
            for changed in (None,True,False, str(value)+'x'):
                with self.subTest(pin=name,changed=changed):
                    candidate=copy.deepcopy(self.manifest);candidate['image'][name]=changed
                    with self.assertRaises(RuntimeError):c.validate_manifest(candidate)

    def test_acceptance_inventory_and_ambiguous_json_rejected(self):
        for name in ('release_acceptance','image_qualified','performance_acceptance','observer_profile_admitted'):
            candidate=copy.deepcopy(self.manifest);candidate[name]=True
            with self.assertRaises(RuntimeError):c.validate_manifest(candidate)
        for category in ('execution_files','source_files'):
            candidate=copy.deepcopy(self.manifest);candidate[category].pop(next(iter(candidate[category])))
            with self.assertRaises(RuntimeError):c.validate_manifest(candidate)
        for raw in ('{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}'):
            with self.assertRaises(RuntimeError):c.strict(raw)


class Protocol(unittest.TestCase):
    def files(self,root):
        for index,name in enumerate(sorted(c.GUEST_FILES)):
            (root/name).write_bytes((b'original-'+str(index).encode())*30)

    def test_actual_duplex_round_trip_retains_original_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';target=root/'target';source.mkdir();target.mkdir();self.files(source)
            left,right=socket.socketpair();left.setblocking(False);right.setblocking(False)
            binding='a'*32;errors=[]
            def sender():
                try:c.export_files(c.Channel(left.fileno(),binding),source)
                except BaseException as exc:errors.append(exc)
            worker=threading.Thread(target=sender);worker.start()
            try:
                channel=c.Channel(right.fileno(),binding);inventory=c.receive_files(channel,target)
                worker.join(timeout=5);self.assertFalse(worker.is_alive());self.assertFalse(errors)
                self.assertEqual(inventory['bytes'],sum(p.stat().st_size for p in source.iterdir()))
                self.assertEqual({p.name:p.read_bytes() for p in source.iterdir()},
                                 {p.name:p.read_bytes() for p in target.iterdir()})
                self.assertGreater(channel.read_bytes,0)
            finally:left.close();right.close()

    def test_envelope_rejects_foreign_binding_duplicate_keys_and_oversize(self):
        for raw in (json.dumps(dict(kind='HELLO',binding_id='b'*32,payload={})).encode()+b'\n',
                    b'{"kind":"x","kind":"y","binding_id":"'+b'a'*32+b'","payload":{}}\n',
                    b'x'*32769+b'\n'):
            left,right=socket.socketpair();left.sendall(raw);right.setblocking(False)
            try:
                with self.assertRaises((RuntimeError,json.JSONDecodeError)):c.Channel(right.fileno(),'a'*32).receive(.1)
            finally:left.close();right.close()

    def encoded(self,source):
        entries,total=c.encode_files(source)
        values=[('INVENTORY',dict(files=[entry for entry,_ in entries],bytes=total))]
        for entry,data in entries:
            values += [('CHUNK',dict(path=entry['path'],index=index,data=base64.b64encode(data[start:start+c.CHUNK]).decode()))
                       for index,start in enumerate(range(0,len(data),c.CHUNK))]
        values.append(('END',dict(files=len(entries),bytes=total)))
        return values

    def test_transport_tampering_and_bombs_are_rejected_before_export(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';source.mkdir();self.files(source)
            base=self.encoded(source)
            cases=[]
            for field,value in (('path','../escape.rgb'),('bytes',True),('bytes',c.MAX_FILE+1),
                                ('sha256','0'*64),('compressed_bytes',1),('chunks',-1)):
                altered=copy.deepcopy(base);altered[0][1]['files'][0][field]=value;cases.append(altered)
            altered=copy.deepcopy(base);altered[1][1]['index']=True;cases.append(altered)
            altered=copy.deepcopy(base);altered[1][1]['data']='not base64';cases.append(altered)
            altered=copy.deepcopy(base);altered[1][1]['data']=base64.b64encode(zlib.compress(b'x'*1000000)).decode();cases.append(altered)
            for index,values in enumerate(cases):
                class Replay:
                    def __init__(self):self.values=iter(values)
                    def expect(self,kind,payload=None,timeout=30):
                        actual,data=next(self.values);c.require(actual==kind and (payload is None or payload==data),'order');return data
                target=root/str(index);target.mkdir()
                with self.subTest(case=index),self.assertRaises((RuntimeError,ValueError,KeyError)):
                    c.receive_files(Replay(),target)
                self.assertFalse((root/'escape.rgb').exists())

    def test_guest_export_refuses_symlink_unexpected_or_missing_member(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.files(root)
            first=root/'guest-report.json';first.unlink();first.symlink_to('/etc/hostname')
            with self.assertRaises(RuntimeError):c.encode_files(root)
            first.unlink()
            with self.assertRaises(RuntimeError):c.encode_files(root)
            first.write_bytes(b'{}');(root/'unexpected.wav').write_bytes(b'a')
            with self.assertRaises(RuntimeError):c.encode_files(root)


class SourceGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();base=Path(cls.temp.name);cls.repo=base/'execution';cls.source=base/'source'
        for target,paths in ((cls.repo,['tools/safe-diagnostic','.github/workflows/safe-diagnostic-20261010.yml',c.MARKER,*c.EXECUTION_FILES]),
                             (cls.source,list(c.SOURCE_FILES))):
            subprocess.run(['git','clone','--quiet','--shared','--no-checkout',str(ROOT),str(target)],check=True,timeout=30)
            git(target,'sparse-checkout','set','--no-cone',*paths)
            git(target,'checkout','--detach',c.IMAGE['source_sha'])
            git(target,'config','user.name','Safe source controls');git(target,'config','user.email','safe-source-controls@invalid.local')
        for path in HERE.iterdir():
            if path.is_file() and path.suffix in ('.py','.c','.sh','.json','.md'):
                destination=cls.repo/'tools/safe-diagnostic'/path.name;destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_bytes(path.read_bytes());destination.chmod(path.stat().st_mode & 0o777)
        workflow=cls.repo/'.github/workflows/safe-diagnostic-20261010.yml';workflow.parent.mkdir(parents=True,exist_ok=True)
        workflow.write_bytes((ROOT/workflow.relative_to(cls.repo)).read_bytes())
        private_manifest=cls.repo/'tools/safe-diagnostic/execution-manifest.json'
        private_value=c.strict(private_manifest.read_bytes());private_value['ready']=True
        private_manifest.write_text(json.dumps(private_value,sort_keys=True,indent=2)+'\n')
        git(cls.repo,'add','tools/safe-diagnostic','.github/workflows/safe-diagnostic-20261010.yml')
        git(cls.repo,'commit','--quiet','-m','Private source fixture diagnostic preparation')
        cls.parent=git(cls.repo,'rev-parse','HEAD');marker=cls.repo/c.MARKER;marker.write_text(cls.parent+'\n')
        git(cls.repo,'add',c.MARKER);git(cls.repo,'commit','--quiet','-m','Private source fixture sole marker child')
        cls.head=git(cls.repo,'rev-parse','HEAD');cls.event=base/'event.json'
        cls.event.write_text(json.dumps(dict(before=cls.parent,after=cls.head)))

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def run_guard(self,updates=None,remote=None):
        env=dict(GITHUB_REPOSITORY=c.REPO,GITHUB_EVENT_NAME='push',GITHUB_REF='refs/heads/'+c.BRANCH,
                 GITHUB_RUN_ATTEMPT='1',RUNNER_ENVIRONMENT='github-hosted',GITHUB_SHA=self.head,GITHUB_EVENT_PATH=str(self.event))
        env.update(updates or {})
        original=c.capture
        def capture(argv,*args,**kwargs):
            if argv[0]=='gh':return json.dumps(remote or dict(ref='refs/heads/'+c.BRANCH,object=dict(sha=self.head)))
            return original(argv,*args,**kwargs)
        with patch.dict(os.environ,env),patch.object(c,'capture',side_effect=capture):return c.guard(self.repo,self.source)

    def test_actual_git_marker_child_and_source_pins_pass(self):
        self.assertEqual(self.run_guard()['parent_sha'],self.parent)

    def test_wrong_event_host_attempt_branch_and_live_ref_rejected(self):
        for key,value in (('GITHUB_EVENT_NAME','workflow_dispatch'),('GITHUB_RUN_ATTEMPT','2'),('RUNNER_ENVIRONMENT','self-hosted'),
                          ('GITHUB_REF','refs/heads/main'),('GITHUB_SHA','0'*40),('GITHUB_REPOSITORY','foreign/repo')):
            with self.subTest(key=key),self.assertRaises(RuntimeError):self.run_guard({key:value})
        with self.assertRaises(RuntimeError):self.run_guard(remote=dict(ref='refs/heads/'+c.BRANCH,object=dict(sha='0'*40)))

    def test_dirty_checkout_pin_and_parent_event_fail_closed(self):
        path=self.repo/'tools/safe-diagnostic/screencopy.c';original=path.read_bytes()
        try:
            path.write_bytes(original+b'\n')
            with self.assertRaises(RuntimeError):self.run_guard()
        finally:path.write_bytes(original)
        original=self.event.read_bytes()
        try:
            self.event.write_text(json.dumps(dict(before='0'*40,after=self.head)))
            with self.assertRaises(RuntimeError):self.run_guard()
        finally:self.event.write_bytes(original)

    def test_marker_bytes_and_original_source_checkout_cannot_drift(self):
        marker=self.repo/c.MARKER;original=marker.read_bytes()
        try:
            for raw in ((self.parent+'\r\n').encode(),('0'*40+'\n').encode()):
                marker.write_bytes(raw)
                with self.assertRaises(RuntimeError):self.run_guard()
        finally:marker.write_bytes(original)
        path=self.source/'tools/lib/iso_startup.py';original=path.read_bytes()
        try:
            path.write_bytes(original+b'\n')
            with self.assertRaises(RuntimeError):self.run_guard()
        finally:path.write_bytes(original)

    def test_high_similarity_product_rename_cannot_hide_original_path(self):
        target=Path(self.temp.name)/'forged';subprocess.run(['git','clone','--quiet','--shared',str(self.repo),str(target)],check=True,timeout=30)
        git(target,'config','user.name','Safe source controls');git(target,'config','user.email','safe-source-controls@invalid.local')
        git(target,'checkout','--detach',self.parent)
        original=target/'tools/native-functional/native_smoke.py'
        original.rename(target/'tools/safe-diagnostic/moved-product.py')
        git(target,'add','-A');git(target,'commit','--quiet','-m','Private forbidden product rename control')
        parent=git(target,'rev-parse','HEAD');(target/c.MARKER).write_text(parent+'\n')
        git(target,'add',c.MARKER);git(target,'commit','--quiet','-m','Private attempted marker activation')
        head=git(target,'rev-parse','HEAD');event=Path(self.temp.name)/'forged-event.json'
        event.write_text(json.dumps(dict(before=parent,after=head)))
        env=dict(GITHUB_REPOSITORY=c.REPO,GITHUB_EVENT_NAME='push',GITHUB_REF='refs/heads/'+c.BRANCH,
                 GITHUB_RUN_ATTEMPT='1',RUNNER_ENVIRONMENT='github-hosted',GITHUB_SHA=head,GITHUB_EVENT_PATH=str(event))
        with patch.dict(os.environ,env),self.assertRaisesRegex(RuntimeError,'preparation changes existing product'):
            c.guard(target,self.source)


class RawReadback(unittest.TestCase):
    def test_stride_padding_and_y_inversion_are_independently_bound(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);samples=[];stride=1920*4+16
            top=bytes((10,20,230,255))*1920+b'padding-sentinel'
            bottom=bytes((200,30,40,255))*1920+b'padding-sentinel'
            raw=top*540+bottom*540
            rgb=bytes((40,30,200))*1920*540+bytes((230,20,10))*1920*540
            for label in c.PAIRS:
                base=label+'-wayland.rgb'
                descriptor=dict(width=1920,height=1080,output_width=1920,output_height=1080,output_transform=0,
                       output_scale=1,stride=stride,flags=1,format=0,raw_bytes=len(raw),schema='arctic-safe-screencopy-v1',
                       selected_output='Virtual-1',output_x=0,output_y=0,output_refresh_mhz=60000,outputs_seen=1)
                (root/base).write_bytes(b'P6\n1920 1080\n255\n'+rgb);(root/(base+'.shm.rgb')).write_bytes(raw)
                (root/(base+'.json')).write_text(json.dumps(descriptor))
                samples.append(dict(label=label,descriptor=descriptor,files={p.name:dict(bytes=p.stat().st_size,sha256=c.sha(p))
                            for p in root.iterdir() if p.name.startswith(label+'-wayland')}))
            report=dict(schema='arctic-safe-guest-observation-v1',release_acceptance=False,image_qualified=False,
                         performance_acceptance=False,observer_profile_admitted=False,selinux_before='Enforcing',selinux_after='Enforcing',samples=samples)
            derived=host.validate_readbacks(root,report)
            self.assertEqual(len(derived),3)
            self.assertTrue(all(v['pixel_sha256']==hashlib.sha256(rgb).hexdigest() for v in derived))
            self.assertEqual((root/(c.PAIRS[0]+'-wayland.rgb.shm.rgb')).read_bytes(),raw)
            for label in c.PAIRS:(root/(label+'-wayland-derived.png')).unlink()
            (root/(c.PAIRS[0]+'-wayland.rgb.shm.rgb')).write_bytes(raw[:-1])
            with self.assertRaises(RuntimeError):host.validate_readbacks(root,report)

    def test_actual_privacy_rejects_credentials_and_hebrew_transcript(self):
        spec=importlib.util.spec_from_file_location('safe_screen_test',ROOT/'tools/native-functional/screen-evidence.py')
        screen=importlib.util.module_from_spec(spec);spec.loader.exec_module(screen)
        for raw in (b'{"transcript":"private"}', '{"תמלול":"פרטי"}'.encode(),b'Authorization: Bearer private',
                    b'https://example.invalid/file?signature=private'):
            with self.assertRaises(RuntimeError):screen.external_text(raw)
        raw=b'{"renderer_environment":{"LIBGL_ALWAYS_SOFTWARE":"1"},"release_acceptance":false}'
        self.assertEqual(screen.external_text(raw),raw)


if __name__=='__main__':unittest.main()
