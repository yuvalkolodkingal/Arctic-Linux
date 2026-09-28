import QtQuick
import QtQuick.Layouts

// What the bar's "Restart to update" item opens (design Menu card, like the power menu): how
// many updates wait and a button to restart now. Restart and install has focus; Tab moves to
// Later, Enter presses, Esc closes. `arctic-shell-ipc updates toggle` opens it from a key.
Popover {
    id: pop
    layerName: 'arctic-updates'
    placement: 'point'
    scrim: false
    cardColor: Theme.surfaceRaised
    cardRadius: Theme.radiusLg
    shadow: 2
    cardWidth: 340
    cardHeight: column.implicitHeight + 2 * Theme.space4
    focusItem: restartButton

    // Installed, or no longer waiting (a dnf transaction invalidated it): nothing to offer.
    Connections {
        target: UpdateService
        function onReadyChanged() { if (!UpdateService.ready) pop.close(); }
    }

    ColumnLayout {
        id: column
        anchors.fill: parent
        anchors.margins: Theme.space4
        spacing: Theme.space3

        RowLayout {
            spacing: Theme.space3
            Rectangle {
                implicitWidth: 32
                implicitHeight: 32
                radius: Theme.radiusMd
                color: Theme.accentSoft
                Icon { anchors.centerIn: parent; name: 'download'; size: 18; color: Theme.accentText }
            }
            Text {
                Layout.fillWidth: true
                text: 'Updates are ready'
                color: Theme.ink
                font.family: Theme.fontSans
                font.pixelSize: 15
                font.weight: Font.DemiBold
                Accessible.role: Accessible.Heading
            }
        }
        Text {
            Layout.fillWidth: true
            text: UpdateService.detail
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            color: Theme.inkMuted
            font.family: Theme.fontSans
            font.pixelSize: 13
            lineHeight: 1.3
        }
        Text {
            Layout.fillWidth: true
            text: 'Save your work first. Installing takes a few minutes; then the computer restarts once more.'
            wrapMode: Text.WordWrap
            color: Theme.inkSubtle
            font.family: Theme.fontSans
            font.pixelSize: 12
            lineHeight: 1.3
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: Theme.space1
            spacing: Theme.space2
            Item { Layout.fillWidth: true }
            ArcticButton {
                id: laterButton
                text: 'Later'
                variant: 'ghost'
                size: 'sm'
                KeyNavigation.tab: restartButton
                KeyNavigation.backtab: restartButton
                onClicked: pop.close()
            }
            ArcticButton {
                id: restartButton
                text: 'Restart and install'
                iconName: 'restart'
                variant: 'primary'
                size: 'sm'
                KeyNavigation.tab: laterButton
                KeyNavigation.backtab: laterButton
                onClicked: {
                    pop.close();
                    UpdateService.restart();
                }
            }
        }
    }
}
