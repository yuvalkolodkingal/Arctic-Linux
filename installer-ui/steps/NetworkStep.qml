// Step 3 — Connect to the internet (INSTALL_STEPS[2]). Next stays disabled
// until the engine reports online. A wired connection skips this step (engine).
pragma ComponentBehavior: Bound
import QtQuick
import ".."
import "../components"

StepPage {
    id: page
    stepId: "network"
    title: "Connect to the internet"
    lede: "Pick a Wi-Fi network or plug in a cable."
    measure: 600
    valid: online
    helpText: "Arctic Linux downloads the apps you pick and the latest security updates while it installs. Pick your Wi-Fi network and type its password, or plug in a network cable. " + Engine.dictationDownloadNotice

    readonly property var opts: Wizard.step.options || {}
    property bool online: !!opts.online
    property bool wired: !!opts.wired
    property string ssid: opts.ssid || ""
    property var networks: []
    property bool scanning: false
    property bool scannedOnce: false
    property string pendingSsid: ""       // secured network waiting for a password
    property string connectingSsid: ""
    property string connectError: ""
    readonly property var rows: {
        const out = networks.slice().sort((a, b) => (b.connected - a.connected) || (b.signal - a.signal)).map(n => ({
                    kind: "wifi",
                    ssid: n.ssid,
                    signal: n.signal,
                    secure: n.secure,
                    connected: n.connected
                }));
        out.push({
            kind: "wired",
            ssid: "Wired",
            connected: wired
        });
        return out;
    }

    function signalWord(s) {
        return s >= 67 ? "strong signal" : s >= 34 ? "good signal" : "weak signal";
    }
    function scan() {
        if (scanning)
            return;
        scanning = true;
        Engine.call("ScanWifi", null, (res, err) => {
            scanning = false;
            scannedOnce = true;
            if (!err)
                networks = res.networks || [];
        });
    }
    function refreshState() {
        Engine.call("NetworkState", null, (res, err) => {
            if (err)
                return;
            online = !!res.online;
            wired = !!res.wired;
            ssid = res.ssid || "";
        });
    }
    function choose(row) {
        connectError = "";
        if (row.kind === "wired" || row.connected)
            return;
        if (row.secure) {
            pendingSsid = row.ssid;
            passwordField.text = "";
            passwordField.forceActiveFocus();
        } else {
            pendingSsid = "";
            connect(row.ssid, "");
        }
    }
    function connect(name, password) {
        connectingSsid = name;
        connectError = "";
        Engine.call("ConnectWifi", {
            ssid: name,
            password: password
        }, (res, err) => {
            connectingSsid = "";
            if (err) {
                connectError = err.code === "auth" ? (err.message || "Wrong password. Check it and try again.") : (err.message || "Couldn't connect. Try again.");
                if (err.code === "auth") {
                    pendingSsid = name;
                    passwordField.forceActiveFocus();
                    passwordField.input.selectAll();
                }
                return;
            }
            pendingSsid = "";
            refreshState();
            scan();
        });
    }
    function focusFirst() {
        list.mouseUsed = true;
        list.forceActiveFocus();
    }
    function fillForm(v) {
        if (v.ssid !== undefined) {
            const row = rows.find(r => r.ssid === v.ssid);
            if (!row)
                return "no such network";
            if (row.secure && v.password !== undefined) {
                pendingSsid = row.ssid;
                passwordField.text = v.password;
                connect(row.ssid, v.password);
            } else {
                choose(row);
            }
        }
        return "ok";
    }

    Component.onCompleted: {
        scan();
        refreshState();
    }
    Timer {
        interval: 8000
        running: true
        repeat: true
        onTriggered: {
            page.scan();
            page.refreshState();
        }
    }

    Column {
        width: page.width
        spacing: Theme.space4

        ArBanner {
            id: networkInfo
            width: parent.width
            kind: "info"
            title: "Why do I need the internet?"
            text: "Arctic Linux downloads the apps you pick and the latest security updates while it installs, so you start up to date. " + Engine.dictationDownloadNotice
        }

        // A Wi-Fi card that works only once its driver is installed (Broadcom wl): say how
        // to get online meanwhile.
        ArBanner {
            id: hint
            visible: (page.opts.driver_hint || "") !== ""
            width: parent.width
            kind: "warning"
            title: "Your Wi-Fi needs a driver"
            text: String(page.opts.driver_hint || "").replace(/&/g, "&amp;").replace(/</g, "&lt;")
        }

        ArList {
            id: list
            width: parent.width
            // The disclosure wraps with the window width; reserve its actual height.
            height: Math.min(implicitHeight, Math.max(120, page.availableHeight - networkInfo.height - Theme.space4 - (hint.visible ? hint.height + Theme.space4 : 0)))
            accessibleName: "Networks"
            model: page.rows
            // Arrows only move; Space or a click connects.
            onActivated: index => page.choose(page.rows[index])
            delegate: ArListRow {
                id: netRow
                required property var modelData
                required property int index
                readonly property bool isWired: modelData.kind === "wired"
                readonly property bool busy: page.connectingSsid === modelData.ssid
                width: ListView.view.width
                first: index === 0
                enabled: !isWired || modelData.connected
                iconName: isWired ? "ethernet" : "wifi"
                title: modelData.ssid
                desc: isWired ? (modelData.connected ? "Connected" : "No cable plugged in") : busy ? "Connecting…" : modelData.connected ? "Connected · " + page.signalWord(modelData.signal) : modelData.secure ? "Secured" : "Open network"
                metaIcon: (!isWired && modelData.secure && !modelData.connected) ? "lock" : ""
                selected: !!modelData.connected
                showFocus: ListView.isCurrentItem && list.showFocus
                onClicked: list.clickRow(index)
                Row {
                    visible: !!netRow.modelData.connected
                    spacing: Theme.space1
                    Icon {
                        name: "check-circle"
                        size: 18
                        color: Theme.success
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    ArText {
                        text: "Connected"
                        size: 13
                        lh: 18
                        weight: Font.DemiBold
                        color: Theme.success
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }
        }

        // Password for the secured network that was picked.
        Row {
            visible: page.pendingSsid !== ""
            width: parent.width
            spacing: Theme.space3
            ArInput {
                id: passwordField
                width: parent.width - connectButton.width - parent.spacing
                label: "Password for " + page.pendingSsid
                password: true
                error: page.connectError
                onAccepted: if (text !== "") page.connect(page.pendingSsid, text)
                onEdited: page.connectError = ""
            }
            ArButton {
                id: connectButton
                y: 18 + Theme.space1
                text: page.connectingSsid !== "" ? "Connecting…" : "Connect"
                enabled: passwordField.text !== "" && page.connectingSsid === ""
                onClicked: page.connect(page.pendingSsid, passwordField.text)
            }
        }

        ArBanner {
            visible: page.connectError !== "" && page.pendingSsid === ""
            width: parent.width
            kind: "error"
            text: page.connectError
        }

        ArText {
            visible: page.scannedOnce && page.networks.length === 0 && !page.wired
            width: parent.width
            wrapMode: Text.WordWrap
            text: "No Wi-Fi networks found. Plug in a network cable, or move closer to your router."
            color: Theme.inkMuted
        }
    }
}
