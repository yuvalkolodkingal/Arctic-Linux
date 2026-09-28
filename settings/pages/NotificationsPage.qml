// Notifications: do not disturb (now, for a while, or on a schedule), whether the notification
// centre keeps its history across restarts, and what each app may do. The shell's notification
// server (shell/NotificationService.qml) reads ~/.config/arctic/notifications.json, which the
// `notification-*` commands write; do not disturb itself goes through arctic-dnd.
pragma ComponentBehavior: Bound
import QtQuick
import ".."
import "../components"

Page {
    id: page
    title: "Notifications"
    lede: "Pop-ups, the notification centre on the bell (Super + Alt + N) and do not disturb."
    property var info: ({ owned: true, dnd: false, history: true, schedule: { enabled: false, from: "22:00", to: "07:00" }, apps: [] })
    readonly property var times: {
        const out = [];
        for (let h = 0; h < 24; h++)
            for (let m = 0; m < 60; m += 30) {
                const t = (h < 10 ? "0" : "") + h + ":" + (m ? "30" : "00");
                out.push({ value: t, label: t });
            }
        return out;
    }
    // What an app may do, as one choice (the four switches of its rule in notifications.json).
    readonly property var presets: [
        { value: "normal", label: "Pop-ups, kept in the centre", rule: { toasts: true, history: true, allow_during_dnd: false, silence_urgent: false } },
        { value: "always", label: "Pop-ups, even during do not disturb", rule: { toasts: true, history: true, allow_during_dnd: true, silence_urgent: false } },
        { value: "quiet", label: "Pop-ups, never during do not disturb", rule: { toasts: true, history: true, allow_during_dnd: false, silence_urgent: true } },
        { value: "centre", label: "Only in the notification centre", rule: { toasts: false, history: true, allow_during_dnd: false, silence_urgent: false } },
        { value: "brief", label: "Pop-ups only, not kept", rule: { toasts: true, history: false, allow_during_dnd: false, silence_urgent: false } },
        { value: "off", label: "Nothing", rule: { toasts: false, history: false, allow_during_dnd: false, silence_urgent: false } }
    ]
    function presetOf(rule) {
        for (let i = 0; i < presets.length; i++) {
            const p = presets[i].rule;
            if (p.toasts === rule.toasts && p.history === rule.history && p.allow_during_dnd === rule.allow_during_dnd && p.silence_urgent === rule.silence_urgent)
                return presets[i].value;
        }
        return "custom";
    }
    function setPreset(app, value) {
        const preset = presets.find(p => p.value === value);
        if (!preset)
            return;
        const args = ["notification-rule-set", app];
        Object.keys(preset.rule).forEach(k => args.push(k, preset.rule[k] ? "on" : "off"));
        apply(args, "Saved");
    }
    function load() {
        Backend.call(["notifications"], r => { if (r.ok) page.info = r; }, true);
    }
    function apply(args, message) {
        Backend.call(args, r => {
            if (r.ok) {
                page.info = r;
                if (message)
                    Backend.notify("success", message, false);
            } else {
                page.load();
            }
        });
    }
    onShown: load()

    ArBanner {
        visible: page.info.owned === false
        width: parent.width
        kind: "info"
        text: "Another notification service shows your notifications right now, not the Arctic shell. Do not disturb still works; the schedule and the app choices apply when the shell shows them."
    }

    Group {
        title: "Do not disturb"
        desc: "Pop-ups wait quietly in the notification centre. Urgent notifications and Arctic’s own alerts, like a battery about to run out, still show."
        SettingRow {
            searchKey: "notifications.dnd"
            title: "Do not disturb"
            desc: page.info.dnd ? "On. Right-click the bell or press Super + Shift + N to turn it off." : "Off"
            resettable: false
            RowSwitch {
                checked: page.info.dnd === true
                Accessible.name: "Do not disturb"
                onToggled: page.apply(["dnd-set", checked ? "on" : "off"], "")
            }
        }
        SettingRow {
            visible: page.info.owned === true
            title: "Turn it on for a while"
            desc: "It turns itself off again. Tomorrow means 08:00."
            resettable: false
            Row {
                spacing: Theme.space2
                ArButton {
                    text: "For 1 hour"
                    gapColor: Theme.surfaceRaised
                    onClicked: page.apply(["dnd-set", "1h"], "Do not disturb is on for an hour")
                }
                ArButton {
                    text: "Until tomorrow"
                    gapColor: Theme.surfaceRaised
                    onClicked: page.apply(["dnd-set", "tomorrow"], "Do not disturb is on until tomorrow")
                }
            }
        }
        SettingRow {
            searchKey: "notifications.schedule"
            title: "On a schedule"
            desc: page.info.schedule.enabled ? "Every day from " + page.info.schedule.from + " to " + page.info.schedule.to + "." : "Every day at the same time, for example at night."
            resettable: false
            RowSwitch {
                checked: page.info.schedule.enabled === true
                Accessible.name: "Do not disturb on a schedule"
                onToggled: page.apply(["notification-set", "schedule", checked ? "on" : "off"], "")
            }
        }
        SettingRow {
            visible: page.info.schedule.enabled === true
            title: "From"
            resettable: false
            ArSelect {
                width: 140
                model: page.times
                value: page.info.schedule.from
                onActivated: v => page.apply(["notification-set", "schedule-from", v], "Saved")
            }
        }
        SettingRow {
            visible: page.info.schedule.enabled === true
            title: "To"
            resettable: false
            ArSelect {
                width: 140
                model: page.times
                value: page.info.schedule.to
                onActivated: v => page.apply(["notification-set", "schedule-to", v], "Saved")
            }
        }
    }

    Group {
        title: "History"
        SettingRow {
            searchKey: "notifications.history"
            title: "Keep notifications after a restart"
            desc: "The notification centre keeps the last 50. They are saved in ~/.local/state/arctic/notifications, only for you."
            resettable: false
            RowSwitch {
                checked: page.info.history === true
                Accessible.name: "Keep notifications after a restart"
                onToggled: page.apply(["notification-set", "history", checked ? "on" : "off"], "")
            }
        }
        SettingRow {
            title: "Clear the notification centre"
            resettable: false
            ArButton {
                text: "Clear"
                iconName: "trash"
                gapColor: Theme.surfaceRaised
                onClicked: page.apply(["notification-history-clear"], "Notifications cleared")
            }
        }
    }

    Group {
        title: "Apps"
        SettingRow {
            searchKey: "notifications.apps"
            title: "What each app may do"
            desc: page.info.apps.length ? "Apps are listed once they have sent a notification. “Never during do not disturb” also hides an app’s urgent notifications, for apps that mark everything urgent."
                                        : "No app has sent a notification yet. Apps show up here once they have."
            resettable: false
        }
        Repeater {
            model: page.info.apps
            SettingRow {
                id: appRow
                required property var modelData
                readonly property string preset: page.presetOf(modelData.rule)
                title: modelData.name
                desc: modelData.desktopEntry && modelData.desktopEntry !== modelData.name ? modelData.desktopEntry : ""
                resettable: false
                ArSelect {
                    width: 300
                    model: appRow.preset === "custom" ? page.presets.concat([{ value: "custom", label: "Your own mix (notifications.json)" }]) : page.presets
                    value: appRow.preset
                    onActivated: v => page.setPreset(appRow.modelData.key, v)
                }
            }
        }
    }
}
