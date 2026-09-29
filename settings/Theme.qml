// Arctic Settings theme: the design tokens of the theme the desktop uses right now.
//
// Like the shell's Theme.qml it reads ~/.config/arctic/current/theme.json (written for every
// theme by design/tools/gen-desktop-themes.py and switched by `arctic-theme`, including themes
// made from the wallpaper) and restyles live when it changes; it falls back to
// /usr/share/arctic/themes/polar-night/theme.json and then to Polar night built in here.
// The property names are the installer's (installer-ui/Theme.qml), so the components ported
// from installer-ui/components work unchanged: onAccent → inkOnAccent, onError → inkOnError.
//   ARCTIC_REDUCE_MOTION=1 or ~/.config/arctic/motion.conf   no slides, short fades only
pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: theme

    // Polar night, used until theme.json has been read (and if it can't be).
    readonly property var builtin: ({
            ground: "#12171e", surface: "#1a212a", surfaceRaised: "#232b36", surfaceSunken: "#0f141a",
            scrim: "#b30c1015", line: "#2f3945", lineStrong: "#6b7a8a", ink: "#e9eef3", inkMuted: "#aeb9c5",
            inkSubtle: "#8f9cab", inkDisabled: "#4d5967", inkInverse: "#151a21", accent: "#f6bd55",
            accentHover: "#fbcc6e", accentPressed: "#e9a93f", onAccent: "#151a21", accentText: "#f6bd55",
            accentSoft: "#3a2d16", accentEdge: "#f6bd55", focus: "#f6bd55", selection: "#5a4520",
            warm: "#c9bcad", warmSoft: "#2f2924", success: "#6fd3a3", successSoft: "#16322a",
            warning: "#f4a270", warningSoft: "#3a2518", error: "#ff9189", errorSoft: "#3d1c1c",
            onError: "#151a21", errorHover: "#ffaaa3", info: "#86bdf5", infoSoft: "#172c42",
            aurora1: "#3fbf8f", aurora2: "#2f9fb0", aurora3: "#2f5f9a"
        })
    property var tokens: ({ id: "polar-night", name: "Polar night", dark: true, colors: builtin })
    readonly property var c: tokens.colors
    function pickColor(name) { return c[name] || builtin[name]; }

    readonly property bool dark: tokens.dark !== false
    readonly property string themeId: tokens.id || ""
    readonly property string themeName: tokens.name || ""

    // ---- colour tokens ----
    readonly property color ground: pickColor("ground")
    readonly property color surface: pickColor("surface")
    readonly property color surfaceRaised: pickColor("surfaceRaised")
    readonly property color surfaceSunken: pickColor("surfaceSunken")
    readonly property color scrim: pickColor("scrim")
    readonly property color line: pickColor("line")
    readonly property color lineStrong: pickColor("lineStrong")
    readonly property color ink: pickColor("ink")
    readonly property color inkMuted: pickColor("inkMuted")
    readonly property color inkSubtle: pickColor("inkSubtle")
    readonly property color inkDisabled: pickColor("inkDisabled")
    readonly property color inkInverse: pickColor("inkInverse")
    readonly property color accent: pickColor("accent")
    readonly property color accentHover: pickColor("accentHover")
    readonly property color accentPressed: pickColor("accentPressed")
    readonly property color inkOnAccent: pickColor("onAccent")
    readonly property color accentText: pickColor("accentText")
    readonly property color accentSoft: pickColor("accentSoft")
    readonly property color accentEdge: pickColor("accentEdge")
    readonly property color focus: pickColor("focus")
    readonly property color selection: pickColor("selection")
    readonly property color warm: pickColor("warm")
    readonly property color warmSoft: pickColor("warmSoft")
    readonly property color success: pickColor("success")
    readonly property color successSoft: pickColor("successSoft")
    readonly property color warning: pickColor("warning")
    readonly property color warningSoft: pickColor("warningSoft")
    readonly property color error: pickColor("error")
    readonly property color errorSoft: pickColor("errorSoft")
    readonly property color inkOnError: pickColor("onError")
    readonly property color errorHover: pickColor("errorHover")
    readonly property color info: pickColor("info")
    readonly property color infoSoft: pickColor("infoSoft")
    readonly property color aurora1: pickColor("aurora1")
    readonly property color aurora2: pickColor("aurora2")
    readonly property color aurora3: pickColor("aurora3")
    // shadow-sm / shadow-md, single-layer approximations (installer-ui/Theme.qml)
    readonly property color shadowSm: dark ? "#66000000" : "#1f12171e"
    readonly property color shadowMd: dark ? "#b3000000" : "#2612171e"

    // ---- type: Figtree for the interface, JetBrains Mono for values ----
    // Some Figtree builds register as "Figtree Light"; use whichever family is installed.
    readonly property var families: Qt.fontFamilies()
    readonly property string fontSans: pick(["Figtree", "Figtree Light", "Noto Sans"])
    readonly property string fontMono: pick(["JetBrains Mono", "JetBrains Mono NL", "Noto Sans Mono", "monospace"])
    function pick(list) {
        for (let i = 0; i < list.length; i++)
            if (families.indexOf(list[i]) >= 0)
                return list[i];
        return list[list.length - 1];
    }

    // ---- spacing, radii, sizes ----
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

    // ---- motion (reduced motion: no movement, opacity fades at duration-fast) ----
    property bool motionFile: false
    readonly property bool reduceMotion: motionFile || Quickshell.env("ARCTIC_REDUCE_MOTION") === "1"
    readonly property int durationFast: 120
    readonly property int durationBase: reduceMotion ? 0 : 180
    readonly property int durationSlow: reduceMotion ? 0 : 280
    readonly property int fadeSlow: reduceMotion ? durationFast : 280
    readonly property int slideDistance: reduceMotion ? 0 : 8
    readonly property var easeStandard: [0.2, 0, 0, 1, 1, 1]

    // ---- where the theme comes from ----
    readonly property string home: Quickshell.env("HOME") || ""
    readonly property string configHome: Quickshell.env("XDG_CONFIG_HOME") || home + "/.config"
    readonly property string arcticConfig: configHome + "/arctic"

    function reload() {
        stateView.reload();
        themeView.reload();
        motionView.reload();
    }
    function apply(text) {
        try {
            const data = JSON.parse(text);
            if (data && data.colors && data.colors.ground)
                theme.tokens = data;
        } catch (e) {
            console.warn("Arctic Settings: could not read theme.json:", e);
        }
    }

    FileView {
        id: themeView
        property bool fallback: false
        path: fallback ? "/usr/share/arctic/themes/polar-night/theme.json" : theme.arcticConfig + "/current/theme.json"
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: theme.apply(text())
        // The read that failed is only dropped by FileView *after* this signal returns, so
        // switching path from inside the handler leaves the fallback read unowned: its result is
        // discarded and Settings keeps whatever colours it had. Wait for the event loop instead
        // (as shell/Theme.qml does).
        onLoadFailed: if (!fallback) Qt.callLater(function() { fallback = true })
    }
    // `arctic-theme` swaps the ~/.config/arctic/current link, which a watch on
    // current/theme.json doesn't see; it rewrites ~/.config/arctic/theme, watched here. It
    // writes that file just before it swaps the link, so read theme.json a moment later.
    FileView {
        id: stateView
        path: theme.arcticConfig + "/theme"
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: later.restart()
    }
    Timer {
        id: later
        interval: 250
        onTriggered: {
            themeView.fallback = false;
            themeView.reload();
        }
    }
    FileView {
        id: motionView
        path: theme.arcticConfig + "/motion.conf"
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: theme.motionFile = true
        onLoadFailed: theme.motionFile = false
    }
}
