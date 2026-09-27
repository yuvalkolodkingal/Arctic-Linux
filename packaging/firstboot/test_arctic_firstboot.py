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
    return {'id': data['id'], 'name': data['name'], 'install': install}


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
        flathub = engine_entry('utilities/flathub')
        self.assertNotIn('ref', flathub['install'][0])       # json:"ref,omitempty", ref = ""
        self.assertNotIn('packages', flathub['install'][0])
        self.assertIn('verified', flathub['install'][0])     # not omitempty


class MethodTests(unittest.TestCase):
    def fb(self, runner, nixpkgs=''):
        return firstboot.FirstBoot(run=runner, release='44', nixpkgs=nixpkgs)

    def test_flathub_without_ref_only_adds_the_remote(self):
        run = FakeRunner()
        self.assertTrue(self.fb(run).install(engine_entry('utilities/flathub')))
        self.assertEqual(run.commands, [['flatpak', 'remote-add', '--system', '--if-not-exists', 'flathub',
                                         'https://dl.flathub.org/repo/flathub.flatpakrepo']])

    def test_flatpak_app_adds_its_remote_once_then_installs(self):
        run = FakeRunner()
        fb = self.fb(run)
        zed = engine_entry('editor/zed')
        ref = zed['install'][0]['ref']
        self.assertTrue(fb.install(zed))
        self.assertTrue(fb.install(engine_entry('utilities/flathub')))
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


class MainTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.pending = Path(self.dir.name) / 'pending.json'
        patches = [mock.patch.object(firstboot, 'PENDING', self.pending),
                   mock.patch.object(firstboot.os, 'geteuid', return_value=0),
                   mock.patch.object(firstboot, 'fedora_release', return_value='44')]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.dir.cleanup)

    def write(self, modules, nixpkgs='github:NixOS/nixpkgs/abc'):
        # As the engine: json.MarshalIndent of {"version", "nixpkgs", "modules"}.
        self.pending.write_text(json.dumps({'version': 2, 'nixpkgs': nixpkgs, 'modules': modules}, indent=2) + '\n')

    def main(self, runner):
        with contextlib.redirect_stdout(io.StringIO()):
            return firstboot.main(runner)

    def test_everything_installed_removes_the_file(self):
        self.write([engine_entry('utilities/flathub'), engine_entry('_system/codecs')])
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

        self.write([broken, engine_entry('utilities/flathub'), engine_entry('editor/zed')])
        self.assertEqual(self.main(run), 1)
        left = json.loads(self.pending.read_text())
        self.assertEqual(left['version'], 2)
        self.assertEqual(left['nixpkgs'], 'github:NixOS/nixpkgs/abc')
        self.assertEqual([m['id'] for m in left['modules']], ['broken', 'zed'])
        self.assertEqual(left['modules'][1], engine_entry('editor/zed'))

    def test_unreadable_file_is_left_alone(self):
        self.pending.write_text('{not json')
        self.assertEqual(self.main(FakeRunner()), 1)
        self.assertEqual(self.pending.read_text(), '{not json')


if __name__ == '__main__':
    unittest.main()
