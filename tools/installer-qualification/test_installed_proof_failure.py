"""Actual runner control flow with synthetic stages; no VM or installed proof claim."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('installed_proof_failure_stage_fixture', HERE / 'test_stage_diagnostics.py')
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)
R = S.R
MISSING = object()


class Controls(unittest.TestCase):
    def exercise(self, *, failed_stage=None, boot=MISSING, active=True):
        """Reuse actual main preparation/cleanup fixture and observe dependent reads."""
        observations = dict(installed_reads=0, uart_stages=[], cleanup_images=[])
        original_main = R.main
        original_read = Path.read_bytes

        def main():
            preserve = R.preserve_host
            uart = R.E.public_uart_receipt
            command = R.subprocess.run

            def preserve_host(vm, target, profile):
                result = preserve(vm, target, profile)
                path = target / 'host-execution.json'
                host = json.loads(path.read_text())
                if active:
                    if boot is MISSING:
                        host.pop('installed_boot', None)
                    else:
                        host['installed_boot'] = boot
                path.write_text(json.dumps(host))
                return result

            def read(path):
                if path.name == 'serial-installed.log':
                    observations['installed_reads'] += 1
                return original_read(path)

            def public_uart(data, installed=False):
                observations['uart_stages'].append(installed)
                return uart(data, installed=installed)

            def host_command(argv, **kwargs):
                if argv[:3] == ['docker', 'image', 'rm']:
                    observations['cleanup_images'].append(argv[-1])
                return command(argv, **kwargs)

            with patch.object(R, 'preserve_host', preserve_host), \
                    patch.object(Path, 'read_bytes', read), \
                    patch.object(R.E, 'public_uart_receipt', public_uart), \
                    patch.object(R.subprocess, 'run', host_command):
                return original_main()

        fixture = S.Controls(methodName='runTest')
        with patch.object(R, 'main', main):
            result = fixture.pipeline(failed_stage=failed_stage, active=active)
        return (*result, observations)

    def test_concrete_harness_failure_with_no_installed_boot_retains_primary_failure_and_live_validation(self):
        status, stdout, state, trace, contract, observed = self.exercise(failed_stage='run-live')
        self.assertEqual(status, 1)
        self.assertEqual(state['status'], 'failed')
        self.assertIs(state['release_acceptance'], False)
        self.assertEqual(len(state['errors']), 1)
        self.assertTrue(state['errors'][0].startswith('harness: ValueError:'))
        self.assertNotIn('KeyError', json.dumps(state))
        self.assertNotIn('key-error', stdout)
        self.assertNotIn('installed_boot', state['host'])
        self.assertEqual(observed['installed_reads'], 0)
        self.assertEqual(observed['uart_stages'], [False])
        self.assertEqual(state['transport']['status'], 'passed')
        self.assertNotIn('required_images', state)
        contract.validate_report.assert_called_once()
        contract.validate_catalog_selection.assert_called_once()
        contract.validate_execution.assert_not_called()
        self.assertEqual(trace, ['provision', 'capture-build', 'run-live'])
        self.assertEqual(len(observed['cleanup_images']), 2)

    def test_failed_harness_does_not_accept_even_when_a_passed_installed_receipt_is_present(self):
        status, _, state, _, contract, observed = self.exercise(
            failed_stage='run-live', boot=dict(status='passed', serial={'status': 'pending'}))
        self.assertEqual(status, 1)
        self.assertEqual(state['status'], 'failed')
        self.assertEqual(observed['installed_reads'], 0)
        self.assertEqual(observed['uart_stages'], [False])
        contract.validate_execution.assert_not_called()
        self.assertEqual(state['host']['installed_boot']['serial'], {'status': 'pending'})

    def test_successful_harness_requires_a_passed_typed_installed_boot_before_private_serial_read(self):
        for boot in (MISSING, None, [], {}, {'status': 'failed'}, {'status': True}, {'status': 1}):
            with self.subTest(boot_type=type(boot).__name__):
                status, stdout, state, _, contract, observed = self.exercise(boot=boot)
                self.assertEqual(status, 1)
                self.assertEqual(state['status'], 'failed')
                self.assertIs(state['release_acceptance'], False)
                self.assertEqual(len(state['errors']), 1)
                self.assertIn('Successful installer harness has no passed installed boot proof', state['errors'][0])
                self.assertNotIn('KeyError', json.dumps(state))
                self.assertNotIn('key-error', stdout)
                self.assertEqual(observed['installed_reads'], 0)
                self.assertEqual(observed['uart_stages'], [False])
                contract.validate_report.assert_called_once()
                contract.validate_execution.assert_not_called()
                self.assertEqual(len(observed['cleanup_images']), 2)

    def test_successful_installed_path_still_projects_private_uart_and_validates_execution(self):
        status, stdout, state, trace, contract, observed = self.exercise(
            boot=dict(status='passed', serial={'status': 'pending'}))
        self.assertEqual(status, 0)
        self.assertEqual(stdout, '')
        self.assertEqual(state['errors'], [])
        self.assertIs(state['release_acceptance'], False)
        self.assertEqual(state['status'],
            'live_installer_active_restoration_completed_and_installed_boot_passed_pending_manual_visual_review')
        self.assertEqual(observed['installed_reads'], 1)
        self.assertEqual(observed['uart_stages'], [False, True])
        self.assertEqual(state['host']['installed_boot']['serial'], {'bytes': 7, 'sha256': '1' * 64})
        contract.validate_report.assert_called_once()
        contract.validate_catalog_selection.assert_called_once()
        contract.validate_execution.assert_called_once()
        media = contract.validate_execution.call_args.args[-1]
        self.assertEqual(media('host/serial-installed.log'), b'synthetic private installed serial')
        self.assertEqual(trace, ['provision', 'capture-build', 'run-live'])
        self.assertEqual(len(observed['cleanup_images']), 2)

    def test_successful_harness_does_not_bypass_execution_validation_failure(self):
        status, stdout, state, _, contract, observed = self.exercise(
            failed_stage='execution-validation', boot=dict(status='passed'))
        self.assertEqual(status, 1)
        self.assertEqual(state['status'], 'failed')
        self.assertIs(state['release_acceptance'], False)
        self.assertIn('installer-execution-validation-value-error', stdout)
        contract.validate_execution.assert_called_once()
        self.assertEqual(observed['installed_reads'], 1)
        self.assertEqual(observed['uart_stages'], [False, True])
        self.assertEqual(len(observed['cleanup_images']), 2)

    def test_harness_failure_does_not_bypass_live_transport_failure(self):
        # Install the mismatch after the existing fixture's mocks are active.
        original_main = R.main

        def main():
            with patch.object(R.E, 'public_uart_receipt', side_effect=lambda *args, **kwargs: (
                    b'public\n', {'bytes': 7, 'sha256': '0' * 64})):
                return original_main()

        with patch.object(R, 'main', main):
            status, _, state, _, contract, observed = self.exercise(failed_stage='run-live')
        self.assertEqual(status, 1)
        self.assertEqual(state['status'], 'failed')
        self.assertEqual(len(state['errors']), 2)
        self.assertIn('live public UART projection receipt differs', state['errors'][1])
        self.assertEqual(observed['installed_reads'], 0)
        self.assertNotIn('transport', state)
        contract.validate_execution.assert_not_called()

    def test_harness_failure_does_not_bypass_live_report_rejection(self):
        original_main = R.main

        def main():
            with patch.object(R.C.validate_report, 'side_effect', RuntimeError('synthetic live report rejected')):
                return original_main()

        with patch.object(R, 'main', main):
            status, _, state, _, contract, observed = self.exercise(failed_stage='run-live')
        self.assertEqual(status, 1)
        self.assertEqual(state['status'], 'failed')
        self.assertEqual(len(state['errors']), 2)
        self.assertIn('synthetic live report rejected', state['errors'][1])
        self.assertEqual(observed['installed_reads'], 0)
        self.assertEqual(observed['uart_stages'], [])
        self.assertNotIn('transport', state)
        contract.validate_report.assert_called_once()
        contract.validate_execution.assert_not_called()


if __name__ == '__main__':
    unittest.main()
