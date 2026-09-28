// Startup apps: commands that run once when you log in. Yours are exec-once lines in
// settings.conf; Arctic's own come from autostart.conf and are shown read-only. Apps that turned
// on their own "start on login" (~/.config/autostart, /etc/xdg/autostart) start through systemd's
// XDG autostart (mango-session.target wants xdg-desktop-autostart.target); switching one off
// writes a Hidden=true copy to ~/.config/autostart.
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
    property var xdg: []
    onShown: {
        Backend.call(["startup"], r => { if (r.ok) page.list = r; });
        Backend.call(["autostart"], r => { if (r.ok) page.xdg = r.entries; }, true);
    }
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
        visible: page.xdg.length > 0
        title: "Apps that start themselves"
        desc: "Apps you told to “start on login” in their own settings, such as a chat or sync app. Switching one off here applies from the next login."
        Repeater {
            model: page.xdg
            SettingRow {
                id: xdgRow
                required property var modelData
                required property int index
                searchKey: index === 0 ? "startup.xdg" : ""
                title: modelData.name
                desc: modelData.comment || modelData.exec
                resettable: false
                RowSwitch {
                    Accessible.name: "Start " + xdgRow.modelData.name + " when you log in"
                    checked: xdgRow.modelData.enabled
                    onToggled: Backend.call(["autostart-set", xdgRow.modelData.id, checked ? "on" : "off"], r => {
                        if (r.ok) {
                            page.xdg = r.entries;
                            Backend.notify("success", "Saved. It applies the next time you log in.", false);
                        } else {
                            Backend.call(["autostart"], r2 => { if (r2.ok) page.xdg = r2.entries; }, true);
                        }
                    })
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
