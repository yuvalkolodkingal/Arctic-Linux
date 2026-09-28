pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."
import "GetApps.js" as GetAppsLogic

// Get apps → Remove apps: what you can uninstall, a tab per source — Flatpak (each
// installation's copy is its own row), Fedora packages (apps with a launcher entry, or the other
// packages you added), Web apps (and the sign-in data kept after removing one) and Terminal
// apps. Packages Arctic Linux needs are listed apart, locked, with the reason. Remove… (or
// Delete / Enter) opens the confirmation (RemoveSheet), which says exactly what goes.
// Hidden on the live USB: removals there would only change the RAM overlay.
FocusScope {
    id: page
    property string initialTab: ''
    property string initialFilter: ''
    property string tab: initialTab || 'flatpak'
    property string dnfView: 'apps'                // apps | other
    property int current: 0
    property bool protectedOpen: false
    property var flatpaks: []
    property var dnfApps: []
    property var dnfOther: []
    property var dnfProtected: []
    property var terminalApps: []
    property var loaded: ({})
    property var removing: ({})                     // rows being removed: key -> true
    property string toast: ''
    property string asking: ''                      // the key of the row the sheet is for
    readonly property var webApps: AppsService.web.apps
    readonly property var kept: AppsService.web.kept
    readonly property bool showWeb: AppsService.webappPresent || webApps.length > 0 || kept.length > 0
    readonly property var tabs: {
        const list = [{ key: 'flatpak', label: 'Flatpak (' + flatpaks.length + ')' },
                      { key: 'dnf', label: 'Fedora packages (' + dnfApps.length + ')' }];
        if (showWeb) list.push({ key: 'web', label: 'Web apps (' + webApps.length + ')' });
        if (terminalApps.length) list.push({ key: 'terminal', label: 'Terminal apps (' + terminalApps.length + ')' });
        return list;
    }
    readonly property var rows: GetAppsLogic.filterRows(
        tab === 'flatpak' ? flatpaks : tab === 'dnf' ? (dnfView === 'apps' ? dnfApps : dnfOther)
        : tab === 'web' ? webApps : terminalApps, field.text)
    readonly property Item inputItem: field
    signal backRequested()

    function back() {
        if (sheet.open) { sheet.close(); return true; }
        if (field.text) { field.text = ''; return true; }
        return false;
    }
    function reopen(text, tabName) { if (tabName) tab = tabName; field.text = text || ''; field.forceActiveFocus(); }
    function refresh(which) {
        const all = !which;
        if (all || which === 'flatpak')
            AppsService.helper(['installed', 'flatpak'], r => { if (r.ok) page.flatpaks = r.apps; page.mark('flatpak'); });
        if (all || which === 'dnf') {
            AppsService.helper(['installed', 'dnf'], r => { if (r.ok) { page.dnfApps = r.apps; page.dnfProtected = r.protected; } page.mark('dnf'); });
            AppsService.helper(['installed', 'dnf', '--other'], r => { if (r.ok) page.dnfOther = r.apps; });
        }
        if (all || which === 'terminal')
            AppsService.helper(['installed', 'terminal'], r => { if (r.ok) page.terminalApps = r.apps; page.mark('terminal'); });
        if ((all || which === 'web') && AppsService.webappPresent) {
            AppsService.web.start();
            if (AppsService.web.ready) AppsService.web.list();
        }
    }
    function mark(which) { const l = Object.assign({}, loaded); l[which] = true; loaded = l; }
    function keyOf(row) {
        return tab === 'flatpak' ? 'flatpak:' + row.id + ':' + row.installation : tab === 'dnf' ? 'dnf:' + row.package : tab + ':' + row.id;
    }
    function requestFor(row) {
        if (tab === 'flatpak') return { source: 'flatpak', name: row.name, icon: row.icon, target: { id: row.id, installation: row.installation } };
        if (tab === 'dnf') return { source: 'dnf', name: row.name, icon: row.icon, target: { package: row.package } };
        if (tab === 'web') return { source: 'webapp', name: row.name, icon: row.icon_path || '', running: !!row.running, target: { id: row.id } };
        return { source: 'terminal-app', name: row.name, icon: row.icon, target: { id: row.id } };
    }
    function ask(row) {
        if (!row || removing[keyOf(row)]) return;
        asking = keyOf(row);
        sheet.openFor(requestFor(row));
    }
    function move(delta) {
        if (!rows.length) return;
        current = (current + delta + rows.length) % rows.length;
        list.positionViewAtIndex(current, ListView.Contain);
    }
    function showToast(text) { toast = text; toastTimer.restart(); }

    Component.onCompleted: { field.text = initialFilter; refresh(); }
    onRowsChanged: current = Math.min(current, Math.max(0, rows.length - 1))
    onTabsChanged: if (!tabs.some(t => t.key === tab)) tab = 'flatpak'
    Timer { id: toastTimer; interval: 4000; onTriggered: page.toast = '' }
    Connections {
        target: AppsService
        function onJobFinished(job) {
            if (job.kind !== 'remove') return;
            const r = Object.assign({}, page.removing);
            job.ids.forEach(id => { Object.keys(r).forEach(k => { if (k.indexOf(':' + id) > 0) delete r[k]; }); });
            page.removing = r;
            if (job.phase === 'done') page.showToast(job.name + ' was removed.');
            page.refresh(job.source);
        }
    }
    Keys.onPressed: event => {
        if ((event.modifiers & Qt.ControlModifier) && (event.key === Qt.Key_Tab || event.key === Qt.Key_PageDown || event.key === Qt.Key_PageUp || event.key === Qt.Key_Backtab)) {
            tabBar.step(event.key === Qt.Key_PageUp || event.key === Qt.Key_Backtab ? -1 : 1);
            event.accepted = true;
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.space3

        PageHeader { title: 'Remove apps'; onBack: page.backRequested() }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space3
            Segmented {
                id: tabBar
                model: page.tabs
                current: page.tab
                onActivated: key => { page.tab = key; page.current = 0; }
            }
            Item { Layout.fillWidth: true }
            Segmented {
                visible: page.tab === 'dnf'
                model: [{ key: 'apps', label: 'Apps' }, { key: 'other', label: 'Other packages you added' }]
                current: page.dnfView
                onActivated: key => { page.dnfView = key; page.current = 0; }
            }
        }
        ArcticField {
            id: field
            Layout.fillWidth: true
            focus: true
            iconName: 'search'
            placeholderText: 'Filter your apps'
            Keys.onDownPressed: page.move(1)
            Keys.onUpPressed: page.move(-1)
            Keys.onTabPressed: event => { if (event.modifiers & Qt.ControlModifier) event.accepted = false; else page.move(1); }
            Keys.onBacktabPressed: page.move(-1)
            Keys.onReturnPressed: page.ask(page.rows[page.current])
            Keys.onEnterPressed: page.ask(page.rows[page.current])
            Keys.onDeletePressed: event => {
                if (field.text === '' || (event.modifiers & Qt.ShiftModifier) || field.cursorPosition === field.text.length) {
                    page.ask(page.rows[page.current]);
                    event.accepted = true;
                } else {
                    event.accepted = false;
                }
            }
        }
        Text {
            Layout.fillWidth: true
            Layout.topMargin: Theme.space4
            visible: page.rows.length === 0
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            color: Theme.inkMuted
            font.family: Theme.fontSans
            font.pixelSize: 14
            text: field.text ? 'None of your apps match “' + field.text + '”.'
                  : page.tab === 'web' && !page.showWeb ? ''
                  : page.tab !== 'web' && !page.loaded[page.tab] ? 'Looking at what’s installed…'
                  : page.tab === 'flatpak' ? 'You have no Flatpak apps.'
                  : page.tab === 'dnf' && page.dnfView === 'other' ? 'You haven’t added other packages.'
                  : page.tab === 'web' ? 'You have no web apps.' : 'Nothing to remove here.'
        }
        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 2
            model: page.rows
            currentIndex: page.current
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: list.contentHeight > list.height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff }
            delegate: AppRow {
                id: row
                required property var modelData
                required property int index
                width: list.width
                name: modelData.name || modelData.id || modelData.package
                summary: GetAppsLogic.removeLine(Object.assign({ runtime_name: AppsService.web.runtimeName(modelData.runtime) }, modelData), page.tab)
                iconName: page.tab === 'web' ? '' : modelData.icon || ''
                imageSource: page.tab === 'web' ? modelData.icon_path || '' : ''
                glyph: page.tab === 'web' ? 'globe' : page.tab === 'terminal' ? 'prompt' : 'package'
                state_: page.removing[page.keyOf(modelData)] ? 'busy' : 'removable'
                actionText: 'Remove…'
                selected: index === page.current
                onHovered: page.current = index
                onClicked: page.current = index
                onActivated: page.ask(modelData)
            }
            footer: ColumnLayout {
                width: list.width
                spacing: 2
                // Fedora: what Arctic Linux needs, collapsed.
                ArcticButton {
                    visible: page.tab === 'dnf' && page.dnfView === 'apps' && page.dnfProtected.length > 0
                    Layout.topMargin: Theme.space3
                    variant: 'ghost'; size: 'sm'
                    iconName: page.protectedOpen ? 'chevron-down' : 'chevron-right'
                    text: 'Part of Arctic Linux (' + page.dnfProtected.length + ')'
                    onClicked: page.protectedOpen = !page.protectedOpen
                }
                Repeater {
                    model: page.tab === 'dnf' && page.dnfView === 'apps' && page.protectedOpen ? page.dnfProtected : []
                    delegate: AppRow {
                        required property var modelData
                        Layout.fillWidth: true
                        name: modelData.name
                        iconName: modelData.icon || ''
                        reason: modelData.message
                        state_: 'locked'
                    }
                }
                // Web apps: sign-in data kept after removing an app.
                Text {
                    visible: page.tab === 'web' && page.kept.length > 0
                    Layout.topMargin: Theme.space4
                    text: 'Saved sign-in data'
                    color: Theme.ink
                    font.family: Theme.fontSans
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }
                Repeater {
                    model: page.tab === 'web' ? page.kept : []
                    delegate: RowLayout {
                        id: keptRow
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.leftMargin: Theme.space3
                        Layout.rightMargin: Theme.space3
                        implicitHeight: 44
                        spacing: Theme.space3
                        Icon { name: 'lock'; size: 16; color: Theme.inkMuted }
                        Text {
                            Layout.fillWidth: true
                            text: keptRow.modelData.name + (keptRow.modelData.data_bytes ? ' · ' + GetAppsLogic.sizeText(keptRow.modelData.data_bytes) : '')
                            color: Theme.ink
                            font.family: Theme.fontSans
                            font.pixelSize: 13
                            elide: Text.ElideRight
                        }
                        ArcticButton {
                            variant: 'secondary'; size: 'sm'
                            text: confirming ? 'Delete ' + keptRow.modelData.name + '’s data' : 'Delete data'
                            property bool confirming: false
                            onClicked: {
                                if (!confirming) { confirming = true; return; }
                                AppsService.web.forget([keptRow.modelData.id], (result, err) => {
                                    if (err) page.showToast(err.message); else page.showToast(keptRow.modelData.name + '’s data was deleted.');
                                });
                            }
                        }
                    }
                }
            }
        }
        Text {
            Layout.fillWidth: true
            visible: page.toast !== ''
            text: page.toast
            color: Theme.ink
            font.family: Theme.fontSans
            font.pixelSize: 13
        }
        JobCard { Layout.fillWidth: true }
    }

    RemoveSheet {
        id: sheet
        bleed: Theme.space3
        onClosed: field.forceActiveFocus()
        onRemoved: (name, source) => {
            if (source === 'flatpak' || source === 'dnf') {
                const r = Object.assign({}, page.removing);
                r[page.asking] = true;
                page.removing = r;
            } else {
                page.showToast(name + ' was removed.');
                page.refresh(source === 'terminal-app' ? 'terminal' : 'web');
            }
        }
    }
}
