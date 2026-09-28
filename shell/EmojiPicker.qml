pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import "LauncherSearch.js" as LauncherSearch

// Emoji (Super + Ctrl + E): type to search by name or keyword (English, and your language when
// the CLDR keywords are installed); the ones you used last come first. Enter types the emoji
// into the window you were in (wtype, once this card is gone), Shift + Enter copies it, and
// Alt + 1…6 picks the skin tone of the emoji that have one (kept for next time).
// The list is scripts/emoji-index.py, from unicode-emoji's emoji-test.txt.
Popover {
    id: picker
    property var emoji: []
    property var recent: []
    property string query: ''
    property int current: 0
    property int tone: 0                // 0 yellow, 1 light … 5 dark
    property string error: ''
    readonly property int columns: 10
    readonly property string helper: Session.scripts + '/emoji-index.py'
    readonly property var candidates: emoji.map(e => ({ e: tone > 0 && e.tones.length === 5 ? e.tones[tone - 1] : e.e,
                                                        base: e.e, tones: e.tones, name: e.name, keywords: e.keys, group: e.group }))
    readonly property var results: {
        const q = query.trim();
        if (q) return LauncherSearch.rank(candidates, q).slice(0, 300);
        const byChar = {};
        candidates.forEach(c => [c.base].concat(c.tones).forEach(e => byChar[e] = c));
        const first = recent.map(e => byChar[e]).filter((c, i, all) => c && all.indexOf(c) === i);
        return first.concat(candidates.filter(c => first.indexOf(c) < 0));
    }
    readonly property var selected: results[current] || null

    layerName: 'arctic-emoji'
    focusItem: field
    cardWidth: 520
    cardHeight: Math.min(476, height - 32)

    onOpened: {
        field.text = '';
        current = 0;
        loader.running = true;
    }
    onResultsChanged: current = Math.min(current, Math.max(0, results.length - 1))

    function setTone(n) {
        tone = n;
        Quickshell.execDetached(['python3', helper, '--tone', String(n)]);
    }
    function move(delta) {
        if (!results.length) return;
        current = Math.max(0, Math.min(results.length - 1, current + delta));
        grid.positionViewAtIndex(current, GridView.Contain);
    }
    function pick(item, copyOnly) {
        if (!item) return;
        Quickshell.execDetached(['python3', helper, '--used', item.e]);
        close();
        if (copyOnly) {
            // --sensitive: an emoji needn't crowd clipboard history.
            Quickshell.execDetached(['sh', '-c', 'wl-copy --sensitive -- "$1" 2>/dev/null || wl-copy -- "$1"', 'sh', item.e]);
        } else {
            typer.text = item.e;
            typer.restart();
        }
    }

    // Type once this layer has gone, so the keys reach your window; copy when wtype is missing.
    Timer {
        id: typer
        property string text: ''
        interval: 150
        onTriggered: Quickshell.execDetached(['sh', '-c', 'wtype -- "$1" 2>/dev/null || wl-copy -- "$1"', 'sh', text])
    }
    Process {
        id: loader
        command: ['python3', picker.helper]
        stdout: StdioCollector {
            onStreamFinished: {
                let data = {};
                try { data = JSON.parse(text); } catch (e) { data = { ok: false, error: 'The emoji list couldn’t be read.' }; }
                picker.error = data.ok ? '' : data.error;
                if (data.ok) {
                    picker.emoji = data.emoji;
                    picker.recent = data.recent;
                    picker.tone = data.tone || 0;
                }
            }
        }
    }

    ColumnLayout {
        id: layout
        anchors.fill: parent
        anchors.margins: Theme.space3
        spacing: Theme.space2

        DragHandle {
            Layout.fillWidth: true
            Layout.topMargin: -Theme.space3
            Layout.bottomMargin: -Theme.space2
            implicitHeight: Theme.space3
            windowX: picker.card.x
            windowY: picker.card.y
            onMoved: (nextX, nextY) => picker.dock.moveTo(nextX, nextY)
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: Theme.controlLg
            radius: Theme.radiusMd
            color: Theme.surfaceRaised
            border.width: 1
            border.color: Theme.line
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.space3
                anchors.rightMargin: Theme.space3
                spacing: Theme.space3
                Icon { name: 'search'; size: 20; color: Theme.inkMuted }
                TextInput {
                    id: field
                    Layout.fillWidth: true
                    color: Theme.ink
                    font.family: Theme.fontSans
                    font.pixelSize: 17
                    selectionColor: Theme.selection
                    selectedTextColor: Theme.ink
                    cursorDelegate: Rectangle { width: 1.5; color: Theme.accentEdge; visible: field.cursorVisible }
                    clip: true
                    focus: true
                    Accessible.role: Accessible.EditableText
                    Accessible.name: 'Search emoji'
                    onTextChanged: { picker.query = text; picker.current = 0; grid.positionViewAtBeginning(); }
                    Keys.onLeftPressed: picker.move(-1)
                    Keys.onRightPressed: picker.move(1)
                    Keys.onTabPressed: picker.move(1)
                    Keys.onBacktabPressed: picker.move(-1)
                    Keys.onUpPressed: picker.move(-picker.columns)
                    Keys.onDownPressed: picker.move(picker.columns)
                    Keys.onPressed: event => {
                        if (event.key === Qt.Key_PageDown) { picker.move(4 * picker.columns); event.accepted = true; }
                        else if (event.key === Qt.Key_PageUp) { picker.move(-4 * picker.columns); event.accepted = true; }
                        else if ((event.modifiers & Qt.AltModifier) && event.key >= Qt.Key_1 && event.key <= Qt.Key_6) {
                            picker.setTone(event.key - Qt.Key_1);
                            event.accepted = true;
                        }
                    }
                    Keys.onEscapePressed: { if (field.text) field.text = ''; else picker.close(); }
                    Keys.onReturnPressed: event => picker.pick(picker.selected, event.modifiers & Qt.ShiftModifier)
                    Keys.onEnterPressed: event => picker.pick(picker.selected, event.modifiers & Qt.ShiftModifier)
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        visible: !field.text
                        text: 'Search emoji'
                        color: Theme.inkSubtle
                        font: field.font
                    }
                }
            }
        }

        GridView {
            id: grid
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            cellWidth: Math.floor(width / picker.columns)
            cellHeight: cellWidth
            model: picker.results
            currentIndex: picker.current
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: grid.contentHeight > grid.height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff }
            delegate: Rectangle {
                id: cell
                required property var modelData
                required property int index
                readonly property bool selected: index === picker.current
                width: grid.cellWidth - 2
                height: grid.cellHeight - 2
                radius: Theme.radiusMd
                color: selected ? Theme.accentSoft : cellMouse.containsMouse ? Theme.surfaceSunken : 'transparent'
                border.width: selected ? 1 : 0
                border.color: Theme.accentEdge
                Accessible.role: Accessible.ListItem
                Accessible.name: modelData.name
                Text {
                    anchors.centerIn: parent
                    text: cell.modelData.e
                    font.family: 'Noto Color Emoji'
                    font.pixelSize: 26
                    textFormat: Text.PlainText
                }
                MouseArea {
                    id: cellMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onPositionChanged: picker.current = cell.index
                    onClicked: mouse => picker.pick(cell.modelData, mouse.modifiers & Qt.ShiftModifier)
                }
            }
        }
        Text {
            Layout.fillWidth: true
            visible: grid.count === 0
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            text: picker.error || (picker.emoji.length ? 'No emoji match “' + picker.query.trim() + '”' : '')
            color: Theme.inkMuted
            font.family: Theme.fontSans
            font.pixelSize: 13
        }

        // Footer: the selected emoji's name, and key hints.
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.line }
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: Theme.space3
            Layout.rightMargin: Theme.space3
            spacing: Theme.space4
            component Hint: RowLayout {
                id: hint
                property alias keys: keysRow.data
                property string label: ''
                spacing: Theme.space1
                RowLayout { id: keysRow; spacing: Theme.space1 }
                Text { text: hint.label; color: Theme.inkMuted; font.family: Theme.fontSans; font.pixelSize: 12 }
            }
            Text {
                Layout.fillWidth: true
                text: picker.selected ? picker.selected.name : ''
                color: Theme.ink
                font.family: Theme.fontSans
                font.pixelSize: 13
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }
            Hint { label: 'type'; keys: [ Kbd { text: 'Enter' } ] }
            Hint { label: 'copy'; keys: [ Kbd { text: 'Shift' }, Kbd { text: 'Enter' } ] }
            Hint { label: 'skin tone'; keys: [ Kbd { text: 'Alt' }, Kbd { text: '1…6' } ] }
        }
    }
}
