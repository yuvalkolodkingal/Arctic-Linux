// Date and time: the time zone, network time and the clock (timedatectl → systemd-timedated),
// and the system language (localectl → systemd-localed). Both services ask for the password
// through polkit (the shell's dialog), so a change can take a moment. Night light's "sunset to
// sunrise" follows the time zone.
pragma ComponentBehavior: Bound
import QtQuick
import ".."
import "../components"

Page {
    id: page
    title: "Date and time"
    lede: "Your time zone, the clock and the language. Changing them asks for your password."
    property var info: ({ available: true, timezone: "", ntp: true, canNtp: true, zones: [], locale: "", locales: [], localectl: false })
    property bool busy: false
    function load(extra) {
        Backend.call(["datetime"].concat(extra || []), r => {
            if (r.ok)
                page.info = extra ? r : Object.assign({}, r, { zones: page.info.zones, locales: page.info.locales });
        });
    }
    function change(what, value, message) {
        page.busy = true;
        Backend.call(["datetime-set", what, value], r => {
            page.busy = false;
            if (r.ok) {
                page.info = Object.assign({}, r, { zones: page.info.zones, locales: page.info.locales });
                Backend.notify("success", message, false);
            } else {
                page.load();
            }
        });
    }
    function languageName(code) {
        const name = Qt.locale(String(code).split(".")[0]).nativeLanguageName;
        const territory = Qt.locale(String(code).split(".")[0]).nativeTerritoryName;
        return name ? name + (territory ? " (" + territory + ")" : "") : code;
    }
    onShown: load(["zones", "locales"])
    Timer {
        // The clock on the page moves with the real one.
        interval: 30000
        running: page.visible
        repeat: true
        onTriggered: page.load()
    }

    ArBanner {
        visible: page.info.available === false
        width: parent.width
        kind: "warning"
        text: "Settings can’t reach systemd-timedated, which changes the time zone and the clock."
    }

    Group {
        visible: page.info.available !== false
        title: "Time"
        SettingRow {
            searchKey: "datetime.timezone"
            title: "Time zone"
            desc: (page.info.now ? "It’s " + page.info.now.split(" ")[1] + " on " + page.info.now.split(" ")[0] + " (UTC" + String(page.info.offset).replace(/^([+-]\d\d)(\d\d)$/, "$1:$2") + "). " : "")
                + "Night light’s sunset and sunrise follow it."
            resettable: false
            ArButton {
                text: String(page.info.timezone || "Choose…").replace(/_/g, " ")
                iconName: "globe"
                enabled: !page.busy && (page.info.zones || []).length > 0
                gapColor: Theme.surfaceRaised
                onClicked: zonePicker.start()
            }
        }
        SettingRow {
            searchKey: "datetime.ntp"
            visible: page.info.canNtp !== false
            title: "Set the time automatically"
            desc: page.info.ntp ? (page.info.ntpSynced ? "From time servers on the internet. The clock is in sync." : "From time servers on the internet, once you’re online.")
                : "The clock keeps the time you set."
            resettable: false
            RowSwitch {
                Accessible.name: "Set the time automatically"
                enabled: !page.busy
                checked: page.info.ntp === true
                onToggled: page.change("ntp", checked ? "on" : "off", checked ? "The time is set automatically" : "Automatic time is off")
            }
        }
        SettingRow {
            searchKey: "datetime.clock"
            visible: page.info.ntp === false
            title: "Date and time"
            desc: "For example 2026-09-28 21:30 (a 24-hour clock)."
            resettable: false
            Row {
                spacing: Theme.space2
                ArInput {
                    id: clockField
                    width: 190
                    text: page.info.now || ""
                    accessibleName: "Date and time"
                    onAccepted: page.change("time", text.trim(), "Clock set")
                }
                ArButton {
                    text: "Set"
                    enabled: !page.busy
                    gapColor: Theme.surfaceRaised
                    onClicked: page.change("time", clockField.text.trim(), "Clock set")
                }
            }
        }
    }

    Group {
        visible: page.info.localectl === true && (page.info.locales || []).length > 0
        title: "Language"
        SettingRow {
            searchKey: "datetime.language"
            title: "Language"
            desc: "The language apps use for everyone on this computer, and how they write dates and numbers. It changes the next time you log in."
            resettable: false
            ArButton {
                text: page.info.locale ? page.languageName(page.info.locale) : "Choose…"
                iconName: "language"
                enabled: !page.busy
                gapColor: Theme.surfaceRaised
                onClicked: languagePicker.start()
            }
        }
    }

    PickerDialog {
        id: zonePicker
        title: "Time zone"
        actionText: "Choose"
        items: (page.info.zones || []).map(z => ({ value: z, label: z.replace(/_/g, " ") }))
        onPicked: v => page.change("timezone", v, "Time zone changed to " + v.replace(/_/g, " "))
    }
    PickerDialog {
        id: languagePicker
        title: "Language"
        actionText: "Choose"
        items: (page.info.locales || []).map(l => ({ value: l, label: page.languageName(l), desc: l }))
        onPicked: v => page.change("locale", v, "Language changed. It applies the next time you log in.")
    }
}
