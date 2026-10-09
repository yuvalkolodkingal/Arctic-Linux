"""Disabled dispatch, source pins, bounded diagnostics and container ownership controls."""
import importlib.util
import json
import os
import signal
import subprocess
from pathlib import Path
import re
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).parent
sys.path.insert(0,str(HERE))
import runner as R

class Controls(unittest.TestCase):
    def test_disabled_manifest_refuses_before_docker_or_actions_access(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'manifest.json';path.write_text(json.dumps({'ready':False,'release_acceptance':False}))
            args=types.SimpleNamespace(manifest=path)
            with patch.object(R.subprocess,'check_output') as call,self.assertRaises(RuntimeError):R.verify(args,Path(root))
            call.assert_not_called()

    def test_public_archive_inventory_is_explicit_and_source_inputs_exist(self):
        root=HERE.resolve().parents[1]
        self.assertTrue(all((root/name).is_file() for name in R.C.EXECUTION_FILES))
        self.assertIn('host/serial.log',R.C.ARCHIVE_FILES)
        self.assertTrue(set(R.C.REQUIRED_IMAGES)<=set(R.C.ARCHIVE_FILES))
        self.assertNotIn('data.iso',R.C.ARCHIVE_FILES)

    def test_preserve_full_bounded_uart_and_prefix_port_for_independent_replay(self):
        with tempfile.TemporaryDirectory() as root:
            vm=Path(root)/'vm';vm.mkdir();target=Path(root)/'host'
            serial=b'actual complete console record\n'+b'x'*70000
            (vm/'serial.log').write_bytes(serial);(vm/'installer-port.log').write_bytes(b'y'*70000)
            records=R.preserve_host(vm,target)
            self.assertEqual((target/'serial.log').read_bytes(),serial)
            self.assertEqual((target/'installer-port.log.bounded-prefix.bin').stat().st_size,65536)
            self.assertEqual(records['serial.log']['sha256'],R.C.digest(serial))
            self.assertTrue(all('host/'+path.name in R.C.ARCHIVE_FILES for path in target.iterdir()))

    def test_container_cleanup_never_removes_existing_name_without_matching_new_receipt(self):
        script=(HERE/'run-live.sh').read_text()
        code=script.split("<<'PY_CLEANUP'\n",1)[1].split('\nPY_CLEANUP',1)[0]
        identity='a'*64;name='arctic-paired-native-'+'b'*32;invocation='c'*32
        with tempfile.TemporaryDirectory() as root:
            receipt=Path(root)/'container-id'
            for scenario in ('absent','foreign-label','different-id','different-name','owned'):
                if scenario!='absent':receipt.write_text(identity)
                row={'Id':identity,'Name':'/'+name,'Config':{'Labels':{'org.arctic.installer.invocation':invocation}}}
                if scenario=='foreign-label':row['Config']['Labels']['org.arctic.installer.invocation']='d'*32
                if scenario=='different-id':row['Id']='e'*64
                if scenario=='different-name':row['Name']='/existing-other'
                with patch.object(sys,'argv',['cleanup','docker',str(receipt),name,invocation]),patch.object(R.subprocess,'check_output',return_value=json.dumps([row]).encode()),patch.object(R.subprocess,'run') as remove:
                    exec(compile(code,'owned-cleanup-control','exec'),{})
                    if scenario=='owned':self.assertEqual(remove.call_args.args[0],['docker','rm','-f',identity])
                    else:remove.assert_not_called()

    def test_repeated_real_signals_do_not_interrupt_owned_process_group_reap(self):
        class Child:
            pid=424242
            calls=0
            def poll(self):return None
            def wait(self,timeout):
                self.calls+=1
                if self.calls==1:raise subprocess.TimeoutExpired('controlled',timeout)
                os.kill(os.getpid(),signal.SIGTERM)
                os.kill(os.getpid(),signal.SIGINT)
                if self.calls==2:raise subprocess.TimeoutExpired('controlled cleanup',timeout)
                return 0
        child=Child();killed=[]
        with tempfile.TemporaryDirectory() as root,patch.object(R.subprocess,'Popen',return_value=child),patch.object(R.os,'killpg',side_effect=lambda pid,sig:killed.append((pid,sig))):
            with self.assertRaises(subprocess.TimeoutExpired):R.execute(['fixture'],Path(root)/'owned.log',1,root,{})
        self.assertEqual(killed,[(424242,signal.SIGTERM),(424242,signal.SIGKILL)])
        self.assertEqual(child.calls,3)


if __name__=='__main__':unittest.main()
