"""Closed optional stop observations never manufacture a completed Native run."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
spec=importlib.util.spec_from_file_location('owned_stop_retention_runner',HERE/'runner.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)

def value(phase='install',code=None,elapsed=1,deadline=2400):
    return dict(schema='arctic-native-harness-stop-v1',phase=phase,qemu_returncode=code,
                elapsed_seconds=elapsed,deadline_seconds=deadline,deadline_reached=elapsed>=deadline,
                exit_marker_present=False,reason='process-exited' if code is not None else 'deadline-expired' if elapsed>=deadline else 'exit-marker-missing',release_acceptance=False)

class StopPreservation(unittest.TestCase):
    def owned(self,path):
        """Actual temp-file graph with only its root UID metadata intercepted."""
        fstat=os.fstat;path_stat=Path.stat
        def root_info(info):
            fields=list(info);fields[4]=0;return os.stat_result(fields)
        def observed_fd(fd):
            info=fstat(fd)
            return root_info(info) if (info.st_dev,info.st_ino)==self.identity else info
        def observed_path(item,*args,**kwargs):
            info=path_stat(item,*args,**kwargs)
            return root_info(info) if (info.st_dev,info.st_ino)==self.identity else info
        info=path.stat();self.identity=(info.st_dev,info.st_ino)
        return patch.object(os,'fstat',observed_fd),patch.object(Path,'stat',observed_path)

    def test_actual_files_preserve_only_exact_names_bytes_hashes_and_private_mode(self):
        for phase in ('install','boot'):
            for code,elapsed in ((None,1),(None,2401),(0,1),(-9,1)):
                with self.subTest(phase=phase,code=code,elapsed=elapsed),tempfile.TemporaryDirectory() as temp:
                    vm,evidence=Path(temp)/'vm',Path(temp)/'evidence';vm.mkdir();evidence.mkdir()
                    path=vm/('native-stop-'+phase+'.json');raw=(json.dumps(value(phase,code,elapsed),sort_keys=True)+'\n').encode()
                    path.write_bytes(raw);path.chmod(0o600)
                    (vm/'native-stop-private.json').write_bytes(b'private arbitrary JSON')
                    a,b=self.owned(path)
                    with a,b:result=runner.R.preserve_phase(vm,evidence,'harness')
                    output=evidence/'harness'/path.name
                    self.assertEqual(output.read_bytes(),raw);self.assertEqual(path.read_bytes(),raw)
                    self.assertEqual(stat.S_IMODE(output.stat().st_mode),0o600)
                    self.assertEqual(result[path.name]['sha256'],hashlib.sha256(raw).hexdigest())
                    self.assertIs(result[path.name]['release_acceptance'],False)
                    self.assertNotIn('native-stop-private.json',result)
                    self.assertFalse((evidence/'harness'/'native-stop-private.json').exists())

    def test_wrong_owner_mode_symlink_schema_types_reasons_and_private_payload_reject(self):
        mutations=[lambda v:v.update(phase='boot'),lambda v:v.update(schema='other'),lambda v:v.update(qemu_returncode=True),
            lambda v:v.update(elapsed_seconds=True),lambda v:v.update(elapsed_seconds=-1),lambda v:v.update(elapsed_seconds=float('nan')),
            lambda v:v.update(deadline_seconds=False),lambda v:v.update(deadline_seconds=0),lambda v:v.update(deadline_reached=1),
            lambda v:v.update(deadline_reached=True),lambda v:v.update(exit_marker_present=True),lambda v:v.update(reason='private reason'),
            lambda v:v.update(release_acceptance=True),lambda v:v.update(password='private'),lambda v:v.pop('reason')]
        for mutate in mutations:
            with self.subTest(mutate=mutate),tempfile.TemporaryDirectory() as temp:
                vm,evidence=Path(temp)/'vm',Path(temp)/'evidence';vm.mkdir();evidence.mkdir();v=value();mutate(v)
                path=vm/'native-stop-install.json';path.write_text(json.dumps(v));path.chmod(0o600);original=path.read_bytes()
                a,b=self.owned(path)
                with a,b:result=runner.R.preserve_phase(vm,evidence,'harness')
                self.assertEqual(result[path.name],dict(retained=False,reason='closed-record-rejected',release_acceptance=False))
                self.assertFalse((evidence/'harness'/path.name).exists());self.assertEqual(path.read_bytes(),original)
        for variant in ('wrong-owner','public-mode','symlink','duplicate','utf8'):
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as temp:
                vm,evidence=Path(temp)/'vm',Path(temp)/'evidence';vm.mkdir();evidence.mkdir()
                path=vm/'native-stop-install.json';path.write_text(json.dumps(value()));path.chmod(0o600)
                if variant=='public-mode':path.chmod(0o644)
                if variant=='symlink':path.rename(vm/'private-source');path.symlink_to(vm/'private-source')
                if variant=='duplicate':path.write_text(json.dumps(value())[:-1]+',"reason":"exit-marker-missing"}')
                if variant=='utf8':path.write_bytes(b'\xffprivate')
                if variant=='wrong-owner' and os.getuid()==0:
                    path.chown(1000,1000)
                if variant=='wrong-owner':result=runner.R.preserve_phase(vm,evidence,'harness')
                else:
                    a,b=self.owned(path)
                    with a,b:result=runner.R.preserve_phase(vm,evidence,'harness')
                self.assertIs(result[path.name]['retained'],False)
                self.assertFalse((evidence/'harness'/path.name).exists())

    def test_source_hash_change_discards_only_acquired_optional_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            vm,evidence=Path(temp)/'vm',Path(temp)/'evidence';vm.mkdir();evidence.mkdir()
            path=vm/'native-stop-install.json';path.write_text(json.dumps(value()));path.chmod(0o600)
            original=path.read_bytes();digest=runner.R.digest
            def changed(item):
                if item==path:path.write_bytes(original+b' ')
                return digest(item)
            a,b=self.owned(path)
            with a,b,patch.object(runner.R,'digest',side_effect=changed):result=runner.R.preserve_phase(vm,evidence,'harness')
            self.assertIs(result[path.name]['retained'],False)
            self.assertFalse((evidence/'harness'/path.name).exists())
            self.assertEqual(path.read_bytes(),original+b' ')

    def test_real_named_fifo_is_rejected_without_waiting_for_writer(self):
        with tempfile.TemporaryDirectory() as temp:
            vm,evidence=Path(temp)/'vm',Path(temp)/'evidence';vm.mkdir();evidence.mkdir()
            path=vm/'native-stop-install.json';os.mkfifo(path,0o600)
            script="import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); import runner; value=runner.R.preserve_phase(Path(sys.argv[2]),Path(sys.argv[3]),'harness'); assert value['native-stop-install.json']==dict(retained=False,reason='closed-record-rejected',release_acceptance=False); assert not (Path(sys.argv[3])/'harness'/'native-stop-install.json').exists()"
            result=subprocess.run([sys.executable,'-B','-c',script,str(HERE),str(vm),str(evidence)],capture_output=True,timeout=2)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout,b'');self.assertTrue(stat.S_ISFIFO(path.stat().st_mode))

    def test_metadata_allocation_bound_and_exact_four_kib_original(self):
        valid=json.dumps(value()).encode()
        for raw,retained in ((valid+b' '*(4096-len(valid)),True),(valid+b' '*(4097-len(valid)),False),(b' '*4096,False)):
            with self.subTest(length=len(raw),retained=retained),tempfile.TemporaryDirectory() as temp:
                vm,evidence=Path(temp)/'vm',Path(temp)/'evidence';vm.mkdir();evidence.mkdir()
                path=vm/'native-stop-install.json';path.write_bytes(raw);path.chmod(0o600);reads=[];fdopen=os.fdopen
                class ObserveRead:
                    def __init__(self,stream):self.stream=stream
                    def __enter__(self):return self
                    def __exit__(self,*args):return self.stream.__exit__(*args)
                    def fileno(self):return self.stream.fileno()
                    def read(self,size):reads.append(size);return self.stream.read(size)
                def observed(fd,mode,*args,**kwargs):
                    stream=fdopen(fd,mode,*args,**kwargs)
                    return ObserveRead(stream) if mode=='rb' else stream
                a,b=self.owned(path)
                with a,b,patch.object(os,'fdopen',side_effect=observed):result=runner.R.preserve_phase(vm,evidence,'harness')
                if retained:self.assertEqual((evidence/'harness'/path.name).read_bytes(),raw)
                else:self.assertIs(result[path.name]['retained'],False);self.assertFalse((evidence/'harness'/path.name).exists())
                self.assertEqual(reads,[] if len(raw)>4096 else [4097]);self.assertEqual(path.read_bytes(),raw)

if __name__=='__main__':unittest.main()
