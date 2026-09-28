// Appearance: the theme (Winter, Polar night, or made from the wallpaper — arctic-theme), light
// and dark by the clock (arctic-daylight), the wallpaper (the shell's picker backend), reduced
// motion (arctic-motion), text size in GTK apps (gsettings) and the pointer (Mango
// cursor_theme / cursor_size).
// Without the newer arctic-theme (set/auto/mode/list), only Winter and Polar night are offered
// and the rest says why.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Templates as T
import ".."
import "../components"

Page {
    id: page
    title: "Appearance"
    lede: "Colours, wallpaper and motion for the whole desktop: the bar, windows, the terminal and apps."

    property var theme: ({ available: true, modern: false, themes: [], current: "", mode: "auto", auto: false })
    property var walls: ({ items: [], current: "", available: true })
    property var motion: ({ available: true, reduced: false })
    property var textScale: ({ available: false, value: 1 })
    property var cursors: []
    property var daylight: ({ available: false, mode: "off" })
    property string busyTheme: ""
    property string busyWall: ""

    function load() {
        Backend.call(["theme"], r => { if (r.ok) page.theme = r; });
        Backend.call(["motion"], r => { if (r.ok) page.motion = r; });
        Backend.call(["text-scale"], r => { if (r.ok) page.textScale = r; }, true);
        Backend.call(["cursor-themes"], r => { if (r.ok) page.cursors = r.themes; }, true);
        Backend.call(["daylight"], r => { if (r.ok) page.daylight = r; }, true);
        loadWallpapers();
    }
    // Light and dark by the clock (arctic-daylight): off, sunset to sunrise, or custom hours.
    function setDaylight(args) {
        Backend.call(["daylight-set"].concat(args), r => {
            if (r.ok) {
                page.daylight = r;
                Theme.reload();
                Backend.notify("success", r.mode === "off" ? "Light and dark: only when you switch" : "Light and dark switch by themselves now", false);
            }
        });
    }
    function daylightText() {
        const d = page.daylight;
        if (d.message) return d.message;
        if (d.mode === "sun" && d.today) return "Light from sunrise (" + d.today.light + " today), dark from sunset (" + d.today.dark + "), where your time zone is. Super + Shift + T still switches until the next one.";
        if (d.mode === "hours") return "Light from " + d.light + ", dark from " + d.dark + ". Super + Shift + T still switches until the next change.";
        return "Only when you switch: here or with Super + Shift + T.";
    }
    function loadWallpapers() {
        Backend.call(["wallpapers"], r => { if (r.ok) page.walls = r; });
    }
    function setTheme(id) {
        if (busyTheme !== "" || id === theme.current)
            return;
        busyTheme = id;
        Backend.call(["theme-set", id], r => {
            page.busyTheme = "";
            if (r.ok) {
                page.theme = r;
                Theme.reload();
                page.loadWallpapers();
                Backend.notify("success", "Theme changed", false);
            }
        });
    }
    onShown: load()
    // /home/you/Pictures/Wallpapers → ~/Pictures/Wallpapers
    function tildePath(path) {
        const home = Theme.home;
        return home && (path === home || String(path).startsWith(home + "/")) ? "~" + String(path).slice(home.length) : path;
    }
    // The theme changed elsewhere too (Super + Shift + T, the shell): follow it.
    Connections {
        target: Theme
        function onThemeIdChanged() {
            Backend.call(["theme"], r => { if (r.ok) page.theme = r; }, true);
            page.loadWallpapers();
        }
    }

    readonly property var swatches: ({
            "winter": ["#eef2f5", "#ffffff", "#151a21", "#efa637"],
            "polar-night": ["#12171e", "#232b36", "#e9eef3", "#f6bd55"]
        })

    Group {
        title: "Theme"
        desc: page.theme.available ? "" : page.theme.reason || ""
        SettingRow {
            searchKey: "appearance.theme"
            title: "Theme"
            desc: page.theme.modern ? "Winter is the light coat, Polar night the dark one. From wallpaper takes the colours of your picture."
                                    : (page.theme.reason || "Winter is the light coat, Polar night the dark one.")
            stacked: true
            enabled: page.theme.available !== false
            Row {
                width: parent.width
                spacing: Theme.space3
                Repeater {
                    model: [{ id: "winter", name: "Winter" }, { id: "polar-night", name: "Polar night" }, { id: "wallpaper", name: "From wallpaper" }]
                    ArCard {
                        id: card
                        required property var modelData
                        readonly property bool isWallpaper: modelData.id === "wallpaper"
                        width: (parent.width - 2 * Theme.space3) / 3
                        choice: true
                        radio: true
                        title: page.busyTheme === modelData.id ? "Switching…" : modelData.name
                        selected: page.theme.current === modelData.id
                        enabled: page.theme.available !== false && (!isWallpaper || page.theme.modern === true)
                        onClicked: page.setTheme(modelData.id)
                        Row {
                            topPadding: Theme.space2
                            spacing: 4
                            Repeater {
                                model: card.isWallpaper ? [Theme.ground, Theme.surfaceRaised, Theme.ink, Theme.accent] : page.swatches[card.modelData.id]
                                Rectangle {
                                    required property var modelData
                                    width: 22
                                    height: 22
                                    radius: 6
                                    color: modelData
                                    border.width: 1
                                    border.color: Theme.line
                                }
                            }
                        }
                    }
                }
            }
        }
        SettingRow {
            searchKey: "appearance.auto"
            title: "Match colours to the wallpaper"
            desc: page.theme.modern ? "Each new wallpaper makes the theme again, so the accent always suits the picture."
                                    : "Needs a newer arctic-theme (arctic-theme auto)."
            enabled: page.theme.modern === true
            RowSwitch {
                checked: page.theme.auto === true
                onToggled: Backend.call(["theme-auto", checked ? "on" : "off"], r => {
                    if (r.ok) { page.theme = r; Theme.reload(); }
                    else checked = page.theme.auto === true;
                })
                Accessible.name: "Match colours to the wallpaper"
            }
        }
        SettingRow {
            searchKey: "appearance.mode"
            title: "Light or dark"
            desc: page.theme.current === "wallpaper" ? "For the theme made from your wallpaper. Automatic picks what suits the picture."
                                                     : "Applies to the theme made from your wallpaper."
            enabled: page.theme.modern === true && (page.theme.current === "wallpaper" || page.theme.auto === true)
            ArSegmented {
                accessibleName: "Light or dark"
                model: [{ value: "auto", label: "Automatic" }, { value: "dark", label: "Dark" }, { value: "light", label: "Light" }]
                value: page.theme.mode || "auto"
                onActivated: v => Backend.call(["theme-mode", v], r => {
                    if (r.ok) { page.theme = r; Theme.reload(); }
                })
            }
        }
        SettingRow {
            searchKey: "appearance.schedule"
            visible: page.daylight.available === true
            title: "Switch light and dark by itself"
            desc: page.daylightText()
            ArSegmented {
                accessibleName: "Switch light and dark by itself"
                model: [{ value: "off", label: "Off" }, { value: "sun", label: "Sunset to sunrise" }, { value: "hours", label: "Custom hours" }]
                value: page.daylight.mode || "off"
                onActivated: v => page.setDaylight(v === "hours" ? ["hours", page.daylight.light || "07:00", page.daylight.dark || "19:00"] : [v])
            }
        }
        SettingRow {
            visible: page.daylight.available === true && page.daylight.mode === "hours"
            title: "Light from, dark from"
            desc: "24-hour times, like 07:00 and 19:00. Enter saves."
            resettable: false
            Row {
                spacing: Theme.space2
                ArInput {
                    id: lightFrom
                    width: 96
                    text: page.daylight.light || "07:00"
                    placeholder: "07:00"
                    maximumLength: 5
                    accessibleName: "Light from"
                    onAccepted: page.setDaylight(["hours", lightFrom.text.trim(), darkFrom.text.trim()])
                }
                ArInput {
                    id: darkFrom
                    width: 96
                    text: page.daylight.dark || "19:00"
                    placeholder: "19:00"
                    maximumLength: 5
                    accessibleName: "Dark from"
                    onAccepted: page.setDaylight(["hours", lightFrom.text.trim(), darkFrom.text.trim()])
                }
            }
        }
    }

    Group {
        title: "Wallpaper"
        desc: page.walls.folder ? "Your own pictures come from " + page.tildePath(page.walls.folder) + "." : ""
        SettingRow {
            searchKey: "appearance.wallpaper"
            title: "Wallpaper"
            desc: page.walls.available === false ? (page.walls.reason || "") : "The Arctic wallpapers follow Winter and Polar night. Super + Shift + W opens the picker from anywhere."
            stacked: true
            Flow {
                width: parent.width
                spacing: Theme.space3
                Repeater {
                    model: page.walls.items || []
                    T.AbstractButton {
                        id: thumb
                        required property var modelData
                        readonly property bool chosen: page.walls.current === modelData.key
                        width: 152
                        height: 112
                        focusPolicy: Qt.StrongFocus
                        hoverEnabled: true
                        Accessible.role: Accessible.RadioButton
                        Accessible.name: modelData.name
                        Accessible.checked: chosen
                        onClicked: {
                            if (page.busyWall !== "")
                                return;
                            page.busyWall = modelData.key;
                            Backend.call(["wallpaper-set", modelData.key], r => {
                                page.busyWall = "";
                                if (r.ok) {
                                    page.walls = Object.assign({}, page.walls, { current: thumb.modelData.key });
                                    Backend.notify("success", "Wallpaper changed", false);
                                }
                            });
                        }
                        Keys.onReturnPressed: clicked()
                        background: Item {}
                        contentItem: Column {
                            spacing: Theme.space1
                            Rectangle {
                                width: thumb.width
                                height: 86
                                radius: Theme.radiusMd
                                color: Theme.surfaceSunken
                                border.width: thumb.chosen ? 2 : 1
                                border.color: thumb.chosen ? Theme.accentEdge : thumb.hovered ? Theme.lineStrong : Theme.line
                                Image {
                                    anchors.fill: parent
                                    anchors.margins: thumb.chosen ? 2 : 1
                                    source: thumb.modelData.thumb ? "file://" + thumb.modelData.thumb : ""
                                    sourceSize: Qt.size(300, 172)
                                    fillMode: Image.PreserveAspectCrop
                                    asynchronous: true
                                    smooth: true
                                }
                                Rectangle {
                                    visible: page.busyWall === thumb.modelData.key
                                    anchors.fill: parent
                                    radius: parent.radius
                                    color: Theme.scrim
                                    ArText {
                                        anchors.centerIn: parent
                                        text: "Setting…"
                                        size: 13
                                        lh: 18
                                        color: "#ffffff"
                                    }
                                }
                                FocusRing {
                                    show: thumb.visualFocus
                                    radius: Theme.radiusMd
                                    gapColor: Theme.surfaceRaised
                                }
                            }
                            ArText {
                                width: thumb.width
                                text: thumb.modelData.name
                                size: 13
                                lh: 18
                                elide: Text.ElideRight
                                weight: thumb.chosen ? Font.DemiBold : Font.Normal
                                color: thumb.chosen ? Theme.ink : Theme.inkMuted
                            }
                        }
                    }
                }
            }
        }
    }

    Group {
        title: "Text and motion"
        SettingRow {
            searchKey: "appearance.motion"
            title: "Reduce motion"
            desc: "Windows and menus fade instead of moving, and the fox in the terminal stays still."
            enabled: page.motion.available !== false
            RowSwitch {
                checked: page.motion.reduced === true
                Accessible.name: "Reduce motion"
                onToggled: Backend.call(["motion-set", checked ? "off" : "on"], r => {
                    if (r.ok) {
                        page.motion = r;
                        Theme.reload();
                        Backend.refresh();
                    } else {
                        checked = page.motion.reduced === true;
                    }
                })
            }
        }
        SettingRow {
            searchKey: "appearance.textscale"
            visible: page.textScale.available === true
            title: "Text size in apps"
            desc: "For GTK apps such as Files and most dialogs. The bar and menus keep their size."
            ArSelect {
                width: 180
                model: [{ value: "1", label: "Default" }, { value: "1.1", label: "110%" }, { value: "1.25", label: "125%" },
                    { value: "1.5", label: "150%" }, { value: "1.75", label: "175%" }]
                value: String(Math.round((page.textScale.value || 1) * 100) / 100)
                onActivated: v => Backend.call(["text-scale", v], r => {
                    if (r.ok) {
                        page.textScale = r;
                        Backend.notify("success", "Text size changed. Apps that are open may need a restart.", false);
                    }
                })
            }
        }
    }

    Group {
        title: "Pointer"
        SettingRow {
            searchKey: "appearance.cursor"
            title: "Pointer size"
            keys: ["cursor_size"]
            onResetRequested: Backend.reset(["cursor_size"])
            ArSegmented {
                accessibleName: "Pointer size"
                model: [{ value: "24", label: "Normal" }, { value: "32", label: "Large" }, { value: "48", label: "Larger" }]
                value: Backend.opt("cursor_size")
                onActivated: v => Backend.set({ cursor_size: v }, "Pointer size changed")
            }
        }
        SettingRow {
            title: "Pointer style"
            desc: "Cursor themes installed on this computer."
            keys: ["cursor_theme"]
            visible: page.cursors.length > 0
            onResetRequested: Backend.reset(["cursor_theme"])
            ArSelect {
                width: 220
                placeholder: "System default"
                model: page.cursors.map(t => ({ value: t, label: t }))
                value: Backend.opt("cursor_theme")
                onActivated: v => Backend.set({ cursor_theme: v }, "Pointer style changed")
            }
        }
    }
}
