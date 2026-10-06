#!/usr/bin/env node
'use strict';
// Reproduce catalog export from the checked-in drawing interface in a scratch
// checkout: distinct modules may share a tile and use TOML literal strings.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const cp = require('node:child_process');
const repo = path.resolve(__dirname, '../..');
const assets = path.join(repo, 'installer-ui/assets');
const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'arctic-export-assets-test-'));
try {
  const drawing = {};
  vm.createContext(drawing);
  vm.runInContext(fs.readFileSync(path.join(assets, 'Icons.js'), 'utf8').replace(/^\.pragma library\r?\n/, ''), drawing);
  const icons = {}, tiles = {}, apps = {};
  for (const name of Object.keys(drawing.ICONS)) icons[name] = fs.readFileSync(path.join(assets, 'icons', name + '.svg'), 'utf8').trimEnd();
  for (const [id, app] of Object.entries(drawing.APPS)) {
    const tile = path.join(assets, 'tiles', id + '-light.svg');
    if (!fs.existsSync(tile)) continue;
    apps[id] = [app.name, app.category, app.glyph, app.summary, app.default];
    tiles[id] = fs.readFileSync(tile, 'utf8').trimEnd();
  }
  const marks = Object.fromEntries(['dark', 'light'].map(theme => [theme, fs.readFileSync(path.join(assets, 'mark-' + theme + '.svg'), 'utf8').trimEnd()]));
  const design = path.join(scratch, 'design');
  fs.mkdirSync(path.join(design, 'components'), {recursive: true});
  fs.writeFileSync(path.join(design, 'components/bundle.js'),
    'const icons=' + JSON.stringify(icons) + ',tiles=' + JSON.stringify(tiles) + ',marks=' + JSON.stringify(marks) + ';\n' +
    'window.Arctic={ICONS:' + JSON.stringify(drawing.ICONS) + ',APPS:' + JSON.stringify(apps) + ',STEP_NAMES:' + JSON.stringify(drawing.STEP_NAMES) +
    ',icon:name=>icons[name],appTileSVG:id=>tiles[id],mark:options=>marks[options.ink==="#e9eef3"?"dark":"light"]};\n');
  fs.cpSync(path.join(repo, 'modules'), path.join(scratch, 'modules'), {recursive: true});
  fs.mkdirSync(path.join(scratch, 'installer-ui/dev'), {recursive: true});
  fs.copyFileSync(path.join(__dirname, 'export-assets.js'), path.join(scratch, 'installer-ui/dev/export-assets.js'));
  const settingsMirror = path.join(scratch, 'settings/assets/Icons.js');
  fs.mkdirSync(path.dirname(settingsMirror), {recursive: true});
  fs.writeFileSync(settingsMirror, '// stale Settings metadata must be replaced by export\n');
  cp.execFileSync(process.execPath, [path.join(scratch, 'installer-ui/dev/export-assets.js'), design], {stdio: 'pipe'});
  const generated = path.join(scratch, 'installer-ui/assets');
  assert.deepEqual(fs.readFileSync(settingsMirror), fs.readFileSync(path.join(generated, 'Icons.js')), 'Settings mirror was not regenerated');
  assert.deepEqual(fs.readFileSync(path.join(repo, 'settings/assets/Icons.js')), fs.readFileSync(path.join(assets, 'Icons.js')), 'checked-in Settings mirror is stale');
  const metadata = {};
  vm.createContext(metadata);
  vm.runInContext(fs.readFileSync(path.join(generated, 'Icons.js'), 'utf8').replace(/^\.pragma library\r?\n/, ''), metadata);
  for (const [id, name] of [['tor-client', 'Tor SOCKS client'], ['tailscale', 'Tailscale'], ['vpn-tools', 'OpenVPN support']]) {
    assert.equal(metadata.APPS[id].name, name, id + ': single-quoted name was lost');
    assert.equal(metadata.APPS[id].category, 'security');
    assert.ok(metadata.APPS[id].summary, id + ': distinct module summary was lost');
    assert.equal(fs.existsSync(path.join(generated, 'tiles', id + '-light.svg')), false, id + ': unnecessary duplicate shared tile');
  }
  assert.equal(metadata.APPS['tor-browser'].name, 'Tor Browser', 'shared artwork overwrote browser metadata');
  let unchanged = 0;
  for (const group of ['icons', 'tiles']) {
    for (const name of fs.readdirSync(path.join(assets, group))) {
      assert.deepEqual(fs.readFileSync(path.join(generated, group, name)), fs.readFileSync(path.join(assets, group, name)), group + '/' + name);
      unchanged++;
    }
  }
  for (const theme of ['dark', 'light']) assert.deepEqual(fs.readFileSync(path.join(generated, 'mark-' + theme + '.svg')), fs.readFileSync(path.join(assets, 'mark-' + theme + '.svg')));
  console.log('export-assets: Settings mirror refreshed byte-for-byte; distinct shared-tile metadata and TOML literal names preserved; ' + unchanged + ' existing icon/tile SVGs and both fox marks unchanged');
} finally {
  fs.rmSync(scratch, {recursive: true, force: true});
}
