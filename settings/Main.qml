// The Settings window: the 232px rail of pages (the installer's rail) with the search on top,
// and the current page. Keyboard: ↑/↓ in the rail change the page, Tab goes into it,
// Ctrl+F (or /) searches, Ctrl+PgUp/PgDn switch pages from anywhere, Esc goes back to the
// rail, Ctrl+Q closes Settings.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Templates as T
import "components"
import "SearchIndex.js" as Index

FocusScope {
    id: main
    focus: true

    property int current: 0
    property string query: ""
    property int hit: 0
    readonly property var results: Index.search(query)
    readonly property var pages: Index.PAGES
    readonly property string currentId: pages[current].id
    property var visited: ({ 0: true })
    // The rail's focus ring shows once the keyboard is used there (not after a click).
    property bool keyboardNav: false

    // The loaded page at index i, or null.
    function pageAt(i) {
        const loader = pageRepeater.itemAt(i) as Loader;
        return loader ? loader.item as Page : null;
    }
    function open(id, key) {
        const i = Index.pageIndex(id);
        if (i < 0)
            return false;
        if (search.text !== "")
            search.text = "";
        const v = Object.assign({}, visited);
        v[i] = true;
        visited = v;
        current = i;
        const loaded = pageAt(i);
        if (key)
            revealLater.schedule(i, key);
        else if (loaded)
            loaded.shown();
        return true;
    }
    function step(delta) {
        open(pages[(current + delta + pages.length) % pages.length].id, "");
    }
    function setSearch(text) {
        search.text = text;
        search.forceActiveFocus();
    }
    function focusSearch() {
        search.forceActiveFocus();
        search.input.selectAll();
    }
    function focusPage() {
        const loaded = pageAt(current);
        if (loaded) {
            const next = loaded.nextItemInFocusChain(true);
            if (next)
                next.forceActiveFocus();
            else
                loaded.forceActiveFocus();
        }
    }
    function pick(i) {
        const r = results[i];
        if (!r)
            return;
        open(r.page, r.key);
        query = "";
        search.text = "";
        nav.forceActiveFocus();
    }

    // Wait until a page has loaded (and laid out) before scrolling to a row.
    Timer {
        id: revealLater
        property int index: -1
        property string key: ""
        property int tries: 0
        interval: 60
        repeat: true
        function schedule(i, k) {
            index = i;
            key = k;
            tries = 0;
            restart();
        }
        onTriggered: {
            const loaded = main.pageAt(index);
            if ((loaded && loaded.reveal(key)) || ++tries > 30)
                stop();
        }
    }

    Shortcut {
        sequences: ["Ctrl+F"]
        onActivated: main.focusSearch()
    }
    Shortcut {
        sequences: ["Ctrl+PgDown", "Alt+Down"]
        onActivated: main.step(1)
    }
    Shortcut {
        sequences: ["Ctrl+PgUp", "Alt+Up"]
        onActivated: main.step(-1)
    }
    Shortcut {
        sequences: ["Ctrl+Q", "Ctrl+W"]
        onActivated: Qt.quit()
    }
    Shortcut {
        sequences: ["Ctrl+Z"]
        enabled: Backend.mango.undo === true
        onActivated: Backend.undo()
    }
    Keys.onEscapePressed: {
        keyboardNav = true;
        nav.forceActiveFocus();
    }

    // ---------------------------------------------------------------- rail
    Rectangle {
        id: rail
        width: Theme.railWidth
        height: parent.height
        color: Theme.surfaceSunken
        Accessible.role: Accessible.Pane
        Accessible.name: "Settings pages"

        Rectangle {
            anchors.right: parent.right
            width: 1
            height: parent.height
            color: Theme.line
        }

        Row {
            id: brand
            x: Theme.space4 + Theme.space2
            y: Theme.space5
            spacing: Theme.space2
            Mark {
                size: 26
                anchors.verticalCenter: parent.verticalCenter
            }
            ArText {
                text: "Settings"
                size: 18
                lh: 26
                weight: Font.DemiBold
                anchors.verticalCenter: parent.verticalCenter
                Accessible.role: Accessible.Heading
            }
        }

        ArInput {
            id: search
            x: Theme.space4
            anchors.top: brand.bottom
            anchors.topMargin: Theme.space4
            width: rail.width - 2 * Theme.space4
            iconName: "search"
            placeholder: "Search settings"
            accessibleName: "Search settings"
            onTextChanged: {
                main.query = text;
                main.hit = 0;
            }
            input.Keys.onDownPressed: event => {
                if (main.results.length) {
                    main.hit = Math.min(main.results.length - 1, main.hit + 1);
                    event.accepted = true;
                } else {
                    nav.forceActiveFocus();
                }
            }
            input.Keys.onUpPressed: main.hit = Math.max(0, main.hit - 1)
            input.Keys.onEscapePressed: event => {
                if (text !== "")
                    text = "";
                else
                    nav.forceActiveFocus();
                event.accepted = true;
            }
            onAccepted: {
                if (main.results.length)
                    main.pick(main.hit);
            }
        }

        // Page list (no query) or search results (query).
        ListView {
            id: nav
            anchors.top: search.bottom
            anchors.topMargin: Theme.space4
            anchors.bottom: parent.bottom
            anchors.bottomMargin: Theme.space4
            x: Theme.space3
            width: rail.width - 2 * Theme.space3
            clip: true
            focus: true
            spacing: 2
            boundsBehavior: Flickable.StopAtBounds
            keyNavigationEnabled: false
            activeFocusOnTab: true
            model: main.query !== "" ? main.results : main.pages
            currentIndex: main.query !== "" ? main.hit : main.current
            Accessible.role: Accessible.List
            Accessible.name: main.query !== "" ? "Search results" : "Pages"

            Keys.onDownPressed: {
                main.keyboardNav = true;
                if (main.query !== "")
                    main.hit = Math.min(main.results.length - 1, main.hit + 1);
                else
                    main.open(main.pages[Math.min(main.pages.length - 1, main.current + 1)].id, "");
            }
            Keys.onUpPressed: {
                main.keyboardNav = true;
                if (main.query !== "")
                    main.hit = Math.max(0, main.hit - 1);
                else
                    main.open(main.pages[Math.max(0, main.current - 1)].id, "");
            }
            Keys.onReturnPressed: {
                if (main.query !== "")
                    main.pick(main.hit);
                else
                    main.focusPage();
            }
            Keys.onRightPressed: if (main.query === "") main.focusPage()
            Keys.onPressed: event => {
                if (event.key === Qt.Key_Home) {
                    main.open(main.pages[0].id, "");
                } else if (event.key === Qt.Key_End) {
                    main.open(main.pages[main.pages.length - 1].id, "");
                } else if (event.key === Qt.Key_Slash) {
                    main.focusSearch();
                } else if (event.text.trim() !== "" && !/[\x00-\x1f\x7f]/.test(event.text) && !(event.modifiers & (Qt.ControlModifier | Qt.AltModifier))) {
                    // Type to search.
                    search.forceActiveFocus();
                    search.text = event.text;
                } else {
                    event.accepted = false;
                    return;
                }
                event.accepted = true;
            }

            delegate: T.AbstractButton {
                id: item
                required property var modelData
                required property int index
                readonly property bool isCurrent: ListView.isCurrentItem
                width: ListView.view.width
                height: main.query !== "" ? 48 : 36
                hoverEnabled: true
                focusPolicy: Qt.NoFocus
                Accessible.role: Accessible.ListItem
                Accessible.name: modelData.title + (main.query !== "" ? ", " + modelData.where : "")
                Accessible.selected: isCurrent
                onClicked: {
                    main.keyboardNav = false;
                    if (main.query !== "")
                        main.pick(index);
                    else
                        main.open(modelData.id, "");
                    nav.forceActiveFocus();
                }
                background: Rectangle {
                    radius: Theme.radiusMd
                    color: item.isCurrent ? Theme.surfaceRaised : item.hovered ? Theme.surface : "transparent"
                    // shadow-sm under the current page (ArSteps)
                    Rectangle {
                        visible: item.isCurrent
                        z: -1
                        y: 1
                        width: parent.width
                        height: parent.height
                        radius: parent.radius
                        color: Theme.shadowSm
                    }
                    FocusRing {
                        show: item.isCurrent && nav.activeFocus && main.keyboardNav
                        inset: true
                        radius: Theme.radiusMd
                    }
                }
                contentItem: Row {
                    leftPadding: Theme.space3
                    spacing: Theme.space3
                    Icon {
                        name: item.modelData.icon
                        size: 18
                        color: item.isCurrent ? Theme.ink : Theme.inkMuted
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        width: item.width - 18 - 3 * Theme.space3
                        ArText {
                            width: parent.width
                            text: item.modelData.title
                            size: 14
                            lh: 20
                            weight: item.isCurrent ? Font.DemiBold : Font.Normal
                            color: item.isCurrent ? Theme.ink : Theme.inkMuted
                            elide: Text.ElideRight
                        }
                        ArText {
                            visible: main.query !== ""
                            width: parent.width
                            text: item.modelData.where || ""
                            size: 12
                            lh: 16
                            color: Theme.inkSubtle
                            elide: Text.ElideRight
                        }
                    }
                }
            }

            ArText {
                visible: main.query !== "" && main.results.length === 0
                width: parent.width
                leftPadding: Theme.space3
                text: "Nothing matches “" + main.query + "”."
                size: 13
                lh: 18
                wrapMode: Text.WordWrap
                color: Theme.inkMuted
            }
        }
    }

    // ---------------------------------------------------------------- pages
    Item {
        id: area
        x: rail.width
        width: parent.width - rail.width
        height: parent.height
        clip: true

        Rectangle {
            anchors.fill: parent
            color: Theme.surface
        }

        Repeater {
            id: pageRepeater
            model: main.pages
            Loader {
                id: loader
                required property var modelData
                required property int index
                anchors.fill: parent
                active: main.visited[index] === true
                visible: main.current === index
                opacity: visible ? 1 : 0
                source: "pages/" + modelData.file
                asynchronous: false
                onLoaded: (loader.item as Page).shown()
                Behavior on opacity {
                    NumberAnimation { duration: Theme.fadeSlow; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeStandard }
                }
            }
        }

        // The config isn't read by Mango at all: say so once, on every page.
        ArBanner {
            visible: Backend.ready && Backend.mango.configExists === false
            x: Theme.space6
            y: Theme.space3
            width: parent.width - 2 * Theme.space6
            kind: "warning"
            title: "Mango isn’t using your config"
            text: "~/.config/mango/config.conf is missing, so Mango uses its built-in settings and the changes you make here won’t show."
        }

        Toast {
            id: toast
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: Theme.space6
            onUndoRequested: Backend.undo()
        }
    }

    Connections {
        target: Backend
        function onNotify(kind, text, undo) {
            toast.show(kind, text, undo);
        }
    }
    // Keep what has the keyboard focus in view on long pages.
    Connections {
        target: main.Window.window
        function onActiveFocusItemChanged() {
            const loaded = main.pageAt(main.current);
            const item = main.Window.activeFocusItem;
            if (loaded && item)
                loaded.ensureVisible(item);
        }
    }
}
