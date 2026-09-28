// One setting: title, why it's there (description), and its control on the right (or under
// the text with `stacked`, for lists and wide controls). `keys` are the Mango options the row
// changes: when settings.conf sets one, the row shows "Changed" and a Reset link; when a later
// file (user.conf) sets it too, it says so, because that file wins. `searchKey` is how the
// search finds and highlights the row.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import "components"

Item {
    id: row
    property string title: ""
    property string desc: ""
    property var keys: []
    property string searchKey: ""
    property bool stacked: false
    property bool resettable: true
    property bool highlighted: false
    property bool compact: false           // lists (the shortcut sheet): 8px instead of 16px
    property bool extraChanged: false      // changed in a way `keys` can't show (the layout)
    default property alias control: slot.data
    signal resetRequested()

    readonly property bool changed: {
        if (extraChanged)
            return true;
        for (let i = 0; i < keys.length; i++)
            if (Backend.info(keys[i]).set)
                return true;
        return false;
    }
    readonly property string overriddenBy: {
        for (let i = 0; i < keys.length; i++) {
            const o = Backend.info(keys[i]);
            if (o.overridden)
                return String(o.origin).split("/").pop();
        }
        return "";
    }
    // The first visible row of its group draws no divider above it.
    readonly property bool isSettingRow: true
    readonly property bool first: {
        const p = parent;
        if (!p)
            return true;
        for (let i = 0; i < p.children.length; i++) {
            const c = p.children[i];
            if (c.isSettingRow === true && c.visible)
                return c === row;
        }
        return true;
    }

    objectName: searchKey
    width: parent ? parent.width : 480
    implicitHeight: body.implicitHeight + 2 * pad + (first ? 0 : 1)
    readonly property int pad: compact ? Theme.space2 : Theme.space4
    Accessible.role: Accessible.Grouping
    Accessible.name: title
    Accessible.description: desc

    Rectangle {
        visible: !row.first
        width: parent.width
        height: 1
        color: Theme.line
    }
    Rectangle {
        anchors.fill: parent
        anchors.topMargin: row.first ? 0 : 1
        radius: row.first ? Theme.radiusLg : 0
        color: Theme.accentSoft
        opacity: row.highlighted ? 1 : 0
        Behavior on opacity {
            NumberAnimation { duration: Theme.fadeSlow }
        }
    }

    GridLayout {
        id: body
        x: Theme.space4
        y: row.pad + (row.first ? 0 : 1)
        width: row.width - 2 * Theme.space4
        columns: row.stacked ? 1 : 2
        columnSpacing: Theme.space6
        rowSpacing: Theme.space3

        Column {
            visible: row.title !== "" || row.desc !== ""
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
            spacing: 2
            Flow {
                width: parent.width
                spacing: Theme.space2
                ArText {
                    text: row.title
                    size: 15
                    lh: 22
                    weight: Font.Medium
                    color: row.enabled ? Theme.ink : Theme.inkDisabled
                }
                Item {
                    visible: row.changed
                    width: tag.width
                    height: 22
                    ArTag {
                        id: tag
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Changed"
                        textSize: 10
                    }
                }
                T.AbstractButton {
                    id: resetLink
                    visible: row.changed && row.resettable
                    implicitWidth: resetText.implicitWidth
                    implicitHeight: 22
                    focusPolicy: Qt.StrongFocus
                    hoverEnabled: true
                    Accessible.role: Accessible.Button
                    Accessible.name: "Reset " + row.title + " to Arctic’s setting"
                    onClicked: row.resetRequested()
                    Keys.onReturnPressed: row.resetRequested()
                    contentItem: ArText {
                        id: resetText
                        text: "Reset"
                        size: 13
                        lh: 22
                        weight: Font.DemiBold
                        color: Theme.accentText
                        font.underline: resetLink.hovered
                    }
                    background: Item {
                        FocusRing {
                            show: resetLink.visualFocus
                            radius: Theme.radiusXs
                            gapColor: Theme.surfaceRaised
                        }
                    }
                }
            }
            ArText {
                visible: row.desc !== ""
                width: parent.width
                text: row.desc
                size: 13
                lh: 18
                wrapMode: Text.WordWrap
                color: row.enabled ? Theme.inkMuted : Theme.inkDisabled
            }
            Row {
                visible: row.overriddenBy !== ""
                spacing: Theme.space1
                topPadding: 2
                Icon {
                    name: "alert"
                    size: 14
                    color: Theme.warning
                    anchors.verticalCenter: parent.verticalCenter
                }
                ArText {
                    text: row.overriddenBy + " sets this too, and that file wins."
                    size: 12
                    lh: 16
                    color: Theme.warning
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
        }
        Item {
            id: slot
            Layout.alignment: row.stacked ? Qt.AlignLeft : (Qt.AlignRight | Qt.AlignVCenter)
            Layout.fillWidth: row.stacked
            implicitWidth: childrenRect.width
            implicitHeight: childrenRect.height
        }
    }
}
