pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Wayland

// The screen frame: a thin ground-coloured surround below the bar with rounded inner corners
// and a `line` hairline, so the desktop reads as one framed sheet (the original shell's
// identity). Amber stays reserved for focus and selection.
//
// It reserves its width on the left, right and bottom (the bar reserves the top band; while the
// bar is hidden the frame reserves the top too and reaches the screen's edge), so Mango lays
// windows out inside it and keeps its own 8px gap; the inner radius is the window radius plus
// that gap, so window corners sit concentric with the frame's.
// Turn it off with {"frame": false} in ~/.config/arctic/shell.json.
Scope {
    id: root
    required property var modelData

    PanelWindow {
        id: frame
        screen: root.modelData
        visible: Theme.frameWidth > 0
        anchors { top: true; bottom: true; left: true; right: true }
        margins.top: Theme.topInset
        margins.bottom: Theme.bottomInset
        color: 'transparent'
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.layer: WlrLayer.Bottom
        WlrLayershell.namespace: 'arctic-frame'
        mask: Region {}

        Canvas {
            id: outline
            anchors.fill: parent
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
            Connections {
                target: Theme
                function onGroundChanged() { outline.requestPaint(); }
                function onLineChanged() { outline.requestPaint(); }
                function onFrameWidthChanged() { outline.requestPaint(); }
            }
            function rounded(ctx, x, y, w, h, r) {
                ctx.moveTo(x + r, y);
                ctx.lineTo(x + w - r, y);
                ctx.arcTo(x + w, y, x + w, y + r, r);
                ctx.lineTo(x + w, y + h - r);
                ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
                ctx.lineTo(x + r, y + h);
                ctx.arcTo(x, y + h, x, y + h - r, r);
                ctx.lineTo(x, y + r);
                ctx.arcTo(x, y, x + r, y, r);
                ctx.closePath();
            }
            onPaint: {
                const ctx = getContext('2d');
                const f = Theme.frameWidth, r = Theme.frameRadius;
                ctx.reset();
                if (f <= 0) return;
                ctx.fillStyle = Theme.ground;
                ctx.fillRect(0, 0, width, height);
                ctx.globalCompositeOperation = 'destination-out';
                ctx.beginPath();
                rounded(ctx, f, f, width - 2 * f, height - 2 * f, r);
                ctx.fill();
                ctx.globalCompositeOperation = 'source-over';
                ctx.beginPath();
                rounded(ctx, f - 0.5, f - 0.5, width - 2 * f + 1, height - 2 * f + 1, r + 0.5);
                ctx.strokeStyle = Theme.line;
                ctx.lineWidth = 1;
                ctx.stroke();
            }
        }
    }

    // Exclusive zones for the other three edges (a layer surface reserves one edge only).
    component Reserve: PanelWindow {
        screen: root.modelData
        visible: Theme.frameWidth > 0
        color: 'transparent'
        implicitWidth: Theme.frameWidth
        implicitHeight: Theme.frameWidth
        exclusionMode: ExclusionMode.Normal
        exclusiveZone: Theme.frameWidth
        WlrLayershell.layer: WlrLayer.Bottom
        WlrLayershell.namespace: 'arctic-frame-reserve'
        mask: Region {}
    }
    Reserve { anchors { left: true; top: true; bottom: true } }
    Reserve { anchors { right: true; top: true; bottom: true } }
    Reserve { anchors { bottom: true; left: true; right: true }
        visible: Theme.frameWidth > 0 && Theme.bottomInset === 0 }
    Reserve {
        anchors { top: true; left: true; right: true }
        visible: Theme.frameWidth > 0 && Theme.topInset === 0
    }
}
