// Arctic Linux — SDDM login screen (Qt 6, Theme-API 2.0).
//
// Layout and behaviour follow the design system's LoginScreen component and
// the Login() mockup builder: clock block, a frosted 360 px card with the user
// picker and the password field, the session menu bottom-left and the keyboard
// layout + power cluster bottom-right. Polar night by default.
pragma ComponentBehavior: Bound

import QtQuick
import "."
import "components"

Rectangle {
    id: root

    width: 1920
    height: 1080
    color: Theme.ground

    LayoutMirroring.enabled: Qt.locale().textDirection === Qt.RightToLeft
    LayoutMirroring.childrenInherit: true

    // ---- configuration (theme.conf, overridable in theme.conf.user) ----------
    readonly property bool reduceMotion: config.boolValue("reduceMotion")
    readonly property string timeFormat: config.stringValue("timeFormat") || "HH:mm"
    readonly property string dateFormat: config.stringValue("dateFormat") || "dddd, d MMMM"
    readonly property string fallbackLayout: config.stringValue("keyboardLayout")
    // Not connected to the daemon: `sddm-greeter-qt6 --test-mode`. Power
    // actions are then shown (for previews) and a login attempt is answered
    // with a failure, so the error state can be previewed.
    readonly property bool testMode: sddm.hostName === ""

    // ---- state -----------------------------------------------------------------
    property int userIndex: userModel.lastIndex >= 0 ? userModel.lastIndex : 0
    property string userName: ""
    property string userRealName: ""
    property int sessionIndex: sessionModel.lastIndex >= 0 ? sessionModel.lastIndex : 0
    property bool busy: false
    property bool failed: false
    property string message: ""
    property bool capsLock: keyboard.capsLock
    property bool keyboardNav: true     // show focus rings; false after a pointer press
    readonly property bool manyUsers: userModel.count > 1
    readonly property bool typedUser: userModel.count === 0

    Component.onCompleted: {
        Theme.dark = config.stringValue("colorScheme") !== "winter"
        Theme.reduceMotion = reduceMotion
    }

    // ---- fonts (bundled; Figtree + JetBrains Mono, SIL OFL) -------------------
    FontLoader { source: "fonts/Figtree-Regular.ttf" }
    FontLoader { source: "fonts/Figtree-Medium.ttf" }
    FontLoader { source: "fonts/Figtree-SemiBold.ttf" }
    FontLoader { source: "fonts/Figtree-Bold.ttf" }
    FontLoader { source: "fonts/JetBrainsMono-Regular.ttf" }
    FontLoader { source: "fonts/JetBrainsMono-Bold.ttf" }

    // ---- actions -----------------------------------------------------------------
    function login() {
        if (busy)
            return
        var user = typedUser ? userField.text.trim() : userName
        if (user === "") {
            userField.input.forceActiveFocus()
            return
        }
        busy = true
        failed = false
        message = ""
        sddm.login(user, passwordField.text, sessionIndex)
        if (testMode)
            testReply.start()
    }

    function selectUser(i) {
        if (i < 0 || i >= userModel.count)
            return
        userIndex = i
        passwordField.text = ""
        failed = false
        message = ""
    }

    // Tab order: password, users, log in, session, suspend, restart, shut down.
    function focusChain() {
        var chain = []
        if (typedUser) chain.push(userField.input)
        chain.push(passwordField.input)
        if (manyUsers) chain.push(userList)
        chain.push(loginButton, sessionSelect)
        if (layoutButton.visible && layoutButton.switchable) chain.push(layoutButton)
        ;[suspendButton, rebootButton, powerButton].forEach(function (b) { if (b.visible) chain.push(b) })
        return chain
    }
    function moveFocus(from, step) {
        var chain = focusChain()
        var i = chain.indexOf(from)
        var next = chain[(i + step + chain.length) % chain.length]
        keyboardNav = true
        next.forceActiveFocus(step > 0 ? Qt.TabFocusReason : Qt.BacktabFocusReason)
    }

    function loginFailed() {
        busy = false
        failed = true
        passwordField.text = ""
        passwordField.input.forceActiveFocus()
        if (!reduceMotion)
            shake.restart()
    }

    Connections {
        target: sddm
        function onLoginFailed() { root.loginFailed() }
        function onLoginSucceeded() {
            root.busy = false
        }
        function onInformationMessage(message) {
            root.message = message
        }
    }
    Timer { id: testReply; interval: 450; onTriggered: root.loginFailed() }

    // pointer presses hide the keyboard focus ring (passive, never blocks input)
    Item {
        anchors.fill: parent
        z: 1000
        PointHandler { onActiveChanged: if (active) root.keyboardNav = false }
    }

    // ---- wallpaper ------------------------------------------------------------------
    // Probe the public system copy. SDDM never reads a user's home or runs the publisher.
    // File URL query revisions bypass Qt's cache after the broker's atomic generation swap.
    Image {
        id: sharedProbe
        visible: false
        asynchronous: true
        cache: false
        sourceSize: Qt.size(root.width, root.height)
        property int revision: 0
        source: "file:///var/lib/arctic-login-wallpaper/current/wallpaper.png?revision=" + revision
        onStatusChanged: {
            if (status === Image.Ready) wallpaper.source = source;
            else if (status === Image.Error) wallpaper.source = config.background || "background.png";
        }
    }
    Timer {
        interval: 5000
        running: true
        repeat: true
        onTriggered: sharedProbe.revision++
    }
    Image {
        id: wallpaper
        anchors.fill: parent
        source: config.background || "background.png"
        fillMode: Image.PreserveAspectCrop
        asynchronous: false
        cache: false
        smooth: true
        // a broken `background=` in theme.conf.user falls back to the bundled image
        onStatusChanged: if (status === Image.Error && source.toString().indexOf("background.png") < 0) source = "background.png"
    }

    // ---- clock ---------------------------------------------------------------------
    // Photos can be bright or dark behind the clock. Keep its small date readable
    // on a solid themed surface while retaining the same clock position and styling.
    Rectangle {
        x: clock.x - Theme.space5
        y: clock.y - Theme.space3
        width: clock.width + 2 * Theme.space5
        height: clock.height + 2 * Theme.space3
        color: Theme.surface
        border.color: Theme.line
        border.width: 1
        radius: Theme.radiusLg
        Accessible.ignored: true
    }
    Column {
        id: clock
        property date now: new Date()
        anchors.horizontalCenter: parent.horizontalCenter
        y: Math.round(root.height * 0.12)

        Timer {
            interval: 1000
            running: true
            repeat: true
            onTriggered: clock.now = new Date()
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: Qt.formatTime(clock.now, root.timeFormat)
            color: Theme.ink
            font.family: Theme.fontSans
            font.pixelSize: 72
            font.weight: Font.Medium
            font.letterSpacing: -72 * 0.03
            font.features: { "tnum": 1 }
            lineHeight: 76
            lineHeightMode: Text.FixedHeight
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: Qt.formatDate(clock.now, root.dateFormat)
            color: Theme.inkMuted
            font.family: Theme.fontSans
            font.pixelSize: 17
            font.weight: Font.Medium
            lineHeight: 24
            lineHeightMode: Text.FixedHeight
        }
    }

    // ---- login card --------------------------------------------------------------------
    FrostPanel {
        id: card
        visible: primaryScreen
        backdrop: wallpaper
        shadow: true
        borderColor: Theme.line
        radius: Theme.radiusXl
        width: 360
        height: content.implicitHeight + 2 * Theme.space6

        property real shakeOffset: 0
        x: Math.round((root.width - width) / 2) + shakeOffset
        y: Math.max(clock.y + clock.height + Theme.space12, Math.round(root.height * 0.433))

        SequentialAnimation {
            id: shake
            // "the card shakes 6px twice" (never under reduced motion)
            NumberAnimation { target: card; property: "shakeOffset"; to: -6; duration: 50; easing.type: Easing.OutSine }
            NumberAnimation { target: card; property: "shakeOffset"; to: 6; duration: 90; easing.type: Easing.InOutSine }
            NumberAnimation { target: card; property: "shakeOffset"; to: -6; duration: 90; easing.type: Easing.InOutSine }
            NumberAnimation { target: card; property: "shakeOffset"; to: 6; duration: 90; easing.type: Easing.InOutSine }
            NumberAnimation { target: card; property: "shakeOffset"; to: 0; duration: 50; easing.type: Easing.InSine }
        }

        Column {
            id: content
            x: Theme.space6
            y: Theme.space6
            width: card.width - 2 * Theme.space6
            spacing: Theme.space4

            // -- user picker: selected user 64 px with the amber ring, others 40 px
            ListView {
                id: userList
                visible: !root.typedUser
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.min(contentWidth, parent.width)
                height: 64 + 6 + 24
                orientation: ListView.Horizontal
                spacing: 18
                interactive: contentWidth > width
                clip: contentWidth > width
                model: userModel
                currentIndex: root.userIndex
                highlightFollowsCurrentItem: false
                highlightRangeMode: ListView.ApplyRange
                preferredHighlightBegin: width / 2 - 32
                preferredHighlightEnd: width / 2 + 32
                boundsBehavior: Flickable.StopAtBounds

                Accessible.role: Accessible.List
                Accessible.name: qsTr("Users")

                Keys.onLeftPressed: root.selectUser(Math.max(0, root.userIndex - (LayoutMirroring.enabled ? -1 : 1)))
                Keys.onRightPressed: root.selectUser(Math.min(userModel.count - 1, root.userIndex + (LayoutMirroring.enabled ? -1 : 1)))
                Keys.onReturnPressed: passwordField.input.forceActiveFocus()
                Keys.onEnterPressed: passwordField.input.forceActiveFocus()
                Keys.onSpacePressed: passwordField.input.forceActiveFocus()
                Keys.onTabPressed: root.moveFocus(userList, 1)
                Keys.onBacktabPressed: root.moveFocus(userList, -1)

                delegate: Item {
                    id: userItem
                    required property int index
                    required property string name
                    required property string realName
                    required property string icon
                    readonly property bool current: index === root.userIndex
                    readonly property string display: realName !== "" ? realName : name

                    width: Math.max(avatar.width, Math.min(nameText.implicitWidth, 120))
                    height: userList.height

                    Binding { target: root; property: "userName"; value: userItem.name; when: userItem.current }
                    Binding { target: root; property: "userRealName"; value: userItem.display; when: userItem.current }

                    Column {
                        anchors.bottom: parent.bottom
                        anchors.horizontalCenter: parent.horizontalCenter
                        spacing: 6
                        Avatar {
                            id: avatar
                            anchors.horizontalCenter: parent.horizontalCenter
                            name: userItem.display
                            face: userItem.icon
                            guest: userItem.name === "guest" || userItem.name === "liveuser"
                            selected: userItem.current
                            showFocus: userItem.current && userList.activeFocus && root.keyboardNav
                        }
                        Text {
                            id: nameText
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: Math.min(implicitWidth, 120)
                            horizontalAlignment: Text.AlignHCenter
                            text: userItem.display
                            elide: Text.ElideRight
                            color: userItem.current ? Theme.ink : Theme.inkMuted
                            font.family: Theme.fontSans
                            font.pixelSize: userItem.current ? 16 : 13
                            font.weight: userItem.current ? Font.DemiBold : Font.Medium
                            lineHeight: userItem.current ? 24 : 18
                            lineHeightMode: Text.FixedHeight
                        }
                    }
                    opacity: current ? 1 : 0.9
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            root.selectUser(userItem.index)
                            passwordField.input.forceActiveFocus()
                        }
                    }
                    Accessible.role: Accessible.ListItem
                    Accessible.name: display
                    Accessible.selected: current
                }
            }

            // -- no user list (e.g. hidden users): type the user name
            TextField {
                id: userField
                visible: root.typedUser
                width: parent.width
                icon: "user"
                placeholder: qsTr("User name")
                onTabbed: (backwards) => root.moveFocus(userField.input, backwards ? -1 : 1)
                onAccepted: passwordField.input.forceActiveFocus()
            }

            // -- password + the one primary action
            Row {
                width: parent.width
                spacing: Theme.space2

                TextField {
                    id: passwordField
                    width: parent.width - loginButton.width - parent.spacing
                    icon: "lock"
                    password: true
                    placeholder: qsTr("Password")
                    error: root.failed
                    enabled: !root.busy
                    focus: true
                    onAccepted: root.login()
                    onTextChanged: if (text.length > 0) { root.failed = false; root.message = "" }

                    onTabbed: (backwards) => root.moveFocus(passwordField.input, backwards ? -1 : 1)
                    onCapsLockChanged: root.capsLock = capsLock
                    Accessible.name: qsTr("Password for %1").arg(root.userRealName)
                }

                IconButton {
                    id: loginButton
                    variant: "primary"
                    size: Theme.controlLg
                    icon: "arrow-right"
                    label: qsTr("Log in")
                    showFocus: root.keyboardNav
                    onClicked: root.login()
                    Keys.onTabPressed: root.moveFocus(loginButton, 1)
                    Keys.onBacktabPressed: root.moveFocus(loginButton, -1)
                }
            }

            // -- hint line / error / PAM message
            Item {
                width: parent.width
                height: 20

                Row {
                    id: hint
                    visible: !root.failed && root.message === ""
                    anchors.centerIn: parent
                    spacing: 6
                    Kbd { text: "Caps Lock"; anchors.verticalCenter: parent.verticalCenter }
                    Icon {
                        visible: root.capsLock
                        name: "alert"
                        size: 14
                        color: Theme.warning
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.capsLock ? qsTr("is on") : qsTr("is off")
                        color: root.capsLock ? Theme.warning : Theme.inkSubtle
                        font.family: Theme.fontSans
                        font.pixelSize: 12
                        font.weight: Font.Medium
                    }
                    Text {
                        visible: root.manyUsers
                        anchors.verticalCenter: parent.verticalCenter
                        text: "\u00b7"
                        color: Theme.inkSubtle
                        font.family: Theme.fontSans
                        font.pixelSize: 12
                        font.weight: Font.Medium
                    }
                    Kbd { visible: root.manyUsers; text: "Tab"; anchors.verticalCenter: parent.verticalCenter }
                    Text {
                        visible: root.manyUsers
                        anchors.verticalCenter: parent.verticalCenter
                        text: qsTr("switch user")
                        color: Theme.inkSubtle
                        font.family: Theme.fontSans
                        font.pixelSize: 12
                        font.weight: Font.Medium
                    }
                }

                Row {
                    visible: root.failed || root.message !== ""
                    anchors.centerIn: parent
                    spacing: Theme.space1
                    Icon {
                        visible: root.failed
                        name: "alert"
                        size: 16
                        color: Theme.error
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        width: Math.min(implicitWidth, content.width - 24)
                        elide: Text.ElideRight
                        text: root.failed ? qsTr("That password didn't work") : root.message
                        color: root.failed ? Theme.error : Theme.inkMuted
                        font.family: Theme.fontSans
                        font.pixelSize: 13
                        lineHeight: 18
                        lineHeightMode: Text.FixedHeight
                        Accessible.role: Accessible.AlertMessage
                    }
                }
            }
        }
    }

    // ---- bottom left: session ------------------------------------------------------------
    SessionSelect {
        id: sessionSelect
        visible: primaryScreen
        anchors.left: parent.left
        anchors.leftMargin: Theme.space4
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 14
        model: sessionModel
        currentIndex: root.sessionIndex
        showFocus: root.keyboardNav
        onPicked: (i) => root.sessionIndex = i
        Keys.onTabPressed: root.moveFocus(sessionSelect, 1)
        Keys.onBacktabPressed: root.moveFocus(sessionSelect, -1)
    }

    // ---- bottom right: keyboard layout + power ---------------------------------------------
    FrostPanel {
        id: cluster
        visible: primaryScreen
        backdrop: wallpaper
        borderColor: Theme.line
        radius: height / 2
        width: clusterRow.implicitWidth + 2 * Theme.space1 + 2
        height: Theme.controlMd + 2
        x: root.width - width - Theme.space4
        y: root.height - height - 14

        Row {
            id: clusterRow
            anchors.centerIn: parent
            spacing: Theme.space1

            Item {
                id: layoutButton
                readonly property var layouts: keyboard.layouts
                readonly property bool switchable: layouts.length > 1
                readonly property string label: {
                    if (layouts.length > 0 && keyboard.currentLayout >= 0 && keyboard.currentLayout < layouts.length)
                        return layouts[keyboard.currentLayout].shortName.toUpperCase()
                    return root.fallbackLayout.toUpperCase()
                }
                visible: label !== ""
                width: layoutRow.implicitWidth + 2 * Theme.space2
                height: Theme.controlMd
                Accessible.role: Accessible.Button
                Accessible.name: qsTr("Keyboard layout: %1").arg(label)
                Row {
                    id: layoutRow
                    anchors.centerIn: parent
                    spacing: 6
                    Icon { name: "keyboard"; size: 16; color: Theme.ink; anchors.verticalCenter: parent.verticalCenter }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: layoutButton.label
                        color: Theme.ink
                        font.family: Theme.fontSans
                        font.pixelSize: 12
                        font.weight: Font.Medium
                    }
                }
                FocusRing { radius: Theme.radiusMd; shown: layoutButton.activeFocus && root.keyboardNav }
                function next() {
                    if (switchable)
                        keyboard.currentLayout = (keyboard.currentLayout + 1) % layouts.length
                }
                Keys.onReturnPressed: next()
                Keys.onSpacePressed: next()
                Keys.onTabPressed: root.moveFocus(layoutButton, 1)
                Keys.onBacktabPressed: root.moveFocus(layoutButton, -1)
                MouseArea {
                    anchors.fill: parent
                    enabled: layoutButton.switchable
                    cursorShape: Qt.PointingHandCursor
                    onClicked: layoutButton.next()
                }
            }

            IconButton {
                id: suspendButton
                visible: sddm.canSuspend || root.testMode
                icon: "sleep"
                label: qsTr("Suspend")
                showFocus: root.keyboardNav
                onClicked: sddm.suspend()
                Keys.onTabPressed: root.moveFocus(suspendButton, 1)
                Keys.onBacktabPressed: root.moveFocus(suspendButton, -1)
            }
            IconButton {
                id: rebootButton
                visible: sddm.canReboot || root.testMode
                icon: "restart"
                label: qsTr("Restart")
                showFocus: root.keyboardNav
                onClicked: sddm.reboot()
                Keys.onTabPressed: root.moveFocus(rebootButton, 1)
                Keys.onBacktabPressed: root.moveFocus(rebootButton, -1)
            }
            IconButton {
                id: powerButton
                visible: sddm.canPowerOff || root.testMode
                icon: "power"
                label: qsTr("Shut down")
                showFocus: root.keyboardNav
                onClicked: sddm.powerOff()
                Keys.onTabPressed: root.moveFocus(powerButton, 1)
                Keys.onBacktabPressed: root.moveFocus(powerButton, -1)
            }
        }
    }

    // Focus the password field once the window is up (SDDM activates the
    // primary screen's window).
    Timer {
        interval: 0
        running: primaryScreen
        onTriggered: (root.typedUser ? userField.input : passwordField.input).forceActiveFocus()
    }
}
