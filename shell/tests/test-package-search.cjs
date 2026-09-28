// Completion for the Get apps console: node shell/tests/test-package-search.cjs
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const context = {};
vm.createContext(context);
vm.runInContext(fs.readFileSync(__dirname + '/../PackageSearch.js', 'utf8').replace('.pragma library', ''), context);
const { search, complete, context: ctx } = context;

const index = ['neovim', 'vim-enhanced', 'vim-minimal', 'fish', 'libuv', 'htop',
    'flathub:org.gimp.GIMP', 'flathub:org.mozilla.firefox', 'flathub:io.neovim.nvim', 'firefox'];

// Ranking: exact and prefix matches first, fuzzy last, case-insensitive.
assert.equal(search(index, 'nvim')[0], 'flathub:io.neovim.nvim');
assert.equal(search(index, 'nvim', 'dnf')[0], 'neovim');
assert.equal(search(index, 'vim', 'dnf')[0], 'vim-minimal');
assert.equal(search(index, 'FISH')[0], 'fish');
assert.equal(search(index, 'gimp')[0], 'flathub:org.gimp.GIMP');
assert.equal(search(index, 'firefox')[0], 'firefox');
assert.equal(search(index, 'flathub:fire')[0], 'flathub:org.mozilla.firefox');
assert.equal(search(index, 'nonexistentzzz').length, 0);
assert.equal(search(index, '').length, index.length);
assert.equal(search(index, '', 'dnf').length, 7);
assert.equal(search(index, '', 'flathub').length, 3);

// Which names are offered where.
assert.equal(ctx('neo', 3).allowed, true);
assert.equal(ctx('neo', 3).source, 'all');
assert.equal(ctx('dnf', 3).allowed, false);
assert.equal(ctx('dnf ins', 7).allowed, false);                 // typing the verb
assert.equal(ctx('dnf install', 11).source, 'dnf');             // names for the next word
assert.equal(ctx('dnf install', 11).prefix, ' ');
assert.equal(ctx('sudo dnf install ne', 19).source, 'dnf');
assert.equal(ctx('dnf install --refresh ne', 24).source, 'dnf');
assert.equal(ctx('dnf install -', 13).allowed, false);          // options aren't names
assert.equal(ctx('dnf search edi', 14).allowed, false);         // search takes words, not names
assert.equal(ctx('flatpak install flathub gi', 26).source, 'flathub');
assert.equal(ctx('flatpak install', 15).source, 'flathub');
assert.equal(ctx('flatpak install flathub', 23).allowed, false);
assert.equal(ctx('htop neo', 8).source, 'all');

// Completion replaces the word under the cursor.
assert.equal(complete('dnf install nvim', 16, 'neovim').text, 'dnf install neovim');
assert.equal(complete('dnf install', 11, 'htop').text, 'dnf install htop');
assert.equal(complete('dnf install nvim fish', 14, 'neovim').text, 'dnf install neovim fish');
assert.equal(complete('gim', 3, 'flathub:org.gimp.GIMP').text, 'flathub:org.gimp.GIMP');
assert.equal(complete('flatpak install flathub gim', 27, 'flathub:org.gimp.GIMP').text, 'flatpak install flathub org.gimp.GIMP');
assert.equal(complete('flatpak install flathub gim', 27, 'flathub:org.gimp.GIMP').cursor, 37);
console.log('Package search and command completion checks passed.');
// A prepared index gives the same answers as a plain list.
const prepared = context.prepare(index);
for (const q of ['nvim', 'vim', 'gimp', 'fire', '']) {
    assert.deepEqual(Array.from(search(prepared, q, 'all')), Array.from(search(index, q, 'all')), q);
}
console.log('Prepared index checks passed.');

// The Flathub and Fedora pages: items with names, summaries and keywords.
const { prepareItems, searchItems } = context;
const items = [
    { id: 'gimp-help', name: 'gimp-help', summary: 'Help files for GIMP' },
    { id: 'org.gimp.GIMP', name: 'GIMP', summary: 'Create images and edit photographs', keywords: ['paint'] },
    { id: 'org.inkscape.Inkscape', name: 'Inkscape', summary: 'Vector graphics editor', keywords: ['svg', 'drawing'] },
    { id: 'org.kde.krita', name: 'Krita', summary: 'Digital painting' },
    { id: 'io.neovim.nvim', name: 'Neovim', summary: 'Vim-fork focused on extensibility' },
];
const ids = (q, limit) => Array.from(searchItems(prepareItems(items), q, limit)).map(i => i.id);
assert.equal(ids('gimp')[0], 'org.gimp.GIMP');                        // the display name beats an id
assert.deepEqual(ids('gimp'), ['org.gimp.GIMP', 'gimp-help']);        // not the summary "Help files for GIMP" twice
assert.equal(ids('svg')[0], 'org.inkscape.Inkscape');                  // keywords
assert.equal(ids('nvim')[0], 'io.neovim.nvim');                        // the last part of the id
assert.deepEqual(ids('photographs'), ['org.gimp.GIMP']);               // summaries when little else matches
assert.deepEqual(ids('krt'), ['org.kde.krita']);                       // fuzzy
assert.equal(ids('').length, items.length);
assert.equal(ids('', 2).length, 2);
assert.deepEqual(ids('zzzz'), []);
assert.deepEqual(Array.from(searchItems(items, 'gimp')).map(i => i.id), ids('gimp'));   // an unprepared list works too
// Summaries don't crowd out stronger matches once there are enough of them.
assert.deepEqual(ids('paint', 1), ['org.gimp.GIMP']);
// ~70,000 packages answer in time for each keystroke.
const many = [];
for (let i = 0; i < 70000; i++) many.push({ id: 'package-' + i, name: 'package-' + i, summary: 'A package number ' + i });
many.push({ id: 'neovim', name: 'neovim', summary: 'Vim-fork focused on extensibility' });
const big = prepareItems(many);
const started = Date.now();
assert.equal(searchItems(big, 'neovim', 200)[0].id, 'neovim');
searchItems(big, 'package-69', 200);
const took = Date.now() - started;
// (a loose bound: CI machines are shared; a desktop answers in tens of milliseconds)
assert.ok(took < 3000, 'searching 70k items took ' + took + ' ms');
console.log('Item search checks passed (' + took + ' ms for two searches over 70k items).');
