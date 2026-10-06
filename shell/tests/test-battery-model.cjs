// The normalized Quickshell charge contract and the SVG's real usable interior.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert/strict');
const shell = path.join(__dirname, '..');
function load(file, extra = {}) {
    const context = vm.createContext(extra);
    vm.runInContext(fs.readFileSync(path.join(shell, file), 'utf8')
        .replace(/^\.pragma library$/mg, '').replace(/^\.import .*$/mg, ''), context);
    return context;
}
const model = load('BatteryModel.js');
for (const [fraction, expected] of [[0, 0], [.01, 1], [.8, 80], [.994, 99], [.995, 100], [1, 100], [1.02, 100]]) {
    assert.equal(model.percentage(fraction), expected);
    assert.equal(model.percentageText(expected), expected + '%');
}
for (const invalid of [NaN, Infinity, -Infinity, -1, null, undefined, '1']) {
    assert.equal(model.percentage(invalid), -1);
    assert.equal(model.percentageText(-1), 'Charge unknown');
}
const icons = load('assets/Icons.js', {
    Data: load('assets/design-data.js'), Extra: load('assets/icons-extra.js')
});
const svg = (name, percentage) => decodeURIComponent(icons.icon(name, '#151a21', 0, percentage).split(',').slice(1).join(','));
assert.match(svg('battery', 100), /x="4\.8" y="9\.8" width="12\.4" height="4\.4"/);
assert.match(svg('battery', 50), /width="6\.2" height="4\.4"/);
assert.match(svg('battery', 80), /width="9\.92" height="4\.4"/);
assert.doesNotMatch(svg('battery', 0), /x="4\.8"/);
assert.match(svg('battery', 101), /width="12\.4" height="4\.4"/);
assert.match(svg('battery', -1), /cy="14\.4"/);
assert.match(svg('battery-charging', 100), /mask="url\(#battery-bolt\)"/);
// Preserve the generic artwork for places that mean battery category/health.
assert.match(svg('battery', undefined), /width="9" height="4\.4"/);
assert.equal(svg('wifi', 100), svg('wifi', undefined));
console.log('test-battery-model: ok');
