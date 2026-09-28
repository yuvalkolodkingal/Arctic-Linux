// Keyboard and mouse: keyboard layouts (+ variants, the key that switches between them, what
// Caps Lock does, the Compose key), key repeat, touchpad and mouse. All of it is Mango config (xkb_rules_*,
// repeat_*, trackpad_*, mouse_*), written to settings.conf for you only: the installer's
// /etc/arctic/mango/keyboard.conf (root's, also used by the login screen) stays as it is.
pragma ComponentBehavior: Bound
import QtQuick
import ".."
import "../components"

Page {
    id: page
    title: "Keyboard and mouse"
    lede: "Layouts and typing, the touchpad and the mouse."

    property var kb: ({ layouts: [], variants: {}, switchKeys: [], capsOptions: [], composeKeys: [], switchClashes: {} })
    property var devices: ({ trackpad: true, mouse: true })
    readonly property var layoutKeys: ["xkb_rules_layout", "xkb_rules_variant", "xkb_rules_options"]

    // The effective keyboard: [{layout, variant}] and the options split into switch / caps / rest.
    readonly property var current: {
        const layouts = (Backend.opt("xkb_rules_layout") || "us").split(",");
        const variants = (Backend.opt("xkb_rules_variant") || "").split(",");
        return layouts.map((l, i) => ({ layout: l, variant: variants[i] || "" }));
    }
    readonly property var options: (Backend.opt("xkb_rules_options") || "").split(",").filter(o => o !== "")
    readonly property string switchKey: options.find(o => o.startsWith("grp:")) || ""
    readonly property string capsKey: options.find(o => o.startsWith("caps:") || o === "ctrl:nocaps") || ""
    readonly property string composeKey: options.find(o => o.startsWith("compose:")) || ""
    // Shortcuts that hold the chord the switch key uses: they switch the layout too.
    readonly property var switchClashes: (kb.switchClashes || {})[switchKey || "grp:alt_shift_toggle"] || []

    function labelOf(id) {
        const l = kb.layouts.find(x => x.id === id);
        return l ? l.label : id;
    }
    function save(list, sw, caps, compose) {
        if (compose === undefined)
            compose = composeKey;
        // Caps Lock can't be both the Compose key and something else, or switch layouts.
        if (compose === "compose:caps") {
            caps = "";
            if (sw === "grp:caps_toggle" || sw === "grp:alt_caps_toggle")
                sw = "grp:alt_shift_toggle";
        }
        const rest = options.filter(o => !o.startsWith("grp:") && !o.startsWith("caps:") && o !== "ctrl:nocaps" && !o.startsWith("compose:"));
        if (list.length > 1)
            rest.unshift(sw || "grp:alt_shift_toggle");
        if (caps)
            rest.push(caps);
        if (compose)
            rest.push(compose);
        const variants = list.map(x => x.variant).join(",");
        Backend.set({
            xkb_rules_layout: list.map(x => x.layout).join(","),
            xkb_rules_variant: /^,*$/.test(variants) ? "" : variants,
            xkb_rules_options: rest.join(",")
        }, "Keyboard changed");
    }
    onShown: {
        Backend.call(["keyboard-data"], r => { if (r.ok) page.kb = r; });
        Backend.call(["devices"], r => { if (r.ok) page.devices = r; }, true);
    }

    Group {
        title: "Keyboard"
        desc: "Only for you: the login screen keeps the layout picked in the installer."
        SettingRow {
            searchKey: "input.layouts"
            title: "Layouts"
            desc: page.current.length > 1 ? "The first one is used when you log in." : "Add another to type in more than one language."
            keys: page.layoutKeys
            stacked: true
            onResetRequested: Backend.reset(page.layoutKeys, "Keyboard is the installer’s again")
            Column {
                width: parent.width
                spacing: Theme.space2
                Repeater {
                    model: page.current
                    Row {
                        id: layoutRow
                        required property var modelData
                        required property int index
                        spacing: Theme.space2
                        ArText {
                            width: 200
                            text: page.labelOf(layoutRow.modelData.layout)
                            size: 15
                            lh: 22
                            elide: Text.ElideRight
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        ArSelect {
                            width: 230
                            placeholder: "Standard"
                            model: [{ value: "", label: "Standard" }].concat((page.kb.variants[layoutRow.modelData.layout] || []).map(v => ({ value: v.id, label: v.label })))
                            value: layoutRow.modelData.variant
                            onActivated: v => {
                                const list = page.current.map(x => Object.assign({}, x));
                                list[layoutRow.index].variant = v;
                                page.save(list, page.switchKey, page.capsKey);
                            }
                        }
                        ArButton {
                            visible: layoutRow.index > 0
                            variant: "ghost"
                            size: "sm"
                            iconName: "chevron-up"
                            Accessible.name: "Use " + page.labelOf(layoutRow.modelData.layout) + " first"
                            anchors.verticalCenter: parent.verticalCenter
                            gapColor: Theme.surfaceRaised
                            onClicked: {
                                const list = page.current.slice();
                                const moved = list.splice(layoutRow.index, 1)[0];
                                list.splice(layoutRow.index - 1, 0, moved);
                                page.save(list, page.switchKey, page.capsKey);
                            }
                        }
                        ArButton {
                            visible: page.current.length > 1
                            variant: "ghost"
                            size: "sm"
                            iconName: "x"
                            Accessible.name: "Remove " + page.labelOf(layoutRow.modelData.layout)
                            anchors.verticalCenter: parent.verticalCenter
                            gapColor: Theme.surfaceRaised
                            onClicked: {
                                const list = page.current.slice();
                                list.splice(layoutRow.index, 1);
                                page.save(list, page.switchKey, page.capsKey);
                            }
                        }
                    }
                }
                ArButton {
                    visible: page.current.length < 4
                    text: "Add a layout"
                    iconName: "plus"
                    gapColor: Theme.surfaceRaised
                    onClicked: layoutPicker.start()
                }
            }
        }
        SettingRow {
            searchKey: "input.switch"
            visible: page.current.length > 1
            title: "Switch layouts with"
            desc: page.switchClashes.length ? "Also switches the layout: " + page.switchClashes.join(", ") + "."
                : page.switchKey === "grp:toggle" ? "Right Alt switches layouts, so Alt shortcuts use the left Alt." : ""
            resettable: false
            ArSelect {
                width: 230
                model: page.kb.switchKeys.filter(o => page.composeKey !== "compose:caps" || o.id.indexOf("caps") < 0)
                    .filter(o => page.composeKey !== "compose:ralt" || o.id !== "grp:toggle")
                    .map(o => ({ value: o.id, label: o.label }))
                value: page.switchKey
                onActivated: v => page.save(page.current, v, page.capsKey)
            }
        }
        SettingRow {
            searchKey: "input.caps"
            title: "Caps Lock key"
            desc: page.composeKey === "compose:caps" ? "Caps Lock is your Compose key." : "Many people make it a second Esc or Ctrl."
            resettable: false
            ArSelect {
                width: 230
                enabled: page.composeKey !== "compose:caps"
                model: [{ value: "", label: "Caps Lock" }].concat(page.kb.capsOptions.map(o => ({ value: o.id, label: o.label.replace(/^Make Caps Lock an additional /, "").replace(/^Caps Lock as /, "") })))
                value: page.capsKey
                onActivated: v => page.save(page.current, page.switchKey, v)
            }
        }
        SettingRow {
            searchKey: "input.compose"
            title: "Compose key"
            desc: "Press it, then two keys: ' then e types é, o then c types ©."
            resettable: false
            ArSelect {
                width: 230
                model: [{ value: "", label: "Off" }].concat((page.kb.composeKeys || []).map(o => ({ value: o.id, label: o.label })))
                value: page.composeKey
                onActivated: v => page.save(page.current, page.switchKey, page.capsKey, v)
            }
        }
        SettingRow {
            title: "Try your keyboard"
            resettable: false
            ArInput {
                width: 260
                placeholder: "Type here to try it"
                accessibleName: "Try your keyboard"
            }
        }
    }

    Group {
        title: "Typing"
        SettingRow {
            searchKey: "input.repeat"
            title: "Repeat delay"
            desc: Backend.opt("repeat_delay") + " ms before a held key starts repeating."
            keys: ["repeat_delay"]
            onResetRequested: Backend.reset(["repeat_delay"])
            ArSlider {
                accessibleName: "Repeat delay"
                valueText: value + " milliseconds"
                from: 150; to: 1000; stepSize: 10
                value: Backend.num("repeat_delay")
                onCommitted: v => Backend.set({ repeat_delay: Math.round(v) })
            }
        }
        SettingRow {
            title: "Repeat rate"
            desc: Backend.opt("repeat_rate") + " characters a second."
            keys: ["repeat_rate"]
            onResetRequested: Backend.reset(["repeat_rate"])
            ArSlider {
                accessibleName: "Repeat rate"
                valueText: value + " per second"
                from: 10; to: 60; stepSize: 1
                value: Backend.num("repeat_rate")
                onCommitted: v => Backend.set({ repeat_rate: Math.round(v) })
            }
        }
        SettingRow {
            searchKey: "input.numlock"
            title: "Num Lock on when you log in"
            keys: ["numlockon"]
            onResetRequested: Backend.reset(["numlockon"])
            RowSwitch {
                Accessible.name: "Num Lock on when you log in"
                checked: Backend.isOn("numlockon")
                onToggled: Backend.set({ numlockon: checked ? 1 : 0 })
            }
        }
    }

    Group {
        visible: page.devices.trackpad !== false
        title: "Touchpad"
        SettingRow {
            searchKey: "input.tap"
            title: "Tap to click"
            keys: ["tap_to_click"]
            onResetRequested: Backend.reset(["tap_to_click"])
            RowSwitch {
                Accessible.name: "Tap to click"
                checked: Backend.isOn("tap_to_click")
                onToggled: Backend.set({ tap_to_click: checked ? 1 : 0 })
            }
        }
        SettingRow {
            title: "Tap and drag"
            desc: "Tap, then keep your finger down to drag."
            keys: ["tap_and_drag"]
            enabled: Backend.isOn("tap_to_click")
            onResetRequested: Backend.reset(["tap_and_drag"])
            RowSwitch {
                Accessible.name: "Tap and drag"
                checked: Backend.isOn("tap_and_drag")
                onToggled: Backend.set({ tap_and_drag: checked ? 1 : 0 })
            }
        }
        SettingRow {
            searchKey: "input.natural"
            title: "Natural scrolling"
            desc: "Content moves with your fingers, like on a phone."
            keys: ["trackpad_natural_scrolling"]
            onResetRequested: Backend.reset(["trackpad_natural_scrolling"])
            RowSwitch {
                Accessible.name: "Natural scrolling on the touchpad"
                checked: Backend.isOn("trackpad_natural_scrolling")
                onToggled: Backend.set({ trackpad_natural_scrolling: checked ? 1 : 0 })
            }
        }
        SettingRow {
            searchKey: "input.typing"
            title: "Turn the touchpad off while typing"
            desc: "So your palm doesn’t move the pointer."
            keys: ["trackpad_disable_while_typing"]
            onResetRequested: Backend.reset(["trackpad_disable_while_typing"])
            RowSwitch {
                Accessible.name: "Turn the touchpad off while typing"
                checked: Backend.isOn("trackpad_disable_while_typing")
                onToggled: Backend.set({ trackpad_disable_while_typing: checked ? 1 : 0 })
            }
        }
        SettingRow {
            searchKey: "input.tpspeed"
            title: "Pointer speed"
            keys: ["trackpad_accel_speed"]
            onResetRequested: Backend.reset(["trackpad_accel_speed"])
            ArSlider {
                accessibleName: "Touchpad pointer speed"
                valueText: Math.round((value + 1) * 50) + " percent"
                from: -1; to: 1; stepSize: 0.1
                value: Backend.num("trackpad_accel_speed")
                onCommitted: v => Backend.set({ trackpad_accel_speed: v.toFixed(1) })
            }
        }
        SettingRow {
            title: "Pointer acceleration"
            desc: "Fast finger movements go further."
            keys: ["trackpad_accel_profile"]
            onResetRequested: Backend.reset(["trackpad_accel_profile"])
            RowSwitch {
                Accessible.name: "Touchpad pointer acceleration"
                checked: Backend.num("trackpad_accel_profile") === 2
                onToggled: Backend.set({ trackpad_accel_profile: checked ? 2 : 1 })
            }
        }
        SettingRow {
            title: "Scrolling speed"
            keys: ["trackpad_scroll_factor"]
            onResetRequested: Backend.reset(["trackpad_scroll_factor"])
            ArSlider {
                accessibleName: "Touchpad scrolling speed"
                valueText: Math.round(value * 100) + " percent"
                from: 0.2; to: 3; stepSize: 0.1
                value: Backend.num("trackpad_scroll_factor")
                onCommitted: v => Backend.set({ trackpad_scroll_factor: v.toFixed(1) })
            }
        }
        SettingRow {
            searchKey: "input.click"
            title: "Right click"
            keys: ["trackpad_click_method"]
            onResetRequested: Backend.reset(["trackpad_click_method"])
            ArSegmented {
                accessibleName: "Right click"
                model: [{ value: "1", label: "Bottom-right corner" }, { value: "2", label: "Two-finger click" }]
                value: Backend.opt("trackpad_click_method")
                onActivated: v => Backend.set({ trackpad_click_method: v })
            }
        }
        SettingRow {
            title: "Middle click with both buttons"
            keys: ["trackpad_middle_button_emulation"]
            onResetRequested: Backend.reset(["trackpad_middle_button_emulation"])
            RowSwitch {
                Accessible.name: "Middle click with both buttons"
                checked: Backend.isOn("trackpad_middle_button_emulation")
                onToggled: Backend.set({ trackpad_middle_button_emulation: checked ? 1 : 0 })
            }
        }
        SettingRow {
            title: "Turn the touchpad off"
            desc: "For when you use a mouse. Keep a mouse plugged in before you switch this on."
            keys: ["disable_trackpad"]
            onResetRequested: Backend.reset(["disable_trackpad"])
            RowSwitch {
                Accessible.name: "Turn the touchpad off"
                checked: Backend.isOn("disable_trackpad")
                onToggled: Backend.set({ disable_trackpad: checked ? 1 : 0 }, checked ? "Touchpad off" : "Touchpad on")
            }
        }
    }

    Group {
        visible: page.devices.mouse !== false
        title: "Mouse"
        SettingRow {
            searchKey: "input.mousespeed"
            title: "Pointer speed"
            keys: ["mouse_accel_speed"]
            onResetRequested: Backend.reset(["mouse_accel_speed"])
            ArSlider {
                accessibleName: "Mouse pointer speed"
                valueText: Math.round((value + 1) * 50) + " percent"
                from: -1; to: 1; stepSize: 0.1
                value: Backend.num("mouse_accel_speed")
                onCommitted: v => Backend.set({ mouse_accel_speed: v.toFixed(1) })
            }
        }
        SettingRow {
            title: "Pointer acceleration"
            desc: "Turn it off for games and precise drawing."
            keys: ["mouse_accel_profile"]
            onResetRequested: Backend.reset(["mouse_accel_profile"])
            RowSwitch {
                Accessible.name: "Mouse pointer acceleration"
                checked: Backend.num("mouse_accel_profile") === 2
                onToggled: Backend.set({ mouse_accel_profile: checked ? 2 : 1 })
            }
        }
        SettingRow {
            title: "Natural scrolling"
            keys: ["mouse_natural_scrolling"]
            onResetRequested: Backend.reset(["mouse_natural_scrolling"])
            RowSwitch {
                Accessible.name: "Natural scrolling with the mouse"
                checked: Backend.isOn("mouse_natural_scrolling")
                onToggled: Backend.set({ mouse_natural_scrolling: checked ? 1 : 0 })
            }
        }
        SettingRow {
            title: "Scrolling speed"
            keys: ["axis_scroll_factor"]
            onResetRequested: Backend.reset(["axis_scroll_factor"])
            ArSlider {
                accessibleName: "Mouse scrolling speed"
                valueText: Math.round(value * 100) + " percent"
                from: 0.2; to: 3; stepSize: 0.1
                value: Backend.num("axis_scroll_factor")
                onCommitted: v => Backend.set({ axis_scroll_factor: v.toFixed(1) })
            }
        }
        SettingRow {
            searchKey: "input.lefthanded"
            title: "Left-handed"
            desc: "Swaps the left and right buttons."
            keys: ["mouse_left_handed"]
            onResetRequested: Backend.reset(["mouse_left_handed"])
            RowSwitch {
                Accessible.name: "Left-handed mouse"
                checked: Backend.isOn("mouse_left_handed")
                onToggled: Backend.set({ mouse_left_handed: checked ? 1 : 0 })
            }
        }
    }

    PickerDialog {
        id: layoutPicker
        title: "Add a keyboard layout"
        items: page.kb.layouts.filter(l => !page.current.some(c => c.layout === l.id)).map(l => ({ value: l.id, label: l.label, desc: l.id }))
        actionText: "Add layout"
        onPicked: v => page.save(page.current.concat([{ layout: v, variant: "" }]), page.switchKey, page.capsKey)
    }
}
