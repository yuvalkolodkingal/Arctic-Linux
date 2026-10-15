// Status is shared with Settings. It accepts only the fixed readiness schema;
// audio and transcript content must never enter QML.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const context = {};
vm.createContext(context);
vm.runInContext(fs.readFileSync(__dirname + '/../DictationStatus.js', 'utf8').replace('.pragma library', ''), context);

const small = { profile: 'small-v2', model: 'small', model_download_bytes: 487601967,
                download_bytes: 506440871, vulkan_download_bytes: 66575872 };
const turbo = { profile: 'turbo-q5-v3', model: 'large-v3-turbo-q5_0', model_download_bytes: 574041195,
                download_bytes: 593457131, vulkan_download_bytes: 66575872 };
for (const input of ['', '{', 'null', '[]', '42', '"ready"']) {
    const state = context.parse(input);
    assert.equal(state.ready, false, input);
    assert.equal(state.state, 'unavailable', input);
    assert.equal(context.active(state), false, input);
}
for (const state of ['unavailable', 'queued', 'downloading']) {
    assert.equal(context.parse(JSON.stringify({ ...small, state, ready: true })).ready, false);
}
for (const state of ['ready', 'recording', 'transcribing', 'error']) {
    const snapshot = context.parse(JSON.stringify({ ...small, state, ready: true }));
    assert.equal(snapshot.ready, true);
    assert.equal(context.active(snapshot), ['recording', 'transcribing'].includes(state));
    assert.notEqual(context.headline(snapshot), 'Dictation is not ready');
}
const state = context.parse(JSON.stringify({
    ...turbo, state: 'recording', ready: true, language: 'he', backend: 'vulkan',
    transcript: 'private text', text: 'private text', audio: 'private audio',
}));
assert.equal(state.language, 'he');
assert.equal(state.backend, 'vulkan');
assert.equal(state.model_download_bytes, 574041195);
assert.equal(state.download_bytes, 593457131);
for (const key of ['transcript', 'text', 'audio']) assert.equal(key in state, false);
assert.equal(JSON.stringify(state).includes('private'), false);
assert.equal(context.parse(JSON.stringify({ ...small, state: 'ready', ready: 'true', language: 'en', backend: 'cpu' })).ready, false);
assert.equal(context.parse('{"language":"unknown","backend":"unknown"}').language, 'auto');
assert.equal(context.parse('{"language":"unknown","backend":"unknown"}').backend, 'cpu');
assert.equal(context.size(593457131), '593.5 MB');
assert.equal(context.detail(context.parse(JSON.stringify({ ...small, state: 'queued' }))).includes('Connect to the internet'), true);
assert.equal(context.detail(context.parse(JSON.stringify({ ...turbo, state: 'transcribing' }))).includes('processing audio'), true);
const pendingUpgrade = context.parse(JSON.stringify({
    ...small, state: 'ready', ready: true, version: '1.1.0', upgrade_pending: true,
}));
assert.equal(pendingUpgrade.ready, true);
assert.equal(pendingUpgrade.version, '1.1.0');
assert.equal(pendingUpgrade.upgrade_pending, true);
assert.equal(context.headline(pendingUpgrade).includes('update queued'), true);
assert.equal(context.detail(pendingUpgrade).includes('remains available'), true);
assert.equal(context.parse('{"version":"9.9.9","upgrade_pending":"true"}').upgrade_pending, false);
const availableUpgrade = context.parse(JSON.stringify({
    ...small, state: 'ready', ready: true, version: '1.1.0', upgrade_pending: false,
}));
assert.equal(context.headline(availableUpgrade).includes('update available'), true);
assert.equal(context.detail(availableUpgrade).includes('Choose Update / retry'), true);
assert.equal(context.detail(availableUpgrade).includes('automatically'), false);

for (const profile of [small, turbo]) {
    const snapshot = context.parse(JSON.stringify({ ...profile, state: 'downloading' }));
    assert.equal(context.profileKnown(snapshot), true);
    assert.equal(snapshot.model, profile.model);
    assert.equal(snapshot.download_bytes, profile.download_bytes);
    assert.equal(context.setupConsent(snapshot).includes(profile.download_bytes + ' bytes'), true);
    assert.equal(context.setupDescription(snapshot).includes(profile.model === 'small' ? 'Small' : 'Turbo Q5'), true);
}
for (const patch of [{ profile: 'unknown' }, { model: 'unknown' }, { model: turbo.model },
                     { model_download_bytes: -1 }, { download_bytes: 1 },
                     { download_bytes: '506440871' }, { model_download_bytes: true }]) {
    const snapshot = context.parse(JSON.stringify({ ...small, state: 'ready', ready: true, ...patch }));
    assert.equal(context.profileKnown(snapshot), false);
    assert.equal(context.setupConsent(snapshot).includes('Refresh status'), true);
}
const activeUnknown = context.parse('{"state":"recording","ready":true,"profile":"unknown"}');
assert.equal(context.active(activeUnknown), true, 'A malformed descriptor must not hide active recording');
const cpu = context.parse(JSON.stringify({ ...turbo, state: 'error', ready: true, backend: 'cpu', error: 'Retry setup.' }));
assert.equal(context.accelerationDetail(cpu).includes('CPU is selected'), true);
assert.equal(context.backends(cpu).some(x => x.value === 'vulkan'), true);
assert.equal(context.selectionDetail(cpu).includes('Large v3 Turbo Q5'), true);
assert.equal(context.setupTarget(cpu, 'retry'), cpu);
assert.equal(context.profileKnown(context.setupTarget(cpu, 'other')), false);
console.log('Direct VoxType profiles, exact sizes, readiness and privacy schema passed.');
