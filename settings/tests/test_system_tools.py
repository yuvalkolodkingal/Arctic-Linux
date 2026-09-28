"""Tests for the power menu's checks (arctic-power), the restarts and the system monitor
(arctic-restart, arctic-sysmon), dimming before the lock (arctic-session idle), Settings' root
helper (packaging/system/arctic-system-helper: firewall, remote login, snapshots) and the
Sharing and snapshot commands that use it.

    python3 -m unittest discover -s settings/tests -v

Everything runs in test_arctic_settings.Home's throwaway home with stand-ins that record their
arguments; the root helper runs as the test user (ARCTIC_SYSTEM_HELPER_TEST=1).
"""
import json
import subprocess
import textwrap
import unittest

from test_arctic_settings import DOTFILES, Home, stub

BIN = DOTFILES / '.local/bin'
SYSTEM_HELPER = DOTFILES.parent / 'packaging/system/arctic-system-helper'
CLIENTS = '[{"id": 12, "appid": "dev.zed.Zed", "title": "main.rs — Zed"}, {"id": 14, "appid": "kitty", "title": "~"}]'


class Tools(Home):
    def setUp(self):
        super().setUp()
        self.env['ARCTIC_POWER_WAIT_STEPS'] = '2'
        stub(self.bin, 'notify-send', 'echo "notify-send $*" >> "{}"\n'.format(self.log))

    def sh(self, *argv, rc=0):
        result = subprocess.run(['bash'] + [str(a) for a in argv], env=self.env, capture_output=True,
                                text=True, timeout=30)
        self.assertEqual(result.returncode, rc, result.stderr)
        return result.stdout


class PowerTest(Tools):
    def mmsg(self, closing=True):
        """mmsg: all-clients from a file; killclient removes the client when `closing`."""
        (self.tmp / 'clients.json').write_text(CLIENTS)
        stub(self.bin, 'mmsg', textwrap.dedent('''\
            echo "mmsg $*" >> "{log}"
            case "$1 $2" in
              "get all-clients") cat "{clients}" ;;
              "dispatch killclient") [ -n "{closing}" ] && echo '[{{"id": 14, "appid": "kitty", "title": "~"}}]' > "{clients}.new" ;;
            esac
            [ -f "{clients}.new" ] && [ "$2" = killclient ] && [ "$3" = client,14 ] && echo '[]' > "{clients}.new"
            [ -f "{clients}.new" ] && [ "$2" = killclient ] && [ "$3" = client,14 ] && mv "{clients}.new" "{clients}"
            exit 0
            ''').format(log=self.log, clients=self.tmp / 'clients.json', closing='yes' if closing else ''))

    def test_prepare_closes_windows(self):
        self.mmsg(closing=True)
        stub(self.bin, 'pgrep', 'exit 1\n')
        data = json.loads(self.sh(BIN / 'arctic-power', 'prepare', 'restart', '--json'))
        self.assertEqual((data['busy'], data['open']), ([], []))
        self.assertIn('mmsg dispatch killclient client,12', self.calls())
        self.assertIn('mmsg dispatch killclient client,14', self.calls())

    def test_prepare_reports_what_stays_open_and_what_installs(self):
        self.mmsg(closing=False)
        stub(self.bin, 'pgrep', 'exit 1\n')
        data = json.loads(self.sh(BIN / 'arctic-power', 'prepare', 'poweroff', '--json'))
        self.assertEqual([w['appid'] for w in data['open']], ['dev.zed.Zed', 'kitty'])
        self.assertEqual(data['open'][0]['title'], 'main.rs — Zed')
        stub(self.bin, 'pgrep', '[ "$2" = dnf5 ] && exit 0; exit 1\n')
        before = len([c for c in self.calls() if 'killclient' in c])
        data = json.loads(self.sh(BIN / 'arctic-power', 'prepare', 'logout', '--json'))
        self.assertEqual(data['busy'], ['dnf5'])
        self.assertEqual(len([c for c in self.calls() if 'killclient' in c]), before)   # nothing closed

    def test_restart_asks_and_can_be_cancelled(self):
        self.mmsg(closing=False)
        stub(self.bin, 'pgrep', 'exit 1\n')
        stub(self.bin, 'systemctl', 'echo "systemctl $*" >> "{}"\n'.format(self.log))
        stub(self.bin, 'fuzzel', 'cat > /dev/null; echo Cancel\n')
        self.sh(BIN / 'arctic-power', 'restart')
        self.assertNotIn('systemctl reboot', self.calls())
        stub(self.bin, 'fuzzel', 'cat > /dev/null; echo "Restart anyway"\n')
        self.sh(BIN / 'arctic-power', 'restart')
        self.assertIn('systemctl reboot', self.calls())
        self.sh(BIN / 'arctic-power', 'poweroff', '--now')
        self.assertIn('systemctl poweroff', self.calls())

    def test_can(self):
        stub(self.bin, 'busctl', '[ "$5" = CanHibernate ] && echo \'s "na"\' || echo \'s "yes"\'\n')
        self.assertEqual(json.loads(self.sh(BIN / 'arctic-power', 'can', '--json')),
                         dict(ok=True, hibernate=False, firmware=True))


class RestartAndMonitorTest(Tools):
    def test_restart(self):
        stub(self.bin, 'systemctl', 'echo "systemctl $*" >> "{}"\n'.format(self.log))
        stub(self.bin, 'nmcli', 'echo "nmcli $*" >> "{}"\n'.format(self.log))
        stub(self.bin, 'sleep', 'exit 0\n')
        for what in ('sound', 'wifi', 'bluetooth'):
            self.assertEqual(json.loads(self.sh(BIN / 'arctic-restart', what, '--json')), dict(ok=True, restarted=what))
        self.assertIn('systemctl --user restart pipewire.service pipewire-pulse.service wireplumber.service', self.calls())
        self.assertIn('nmcli radio wifi on', self.calls())
        self.assertIn('systemctl restart bluetooth.service', self.calls())
        stub(self.bin, 'systemctl', 'exit 1\n')
        self.assertFalse(json.loads(self.sh(BIN / 'arctic-restart', 'sound', '--json', rc=1))['ok'])
        self.sh(BIN / 'arctic-restart', 'kernel', rc=2)
        (self.bin / 'arctic-restart').symlink_to(BIN / 'arctic-restart')
        self.helper('troubleshoot', 'wifi')
        self.helper('troubleshoot', 'everything', ok=False)

    def test_sysmon_picks_a_monitor(self):
        stub(self.bin, 'flatpak', 'exit 1\n')
        stub(self.bin, 'btop', 'exit 0\n')
        self.assertEqual(self.sh(BIN / 'arctic-sysmon', '--which').strip(), 'arctic-open terminal -e btop')
        stub(self.bin, 'gnome-system-monitor', 'exit 0\n')
        self.assertEqual(self.sh(BIN / 'arctic-sysmon', '--which').strip(), 'gnome-system-monitor')
        stub(self.bin, 'flatpak', 'exit 0\n')
        self.assertEqual(self.sh(BIN / 'arctic-sysmon', '--which').strip(), 'flatpak run io.missioncenter.MissionCenter')


class DimTest(Tools):
    def test_dims_before_the_lock(self):
        ran = self.tmp / 'swayidle.log'
        stub(self.bin, 'arctic-is-live', 'exit 1\n')
        stub(self.bin, 'pgrep', 'exit 1\n')
        stub(self.bin, 'swayidle', 'printf "%s^" "$@" >> "{}"; echo >> "{}"\n'.format(ran, ran))
        stub(self.bin, 'setsid', 'shift; exec "$@"\n')
        stub(self.bin, 'brightnessctl', 'exit 0\n')
        subprocess.run(['bash', str(BIN / 'arctic-session'), 'idle'], env=self.env, check=True, timeout=10)
        args = ran.read_text().splitlines()[-1].split('^')
        self.assertEqual(args[:3], ['-w', 'timeout', '270'])
        self.assertIn('brightnessctl -q -s set', args[3])
        self.assertEqual(args[4:6], ['resume', 'brightnessctl -q -r'])
        self.assertEqual(args[6:8], ['timeout', '300'])
        (self.home / '.config/arctic/idle.conf').write_text('lock_after=600\nsuspend_after=0\ndim_before_lock=0\n')
        subprocess.run(['bash', str(BIN / 'arctic-session'), 'idle'], env=self.env, check=True, timeout=10)
        self.assertEqual(ran.read_text().splitlines()[-1], '-w^timeout^600^arctic-lock^before-sleep^arctic-lock^')


FIREWALL = '''\
echo "firewall-cmd $*" >> "{log}"
case "$*" in
  --state) [ -n "$FW_OFF" ] && {{ echo "not running"; exit 252; }}; echo running ;;
  --get-default-zone) echo public ;;
  "--zone=public --list-services") echo "dhcpv6-client ssh mdns" ;;
  "--zone=public --list-ports") echo "53317/tcp 53317/udp" ;;
esac
exit 0
'''


class SystemHelperTest(Home):
    def setUp(self):
        super().setUp()
        self.env.update(ARCTIC_SYSTEM_HELPER_TEST='1', ARCTIC_SYSTEM_HELPER=str(SYSTEM_HELPER),
                        ARCTIC_SSH_KEYS_ONLY=str(self.tmp / 'sshd_config.d/40-arctic-keys-only.conf'),
                        ARCTIC_SNAPPER_ROOT_CONFIG=str(self.tmp / 'snapper-root'), USER='you')
        stub(self.bin, 'firewall-cmd', FIREWALL.format(log=self.log))
        stub(self.bin, 'logger', 'echo "logger $*" >> "{}"\n'.format(self.log))
        stub(self.bin, 'systemctl', textwrap.dedent('''\
            echo "systemctl $*" >> "{}"
            case "$1" in is-enabled) echo enabled ;; is-active) echo active ;; esac
            ''').format(self.log))
        stub(self.bin, 'sshd', '[ -n "$SSHD_BAD" ] && {{ echo "line 3: Bad configuration option" >&2; exit 255; }}; echo "sshd $*" >> "{}"\n'.format(self.log))
        stub(self.bin, 'hostname', 'echo arctic\n')
        stub(self.bin, 'ssh-keygen', 'echo "256 SHA256:abc root@arctic (ED25519)"\n')

    def tool(self, *args, ok=True):
        result = subprocess.run([str(SYSTEM_HELPER)] + list(args), env=self.env, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(data['ok'], ok, data)
        return data

    def test_firewall_allow(self):
        self.assertEqual(self.tool('firewall-allow', 'localsend', 'on')['zone'], 'public')
        calls = self.calls()
        self.assertIn('firewall-cmd --zone=public --add-port=53317/tcp --add-port=53317/udp', calls)
        self.assertIn('firewall-cmd --zone=public --permanent --add-port=53317/tcp --add-port=53317/udp', calls)
        self.tool('firewall-allow', 'kdeconnect', 'off')
        self.assertIn('firewall-cmd --zone=public --permanent --remove-service=kdeconnect', self.calls())
        self.assertTrue(any(c.startswith('logger -t arctic-system-helper') for c in self.calls()))
        self.env['FW_OFF'] = '1'
        self.assertIn('isn’t running', self.tool('firewall-allow', 'mdns', 'on', ok=False)['error'])
        result = subprocess.run([str(SYSTEM_HELPER), 'firewall-allow', 'telnet', 'on'], env=self.env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2)

    def test_ssh(self):
        self.assertEqual(self.tool('ssh', 'on'), dict(ok=True, enabled=True, active=True))
        self.assertIn('systemctl enable --now sshd.service', self.calls())
        keys_only = self.tmp / 'sshd_config.d/40-arctic-keys-only.conf'
        self.tool('ssh-password', 'off')
        self.assertIn('PasswordAuthentication no', keys_only.read_text())
        self.assertIn('systemctl try-reload-or-restart sshd.service', self.calls())
        self.tool('ssh-password', 'on')
        self.assertFalse(keys_only.exists())
        self.env['SSHD_BAD'] = '1'
        self.assertIn('Bad configuration option', self.tool('ssh-password', 'off', ok=False)['error'])
        self.assertFalse(keys_only.exists())      # a config sshd refuses is taken back

    def test_snapshots(self):
        self.assertEqual(self.tool('snapshots')['config'], False)
        (self.tmp / 'snapper-root').write_text('')
        rows = [dict(number=0, type='single', description='current'),
                dict(number=41, type='pre', date='2026-09-20 10:00:00', description='dnf5 upgrade', cleanup='number'),
                dict(number=42, type='post', **{'pre-number': 41}, date='2026-09-20 10:02:00', description=''),
                dict(number=43, type='single', date='2026-09-21 09:00:00', description='Taken in Settings')]
        stub(self.bin, 'snapper', textwrap.dedent('''\
            echo "snapper $*" >> "{}"
            case "$*" in
              *list*) echo '{}' ;;
              *create*) echo 44 ;;
            esac
            ''').format(self.log, json.dumps({'root': rows})))
        data = self.tool('snapshots')
        self.assertEqual(data['pairs'], [dict(pre=41, post=42, date='2026-09-20 10:00:00', description='dnf5 upgrade')])
        self.assertEqual([s['number'] for s in data['singles']], [43])
        self.assertEqual(self.tool('snapshot-create', 'Before tinkering')['number'], 44)
        self.assertIn('snapper --no-dbus -c root create -t single -c number -p -d Before tinkering', self.calls())
        self.assertIn('80 characters', self.tool('snapshot-create', 'x' * 81, ok=False)['error'])
        self.assertIn('no snapshot pair', self.tool('snapshot-undo', '42', '43', ok=False)['error'])

    def test_settings_commands(self):
        stub(self.bin, 'sshd', 'exit 0\n')
        (self.home / '.ssh').mkdir()
        data = self.helper('sharing')
        self.assertEqual(data['firewall']['zone'], 'public')
        self.assertEqual(data['allows'], dict(mdns=True, kdeconnect=False, ssh=True, localsend=True))
        self.assertEqual((data['ssh']['enabled'], data['ssh']['fingerprint'], data['ssh']['authorizedKeys']),
                         (True, 'SHA256:abc', False))
        self.assertEqual(data['mdnsName'], 'arctic.local')
        self.helper('sharing-set', 'ssh', 'on')
        self.assertIn('firewall-cmd --zone=public --permanent --add-service=ssh', self.calls())
        self.helper('sharing-set', 'allow', 'telnet', 'on', ok=False)
        self.assertEqual(self.helper('snapshots')['config'], False)


if __name__ == '__main__':
    unittest.main()
