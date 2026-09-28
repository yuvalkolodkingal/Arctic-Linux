//@ pragma UseQApplication
//@ pragma Env QS_NO_RELOAD_POPUP=1
import QtQuick
import Quickshell
import Quickshell.Io

// Arctic Linux desktop shell (Quickshell): the bar, screen frame, launcher with Get apps,
// wallpaper picker, power menu, keyboard shortcuts, OSD, lock screen, polkit agent, the
// "updates ready" notice and the live-session welcome. It grew out of a personal Quickshell setup (bar + Rofi-style launcher,
// install console, wallpaper picker, docking popovers, screen frame) and is styled entirely
// from the Arctic design tokens (Theme.qml).
//
// Run it with `arctic-shell`. Keybinds reach it through `arctic-shell-ipc <target> <function>`:
//   launcher toggle · wallpapers toggle · apps install · power toggle · osd volume|brightness
//   lock lock · keys toggle · welcome open · dnd refresh · updates toggle|refresh · shell reload
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
        [launcher, wallpapers, power, keys, updates, menuHost].forEach(p => { if (p !== except && p.open) p.close(); });
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
    function openGetApps(screen) {
        launcher.view = 'get';
        if (launcher.open) launcher.openView('get'); else present(launcher, screen);
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
    function toggleKeys() {
        if (keys.open) keys.close(); else present(keys, null);
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
        menuHost.panel = name;
        menuHost.options = options || {};
        menuHost.pointX = anchor !== null ? anchor : target.width - Theme.space2 - Theme.frameWidth - 190;
        // Already showing: go to the page asked for (panels read options.page when they load).
        if (same && menuHost.item && menuHost.item.showPage) menuHost.item.showPage((options && options.page) || '');
        if (menuHost.open && menuHost.screen === target) { menuHost.focusContent(); return; }
        present(menuHost, target);
    }
    function closePanel() { menuHost.close(); }
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
    Osd { id: osd }
    LiveWelcome { id: welcome }
    LockScreen { id: lockScreen }
    PolkitDialog { id: polkit }
    BarMenu { id: menuHost; shell: root }
    BluetoothPairDialog { id: btPair }

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
    }
    IpcHandler {
        target: 'apps'
        function install(): void { shell.openGetApps(null); }
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
        target: 'keys'
        function toggle(): void { shell.toggleKeys(); }
    }
    IpcHandler {
        target: 'osd'
        function volume(): void { osd.showVolume(); }
        function brightness(): void { osd.showBrightness(); }
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
    }
    IpcHandler {
        target: 'dnd'
        function refresh(): void { DndService.refresh(); }
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
        function toggle(name: string): void { shell.togglePanel(name, null, undefined, { keyboard: true }); }
        function open(name: string): void { shell.openPanel(name, null, undefined, { keyboard: true }); }
        function close(): void { shell.closePanel(); }
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
        target: 'shell'
        function reload(): void { Session.reload(); Theme.reload(); }
        function live(): bool { return Session.live; }
    }
}
