pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io

// The welcome on an installed system, at the first login of a new account (arctic-welcome
// calls `arctic-shell-ipc welcome firstLogin`; the command menu's Learn › Welcome shows it
// again). A centred card: the keys that get you everywhere, then what to do first: get online
// (only while offline), Get apps, light or dark, and, while arctic-firstboot still has apps
// the installer put off (/var/lib/arctic/pending.json), which ones are on their way. When that
// file goes away, a notification says they're all installed.
Popover {
    id: card
    property bool quickSettings: false          // the bar's Quick settings (Super + A) is there
    property var pendingApps: []
    property bool pendingSeen: false
    readonly property string firstName: (Session.fullName || Session.user).split(' ')[0]
    readonly property bool offline: NetworkService.available && NetworkService.state !== 'connected'

    layerName: 'arctic-welcome'
    placement: 'center'
    cardWidth: 480
    cardHeight: body.implicitHeight + 2 * 28
    focusItem: start
    onOpened: if (!ipcShow.running) ipcShow.running = true

    function run(argv) {
        Quickshell.execDetached(argv);
    }
    function names(list) {
        if (list.length <= 1) return list.join('');
        return list.slice(0, -1).join(', ') + ' and ' + list[list.length - 1];
    }

    // Is Quick settings (another part of the shell) there to point at?
    Process {
        id: ipcShow
        command: ['quickshell', 'ipc', '-p', Quickshell.shellDir, 'show']
        stdout: StdioCollector { onStreamFinished: card.quickSettings = /^target quick$/m.test(text) }
    }
    // Apps the installer put off, which arctic-firstboot installs in the background.
    FileView {
        path: '/var/lib/arctic/pending.json'
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: {
            try {
                const data = JSON.parse(text());
                card.pendingApps = (data.modules || []).map(m => m.name || m.id).filter(n => !!n);
            } catch (e) {
                card.pendingApps = [];
            }
            if (card.pendingApps.length) card.pendingSeen = true;
        }
        onLoadFailed: {
            if (card.pendingSeen && card.pendingApps.length)
                Quickshell.execDetached(['notify-send', '-a', 'Arctic Linux', '-i', 'emblem-ok-symbolic', 'All set',
                                         card.names(card.pendingApps) + (card.pendingApps.length === 1 ? ' is' : ' are') + ' installed now.']);
            card.pendingApps = [];
            card.pendingSeen = false;
        }
    }

    component Step: RowLayout {
        id: step
        property string icon: ''
        property string title: ''
        property string desc: ''
        default property alias actions: actionRow.data
        Layout.fillWidth: true
        spacing: Theme.space3
        Icon { name: step.icon; size: 20; color: Theme.inkMuted; Layout.alignment: Qt.AlignTop; Layout.topMargin: 2 }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 0
            Text { Layout.fillWidth: true; text: step.title; color: Theme.ink; font.family: Theme.fontSans; font.pixelSize: 15; font.weight: Font.DemiBold; wrapMode: Text.Wrap }
            Text { Layout.fillWidth: true; visible: text !== ''; text: step.desc; color: Theme.inkMuted; font.family: Theme.fontSans; font.pixelSize: 12; wrapMode: Text.Wrap }
        }
        RowLayout { id: actionRow; spacing: Theme.space1 }
    }
    component KeyRow: RowLayout {
        id: keyRow
        property var keys: []
        property string what: ''
        Layout.fillWidth: true
        spacing: Theme.space3
        Item {
            Layout.preferredWidth: 168
            Layout.fillWidth: false
            implicitHeight: chips.implicitHeight
            Row {
                id: chips
                spacing: Theme.space1
                Repeater {
                    model: keyRow.keys
                    Row {
                        id: chip
                        required property string modelData
                        required property int index
                        spacing: Theme.space1
                        Text { visible: chip.index > 0; anchors.verticalCenter: parent.verticalCenter; text: '+'; color: Theme.inkMuted; font.family: Theme.fontSans; font.pixelSize: 12 }
                        Kbd { text: chip.modelData }
                    }
                }
            }
        }
        Text { Layout.fillWidth: true; text: keyRow.what; color: Theme.ink; font.family: Theme.fontSans; font.pixelSize: 14; wrapMode: Text.Wrap }
    }

    ColumnLayout {
        id: body
        anchors.fill: parent
        anchors.margins: 28
        spacing: 0
        Keys.onEscapePressed: card.close()

        Mark { size: 48; color: Theme.ink; eye: Theme.accent }
        Text {
            Layout.topMargin: 12
            Layout.fillWidth: true
            text: 'Welcome to Arctic Linux'
            color: Theme.ink
            font.family: Theme.fontSans
            font.pixelSize: 28
            font.weight: Font.DemiBold
            font.letterSpacing: -0.28
            lineHeight: 36
            lineHeightMode: Text.FixedHeight
        }
        Text {
            Layout.topMargin: 4
            Layout.fillWidth: true
            text: (card.firstName ? 'Hi ' + card.firstName + '. ' : '') + 'A few keys get you everywhere.'
            color: Theme.inkMuted
            wrapMode: Text.Wrap
            font.family: Theme.fontSans
            font.pixelSize: 15
            lineHeight: 22
            lineHeightMode: Text.FixedHeight
        }

        ColumnLayout {
            Layout.topMargin: 16
            Layout.fillWidth: true
            spacing: Theme.space2
            KeyRow { keys: ['Super', 'Space']; what: 'Apps, settings and files' }
            KeyRow { keys: ['Super', 'Alt', 'Space']; what: 'Every system action, in one menu' }
            KeyRow { visible: card.quickSettings; keys: ['Super', 'A']; what: 'Quick settings: Wi-Fi, sound, modes' }
            KeyRow { keys: ['Super', '/']; what: 'All the shortcuts' }
        }

        Rectangle { Layout.topMargin: 20; Layout.bottomMargin: 16; Layout.fillWidth: true; implicitHeight: 1; color: Theme.line }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.space4
            Step {
                visible: card.offline
                icon: 'wifi-off'
                title: 'Get online'
                desc: 'For updates and new apps.'
                ArcticButton {
                    size: 'sm'
                    text: 'Connect'
                    onClicked: {
                        card.close();
                        card.run(['sh', '-c', 'arctic-shell-ipc panel open network >/dev/null 2>&1 || exec arctic-settings network']);
                    }
                }
            }
            Step {
                visible: card.pendingApps.length > 0
                icon: 'download'
                title: 'Finishing setup'
                desc: 'Installing ' + card.names(card.pendingApps) + ' in the background' + (card.offline ? ', once you’re online.' : '.')
            }
            Step {
                icon: 'package'
                title: 'Get apps'
                desc: 'From Flathub, Fedora and the web.'
                ArcticButton {
                    size: 'sm'
                    text: 'Get apps'
                    onClicked: { card.close(); card.run(['arctic-shell-ipc', 'apps', 'install']); }
                }
            }
            Step {
                icon: Theme.dark ? 'moon' : 'snowflake'
                title: 'Light or dark'
                desc: 'Switch any time with Super + Shift + T.'
                ArcticButton {
                    size: 'sm'
                    variant: Theme.dark ? 'secondary' : 'primary'
                    iconName: 'snowflake'
                    text: 'Light'
                    onClicked: card.run(['arctic-theme', 'light'])
                }
                ArcticButton {
                    size: 'sm'
                    variant: Theme.dark ? 'primary' : 'secondary'
                    iconName: 'moon'
                    text: 'Dark'
                    onClicked: card.run(['arctic-theme', 'dark'])
                }
            }
        }

        RowLayout {
            Layout.topMargin: 24
            Layout.fillWidth: true
            spacing: Theme.space2
            ArcticButton {
                variant: 'ghost'
                iconName: 'globe'
                text: 'Read the guide'
                onClicked: { card.close(); card.run(['xdg-open', 'https://github.com/yuvalkolodkingal/O-Tism/wiki/Desktop-Tour']); }
            }
            Item { Layout.fillWidth: true }
            ArcticButton {
                id: start
                variant: 'primary'
                text: 'Get started'
                onClicked: card.close()
                Keys.onEscapePressed: card.close()
            }
        }
    }
}
