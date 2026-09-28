import QtQuick
import Quickshell.Io

// The shell's side of `arctic-webapp serve` (the web-app engine, arctic-webapps): JSON lines,
// {id, method, params} out, {id, result} or {id, error: {code, message, fields}} back, and
// events told apart by their "event" key (progress while inspecting or installing, changed when
// apps come and go). One process, started when Get apps' web pages or a web-app Delete need it,
// stopped when Get apps has been closed for a while (stdin closes; serve exits on EOF).
// Replies go to the callback given with the request: done(result, error).
Item {
    id: client
    property string command: 'arctic-webapp'
    property bool ready: false                     // Hello answered
    property var runtimes: []
    property var apps: []                          // List: app info objects
    property var kept: []                          // List: sign-in data kept after a removal
    property bool listed: false
    property string error: ''
    property int nextId: 1
    property var pending: ({})
    signal progress(int request, string stage, string message)
    signal changed(var ids)

    function start() {
        if (process.running) return;
        error = '';
        process.running = true;
        call('Hello', {}, (result, err) => {
            if (result) { client.runtimes = result.runtimes || []; client.ready = true; client.list(); }
            else client.error = err.message;
        });
    }
    function stop() { if (process.running) process.running = false; }
    function call(method, params, done) {
        if (!process.running) start();
        const id = nextId++;
        const table = pending;
        table[id] = done || null;
        pending = table;
        process.write(JSON.stringify({ id: id, method: method, params: params || {} }) + '\n');
        return id;
    }
    function list(done) {
        return call('List', { sizes: false, kept: true }, (result, err) => {
            if (result) { client.apps = result.apps || []; client.kept = result.kept || []; client.listed = true; }
            if (done) done(result, err);
        });
    }
    function inspect(url, done) { return call('Inspect', { url: url }, done); }
    function cancel(request) { if (request > 0 && process.running) call('Cancel', { request: request }, null); }
    function install(params, done) { return call('Install', params, done); }
    function get(id, sizes, done) { return call('Get', { id: id, sizes: !!sizes }, done); }
    function launch(id, done) { return call('Launch', { id: id }, done); }
    function remove(ids, keepData, done) {
        return call('Remove', { ids: ids, keep_data: !!keepData }, (result, err) => { client.list(); if (done) done(result, err); });
    }
    function forget(ids, done) {
        return call('Forget', { ids: ids }, (result, err) => { client.list(); if (done) done(result, err); });
    }
    function runtimeName(id) {
        const r = runtimes.find(x => x.id === id);
        return r ? r.name : id === 'webkit' ? 'Arctic' : '';
    }

    function dispatch(line) {
        let message;
        try { message = JSON.parse(line); } catch (e) { return; }
        if (message.event === 'progress') { progress(message.request, message.stage || '', message.message || ''); return; }
        if (message.event === 'changed') { changed(message.ids || []); list(); return; }
        if (message.event !== undefined || message.id === undefined) return;
        const table = pending;
        const done = table[message.id];
        delete table[message.id];
        pending = table;
        if (done) done(message.error ? null : (message.result || {}), message.error || null);
    }

    Process {
        id: process
        command: [client.command, 'serve']
        stdinEnabled: true
        stdout: SplitParser { onRead: data => client.dispatch(data) }
        onExited: {
            client.ready = false;
            const table = client.pending;
            client.pending = ({});
            const failure = { code: 'internal', message: 'Web apps stopped. Open Get apps again to restart it.' };
            for (const id in table) if (table[id]) table[id](null, failure);
        }
    }
}
