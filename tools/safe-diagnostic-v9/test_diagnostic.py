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
import pwd
import select
import stat
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


LEGACY_V7_WRAPPER_TAIL = "status=$?\n# Secondary export/screening failures preserve an existing primary failure.\n# A zero primary still fails if either strict reporting stage rejects bytes.\npython3 - \"$out\" \"$execution\" <<'PY'\nimport importlib.util,shutil,stat,sys\nfrom pathlib import Path\nout=Path(sys.argv[1]);execution=Path(sys.argv[2]);evidence=out/'evidence';evidence.mkdir()\nspec=importlib.util.spec_from_file_location('safe_status_export',execution/'tools/safe-diagnostic/common.py')\nc=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)\n# Begin reviewed guest fixed-status projection; no raw errors or unvalidated JSON.\nguest_context=None\nguest_status_path=out/'guest-entry-status.json'\nc.require(not guest_status_path.exists() and not guest_status_path.is_symlink(), 'Guest fixed export must be new')\nif (out/'serial.log').exists():\n    serial=c.regular(out/'serial.log').read_bytes()\n    if c.GUEST_STATUS_PREFIX.encode() in serial:\n        guest_context=c.context(c.strict(c.regular(out/'data/context.json').read_bytes()))\n        guest_status=c.project_guest_status(serial,guest_context)\n        if guest_status is not None:\n            c.exclusive_json(guest_status_path,guest_status)\n# End reviewed guest fixed-status projection.\ntotal=0\nfor path in out.iterdir():\n    if path.name in ('build-provenance.json','fixture-provenance.json','host-report.json','guest-report.json','serial.log','qemu.log','host-entry-status.json','guest-entry-status.json') or (path.name.startswith('stage-') and path.suffix=='.json') or path.suffix=='.png' or '-wayland' in path.name:\n        s=path.lstat();assert stat.S_ISREG(s.st_mode) and s.st_size<=32*1024**2\n        if path.name=='guest-entry-status.json':\n            c.validate_guest_status(c.strict(c.regular(path).read_bytes()),guest_context)\n        if path.name=='host-entry-status.json' or path.name.startswith('stage-'):\n            value=c.validate_fixed_status(c.strict(c.regular(path).read_bytes()))\n            assert value['stage'] in c.HOST_PHASES if path.name=='host-entry-status.json' else path.name=='stage-'+value['stage']+'.json' and value['stage'] in c.STAGES\n        total+=s.st_size;assert total<=128*1024**2\n        shutil.copyfile(path,evidence/path.name)\nassert len(list(evidence.iterdir()))<=40\nPY\nexport_status=$?\nscreen_status=0\nif [[ $export_status == 0 ]]; then\n  python3 -B \"$execution/tools/native-functional/screen-evidence.py\" --preserve-original \\\n    --source \"$out/evidence\" --out \"$out/screened\"\n  screen_status=$?\nfi\nif [[ $status == 0 ]]; then\n  [[ $export_status == 0 ]] || status=$export_status\n  [[ $screen_status == 0 ]] || status=$screen_status\nfi\nexit \"$status\"\n"


def without_rerender_wrapper(wrapper):
    """Attest the exact old wrapper for labelled historical failure controls."""
    wrapper=wrapper.replace('tools/safe-diagnostic-v9/','tools/safe-diagnostic/')
    wrapper=wrapper[:wrapper.index('status=$?\n')]+LEGACY_V7_WRAPPER_TAIL
    wrapper=wrapper.replace('15m python3 -B','10m python3 -B',1)
    if hashlib.sha256(wrapper.encode()).hexdigest()!='3cd69c2e8d86da9f8aac12c24fef24c0ca21d9614a882387a52080d6e7c282b2':
        raise AssertionError('Historical rollback differs from the complete original v7 wrapper')
    return wrapper


def actual_failed_v2_wrapper(wrapper):
    """Undo only this ownership correction and attest all original v2 bytes."""
    wrapper=without_guest_projection(without_rerender_wrapper(wrapper))
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
            (execution/'tools/safe-diagnostic-v9/execution-manifest.json').write_text(json.dumps(manifest,sort_keys=True)+'\n')
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
        for target,paths in ((cls.repo,['tools/safe-diagnostic-v9','.github/workflows/safe-rerender-v9-20261010.yml',c.CI_PATH,c.MARKER,*c.EXECUTION_FILES]),
                             (cls.source,list(c.SOURCE_FILES))):
            subprocess.run(['git','clone','--quiet','--shared','--no-checkout',str(ROOT),str(target)],check=True,timeout=30)
            git(target,'sparse-checkout','set','--no-cone',*paths)
            git(target,'checkout','--detach',c.PREPARATION_BASE if target==cls.repo else c.IMAGE['source_sha'])
            git(target,'config','user.name','Safe source controls');git(target,'config','user.email','safe-source-controls@invalid.local')
        for path in HERE.iterdir():
            if path.is_file() and path.suffix in ('.py','.c','.sh','.json','.md'):
                destination=cls.repo/'tools/safe-diagnostic-v9'/path.name;destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_bytes(path.read_bytes());destination.chmod(path.stat().st_mode & 0o777)
        workflow=cls.repo/'.github/workflows/safe-rerender-v9-20261010.yml';workflow.parent.mkdir(parents=True,exist_ok=True)
        workflow.write_bytes((ROOT/workflow.relative_to(cls.repo)).read_bytes())
        (cls.repo/c.CI_PATH).write_bytes(subprocess.check_output(['git','-C',str(ROOT),'show',c.PREPARATION_BASE+':'+c.CI_PATH]).replace(c.CI_ANCHOR,c.CI_ANCHOR+c.CI_ADDITION,1))
        private_manifest=cls.repo/'tools/safe-diagnostic-v9/execution-manifest.json'
        private_value=c.strict(private_manifest.read_bytes());private_value['ready']=True
        # This labelled operational fixture uses its actual prepared tree,
        # whose inherited helper identities can differ from the disabled source.
        for path in private_value['execution_files']:
            private_value['execution_files'][path]=c.sha(cls.repo/path)
        private_manifest.write_text(json.dumps(private_value,sort_keys=True,indent=2)+'\n')
        git(cls.repo,'add','tools/safe-diagnostic-v9','.github/workflows/safe-rerender-v9-20261010.yml',c.CI_PATH)
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
        path=self.repo/'tools/safe-diagnostic-v9/screencopy.c';original=path.read_bytes()
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
        original.rename(target/'tools/safe-diagnostic-v9/moved-product.py')
        git(target,'add','-A')
        # This synthetic forged preparation still has the exact allowed sole
        # base; the no-renames path gate must detect its product deletion.
        git(target,'reset','--soft',c.PREPARATION_BASE)
        git(target,'commit','--quiet','-m','Private forbidden product rename control')
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
                    self.assertFalse((root/'screened/context/serial.log').exists())
                    self.assertFalse((root/'screened/context/stage-bootstrap-cd.json').exists())
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
                    self.assertNotEqual(run.returncode,0);self.assertEqual(list((root/'evidence/context').iterdir()),[])
                else:
                    self.assertEqual(run.returncode,0,run.stderr)
                    self.assertEqual([p.name for p in (root/'evidence/context').iterdir()],['stage-bootstrap-cd.json'])
                    subprocess.run([sys.executable,'-B',str(ROOT/'tools/native-functional/screen-evidence.py'),'--preserve-original','--source',str(root/'evidence/context'),'--out',str(root/'screened')],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
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
            tree=ast.parse((HERE/'guest.py').read_bytes());capture=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='capture_arm')
            guarded=next(n for n in capture.body if isinstance(n,ast.Try))
            # Retain the exact source-derived try/except/finally and its return
            # inside a harmless private function rather than top-level code.
            function=ast.FunctionDef(name='synthetic_guarded_capture',args=ast.arguments(
                posonlyargs=[],args=[],vararg=None,kwonlyargs=[],kw_defaults=[],kwarg=None,defaults=[]),
                body=[ast.Global(names=['_guest_primary','foot','foot_fd']),guarded],decorator_list=[])
            code=compile(ast.fix_missing_locations(ast.Module(body=[function],type_ignores=[])),str(HERE/'guest.py'),'exec')
            exec(code,g)
            def fail_send(*args):raise ValueError('PRIVATE_PRIMARY_TRANSCRIPT')
            def actual_try():
                g['_guest_context']=ctx;g.update(channel=types.SimpleNamespace(send=fail_send),ctx=ctx,name='SYNTHETIC_OUTPUT',foot=None,foot_fd=9)
                g['synthetic_guarded_capture']()
            g['main']=actual_try;stream=io.StringIO()
            with patch.object(signal,'pidfd_send_signal',side_effect=PermissionError('PRIVATE_CLEANUP_TRANSCRIPT')),patch.object(sys,'stdout',stream),patch.object(time,'sleep'):
                self.assertEqual(g['execute'](),1)
            value=c.project_guest_status(stream.getvalue().encode(),ctx)
            self.assertEqual((value['phase'],value['exception_class']),('capture','ValueError'))
            self.assertNotIn('PRIVATE_',stream.getvalue())
            class Closed:
                def write(self,value):raise BrokenPipeError('PRIVATE_CLOSED_STDOUT')
                def flush(self):raise BrokenPipeError('PRIVATE_CLOSED_STDOUT')
            with patch.object(signal,'pidfd_send_signal',side_effect=PermissionError('PRIVATE_CLEANUP_TRANSCRIPT')),patch.object(sys,'stdout',Closed()),patch.object(time,'sleep'):
                self.assertEqual(g['execute'](),1)
            self.assertEqual(g['_guest_primary'],('capture','ValueError'))

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
                    self.assertEqual((out/'evidence/context/guest-entry-status.json').read_bytes(),(out/'guest-entry-status.json').read_bytes())
                elif kind=='foreign-status':self.assertEqual((out/'guest-entry-status.json').read_bytes(),b'FOREIGN')
                else:self.assertFalse((out/'guest-entry-status.json').exists())


class HandoffDiagnostics(unittest.TestCase):
    """Exact guest functions with labelled synthetic labels/commands; no OS VM."""
    def test_closed_primary_ids_are_exact_source_guard_literals(self):
        tree=ast.parse((HERE/'guest.py').read_bytes());literals=set()
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and ((isinstance(node.func,ast.Attribute)
                    and isinstance(node.func.value,ast.Name) and node.func.value.id=='c'
                    and node.func.attr=='require') or (isinstance(node.func,ast.Name)
                    and node.func.id=='RuntimeError')):
                if node.args and isinstance(node.args[-1],ast.Constant) and type(node.args[-1].value) is str:
                    literals.add(node.args[-1].value)
        self.assertFalse(set(c.HANDOFF_GUARDS)-literals)
        self.assertEqual(len(c.HANDOFF_GUARDS),len(c.HANDOFF_PRIMARY_IDS))
        for message,identifier in c.HANDOFF_GUARDS.items():
            self.assertRegex(identifier,'^[a-z][a-z0-9-]{1,63}$')
            for phase in ('session-handoff',*c.HANDOFF_PHASES):
                self.assertEqual(c.handoff_primary_id(RuntimeError(message),phase),identifier)
            for error in (ValueError(message),RuntimeError(message+' PRIVATE_TRANSCRIPT'),
                          RuntimeError(message,1),RuntimeError(['PRIVATE']),
                          type('PrivateSubclass',(RuntimeError,),{})(message)):
                self.assertIsNone(c.handoff_primary_id(error,'session-handoff'))
            self.assertIsNone(c.handoff_primary_id(RuntimeError(message),'capture'))

    def test_closed_handoff_status_ids_binding_and_privacy_cannot_be_extended(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx=GuestPhase().fixture(Path(tmp))
            for phase in c.HANDOFF_PHASES:
                valid=c.guest_status(phase,'exception','RuntimeError',ctx,'reference-policy-label')
                raw=(c.GUEST_STATUS_PREFIX+json.dumps(valid)+'\n').encode()
                self.assertEqual(c.project_guest_status(raw,ctx),valid)
            for phase,klass,primary in [('capture','RuntimeError','reference-policy-label'),
                    ('handoff-reference-label','OSError','reference-policy-label'),
                    ('handoff-reference-label','RuntimeError','PRIVATE_ERROR'),
                    ('handoff-reference-label','RuntimeError',[]),
                    ('handoff-reference-label','RuntimeError',True)]:
                with self.subTest(phase=phase,klass=klass,primary=primary),self.assertRaises(RuntimeError):
                    c.guest_status(phase,'exception',klass,ctx,primary)
            valid=c.guest_status('handoff-reference-label','exception','RuntimeError',ctx,'reference-policy-label')
            for field,value in [('binding_id','c'*32),('primary_id','PRIVATE_TRANSCRIPT'),
                    ('phase','PRIVATE_PHASE'),('exception_class','PRIVATE_CLASS'),('release_acceptance',True)]:
                candidate=dict(valid,**{field:value})
                with self.assertRaises(RuntimeError):c.project_guest_status((c.GUEST_STATUS_PREFIX+json.dumps(candidate)).encode(),ctx)
            with self.assertRaises(RuntimeError):c.validate_guest_status(dict(valid,message='PRIVATE'),ctx)
            raw=(c.GUEST_STATUS_PREFIX+json.dumps(valid)+'\n').encode()
            with self.assertRaises(RuntimeError):c.project_guest_status(raw+raw,ctx)
            spec=importlib.util.spec_from_file_location('handoff_original_privacy',ROOT/'tools/native-functional/screen-evidence.py')
            screen=importlib.util.module_from_spec(spec);spec.loader.exec_module(screen)
            screen.external_text(raw)
            with self.assertRaises(Exception):screen.external_text(b'Transcript: PRIVATE_TRANSCRIPT\n'+raw)

    def exercise_label_failure(self,kind,cleanup=False):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);ctx=GuestPhase().fixture(root);g=GuestPhase().module(root)
            record=dict(bytes=3,sha256='a'*64,mode=0o755,uid=0)
            g['protected']=lambda path,executable=False:record
            calls=[]
            def run(argv,**kwargs):
                calls.append(argv)
                if argv[0]=='matchpathcon':raw='system_u:object_r:sddm_exec_t:s0'
                elif argv[0]=='stat':raw='system_u:object_r:bin_t:s0' if kind=='reference-mismatch' else 'system_u:object_r:sddm_exec_t:s0'
                elif argv[0]=='restorecon':return types.SimpleNamespace(returncode=1,stdout=b'',stderr=b'PRIVATE_COMMAND_ERROR')
                else:raise AssertionError('Unexpected synthetic label command')
                return types.SimpleNamespace(returncode=0,stdout=(raw+'\n').encode(),stderr=b'')
            # Retain the actual arm try/except/finally; replace only its VM body
            # with one actual label function and its synthetic command adapter.
            main=next(n for n in ast.parse((HERE/'guest.py').read_bytes()).body if isinstance(n,ast.FunctionDef) and n.name=='main')
            guarded=copy.deepcopy(next(n for n in ast.walk(main) if isinstance(n,ast.Try) and any(
                isinstance(s,ast.ExceptHandler) and any(isinstance(a,ast.Assign) and any(
                isinstance(t,ast.Name) and t.id=='primary' for t in a.targets) for a in s.body) for s in n.handlers)))
            guarded.body=[ast.Expr(value=ast.Call(func=ast.Name(id='actual_label',ctx=ast.Load()),args=[],keywords=[]))]
            fun=ast.FunctionDef(name='actual_arm_handler',args=ast.arguments(posonlyargs=[],args=[],vararg=None,
                kwonlyargs=[],kw_defaults=[],kwarg=None,defaults=[]),body=[ast.Global(names=['_guest_primary','primary']),guarded],decorator_list=[])
            exec(compile(ast.fix_missing_locations(ast.Module(body=[fun],type_ignores=[])),str(HERE/'guest.py'),'exec'),g)
            def actual_label():return g['label_owned'](root/'wrapper',root/'config',root/'reference',record,query=g['bounded'])
            def close():
                if cleanup:raise PermissionError('PRIVATE_CLEANUP_ERROR')
            def actual_main():
                g['_guest_context']=ctx;g['_stage']('session-handoff');g.update(actual_label=actual_label,
                    primary=None,old_fd=None,override=types.SimpleNamespace(close=close))
                g['actual_arm_handler']()
            g['main']=actual_main;stream=io.StringIO()
            with patch.object(g['subprocess'],'run',side_effect=run),patch.object(sys,'stdout',stream):
                self.assertEqual(g['execute'](),1)
            self.assertNotIn('PRIVATE',stream.getvalue())
            status=c.project_guest_status(stream.getvalue().encode(),ctx)
            phase='handoff-reference-label' if kind=='reference-mismatch' else 'handoff-policy-restore'
            identifier='reference-policy-label' if kind=='reference-mismatch' else 'command-failed-or-bound'
            self.assertEqual((status['phase'],status['exception_class'],status['primary_id']),(phase,'RuntimeError',identifier))
            self.assertEqual(g['_guest_primary'],(phase,'RuntimeError'))
            self.assertEqual(g['_guest_primary_detail']['id'],identifier)
            self.assertEqual([v[0] for v in calls],['matchpathcon','stat']+([] if kind=='reference-mismatch' else ['restorecon']))

    def test_actual_reference_guard_identified_before_restore_or_restart(self):
        self.exercise_label_failure('reference-mismatch')

    def test_actual_restore_command_failure_is_closed_without_private_output(self):
        self.exercise_label_failure('restore-failure')

    def test_actual_arm_primary_phase_id_survives_foreign_cleanup_error(self):
        self.exercise_label_failure('reference-mismatch',cleanup=True)
        self.exercise_label_failure('restore-failure',cleanup=True)

    def test_handoff_annotations_do_not_reattribute_original_or_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            g=GuestPhase().module(Path(tmp))
            for phase in ('entry','session-contract','capture','export'):
                g['_stage'](phase);g['_handoff_stage']('handoff-reference-label')
                self.assertEqual(g['_guest_phase'],phase)
            g['_stage']('session-handoff')
            for phase in c.HANDOFF_PHASES:
                g['_handoff_stage'](phase);self.assertEqual(g['_guest_phase'],phase)
            with self.assertRaises(RuntimeError):g['_handoff_stage']('PRIVATE_PHASE')


class RerenderExperiment(unittest.TestCase):
    """Owned synthetic files/processes only; no SDDM, guest, renderer or VM."""
    def module(self,root):
        return GuestPhase().module(root)

    @staticmethod
    def synthetic_labels(*args,**kwargs):
        # No real SELinux operation in these labelled synthetic file controls.
        value='system_u:object_r:usr_t:s0'
        return dict(script=dict(policy_expected=value,observed=value,reference=value,action='ordinary-policy-restore'),
                    configuration=dict(policy_expected=value,observed=value))

    def synthetic_handoff(self,arm):
        record=dict(bytes=100,sha256='a'*64,mode=0o755,uid=0)
        return dict(arm=arm,wrapper=record,configuration={**record,'mode':0o644},original_script=record,
            security_labels=self.synthetic_labels(),selector='unset')

    @staticmethod
    def synthetic_session():
        return dict(id='c9',uid=1000,type='wayland',vt=2,active=True,prefix_bound=True)

    @staticmethod
    def synthetic_display():
        return dict(schema='arctic-safe-display-binding-v1',pid=101,start_ticks=201,
                    kernel_release='synthetic-0',devices=[],journal_status='unavailable',
                    source_log_markers={key:False for key in c.ALLOCATOR_MARKERS})

    def fixture(self,root):
        for name in ('run','etc/sddm.conf.d','usr/lib/sddm/sddm.conf.d',
                     'usr/share/sddm/scripts','usr/share/wayland-sessions'):
            (root/name).mkdir(parents=True,exist_ok=True)
        (root/'etc/sddm.conf.d/90-live.conf').write_text(
            '[General]\nDisplayServer=wayland\n[Autologin]\nUser=liveuser\nSession=mango.desktop\nRelogin=false\n')
        script=root/'usr/share/sddm/scripts/wayland-session'
        script.write_text('#!/bin/sh\nprintf "profile=%s\\n" "${WLR_SCENE_DISABLE_VISIBILITY-unset}"\nprintf "arg=%s\\n" "$@"\n')
        script.chmod(0o755)
        (root/'usr/share/wayland-sessions/mango.desktop').write_text('[Desktop Entry]\nExec=mango\n')
        def query(argv):
            if argv==['rpm','-ql','sddm']:return '/usr/share/sddm/scripts/wayland-session'
            if argv==['sddm','--example-config']:return '[Wayland]\nSessionCommand=/usr/share/sddm/scripts/wayland-session\n'
            if argv==['rpm','-qf',str(script)]:return 'sddm-0.21.0-13.fc44.x86_64'
            if argv[0] in ('matchpathcon','stat'):return 'system_u:object_r:usr_t:s0'
            raise AssertionError('Unexpected synthetic package query')
        return script,query

    def test_actual_precedence_and_compiled_script_contract_reject_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);_,query=self.fixture(root);g=self.module(root)
            contract=g['session_contract'](root,query)
            self.assertEqual(contract['session_argv'],['mango'])
            self.assertEqual(contract['script'],'/usr/share/sddm/scripts/wayland-session')
            final=root/'etc/sddm.conf'
            for raw in ('[Wayland]\nSessionCommand=/foreign/script\n',
                        '[General]\nDisplayServer=x11\n','[Autologin]\nUser=foreign\n'):
                with self.subTest(raw=raw):
                    final.write_text(raw)
                    with self.assertRaises(RuntimeError):g['session_contract'](root,query)
            final.unlink()
            with self.assertRaises(RuntimeError):g['session_contract'](root,lambda argv:
                '[Wayland]\nSessionCommand=/foreign/script\n' if argv[0]=='sddm' else query(argv))
            desktop=root/'usr/share/wayland-sessions/mango.desktop'
            desktop.write_text('[Desktop Entry]\nExec=mango %U\n')
            with self.assertRaises(RuntimeError):g['session_contract'](root,query)

    def fedora_fixture(self,root):
        """Synthetic commands/files use the matching Fedora SRPM's compiled path."""
        sample,_=self.fixture(root)
        (root/'etc/sddm').mkdir()
        script=root/'etc/sddm/wayland-session'
        script.write_bytes(sample.read_bytes());script.chmod(0o755)
        def query(argv):
            if argv==['rpm','-ql','sddm']:
                return '/etc/sddm/wayland-session\n/usr/share/sddm/scripts/wayland-session'
            if argv==['sddm','--example-config']:
                return '[Wayland]\nSessionCommand=/etc/sddm/wayland-session\n'
            if argv==['rpm','-qf',str(script)]:return 'sddm-0.21.0-13.fc44.x86_64'
            if argv[0] in ('matchpathcon','stat'):return 'system_u:object_r:usr_t:s0'
            raise AssertionError('Unexpected synthetic Fedora package query')
        return script,query

    def test_actual_fedora_compiled_path_acceptance_and_prior_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);_,query=self.fedora_fixture(root);g=self.module(root)
            value=g['session_contract'](root,query)
            self.assertEqual(value['script'],'/etc/sddm/wayland-session')
            self.assertEqual(value['script_owner'],'sddm-0.21.0-13.fc44.x86_64')
            self.assertEqual(value['session_argv'],['mango'])
            # Undo only the canonical-path addition and bind every original byte
            # to the actual failed experiment's immutable guest payload.
            raw=(HERE/'guest.py').read_bytes()
            self.assertEqual(raw.count(b",'/etc/sddm/wayland-session'"),1)
            prior=raw.replace(b",'/etc/sddm/wayland-session'",b'',1)
            self.assertEqual(hashlib.sha256(prior).hexdigest(),
                             '770cde77b62f5e20aa3608c753361360ff41946df693ed31ab0b96b4e743d4bb')
            function=next(n for n in ast.parse(prior).body
                          if isinstance(n,ast.FunctionDef) and n.name=='session_contract')
            historical=dict(g)
            exec(compile(ast.Module(body=[function],type_ignores=[]),str(HERE/'guest.py'),'exec'),historical)
            with self.assertRaisesRegex(RuntimeError,'Actual compiled packaged Wayland session script differs'):
                historical['session_contract'](root,query)

    def test_actual_fedora_compiled_path_preserves_package_protection_and_precedence(self):
        cases=('unlisted','foreign-compiled','wrong-owner','writable','nonexecutable',
               'symlink','different-effective','higher-priority-master')
        for case in cases:
            with self.subTest(case=case),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);script,query=self.fedora_fixture(root);g=self.module(root)
                reference=root/'run/foreign-preserved';reference.write_bytes(b'FOREIGN_MUST_SURVIVE')
                def hostile(argv):
                    if case=='unlisted' and argv==['rpm','-ql','sddm']:
                        return '/usr/share/sddm/scripts/wayland-session'
                    if case=='foreign-compiled' and argv==['sddm','--example-config']:
                        return '[Wayland]\nSessionCommand=/etc/sddm/foreign-session\n'
                    if case=='wrong-owner' and argv==['rpm','-qf',str(script)]:
                        return 'sddm-0.21.0-14.fc44.x86_64'
                    return query(argv)
                if case=='writable':script.chmod(0o777)
                if case=='nonexecutable':script.chmod(0o644)
                if case=='symlink':script.unlink();script.symlink_to(reference)
                if case=='different-effective':
                    (root/'etc/sddm.conf.d/99-conflict.conf').write_text('[Wayland]\nSessionCommand=/foreign/script\n')
                if case=='higher-priority-master':
                    (root/'etc/sddm.conf').write_text('[Wayland]\nSessionCommand=/etc/sddm/wayland-session\n')
                with self.assertRaises(RuntimeError):g['session_contract'](root,hostile)
                self.assertEqual(reference.read_bytes(),b'FOREIGN_MUST_SURVIVE')

    def test_real_wrapper_preserves_original_profile_argv_and_selector(self):
        for arm in c.ARMS:
            with self.subTest(arm=arm),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);script,query=self.fixture(root);g=self.module(root)
                contract=g['session_contract'](root,query)
                # Labelled test-only original script path; production contract only
                # accepts the observed packaged fixed path above.
                contract['script']=str(script)
                owned=g['OwnedSessionOverride'](root,'b'*32,arm,contract,self.synthetic_labels)
                try:
                    record=owned.install()
                    result=subprocess.run([str(owned.wrapper),'literal space','$(never-run)','end'],
                        env={**os.environ,'WLR_SCENE_DISABLE_VISIBILITY':'POISON_INHERITED'},capture_output=True,text=True,timeout=5)
                    self.assertEqual(result.returncode,0)
                    expected='unset' if arm=='default-restart' else '1'
                    self.assertEqual(result.stdout.splitlines(),['profile=unset',
                        'arg=literal space','arg=$(never-run)','arg=end','arg=-d'])
                    self.assertEqual(record['selector'],'unset')
                    self.assertEqual(stat.S_IMODE(owned.wrapper.stat().st_mode),0o755)
                    self.assertEqual(stat.S_IMODE(owned.configuration.stat().st_mode),0o644)
                finally:owned.close()
                self.assertFalse(owned.wrapper.exists());self.assertFalse(owned.configuration.exists())

    def test_acquired_override_cleanup_preserves_foreign_replacement_and_failed_acquisition(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);_,query=self.fixture(root);g=self.module(root)
            contract=g['session_contract'](root,query)
            owned=g['OwnedSessionOverride'](root,'b'*32,c.ARMS[0],contract,self.synthetic_labels);owned.install()
            acquired=owned.wrapper.with_name('retained-acquired.sh');owned.wrapper.rename(acquired)
            owned.wrapper.write_bytes(b'FOREIGN_REPLACEMENT_MUST_SURVIVE')
            with self.assertRaises(RuntimeError):owned.close()
            self.assertEqual(owned.wrapper.read_bytes(),b'FOREIGN_REPLACEMENT_MUST_SURVIVE')
            self.assertTrue(acquired.exists());self.assertFalse(owned.configuration.exists())
            owned=g['OwnedSessionOverride'](root,'c'*32,c.ARMS[0],contract,self.synthetic_labels)
            owned.configuration.write_bytes(b'FOREIGN_PREEXISTING_CONFIG')
            with self.assertRaises(RuntimeError):owned.install()
            owned.close()
            self.assertEqual(owned.configuration.read_bytes(),b'FOREIGN_PREEXISTING_CONFIG')
            self.assertFalse(owned.wrapper.exists())

    def test_symlink_high_priority_and_incomplete_write_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);_,query=self.fixture(root);g=self.module(root);contract=g['session_contract'](root,query)
            late=root/'etc/sddm.conf.d/zzzzz-foreign.conf';late.write_text('[Wayland]\nSessionCommand=/foreign\n')
            owned=g['OwnedSessionOverride'](root,'b'*32,c.ARMS[0],contract,self.synthetic_labels)
            with self.assertRaises(RuntimeError):owned.install()
            self.assertFalse(owned.wrapper.exists());owned.close();late.unlink()
            target=root/'run/foreign';target.write_bytes(b'FOREIGN_TARGET')
            owned=g['OwnedSessionOverride'](root,'c'*32,c.ARMS[0],contract,self.synthetic_labels);owned.wrapper.symlink_to(target)
            with self.assertRaises(FileExistsError):owned.install()
            owned.close();self.assertEqual(target.read_bytes(),b'FOREIGN_TARGET')
            owned=g['OwnedSessionOverride'](root,'d'*32,c.ARMS[0],contract,self.synthetic_labels)
            with patch.object(g['os'],'write',return_value=0),self.assertRaises(RuntimeError):owned.install()
            owned.close();self.assertFalse(owned.wrapper.exists())

    def test_label_hook_uses_only_owned_paths_and_original_full_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);script,_=self.fixture(root);g=self.module(root)
            wrapper=root/'usr/share/sddm/scripts/owned-wrapper.sh';wrapper.write_bytes(b'OWNED_SYNTHETIC_WRAPPER');wrapper.chmod(0o755)
            config=root/'etc/sddm.conf.d/owned.conf';config.write_bytes(b'OWNED_SYNTHETIC_CONFIG')
            original='system_u:object_r:sddm_exec_t:s0';ordinary='system_u:object_r:usr_t:s0';etc='system_u:object_r:etc_t:s0'
            labels={str(script):original,str(wrapper):ordinary,str(config):etc};commands=[];verifications=[]
            def query(argv):
                commands.append(argv)
                if argv[0]=='matchpathcon':return original if argv[-1]==str(script) else etc if argv[-1]==str(config) else ordinary
                if argv[0]=='stat':return labels[argv[-1]]
                if argv==['restorecon','-F','--',str(wrapper),str(config)]:return ''
                if argv==['chcon','--reference='+str(script),'--',str(wrapper)]:labels[str(wrapper)]=original;return ''
                raise AssertionError('Unexpected synthetic security-label operation')
            record=g['protected'](script,True)
            value=g['label_owned'](wrapper,config,script,record,query,lambda:verifications.append('owned-identity-checked'))
            self.assertEqual(value['script']['action'],'owned-trusted-script-reference')
            self.assertEqual(value['script']['policy_expected'],ordinary)
            self.assertEqual(value['script']['observed'],original)
            self.assertEqual(value['configuration']['observed'],etc)
            self.assertEqual(len(verifications),4)
            self.assertEqual([v for v in commands if v[0] in ('restorecon','chcon')],
                [['restorecon','-F','--',str(wrapper),str(config)],['chcon','--reference='+str(script),'--',str(wrapper)]])
            self.assertEqual(g['protected'](script,True),record)
            commands.clear();labels[str(script)]='system_u:object_r:foreign_t:s0'
            with self.assertRaises(RuntimeError):g['label_owned'](wrapper,config,script,record,query)
            self.assertFalse(any(v[0] in ('restorecon','chcon') for v in commands))
            with self.assertRaises(RuntimeError):g['security_label'](script,lambda argv:'PRIVATE_TRANSCRIPT_SENTINEL')

    def test_host_handoff_rejects_foreign_mode_uid_or_label(self):
        previous=dict(pid=100,start_ticks=200,executable='/usr/bin/mango',sha256='a'*64)
        env=dict(WLR_RENDERER_FORCE_SOFTWARE='1',LIBGL_ALWAYS_SOFTWARE='1');arm=c.ARMS[0]
        hello=dict(output='Unknown-1',original=dict(renderer_environment=env))
        base=dict(arm=arm,guest_ns=300,mango={**previous,'pid':101,'start_ticks':201},
            renderer_environment=env,output='Unknown-1',session_handoff=self.synthetic_handoff(arm),session=self.synthetic_session(),display_binding=self.synthetic_display(),renderer_debug=LegacyRendererDiscovery.debug_fixture(101,201),readonly_drm=dict(schema='arctic-safe-readonly-drm-v1',pid=101,start_ticks=201,status='unknown',devices=[]))
        changes=[('wrapper','uid',1000),('wrapper','mode',0o777),('wrapper','bytes',True),
                 ('configuration','mode',0o600),('original_script','sha256','PRIVATE_HASH')]
        for record,key,value in changes:
            bad=copy.deepcopy(base);bad['session_handoff'][record][key]=value
            with self.subTest(record=record,key=key),self.assertRaises(RuntimeError):host.validate_arm_ready(bad,arm,hello,previous)
        for record,key,value in [('script','observed','system_u:object_r:foreign_t:s0'),
            ('script','action','arbitrary-permission-bypass'),('configuration','observed','system_u:object_r:foreign_t:s0'),
            ('script','reference','PRIVATE_TRANSCRIPT_SENTINEL')]:
            bad=copy.deepcopy(base);bad['session_handoff']['security_labels'][record][key]=value
            with self.subTest(record=record,key=key),self.assertRaises(RuntimeError):host.validate_arm_ready(bad,arm,hello,previous)

    def test_host_arm_identity_selector_and_order_are_strict(self):
        previous=dict(pid=100,start_ticks=200,executable='/usr/bin/mango',sha256='a'*64)
        env=dict(WLR_RENDERER_FORCE_SOFTWARE='1',LIBGL_ALWAYS_SOFTWARE='1')
        hello=dict(output='Unknown-1',original=dict(renderer_environment=env))
        for arm in c.ARMS:
            expected=dict(env)
            ready=dict(arm=arm,guest_ns=300,mango={**previous,'pid':101,'start_ticks':201},
                       renderer_environment=expected,output='Unknown-1',session_handoff=self.synthetic_handoff(arm),session=self.synthetic_session(),display_binding=self.synthetic_display(),renderer_debug=LegacyRendererDiscovery.debug_fixture(101,201),readonly_drm=dict(schema='arctic-safe-readonly-drm-v1',pid=101,start_ticks=201,status='unknown',devices=[]))
            self.assertIs(host.validate_arm_ready(ready,arm,hello,previous),ready)
            for key,value in (('arm','foreign'),('guest_ns',True),('output','foreign'),
                              ('renderer_environment',{**env,'WLR_SCENE_DISABLE_VISIBILITY':'1'})):
                bad=copy.deepcopy(ready);bad[key]=value
                with self.subTest(arm=arm,key=key),self.assertRaises(RuntimeError):host.validate_arm_ready(bad,arm,hello,previous)
            for key,value in (('pid',True),('start_ticks',200),('executable','/foreign/mango'),('sha256','b'*64)):
                bad=copy.deepcopy(ready);bad['mango'][key]=value
                with self.subTest(arm=arm,key=key),self.assertRaises(RuntimeError):host.validate_arm_ready(bad,arm,hello,previous)
            bad=copy.deepcopy(ready);bad['PRIVATE_SENTINEL']='not allowed'
            with self.assertRaises(RuntimeError):host.validate_arm_ready(bad,arm,hello,previous)
            for key,value in [('uid',True),('uid',0),('id','PRIVATE SESSION'),('active',False),
                              ('prefix_bound',False),('type','tty'),('vt',True),('vt',0)]:
                bad=copy.deepcopy(ready);bad['session'][key]=value
                with self.subTest(session_field=key,value=value),self.assertRaises(RuntimeError):host.validate_arm_ready(bad,arm,hello,previous)

    def test_actual_host_arm_controller_orders_three_baselines_before_brackets(self):
        for mutation in ('none','capture-order','returned-arm'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp);(out/'data').mkdir();ctx=GuestPhase().fixture(out/'data')
                previous=dict(pid=100,start_ticks=200,executable='/usr/bin/mango',sha256='a'*64)
                env=dict(WLR_RENDERER_FORCE_SOFTWARE='1',LIBGL_ALWAYS_SOFTWARE='1')
                arm=c.ARMS[0];events=[];state=dict(arms=[])
                ready=dict(arm=arm,guest_ns=400,mango={**previous,'pid':101,'start_ticks':201},
                    renderer_environment=env,output='Unknown-1',session_handoff=self.synthetic_handoff(arm),session=self.synthetic_session(),display_binding=self.synthetic_display(),renderer_debug=LegacyRendererDiscovery.debug_fixture(101,201),readonly_drm=dict(schema='arctic-safe-readonly-drm-v1',pid=101,start_ticks=201,status='unknown',devices=[]))
                hello=dict(output='Unknown-1',original=dict(renderer_environment=env))
                clock=types.SimpleNamespace(ns=1_000_000)
                def sleep(seconds):clock.ns+=int(seconds*1_000_000_000)
                vm=types.SimpleNamespace(proc=types.SimpleNamespace(poll=lambda:None))
                def shot(name):
                    events.append(('shot',name));path=out/(name+'.png')
                    host.Image.new('RGB',(1920,1080),'#223344').save(path);clock.ns+=1_000_000
                    return path
                vm.shot=shot;requests={};done={};acks={};afters={};index=0
                def expect(kind,payload=None,timeout=30):
                    nonlocal index
                    events.append(('expect',kind))
                    if kind=='ARM-READY':return ready
                    label=c.PAIRS[index]
                    if kind=='CAPTURE-REQUEST':
                        value=dict(label='foreign' if mutation=='capture-order' else label,guest_ns=500+index*10)
                        requests[label]=value;return value
                    if kind=='CAPTURE-DONE':
                        value=dict(label=label,guest_ns=501+index*10);done[label]=value;index+=1;return value
                    raise AssertionError('Unexpected synthetic protocol expectation')
                def send(kind,value):
                    events.append(('send',kind))
                    if kind=='QMP-BEFORE':acks[value['label']]=value
                    if kind=='QMP-AFTER':afters[value['label']]=value
                channel=types.SimpleNamespace(expect=expect,send=send)
                def receive(channel,directory):
                    report=dict(context=ctx,arm='foreign' if mutation=='returned-arm' else arm,
                        mango=ready['mango'],renderer_environment=env,session=ready['session'],display_binding=ready['display_binding'],renderer_debug=ready['renderer_debug'],readonly_drm=ready['readonly_drm'],
                        samples=[dict(label=label,request_ns=requests[label]['guest_ns'],
                            capture_end_ns=done[label]['guest_ns'],qmp_before_ack=acks[label],qmp_after_ack=afters[label]) for label in c.PAIRS])
                    (directory/'guest-report.json').write_text(json.dumps(report));return dict(files=[])
                with patch.object(host.time,'monotonic_ns',side_effect=lambda:clock.ns),patch.object(host.time,'sleep',side_effect=sleep),\
                    patch.object(c,'receive_files',side_effect=receive),patch.object(host,'validate_readbacks',return_value=[]) as raw:
                    if mutation!='none':
                        with self.assertRaises(RuntimeError):host.observe_arm(vm,channel,out,ctx,hello,previous,arm,state)
                    else:
                        self.assertEqual(host.observe_arm(vm,channel,out,ctx,hello,previous,arm,state),ready['mango'])
                        self.assertEqual(events[:4],[('expect','ARM-READY'),
                            ('shot',arm+'/arm-baseline-035s'),('shot',arm+'/arm-baseline-080s'),('shot',arm+'/arm-baseline-125s')])
                        self.assertEqual([v['requested_seconds'] for v in state['arms'][0]['baseline']],[35,80,125])
                        self.assertEqual([v['label'] for v in state['arms'][0]['brackets']],list(c.PAIRS))
                        self.assertEqual(raw.call_count,1)
                        self.assertTrue((out/arm/'arm-host-report.json').is_file())

    def test_new_desktop_is_rediscovered_and_actual_selector_argv_libraries_are_checked(self):
        for arm in c.ARMS:
            with self.subTest(arm=arm),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);g=self.module(root);proc=root/'proc';mango=proc/'222';mango.mkdir(parents=True)
                library=root/'owned-synthetic-scene.so';library.write_bytes(b'OWNED_SYNTHETIC_LIBRARY')
                (mango/'comm').write_text('mango\n');(mango/'cmdline').write_bytes(b'mango\0-d\0')
                (mango/'maps').write_text('0000-0001 r-xp 0 0:0 0 /usr/lib64/libscenefx-test.so\n')
                class FixturePath(type(Path())):
                    def stat(self,*args,**kwargs):
                        value=super().stat(*args,**kwargs)
                        if str(self).startswith(str(proc)):
                            fields=list(value);fields[4]=1000;return os.stat_result(fields)
                        return value
                def path(value='.'):
                    value=str(value)
                    return FixturePath(proc if value=='/proc' else library if value=='/usr/lib64/libscenefx-test.so' else value)
                g['Path']=path
                identity=dict(pid=222,start_ticks=3,executable='/usr/bin/mango');previous={**identity,'pid':111,'start_ticks':2}
                env=dict(WLR_RENDERER_FORCE_SOFTWARE='1',LIBGL_ALWAYS_SOFTWARE='1')
                actual=dict(env)
                def write_env(value):(mango/'environ').write_bytes(('\0'.join(k+'='+v for k,v in {'XDG_SESSION_ID':'c9',**value}.items())+'\0').encode())
                write_env(actual);monitors=_fixture_monitors()
                original=dict(mango=dict(sha256='a'*64),actual_mango_argv=['mango'],renderer_environment=env,
                    monitors=monitors,libraries=[dict(path=str(library.resolve()),sha256=c.sha(library))])
                prefix=['runuser','-u','liveuser','--','env','XDG_SESSION_ID=c9','SYNTHETIC_REFRESH=1']
                native=types.SimpleNamespace(identity=lambda pid,uid:identity,
                    discover_desktop=unittest.mock.Mock(return_value=prefix))
                query_values=dict(Id='c9',User='1000',Type='wayland',VTNr='2',Active='yes')
                def bounded(argv,**kw):
                    if argv==[*native.discover_desktop.return_value,'mmsg','get','all-monitors']:return json.dumps(monitors)
                    if argv==['getenforce']:return 'Enforcing'
                    if len(argv)==6 and argv[:4]==['loginctl','show-session','c9','-p'] and argv[-1]=='--value':return query_values[argv[4]]
                    if argv==['chvt','2']:return ''
                    raise AssertionError('Unexpected synthetic desktop command')
                g['fresh_desktop_prefix']=lambda native,identity,env:native.discover_desktop()
                g['bounded']=bounded;original_sha=c.sha
                with patch.object(c,'sha',side_effect=lambda p:'a'*64 if str(p)=='/usr/bin/mango' else original_sha(p)):
                    result=g['arm_desktop'](native,arm,previous,original)
                    self.assertEqual(result[0],prefix);self.assertEqual(result[2],actual)
                    self.assertEqual(result[5],self.synthetic_session())
                    self.assertEqual(native.discover_desktop.call_count,1)
                    for key,value in [('Id','c10'),('User','0'),('Type','tty'),('Active','no')]:
                        saved=query_values[key];query_values[key]=value
                        with self.subTest(login_field=key,value=value),self.assertRaises(RuntimeError):g['arm_desktop'](native,arm,previous,original)
                        query_values[key]=saved
                    for foreign in (prefix[:-2],prefix[:-2]+['XDG_SESSION_ID=c10'],
                                    ['runuser','-u','foreign','--','env','XDG_SESSION_ID=c9']):
                        native.discover_desktop.return_value=foreign
                        with self.subTest(prefix=foreign),self.assertRaises(RuntimeError):g['arm_desktop'](native,arm,previous,original)
                    native.discover_desktop.return_value=prefix
                    write_env({**actual,'XDG_SESSION_ID':'c10'})
                    with self.assertRaises(RuntimeError):g['arm_desktop'](native,arm,previous,original)
                    write_env(actual)
                    with self.assertRaises(RuntimeError):g['arm_desktop'](native,arm,identity,original)
                    write_env({**actual,'WLR_SCENE_DISABLE_VISIBILITY':'POISON_SELECTOR'})
                    with self.assertRaises(RuntimeError):g['arm_desktop'](native,arm,previous,original)
                    write_env(actual);(mango/'cmdline').write_bytes(b'mango\0--foreign\0')
                    with self.assertRaises(RuntimeError):g['arm_desktop'](native,arm,previous,original)
                    (mango/'cmdline').write_bytes(b'mango\0-d\0');library.write_bytes(b'FOREIGN_SAME_SIZE_BYTES')
                    with self.assertRaises(RuntimeError):g['arm_desktop'](native,arm,previous,original)

    def export(self,out):
        wrapper=(HERE/'run.sh').read_text()
        # Execute the exact source-derived export handoff, not a mirror.
        start=wrapper.index('python3 - "$out" "$execution" <<\'PY\'\n')+len('python3 - "$out" "$execution" <<\'PY\'\n')
        end=wrapper.index('\nPY\nexport_status=$?',start)
        return subprocess.run([sys.executable,'-B','-',str(out),str(ROOT)],input=wrapper[start:end].encode(),
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)

    def export_fixture(self,out):
        (out/'data').mkdir();ctx=GuestPhase().fixture(out/'data')
        (out/'serial.log').write_bytes(b'OWNED_SYNTHETIC_STATUS\n')
        for arm in c.ARMS:
            (out/arm).mkdir();(out/arm/'terminal-initial-wayland.rgb').write_bytes(b'OWNED_SYNTHETIC_RGB_BYTES')
        return ctx

    def test_actual_compartment_export_preserves_source_nonce_and_original_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);ctx=self.export_fixture(out);result=self.export(out)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            self.assertEqual((out/'evidence/context/serial.log').read_bytes(),b'OWNED_SYNTHETIC_STATUS\n')
            for arm in c.ARMS:
                binding=json.loads((out/'evidence'/arm/'arm-binding.json').read_bytes())
                self.assertEqual(binding['context'],ctx);self.assertEqual(binding['arm'],arm)
                self.assertIs(binding['release_acceptance'],False)
                self.assertEqual((out/'evidence'/arm/'terminal-initial-wayland.rgb').read_bytes(),b'OWNED_SYNTHETIC_RGB_BYTES')
                self.assertLessEqual(len(list((out/'evidence'/arm).iterdir())),40)

    def test_actual_compartment_export_rejects_privacy_unknown_path_symlink_and_oversize(self):
        for mutation in ('privacy','unknown','symlink','oversize'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp);self.export_fixture(out);member=out/c.ARMS[0]/'terminal-initial-wayland.rgb'
                if mutation=='privacy':(out/'serial.log').write_bytes(b'Transcription: PRIVATE_TRANSCRIPT_SENTINEL\n')
                if mutation=='unknown':(out/c.ARMS[0]/'foreign.bin').write_bytes(b'FOREIGN')
                if mutation=='symlink':
                    member.unlink();member.symlink_to(out/'serial.log')
                if mutation=='oversize':
                    with member.open('wb') as stream:stream.truncate(c.MAX_FILE+1)
                result=self.export(out);self.assertNotEqual(result.returncode,0)
                self.assertFalse((out/'screened').exists())

    def test_actual_nested_arm_handler_retains_capture_primary_over_cleanup(self):
        """Source-derived inner capture and outer arm handlers, no guest/VM."""
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);ctx=GuestPhase().fixture(root);g=self.module(root)
            tree=ast.parse((HERE/'guest.py').read_bytes())
            capture=next(v for v in tree.body if isinstance(v,ast.FunctionDef) and v.name=='capture_arm')
            guarded=copy.deepcopy(next(v for v in capture.body if isinstance(v,ast.Try)))
            main=next(v for v in tree.body if isinstance(v,ast.FunctionDef) and v.name=='main')
            handler=copy.deepcopy(next(v for v in ast.walk(main) if isinstance(v,ast.ExceptHandler)
                and any(isinstance(s,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='primary' for t in s.targets) for s in v.body)))
            def function(name,body):return ast.FunctionDef(name=name,args=ast.arguments(
                posonlyargs=[],args=[],vararg=None,kwonlyargs=[],kw_defaults=[],kwarg=None,defaults=[]),
                body=[ast.Global(names=['_guest_primary','foot','foot_fd','primary']),*body],decorator_list=[])
            outer=ast.Try(body=[ast.Expr(value=ast.Call(func=ast.Name(id='private_capture',ctx=ast.Load()),args=[],keywords=[]))],
                handlers=[handler],orelse=[],finalbody=[])
            module=ast.Module(body=[function('private_capture',[guarded]),function('private_arm',[outer])],type_ignores=[])
            exec(compile(ast.fix_missing_locations(module),str(HERE/'guest.py'),'exec'),g)
            def fail_send(*args):raise ValueError('PRIVATE_PRIMARY_TRANSCRIPT')
            def actual_nested():
                g['_guest_context']=ctx;g.update(channel=types.SimpleNamespace(send=fail_send),
                    name='SYNTHETIC_OUTPUT',foot=None,foot_fd=9)
                g['private_arm']()
            g['main']=actual_nested;stream=io.StringIO()
            with patch.object(signal,'pidfd_send_signal',side_effect=PermissionError('PRIVATE_CLEANUP_TRANSCRIPT')),\
                 patch.object(sys,'stdout',stream),patch.object(time,'sleep'):
                self.assertEqual(g['execute'](),1)
            value=c.project_guest_status(stream.getvalue().encode(),ctx)
            self.assertEqual((value['phase'],value['exception_class']),('capture','ValueError'))
            self.assertNotIn('PRIVATE_',stream.getvalue())

    def test_actual_capture_arm_uses_the_passed_privacy_oracle_and_bound_ack(self):
        """Actual lifted capture function, synthetic command/output adapter, no VM."""
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);g=self.module(root);arm=c.ARMS[0];label=c.PAIRS[0]
            report=dict(mango=dict(pid=123,start_ticks=456),selinux_before='Enforcing',
                        samples=[],interventions=[],cpu_observations=[])
            oracle=types.SimpleNamespace(external_text=unittest.mock.Mock())
            def capture(argv,**kwargs):
                path=Path(argv[-1]);path.write_bytes(b'OWNED_SYNTHETIC_CAPTURE_BYTES')
                Path(str(path)+'.json').write_text(json.dumps(dict(width=1920,output_width=1920,
                    height=1080,output_height=1080,output_scale=1,output_transform=0,
                    selected_output='Unknown-1',outputs_seen=1,raw_bytes=8294400,stride=7680,flags=0)))
                return types.SimpleNamespace(returncode=0,stdout=b'',stderr=b'OWNED_SYNTHETIC_CAPTURE_LOG')
            def expect(kind,value=None,timeout=30):
                if kind in ('QMP-BEFORE','QMP-AFTER'):return dict(label=label,host_ns=100 if kind=='QMP-BEFORE' else 200)
                if kind=='RECEIVED':
                    self.assertEqual(value,dict(files=len(c.GUEST_FILES),arm=arm));return value
                raise AssertionError('Unexpected private capture acknowledgement')
            channel=types.SimpleNamespace(send=unittest.mock.Mock(),expect=expect)
            g['cpu_observation']=lambda identity:dict(pid=identity['pid'],start_ticks=identity['start_ticks'])
            g['bounded']=lambda argv:'Enforcing' if argv==['getenforce'] else (_ for _ in ()).throw(AssertionError('Unexpected capture query'))
            with patch.object(c,'PAIRS',(label,)),patch.object(c,'export_files') as exported,\
                 patch.object(g['subprocess'],'run',side_effect=capture),patch.object(g['time'],'sleep'):
                returned=g['capture_arm'](types.SimpleNamespace(),['FRESH_SYNTHETIC_PREFIX'],'Unknown-1',
                    root,report,channel,oracle,arm,dict(pid=123,start_ticks=456))
            self.assertIs(returned,report);self.assertEqual(exported.call_count,1)
            self.assertGreaterEqual(oracle.external_text.call_count,4)
            self.assertIn(unittest.mock.call(b'OWNED_SYNTHETIC_CAPTURE_LOG'),oracle.external_text.call_args_list)
            self.assertEqual([v['label'] for v in report['samples']],[label])
            self.assertEqual(report['selinux_after'],'Enforcing')
            self.assertIsInstance(json.loads((root/'guest-report.json').read_text()),dict)

    def test_original_baseline_raw_oracle_and_explicit_diagnostic_budget_remain(self):
        current=(HERE/'host.py').read_text()
        start=current.index("        vm.keys('home','down','down')")
        end=current.index("        state['interventions'].append",start)
        # Whole original v7 baseline slice, independently retained before refactoring.
        self.assertEqual(hashlib.sha256(current[start:end].encode()).hexdigest(),
            '05933f4f632682d630b35ad413ceb3bd69e930880b4a84847b5ac36f30fe96db')
        self.assertEqual(c.sha(HERE/'screencopy.c'),'72deb18e64b271d8c2fb182511b19056b6d182d1ffdc77106dd9515f22fc40e0')
        source=(HERE/'guest.py').read_text();tree=ast.parse(source)
        function=next(v for v in tree.body if isinstance(v,ast.FunctionDef) and v.name=='arm_desktop')
        self.assertTrue(any(isinstance(v,ast.Call) and isinstance(v.func,ast.Name)
            and v.func.id=='fresh_desktop_prefix' for v in ast.walk(function)))
        self.assertIn('15m python3 -B',(HERE/'run.sh').read_text())
        self.assertIn('19m bash',(ROOT/'.github/workflows/safe-rerender-v9-20261010.yml').read_text())
        self.assertEqual((c.MAX_FILE,c.MAX_TOTAL,c.MAX_WIRE),(32*1024**2,128*1024**2,200*1024**2))


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


class FreshDiscovery(unittest.TestCase):
    """Actual owned AF_UNIX servers plus explicitly synthetic proc/session data."""
    def server(self,root,names):
        code="""import os,socket,sys,select
from pathlib import Path
root=Path(sys.argv[1]);socks=[]
for name in sys.argv[2:]:
 s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.bind(str(root/name.replace('PID',str(os.getpid()))));s.listen(16);socks.append(s)
print(os.getpid(),flush=True)
while True:
 for s in select.select(socks,[],[],1)[0]:
  c,_=s.accept();c.close()
"""
        child=subprocess.Popen([sys.executable,'-c',code,str(root),*names],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.addCleanup(self.close,child)
        self.assertTrue(select.select([child.stdout],[],[],5)[0])
        pid=int(child.stdout.readline());self.assertEqual(pid,child.pid)
        return child

    @staticmethod
    def close(child):
        if child.poll() is None:child.terminate()
        child.wait(timeout=5)
        child.stdout.close();child.stderr.close()

    def test_real_peer_credentials_reject_foreign_uid_pid_symlink_and_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);g=GuestPhase().module(root);child=self.server(root,['owned.sock'])
            uid=os.getuid();path=root/'owned.sock'
            self.assertTrue(g['socket_peer'](path,child.pid,uid))
            self.assertFalse(g['socket_peer'](path,os.getpid(),uid))
            with self.assertRaises(RuntimeError):g['socket_peer'](path,child.pid,uid+1)
            alias=root/'alias';alias.symlink_to(path)
            with self.assertRaises(RuntimeError):g['socket_peer'](alias,child.pid,uid)
            regular=root/'regular';regular.write_bytes(b'SYNTHETIC')
            with self.assertRaises(RuntimeError):g['socket_peer'](regular,child.pid,uid)
            real_socket=socket.socket
            class Swapped:
                def __enter__(self):self.inner=real_socket(socket.AF_UNIX,socket.SOCK_STREAM);return self
                def __exit__(self,*a):self.inner.close()
                def settimeout(self,v):self.inner.settimeout(v)
                def connect(self,v):self.inner.connect(v)
                def getsockopt(self,*a):
                    value=self.inner.getsockopt(*a);path.rename(root/'original.sock');path.write_bytes(b'FOREIGN');return value
            with patch.object(socket,'socket',side_effect=lambda *a:Swapped()),self.assertRaises(RuntimeError):g['socket_peer'](path,child.pid,uid)
            self.assertEqual(path.read_bytes(),b'FOREIGN')

    def fixture(self,root):
        runtime=root/'runtime';runtime.mkdir(mode=0o700)
        fresh=self.server(runtime,['wayland-1','mango-PID.sock'])
        old=self.server(runtime,['wayland-0','old.sock'])
        proc=root/'proc';proc.mkdir()
        for name,session,display in [('111','old-session','wayland-1'),('112','fresh-session','wayland-1')]:
            p=proc/name;p.mkdir();(p/'environ').write_bytes(('XDG_SESSION_ID='+session+'\0XDG_RUNTIME_DIR='+str(runtime)+'\0WAYLAND_DISPLAY='+display+'\0MANGO_INSTANCE_SIGNATURE=/POISON\0DISPLAY='+(':OLD' if name=='111' else ':NEW')+'\0').encode())
        g=GuestPhase().module(root);original_path=Path
        def mapped(value='.'):
            return runtime if str(value)=='/run/user/1000' else proc if str(value)=='/proc' else original_path(value)
        g['Path']=mapped
        identity=dict(pid=fresh.pid,start_ticks=3,executable='SYNTHETIC_OWNED_SERVER')
        native=types.SimpleNamespace(identity=unittest.mock.Mock(return_value=identity))
        env=dict(XDG_SESSION_ID='fresh-session',XDG_RUNTIME_DIR=str(runtime),PATH='/usr/bin',XDG_DATA_DIRS='/usr/share')
        # The production helper always uses real UID1000. These owned local
        # fixtures therefore require the same UID and never impersonate another.
        self.assertEqual(os.getuid(),1000)
        return g,native,identity,env,runtime,fresh,old

    def test_fresh_prefix_selects_authenticated_server_and_same_session_children(self):
        with tempfile.TemporaryDirectory() as tmp:
            g,native,identity,env,runtime,fresh,old=self.fixture(Path(tmp))
            with patch.object(pwd,'getpwuid',return_value=types.SimpleNamespace(pw_name='liveuser',pw_dir='/home/liveuser')):
                prefix=g['fresh_desktop_prefix'](native,identity,env)
                self.assertIn('WAYLAND_DISPLAY=wayland-1',prefix)
                self.assertIn('MANGO_INSTANCE_SIGNATURE='+str(runtime/('mango-'+str(fresh.pid)+'.sock')),prefix)
                self.assertIn('DISPLAY=:NEW',prefix);self.assertNotIn('DISPLAY=:OLD',prefix)
                self.assertNotIn('MANGO_INSTANCE_SIGNATURE=/POISON',prefix)
                self.assertEqual(native.identity.call_args_list,[unittest.mock.call(fresh.pid,1000)]*2)

    def test_identity_session_runtime_path_xdg_and_ipc_poison_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            g,native,identity,env,runtime,fresh,old=self.fixture(Path(tmp))
            with patch.object(pwd,'getpwuid',return_value=types.SimpleNamespace(pw_name='liveuser',pw_dir='/home/liveuser')):
                for key,value in [('XDG_SESSION_ID','../PRIVATE'),('XDG_RUNTIME_DIR','/foreign'),('PATH',''),('XDG_DATA_DIRS',''),('MANGO_SOCKET','/foreign')]:
                    with self.subTest(key=key),self.assertRaises(RuntimeError):g['fresh_desktop_prefix'](native,identity,{**env,key:value})
                native.identity.side_effect=[identity,{**identity,'start_ticks':4}]
                with self.assertRaises(RuntimeError):g['fresh_desktop_prefix'](native,identity,env)
                native.identity.side_effect=None
                runtime.chmod(0o777)
                with self.assertRaises(RuntimeError):g['fresh_desktop_prefix'](native,identity,env)

    def test_closed_last_guard_projection_rejects_private_stale_or_wrong_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx=GuestPhase().fixture(Path(tmp));label='discovery-wayland-endpoint'
            status=c.guest_status('handoff-ipc-discovery','exception','RuntimeError',ctx,'new-desktop-deadline',label)
            raw=(c.GUEST_STATUS_PREFIX+json.dumps(status)+'\n').encode()
            self.assertEqual(c.project_guest_status(raw,ctx)['last_discovery_id'],label)
            for key,value in [('last_discovery_id','PRIVATE_TRANSCRIPT'),('primary_id','new-mango-count'),('phase','capture'),('exception_class','OSError'),('schema','arctic-safe-guest-fixed-stage-v2')]:
                bad={**status,key:value}
                with self.subTest(key=key),self.assertRaises(RuntimeError):c.validate_guest_status(bad,ctx)
            with self.assertRaises(RuntimeError):c.project_guest_status(raw+raw,ctx)
            class Foreign(RuntimeError):pass
            for error in (Foreign('ambiguous Wayland session'),RuntimeError('PRIVATE'),RuntimeError('ambiguous Wayland session','PRIVATE')):
                self.assertIsNone(c.discovery_failure_id(error))
            self.assertEqual(c.discovery_failure_id(RuntimeError('ambiguous Wayland session')),'native-wayland-ambiguous')

    def test_actual_original_readiness_loop_records_last_guard_preserves_deadline_and_clears_on_success(self):
        tree=ast.parse((HERE/'guest.py').read_text())
        loop=next(n for n in ast.walk(tree) if isinstance(n,ast.While) and any(isinstance(v,ast.Call) and isinstance(v.func,ast.Name) and v.func.id=='arm_desktop' for v in ast.walk(n)))
        code=compile(ast.fix_missing_locations(ast.Module(body=[loop],type_ignores=[])),str(HERE/'guest.py'),'exec')
        for success in (False,True):
            calls=[];detail=dict(id=None,last_discovery_id=None)
            def desktop(*a):
                calls.append(1)
                if len(calls)==1:raise RuntimeError('Fresh owned Wayland endpoint is unobserved or ambiguous')
                return ([],{}, {},{},2,{})
            sleeps=[];g=dict(arm_desktop=desktop,native=None,arm='default-restart',previous=None,original=None,
                _guest_primary_detail=detail,_guest_phase='handoff-ipc-discovery',c=c,deadline=60,
                time=types.SimpleNamespace(monotonic=lambda:0 if success else 61,sleep=lambda v:sleeps.append(v)))
            if success:
                exec(code,g);self.assertEqual(detail['last_discovery_id'],None);self.assertEqual(sleeps,[.2]);self.assertEqual(len(calls),2)
            else:
                with self.assertRaisesRegex(RuntimeError,'New attested desktop readiness deadline'):exec(code,g)
                self.assertEqual(detail['last_discovery_id'],'discovery-wayland-endpoint');self.assertEqual(sleeps,[])


# Whole admitted Mango 0.17.3 monitor schema; synthetic desktop values only.
def _fixture_monitors():
    return dict(monitors=[dict(name='Unknown-1', active=True, is_hdr=False,
        is_vrr=False, x=0, y=0, width=1920, height=1080, scale=1,
        layout_index=0, layout_symbol='T', last_open_surface='arctic-frame-reserve',
        tag_num=5, hide_clients=0,
        tags=[dict(index=i, client_count=0, is_active=i==1, is_urgent=False, layout='T')
              for i in range(1,6)], active_tags=[1],
        active_client=dict(id=None, title=None, appid=None), keymode='default',
        keyboardlayout='English (US)')])


class OutputConfiguration(unittest.TestCase):
    """Whole actual arm operation with labelled synthetic process/session facts."""
    def fixture(self, root, monitor, enforcing='Enforcing', raw=None, command_error=None):
        g=GuestPhase().module(root);g['_guest_phase']='session-handoff'
        proc=root/'proc';mango=proc/'222';mango.mkdir(parents=True)
        library=root/'owned-synthetic-scene.so';library.write_bytes(b'OWNED_SYNTHETIC_LIBRARY')
        (mango/'comm').write_text('mango\n');(mango/'cmdline').write_bytes(b'mango\0-d\0')
        (mango/'maps').write_text('0000-0001 r-xp 0 0:0 0 /usr/lib64/libscenefx-test.so\n')
        class FixturePath(type(Path())):
            def stat(self,*args,**kwargs):
                info=super().stat(*args,**kwargs)
                if str(self).startswith(str(proc)):
                    fields=list(info);fields[4]=1000;return os.stat_result(fields)
                return info
        def path(value='.'):
            value=str(value)
            return FixturePath(proc if value=='/proc' else library
                if value=='/usr/lib64/libscenefx-test.so' else value)
        g['Path']=path
        identity=dict(pid=222,start_ticks=3,executable='/usr/bin/mango')
        previous={**identity,'pid':111,'start_ticks':2}
        env=dict(WLR_RENDERER_FORCE_SOFTWARE='1',LIBGL_ALWAYS_SOFTWARE='1')
        (mango/'environ').write_bytes(('\0'.join(k+'='+v for k,v in
            {'XDG_SESSION_ID':'c9',**env}.items())+'\0').encode())
        original=dict(mango=dict(sha256='a'*64),actual_mango_argv=['mango'],
            renderer_environment=env,monitors=_fixture_monitors(),
            libraries=[dict(path=str(library.resolve()),sha256=c.sha(library))])
        prefix=['runuser','-u','liveuser','--','env','XDG_SESSION_ID=c9']
        native=types.SimpleNamespace(identity=lambda pid,uid:identity)
        calls=[]
        def bounded(argv,**kwargs):
            calls.append(argv)
            if argv==[*prefix,'mmsg','get','all-monitors']:
                if command_error is not None:raise command_error
                return json.dumps(monitor) if raw is None else raw
            if argv==['getenforce']:return enforcing
            if len(argv)==6 and argv[:4]==['loginctl','show-session','c9','-p']:
                return dict(Id='c9',User='1000',Type='wayland',VTNr='2',Active='yes')[argv[4]]
            if argv==['chvt','2']:return ''
            raise AssertionError('Unexpected labelled synthetic desktop command')
        g['bounded']=bounded;g['fresh_desktop_prefix']=lambda *args:prefix
        return g,native,previous,original,calls

    def call_arm(self, g, native, previous, original):
        original_sha=c.sha
        with patch.object(c,'sha',side_effect=lambda p:'a'*64
                if str(p)=='/usr/bin/mango' else original_sha(p)):
            return g['arm_desktop'](native,'default-restart',previous,original)

    def test_transient_fields_do_not_block_exact_whole_arm_and_prior_code_rejects(self):
        for key,value in [('last_open_surface','owned-synthetic-foot'),
                ('layout_index',1),('layout_symbol','M'),('hide_clients',1),
                ('keymode','owned-synthetic-mode'),('keyboardlayout','Hebrew'),
                ('active_tags',[2]),('active_client',dict(id=9,title='OWNED_SYNTHETIC',appid='foot')),
                ('tags',[dict(index=1,client_count=1,is_active=True,is_urgent=False,layout='T')])]:
            monitor=_fixture_monitors();monitor['monitors'][0][key]=value
            with self.subTest(key=key),tempfile.TemporaryDirectory() as tmp:
                g,native,previous,original,calls=self.fixture(Path(tmp),monitor)
                result=self.call_arm(g,native,previous,original)
                self.assertEqual(result[3],monitor)
                self.assertIn(['getenforce'],calls);self.assertIn(['chvt','2'],calls)
                self.assertEqual(calls[-1],['loginctl','show-session','c9','-p','Active','--value'])
                # Exact old full comparison, reconstructed from the current
                # source by undoing only this reviewed output correction.
                source=_rollback_visibility_guest((HERE/'guest.py').read_text())
                start=source.index('MONITOR_FIELDS =');end=source.index('def arm_desktop(',start)
                source=source[:start]+source[end:]
                first=source.index("    _handoff_stage('handoff-output-command')")
                last=source.index('    # Bind the freshly discovered IPC prefix',first)
                old="    _handoff_stage('handoff-output-security')\n    monitors=c.strict(bounded([*prefix,'mmsg','get','all-monitors']))\n    c.require(monitors==original['monitors'] and bounded(['getenforce'])=='Enforcing',\n              'Restart output or security differs')\n"
                source=source[:first]+old+source[last:]
                restored=source.replace('tools/safe-diagnostic-v5','tools/safe-diagnostic-v4')
                self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),
                    '1405954d37def85eef9993a8125796264c556a8e17ca90c4de4b91afce9705f7')
                node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='arm_desktop')
                exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),
                    str(HERE/'guest.py'),'exec'),g)
                calls.clear()
                with patch.object(c,'HANDOFF_PHASES',(*c.HANDOFF_PHASES,'handoff-output-security')), \
                        patch.object(c,'GUEST_PHASES',(*c.GUEST_PHASES,'handoff-output-security')):
                    with self.assertRaisesRegex(RuntimeError,'Restart output or security differs'):
                        self.call_arm(g,native,previous,original)
                self.assertNotIn(['getenforce'],calls);self.assertNotIn(['chvt','2'],calls)

    def test_all_output_identity_geometry_hdr_vrr_and_selection_changes_reject(self):
        for key,value in [('name','Unknown-2'),('x',1),('y',1),('width',1280),
                ('height',720),('scale',1.25),('is_hdr',True),('is_vrr',True),('tag_num',6),('active',False)]:
            monitor=_fixture_monitors();monitor['monitors'][0][key]=value
            with self.subTest(key=key),tempfile.TemporaryDirectory() as tmp:
                g,native,previous,original,calls=self.fixture(Path(tmp),monitor)
                expected='handoff-output-selection' if key=='active' else 'handoff-output-config'
                with self.assertRaises(RuntimeError):self.call_arm(g,native,previous,original)
                self.assertEqual(g['_guest_phase'],expected)
                self.assertNotIn(['getenforce'],calls);self.assertNotIn(['chvt','2'],calls)

    def test_schema_types_multiple_outputs_and_unknown_fields_remain_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            g=GuestPhase().module(Path(tmp));monitors=_fixture_monitors()
            self.assertEqual(tuple(g['output_configuration'](monitors)),g['OUTPUT_CONFIGURATION_FIELDS'])
            cases=[{},dict(monitors=[]),dict(monitors=monitors['monitors']*2),dict(monitors=[None]),
                dict(monitors=[dict(monitors['monitors'][0],extra='POISON')])]
            for key,value in [('name','PRIVATE /path'),('x',True),('width',True),('height',0),
                    ('scale',True),('scale',0),('tag_num',True),('tag_num',0),('is_hdr',1),('is_vrr',None),('active',1)]:
                candidate=copy.deepcopy(monitors);candidate['monitors'][0][key]=value;cases.append(candidate)
            for candidate in cases:
                with self.subTest(candidate=candidate),self.assertRaises(RuntimeError):g['output_configuration'](candidate)
            for key in g['MONITOR_FIELDS']:
                candidate=copy.deepcopy(monitors);del candidate['monitors'][0][key]
                with self.subTest(missing=key),self.assertRaises(RuntimeError):g['output_configuration'](candidate)

    def test_actual_command_parse_and_enforcing_roles_are_closed_and_keep_failure(self):
        for role,kwargs,klass in [('output-command',dict(command_error=RuntimeError('Guest observation command failed or exceeded bound')),'RuntimeError'),
                ('output-parse',dict(raw='not JSON'),'OTHER'),
                ('selinux-enforcing',dict(enforcing='Permissive'),'RuntimeError')]:
            with self.subTest(role=role),tempfile.TemporaryDirectory() as tmp:
                g,native,previous,original,calls=self.fixture(Path(tmp),_fixture_monitors(),**kwargs)
                try:self.call_arm(g,native,previous,original)
                except Exception as error:
                    context=Path(tmp)/'context';context.mkdir()
                    status=c.guest_status(g['_guest_phase'],'exception',c.guest_exception_class(error),
                        GuestPhase().fixture(context))
                else:self.fail('Required command/parse/Enforcing failure admitted')
                self.assertEqual(status['failure_role'],role);self.assertEqual(status['exception_class'],klass)
                self.assertNotIn(['chvt','2'],calls)

    def test_role_projection_binding_duplicates_and_privacy_cannot_be_extended(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx=GuestPhase().fixture(Path(tmp))
            for phase,role in c.OUTPUT_FAILURE_ROLES.items():
                status=c.guest_status(phase,'exception','RuntimeError',ctx,'new-desktop-deadline')
                self.assertEqual(status['failure_role'],role)
                raw=(c.GUEST_STATUS_PREFIX+json.dumps(status)+'\n').encode()
                self.assertEqual(c.project_guest_status(raw,ctx),status)
                for key,value in [('failure_role','PRIVATE_TRANSCRIPT'),('failure_role',None),
                        ('phase','capture'),('schema','arctic-safe-guest-fixed-stage-v3'),
                        ('execution_sha','0'*40),('release_acceptance',True)]:
                    with self.subTest(phase=phase,key=key),self.assertRaises(RuntimeError):
                        c.validate_guest_status(dict(status,**{key:value}),ctx)
                with self.assertRaises(RuntimeError):c.project_guest_status(raw+raw,ctx)
            spec=importlib.util.spec_from_file_location('output_role_screen',ROOT/'tools/native-functional/screen-evidence.py');screen=importlib.util.module_from_spec(spec);spec.loader.exec_module(screen)
            screen.external_text(raw)
            with self.assertRaises(Exception):screen.external_text(b'Transcript: PRIVATE_TRANSCRIPT\n'+raw)
            self.assertIsNone(c.guest_status('capture','exception','OSError',ctx)['failure_role'])


def _rollback_visibility_guest(source):
    """Private counterfactual only: restore exact retained v5 guest bytes."""
    source=source.replace('export WLR_SCENE_DEBUG_DAMAGE=rerender\\nexport WLR_SCENE_DISABLE_VISIBILITY=1','unset WLR_SCENE_DEBUG_DAMAGE\\nexport WLR_SCENE_DISABLE_VISIBILITY=1').replace("expected.update(WLR_SCENE_DEBUG_DAMAGE='rerender',WLR_SCENE_DISABLE_VISIBILITY='1')","expected['WLR_SCENE_DISABLE_VISIBILITY']='1'")
    begin=source.index('def display_binding(');end=source.index('def cpu_observation(',begin)
    source=source[:begin]+source[end:]
    replacements={
        ", 'WLR_SCENE_DISABLE_VISIBILITY'":'',
        "selector='unset WLR_SCENE_DEBUG_DAMAGE\\nunset WLR_SCENE_DISABLE_VISIBILITY' if self.arm=='default-restart' else 'unset WLR_SCENE_DEBUG_DAMAGE\\nexport WLR_SCENE_DISABLE_VISIBILITY=1'":"selector='unset WLR_SCENE_DEBUG_DAMAGE' if self.arm=='default-restart' else 'export WLR_SCENE_DEBUG_DAMAGE=rerender'",
        "'visibility-disabled-full-rerender'":"'rerender'",
        "expected['WLR_SCENE_DISABLE_VISIBILITY']='1'":"expected['WLR_SCENE_DEBUG_DAMAGE']='rerender'",
        "              and 'WLR_SCENE_DISABLE_VISIBILITY' not in observed_env\n":'',
        "    report['display_binding']=display_binding(native,mango_identity)\n":'',
        "                display=display_binding(native,new_mango)\n":'',
        'session_handoff=handoff,cpu_observations=[],display_binding=display)':'session_handoff=handoff,cpu_observations=[])',
        'session_handoff=handoff,session=session,display_binding=display))':'session_handoff=handoff,session=session))',
        'default-repeat-restart':'rerender-restart',
        'tools/safe-diagnostic-v9':'tools/safe-diagnostic-v5',
    }
    for new,old in replacements.items():source=source.replace(new,old)
    if hashlib.sha256(source.encode()).hexdigest()!='b6721545141f75ee2599c2d3eb6cc5735ef35f9228f52b3f66104e0bc9d26018':
        raise AssertionError('Private visibility rollback differs from exact retained v5')
    return source


class VisibilityDisplayBinding(unittest.TestCase):
    """Synthetic process/device adapters exercise actual new observers, no VM."""
    def test_actual_wrapper_unsets_damage_and_selects_only_visibility(self):
        helper=RerenderExperiment()
        for arm in c.ARMS:
            with self.subTest(arm=arm),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);script,query=helper.fixture(root)
                script.write_text('#!/bin/sh\nprintf "damage=%s\\nvisibility=%s\\n" "${WLR_SCENE_DEBUG_DAMAGE-unset}" "${WLR_SCENE_DISABLE_VISIBILITY-unset}"\nprintf "arg=%s\\n" "$@"\n')
                script.chmod(0o755);g=helper.module(root)
                contract=g['session_contract'](root,query)
                # Only this synthetic fixture redirects the packaged original
                # reference into its owned directory, as prior wrapper tests.
                contract['script']=str(script)
                owned=g['OwnedSessionOverride'](root,'a'*32,arm,contract,labeler=helper.synthetic_labels)
                try:
                    handoff=owned.install()
                    result=subprocess.run([str(owned.wrapper),'mango'],env={**os.environ,
                        'WLR_SCENE_DEBUG_DAMAGE':'POISON_DAMAGE','WLR_SCENE_DISABLE_VISIBILITY':'POISON_VISIBILITY'},
                        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=5)
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertEqual(result.stdout,'damage='+('unset' if arm=='default-restart' else 'rerender')+'\nvisibility='+('unset' if arm=='default-restart' else '1')+'\narg=mango\n')
                    self.assertEqual(handoff['selector'],'unset')
                finally:owned.close()

    def test_closed_binding_rejects_identity_private_fields_and_unknown_markers(self):
        value=RerenderExperiment.synthetic_display();identity=dict(pid=101,start_ticks=201)
        self.assertIs(c.validate_display_binding(value,identity),value)
        variants=[dict(value,pid=True),dict(value,pid=102),dict(value,start_ticks=200),
                  dict(value,kernel_release='PRIVATE TRANSCRIPT /home/account'),
                  dict(value,journal_status='PRIVATE_ERROR'),dict(value,PRIVATE_TRANSCRIPT='SECRET'),
                  dict(value,source_log_markers={**value['source_log_markers'],'PRIVATE':True}),
                  dict(value,source_log_markers={**value['source_log_markers'],'drm-dumb':1}),
                  dict(value,source_log_markers={**value['source_log_markers'],'drm-dumb':True})]
        for bad in variants:
            with self.assertRaises(RuntimeError):c.validate_display_binding(bad,identity)
        device=dict(node='card0',major=226,minor=0,driver='simple-framebuffer')
        self.assertIs(c.validate_display_binding(dict(value,devices=[device]),identity)['devices'][0],device)
        for key,change in [('node','/private/device'),('major',1),('minor',True),('driver','PRIVATE_DRIVER')]:
            with self.subTest(key=key),self.assertRaises(RuntimeError):
                c.validate_display_binding(dict(value,devices=[dict(device,**{key:change})]),identity)
        with self.assertRaises(RuntimeError):c.validate_display_binding(dict(value,devices=[device,device]),identity)

    def test_actual_observer_binds_char_device_pid_and_filters_source_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fds=root/'proc/101/fd';fds.mkdir(parents=True)
            (fds/'14').write_bytes(b'LABELLED_SYNTHETIC_FD')
            g=GuestPhase().module(root);identity=dict(pid=101,start_ticks=201,executable='/usr/bin/mango')
            native=types.SimpleNamespace(identity=lambda pid,uid:dict(identity))
            real_stat=os.stat;device=root/'dev/dri/card0';driver=root/'sys/dev/char/226:0/device/driver'
            info=types.SimpleNamespace(st_mode=stat.S_IFCHR|0o660,st_uid=0,st_rdev=os.makedev(226,0))
            def observed_stat(path,*args,**kwargs):
                return info if Path(path) in (fds/'14',device) else real_stat(path,*args,**kwargs)
            def links(path):
                if Path(path)==fds/'14':return '/dev/dri/card0'
                if Path(path)==driver:return '../../../drivers/simple-framebuffer'
                raise AssertionError('Unowned synthetic link lookup')
            journal='[render/allocator/drm_dumb.c:230] Created DRM dumb allocator\nPRIVATE_TRANSCRIPT_SECRET\n[backend/drm/drm.c:112] Using atomic DRM interface\n'
            calls=[]
            def query(argv):calls.append(argv);return journal
            with patch.object(os,'stat',side_effect=observed_stat),patch.object(os,'readlink',side_effect=links):
                report=g['display_binding'](native,identity,root,query)
                self.assertEqual(report['devices'],[dict(node='card0',major=226,minor=0,driver='simple-framebuffer')])
                self.assertTrue(report['source_log_markers']['drm-dumb']);self.assertTrue(report['source_log_markers']['atomic-drm'])
                self.assertNotIn('PRIVATE_TRANSCRIPT',json.dumps(report))
                self.assertEqual(calls,[['journalctl','--no-pager','--boot=0','-o','cat','_COMM=mango','_PID=101','-n','400']])
                for poison in [types.SimpleNamespace(st_mode=stat.S_IFREG|0o660,st_uid=0,st_rdev=os.makedev(226,0)),
                               types.SimpleNamespace(st_mode=stat.S_IFCHR|0o660,st_uid=1000,st_rdev=os.makedev(226,0)),
                               types.SimpleNamespace(st_mode=stat.S_IFCHR|0o660,st_uid=0,st_rdev=os.makedev(1,0))]:
                    info=poison
                    with self.assertRaises(RuntimeError):g['display_binding'](native,identity,root,query)
                info=types.SimpleNamespace(st_mode=stat.S_IFCHR|0o660,st_uid=0,st_rdev=os.makedev(226,0))
                states=iter([identity,dict(identity,start_ticks=202)])
                with self.assertRaises(RuntimeError):
                    g['display_binding'](types.SimpleNamespace(identity=lambda pid,uid:next(states)),identity,root,query)

    def test_missing_logs_remain_unknown_and_do_not_infer_allocator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'proc/101/fd').mkdir(parents=True)
            g=GuestPhase().module(root);identity=dict(pid=101,start_ticks=201,executable='/usr/bin/mango')
            native=types.SimpleNamespace(identity=lambda pid,uid:dict(identity))
            unavailable=[RuntimeError('PRIVATE_RAW_ERROR'),subprocess.TimeoutExpired('PRIVATE_ARGV',20),
                         UnicodeDecodeError('utf-8',b'\xffPRIVATE_BYTES',0,1,'PRIVATE_REASON')]
            queries=[lambda argv:'',*[lambda argv,error=error:(_ for _ in ()).throw(error) for error in unavailable]]
            for query in queries:
                report=g['display_binding'](native,identity,root,query)
                self.assertEqual(report['devices'],[]);self.assertFalse(any(report['source_log_markers'].values()))
                self.assertNotIn('PRIVATE',json.dumps(report))

    def test_host_requires_new_binding_and_returned_report_identity(self):
        helper=RerenderExperiment();previous=dict(pid=100,start_ticks=200,executable='/usr/bin/mango',sha256='a'*64)
        env=dict(WLR_RENDERER_FORCE_SOFTWARE='1',LIBGL_ALWAYS_SOFTWARE='1')
        ready=dict(arm='default-restart',guest_ns=300,mango={**previous,'pid':101,'start_ticks':201},
                   renderer_environment=env,output='Unknown-1',session_handoff=helper.synthetic_handoff('default-restart'),
                   session=helper.synthetic_session(),display_binding=helper.synthetic_display())
        hello=dict(output='Unknown-1',original=dict(renderer_environment=env))
        self.assertIs(host.validate_arm_ready(ready,'default-restart',hello,previous),ready)
        for key,value in [('pid',100),('start_ticks',200),('PRIVATE_TRANSCRIPT','SECRET')]:
            bad=copy.deepcopy(ready);bad['display_binding'][key]=value
            with self.assertRaises(RuntimeError):host.validate_arm_ready(bad,'default-restart',hello,previous)
        absent=copy.deepcopy(ready);del absent['display_binding']
        with self.assertRaises(RuntimeError):host.validate_arm_ready(absent,'default-restart',hello,previous)



class CombinedOwnedSocketCleanup(unittest.TestCase):
    """Real local AF_UNIX/inode and harmless owned-child controls; no QEMU/VM."""
    def fixture(self,root):
        listener=socket.socket(socket.AF_UNIX);path=root/'qmp.sock';listener.bind(str(path))
        owner=host.OwnedTemporaries(root);owner.socket(path.name)
        return listener,path,owner

    def test_real_owned_child_socket_unlink_requires_positive_reap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'qmp.sock'
            code='import os,signal,socket,sys\ns=socket.socket(socket.AF_UNIX);s.bind(sys.argv[1])\ndef stop(*args):\n s.close();os.unlink(sys.argv[1]);sys.exit(0)\nsignal.signal(signal.SIGTERM,stop)\nprint("READY",flush=True)\nsignal.pause()\n'
            proc=subprocess.Popen([sys.executable,'-c',code,str(path)],stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL,start_new_session=True,text=True)
            vm=object.__new__(host.OwnedVM);vm.proc=proc;vm.f=vm.s=None;vm.log=io.BytesIO();vm.reaped=False
            owner=None
            try:
                self.assertEqual(proc.stdout.readline(),'READY\n')
                owner=host.OwnedTemporaries(root);owner.socket(path.name)
                retained=owner.files[path.name][0]
                self.assertFalse(vm.reaped);self.assertIsNone(proc.poll())
                vm.close();self.assertTrue(vm.reaped);self.assertEqual(proc.returncode,0)
                self.assertFalse(path.exists());owner.close(sockets_reaped=vm.reaped);owner=None
                with self.assertRaises(OSError):os.fstat(retained)
            finally:
                if proc.poll() is None:vm.close()
                if owner is not None:owner.close(sockets_reaped=vm.reaped)
                proc.stdout.close()

    def test_absent_socket_without_reap_remains_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            listener,path,owner=self.fixture(Path(tmp));path.unlink()
            try:
                with self.assertRaises(FileNotFoundError):owner.close()
            finally:listener.close()

    def test_missing_regular_file_remains_failure_after_reap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);owner=host.OwnedTemporaries(root);owner.create('disk.qcow2');(root/'disk.qcow2').unlink()
            with self.assertRaises(FileNotFoundError):owner.close(sockets_reaped=True)

    def test_present_regular_replacement_remains_and_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            listener,path,owner=self.fixture(Path(tmp));path.unlink();path.write_bytes(b'FOREIGN REGULAR')
            foreign=path.lstat()
            try:
                with self.assertRaises(RuntimeError):owner.close(sockets_reaped=True)
                self.assertEqual(path.read_bytes(),b'FOREIGN REGULAR');self.assertEqual(path.lstat().st_ino,foreign.st_ino)
            finally:listener.close()

    def test_present_socket_replacement_remains_and_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            listener,path,owner=self.fixture(Path(tmp));path.unlink();other=socket.socket(socket.AF_UNIX);other.bind(str(path));foreign=path.lstat()
            try:
                with self.assertRaises(RuntimeError):owner.close(sockets_reaped=True)
                self.assertTrue(stat.S_ISSOCK(path.lstat().st_mode));self.assertEqual(path.lstat().st_ino,foreign.st_ino)
            finally:listener.close();other.close()

    def test_symlink_replacement_never_follows_or_unlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);listener,path,owner=self.fixture(root);path.unlink();foreign=root/'foreign';foreign.write_bytes(b'FOREIGN');path.symlink_to(foreign)
            try:
                with self.assertRaises(RuntimeError):owner.close(sockets_reaped=True)
                self.assertTrue(path.is_symlink());self.assertEqual(foreign.read_bytes(),b'FOREIGN')
            finally:listener.close()

    def test_reused_descriptor_is_not_closed_or_admitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);listener,path,owner=self.fixture(root);fd=owner.files[path.name][0]
            foreign=root/'foreign';foreign.write_bytes(b'FOREIGN');other=os.open(foreign,os.O_RDONLY)
            os.dup2(other,fd);path.unlink()
            try:
                with self.assertRaises(RuntimeError):owner.close(sockets_reaped=True)
                self.assertEqual(os.fstat(fd).st_ino,foreign.stat().st_ino)
            finally:os.close(fd);os.close(other);listener.close()

    def test_existing_socket_requires_identity_and_reap_flag_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            listener,path,owner=self.fixture(Path(tmp))
            try:
                with self.assertRaises(RuntimeError):owner.close(sockets_reaped=1)
                self.assertTrue(path.exists());owner.close();self.assertFalse(path.exists())
            finally:listener.close()

    def test_stream_close_failure_preserves_primary_and_closes_remaining(self):
        proc=subprocess.Popen([sys.executable,'-c','pass'],start_new_session=True)
        proc.wait(timeout=5);events=[];primary=OSError('LABELLED PRIMARY CLOSE')
        class Resource:
            def __init__(self,name,failure=None):self.name=name;self.failure=failure
            def close(self):
                events.append(self.name)
                if self.failure is not None:raise self.failure
        vm=object.__new__(host.OwnedVM);vm.proc=proc;vm.reaped=False
        vm.f=Resource('stream',primary);vm.s=Resource('socket',RuntimeError('LABELLED SECONDARY CLOSE'));vm.log=Resource('log')
        with self.assertRaises(OSError) as raised:vm.close()
        self.assertIs(raised.exception,primary);self.assertEqual(events,['stream','socket','log'])
        self.assertTrue(vm.reaped);self.assertEqual(proc.returncode,0)

    def test_constructor_cleanup_cannot_mask_original_qmp_acquisition_failure(self):
        proc=subprocess.Popen([sys.executable,'-c','pass'],start_new_session=True)
        proc.wait(timeout=5);observed=[];original_close=host.OwnedVM.close
        def secondary(vm):
            original_close(vm);observed.append(vm)
            raise OSError('LABELLED SECONDARY CONSTRUCTOR CLEANUP')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.object(host.subprocess,'Popen',return_value=proc),patch.object(host.OwnedVM,'close',secondary):
                with self.assertRaises(RuntimeError) as raised:host.OwnedVM(['LABELLED SYNTHETIC CHILD'],root/'qmp.sock',root)
            self.assertEqual(raised.exception.args,('Owned QEMU exited before QMP acquisition',))
            self.assertEqual(len(observed),1);self.assertTrue(observed[0].reaped);self.assertTrue(observed[0].log.closed)
            self.assertEqual(proc.returncode,0)

    def test_descriptor_close_failure_keeps_primary_and_closes_remaining(self):
        class Primary(RuntimeError):
            def __bool__(self):return False
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);owner=host.OwnedTemporaries(root);first=owner.create('a');second=owner.create('b');directory=owner.directory
            original_close=os.close;events=[];primary=Primary('LABELLED PRIMARY IDENTITY');secondary=OSError('LABELLED SECONDARY CLOSE')
            original_verify=owner.verify
            def verify(name):
                if name=='a':raise primary
                return original_verify(name)
            def close(fd):
                events.append(fd);original_close(fd)
                if fd==first:raise secondary
            with patch.object(owner,'verify',verify),patch.object(host.os,'close',close):
                with self.assertRaises(RuntimeError) as raised:owner.close()
            self.assertIs(raised.exception,primary);self.assertEqual(events,[first,second,directory])
            self.assertTrue((root/'a').exists());self.assertFalse((root/'b').exists())
            for fd in (first,second,directory):
                with self.assertRaises(OSError):os.fstat(fd)


if __name__=='__main__':unittest.main()


class LegacyRendererDiscovery(unittest.TestCase):
    @staticmethod
    def debug_fixture(pid=101,ticks=201):
        return dict(schema='arctic-safe-renderer-debug-v1',pid=pid,start_ticks=ticks,
            source='pid-journal',status='unavailable',bytes=0,sha256=None,renderer='unknown',
            source_markers={key:False for key in c.RENDERER_DEBUG_MARKERS})

    def module(self):
        root=Path(tempfile.gettempdir())
        return RerenderExperiment().module(root)


    def test_debug_argv_is_one_exact_flag_and_rejects_unknown_original(self):
        g=self.module()
        for original in (['mango'],['/usr/bin/mango','-c','/safe/config.conf']):
            self.assertEqual(g['debug_mango_argv'](original),[*original,'-d'])
        for bad in (None,[],['foot'],['mango','-d'],['mango','$(secret)'],['mango',False]):
            with self.subTest(bad=bad),self.assertRaises(RuntimeError):g['debug_mango_argv'](bad)

    def test_exact_source_markers_and_llvmpipe_are_projected_without_raw_values(self):
        g=self.module();identity=dict(pid=123,start_ticks=456)
        lines=['ARCTIC-SAFE-DEBUG '+'e'*32+' default-restart 123']
        for key,(source,literal) in c.RENDERER_DEBUG_LITERALS.items():
            if key in ('allocator-shm','drm-forced-legacy','drm-fallback-legacy'):continue
            lines.append('00:00:00.123 [INFO] ['+source+':123] '+literal)
        lines.append('00:00:00.123 [INFO] [render/fx_renderer/fx_renderer.c:475] GL renderer: llvmpipe (LLVM 22.1.0, 256 bits)')
        raw=('\n'.join(lines)+'\n').encode()
        result=g['project_renderer_debug'](raw,identity,'mango-stderr-file','e'*32,'default-restart')
        self.assertEqual(result['renderer'],'llvmpipe');self.assertTrue(result['source_markers']['allocator-drm-dumb'])
        self.assertTrue(result['source_markers']['drm-atomic']);self.assertEqual(result['sha256'],hashlib.sha256(raw).hexdigest())
        self.assertNotIn('LLVM',json.dumps(result));self.assertNotIn('GL renderer',json.dumps(result))
        self.assertFalse(result['source_markers']['allocator-gbm'])

    def test_prefix_spoofs_try_logs_conflicts_and_foreign_sentinel_are_not_admitted(self):
        g=self.module();identity=dict(pid=123,start_ticks=456)
        raw=b'ARCTIC-SAFE-DEBUG '+b'e'*32+b' default-restart 123\ntranscript [backend/drm/drm.c:123] Using atomic DRM interface\n00:00:00.123 [DEBUG] [render/allocator/allocator.c:123] Trying to create gbm allocator\n'
        result=g['project_renderer_debug'](raw,identity,'pid-journal','e'*32,'default-restart')
        self.assertEqual(result['renderer'],'unknown');self.assertFalse(any(result['source_markers'].values()))
        for raw in (b'ARCTIC-SAFE-DEBUG '+b'e'*32+b' default-restart 122\n',
                    b'ARCTIC-SAFE-DEBUG '+b'e'*32+b' default-restart 123\nARCTIC-SAFE-DEBUG '+b'e'*32+b' default-restart 123\n',
                    b'00:00:00.123 [DEBUG] [backend/drm/drm.c:123] Using atomic DRM interface\n00:00:00.124 [DEBUG] [backend/drm/drm.c:123] WLR_DRM_NO_ATOMIC set, forcing legacy DRM interface\n'):
            with self.assertRaises(RuntimeError):g['project_renderer_debug'](raw,identity,'mango-stderr-file' if raw.startswith(b'ARCTIC') else 'pid-journal','e'*32,'default-restart')

    def test_closed_debug_provenance_identity_types_and_unknowns_fail(self):
        identity=dict(pid=101,start_ticks=201);value=self.debug_fixture()
        self.assertEqual(c.validate_renderer_debug(value,identity),value)
        for key,bad in [('pid',True),('start_ticks',202),('source','private/path'),('status','accepted'),
                         ('sha256','f'*64),('bytes',True),('renderer','private transcription')]:
            item=copy.deepcopy(value);item[key]=bad
            with self.subTest(key=key),self.assertRaises(RuntimeError):c.validate_renderer_debug(item,identity)
        item=copy.deepcopy(value);item['source_markers']['private']=False
        with self.assertRaises(RuntimeError):c.validate_renderer_debug(item,identity)
        item=copy.deepcopy(value);item['source_markers']['scenefx']=True
        with self.assertRaises(RuntimeError):c.validate_renderer_debug(item,identity)


    def test_actual_ci_preparation_is_one_literal_and_semantic_inverse(self):
        import fnmatch
        old=subprocess.check_output(['git','-C',str(ROOT),'show','HEAD^:'+c.CI_PATH])
        new=(ROOT/c.CI_PATH).read_bytes()
        self.assertEqual(new,old.replace(c.CI_ANCHOR,c.CI_ANCHOR+c.CI_ADDITION,1))
        old_ignored=re.findall(rb'^      - ([^\n]+)$',old,flags=re.M)
        new_ignored=re.findall(rb'^      - ([^\n]+)$',new,flags=re.M)
        for ref in [c.BRANCH,'main','staging','codex/arctic-release-integration','codex/native-control-other',*map(bytes.decode,old_ignored)]:
            before=not any(fnmatch.fnmatchcase(ref,v.decode()) for v in old_ignored)
            after=not any(fnmatch.fnmatchcase(ref,v.decode()) for v in new_ignored)
            self.assertEqual(after,False if ref==c.BRANCH else before)
        self.assertEqual(new.replace(c.CI_ADDITION,b'',1),old)







class OwnedStderrControls(unittest.TestCase):
    """Real owned files/children, synthetic Mango identity; no VM or ioctl."""
    def fixture(self, root, arm):
        fixture=RerenderExperiment();script,query=fixture.fixture(root);g=fixture.module(root)
        contract=g['session_contract'](root,query);contract['script']=str(script)
        script.write_text('#!/usr/bin/python3\nimport json,os,stat,sys,time\ni=os.fstat(2)\nprint(json.dumps(dict(pid=os.getpid(),dev=i.st_dev,ino=i.st_ino,uid=i.st_uid,gid=i.st_gid,mode=stat.S_IMODE(i.st_mode),args=sys.argv[1:],selectors=[os.environ.get(k) for k in ("WLR_DRM_NO_ATOMIC","WLR_SCENE_DEBUG_DAMAGE","WLR_SCENE_DISABLE_VISIBILITY")],software=os.environ.get("WLR_RENDERER_FORCE_SOFTWARE"))),flush=True)\nos.write(2,b"00:00:00.123 [INFO] [render/fx_renderer/fx_renderer.c:473] Creating scenefx FX renderer\\n")\ntime.sleep(8)\n')
        owned=g['OwnedSessionOverride'](root,'e'*32,arm,contract,fixture.synthetic_labels,debug_directory=root/'run')
        return g,owned

    def test_real_owned_preexec_fd2_and_whole_observation_for_both_default_arms(self):
        for arm in c.ARMS:
            with self.subTest(arm=arm),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);g,owned=self.fixture(root,arm);child=None
                try:
                    handoff=owned.install();fd,info=owned.files[owned.debug_file]
                    child=subprocess.Popen([str(owned.wrapper),'mango'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                        env={**os.environ,'WLR_DRM_NO_ATOMIC':'POISON','WLR_SCENE_DEBUG_DAMAGE':'POISON','WLR_SCENE_DISABLE_VISIBILITY':'POISON','WLR_RENDERER_FORCE_SOFTWARE':'1'},text=True)
                    record=json.loads(child.stdout.readline());self.assertEqual(record['pid'],child.pid)
                    self.assertEqual((record['dev'],record['ino'],record['uid'],record['gid'],record['mode']),
                        (info.st_dev,info.st_ino,1000,1000,0o600))
                    self.assertEqual(record['args'],['mango','-d']);self.assertEqual(record['selectors'],[None,None,None]);self.assertEqual(record['software'],'1')
                    self.assertEqual(handoff['selector'],'unset');self.assertNotIn(str(owned.debug_file),json.dumps(handoff))
                    ticks=int((Path('/proc')/str(child.pid)/'stat').read_text().split(') ')[1].split()[19])
                    identity=dict(pid=child.pid,start_ticks=ticks,executable='/usr/bin/mango')
                    seen=[];native=types.SimpleNamespace(identity=lambda pid,uid:identity)
                    result=g['renderer_debug_observation'](native,identity,'e'*32,arm,types.SimpleNamespace(external_text=lambda raw:seen.append(raw)),owned)
                    self.assertEqual(result['status'],'observed');self.assertTrue(result['source_markers']['scenefx'])
                    self.assertEqual(seen,[os.pread(fd,1024**2+1,0)]);self.assertEqual(result['sha256'],hashlib.sha256(seen[0]).hexdigest())
                    self.assertNotIn(str(owned.debug_file),json.dumps(result))
                finally:
                    if child is not None:
                        if child.poll() is None:child.terminate()
                        child.communicate(timeout=5)
                    owned.close()
                self.assertFalse(owned.debug_file.exists())
                with self.assertRaises(OSError):os.fstat(fd)

    def test_exact_preexec_rejects_replaced_symlink_and_bad_mode_without_original_exec(self):
        for variant in ('replacement','symlink','fifo','mode'):
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);g,owned=self.fixture(root,c.ARMS[0]);aside=None
                try:
                    owned.install();path=owned.debug_file
                    if variant=='mode':path.chmod(0o604)
                    else:
                        aside=path.with_suffix('.retained');path.rename(aside)
                        if variant=='replacement':path.write_bytes(b'FOREIGN_CANARY');path.chmod(0o600)
                        elif variant=='symlink':path.symlink_to(aside)
                        else:os.mkfifo(path,0o600)
                    result=subprocess.run([str(owned.wrapper),'mango'],capture_output=True,timeout=5)
                    self.assertEqual(result.returncode,70);self.assertEqual(result.stdout,b'');self.assertEqual(result.stderr,b'')
                    if variant=='replacement':self.assertEqual(path.read_bytes(),b'FOREIGN_CANARY')
                finally:
                    if variant=='mode':path.chmod(0o600);owned.close()
                    else:
                        with self.assertRaises(RuntimeError):owned.close()
                        self.assertTrue(path.exists());path.unlink();aside.unlink()

    def test_observation_rejects_actual_fd_mismatch_race_private_and_oversize(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);g,owned=self.fixture(root,c.ARMS[0]);owned.install();fd,info=owned.files[owned.debug_file]
            identity=dict(pid=123,start_ticks=456,executable='/usr/bin/mango');native=types.SimpleNamespace(identity=lambda pid,uid:identity)
            good=b'ARCTIC-SAFE-DEBUG '+b'e'*32+b' default-restart 123\n00:00:00.123 [INFO] [render/fx_renderer/fx_renderer.c:473] Creating scenefx FX renderer\n'
            os.write(fd,good);real_stat=os.stat
            def bound_stat(path,*a,**k):
                return os.fstat(fd) if str(path)=='/proc/123/fd/2' else real_stat(path,*a,**k)
            try:
                with patch.object(os,'stat',side_effect=bound_stat):
                    events=[]
                    def reject(raw):events.append(raw);raise RuntimeError('PRIVATE_TRANSCRIPT_SENTINEL')
                    value=g['renderer_debug_observation'](native,identity,'e'*32,c.ARMS[0],types.SimpleNamespace(external_text=reject),owned)
                    self.assertEqual(events,[good]);self.assertEqual(value['status'],'privacy-rejected');self.assertFalse(any(value['source_markers'].values()))
                    self.assertNotIn('PRIVATE',json.dumps(value))
                    os.ftruncate(fd,0);os.write(fd,b'x'*(1024**2+1));value=g['renderer_debug_observation'](native,identity,'e'*32,c.ARMS[0],types.SimpleNamespace(external_text=lambda raw:self.fail('Oversize input reached screen')),owned)
                    self.assertEqual(value['status'],'unavailable');os.ftruncate(fd,0);os.pwrite(fd,good,0)
                wrong=types.SimpleNamespace(st_mode=stat.S_IFREG|0o600,st_dev=info.st_dev,st_ino=info.st_ino+1,st_uid=1000,st_gid=1000)
                with patch.object(os,'stat',return_value=wrong):
                    value=g['renderer_debug_observation'](native,identity,'e'*32,c.ARMS[0],types.SimpleNamespace(external_text=lambda raw:self.fail('Foreign fd reached screen')),owned)
                    self.assertEqual(value['status'],'unavailable')
                calls=[0]
                def race(path,*a,**k):
                    if str(path)=='/proc/123/fd/2':calls[0]+=1;return os.fstat(fd) if calls[0]==1 else wrong
                    return real_stat(path,*a,**k)
                with patch.object(os,'stat',side_effect=race):
                    value=g['renderer_debug_observation'](native,identity,'e'*32,c.ARMS[0],types.SimpleNamespace(external_text=lambda raw:self.fail('Changed fd reached screen')),owned)
                    self.assertEqual(value['status'],'unavailable')
                native.identity=lambda pid,uid:{**identity,'start_ticks':457}
                with self.assertRaises(RuntimeError):g['renderer_debug_observation'](native,identity,'e'*32,c.ARMS[0],types.SimpleNamespace(external_text=lambda raw:raw),owned)
            finally:owned.close()

    def test_fifo_counterfactual_old_opener_blocks_and_owned_child_is_reaped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);g,owned=self.fixture(root,c.ARMS[0]);owned.install()
            fd,info=owned.files[owned.debug_file];aside=owned.debug_file.with_suffix('.retained')
            owned.debug_file.rename(aside);os.mkfifo(owned.debug_file,0o600)
            try:
                old=owned.debug_opener(info);self.assertEqual(old.count('|os.O_NONBLOCK'),1)
                old=old.replace('|os.O_NONBLOCK','',1)
                with self.assertRaises(subprocess.TimeoutExpired):
                    subprocess.run(['/usr/bin/python3','-c',old,'mango'],capture_output=True,timeout=.5)
                result=subprocess.run([str(owned.wrapper),'mango'],capture_output=True,timeout=2)
                self.assertEqual(result.returncode,70);self.assertEqual(result.stdout,b'');self.assertEqual(result.stderr,b'')
            finally:
                with self.assertRaises(RuntimeError):owned.close()
                with self.assertRaises(OSError):os.fstat(fd)
                owned.debug_file.unlink();aside.unlink()

    def test_all_owned_resource_closes_attempted_after_first_close_error_and_old_counterfactual(self):
        raw=(HERE/'guest.py').read_text()
        klass=next(n for n in ast.parse(raw).body if isinstance(n,ast.ClassDef) and n.name=='OwnedSessionOverride')
        method=next(n for n in klass.body if isinstance(n,ast.FunctionDef) and n.name=='close')
        current=ast.get_source_segment(raw,method)
        block="            finally:\n                try:\n                    held=os.fstat(fd)\n                    c.require(stat.S_ISREG(held.st_mode) and\n                        (held.st_dev,held.st_ino,held.st_uid)==(owned.st_dev,owned.st_ino,owned.st_uid),\n                        'Owned override descriptor differs')\n                    os.close(fd)\n                except BaseException as error:errors.append(error)"
        self.assertEqual(current.count(block),1)
        old=current.replace(block,'            finally:os.close(fd)',1).replace('fd,owned=self.files[path]','fd,_=self.files[path]',1)
        self.assertEqual(hashlib.sha256(old.encode()).hexdigest(),'7c16ab77ca0b98672bf70a1bd26400477cf0fda26bdb2fe1791a1972420a9d31')
        for counterfactual in (True,False):
            with self.subTest(counterfactual=counterfactual),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);g,owned=self.fixture(root,c.ARMS[0]);owned.install()
                acquired=dict(owned.files);first=acquired[owned.configuration][0]
                real_close=os.close;calls=[];primary=OSError(5,'SYNTHETIC_OWNED_CLOSE_FAILURE')
                def fail_first(fd):
                    calls.append(fd);real_close(fd)
                    if fd==first:raise primary
                action=owned.close
                if counterfactual:
                    namespace=dict(g);exec(old,namespace);action=lambda:namespace['close'](owned)
                try:
                    with patch.object(os,'close',side_effect=fail_first),self.assertRaises(OSError) as caught:action()
                    self.assertIs(caught.exception,primary)
                    self.assertEqual(len(calls),1 if counterfactual else 3)
                    if counterfactual:
                        self.assertTrue(owned.wrapper.exists());self.assertTrue(owned.debug_file.exists())
                        for path,(fd,_) in acquired.items():
                            if fd!=first:os.fstat(fd)
                    else:
                        self.assertEqual(owned.files,{})
                        for path,(fd,_) in acquired.items():
                            self.assertFalse(path.exists())
                            with self.assertRaises(OSError):os.fstat(fd)
                finally:
                    for path,(fd,_) in acquired.items():
                        if fd not in calls:real_close(fd)
                        if path.exists():path.unlink()
                    owned.files.clear();owned.contents.clear()

    def test_real_reused_descriptor_is_preserved_and_other_owned_resources_are_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);g,owned=self.fixture(root,c.ARMS[0]);owned.install()
            acquired=dict(owned.files);fd,info=acquired[owned.debug_file]
            foreign=root/'foreign-canary';foreign.write_bytes(b'FOREIGN_CANARY');foreign.chmod(0o600)
            other=os.open(foreign,os.O_RDWR|os.O_CLOEXEC)
            try:
                os.dup2(other,fd)
                with self.assertRaises(RuntimeError):owned.close()
                self.assertEqual(os.pread(fd,64,0),b'FOREIGN_CANARY');self.assertEqual(os.fstat(fd).st_ino,os.fstat(other).st_ino)
                self.assertNotEqual(os.fstat(fd).st_ino,info.st_ino)
                self.assertTrue(owned.debug_file.exists());self.assertEqual(owned.files,{})
                for path,(number,_) in acquired.items():
                    if number==fd:continue
                    self.assertFalse(path.exists())
                    with self.assertRaises(OSError):os.fstat(number)
            finally:
                os.close(fd);os.close(other);owned.debug_file.unlink()

    def test_directory_symlink_foreign_owner_and_cleanup_identity_remain_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);g,owned=self.fixture(root,c.ARMS[0]);owned.debug_directory.chmod(0o777)
            with self.assertRaises(RuntimeError):owned.install()
            self.assertFalse(owned.debug_file.exists());owned.close()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);g,owned=self.fixture(root,c.ARMS[0]);owned.install();fd,_=owned.files[owned.debug_file]
            aside=owned.debug_file.with_suffix('.retained');owned.debug_file.rename(aside);owned.debug_file.write_bytes(b'FOREIGN_CANARY');owned.debug_file.chmod(0o600)
            with self.assertRaises(RuntimeError):owned.close()
            self.assertEqual(owned.debug_file.read_bytes(),b'FOREIGN_CANARY');self.assertTrue(aside.exists())
            with self.assertRaises(OSError):os.fstat(fd)


import ctypes as C
DRM_NAME_MAP={'Blob': 'drm_Blob', 'C': 'drm_C', 'Crtc': 'drm_Crtc', 'DRIVERS': 'drm_DRIVERS', 'Fb2': 'drm_Fb2', 'MetadataBoundsError': 'drm_MetadataBoundsError', 'Mode': 'drm_Mode', 'OBJECT_CRTC': 'drm_OBJECT_CRTC', 'OBJECT_PLANE': 'drm_OBJECT_PLANE', 'ObjectProperties': 'drm_ObjectProperties', 'PROPERTY_NAMES': 'drm_PROPERTY_NAMES', 'Path': 'drm_Path', 'Plane': 'drm_Plane', 'PlaneResources': 'drm_PlaneResources', 'ProcessIdentity': 'drm_ProcessIdentity', 'Property': 'drm_Property', 'Query': 'drm_Query', 'REQUESTS': 'drm_REQUESTS', 'Resources': 'drm_Resources', 'U32': 'drm_U32', 'U64': 'drm_U64', 'Version': 'drm_Version', 'address': 'drm_address', 'array': 'drm_array', 'bounded_observe_drm': 'drm_bounded_observe_drm', 'child_entry': 'drm_child_entry', 'errno': 'drm_errno', 'existing_debugfs': 'drm_existing_debugfs', 'fcntl': 'drm_fcntl', 'fields': 'drm_fields', 'ids': 'drm_ids', 'json': 'drm_json', 'object_properties': 'drm_object_properties', 'observe_drm': 'drm_observe_drm', 'os': 'drm_os', 'parse_existing_framebuffers': 'drm_parse_existing_framebuffers', 'probe_fd': 'drm_probe_fd', 're': 'drm_re', 'require': 'drm_require', 'stat': 'drm_stat', 'strict_json': 'drm_strict_json', 'struct': 'drm_struct', 'subprocess': 'drm_subprocess', 'sys': 'drm_sys', 'validate_snapshot': 'drm_validate_snapshot'}
D=types.SimpleNamespace(**{name:getattr(c,target) for name,target in DRM_NAME_MAP.items()})
IDENTITY=dict(pid=1234,start_ticks=555,executable='/usr/bin/mango')
PRIVATE='PRIVATE_DRM_PROPERTY_SENTINEL'
class KernelModel:
    """Synthetic kernel copies only into caller-owned ctypes array addresses."""
    def __init__(self, mutation=None):
        self.mutation, self.calls = mutation, []

    def __call__(self, fd, request, raw, mutate):
        assert fd == 91 and mutate is True
        role, kind = next((key, kind) for key, (value, kind) in D.REQUESTS.items() if value == request)
        self.calls.append(role)
        obj = kind.from_buffer(raw)
        if role == 'version':
            obj.major, obj.minor, obj.patch = 1, 0, 0
            if obj.name:
                C.memmove(obj.name, b'simpledrm', 9)
            obj.name_len = 9
        elif role == 'resources':
            obj.count_fbs, obj.count_crtcs, obj.count_connectors, obj.count_encoders = 1, 1, 1, 0
            for ptr, values in [(obj.fb_id_ptr, [41]), (obj.crtc_id_ptr, [31]), (obj.connector_id_ptr, [11])]:
                if ptr:
                    C.memmove(ptr, (D.U32 * len(values))(*values), 4 * len(values))
        elif role == 'crtc':
            obj.fb_id, obj.mode_valid = 41, 1
            obj.mode.hdisplay, obj.mode.vdisplay = 1920, 1080
        elif role == 'plane_resources':
            obj.count_planes = 1
            if obj.plane_id_ptr:
                C.memmove(obj.plane_id_ptr, (D.U32 * 1)(33), 4)
        elif role == 'plane':
            obj.crtc_id, obj.fb_id, obj.count_format_types = 31, 41, 2
        elif role == 'fb2':
            obj.width, obj.height, obj.pixel_format, obj.flags = 1920, 1080, 0x34325258, 2
            obj.pitches[0], obj.handles[0], obj.modifier[0] = 7680, 0xDEADBEEF, 0
        elif role == 'object_properties':
            keys, values = ([10, 99], [1, 123456]) if obj.obj_type == D.OBJECT_CRTC else ([20, 21], [31, 8])
            obj.count_props = len(keys)
            if obj.props_ptr:
                C.memmove(obj.props_ptr, (D.U32 * len(keys))(*keys), 4 * len(keys))
                C.memmove(obj.prop_values_ptr, (D.U64 * len(values))(*values), 8 * len(values))
        elif role == 'property':
            obj.name = {10: b'ACTIVE', 99: PRIVATE.encode(), 20: b'CRTC_ID', 21: b'FB_DAMAGE_CLIPS'}[obj.prop_id]
            if obj.prop_id == 21:
                obj.flags = 1 << 4
        elif role == 'blob':
            obj.length = 16
            if obj.data:
                C.memmove(obj.data, (C.c_int32 * 4)(0, 0, 1920, 1080), 16)
        else:
            raise AssertionError(role)
        if self.mutation:
            self.mutation(role, obj)
        return 0


def full_report(model=None):
    data = D.probe_fd(91, model or KernelModel())
    report = dict(schema='arctic-safe-readonly-drm-v1', pid=1234, start_ticks=555,
                  status='observed', devices=[dict(node='card0', major=226, minor=0,
                    existing_debugfs=dict(status='unknown', framebuffers=[], damage_clips_status='unknown'), **data)])
    return D.validate_snapshot(report, IDENTITY)


class ReadonlyDRMControls(unittest.TestCase):
    def test_actual_structures_and_read_requests_equal_compiled_public_C_ABI(self):
        actual = {'requests': {'blob': 3222299820, 'crtc': 3228066977, 'fb2': 3228067022, 'object_properties': 3223348409, 'plane': 3223348406, 'plane_resources': 3222299829, 'property': 3225445546, 'resources': 3225445536, 'version': 3225445376}, 'structures': {'Blob': {'offsets': {'blob_id': 0, 'data': 8, 'length': 4}, 'size': 16}, 'Crtc': {'offsets': {'count_connectors': 8, 'crtc_id': 12, 'fb_id': 16, 'gamma_size': 28, 'mode': 36, 'mode_valid': 32, 'set_connectors_ptr': 0, 'x': 20, 'y': 24}, 'size': 104}, 'Fb2': {'offsets': {'fb_id': 0, 'flags': 16, 'handles': 20, 'height': 8, 'modifier': 72, 'offsets': 52, 'pitches': 36, 'pixel_format': 12, 'width': 4}, 'size': 104}, 'Mode': {'offsets': {'clock': 0, 'flags': 28, 'hdisplay': 4, 'hskew': 12, 'hsync_end': 8, 'hsync_start': 6, 'htotal': 10, 'name': 36, 'type': 32, 'vdisplay': 14, 'vrefresh': 24, 'vscan': 22, 'vsync_end': 18, 'vsync_start': 16, 'vtotal': 20}, 'size': 68}, 'ObjectProperties': {'offsets': {'count_props': 16, 'obj_id': 20, 'obj_type': 24, 'prop_values_ptr': 8, 'props_ptr': 0}, 'size': 32}, 'Plane': {'offsets': {'count_format_types': 20, 'crtc_id': 4, 'fb_id': 8, 'format_type_ptr': 24, 'gamma_size': 16, 'plane_id': 0, 'possible_crtcs': 12}, 'size': 32}, 'PlaneResources': {'offsets': {'count_planes': 8, 'plane_id_ptr': 0}, 'size': 16}, 'Property': {'offsets': {'count_enum_blobs': 60, 'count_values': 56, 'enum_blob_ptr': 8, 'flags': 20, 'name': 24, 'prop_id': 16, 'values_ptr': 0}, 'size': 64}, 'Resources': {'offsets': {'connector_id_ptr': 16, 'count_connectors': 40, 'count_crtcs': 36, 'count_encoders': 44, 'count_fbs': 32, 'crtc_id_ptr': 8, 'encoder_id_ptr': 24, 'fb_id_ptr': 0, 'max_height': 60, 'max_width': 52, 'min_height': 56, 'min_width': 48}, 'size': 64}, 'Version': {'offsets': {'date': 40, 'date_len': 32, 'desc': 56, 'desc_len': 48, 'major': 0, 'minor': 4, 'name': 24, 'name_len': 16, 'patch': 8}, 'size': 64}}}
        for name, value in actual['structures'].items():
            kind = getattr(D, name)
            self.assertEqual(C.sizeof(kind), value['size'])
            self.assertEqual({field: getattr(kind, field).offset for field, _ in kind._fields_}, value['offsets'])
        self.assertEqual({name: value[0] for name, value in D.REQUESTS.items()}, actual['requests'])

    def test_actual_probe_positive_current_framebuffer_clip_and_no_private_projection(self):
        model = KernelModel()
        report = full_report(model)
        device = report['devices'][0]
        self.assertEqual(device['driver'], 'simpledrm')
        self.assertEqual(device['framebuffers'][0]['pitches'], [7680])
        self.assertEqual(device['framebuffers'][0]['modifiers'], [0])
        self.assertEqual(device['planes'][0]['properties']['FB_DAMAGE_CLIPS']['rectangles'], [[0, 0, 1920, 1080]])
        output = json.dumps(report)
        self.assertNotIn(PRIVATE, output)
        self.assertNotIn(str(0xDEADBEEF), output)
        self.assertNotIn('handles', output)
        self.assertEqual(set(model.calls), set(D.REQUESTS))

    def test_hotplug_count_growth_rejected_before_reading_arrays(self):
        def mutation(role, obj):
            if role == 'resources' and obj.crtc_id_ptr:
                obj.count_crtcs += 1
        with self.assertRaises(D.MetadataBoundsError):
            D.probe_fd(91, KernelModel(mutation))

    def test_foreign_returned_array_pointer_never_dereferenced(self):
        def mutation(role, obj):
            if role == 'resources' and obj.crtc_id_ptr:
                obj.crtc_id_ptr = 1
        with self.assertRaises(D.MetadataBoundsError):
            D.probe_fd(91, KernelModel(mutation))

    def test_driver_name_count_and_unknown_driver_closed(self):
        def overlong(role, obj):
            if role == 'version':
                obj.name_len = 64
        with self.assertRaises(D.MetadataBoundsError):
            D.probe_fd(91, KernelModel(overlong))
        def unknown(role, obj):
            if role == 'version' and obj.name:
                C.memmove(obj.name, b'PRIVATE!!', 9)
        report = full_report(KernelModel(unknown))
        self.assertEqual(report['devices'][0]['driver'], 'unknown')
        self.assertNotIn('PRIVATE', json.dumps(report))

    def test_blob_bounds_and_returned_pointer_and_rect_order(self):
        for fault in ['length', 'pointer', 'rectangle']:
            def mutation(role, obj):
                if role == 'blob':
                    if fault == 'length':
                        obj.length = 17
                    elif obj.data and fault == 'pointer':
                        obj.data = 1
                    elif obj.data and fault == 'rectangle':
                        C.memmove(obj.data, (C.c_int32 * 4)(30, 0, 10, 1080), 16)
            with self.subTest(fault=fault), self.assertRaises(D.MetadataBoundsError):
                D.probe_fd(91, KernelModel(mutation))

    def test_framebuffer_pitch_and_flags_and_plane_format_count_fail_closed(self):
        for fault in ['pitch', 'flags', 'formats']:
            def mutation(role, obj):
                if role == 'fb2' and fault == 'pitch':
                    obj.pitches[0] = 1024 * 1024 + 1
                if role == 'fb2' and fault == 'flags':
                    obj.flags = 0xFFFFFFFF
                if role == 'plane' and fault == 'formats':
                    obj.count_format_types = 257
            with self.subTest(fault=fault), self.assertRaises(D.MetadataBoundsError):
                D.probe_fd(91, KernelModel(mutation))

    def test_returned_duplicate_property_names_and_bad_bool_status_rejected(self):
        good = full_report()
        for change in ['private-key', 'bool-id', 'bad-status', 'bad-modifier-count']:
            bad = copy.deepcopy(good)
            if change == 'private-key':
                bad['devices'][0][PRIVATE] = PRIVATE
            elif change == 'bool-id':
                bad['devices'][0]['crtcs'][0]['id'] = True
            elif change == 'bad-status':
                bad['devices'][0]['status'] = PRIVATE
            else:
                bad['devices'][0]['framebuffers'][0]['modifiers'] = []
            with self.subTest(change=change), self.assertRaises(D.MetadataBoundsError):
                D.validate_snapshot(bad, IDENTITY)

    def test_forged_debugfs_current_id_and_float_major_and_empty_positive_blob_rejected(self):
        for fault in ['foreign-debug-id', 'float-major', 'empty-blob']:
            report = full_report()
            device = report['devices'][0]
            if fault == 'foreign-debug-id':
                device['existing_debugfs'] = dict(status='parsed', damage_clips_status='unknown',
                    framebuffers=[dict(id=900, width=1920, height=1080, pitch=7680, format=0x34325258, modifier=0)])
            elif fault == 'float-major':
                device['major'] = 226.0
            else:
                device['planes'][0]['properties']['FB_DAMAGE_CLIPS']['rectangles'] = []
            with self.subTest(fault=fault), self.assertRaises(D.MetadataBoundsError):
                D.validate_snapshot(report, IDENTITY)

    def test_timeout_is_closed_unknown_and_fixed20s_owned_child_args(self):
        native = types.SimpleNamespace(identity=lambda *_: dict(IDENTITY))
        calls = []
        def timeout(argv, **kwargs):
            calls.append((argv, kwargs))
            raise subprocess.TimeoutExpired(PRIVATE, 20, output=PRIVATE)
        report = D.bounded_observe_drm(native, IDENTITY, HERE / 'guest.py', run=timeout)
        self.assertEqual(report['devices'], [])
        self.assertNotIn(PRIVATE, json.dumps(report))
        argv, kwargs = calls[0]
        self.assertEqual(argv[1], '-I')
        self.assertEqual(argv[-1], '--safe-readonly-drm-child')
        self.assertEqual(kwargs['timeout'], 20)
        self.assertEqual(kwargs['stderr'], subprocess.DEVNULL)
        self.assertEqual(json.loads(kwargs['input']), IDENTITY)

    def test_real_worker_invalid_private_input_has_no_output_no_drm(self):
        result = subprocess.run([sys.executable, '-I', str(HERE / 'guest.py'), '--safe-readonly-drm-child'],
            input=json.dumps({PRIVATE: PRIVATE}).encode(), capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b'')
        self.assertEqual(result.stderr, b'')

    def test_malformed_child_duplicate_json_and_changed_pid_start_rejected(self):
        native = types.SimpleNamespace(identity=lambda *_: dict(IDENTITY))
        result = types.SimpleNamespace(returncode=0, stdout=b'{"schema":"a","schema":"b"}')
        with self.assertRaises(D.MetadataBoundsError):
            D.bounded_observe_drm(native, IDENTITY, HERE / 'guest.py', run=lambda *_a, **_k: result)
        values = iter([dict(IDENTITY), dict(IDENTITY, start_ticks=556)])
        native.identity = lambda *_: next(values)
        result = types.SimpleNamespace(returncode=0, stdout=json.dumps(full_report()).encode())
        with self.assertRaises(D.MetadataBoundsError):
            D.bounded_observe_drm(native, IDENTITY, HERE / 'guest.py', run=lambda *_a, **_k: result)

    def test_actual_acquisition_private_fd_closed_on_query_permission_and_cancel(self):
        class Native:
            def identity(self, *_):
                return dict(IDENTITY)
        info = types.SimpleNamespace(st_mode=stat.S_IFCHR | 0o600, st_uid=0,
                                     st_rdev=D.os.makedev(226, 0), st_dev=7, st_ino=8)
        with tempfile.TemporaryDirectory(prefix='drm-model-', dir=HERE) as root:
            root = Path(root)
            descriptors = root / 'proc/1234/fd'
            descriptors.mkdir(parents=True)
            (descriptors / '14').symlink_to('/dev/dri/card0')
            for error in [PermissionError(13, PRIVATE), KeyboardInterrupt(PRIVATE)]:
                def fail(*_args, **_kwargs):
                    raise error
                with patch.object(Path, 'lstat', return_value=info), patch.object(D.os, 'stat', return_value=info), \
                     patch.object(D.os, 'open', return_value=91), patch.object(D.os, 'fstat', return_value=info), \
                     patch.object(D.fcntl, 'fcntl', return_value=D.os.O_RDONLY), patch.object(D.os, 'close') as close:
                    if isinstance(error, KeyboardInterrupt):
                        with self.assertRaises(KeyboardInterrupt) as caught:
                            D.observe_drm(Native(), IDENTITY, root=root, ioctl=fail)
                        self.assertIs(caught.exception, error)
                    else:
                        report = D.observe_drm(Native(), IDENTITY, root=root, ioctl=fail)
                        self.assertEqual(report['devices'][0]['reason'], 'permission')
                        self.assertNotIn(PRIVATE, json.dumps(report))
                    close.assert_called_once_with(91)

    def test_existing_debugfs_selected_framebuffer_projected_without_private_addresses(self):
        raw = (b'framebuffer[41]:\n\tallocated by = mango\n\tformat = XR24 little-endian (0x34325258)\n'
               b'\tmodifier=0x0\n\tsize=1920x1080\n\tlayers:\n\t\t\tpitch[0]=7680\n'
               b'\t\t\tvaddr=PRIVATE_ADDRESS_SENTINEL\nframebuffer[40]:\n\tallocated by = [fbcon]\n')
        report = D.parse_existing_framebuffers(raw, {41})
        self.assertEqual(report['framebuffers'], [dict(id=41, width=1920, height=1080,
            pitch=7680, format=0x34325258, modifier=0)])
        self.assertEqual(report['damage_clips_status'], 'unknown')
        self.assertNotIn('PRIVATE', json.dumps(report))
        self.assertEqual(D.parse_existing_framebuffers(raw, {42})['status'], 'unknown')
        with self.assertRaises(D.MetadataBoundsError):
            D.parse_existing_framebuffers(raw + raw, {41})
        with self.assertRaises(D.MetadataBoundsError):
            D.parse_existing_framebuffers(raw.replace(b'pitch[0]=7680', b'pitch[0]=9999999'), {41})


    def test_actual_debugfs_primary_cancellation_preserved_over_close_failure(self):
        class Falsey(RuntimeError):
            def __bool__(self):
                return False
        info = types.SimpleNamespace(st_mode=stat.S_IFREG | 0o400, st_uid=0)
        for primary in [KeyboardInterrupt(PRIVATE), SystemExit(7), Falsey(PRIVATE)]:
            with self.subTest(kind=type(primary).__name__), patch.object(D.os, 'open', return_value=91), \
                 patch.object(D.os, 'fstat', return_value=info), patch.object(D.os, 'read', side_effect=primary), \
                 patch.object(D.os, 'close', side_effect=OSError(5, PRIVATE)) as close:
                with self.assertRaises(type(primary)) as caught:
                    D.existing_debugfs(HERE, 0, {41})
                self.assertIs(caught.exception, primary)
                close.assert_called_once_with(91)


