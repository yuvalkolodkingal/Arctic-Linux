// Step 1 — Welcome and language (INSTALL_STEPS[0]).
pragma ComponentBehavior: Bound
import QtQuick
import ".."
import "../components"

StepPage {
    id: page
    stepId: "welcome"
    hero: "welcome"
    title: "Welcome to Arctic Linux"
    lede: "This takes about 10 minutes. First, pick the language you’d like to use."
    note: "Nothing is changed on this computer until the Summary step."
    showBack: false
    fade: true
    fillHeight: true
    measure: 560
    valid: selected !== ""
    helpText: "Pick the language for the installer and for your new system. Type in the search box to find it quickly. You can change it later in Settings."

    readonly property var languages: (Wizard.step.options && Wizard.step.options.languages) || []
    property string selected: (Wizard.step.data && Wizard.step.data.language) || (Wizard.step.options && Wizard.step.options.suggested) || ""
    property string query: ""
    readonly property var filtered: {
        const q = query.trim().toLowerCase();
        if (q === "")
            return languages;
        return languages.filter(l => (l.name || "").toLowerCase().indexOf(q) >= 0 || (l.english || "").toLowerCase().indexOf(q) >= 0 || (l.id || "").toLowerCase().indexOf(q) >= 0);
    }

    onSelectedChanged: updateRail()
    // Typing narrows the list; if the chosen language is filtered out, the first
    // match becomes the choice, so "deu" + Enter means German.
    onFilteredChanged: {
        if (query.trim() !== "" && filtered.length && indexOfSelected() < 0)
            selected = filtered[0].id;
        list.currentIndex = indexOfSelected();
    }
    Component.onCompleted: updateRail()

    function updateRail() {
        for (const l of languages)
            if (l.id === selected)
                Wizard.languageName = l.name;
    }
    function indexOfSelected() {
        for (let i = 0; i < filtered.length; i++)
            if (filtered[i].id === selected)
                return i;
        return -1;
    }
    function commit(done) {
        Wizard.saveStep("welcome", {
            language: selected
        }, done);
    }
    function focusFirst() {
        list.mouseUsed = true;
        list.forceActiveFocus();
    }
    function fillForm(v) {
        if (v.language !== undefined)
            selected = v.language;
        if (v.query !== undefined)
            query = v.query;
        return "ok";
    }

    Column {
        width: page.width
        spacing: 10

        ArInput {
            id: search
            width: parent.width
            iconName: "search"
            placeholder: "Search languages"
            accessibleName: "Search languages"
            text: page.query
            onEdited: page.query = text
            input.Keys.onDownPressed: event => {
                list.forceActiveFocus();
                if (list.currentIndex < 0 && page.filtered.length)
                    list.pickRow(0, false);
                event.accepted = true;
            }
        }

        ArList {
            id: list
            width: parent.width
            height: Math.min(implicitHeight, Math.max(120, page.availableHeight - search.height - 10))
            accessibleName: "Languages"
            model: page.filtered
            currentIndex: page.indexOfSelected()
            onPicked: index => page.selected = page.filtered[index].id
            // Typing on the list goes to the search box.
            onTyped: text => {
                page.query = page.query + text;
                search.forceActiveFocus();
                search.input.cursorPosition = search.text.length;
            }
            delegate: ArListRow {
                required property var modelData
                required property int index
                width: ListView.view.width
                first: index === 0
                title: modelData.name
                desc: modelData.english
                selected: modelData.id === page.selected
                check: selected
                showFocus: ListView.isCurrentItem && list.showFocus
                onClicked: list.clickRow(index)
            }
        }

        ArText {
            visible: page.filtered.length === 0
            text: "No language matches “" + page.query + "”."
            color: Theme.inkMuted
        }
    }
}
