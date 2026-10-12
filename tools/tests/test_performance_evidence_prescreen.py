"""Privacy and fail-closed controls for external paired evidence prescreening."""
import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load('paired_prescreen_runner', ROOT/'tools/performance/run-paired.py')
screen = load('paired_prescreen_scanner', ROOT/'tools/native-functional/screen-evidence.py')


class PairedEvidencePrescreenControls(unittest.TestCase):
    def capture_diagnostic(self, relative, error):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            screen.diagnose_external_member(relative, error)
        return output.getvalue()

    def test_closed_performance_member_categories_never_echo_paths_or_errors(self):
        cases = {
            'candidate-install-harness.log': 'paired-candidate-install-harness',
            'candidate/serial-install.log': 'paired-candidate-install-uart',
            'runs/candidate/3/serial-boot.log': 'paired-candidate-boot-uart',
            'runs/baseline/1/harness.log': 'paired-baseline-boot-harness',
            'runs/candidate/2/private-name.log': 'paired-candidate-boot-other',
        }
        for relative, role in cases.items():
            with self.subTest(relative=relative):
                output = self.capture_diagnostic(
                    relative, RuntimeError('private@example.invalid /private/path'))
                self.assertEqual(output,
                    'ARCTIC-EVIDENCE-DIAGNOSTIC=external-text-' + role
                    + '-rejection-other-error\n')
                self.assertNotIn(relative, output)
                self.assertNotIn('private', output)
        output = self.capture_diagnostic(
            'private@example.invalid/private-name.log',
            RuntimeError('private@example.invalid /private/path'))
        self.assertEqual(output,
            'ARCTIC-EVIDENCE-DIAGNOSTIC=external-text-other-text-rejection-other-error\n')
        self.assertNotIn('private', output)

    def test_unknown_email_still_rejects_before_next_stage_without_payload_leak(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            member = root/'runs/candidate/3/serial-boot.log'
            member.parent.mkdir(parents=True)
            private = 'person.private@example.invalid'
            member.write_text('prefix ' + private + ' suffix\n')
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                with self.assertRaisesRegex(RuntimeError, '^Sensitive text in external evidence$'):
                    runner.prescreen_external_stage(screen, root, (member.parent,))
            observed = output.getvalue()
            self.assertEqual(observed,
                'ARCTIC-EVIDENCE-RULE=source-view-email-shape\n'
                'ARCTIC-EVIDENCE-EMAIL-CANDIDATE=source-view-unknown-unit\n'
                'ARCTIC-EVIDENCE-DIAGNOSTIC=external-text-paired-candidate-boot-uart-'
                'rejection-sensitive-text\n')
            self.assertNotIn(private, observed)
            self.assertNotIn(str(root), observed)
            self.assertNotIn('serial-boot.log', observed)

    def test_prescreen_uses_public_token_rules_without_creating_an_exemption(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            safe = root/'runs/baseline/1/serial-boot.log'
            safe.parent.mkdir(parents=True)
            safe.write_bytes(b'modprobe@configfs.service\n')
            runner.prescreen_external_stage(screen, root, (safe.parent,))
            unsafe = root/'runs/baseline/1/harness.log'
            unsafe.write_bytes(b'other@unknown.invalid\n')
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                with self.assertRaises(RuntimeError):
                    runner.prescreen_external_stage(screen, root, (safe.parent,))
            self.assertIn('source-view-unknown-unit', output.getvalue())
            self.assertNotIn('other@unknown.invalid', output.getvalue())

    def test_symlinks_and_escaped_members_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            outside = root.parent/'private-external-prescreen.txt'
            outside.write_text('safe\n')
            link = root/'candidate/serial-install.log'
            link.parent.mkdir(parents=True)
            link.symlink_to(outside)
            with self.assertRaisesRegex(RuntimeError, '^Diagnostic symlinks are forbidden$'):
                runner.prescreen_external_stage(screen, root, (link.parent,))
            with self.assertRaisesRegex(RuntimeError, 'escaped owned root'):
                runner.prescreen_external_stage(screen, root, (outside,))
            outside.unlink()


if __name__ == '__main__':
    unittest.main()
