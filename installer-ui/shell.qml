// Arctic Linux installer — Quickshell frontend for the 12-step wizard.
// Run: quickshell -p /usr/share/arctic/installer-ui   (packaged: arctic-installer)
// Dev: installer-ui/dev/run.sh (uses dev/mock-bridge.py, no root needed).
//
// One full-screen layer-shell window on the output the compositor picks (the
// focused one), exclusive keyboard focus. The engine owns the flow (Engine.qml,
// Wizard.qml); this file only hosts the window and the test/automation IPC.
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

ShellRoot {
    id: root

    Component.onCompleted: Engine.start()

    PanelWindow {
        id: win
        anchors {
            top: true
            bottom: true
            left: true
            right: true
        }
        exclusionMode: ExclusionMode.Ignore
        color: Theme.surface
        WlrLayershell.layer: WlrLayer.Top
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
        WlrLayershell.namespace: "arctic-installer"

        Frame {
            id: frame
            anchors.fill: parent
        }
    }

    // quickshell -p <dir> ipc call installer <function> [args]
    // Used by dev/test-headless.sh to drive the wizard; handy for kiosk scripts too.
    IpcHandler {
        target: "installer"

        // Press the primary footer action (Next / Erase disk and install / Restart now).
        function next(): string {
            if (!frame.page)
                return "no page";
            if (!frame.nextEnabled)
                return "next disabled";
            frame.goNext();
            return "ok";
        }
        function back(): string {
            frame.goBack();
            return "ok";
        }
        // Go back to a finished step (as the Summary "Change" links do).
        function goto(id: string): string {
            Wizard.gotoStep(id);
            return "ok";
        }
        // Fill the current page's form: a JSON object, see each step's fillForm().
        function fill(json: string): string {
            if (!frame.page)
                return "no page";
            let values;
            try {
                values = JSON.parse(json);
            } catch (e) {
                return "bad json: " + e;
            }
            return frame.page.fillForm(values);
        }
        // Current state for scripts: {page, current, view, valid, busy, percent, …}
        function state(): string {
            return JSON.stringify({
                page: frame.pageKey,
                current: Wizard.current,
                view: Wizard.view,
                valid: frame.page ? frame.page.valid : false,
                busy: Wizard.busy,
                connected: Engine.connected,
                failure: Engine.failure,
                error: Wizard.stepError,
                fields: Wizard.fieldErrors,
                percent: Wizard.percent,
                status: Wizard.status,
                apps: Wizard.appsDone + "/" + Wizard.appsTotal
            });
        }
        // Step 11: "Try again" / "Skip {App}" (or retry after a core failure).
        function retry(): string {
            if (Wizard.failure)
                Wizard.retryInstall();
            else if (Wizard.attention)
                Wizard.retryModule();
            else
                return "nothing to retry";
            return "ok";
        }
        function skip(): string {
            if (!Wizard.attention)
                return "nothing to skip";
            Wizard.skipModule();
            return "ok";
        }
        function savelog(): string {
            Wizard.saveLog((path, err) => console.log("installer: log", path || err));
            return "ok";
        }
        function help(): string {
            frame.openHelp();
            return "ok";
        }
        // Move keyboard focus like Tab / Shift+Tab (shows the focus ring).
        function tab(forward: bool): string {
            const cur = win.contentItem.Window.activeFocusItem || frame;
            const nextItem = cur.nextItemInFocusChain(forward);
            if (!nextItem)
                return "nothing to focus";
            nextItem.forceActiveFocus(forward ? Qt.TabFocusReason : Qt.BacktabFocusReason);
            return String(nextItem);
        }
        // What has keyboard focus (type + accessible name), for tests.
        function focused(): string {
            const it = win.contentItem.Window.activeFocusItem;
            if (!it)
                return "none";
            return String(it).split("(")[0] + " " + (it.Accessible ? it.Accessible.name : "");
        }
        function theme(name: string): string {
            Theme.dark = name !== "light";
            return Theme.dark ? "dark" : "light";
        }
    }
}
