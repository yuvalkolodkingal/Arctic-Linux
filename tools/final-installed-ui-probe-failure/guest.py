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


# BEGIN SOURCE-CLOSED GUEST PREPROBE OBSERVATION
GUEST_OBSERVATION_PREFIX = 'ARCTIC-UI-GUEST-OBSERVATION '
GUEST_OBSERVATION_PHASES = ('context-validated', 'stage-authorization', 'owned-data-cd',
    'native-authorization', 'native-authorized', 'desktop-discovery', 'desktop-prefix', 'probe-acquisition', 'probe-ready')
GUEST_OBSERVATION_GUARDS = ('unknown', 'guest-stage', 'guest-owned-data-cd', 'guest-prefix',
    'native-explicit-authorization', 'native-root-virtualized', 'native-enforcing', 'native-boot-mode',
    'native-discovery-wayland', 'native-discovery-signature', 'native-discovery-path',
    'native-discovery-single', 'native-command-output-bound', 'native-command-exit')
GUEST_FAILED_PHASES = ('stage-authorization', 'owned-data-cd', 'native-authorization',
    'desktop-discovery', 'desktop-prefix', 'probe-acquisition')
GUEST_GUARD_PHASES = dict([
    ('guest-stage', 'stage-authorization'), ('guest-owned-data-cd', 'owned-data-cd'),
    ('guest-prefix', 'desktop-prefix'),
    *[(name, 'native-authorization') for name in ('native-explicit-authorization',
       'native-root-virtualized', 'native-enforcing', 'native-boot-mode',
       'native-command-output-bound', 'native-command-exit')],
    *[(name, 'desktop-discovery') for name in ('native-discovery-wayland',
       'native-discovery-signature', 'native-discovery-path', 'native-discovery-single')]])
GUEST_OBSERVATION_ERRORS = (RuntimeError, TimeoutError, OSError, FileNotFoundError,
    PermissionError, json.JSONDecodeError, KeyError, ValueError, KeyboardInterrupt, SystemExit)


def validate_guest_observation(value):
    require(type(value) is dict and set(value) == {'schema', 'context', 'stage', 'status',
        'phase', 'guard', 'error_class', 'ui_acceptance', 'release_acceptance', 'raw_error_exported'},
        'guest-observation-fields')
    validate_context(value['context'])
    require(value['schema'] == 'arctic-final-ui-guest-preprobe-v1'
        and value['stage'] in ('unknown', 'live', 'installed') and value['status'] in ('observed', 'failed')
        and value['phase'] in GUEST_OBSERVATION_PHASES and value['guard'] in GUEST_OBSERVATION_GUARDS
        and value['error_class'] in {'none', 'OtherError'} | {t.__name__ for t in GUEST_OBSERVATION_ERRORS}
        and value['ui_acceptance'] is False and value['release_acceptance'] is False
        and value['raw_error_exported'] is False, 'guest-observation-values')
    require((value['status'] == 'observed' and value['phase'] in ('context-validated', 'native-authorized', 'probe-ready')
        and value['guard'] == 'unknown' and value['error_class'] == 'none')
        or (value['status'] == 'failed' and value['error_class'] != 'none'), 'guest-observation-role')
    require(value['status'] != 'failed' or value['phase'] in GUEST_FAILED_PHASES,
        'guest-observation-failed-phase')
    require(value['guard'] == 'unknown' or (value['status'] == 'failed'
        and value['error_class'] == 'RuntimeError' and GUEST_GUARD_PHASES[value['guard']] == value['phase']),
        'guest-observation-guard-role')
    require(value['stage'] != 'unknown' or value['phase'] in ('context-validated', 'stage-authorization'),
        'guest-observation-stage-role')
    return value


def guest_guard_label(error, native):
    # Only the loaded source code objects and their exact require frames can label a guard.
    # Exception text/args/repr and arbitrary frame locals are never read.
    if type(error) is not RuntimeError:
        return 'unknown'
    try:
        entries = { _preprobe.__code__: (globals(), require.__code__, globals(), GUEST_PREPROBE_SPANS) }
        trusted_require = native.get('require')
        if callable(trusted_require) and getattr(trusted_require, '__globals__', None) is native:
            for name, spans in NATIVE_PREPROBE_SPANS.items():
                function = native.get(name)
                if callable(function) and getattr(function, '__globals__', None) is native:
                    entries[function.__code__] = (native, trusted_require.__code__, native, spans)
        tb = BaseException.__traceback__.__get__(error, type(error)); seen = 0
        while tb is not None and seen < 64:
            following = tb.tb_next; frame = tb.tb_frame; seen += 1
            entry = entries.get(frame.f_code)
            if entry is not None and frame.f_globals is entry[0] and following is not None:
                nextframe = following.tb_frame
                if nextframe.f_code is entry[1] and nextframe.f_globals is entry[2]:
                    labels = [label for first, last, label in entry[3] if first <= tb.tb_lineno <= last]
                    if len(labels) == 1:
                        return labels[0]
            tb = following
    except BaseException:
        pass
    return 'unknown'


def emit_guest_observation(context, stage, status, phase, guard='unknown', error_class='none'):
    value = dict(schema='arctic-final-ui-guest-preprobe-v1', context=context, stage=stage,
        status=status, phase=phase, guard=guard, error_class=error_class,
        ui_acceptance=False, release_acceptance=False, raw_error_exported=False)
    # An invalid context never reaches the serializer; no reporting failure can change the primary.
    try:
        validate_guest_observation(value)
        print(GUEST_OBSERVATION_PREFIX + json.dumps(value, sort_keys=True), flush=True)
    except BaseException:
        pass


def _preprobe(native, context):
    stage = sys.argv[1] if len(sys.argv) == 2 and sys.argv[1] in ('live', 'installed') else 'unknown'
    phase = 'context-validated'
    emit_guest_observation(context, stage, 'observed', phase)
    try:
        phase = 'stage-authorization'
        require(len(sys.argv) == 2 and sys.argv[1] in ('live', 'installed'), 'stage')
        phase = 'owned-data-cd'
        require(Path(__file__).parent == Path('/run/t')
                and os.geteuid() == 0, 'owned-data-cd')
        phase = 'native-authorization'
        native['guest_guard'](sys.argv[1], True)
        emit_guest_observation(context, stage, 'observed', 'native-authorized')
        if sys.argv[1] == 'live':
            print('ARCTIC-FINAL-UI-LIVE-PRECHECK=PASS', flush=True)
            return None
        phase = 'desktop-discovery'
        prefix = native['discover_desktop']()
        phase = 'desktop-prefix'
        require(prefix[:5] == ['runuser', '-u', 'ci', '--', 'env'] and not any(
                value.startswith(('ARCTIC_UPDATE_STATUS=', 'ARCTIC_WALLPAPER_TEST_BUS=')) for value in prefix),
                'fixture-user-and-production-backends')
        phase = 'probe-acquisition'
        probe = Probe(native, prefix, context)
        emit_guest_observation(context, stage, 'observed', 'probe-ready')
        return probe
    except BaseException as error:
        error_class = type(error).__name__ if type(error) in GUEST_OBSERVATION_ERRORS else 'OtherError'
        emit_guest_observation(context, stage, 'failed', phase, guest_guard_label(error, native), error_class)
        raise
# END SOURCE-CLOSED GUEST PREPROBE OBSERVATION


def main(native, context):
    validate_context(context)
    probe = _preprobe(native, context)
    if probe is None:
        return 0
    status, error_class = 'failed', 'none'
    old_handler = signal.getsignal(signal.SIGALRM)
    def deadline(signum, frame):
        raise TimeoutError('ui-segment-deadline')
    signal.signal(signal.SIGALRM, deadline); signal.alarm(720)
    try:
        probe.execute(); status = 'passed'
    except Exception as error:
        emit_probe_failure(context, probe.phase, 'execute', error)
        error_class = type(error).__name__ if type(error).__name__ in (
            'RuntimeError', 'TimeoutError', 'OSError', 'FileNotFoundError', 'PermissionError',
            'JSONDecodeError', 'KeyError', 'ValueError') else 'OtherError'
    finally:
        signal.alarm(0); signal.signal(signal.SIGALRM, old_handler)
        try:
            try:
                probe.export(status, probe.phase, error_class)
            except BaseException as error:
                emit_probe_failure(context, probe.phase, 'export', error)
                raise
        finally:
            # Only the acquired child receives termination; guest-owned captures
            # remain until the existing normal disposable-VM poweroff.
            if probe.child is not None and probe.child.poll() is None:
                probe.child.terminate()
                try: probe.child.wait(5)
                except subprocess.TimeoutExpired: probe.child.kill(); probe.child.wait(5)
    return int(status != 'passed')

# Exact Source call spans, bound to the loaded code objects above.
GUEST_PREPROBE_SPANS = [(351, 351, 'guest-stage'), (353, 354, 'guest-owned-data-cd'), (364, 366, 'guest-prefix')]
NATIVE_PREPROBE_SPANS = {'guest_guard': [(239, 239, 'native-explicit-authorization'), (240, 241, 'native-root-virtualized'), (242, 242, 'native-enforcing'), (244, 244, 'native-boot-mode')], 'discover_desktop': [(209, 209, 'native-discovery-wayland'), (221, 221, 'native-discovery-signature'), (226, 226, 'native-discovery-path'), (234, 234, 'native-discovery-single')], 'execute': [(58, 58, 'native-command-output-bound'), (60, 62, 'native-command-exit')]}


# BEGIN SOURCE-CLOSED POSTPROBE FAILURE CHANNEL
PROBE_FAILURE_PREFIX = 'ARCTIC-UI-PROBE-FAILURE '
PROBE_FAILURE_ERRORS = (RuntimeError, TimeoutError, OSError, FileNotFoundError,
    PermissionError, json.JSONDecodeError, KeyError, ValueError, KeyboardInterrupt, SystemExit)
# Literal source call spans; no dynamic exception operand is inspected.
PROBE_FAILURE_SITES = (
    ('result', 48, 48, 1, RuntimeError, True),
    ('result', 49, 49, 2, RuntimeError, True),
    ('wait', 59, 59, 3, TimeoutError, False),
    ('object_value', 64, 64, 4, RuntimeError, True),
    ('png', 70, 71, 5, RuntimeError, True),
    ('png', 73, 73, 6, RuntimeError, True),
    ('png', 76, 77, 7, RuntimeError, True),
    ('Probe.capture', 98, 99, 8, RuntimeError, True),
    ('Probe.capture', 100, 100, 9, RuntimeError, True),
    ('Probe.capture', 102, 102, 10, RuntimeError, True),
    ('Probe.check', 108, 108, 11, RuntimeError, True),
    ('Probe.library', 113, 113, 12, RuntimeError, True),
    ('Probe.choose', 117, 117, 13, RuntimeError, True),
    ('Probe.appearance', 133, 134, 14, RuntimeError, True),
    ('Probe.appearance', 136, 136, 15, RuntimeError, True),
    ('Probe.execute', 143, 143, 16, RuntimeError, True),
    ('Probe.execute', 145, 146, 17, RuntimeError, True),
    ('Probe.execute', 148, 149, 18, RuntimeError, True),
    ('Probe.execute', 164, 164, 19, RuntimeError, True),
    ('Probe.execute', 166, 166, 20, RuntimeError, True),
    ('Probe.execute', 169, 169, 21, RuntimeError, True),
    ('Probe.execute', 183, 183, 22, RuntimeError, True),
    ('Probe.execute', 185, 187, 23, RuntimeError, True),
    ('Probe.execute', 205, 205, 24, RuntimeError, True),
    ('Probe.execute', 210, 210, 25, RuntimeError, True),
    ('Probe.execute', 212, 212, 26, RuntimeError, True),
    ('Probe.export', 243, 243, 27, RuntimeError, True),
 )
PROBE_FAILURE_SITE_NAMES = dict((row[3], row[0]) for row in PROBE_FAILURE_SITES)
PROBE_FAILURE_CODE_ROWS = tuple(((getattr(Probe,name.split('.')[1]) if name.startswith('Probe.')
    else globals()[name]).__code__,first,last,ident,kind,needs_require)
    for name,first,last,ident,kind,needs_require in PROBE_FAILURE_SITES)
PROBE_FAILURE_REQUIRE_CODE = require.__code__
PROBE_FAILURE_DEADLINE_CODES = tuple(code for code in main.__code__.co_consts
    if type(code) is type(main.__code__) and code.co_name == 'deadline')



def probe_failure_site(error):
    """Loaded CodeType/globals and exact require frame only; bounded 64 frames."""
    if type(error) not in (RuntimeError, TimeoutError):
        return 0
    try:
        tb = BaseException.__traceback__.__get__(error, type(error)); seen = 0
        while tb is not None and seen < 64:
            frame = tb.tb_frame; following = tb.tb_next; seen += 1
            if frame.f_globals is globals():
                if any(frame.f_code is code for code in PROBE_FAILURE_DEADLINE_CODES) and type(error) is TimeoutError:
                    return 28
                matches = []
                for code,first,last,ident,kind,needs_require in PROBE_FAILURE_CODE_ROWS:
                    if frame.f_code is not code:continue
                    trusted = not needs_require or (following is not None
                        and following.tb_frame.f_code is PROBE_FAILURE_REQUIRE_CODE
                        and following.tb_frame.f_globals is globals())
                    if first <= tb.tb_lineno <= last and type(error) is kind and trusted:
                        matches.append(ident)
                if len(matches) == 1:
                    return matches[0]
            tb = following
    except BaseException:
        pass
    return 0


def validate_probe_failure(value):
    require(type(value) is dict and set(value) == {'schema','context','stage','role',
        'phase','site_id','error_class','source_text_observation_only',
        'authenticated_guest_execution','raw_error_exported','ui_acceptance','release_acceptance'},
        'probe-failure-fields')
    validate_context(value['context'])
    require(value['schema'] == 'arctic-ui-probe-failure-v1' and value['stage'] == 'installed'
        and value['role'] in ('execute','export') and value['phase'] in PHASES | {'unknown'}
        and type(value['site_id']) is int and 0 <= value['site_id'] <= 28
        and value['error_class'] in {'OtherError'} | {kind.__name__ for kind in PROBE_FAILURE_ERRORS}
        and value['source_text_observation_only'] is True
        and value['authenticated_guest_execution'] is False and value['raw_error_exported'] is False
        and value['ui_acceptance'] is False and value['release_acceptance'] is False,
        'probe-failure-values')
    require(value['site_id'] == 0 or (value['error_class'] ==
        ('TimeoutError' if value['site_id'] in (3,28) else 'RuntimeError')),
        'probe-failure-site-class')
    require(value['site_id'] != 28 or value['role'] == 'execute', 'probe-failure-deadline-role')
    return value


def emit_probe_failure(context, phase, role, error):
    """Best-effort finite observation cannot replace any existing failure."""
    try:
        value = dict(schema='arctic-ui-probe-failure-v1',context=context,stage='installed',role=role,
            phase=phase if type(phase) is str and phase in PHASES else 'unknown',
            site_id=probe_failure_site(error),error_class=type(error).__name__
                if type(error) in PROBE_FAILURE_ERRORS else 'OtherError',
            source_text_observation_only=True,authenticated_guest_execution=False,
            raw_error_exported=False,ui_acceptance=False,release_acceptance=False)
        validate_probe_failure(value)
        print(PROBE_FAILURE_PREFIX + json.dumps(value,sort_keys=True),flush=True)
    except BaseException:
        pass
# END SOURCE-CLOSED POSTPROBE FAILURE CHANNEL
