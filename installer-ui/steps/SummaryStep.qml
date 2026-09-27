// Step 9 — Ready to install (INSTALL_STEPS[8]). Rows from GetSummary with
// "Change" links back to each step, the erase warning, and the one primary
// action: "Erase disk and install" / "Install alongside {OS}". Only a click (or
// Enter/Space on the focused button) starts it, and only after a short wait: Enter
// elsewhere on the page, a key held down or a double click from Apps do nothing.
pragma ComponentBehavior: Bound
import QtQuick
import ".."
import "../components"

StepPage {
    id: page
    stepId: "summary"
    title: "Ready to install"
    lede: "Check everything below. Nothing has been written to your disk yet."
    measure: 620
    nextLabel: primaryLabel
    valid: rows.length > 0
    armDelay: 1000
    armVisible: true
    enterActivates: false
    helpText: "Check each line. Use Change to go back to a step; your other answers are kept. Installing starts only when you press the button at the bottom right."

    property var rows: []
    property string warning: ""
    property string primaryLabel: "Erase disk and install"
    property bool loaded: false

    readonly property var icons: ({
            welcome: "language",
            keyboard: "keyboard",
            network: "wifi",
            timezone: "clock",
            disk: "disk",
            encryption: "shield-lock",
            account: "user",
            apps: "grid"
        })

    // Plain text → StyledText: escape, then **bold** or the "erase everything on X" phrase.
    function richWarning(t) {
        let s = String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        if (s.indexOf("**") >= 0)
            return s.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
        return s.replace(/(erase everything on [^.]+)/, "<b>$1</b>");
    }
    function load() {
        Engine.call("GetSummary", null, (res, err) => {
            if (err) {
                Wizard.showError(err);
                return;
            }
            rows = res.rows || [];
            warning = res.warning || "";
            primaryLabel = res.primary_label || "Erase disk and install";
            loaded = true;
        });
    }
    function primary() {
        Wizard.startInstall();
    }
    // Take keyboard focus off the footer button (it keeps it after a click on Apps' Next,
    // where Enter would then press "Erase disk and install").
    function focusFirst() {
        page.forceActiveFocus();
    }

    Component.onCompleted: load()

    Column {
        width: page.width
        spacing: 14

        ArList {
            id: list
            width: parent.width
            activeFocusOnTab: false
            view.interactive: false
            accessibleName: "Summary"
            model: page.rows
            delegate: ArListRow {
                id: srow
                required property var modelData
                required property int index
                width: ListView.view.width
                first: index === 0
                hoverEnabled: false
                iconName: page.icons[modelData.step] || "check"
                title: modelData.label
                desc: modelData.value
                ArButton {
                    variant: "ghost"
                    size: "sm"
                    text: "Change"
                    gapColor: Theme.surfaceRaised
                    Accessible.name: "Change " + srow.modelData.label.toLowerCase()
                    onClicked: Wizard.gotoStep(srow.modelData.step)
                }
            }
        }

        // An answer the engine rejected when installing was asked for (for example a
        // passphrase too weak): where to change it. The footer has the message.
        ArBanner {
            visible: Wizard.errorStep !== ""
            width: parent.width
            kind: "error"
            title: "The " + Wizard.railName(Wizard.errorStep) + " step needs a change"
            actionText: "Go to " + Wizard.railName(Wizard.errorStep)
            onAction: Wizard.gotoStep(Wizard.errorStep)
        }

        ArBanner {
            visible: page.warning !== ""
            width: parent.width
            kind: "warning"
            strong: true
            text: page.richWarning(page.warning)
        }
    }
}
