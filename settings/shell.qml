//@ pragma Env QS_NO_RELOAD_POPUP=1
// Arctic Settings — the settings app of Arctic Linux (Quickshell). A normal window, not a
// layer: Mango floats it centred (rules.conf matches the title "Arctic Settings").
//
//   arctic-settings [page]        open it (on a page: appearance, windows, displays, input,
//                                 shortcuts, apps, network, bluetooth, sound, updates, power,
//                                 startup, about); a second call brings the open one forward
//   quickshell -p <this folder> ipc call settings <function>      see the IpcHandler below
//
// It looks like the rest of Arctic because it is built from the installer's components
// (components/, ported from installer-ui/components) on the live design tokens (Theme.qml
// reads ~/.config/arctic/current/theme.json, so it restyles when the theme changes). Every
// change goes through scripts/arctic_settings.py (Backend.qml).
import QtQuick
import Quickshell
import Quickshell.Io
import "SearchIndex.js" as Index

ShellRoot {
    id: root

    FloatingWindow {
        id: window
        title: "Arctic Settings"
        color: Theme.surface
        // Never bigger than the screen (1280 × 720, or 1366 × 768 at 150 % is 512 px tall), so
        // the bottom of a page (Displays' Apply / Keep) stays reachable. Mango's window rule only
        // floats it; the size is ours.
        readonly property int screenW: screen ? screen.width : 1080
        readonly property int screenH: screen ? screen.height : 740
        implicitWidth: Math.max(320, Math.min(1080, screenW - 80))
        implicitHeight: Math.max(300, Math.min(740, screenH - 80))
        minimumSize: Qt.size(Math.min(760, implicitWidth), Math.min(520, implicitHeight))
        visible: true
        // Closing the window (Super + Q, or the compositor) quits Settings.
        onVisibleChanged: if (!visible) Qt.quit()
        onClosed: Qt.quit()

        Main {
            id: main
            anchors.fill: parent
            Component.onCompleted: {
                const start = Quickshell.env("ARCTIC_SETTINGS_PAGE") || "";
                if (start !== "")
                    main.open(start, Quickshell.env("ARCTIC_SETTINGS_REVEAL") || "");
            }
        }
    }

    // quickshell -p <settings folder> ipc call settings <function> [args]
    // (arctic-settings uses `open`; the headless test and screenshots use the rest).
    IpcHandler {
        target: "settings"

        // Show a page, optionally scrolled to one setting (a searchKey, e.g. windows.gaps).
        function open(page: string): string {
            return main.open(page, "") ? "ok" : "no such page";
        }
        function reveal(page: string, key: string): string {
            return main.open(page, key) ? "ok" : "no such page";
        }
        function search(text: string): void {
            main.setSearch(text);
        }
        function page(): string {
            return main.currentId;
        }
        function pages(): string {
            return Index.PAGES.map(p => p.id).join(" ");
        }
        // For tests: is the page loaded, and has the helper answered?
        function ready(): bool {
            return Backend.ready && Backend.running === 0;
        }
        function theme(): string {
            return Theme.themeId;
        }
        // Change one Mango option the way a control does (tests), and read one back.
        function set(key: string, value: string): void {
            const values = {};
            values[key] = value;
            Backend.set(values, "Saved");
        }
        function value(key: string): string {
            return Backend.opt(key);
        }
        function quit(): void {
            Qt.quit();
        }
    }
}
