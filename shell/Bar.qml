pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import Quickshell.Bluetooth
import Quickshell.Services.SystemTray
import Quickshell.Services.UPower

// The top bar (design TopBar): 34px frost with a 1px line along the bottom.
// Left: fox mark (launcher) and workspaces 1–5, plus the "Live session" tag on the live USB.
// Centre: the clock, with what listens and the modes that are on to its left, and the
// temperature and what's playing to its right. Right: Install (live only) or Restart to update
// (updates waiting), notifications and Bluetooth (quiet), tray, network, volume, battery, power.
// Anything the system can't report is hidden, never faked.
PanelWindow {
    id: bar
    required property var modelData
    required property var shell
    screen: modelData

    anchors { top: true; left: true; right: true }
    implicitHeight: Theme.barHeight
    color: Theme.frost
    exclusionMode: ExclusionMode.Normal
    // Reserve the frame's top band too, so tiled windows keep Mango's gap from the frame.
    exclusiveZone: Theme.barHeight + Theme.frameWidth
    WlrLayershell.layer: WlrLayer.Top
    WlrLayershell.namespace: 'arctic-bar'

    // The menu open on this bar, if any: tooltips stay quiet meanwhile.
    readonly property var menuHost: bar.shell ? bar.shell.barMenu : null
    readonly property bool menuHere: menuHost !== null && menuHost.open && menuHost.screen === bar.screen
    function menuOpen(name) { return menuHere && menuHost.panel === name; }
    function hint(item, text) { if (!menuHere) tipPopup.request(item, text); }

    // ---- keyboard mode (Super + Alt + B): Left/Right across the items, Enter opens --------
    // The bar takes the keyboard (Top layer); a menu it opens (Overlay) takes it while open and
    // gives it back on close. Esc, the key again or 10 s without a key leave the mode.
    property bool focusMode: false
    property Item focusedStop: null
    WlrLayershell.keyboardFocus: focusMode ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
    function barStops() {
        const out = [];
        function walk(item) {
            const kids = item.children;
            for (let i = 0; i < kids.length; i++) {
                if (!kids[i].visible) continue;
                if (kids[i].barStop === true) out.push(kids[i]); else walk(kids[i]);
            }
        }
        walk(bar.contentItem);
        return out.sort((a, b) => a.mapToItem(null, 0, 0).x - b.mapToItem(null, 0, 0).x);
    }
    function moveFocus(item) {
        if (focusedStop) focusedStop.keyboardFocused = false;
        focusedStop = item;
        if (item) item.keyboardFocused = true;
    }
    function enterFocusMode() {
        const stops = barStops();
        focusMode = true;
        moveFocus(stops.length ? stops[0] : null);
        barKeys.forceActiveFocus();
        idle.restart();
    }
    function leaveFocusMode() {
        focusMode = false;
        moveFocus(null);
        idle.stop();
    }
    function toggleFocusMode() { if (focusMode) leaveFocusMode(); else enterFocusMode(); }
    Timer { id: idle; interval: 10000; onTriggered: if (!bar.menuHere) bar.leaveFocusMode() }
    onMenuHereChanged: {
        if (menuHere) tipPopup.dismiss();
        else if (focusMode) { barKeys.forceActiveFocus(); idle.restart(); }
    }
    Item {
        id: barKeys
        focus: true
        Keys.onPressed: event => {
            if (!bar.focusMode) return;
            idle.restart();
            const stops = bar.barStops();
            const at = stops.indexOf(bar.focusedStop);
            if (event.key === Qt.Key_Right || event.key === Qt.Key_Tab) bar.moveFocus(stops[Math.min(stops.length - 1, at + 1)] || null);
            else if (event.key === Qt.Key_Left || event.key === Qt.Key_Backtab) bar.moveFocus(stops[Math.max(0, at - 1)] || null);
            else if (event.key === Qt.Key_Home) bar.moveFocus(stops[0] || null);
            else if (event.key === Qt.Key_End) bar.moveFocus(stops[stops.length - 1] || null);
            else if (event.key === Qt.Key_Escape) bar.leaveFocusMode();
            else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space || event.key === Qt.Key_Down) {
                const item = bar.focusedStop;
                if (!item) return;
                item.press();
                // An item without a menu starts something else (an app, a workspace): done.
                if (item.hasMenu !== true) bar.leaveFocusMode();
            } else return;
            event.accepted = true;
        }
    }
    function unhint(item) { tipPopup.release(item); }
    // Where a panel's menu hangs: the centre x of the visible bar item that owns it, else null.
    function ownerOf(name) {
        const owners = {
            network: networkItem,
            bluetooth: bluetoothItem,
            sound: volumeItem,
            battery: batteryItem,
            notifications: bellItem,
            keyboard: keyboardItem,
            calendar: clockItem,
            media: mediaItem,
        };
        const item = owners[name] || null;
        return item && item.visible ? item : null;
    }
    function anchorFor(name) {
        const item = ownerOf(name);
        return item ? item.mapToItem(null, item.width / 2, 0).x : null;
    }
    // The menus on this bar from left to right (Ctrl+Tab in a menu).
    function panelOrder() {
        return Object.keys(bar.menuHost.panels)
            .filter(n => ownerOf(n) !== null)
            .sort((a, b) => anchorFor(a) - anchorFor(b));
    }

    SystemClock { id: clock; precision: SystemClock.Minutes }
    BarTooltip { id: tipPopup; anchor.window: bar }

    Rectangle {
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        height: 1
        color: Theme.line
    }

    // ---- left ---------------------------------------------------------------------------
    RowLayout {
        anchors.left: parent.left
        anchors.leftMargin: Theme.space2
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.space1

        BarItem {
            id: launcherItem
            implicitWidth: 18 + 2 * 6
            Mark { size: 18; color: Theme.ink }
            tooltip: 'Apps  (Super + Space)'
            onClicked: bar.shell.toggleLauncher(bar.screen)
            onHoverChanged: h => h ? bar.hint(launcherItem, tooltip) : bar.unhint(launcherItem)
        }
        Workspaces {
            monitorName: bar.screen ? bar.screen.name : ''
            onHovered: (item, text) => bar.hint(item, text)
            onUnhovered: item => bar.unhint(item)
        }
        Rectangle {
            id: liveTag
            visible: Session.live
            Layout.leftMargin: 6
            implicitWidth: liveLabel.implicitWidth + 2 * Theme.space2
            implicitHeight: 20
            radius: Theme.radiusSm
            color: Theme.infoSoft
            Text {
                id: liveLabel
                anchors.centerIn: parent
                text: 'LIVE SESSION'
                color: Theme.info
                font.family: Theme.fontSans
                font.pixelSize: 11
                font.weight: Font.DemiBold
                font.letterSpacing: 0.66
            }
            MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                onContainsMouseChanged: containsMouse ? bar.hint(liveTag, 'Nothing you do here is saved to this computer') : bar.unhint(liveTag)
            }
        }
    }

    // ---- centre: clock (tabular figures); click for the calendar ------------------------
    BarItem {
        id: clockItem
        anchors.centerIn: parent
        text: Qt.formatDateTime(clock.date, 'ddd d MMM · hh:mm')
        textWeight: Font.DemiBold
        hasMenu: true
        active: bar.menuOpen('calendar')
        tooltip: Qt.locale().toString(clock.date, 'dddd d MMMM yyyy') + '  (Super + Ctrl + T)'
        onClicked: bar.shell.togglePanel('calendar', bar.screen, clockItem.mapToItem(null, clockItem.width / 2, 0).x)
        onHoverChanged: h => h ? bar.hint(clockItem, tooltip) : bar.unhint(clockItem)
    }
    // Left of the clock: what is listening or watching, and the modes that are on.
    ModeIndicators {
        anchors.right: clockItem.left
        anchors.rightMargin: Theme.space2
        anchors.verticalCenter: parent.verticalCenter
        bar: bar
    }
    // Right of the clock: the temperature (Settings > Appearance > Weather > "Show the
    // temperature on the bar"), only with a reading; a click opens the calendar, which has the
    // forecast under the month.
    WeatherItem {
        id: weatherItem
        anchors.left: clockItem.right
        anchors.leftMargin: Theme.space2
        anchors.verticalCenter: parent.verticalCenter
        visible: WeatherService.showInBar
        hasMenu: true
        tooltip: WeatherService.summary + '  (Super + Ctrl + T)'
        onClicked: bar.shell.togglePanel('calendar', bar.screen, clockItem.mapToItem(null, clockItem.width / 2, 0).x)
        onHoverChanged: h => h ? bar.hint(weatherItem, tooltip) : bar.unhint(weatherItem)
    }
    // Right of the clock (and the temperature) while a media player exists: its title; click for
    // the media menu, middle click plays or pauses, scrolling skips.
    BarItem {
        id: mediaItem
        anchors.left: weatherItem.visible ? weatherItem.right : clockItem.right
        anchors.leftMargin: weatherItem.visible ? Theme.space1 : Theme.space2
        anchors.verticalCenter: parent.verticalCenter
        visible: MediaService.available && MediaService.title !== ''
        hasMenu: true
        active: bar.menuOpen('media')
        iconName: MediaService.playing ? 'music' : 'pause'
        iconColor: Theme.inkMuted
        text: MediaService.title
        textColor: Theme.inkMuted
        maxTextWidth: 180
        tooltip: MediaService.title + (MediaService.artist ? ' — ' + MediaService.artist : '')
                 + (MediaService.playing ? '' : ' · paused') + '  (Super + Ctrl + M)'
        onClicked: bar.shell.togglePanel('media', bar.screen, mediaItem.mapToItem(null, mediaItem.width / 2, 0).x)
        onMiddleClicked: MediaService.playPause()
        onScrolled: steps => steps > 0 ? MediaService.previous() : MediaService.next()
        onHoverChanged: h => h ? bar.hint(mediaItem, tooltip) : bar.unhint(mediaItem)
    }

    // ---- right ----------------------------------------------------------------------------
    RowLayout {
        anchors.right: parent.right
        anchors.rightMargin: Theme.space2
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.space1

        BarItem {
            id: installItem
            visible: Session.live
            accentFill: true
            iconName: 'download'
            iconColor: Theme.onAccent
            text: 'Install'
            textColor: Theme.onAccent
            textWeight: Font.DemiBold
            tooltip: 'Install Arctic Linux  (Super + I)'
            onClicked: Quickshell.execDetached(['arctic-start-installer'])
            onHoverChanged: h => h ? bar.hint(installItem, tooltip) : bar.unhint(installItem)
        }
        UpdateIndicator {
            id: updateItem
            onClicked: bar.shell.toggleUpdates(bar.screen, updateItem.mapToItem(null, updateItem.width / 2, 0).x)
            onHoverChanged: h => h ? bar.hint(updateItem, tooltip) : bar.unhint(updateItem)
        }

        // Quiet group: notifications and Bluetooth sit in ink-muted.
        // The bell: the notification centre (right click: do not disturb). A dot marks what
        // arrived since the centre was last opened. When the shell doesn't own notifications
        // (mako in the fallback), it is 0.2's bell: do not disturb, right click brings one back.
        BarItem {
            id: bellItem
            readonly property bool centre: NotificationService.owned
            readonly property int unseen: NotificationService.unseen
            visible: centre || DndService.available
            iconName: DndService.active ? 'bell-off' : 'bell'
            iconColor: Theme.inkMuted
            tooltip: !centre ? (DndService.active ? 'Do not disturb is on · only urgent notifications show' : 'Notifications · click for do not disturb')
                     : (DndService.active ? 'Do not disturb is on' : unseen > 0 ? unseen + (unseen === 1 ? ' new notification' : ' new notifications') : 'Notifications')
                       + '  (Super + Alt + N · right click: do not disturb)'
            onClicked: centre ? bar.shell.toggleNotifications(bar.screen, bellItem.mapToItem(null, bellItem.width / 2, 0).x) : DndService.toggle()
            onRightClicked: centre ? DndService.toggle() : Quickshell.execDetached(['makoctl', 'restore'])
            onHoverChanged: h => h ? bar.hint(bellItem, tooltip) : bar.unhint(bellItem)
            Item {
                // Unseen: a dot on the bell's shoulder, in ink (a count, not a status colour).
                visible: bellItem.centre && bellItem.unseen > 0 && !DndService.active
                Layout.preferredWidth: 0
                Layout.preferredHeight: 0
                Layout.leftMargin: -Theme.space1
                Rectangle {
                    x: -7
                    y: -8
                    width: 6
                    height: 6
                    radius: 3
                    color: Theme.ink
                    border.width: 1
                    border.color: Theme.frost
                }
            }
        }
        // The keyboard layout ("EN"), only with more than one layout.
        KeyboardItem {
            id: keyboardItem
            onRightClicked: bar.shell.toggleKeyboardMenu(bar.screen, keyboardItem.mapToItem(null, keyboardItem.width / 2, 0).x)
            onHoverChanged: h => h ? bar.hint(keyboardItem, tooltip) : bar.unhint(keyboardItem)
        }
        BarItem {
            id: bluetoothItem
            readonly property var adapter: Bluetooth.defaultAdapter
            readonly property var connected: adapter ? adapter.devices.values.filter(d => d.connected) : []
            visible: adapter !== null
            hasMenu: true
            active: bar.menuOpen('bluetooth')
            iconName: 'bluetooth'
            iconColor: adapter && adapter.enabled ? Theme.inkMuted : Theme.inkDisabled
            tooltip: !adapter ? '' : !adapter.enabled ? 'Bluetooth off  (Super + Ctrl + B)'
                     : connected.length ? 'Connected to ' + connected.map(d => d.name + (d.batteryAvailable ? ' · ' + Math.round(d.battery * 100) + ' %' : '')).join(', ')
                     : 'Bluetooth on  (Super + Ctrl + B)'
            onClicked: bar.shell.togglePanel('bluetooth', bar.screen, bluetoothItem.mapToItem(null, bluetoothItem.width / 2, 0).x)
            onRightClicked: if (adapter) adapter.enabled = !adapter.enabled
            onHoverChanged: h => h ? bar.hint(bluetoothItem, tooltip) : bar.unhint(bluetoothItem)
        }

        Repeater {
            // nm-applet's own icon is folded into the network item below, and blueman's applet
            // (started by "More Bluetooth options…") into the Bluetooth item.
            model: SystemTray.items.values.filter(i => i.id !== 'nm-applet' && !String(i.id).startsWith('blueman'))
            BarItem {
                id: trayItem
                required property var modelData
                function openMenu() {
                    bar.shell.togglePanel('tray', bar.screen, trayItem.mapToItem(null, trayItem.width / 2, 0).x, { item: trayItem.modelData });
                }
                implicitWidth: 16 + 2 * Theme.space2
                hasMenu: modelData.hasMenu
                active: bar.menuOpen('tray') && bar.menuHost.options.item === modelData
                tooltip: modelData.tooltipTitle || modelData.title || modelData.id
                Image {
                    Layout.preferredWidth: 16
                    Layout.preferredHeight: 16
                    sourceSize: Qt.size(16, 16)
                    source: trayItem.modelData.icon
                    fillMode: Image.PreserveAspectFit
                }
                onClicked: modelData.onlyMenu && modelData.hasMenu ? openMenu() : modelData.activate()
                onMiddleClicked: modelData.secondaryActivate()
                onRightClicked: if (modelData.hasMenu) openMenu()
                onScrolled: steps => modelData.scroll(steps, false)
                onHoverChanged: h => h ? bar.hint(trayItem, tooltip) : bar.unhint(trayItem)
            }
        }

        BarItem {
            id: networkItem
            // Click: the network menu (Wi-Fi, wired, VPN); right click: Settings → Network.
            visible: NetworkService.available
            hasMenu: true
            active: bar.menuOpen('network')
            iconName: NetworkService.iconName
            tooltip: NetworkService.summary + (NetworkService.vpnActive ? ' · VPN on' : '') + '  (Super + Ctrl + W)'
            onClicked: bar.shell.togglePanel('network', bar.screen, networkItem.mapToItem(null, networkItem.width / 2, 0).x)
            onRightClicked: Quickshell.execDetached(['arctic-settings', 'network'])
            onHoverChanged: h => h ? bar.hint(networkItem, tooltip) : bar.unhint(networkItem)
        }
        BarItem {
            id: volumeItem
            visible: AudioService.available
            iconName: AudioService.muted ? 'volume-mute' : 'volume'
            text: AudioService.muted ? 'Muted' : AudioService.percent + '%'
            hasMenu: true
            active: bar.menuOpen('sound')
            tooltip: (AudioService.description ? AudioService.description + ' · ' : '') + (AudioService.muted ? 'Muted' : AudioService.percent + '%') + '  (Super + Ctrl + A)'
            onClicked: bar.shell.togglePanel('sound', bar.screen, volumeItem.mapToItem(null, volumeItem.width / 2, 0).x)
            onRightClicked: AudioService.toggleMute()
            onScrolled: steps => AudioService.step(steps)
            onHoverChanged: h => h ? bar.hint(volumeItem, tooltip) : bar.unhint(volumeItem)
        }
        BarItem {
            id: batteryItem
            // Charge, and the battery menu (power mode, charge limit) on click. At or below
            // UPower's low level the word travels with the colour.
            readonly property var b: BatteryService
            visible: b.present
            hasMenu: true
            active: bar.menuOpen('battery')
            iconName: b.charging ? 'battery-charging' : 'battery'
            iconColor: b.present && !b.charging && b.percent <= 10 ? Theme.error : Theme.ink
            text: b.percent + '%' + (b.low ? ' · Low' : '')
            tooltip: (b.full ? 'Fully charged' : b.percent + '%' + (b.timeText ? ' · ' + b.timeText : ''))
                     + (PowerService.available && PowerService.current ? ' · ' + PowerService.current.label : '') + '  (Super + Ctrl + P)'
            onClicked: bar.shell.togglePanel('battery', bar.screen, batteryItem.mapToItem(null, batteryItem.width / 2, 0).x)
            onHoverChanged: h => h ? bar.hint(batteryItem, tooltip) : bar.unhint(batteryItem)
        }
        BarItem {
            id: powerItem
            iconName: 'power'
            tooltip: 'Power  (Super + Esc)'
            onClicked: bar.shell.togglePower(bar.screen, powerItem.mapToItem(null, powerItem.width / 2, 0).x)
            onHoverChanged: h => h ? bar.hint(powerItem, tooltip) : bar.unhint(powerItem)
        }
    }
}
