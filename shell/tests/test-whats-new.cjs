// "What's new" after an update (WhatsNewCore.js): node shell/tests/test-whats-new.cjs
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
function load(file) {
    const c = {};
    vm.createContext(c);
    vm.runInContext(fs.readFileSync(__dirname + '/../' + file, 'utf8').replace('.pragma library', ''), c);
    return c;
}
const W = load('WhatsNewCore.js');
const plain = o => JSON.parse(JSON.stringify(o));

// The source placeholder is replaced with this RPM Version-Release identity in %install.
const packagedId = 'arctic-1.2.1-1.202610131000.git7654321.fc44';

const notes = W.parseNotes(JSON.stringify({
    schema: 1,
    update_id: packagedId,
    title: 'What’s new in Arctic Linux',
    items: [
        { icon: 'microphone', title: 'Voice typing', text: 'Speak into any app.' },
        { icon: '../bad', title: 'Safe fallback icon', text: 'Still visible.' },
        { title: 3 }
    ],
    notes_url: 'https://example.org/notes'
}));
assert.equal(notes.updateId, packagedId);
assert.equal(notes.notesUrl, 'https://example.org/notes');
assert.deepEqual(plain(notes.items), [
    { icon: 'microphone', title: 'Voice typing', text: 'Speak into any app.' },
    { icon: 'sparkle', title: 'Safe fallback icon', text: 'Still visible.' }
]);

for (const bad of [
    '', '{', 'null', '[]',
    '{"schema":1,"update_id":"bad id","items":[{"title":"x","text":"y"}]}',
    '{"schema":2,"update_id":"2026.10.12-1","items":[{"title":"x","text":"y"}]}',
    '{"schema":1,"update_id":"2026.10.12-1","items":[]}'
])
    assert.equal(W.parseNotes(bad), null, bad);

for (const id of ['arctic-1.2.1-1.fc44', 'arctic-1.2.1-1.preview+1~2^3.fc44'])
    assert.equal(W.parseNotes(JSON.stringify({schema: 1, update_id: id,
        items: [{title: 'x', text: 'y'}]})).updateId, id);

// A fresh account records this exact notes id and relies on the first-login welcome.
assert.deepEqual(plain(W.decide('', notes, false)), { show: false, record: packagedId });
// The same update never nags; any newly packaged id shows once, including migration from legacy
// release-version state. Live media and malformed/missing notes never show or alter state.
assert.deepEqual(plain(W.decide(packagedId, notes, false)), { show: false, record: '' });
assert.deepEqual(plain(W.decide('2026.10.11-4', notes, false)), { show: true, record: '' });
assert.deepEqual(plain(W.decide('0.3', notes, false)), { show: true, record: '' });
assert.deepEqual(plain(W.decide('2026.10.11-4', notes, true)), { show: false, record: '' });
assert.deepEqual(plain(W.decide('2026.10.11-4', null, false)), { show: false, record: '' });
console.log('whats-new: ok');
