"""Privacy and fail-closed controls for performance stage evidence pre-screening."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT/relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load('performance_prescreen_runner', 'tools/performance/run-paired.py')
screen = load('performance_prescreen_screen', 'tools/native-functional/screen-evidence.py')
guest = load('performance_prescreen_guest', 'tools/performance/guest.py')


class PerformanceEvidencePrescreenTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='private-person@example.invalid-')
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)/'work'
        self.out.mkdir()

    def member(self, relative, content):
        path = self.out/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return (relative, path)

    def rejected(self, relative, content):
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(runner.EarlyEvidenceScreeningError) as caught:
            runner.pre_screen_evidence_members(self.out, [self.member(relative, content)], screen)
        return caught.exception, output.getvalue()

    def test_unknown_email_is_rejected_with_only_closed_member_category(self):
        private = b'source-view@unknown-unit.invalid'
        error, output = self.rejected('runs/candidate/3/serial-boot.log', private + b'\n')
        self.assertEqual(error.args, ('Early performance evidence screening rejected',))
        self.assertEqual(error.category, 'performance-candidate-boot-3-serial')
        self.assertEqual(error.screening_failure, 'sensitive_text')
        self.assertIn('external-text-performance-candidate-boot-3-serial-rejection-sensitive-text', output)
        self.assertNotIn(private.decode(), output)
        self.assertNotIn(str(self.out), output)
        self.assertNotIn('private-person', output)

    def test_unknown_unit_shape_has_no_exemption(self):
        error, output = self.rejected('baseline/serial-install.log', b'mystery@unknown.service\n')
        self.assertEqual(error.category, 'performance-baseline-install-serial')
        self.assertEqual(error.screening_failure, 'sensitive_text')
        self.assertNotIn('mystery@unknown.service', output)

    def test_sanitized_unknown_unit_record_passes_early_prescreen_without_raw_text(self):
        private = 'mystery@unknown.service\nprivate.person@example.invalid\n'
        summary = guest.private_diagnostic_summary('systemd-failed-units', private)
        content = ('ARCTIC-PERFORMANCE ' + json.dumps(dict(
            stage='installed', check='system_failed_units', value=summary),
            sort_keys=True) + '\n').encode()
        self.assertNotIn(private.encode(), content)
        member = self.member('runs/candidate/3/serial-boot.log', content)
        runner.pre_screen_evidence_members(self.out, [member], screen)
        self.assertEqual(member[1].read_bytes(), content)

    def test_unknown_private_filename_is_never_emitted(self):
        relative = 'runs/baseline/2/private-person@example.invalid.log'
        error, output = self.rejected(relative, b'another@unknown.invalid\n')
        self.assertEqual(error.category, 'performance-baseline-boot-2-other-text')
        self.assertNotIn('private-person', output)
        self.assertNotIn('another@unknown.invalid', output)
        self.assertNotIn(relative, output)

    def test_cancellation_identity_is_not_replaced(self):
        member = self.member('runs/candidate/1/harness.log', b'public\n')
        class CancellingScreen:
            PERFORMANCE_MEMBER_CATEGORIES = screen.PERFORMANCE_MEMBER_CATEGORIES
            performance_external_member_category = staticmethod(screen.performance_external_member_category)
            @staticmethod
            def screen_external(source, target):
                raise KeyboardInterrupt('private@example.invalid')
        with self.assertRaises(KeyboardInterrupt) as caught:
            runner.pre_screen_evidence_members(self.out, [member], CancellingScreen)
        self.assertEqual(caught.exception.args, ('private@example.invalid',))

    def test_rejected_member_removes_owned_temporary_directories(self):
        before = set(self.out.parent.glob('arctic-paired-prescreen-*'))
        self.rejected('runs/candidate/2/serial-boot.log', b'private@example.invalid\n')
        self.assertEqual(set(self.out.parent.glob('arctic-paired-prescreen-*')), before)

    def test_future_caller_attributes_are_normalized_before_status(self):
        error = runner.EarlyEvidenceScreeningError('private@example.invalid', 'secret/path/value')
        self.assertEqual(runner.normalized_screening_status(error, screen),
                         ('performance-other-text', 'unclassified'))
        error.category = 'performance-candidate-boot-2-serial'
        error.screening_failure = 'sensitive_text'
        self.assertEqual(runner.normalized_screening_status(error, screen),
                         ('performance-candidate-boot-2-serial', 'sensitive_text'))
        self.assertEqual(runner.normalized_screening_status(RuntimeError('private@example.invalid'), screen),
                         ('performance-other-text', 'unclassified'))

    def test_mutated_or_symlinked_scanner_source_has_only_fixed_failure(self):
        root = self.out/'source-root'
        path = root/'tools/native-functional/screen-evidence.py'
        path.parent.mkdir(parents=True)
        path.write_bytes(b'mutated private@example.invalid')
        with patch.object(runner, 'ROOT', root), \
                patch.object(runner.subprocess, 'check_output', return_value=b'reviewed'):
            with self.assertRaises(RuntimeError) as caught:
                runner.load_screen_source()
        self.assertEqual(caught.exception.args, ('Performance evidence scanner differs from Git HEAD',))
        path.unlink()
        reviewed = root/'reviewed-screen-evidence.py'
        reviewed.write_bytes(b'reviewed')
        path.symlink_to(reviewed)
        with patch.object(runner, 'ROOT', root), \
                patch.object(runner.subprocess, 'check_output', return_value=b'reviewed'):
            with self.assertRaises(RuntimeError) as caught:
                runner.load_screen_source()
        self.assertEqual(caught.exception.args, ('Performance evidence scanner differs from Git HEAD',))
        path.unlink()
        path.symlink_to(root/'missing-screen-evidence.py')
        with patch.object(runner, 'ROOT', root):
            with self.assertRaises(RuntimeError) as caught:
                runner.load_screen_source()
        self.assertEqual(caught.exception.args, ('Performance evidence scanner differs from Git HEAD',))
        path.unlink()
        path.symlink_to(path)
        with patch.object(runner, 'ROOT', root):
            with self.assertRaises(RuntimeError) as caught:
                runner.load_screen_source()
        self.assertEqual(caught.exception.args, ('Performance evidence scanner differs from Git HEAD',))
        self.assertEqual(runner.screen_source_failure_status(), ('performance-other-text', 'member_type'))

    def test_valid_member_passes_without_changing_scanner_output(self):
        member = self.member('runs/candidate/1/harness.log', b'bounded public harness\n')
        runner.pre_screen_evidence_members(self.out, [member], screen)
        self.assertEqual(member[1].read_bytes(), b'bounded public harness\n')

    def test_symlink_and_duplicate_are_fixed_member_type_rejections(self):
        outside = Path(self.temp.name)/'outside.log'
        outside.write_text('private@example.invalid\n')
        link = self.out/'runs/candidate/1/harness.log'
        link.parent.mkdir(parents=True)
        link.symlink_to(outside)
        with self.assertRaises(runner.EarlyEvidenceScreeningError) as caught:
            runner.pre_screen_evidence_members(self.out, [(link.relative_to(self.out).as_posix(), link)], screen)
        self.assertEqual((caught.exception.category, caught.exception.screening_failure),
                         ('performance-candidate-boot-1-harness', 'member_type'))
        valid = self.member('status.json', b'{}\n')
        with self.assertRaises(runner.EarlyEvidenceScreeningError) as caught:
            runner.pre_screen_evidence_members(self.out, [valid, valid], screen)
        self.assertEqual((caught.exception.category, caught.exception.screening_failure),
                         ('performance-other-text', 'member_type'))




if __name__ == '__main__':
    unittest.main()
