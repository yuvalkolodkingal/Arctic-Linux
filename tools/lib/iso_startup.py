"""Fail-closed evidence for the disposable ISO boot harness."""
import shlex
from pathlib import Path


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
        commands += 'if ' + ' && '.join(checks) + '; then '
        commands += f'echo ARCTIC-STARTUP-PASS={mode}; else echo ARCTIC-STARTUP-FAILED; fi; '
    commands += 'echo ARCTIC-COLLECT-END'
    return 'sudo sh -c ' + shlex.quote('(' + commands + ') >/dev/ttyS0 2>&1')


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
