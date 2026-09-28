pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Effects
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Services.Pam

// The lock screen (design LockScreen): the wallpaper blurred under frost, the clock, your
// avatar and name, and the password field, whose ring is amber while you type, red when the
// password is wrong and green when it's accepted. Battery, Wi-Fi and power sit bottom-right.
// Uses the ext-session-lock protocol (WlSessionLock), so the compositor keeps the session
// locked even if the shell crashes, and PAM (pam/arctic-lock) to check the password.
// The live USB has no password, so locking is off there.
Scope {
    id: root
    property string password: ''
    property string state: 'idle'      // idle, checking, error, success
    property string message: ''
    property string wallpaper: ''
    property int attempt: 0
    property bool powerOpen: false
    property bool reveal: false
    // locked: the lock is requested (true as soon as lock() runs). secure: the compositor has
    // confirmed every screen is covered — only then is the session really locked.
    readonly property bool locked: lock.locked
    readonly property bool secure: lock.secure
    // Set by lock() and the unlock: in Fedora's Quickshell snapshot lock.locked doesn't announce
    // its changes (bindings on it keep the old value), so the Caps Lock check and
    // NotificationService's count (toasts hide, the "N notifications" line) follow this.
    property bool showing: false

    function lock() {
        if (Session.live) {
            Quickshell.execDetached(['notify-send', '-a', 'Arctic Linux', '-i', 'system-lock-screen',
                'Locking is off in the live session',
                'The live user has no password. Install Arctic Linux to lock your screen.']);
            return;
        }
        password = '';
        state = 'idle';
        message = '';
        powerOpen = false;
        reveal = false;
        wallpaperView.reload();
        // The password is typed in the first layout (the installer's), whatever was active.
        if (KeyboardService.multiple && KeyboardService.index !== 0) KeyboardService.set(0, true);
        lock.locked = true;
        root.showing = true;
        NotificationService.locked = true;
    }
    function submit() {
        if (state === 'checking' || state === 'success') return;
        if (!password.length) { state = 'error'; message = 'Type your password to unlock.'; return; }
        state = 'checking';
        message = '';
        pam.start();
    }

    PamContext {
        id: pam
        configDirectory: Quickshell.shellDir + '/pam'
        config: 'arctic-lock'
        onPamMessage: {
            if (responseRequired) respond(root.password);
            else if (messageIsError) root.message = message;
        }
        onCompleted: result => {
            if (result === PamResult.Success) {
                root.state = 'success';
                root.message = '';
                unlockTimer.restart();
            } else {
                root.state = 'error';
                root.attempt++;
                root.message = result === PamResult.MaxTries ? 'Too many tries. Wait a moment, then try again.'
                                                             : 'That password didn’t work. Try again.';
                root.password = '';
            }
        }
        onError: error => {
            root.state = 'error';
            root.message = 'Your password couldn’t be checked (' + PamError.toString(error) + '). Try again.';
            root.password = '';
        }
    }
    // Stream 5: the fingerprint reader unlocks too (pam/arctic-lock-fingerprint: pam_fprintd), next
    // to the password, when a finger is saved (fprintd-list), the lid is open (logind) and
    // shell.json doesn't say "lock_fingerprint": false (Settings > Users and sign-in). It listens
    // again each time its 30 s wait runs out; three fingers that don't match, or a reader that
    // keeps failing, stop it until the next lock.
    property bool fingerprint: false    // listening now
    property int fingerMisses: 0
    property int fingerFailures: 0
    property double fingerStarted: 0
    function listenForFinger() {
        if (!lock.secure || state === 'success' || fingerPam.active || fingerMisses >= 3 || fingerFailures >= 3
                || Session.settings.lock_fingerprint === false || fingerCheck.running || lidCheck.running)
            return;
        fingerCheck.running = true;
    }
    onSecureChanged: {
        fingerMisses = 0;
        fingerFailures = 0;
        if (secure) {
            listenForFinger();
            Quickshell.execDetached(['arctic-hook', 'lock']);     // your lock hooks, once every screen is covered
        }
    }
    onLockedChanged: if (!locked && fingerPam.active) fingerPam.abort()
    Process {
        id: fingerCheck
        command: ['fprintd-list', Session.user]
        stdout: StdioCollector {
            onStreamFinished: if (/^\s*- #\d+:/m.test(text)) lidCheck.running = true
        }
    }
    Process {
        id: lidCheck
        command: ['gdbus', 'call', '--system', '--dest', 'org.freedesktop.login1', '--object-path', '/org/freedesktop/login1',
            '--method', 'org.freedesktop.DBus.Properties.Get', 'org.freedesktop.login1.Manager', 'LidClosed']
        stdout: StdioCollector {
            onStreamFinished: {
                if (/true/.test(text) || !lock.secure || root.state === 'success')
                    return;
                root.fingerStarted = Date.now();
                fingerPam.start();
            }
        }
    }
    Timer { id: fingerAgain; interval: 1000; onTriggered: root.listenForFinger() }
    PamContext {
        id: fingerPam
        configDirectory: Quickshell.shellDir + '/pam'
        config: 'arctic-lock-fingerprint'
        onActiveChanged: root.fingerprint = active
        onPamMessage: {
            if (responseRequired) {
                respond('');
            } else if (messageIsError && /match/i.test(message)) {
                root.fingerMisses++;
                root.message = 'That finger didn’t match. Try again, or type your password.';
            }
        }
        onCompleted: result => {
            if (result === PamResult.Success) {
                if (!lock.locked || root.state === 'success')
                    return;
                root.state = 'success';
                root.message = '';
                unlockTimer.restart();
                return;
            }
            if (result === PamResult.MaxTries)
                root.fingerMisses = 3;
            else if (Date.now() - root.fingerStarted < 5000)
                root.fingerFailures++;
            if (lock.locked)
                fingerAgain.restart();
        }
        onError: {
            root.fingerFailures++;
            if (lock.locked)
                fingerAgain.restart();
        }
    }

    // Let the green "accepted" ring show for a moment before the screen unlocks.
    Timer {
        id: unlockTimer
        interval: 180
        onTriggered: {
            lock.locked = false;
            root.showing = false;
            NotificationService.locked = false;
            root.password = '';
            root.state = 'idle';
            Quickshell.execDetached(['arctic-hook', 'unlock']);
        }
    }

    // arctic-wallpaper records the picture it drew; fall back to the theme's lock wallpaper.
    FileView {
        id: wallpaperView
        path: Session.arcticCache + '/wallpaper-current'
        printErrors: false
        onLoaded: root.wallpaper = text().trim()
        onLoadFailed: root.wallpaper = ''
    }
    readonly property string fallbackWallpaper: '/usr/share/backgrounds/arctic/' + Theme.tokens.lockWallpaper + '.svg'

    SystemClock { id: clock; precision: SystemClock.Minutes; enabled: lock.locked }

    // Caps Lock, from the keyboard LEDs (sysfs has no change events, so it is read twice a
    // second, only while locked).
    property bool capsLock: false
    Timer {
        interval: 500
        repeat: true
        running: root.showing
        onRunningChanged: if (!running) root.capsLock = false
        onTriggered: if (!capsQuery.running) capsQuery.running = true
    }
    Process {
        id: capsQuery
        command: ['sh', '-c', 'cat /sys/class/leds/*::capslock/brightness 2>/dev/null']
        stdout: StdioCollector { onStreamFinished: root.capsLock = /^[1-9]/m.test(text) }
    }

    WlSessionLock {
        id: lock
        WlSessionLockSurface {
            id: surface
            color: Theme.ground

            Image {
                id: backdrop
                anchors.fill: parent
                source: root.wallpaper ? 'file://' + root.wallpaper : 'file://' + root.fallbackWallpaper
                fillMode: Image.PreserveAspectCrop
                sourceSize: Qt.size(surface.width, surface.height)
                asynchronous: true
                visible: false
            }
            MultiEffect {
                anchors.fill: parent
                source: backdrop
                visible: backdrop.status === Image.Ready
                blurEnabled: true
                blur: 1.0
                blurMax: 48
                saturation: 0.1
            }
            Rectangle { anchors.fill: parent; color: Theme.frost }

            // Clock
            ColumnLayout {
                anchors.horizontalCenter: parent.horizontalCenter
                y: 96
                spacing: 0
                Text {
                    Layout.alignment: Qt.AlignHCenter
                    text: Qt.formatDateTime(clock.date, 'hh:mm')
                    color: Theme.ink
                    font.family: Theme.fontSans
                    font.pixelSize: 72
                    font.weight: Font.Medium
                    font.letterSpacing: -2.16
                    font.features: { 'tnum': 1 }
                }
                Text {
                    Layout.alignment: Qt.AlignHCenter
                    text: Qt.formatDateTime(clock.date, 'dddd, d MMMM')
                    color: Theme.inkMuted
                    font.family: Theme.fontSans
                    font.pixelSize: 17
                    font.weight: Font.Medium
                }
                // How many arrived while locked: the count only, never what they say.
                Text {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.topMargin: Theme.space2
                    visible: NotificationService.lockedCount > 0
                    text: NotificationService.lockedCount + (NotificationService.lockedCount === 1 ? ' notification' : ' notifications')
                    color: Theme.inkMuted
                    font.family: Theme.fontSans
                    font.pixelSize: 13
                    font.features: { 'tnum': 1 }
                }
            }

            // Avatar, name, password
            ColumnLayout {
                id: card
                anchors.horizontalCenter: parent.horizontalCenter
                y: 300
                width: 340
                spacing: 14
                Rectangle {
                    Layout.alignment: Qt.AlignHCenter
                    implicitWidth: 56
                    implicitHeight: 56
                    radius: 28
                    color: Theme.warmSoft
                    Text {
                        anchors.centerIn: parent
                        visible: face.status !== Image.Ready
                        text: (Session.fullName || Session.user || '?').charAt(0).toUpperCase()
                        color: Theme.warm
                        font.family: Theme.fontSans
                        font.pixelSize: 22
                        font.weight: Font.DemiBold
                    }
                    RoundedImage {
                        id: face
                        anchors.fill: parent
                        radius: 28
                        source: Session.hasFace ? 'file://' + Session.home + '/.face' : ''
                        sourceSize: Qt.size(112, 112)
                        visible: face.status === Image.Ready
                    }
                }
                Text {
                    Layout.alignment: Qt.AlignHCenter
                    text: Session.fullName || Session.user
                    color: Theme.ink
                    font.family: Theme.fontSans
                    font.pixelSize: 17
                    font.weight: Font.DemiBold
                }
                Rectangle {
                    // Frost behind the field, as in the design.
                    Layout.fillWidth: true
                    implicitHeight: field.implicitHeight
                    radius: Theme.radiusMd
                    color: Theme.frost
                    ArcticField {
                        id: field
                        anchors.fill: parent
                        size: 'lg'
                        iconName: 'lock'
                        echoMode: root.reveal ? TextInput.Normal : TextInput.Password
                        passwordCharacter: '•'
                        placeholderText: 'Password'
                        rightPadding: Theme.space3 + 18 + Theme.space2 + (layoutChip.visible ? layoutChip.width + Theme.space2 : 0)
                        inputMethodHints: Qt.ImhSensitiveData | Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase
                        enabled: root.state !== 'checking' && root.state !== 'success'
                        error: root.state === 'error'
                        success: root.state === 'success'
                        focusLook: root.state === 'idle' || root.state === 'checking'
                        text: root.password
                        focus: true
                        onTextEdited: { root.password = text; if (root.state === 'error') root.state = 'idle'; }
                        onAccepted: root.submit()
                        Keys.onEscapePressed: { root.password = ''; root.state = 'idle'; root.message = ''; }
                        Component.onCompleted: forceActiveFocus()
                        Connections {
                            target: lock
                            function onLockedChanged() { if (lock.locked) field.forceActiveFocus(); }
                        }
                        // The keyboard layout the password is typed in (with more than one): a
                        // click switches to the next.
                        Rectangle {
                            id: layoutChip
                            visible: KeyboardService.multiple
                            anchors.right: parent.right
                            anchors.rightMargin: Theme.space3 + 18 + Theme.space2
                            anchors.verticalCenter: parent.verticalCenter
                            implicitWidth: layoutText.implicitWidth + 2 * Theme.space2
                            implicitHeight: 22
                            radius: Theme.radiusSm
                            color: Theme.surfaceSunken
                            border.width: 1
                            border.color: Theme.line
                            Accessible.role: Accessible.Button
                            Accessible.name: 'Keyboard layout: ' + KeyboardService.name
                            Text {
                                id: layoutText
                                anchors.centerIn: parent
                                text: KeyboardService.shortName
                                color: Theme.inkMuted
                                font.family: Theme.fontSans
                                font.pixelSize: 12
                                font.weight: Font.DemiBold
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: { KeyboardService.next(); field.forceActiveFocus(); }
                            }
                        }
                        // Show / hide the password (design Input: eye at the end of password fields).
                        Icon {
                            anchors.right: parent.right
                            anchors.rightMargin: Theme.space3
                            anchors.verticalCenter: parent.verticalCenter
                            name: root.reveal ? 'eye-off' : 'eye'
                            size: 18
                            color: Theme.inkMuted
                            MouseArea {
                                anchors.fill: parent
                                anchors.margins: -8
                                cursorShape: Qt.PointingHandCursor
                                onClicked: { root.reveal = !root.reveal; field.forceActiveFocus(); }
                            }
                        }
                    }
                }
                Text {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.maximumWidth: 340
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    readonly property bool caps: root.capsLock && !root.message && root.state === 'idle'
                    text: root.message || (root.state === 'checking' ? 'Checking…' : root.state === 'success' ? 'Unlocked'
                        : caps ? 'Caps Lock is on'
                        : root.fingerprint ? 'Locked. Touch the fingerprint reader or type your password.' : 'Locked')
                    color: root.state === 'error' ? Theme.error : root.state === 'success' ? Theme.success : caps ? Theme.warning : Theme.inkMuted
                    font.family: Theme.fontSans
                    font.pixelSize: 12
                    font.weight: Font.Medium
                }
                // What is playing (only while a player exists): title — artist, play/pause, next.
                RowLayout {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.fillWidth: false
                    Layout.maximumWidth: 340
                    Layout.topMargin: Theme.space2
                    visible: MediaService.available
                    spacing: Theme.space1
                    Icon { name: 'music'; size: 16; color: Theme.inkMuted }
                    Text {
                        Layout.maximumWidth: 250
                        elide: Text.ElideRight
                        text: MediaService.title + (MediaService.artist ? ' — ' + MediaService.artist : '')
                        color: Theme.inkMuted
                        font.family: Theme.fontSans
                        font.pixelSize: 12
                    }
                    ArcticButton {
                        variant: 'ghost'; size: 'sm'; iconOnly: true
                        iconName: MediaService.playing ? 'pause' : 'play'
                        label: MediaService.playing ? 'Pause' : 'Play'
                        enabled: MediaService.available && MediaService.active.canTogglePlaying
                        onClicked: { MediaService.playPause(); field.forceActiveFocus(); }
                    }
                    ArcticButton {
                        variant: 'ghost'; size: 'sm'; iconOnly: true
                        iconName: 'skip-forward'
                        label: 'Next'
                        enabled: MediaService.available && MediaService.active.canGoNext
                        onClicked: { MediaService.next(); field.forceActiveFocus(); }
                    }
                }
            }

            // Battery, Wi-Fi and power, bottom-right.
            Rectangle {
                id: statusPill
                readonly property bool hasBattery: BatteryService.present
                anchors { right: parent.right; bottom: parent.bottom; rightMargin: 16; bottomMargin: 14 }
                implicitWidth: statusRow.implicitWidth + 2 * Theme.space1
                implicitHeight: Theme.controlMd + 2
                radius: height / 2
                color: Theme.frost
                border.width: 1
                border.color: Theme.line
                RowLayout {
                    id: statusRow
                    anchors.centerIn: parent
                    spacing: Theme.space1
                    RowLayout {
                        Layout.leftMargin: Theme.space2
                        Layout.rightMargin: Theme.space2
                        spacing: 6
                        visible: statusPill.hasBattery || NetworkService.available
                        Icon {
                            visible: statusPill.hasBattery
                            name: BatteryService.charging ? 'battery-charging' : 'battery'
                            size: 16
                            color: Theme.ink
                        }
                        Text {
                            visible: statusPill.hasBattery
                            text: statusPill.hasBattery ? BatteryService.percent + '%' : ''
                            color: Theme.ink
                            font.family: Theme.fontSans
                            font.pixelSize: 12
                            font.weight: Font.Medium
                            font.features: { 'tnum': 1 }
                        }
                        Icon { visible: NetworkService.available; name: NetworkService.iconName; size: 16; color: Theme.ink }
                    }
                    ArcticButton {
                        visible: powerRow.visible
                        variant: 'ghost'; iconOnly: true; iconName: 'sleep'; label: 'Suspend'
                        onClicked: Quickshell.execDetached(['systemctl', 'suspend'])
                    }
                    ArcticButton {
                        visible: powerRow.visible
                        variant: 'ghost'; iconOnly: true; iconName: 'restart'; label: 'Restart'
                        onClicked: Quickshell.execDetached(['systemctl', 'reboot'])
                    }
                    ArcticButton {
                        id: powerRow
                        readonly property bool expanded: root.powerOpen
                        visible: expanded
                        variant: 'ghost'; iconOnly: true; iconName: 'power'; label: 'Shut down'
                        onClicked: Quickshell.execDetached(['systemctl', 'poweroff'])
                    }
                    ArcticButton {
                        visible: !powerRow.expanded
                        variant: 'ghost'; iconOnly: true; iconName: 'power'; label: 'Power'
                        onClicked: root.powerOpen = true
                    }
                }
            }
        }
    }
}
