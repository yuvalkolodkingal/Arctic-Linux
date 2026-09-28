import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Quickshell
import ".."
import "GetApps.js" as GetAppsLogic

// An app's details (Shift+Enter or a click on a result): a 360-wide panel on the right of the
// card with the icon, name, developer, Verified, summary and description from AppStream, then
// version, licence, sizes and repository from apps.py info (filled in when it answers; left out
// offline), where it installs, and Install.
Sheet {
    id: details
    property string source: 'flatpak'
    property var item: null
    property var info: null
    readonly property string state_: item ? GetAppsLogic.rowState(item, source, AppsService.installedIds, AppsService.jobs) : ''
    signal installRequested(var item)

    side: true
    panelWidth: 360
    initialFocus: installButton

    function show(entry) {
        item = entry;
        info = null;
        open = true;
        const id = source === 'flatpak' ? entry.id : (entry.pkg || entry.id);
        AppsService.helper(['info', source, id], r => { if (details.item === entry && r.ok) details.info = r; });
        Qt.callLater(() => installButton.forceActiveFocus());
    }

    ColumnLayout {
        width: parent.width
        height: parent.height
        spacing: Theme.space3
        RowLayout {
            spacing: Theme.space3
            AppTile {
                size: 64
                imageSource: details.item && details.item.icon && details.item.icon.startsWith('/') ? details.item.icon : ''
                iconName: details.item && details.item.icon && !details.item.icon.startsWith('/') ? details.item.icon : ''
                fallbackGlyph: details.source === 'dnf' && details.item && !details.item.pkg ? 'layers' : 'package'
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Text {
                    Layout.fillWidth: true
                    text: details.item ? details.item.name || details.item.id : ''
                    color: Theme.ink
                    font.family: Theme.fontSans
                    font.pixelSize: 18
                    font.weight: Font.DemiBold
                    wrapMode: Text.Wrap
                }
                Text {
                    Layout.fillWidth: true
                    visible: text !== ''
                    text: details.item && details.item.developer ? details.item.developer : ''
                    color: Theme.inkMuted
                    font.family: Theme.fontSans
                    font.pixelSize: 13
                }
                RowLayout {
                    visible: !!(details.item && details.item.verified)
                    spacing: Theme.space1
                    Icon { name: 'shield-check'; size: 14; color: Theme.info }
                    Text { text: 'Verified'; color: Theme.info; font.family: Theme.fontSans; font.pixelSize: 12; font.weight: Font.Medium }
                }
            }
        }
        ScrollView {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(facts.implicitHeight, details.panel.height - 260)
            clip: true
            contentWidth: availableWidth
            ColumnLayout {
                id: facts
                width: parent.width
                spacing: Theme.space2
                Text {
                    Layout.fillWidth: true
                    text: details.item ? details.item.summary || (details.info ? details.info.summary : '') : ''
                    color: Theme.ink
                    font.family: Theme.fontSans
                    font.pixelSize: 14
                    font.weight: Font.Medium
                    wrapMode: Text.Wrap
                }
                Repeater {
                    model: details.item && details.item.description ? details.item.description
                           : details.info && details.info.description ? [details.info.description] : []
                    delegate: Text {
                        required property string modelData
                        Layout.fillWidth: true
                        text: modelData
                        color: Theme.inkMuted
                        font.family: Theme.fontSans
                        font.pixelSize: 13
                        wrapMode: Text.Wrap
                        maximumLineCount: 8
                        elide: Text.ElideRight
                    }
                }
                Repeater {
                    model: {
                        const rows = [];
                        const i = details.info || {}, it = details.item || {};
                        const version = i.evr || i.version || '';
                        if (version) rows.push(['Version', version]);
                        if (i.repo) rows.push(['From', GetAppsLogic.repoLabel(i.repo) || i.repo]);
                        const license = it.license || i.license;
                        if (license) rows.push(['Licence', license]);
                        if (it.categories && it.categories.length) rows.push(['Categories', it.categories.join(', ')]);
                        const sizes = [GetAppsLogic.sizeText(i.download_bytes), GetAppsLogic.sizeText(i.install_bytes)];
                        if (sizes[0] || sizes[1]) rows.push(['Download · Installed', (sizes[0] || '?') + ' · ' + (sizes[1] || '?')]);
                        return rows;
                    }
                    delegate: RowLayout {
                        id: fact
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: Theme.space2
                        Text { Layout.preferredWidth: 120; text: fact.modelData[0]; color: Theme.inkSubtle; font.family: Theme.fontSans; font.pixelSize: 12 }
                        Text { Layout.fillWidth: true; text: fact.modelData[1]; color: Theme.ink; font.family: Theme.fontSans; font.pixelSize: 12; wrapMode: Text.Wrap }
                    }
                }
                ArcticButton {
                    readonly property string url: details.item && details.item.homepage ? details.item.homepage : details.info && details.info.url ? details.info.url : ''
                    visible: url !== ''
                    variant: 'ghost'; size: 'sm'; iconName: 'external'; text: 'Website'
                    onClicked: Quickshell.execDetached(['xdg-open', url])
                }
            }
        }
        Item { Layout.fillHeight: true }
        RowLayout {
            spacing: Theme.space2
            Icon { name: details.source === 'dnf' ? 'lock' : 'info'; size: 14; color: Theme.inkMuted }
            Text {
                Layout.fillWidth: true
                text: details.source === 'dnf' ? 'Installs for everyone on this computer. Asks for your password.'
                      : AppsService.sources.flatpak && AppsService.sources.flatpak.install_to === 'user'
                        ? 'Installs only for you. No password needed.' : 'Installs for everyone on this computer. No password needed.'
                color: Theme.inkMuted
                font.family: Theme.fontSans
                font.pixelSize: 12
                wrapMode: Text.Wrap
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space2
            Item { Layout.fillWidth: true }
            ArcticButton { variant: 'secondary'; text: 'Close'; onClicked: details.close() }
            ArcticButton {
                id: installButton
                variant: 'primary'
                enabled: details.state_ === 'install' || details.state_ === 'failed' || details.state_ === 'installed'
                text: details.state_ === 'installed' ? 'Open' : details.state_ === 'waiting' || details.state_ === 'running' ? 'Installing…'
                      : 'Install ' + (details.item ? details.item.name || details.item.id : '')
                onClicked: { details.installRequested(details.item); if (details.state_ === 'installed') details.close(); }
            }
        }
    }
}
