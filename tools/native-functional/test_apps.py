"""Additive inventory/MIME controls; these fixtures never claim a guest result."""
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import apps as A

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location('apps_photo_composer', HERE / 'compose-photo-probe.py')
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)
MIME = (ROOT / 'packaging/desktop/live-mimeapps.list').read_bytes()
CONTEXT = dict(source_sha='1' * 40, iso_sha256='2' * 64, iso_bytes=12345,
               **{key: '3' * 64 for key in A.CONTEXT - {'source_sha', 'iso_sha256', 'iso_bytes'}})
BOOT = '11111111-1111-1111-1111-111111111111'


def record():
    return dict(schema='arctic-native-app-defaults-v1', stage='installed', status='passed',
        release_acceptance=False, context=CONTEXT, boot_id=BOOT, desktop_uid=1000, active_desktop_session='2',
        packages={name: dict(version='1.2', release='1.fc44', arch='x86_64') for name in A.PACKAGES},
        pcmanfm=dict(owner='pcmanfm', requirements=[A.GTK3]), mime_defaults=A.mime_defaults(MIME), scope='read-only fixture')


class AppDefaultControls(unittest.TestCase):
    def inventory_probe(self, rows, requirements=None):
        """Run the real read-only probe with labelled synthetic guest commands."""
        prefix = ['runuser', '-u', 'fixture', '--', 'env', 'XDG_SESSION_ID=2']
        mimes = A.mime_defaults(MIME)
        def command(argv):
            if argv == prefix + ['id', '-u']: return '1000'
            if argv[:2] == ['loginctl', 'show-session']:
                return {'User': '1000', 'Type': 'wayland', 'Active': 'yes'}[argv[4]]
            if argv == ['rpm', '-q', '--qf', '%{NAME}\t%{VERSION}\t%{RELEASE}\t%{ARCH}\n', *A.PACKAGES]:
                return '\n'.join(rows)
            if argv == ['rpm', '-qf', '--qf', '%{NAME}\n', '/usr/bin/pcmanfm']: return 'pcmanfm'
            if argv == ['rpm', '-q', '--requires', 'pcmanfm']:
                return A.GTK3 if requirements is None else requirements
            self.assertEqual(argv[:len(prefix)], prefix)
            self.assertEqual(argv[len(prefix):-1], ['LC_ALL=C', 'gio', 'mime'])
            return 'Default application for “' + argv[-1] + '”: ' + mimes[argv[-1]]
        def proc_read(path, *args, **kwargs):
            if str(path) == '/proc/cmdline': return 'fixture-installed'
            if str(path) == '/proc/sys/kernel/random/boot_id': return BOOT
            raise AssertionError('Unexpected fixture file read')
        with patch.object(A, 'command', side_effect=command), patch.object(A.Path, 'read_text', proc_read):
            return A.probe(prefix, 'installed', CONTEXT, mimes)

    def test_observed_caret_version_passes_actual_inventory_and_report(self):
        # This VERSION is independently present in the authenticated A2
        # fresh-defaults inventory; the failed extra query row was not saved.
        version = '1.4.0^20251022git09087446'
        rows = [name + '\t' + (version if name == 'pcmanfm' else '1.2') + '\t1.fc44\tx86_64'
                for name in A.PACKAGES]
        item = self.inventory_probe(rows)
        self.assertEqual(item['packages']['pcmanfm']['version'], version)
        self.assertEqual(set(item['packages']), set(A.PACKAGES))
        self.assertEqual(item['pcmanfm']['requirements'], [A.GTK3])
        self.assertEqual(item['mime_defaults'], A.mime_defaults(MIME))
        self.assertFalse(item['release_acceptance'])
        self.assertEqual(A.validate_report(item, CONTEXT, A.mime_defaults(MIME))['packages'], item['packages'])

    def test_caret_report_support_does_not_admit_other_malformed_nevra(self):
        for version in ('1.4.0^20251022git09087446', '1.4.0~rc1', '1.4.0+git.1'):
            item = record(); item['packages']['pcmanfm']['version'] = version
            A.validate_report(item, CONTEXT, A.mime_defaults(MIME))
        for key, value in (('version', ''), ('version', '1.4.0\nsecret'), ('version', '1.4.0\t2'),
                           ('version', '1.4.0/2'), ('version', '1.4.0\x00'), ('version', 1),
                           ('release', '1^git.fc44'), ('arch', 'x86_64^git'), ('arch', 'noarch')):
            item = record(); item['packages']['pcmanfm'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                A.validate_report(item, CONTEXT, A.mime_defaults(MIME))

    def test_caret_inventory_support_preserves_closed_package_and_gtk3_gates(self):
        rows = [name + '\t1.2\t1.fc44\tx86_64' for name in A.PACKAGES]
        index = A.PACKAGES.index('pcmanfm')
        variants = [rows[:-1], rows + [rows[0]], rows + ['unknown\t1.2\t1.fc44\tx86_64']]
        for replacement in ('pcmanfm\t\t1.fc44\tx86_64', 'pcmanfm\t1.4.0/2\t1.fc44\tx86_64',
                            'pcmanfm\t1.4.0\t1^git.fc44\tx86_64', 'pcmanfm\t1.4.0\t1.fc44\tx86_64^git',
                            'pcmanfm\t1.4.0\t1.fc44\tnoarch', 'pcmanfm\t1.4.0\t1.fc44\tx86_64\textra'):
            changed = rows.copy(); changed[index] = replacement; variants.append(changed)
        for variant in variants:
            with self.subTest(rows=variant), self.assertRaises(RuntimeError): self.inventory_probe(variant)
        caret = rows.copy(); caret[index] = 'pcmanfm\t1.4.0^20251022git09087446\t1.fc44\tx86_64'
        for requirements in ('', A.GTK3 + '\nlibgtk-x11-2.0.so.0()(64bit)'):
            with self.subTest(requirements=requirements), self.assertRaisesRegex(RuntimeError, 'GTK3-only'):
                self.inventory_probe(caret, requirements)

    def test_complete_manifest_mime_context_and_original_native_identity(self):
        item = record()
        proof = {key: item[key] for key in ('stage', 'boot_id', 'desktop_uid', 'active_desktop_session')}
        result = A.validate_report(item, CONTEXT, A.mime_defaults(MIME), proof)
        self.assertEqual(set(result['packages']), set(A.PACKAGES))
        self.assertFalse(result['release_acceptance'])

    def test_wrong_image_missing_package_gtk2_and_fallback_defaults_fail(self):
        variations = []
        item = record(); item['context'] = dict(CONTEXT, iso_sha256='4' * 64); variations.append(item)
        item = record(); item['packages'].pop('nano'); variations.append(item)
        item = record(); item['packages']['pcmanfm']['arch'] = 'noarch'; variations.append(item)
        item = record(); item['pcmanfm']['requirements'] = []; variations.append(item)
        item = record(); item['pcmanfm']['requirements'] = sorted([A.GTK3, 'libgtk-x11-2.0.so.0()(64bit)']); variations.append(item)
        item = record(); item['pcmanfm']['owner'] = 'replacement'; variations.append(item)
        item = record(); item['mime_defaults']['text/plain'] = 'fallback.desktop'; variations.append(item)
        item = record(); item['mime_defaults'].pop('audio/opus'); variations.append(item)
        item = record(); item['status'] = 'failed'; variations.append(item)
        item = record(); item['release_acceptance'] = True; variations.append(item)
        for item in variations:
            with self.subTest(item=item), self.assertRaises(RuntimeError):
                A.validate_report(item, CONTEXT, A.mime_defaults(MIME))

    def test_other_boot_user_session_and_stage_are_rejected(self):
        item = record()
        proof = {key: item[key] for key in ('stage', 'boot_id', 'desktop_uid', 'active_desktop_session')}
        for key, value in [('stage', 'live'), ('boot_id', '22222222-2222-2222-2222-222222222222'),
                           ('desktop_uid', 1001), ('active_desktop_session', '3')]:
            with self.subTest(key=key), self.assertRaisesRegex(RuntimeError, 'original native boot/session'):
                A.validate_report(item, CONTEXT, A.mime_defaults(MIME), dict(proof, **{key: value}))

    def test_gio_requires_the_actual_default_not_a_registered_application(self):
        good = 'Default application for “text/plain”: featherpad.desktop\nRegistered applications:\n nano.desktop'
        self.assertEqual(A.gio_default(good, 'text/plain'), 'featherpad.desktop')
        for text in ('No default applications for “text/plain”\nRegistered applications:\n featherpad.desktop',
                     good + '\nDefault application for “text/plain”: nano.desktop',
                     'Default application for “text/html”: featherpad.desktop',
                     'Default application for “text/plain2”: featherpad.desktop'):
            with self.subTest(text=text), self.assertRaises(RuntimeError): A.gio_default(text, 'text/plain')

    def test_duplicate_multiple_or_wrong_role_source_defaults_are_rejected(self):
        for data in (MIME + b'\n[Default Applications]\n',
                     MIME.replace(b'text/plain=featherpad.desktop;', b'text/plain=featherpad.desktop;nano.desktop;'),
                     MIME.replace(b'text/plain=featherpad.desktop;', b'text/plain=nano.desktop;')):
            with self.subTest(data=data[:20]), self.assertRaises(Exception): A.mime_defaults(data)

    def test_composed_execution_supplement_embeds_exact_source_and_refuses_host(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'probe.py'
            C.compose(ROOT, out, {key: CONTEXT[key] for key in ('source_sha', 'iso_sha256', 'iso_bytes')}, ROOT)
            source = out.read_text(); compile(source, str(out), 'exec')
            self.assertIn('ARCTIC-NATIVE-APP-DEFAULTS', source)
            self.assertIn(hashlib.sha256(MIME).hexdigest(), source)
            self.assertIn(hashlib.sha256((HERE / 'apps.py').read_bytes()).hexdigest(), source)
            result = subprocess.run(['python3', str(out), 'installed'], capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Requires root in the owned QEMU test guest', result.stderr)
            self.assertNotIn('ARCTIC-NATIVE-APP-DEFAULTS', result.stdout)

    def test_probe_queries_real_desktop_environment_without_mutation_commands(self):
        prefix = ['runuser', '-u', 'ci', '--', 'env', 'XDG_SESSION_ID=2', 'HOME=/home/ci']
        mimes = A.mime_defaults(MIME)
        calls = []
        def command(argv):
            calls.append(argv)
            if argv[-2:] == ['id', '-u']: return '1000'
            if argv[:2] == ['loginctl', 'show-session']:
                return {'User': '1000', 'Type': 'wayland', 'Active': 'yes'}[argv[4]]
            if argv[:3] == ['rpm', '-q', '--qf']:
                return '\n'.join(name + '\t1.2\t1.fc44\tx86_64' for name in A.PACKAGES)
            if argv[:2] == ['rpm', '-qf']: return 'pcmanfm'
            if argv[:3] == ['rpm', '-q', '--requires']: return A.GTK3
            self.assertEqual(argv[:len(prefix)], prefix)
            self.assertEqual(argv[len(prefix):-1], ['LC_ALL=C', 'gio', 'mime'])
            return 'Default application for “' + argv[-1] + '”: ' + mimes[argv[-1]]
        with patch.object(A, 'command', side_effect=command):
            result = A.probe(prefix, 'installed', CONTEXT, mimes)
        self.assertEqual(result['mime_defaults'], mimes)
        self.assertEqual(sum('gio' in argv for argv in calls), len(mimes))
        self.assertFalse(any(word in ('set', 'install', 'remove', 'chvt', 'arctic-open') for argv in calls for word in argv))


if __name__ == '__main__':
    unittest.main()
