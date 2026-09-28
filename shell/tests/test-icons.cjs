// The shell's icon names resolve (design-data.js + icons-extra.js), and app tiles: node shell/tests/test-icons.cjs
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');
const shell = path.join(__dirname, '..');
function load(file, name) {
    const c = {};
    vm.createContext(c);
    vm.runInContext(fs.readFileSync(path.join(shell, file), 'utf8').replace('.pragma library', '')
        .replace(/^\.import .*$/mg, '') + '\nthis.' + name + ' = ' + name + ';', c);
    return c[name];
}
const design = load('assets/design-data.js', 'ICONS');
const extra = load('assets/icons-extra.js', 'EXTRA');
const has = n => Object.prototype.hasOwnProperty.call(design, n) || Object.prototype.hasOwnProperty.call(extra, n);

// ---- no extra glyph hides a design glyph, and each is plain SVG in the house style ----------
for (const [name, body] of Object.entries(extra)) {
    assert.ok(!Object.prototype.hasOwnProperty.call(design, name), name + ' shadows a design glyph');
    assert.match(name, /^[a-z0-9-]+$/, name);
    const tags = body.match(/<[^>]+>/g) || [];
    assert.ok(tags.length > 0, name);
    for (const t of tags) {
        assert.match(t, /^<(path|rect|circle|ellipse|line|polyline) [^<>]*\/>$/, name + ': ' + t);
        if (/fill="currentColor"/.test(t)) assert.match(t, /stroke="none"/, name + ': filled shapes are dots');
        else assert.ok(!/fill=/.test(t), name + ': no fills besides dots');
    }
    assert.equal(body.replace(/<[^>]+>/g, ''), '', name + ': nothing between the tags');
    for (const d of body.match(/ d="([^"]*)"/g) || []) assert.match(d, /^ d="[MmLlHhVvCcSsQqTtAaZz0-9 .,-]+"$/, name + ': ' + d);
}

// ---- the glyphs Settings carries too are identical -------------------------------------------
const settingsSrc = fs.readFileSync(path.join(shell, '../settings/assets/SettingsIcons.js'), 'utf8');
const settingsExtra = (() => {
    const c = {};
    vm.createContext(c);
    const body = settingsSrc.slice(settingsSrc.indexOf('var EXTRA'), settingsSrc.indexOf('};', settingsSrc.indexOf('var EXTRA')) + 2);
    vm.runInContext(body + '\nthis.EXTRA = EXTRA;', c);
    return c.EXTRA;
})();
for (const name of Object.keys(settingsExtra)) {
    if (Object.prototype.hasOwnProperty.call(extra, name)) assert.equal(extra[name], settingsExtra[name], name + ' differs from Settings');
}

// ---- every literal icon name in the shell's QML resolves --------------------------------------
const missing = [];
for (const file of fs.readdirSync(shell).filter(f => f.endsWith('.qml'))) {
    const src = fs.readFileSync(path.join(shell, file), 'utf8');
    const re = /\b(?:name|iconName|icon|iconOff|iconBase|mutedIcon|glyph):\s*'([a-z0-9-]+)'/g;
    let m;
    while ((m = re.exec(src))) if (!has(m[1])) missing.push(file + ': ' + m[1]);
    // Icon names inside JS object literals, e.g. { id: 'lock', icon: 'lock' }.
    const re2 = /\bicon: '([a-z0-9-]+)'/g;
    while ((m = re2.exec(src))) if (!has(m[1])) missing.push(file + ': ' + m[1]);
}
assert.deepEqual([...new Set(missing)], [], 'unknown icon names');


// ---- app tiles: a web app (arctic-webapp, desktop id org.arcticlinux.WebApp.…) keeps its own
// icon even when its name matches a design tile ("Signal", "Steam", "Settings") -------------
const dataCtx = {};
vm.createContext(dataCtx);
vm.runInContext(fs.readFileSync(path.join(shell, 'assets/design-data.js'), 'utf8').replace('.pragma library', ''), dataCtx);
const extraCtx = {};
vm.createContext(extraCtx);
vm.runInContext(fs.readFileSync(path.join(shell, 'assets/icons-extra.js'), 'utf8').replace('.pragma library', ''), extraCtx);
const icons = { Data: dataCtx, Extra: extraCtx };
vm.createContext(icons);
vm.runInContext(fs.readFileSync(path.join(shell, 'assets/Icons.js'), 'utf8').replace('.pragma library', '')
    .replace(/^\.import .*$/mg, ''), icons);
assert.equal(icons.tileFor('org.arcticlinux.WebApp.Signal_1a2b3c', 'Signal'), '');
assert.equal(icons.tileFor('org.arcticlinux.WebApp.Steam_1a2b3c', 'Steam Store'), '');
assert.equal(icons.tileFor('org.arcticlinux.WebApp.Settings_00ff00', 'Account settings'), '');
assert.equal(icons.tileFor('org.signal.Signal', 'Signal'), 'signal');
assert.equal(icons.tileFor('com.valvesoftware.Steam', 'Steam'), 'steam');
assert.equal(icons.tileFor('org.arcticlinux.Settings', 'Arctic Settings'), 'settings');
// ...and the extra glyphs reach Icons.js (the bar menus' icons).
assert.ok(icons.has('hotspot') && icons.has('lock'));
console.log('test-icons: ok (' + Object.keys(extra).length + ' extra glyphs)');
