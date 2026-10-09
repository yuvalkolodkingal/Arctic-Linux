// Status is shared with Settings. Readiness must fail closed, and text must stay out of QML.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const context = {};
vm.createContext(context);
vm.runInContext(fs.readFileSync(__dirname + '/../DictationStatus.js', 'utf8').replace('.pragma library', ''), context);

for (const input of ['', '{', 'null', '[]', '42', '"ready"', '{"state":"other","ready":true}']) {
    const state = context.parse(input);
    assert.equal(state.ready, false, input);
    assert.equal(state.state, 'unavailable', input);
    assert.equal(context.active(state), false, input);
}
for (const state of ['unavailable', 'queued', 'downloading']) {
    assert.equal(context.parse(JSON.stringify({ state, ready: true })).ready, false);
}
for (const state of ['ready', 'recording', 'transcribing', 'error']) {
    const snapshot = context.parse(JSON.stringify({ state, ready: true }));
    assert.equal(snapshot.ready, true);
    assert.equal(context.active(snapshot), ['recording', 'transcribing'].includes(state));
    assert.notEqual(context.headline(snapshot), 'Dictation is not ready');
}
const state = context.parse(JSON.stringify({
    state: 'recording', ready: true, progress: 3, language: 'he', backend: 'auto', active_backend: 'vulkan',
    transcript: 'private text', text: 'private text', audio: 'private audio', model_download_bytes: -1,
    download_bytes: 572524159,
}));
assert.equal(state.progress, 1);
assert.equal(state.language, 'he');
assert.equal(state.active_backend, 'vulkan');
assert.equal(state.model_download_bytes, 487601967);
for (const key of ['transcript', 'text', 'audio']) assert.equal(key in state, false);
assert.equal(JSON.stringify(state).includes('private'), false);
assert.equal(context.parse('{"state":"ready","ready":"true","progress":-1,"language":"en","backend":"cpu"}').ready, false);
assert.equal(context.parse('{"progress":-1}').progress, 0);
assert.equal(context.parse('{"language":"unknown","backend":"unknown"}').language, 'auto');
assert.equal(context.parse('{"language":"unknown","backend":"unknown"}').backend, 'auto');
assert.equal(context.size(572524159), '572.5 MB');
assert.equal(context.detail(context.parse('{"state":"queued"}')).includes('unavailable until setup finishes'), true);
assert.equal(context.detail(context.parse('{"state":"transcribing"}')).includes('Release the shortcut keys'), true);
console.log('Dictation status readiness, privacy boundary and state transitions passed.');
