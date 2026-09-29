// The OSD's sizes and timing: node shell/tests/test-osd-model.cjs
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const c = {};
vm.createContext(c);
vm.runInContext(fs.readFileSync(__dirname + '/../OsdModel.js', 'utf8').replace('.pragma library', ''), c);
const M = c;

// A level stays 1.2 s and is 280 wide, as the volume pill always was.
assert.equal(M.duration('level', 'DELL U2720Q', ''), 1200);
assert.equal(M.duration('volume'), 1200);
assert.equal(M.width('level', 900), 280);
// A notice: 1.6 s up to 20 characters, then 60 ms more for each, at most 3 s.
assert.equal(M.duration('notice', 'Caps Lock on', ''), 1600);
assert.equal(M.duration('notice', 'x'.repeat(30), ''), 1600 + 10 * 60);
assert.equal(M.duration('notice', 'Night light on', 'Until 07:00'), 1600 + (14 + 11 + 3 - 20) * 60);
assert.equal(M.duration('notice', 'x'.repeat(200), ''), 3000);
// It fits its words, between 200 and 420.
assert.equal(M.width('notice', 120), 200);
assert.equal(M.width('notice', 311.6), 312);
assert.equal(M.width('notice', 1000), 420);
assert.equal(M.width('notice', undefined), 200);
// Unknown glyphs fall back to "info".
const known = n => ['keyboard', 'hash'].includes(n);
assert.equal(M.icon('keyboard', known), 'keyboard');
assert.equal(M.icon('caps-lock', known), 'info');
assert.equal(M.icon('', known), 'info');
console.log('OSD model checks passed.');
