// .ar-field + .ar-input — label, 36px box (lg 44) with optional leading icon,
// password reveal, trailing icon, strength meter, help / error / success line.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Templates as T
import ".."

Column {
    id: field
    property string label: ""
    property alias text: input.text
    property string placeholder: ""
    property string iconName: ""
    property bool password: false
    property bool revealed: false
    property string help: ""
    property string error: ""          // non-empty: error state + message
    property string success: ""        // non-empty: success message (e.g. "Matches")
    property string trailingIcon: ""   // e.g. "check"
    property color trailingColor: Theme.success
    property int meterLevel: -1        // 0-4 shows ArMeter
    property string meterLabel: ""
    property string size: "md"
    property bool readOnly: false
    property int maximumLength: 256
    property alias input: input
    property string accessibleName: label
    readonly property bool hasError: error !== ""

    signal accepted()
    signal edited()

    spacing: Theme.space1
    width: 320

    function forceActiveFocus() {
        input.forceActiveFocus();
    }

    ArText {
        visible: field.label !== ""
        text: field.label
        size: 13
        lh: 18
        weight: Font.Medium
        color: field.enabled ? Theme.ink : Theme.inkDisabled
    }

    Rectangle {
        id: box
        width: parent.width
        height: field.size === "lg" ? Theme.controlLg : Theme.controlMd
        radius: Theme.radiusMd
        antialiasing: true
        color: field.enabled ? Theme.surfaceRaised : Theme.surfaceSunken
        readonly property bool focused: input.activeFocus
        border.width: (focused || field.hasError) ? 2 : 1
        border.color: !field.enabled ? Theme.line : field.hasError ? Theme.error : focused ? Theme.focus : hover.hovered ? Theme.inkMuted : Theme.lineStrong
        Behavior on border.color {
            ColorAnimation { duration: Theme.durationFast }
        }
        HoverHandler {
            id: hover
            cursorShape: Qt.IBeamCursor
        }
        TapHandler {
            onTapped: input.forceActiveFocus()
        }

        Row {
            id: lead
            x: Theme.space3
            anchors.verticalCenter: parent.verticalCenter
            spacing: Theme.space2
            Icon {
                visible: field.iconName !== ""
                name: field.iconName || "help"
                size: 18
                color: field.enabled ? Theme.inkMuted : Theme.inkDisabled
            }
        }

        // Templates draw no placeholder; show it ourselves.
        Text {
            visible: input.text === "" && input.preeditText === ""
            anchors.left: input.left
            anchors.right: input.right
            anchors.verticalCenter: parent.verticalCenter
            text: field.placeholder
            color: field.enabled ? Theme.inkSubtle : Theme.inkDisabled
            font: input.font
            elide: Text.ElideRight
            Accessible.ignored: true
        }

        T.TextField {
            id: input
            anchors.left: parent.left
            anchors.leftMargin: Theme.space3 + (field.iconName !== "" ? 18 + Theme.space2 : 0)
            anchors.right: trail.left
            anchors.rightMargin: Theme.space2
            anchors.verticalCenter: parent.verticalCenter
            height: parent.height - 4
            leftPadding: 0
            rightPadding: 0
            topPadding: 0
            bottomPadding: 0
            verticalAlignment: TextInput.AlignVCenter
            color: field.enabled ? Theme.ink : Theme.inkDisabled
            placeholderText: field.placeholder
            placeholderTextColor: field.enabled ? Theme.inkSubtle : Theme.inkDisabled
            selectionColor: Theme.selection
            selectedTextColor: Theme.ink
            font.family: Theme.fontSans
            // .ar-dots: 18px bullets, .15em apart
            readonly property bool dots: field.password && !field.revealed && text.length > 0
            font.pixelSize: dots ? 18 : (field.size === "lg" ? 16 : 15)
            font.letterSpacing: dots ? 2.7 : 0
            echoMode: (field.password && !field.revealed) ? TextInput.Password : TextInput.Normal
            passwordCharacter: "•"
            readOnly: field.readOnly
            enabled: field.enabled
            maximumLength: field.maximumLength
            selectByMouse: true
            inputMethodHints: field.password ? (Qt.ImhSensitiveData | Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase) : Qt.ImhNone
            Accessible.role: Accessible.EditableText
            Accessible.name: field.accessibleName
            Accessible.description: field.hasError ? field.error : (field.success || field.help)
            Accessible.passwordEdit: field.password && !field.revealed
            onAccepted: field.accepted()
            onTextEdited: field.edited()
            cursorDelegate: Rectangle {
                width: 1.5
                color: Theme.accentEdge
                visible: input.cursorVisible
            }
        }

        Row {
            id: trail
            anchors.right: parent.right
            // the eye glyph lands 12px from the edge, like the mockup's inline icon
            anchors.rightMargin: field.password ? 7 : Theme.space3
            anchors.verticalCenter: parent.verticalCenter
            spacing: field.password ? 3 : Theme.space2
            Icon {
                visible: field.trailingIcon !== ""
                name: field.trailingIcon || "check"
                size: 18
                color: field.trailingColor
                anchors.verticalCenter: parent.verticalCenter
            }
            // Password reveal: a real button so it works from the keyboard too.
            T.AbstractButton {
                id: reveal
                visible: field.password
                width: 28
                height: 28
                anchors.verticalCenter: parent.verticalCenter
                focusPolicy: Qt.StrongFocus
                hoverEnabled: true
                Accessible.role: Accessible.Button
                Accessible.name: field.revealed ? "Hide" : "Show"
                onClicked: field.revealed = !field.revealed
                background: Rectangle {
                    radius: Theme.radiusSm
                    color: reveal.hovered ? Theme.surfaceSunken : "transparent"
                    FocusRing {
                        show: reveal.visualFocus
                        radius: Theme.radiusSm
                        gapColor: Theme.surfaceRaised
                    }
                }
                contentItem: Item {
                    Icon {
                        anchors.centerIn: parent
                        name: field.revealed ? "eye-off" : "eye"
                        size: 18
                        color: Theme.inkMuted
                    }
                }
            }
        }
    }

    ArMeter {
        visible: field.meterLevel >= 0
        width: parent.width
        level: Math.max(0, field.meterLevel)
        label: field.meterLabel
    }

    Row {
        id: helpRow
        visible: helpText.text !== ""
        width: parent.width
        spacing: Theme.space1
        Icon {
            visible: field.hasError
            name: "alert"
            size: 16
            color: Theme.error
            y: 1
        }
        ArText {
            id: helpText
            width: parent.width - (field.hasError ? 16 + Theme.space1 : 0)
            text: field.hasError ? field.error : (field.success !== "" ? field.success : field.help)
            size: 13
            lh: 18
            wrapMode: Text.WordWrap
            color: field.hasError ? Theme.error : field.success !== "" ? Theme.success : Theme.inkMuted
            Accessible.role: field.hasError ? Accessible.AlertMessage : Accessible.StaticText
        }
    }
}
