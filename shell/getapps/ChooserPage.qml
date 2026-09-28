pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import ".."
import "GetApps.js" as GetAppsLogic

// Get apps' home (Super + Shift + A): where should the app come from? Three large cards
// (Flathub apps, Fedora packages, Web apps) and three small ones (Terminal apps, Remove apps,
// Console). Cards that can't work here are hidden (no web-app engine; Remove apps on the live
// USB), and the digit keys follow the visible order. The chooser only links to pages.
FocusScope {
    id: page
    property int current: 0
    readonly property var cards: GetAppsLogic.cards({
        live: Session.live, webapp: AppsService.webappPresent,
        flatpak: AppsService.sourcesLoaded ? AppsService.sources.flatpak.present : undefined,
        flathub: AppsService.sourcesLoaded && AppsService.sources.flatpak.present
                 ? (AppsService.sources.flatpak.flathub.system || AppsService.sources.flatpak.flathub.user) : undefined })
    readonly property var big: cards.filter(c => c.big)
    readonly property var small: cards.filter(c => !c.big)
    readonly property Item inputItem: page
    signal openPage(string name)
    signal backRequested()

    function back() { return false; }
    function activate(index) { if (index >= 0 && index < cards.length) openPage(cards[index].page); }
    function move(dx, dy) {
        const row = current < big.length ? 0 : 1;
        const col = row === 0 ? current : current - big.length;
        if (dy !== 0) {
            const target = row + dy;
            if (target < 0 || target > 1) return;
            const list = target === 0 ? big : small;
            current = (target === 0 ? 0 : big.length) + Math.min(col, list.length - 1);
        } else {
            current = Math.max(0, Math.min(cards.length - 1, current + dx));
        }
    }
    onCardsChanged: current = Math.min(current, cards.length - 1)

    focus: true
    implicitHeight: column.implicitHeight
    Keys.onLeftPressed: move(-1, 0)
    Keys.onRightPressed: move(1, 0)
    Keys.onUpPressed: move(0, -1)
    Keys.onDownPressed: move(0, 1)
    Keys.onTabPressed: current = (current + 1) % cards.length
    Keys.onBacktabPressed: current = (current - 1 + cards.length) % cards.length
    Keys.onReturnPressed: activate(current)
    Keys.onEnterPressed: activate(current)
    Keys.onSpacePressed: activate(current)
    Keys.onPressed: event => {
        const digit = event.key - Qt.Key_1;
        if (digit >= 0 && digit < cards.length && !(event.modifiers & (Qt.ControlModifier | Qt.AltModifier))) {
            activate(digit);
            event.accepted = true;
        }
    }

    component Card: Rectangle {
        id: tile
        required property var modelData
        required property int index
        property int offset: 0
        readonly property int position: index + offset
        readonly property bool selected: page.current === position
        readonly property bool large: modelData.big
        radius: Theme.radiusLg
        color: selected ? Theme.accentSoft : mouse.containsMouse ? Theme.surfaceSunken : Theme.surfaceRaised
        border.width: 1
        border.color: selected ? Theme.accentEdge : Theme.line
        Behavior on color { ColorAnimation { duration: Theme.durationFast } }
        Accessible.role: Accessible.Button
        Accessible.name: modelData.title
        Accessible.description: modelData.desc
        FocusRing { targetRadius: Theme.radiusLg; shown: tile.selected && page.activeFocus }
        MouseArea {
            id: mouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onPositionChanged: page.current = tile.position
            onClicked: page.activate(tile.position)
        }
        Kbd { anchors.top: parent.top; anchors.right: parent.right; anchors.margins: Theme.space2; text: String(tile.modelData.digit) }
        ColumnLayout {
            visible: tile.large
            anchors.fill: parent
            anchors.margins: Theme.space4
            spacing: Theme.space1
            AppTile {
                size: 48
                tileId: tile.modelData.tile || ''
                fallbackGlyph: tile.modelData.glyph
                tint: tile.modelData.tint || ''
            }
            Item { implicitHeight: Theme.space1 }
            Text { text: tile.modelData.title; color: Theme.ink; font.family: Theme.fontSans; font.pixelSize: 15; font.weight: Font.DemiBold }
            Text {
                Layout.fillWidth: true
                text: tile.modelData.desc
                color: Theme.inkMuted
                font.family: Theme.fontSans
                font.pixelSize: 13
                wrapMode: Text.Wrap
                maximumLineCount: 2
                elide: Text.ElideRight
            }
            Item { Layout.fillHeight: true }
            Text { text: tile.modelData.status || ''; color: Theme.inkSubtle; font.family: Theme.fontSans; font.pixelSize: 12 }
        }
        RowLayout {
            visible: !tile.large
            anchors.fill: parent
            anchors.leftMargin: Theme.space3
            anchors.rightMargin: Theme.space6
            spacing: Theme.space3
            AppTile {
                size: 28
                fallbackGlyph: tile.modelData.glyph
                tint: tile.modelData.tint || ''
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                Text { text: tile.modelData.title; color: Theme.ink; font.family: Theme.fontSans; font.pixelSize: 14; font.weight: Font.DemiBold }
                Text {
                    Layout.fillWidth: true
                    text: tile.modelData.short || tile.modelData.desc
                    color: Theme.inkMuted
                    font.family: Theme.fontSans
                    font.pixelSize: 12
                    elide: Text.ElideRight
                }
            }
        }
    }

    ColumnLayout {
        id: column
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        spacing: Theme.space3

        PageHeader {
            title: 'Get apps'
            detail: 'Where should the app come from?'
            onBack: page.backRequested()
        }
        RowLayout {
            Layout.fillWidth: true
            visible: Session.live
            spacing: Theme.space2
            Icon { name: 'info'; size: 16; color: Theme.info }
            Text {
                Layout.fillWidth: true
                text: 'You’re trying Arctic Linux: apps you add are gone when you restart.'
                color: Theme.info
                font.family: Theme.fontSans
                font.pixelSize: 13
                wrapMode: Text.Wrap
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space3
            Repeater {
                model: page.big
                delegate: Card { Layout.fillWidth: true; Layout.preferredWidth: 1; implicitHeight: 164 }
            }
        }
        GridLayout {
            Layout.fillWidth: true
            columns: 3
            columnSpacing: Theme.space3
            rowSpacing: Theme.space3
            Repeater {
                model: page.small
                delegate: Card { offset: page.big.length; Layout.fillWidth: true; Layout.preferredWidth: 1; implicitHeight: 56 }
            }
        }
        JobCard { Layout.fillWidth: true }
    }
}
