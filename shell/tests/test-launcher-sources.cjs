// The launcher's other sources (settings, windows, files, web, units, frecency):
// node shell/tests/test-launcher-sources.cjs
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const root = __dirname + '/../';
const c = {};
vm.createContext(c);
vm.runInContext(fs.readFileSync(root + 'LauncherSearch.js', 'utf8').replace('.pragma library', ''), c);
const S = c;
const plain = x => JSON.parse(JSON.stringify(x));

// ---- Settings' own index, read without running it --------------------------------------------
const indexText = fs.readFileSync(root + '../settings/SearchIndex.js', 'utf8');
const parsed = S.parseSettings(indexText);
const real = {};
vm.createContext(real);
vm.runInContext(indexText.replace('.pragma library', '').replace(/^var (PAGES|ENTRIES) =/mg, 'globalThis.$1 ='), real);
// Same as evaluating it: if SearchIndex.js changes shape, this fails rather than the launcher.
assert.deepEqual(parsed.pages.map(p => [p.id, p.title, p.icon, p.words]), real.PAGES.map(p => [p.id, p.title, p.icon, p.words]));
assert.deepEqual(parsed.entries.map(e => [e.page, e.key, e.title, e.words]), plain(real.ENTRIES));
assert.deepEqual(plain(S.parseSettings('nothing here')), { pages: [], entries: [] });

const settings = S.settingsCandidates(parsed.pages, parsed.entries);
assert.equal(settings.length, parsed.pages.length + parsed.entries.length);
const motion = settings.find(s => s.key === 'appearance.motion');
assert.equal(motion.desc, 'Settings › Appearance');
assert.equal(motion.id, 'setting:appearance/appearance.motion');
// Ranked with apps: an app of the same name stays first; "dark mode" finds the setting.
const apps = [{ kind: 'app', name: 'Network Manager', keywords: 'wifi', id: 'app:nm' }];
const top = q => S.rank(apps.concat(settings), q)[0];
assert.equal(top('network').kind, 'app');
assert.equal(top('reduce motion').key, 'appearance.motion');
assert.equal(top('wallpaper').key, 'appearance.wallpaper');
assert.equal(S.rank(settings, 'bluetooth')[0].page, 'bluetooth');

// ---- windows ----------------------------------------------------------------------------------
const wins = S.windowCandidates([{ title: 'Inbox — Mail', appId: 'org.gnome.Evolution', appName: 'Evolution', ref: 1 },
                                  { title: '', appId: '', ref: 2 }]);
assert.equal(wins.length, 1);
assert.equal(wins[0].desc, 'Open window · Evolution');
assert.equal(S.rank(wins, 'inbox')[0].ref, 1);
assert.equal(S.rank(wins, 'evolution')[0].ref, 1, 'found by its app too');

// ---- web ------------------------------------------------------------------------------------
assert.equal(S.mode('? fedora 44').mode, 'web');
assert.equal(S.mode('? fedora 44').text, 'fedora 44');
assert.equal(S.webSearch('duckduckgo', 'a&b c').url, 'https://duckduckgo.com/?q=a%26b%20c');
assert.equal(S.webSearch('nope', 'x').url, 'https://duckduckgo.com/?q=x', 'unknown engine: the default');
assert.equal(S.webSearch('https://search.example.org/?s=%s', 'x').url, 'https://search.example.org/?s=x');
assert.equal(S.webSearch('javascript:alert(%s)', 'x').url, 'https://duckduckgo.com/?q=x', 'only https addresses');
assert.equal(S.webSearch('google', '  '), null);

// ---- files (fd output) -------------------------------------------------------------------------
const files = S.fileRows('/home/me/Documents/report.pdf\n/home/me/Documents/Reports/\nrelative\n/etc/fstab\n', '/home/me');
assert.deepEqual(files.map(f => [f.name, f.desc, f.glyph]),
                 [['report.pdf', '~/Documents', 'file'], ['Reports', '~/Documents', 'folder'], ['fstab', '/etc', 'file']]);
assert.equal(files[1].path, '/home/me/Documents/Reports');

// ---- units --------------------------------------------------------------------------------------
for (const yes of ['10 km to mi', '72 °F to °C', '1.5 kg to lb', '100 usd to eur', '3h to min']) assert.ok(S.looksLikeConversion(yes), yes);
for (const no of ['zen browser', '10', 'km to mi', 'set up 2 monitors', '-rf / to x', '1.5 kg in lb']) assert.ok(!S.looksLikeConversion(no), no);

// ---- frecency -----------------------------------------------------------------------------------
const now = Date.UTC(2026, 8, 28);
let stats = {};
for (let i = 0; i < 5; i++) stats = S.remember(stats, 'app:zen', now);
assert.equal(stats['app:zen'].n, 5);
assert.ok(S.frecency(stats, 'app:zen', now) > 0 && S.frecency(stats, 'app:zen', now) <= 300);
assert.ok(S.frecency(stats, 'app:zen', now + 40 * 86400000) < S.frecency(stats, 'app:zen', now), 'fades');
assert.equal(S.frecency(stats, 'app:other', now), 0);
assert.equal(S.frecency(null, 'x', now), 0);
// What you open often wins a tie ("ze" matches both by name prefix).
const two = [{ name: 'Zed', id: 'app:zed' }, { name: 'Zen Browser', id: 'app:zen' }];
assert.equal(S.rank(two, 'ze')[0].name, 'Zed');
assert.equal(S.rank(two, 'ze', item => S.frecency(stats, item.id, now))[0].name, 'Zen Browser');
// Kept small: the oldest go first.
let many = {};
for (let i = 0; i < 12; i++) many = S.remember(many, 'k' + i, now + i, 10);
assert.equal(Object.keys(many).length, 10);
assert.ok(!many.k0 && !many.k1 && many.k11);
console.log('Launcher sources checks passed.');
