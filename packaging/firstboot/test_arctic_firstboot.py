"""Tests for arctic-firstboot against pending.json as the installer writes it.

The entries are built from the real catalog (modules/…/module.toml) and encoded the way the
engine's json.Marshal does it: the omitempty fields of catalog.Install are read from
internal/catalog/catalog.go, so a module whose flatpak ref is empty has no "ref" key at all.
Commands go to a fake runner; nothing is installed.

Run: python3 -m unittest discover -s packaging/firstboot
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import re
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
loader = importlib.machinery.SourceFileLoader('arctic_firstboot', str(Path(__file__).parent / 'arctic-firstboot'))
spec = importlib.util.spec_from_loader('arctic_firstboot', loader)
firstboot = importlib.util.module_from_spec(spec)
loader.exec_module(firstboot)


def install_json_tags():
    """{toml key: (json key, omitempty)} for catalog.Install, from its struct tags."""
    src = (ROOT / 'internal/catalog/catalog.go').read_text()
    body = re.search(r'type Install struct \{(.*?)\n\}', src, re.S).group(1)
    tags = {}
    for toml_key, json_tag in re.findall(r'toml:"([^"]+)" json:"([^"]+)"', body):
        name, _, opts = json_tag.partition(',')
        if name != '-':
            tags[toml_key] = (name, 'omitempty' in opts.split(','))
    return tags


TAGS = install_json_tags()
# Go zero values of the fields a module.toml may leave out.
ZERO = {'verified': False, 'download_mb': 0}


def engine_entry(path):
    """A pending.json module entry for modules/<path>/module.toml, encoded as the engine does."""
    data = tomllib.loads((ROOT / 'modules' / path / 'module.toml').read_text())
    install = []
    for method in data['install']:
        out = {}
        for key, (name, omitempty) in TAGS.items():
            value = method.get(key, ZERO.get(key))
            if omitempty and not value:   # "", [] or absent: json.Marshal leaves it out
                continue
            out[name] = value
        install.append(out)
    entry = {'id': data['id'], 'name': data['name'], 'install': install}
    # Drivers: json:"akmod,omitempty" and json:"kernel_args,omitempty" (installer finalizePhase;
    # the LUKS-only display arguments are left out here: an iGPU drives the screen).
    if 'akmod' in data:
        entry['akmod'] = {'name': data['akmod']['name'], 'module': data['akmod']['module']}
    args = data.get('boot', {}).get('kernel_args')
    if args:
        entry['kernel_args'] = args
    return entry


class FakeRunner:
    """Records commands. `fail` is a set of command prefixes that fail; `installed` the
    packages `rpm -q` finds."""

    def __init__(self, fail=(), installed=()):
        self.commands = []
        self.fail = [tuple(f) for f in fail]
        self.installed = set(installed)

    def __call__(self, cmd, quiet=False):
        if cmd[:3] == ['rpm', '-q', '--quiet']:
            return cmd[3] in self.installed
        self.commands.append(cmd)
        return not any(tuple(cmd[:len(f)]) == f for f in self.fail)


class EngineShapeTests(unittest.TestCase):
    def test_encoding_drops_empty_fields(self):
        flathub = engine_entry('extras/flathub')
        self.assertNotIn('ref', flathub['install'][0])       # json:"ref,omitempty", ref = ""
        self.assertNotIn('packages', flathub['install'][0])
        self.assertIn('verified', flathub['install'][0])     # not omitempty


class MethodTests(unittest.TestCase):
    def fb(self, runner, nixpkgs=''):
        return firstboot.FirstBoot(run=runner, release='44', nixpkgs=nixpkgs)

    def test_flathub_without_ref_only_adds_the_remote(self):
        run = FakeRunner()
        self.assertTrue(self.fb(run).install(engine_entry('extras/flathub')))
        self.assertEqual(run.commands, [['flatpak', 'remote-add', '--system', '--if-not-exists', 'flathub',
                                         'https://dl.flathub.org/repo/flathub.flatpakrepo']])

    def test_flatpak_app_adds_its_remote_once_then_installs(self):
        run = FakeRunner()
        fb = self.fb(run)
        zed = engine_entry('editor/zed')
        ref = zed['install'][0]['ref']
        self.assertTrue(fb.install(zed))
        self.assertTrue(fb.install(engine_entry('extras/flathub')))
        self.assertEqual([c[:2] for c in run.commands], [['flatpak', 'remote-add'], ['flatpak', 'install']])
        self.assertEqual(run.commands[1], ['flatpak', 'install', '--system', '-y', '--noninteractive', 'flathub', ref])

    def test_unknown_flatpak_remote_fails(self):
        run = FakeRunner()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(self.fb(run).try_method({'method': 'flatpak', 'remote': 'elsewhere', 'ref': 'x.y'}))
        self.assertEqual(run.commands, [])

    def test_codecs_enable_rpmfusion_and_swap_before_installing(self):
        run = FakeRunner(installed={'ffmpeg-free'})
        codecs = engine_entry('_system/codecs')
        self.assertTrue(self.fb(run).install(codecs))
        keys = '/usr/share/distribution-gpg-keys/rpmfusion/RPM-GPG-KEY-rpmfusion-{}-fedora-44'
        url = 'https://mirrors.rpmfusion.org/{0}/fedora/rpmfusion-{0}-release-44.noarch.rpm'
        self.assertEqual(run.commands, [
            ['rpm', '--import', keys.format('free')],
            ['dnf', 'install', '-y', url.format('free')],
            ['rpm', '--import', keys.format('nonfree')],
            ['dnf', 'install', '-y', url.format('nonfree')],
            ['dnf', 'swap', '-y', '--allowerasing', 'ffmpeg-free', 'ffmpeg'],
            ['dnf', 'install', '-y', *codecs['install'][0]['packages']],
        ])

    def test_repo_setup_already_done_is_skipped(self):
        run = FakeRunner(installed={'rpmfusion-free-release', 'rpmfusion-nonfree-release', 'ffmpeg'})
        codecs = engine_entry('_system/codecs')
        self.assertTrue(self.fb(run).install(codecs))
        self.assertEqual(run.commands, [['dnf', 'install', '-y', *codecs['install'][0]['packages']]])

    def test_failed_repo_setup_does_not_install(self):
        run = FakeRunner(fail=[['dnf', 'install', '-y', 'https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-44.noarch.rpm']])
        self.assertFalse(self.fb(run).install(engine_entry('_system/codecs')))
        self.assertEqual(run.commands[-1][:3], ['dnf', 'install', '-y'])
        self.assertTrue(run.commands[-1][3].startswith('https://'))

    def test_copr_then_nix_fallback_with_the_recorded_pin(self):
        run = FakeRunner(fail=[['dnf', 'copr']])
        yazi = engine_entry('files/yazi')
        self.assertTrue(self.fb(run, nixpkgs='github:NixOS/nixpkgs/abc').install(yazi))
        self.assertEqual(run.commands, [
            ['dnf', 'copr', 'enable', '-y', 'lihaohong/yazi'],
            ['nix', '--extra-experimental-features', 'nix-command flakes', 'profile', 'add',
             '--profile', '/nix/var/nix/profiles/default', 'github:NixOS/nixpkgs/abc#yazi'],
        ])

    def test_copr_installs_after_enabling(self):
        run = FakeRunner()
        self.assertTrue(self.fb(run).install(engine_entry('files/yazi')))
        self.assertEqual(run.commands, [['dnf', 'copr', 'enable', '-y', 'lihaohong/yazi'],
                                        ['dnf', 'install', '-y', 'yazi']])


KVER = '6.17.8-300.fc44.x86_64'
NEW_KVER = '7.2.7-200.fc44.x86_64'


def fake_root(tmp, kernels=(KVER,), devel=(KVER,)):
    """A root with these kernels in /lib/modules and kernel-devel for `devel`."""
    root = Path(tmp)
    for k in kernels:
        (root / 'lib/modules' / k).mkdir(parents=True, exist_ok=True)
        (root / 'lib/modules' / k / 'vmlinuz').write_text('')
    for k in devel:
        (root / 'usr/src/kernels' / k).mkdir(parents=True, exist_ok=True)
        (root / 'usr/src/kernels' / k / 'Makefile').write_text('')
    return root


class DriverTests(unittest.TestCase):
    NVIDIA = ['dnf', 'install', '-y', 'akmod-nvidia', 'xorg-x11-drv-nvidia-cuda', 'libva-nvidia-driver']

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = fake_root(self.tmp.name)

    def fb(self, runner):
        return firstboot.FirstBoot(run=runner, release='44', root=self.root)

    def test_nvidia_is_built_and_gets_its_kernel_arguments(self):
        run = FakeRunner()
        self.assertTrue(self.fb(run).install(engine_entry('drivers/nvidia')))
        cmds = run.commands
        i = cmds.index(self.NVIDIA)
        self.assertEqual(cmds[i + 1:], [
            ['akmods', '--force', '--kernels', KVER, '--akmod', 'nvidia'],
            ['modinfo', '-k', KVER, '-F', 'version', 'nvidia'],
            ['grubby', '--update-kernel=ALL', '--args=rd.driver.blacklist=nouveau,nova_core modprobe.blacklist=nouveau,nova_core nvidia-drm.modeset=1'],
        ])

    def test_key_is_made_before_the_akmod_is_installed(self):
        # The akmod's %posttrans starts a build at once; it signs only with a key already there.
        run = FakeRunner()
        self.assertTrue(self.fb(run).install(engine_entry('drivers/nvidia')))
        cmds = run.commands
        self.assertLess(cmds.index(['dnf', 'install', '-y', 'akmods', f'kernel-devel-matched-{KVER}']),
                        cmds.index(['kmodgenca', '-a']))
        self.assertLess(cmds.index(['kmodgenca', '-a']), cmds.index(self.NVIDIA))

    def test_newest_complete_kernel_when_the_devel_files_are_gone(self):
        # The installed kernel's kernel-devel-matched left the repositories: a whole new kernel
        # comes with its development files (not just kernel-core), and the driver is built for
        # the kernel that has them, not for the running one.
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        self.root = fake_root(other.name, kernels=(KVER, NEW_KVER), devel=(NEW_KVER,))
        run = FakeRunner(fail=[['dnf', 'install', '-y', 'akmods', f'kernel-devel-matched-{KVER}']])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(self.fb(run).install(engine_entry('drivers/nvidia')))
        cmds = run.commands
        self.assertIn(['dnf', 'install', '-y', 'akmods', f'kernel-devel-matched-{KVER}', f'kernel-devel-matched-{NEW_KVER}'], cmds)
        fallback = ['dnf', 'install', '-y', 'akmods', 'kernel', 'kernel-core', 'kernel-modules',
                    'kernel-modules-core', 'kernel-modules-extra', 'kernel-devel-matched']
        self.assertIn(fallback, cmds)
        self.assertLess(cmds.index(fallback), cmds.index(self.NVIDIA))
        builds = [c for c in cmds if c[0] in ('akmods', 'modinfo')]
        self.assertEqual(builds, [['akmods', '--force', '--kernels', NEW_KVER, '--akmod', 'nvidia'],
                                  ['modinfo', '-k', NEW_KVER, '-F', 'version', 'nvidia']])

    def test_failed_build_keeps_the_driver_pending_and_sets_no_arguments(self):
        run = FakeRunner(fail=[['akmods']])
        self.assertFalse(self.fb(run).install(engine_entry('drivers/broadcom-wl')))
        self.assertFalse(any(c[0] == 'grubby' for c in run.commands))

    def test_media_driver_has_no_build(self):
        run = FakeRunner()
        self.assertTrue(self.fb(run).install(engine_entry('drivers/intel-media')))
        self.assertFalse(any(c[0] in ('akmods', 'kmodgenca', 'grubby') for c in run.commands))

    def test_amd_media_driver_never_swaps_the_va_driver(self):
        # F44: mesa-dri-drivers provides mesa-va-drivers; only the Vulkan package is swapped.
        run = FakeRunner(installed={'rpmfusion-free-release', 'rpmfusion-nonfree-release', 'mesa-vulkan-drivers'})
        self.assertTrue(self.fb(run).install(engine_entry('drivers/amd-video')))
        swaps = [c for c in run.commands if c[:2] == ['dnf', 'swap']]
        self.assertEqual(swaps, [['dnf', 'swap', '-y', '--allowerasing', 'mesa-vulkan-drivers', 'mesa-vulkan-drivers-freeworld']])


class MainTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.pending = Path(self.dir.name) / 'pending.json'
        patches = [mock.patch.object(firstboot, 'PENDING', self.pending),
                   mock.patch.object(firstboot.os, 'geteuid', return_value=0),
                   mock.patch.object(firstboot, 'fedora_release', return_value='44'),
                   mock.patch.object(firstboot, 'ROOT', fake_root(Path(self.dir.name) / 'root'))]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.dir.cleanup)

    def write(self, modules, nixpkgs='github:NixOS/nixpkgs/abc'):
        # As the engine: json.MarshalIndent of {"version", "nixpkgs", "modules"}.
        self.pending.write_text(json.dumps({'version': 2, 'nixpkgs': nixpkgs, 'modules': modules}, indent=2) + '\n')

    def main(self, runner, sb=lambda: False):
        with contextlib.redirect_stdout(io.StringIO()):
            return firstboot.main(runner, sb=sb)

    def test_everything_installed_removes_the_file(self):
        self.write([engine_entry('extras/flathub'), engine_entry('_system/codecs')])
        self.assertEqual(self.main(FakeRunner(installed={'ffmpeg-free'})), 0)
        self.assertFalse(self.pending.exists())

    def test_bad_entries_do_not_stop_the_others_and_the_rest_is_kept(self):
        broken = {'id': 'broken', 'name': 'Broken', 'install': [{'method': 'flatpak', 'remote': 'flathub', 'ref': 7}]}
        runner = FakeRunner(fail=[['flatpak', 'install']])
        original = runner.__call__

        def run(cmd, quiet=False):   # a ref that isn't a string makes " ".join() blow up
            if any(not isinstance(c, str) for c in cmd):
                raise TypeError('bad command')
            return original(cmd, quiet)

        self.write([broken, engine_entry('extras/flathub'), engine_entry('editor/zed')])
        self.assertEqual(self.main(run), 1)
        left = json.loads(self.pending.read_text())
        self.assertEqual(left['version'], 2)
        self.assertEqual(left['nixpkgs'], 'github:NixOS/nixpkgs/abc')
        self.assertEqual([m['id'] for m in left['modules']], ['broken', 'zed'])
        self.assertEqual(left['modules'][1], engine_entry('editor/zed'))

    def write_driver(self, modules):
        hash_file = Path(self.dir.name) / 'mok.hash'
        hash_file.write_text('$6$salt$hash\n')
        self.pending.write_text(json.dumps({'version': 2, 'nixpkgs': '', 'modules': modules,
                                            'mok_hash': str(hash_file)}, indent=2) + '\n')
        return hash_file

    def test_driver_key_enrolled_after_the_build_with_secure_boot(self):
        hash_file = self.write_driver([engine_entry('drivers/nvidia'), engine_entry('editor/zed')])
        run = FakeRunner(fail=[['flatpak', 'install']])
        self.assertEqual(self.main(run, sb=lambda: True), 1)
        self.assertIn(['mokutil', '--import', '/etc/pki/akmods/certs/public_key.der', '--hash-file', str(hash_file)], run.commands)
        self.assertFalse(hash_file.exists())
        left = json.loads(self.pending.read_text())
        self.assertNotIn('mok_hash', left)
        self.assertEqual([m['id'] for m in left['modules']], ['zed'])

    def test_driver_key_waits_for_the_driver(self):
        hash_file = self.write_driver([engine_entry('drivers/nvidia')])
        run = FakeRunner(fail=[['dnf', 'install', '-y', 'akmod-nvidia']])
        self.assertEqual(self.main(run, sb=lambda: True), 1)
        self.assertFalse(any(c[0] == 'mokutil' for c in run.commands))
        self.assertTrue(hash_file.exists())
        self.assertEqual(json.loads(self.pending.read_text())['mok_hash'], str(hash_file))

    def test_no_enrolment_without_secure_boot(self):
        hash_file = self.write_driver([engine_entry('drivers/nvidia')])
        run = FakeRunner()
        self.assertEqual(self.main(run, sb=lambda: False), 0)
        self.assertFalse(any(c[0] == 'mokutil' for c in run.commands))
        self.assertFalse(hash_file.exists())
        self.assertFalse(self.pending.exists())

    def test_unreadable_file_is_left_alone(self):
        self.pending.write_text('{not json')
        self.assertEqual(self.main(FakeRunner()), 1)
        self.assertEqual(self.pending.read_text(), '{not json')


if __name__ == '__main__':
    unittest.main()
