pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "NotificationRules.js" as Rules

// One notification's content, in a toast (ToastCard.qml) and in the centre
// (NotificationCenter.qml): its picture (36px), the app and "Urgent" line with the time, the
// summary (15/600), the body as plain text, an OSD-style bar for a `value` hint and up to three
// action buttons. The default action is the click on the whole card, not a button.
Item {
    id: card
    required property var entry
    property bool showApp: true         // the centre groups by app, so its cards leave it out
    property int maxLines: 3
    property bool expanded: false
    property bool showTime: true        // the toast's close button takes its place on hover
    property int currentAction: -1      // keyboard: the action button that has the highlight
    property bool keyboardNav: false
    readonly property var actions: entry ? entry.actions.slice(0, 3) : []
    readonly property string picture: NotificationService.imageFor(entry) || (showApp ? NotificationService.appIconFor(entry) : '')
    readonly property bool urgent: entry !== null && entry.urgency === 'critical'
    readonly property string when: entry ? Rules.relativeTime(entry.time, Math.floor(NotificationService.now), new Date(NotificationService.now * 1000)) : ''
    signal actionInvoked(string identifier)

    implicitWidth: 340
    implicitHeight: row.implicitHeight

    RowLayout {
        id: row
        width: parent.width
        spacing: Theme.space3

        // The picture: a sender's image, the app's icon, or the bell on a quiet tile.
        Rectangle {
            Layout.alignment: Qt.AlignTop
            visible: card.showApp || card.picture !== ''
            implicitWidth: 36
            implicitHeight: 36
            radius: Theme.radiusMd
            color: picture.status === Image.Ready ? 'transparent' : Theme.surfaceSunken
            RoundedImage {
                id: picture
                anchors.fill: parent
                radius: Theme.radiusMd
                source: card.picture
                sourceSize: Qt.size(72, 72)
                fillMode: Image.PreserveAspectCrop
                visible: status === Image.Ready
            }
            Icon {
                anchors.centerIn: parent
                visible: picture.status !== Image.Ready
                name: 'bell'
                size: 18
                color: Theme.inkMuted
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            // The app (toasts) and "Urgent" with the time; in the centre the time sits beside the
            // summary unless the notification is urgent.
            RowLayout {
                id: header
                Layout.fillWidth: true
                visible: card.showApp || card.urgent
                spacing: Theme.space1
                Text {
                    visible: card.showApp
                    Layout.fillWidth: true
                    text: NotificationService.appNameFor(card.entry)
                    elide: Text.ElideRight
                    color: Theme.inkMuted
                    font.family: Theme.fontSans
                    font.pixelSize: 12
                    font.weight: Font.Medium
                }
                // Urgent: the word, never the colour alone (the toast adds its red edge).
                Text {
                    visible: card.urgent
                    Layout.fillWidth: !card.showApp
                    text: (card.showApp ? '· ' : '') + 'Urgent'
                    color: Theme.error
                    font.family: Theme.fontSans
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                }
                Text {
                    opacity: card.showTime ? 1 : 0
                    text: card.when
                    color: Theme.inkSubtle
                    font.family: Theme.fontSans
                    font.pixelSize: 12
                    font.features: { 'tnum': 1 }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space2
                Text {
                    Layout.fillWidth: true
                    visible: text !== ''
                    text: card.entry ? card.entry.summary : ''
                    textFormat: Text.PlainText
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                    color: Theme.ink
                    font.family: Theme.fontSans
                    font.pixelSize: 15
                    font.weight: Font.DemiBold
                }
                Text {
                    Layout.alignment: Qt.AlignTop
                    Layout.topMargin: 2
                    visible: !header.visible
                    opacity: card.showTime ? 1 : 0
                    text: card.when
                    color: Theme.inkSubtle
                    font.family: Theme.fontSans
                    font.pixelSize: 12
                    font.features: { 'tnum': 1 }
                }
            }
            Text {
                id: body
                Layout.fillWidth: true
                visible: text !== ''
                text: card.entry ? card.entry.body : ''
                textFormat: Text.PlainText
                wrapMode: Text.Wrap
                maximumLineCount: card.expanded ? 12 : card.maxLines
                elide: Text.ElideRight
                color: Theme.inkMuted
                font.family: Theme.fontSans
                font.pixelSize: 13
                lineHeight: 1.2
            }
            // A progress or level hint (e.g. a volume change from a program without the OSD).
            Rectangle {
                Layout.fillWidth: true
                Layout.topMargin: Theme.space1
                visible: card.entry !== null && card.entry.value >= 0
                implicitHeight: 6
                radius: 3
                color: Theme.surfaceSunken
                border.width: 1
                border.color: Theme.line
                Rectangle {
                    width: parent.width * (card.entry ? Math.max(0, card.entry.value) : 0) / 100
                    height: parent.height
                    radius: 3
                    color: Theme.accent
                    visible: width > 0
                }
            }
            Flow {
                Layout.fillWidth: true
                Layout.topMargin: Theme.space2
                visible: card.actions.length > 0
                spacing: Theme.space2
                Repeater {
                    model: card.actions
                    ArcticButton {
                        id: actionButton
                        required property var modelData
                        required property int index
                        text: modelData.text || modelData.identifier
                        size: 'sm'
                        variant: 'secondary'
                        focusPolicy: Qt.NoFocus
                        FocusRing { targetRadius: Theme.radiusMd; shown: card.keyboardNav && card.currentAction === actionButton.index }
                        onClicked: card.actionInvoked(modelData.identifier)
                    }
                }
            }
        }
    }
}
