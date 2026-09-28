// Keyboard movement in the bar menus (MenuNav.js): node shell/tests/test-menu-nav.cjs
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
function load(file) {
    const c = {};
    vm.createContext(c);
    vm.runInContext(fs.readFileSync(__dirname + '/../' + file, 'utf8').replace('.pragma library', ''), c);
    return c;
}
const N = load('MenuNav.js');
const row = (label, group, enabled) => ({ label: label, group: group || 0, enabled: enabled !== false });

// Wi-Fi header switch (group 0), four networks with one disabled (group 1), two footer rows (group 2).
const stops = [row('Wi-Fi', 0), row('Home', 1), row('Office', 1, false), row('Hotel', 1), row('home-guest', 1),
               row('Network settings', 2), row('Edit connections', 2)];

// ---- Up / Down: skip disabled rows, wrap at the ends ------------------------------------
assert.equal(N.step(stops, 0, 1), 1);
assert.equal(N.step(stops, 1, 1), 3);                 // Office is disabled
assert.equal(N.step(stops, 3, -1), 1);
assert.equal(N.step(stops, 6, 1), 0);                 // wraps to the top
assert.equal(N.step(stops, 0, -1), 6);                // and to the bottom
assert.equal(N.step(stops, 6, 1, false), 6);          // without wrapping it stays
assert.equal(N.step(stops, -1, 1), 0);                // nothing focused yet: first row
assert.equal(N.step(stops, -1, -1), 6);
assert.equal(N.step([], 0, 1), -1);
assert.equal(N.step([row('a', 0, false)], -1, 1), -1);   // nothing usable
assert.equal(N.step([row('only')], 0, 1), 0);

// ---- Home / End, PgUp / PgDn -----------------------------------------------------------------
const edges = [row('x', 0, false), row('a'), row('b'), row('c', 0, false)];
assert.equal(N.edge(edges, -1), 1);
assert.equal(N.edge(edges, 1), 2);
assert.equal(N.page(stops, 0, 1, 5), 6);              // 5 usable rows down: Home, Hotel, guest, settings, editor
assert.equal(N.page(stops, 0, 1, 2), 3);
assert.equal(N.page(stops, 6, -1, 5), 0);
assert.equal(N.page(stops, 5, 1, 5), 6);              // stops at the end, no wrap

// ---- Tab / Shift+Tab: groups -------------------------------------------------------------
assert.equal(N.group(stops, 0, 1), 1);                // header → list
assert.equal(N.group(stops, 3, 1), 5);                // list → footer
assert.equal(N.group(stops, 6, 1), 0);                // footer → header (wraps)
assert.equal(N.group(stops, 5, -1), 1);               // footer → the list's first row
assert.equal(N.group(stops, 1, -1), 0);
assert.equal(N.group(stops, 0, -1), 5);               // header → footer's first row
assert.equal(N.group([row('a', 1), row('b', 1)], 1, 1), 1);   // one group: stays
assert.equal(N.group(stops, -1, 1), 0);

// ---- type-ahead ------------------------------------------------------------------------------
assert.equal(N.match(stops, 0, 'h'), 1);              // Home
assert.equal(N.match(stops, 1, 'h'), 3);              // then Hotel
assert.equal(N.match(stops, 3, 'h'), 4);              // then home-guest (case-insensitive)
assert.equal(N.match(stops, 4, 'h'), 1);              // wraps
assert.equal(N.match(stops, 1, 'ho'), 3);
assert.equal(N.match(stops, 0, 'off'), -1);           // Office is disabled
assert.equal(N.match(stops, 0, 'zzz'), -1);
assert.equal(N.match(stops, 0, ''), -1);
assert.equal(N.match(stops, -1, 'wi'), 0);
assert.equal(N.match(stops, 5, 'network'), 5);        // only itself matches

console.log('menu nav: ok');
