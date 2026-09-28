// Talks to scripts/arctic_settings.py, the helper that does every read and write (so the
// file formats live in one tested place). call(args, done) runs it and hands `done` the JSON
// it printed; a failure also shows its sentence in the toast unless `quiet`.
// `mango` is the helper's `state`: Mango options with their effective value and origin,
// custom shortcuts, startup apps, saved monitor rules; `caps` says which tools exist.
pragma Singleton
pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: backend

    readonly property string helper: Quickshell.shellDir + "/scripts/arctic_settings.py"
    property var mango: ({ options: {}, layouts: [], customBinds: [], startup: [], monitors: [], sourced: true, configExists: true })
    property var caps: ({})
    property bool ready: false
    property int running: 0
    // Changes run one after another in the helper (it holds a lock around each write); answers
    // can still arrive out of order, so only the newest change's answer updates `mango`.
    property int changeSeq: 0
    readonly property bool live: caps.live === true
    // Shown by the window: kind is "success", "error" or "info"; undo offers "Undo".
    signal notify(string kind, string text, bool undo)

    // ---- Mango options ----
    function info(key) {
        return (mango.options && mango.options[key]) || ({ value: "", set: false, overridden: false, origin: "", arctic: "" });
    }
    function opt(key) {
        return info(key).value;
    }
    function num(key) {
        return Number(info(key).value);
    }
    function isOn(key) {
        return info(key).value === "1";
    }
    function arcticNum(key) {
        return Number(info(key).arctic);
    }

    function refresh() {
        call(["state"], r => {
            if (!r.ok)
                return;
            backend.mango = r;
            backend.caps = r.caps || {};
            backend.ready = true;
        });
    }
    // set({gappih: 12, gappiv: 12}, "Gaps changed")
    function set(values, message) {
        const args = [values.cursor_theme !== undefined || values.cursor_size !== undefined ? "set-cursor" : "set"];
        for (const key in values)
            args.push(key + "=" + values[key]);
        change(args, r => backend.notify("success", message || "Saved", true), true);
    }
    function reset(keys, message) {
        change(["reset"].concat(keys), r => backend.notify("success", message || "Back to Arctic’s setting", true));
    }
    function setLayout(name) {
        change(["layout", name || "--reset"], r => backend.notify("success", "Layout changed", true));
    }
    function undo() {
        change(["undo"], r => backend.notify("info", "Undone", false));
    }
    // A change that answers with the whole state: apply it only if no newer change was started
    // meanwhile (that one's answer is the newer state); on failure, re-read the state.
    function change(args, ok, refreshOnError) {
        const seq = ++backend.changeSeq;
        call(args, r => {
            if (!r.ok) {
                if (refreshOnError && seq === backend.changeSeq)
                    backend.refresh();
                return;
            }
            if (seq === backend.changeSeq)
                backend.mango = r;
            ok(r);
        });
    }

    // Open a tool (pavucontrol, blueman-manager …) or a link, detached from Settings.
    function launch(argv) {
        Quickshell.execDetached(argv);
    }
    function openUrl(url) {
        Quickshell.execDetached(["xdg-open", url]);
    }

    function call(args, done, quiet) {
        const proc = runner.createObject(backend, {
            command: ["python3", backend.helper].concat(args),
            done: done || null,
            quiet: !!quiet
        });
        backend.running++;
        proc.running = true;
        return proc;
    }

    Component {
        id: runner
        Process {
            id: proc
            property var done: null
            property bool quiet: false
            property bool handled: false
            stdout: StdioCollector {
                onStreamFinished: proc.finish(text)
            }
            onRunningChanged: if (!running && handled) destroy()
            function finish(text) {
                if (handled)
                    return;
                handled = true;
                backend.running--;
                let result;
                try {
                    result = JSON.parse(text);
                } catch (e) {
                    result = { ok: false, error: "Settings couldn’t read what its helper answered. Please try again." };
                }
                if (!result.ok && !quiet)
                    backend.notify("error", result.error || "That didn’t work.", false);
                if (done)
                    done(result);
                if (!running)
                    destroy();
            }
        }
    }

    Component.onCompleted: refresh()
}
