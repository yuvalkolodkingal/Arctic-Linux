"""Meaningful exact-source guard and bounded evidence negative controls; no VM."""
import base64
import ast
import builtins
import copy
import hashlib
import importlib.util
import io
import json
import os
import signal
import shlex
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


def without_guest_projection(wrapper):
    wrapper=re.sub(r'# Begin reviewed guest fixed-status projection;.*?# End reviewed guest fixed-status projection.\n','',wrapper,count=1,flags=re.S)
    wrapper=wrapper.replace(",'guest-entry-status.json'",'')
    wrapper=wrapper.replace("        if path.name=='guest-entry-status.json':\n            c.validate_guest_status(c.strict(c.regular(path).read_bytes()),guest_context)\n",'')
    return wrapper


def actual_failed_v2_wrapper(wrapper):
    """Undo only this ownership correction and attest all original v2 bytes."""
    wrapper=without_guest_projection(wrapper)
    wrapper=wrapper.replace('device=$(blkid -t LABEL=ARCTICSAFE -o device)\n[ -b "$device" ]\nlabel=$(blkid -s LABEL -o value "$device")\n[ "$label" = ARCTICSAFE ]',
                            '[ "$(blkid -s LABEL -o value /dev/sr1)" = ARCTICSAFE ]')
    wrapper=wrapper.replace('mount -t iso9660 -o ro,nodev,nosuid "$device" /run/t',
                            'mount -t iso9660 -o ro,nodev,nosuid /dev/sr1 /run/t')
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
        for target,paths in ((cls.repo,['tools/safe-diagnostic','.github/workflows/safe-diagnostic-v7-20261010.yml',c.MARKER,*c.EXECUTION_FILES]),
                             (cls.source,list(c.SOURCE_FILES))):
            subprocess.run(['git','clone','--quiet','--shared','--no-checkout',str(ROOT),str(target)],check=True,timeout=30)
            git(target,'sparse-checkout','set','--no-cone',*paths)
            git(target,'checkout','--detach',c.IMAGE['source_sha'])
            git(target,'config','user.name','Safe source controls');git(target,'config','user.email','safe-source-controls@invalid.local')
        for path in HERE.iterdir():
            if path.is_file() and path.suffix in ('.py','.c','.sh','.json','.md'):
                destination=cls.repo/'tools/safe-diagnostic'/path.name;destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_bytes(path.read_bytes());destination.chmod(path.stat().st_mode & 0o777)
        workflow=cls.repo/'.github/workflows/safe-diagnostic-v7-20261010.yml';workflow.parent.mkdir(parents=True,exist_ok=True)
        workflow.write_bytes((ROOT/workflow.relative_to(cls.repo)).read_bytes())
        private_manifest=cls.repo/'tools/safe-diagnostic/execution-manifest.json'
        private_value=c.strict(private_manifest.read_bytes());private_value['ready']=True
        private_manifest.write_text(json.dumps(private_value,sort_keys=True,indent=2)+'\n')
        git(cls.repo,'add','tools/safe-diagnostic','.github/workflows/safe-diagnostic-v7-20261010.yml')
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


class ExtraCDTopology(unittest.TestCase):
    def test_cached_actual_q35_paused_two_cd_old_rejection_and_fixed_ports(self):
        """Only synthetic device wiring, TCG paused; no ISO/OS/guest claim."""
        image='sha256:3c41bf8a38534181a1612949768dfae5af46c21931acfccceacf7c9e0cfe9afb'
        env=dict(os.environ)
        for key in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'):env.pop(key,None)
        engine=['docker','--host=unix:///var/run/docker.sock']
        if not shutil.which('docker'):self.skipTest('Cached QEMU topology prerequisite unavailable')
        available=subprocess.run(engine+['image','inspect',image],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
        if available.returncode:self.skipTest('Cached QEMU topology image unavailable; no pull is performed')
        host_raw=(HERE/'host.py').read_bytes();old=host_raw.replace(b"'ide-cd,drive=data,bus=ide.1'",b"'ide-cd,drive=data'")
        old=old.replace(b'''sudo sh -c \\'d=$(blkid -t LABEL=ARCTICSAFE -o device) && [ -b "$d" ] && label=$(blkid -s LABEL -o value "$d") && [ "$label" = ARCTICSAFE ] && exec sh "$d" "$1"\\' sh ''',b'sudo sh /dev/sr1 ')
        self.assertEqual(host_raw.count(b"'ide-cd,drive=data,bus=ide.1'"),1)
        self.assertEqual(host_raw.count(b"'ide-cd,drive=cd,bootindex=0'"),1)
        self.assertEqual(hashlib.sha256(old).hexdigest(),'a131abc80a4717a34affadb916bb3f7aae73381a7b2362c207565d7c026c9160')
        code=r'''
import hashlib,json,os,pathlib,re,socket,subprocess,tempfile,time
binary='/usr/sbin/qemu-system-x86_64'
sha=hashlib.sha256(pathlib.Path(binary).read_bytes()).hexdigest()
version=subprocess.check_output([binary,'--version'],text=True).splitlines()[0]
assert '10.2.2' in version
records=[]
with tempfile.TemporaryDirectory(dir='/fixture') as tmp:
 root=pathlib.Path(tmp)
 for name in ('cd','data'):(root/(name+'.raw')).write_bytes(b'\0'*65536)
 for fixed in (False,True):
  qmp=root/('qmp-fixed' if fixed else 'qmp-old')
  argv=[binary,'-machine','q35','-accel','tcg','-S','-m','64','-nodefaults','-display','none',
       '-qmp','unix:'+str(qmp)+',server=on,wait=off',
       '-drive','file='+str(root/'cd.raw')+',media=cdrom,readonly=on,if=none,id=cd',
       '-device','ide-cd,drive=cd,bootindex=0',
       '-drive','file='+str(root/'data.raw')+',media=cdrom,readonly=on,if=none,id=data',
       '-device','ide-cd,drive=data'+(',bus=ide.1' if fixed else '')]
  proc=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  sock=None;stream=None
  try:
   if not fixed:
    output,error=proc.communicate(timeout=10)
    assert proc.returncode!=0 and b"Can't create IDE unit 1, bus supports only 1 units" in error
    records.append(dict(fixed=False,argv=argv,returncode=proc.returncode,original_stderr=error.decode(),stdout_bytes=len(output)))
   else:
    until=time.monotonic()+10
    while not qmp.exists() and time.monotonic()<until:
     assert proc.poll() is None;time.sleep(.05)
    sock=socket.socket(socket.AF_UNIX);sock.settimeout(5);sock.connect(str(qmp));stream=sock.makefile('rwb')
    greeting_raw=stream.readline();greeting=json.loads(greeting_raw);assert 'QMP' in greeting
    qmp_wire=[dict(direction='greeting',original=greeting_raw.decode())]
    def command(name,arguments=None):
     request=(json.dumps(dict(execute=name,arguments=arguments or {}))+'\n').encode()
     qmp_wire.append(dict(direction='request',original=request.decode()));stream.write(request);stream.flush()
     for _ in range(20):
      answer_raw=stream.readline();qmp_wire.append(dict(direction='reply',original=answer_raw.decode()))
      answer=json.loads(answer_raw);assert 'error' not in answer
      if 'return' in answer:return answer['return']
     raise RuntimeError('Bounded QMP reply missing')
    command('qmp_capabilities');status=command('query-status');blocks=command('query-block')
    assert status['running'] is False and status['status'] in ('prelaunch','paused')
    assert {b['device'] for b in blocks}=={'cd','data'} and all(b['inserted']['ro'] is True for b in blocks)
    tree=command('human-monitor-command',{'command-line':'info qtree'});ports={}
    for block in blocks:
     parent=command('qom-get',{'path':block['qdev'],'property':'parent_bus'})
     bus=parent.rsplit('/',1)[-1];assert re.fullmatch(r'ide\.[0-5]',bus)
     assert bus not in ports;ports[bus]=block['device']
    assert ports['ide.1']=='data' and len(ports)==2
    command('quit');output,error=proc.communicate(timeout=10);assert proc.returncode==0
    records.append(dict(fixed=True,returncode=0,argv=argv,qmp_wire=qmp_wire,status=status,blocks=blocks,ports=ports,original_qtree=tree,
                        original_stderr=error.decode(),stdout_bytes=len(output)))
  finally:
   if stream is not None:stream.close()
   if sock is not None:sock.close()
   if proc.poll() is None:proc.kill();proc.communicate(timeout=5)
print(json.dumps(dict(schema='arctic-safe-synthetic-q35-cd-topology-v1',qemu_sha256=sha,qemu_version=version,
                     actual_v4_qemu_sha256='27cd395848940fc6482256d85096fc64bc4fe3f3e909824d51c202f8314cd9e9',
                     same_binary_as_actual_v4=sha=='27cd395848940fc6482256d85096fc64bc4fe3f3e909824d51c202f8314cd9e9',
                     records=records,synthetic_cd_bytes_each=65536,TCG=True,paused=True,OS_boot=False,KVM=False,
                     image_qualified=False,release_acceptance=False)))
'''
        token=uuid.uuid4().hex;name='arctic-safe-q35-'+token
        argv=engine+['run','--rm','--pull=never','--name',name,'--label','org.arctic.safe.fixture='+token,
                     '--network','none','--read-only','--security-opt','no-new-privileges','--cap-drop=ALL',
                     '--tmpfs','/fixture:rw,size=8m,mode=1777',image,'python3','-B','-c',code]
        try:
            run=subprocess.run(argv,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
            self.assertEqual(run.returncode,0,run.stderr)
            value=json.loads(run.stdout);self.assertEqual(value['records'][1]['ports']['ide.1'],'data')
            self.assertEqual(set(value['records'][1]['ports'].values()),{'cd','data'})
            self.assertTrue(value['same_binary_as_actual_v4'])
            print('SYNTHETIC_Q35_TOPOLOGY_CONTROL='+json.dumps(dict(**value,container_name=name,owned_label=token,
                  executed_python_sha256=hashlib.sha256(code.encode()).hexdigest()),sort_keys=True))
        finally:
            check=subprocess.run(engine+['container','inspect',name],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
            if check.returncode==0:
                rows=json.loads(check.stdout);self.assertEqual(len(rows),1)
                self.assertEqual(rows[0]['Name'],'/'+name);self.assertEqual(rows[0]['Config']['Labels']['org.arctic.safe.fixture'],token)
                subprocess.run(engine+['rm','-f',rows[0]['Id']],env=env,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=10)


class DiagnosticLabel(unittest.TestCase):
    def test_exact_console_and_bootstrap_unique_label_guards_fail_closed(self):
        wrapper=(HERE/'run.sh').read_text()
        bootstrap=re.search(r"<<'BOOTSTRAP'\n(.*?)\nBOOTSTRAP\n",wrapper,re.S).group(1)+'\n'
        prefix=bootstrap.split('python3 -I - "$1"',1)[0]
        literals=[n.left.value for n in ast.walk(ast.parse((HERE/'host.py').read_text()))
                  if isinstance(n,ast.BinOp) and isinstance(n.left,ast.Constant)
                  and isinstance(n.left.value,str) and n.left.value.startswith('sudo sh -c ')]
        self.assertEqual(len(literals),1)
        argv=shlex.split(literals[0]);self.assertEqual(argv[:3],['sudo','sh','-c']);console=argv[3]
        rollback=without_guest_projection(wrapper).replace('device=$(blkid -t LABEL=ARCTICSAFE -o device)\n[ -b "$device" ]\nlabel=$(blkid -s LABEL -o value "$device")\n[ "$label" = ARCTICSAFE ]',
                 '[ "$(blkid -s LABEL -o value /dev/sr1)" = ARCTICSAFE ]').replace(
                 'mount -t iso9660 -o ro,nodev,nosuid "$device" /run/t',
                 'mount -t iso9660 -o ro,nodev,nosuid /dev/sr1 /run/t')
        self.assertEqual(hashlib.sha256(rollback.encode()).hexdigest(),
                         '8aa8b127b03ccb31d3d8f044fe954ff5e14ae4b1b5c4d2b3e848e8e7739a38c1')
        # These are labelled shell guards, with synthetic root/block predicates.
        # Real tiny ISO label discovery is exercised independently below.
        helpers=r'''
blkid() {
 if [[ "$*" == '-t LABEL=ARCTICSAFE -o device' ]]; then printf '%s' "$SELECTED"; return "$DISCOVERY_STATUS"; fi
 if [[ "$1 $2 $3 $4" == '-s LABEL -o value' && "$5" == "$GOOD" ]]; then printf '%s' "$DEVICE_LABEL"; return "$LABEL_STATUS"; fi
 return 2
}
[() { if [[ "$1" == '-b' ]]; then [[ "$BLOCK_OK" == 1 && "$2" == "$GOOD" ]]; else builtin [ "$@"; fi; }
id() { [[ "$*" == '-u' ]] && printf '0\n'; }
mkdir() { [[ "$*" == '-p /run/t' ]]; }
mountpoint() { [[ "$*" == '-q /run/t' ]] && return 1; return 2; }
mount() { printf '%s\n' "$@" >"$MOUNT_RECEIPT"; }
'''
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);device=base/'owned-synthetic-device'
            device.write_text('printf "%s\\n" "$1" >"$EXEC_RECEIPT"\n')
            foreign=base/'foreign';foreign.write_bytes(b'FOREIGN');link=base/'poison-symlink';link.symlink_to(foreign)
            cases=[('valid',str(device),'ARCTICSAFE',0,0,'1',True),
                   ('missing','','ARCTICSAFE',0,0,'1',False),
                   ('duplicate',str(device)+'\n'+str(device),'ARCTICSAFE',0,0,'1',False),
                   ('wrong-label',str(device),'WRONGSAFE',0,0,'1',False),
                   ('discovery-failed-with-valid-output',str(device),'ARCTICSAFE',2,0,'1',False),
                   ('label-query-failed-with-valid-output',str(device),'ARCTICSAFE',0,2,'1',False),
                   ('regular-file',str(device),'ARCTICSAFE',0,0,'0',False),
                   ('foreign-regular',str(foreign),'ARCTICSAFE',0,0,'1',False),
                   ('poison-symlink',str(link),'ARCTICSAFE',0,0,'1',False)]
            records=[]
            for kind,body in (('console',console),('bootstrap',prefix)):
                for name,selected,label,discovery_status,label_status,block,accepted in cases:
                    exec_receipt=base/'executed';mount_receipt=base/'mounted'
                    for p in (exec_receipt,mount_receipt):p.unlink(missing_ok=True)
                    env=dict(os.environ,SELECTED=selected,DEVICE_LABEL=label,DISCOVERY_STATUS=str(discovery_status),
                             LABEL_STATUS=str(label_status),BLOCK_OK=block,GOOD=str(device),EXEC_RECEIPT=str(exec_receipt),MOUNT_RECEIPT=str(mount_receipt))
                    r=subprocess.run(['bash','-c',helpers+'\n'+body,'sh','OWNED_BINDING'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
                    self.assertEqual(r.returncode==0,accepted,(kind,name,r.returncode,r.stderr))
                    self.assertEqual(exec_receipt.exists(),accepted and kind=='console')
                    self.assertEqual(mount_receipt.exists(),accepted and kind=='bootstrap')
                    if exec_receipt.exists():self.assertEqual(exec_receipt.read_text(),'OWNED_BINDING\n')
                    if mount_receipt.exists():self.assertEqual(mount_receipt.read_text().splitlines(),['-t','iso9660','-o','ro,nodev,nosuid',str(device),'/run/t'])
                    self.assertEqual(foreign.read_bytes(),b'FOREIGN');self.assertTrue(link.is_symlink())
                    records.append(dict(consumer=kind,case=name,returncode=r.returncode,accepted=accepted))
            print('SYNTHETIC_LABEL_GUARD_CONTROL='+json.dumps(dict(records=records,
                  console_body_sha256=hashlib.sha256(console.encode()).hexdigest(),bootstrap_prefix_sha256=hashlib.sha256(prefix.encode()).hexdigest(),
                  synthetic_root_and_block_predicates=True,actual_mount=False,actual_guest=False,release_acceptance=False),sort_keys=True))

    def test_cached_real_xorriso_generated_system_area_and_unique_iso_label(self):
        image='sha256:3c41bf8a38534181a1612949768dfae5af46c21931acfccceacf7c9e0cfe9afb'
        env=dict(os.environ)
        for key in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'):env.pop(key,None)
        engine=['docker','--host=unix:///var/run/docker.sock']
        if not shutil.which('docker'):self.skipTest('Cached ISO-label prerequisite unavailable')
        available=subprocess.run(engine+['image','inspect',image],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
        if available.returncode:self.skipTest('Cached ISO-label image unavailable; no pull is performed')
        wrapper=(HERE/'run.sh').read_text();bootstrap=re.search(r"<<'BOOTSTRAP'\n(.*?)\nBOOTSTRAP\n",wrapper,re.S).group(1)+'\n'
        original_argv=shlex.split(re.search(r'^ xorriso .*$',wrapper,re.M).group(0))
        self.assertEqual(original_argv,['xorriso','-as','mkisofs','-quiet','-V','ARCTICSAFE','-J','-R','-uid','0','-gid','0','-G','/out/system-area.sh','-o','/out/data.iso','/out/data'])
        code=r'''
import base64,hashlib,json,pathlib,subprocess,tempfile
bootstrap=base64.b64decode(BOOTSTRAP_B64);original_argv=ORIGINAL_ARGV
def sha(raw):return hashlib.sha256(raw).hexdigest()
records=[]
with tempfile.TemporaryDirectory(dir='/fixture') as tmp:
 root=pathlib.Path(tmp);data=root/'data';data.mkdir();(data/'owned-label-fixture').write_bytes(b'ARCTIC_SYNTHETIC_LABEL_FIXTURE\n')
 script=root/'system-area.sh';script.write_bytes(bootstrap)
 for label in ('ARCTICSAFE','WRONGSAFE'):
  dest=root/(label+'.iso');argv=[str(root/value[len('/out/'):]) if value.startswith('/out/') else value for value in original_argv]
  argv[argv.index('-V')+1]=label;argv[argv.index('-o')+1]=str(dest)
  result=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10);assert result.returncode==0
  raw=dest.read_bytes();assert raw.startswith(bootstrap) and raw[16*2048+1:16*2048+6]==b'CD001'
  pvd_label=raw[16*2048+40:16*2048+72].decode().rstrip(' ');assert pvd_label==label
  probe_argv=['blkid','-p','-s','LABEL','-o','value',str(dest)]
  probe=subprocess.run(probe_argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
  assert probe.returncode==0 and probe.stdout.decode().strip()==label
  records.append(dict(label=label,original_argv=argv,xorriso_returncode=result.returncode,
                      original_stdout=result.stdout.decode(),original_stderr=result.stderr.decode(),
                      bytes=len(raw),sha256=sha(raw),system_area_matches=True,bootstrap_sha256=sha(bootstrap),
                      original_probe_argv=probe_argv,probe_returncode=probe.returncode,original_probe_stdout=probe.stdout.decode(),
                      original_probe_stderr=probe.stderr.decode(),pvd_label=pvd_label,accepted_label=label=='ARCTICSAFE'))
 binaries={}
 for name in ('xorriso','blkid'):
  version=subprocess.run([name,'--version'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
  binaries[name]=dict(sha256=sha(pathlib.Path('/usr/sbin/'+name).read_bytes()),
                      version=(version.stdout+version.stderr).decode().splitlines()[0],version_returncode=version.returncode)
print(json.dumps(dict(schema='arctic-safe-synthetic-iso-label-v1',binaries=binaries,records=records,
                     actual_guest=False,actual_ISO=False,KVM=False,release_acceptance=False)))
'''.replace('BOOTSTRAP_B64',repr(base64.b64encode(bootstrap.encode()).decode())).replace('ORIGINAL_ARGV',repr(original_argv))
        token=uuid.uuid4().hex;name='arctic-safe-iso-label-'+token
        argv=engine+['run','--rm','--pull=never','--name',name,'--label','org.arctic.safe.fixture='+token,
                     '--network','none','--read-only','--security-opt','no-new-privileges','--cap-drop=ALL',
                     '--tmpfs','/fixture:rw,size=8m,mode=1777',image,'python3','-B','-c',code]
        try:
            run=subprocess.run(argv,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=40)
            self.assertEqual(run.returncode,0,run.stderr);value=json.loads(run.stdout)
            self.assertEqual([r['label'] for r in value['records']],['ARCTICSAFE','WRONGSAFE'])
            print('SYNTHETIC_ISO_LABEL_CONTROL='+json.dumps(dict(**value,container_name=name,owned_label=token,
                  executed_python_sha256=hashlib.sha256(code.encode()).hexdigest()),sort_keys=True))
        finally:
            check=subprocess.run(engine+['container','inspect',name],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
            if check.returncode==0:
                rows=json.loads(check.stdout);self.assertEqual(len(rows),1)
                self.assertEqual(rows[0]['Name'],'/'+name);self.assertEqual(rows[0]['Config']['Labels']['org.arctic.safe.fixture'],token)
                subprocess.run(engine+['rm','-f',rows[0]['Id']],env=env,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=10)


class GuestPhase(unittest.TestCase):
    def fixture(self, root):
        bundle={name:b'OWNED_SYNTHETIC_GUEST_BUNDLE\n' for name in
                ('common.py','guest.py','taskbar-runtime.py','native_smoke.py','raw-screencopy','screen-evidence.py')}
        for name,raw in bundle.items():(root/name).write_bytes(raw)
        ctx=dict(schema='arctic-safe-guest-context-v1',image=c.IMAGE,execution_sha='a'*40,
                 binding_id='b'*32,bundle={name:hashlib.sha256(raw).hexdigest() for name,raw in bundle.items()})
        (root/'context.json').write_text(json.dumps(ctx));return ctx

    def module(self, root):
        source=(HERE/'guest.py').read_bytes();tree=ast.parse(source)
        # Only module path/common-load bindings differ in this private fixture.
        # The actual guest main/execute/try/finally bodies remain byte-derived.
        tree.body=[n for n in tree.body if not (isinstance(n,ast.Assign) and any(
                 isinstance(t,ast.Name) and t.id in ('BASE','c') for t in n.targets))]
        namespace=dict(__name__='safe_guest_phase_fixture',__file__=str(root/'guest.py'),BASE=root,c=c)
        exec(compile(tree,str(HERE/'guest.py'),'exec'),namespace);return namespace

    def test_actual_guest_main_early_paths_emit_only_after_valid_context(self):
        cases=[('entry',None,'bad-argv',None),('context',None,'bad-context',None),
               ('bundle','RuntimeError','bad-bundle','bundle'),
               ('native-import','ModuleNotFoundError','bad-import','native-import'),
               ('native-guard','OTHER','bad-guard','native-guard')]
        for _,klass,kind,phase in cases:
            with self.subTest(case=kind),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);ctx=self.fixture(root);g=self.module(root)
                if kind=='bad-context':
                    value=copy.deepcopy(ctx);value['binding_id']='PRIVATE_INVALID_CONTEXT';(root/'context.json').write_text(json.dumps(value))
                if kind=='bad-bundle':(root/'raw-screencopy').write_bytes(b'FOREIGN_WRONG_HASH')
                private='PRIVATE_TRANSCRIPT_SECRET_PATH_ACCOUNT'
                def loader(name,path):
                    if name=='safe_transport':return types.SimpleNamespace(read_regular=lambda p,**kw:p.read_bytes())
                    if name=='safe_privacy':return types.SimpleNamespace()
                    if name=='safe_native':
                        if kind=='bad-import':raise ModuleNotFoundError(private)
                        def guard(*args):raise type('PrivateInjectedException',(RuntimeError,),{})(private)
                        return types.SimpleNamespace(guest_guard=guard)
                    raise AssertionError('Unexpected fixture import')
                g['load']=loader;stream=io.StringIO()
                argv=['fixture.py']+(['wrong'] if kind=='bad-argv' else ['--disposable-guest'])
                with patch.object(sys,'argv',argv),patch.object(os,'geteuid',return_value=0),patch.object(sys,'stdout',stream):
                    self.assertEqual(g['execute'](),1)
                raw=stream.getvalue().encode();self.assertNotIn(private.encode(),raw);self.assertNotIn(b'PRIVATE_INVALID_CONTEXT',raw)
                self.assertEqual(raw.count(b'ARCTIC-SAFE-DIAGNOSTIC-FAILED'),1)
                value=c.project_guest_status(raw,ctx)
                if phase is None:self.assertIsNone(value)
                else:
                    self.assertEqual(value['phase'],phase);self.assertEqual(value['exception_class'],klass)
                    self.assertEqual(value['binding_id'],ctx['binding_id']);self.assertEqual(value['status'],'exception')

    def test_actual_guest_try_cleanup_and_closed_stdout_keep_primary_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);ctx=self.fixture(root);g=self.module(root)
            tree=ast.parse((HERE/'guest.py').read_bytes());main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
            guarded=next(n for n in main.body if isinstance(n,ast.Try))
            code=compile(ast.fix_missing_locations(ast.Module(body=[guarded],type_ignores=[])),str(HERE/'guest.py'),'exec')
            def fail_send(*args):raise ValueError('PRIVATE_PRIMARY_TRANSCRIPT')
            def actual_try():
                g['_guest_context']=ctx;g.update(channel=types.SimpleNamespace(send=fail_send),ctx=ctx,name='SYNTHETIC_OUTPUT',foot=None,foot_fd=None,fd=-1)
                exec(code,g)
            g['main']=actual_try;stream=io.StringIO()
            with patch.object(os,'close',side_effect=PermissionError('PRIVATE_CLEANUP_TRANSCRIPT')),patch.object(sys,'stdout',stream):
                self.assertEqual(g['execute'](),1)
            value=c.project_guest_status(stream.getvalue().encode(),ctx)
            self.assertEqual((value['phase'],value['exception_class']),('hello-send','ValueError'))
            self.assertNotIn('PRIVATE_',stream.getvalue())
            class Closed:
                def write(self,value):raise BrokenPipeError('PRIVATE_CLOSED_STDOUT')
                def flush(self):raise BrokenPipeError('PRIVATE_CLOSED_STDOUT')
            with patch.object(os,'close',side_effect=PermissionError('PRIVATE_CLEANUP_TRANSCRIPT')),patch.object(sys,'stdout',Closed()):
                self.assertEqual(g['execute'](),1)
            self.assertEqual(g['_guest_primary'],('hello-send','ValueError'))

    def test_fixed_guest_status_binding_types_classes_duplicates_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx=self.fixture(Path(tmp));valid=c.guest_status('package-query','exception','RuntimeError',ctx)
            raw=(c.GUEST_STATUS_PREFIX+json.dumps(valid)+'\n').encode();self.assertEqual(c.project_guest_status(raw,ctx),valid)
            for key,value in [('phase','PRIVATE_ERROR'),('phase',[]),('status','success'),('exception_class','PRIVATE_TRANSCRIPT'),
                              ('binding_id','c'*32),('execution_sha','c'*40),('image_source_sha','c'*40),('schema','unknown'),
                              ('release_acceptance',0),('release_acceptance',True),('image_qualified',True),
                              ('performance_acceptance',True),('observer_profile_admitted',True)]:
                candidate=copy.deepcopy(valid);candidate[key]=value
                with self.subTest(field=key,value=value),self.assertRaises(RuntimeError):c.project_guest_status((c.GUEST_STATUS_PREFIX+json.dumps(candidate)).encode(),ctx)
            for extra in ('message','path','environment','account','command'):
                candidate=dict(valid,**{extra:'PRIVATE_TRANSCRIPT'})
                with self.assertRaises(RuntimeError):c.validate_guest_status(candidate,ctx)
            with self.assertRaises(RuntimeError):c.project_guest_status(raw+raw,ctx)
            with self.assertRaises(RuntimeError):c.project_guest_status((c.GUEST_STATUS_PREFIX+' '*2049).encode(),ctx)
            with self.assertRaises(RuntimeError):c.project_guest_status((c.GUEST_STATUS_PREFIX+'{"phase":1,"phase":2}').encode(),ctx)
            self.assertIsNone(c.project_guest_status(b'ARCTIC-SAFE-DIAGNOSTIC-FAILED\n',ctx))
            self.assertEqual(c.guest_status('complete','completed',None,ctx)['exception_class'],None)
            with self.assertRaises(RuntimeError):c.guest_status('entry','completed',None,ctx)

    def test_actual_wrapper_projects_only_bound_fixed_record_without_foreign_write(self):
        wrapper=(HERE/'run.sh').read_text();marker='python3 - "$out" "$execution" <<\'PY\'\n'
        body=wrapper[wrapper.rindex(marker)+len(marker):].split('\nPY\n',1)[0]
        for kind in ('valid','wrong-nonce','extra-private-field','duplicate','foreign-status'):
            with self.subTest(case=kind),tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp);data=out/'data';data.mkdir();ctx=self.fixture(data)
                value=c.guest_status('port-open','exception','PermissionError',ctx)
                if kind=='wrong-nonce':value['binding_id']='c'*32
                if kind=='extra-private-field':value['message']='PRIVATE_TRANSCRIPT'
                raw=(c.GUEST_STATUS_PREFIX+json.dumps(value)+'\n').encode()
                if kind=='duplicate':raw*=2
                (out/'serial.log').write_bytes(raw)
                if kind=='foreign-status':(out/'guest-entry-status.json').write_bytes(b'FOREIGN')
                run=subprocess.run([sys.executable,'-B','-c',body,str(out),str(ROOT)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
                self.assertEqual(run.returncode==0,kind=='valid')
                self.assertEqual((out/'serial.log').read_bytes(),raw)
                if kind=='valid':
                    projected=c.strict((out/'guest-entry-status.json').read_bytes());self.assertEqual(projected,value)
                    self.assertEqual((out/'evidence/guest-entry-status.json').read_bytes(),(out/'guest-entry-status.json').read_bytes())
                elif kind=='foreign-status':self.assertEqual((out/'guest-entry-status.json').read_bytes(),b'FOREIGN')
                else:self.assertFalse((out/'guest-entry-status.json').exists())


class DuplexPort(unittest.TestCase):
    def fixture(self):
        """Real owned pipe/socket FDs; explicitly synthetic sysfs/char metadata."""
        import errno, stat
        from pathlib import PurePosixPath
        model=types.SimpleNamespace(open_calls=[],dup_calls=[],close_calls=[],references=set(),
            created=set(),peer=None,mutation=None,dup_failure=False,close_failure=None,
            sysfs_uid=0,sysfs_mode=0o644,sysfs_name='arctic-safe-evidence',sysfs_device='240:1')
        class ProtectedPath:
            def __init__(self,p):self.p=PurePosixPath(p)
            def __truediv__(self,p):return ProtectedPath(self.p/p)
            def __str__(self):return str(self.p)
            def __eq__(self,p):return isinstance(p,ProtectedPath) and self.p==p.p
            @property
            def parent(self):return ProtectedPath(self.p.parent)
            @property
            def name(self):return self.p.name
            def resolve(self,strict=True):return ProtectedPath('/dev/vport9p1')
            def stat(self):return types.SimpleNamespace(st_uid=model.sysfs_uid,st_mode=stat.S_IFREG|model.sysfs_mode)
            def read_text(self):return model.sysfs_name if self.name=='name' else model.sysfs_device
        class Syscalls:
            def __getattr__(self,name):return getattr(os,name)
            def open(self,path,flags):
                model.open_calls.append(dict(path=str(path),flags=flags))
                if model.references:raise OSError(errno.EBUSY,'synthetic exclusive-open driver')
                if flags&os.O_ACCMODE==os.O_RDWR:
                    left,right=socket.socketpair();fd,model.peer=left.detach(),right.detach()
                else:model.peer,fd=os.pipe()
                os.set_blocking(fd,False);model.created.update((fd,model.peer));model.references.add(fd);return fd
            def dup(self,fd):
                model.dup_calls.append(fd)
                if model.dup_failure:raise OSError(errno.EMFILE,'synthetic acquired-dup failure')
                other=os.dup(fd);model.created.add(other);model.references.add(other);return other
            def fstat(self,fd):
                os.fstat(fd)
                result=dict(st_mode=stat.S_IFCHR|0o600,st_uid=0,st_rdev=os.makedev(240,1),st_ino=999)
                if model.mutation and model.dup_calls and fd!=model.dup_calls[0]:result.update(model.mutation)
                return types.SimpleNamespace(**result)
            def close(self,fd):
                os.close(fd);model.created.discard(fd);model.references.discard(fd);model.close_calls.append(fd)
                if model.close_failure==fd:raise OSError(errno.EIO,'synthetic close after releasing owned fd')
        proxy=Syscalls()
        source=(ROOT/'tools/native-functional/taskbar-runtime.py').read_text();tree=ast.parse(source)
        writer=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='PortWriter')
        opener=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='open_port')
        ns=dict(os=proxy,time=time,TIMEOUT=1500,require=c.require,Path=ProtectedPath,re=re,stat=stat,PORT_NAME='arctic-safe-evidence')
        exec(compile(ast.Module(body=[writer,opener],type_ignores=[]),'actual-pinned-runtime-port-controls','exec'),ns)
        runtime=types.SimpleNamespace(PORT_NAME='arctic-safe-evidence',require=c.require,PortWriter=ns['PortWriter'],open_port=ns['open_port'])
        guest=ast.parse((HERE/'guest.py').read_text());helpers=[n for n in guest.body if isinstance(n,ast.FunctionDef) and n.name in ('_open_duplex_port','_duplex_fd')]
        ns.update(c=c);exec(compile(ast.Module(body=helpers,type_ignores=[]),'actual-safe-duplex-port-controls','exec'),ns)
        def cleanup():
            for fd in list(model.created):
                try:os.close(fd)
                except OSError:pass
                model.created.discard(fd)
        return model,proxy,runtime,ns,cleanup

    def test_exact_opener_retains_all_pinned_runtime_guards_except_duplex_access(self):
        source=ast.parse((ROOT/'tools/native-functional/taskbar-runtime.py').read_text())
        old=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='open_port')
        guest=ast.parse((HERE/'guest.py').read_text())
        new=copy.deepcopy(next(n for n in guest.body if isinstance(n,ast.FunctionDef) and n.name=='_open_duplex_port'))
        new.name='open_port';new.args.args=[]
        class Rollback(ast.NodeTransformer):
            def visit_Attribute(self,node):
                if isinstance(node.value,ast.Name) and node.value.id=='runtime' and node.attr in ('PORT_NAME','require','PortWriter'):
                    return ast.Name(id=node.attr,ctx=node.ctx)
                if isinstance(node.value,ast.Name) and node.value.id=='os' and node.attr=='O_RDWR':node.attr='O_WRONLY'
                return self.generic_visit(node)
        self.assertEqual(ast.dump(Rollback().visit(new),include_attributes=False),ast.dump(old,include_attributes=False))
        for field,value in (('sysfs_uid',1),('sysfs_mode',0o666),('sysfs_name','another-channel'),('sysfs_device','malformed')):
            with self.subTest(field=field):
                model,proxy,runtime,ns,cleanup=self.fixture()
                try:
                    setattr(model,field,value)
                    with self.assertRaises(RuntimeError):ns['_open_duplex_port'](runtime)
                    self.assertEqual(model.open_calls,[]);self.assertEqual(model.created,set())
                finally:cleanup()

    def test_one_actual_owned_open_dup_is_duplex_and_original_double_open_is_rejected(self):
        import errno,fcntl,stat
        model,proxy,runtime,ns,cleanup=self.fixture();foreign_r,foreign_w=os.pipe()
        try:
            writer,port=ns['_open_duplex_port'](runtime);original=writer.fd
            fd=ns['_duplex_fd'](writer)
            self.assertIsNone(writer.fd);self.assertEqual(len(model.open_calls),1);self.assertEqual(model.dup_calls,[original])
            self.assertEqual(model.references,{fd});self.assertEqual(model.close_calls,[original])
            with self.assertRaises(OSError):os.fstat(original)
            self.assertEqual(fcntl.fcntl(fd,fcntl.F_GETFL)&os.O_ACCMODE,os.O_RDWR)
            self.assertFalse(os.get_inheritable(fd))
            channel=c.Channel(fd,'a'*32)
            channel.send('HELLO',dict(execution_sha='b'*40))
            hello=json.loads(os.read(model.peer,4096));self.assertEqual(hello['kind'],'HELLO')
            os.write(model.peer,(json.dumps(dict(binding_id='a'*32,kind='HELLO-ACK',payload=dict(execution_sha='b'*40)))+'\n').encode())
            self.assertEqual(channel.expect('HELLO-ACK',dict(execution_sha='b'*40)),dict(execution_sha='b'*40))
            proxy.close(fd);self.assertEqual(model.references,set());os.fstat(foreign_r);os.fstat(foreign_w)
            print('SYNTHETIC_DUPLEX_OWNED_FD_CONTROL='+json.dumps(dict(one_requested_device_open=True,actual_owned_dup=True,
                actual_fd_mode='O_RDWR',actual_local_channel_roundtrip=True,unrelated_canary_preserved=True,
                synthetic_protected_sysfs_and_character_metadata=True,actual_virtio_guest=False,release_acceptance=False)))
        finally:cleanup();os.close(foreign_r);os.close(foreign_w)
        model,proxy,runtime,ns,cleanup=self.fixture()
        try:
            writer,port=runtime.open_port()
            with self.assertRaises(OSError) as failure:
                proxy.open(port['device'],os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_NOCTTY)
            self.assertEqual(failure.exception.errno,errno.EBUSY);self.assertEqual(len(model.open_calls),2)
            self.assertEqual(model.dup_calls,[]);writer.close();self.assertEqual(model.references,set())
        finally:cleanup()

    def test_partial_dup_identity_and_close_failures_release_only_acquired_fds(self):
        import errno,stat
        cases=[('dup',None),('owner',{'st_uid':1}),('mode',{'st_mode':stat.S_IFCHR|0o666}),
               ('type',{'st_mode':stat.S_IFREG|0o600}),('rdev',{'st_rdev':os.makedev(240,2)}),('inode',{'st_ino':1000}),('close',None)]
        for kind,mutation in cases:
            with self.subTest(kind=kind):
                model,proxy,runtime,ns,cleanup=self.fixture();foreign_r,foreign_w=os.pipe()
                try:
                    writer,port=ns['_open_duplex_port'](runtime);original=writer.fd
                    model.dup_failure=kind=='dup';model.mutation=mutation
                    if kind=='close':model.close_failure=original
                    with self.assertRaises(OSError if kind in ('dup','close') else RuntimeError):ns['_duplex_fd'](writer)
                    self.assertIsNone(writer.fd);self.assertEqual(model.references,set())
                    self.assertEqual(model.created,{model.peer});os.fstat(foreign_r);os.fstat(foreign_w)
                finally:cleanup();os.close(foreign_r);os.close(foreign_w)

    def test_cleanup_error_cannot_replace_primary_duplicate_identity_failure(self):
        model,proxy,runtime,ns,cleanup=self.fixture()
        try:
            writer,port=ns['_open_duplex_port'](runtime);model.mutation={'st_uid':1}
            original_dup=proxy.dup
            def dup(fd):
                acquired=original_dup(fd);model.close_failure=acquired;return acquired
            proxy.dup=dup
            with self.assertRaisesRegex(RuntimeError,'^Duplex virtio identity differs$'):ns['_duplex_fd'](writer)
            self.assertIsNone(writer.fd);self.assertEqual(model.references,set());self.assertEqual(model.created,{model.peer})
        finally:cleanup()


if __name__=='__main__':unittest.main()
