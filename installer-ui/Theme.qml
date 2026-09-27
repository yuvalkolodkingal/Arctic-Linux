// Arctic Linux installer theme. Colours, spacing, radii and motion come from
// design/exports/Theme.qml (generated from design/tokens.json); the rest
// (type scale, shadows, easing, fonts) from design/components/bundle.css and
// tokens.json. Polar night (dark) is the default in the live session.
//   ARCTIC_INSTALLER_THEME=light   Winter theme
//   ARCTIC_REDUCE_MOTION=1         no slides; only short opacity fades
pragma Singleton
import QtQuick
import Quickshell

Singleton {
    id: theme

    property bool dark: Quickshell.env("ARCTIC_INSTALLER_THEME") !== "light"
    readonly property bool reduceMotion: Quickshell.env("ARCTIC_REDUCE_MOTION") === "1"

    // ---- colour tokens (design/exports/Theme.qml) ----
    readonly property color ground: dark ? "#12171e" : "#eef2f5"
    readonly property color surface: dark ? "#1a212a" : "#fbfcfd"
    readonly property color surfaceRaised: dark ? "#232b36" : "#ffffff"
    readonly property color surfaceSunken: dark ? "#0f141a" : "#e8edf1"
    readonly property color scrim: dark ? "#b30c1015" : "#6612171e"
    readonly property color line: dark ? "#2f3945" : "#d5dde4"
    readonly property color lineStrong: dark ? "#6b7a8a" : "#7c8a99"
    readonly property color ink: dark ? "#e9eef3" : "#151a21"
    readonly property color inkMuted: dark ? "#aeb9c5" : "#4a5663"
    readonly property color inkSubtle: dark ? "#8f9cab" : "#5f6b79"
    readonly property color inkDisabled: dark ? "#4d5967" : "#a9b5c1"
    readonly property color inkInverse: dark ? "#151a21" : "#e9eef3"
    readonly property color accent: dark ? "#f6bd55" : "#efa637"
    readonly property color accentHover: dark ? "#fbcc6e" : "#e2961f"
    readonly property color accentPressed: dark ? "#e9a93f" : "#cf8519"
    // design Theme.qml calls these onAccent/onError; QML reads "on" + capital
    // as a signal handler, so they are renamed here.
    readonly property color inkOnAccent: "#151a21"
    readonly property color accentText: dark ? "#f6bd55" : "#84500d"
    readonly property color accentSoft: dark ? "#3a2d16" : "#fdf0d6"
    // In Polar night the amber edge is the accent itself (bundle.css [data-theme=dark] rules).
    readonly property color accentEdge: dark ? "#f6bd55" : "#a86812"
    readonly property color focus: dark ? "#f6bd55" : "#a86812"
    readonly property color selection: dark ? "#5a4520" : "#fbdea3"
    readonly property color warm: dark ? "#c9bcad" : "#62564b"
    readonly property color warmSoft: dark ? "#2f2924" : "#f0eae3"
    readonly property color success: dark ? "#6fd3a3" : "#1d7350"
    readonly property color successSoft: dark ? "#16322a" : "#e1f2e9"
    readonly property color warning: dark ? "#f4a270" : "#9a4812"
    readonly property color warningSoft: dark ? "#3a2518" : "#fbeadf"
    readonly property color error: dark ? "#ff9189" : "#b3261e"
    readonly property color errorSoft: dark ? "#3d1c1c" : "#fbe6e4"
    readonly property color inkOnError: dark ? "#151a21" : "#ffffff"
    readonly property color errorHover: dark ? "#ffaaa3" : "#9a1f18"
    readonly property color info: dark ? "#86bdf5" : "#1f5f9e"
    readonly property color infoSoft: dark ? "#172c42" : "#e2eefa"
    readonly property color aurora1: dark ? "#3fbf8f" : "#c9f1de"
    readonly property color aurora2: dark ? "#2f9fb0" : "#c4ecee"
    readonly property color aurora3: dark ? "#2f5f9a" : "#d3e3f6"
    // shadow-sm (single layer approximation): dark 0 1px 2px #00000066, light 0 1px 3px #12171e14
    readonly property color shadowSm: dark ? "#66000000" : "#1f12171e"
    readonly property color shadowMd: dark ? "#b3000000" : "#2612171e"

    // ---- type ----
    // The design's Figtree woff2 files carry the family name "Figtree Light"
    // (fc-scan). FontLoader.name gives the real family; fall back to "Figtree".
    readonly property string fontSans: figtree400.status === FontLoader.Ready ? figtree400.name : "Figtree"
    readonly property string fontMono: mono400.status === FontLoader.Ready ? mono400.name : "JetBrains Mono"
    readonly property string fontDir: "file:///usr/share/fonts/arctic/"
    // Qt.resolvedUrl() outside the shell dir is blackholed by Quickshell; build a file URL.
    readonly property string repoFontDir: "file://" + Quickshell.shellDir + "/../design/fonts/"
    FontLoader { id: figtree400; source: theme.fontDir + "Figtree-400.woff2"; onStatusChanged: theme.fontFallback(figtree400, "Figtree-400.woff2") }
    FontLoader { id: figtree500; source: theme.fontDir + "Figtree-500.woff2"; onStatusChanged: theme.fontFallback(figtree500, "Figtree-500.woff2") }
    FontLoader { id: figtree600; source: theme.fontDir + "Figtree-600.woff2"; onStatusChanged: theme.fontFallback(figtree600, "Figtree-600.woff2") }
    FontLoader { id: figtree700; source: theme.fontDir + "Figtree-700.woff2"; onStatusChanged: theme.fontFallback(figtree700, "Figtree-700.woff2") }
    FontLoader { id: mono400; source: theme.fontDir + "JetBrainsMono-400.woff2"; onStatusChanged: theme.fontFallback(mono400, "JetBrainsMono-400.woff2") }
    FontLoader { id: mono700; source: theme.fontDir + "JetBrainsMono-700.woff2"; onStatusChanged: theme.fontFallback(mono700, "JetBrainsMono-700.woff2") }
    function fontFallback(loader, file) {
        // Installed fonts live in /usr/share/fonts/arctic (arctic-fonts); from a
        // repo checkout use design/fonts next to installer-ui/.
        if (loader.status === FontLoader.Error && String(loader.source).indexOf(theme.fontDir) === 0)
            loader.source = theme.repoFontDir + file;
    }

    // ---- spacing, radii, sizes (tokens) ----
    readonly property int space1: 4
    readonly property int space2: 8
    readonly property int space3: 12
    readonly property int space4: 16
    readonly property int space5: 20
    readonly property int space6: 24
    readonly property int space8: 32
    readonly property int space10: 40
    readonly property int radiusXs: 4
    readonly property int radiusSm: 6
    readonly property int radiusMd: 10
    readonly property int radiusLg: 14
    readonly property int radiusXl: 20
    readonly property int controlSm: 28
    readonly property int controlMd: 36
    readonly property int controlLg: 44
    readonly property int targetMin: 32
    readonly property int focusWidth: 2
    readonly property int railWidth: 232

    // ---- motion ----
    readonly property int durationFast: 120
    readonly property int durationBase: reduceMotion ? 0 : 180
    readonly property int durationSlow: reduceMotion ? 0 : 280
    // Opacity fades survive reduced motion at duration-fast (brand book, Motion).
    readonly property int fadeSlow: reduceMotion ? durationFast : 280
    readonly property int slideDistance: reduceMotion ? 0 : 8
    // ease-standard cubic-bezier(0.2, 0, 0, 1)
    readonly property var easeStandard: [0.2, 0, 0, 1, 1, 1]
}
