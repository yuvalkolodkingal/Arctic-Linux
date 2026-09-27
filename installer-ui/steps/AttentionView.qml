// Step 11 — One app needs attention / Something went wrong (INSTALL_STEPS[10]).
// Replaces the Install page while the engine waits: an optional app failed
// (Try again / Skip {App}) or a core step failed (Try again / Change your answers,
// back to the Summary / Save log to USB). Show details has the engine's own error.
import QtQuick
import ".."
import "../components"

StepPage {
    id: page
    stepId: "install"
    readonly property bool fatal: Wizard.failure !== null
    readonly property var ev: fatal ? Wizard.failure : (Wizard.attention || {})
    readonly property string appName: (!fatal && ev.module) ? (ev.module.name || ev.module.id) : ""
    title: fatal ? "Something went wrong while installing" : "One app needs attention"
    lede: ""
    measure: 560
    showBack: false
    showNext: false
    // Attention comes while the apps install, before the account is set up.
    caption: fatal ? "Don’t remove the USB stick yet." : "Only optional apps are affected. The install carries on once you choose."
    helpText: fatal ? "A part of the system couldn’t be installed. Try again first. If the problem is one of your answers (for example the disk), use Change your answers to go back to the Summary. If it keeps failing, save the log to the USB stick and share it with us when you ask for help." : "An optional app couldn’t be downloaded. Try again, or skip it — you can add it later from the Software app. The rest of your system is fine."

    property bool showDetails: false
    readonly property string logPath: Wizard.lastLogPath
    property string logError: ""
    readonly property string detailsText: {
        const lines = [];
        if (!fatal && ev.module)
            lines.push("module: " + ev.module.id);
        if (ev.details)
            lines.push(ev.details);
        else if (ev.message)
            lines.push(ev.message);
        return lines.join("\n");
    }

    function escaped(t) {
        return String(t || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }
    function primary() {
        if (fatal)
            Wizard.retryInstall();
        else
            Wizard.retryModule();
    }
    function focusFirst() {
        tryAgain.forceActiveFocus();
    }
    function fillForm(v) {
        if (v.show_details !== undefined)
            showDetails = !!v.show_details;
        return "ok";
    }

    Column {
        width: page.width
        spacing: 20

        ArProgress {
            width: parent.width
            value: Wizard.percent
            barHeight: 8
            state_: "error"
            label: page.fatal ? "Paused" : "Paused on " + page.appName
            valueText: page.fatal ? Math.round(Wizard.percent) + "%" : Wizard.appsDone + " of " + Wizard.appsTotal + " apps"
        }

        ArBanner {
            width: parent.width
            kind: "error"
            title: page.fatal ? "The install stopped" : (page.ev.title || page.appName + " couldn’t be downloaded")
            text: page.escaped(page.fatal ? page.ev.message : (page.ev.message || "The download server didn’t answer.") + " " + (page.ev.help || "Everything else is fine — " + page.appName + " is optional and you can add it later from the Software app."))
            actionText: page.detailsText === "" ? "" : (page.showDetails ? "Hide details" : "Show details")
            onAction: page.showDetails = !page.showDetails
        }

        Rectangle {
            visible: page.showDetails && page.detailsText !== ""
            width: parent.width
            height: details.implicitHeight + 2 * Theme.space3
            radius: Theme.radiusMd
            color: Theme.surfaceSunken
            Text {
                id: details
                x: Theme.space3
                y: Theme.space3
                width: parent.width - 2 * Theme.space3
                wrapMode: Text.WrapAnywhere
                textFormat: Text.PlainText
                color: Theme.inkMuted
                font.family: Theme.fontMono
                font.pixelSize: 12
                text: page.detailsText
            }
        }

        Row {
            spacing: Theme.space2
            ArButton {
                id: tryAgain
                variant: "primary"
                iconName: "refresh"
                text: "Try again"
                enabled: !Wizard.busy
                onClicked: page.primary()
            }
            ArButton {
                visible: !page.fatal
                variant: "secondary"
                text: "Skip " + page.appName
                enabled: !Wizard.busy
                onClicked: Wizard.skipModule()
            }
            // Back to the Summary with every answer kept, to pick another disk and so on
            // (when the engine allows it: can_change).
            ArButton {
                visible: page.fatal && !!page.ev.can_change
                variant: "secondary"
                iconName: "chevron-left"
                text: "Change your answers"
                enabled: !Wizard.busy
                onClicked: Wizard.leaveFailure()
            }
            ArButton {
                visible: page.fatal
                variant: "ghost"
                iconName: "download"
                text: "Save log to USB"
                onClicked: Wizard.saveLog((path, err) => page.logError = err)
            }
        }

        ArBanner {
            visible: page.logPath !== "" || page.logError !== ""
            width: parent.width
            kind: page.logError !== "" ? "error" : "success"
            text: page.escaped(page.logError !== "" ? page.logError : (Wizard.lastLogMessage || "Saved the log to " + page.logPath + "."))
        }
    }
}
