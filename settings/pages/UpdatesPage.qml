// Updates: Arctic's updater (arctic-update): its state (idle, checking, downloading, ready,
// failed), check now, restart and install, the channel and automatic downloads. Without
// arctic-update this page says how to update instead. "Apps and firmware": Flatpak apps (updated
// daily in place by arctic-flatpak-update.timer, or now) and fwupd's firmware updates.
pragma ComponentBehavior: Bound
import QtQuick
import ".."
import "../components"

Page {
    id: page
    title: "Updates"
    lede: "Security fixes and new versions of your apps and of Arctic Linux."
    property var up: ({ available: true, state: "idle" })
    property bool requestPending: false
    readonly property bool active: requestPending || up.state === "checking" || up.state === "downloading"
    function load() {
        Backend.call(["updates"], r => { if (r.ok) page.up = r; }, true);
    }
    function run(args, message) {
        page.requestPending = true;
        Backend.call(["update-run"].concat(args), r => {
            page.requestPending = false;
            if (r.ok) {
                page.up = r;
                if (message)
                    Backend.notify("success", message, false);
            }
            page.load();
        });
    }
    property var more: ({ available: false, flatpak: false, apps: null, firmware: { available: false, devices: [] } })
    function loadMore() {
        Backend.call(["more-updates"], r => { if (r.ok) page.more = r; }, true);
    }
    function when(iso) {
        return iso ? String(iso).replace("T", " at ").replace(/:\d\d(\.\d+)?([+-]\d\d:\d\d|Z)?$/, "") : "";
    }
    onShown: {
        load();
        loadMore();
    }
    Timer {
        interval: page.active ? 2000 : 15000
        repeat: true
        running: page.visible && page.up.available === true
        onTriggered: page.load()
    }
    readonly property var headline: ({
            idle: ["check-circle", Theme.success, "No updates at the last check"],
            checking: ["refresh", Theme.info, "Checking for updates…"],
            downloading: ["download", Theme.info, "Downloading updates…"],
            ready: ["download", Theme.accentText, "Updates are ready to install"],
            failed: ["alert", Theme.error, "The last update didn’t work"]
        })
    readonly property var head: requestPending && !["checking", "downloading"].includes(up.state)
        ? ["refresh", Theme.info, "Waiting for the update command…"]
        : up.held ? ["info", Theme.info, "Another offline update is waiting"]
        : up.state === "idle" && !up.checkedAt ? ["refresh", Theme.info, "Check for updates"]
        : headline[up.state] || headline.idle

    ArBanner {
        visible: page.up.available === false
        width: parent.width
        kind: "info"
        title: "Update from the terminal for now"
        text: page.up.reason || ""
        actionText: "Open a terminal with sudo dnf upgrade"
        onAction: Backend.launch(["arctic-open", "terminal", "--hold", "-e", "sudo", "dnf", "upgrade"])
    }

    // The next Fedora release, once Arctic's repository has it (arctic-update upgrade check).
    Group {
        id: upgradeGroup
        property var up: ({ available: false })
        visible: up.available === true && page.up.available === true
        title: "Fedora " + (up.next || "")
        Component.onCompleted: Backend.call(["upgrade", "check"], r => { if (r.ok) upgradeGroup.up = r; }, true)
        SettingRow {
            searchKey: "updates.upgrade"
            title: "Fedora " + (upgradeGroup.up.next || "") + " is ready for Arctic Linux"
            desc: "Opens a terminal window: it downloads a few gigabytes, then asks to restart and installs it. A snapshot is taken first, and your files and apps stay."
            resettable: false
            Row {
                spacing: Theme.space2
                ArButton {
                    text: "Release notes"
                    variant: "ghost"
                    iconRight: "external"
                    gapColor: Theme.surfaceRaised
                    onClicked: Backend.openUrl(upgradeGroup.up.notes || "")
                }
                ArButton {
                    text: "Upgrade…"
                    iconName: "terminal"
                    gapColor: Theme.surfaceRaised
                    onClicked: Backend.call(["upgrade", "download"], r => {})
                }
            }
        }
    }

    Group {
        visible: page.up.available === true
        title: "Status"
        SettingRow {
            searchKey: "updates.status"
            title: page.head[2]
            desc: {
                const u = page.up;
                if (u.held) return u.message || "Finish the pending offline update before checking again.";
                if (u.state === "ready")
                    return u.count + (u.count === 1 ? " update" : " updates") + " downloaded" + (u.stagedAt ? " " + u.stagedAt.replace("T", " at ").replace(/:\d\dZ?$/, "") : "") + ". They install while the computer restarts.";
                if (u.state === "downloading")
                    return u.count + " updates" + (u.downloadMb ? ", " + Math.round(u.downloadMb) + " MB" : "") + ". You can keep working.";
                if (u.state === "failed")
                    return u.error || "Check the network and try again.";
                return (u.checkedAt ? "Last checked " + page.when(u.checkedAt) + ". " : "")
                    + (u.channel === "testing" ? "You get test versions first." : "");
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
                    text: page.active ? "Checking…" : "Check now"
                    enabled: !page.active
                    gapColor: Theme.surfaceRaised
                    onClicked: page.run(["now"], "")
                }
                ArButton {
                    visible: page.up.state === "ready"
                    text: "Restart and install"
                    enabled: !page.active
                    variant: "primary"
                    gapColor: Theme.surfaceRaised
                    onClicked: page.run(["apply"], "Restarting to install updates…")
                }
            }
        }
        Text {
            visible: !!page.up.error && page.up.state !== "failed"
            width: parent.width
            text: page.up.error || ""
            wrapMode: Text.Wrap
            color: Theme.warning
            font.family: Theme.fontSans
            font.pixelSize: 13
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
        visible: !Backend.live
        title: "Nix packages"
        SettingRow {
            searchKey: "updates.nix"
            title: "Your Nix packages"
            desc: "Update or roll back your own profile in Get apps. Pinned inputs stay pinned. Nix itself updates with Arctic’s system packages."
            resettable: false
            ArButton {
                text: "Manage Nix updates"
                gapColor: Theme.surfaceRaised
                onClicked: Backend.launch(["arctic-shell-ipc", "apps", "open", "nix"])
            }
        }
        SettingRow {
            searchKey: "updates.nix.shared"
            title: "Shared installer Nix packages"
            desc: "Administrator action for installer fallbacks such as lazygit and yazi. Update replaces the installer's pin with the supported Nixpkgs release. Custom shared profiles are left for their administrator."
            resettable: false
            Row {
                spacing: Theme.space2
                ArButton {
                    text: "Update shared packages…"
                    gapColor: Theme.surfaceRaised
                    onClicked: Backend.launch(["arctic-open", "terminal", "--hold", "-e", "pkexec", "/usr/libexec/arctic-nix-system", "update"])
                }
                ArButton {
                    text: "Roll back…"
                    gapColor: Theme.surfaceRaised
                    onClicked: Backend.launch(["arctic-open", "terminal", "--hold", "-e", "pkexec", "/usr/libexec/arctic-nix-system", "rollback"])
                }
            }
        }
    }

    Group {
        visible: page.more.available === true && (page.more.flatpak === true || page.more.firmware.available === true)
        title: "Apps and firmware"
        SettingRow {
            visible: page.more.flatpak === true
            searchKey: "updates.apps"
            title: "Flatpak apps"
            desc: {
                const a = page.more.apps;
                const last = !a ? "" : a.state === "failed" ? a.message : (a.updated ? a.updated + (a.updated === 1 ? " app" : " apps") + " updated" : "Up to date") + ", " + page.when(a.checked_at) + ".";
                return (last ? last + " " : "") + (page.more.auto ? "They’re updated every day; an open app gets the new version when you restart it." : "Update them here or with arctic-update flatpak.");
            }
            resettable: false
            ArButton {
                text: "Update apps now"
                gapColor: Theme.surfaceRaised
                onClicked: Backend.call(["more-update-run", "apps"], r => {
                    if (r.ok)
                        Backend.notify("info", "Updating your apps. A notification says when they’re done.", false);
                })
            }
        }
        SettingRow {
            visible: page.more.firmware.available === true
            searchKey: "updates.firmware"
            title: "Firmware"
            desc: {
                const d = page.more.firmware.devices || [];
                if (d.length === 0)
                    return "The firmware of this computer’s devices is up to date, as far as fwupd knows.";
                return d.map(x => x.name + " " + x.version + " → " + x.update).join(", ") + "."
                    + (d.some(x => x.reboot) ? " The computer restarts to install it; plug in the charger first." : "");
            }
            resettable: false
            ArButton {
                visible: (page.more.firmware.devices || []).length > 0
                text: "Install in a terminal"
                iconName: "terminal"
                gapColor: Theme.surfaceRaised
                onClicked: Backend.call(["more-update-run", "firmware"], r => {})
            }
        }
    }

    // Snapshots (snapper, root's; listed through Settings' root helper, so only when asked).
    Group {
        id: snapGroup
        property var snaps: ({ asked: false })
        function load() {
            Backend.call(["snapshots"], r => { if (r.ok) snapGroup.snaps = Object.assign({ asked: true }, r); });
        }
        visible: page.up.available === true
        title: "Snapshots"
        desc: "Every update takes a snapshot of the system before and after, so you can undo one."
        SettingRow {
            searchKey: "updates.snapshots"
            visible: !snapGroup.snaps.asked
            title: "Undo an update"
            desc: "Lists the snapshots. It asks for your password."
            resettable: false
            ArButton {
                text: "Show snapshots"
                iconName: "clock"
                gapColor: Theme.surfaceRaised
                onClicked: snapGroup.load()
            }
        }
        SettingRow {
            visible: snapGroup.snaps.asked === true && snapGroup.snaps.config === false
            title: "Snapshots aren’t set up"
            desc: "The installer sets them up when the system is on btrfs. See the wiki’s Updates page."
            resettable: false
        }
        Repeater {
            model: snapGroup.snaps.asked ? (snapGroup.snaps.pairs || []).slice(0, 6) : []
            SettingRow {
                id: pairRow
                required property var modelData
                title: pairRow.modelData.description || "Software change"
                desc: String(pairRow.modelData.date || "").replace(/:\d\d$/, "") + " · snapshots " + pairRow.modelData.pre + " and " + pairRow.modelData.post
                resettable: false
                ArButton {
                    text: "Undo…"
                    size: "sm"
                    gapColor: Theme.surfaceRaised
                    onClicked: Backend.call(["snapshot-run", "undo", String(pairRow.modelData.pre), String(pairRow.modelData.post)], r => {
                        if (r.ok)
                            Backend.notify("info", "A terminal shows what’s undone. Restart afterwards.", false);
                    })
                }
            }
        }
        SettingRow {
            visible: snapGroup.snaps.asked === true && snapGroup.snaps.config === true
            title: "Take a snapshot now"
            desc: "Before you change something by hand, for example."
            resettable: false
            ArButton {
                text: "Take snapshot"
                gapColor: Theme.surfaceRaised
                onClicked: Backend.call(["snapshot-run", "create", "Taken in Settings"], r => {
                    if (r.ok) {
                        snapGroup.snaps = Object.assign({ asked: true }, r);
                        Backend.notify("success", "Snapshot taken", false);
                    }
                })
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
