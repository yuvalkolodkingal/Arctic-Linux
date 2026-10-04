pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

// Where things live and what kind of session this is: paths (XDG first, then /usr/share),
// the live-USB flag, reduced motion and the shell settings in ~/.config/arctic/shell.json.
Singleton {
    id: session

    readonly property string home: Quickshell.env('HOME') || ''
    readonly property string configHome: Quickshell.env('XDG_CONFIG_HOME') || home + '/.config'
    readonly property string cacheHome: Quickshell.env('XDG_CACHE_HOME') || home + '/.cache'
    readonly property string dataHome: Quickshell.env('XDG_DATA_HOME') || home + '/.local/share'
    readonly property string runtimeDir: Quickshell.env('XDG_RUNTIME_DIR') || '/tmp'
    readonly property string arcticConfig: configHome + '/arctic'
    readonly property string arcticCache: cacheHome + '/arctic'
    readonly property string scripts: Quickshell.shellDir + '/scripts'
    property string user: Quickshell.env('USER') || ''
    property string fullName: ''
    property bool hasFace: false        // ~/.face, the avatar picture used by the lock screen

    // Live USB ("Try Arctic Linux"): rd.live.image on the kernel command line.
    // ARCTIC_FORCE_LIVE=1 fakes it for screenshots and tests only.
    readonly property bool forceLive: Quickshell.env('ARCTIC_FORCE_LIVE') === '1'
    property string cmdline: ''
    readonly property bool live: forceLive || /(^|\s)rd\.live\.image(\s|$)/.test(cmdline)

    // Reduced motion: `arctic-motion off` writes ~/.config/arctic/motion.conf.
    property bool motionFile: false
    readonly property bool reduceMotion: motionFile || Quickshell.env('ARCTIC_REDUCE_MOTION') === '1'

    // ~/.config/arctic/shell.json, e.g. {"frame": true}. Missing keys use the defaults.
    property var settings: ({})
    readonly property bool frame: settings.frame !== false

    // The top bar hidden with Super + Shift + Space (`bar toggleHidden`): for this session only,
    // so a restart of the shell or a new login brings it back. Never on the live USB, whose bar
    // holds the Install item.
    property bool barHidden: false
    readonly property string barPosition: ['top', 'bottom', 'left', 'right'].includes(settings.barPosition) ? settings.barPosition : 'top'
    readonly property bool barVertical: barPosition === 'left' || barPosition === 'right'
    readonly property int barSize: Number.isInteger(settings.barSize) && settings.barSize >= 28 && settings.barSize <= 56 ? settings.barSize : 0
    readonly property bool barAutoHide: !live && settings.barAutoHide === true
    readonly property bool barWorkspaces: settings.barWorkspaces !== false
    readonly property bool barClock: settings.barClock !== false
    readonly property bool barMedia: settings.barMedia !== false
    readonly property bool barTray: settings.barTray !== false

    function reload() {
        motionView.reload();
        settingsView.reload();
    }

    Process {
        command: ['cat', '/proc/cmdline']
        running: true
        stdout: StdioCollector { onStreamFinished: session.cmdline = text.trim() }
    }
    Process {
        command: ['test', '-r', session.home + '/.face']
        running: true
        onExited: code => session.hasFace = code === 0
    }
    Process {
        command: ['id', '-un']
        running: session.user === ''
        stdout: StdioCollector { onStreamFinished: session.user = text.trim() }
    }
    Process {
        command: ['getent', 'passwd', session.user]
        running: session.user !== ''
        stdout: StdioCollector {
            onStreamFinished: {
                const gecos = (text.split(':')[4] || '').split(',')[0].trim();
                session.fullName = gecos;
            }
        }
    }
    FileView {
        id: motionView
        path: session.arcticConfig + '/motion.conf'
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: session.motionFile = true
        onLoadFailed: session.motionFile = false
    }
    FileView {
        id: settingsView
        path: session.arcticConfig + '/shell.json'
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: {
            try { session.settings = JSON.parse(text()) || {}; } catch (e) { session.settings = {}; }
        }
        onLoadFailed: session.settings = {}
    }
}
