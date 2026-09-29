.pragma library
// Get apps' pure logic (tests: tests/test-getapps.cjs): which cards the chooser shows, page
// names, the Esc ladder, row states and the words jobs and sizes are shown with.

const PAGES = ['choose', 'flatpak', 'dnf', 'web', 'terminal', 'remove', 'console'];
const ALIASES = { flathub: 'flatpak', fedora: 'dnf', webapp: 'web', 'web-apps': 'web', install: 'choose', home: 'choose' };
const TABS = ['flatpak', 'dnf', 'web', 'terminal'];

// The chooser's cards, in order; the digit keys follow the visible ones.
// state: {live, webapp (engine present), flatpak (command present), flathub (a remote set up)}
function cards(state) {
    const s = state || {};
    const list = [
        { page: 'flatpak', title: 'Flathub apps', big: true, tile: 'flathub', glyph: 'package',
          desc: 'Desktop apps from Flathub, each in its own sandbox.',
          status: s.flatpak === false ? 'Flatpak isn’t installed' : s.flathub === false ? 'Flathub isn’t set up yet' : 'No password needed' },
        { page: 'dnf', title: 'Fedora packages', big: true, glyph: 'layers', tint: 'surfaceSunken',
          desc: 'Apps and tools from Fedora and RPM Fusion.', status: 'Asks for your password' },
        { page: 'web', title: 'Web apps', big: true, glyph: 'globe', tint: 'infoSoft',
          desc: 'Any website as an app, with its own window and sign-in.', status: 'Needs the internet' },
        { page: 'terminal', title: 'Terminal apps', big: false, glyph: 'prompt', tint: 'slate900',
          desc: 'Put a terminal program like btop in the launcher.', short: 'Terminal programs like btop in the launcher' },
        { page: 'remove', title: 'Remove apps', big: false, glyph: 'trash', tint: 'surfaceSunken',
          desc: 'Uninstall Flatpak apps, Fedora packages and web apps.', short: 'Flatpak, Fedora and web apps' },
        { page: 'console', title: 'Console', big: false, glyph: 'terminal', tint: 'surfaceSunken',
          desc: 'Type dnf and flatpak commands.', short: 'Type dnf and flatpak commands' },
    ];
    return list.filter(c => !(c.page === 'web' && !s.webapp) && !(c.page === 'remove' && s.live))
               .map((c, i) => Object.assign({ digit: i + 1 }, c));
}

// "remove/dnf" -> {page: 'remove', tab: 'dnf'}, "dnf/all" -> {page: 'dnf', tab: 'all'} (every
// package, not only apps); anything unknown opens the chooser.
function parsePage(text) {
    const parts = String(text || '').trim().toLowerCase().split('/');
    let page = ALIASES[parts[0]] || parts[0];
    if (PAGES.indexOf(page) < 0) page = 'choose';
    let tab = '';
    if (page === 'remove' && parts.length > 1) {
        const t = ALIASES[parts[1]] || parts[1];
        if (TABS.indexOf(t) >= 0) tab = t;
    }
    if (page === 'dnf' && (parts[1] === 'apps' || parts[1] === 'all')) tab = parts[1];
    return { page: page, tab: tab };
}

// What Esc does now: close a sheet, clear the field, go back to the chooser, or leave Get apps.
// state: {sheet (a sheet or the details panel is open), field (the page's field has text), page}
function backStep(state) {
    const s = state || {};
    if (s.sheet) return 'sheet';
    if (s.field) return 'field';
    if (s.page && s.page !== 'choose') return 'page';
    return 'leave';
}

// A result row's state: 'installed', 'waiting', 'running', 'failed' or 'install'.
// installed: {flatpak: {id: installation}, dnf: {name: true}}; jobs: AppsService.jobs.
function rowState(item, source, installed, jobs) {
    const id = source === 'dnf' ? (item.pkg || item.id) : item.id;
    const list = jobs || [];
    for (let i = list.length - 1; i >= 0; i--) {
        const job = list[i];
        if (job.kind !== 'install' || job.source !== source || (job.ids || []).indexOf(id) < 0) continue;
        if (job.phase === 'waiting' || job.phase === 'running') return job.phase;
        if (job.phase === 'failed') return 'failed';
        break;
    }
    const table = (installed || {})[source] || {};
    return Object.prototype.hasOwnProperty.call(table, id) ? 'installed' : 'install';
}

// "Installing GIMP", "Removing GIMP", "Adding Flathub", "Installed GIMP" …
function jobLabel(job) {
    if (!job) return '';
    const name = job.name || (job.ids || []).join(', ');
    const done = job.phase === 'done';
    switch (job.kind) {
    case 'install': return (done ? 'Installed ' : 'Installing ') + name;
    case 'remove': return (done ? 'Removed ' : 'Removing ') + name;
    case 'add-remote': return done ? 'Added Flathub' : 'Adding Flathub';
    case 'console': return 'Running a Console command';
    }
    return name;
}

function repoLabel(repo) {
    const r = String(repo || '');
    if (r === 'fedora' || r === 'updates' || r.startsWith('fedora-') || r.startsWith('updates-')) return 'Fedora';
    if (r.startsWith('rpmfusion-')) return 'RPM Fusion';
    if (r.startsWith('copr:')) return 'COPR';
    if (r === 'arctic' || r.startsWith('arctic-')) return 'Arctic Linux';
    if (r === '@System' || r === '<unknown>') return '';
    return r;
}

// 201326592 -> "201 MB" (decimal units, as dnf and flatpak print them).
function sizeText(bytes) {
    const n = Number(bytes);
    if (bytes === null || bytes === undefined || !isFinite(n) || n < 0) return '';
    const units = ['B', 'kB', 'MB', 'GB', 'TB'];
    let value = n, unit = 0;
    while (value >= 1000 && unit < units.length - 1) { value /= 1000; unit++; }
    const text = unit === 0 || value >= 100 ? String(Math.round(value)) : value.toFixed(1).replace(/\.0$/, '');
    return text + ' ' + units[unit];
}

// Remove apps' second line for a row, per source.
function removeLine(row, source) {
    const r = row || {};
    const parts = [];
    if (source === 'flatpak') {
        if (r.version) parts.push(r.version);
        parts.push(r.origin === 'flathub' ? 'Flathub' : (r.origin || ''));
        if (r.size_text) parts.push(r.size_text);
        parts.push(r.installation === 'user' ? 'Only you' : 'For everyone');
    } else if (source === 'dnf') {
        parts.push(r.package || '');
        if (r.repo_label) parts.push(r.repo_label);
        const size = sizeText(r.install_bytes);
        if (size) parts.push(size);
        if (r.added === 'you') parts.push('You added it');
        else if (r.added === 'arctic') parts.push('Came with Arctic Linux');
    } else if (source === 'web') {
        parts.push(r.host || r.url || '');
        if (r.runtime_name) parts.push(r.runtime_name);
        if (r.running) parts.push('Running');
        const problem = { 'no-desktop-file': 'Launcher entry missing', 'no-registry': 'Record missing',
                          'runtime-missing': 'Runtime missing' }[r.problem || ''];
        if (problem) parts.push(problem);
    } else if (source === 'terminal') {
        parts.push(r.command || '');
        parts.push(r.window === 'tile' ? 'tiled window' : 'floating window');
    }
    return parts.filter(p => p).join(' · ');
}

// Rows whose name, id or second line contain the filter text.
function filterRows(rows, text) {
    const q = String(text || '').trim().toLowerCase();
    if (!q) return rows || [];
    return (rows || []).filter(r => [r.name, r.id, r.package, r.host, r.command].some(v => v && String(v).toLowerCase().indexOf(q) >= 0));
}
