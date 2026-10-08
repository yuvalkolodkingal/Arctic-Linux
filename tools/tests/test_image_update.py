"""Negative controls for the disabled same-image update lane and serial gates."""
import importlib.util
import json
from pathlib import Path
import unittest

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
                             ('initial', 'signed-offline-update-ready'), ('final', 'new-boot'),
                             ('final', 'signed-offline-update-completed')):
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
        manifest = json.loads((ROOT / 'tools/image-update/execution-manifest.json').read_text())
        self.assertFalse(manifest['ready'])
        with self.assertRaisesRegex(RuntimeError, 'disabled'):
            guard.verify(manifest, ROOT)


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
