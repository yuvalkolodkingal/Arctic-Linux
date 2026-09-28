// Sound: the output and input devices and their volume, through PipeWire
// (Quickshell.Services.Pipewire, as the bar and OSD use). Per-app volumes are in the sound
// menu on the bar; device profiles and routing in pavucontrol (or pwvucontrol).
pragma ComponentBehavior: Bound
import QtQuick
import Quickshell.Services.Pipewire
import ".."
import "../components"

Page {
    id: page
    title: "Sound"
    lede: "Where sound plays and what you speak into."
    readonly property var nodes: Pipewire.nodes.values.filter(n => n.audio && !n.isStream)
    readonly property var sinks: nodes.filter(n => n.isSink)
    readonly property var sources: nodes.filter(n => !n.isSink && String(n.properties["media.class"] || "").indexOf("Audio/Source") === 0)
    readonly property var sink: Pipewire.defaultAudioSink
    readonly property var source: Pipewire.defaultAudioSource
    function label(n) {
        return n ? (n.description || n.nickname || n.name || "") : "";
    }

    PwObjectTracker {
        objects: page.nodes
    }

    ArBanner {
        visible: !Pipewire.ready || page.sinks.length === 0
        width: parent.width
        kind: "info"
        title: Pipewire.ready ? "No speakers or headphones found" : "Sound isn’t running"
        text: Pipewire.ready ? "Plug in headphones or check the cable." : "PipeWire, the sound service, isn’t running."
    }

    Group {
        visible: page.sinks.length > 0
        title: "Output"
        SettingRow {
            searchKey: "sound.output"
            title: "Play sound on"
            resettable: false
            ArSelect {
                width: 280
                model: page.sinks.map(n => ({ value: String(n.id), label: page.label(n) }))
                value: page.sink ? String(page.sink.id) : ""
                onActivated: v => Pipewire.preferredDefaultAudioSink = page.sinks.find(n => String(n.id) === v)
            }
        }
        SettingRow {
            title: "Volume"
            desc: page.sink && page.sink.audio ? (page.sink.audio.muted ? "Muted" : Math.round(page.sink.audio.volume * 100) + "%") : ""
            resettable: false
            Row {
                spacing: Theme.space2
                ArButton {
                    variant: "ghost"
                    size: "sm"
                    iconName: page.sink && page.sink.audio && page.sink.audio.muted ? "volume-mute" : "volume"
                    Accessible.name: "Mute"
                    gapColor: Theme.surfaceRaised
                    anchors.verticalCenter: parent.verticalCenter
                    onClicked: if (page.sink && page.sink.audio) page.sink.audio.muted = !page.sink.audio.muted
                }
                ArSlider {
                    accessibleName: "Output volume"
                    valueText: Math.round(value * 100) + " percent"
                    from: 0; to: 1; stepSize: 0.01
                    value: page.sink && page.sink.audio ? page.sink.audio.volume : 0
                    onMoved: if (page.sink && page.sink.audio) { page.sink.audio.muted = false; page.sink.audio.volume = value; }
                }
            }
        }
    }

    Group {
        visible: page.sources.length > 0
        title: "Input"
        SettingRow {
            searchKey: "sound.input"
            title: "Microphone"
            resettable: false
            ArSelect {
                width: 280
                model: page.sources.map(n => ({ value: String(n.id), label: page.label(n) }))
                value: page.source ? String(page.source.id) : ""
                onActivated: v => Pipewire.preferredDefaultAudioSource = page.sources.find(n => String(n.id) === v)
            }
        }
        SettingRow {
            title: "Input volume"
            desc: page.source && page.source.audio ? (page.source.audio.muted ? "Muted" : Math.round(page.source.audio.volume * 100) + "%") : ""
            resettable: false
            Row {
                spacing: Theme.space2
                ArButton {
                    variant: "ghost"
                    size: "sm"
                    iconName: page.source && page.source.audio && page.source.audio.muted ? "x-circle" : "mic"
                    Accessible.name: "Mute the microphone"
                    gapColor: Theme.surfaceRaised
                    anchors.verticalCenter: parent.verticalCenter
                    onClicked: if (page.source && page.source.audio) page.source.audio.muted = !page.source.audio.muted
                }
                ArSlider {
                    accessibleName: "Input volume"
                    valueText: Math.round(value * 100) + " percent"
                    from: 0; to: 1; stepSize: 0.01
                    value: page.source && page.source.audio ? page.source.audio.volume : 0
                    onMoved: if (page.source && page.source.audio) page.source.audio.volume = value
                }
            }
        }
    }

    Group {
        title: "More"
        SettingRow {
            visible: Backend.caps.shellIpc === true
            title: "Volume per app"
            desc: "The sound menu on the bar has a volume for every app playing (Super + Ctrl + A)."
            resettable: false
            ArButton {
                text: "Open the sound menu"
                gapColor: Theme.surfaceRaised
                onClicked: Backend.launch(["arctic-shell-ipc", "panel", "open", "sound"])
            }
        }
        SettingRow {
            title: "Device profiles and routing"
            desc: "For example to send one app to the headphones."
            resettable: false
            enabled: Backend.caps.pavucontrol === true || Backend.caps.pwvucontrol === true
            ArButton {
                text: "Open the volume control"
                iconRight: "external"
                gapColor: Theme.surfaceRaised
                onClicked: Backend.launch([Backend.caps.pwvucontrol ? "pwvucontrol" : "pavucontrol"])
            }
        }
    }
}
