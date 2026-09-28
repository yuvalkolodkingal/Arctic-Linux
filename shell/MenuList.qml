import QtQuick
import QtQuick.Layouts
import "MenuNav.js" as Nav

// The body of a bar menu: a column of rows that scrolls when the menu is capped to the screen,
// with the menus' keyboard model (MenuNav.js). Rows, switches, sliders and fields are "stops"
// (items with `menuStop: true`), found in visual order; sections and separators (`menuBreak`)
// start a new group for Tab. Up/Down move and wrap, Home/End and PgUp/PgDn jump, Tab moves
// between groups, letters jump to the next row starting with what was typed. On a page
// (MenuPage) Left, Backspace and Esc go back; otherwise Esc reaches the popover, which closes.
FocusScope {
    id: list
    default property alias content: column.data
    property int padding: Theme.space1
    property bool isPage: false
    property string typed: ''
    readonly property alias flickable: flick
    signal back()

    implicitWidth: 320
    implicitHeight: column.implicitHeight + 2 * padding

    // ---- stops ------------------------------------------------------------------------------
    function stops() {
        const out = [];
        let group = 0;
        function walk(item) {
            const kids = item.children;
            for (let i = 0; i < kids.length; i++) {
                const k = kids[i];
                if (!k.visible) continue;
                if (k.menuBreak === true) group++;
                if (k.menuStop === true) out.push({ item: k, enabled: k.enabled, label: k.label || k.title || '', group: group });
                else walk(k);
                if (k.menuBreakAfter === true) group++;
            }
        }
        walk(column);
        return out;
    }
    function currentIn(all) {
        for (let i = 0; i < all.length; i++) if (all[i].item.activeFocus) return i;
        return -1;
    }
    function focusAt(all, i) {
        if (i < 0 || i >= all.length) return false;
        all[i].item.forceActiveFocus();
        ensureVisible(all[i].item);
        return true;
    }
    function focusItem(item) {
        if (!item) return;
        item.forceActiveFocus();
        ensureVisible(item);
    }
    function first() { const all = stops(); return focusAt(all, Nav.edge(all, -1)); }
    // Where the keyboard starts: the first row after a header's switch (Enter there would turn
    // Wi-Fi or Bluetooth off by accident), else the first stop.
    function start() {
        const all = stops();
        const i = all.findIndex(s => s.enabled && s.item.headerStop !== true);
        return focusAt(all, i >= 0 ? i : Nav.edge(all, -1));
    }
    function last() { const all = stops(); return focusAt(all, Nav.edge(all, 1)); }
    function move(dir) { const all = stops(); return focusAt(all, Nav.step(all, currentIn(all), dir)); }
    function ensureVisible(item) {
        if (!item || flick.height <= 0) return;
        const p = item.mapToItem(column, 0, 0);
        const top = p.y, bottom = p.y + item.height + 2 * padding;
        if (top < flick.contentY) flick.contentY = Math.max(0, top);
        else if (bottom > flick.contentY + flick.height) flick.contentY = Math.min(flick.contentHeight - flick.height, bottom - flick.height);
    }
    // Nothing focused yet when the list gets focus: the first stop.
    onActiveFocusChanged: if (activeFocus && currentIn(stops()) < 0) Qt.callLater(start)

    Keys.onPressed: event => {
        MenuState.keyboardNav = true;
        const all = stops();
        const here = currentIn(all);
        let target = -2;
        const plain = !(event.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier));
        switch (event.key) {
        case Qt.Key_Down: target = Nav.step(all, here, 1); break;
        case Qt.Key_Up: target = Nav.step(all, here, -1); break;
        case Qt.Key_Home: target = Nav.edge(all, -1); break;
        case Qt.Key_End: target = Nav.edge(all, 1); break;
        case Qt.Key_PageDown: target = Nav.page(all, here, 1, 5); break;
        case Qt.Key_PageUp: target = Nav.page(all, here, -1, 5); break;
        case Qt.Key_Tab: if (plain) target = Nav.group(all, here, 1); break;
        case Qt.Key_Backtab: target = Nav.group(all, here, -1); break;
        case Qt.Key_Left:
        case Qt.Key_Backspace:
        case Qt.Key_Escape:
            if (list.isPage) { list.back(); event.accepted = true; }
            return;
        default:
            if (plain && event.text.length === 1 && event.text.trim() !== '') {
                typed = (typeAhead.running ? typed : '') + event.text;
                typeAhead.restart();
                target = Nav.match(all, here, typed);
                if (target < 0 && typed.length > 1) target = Nav.match(all, here, event.text);
                if (target < 0) target = -2;
            }
        }
        if (target === -2) return;
        event.accepted = true;
        focusAt(all, target);
    }
    Timer { id: typeAhead; interval: 800 }

    Flickable {
        id: flick
        anchors.fill: parent
        contentWidth: width
        contentHeight: list.implicitHeight
        boundsBehavior: Flickable.StopAtBounds
        interactive: contentHeight > height + 1
        clip: interactive
        ColumnLayout {
            id: column
            x: list.padding
            y: list.padding
            width: flick.width - 2 * list.padding
            spacing: 0
        }
    }
    // A 4px scroll indicator, only while the list moves.
    Rectangle {
        visible: flick.interactive
        opacity: flick.moving ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.durationFast } }
        anchors.right: parent.right
        anchors.rightMargin: 2
        y: flick.visibleArea.yPosition * flick.height
        width: 4
        height: Math.max(16, flick.visibleArea.heightRatio * flick.height)
        radius: 2
        color: Theme.inkSubtle
    }
}
