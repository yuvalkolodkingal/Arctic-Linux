// Power and lock: when the screen locks and the computer suspends when you're away (swayidle,
// started by `arctic-session idle`, reads ~/.config/arctic/idle.conf), the power mode
// (powerprofilesctl, from tuned-ppd), and what closing the lid does (systemd-logind).
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

    Group {
        title: "Laptop lid"
        SettingRow {
            searchKey: "power.lid"
            title: "Closing the lid"
            desc: "Suspends the computer (and locks it first). With another screen plugged in and the laptop on power, closing the lid doesn’t suspend. This is decided by systemd-logind (HandleLidSwitch in /etc/systemd/logind.conf)."
            resettable: false
        }
    }
}
