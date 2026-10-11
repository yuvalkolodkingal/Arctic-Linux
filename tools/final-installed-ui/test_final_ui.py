#!/usr/bin/env python3
"""Source controls only: labelled transport/process/UI adapters, no VM claim."""
import base64
import contextlib
import copy
import gzip
import hashlib
import io
import inspect
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zlib

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import common as C
import guest as G
import compose
import run


def context():
    return dict(schema='arctic-final-installed-ui-context-v1',nonce='a'*32,execution_sha='b'*40,
        source_sha='326690f173d4dc4f049f43e046c8380e66825a07',
        iso_sha256='807eaaa64ab8480ec2b18bc8434fd5e37d82c41b73a3e0a6f002c35d152ba54c',
        native_sha256='c'*64,ui_sha256='d'*64)


def checks():
    return [dict(check='winner-keyboard-ui-selection',status='passed',master_sha256=G.WINNER_SHA,catalog_photos=19),
        dict(check='custom-choice-survives-mode-change',status='passed'),
        dict(check='remove-apps-routing-and-read-only-preview',status='passed',preview_packages=1,
            transaction_committed=False,original_ui_review_required=True),
        dict(check='genuine-update-indicator-observation',status='observed',ready=False,staged_packages=0,
            signed_stage_and_cleared_reboot_proven=False),
        dict(check='production-lock-clock-and-pam',status='passed',secure=True,expected_clock_before='12:59',
            expected_clock_after='13:00',original_clock_visual_review_required=True,
            authenticated_by_existing_host_fixture=True)]


class FinalUI(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='arctic-ui-source-controls-')
        self.root=Path(self.temp.name)
        self.scanner=C.load(C.ROOT/'tools/native-functional/screen-evidence.py','ui_actual_source_scanner')
    def tearDown(self): self.temp.cleanup()

    def wire(self,passed=True):
        from PIL import Image
        probe=object.__new__(G.Probe); probe.context=context(); probe.checks=checks() if passed else []
        probe.captures=[]
        for i,name in enumerate(G.PNG_NAMES if passed else G.PNG_NAMES[:2]):
            path=self.root/name;Image.new('RGB',(640,480),(i,30,70)).save(path);probe.captures.append(path)
        stream=io.StringIO()
        with patch.object(G,'result',return_value='Enforcing'),contextlib.redirect_stdout(stream):
            probe.export('passed' if passed else 'failed','complete' if passed else 'winner',
                         'none' if passed else 'RuntimeError')
        return stream.getvalue().encode()

    def test_disabled_manifest_pins_and_exact_image(self):
        value=C.strict_json((HERE/'execution-manifest.json').read_bytes())
        C.manifest(value);self.assertFalse(value['release_acceptance'])
        for path,sha in value['execution_files'].items():self.assertEqual(C.digest_file(C.ROOT/path),sha,path)
        disabled=copy.deepcopy(value);disabled['ready']=False
        with self.assertRaises(RuntimeError):C.manifest(disabled,True)
        operational=copy.deepcopy(value);operational['ready']=True;C.manifest(operational,True)
        for key,new in (('bytes',2000000000),('run_id',True),('source_sha','e'*40),('producer_mode','legacy')):
            wrong=copy.deepcopy(value);wrong['image'][key]=new
            with self.subTest(key=key),self.assertRaises(RuntimeError):C.manifest(wrong)

    def test_context_rejects_paths_identity_and_extra_data(self):
        G.validate_context(context())
        for key,new in (('nonce','../foreign'),('source_sha','e'*40),('iso_sha256','e'*64),
                        ('execution_sha',False),('ui_sha256','e'*63)):
            value=context();value[key]=new
            with self.subTest(key=key),self.assertRaises(RuntimeError):G.validate_context(value)
        value=context();value['transcript']='private'
        with self.assertRaises(RuntimeError):G.validate_context(value)

    def test_actual_exporter_roundtrip_all_fourteen_pngs(self):
        wire=self.wire();value,inventory=C.decode(wire,context(),self.scanner,self.root/'decoded')
        self.assertEqual(value['checks'],checks());self.assertEqual(len(inventory),15)
        for name in G.PNG_NAMES:self.assertEqual((self.root/name).read_bytes(),(self.root/'decoded'/name).read_bytes())

    def test_partial_failed_originals_remain_failed(self):
        value,inventory=C.decode(self.wire(False),context(),self.scanner,self.root/'failed-originals')
        self.assertEqual(value['status'],'failed');self.assertEqual(len(inventory),3)
        self.assertFalse(value['release_acceptance'])

    def test_whole_uart_privacy_rejects_preceding_private_record(self):
        wire=b'transcript: private source control\n'+self.wire()
        with self.assertRaises(RuntimeError):C.decode(wire,context(),self.scanner,self.root/'rejected')
        self.assertFalse((self.root/'rejected').exists())

    def test_missing_duplicate_foreign_and_extra_transport_reject(self):
        wire=self.wire();lines=wire.decode().splitlines()
        variants=[lines[:-1],lines+[lines[-1]],
            [line.replace('"nonce": "'+'a'*32+'"','"nonce": "'+'f'*32+'"') for line in lines],
            lines+['ARCTIC-FINAL-UI-UNKNOWN {}'],
            lines+[next(line for line in lines if line.startswith('ARCTIC-FINAL-UI-CHUNK '))]]
        for i,rows in enumerate(variants):
            path=self.root/('reject-'+str(i))
            with self.subTest(i=i),self.assertRaises((RuntimeError,ValueError)):C.decode(
                ('\n'.join(rows)+'\n').encode(),context(),self.scanner,path)
            self.assertFalse(path.exists())

    def test_hash_expansion_extra_compressed_stream_and_path_reject(self):
        wire=self.wire();rows=wire.decode().splitlines()
        index=next(i for i,row in enumerate(rows) if row.startswith('ARCTIC-FINAL-UI-MANIFEST '))
        original=json.loads(rows[index].split(' ',1)[1])
        for role,mutate in [('hash',lambda v:v[0].update(sha256='f'*64)),
            ('expanded',lambda v:v[0].update(bytes=1)),('path',lambda v:v[0].update(name='../report.json')),
            ('duplicate',lambda v:v.append(copy.deepcopy(v[0])))]:
            inventory=copy.deepcopy(original);mutate(inventory);changed=rows[:]
            changed[index]='ARCTIC-FINAL-UI-MANIFEST '+json.dumps(inventory)
            with self.subTest(role=role),self.assertRaises(RuntimeError):C.decode(
                ('\n'.join(changed)+'\n').encode(),context(),self.scanner,self.root/role)

    def test_report_requires_real_claim_boundaries_and_clock_transition(self):
        value=dict(schema='arctic-final-installed-ui-report-v1',context=context(),status='passed',phase='complete',
            error_class='none',checks=checks(),selinux='Enforcing',visual_review_required=True,release_acceptance=False)
        C.report(value,context(),G.PNG_NAMES)
        for role,mutate in [('PAM',lambda v:v['checks'][-1].update(authenticated_by_existing_host_fixture=False)),
            ('clock',lambda v:v['checks'][-1].update(expected_clock_after='12:59')),
            ('update',lambda v:v['checks'][3].update(signed_stage_and_cleared_reboot_proven=True)),
            ('removal',lambda v:v['checks'][2].update(transaction_committed=True)),
            ('Enforcing',lambda v:v.update(selinux='Permissive')),
            ('private',lambda v:v['checks'][0].update(transcript='private'))]:
            wrong=copy.deepcopy(value);mutate(wrong)
            with self.subTest(role=role),self.assertRaises(RuntimeError):C.report(wrong,context(),G.PNG_NAMES)
        with self.assertRaises(RuntimeError):C.report(value,context(),G.PNG_NAMES[:-1])

    def test_actual_source_restore_attempts_both_preserving_primary(self):
        winner=self.root/'fixture-winner';winner.write_bytes(b'labelled synthetic photo')
        probe=object.__new__(G.Probe);probe.captures=[];probe.checks=[];probe.prefix=['fixture'];probe.wall=['wall']
        probe.phase='appearance';probe.appearance=lambda:None;probe.capture=lambda name:None
        photos=[dict(arctic=True,photographer='fixture',name=G.WINNER if i==0 else 'Other',path=str(winner),key='fixture')
                for i in range(19)]
        probe.library=lambda:dict(items=photos,current='original')
        probe.choose=lambda *args:(_ for _ in ()).throw(ValueError('fixture primary'))
        attempted=[]
        def command(argv,*args):
            if argv[1:]==['arctic-theme','current','--json']:
                return '{"mode":"dark","wallpaper_mode":"auto","auto_colors":true}'
            attempted.append(argv);raise OSError('fixture cleanup')
        with patch.object(G,'WINNER_SHA',hashlib.sha256(winner.read_bytes()).hexdigest()),patch.object(G,'result',command):
            with self.assertRaisesRegex(ValueError,'fixture primary'):probe.execute()
        self.assertEqual(attempted,[['wall','apply','original'],['fixture','arctic-theme','mode','auto']])

    def test_compose_pins_and_exclusive_foreign_path(self):
        source=self.root/'source';(source/'tools/native-functional').mkdir(parents=True)
        native=source/'tools/native-functional/native_smoke.py';native.write_text('fixture_value=1\n')
        value=context();value['native_sha256']=C.digest(native);value['ui_sha256']=C.digest(HERE/'guest.py')
        output=self.root/'composed.py';compose.compose(source,HERE/'guest.py',value,output)
        self.assertIn('fixture_value=1',output.read_text())
        original=output.read_bytes()
        with self.assertRaises(FileExistsError):compose.compose(source,HERE/'guest.py',value,output)
        self.assertEqual(output.read_bytes(),original)
        value['native_sha256']='f'*64
        with self.assertRaises(RuntimeError):compose.compose(source,HERE/'guest.py',value,self.root/'foreign')

    def test_exclusive_transport_preserves_foreign_symlink(self):
        foreign=self.root/'foreign';foreign.write_bytes(b'foreign')
        target=self.root/'target';target.symlink_to(foreign)
        with self.assertRaises(FileExistsError):C.exclusive(target,b'new')
        self.assertEqual(foreign.read_bytes(),b'foreign');self.assertTrue(target.is_symlink())

    def test_real_owned_host_group_cleanup_after_leader_exit(self):
        child=self.root/'descendant.pid';canary=subprocess.Popen([sys.executable,'-c','import time;time.sleep(10)'])
        code=('import os,signal,time\np=os.fork()\n'
              'if p: os._exit(0)\n'
              'signal.signal(signal.SIGTERM,signal.SIG_IGN)\n'
              'open('+repr(str(child))+',"w").write(str(os.getpid()))\ntime.sleep(10)\n')
        try:
            run.execute([sys.executable,'-c',code],self.root/'owned.log',5,self.root,os.environ.copy())
            pid=int(child.read_text());path=Path('/proc')/str(pid)/'stat'
            until=time.monotonic()+2
            while path.exists() and not path.read_text().split(') ',1)[1].startswith('Z ') and time.monotonic()<until:
                time.sleep(.01)
            self.assertTrue(not path.exists() or path.read_text().split(') ',1)[1].startswith('Z '))
            self.assertIsNone(canary.poll())
        finally:canary.terminate();canary.wait(5)

    def test_real_nonzero_exit_remains_failed(self):
        with self.assertRaisesRegex(RuntimeError,'UI host invocation failed'):
            run.execute([sys.executable,'-c','raise SystemExit(23)'],self.root/'failed.log',5,self.root,os.environ.copy())

    def test_gzip_original_screening_precedes_public_copy(self):
        source=self.root/'public';source.mkdir()
        C.exclusive(source/'host-status.json',b'{"release_acceptance":false}\n')
        C.exclusive(source/'serial-boot.log.gz',gzip.compress(b'transcript: private fixture\n',mtime=0))
        with self.assertRaises(RuntimeError):run.screen(source,self.root/'screened')
        self.assertFalse((self.root/'screened').exists())

    def test_unknown_artifact_inventory_is_fail_closed(self):
        source=self.root/'public';source.mkdir();C.exclusive(source/'host-status.json',b'{}')
        C.exclusive(source/'foreign.txt',b'public-looking but undeclared')
        with self.assertRaises(RuntimeError):run.screen(source,self.root/'screened')
        self.assertFalse((self.root/'screened').exists())

    def test_actual_container_cleanup_refuses_foreign_and_binds_immutable_id(self):
        name='arctic-paired-'+'a'*32+'-12345678';image='sha256:'+'b'*64;vm=self.root/'vm'
        row=dict(Name='/'+name,Image=image,Id='c'*64,Mounts=[dict(Source=str(vm),Destination=str(vm))])
        calls=[]
        def command(argv,**kwargs):
            calls.append(argv)
            return subprocess.CompletedProcess(argv,0,json.dumps([row]).encode(),b'')
        with patch.object(run.subprocess,'run',command):run.remove_owned_container(name,image,vm)
        self.assertEqual(calls[-1],['docker','rm','--force','c'*64])
        for field,new in (('Image','sha256:'+'d'*64),('Name','/foreign'),('Mounts',[])):
            wrong=copy.deepcopy(row);wrong[field]=new;calls=[]
            with patch.object(run.subprocess,'run',side_effect=lambda argv,**kw:
                    (calls.append(argv) or subprocess.CompletedProcess(argv,0,json.dumps([wrong]).encode(),b''))):
                with self.subTest(field=field),self.assertRaises(RuntimeError):run.remove_owned_container(name,image,vm)
            self.assertEqual(len(calls),1)

    def test_acquired_reader_refuses_symlink_and_nonregular_without_blocking(self):
        original=self.root/'original';original.write_bytes(b'fixture original')
        link=self.root/'link';link.symlink_to(original)
        with self.assertRaises(OSError):C.regular(link,100)
        fifo=self.root/'fifo';os.mkfifo(fifo)
        with self.assertRaises(RuntimeError):C.regular(fifo,100)
        self.assertEqual(C.regular(original,100),b'fixture original')

    def test_actual_git_preparation_modes_reject_before_remote_boundary(self):
        fixture=self.root/'mode-git';fixture.mkdir()
        def git(*args):
            return subprocess.check_output(['git','-C',str(fixture),*args],text=True).strip()
        git('init','--quiet');git('config','user.name','Source fixture');git('config','user.email','source@example.invalid')
        ci=fixture/'.github/workflows/ci.yml';ci.parent.mkdir(parents=True)
        before=(C.ROOT/'.github/workflows/ci.yml').read_bytes().replace(('      - '+C.BRANCH+'\n').encode(),b'',1)
        ci.write_bytes(before);git('add','.');git('commit','--quiet','-m','labelled synthetic base');base=git('rev-parse','HEAD')
        for name in C.ADDITIONS:
            target=fixture/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((C.ROOT/name).read_bytes())
        ci.write_bytes((C.ROOT/'.github/workflows/ci.yml').read_bytes());git('add','.')
        # Execute the actual guard through preparation admission, before its CI
        # byte comparison, source checkout or first remote producer API call.
        prefix=inspect.getsource(C.guard).split('    before = ',1)[0]
        namespace={};exec(prefix,C.__dict__,namespace);admit=namespace['guard']
        value=C.strict_json((HERE/'execution-manifest.json').read_bytes());value['ready']=True
        def check(mode,path):
            git('update-index','--cacheinfo',mode,git('rev-parse',':'+path),path)
            prep=git('commit-tree',git('write-tree'),'-p',base,'-m','labelled preparation')
            marker=fixture/C.MARKER;marker.parent.mkdir(parents=True,exist_ok=True);marker.write_text(prep+'\n')
            git('add',C.MARKER);head=git('commit-tree',git('write-tree'),'-p',prep,'-m','labelled activation')
            git('update-ref','HEAD',head)
            event=fixture/'event.json';event.write_text(json.dumps(dict(before=prep,after=head)))
            env=dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',
                GITHUB_REPOSITORY='yuvalkolodkingal/Arctic-Linux',GITHUB_REF='refs/heads/'+C.BRANCH,
                GITHUB_EVENT_NAME='push',GITHUB_WORKFLOW=C.WORKFLOW,GITHUB_RUN_ATTEMPT='1',
                GITHUB_SHA=head,GITHUB_EVENT_PATH=str(event))
            with patch.object(C,'ROOT',fixture),patch.object(C,'BASE',base),patch.dict(os.environ,env):
                if mode=='100644':admit(value,self.root/'unused-image-source')
                else:
                    # Historical name/status inventory admitted this same path.
                    self.assertEqual(set(git('diff','--no-renames','--name-status',base,prep).splitlines()),
                        {'A\t'+name for name in C.ADDITIONS}|{'M\t.github/workflows/ci.yml'})
                    with self.assertRaisesRegex(RuntimeError,'Preparation regular mode/type differs'):
                        admit(value,self.root/'unused-image-source')
            git('reset','--quiet',prep);git('update-index','--force-remove',C.MARKER);marker.unlink()
        check('100644',C.PREFIX+'guest.py')
        for path in (C.PREFIX+'guest.py',C.PREFIX+'README.md','.github/workflows/ci.yml'):
            check('100755',path);git('update-index','--chmod=-x',path)
        check('120000',C.PREFIX+'guest.py')

    def test_real_cancellation_defers_until_owned_popen_assignment(self):
        real_popen=subprocess.Popen;owned=[]
        legacy=Path(run.__file__).read_text().replace(
            'child=None; primary=None; secondary=None; acquiring=True; pending=False',
            'child=None; primary=None; secondary=None',1).replace(
            "    def interrupted(signum,frame):\n        nonlocal pending\n        if acquiring: pending=True\n"
            "        else: raise RuntimeError('Owned UI host invocation interrupted')\n",
            "    def interrupted(signum,frame): raise RuntimeError('Owned UI host invocation interrupted')\n",1).replace(
            "            acquiring=False\n            if pending: raise RuntimeError('Owned UI host invocation interrupted')\n",'',1)
        self.assertEqual(hashlib.sha256(legacy.encode()).hexdigest(),
            'd51364cfc1562e562dac7eee837ce316f3079b49d15079f8bc06b43930f42929')
        old_namespace={'__name__':'ui_original_execute','__file__':run.__file__}
        exec(compile(legacy,'<byte-exact-original-run.py>','exec'),old_namespace)
        canary=real_popen([sys.executable,'-c','import time;time.sleep(10)'])
        def interrupted_handoff(*args,**kwargs):
            child=real_popen(*args,**kwargs);owned.append(child)
            os.kill(os.getpid(),signal.SIGTERM)
            return child
        try:
            with patch.object(run.subprocess,'Popen',interrupted_handoff):
                with self.assertRaisesRegex(RuntimeError,'Owned UI host invocation interrupted'):
                    old_namespace['execute']([sys.executable,'-c','import time;time.sleep(10)'],
                        self.root/'historical-cancelled-acquisition.log',5,self.root,os.environ.copy())
            self.assertEqual(len(owned),1);self.assertIsNone(owned[0].poll())
            os.killpg(owned[0].pid,signal.SIGKILL);owned[0].wait(5);owned=[]
            with patch.object(run.subprocess,'Popen',interrupted_handoff):
                with self.assertRaisesRegex(RuntimeError,'Owned UI host invocation interrupted'):
                    run.execute([sys.executable,'-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(10)'],
                        self.root/'cancelled-acquisition.log',5,self.root,os.environ.copy())
            self.assertEqual(len(owned),1);self.assertIsNotNone(owned[0].returncode)
            self.assertIsNone(canary.poll())
        finally:
            for child in owned:
                if child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.wait(5)
            canary.terminate();canary.wait(5)


if __name__=='__main__':unittest.main()
