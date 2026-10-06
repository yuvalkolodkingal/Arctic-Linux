"""Bounded host controls only; all VM/process commands are intercepted."""
import ast
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

HERE=Path(__file__).resolve().parent
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
helper=load('cycle_helper_v4',HERE/'offline-update-cycle-v4.py')
driver=load('cycle_driver_v4',HERE/'offline-only-recovery-v4.py')
ACTUAL=Path(os.environ.get('ARCTIC_OFFLINE_V4_CONTROL_EVIDENCE',
    str(HERE.parent/'same-iso-recovery/results-37520174911/arctic-offline/first-boot')))
def actual_fixture():
    for name,sha in {'serial-boot.log':'e02d56464396374a5955afb640f820fab2a4e62aadb58d770912bf95c78ee56e',
            'serial-install.log':'7006a8083ba26ffefbfc18f737dc182f5de0fff16a53cf4f5ccb2cb863558c34'}.items():
        driver.base.pinned_file(ACTUAL/name,sha)
    return ACTUAL

def good_cycle():
    return dict(unlock_prompt_seen=True,passphrase_submitted=True,guest_exited=True,
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
    def test_cycle_argv_is_kvm_restricted_network_no_cd_or_security_bypass(self):
        argv=helper.qemu_argv(Path('/out/target.qcow2'),Path('/out/OVMF_VARS.fd'),
            Path('/out/offline-update-cycle'),Path('/firmware/OVMF_CODE.fd'),'/tmp/qmp.sock')
        self.assertEqual(argv[argv.index('-accel')+1],'kvm')
        self.assertEqual(argv[argv.index('-netdev')+1],'user,id=net0,restrict=on')
        self.assertIn('-no-reboot',argv)
        self.assertFalse(any('data.iso' in item or 'cdrom' in item or 'tcg' in item for item in argv))
        self.assertEqual(helper.CONSOLE_APPEND,'console=tty0 console=ttyS0,115200 systemd.journald.forward_to_console=1')
        with self.assertRaises(RuntimeError):helper.qemu_argv(Path('/out/a,b'),Path('/vars'),Path('/out/result'),Path('/firmware'),'/tmp/qmp')
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
            helper.observe(vm,vmtest,{},300,clock=lambda:next(clock_values),pause=lambda _:None)
        vm.type_text.assert_not_called()
        clock_values=iter(range(0,10000,100));vm.reset_mock();vm.alive.return_value=True;vm.shot.return_value='screen'
        vmtest.looks_like_boot_menu=lambda _:True
        with self.assertRaisesRegex(RuntimeError,'LUKS'):
            helper.observe(vm,vmtest,{},300,clock=lambda:next(clock_values),pause=lambda _:None)
        self.assertEqual(vm.type_text.call_args_list[0].args[0],' '+helper.CONSOLE_APPEND)
        self.assertEqual(vm.type_text.call_count,1)
    def test_qmp_exception_is_not_expected_guest_cycle_success(self):
        vm=Mock();vm.alive.return_value=True;vm.shot.return_value='menu';vm.keys.side_effect=RuntimeError('QMP broken')
        vmtest=SimpleNamespace(looks_like_boot_menu=lambda _:True)
        with self.assertRaisesRegex(RuntimeError,'QMP broken'):helper.observe(vm,vmtest,{},300)

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
        args=SimpleNamespace(source=Path('/candidate'),bundle=Path('/qualification/tools/same-iso-offline-v4'))
        argv=driver.cycle_command(args,Path('/fresh/run/vm'),'sha256:'+'a'*64,'arctic-paired-offline-v4-test')
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
                    '/tmp/arctic-offline-cycle-v4-123.sock'))
            result=folder/'cycle-result.json';events=folder/'qmp-events.jsonl';serial=folder/'serial-offline-cycle.log'
            def write():result.write_text(json.dumps(value));events.write_text('\n'.join(json.dumps(row) for row in value['events'])+'\n')
            serial.write_text('synthetic observation only');write()
            self.assertEqual(driver.cycle_success(vm)['network'],'restricted_offline')
            for change in ('network','argv','events','serial'):
                original=copy.deepcopy(value)
                if change=='network':value['network']='online'
                elif change=='argv':value['actual_qemu_argv']=list(value['actual_qemu_argv']);value['actual_qemu_argv'][value['actual_qemu_argv'].index('user,id=net0,restrict=on')]='user,id=net0'
                write()
                if change=='events':events.write_text('')
                if change=='serial':serial.unlink()
                with self.subTest(change=change),self.assertRaises(RuntimeError):driver.cycle_success(vm)
                value=original;serial.write_text('synthetic observation only')
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
                    patch.object(driver.base,'preserve_phase',return_value={'vm-toolchain.txt':{'sha256':'same'},'serial-boot.log':{}}),
                    patch.object(driver,'preserve_cycle',return_value={}),patch.object(driver.signal,'signal'),
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
        text=(HERE/'registered-iso-offline-cycle-v4.yml').read_text()
        self.assertIn('(!inputs.same_iso_recovery && !inputs.offline_cycle_recovery)',text)
        self.assertEqual(text.count("inputs.same_iso_recovery && !inputs.offline_cycle_recovery }}"),2)
        v4=text[text.index('  same-iso-offline-cycle-v4:'):]
        self.assertIn("if: ${{ github.event_name == 'workflow_dispatch' && inputs.offline_cycle_recovery }}",v4)
        self.assertNotIn('&& !inputs.same_iso_recovery }}',v4)
        self.assertNotIn('contents: write',text[text.index('  same-iso-offline-cycle-v4:'):])
    def test_original_primitives_and_frozen_checker_bytes_unchanged(self):
        pins={'vm-only-recovery-v2.py':driver.BASE_SHA256,'guest-check-offline-v1.py':driver.OFFLINE_CHECKER_SHA256,
            'README-v1.md':driver.base.BUNDLE_PINS['README-v1.md'],
            'review-ready-v1.json':driver.base.BUNDLE_PINS['review-ready-v1.json']}
        for name,sha in pins.items():self.assertEqual(driver.base.digest(HERE/name),sha,name)
        tree=ast.parse((HERE/'offline-only-recovery-v4.py').read_text())
        assignments=[node for node in ast.walk(tree) if isinstance(node,(ast.Assign,ast.AnnAssign))]
        self.assertFalse(any(isinstance(target,ast.Attribute) and isinstance(target.value,ast.Name) and target.value.id=='base'
            for node in assignments for target in (node.targets if isinstance(node,ast.Assign) else [node.target])))

if __name__=='__main__':unittest.main(verbosity=2)
