// Printers and scanners: the CUPS queues (lpstat), your default printer (lpoptions -d, kept in
// ~/.cups/lpoptions), cancelling your jobs, and driverless printers CUPS finds on the network
// (IPP Everywhere over DNS-SD; any app's print dialog can use them without setting anything
// up). Adding and administering queues is system-config-printer's job (cups-pk-helper asks for
// the password); scanning opens Document Scanner (simple-scan with sane-airscan).
pragma ComponentBehavior: Bound
import QtQuick
import ".."
import "../components"

Page {
    id: page
    title: "Printers and scanners"
    lede: "Most printers and scanners made in the last ten years work without drivers, over USB or your network."
    property var info: ({ available: true, running: true, printers: [], network: [], canAdd: false, scan: false })
    property bool loading: true
    function load() {
        Backend.call(["printers"], r => {
            page.loading = false;
            if (r.ok)
                page.info = r;
        });
    }
    function stateText(p) {
        const parts = [];
        parts.push(p.state === "printing" ? "Printing" : p.state === "paused" ? "Paused" + (p.reason && p.reason !== "Paused" ? ": " + p.reason : "") : "Ready");
        if (p.jobs > 0)
            parts.push(p.jobs === 1 ? "1 job waiting" : p.jobs + " jobs waiting");
        if (p.location)
            parts.push(p.location);
        return parts.join(" · ");
    }
    onShown: load()

    ArBanner {
        visible: !page.loading && page.info.available === false
        width: parent.width
        kind: "warning"
        title: "Printing isn’t installed"
        text: "Install it with <b>sudo dnf install cups cups-filters system-config-printer</b>."
    }
    ArBanner {
        visible: page.info.available === true && page.info.running === false
        width: parent.width
        kind: "warning"
        title: "The printing service isn’t running"
        text: "Start it with <b>sudo systemctl enable --now cups.socket</b>."
    }

    Group {
        visible: page.info.available === true
        title: "Printers"
        SettingRow {
            searchKey: "printers.list"
            visible: (page.info.printers || []).length === 0
            title: page.loading ? "Looking for printers…" : "No printers set up"
            desc: page.loading ? "" : "A printer on your network or plugged in by USB usually shows up in apps’ print dialogs by itself. Add it here to keep it for good."
            resettable: false
        }
        Repeater {
            model: page.info.printers || []
            SettingRow {
                id: printerRow
                required property var modelData
                title: modelData.description || modelData.name
                desc: page.stateText(modelData)
                resettable: false
                Row {
                    spacing: Theme.space2
                    ArTag {
                        visible: printerRow.modelData.default === true
                        text: "Default"
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    ArButton {
                        visible: printerRow.modelData.jobs > 0
                        text: "Cancel jobs"
                        variant: "ghost"
                        size: "sm"
                        gapColor: Theme.surfaceRaised
                        onClicked: Backend.call(["printer-cancel", printerRow.modelData.name], r => {
                            if (r.ok) {
                                page.info = r;
                                Backend.notify("success", "Your print jobs were cancelled", false);
                            }
                        })
                    }
                    ArButton {
                        visible: printerRow.modelData.default !== true
                        text: "Make default"
                        variant: "secondary"
                        size: "sm"
                        gapColor: Theme.surfaceRaised
                        onClicked: Backend.call(["printer-default", printerRow.modelData.name], r => {
                            if (r.ok) {
                                page.info = r;
                                Backend.notify("success", "Default printer changed", false);
                            }
                        })
                    }
                }
            }
        }
        SettingRow {
            visible: page.info.canAdd === true
            searchKey: "printers.add"
            title: "Add or change printers"
            desc: "Set up a printer, share one, or change its paper and quality. It asks for your password."
            resettable: false
            ArButton {
                text: "Open printer settings"
                iconName: "external"
                gapColor: Theme.surfaceRaised
                onClicked: Backend.launch(["system-config-printer"])
            }
        }
    }

    Group {
        visible: (page.info.network || []).length > 0
        title: "On your network"
        desc: "Printers that work without drivers. Any app’s print dialog can use them as they are."
        Repeater {
            model: page.info.network || []
            SettingRow {
                id: netRow
                required property var modelData
                title: String(modelData.name).replace(/_/g, " ")
                resettable: false
                ArButton {
                    visible: netRow.modelData.default !== true
                    text: "Make default"
                    variant: "secondary"
                    size: "sm"
                    gapColor: Theme.surfaceRaised
                    onClicked: Backend.call(["printer-default", netRow.modelData.name], r => {
                        if (r.ok) {
                            page.info = r;
                            Backend.notify("success", "Default printer changed", false);
                        }
                    })
                }
            }
        }
    }

    Group {
        visible: page.info.scan === true
        title: "Scanners"
        SettingRow {
            searchKey: "printers.scan"
            title: "Scan a document or photo"
            desc: "Document Scanner finds scanners on USB and on your network, including the scanner in most printers."
            resettable: false
            ArButton {
                text: "Open Document Scanner"
                iconName: "external"
                gapColor: Theme.surfaceRaised
                onClicked: Backend.launch(["simple-scan"])
            }
        }
    }
}
