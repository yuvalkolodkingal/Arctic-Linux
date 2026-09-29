// Windows: how Mango lays out and draws windows — gaps, borders, corners, animations, blur and
// shadows, focus, and the layout every workspace starts with. Each change is written to
// ~/.config/mango/settings.conf and Mango reloads its config at once (mmsg).
pragma ComponentBehavior: Bound
import QtQuick
import ".."
import "../components"

Page {
    id: page
    title: "Windows"
    lede: "How windows sit on the screen, move and take focus. Changes show at once."

    readonly property bool reducedMotion: String(Backend.info("animations").origin).endsWith("motion.conf")
    readonly property var layoutNames: ({
            tile: "Main and stack", scroller: "Scrolling columns", monocle: "One at a time", grid: "Grid",
            deck: "Deck", center_tile: "Centred main", vertical_tile: "Main on top", right_tile: "Main on the right",
            vertical_scroller: "Scrolling rows", vertical_grid: "Grid (rows)", vertical_deck: "Deck (rows)",
            dwindle: "Spiral", fair: "Even columns", vertical_fair: "Even rows"
        })
    // Animation speed as a factor of Arctic's durations (look.conf: 180 ms, 120 ms to close).
    readonly property var speedKeys: ["animation_duration_open", "animation_duration_move", "animation_duration_tag", "animation_duration_close"]
    readonly property string speed: {
        const now = Backend.num("animation_duration_open"), base = Backend.arcticNum("animation_duration_open") || 180;
        if (!Backend.info("animation_duration_open").set)
            return "1";
        const f = now / base;
        return f > 1.2 ? "1.6" : f < 0.8 ? "0.6" : "1";
    }
    function setSpeed(f) {
        if (f === "1") {
            Backend.reset(speedKeys, "Animation speed changed");
            return;
        }
        const values = {};
        speedKeys.forEach(k => values[k] = Math.round((Backend.arcticNum(k) || 180) * Number(f)));
        Backend.set(values, "Animation speed changed");
    }
    readonly property var windowKeys: ["gappih", "gappiv", "gappoh", "gappov", "borderpx", "border_radius", "smartgaps",
        "no_border_when_single", "animations", "layer_animations", "blur", "blur_layer", "shadows", "layer_shadows",
        "unfocused_opacity", "sloppyfocus", "warpcursor", "focus_on_activate", "enable_hotarea", "hotarea_corner", "new_is_master",
        "default_mfact"].concat(speedKeys)
    readonly property bool anyChanged: {
        for (let i = 0; i < windowKeys.length; i++)
            if (Backend.info(windowKeys[i]).set)
                return true;
        return (Backend.mango.layout || "") !== "";
    }

    Group {
        title: "Spacing and shape"
        SettingRow {
            searchKey: "windows.gaps"
            title: "Gap between windows"
            desc: Backend.opt("gappih") + " px"
            keys: ["gappih", "gappiv"]
            onResetRequested: Backend.reset(["gappih", "gappiv"])
            ArSlider {
                accessibleName: "Gap between windows"
                valueText: value + " pixels"
                from: 0; to: 32; stepSize: 1
                value: Backend.num("gappih")
                onCommitted: v => Backend.set({ gappih: v, gappiv: v }, "Gaps changed")
            }
        }
        SettingRow {
            searchKey: "windows.outer"
            title: "Gap at the screen edge"
            desc: Backend.opt("gappoh") + " px"
            keys: ["gappoh", "gappov"]
            onResetRequested: Backend.reset(["gappoh", "gappov"])
            ArSlider {
                accessibleName: "Gap at the screen edge"
                valueText: value + " pixels"
                from: 0; to: 48; stepSize: 1
                value: Backend.num("gappoh")
                onCommitted: v => Backend.set({ gappoh: v, gappov: v }, "Gaps changed")
            }
        }
        SettingRow {
            searchKey: "windows.border"
            title: "Border width"
            desc: Backend.opt("borderpx") + " px. The focused window’s border is amber."
            keys: ["borderpx"]
            onResetRequested: Backend.reset(["borderpx"])
            ArSlider {
                accessibleName: "Border width"
                valueText: value + " pixels"
                from: 0; to: 8; stepSize: 1
                value: Backend.num("borderpx")
                onCommitted: v => Backend.set({ borderpx: v }, "Border changed")
            }
        }
        SettingRow {
            searchKey: "windows.radius"
            title: "Rounded corners"
            desc: Backend.opt("border_radius") + " px. Arctic’s screen frame is drawn for 10."
            keys: ["border_radius"]
            onResetRequested: Backend.reset(["border_radius"])
            ArSlider {
                accessibleName: "Rounded corners"
                valueText: value + " pixels"
                from: 0; to: 24; stepSize: 1
                value: Backend.num("border_radius")
                onCommitted: v => Backend.set({ border_radius: v }, "Corners changed")
            }
        }
        SettingRow {
            searchKey: "windows.smart"
            title: "No gaps around a window on its own"
            desc: "A single window on a workspace fills the screen."
            keys: ["smartgaps"]
            onResetRequested: Backend.reset(["smartgaps"])
            RowSwitch {
                Accessible.name: "No gaps around a window on its own"
                checked: Backend.isOn("smartgaps")
                onToggled: Backend.set({ smartgaps: checked ? 1 : 0 })
            }
        }
        SettingRow {
            title: "No border around a window on its own"
            keys: ["no_border_when_single"]
            onResetRequested: Backend.reset(["no_border_when_single"])
            RowSwitch {
                Accessible.name: "No border around a window on its own"
                checked: Backend.isOn("no_border_when_single")
                onToggled: Backend.set({ no_border_when_single: checked ? 1 : 0 })
            }
        }
    }

    Group {
        title: "Motion and effects"
        SettingRow {
            searchKey: "windows.animations"
            title: "Window animations"
            desc: page.reducedMotion ? "Reduce motion is on (Appearance), so windows don’t animate." : "Windows fade and scale a little as they open, close and move."
            keys: ["animations", "layer_animations"]
            enabled: !page.reducedMotion
            onResetRequested: Backend.reset(["animations", "layer_animations"])
            // On = Arctic's value (never "animations=1", so reduced motion keeps working).
            RowSwitch {
                Accessible.name: "Window animations"
                checked: Backend.isOn("animations")
                onToggled: {
                    if (checked)
                        Backend.reset(["animations", "layer_animations"], "Animations on");
                    else
                        Backend.set({ animations: 0, layer_animations: 0 }, "Animations off");
                }
            }
        }
        SettingRow {
            searchKey: "windows.speed"
            title: "Animation speed"
            keys: page.speedKeys
            enabled: Backend.isOn("animations")
            resettable: false
            ArSegmented {
                accessibleName: "Animation speed"
                model: [{ value: "1.6", label: "Slower" }, { value: "1", label: "Arctic" }, { value: "0.6", label: "Faster" }]
                value: page.speed
                onActivated: v => page.setSpeed(v)
            }
        }
        SettingRow {
            searchKey: "windows.blur"
            title: "Frosted bar"
            desc: "Blur the wallpaper behind the top bar. Turn it off if the graphics are slow."
            keys: ["blur", "blur_layer"]
            onResetRequested: Backend.reset(["blur", "blur_layer"])
            RowSwitch {
                Accessible.name: "Frosted bar"
                checked: Backend.isOn("blur") && Backend.isOn("blur_layer")
                onToggled: {
                    if (checked)
                        Backend.set({ blur: 1, blur_layer: 1 }, "Frost on");
                    else
                        Backend.set({ blur: 0, blur_layer: 0 }, "Frost off");
                }
            }
        }
        SettingRow {
            searchKey: "windows.shadows"
            title: "Shadows"
            desc: "Under floating windows, menus and notifications."
            keys: ["shadows", "layer_shadows"]
            onResetRequested: Backend.reset(["shadows", "layer_shadows"])
            RowSwitch {
                Accessible.name: "Shadows"
                checked: Backend.isOn("shadows")
                onToggled: Backend.set({ shadows: checked ? 1 : 0, layer_shadows: checked ? 1 : 0 }, checked ? "Shadows on" : "Shadows off")
            }
        }
        SettingRow {
            searchKey: "windows.dim"
            title: "Dim windows you aren’t using"
            desc: "Makes the window you’re working in stand out."
            keys: ["unfocused_opacity"]
            resettable: false
            RowSwitch {
                Accessible.name: "Dim windows you aren’t using"
                checked: Backend.num("unfocused_opacity") < 1
                onToggled: {
                    if (checked)
                        Backend.set({ unfocused_opacity: 0.85 }, "Other windows dimmed");
                    else
                        Backend.reset(["unfocused_opacity"], "Dimming off");
                }
            }
        }
    }

    Group {
        title: "Focus"
        SettingRow {
            searchKey: "windows.focus"
            title: "Focus follows the mouse"
            desc: "The window under the pointer gets the keyboard, no click needed."
            keys: ["sloppyfocus"]
            onResetRequested: Backend.reset(["sloppyfocus"])
            RowSwitch {
                Accessible.name: "Focus follows the mouse"
                checked: Backend.isOn("sloppyfocus")
                onToggled: Backend.set({ sloppyfocus: checked ? 1 : 0 })
            }
        }
        SettingRow {
            searchKey: "windows.warp"
            title: "Pointer follows the focus"
            desc: "When you switch windows with the keyboard, the pointer moves to the window."
            keys: ["warpcursor"]
            onResetRequested: Backend.reset(["warpcursor"])
            RowSwitch {
                Accessible.name: "Pointer follows the focus"
                checked: Backend.isOn("warpcursor")
                onToggled: Backend.set({ warpcursor: checked ? 1 : 0 })
            }
        }
        SettingRow {
            searchKey: "windows.activate"
            title: "Apps can bring themselves forward"
            desc: "For example a browser when you click a link in another app."
            keys: ["focus_on_activate"]
            onResetRequested: Backend.reset(["focus_on_activate"])
            RowSwitch {
                Accessible.name: "Apps can bring themselves forward"
                checked: Backend.isOn("focus_on_activate")
                onToggled: Backend.set({ focus_on_activate: checked ? 1 : 0 })
            }
        }
        SettingRow {
            searchKey: "windows.hotcorner"
            title: "Hot corner"
            desc: "Push the pointer into a corner of the screen to open the overview (Super + O)."
            keys: ["enable_hotarea", "hotarea_corner"]
            onResetRequested: Backend.reset(["enable_hotarea", "hotarea_corner"])
            Row {
                spacing: Theme.space3
                ArSelect {
                    visible: Backend.isOn("enable_hotarea")
                    width: 180
                    model: [{ value: "0", label: "Top left" }, { value: "1", label: "Top right" },
                            { value: "2", label: "Bottom left" }, { value: "3", label: "Bottom right" }]
                    value: String(Backend.num("hotarea_corner"))
                    onActivated: v => Backend.set({ hotarea_corner: v })
                }
                RowSwitch {
                    anchors.verticalCenter: parent.verticalCenter
                    Accessible.name: "Hot corner"
                    checked: Backend.isOn("enable_hotarea")
                    onToggled: Backend.set({ enable_hotarea: checked ? 1 : 0 })
                }
            }
        }
    }

    Group {
        title: "Layout"
        desc: "Super + N switches the layout of the workspace you’re on; this is where every workspace starts."
        SettingRow {
            searchKey: "windows.layout"
            title: "Layout for every workspace"
            desc: "Arctic uses " + (page.layoutNames[Backend.mango.arcticLayout] || "Main and stack").toLowerCase() + "."
            extraChanged: (Backend.mango.layout || "") !== ""
            onResetRequested: Backend.setLayout("")
            ArSelect {
                width: 240
                model: (Backend.mango.layouts || []).map(l => ({ value: l, label: page.layoutNames[l] || l }))
                value: Backend.mango.layout || Backend.mango.arcticLayout || "tile"
                onActivated: v => Backend.setLayout(v === (Backend.mango.arcticLayout || "tile") ? "" : v)
            }
        }
        SettingRow {
            searchKey: "windows.master"
            title: "New windows open as the main window"
            desc: "Otherwise they join the stack beside it."
            keys: ["new_is_master"]
            onResetRequested: Backend.reset(["new_is_master"])
            RowSwitch {
                Accessible.name: "New windows open as the main window"
                checked: Backend.isOn("new_is_master")
                onToggled: Backend.set({ new_is_master: checked ? 1 : 0 })
            }
        }
        SettingRow {
            searchKey: "windows.mfact"
            title: "Width of the main area"
            desc: Math.round(Backend.num("default_mfact") * 100) + "% of the screen. Super + Ctrl + ← → changes it for now."
            keys: ["default_mfact"]
            onResetRequested: Backend.reset(["default_mfact"])
            ArSlider {
                accessibleName: "Width of the main area"
                valueText: Math.round(value * 100) + " percent"
                from: 0.3; to: 0.7; stepSize: 0.05
                value: Backend.num("default_mfact")
                onCommitted: v => Backend.set({ default_mfact: v.toFixed(2) })
            }
        }
    }

    // Lighter effects and game mode (arctic-effects): Mango lines in ~/.config/arctic/effects.conf,
    // sourced after settings.conf, so they win over the rows above while they're on.
    Group {
        id: effectsGroup
        property var fx: ({ helper: false })
        function set(what, value) {
            Backend.call(["effects-set", what, value], r => {
                if (r.ok) {
                    effectsGroup.fx = r;
                    Backend.refresh();
                }
            });
        }
        visible: fx.helper === true
        title: "Effects"
        desc: fx.lighter_active ? "Animations, blur and shadows are off while this is on, whatever the rows above say." : ""
        Component.onCompleted: Backend.call(["effects"], r => { if (r.ok) effectsGroup.fx = r; }, true)
        SettingRow {
            searchKey: "windows.lighter"
            title: "Lighter effects"
            desc: "No animations, blur or shadows. Automatic turns them off in virtual machines and without a graphics driver."
                + (effectsGroup.fx.reason === "vm" ? " On now: this is a virtual machine." : effectsGroup.fx.reason === "software" ? " On now: there’s no graphics driver." : "")
            resettable: false
            ArSegmented {
                accessibleName: "Lighter effects"
                model: [{ value: "auto", label: "Automatic" }, { value: "on", label: "On" }, { value: "off", label: "Off" }]
                value: effectsGroup.fx.lighter || "auto"
                onActivated: v => effectsGroup.set("lighter", v)
            }
        }
        SettingRow {
            searchKey: "windows.gamemode"
            title: "Game mode"
            desc: "Lighter effects and no gaps, until you turn it off or log out."
            resettable: false
            RowSwitch {
                Accessible.name: "Game mode"
                checked: effectsGroup.fx.game === true
                onToggled: effectsGroup.set("game", checked ? "on" : "off")
            }
        }
    }

    Row {
        spacing: Theme.space2
        ArButton {
            text: "Reset all window settings"
            variant: "secondary"
            enabled: page.anyChanged
            onClicked: {
                Backend.reset(page.windowKeys, "Window settings are Arctic’s again");
                if ((Backend.mango.layout || "") !== "")
                    Backend.setLayout("");
            }
        }
        ArButton {
            visible: Backend.caps.xdgOpen === true
            text: "Open settings.conf"
            variant: "ghost"
            iconRight: "external"
            onClicked: Backend.openUrl("file://" + Backend.mango.settingsFile)
        }
    }
}
