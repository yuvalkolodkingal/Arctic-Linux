"""Source and host controls for the installed-only renderer diagnostic matrix."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import pwd
import hashlib
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('installed_renderer_matrix_tested',HERE/'native_smoke.py')
N=importlib.util.module_from_spec(spec);spec.loader.exec_module(N)


class InstalledRendererMatrixControls(unittest.TestCase):
    def test_launch_requests_each_explicit_lowercase_renderer_on_owned_pipe(self):
        for mode in ('gl','ngl','cairo','vulkan'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as t:
                parent=Mock(root=Path(t),user=pwd.getpwuid(os.getuid()),uid=os.getuid(),stage='installed',
                            prefix=['synthetic-prefix'],original_prefix=['synthetic-prefix'])
                trial=N.InstalledRendererTrialSmoke(parent,mode);drain=Mock()
                with patch.object(N,'NativeProtocolDrain',return_value=drain), \
                     patch.object(N.subprocess,'Popen',return_value=Mock()) as popen:
                    trial.launch_renderer(['/usr/bin/celluloid','--no-existing-session','fixture.mkv'])
                argv=popen.call_args.args[0]
                self.assertEqual(argv[:6],['synthetic-prefix','env','-u','GSK_RENDERER',
                                           'GSK_DEBUG=renderer','WAYLAND_DEBUG=client'])
                self.assertEqual(argv[6],'GSK_RENDERER='+mode)
                self.assertEqual(sum(x.startswith('GSK_RENDERER=') for x in argv),1)
                self.assertIs(popen.call_args.kwargs['stdout'],subprocess.DEVNULL)
                self.assertIs(type(popen.call_args.kwargs['stderr']),int)
                drain.start.assert_called_once();drain.start.call_args.args[0].close()

    def test_observe_reports_supported_aliases_without_changing_oracle(self):
        cases=(('gl','gl',True),('ngl','gl',True),('cairo','cairo',True),
               ('vulkan','vulkan',True),('vulkan','gl',False))
        for mode,realized,supported in cases:
            with self.subTest(mode=mode,realized=realized),tempfile.TemporaryDirectory() as t:
                parent=Mock(root=Path(t),user=pwd.getpwuid(os.getuid()),uid=os.getuid(),stage='installed',
                            prefix=[],original_prefix=[])
                trial=N.InstalledRendererTrialSmoke(parent,mode)
                inherited=dict(intervention=mode,status='observed',oracle=dict(status='matched'),
                    realized_renderer=dict(status='reported-realized',renderer=realized),release_acceptance=False)
                with patch.object(N.RendererTrialSmoke,'observe',return_value=copy.deepcopy(inherited)):
                    value=trial.observe(Path(t)/'fixture',Path(t)/'expected','a'*64)
                self.assertEqual(value['oracle'],inherited['oracle'])
                self.assertEqual(value['requested_gsk_renderer'],mode)
                self.assertEqual(value['expected_realized_renderer'],
                    {'gl':'gl','ngl':'gl','cairo':'cairo','vulkan':'vulkan'}[mode])
                self.assertEqual(value['requested_renderer_matched'],supported)
                self.assertEqual(value['support_status'],
                    'supported-and-realized' if supported else 'not-proven-supported')
                self.assertEqual(value['status'],'observed' if supported else 'unknown')
                self.assertEqual(value['capture_attempt_limit'],1)
                self.assertFalse(value['release_acceptance'])

    def test_matrix_runs_all_four_fresh_trials_and_cannot_rewrite_primary_failure(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);fixture=root/'fixture';fixture.write_bytes(b'fixed')
            expected=root/'expected';expected.write_bytes(b'rgb')
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=root;smoke.uid=os.getuid();smoke.stage='installed'
            smoke.owned=[dict(executable='/usr/bin/celluloid') for _ in range(6)]
            smoke.launches=[];smoke.finish_native_protocol=Mock()
            smoke.gates=[dict(check='open-codec-content-and-player-state',status='failed')]
            primary=dict(oracle=dict(status='unmatched'),screenshot=dict(sha256='a'*64),
                fixture_sha256=N.digest(fixture),expected_rgb_sha256=N.digest(expected))
            modes=('gl','ngl','cairo','vulkan');before=copy.deepcopy(smoke.gates)
            trials=[Mock(owned=[],launches=[],observe=Mock(return_value=dict(
                intervention=mode,status='observed',oracle=dict(status='matched'),release_acceptance=False)))
                for mode in modes]
            with patch.object(N,'InstalledRendererTrialSmoke',side_effect=trials), \
                 patch.object(N,'retire_renderer_player') as retire:
                smoke.installed_renderer_matrix(fixture,expected,'b'*64,primary)
            receipt=json.loads((root/'0-controlled-renderer-trials.json').read_bytes())
            self.assertEqual(receipt['schema'],'arctic-native-installed-renderer-matrix-v1')
            self.assertEqual([row['intervention'] for row in receipt['trials']],list(modes))
            self.assertEqual(smoke.gates,before);self.assertEqual(primary['oracle']['status'],'unmatched')
            self.assertTrue(receipt['primary_failure_preserved']);self.assertFalse(receipt['release_acceptance'])
            self.assertEqual(receipt['controls']['capture_attempts_per_mode'],1)
            self.assertEqual(retire.call_count,6)

    def test_matrix_rejects_live_stage_or_wrong_exact_inventory_before_trials(self):
        for stage,count in (('live',6),('installed',5),('installed',7)):
            with self.subTest(stage=stage,count=count),tempfile.TemporaryDirectory() as t:
                root=Path(t);fixture=root/'fixture';fixture.write_bytes(b'f');expected=root/'expected';expected.write_bytes(b'e')
                smoke=N.Smoke.__new__(N.Smoke);smoke.root=root;smoke.uid=os.getuid();smoke.stage=stage
                smoke.owned=[dict(executable='/usr/bin/celluloid') for _ in range(count)]
                smoke.launches=[];smoke.finish_native_protocol=Mock()
                primary=dict(oracle=dict(status='unmatched'),screenshot=dict(sha256='a'*64),
                    fixture_sha256=N.digest(fixture),expected_rgb_sha256=N.digest(expected))
                with patch.object(N,'InstalledRendererTrialSmoke') as trial,patch.object(N,'retire_renderer_player'):
                    smoke.installed_renderer_matrix(fixture,expected,'b'*64,primary)
                receipt=json.loads((root/'0-controlled-renderer-trials.json').read_bytes())
                self.assertEqual(receipt['preparation_error'],'guard-error');trial.assert_not_called()
                self.assertTrue(all(row['status']=='unrun' for row in receipt['trials']))

    def test_matrix_inverse_restores_exact_preparation_parent(self):
        from test_controls_state_trials import restore_installed_renderer_matrix
        current=(HERE/'native_smoke.py').read_text()
        restored=restore_installed_renderer_matrix(current)
        self.assertNotIn('INSTALLED_RENDERER_MATRIX',restored)
        self.assertNotIn('installed_renderer_matrix(',restored)
        self.assertNotIn('InstalledRendererTrialSmoke',restored)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),
                         'e943557259ef12d8d463ad49523bc756d2d1102ffb7344ce6cdea144e7f3e151')


if __name__=='__main__':unittest.main()
