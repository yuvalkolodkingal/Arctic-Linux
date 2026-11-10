"""Tests for arctic-update-finish: how the computer leaves the offline-update boot.

The script runs under a scratch root (ARCTIC_UPDATE_FINISH_ROOT, ARCTIC_UPDATE_FINISH_RUN) with
a scripted systemctl in PATH. Nothing on this machine changes.

Run: python3 -m unittest discover -s packaging/updates
"""
import os
import stat
import subprocess
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / 'arctic-update-finish'
DROPIN = HERE / '50-arctic-finish.conf'

STATE = textwrap.dedent('''\
    [offline-transaction-state]
    poweroff_after = {poweroff}
    verb = "{verb}"
    system_releasever = "{system}"
    target_releasever = "{target}"
    status = "ready"
    ''')


class FinishTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'root'
        self.run_dir = Path(self.tmp.name) / 'run'
        self.bin = Path(self.tmp.name) / 'bin'
        self.calls = Path(self.tmp.name) / 'calls'
        for d in ('usr/lib/modules/6.17.8-300.fc44.x86_64/kernel', 'usr/lib/firmware/intel',
                  'usr/src/akmods', 'usr/lib/sysimage/libdnf5/offline', 'usr/bin'):
            (self.root / d).mkdir(parents=True)
        (self.root / 'usr/lib/modules/6.17.8-300.fc44.x86_64/kernel/a.ko.xz').write_text('a')
        (self.root / 'usr/lib/firmware/intel/fw.bin').write_text('f')
        self.bin.mkdir()
        self.fake('systemctl', 'echo "$*" >> "$CALLS"\ncase " $* " in *" $REFUSE "*) exit 1 ;; esac\nexit 0\n')
        self.state()

    def tearDown(self):
        self.tmp.cleanup()

    def fake(self, name, body):
        path = self.bin / name
        path.write_text('#!/usr/bin/bash\n' + body)
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def state(self, poweroff='false', verb='upgrade', system='44', target='44'):
        (self.root / 'usr/lib/sysimage/libdnf5/offline/offline-transaction-state.toml').write_text(
            STATE.format(poweroff=poweroff, verb=verb, system=system, target=target))

    def script(self, verb, refuse='-'):
        env = dict(os.environ, PATH=f'{self.bin}:/usr/bin:/bin', CALLS=str(self.calls), REFUSE=refuse,
                   ARCTIC_UPDATE_FINISH_ROOT=str(self.root), ARCTIC_UPDATE_FINISH_RUN=str(self.run_dir),
                   ARCTIC_UPDATE_FINISH_INHIBIT_WAIT='0')
        return subprocess.run([str(SCRIPT), verb], env=env, capture_output=True, text=True, timeout=30)

    def prepare(self):
        self.assertEqual(self.script('prepare').returncode, 0)
        time.sleep(0.05)   # what follows is later than the marker on any file system

    def decide(self):
        p = self.script('decide')
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout.strip()

    def systemctl(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_programs_only_soft_reboots(self):
        self.prepare()
        (self.root / 'usr/bin/jq').write_text('new')
        self.assertEqual(self.decide(), 'soft-reboot')
        p = self.script('finish')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.systemctl(), ['--no-block soft-reboot'])
        self.assertFalse(self.run_dir.exists())

    def test_new_kernel_restarts(self):
        self.prepare()
        new = self.root / 'usr/lib/modules/6.17.9-300.fc44.x86_64'
        new.mkdir()
        (new / 'vmlinuz').write_text('k')
        self.assertEqual(self.decide(), 'reboot')
        self.assertEqual(self.script('finish').returncode, 0)
        self.assertEqual(self.systemctl(), ['--no-block reboot'])

    def test_replaced_module_with_an_old_build_time_restarts(self):
        self.prepare()
        module = self.root / 'usr/lib/modules/6.17.8-300.fc44.x86_64/kernel/a.ko.xz'
        replacement = module.with_name('a.ko.xz;tmp')
        replacement.write_text('b')
        os.utime(replacement, (1_000_000_000, 1_000_000_000))   # rpm sets the build time
        os.replace(replacement, module)
        self.assertEqual(self.decide(), 'reboot')

    def test_removed_module_restarts(self):
        self.prepare()
        (self.root / 'usr/lib/modules/6.17.8-300.fc44.x86_64/kernel/a.ko.xz').unlink()
        self.assertEqual(self.decide(), 'reboot')

    def test_firmware_and_akmod_sources_restart(self):
        for path in ('usr/lib/firmware/intel/new.bin', 'usr/src/akmods/nvidia-kmod.latest'):
            with self.subTest(path=path):
                self.prepare()
                (self.root / path).write_text('x')
                self.assertEqual(self.decide(), 'reboot')
                (self.root / path).unlink()

    def test_release_upgrade_restarts(self):
        for kwargs in (dict(verb='system-upgrade download', target='45'), dict(target='45')):
            with self.subTest(**kwargs):
                self.state(**kwargs)
                self.prepare()
                self.assertEqual(self.decide(), 'reboot')

    def test_poweroff_request_is_kept(self):
        self.state(poweroff='true')
        self.prepare()
        self.assertEqual(self.decide(), 'poweroff')
        self.assertEqual(self.script('finish').returncode, 0)
        self.assertEqual(self.systemctl(), ['--no-block poweroff'])

    def test_without_prepare_restarts(self):
        self.assertEqual(self.decide(), 'reboot')
        self.assertEqual(self.script('finish').returncode, 0)
        self.assertEqual(self.systemctl(), ['--no-block reboot'])

    def test_refused_soft_reboot_falls_back_to_a_restart(self):
        self.prepare()
        p = self.script('finish', refuse='soft-reboot')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.systemctl(), ['--no-block soft-reboot', '--no-block reboot'])

    def test_a_refused_restart_fails_the_unit(self):
        # The unit's OnFailure= (dnf5-offline-transaction-cleanup.service) restarts then.
        p = self.script('finish', refuse='reboot')
        self.assertEqual(p.returncode, 1)

    def test_prepare_never_fails_without_a_state_file(self):
        (self.root / 'usr/lib/sysimage/libdnf5/offline/offline-transaction-state.toml').unlink()
        self.prepare()
        self.assertEqual(self.decide(), 'soft-reboot')

    def test_usage(self):
        self.assertEqual(self.script('nonsense').returncode, 2)

    def test_dropin(self):
        text = DROPIN.read_text()
        lines = [l for l in text.splitlines() if l and not l.startswith('#')]
        self.assertEqual(lines, [
            '[Service]',
            'Environment=DNF_SYSTEM_UPGRADE_NO_REBOOT=1',
            # A failing prepare must never keep the updates from being installed.
            'ExecStartPre=-/usr/libexec/arctic/arctic-update-finish prepare',
            'ExecStartPost=/usr/libexec/arctic/arctic-update-finish finish',
        ])


if __name__ == '__main__':
    unittest.main()
