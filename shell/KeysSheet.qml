pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Quickshell
import Quickshell.Io

// Keyboard shortcuts (Super + /): the cheat sheet from keys.txt, in a centred card.
// keys.txt is found in ~/.local/share/arctic, then /usr/share/arctic.
Popover {
    id: sheet
    property var sections: []
    layerName: 'arctic-keys'
    placement: 'center'
    cardWidth: Math.min(820, width - 48)
    cardHeight: Math.min(layout.implicitHeight + 2 * Theme.space6, height - 48)
    focusItem: flick

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
        onLoadFailed: if (candidate + 1 < paths.length) candidate++
    }

    ColumnLayout {
        id: layout
        anchors.fill: parent
        anchors.margins: Theme.space6
        spacing: Theme.space4
        RowLayout {
            Layout.fillWidth: true
            Text { text: 'Keyboard shortcuts'; color: Theme.ink; font.family: Theme.fontSans; font.pixelSize: 20; font.weight: Font.DemiBold; Layout.fillWidth: true }
            ArcticButton { variant: 'ghost'; size: 'sm'; iconName: 'x'; iconOnly: true; label: 'Close  (Esc)'; onClicked: sheet.close() }
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
                    model: sheet.sections
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
