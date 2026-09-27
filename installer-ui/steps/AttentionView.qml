// Step 11 — One app needs attention / Something went wrong (INSTALL_STEPS[10]).
// Replaces the Install page while the engine waits: an optional app failed
// (Try again / Skip {App}) or a core step failed (Try again / Save log to USB).
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
    caption: fatal ? "Don’t remove the USB stick yet." : "Your system is installed. Only optional apps are affected."
    helpText: fatal ? "A part of the system couldn’t be installed. Try again first. If it keeps failing, save the log to the USB stick and share it with us when you ask for help." : "An optional app couldn’t be downloaded. Try again, or skip it — you can add it later from the Software app. The rest of your system is fine."

    property bool showDetails: false
    readonly property string logPath: Wizard.lastLogPath
    property string logError: ""

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
            title: page.fatal ? "The install stopped" : page.appName + " couldn’t be downloaded"
            text: page.fatal ? (page.ev.message || "") : (page.ev.message || "The download server didn’t answer.") + " Everything else is fine — " + page.appName + " is optional and you can add it later from the Software app."
            actionText: page.fatal ? "" : (page.showDetails ? "Hide details" : "Show details")
            onAction: page.showDetails = !page.showDetails
        }

        Rectangle {
            visible: page.showDetails && !page.fatal
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
                color: Theme.inkMuted
                font.family: Theme.fontMono
                font.pixelSize: 12
                text: "module: " + (page.ev.module ? page.ev.module.id : "") + "\nmessage: " + (page.ev.message || "") + "\noptional: " + (page.ev.optional ? "yes" : "no")
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
            ArButton {
                visible: page.fatal
                variant: "secondary"
                iconName: "download"
                text: "Save log to USB"
                onClicked: Wizard.saveLog((path, err) => page.logError = err)
            }
        }

        ArBanner {
            visible: page.logPath !== "" || page.logError !== ""
            width: parent.width
            kind: page.logError !== "" ? "error" : "success"
            text: page.logError !== "" ? page.logError : "Saved the log to " + page.logPath + "."
        }
    }
}
