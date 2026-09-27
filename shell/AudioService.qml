pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Services.Pipewire

// The default output device through PipeWire (event-driven). `changed` fires when its volume
// or mute state changes after it has settled, which is what drives the OSD.
Singleton {
    id: audio
    readonly property var sink: Pipewire.defaultAudioSink
    readonly property bool available: Pipewire.ready && sink !== null && sink.audio !== null
    readonly property real volume: available ? sink.audio.volume : 0
    readonly property bool muted: available ? sink.audio.muted : false
    readonly property int percent: Math.round(volume * 100)
    readonly property string description: sink ? (sink.description || sink.nickname || sink.name || '') : ''
    property bool settled: false
    signal changed()

    function setVolume(v) {
        if (!available) return;
        sink.audio.muted = false;
        sink.audio.volume = Math.max(0, Math.min(1, v));
    }
    function step(direction) { setVolume(Math.round((volume + direction * 0.05) * 20) / 20); }
    function toggleMute() { if (available) sink.audio.muted = !sink.audio.muted; }

    PwObjectTracker { objects: audio.sink ? [audio.sink] : [] }
    onSinkChanged: { settled = false; settle.restart(); }
    Timer { id: settle; interval: 1500; running: true; onTriggered: audio.settled = true }
    Connections {
        target: audio.available ? audio.sink.audio : null
        function onVolumeChanged() { if (audio.settled) audio.changed(); }
        function onMutedChanged() { if (audio.settled) audio.changed(); }
    }
}
