import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io

// "Share with a phone…" from a saved network's page in the network menu: a QR code a phone
// camera joins with (network.py share: nmcli reads the password, qrencode draws it from stdin),
// and "Show password" for typing it instead. The password lives only in this card while it is
// open and is cleared on close; a warning hides it while the screen is recorded or shared.
Popover {
    id: card
    property string uuid: ''
    property string ssid: ''
    property string svg: ''
    property string password: ''
    property string error: ''
    property bool busy: false

    layerName: 'arctic-wifi-share'
    hideWhileCaptured: true
    placement: 'center'
    cardColor: Theme.surfaceRaised
    shadow: 2
    cardWidth: 360
    cardHeight: body.implicitHeight + 2 * Theme.space5
    focusItem: done

    function show(u, name) {
        uuid = u;
        ssid = name;
        svg = '';
        password = '';
        error = '';
        load(false);
    }
    function load(reveal) {
        busy = true;
        reader.command = ['python3', Session.scripts + '/network.py', 'share', '--uuid', uuid].concat(reveal ? ['--reveal'] : []);
        reader.running = true;
    }
    onDismissed: { password = ''; svg = ''; }

    Process {
        id: reader
        stdout: StdioCollector {
            onStreamFinished: {
                card.busy = false;
                let data = null;
                try { data = JSON.parse(text); } catch (e) {}
                if (!data || !data.ok) { card.error = data ? data.error : 'Couldn’t read the network.'; return; }
                card.svg = data.svg;
                if (data.password !== undefined) card.password = data.password;
            }
        }
    }

    ColumnLayout {
        id: body
        anchors.fill: parent
        anchors.margins: Theme.space5
        spacing: Theme.space3
        Text {
            Layout.fillWidth: true
            text: 'Share “' + card.ssid + '”'
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
            text: card.error !== '' ? card.error : 'Scan this with a phone camera to join.'
            textFormat: Text.PlainText
            color: card.error !== '' ? Theme.error : Theme.inkMuted
            font.family: Theme.fontSans
            font.pixelSize: 15
            wrapMode: Text.Wrap
        }
        // The code stays black on white (what cameras read best), on a white tile in both themes.
        Rectangle {
            visible: card.svg !== ''
            Layout.alignment: Qt.AlignHCenter
            implicitWidth: 220
            implicitHeight: 220
            radius: Theme.radiusMd
            color: '#ffffff'
            border.width: 1
            border.color: Theme.line
            Image {
                anchors.fill: parent
                anchors.margins: Theme.space2
                source: card.svg !== '' ? 'data:image/svg+xml;utf8,' + encodeURIComponent(card.svg) : ''
                sourceSize: Qt.size(408, 408)
                fillMode: Image.PreserveAspectFit
                smooth: false
                Accessible.role: Accessible.Graphic
                Accessible.name: 'QR code for ' + card.ssid
            }
        }
        Spinner { visible: card.busy; running: visible; Layout.alignment: Qt.AlignHCenter }
        Text {
            visible: card.password !== ''
            Layout.alignment: Qt.AlignHCenter
            text: card.password
            color: Theme.ink
            font.family: Theme.fontMono
            font.pixelSize: 17
            textFormat: Text.PlainText
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: Theme.space2
            spacing: Theme.space2
            ArcticButton {
                id: reveal
                visible: card.svg !== '' && card.password === ''
                text: 'Show password'
                variant: 'ghost'
                iconName: 'eye'
                KeyNavigation.tab: done
                KeyNavigation.backtab: done
                onClicked: card.load(true)
            }
            Item { Layout.fillWidth: true }
            ArcticButton {
                id: done
                text: 'Done'
                variant: 'primary'
                KeyNavigation.tab: reveal.visible ? reveal : null
                KeyNavigation.backtab: reveal.visible ? reveal : null
                onClicked: card.close()
            }
        }
    }
}
