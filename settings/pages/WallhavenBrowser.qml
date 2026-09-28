// Appearance → Wallhaven: search wallhaven.cc, look at a picture, set it as the wallpaper.
// Every network call happens in the shell's scripts/wallhaven.py (through the helper's
// `wallhaven` command): searches, thumbnails, downloads, the 45-requests-a-minute limit and the
// optional API key (~/.config/arctic/wallhaven.json, mode 600). Nothing is fetched until the
// person searches or presses Browse. A picture that is set is downloaded to
// ~/Pictures/Wallpapers/wallhaven/ and applied with arctic-wallpaper, so the colours follow it
// when "Match colours to the wallpaper" is on.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Templates as T
import ".."
import "../components"

Column {
    id: browser
    width: parent ? parent.width : 600

    // Called after a picture was set (the page reloads its wallpaper list and theme).
    signal wallpaperSet(string path)

    property var info: ({ has_key: false, key_hint: "", prefs: { categories: "111", purity: "100", sorting: "toplist", range: "1M", fit: true }, filters: {}, screens: [] })
    property var results: null          // the last search's answer
    property string query: ""
    property int page: 1
    property string seed: ""
    property bool searching: false
    property string problem: ""         // a sentence shown in place (offline, rate limit, no key)
    property string problemKind: "info"
    property string busyId: ""          // the picture being downloaded / set
    readonly property var prefs: info.prefs || ({})
    readonly property var items: (results && results.items) || []

    function loadState() {
        Backend.call(["wallhaven", "state"], r => { if (r.ok) browser.info = r; }, true);
    }
    Component.onCompleted: loadState()

    function search(pageNo) {
        if (searching)
            return;
        searching = true;
        problem = "";
        const args = ["wallhaven", "search", "--q", query, "--page", String(pageNo || 1),
            "--categories", prefs.categories, "--purity", prefs.purity, "--sorting", prefs.sorting, "--range", prefs.range,
            prefs.fit ? "--fit" : "--no-fit"];
        if (prefs.sorting === "random" && pageNo > 1 && seed !== "")
            args.push("--seed", seed);
        Backend.call(args, r => {
            browser.searching = false;
            if (r.ok) {
                browser.results = r;
                browser.page = r.page;
                browser.seed = r.seed || "";
                if (!r.items.length)
                    browser.say("info", "Nothing on Wallhaven matches that. Try other words or fewer filters.");
            } else {
                browser.say(r.offline ? "warning" : "error", r.error || "Wallhaven couldn’t be searched.");
            }
        }, true);
    }
    function say(kind, text) {
        problemKind = kind;
        problem = text;
    }
    // Change a filter: remember it (no network), then search again from page 1.
    function setPref(name, value) {
        const p = Object.assign({}, prefs);
        p[name] = value;
        info = Object.assign({}, info, { prefs: p });
        const flag = name === "fit" ? (value ? "on" : "off") : String(value);
        Backend.call(["wallhaven", "prefs", "--" + name, flag], r => {
            if (r.ok)
                browser.info = r;
            else
                browser.say("error", r.error);
        }, true);
        if (results !== null)
            search(1);
    }
    function toggleBit(name, index, on) {
        const bits = String(prefs[name] || "000").split("");
        bits[index] = on ? "1" : "0";
        const value = bits.join("");
        if (value === "000") {
            say("info", name === "purity" ? "Choose at least one kind of picture." : "Choose at least one category.");
            return false;
        }
        setPref(name, value);
        return true;
    }
    function setWallpaper(it) {
        if (busyId !== "")
            return;
        busyId = it.id;
        Backend.call(["wallhaven", "set", it.id, it.path], r => {
            browser.busyId = "";
            if (r.ok) {
                // New objects, so the tiles and the dialog see the download.
                const items = browser.items.map(x => x.id === it.id ? Object.assign({}, x, { downloaded: r.path }) : x);
                browser.results = Object.assign({}, browser.results, { items: items, current: r.path });
                preview.close();
                Backend.notify("success", "Wallpaper changed", false);
                browser.wallpaperSet(r.path);
            } else {
                Backend.notify("error", r.error || "The picture couldn’t be set.", false);
            }
        }, true);
    }
    function size(bytes) {
        return bytes >= 1048576 ? (bytes / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(bytes / 1024)) + " KB";
    }
    readonly property string fitText: {
        const f = info.filters || {};
        if (!f.atleast)
            return "Your screens aren’t known here (no wlr-randr), so every size is shown.";
        const ratios = String(f.ratios || "").split(",").map(r => r.replace("x", ":")).join(", ");
        return f.atleast.replace("x", " × ") + " or larger, " + ratios + ".";
    }

    SettingRow {
        searchKey: "appearance.wallhaven"
        title: "Find wallpapers on Wallhaven"
        desc: "Search wallhaven.cc and set a picture with one click. It’s saved in ~/Pictures/Wallpapers/wallhaven, next to your own pictures."
        stacked: true
        Column {
            width: parent.width
            spacing: Theme.space3

            Row {
                width: parent.width
                spacing: Theme.space2
                ArInput {
                    id: searchField
                    width: parent.width - searchButton.width - parent.spacing
                    iconName: "search"
                    placeholder: "mountains, aurora, minimal…"
                    accessibleName: "Search Wallhaven"
                    maximumLength: 200
                    onTextChanged: browser.query = text
                    onAccepted: browser.search(1)
                }
                ArButton {
                    id: searchButton
                    variant: "primary"
                    text: browser.searching ? "Searching…" : (browser.query.trim() === "" ? "Browse" : "Search")
                    enabled: !browser.searching
                    onClicked: browser.search(1)
                }
            }

            Flow {
                width: parent.width
                spacing: Theme.space3
                ArSegmented {
                    accessibleName: "Order"
                    model: [{ value: "toplist", label: "Top" }, { value: "date_added", label: "Latest" }, { value: "random", label: "Random" }]
                    value: browser.prefs.sorting === "date_added" || browser.prefs.sorting === "random" ? browser.prefs.sorting : "toplist"
                    onActivated: v => browser.setPref("sorting", v)
                }
                ArSelect {
                    visible: browser.prefs.sorting === "toplist"
                    width: 170
                    model: [{ value: "1d", label: "Today" }, { value: "1w", label: "This week" }, { value: "1M", label: "This month" },
                        { value: "3M", label: "3 months" }, { value: "6M", label: "6 months" }, { value: "1y", label: "This year" }]
                    value: browser.prefs.range || "1M"
                    onActivated: v => browser.setPref("range", v)
                }
            }

            Row {
                spacing: Theme.space4
                ArText {
                    width: 72
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Show"
                    size: 13
                    lh: 18
                    color: Theme.inkMuted
                }
                Repeater {
                    model: [{ label: "General", i: 0 }, { label: "Anime", i: 1 }, { label: "People", i: 2 }]
                    ArCheck {
                        required property var modelData
                        text: modelData.label
                        checked: String(browser.prefs.categories || "111")[modelData.i] === "1"
                        onToggled: if (!browser.toggleBit("categories", modelData.i, checked)) checked = true
                    }
                }
            }
            Row {
                spacing: Theme.space4
                ArText {
                    width: 72
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Purity"
                    size: 13
                    lh: 18
                    color: Theme.inkMuted
                }
                Repeater {
                    model: [{ label: "Safe", i: 0 }, { label: "Sketchy", i: 1 }, { label: "NSFW", i: 2 }]
                    ArCheck {
                        required property var modelData
                        text: modelData.label
                        // NSFW needs the API key (Wallhaven's rule).
                        enabled: modelData.i < 2 || browser.info.has_key === true
                        checked: String(browser.prefs.purity || "100")[modelData.i] === "1"
                        onToggled: if (!browser.toggleBit("purity", modelData.i, checked)) checked = true
                    }
                }
            }

            ArCheck {
                width: parent.width
                text: "Fit my screens"
                description: browser.fitText
                checked: browser.prefs.fit !== false
                onToggled: browser.setPref("fit", checked)
            }

            ArBanner {
                visible: browser.problem !== ""
                width: parent.width
                kind: browser.problemKind
                text: browser.problem
            }

            // Results: 4 across; each opens a larger preview.
            Grid {
                id: grid
                visible: browser.items.length > 0
                width: parent.width
                columns: Math.max(2, Math.floor((width + Theme.space3) / (160 + Theme.space3)))
                spacing: Theme.space3
                readonly property real cell: (width - (columns - 1) * spacing) / columns
                Repeater {
                    model: browser.items
                    T.AbstractButton {
                        id: tile
                        required property var modelData
                        readonly property bool chosen: browser.results && modelData.downloaded !== "" && browser.results.current === modelData.downloaded
                        width: grid.cell
                        height: Math.round(grid.cell * 0.625)
                        focusPolicy: Qt.StrongFocus
                        hoverEnabled: true
                        Accessible.role: Accessible.Button
                        Accessible.name: "Wallhaven picture " + modelData.resolution + ", " + modelData.category
                        onClicked: preview.show(modelData)
                        Keys.onReturnPressed: clicked()
                        background: Rectangle {
                            radius: Theme.radiusMd
                            color: Theme.surfaceSunken
                            border.width: tile.chosen ? 2 : 1
                            border.color: tile.chosen ? Theme.accentEdge : tile.hovered ? Theme.lineStrong : Theme.line
                            Image {
                                anchors.fill: parent
                                anchors.margins: tile.chosen ? 2 : 1
                                source: tile.modelData.thumb ? "file://" + tile.modelData.thumb : ""
                                sourceSize: Qt.size(320, 200)
                                fillMode: Image.PreserveAspectCrop
                                asynchronous: true
                                smooth: true
                            }
                            Rectangle {
                                anchors.left: parent.left
                                anchors.bottom: parent.bottom
                                anchors.margins: 6
                                width: res.implicitWidth + 12
                                height: 20
                                radius: 6
                                color: "#99000000"
                                ArText {
                                    id: res
                                    anchors.centerIn: parent
                                    text: tile.modelData.resolution.replace("x", "×")
                                    size: 11
                                    lh: 14
                                    color: "#ffffff"
                                }
                            }
                            Rectangle {
                                visible: tile.modelData.downloaded !== ""
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: 6
                                width: 22
                                height: 22
                                radius: 11
                                color: Theme.accent
                                Icon {
                                    anchors.centerIn: parent
                                    name: "check"
                                    size: 14
                                    color: Theme.inkOnAccent
                                }
                            }
                            Rectangle {
                                visible: browser.busyId === tile.modelData.id
                                anchors.fill: parent
                                radius: parent.radius
                                color: Theme.scrim
                                ArText {
                                    anchors.centerIn: parent
                                    text: "Downloading…"
                                    size: 13
                                    lh: 18
                                    color: "#ffffff"
                                }
                            }
                            FocusRing {
                                show: tile.visualFocus
                                radius: Theme.radiusMd
                                gapColor: Theme.surfaceRaised
                            }
                        }
                    }
                }
            }

            Row {
                visible: browser.results !== null && browser.items.length > 0
                width: parent.width
                spacing: Theme.space3
                ArButton {
                    size: "sm"
                    iconName: "chevron-left"
                    text: "Previous"
                    enabled: !browser.searching && browser.page > 1
                    onClicked: browser.search(browser.page - 1)
                }
                ArText {
                    anchors.verticalCenter: parent.verticalCenter
                    text: browser.results ? "Page " + browser.page + " of " + Math.max(1, browser.results.last_page)
                                            + (browser.results.total ? " · " + Number(browser.results.total).toLocaleString(Qt.locale(), "f", 0) + " pictures" : "") : ""
                    size: 13
                    lh: 18
                    color: Theme.inkMuted
                }
                ArButton {
                    size: "sm"
                    iconRight: "chevron-right"
                    text: "Next"
                    enabled: !browser.searching && browser.results !== null && browser.page < browser.results.last_page
                    onClicked: browser.search(browser.page + 1)
                }
            }
        }
    }

    SettingRow {
        searchKey: "appearance.wallhaven.key"
        title: "Wallhaven API key"
        desc: browser.info.has_key
              ? "Saved (" + browser.info.key_hint + "). Searches use your account and can include NSFW pictures when you tick it. Only you can read the file it’s kept in."
              : "Optional. With the key from your Wallhaven account (Settings → Account), searches follow your account and can include NSFW pictures."
        stacked: !browser.info.has_key
        Row {
            visible: !browser.info.has_key
            width: parent.width
            spacing: Theme.space2
            ArInput {
                id: keyField
                width: Math.min(360, parent.width - saveKey.width - parent.spacing)
                password: true
                placeholder: "API key"
                accessibleName: "Wallhaven API key"
                maximumLength: 64
                onAccepted: saveKey.clicked()
            }
            ArButton {
                id: saveKey
                text: "Save"
                enabled: keyField.text.trim().length >= 8
                onClicked: Backend.call(["wallhaven", "key", "--set", keyField.text.trim()], r => {
                    if (r.ok) {
                        keyField.text = "";
                        browser.info = r;
                        Backend.notify("success", "API key saved", false);
                    } else {
                        keyField.error = r.error || "Wallhaven didn’t accept that key.";
                    }
                }, true)
            }
        }
        ArButton {
            visible: browser.info.has_key === true
            text: "Remove"
            onClicked: Backend.call(["wallhaven", "key", "--clear"], r => {
                if (r.ok) {
                    browser.info = r;
                    Backend.notify("success", "API key removed", false);
                }
            })
        }
    }

    // ---- a larger look at one picture ----
    ArDialog {
        id: preview
        parent: T.Overlay.overlay
        width: Math.min(760, (T.Overlay.overlay ? T.Overlay.overlay.width : 800) - 64)
        title: it ? it.resolution.replace("x", " × ") + " · " + it.category.charAt(0).toUpperCase() + it.category.slice(1) : ""
        body: it ? browser.size(it.size) + " · " + it.favorites + " favourites" + (it.purity !== "sfw" ? " · " + it.purity.toUpperCase() : "") : ""
        property var it: null
        property string image: ""
        function show(item) {
            it = item;
            image = item.thumb || "";
            open();
            Backend.call(["wallhaven", "preview", item.id, item.large], r => {
                if (r.ok && preview.it && preview.it.id === item.id)
                    preview.image = r.preview;
            }, true);
        }
        Rectangle {
            width: parent.width
            height: Math.round(width * 0.5625)
            radius: Theme.radiusMd
            color: Theme.surfaceSunken
            clip: true
            Image {
                anchors.fill: parent
                source: preview.image ? "file://" + preview.image : ""
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                smooth: true
            }
        }
        Row {
            spacing: 6
            Repeater {
                model: preview.it ? preview.it.colors : []
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
        buttons: [
            ArButton {
                text: "Open on Wallhaven"
                iconName: "external"
                onClicked: Backend.openUrl(preview.it.url)
            },
            ArButton {
                variant: "primary"
                text: browser.busyId !== "" ? "Downloading…" : (preview.it && preview.it.downloaded !== "" ? "Set as wallpaper" : "Download and set")
                enabled: browser.busyId === ""
                onClicked: browser.setWallpaper(preview.it)
            }
        ]
    }
}
