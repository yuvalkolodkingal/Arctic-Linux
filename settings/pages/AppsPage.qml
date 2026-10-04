// Default apps: which app opens for each role. The keyboard roles (browser, terminal, files,
// editor) go to ~/.config/arctic/default-apps, which arctic-open reads after the installer's
// /etc/arctic/default-apps (Super + B, Super + Enter, Super + F, Super + E); links and files
// open through ~/.config/mimeapps.list, the file `xdg-mime default` writes. "Install and remove
// apps" opens the shell's Get apps and Remove apps (arctic-shell-ipc apps install|remove).
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Templates as T
import ".."
import "../components"

Page {
    id: page
    title: "Default apps"
    lede: "The apps your keyboard shortcuts open, and the ones links and files open in."
    property var gaming: ({ gpus: [], packages: [], warnings: [], blocked: "", repositories: false, secure_boot: "unknown" })
    property var roles: []
    property var shellOptions: ({})
    onShown: {
        Backend.call(["gaming"], r => { if (r.ok) page.gaming = r; }, true);
        Backend.call(["apps"], r => { if (r.ok) page.roles = r.roles; });
        Backend.call(["shell-options"], r => { if (r.ok) page.shellOptions = r; });
    }

    Group {
        title: "Apps"
        Repeater {
            model: page.roles
            SettingRow {
                id: roleRow
                required property var modelData
                searchKey: "apps." + modelData.id
                title: modelData.label
                desc: modelData.candidates.length === 0 ? "Nothing installed for this yet."
                    : modelData.keys ? "Opens with " + modelData.keys + (modelData.id === "browser" ? ", and for links" : "") + "."
                    : "Opens " + modelData.label.toLowerCase() + " when you open a file."
                resettable: false
                Row {
                    spacing: Theme.space2
                    Icon {
                        name: roleRow.modelData.icon
                        size: 20
                        color: Theme.inkMuted
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    ArSelect {
                        visible: roleRow.modelData.candidates.length > 0
                        width: 240
                        placeholder: roleRow.modelData.command ? roleRow.modelData.command : "Choose…"
                        model: roleRow.modelData.candidates.map(c => ({ value: c.id, label: c.name }))
                        value: roleRow.modelData.current
                        onActivated: v => Backend.call(["app-set", roleRow.modelData.id, v], r => {
                            if (r.ok) {
                                page.roles = r.roles;
                                Backend.notify("success", roleRow.modelData.label + " changed", false);
                            }
                        })
                    }
                    ArButton {
                        visible: roleRow.modelData.candidates.length === 0
                        text: "Get apps"
                        iconName: "package"
                        gapColor: Theme.surfaceRaised
                        onClicked: Backend.launch(["arctic-shell-ipc", "apps", "install"])
                    }
                }
            }
        }
        SettingRow {
            searchKey: "apps.software"
            title: "Install and remove apps"
            desc: "Flathub apps, Fedora packages, Nix packages, web apps and terminal apps."
            resettable: false
            Row {
                spacing: Theme.space2
                ArButton {
                    text: "Get apps"
                    iconName: "package"
                    gapColor: Theme.surfaceRaised
                    onClicked: Backend.launch(["arctic-shell-ipc", "apps", "install"])
                }
                ArButton {
                    visible: !Backend.live
                    text: "Remove apps"
                    iconName: "trash"
                    gapColor: Theme.surfaceRaised
                    onClicked: Backend.launch(["arctic-shell-ipc", "apps", "remove"])
                }
            }
        }
    }
    ArText {
        width: parent.width
        text: "Apps you install with Get apps (Super + Shift + A) show up here."
        size: 13
        lh: 18
        wrapMode: Text.WordWrap
        color: Theme.inkMuted
    }

    Group {
        title: "Gaming (optional)"
        visible: !Backend.live
        SettingRow {
            searchKey: "apps.gaming"
            title: "Steam and Proton"
            desc: (page.gaming.gpus.length ? page.gaming.gpus.map(g => g.name + " · " + g.driver).join(", ") : "No graphics device detected")
                + ". Secure Boot: " + page.gaming.secure_boot + ". Steam manages your account, games and Proton downloads."
            resettable: false
            Row {
                spacing: Theme.space2
                ArButton { text: "Review automatic setup…"; gapColor: Theme.surfaceRaised; onClicked: gamingDialog.open() }
                ArButton { text: "Driver guide"; gapColor: Theme.surfaceRaised; onClicked: Backend.openUrl("https://github.com/yuvalkolodkingal/Arctic-Linux/wiki/Drivers") }
            }
        }
        SettingRow {
            title: "Additional Proton versions"
            desc: "Optional ProtonPlus manages community compatibility tools. Steam's built-in Proton remains available."
            resettable: false
            ArButton { text: "Get ProtonPlus…"; gapColor: Theme.surfaceRaised; onClicked: Backend.launch(["arctic-shell-ipc", "apps", "search", "flatpak", "com.vysp3r.ProtonPlus"]) }
        }
    }
    ArDialog {
        id: gamingDialog
        parent: T.Overlay.overlay
        title: "Gaming setup for this hardware"
        body: "Packages: " + page.gaming.packages.join(", ") + ".\n\n" + page.gaming.warnings.join("\n\n")
            + (page.gaming.blocked ? "\n\n" + page.gaming.blocked : "")
            + (!page.gaming.repositories ? "\n\nRPM Fusion must be enabled first. Review its repositories and signing keys before proceeding." : "")
            + "\n\nDNF asks before installing. No Steam account, purchase or Secure Boot enrollment is performed."
        ArButton {
            visible: !page.gaming.repositories
            text: "RPM Fusion setup guide"
            onClicked: Backend.openUrl("https://rpmfusion.org/Configuration")
        }
        ArButton {
            text: "Install planned packages…"
            enabled: !page.gaming.blocked && page.gaming.repositories
            onClicked: Backend.call(["gaming-run", "setup"], r => { if (r.ok) gamingDialog.close(); })
        }
    }

    // The launcher's web search (shell.json "webSearch"): the last row of every search, and
    // what "?" searches straight away.
    Group {
        title: "Launcher"
        visible: page.shellOptions.engines !== undefined
        SettingRow {
            searchKey: "apps.websearch"
            title: "Web search"
            desc: "Searches in the launcher end with a web search; start with ? to search only the web."
            resettable: false
            ArSelect {
                width: 240
                readonly property bool custom: !(page.shellOptions.engines || []).some(e => e.id === page.shellOptions.webSearch)
                placeholder: custom ? "Your own" : "Choose…"
                model: (page.shellOptions.engines || []).map(e => ({ value: e.id, label: e.name }))
                value: page.shellOptions.webSearch || "duckduckgo"
                onActivated: v => Backend.call(["shell-option-set", "webSearch", v], r => {
                    if (r.ok) {
                        page.shellOptions = r;
                        Backend.notify("success", "Web search changed", false);
                    }
                })
            }
        }
    }
}
