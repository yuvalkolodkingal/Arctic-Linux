import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

// The frozen screen for area screenshots: arctic-screenshot takes a picture of every monitor
// (arctic-capture freeze) and asks the shell to show them over everything (`capture freeze`)
// while you select with slurp, which opens above. Menus and tooltips stay as they were, and the
// screenshot is cut from the same picture. No input: slurp has the pointer and keyboard.
// `capture thaw` (or two minutes, should the helper die) takes them away.
Scope {
    id: frozen
    property string dir: ''
    property var outputs: []
    readonly property bool active: dir !== ''

    function freeze(path) {
        if (path !== Session.runtimeDir + '/arctic/capture/frozen') return false;
        dir = path;
        info.reload();
        safety.restart();
        return true;
    }
    function thaw() {
        dir = '';
        outputs = [];
        safety.stop();
    }

    FileView {
        id: info
        path: frozen.active ? frozen.dir + '/frozen.json' : ''
        blockLoading: true
        printErrors: false
        onLoaded: {
            try { frozen.outputs = JSON.parse(text()).outputs || []; } catch (e) { frozen.outputs = []; }
        }
    }
    Timer { id: safety; interval: 120000; onTriggered: frozen.thaw() }

    Variants {
        model: Quickshell.screens
        PanelWindow {
            id: layer
            required property var modelData
            readonly property var picture: frozen.outputs.find(o => o.name === modelData.name) || null
            screen: modelData
            visible: frozen.active && picture !== null
            color: 'transparent'
            anchors { top: true; bottom: true; left: true; right: true }
            exclusionMode: ExclusionMode.Ignore
            WlrLayershell.layer: WlrLayer.Overlay
            WlrLayershell.namespace: 'arctic-freeze'
            WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
            mask: Region {}
            Image {
                anchors.fill: parent
                source: layer.picture ? 'file://' + layer.picture.file : ''
                smooth: false
                cache: false
                asynchronous: false
                fillMode: Image.Stretch
            }
        }
    }
}
