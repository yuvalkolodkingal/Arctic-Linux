// Step 2 — Keyboard layout (INSTALL_STEPS[1]). The layout is saved as soon as it
// is picked, and Wizard applies what the engine stored to the live session
// (live/live-keyboard), so "Try it", the disk passphrase and the password are
// typed with the layout the installed system uses.
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
    // Can't type Latin letters: English (US) comes first and Alt+Shift switches (the
    // engine says so for the saved choice; the list covers the moment before saving).
    readonly property bool nonLatin: {
        const l = selectedLayout();
        if (l === null)
            return false;
        if (Wizard.keyboardXkb && l.layout === Wizard.keyboardLayout && (l.variant || "") === Wizard.keyboardVariant)
            return Wizard.keyboardNonLatin;
        return Wizard.nonLatinLayouts.indexOf(l.layout) >= 0;
    }
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
        if (v.layout !== undefined) {
            selectedKey = v.layout + ":" + (v.variant || "");
            applyTimer.restart();
        }
        if (v["try"] !== undefined) {
            tryIt.text = v["try"];
            tryIt.forceActiveFocus();
        }
        return "ok";
    }

    // Save the picked layout shortly after picking; Wizard.saveStep then applies it
    // to the live session.
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
            help: page.nonLatin ? "English (US) is added too, so you can type passwords. Alt + Shift switches between them." : "Type a few letters to check the layout matches your keys."
        }
    }
}
