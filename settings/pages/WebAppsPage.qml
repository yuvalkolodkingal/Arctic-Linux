// Web apps: the websites you added as apps (arctic-webapp, docs/wiki/Web-Apps.md), each with
// its links, notifications, engine and sign-in. Adding happens in the launcher (Get apps →
// Web apps); this page changes and removes. Every call goes through arctic_settings.py
// webapp-*, which passes arctic-webapp's one line of --json through.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Templates as T
import ".."
import "../components"

Page {
    id: page
    title: "Web apps"
    lede: "Websites you added as apps, each with its own window and sign-in. Add more in the launcher: Get apps, then Web apps."
    property var list: ({ apps: [], kept: [] })
    property var runtimes: []
    property string missing: ""
    property string selected: ""
    readonly property var app: {
        const apps = page.list.apps || [];
        for (let i = 0; i < apps.length; i++)
            if (apps[i].id === page.selected)
                return apps[i];
        return null;
    }
    onShown: refresh()

    function refresh() {
        Backend.call(["webapps"], r => {
            if (!r.ok) {
                page.missing = r.error || "Web apps aren’t available.";
                return;
            }
            page.missing = "";
            page.list = r;
            const apps = r.apps || [];
            if (!apps.some(a => a.id === page.selected))
                page.selected = apps.length > 0 ? apps[0].id : "";
        }, true);
        Backend.call(["webapp-runtimes"], r => { if (r.ok) page.runtimes = r.runtimes || []; }, true);
    }
    function applied(r) {
        return r.applied === "live" ? "Applied to the open window"
            : r.applied === "next_start" ? "Applies the next time it opens" : "Saved";
    }
    function set(key, value) {
        if (!page.app)
            return;
        Backend.call(["webapp-set", page.app.id, key, String(value)], r => {
            if (r.ok) {
                Backend.notify("success", page.applied(r), false);
                page.refresh();
            } else {
                page.refresh();
            }
        });
    }
    function simple(command, message) {
        if (!page.app)
            return;
        Backend.call([command, page.app.id], r => {
            if (r.ok) {
                Backend.notify("success", message, false);
                page.refresh();
            }
        });
    }
    function size(bytes) {
        if (bytes === null || bytes === undefined)
            return "";
        if (bytes < 1e6)
            return Math.max(1, Math.round(bytes / 1e3)) + " kB";
        return (bytes / 1e6).toFixed(bytes < 1e8 ? 1 : 0) + " MB";
    }
    // A missing browser keeps settings available so the user can choose a replacement.
    function usable(a) {
        return a !== null && (a.problem === "" || a.problem === "runtime-missing");
    }
    function problem(p) {
        return ({ "no-desktop-file": "Launcher entry missing", "no-registry": "Record missing",
                  "runtime-missing": "Its browser isn’t installed" })[p] || "";
    }
    function engineName(id) {
        for (let i = 0; i < page.runtimes.length; i++)
            if (page.runtimes[i].id === id)
                return page.runtimes[i].name;
        return id === "webkit" ? "Arctic" : id;
    }

    Group {
        title: "Your web apps"
        SettingRow {
            searchKey: "webapps.list"
            visible: page.missing !== ""
            title: "Web apps aren’t available"
            desc: page.missing
            resettable: false
        }
        SettingRow {
            visible: page.missing === "" && (page.list.apps || []).length === 0
            title: "Nothing yet"
            desc: "Open the launcher, choose Get apps, then Web apps, and paste an address like music.youtube.com."
            resettable: false
        }
        Repeater {
            model: page.list.apps || []
            SettingRow {
                id: appRow
                required property var modelData
                title: modelData.name
                desc: [modelData.host, page.engineName(modelData.runtime), modelData.running ? "Running" : "",
                       page.size(modelData.data_bytes), page.problem(modelData.problem)].filter(s => s !== "").join(" · ")
                resettable: false
                Row {
                    spacing: Theme.space2
                    ArButton {
                        visible: page.usable(appRow.modelData)
                        variant: "ghost"
                        size: "sm"
                        iconName: "external"
                        text: "Open"
                        gapColor: Theme.surfaceRaised
                        onClicked: Backend.call(["webapp-open", appRow.modelData.id], r => {})
                    }
                    ArButton {
                        visible: appRow.modelData.running
                        variant: "ghost"
                        size: "sm"
                        text: "Quit"
                        gapColor: Theme.surfaceRaised
                        onClicked: Backend.call(["webapp-quit", appRow.modelData.id], r => { page.refresh(); })
                    }
                    ArButton {
                        visible: page.usable(appRow.modelData) && page.selected !== appRow.modelData.id
                        size: "sm"
                        text: "Settings"
                        gapColor: Theme.surfaceRaised
                        onClicked: page.selected = appRow.modelData.id
                    }
                    ArButton {
                        visible: !page.usable(appRow.modelData)
                        variant: "ghost"
                        size: "sm"
                        iconName: "trash"
                        text: "Remove"
                        gapColor: Theme.surfaceRaised
                        onClicked: {
                            page.selected = appRow.modelData.id;
                            removeDialog.start(appRow.modelData);
                        }
                    }
                }
            }
        }
    }

    Group {
        visible: page.usable(page.app)
        title: page.app ? page.app.name : ""
        desc: page.app ? page.app.url : ""
        SettingRow {
            searchKey: "webapps.name"
            title: "Name"
            resettable: false
            Row {
                spacing: Theme.space2
                ArInput {
                    id: nameField
                    width: 220
                    text: page.app ? page.app.name : ""
                    accessibleName: "Web app name"
                    onAccepted: if (text.trim() !== "") page.set("name", text.trim())
                }
                ArButton {
                    text: "Rename"
                    enabled: page.app !== null && nameField.text.trim() !== "" && nameField.text.trim() !== page.app.name
                    gapColor: Theme.surfaceRaised
                    onClicked: page.set("name", nameField.text.trim())
                }
            }
        }
        SettingRow {
            searchKey: "webapps.icon"
            title: "Icon"
            desc: "A letter icon in the category's colour, or the site's own icon again."
            resettable: false
            Row {
                spacing: Theme.space2
                ArButton {
                    size: "sm"
                    text: "Letter icon"
                    gapColor: Theme.surfaceRaised
                    onClicked: page.set("icon", "monogram")
                }
                ArButton {
                    size: "sm"
                    iconName: "refresh"
                    text: "From the site"
                    gapColor: Theme.surfaceRaised
                    onClicked: page.set("icon", "site")
                }
            }
        }
        SettingRow {
            visible: page.app !== null && page.app.runtime === "webkit"
            searchKey: "webapps.background"
            title: "Keep running when closed"
            desc: "Closing hides the window. Messages and active media can continue. Use Quit to stop the app."
            resettable: false
            RowSwitch {
                Accessible.name: "Keep running when closed"
                checked: page.app !== null && page.app.keep_running === true
                onToggled: page.set("keep-running", checked ? "on" : "off")
            }
        }
        SettingRow {
            visible: page.app !== null && page.app.runtime === "webkit"
            searchKey: "webapps.startup"
            title: "Start at login"
            desc: "Opens at login, or starts hidden when Keep running is enabled."
            resettable: false
            RowSwitch {
                Accessible.name: "Start at login"
                checked: page.app !== null && page.app.start_at_login === true
                onToggled: page.set("start-at-login", checked ? "on" : "off")
            }
        }
        SettingRow {
            visible: page.app !== null && page.app.runtime === "webkit"
            searchKey: "webapps.downloads"
            title: "Ask where to save downloads"
            desc: "Choose a folder and filename for each download."
            resettable: false
            RowSwitch {
                Accessible.name: "Ask where to save downloads"
                checked: page.app !== null && page.app.ask_download === true
                onToggled: page.set("ask-download", checked ? "on" : "off")
            }
        }
        SettingRow {
            searchKey: "webapps.links"
            title: "Open other sites in your browser"
            desc: "Off: links to other sites open inside the app too."
            resettable: false
            RowSwitch {
                Accessible.name: "Open other sites in your browser"
                checked: page.app !== null && page.app.links === "browser"
                onToggled: page.set("links", checked ? "browser" : "app")
            }
        }
        SettingRow {
            searchKey: "webapps.domains"
            title: "Extra sites"
            desc: (page.app && page.app.extra_domains.length > 0 ? page.app.extra_domains.join(", ") + ". " : "")
                + "Sites that open inside the app, like a sign-in site it uses."
            resettable: false
            Row {
                spacing: Theme.space2
                ArInput {
                    id: domainField
                    width: 200
                    placeholder: "accounts.example.com"
                    accessibleName: "Extra site to keep in the app"
                    onAccepted: if (text.trim() !== "") { page.set("add-domain", text.trim().toLowerCase()); text = ""; }
                }
                ArButton {
                    text: "Add"
                    enabled: domainField.text.trim() !== ""
                    gapColor: Theme.surfaceRaised
                    onClicked: {
                        page.set("add-domain", domainField.text.trim().toLowerCase());
                        domainField.text = "";
                    }
                }
            }
        }
        Repeater {
            model: page.app ? page.app.extra_domains : []
            SettingRow {
                id: domainRow
                required property string modelData
                title: modelData
                resettable: false
                ArButton {
                    variant: "ghost"
                    size: "sm"
                    iconName: "trash"
                    text: "Remove"
                    gapColor: Theme.surfaceRaised
                    onClicked: page.set("remove-domain", domainRow.modelData)
                }
            }
        }
        SettingRow {
            searchKey: "webapps.notifications"
            title: "Notifications"
            desc: "Allow shows the site's notifications; Ask asks the first time."
            resettable: false
            ArSegmented {
                accessibleName: "Notifications"
                model: [{ value: "allow", label: "Allow" }, { value: "ask", label: "Ask" }, { value: "block", label: "Block" }]
                value: page.app ? page.app.notifications : "allow"
                onActivated: v => page.set("notifications", v)
            }
        }
        SettingRow {
            searchKey: "webapps.engine"
            title: "Engine"
            desc: "Video calls and protected video (Netflix, Spotify) need Brave, Chrome or Vivaldi."
            resettable: false
            ArSelect {
                width: 220
                model: page.runtimes.filter(r => r.available || (page.app && r.id === page.app.runtime))
                    .map(r => ({ value: r.id, label: r.name + (r.available ? "" : " (not installed)") }))
                value: page.app ? page.app.runtime : "webkit"
                onActivated: v => page.set("runtime", v)
            }
        }
        SettingRow {
            searchKey: "webapps.mail"
            visible: page.app !== null && page.app.handlers_supported.indexOf("mailto") >= 0
            title: "Open email links in this app"
            desc: "Offers the app for mailto: links."
            resettable: false
            RowSwitch {
                Accessible.name: "Open email links in this app"
                checked: page.app !== null && page.app.handlers.indexOf("mailto") >= 0
                onToggled: page.set("mail-links", checked ? "on" : "off")
            }
        }
        SettingRow {
            searchKey: "webapps.devtools"
            title: "Developer tools"
            desc: "F12 opens the web inspector."
            resettable: false
            RowSwitch {
                Accessible.name: "Developer tools"
                checked: page.app !== null && page.app.devtools === true
                onToggled: page.set("devtools", checked ? "on" : "off")
            }
        }
        SettingRow {
            searchKey: "webapps.rendering"
            title: "Rendering"
            desc: "Try Software if the window stays blank or flickers."
            resettable: false
            ArSegmented {
                accessibleName: "Rendering"
                model: [{ value: "auto", label: "Automatic" }, { value: "software", label: "Software" }]
                value: page.app ? page.app.rendering : "auto"
                onActivated: v => page.set("rendering", v)
            }
        }
        Repeater {
            model: page.app ? page.app.tls_exceptions : []
            SettingRow {
                id: certRow
                required property var modelData
                title: "Trusted certificate: " + modelData.host
                desc: "SHA-256 " + String(modelData.sha256).slice(0, 16) + "…"
                resettable: false
                ArButton {
                    variant: "ghost"
                    size: "sm"
                    text: "Forget"
                    gapColor: Theme.surfaceRaised
                    onClicked: page.set("forget-certificate", certRow.modelData.host)
                }
            }
        }
        SettingRow {
            searchKey: "webapps.permissions"
            title: "Permissions"
            desc: "Forget what you allowed or blocked (camera, microphone, location, notifications)."
            resettable: false
            ArButton {
                size: "sm"
                text: "Reset"
                gapColor: Theme.surfaceRaised
                onClicked: page.simple("webapp-reset-permissions", "Permissions reset")
            }
        }
        SettingRow {
            searchKey: "webapps.signout"
            title: "Sign out"
            desc: "Deletes its cookies and site data. The app stays."
            resettable: false
            ArButton {
                size: "sm"
                text: "Sign out"
                gapColor: Theme.surfaceRaised
                onClicked: signOutDialog.open()
            }
        }
        SettingRow {
            searchKey: "webapps.remove"
            title: "Remove"
            desc: "Removes the app from the launcher."
            resettable: false
            ArButton {
                variant: "destructive"
                size: "sm"
                iconName: "trash"
                text: "Remove"
                gapColor: Theme.surfaceRaised
                onClicked: removeDialog.start(page.app)
            }
        }
    }

    Group {
        visible: (page.list.kept || []).length > 0
        title: "Saved sign-in data"
        desc: "From web apps you removed. Adding the same site again signs you back in."
        Repeater {
            model: page.list.kept || []
            SettingRow {
                id: keptRow
                required property var modelData
                searchKey: "webapps.kept"
                title: modelData.name
                desc: [String(modelData.url).replace(/^https?:\/\//, "").replace(/\/.*$/, ""), page.size(modelData.data_bytes)]
                    .filter(s => s !== "").join(" · ")
                resettable: false
                ArButton {
                    variant: "ghost"
                    size: "sm"
                    iconName: "trash"
                    text: "Forget"
                    gapColor: Theme.surfaceRaised
                    onClicked: Backend.call(["webapp-forget", keptRow.modelData.id], r => {
                        if (r.ok) {
                            Backend.notify("success", "Sign-in data deleted", false);
                            page.refresh();
                        }
                    })
                }
            }
        }
    }

    ArDialog {
        id: signOutDialog
        parent: T.Overlay.overlay
        title: page.app ? "Sign out of " + page.app.name + "?" : ""
        body: "Its cookies and site data are deleted. If it's open, its window closes."
        iconName: "lock"
        buttons: [
            ArButton {
                text: "Cancel"
                onClicked: signOutDialog.close()
            },
            ArButton {
                text: "Sign out"
                variant: "destructive"
                onClicked: {
                    signOutDialog.close();
                    page.simple("webapp-clear", "Signed out");
                }
            }
        ]
    }

    ArDialog {
        id: removeDialog
        parent: T.Overlay.overlay
        property var target: null
        function start(a) {
            target = a;
            deleteData.checked = false;
            open();
        }
        title: target ? "Remove " + target.name + "?" : ""
        body: "It leaves the launcher. If it's open, its window closes."
        iconName: "trash"
        ArCheck {
            id: deleteData
            text: "Also delete sign-in data (you’ll be signed out)"
        }
        buttons: [
            ArButton {
                text: "Cancel"
                onClicked: removeDialog.close()
            },
            ArButton {
                text: "Remove"
                variant: "destructive"
                onClicked: {
                    const a = removeDialog.target;
                    removeDialog.close();
                    if (!a)
                        return;
                    Backend.call(["webapp-remove", a.id, deleteData.checked ? "delete" : "keep"], r => {
                        if (r.ok) {
                            Backend.notify("success", a.name + " removed", false);
                            page.refresh();
                        }
                    });
                }
            }
        ]
    }
}
