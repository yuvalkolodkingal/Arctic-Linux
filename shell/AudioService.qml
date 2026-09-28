pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Services.Pipewire

// Sound through PipeWire (event-driven): the default output and input, every output and input
// device, and the apps playing (the sound menu). `changed` fires when the default output's
// volume or mute state changes after it has settled, which is what drives the OSD. When the
// default output changes by itself (headphones plugged in, a headset connected) a quiet
// notification says where sound plays now.
Singleton {
    id: audio
    readonly property var sink: Pipewire.defaultAudioSink
    readonly property var source: Pipewire.defaultAudioSource
    readonly property bool available: Pipewire.ready && sink !== null && sink.audio !== null
    readonly property bool sourceAvailable: Pipewire.ready && source !== null && source.audio !== null
    readonly property real volume: available ? sink.audio.volume : 0
    readonly property bool muted: available ? sink.audio.muted : false
    readonly property int percent: Math.round(volume * 100)
    readonly property string description: label(sink)
    readonly property real sourceVolume: sourceAvailable ? source.audio.volume : 0
    readonly property bool sourceMuted: sourceAvailable ? source.audio.muted : false
    // Devices and app streams (the filters of Settings → Sound).
    readonly property var devices: Pipewire.nodes.values.filter(n => n.audio && !n.isStream)
    readonly property var sinks: devices.filter(n => n.isSink)
    readonly property var sources: devices.filter(n => !n.isSink)
    readonly property var streams: Pipewire.nodes.values.filter(n => n.audio && n.isStream && n.isSink)
    property bool settled: false
    property var chosenSink: null       // the output picked in the menu (no "now plays on" notice)
    signal changed()

    function label(n) { return n ? (n.description || n.nickname || n.name || '') : ''; }
    // A glyph for an output or input: Bluetooth and headphone jacks, HDMI/DisplayPort, speakers.
    function iconFor(n) {
        if (!n) return 'speaker';
        const text = (String(n.name || '') + ' ' + label(n)).toLowerCase();
        if (!n.isSink) return 'mic';
        if (text.indexOf('headset') >= 0 || text.indexOf('hands-free') >= 0) return 'headset';
        if (text.indexOf('bluez') >= 0 || text.indexOf('headphone') >= 0) return 'headphones';
        if (text.indexOf('hdmi') >= 0 || text.indexOf('displayport') >= 0) return 'display';
        return 'speaker';
    }

    function setVolume(v) {
        if (!available) return;
        sink.audio.muted = false;
        sink.audio.volume = Math.max(0, Math.min(1, v));
    }
    function step(direction) { setVolume(Math.round((volume + direction * 0.05) * 20) / 20); }
    function toggleMute() { if (available) sink.audio.muted = !sink.audio.muted; }
    function setSourceVolume(v) {
        if (!sourceAvailable) return;
        source.audio.muted = false;
        source.audio.volume = Math.max(0, Math.min(1, v));
    }
    function toggleSourceMute() { if (sourceAvailable) source.audio.muted = !source.audio.muted; }
    function setNodeVolume(n, v) {
        if (!n || !n.audio) return;
        n.audio.muted = false;
        n.audio.volume = Math.max(0, Math.min(1, v));
    }
    function toggleNodeMute(n) { if (n && n.audio) n.audio.muted = !n.audio.muted; }
    function setDefaultSink(n) { if (n) { chosenSink = n; Pipewire.preferredDefaultAudioSink = n; } }
    function setDefaultSource(n) { if (n) Pipewire.preferredDefaultAudioSource = n; }
    // The next output by name, wrapping (Shift + Mute key).
    function nextOutput() {
        const list = sinks.slice().sort((a, b) => label(a).localeCompare(label(b)));
        if (list.length < 2) return;
        const at = list.indexOf(sink);
        setDefaultSink(list[(at + 1) % list.length]);
    }

    PwObjectTracker { objects: [audio.sink, audio.source].filter(n => n !== null) }
    onSinkChanged: {
        if (settled && sink && sink !== chosenSink && sinks.length > 1)
            Quickshell.execDetached(['notify-send', '-a', 'Sound', '-i', 'audio-speakers', '-u', 'low', '-e',
                                     'Sound now plays on ' + label(sink)]);
        chosenSink = null;
        settled = false;
        settle.restart();
    }
    Timer { id: settle; interval: 1500; running: true; onTriggered: audio.settled = true }
    Connections {
        target: audio.available ? audio.sink.audio : null
        function onVolumeChanged() { if (audio.settled) audio.changed(); }
        function onMutedChanged() { if (audio.settled) audio.changed(); }
    }
}
