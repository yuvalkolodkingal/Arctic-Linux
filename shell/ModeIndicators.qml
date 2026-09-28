pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts

// Left of the clock: privacy pills while something listens or watches ("Mic", "Camera",
// "Sharing": warning-soft with an icon and a word, never colour alone), then the modes that
// are on (the registry's toggles with an indicator: night light, keep awake, VPN, a muted
// microphone) as quiet icons. Clicking a mode turns it back; clicking "Mic" opens the sound menu.
// Resting the pointer on them for a moment shows the other modes too, dimmed, on the far left
// (so nothing that was there moves); clicking one turns it on.
RowLayout {
    id: row
    required property var bar
    property bool revealed: false
    spacing: Theme.space1

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
        model: row.revealed ? ToggleRegistry.toggles.filter(t => t.available && t.indicator && !t.indicatorShown && t.kind === 'switch') : []
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
            text: modelData.word
            textColor: Theme.warning
            textWeight: Font.DemiBold
            interactive: modelData.key === 'mic'
            tooltip: modelData.what + PrivacyService.names(modelData.apps)
            onClicked: row.bar.shell.togglePanel('sound', row.bar.screen, undefined, undefined)
            onHoverChanged: h => h ? row.bar.hint(pill, tooltip) : row.bar.unhint(pill)
        }
    }
    Repeater {
        model: ToggleRegistry.toggles.filter(t => t.available && t.indicatorShown)
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
