// Get apps' page logic: node shell/tests/test-getapps.cjs
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const context = {};
vm.createContext(context);
vm.runInContext(fs.readFileSync(__dirname + '/../getapps/GetApps.js', 'utf8').replace('.pragma library', ''), context);
const G = context;
const plain = value => JSON.parse(JSON.stringify(value));

// The chooser's cards and their digits.
const pages = state => G.cards(state).map(c => c.page + c.digit).join(' ');
assert.equal(pages({ webapp: true, flathub: true }), 'flatpak1 dnf2 web3 terminal4 remove5 console6');
assert.equal(pages({ webapp: false }), 'flatpak1 dnf2 terminal3 remove4 console5');   // no engine: no Web apps
assert.equal(pages({ webapp: true, live: true }), 'flatpak1 dnf2 web3 terminal4 console5');   // live USB: no Remove apps
assert.equal(G.cards({ flathub: false })[0].status, 'Flathub isn’t set up yet');
assert.equal(G.cards({ flathub: true })[0].status, 'No password needed');
assert.equal(G.cards({})[1].glyph, 'layers');

// Page names (IPC `apps open <page>`, `apps source <name>`).
assert.deepEqual(plain(G.parsePage('remove/dnf')), { page: 'remove', tab: 'dnf' });
assert.deepEqual(plain(G.parsePage('remove/fedora')), { page: 'remove', tab: 'dnf' });
assert.deepEqual(plain(G.parsePage('remove/snap')), { page: 'remove', tab: '' });
assert.deepEqual(plain(G.parsePage('flathub')), { page: 'flatpak', tab: '' });
assert.deepEqual(plain(G.parsePage('fedora')), { page: 'dnf', tab: '' });
assert.deepEqual(plain(G.parsePage('dnf/all')), { page: 'dnf', tab: 'all' });
assert.deepEqual(plain(G.parsePage('fedora/apps')), { page: 'dnf', tab: 'apps' });
assert.deepEqual(plain(G.parsePage('flatpak/all')), { page: 'flatpak', tab: '' });
assert.deepEqual(plain(G.parsePage('Console')), { page: 'console', tab: '' });
assert.deepEqual(plain(G.parsePage('nonsense')), { page: 'choose', tab: '' });
assert.deepEqual(plain(G.parsePage('')), { page: 'choose', tab: '' });
assert.deepEqual(plain(G.parsePage(undefined)), { page: 'choose', tab: '' });

// Esc goes back one step at a time.
for (const sheet of [false, true]) for (const field of [false, true]) for (const page of ['choose', 'flatpak', 'remove']) {
    const step = G.backStep({ sheet: sheet, field: field, page: page });
    const want = sheet ? 'sheet' : field ? 'field' : page !== 'choose' ? 'page' : 'leave';
    assert.equal(step, want, JSON.stringify({ sheet, field, page }));
}

// Row states: jobs first, then what is installed.
const installed = { flatpak: { 'org.gimp.GIMP': 'system' }, dnf: { htop: true } };
const gimp = { id: 'org.gimp.GIMP' }, krita = { id: 'org.kde.krita' };
assert.equal(G.rowState(gimp, 'flatpak', installed, []), 'installed');
assert.equal(G.rowState(krita, 'flatpak', installed, []), 'install');
assert.equal(G.rowState({ id: 'htop.desktop', pkg: 'htop' }, 'dnf', installed, []), 'installed');
assert.equal(G.rowState(krita, 'flatpak', installed, [{ kind: 'install', source: 'flatpak', ids: ['org.kde.krita'], phase: 'waiting' }]), 'waiting');
assert.equal(G.rowState(krita, 'flatpak', installed, [{ kind: 'install', source: 'flatpak', ids: ['org.kde.krita'], phase: 'running' }]), 'running');
assert.equal(G.rowState(krita, 'flatpak', installed, [{ kind: 'install', source: 'flatpak', ids: ['org.kde.krita'], phase: 'failed' }]), 'failed');
assert.equal(G.rowState(krita, 'flatpak', installed, [{ kind: 'install', source: 'flatpak', ids: ['org.kde.krita'], phase: 'failed' },
                                                      { kind: 'install', source: 'flatpak', ids: ['org.kde.krita'], phase: 'running' }]), 'running');
assert.equal(G.rowState(krita, 'dnf', installed, [{ kind: 'install', source: 'flatpak', ids: ['org.kde.krita'], phase: 'running' }]), 'install');

// Words.
assert.equal(G.jobLabel({ kind: 'install', name: 'GIMP', phase: 'running' }), 'Installing GIMP');
assert.equal(G.jobLabel({ kind: 'install', name: 'GIMP', phase: 'done' }), 'Installed GIMP');
assert.equal(G.jobLabel({ kind: 'remove', ids: ['gimp'], phase: 'waiting' }), 'Removing gimp');
assert.equal(G.jobLabel({ kind: 'add-remote', phase: 'running' }), 'Adding Flathub');
assert.equal(G.jobLabel(null), '');
assert.equal(G.repoLabel('fedora'), 'Fedora');
assert.equal(G.repoLabel('updates'), 'Fedora');
assert.equal(G.repoLabel('rpmfusion-free-updates'), 'RPM Fusion');
assert.equal(G.repoLabel('copr:copr.fedorainfracloud.org:user:proj'), 'COPR');
assert.equal(G.repoLabel('arctic'), 'Arctic Linux');
assert.equal(G.repoLabel('@System'), '');
assert.equal(G.sizeText(201326592), '201 MB');
assert.equal(G.sizeText(1048576), '1 MB');
assert.equal(G.sizeText(1500), '1.5 kB');
assert.equal(G.sizeText(12), '12 B');
assert.equal(G.sizeText(null), '');
assert.equal(G.sizeText(undefined), '');
assert.equal(G.removeLine({ version: '3.0.4', origin: 'flathub', size_text: '412.3 MB', installation: 'system' }, 'flatpak'),
             '3.0.4 · Flathub · 412.3 MB · For everyone');
assert.equal(G.removeLine({ installation: 'user', origin: 'flathub' }, 'flatpak'), 'Flathub · Only you');
assert.equal(G.removeLine({ package: 'gimp', repo_label: 'Fedora', install_bytes: 120000000, added: 'you' }, 'dnf'),
             'gimp · Fedora · 120 MB · You added it');
assert.equal(G.removeLine({ host: 'music.youtube.com', runtime_name: 'Arctic', running: true }, 'web'), 'music.youtube.com · Arctic · Running');
assert.equal(G.removeLine({ command: 'btop', window: 'float' }, 'terminal'), 'btop · floating window');
assert.equal(G.filterRows([{ name: 'GIMP' }, { name: 'Htop', package: 'htop' }], 'ht').length, 1);
assert.equal(G.filterRows([{ name: 'GIMP' }], '').length, 1);
console.log('Get apps page logic checks passed.');
