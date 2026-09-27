// Step 12 — Arctic Linux is ready (INSTALL_STEPS[11]). Aurora band, the USB
// card, Restart now (primary) and Keep trying (ghost: stay in the live session).
import QtQuick
import ".."
import "../components"

StepPage {
    id: page
    stepId: "done"
    hero: "done"
    readonly property var info: Wizard.doneInfo || Wizard.step.data || {}
    readonly property int apps: info.apps_installed !== undefined ? info.apps_installed : Wizard.appsInstalled
    readonly property string firstName: info.first_name || ""
    title: "Arctic Linux is ready"
    lede: "Everything is installed, including " + apps + (apps === 1 ? " app" : " apps") + "." + (firstName !== "" ? " Welcome aboard, " + firstName + "." : "")
    measure: 520
    showBack: false
    nextLabel: "Restart now"
    nextIcon: "restart"
    secondaryLabel: "Keep trying"
    helpText: "Take the USB stick out and restart. Your computer will start Arctic Linux. Keep trying closes the installer so you can keep using Arctic Linux from the USB stick."

    property string rebootError: ""

    function primary() {
        rebootError = "";
        Wizard.reboot(err => page.rebootError = err);
    }
    function secondary() {
        Qt.quit();
    }

    Column {
        width: page.width
        spacing: Theme.space4

        ArCard {
            width: parent.width
            iconName: "usb"
            title: "Remove the USB stick"
            desc: "Take it out now, then restart. Your computer will start Arctic Linux" + (Wizard.encryptionEnabled ? " and ask for your disk passphrase." : ".")
        }

        // Restart refused or failed: say so, and how else to restart.
        ArBanner {
            visible: page.rebootError !== ""
            width: parent.width
            kind: "error"
            strong: true
            text: page.rebootError.replace(/&/g, "&amp;").replace(/</g, "&lt;") + " Choose Keep trying, then restart from the power button on the top bar."
        }

        ArBanner {
            visible: Wizard.deferredApps.length > 0
            width: parent.width
            kind: "info"
            text: Wizard.deferredApps.join(", ") + (Wizard.deferredApps.length === 1 ? " isn’t" : " aren’t") + " installed. You can add " + (Wizard.deferredApps.length === 1 ? "it" : "them") + " later from the Software app."
        }
    }
}
