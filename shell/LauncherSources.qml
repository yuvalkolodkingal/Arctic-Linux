import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import "LauncherSearch.js" as LauncherSearch

// What the launcher finds besides apps (LauncherSearch.js does the ranking): Settings pages and
// single settings, open windows, apps' own actions ("New private window"), files in your home
// folder (fd-find), unit conversions (qalc from qalculate) and a web search. It also
// remembers what you open, so that ranks higher next time (~/.local/state/arctic/launcher.json).
// fd and qalc are optional: without them there are no file rows and "=" stays arithmetic.
Item {
    id: sources
    property bool active: false         // the launcher is open
    property string text: ''            // what is typed (plain search)
    property string calc: ''            // an "=" expression the built-in calculator can't do
    property var apps: []               // the launcher's DesktopEntry list
    property var stats: ({})
    property real now: Date.now()
    property bool hasFd: false
    property bool hasQalc: false
    property var files: []
    property string filesFor: ''
    property string qalcFor: ''
    property string qalcResult: ''
    readonly property string stateDir: (Quickshell.env('XDG_STATE_HOME') || Session.home + '/.local/state') + '/arctic'
    // shell.json "webSearch": duckduckgo (default), startpage, brave, ecosia, google, bing or
    // an https:// address with %s.
    readonly property string engine: Session.settings.webSearch || 'duckduckgo'

    readonly property var settingsRows: active ? LauncherSearch.settingsCandidates(SettingsIndex.pages, SettingsIndex.entries) : []
    readonly property var windowRows: active ? LauncherSearch.windowCandidates(ToplevelManager.toplevels.values.map(t => {
        const entry = t.appId ? DesktopEntries.heuristicLookup(t.appId) : null;
        return { title: t.title, appId: t.appId, appName: entry ? entry.name : '', icon: entry ? entry.icon : '', ref: t };
    })) : []
    readonly property var actionRows: {
        if (!active) return [];
        const out = [];
        apps.forEach(a => (a.entry.actions || []).forEach(action => out.push({
            kind: 'action', action: action, name: action.name, desc: a.name, keywords: '', tile: a.tile, icon: action.icon || a.icon,
            glyph: 'arrow-right', bias: -200, fuzzy: false, id: 'action:' + a.entry.id + '/' + action.id })));
        return out;
    }
    // Candidates ranked together with the apps.
    readonly property var extra: settingsRows.concat(windowRows).concat(actionRows)

    function boost(item) { return item.id ? LauncherSearch.frecency(stats, item.id, now) : 0; }
    function remember(id) {
        if (!id) return;
        stats = LauncherSearch.remember(stats, id, Date.now());
        statsFile.setText(JSON.stringify(stats));
    }
    // Rows after the ranked ones: files for this text, then the web search.
    function tail(query) {
        const out = filesFor === query ? files.slice() : [];
        const web = LauncherSearch.webSearch(engine, query);
        if (web) out.push(web);
        return out;
    }
    function webRow(query) { return LauncherSearch.webSearch(engine, query); }
    // A qalc answer for this expression, or null.
    function qalcRow(expr) {
        if (!expr || qalcFor !== expr || !qalcResult) return null;
        return { kind: 'calc', name: qalcResult, desc: '= ' + expr + ' · Enter copies the result', glyph: 'hash' };
    }

    onActiveChanged: if (active) now = Date.now()
    onTextChanged: { if (text.length >= 3 && hasFd) fileTimer.restart(); if (LauncherSearch.looksLikeConversion(text)) qalcTimer.restart(); }
    onCalcChanged: if (calc) qalcTimer.restart()

    Process {
        command: ['sh', '-c', 'for c in fd qalc; do command -v "$c" >/dev/null 2>&1 && echo "$c"; done; mkdir -p "$1"', 'sh', sources.stateDir]
        running: true
        stdout: StdioCollector {
            onStreamFinished: {
                sources.hasFd = /^fd$/m.test(text);
                sources.hasQalc = /^qalc$/m.test(text);
            }
        }
    }
    FileView {
        id: statsFile
        path: sources.stateDir + '/launcher.json'
        printErrors: false
        onLoaded: {
            try { sources.stats = JSON.parse(text()) || {}; } catch (e) { sources.stats = {}; }
        }
    }

    // fd, one at a time: a search typed while one runs starts when it ends.
    property string fdWanted: ''
    property string fdRunning: ''
    Timer { id: fileTimer; interval: 180; onTriggered: sources.findFiles(sources.text) }
    function findFiles(query) {
        fdWanted = query;
        if (fd.running || query.length < 3) return;
        fdRunning = query;
        fd.command = ['timeout', '3', 'fd', '--fixed-strings', '--ignore-case', '--absolute-path', '--max-results', '6',
                      '--type', 'f', '--type', 'd', '--', query, Session.home];
        fd.running = true;
    }
    Process {
        id: fd
        stdout: StdioCollector {
            onStreamFinished: {
                sources.files = LauncherSearch.fileRows(text, Session.home);
                sources.filesFor = sources.fdRunning;
            }
        }
        onExited: if (sources.fdWanted !== sources.fdRunning && sources.fdWanted === sources.text) Qt.callLater(() => sources.findFiles(sources.fdWanted))
    }

    // qalc the same way, for "=" expressions and "10 km to mi".
    property string qalcWanted: ''
    property string qalcRunning: ''
    Timer {
        id: qalcTimer
        interval: 150
        onTriggered: sources.convert(sources.calc || (LauncherSearch.looksLikeConversion(sources.text) ? sources.text : ''))
    }
    function convert(expr) {
        qalcWanted = expr;
        if (qalc.running || !expr || !hasQalc || /^\s*-/.test(expr)) return;
        qalcRunning = expr;
        qalc.command = ['timeout', '3', 'qalc', '-t', expr];
        qalc.running = true;
    }
    Process {
        id: qalc
        stdout: StdioCollector {
            onStreamFinished: {
                const answer = text.trim().split('\n').pop() || '';
                // Only a real answer: a number, not the question given back.
                const ok = /\d/.test(answer) && answer !== sources.qalcRunning.trim() && !/error|warning/i.test(answer);
                sources.qalcResult = ok ? answer : '';
                sources.qalcFor = sources.qalcRunning;
            }
        }
        onExited: if (sources.qalcWanted && sources.qalcWanted !== sources.qalcRunning) Qt.callLater(() => sources.convert(sources.qalcWanted))
    }
}
