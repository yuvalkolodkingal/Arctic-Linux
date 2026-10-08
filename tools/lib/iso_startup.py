"""Fail-closed evidence for the disposable ISO boot harness."""
import shlex
import time
from pathlib import Path


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


def collect_session(vm, mode, require_startup, shot, log, sleep=time.sleep):
    shot('97-before-collect')
    if mode == 'install':
        # The installer intentionally has exclusive layer-shell keyboard focus.
        # Super+Enter and typed shell commands would instead drive its wizard.
        vm.keys('ctrl-alt-f3')
        sleep(5)
        vm.type_text('liveuser', gap=.2)
        vm.keys('ret')
        sleep(5)
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
