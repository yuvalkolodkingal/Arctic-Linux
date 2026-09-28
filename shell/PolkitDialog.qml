import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Services.Polkit

// The polkit agent (design Dialog): asks for your password when an app needs permission for
// a system change. If another agent already runs, or registering fails, the shell starts
// the fallback agent through `arctic-session polkit` instead.
Scope {
    id: root
    readonly property var flow: agent.flow
    readonly property bool active: agent.isActive   // asking now (Get apps shows "Waiting for your password")
    property string password: ''

    PolkitAgent { id: agent }
    Connections {
        target: agent
        function onIsActiveChanged() { dialog.open = agent.isActive; }
    }

    Timer {
        interval: 4000
        running: true
        onTriggered: if (!agent.isRegistered) Quickshell.execDetached(['arctic-session', 'polkit'])
    }

    Popover {
        id: dialog
        layerName: 'arctic-polkit'
        placement: 'center'
        cardColor: Theme.surfaceRaised
        cardWidth: 420
        cardHeight: body.implicitHeight + 2 * Theme.space5
        focusItem: field
        onOpened: { root.password = ''; field.text = ''; }
        // Esc, Cancel or a click outside: tell polkit the request was cancelled.
        onDismissed: if (agent.isActive && root.flow) root.flow.cancelAuthenticationRequest()

        function submit() {
            if (!root.flow || !root.flow.isResponseRequired) return;
            root.flow.submit(field.text);
            field.text = '';
        }

        ColumnLayout {
            id: body
            anchors.fill: parent
            anchors.margins: Theme.space5
            spacing: 0
            RowLayout {
                spacing: Theme.space3
                Layout.fillWidth: true
                Rectangle {
                    Layout.alignment: Qt.AlignTop
                    implicitWidth: 40
                    implicitHeight: 40
                    radius: 20
                    color: Theme.infoSoft
                    Icon { anchors.centerIn: parent; name: 'shield-lock'; size: 22; color: Theme.info }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space1
                    Text {
                        Layout.fillWidth: true
                        text: 'Enter your password to continue'
                        color: Theme.ink
                        font.family: Theme.fontSans
                        font.pixelSize: 20
                        font.weight: Font.DemiBold
                        wrapMode: Text.Wrap
                    }
                    Text {
                        Layout.fillWidth: true
                        text: root.flow ? root.flow.message : ''
                        color: Theme.inkMuted
                        font.family: Theme.fontSans
                        font.pixelSize: 15
                        wrapMode: Text.Wrap
                    }
                }
            }
            ArcticField {
                id: field
                Layout.fillWidth: true
                Layout.topMargin: Theme.space5
                iconName: 'lock'
                echoMode: root.flow && root.flow.responseVisible ? TextInput.Normal : TextInput.Password
                passwordCharacter: '•'
                placeholderText: root.flow && root.flow.inputPrompt ? root.flow.inputPrompt.replace(/:\s*$/, '') : 'Password'
                inputMethodHints: Qt.ImhSensitiveData | Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase
                error: root.flow ? root.flow.failed || root.flow.supplementaryIsError : false
                onAccepted: dialog.submit()
                Keys.onEscapePressed: dialog.close()
            }
            Text {
                Layout.fillWidth: true
                Layout.topMargin: Theme.space2
                visible: text !== ''
                text: !root.flow ? '' : root.flow.failed ? 'That password didn’t work. Try again.' : root.flow.supplementaryMessage
                color: root.flow && (root.flow.failed || root.flow.supplementaryIsError) ? Theme.error : Theme.inkMuted
                font.family: Theme.fontSans
                font.pixelSize: 13
                wrapMode: Text.Wrap
            }
            RowLayout {
                Layout.topMargin: Theme.space6
                Layout.fillWidth: true
                spacing: Theme.space2
                Item { Layout.fillWidth: true }
                ArcticButton { variant: 'ghost'; text: 'Cancel'; onClicked: dialog.close() }
                ArcticButton { variant: 'primary'; text: 'Allow'; enabled: root.flow !== null && root.flow.isResponseRequired; onClicked: dialog.submit() }
            }
        }
    }
}
