"""Bounded setup diagnostics only; no VM, model, microphone or transcription."""
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location(
    'dictation_collector_diagnostics', Path(__file__).with_name('guest_check.py'))
guest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guest)


def restore_collector_diagnostics(text):
    """Remove only this diagnostic layer and recover its exact reviewed parent bytes."""
    marker = 'COLLECTOR_SETUP_STAGES = '
    if marker not in text:
        return text
    start = text.index(marker)
    end = text.index('def verify_small_cpu_fixture', start)
    text = text[:start] + '\n' + text[end:]
    owned_markers = {
        indent + "mark_collector_setup('" + stage + "')\n"
        for stage in guest.COLLECTOR_SETUP_STAGES
        for indent in ('    ', '        ')
    }
    text = ''.join(line for line in text.splitlines(keepends=True)
                   if line not in owned_markers)
    revised = """if __name__ == '__main__':
    try:
        sys.exit(main())
    except (Invalid, OSError, ValueError, subprocess.TimeoutExpired, KeyError, TypeError) as error:
        try:
            code = collector_diagnostic_code(COLLECTOR_SETUP_STAGE, error)
        except (Invalid, OSError, ValueError, subprocess.TimeoutExpired, KeyError, TypeError):
            code = 'collector-unknown'
        print('ARCTIC-DICTATION-COLLECTOR-ERROR ' + json.dumps(
            {'code': code, 'release_acceptance': False}, sort_keys=True), flush=True)
        sys.exit(1)
"""
    original = """if __name__ == '__main__':
    try:
        sys.exit(main())
    except (Invalid, OSError, ValueError, subprocess.TimeoutExpired, KeyError, TypeError):
        print('ARCTIC-DICTATION-COLLECTOR-ERROR {"code":"collector-guard-or-setup-failed","release_acceptance":false}', flush=True)
        sys.exit(1)
"""
    if text.count(revised) != 1:
        raise AssertionError('collector diagnostic outer guard differs')
    return text.replace(revised, original)


class PrivateInvalid(guest.Invalid):
    def __str__(self):
        raise AssertionError('exception text must remain private')

    def __repr__(self):
        raise AssertionError('exception representation must remain private')


class PrivateValue(ValueError):
    def __str__(self):
        raise AssertionError('exception text must remain private')

    def __repr__(self):
        raise AssertionError('exception representation must remain private')


class CollectorDiagnosticControls(unittest.TestCase):
    def test_complete_layer_rolls_back_to_exact_parent_source(self):
        current = Path(guest.__file__).read_text()
        parent = subprocess.check_output([
            'git', '-C', str(Path(__file__).resolve().parents[2]), 'show',
            '2e1e100f636f87799ef44e29cd2156fb1d818de3:tools/dictation-qualification/guest_check.py'
        ], text=True)
        restored = restore_collector_diagnostics(current)
        self.assertEqual(restored, parent)
        self.assertEqual(restore_collector_diagnostics(restored), parent)

    def test_every_source_owned_stage_and_caught_class_has_one_fixed_code(self):
        errors = (
            (PrivateInvalid('private transcript'), 'invalid'),
            (OSError('private path'), 'os-error'),
            (PrivateValue('private text'), 'value-error'),
            (subprocess.TimeoutExpired(['private', 'argv'], 1,
                                       output=b'private output', stderr=b'private stderr'), 'timeout'),
            (KeyError('private key'), 'key-error'),
            (TypeError('private type'), 'type-error'),
        )
        for stage in guest.COLLECTOR_SETUP_STAGES:
            for error, label in errors:
                with self.subTest(stage=stage, label=label):
                    code = guest.collector_diagnostic_code(stage, error)
                    self.assertEqual(code, 'collector-' + stage + '-' + label)
                    self.assertRegex(code, r'^[a-z0-9-]{1,80}$')
                    public = json.dumps({'code': code, 'release_acceptance': False}, sort_keys=True)
                    self.assertNotIn('private', public)

    def test_exception_payload_shape_is_never_read_or_formatted(self):
        class PrivateString(str):
            def __eq__(self, other):
                raise AssertionError('private string compared')
            def __str__(self):
                raise AssertionError('private string formatted')
            def __repr__(self):
                raise AssertionError('private string represented')
        errors = (
            PrivateInvalid(),
            PrivateInvalid('one', 'two'),
            PrivateInvalid(b'private'),
            PrivateInvalid({'transcript': 'private'}),
            PrivateInvalid(PrivateString('private')),
        )
        for error in errors:
            self.assertEqual(
                guest.collector_diagnostic_code('controller', error),
                'collector-controller-invalid')

    def test_unknown_stage_or_error_type_fails_closed(self):
        for stage in (None, '', 'private-transcript', 1, [], {}):
            with self.subTest(stage=stage), self.assertRaisesRegex(
                    guest.Invalid, '^unknown-collector-setup-stage$'):
                guest.collector_diagnostic_code(stage, PrivateInvalid('private'))
        with self.assertRaisesRegex(
                guest.Invalid, '^unknown-collector-setup-error-type$'):
            guest.collector_diagnostic_code('controller', RuntimeError('private'))

    def test_constructor_marks_controller_before_loading_installed_code(self):
        error = PrivateInvalid('private installed controller failure')
        old = guest.COLLECTOR_SETUP_STAGE
        try:
            with mock.patch.object(guest, 'installed_controller', side_effect=error):
                with self.assertRaises(PrivateInvalid) as caught:
                    guest.Checker({})
            self.assertIs(caught.exception, error)
            self.assertEqual(guest.COLLECTOR_SETUP_STAGE, 'controller')
            self.assertEqual(
                guest.collector_diagnostic_code(guest.COLLECTOR_SETUP_STAGE, caught.exception),
                'collector-controller-invalid')
        finally:
            guest.COLLECTOR_SETUP_STAGE = old

    def test_stage_marker_accepts_only_the_finite_source_inventory(self):
        old = guest.COLLECTOR_SETUP_STAGE
        try:
            for stage in guest.COLLECTOR_SETUP_STAGES:
                guest.mark_collector_setup(stage)
                self.assertEqual(guest.COLLECTOR_SETUP_STAGE, stage)
            with self.assertRaisesRegex(
                    guest.Invalid, '^unknown-collector-setup-stage$'):
                guest.mark_collector_setup('private-path')
            self.assertEqual(guest.COLLECTOR_SETUP_STAGE, guest.COLLECTOR_SETUP_STAGES[-1])
        finally:
            guest.COLLECTOR_SETUP_STAGE = old


if __name__ == '__main__':
    unittest.main()
