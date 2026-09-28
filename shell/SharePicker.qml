pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import "assets/Icons.js" as Icons

// "Share your screen": when an app asks to share the screen, xdg-desktop-portal-wlr runs
// /usr/libexec/arctic/arctic-share-picker, which opens this card (`share pick <fifo>`) and waits
// on the FIFO. Every monitor and window is listed (arctic-capture sources); Share writes the
// portal's answer ("Monitor: eDP-1" / "Window: <id>"), and Cancel, Esc or another popover an
// empty line, which shares nothing.
Popover {
    id: picker
    property string reply: ''
    property var sources: []
    property int current: 0
    property bool loaded: false
    readonly property var selected: sources[current] || null

    layerName: 'arctic-share'
    placement: 'center'
    cardWidth: 520
    cardHeight: Math.min(layout.implicitHeight + 2 * Theme.space6, height - 48)
    focusItem: list

    // Only a FIFO in our own runtime folder, which arctic-share-picker made.
    function start(fifo) {
        if (!/^\/[^\n]*$/.test(fifo) || fifo.indexOf(Session.runtimeDir + '/arctic/share-') !== 0 || fifo.indexOf('..') >= 0)
            return false;
        answer('');         // an older request still waiting gets "nothing"
        reply = fifo;
        sources = [];
        current = 0;
        loaded = false;
        lister.running = true;
        return true;
    }
    function answer(value) {
        if (!reply) return;
        // timeout: a picker that gave up must not keep this writer waiting.
        Quickshell.execDetached(['timeout', '2', 'sh', '-c', 'printf "%s\\n" "$1" > "$2"', 'sh', value, reply]);
        reply = '';
    }
    function share() {
        if (!selected) return;
        answer(selected.value);
        close();
    }
    function move(delta) {
        if (!sources.length) return;
        current = (current + delta + sources.length) % sources.length;
        list.positionViewAtIndex(current, ListView.Contain);
    }
    onOpenChanged: if (!open) answer('')

    Process {
        id: lister
        command: ['arctic-capture', 'sources', '--json']
        stdout: StdioCollector {
            onStreamFinished: {
                let data = {};
                try { data = JSON.parse(text); } catch (e) { data = {}; }
                picker.sources = data.ok ? data.sources : [];
                picker.loaded = true;
            }
        }
    }

    ColumnLayout {
        id: layout
        anchors.fill: parent
        anchors.margins: Theme.space6
        spacing: Theme.space4

        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.space1
            Text { text: 'Share your screen'; color: Theme.ink; font.family: Theme.fontSans; font.pixelSize: 20; font.weight: Font.DemiBold }
            Text {
                Layout.fillWidth: true
                text: 'An app asked to share your screen. Pick what it can see.'
                color: Theme.inkMuted
                font.family: Theme.fontSans
                font.pixelSize: 14
                wrapMode: Text.Wrap
            }
        }

        ListView {
            id: list
            Layout.fillWidth: true
            implicitHeight: Math.min(contentHeight, 7 * 54)
            Layout.preferredHeight: implicitHeight
            visible: count > 0
            clip: true
            spacing: 2
            focus: true
            model: picker.sources
            currentIndex: picker.current
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: list.contentHeight > list.height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff }
            Keys.onDownPressed: picker.move(1)
            Keys.onUpPressed: picker.move(-1)
            Keys.onTabPressed: picker.move(1)
            Keys.onBacktabPressed: picker.move(-1)
            Keys.onReturnPressed: picker.share()
            Keys.onEnterPressed: picker.share()
            Keys.onEscapePressed: picker.close()
            delegate: Rectangle {
                id: row
                required property var modelData
                required property int index
                readonly property bool selected: index === picker.current
                width: list.width
                height: 52
                radius: Theme.radiusMd
                color: selected ? Theme.accentSoft : rowMouse.containsMouse ? Theme.surfaceSunken : 'transparent'
                Accessible.role: Accessible.ListItem
                Accessible.name: modelData.label
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.space3
                    anchors.rightMargin: Theme.space3
                    spacing: Theme.space3
                    AppTile {
                        size: 36
                        tileId: row.modelData.kind === 'window' ? Icons.tileFor(row.modelData.app_id, row.modelData.app_id) : ''
                        iconName: row.modelData.app_id
                        fallbackGlyph: row.modelData.kind === 'screen' ? 'image' : 'grid'
                    }
                    Text {
                        Layout.fillWidth: true
                        text: row.modelData.label
                        color: Theme.ink
                        font.family: Theme.fontSans
                        font.pixelSize: 15
                        font.weight: row.modelData.kind === 'screen' ? Font.DemiBold : Font.Normal
                        elide: Text.ElideRight
                        textFormat: Text.PlainText
                    }
                }
                MouseArea {
                    id: rowMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onPositionChanged: picker.current = row.index
                    onClicked: picker.current = row.index
                    onDoubleClicked: picker.share()
                }
            }
        }
        Text {
            Layout.fillWidth: true
            visible: picker.loaded && picker.sources.length === 0
            text: 'Arctic couldn’t list your screens (is this a Mango session?).'
            color: Theme.inkMuted
            font.family: Theme.fontSans
            font.pixelSize: 13
            wrapMode: Text.Wrap
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space2
            Item { Layout.fillWidth: true }
            ArcticButton { variant: 'ghost'; text: 'Cancel'; onClicked: picker.close() }
            ArcticButton { variant: 'primary'; text: 'Share'; enabled: picker.selected !== null; onClicked: picker.share() }
        }
    }
}
