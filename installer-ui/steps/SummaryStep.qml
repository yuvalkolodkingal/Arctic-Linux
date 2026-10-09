// Step 9 — Ready to install (INSTALL_STEPS[8]). Rows from GetSummary with
// "Change" links back to each step (an easy-to-guess disk passphrase or password is
// noted in its row, so the warning doesn't grow), the erase warning, and the one primary
// action: "Erase disk and install" / "Install alongside {OS}". Only a click (or
// Enter/Space on the focused button) starts it, and only after a short wait: Enter
// elsewhere on the page, a key held down or a double click from Apps do nothing.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic as Controls
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

    function ensureVisible(item) {
        const p = item.mapToItem(summaryFlick.contentItem, 0, 0);
        if (p.y < summaryFlick.contentY)
            summaryFlick.contentY = Math.max(0, p.y - 4);
        else if (p.y + item.height > summaryFlick.contentY + summaryFlick.height)
            summaryFlick.contentY = Math.max(0, Math.min(summaryFlick.contentHeight - summaryFlick.height, p.y + item.height - summaryFlick.height + 4));
    }

    Component.onCompleted: load()

    // Keep the disclosure, every Change link and the erase warning reachable
    // above the persistent footer at smaller output sizes.
    Flickable {
        id: summaryFlick
        width: page.width + 8
        x: -4
        y: -4
        height: Math.max(0, Math.min(summaryColumn.height + 8, page.availableHeight + 4))
        contentWidth: width
        contentHeight: summaryColumn.height + 8
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        interactive: contentHeight > height
        Accessible.role: Accessible.Pane
        Accessible.name: "Installation summary"
        activeFocusOnTab: interactive
        function scrollBy(dy) {
            contentY = Math.max(0, Math.min(contentHeight - height, contentY + dy));
        }
        Keys.onPressed: event => {
            const step = Math.max(40, height - 48);
            if (event.key === Qt.Key_Down)
                scrollBy(40);
            else if (event.key === Qt.Key_Up)
                scrollBy(-40);
            else if (event.key === Qt.Key_PageDown || event.key === Qt.Key_Space)
                scrollBy(step);
            else if (event.key === Qt.Key_PageUp)
                scrollBy(-step);
            else if (event.key === Qt.Key_Home)
                contentY = 0;
            else if (event.key === Qt.Key_End)
                scrollBy(contentHeight);
            else
                return;
            event.accepted = true;
        }
        Controls.ScrollBar.vertical: Controls.ScrollBar {
            policy: Controls.ScrollBar.AsNeeded
            width: 6
            contentItem: Rectangle {
                implicitWidth: 6
                radius: 3
                color: Theme.inkMuted
            }
        }
        Rectangle {
            visible: summaryFlick.activeFocus
            parent: summaryFlick
            anchors.fill: parent
            color: "transparent"
            radius: Theme.radiusMd
            border.width: Theme.focusWidth
            border.color: Theme.focus
            z: 10
        }

        Column {
            id: summaryColumn
            x: 4
            y: 4
            width: page.width
            spacing: 14

            ArBanner {
                width: parent.width
                kind: "info"
                title: "Local dictation setup"
                text: Engine.dictationDownloadNotice
            }

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
                    // The engine names the icon (the Drivers row shares the apps step).
                    iconName: modelData.icon || page.icons[modelData.step] || "check"
                    title: modelData.label
                    desc: modelData.value
                    ArButton {
                        id: changeButton
                        onActiveFocusChanged: if (activeFocus) Qt.callLater(() => page.ensureVisible(changeButton))
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
            // username the system already has): where to change it. The footer has the message.
            FocusScope {
                id: errorScope
                visible: Wizard.errorStep !== ""
                width: parent.width
                implicitHeight: errorBanner.height
                onActiveFocusChanged: if (activeFocus) Qt.callLater(() => page.ensureVisible(errorScope))
                ArBanner {
                    id: errorBanner
                    width: parent.width
                    kind: "error"
                    title: "The " + Wizard.railName(Wizard.errorStep) + " step needs a change"
                    actionText: "Go to " + Wizard.railName(Wizard.errorStep)
                    onAction: Wizard.gotoStep(Wizard.errorStep)
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
}
