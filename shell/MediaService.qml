pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Services.Mpris

// Media players (MPRIS) for the bar's media item, its menu and Quick Settings: the player
// picked in the menu, else the one playing, else the first. Media keys stay on playerctl
// (binds.conf), which works without the shell.
Singleton {
    id: media
    readonly property var players: Mpris.players.values
    property var chosen: null
    readonly property var active: players.indexOf(chosen) >= 0 ? chosen
                                  : players.find(p => p.isPlaying) || (players.length ? players[0] : null)
    readonly property bool available: active !== null
    readonly property bool playing: active !== null && active.isPlaying
    readonly property string title: active ? (active.trackTitle || active.identity || '') : ''
    readonly property string artist: active ? (active.trackArtist || '') : ''

    function setActive(p) { chosen = p; }
    function playPause() { if (active && active.canTogglePlaying) active.togglePlaying(); }
    function next() { if (active && active.canGoNext) active.next(); }
    function previous() { if (active && active.canGoPrevious) active.previous(); }
    function time(seconds) {
        const s = Math.max(0, Math.floor(seconds));
        const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
        return (h > 0 ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(r).padStart(2, '0');
    }
}
