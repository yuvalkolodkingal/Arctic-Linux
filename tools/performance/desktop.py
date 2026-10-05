#!/usr/bin/env python3
"""Separate functional GUI/PAM checks, ONLY in a disposable installed QEMU guest.

Use a composed --desktop probe with --stage boot --guest-check-interactive.
Runs after the repeated performance measurements, without altering preferences,
network services, security policy, or the shipped browser choice.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def exercise(performance, prefix, wallpaper=False):
    run = performance['run']
    failed = False

    def emit(name, status, value):
        print('ARCTIC-DESKTOP ' + json.dumps(dict(check=name, status=status, value=value)), flush=True)

    def require(condition, value):
        if not condition:
            raise RuntimeError(value)
        return value

    def check(name, fn):
        nonlocal failed
        try:
            emit(name, 'passed', fn())
        except Exception as error:
            failed = True
            emit(name, 'failed', str(error))

    def wait(fn, wanted, seconds):
        until = time.monotonic()+seconds
        while time.monotonic() < until:
            if fn() == wanted:
                return True
            time.sleep(1)
        raise RuntimeError(f'Expected {wanted} within {seconds}s')

    settings = prefix + ['python3', '/usr/share/arctic/settings/scripts/arctic_settings.py']
    shell = prefix + ['quickshell', 'ipc', '-p', run(prefix + ['arctic-shell', '--path']), 'call']
    check('selinux-enforcing', lambda: require(run(['getenforce']) == 'Enforcing', 'SELinux enforcing'))
    check('default-browser', lambda: require('zen' in (value := run(prefix + ['xdg-settings', 'get', 'default-web-browser'])).lower(), value))
    for feature in ('motion', 'gaming', 'optional-network'):
        check(feature+'-status', lambda feature=feature: json.loads(run(settings + [feature], timeout=180)))
    check('webapp-runtimes', lambda: json.loads(run(prefix + ['arctic-webapp', 'runtimes', '--json'], timeout=180)))
    check('chromium-backend-binary', lambda: run(['test', '-x', '/usr/lib64/chromium-browser/chromium-browser']))
    if wallpaper:
        check('shared-wallpaper-status', lambda: require((value := json.loads(run(settings + ['login-wallpaper', 'status'], timeout=180))).get('ok') and value.get('available', True), value))

    def settings_gui():
        before = set(performance['clients'](prefix))
        output = Path('/tmp/arctic-desktop-settings.log')
        ipc = prefix + ['quickshell', 'ipc', '-p', '/usr/share/arctic/settings', 'call', 'settings']
        with output.open('w') as log:
            child = subprocess.Popen(prefix + ['arctic-settings'], stdout=log, stderr=log)
            try:
                def mapped():
                    return any(key not in before and 'arctic settings' in str(value.get('title', '')).lower()
                               for key, value in performance['clients'](prefix).items())
                wait(mapped, True, 300)
                pages = run(ipc + ['pages']).split()
                expected = ('appearance', 'accessibility', 'apps', 'network', 'sound', 'updates', 'power', 'about')
                require(set(expected).issubset(pages), pages)
                for page in expected:
                    require(run(ipc + ['open', page]) == 'ok', page)
                    wait(lambda: run(ipc + ['ready']).lower() == 'true', True, 180)
                    require(run(ipc + ['page']) == page, page)
                    require(mapped(), 'Settings window must remain mapped')
                    emit('settings-page', 'passed', page)
                    time.sleep(15)  # the interactive harness captures each rendered page
                return list(expected)
            finally:
                current = performance['clients'](prefix)
                for key in set(current)-before:
                    if 'arctic settings' in str(current[key].get('title', '')).lower():
                        subprocess.run(prefix + ['mmsg', 'dispatch', 'killclient', 'client,'+key], capture_output=True, timeout=30)
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(10)
                    except subprocess.TimeoutExpired:
                        child.kill(); child.wait()
                emit('settings-launch-output', 'diagnostic', output.read_text(errors='replace')[-12000:])
    check('settings-window-and-pages', settings_gui)

    def get_apps():
        run(shell + ['apps', 'install'])
        emit('get-apps-opened', 'requested', 'Check the captured chooser/catalog screenshot')
        time.sleep(30)
        run(shell + ['launcher', 'close'])
        return 'Production shell IPC request completed; visual review required'
    check('get-apps-request', get_apps)

    def lock_unlock():
        locked = lambda: run(shell + ['lock', 'isLocked']).lower() == 'true'
        require(not locked(), 'Session starts unlocked')
        run(shell + ['lock', 'lock'])
        wait(locked, True, 60)
        emit('session-lock-confirmed', 'passed', 'Compositor confirmed a secure session lock')
        time.sleep(65)  # screenshots span at least one clock-minute transition
        require(locked(), 'Lock stays secure until password authentication')
        print('ARCTIC-DESKTOP-UNLOCK-REQUESTED', flush=True)
        wait(locked, False, 180)
        return 'Unlocked through the real lock-screen PAM flow using simulated keyboard input'
    check('lock-and-password-unlock', lock_unlock)
    emit('done', 'failed' if failed else 'passed', 'Visual screenshot review remains a separate gate')
    return int(failed)


def main(performance, wallpaper=False):
    run = performance['run']
    if sys.argv[1] != 'installed' or os.geteuid() != 0 or run(['systemd-detect-virt', '--vm']) != 'qemu':
        raise RuntimeError('Requires the disposable installed QEMU guest')
    prefix = performance['desktop']()
    awake = json.loads(run(prefix + ['arctic-keep-awake', 'status', '--json']))
    if not awake.get('on'):
        run(prefix + ['arctic-keep-awake', 'on', '--quiet'])
    try:
        # Keep awake prevents an unrelated idle timeout; explicit session lock still
        # uses the unchanged compositor/PAM flow and the real simulated password.
        return exercise(performance, prefix, wallpaper)
    finally:
        if not awake.get('on'):
            run(prefix + ['arctic-keep-awake', 'off', '--quiet'])
