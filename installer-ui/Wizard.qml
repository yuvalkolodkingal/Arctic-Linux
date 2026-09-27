// Wizard state and navigation. The engine owns the flow (steps, validation,
// defaults); this singleton mirrors it for the UI and turns engine events into
// properties the step pages bind to.
pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

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
    property bool committing: false     // a page is saving its answers before Next
    property var fieldErrors: ({})      // field -> message from the last SetStep/Next
    property string stepError: ""       // general error for the current step
    property string errorStep: ""       // step that owns fieldErrors when it isn't the current one (Summary)
    property string languageName: "English (US)"
    property string layoutName: "English (US)"
    property string keyboardLayout: "us"
    property string keyboardVariant: ""
    // What the engine makes of the choice (keyboard data.xkb: layout, variant, options,
    // latin), when it says: the same goes to the installed system and the live session.
    property var keyboardXkb: null
    // xkb layouts that can't type Latin letters (English (US) is added first, Alt+Shift
    // switches), for engines that don't send xkb. Same list as live/live-keyboard.
    readonly property var nonLatinLayouts: ["af", "am", "ara", "bd", "bg", "bt", "by", "et", "ge", "gr", "il", "in", "iq", "ir", "kg", "kh", "kz", "la", "lk", "mk", "mm", "mn", "mv", "np", "pk", "rs", "ru", "sy", "th", "tj", "ua"]
    readonly property bool keyboardNonLatin: keyboardXkb ? keyboardXkb.latin === false : nonLatinLayouts.indexOf(keyboardLayout) >= 0
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
    property string lastLogMessage: ""  // SaveLog's own sentence, when the engine sends one

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
    // On every (re)connection. The engine replays the install state (progress, modules,
    // attention, failed, done) right after Subscribe answers, so everything shown from
    // events is dropped here: a failure the bridge reported before the engine answered, or
    // one from an earlier connection, must not outlive it.
    function reset() {
        steps = [];
        current = "";
        step = {};
        loading = true;
        busy = false;
        committing = false;
        fieldErrors = {};
        stepError = "";
        errorStep = "";
        resetProgress();
        lastLogPath = "";
        lastLogMessage = "";
    }

    function refresh() {
        Engine.call("GetWizard", null, (res, err) => {
            if (err) {
                stepError = err.message || "";
                return;
            }
            // Summary's Next went through but Start never came (the installer was closed
            // in between): back to Summary, where the install is started.
            if (res && res.current === "install" && Engine.hello.state === "wizard") {
                Engine.call("Back", null, (r, e) => applyWizard(e ? res : r));
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
            errorStep = "";
            step = res;
            current = id;
            loading = false;
            // Back in the wizard (Back / Change after a failed install): the failed run is
            // over. `current` is set first so the install page doesn't flash.
            if ((failure !== null || attention !== null) && railIds.indexOf(id) >= 0 && railIds.indexOf(id) < railIds.indexOf("install"))
                resetProgress();
            if (id === "keyboard" && res.data)
                rememberStep("keyboard", res.data);
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
        if (id === "keyboard" && data.layout)
            setKeyboard(data);
        // A new language can change the suggested layout (when none was picked yet).
        if (id === "welcome")
            syncKeyboard();
    }

    // The engine's keyboard choice, applied to the live session.
    function syncKeyboard() {
        Engine.call("GetStep", {
            id: "keyboard"
        }, (res, err) => {
            if (!err && res && res.data && res.data.layout)
                setKeyboard(res.data);
        });
    }
    function setKeyboard(data) {
        keyboardLayout = data.layout;
        keyboardVariant = data.variant || "";
        keyboardXkb = (data.xkb && data.xkb.layout) ? data.xkb : null;
        applyLiveKeyboard();
    }

    // ---- the live session's keyboard (docs/PLAN.md step 2): the layout picked here is
    // what the disk passphrase and the password are checked with after installing, so the
    // live session types with it too (live/live-keyboard: Mango config include + reload).
    // Only on a real live system; ARCTIC_LIVE_KEYBOARD=<command> overrides it (tests).
    readonly property string liveKeyboardOverride: Quickshell.env("ARCTIC_LIVE_KEYBOARD") || ""
    readonly property bool liveKeyboardEnabled: liveKeyboardOverride !== "" || (!!Engine.hello.live && !Engine.hello.mock)
    property string liveKeyboardApplied: ""
    property bool liveKeyboardPending: false

    // live-keyboard --xkb LAYOUT VARIANT OPTIONS (the engine's xkb), or LAYOUT VARIANT.
    function applyLiveKeyboard() {
        if (!liveKeyboardEnabled || keyboardLayout === "")
            return;
        if (liveKeyboardProc.running) {
            liveKeyboardPending = true;     // runs again with the latest choice when done
            return;
        }
        const x = keyboardXkb;
        const args = x ? ["--xkb", x.layout, x.variant || "", x.options || ""] : [keyboardLayout, keyboardVariant];
        const key = args.join("|");
        if (key === liveKeyboardApplied)
            return;
        liveKeyboardApplied = key;
        const helper = liveKeyboardOverride !== "" ? ["sh", "-c", liveKeyboardOverride + " \"$@\"", "live-keyboard"] : ["/usr/libexec/arctic/live-keyboard"];
        liveKeyboardProc.command = helper.concat(args);
        liveKeyboardProc.running = true;
    }

    Process {
        id: liveKeyboardProc
        stderr: SplitParser {
            onRead: data => console.warn("installer: live-keyboard:", data)
        }
        onExited: exitCode => {
            if (exitCode !== 0)
                wiz.liveKeyboardApplied = "";   // try again with the next change
            if (wiz.liveKeyboardPending) {
                wiz.liveKeyboardPending = false;
                wiz.applyLiveKeyboard();
            }
        }
    }

    // Which step owns a field the engine complained about (for errors on Summary).
    readonly property var fieldSteps: ({
            language: "welcome",
            layout: "keyboard",
            variant: "keyboard",
            network: "network",
            timezone: "timezone",
            disk: "disk",
            mode: "disk",
            passphrase: "encryption",
            full_name: "account",
            username: "account",
            hostname: "account",
            password: "account"
        })
    function stepForField(name) {
        if (fieldSteps[name] !== undefined)
            return fieldSteps[name];
        return "apps";                  // category ids (browser, terminal, …)
    }

    // Field errors show inline (and the footer says "Fix the highlighted field
    // to continue."); anything else shows in the footer. On Summary (no fields of
    // its own) the first message shows instead, and errorStep says where to fix it.
    function showError(err) {
        const fields = (err && err.fields) ? err.fields : {};
        const names = Object.keys(fields);
        fieldErrors = fields;
        errorStep = "";
        if (names.length && (current === "summary" || current === "install")) {
            stepError = fields[names[0]];
            errorStep = stepForField(names[0]);
            return;
        }
        stepError = names.length ? "" : ((err && err.message) ? err.message : "Something went wrong.");
    }

    function clearFieldError(name) {
        if (fieldErrors[name] === undefined)
            return;
        const f = Object.assign({}, fieldErrors);
        delete f[name];
        fieldErrors = f;
    }

    // Next: the page has already committed its data (see Frame.qml goNext).
    function next() {
        committing = false;
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
        if (busy || committing)
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
                if (e) {
                    // Nothing started (for example the disk changed): put the engine back
                    // on Summary, where this page still is, and say why.
                    Engine.call("Back", null, () => {
                        busy = false;
                        showError(e);
                    });
                    return;
                }
                busy = false;
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

    // Core failure: "Try again" starts the install again with the same answers.
    // Progress is cleared before Start: the new run's first events (even an immediate
    // failure) can arrive before Start's answer.
    function retryInstall() {
        const previous = failure;
        busy = true;
        stepError = "";
        resetProgress();
        Engine.call("Start", null, (res, err) => {
            busy = false;
            if (err) {
                if (failure === null)
                    failure = previous;     // still failed: nothing started
                showError(err);
            }
        });
    }

    // Core failure: "Change something" goes back to the Summary (the engine keeps every
    // answer and the secrets), where each Change link opens its step.
    function leaveFailure() {
        busy = true;
        stepError = "";
        Engine.call("Back", null, (res, err) => {
            busy = false;
            if (err) {
                showError(err);
                return;
            }
            applyWizard(res);
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
            lastLogMessage = res.message || "";
            if (done)
                done(lastLogPath, "");
        });
    }

    // done(errorMessage): "" when the restart was accepted.
    function reboot(done) {
        busy = true;
        Engine.call("Reboot", null, (res, err) => {
            busy = false;
            if (done)
                done(err ? (err.message || "Couldn’t restart.") : "");
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
            // Before Hello is answered this is the bridge saying it has no engine
            // (Engine.qml shows that); only an install can fail after that.
            if (Engine.connected)
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
            wiz.liveKeyboardApplied = "";
            wiz.syncKeyboard();
        }
    }
}
