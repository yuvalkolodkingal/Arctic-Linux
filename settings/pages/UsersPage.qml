// Users and sign-in: your picture (~/.face, 256×256, and AccountsService's copy for the login
// screen) and full name (AccountsService), and the jobs that ask questions, which open a
// terminal window: the password (passwd), the disk passphrase (cryptsetup luksChangeKey through
// pkexec, only when / is on LUKS) and fingerprints (fprintd-enroll, only with a reader).
// Hidden in the live session.
pragma ComponentBehavior: Bound
import QtQuick
import ".."
import "../components"

Page {
    id: page
    title: "Users and sign-in"
    lede: "Your picture and name, your password and how this computer unlocks."
    property var info: ({ user: "", name: "", picture: "", luks: { present: false }, fingerprint: { reader: false, fingers: [] }, live: false })
    property var pictures: []
    function load() {
        Backend.call(["users"], r => { if (r.ok) page.info = r; });
    }
    function run(job, message) {
        Backend.call(["user-run", job], r => {
            if (r.ok)
                Backend.notify("info", message, false);
        });
    }
    onShown: load()

    ArBanner {
        visible: page.info.live === true
        width: parent.width
        kind: "info"
        text: "The live session’s user is temporary. Set up your account when you install Arctic Linux."
    }

    Group {
        visible: page.info.live !== true
        title: "You"
        SettingRow {
            searchKey: "users.picture"
            title: "Picture"
            desc: "Shown on the login and lock screens."
            resettable: false
            Row {
                spacing: Theme.space3
                Rectangle {
                    width: 48
                    height: 48
                    radius: 24
                    color: Theme.surfaceSunken
                    clip: true
                    anchors.verticalCenter: parent.verticalCenter
                    Image {
                        anchors.fill: parent
                        visible: page.info.picture !== ""
                        source: page.info.picture ? "file://" + page.info.picture + "?" + Date.now() : ""
                        fillMode: Image.PreserveAspectCrop
                        cache: false
                    }
                    Icon {
                        visible: page.info.picture === ""
                        anchors.centerIn: parent
                        name: "user"
                        size: 24
                        color: Theme.inkMuted
                    }
                }
                ArButton {
                    text: "Change…"
                    gapColor: Theme.surfaceRaised
                    anchors.verticalCenter: parent.verticalCenter
                    onClicked: Backend.call(["user-pictures"], r => {
                        if (!r.ok)
                            return;
                        page.pictures = r.pictures;
                        if (r.pictures.length === 0)
                            Backend.notify("info", "Put a picture in " + r.folder + " first.", false);
                        else
                            picturePicker.start();
                    })
                }
                ArButton {
                    visible: page.info.picture !== ""
                    text: "Remove"
                    variant: "ghost"
                    gapColor: Theme.surfaceRaised
                    anchors.verticalCenter: parent.verticalCenter
                    onClicked: Backend.call(["user-set", "picture", "--remove"], r => { if (r.ok) page.info = r; })
                }
            }
        }
        SettingRow {
            searchKey: "users.name"
            title: "Name"
            desc: "Your username is " + page.info.user + "; it doesn’t change."
            resettable: false
            Row {
                spacing: Theme.space2
                ArInput {
                    id: nameField
                    width: 220
                    text: page.info.name
                    accessibleName: "Your full name"
                    onAccepted: saveName.clicked()
                }
                ArButton {
                    id: saveName
                    text: "Save"
                    enabled: nameField.text.trim() !== "" && nameField.text.trim() !== page.info.name
                    gapColor: Theme.surfaceRaised
                    onClicked: Backend.call(["user-set", "name", nameField.text.trim()], r => {
                        if (r.ok) {
                            page.info = r;
                            Backend.notify("success", "Name changed", false);
                        }
                    })
                }
            }
        }
    }

    Group {
        visible: page.info.live !== true
        title: "Signing in"
        SettingRow {
            searchKey: "users.password"
            title: "Password"
            desc: "Opens a terminal window: it asks for your current password, then the new one twice. Your keyring follows."
            resettable: false
            ArButton {
                text: "Change password"
                iconName: "terminal"
                gapColor: Theme.surfaceRaised
                onClicked: page.run("password", "Change your password in the terminal window.")
            }
        }
        SettingRow {
            visible: page.info.luks.present === true
            searchKey: "users.disk"
            title: "Disk encryption passphrase"
            desc: "What you type when the computer starts. Opens a terminal window: your password, then the old passphrase and the new one twice."
            resettable: false
            ArButton {
                text: "Change passphrase"
                iconName: "terminal"
                gapColor: Theme.surfaceRaised
                onClicked: page.run("disk", "Change the disk passphrase in the terminal window.")
            }
        }
        SettingRow {
            visible: page.info.fingerprint.reader === true
            searchKey: "users.fingerprint"
            title: "Fingerprints"
            desc: (page.info.fingerprint.fingers || []).length ? "Saved: " + page.info.fingerprint.fingers.join(", ").replace(/-/g, " ") + "."
                : "None saved yet. Opens a terminal window: touch the reader a few times."
            resettable: false
            ArButton {
                text: "Add a fingerprint"
                iconName: "terminal"
                gapColor: Theme.surfaceRaised
                onClicked: page.run("fingerprint", "Touch the reader when the terminal window asks.")
            }
        }
    }

    PickerDialog {
        id: picturePicker
        title: "Your picture"
        actionText: "Use"
        items: page.pictures.map(p => ({ value: p.path, label: p.name }))
        onPicked: v => Backend.call(["user-set", "picture", v], r => {
            if (r.ok) {
                page.info = r;
                Backend.notify("success", "Picture changed", false);
            }
        })
    }
}
