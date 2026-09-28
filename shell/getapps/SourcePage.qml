pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Quickshell
import ".."
import "../PackageSearch.js" as PackageSearch
import "GetApps.js" as GetAppsLogic

// Get apps → Flathub apps (source 'flatpak') or Fedora packages (source 'dnf'): search,
// details and install. Flathub lists the local AppStream catalogue (names, summaries, icons,
// the Verified badge), else the index's names; Fedora has Apps (appstream-data) and All
// packages (every available package, with its summary and repository). Installs are
// AppsService jobs: Flathub needs no password, Fedora asks once through the polkit dialog.
// Before you type, the page offers Arctic picks: the installer catalogue's apps that this source
// has (assets/featured.json, made by `arctic-install catalog --featured`).
// Keys: type to search, ↑/↓ or Tab move, Enter installs (or opens), Shift+Enter details,
// Ctrl+Tab / Ctrl+Page Up/Down switch between Apps and All packages.
FocusScope {
    id: page
    property string source: 'flatpak'
    property string initialQuery: ''
    property string view: 'apps'                   // dnf: apps | all
    property int current: 0
    readonly property bool flathub: source === 'flatpak'
    readonly property bool catalogApps: flathub ? AppsService.flathubCatalog.length > 0 : view === 'apps'
    readonly property bool fedoraCatalog: AppsService.fedoraApps.length > 0 || !AppsService.fedoraCatalogMissing
    readonly property var items: flathub ? AppsService.flathubItems : view === 'apps' ? AppsService.fedoraApps : AppsService.fedoraPackages
    readonly property var prepared: PackageSearch.prepareItems(items)
    property var results: []
    readonly property var flatpakSource: AppsService.sources.flatpak || null
    readonly property bool noFlatpak: flathub && AppsService.sourcesLoaded && !!flatpakSource && !flatpakSource.present
    readonly property bool noFlathub: flathub && AppsService.sourcesLoaded && !!flatpakSource && flatpakSource.present
                                      && !flatpakSource.flathub.system && !flatpakSource.flathub.user
    readonly property Item inputItem: field
    signal backRequested()
    signal openPage(string name, string text)
    signal closeRequested()

    function back() {
        if (details.open) { details.close(); return true; }
        if (field.text) { field.text = ''; return true; }
        return false;
    }
    function reopen(text) { field.text = text || ''; field.forceActiveFocus(); }
    // The picks this source can install, as result items (with the catalogue's icon when it has one).
    readonly property var picks: {
        const list = [];
        const byId = {};
        items.forEach(i => byId[flathub ? i.id : (i.pkg || i.id)] = i);
        AppsService.featured.forEach(app => {
            const method = flathub ? app.flatpak : app.dnf;
            if (!method || (!flathub && view === 'all')) return;
            const key = flathub ? method.ref : method.packages[0];
            // Only what this computer's lists have (once they are loaded).
            if (flathub && items.length && !byId[key]) return;
            if (!flathub && AppsService.dnfNamesCount && !AppsService.dnfNames[key] && !AppsService.installedIds.dnf[key]) return;
            const known = byId[key] || {};
            list.push(Object.assign({}, known, { id: flathub ? key : (known.id || key), pkg: flathub ? undefined : key,
                                                 pkgs: flathub ? undefined : method.packages, name: known.name || app.name,
                                                 summary: known.summary || app.summary, tile: app.tile,
                                                 verified: flathub ? (known.verified || method.verified) : false, pick: true }));
        });
        return list;
    }
    function search() {
        results = field.text.trim() === '' && picks.length ? picks : PackageSearch.searchItems(prepared, field.text, 200);
        current = 0;
        list.positionViewAtBeginning();
    }
    function stateOf(item) { return GetAppsLogic.rowState(item, source, AppsService.installedIds, AppsService.jobs); }
    function jobOf(item) {
        const id = flathub ? item.id : (item.pkg || item.id);
        const jobs = AppsService.jobs;
        for (let i = jobs.length - 1; i >= 0; i--) if (jobs[i].kind === 'install' && jobs[i].source === source && jobs[i].ids.indexOf(id) >= 0) return jobs[i];
        return null;
    }
    function desktopOf(item) { return flathub ? item.id : item.pkg ? item.id : ''; }
    function install(item) {
        if (!item) return;
        const state = stateOf(item);
        if (state === 'installed') { launch(item); return; }
        if (state === 'waiting' || state === 'running') return;
        AppsService.install(source, flathub ? [item.id] : item.pkgs || [item.pkg || item.id],
                            { name: item.name || item.id, icon: item.icon || '', desktop: desktopOf(item) });
    }
    function launch(item) {
        const entry = DesktopEntries.byId(desktopOf(item) || item.id);
        if (entry) { entry.execute(); closeRequested(); }
    }
    function move(delta) {
        if (!results.length) return;
        current = (current + delta + results.length) % results.length;
        list.positionViewAtIndex(current, ListView.Contain);
    }
    function showDetails(item) { if (item) details.show(item); }
    function accept(shift) {
        if (debounce.running) { debounce.stop(); search(); }
        const item = results[current];
        if (shift) showDetails(item); else install(item);
    }

    onPreparedChanged: search()
    onPicksChanged: if (field.text.trim() === '') search()
    onSourceChanged: { view = 'apps'; field.text = initialQuery; search(); }
    Component.onCompleted: {
        if (source === 'dnf' && AppsService.fedoraCatalogMissing && !AppsService.fedoraApps.length) view = 'all';
        field.text = initialQuery;
        search();
    }
    Connections {
        target: AppsService
        function onFedoraCatalogMissingChanged() { if (page.source === 'dnf' && AppsService.fedoraCatalogMissing && !AppsService.fedoraApps.length) page.view = 'all'; }
    }
    Timer { id: debounce; interval: 120; onTriggered: page.search() }
    Keys.onPressed: event => {
        if ((event.modifiers & Qt.ControlModifier) && page.source === 'dnf'
            && (event.key === Qt.Key_Tab || event.key === Qt.Key_PageDown || event.key === Qt.Key_PageUp || event.key === Qt.Key_Backtab)) {
            segments.step(event.key === Qt.Key_PageUp || event.key === Qt.Key_Backtab ? -1 : 1);
            event.accepted = true;
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.space3

        PageHeader {
            title: page.flathub ? 'Flathub apps' : 'Fedora packages'
            detail: page.items.length ? page.items.length.toLocaleString(Qt.locale('en_US'), 'f', 0) + (page.flathub || page.view === 'apps' ? ' apps' : ' packages') : ''
            onBack: page.backRequested()
            Segmented {
                id: segments
                visible: !page.flathub && page.fedoraCatalog
                model: [{ key: 'apps', label: 'Apps' }, { key: 'all', label: 'All packages' }]
                current: page.view
                onActivated: key => { page.view = key; page.current = 0; }
            }
            ArcticButton {
                variant: 'ghost'; size: 'sm'; iconName: 'refresh'; iconOnly: true; label: 'Refresh the list'
                focusPolicy: Qt.NoFocus
                enabled: !AppsService.indexRefreshing
                onClicked: AppsService.refreshIndex(true)
            }
        }
        ArcticField {
            id: field
            Layout.fillWidth: true
            focus: true
            iconName: 'search'
            placeholderText: page.flathub ? 'Search Flathub' : page.view === 'apps' ? 'Search Fedora’s apps' : 'Search all packages'
            onTextChanged: debounce.restart()
            Keys.onDownPressed: page.move(1)
            Keys.onUpPressed: page.move(-1)
            Keys.onTabPressed: event => { if (event.modifiers & Qt.ControlModifier) event.accepted = false; else page.move(1); }
            Keys.onBacktabPressed: page.move(-1)
            Keys.onReturnPressed: event => page.accept(event.modifiers & Qt.ShiftModifier)
            Keys.onEnterPressed: event => page.accept(event.modifiers & Qt.ShiftModifier)
        }

        // What there is to say instead of results.
        ColumnLayout {
            Layout.fillWidth: true
            Layout.topMargin: Theme.space5
            Layout.bottomMargin: Theme.space5
            visible: text.text !== ''
            spacing: Theme.space3
            Text {
                id: text
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                color: Theme.inkMuted
                font.family: Theme.fontSans
                font.pixelSize: 14
                text: page.noFlatpak ? 'Flatpak isn’t installed.'
                      : page.noFlathub ? 'Flathub isn’t set up on this computer. Adding it asks for your password once.'
                      : !page.items.length && (!AppsService.indexLoaded || AppsService.indexRefreshing)
                        ? (page.flathub ? 'Getting the list of Flathub apps… this takes a minute the first time.' : 'Getting the list of Fedora packages… this takes a minute the first time.')
                      : !page.items.length && AppsService.indexError ? AppsService.indexError
                      : page.items.length && !page.results.length && field.text.trim()
                        ? (page.flathub ? 'No Flathub apps match “' + field.text.trim() + '”.' : 'No Fedora packages match “' + field.text.trim() + '”.')
                      : ''
            }
            RowLayout {
                Layout.alignment: Qt.AlignHCenter
                spacing: Theme.space2
                ArcticButton {
                    visible: page.noFlathub
                    variant: 'primary'
                    text: 'Add Flathub'
                    onClicked: AppsService.addFlathub()
                }
                ArcticButton {
                    visible: !page.noFlathub && !page.noFlatpak && page.items.length > 0 && page.results.length === 0 && field.text.trim() !== ''
                    variant: 'secondary'
                    text: page.flathub ? 'Search Fedora packages' : 'Search Flathub'
                    onClicked: page.openPage(page.flathub ? 'dnf' : 'flatpak', field.text.trim())
                }
            }
        }
        Text {
            Layout.fillWidth: true
            visible: !page.flathub && page.view === 'all' && !page.fedoraCatalog
            text: 'Install Fedora’s app catalogue (appstream-data) for app names and icons.'
            color: Theme.inkSubtle
            font.family: Theme.fontSans
            font.pixelSize: 12
        }

        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !page.noFlathub && !page.noFlatpak && count > 0
            clip: true
            spacing: 2
            model: page.results
            currentIndex: page.current
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: list.contentHeight > list.height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff }
            header: Item {
                width: list.width
                height: hint.visible ? hint.implicitHeight + Theme.space2 : 0
                Text {
                    id: hint
                    visible: field.text.trim() === ''
                    text: (page.picks.length && page.view !== 'all' ? 'Arctic picks · ' : '')
                          + (page.flathub ? 'Type to search all of Flathub.' : page.view === 'apps' ? 'Type to search Fedora’s apps.' : 'Type to search every package.')
                    color: Theme.inkSubtle
                    font.family: Theme.fontSans
                    font.pixelSize: 12
                }
            }
            delegate: AppRow {
                id: row
                required property var modelData
                required property int index
                readonly property var job: page.jobOf(modelData)
                width: list.width
                name: modelData.name || modelData.id
                summary: page.source === 'dnf' && page.view === 'all'
                         ? [modelData.summary, GetAppsLogic.repoLabel(modelData.repo)].filter(s => s).join(' · ') : (modelData.summary || '')
                imageSource: modelData.icon && modelData.icon.startsWith('/') ? modelData.icon : ''
                iconName: modelData.icon && !modelData.icon.startsWith('/') ? modelData.icon : ''
                glyph: page.source === 'dnf' && page.view === 'all' ? 'layers' : 'package'
                tileId: modelData.pick && !imageSource ? modelData.tile || '' : ''
                verified: !!modelData.verified
                state_: page.stateOf(modelData)
                percent: job ? job.percent : null
                selected: index === page.current
                onHovered: page.current = index
                onClicked: { page.current = index; page.showDetails(modelData); }
                onActivated: page.install(modelData)
            }
        }
        Item { Layout.fillHeight: true; visible: !list.visible }
        JobCard { Layout.fillWidth: true }
    }

    DetailsSheet {
        id: details
        bleed: Theme.space3
        source: page.source
        onInstallRequested: item => page.install(item)
        onClosed: field.forceActiveFocus()
    }
}
