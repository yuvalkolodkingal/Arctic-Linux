pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Services.Pipewire

// The sound menu (bar volume item, Super + Ctrl + A): output volume and where sound plays,
// microphone volume and which one listens, and a volume for each app playing. A device's page
// (right click, Menu key or its dots) picks its port (headphones or speakers) and its card's
// profile (scripts/audio.py). Everything else is PipeWire through AudioService; the volume
// control (pwvucontrol or pavucontrol) is one row away for routing.
FocusScope {
    id: panel
    property var menu: null
    readonly property string mixer: Tools.has('pwvucontrol') ? 'pwvucontrol' : Tools.has('pavucontrol') ? 'pavucontrol' : ''

    property string page: ''            // '', 'device'
    property var target: null           // the sink or source whose page is open
    property var cards: []              // audio.py devices
    property string pageError: ''
    readonly property var card: target ? cards.find(c => String(c.id) === String(target.properties['device.id'])) || null : null
    readonly property var routes: card && target
        ? card.routes.filter(r => r.direction === (target.isSink ? 'output' : 'input')
                             && r.devices.indexOf(Number(target.properties['card.profile.device'])) >= 0)
        : []

    implicitWidth: 360
    implicitHeight: page === '' ? list.implicitHeight : devicePage.implicitHeight

    function openDevice(n) {
        target = n;
        pageError = '';
        page = 'device';
        readCards();
    }
    function back() {
        page = '';
        Qt.callLater(() => list.start());
    }
    function readCards() { if (!cardReader.running) cardReader.running = true; }
    function apply(args) {
        pageError = '';
        action.command = ['python3', Session.scripts + '/audio.py'].concat(args.map(String));
        action.running = true;
    }
    Process {
        id: cardReader
        command: ['python3', Session.scripts + '/audio.py', 'devices']
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const data = JSON.parse(text);
                    if (data.ok) panel.cards = data.devices; else panel.pageError = data.error;
                } catch (e) {}
            }
        }
    }
    Process {
        id: action
        stdout: StdioCollector {
            onStreamFinished: {
                try { const data = JSON.parse(text); if (!data.ok) panel.pageError = data.error; } catch (e) {}
                panel.readCards();
            }
        }
    }

    function external(command) {
        if (menu) menu.close();
        Quickshell.execDetached(command);
    }
    function appIcon(n) {
        const name = n.properties['application.icon-name'] || '';
        return name ? Quickshell.iconPath(name, true) : '';
    }
    function appName(n) {
        return n.properties['application.name'] || n.properties['media.name'] || AudioService.label(n);
    }

    // Volumes of every device and app shown here stay live while the menu is open.
    PwObjectTracker { objects: AudioService.devices.concat(AudioService.streams) }

    MenuList {
        id: list
        anchors.fill: parent
        visible: panel.page === ''
        focus: visible

        MenuHeader { title: 'Sound' }
        MenuSection {
            text: 'Output'
            visible: AudioService.sinks.length > 0
        }
        MenuSlider {
            visible: AudioService.available
            icon: 'volume'
            mutedIcon: 'volume-mute'
            label: AudioService.description + ' volume'
            caption: AudioService.sinks.length > 1 ? '' : AudioService.description
            value: AudioService.volume
            muted: AudioService.muted
            showChevron: true
            onMoved: v => AudioService.setVolume(v)
            onMuteToggled: AudioService.toggleMute()
            onOpened: panel.openDevice(AudioService.sink)
        }
        Repeater {
            // The device list when there is a choice (or no default yet to show a slider for).
            model: AudioService.sinks.length > 1 || !AudioService.available ? AudioService.sinks : []
            MenuRow {
                required property var modelData
                icon: AudioService.iconFor(modelData)
                label: AudioService.label(modelData)
                selected: modelData === AudioService.sink
                trailing: 'dots'
                onActivated: AudioService.setDefaultSink(modelData)
                onSecondary: panel.openDevice(modelData)
            }
        }
        Text {
            visible: AudioService.sinks.length === 0
            Layout.fillWidth: true
            Layout.leftMargin: Theme.space3
            Layout.bottomMargin: Theme.space2
            text: Pipewire.ready ? 'No speakers or headphones found.' : 'Sound isn’t running.'
            color: Theme.inkMuted
            font.family: Theme.fontSans
            font.pixelSize: 13
        }

        MenuSection {
            text: 'Input'
            visible: AudioService.sources.length > 0
        }
        MenuSlider {
            visible: AudioService.sourceAvailable
            icon: 'mic'
            mutedIcon: 'mic-off'
            label: AudioService.label(AudioService.source) + ' volume'
            caption: AudioService.sources.length > 1 ? '' : AudioService.label(AudioService.source)
            value: AudioService.sourceVolume
            muted: AudioService.sourceMuted
            showChevron: true
            onMoved: v => AudioService.setSourceVolume(v)
            onMuteToggled: AudioService.toggleSourceMute()
            onOpened: panel.openDevice(AudioService.source)
        }
        Repeater {
            model: AudioService.sources.length > 1 || !AudioService.sourceAvailable ? AudioService.sources : []
            MenuRow {
                required property var modelData
                icon: 'mic'
                label: AudioService.label(modelData)
                selected: modelData === AudioService.source
                trailing: 'dots'
                onActivated: AudioService.setDefaultSource(modelData)
                onSecondary: panel.openDevice(modelData)
            }
        }

        MenuSection {
            text: 'Apps'
            visible: AudioService.streams.length > 0
        }
        Repeater {
            model: AudioService.streams
            MenuSlider {
                required property var modelData
                image: panel.appIcon(modelData)
                icon: 'volume'
                mutedIcon: 'volume-mute'
                caption: panel.appName(modelData)
                label: panel.appName(modelData) + ' volume'
                value: modelData.audio ? modelData.audio.volume : NaN
                muted: modelData.audio ? modelData.audio.muted : false
                onMoved: v => AudioService.setNodeVolume(modelData, v)
                onMuteToggled: AudioService.toggleNodeMute(modelData)
            }
        }

        MenuSeparator {}
        MenuRow {
            visible: Tools.has('arctic-settings')
            icon: 'sliders'
            label: 'Sound settings'
            onActivated: panel.external(['arctic-settings', 'sound'])
        }
        MenuRow {
            visible: panel.mixer !== ''
            icon: 'volume'
            label: 'Volume control…'
            trailing: 'external'
            onActivated: panel.external([panel.mixer])
        }
    }

    // ---- a device's port and profile ----------------------------------------------------------
    MenuPage {
        id: devicePage
        anchors.fill: parent
        visible: panel.page === 'device'
        focus: visible
        title: panel.target ? AudioService.label(panel.target) : ''
        detail: panel.card ? panel.card.description : ''
        backText: 'Sound'
        onBack: panel.back()
        onVisibleChanged: if (visible) Qt.callLater(() => devicePage.start())

        MenuSection {
            visible: panel.routes.length > 1
            text: panel.target && panel.target.isSink ? 'Plays through' : 'Listens through'
        }
        Repeater {
            model: panel.routes.length > 1 ? panel.routes : []
            MenuRow {
                required property var modelData
                label: modelData.description
                detail: modelData.available === 'no' ? 'Not plugged in' : ''
                selected: modelData.active
                Accessible.role: Accessible.RadioButton
                onActivated: panel.apply(['route', panel.card.id, modelData.index, modelData.device])
            }
        }
        MenuSection {
            visible: panel.card !== null && panel.card.profiles.length > 1
            text: 'Profile'
        }
        Repeater {
            model: panel.card && panel.card.profiles.length > 1 ? panel.card.profiles : []
            MenuRow {
                required property var modelData
                label: modelData.description
                detail: modelData.available === 'no' ? 'Not available now' : ''
                enabled: modelData.available !== 'no' || modelData.active
                selected: modelData.active
                Accessible.role: Accessible.RadioButton
                onActivated: panel.apply(['profile', panel.card.id, modelData.index])
            }
        }
        Text {
            visible: panel.pageError !== '' || (!cardReader.running
                     && (panel.card === null || (panel.routes.length <= 1 && panel.card.profiles.length <= 1)))
            Layout.fillWidth: true
            Layout.leftMargin: Theme.space3
            Layout.rightMargin: Theme.space3
            Layout.bottomMargin: Theme.space2
            text: panel.pageError || 'This device has nothing to choose.'
            wrapMode: Text.WordWrap
            color: panel.pageError ? Theme.error : Theme.inkMuted
            font.family: Theme.fontSans
            font.pixelSize: 13
        }
    }
}
