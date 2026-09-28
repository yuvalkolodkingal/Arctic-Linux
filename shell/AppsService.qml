pragma Singleton
pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io
import "PackageSearch.js" as PackageSearch
import "getapps/GetApps.js" as GetAppsLogic

// Get apps' state, kept for the shell's lifetime so installs outlive the launcher
// (getapps/GetApps.qml is the page router; see scripts/apps.py and install-terminal.py):
//   runner  scripts/install-terminal.py   one PTY, one job at a time: the pages' installs and
//                                         removals (queued here) and the Console's commands
//   index   scripts/package-index.py      names and summaries of every package and Flathub app
//   helper  scripts/apps.py               read-only questions, one JSON line each, as you
//   web     WebAppClient                  arctic-webapp serve, for web apps (only when present)
// Pages never build command lines: they queue {kind, source, ids} jobs, and the runner makes
// the commands itself. A job that ends while Get apps isn't on screen sends a notification.
Singleton {
    id: service

    // ---- jobs -----------------------------------------------------------------------------
    property var jobs: []                          // {id, kind, source, ids, name, icon, desktop, phase, percent, step, code, message}
    readonly property var job: jobs.find(j => j.phase === 'running') || null
    readonly property bool busy: consoleRunning || jobs.some(j => j.phase === 'running' || j.phase === 'waiting')
    readonly property string currentLabel: job ? GetAppsLogic.jobLabel(job) : consoleRunning ? 'Running a Console command' : ''
    property bool watching: false                  // the launcher shows Get apps (set by Launcher.qml)
    property bool polkitActive: false              // the password dialog is up (set by shell.qml)
    property int nextJob: 1
    signal jobFinished(var job)

    // ---- what the pages show ----------------------------------------------------------------
    property var sources: ({})
    property bool sourcesLoaded: false
    readonly property bool live: Session.live
    readonly property string webappCmd: Quickshell.env('ARCTIC_WEBAPP_CMD') || 'arctic-webapp'
    readonly property bool webappPresent: sourcesLoaded && !!(sources.webapp && sources.webapp.present)
    readonly property WebAppClient web: webClient
    property var packages: []                      // Console completion (names + 'flathub:' ids)
    property var packageIndex: PackageSearch.prepare([])
    property var flathubList: []                   // [{id, name, summary}] from the index (no icons)
    property var fedoraPackages: []                // [{id, name, repo, summary}] every available package
    property var dnfNames: ({})                    // {name: true} of fedoraPackages
    property int dnfNamesCount: 0
    property var flathubCatalog: []                // AppStream apps: names, summaries, icons
    property var fedoraApps: []
    property bool flathubCatalogMissing: false
    property bool fedoraCatalogMissing: false
    readonly property var flathubItems: flathubCatalog.length ? flathubCatalog : flathubList
    property var installedIds: ({ flatpak: {}, dnf: {} })   // {flatpak: {id: installation}, dnf: {name: true}}
    property var featured: []                      // Arctic picks (assets/featured.json)
    property string indexError: ''
    property bool indexRefreshing: false
    property bool indexLoaded: false

    // ---- the Console --------------------------------------------------------------------------
    property string consoleOutput: ''
    property string consoleNotice: ''
    property bool consoleRunning: false
    property bool consoleSecret: false
    property bool consoleSubmitting: false
    property bool transcript: false                // the Console or a job's details are on screen

    function ensureStarted() {
        if (!runner.running) runner.running = true;
        if (!indexLoaded && !index.running) { index.command = ['python3', Session.scripts + '/package-index.py', '--details']; index.running = true; }
        refreshSources();
        refreshInstalledIds();
        if (!flathubCatalog.length) loadCatalog('flathub');
        if (!fedoraApps.length) loadCatalog('fedora');
        dropTimer.stop();
    }
    function refreshIndex(force) {
        if (index.running) return;
        indexError = '';
        index.command = ['python3', Session.scripts + '/package-index.py', '--details'].concat(force ? ['--force'] : []);
        index.running = true;
    }
    function refreshSources() { helper(['sources'], r => { if (r.ok) { service.sources = r; service.sourcesLoaded = true; } }); }
    function refreshInstalledIds() {
        helper(['installed-ids'], r => {
            if (!r.ok) return;
            const flatpak = {}, dnf = {};
            (r.flatpak.system || []).forEach(id => flatpak[id] = 'system');
            (r.flatpak.user || []).forEach(id => { if (!flatpak[id]) flatpak[id] = 'user'; });
            (r.dnf || []).forEach(n => dnf[n] = true);
            service.installedIds = { flatpak: flatpak, dnf: dnf };
        });
    }
    function loadCatalog(source) {
        helper(['catalog', source], r => {
            if (!r.ok) return;
            if (source === 'flathub') { service.flathubCatalog = r.items; service.flathubCatalogMissing = !!r.missing; }
            else { service.fedoraApps = r.items; service.fedoraCatalogMissing = !!r.missing; }
        });
    }

    // ---- queueing jobs ------------------------------------------------------------------------
    // extra: {name, icon, desktop, installation, autoremove, delete_data, unused}
    function queue(kind, source, ids, extra) {
        const job = Object.assign({ id: 'j' + nextJob++, kind: kind, source: source, ids: ids || [], name: '', icon: '',
                                    desktop: '', phase: 'waiting', percent: null, step: '', code: 0, message: '', finishedAt: 0 },
                                  extra || {});
        jobs = jobs.concat([job]).slice(-20);
        pump();
        return job.id;
    }
    function install(source, ids, extra) {
        const e = Object.assign({}, extra || {});
        if (source === 'flatpak') {
            e.installation = sources.flatpak ? sources.flatpak.install_to : 'system';
            e.remote = 'flathub';
        }
        return queue('install', source, ids, e);
    }
    function remove(source, ids, extra) { return queue('remove', source, ids, extra); }
    function addFlathub() {
        return queue('add-remote', 'flatpak', [], { remote: 'flathub', installation: sources.flatpak ? sources.flatpak.install_to : 'system', name: 'Flathub' });
    }
    function cancel(jobId) {
        const job = jobs.find(j => j.id === jobId);
        if (!job) return;
        if (job.phase === 'waiting') update(jobId, { phase: 'cancelled', finishedAt: Date.now() });
        else if (job.phase === 'running') { update(jobId, { stopping: true }); send({ action: 'interrupt' }); }
    }
    function update(jobId, fields) {
        jobs = jobs.map(j => j.id === jobId ? Object.assign({}, j, fields) : j);
    }
    function pump() {
        if (!runner.running) { runner.running = true; return; }
        if (job || consoleRunning) return;
        const next = jobs.find(j => j.phase === 'waiting');
        if (!next) return;
        update(next.id, { phase: 'running', step: '' });
        const request = { id: next.id, kind: next.kind, source: next.source, ids: next.ids, name: next.name };
        ['installation', 'remote', 'autoremove', 'delete_data', 'unused'].forEach(k => { if (next[k] !== undefined) request[k] = next[k]; });
        send({ action: 'run', job: request });
    }
    function send(request) {
        if (!runner.running) return;
        runner.write(JSON.stringify(request) + '\n');
    }
    function consoleSend(action, text) {
        if (!runner.running) return;
        if (action === 'start') consoleSubmitting = true;
        send({ action: action, text: text || '', secret: consoleSecret });
    }
    function finish(done) {
        const job = jobs.find(j => j.id === done.id);
        if (!job) return;
        const phase = done.ok ? 'done' : job.stopping ? 'cancelled' : 'failed';
        update(done.id, { phase: phase, code: done.code, message: done.message || '', percent: done.ok ? 100 : job.percent, finishedAt: Date.now() });
        const ended = jobs.find(j => j.id === done.id);
        refreshInstalledIds();
        if (job.kind === 'add-remote' && done.ok) { refreshSources(); refreshIndex(true); loadCatalog('flathub'); }
        jobFinished(ended);
        if (!watching) notify(ended);
    }
    onTranscriptChanged: send({ action: 'transcript', on: transcript })
    onConsoleRunningChanged: if (!consoleRunning) Qt.callLater(pump)

    // ---- notifications ------------------------------------------------------------------------
    function notify(job) {
        if (!job || job.kind === 'console') return;
        const name = job.name || job.ids.join(', ');
        let argv;
        if (job.phase === 'done' && job.kind === 'install')
            argv = ['notify-send', '-a', 'Arctic Linux', '-i', job.icon || 'system-software-install']
                   .concat(job.desktop ? ['-A', 'open=Open'] : [])
                   .concat([name + ' is installed', 'It’s in the launcher (Super + Space).']);
        else if (job.phase === 'done' && job.kind === 'remove')
            argv = ['notify-send', '-a', 'Arctic Linux', '-i', job.icon || 'user-trash', name + ' was removed', ''];
        else if (job.phase === 'failed')
            argv = ['notify-send', '-a', 'Arctic Linux', '-i', 'dialog-warning', '-A', 'details=Show details',
                    job.kind === 'remove' ? name + ' wasn’t removed' : name + ' wasn’t installed', job.message];
        else return;
        notifier.createObject(service, { command: argv, job: job }).running = true;
    }
    signal detailsRequested(var job)
    Component {
        id: notifier
        Process {
            id: note
            property var job: null
            stdout: StdioCollector {
                onStreamFinished: {
                    const action = text.trim();
                    if (action === 'open' && note.job.desktop) {
                        const entry = DesktopEntries.byId(note.job.desktop);
                        if (entry) entry.execute();
                    } else if (action === 'details') {
                        service.detailsRequested(note.job);
                    }
                }
            }
            onRunningChanged: if (!running) destroy()
        }
    }

    // ---- apps.py --------------------------------------------------------------------------
    // helper(['installed', 'dnf'], result => …): one JSON line, {ok: false, error} on failure.
    function helper(args, done) {
        const proc = helperRun.createObject(service, { command: ['python3', Session.scripts + '/apps.py'].concat(args), done: done || null });
        proc.running = true;
        return proc;
    }
    Component {
        id: helperRun
        Process {
            id: proc
            property var done: null
            property bool handled: false
            environment: ({ ARCTIC_WEBAPP_CMD: service.webappCmd })
            stdout: StdioCollector { onStreamFinished: proc.finish(text) }
            onRunningChanged: if (!running && handled) destroy()
            function finish(text) {
                if (handled) return;
                handled = true;
                let result;
                try { result = JSON.parse(text.trim().split('\n').pop()); }
                catch (e) { result = { ok: false, error: 'Get apps couldn’t read what its helper answered. Try again.' }; }
                if (done) done(result);
                if (!running) destroy();
            }
        }
    }

    // ---- processes ------------------------------------------------------------------------
    Process {
        id: index
        command: ['python3', Session.scripts + '/package-index.py', '--details']
        stdout: SplitParser {
            onRead: data => {
                try {
                    const result = JSON.parse(data);
                    if (result.packages.length || !service.packages.length) {
                        service.packages = result.packages;
                        service.packageIndex = PackageSearch.prepare(result.packages);
                        const details = result.details || { dnf: [], flathub: [] };
                        service.fedoraPackages = details.dnf.map(r => ({ id: r[0], name: r[0], repo: r[1], summary: r[2] }));
                        const names = {};
                        details.dnf.forEach(r => names[r[0]] = true);
                        service.dnfNames = names;
                        service.dnfNamesCount = details.dnf.length;
                        service.flathubList = details.flathub.map(r => ({ id: r[0], name: r[1] || r[0], summary: r[2], icon: '' }));
                    }
                    service.indexRefreshing = result.refreshing;
                    service.indexError = result.error || '';
                    service.indexLoaded = true;
                } catch (e) { service.indexError = 'Could not read the package list.'; }
            }
        }
        onExited: {
            service.indexRefreshing = false;
            // A refreshed index can change what the Fedora catalogue keeps.
            service.loadCatalog('fedora');
        }
    }
    Process {
        id: runner
        command: ['python3', Session.scripts + '/install-terminal.py']
        stdinEnabled: true
        onRunningChanged: if (running) { service.send({ action: 'transcript', on: service.transcript }); Qt.callLater(service.pump); }
        stdout: SplitParser {
            onRead: data => {
                let state;
                try { state = JSON.parse(data); } catch (e) { service.consoleNotice = 'Could not read terminal output.'; return; }
                service.consoleSubmitting = false;
                if (state.output !== undefined) service.consoleOutput = state.output;
                service.consoleSecret = state.secret;
                service.consoleNotice = state.notice;
                const j = state.job;
                if (j && j.kind !== 'console') {
                    const step = service.polkitActive ? 'Waiting for your password' : j.step;
                    service.update(j.id, { percent: j.percent, step: step });
                }
                if (state.finished && state.finished.id) service.finish(state.finished);
                service.consoleRunning = !!(j && j.kind === 'console');
                if (!state.running) Qt.callLater(service.pump);
            }
        }
        onExited: {
            service.consoleRunning = false;
            service.consoleSecret = false;
            service.consoleSubmitting = false;
            service.consoleNotice = 'The console stopped. It starts again the next time you open it.';
            const lost = service.jobs.find(j => j.phase === 'running');
            if (lost) service.update(lost.id, { phase: 'failed', code: -1, finishedAt: Date.now(),
                                                message: 'Get apps stopped unexpectedly. Nothing else changed; try again.' });
            if (service.jobs.some(j => j.phase === 'waiting')) restart.start();
        }
    }
    Timer { id: restart; interval: 500; onTriggered: service.pump() }
    WebAppClient { id: webClient; command: service.webappCmd }
    FileView {
        path: Quickshell.shellDir + '/assets/featured.json'
        printErrors: false
        onLoaded: { try { service.featured = JSON.parse(text()).apps || []; } catch (e) { service.featured = []; } }
    }
    onPolkitActiveChanged: if (job) update(job.id, { step: polkitActive ? 'Waiting for your password' : job.step === 'Waiting for your password' ? '' : job.step })

    // The large lists go 5 minutes after the launcher closes, unless a job runs; the next
    // Get apps loads them again.
    onWatchingChanged: if (watching) dropTimer.stop(); else dropTimer.restart()
    Timer {
        id: dropTimer
        interval: 5 * 60 * 1000
        onTriggered: {
            if (service.busy || service.watching) return;
            service.fedoraPackages = [];
            service.dnfNames = {};
            service.dnfNamesCount = 0;
            service.flathubList = [];
            service.flathubCatalog = [];
            service.fedoraApps = [];
            service.packages = [];
            service.packageIndex = PackageSearch.prepare([]);
            service.indexLoaded = false;
            webClient.stop();
        }
    }
}
