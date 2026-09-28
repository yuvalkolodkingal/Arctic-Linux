// Appearance: the theme (Winter, Polar night, or made from the wallpaper — arctic-theme), light
// and dark by the clock (arctic-daylight), the wallpaper (the shell's picker backend: the same
// list and thumbnails as Super + Shift + W), your own pictures (added with the file chooser — the
// xdg-desktop-portal one, through qt6ct — or dropped from Files, renamed, deleted), Wallhaven
// (WallhavenBrowser.qml). Reduced motion, text size and the pointer moved to Accessibility.
// Without the newer arctic-theme (set/auto/mode/list), only Winter and Polar night are offered
// and the rest says why.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Dialogs
import QtQuick.Templates as T
import ".."
import "../components"

Page {
    id: page
    title: "Appearance"
    lede: "Colours, wallpaper and motion for the whole desktop: the bar, windows, the terminal and apps."

    property var theme: ({ available: true, modern: false, themes: [], current: "", mode: "auto", auto: false })
    property var walls: ({ items: [], current: "", available: true })
    property var daylight: ({ available: false, mode: "off" })
    property string busyTheme: ""
    property string busyWall: ""
    property bool importing: false

    function load() {
        Backend.call(["theme"], r => { if (r.ok) page.theme = r; });
        Backend.call(["daylight"], r => { if (r.ok) page.daylight = r; }, true);
        loadWallpapers();
    }
    // Light and dark by the clock (arctic-daylight): off, sunset to sunrise, or custom hours.
    function setDaylight(args) {
        Backend.call(["daylight-set"].concat(args), r => {
            if (r.ok) {
                page.daylight = r;
                Theme.reload();
                Backend.notify("success", r.mode === "off" ? "Light and dark: only when you switch" : "Light and dark switch by themselves now", false);
            }
        });
    }
    function daylightText() {
        const d = page.daylight;
        if (d.message) return d.message;
        if (d.mode === "sun" && d.today) return "Light from sunrise (" + d.today.light + " today), dark from sunset (" + d.today.dark + "), where your time zone is. Super + Shift + T still switches until the next one.";
        if (d.mode === "hours") return "Light from " + d.light + ", dark from " + d.dark + ". Super + Shift + T still switches until the next change.";
        return "Only when you switch: here or with Super + Shift + T.";
    }
    function loadWallpapers() {
        Backend.call(["wallpapers"], r => { if (r.ok) page.walls = r; });
    }
    // Copy pictures (paths or file:// URLs) into the wallpaper folder.
    function importPictures(urls) {
        const list = [];
        for (let i = 0; i < urls.length; i++)
            if (String(urls[i]).startsWith("file:") || String(urls[i]).startsWith("/"))
                list.push(String(urls[i]));
        if (!list.length) {
            Backend.notify("info", "Only pictures from this computer can be added.", false);
            return;
        }
        page.importing = true;
        Backend.call(["wallpaper-import"].concat(list), r => {
            page.importing = false;
            if (!r.ok)
                return;
            page.loadWallpapers();
            const n = r.added.length;
            if (r.errors && r.errors.length)
                Backend.notify("info", (n === 1 ? "1 picture added. " : n + " pictures added. ") + r.errors.join(" "), false);
            else
                Backend.notify("success", n === 1 ? "Picture added" : n + " pictures added", false);
        });
    }
    function setTheme(id) {
        if (busyTheme !== "" || id === theme.current)
            return;
        busyTheme = id;
        Backend.call(["theme-set", id], r => {
            page.busyTheme = "";
            if (r.ok) {
                page.theme = r;
                Theme.reload();
                page.loadWallpapers();
                Backend.notify("success", "Theme changed", false);
            }
        });
    }
    onShown: load()
    // /home/you/Pictures/Wallpapers → ~/Pictures/Wallpapers
    function tildePath(path) {
        const home = Theme.home;
        return home && (path === home || String(path).startsWith(home + "/")) ? "~" + String(path).slice(home.length) : path;
    }
    // The theme changed elsewhere too (Super + Shift + T, the shell): follow it.
    Connections {
        target: Theme
        function onThemeIdChanged() {
            Backend.call(["theme"], r => { if (r.ok) page.theme = r; }, true);
            page.loadWallpapers();
        }
    }

    readonly property var swatches: ({
            "winter": ["#eef2f5", "#ffffff", "#151a21", "#efa637"],
            "polar-night": ["#12171e", "#232b36", "#e9eef3", "#f6bd55"]
        })

    Group {
        title: "Theme"
        desc: page.theme.available ? "" : page.theme.reason || ""
        SettingRow {
            searchKey: "appearance.theme"
            title: "Theme"
            desc: page.theme.modern ? "Winter is the light coat, Polar night the dark one. From wallpaper takes the colours of your picture."
                                    : (page.theme.reason || "Winter is the light coat, Polar night the dark one.")
            stacked: true
            enabled: page.theme.available !== false
            Row {
                width: parent.width
                spacing: Theme.space3
                Repeater {
                    model: [{ id: "winter", name: "Winter" }, { id: "polar-night", name: "Polar night" }, { id: "wallpaper", name: "From wallpaper" }]
                    ArCard {
                        id: card
                        required property var modelData
                        readonly property bool isWallpaper: modelData.id === "wallpaper"
                        width: (parent.width - 2 * Theme.space3) / 3
                        choice: true
                        radio: true
                        title: page.busyTheme === modelData.id ? "Switching…" : modelData.name
                        selected: page.theme.current === modelData.id
                        enabled: page.theme.available !== false && (!isWallpaper || page.theme.modern === true)
                        onClicked: page.setTheme(modelData.id)
                        Row {
                            topPadding: Theme.space2
                            spacing: 4
                            Repeater {
                                model: card.isWallpaper ? [Theme.ground, Theme.surfaceRaised, Theme.ink, Theme.accent] : page.swatches[card.modelData.id]
                                Rectangle {
                                    required property var modelData
                                    width: 22
                                    height: 22
                                    radius: 6
                                    color: modelData
                                    border.width: 1
                                    border.color: Theme.line
                                }
                            }
                        }
                    }
                }
            }
        }
        SettingRow {
            searchKey: "appearance.auto"
            title: "Match colours to the wallpaper"
            desc: page.theme.modern ? "Each new wallpaper makes the theme again, so the accent always suits the picture."
                                    : "Needs a newer arctic-theme (arctic-theme auto)."
            enabled: page.theme.modern === true
            RowSwitch {
                checked: page.theme.auto === true
                onToggled: Backend.call(["theme-auto", checked ? "on" : "off"], r => {
                    if (r.ok) { page.theme = r; Theme.reload(); }
                    else checked = page.theme.auto === true;
                })
                Accessible.name: "Match colours to the wallpaper"
            }
        }
        SettingRow {
            searchKey: "appearance.mode"
            title: "Light or dark"
            desc: page.theme.current === "wallpaper" ? "For the theme made from your wallpaper. Automatic picks what suits the picture."
                                                     : "Applies to the theme made from your wallpaper."
            enabled: page.theme.modern === true && (page.theme.current === "wallpaper" || page.theme.auto === true)
            ArSegmented {
                accessibleName: "Light or dark"
                model: [{ value: "auto", label: "Automatic" }, { value: "dark", label: "Dark" }, { value: "light", label: "Light" }]
                value: page.theme.mode || "auto"
                onActivated: v => Backend.call(["theme-mode", v], r => {
                    if (r.ok) { page.theme = r; Theme.reload(); }
                })
            }
        }
        SettingRow {
            searchKey: "appearance.schedule"
            visible: page.daylight.available === true
            title: "Switch light and dark by itself"
            desc: page.daylightText()
            ArSegmented {
                accessibleName: "Switch light and dark by itself"
                model: [{ value: "off", label: "Off" }, { value: "sun", label: "Sunset to sunrise" }, { value: "hours", label: "Custom hours" }]
                value: page.daylight.mode || "off"
                onActivated: v => page.setDaylight(v === "hours" ? ["hours", page.daylight.light || "07:00", page.daylight.dark || "19:00"] : [v])
            }
        }
        SettingRow {
            visible: page.daylight.available === true && page.daylight.mode === "hours"
            title: "Light from, dark from"
            desc: "24-hour times, like 07:00 and 19:00. Enter saves."
            resettable: false
            Row {
                spacing: Theme.space2
                ArInput {
                    id: lightFrom
                    width: 96
                    text: page.daylight.light || "07:00"
                    placeholder: "07:00"
                    maximumLength: 5
                    accessibleName: "Light from"
                    onAccepted: page.setDaylight(["hours", lightFrom.text.trim(), darkFrom.text.trim()])
                }
                ArInput {
                    id: darkFrom
                    width: 96
                    text: page.daylight.dark || "19:00"
                    placeholder: "19:00"
                    maximumLength: 5
                    accessibleName: "Dark from"
                    onAccepted: page.setDaylight(["hours", lightFrom.text.trim(), darkFrom.text.trim()])
                }
            }
        }
    }

    Group {
        title: "Wallpaper"
        desc: page.walls.folder ? "Your own pictures come from " + page.tildePath(page.walls.folder) + "." : ""
        SettingRow {
            searchKey: "appearance.wallpaper"
            title: "Wallpaper"
            desc: page.walls.available === false ? (page.walls.reason || "")
                  : "The Arctic wallpapers follow Winter and Polar night. Add your own pictures, or drop them here from Files. Super + Shift + W opens the picker from anywhere."
            stacked: true
            Column {
                width: parent.width
                spacing: Theme.space3
                ArButton {
                    iconName: "plus"
                    text: page.importing ? "Adding…" : "Add pictures…"
                    enabled: !page.importing && page.walls.available !== false
                    onClicked: fileDialog.open()
                }
                DropArea {
                    id: drop
                    width: parent.width
                    height: wallFlow.implicitHeight
                    enabled: page.walls.available !== false
                    onEntered: drag => drag.accepted = drag.hasUrls
                    onDropped: drop => {
                        if (drop.hasUrls) {
                            drop.acceptProposedAction();
                            page.importPictures(drop.urls);
                        }
                    }
                    Flow {
                        id: wallFlow
                        width: parent.width
                        spacing: Theme.space3
                        Repeater {
                            model: page.walls.items || []
                            T.AbstractButton {
                                id: thumb
                                required property var modelData
                                readonly property bool chosen: page.walls.current === modelData.key
                                width: 152
                                height: 112
                                focusPolicy: Qt.StrongFocus
                                hoverEnabled: true
                                Accessible.role: Accessible.RadioButton
                                Accessible.name: modelData.name
                                Accessible.checked: chosen
                                Accessible.description: modelData.arctic ? "" : "F2 renames it, Delete deletes it"
                                Keys.onPressed: event => {
                                    if (thumb.modelData.arctic)
                                        return;
                                    if (event.key === Qt.Key_F2) {
                                        renameDialog.start(thumb.modelData);
                                        event.accepted = true;
                                    } else if (event.key === Qt.Key_Delete) {
                                        deleteDialog.start(thumb.modelData);
                                        event.accepted = true;
                                    }
                                }
                                onClicked: {
                                    if (page.busyWall !== "")
                                        return;
                                    page.busyWall = modelData.key;
                                    Backend.call(["wallpaper-set", modelData.key], r => {
                                        page.busyWall = "";
                                        if (r.ok) {
                                            page.walls = Object.assign({}, page.walls, { current: thumb.modelData.key });
                                            Backend.notify("success", "Wallpaper changed", false);
                                        }
                                    });
                                }
                                Keys.onReturnPressed: clicked()
                                background: Item {}
                                contentItem: Column {
                                    spacing: Theme.space1
                                    Rectangle {
                                        width: thumb.width
                                        height: 86
                                        radius: Theme.radiusMd
                                        color: Theme.surfaceSunken
                                        border.width: thumb.chosen ? 2 : 1
                                        border.color: thumb.chosen ? Theme.accentEdge : thumb.hovered ? Theme.lineStrong : Theme.line
                                        Image {
                                            anchors.fill: parent
                                            anchors.margins: thumb.chosen ? 2 : 1
                                            source: thumb.modelData.thumb ? "file://" + thumb.modelData.thumb : ""
                                            sourceSize: Qt.size(300, 172)
                                            fillMode: Image.PreserveAspectCrop
                                            asynchronous: true
                                            smooth: true
                                        }
                                        Rectangle {
                                            visible: page.busyWall === thumb.modelData.key
                                            anchors.fill: parent
                                            radius: parent.radius
                                            color: Theme.scrim
                                            ArText {
                                                anchors.centerIn: parent
                                                text: "Setting…"
                                                size: 13
                                                lh: 18
                                                color: "#ffffff"
                                            }
                                        }
                                        FocusRing {
                                            show: thumb.visualFocus
                                            radius: Theme.radiusMd
                                            gapColor: Theme.surfaceRaised
                                        }
                                        // Your own pictures: rename and delete (shown on hover and focus).
                                        Row {
                                            visible: !thumb.modelData.arctic && (thumb.hovered || thumb.activeFocus)
                                            anchors.top: parent.top
                                            anchors.right: parent.right
                                            anchors.margins: 6
                                            spacing: 4
                                            Repeater {
                                                model: [{ icon: "edit", tip: "Rename" }, { icon: "trash", tip: "Delete" }]
                                                T.AbstractButton {
                                                    id: hit
                                                    required property var modelData
                                                    required property int index
                                                    width: 26
                                                    height: 26
                                                    hoverEnabled: true
                                                    focusPolicy: Qt.NoFocus
                                                    Accessible.role: Accessible.Button
                                                    Accessible.name: modelData.tip + " " + thumb.modelData.name
                                                    onClicked: index === 0 ? renameDialog.start(thumb.modelData) : deleteDialog.start(thumb.modelData)
                                                    background: Rectangle {
                                                        radius: 8
                                                        color: hit.hovered ? (hit.index === 1 ? Theme.error : Theme.surfaceRaised) : "#b3000000"
                                                    }
                                                    contentItem: Icon {
                                                        name: hit.modelData.icon
                                                        size: 16
                                                        color: hit.hovered && hit.index === 0 ? Theme.ink : "#ffffff"
                                                    }
                                                }
                                            }
                                        }
                                    }
                                    ArText {
                                        width: thumb.width
                                        text: thumb.modelData.name
                                        size: 13
                                        lh: 18
                                        elide: Text.ElideRight
                                        weight: thumb.chosen ? Font.DemiBold : Font.Normal
                                        color: thumb.chosen ? Theme.ink : Theme.inkMuted
                                    }
                                }
                            }
                        }
                    }
                    // Dragging pictures over the list.
                    Rectangle {
                        visible: drop.containsDrag
                        anchors.fill: parent
                        anchors.margins: -Theme.space2
                        radius: Theme.radiusLg
                        color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.14)
                        border.width: 2
                        border.color: Theme.accentEdge
                        ArText {
                            anchors.centerIn: parent
                            text: "Drop to add to your wallpapers"
                            size: 15
                            lh: 22
                            weight: Font.DemiBold
                        }
                    }
                }
            }
        }
    }

    Group {
        title: "Wallhaven"
        desc: "Wallpapers from wallhaven.cc, made by its community. Nothing is fetched until you search."
        WallhavenBrowser {
            onWallpaperSet: page.loadWallpapers()
        }
    }

    // Add pictures: the file chooser (xdg-desktop-portal through qt6ct, Qt's own dialog otherwise).
    FileDialog {
        id: fileDialog
        title: "Add pictures to your wallpapers"
        fileMode: FileDialog.OpenFiles
        nameFilters: ["Pictures (*.jpg *.jpeg *.png *.webp *.bmp *.gif *.JPG *.JPEG *.PNG *.WEBP)"]
        currentFolder: "file://" + Theme.home + "/Pictures"
        onAccepted: page.importPictures(selectedFiles)
    }

    ArDialog {
        id: renameDialog
        parent: T.Overlay.overlay
        width: 440
        title: "Rename picture"
        property var item: null
        function start(it) {
            item = it;
            nameField.text = it.name ? String(it.path).split("/").pop().replace(/\.[^.]+$/, "") : "";
            nameField.error = "";
            open();
            nameField.input.forceActiveFocus();
            nameField.input.selectAll();
        }
        function save() {
            Backend.call(["wallpaper-rename", item.path, nameField.text.trim()], r => {
                if (r.ok) {
                    renameDialog.close();
                    page.loadWallpapers();
                    Backend.notify("success", "Picture renamed", false);
                } else {
                    nameField.error = r.error;
                }
            }, true);
        }
        ArInput {
            id: nameField
            width: parent.width
            label: "Name"
            maximumLength: 120
            onAccepted: renameDialog.save()
        }
        buttons: [
            ArButton {
                text: "Cancel"
                onClicked: renameDialog.close()
            },
            ArButton {
                variant: "primary"
                text: "Rename"
                enabled: nameField.text.trim() !== ""
                onClicked: renameDialog.save()
            }
        ]
    }

    ArDialog {
        id: deleteDialog
        parent: T.Overlay.overlay
        width: 440
        iconName: "trash"
        tone: "error"
        title: "Delete “" + (item ? item.name : "") + "”?"
        body: "The picture is deleted from " + (item ? page.tildePath(String(item.path).replace(/\/[^/]*$/, "")) : "your folder") + ". This can’t be undone."
        property var item: null
        function start(it) {
            item = it;
            open();
        }
        buttons: [
            ArButton {
                text: "Cancel"
                focus: true
                onClicked: deleteDialog.close()
            },
            ArButton {
                variant: "destructive"
                text: "Delete"
                onClicked: Backend.call(["wallpaper-delete", deleteDialog.item.path], r => {
                    deleteDialog.close();
                    if (r.ok) {
                        page.loadWallpapers();
                        Backend.notify("success", "Picture deleted", false);
                    }
                })
            }
        ]
    }

    // Text size, the pointer and motion moved to Accessibility (0.3).
    ArButton {
        text: "Text size, pointer and motion are in Accessibility"
        variant: "ghost"
        iconRight: "chevron-right"
        onClicked: Backend.launch(["arctic-settings", "accessibility"])
    }
}
