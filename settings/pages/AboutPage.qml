// About: which Arctic Linux this is, on which Fedora, the hardware, and where to get help.
pragma ComponentBehavior: Bound
import QtQuick
import ".."
import "../components"

Page {
    id: page
    title: "About"
    lede: "What this computer runs, and where to get help."
    property var about: ({})

    function gib(bytes) {
        const g = bytes / 1073741824;
        return g >= 100 ? Math.round(g) + " GB" : g.toFixed(1).replace(/\.0$/, "") + " GB";
    }
    readonly property string details: {
        const a = about;
        if (!a.name)
            return "";
        const lines = [(a.pretty || a.name), "Kernel " + a.kernel, a.machine || "", (a.cpu || "") + (a.cores ? " (" + a.cores + " threads)" : ""),
            (a.gpus || []).join(", "), "Memory " + gib(a.memory || 0),
            (a.disks || []).map(d => d.mount + " " + gib(d.free) + " free of " + gib(d.total)).join(", "),
            "Mango " + (a.mango || "?") + ", Quickshell " + (a.quickshell || "?")];
        return lines.filter(l => l && l.trim() !== "").join("\n");
    }
    onShown: Backend.call(["about"], r => {
        if (r.ok)
            page.about = r;
    })

    Row {
        spacing: Theme.space4
        Mark {
            size: 56
            anchors.verticalCenter: parent.verticalCenter
        }
        Column {
            anchors.verticalCenter: parent.verticalCenter
            ArText {
                text: (page.about.name || "Arctic Linux") + (page.about.version ? " " + page.about.version : "")
                size: 20
                lh: 28
                weight: Font.DemiBold
            }
            ArText {
                text: page.about.fedora ? "Built on " + page.about.fedora + (page.about.live ? " · running from the live USB" : "") : ""
                size: 15
                lh: 22
                color: Theme.inkMuted
            }
        }
    }

    Group {
        title: "This computer"
        SettingRow {
            searchKey: "about.system"
            title: "Model"
            visible: (page.about.machine || "") !== ""
            ArText { text: page.about.machine || ""; size: 14; lh: 20; color: Theme.inkMuted }
        }
        SettingRow {
            title: "Processor"
            ArText { text: (page.about.cpu || "Unknown") + (page.about.cores ? " · " + page.about.cores + " threads" : ""); size: 14; lh: 20; color: Theme.inkMuted; horizontalAlignment: Text.AlignRight; width: Math.min(implicitWidth, 380); elide: Text.ElideMiddle }
        }
        SettingRow {
            title: "Graphics"
            ArText { text: (page.about.gpus || []).join(", ") || "Unknown"; size: 14; lh: 20; color: Theme.inkMuted; width: Math.min(implicitWidth, 380); elide: Text.ElideRight }
        }
        SettingRow {
            title: "Memory"
            ArText { text: page.about.memory ? page.gib(page.about.memory) : "Unknown"; size: 14; lh: 20; color: Theme.inkMuted }
        }
        Repeater {
            model: page.about.disks || []
            SettingRow {
                id: disk
                required property var modelData
                title: modelData.mount === "/" ? "Storage" : "Storage (" + modelData.mount + ")"
                desc: page.gib(modelData.free) + " free of " + page.gib(modelData.total)
                ArProgress {
                    width: 200
                    value: disk.modelData.total ? 1 - disk.modelData.free / disk.modelData.total : 0
                }
            }
        }
    }

    Group {
        title: "Software"
        SettingRow {
            searchKey: "about.software"
            title: "Arctic Linux"
            ArText { text: page.about.pretty || "Unknown"; size: 14; lh: 20; color: Theme.inkMuted }
        }
        SettingRow {
            title: "Window manager"
            ArText { text: page.about.mango ? "Mango " + page.about.mango : "Mango"; size: 14; lh: 20; color: Theme.inkMuted }
        }
        SettingRow {
            title: "Desktop shell"
            ArText { text: page.about.quickshell ? "Quickshell " + page.about.quickshell : "Quickshell"; size: 14; lh: 20; color: Theme.inkMuted }
        }
        SettingRow {
            title: "Linux kernel"
            ArText { text: page.about.kernel || ""; size: 14; lh: 20; color: Theme.inkMuted; font.family: Theme.fontMono }
        }
        SettingRow {
            title: "Computer name"
            ArText { text: page.about.hostname || ""; size: 14; lh: 20; color: Theme.inkMuted; font.family: Theme.fontMono }
        }
    }

    Group {
        title: "Help and feedback"
        SettingRow {
            searchKey: "about.help"
            title: "Arctic Linux wiki"
            desc: "How-tos, keyboard shortcuts and answers to common questions."
            ArButton {
                text: "Open the wiki"
                iconRight: "external"
                gapColor: Theme.surfaceRaised
                onClicked: Backend.openUrl(page.about.wiki || "https://github.com/yuvalkolodkingal/O-Tism/wiki")
            }
        }
        SettingRow {
            title: "Report a problem"
            desc: "Copy the details below into your report: they help us find the cause."
            Row {
                spacing: Theme.space2
                ArButton {
                    visible: Backend.caps.wlCopy === true
                    text: "Copy details"
                    iconName: "copy"
                    variant: "ghost"
                    gapColor: Theme.surfaceRaised
                    onClicked: {
                        Backend.launch(["wl-copy", "--", page.details]);
                        Backend.notify("success", "System details copied", false);
                    }
                }
                ArButton {
                    text: "Open issues"
                    iconRight: "external"
                    gapColor: Theme.surfaceRaised
                    onClicked: Backend.openUrl(page.about.issues || "https://github.com/yuvalkolodkingal/O-Tism/issues")
                }
            }
        }
    }

    // Restart one part of the desktop (arctic-restart), not the computer.
    Group {
        title: "If something stops working"
        desc: "Restart just that part of the desktop. Your apps and files stay as they are."
        SettingRow {
            searchKey: "about.troubleshoot"
            title: "Sound, Wi-Fi, Bluetooth or the desktop shell"
            desc: "The shell is the bar, the launcher and the notifications. Ctrl + Shift + Esc shows what’s running."
            resettable: false
            stacked: true
            Flow {
                width: parent.width
                spacing: Theme.space2
                Repeater {
                    model: [{ id: "sound", label: "Restart sound" }, { id: "wifi", label: "Restart Wi-Fi" },
                        { id: "bluetooth", label: "Restart Bluetooth" }, { id: "shell", label: "Restart the shell" }]
                    ArButton {
                        required property var modelData
                        text: modelData.label
                        iconName: "refresh"
                        size: "sm"
                        gapColor: Theme.surfaceRaised
                        onClicked: Backend.call(["troubleshoot", modelData.id], r => {
                            if (r.ok)
                                Backend.notify("success", "Restarted", false);
                        })
                    }
                }
            }
        }
    }
}
