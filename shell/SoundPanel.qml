pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Services.Pipewire

// The sound menu (bar volume item, Super + Ctrl + A): output volume and where sound plays,
// microphone volume and which one listens, and a volume for each app playing. Everything is
// PipeWire through AudioService; the volume control (pwvucontrol or pavucontrol) is one row
// away for ports, profiles and routing.
FocusScope {
    id: panel
    property var menu: null
    readonly property string mixer: Tools.has('pwvucontrol') ? 'pwvucontrol' : Tools.has('pavucontrol') ? 'pavucontrol' : ''

    implicitWidth: 360
    implicitHeight: list.implicitHeight

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
        focus: true

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
            onMoved: v => AudioService.setVolume(v)
            onMuteToggled: AudioService.toggleMute()
        }
        Repeater {
            // The device list when there is a choice (or no default yet to show a slider for).
            model: AudioService.sinks.length > 1 || !AudioService.available ? AudioService.sinks : []
            MenuRow {
                required property var modelData
                icon: AudioService.iconFor(modelData)
                label: AudioService.label(modelData)
                selected: modelData === AudioService.sink
                onActivated: AudioService.setDefaultSink(modelData)
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
            onMoved: v => AudioService.setSourceVolume(v)
            onMuteToggled: AudioService.toggleSourceMute()
        }
        Repeater {
            model: AudioService.sources.length > 1 || !AudioService.sourceAvailable ? AudioService.sources : []
            MenuRow {
                required property var modelData
                icon: 'mic'
                label: AudioService.label(modelData)
                selected: modelData === AudioService.source
                onActivated: AudioService.setDefaultSource(modelData)
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
}
