pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."
import "GetApps.js" as GetAppsLogic

// "Remove GIMP?" — the confirmation for Remove apps and for Delete on a launcher row. It says
// exactly what goes before anything happens: for a Fedora package every package dnf would
// remove (asked, the ones that need it, the ones nothing needs any more; a preview dnf works out
// as you, without a password), for a Flatpak app whether its data goes too (off by default),
// for a web app whether its sign-in goes (off by default). What can't be removed says why and
// offers only Close. Cancel has the first focus; the red button is one Tab away.
// request: {source: flatpak|dnf|webapp|terminal-app|launcher|nix|unknown, name, icon,
//           target: {id, installation} | {package} | {path, overrides} | {name}, blocked, running}
Sheet {
    id: sheet
    property var request: null
    property var preview: null
    property bool loading: false
    property string error: ''
    property bool deleteData: false
    property bool autoremove: true
    property bool changed: false                   // the dnf preview changed when it was checked again
    property var webInfo: null
    readonly property string source: request ? request.source : ''
    readonly property string name: request ? request.name || '' : ''
    readonly property var blocked: request && request.blocked ? request.blocked : preview && preview.blocked ? preview.blocked : null
    readonly property bool closeOnly: blocked !== null || source === 'nix' || source === 'unknown' || error !== ''
    readonly property var asked: preview && preview.packages ? preview.packages.filter(p => p.why === 'asked') : []
    readonly property var needing: preview && preview.packages ? preview.packages.filter(p => p.why === 'needs-it') : []
    readonly property var unused: preview && preview.packages ? preview.packages.filter(p => p.why === 'unused') : []
    signal removed(string name, string source)

    initialFocus: cancelButton

    function openFor(req) {
        request = req;
        preview = null;
        webInfo = null;
        error = '';
        deleteData = false;
        autoremove = true;
        changed = false;
        show();
        load();
    }
    function load() {
        if (!request || request.blocked) return;
        const t = request.target || {};
        if (source === 'webapp' && AppsService.sourcesLoaded && !AppsService.webappPresent) {
            error = 'The web-app engine (arctic-webapps) isn’t installed, so ' + name + ' can’t be removed here.';
            return;
        }
        if (source === 'dnf') {
            loading = true;
            AppsService.helper(['preview-remove', 'dnf'].concat(autoremove ? [] : ['--no-autoremove'], [t.package]), r => {
                if (!sheet.open || sheet.request === null || (sheet.request.target || {}).package !== t.package) return;
                sheet.loading = false;
                if (r.ok) sheet.preview = r; else sheet.error = r.error;
            });
        } else if (source === 'flatpak') {
            loading = true;
            AppsService.helper(['preview-remove', 'flatpak', t.id, '--installation', t.installation || 'system'], r => {
                sheet.loading = false;
                if (r.ok) sheet.preview = r;
            });
        } else if (source === 'webapp') {
            AppsService.web.get(t.id, true, (result, err) => { if (result) sheet.webInfo = result.app; });
        }
    }
    function names(list) { return list.map(p => p.name).join(' '); }
    function confirm() {
        if (closeOnly || loading || !request) return;
        const t = request.target || {};
        const extra = { name: name, icon: request.icon || '' };
        if (source === 'dnf') {
            // Check again right before: the packages may have changed since the preview.
            const before = names(preview ? preview.packages : []);
            loading = true;
            AppsService.helper(['preview-remove', 'dnf'].concat(autoremove ? [] : ['--no-autoremove'], [t.package]), r => {
                sheet.loading = false;
                if (!r.ok) { sheet.error = r.error; return; }
                if (sheet.names(r.packages) !== before || r.blocked) { sheet.preview = r; sheet.changed = true; return; }
                AppsService.remove('dnf', [t.package], Object.assign(extra, { autoremove: sheet.autoremove }));
                sheet.done();
            });
            return;
        }
        if (source === 'flatpak') {
            AppsService.remove('flatpak', [t.id], Object.assign(extra, { installation: t.installation || 'system', delete_data: deleteData, unused: true }));
            done();
        } else if (source === 'webapp') {
            loading = true;
            AppsService.web.remove([t.id], !deleteData, (result, err) => {
                sheet.loading = false;
                if (err) { sheet.error = err.message; return; }
                sheet.done();
            });
        } else if (source === 'terminal-app') {
            AppsService.helper(['terminal-app', 'remove', t.id], r => { if (r.ok) sheet.done(); else sheet.error = r.error; });
        } else if (source === 'launcher') {
            AppsService.helper(['launcher-entry', 'remove', request.desktop_id], r => { if (r.ok) sheet.done(); else sheet.error = r.error; });
        }
    }
    function done() {
        const n = name, s = source;
        close();
        removed(n, s);
    }
    onAutoremoveChanged: if (open && source === 'dnf' && preview) load()

    ColumnLayout {
        width: parent.width
        spacing: Theme.space3

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space3
            AppTile {
                size: 40
                imageSource: sheet.request && sheet.request.icon && sheet.request.icon.startsWith('/') ? sheet.request.icon : ''
                iconName: sheet.request && sheet.request.icon && !sheet.request.icon.startsWith('/') ? sheet.request.icon : ''
                fallbackGlyph: 'package'
            }
            Text {
                Layout.fillWidth: true
                text: sheet.blocked ? sheet.name + ' can’t be removed' : 'Remove ' + sheet.name + '?'
                textFormat: Text.PlainText
                color: Theme.ink
                font.family: Theme.fontSans
                font.pixelSize: 18
                font.weight: Font.DemiBold
                wrapMode: Text.Wrap
            }
            Icon { visible: sheet.blocked !== null; name: 'lock'; size: 18; color: Theme.inkMuted }
        }

        component Line: Text {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            color: Theme.inkMuted
            font.family: Theme.fontSans
            font.pixelSize: 13
            wrapMode: Text.Wrap
            visible: text !== ''
        }
        component Heading: Text {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            color: Theme.ink
            font.family: Theme.fontSans
            font.pixelSize: 13
            font.weight: Font.DemiBold
            visible: text !== ''
        }

        Line { text: sheet.blocked ? sheet.blocked.message : '' ; color: Theme.ink }
        Line { text: sheet.error }
        RowLayout {
            visible: sheet.loading
            spacing: Theme.space2
            Icon { name: 'clock'; size: 14; color: Theme.inkMuted }
            Line { text: sheet.source === 'dnf' ? 'Checking what else goes…' : 'Checking…' }
        }

        // ---- Fedora packages: every package dnf would remove ----
        ColumnLayout {
            Layout.fillWidth: true
            visible: sheet.source === 'dnf' && sheet.preview !== null && !sheet.blocked && !sheet.error
            spacing: Theme.space2
            Line { text: sheet.changed ? 'What would be removed changed since you opened this. Check the list again.' : ''; color: Theme.warning }
            Heading { text: 'These packages will be removed:' }
            ScrollView {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(packageList.implicitHeight, 180)
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    id: packageList
                    width: parent.width
                    spacing: 2
                    Repeater {
                        model: [{ title: '', rows: sheet.asked }, { title: 'Also removed, because they need it:', rows: sheet.needing },
                                { title: 'No longer needed:', rows: sheet.unused }]
                        delegate: ColumnLayout {
                            id: group
                            required property var modelData
                            Layout.fillWidth: true
                            visible: modelData.rows.length > 0
                            spacing: 2
                            Heading { text: group.modelData.title; Layout.topMargin: text ? Theme.space1 : 0 }
                            Repeater {
                                model: group.modelData.rows
                                delegate: RowLayout {
                                    id: pkg
                                    required property var modelData
                                    Layout.fillWidth: true
                                    spacing: Theme.space2
                                    Text { Layout.fillWidth: true; text: pkg.modelData.name; textFormat: Text.PlainText; color: Theme.ink; font.family: Theme.fontMono; font.pixelSize: 12; elide: Text.ElideRight }
                                    Text { text: GetAppsLogic.sizeText(pkg.modelData.install_bytes); color: Theme.inkSubtle; font.family: Theme.fontSans; font.pixelSize: 12 }
                                }
                            }
                        }
                    }
                }
            }
            Check {
                Layout.fillWidth: true
                text: 'Also remove packages nothing else needs'
                checked: sheet.autoremove
                onToggled: sheet.autoremove = checked
            }
            Line {
                text: (sheet.preview && sheet.preview.frees_bytes ? 'Frees ' + GetAppsLogic.sizeText(sheet.preview.frees_bytes) + '. ' : '')
                      + (sheet.preview && sheet.preview.undo ? 'A snapshot is taken first, so this can be undone.' : '')
            }
        }

        // ---- Flathub apps ----
        ColumnLayout {
            Layout.fillWidth: true
            visible: sheet.source === 'flatpak' && !sheet.blocked
            spacing: Theme.space2
            Line {
                text: sheet.name + (sheet.request && sheet.request.target && sheet.request.target.installation === 'user'
                                    ? ' will be removed for you.' : ' will be removed for everyone on this computer.')
            }
            Check {
                Layout.fillWidth: true
                text: 'Also delete its settings and data' + (sheet.preview && sheet.preview.data_bytes
                      ? ' (' + GetAppsLogic.sizeText(sheet.preview.data_bytes) + ' in ~/.var/app/' + sheet.preview.id + ')' : '')
                checked: sheet.deleteData
                onToggled: sheet.deleteData = checked
            }
            Line { text: 'Runtimes no other app uses are removed too.' }
        }

        // ---- web apps ----
        ColumnLayout {
            Layout.fillWidth: true
            visible: sheet.source === 'webapp' && !sheet.blocked
            spacing: Theme.space2
            Line {
                text: sheet.name + ' will be removed from the launcher.'
                      + ((sheet.webInfo && sheet.webInfo.running) || (sheet.request && sheet.request.running) ? ' It’s open and will be closed.' : '')
            }
            Check {
                Layout.fillWidth: true
                text: 'Also sign out and delete its data' + (sheet.webInfo && sheet.webInfo.data_bytes ? ' (' + GetAppsLogic.sizeText(sheet.webInfo.data_bytes) + ')' : '')
                checked: sheet.deleteData
                onToggled: sheet.deleteData = checked
            }
        }
        Line {
            text: sheet.source === 'terminal-app' ? 'The launcher entry for ' + sheet.name + ' will be removed. The program itself stays installed.'
                  : sheet.source === 'launcher' ? 'This is your own launcher entry for ' + sheet.name + '.'
                                                   + (sheet.request && sheet.request.target && sheet.request.target.overrides ? ' Removing it brings back the original.' : '')
                  : sheet.source === 'nix' ? sheet.name + ' was installed with Nix. Remove it in a terminal: sudo nix profile remove --profile /nix/var/nix/profiles/default ' + sheet.name
                  : sheet.source === 'unknown' && !sheet.blocked ? 'Arctic Linux can’t tell where ' + sheet.name + ' came from.' : ''
        }

        // Warnings (a default app, …).
        Repeater {
            model: sheet.preview && sheet.preview.warnings && !sheet.blocked ? sheet.preview.warnings : []
            delegate: RowLayout {
                id: warning
                required property var modelData
                Layout.fillWidth: true
                spacing: Theme.space2
                Icon { Layout.alignment: Qt.AlignTop; name: 'alert'; size: 16; color: Theme.warning }
                Text { Layout.fillWidth: true; text: warning.modelData.message; textFormat: Text.PlainText; color: Theme.warning; font.family: Theme.fontSans; font.pixelSize: 13; wrapMode: Text.Wrap }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: Theme.space2
            spacing: Theme.space2
            Item { Layout.fillWidth: true }
            ArcticButton {
                id: cancelButton
                variant: 'secondary'
                text: sheet.closeOnly ? 'Close' : 'Cancel'
                onClicked: sheet.close()
            }
            ArcticButton {
                visible: !sheet.closeOnly
                variant: 'destructive'
                enabled: !sheet.loading && (sheet.source !== 'dnf' || sheet.preview !== null)
                text: 'Remove ' + sheet.name
                onClicked: sheet.confirm()
            }
        }
    }
}
