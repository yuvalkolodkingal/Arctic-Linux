// Status is shared with Settings. Readiness must fail closed, and text must stay out of QML.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const context = {};
vm.createContext(context);
vm.runInContext(fs.readFileSync(__dirname + '/../DictationStatus.js', 'utf8').replace('.pragma library', ''), context);

const small = { profile: 'small-v2', model: 'small', cpu_variant: 'baseline',
                model_download_bytes: 487601967, download_bytes: 506181191 };
const turbo = { profile: 'turbo-q5-v3', model: 'large-v3-turbo-q5_0', cpu_variant: 'avx2',
                model_download_bytes: 574041195, download_bytes: 678117115 };
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
    ...turbo,
    state: 'recording', ready: true, progress: 3, language: 'he', backend: 'auto', active_backend: 'vulkan',
    transcript: 'private text', text: 'private text', audio: 'private audio',
}));
assert.equal(state.progress, 1);
assert.equal(state.language, 'he');
assert.equal(state.active_backend, 'vulkan');
assert.equal(state.model_download_bytes, 574041195);
assert.equal(state.download_bytes, 678117115);
for (const key of ['transcript', 'text', 'audio']) assert.equal(key in state, false);
assert.equal(JSON.stringify(state).includes('private'), false);
assert.equal(context.parse(JSON.stringify({ ...small, state: 'ready', ready: 'true', progress: -1, language: 'en', backend: 'cpu' })).ready, false);
assert.equal(context.parse('{"progress":-1}').progress, 0);
assert.equal(context.parse('{"language":"unknown","backend":"unknown"}').language, 'auto');
assert.equal(context.parse('{"language":"unknown","backend":"unknown"}').backend, 'auto');
assert.equal(context.size(678117115), '678.1 MB');
assert.equal(context.detail(context.parse(JSON.stringify({ ...small, state: 'queued' }))).includes('unavailable until setup finishes'), true);
assert.equal(context.detail(context.parse(JSON.stringify({ ...turbo, state: 'transcribing' }))).includes('Release the shortcut keys'), true);

for (const profile of [small, turbo]) {
    const snapshot = context.parse(JSON.stringify({ ...profile, state: 'downloading', progress: .3 }));
    assert.equal(context.profileKnown(snapshot), true);
    assert.equal(snapshot.model, profile.model);
    assert.equal(snapshot.download_bytes, profile.download_bytes);
    assert.equal(context.setupConsent(snapshot).includes(profile.download_bytes + ' bytes'), true);
    assert.equal(context.setupDescription(snapshot).includes(profile.model === 'small' ? 'Small' : 'Turbo Q5'), true);
}
for (const patch of [{ profile: 'unknown' }, { model: 'unknown' }, { model: turbo.model },
                     { cpu_variant: 'avx2' }, { model_download_bytes: -1 }, { download_bytes: 1 },
                     { download_bytes: '506181191' }, { model_download_bytes: true }]) {
    const snapshot = context.parse(JSON.stringify({ ...small, state: 'ready', ready: true, ...patch }));
    assert.equal(snapshot.ready, false);
    assert.equal(context.profileKnown(snapshot), false);
    assert.equal(snapshot.download_bytes, 0);
    assert.equal(snapshot.model_download_bytes, 0);
    assert.equal(context.setupConsent(snapshot).includes('unavailable'), true);
    assert.equal(context.setupConsent(snapshot).includes('Small'), false);
}
const activeUnknown = context.parse('{"state":"recording","ready":true,"profile":"unknown"}');
assert.equal(activeUnknown.ready, false);
assert.equal(context.active(activeUnknown), true, 'A malformed descriptor must not hide active recording');
const cpuFallback = context.parse(JSON.stringify({ ...turbo, state: 'error', ready: true,
    active_backend: 'cpu', active_cpu_variant: 'baseline', error: 'Record a shorter phrase again.' }));
assert.equal(cpuFallback.active_cpu_variant, 'baseline');
assert.equal(context.accelerationDetail(cpuFallback).includes('Current backend: Baseline CPU.'), true);
assert.equal(context.backends(context.parse(JSON.stringify(small))).some(x => x.value === 'vulkan'), false);
assert.equal(context.backends(context.parse(JSON.stringify(turbo))).some(x => x.value === 'vulkan'), true);
assert.equal(context.backends(context.parse(JSON.stringify({ ...small, backend: 'vulkan' }))).find(x => x.value === 'vulkan').label,
             'Vulkan GPU (unavailable)');
const needsCompatibility = context.parse(JSON.stringify({ ...turbo, state: 'error', ready: true,
    profile_selection: 'recommended', compatibility_required: true,
    recommended_profile: { ...turbo, transcript: 'private text' },
    compatibility_profile: { ...small, audio: 'private audio' } }));
assert.equal(needsCompatibility.ready, false);
assert.equal(needsCompatibility.compatibility_required, true);
assert.equal(context.selectionDetail(needsCompatibility).includes('Small compatibility model'), true);
assert.equal(context.setupConsent(needsCompatibility.compatibility_profile).includes('506181191 bytes'), true);
assert.equal(context.setupConsent(needsCompatibility.recommended_profile).includes('678117115 bytes'), true);
assert.equal(JSON.stringify(needsCompatibility).includes('private'), false, 'Nested descriptors must also prune private fields');
const compatibilitySelected = context.parse(JSON.stringify({ ...small, state: 'ready', ready: true,
    profile_selection: 'compatibility', recommended_profile: turbo, compatibility_profile: small }));
assert.equal(compatibilitySelected.ready, true);
assert.equal(context.selectionDetail(compatibilitySelected).includes('Compatibility is selected'), true);
for (const bad of [null, {}, { ...small, download_bytes: '506181191' }, turbo]) {
    const snapshot = context.parse(JSON.stringify({ ...small, compatibility_profile: bad }));
    assert.equal(context.profileKnown(snapshot.compatibility_profile), false);
    assert.equal(context.setupConsent(snapshot.compatibility_profile).includes('506181191'), false);
}
// Retry follows the persisted choice, while the current queued job keeps its
// original model/progress denominator. A hardware move can make these differ.
for (const [current, selection, expected] of [[small, 'recommended', turbo], [turbo, 'compatibility', small]]) {
    const queued = context.parse(JSON.stringify({ ...current, state: 'queued', profile_selection: selection,
        recommended_profile: turbo, compatibility_profile: small }));
    const target = context.setupTarget(queued, 'retry');
    assert.equal(queued.download_bytes, current.download_bytes, 'Frozen progress size must remain unchanged');
    assert.equal(target.profile, expected.profile);
    assert.equal(target.download_bytes, expected.download_bytes);
    assert.equal(context.setupConsent(target).includes(expected.download_bytes + ' bytes'), true);
    assert.equal(context.setupConsent(target).includes(current.download_bytes + ' bytes'), false);
}
for (const selection of ['', 'unknown', null]) {
    const queued = context.parse(JSON.stringify({ ...small, state: 'queued', profile_selection: selection,
        recommended_profile: turbo, compatibility_profile: small }));
    assert.equal(context.profileKnown(context.setupTarget(queued, 'retry')), false);
}
const missingTarget = context.parse(JSON.stringify({ ...small, state: 'queued', profile_selection: 'recommended',
    compatibility_profile: small }));
assert.equal(context.profileKnown(context.setupTarget(missingTarget, 'retry')), false);
console.log('Dictation adaptive profiles, actual sizes, readiness, privacy and state transitions passed.');
