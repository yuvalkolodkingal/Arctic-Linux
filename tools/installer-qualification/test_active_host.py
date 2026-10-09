"""Adversarial owned-target and secret-input controls; synthetic, no ISO qualification."""
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


D = load('active_host_driver_controls', HERE/'driver.py')
H = load('active_host_controller_controls', HERE/'controller.py')
G = load('active_host_guest_controls', HERE/'guest.py')
A = load('active_host_active_controls', HERE/'active-guest.py')


def context():
    value = dict(schema='arctic-installer-active-context-v1', source_sha='a'*40, execution_sha='b'*40,
                 binding_id='c'*32, iso_sha256='d'*64, iso_bytes=1900000000,
                 checker_sha256='1'*64, native_sha256='2'*64, runtime_sha256='3'*64, capture_sha256='4'*64,
                 active_checker_sha256='5'*64, installed_checker_sha256='6'*64,
                 disk_serial='arctic-a-'+'1'*11, disk_bytes=64*1024**3, disk_node='target0', write_bps=8*1024**2)
    return value


class Controls(unittest.TestCase):
    def test_active_context_refuses_unowned_serial_wrong_size_and_private_keys(self):
        self.assertEqual(G.validate_context(context()), context())
        for key, value in (('disk_serial','customer-disk'),('disk_serial','arctic-a-'+'1'*32),
                           ('disk_bytes',True),('disk_bytes',128*1024**3),('write_bps',0),('password','secret')):
            changed = context(); changed[key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError):G.validate_context(changed)

    def test_live_target_acquisition_refuses_existing_file_and_symlink_without_truncation(self):
        for link in (False, True):
            with tempfile.TemporaryDirectory() as temporary:
                out = Path(temporary); foreign = out/'foreign'; foreign.write_bytes(b'preserve foreign bytes')
                target = out/'target.qcow2'
                if link:target.symlink_to(foreign)
                else:target.write_bytes(b'preserve existing bytes')
                before = target.read_bytes()
                display = types.SimpleNamespace(display_arg='dbus,addr=unix:path=/tmp/private/bus,gl=off')
                with patch.object(D.shutil,'copyfile'),patch.object(D.subprocess,'run') as create:
                    with self.assertRaises(FileExistsError):D.prepare_vm(display,out,'uefi',context())
                create.assert_not_called();self.assertEqual(target.read_bytes(),before)

    def test_installed_boot_uses_same_target_and_vars_and_removes_live_iso(self):
        with tempfile.TemporaryDirectory() as temporary:
            out=Path(temporary);(out/'target.qcow2').write_bytes(b'owned');(out/'OVMF_VARS.fd').write_bytes(b'owned vars')
            info=json.dumps({'format':'qcow2','virtual-size':context()['disk_bytes']}).encode()
            with patch.object(D.subprocess,'check_output',return_value=info),patch.object(D.shutil,'copyfile') as copy:
                argv=D.prepare_vm(types.SimpleNamespace(display_arg='dbus,addr=unix:path=/tmp/private/bus,gl=off'),out,'uefi',context(),True)
            copy.assert_not_called();self.assertFalse(any('drive=live' in value or 'file=/iso' in value for value in argv))
            self.assertIn('virtio-blk-pci,drive=active_target,serial='+context()['disk_serial']+',bootindex=0',argv)
            self.assertIn('file='+str(out/'target.qcow2')+',if=none,id=active_target,node-name=target0,format=qcow2,bps_wr=8388608',argv)
            self.assertEqual((out/'OVMF_VARS.fd').read_bytes(),b'owned vars')

    def test_installed_boot_rejects_backing_file_or_wrong_size(self):
        with tempfile.TemporaryDirectory() as temporary:
            out=Path(temporary);(out/'target.qcow2').write_bytes(b'owned');(out/'OVMF_VARS.fd').write_bytes(b'owned vars')
            for info in ({'format':'qcow2','virtual-size':64*1024**3,'backing-filename':'/dev/sda'},
                         {'format':'qcow2','virtual-size':8*1024**3}):
                with patch.object(D.subprocess,'check_output',return_value=json.dumps(info).encode()):
                    with self.assertRaises(RuntimeError):D.prepare_vm(types.SimpleNamespace(display_arg='dbus'),out,'uefi',context(),True)

    def test_live_and_installed_refuse_foreign_or_symlinked_variable_store(self):
        for installed in (False, True):
            for exists in (False, True):
                with tempfile.TemporaryDirectory() as temporary:
                    out=Path(temporary);foreign=out/'foreign-vars'
                    if exists:foreign.write_bytes(b'foreign variables must survive')
                    (out/'OVMF_VARS.fd').symlink_to(foreign)
                    with patch.object(D.shutil,'copyfile') as copy:
                        with self.assertRaises(RuntimeError):
                            D.prepare_vm(types.SimpleNamespace(display_arg='dbus'),out,'uefi',context(),installed)
                    copy.assert_not_called()
                    self.assertEqual(foreign.read_bytes() if exists else None,b'foreign variables must survive' if exists else None)
                    self.assertFalse((out/'target.qcow2').exists())

    def test_host_counters_reject_foreign_node_file_or_readonly_disk(self):
        for inserted in ({'node-name':'foreign','file':'/tmp/owned/target.qcow2','ro':False},
                         {'node-name':'target0','file':'/dev/sda','ro':False},
                         {'node-name':'target0','file':'/tmp/owned/target.qcow2','ro':True}):
            controller=object.__new__(H.InstallerController);controller.out=Path('/tmp/owned');controller.context=context();controller.receipts=[]
            controller.vm=object();controller.display=types.SimpleNamespace(_query=lambda *args:[{'inserted':inserted}])
            with self.subTest(inserted=inserted),self.assertRaises(RuntimeError):controller.active_write_proof()

    def test_buffered_real_writes_wait_then_require_growth_and_keep_original_counter(self):
        counters=iter([{'wr_bytes':100,'wr_operations':2},{'wr_bytes':100,'wr_operations':2},{'wr_bytes':500,'wr_operations':3}])
        def query(vm,name,*args):
            if name=='query-block':return [{'inserted':{'node-name':'target0','file':'/tmp/owned/target.qcow2','ro':False}}]
            return [{'node-name':'target0','stats':next(counters)}]
        controller=object.__new__(H.InstallerController);controller.out=Path('/tmp/owned');controller.context=context();controller.receipts=[]
        controller.vm=object();controller.display=types.SimpleNamespace(_query=query)
        with patch.object(H.time,'sleep'):proof=controller.active_write_proof()
        self.assertEqual(proof['before']['wr_bytes'],100);self.assertEqual(proof['after']['wr_bytes'],500)
        self.assertEqual(proof['target_file'],'/tmp/owned/target.qcow2')

    def test_private_account_ipc_failure_never_exports_argv_or_secret(self):
        installer=object.__new__(A.installer_type(G));installer.gui_pid=42;installer.password='a'*32
        installer.assert_gui_identity=lambda:None
        state=dict(page='account',current='account',ready=True,connected=True,busy=False,failure='')
        def command(argv,**kw):
            if argv[-1]=='state':return 0,json.dumps(state),''
            raise RuntimeError('danger '+repr(argv))
        installer.command=command
        payload=dict(full_name='Arctic Qualification',username='arcticqual',hostname='arctic-qual',password='a'*32,
                     confirm='a'*32,autologin=False,same_as_disk=False)
        with self.assertRaises(RuntimeError) as error:installer.ipc('fill',payload)
        self.assertNotIn('a'*32,str(error.exception));self.assertEqual(str(error.exception),'active GUI IPC failed (details withheld)')

    def test_prompt_guard_refuses_private_text_before_archiving(self):
        with tempfile.TemporaryDirectory() as temporary:
            out=Path(temporary);probe=out/'probe.png';probe.write_bytes(b'private screenshot')
            vm=types.SimpleNamespace(alive=lambda:True,shot=lambda label:probe)
            startup=types.SimpleNamespace(console_screen=lambda path:True)
            with patch.object(D.subprocess,'run',return_value=types.SimpleNamespace(stdout=b'a'*32+b'\nPassword:\n')):
                with self.assertRaises(RuntimeError):D.console_prompt(vm,startup,out,'installed-getty-password','Password:','a'*32)
            self.assertFalse((out/'installed-getty-password.png').exists())


if __name__=='__main__':unittest.main()
