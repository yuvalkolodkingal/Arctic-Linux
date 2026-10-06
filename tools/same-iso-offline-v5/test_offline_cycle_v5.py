"""Bounded host controls only; all VM/process commands are intercepted."""
import ast
import copy
import importlib.util
import io
import hashlib
import socket
import stat
import threading
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import yaml
from unittest.mock import Mock,patch

HERE=Path(__file__).resolve().parent
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
helper=load('cycle_helper_v5',HERE/'offline-update-cycle-v5.py')
driver=load('cycle_driver_v5',HERE/'offline-only-recovery-v5.py')
DEFAULT_JOBS={
    'iso':'745a7eaf87cd79ee518aeb027aabe6856e9c77132def17cd3c734d773473c07c',
    'same-iso-installs':'fbe035484e489c8036ed53bc5203829ccad40ab6c73f54562427f583992b792e',
    'same-iso-boot-evidence':'75c1ef851c7fcb1004dec6f3ba306f68d335d0ebc7b9d9fa43233e267c4add9a'}
TOP_LEVEL_SHA='7b003970763675fc060e707632fa86d9973b4b7cb2b123944087c52ecf7c7691'
def canonical_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def read_workflow(bundle=HERE):
    audit=bundle/'registered-iso-offline-cycle-v5.yml'
    # Select once. A present bad audit file cannot fall through to deployment.
    selected=audit if audit.exists() or audit.is_symlink() else bundle.parents[1]/'.github/workflows/iso.yml'
    driver.base.require(selected.is_file() and not selected.is_symlink(),'Selected workflow absent or linked')
    text=selected.read_text()
    try:data=yaml.safe_load(text)
    except yaml.YAMLError:raise RuntimeError('Selected workflow malformed') from None
    driver.base.require(isinstance(data,dict) and isinstance(data.get('jobs'),dict),'Selected workflow malformed')
    # PyYAML's YAML 1.1 parser reads the Actions `on` key as boolean True.
    if True in data:data['on']=data.pop(True)
    driver.base.require(set(data['jobs'])==set(DEFAULT_JOBS)|{'same-iso-offline-cycle-v5'},'Unexpected workflow jobs')
    for name,wanted in DEFAULT_JOBS.items():
        driver.base.require(canonical_hash(data['jobs'][name])==wanted,'Default workflow job changed: '+name)
    driver.base.require(canonical_hash({key:value for key,value in data.items() if key!='jobs'})==TOP_LEVEL_SHA,
        'Default workflow inputs/permissions/top-level configuration changed')
    return text
ACTUAL=Path(os.environ.get('ARCTIC_OFFLINE_V4_CONTROL_EVIDENCE',
    str(HERE.parent/'same-iso-recovery/results-37520174911/arctic-offline/first-boot')))
def actual_fixture():
    for name,sha in {'serial-boot.log':'e02d56464396374a5955afb640f820fab2a4e62aadb58d770912bf95c78ee56e',
            'serial-install.log':'7006a8083ba26ffefbfc18f737dc182f5de0fff16a53cf4f5ccb2cb863558c34'}.items():
        driver.base.pinned_file(ACTUAL/name,sha)
    return ACTUAL

def good_cycle():
    owner=dict(uid=os.getuid(),gid=os.getgid())
    return dict(disk_owner=owner,disk_identity={name:owner|dict(mode=0o644,device=1,inode=2)
        for name in ('/out/target.qcow2','/out/OVMF_VARS.fd')},
        first_install={'luks_uuid':'12345678-1234-1234-1234-123456789abc','serial_install_sha256':'a'*64},unlock_prompt_evidence={'luks_uuid':'12345678-1234-1234-1234-123456789abc','boot_id':'b'*32,'unique_current_prompt':True,'transport':'owned bidirectional ttyS0 serial'},serial_peer_verified=True,unlock_attempts=1,raw_serial_complete=True,serial_eof_observed=True,passphrase_echo_detected=False,unlock_prompt_seen=True,passphrase_submitted=True,guest_exited=True,
        qemu_exit_code=0,timed_out=False,events=[dict(received_monotonic=40.0,
            reply=dict(event='SHUTDOWN',data=dict(guest=True,reason='guest-reset')))])

class CycleControls(unittest.TestCase):
    def test_guest_reset_or_shutdown_only_requires_third_boot(self):
        for reason in ('guest-reset','guest-shutdown'):
            value=good_cycle();value['events'][0]['reply']['data']['reason']=reason
            proof=helper.validate_cycle(value)
            self.assertEqual(proof['status'],'guest_cycle_exit_observed_third_boot_required')
            self.assertIn('UNRUN',proof['update_qualification'])
    def test_zero_exit_without_shutdown_host_error_panic_watchdog_duplicate_fail(self):
        values=[good_cycle()|dict(events=[])]
        for guest,reason in ((False,'guest-reset'),(True,'host-signal'),(True,'host-qmp-quit'),(True,'host-error'),(True,'guest-panic'),(1,'guest-reset')):
            value=good_cycle();value['events'][0]['reply']['data']=dict(guest=guest,reason=reason);values.append(value)
        value=good_cycle();value['events']*=2;values.append(value)
        for event in ('GUEST_PANICKED','WATCHDOG'):
            value=good_cycle();value['events'].append(dict(reply=dict(event=event)));values.append(value)
        for value in values:
            with self.subTest(value=value),self.assertRaises(RuntimeError):helper.validate_cycle(value)
    def test_exit_before_unlock_timeout_nonzero_and_boolean_exit_fail(self):
        for changes in (dict(unlock_prompt_seen=False),dict(passphrase_submitted=False),dict(guest_exited=False),
            dict(timed_out=True),dict(qemu_exit_code=1),dict(qemu_exit_code=False)):
            with self.subTest(changes=changes),self.assertRaises(RuntimeError):helper.validate_cycle(good_cycle()|changes)
    def test_only_exact_fresh_disposable_unlinked_paths_allowed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);disk=root/'target.qcow2';vars=root/'OVMF_VARS.fd';out=root/'offline-update-cycle'
            disk.write_bytes(b'disposable');vars.write_bytes(b'vars')
            helper.validate_paths(disk,vars,out,root)
            for values in ((root/'outside.qcow2',vars,out),(disk,root/'foreign-vars',out),(disk,vars,root/'other-out')):
                with self.assertRaises(RuntimeError):helper.validate_paths(*values,root)
            out.mkdir()
            with self.assertRaises(RuntimeError):helper.validate_paths(disk,vars,out,root)
            out.rmdir();disk.unlink();disk.symlink_to(vars)
            with self.assertRaises(RuntimeError):helper.validate_paths(disk,vars,out,root)
    def test_explicit_host_disk_owner_survives_root_container_without_ownership_relaxation(self):
        owner=dict(uid=os.getuid(),gid=os.getgid())
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);disk=root/'target.qcow2';variables=root/'OVMF_VARS.fd';out=root/'offline-update-cycle'
            disk.write_bytes(b'owned disk');variables.write_bytes(b'owned vars')
            with patch.object(helper.os,'getuid',return_value=owner['uid']+100):
                proof=helper.validate_paths(disk,variables,out,root,owner)
                self.assertEqual(proof[str(disk)]['uid'],owner['uid'])
                with self.assertRaises(RuntimeError):helper.validate_paths(disk,variables,out,root)
            for changed in (owner|dict(uid=owner['uid']+1),owner|dict(gid=owner['gid']+1),owner|dict(uid=True)):
                with self.assertRaises(RuntimeError):helper.validate_paths(disk,variables,out,root,changed)
            disk.chmod(0o664)
            with self.assertRaises(RuntimeError):helper.validate_paths(disk,variables,out,root,owner)
    def test_cycle_argv_is_kvm_restricted_network_no_cd_or_security_bypass(self):
        argv=helper.qemu_argv(Path('/out/target.qcow2'),Path('/out/OVMF_VARS.fd'),
            Path('/out/offline-update-cycle'),Path('/firmware/OVMF_CODE.fd'),'/tmp/arctic-offline-v5-abcdefgh/qmp.sock','/tmp/arctic-offline-v5-abcdefgh/serial.sock')
        self.assertEqual(argv[argv.index('-accel')+1],'kvm')
        self.assertEqual(argv[argv.index('-netdev')+1],'user,id=net0,restrict=on')
        self.assertIn('-no-reboot',argv)
        self.assertFalse(any('data.iso' in item or 'cdrom' in item or 'tcg' in item for item in argv))
        self.assertEqual(helper.CONSOLE_APPEND,'console=tty0 console=ttyS0,115200 systemd.journald.forward_to_console=1')
        with self.assertRaises(RuntimeError):helper.qemu_argv(Path('/out/a,b'),Path('/vars'),Path('/out/result'),Path('/firmware'),'/tmp/qmp','/tmp/serial')
    def test_event_capture_subclass_preserves_original_class_and_actual_event_stream(self):
        class Original:
            def cmd(self,name,**args):return 'original'
        original=Original.cmd
        fake=SimpleNamespace(VM=Original,QMPError=RuntimeError)
        VM=helper.observed_vm_type(fake)
        with tempfile.TemporaryDirectory() as temporary:
            vm=VM.__new__(VM);vm.events=[];vm.event_log=Path(temporary)/'events.jsonl'
            class Duplex:
                def __init__(self):self.lines=iter([json.dumps(good_cycle()['events'][0]['reply'])+'\n','{"return": {}}\n']);self.written=[]
                def write(self,value):self.written.append(value)
                def flush(self):pass
                def readline(self):return next(self.lines,'')
            vm.f=Duplex();reply=vm.cmd('query-status')
            self.assertEqual(reply,{'return':{}});self.assertEqual(vm.events[0]['reply']['event'],'SHUTDOWN')
            self.assertEqual(json.loads(vm.event_log.read_text())['reply'],vm.events[0]['reply'])
            self.assertIs(Original.cmd,original)
            with self.assertRaises(RuntimeError):vm.cmd('query-status')
    def test_observation_requires_menu_and_luks_never_blind_types_login(self):
        clock_values=iter(range(0,10000,100))
        vm=Mock();vm.alive.return_value=True;vm.shot.return_value='screen'
        vmtest=SimpleNamespace(looks_like_boot_menu=lambda _:False,classify=lambda _:'other',log=lambda _:None)
        with self.assertRaisesRegex(RuntimeError,'menu'):
            helper.observe(vm,vmtest,{},300,Mock(data=b'',closed=False),{'luks_uuid':'unused'},clock=lambda:next(clock_values),pause=lambda _:None)
        vm.type_text.assert_not_called()
        clock_values=iter(range(0,10000,100));vm.reset_mock();vm.alive.return_value=True;vm.shot.return_value='screen'
        vmtest.looks_like_boot_menu=lambda _:True
        with self.assertRaisesRegex(RuntimeError,'serial root password'):
            helper.observe(vm,vmtest,{},300,Mock(data=b'',closed=False),{'luks_uuid':'unused'},clock=lambda:next(clock_values),pause=lambda _:None)
        self.assertEqual(vm.type_text.call_args_list[0].args[0],' '+helper.CONSOLE_APPEND)
        self.assertEqual(vm.type_text.call_count,1)
    def test_qmp_exception_is_not_expected_guest_cycle_success(self):
        vm=Mock();vm.alive.return_value=True;vm.shot.return_value='menu';vm.keys.side_effect=RuntimeError('QMP broken')
        vmtest=SimpleNamespace(looks_like_boot_menu=lambda _:True)
        with self.assertRaisesRegex(RuntimeError,'QMP broken'):helper.observe(vm,vmtest,{},300,Mock(data=b'',closed=False),{'luks_uuid':'unused'})

class DriverControls(unittest.TestCase):
    def test_exclusive_offline_branch_and_release_mode_fail_closed(self):
        env=dict(GITHUB_ACTIONS='true',GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REPOSITORY=driver.base.REPOSITORY,
            GITHUB_API_URL='https://api.github.com',RECOVERY_MODE='true',RELEASE_REQUESTED='false',
            GITHUB_SHA='a'*40,GITHUB_RUN_ID='99999',GITHUB_RUN_ATTEMPT='1',OFFLINE_CYCLE_RECOVERY_MODE='true',
            SAME_ISO_RECOVERY_REQUESTED='false',GITHUB_REF='refs/heads/'+driver.BRANCH)
        driver.validate_ci(env)
        for changes in (dict(RELEASE_REQUESTED='true'),dict(SAME_ISO_RECOVERY_REQUESTED='true'),dict(OFFLINE_CYCLE_RECOVERY_MODE='false'),
            dict(GITHUB_REF='refs/heads/main'),dict(GITHUB_SHA=driver.base.SOURCE),dict(GITHUB_EVENT_NAME='push')):
            with self.subTest(changes=changes),self.assertRaises(RuntimeError):driver.validate_ci(env|changes)
    def test_actual_preserved_first_pass_is_valid_but_no_third_boot_claim(self):
        actual=actual_fixture()
        proof=driver.installed_success(actual,'first-boot',HERE)
        self.assertEqual(proof['checks']['signed-offline-update-ready'],'passed')
        self.assertNotIn('signed-offline-update-completed',proof['checks'])
        with self.assertRaises(RuntimeError):driver.installed_success(actual,'third-boot',HERE)
    def test_missing_or_duplicate_live_gates_and_failed_staging_reject_zero_exit(self):
        actual=actual_fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            original_live=(actual/'serial-install.log').read_text()
            original_boot=(actual/'serial-boot.log').read_text()
            (root/'serial-boot.log').write_text(original_boot)
            lines=original_live.splitlines()
            browser=next(line for line in lines if line.startswith('ARCTIC-NIX-ACCEPTANCE ') and '"check": "non-chromium-browser"' in line)
            for text in (original_live.replace(browser+'\n',''),original_live+browser+'\n'):
                (root/'serial-install.log').write_text(text)
                with self.assertRaises(RuntimeError):driver.installed_success(root,'first-boot',HERE)
            (root/'serial-install.log').write_text(original_live)
            text=original_boot.replace('"check": "signed-offline-update-ready", "status": "passed"',
                '"check": "signed-offline-update-ready", "status": "failed"')
            self.assertNotEqual(text,original_boot);(root/'serial-boot.log').write_text(text)
            with self.assertRaises(RuntimeError):driver.installed_success(root,'first-boot',HERE)
    def test_cycle_container_is_network_none_and_only_owned_rw_disk_mount(self):
        args=SimpleNamespace(source=Path('/candidate'),bundle=Path('/qualification/tools/same-iso-offline-v5'),evidence=Path('/evidence'))
        with patch.object(Path,'read_text',return_value=json.dumps({'serial-install.log':{'sha256':'c'*64}})),patch.object(driver.base,'pinned_file'):
            argv=driver.cycle_command(args,Path('/fresh/run/vm'),'sha256:'+'a'*64,'arctic-paired-offline-v5-test')
        self.assertEqual(argv[-2:],['--first-install-sha256','c'*64])
        self.assertEqual(argv[argv.index('--disk-owner-uid')+1],str(os.getuid()))
        self.assertEqual(argv[argv.index('--disk-owner-gid')+1],str(os.getgid()))
        self.assertEqual(argv[argv.index('--network')+1],'none');self.assertIn('--device',argv)
        mounts=[argv[index+1] for index,item in enumerate(argv) if item=='-v']
        self.assertEqual(sum(value.endswith(':rw') for value in mounts),1)
        self.assertEqual(mounts[0],'/fresh/run/vm:/out:rw')
        self.assertNotIn('--privileged',argv);self.assertNotIn('--security-opt',argv)
    def test_actual_cycle_log_argv_and_raw_events_must_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            vm=Path(temporary);folder=vm/'offline-update-cycle';folder.mkdir()
            value=good_cycle()|dict(status='guest_cycle_exit_observed_third_boot_required',platform='QEMU_KVM',
                network='restricted_offline',transient_console_append=helper.CONSOLE_APPEND,
                actual_qemu_argv=helper.qemu_argv(Path('/out/target.qcow2'),Path('/out/OVMF_VARS.fd'),
                    Path('/out/offline-update-cycle'),Path('/usr/share/edk2/ovmf/OVMF_CODE.fd'),
                    '/tmp/arctic-offline-v5-abcdefgh/qmp.sock','/tmp/arctic-offline-v5-abcdefgh/serial.sock'))
            current=current_fixture()
            for name in ('target.qcow2','OVMF_VARS.fd'):(vm/name).write_bytes(b'owned fresh fixture')
            value['disk_identity']={str(Path('/out')/Path(name).name):proof for name,proof in
                helper.input_identity(vm/'target.qcow2',vm/'OVMF_VARS.fd').items()}
            value.update(first_install=current['first'],unlock_prompt_evidence=helper.serial_prompt(current['serial'],current['first']),raw_serial_bytes=len(current['serial']),raw_serial_sha256=hashlib.sha256(current['serial']).hexdigest())
            result=folder/'cycle-result.json';events=folder/'qmp-events.jsonl';serial=folder/'serial-offline-cycle.log'
            def write():result.write_text(json.dumps(value));events.write_text('\n'.join(json.dumps(row) for row in value['events'])+'\n')
            (vm/'serial-install.log').write_bytes(current['install']);serial.write_bytes(current['serial']);write()
            self.assertEqual(driver.cycle_success(vm,INSTALL_SHA)['network'],'restricted_offline')
            for change in ('network','argv','events','serial'):
                original=copy.deepcopy(value)
                if change=='network':value['network']='online'
                elif change=='argv':value['actual_qemu_argv']=list(value['actual_qemu_argv']);value['actual_qemu_argv'][value['actual_qemu_argv'].index('user,id=net0,restrict=on')]='user,id=net0'
                write()
                if change=='events':events.write_text('')
                if change=='serial':serial.unlink()
                with self.subTest(change=change),self.assertRaises(RuntimeError):driver.cycle_success(vm,INSTALL_SHA)
                value=original;serial.write_bytes(current['serial'])
    def test_all_three_phases_and_first_cycle_third_failures_stop_qualification(self):
        for fail in (None,'first-boot','offline-update-cycle','third-boot'):
            with tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);evidence=root/'evidence';evidence.mkdir()
                args=SimpleNamespace(evidence=evidence,source=root/'source',bundle=HERE,inputs=root/'inputs')
                calls=[]
                def execute(argv,log,*unused):
                    phase=log.stem.removesuffix('-harness')
                    if phase=='provision':(evidence/'vm-prepared-image-id.txt').write_text('sha256:'+'a'*64)
                    else:
                        calls.append(phase)
                        if fail==phase:raise RuntimeError('injected '+phase+' failure')
                patches=[patch.object(driver,'verify'),patch.object(driver,'verify_sources'),patch.object(driver.base,'verify_iso'),
                    patch.object(driver.base,'require_docker',return_value='fixture'),patch.object(Path,'is_char_device',return_value=True),
                    patch.object(driver.base,'execute',side_effect=execute),patch.object(driver.base,'pinned_file'),
                    patch.object(driver,'installed_success',return_value={'checks':'fixture only'}),patch.object(driver,'cycle_success',return_value={'status':'cycle pending third'}),
                    patch.object(driver.base,'preserve_phase',return_value={'vm-toolchain.txt':{'sha256':'same'},'serial-boot.log':{},'serial-install.log':{'sha256':'c'*64}}),
                    patch.object(driver,'preserve_cycle',return_value={}),patch.object(driver,'cycle_command',return_value=['intercepted-cycle']),patch.object(driver.signal,'signal'),
                    patch.object(driver.subprocess,'run'),patch.dict(driver.os.environ,{'GITHUB_SHA':'b'*40})]
                from contextlib import ExitStack
                with ExitStack() as stack:
                    for item in patches:stack.enter_context(item)
                    if fail:
                        with self.assertRaisesRegex(RuntimeError,'injected'):driver.run(args)
                    else:driver.run(args)
                record=json.loads((evidence/'execution.json').read_text())
                expected=['first-boot','offline-update-cycle','third-boot']
                self.assertEqual(calls,expected if fail is None else expected[:expected.index(fail)+1])
                self.assertEqual(record['status'],'old_stable_signed_offline_three_phase_vm_acceptance_passed' if fail is None else 'failed_or_unrun')
                self.assertFalse(record['canonical_new_stable_qualification'])
    def test_iso_recheck_failure_after_provisioning_never_starts_first_vm(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);evidence=root/'evidence';evidence.mkdir()
            args=SimpleNamespace(evidence=evidence,source=root/'source',bundle=HERE,inputs=root/'inputs')
            calls=[]
            def execute(argv,log,*unused):
                calls.append(log.stem);(evidence/'vm-prepared-image-id.txt').write_text('sha256:'+'a'*64)
            with (patch.object(driver,'verify'),patch.object(driver,'verify_sources'),patch.object(driver.base,'verify_iso',side_effect=RuntimeError('ISO changed')),
                    patch.object(driver.base,'require_docker',return_value='fixture'),patch.object(Path,'is_char_device',return_value=True),
                    patch.object(driver.base,'execute',side_effect=execute),patch.object(driver.base,'pinned_file'),
                    patch.object(driver.signal,'signal'),patch.object(driver.subprocess,'run'),patch.dict(driver.os.environ,{'GITHUB_SHA':'b'*40})):
                with self.assertRaisesRegex(RuntimeError,'ISO changed'):driver.run(args)
            self.assertEqual(calls,['provision'])
    def test_both_original_jobs_and_build_skip_selected_offline_cycle(self):
        text=read_workflow()
        self.assertIn('(!inputs.same_iso_recovery && !inputs.offline_cycle_recovery)',text)
        self.assertEqual(text.count("inputs.same_iso_recovery && !inputs.offline_cycle_recovery }}"),2)
        v5=text[text.index('  same-iso-offline-cycle-v5:'):]
        self.assertIn("if: ${{ github.event_name == 'workflow_dispatch' && inputs.offline_cycle_recovery }}",v5)
        self.assertNotIn('&& !inputs.same_iso_recovery }}',v5)
        self.assertNotIn('contents: write',text[text.index('  same-iso-offline-cycle-v5:'):])
    def test_deployed_workflow_layout_and_present_audit_precedence(self):
        text=read_workflow()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);bundle=root/'tools/same-iso-offline-v5';bundle.mkdir(parents=True)
            deployed=root/'.github/workflows/iso.yml';deployed.parent.mkdir(parents=True);deployed.write_text(text)
            self.assertEqual(read_workflow(bundle),text)
            audit=bundle/'registered-iso-offline-cycle-v5.yml';audit.write_text(text)
            deployed.write_text('invalid deployed YAML: [')
            self.assertEqual(read_workflow(bundle),text)
            audit.write_text('invalid audit YAML: [');deployed.write_text(text)
            with self.assertRaisesRegex(RuntimeError,'malformed'):read_workflow(bundle)
            audit.unlink();deployed.unlink()
            with self.assertRaisesRegex(RuntimeError,'absent'):read_workflow(bundle)
            deployed.write_text(text);audit.symlink_to(deployed)
            with self.assertRaisesRegex(RuntimeError,'linked'):read_workflow(bundle)
    def test_action_major_inputs_permissions_and_default_jobs_adverse_controls(self):
        text=read_workflow()
        bad=[text.replace('actions/checkout@v4','actions/checkout@v5',1),
             text.replace('actions/cache/restore@v4','actions/cache/restore@v5',1),
             text.replace('actions/upload-artifact@v4','actions/upload-artifact@v5',1),
             text.replace('default: false','default: true',1),text.replace('contents: read','contents: write',1)]
        self.assertTrue(all(value!=text for value in bad))
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);bundle=root/'tools/same-iso-offline-v5';bundle.mkdir(parents=True)
            audit=bundle/'registered-iso-offline-cycle-v5.yml'
            for value in bad:
                audit.write_text(value)
                with self.assertRaisesRegex(RuntimeError,'changed'):read_workflow(bundle)
    def test_original_primitives_and_frozen_checker_bytes_unchanged(self):
        pins={'vm-only-recovery-v2.py':driver.BASE_SHA256,'guest-check-offline-v1.py':driver.OFFLINE_CHECKER_SHA256,
            'README-v1.md':driver.base.BUNDLE_PINS['README-v1.md'],
            'review-ready-v1.json':driver.base.BUNDLE_PINS['review-ready-v1.json']}
        for name,sha in pins.items():self.assertEqual(driver.base.digest(HERE/name),sha,name)
        tree=ast.parse((HERE/'offline-only-recovery-v5.py').read_text())
        assignments=[node for node in ast.walk(tree) if isinstance(node,(ast.Assign,ast.AnnAssign))]
        self.assertFalse(any(isinstance(target,ast.Attribute) and isinstance(target.value,ast.Name) and target.value.id=='base'
            for node in assignments for target in (node.targets if isinstance(node,ast.Assign) else [node.target])))
    def test_pinned_original_install_harness_chowns_to_host_writer_identity(self):
        candidates=(HERE.parents[1]/'tools/test-install.sh',Path.cwd()/'tools/test-install.sh')
        source=next(path for path in candidates if path.is_file())
        driver.base.pinned_file(source,driver.base.SOURCE_PINS['tools/test-install.sh'])
        text=source.read_text()
        self.assertIn('chown -R "$HOST_UID:$HOST_GID" "$OUT"',text)
        self.assertIn('-e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)"',text)

CURRENT=Path(os.environ.get('ARCTIC_OFFLINE_V5_CONTROL_EVIDENCE',
    str(HERE.parent/'offline-cycle-results-37527394624/evidence')))
INSTALL_SHA='60119dc67f4a1ab57fa405179d625f6014deaf93e1dafe5e4ba42567dc4cfd57'
SERIAL_SHA='ce44297abc14757f5b1d440dde60fe4dca498f0d557cd94743e93a0b03660808'

def current_fixture():
    install=CURRENT/'first-boot/serial-install.log'
    serial=CURRENT/'offline-update-cycle/serial-offline-cycle.log'
    driver.base.pinned_file(install,INSTALL_SHA);driver.base.pinned_file(serial,SERIAL_SHA)
    return dict(install=install.read_bytes(),serial=serial.read_bytes(),
        first=helper.first_install_root(install,INSTALL_SHA))

def bare_channel(data=b''):
    channel=helper.SerialChannel.__new__(helper.SerialChannel)
    channel.data=bytearray(data);channel.after=bytearray();channel.attempts=0
    channel.closed=False;channel.persisted=False;channel.echo_rejected=False
    channel.stream=io.BytesIO();channel.stream.write(data)
    channel.process=Mock();channel.process.poll.return_value=None
    channel.sock=Mock();channel.verify_peer=Mock()
    return channel

class SerialControls(unittest.TestCase):
    def test_actual_failed_v4_text_request_matches_its_fresh_root(self):
        actual=current_fixture();proof=helper.serial_prompt(actual['serial'],actual['first'])
        self.assertEqual(proof['luks_uuid'],'acaf0bbe-5125-44ff-bda7-aedbab9c1169')
        self.assertEqual(proof['boot_id'],'7a0bb862f43a41f19da4639c387d212f')
        self.assertEqual(proof['transport'],'owned bidirectional ttyS0 serial')
        self.assertTrue(proof['unique_current_prompt'])

    def test_first_install_wrong_hash_device_duplicates_failed_exit_and_link_reject(self):
        actual=current_fixture()
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'serial-install.log';path.write_bytes(actual['install'])
            with self.assertRaises(RuntimeError):helper.first_install_root(path,'0'*64)
            mapping=next(line for line in actual['install'].splitlines() if line.startswith(b'$ cryptsetup open '))
            cases=[actual['install']+mapping+b'\n',actual['install'].replace(b'/dev/vda4 luks-',b'/dev/vda5 luks-'),
                   actual['install'].replace(b'ARCTIC-INSTALL-EXIT=0',b'ARCTIC-INSTALL-EXIT=1')]
            for data in cases:
                path.write_bytes(data)
                with self.assertRaises(RuntimeError):helper.first_install_root(path,hashlib.sha256(data).hexdigest())
            link=path.parent/'linked.log';link.symlink_to(path)
            with self.assertRaises(RuntimeError):helper.first_install_root(link,hashlib.sha256(path.read_bytes()).hexdigest())

    def test_wrong_root_console_boot_order_stale_duplicate_and_login_paths_reject(self):
        actual=current_fixture();raw=actual['serial'];first=actual['first']
        prompt=b'Please enter passphrase for disk Arctic root (luks-'+first['luks_uuid'].encode()+b')::'
        self.assertIsNone(helper.serial_prompt(raw.replace(prompt,b''),first))
        bad=[raw.replace(first['luks_uuid'].encode(),b'12345678-1234-1234-1234-123456789abc'),
             raw.replace(b'console=tty0 console=ttyS0,115200',b'console=ttyS0,115200 console=tty0'),
             raw.replace(b'bootid=',b'missing_bootid='),raw+prompt,
             prompt+b'\n'+raw.replace(prompt,b''),raw+b'\nlogin: ',raw+b'\nNo key available',
             raw.replace(b'bootid=7a0bb862f43a41f19da4639c387d212f',b'bootid=00000000000000000000000000000000')+
                b'bootid=11111111111111111111111111111111;pid=1;comm=systemd;type=boot']
        # Removing a marker must remove the substring as well, not rename its key.
        bad[2]=raw.replace(b'bootid=7a0bb862f43a41f19da4639c387d212f',b'bootxxxx')
        for index,data in enumerate(bad):
            with self.subTest(case=index),self.assertRaises(RuntimeError):helper.serial_prompt(data,first)
        with self.assertRaises(RuntimeError):helper.serial_prompt(raw,first|dict(luks_uuid='12345678-1234-1234-1234-123456789abc'))

    def test_fragmented_guest_output_reassembles_request_without_sending_input(self):
        actual=current_fixture();channel=bare_channel();channel.process.poll.return_value=0
        chunks=[actual['serial'][i:i+11] for i in range(0,len(actual['serial']),11)]+[b'']
        channel.sock.recv.side_effect=chunks
        while not channel.closed:channel.pump()
        self.assertEqual(bytes(channel.data),actual['serial'])
        self.assertEqual(helper.serial_prompt(channel.data,actual['first'])['luks_uuid'],actual['first']['luks_uuid'])
        channel.sock.sendall.assert_not_called();self.assertEqual(channel.stream.getvalue(),actual['serial'])

    def test_peer_pid_uid_epoch_executable_inode_and_type_controls(self):
        identity=dict(pid=40,uid=os.getuid(),start_ticks=100,executable='/usr/bin/qemu-system-x86_64')
        current=identity.copy();credentials=(40,os.getuid(),os.getuid())
        inode=SimpleNamespace(st_mode=stat.S_IFSOCK|0o600,st_uid=os.getuid(),st_dev=1,st_ino=2)
        helper.validate_peer(credentials,identity,current,inode,inode)
        for change in (dict(pid=41),dict(uid=os.getuid()+1),dict(start_ticks=101),dict(executable='/usr/bin/python3')):
            with self.assertRaises(RuntimeError):helper.validate_peer(credentials,identity,current|change,inode,inode)
        for changed in ((41,os.getuid(),os.getuid()),(40,os.getuid()+1,os.getuid())):
            with self.assertRaises(RuntimeError):helper.validate_peer(changed,identity,current,inode,inode)
        for stat_changes in (dict(st_ino=3),dict(st_mode=stat.S_IFLNK|0o777),dict(st_uid=os.getuid()+1)):
            with self.assertRaises(RuntimeError):helper.validate_peer(credentials,identity,current,SimpleNamespace(**(vars(inode)|stat_changes)),inode)
        # A real host Python process must not satisfy the Fedora QEMU proof.
        original_resolve=Path.resolve
        def resolve(path,*args,**kwargs):
            if path==Path('/usr/bin/qemu-system-x86_64'):
                return path  # The VM tools package is intentionally absent on this host.
            return original_resolve(path,*args,**kwargs)
        with patch.object(Path,'resolve',autospec=True,side_effect=resolve),self.assertRaises(RuntimeError):
            helper.qemu_identity(os.getpid())

    def test_real_unix_credentials_and_partial_constructor_failures_close(self):
        identity=dict(pid=os.getpid(),uid=os.getuid(),start_ticks=1,executable='fixture-only')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);root.chmod(0o700);path=root/'serial.sock'
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
                server.bind(str(path));server.listen(2)
                process=Mock(pid=os.getpid());process.poll.return_value=None
                with patch.object(helper,'qemu_identity',return_value=identity):
                    channel=helper.SerialChannel(path,process,root/'received.log')
                    self.assertEqual(channel.credentials,(os.getpid(),os.getuid(),os.getuid()));channel.close()
                accepted,_=server.accept();accepted.close()
                wrong=identity|dict(pid=os.getpid()+1)
                with patch.object(helper,'qemu_identity',return_value=wrong),self.assertRaises(RuntimeError):
                    helper.SerialChannel(path,process,root/'wrong-peer.log')
                accepted,_=server.accept();accepted.close()
                link=root/'linked.sock';link.symlink_to(path)
                with patch.object(helper,'qemu_identity',return_value=identity),self.assertRaises(RuntimeError):
                    helper.SerialChannel(link,process,root/'linked.log')
                process.poll.return_value=0
                with patch.object(helper,'qemu_identity',return_value=identity),self.assertRaises(RuntimeError):
                    helper.SerialChannel(root/'absent.sock',process,root/'absent.log')
            self.assertFalse((root/'wrong-peer.log').exists());self.assertFalse((root/'linked.log').exists())

    def test_one_attempt_only_missing_closed_peer_and_partial_write_fail_closed(self):
        actual=current_fixture();channel=bare_channel(actual['serial']);result={}
        channel.submit_once(actual['first'],result)
        self.assertEqual(channel.attempts,1);self.assertTrue(result['passphrase_submitted'])
        self.assertEqual(channel.sock.sendall.call_args.args,(helper.PASSPHRASE.encode()+b'\n',))
        self.assertNotIn(helper.PASSPHRASE,result.values());self.assertNotIn(helper.PASSPHRASE.encode(),channel.stream.getvalue())
        with self.assertRaises(RuntimeError):channel.submit_once(actual['first'],result)
        self.assertEqual(channel.sock.sendall.call_count,1)
        for channel in (bare_channel(),bare_channel(actual['serial'])):
            if channel.data:channel.closed=True
            with self.assertRaises(RuntimeError):channel.submit_once(actual['first'],{})
            channel.sock.sendall.assert_not_called();self.assertEqual(channel.attempts,0)
        channel=bare_channel(actual['serial']);channel.sock.sendall.side_effect=OSError(helper.PASSPHRASE)
        with self.assertRaisesRegex(RuntimeError,'single bounded') as error:channel.submit_once(actual['first'],{})
        self.assertNotIn(helper.PASSPHRASE,str(error.exception));self.assertEqual(channel.attempts,1)
        with self.assertRaises(RuntimeError):channel.submit_once(actual['first'],{})
        self.assertEqual(channel.sock.sendall.call_count,1)

    def test_echo_full_partial_ansi_and_fragmented_output_never_persists(self):
        secret=helper.PASSPHRASE.encode()
        for echoed in (secret,secret[:8],secret[:4]+b'\x1b[0m'+secret[4:]):
            channel=bare_channel(b'actual pre-input request');channel.attempts=1
            channel.after.extend(b'guest output '+echoed+b'\n')
            with self.assertRaisesRegex(RuntimeError,'echo'):channel.persist_safe()
            self.assertEqual(channel.stream.getvalue(),b'actual pre-input request')
            self.assertTrue(channel.echo_rejected)
        channel=bare_channel(b'prefix');channel.attempts=1
        channel.after.extend(b'valid guest-only transaction output');channel.data.extend(channel.after);channel.closed=True
        result=channel.persist_safe()
        self.assertEqual(channel.stream.getvalue(),bytes(channel.data))
        self.assertEqual(result['raw_serial_sha256'],hashlib.sha256(channel.stream.getvalue()).hexdigest())
        self.assertTrue(result['serial_eof_observed']);self.assertFalse(result['passphrase_echo_detected'])

    def test_incoming_echo_stops_before_any_post_input_screenshot(self):
        channel=bare_channel(b'actual pre-input request');channel.attempts=1
        channel.sock.recv.side_effect=[helper.PASSPHRASE.encode(),b'']
        with self.assertRaisesRegex(RuntimeError,'echo'):channel.pump()
        self.assertEqual(channel.stream.getvalue(),b'actual pre-input request')
        source=ast.parse((HERE/'offline-update-cycle-v5.py').read_text())
        observe=next(node for node in source.body if isinstance(node,ast.FunctionDef) and node.name=='observe')
        last_shot=max(node.lineno for node in ast.walk(observe) if isinstance(node,ast.Call)
            and isinstance(node.func,ast.Attribute) and node.func.attr=='shot')
        submit=next(node.lineno for node in ast.walk(observe) if isinstance(node,ast.Call)
            and isinstance(node.func,ast.Attribute) and node.func.attr=='submit_once')
        self.assertLessEqual(last_shot,submit)

    def test_new_transport_flags_and_identity_proof_are_mandatory(self):
        for change in (dict(serial_peer_verified=False),dict(unlock_attempts=0),dict(unlock_attempts=2),dict(unlock_attempts=True),
                       dict(raw_serial_complete=False),dict(serial_eof_observed=False),dict(passphrase_echo_detected=True),
                       dict(first_install={}),dict(unlock_prompt_evidence={}),dict(disk_owner={}),dict(disk_identity={}),
                       dict(disk_owner=dict(uid=True,gid=os.getgid()))):
            with self.assertRaises(RuntimeError):helper.validate_cycle(good_cycle()|change)

    def test_dark_vga_live_serial_route_observation_preserves_third_boot_requirement(self):
        actual=current_fixture();channel=bare_channel()
        state=dict(alive=True,booted=False,delivered=False)
        class StreamSocket:
            def recv(self,_):
                if not state['alive']:return b''
                if state['booted'] and not state['delivered']:
                    state['delivered']=True;return actual['serial']
                raise socket.timeout()
            def settimeout(self,_):pass
            def sendall(self,value):
                self.written=value;state['alive']=False
        channel.sock=StreamSocket();channel.process.poll.side_effect=lambda:None if state['alive'] else 0
        vm=Mock();vm.alive.side_effect=lambda:state['alive'];vm.shot.return_value='dark-console-frame'
        vm.keys.side_effect=lambda *keys:state.update(booted=True) if keys==('ctrl-x',) else None
        vm.proc=channel.process;vm.events=good_cycle()['events']
        vmtest=SimpleNamespace(looks_like_boot_menu=lambda _:True,classify=Mock(side_effect=AssertionError('VGA classification must not unlock serial')),
            log=lambda _:None)
        counter=iter(range(1000));result=good_cycle()|dict(first_install=actual['first'])
        helper.observe(vm,vmtest,result,300,channel,actual['first'],clock=lambda:next(counter),pause=lambda _:None)
        self.assertEqual(result['status'],'guest_cycle_exit_observed_third_boot_required')
        self.assertIn('UNRUN',result['update_qualification']);vmtest.classify.assert_not_called()
        self.assertEqual(vm.type_text.call_args.args[0],' '+helper.CONSOLE_APPEND)
        self.assertEqual(vm.type_text.call_count,1);self.assertTrue(result['serial_eof_observed'])

if __name__=='__main__':unittest.main(verbosity=2)
