//@ pragma Env QS_NO_RELOAD_POPUP=1
import QtQuick
import Quickshell
import Quickshell.Io
import ".."

// Copy this entry point into a throwaway copy of shell/ before launching it. It exercises the
// real bar and popup components without replacing the user's shell.
ShellRoot {
    id: preview
    readonly property var root: preview
    readonly property var barMenu: menu
    readonly property var barPopovers: [menu, extra]
    readonly property bool modalOpen: false
    function onScreen(name) {
        return Quickshell.screens.find(s => s.name === name) || Quickshell.screens[0];
    }
    function barOn(screen) { return bars.instances.find(b => b.screen === screen); }
    function togglePanel(name, screen, coordinate, options) {
        if (menu.open && menu.panel === name && menu.screen === screen) { menu.close(); return; }
        extra.close();
        menu.options = options || {};
        menu.panel = name;
        menu.pointX = coordinate === undefined ? barOn(screen).anchorFor(name) || 300 : coordinate;
        menu.screen = screen;
        menu.open = true;
    }
    function popup(screen, coordinate) {
        menu.close(); extra.screen = screen; extra.pointX = coordinate || 300; extra.open = !extra.open;
    }
    function toggleLauncher(screen) { popup(screen, 300); }
    function togglePower(screen, coordinate) { popup(screen, coordinate); }
    function toggleUpdates(screen, coordinate) { popup(screen, coordinate); }
    function toggleNotifications(screen, coordinate) { popup(screen, coordinate); }
    function toggleKeyboardMenu(screen, coordinate) { popup(screen, coordinate); }
    function cyclePanel(screen, dir) {}
    Variants { id: bars; model: Quickshell.screens; Bar { shell: preview.root } }
    BarMenu { id: menu; shell: preview.root }
    Popover {
        id: extra
        placement: 'point'; scrim: false; cardWidth: 280; cardHeight: 120
        Text { anchors.centerIn: parent; text: 'Separate popup host'; color: Theme.ink; font.pixelSize: 20 }
    }
    IpcHandler {
        target: 'testbar'
        function configure(edge: string, size: int, hide: bool): void {
            menu.close(); extra.close();
            Session.settings = Object.assign({}, Session.settings, {barPosition: edge, barSize: size, barAutoHide: hide});
        }
        function focus(name: string): void { barOn(onScreen(name)).toggleFocusMode(); }
        function key(name: string, end: bool): void {
            const b = barOn(onScreen(name)), stops = b.barStops();
            b.moveFocus(end ? stops[stops.length - 1] : stops[0]);
        }
        function open(name: string, panel: string): void {
            const screen = onScreen(name);
            togglePanel(panel, screen, barOn(screen).anchorFor(panel), {});
        }
        function separate(name: string): void { popup(onScreen(name), 700); }
        function close(): void { menu.close(); extra.close(); }
        function reset(): void {
            menu.close(); extra.close(); RecordService.recording = false;
            for (const b of bars.instances) b.leaveFocusMode();
            Session.reload();
        }
        function recording(enabled: bool): void { RecordService.startedAt = Date.now() / 1000; RecordService.recording = enabled; }
        function motion(reduced: bool): void { Session.motionFile = reduced; }
        function state(): string {
            return JSON.stringify(bars.instances.map(b => ({
                screen: b.screen.name, edge: Session.barPosition, thickness: Theme.barHeight,
                width: b.width, height: b.height, expanded: b.expanded, reveal: b.reveal,
                exposed: b.exposed, heldOpen: b.heldOpen, popupHere: b.popupHere, focus: b.focusMode,
                anchors: {calendar: b.anchorFor('calendar'), sound: b.anchorFor('sound'), network: b.anchorFor('network'), quick: b.anchorFor('quick')},
                focused: b.focusedStop ? {y: b.focusedStop.mapToItem(b.contentItem, 0, 0).y, height: b.focusedStop.height} : null,
                stops: b.barStops().map(i => ({label: i.tooltip || i.text || 'Workspace',
                    x: i.mapToItem(b.contentItem, 0, 0).x, y: i.mapToItem(b.contentItem, 0, 0).y,
                    width: i.width, height: i.height})),
                popup: menu.open && menu.screen === b.screen ? {x: menu.card.x, y: menu.card.y,
                    width: menu.card.width, height: menu.card.height, anchor: menu.pointX} : null
            })));
        }
    }
}
