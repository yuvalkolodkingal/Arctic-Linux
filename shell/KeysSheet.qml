pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Quickshell
import Quickshell.Io

// Keyboard shortcuts (Super + /): the cheat sheet from keys.txt, in a centred card. Type to
// find a shortcut by its keys or what it does; ↑/↓ scroll, Esc clears, then closes.
// keys.txt is found in ~/.local/share/arctic, then /usr/share/arctic.
Popover {
    id: sheet
    property var sections: []
    property string query: ''
    readonly property var matched: {
        const q = query.trim().toLowerCase();
        if (!q) return sections;
        return sections.map(s => ({ title: s.title, rows: s.rows.filter(r => (r.keys + ' ' + r.what).toLowerCase().indexOf(q) >= 0) }))
            .filter(s => s.rows.length > 0);
    }
    layerName: 'arctic-keys'
    placement: 'center'
    cardWidth: Math.min(820, width - 48)
    cardHeight: Math.min(760, height - 48)
    focusItem: field
    onOpened: field.text = ''

    function parse(text) {
        const out = [];
        text.split('\n').forEach(line => {
            if (!line.trim()) return;
            const entry = /^ {4}(\S.*?)\s{2,}(\S.*)$/.exec(line);
            if (entry && out.length) { out[out.length - 1].rows.push({ keys: entry[1], what: entry[2] }); return; }
            const heading = /^ {2}(\S.*?)(\s{2,}.*)?$/.exec(line);
            if (heading && !/Keyboard shortcuts/.test(line)) out.push({ title: heading[1], rows: [] });
        });
        sections = out;
    }
    FileView {
        id: file
        property int candidate: 0
        readonly property var paths: [Session.dataHome + '/arctic/keys.txt', '/usr/share/arctic/keys.txt']
        path: paths[candidate]
        printErrors: false
        onLoaded: sheet.parse(text())
        // FileView drops its in-flight operation only after this signal returns, so moving on
        // to the next path from inside the handler leaves that read unowned: its result is
        // discarded ("operation finished from dropped operation") and the sheet stays empty.
        // Wait for the event loop instead, as `loadFailed` on a read that never started would.
        onLoadFailed: if (candidate + 1 < paths.length) Qt.callLater(function() { candidate++ })
    }

    ColumnLayout {
        id: layout
        anchors.fill: parent
        anchors.margins: Theme.space6
        spacing: Theme.space4
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space4
            Text { text: 'Keyboard shortcuts'; color: Theme.ink; font.family: Theme.fontSans; font.pixelSize: 20; font.weight: Font.DemiBold }
            // Find a shortcut: 36px search field, as small as the design's inputs.
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: Theme.controlMd
                radius: Theme.radiusMd
                color: Theme.surfaceRaised
                border.width: field.activeFocus ? 2 : 1
                border.color: field.activeFocus ? Theme.focus : Theme.lineStrong
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.space3
                    anchors.rightMargin: Theme.space3
                    spacing: Theme.space2
                    Icon { name: 'search'; size: 16; color: Theme.inkMuted }
                    TextInput {
                        id: field
                        Layout.fillWidth: true
                        color: Theme.ink
                        font.family: Theme.fontSans
                        font.pixelSize: 14
                        selectionColor: Theme.selection
                        selectedTextColor: Theme.ink
                        clip: true
                        focus: true
                        Accessible.role: Accessible.EditableText
                        Accessible.name: 'Find a shortcut'
                        onTextChanged: { sheet.query = text; flick.contentY = 0; }
                        Keys.onEscapePressed: { if (field.text) field.text = ''; else sheet.close(); }
                        Keys.onDownPressed: flick.contentY = Math.max(0, Math.min(flick.contentHeight - flick.height, flick.contentY + 40))
                        Keys.onUpPressed: flick.contentY = Math.max(0, flick.contentY - 40)
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            visible: !field.text
                            text: 'Find a shortcut'
                            color: Theme.inkSubtle
                            font: field.font
                        }
                    }
                }
            }
            ArcticButton { variant: 'ghost'; size: 'sm'; iconName: 'x'; iconOnly: true; label: 'Close  (Esc)'; onClicked: sheet.close() }
        }
        Text {
            Layout.fillWidth: true
            visible: sheet.query.trim() !== '' && sheet.matched.length === 0
            text: 'No shortcut matches “' + sheet.query.trim() + '”'
            color: Theme.inkMuted
            font.family: Theme.fontSans
            font.pixelSize: 13
        }
        Flickable {
            id: flick
            Layout.fillWidth: true
            Layout.fillHeight: true
            implicitHeight: grid.implicitHeight
            contentHeight: grid.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}
            Keys.onEscapePressed: sheet.close()
            Keys.onDownPressed: contentY = Math.min(contentHeight - height, contentY + 40)
            Keys.onUpPressed: contentY = Math.max(0, contentY - 40)
            GridLayout {
                id: grid
                width: flick.width
                columns: flick.width > 640 ? 2 : 1
                columnSpacing: Theme.space8
                rowSpacing: Theme.space5
                Repeater {
                    model: sheet.matched
                    ColumnLayout {
                        id: section
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignTop
                        spacing: Theme.space1
                        Text {
                            text: section.modelData.title.toUpperCase()
                            color: Theme.inkMuted
                            font.family: Theme.fontSans
                            font.pixelSize: 11
                            font.weight: Font.DemiBold
                            font.letterSpacing: 0.88
                            Layout.bottomMargin: 2
                        }
                        Repeater {
                            model: section.modelData.rows
                            RowLayout {
                                id: entry
                                required property var modelData
                                Layout.fillWidth: true
                                spacing: Theme.space3
                                Text {
                                    Layout.preferredWidth: 176
                                    text: entry.modelData.keys
                                    color: Theme.ink
                                    font.family: Theme.fontMono
                                    font.pixelSize: 12
                                    font.weight: Font.Bold
                                    elide: Text.ElideRight
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: entry.modelData.what
                                    color: Theme.inkMuted
                                    font.family: Theme.fontSans
                                    font.pixelSize: 13
                                    wrapMode: Text.Wrap
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
