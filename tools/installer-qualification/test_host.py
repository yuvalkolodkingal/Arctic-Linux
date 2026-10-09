"""Owned host fault controls; no VM/image qualification is claimed."""
import contextlib
import importlib.util
import json
import os
import signal
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).parent

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

D=load('installer_driver_controls',HERE/'driver.py')
H=load('installer_controller_controls',HERE/'controller.py')
G=load('installer_control_fixtures',HERE/'test_guest.py')

class Proc:
    def __init__(self):self.pid=200;self.alive=True;self.calls=[]
    def poll(self):return None if self.alive else 0
    def terminate(self):self.calls.append('terminate');self.alive=False
    def kill(self):self.calls.append('kill');self.alive=False
    def wait(self,timeout):self.calls.append('wait');return 0

class Socket:
    def __init__(self,greeting):self.greeting=greeting;self.closed=False;self.stream=None
    def settimeout(self,value):self.timeout=value
    def connect(self,path):self.path=path
    def recv(self,bound):data,self.greeting=self.greeting,b'';return data
    def makefile(self,mode):
        import io
        self.stream=io.StringIO();return self.stream
    def close(self):self.closed=True

class Display:
    def __init__(self,fail=False):
        self.fail=fail;self.calls=[];self.proof=dict(gpu_id='arctic_taskbar_gpu',guest_monitor_verification_required=True,
            heads=[dict(head=n,console_id=n,device_address='pci/0000/01.0') for n in (0,1)])
    def _query(self,vm,name,*args):return dict(running=True)
    def _owner(self,vm):return ':1.5'
    def _gpu(self,vm):return 'pci/0000/01.0'
    def _call(self,path,*args,**kwargs):
        self.calls.append((path,args))
        if self.fail and path.endswith('_0'):raise RuntimeError('injected UIInfo error')
        return '()'

class Controls(unittest.TestCase):
    def test_partial_utf8_request_waits_until_newline_and_exact_request_processed_once(self):
        with tempfile.TemporaryDirectory() as root:
            serial=Path(root)/'serial.log';display=Display();controller=H.InstallerController(types.SimpleNamespace(proc=Proc()),display,G.context(),root)
            value=dict(schema='arctic-installer-request-v1',kind='vt-away',token=G.context()['token'],boot_id='11111111-1111-1111-1111-111111111111',cycle=0,
                       away=dict(session='1',uid=1000,vt=2,active=False,foreground='tty6'),original_vt=2,engine_sha256='a'*64)
            line=H.REQUEST_PREFIX+json.dumps(value,sort_keys=True)
            serial.write_bytes((line+'\n').encode()[:-3]);self.assertFalse(controller.poll(serial));self.assertEqual(controller.position,0)
            serial.write_bytes((line+'\n').encode())
            with patch.object(controller,'capture',return_value={'path':'away.png'}):self.assertTrue(controller.poll(serial))
            self.assertFalse(controller.poll(serial));self.assertEqual(controller.position,1)
            serial.write_bytes((line+'\n').encode()+b'\xe2\x82');self.assertFalse(controller.poll(serial))

    def test_duplicate_field_unknown_head_and_unbounded_pending_tail_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            serial=Path(root)/'serial.log';controller=H.InstallerController(types.SimpleNamespace(proc=Proc()),Display(),G.context(),root)
            serial.write_bytes(b'x'*16385)
            with self.assertRaises(RuntimeError):controller.poll(serial)
        for text in ('{"cycle":0,"cycle":0}', '{"width":NaN}'):
            with self.assertRaises((RuntimeError,ValueError)):H.strict_json(text)
        for name in ('HEADLESS-1','Virtual-3',None):
            with self.assertRaises(RuntimeError):H.head_for_output(name)

    def test_partial_output_mutation_attempts_both_and_cleanup_restores_both(self):
        with tempfile.TemporaryDirectory() as root:
            display=Display(fail=True);controller=H.InstallerController(types.SimpleNamespace(proc=Proc()),display,G.context(),root)
            with self.assertRaises(RuntimeError):controller.set_heads({1})
            self.assertEqual(len(display.calls),2);self.assertTrue(controller.disconnected);display.fail=False
            receipt=controller.restore();self.assertEqual(receipt['enabled_heads'],[0,1]);self.assertEqual(len(display.calls),4)
            self.assertTrue(controller.failed)

    def test_existing_monitor_cmd_uses_reviewed_absolute_bound_for_input_and_shot(self):
        calls=[]
        display=types.SimpleNamespace(qmp_query=lambda vm,name,args,seconds:calls.append((name,args,seconds)) or {})
        base=types.SimpleNamespace(VM=object);cls=D.owned_vm_type(base,display);vm=object.__new__(cls)
        self.assertEqual(vm.cmd('send-key',keys=['f6']),{'return':{}})
        self.assertEqual(calls,[('send-key',{'keys':['f6']},10)])

    def test_constructor_failure_after_spawn_stops_recorded_child_and_closes_handles(self):
        with tempfile.TemporaryDirectory() as root:
            proc=Proc();sock=Socket(b'{"wrong":"greeting"}\n')
            display=types.SimpleNamespace(defer_signals=contextlib.nullcontext,qmp_query=lambda *args,**kwargs:{})
            cls=D.owned_vm_type(types.SimpleNamespace(VM=object),display)
            with patch.dict(os.environ,OUT=root),patch.object(D.subprocess,'Popen',return_value=proc),patch.object(D.socket,'socket',return_value=sock):
                with self.assertRaises(RuntimeError):cls(['qemu'],str(Path(root)/'qmp.sock'),'fault')
            self.assertFalse(proc.alive);self.assertTrue(sock.closed);self.assertIn('terminate',proc.calls)
            (Path(root)/'qemu-fault.log').rename(Path(root)/'log-closed')

    def test_repeated_signal_during_constructor_failure_still_stops_child_and_closes_socket(self):
        with tempfile.TemporaryDirectory() as root:
            proc=Proc();sock=Socket(b'{"wrong":"greeting"}\n')
            signals=load('installer_constructor_signals',HERE.parent/'native-functional/taskbar-display.py')
            def stop():
                proc.alive=False;proc.calls.append('terminate')
                os.kill(os.getpid(),signal.SIGTERM);os.kill(os.getpid(),signal.SIGINT)
            proc.terminate=stop
            cls=D.owned_vm_type(types.SimpleNamespace(VM=object),signals)
            with patch.dict(os.environ,OUT=root),patch.object(D.subprocess,'Popen',return_value=proc),patch.object(D.socket,'socket',return_value=sock):
                with self.assertRaises(SystemExit):cls(['qemu'],str(Path(root)/'qmp.sock'),'signal-fault')
            self.assertFalse(proc.alive);self.assertTrue(sock.closed);self.assertIn('terminate',proc.calls)

    def test_constructor_success_uses_original_socket_and_closes_every_handle(self):
        with tempfile.TemporaryDirectory() as root:
            proc=Proc();sock=Socket(b'{"QMP":{"version":{}}}\n');calls=[]
            display=types.SimpleNamespace(defer_signals=contextlib.nullcontext,qmp_query=lambda vm,name,args,seconds:calls.append((vm.s,name,seconds)) or {})
            cls=D.owned_vm_type(types.SimpleNamespace(VM=object),display)
            with patch.dict(os.environ,OUT=root),patch.object(D.subprocess,'Popen',return_value=proc),patch.object(D.socket,'socket',return_value=sock):vm=cls(['qemu'],str(Path(root)/'qmp.sock'),'owned')
            self.assertIs(calls[0][0],sock);self.assertEqual(calls[0][1:],('qmp_capabilities',10))
            D.stop_owned(vm,None);vm.close_handles();self.assertTrue(sock.closed);self.assertTrue(sock.stream.closed);self.assertTrue(vm.log.closed)

    def test_host_cleanup_attempts_private_bus_even_when_qemu_termination_raises(self):
        proc=Proc()
        def fail():proc.alive=False;raise KeyboardInterrupt('injected')
        proc.terminate=fail
        display=types.SimpleNamespace(close=lambda:setattr(display,'closed',True),closed=False)
        with self.assertRaises(RuntimeError):D.stop_owned(types.SimpleNamespace(proc=proc),display)
        self.assertTrue(display.closed)

    def test_actual_signal_during_first_write_is_recorded_as_failed_and_handlers_restore(self):
        original=Path.write_text;written=[]
        def interrupted_write(path,data):
            written.append(data)
            if len(written)==1:os.kill(os.getpid(),signal.SIGTERM)
            return original(path,data)
        before=signal.getsignal(signal.SIGTERM)
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'execution.json';state={'status':'passed'};errors=[]
            with H.cleanup_signals() as pending,patch.object(Path,'write_text',interrupted_write):
                H.persist_cleanup_state(path,state,errors,pending)
            self.assertEqual(json.loads(path.read_text())['status'],'failed')
            self.assertEqual(errors,['cancelled during bounded owned cleanup'])
        self.assertEqual(len(written),2);self.assertEqual(signal.getsignal(signal.SIGTERM),before)



if __name__=='__main__':unittest.main()
