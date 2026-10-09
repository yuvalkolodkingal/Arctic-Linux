"""Fail-closed evidence for the disposable ISO boot harness."""
import shlex
import time
import re
import uuid
from pathlib import Path


def console_screen(path):
    """Input guard only: refuse to type shell commands into a graphical wizard.

    Guest authentication, installer IPC, enforcing SELinux and unique completion
    records still determine startup acceptance. A dark image alone never passes.
    """
    from PIL import Image
    try:
        with Image.open(path) as image:
            if not (320 <= image.width <= 4096 and 200 <= image.height <= 4096):
                return False
            # Linux's text VT is black with a small amount of white console text.
            # Examine original pixels; a missing/blank/graphical capture fails.
            histogram = image.convert('L').histogram()
            total = image.width * image.height
            return sum(histogram[:17]) / total > .90 and sum(histogram[192:]) >= 30
    except (OSError, TypeError, ValueError):
        return False


def console_auth_command(nonce):
    if not re.fullmatch('[0-9a-f]{32}', nonce):
        raise ValueError('Invalid console authentication nonce')
    # Only the authenticated live account can emit this response. sudo merely
    # opens the serial device after the unprivileged caller's identity checks.
    response = 'printf "ARCTIC-CONSOLE-READY=' + nonce + ' user=liveuser uid=%s\\n" "$1" >/dev/ttyS0'
    return ('uid=$(id -u); test "$(id -un)" = liveuser && '
            'test "$uid" = "$(id -u liveuser)" && test "$uid" -ge 1000 && '
            'sudo sh -c ' + shlex.quote(response) + ' sh "$uid"')


def console_authenticated(path, nonce):
    if not re.fullmatch('[0-9a-f]{32}', nonce):
        return False
    try:
        content = Path(path).read_bytes()
    except (OSError, TypeError):
        return False
    if len(content) > 1024 * 1024:
        return False
    lines = content.decode('utf-8', errors='replace').splitlines()
    records = [line for line in lines if line.startswith('ARCTIC-CONSOLE-READY=')]
    if len(records) != 1:
        return False
    match = re.fullmatch('ARCTIC-CONSOLE-READY=' + nonce + r' user=liveuser uid=([0-9]+)', records[0])
    return bool(match and 1000 <= int(match[1]) <= 2147483647)


def installer_probe():
    validate = ("import json,sys; s=json.load(sys.stdin); "
                "assert s['page']=='welcome' and s['ready'] is True "
                "and s['connected'] is True and not s['failure']")
    return ("runuser -u liveuser -- env XDG_RUNTIME_DIR=/run/user/$(id -u liveuser) "
            "quickshell ipc -p /usr/share/arctic/installer-ui call installer state | "
            "python3 -c " + shlex.quote(validate))


def restore_desktop():
    # Discover the live user's real Wayland VT rather than guessing tty1/tty2.
    return ("restored=0; for s in $(loginctl list-sessions --no-legend | "
            "awk '$3==\"liveuser\" {print $1}'); do "
            "[ \"$(loginctl show-session \"$s\" -p Type --value)\" = wayland ] || continue; "
            "vt=$(loginctl show-session \"$s\" -p VTNr --value); "
            "case $vt in ''|0|*[!0-9]*) continue;; esac; "
            "if chvt \"$vt\"; then restored=1; break; fi; done; "
            "test \"$restored\" = 1")


def collection_command(mode, require_startup):
    commands = ('echo ARCTIC-COLLECT-BEGIN; cat ~liveuser/.local/share/sddm/*.log; '
                'cat /proc/cmdline; mokutil --sb-state; '
                'systemctl --failed --no-pager; journalctl -b -p warning --no-pager; '
                'getenforce; flatpak list; ')
    if require_startup:
        if mode not in ('try', 'install', 'safe'):
            raise ValueError('startup qualification supports try, install and safe')
        requested = 'install' if mode == 'install' else 'try'
        checks = ["grep -Eq '(^| )rd.live.image( |$)' /proc/cmdline",
                  f"grep -Eq '(^| )arctic.mode={requested}( |$)' /proc/cmdline",
                  'pgrep -u liveuser -x mango >/dev/null',
                  'test "$(getenforce)" = Enforcing']
        checks.append(("" if mode == 'safe' else '! ') +
                      "grep -Eq '(^| )nomodeset( |$)' /proc/cmdline")
        if mode == 'install':
            # Preserve the exclusive-focus installer and prove it actually
            # reached its connected, ready welcome state before collecting.
            checks.extend(['(' + installer_probe() + ')', '(' + restore_desktop() + ')'])
        commands += 'if ' + ' && '.join(checks) + '; then '
        commands += f'echo ARCTIC-STARTUP-PASS={mode}; else echo ARCTIC-STARTUP-FAILED; fi; '
    commands += 'echo ARCTIC-COLLECT-END'
    return 'sudo sh -c ' + shlex.quote('(' + commands + ') >/dev/ttyS0 2>&1')


def collect_session(vm, mode, require_startup, shot, log, sleep=time.sleep, serial_path=None):
    shot('97-before-collect')
    if mode == 'install':
        if serial_path is None:
            raise ValueError('Live console authentication needs the owned serial log')
        # The installer intentionally has exclusive layer-shell keyboard focus.
        # Super+Enter and typed shell commands would instead drive its wizard.
        # tty3 can belong to the live SDDM greeter (the retained BIOS captures
        # show the installer before Ctrl+Alt+F3 and that greeter afterwards).
        # logind reserves tty6 for a getty by default; still verify its actual
        # image before any input. Keep modifiers down through QEMU's 100 ms
        # key-up delay instead of a zero-duration input-send-event batch.
        reply = vm.cmd('send-key', keys=[dict(type='qcode', data=key)
                       for key in ('ctrl', 'alt', 'f6')], **{'hold-time': 100})
        if 'error' in reply:
            raise RuntimeError('QEMU refused the console VT chord')
        sleep(5)
        if not console_screen(shot('97-console-login')):
            raise RuntimeError('Console VT was not visible; refused to type into the installer')
        vm.type_text('liveuser', gap=.2)
        vm.keys('ret')
        sleep(3)
        # PAM may request the live account's empty password. If the shell is
        # already up, this is just an empty command. Never send the probe as a
        # password: first require a fresh response from the actual live UID.
        vm.keys('ret')
        sleep(3)
        nonce = uuid.uuid4().hex
        vm.type_text(console_auth_command(nonce), gap=.2)
        vm.keys('ret')
        for _ in range(30):
            if console_authenticated(serial_path, nonce):
                break
            sleep(1)
        else:
            shot('97-console-authentication-failed')
            raise RuntimeError('Live console authentication did not produce an exact UID response')
        log('authenticated liveuser text console with a unique UID response')
    else:
        vm.keys('meta_l-ret')
        sleep(60)
        vm.keys('ret')
        sleep(5)
    shot('98-console' if mode == 'install' else '98-terminal')
    vm.type_text(collection_command(mode, require_startup), gap=.2)
    vm.keys('ret')
    sleep(30)
    log('session collection command sent through ' + ('console' if mode == 'install' else 'terminal'))


def collection_complete(path, mode=None):
    try:
        lines = Path(path).read_text(errors='replace').splitlines()
    except OSError:
        return False
    markers = ['ARCTIC-COLLECT-BEGIN', 'ARCTIC-COLLECT-END']
    if mode is not None:
        markers.append('ARCTIC-STARTUP-PASS=' + mode)
        if 'ARCTIC-STARTUP-FAILED' in lines:
            return False
    # Commands echoed in warnings, partial/duplicate collections or another mode
    # cannot stand in for exact, uniquely emitted guest records.
    return (all(lines.count(marker) == 1 for marker in markers)
            and lines.index(markers[0]) < lines.index(markers[1])
            and (mode is None or lines.index(markers[0]) < lines.index(markers[2]) < lines.index(markers[1])))
