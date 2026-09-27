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
