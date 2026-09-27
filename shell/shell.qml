//@ pragma UseQApplication
//@ pragma Env QS_NO_RELOAD_POPUP=1
import QtQuick
import Quickshell
import Quickshell.Io

// Arctic Linux desktop shell (Quickshell): the bar, screen frame, launcher with Get apps,
// wallpaper picker, power menu, keyboard shortcuts, OSD, lock screen, polkit agent and the
// live-session welcome. It grew out of a personal Quickshell setup (bar + Rofi-style launcher,
// install console, wallpaper picker, docking popovers, screen frame) and is styled entirely
// from the Arctic design tokens (Theme.qml).
//
// Run it with `arctic-shell`. Keybinds reach it through `arctic-shell-ipc <target> <function>`:
//   launcher toggle · wallpapers toggle · apps install · power toggle · osd volume|brightness
//   lock lock · keys toggle · welcome open · dnd refresh · shell reload
ShellRoot {
    id: shell

    // Only one popover at a time.
    function closePopovers(except) {
        [launcher, wallpapers, power, keys].forEach(p => { if (p !== except && p.open) p.open = false; });
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
    function toggleKeys() {
        if (keys.open) keys.close(); else present(keys, null);
    }
    function lock() {
        closePopovers(null);
        lockScreen.lock();
    }

    Variants {
        model: Quickshell.screens
        ScreenFrame {}
    }
    Variants {
        model: Quickshell.screens
        Bar { shell: shell }
    }

    Launcher { id: launcher; shell: shell }
    Wallpapers { id: wallpapers }
    PowerMenu { id: power; shell: shell }
    KeysSheet { id: keys }
    Osd { id: osd }
    LiveWelcome { id: welcome }
    LockScreen { id: lockScreen }
    PolkitDialog {}

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
        target: 'shell'
        function reload(): void { Session.reload(); Theme.reload(); }
        function live(): bool { return Session.live; }
    }
}
