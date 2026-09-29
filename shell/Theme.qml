pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import "assets/theme-defaults.js" as Defaults

// The Arctic design tokens for the active theme (Winter, Polar night, the one made from your
// wallpaper, or a theme of your own).
//
// Read from ~/.config/arctic/current/theme.json, which `arctic-theme` switches, falling back to
// /usr/share/arctic/themes/polar-night/theme.json and then to the built-in Polar night.
// Every theme.json is rendered by the theme engine (design/themegen, arctic-themegen) from a
// palette; the static ones from design/tokens.json.
// `arctic-theme` also writes ~/.config/arctic/theme and calls `arctic-shell-ipc shell reload`,
// so the whole shell restyles live.
Singleton {
    id: theme

    property var tokens: Defaults.THEME
    readonly property var c: tokens.colors
    readonly property bool dark: tokens.dark
    readonly property string themeId: tokens.id
    readonly property string themeName: tokens.name
    // High contrast (Settings > Accessibility): the theme is its high-contrast take (arctic-theme
    // contrast on), and lines and focus rings get heavier too.
    readonly property bool highContrast: tokens.contrast === 'high'
    readonly property int lineWidth: highContrast ? 2 : 1

    // ---- colour (semantic tokens) -------------------------------------------------------
    readonly property color ground: c.ground
    readonly property color surface: c.surface
    readonly property color surfaceRaised: c.surfaceRaised
    readonly property color surfaceSunken: c.surfaceSunken
    readonly property color frost: c.frost
    readonly property color scrim: c.scrim
    readonly property color line: c.line
    readonly property color lineStrong: c.lineStrong
    readonly property color ink: c.ink
    readonly property color inkMuted: c.inkMuted
    readonly property color inkSubtle: c.inkSubtle
    readonly property color inkDisabled: c.inkDisabled
    readonly property color inkInverse: c.inkInverse
    readonly property color accent: c.accent
    readonly property color accentHover: c.accentHover
    readonly property color accentPressed: c.accentPressed
    readonly property color onAccent: c.onAccent
    readonly property color accentText: c.accentText
    readonly property color accentSoft: c.accentSoft
    readonly property color accentEdge: c.accentEdge
    readonly property color focus: c.focus
    readonly property color selection: c.selection
    readonly property color warm: c.warm
    readonly property color warmSoft: c.warmSoft
    readonly property color success: c.success
    readonly property color successSoft: c.successSoft
    readonly property color warning: c.warning
    readonly property color warningSoft: c.warningSoft
    readonly property color error: c.error
    readonly property color errorSoft: c.errorSoft
    readonly property color onError: c.onError
    readonly property color info: c.info
    readonly property color infoSoft: c.infoSoft
    readonly property color snow100: c.snow100
    readonly property color slate900: c.slate900
    function token(name) { return c[name] || c.ink; }
    // shadow-sm / shadow-md, single-layer approximations (as settings/Theme.qml; ShadowLayers.qml)
    readonly property color shadowSm: dark ? '#66000000' : '#1f12171e'
    readonly property color shadowMd: dark ? '#b3000000' : '#2612171e'

    // ---- type -----------------------------------------------------------------------------
    // Figtree for the interface, JetBrains Mono for values that benefit from it. Some Figtree
    // builds register as "Figtree Light"; use whichever family is really installed.
    readonly property var families: Qt.fontFamilies()
    readonly property string fontSans: pick([tokens.fonts.sans, tokens.fonts.sans + ' Light', 'Noto Sans'])
    // The code font you chose (arctic-font writes shell.json "monoFont"), when it's installed.
    readonly property string fontMono: pick([Session.settings.monoFont || '', tokens.fonts.mono, 'JetBrains Mono NL', 'Noto Sans Mono', 'monospace'])
    function pick(list) {
        for (let i = 0; i < list.length; i++) if (families.indexOf(list[i]) >= 0) return list[i];
        return list[list.length - 1];
    }
    readonly property var type: tokens.type

    // ---- space, shape, size -------------------------------------------------------------
    readonly property int space1: 4
    readonly property int space2: 8
    readonly property int space3: 12
    readonly property int space4: 16
    readonly property int space5: 20
    readonly property int space6: 24
    readonly property int space8: 32
    readonly property int radiusXs: tokens.radius.radiusXs
    readonly property int radiusSm: tokens.radius.radiusSm
    readonly property int radiusMd: tokens.radius.radiusMd
    readonly property int radiusLg: tokens.radius.radiusLg
    readonly property int radiusXl: tokens.radius.radiusXl
    readonly property int barHeight: tokens.size.barHeight
    // Where the shell's surfaces start: under the bar, or at the screen's top edge while the bar
    // is hidden (Super + Shift + Space).
    readonly property int topInset: Session.barHidden ? 0 : barHeight
    readonly property int controlSm: tokens.size.controlSm
    readonly property int controlMd: tokens.size.controlMd
    readonly property int controlLg: tokens.size.controlLg
    readonly property int targetMin: tokens.size.targetMin
    readonly property int focusWidth: highContrast ? Math.max(3, tokens.border.borderFocus) : tokens.border.borderFocus

    // Screen frame (the shell's rounded surround). Its inner radius is concentric with tiled
    // window corners: window radius + Mango's 8px gap.
    readonly property int frameWidth: Session.frame ? 6 : 0
    readonly property int frameRadius: radiusMd + space2

    // ---- motion ---------------------------------------------------------------------------
    // Reduced motion: movement becomes instant, opacity fades stay at duration-fast.
    readonly property bool reduceMotion: Session.reduceMotion
    readonly property int durationFast: tokens.duration.durationFast
    readonly property int durationBase: reduceMotion ? 0 : tokens.duration.durationBase
    readonly property int durationSlow: reduceMotion ? 0 : tokens.duration.durationSlow
    readonly property int fadeBase: reduceMotion ? durationFast : tokens.duration.durationBase
    readonly property int fadeSlow: reduceMotion ? durationFast : tokens.duration.durationSlow
    readonly property var easeStandard: tokens.easing.easeStandard.concat([1, 1])
    readonly property var easeEnter: tokens.easing.easeEnter.concat([1, 1])
    readonly property var easeExit: tokens.easing.easeExit.concat([1, 1])

    function reload() {
        stateView.reload();
        themeView.reload();
    }

    function apply(text) {
        try {
            const data = JSON.parse(text);
            if (data && data.colors && data.colors.ground) theme.tokens = data;
        } catch (e) {
            console.warn('Arctic: could not read theme.json:', e);
        }
    }

    FileView {
        id: themeView
        property bool fallback: false
        // Toggled on every switch: two spellings of the same file, so the path changes and
        // FileView re-creates its watch (it sets one up only when `path` changes).
        property bool respell: false
        path: fallback ? '/usr/share/arctic/themes/polar-night/theme.json'
                       : Session.arcticConfig + (respell ? '/current/./theme.json' : '/current/theme.json')
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: theme.apply(text())
        // The read that failed is only dropped by FileView *after* this signal returns, so
        // switching path from inside the handler leaves the fallback read unowned: its result is
        // discarded ("operation finished from dropped operation") and the desktop keeps no colours
        // at all. Wait for the event loop instead, as `loadFailed` on a read that never started.
        onLoadFailed: if (!fallback) Qt.callLater(function() { fallback = true })
    }
    // `arctic-theme` swaps the ~/.config/arctic/current symlink, which a file watch on
    // current/theme.json can't see (the watch follows the link once, to the file it pointed at
    // then, and a FileView only re-creates it when its path changes). arctic-theme rewrites the
    // theme name file after every switch, and that is watched instead: on a change themeView's
    // path is respelled, so it reads theme.json through the new link and watches the new
    // target (a theme regenerated in place, like the wallpaper one, is then picked up too).
    FileView {
        id: stateView
        path: Session.arcticConfig + '/theme'
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: {
            themeView.fallback = false;
            themeView.respell = !themeView.respell;
            themeView.reload();
        }
    }
}
