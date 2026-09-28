pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Quickshell
import Quickshell.Io

// Clipboard history (Super + V): what you copied, newest first (cliphist, through
// scripts/clipboard.py). Type to filter; Enter copies it again, Shift + Enter also pastes it
// into the window you were in, Delete removes it. Pictures show a small preview. The layer is
// shielded from screenshots and screencasts (rules.conf), since history can hold passwords.
Popover {
    id: panel
    property var items: []
    property string query: ''
    property int current: 0
    property string error: ''
    property bool loaded: false
    property bool confirmWipe: false
    readonly property string helper: Session.scripts + '/clipboard.py'
    readonly property var filtered: {
        const q = query.trim().toLowerCase();
        if (!q) return items;
        return items.filter(i => i.kind === 'image' ? 'picture image'.indexOf(q) >= 0 || String(i.format).indexOf(q) >= 0
                                                    : String(i.preview).toLowerCase().indexOf(q) >= 0);
    }

    layerName: 'arctic-clipboard'
    focusItem: field
    cardWidth: 520
    cardHeight: Math.min(layout.implicitHeight + 2 * Theme.space3, height - 32)

    onOpened: {
        field.text = '';
        current = 0;
        confirmWipe = false;
        refresh();
    }
    onFilteredChanged: current = Math.min(current, Math.max(0, filtered.length - 1))

    function refresh() { lister.running = true; }
    function run(args, then) {
        const proc = runner.createObject(panel, { command: ['python3', helper].concat(args) });
        proc.done.connect(r => { if (then) then(r); proc.destroy(); });
        proc.running = true;
    }
    function activate(item, paste) {
        if (!item) return;
        close();
        // Detached: pasting waits for this layer to go, so the keys reach your window.
        Quickshell.execDetached(['python3', helper, paste ? 'paste' : 'copy', item.id]);
    }
    function remove(item) {
        if (item) run(['delete', item.id], () => refresh());
    }
    function move(delta) {
        if (!filtered.length) return;
        current = (current + delta + filtered.length) % filtered.length;
        list.positionViewAtIndex(current, ListView.Contain);
    }

    Process {
        id: lister
        command: ['python3', panel.helper, 'list']
        stdout: StdioCollector {
            onStreamFinished: {
                let data = {};
                try { data = JSON.parse(text); } catch (e) { data = { ok: false, error: 'Clipboard history couldn’t be read.' }; }
                panel.items = data.ok ? data.items : [];
                panel.error = data.ok ? '' : data.error;
                panel.loaded = true;
            }
        }
    }
    Component {
        id: runner
        Process {
            id: proc
            signal done(var result)
            stdout: StdioCollector {
                onStreamFinished: {
                    let data = {};
                    try { data = JSON.parse(text); } catch (e) { data = { ok: false }; }
                    proc.done(data);
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
            windowX: panel.card.x
            windowY: panel.card.y
            onMoved: (nextX, nextY) => panel.dock.moveTo(nextX, nextY)
        }

        // Query row, as in the launcher.
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
                Icon { name: 'copy'; size: 20; color: Theme.inkMuted }
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
                    Accessible.name: 'Search clipboard history'
                    onTextChanged: { panel.query = text; panel.current = 0; }
                    Keys.onDownPressed: panel.move(1)
                    Keys.onUpPressed: panel.move(-1)
                    Keys.onTabPressed: panel.move(1)
                    Keys.onBacktabPressed: panel.move(-1)
                    Keys.onEscapePressed: { if (panel.confirmWipe) panel.confirmWipe = false; else if (field.text) field.text = ''; else panel.close(); }
                    Keys.onReturnPressed: event => panel.activate(panel.filtered[panel.current], event.modifiers & Qt.ShiftModifier)
                    Keys.onEnterPressed: event => panel.activate(panel.filtered[panel.current], event.modifiers & Qt.ShiftModifier)
                    Keys.onDeletePressed: event => {
                        if (field.cursorPosition === field.text.length) panel.remove(panel.filtered[panel.current]);
                        else event.accepted = false;
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        visible: !field.text
                        text: 'Search clipboard history'
                        color: Theme.inkSubtle
                        font: field.font
                    }
                }
                Text {
                    visible: panel.loaded && panel.items.length > 0
                    text: panel.filtered.length === 1 ? '1 item' : panel.filtered.length + ' items'
                    color: Theme.inkSubtle
                    font.family: Theme.fontSans
                    font.pixelSize: 12
                    font.weight: Font.Medium
                }
            }
        }

        ListView {
            id: list
            Layout.fillWidth: true
            implicitHeight: Math.min(contentHeight, 7 * 56)
            Layout.preferredHeight: implicitHeight
            visible: count > 0
            clip: true
            spacing: 2
            model: panel.filtered
            currentIndex: panel.current
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: list.contentHeight > list.height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff }
            delegate: Rectangle {
                id: row
                required property var modelData
                required property int index
                readonly property bool selected: index === panel.current
                readonly property bool image: modelData.kind === 'image'
                property string thumb: modelData.thumb || ''
                width: list.width
                height: image ? 64 : 44
                radius: Theme.radiusMd
                color: selected ? Theme.accentSoft : rowMouse.containsMouse ? Theme.surfaceSunken : 'transparent'
                Behavior on color { ColorAnimation { duration: Theme.durationFast } }
                Accessible.role: Accessible.ListItem
                Accessible.name: image ? 'Picture, ' + modelData.width + ' by ' + modelData.height : modelData.preview
                Component.onCompleted: if (image && !thumb) panel.run(['thumb', modelData.id], r => { if (r.ok) row.thumb = r.thumb; })
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.space3
                    anchors.rightMargin: Theme.space3
                    spacing: Theme.space3
                    Rectangle {
                        visible: row.image
                        implicitWidth: 72
                        implicitHeight: 48
                        radius: Theme.radiusSm
                        color: Theme.surfaceSunken
                        border.width: 1
                        border.color: Theme.line
                        clip: true
                        Image {
                            anchors.fill: parent
                            anchors.margins: 1
                            source: row.thumb ? 'file://' + row.thumb : ''
                            fillMode: Image.PreserveAspectFit
                            asynchronous: true
                            cache: false
                        }
                        Icon { anchors.centerIn: parent; visible: !row.thumb; name: 'image'; size: 18; color: Theme.inkMuted }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: row.image ? 'Picture · ' + row.modelData.width + ' × ' + row.modelData.height + ' · ' + row.modelData.size
                                        : row.modelData.preview
                        color: row.image ? Theme.inkMuted : Theme.ink
                        font.family: Theme.fontSans
                        font.pixelSize: 14
                        font.features: { 'tnum': 1 }
                        elide: Text.ElideRight
                        maximumLineCount: 1
                        textFormat: Text.PlainText
                    }
                    Kbd { visible: row.selected; text: 'Enter' }
                }
                MouseArea {
                    id: rowMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onPositionChanged: panel.current = row.index
                    onClicked: mouse => panel.activate(row.modelData, mouse.modifiers & Qt.ShiftModifier)
                }
            }
        }
        Text {
            Layout.fillWidth: true
            Layout.topMargin: Theme.space3
            Layout.bottomMargin: Theme.space3
            visible: panel.loaded && list.count === 0
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            text: panel.error ? panel.error
                : panel.items.length === 0 ? 'Nothing copied yet. What you copy shows up here.'
                : 'Nothing copied matches “' + panel.query.trim() + '”'
            color: Theme.inkMuted
            font.family: Theme.fontSans
            font.pixelSize: 13
        }

        // Clearing asks first, in place (the one destructive action here).
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: Theme.space3
            visible: panel.confirmWipe
            spacing: Theme.space2
            Text {
                Layout.fillWidth: true
                text: 'Clear the whole clipboard history?'
                color: Theme.ink
                font.family: Theme.fontSans
                font.pixelSize: 13
                font.weight: Font.DemiBold
            }
            ArcticButton { size: 'sm'; variant: 'ghost'; text: 'Cancel'; onClicked: { panel.confirmWipe = false; field.forceActiveFocus(); } }
            ArcticButton {
                size: 'sm'
                variant: 'destructive'
                text: 'Clear history'
                onClicked: panel.run(['wipe'], () => { panel.confirmWipe = false; panel.refresh(); field.forceActiveFocus(); })
            }
        }

        // Footer: key hints and Clear.
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.line }
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: Theme.space3
            spacing: Theme.space4
            component Hint: RowLayout {
                id: hint
                property alias keys: keysRow.data
                property string label: ''
                spacing: Theme.space1
                RowLayout { id: keysRow; spacing: Theme.space1 }
                Text { text: hint.label; color: Theme.inkMuted; font.family: Theme.fontSans; font.pixelSize: 12 }
            }
            Hint { label: 'copy'; keys: [ Kbd { text: 'Enter' } ] }
            Hint { label: 'paste'; keys: [ Kbd { text: 'Shift' }, Kbd { text: 'Enter' } ] }
            Hint { label: 'remove'; keys: [ Kbd { text: 'Delete' } ] }
            Item { Layout.fillWidth: true }
            ArcticButton {
                visible: panel.items.length > 0 && !panel.confirmWipe
                size: 'sm'
                variant: 'ghost'
                iconName: 'trash'
                text: 'Clear'
                onClicked: panel.confirmWipe = true
            }
        }
    }
}
