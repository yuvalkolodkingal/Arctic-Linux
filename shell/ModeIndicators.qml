pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts

// Left of the clock: privacy pills while something listens or watches ("Mic", "Camera",
// "Sharing": warning-soft with an icon and a word, never colour alone), "Recording 01:23" while
// arctic-record records (error-soft: an alert, not a mode; a click stops it), then the modes that
// are on (the registry's toggles with an indicator: night light, keep awake, VPN, a muted
// microphone) as quiet icons. Clicking a mode turns it back; clicking "Mic" opens the sound menu.
// Resting the pointer on them for a moment shows the other modes too, dimmed, on the far left
// (so nothing that was there moves); clicking one turns it on.
// urgentOnly: just the privacy pills and the recording (PrivacyPeek, while the bar is hidden).
GridLayout {
    id: row
    required property var bar
    property bool vertical: false
    columns: vertical ? 1 : -1
    rows: vertical ? -1 : 1
    property bool urgentOnly: false
    property bool revealed: false
    // Something records, listens or watches right now.
    readonly property bool urgent: pills.count > 0 || RecordService.recording
    columnSpacing: Theme.space1
    rowSpacing: Theme.space1

    // The recording's length: mm:ss, or h:mm:ss past the hour.
    function elapsedText(seconds) {
        const two = n => (n < 10 ? '0' : '') + n;
        const h = Math.floor(seconds / 3600), m = Math.floor(seconds % 3600 / 60), s = seconds % 60;
        return h > 0 ? h + ':' + two(m) + ':' + two(s) : two(m) + ':' + two(s);
    }

    HoverHandler {
        id: hover
        onHoveredChanged: {
            if (hovered) { hideTimer.stop(); revealTimer.restart(); }
            else { revealTimer.stop(); hideTimer.restart(); }
        }
    }
    Timer { id: revealTimer; interval: 300; onTriggered: row.revealed = true }
    Timer { id: hideTimer; interval: 600; onTriggered: row.revealed = false }

    Repeater {
        model: row.revealed && !row.urgentOnly ? ToggleRegistry.toggles.filter(t => t.available && t.indicator && !t.indicatorShown && t.kind === 'switch') : []
        BarItem {
            id: other
            required property var modelData
            iconName: !modelData.active && modelData.iconOff !== '' ? modelData.iconOff : modelData.icon
            iconColor: Theme.inkSubtle
            tooltip: modelData.indicatorOffText
            onClicked: modelData.toggle()
            onHoverChanged: h => h ? row.bar.hint(other, tooltip) : row.bar.unhint(other)
        }
    }
    Repeater {
        id: pills
        model: [
            { key: 'mic', icon: 'mic', word: 'Mic', apps: PrivacyService.mic, what: 'Microphone in use by ' },
            { key: 'camera', icon: 'camera', word: 'Camera', apps: PrivacyService.camera, what: 'Camera in use by ' },
            { key: 'sharing', icon: 'screen-share', word: 'Sharing', apps: PrivacyService.sharing, what: 'Sharing ' }
        ].filter(p => p.apps.length > 0)
        BarItem {
            id: pill
            required property var modelData
            accentFill: false
            color: Theme.warningSoft
            iconName: modelData.icon
            iconColor: Theme.warning
            text: row.vertical ? '' : modelData.word
            textColor: Theme.warning
            textWeight: Font.DemiBold
            interactive: modelData.key === 'mic'
            tooltip: modelData.what + PrivacyService.names(modelData.apps)
            onClicked: row.bar.shell.togglePanel('sound', row.bar.screen, undefined, undefined)
            onHoverChanged: h => h ? row.bar.hint(pill, tooltip) : row.bar.unhint(pill)
        }
    }
    BarItem {
        id: recording
        visible: RecordService.recording
        color: Theme.errorSoft
        iconName: 'record'
        iconColor: Theme.error
        text: row.vertical ? '' : 'Recording ' + row.elapsedText(RecordService.elapsed)
        textColor: Theme.error
        textWeight: Font.DemiBold
        tooltip: 'Recording ' + row.elapsedText(RecordService.elapsed) + ' · click to stop  (Super + Alt + R)'
        onClicked: RecordService.stop()
        onHoverChanged: h => h ? row.bar.hint(recording, tooltip) : row.bar.unhint(recording)
    }
    Repeater {
        model: row.urgentOnly ? [] : ToggleRegistry.toggles.filter(t => t.available && t.indicatorShown)
        BarItem {
            id: mode
            required property var modelData
            iconName: !modelData.active && modelData.iconOff !== '' ? modelData.iconOff : modelData.icon
            iconColor: Theme.inkMuted
            tooltip: modelData.indicatorText
            onClicked: modelData.toggle()
            onHoverChanged: h => h ? row.bar.hint(mode, tooltip) : row.bar.unhint(mode)
        }
    }
}
