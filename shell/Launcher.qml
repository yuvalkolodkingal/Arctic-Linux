pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Quickshell
import "LauncherSearch.js" as LauncherSearch
import "Calc.js" as Calc
import "assets/Icons.js" as Icons
import "getapps"

// The launcher (design Launcher, Super+Space): a 520px frosted card that hangs from the bar
// over a scrim. Type to find apps; "=" is a calculator, ">" runs a command. With nothing
// typed it offers Apps, Get apps, Remove apps, Wallpapers, Settings and Fetch (the original
// shell's), and on the live USB "Install Arctic Linux" first. Keyboard first: ↑/↓ or Tab move,
// Enter opens, Esc goes back or closes; Shift+Delete (or Delete at the end of the text) removes
// the selected app after a confirmation (getapps/RemoveSheet). Get apps is a set of pages inside
// the card (getapps/GetApps.qml). The card can be dragged to any screen edge, where it docks.
Popover {
    id: launcher
    required property var shell
    property string view: 'home'        // home, apps (every app), get (Get apps, see getapps/GetApps.qml)
    property string getPage: 'choose'   // the Get apps page to open with, and what to type there
    property string getQuery: ''
    property string query: ''
    property int current: 0
    readonly property var parsed: LauncherSearch.mode(query)

    layerName: 'arctic-launcher'
    focusItem: view === 'get' ? getApps.inputItem : field
    cardWidth: view === 'get' ? Math.min(getApps.preferredWidth, width - 32) : 520
    cardHeight: view === 'get' ? Math.min(getApps.preferredHeight, height - 32) : Math.min(layout.implicitHeight + 2 * Theme.space3, height - 32)

    function openView(name, page, text) {
        removeSheet.close();
        view = name;
        query = '';
        field.text = '';
        current = 0;
        if (name === 'get') getApps.open(page || 'choose', text || ''); else field.forceActiveFocus();
    }
    function setQuery(text) {
        if (view === 'get') openView('home');
        field.text = text;
        field.cursorPosition = text.length;
    }
    function back() {
        if (view !== 'home') openView('home');
        else close();
    }
    onOpened: openView(view === 'get' ? 'get' : 'home', getPage, getQuery)
    onDismissed: removeSheet.close()
    // Delete on an app row: find where the app came from, then ask (not on the live USB).
    function askRemove(entryOrId) {
        const id = typeof entryOrId === 'string' ? entryOrId : entryOrId && entryOrId.id;
        if (!id || Session.live) return;
        AppsService.helper(['owner', id], r => {
            if (!launcher.open) return;
            if (!r.ok) { removeSheet.openFor({ source: 'unknown', name: id, blocked: { code: r.code, message: r.error } }); return; }
            if (r.source === 'webapp') AppsService.web.start();
            removeSheet.openFor(r);
        });
    }
    Binding { target: AppsService; property: 'watching'; value: launcher.open && launcher.view === 'get' }

    // ---- results --------------------------------------------------------------------------
    readonly property var specials: {
        const list = [];
        if (Session.live) list.push({ kind: 'install', name: 'Install Arctic Linux', desc: 'Put Arctic Linux on this computer · Super + I', tile: 'installer', keywords: 'installer setup disk' });
        list.push({ kind: 'apps', name: 'Apps', desc: 'Every app on this computer', glyph: 'grid', keywords: 'applications programs all' });
        list.push({ kind: 'get', name: 'Get apps', desc: 'Install from Flathub, Fedora or the web', glyph: 'package', keywords: 'install software packages dnf flatpak flathub store web app terminal' });
        if (!Session.live) list.push({ kind: 'remove', name: 'Remove apps', desc: 'Uninstall Flatpak apps, Fedora packages and web apps', glyph: 'trash', keywords: 'uninstall delete remove flatpak dnf web app' });
        list.push({ kind: 'wallpapers', name: 'Wallpapers', desc: 'Change the desktop picture', glyph: 'image', keywords: 'background picture desktop' });
        list.push({ kind: 'settings', name: 'Settings', desc: 'Appearance, displays, keyboard, apps and more · Super + S', glyph: 'sliders', keywords: 'preferences control panel options configure theme' });
        list.push({ kind: 'fetch', name: 'Fetch', desc: 'The Arctic greeting in a terminal', glyph: 'terminal', keywords: 'fastfetch neofetch system info' });
        return list;
    }
    readonly property var apps: DesktopEntries.applications.values
        .filter(e => !e.noDisplay)
        .map(e => ({ kind: 'app', entry: e, name: e.name, desc: e.genericName || e.comment || '',
                     keywords: [e.genericName, e.comment].concat(e.keywords || []).concat(e.categories || []).join(' '),
                     // Web apps and terminal apps keep their own icons (a TUI called "Settings
                     // monitor" isn't Settings).
                     tile: e.id.startsWith('org.arcticlinux.WebApp.') || e.id.startsWith('org.arcticlinux.TerminalApp.') ? '' : Icons.tileFor(e.id, e.name),
                     icon: e.icon }))
    readonly property var results: {
        if (parsed.mode === 'calc') {
            const calc = Calc.evaluate(parsed.text);
            return [calc.ok ? { kind: 'calc', name: calc.text, desc: '= ' + parsed.text + ' · Enter copies the result', glyph: 'hash' }
                            : { kind: 'none', name: parsed.text ? 'Can’t work that out' : 'Calculator', desc: calc.error, glyph: 'hash' }];
        }
        if (parsed.mode === 'command')
            return [parsed.text ? { kind: 'command', name: parsed.text, desc: 'Run this command · Shift + Enter runs it in a terminal', glyph: 'prompt' }
                                : { kind: 'none', name: 'Run a command', desc: 'Type a command after >, like > htop', glyph: 'prompt' }];
        if (view === 'apps') return withGetSearch(LauncherSearch.rank(apps, parsed.text));
        if (!parsed.text) return specials;
        // Settings is one of the specials, so its desktop entry would show twice.
        return withGetSearch(LauncherSearch.rank(specials.concat(apps.filter(a => a.entry.id !== 'org.arcticlinux.Settings')), parsed.text).slice(0, 50));
    }
    // No app found: offer to look for it in Get apps.
    function withGetSearch(found) {
        if (!parsed.text || found.some(r => r.kind === 'app')) return found;
        return found.concat([{ kind: 'get-search', name: 'Find “' + parsed.text + '” in Get apps', desc: 'Search Flathub and Fedora', glyph: 'package' }]);
    }
    onResultsChanged: current = Math.min(current, Math.max(0, results.length - 1))

    // Terminal apps, Fetch and Shift+Enter commands open in the terminal picked in the
    // installer (arctic-open reads /etc/arctic/default-apps), which need not be kitty.
    function inTerminal(command, hold) {
        return ['arctic-open', 'terminal'].concat(hold ? ['--hold'] : [], ['-e'], command);
    }
    function activate(item, alternate) {
        if (!item) return;
        switch (item.kind) {
        case 'app':
            if (item.entry.runInTerminal)
                Quickshell.execDetached({ command: inTerminal(item.entry.command, false), workingDirectory: item.entry.workingDirectory || Session.home });
            else
                item.entry.execute();
            close();
            break;
        case 'apps': openView('apps'); break;
        case 'get': openView('get'); break;
        case 'remove': openView('get', 'remove'); break;
        case 'get-search': openView('get', 'flatpak', parsed.text); break;
        case 'wallpapers': close(); shell.openWallpapers(launcher.screen); break;
        case 'settings': Quickshell.execDetached(['arctic-settings']); close(); break;
        case 'fetch': Quickshell.execDetached(inTerminal(['arctic-fetch'], true)); close(); break;
        case 'install': Quickshell.execDetached(['arctic-start-installer']); close(); break;
        case 'calc': Quickshell.execDetached(['wl-copy', '--', item.name]); close(); break;
        case 'command':
            if (alternate) Quickshell.execDetached(inTerminal(['sh', '-c', item.name], true));
            else Quickshell.execDetached(['sh', '-c', item.name]);
            close();
            break;
        }
    }
    function move(delta) {
        if (!results.length) return;
        current = (current + delta + results.length) % results.length;
        list.positionViewAtIndex(current, ListView.Contain);
    }

    // ---- card ---------------------------------------------------------------------------
    ColumnLayout {
        id: layout
        anchors.fill: parent
        anchors.margins: Theme.space3
        anchors.topMargin: Theme.space3
        spacing: Theme.space2

        DragHandle {
            Layout.fillWidth: true
            Layout.topMargin: -Theme.space3
            Layout.bottomMargin: -Theme.space2
            implicitHeight: Theme.space3
            windowX: launcher.card.x
            windowY: launcher.card.y
            onMoved: (nextX, nextY) => launcher.dock.moveTo(nextX, nextY)
        }

        GetApps {
            id: getApps
            visible: launcher.view === 'get'
            Layout.fillWidth: true
            Layout.fillHeight: true
            onBackRequested: launcher.openView('home')
            onCloseRequested: launcher.close()
        }

        ColumnLayout {
            id: column
            visible: launcher.view !== 'get'
            Layout.fillWidth: true
            spacing: Theme.space2

            // Query row: 44px, surface-raised, 1px line inset.
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
                    Icon {
                        name: launcher.view === 'apps' ? 'grid' : launcher.parsed.mode === 'calc' ? 'hash' : launcher.parsed.mode === 'command' ? 'prompt' : 'search'
                        size: 20
                        color: Theme.inkMuted
                    }
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
                        onTextChanged: { launcher.query = text; launcher.current = 0; }
                        Keys.onDownPressed: launcher.move(1)
                        Keys.onUpPressed: launcher.move(-1)
                        Keys.onTabPressed: launcher.move(1)
                        Keys.onBacktabPressed: launcher.move(-1)
                        Keys.onEscapePressed: { if (field.text && launcher.view === 'home') field.text = ''; else launcher.back(); }
                        // Shift+Delete, or Delete with the cursor at the end: remove the selected app.
                        Keys.onDeletePressed: event => {
                            const item = launcher.results[launcher.current];
                            if (item && item.kind === 'app' && !Session.live
                                && ((event.modifiers & Qt.ShiftModifier) || field.cursorPosition === field.text.length)) {
                                launcher.askRemove(item.entry);
                                event.accepted = true;
                            } else {
                                event.accepted = false;
                            }
                        }
                        Keys.onReturnPressed: event => launcher.activate(launcher.results[launcher.current], event.modifiers & Qt.ShiftModifier)
                        Keys.onEnterPressed: event => launcher.activate(launcher.results[launcher.current], event.modifiers & Qt.ShiftModifier)
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            visible: !field.text
                            text: launcher.view === 'apps' ? 'Search every app' : 'Search apps, or type = to calculate'
                            color: Theme.inkSubtle
                            font: field.font
                        }
                    }
                    Text {
                        text: launcher.results.length === 1 ? '1 result' : launcher.results.length + ' results'
                        visible: launcher.parsed.mode === 'search' && (launcher.query !== '' || launcher.view === 'apps')
                        color: Theme.inkSubtle
                        font.family: Theme.fontSans
                        font.pixelSize: 12
                        font.weight: Font.Medium
                    }
                }
            }

            ListView {
                id: list
                Layout.fillWidth: true
                implicitHeight: Math.min(contentHeight, 7 * 54)
                Layout.preferredHeight: implicitHeight
                visible: count > 0
                clip: true
                spacing: 2
                model: launcher.results
                currentIndex: launcher.current
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: list.contentHeight > list.height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff }
                delegate: Rectangle {
                    id: row
                    required property var modelData
                    required property int index
                    readonly property bool selected: index === launcher.current
                    width: list.width
                    height: 52
                    radius: Theme.radiusMd
                    color: selected ? Theme.accentSoft : rowMouse.containsMouse ? Theme.surfaceSunken : 'transparent'
                    Behavior on color { ColorAnimation { duration: Theme.durationFast } }
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Theme.space3
                        anchors.rightMargin: Theme.space3
                        spacing: Theme.space3
                        AppTile {
                            size: 36
                            tileId: row.modelData.tile || ''
                            iconName: row.modelData.icon || ''
                            fallbackGlyph: row.modelData.glyph || 'grid'
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            Text {
                                Layout.fillWidth: true
                                text: row.modelData.name
                                color: Theme.ink
                                font.family: row.modelData.kind === 'command' ? Theme.fontMono : Theme.fontSans
                                font.pixelSize: 15
                                font.weight: Font.DemiBold
                                font.features: { 'tnum': 1 }
                                elide: Text.ElideRight
                            }
                            Text {
                                Layout.fillWidth: true
                                visible: text !== ''
                                text: row.modelData.desc
                                color: Theme.inkMuted
                                font.family: Theme.fontSans
                                font.pixelSize: 12
                                elide: Text.ElideRight
                            }
                        }
                        Kbd { visible: row.selected && row.modelData.kind !== 'none'; text: 'Enter' }
                    }
                    MouseArea {
                        id: rowMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        acceptedButtons: Qt.LeftButton | Qt.RightButton
                        cursorShape: Qt.PointingHandCursor
                        onPositionChanged: launcher.current = row.index
                        onClicked: mouse => {
                            if (mouse.button === Qt.RightButton) { if (row.modelData.kind === 'app') launcher.askRemove(row.modelData.entry); }
                            else launcher.activate(row.modelData, mouse.modifiers & Qt.ShiftModifier);
                        }
                    }
                    // Remove this app (the same as Delete), on the hovered or selected app row.
                    ArcticButton {
                        anchors.right: parent.right
                        anchors.rightMargin: Theme.space3 + 52
                        anchors.verticalCenter: parent.verticalCenter
                        visible: row.modelData.kind === 'app' && !Session.live && (row.selected || rowMouse.containsMouse)
                        variant: 'ghost'; size: 'sm'; iconName: 'trash'; iconOnly: true; label: 'Remove app'
                        focusPolicy: Qt.NoFocus
                        onClicked: launcher.askRemove(row.modelData.entry)
                    }
                }
            }
            Text {
                Layout.fillWidth: true
                Layout.topMargin: Theme.space2
                Layout.bottomMargin: Theme.space2
                visible: list.count === 0
                horizontalAlignment: Text.AlignHCenter
                text: 'No apps match “' + launcher.parsed.text + '”'
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
                Hint { label: launcher.view === 'home' ? 'close' : 'back'; keys: [ Kbd { text: 'Esc' } ] }
                Hint {
                    id: removeHint
                    label: 'remove'
                    keys: [ Kbd { text: 'Delete' } ]
                    visible: !Session.live && !!launcher.results[launcher.current] && launcher.results[launcher.current].kind === 'app'
                }
                Item { Layout.fillWidth: true }
                // (they make room for "remove" while an app is selected)
                Hint { label: 'calculator'; visible: !removeHint.visible; keys: [ Kbd { text: '=' } ] }
                Hint { label: 'command'; visible: !removeHint.visible; keys: [ Kbd { text: '>' } ] }
            }
        }
    }

    // Delete on an app row asks here, over the card.
    RemoveSheet {
        id: removeSheet
        onClosed: field.forceActiveFocus()
    }
}
