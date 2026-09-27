// .ar-list — a bordered, rounded list (ListView) with keyboard navigation:
// Tab focuses it, ↑/↓/Home/End/PgUp/PgDn move the current row, Space picks it,
// Enter goes on to Next (not consumed). Delegates are usually ArListRow, bound to
// `ListView.isCurrentItem` and the list's `showFocus`.
import QtQuick
import ".."

FocusScope {
    id: list
    property alias model: view.model
    property alias delegate: view.delegate
    property alias currentIndex: view.currentIndex
    property alias view: view
    property int maxHeight: 100000
    property bool mouseUsed: false
    property string accessibleName: ""
    readonly property bool showFocus: view.activeFocus && !mouseUsed
    // The current row changed (arrows, Home/End, click): selection follows focus.
    signal picked(int index)
    // A row was activated explicitly (click or Space).
    signal activated(int index)
    // Printable text typed while the list has focus (type-to-search).
    signal typed(string text)

    implicitWidth: 560
    implicitHeight: Math.min(view.contentHeight + 2, maxHeight)
    activeFocusOnTab: true
    Accessible.role: Accessible.List
    Accessible.name: accessibleName

    onActiveFocusChanged: if (!activeFocus) mouseUsed = false

    function pickRow(i, byMouse) {
        if (i < 0 || i >= view.count)
            return;
        mouseUsed = !!byMouse;
        view.currentIndex = i;
        view.forceActiveFocus();
        picked(i);
    }
    function clickRow(i) {
        pickRow(i, true);
        activated(i);
    }

    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusLg
        color: Theme.surfaceRaised
    }

    ListView {
        id: view
        anchors.fill: parent
        anchors.margins: 1
        focus: true
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        keyNavigationEnabled: false
        highlightMoveDuration: Theme.durationBase
        highlightFollowsCurrentItem: false
        currentIndex: -1
        Keys.onUpPressed: event => list.pickRow(Math.max(0, view.currentIndex - 1), false)
        Keys.onDownPressed: event => list.pickRow(Math.min(view.count - 1, view.currentIndex + 1), false)
        Keys.onPressed: event => {
            const page = Math.max(1, Math.floor(view.height / 56));
            if (event.key === Qt.Key_Home)
                list.pickRow(0, false);
            else if (event.key === Qt.Key_End)
                list.pickRow(view.count - 1, false);
            else if (event.key === Qt.Key_PageDown)
                list.pickRow(Math.min(view.count - 1, view.currentIndex + page), false);
            else if (event.key === Qt.Key_PageUp)
                list.pickRow(Math.max(0, view.currentIndex - page), false);
            else if (event.key === Qt.Key_Space) {
                if (view.currentIndex >= 0) {
                    list.picked(view.currentIndex);
                    list.activated(view.currentIndex);
                }
            }
            // type-ahead: printable text only (Esc, Enter, Tab… carry control characters and
            // belong to the frame: quit, Next).
            else if (event.text.trim() !== "" && !/[\x00-\x1f\x7f]/.test(event.text) && !(event.modifiers & (Qt.ControlModifier | Qt.AltModifier))) {
                list.typed(event.text);
            } else {
                event.accepted = false;
                return;
            }
            event.accepted = true;
        }
        onCurrentIndexChanged: if (currentIndex >= 0) positionViewAtIndex(currentIndex, ListView.Contain)
    }

    CornerMask {
        radius: Theme.radiusLg
    }
    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusLg
        color: "transparent"
        border.width: 1
        border.color: Theme.line
        z: 60
    }
}
