pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import QtQml.Models
import Quickshell

// A tray icon's menu (StatusNotifierItem DBusMenu), drawn by the shell with QsMenuOpener
// instead of Qt's stock QMenu: separators, disabled entries, check boxes and radio items, and
// submenus as pages with a back row. Each level keeps its own opener, so the entries of the
// levels above stay loaded. Fedora 44's Quickshell snapshot can drop DBusMenu updates, so the
// menu is read afresh on every open (the panel is created per open); an app that publishes no
// menu gets its default action (or, when it has none, a line saying so).
FocusScope {
    id: panel
    property var menu: null
    readonly property var item: menu && menu.options ? menu.options.item : null
    property var stack: []              // submenu entries opened, innermost last
    readonly property var opener: stack.length && levels.count === stack.length ? levels.objectAt(stack.length - 1) : rootOpener
    property bool empty: false
    property real widest: 0

    implicitWidth: Math.max(200, Math.min(320, widest + 2 * Theme.space1))
    implicitHeight: list.implicitHeight

    // Mnemonics: "_Open" → "Open", "__" → "_".
    function clean(text) { return String(text || '').replace(/__/g, '\u0000').replace(/_/g, '').replace(/\u0000/g, '_'); }
    function run(entry) {
        if (!entry || !entry.enabled) return;
        if (entry.hasChildren) {
            stack = stack.concat([entry]);
            Qt.callLater(() => list.start());
            return;
        }
        entry.triggered();
        if (menu) menu.close();
    }
    function back() {
        stack = stack.slice(0, -1);
        Qt.callLater(() => list.start());
    }

    QsMenuOpener { id: rootOpener; menu: panel.item ? panel.item.menu : null }
    Instantiator {
        id: levels
        model: panel.stack
        delegate: QsMenuOpener {
            required property var modelData
            menu: modelData
        }
    }
    onItemChanged: { stack = []; empty = false; emptyCheck.restart(); }
    onStackChanged: widest = 0
    Component.onCompleted: emptyCheck.restart()
    Timer {
        id: emptyCheck
        interval: 300
        onTriggered: {
            if (rootOpener.children.values.length > 0 || panel.stack.length) return;
            if (panel.item && !panel.item.onlyMenu) { panel.item.activate(); if (panel.menu) panel.menu.close(); }
            else panel.empty = true;
        }
    }

    MenuList {
        id: list
        anchors.fill: parent
        focus: true
        isPage: panel.stack.length > 0
        onBack: panel.back()

        MenuRow {
            readonly property bool headerStop: true
            visible: panel.stack.length > 0
            icon: 'chevron-left'
            iconColor: Theme.inkMuted
            label: panel.stack.length > 1 ? panel.clean(panel.stack[panel.stack.length - 2].text)
                   : panel.item ? (panel.item.tooltipTitle || panel.item.title || 'Back') : 'Back'
            onActivated: panel.back()
        }
        MenuRow {
            visible: panel.empty
            enabled: false
            label: 'This app has no menu'
        }
        Repeater {
            model: panel.opener ? panel.opener.children : null
            Item {
                id: entryItem
                required property var modelData
                Layout.fillWidth: true
                implicitHeight: modelData.isSeparator ? sep.implicitHeight : row.implicitHeight
                // Only the row is a stop; separators start a new group.
                readonly property bool menuBreak: modelData.isSeparator
                MenuSeparator {
                    id: sep
                    visible: entryItem.modelData.isSeparator
                    width: parent.width
                }
                MenuRow {
                    id: row
                    visible: !entryItem.modelData.isSeparator
                    width: parent.width
                    enabled: entryItem.modelData.enabled
                    image: entryItem.modelData.icon || ''
                    label: panel.clean(entryItem.modelData.text)
                    toggle: entryItem.modelData.buttonType === QsMenuButtonType.CheckBox ? 'checkbox'
                            : entryItem.modelData.buttonType === QsMenuButtonType.RadioButton ? 'radio' : ''
                    checked: entryItem.modelData.checkState === Qt.Checked
                    trailing: entryItem.modelData.hasChildren ? 'chevron' : ''
                    onActivated: panel.run(entryItem.modelData)
                    Component.onCompleted: panel.widest = Math.max(panel.widest, implicitWidth)
                }
            }
        }
    }
}
