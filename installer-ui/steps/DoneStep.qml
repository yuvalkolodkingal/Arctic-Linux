// Step 12 — Arctic Linux is ready (INSTALL_STEPS[11]). Aurora band, the USB
// card, Restart now (primary) and Keep trying (ghost: stay in the live session).
// With drivers: a line for each, and with Secure Boot on, the steps of the blue
// "Perform MOK management" screen and the one-time code to type there.
pragma ComponentBehavior: Bound
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
    readonly property var opts: Wizard.step.options || {}
    readonly property var drivers: (Wizard.doneInfo && Wizard.doneInfo.drivers) || opts.drivers || []
    readonly property var secureBoot: (Wizard.doneInfo && Wizard.doneInfo.secure_boot) || opts.secure_boot || null

    function primary() {
        rebootError = "";
        Wizard.reboot(err => page.rebootError = err);
    }
    function secondary() {
        Qt.quit();
    }

    // Scrolls when the driver and Secure Boot cards don't fit above the footer.
    fade: doneColumn.height + 8 > page.availableHeight + 4

    Flickable {
        id: doneFlick
        width: page.width + 8
        x: -4
        y: -4
        height: Math.min(doneColumn.height + 8, page.availableHeight + 4)
        contentHeight: doneColumn.height + (page.fade ? 48 : 8) // room above the footer's fade
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        interactive: contentHeight > height
        Accessible.role: Accessible.Pane
        Accessible.name: "Arctic Linux is ready"
        // Keyboard: Tab reaches the page when it scrolls; arrows and Page Up/Down, Home/End move it.
        activeFocusOnTab: interactive
        function scrollBy(dy) {
            contentY = Math.max(0, Math.min(contentHeight - height, contentY + dy));
        }
        Keys.onPressed: event => {
            const step = height - 48;
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

        // Focus ring while the page has keyboard focus.
        Rectangle {
            visible: doneFlick.activeFocus
            parent: doneFlick
            anchors.fill: parent
            color: "transparent"
            radius: Theme.radiusMd
            border.width: Theme.focusWidth
            border.color: Theme.focus
            z: 10
        }

        Column {
            id: doneColumn
            x: 4
            y: 4
            width: page.width
            spacing: Theme.space4

            ArCard {
                width: parent.width
                iconName: "usb"
                title: "Remove the USB stick"
                desc: "Take it out now, then restart. Your computer will start Arctic Linux" + (Wizard.encryptionEnabled ? " and ask for your disk passphrase." : ".")
            }

            // Secure Boot: enroll the driver's signing key on the first restart.
            ArCard {
                id: mokCard
                visible: page.secureBoot !== null
                width: parent.width
                iconName: "shield-lock"
                iconColor: page.secureBoot && page.secureBoot.failed ? Theme.warning : Theme.inkMuted
                title: page.secureBoot ? page.secureBoot.title : ""
                desc: page.secureBoot ? page.secureBoot.intro : ""

                Item {
                    width: parent.width
                    height: Theme.space2
                }
                Repeater {
                    model: page.secureBoot ? page.secureBoot.steps : []
                    delegate: ArText {
                        required property var modelData
                        required property int index
                        width: mokCard.width - 2 * mokCard.pad - 24 - Theme.space3
                        text: (index + 1) + ". " + modelData
                        size: 14
                        lh: 20
                        wrapMode: Text.WordWrap
                        color: Theme.ink
                    }
                }
                // The code, large, so it can be copied onto paper or a phone before restarting.
                Row {
                    visible: page.secureBoot !== null && (page.secureBoot.code || "") !== ""
                    spacing: Theme.space3
                    topPadding: Theme.space2
                    bottomPadding: Theme.space1
                    ArText {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "One-time code"
                        size: 13
                        lh: 18
                        color: Theme.inkMuted
                    }
                    ArText {
                        text: page.secureBoot ? page.secureBoot.code || "" : ""
                        font.family: Theme.fontMono
                        size: 22
                        lh: 30
                        weight: Font.Bold
                        tracking: 0.12
                        Accessible.name: "One-time code " + (page.secureBoot && page.secureBoot.code ? page.secureBoot.code.split("").join(" ") : "")
                    }
                }
                ArText {
                    visible: page.secureBoot !== null && (page.secureBoot.note || "") !== ""
                    width: mokCard.width - 2 * mokCard.pad - 24 - Theme.space3
                    text: page.secureBoot ? page.secureBoot.note || "" : ""
                    size: 13
                    lh: 18
                    wrapMode: Text.WordWrap
                    color: Theme.inkMuted
                }
            }

            ArCard {
                visible: page.drivers.length > 0
                width: parent.width
                iconName: "cpu"
                title: page.drivers.length === 1 ? "Driver" : "Drivers"
                desc: page.drivers.map(d => d.text).join("\n")
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
}
