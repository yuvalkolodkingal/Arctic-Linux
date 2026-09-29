pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import "LauncherSearch.js" as LauncherSearch

// The pages and settings of Arctic Settings, for the launcher's search and the command menu's
// Setup branch. Read from Settings' own SearchIndex.js (found with `arctic-settings --path`),
// so a page added there shows up here too. Empty when Settings isn't installed.
Singleton {
    id: index
    property var pages: []
    property var entries: []
    property string dir: ''

    function refresh() { if (!locate.running) locate.running = true; }

    Process {
        id: locate
        command: ['arctic-settings', '--path']
        running: true
        stdout: StdioCollector { onStreamFinished: index.dir = text.trim() }
    }
    FileView {
        path: index.dir ? index.dir + '/SearchIndex.js' : ''
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: {
            const parsed = LauncherSearch.parseSettings(text());
            index.pages = parsed.pages;
            index.entries = parsed.entries;
        }
    }
}
