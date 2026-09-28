import QtQuick
import Quickshell
import Quickshell.Io

// The power button opens the power menu (binds.conf: XF86PowerOff → arctic-power) instead of
// shutting down at once. logind handles the button itself unless someone holds a
// handle-power-key inhibitor, so the shell holds one while it runs and the screen is unlocked.
// `cat` keeps it: it reads the shell's pipe and exits when the shell does (a crash included),
// which releases the lock and gives the button back to logind. While locked, logind's own
// setting applies, as without the shell.
Scope {
    id: key
    property bool locked: false

    Process {
        command: ['systemd-inhibit', '--what=handle-power-key', '--mode=block', '--who=Arctic shell',
                  '--why=The power button opens the power menu', 'cat']
        stdinEnabled: true
        running: !key.locked
    }
}
