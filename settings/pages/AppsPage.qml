// Default apps: which app opens for each role. The keyboard roles (browser, terminal, files,
// editor) go to ~/.config/arctic/default-apps, which arctic-open reads after the installer's
// /etc/arctic/default-apps (Super + B, Super + Enter, Super + F, Super + E); links and files
// open through ~/.config/mimeapps.list, the file `xdg-mime default` writes.
pragma ComponentBehavior: Bound
import QtQuick
import ".."
import "../components"

Page {
    id: page
    title: "Default apps"
    lede: "The apps your keyboard shortcuts open, and the ones links and files open in."
    property var roles: []
    onShown: Backend.call(["apps"], r => { if (r.ok) page.roles = r.roles; })

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
    }
    ArText {
        width: parent.width
        text: "Install more apps with Get apps (Super + Shift + A); they show up here."
        size: 13
        lh: 18
        wrapMode: Text.WordWrap
        color: Theme.inkMuted
    }
}
