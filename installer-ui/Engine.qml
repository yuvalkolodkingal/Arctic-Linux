// Connection to the installer engine (docs/BUILD-SPEC.md §4).
// Runs `arctic-install bridge` and speaks newline-delimited JSON over its
// stdin/stdout: requests carry an id, responses answer that id, events have none.
//   ARCTIC_INSTALLER_BRIDGE="cmd …"   run this instead (e.g. dev/mock-bridge.py)
//   ARCTIC_INSTALLER_MOCK=1           append --mock (in-process mock engine)
pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: engine

    readonly property string clientVersion: "0.2.1"
    property bool connected: false      // Hello answered
    property bool starting: false
    property string failure: ""         // why the bridge is not usable
    property var hello: ({})
    property int nextId: 1
    property var pending: ({})          // id -> callback(result, error)
    property string stderrTail: ""
    property string bridgeMessage: ""   // the bridge's own "no engine" message ({"event":"failed"} before Hello)

    // Every event line ({"event": …}) is re-emitted here.
    signal event(var ev)
    // The bridge answered Hello and Subscribe.
    signal ready()
    signal lost(string reason)

    readonly property string bridgeOverride: Quickshell.env("ARCTIC_INSTALLER_BRIDGE") || ""
    readonly property bool mockRequested: Quickshell.env("ARCTIC_INSTALLER_MOCK") === "1"
    readonly property var bridgeCommand: {
        if (bridgeOverride !== "")
            return ["sh", "-c", "exec " + bridgeOverride];
        const cmd = ["arctic-install", "bridge"];
        const sock = Quickshell.env("ARCTIC_INSTALLER_SOCKET") || "";
        if (sock !== "")
            cmd.push("--socket", sock);
        if (mockRequested)
            cmd.push("--mock");
        return cmd;
    }

    // call("GetStep", {id: "disk"}, (result, error) => …). error = {code, message, fields?}
    function call(method, params, callback) {
        if (!proc.running) {
            if (callback)
                callback(null, {
                    code: "disconnected",
                    message: "The installer engine isn't running."
                });
            return -1;
        }
        const id = engine.nextId++;
        const msg = {
            id: id,
            method: method
        };
        if (params !== undefined && params !== null)
            msg.params = params;
        if (callback)
            engine.pending[id] = callback;
        proc.write(JSON.stringify(msg) + "\n");
        return id;
    }

    function start() {
        if (proc.running)
            return;
        engine.failure = "";
        engine.bridgeMessage = "";
        engine.connected = false;
        engine.starting = true;
        engine.pending = {};
        proc.running = true;
        helloTimeout.restart();
    }

    function restart() {
        if (proc.running) {
            restartTimer.pendingRestart = true;
            proc.running = false;
        } else {
            start();
        }
    }

    function handleLine(line) {
        const text = line.trim();
        if (text === "")
            return;
        let msg;
        try {
            msg = JSON.parse(text);
        } catch (e) {
            console.warn("installer: bridge sent a line that isn't JSON:", text.slice(0, 200));
            return;
        }
        if (msg.event !== undefined) {
            // `arctic-install bridge` prints a failed event when it can't reach arcticd
            // (and the details on stderr); before Hello is answered that is about the
            // engine, not an install. Shown when the bridge exits.
            if (msg.event === "failed" && !engine.connected) {
                engine.bridgeMessage = msg.message || "";
                return;
            }
            engine.event(msg);
            return;
        }
        if (msg.id === undefined || msg.id === null)
            return;
        const cb = engine.pending[msg.id];
        delete engine.pending[msg.id];
        if (!cb)
            return;
        try {
            if (msg.error)
                cb(null, msg.error);
            else
                cb(msg.result === undefined ? {} : msg.result, null);
        } catch (e) {
            console.warn("installer: callback for request", msg.id, "failed:", e, e.stack || "");
        }
    }

    function failAll(reason) {
        const p = engine.pending;
        engine.pending = {};
        for (const id in p) {
            try {
                p[id](null, {
                    code: "disconnected",
                    message: reason
                });
            } catch (e) {}
        }
    }

    Process {
        id: proc
        command: engine.bridgeCommand
        stdinEnabled: true
        stdout: SplitParser {
            splitMarker: "\n"
            onRead: data => engine.handleLine(data)
        }
        stderr: SplitParser {
            splitMarker: "\n"
            onRead: data => {
                console.log("arctic-install bridge:", data);
                engine.stderrTail = (engine.stderrTail + "\n" + data).slice(-2000);
            }
        }
        onStarted: {
            engine.call("Hello", {
                client: "installer-ui",
                version: engine.clientVersion
            }, (result, error) => {
                if (error) {
                    engine.starting = false;
                    engine.failure = error.message || "The installer engine didn't answer.";
                    engine.lost(engine.failure);
                    return;
                }
                engine.hello = result;
                engine.call("Subscribe", {}, (r, e) => {
                    engine.starting = false;
                    if (e) {
                        engine.failure = e.message || "Couldn't follow the installer engine.";
                        engine.lost(engine.failure);
                        return;
                    }
                    engine.connected = true;
                    helloTimeout.stop();
                    engine.ready();
                });
            });
        }
        onExited: exitCode => {
            helloTimeout.stop();
            engine.connected = false;
            engine.starting = false;
            engine.failure = engine.bridgeMessage || ("The installer engine stopped (exit code " + exitCode + ").");
            engine.failAll(engine.failure);
            console.warn("installer:", engine.failure, engine.stderrTail);
            if (restartTimer.pendingRestart) {
                restartTimer.pendingRestart = false;
                restartTimer.start();
            } else {
                engine.lost(engine.failure);
            }
        }
    }

    // A bridge that never answers Hello (wrong binary, daemon down) must not
    // leave the person looking at a blank window.
    Timer {
        id: helloTimeout
        interval: 15000
        onTriggered: {
            if (engine.connected)
                return;
            engine.starting = false;
            engine.failure = proc.running ? "The installer engine didn't answer." : "The installer engine couldn't be started.";
            engine.failAll(engine.failure);
            engine.lost(engine.failure);
        }
    }

    Timer {
        id: restartTimer
        property bool pendingRestart: false
        interval: 150
        onTriggered: engine.start()
    }
}
