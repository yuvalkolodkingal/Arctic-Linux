// The installer window content (Installer01 README + bundle.js installer()):
// 232px rail (wordmark, steps, language, Help F1) | main: header (overline,
// title, lede — or the aurora hero on Welcome/Done), the step's one decision,
// footer with the reassurance note and Back/Next (44px).
// Keys: Enter = Next when valid, Alt+← = Back, F1 = help, Tab/Shift+Tab.
pragma ComponentBehavior: Bound
import QtQuick
import "components"
import "steps"

FocusScope {
    id: frame
    focus: true

    readonly property StepPage page: stepLoader.item as StepPage
    readonly property bool engineDown: !Engine.connected && !Engine.starting && Engine.failure !== ""
    readonly property string pageKey: Engine.connected && !Wizard.loading ? (Wizard.view === "step" ? Wizard.current : Wizard.view) : ""
    readonly property bool hero: page !== null && page.hero !== ""
    readonly property bool nextEnabled: page !== null && page.showNext && page.valid
    property string loadedKey: ""

    function goNext() {
        if (!page || !page.showNext || !page.valid || Wizard.busy)
            return;
        page.primary();
    }
    function goBack() {
        if (!page || !page.showBack || Wizard.railIndex === 0 || Wizard.busy)
            return;
        Wizard.back();
    }
    function openHelp() {
        help.open();
    }

    function componentFor(key) {
        switch (key) {
        case "welcome":
            return cWelcome;
        case "keyboard":
            return cKeyboard;
        case "network":
            return cNetwork;
        case "timezone":
            return cTimezone;
        case "disk":
            return cDisk;
        case "encryption":
            return cEncryption;
        case "account":
            return cAccount;
        case "apps":
            return cApps;
        case "summary":
            return cSummary;
        case "install":
            return cInstall;
        case "attention":
        case "failed":
            return cAttention;
        case "done":
            return cDone;
        }
        return null;
    }

    onPageKeyChanged: {
        const comp = componentFor(pageKey);
        const sameView = (pageKey === "attention" && loadedKey === "failed") || (pageKey === "failed" && loadedKey === "attention");
        if (sameView) {
            loadedKey = pageKey;
            return;
        }
        loadedKey = pageKey;
        stepLoader.sourceComponent = comp;
        if (comp) {
            enter.restart();
            Qt.callLater(() => {
                if (frame.page)
                    frame.page.focusFirst();
            });
        }
    }

    Keys.onReturnPressed: frame.goNext()
    Keys.onEnterPressed: frame.goNext()
    Shortcut {
        sequences: ["Alt+Left"]
        onActivated: frame.goBack()
    }
    Shortcut {
        sequences: ["F1"]
        onActivated: frame.openHelp()
    }

    Component { id: cWelcome; WelcomeStep {} }
    Component { id: cKeyboard; KeyboardStep {} }
    Component { id: cNetwork; NetworkStep {} }
    Component { id: cTimezone; TimezoneStep {} }
    Component { id: cDisk; DiskStep {} }
    Component { id: cEncryption; EncryptionStep {} }
    Component { id: cAccount; AccountStep {} }
    Component { id: cApps; AppsStep {} }
    Component { id: cSummary; SummaryStep {} }
    Component { id: cInstall; InstallStep {} }
    Component { id: cAttention; AttentionView {} }
    Component { id: cDone; DoneStep {} }

    // ---------------------------------------------------------------- rail
    Rectangle {
        id: rail
        width: Theme.railWidth
        height: parent.height
        color: Theme.surfaceSunken
        Accessible.role: Accessible.Pane
        Accessible.name: "Installation progress"

        Rectangle {
            anchors.right: parent.right
            width: 1
            height: parent.height
            color: Theme.line
        }

        Wordmark {
            id: wordmark
            x: Theme.space4 + Theme.space2
            y: Theme.space6
            size: 18
        }

        ArSteps {
            x: Theme.space4
            anchors.top: wordmark.bottom
            // 24px gap + the inline line box the HTML wordmark sits in (measured: 6px)
            anchors.topMargin: Theme.space6 + 6
            width: rail.width - 2 * Theme.space4
            names: Wizard.railNames
            current: Wizard.railIndex
            error: Wizard.railError
        }

        Column {
            x: Theme.space4 + Theme.space2
            anchors.bottom: parent.bottom
            anchors.bottomMargin: Theme.space6
            spacing: 6
            Row {
                spacing: 6
                Icon {
                    name: "language"
                    size: 16
                    color: Theme.inkMuted
                    anchors.verticalCenter: parent.verticalCenter
                }
                ArText {
                    text: Wizard.languageName
                    size: 12
                    lh: 16
                    weight: Font.Medium
                    color: Theme.inkMuted
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
            Row {
                spacing: 6
                Accessible.role: Accessible.Button
                Accessible.name: "Help (F1)"
                Icon {
                    name: "help"
                    size: 16
                    color: Theme.inkMuted
                    anchors.verticalCenter: parent.verticalCenter
                }
                ArText {
                    text: "Help"
                    size: 12
                    lh: 16
                    weight: Font.Medium
                    color: Theme.inkMuted
                    anchors.verticalCenter: parent.verticalCenter
                }
                ArKbd {
                    text: "F1"
                    anchors.verticalCenter: parent.verticalCenter
                }
                TapHandler {
                    onTapped: frame.openHelp()
                }
                HoverHandler {
                    cursorShape: Qt.PointingHandCursor
                }
            }
        }
    }

    // ---------------------------------------------------------------- main
    Item {
        id: main
        x: rail.width
        width: parent.width - rail.width
        height: parent.height
        clip: true

        Rectangle {
            anchors.fill: parent
            color: Theme.surface
        }

        AuroraBand {
            visible: frame.hero
            width: parent.width
            opacity: body.opacity
        }

        Item {
            id: body
            x: Theme.space10
            y: 36
            width: main.width - 2 * Theme.space10
            height: footer.y - y
            transform: Translate {
                id: slide
            }

            ParallelAnimation {
                id: enter
                NumberAnimation {
                    target: body
                    property: "opacity"
                    from: 0
                    to: 1
                    duration: Theme.fadeSlow
                    easing.type: Easing.BezierSpline
                    easing.bezierCurve: Theme.easeStandard
                }
                NumberAnimation {
                    target: slide
                    property: "y"
                    from: Theme.slideDistance
                    to: 0
                    duration: Theme.durationSlow
                    easing.type: Easing.BezierSpline
                    easing.bezierCurve: Theme.easeStandard
                }
            }

            // Header: overline + title + lede, or the hero on Welcome / Done.
            Column {
                id: header
                visible: frame.page !== null
                width: parent.width
                spacing: 0

                // hero
                Mark {
                    visible: frame.hero && frame.page.hero === "welcome"
                    size: 44
                }
                Icon {
                    visible: frame.hero && frame.page.hero === "done"
                    name: "check-circle"
                    size: 44
                    stroke: 1.5
                    color: Theme.success
                }
                // 10px margin + the inline-image baseline gap under the 44px mark
                // in the HTML mockup (measured: 5px)
                Item {
                    visible: frame.hero
                    width: 1
                    height: frame.page && frame.page.hero === "done" ? 9 : 16
                }

                // overline
                ArText {
                    visible: !frame.hero
                    text: frame.page ? (frame.page.overline !== "" ? frame.page.overline : "Step " + Math.min(Wizard.railIndex + 1, Wizard.railNames.length) + " of " + Wizard.railNames.length).toUpperCase() : ""
                    size: 11
                    lh: 16
                    weight: Font.DemiBold
                    tracking: 0.08
                    color: Theme.inkMuted
                }
                Item {
                    visible: !frame.hero
                    width: 1
                    height: 6
                }
                ArText {
                    width: parent.width
                    text: frame.page ? frame.page.title : ""
                    size: frame.hero ? 40 : 28
                    lh: frame.hero ? 48 : 36
                    weight: Font.DemiBold
                    tracking: frame.hero ? -0.02 : -0.01
                    wrapMode: Text.WordWrap
                    Accessible.role: Accessible.Heading
                }
                Item {
                    visible: frame.page !== null && frame.page.lede !== ""
                    width: 1
                    height: frame.hero ? 6 : 8
                }
                ArText {
                    visible: frame.page !== null && frame.page.lede !== ""
                    width: Math.min(parent.width, frame.page && frame.page.hero === "done" ? 520 : 560)
                    text: frame.page ? frame.page.lede : ""
                    size: 15
                    lh: 22
                    wrapMode: Text.WordWrap
                    color: Theme.inkMuted
                }
            }

            // No width/height on the Loader: a sized Loader would stretch the page.
            Loader {
                id: stepLoader
                y: header.height + Theme.space6
                onLoaded: {
                    const p = item as StepPage;
                    p.width = Qt.binding(() => Math.min(p.measure, body.width));
                    p.availableHeight = Qt.binding(() => body.height - stepLoader.y - (p.fade ? 8 : Theme.space4));
                }
            }

            // soft fade above the footer when the content scrolls (Welcome, Apps)
            Rectangle {
                visible: frame.page !== null && frame.page.fade
                anchors.bottom: parent.bottom
                x: -Theme.space10
                width: main.width
                height: 56
                z: 10
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.rgba(Theme.surface.r, Theme.surface.g, Theme.surface.b, 0) }
                    GradientStop { position: 1.0; color: Theme.surface }
                }
            }
        }

        // Engine not reachable / starting.
        Column {
            visible: frame.pageKey === ""
            anchors.centerIn: parent
            width: Math.min(460, parent.width - 80)
            spacing: Theme.space4
            ArText {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: frame.engineDown ? "The installer couldn’t start" : "Starting the installer…"
                size: frame.engineDown ? 20 : 15
                lh: frame.engineDown ? 28 : 22
                weight: frame.engineDown ? Font.DemiBold : Font.Normal
                color: frame.engineDown ? Theme.ink : Theme.inkMuted
            }
            ArText {
                visible: frame.engineDown
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: Engine.failure
                color: Theme.inkMuted
            }
            // What the bridge said last (e.g. "cannot connect to /run/arcticd.sock").
            Text {
                visible: frame.engineDown && text !== ""
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WrapAnywhere
                text: Engine.stderrTail.trim().split("\n").slice(-1)[0] || ""
                color: Theme.inkSubtle
                font.family: Theme.fontMono
                font.pixelSize: 12
            }
            ArButton {
                visible: frame.engineDown
                anchors.horizontalCenter: parent.horizontalCenter
                variant: "primary"
                size: "lg"
                iconName: "refresh"
                text: "Try again"
                onClicked: Engine.restart()
            }
        }

        // ------------------------------------------------------------ footer
        Rectangle {
            id: footer
            readonly property bool hasButtons: frame.page !== null && (frame.page.showNext || (frame.page.showBack && Wizard.railIndex > 0) || frame.page.secondaryLabel !== "")
            visible: frame.page !== null
            anchors.bottom: parent.bottom
            width: parent.width
            height: visible ? (hasButtons ? Theme.controlLg + 2 * Theme.space4 : 16 + 2 * Theme.space4) + 1 : 0
            color: Theme.surface

            Rectangle {
                width: parent.width
                height: 1
                color: Theme.line
            }

            Row {
                id: noteRow
                x: Theme.space10
                width: buttons.x - x - Theme.space3
                anchors.verticalCenter: parent.verticalCenter
                anchors.verticalCenterOffset: 0.5
                spacing: Theme.space1
                readonly property bool isError: Wizard.stepError !== ""
                Icon {
                    visible: noteRow.isError
                    name: "alert"
                    size: 16
                    color: Theme.error
                    anchors.verticalCenter: parent.verticalCenter
                }
                ArText {
                    width: parent.width - (noteRow.isError ? 20 : 0)
                    text: noteRow.isError ? Wizard.stepError : frame.page ? (frame.page.caption !== "" && !footer.hasButtons ? frame.page.caption : frame.page.note !== "" ? frame.page.note : Object.keys(Wizard.fieldErrors).length ? "Fix the highlighted field to continue." : "") : ""
                    size: noteRow.isError ? 13 : 12
                    lh: 16
                    weight: noteRow.isError ? Font.Normal : Font.Medium
                    color: noteRow.isError ? Theme.error : Theme.inkMuted
                    elide: Text.ElideRight
                    anchors.verticalCenter: parent.verticalCenter
                    Accessible.role: noteRow.isError ? Accessible.AlertMessage : Accessible.StaticText
                }
            }

            Row {
                id: buttons
                anchors.right: parent.right
                anchors.rightMargin: Theme.space10
                anchors.verticalCenter: parent.verticalCenter
                anchors.verticalCenterOffset: 0.5
                spacing: Theme.space3

                ArButton {
                    visible: frame.page !== null && frame.page.secondaryLabel !== ""
                    variant: "ghost"
                    size: "lg"
                    text: frame.page ? frame.page.secondaryLabel : ""
                    onClicked: frame.page.secondary()
                }
                ArButton {
                    id: backButton
                    visible: frame.page !== null && frame.page.showBack && Wizard.railIndex > 0
                    variant: "secondary"
                    size: "lg"
                    iconName: "chevron-left"
                    text: "Back"
                    Accessible.description: "Alt + Left"
                    onClicked: frame.goBack()
                }
                ArButton {
                    id: nextButton
                    visible: frame.page !== null && frame.page.showNext
                    variant: "primary"
                    size: "lg"
                    text: frame.page ? frame.page.nextLabel : ""
                    iconName: frame.page ? frame.page.nextIcon : ""
                    iconRight: frame.page && frame.page.nextLabel === "Next" ? "chevron-right" : ""
                    enabled: frame.nextEnabled
                    Accessible.description: "Enter"
                    onClicked: frame.goNext()
                }
            }
        }
    }

    // ---------------------------------------------------------------- help (F1)
    ArDialog {
        id: help
        title: frame.page && frame.page.title ? "Help: " + frame.page.title : "Help"
        body: frame.page ? frame.page.helpText : ""
        iconName: "help"
        tone: "info"

        Repeater {
            model: [["Enter", "Next, when everything is filled in"], ["Alt + ←", "Back to the previous step"], ["Tab", "Move between controls"], ["F1", "This help"], ["Esc", "Close this help"]]
            Row {
                id: shortcut
                required property var modelData
                spacing: Theme.space2
                ArKbd {
                    text: shortcut.modelData[0]
                    anchors.verticalCenter: parent.verticalCenter
                }
                ArText {
                    text: shortcut.modelData[1]
                    size: 13
                    lh: 18
                    color: Theme.inkMuted
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
        }

        buttons: [
            ArButton {
                variant: "primary"
                text: "Close"
                gapColor: Theme.surfaceRaised
                onClicked: help.close()
            }
        ]
    }
}
