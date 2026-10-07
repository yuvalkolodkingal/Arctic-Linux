#!/usr/bin/env python3
"""Host-only controls; synthetic serial/WAV and mocked harness, never a VM."""
import ast
import base64
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock
import wave
import yaml
import zlib

HERE=Path(__file__).resolve().parent


def native_workflow_path(here=None):
    """Audit copy when present; otherwise the workflow in the deployed repo."""
    here=HERE if here is None else Path(here)
    audit=here/'registered-iso-native-v5.yml'
    if os.path.lexists(audit):
        return audit
    deployed=here.parents[1]/'.github/workflows/iso.yml'
    if not deployed.is_file():
        raise FileNotFoundError('native workflow missing from audit and deployed repository locations')
    return deployed

def load(name,file):
    spec=importlib.util.spec_from_file_location(name,HERE/file);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

N=load('native_runner_v4_tested','native-runner-v5.py')
A=load('native_adapter_v4_tested','guest-check-native-v5.py')
P=load('native_prepare_v4_tested','prepare-adapter-v5.py')
L=load('native_launcher_v4_tested','native-launcher-v5.py')
V=load('native_visual_v4_tested','native_smoke.py')


def report(stage,status='limited-smoke-passed'):
    gates=[dict(check=name,status='passed') for name in sorted(N.GATES)]
    if status=='failed':gates[-1]['status']='failed'
    return dict(schema='arctic-native-functional-smoke-v4',stage=stage,status=status,release_acceptance=False,
                gates=gates,evidence_root='/tmp/arctic-native-smoke-test')


def launcher_proof(stage,uid=1000):
    def item(pid,exe,owner):return dict(pid=pid,ppid=pid-1,start_ticks=pid*10,uid=owner,executable=exe,executable_sha256='1'*64)
    return dict(schema='arctic-native-launcher-v1',stage=stage,boot_id=('1' if stage=='live' else '2')*8+'-1111-1111-1111-111111111111',launcher_sha256=N.LAUNCHER_SHA,owned_launcher_gone=True,shell=item(20,'/usr/bin/fish',uid),foot=item(10,'/usr/bin/foot',uid),probe=item(30,'/usr/bin/python3.14',0),ancestry=[])


def protocol(stage,status='limited-smoke-passed',extra=None):
    value=report(stage,status);begin=dict(stage=stage,native_source_sha256=N.NATIVE_SOURCE_SHA,
        checker_sha256=N.CHECKERS['native-functional'][1],release_acceptance=False)
    proof=dict(begin,desktop_uid=1000,boot_id=('1' if stage=='live' else '2')*8+'-1111-1111-1111-111111111111',
               cmdline='rd.live.image arctic.mode=try' if stage=='live' else 'root=/dev/mapper/luks-test',
               virtual_audio_cards=' 0 [ICH6 ]: HDA-Intel - HDA Intel\n')
    proof['launcher']=launcher_proof(stage);proof['active_desktop_session']='2'
    if stage=='installed':proof['encrypted_root']=dict(type='LUKS2',device='/dev/mapper/luks-test',source='/dev/mapper/luks-test[/@]',status=' type: LUKS2\n')
    png=b'\x89PNG\r\n\x1a\nsynthetic'
    shots=[dict(path=value['evidence_root']+'/'+name,sha256=hashlib.sha256(png).hexdigest()) for name in ('editor-saved.png','files-opened-zip.png','celluloid-playing.png')]
    byname={g['check']:g for g in value['gates']}
    byname['actual-role-file-manager-terminal-editor']['value']=dict(screenshots=shots[:2])
    reference=V.visual_reference_frame()
    oracle=V.evaluate_reference_rgb(reference,160,120,reference)
    visual=dict(screenshot=dict(path=value['evidence_root']+'/celluloid-reference.png',sha256=hashlib.sha256(png).hexdigest()),
                expected_rgb_path=value['evidence_root']+'/visual-reference-frame.rgb',actual_rgb_path=value['evidence_root']+'/visual-owned-window.rgb',
                expected_rgb_sha256=hashlib.sha256(reference).hexdigest(),actual_rgb_sha256=hashlib.sha256(reference).hexdigest(),
                client_pixel_crop=dict(x=0,y=0,width=160,height=120),oracle=oracle)
    if extra and 'visual-owned-window.rgb' in extra:
        visual['actual_rgb_sha256']=hashlib.sha256(extra['visual-owned-window.rgb']).hexdigest()
    byname['open-codec-content-and-player-state']['value']=dict(screenshot=shots[2],visual_reference=visual)
    # Rewrite the report line after adding its actual exported screenshot references.
    data={'report.json':json.dumps(value).encode(),'screen.png':png,'partial.log':b'preserve failed diagnostic',
          **{Path(shot['path']).name:png for shot in shots}}
    data.update({'celluloid-reference.png':png,'visual-reference-frame.rgb':reference,'visual-owned-window.rgb':reference,
                 'gui-trace.log':b'fixture only','gui-trace-summary.json':b'{}','final-clients.json':b'{}',
                 'visual-oracle.json':json.dumps(visual).encode(),'moving-player-proof.json':b'{}'})
    if extra:data.update(extra)
    ready=dict(proof['launcher']);ready.pop('owned_launcher_gone')
    lines=['ARCTIC-NATIVE-LAUNCHER-READY '+json.dumps(ready),'ARCTIC-NATIVE-LAUNCHER-GONE '+json.dumps(proof['launcher']),'ARCTIC-NATIVE-RUNNER-BEGIN '+json.dumps(begin),'ARCTIC-NATIVE-PROVENANCE '+json.dumps(proof),
           'ARCTIC-NATIVE-FUNCTIONAL '+json.dumps(value)]
    files=[]
    for name,content in data.items():
        compressed=zlib.compress(content);files.append(dict(path=name,bytes=len(content),sha256=hashlib.sha256(content).hexdigest(),compressed_bytes=len(compressed),chunks=1,encoding='zlib+base64'))
        lines.append('ARCTIC-NATIVE-EVIDENCE-CHUNK '+json.dumps(dict(path=name,index=0,data=base64.b64encode(compressed).decode())))
    lines+=['ARCTIC-NATIVE-EVIDENCE-MANIFEST '+json.dumps(dict(schema='arctic-native-evidence-v1',stage=stage,files=files,bytes=sum(len(v) for v in data.values()),evidence_root=value['evidence_root'])),
            'ARCTIC-NATIVE-RUNNER-END '+json.dumps(dict(stage=stage,status='passed' if status!='failed' else 'failed',error=None if status!='failed' else 'native cleanup failure',evidence_export_complete=True,release_acceptance=False))]
    return '\n'.join(lines)+'\n'


def harness_live():
    return 'ARCTIC-OFFLINE-HTTP-RESPONSE=000\nARCTIC-OFFLINE-GATE=passed: restricted QEMU network, no outside HTTP response\n'+protocol('live')+'ARCTIC-LIVE-SMOKE-EXIT=0\nARCTIC-INSTALL-EXIT=0\n'


def harness_installed():
    return 'ARCTIC-COLLECT-BEGIN\n'+protocol('installed')+'ARCTIC-INSTALLED-SMOKE-EXIT=0\nARCTIC-COLLECT-END\n'


def ci():
    return dict(GITHUB_ACTIONS='true',GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REPOSITORY=N.R.REPOSITORY,
                GITHUB_API_URL='https://api.github.com',GITHUB_SHA='3'*40,GITHUB_RUN_ID='37530000000',
                GITHUB_RUN_ATTEMPT='1',NIX_REQUESTED='false',PERFORMANCE_REQUESTED='false',BOOT_TEST_REQUESTED='false',NATIVE_SMOKE_MODE='true',RECOVERY_MODE='false',RELEASE_REQUESTED='false')


class ProtocolControls(unittest.TestCase):
    def test_checksums_and_claimed_playback_cannot_accept_black_or_wrong_rgb(self):
        reference=V.visual_reference_frame()
        for frame in (b'\0'*len(reference),reference[::-1]):
            with self.subTest(frame_hash=hash(frame)),tempfile.TemporaryDirectory() as folder:
                target=Path(folder)/'files'
                with self.assertRaisesRegex(RuntimeError,'visual oracle'):
                    N.check_native(protocol('live',extra={'visual-owned-window.rgb':frame}),'live',target)
                self.assertEqual((target/'visual-owned-window.rgb').read_bytes(),frame)
                self.assertTrue((target/'report.json').is_file())
    def test_roundtrip_both_stages(self):
        with tempfile.TemporaryDirectory() as folder:
            for stage in ('live','installed'):
                target=Path(folder)/stage
                result=N.check_native(protocol(stage),stage,target)
                self.assertFalse(result['release_acceptance']);self.assertEqual((target/'partial.log').read_bytes(),b'preserve failed diagnostic')

    def test_failed_cleanup_retains_guest_files_and_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'failed'
            with self.assertRaises(RuntimeError):N.check_native(protocol('live','failed'),'live',target)
            self.assertTrue((target/'report.json').exists());self.assertTrue((target/'screen.png').exists())

    def test_stage_identity_gate_and_completion_negatives(self):
        cases=[('"stage": "live"','"stage": "installed"'),(N.NATIVE_SOURCE_SHA,'0'*64),
               ('"release_acceptance": false','"release_acceptance": true'),
               ('"evidence_export_complete": true','"evidence_export_complete": false'),
               ('"status": "passed"','"status": "failed"'),('"error": null','"error": "cleanup"'),
               ('rd.live.image','not.live'),(' 0 [ICH6 ]','no card'),
               ('ARCTIC-NATIVE-RUNNER-END ','BROKEN-END '),('"desktop_uid": 1000','"desktop_uid": true'),('11111111-1111-1111-1111-111111111111','-'*36)]
        for old,new in cases:
            with self.subTest(old=old),tempfile.TemporaryDirectory() as folder,self.assertRaises((RuntimeError,KeyError)):
                N.check_native(protocol('live').replace(old,new),'live',Path(folder)/'out')

    def test_unsafe_or_reserved_path_rejected(self):
        for path in ('../escape.json','/escape.json','a/../escape.json','report.json/child.json','transport-manifest.json','serial-native-report.json'):
            with self.subTest(path=path),tempfile.TemporaryDirectory() as folder,self.assertRaises((RuntimeError,FileExistsError)):
                N.check_native(protocol('live',extra={path:b'unsafe'}),'live',Path(folder)/'out')

    def test_changed_chunk_or_missing_report_cannot_pass(self):
        value=protocol('live')
        for bad in (value.replace('"index": 0','"index": true'),value.replace('"encoding": "zlib+base64"','"encoding": "none"'),
                    value.replace('ARCTIC-NATIVE-FUNCTIONAL ','NO-REPORT '),value+'ARCTIC-NATIVE-RUNNER-END {}\n'):
            with self.subTest(),tempfile.TemporaryDirectory() as folder,self.assertRaises(RuntimeError):
                N.check_native(bad,'live',Path(folder)/'out')

    def test_installed_root_luks_required(self):
        with tempfile.TemporaryDirectory() as folder,self.assertRaises(RuntimeError):
            N.check_native(protocol('installed').replace('LUKS2','plain'),'installed',Path(folder)/'out')

    def test_successful_encrypted_offline_live_first_boot(self):
        with tempfile.TemporaryDirectory() as folder:
            vm=Path(folder)/'vm';vm.mkdir();evidence=Path(folder)/'evidence';evidence.mkdir()
            (vm/'serial-install.log').write_text(harness_live());(vm/'serial-boot.log').write_text(harness_installed())
            results=N.validate_harness_serial(vm,evidence)
            self.assertEqual(set(results),{'live','installed'})

    def test_missing_second_log_still_extracts_live(self):
        with tempfile.TemporaryDirectory() as folder:
            vm=Path(folder)/'vm';vm.mkdir();evidence=Path(folder)/'evidence';evidence.mkdir()
            (vm/'serial-install.log').write_text(harness_live())
            with self.assertRaises(RuntimeError):N.validate_harness_serial(vm,evidence)
            self.assertTrue((evidence/'native-live'/'screen.png').exists())

    def test_native_outside_installed_collect_cannot_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            vm=Path(folder)/'vm';vm.mkdir();evidence=Path(folder)/'evidence';evidence.mkdir()
            (vm/'serial-install.log').write_text(harness_live())
            (vm/'serial-boot.log').write_text(protocol('installed')+'ARCTIC-COLLECT-BEGIN\nARCTIC-INSTALLED-SMOKE-EXIT=0\nARCTIC-COLLECT-END\n')
            with self.assertRaises(RuntimeError):N.validate_harness_serial(vm,evidence)

    def test_offline_or_install_failure_cannot_pass(self):
        for old,new in [('HTTP-RESPONSE=000','HTTP-RESPONSE=200'),('ARCTIC-INSTALL-EXIT=0','ARCTIC-INSTALL-EXIT=3'),('ARCTIC-LIVE-SMOKE-EXIT=0','ARCTIC-LIVE-SMOKE-EXIT=3')]:
            with self.subTest(old=old),tempfile.TemporaryDirectory() as folder:
                vm=Path(folder)/'vm';vm.mkdir();e=Path(folder)/'e';e.mkdir()
                (vm/'serial-install.log').write_text(harness_live().replace(old,new));(vm/'serial-boot.log').write_text(harness_installed())
                with self.assertRaises(RuntimeError):N.validate_harness_serial(vm,e)
                self.assertTrue((e/'native-live'/'report.json').exists())


class AdapterControls(unittest.TestCase):
    def test_native_top_level_bytes_and_ast_retained(self):
        with tempfile.TemporaryDirectory() as folder:
            result=P.build(HERE/'native_smoke.py',Path(folder)/'adapter.py')
            self.assertTrue(result['all_other_source_bytes_equal'])
            self.assertEqual(result['adapter_sha256'],N.CHECKERS['native-functional'][1])

    def test_wrong_location_or_stage_emits_failed_completion(self):
        for argv in ([str(HERE/'guest-check-native-v5.py'),'live'],[str(HERE/'guest-check-native-v5.py'),'installed','extra']):
            output=io.StringIO()
            with mock.patch('sys.argv',argv),contextlib.redirect_stdout(output),contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(A.main(),1)
            end=json.loads(output.getvalue().split('ARCTIC-NATIVE-RUNNER-END ',1)[1])
            self.assertEqual(end['status'],'failed')

    def test_actual_adapter_export_on_pass_and_failed_native_gate(self):
        for status in ('limited-smoke-passed','failed'):
            with self.subTest(status=status),tempfile.TemporaryDirectory(prefix='arctic-native-smoke-') as folder:
                root=Path(folder);uid=os.getuid();value=report('live',status);value['evidence_root']=str(root)
                (root/'report.json').write_text(json.dumps(value));(root/'failure.log').write_text('real fixture bytes')
                def native(prefix,stage,disposable_guest):
                    self.assertTrue(disposable_guest);print('ARCTIC-NATIVE-FUNCTIONAL '+json.dumps(value));return value
                proc={'/proc/asound/cards':' 0 [ICH6 ]: HDA-Intel', '/proc/cmdline':'rd.live.image', '/proc/sys/kernel/random/boot_id':'11111111-1111-1111-1111-111111111111'}
                def path(value):
                    if str(value)=='/run/t/native-launcher.py':return HERE/'native-launcher-v5.py'
                    if str(value) in proc:return SimpleNamespace(read_text=lambda:proc[str(value)])
                    return Path(value)
                output=io.StringIO()
                with mock.patch('sys.argv',['/run/t/guest-check.py','live']),mock.patch.object(A,'__file__','/run/t/guest-check.py'),mock.patch.object(A,'digest',return_value=N.CHECKERS['native-functional'][1]),mock.patch.object(A,'guest_guard'),mock.patch.object(A,'discover_desktop',return_value=['runuser','-u','fixture','--','env','XDG_SESSION_ID=2']),mock.patch.object(A.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=uid)),mock.patch.object(A,'Path',side_effect=path),mock.patch.object(A,'run_checks',side_effect=native),mock.patch('importlib.util.spec_from_file_location',return_value=SimpleNamespace(loader=SimpleNamespace(exec_module=lambda module:None))),mock.patch('importlib.util.module_from_spec',return_value=SimpleNamespace(verify_barrier=lambda stage,sha:launcher_proof(stage,uid))),mock.patch.object(A,'execute',side_effect=lambda argv:(0,'wayland' if 'Type' in argv else 'yes')),contextlib.redirect_stdout(output),contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(A.main(),int(status=='failed'))
                lines,begin,end=N.native_block(output.getvalue(),'live')
                with tempfile.TemporaryDirectory() as dest:
                    N.extract_evidence(lines,'live',Path(dest)/'files')
                    self.assertEqual((Path(dest)/'files'/'failure.log').read_text(),'real fixture bytes')
                self.assertEqual(end['status'],'passed' if status!='failed' else 'failed')


class LauncherControls(unittest.TestCase):
    def chain(self):
        current=os.getpid()
        def item(pid,ppid,uid,exe):return dict(pid=pid,ppid=ppid,uid=uid,start_ticks=pid*10,executable=exe,executable_sha256='1'*64)
        return {current:item(current,40,0,'/usr/bin/python3.14'),40:item(40,30,0,'/usr/bin/sudo'),30:item(30,20,1000,'/usr/bin/fish'),20:item(20,1,1000,'/usr/bin/foot')}

    def test_ancestor_selection_fish_safe_and_owned_only(self):
        chain=self.chain();proof=L.identify_launcher(read=chain.__getitem__)
        self.assertEqual(proof['shell']['pid'],30);self.assertEqual(proof['foot']['pid'],20)
        for mutation in ('different_uid','outside_shell','wrong_elf'):
            bad=copy.deepcopy(chain)
            if mutation=='different_uid':bad[20]['uid']=2000
            if mutation=='wrong_elf':bad[30]['executable']='/usr/bin/sleep'
            with self.subTest(mutation=mutation),self.assertRaises(RuntimeError):
                L.identify_launcher(999 if mutation=='outside_shell' else None,read=bad.__getitem__)

    def test_actual_pidfd_barrier_after_both_owned_processes_exit(self):
        import subprocess,time
        children=[subprocess.Popen(['/usr/bin/sleep',str(seconds)]) for seconds in (.2,.3)]
        fds=[]
        try:
            proof={name:L.identity(child.pid) for name,child in zip(('shell','foot'),children)}
            fds=[os.pidfd_open(child.pid) for child in children]
            started=time.monotonic();L.wait_disappeared(proof,fds,timeout=2)
            self.assertGreater(time.monotonic()-started,.15)
            self.assertTrue(all(not L.same_process(proof[name]) for name in ('shell','foot')))
        finally:
            for fd in fds:os.close(fd)
            for child in children:child.wait(timeout=2)

    def test_live_identity_cannot_pass_and_pid_reuse_not_same_process(self):
        import subprocess
        with subprocess.Popen(['/usr/bin/sleep','.3']) as child:
            item=L.identity(child.pid);fd=os.pidfd_open(child.pid)
            try:
                with self.assertRaises(RuntimeError):L.wait_disappeared(dict(shell=item,foot=item),[fd,fd],timeout=.02)
                changed=dict(item,start_ticks=item['start_ticks']+1)
                self.assertFalse(L.same_process(item,read=lambda pid:changed))
            finally:os.close(fd)

    def test_missing_wrong_owned_launcher_or_marker_cannot_pass(self):
        for old,new in [('ARCTIC-NATIVE-LAUNCHER-GONE ','NO-GONE '),('"owned_launcher_gone": true','"owned_launcher_gone": false'),('/usr/bin/foot','/usr/bin/kitty'),(N.LAUNCHER_SHA,'0'*64),('"pid": 20','"pid": true')]:
            with self.subTest(old=old),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);vm=root/'vm';vm.mkdir();e=root/'e';e.mkdir()
                (vm/'serial-install.log').write_text(harness_live().replace(old,new));(vm/'serial-boot.log').write_text(harness_installed())
                with self.assertRaises(RuntimeError):N.validate_harness_serial(vm,e)

    def test_actual_default_typed_commands_remain_and_only_native_exits(self):
        original=N.subprocess.check_output(['git','-C',str(HERE),'show',N.R.SOURCE+':tools/test-install.sh'],text=True)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'tools').mkdir();(root/'tools/test-install.sh').write_text(original)
            N.subprocess.run(['git','-C',str(root),'apply',str(HERE/'test-install-native-audio-v5.patch')],check=True,capture_output=True)
            changed=(root/'tools/test-install.sh').read_text()
        def statements(source,revised):
            driver=source.split("read -r -d '' DRIVER <<'PY' || true\n",1)[1].split('\nPY\n',1)[0]
            tree=ast.parse(driver);found=[]
            for fn in tree.body:
                if not isinstance(fn,ast.FunctionDef) or fn.name not in ('stage_install','stage_boot'):continue
                if revised:
                    assignments=[n for n in ast.walk(fn) if isinstance(n,ast.Assign) and ast.unparse(n.targets[0])=='command']
                    self.assertEqual(len(assignments),1)
                    calls=[n for n in ast.walk(fn) if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and ast.unparse(n.value.func)=='vm.type_text' and ast.unparse(n.value.args[0])=='command']
                    found.append([assignments[0],calls[0]])
                else:
                    calls=[n for n in ast.walk(fn) if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and ast.unparse(n.value.func)=='vm.type_text' and isinstance(n.value.args[0],ast.Constant) and n.value.args[0].value=='sudo sh /dev/sr0']
                    self.assertEqual(len(calls),1);found.append([calls[0]])
            self.assertEqual(len(found),2);return found
        originals=statements(original,False);revised=statements(changed,True)
        for enabled in (None,'0','1'):
            for old,new in zip(originals,revised):
                recorded=[];env=dict(E={} if enabled is None else {'NATIVE_LAUNCHER_FIXTURE':enabled},vm=SimpleNamespace(type_text=lambda text,gap:recorded.append((text,gap))))
                exec(compile(ast.Module(body=old,type_ignores=[]),'original-command','exec'),env);before=recorded.pop()
                exec(compile(ast.Module(body=new,type_ignores=[]),'native-command','exec'),env)
                self.assertEqual(recorded,[('sudo sh /dev/sr0; exit',.3)] if enabled=='1' else [before])

    def test_fixture_shell_exit_only_opt_in_and_no_signal_or_tty_switch(self):
        patch=(HERE/'test-install-native-audio-v5.patch').read_text()
        self.assertEqual(patch.count('command = "sudo sh /dev/sr0; exit" if E.get("NATIVE_LAUNCHER_FIXTURE")'),2)
        self.assertIn('else "sudo sh /dev/sr0"',patch)
        self.assertIn('if [ -f /run/t/native-launcher.py ]; then exec python3',patch)
        self.assertIn('exec >/dev/null',patch)
        tree=ast.parse((HERE/'native-launcher-v5.py').read_text())
        called={ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n,ast.Call)}
        self.assertFalse(called & {'os.kill','signal.pidfd_send_signal','os.killpg'})
        self.assertNotIn('chvt',patch)


class AudioControls(unittest.TestCase):
    def make_wav(self,path,silent=False,frames=48000):
        with wave.open(str(path),'wb') as out:
            out.setnchannels(2);out.setsampwidth(2);out.setframerate(48000)
            chunk=(b'\0'*4 if silent else b'\1\0\1\0')*4096
            while frames:
                count=min(frames,4096);out.writeframesraw(chunk[:count*4]);frames-=count

    def test_actual_pcm_nonzero_and_silence_failure_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for silent in (False,True):
                path=root/('silent.wav' if silent else 'nonzero.wav');self.make_wav(path,silent)
                target=root/path.stem
                if silent:
                    with self.assertRaises(RuntimeError):N.preserve_audio(path,target)
                    self.assertTrue((target/(path.name+'.bounded-prefix.bin')).exists())
                else:
                    result=N.preserve_audio(path,target);self.assertGreater(result['nonzero_blocks'],0)
                    self.assertTrue(result['preserved_full'])

    def test_actual_large_wav_preserves_valid_bounded_excerpts(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'large.wav';self.make_wav(path,frames=8_500_000)
            result=N.preserve_audio(path,root/'evidence')
            self.assertFalse(result['preserved_full'])
            for item in result['excerpts']:
                with wave.open(str(root/'evidence'/item['path']),'rb') as wav:
                    self.assertLessEqual(wav.getnframes(),96000)
            self.assertFalse((root/'evidence'/'large.wav').exists())

    def test_corrupt_wav_fails_and_retains_bounded_prefix(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'corrupt.wav';path.write_bytes(b'bad header')
            with self.assertRaises(wave.Error):N.preserve_audio(path,root/'evidence')
            self.assertEqual((root/'evidence'/'corrupt.wav.bounded-prefix.bin').read_bytes(),b'bad header')

    def test_default_qemu_argv_unchanged_and_audio_opt_in(self):
        original=N.subprocess.check_output(['git','-C',str(HERE),'show',N.R.SOURCE+':tools/test-install.sh'],text=True)
        # Apply the reviewed draft patch in an isolated temporary copy only.
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'tools').mkdir();(root/'tools/test-install.sh').write_text(original)
            N.subprocess.run(['git','-C',str(root),'apply',str(HERE/'test-install-native-audio-v5.patch')],check=True,capture_output=True)
            changed=(root/'tools/test-install.sh').read_text()
        def argv(text,audio):
            driver=text.split("read -r -d '' DRIVER <<'PY' || true\n",1)[1].split('\nPY\n',1)[0]
            fn=next(n for n in ast.parse(driver).body if isinstance(n,ast.FunctionDef) and n.name=='qemu_argv')
            code=compile(ast.Module(body=[fn],type_ignores=[]),'qemu-argv-control','exec')
            env=dict(E=dict(ONLINE_PROXY='0',BOOT_NETWORK='offline',NATIVE_AUDIO_FIXTURE=audio),accel='kvm',smp='2',mem='4096',out='/fixture',fw='uefi')
            exec(code,env);return env['qemu_argv']('install',True)
        self.assertEqual(argv(original,'0'),argv(changed,'0'))
        enabled=argv(changed,'1');self.assertIn('hda-output,audiodev=native_audio',enabled)
        self.assertTrue(any('wav,id=native_audio' in arg for arg in enabled))
        self.assertFalse(any('/dev/snd' in arg or 'null' in arg for arg in enabled))


class LifecycleControls(unittest.TestCase):
    def synthetic_run(self, fail):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);e=root/'evidence';e.mkdir()
            args=SimpleNamespace(source=root/'candidate-fe',bundle=HERE,inputs=root/'inputs',evidence=e)
            calls=[]
            def execute(argv,log,seconds,cwd,env,container):
                self.assertEqual(env['CONTAINER_ENGINE'],'docker')
                self.assertTrue(container.startswith('arctic-paired-native-'))
                log.write_text('synthetic host control; no VM')
                if 'prepare-vm-tools.sh' in ' '.join(argv):
                    self.assertEqual(cwd,args.source);(e/'vm-prepared-image-id.txt').write_text('sha256:'+'1'*64);return
                calls.append(argv)
                self.assertEqual(env['ARCTIC_NATIVE_AUDIO_FIXTURE'],'1')
                self.assertEqual(env['ARCTIC_NATIVE_LAUNCHER'],str(HERE/'native-launcher-v5.py'))
                self.assertEqual(argv[argv.index('--boot-network')+1],'offline')
                self.assertNotIn('--stage',argv)
                self.assertEqual(Path(argv[1]),args.bundle.parents[1]/'tools/test-install.sh')
                vm=root/'native-vm';vm.mkdir()
                (vm/'serial-install.log').write_text(harness_live())
                AudioControls().make_wav(vm/'native-audio-install.wav')
                if fail:raise RuntimeError('induced harness failure after live evidence')
                (vm/'serial-boot.log').write_text(harness_installed())
                AudioControls().make_wav(vm/'native-audio-boot.wav')
            with mock.patch.object(N,'verify'),mock.patch.object(N,'check_physical',return_value={'synthetic_authority':True}),mock.patch.object(N.R,'verify_iso',return_value={'synthetic_authority':True}),mock.patch.object(N.R,'require_docker',return_value='28.0.0'),mock.patch.object(Path,'is_char_device',return_value=True),mock.patch.object(N.R,'pinned_file'),mock.patch.object(N.R,'execute',side_effect=execute),mock.patch.object(N.subprocess,'run'),mock.patch.object(N.signal,'signal'),mock.patch.dict(os.environ,ci()):
                if fail:
                    with self.assertRaisesRegex(RuntimeError,'induced harness failure'):N.run(args)
                else:N.run(args)
            self.assertEqual(len(calls),1)
            self.assertTrue((e/'native-live'/'report.json').exists())
            self.assertTrue((e/'virtual-audio'/'native-audio-install.wav').exists())
            state=json.loads((e/'execution.json').read_text())
            self.assertEqual(state['status'],'failed_or_unrun' if fail else 'limited_native_live_installed_smoke_passed_pending_visual_audio_review')
            self.assertFalse(state['release_acceptance'])

    def test_single_fresh_live_install_first_boot_success(self):self.synthetic_run(False)
    def test_harness_failure_preserves_live_guest_and_audio(self):self.synthetic_run(True)


class WorkflowControls(unittest.TestCase):
    def test_new_base_ancestry_exact_manifest_and_product_scope_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);bundle=root/'tools/native-functional-v5';bundle.mkdir(parents=True)
            args=SimpleNamespace(source=root/'candidate',bundle=bundle)
            manifest=dict(schema=4,candidate_source=N.R.SOURCE,qualification_base=N.QUALIFICATION_BASE,
                          execution_base=N.EXECUTION_BASE,files={p:'1'*64 for p in N.EXECUTION_FILES})
            (bundle/'execution-pins-v5.json').write_text(json.dumps(manifest))
            for name in ('frozen-v2-pins-v5.json','source-provenance-v5.json','adapter-parity-v5.json'):
                shutil.copyfile(HERE/name,bundle/name)
            valid='.github/workflows/iso.yml\ntools/test-install.sh\ntools/native-functional-v5/native_smoke.py\n'
            for extra in ('','shell/Theme.qml\n','tools/native-functional-runner/native_smoke.py\n','iso/kiwi/config.sh\n'):
                outputs=[N.R.SOURCE+'\n','','3'*40+'\n','',valid+extra]
                with mock.patch.dict(os.environ,ci()),mock.patch.object(N.subprocess,'check_output',side_effect=outputs),mock.patch.object(N.subprocess,'run') as ancestry,mock.patch.object(N.R,'pinned_file') as pinned:
                    if extra:
                        with self.assertRaisesRegex(RuntimeError,'scope'):N.verify_sources(args)
                    else:
                        self.assertEqual(N.verify_sources(args),manifest)
                        ancestry.assert_called_once_with(['git','-C',str(root),'merge-base','--is-ancestor',N.EXECUTION_BASE,'3'*40],check=True,timeout=30)
                        self.assertIn(mock.call(root/'tools/tests/test_performance_harness.py','5a9b35e0dea7ba476f013376c8da301f32ac44788743e50cc3cf3804d43faca3'),pinned.call_args_list)
    def test_native_only_mode_omits_build_updates_recovery_and_performance(self):
        value=yaml.load(native_workflow_path().read_text(),Loader=yaml.BaseLoader)
        jobs=value['jobs'];self.assertIn('!inputs.same_iso_native_smoke',jobs['iso']['if'])
        for name in ('same-iso-installs','same-iso-boot-evidence'):self.assertIn('!inputs.same_iso_native_smoke',jobs[name]['if'])
        native=jobs['same-iso-native-functional'];self.assertEqual(native['permissions'],{'contents':'read','actions':'read'})
        self.assertFalse('matrix' in native)
        steps=native['steps'];download=[s for s in steps if s.get('uses','').startswith('actions/download-artifact')][0]
        self.assertEqual(download['with']['artifact-ids'],'11434226349');self.assertEqual(download['with']['run-id'],'37507582946')
        commands='\n'.join(s.get('run','') for s in steps)
        self.assertFalse(any(term in commands for term in ('build-iso','dnf','nix','arctic-update')))
        upload=[s for s in steps if s.get('uses','').startswith('actions/upload-artifact')][0]
        self.assertEqual(upload['with']['path'],'${{ env.NATIVE_ROOT }}/evidence/')

    def test_workflow_path_uses_actual_mapped_layout_and_audit_precedence(self):
        original=native_workflow_path().read_text()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);bundle=root/'tools/native-functional-v5';bundle.mkdir(parents=True)
            deployed=root/'.github/workflows/iso.yml';deployed.parent.mkdir(parents=True);deployed.write_text(original)
            with mock.patch.dict(globals(),HERE=bundle):
                self.assertEqual(native_workflow_path(),deployed)
                self.test_native_only_mode_omits_build_updates_recovery_and_performance()
                audit=bundle/'registered-iso-native-v5.yml';audit.write_text(original)
                self.assertEqual(native_workflow_path(),audit)
                self.test_native_only_mode_omits_build_updates_recovery_and_performance()

    def test_workflow_path_missing_both_fails_and_audit_only_still_works(self):
        original=native_workflow_path().read_text()
        with tempfile.TemporaryDirectory() as folder:
            bundle=Path(folder)/'tools/native-functional-v5';bundle.mkdir(parents=True)
            with mock.patch.dict(globals(),HERE=bundle):
                with self.assertRaisesRegex(FileNotFoundError,'audit and deployed'):
                    self.test_native_only_mode_omits_build_updates_recovery_and_performance()
                (bundle/'registered-iso-native-v5.yml').write_text(original)
                self.test_native_only_mode_omits_build_updates_recovery_and_performance()

    def test_selected_adverse_workflow_cannot_fall_back_or_weaken_guards(self):
        original=native_workflow_path().read_text()
        adverse=original.replace('!inputs.same_iso_native_smoke','inputs.same_iso_native_smoke')
        self.assertNotEqual(adverse,original)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);bundle=root/'tools/native-functional-v5';bundle.mkdir(parents=True)
            deployed=root/'.github/workflows/iso.yml';deployed.parent.mkdir(parents=True);deployed.write_text(adverse)
            with mock.patch.dict(globals(),HERE=bundle):
                with self.assertRaises(AssertionError):
                    self.test_native_only_mode_omits_build_updates_recovery_and_performance()
                deployed.write_text(original)
                (bundle/'registered-iso-native-v5.yml').write_text(adverse)
                with self.assertRaises(AssertionError):
                    self.test_native_only_mode_omits_build_updates_recovery_and_performance()

    def test_mode_engine_release_and_run_negative_controls(self):
        N.validate_ci(ci())
        for name,value in [('NATIVE_SMOKE_MODE','false'),('RECOVERY_MODE','true'),('RELEASE_REQUESTED','true'),('CONTAINER_ENGINE','podman'),('GITHUB_SHA',N.QUALIFICATION_BASE),('GITHUB_SHA',N.EXECUTION_BASE),('GITHUB_RUN_ID','37520174911'),('GITHUB_RUN_ID','37525639962'),('NIX_REQUESTED','true'),('PERFORMANCE_REQUESTED','true'),('BOOT_TEST_REQUESTED','true')]:
            env=ci();env[name]=value
            with self.subTest(name=name),self.assertRaises(RuntimeError):N.validate_ci(env)

    def test_no_vm_after_input_verification_failure(self):
        with mock.patch.object(N,'verify',side_effect=RuntimeError('ISO checksum mismatch')),mock.patch.object(N.R,'execute') as execute:
            with self.assertRaises(RuntimeError):N.run(SimpleNamespace())
            execute.assert_not_called()


if __name__=='__main__':unittest.main(verbosity=2)
