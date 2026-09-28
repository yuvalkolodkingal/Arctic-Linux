// Weather words, glyphs and text: node shell/tests/test-weather.cjs
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const W = {};
vm.createContext(W);
vm.runInContext(fs.readFileSync(__dirname + '/../Weather.js', 'utf8').replace('.pragma library', ''), W);

// Every WMO code Open-Meteo documents has words and a glyph that exists.
const codes = [0, 1, 2, 3, 45, 48, 51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75, 77, 80, 81, 82, 85, 86, 95, 96, 99];
for (const code of codes) {
    for (const day of [true, false]) {
        const d = W.describe(code, day);
        assert.ok(d.text, code);
        assert.ok(W.GLYPHS[d.glyph], code + ' ' + d.glyph);
    }
}
assert.deepEqual([W.describe(0, true).glyph, W.describe(0, false).glyph], ['sun', 'moon']);
assert.deepEqual([W.describe(2, true).text, W.describe(2, false).glyph], ['Partly cloudy', 'cloud-moon']);
assert.equal(W.describe(66, true).text, 'Freezing rain');
assert.equal(W.describe(75).glyph, 'snowflake');
assert.equal(W.describe(96).glyph, 'cloud-lightning');
assert.equal(W.describe(12345).text, 'Cloudy', 'an unknown code still says something');
// Every glyph draws with the design's stroke and nothing filled.
for (const [name, body] of Object.entries(W.GLYPHS)) {
    assert.ok(!/fill=/.test(body), name);
    assert.ok(decodeURIComponent(W.icon(name, '#ff12171e')).includes('stroke="#12171e"'), name);
}

// Temperatures: rounded, never "-0°".
assert.equal(W.tempText(21.4), '21°');
assert.equal(W.tempText(-0.4), '0°');
assert.equal(W.tempText(-3.6), '-4°');
assert.equal(W.tempText(null), '–');
assert.equal(W.unitText('imperial'), '°F');

// Day names and "updated".
assert.equal(W.dayName('2026-09-29', '2026-09-28'), 'Tue');
assert.equal(W.dayName('2026-09-28', '2026-09-28'), 'Today');
assert.equal(W.dayName('soon', ''), '');
const at = Math.floor(new Date(2026, 8, 28, 14, 5).getTime() / 1000);
assert.equal(W.updatedText(at, at + 60), 'updated 14:05');
assert.equal(W.updatedText(at, at + 3 * 3600 + 10), 'updated 3 h ago');
assert.equal(W.updatedText(0, at), '');

assert.equal(W.summary({ place: 'Jerusalem', current: { code: 2, is_day: true, temp: 21.4 } }), 'Partly cloudy, 21° in Jerusalem');
assert.equal(W.summary(null), '');

console.log('Weather checks passed.');
