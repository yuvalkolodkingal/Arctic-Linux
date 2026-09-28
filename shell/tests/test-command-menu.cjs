// The command menu's model and its data file: node shell/tests/test-command-menu.cjs
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const { execFileSync } = require('child_process');
const root = __dirname + '/../';
function load(file, extra) {
    const c = Object.assign({}, extra || {});
    vm.createContext(c);
    vm.runInContext(fs.readFileSync(root + file, 'utf8').replace('.pragma library', '').replace(/^\.import .*$/mg, ''), c);
    return c;
}
const Search = load('LauncherSearch.js');
const Menu = load('MenuModel.js', { LauncherSearch: Search });
const plain = x => JSON.parse(JSON.stringify(x));

// ---- the shipped data -----------------------------------------------------------------------
// Shipped files are strict JSON (other tools may read them), {"version": 1, "entries": {…}}.
const text = fs.readFileSync(root + 'menu/00-arctic.json', 'utf8');
const shippedFile = JSON.parse(text);
assert.equal(shippedFile.version, 1);
const shipped = shippedFile.entries;
for (const f of fs.readdirSync(root + 'menu')) assert.ok(/^\d\d-[a-z-]+\.json$/.test(f), 'menu file name: ' + f);
const icons = load('assets/design-data.js').ICONS;
const top = ['apps', 'learn', 'capture', 'toggle', 'style', 'setup', 'install', 'remove', 'update', 'system'];
assert.deepEqual(Object.keys(shipped).filter(id => !id.includes('.')), top);
for (const [id, e] of Object.entries(shipped)) {
    assert.ok(Menu.validId(id), id);
    assert.ok(e.label && typeof e.label === 'string', id + ' has a label');
    assert.ok(icons[e.icon], id + ': icon ' + e.icon + ' is a design icon');
    if (id.includes('.')) assert.ok(shipped[Menu.parentOf(id)], id + ' has a parent');
    // Shipped rows run argv lists, never a string through the shell.
    if (e.run !== undefined) assert.ok(Array.isArray(e.run) && e.run.every(a => typeof a === 'string'), id + ' runs an argv list');
    if (e.state !== undefined) assert.ok(e.state === 'dark' || Array.isArray(e.state), id + ' state');
    if (e.ipc !== undefined) assert.equal(e.run[0], 'arctic-shell-ipc', id + ': an ipc guard goes with an arctic-shell-ipc command');
    if (e.ipc !== undefined) assert.equal(e.run.slice(1, 3).join(' '), e.ipc, id + ': the ipc guard names the function it calls');
    if (e.keys !== undefined) assert.match(e.keys, /^(Super|Ctrl|Shift|Alt|Print)( \+ \S+)*$/, id + ' keys');
}
// The cross-stream names (impl contract) and the capture branch the capture key opens.
assert.deepEqual(shipped['capture.area'].run, ['arctic-screenshot', 'area']);
assert.deepEqual(shipped['capture.color'].run, ['arctic-colorpick']);
assert.deepEqual(shipped['capture.text'].run, ['arctic-ocr']);
assert.deepEqual(shipped['capture.record'].run, ['arctic-record', 'toggle']);
assert.deepEqual(shipped['toggle.nightlight'].run, ['arctic-nightlight', 'toggle']);
assert.deepEqual(shipped['toggle.awake'].run, ['arctic-keep-awake', 'toggle']);
assert.deepEqual(shipped['remove.apps'].run, ['arctic-shell-ipc', 'apps', 'remove']);
// Every IPC function the shipped rows call that this shell already has is really in shell.qml.
const shellQml = fs.readFileSync(root + 'shell.qml', 'utf8');
for (const fn of ['launcher apps', 'launcher search', 'apps install', 'wallpapers open']) {
    const [target, name] = fn.split(' ');
    const block = new RegExp("target: '" + target + "'[\\s\\S]*?\\n    \\}").exec(shellQml);
    assert.ok(block && new RegExp('function ' + name + '\\(').test(block[0]), 'shell.qml has ' + fn);
}

// ---- several files (another part of Arctic adds its own), and the plan's fields -----------------
const two = Menu.build([shippedFile, { version: 1, entries: {
    'capture.delay': { label: 'Screenshot in 5 seconds', icon: 'clock', run: ['arctic-screenshot', 'screen', '--delay', '5'], order: 5 },
    'capture.screens': { label: 'All screens', icon: 'camera', run: ['arctic-screenshot', 'screen', '--all'], when: { outputs: 2 } },
    'install.flatpak': { label: 'Flatpak', icon: 'package', shell: 'openGetApps', args: ['flatpak'] },
    'remove.web': { label: 'Web apps', icon: 'globe', shell: 'openGetApps', args: ['remove/web'], when: { live: false } },
    'learn.tour': { label: 'Desktop tour', icon: 'compass', shell: 'url', args: ['https://example.org/tour'] },
    'learn.bad': { label: 'Bad', icon: 'compass', shell: 'url', args: ['javascript:alert(1)'] },
    'learn.more': { label: 'More', icon: 'help', target: 'capture' },
    'learn.evil': { label: 'Evil', icon: 'help', sh: 'rm -rf ~' },
    'learn.evil2': { label: 'Evil', icon: 'help', run: 'rm -rf ~' },
    'capture.edit': { label: 'Edit', icon: 'edit', run: ['arctic-screenshot', 'area', '--edit'], when: { command: 'swappy', file: '/etc/x' } },
} }], '{"mine": {"label": "Mine", "icon": "user"}, "mine.x": {"label": "X", "icon": "user", "sh": "echo hi | wl-copy"}}');
const kids = parent => two.order.filter(id => Menu.parentOf(id) === parent);
assert.equal(kids('capture')[0], 'capture.delay', 'order puts a row first');
assert.ok(kids('capture').indexOf('capture.screens') > kids('capture').indexOf('capture.folder'), 'new rows after the shipped ones');
assert.deepEqual(plain(two.byId['install.flatpak'].run), ['arctic-shell-ipc', 'apps', 'source', 'flatpak']);
assert.equal(two.byId['install.flatpak'].ipc, 'apps source');
assert.deepEqual(plain(two.byId['remove.web'].run), ['arctic-shell-ipc', 'apps', 'remove']);
assert.equal(two.byId['remove.web'].when, 'installed');
assert.deepEqual(plain(two.byId['learn.tour'].run), ['xdg-open', 'https://example.org/tour']);
assert.equal(two.byId['learn.bad'].run, undefined, 'only https addresses');
assert.equal(two.byId['learn.more'].go, 'capture');
assert.equal(two.byId['learn.evil'].run, undefined, 'sh only from your own file');
assert.equal(two.byId['learn.evil2'].run, undefined, 'a run string neither');
assert.equal(two.byId['mine.x'].run, 'echo hi | wl-copy');
assert.deepEqual(plain(two.byId['capture.edit'].needs), ['arctic-screenshot', 'swappy']);
assert.match(two.byId['capture.edit'].test, /^test -e '\/etc\/x'$/);
assert.ok(two.order.indexOf('mine') > two.order.indexOf('system.poweroff'));
{
    const c = Menu.context(false, false);
    Object.values(two.byId).forEach(e => Menu.needsOf(e).forEach(n => Menu.readGuard(c, 'cmd\t' + n)));
    c.outputs = 1;
    assert.ok(!Menu.rows(two, 'capture', c, {}).some(r => r.id === 'capture.screens'), 'one screen: no "all screens"');
    c.outputs = 2;
    assert.ok(Menu.rows(two, 'capture', c, {}).some(r => r.id === 'capture.screens'));
    assert.equal(Menu.rows(two, 'learn', c, {}).find(r => r.id === 'learn.more').kind, 'link');
}
assert.deepEqual(plain(Menu.locate(two, 'apps.reminders_cancel')), { branch: 'apps', select: 'apps.reminders-cancel' });

// ---- merging your own file ------------------------------------------------------------------
const model = Menu.build(shipped, JSON.stringify({
    'update.firmware': { hidden: true },
    'capture.area': { label: 'Snip' },
    'mine': { label: 'Mine', icon: 'user' },
    'mine.notes': { label: 'Notes', icon: 'document', run: 'gnome-text-editor ~/notes.txt' },
    'Bad Id': { label: 'ignored' },
    'remove': { hidden: true },
}));
assert.ok(!model.byId['update.firmware']);
assert.ok(!model.byId['remove'] && !model.byId['remove.apps'], 'hiding a branch hides its rows');
assert.equal(model.byId['capture.area'].label, 'Snip');
assert.deepEqual(plain(model.byId['capture.area'].run), ['arctic-screenshot', 'area'], 'fields not given are kept');
assert.equal(model.order[model.order.length - 1], 'mine.notes', 'new rows come after the shipped ones');
assert.ok(!model.byId['Bad Id']);
// A broken file of yours is ignored, not fatal.
assert.equal(Menu.build(shipped, '{ not json').order.length, Object.keys(shipped).length);
// Comments: whole lines only (a URL's // stays).
assert.deepEqual(plain(Menu.parse('// hi\n{"a": {"label": "x", "run": ["xdg-open", "https://e.org"]}}')),
                 { a: { label: 'x', run: ['xdg-open', 'https://e.org'] } });

// ---- guards ---------------------------------------------------------------------------------
const base = Menu.build(shipped, '');
function ctxWith(opts) {
    const ctx = Menu.context(opts.live, opts.dark);
    (opts.cmds || []).forEach(c => Menu.readGuard(ctx, 'cmd\t' + c));
    (opts.lines || []).forEach(l => Menu.readGuard(ctx, l));
    return ctx;
}
const everything = Array.from(new Set(Object.values(shipped).flatMap(e => Menu.needsOf(e))));
const ids = (list) => list.map(r => r.id);

// Nothing known yet: nothing shows (not rows that may not work).
assert.deepEqual(ids(Menu.rows(base, '', Menu.context(false, false), {})), []);
// All commands present but no shell IPC: the IPC-only rows and Remove (IPC only) hide.
let ctx = ctxWith({ cmds: everything });
assert.deepEqual(ids(Menu.rows(base, '', ctx, {})), ['apps', 'learn', 'capture', 'toggle', 'style', 'setup', 'update', 'system']);
assert.ok(!ids(Menu.rows(base, 'apps', ctx, {})).includes('apps.emoji'));
// The shell's `quickshell ipc show` lines.
const show = ['target apps', '  function install(): void', '  function remove(): void', '  function source(name: string): void',
              'target launcher', '  function apps(): void', 'target emoji', '  function toggle(): void'];
ctx = ctxWith({ cmds: everything, lines: show.map(l => 'ipc\t' + l) });
assert.ok(ctx.ipc['apps remove'] && ctx.ipc['emoji toggle'] && ctx.ipc['launcher apps'] && !ctx.ipc['launcher remove']);
assert.deepEqual(ids(Menu.rows(base, 'remove', ctx, {})), ['remove.apps']);
assert.deepEqual(ids(Menu.rows(base, 'install', ctx, {})), ['install.apps', 'install.flathub', 'install.fedora', 'install.web', 'install.console']);
// A missing helper hides its row (other streams ship arctic-ocr, arctic-colorpick, …).
ctx = ctxWith({ cmds: everything.filter(c => c !== 'arctic-ocr' && c !== 'arctic-colorpick') });
assert.deepEqual(ids(Menu.rows(base, 'capture', ctx, {})),
                 ['capture.area', 'capture.window', 'capture.screen', 'capture.record', 'capture.folder']);
// A branch whose rows are all hidden hides too.
ctx = ctxWith({ cmds: everything.filter(c => !['arctic-theme', 'arctic-nightlight', 'arctic-keep-awake', 'arctic-dnd', 'arctic-motion'].includes(c)) });
assert.ok(!ids(Menu.rows(base, '', ctx, {})).includes('toggle'));
// Live session: no lock, log out or suspend; no update check.
ctx = ctxWith({ live: true, cmds: everything });
assert.deepEqual(ids(Menu.rows(base, 'system', ctx, {})), ['system.restart', 'system.poweroff']);
ctx = ctxWith({ live: false, cmds: everything });
assert.equal(Menu.rows(base, 'system', ctx, {}).length, 5);

// States: a switch for toggles, the label while on, "dark" from the theme.
ctx = ctxWith({ dark: true, cmds: everything, lines: [
    'state\ttoggle.nightlight\t{"ok": true, "on": true, "temperature": 4000}',
    'state\ttoggle.awake\t{"ok": false, "error": "Nope"}',
    'state\ttoggle.dnd\t{"text":" ","tooltip":"Do not disturb is on","class":"dnd"}',
    'state\ttoggle.motion\treduced',
    'state\tcapture.record\t{"ok": true, "recording": true}'] });
const toggles = {};
Menu.rows(base, 'toggle', ctx, {}).forEach(r => { toggles[r.id] = r.checked; });
assert.deepEqual(plain(toggles), { 'toggle.dark': true, 'toggle.nightlight': true, 'toggle.dnd': true, 'toggle.motion': true },
                 'unknown state (ok: false) shows no switch');
assert.ok(!('toggle.awake' in toggles) || toggles['toggle.awake'] === undefined);
assert.equal(Menu.rows(base, 'capture', ctx, {}).find(r => r.id === 'capture.record').label, 'Stop recording');
for (const [t, v] of [['off', false], ['{"ok":true,"active":false}', false], ['{"ok":true,"state":"on"}', true],
                      ['{"text":"","class":"on"}', false], ['garbage', undefined], ['', undefined], ['normal', false]])
    assert.strictEqual(Menu.stateOf(t), v, t);

// Providers: the Settings pages, and themes from `arctic-theme list --json`.
const pages = Search.parseSettings(fs.readFileSync(root + '../settings/SearchIndex.js', 'utf8')).pages;
ctx = ctxWith({ cmds: everything, lines: ['provider\tstyle.theme\t[{"name":"winter","label":"Winter","mode":"light","active":false},'
    + '{"name":"polar-night","label":"Polar night","mode":"dark","active":true}]'] });
const setup = Menu.rows(base, 'setup', ctx, { settingsPages: pages });
assert.equal(setup.length, pages.length + 1, 'the pages, then the branch\'s own rows');
assert.deepEqual(plain(setup[0].run), ['arctic-settings', pages[0].id]);
assert.equal(setup[setup.length - 1].id, 'setup.hooks');
const themes = Menu.rows(base, 'style.theme', ctx, {});
assert.deepEqual(themes.map(t => [t.label, t.current]), [['Winter', false], ['Polar night', true]]);
assert.deepEqual(plain(themes[0].run), ['arctic-theme', 'set', 'winter']);
// No pages (Settings not installed): only its own rows; none of those either, and Setup hides.
assert.deepEqual(ids(Menu.rows(base, 'setup', ctx, { settingsPages: [] })), ['setup.hooks']);
ctx.commands['arctic-hook'] = false;
assert.ok(!ids(Menu.rows(base, '', ctx, { settingsPages: [] })).includes('setup'));
ctx.commands['arctic-hook'] = true;

// ---- search, trail, locate --------------------------------------------------------------------
ctx = ctxWith({ cmds: everything, lines: show.map(l => 'ipc\t' + l) });
const found = Menu.search(base, '', 'screensh', ctx, { settingsPages: pages });
assert.ok(found.length >= 3 && found.every(r => r.kind !== 'branch'));
assert.equal(found[0].desc, 'Capture', 'a search result says where it is');
assert.equal(Menu.search(base, '', 'night', ctx, {})[0].id, 'toggle.nightlight');
assert.equal(Menu.search(base, 'capture', 'colour', ctx, {})[0].id, 'capture.color');
assert.equal(Menu.search(base, 'capture', 'night', ctx, {}).length, 0, 'search stays in the branch');
assert.ok(Menu.search(base, '', 'bluetooth', ctx, { settingsPages: pages }).some(r => r.id === 'setup.bluetooth'));
assert.deepEqual(plain(Menu.trail(base, 'style.theme')), ['Style', 'Theme']);
assert.deepEqual(plain(Menu.locate(base, 'capture')), { branch: 'capture', select: '' });
assert.deepEqual(plain(Menu.locate(base, 'capture.color')), { branch: 'capture', select: 'capture.color' });
assert.deepEqual(plain(Menu.locate(base, '')), { branch: '', select: '' });
assert.deepEqual(plain(Menu.locate(base, 'Style Theme')), { branch: 'style.theme', select: '' });
assert.equal(Menu.locate(base, 'nope'), null);

// ---- the guard script runs, and quotes what it's given ----------------------------------------
const tmp = fs.mkdtempSync(require('os').tmpdir() + '/menu-');
fs.writeFileSync(tmp + '/arctic-nightlight', '#!/bin/sh\necho \'{"ok": true,\n "on": false}\'\n', { mode: 0o755 });
fs.writeFileSync(tmp + '/arctic-theme', '#!/bin/sh\necho \'[{"name": "winter",\n"label": "Winter"}]\'\n', { mode: 0o755 });
const evil = Menu.build({ t: { label: 'T' }, 't.a': { label: 'A', run: ['arctic-nightlight', 'toggle'], state: ['arctic-nightlight', 'status', '--json'] },
                          't.b': { label: "B'; touch " + tmp + '/pwned; \'', run: ["x'; touch " + tmp + "/pwned; '"] },
                          't.c': { label: 'C', run: 'true', test: 'test -d /' }, 't.d': { label: 'D', run: 'true', test: 'false' },
                          'th': { label: 'Th', provider: 'themes', needs: ['arctic-theme'] } }, '');
const script = Menu.guardScript(evil, { shellDir: '/nonexistent' });
const out = execFileSync('sh', ['-c', script], { env: { PATH: tmp + ':/usr/bin:/bin' }, encoding: 'utf8' });
assert.ok(!fs.existsSync(tmp + '/pwned'), 'names are quoted');
const got = Menu.context(false, false);
out.split('\n').forEach(l => l && Menu.readGuard(got, l));
assert.ok(got.commands['arctic-nightlight'] && !got.commands["x'; touch " + tmp + "/pwned; '"]);
assert.strictEqual(got.states['t.a'], false);
assert.ok(got.tests['t.c'] && !got.tests['t.d']);
assert.deepEqual(plain(got.providers.th), [{ name: 'winter', label: 'Winter' }]);
fs.rmSync(tmp, { recursive: true });
console.log('Command menu checks passed.');
