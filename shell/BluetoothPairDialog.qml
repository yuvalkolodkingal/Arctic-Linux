import QtQuick
import QtQuick.Layouts
import Quickshell

// Pairing codes and questions from the Bluetooth agent (bt-agent.py via BluetoothService), as a
// design Dialog like the polkit one: check a code, type a passkey or PIN, type a code on a
// keyboard, or allow a device or one of its services. Esc, Cancel or a click outside says no;
// the agent cancelling (or its 90 s timeout) closes it. Its layer is shielded in screen shares.
Popover {
    id: dialog
    readonly property var req: BluetoothService.request
    readonly property string kind: req ? req.kind : ''
    readonly property string device: req ? req.name : ''
    readonly property bool needsInput: kind === 'passkey' || kind === 'pin'
    readonly property bool answerable: kind !== 'show_passkey' && kind !== 'show_pin'
    property bool answered: false

    layerName: 'arctic-bt-pair'
    placement: 'center'
    cardColor: Theme.surfaceRaised
    shadow: 2
    cardWidth: 420
    cardHeight: body.implicitHeight + 2 * Theme.space5
    focusItem: needsInput ? field : answerable ? primary : cancel

    // Esc, Cancel or a click outside: no.
    onDismissed: if (!answered) { answered = true; if (answerable) BluetoothService.reply(false); else BluetoothService.dismiss(); }
    onReqChanged: {
        field.text = '';
        if (req) {
            answered = false;
            if (!open) open = true; else Qt.callLater(focusContent);
        } else if (open) {
            answered = true;         // answered, or cancelled by the device or the agent
            close();
        }
    }

    function accept() {
        if (!req) return;
        if (kind === 'passkey' && !/^\d{1,6}$/.test(field.text)) return;
        if (kind === 'pin' && (field.text.length < 1 || field.text.length > 16)) return;
        answered = true;
        BluetoothService.reply(true, field.text);
        field.text = '';
    }

    readonly property string title: {
        switch (kind) {
        case 'confirm': return 'Pair with “' + device + '”?';
        case 'passkey': return 'Enter the code shown on “' + device + '”';
        case 'pin': return 'Enter the PIN for “' + device + '”';
        case 'show_passkey': return 'Type this code on “' + device + '”';
        case 'show_pin': return 'Type this PIN on “' + device + '”';
        case 'authorize': return '“' + device + '” wants to pair with this computer';
        case 'service': return 'Allow “' + device + '” to connect for ' + (req.service || 'a service') + '?';
        }
        return '';
    }
    readonly property string message: {
        switch (kind) {
        case 'confirm': return 'Check that “' + device + '” shows the same code.';
        case 'pin': return 'Often 0000 or 1234, or printed in the manual.';
        case 'show_passkey':
        case 'show_pin': return 'Then press Enter on that keyboard.';
        }
        return '';
    }
    readonly property string code: !req ? '' : kind === 'show_pin' ? (req.pin || '') : (req.passkey || '')

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
                Icon { anchors.centerIn: parent; name: BluetoothService.iconFor(dialog.req ? dialog.req.icon : ''); size: 22; color: Theme.info }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.space1
                Text {
                    Layout.fillWidth: true
                    text: dialog.title
                    textFormat: Text.PlainText
                    color: Theme.ink
                    font.family: Theme.fontSans
                    font.pixelSize: 20
                    font.weight: Font.DemiBold
                    wrapMode: Text.Wrap
                    Accessible.role: Accessible.Heading
                }
                Text {
                    Layout.fillWidth: true
                    visible: dialog.message !== ''
                    text: dialog.message
                    textFormat: Text.PlainText
                    color: Theme.inkMuted
                    font.family: Theme.fontSans
                    font.pixelSize: 15
                    wrapMode: Text.Wrap
                }
            }
        }
        // The code to compare or type, in large tabular mono ("042 917").
        Text {
            visible: dialog.code !== ''
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: Theme.space5
            text: dialog.code.length === 6 ? dialog.code.slice(0, 3) + ' ' + dialog.code.slice(3) : dialog.code
            textFormat: Text.PlainText
            color: Theme.ink
            font.family: Theme.fontMono
            font.pixelSize: 28
            font.weight: Font.DemiBold
            font.features: { 'tnum': 1 }
            Accessible.name: 'Code ' + dialog.code.split('').join(' ')
        }
        // One dot per digit already typed on the keyboard being paired.
        Row {
            visible: dialog.kind === 'show_passkey'
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: Theme.space2
            spacing: Theme.space2
            Repeater {
                model: 6
                Rectangle {
                    required property int index
                    width: 8
                    height: 8
                    radius: 4
                    color: dialog.req && index < (dialog.req.entered || 0) ? Theme.ink : Theme.line
                }
            }
        }
        ArcticField {
            id: field
            visible: dialog.needsInput
            Layout.fillWidth: true
            Layout.topMargin: Theme.space5
            iconName: 'key'
            placeholderText: dialog.kind === 'passkey' ? '6-digit code' : 'PIN'
            maximumLength: dialog.kind === 'passkey' ? 6 : 16
            validator: RegularExpressionValidator { regularExpression: dialog.kind === 'passkey' ? /\d{0,6}/ : /.{0,16}/ }
            inputMethodHints: dialog.kind === 'passkey' ? Qt.ImhDigitsOnly : Qt.ImhSensitiveData | Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase
            font.family: dialog.kind === 'passkey' ? Theme.fontMono : Theme.fontSans
            onAccepted: dialog.accept()
            Keys.onEscapePressed: dialog.close()
        }
        RowLayout {
            Layout.topMargin: Theme.space6
            Layout.fillWidth: true
            spacing: Theme.space2
            Item { Layout.fillWidth: true }
            ArcticButton {
                id: cancel
                variant: 'ghost'
                text: dialog.kind === 'authorize' ? 'Don’t pair' : dialog.kind === 'service' ? 'Don’t allow' : 'Cancel'
                KeyNavigation.tab: primary.visible ? primary : (field.visible ? field : null)
                Keys.onEscapePressed: dialog.close()
                onClicked: dialog.close()
            }
            ArcticButton {
                id: primary
                visible: dialog.answerable
                variant: 'primary'
                text: dialog.kind === 'service' ? 'Allow' : 'Pair'
                enabled: !dialog.needsInput || field.text.length > 0
                KeyNavigation.tab: field.visible ? field : cancel
                Keys.onEscapePressed: dialog.close()
                onClicked: dialog.accept()
            }
        }
    }
}
