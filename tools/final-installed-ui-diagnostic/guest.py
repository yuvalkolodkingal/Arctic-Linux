#!/usr/bin/env python3
"""Bounded installed production UI checks; compose with the pinned desktop helpers."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time
import zlib

PNG_NAMES = ('01-appearance.png', '02-picker-winner.png', '03-winner-applied.png',
             '04-custom-selected.png', '05-custom-after-mode.png', '06-custom-appearance.png',
             '07-launcher-remove.png', '08-remove-page.png', '09-get-apps.png',
             '10-update-popover.png', '11-lock-initial.png', '12-lock-next-minute.png',
             '13-after-authentication.png', '14-restored.png')
MAX_PNG = 8 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024
WINNER = 'Ember Clouds, City Silhouette'
WINNER_SHA = '7af8cb5ce0d87773109d759afdd1d14ef22ce7e84fdc1533da1539083cd11b0b'
PHASES = {'appearance', 'winner', 'custom', 'remove-apps', 'updates', 'lock', 'restore', 'complete'}


def validate_context(context):
    require(type(context) is dict and set(context) == {'schema', 'nonce', 'execution_sha', 'source_sha',
            'iso_sha256', 'native_sha256', 'ui_sha256'}, 'context-fields')
    require(context['schema'] == 'arctic-final-installed-ui-context-v1'
            and context['source_sha'] == '326690f173d4dc4f049f43e046c8380e66825a07'
            and context['iso_sha256'] == '807eaaa64ab8480ec2b18bc8434fd5e37d82c41b73a3e0a6f002c35d152ba54c'
            and type(context['execution_sha']) is str and re.fullmatch('[0-9a-f]{40}', context['execution_sha'])
            and type(context['nonce']) is str and re.fullmatch('[0-9a-f]{32}', context['nonce'])
            and all(type(context[k]) is str and re.fullmatch('[0-9a-f]{64}', context[k])
                    for k in ('native_sha256', 'ui_sha256')), 'context-binding')
    return context


def require(value, role):
    if not value:
        raise RuntimeError(role)


def result(command, timeout=45):
    value = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
    require(len(value.stdout) <= 4 * 1024 * 1024 and len(value.stderr) <= 256 * 1024, 'command-bound')
    require(value.returncode == 0, 'command-exit')
    return value.stdout.decode('utf-8').strip()


def wait(predicate, seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.25)
    raise TimeoutError('condition-deadline')


def object_value(raw):
    value = json.loads(raw)
    require(type(value) is dict, 'object-type')
    return value


def png(path):
    value = path.lstat()
    require(stat.S_ISREG(value.st_mode) and not path.is_symlink() and 0 < value.st_size <= MAX_PNG,
            'capture-file')
    data = path.read_bytes()
    require(data.startswith(b'\x89PNG\r\n\x1a\n'), 'capture-format')
    from PIL import Image
    with Image.open(path) as image:
        require(image.format == 'PNG' and 640 <= image.width <= 3840 and 480 <= image.height <= 2160,
                'capture-geometry')
        image.verify()
    return data


class Probe:
    def __init__(self, native, prefix, context):
        self.native, self.prefix, self.context = native, prefix, context
        self.root = Path('/tmp') / ('arctic-final-ui-' + context['nonce'])
        self.root.mkdir(mode=0o700)
        os.chown(self.root, 1000, 1000)
        self.root_identity = (self.root.stat().st_dev, self.root.stat().st_ino)
        self.captures, self.checks = [], []
        self.shell = prefix + ['arctic-shell-ipc']
        self.settings = prefix + ['quickshell', 'ipc', '-p', '/usr/share/arctic/settings', 'call', 'settings']
        self.wall = prefix + ['python3', '/usr/share/arctic/shell/scripts/wallpapers.py']
        self.apps = prefix + ['python3', '/usr/share/arctic/shell/scripts/apps.py']
        self.child = None
        self.phase = 'appearance'

    def capture(self, name):
        require(name in PNG_NAMES and name not in [p.name for p in self.captures]
                and len(self.captures) < 16, 'capture-inventory')
        require(result(['getenforce']) == 'Enforcing', 'capture-enforcing')
        path = self.root / name
        require(not path.exists() and not path.is_symlink(),'capture-path-new')
        result(self.prefix + ['grim', str(path)])
        png(path)
        self.captures.append(path)

    def check(self, name, values):
        require(type(name) is str and name not in [v['check'] for v in self.checks], 'check-identity')
        self.checks.append(dict(check=name, **values))

    def library(self):
        value = object_value(result(self.wall + ['list']))
        require(type(value.get('items')) is list and 19 <= len(value['items']) <= 64, 'wallpaper-list')
        return value

    def choose(self, name, key, capture_name):
        require(type(name) is str and type(key) is str and 0 < len(name) <= 100, 'choice-identity')
        result(self.shell + ['wallpapers', 'open'])
        time.sleep(1)
        # The shipped picker focuses its search field; Enter invokes its real use() control.
        result(self.prefix + ['wtype', '-M', 'ctrl', '-k', 'a', '-m', 'ctrl', name])
        time.sleep(.5)
        self.capture(capture_name)
        result(self.prefix + ['wtype', '-k', 'Return'])
        wait(lambda: self.library()['current'] == key)
        result(self.prefix + ['wtype', '-k', 'Escape'])

    def appearance(self):
        if self.child is None:
            self.child = subprocess.Popen(self.prefix + ['arctic-settings'], stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL)
        wait(lambda: result(self.settings + ['ready']).lower() == 'true')
        require(result(self.settings + ['reveal', 'appearance', 'appearance.wallpaper']) == 'ok',
                'appearance-route')
        wait(lambda: result(self.settings + ['ready']).lower() == 'true')
        require(result(self.settings + ['page']) == 'appearance', 'appearance-page')
        time.sleep(1)

    def execute(self):
        self.appearance(); self.capture('01-appearance.png')
        original = self.library()
        photos = [v for v in original['items'] if v.get('arctic') is True and v.get('photographer')]
        require(len(photos) == 19, 'photo-count')
        winner = [v for v in photos if v.get('name') == WINNER]
        require(len(winner) == 1 and hashlib.sha256(Path(winner[0]['path']).read_bytes()).hexdigest() == WINNER_SHA,
                'winner-source')
        original_mode = object_value(result(self.prefix + ['arctic-theme', 'current', '--json']))
        require(original_mode.get('auto_colors') is True and original_mode.get('mode') in ('dark','light')
                and original_mode.get('wallpaper_mode') in ('auto','dark','light'),'fresh-theme-fixture')
        original_key = original['current']
        try:
            self.phase = 'winner'
            self.choose(WINNER, winner[0]['key'], '02-picker-winner.png')
            result(self.settings + ['open', 'about']); self.appearance()
            self.capture('03-winner-applied.png')
            self.check('winner-keyboard-ui-selection', dict(status='passed', master_sha256=WINNER_SHA,
                                                           catalog_photos=19))
            self.phase = 'custom'
            from PIL import Image
            custom = self.root / 'Arctic UI Custom.png'
            Image.new('RGB', (1600, 900), '#2468ad').save(custom)
            os.chown(custom, 1000, 1000)
            imported = object_value(result(self.wall + ['import', str(custom)]))
            require(imported.get('ok') is True, 'custom-import')
            items = [v for v in self.library()['items'] if v.get('name') == 'Arctic UI Custom']
            require(len(items) == 1 and items[0].get('arctic') is False, 'custom-library')
            self.choose('Arctic UI Custom', items[0]['key'], '04-custom-selected.png')
            result(self.prefix + ['arctic-theme', 'light' if original_mode.get('mode') == 'dark' else 'dark'])
            require(self.library()['current'] == items[0]['key'], 'custom-mode-persistence')
            self.capture('05-custom-after-mode.png')
            result(self.settings + ['open', 'about']); self.appearance()
            self.capture('06-custom-appearance.png')
            self.check('custom-choice-survives-mode-change', dict(status='passed'))
            self.phase = 'remove-apps'
            result(self.shell + ['launcher', 'search', 'Remove apps']); time.sleep(1)
            self.capture('07-launcher-remove.png')
            result(self.prefix + ['wtype', '-k', 'Return']); time.sleep(2)
            self.capture('08-remove-page.png')
            result(self.shell + ['apps', 'install']); time.sleep(1)
            self.capture('09-get-apps.png'); result(self.shell + ['launcher', 'close'])
            # Read-only production preview; it cannot commit a transaction.
            protected = object_value(result(self.apps + ['preview-remove', 'dnf', 'arctic-desktop']))
            require(protected.get('blocked', {}).get('code') == 'protected', 'protected-core')
            preview = object_value(result(self.apps + ['preview-remove', 'dnf', '--no-autoremove', 'xarchiver'], 90))
            require(preview.get('source') == 'dnf' and preview.get('request') == ['xarchiver']
                    and type(preview.get('packages')) is list and preview.get('blocked') is None,
                    'read-only-preview')
            self.check('remove-apps-routing-and-read-only-preview', dict(status='passed',
                       preview_packages=len(preview['packages']), transaction_committed=False,
                       original_ui_review_required=True))
            self.phase = 'updates'
            # Genuine backend state only; no ARCTIC_UPDATE_STATUS override or fake ready file.
            status_path = Path('/var/lib/arctic/update-status.json')
            status = object_value(status_path.read_text()) if status_path.is_file() else {}
            linked = Path('/system-update').is_symlink()
            ready = status.get('state') == 'ready' and status.get('armed') is True and type(status.get('packages')) is int \
                    and status['packages'] > 0 and linked
            result(self.shell + ['updates', 'refresh']); result(self.shell + ['updates', 'toggle']); time.sleep(1)
            self.capture('10-update-popover.png'); result(self.shell + ['updates', 'toggle'])
            self.check('genuine-update-indicator-observation', dict(status='observed', ready=ready,
                       staged_packages=status.get('packages', 0) if type(status.get('packages', 0)) is int else 0,
                       signed_stage_and_cleared_reboot_proven=False))
            self.phase = 'lock'
            locked = lambda: result(self.shell + ['lock', 'isLocked']).lower() == 'true'
            require(not locked(), 'initial-unlocked')
            result(self.shell + ['lock', 'lock']); wait(locked, 60)
            before = time.time(); expected_before = time.strftime('%H:%M', time.localtime(before))
            self.capture('11-lock-initial.png')
            time.sleep(65)
            require(locked(), 'secure-lock-persists')
            expected_after = time.strftime('%H:%M', time.localtime())
            require(expected_before != expected_after, 'minute-rollover')
            self.capture('12-lock-next-minute.png')
            print('ARCTIC-DESKTOP-UNLOCK-REQUESTED', flush=True)
            wait(lambda: not locked(), 180)
            self.capture('13-after-authentication.png')
            self.check('production-lock-clock-and-pam', dict(status='passed', secure=True,
                       expected_clock_before=expected_before, expected_clock_after=expected_after,
                       original_clock_visual_review_required=True, authenticated_by_existing_host_fixture=True))
        except BaseException:
            # Attempt both restorations; neither can replace the original failure.
            for command in (self.wall + ['apply', original_key], self.prefix +
                            ['arctic-theme', 'mode', original_mode['wallpaper_mode']]):
                try: result(command)
                except BaseException: pass
            raise
        self.phase = 'restore'
        errors = []
        for command in (self.wall + ['apply', original_key], self.prefix +
                        ['arctic-theme', 'mode', original_mode['wallpaper_mode']]):
            try: result(command)
            except BaseException as error: errors.append(error)
        if errors: raise errors[0]
        self.capture('14-restored.png')
        self.phase = 'complete'

    def export(self, status, phase, error_class):
        report = dict(schema='arctic-final-installed-ui-report-v1', context=self.context, status=status,
                      phase=phase, error_class=error_class, checks=self.checks, selinux=result(['getenforce']),
                      visual_review_required=True, release_acceptance=False)
        records = [('report.json', (json.dumps(report, sort_keys=True) + '\n').encode())]
        records += [(path.name, png(path)) for path in self.captures]
        require(len(records) <= 17 and sum(len(b) for _, b in records) <= MAX_TOTAL, 'export-total')
        print('ARCTIC-FINAL-UI-BEGIN ' + json.dumps(self.context, sort_keys=True), flush=True)
        manifest = []
        for name, data in records:
            compressed = zlib.compress(data, 6)
            chunks = [compressed[i:i+32768] for i in range(0, len(compressed), 32768)]
            manifest.append(dict(name=name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                                 compressed_bytes=len(compressed), chunks=len(chunks)))
            for index, chunk in enumerate(chunks):
                print('ARCTIC-FINAL-UI-CHUNK ' + json.dumps(dict(name=name, index=index,
                      data=base64.b64encode(chunk).decode()), sort_keys=True), flush=True)
        print('ARCTIC-FINAL-UI-MANIFEST ' + json.dumps(manifest, sort_keys=True), flush=True)
        print('ARCTIC-FINAL-UI-END ' + json.dumps(self.context, sort_keys=True), flush=True)


def main(native, context):
    validate_context(context)
    require(len(sys.argv) == 2 and sys.argv[1] in ('live', 'installed'), 'stage')
    require(Path(__file__).parent == Path('/data' if sys.argv[1] == 'live' else '/run/t')
            and os.geteuid() == 0, 'owned-data-cd')
    native['guest_guard'](sys.argv[1], True)
    if sys.argv[1] == 'live':
        print('ARCTIC-FINAL-UI-LIVE-PRECHECK=PASS', flush=True)
        return 0
    prefix = native['discover_desktop']()
    require(prefix[:5] == ['runuser', '-u', 'ci', '--', 'env'] and not any(
            value.startswith(('ARCTIC_UPDATE_STATUS=', 'ARCTIC_WALLPAPER_TEST_BUS=')) for value in prefix),
            'fixture-user-and-production-backends')
    probe = Probe(native, prefix, context)
    status, error_class = 'failed', 'none'
    old_handler = signal.getsignal(signal.SIGALRM)
    def deadline(signum, frame):
        raise TimeoutError('ui-segment-deadline')
    signal.signal(signal.SIGALRM, deadline); signal.alarm(720)
    try:
        probe.execute(); status = 'passed'
    except Exception as error:
        error_class = type(error).__name__ if type(error).__name__ in (
            'RuntimeError', 'TimeoutError', 'OSError', 'FileNotFoundError', 'PermissionError',
            'JSONDecodeError', 'KeyError', 'ValueError') else 'OtherError'
    finally:
        signal.alarm(0); signal.signal(signal.SIGALRM, old_handler)
        try:
            probe.export(status, probe.phase, error_class)
        finally:
            # Only the acquired child receives termination; guest-owned captures
            # remain until the existing normal disposable-VM poweroff.
            if probe.child is not None and probe.child.poll() is None:
                probe.child.terminate()
                try: probe.child.wait(5)
                except subprocess.TimeoutExpired: probe.child.kill(); probe.child.wait(5)
    return int(status != 'passed')
