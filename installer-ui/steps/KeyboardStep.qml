// Step 2 — Keyboard layout (INSTALL_STEPS[1]). The layout is saved as soon as it
// is picked so the engine can apply it to the live session and "Try it" types
// with it.
pragma ComponentBehavior: Bound
import QtQuick
import ".."
import "../components"

StepPage {
    id: page
    stepId: "keyboard"
    title: "Choose your keyboard layout"
    lede: "This is how the keys on your keyboard will type. You can add more layouts later."
    fillHeight: true
    measure: 560
    valid: selectedKey !== ""
    helpText: "Pick the layout printed on your keys. Then type in the Try it box to check that the letters on screen match the keys you press."

    readonly property var layouts: (Wizard.step.options && Wizard.step.options.layouts) || []
    property string selectedKey: {
        const d = Wizard.step.data || {};
        return d.layout ? d.layout + ":" + (d.variant || "") : "";
    }
    function keyOf(l) {
        return l.layout + ":" + (l.variant || "");
    }
    function indexOfSelected() {
        for (let i = 0; i < layouts.length; i++)
            if (keyOf(layouts[i]) === selectedKey)
                return i;
        return -1;
    }
    function selectedLayout() {
        const i = indexOfSelected();
        return i >= 0 ? layouts[i] : null;
    }
    function pick(i) {
        selectedKey = keyOf(layouts[i]);
        applyTimer.restart();
    }
    function commit(done) {
        const l = selectedLayout();
        if (!l) {
            done(false);
            return;
        }
        applyTimer.stop();
        Wizard.layoutName = l.name;
        Wizard.saveStep("keyboard", {
            layout: l.layout,
            variant: l.variant || ""
        }, done);
    }
    function focusFirst() {
        list.mouseUsed = true;
        list.forceActiveFocus();
    }
    function fillForm(v) {
        if (v.layout !== undefined)
            selectedKey = v.layout + ":" + (v.variant || "");
        if (v["try"] !== undefined) {
            tryIt.text = v["try"];
            tryIt.forceActiveFocus();
        }
        return "ok";
    }

    // Apply the picked layout live (engine → compositor) shortly after picking.
    Timer {
        id: applyTimer
        interval: 250
        onTriggered: {
            const l = page.selectedLayout();
            if (l)
                Wizard.saveStep("keyboard", {
                    layout: l.layout,
                    variant: l.variant || ""
                }, null);
        }
    }

    Column {
        width: page.width
        spacing: Theme.space4

        ArList {
            id: list
            width: parent.width
            height: Math.min(implicitHeight, Math.max(120, page.availableHeight - tryIt.height - Theme.space4))
            accessibleName: "Keyboard layouts"
            model: page.layouts
            currentIndex: page.indexOfSelected()
            onPicked: index => page.pick(index)
            delegate: ArListRow {
                required property var modelData
                required property int index
                width: ListView.view.width
                first: index === 0
                iconName: "keyboard"
                title: modelData.name
                desc: modelData.suggested ? "Suggested for your language" : (modelData.description || "")
                selected: page.keyOf(modelData) === page.selectedKey
                check: selected
                showFocus: ListView.isCurrentItem && list.showFocus
                onClicked: list.clickRow(index)
            }
        }

        ArInput {
            id: tryIt
            width: parent.width
            label: "Try it"
            help: "Type a few letters to check the layout matches your keys."
        }
    }
}
