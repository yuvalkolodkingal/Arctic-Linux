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

const notes = W.parseNotes(JSON.stringify({
    schema: 1,
    update_id: '2026.10.12-1',
    title: 'What’s new in Arctic Linux',
    items: [
        { icon: 'microphone', title: 'Local dictation', text: 'Speak in Hebrew or English.' },
        { icon: '../bad', title: 'Safe fallback icon', text: 'Still visible.' },
        { title: 3 }
    ],
    notes_url: 'https://example.org/notes'
}));
assert.equal(notes.updateId, '2026.10.12-1');
assert.equal(notes.notesUrl, 'https://example.org/notes');
assert.deepEqual(plain(notes.items), [
    { icon: 'microphone', title: 'Local dictation', text: 'Speak in Hebrew or English.' },
    { icon: 'sparkle', title: 'Safe fallback icon', text: 'Still visible.' }
]);

for (const bad of [
    '', '{', 'null', '[]',
    '{"schema":1,"update_id":"bad id","items":[{"title":"x","text":"y"}]}',
    '{"schema":2,"update_id":"2026.10.12-1","items":[{"title":"x","text":"y"}]}',
    '{"schema":1,"update_id":"2026.10.12-1","items":[]}'
])
    assert.equal(W.parseNotes(bad), null, bad);

// A fresh account records this exact notes id and relies on the first-login welcome.
assert.deepEqual(plain(W.decide('', notes, false)), { show: false, record: '2026.10.12-1' });
// The same update never nags; any newly packaged id shows once, including migration from legacy
// release-version state. Live media and malformed/missing notes never show or alter state.
assert.deepEqual(plain(W.decide('2026.10.12-1', notes, false)), { show: false, record: '' });
assert.deepEqual(plain(W.decide('2026.10.11-4', notes, false)), { show: true, record: '' });
assert.deepEqual(plain(W.decide('0.3', notes, false)), { show: true, record: '' });
assert.deepEqual(plain(W.decide('2026.10.11-4', notes, true)), { show: false, record: '' });
assert.deepEqual(plain(W.decide('2026.10.11-4', null, false)), { show: false, record: '' });
console.log('whats-new: ok');
