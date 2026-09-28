// Updates: Arctic's updater (arctic-update): its state (idle, checking, downloading, ready,
// failed), check now, restart and install, the channel and automatic downloads. Without
// arctic-update this page says how to update instead.
pragma ComponentBehavior: Bound
import QtQuick
import ".."
import "../components"

Page {
    id: page
    title: "Updates"
    lede: "Security fixes and new versions of your apps and of Arctic Linux."
    property var up: ({ available: true, state: "idle" })
    readonly property bool active: up.state === "checking" || up.state === "downloading"
    function load() {
        Backend.call(["updates"], r => { if (r.ok) page.up = r; }, true);
    }
    function run(args, message) {
        Backend.call(["update-run"].concat(args), r => {
            if (r.ok) {
                page.up = r;
                if (message)
                    Backend.notify("success", message, false);
            }
        });
    }
    onShown: load()
    Timer {
        interval: page.active ? 2000 : 15000
        repeat: true
        running: page.visible && page.up.available === true
        onTriggered: page.load()
    }
    readonly property var headline: ({
            idle: ["check-circle", Theme.success, "Arctic Linux is up to date"],
            checking: ["refresh", Theme.info, "Checking for updates…"],
            downloading: ["download", Theme.info, "Downloading updates…"],
            ready: ["download", Theme.accentText, "Updates are ready to install"],
            failed: ["alert", Theme.error, "The last update didn’t work"]
        })
    readonly property var head: headline[up.state] || headline.idle

    ArBanner {
        visible: page.up.available === false
        width: parent.width
        kind: "info"
        title: "Update from the terminal for now"
        text: page.up.reason || ""
        actionText: "Open a terminal with sudo dnf upgrade"
        onAction: Backend.launch(["arctic-open", "terminal", "--hold", "-e", "sudo", "dnf", "upgrade"])
    }

    Group {
        visible: page.up.available === true
        title: "Status"
        SettingRow {
            searchKey: "updates.status"
            title: page.head[2]
            desc: {
                const u = page.up;
                if (u.state === "ready")
                    return u.count + (u.count === 1 ? " update" : " updates") + " downloaded" + (u.stagedAt ? " " + u.stagedAt.replace("T", " at ").replace(/:\d\dZ?$/, "") : "") + ". They install while the computer restarts.";
                if (u.state === "downloading")
                    return u.count + " updates" + (u.downloadMb ? ", " + Math.round(u.downloadMb) + " MB" : "") + ". You can keep working.";
                if (u.state === "failed")
                    return u.error || "Check the network and try again.";
                return u.channel === "testing" ? "You get test versions first." : "";
            }
            resettable: false
            Row {
                spacing: Theme.space2
                Icon {
                    name: page.head[0]
                    size: 22
                    color: page.head[1]
                    anchors.verticalCenter: parent.verticalCenter
                }
                ArButton {
                    visible: page.up.state !== "ready"
                    text: page.active ? "Checking…" : "Check now"
                    enabled: !page.active
                    gapColor: Theme.surfaceRaised
                    onClicked: page.run(["now"], "")
                }
                ArButton {
                    visible: page.up.state === "ready"
                    text: "Restart and install"
                    variant: "primary"
                    gapColor: Theme.surfaceRaised
                    onClicked: page.run(["apply"], "Restarting to install updates…")
                }
            }
        }
        Repeater {
            model: page.up.state === "ready" ? (page.up.packages || []).slice(0, 8) : []
            SettingRow {
                required property var modelData
                title: typeof modelData === "string" ? modelData : (modelData.name || "")
                desc: typeof modelData === "string" ? "" : (modelData.version || "")
                resettable: false
            }
        }
    }

    Group {
        visible: page.up.available === true
        title: "How updates come"
        SettingRow {
            searchKey: "updates.auto"
            title: "Download updates automatically"
            desc: "In the background. They only install when you restart."
            resettable: false
            RowSwitch {
                Accessible.name: "Download updates automatically"
                checked: page.up.auto === true
                onToggled: page.run(["auto", checked ? "on" : "off"], checked ? "Automatic downloads on" : "Automatic downloads off")
            }
        }
        SettingRow {
            searchKey: "updates.channel"
            title: "Channel"
            desc: page.up.channel === "testing" ? "Testing gets new versions a few days early. Things can break." : "Stable gets updates once they’ve been tested."
            resettable: false
            ArSegmented {
                accessibleName: "Update channel"
                model: [{ value: "stable", label: "Stable" }, { value: "testing", label: "Testing" }]
                value: page.up.channel || "stable"
                onActivated: v => page.run(["channel", v], v === "testing" ? "You’re on the testing channel" : "You’re on the stable channel")
            }
        }
    }
}
