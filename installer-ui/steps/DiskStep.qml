// Step 5 — How should we install? (INSTALL_STEPS[4]). Disk dropdown, choice cards
// "Erase disk and install" (Recommended, pre-selected) and "Install alongside
// {OS}" (only when the engine says there is room), and the erase warning.
import QtQuick
import ".."
import "../components"

StepPage {
    id: page
    stepId: "disk"
    title: "How should we install?"
    lede: ""
    note: "Nothing is erased until you confirm on the Summary step."
    measure: 600
    valid: diskPath !== "" && (mode === "erase" || (mode === "alongside" && canAlongside))
    helpText: "Erase disk and install gives Arctic Linux the whole disk and encrypts it. Install alongside keeps the system you have and uses free space next to it; you pick which one to start each time. Nothing is written until you confirm on the Summary step."

    readonly property var disks: (Wizard.step.options && Wizard.step.options.disks || []).filter(d => !d.install_media)
    property string diskPath: (Wizard.step.data && Wizard.step.data.disk) || (disks.length ? disks[0].path : "")
    property string mode: (Wizard.step.data && Wizard.step.data.mode) || "erase"
    readonly property var disk: {
        for (const d of disks)
            if (d.path === diskPath)
                return d;
        return null;
    }
    readonly property bool canAlongside: !!(disk && disk.alongside_possible)
    readonly property string otherOs: disk && disk.existing_os && disk.existing_os.length ? disk.existing_os[0] : ""

    onDiskChanged: if (!canAlongside && mode === "alongside") mode = "erase"

    function label(d) {
        return d.model + " · " + d.size_label;
    }
    function commit(done) {
        Wizard.selectedDiskLabel = disk ? label(disk) : "";
        Wizard.alongsideOs = otherOs;
        Wizard.saveStep("disk", {
            disk: diskPath,
            mode: mode
        }, done);
    }
    function focusFirst() {
        (mode === "alongside" && canAlongside ? alongsideCard : eraseCard).forceActiveFocus();
    }
    function fillForm(v) {
        if (v.disk !== undefined)
            diskPath = v.disk;
        if (v.mode !== undefined)
            mode = v.mode;
        return "ok";
    }

    Column {
        width: page.width
        spacing: Theme.space3

        ArSelect {
            width: parent.width
            label: "Install on"
            iconName: "disk"
            model: page.disks.map(d => ({
                        value: d.path,
                        label: page.label(d)
                    }))
            value: page.diskPath
            error: Wizard.fieldErrors.disk || ""
            onActivated: v => page.diskPath = v
        }

        Item {
            width: 1
            height: Theme.space1
        }

        ArCard {
            id: eraseCard
            width: parent.width
            choice: true
            radio: true
            selected: page.mode === "erase"
            title: "Erase disk and install"
            tag: "Recommended"
            tagKind: "accent"
            desc: "Replaces everything on this disk with Arctic Linux. Your files are encrypted, so they stay private if the laptop is lost."
            onClicked: page.mode = "erase"
            Keys.onDownPressed: event => {
                if (alongsideCard.visible) {
                    page.mode = "alongside";
                    alongsideCard.forceActiveFocus(Qt.TabFocusReason);
                } else {
                    event.accepted = false;
                }
            }
        }

        ArCard {
            id: alongsideCard
            visible: page.canAlongside
            width: parent.width
            choice: true
            radio: true
            selected: page.mode === "alongside"
            title: "Install alongside " + (page.otherOs || "the other system")
            desc: "Keeps " + (page.otherOs || "the other system") + ". You choose which one to start each time. " + (page.disk && page.disk.alongside_label ? page.disk.alongside_label + "." : "")
            onClicked: page.mode = "alongside"
            Keys.onUpPressed: event => {
                page.mode = "erase";
                eraseCard.forceActiveFocus(Qt.TabFocusReason);
            }
        }

        // warning banner: margin-top 4px on top of the 12px gap
        Item {
            visible: page.mode === "erase" && page.disk !== null
            width: parent.width
            height: eraseBanner.implicitHeight + Theme.space1
            ArBanner {
                id: eraseBanner
                y: Theme.space1
                width: parent.width
                kind: "warning"
                strong: true
                text: "<b>All files on this disk will be erased.</b> Back up anything you want to keep first."
            }
        }

        ArBanner {
            visible: page.disks.length === 0
            width: parent.width
            kind: "error"
            title: "No disk to install on"
            text: "Arctic Linux needs a disk of at least 40 GB that isn’t the USB stick you started from."
        }
    }
}
