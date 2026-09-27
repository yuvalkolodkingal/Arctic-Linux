import QtQuick
import Quickshell
import Quickshell.Wayland

PanelWindow {
    id: frame
    anchors { top: true; bottom: true; left: true; right: true }
    margins.top: Theme.barHeight
    color: 'transparent'
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.namespace: 'quickshell-frame'
    WlrLayershell.layer: WlrLayer.Overlay
    mask: Region {}
    Canvas {
        id: outline
        anchors.fill: parent
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Connections {
            target: Theme
            function onBackgroundChanged() { outline.requestPaint(); }
            function onAccentChanged() { outline.requestPaint(); }
        }
        function rounded(ctx, x, y, w, h, r) {
            ctx.moveTo(x + r, y);
            ctx.lineTo(x + w - r, y);
            ctx.quadraticCurveTo(x + w, y, x + w, y + r);
            ctx.lineTo(x + w, y + h - r);
            ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
            ctx.lineTo(x + r, y + h);
            ctx.quadraticCurveTo(x, y + h, x, y + h - r);
            ctx.lineTo(x, y + r);
            ctx.quadraticCurveTo(x, y, x + r, y);
            ctx.closePath();
        }
        onPaint: {
            const ctx = getContext('2d');
            ctx.reset();
            ctx.fillStyle = Theme.background;
            ctx.fillRect(0, 0, width, height);
            ctx.globalCompositeOperation = 'destination-out';
            ctx.beginPath();
            rounded(ctx, Theme.frameWidth, Theme.frameWidth, width - 2 * Theme.frameWidth, height - 2 * Theme.frameWidth, Theme.frameRadius);
            ctx.fill();
            ctx.globalCompositeOperation = 'source-over';
            ctx.beginPath();
            rounded(ctx, Theme.frameWidth - 0.5, Theme.frameWidth - 0.5, width - 2 * Theme.frameWidth + 1, height - 2 * Theme.frameWidth + 1, Theme.frameRadius);
            ctx.strokeStyle = Theme.accent;
            ctx.globalAlpha = 0.55;
            ctx.lineWidth = 1;
            ctx.stroke();
        }
    }
}
