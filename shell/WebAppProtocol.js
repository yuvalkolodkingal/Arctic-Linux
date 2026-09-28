.pragma library
// The wire format of `arctic-webapp serve` as WebAppClient.qml speaks it (tests:
// tests/test-webapp-protocol.cjs): JSON lines, {id, method, params} out; back come replies
// {id, result} or {id, error: {code, message, fields}} and events {event, …}, told apart by
// the "event" key.

function request(id, method, params) {
    return JSON.stringify({ id: id, method: method, params: params || {} }) + '\n';
}

// One line from the engine -> {kind: 'progress', request, stage, message} | {kind: 'changed', ids}
// | {kind: 'reply', id, result, error} | {kind: 'ignore'} (unknown events, bad JSON).
function parse(line) {
    let message;
    try { message = JSON.parse(line); } catch (e) { return { kind: 'ignore' }; }
    if (!message || typeof message !== 'object') return { kind: 'ignore' };
    if (message.event === 'progress')
        return { kind: 'progress', request: message.request, stage: message.stage || '', message: message.message || '' };
    if (message.event === 'changed') return { kind: 'changed', ids: message.ids || [] };
    if (message.event !== undefined || message.id === undefined || message.id === null) return { kind: 'ignore' };
    if (message.error)
        return { kind: 'reply', id: message.id, result: null,
                 error: { code: message.error.code || 'internal', message: message.error.message || 'The web-app engine couldn’t do that.',
                          fields: message.error.fields || {} } };
    return { kind: 'reply', id: message.id, result: message.result || {}, error: null };
}

// A runtime's name for people ("Arctic" for the built-in engine).
function runtimeName(runtimes, id) {
    const r = (runtimes || []).find(x => x.id === id);
    return r ? r.name : id === 'webkit' ? 'Arctic' : '';
}
