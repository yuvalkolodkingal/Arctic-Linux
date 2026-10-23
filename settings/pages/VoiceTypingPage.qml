// Voice typing is OpenWhispr's own app; this page installs, opens and starts it through
// arctic-openwhispr. Recording, models and pasting are set up in OpenWhispr itself.
pragma ComponentBehavior: Bound
import QtQuick
import ".."
import "../components"

Page {
    id: page
    title: "Voice typing"
    lede: "Speak and have the words typed into any app, with OpenWhispr."
    property var status: ({ installed: false, version: "", running: false, autostart: false })
    property string error: ""
    property string doing: ""
    readonly property bool busy: doing !== ""
    onShown: page.run(["status"])

    // The backend runs arctic-openwhispr and answers with its status.
    function run(args) {
        if (page.busy && args[0] !== "status") return;
        page.doing = args[0] === "status" ? page.doing : args[0];
        Backend.call(["voice"].concat(args), r => {
            if (args[0] !== "status") page.doing = "";
            page.error = r.ok ? "" : (r.error || "That didn’t work.");
            if (r.ok) page.status = r;
            else if (args[0] !== "status") Backend.call(["voice"], s => { if (s.ok) page.status = s; }, true);
        }, args[0] === "status");
    }

    ArBanner {
        width: parent.width
        kind: page.error !== "" ? "error" : page.status.installed ? "success" : "info"
        title: page.error !== "" ? "Something went wrong"
               : page.status.installed ? "OpenWhispr " + page.status.version + " is installed"
               : "OpenWhispr isn’t installed"
        text: (page.error !== "" ? page.error
               : page.status.installed ? "Open it with Super + Ctrl + X. Choose a local Whisper model or a cloud service, and your shortcut, in OpenWhispr’s own settings."
               : "Install downloads the official OpenWhispr app from its GitHub releases and checks it before installing.")
              .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    }

    Group {
        title: "OpenWhispr"
        SettingRow {
            searchKey: "voice.app"
            title: page.status.installed ? "Installed" : "Not installed"
            desc: page.status.installed ? (page.status.running ? "Running now." : "Not running.") : "Free and open source; it runs on this computer."
            resettable: false
            stacked: true
            Column {
                width: parent.width
                spacing: Theme.space3
                ArProgress {
                    width: parent.width
                    visible: page.busy && (page.doing === "install" || page.doing === "remove")
                    label: page.doing === "install" ? "Downloading and installing" : "Removing"
                    indeterminate: true
                    valueText: ""
                }
                Row {
                    spacing: Theme.space2
                    ArButton {
                        text: page.status.installed ? "Open OpenWhispr" : "Install"
                        iconName: page.status.installed ? "play" : "download"
                        enabled: !page.busy
                        gapColor: Theme.surfaceRaised
                        onClicked: page.status.installed ? page.run(["open"]) : page.run(["install"])
                    }
                    ArButton {
                        visible: page.status.installed === true
                        text: "Update"
                        variant: "ghost"
                        enabled: !page.busy
                        gapColor: Theme.surfaceRaised
                        onClicked: page.run(["install"])
                    }
                    ArButton {
                        visible: page.status.installed === true
                        text: "Remove"
                        variant: "ghost"
                        enabled: !page.busy
                        gapColor: Theme.surfaceRaised
                        onClicked: page.run(["remove"])
                    }
                }
            }
        }
        SettingRow {
            searchKey: "voice.autostart"
            title: "Start at login"
            desc: "Keeps OpenWhispr ready in the background, so its shortcut works right away."
            resettable: false
            RowSwitch {
                enabled: page.status.installed === true && !page.busy
                checked: page.status.autostart === true
                onToggled: page.run(["autostart", checked ? "on" : "off"])
            }
        }
    }

    Group {
        title: "Shortcuts"
        SettingRow {
            searchKey: "voice.shortcut"
            title: "Open OpenWhispr"
            desc: "Opens OpenWhispr, or this page when it isn’t installed. To dictate, use OpenWhispr’s own shortcut (F8 unless you change it) with the text field you want to type in focused."
            resettable: false
            ArKbd { text: "Super + Ctrl + X" }
        }
    }
}
