// Step 10 — Installing Arctic Linux (INSTALL_STEPS[9]). Progress with the
// engine's status line and time left, four sub-steps, a shortcuts tip. No Back.
pragma ComponentBehavior: Bound
import QtQuick
import ".."
import "../components"

StepPage {
    id: page
    stepId: "install"
    title: "Installing Arctic Linux"
    lede: "You can leave this running. Keep the computer plugged in."
    measure: 560
    showBack: false
    showNext: false
    caption: "Don’t remove the USB stick yet."
    helpText: "The install runs by itself and takes about 10 minutes. If an optional app can’t be downloaded, you can try again or skip it and add it later from the Software app."

    readonly property var defaultSubsteps: [
        {
            id: "disk",
            label: "Preparing the disk",
            state: "active"
        },
        {
            id: "system",
            label: "Copying Arctic Linux",
            state: "todo"
        },
        {
            id: "apps",
            label: "Installing your apps",
            state: "todo"
        },
        {
            id: "finish",
            label: "Setting up your account",
            state: "todo"
        }
    ]
    readonly property var subs: Wizard.substeps.length ? Wizard.substeps : defaultSubsteps

    function etaText(s) {
        if (s < 0)
            return "";
        if (s < 60)
            return "Less than a minute left";
        const m = Math.ceil(s / 60);
        return "About " + m + " min left";
    }
    // The engine's label; the active apps sub-step already reads "Installing your apps · 3 of 9".
    function subLabel(s) {
        return s.label || "";
    }

    Column {
        width: page.width
        spacing: 22

        ArProgress {
            width: parent.width
            value: Wizard.percent
            barHeight: 8
            label: Wizard.status
            valueText: page.etaText(Wizard.etaSeconds)
        }

        Column {
            spacing: 10
            Accessible.role: Accessible.List
            Accessible.name: "Install steps"
            Repeater {
                model: page.subs
                Row {
                    id: sub
                    required property var modelData
                    spacing: 10
                    Accessible.role: Accessible.ListItem
                    Accessible.name: page.subLabel(modelData) + (modelData.state === "done" ? ", done" : modelData.state === "active" ? ", in progress" : "")
                    Icon {
                        name: sub.modelData.state === "done" ? "check-circle" : sub.modelData.state === "active" ? "refresh" : "clock"
                        size: 20
                        color: sub.modelData.state === "done" ? Theme.success : sub.modelData.state === "active" ? Theme.accentText : Theme.inkMuted
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    ArText {
                        text: page.subLabel(sub.modelData)
                        size: 15
                        lh: 22
                        weight: sub.modelData.state === "active" ? Font.DemiBold : Font.Normal
                        color: sub.modelData.state === "todo" ? Theme.inkMuted : Theme.ink
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }
        }

        ArCard {
            width: parent.width
            iconName: "keyboard"
            title: "While you wait"
            desc: "Super + Space opens the launcher. Super + Enter opens a terminal. Super + arrows move between windows."
        }
    }
}
