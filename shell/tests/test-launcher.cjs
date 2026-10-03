// Launcher ranking and the "=" calculator: node shell/tests/test-launcher.cjs
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
function load(file) {
    const c = {};
    vm.createContext(c);
    vm.runInContext(fs.readFileSync(__dirname + '/../' + file, 'utf8').replace('.pragma library', ''), c);
    return c;
}
const Calc = load('Calc.js');
const Search = load('LauncherSearch.js');

// ---- calculator: arithmetic only, never code -------------------------------------------
const calc = t => Calc.evaluate(t);
assert.equal(calc('2+2').text, '4');
assert.equal(calc('2 + 3 * 4').text, '14');
assert.equal(calc('(2 + 3) * 4').text, '20');
assert.equal(calc('2^10').text, '1024');
assert.equal(calc('-2^2').text, '-4');
assert.equal(calc('2^-1').text, '0.5');
assert.equal(calc('10 / 4').text, '2.5');
assert.equal(calc('7 % 3').text, '1');
assert.equal(calc('12 × 4 ÷ 2').text, '24');
assert.equal(calc('0.1 + 0.2').text, '0.3');
assert.equal(calc('sqrt(16) + abs(-2)').text, '6');
assert.equal(calc('2pi').text, String(parseFloat((2 * Math.PI).toPrecision(12))));
assert.equal(calc('1e3 + 1').text, '1001');
assert.equal(calc('1/0').text, '∞');
assert.equal(calc('').ok, false);
assert.equal(calc('2 +').ok, false);
assert.equal(calc('(1').ok, false);
// Anything that isn't arithmetic is refused, not run.
for (const bad of ['alert(1)', 'this.constructor', 'process.exit()', '[].map', 'a=1', '"x"', 'constructor', '__proto__', 'Math.PI', '2;3']) {
    assert.equal(calc(bad).ok, false, bad);
}

// ---- modes ----------------------------------------------------------------------------
assert.deepEqual(JSON.parse(JSON.stringify(Search.mode('= 2+2'))), { mode: 'calc', text: '2+2' });
assert.deepEqual(JSON.parse(JSON.stringify(Search.mode('>htop'))), { mode: 'command', text: 'htop' });
assert.equal(Search.mode('zed').mode, 'search');

// ---- ranking --------------------------------------------------------------------------
const apps = [
    { name: 'Zed', keywords: 'Code editor' },
    { name: 'Zen Browser', keywords: 'Web browser internet' },
    { name: 'yazi', keywords: 'Terminal file manager' },
    { name: 'kitty', keywords: 'Terminal emulator' },
    { name: 'Visual Studio Code', keywords: 'editor' },
    { name: 'Wallpapers', keywords: 'background picture' },
];
const names = q => Search.rank(apps, q).map(a => a.name);
assert.deepEqual(names('ze').slice(0, 2), ['Zed', 'Zen Browser']);
assert.equal(names('zen')[0], 'Zen Browser');
assert.equal(names('term')[0], 'kitty');                  // keyword prefix (after a name match: none)
assert.equal(names('vsc')[0], 'Visual Studio Code');      // initials
assert.equal(names('studio')[0], 'Visual Studio Code');   // word start
assert.equal(names('picture')[0], 'Wallpapers');
assert.equal(names('qqqq').length, 0);
assert.equal(names('').length, apps.length);
assert.equal(names('')[0], 'kitty');                      // alphabetical when empty
console.log('Launcher ranking and calculator checks passed.');

// Live model rescans may repeat objects or contain an obsolete occurrence. IDs
// are case-sensitive; byId chooses the XDG winner, never the name/model order.
const systemSteam = { id: 'steam', name: 'Steam', command: ['steam'] };
const userSteam = { id: 'steam', name: 'Steam', command: ['switcherooctl', 'launch', '-g', '1', 'steam'] };
const sameName = { id: 'another-steam', name: 'Steam' };
const caseVariant = { id: 'Steam', name: 'Steam' };
const noDisplay = { id: 'nodisplay', noDisplay: true };
const winners = new Map([['steam', userSteam], ['another-steam', sameName], ['Steam', caseVariant], ['nodisplay', noDisplay]]);
const entries = Search.applicationEntries([systemSteam, userSteam, systemSteam, sameName, caseVariant,
    noDisplay, { id: 'masked' }, { id: 'removed' }, null], id => winners.get(id));
assert.deepEqual(Array.from(entries), [userSteam, sameName, caseVariant]);
assert.strictEqual(entries[0], userSteam);
assert.deepEqual(Search.applicationEntries([{ id: 'Steam' }], () => userSteam), []);
for (const query of ['', 'steam']) {
    const rows = entries.map(entry => ({ kind: 'app', id: 'app:' + entry.id, name: entry.name, entry }));
    rows.push({ kind: 'window', name: 'Steam', ref: {} }, { kind: 'window', name: 'Steam', ref: {} },
        { kind: 'action', id: 'action:steam/Store', name: 'Steam Store' },
        { kind: 'action', id: 'action:steam/Library', name: 'Steam Library' });
    const results = Search.rank(rows, query);
    assert.equal(results.filter(r => r.kind === 'app').length, 3);
    assert.equal(results.filter(r => r.kind === 'window').length, 2);
    assert.equal(results.filter(r => r.kind === 'action').length, 2);
}
console.log('Launcher desktop ID and override checks passed.');
