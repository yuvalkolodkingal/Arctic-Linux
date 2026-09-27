#!/usr/bin/env node
// Export the design system's icons, app tiles and fox mark for the installer UI.
// Runs the design bundle (components/bundle.js) in a node vm, as described in
// docs/BUILD-SPEC.md §7, and writes:
//   assets/icons/<name>.svg          every design icon, stroke #151a21 (for other tools)
//   assets/tiles/<id>-light.svg      app tiles, Winter colours (appTileSVG)
//   assets/tiles/<id>-dark.svg       app tiles, Polar night colours
//   assets/mark-dark.svg / mark-light.svg   the fox mark with amber eyes
//   assets/Icons.js                  QML JS library: icon bodies + tile/app data, so
//                                    Icon.qml can recolour icons at runtime
// The app catalog (modules/) has grown past the design's 28 app tiles: every visible module
// gets a tile drawn the design's way (category tint + one generic line glyph, never a vendor
// logo) from its module.toml (category, tile, icon), with the extra glyphs below.
// Usage: node dev/export-assets.js <path-to-design-project>   (dir containing components/bundle.js)
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const designDir = process.argv[2];
if (!designDir) {
  console.error('usage: export-assets.js <design project dir with components/bundle.js>');
  process.exit(2);
}
const bundle = fs.readFileSync(path.join(designDir, 'components', 'bundle.js'), 'utf8');
const ctx = { window: {}, document: {} };
vm.createContext(ctx);
vm.runInContext(bundle, ctx);
const A = ctx.window.Arctic;

const out = path.resolve(__dirname, '..', 'assets');
fs.mkdirSync(path.join(out, 'icons'), { recursive: true });
fs.mkdirSync(path.join(out, 'tiles'), { recursive: true });

// Token values (design/tokens.json, semantic colours) used by the tiles.
const TINT = {
  light: { 'info-soft': '#e2eefa', 'surface-sunken': '#e8edf1', 'slate-900': '#1a212a', 'warm-soft': '#f0eae3', 'accent-soft': '#fdf0d6', 'success-soft': '#e1f2e9', 'warning-soft': '#fbeadf' },
  dark: { 'info-soft': '#172c42', 'surface-sunken': '#0f141a', 'slate-900': '#1a212a', 'warm-soft': '#2f2924', 'accent-soft': '#3a2d16', 'success-soft': '#16322a', 'warning-soft': '#3a2518' },
};
const INK = { light: '#151a21', dark: '#e9eef3' };
const SNOW100 = '#f3f6f8';
// APP_TINT is not exported by the bundle; mirror it (bundle.js "APP_TINT") and extend it to
// the catalog's optional groups. Amber (accent-soft) stays with Files and error-soft is a status
// colour, so neither is reused. Dark tiles (slate-900) carry snow ink.
const APP_TINT = {
  browser: 'info-soft', editor: 'surface-sunken', terminal: 'slate-900', shell: 'warm-soft', files: 'accent-soft',
  office: 'success-soft', video: 'warning-soft', extras: 'surface-sunken', system: 'surface-sunken',
  music: 'warning-soft', photos: 'warm-soft', graphics: 'warm-soft', recording: 'warning-soft', chat: 'info-soft',
  email: 'info-soft', notes: 'success-soft', reading: 'success-soft', gaming: 'slate-900', security: 'surface-sunken',
  sync: 'info-soft', dev: 'surface-sunken', containers: 'surface-sunken', utilities: 'surface-sunken',
};
const SNOW_INK = new Set(['terminal', 'gaming']);

// Glyphs the catalog uses that the design bundle does not draw (24-unit grid, bodies only,
// same 1.75 line as the rest of the set).
const EXTRA_ICONS = {
  mail: '<rect x="3.5" y="5.5" width="17" height="13" rx="2.5"/><path d="M4.5 7.5l7.5 5.5 7.5-5.5"/>',
  book: '<path d="M12 6.5c-1.8-1.4-4.3-2-7.5-2v13c3.2 0 5.7.6 7.5 2 1.8-1.4 4.3-2 7.5-2v-13c-3.2 0-5.7.6-7.5 2z M12 6.5v13"/>',
  cloud: '<path d="M7.5 18.5h9.5a3.75 3.75 0 0 0 .4-7.48A5.5 5.5 0 0 0 6.8 9.6a4.5 4.5 0 0 0 .7 8.9z"/>',
  send: '<path d="M20.5 3.5l-17 7 7 2.5 2.5 7z M20.5 3.5L10.5 13"/>',
  branch: '<circle cx="7" cy="5.5" r="2"/><circle cx="7" cy="18.5" r="2"/><circle cx="17" cy="7.5" r="2"/><path d="M7 7.5v9 M17 9.5c0 4.5-10 2.5-10 7"/>',
  database: '<ellipse cx="12" cy="6" rx="7" ry="2.5"/><path d="M5 6v12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5V6 M5 12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5"/>',
  monitor: '<rect x="3" y="4.5" width="18" height="12" rx="2.5"/><path d="M9 20h6 M12 16.5V20"/>',
  phone: '<rect x="7" y="3" width="10" height="18" rx="2.5"/><path d="M11 17.5h2"/>',
  key: '<circle cx="8" cy="15" r="4"/><path d="M10.9 12.1l8.6-8.6 M16 7l2.5 2.5 M13.5 9.5l2 2"/>',
};
const ICONS = Object.assign({}, A.ICONS);
for (const [name, body] of Object.entries(EXTRA_ICONS)) {
  if (!ICONS[name]) ICONS[name] = body;
}

// The catalog, read with a line parser that is enough for the catalog's own house style
// (top-level `key = "string" | true | false`, `[[category]]` blocks, `modules = [...]`).
const modulesDir = path.resolve(__dirname, '..', '..', 'modules');
function tomlTop(text) {
  const o = {};
  for (const line of text.split('\n')) {
    if (/^\s*\[/.test(line)) break;
    const m = /^([a-z_]+) = ("(?:[^"\\]|\\.)*"|true|false)\s*$/.exec(line);
    if (m) o[m[1]] = JSON.parse(m[2]);
  }
  return o;
}
const categories = fs.readFileSync(path.join(modulesDir, 'catalog.toml'), 'utf8').split(/^\[\[category\]\]\s*$/m).slice(1).map(block => {
  const c = tomlTop(block);
  c.modules = JSON.parse(/^modules = (\[.*\])\s*$/m.exec(block)[1]);
  return c;
});
const catalogApps = {};
for (const cat of categories) {
  for (const id of cat.modules) {
    const m = tomlTop(fs.readFileSync(path.join(modulesDir, cat.id, id, 'module.toml'), 'utf8'));
    catalogApps[m.tile || id] = [m.name, m.category, m.icon, m.summary, !!m.default];
  }
}

let n = 0;
for (const name of Object.keys(ICONS)) {
  const svg = A.ICONS[name] ? A.icon(name, { size: 24, color: '#151a21' })
    : '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="#151a21" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="ar-icon">' +
      ICONS[name].replace(/currentColor/g, '#151a21') + '</svg>';
  fs.writeFileSync(path.join(out, 'icons', name + '.svg'), svg + '\n');
  n++;
}

// Design tiles (installer, settings, …) plus every catalog app; the catalog decides the
// category (and so the tint) of apps the design also draws.
const APPS = Object.assign({}, A.APPS, catalogApps);
function tileSVG(id, theme) {
  const a = APPS[id];
  if (!APP_TINT[a[1]]) throw new Error('no tint for category ' + a[1] + ' (' + id + ')');
  if (!ICONS[a[2]]) throw new Error('no glyph ' + a[2] + ' (' + id + ')');
  const tint = TINT[theme][APP_TINT[a[1]]];
  const ink = SNOW_INK.has(a[1]) ? SNOW100 : INK[theme];
  // Same geometry as the bundle's appTileSVG (64 box, rx 19 = 30%, glyph scaled 1.5).
  return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64"><rect width="64" height="64" rx="19" fill="' + tint + '"/>' +
    '<g transform="translate(14 14) scale(1.5)" fill="none" stroke="' + ink + '" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' +
    ICONS[a[2]].replace(/currentColor/g, ink) + '</g></svg>\n';
}
let t = 0;
for (const id of Object.keys(APPS)) {
  const light = tileSVG(id, 'light');
  // Sanity: where the design draws the same tile, ours must equal its own appTileSVG output.
  const d = A.APPS[id];
  if (d && d[1] === APPS[id][1] && d[2] === APPS[id][2] && light.trim() !== A.appTileSVG(id, 64).trim()) {
    throw new Error('tile mismatch for ' + id);
  }
  fs.writeFileSync(path.join(out, 'tiles', id + '-light.svg'), light);
  fs.writeFileSync(path.join(out, 'tiles', id + '-dark.svg'), tileSVG(id, 'dark'));
  t++;
}

fs.writeFileSync(path.join(out, 'mark-dark.svg'), A.mark({ size: 96, ink: '#e9eef3', eye: '#f6bd55' }) + '\n');
fs.writeFileSync(path.join(out, 'mark-light.svg'), A.mark({ size: 96, ink: '#151a21', eye: '#efa637' }) + '\n');

// QML JS library. `.pragma library` so it is shared by every Icon instance.
const apps = {};
for (const id of Object.keys(APPS)) {
  const a = APPS[id];
  apps[id] = { name: a[0], category: a[1], glyph: a[2], summary: a[3], default: a[4] };
}
// Picker sections in the design's shape: [id, name, "one" | "many", note].
const cats = categories.map(c => [c.id, c.name, c.choice === 'one' ? 'one' : 'many', c.note || '']);
const js = '.pragma library\n' +
  '// Generated by dev/export-assets.js from the Arctic design bundle and modules/. Do not edit.\n' +
  'var ICONS = ' + JSON.stringify(ICONS, null, 1) + ';\n' +
  'var APPS = ' + JSON.stringify(apps, null, 1) + ';\n' +
  'var CATEGORIES = ' + JSON.stringify(cats) + ';\n' +
  'var STEP_NAMES = ' + JSON.stringify(A.STEP_NAMES) + ';\n' +
  '// Build an SVG data URI for icon `name` stroked with `color` (a #rrggbb string).\n' +
  'function svg(name, color, stroke) {\n' +
  '    var body = ICONS[name] || ICONS["help"];\n' +
  '    body = body.replace(/currentColor/g, color);\n' +
  '    var s = \'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="\' + color +\n' +
  '        \'" stroke-width="\' + (stroke || 1.75) + \'" stroke-linecap="round" stroke-linejoin="round">\' + body + "</svg>";\n' +
  '    return "data:image/svg+xml;utf8," + encodeURIComponent(s);\n' +
  '}\n';
fs.writeFileSync(path.join(out, 'Icons.js'), js);
console.log('icons: ' + n + ', tiles: ' + t + ' x2 themes, marks: 2, Icons.js written to ' + out);
