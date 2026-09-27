// Startup apps: commands that run once when you log in. Mango runs exec-once lines (it doesn't
// read ~/.config/autostart), so yours are exec-once lines in settings.conf; Arctic's own come
// from autostart.conf and are shown read-only.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Templates as T
import ".."
import "../components"

Page {
    id: page
    title: "Startup apps"
    lede: "Apps and commands that start when you log in. Changes apply the next time you log in."
    property var list: ({ mine: [], arctic: [], apps: [] })
    onShown: Backend.call(["startup"], r => { if (r.ok) page.list = r; })
    function add(args) {
        Backend.call(["startup-add"].concat(args), r => {
            if (r.ok) {
                page.list = r;
                Backend.refresh();
                Backend.notify("success", "Added. It starts the next time you log in.", true);
            }
        });
    }

    Group {
        title: "Yours"
        SettingRow {
            searchKey: "startup.mine"
            visible: page.list.mine.length === 0
            title: "Nothing yet"
            desc: "Add a chat app, a sync client or a script."
            resettable: false
        }
        Repeater {
            model: page.list.mine
            SettingRow {
                id: item
                required property var modelData
                title: item.modelData.command.replace(/^gtk-launch /, "")
                desc: item.modelData.command
                resettable: false
                ArButton {
                    variant: "ghost"
                    size: "sm"
                    iconName: "trash"
                    text: "Remove"
                    gapColor: Theme.surfaceRaised
                    onClicked: Backend.call(["startup-remove", String(item.modelData.index)], r => {
                        if (r.ok) {
                            page.list = r;
                            Backend.refresh();
                            Backend.notify("success", "Removed", true);
                        }
                    })
                }
            }
        }
        SettingRow {
            title: "Add an app"
            resettable: false
            ArButton {
                text: "Choose an app"
                iconName: "plus"
                gapColor: Theme.surfaceRaised
                onClicked: appPicker.start()
            }
        }
        SettingRow {
            title: "Add a command"
            desc: "Runs as if typed in a terminal, without one."
            resettable: false
            Row {
                spacing: Theme.space2
                ArInput {
                    id: commandField
                    width: 260
                    placeholder: "For example: syncthing serve"
                    accessibleName: "Command to run at login"
                    onAccepted: if (text.trim() !== "") { page.add(text.trim().split(/\s+/)); text = ""; }
                }
                ArButton {
                    text: "Add"
                    enabled: commandField.text.trim() !== ""
                    gapColor: Theme.surfaceRaised
                    onClicked: {
                        page.add(commandField.text.trim().split(/\s+/));
                        commandField.text = "";
                    }
                }
            }
        }
    }

    Group {
        title: "Started by Arctic"
        desc: "The desktop itself. To change these, see autostart.conf in ~/.config/mango/arctic."
        Repeater {
            model: page.list.arctic
            SettingRow {
                required property var modelData
                searchKey: "startup.arctic"
                title: modelData.command
                desc: String(modelData.file).split("/").pop()
                resettable: false
            }
        }
    }

    PickerDialog {
        id: appPicker
        title: "Start an app when you log in"
        items: page.list.apps.map(a => ({ value: a.id, label: a.name }))
        onPicked: v => page.add(["--app", v])
    }
}
