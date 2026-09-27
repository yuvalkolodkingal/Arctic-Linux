// Line icon from the Arctic icon set (24 px grid, 1.75 px round stroke).
// Path data is copied from the design system (components/bundle.js ICONS);
// circles and rounded rectangles are written out as SVG arcs.
// The stroke stays 1.75 px at every size, as the brand book asks.
import QtQuick
import QtQuick.Shapes
import ".."

Item {
    id: icon

    property string name
    property color color: Theme.ink
    property real size: 20
    property real strokeWidth: 1.75

    implicitWidth: size
    implicitHeight: size

    readonly property var paths: ({
        "lock": "M7.5 10.5H16.5A2.5 2.5 0 0 1 19 13V18A2.5 2.5 0 0 1 16.5 20.5H7.5A2.5 2.5 0 0 1 5 18V13A2.5 2.5 0 0 1 7.5 10.5Z M8 10.5V8a4 4 0 0 1 8 0v2.5 M12 14.5v2",
        "arrow-right": "M5 12h14 M13.5 6.5L19 12l-5.5 5.5",
        "sleep": "M19 14.5A7.5 7.5 0 1 1 9.5 5a6 6 0 0 0 9.5 9.5z M14.5 4h3l-3 3.5h3",
        "restart": "M4.5 12a7.5 7.5 0 1 0 2.2-5.3 M4.5 4.5v4h4",
        "power": "M12 3.5v8 M7.3 6.5a7.5 7.5 0 1 0 9.4 0",
        "keyboard": "M5 6H19A2.5 2.5 0 0 1 21.5 8.5V15.5A2.5 2.5 0 0 1 19 18H5A2.5 2.5 0 0 1 2.5 15.5V8.5A2.5 2.5 0 0 1 5 6Z M6 10h.01 M9 10h.01 M12 10h.01 M15 10h.01 M18 10h.01 M8 14h8",
        "chevron-down": "M6 9.5l6 6 6-6",
        "chevron-up": "M6 14.5l6-6 6 6",
        "user": "M8.5 8.5A3.5 3.5 0 1 0 15.5 8.5A3.5 3.5 0 1 0 8.5 8.5Z M5 20a7 7 0 0 1 14 0",
        "tiling": "M6 4.5H18A2.5 2.5 0 0 1 20.5 7V17A2.5 2.5 0 0 1 18 19.5H6A2.5 2.5 0 0 1 3.5 17V7A2.5 2.5 0 0 1 6 4.5Z M12 4.5v15 M12 12h8.5",
        "alert": "M12 4.2l8.8 15.3H3.2z M12 10v4.2 M12 17h.01",
        "check": "M5 12.5l4.5 4.5L19 7.5"
    })

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            scale: Qt.size(icon.size / 24, icon.size / 24)
            strokeColor: icon.color
            strokeWidth: icon.strokeWidth
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin

            PathSvg { path: icon.paths[icon.name] || "" }
        }
    }
}
