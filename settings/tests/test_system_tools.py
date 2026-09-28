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

    def supplies(self, on_battery):
        """A laptop's sysfs power supplies: BAT0, a mouse's battery and the charger."""
        root = self.tmp / 'power_supply'
        for name, files in (('BAT0', dict(type='Battery', capacity='80')),
                            ('hidpp_battery_0', dict(type='Battery', scope='Device')),
                            ('AC', dict(type='Mains', online='0' if on_battery else '1'))):
            (root / name).mkdir(parents=True, exist_ok=True)
            for key, value in files.items():
                (root / name / key).write_text(value + '\n')
        self.env['ARCTIC_POWER_SUPPLY'] = str(root)

    def test_battery_times_and_screens_off(self):
        ran = self.tmp / 'swayidle.log'
        stub(self.bin, 'arctic-is-live', 'exit 1\n')
        stub(self.bin, 'pgrep', 'exit 1\n')
        stub(self.bin, 'swayidle', 'printf "%s^" "$@" >> "{}"; echo >> "{}"\n'.format(ran, ran))
        stub(self.bin, 'setsid', 'shift; echo "setsid $*" >> "{}"; case "$1" in */arctic-session) ;; *) exec "$@" ;; esac\n'.format(self.log))
        stub(self.bin, 'arctic-display', 'exit 0\n')
        self.supplies(on_battery=True)
        conf = self.home / '.config/arctic/idle.conf'
        conf.write_text('lock_after=600\nsuspend_after=1800\ndim_before_lock=0\nlock_after_battery=120\n')
        session = ['bash', str(BIN / 'arctic-session'), 'idle']
        subprocess.run(session, env=self.env, check=True, timeout=10)
        self.assertEqual(ran.read_text().splitlines()[-1].split('^')[:-1],
                         ['-w', 'timeout', '120', 'arctic-lock', 'timeout', '180', 'arctic-display screens off',
                          'resume', 'arctic-display screens on', 'timeout', '1800', 'systemctl suspend',
                          'before-sleep', 'arctic-lock'])
        self.assertTrue(any(c.startswith('setsid ') and c.endswith('arctic-session power-watch') for c in self.calls()))
        self.supplies(on_battery=False)
        conf.write_text('lock_after=600\nsuspend_after=0\nscreen_off_after=0\nlock_after_battery=120\n')
        subprocess.run(session, env=self.env, check=True, timeout=10)
        self.assertEqual(ran.read_text().splitlines()[-1].split('^')[1:-1], ['timeout', '600', 'arctic-lock',
                                                                            'before-sleep', 'arctic-lock'])
        # The watcher: one per session; it restarts idle when the source changes.
        stub(self.bin, 'udevadm', 'echo "UDEV  [1.0] change /devices/AC (power_supply)"\n')
        watch = ['bash', str(BIN / 'arctic-session'), 'power-watch']
        before = len(self.calls())
        subprocess.run(watch, env=self.env, check=True, timeout=10)
        self.assertEqual(len(self.calls()), before)                            # still plugged in
        stub(self.bin, 'udevadm', 'echo 0 > "$ARCTIC_POWER_SUPPLY/AC/online"\n'
                                  'echo "UDEV  [2.0] change /devices/AC (power_supply)"\n')
        subprocess.run(watch, env=self.env, check=True, timeout=10)
        self.assertEqual(self.calls()[-1], 'setsid swayidle -w timeout 120 arctic-lock before-sleep arctic-lock')

    def test_settings(self):
        self.supplies(on_battery=True)
        stub(self.bin, 'arctic-session', 'echo "arctic-session $*" >> "{}"\n'.format(self.log))
        stub(self.bin, 'arctic-display', 'exit 0\n')
        data = self.helper('idle-more')
        self.assertEqual((data['battery'], data['onBattery'], data['lockBattery'], data['dim'], data['screenOff']),
                         (True, True, None, True, 60))
        self.helper('idle-set', 600, 1800)
        self.helper('idle-more-set', 'lock-battery', 180)
        self.helper('idle-more-set', 'screen-off', 30)
        self.helper('idle-more-set', 'dim', 'off')
        conf = self.home / '.config/arctic/idle.conf'
        self.assertEqual(conf.read_text().splitlines()[1:], ['lock_after=600', 'suspend_after=1800',
                                                            'lock_after_battery=180', 'screen_off_after=30',
                                                            'dim_before_lock=0'])
        self.helper('idle-set', 300, 900)                  # the plugged-in times keep the rest
        self.assertIn('lock_after_battery=180', conf.read_text())
        self.assertIn('before the screen locks', self.helper('idle-more-set', 'suspend-battery', 120, ok=False)['error'])
        for args in (('screen-off', 45), ('dim', 'maybe'), ('lock-battery', 10), ('colour', 'red')):
            with self.subTest(args):
                self.helper('idle-more-set', *args, ok=False)
        self.helper('idle-more-set', 'lock-battery', 'same')
        self.assertNotIn('lock_after_battery', conf.read_text())
        self.assertIn('arctic-session idle --restart', self.calls())


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


LSBLK_LUKS = {'blockdevices': [{'name': 'nvme0n1', 'type': 'disk', 'children': [
    {'name': 'nvme0n1p1', 'type': 'part', 'fstype': 'vfat', 'mountpoints': ['/boot/efi']},
    {'name': 'nvme0n1p2', 'type': 'part', 'fstype': 'crypto_LUKS', 'uuid': '0f3a4d2e-11aa-4bbb-8ccc-0123456789ab', 'mountpoints': [None],
     'children': [{'name': 'luks-0f3a', 'type': 'crypt', 'fstype': 'btrfs', 'mountpoints': ['/home', '/']}]}]}]}


class UsersTest(Tools):
    def setUp(self):
        super().setUp()
        stub(self.bin, 'lsblk', "echo '{}'\n".format(json.dumps(LSBLK_LUKS)))
        stub(self.bin, 'gdbus', 'echo "gdbus $*" >> "{}"; echo "()"\n'.format(self.log))
        stub(self.bin, 'arctic-open', 'echo "arctic-open $*" >> "{}"\n'.format(self.log))

    def test_status_and_jobs(self):
        stub(self.bin, 'fprintd-list', 'echo "found 1 devices"; echo "Fingerprints for user you on Goodix:"; echo " - #0: right-index-finger"\n')
        stub(self.bin, 'fprintd-enroll', 'exit 0\n')
        data = self.helper('users')
        self.assertEqual(data['luks'], dict(present=True, uuid='0f3a4d2e-11aa-4bbb-8ccc-0123456789ab'))
        self.assertEqual((data['fingerprint']['reader'], data['fingerprint']['fingers']), (True, ['right-index-finger']))
        self.helper('user-run', 'disk')
        self.helper('user-run', 'password')
        for _ in range(50):
            if len([c for c in self.calls() if c.startswith('arctic-open')]) == 2:
                break
            import time
            time.sleep(0.1)
        self.assertIn('arctic-open terminal --hold -e pkexec /usr/sbin/cryptsetup luksChangeKey /dev/disk/by-uuid/0f3a4d2e-11aa-4bbb-8ccc-0123456789ab', self.calls())
        self.assertIn('arctic-open terminal --hold -e passwd', self.calls())
        self.helper('user-run', 'rm', ok=False)

    def test_lock_screen_fingerprint(self):
        pam = self.tmp / 'lib64/security'
        pam.mkdir(parents=True)
        (pam / 'pam_fprintd.so').write_text('')
        self.env['ARCTIC_PAM_LIB'] = str(self.tmp / 'lib64')
        shell_json = self.home / '.config/arctic/shell.json'
        shell_json.parent.mkdir(parents=True, exist_ok=True)
        shell_json.write_text('{"frame": false}\n')
        data = self.helper('users')['fingerprint']
        self.assertEqual((data['lockScreen'], data['pam']), (True, True))
        data = self.helper('user-set', 'lock-fingerprint', 'off')['fingerprint']
        self.assertFalse(data['lockScreen'])
        self.assertEqual(json.loads(shell_json.read_text()), {'frame': False, 'lock_fingerprint': False})
        self.helper('user-set', 'lock-fingerprint', 'maybe', ok=False)
        shell_json.write_text('{"frame": fal')                  # yours, half written: left alone
        self.assertIn('valid JSON', self.helper('user-set', 'lock-fingerprint', 'on', ok=False)['error'])
        self.assertEqual(shell_json.read_text(), '{"frame": fal')
        # The lock screen's PAM service asks pam_fprintd only.
        service = (DOTFILES.parent / 'shell/pam/arctic-lock-fingerprint').read_text()
        self.assertEqual([l for l in service.splitlines() if l and not l.startswith('#')],
                         ['auth required pam_fprintd.so max-tries=3 timeout=30'])

    def test_name(self):
        self.helper('user-set', 'name', 'Yuval K')
        self.assertTrue(any('SetRealName Yuval K' in c for c in self.calls()))
        self.helper('user-set', 'name', 'a:b', ok=False)
        self.helper('user-set', 'name', 'x' * 65, ok=False)

    @unittest.skipUnless(__import__('importlib').util.find_spec('PIL'), 'needs Pillow')
    def test_picture(self):
        from PIL import Image
        pictures = self.home / 'Pictures'
        pictures.mkdir()
        Image.new('RGB', (400, 300), (200, 30, 30)).save(pictures / 'me.jpg')
        stub(self.bin, 'xdg-user-dir', 'echo "{}"\n'.format(pictures))
        self.assertEqual([p['name'] for p in self.helper('user-pictures')['pictures']], ['me.jpg'])
        data = self.helper('user-set', 'picture', str(pictures / 'me.jpg'))
        self.assertTrue(data['picture'].endswith('.face'))
        with Image.open(self.home / '.face') as face:
            self.assertEqual(face.size, (256, 256))
        self.assertTrue(any('SetIconFile ' + str(self.home / '.face') in c for c in self.calls()))
        self.helper('user-set', 'picture', '--remove')
        self.assertFalse((self.home / '.face').exists())
        self.helper('user-set', 'picture', str(self.home / 'nothing.png'), ok=False)


class InputMethodTest(Tools):
    def test_install_and_state(self):
        stub(self.bin, 'rpm', 'for p in "$@"; do case "$p" in fcitx5|fcitx5-mozc) echo "$p" ;; esac; done\n')
        stub(self.bin, 'pgrep', 'exit 1\n')
        stub(self.bin, 'arctic-open', 'echo "arctic-open $*" >> "{}"\n'.format(self.log))
        data = self.helper('im')
        self.assertEqual((data['installed'], data['running']), (True, False))
        self.assertEqual([e['id'] for e in data['engines'] if e['installed']], ['japanese'])
        self.helper('im-run', 'install', 'korean', 'chinese')
        for _ in range(50):
            if self.calls():
                break
            import time
            time.sleep(0.1)
        self.assertEqual(self.calls()[0], 'arctic-open terminal --hold -e pkexec /usr/bin/dnf5 install -y fcitx5 '
                         'fcitx5-gtk fcitx5-qt fcitx5-configtool fcitx5-autostart fcitx5-hangul fcitx5-chinese-addons')
        self.helper('im-run', 'install', 'klingon', ok=False)


def load_helper(name):
    """A dotfiles helper as a module (without writing __pycache__ into dotfiles/.local/bin)."""
    import importlib.machinery
    import importlib.util
    import sys
    loader = importlib.machinery.SourceFileLoader(name.replace('-', '_'), str(BIN / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    old, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = old
    return module


class ScreenSaverTest(Tools):
    def test_cookies(self):
        ss = load_helper('arctic-screensaver')
        cookies = ss.Cookies()
        zoom = cookies.add(':1.20', 'Zoom', 'Video call')
        cookies.add(':1.20', 'Zoom', 'Video call')
        chrome = cookies.add(':1.31', 'Google Chrome' + 'x' * 80, '')
        self.assertEqual(len(cookies.apps()), 2)                     # the same app and reason once
        self.assertEqual(len(cookies.apps()[1]['app']), 64)
        self.assertFalse(cookies.remove(zoom, ':1.31'))               # not yours to let go
        self.assertTrue(cookies.remove(zoom, ':1.20'))
        self.assertEqual(cookies.vanish(':1.20'), 1)
        self.assertEqual(list(cookies.held), [chrome])
        for _ in range(ss.PER_SENDER - 1):
            cookies.add(':1.31', 'Chrome', '')
        with self.assertRaises(ValueError):
            cookies.add(':1.31', 'Chrome', '')

    def test_publish_drives_swayidle(self):
        ss = load_helper('arctic-screensaver')
        stub(self.bin, 'arctic-session', 'echo "arctic-session $*" >> "{}"\n'.format(self.log))
        import os
        old_env = dict(os.environ)
        os.environ.update(PATH=self.env['PATH'], XDG_RUNTIME_DIR=str(self.tmp))
        try:
            cookies = ss.Cookies()
            cookies.add(':1.5', 'Chromium', 'Playing video')
            self.assertTrue(ss.publish(cookies, False))
            self.assertEqual(json.loads((self.tmp / 'arctic/inhibitors.json').read_text())['apps'][0]['app'], 'Chromium')
            cookies.vanish(':1.5')
            self.assertFalse(ss.publish(cookies, True))
            self.assertFalse((self.tmp / 'arctic/inhibitors.json').exists())
        finally:
            os.environ.clear()
            os.environ.update(old_env)
        self.assertEqual(self.calls(), ['arctic-session idle --restart'] * 2)
        # swayidle keeps only "lock before sleep" while an app holds the screen on.
        (self.tmp / 'arctic/inhibitors.json').write_text('{"apps": [{"app": "Zoom", "reason": ""}]}')
        ran = self.tmp / 'swayidle.log'
        stub(self.bin, 'arctic-is-live', 'exit 1\n')
        stub(self.bin, 'pgrep', 'exit 1\n')
        stub(self.bin, 'setsid', 'shift; exec "$@"\n')
        stub(self.bin, 'swayidle', 'echo "$*" >> "{}"\n'.format(ran))
        env = dict(self.env, XDG_RUNTIME_DIR=str(self.tmp))
        subprocess.run(['bash', str(BIN / 'arctic-session'), 'idle'], env=env, check=True, timeout=10)
        self.assertEqual(ran.read_text().strip(), '-w before-sleep arctic-lock')


class GpuAndShareTest(Tools):
    def test_gpu(self):
        stub(self.bin, 'switcherooctl', textwrap.dedent('''\
            echo "Device: 0"
            echo "  Name:        Intel Corporation Raptor Lake-P [Iris Xe Graphics]"
            echo "  Default:     yes"
            echo "  Discrete:    no"
            echo "Device: 1"
            echo "  Name:        NVIDIA Corporation AD107M [GeForce RTX 4060 Max-Q / Mobile]"
            echo "  Default:     no"
            echo "  Discrete:    yes"
            '''))
        apps = self.data_dirs / 'applications'
        (apps / 'steam.desktop').write_text('[Desktop Entry]\nName=Steam\nExec=steam\nPrefersNonDefaultGPU=true\n')
        (apps / 'zed.desktop').write_text('[Desktop Entry]\nName=Zed\nExec=zed\n')
        result = subprocess.run([str(BIN / 'arctic-gpu'), 'status', '--json'], env=self.env, capture_output=True, text=True)
        data = json.loads(result.stdout)
        self.assertEqual((data['hybrid'], data['prefers']), (True, ['steam']))
        self.assertIn('RTX 4060', data['discrete'])
        stub(self.bin, 'switcherooctl', 'echo "Device: 0"; echo "  Name: AMD"; echo "  Default: yes"; echo "  Discrete: no"\n')
        data = json.loads(subprocess.run([str(BIN / 'arctic-gpu'), 'status', '--json'], env=self.env,
                                         capture_output=True, text=True).stdout)
        self.assertEqual((data['hybrid'], data['prefers']), (False, []))

    def test_share(self):
        stub(self.bin, 'flatpak', 'exit 1\n')
        self.assertEqual(json.loads(self.sh(BIN / 'arctic-share', 'status', '--json')),
                         dict(ok=True, localsend=False, kdeconnect=False))
        stub(self.bin, 'arctic-shell-ipc', 'echo "arctic-shell-ipc $*" >> "{}"\n'.format(self.log))
        self.sh(BIN / 'arctic-share', 'open', rc=1)
        self.assertIn('arctic-shell-ipc apps install', self.calls())
        stub(self.bin, 'flatpak', 'echo "flatpak $*" >> "{}"\n'.format(self.log))
        stub(self.bin, 'setsid', 'shift; exec "$@"\n')
        stub(self.bin, 'xdg-user-dir', 'echo "{}"\n'.format(self.tmp / 'Downloads'))
        stub(self.bin, 'wl-paste', 'case "$*" in *list-types*) echo text/plain ;; *) echo "hello" ;; esac\n')
        self.sh(BIN / 'arctic-share', 'clipboard')
        saved = list((self.tmp / 'Downloads').glob('Clipboard *.txt'))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].read_text(), 'hello\n')
        self.assertIn('flatpak run --file-forwarding org.localsend.localsend_app @@ {} @@'.format(saved[0]), self.calls())
        # Files through the document portal, folders as they are; missing ones are left out.
        photo = self.tmp / '-photo.jpg'
        photo.write_text('jpeg')
        self.sh(BIN / 'arctic-share', 'files', str(photo), str(self.tmp / 'Downloads'), str(self.tmp / 'gone.txt'))
        self.assertEqual(self.calls()[-1], 'flatpak run --file-forwarding org.localsend.localsend_app @@ {} @@ {}'.format(
            photo, self.tmp / 'Downloads'))
        self.sh(BIN / 'arctic-share', 'files', str(self.tmp / 'gone.txt'), rc=1)
        # A LocalSend on the PATH (an RPM or a tarball) gets the paths directly.
        stub(self.bin, 'localsend_app', 'echo "localsend_app $*" >> "{}"\n'.format(self.log))
        self.sh(BIN / 'arctic-share', 'files', str(photo))
        self.assertEqual(self.calls()[-1], 'localsend_app {}'.format(photo))
        entry = (DOTFILES.parent / 'packaging/desktop/arctic-sendto-localsend.desktop').read_text()
        self.assertIn('Exec=arctic-share files %F', entry)


if __name__ == '__main__':
    unittest.main()
