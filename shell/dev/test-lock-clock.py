#!/usr/bin/env python3
"""Exercise LockScreen's clock in a private headless compositor; never use the desktop.

Requires quickshell, dbus-daemon and sway (or mango). Runs in about 75 seconds,
including a real minute rollover. No Arctic services, bar or PAM context are loaded.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time
from zoneinfo import ZoneInfo


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def run(source, compositor):
    qml = source.read_text()
    clock = re.search(r'SystemClock\s*\{[^{}]*\bid:\s*clock\b[^{}]*\}', qml).group()
    formats = re.findall(r"Qt\.formatDateTime\(clock\.date, ('[^']*')\)", qml)
    check(len(formats) == 2, 'Expected the production time and date formats')
    # Also probe the same binding with second precision, for fast relock/resume checks.
    ticks = clock.replace('id: clock', 'id: ticks').replace('SystemClock.Minutes', 'SystemClock.Seconds')
    harness = '''import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
ShellRoot {
    id: root
    property bool showing: false
    CLOCK
    TICKS
    WlSessionLock { id: lock; WlSessionLockSurface { color: "#101010" } }
    IpcHandler {
        target: "clockTest"
        function engage(): void { lock.locked = true; root.showing = true; }
        function release(): void { lock.locked = false; root.showing = false; }
        function sample(): string {
            return JSON.stringify({ enabled: clock.enabled, locked: lock.locked, secure: lock.secure,
                epoch: clock.date.getTime(), tick: ticks.date.getTime(), now: Date.now(),
                time: Qt.formatDateTime(clock.date, TIME_FORMAT),
                day: Qt.formatDateTime(clock.date, DATE_FORMAT) });
        }
        function format(iso: string): string { return Qt.formatDateTime(new Date(iso), TIME_FORMAT); }
    }
}'''.replace('CLOCK', clock).replace('TICKS', ticks).replace('TIME_FORMAT', formats[0]).replace('DATE_FORMAT', formats[1])

    with tempfile.TemporaryDirectory(prefix='arctic-lock-clock-') as temporary:
        base = Path(temporary)
        runtime = base / 'runtime'
        runtime.mkdir(mode=0o700)
        env = dict(os.environ, XDG_RUNTIME_DIR=str(runtime), XDG_CONFIG_HOME=str(base / 'config'),
                   XDG_CACHE_HOME=str(base / 'cache'), XDG_STATE_HOME=str(base / 'state'),
                   WLR_BACKENDS='headless', WLR_RENDERER='pixman', WLR_LIBINPUT_NO_DEVICES='1',
                   QT_QPA_PLATFORM='wayland', QT_QUICK_BACKEND='software',
                   QT_QPA_PLATFORMTHEME='generic', QT_NO_XDG_DESKTOP_PORTAL='1',
                   LANG='en_US.UTF-8', LC_ALL='en_US.UTF-8')
        for key in ('WAYLAND_DISPLAY', 'DISPLAY', 'SWAYSOCK', 'DBUS_SESSION_BUS_ADDRESS'):
            env.pop(key, None)
        bus = subprocess.Popen(['dbus-daemon', '--session', '--nofork', '--nopidfile', '--print-address=1'],
                               env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        try:
            env['DBUS_SESSION_BUS_ADDRESS'] = bus.stdout.readline().strip()
            check(bool(env['DBUS_SESSION_BUS_ADDRESS']), 'Private D-Bus session did not start')
            config = base / 'compositor.conf'
            is_sway = Path(compositor).name == 'sway'
            config.write_text('output HEADLESS-1 resolution 1280x800\n' if is_sway else 'xkb_rules_layout=us\n')
            # Copying sway removes file capabilities that prevent its use in CI containers.
            if is_sway:
                compositor = shutil.copyfile(compositor, base / 'sway')
                Path(compositor).chmod(0o755)
            with (base / 'compositor.log').open('w') as log:
                display = subprocess.Popen([compositor, '-c', str(config)], env=env, stdout=log, stderr=log)
                try:
                    for _ in range(100):
                        sockets = [p for p in runtime.glob('wayland-*') if p.is_socket()]
                        if sockets:
                            break
                        check(display.poll() is None, 'Headless compositor failed: ' + (base / 'compositor.log').read_text())
                        time.sleep(.05)
                    check(bool(sockets), 'Private Wayland socket did not appear')
                    env['WAYLAND_DISPLAY'] = sockets[0].name
                    for zone in ('Asia/Jerusalem', 'UTC', 'America/New_York'):
                        test_zone(base, env, zone, harness, zone == 'Asia/Jerusalem')
                finally:
                    stop(display)
        finally:
            stop(bus)
            bus.stdout.close()


def test_zone(base, env, zone, harness, rollover):
    env = dict(env, TZ=zone)
    shell = base / 'shell.qml'
    shell.write_text(harness)
    log_path = base / 'shell.log'
    with log_path.open('w') as log:
        process = subprocess.Popen(['quickshell', '--no-color', '-p', str(shell)], env=env, stdout=log, stderr=log)
        try:
            def ipc(function, *args):
                result = subprocess.run(['quickshell', 'ipc', '-p', str(shell), 'call', 'clockTest', function, *args],
                                        env=env, capture_output=True, text=True, timeout=3)
                if result.returncode:
                    raise RuntimeError(result.stderr + log_path.read_text())
                return result.stdout.strip()

            for _ in range(60):
                check(process.poll() is None, 'Clock harness failed: ' + log_path.read_text())
                if 'Configuration Loaded' in log_path.read_text():
                    break
                time.sleep(.05)
            sample = lambda: json.loads(ipc('sample'))
            check(not sample()['enabled'], 'Clock should sleep while unlocked')
            ipc('engage')
            for _ in range(20):
                first = sample()
                if first['locked'] and first['secure']:
                    break
                time.sleep(.1)
            check(first['locked'] and first['secure'], 'The private test session must actually lock: '
                  + str(first) + '\n' + log_path.read_text())
            check(first['enabled'], 'Clock did not start on lock (missing WlSessionLock notification)')
            # SystemClock deliberately tolerates up to 500 ms of timer skew at a boundary.
            check(-500 <= first['now'] - first['epoch'] < 60000, 'First lock shows a stale minute')
            local = datetime.fromtimestamp(first['epoch'] / 1000, ZoneInfo(zone))
            check(first['time'] == local.strftime('%H:%M'), f'Wrong local hour in {zone}: {first}')
            check(first['day'] == f'{local:%A}, {local.day} {local:%B}', f'Wrong local date in {zone}')

            for iso in ('2026-01-15T00:05:00Z', '2026-01-15T12:05:00Z', '2026-07-15T18:05:00Z',
                        '2026-10-05T22:05:00Z'):
                expected = datetime.fromisoformat(iso).astimezone(ZoneInfo(zone)).strftime('%H:%M')
                check(ipc('format', iso) == expected, f'24-hour/DST/midnight format failed: {zone} {iso}')

            ipc('release')
            check(not sample()['enabled'], 'Clock kept running after unlock')
            time.sleep(1.2)
            ipc('engage')
            relock = sample()
            check(relock['enabled'] and -500 <= relock['now'] - relock['tick'] < 1000, 'Relock did not refresh time immediately')

            # Pause this test process only, then deliver overdue timers as after resume.
            process.send_signal(signal.SIGSTOP)
            try:
                time.sleep(2.2)
            finally:
                process.send_signal(signal.SIGCONT)
            # A second-precision Qt timer may resume at its next boundary rather
            # than within 150 ms. Wait for delivery while retaining the strict
            # fresh-tick check, and bound recovery independently of wall time.
            deadline = time.monotonic() + 2
            while True:
                resumed = sample()
                if (resumed['tick'] > relock['tick']
                        and -500 <= resumed['now'] - resumed['tick'] < 1000):
                    break
                if time.monotonic() >= deadline:
                    break
                time.sleep(.05)
            check(resumed['tick'] > relock['tick'] and -500 <= resumed['now'] - resumed['tick'] < 1000,
                  'Clock did not recover after the event loop resumed: ' + str(resumed))
            if rollover:
                print(f'{zone}: lock/relock/resume and local formats passed; waiting for minute rollover', flush=True)
                deadline = time.monotonic() + 65
                while time.monotonic() < deadline:
                    if sample()['epoch'] > resumed['epoch']:
                        break
                    time.sleep(.25)
                else:
                    raise AssertionError('Production minute clock did not advance while locked')
            ipc('release')
            check(not sample()['enabled'], 'Clock did not stop after final unlock')
            check(not re.search(r'TypeError|ReferenceError|SyntaxError|ERROR|Failed to load', log_path.read_text()),
                  'QML errors: ' + log_path.read_text())
            print(f'{zone}: clock regression checks passed', flush=True)
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGCONT)
            stop(process)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1] / 'LockScreen.qml')
    parser.add_argument('--compositor', default=shutil.which('sway') or shutil.which('mango'))
    args = parser.parse_args()
    if not args.compositor or not shutil.which('quickshell') or not shutil.which('dbus-daemon'):
        parser.error('Install quickshell, dbus-daemon and sway (or mango) first')
    run(args.source, args.compositor)
