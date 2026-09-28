// Power and lock: when the screen locks and the computer suspends when you're away (swayidle,
// started by `arctic-session idle`, reads ~/.config/arctic/idle.conf), the power mode
// (powerprofilesctl, from tuned-ppd), and what closing the lid does (arctic-display; logind
// suspends unless `arctic-session lid` holds its lid switch for "lock" or "screen off").
pragma ComponentBehavior: Bound
import QtQuick
import ".."
import "../components"

Page {
    id: page
    title: "Power and lock"
    lede: "What happens when you step away, and how hard the computer works."
    property var idle: ({ lock: 300, suspend: 900, live: false })
    property var profile: ({ available: false })
    readonly property var lockChoices: [0, 60, 120, 180, 300, 600, 900, 1800]
    readonly property var suspendChoices: [0, 300, 600, 900, 1200, 1800, 2700, 3600, 7200]
    function words(s) {
        if (s === 0)
            return "Never";
        return s >= 3600 ? (s / 3600) + (s === 3600 ? " hour" : " hours") : (s / 60) + (s === 60 ? " minute" : " minutes");
    }
    function setIdle(lock, suspend) {
        Backend.call(["idle-set", String(lock), String(suspend)], r => {
            if (r.ok) {
                page.idle = r;
                Backend.notify("success", "Saved", false);
            } else {
                Backend.call(["idle"], r2 => { if (r2.ok) page.idle = r2; });
            }
        });
    }
    onShown: {
        Backend.call(["idle"], r => { if (r.ok) page.idle = r; });
        Backend.call(["power-profile"], r => { if (r.ok) page.profile = r; }, true);
    }

    ArBanner {
        visible: page.idle.live === true
        width: parent.width
        kind: "info"
        text: "The live session never locks or suspends on its own. These settings apply once Arctic Linux is installed."
    }

    Group {
        title: "When you’re away"
        desc: "The screen always locks before the computer sleeps."
        SettingRow {
            searchKey: "power.lock"
            title: "Lock the screen after"
            resettable: false
            ArSelect {
                width: 200
                model: page.lockChoices.map(s => ({ value: String(s), label: page.words(s) }))
                value: String(page.idle.lock)
                onActivated: v => page.setIdle(Number(v), page.idle.suspend && page.idle.suspend < Number(v) ? Number(v) : page.idle.suspend)
            }
        }
        SettingRow {
            searchKey: "power.suspend"
            title: "Suspend after"
            desc: "Suspending saves power; open the lid or press a key to wake up."
            resettable: false
            ArSelect {
                width: 200
                model: page.suspendChoices.filter(s => s === 0 || !page.idle.lock || s >= page.idle.lock).map(s => ({ value: String(s), label: page.words(s) }))
                value: String(page.idle.suspend)
                onActivated: v => page.setIdle(page.idle.lock, Number(v))
            }
        }
    }

    // Stream 5: keep awake for a while (arctic-keep-awake, also Super + Ctrl + I).
    Group {
        id: awake
        property var state: ({ helper: false, on: false })
        function load() {
            Backend.call(["keep-awake"], r => { if (r.ok) awake.state = r; }, true);
        }
        Component.onCompleted: load()
        Timer { interval: 30000; repeat: true; running: awake.state.on === true; onTriggered: awake.load() }
        visible: state.helper === true && page.idle.live !== true
        title: "Keep awake"
        SettingRow {
            searchKey: "power.awake"
            title: "Keep the computer awake"
            desc: awake.state.on ? (awake.state.until ? "On until " + awake.state.untilText : "On until you turn it off") + ": the screen doesn’t lock and the computer doesn’t sleep."
                : "For a presentation or a long download: no lock and no sleep for a while. Super\u00a0+\u00a0Ctrl\u00a0+\u00a0I turns it on and off."
            resettable: false
            ArSelect {
                width: 200
                model: (awake.state.on ? [{ value: "now", label: awake.state.until ? "Until " + awake.state.untilText : "Until turned off" }] : [])
                    .concat([{ value: "off", label: "Off" }, { value: "30", label: "30 minutes" }, { value: "60", label: "1 hour" },
                        { value: "120", label: "2 hours" }].concat(awake.state.on && !awake.state.until ? [] : [{ value: "0", label: "Until turned off" }]))
                value: awake.state.on ? "now" : "off"
                onActivated: v => {
                    if (v === "now")
                        return;
                    Backend.call(["keep-awake"].concat(v === "off" ? ["off"] : v === "0" ? ["on"] : ["on", v]), r => { if (r.ok) awake.state = Object.assign({ helper: true }, r); });
                }
            }
        }
    }

    // Stream 5: times on battery, dimming and screens off (idle.conf's other keys; arctic_system.py
    // idle-more, `arctic-session idle` reads them). Hidden in the live session.
    Group {
        id: battery
        property var more: ({ battery: false, live: true })
        function load() {
            Backend.call(["idle-more"], r => { if (r.ok) battery.more = r; }, true);
        }
        function change(what, value) {
            Backend.call(["idle-more-set", what, String(value)], r => {
                if (r.ok) {
                    battery.more = r;
                    Backend.notify("success", "Saved", false);
                } else {
                    battery.load();
                }
            });
        }
        function choices(list, lock) {
            return [{ value: "same", label: "Same as plugged in" }].concat(
                list.filter(s => s === 0 || !lock || s >= lock).map(s => ({ value: String(s), label: page.words(s) })));
        }
        Component.onCompleted: load()
        visible: more.battery === true && more.live !== true
        title: "On battery"
        desc: "Shorter times save power. " + (more.onBattery ? "Running on battery now." : "Plugged in now.")
        SettingRow {
            searchKey: "power.battery.times"
            title: "Lock the screen after"
            resettable: false
            ArSelect {
                width: 200
                model: battery.choices(page.lockChoices, 0)
                value: battery.more.lockBattery === null || battery.more.lockBattery === undefined ? "same" : String(battery.more.lockBattery)
                onActivated: v => battery.change("lock-battery", v)
            }
        }
        SettingRow {
            title: "Suspend after"
            resettable: false
            ArSelect {
                width: 200
                model: battery.choices(page.suspendChoices, battery.more.lockBattery === null || battery.more.lockBattery === undefined ? page.idle.lock : battery.more.lockBattery)
                value: battery.more.suspendBattery === null || battery.more.suspendBattery === undefined ? "same" : String(battery.more.suspendBattery)
                onActivated: v => battery.change("suspend-battery", v)
            }
        }
    }

    Group {
        visible: battery.more.live !== true && (battery.more.canDim === true || battery.more.canScreenOff === true)
        title: "Around the lock"
        SettingRow {
            searchKey: "power.dim"
            visible: battery.more.canDim === true
            title: "Dim the screen before it locks"
            desc: "Half as bright 30 seconds before; a key or the mouse brings it back."
            resettable: false
            RowSwitch {
                Accessible.name: "Dim the screen before it locks"
                checked: battery.more.dim === true
                onToggled: battery.change("dim", checked ? "on" : "off")
            }
        }
        SettingRow {
            searchKey: "power.screenoff"
            visible: battery.more.canScreenOff === true
            title: "Turn the screens off after locking"
            desc: "A key or the mouse turns them back on."
            resettable: false
            ArSelect {
                width: 200
                model: [0, 30, 60, 120, 300, 600].map(s => ({ value: String(s), label: s === 0 ? "Never" : s < 60 ? s + " seconds" : page.words(s) }))
                value: String(battery.more.screenOff === undefined ? 60 : battery.more.screenOff)
                onActivated: v => battery.change("screen-off", v)
            }
        }
    }

    Group {
        visible: page.profile.available === true
        title: "Power mode"
        SettingRow {
            searchKey: "power.profile"
            title: "Power mode"
            desc: page.profile.current === "power-saver" ? "Longer battery life, a bit slower." : page.profile.current === "performance" ? "Fastest, uses more power and makes more heat." : "Fast when it needs to be, quiet otherwise."
            resettable: false
            ArSegmented {
                accessibleName: "Power mode"
                model: (page.profile.profiles || []).map(p => ({ value: p, label: ({ "power-saver": "Power saver", balanced: "Balanced", performance: "Performance" })[p] || p }))
                value: page.profile.current || "balanced"
                onActivated: v => Backend.call(["power-profile", v], r => { if (r.ok) page.profile = r; })
            }
        }
    }

    // Closing the lid (arctic-display lid-closed; ~/.config/arctic/lid.conf). Only on laptops.
    Group {
        id: lidGroup
        property var lid: ({ present: false, whenClosed: "suspend" })
        visible: lid.present === true
        title: "Laptop lid"
        Component.onCompleted: Backend.call(["lid"], r => { if (r.ok) lidGroup.lid = r; }, true)
        SettingRow {
            searchKey: "power.lid"
            title: "When you close the lid"
            desc: "With another screen plugged in, closing the lid turns the laptop screen off and your windows move to the other screen."
            resettable: false
            ArSelect {
                width: 260
                model: [{ value: "suspend", label: "Suspend" }, { value: "lock", label: "Lock and turn the screen off" },
                    { value: "screen-off", label: "Keep running, screen off" }]
                value: lidGroup.lid.whenClosed || "suspend"
                onActivated: v => Backend.call(["lid-set", v], r => {
                    if (r.ok) {
                        lidGroup.lid = r;
                        Backend.notify("success", "Saved", false);
                    }
                })
            }
        }
    }
}
