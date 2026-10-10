"""Kernel ABI fixtures bind real sysfs graphs; no guest, engine or network."""
import ast
import contextlib
import importlib.util
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import test_target_diagnostics as T
G = T.G


class SysfsFixture:
    def __init__(self, root):
        self.root, self.proc, self.sys = root, root/'proc', root/'sys'
        self.session = 'synthetic-live'
        self.uid = os.getuid()
        self.sys_devices = self.sys/'devices'
        self.pci = self.sys_devices/'pci0000:00/0000:00:03.0'
        self.child = self.pci/'virtio2'
        self.card = self.pci/'drm/card1'
        self.render = self.pci/'drm/renderD129'
        for directory in (self.sys/'class/drm',self.sys/'dev/char',self.child,self.card,self.render,
                self.sys/'bus/pci/drivers/virtio-pci',self.sys/'bus/virtio/drivers/virtio_gpu',self.proc/'42/fd'):
            directory.mkdir(parents=True,exist_ok=True)
        (self.pci/'vendor').write_text('0x1af4\n');(self.pci/'device').write_text('0x1050\n')
        (self.pci/'driver').symlink_to(self.sys/'bus/pci/drivers/virtio-pci')
        (self.child/'driver').symlink_to(self.sys/'bus/virtio/drivers/virtio_gpu')
        (self.child/'device').write_text('0x0010\n')
        for node,number in ((self.card,'226:1'),(self.render,'226:129')):
            (node/'dev').write_text(number+'\n');(node/'device').symlink_to(self.pci)
            (self.sys/'class/drm'/node.name).symlink_to(node)
            (self.sys/'dev/char'/number).symlink_to(node)
        for index in (1,2):
            connector=self.card/(self.card.name+'-Virtual-'+str(index));connector.mkdir()
            (connector/'connector_id').write_text(str(100+index)+'\n')
            (self.sys/'class/drm'/connector.name).symlink_to(connector)
        # A second actual card is present but is not the compositor's device.
        other=self.sys_devices/'platform/simple-framebuffer';other.mkdir(parents=True)
        other_card=other/'drm/card0';other_card.mkdir(parents=True)
        (other_card/'device').symlink_to(other)
        (self.sys/'class/drm/card0').symlink_to(other_card)
        (self.proc/'42/comm').write_text('mango\n')
        self.fd_numbers={4:os.makedev(226,1),5:os.makedev(226,129),6:os.makedev(1,3)}
        for number in self.fd_numbers:(self.proc/'42/fd'/str(number)).write_bytes(b'synthetic descriptor')
        self.proof_calls=0;self.changed=False;self.proof_session=self.session;self.descriptor_error=None

    def proof(self,pid,uid,executable,proc_root):
        assert pid==42 and uid==self.uid and executable=='/usr/bin/mango' and proc_root==self.proc
        self.proof_calls+=1
        return dict(pid=42,start_ticks=2 if self.changed and self.proof_calls>1 else 1),dict(XDG_SESSION_ID=self.proof_session)

    @contextlib.contextmanager
    def intercepted(self,heads=False):
        actual_stat=Path.stat
        actual_path=Path
        helper=G.mango_drm_devices
        def descriptor_stat(path,*args,**kwargs):
            if path.parent==self.proc/'42/fd' and path.name.isdigit():
                if path.name=='6' and self.descriptor_error is not None:raise self.descriptor_error
                return SimpleNamespace(st_mode=stat.S_IFCHR|0o600,st_rdev=self.fd_numbers[int(path.name)])
            return actual_stat(path,*args,**kwargs)
        def path(value):
            text=str(value)
            return self.sys/text[5:] if text.startswith('/sys/') else actual_path(value)
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(Path,'stat',descriptor_stat))
            stack.enter_context(patch.object(G,'process_proof',self.proof))
            if heads:
                stack.enter_context(patch.object(G,'Path',path))
                stack.enter_context(patch.object(G,'mango_drm_devices',lambda uid,session: helper(uid,session,self.proc,self.sys)))
            yield

    def devices(self):
        with self.intercepted():return G.mango_drm_devices(self.uid,self.session,self.proc,self.sys)

    def heads(self):
        value=G.Installer.__new__(G.Installer);value.uid=self.uid;value.session=self.session
        with self.intercepted(heads=True):return value.drm_heads()


class AbiControls(unittest.TestCase):
    def test_kernel_pci_parent_and_virtio_child_bind_the_actual_mango_fds(self):
        for extra_card in (False,True):
            with self.subTest(extra_card=extra_card),tempfile.TemporaryDirectory() as temp:
                fixture=SysfsFixture(Path(temp))
                if not extra_card:(fixture.sys/'class/drm/card0').unlink()
                self.assertEqual(fixture.devices(),{fixture.pci})
                heads=fixture.heads()
                self.assertEqual(heads['card'],'card1')
                self.assertEqual(heads['device'],str(fixture.pci))
                self.assertEqual(heads['driver'],str(fixture.sys/'bus/virtio/drivers/virtio_gpu'))
                self.assertEqual(heads['pci_address'],'0000:00:03.0')
                self.assertEqual(heads['pci_vendor'],'0x1af4');self.assertEqual(heads['pci_device'],'0x1050')
                self.assertEqual([heads['outputs']['Virtual-'+str(n)]['head'] for n in (1,2)],[0,1])

    def test_primary_only_compositor_and_duplicate_descriptor_are_valid(self):
        for render in (False,True):
            with self.subTest(render=render),tempfile.TemporaryDirectory() as temp:
                fixture=SysfsFixture(Path(temp))
                fixture.fd_numbers[5]=os.makedev(226,129 if render else 1)
                self.assertEqual(fixture.devices(),{fixture.pci})

    def test_closed_unrelated_descriptor_race_is_narrow_and_other_errors_are_fatal(self):
        for error in (FileNotFoundError('synthetic closed fd'),ProcessLookupError('synthetic exited fd'),OSError(5,'private fd error')):
            with self.subTest(kind=type(error).__name__),tempfile.TemporaryDirectory() as temp:
                fixture=SysfsFixture(Path(temp));fixture.descriptor_error=error
                if type(error) in (FileNotFoundError,ProcessLookupError):
                    self.assertEqual(fixture.devices(),{fixture.pci})
                else:
                    with self.assertRaises(OSError) as caught:fixture.devices()
                    self.assertIs(caught.exception,error)

    def test_missing_ambiguous_and_wrong_session_compositor_are_rejected(self):
        for kind in ('missing','ambiguous','session'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp:
                fixture=SysfsFixture(Path(temp))
                if kind=='missing':(fixture.proc/'42/comm').write_text('other\n')
                elif kind=='ambiguous':
                    (fixture.proc/'43').mkdir();(fixture.proc/'43/comm').write_text('mango\n')
                    original=fixture.proof
                    fixture.proof=lambda pid,*args: (dict(pid=pid,start_ticks=1),dict(XDG_SESSION_ID=fixture.session)) if pid==43 else original(pid,*args)
                else:fixture.proof_session='other'
                with self.assertRaisesRegex(RuntimeError,'Mango DRM process'):fixture.devices()

    def test_fd_backlink_unknown_node_render_only_and_changed_process_fail_closed(self):
        for kind in ('backlink','unknown-node','render-only','changed'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp:
                fixture=SysfsFixture(Path(temp))
                if kind=='backlink':(fixture.card/'dev').write_text('226:9\n')
                elif kind=='unknown-node':
                    link=fixture.sys/'dev/char/226:1';link.unlink();link.symlink_to(fixture.child)
                elif kind=='render-only':fixture.fd_numbers[4]=os.makedev(226,129)
                else:fixture.changed=True
                with self.assertRaises(RuntimeError):fixture.devices()

    def test_every_original_pci_child_connector_guard_remains_closed(self):
        for kind in ('vendor','pci-id','transport','child-driver','child-id','duplicate-child','missing-connector','foreign-connector'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp:
                fixture=SysfsFixture(Path(temp))
                if kind=='vendor':(fixture.pci/'vendor').write_text('0x1234\n')
                elif kind=='pci-id':(fixture.pci/'device').write_text('0x1042\n')
                elif kind=='transport':
                    p=fixture.pci/'driver';p.unlink();p.symlink_to(fixture.sys/'bus/virtio/drivers/virtio_gpu')
                elif kind=='child-driver':
                    p=fixture.child/'driver';p.unlink();p.symlink_to(fixture.sys/'bus/pci/drivers/virtio-pci')
                elif kind=='child-id':(fixture.child/'device').write_text('0x0002\n')
                elif kind=='duplicate-child':
                    p=fixture.pci/'virtio3';p.mkdir();(p/'driver').symlink_to(fixture.sys/'bus/virtio/drivers/virtio_gpu')
                elif kind=='missing-connector':(fixture.sys/'class/drm/card1-Virtual-2').unlink()
                else:
                    p=fixture.sys/'class/drm/card1-Virtual-2';p.unlink();p.symlink_to(fixture.render)
                with self.assertRaises((RuntimeError,FileNotFoundError)):fixture.heads()

    def test_optical_serial_enxio_is_never_read_and_owned_serial_stays_required(self):
        for nodes in (['sr0','vda'],['vda','sr0']):
            with self.subTest(nodes=nodes),tempfile.TemporaryDirectory() as temp:
                value=T.TargetControls().instance(Path(temp))
                model=T.TargetModel(self,value,override=dict(nodes=nodes,foreign_serial_error=OSError(6,T.PRIVATE)))
                value.command=model.command
                with patch.object(T.A,'Path',model.path):result=value.target_disk(pristine=True)
                self.assertEqual(result['serial'],'ARCTIC-OWNED-TARGET')
                self.assertEqual(model.trace.count('target-serial'),1)

    def test_owned_supported_serial_enxio_is_fatal_and_foreign_disk_cannot_pass(self):
        for kind in ('owned-enxio','foreign-disk'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp:
                value=T.TargetControls().instance(Path(temp))
                kwargs=dict(fail='target-serial',error=OSError(6,T.PRIVATE)) if kind=='owned-enxio' else dict(
                    override=dict(nodes=['sr0','vda'],disks=[dict(name='vda',type='disk'),dict(name='sda',type='disk')]))
                model=T.TargetModel(self,value,**kwargs);value.command=model.command
                with patch.object(T.A,'Path',model.path),self.assertRaises(OSError if kind=='owned-enxio' else RuntimeError):
                    value.target_disk(pristine=True)

    def test_installed_target_serial_uses_supported_block_abi_and_fails_closed(self):
        checker=Path(__file__).with_name('installed-guest.py')
        spec=importlib.util.spec_from_file_location('installed_abi_checked',checker)
        installed=importlib.util.module_from_spec(spec);spec.loader.exec_module(installed)
        main=next(n for n in ast.parse(checker.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='main')
        index=next(i for i,n in enumerate(main.body) if isinstance(n,ast.Assign)
                   and any(isinstance(x,ast.Name) and x.id=='serial' for x in n.targets))
        # Execute the actual driver/serial/security guard region, not a mirror.
        guard=compile(ast.Module(body=main.body[index-1:index+2],type_ignores=[]),str(checker),'exec')
        for kind in ('valid','wrong-driver','missing-driver','legacy-only','wrong-block-serial',
                     'owned-enxio','owned-hostile-error','permissive-security'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);block=root/'sys/class/block/vda';device=block/'device';device.mkdir(parents=True)
                driver=root/'sys/bus/virtio/drivers'/('other' if kind=='wrong-driver' else 'virtio_blk')
                driver.mkdir(parents=True)
                if kind!='missing-driver':(device/'driver').symlink_to(driver)
                (device/'serial').write_text('ARCTIC-OWNED-TARGET\n')
                if kind!='legacy-only':(block/'serial').write_text('other\n' if kind=='wrong-block-serial' else 'ARCTIC-OWNED-TARGET\n')
                commands=[];reads=[];actual_read=Path.read_text
                error=OSError(6,T.PRIVATE) if kind=='owned-enxio' else T.HostileOSError(T.PRIVATE)
                def path(value):
                    return root/str(value).lstrip('/')
                def read(value,*args,**kwargs):
                    reads.append(value)
                    if value==block/'serial' and kind in ('owned-enxio','owned-hostile-error'):raise error
                    return actual_read(value,*args,**kwargs)
                def command(argv):
                    commands.append(argv);self.assertEqual(argv,['getenforce'])
                    return 'Permissive' if kind=='permissive-security' else 'Enforcing'
                env=dict(Path=path,require=installed.require,context=dict(disk_serial='ARCTIC-OWNED-TARGET'),command=command)
                with patch.object(Path,'read_text',read):
                    if kind=='valid':
                        exec(guard,env);self.assertEqual(env['serial'],'ARCTIC-OWNED-TARGET')
                    else:
                        expected=FileNotFoundError if kind in ('missing-driver','legacy-only') else OSError if kind in ('owned-enxio','owned-hostile-error') else RuntimeError
                        with self.assertRaises(expected) as caught:exec(guard,env)
                        if kind in ('owned-enxio','owned-hostile-error'):self.assertIs(caught.exception,error)
                self.assertNotIn(device/'serial',reads)
                if kind in ('wrong-driver','missing-driver'):
                    self.assertEqual(reads,[]);self.assertEqual(commands,[])


if __name__=='__main__':unittest.main()
