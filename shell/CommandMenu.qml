pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import "MenuModel.js" as MenuModel
import "assets/Icons.js" as Icons

// The command menu (Super + Alt + Space): every system action in one keyboard-driven tree
// (Apps, Learn, Capture, Toggle, Style, Setup, Install, Remove, Update, System), after
// Omarchy's menu. The rows are data (menu/*.json, then ~/.config/arctic/menu.json)
// and MenuModel.js makes the tree; a row whose command isn't installed is hidden. Type to
// search everything under the branch you're in. ↑/↓ move, Enter or → opens, ← or Backspace
// goes up, Esc closes (from a branch it was opened at, e.g. Capture on Super + Ctrl + C).
// The card hangs from the bar like the launcher and docks to any edge the same way.
Popover {
    id: menu
    property string branch: ''          // the branch shown ('' = the top)
    property string home: ''            // the branch it was opened at
    property string query: ''
    property int current: 0
    property var model: MenuModel.build({}, {})
    property var ctx: MenuModel.context(false, false)
    property var pending: null
    property var shippedFiles: []
    property string mineText: ''
    property var pendingRun: null
    readonly property var view: Object.assign({}, ctx, { live: Session.live, dark: Theme.dark, outputs: Quickshell.screens.length })
    readonly property var extra: ({
        settingsPages: SettingsIndex.pages,
        // Every window on every workspace (Open windows), only while the menu is open.
        windows: open ? ToplevelManager.toplevels.values.map(t => {
            const entry = t.appId ? DesktopEntries.heuristicLookup(t.appId) : null;
            return { title: t.title, appName: entry ? entry.name : t.appId, ref: t };
        }) : []
    })
    readonly property var rows: query.trim() ? MenuModel.search(model, branch, query, view, extra)
                                             : MenuModel.rows(model, branch, view, extra)
    readonly property var trail: MenuModel.trail(model, branch)

    layerName: 'arctic-command'
    cardWidth: 460
    cardHeight: Math.min(layout.implicitHeight + 2 * Theme.space3, height - 32)
    focusItem: field

    // Where to open (shell.qml calls this before presenting it): '' or a path like "capture".
    function show(path) {
        const at = MenuModel.locate(model, path) || { branch: '', select: '' };
        home = at.branch;
        enter(at.branch, at.select);
    }
    function search(text) {
        field.text = text;
        field.cursorPosition = text.length;
    }
    function isAt(path) {
        const at = MenuModel.locate(model, path);
        return open && at !== null && home === at.branch;
    }
    function enter(id, select) {
        branch = id;
        field.text = '';
        query = '';
        let at = 0;
        const list = MenuModel.rows(model, id, view, extra);
        for (let i = 0; i < list.length; i++) if (list[i].id === select) at = i;
        current = at;
        list_.positionViewAtIndex(current, ListView.Contain);
    }
    function up() {
        if (!branch) return false;
        const from = branch;
        enter(MenuModel.parentOf(branch), from);
        return true;
    }
    function move(delta) {
        if (!rows.length) return;
        current = (current + delta + rows.length) % rows.length;
        list_.positionViewAtIndex(current, ListView.Contain);
    }
    function activate(row) {
        if (!row) return;
        if (row.kind === 'branch') { enter(row.id, ''); return; }
        if (row.kind === 'link') { enter(row.go, ''); return; }
        if (row.window) { close(); row.window.activate(); return; }
        // Run it once the card is gone, so screenshots and pickers don't catch it.
        pendingRun = row.run;
        close();
    }
    onShownChanged: if (!shown && pendingRun) runLater.restart()
    Timer {
        id: runLater
        interval: 120
        onTriggered: {
            const run = menu.pendingRun;
            menu.pendingRun = null;
            if (Array.isArray(run) && run.length) Quickshell.execDetached({ command: run, workingDirectory: Session.home });
            else if (typeof run === 'string' && run.trim()) Quickshell.execDetached({ command: ['sh', '-c', run], workingDirectory: Session.home });
        }
    }
    onOpened: refreshGuards()
    onRowsChanged: current = Math.min(current, Math.max(0, rows.length - 1))

    // ---- data and guards ----------------------------------------------------------------
    function rebuild() {
        // A shipped file with an error is left out (and said so), not the whole menu.
        const files = [];
        shippedFiles.forEach(text => {
            try { files.push(MenuModel.parse(text)); } catch (e) { console.warn('Arctic: a command menu file has an error:', e); }
        });
        model = MenuModel.build(files, mineText);
    }
    onModelChanged: refreshGuards()
    // One sh script checks every guard and state; while it runs, what it has found so far is
    // laid over the last results (no flicker), and when it ends its results replace them.
    function refreshGuards() {
        if (guards.running || !model.order.length) return;
        pending = MenuModel.context(Session.live, Theme.dark);
        guards.command = ['sh', '-c', MenuModel.guardScript(model, { shellDir: Quickshell.shellDir })];
        guards.running = true;
    }
    function publish(final) {
        const fresh = menu.pending;
        if (!fresh) return;
        if (final) {
            fresh.ready = true;
            menu.ctx = Object.assign({}, fresh);
            return;
        }
        const old = menu.ctx;
        menu.ctx = Object.assign({}, fresh, {
            ready: old.ready,
            commands: Object.assign({}, old.commands, fresh.commands),
            tests: Object.assign({}, old.tests, fresh.tests),
            ipc: Object.assign({}, old.ipc, fresh.ipc),
            states: Object.assign({}, old.states, fresh.states),
            providers: Object.assign({}, old.providers, fresh.providers)
        });
    }
    Process {
        id: guards
        stdout: SplitParser {
            onRead: line => {
                if (menu.pending) MenuModel.readGuard(menu.pending, line);
                publishSoon.restart();
            }
        }
        onExited: {
            publishSoon.stop();
            menu.publish(true);
        }
    }
    Timer { id: publishSoon; interval: 30; onTriggered: menu.publish(false) }
    // Every menu/*.json, in name order, as one stream: "\x1e<name>" then the file.
    Process {
        command: ['sh', '-c', 'for f in "$1"/menu/*.json; do [ -f "$f" ] && printf "\\036%s\\n" "${f##*/}" && cat -- "$f"; done', 'sh', Quickshell.shellDir]
        running: true
        stdout: StdioCollector {
            onStreamFinished: {
                menu.shippedFiles = text.split('\x1e').filter(part => part.trim() !== '').map(part => part.slice(part.indexOf('\n') + 1));
                menu.rebuild();
            }
        }
    }
    FileView {
        path: Session.arcticConfig + '/menu.json'
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: { menu.mineText = text(); menu.rebuild(); }
        onLoadFailed: if (menu.mineText !== '') { menu.mineText = ''; menu.rebuild(); }
    }

    // ---- card ---------------------------------------------------------------------------
    ColumnLayout {
        id: layout
        anchors.fill: parent
        anchors.margins: Theme.space3
        spacing: Theme.space2

        DragHandle {
            Layout.fillWidth: true
            Layout.topMargin: -Theme.space3
            Layout.bottomMargin: -Theme.space2
            implicitHeight: Theme.space3
            windowX: menu.card.x
            windowY: menu.card.y
            onMoved: (nextX, nextY) => menu.dock.moveTo(nextX, nextY)
        }

        // Where you are: "Menu", "Menu › Capture".
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: Theme.space1
            spacing: Theme.space1
            Repeater {
                model: ['Menu'].concat(menu.trail)
                RowLayout {
                    id: crumb
                    required property string modelData
                    required property int index
                    spacing: Theme.space1
                    Icon { visible: crumb.index > 0; name: 'chevron-right'; size: 12; color: Theme.inkSubtle }
                    Text {
                        text: crumb.modelData.toUpperCase()
                        color: crumb.index === menu.trail.length ? Theme.ink : Theme.inkMuted
                        font.family: Theme.fontSans
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                        font.letterSpacing: 0.88
                    }
                }
            }
            Item { Layout.fillWidth: true }
        }

        // Search row: 44px, surface-raised, 1px line inset (as in the launcher).
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: Theme.controlLg
            radius: Theme.radiusMd
            color: Theme.surfaceRaised
            border.width: 1
            border.color: Theme.line
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.space3
                anchors.rightMargin: Theme.space3
                spacing: Theme.space3
                Icon { name: 'search'; size: 20; color: Theme.inkMuted }
                TextInput {
                    id: field
                    Layout.fillWidth: true
                    color: Theme.ink
                    font.family: Theme.fontSans
                    font.pixelSize: 17
                    selectionColor: Theme.selection
                    selectedTextColor: Theme.ink
                    cursorDelegate: Rectangle { width: 1.5; color: Theme.accentEdge; visible: field.cursorVisible }
                    clip: true
                    focus: true
                    onTextChanged: { menu.query = text; menu.current = 0; }
                    Keys.onDownPressed: menu.move(1)
                    Keys.onUpPressed: menu.move(-1)
                    Keys.onTabPressed: menu.move(1)
                    Keys.onBacktabPressed: menu.move(-1)
                    Keys.onReturnPressed: menu.activate(menu.rows[menu.current])
                    Keys.onEnterPressed: menu.activate(menu.rows[menu.current])
                    Keys.onRightPressed: event => {
                        const row = menu.rows[menu.current];
                        if (!field.text && row && row.kind !== 'action') menu.activate(row);
                        else event.accepted = false;
                    }
                    Keys.onLeftPressed: event => { if (field.text || !menu.up()) event.accepted = false; }
                    Keys.onPressed: event => {
                        if (event.key === Qt.Key_Backspace && !field.text) { menu.up(); event.accepted = true; }
                    }
                    Keys.onEscapePressed: {
                        if (field.text) field.text = '';
                        else if (menu.branch !== menu.home) menu.up();
                        else menu.close();
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        visible: !field.text
                        text: menu.branch ? 'Search ' + menu.trail[menu.trail.length - 1] : 'Search the menu'
                        color: Theme.inkSubtle
                        font: field.font
                    }
                }
            }
        }

        ListView {
            id: list_
            Layout.fillWidth: true
            implicitHeight: Math.min(contentHeight, 10 * 42)
            Layout.preferredHeight: implicitHeight
            visible: count > 0
            clip: true
            spacing: 2
            model: menu.rows
            currentIndex: menu.current
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: list_.contentHeight > list_.height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff }
            delegate: Rectangle {
                id: row
                required property var modelData
                required property int index
                readonly property bool selected: index === menu.current
                width: list_.width
                height: 40
                radius: Theme.radiusMd
                color: selected ? Theme.accentSoft : rowMouse.containsMouse ? Theme.surfaceSunken : 'transparent'
                border.width: selected && Theme.highContrast ? Theme.lineWidth : 0      // high contrast: an edge too
                border.color: Theme.focus
                Behavior on color { ColorAnimation { duration: Theme.durationFast } }
                Accessible.role: Accessible.MenuItem
                Accessible.name: row.modelData.label + (row.modelData.checked === true ? ', on' : row.modelData.checked === false ? ', off' : '')
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.space3
                    anchors.rightMargin: Theme.space3
                    spacing: Theme.space3
                    Icon {
                        name: Icons.has(row.modelData.icon) ? row.modelData.icon : row.modelData.kind === 'branch' ? 'grid' : 'sliders'
                        size: 18
                        color: row.selected ? Theme.ink : Theme.inkMuted
                    }
                    Text {
                        text: row.modelData.label
                        color: Theme.ink
                        font.family: Theme.fontSans
                        font.pixelSize: 15
                        font.weight: Font.Medium
                        elide: Text.ElideRight
                        Layout.maximumWidth: row.width * 0.6
                    }
                    Text {
                        Layout.fillWidth: true
                        text: row.modelData.desc
                        color: Theme.inkMuted
                        font.family: Theme.fontSans
                        font.pixelSize: 12
                        elide: Text.ElideRight
                    }
                    Kbd { visible: !!row.modelData.keys; text: row.modelData.keys || '' }
                    Icon { visible: row.modelData.current === true; name: 'check'; size: 18; color: Theme.accentText }
                    ArcticSwitch {
                        visible: row.modelData.checked === true || row.modelData.checked === false
                        checked: row.modelData.checked === true
                        focusPolicy: Qt.NoFocus
                        implicitHeight: 24
                    }
                    Icon { visible: row.modelData.kind !== 'action'; name: 'chevron-right'; size: 16; color: Theme.inkMuted }
                }
                MouseArea {
                    id: rowMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onPositionChanged: menu.current = row.index
                    onClicked: menu.activate(row.modelData)
                }
            }
        }
        Text {
            Layout.fillWidth: true
            Layout.topMargin: Theme.space2
            Layout.bottomMargin: Theme.space2
            visible: list_.count === 0
            horizontalAlignment: Text.AlignHCenter
            text: menu.query.trim() ? 'Nothing in the menu matches “' + menu.query.trim() + '”' : 'Nothing here on this computer'
            color: Theme.inkMuted
            font.family: Theme.fontSans
            font.pixelSize: 13
        }

        // Footer: key hints.
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.line }
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: Theme.space3
            Layout.rightMargin: Theme.space3
            spacing: Theme.space4
            component Hint: RowLayout {
                id: hint
                property alias keys: keysRow.data
                property string label: ''
                spacing: Theme.space1
                RowLayout { id: keysRow; spacing: Theme.space1 }
                Text { text: hint.label; color: Theme.inkMuted; font.family: Theme.fontSans; font.pixelSize: 12 }
            }
            Hint { label: 'move'; keys: [ Kbd { text: '↑' }, Kbd { text: '↓' } ] }
            Hint { label: 'open'; keys: [ Kbd { text: 'Enter' } ] }
            Hint { visible: menu.branch !== ''; label: 'back'; keys: [ Kbd { text: '←' } ] }
            Item { Layout.fillWidth: true }
            Hint { label: 'close'; keys: [ Kbd { text: 'Esc' } ] }
        }
    }
}
