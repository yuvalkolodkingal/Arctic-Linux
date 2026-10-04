pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Bluetooth
import Quickshell.Services.SystemTray
import "Weather.js" as Weather

// Side bars use the thickness as their control size, with upright, centred labels. Flexible
// space separates navigation, time/status and system controls; short screens scroll the entire
// column so privacy indicators, tray items and keyboard navigation remain reachable.
Item {
    id: root
    required property var bar
    readonly property real controlWidth: Math.max(20, width - 4)
    readonly property real controlHeight: Math.max(26, Theme.barHeight - 8)
    readonly property int iconSize: Math.max(16, Math.round(Theme.barHeight / 2))
    readonly property int textSize: Math.max(12, Math.min(17, Math.round(Theme.barHeight * 0.4)))
    function coordinate(item) { return item.mapToItem(bar.contentItem, 0, item.height / 2).y; }
    function open(name, item, options) { bar.shell.togglePanel(name, bar.screen, coordinate(item), options); }
    function ownerOf(name) {
        const items = { network: network, bluetooth: bluetooth, sound: sound, battery: battery,
            notifications: bell, keyboard: keyboard, calendar: clockItem, media: media, quick: quick };
        return items[name] || null;
    }
    function ensureVisible(item) {
        const y = item.mapToItem(column, 0, 0).y;
        scroll.contentY = Math.max(0, Math.min(scroll.contentHeight - scroll.height,
            y < scroll.contentY ? y : y + item.height > scroll.contentY + scroll.height
            ? y + item.height - scroll.height : scroll.contentY));
    }
    component Button: BarItem {
        id: button
        Layout.alignment: Qt.AlignHCenter
        Layout.preferredWidth: root.controlWidth
        implicitHeight: root.controlHeight
        horizontalPadding: 2
        maxTextWidth: root.controlWidth - 4
        iconSize: root.iconSize
        textSize: root.textSize
        textAlignment: Text.AlignHCenter
        radius: Math.min(width, height) / 2
        onHoverChanged: h => h ? root.bar.hint(button, tooltip) : root.bar.unhint(button)
    }
    SystemClock { id: clock; precision: SystemClock.Minutes }
    Flickable {
        id: scroll
        anchors.fill: parent
        anchors.topMargin: Theme.space2
        anchors.bottomMargin: Theme.space2
        contentWidth: width
        contentHeight: column.height
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        // Re-clamp after thickness/scaling, widget visibility or screen size changes.
        onContentHeightChanged: returnToBounds()
        onHeightChanged: returnToBounds()
        ColumnLayout {
            id: column
            width: scroll.width
            height: Math.max(implicitHeight, scroll.height)
            spacing: Theme.space1
            Button { iconName: 'grid'; tooltip: 'Apps  (Super + Space)'; onClicked: root.bar.shell.toggleLauncher(root.bar.screen) }
            Workspaces {
                visible: Session.barWorkspaces
                vertical: true
                verticalWidth: root.controlWidth
                verticalHeight: root.controlHeight
                labelSize: root.textSize
                Layout.preferredWidth: root.width
                Layout.alignment: Qt.AlignHCenter
                monitorName: root.bar.screen ? root.bar.screen.name : ''
                onHovered: (item, text) => root.bar.hint(item, text)
                onUnhovered: item => root.bar.unhint(item)
            }
            Item { Layout.fillHeight: true; Layout.minimumHeight: Theme.space2 }
            ModeIndicators {
                Layout.fillWidth: true
                bar: root.bar
                vertical: true
                controlWidth: root.controlWidth
                controlHeight: root.controlHeight
                iconSize: root.iconSize
            }
            Button {
                id: clockItem
                visible: Session.barClock
                text: Qt.formatDateTime(clock.date, 'hh\nmm')
                textWeight: Font.DemiBold
                implicitHeight: Math.max(root.controlHeight, root.textSize * 2 + 10)
                tooltip: Qt.locale().toString(clock.date, 'dddd d MMMM yyyy hh:mm')
                hasMenu: true
                active: root.bar.menuOpen('calendar')
                onClicked: root.open('calendar', clockItem)
            }
            Button {
                id: weather
                visible: WeatherService.showInBar
                tooltip: WeatherService.summary; hasMenu: true
                implicitHeight: root.iconSize + root.textSize + 10
                onClicked: root.open('calendar', weather)
                Column {
                    spacing: 2
                    Image {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: root.iconSize; height: root.iconSize
                        sourceSize: Qt.size(width, height)
                        source: WeatherService.current ? Weather.icon(Weather.describe(WeatherService.current.code, WeatherService.current.is_day).glyph, Theme.ink) : ''
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: WeatherService.current ? Weather.tempText(WeatherService.current.temp) : ''
                        color: Theme.ink; font.family: Theme.fontSans; font.pixelSize: root.textSize
                    }
                }
            }
            Button {
                id: media
                visible: Session.barMedia && MediaService.available
                iconName: MediaService.playing ? 'music' : 'pause'
                tooltip: MediaService.title + (MediaService.artist ? ' — ' + MediaService.artist : '')
                hasMenu: true; active: root.bar.menuOpen('media')
                onClicked: root.open('media', media)
                onMiddleClicked: MediaService.playPause()
                onScrolled: steps => steps > 0 ? MediaService.previous() : MediaService.next()
            }
            Item { Layout.fillHeight: true; Layout.minimumHeight: Theme.space2 }
            Button {
                visible: Session.live; iconName: 'download'; tooltip: 'Install Arctic Linux'; accentFill: true
                onClicked: Quickshell.execDetached(['arctic-start-installer'])
            }
            Button {
                id: update
                visible: UpdateService.ready; iconName: 'download'; tooltip: UpdateService.summary; accentFill: true
                onClicked: root.bar.shell.toggleUpdates(root.bar.screen, root.coordinate(update))
            }
            Button {
                id: bell
                visible: NotificationService.owned || DndService.available
                iconName: DndService.active ? 'bell-off' : 'bell'; tooltip: 'Notifications · ' + NotificationService.unseen + ' new'
                hasMenu: NotificationService.owned
                onClicked: NotificationService.owned ? root.bar.shell.toggleNotifications(root.bar.screen, root.coordinate(bell)) : DndService.toggle()
                onRightClicked: DndService.toggle()
            }
            KeyboardItem {
                id: keyboard
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: root.controlWidth
                implicitHeight: root.controlHeight
                horizontalPadding: 2; textSize: root.textSize; textAlignment: Text.AlignHCenter
                onRightClicked: root.bar.shell.toggleKeyboardMenu(root.bar.screen, root.coordinate(keyboard))
                onHoverChanged: h => h ? root.bar.hint(keyboard, tooltip) : root.bar.unhint(keyboard)
            }
            Button {
                id: bluetooth
                readonly property var adapter: Bluetooth.defaultAdapter
                visible: adapter !== null
                iconName: 'bluetooth'; iconColor: adapter && adapter.enabled ? Theme.inkMuted : Theme.inkDisabled
                tooltip: adapter && adapter.enabled ? 'Bluetooth on' : 'Bluetooth off'; hasMenu: true
                active: root.bar.menuOpen('bluetooth')
                onClicked: root.open('bluetooth', bluetooth)
                onRightClicked: if (adapter) adapter.enabled = !adapter.enabled
            }
            Repeater {
                model: Session.barTray ? SystemTray.items.values.filter(i => i.id !== 'nm-applet' && !String(i.id).startsWith('blueman')) : []
                Button {
                    id: tray
                    required property var modelData
                    tooltip: modelData.tooltipTitle || modelData.title || modelData.id
                    hasMenu: modelData.hasMenu
                    active: root.bar.menuOpen('tray') && root.bar.menuHost.options.item === modelData
                    function openMenu() { root.open('tray', tray, {item: modelData}); }
                    Image {
                        Layout.preferredWidth: root.iconSize; Layout.preferredHeight: root.iconSize
                        sourceSize: Qt.size(root.iconSize, root.iconSize); source: tray.modelData.icon
                        fillMode: Image.PreserveAspectFit
                    }
                    onClicked: modelData.onlyMenu && modelData.hasMenu ? openMenu() : modelData.activate()
                    onRightClicked: if (modelData.hasMenu) openMenu()
                    onMiddleClicked: modelData.secondaryActivate()
                    onScrolled: steps => modelData.scroll(steps, false)
                }
            }
            Button {
                id: network
                visible: NetworkService.available; iconName: NetworkService.iconName; tooltip: NetworkService.summary; hasMenu: true
                active: root.bar.menuOpen('network')
                onClicked: root.open('network', network)
                onRightClicked: Quickshell.execDetached(['arctic-settings', 'network'])
            }
            Button {
                id: sound
                visible: AudioService.available; iconName: AudioService.muted ? 'volume-mute' : 'volume'
                tooltip: AudioService.description + ' · ' + AudioService.percent + '%'; hasMenu: true
                active: root.bar.menuOpen('sound')
                onClicked: root.open('sound', sound)
                onRightClicked: AudioService.toggleMute()
                onScrolled: steps => AudioService.step(steps)
            }
            Button {
                id: battery
                visible: BatteryService.present; iconName: BatteryService.charging ? 'battery-charging' : 'battery'
                tooltip: BatteryService.percent + '% · ' + BatteryService.timeText; hasMenu: true
                active: root.bar.menuOpen('battery')
                onClicked: root.open('battery', battery)
            }
            Button { id: quick; iconName: 'sliders'; tooltip: 'Quick settings'; hasMenu: true; active: root.bar.menuOpen('quick'); onClicked: root.open('quick', quick) }
            Button { id: power; iconName: 'power'; tooltip: 'Power'; hasMenu: true; onClicked: root.bar.shell.togglePower(root.bar.screen, root.coordinate(power)) }
        }
    }
}
