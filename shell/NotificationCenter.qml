pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell
import "NotificationRules.js" as Rules

// The notification centre under the bell (design Menu card, 380px): do not disturb with its
// durations, then the notifications grouped by app (newest group first; the three newest
// groups open, older ones folded into one card), "Clear all" and "Notification settings".
// Opening it marks everything seen and tucks the toasts away (they are all here).
//
// Keyboard: ↑/↓ move (Home/End), Enter runs (the default action on a card, fold/unfold on a
// group, the switch on do not disturb), → opens do not disturb's durations or unfolds a group,
// ← folds it or goes back, Tab steps through a card's buttons, Delete dismisses a card or
// clears a group, Shift+Delete clears everything, Esc goes back or closes.
// `arctic-notify center` (Super + Alt + N) opens it from anywhere.
Popover {
    id: centre
    layerName: 'arctic-notifications'
    placement: 'point'
    scrim: false
    cardColor: Theme.surfaceRaised
    cardRadius: Theme.radiusLg
    cardWidth: 380
    cardHeight: Math.min(layout.implicitHeight, height - 2 * Theme.space4 - Theme.frameWidth)
    focusItem: keys

    property string page: 'main'            // main, or dnd (the durations)
    property string current: ''             // the highlighted stop (see stops)
    property int currentAction: -1          // a card's button, reached with Tab
    property bool keyboardNav: false
    property var folded: ({})               // group key → true (folded) / false (open), by hand
    property var items: ({})                // stop → its item, for scrolling it into view
    readonly property bool owned: NotificationService.owned || !NotificationService.checked
    readonly property var groups: Rules.group(NotificationService.centreEntries)
    // Header, do not disturb and footer: the list scrolls in what is left of the screen.
    readonly property real fixedHeight: headerRow.implicitHeight + Theme.space3 + Theme.space2 + (dndLine.visible ? dndLine.implicitHeight : 0)
                                        + Theme.space1 + 2 + footerRow.implicitHeight + 2 * Theme.space2
    readonly property var durations: [
        { key: 'd:1h', command: '1h', label: 'For 1 hour', icon: 'clock' },
        { key: 'd:tomorrow', command: 'tomorrow', label: 'Until tomorrow', detail: '08:00', icon: 'moon' },
        { key: 'd:on', command: 'on', label: 'Until I turn it off', icon: 'bell-off' },
        { key: 'd:off', command: 'off', label: 'Turn off', icon: 'bell' }
    ]
    readonly property var stops: {
        if (page === 'dnd') return durations.map(d => d.key);
        const out = [];
        if (!owned) return ['settings'];
        out.push('dnd');
        groups.forEach((g, i) => {
            out.push('g:' + g.key);
            if (isOpen(g, i)) g.items.forEach(e => out.push('n:' + e.id));
        });
        if (groups.length) out.push('clear');
        out.push('settings');
        return out;
    }

    function isOpen(g, index) { return folded[g.key] !== undefined ? !folded[g.key] : index < 3; }
    function setFolded(key, value) { const f = Object.assign({}, folded); f[key] = value; folded = f; }
    function entryOf(stop) { return stop.startsWith('n:') ? NotificationService.find(Number(stop.slice(2))) : null; }
    function groupOf(stop) {
        const key = stop.startsWith('g:') ? stop.slice(2) : '';
        for (let i = 0; i < groups.length; i++) if (groups[i].key === key) return { group: groups[i], index: i };
        return null;
    }
    function move(delta) {
        const list = stops;
        if (!list.length) return;
        let i = list.indexOf(current);
        i = i < 0 ? (delta > 0 ? 0 : list.length - 1) : (i + delta + list.length) % list.length;
        select(list[i]);
    }
    function select(stop) {
        current = stop;
        currentAction = -1;
        Qt.callLater(reveal);
    }
    function reveal() {
        const item = items[current];
        if (!item || !flick.visible) return;
        const y = item.mapToItem(flick.contentItem, 0, 0).y;
        if (y < flick.contentY) flick.contentY = Math.max(0, y - Theme.space1);
        else if (y + item.height > flick.contentY + flick.height)
            flick.contentY = Math.min(flick.contentHeight - flick.height, y + item.height - flick.height + Theme.space1);
    }
    function register(stop, item) { items[stop] = item; }
    // After a dismissal the highlight moves to the next stop (or the previous at the end).
    function removeCurrent(action) {
        const list = stops, i = list.indexOf(current);
        action();
        Qt.callLater(() => {
            const after = centre.stops;
            centre.select(after[Math.min(Math.max(0, i), after.length - 1)] || '');
        });
    }
    function activate(stop) {
        if (stop === 'dnd') DndService.toggle();
        else if (stop === 'clear') removeCurrent(() => NotificationService.clearAll());
        else if (stop === 'settings') { close(); Quickshell.execDetached(['arctic-settings', 'notifications']); }
        else if (stop.startsWith('d:')) {
            const d = durations.find(x => x.key === stop);
            if (d) DndService.set(d.command);
            page = 'main';
            select('dnd');
        } else if (stop.startsWith('g:')) {
            const g = groupOf(stop);
            if (g) setFolded(g.group.key, isOpen(g.group, g.index));
        } else if (stop.startsWith('n:')) {
            const e = entryOf(stop);
            if (!e) return;
            const actions = e.actions.slice(0, 3);
            if (currentAction >= 0 && currentAction < actions.length) {
                removeCurrent(() => NotificationService.invokeAction(e.id, actions[currentAction].identifier));
            } else {
                close();
                NotificationService.activate(e.id);
            }
        }
    }
    function deleteCurrent(all) {
        if (all) { removeCurrent(() => NotificationService.clearAll()); return; }
        if (current.startsWith('n:')) { const e = entryOf(current); if (e) removeCurrent(() => NotificationService.remove(e.id)); }
        else if (current.startsWith('g:')) { const g = groupOf(current); if (g) removeCurrent(() => NotificationService.clearGroup(g.group.key)); }
    }
    function openDurations() { page = 'dnd'; select(NotificationService.dndActive ? 'd:off' : 'd:1h'); }
    function back() { page = 'main'; select('dnd'); }

    onOpened: {
        page = 'main';
        folded = {};
        keyboardNav = false;
        flick.contentY = 0;
        select(owned ? 'dnd' : 'settings');
        NotificationService.markSeen();
        NotificationService.dismissToasts();
    }
    Connections {
        target: NotificationService
        // New ones while it is open are seen at once.
        function onUnseenChanged() { if (centre.open && NotificationService.unseen > 0) NotificationService.markSeen(); }
    }

    FocusScope {
        id: keys
        anchors.fill: parent
        focus: true
        Keys.onPressed: event => {
            const k = event.key, shift = event.modifiers & Qt.ShiftModifier;
            centre.keyboardNav = true;
            if (k === Qt.Key_Down) centre.move(1);
            else if (k === Qt.Key_Up) centre.move(-1);
            else if (k === Qt.Key_Home) centre.select(centre.stops[0] || '');
            else if (k === Qt.Key_End) centre.select(centre.stops[centre.stops.length - 1] || '');
            else if (k === Qt.Key_Return || k === Qt.Key_Enter || k === Qt.Key_Space) centre.activate(centre.current);
            else if (k === Qt.Key_Right) {
                if (centre.current === 'dnd') centre.openDurations();
                else if (centre.current.startsWith('g:')) { const g = centre.groupOf(centre.current); if (g) centre.setFolded(g.group.key, false); }
            } else if (k === Qt.Key_Left || k === Qt.Key_Backspace) {
                if (centre.page === 'dnd') centre.back();
                else if (centre.current.startsWith('g:')) { const g = centre.groupOf(centre.current); if (g) centre.setFolded(g.group.key, true); }
                else if (centre.current.startsWith('n:')) { const e = centre.entryOf(centre.current); if (e) centre.select('g:' + Rules.appKey(e)); }
            } else if (k === Qt.Key_Tab || k === Qt.Key_Backtab) {
                const back = k === Qt.Key_Backtab || shift;
                const e = centre.entryOf(centre.current);
                const n = e ? e.actions.slice(0, 3).length : 0;
                if (!back && n && centre.currentAction < n - 1) centre.currentAction++;
                else if (back && n && centre.currentAction >= 0) centre.currentAction--;
                else centre.move(back ? -1 : 1);
            } else if (k === Qt.Key_Delete) centre.deleteCurrent(shift);
            else if (k === Qt.Key_Escape && centre.page === 'dnd') centre.back();
            else { event.accepted = false; return; }
            event.accepted = true;
        }

        ColumnLayout {
            id: layout
            anchors { left: parent.left; right: parent.right; top: parent.top }
            spacing: 0

            // ---- header ------------------------------------------------------------------
            RowLayout {
                id: headerRow
                Layout.fillWidth: true
                Layout.leftMargin: Theme.space4
                Layout.rightMargin: Theme.space2
                Layout.topMargin: Theme.space3
                Layout.bottomMargin: Theme.space2
                spacing: Theme.space2
                ArcticButton {
                    visible: centre.page === 'dnd'
                    variant: 'ghost'
                    size: 'sm'
                    iconOnly: true
                    iconName: 'chevron-left'
                    label: 'Back'
                    focusPolicy: Qt.NoFocus
                    onClicked: centre.back()
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Text {
                        Layout.fillWidth: true
                        text: centre.page === 'dnd' ? 'Do not disturb' : 'Notifications'
                        color: Theme.ink
                        font.family: Theme.fontSans
                        font.pixelSize: 15
                        font.weight: Font.DemiBold
                        Accessible.role: Accessible.Heading
                    }
                    // On the durations page: what is on now ("On until 15:40").
                    Text {
                        Layout.fillWidth: true
                        visible: centre.page === 'dnd'
                        text: NotificationService.dndDetail
                        color: Theme.inkMuted
                        font.family: Theme.fontSans
                        font.pixelSize: 12
                        font.features: { 'tnum': 1 }
                    }
                }
                Text {
                    visible: centre.page === 'main' && NotificationService.count > 0
                    Layout.rightMargin: Theme.space2
                    text: NotificationService.count
                    color: Theme.inkSubtle
                    font.family: Theme.fontSans
                    font.pixelSize: 13
                    font.features: { 'tnum': 1 }
                }
            }

            // ---- do not disturb ----------------------------------------------------------
            MenuLine {
                id: dndLine
                menu: centre
                visible: centre.page === 'main' && centre.owned
                stop: 'dnd'
                icon: DndService.active ? 'bell-off' : 'moon'
                label: 'Do not disturb'
                detail: NotificationService.dndDetail
                ArcticSwitch {
                    checked: DndService.active
                    focusPolicy: Qt.NoFocus
                    Accessible.name: 'Do not disturb'
                    onToggled: DndService.set(checked ? 'on' : 'off')
                }
                ArcticButton {
                    variant: 'ghost'
                    size: 'sm'
                    iconOnly: true
                    iconName: 'chevron-right'
                    label: 'How long'
                    focusPolicy: Qt.NoFocus
                    onClicked: centre.openDurations()
                }
            }
            Repeater {
                model: centre.page === 'dnd' ? centre.durations : []
                MenuLine {
                    required property var modelData
                    menu: centre
                    stop: modelData.key
                    icon: modelData.icon
                    label: modelData.label
                    detail: modelData.detail || ''
                    checked: modelData.command === 'on' ? NotificationService.dndReason === 'on'
                           : modelData.command === 'off' ? !NotificationService.dndActive : false
                    onClicked: centre.activate(modelData.key)
                }
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.topMargin: Theme.space1
                visible: centre.page === 'main'
                implicitHeight: 1
                color: Theme.line
            }

            // ---- the notifications -------------------------------------------------------
            Flickable {
                id: flick
                Layout.fillWidth: true
                visible: centre.page === 'main'
                Layout.preferredHeight: Math.min(list.implicitHeight, centre.height - 2 * Theme.space4 - Theme.frameWidth - centre.fixedHeight)
                contentHeight: list.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds

                ColumnLayout {
                    id: list
                    width: flick.width
                    spacing: 0

                    // Nothing here, or another daemon has the name.
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.margins: Theme.space5
                        visible: centre.groups.length === 0
                        spacing: Theme.space2
                        Icon {
                            Layout.alignment: Qt.AlignHCenter
                            name: centre.owned ? 'bell' : 'alert'
                            size: 28
                            color: Theme.inkSubtle
                        }
                        Text {
                            Layout.fillWidth: true
                            horizontalAlignment: Text.AlignHCenter
                            text: centre.owned ? 'No notifications' : 'Another notification service is running (' + NotificationService.foreign + ')'
                            textFormat: Text.PlainText
                            wrapMode: Text.Wrap
                            color: Theme.ink
                            font.family: Theme.fontSans
                            font.pixelSize: 15
                            font.weight: Font.DemiBold
                        }
                        Text {
                            Layout.fillWidth: true
                            horizontalAlignment: Text.AlignHCenter
                            text: centre.owned ? 'New ones appear here, including those that arrive while do not disturb is on.'
                                               : 'Arctic’s notification centre is off. Quit the other service and log in again to use it.'
                            wrapMode: Text.Wrap
                            color: Theme.inkMuted
                            font.family: Theme.fontSans
                            font.pixelSize: 13
                            lineHeight: 1.2
                        }
                    }

                    Repeater {
                        model: centre.groups
                        ColumnLayout {
                            id: groupBlock
                            required property var modelData
                            required property int index
                            readonly property bool open: centre.isOpen(modelData, index)
                            readonly property var first: modelData.items[0]
                            Layout.fillWidth: true
                            Layout.leftMargin: Theme.space1
                            Layout.rightMargin: Theme.space1
                            Layout.topMargin: index === 0 ? Theme.space1 : 0
                            spacing: 2

                            // App header: icon, name, count, clear.
                            MenuLine {
                                menu: centre
                                Layout.leftMargin: 0
                                Layout.rightMargin: 0
                                stop: 'g:' + groupBlock.modelData.key
                                imageSource: NotificationService.appIconFor(groupBlock.first)
                                icon: 'bell'
                                label: NotificationService.appNameFor(groupBlock.first)
                                labelSize: 13
                                labelWeight: Font.DemiBold
                                rowHeight: 34
                                trailingText: groupBlock.modelData.items.length > 1 ? String(groupBlock.modelData.items.length) : ''
                                onClicked: centre.setFolded(groupBlock.modelData.key, groupBlock.open)
                                ArcticButton {
                                    variant: 'ghost'
                                    size: 'sm'
                                    iconOnly: true
                                    iconName: 'x'
                                    label: 'Clear ' + NotificationService.appNameFor(groupBlock.first)
                                    focusPolicy: Qt.NoFocus
                                    onClicked: NotificationService.clearGroup(groupBlock.modelData.key)
                                }
                            }
                            // Folded: one stacked card ("5 from Signal").
                            Rectangle {
                                visible: !groupBlock.open
                                Layout.fillWidth: true
                                Layout.bottomMargin: Theme.space1
                                implicitHeight: stacked.implicitHeight + 2 * Theme.space3
                                radius: Theme.radiusMd
                                color: stackedMouse.containsMouse ? Theme.surfaceSunken : Theme.surface
                                border.width: 1
                                border.color: Theme.line
                                ColumnLayout {
                                    id: stacked
                                    anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: Theme.space3 }
                                    spacing: 2
                                    Text {
                                        Layout.fillWidth: true
                                        text: groupBlock.first ? groupBlock.first.summary || groupBlock.first.body : ''
                                        textFormat: Text.PlainText
                                        elide: Text.ElideRight
                                        color: Theme.ink
                                        font.family: Theme.fontSans
                                        font.pixelSize: 13
                                        font.weight: Font.DemiBold
                                    }
                                    Text {
                                        text: groupBlock.modelData.items.length + ' from ' + NotificationService.appNameFor(groupBlock.first)
                                        textFormat: Text.PlainText
                                        color: Theme.inkMuted
                                        font.family: Theme.fontSans
                                        font.pixelSize: 12
                                        font.features: { 'tnum': 1 }
                                    }
                                }
                                MouseArea {
                                    id: stackedMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: centre.setFolded(groupBlock.modelData.key, false)
                                }
                            }
                            // Open: every card.
                            Repeater {
                                model: groupBlock.open ? groupBlock.modelData.items : []
                                Rectangle {
                                    id: cardBox
                                    required property var modelData
                                    readonly property string stop: 'n:' + modelData.id
                                    readonly property bool isCurrent: centre.current === stop
                                    Layout.fillWidth: true
                                    Layout.bottomMargin: Theme.space1
                                    implicitHeight: card.implicitHeight + 2 * Theme.space3
                                    radius: Theme.radiusMd
                                    color: (cardBox.isCurrent && centre.keyboardNav) || cardHover.hovered ? Theme.surfaceSunken : Theme.surface
                                    border.width: 1
                                    border.color: Theme.line
                                    Component.onCompleted: centre.register(stop, cardBox)
                                    FocusRing { targetRadius: Theme.radiusMd; shown: cardBox.isCurrent && centre.keyboardNav && centre.currentAction < 0 }
                                    HoverHandler { id: cardHover }
                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: { centre.close(); NotificationService.activate(cardBox.modelData.id); }
                                    }
                                    NotificationCard {
                                        id: card
                                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: Theme.space3 }
                                        entry: cardBox.modelData
                                        showApp: false
                                        expanded: cardBox.isCurrent && centre.keyboardNav
                                        keyboardNav: centre.keyboardNav && cardBox.isCurrent
                                        currentAction: cardBox.isCurrent ? centre.currentAction : -1
                                        onActionInvoked: identifier => NotificationService.invokeAction(cardBox.modelData.id, identifier)
                                    }
                                    ArcticButton {
                                        anchors { right: parent.right; top: parent.top; margins: Theme.space2 }
                                        visible: cardHover.hovered
                                        variant: 'ghost'
                                        size: 'sm'
                                        iconOnly: true
                                        iconName: 'x'
                                        label: 'Dismiss'
                                        tooltip: ''
                                        focusPolicy: Qt.NoFocus
                                        onClicked: NotificationService.remove(cardBox.modelData.id)
                                    }
                                }
                            }
                        }
                    }
                    Item { implicitHeight: Theme.space1 }
                }
            }

            // ---- footer ------------------------------------------------------------------
            Rectangle {
                Layout.fillWidth: true
                visible: centre.page === 'main'
                implicitHeight: 1
                color: Theme.line
            }
            RowLayout {
                id: footerRow
                Layout.fillWidth: true
                Layout.margins: Theme.space2
                visible: centre.page === 'main'
                spacing: Theme.space2
                FooterButton {
                    menu: centre
                    stop: 'clear'
                    visible: centre.groups.length > 0
                    text: 'Clear all'
                    iconName: 'trash'
                }
                Item { Layout.fillWidth: true }
                FooterButton {
                    menu: centre
                    stop: 'settings'
                    text: 'Notification settings'
                    iconName: 'sliders'
                }
            }
            Item { visible: centre.page === 'dnd'; implicitHeight: Theme.space1 }
        }
    }

    // A ghost button in the footer that is also a keyboard stop.
    // (Inline components don't see this file's ids, so each gets `menu: centre`.)
    component FooterButton: ArcticButton {
        id: footerButton
        required property var menu
        required property string stop
        variant: 'ghost'
        size: 'sm'
        focusPolicy: Qt.NoFocus
        onClicked: menu.activate(stop)
        FocusRing { targetRadius: Theme.radiusMd; shown: footerButton.menu.keyboardNav && footerButton.menu.current === footerButton.stop }
    }

    // One menu row (34px, or 44px with a detail line): icon, label, detail, trailing controls.
    component MenuLine: Rectangle {
        id: line
        required property var menu
        required property string stop
        property string icon: ''
        property string imageSource: ''
        property string label: ''
        property string detail: ''
        property string trailingText: ''
        property bool checked: false
        property int labelSize: 15
        property int labelWeight: Font.Normal
        property int rowHeight: detail !== '' ? 44 : 34
        default property alias trailing: trail.data
        readonly property bool isCurrent: menu.current === stop
        signal clicked()
        Layout.fillWidth: true
        Layout.leftMargin: Theme.space1
        Layout.rightMargin: Theme.space1
        implicitHeight: rowHeight
        radius: Theme.radiusSm
        color: (isCurrent && menu.keyboardNav) || lineHover.hovered ? Theme.surfaceSunken : 'transparent'
        Component.onCompleted: menu.register(stop, line)
        Accessible.role: Accessible.MenuItem
        Accessible.name: label + (detail ? ', ' + detail : '')
        FocusRing { targetRadius: Theme.radiusSm; shown: line.isCurrent && line.menu.keyboardNav }
        HoverHandler { id: lineHover }
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: { line.menu.select(line.stop); line.clicked(); }
        }
        RowLayout {
            anchors { fill: parent; leftMargin: Theme.space3; rightMargin: Theme.space1 }
            spacing: Theme.space2
            Item {
                implicitWidth: 18
                implicitHeight: 18
                RoundedImage {
                    id: lineImage
                    anchors.fill: parent
                    radius: Theme.radiusXs
                    source: line.imageSource
                    sourceSize: Qt.size(36, 36)
                    fillMode: Image.PreserveAspectFit
                    visible: status === Image.Ready
                }
                Icon {
                    anchors.fill: parent
                    visible: lineImage.status !== Image.Ready
                    name: line.icon || 'bell'
                    size: 18
                    color: Theme.ink
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                Text {
                    Layout.fillWidth: true
                    text: line.label
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    color: Theme.ink
                    font.family: Theme.fontSans
                    font.pixelSize: line.labelSize
                    font.weight: line.labelWeight
                }
                Text {
                    Layout.fillWidth: true
                    visible: line.detail !== ''
                    text: line.detail
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    color: Theme.inkMuted
                    font.family: Theme.fontSans
                    font.pixelSize: 12
                    font.features: { 'tnum': 1 }
                }
            }
            Text {
                visible: line.trailingText !== ''
                text: line.trailingText
                textFormat: Text.PlainText
                color: Theme.inkSubtle
                font.family: Theme.fontSans
                font.pixelSize: 12
                font.features: { 'tnum': 1 }
            }
            Icon {
                visible: line.checked
                name: 'check'
                size: 16
                color: Theme.accentText
            }
            RowLayout {
                id: trail
                spacing: Theme.space1
            }
        }
    }
}
