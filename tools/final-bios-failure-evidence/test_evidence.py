#!/usr/bin/env python3
"""Source controls with real owned files/children; no VM, image or PAM claim."""
import copy
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock
from PIL import Image,ImageDraw,ImageFont
import evidence as E

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]

def manifest():return json.loads((HERE/'execution-manifest.json').read_bytes())

def modules():
    exact,state=E.build(manifest());old=exact.__globals__['original_evidence'].__globals__
    return exact,state,types.SimpleNamespace(**old)

def context():
    value=json.loads((ROOT/'tools/final-bios-observed-install/execution-manifest.json').read_bytes())
    return {'schema':'arctic-final-bios-context-v1','nonce':'a'*32,'execution_sha':manifest()['base'],
            'source_sha':value['image']['source_sha'],'iso_sha256':value['image']['sha256'],
            'probe_sha256':value['execution_files']['tools/final-bios-install/guest.py'],
            'native_sha256':value['source_files']['tools/native-functional/native_smoke.py'],
            'security_sha256':value['security_binding']['helper_sha256']}

def observer_modules():
    for name in ('observer','composition'):
        path=ROOT/'tools/final-bios-failure-observer'/ (name+'.py')
        m=types.ModuleType('failure_evidence_'+name);m.__file__=str(path)
        if name=='composition':
            previous=sys.modules.get('observer');missing='observer' not in sys.modules
            try:sys.modules['observer']=observer;exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__)
            finally:
                if missing:sys.modules.pop('observer',None)
                else:sys.modules['observer']=previous
        else:
            exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__);observer=m
    source=json.loads((ROOT/'tools/final-bios-failure-observer/execution-manifest.json').read_bytes())
    return observer,m,source

def real_source_cause():
    observer,adapter,source=observer_modules()
    path=ROOT/'tools/final-bios-install/guest.py';raw=path.read_bytes()
    guest=types.ModuleType('bios_failure_evidence_probe');guest.__file__='/run/t/guest-check.py'
    exec(compile(raw,guest.__file__,'exec'),guest.__dict__)
    sites=observer.SourceSites();sites.bind(guest.__dict__,raw,hashlib.sha256(raw).hexdigest(),guest.__file__,'bios-probe')
    rows=[]
    # Explicit synthetic invalid stage short-circuits before any guest command.
    with unittest.TestCase().assertRaisesRegex(RuntimeError,'disposable-root'):
        sites.invoke(guest.main,rows.append,'source-control-invalid-stage',context(),None,None)
    assert len(rows)==1
    value={'schema':'arctic-final-bios-finite-cause-v1','context':context(),'cause':rows[0],'release_acceptance':False}
    return E.PREFIX+json.dumps(value,sort_keys=True).encode()+b'\n',value,adapter,source

def tree(base):
    private=base/'private';private.mkdir(mode=0o700);vm=private/'vm';vm.mkdir(mode=0o700)
    return vm

def put(path,data):path.write_bytes(data);path.chmod(0o600)

def png(text=''):
    image=Image.new('RGB',(640,480),'white')
    if text:
        font=ImageFont.truetype('DejaVuSans.ttf',30)
        ImageDraw.Draw(image).text((20,80),text,fill='black',font=font)
    output=io.BytesIO();image.save(output,format='PNG');return output.getvalue()

class Controls(unittest.TestCase):
    def test_disabled_cli_and_build_release_false(self):
        with self.assertRaisesRegex(SystemExit,'disabled Source'):E.main()
        value=manifest();value['ready']=True
        with self.assertRaises(ValueError):E.build(value)
        self.assertFalse(manifest()['qualification_supplied'])

    def test_exact_original_main_and_unchanged_owned_cleanup(self):
        exact,state,old=modules()
        self.assertIs(exact.__code__,old.main.__code__)
        for name in ('recover_prepared_image','remove_owned_container','harness_environment','original_evidence','argv'):
            if name!='argv':self.assertIs(exact.__globals__[name],getattr(old,name))
        self.assertIs(old.execute.__globals__,old.main.__globals__)
        self.assertEqual(manifest()['install_timeout'],2400)
        self.assertEqual(manifest()['harness_seconds'],6600)

    def test_source_pin_drift_rejects_before_factory(self):
        value=manifest();value['published_execution_files']['tools/final-bios-install/guest.py']='0'*64
        with self.assertRaises(ValueError):E.build(value)

    def test_actual_source_exception_context_and_unknown_negatives(self):
        line,value,adapter,source=real_source_cause()
        self.assertEqual(E.finite_guest(line,context(),source['allowed_sites'],adapter),[value])
        self.assertEqual(value['cause']['site']['fixed_assertion_label'],'disposable-root')
        for mutated in (dict(value,extra='private'),dict(value,context=dict(context(),nonce='b'*32)),
                dict(value,cause=dict(value['cause'],site=dict(value['cause']['site'],source_line=True))),
                dict(value,cause=dict(value['cause'],site=dict(value['cause']['site'],fixed_assertion_label='unknown')))):
            with self.assertRaises(ValueError):E.finite_guest(E.PREFIX+json.dumps(mutated).encode()+b'\n',context(),source['allowed_sites'],adapter)
        self.assertEqual(E.finite_guest(line.rstrip(b'\n'),context(),source['allowed_sites'],adapter),[])
        with self.assertRaises(ValueError):E.finite_guest(line+line,context(),source['allowed_sites'],adapter)

    def test_real_member_owner_mode_link_and_fifo_negatives(self):
        with tempfile.TemporaryDirectory() as td:
            vm=tree(Path(td));path=vm/'serial-boot.log';put(path,b'public control\n')
            self.assertEqual(E.read_original(vm,path.name,128,os.geteuid()),path.read_bytes())
            with self.assertRaises(ValueError):E.read_original(vm,path.name,128,os.geteuid()+1)
            path.chmod(0o622)
            with self.assertRaises(ValueError):E.read_original(vm,path.name,128,os.geteuid())
            path.chmod(0o600);os.link(path,vm/'canary')
            with self.assertRaises(ValueError):E.read_original(vm,path.name,128,os.geteuid())
            (vm/'canary').unlink();path.unlink();os.mkfifo(path,mode=0o600)
            with self.assertRaises(ValueError):E.read_original(vm,path.name,128,os.geteuid())

    def test_real_member_symlink_and_directory_replacement_reject(self):
        with tempfile.TemporaryDirectory() as td:
            vm=tree(Path(td));path=vm/'serial-boot.log';put(path,b'public control\n')
            target=vm/'canary';put(target,b'private fixture');path.unlink();path.symlink_to(target.name)
            with self.assertRaises(OSError):E.read_original(vm,path.name,128,os.geteuid())
            path.unlink();put(path,b'public control\n');saved=os.read;swapped=False
            def read(fd,size):
                nonlocal swapped
                value=saved(fd,size)
                if value and not swapped:
                    swapped=True;vm.rename(vm.with_name('vm-detached'));vm.mkdir(mode=0o700)
                    put(vm/'serial-boot.log',b'public substitute\n')
                return value
            with mock.patch.object(os,'read',read):
                with self.assertRaises(ValueError):E.read_original(vm,path.name,128,os.geteuid())

    def test_actual_signal_during_fd_acquisition_closes_all_owned_fds(self):
        worker='''import os,signal,tempfile\nfrom pathlib import Path\nimport evidence as E\nwith tempfile.TemporaryDirectory() as td:\n b=Path(td);(b/'private').mkdir(mode=0o700);v=b/'private/vm';v.mkdir(mode=0o700);p=v/'serial-boot.log';p.write_bytes(b'public fixture\\n');p.chmod(0o600)\n before=set(os.listdir('/proc/self/fd'));real=os.open\n def acquire(path,*a,**k):\n  fd=real(path,*a,**k)\n  if path=='serial-boot.log':os.kill(os.getpid(),signal.SIGINT)\n  return fd\n E.os.open=acquire\n try:E.read_original(v,p.name,128,os.geteuid())\n except KeyboardInterrupt:pass\n else:raise AssertionError('signal not delivered')\n assert set(os.listdir('/proc/self/fd'))==before\n print('owned-acquisition-signal-all-fds-closed')\n'''
        result=subprocess.run([sys.executable,'-B','-c',worker],cwd=HERE,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout,b'owned-acquisition-signal-all-fds-closed\n')

    def test_same_inode_generation_change_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            vm=tree(Path(td));path=vm/'serial-boot.log';put(path,b'public control\n');saved=os.read;changed=False
            def read(fd,size):
                nonlocal changed
                value=saved(fd,size)
                if value and not changed:changed=True;path.write_bytes(b'public replacement\n')
                return value
            with mock.patch.object(os,'read',read):
                with self.assertRaises(ValueError):E.read_original(vm,path.name,128,os.geteuid())

    def test_failed_linux_close_never_retries_reused_foreign_fd(self):
        import errno
        with tempfile.TemporaryDirectory() as td:
            a=Path(td)/'owned';b=Path(td)/'foreign';put(a,b'owned');put(b,b'foreign')
            fd=os.open(a,os.O_RDONLY);real=os.close
            def fail_closed(value):
                real(value);raise OSError(errno.EIO,'synthetic already-closed fault')
            with mock.patch.object(os,'close',fail_closed):E.close_owned(fd)
            with self.assertRaises(OSError):os.fstat(fd)
            fd=os.open(a,os.O_RDONLY);canary=[]
            def reused(value):
                real(value);replacement=os.open(b,os.O_RDONLY);self.assertEqual(replacement,value)
                canary.append(replacement);raise OSError(errno.EIO,'synthetic already-closed fault')
            try:
                with mock.patch.object(os,'close',reused):E.close_owned(fd)
                self.assertEqual(os.read(canary[0],7),b'foreign')
            finally:
                for value in canary:real(value)

    def test_retained_holder_pending_open_replacement_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            vm=tree(Path(td));path=vm/'serial-boot.log';put(path,b'public Source control\n')
            holder=vm.parent/'failed-originals';holder.mkdir(mode=0o700)
            saved=os.open;swapped=False;before=set(os.listdir('/proc/self/fd'))
            def opened(name,*args,**kwargs):
                nonlocal swapped
                descriptor=saved(name,*args,**kwargs)
                if name=='serial-boot.log.pending' and not swapped:
                    swapped=True;holder.rename(holder.with_name('failed-originals-detached'));holder.mkdir(mode=0o700)
                return descriptor
            with mock.patch.object(os,'open',opened):
                with self.assertRaises(ValueError):E.read_original(vm,path.name,128,os.geteuid(),retain=True)
            self.assertFalse((holder/path.name).exists())
            self.assertEqual(set(os.listdir('/proc/self/fd')),before)

    def test_retained_final_name_collision_never_overwrites_canary(self):
        with tempfile.TemporaryDirectory() as td:
            vm=tree(Path(td));path=vm/'serial-boot.log';put(path,b'public Source control\n')
            holder=vm.parent/'failed-originals';holder.mkdir(mode=0o700);canary=holder/path.name;put(canary,b'owned canary')
            before=set(os.listdir('/proc/self/fd'))
            with self.assertRaises(FileExistsError):E.read_original(vm,path.name,128,os.geteuid(),retain=True)
            self.assertEqual(canary.read_bytes(),b'owned canary');self.assertEqual(set(os.listdir('/proc/self/fd')),before)

    def test_snapshot_holder_replaced_between_members_rejects_complete_snapshot(self):
        _,_,old=modules();line,_,adapter,source=real_source_cause()
        scanner=old.C.load(ROOT/'tools/native-functional/screen-evidence.py','bios_holder_race_screen',manifest()['published_execution_files']['tools/native-functional/screen-evidence.py'])
        with tempfile.TemporaryDirectory() as td:
            vm=tree(Path(td));put(vm/'serial-install.log',b'public Source control\n');put(vm/'serial-boot.log',line)
            swapped=False
            def screened(raw):
                nonlocal swapped
                result=scanner.external_text(raw)
                if not swapped:
                    swapped=True;holder=vm.parent/'failed-originals';holder.rename(holder.with_name('failed-originals-detached'));holder.mkdir(mode=0o700)
                return result
            before=set(os.listdir('/proc/self/fd'))
            with self.assertRaises(ValueError):E.snapshot(vm,context(),old,types.SimpleNamespace(external_text=screened),source['allowed_sites'],adapter)
            self.assertEqual(set(os.listdir('/proc/self/fd')),before)

    def test_actual_holder_acquisition_signal_restores_only_after_fd_cleanup(self):
        worker='''import os,signal,tempfile\nfrom pathlib import Path\nimport evidence as E\nwith tempfile.TemporaryDirectory() as td:\n p=Path(td)/'holder';p.mkdir(mode=0o700);before=set(os.listdir('/proc/self/fd'));real=os.open\n def acquire(path,*a,**k):\n  fd=real(path,*a,**k)\n  if path==p:os.kill(os.getpid(),signal.SIGINT)\n  return fd\n E.os.open=acquire\n try:\n  with E.snapshot_directory(p):pass\n except KeyboardInterrupt:pass\n else:raise AssertionError('signal not delivered')\n assert set(os.listdir('/proc/self/fd'))==before\n assert signal.pthread_sigmask(signal.SIG_BLOCK,set())==set()\n print('holder-signal-all-fds-closed-mask-restored')\n'''
        result=subprocess.run([sys.executable,'-B','-c',worker],cwd=HERE,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout,b'holder-signal-all-fds-closed-mask-restored\n')

    def test_real_ocr_safe_original_and_private_rejection(self):
        _,_,old=modules();line,_,adapter,source=real_source_cause()
        scanner=old.C.load(ROOT/'tools/native-functional/screen-evidence.py','bios_evidence_test_screen',manifest()['published_execution_files']['tools/native-functional/screen-evidence.py'])
        with tempfile.TemporaryDirectory() as td:
            vm=tree(Path(td));put(vm/'serial-install.log',b'public control\n');put(vm/'serial-boot.log',line)
            safe=png('BIOS source control');unsafe=png('password: privatefixture')
            put(vm/E.PNGS[0],safe);put(vm/E.PNGS[1],unsafe)
            files,finite=E.snapshot(vm,context(),old,scanner,source['allowed_sites'],adapter)
            self.assertEqual(files[E.PNGS[0]],safe);self.assertNotIn(E.PNGS[1],files)
            self.assertEqual(finite['member_status'][E.PNGS[1]],'png-or-ocr-rejected')
            self.assertEqual(gzip.decompress(files['serial-boot.log.gz']),line)
            self.assertEqual((vm.parent/'failed-originals'/E.PNGS[1]).read_bytes(),unsafe)

    def test_rejected_uart_still_projects_only_closed_source_record(self):
        _,_,old=modules();line,value,adapter,source=real_source_cause()
        scanner=old.C.load(ROOT/'tools/native-functional/screen-evidence.py','bios_evidence_test_screen2',manifest()['published_execution_files']['tools/native-functional/screen-evidence.py'])
        with tempfile.TemporaryDirectory() as td:
            vm=tree(Path(td));original=b'password: privatefixture\n'+line;put(vm/'serial-boot.log',original)
            files,finite=E.snapshot(vm,context(),old,scanner,source['allowed_sites'],adapter)
            self.assertNotIn('serial-boot.log.gz',files)
            self.assertEqual(finite['member_status']['serial-boot.log'],'privacy-rejected')
            self.assertEqual(finite['guest_source_causes']['installed'],[value])
            self.assertNotIn('privatefixture',json.dumps(finite))
            self.assertEqual((vm.parent/'failed-originals/serial-boot.log').read_bytes(),original)

    def test_failure_adapter_same_primary_snapshot_before_cleanup_success_bytes(self):
        built,_,old=modules();line,_,adapter,source=real_source_cause()
        scanner=old.C.load(ROOT/'tools/native-functional/screen-evidence.py','bios_evidence_test_screen3',manifest()['published_execution_files']['tools/native-functional/screen-evidence.py'])
        events=[];primary=RuntimeError('private fixture primary')
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);vm=tree(base);put(vm/'serial-boot.log',line)
            dependencies=built.__globals__.copy()
            def failed(*args):events.append('unchanged-execute-returned-primary');raise primary
            dependencies['execute']=failed
            dependencies['compose']=types.SimpleNamespace(compose=lambda *args:'original-guest-sha')
            dependencies['publish']=lambda out,files:events.append(('publish',files))
            exact=types.FunctionType(old.main.__code__,dependencies)
            wrapped,state=E.attach(exact,old,{'shell':Path('/fixed/source-shell')},source,adapter,scanner)
            d=wrapped.__globals__;ctx=context()
            self.assertEqual(d['compose'].compose(None,None,None,ctx,None),'original-guest-sha')
            try:d['execute'](['bash','/fixed/source-shell','--out',str(vm)],base/'private/harness.log',6600,None,{})
            except BaseException as error:self.assertIs(error,primary)
            else:self.fail('primary was lost')
            events.append('original-main-cleanup')
            self.assertTrue((base/'private/failed-originals/serial-boot.log').is_file())
            self.assertEqual(events[:2],['unchanged-execute-returned-primary','original-main-cleanup'])
            passed=b'{"status":"passed_pending_original_image_review"}\n'
            d['publish'](base,{'host-status.json':passed})
            self.assertEqual(events[-1],('publish',{'host-status.json':passed}))
            failed_status=b'{"status":"failed","release_acceptance":false}\n'
            d['publish'](base,{'host-status.json':failed_status})
            sent=events[-1][1];self.assertIn('serial-boot.log.gz',sent)
            status=json.loads(sent['host-status.json']);self.assertFalse(status['strict_failed_originals']['qualification_supplied'])

    def test_exact_shell_inverse_and_no_unscreened_failed_tail(self):
        _,_,old=modules();source=(ROOT/'tools/test-install.sh').read_bytes()
        staged=source.replace(b'python3 -c "$DRIVER" || rc=$?',b'python3 /arctic-lib/driver-entry.py || rc=$?',1)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'test-install.sh';put(path,staged)
            E.private_failure_tail(path,source,old);changed=path.read_bytes()
            self.assertNotIn(E.FAILED_TAIL,changed)
            self.assertEqual(changed.replace(E.PRIVATE_TAIL,E.FAILED_TAIL,1),staged)
            marker=b"read -r -d '' DRIVER <<'PY' || true\n"
            def driver(raw):
                start=raw.index(marker)+len(marker);return raw[start:raw.index(b'\nPY\n',start)]
            self.assertEqual(driver(changed),driver(source))
            with self.assertRaises(ValueError):E.private_failure_tail(path,source,old)

    def test_real_original_execute_main_cleanup_and_strict_failure_publication(self):
        exact,state,old=modules();task='a'*32;image='sha256:'+'b'*64;events=[]
        line,guest_value,_,_=real_source_cause()
        source_raw=subprocess.check_output(['git','-C',str(ROOT),'show',
            '326690f173d4dc4f049f43e046c8380e66825a07:tools/native-functional/native_smoke.py'])
        original_popen=subprocess.Popen;original_run=subprocess.run;original_check=subprocess.check_output
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);source=base/'source';(source/'tools/native-functional').mkdir(parents=True)
            (source/'tools/native-functional/native_smoke.py').write_bytes(source_raw)
            inputs=base/'inputs';inputs.mkdir();out=base/'evidence'
            deps=exact.__globals__;deps['uuid']=types.SimpleNamespace(uuid4=lambda:types.SimpleNamespace(hex=task))
            deps['Path']=lambda path:types.SimpleNamespace(is_char_device=lambda:True) if path=='/dev/kvm' else Path(path)
            deps['C'].guard=lambda *a,**k:None # Explicit synthetic hosted-admission metadata.
            def spawn(argv,**kwargs):
                if argv[0]!='bash':return original_popen(argv,**kwargs)
                if argv[1].endswith('prepare-vm-tools.sh'):
                    code='from pathlib import Path;Path('+repr(str(out/'private/vm-prepared-image-id.txt'))+').write_text('+repr(image)+'+"\\n")'
                else:
                    value=dict(guest_value,context=state['context'])
                    boot=E.PREFIX+json.dumps(value,sort_keys=True).encode()+b'\npassword: privatefixture\n'
                    contents={'serial-install.log':b'public Source control\n','serial-boot.log':boot,E.PNGS[0]:png('BIOS Source control')}
                    code='from pathlib import Path;v=Path('+repr(str(out/'private/vm'))+');v.mkdir(mode=0o700)\n'
                    for name,raw in contents.items():code+='p=v/'+repr(name)+';p.write_bytes('+repr(raw)+');p.chmod(0o600)\n'
                    code+='raise SystemExit(23)\n'
                return original_popen([sys.executable,'-B','-c',code],**kwargs)
            def metadata(argv,**kwargs):
                if argv[0]!='docker':return original_run(argv,**kwargs)
                if argv[:3]==['docker','container','inspect']:
                    self.assertTrue((out/'private/failed-originals/serial-boot.log').is_file())
                    events.append('owned-container-cleanup-after-snapshot')
                    row={'Name':'/'+argv[-1],'Image':image,'Id':'c'*64,'Mounts':[{'Source':str(out/'private/vm'),'Destination':str(out/'private/vm')}]}
                    return types.SimpleNamespace(returncode=0,stdout=json.dumps([row]).encode())
                if argv[:2] in (['docker','rm'],['docker','image']):
                    events.append('owned-cleanup');return types.SimpleNamespace(returncode=0,stdout=b'')
                raise AssertionError('Unexpected synthetic owned metadata')
            def inspected(argv,**kwargs):
                if argv[:3]==['docker','image','inspect']:
                    return json.dumps({'org.arctic.test.vm-tools.task':task,'org.arctic.test.vm-tools.container':'arctic-paired-'+task+'-'+task[:8],'org.arctic.test.vm-tools.scope':'paired-v1'}).encode()
                return original_check(argv,**kwargs)
            with mock.patch.object(subprocess,'Popen',spawn),mock.patch.object(subprocess,'run',metadata),mock.patch.object(subprocess,'check_output',inspected),mock.patch.object(sys,'argv',['Source-control','--source',str(source),'--inputs',str(inputs),'--out',str(out)]):
                self.assertEqual(exact(),1)
            status=json.loads((out/'public/host-status.json').read_bytes())
            self.assertEqual(status['status'],'failed');self.assertEqual(status['phase'],'install-and-boot')
            self.assertFalse(status['complete_UART_published']);self.assertFalse(status['release_acceptance'])
            self.assertIsNone(status['result'])
            finite=status['strict_failed_originals'];self.assertEqual(finite['member_status']['serial-boot.log'],'privacy-rejected')
            self.assertEqual(finite['guest_source_causes']['installed'][0]['cause']['site']['fixed_assertion_label'],'disposable-root')
            self.assertEqual(set(p.name for p in (out/'public').iterdir()),{'host-status.json','serial-install.log.gz',E.PNGS[0]})
            self.assertNotIn('privatefixture',json.dumps(status));self.assertEqual(events.count('owned-cleanup'),2)
            self.assertEqual((out/'private/failed-originals/serial-boot.log').stat().st_mode&0o777,0o600)

if __name__=='__main__':unittest.main()
