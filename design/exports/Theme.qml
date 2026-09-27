// Arctic Linux — Theme.qml singleton for the SDDM theme and Qt apps.
// qmldir: singleton Theme 1.0 Theme.qml
pragma Singleton
import QtQuick

QtObject {
    property bool dark: true   // Polar night by default on the login screen
    readonly property color ground: dark ? "#12171e" : "#eef2f5"
    readonly property color surface: dark ? "#1a212a" : "#fbfcfd"
    readonly property color surfaceRaised: dark ? "#232b36" : "#ffffff"
    readonly property color surfaceSunken: dark ? "#0f141a" : "#e8edf1"
    readonly property color frost: dark ? "#d11a212a" : "#ccfbfcfd"
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
    readonly property color onAccent: dark ? "#151a21" : "#151a21"
    readonly property color accentText: dark ? "#f6bd55" : "#84500d"
    readonly property color accentSoft: dark ? "#3a2d16" : "#fdf0d6"
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
    readonly property color onError: dark ? "#151a21" : "#ffffff"
    readonly property color errorHover: dark ? "#ffaaa3" : "#9a1f18"
    readonly property color info: dark ? "#86bdf5" : "#1f5f9e"
    readonly property color infoSoft: dark ? "#172c42" : "#e2eefa"
    readonly property color aurora1: dark ? "#3fbf8f" : "#c9f1de"
    readonly property color aurora2: dark ? "#2f9fb0" : "#c4ecee"
    readonly property color aurora3: dark ? "#2f5f9a" : "#d3e3f6"
    readonly property color termBackground: dark ? "#151b22" : "#f7f9fb"
    readonly property color termForeground: dark ? "#dfe6ed" : "#1d242d"
    readonly property color termCursor: dark ? "#f6bd55" : "#9a5e0f"
    readonly property color termCursorTextColor: dark ? "#151b22" : "#f7f9fb"
    readonly property color termSelectionBackground: dark ? "#5a4520" : "#fbdea3"
    readonly property color termSelectionForeground: dark ? "#f3f6f9" : "#1d242d"
    readonly property color ansi0: dark ? "#2a3440" : "#1d242d"
    readonly property color ansi1: dark ? "#ef8a84" : "#b3261e"
    readonly property color ansi2: dark ? "#7fcf9b" : "#1d7350"
    readonly property color ansi3: dark ? "#f2b857" : "#84500d"
    readonly property color ansi4: dark ? "#80b0e8" : "#1f5f9e"
    readonly property color ansi5: dark ? "#d49ccf" : "#8a3d86"
    readonly property color ansi6: dark ? "#72cfd3" : "#136c76"
    readonly property color ansi7: dark ? "#c3ccd6" : "#66727f"
    readonly property color ansi8: dark ? "#8392a3" : "#5f6b79"
    readonly property color ansi9: dark ? "#ffa39c" : "#c43a2c"
    readonly property color ansi10: dark ? "#9ee6b6" : "#237f5b"
    readonly property color ansi11: dark ? "#ffd07f" : "#a35f0c"
    readonly property color ansi12: dark ? "#a2c8f2" : "#2e6eb0"
    readonly property color ansi13: dark ? "#e8b8e3" : "#9c4b98"
    readonly property color ansi14: dark ? "#9be3e6" : "#1a7c87"
    readonly property color ansi15: dark ? "#f3f6f9" : "#3e4a58"

    readonly property string fontSans: "Figtree"
    readonly property string fontMono: "JetBrains Mono"
    readonly property int spaceHalf: 2
    readonly property int space1: 4
    readonly property int space2: 8
    readonly property int space3: 12
    readonly property int space4: 16
    readonly property int space5: 20
    readonly property int space6: 24
    readonly property int space8: 32
    readonly property int space10: 40
    readonly property int space12: 48
    readonly property int space16: 64
    readonly property int radiusXs: 4
    readonly property int radiusSm: 6
    readonly property int radiusMd: 10
    readonly property int radiusLg: 14
    readonly property int radiusXl: 20
    readonly property int radiusFull: 9999
    readonly property int durationFast: 120
    readonly property int durationBase: 180
    readonly property int durationSlow: 280
    readonly property int durationAmbient: 2400
    readonly property int controlLg: 44
    readonly property int targetMin: 32
    readonly property int focusWidth: 2
}
