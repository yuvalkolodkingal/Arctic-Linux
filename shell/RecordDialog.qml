pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io

// "Record the screen" (Super + Alt + R, when nothing is recording): what to record (an area or
// a screen you then click or drag, the window you were in, or this screen) and which sound.
// Enter starts with the choice shown, which is the last one you used
// (~/.local/state/arctic/record.json, written by arctic-record). Keys: ←/→ within a row,
// ↑/↓ or Tab between rows, Enter starts, Esc cancels.
Popover {
    id: dialog
    property string kind: 'area'
    property string audio: 'none'
    property int row: 0
    readonly property var kinds: [{ id: 'area', label: 'Area' }, { id: 'window', label: 'Window' }, { id: 'screen', label: 'Screen' }]
    readonly property var sounds: [{ id: 'none', label: 'No sound' }, { id: 'desktop', label: 'Desktop sound' }, { id: 'mic', label: 'Microphone' }]

    layerName: 'arctic-record'
    placement: 'center'
    cardWidth: 440
    cardHeight: layout.implicitHeight + 2 * Theme.space6
    focusItem: keys
    onOpened: { row = 0; last.reload(); }

    function start() {
        close();
        Quickshell.execDetached(['arctic-record', 'start', kind, '--audio', audio]);
    }
    function step(delta) {
        const list = row === 0 ? kinds : sounds;
        const now = list.findIndex(o => o.id === (row === 0 ? kind : audio));
        const next = list[(now + delta + list.length) % list.length].id;
        if (row === 0) kind = next; else audio = next;
    }

    FileView {
        id: last
        path: Session.home + '/.local/state/arctic/record.json'
        printErrors: false
        onLoaded: {
            let data = {};
            try { data = JSON.parse(text()); } catch (e) { data = {}; }
            if (['area', 'window', 'screen'].indexOf(data.kind) >= 0) dialog.kind = data.kind;
            if (['none', 'desktop', 'mic'].indexOf(data.audio) >= 0) dialog.audio = data.audio;
        }
    }

    // A row of choices: the chosen one is "here" (accent-soft with its edge), like a selected item.
    component Choices: RowLayout {
        id: choices
        property var options: []
        property string value: ''
        property bool active: false
        signal picked(string id)
        spacing: Theme.space2
        Repeater {
            model: choices.options
            Rectangle {
                id: chip
                required property var modelData
                readonly property bool chosen: modelData.id === choices.value
                Layout.fillWidth: true
                implicitHeight: Theme.controlMd
                radius: Theme.radiusMd
                color: chosen ? Theme.accentSoft : chipMouse.containsMouse ? Theme.surfaceSunken : Theme.surfaceRaised
                border.width: 1
                border.color: chosen ? Theme.accentEdge : Theme.lineStrong
                Accessible.role: Accessible.RadioButton
                Accessible.name: modelData.label
                Accessible.checked: chosen
                Text {
                    anchors.centerIn: parent
                    text: chip.modelData.label
                    color: Theme.ink
                    font.family: Theme.fontSans
                    font.pixelSize: 14
                    font.weight: chip.chosen ? Font.DemiBold : Font.Normal
                }
                FocusRing { targetRadius: Theme.radiusMd; shown: chip.chosen && choices.active && keys.activeFocus }
                MouseArea {
                    id: chipMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: choices.picked(chip.modelData.id)
                }
            }
        }
    }

    ColumnLayout {
        id: layout
        anchors.fill: parent
        anchors.margins: Theme.space6
        spacing: Theme.space4

        Item {
            id: keys
            Layout.fillWidth: true
            implicitHeight: title.implicitHeight
            focus: true
            Keys.onPressed: event => {
                switch (event.key) {
                case Qt.Key_Left: dialog.step(-1); break;
                case Qt.Key_Right: dialog.step(1); break;
                case Qt.Key_Up: dialog.row = 0; break;
                case Qt.Key_Down: dialog.row = 1; break;
                case Qt.Key_Tab:
                case Qt.Key_Backtab: dialog.row = 1 - dialog.row; break;
                case Qt.Key_Return:
                case Qt.Key_Enter: dialog.start(); break;
                case Qt.Key_Escape: dialog.close(); break;
                default: return;
                }
                event.accepted = true;
            }
            Text {
                id: title
                text: 'Record the screen'
                color: Theme.ink
                font.family: Theme.fontSans
                font.pixelSize: 20
                font.weight: Font.DemiBold
            }
        }

        Text {
            text: dialog.kind === 'area' ? 'Then click a screen, or drag over an area.'
                : dialog.kind === 'window' ? 'The window you were in, where it is now.' : 'The screen you’re on.'
            color: Theme.inkMuted
            font.family: Theme.fontSans
            font.pixelSize: 13
        }
        Choices {
            Layout.fillWidth: true
            options: dialog.kinds
            value: dialog.kind
            active: dialog.row === 0
            onPicked: id => { dialog.kind = id; dialog.row = 0; }
        }
        Choices {
            Layout.fillWidth: true
            options: dialog.sounds
            value: dialog.audio
            active: dialog.row === 1
            onPicked: id => { dialog.audio = id; dialog.row = 1; }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: Theme.space2
            spacing: Theme.space2
            Text {
                Layout.fillWidth: true
                text: 'Super + Alt + R again stops it.'
                color: Theme.inkSubtle
                font.family: Theme.fontSans
                font.pixelSize: 12
            }
            ArcticButton { variant: 'ghost'; text: 'Cancel'; onClicked: dialog.close() }
            ArcticButton { variant: 'primary'; text: 'Start recording'; onClicked: dialog.start() }
        }
    }
}
