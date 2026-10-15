"""Readiness and negative controls for the same-image update lane and serial gates."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


records = load('update_records', 'tools/image-update/verify-records.py')
guard = load('update_guard', 'tools/image-update/guard.py')


class UpdateRecordsTest(unittest.TestCase):
    def serial(self, phase):
        stage = 'live' if phase == 'live' else 'installed'
        names = records.COMMON | ({'live-mutation-denied'} if phase == 'live' else
                                 records.INSTALLED | (records.INITIAL if phase == 'initial' else records.FINAL))
        rows = [dict(stage=stage, check=name, status='passed', detail='synthetic control') for name in sorted(names)]
        if phase == 'initial':
            next(row for row in rows if row['check'] == 'engine-version-change')['status'] = 'unrun'
        marker = 'ARCTIC-LIVE-SMOKE-EXIT=0' if stage == 'live' else 'ARCTIC-INSTALLED-SMOKE-EXIT=0'
        return '\n'.join(['ARCTIC-NIX-ACCEPTANCE ' + json.dumps(row) for row in rows] + [marker])

    def test_all_three_phases_accept_only_complete_records(self):
        for phase in ('live', 'initial', 'final'):
            with self.subTest(phase=phase):
                proof = records.verify(self.serial(phase), phase)
                self.assertFalse(proof['release_acceptance'])
                self.assertEqual(proof['nix_engine_version_change'], 'unrun' if phase == 'initial' else None)

    def test_missing_gui_signature_update_or_new_boot_never_pass(self):
        for phase, check in (('live', 'live-mutation-denied'), ('initial', 'graphical-foot'),
                             ('initial', 'voxtype-legacy-migration-seeded'),
                             ('initial', 'signed-offline-update-ready'), ('final', 'new-boot'),
                             ('final', 'signed-offline-update-completed'),
                             ('final', 'voxtype-resident-config-migrated'),
                             ('final', 'voxtype-migration-prelogin-private'),
                             ('final', 'whats-new-voxtype-card')):
            text = '\n'.join(line for line in self.serial(phase).splitlines()
                             if not line.startswith('ARCTIC-NIX-ACCEPTANCE ') or json.loads(line.split(' ', 1)[1])['check'] != check)
            with self.subTest(phase=phase, check=check), self.assertRaises(RuntimeError):
                records.verify(text, phase)

    def test_failed_unrun_duplicate_wrong_stage_or_unknown_checks_fail(self):
        original = self.serial('final')
        lines = original.splitlines()
        for text in (original.replace('"passed"', '"failed"', 1),
                     original.replace('"passed"', '"unrun"', 1), original + '\n' + lines[0],
                     original.replace('"installed"', '"live"', 1),
                     original.replace('"new-boot"', '"invented-check"')):
            with self.subTest(text=text[:120]), self.assertRaises(RuntimeError):
                records.verify(text, 'final')

    def test_missing_duplicate_failed_and_truncated_generic_markers_fail(self):
        original = self.serial('final')
        for marker in ('', 'ARCTIC-INSTALLED-SMOKE-EXIT=1', 'ARCTIC-INSTALLED-SMOKE-EXIT=',
                       'ARCTIC-INSTALLED-SMOKE-EXIT=0\nARCTIC-INSTALLED-SMOKE-EXIT=0'):
            with self.subTest(marker=marker), self.assertRaises(RuntimeError):
                records.verify(original.replace('ARCTIC-INSTALLED-SMOKE-EXIT=0', marker), 'final')

    def test_disabled_manifest_stops_before_external_actions(self):
        manifest = {'ready': False, 'release_acceptance': False,
                    'image': None, 'stable': None, 'execution_files': {}}
        self.assertFalse(manifest['ready'])
        with self.assertRaisesRegex(RuntimeError, 'disabled'):
            guard.verify(manifest, ROOT)

    def test_checked_in_manifest_is_unbound_until_fresh_image_succeeds(self):
        manifest = json.loads((ROOT / 'tools/image-update/execution-manifest.json').read_text())
        self.assertIs(manifest['ready'], False)
        self.assertIs(manifest['release_acceptance'], False)
        self.assertIsNone(manifest['image'])
        self.assertIsNone(manifest['stable'])
        self.assertEqual(manifest['execution_files'], {})
        self.assertFalse((ROOT / '.github/qualification-20261010.update').exists())


class SigningFingerprintTest(unittest.TestCase):
    def setUp(self):
        self.guest = load('update_nix_signature_guest', 'tools/nix-acceptance/guest.py')
        self.expected = '80F75DE9A23B632246FD1FF1BD1A642B5436645A'

    def output(self, fingerprint):
        return ('synthetic.rpm:\n'
                f'    Header OpenPGP V4 RSA/SHA256 signature, key fingerprint: {fingerprint}: OK\n'
                '    Header SHA256 digest: OK\n'
                '    Payload SHA256 digest: OK')

    def test_signature_must_match_full_pinned_fingerprint(self):
        from unittest.mock import patch
        with patch.object(self.guest, 'run', return_value=self.output(self.expected.lower())):
            self.assertIn(self.expected.lower(),
                          self.guest.verified_rpm_signatures(['synthetic.rpm'], self.expected))
        for fingerprint in ('0' * 40, self.expected[-8:]):
            with self.subTest(fingerprint=fingerprint), \
                    patch.object(self.guest, 'run', return_value=self.output(fingerprint)), \
                    self.assertRaisesRegex(RuntimeError, 'Unexpected signing key'):
                self.guest.verified_rpm_signatures(['synthetic.rpm'], self.expected)


class VoxTypeStableMigrationTest(unittest.TestCase):
    def setUp(self):
        self.guest = load('update_voxtype_migration_guest', 'tools/nix-acceptance/guest.py')
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / 'home'
        self.config_dir = self.home / '.config/voxtype'
        self.config_dir.mkdir(parents=True)
        (self.home / '.config').chmod(0o700)
        self.config_dir.chmod(0o700)
        self.state = self.root / 'state'
        self.state.mkdir()
        self.notes = self.root / 'whats-new.json'
        self.user = SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid(),
                                    pw_name='fixture', pw_dir=str(self.home))
        for name, data in (('verified.json', json.dumps({
                                'integration': 'upstream-direct-v1', 'version': '1.1.1',
                                'source_commit': '014c56105b2f071bb3457c51a95c38be380e5124'}).encode()),
                           ('upstream-direct-v1', b'upstream-direct-v1\n')):
            path = self.state / name
            path.write_bytes(data)
            path.chmod(0o644)
        self.model = self.guest.VOXTYPE_MODELS[0]
        self.language = self.guest.VOXTYPE_LANGUAGES[0]
        self.config = self.config_dir / 'config.toml'
        self.config.write_bytes(self.guest.voxtype_managed_config(self.model, self.language, True))
        self.config.chmod(0o600)
        (self.home / '.local/state/arctic').mkdir(parents=True)
        self.notes.write_text(json.dumps({'schema': 1, 'update_id': 'arctic-1.2.1-old',
                                          'items': [{'title': 'old', 'text': 'old'}]}))

    def test_fixture_bytes_are_exactly_the_migration_helpers_six_known_configs(self):
        migration = runpy.run_path(str(ROOT / 'packaging/dictation/arctic-voxtype-migrate-config'))
        for model in self.guest.VOXTYPE_MODELS:
            for language in self.guest.VOXTYPE_LANGUAGES:
                for resident in (False, True):
                    with self.subTest(model=model, language=language, resident=resident):
                        self.assertEqual(self.guest.voxtype_managed_config(model, language, resident),
                                         migration['canonical'](model, language, resident))

    def test_seed_and_post_reboot_proof_require_one_migrated_generation(self):
        generation = self.state / 'config-generation-resident-v1.json'
        generation.write_text('{}')
        generation.chmod(0o644)
        pending = self.state / 'config-resident-v1.pending'
        pending.write_text('resident-model-v1\n')
        pending.chmod(0o644)
        expected = self.guest.seed_voxtype_update_fixture(
            self.user, state=self.state, notes_path=self.notes)
        self.assertEqual(self.config.read_bytes(),
                         self.guest.voxtype_managed_config(self.model, self.language, False))
        self.assertFalse(generation.exists())
        self.assertFalse(pending.exists())

        self.config.write_bytes(self.guest.voxtype_managed_config(self.model, self.language, True))
        generation.write_text(json.dumps({
            'schema': 'arctic-voxtype-config-generation-v1',
            'migration': 'resident-model-v1', 'user': 'fixture',
            'generation': 'resident-model-v1', 'outcome': 'migrated'}))
        generation.chmod(0o644)
        result = self.guest.verify_voxtype_migration_files(
            self.user, expected, state=self.state)
        self.assertEqual(result['generation']['outcome'], 'migrated')
        generation.write_text(generation.read_text().replace('migrated', 'already-current'))
        with self.assertRaisesRegex(RuntimeError, 'outcome differs'):
            self.guest.verify_voxtype_migration_files(self.user, expected, state=self.state)

    def test_offline_recovery_must_finish_before_the_update_fixture_is_seeded(self):
        setup = self.state / 'setup.state'
        setup.write_bytes(b'ready\n')
        setup.chmod(0o644)
        expected = {'fixture': 'seeded'}
        with patch.object(self.guest, 'VOXTYPE_STATE', self.state), \
                patch.object(self.guest, 'run', return_value='inactive'), \
                patch.object(self.guest, 'seed_voxtype_update_fixture', return_value=expected) as seed:
            self.assertEqual(self.guest.seed_ready_voxtype_update_fixture(self.user), expected)
        seed.assert_called_once_with(self.user)
        (self.state / 'pending').write_text('1.1.1\n')
        with patch.object(self.guest, 'VOXTYPE_STATE', self.state), \
                patch.object(self.guest, 'run', return_value='inactive'), \
                self.assertRaisesRegex(RuntimeError, 'remains queued'):
            self.guest.seed_ready_voxtype_update_fixture(self.user)

    def test_custom_config_is_rejected_before_state_or_seen_mutation(self):
        self.config.write_text('custom = true\n')
        generation = self.state / 'config-generation-resident-v1.json'
        generation.write_text('keep')
        generation.chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, 'not one exact managed'):
            self.guest.seed_voxtype_update_fixture(
                self.user, state=self.state, notes_path=self.notes)
        self.assertEqual(generation.read_text(), 'keep')
        self.assertFalse((self.home / '.local/state/arctic/whats-new-seen').exists())

    def test_updated_voxtype_card_requires_new_rpm_id_and_one_mapped_layer(self):
        expected = self.guest.seed_voxtype_update_fixture(
            self.user, state=self.state, notes_path=self.notes)
        new_id = 'arctic-1.2.1-new'
        self.notes.write_text(json.dumps({'schema': 1, 'update_id': new_id, 'items': [{
            'title': 'Official VoxType dictation',
            'text': 'VoxType runs multilingual Whisper locally for Hebrew and English; '
                    'audio stays on this computer.'}]}))
        def command(argv, **kwargs):
            if argv[:3] == ['rpm', '-q', '--qf']:
                return new_id
            if argv[-3:] == ['mmsg', 'get', 'all-layers']:
                return json.dumps({'layers': [{'name': 'arctic-whats-new', 'layer': 'top'}]})
            raise AssertionError(argv)
        with patch.object(self.guest, 'run', side_effect=command):
            result = self.guest.verify_whats_new_voxtype_card(
                ['desktop'], self.user, expected, notes_path=self.notes)
        self.assertEqual(result['update_id'], new_id)
        self.assertEqual(result['mapped_layers'], 1)

    def test_prelogin_private_unit_requires_ordering_idle_daemon_and_clean_journals(self):
        unit = ('Before=systemd-user-sessions.service user@.service\nPrivateNetwork=yes\n'
                'RestrictAddressFamilies=AF_UNIX\nStandardOutput=null\nStandardError=null\n')
        values = {
            'arctic-voxtype-config-migration.service':
                'Result=success\nExecMainCode=exited\nExecMainStatus=0\n'
                'ExecMainStartTimestampMonotonic=100\nExecMainExitTimestampMonotonic=200',
            'systemd-user-sessions.service': 'ActiveEnterTimestampMonotonic=300',
            f'user@{self.user.pw_uid}.service': 'ActiveEnterTimestampMonotonic=400',
        }
        def command(argv, **kwargs):
            if argv[:2] == ['systemctl', 'show']:
                return values[argv[2]]
            if argv[:2] == ['systemctl', 'cat']:
                return unit
            if argv[:4] == ['desktop', 'systemctl', '--user', 'show']:
                return 'inactive'
            if argv[:2] == ['journalctl', '-b'] or argv[:4] == ['desktop', 'journalctl', '--user', '-b']:
                return 'Started safe migration.\nFinished safe migration.'
            raise AssertionError(argv)
        with patch.object(self.guest, 'run', side_effect=command):
            result = self.guest.verify_voxtype_migration_boot(['desktop'], self.user)
        self.assertLessEqual(result['migration_finished'], result['login_started'])
        values[f'user@{self.user.pw_uid}.service'] = 'ActiveEnterTimestampMonotonic=150'
        with patch.object(self.guest, 'run', side_effect=command), \
                self.assertRaisesRegex(RuntimeError, 'before login'):
            self.guest.verify_voxtype_migration_boot(['desktop'], self.user)


class HigherEvrTest(unittest.TestCase):
    def setUp(self):
        self.guest = load('update_nix_guest', 'tools/nix-acceptance/guest.py')

    def check(self, before, after, comparator):
        from unittest.mock import patch
        def run(argv, **kwargs):
            if argv[1] == '-qp':
                return 'arctic-shell\t' + '\t'.join(after)
            if argv[1] == '-q':
                return 'arctic-shell\t' + '\t'.join(before)
            if argv[1] == '--eval':
                self.assertIn('rpm.vercmp(', argv[2])
                return str(comparator)
            raise AssertionError(argv)
        with patch.object(self.guest, 'run', side_effect=run):
            return self.guest.higher_downloaded_evr(['synthetic.rpm'], {'arctic-shell'})

    def test_higher_equal_lower_versions_and_epochs(self):
        self.assertEqual(self.check(('0', '1.2', '1.preview.1'), ('0', '1.2', '1.20261008'), 1)
                         ['arctic-shell']['rpm_order'], 1)
        self.assertEqual(self.check(('0', '1.2', '9'), ('1', '1.0', '1'), -1)
                         ['arctic-shell']['rpm_order'], 1)
        for before, after, compare in ((('0', '1.2', '1'), ('0', '1.2', '1'), 0),
                                       (('0', '1.2', '2'), ('0', '1.2', '1'), -1),
                                       (('1', '1.0', '1'), ('0', '9.0', '9'), 1)):
            with self.subTest(before=before, after=after), self.assertRaisesRegex(RuntimeError, 'not higher'):
                self.check(before, after, compare)

    @unittest.skipUnless(shutil.which('rpm'), 'real RPM comparison needs the Fedora test image')
    def test_real_rpm_rules_for_preview_replacement_epochs_and_version_precedence(self):
        from unittest.mock import patch
        for before, after, expected in ((('0', '1.2', '1.preview.1'), ('0', '1.2', '1.20261008'), True),
                                        (('0', '1.2', '1'), ('0', '1.2', '1'), False),
                                        (('0', '1.2', '2'), ('0', '1.2', '1'), False),
                                        (('0', '2.0', '1'), ('0', '1.0', '999'), False),
                                        (('0', '2.0', '1'), ('1', '1.0', '1'), True),
                                        (('1', '1.0', '1'), ('0', '9.0', '999'), False)):
            def run(argv, **kwargs):
                if argv[1] == '-qp':
                    return 'arctic-shell\t' + '\t'.join(after)
                if argv[1] == '-q':
                    return 'arctic-shell\t' + '\t'.join(before)
                return subprocess.check_output(argv, text=True).strip()
            with self.subTest(before=before, after=after), patch.object(self.guest, 'run', side_effect=run):
                if expected:
                    self.assertIn('arctic-shell', self.guest.higher_downloaded_evr(['control.rpm'], {'arctic-shell'}))
                else:
                    with self.assertRaisesRegex(RuntimeError, 'not higher'):
                        self.guest.higher_downloaded_evr(['control.rpm'], {'arctic-shell'})

    def test_missing_or_duplicate_downloaded_replacements_fail(self):
        from unittest.mock import patch
        for query in ('other-package\t0\t1.2\t2', 'arctic-shell\t0\t1.2\t2\narctic-shell\t0\t1.2\t3'):
            with self.subTest(query=query), patch.object(self.guest, 'run', return_value=query), self.assertRaises(RuntimeError):
                self.guest.higher_downloaded_evr(['control.rpm'], {'arctic-shell'})
