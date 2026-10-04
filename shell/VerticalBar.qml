pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Bluetooth
import Quickshell.Services.SystemTray

// Upright controls on either side edge; short screens scroll without losing controls.
Item {
    id: root
    required property var bar
    function coordinate(item) { return item.mapToItem(bar.contentItem, 0, item.height / 2).y; }
    function open(name, item, options) { bar.shell.togglePanel(name, bar.screen, coordinate(item), options); }
    function ownerOf(name) {
        const items = { network: network, bluetooth: bluetooth, sound: sound, battery: battery,
            notifications: bell, keyboard: keyboard, calendar: clockItem, media: media, quick: quick };
        return items[name] || null;
    }
    function ensureVisible(item) {
        if (item.parent === indicators) return;
        const y = item.mapToItem(column, 0, 0).y;
        if (y < scroll.contentY) scroll.contentY = y;
        else if (y + item.height > scroll.contentY + scroll.height) scroll.contentY = y + item.height - scroll.height;
    }
    component Button: BarItem {
        id: button
        Layout.alignment: Qt.AlignHCenter
        implicitWidth: Math.max(26, root.width - 2)
        maxTextWidth: Math.max(16, root.width - 8)
        onHoverChanged: h => h ? root.bar.hint(button, tooltip) : root.bar.unhint(button)
    }
    SystemClock { id: clock; precision: SystemClock.Minutes }
    ModeIndicators {
        id: indicators
        anchors.top: parent.top
        anchors.horizontalCenter: parent.horizontalCenter
        bar: root.bar
        vertical: true
    }
    Flickable {
        id: scroll
        anchors.fill: parent
        anchors.topMargin: indicators.implicitHeight > 0 ? indicators.implicitHeight + 4 : 0
        contentWidth: width
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ColumnLayout {
            id: column
            width: scroll.width
            spacing: 4
            Button { iconName: 'grid'; tooltip: 'Apps'; onClicked: root.bar.shell.toggleLauncher(root.bar.screen) }
            Workspaces {
                visible: Session.barWorkspaces
                vertical: true
                Layout.preferredWidth: root.width
                Layout.alignment: Qt.AlignHCenter
                monitorName: root.bar.screen ? root.bar.screen.name : ''
                onHovered: (item, text) => root.bar.hint(item, text)
                onUnhovered: item => root.bar.unhint(item)
            }
            Button {
                id: clockItem
                visible: Session.barClock
                text: Qt.formatDateTime(clock.date, 'hh\nmm')
                implicitHeight: 42
                tooltip: Qt.locale().toString(clock.date, 'dddd d MMMM yyyy hh:mm')
                hasMenu: true
                onClicked: root.open('calendar', clockItem)
            }
            Button {
                visible: WeatherService.showInBar
                iconName: 'sun'; tooltip: WeatherService.summary; hasMenu: true
                onClicked: root.open('calendar', clockItem)
            }
            Button {
                id: media
                visible: Session.barMedia && MediaService.available
                iconName: MediaService.playing ? 'music' : 'pause'; tooltip: MediaService.title
                hasMenu: true
                onClicked: root.open('media', media)
                onMiddleClicked: MediaService.playPause()
                onScrolled: steps => steps > 0 ? MediaService.previous() : MediaService.next()
            }
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
                onClicked: NotificationService.owned ? root.bar.shell.toggleNotifications(root.bar.screen, root.coordinate(bell)) : DndService.toggle()
                onRightClicked: DndService.toggle()
            }
            KeyboardItem {
                id: keyboard
                Layout.alignment: Qt.AlignHCenter
                onRightClicked: root.bar.shell.toggleKeyboardMenu(root.bar.screen, root.coordinate(keyboard))
                onHoverChanged: h => h ? root.bar.hint(keyboard, tooltip) : root.bar.unhint(keyboard)
            }
            Button {
                id: bluetooth
                visible: Bluetooth.defaultAdapter !== null
                iconName: 'bluetooth'; tooltip: 'Bluetooth'; hasMenu: true
                onClicked: root.open('bluetooth', bluetooth)
            }
            Repeater {
                model: Session.barTray ? SystemTray.items.values.filter(i => i.id !== 'nm-applet' && !String(i.id).startsWith('blueman')) : []
                Button {
                    id: tray
                    required property var modelData
                    tooltip: modelData.tooltipTitle || modelData.title || modelData.id
                    hasMenu: modelData.hasMenu
                    function openMenu() { root.open('tray', tray, {item: modelData}); }
                    Image { Layout.preferredWidth: 16; Layout.preferredHeight: 16; sourceSize: Qt.size(16,16); source: tray.modelData.icon }
                    onClicked: modelData.onlyMenu && modelData.hasMenu ? openMenu() : modelData.activate()
                    onRightClicked: if (modelData.hasMenu) openMenu()
                    onMiddleClicked: modelData.secondaryActivate()
                    onScrolled: steps => modelData.scroll(steps, false)
                }
            }
            Button {
                id: network
                visible: NetworkService.available; iconName: NetworkService.iconName; tooltip: NetworkService.summary; hasMenu: true
                onClicked: root.open('network', network)
                onRightClicked: Quickshell.execDetached(['arctic-settings', 'network'])
            }
            Button {
                id: sound
                visible: AudioService.available; iconName: AudioService.muted ? 'volume-mute' : 'volume'
                tooltip: AudioService.description + ' · ' + AudioService.percent + '%'; hasMenu: true
                onClicked: root.open('sound', sound)
                onRightClicked: AudioService.toggleMute()
                onScrolled: steps => AudioService.step(steps)
            }
            Button {
                id: battery
                visible: BatteryService.present; iconName: BatteryService.charging ? 'battery-charging' : 'battery'
                tooltip: BatteryService.percent + '% · ' + BatteryService.timeText; hasMenu: true
                onClicked: root.open('battery', battery)
            }
            Button { id: quick; iconName: 'sliders'; tooltip: 'Quick settings'; hasMenu: true; onClicked: root.open('quick', quick) }
            Button { id: power; iconName: 'power'; tooltip: 'Power'; onClicked: root.bar.shell.togglePower(root.bar.screen, root.coordinate(power)) }
        }
    }
}
