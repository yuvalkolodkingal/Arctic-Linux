#!/usr/bin/env python3
"""Host-only controls. These use tiny synthetic files and never start a VM."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock
import yaml

HERE = Path(__file__).resolve().parent

def module(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE/file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

R = module('vm_only_v2_tested', 'vm-only-recovery-v2.py')
B = module('boot_v2_tested', 'boot-evidence-v2.py')


def ci():
    return dict(GITHUB_ACTIONS='true', GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_REPOSITORY=R.REPOSITORY,
                GITHUB_API_URL='https://api.github.com', RECOVERY_MODE='true', RELEASE_REQUESTED='false',
                GITHUB_SHA='1'*40, GITHUB_RUN_ID='37507582947', GITHUB_RUN_ATTEMPT='1')


def original():
    return (dict(id=R.ORIGINAL_RUN, run_attempt=1, head_sha=R.SOURCE, name='ISO', status='completed', conclusion='failure'),
            [dict(id=7, run_id=R.ORIGINAL_RUN, head_sha=R.SOURCE,
                  steps=[dict(name='Nix enforcing VM acceptance', number=8, status='completed', conclusion='failure')])],
            dict(id=R.ARTIFACT_ID, name=R.ARTIFACT_NAME, expired=False, size_in_bytes=R.ARCHIVE_BYTES,
                 digest=R.ARCHIVE_DIGEST, workflow_run=dict(id=R.ORIGINAL_RUN, head_sha=R.SOURCE)))


def collected(method='uefi-sb-try'):
    sections = dict(CMDLINE=['BOOT_IMAGE=/vmlinuz rd.live.image ' + ('nomodeset' if method == 'uefi-safe' else '')],
                    SECUREBOOT=['SecureBoot enabled'],
                    **{'FAILED-UNITS':['  UNIT LOAD ACTIVE SUB DESCRIPTION', '0 loaded units listed.', 'ARCTIC-FAILED-UNITS-EXIT=0']},
                    WARNINGS=['A kernel warning retained for review'], SELINUX=['Enforcing'],
                    AVC=['ARCTIC-AVC-JOURNAL-EXIT=0', 'ARCTIC-AVC-FILTER-EXIT=1'])
    lines = ['unrelated startup text', 'ARCTIC-COLLECT-BEGIN']
    for name, content in sections.items():
        lines += ['ARCTIC-'+name+'-BEGIN'] + content + ['ARCTIC-'+name+'-END']
    return '\r\n'.join(lines + ['ARCTIC-COLLECT-END', 'outside Enforcing'])


class MetadataControls(unittest.TestCase):
    def test_fixed_identity_success(self):
        self.assertEqual(R.validate_original(*original())['nix_step_conclusion'], 'failure')
        R.validate_ci(ci())
        run,jobs,artifact=original();run.update(status='in_progress',conclusion=None)
        self.assertEqual(R.validate_original(run,jobs,artifact)['status'],'in_progress')

    def test_ci_negative_controls(self):
        changes = [('CONTAINER_ENGINE','podman'),('GITHUB_ACTIONS','false'),('GITHUB_EVENT_NAME','push'),('GITHUB_REPOSITORY','other/repo'),
                   ('GITHUB_API_URL','https://other.test'),('RECOVERY_MODE','false'),('RELEASE_REQUESTED','true'),
                   ('GITHUB_SHA',R.SOURCE),('GITHUB_RUN_ID',str(R.ORIGINAL_RUN)),('GITHUB_RUN_ATTEMPT','0')]
        for key, value in changes:
            with self.subTest(key=key):
                env=ci();env[key]=value
                with self.assertRaises(RuntimeError):R.validate_ci(env)

    def test_original_and_artifact_negative_controls(self):
        changes=[(0,'status','queued'),(0,'conclusion','success'),(0,'head_sha','2'*40),
                 (0,'run_attempt',2),(0,'run_attempt',True),(0,'id',999),(2,'id',999),(2,'name','arbitrary'),
                 (2,'expired',True),(2,'size_in_bytes',R.ARCHIVE_BYTES+1),(2,'digest','wrong')]
        for index, key, value in changes:
            with self.subTest(key=key):
                values=copy.deepcopy(original()); values[index][key]=value
                with self.assertRaises(RuntimeError): R.validate_original(*values)
        run,jobs,artifact=original()
        for steps in ([], jobs[0]['steps']*2, [dict(jobs[0]['steps'][0],conclusion='success')]):
            with self.subTest(steps=steps),self.assertRaises(RuntimeError):
                R.validate_original(run,[dict(jobs[0],steps=steps)],artifact)

    def test_actual_bytes_not_metadata_label(self):
        with tempfile.TemporaryDirectory() as folder:
            inputs=Path(folder);(inputs/'iso').mkdir();iso=inputs/'iso'/R.ISO;iso.write_bytes(b'tiny-control-ISO')
            build=inputs/'BUILD-INFO';build.write_text('git_commit='+R.SOURCE+'\ngit_dirty=no\nrelease_suffix=.preview.37507582946.1.gitfe4742c\narctic_repos=enabled\n')
            meta=inputs/'iso'/(R.ISO[:-4]+'.build-info')
            meta.write_text('git_commit='+R.SOURCE+'\nbuild_tool_commit='+R.SOURCE+'\niso_bytes='+str(iso.stat().st_size)+'\narctic_repos=enabled\n')
            pins={str(p.relative_to(inputs)):R.digest(p) for p in (build,meta)}
            with mock.patch.multiple(R,ISO_BYTES=iso.stat().st_size,ISO_SHA256=R.digest(iso),METADATA_PINS=pins):
                self.assertTrue(R.verify_iso(inputs)['byte_verified'])
                iso.write_bytes(b'TINY-control-ISO') # same length, different actual bytes
                with self.assertRaisesRegex(RuntimeError,'checksum'):R.verify_iso(inputs)
                iso.write_bytes(b'tiny-control-ISO-extra')
                with self.assertRaisesRegex(RuntimeError,'byte count'):R.verify_iso(inputs)
                iso.write_bytes(b'tiny-control-ISO');(inputs/'extra').write_text('not allowed')
                with self.assertRaisesRegex(RuntimeError,'Unexpected'):R.verify_iso(inputs)
                (inputs/'extra').unlink();(inputs/'linked').symlink_to(build)
                with self.assertRaisesRegex(RuntimeError,'symlink'):R.verify_iso(inputs)

    def test_docker_contract_fail_closed(self):
        with mock.patch.object(R.shutil, 'which', return_value=None):
            with self.assertRaises(RuntimeError):R.require_docker()
        with mock.patch.object(R.shutil, 'which', return_value='/usr/bin/docker'),mock.patch.object(R.subprocess,'check_output',return_value=''):
            with self.assertRaises(RuntimeError):R.require_docker()
        with mock.patch.object(R.shutil, 'which', return_value='/usr/bin/docker'),mock.patch.object(R.subprocess,'check_output',return_value='28.0.0\n'):
            self.assertEqual(R.require_docker(),'28.0.0')
        for engine in ('', 'docker'):
            env=ci();env['CONTAINER_ENGINE']=engine;R.validate_ci(env)

    def test_pinned_checker_changed(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'checker';path.write_text('original')
            wanted=R.digest(path);R.pinned_file(path,wanted);path.write_text('modified')
            with self.assertRaises(RuntimeError):R.pinned_file(path,wanted)


class BootParserControls(unittest.TestCase):
    def test_all_three_positive_modes_still_need_visual_review(self):
        for method in B.MODES:
            result=B.parse(collected(method),method,['99-final.png'])
            self.assertEqual(result['status'],'semantic_collection_passed_pending_visual_review')
            self.assertIn('REQUIRED',result['visual_review'])
            self.assertTrue(result['sections']['WARNINGS'])

    def test_scoped_security_negative_controls(self):
        cases=[('Enforcing','Permissive'),('SecureBoot enabled','SecureBoot disabled'),
               ('rd.live.image','rd.live.other'),('ARCTIC-COLLECT-BEGIN','missingbegin'),
               ('ARCTIC-COLLECT-END','missingend'),('ARCTIC-SELINUX-BEGIN','missingsection'),
               ('ARCTIC-AVC-JOURNAL-EXIT=0','ARCTIC-AVC-JOURNAL-EXIT=1'),
               ('ARCTIC-AVC-FILTER-EXIT=1','ARCTIC-AVC-FILTER-EXIT=2'),
               ('ARCTIC-FAILED-UNITS-EXIT=0','ARCTIC-FAILED-UNITS-EXIT=1'),
               ('0 loaded units listed.','incomplete report')]
        for old,new in cases:
            with self.subTest(old=old),self.assertRaises(RuntimeError):
                B.parse('Enforcing\nSecureBoot enabled\nrd.live.image\n'+collected().replace(old,new), 'uefi-sb-try',['99-final.png'])

    def test_missing_safe_flag(self):
        with self.assertRaises(RuntimeError):B.parse(collected('uefi-safe').replace('nomodeset',''), 'uefi-safe',['shot.png'])

    def test_duplicate_and_nested_sections(self):
        for serial in (collected()+'\nARCTIC-COLLECT-END',collected().replace('Enforcing','ARCTIC-AVC-BEGIN\nEnforcing')):
            with self.assertRaises(RuntimeError):B.parse(serial,'uefi-sb-try',['shot.png'])

    def test_failed_units_retained_and_fail_qualification(self):
        result=B.parse(collected().replace('0 loaded units listed.','1 loaded units listed.'),'uefi-sb-try',['shot.png'])
        self.assertEqual(result['status'],'semantic_qualification_failed_review_required')
        self.assertEqual(result['failed_units_count'],1)

    def test_new_denial_captured_and_fails(self):
        serial=collected().replace('ARCTIC-AVC-FILTER-EXIT=1','avc: denied { read } for pid=42\nARCTIC-AVC-FILTER-EXIT=0')
        result=B.parse(serial,'uefi-sb-try',['shot.png'])
        self.assertEqual(result['status'],'semantic_qualification_failed_review_required')
        self.assertEqual(len(result['avc_denials']),1)

    def test_filter_status_consistency(self):
        with self.assertRaises(RuntimeError):B.parse(collected().replace('ARCTIC-AVC-FILTER-EXIT=1','ARCTIC-AVC-FILTER-EXIT=0'),'uefi-sb-try',['shot.png'])
        with self.assertRaises(RuntimeError):B.parse(collected(),'uefi-sb-try',[])


class ActualCollectorShellControls(unittest.TestCase):
    def test_real_shell_pipeline_handles_no_denials_and_low_priority_denial(self):
        # Execute only the collector's shell logic against isolated fake commands;
        # no sudo, VM, host journal, host systemctl or serial-device writes.
        command=shlex.split((HERE/'collector-command-v2.txt').read_text())
        self.assertEqual(command[:3],['sudo','sh','-c'])
        script=command[3]
        self.assertTrue(script.endswith(' >/dev/ttyS0 2>&1'))
        script=script.removesuffix(' >/dev/ttyS0 2>&1')
        with tempfile.TemporaryDirectory() as folder:
            binpath=Path(folder)
            tools={
                'cat':'if [ "$1" = /proc/cmdline ]; then echo "rd.live.image nomodeset"; else /bin/cat "$@"; fi',
                'mokutil':'echo "SecureBoot enabled"',
                'systemctl':'echo "0 loaded units listed."',
                'getenforce':'echo Enforcing',
                'flatpak':'exit 0',
                'journalctl':'case " $* " in *" -p warning "*) echo "benign warning";; *) [ "$DENY" = 1 ] && echo "avc: denied { read } for pid=42"; echo "normal info log";; esac; exit 0',
            }
            for name, content in tools.items():
                path=binpath/name;path.write_text('#!/bin/sh\n'+content+'\n');path.chmod(0o755)
            for deny in ('0','1'):
                env=dict(os.environ,PATH=str(binpath)+':/usr/bin:/bin',DENY=deny)
                completed=subprocess.run(['/bin/sh','-c',script],env=env,text=True,capture_output=True,check=True)
                result=B.parse(completed.stdout,'uefi-sb-try',['shot.png'])
                self.assertEqual(result['status'],'semantic_qualification_failed_review_required' if deny=='1' else 'semantic_collection_passed_pending_visual_review')
                self.assertEqual(len(result['avc_denials']),int(deny))


class LifecycleControls(unittest.TestCase):
    def test_first_boot_preserved_and_second_failure_retained(self):
        self.synthetic_run(fail='after-update-reboot',expected=2)

    def test_first_failure_prevents_second_boot(self):
        self.synthetic_run(fail='first-boot',expected=1)

    def test_first_and_second_success(self):
        self.synthetic_run(fail=None,expected=2)

    def synthetic_run(self, fail, expected):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);evidence=root/'evidence';evidence.mkdir();bundle=root/'bundle';bundle.mkdir()
            name,sha=R.CHECKERS['dnf'];(bundle/name).write_text('controlled fixture')
            args=SimpleNamespace(source=root/'source',bundle=bundle,inputs=root/'inputs',evidence=evidence,method='dnf')
            calls=[]
            def execute(argv, log, seconds, cwd, env, container):
                self.assertEqual(env.get('CONTAINER_ENGINE'), 'docker')
                log.write_text('synthetic; no VM')
                if 'prepare-vm-tools.sh' in ' '.join(argv):
                    (evidence/'vm-prepared-image-id.txt').write_text('sha256:'+'1'*64);return
                phase='after-update-reboot' if '--stage' in argv else 'first-boot'
                calls.append(phase);vm=root/'vm';vm.mkdir(exist_ok=True)
                (vm/'serial-boot.log').write_text('phase='+phase+'\nARCTIC-INSTALLED-SMOKE-EXIT='+('3' if fail==phase else '0')+'\n')
                (vm/'vm-toolchain.txt').write_text('same toolchain')
                (vm/'target.qcow2').write_text('never export')
                (vm/'99.png').write_bytes(b'fixture')
            with mock.patch.object(R,'verify'),mock.patch.object(R,'require_docker',return_value='28.0.0'),mock.patch.object(R,'pinned_file'),mock.patch.object(R,'execute',side_effect=execute),mock.patch.object(Path,'is_char_device',return_value=True),mock.patch.object(R.subprocess,'run'),mock.patch.object(R.signal,'signal'),mock.patch.dict(os.environ,ci()):
                if fail:
                    with self.assertRaisesRegex(RuntimeError,'probe exit'):R.run(args)
                else:R.run(args)
            self.assertEqual(len(calls),expected)
            first=(evidence/'first-boot'/'serial-boot.log').read_text()
            self.assertIn('phase=first-boot',first)
            self.assertFalse((evidence/'first-boot'/'target.qcow2').exists())
            if expected==2:
                self.assertIn('phase=after-update-reboot',(evidence/'after-update-reboot'/'serial-boot.log').read_text())

    def test_no_vm_after_bad_iso(self):
        args=SimpleNamespace(method='dnf')
        with mock.patch.object(R,'verify',side_effect=RuntimeError('ISO mismatch')),mock.patch.object(R,'execute') as execute:
            with self.assertRaises(RuntimeError):R.run(args)
            execute.assert_not_called()

    def test_duplicate_or_failure_exit_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            vm=Path(folder)
            for content in ('ARCTIC-INSTALLED-SMOKE-EXIT=3\n','ARCTIC-INSTALLED-SMOKE-EXIT=0\n'*2,'missing marker'):
                (vm/'serial-boot.log').write_text(content)
                with self.assertRaises(RuntimeError):R.probe_success(vm)


class WorkflowControls(unittest.TestCase):
    def test_registered_workflow_build_skip_and_least_permissions(self):
        value=yaml.load((HERE/'registered-iso-recovery-v2.yml').read_text(),Loader=yaml.BaseLoader)
        self.assertEqual(value['permissions'],{'contents':'read','actions':'read'})
        self.assertIn('!inputs.same_iso_recovery',value['jobs']['iso']['if'])
        self.assertEqual(value['jobs']['iso']['permissions'],{'contents':'write'})
        self.assertEqual(value['on']['workflow_dispatch']['inputs']['same_iso_recovery']['default'],'false')
        methods=[]
        for name in ('same-iso-installs','same-iso-boot-evidence'):
            job=value['jobs'][name];methods+=job['strategy']['matrix']['method']
            self.assertEqual(job['permissions'],{'contents':'read','actions':'read'})
            self.assertEqual(job['strategy']['fail-fast'],'false')
            steps=job['steps'];download=[s for s in steps if s.get('uses','').startswith('actions/download-artifact@')]
            self.assertEqual(len(download),1)
            self.assertEqual(download[0]['with']['artifact-ids'],str(R.ARTIFACT_ID))
            self.assertEqual(download[0]['with']['run-id'],str(R.ORIGINAL_RUN))
            upload=[s for s in steps if s.get('uses','').startswith('actions/upload-artifact@')][0]
            self.assertEqual(upload['with']['path'],'${{ env.RECOVERY_ROOT }}/evidence/')
            self.assertFalse(any('build-iso' in s.get('run','') or 'release create' in s.get('run','') for s in steps))
            self.assertTrue(all(len(s['uses'].split('@')[1])==40 for s in steps if 'uses' in s))
        self.assertEqual(set(methods),set(R.CHECKERS)|set(B.MODES))


if __name__=='__main__':unittest.main(verbosity=2)
