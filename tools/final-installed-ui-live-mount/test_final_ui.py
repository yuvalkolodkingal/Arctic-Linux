#!/usr/bin/env python3
"""Source controls only: labelled transport/process/UI adapters, no VM claim."""
import base64
import ast
import re
import types
import contextlib
import copy
import gzip
import hashlib
import io
import inspect
import textwrap
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


def _without_failure_observation(body):
    start=body.index('\n# BEGIN SOURCE-CLOSED FAILURE OBSERVATION')
    end=body.index('# END SOURCE-CLOSED FAILURE OBSERVATION',start)+len('# END SOURCE-CLOSED FAILURE OBSERVATION\n')
    body=body[:start]+body[end:]
    for new,old in [("allowed={'host-status.json','host-failure.json','original-ui/report.json','serial-install.log.gz','serial-boot.log.gz'}", "allowed={'host-status.json','original-ui/report.json','serial-install.log.gz','serial-boot.log.gz'}"), ("            if name=='host-failure.json':validate_failure(C.strict_json(data))\n", ''), ('def execute(argv, log, seconds, cwd, env, observation=None):', 'def execute(argv, log, seconds, cwd, env):'), ("            if observation is not None:observation['stage']='acquisition'\n", ''), ("            if observation is not None:observation.update(acquired=True,stage='observation')\n", ''), ("            if observation is not None:observation['exit_status']=status\n", ''), ("        except BaseException as error:\n            primary=error\n            if observation is not None:observation.update(failed_stage=observation['stage'],primary_guard=primary_guard(error))", '        except BaseException as error: primary=error'), ("                if observation is not None:observation['stage']='cleanup'\n", ''), ("                    if observation is not None:observation['reaped']=True\n", ''), ("    if observation is not None and primary is None and secondary is None:observation['stage']='complete'\n", ''), ("    observations=[invocation('provision'),invocation('harness')]\n", ''), ("private/'provision.log',20*60,C.ROOT,env,observations[0])", "private/'provision.log',20*60,C.ROOT,env)"), ("ARCTIC_FEDORA_IMAGE=prepared,ARCTIC_VM_TOOLS_PREPARED='1',ARCTIC_DICTATION_HOST_TOKEN=task)", "ARCTIC_FEDORA_IMAGE=prepared,ARCTIC_VM_TOOLS_PREPARED='1')"), ("private/'harness.log',70*60,C.ROOT,env,observations[1])", "private/'harness.log',70*60,C.ROOT,env)"), ("            if primary is not None:\n                try:\n                    diagnostic=failure_observation(primary,primary_phase,context,observations,private,scanner)\n                    data=(json.dumps(diagnostic,sort_keys=True,indent=2)+'\\n').encode()\n                    C.require(scanner.external_text(data)==data,'Failure observation privacy rejected')\n                    C.exclusive(public/'host-failure.json',data)\n                except BaseException:pass  # Reporting cannot replace the original failed result.\n", ''), ("    if 'host-failure.json' in files:\n        status=C.strict_json(files['host-status.json']);failure=C.strict_json(files['host-failure.json'])\n        C.require(status.get('status')=='failed' and status.get('context')==failure['context']\n            and status.get('phase')==failure['phase'] and status.get('error_class')==failure['error_class'],\n            'Failure-only diagnostic differs from original failed host status')\n", '')]:
        assert body.count(new)==1
        body=body.replace(new,old,1)
    assert hashlib.sha256(body.encode()).hexdigest()=='eb64d4c660dc6ce903df48c90f390748b1f3751c98b6cb612d6ae37699380ca3'
    return body


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

    def test_both_workflow_inline_imports_select_only_diagnostic_common(self):
        workflow=(C.ROOT/'.github/workflows/final-installed-ui-live-mount-20261011.yml').read_text()
        blocks=re.findall(r"python3 -B - <<'PY'\n(.*?)\n\s+PY",workflow,re.S)
        self.assertEqual(len(blocks),2)
        scripts=[textwrap.dedent(block) for block in blocks]
        execution=self.root/'execution';(self.root/'source').mkdir()
        for name in ('final-installed-ui','final-installed-ui-live-mount'):
            target=execution/'tools'/name;target.mkdir(parents=True)
            (target/'common.py').write_bytes((C.ROOT/'tools'/name/'common.py').read_bytes())
        value=C.strict_json((HERE/'execution-manifest.json').read_bytes());value['ready']=True
        (execution/'tools/final-installed-ui-live-mount/execution-manifest.json').write_text(json.dumps(value))
        env=os.environ.copy();env['GITHUB_OUTPUT']=str(self.root/'github-output')
        first=subprocess.run([sys.executable,'-B','-c',scripts[0]],cwd=execution,env=env,capture_output=True)
        self.assertEqual(first.returncode,0,first.stderr)
        self.assertEqual((self.root/'github-output').read_text(),'source='+value['image']['source_sha']+'\n')
        failed=subprocess.run([sys.executable,'-B','-c',scripts[0].replace(
            "sys.path.insert(0,'tools/final-installed-ui-live-mount')",
            "sys.path.insert(0,'tools/final-installed-ui')")],cwd=execution,env=env,capture_output=True)
        self.assertNotEqual(failed.returncode,0);self.assertIn(b'Execution inventory differs',failed.stderr)
        # Source-only adapter at the guard call, proving module selection before any API/VM boundary.
        adapter="import common\nassert common.BRANCH == 'codex/final-installed-ui-live-mount-20261011'\nassert common.MARKER == '.github/final-installed-ui-live-mount-20261011.activate'\nassert common.FILES == set(common.manifest(common.strict_json(Path('execution/tools/final-installed-ui-live-mount/execution-manifest.json').read_bytes()),True)['execution_files'])\ncommon.guard=lambda value,source: None"
        second=scripts[1].replace('import common',adapter,1)
        good=subprocess.run([sys.executable,'-B','-c',second],cwd=self.root,env=env,capture_output=True)
        self.assertEqual(good.returncode,0,good.stderr)
        old=subprocess.run([sys.executable,'-B','-c',second.replace(
            "sys.path.insert(0,'execution/tools/final-installed-ui-live-mount')",
            "sys.path.insert(0,'execution/tools/final-installed-ui')")],cwd=self.root,env=env,capture_output=True)
        self.assertNotEqual(old.returncode,0)

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
        legacy=_without_failure_observation(Path(run.__file__).read_text()).replace(
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


class FailureProjection(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='arctic-ui-failure-source-')
        self.root=Path(self.temp.name)
        self.scanner=C.load(C.ROOT/'tools/native-functional/screen-evidence.py','ui_failure_actual_scanner')
    def tearDown(self):self.temp.cleanup()

    def record(self,error=None):
        return run.failure_observation(error or RuntimeError('private error not exported'),'harness',
            context(),[run.invocation('provision'),run.invocation('harness')],self.root,self.scanner)

    def test_actual_nonzero_child_exit_and_source_frame_are_preserved(self):
        item=run.invocation('harness')
        try:
            run.execute([sys.executable,'-c','raise SystemExit(23)'],self.root/'harness.log',5,
                        self.root,os.environ.copy(),item)
        except RuntimeError as error:
            self.assertEqual(run.primary_guard(error),'execute-002')
            value=run.failure_observation(error,'harness',context(),
                [run.invocation('provision'),item],self.root,self.scanner)
        else:self.fail('Original nonzero-exit gate weakened')
        self.assertEqual(item['exit_status'],23);self.assertTrue(item['acquired']);self.assertTrue(item['reaped'])
        self.assertEqual(item['failed_stage'],'observation');self.assertEqual(value['status'],'failed')
        self.assertFalse(value['ui_acceptance']);self.assertFalse(value['release_acceptance'])

    def test_foreign_source_lookalikes_and_fake_repr_stay_unknown(self):
        class Hostile(RuntimeError):
            def __str__(self):raise AssertionError('private str accessed')
            def __repr__(self):raise AssertionError('private repr accessed')
        self.assertEqual(run.primary_guard(Hostile('UI host invocation failed')),'unknown')
        try:C.require(False,'UI host invocation failed')
        except RuntimeError as error:self.assertEqual(run.primary_guard(error),'unknown')
        copied=types.FunctionType(C.guard.__code__,dict(C.guard.__globals__),argdefs=C.guard.__defaults__)
        value=C.strict_json((HERE/'execution-manifest.json').read_bytes());value['ready']=True
        with patch.dict(os.environ,{},clear=True):
            try:copied(value,self.root)
            except RuntimeError as error:self.assertEqual(run.primary_guard(error),'unknown')
            try:C.guard(value,self.root)
            except RuntimeError as error:self.assertEqual(run.primary_guard(error),'guard-001')

    def test_actual_require_deadline_guard_keeps_owned_cleanup(self):
        item=run.invocation('harness')
        try:
            run.execute([sys.executable,'-c','import time;time.sleep(5)'],self.root/'deadline.log',.01,
                        self.root,os.environ.copy(),item)
        except RuntimeError as error:self.assertEqual(run.primary_guard(error),'execute-001')
        else:self.fail('Original deadline gate weakened')
        self.assertTrue(item['reaped']);self.assertIsNone(item['exit_status'])

    def test_nonce_closed_checkpoints_and_duplicate_exits_are_ambiguous(self):
        path=self.root/'harness.log';nonce=context()['nonce']
        path.write_text('ARCTIC-DICTATION-HOST-STAGE '+nonce+' container-driver\n'
            +'ARCTIC-DICTATION-HOST-STAGE '+('f'*32)+' boot-menu\n'
            +'ARCTIC-DICTATION-HOST-STAGE '+nonce+' arbitrary-private-role\n'
            +'ARCTIC-FINAL-UI-LIVE-PRECHECK=PASS\nARCTIC-INSTALL-EXIT=0\nARCTIC-INSTALL-EXIT=23\n')
        value=run.private_checkpoints(path,nonce,self.scanner)
        self.assertEqual(value['host_stages'],{'container-driver':1})
        self.assertEqual(value['guest_fixed_stages'],{'ARCTIC-FINAL-UI-LIVE-PRECHECK=PASS':1})
        self.assertEqual(value['install_exit_count'],2);self.assertIsNone(value['install_exit_status'])
        path.write_text('ARCTIC-INSTALL-EXIT=7\n')
        self.assertEqual(run.private_checkpoints(path,nonce,self.scanner)['install_exit_status'],7)

    def test_complete_private_rejection_precedes_checkpoint_parsing(self):
        path=self.root/'harness.log';nonce=context()['nonce']
        path.write_text('transcript: private source fixture\nARCTIC-DICTATION-HOST-STAGE '+nonce+' container-driver\n')
        value=run.private_checkpoints(path,nonce,self.scanner)
        self.assertEqual(value['privacy'],'rejected');self.assertEqual(value['host_stages'],{})
        self.assertEqual(value['install_exit_count'],0);self.assertIsNone(value['install_exit_status'])

    def test_projection_rejects_foreign_fields_classes_labels_and_acceptance(self):
        value=self.record();run.validate_failure(value)
        variants=[('raw_private_exported',True),('ui_acceptance',True),('release_acceptance',True),
            ('primary_guard','private arbitrary guard'),('error_class','private error'),('phase','private path')]
        for key,new in variants:
            wrong=copy.deepcopy(value);wrong[key]=new
            with self.subTest(key=key),self.assertRaises(RuntimeError):run.validate_failure(wrong)
        wrong=copy.deepcopy(value);wrong['transcript']='private'
        with self.assertRaises(RuntimeError):run.validate_failure(wrong)
        for new in (True,-1,256):
            wrong=copy.deepcopy(value);wrong['invocations'][1]['exit_status']=new
            with self.subTest(exit=new),self.assertRaises(RuntimeError):run.validate_failure(wrong)

    def test_failure_only_screen_binds_original_host_status(self):
        value=self.record();source=self.root/'public';source.mkdir()
        status={'status':'failed','phase':'harness','error_class':'RuntimeError','context':context()}
        (source/'host-status.json').write_text(json.dumps(status))
        (source/'host-failure.json').write_text(json.dumps(value))
        run.screen(source,self.root/'good')
        self.assertEqual((source/'host-failure.json').read_bytes(),(self.root/'good/host-failure.json').read_bytes())
        status['status']='passed';(source/'host-status.json').write_text(json.dumps(status))
        with self.assertRaises(RuntimeError):run.screen(source,self.root/'rejected')
        self.assertFalse((self.root/'rejected').exists())

    def test_deferred_cancel_reports_source_guard_and_reaps_real_acquired_child(self):
        item=run.invocation('harness');real=subprocess.Popen;children=[]
        def handoff(*args,**kwargs):
            child=real(*args,**kwargs);children.append(child);os.kill(os.getpid(),signal.SIGTERM);return child
        try:
            with patch.object(run.subprocess,'Popen',handoff):
                try:run.execute([sys.executable,'-c','import time;time.sleep(5)'],self.root/'cancel.log',5,
                                self.root,os.environ.copy(),item)
                except RuntimeError as error:self.assertEqual(run.primary_guard(error),'execute-deferred-interrupted')
                else:self.fail('Original cancellation was lost')
            self.assertTrue(item['acquired']);self.assertTrue(item['reaped']);self.assertIsNotNone(children[0].returncode)
        finally:
            for child in children:
                if child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.wait(5)

    def test_original_runtime_inverse_and_official_host_stage_inventory(self):
        original=_without_failure_observation(Path(run.__file__).read_text())
        self.assertEqual(hashlib.sha256(original.encode()).hexdigest(),
            'eb64d4c660dc6ce903df48c90f390748b1f3751c98b6cb612d6ae37699380ca3')
        source=(C.ROOT/'tools/test-install.sh').read_text()
        driver=re.search(r'DICTATION_HOST_STAGES = frozenset\((\{.*?\})\)',source,re.S)
        stages=ast.literal_eval(driver[1])|{'host-data','host-container','container-packages','container-audio',
            'container-data','container-disk','container-profile','container-driver','container-complete'}
        self.assertEqual(set(run.HOST_STAGES),stages)


if __name__=='__main__':unittest.main()
