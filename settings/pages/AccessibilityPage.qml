// Accessibility: high contrast (arctic-theme contrast), bigger text and pointer, less motion, and
// the pointer from the keyboard
// (wl-kbptr, Super + Alt + K). The motion, text size and pointer rows came from Appearance
// (their commands are unchanged: motion-set, text-scale, set cursor_size / cursor_theme). The
// last group says plainly what this desktop can't offer yet, rather than hiding it.
pragma ComponentBehavior: Bound
import QtQuick
import ".."
import "../components"

Page {
    id: page
    title: "Accessibility"
    lede: "Make things bigger, calmer and easier to reach from the keyboard."

    property var motion: ({ available: true, reduced: false })
    property var textScale: ({ available: false, value: 1 })
    property var cursors: []
    property var access: ({ kbptr: false, contrast: null })

    onShown: {
        Backend.call(["motion"], r => { if (r.ok) page.motion = r; });
        Backend.call(["text-scale"], r => { if (r.ok) page.textScale = r; }, true);
        Backend.call(["cursor-themes"], r => { if (r.ok) page.cursors = r.themes; }, true);
        Backend.call(["accessibility"], r => { if (r.ok) page.access = r; }, true);
    }

    Group {
        title: "Seeing"
        SettingRow {
            searchKey: "accessibility.contrast"
            visible: page.access.contrast === true || page.access.contrast === false
            title: "High contrast"
            desc: "Stronger text, lines and focus rings in whatever theme you use, the bar and apps too."
            resettable: false
            RowSwitch {
                checked: page.access.contrast === true
                Accessible.name: "High contrast"
                onToggled: Backend.call(["contrast-set", checked ? "off" : "on"], r => {
                    if (r.ok) {
                        page.access = r;
                        Theme.reload();
                    } else {
                        checked = page.access.contrast === true;
                    }
                })
            }
        }
        SettingRow {
            searchKey: "accessibility.textsize"
            visible: page.textScale.available === true
            title: "Text size in apps"
            desc: "For GTK apps such as Files and most dialogs. The bar and menus keep their size."
            ArSelect {
                width: 180
                model: [{ value: "1", label: "Default" }, { value: "1.1", label: "110%" }, { value: "1.25", label: "125%" },
                    { value: "1.5", label: "150%" }, { value: "1.75", label: "175%" }, { value: "2", label: "200%" }]
                value: String(Math.round((page.textScale.value || 1) * 100) / 100)
                onActivated: v => Backend.call(["text-scale", v], r => {
                    if (r.ok) {
                        page.textScale = r;
                        Backend.notify("success", "Text size changed. Apps that are open may need a restart.", false);
                    }
                })
            }
        }
        SettingRow {
            searchKey: "accessibility.cursor"
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

    Group {
        title: "Motion"
        SettingRow {
            searchKey: "accessibility.motion"
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
    }

    Group {
        title: "Keyboard"
        SettingRow {
            searchKey: "accessibility.kbptr"
            title: "Keyboard pointer"
            desc: page.access.kbptr ? "Super + Alt + K labels the screen: type a label to move the pointer there, then click with the keyboard. The key again closes it."
                                    : "Move and click the pointer from the keyboard. Needs wl-kbptr: install it with Get apps (Super + Shift + A)."
            resettable: false
            Row {
                spacing: Theme.space2
                ArKbd { text: "Super + Alt + K"; anchors.verticalCenter: parent.verticalCenter }
                ArButton {
                    text: page.access.kbptr ? "Try it" : "Get it"
                    gapColor: Theme.surfaceRaised
                    onClicked: page.access.kbptr ? Backend.launch(["arctic-kbptr"]) : Backend.launch(["arctic-shell-ipc", "apps", "install"])
                }
            }
        }
    }

    Group {
        title: "Not available yet"
        SettingRow {
            searchKey: "accessibility.reader"
            title: "Screen reader"
            desc: "Orca isn't reliable on this kind of desktop yet: compositors like Mango don't give it the keyboard access it needs."
            resettable: false
        }
        SettingRow {
            searchKey: "accessibility.zoom"
            title: "Magnifier"
            desc: "Mango has no screen magnifier yet. Larger text and a larger pointer are above."
            resettable: false
        }
        SettingRow {
            searchKey: "accessibility.osk"
            title: "On-screen keyboard"
            desc: "No on-screen keyboard that works on this desktop is packaged for Fedora 44 yet."
            resettable: false
        }
    }
}
