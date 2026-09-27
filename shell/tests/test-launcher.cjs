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
