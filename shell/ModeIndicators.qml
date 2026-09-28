pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts

// Left of the clock: privacy pills while something listens or watches ("Mic", "Camera",
// "Sharing": warning-soft with an icon and a word, never colour alone), then the modes that
// are on (the registry's toggles with an indicator: night light, keep awake, VPN, a muted
// microphone) as quiet icons. Clicking a mode turns it back; clicking "Mic" opens the sound menu.
RowLayout {
    id: row
    required property var bar
    spacing: Theme.space1

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
