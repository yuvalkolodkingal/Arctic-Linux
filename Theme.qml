pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
Singleton {
    id: theme
    property var palette: ({})
    readonly property color background: palette.ui ? palette.ui.background : '#191b20'
    readonly property color text: '#f4f3f0'
    readonly property color muted: '#b9bcc4'
    readonly property color surface: palette.ui ? palette.ui.surface : '#292c33'
    readonly property color accent: palette.ui ? palette.ui.accent : '#a6bedc'
    readonly property string font: 'DejaVu Sans'
    readonly property int radius: 12
    readonly property int gap: 16
    readonly property int motionDuration: 260
    readonly property int glideDuration: 240
    readonly property int barHeight: 44
    readonly property int frameWidth: 6
    readonly property int frameRadius: 18
    FileView {
        path: Quickshell.env('HOME') + '/.cache/quickshell-wallpapers/theme.json'
        watchChanges: true
        onFileChanged: reload()
        onLoaded: { try { theme.palette = JSON.parse(text()); } catch (e) {} }
    }
}
