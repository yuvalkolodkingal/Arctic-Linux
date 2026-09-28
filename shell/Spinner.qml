import QtQuick

// A 16px busy ring: an ink-muted arc turning once a second. Reduced motion: a still "…".
Item {
    id: spinner
    property bool running: true
    property int size: 16
    property color color: Theme.inkMuted
    implicitWidth: size
    implicitHeight: size
    Accessible.role: Accessible.Indicator
    Accessible.name: 'Working'

    Canvas {
        id: ring
        visible: !Theme.reduceMotion
        anchors.fill: parent
        onPaint: {
            const ctx = getContext('2d');
            ctx.reset();
            ctx.lineWidth = 2;
            ctx.lineCap = 'round';
            ctx.strokeStyle = spinner.color;
            ctx.beginPath();
            ctx.arc(width / 2, height / 2, width / 2 - 2, 0, Math.PI * 1.4);
            ctx.stroke();
        }
        Connections {
            target: spinner
            function onColorChanged() { ring.requestPaint(); }
        }
        RotationAnimator on rotation {
            running: spinner.running && spinner.visible && ring.visible
            from: 0
            to: 360
            duration: 1000
            loops: Animation.Infinite
        }
    }
    Text {
        visible: Theme.reduceMotion
        anchors.centerIn: parent
        text: '…'
        color: spinner.color
        font.family: Theme.fontSans
        font.pixelSize: 13
    }
}
