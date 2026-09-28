// Step 8 — Choose your apps (INSTALL_STEPS[7], AppChecklist). Categories from
// the engine catalog; "one" categories behave like radio groups, "any" like
// checkboxes. A "one" category that isn't required (Office) can be left empty:
// clicking the ticked app unticks it. The footer note is the engine's
// EstimateDownload label.
// The design's sections are always open. The optional groups the catalog marks
// `collapsed` ("More apps": Music & audio … Utilities; nothing in them is ticked
// by default) start folded behind a header row, unless something in them is
// ticked. The search box looks through every app (name, summary, group) and
// shows the groups with matches open. Only open groups create their app rows.
// When the engine refuses the picks on Next (a missing requirement: "Podman
// Desktop needs Podman. Tick it too."), the group opens, says why in red under
// its apps, and the footer shows the same sentence until the group is changed.
pragma ComponentBehavior: Bound
import QtQuick
import ".."
import "../components"

StepPage {
    id: page
    stepId: "apps"
    title: "Choose your apps"
    lede: "We’ve ticked our favourites. Change anything — you can add or remove apps later."
    measure: 640
    fade: true
    fillHeight: true
    // The engine's apps errors are keyed by group; the first one replaces the estimate
    // in the footer (the group also says it, in red, under its apps).
    note: firstError !== "" ? Wizard.fieldErrors[firstError] : estimate
    valid: missingOne === ""
    helpText: "Pick the apps you want. Where it says Pick one, the app you choose becomes the default. More apps wait in the groups under More apps: open a group, or type to search every app. Use the arrow keys to move between apps and groups, Space to tick an app, and Space or Enter to open a group. Everything can be changed later."

    readonly property var opts: Wizard.step.options || {}
    readonly property var categories: opts.categories || []
    readonly property var modules: opts.modules || []
    property var selection: {
        const d = Wizard.step.data || {};
        if (d.selection)
            return JSON.parse(JSON.stringify(d.selection));
        const s = {};
        for (const m of modules)
            if (m.default) {
                s[m.category] = s[m.category] || [];
                s[m.category].push(m.id);
            }
        return s;
    }
    property string estimate: ""
    // First required category with nothing picked (the engine refuses those).
    readonly property string missingOne: {
        for (const c of categories)
            if (c.required && !((selection[c.id] || []).length))
                return c.id;
        return "";
    }
    // First group the engine flagged on Next ("Podman Desktop needs Podman. Tick it too.").
    readonly property string firstError: {
        for (const c of categories)
            if (Wizard.fieldErrors[c.id] !== undefined)
                return c.id;
        return "";
    }
    property string query: ""
    readonly property string needle: query.trim().toLowerCase()
    readonly property bool searching: needle !== ""
    readonly property var matching: modules.filter(m => matches(m))
    // Folded groups the person opened: category id → true.
    property var opened: ({})
    readonly property string firstFolded: {
        for (const c of categories)
            if (c.collapsed)
                return c.id;
        return "";
    }
    property int rowCount: 0            // AppRows that exist (open groups only)
    // For tests (IPC state().step): open folded groups, app rows, search matches.
    testState: ({
            open: categories.filter(c => c.collapsed && isOpen(c)).map(c => c.id),
            rows: rowCount,
            matches: matching.length,
            query: query,
            errors: categories.filter(c => Wizard.fieldErrors[c.id] !== undefined && isOpen(c) && (!searching || modulesOf(c.id).length > 0)).map(c => Wizard.fieldErrors[c.id])
        })

    function isOne(c) {
        return c.choice === "one";
    }
    function catName(id) {
        const c = categories.find(x => x.id === id);
        return c ? c.name : "";
    }
    function matches(m) {
        if (!searching)
            return true;
        return [m.name, m.summary, m.id, catName(m.category)].some(s => String(s || "").toLowerCase().indexOf(needle) >= 0);
    }
    function modulesOf(cid) {
        return modules.filter(m => m.category === cid && matches(m));
    }
    // A section shows its apps when it isn't foldable, while searching, when the person
    // opened it, or when the engine flagged something in it.
    function isOpen(c) {
        return !c.collapsed || searching || !!opened[c.id] || Wizard.fieldErrors[c.id] !== undefined;
    }
    function setOpen(cid, on) {
        const o = Object.assign({}, opened);
        if (on)
            o[cid] = true;
        else
            delete o[cid];
        opened = o;
    }
    function isOn(cid, id) {
        return (selection[cid] || []).indexOf(id) >= 0;
    }
    function toggle(c, id) {
        const s = Object.assign({}, selection);
        const cur = (s[c.id] || []).slice();
        if (isOne(c)) {
            s[c.id] = (!c.required && cur.indexOf(id) >= 0) ? [] : [id];
        } else {
            const i = cur.indexOf(id);
            if (i >= 0)
                cur.splice(i, 1);
            else
                cur.push(id);
            s[c.id] = cur;
        }
        selection = s;
        Wizard.clearFieldError(c.id);
    }
    function refreshEstimate() {
        Engine.call("EstimateDownload", {
            selection: selection
        }, (res, err) => {
            if (!err)
                estimate = res.label || "";
        });
    }
    function commit(done) {
        Wizard.saveStep("apps", {
            selection: selection
        }, done);
    }

    // ---- keyboard: every app row and group header in reading order
    function navItems() {
        const out = [];
        for (let i = 0; i < sectionRepeater.count; i++) {
            const s = sectionRepeater.itemAt(i);
            if (!s || !s.visible)
                continue;
            if (s.foldable && !searching)
                out.push(s.header);
            for (const r of s.rowList())
                out.push(r);
        }
        return out;
    }
    function focusItem(item) {
        if (item)
            item.forceActiveFocus(Qt.TabFocusReason);
    }
    function focusFirst() {
        focusItem(navItems()[0]);
    }
    // Previous / next item in reading order; above the first one is the search box.
    function stepFocus(from, delta) {
        const items = navItems();
        const i = items.indexOf(from);
        if (i < 0)
            return;
        if (i + delta < 0)
            search.forceActiveFocus();
        else if (i + delta < items.length)
            focusItem(items[i + delta]);
    }
    // Two columns: Down/Up stay in the column while the group has a line there.
    function rowDown(row, section) {
        const rs = section.rowList();
        const i = rs.indexOf(row);
        if (i + 2 < rs.length)
            focusItem(rs[i + 2]);
        else if (i + 1 < rs.length && i % 2 === 1)
            focusItem(rs[i + 1]);           // the last line has one app
        else
            stepFocus(rs[rs.length - 1], 1);
    }
    function rowUp(row, section) {
        const rs = section.rowList();
        const i = rs.indexOf(row);
        if (i >= 2)
            focusItem(rs[i - 2]);
        else
            stepFocus(rs[0], -1);
    }
    // Typing on an app or a group goes to the search box.
    function typeToSearch(event) {
        const t = event.text;
        if (t.length !== 1 || t === " " || t.charCodeAt(0) < 32 || t.charCodeAt(0) === 127)
            return;
        if (event.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier))
            return;
        query = query + t;
        search.forceActiveFocus();
        search.input.cursorPosition = search.text.length;
        event.accepted = true;
    }
    function ensureVisible(item) {
        const p = item.mapToItem(flick.contentItem, 0, 0);
        if (p.y < flick.contentY)
            flick.contentY = Math.max(0, p.y - Theme.space4);
        else if (p.y + item.height > flick.contentY + flick.height - 40)
            flick.contentY = Math.max(0, Math.min(flick.contentHeight - flick.height, p.y + item.height - flick.height + 56));
    }

    // Test hook (IPC "fill"): select / unselect / toggle app ids (a folded group
    // opens to show them), query, open / close group ids, scroll, focus
    // ("search", an app id or "group:<id>").
    function fillForm(v) {
        const s = Object.assign({}, selection);
        for (const id of (v.select || [])) {
            const m = modules.find(x => x.id === id);
            if (!m)
                continue;
            const c = categories.find(x => x.id === m.category);
            if (c && isOne(c))
                s[c.id] = [id];
            else {
                s[m.category] = (s[m.category] || []).filter(x => x !== id).concat([id]);
            }
            setOpen(m.category, true);
            Wizard.clearFieldError(m.category);
        }
        for (const id of (v.unselect || [])) {
            for (const k in s)
                if ((s[k] || []).indexOf(id) >= 0) {
                    s[k] = s[k].filter(x => x !== id);
                    Wizard.clearFieldError(k);
                }
        }
        selection = s;
        // like clicking the app's row
        for (const id of (v.toggle || [])) {
            const m = modules.find(x => x.id === id);
            const c = m ? categories.find(x => x.id === m.category) : null;
            if (c) {
                setOpen(c.id, true);
                toggle(c, id);
            }
        }
        if (v.query !== undefined)
            query = v.query;
        for (const cid of (v.open || []))
            setOpen(cid, true);
        for (const cid of (v.close || []))
            setOpen(cid, false);
        if (v.scroll !== undefined)
            flick.contentY = Math.max(0, Math.min(flick.contentHeight - flick.height, v.scroll));
        if (v.focus !== undefined) {
            let target = null;
            if (v.focus === "search")
                target = search;
            else
                target = navItems().find(it => it.navId === v.focus) || null;
            if (!target)
                return "nothing to focus: " + v.focus;
            target.forceActiveFocus(Qt.TabFocusReason);
        }
        return "ok";
    }

    onSelectionChanged: estimateTimer.restart()
    onQueryChanged: flick.contentY = 0
    Component.onCompleted: {
        // Groups that already have something ticked (back from the Summary) start open.
        const o = {};
        for (const c of categories)
            if (c.collapsed && (selection[c.id] || []).length)
                o[c.id] = true;
        opened = o;
        refreshEstimate();
    }
    Timer {
        id: estimateTimer
        interval: 120
        onTriggered: page.refreshEstimate()
    }

    ArInput {
        id: search
        width: page.width
        iconName: "search"
        placeholder: "Search " + page.modules.length + " apps"
        accessibleName: "Search apps"
        text: page.query
        onEdited: page.query = text
        // Down (or Enter with a search) goes to the first app; Esc clears the search first.
        input.Keys.onDownPressed: event => {
            page.focusFirst();
            event.accepted = true;
        }
        input.Keys.onReturnPressed: event => {
            if (page.searching) {
                page.focusFirst();
                event.accepted = true;
            } else {
                event.accepted = false;
            }
        }
        input.Keys.onEnterPressed: event => {
            if (page.searching) {
                page.focusFirst();
                event.accepted = true;
            } else {
                event.accepted = false;
            }
        }
        input.Keys.onEscapePressed: event => {
            if (page.query !== "") {
                page.query = "";
                event.accepted = true;
            } else {
                event.accepted = false;
            }
        }
    }

    Flickable {
        id: flick
        width: page.width + 8
        x: -4
        y: search.height + Theme.space3 - 4
        height: Math.max(0, page.availableHeight - search.height - Theme.space3 + 4)
        contentHeight: sections.height + 48
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        Accessible.role: Accessible.Pane

        Column {
            id: sections
            x: 4
            y: 4
            width: page.width
            spacing: Theme.space2

            ArText {
                visible: page.searching && page.matching.length === 0
                width: parent.width
                text: "No app matches “" + page.query.trim() + "”. Try another name, or what it does (music, PDF, games)."
                wrapMode: Text.WordWrap
                color: Theme.inkMuted
            }

            Repeater {
                id: sectionRepeater
                model: page.categories
                Column {
                    id: section
                    required property var modelData
                    required property int index
                    readonly property var cat: modelData
                    readonly property bool foldable: !!cat.collapsed
                    readonly property bool open: page.isOpen(cat)
                    readonly property var apps: page.modulesOf(cat.id)
                    readonly property int picked: (page.selection[cat.id] || []).length
                    readonly property string rule: page.isOne(cat) ? (cat.required ? "Pick one" : "Pick one or none") : "Pick any"
                    property alias header: groupHeader
                    visible: !page.searching || apps.length > 0
                    width: sections.width
                    spacing: Theme.space2
                    // Open sections keep the design's 16px between them; folded rows sit closer.
                    topPadding: section.index > 0 && section.open ? Theme.space2 : 0
                    Accessible.role: Accessible.Grouping
                    Accessible.name: cat.name

                    // After a refused Next, the first flagged group scrolls its message into view.
                    function reveal() {
                        if (!section.visible || page.firstError !== section.cat.id)
                            return;
                        // The group may have just opened: place its rows before measuring.
                        appGrid.forceLayout();
                        section.forceLayout();
                        sections.forceLayout();
                        page.ensureVisible(errorLine);
                    }
                    Connections {
                        target: Wizard
                        function onFieldErrorsChanged() {
                            if (page.firstError === section.cat.id)
                                Qt.callLater(section.reveal);
                        }
                    }

                    function rowList() {
                        const out = [];
                        for (let i = 0; i < rows.count; i++) {
                            const r = rows.itemAt(i);
                            if (r)
                                out.push(r);
                        }
                        return out;
                    }

                    // "More apps": once, above the first foldable group.
                    Column {
                        visible: !page.searching && page.firstFolded === section.cat.id
                        width: parent.width
                        topPadding: Theme.space4
                        bottomPadding: Theme.space1
                        spacing: 2
                        Rectangle {
                            width: parent.width
                            height: 1
                            color: Theme.line
                        }
                        Item {
                            width: 1
                            height: Theme.space3
                        }
                        ArText {
                            text: "MORE APPS"
                            size: 13
                            lh: 18
                            weight: Font.DemiBold
                            tracking: 0.06
                            Accessible.role: Accessible.Heading
                        }
                        ArText {
                            width: parent.width
                            text: "Nothing here is ticked by default. Open a group, or search, to add apps."
                            size: 12
                            lh: 18
                            wrapMode: Text.WordWrap
                            color: Theme.inkSubtle
                        }
                    }

                    // The design's section header (and every header while searching).
                    Row {
                        visible: !section.foldable || page.searching
                        spacing: Theme.space2
                        ArText {
                            text: section.cat.name.toUpperCase()
                            size: 13
                            lh: 18
                            weight: Font.DemiBold
                            tracking: 0.06
                            Accessible.role: Accessible.Heading
                        }
                        ArText {
                            text: section.rule + (section.cat.note ? " · " + section.cat.note : "") + (section.foldable && section.picked ? " · " + section.picked + " picked" : "")
                            size: 12
                            lh: 18
                            color: Theme.inkSubtle
                        }
                    }

                    AppGroupHeader {
                        id: groupHeader
                        readonly property string navId: "group:" + section.cat.id
                        visible: section.foldable && !page.searching
                        width: section.width
                        name: section.cat.name
                        rule: section.rule
                        picked: section.picked
                        count: section.apps.length
                        preview: section.apps.map(m => m.name).join(", ")
                        expanded: section.open
                        error: Wizard.fieldErrors[section.cat.id] !== undefined
                        onClicked: page.setOpen(section.cat.id, !section.open)
                        onActiveFocusChanged: if (activeFocus) page.ensureVisible(groupHeader)
                        Keys.onDownPressed: page.stepFocus(groupHeader, 1)
                        Keys.onUpPressed: page.stepFocus(groupHeader, -1)
                        Keys.onRightPressed: {
                            if (section.open)
                                page.stepFocus(groupHeader, 1);
                            else
                                page.setOpen(section.cat.id, true);
                        }
                        Keys.onLeftPressed: {
                            if (section.open && !groupHeader.error)
                                page.setOpen(section.cat.id, false);
                            else
                                page.stepFocus(groupHeader, -1);
                        }
                        Keys.onPressed: event => page.typeToSearch(event)
                    }

                    Grid {
                        id: appGrid
                        visible: section.open
                        columns: 2
                        columnSpacing: Theme.space2
                        rowSpacing: Theme.space2
                        width: parent.width
                        Repeater {
                            id: rows
                            model: section.open ? section.apps : []
                            AppRow {
                                id: appRow
                                required property var modelData
                                readonly property string navId: modelData.id
                                width: (section.width - Theme.space2) / 2
                                appId: modelData.id
                                tile: modelData.tile || modelData.id
                                name: modelData.name
                                summary: modelData.summary
                                isDefault: !!modelData["default"]
                                proprietary: !!modelData.proprietary
                                radio: page.isOne(section.cat)
                                checked: page.isOn(section.cat.id, modelData.id)
                                error: Wizard.fieldErrors[section.cat.id] !== undefined
                                onClicked: page.toggle(section.cat, modelData.id)
                                onActiveFocusChanged: if (activeFocus) page.ensureVisible(appRow)
                                Keys.onRightPressed: page.stepFocus(appRow, 1)
                                Keys.onLeftPressed: page.stepFocus(appRow, -1)
                                Keys.onDownPressed: page.rowDown(appRow, section)
                                Keys.onUpPressed: page.rowUp(appRow, section)
                                Keys.onPressed: event => page.typeToSearch(event)
                                Component.onCompleted: page.rowCount++
                                Component.onDestruction: page.rowCount--
                            }
                        }
                    }

                    // The engine's reason for refusing this group (e.g. a missing requirement).
                    ArText {
                        id: errorLine
                        readonly property string message: Wizard.fieldErrors[section.cat.id] || ""
                        visible: message !== "" && section.open
                        width: parent.width
                        text: message
                        size: 13
                        lh: 18
                        wrapMode: Text.WordWrap
                        color: Theme.error
                        Accessible.role: Accessible.AlertMessage
                        Accessible.name: message
                    }
                }
            }
        }
    }
}
