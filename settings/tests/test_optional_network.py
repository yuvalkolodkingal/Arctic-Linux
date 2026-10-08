import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import optional_network as N


class OptionalNetworkTests(unittest.TestCase):
    def service(self, running=False):
        return dict(installed=True, running=running, invocation='a'*32, state='active' if running else 'inactive')

    def test_discovery_never_mutates_services_or_routes(self):
        with patch.object(N, 'run', return_value=(1,'','')) as run, patch.object(N,'socks',return_value=False), patch('shutil.which',return_value=None):
            data=N.status()
            self.assertFalse(data['tor']['installed'])
            self.assertIsNone(data['tor']['bootstrap'])
            for call in run.call_args_list:
                self.assertFalse(set(call.args[0]) & {'start','stop','enable','install','up','down','pkexec'})

    def test_existing_socks_or_tor_process_blocks_duplicate_start(self):
        with patch.object(N,'service',return_value=self.service()), patch.object(N,'run',return_value=(1,'','')), patch.object(N,'socks',return_value=True), patch('shutil.which',return_value=None):
            result=N.tor_status()
            self.assertFalse(result['can_start'])
            self.assertFalse(result['endpoints'][0]['tor_verified'])
            self.assertIsNone(result['bootstrap'])
            with self.assertRaises(ValueError): N.action(['tor','start'])
        with patch.object(N,'service',return_value=self.service()), patch.object(N,'run',return_value=(0,'','')), patch.object(N,'socks',return_value=False), patch('shutil.which',return_value=None):
            self.assertFalse(N.tor_status()['can_start'])

    def test_bootstrap_only_from_current_service_invocation(self):
        def run(argv, **kw):
            return (0,'Bootstrapped 10%\nBootstrapped 100%\n','') if argv[0]=='journalctl' else (1,'','')
        with patch.object(N,'service',return_value=self.service(True)), patch.object(N,'run',side_effect=run) as calls, patch.object(N,'socks',return_value=False), patch('shutil.which',return_value=None):
            self.assertEqual(N.tor_status()['bootstrap'],100)
            journal=next(c.args[0] for c in calls.call_args_list if c.args[0][0]=='journalctl')
            self.assertIn('_SYSTEMD_INVOCATION_ID='+'a'*32,journal)

    def test_install_and_connect_are_separate_explicit_plans(self):
        self.assertEqual(N.action(['tailscale','install']),['pkexec','/usr/bin/dnf5','install','tailscale'])
        self.assertEqual(N.action(['tailscale','login']),['pkexec','/usr/bin/tailscale','up'])
        self.assertNotIn('--exit-node',N.action(['tailscale','login']))
        self.assertNotIn('--auth-key',N.action(['tailscale','login']))
        for args in [['evil','install'],['tor','enable'],['tor','install','extra'],['tailscale','exit-node']]:
            with self.assertRaises(ValueError): N.action(args)
