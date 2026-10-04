"""Nix contract tests. Native daemon/SELinux acceptance is a separate gate."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nixlib
import appslib


class NixTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.patch_home = patch.object(Path, 'home', return_value=self.home)
        self.patch_home.start()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.patch_home.stop)

    def manifest(self, original=nixlib.SOURCE):
        p = nixlib.profile()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.symlink_to('arctic-1-link')
        return {'version': 3, 'elements': {'hello': {'attrPath': 'legacyPackages.x86_64-linux.hello',
                'originalUrl': original, 'url': 'github:NixOS/nixpkgs/' + 'a' * 40,
                'storePaths': ['/nix/store/abc-hello-1.0']}}}

    def test_commands_are_scoped_and_unprivileged(self):
        argv = nixlib.command('install', ['hello', 'python3Packages.requests'])
        self.assertEqual(argv[:5], ['/usr/bin/nix', '--extra-experimental-features', 'nix-command flakes', '--store', 'daemon'])
        self.assertEqual(argv[5:9], ['profile', 'add', '--profile', str(nixlib.profile())])
        self.assertEqual(argv[-2:], [nixlib.SOURCE+'#hello', nixlib.SOURCE+'#python3Packages.requests'])
        self.assertNotIn('pkexec', str(appslib.build_job({'kind': 'update', 'source': 'nix'})))
        self.assertEqual(nixlib.command('update')[-2:], ['--all', '--refresh'])

    def test_untrusted_arguments_rejected(self):
        for value in ['--profile', '../bob', '/nix/store/x', 'x;rm', 'x\n', 'github:evil/a', '#hello', 'x y', 'x.*']:
            for action in ('install', 'remove'):
                with self.subTest(value=value, action=action), self.assertRaises(nixlib.Error):
                    nixlib.command(action, [value])
        for ids in ([], ['hello']*51):
            with self.assertRaises(nixlib.Error): nixlib.command('install', ids)
        with self.assertRaises(nixlib.Error): nixlib.command('update', ['hello'])
        with self.assertRaises(nixlib.Error): nixlib.command('gc')
        with self.assertRaises(ValueError): appslib.build_job({'kind':'install','source':'nix','ids':'hello'})

    def test_pins_require_exact_commit_and_only_install(self):
        self.assertEqual(nixlib.command('install',['hello'],'a'*40)[-1], 'github:NixOS/nixpkgs/'+'a'*40+'#hello')
        for rev in ['main', 'a'*39, 'A'*40, 'a'*40+'\n']:
            with self.assertRaises(nixlib.Error): nixlib.command('install',['hello'],rev)
        with self.assertRaises(nixlib.Error): nixlib.command('update', revision='a'*40)

    def test_fresh_profile_is_empty_without_running_nix(self):
        with patch.object(nixlib, 'run_json') as run:
            self.assertEqual(nixlib.installed(), [])
            run.assert_not_called()

    def test_manifest_preserves_exact_references(self):
        manifest = self.manifest()
        with patch.object(nixlib, 'run_json', return_value=manifest):
            row = nixlib.installed()[0]
        self.assertEqual(row['id'], 'hello')
        self.assertEqual(row['attr'], 'hello')
        self.assertFalse(row['pinned'])
        self.assertEqual(row['locked'], manifest['elements']['hello']['url'])

    def test_unknown_manifest_fails_closed(self):
        self.manifest()
        for data in [{'version':2,'elements':[]}, {'version':4,'elements':{}}, {},
                     {'version':3,'elements':{'--all':{}}}]:
            with patch.object(nixlib,'run_json',return_value=data), self.assertRaises(nixlib.Error):
                nixlib.installed()

    def test_pinned_input_not_claimed_updatable(self):
        manifest = self.manifest('github:NixOS/nixpkgs/'+'a'*40)
        with patch.object(nixlib,'run_json',return_value=manifest):
            self.assertTrue(nixlib.installed()[0]['pinned'])

    def test_network_and_json_errors_not_empty_success(self):
        for result in [subprocess.CompletedProcess([],1,'','download failed'), subprocess.CompletedProcess([],0,'oops','')]:
            with patch('subprocess.run', return_value=result), self.assertRaises(nixlib.Error):
                nixlib.search('hello')
        with patch('subprocess.run',side_effect=subprocess.TimeoutExpired('nix',180)), self.assertRaises(nixlib.Error):
            nixlib.search('hello')

    def test_search_is_literal_bounded_and_validates_attributes(self):
        data = {'legacyPackages.x86_64-linux.hello':{'pname':'hello','version':'2','description':'Greeting'},
                'legacyPackages.x86_64-linux.--evil':{}, 'legacyPackages.x86_64-linux.bad;':{}}
        with patch.object(nixlib,'run_json',return_value=data) as run:
            rows=nixlib.search('hi.*')
            self.assertEqual(run.call_args.args[0][-1], r'hi\.\*')
            self.assertEqual([r['id'] for r in rows['items']], ['hello'])
        for q in ['', 'x', 'x'*81, 'hello\nworld']:
            with self.assertRaises(nixlib.Error): nixlib.search(q)

    def test_live_and_root_mutations_rejected(self):
        with patch('os.geteuid',return_value=0), self.assertRaises(nixlib.Error): nixlib.mutate('install',['hello'])
        with patch('os.geteuid',return_value=1000), patch.object(nixlib,'live',return_value=True), self.assertRaises(nixlib.Error):
            nixlib.mutate('install',['hello'])

    def test_foreign_profile_symlink_rejected(self):
        p=nixlib.profile(); p.parent.mkdir(parents=True); p.symlink_to('/home/bob/profile')
        with self.assertRaises(nixlib.Error):
            nixlib.check_profile(os.getuid())

    def test_failed_mutation_is_not_reported_success(self):
        with patch('os.geteuid',return_value=1000), patch.object(nixlib,'check_profile'), patch.object(nixlib,'live',return_value=False), \
             patch('subprocess.run',return_value=subprocess.CompletedProcess([],1)), self.assertRaises(nixlib.Error):
            nixlib.mutate('install',['hello'])

    def test_rollback_allowed_from_empty_generation(self):
        self.manifest()
        with patch('os.geteuid',return_value=1000), patch.object(nixlib,'check_profile'), patch.object(nixlib,'live',return_value=False), \
             patch.object(nixlib,'installed',return_value=[]), patch('subprocess.run',return_value=subprocess.CompletedProcess([],0)) as run:
            nixlib.mutate('rollback')
            self.assertIn('rollback',run.call_args.args[0])


if __name__ == '__main__': unittest.main()

# The administrative helper loads only RPM-owned siblings under isolated Python.
import importlib.util
_spec = importlib.util.spec_from_file_location('nix_system', Path(nixlib.__file__).with_name('nix-system.py'))
shared = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shared)


class SharedNixTests(unittest.TestCase):
    def data(self):
        return {'version': 3, 'elements': {'lazygit': {'attrPath': 'legacyPackages.x86_64-linux.lazygit',
                'originalUrl': shared.INSTALLER_PIN, 'active': True, 'priority': 5, 'outputs': None}}}

    def test_only_known_installer_entries_can_migrate(self):
        self.assertEqual(shared.plan(self.data()), [nixlib.SOURCE+'#legacyPackages.x86_64-linux.lazygit'])
        for key, value in [('attrPath','legacyPackages.x86_64-linux.hello'), ('originalUrl','github:someone/code'),
                           ('priority',1), ('active',False), ('outputs',['dev'])]:
            data=self.data(); data['elements']['lazygit'][key]=value
            with self.subTest(key=key), self.assertRaises(ValueError): shared.plan(data)

    def test_sanitized_environment_drops_caller_configuration(self):
        for key in ['NIX_CONFIG','NIX_PATH','PYTHONPATH','XDG_CONFIG_HOME','LD_PRELOAD']:
            self.assertNotIn(key,shared.ENV)
        self.assertEqual(shared.ENV['HOME'],'/root')
        with patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,'')) as run:
            shared.run(['/usr/bin/nix','--version'])
            self.assertIs(run.call_args.kwargs['env'],shared.ENV)

    def test_user_and_arbitrary_actions_are_rejected(self):
        with patch('os.geteuid',return_value=1000), patch.object(shared,'run') as run:
            self.assertEqual(shared.main(['update']),1)
            run.assert_not_called()
        for args in [['update','--profile','/home/bob'], ['install'], []]:
            self.assertEqual(shared.main(args),1)

    def test_failed_build_never_switches_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            profile=Path(folder)/'default'; old=Path(folder)/'old'; old.mkdir(); profile.symlink_to(old)
            with patch.object(shared,'PROFILE',profile), patch.object(shared,'manifest',return_value=self.data()), \
                 patch.object(shared,'run',side_effect=subprocess.CalledProcessError(1,['nix'])) as run:
                with self.assertRaises(subprocess.CalledProcessError): shared.update()
                self.assertEqual(profile.resolve(),old)
                self.assertEqual(run.call_count,1)
                self.assertNotIn('/usr/bin/nix-env',run.call_args.args[0])
