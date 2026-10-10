"""Meaningful exact-source guard and bounded evidence negative controls; no VM."""
import base64
import builtins
import copy
import hashlib
import importlib.util
import io
import json
import os
import signal
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch
import uuid
import zlib
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
import common as c
import host


def git(root,*args):
    return subprocess.check_output(['git','-C',str(root),*args],stderr=subprocess.PIPE,timeout=30).decode().strip()


def actual_failed_v2_wrapper(wrapper):
    """Undo only this ownership correction and attest all original v2 bytes."""
    wrapper=wrapper.replace('  local primary=$? secondary=0\n  set +e\n','')
    wrapper=wrapper.replace('  secondary=$?\n  [[ $primary != 0 ]] && exit "$primary"\n  exit "$secondary"\n','')
    wrapper=wrapper.replace('# Secondary export/screening failures preserve an existing primary failure.\n# A zero primary still fails if either strict reporting stage rejects bytes.\n','set -e\n')
    wrapper=wrapper[:wrapper.index('export_status=$?\n')]+'''python3 -B "$execution/tools/native-functional/screen-evidence.py" --preserve-original \\
  --source "$out/evidence" --out "$out/screened"
exit "$status"
'''
    wrapper=wrapper.replace('python3 -B "$HERE/common.py" docker-prep "$out" -- \\\n "$engine" run', '"$engine" run')
    wrapper=wrapper.replace('python3 -B "$HERE/common.py" docker-vm "$out" -- \\\n "$engine" run', '"$engine" run')
    wrapper=wrapper.replace('python3 -B /execution/tools/safe-diagnostic/common.py bootstrap-cd /out -- \\\n xorriso', 'xorriso')
    wrapper=wrapper.replace('python3 -B /execution/tools/safe-diagnostic/common.py python-driver /out -- \\\n timeout', 'timeout')
    wrapper=wrapper.replace(",\x27host-entry-status.json\x27) or (path.name.startswith(\x27stage-\x27) and path.suffix==\x27.json\x27)", ')')
    wrapper=wrapper.replace('python3 - "$out" "$execution" <<\x27PY\x27\nimport importlib.util,shutil,stat,sys',
                            'python3 - "$out" <<\x27PY\x27\nimport shutil,stat,sys')
    wrapper=wrapper.replace("out=Path(sys.argv[1]);execution=Path(sys.argv[2]);evidence=out/\x27evidence\x27;evidence.mkdir()\nspec=importlib.util.spec_from_file_location(\x27safe_status_export\x27,execution/\x27tools/safe-diagnostic/common.py\x27)\nc=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)",
                            "out=Path(sys.argv[1]);evidence=out/\x27evidence\x27;evidence.mkdir()")
    wrapper=re.sub(r"        if path.name==\x27host-entry-status.json\x27.*?\n(?=        total\+=)",'',wrapper,count=1,flags=re.S)
    old=wrapper.replace('\numask 022\n','\n').replace('chmod 0755 /out/data/raw-screencopy\n','')
    old=old.replace('import hashlib,json,os,stat,subprocess','import hashlib,json,subprocess')
    old=re.sub(r'binary=Path\("/out/data/raw-screencopy"\).*?\n(?=packages=)','',old,count=1,flags=re.S)
    old=old.replace('binary_sha256=sha("/out/data/raw-screencopy"),binary=binary_record,packages=packages,',
                    'binary_sha256=sha("/out/data/raw-screencopy"),packages=packages,')
    old=old.replace('report=Path("/out/build-provenance.json");report.write_text(json.dumps(value,sort_keys=True)+"\\n");report.chmod(0o644)',
                    'Path("/out/build-provenance.json").write_text(json.dumps(value,sort_keys=True)+"\\n")')
    old=old.replace('import importlib.util,json,os,secrets,shutil,stat,subprocess,sys',
                    'import importlib.util,json,secrets,shutil,subprocess,sys')
    old=re.sub(r"build=c.strict\(c.regular\(out/'build-provenance.json'.*?\n(?=ctx=)",
               lambda m:"assert (out/'data/raw-screencopy').read_bytes()[:4]==b'\\x7fELF'\n",old,count=1,flags=re.S)
    old=old.replace('prepared_image_id=prepared,binary=record,release_acceptance=False',
                    'prepared_image_id=prepared,release_acceptance=False')
    old=old.replace('\nset +e\n','\nchmod 0755 "$out/data/raw-screencopy"\nset +e\n',1)
    if hashlib.sha256(old.encode()).hexdigest()!='3d795f1dd7a4ebab7769625449cb6884e2e4db77d13c49df0bf9363f8a30e6af':
        raise AssertionError('Reconstruction differs from complete actual failed v2 wrapper')
    return old


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


class FetchHandoff(unittest.TestCase):
    """Tiny synthetic producer bytes exercise the unchanged real fetcher;
    no image download, container, VM or rendering result is represented.
    """
    def prepare_binary(self,out,wrapper):
        binary=out/'data/raw-screencopy';binary.write_bytes(b'\x7fELFlabelled-synthetic-not-executed')
        owner_step=re.search(r'\n(chmod 0755 /out/data/raw-screencopy)\npython3',wrapper)
        self.assertIsNotNone(owner_step)
        subprocess.run(['bash','-c',owner_step.group(1).replace('/out/',str(out)+'/')],check=True,timeout=30)

    def binary_provenance(self,out):
        binary=out/'data/raw-screencopy';info=binary.lstat()
        record=dict(bytes=info.st_size,uid=info.st_uid,gid=info.st_gid,mode=info.st_mode&0o7777,sha256=c.sha(binary))
        (out/'build-provenance.json').write_text(json.dumps(dict(schema='arctic-safe-tools-v1',
                   release_acceptance=False,binary=record,binary_sha256=record['sha256']))+'\n')
        return record

    def test_real_fetcher_extraction_reaches_actual_preflight_and_readonly_bind(self):
        spec=importlib.util.spec_from_file_location('safe_real_fetcher',ROOT/'tools/native-functional/fetch-image.py')
        fetcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(fetcher)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);execution=root/'execution';execution.mkdir();out=root/'out';(out/'data').mkdir(parents=True)
            # Labelled private three-byte image; the real source/image pins on
            # disk remain untouched. Both wrappers consume this exact layout.
            image=copy.deepcopy(c.IMAGE);image.update(bytes=3,sha256=hashlib.sha256(b'iso').hexdigest())
            receipt=dict(schema='arctic-producer-performance-receipt-v1',repository=c.REPO,
                         workflow='.github/workflows/iso.yml',event='workflow_dispatch',source_sha=image['source_sha'],
                         run_id=image['run_id'],run_attempt=1,mode=fetcher.EXTERNAL_MODE,release_acceptance=False,
                         inputs=dict(expected_source_sha=image['source_sha'],release=False,tag='',prerelease=True,
                                     draft=False,nix_acceptance=False,performance_acceptance=False,boot_test=True,
                                     performance_mode=fetcher.EXTERNAL_MODE),
                         image={key:image[key] for key in ('name','bytes','sha256')},
                         startup_results={name:dict(firmware=firmware,mode=mode,status='passed',serial_bytes=100,
                                               serial_sha256='4'*64) for name,(firmware,mode) in fetcher.STARTUP_LANES.items()})
            raw=json.dumps(receipt,sort_keys=True).encode();image['producer_receipt_sha256']=hashlib.sha256(raw).hexdigest()
            archive=root/'labelled-synthetic-artifact.zip';wanted='iso/'+image['name']
            with zipfile.ZipFile(archive,'w') as output:
                output.writestr(wanted,b'iso')
                output.writestr(wanted+'.sha256',image['sha256']+'  '+image['name']+'\n')
                output.writestr('BUILD-INFO','git_commit='+image['source_sha']+'\narctic_repos=enabled\n')
                output.writestr(fetcher.RECEIPT_NAME,raw)
            inputs=root/'inputs';fetcher.extract(archive,inputs,image)
            actual=inputs/wanted;self.assertEqual(actual.read_bytes(),b'iso')
            self.assertFalse((inputs/image['name']).exists())
            manifest=c.strict((HERE/'execution-manifest.json').read_bytes());manifest.update(ready=True,image=image)
            for name in c.EXECUTION_FILES:
                destination=execution/name;destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_bytes((ROOT/name).read_bytes())
            (execution/'tools/safe-diagnostic/execution-manifest.json').write_text(json.dumps(manifest,sort_keys=True)+'\n')
            wrapper=(HERE/'run.sh').read_text();self.prepare_binary(out,wrapper)
            binary_record=self.binary_provenance(out)
            subprocess.run(['git','init','--quiet',str(execution)],check=True,timeout=30)
            git(execution,'config','user.name','Synthetic handoff control')
            git(execution,'config','user.email','synthetic-handoff@invalid.local')
            git(execution,'add','-A');git(execution,'commit','--quiet','-m','Labelled private synthetic fetch handoff')
            failed_wrapper=actual_failed_v2_wrapper(wrapper).replace("iso=inputs/'iso'/c.IMAGE['name']","iso=inputs/c.IMAGE['name']",1).replace(
                '-v "$inputs/iso/Arctic-Linux-1.2-candidate-38032256030-1-x86_64.iso:/iso:ro"',
                '-v "$inputs/Arctic-Linux-1.2-candidate-38032256030-1-x86_64.iso:/iso:ro"',1)
            # Whole-byte identity with the retained actual failed wrapper;
            # no off-branch Git object is required by this source control.
            self.assertEqual(hashlib.sha256(failed_wrapper.encode()).hexdigest(),
                             '291d448e20adc50600c91f4c70b4cf55610aa5b4ad21f3cf9b97e230e2a475be')
            def preflight(text):
                found=re.search(r"python3 - \"\$execution\" \"\$inputs\" \"\$out\" \"\$prepared\" <<'PY'\n(.*?)\nPY\n",text,re.S)
                self.assertIsNotNone(found)
                original_spec=importlib.util.spec_from_file_location
                def private_spec(name,path):
                    value=original_spec(name,path);delegate=value.loader
                    class Loader:
                        def create_module(self,spec):return delegate.create_module(spec)
                        def exec_module(self,module):
                            delegate.exec_module(module);module.IMAGE=copy.deepcopy(image)
                    value.loader=Loader();return value
                with patch.object(importlib.util,'spec_from_file_location',side_effect=private_spec),\
                     patch.object(sys,'argv',['actual-preflight',str(execution),str(inputs),str(out),'sha256:'+'a'*64]):
                    exec(compile(found.group(1),'actual-run.sh-preflight','exec'),{})
            # Reproduce the actual failed consumer before proving the fix.
            with self.assertRaises(FileNotFoundError):preflight(failed_wrapper)
            preflight(wrapper)
            fixture=json.loads((out/'fixture-provenance.json').read_text())
            self.assertEqual(fixture['image'],image);self.assertFalse(fixture['release_acceptance'])
            self.assertEqual(fixture['binary'],binary_record)
            recorder=root/'record-argv.py';argv_path=root/'container-argv.json'
            recorder.write_text('#!/usr/bin/env python3\nimport json,os,sys\nfrom pathlib import Path\n'
                                'Path(os.environ["SAFE_SYNTHETIC_ARGV"]).write_text(json.dumps(sys.argv[1:]))\n')
            recorder.chmod(0o755)
            def bind(text):
                found=re.search(r'("\$engine" run --name "\$vm".*?)(?=\nstatus=\$\?)',text,re.S)
                self.assertIsNotNone(found)
                prefix='engine=$1\nexecution=$2\ninputs=$3\nout=$4\nprepared=synthetic-image\nvm=synthetic-owned-vm\ninvocation=synthetic\n'
                subprocess.run(['bash','-c',prefix+found.group(1),'synthetic-container-recorder',str(recorder),
                                str(execution),str(inputs),str(out)],env=dict(os.environ,SAFE_SYNTHETIC_ARGV=str(argv_path)),
                               check=True,timeout=30)
                argv=json.loads(argv_path.read_text())
                mounts=[argv[i+1] for i,arg in enumerate(argv[:-1]) if arg=='-v']
                matches=[mount for mount in mounts if mount.endswith(':/iso:ro')]
                self.assertEqual(len(matches),1)
                self.assertIn('--network',argv);self.assertEqual(argv[argv.index('--network')+1],'none')
                return Path(matches[0][:-len(':/iso:ro')])
            self.assertFalse(bind(failed_wrapper).exists())
            bound=bind(wrapper);self.assertEqual(bound,actual);self.assertEqual(bound.read_bytes(),b'iso')


class Ownership(unittest.TestCase):
    def test_distinct_uid_owner_step_and_actual_readonly_preflight(self):
        engine=shutil.which('docker')
        if not engine:self.skipTest('Distinct-UID cached Docker fixture unavailable; no pull allowed')
        result=subprocess.run([engine,'image','inspect','fedora:44','--format','{{.Id}}'],
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30)
        image=result.stdout.strip()
        if result.returncode or not re.fullmatch('sha256:[0-9a-f]{64}',image):
            self.skipTest('Cached Fedora44 immutable image unavailable; no pull allowed')
        if os.geteuid()==0:self.skipTest('Requires nonroot host for actual different-owner chmod refusal')
        observations=[]
        control=FetchHandoff('test_real_fetcher_extraction_reaches_actual_preflight_and_readonly_bind')
        def foreign_binary(out,wrapper):
            data=out/'data';data.chmod(0o777)  # Only this private host-owned fixture directory.
            owner_step=re.search(r'\n(chmod 0755 /out/data/raw-screencopy)\npython3',wrapper)
            self.assertIsNotNone(owner_step)
            def owned_container(command):
                binding=uuid.uuid4().hex;name='arctic-safe-ownership-'+binding;cid=out/('cid-'+binding)
                absent=subprocess.run([engine,'container','inspect',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
                self.assertNotEqual(absent.returncode,0)
                try:
                    subprocess.run([engine,'run','--pull','never','--rm','--name',name,'--cidfile',str(cid),
                                    '--label','org.arctic.safe.ownership='+binding,'--network','none','--read-only',
                                    '--cap-drop','ALL','--security-opt','no-new-privileges','-v',str(data)+':/out/data',
                                    image,'bash','-c','set -euo pipefail\n'+command],check=True,timeout=30)
                finally:
                    retained=subprocess.run([engine,'container','inspect',name],stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE,text=True,timeout=30)
                    if retained.returncode==0:
                        rows=json.loads(retained.stdout);self.assertEqual(len(rows),1);row=rows[0]
                        self.assertEqual(row['Name'],'/'+name)
                        self.assertEqual(row['Config']['Labels'].get('org.arctic.safe.ownership'),binding)
                        self.assertRegex(row['Id'],'^[0-9a-f]{64}$')
                        subprocess.run([engine,'rm','-f',row['Id']],check=True,stdout=subprocess.DEVNULL,timeout=30)
                identity=cid.read_text().strip();self.assertRegex(identity,'^[0-9a-f]{64}$')
                gone=subprocess.run([engine,'container','inspect',identity],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
                self.assertNotEqual(gone.returncode,0)
                observations.append(dict(container_id=identity,container_name=name,owned_label=binding,removed=True))
            owned_container("printf '\\177ELFlabelled-synthetic-not-executed' >/out/data/raw-screencopy\nchmod 0644 /out/data/raw-screencopy")
            binary=data/'raw-screencopy';initial=binary.lstat()
            self.assertNotEqual(initial.st_uid,os.geteuid());self.assertEqual(initial.st_mode&0o7777,0o644)
            failed=actual_failed_v2_wrapper(wrapper)
            host_step=re.search(r'\n(chmod 0755 "\$out/data/raw-screencopy")\nset \+e',failed)
            self.assertIsNotNone(host_step)
            refused=subprocess.run(['bash','-c',host_step.group(1)],env=dict(os.environ,out=str(out)),
                                   stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
            self.assertNotEqual(refused.returncode,0);self.assertIn(b'Operation not permitted',refused.stderr)
            self.assertEqual(binary.lstat().st_mode&0o7777,0o644)
            owned_container(owner_step.group(1))
            final=binary.lstat();self.assertEqual(final.st_uid,initial.st_uid);self.assertEqual(final.st_mode&0o7777,0o755)
            self.assertTrue(os.access(binary,os.R_OK|os.X_OK))
            observations.append(dict(host_uid=os.geteuid(),binary_uid=final.st_uid,binary_gid=final.st_gid,
                                     initial_mode=0o644,final_mode=0o755,bytes=final.st_size,sha256=c.sha(binary),
                                     historical_host_chmod_refused=True,owner_chmod_passed=True,actual_readonly_preflight_pending=True))
        control.prepare_binary=foreign_binary
        control.test_real_fetcher_extraction_reaches_actual_preflight_and_readonly_bind()
        observations[-1]['actual_readonly_preflight_pending']=False
        observations[-1]['actual_readonly_preflight_passed']=True
        print('SYNTHETIC_OWNERSHIP_CONTROL='+json.dumps(dict(cached_image_id=image,observations=observations),sort_keys=True))


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
        for target,paths in ((cls.repo,['tools/safe-diagnostic','.github/workflows/safe-diagnostic-v4-20261010.yml',c.MARKER,*c.EXECUTION_FILES]),
                             (cls.source,list(c.SOURCE_FILES))):
            subprocess.run(['git','clone','--quiet','--shared','--no-checkout',str(ROOT),str(target)],check=True,timeout=30)
            git(target,'sparse-checkout','set','--no-cone',*paths)
            git(target,'checkout','--detach',c.IMAGE['source_sha'])
            git(target,'config','user.name','Safe source controls');git(target,'config','user.email','safe-source-controls@invalid.local')
        for path in HERE.iterdir():
            if path.is_file() and path.suffix in ('.py','.c','.sh','.json','.md'):
                destination=cls.repo/'tools/safe-diagnostic'/path.name;destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_bytes(path.read_bytes());destination.chmod(path.stat().st_mode & 0o777)
        workflow=cls.repo/'.github/workflows/safe-diagnostic-v4-20261010.yml';workflow.parent.mkdir(parents=True,exist_ok=True)
        workflow.write_bytes((ROOT/workflow.relative_to(cls.repo)).read_bytes())
        private_manifest=cls.repo/'tools/safe-diagnostic/execution-manifest.json'
        private_value=c.strict(private_manifest.read_bytes());private_value['ready']=True
        private_manifest.write_text(json.dumps(private_value,sort_keys=True,indent=2)+'\n')
        git(cls.repo,'add','tools/safe-diagnostic','.github/workflows/safe-diagnostic-v4-20261010.yml')
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


class StageObservation(unittest.TestCase):
    """Actual owned children and early host checks; never KVM or QEMU."""
    def test_actual_child_exit125_private_streams_fixed_public_status(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);message='LABELLED-SYNTHETIC-PRIVATE-RAW'
            code=c.run_stage('bootstrap-cd',root,[sys.executable,'-c',
                       'import sys;print("'+message+'");sys.stderr.write("private stderr");sys.exit(125)'])
            self.assertEqual(code,125)
            value=c.strict((root/'stage-bootstrap-cd.json').read_bytes())
            self.assertEqual((value['status'],value['exit_code'],value['exception_class']),('completed',125,None))
            self.assertNotIn(message,json.dumps(value));self.assertNotIn('argv',value)
            for label in ('stdout','stderr'):
                p=root/('private-bootstrap-cd-'+label+'.log');raw=p.read_bytes()
                self.assertEqual(p.stat().st_mode&0o7777,0o600)
                self.assertEqual(value['private_raw_output'][label],dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),complete=True))

    def test_actual_stage_wrapper_closed_stdout_preserves_child_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            script='import os,sys;sys.path.insert(0,sys.argv[1]);import common;os.close(1);raise SystemExit(common.run_stage("python-driver",sys.argv[2],[sys.executable,"-c","import os,sys;os.close(1);sys.stderr.write(chr(120));sys.exit(7)"]))'
            child=subprocess.run([sys.executable,'-B','-c',script,str(HERE),temp],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
            self.assertEqual(child.returncode,7);self.assertEqual(child.stdout,b'');self.assertEqual(child.stderr,b'')
            value=c.strict((Path(temp)/'stage-python-driver.json').read_bytes())
            self.assertEqual(value['exit_code'],7);self.assertTrue(value['private_raw_output']['stdout']['complete'])
            self.assertEqual(value['private_raw_output']['stdout']['bytes'],0)

    def test_actual_missing_executable_reports_class_without_error_text(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with self.assertRaises(FileNotFoundError):c.run_stage('python-driver',root,['/labelled-synthetic-missing-executable'])
            value=c.strict((root/'stage-python-driver.json').read_bytes())
            self.assertEqual(value['exception_class'],'FileNotFoundError');self.assertIsNone(value['exit_code'])
            self.assertNotIn('labelled-synthetic-missing',json.dumps(value))

    def test_actual_private_output_bound_fails_and_reaps_owned_child(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(c,'MAX_FILE',32):
            root=Path(temp)
            with self.assertRaises(RuntimeError):c.run_stage('python-driver',root,[sys.executable,'-c','import sys;sys.stdout.write("x"*33);sys.stdout.flush()'])
            value=c.strict((root/'stage-python-driver.json').read_bytes())
            self.assertEqual(value['exception_class'],'RuntimeError')
            self.assertLessEqual(value['private_raw_output']['stdout']['bytes'],32)

    def test_preexisting_raw_symlink_and_report_remain_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);foreign=root/'foreign';foreign.write_bytes(b'FOREIGN')
            raw=root/'private-bootstrap-cd-stdout.log';raw.symlink_to(foreign)
            with self.assertRaises(FileExistsError):c.run_stage('bootstrap-cd',root,[sys.executable,'-c','pass'])
            self.assertEqual(foreign.read_bytes(),b'FOREIGN');self.assertTrue(raw.is_symlink())
            (root/'stage-bootstrap-cd.json').unlink();report=root/'stage-bootstrap-cd.json';report.symlink_to(foreign)
            with self.assertRaises(RuntimeError):c.run_stage('bootstrap-cd',root,[sys.executable,'-c','pass'])
            self.assertEqual(foreign.read_bytes(),b'FOREIGN')

    def test_fixed_status_types_classes_and_acceptance_fail_closed(self):
        for args in [('private-stage','completed',0,None),('docker-vm','guessed',0,None),
                     ('docker-vm','completed',True,None),('docker-vm','completed',0,'raw exception text')]:
            with self.assertRaises(RuntimeError):c.fixed_status(*args)
        value=c.fixed_status('docker-vm','completed',125,None)
        for name in ('release_acceptance','image_qualified','performance_acceptance','observer_profile_admitted'):
            self.assertIs(value[name],False)
        for mutation in ({'raw_error':'arbitrary'}, {'exit_code':True}, {'image_qualified':True},
                         {'private_raw_output':[]}, {'exception_class':'arbitrary'}):
            candidate=copy.deepcopy(value);candidate.update(mutation)
            with self.assertRaises((RuntimeError,TypeError)):c.validate_fixed_status(candidate)

    def test_child_failure_survives_secondary_report_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            child='import pathlib,sys;pathlib.Path(sys.argv[1]).write_text("owned-child-poison-status");sys.exit(125)'
            code=c.run_stage('bootstrap-cd',root,[sys.executable,'-c',child,str(root/'stage-bootstrap-cd.json')])
            self.assertEqual(code,125)
            self.assertEqual((root/'stage-bootstrap-cd.json').read_text(),'owned-child-poison-status')

    def test_exited_owned_leader_pipe_descendant_and_repeated_term_are_cleaned(self):
        """Real processes, no VM: an exited leader must not escape group cleanup."""
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);out=root/'out';out.mkdir();identity=root/'identity.json'
            grandchild='import os,signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)'
            leader=('import json,os,pathlib,subprocess,sys;'
                    'p=subprocess.Popen([sys.executable,"-c",sys.argv[2]]);'
                    'pathlib.Path(sys.argv[1]).write_text(json.dumps(dict(leader=os.getpid(),descendant=p.pid)));'
                    'sys.exit(125)')
            observer=('import sys;sys.path.insert(0,sys.argv[1]);import common;'
                      'sys.exit(common.run_stage("python-driver",sys.argv[2],sys.argv[3:]))')
            proc=subprocess.Popen([sys.executable,'-B','-c',observer,str(HERE),str(out),
                  sys.executable,'-B','-c',leader,str(identity),grandchild],
                  stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            ids=None
            try:
                deadline=time.monotonic()+10
                while not identity.exists() and time.monotonic()<deadline:time.sleep(.02)
                ids=json.loads(identity.read_bytes())
                # Allow the descendant to install its TERM-ignore handler.
                time.sleep(.2);proc.send_signal(signal.SIGTERM);time.sleep(.25)
                proc.send_signal(signal.SIGTERM)
                _,error=proc.communicate(timeout=15)
                self.assertNotEqual(proc.returncode,0,error)
                status=c.strict((out/'stage-python-driver.json').read_bytes())
                self.assertEqual(status['exception_class'],'RuntimeError')
                self.assertFalse(status['private_raw_output']['stdout']['complete'])
                path=Path('/proc')/str(ids['descendant'])/'stat'
                self.assertTrue(not path.exists() or path.read_text().split(') ',1)[1].split()[0]=='Z',
                                'Owned descendant still running after cleanup')
            finally:
                if proc.poll() is None:proc.kill();proc.communicate(timeout=5)
                if ids:
                    path=Path('/proc')/str(ids['descendant'])/'stat'
                    if path.exists():
                        fields=path.read_text().split(') ',1)[1].split()
                        if fields[0]!='Z' and int(fields[2])==ids['leader']:
                            os.killpg(ids['leader'],signal.SIGKILL)

    def test_actual_wrapper_primary_failure_survives_export_and_screen_rejection(self):
        wrapper=(HERE/'run.sh').read_text();tail=wrapper[wrapper.index('status=$?\n'):]
        for primary in (0,125):
            for rejection in ('export','screen'):
                with self.subTest(primary=primary,rejection=rejection),tempfile.TemporaryDirectory() as temp:
                    root=Path(temp)
                    if rejection=='export':
                        (root/'stage-bootstrap-cd.json').write_text('{"arbitrary":"private"}')
                    else:
                        (root/'serial.log').write_bytes(b'Authorization: Bearer LABELLED-SYNTHETIC-NOT-A-REAL-SECRET')
                    command='set -e\nset +e\n(exit '+str(primary)+')\n'+tail
                    run=subprocess.run(['bash','-c',command],env=dict(os.environ,out=str(root),execution=str(ROOT)),
                                       stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
                    self.assertEqual(run.returncode,primary if primary else 1)
                    self.assertFalse((root/'screened/serial.log').exists())
                    self.assertFalse((root/'screened/stage-bootstrap-cd.json').exists())
        cleanup=wrapper[wrapper.index('cleanup() {\n'):wrapper.index('python3 -B "$HERE/common.py" docker-prep')]
        # Actual EXIT trap body, no container: a nonexistent owned-engine command
        # makes secondary cleanup fail while retaining an existing primary125.
        for primary in (0,125):
            with self.subTest(cleanup_primary=primary),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);(root/'prep-container-id').write_text('1'*64)
                run=subprocess.run(['bash','-c','set -euo pipefail\n'+cleanup+'exit '+str(primary)],
                      env=dict(os.environ,engine='/labelled-synthetic-nonexistent-engine',out=str(root),invocation='2'*32),
                      stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
                self.assertEqual(run.returncode,primary if primary else 1)

    def test_actual_host_failed_acquisition_and_replacement_keep_foreign_inode(self):
        """Actual main/finally with labelled synthetic hardware/image attestation."""
        for failure in ('before-acquisition','after-replacement'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);(root/'data').mkdir();target=root/'OVMF_VARS.fd'
                ctx=dict(schema='arctic-safe-guest-context-v1',image=c.IMAGE,execution_sha='6e14b95cbc8450fe66290499649b79c14d9352bb',binding_id='1'*32,bundle={n:'2'*64 for n in ('common.py','guest.py','taskbar-runtime.py','native_smoke.py','screen-evidence.py','raw-screencopy')})
                (root/'data/context.json').write_text(json.dumps(ctx))
                original_create=host.OwnedTemporaries.create;original_open=builtins.open
                original_stat=Path.stat;original_char=Path.is_char_device;original_sha=c.sha
                original_run=subprocess.run;foreign={}
                def create_foreign():
                    original_run([sys.executable,'-c','import pathlib,sys;pathlib.Path(sys.argv[1]).open("xb").write(b"FOREIGN SYNTHETIC")',str(target)],check=True,timeout=5)
                    info=target.lstat();foreign.update(device=info.st_dev,inode=info.st_ino)
                def create_hook(owner,name):
                    if failure=='before-acquisition' and name=='OVMF_VARS.fd':create_foreign()
                    return original_create(owner,name)
                def open_hook(path,*args,**kwargs):
                    if str(path)=='/usr/share/edk2/ovmf/OVMF_VARS.fd':return io.BytesIO(b'SYNTHETIC FIRMWARE')
                    return original_open(path,*args,**kwargs)
                def disk_hook(argv,**kwargs):
                    self.assertEqual(argv[:5],['qemu-img','create','-q','-f','qcow2'])
                    self.assertEqual(argv[5],'/proc/self/fd/'+str(kwargs['pass_fds'][0]))
                    self.assertEqual(argv[-1],'64G')
                    target.rename(root/'retained-owned-firmware');create_foreign()
                    raise OSError('Labelled synthetic disk initialization failure')
                def stat_hook(path,*args,**kwargs):
                    return types.SimpleNamespace(st_size=c.IMAGE['bytes']) if str(path)=='/iso' else original_stat(path,*args,**kwargs)
                handlers={s:signal.getsignal(s) for s in (signal.SIGTERM,signal.SIGINT)}
                try:
                    with patch.object(sys,'argv',['host.py','--out',str(root)]),patch.object(host.os,'geteuid',return_value=0),\
                         patch.object(Path,'is_char_device',lambda p:True if str(p)=='/dev/kvm' else original_char(p)),\
                         patch.object(Path,'stat',stat_hook),patch.object(c,'sha',lambda p:c.IMAGE['sha256'] if str(p)=='/iso' else original_sha(p)),\
                         patch.dict(sys.modules,{'vmtest':types.ModuleType('vmtest'),'iso_startup':types.ModuleType('iso_startup')}),\
                         patch.object(host.OwnedTemporaries,'create',create_hook),patch.object(builtins,'open',open_hook),\
                         patch.object(host.subprocess,'run',disk_hook):
                        with self.assertRaises(OSError):host.main()
                finally:
                    for s,h in handlers.items():signal.signal(s,h)
                info=target.lstat();self.assertEqual((info.st_dev,info.st_ino),(foreign['device'],foreign['inode']))
                self.assertEqual(target.read_bytes(),b'FOREIGN SYNTHETIC')
                value=c.strict((root/'host-entry-status.json').read_bytes())
                self.assertEqual(value['stage'],'vm-capture')
                self.assertEqual(value['exception_class'],'FileExistsError' if failure=='before-acquisition' else 'OSError')
                self.assertEqual([v['stage'] for v in value['cleanup_errors']],[] if failure=='before-acquisition' else ['temporary-cleanup'])
                self.assertFalse((root/'target.qcow2').exists())

    def test_actual_status_export_excludes_private_raw_and_rejects_arbitrary_json(self):
        wrapper=(HERE/'run.sh').read_text()
        body=re.search(r'python3 - "\$out" "\$execution" <<\x27PY\x27\n(.*?)\nPY\nexport_status=',wrapper,re.S).group(1)
        for poison in (False,True):
            with self.subTest(poison=poison),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);private=b'Authorization: Bearer LABELLED-SYNTHETIC-NO-REAL-SECRET'
                (root/'private-bootstrap-cd-stdout.log').write_bytes(private)
                raw={n:dict(bytes=len(private) if n=='stdout' else 0,sha256=hashlib.sha256(private if n=='stdout' else b'').hexdigest(),complete=True) for n in ('stdout','stderr')}
                value=c.fixed_status('bootstrap-cd','completed',125,None,raw=raw)
                if poison:value['raw_exception_text']='arbitrary private text'
                status=root/'stage-bootstrap-cd.json';status.write_text(json.dumps(value)+'\n')
                run=subprocess.run([sys.executable,'-B','-',str(root),str(ROOT)],input=body.encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
                if poison:
                    self.assertNotEqual(run.returncode,0);self.assertEqual(list((root/'evidence').iterdir()),[])
                else:
                    self.assertEqual(run.returncode,0,run.stderr)
                    self.assertEqual([p.name for p in (root/'evidence').iterdir()],['stage-bootstrap-cd.json'])
                    subprocess.run([sys.executable,'-B',str(ROOT/'tools/native-functional/screen-evidence.py'),'--preserve-original','--source',str(root/'evidence'),'--out',str(root/'screened')],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
                    self.assertEqual((root/'screened/stage-bootstrap-cd.json').read_bytes(),status.read_bytes())
                    self.assertFalse((root/'screened/private-bootstrap-cd-stdout.log').exists())
                    self.assertNotIn(private,(root/'screened/stage-bootstrap-cd.json').read_bytes())

    def invoke_early_host(self,root,uid=1000):
        handlers={s:signal.getsignal(s) for s in (signal.SIGTERM,signal.SIGINT)}
        try:
            with patch.object(sys,'argv',['host.py','--out',str(root)]),patch.object(host.os,'geteuid',return_value=uid):
                host.main()
        finally:
            for s,h in handlers.items():signal.signal(s,h)

    def test_actual_early_root_failure_has_fixed_stage_and_partial_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with self.assertRaisesRegex(RuntimeError,'owned disposable'):self.invoke_early_host(root)
            value=c.strict((root/'host-entry-status.json').read_bytes())
            self.assertEqual((value['stage'],value['status'],value['exception_class']),('root-kvm','exception','RuntimeError'))
            report=c.strict((root/'host-report.json').read_bytes())
            self.assertEqual(report['diagnostic_failure'],dict(stage='root-kvm',exception_class='RuntimeError'))
            self.assertIsNone(report['context']);self.assertEqual(report['baseline'],[])

    def test_actual_early_context_and_image_errors_preserve_stage(self):
        actual_char=Path.is_char_device
        for valid_context,expected,error in [(False,'context',RuntimeError),(True,'image',FileNotFoundError)]:
            with self.subTest(stage=expected),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);(root/'data').mkdir()
                ctx=dict(schema='arctic-safe-guest-context-v1',image=c.IMAGE,execution_sha='6e14b95cbc8450fe66290499649b79c14d9352bb',binding_id='1'*32,bundle={n:'2'*64 for n in ('common.py','guest.py','taskbar-runtime.py','native_smoke.py','screen-evidence.py','raw-screencopy')})
                (root/'data/context.json').write_text(json.dumps(ctx if valid_context else {}))
                with patch.object(Path,'is_char_device',lambda p:True if str(p)=='/dev/kvm' else actual_char(p)):
                    with self.assertRaises(error):self.invoke_early_host(root,uid=0)
                value=c.strict((root/'host-entry-status.json').read_bytes())
                self.assertEqual((value['stage'],value['exception_class']),(expected,error.__name__))

    def test_early_cleanup_and_report_symlinks_cannot_hide_primary_or_delete_foreign(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);foreign=root/'foreign';foreign.write_bytes(b'FOREIGN')
            (root/'host-report.json').symlink_to(foreign);(root/'target.qcow2').symlink_to(foreign)
            with self.assertRaisesRegex(RuntimeError,'owned disposable'):self.invoke_early_host(root)
            self.assertEqual(foreign.read_bytes(),b'FOREIGN');self.assertTrue((root/'target.qcow2').is_symlink())
            value=c.strict((root/'host-entry-status.json').read_bytes())
            self.assertEqual(value['stage'],'root-kvm');self.assertEqual(value['exception_class'],'RuntimeError')
            self.assertEqual([v['stage'] for v in value['cleanup_errors']],['host-report'])
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);foreign=root/'foreign';foreign.mkdir();(foreign/'target.qcow2').write_bytes(b'FOREIGN')
            link=root/'out';link.symlink_to(foreign,target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError,'owned disposable'):self.invoke_early_host(link)
            self.assertEqual((foreign/'target.qcow2').read_bytes(),b'FOREIGN')
            self.assertFalse((foreign/'host-report.json').exists());self.assertFalse((foreign/'host-entry-status.json').exists())


if __name__=='__main__':unittest.main()
