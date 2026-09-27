// Wizard state and navigation. The engine owns the flow (steps, validation,
// defaults); this singleton mirrors it for the UI and turns engine events into
// properties the step pages bind to.
pragma Singleton
import QtQuick
import Quickshell

Singleton {
    id: wiz

    // ---- rail (design STEP_NAMES; the engine's own titles are the page titles)
    readonly property var railIds: ["welcome", "keyboard", "network", "timezone", "disk", "encryption", "account", "apps", "summary", "install"]
    readonly property var railNames: ["Welcome", "Keyboard", "Network", "Time zone", "Disk", "Encryption", "Account", "Apps", "Summary", "Install"]

    property var steps: []              // GetWizard.steps
    property string current: ""         // engine's current step id
    property var step: ({})             // GetStep result for `current`
    property bool loading: true         // waiting for the first GetStep
    property bool busy: false           // a navigation request is in flight
    property var fieldErrors: ({})      // field -> message from the last SetStep/Next
    property string stepError: ""       // general error for the current step
    property string languageName: "English (US)"
    property string layoutName: "English (US)"
    property bool encryptionEnabled: true
    property string selectedDiskLabel: ""
    property string alongsideOs: ""

    // ---- install progress (events)
    property real percent: 0
    property string phase: ""
    property string status: ""
    property int etaSeconds: -1
    property var substeps: []
    property var modules: ({})          // id -> {id, name, status, percent}
    property var moduleOrder: []
    property var attention: null        // attention event while paused
    property var failure: null          // failed event (core failure)
    property var doneInfo: null         // done event
    property string lastLogPath: ""

    // "step" normally; "attention" / "failed" replace the Install page (step 11).
    readonly property string view: failure ? "failed" : (attention ? "attention" : "step")
    readonly property int railIndex: {
        if (current === "done")
            return railIds.length;          // every step done
        const i = railIds.indexOf(current);
        return i < 0 ? 0 : i;
    }
    readonly property bool railError: view !== "step"
    readonly property int appsTotal: moduleOrder.length
    readonly property int appsDone: {
        let n = 0;
        for (const id of moduleOrder) {
            const s = (modules[id] || {}).status;
            if (s === "installed" || s === "skipped" || s === "deferred")
                n++;
        }
        return n;
    }
    readonly property int appsInstalled: {
        let n = 0;
        for (const id of moduleOrder)
            if ((modules[id] || {}).status === "installed")
                n++;
        return n;
    }
    readonly property var deferredApps: {
        const out = [];
        for (const id of moduleOrder) {
            const m = modules[id] || {};
            if (m.status === "skipped" || m.status === "deferred")
                out.push(m.name || id);
        }
        return out;
    }

    signal stepLoaded(string id)
    signal navigated(string from, string to)
    signal notify(string message)

    function railName(id) {
        const i = railIds.indexOf(id);
        return i < 0 ? id : railNames[i];
    }
    function stepTitle(id) {
        for (const s of steps)
            if (s.id === id)
                return s.title;
        return "";
    }

    // ---- lifecycle
    function reset() {
        steps = [];
        current = "";
        step = {};
        loading = true;
        busy = false;
        fieldErrors = {};
        stepError = "";
    }

    function refresh() {
        Engine.call("GetWizard", null, (res, err) => {
            if (err) {
                stepError = err.message || "";
                return;
            }
            applyWizard(res);
        });
    }

    function applyWizard(res) {
        if (!res)
            return;
        steps = res.steps || [];
        const target = res.current || (steps.length ? steps[0].id : "welcome");
        if (target !== current || loading)
            loadStep(target);
    }

    // Fetch the step's data/options first so pages are created fully populated.
    function loadStep(id) {
        busy = true;
        Engine.call("GetStep", {
            id: id
        }, (res, err) => {
            busy = false;
            if (err) {
                // install/done may have no GetStep data on the real engine.
                res = {
                    id: id,
                    title: stepTitle(id),
                    help: "",
                    data: {},
                    options: {}
                };
            }
            const from = current;
            fieldErrors = {};
            stepError = "";
            step = res;
            current = id;
            loading = false;
            stepLoaded(id);
            navigated(from, id);
        });
    }

    // Save a step's data. done(ok) is called after the engine answered.
    function saveStep(id, data, done) {
        Engine.call("SetStep", {
            id: id,
            data: data
        }, (res, err) => {
            if (err) {
                showError(err);
                if (done)
                    done(false);
                return;
            }
            rememberStep(id, (res && res.data) ? res.data : data);
            if (done)
                done(true);
        });
    }

    // Values the rail/summary/done pages show outside their own step.
    function rememberStep(id, data) {
        if (!data)
            return;
        if (id === "encryption" && data.enabled !== undefined)
            encryptionEnabled = !!data.enabled;
    }

    // Field errors show inline (and the footer says "Fix the highlighted field
    // to continue."); anything else shows in the footer.
    function showError(err) {
        const fields = (err && err.fields) ? err.fields : {};
        fieldErrors = fields;
        stepError = Object.keys(fields).length ? "" : ((err && err.message) ? err.message : "Something went wrong.");
    }

    function clearFieldError(name) {
        if (fieldErrors[name] === undefined)
            return;
        const f = Object.assign({}, fieldErrors);
        delete f[name];
        fieldErrors = f;
    }

    // Next: the page has already committed its data (see shell.qml goNext).
    function next() {
        busy = true;
        Engine.call("Next", null, (res, err) => {
            busy = false;
            if (err) {
                showError(err);
                return;
            }
            applyWizard(res);
        });
    }

    function back() {
        if (current === "install" || current === "done" || current === railIds[0])
            return;
        busy = true;
        Engine.call("Back", null, (res, err) => {
            busy = false;
            if (err) {
                showError(err);
                return;
            }
            applyWizard(res);
        });
    }

    function gotoStep(id) {
        busy = true;
        Engine.call("Goto", {
            id: id
        }, (res, err) => {
            busy = false;
            if (err) {
                showError(err);
                return;
            }
            applyWizard(res);
        });
    }

    // Summary → Install: move to the install step, then start.
    function startInstall() {
        busy = true;
        resetProgress();
        Engine.call("Next", null, (res, err) => {
            if (err) {
                busy = false;
                showError(err);
                return;
            }
            Engine.call("Start", null, (r, e) => {
                busy = false;
                if (e) {
                    showError(e);
                    return;
                }
                applyWizard(res);
                if ((res && res.current) !== "install")
                    loadStep("install");
            });
        });
    }

    function resetProgress() {
        percent = 0;
        phase = "";
        status = "Preparing the disk…";
        etaSeconds = -1;
        substeps = [];
        modules = {};
        moduleOrder = [];
        attention = null;
        failure = null;
        doneInfo = null;
    }

    function retryModule() {
        if (!attention)
            return;
        const id = attention.module ? attention.module.id : "";
        busy = true;
        Engine.call("RetryModule", {
            id: id
        }, (res, err) => {
            busy = false;
            if (err) {
                showError(err);
                return;
            }
            attention = null;
        });
    }

    function skipModule() {
        if (!attention)
            return;
        const id = attention.module ? attention.module.id : "";
        busy = true;
        Engine.call("SkipModule", {
            id: id
        }, (res, err) => {
            busy = false;
            if (err) {
                showError(err);
                return;
            }
            attention = null;
        });
    }

    // Core failure: "Try again" starts the install again.
    function retryInstall() {
        busy = true;
        Engine.call("Start", null, (res, err) => {
            busy = false;
            if (err) {
                showError(err);
                return;
            }
            failure = null;
        });
    }

    function saveLog(done) {
        Engine.call("SaveLog", null, (res, err) => {
            if (err) {
                if (done)
                    done("", err.message || "");
                return;
            }
            lastLogPath = res.path || "";
            if (done)
                done(lastLogPath, "");
        });
    }

    function reboot() {
        busy = true;
        Engine.call("Reboot", null, (res, err) => {
            busy = false;
            if (err)
                notify(err.message || "Couldn't restart. Restart from the power menu.");
        });
    }

    // ---- events
    function onEngineEvent(ev) {
        switch (ev.event) {
        case "progress":
            if (ev.percent !== undefined)
                percent = ev.percent;
            if (ev.phase !== undefined)
                phase = ev.phase;
            if (ev.status)
                status = ev.status;
            if (ev.eta_seconds !== undefined)
                etaSeconds = ev.eta_seconds;
            if (ev.substeps)
                substeps = ev.substeps;
            if (current !== "install" && current !== "done" && !busy)
                loadStep("install");
            break;
        case "module":
            {
                const m = Object.assign({}, modules);
                m[ev.id] = {
                    id: ev.id,
                    name: ev.name || ev.id,
                    status: ev.status,
                    percent: ev.percent || 0
                };
                if (moduleOrder.indexOf(ev.id) < 0)
                    moduleOrder = moduleOrder.concat([ev.id]);
                modules = m;
                break;
            }
        case "attention":
            attention = ev;
            break;
        case "failed":
            failure = ev;
            break;
        case "done":
            doneInfo = ev;
            attention = null;
            failure = null;
            percent = 100;
            loadStep("done");
            break;
        default:
            break;
        }
    }

    Connections {
        target: Engine
        function onEvent(ev) {
            wiz.onEngineEvent(ev);
        }
        function onReady() {
            wiz.reset();
            wiz.refresh();
        }
    }
}
