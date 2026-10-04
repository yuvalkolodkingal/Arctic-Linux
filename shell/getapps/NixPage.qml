pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."
import "GetApps.js" as GetAppsLogic

// Search is explicit: evaluating nixpkgs is too expensive for a keystroke timer.
// All mutations use AppsService's existing serialized jobs and unprivileged PTY.
FocusScope {
    id: page
    property string initialQuery: ''
    property var results: []
    property var installed: []
    property bool searching: false
    property bool loading: true
    property string error: ''
    property string note: ''
    property string view: 'search'
    property var pending: null
    property int requestId: 0
    readonly property Item inputItem: field
    readonly property bool live: Session.live
    readonly property var installedAttrs: {
        const attrs = {};
        installed.forEach(r => attrs[r.attr] = true);
        return attrs;
    }
    signal backRequested()
    function back() {
        if (confirm.open) { confirm.close(); return true; }
        if (field.text) { field.text = ''; return true; }
        return false;
    }
    function refresh() {
        loading = true;
        AppsService.helper(['installed', 'nix'], r => {
            page.loading = false;
            if (r.ok) page.installed = r.apps;
            else page.error = r.error || 'Could not read your Nix profile.';
        });
    }
    function search() {
        if (searching || field.text.trim().length < 2) return;
        searching = true; error = ''; note = ''; view = 'search';
        const request = ++requestId;
        AppsService.helper(['nix-search', field.text.trim()], r => {
            if (request !== page.requestId) return;
            page.searching = false;
            if (r.ok) {
                page.results = r.items;
                page.note = r.total > r.items.length ? 'Showing the first 200 results. Narrow your search.' : r.total + ' results from Nixpkgs.';
            } else { page.results = []; page.error = r.error || 'Nix search failed.'; }
        });
    }
    function ask(kind, item) {
        pending = { kind: kind, item: item };
        confirm.show();
    }
    function reopen(text, tab) { field.text = text || ''; view = 'search'; field.forceActiveFocus(); }
    Component.onCompleted: { field.text = initialQuery; refresh(); }
    Connections {
        target: AppsService
        function onJobFinished(job) {
            if (job.source === 'nix') {
                if (job.phase === 'failed') page.error = job.message;
                else { page.error = ''; page.note = GetAppsLogic.jobLabel(job); }
                page.refresh();
            }
        }
    }
    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.space3
        PageHeader { title: 'Nix packages'; detail: 'Nixpkgs · Only you'; onBack: page.backRequested() }
        Text {
            Layout.fillWidth: true
            text: page.live ? 'Install Arctic to disk before changing Nix packages.'
                : 'Separate from Fedora and Flatpak. Nix apps are not sandboxed like Flatpak apps. Some graphical apps need host-specific integration.'
            wrapMode: Text.Wrap; color: Theme.inkMuted; font.family: Theme.fontSans; font.pixelSize: 13
        }
        RowLayout {
            Layout.fillWidth: true
            Segmented {
                current: page.view
                model: [{ key: 'search', label: 'Search' }, { key: 'installed', label: 'Installed (' + page.installed.length + ')' }]
                onActivated: key => page.view = key
            }
            Item { Layout.fillWidth: true }
            ArcticButton {
                text: 'Update'; enabled: !page.live && !AppsService.busy && page.installed.length > 0
                onClicked: page.ask('update', null)
            }
            ArcticButton {
                text: 'Roll back…'; enabled: !page.live && !AppsService.busy
                onClicked: page.ask('rollback', null)
            }
        }
        RowLayout {
            visible: page.view === 'search'; Layout.fillWidth: true
            ArcticField {
                id: field; Layout.fillWidth: true; focus: true; iconName: 'search'
                placeholderText: 'Search Nixpkgs (at least 2 characters)'
                Keys.onReturnPressed: page.search()
                Keys.onEnterPressed: page.search()
            }
            ArcticButton { text: page.searching ? 'Searching…' : 'Search'; enabled: !page.searching && field.text.trim().length >= 2; onClicked: page.search() }
        }
        Text {
            visible: text !== ''; Layout.fillWidth: true
            text: page.error || (page.loading ? 'Reading your profile…' : page.searching ? 'Fetching and evaluating Nixpkgs. The first search can take a few minutes…' : page.note)
            textFormat: Text.PlainText; wrapMode: Text.Wrap
            color: page.error ? Theme.error : Theme.inkMuted; font.family: Theme.fontSans; font.pixelSize: 13
            maximumLineCount: 4; elide: Text.ElideRight
        }
        ListView {
            id: list; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 2
            model: page.view === 'installed' ? page.installed : page.results
            ScrollBar.vertical: ScrollBar {}
            delegate: AppRow {
                required property var modelData
                required property int index
                width: list.width
                name: page.view === 'installed' ? modelData.name : modelData.id
                summary: page.view === 'installed' ? modelData.summary : 'Nix · ' + modelData.version + ' · ' + modelData.summary
                state_: AppsService.busy ? 'busy' : page.view === 'installed' ? 'removable'
                        : page.installedAttrs[modelData.id] ? 'installed' : 'install'
                canOpen: false
                actionText: page.view === 'installed' ? 'Remove…' : 'Install…'
                enabled: !page.live
                onActivated: page.ask(page.view === 'installed' ? 'remove' : 'install', modelData)
            }
        }
        JobCard { Layout.fillWidth: true }
    }
    Sheet {
        id: confirm
        initialFocus: cancel
        ColumnLayout {
            width: parent.width; spacing: Theme.space3
            Text {
                Layout.fillWidth: true; textFormat: Text.PlainText; wrapMode: Text.Wrap
                text: !page.pending ? '' : page.pending.kind === 'install' ? 'Install ' + page.pending.item.id + ' from Nixpkgs? Downloads and builds can use substantial disk space.'
                    : page.pending.kind === 'remove' ? 'Remove ' + page.pending.item.name + ' from your Nix profile? App data and older generations are kept; disk space may not be freed yet.'
                    : page.pending.kind === 'update' ? 'Update your Nix packages? Pinned inputs stay pinned. Restart open apps afterward. Nix itself updates with Arctic’s system updates.'
                    : 'Switch your Nix profile to its previous generation? This does not roll back application data or the operating system.'
                font.family: Theme.fontSans; font.pixelSize: 14; color: Theme.ink
            }
            RowLayout {
                Item { Layout.fillWidth: true }
                ArcticButton { id: cancel; text: 'Cancel'; onClicked: confirm.close() }
                ArcticButton {
                    text: 'Continue'; enabled: !page.live && !AppsService.busy
                    onClicked: {
                        const p = page.pending;
                        if (!p) return;
                        AppsService.queue(p.kind, 'nix', p.item ? [p.item.id] : [], { name: p.item ? p.item.id : 'Nix packages' });
                        confirm.close();
                    }
                }
            }
        }
    }
}
