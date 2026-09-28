//@ pragma UseQApplication
//@ pragma Env QS_NO_RELOAD_POPUP=1
import QtQuick
import Quickshell
import Quickshell.Io

// Arctic Linux desktop shell (Quickshell): the bar, screen frame, launcher with Get apps,
// wallpaper picker, power menu, keyboard shortcuts, OSD, lock screen, polkit agent, the
// "updates ready" notice, the live-session welcome, and the notification server with its toasts
// and centre. It grew out of a personal Quickshell setup (bar + Rofi-style launcher,
// install console, wallpaper picker, docking popovers, screen frame) and is styled entirely
// from the Arctic design tokens (Theme.qml).
//
// Run it with `arctic-shell`. Keybinds reach it through `arctic-shell-ipc <target> <function>`:
//   launcher toggle · wallpapers toggle · power toggle · osd volume|brightness|brightnessLevel
//   apps install|remove|toggle · apps open|source <page> · apps search <page> <text> · apps uninstall <desktop-id>
//   lock lock · keys toggle · welcome open · dnd refresh · updates toggle|refresh · shell reload
//   menu toggle|toggleAt <branch>|open <branch>|close (the command menu) · welcome firstLogin
//   notifications center|dismiss|dismissAll|invoke|count|history|dnd|clearHistory|reload
//   keyboard next|set|menu
//   clipboard toggle · emoji toggle · record open|refresh · share pick <fifo> · capture freeze|thaw
//   panel toggle|open|close <network|bluetooth|sound|battery|calendar|media|display> ·
//   quick toggle|open [page] · toggle set|get|states · bar focus
// The bar's menus all open in one BarMenu (one menu at a time); Quick Settings is its `quick` panel.
ShellRoot {
    id: shell
    // What `shell: …` bindings below hand out: inside `Bar { shell: shell }` the name would
    // resolve to Bar's own (still unset) `shell` property, not to this id.
    readonly property var root: shell

    // Only one popover at a time.
    function closePopovers(except) {
        // close(), not open = false: a popover's `dismissed` clears what it held (the Wi-Fi
        // share card forgets the password).
        [launcher, wallpapers, power, keys, updates, notificationCenter, keyboardPanel,
         clipboard, emoji, sharePicker, recordDialog, menuHost, wifiShare, commandMenu, firstLoginCard]
            .forEach(p => { if (p !== except && p.open) p.close(); });
    }
    function present(popover, screen) {
        closePopovers(popover);
        popover.screen = screen || Outputs.focused;
        popover.open = true;
    }
    function toggleLauncher(screen) {
        const target = screen || Outputs.focused;
        if (launcher.open && launcher.screen === target && launcher.view !== 'get') { launcher.close(); return; }
        launcher.view = 'home';
        present(launcher, target);
    }
    // Get apps on one of its pages (getapps/GetApps.js parsePage: choose, flatpak, dnf, web,
    // terminal, remove[/tab], console), with `query` typed in its field.
    function openGetApps(screen, page, query) {
        launcher.view = 'get';
        launcher.getPage = page || 'choose';
        launcher.getQuery = query || '';
        if (launcher.open) launcher.openView('get', launcher.getPage, launcher.getQuery); else present(launcher, screen);
    }
    // Remove an app by its desktop id: the launcher with the remove confirmation.
    function uninstallEntry(screen, desktopId) {
        if (!launcher.open) { launcher.view = 'home'; present(launcher, screen); }
        else if (launcher.view !== 'home') launcher.openView('home');
        launcher.askRemove(desktopId);
    }
    function openWallpapers(screen) { present(wallpapers, screen); }
    function toggleWallpapers(screen) {
        if (wallpapers.open) wallpapers.close(); else openWallpapers(screen);
    }
    function togglePower(screen, x) {
        const target = screen || Outputs.focused;
        if (power.open && power.screen === target) { power.close(); return; }
        power.pointX = x !== undefined ? x : (target ? target.width - Theme.space2 - 17 : 0);
        present(power, target);
    }
    // The updates popover, under the bar's "Restart to update" item (only while updates wait).
    function toggleUpdates(screen, x) {
        const target = screen || Outputs.focused;
        if (updates.open && updates.screen === target) { updates.close(); return; }
        if (!UpdateService.ready) return;
        updates.pointX = x !== undefined ? x : (target ? target.width - 160 : 0);
        present(updates, target);
    }
    // The command menu (Super + Alt + Space), at a branch if one is named ("capture"); pressing
    // the same key again closes it.
    function toggleMenu(path) {
        if (commandMenu.isAt(path) && commandMenu.screen === Outputs.focused) { commandMenu.close(); return; }
        commandMenu.show(path);
        present(commandMenu, null);
    }
    // The notification centre, under the bar's bell (right-aligned when opened by a key).
    function toggleNotifications(screen, x) {
        const target = screen || Outputs.focused;
        if (notificationCenter.open && notificationCenter.screen === target) { notificationCenter.close(); return; }
        openNotifications(target, x);
    }
    function openNotifications(screen, x) {
        const target = screen || Outputs.focused;
        notificationCenter.pointX = x !== undefined ? x : (target ? target.width : 0);
        present(notificationCenter, target);
    }
    // The keyboard-layout menu, under the bar's layout chip.
    function toggleKeyboardMenu(screen, x) {
        const target = screen || Outputs.focused;
        if (keyboardPanel.open && keyboardPanel.screen === target) { keyboardPanel.close(); return; }
        if (!KeyboardService.multiple) return;
        keyboardPanel.pointX = x !== undefined ? x : (target ? target.width : 0);
        present(keyboardPanel, target);
    }
    function toggleKeys() {
        if (keys.open) keys.close(); else present(keys, null);
    }
    // Clipboard history (Super + V) and emoji (Super + Ctrl + E), on the focused screen.
    function toggleClipboard() {
        if (clipboard.open) clipboard.close(); else present(clipboard, null);
    }
    function toggleEmoji() {
        if (emoji.open) emoji.close(); else present(emoji, null);
    }
    function lock() {
        closePopovers(null);
        if (btPair.open) btPair.close();        // says no to a pending pairing question
        lockScreen.lock();
    }

    // ---- bar menus (BarMenu) --------------------------------------------------------------------
    readonly property var barMenu: menuHost
    // A dialog that needs the keyboard is open over a menu: the menu lets go of it meanwhile.
    readonly property bool modalOpen: polkit.active || btPair.open
    function barOn(screen) {
        const all = bars.instances;
        for (let i = 0; i < all.length; i++) if (screen && all[i].screen && all[i].screen.name === screen.name) return all[i];
        return null;
    }
    // The x of the bar item that owns a panel on that screen, or null when it isn't shown.
    function panelAnchor(screen, name) {
        const bar = barOn(screen);
        return bar ? bar.anchorFor(name) : null;
    }
    function togglePanel(name, screen, x, options) {
        const target = screen || Outputs.focused;
        const sameItem = !options || options.item === undefined || options.item === menuHost.options.item;
        if (menuHost.open && menuHost.screen === target && menuHost.panel === name && sameItem && !(options && options.page)) { menuHost.close(); return; }
        // A menu without a bar item here (battery on a desktop) opened as a Quick Settings page.
        if (menuHost.open && menuHost.screen === target && menuHost.panel === 'quick' && menuHost.options.page === name
            && panelAnchor(target, name) === null) { menuHost.close(); return; }
        openPanel(name, target, x, options);
    }
    function openPanel(name, screen, x, options) {
        const target = screen || Outputs.focused;
        if (!target || !menuHost.panels[name]) return;
        const anchor = x !== undefined && x !== null ? x : panelAnchor(target, name);
        // No bar item for it (hidden, or a panel without one): Quick Settings shows it as a page.
        if (anchor === null && name !== 'quick') {
            if (menuHost.panels.quick && ['battery', 'display', 'sound', 'network', 'bluetooth', 'media'].indexOf(name) >= 0)
                openPanel('quick', target, undefined, Object.assign({}, options || {}, { page: name }));
            return;
        }
        const same = menuHost.open && menuHost.screen === target && menuHost.panel === name
                     && (!options || options.item === undefined || options.item === menuHost.options.item);
        menuHost.options = options || {};       // before the panel: a new panel reads it as it loads
        menuHost.panel = name;
        menuHost.pointX = anchor !== null ? anchor : target.width - Theme.space2 - Theme.frameWidth - 190;
        // Already showing: go to the page asked for (panels read options.page when they load).
        if (same && menuHost.item && menuHost.item.showPage) menuHost.item.showPage((options && options.page) || '');
        if (menuHost.open && menuHost.screen === target) { menuHost.focusContent(); return; }
        present(menuHost, target);
    }
    function closePanel() { menuHost.close(); }
    // A saved Wi-Fi network as a QR code (from its page in the network menu).
    function shareWifi(uuid, ssid) {
        const target = menuHost.screen || Outputs.focused;
        wifiShare.show(uuid, ssid);
        present(wifiShare, target);
    }
    // Ctrl+Tab in a menu: the next (dir 1) or previous (-1) bar item that has a menu.
    function cyclePanel(screen, dir) {
        const bar = barOn(screen);
        if (!bar || menuHost.panel === 'quick') return;
        const order = bar.panelOrder();
        const at = order.indexOf(menuHost.panel);
        if (at < 0 || order.length < 2) return;
        openPanel(order[(at + dir + order.length) % order.length], screen, undefined, { keyboard: true });
    }

    Variants {
        model: Quickshell.screens
        ScreenFrame {}
    }
    Variants {
        id: bars
        model: Quickshell.screens
        Bar { shell: root }
    }

    Launcher { id: launcher; shell: root }
    Wallpapers { id: wallpapers }
    PowerMenu { id: power; shell: root }
    UpdatePopover { id: updates }
    KeysSheet { id: keys }
    CommandMenu { id: commandMenu }
    FirstLogin { id: firstLoginCard }
    ClipboardPanel { id: clipboard }
    EmojiPicker { id: emoji }
    PowerKey { locked: lockScreen.secure }
    SharePicker { id: sharePicker }
    RecordDialog { id: recordDialog }
    FrozenScreens { id: frozenScreens }
    Osd { id: osd }
    LiveWelcome { id: welcome }
    WhatsNew { id: whatsNew }
    LockScreen { id: lockScreen }
    PolkitDialog { id: polkit }
    BarMenu { id: menuHost; shell: root }
    Connections {
        target: NetworkService
        function onPasswordWanted(ssid) { shell.openPanel('network', null, undefined, { keyboard: true, ask: ssid }); }
    }
    BluetoothPairDialog { id: btPair }
    WifiShare { id: wifiShare }
    Binding { target: AppsService; property: 'polkitActive'; value: polkit.active }
    NotificationCenter { id: notificationCenter }
    Toasts { shell: root }
    KeyboardPanel { id: keyboardPanel }

    // ---- IPC (arctic-shell-ipc <target> <function>) -----------------------------------------
    IpcHandler {
        target: 'launcher'
        function toggle(): void { shell.toggleLauncher(null); }
        function open(): void { if (!launcher.open) shell.toggleLauncher(null); }
        function close(): void { launcher.close(); }
        // Open with something already typed, e.g. `arctic-shell-ipc launcher search "=2+2"`.
        function search(text: string): void {
            if (!launcher.open) shell.toggleLauncher(null);
            launcher.setQuery(text);
        }
        // Every app (the command menu's Apps › Every app).
        function apps(): void {
            if (!launcher.open) shell.toggleLauncher(null);
            launcher.openView('apps');
        }
    }
    IpcHandler {
        target: 'apps'
        function install(): void { shell.openGetApps(null, 'choose', ''); }
        function remove(): void { shell.openGetApps(null, 'remove', ''); }
        // choose|flatpak|dnf|web|terminal|remove|remove/<tab>|console; source takes the names
        // flathub|fedora|web|terminal|console as well.
        function open(page: string): void { shell.openGetApps(null, page, ''); }
        function source(name: string): void { shell.openGetApps(null, name, ''); }
        function search(page: string, text: string): void { shell.openGetApps(null, page, text); }
        function uninstall(desktopId: string): void { shell.uninstallEntry(null, desktopId); }
        function toggle(): void { shell.toggleLauncher(null); }
    }
    IpcHandler {
        target: 'wallpapers'
        function toggle(): void { shell.toggleWallpapers(null); }
        function open(): void { shell.openWallpapers(null); }
    }
    IpcHandler {
        target: 'power'
        function toggle(): void { shell.togglePower(null, undefined); }
    }
    IpcHandler {
        target: 'menu'
        function toggle(): void { shell.toggleMenu(''); }
        // A branch or row by its id, e.g. `arctic-shell-ipc menu toggleAt capture` (Super + Ctrl + C).
        function toggleAt(path: string): void { shell.toggleMenu(path); }
        function open(path: string): void { commandMenu.show(path); shell.present(commandMenu, null); }
        function close(): void { commandMenu.close(); }
        // Open it with something typed, e.g. `arctic-shell-ipc menu search night`.
        function search(text: string): void { commandMenu.show(''); shell.present(commandMenu, null); commandMenu.search(text); }
    }
    IpcHandler {
        target: 'keys'
        function toggle(): void { shell.toggleKeys(); }
    }
    IpcHandler {
        target: 'osd'
        function volume(): void { osd.showVolume(); }
        function brightness(): void { osd.showBrightness(); }
        // Any level with an icon and a label, e.g. `osd level brightness 40 "DELL U2720Q"`.
        function level(icon: string, percent: int, label: string): void { osd.showLevel(icon, percent, label); }
        // An icon (a design icon name) and a few words, e.g. `osd notice keyboard "Caps Lock on" ""`.
        function notice(icon: string, text: string, detail: string): void { osd.showNotice(icon, text, detail); }
        // arctic-osd after brightness.py stepped the focused monitor: its level and name.
        function brightnessLevel(percent: int, monitor: string): void { osd.showBrightnessLevel(percent, monitor); }
    }
    IpcHandler {
        target: 'lock'
        function lock(): void { shell.lock(); }
        // Only once the compositor confirms it (WlSessionLock.secure), not when the lock is
        // merely requested: arctic-lock waits on this before letting the machine sleep.
        function isLocked(): bool { return lockScreen.secure; }
    }
    IpcHandler {
        target: 'welcome'
        // (not "show": `quickshell ipc call … show` is read as its own show subcommand)
        function open(): void { welcome.show(); }
        // The installed system's welcome, at a new account's first login (arctic-welcome).
        function firstLogin(): void { if (!Session.live) shell.present(firstLoginCard, null); }
    }
    IpcHandler {
        target: 'whatsnew'
        // "What's new" after an Arctic update, shown again (not "show": see welcome above).
        function open(): void { whatsNew.show(); }
    }
    IpcHandler {
        target: 'dnd'
        function refresh(): void { DndService.refresh(); }
    }
    // `arctic-notify` and `arctic-dnd`. dnd(): on, off, toggle, 1h, tomorrow, status → on / off,
    // or "unowned" when another daemon (or mako) has the notifications.
    IpcHandler {
        target: 'notifications'
        function center(): void { shell.toggleNotifications(null, undefined); }
        function toggle(): void { shell.toggleNotifications(null, undefined); }
        function open(): void { if (!notificationCenter.open) shell.openNotifications(null, undefined); }
        function close(): void { notificationCenter.close(); }
        function dismiss(): void { NotificationService.dismissNewest(); }
        function dismissAll(): void { NotificationService.dismissToasts(); }
        function invoke(): void { NotificationService.invokeNewest(); }
        function count(): int { return NotificationService.count; }
        function history(): string { return NotificationService.historyLines(); }
        function clearHistory(): void { NotificationService.clearAll(); }
        function reload(): void { NotificationService.reloadConfig(); }
        function dnd(mode: string): string {
            if (!NotificationService.owned) return 'unowned';
            return NotificationService.setDnd(mode);
        }
    }
    IpcHandler {
        target: 'keyboard'
        function next(): void { KeyboardService.next(); }
        function set(index: int): void { KeyboardService.set(index); }
        function menu(): void { shell.toggleKeyboardMenu(null, undefined); }
    }
    IpcHandler {
        target: 'updates'
        function toggle(): void { shell.toggleUpdates(null, undefined); }
        function refresh(): void { UpdateService.refresh(); }
    }
    // `panel toggle network` etc. (Super + Ctrl + W / B / A / P / T / M). No function is
    // called `show` or `list` (quickshell ipc reads those as its own subcommands).
    IpcHandler {
        target: 'panel'
        // The notification centre and the layout menu are popovers of their own, under the
        // bell and the layout chip.
        function toggle(name: string): void {
            const x = shell.panelAnchor(Outputs.focused, name);
            if (name === 'notifications') shell.toggleNotifications(null, x !== null ? x : undefined);
            else if (name === 'keyboard') shell.toggleKeyboardMenu(null, x !== null ? x : undefined);
            else shell.togglePanel(name, null, undefined, { keyboard: true });
        }
        function open(name: string): void {
            const x = shell.panelAnchor(Outputs.focused, name);
            if (name === 'notifications') shell.openNotifications(null, x !== null ? x : undefined);
            else if (name === 'keyboard') { if (!keyboardPanel.open) shell.toggleKeyboardMenu(null, x !== null ? x : undefined); }
            else shell.openPanel(name, null, undefined, { keyboard: true });
        }
        function close(): void { [menuHost, notificationCenter, keyboardPanel].forEach(p => p.close()); }
    }
    // Quick Settings (Super + A) and the toggle registry behind its tiles.
    IpcHandler {
        target: 'quick'
        function toggle(): void { shell.togglePanel('quick', null, undefined, { keyboard: true }); }
        // A page: network, bluetooth, sound, battery, display, media; empty for the main page.
        function open(page: string): void { shell.openPanel('quick', null, undefined, { keyboard: true, page: page }); }
    }
    IpcHandler {
        target: 'toggle'
        // `toggle set wifi off`: on, off or toggle; answers the new state or "unavailable".
        function set(key: string, mode: string): string { return ToggleRegistry.set(key, mode); }
        function get(key: string): string { return ToggleRegistry.get(key); }
        function states(): string { return ToggleRegistry.states(); }
        // Helpers (arctic-nightlight, arctic-keep-awake) call this after a change.
        function refresh(key: string): void { ToggleRegistry.refresh(key); }
    }
    IpcHandler {
        target: 'bar'
        // The bar on the focused screen takes the keyboard (Super + Alt + B), or gives it back.
        function focus(): void { const b = shell.barOn(Outputs.focused); if (b) b.toggleFocusMode(); }
    }
    IpcHandler {
        target: 'media'
        function playPause(): void { MediaService.playPause(); }
        function next(): void { MediaService.next(); }
        function previous(): void { MediaService.previous(); }
    }
    IpcHandler {
        target: 'audio'
        // The next output device (Shift + Mute key, `arctic-osd output next`).
        function nextOutput(): void { AudioService.nextOutput(); }
    }
    IpcHandler {
        target: 'bluetooth'
        // The Bluetooth menu on its pairing page (Settings → Bluetooth → Pair a device).
        function pair(): void { shell.openPanel('bluetooth', null, undefined, { page: 'pair', keyboard: true }); }
    }
    IpcHandler {
        target: 'clipboard'
        function toggle(): void { shell.toggleClipboard(); }
    }
    IpcHandler {
        target: 'emoji'
        function toggle(): void { shell.toggleEmoji(); }
    }
    IpcHandler {
        target: 'capture'
        // arctic-screenshot: show the monitors as they were at the key press while you select an
        // area (the picture already has any open popover in it), then take them away.
        function freeze(dir: string): bool {
            closePopoversSoon.restart();
            return frozenScreens.freeze(dir);
        }
        function thaw(): void { frozenScreens.thaw(); }
    }
    Timer { id: closePopoversSoon; interval: 1; onTriggered: shell.closePopovers(null) }
    IpcHandler {
        target: 'share'
        // arctic-share-picker (the screen-share portal's chooser) waits on this FIFO for the
        // answer; false when the path isn't one it made.
        function pick(reply: string): bool {
            if (!sharePicker.start(reply)) return false;
            shell.present(sharePicker, null);
            return true;
        }
    }
    IpcHandler {
        target: 'record'
        // arctic-record toggle, when nothing is recording: what to record, and which sound.
        function open(): void { shell.present(recordDialog, null); }
        // arctic-record started or stopped a recording (RecordService re-reads record.json).
        function refresh(): void { RecordService.refresh(); }
    }
    IpcHandler {
        target: 'shell'
        function reload(): void { Session.reload(); Theme.reload(); }
        function live(): bool { return Session.live; }
    }
}
