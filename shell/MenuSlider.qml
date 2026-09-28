import QtQuick
import QtQuick.Layouts

// A volume or brightness row in a bar menu: an icon button (mute), the slider, the value in
// tabular figures and an optional chevron to the device page. The row is one stop: ←/→ change
// the value by 5 %, Space mutes, Enter opens the page (when there is one).
FocusScope {
    id: row
    property string icon: 'volume'
    property string mutedIcon: 'volume-mute'
    property string image: ''
    property real value: 0              // 0…1
    property bool muted: false
    property bool canMute: true
    property string label: ''           // accessible name ("Speakers volume")
    property string caption: ''         // an optional line above the slider (an app's name)
    property bool showChevron: false
    readonly property bool menuStop: true
    signal moved(real value)
    signal muteToggled()
    signal opened()

    Layout.fillWidth: true
    implicitHeight: layout.implicitHeight + 2 * 4
    Accessible.role: Accessible.Slider
    Accessible.name: label

    Keys.onPressed: event => {
        MenuState.keyboardNav = true;
        if (event.key === Qt.Key_Space && row.canMute) row.muteToggled();
        else if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && row.showChevron) row.opened();
        else return;
        event.accepted = true;
    }

    ColumnLayout {
        id: layout
        anchors.fill: parent
        anchors.topMargin: 4
        anchors.bottomMargin: 4
        anchors.leftMargin: Theme.space1
        anchors.rightMargin: Theme.space1
        spacing: 0
        Text {
            visible: row.caption !== ''
            Layout.fillWidth: true
            Layout.leftMargin: Theme.space2
            text: row.caption
            elide: Text.ElideRight
            color: Theme.inkMuted
            font.family: Theme.fontSans
            font.pixelSize: 12
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space1
            Rectangle {
                implicitWidth: 30
                implicitHeight: 30
                radius: Theme.radiusSm
                color: muteMouse.containsMouse && row.canMute ? Theme.surfaceSunken : 'transparent'
                Icon {
                    anchors.centerIn: parent
                    visible: row.image === ''
                    name: row.muted ? row.mutedIcon : row.icon
                    size: 18
                    color: row.muted ? Theme.inkMuted : Theme.ink
                }
                Image {
                    anchors.centerIn: parent
                    visible: row.image !== ''
                    width: 18
                    height: 18
                    source: row.image
                    sourceSize: Qt.size(18, 18)
                    fillMode: Image.PreserveAspectFit
                    opacity: row.muted ? 0.5 : 1
                }
                MouseArea {
                    id: muteMouse
                    anchors.fill: parent
                    enabled: row.canMute
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: row.muteToggled()
                }
                Accessible.role: Accessible.Button
                Accessible.name: row.muted ? 'Unmute' : 'Mute'
            }
            ArcticSlider {
                id: slider
                Layout.fillWidth: true
                focus: true
                from: 0
                to: 1
                stepSize: 0.05
                showFocus: row.activeFocus && MenuState.keyboardNav
                accessibleName: row.label
                valueText: Math.round(row.value * 100) + ' %'
                onMoved: row.moved(value)
                Binding on value { value: row.muted || !isFinite(row.value) ? 0 : Math.min(1, row.value); when: !slider.pressed; restoreMode: Binding.RestoreNone }
            }
            Text {
                Layout.preferredWidth: 40
                horizontalAlignment: Text.AlignRight
                text: row.muted ? 'Off' : isFinite(row.value) ? Math.round(row.value * 100) + ' %' : ''
                color: Theme.inkMuted
                font.family: Theme.fontSans
                font.pixelSize: 13
                font.features: { 'tnum': 1 }
            }
            Rectangle {
                visible: row.showChevron
                implicitWidth: 26
                implicitHeight: 26
                radius: Theme.radiusSm
                color: chevronMouse.containsMouse ? Theme.surfaceSunken : 'transparent'
                Icon { anchors.centerIn: parent; name: 'chevron-right'; size: 16; color: Theme.inkMuted }
                MouseArea {
                    id: chevronMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: row.opened()
                }
                Accessible.role: Accessible.Button
                Accessible.name: 'More'
            }
        }
    }
}
