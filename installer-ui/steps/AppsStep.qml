// Step 8 — Choose your apps (INSTALL_STEPS[7], AppChecklist). Categories from
// the engine catalog; "one" categories behave like radio groups, "any" like
// checkboxes. The footer note is the engine's EstimateDownload label.
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
    note: estimate
    valid: missingOne === ""
    helpText: "Pick the apps you want. Where it says Pick one, the app you choose becomes the default. Use the arrow keys to move between apps and Space to tick them. Everything can be changed later."

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
    readonly property string missingOne: {
        for (const c of categories)
            if (isOne(c) && c.id === "browser" && !((selection[c.id] || []).length))
                return c.id;
        return "";
    }
    // Every AppRow in visual order, for arrow-key navigation across sections.
    property var rowItems: []

    function isOne(c) {
        return c.choice === "one";
    }
    function modulesOf(cid) {
        return modules.filter(m => m.category === cid);
    }
    function isOn(cid, id) {
        return (selection[cid] || []).indexOf(id) >= 0;
    }
    function toggle(c, id) {
        const s = Object.assign({}, selection);
        const cur = (s[c.id] || []).slice();
        if (isOne(c)) {
            s[c.id] = [id];
        } else {
            const i = cur.indexOf(id);
            if (i >= 0)
                cur.splice(i, 1);
            else
                cur.push(id);
            s[c.id] = cur;
        }
        selection = s;
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
    function focusFirst() {
        if (rowItems.length)
            rowItems[0].forceActiveFocus();
    }
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
        }
        for (const id of (v.unselect || [])) {
            for (const k in s)
                s[k] = (s[k] || []).filter(x => x !== id);
        }
        selection = s;
        if (v.scroll !== undefined)
            flick.contentY = Math.max(0, Math.min(flick.contentHeight - flick.height, v.scroll));
        return "ok";
    }
    function moveFocus(from, delta) {
        const i = rowItems.indexOf(from);
        const j = i + delta;
        if (i < 0 || j < 0 || j >= rowItems.length)
            return;
        rowItems[j].forceActiveFocus(Qt.TabFocusReason);
    }
    function ensureVisible(item) {
        const p = item.mapToItem(flick.contentItem, 0, 0);
        if (p.y < flick.contentY)
            flick.contentY = Math.max(0, p.y - Theme.space4);
        else if (p.y + item.height > flick.contentY + flick.height - 40)
            flick.contentY = Math.min(flick.contentHeight - flick.height, p.y + item.height - flick.height + 56);
    }

    onSelectionChanged: estimateTimer.restart()
    Component.onCompleted: refreshEstimate()
    Timer {
        id: estimateTimer
        interval: 120
        onTriggered: page.refreshEstimate()
    }

    Flickable {
        id: flick
        width: page.width + 8
        x: -4
        y: -4
        height: page.availableHeight + 4
        contentHeight: sections.height + 48
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        Accessible.role: Accessible.Pane

        Column {
            id: sections
            x: 4
            y: 4
            width: page.width
            spacing: Theme.space4

            Repeater {
                model: page.categories
                Column {
                    id: section
                    required property var modelData
                    readonly property var cat: modelData
                    width: sections.width
                    spacing: Theme.space2
                    Accessible.role: page.isOne(cat) ? Accessible.Grouping : Accessible.Grouping
                    Accessible.name: cat.name

                    Row {
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
                            text: (page.isOne(section.cat) ? "Pick one" : "Pick any") + (section.cat.note ? " · " + section.cat.note : "")
                            size: 12
                            lh: 18
                            color: Theme.inkSubtle
                        }
                    }

                    Grid {
                        columns: 2
                        columnSpacing: Theme.space2
                        rowSpacing: Theme.space2
                        width: parent.width
                        Repeater {
                            model: page.modulesOf(section.cat.id)
                            AppRow {
                                id: appRow
                                required property var modelData
                                width: (section.width - Theme.space2) / 2
                                appId: modelData.id
                                tile: modelData.tile || modelData.id
                                name: modelData.name
                                summary: modelData.summary
                                isDefault: !!modelData["default"]
                                radio: page.isOne(section.cat)
                                checked: page.isOn(section.cat.id, modelData.id)
                                error: Wizard.fieldErrors[section.cat.id] !== undefined
                                onClicked: page.toggle(section.cat, modelData.id)
                                onActiveFocusChanged: if (activeFocus) page.ensureVisible(appRow)
                                Keys.onRightPressed: page.moveFocus(appRow, 1)
                                Keys.onLeftPressed: page.moveFocus(appRow, -1)
                                Keys.onDownPressed: page.moveFocus(appRow, 2)
                                Keys.onUpPressed: page.moveFocus(appRow, -2)
                                Component.onCompleted: page.rowItems = page.rowItems.concat([appRow])
                                Component.onDestruction: page.rowItems = page.rowItems.filter(r => r !== appRow)
                            }
                        }
                    }
                }
            }
        }
    }
}
