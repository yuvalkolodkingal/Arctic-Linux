// A settings page: title-1 heading and a lede that says what the page is for, then groups of
// settings in a scrolling column (a 720px measure). reveal(key) scrolls to the row whose
// searchKey is `key` and highlights it for a moment (the search uses it).
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import "components"

FocusScope {
    id: page
    property string title: ""
    property string lede: ""
    default property alias content: body.data
    property alias flick: flick
    property var highlighted: null
    // Pages reload their data when shown again (network, Bluetooth, updates change on their own).
    signal shown()

    function find(item, key) {
        if (!item)
            return null;
        if (item.objectName === key)
            return item;
        for (let i = 0; i < item.children.length; i++) {
            const hit = find(item.children[i], key);
            if (hit)
                return hit;
        }
        return null;
    }
    function reveal(key) {
        const item = find(body, key);
        if (!item)
            return false;
        const y = item.mapToItem(flick.contentItem, 0, 0).y;
        flick.contentY = Math.max(0, Math.min(flick.contentHeight - flick.height, y - 96));
        if (highlighted && highlighted.highlighted !== undefined)
            highlighted.highlighted = false;
        if (item.highlighted !== undefined) {
            item.highlighted = true;
            highlighted = item;
            unhighlight.restart();
        }
        return true;
    }
    // Keep the keyboard focus in view while tabbing through a long page.
    function ensureVisible(item) {
        if (!item || !flick.contentItem || !isInside(item, flick.contentItem))
            return;
        const top = item.mapToItem(flick.contentItem, 0, 0).y;
        const bottom = top + item.height;
        if (top < flick.contentY + 16)
            flick.contentY = Math.max(0, top - 48);
        else if (bottom > flick.contentY + flick.height - 16)
            flick.contentY = Math.min(flick.contentHeight - flick.height, bottom - flick.height + 48);
    }
    function isInside(item, ancestor) {
        for (let p = item; p; p = p.parent)
            if (p === ancestor)
                return true;
        return false;
    }
    Timer {
        id: unhighlight
        interval: 1800
        onTriggered: if (page.highlighted) page.highlighted.highlighted = false
    }

    Flickable {
        id: flick
        anchors.fill: parent
        contentHeight: column.implicitHeight + 36 + Theme.space10
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {
            policy: flick.contentHeight > flick.height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
        }
        Behavior on contentY {
            enabled: !Theme.reduceMotion && !flick.moving
            NumberAnimation { duration: Theme.durationBase; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeStandard }
        }

        Column {
            id: column
            x: Theme.space10
            y: 36
            width: Math.min(720, flick.width - 2 * Theme.space10)
            spacing: Theme.space6

            Column {
                width: parent.width
                spacing: Theme.space1
                ArText {
                    width: parent.width
                    text: page.title
                    size: 28
                    lh: 36
                    weight: Font.DemiBold
                    tracking: -0.01
                    wrapMode: Text.WordWrap
                    Accessible.role: Accessible.Heading
                }
                ArText {
                    visible: page.lede !== ""
                    width: parent.width
                    text: page.lede
                    size: 15
                    lh: 22
                    wrapMode: Text.WordWrap
                    color: Theme.inkMuted
                }
            }
            Column {
                id: body
                width: parent.width
                spacing: Theme.space8
            }
        }
    }
    Keys.onPressed: event => {
        if (event.key === Qt.Key_PageDown)
            flick.contentY = Math.min(Math.max(0, flick.contentHeight - flick.height), flick.contentY + flick.height * 0.8);
        else if (event.key === Qt.Key_PageUp)
            flick.contentY = Math.max(0, flick.contentY - flick.height * 0.8);
        else
            return;
        event.accepted = true;
    }
}
