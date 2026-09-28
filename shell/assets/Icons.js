.pragma library
.import "design-data.js" as Data

// SVG builders for the design's line icons, the fox mark and app tiles.
// Images are data: URLs, so each icon is drawn in exactly the token colour asked for.

function hex(c) {
    // QML colours stringify as #rrggbb or #aarrggbb; SVG wants #rrggbb.
    const s = String(c);
    return s.length === 9 ? '#' + s.slice(3) : s;
}

function url(svg) {
    return 'data:image/svg+xml;utf8,' + encodeURIComponent(svg);
}

function has(name) {
    return Object.prototype.hasOwnProperty.call(Data.ICONS, name);
}

// A 24-grid line icon: 1.75 stroke, round caps and joins (brand book "Iconography").
function icon(name, color, stroke) {
    const ink = hex(color);
    const body = (Data.ICONS[name] || Data.ICONS.help).replace(/currentColor/g, ink);
    return url('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="'
        + ink + '" stroke-width="' + (stroke || 1.75) + '" stroke-linecap="round" stroke-linejoin="round">' + body + '</svg>');
}

// The fox mark on its 48-unit grid (design bundle mark()). At 20px and below the -16 drawing
// is used: no eyes and a wider head/tail gap. `eye` colours the eyes; empty = cut-outs.
const FOX_HEAD = 'M14 6.5 L20 13 H28 L34 6.5 L38.5 20.5 L24 31.5 L9.5 20.5 Z';
const FOX_HEAD_SMALL = 'M13.5 7 L20 13.5 H28 L34.5 7 L38.5 21 L24 31 L9.5 21 Z';
const FOX_TAIL = 'M9.5 38.5 C 15 43.5, 27 44, 34.5 39.5 C 41.5 35, 44.5 26, 41 16.5';
const FOX_FLUFF = 'M27 41.2 C 33 39.5, 39 34.5, 40.6 27';
const FOX_EYES = [[18.2, 20.2, 12], [29.8, 20.2, -12]];

function mark(size, color, eye) {
    const ink = hex(color);
    const small = size <= 20;
    const gap = small ? 16 : 14;
    let cut = '<path d="' + FOX_TAIL + '" fill="none" stroke="#000" stroke-width="' + gap + '" stroke-linecap="round"/>';
    if (!small) cut += '<path d="' + FOX_FLUFF + '" fill="none" stroke="#000" stroke-width="15" stroke-linecap="round"/>';
    let eyesMask = '', eyesFill = '';
    if (!small) {
        FOX_EYES.forEach(function (e) {
            const el = '<ellipse cx="' + e[0] + '" cy="' + e[1] + '" rx="2" ry="1.35" transform="rotate(' + e[2] + ' ' + e[0] + ' ' + e[1] + ')" fill="';
            if (eye) eyesFill += el + hex(eye) + '"/>'; else eyesMask += el + '#000"/>';
        });
    }
    const head = small ? FOX_HEAD_SMALL : FOX_HEAD;
    return url('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="48" height="48">'
        + '<defs><mask id="h" maskUnits="userSpaceOnUse" x="0" y="0" width="48" height="48"><rect width="48" height="48" fill="#fff"/>' + cut + eyesMask + '</mask></defs>'
        + '<path mask="url(#h)" d="' + head + '" fill="' + ink + '" stroke="' + ink + '" stroke-width="5" stroke-linejoin="round"/>'
        + '<path d="' + FOX_TAIL + '" fill="none" stroke="' + ink + '" stroke-width="' + (small ? 10 : 9) + '" stroke-linecap="round"/>'
        + (small ? '' : '<path d="' + FOX_FLUFF + '" fill="none" stroke="' + ink + '" stroke-width="10.5" stroke-linecap="round"/>')
        + eyesFill + '</svg>');
}

// ---- app tiles --------------------------------------------------------------------------
// Installed apps that match a design tile get its calm, uniform tile in the launcher.
const TILE_MATCH = [
    ['installer', /arcticlinux\.installer|arctic-install/],
    ['zen', /zen[_-]?browser|^zen\b/], ['firefox', /firefox/], ['chromium', /chromium/],
    ['zed', /dev\.zed|^zed\b|zeditor/], ['vscodium', /codium/], ['neovim', /nvim|neovim/],
    ['helix', /helix/], ['kitty', /kitty/], ['alacritty', /alacritty/], ['foot', /^foot|\.foot\b|footclient/],
    ['yazi', /yazi/], ['thunar', /thunar/], ['nautilus', /nautilus/],
    ['collabora', /collabora/], ['libreoffice', /libreoffice/], ['onlyoffice', /onlyoffice/],
    ['vlc', /vlc/], ['mpv', /^mpv|io\.mpv/], ['celluloid', /celluloid/],
    ['steam', /steam/], ['gimp', /gimp/], ['inkscape', /inkscape/], ['signal', /signal/],
    ['obs', /obsproject|^obs\b|com\.obs/], ['settings', /settings|control-center/]
];

function tileFor(id, name) {
    const key = (String(id || '') + ' ' + String(name || '')).toLowerCase();
    // Web apps (arctic-webapp) keep their own icon: a web app named "Signal" isn't Signal.
    if (key.startsWith('org.arcticlinux.webapp.')) return '';
    for (let i = 0; i < TILE_MATCH.length; i++) if (TILE_MATCH[i][1].test(key)) return TILE_MATCH[i][0];
    return '';
}

function app(id) {
    return Data.APPS[id] || null;
}

function tint(category) {
    return Data.TINTS[category] || 'surfaceSunken';
}
