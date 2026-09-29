pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Services.Pipewire

// What is listening or watching right now, from PipeWire: apps recording from a microphone
// (Stream/Input/Audio, level meters of mixers left out), apps capturing a camera
// (Stream/Input/Video) and screen sharing through xdg-desktop-portal-wlr (its xdpw video
// sources). Apps that open /dev/video* directly aren't seen by PipeWire, so they don't show.
Singleton {
    id: privacy
    // Streams and video sources only: a small, bounded set to track.
    readonly property var candidates: Pipewire.nodes.values.filter(n => n.isStream || String(n.name).indexOf('xdpw') === 0)
    readonly property var mic: appsOf('Stream/Input/Audio')
    readonly property var camera: appsOf('Stream/Input/Video')
    readonly property var sharing: candidates.filter(n => String(n.name).indexOf('xdpw') === 0).map(n => 'the screen')
    readonly property bool active: mic.length > 0 || camera.length > 0 || sharing.length > 0

    function appsOf(kind) {
        const out = [];
        candidates.forEach(n => {
            const p = n.properties || {};
            if (p['media.class'] !== kind || p['stream.monitor'] === 'true') return;
            const name = p['application.name'] || p['application.process.binary'] || n.description || n.name || 'An app';
            if (out.indexOf(name) < 0) out.push(name);
        });
        return out;
    }
    function names(list) {
        return list.length <= 2 ? list.join(' and ') : list.slice(0, 2).join(', ') + ' and ' + (list.length - 2) + ' more';
    }

    PwObjectTracker { objects: privacy.candidates }
}
