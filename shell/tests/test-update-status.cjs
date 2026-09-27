// The bar's "Updates ready" logic (UpdateStatus.js): node shell/tests/test-update-status.cjs
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
function load(file) {
    const c = {};
    vm.createContext(c);
    vm.runInContext(fs.readFileSync(__dirname + '/../' + file, 'utf8').replace('.pragma library', ''), c);
    return c;
}
const U = load('UpdateStatus.js');
const plain = o => JSON.parse(JSON.stringify(o));

// ---- parsing the status file arctic-update writes --------------------------------------
const written = JSON.stringify({
    armed: true, auto: 'download-and-install-on-reboot', channel: 'stable',
    checked_at: '2026-09-27T21:53:15+00:00', download_mb: 84.3,
    message: '12 updates will be installed the next time you restart.', packages: 12,
    staged_at: '2026-09-27T21:53:15+00:00', state: 'ready', updated_at: '2026-09-27T21:53:15+00:00',
});
const ready = U.parse(written);
assert.deepEqual(plain(ready), {
    state: 'ready', packages: 12, download_mb: 84.3, staged_at: '2026-09-27T21:53:15+00:00', armed: true,
    message: '12 updates will be installed the next time you restart.',
});
// Missing, empty, broken or odd files mean "nothing waiting", never an exception.
for (const bad of ['', '{', 'null', '[]', '42', '"ready"', '{"state": 3, "packages": "many", "armed": "true"}']) {
    const s = U.parse(bad);
    assert.equal(s.state === 'ready', false, bad);
    assert.equal(s.packages, 0, bad);
    assert.equal(s.armed, false, bad);
}
assert.equal(U.parse('{"packages": -3, "download_mb": -1}').packages, 0);

// ---- when the bar shows it -----------------------------------------------------------------
assert.equal(U.isReady(ready, true, false), true);
assert.equal(U.isReady(ready, false, false), false);                       // a dnf transaction removed /system-update
assert.equal(U.isReady(ready, true, true), false);                         // never on the live USB
assert.equal(U.isReady(Object.assign({}, ready, { armed: false }), true, false), false);   // AUTO=download-only
assert.equal(U.isReady(Object.assign({}, ready, { state: 'downloading' }), true, false), false);
assert.equal(U.isReady(Object.assign({}, ready, { packages: 0 }), true, false), false);

// ---- words ---------------------------------------------------------------------------------
assert.equal(U.summary(ready), '12 updates · 84 MB');
assert.equal(U.summary(U.parse('{"packages": 1, "download_mb": 0.04}')), '1 update · 0.1 MB');
assert.equal(U.summary(U.parse('{"packages": 3, "download_mb": 1843.2}')), '3 updates · 1.8 GB');
assert.equal(U.summary(U.parse('{"packages": 2}')), '2 updates');
assert.equal(U.detail(ready), '12 updates (84 MB) are downloaded and will be installed the next time you restart, before the desktop starts.');
assert.equal(U.detail(U.parse('{"packages": 1, "download_mb": 2.25}')), '1 update (2.3 MB) is downloaded and will be installed the next time you restart, before the desktop starts.');
assert.equal(U.notification(ready), '12 updates are ready. They install the next time you restart.');
assert.equal(U.notification(U.parse('{"packages": 1}')), '1 update is ready. It installs the next time you restart.');

// ---- one notification per downloaded update ------------------------------------------------
assert.equal(U.shouldNotify(ready, true, ''), true);
assert.equal(U.shouldNotify(ready, true, '2026-09-27T21:53:15+00:00\n'), false);   // already announced
assert.equal(U.shouldNotify(ready, true, '2026-09-26T06:12:00+00:00'), true);      // a newer download
assert.equal(U.shouldNotify(ready, false, ''), false);
assert.equal(U.shouldNotify(U.parse('{"state": "ready", "armed": true, "packages": 2}'), true, ''), false);   // no staged_at: can't remember it

console.log('update status: ok');
