pragma Singleton
pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io
import "../shell/DictationStatus.js" as Status

Singleton {
    id: dictation
    property var status: Status.parse('')
    readonly property bool busy: command.running
    readonly property bool active: Status.active(status)
    readonly property string headline: Status.headline(status)
    readonly property string detail: Status.detail(status)

    // Argument lists are fixed by the page. No shell interpolation, audio or text results.
    function run(args) {
        if (command.running) return;
        command.command = ['arctic-dictation'].concat(args);
        command.running = true;
    }
    function refresh() { run(['status']); }
    function cancel() { run(['cancel']); }
    Process {
        id: command
        command: ['arctic-dictation', 'status']
        stdout: StdioCollector {
            onStreamFinished: {
                const snapshot = Status.parse(text);
                if (text.trim() === '') snapshot.error = 'The dictation controller is unavailable. Install the current Arctic desktop updates, then try again.';
                dictation.status = snapshot;
            }
        }
        onExited: code => {
            if (code !== 0 && dictation.status.state === 'unavailable') {
                const snapshot = Status.parse('');
                snapshot.error = 'The dictation controller is unavailable. Install the current Arctic desktop updates, then try again.';
                dictation.status = snapshot;
            }
        }
    }
}
