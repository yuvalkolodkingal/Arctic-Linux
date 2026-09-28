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

assert.equal(W.compare('0.10', '0.9'), 1);
assert.equal(W.compare('0.3', '0.3.0'), 0);
assert.equal(W.compare('0.2.1', '0.3'), -1);
assert.equal(W.osVersion('NAME="Arctic Linux"\nVERSION_ID=0.3\nPLATFORM_ID="platform:f44"\n'), '0.3');
assert.equal(W.osVersion('VERSION_ID="0.3"\n'), '0.3');
assert.equal(W.osVersion(''), '');

const notes = W.parseNotes(JSON.stringify({ version: '0.3', title: 'What’s new in Arctic Linux 0.3',
    items: [{ icon: 'moon', title: 'Night light', text: 'Warmer colours in the evening.' }, { title: 3 }],
    notes_url: 'https://example.org' }));
assert.deepEqual(plain(notes.items), [{ icon: 'moon', title: 'Night light', text: 'Warmer colours in the evening.' }]);
for (const bad of ['', '{', 'null', '[]', '{"version": 3, "items": []}', '{"version": "0.3", "items": []}'])
    assert.equal(W.parseNotes(bad), null, bad);

// A fresh home records the version and shows nothing (the first login has its own welcome).
assert.deepEqual(plain(W.decide('0.3', '', notes, false)), { show: false, record: '0.3' });
// Upgraded from 0.2: show; seen already, or older, or the live USB: don't.
assert.deepEqual(plain(W.decide('0.3', '0.2', notes, false)), { show: true, record: '' });
assert.deepEqual(plain(W.decide('0.3', '0.3', notes, false)), { show: false, record: '' });
assert.deepEqual(plain(W.decide('0.3', '0.4', notes, false)), { show: false, record: '' });
assert.deepEqual(plain(W.decide('0.3', '0.2', notes, true)), { show: false, record: '' });
// Notes for another release: nothing to show, but remember this one.
assert.deepEqual(plain(W.decide('0.4', '0.3', notes, false)), { show: false, record: '0.4' });
assert.deepEqual(plain(W.decide('0.4', '0.3', null, false)), { show: false, record: '0.4' });
console.log('whats-new: ok');
