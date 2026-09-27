// Step 9 — Ready to install (INSTALL_STEPS[8]). Rows from GetSummary with
// "Change" links back to each step, the erase warning, and the one primary
// action: "Erase disk and install" / "Install alongside {OS}".
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
    function focusFirst() {
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

        ArBanner {
            visible: page.warning !== ""
            width: parent.width
            kind: "warning"
            strong: true
            text: page.richWarning(page.warning)
        }
    }
}
