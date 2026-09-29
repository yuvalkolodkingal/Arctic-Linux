import QtQuick
import QtQuick.Layouts
import ".."

// One app in a Get apps list (56 high): its tile (the AppStream or web-app icon, else a glyph),
// name and summary, a Verified chip, and on the right its state — Install (primary only on the
// selected row, with Enter), Installed with Open, waiting, or a progress bar. Remove apps uses
// the same row with `removable` (Remove… and Delete) or a lock and the reason.
Rectangle {
    id: row
    property string name: ''
    property string summary: ''
    property string iconName: ''
    property string imageSource: ''
    property string glyph: 'package'
    property string tileId: ''
    property bool verified: false
    property string state_: 'install'              // install | installed | waiting | running | failed | removable | locked | busy
    property var percent: null
    property bool selected: false
    property string actionText: 'Install'
    property string reason: ''                     // locked rows: why
    property bool canOpen: true                    // installed rows: it has a launcher entry
    signal activated()                             // the row's button (Install, Open, Remove…)
    signal clicked()                               // the row body (details)
    signal hovered()

    implicitHeight: 56
    radius: Theme.radiusMd
    color: selected ? Theme.accentSoft : mouse.containsMouse ? Theme.surfaceSunken : 'transparent'
    border.width: selected ? 1 : 0
    border.color: Theme.accentEdge
    Behavior on color { ColorAnimation { duration: Theme.durationFast } }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        cursorShape: Qt.PointingHandCursor
        onPositionChanged: row.hovered()
        onClicked: row.clicked()
    }
    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.space3
        anchors.rightMargin: Theme.space3
        spacing: Theme.space3
        AppTile {
            size: 40
            tileId: row.tileId
            iconName: row.iconName
            imageSource: row.imageSource
            fallbackGlyph: row.glyph
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 0
            Text {
                Layout.fillWidth: true
                text: row.name
                textFormat: Text.PlainText
                color: Theme.ink
                font.family: Theme.fontSans
                font.pixelSize: 15
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }
            Text {
                Layout.fillWidth: true
                visible: text !== ''
                text: row.state_ === 'locked' && row.reason ? row.reason : row.summary
                textFormat: Text.PlainText
                color: Theme.inkMuted
                font.family: Theme.fontSans
                font.pixelSize: 12
                elide: Text.ElideRight
            }
        }
        RowLayout {
            visible: row.verified
            spacing: Theme.space1
            Icon { name: 'shield-check'; size: 14; color: Theme.info }
            Text { text: 'Verified'; color: Theme.info; font.family: Theme.fontSans; font.pixelSize: 12; font.weight: Font.Medium }
        }
        // State, on the right.
        RowLayout {
            visible: row.state_ === 'installed'
            spacing: Theme.space2
            Icon { name: 'check-circle'; size: 16; color: Theme.success }
            Text { text: 'Installed'; color: Theme.success; font.family: Theme.fontSans; font.pixelSize: 12; font.weight: Font.Medium }
            ArcticButton { visible: row.canOpen; variant: 'ghost'; size: 'sm'; text: 'Open'; focusPolicy: Qt.NoFocus; onClicked: row.activated() }
        }
        RowLayout {
            visible: row.state_ === 'waiting'
            spacing: Theme.space1
            Icon { name: 'clock'; size: 16; color: Theme.inkMuted }
            Text { text: 'Waiting'; color: Theme.inkMuted; font.family: Theme.fontSans; font.pixelSize: 12 }
        }
        RowLayout {
            visible: row.state_ === 'running' || row.state_ === 'busy'
            spacing: Theme.space2
            Rectangle {
                implicitWidth: 72
                implicitHeight: 4
                radius: 2
                color: Theme.surfaceSunken
                Rectangle {
                    width: parent.width * Math.max(0.08, Math.min(1, (row.percent || 0) / 100))
                    height: parent.height
                    radius: 2
                    color: Theme.accent
                }
            }
            Text {
                text: row.state_ === 'busy' ? 'Removing…' : row.percent !== null && row.percent !== undefined ? row.percent + '%' : 'Starting…'
                color: Theme.inkMuted
                font.family: Theme.fontSans
                font.pixelSize: 12
                font.features: { 'tnum': 1 }
            }
        }
        RowLayout {
            visible: row.state_ === 'failed'
            spacing: Theme.space1
            Icon { name: 'x-circle'; size: 16; color: Theme.error }
            Text { text: 'Didn’t work'; color: Theme.error; font.family: Theme.fontSans; font.pixelSize: 12 }
        }
        Icon { visible: row.state_ === 'locked'; name: 'lock'; size: 16; color: Theme.inkMuted }
        Kbd { visible: row.selected && (row.state_ === 'install' || row.state_ === 'failed'); text: 'Enter' }
        Kbd { visible: row.selected && row.state_ === 'removable'; text: 'Delete' }
        ArcticButton {
            visible: row.state_ === 'install' || row.state_ === 'failed' || row.state_ === 'removable'
            variant: row.selected && row.state_ !== 'removable' ? 'primary' : 'secondary'
            size: 'sm'
            text: row.state_ === 'failed' ? 'Try again' : row.actionText
            focusPolicy: Qt.NoFocus
            onClicked: row.activated()
        }
    }
}
