pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell

// The media menu (bar media item, Super + Ctrl + M): cover, title, artist and album, a seek
// bar when the player can seek, previous / play-pause / next, the other players when there
// are several, and a row to bring the player's window forward. Space plays or pauses.
FocusScope {
    id: panel
    property var menu: null
    readonly property var p: MediaService.active
    readonly property bool canSeek: p !== null && p.canSeek && p.positionSupported && p.length > 0

    implicitWidth: 340
    implicitHeight: list.implicitHeight

    // MPRIS doesn't signal position changes while playing: ask once a second while shown.
    Timer {
        interval: 1000
        repeat: true
        running: panel.p !== null && panel.p.isPlaying && panel.canSeek
        onTriggered: panel.p.positionChanged()
    }
    Keys.onSpacePressed: MediaService.playPause()

    MenuList {
        id: list
        anchors.fill: parent
        focus: true

        RowLayout {
            Layout.fillWidth: true
            Layout.margins: Theme.space3
            spacing: Theme.space3
            Item {
                implicitWidth: 64
                implicitHeight: 64
                Rectangle {
                    anchors.fill: parent
                    radius: Theme.radiusMd
                    color: Theme.surfaceSunken
                    visible: art.status !== Image.Ready
                    Icon { anchors.centerIn: parent; name: 'music'; size: 28; color: Theme.inkMuted }
                }
                RoundedImage {
                    id: art
                    anchors.fill: parent
                    source: panel.p ? panel.p.trackArtUrl : ''
                    sourceSize: Qt.size(128, 128)
                    visible: status === Image.Ready
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Text {
                    Layout.fillWidth: true
                    text: MediaService.title || 'Nothing playing'
                    elide: Text.ElideRight
                    color: Theme.ink
                    font.family: Theme.fontSans
                    font.pixelSize: 15
                    font.weight: Font.DemiBold
                }
                Text {
                    Layout.fillWidth: true
                    visible: text !== ''
                    text: MediaService.artist
                    elide: Text.ElideRight
                    color: Theme.inkMuted
                    font.family: Theme.fontSans
                    font.pixelSize: 13
                }
                Text {
                    Layout.fillWidth: true
                    visible: text !== ''
                    text: panel.p ? panel.p.trackAlbum : ''
                    elide: Text.ElideRight
                    color: Theme.inkSubtle
                    font.family: Theme.fontSans
                    font.pixelSize: 12
                }
            }
        }
        // Seek (only when the player supports it).
        FocusScope {
            readonly property bool menuStop: true
            readonly property string label: 'Position'
            visible: panel.canSeek
            Layout.fillWidth: true
            Layout.leftMargin: Theme.space3
            Layout.rightMargin: Theme.space3
            implicitHeight: seekColumn.implicitHeight
            ColumnLayout {
                id: seekColumn
                anchors.fill: parent
                spacing: 0
                ArcticSlider {
                    id: seek
                    Layout.fillWidth: true
                    focus: true
                    from: 0
                    to: panel.p ? panel.p.length : 1
                    stepSize: 5
                    showFocus: parent.parent.activeFocus && MenuState.keyboardNav
                    accessibleName: 'Position'
                    valueText: panel.p ? MediaService.time(panel.p.position) : ''
                    Binding on value { value: panel.p ? panel.p.position : 0; when: !seek.pressed; restoreMode: Binding.RestoreNone }
                    onMoved: if (!pressed && panel.p) panel.p.position = value
                    onCommitted: v => { if (panel.p) panel.p.position = v; }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        text: panel.p ? MediaService.time(seek.value) : ''
                        color: Theme.inkSubtle
                        font.family: Theme.fontSans
                        font.pixelSize: 11
                        font.features: { 'tnum': 1 }
                    }
                    Item { Layout.fillWidth: true }
                    Text {
                        text: panel.p ? MediaService.time(panel.p.length) : ''
                        color: Theme.inkSubtle
                        font.family: Theme.fontSans
                        font.pixelSize: 11
                        font.features: { 'tnum': 1 }
                    }
                }
            }
        }
        // Previous · play/pause · next: 36px icon buttons; play/pause on a sunken circle.
        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: Theme.space1
            Layout.bottomMargin: Theme.space2
            spacing: Theme.space4
            Repeater {
                model: [
                    { key: 'previous', icon: 'skip-back', label: 'Previous', enabled: panel.p !== null && panel.p.canGoPrevious },
                    { key: 'play', icon: panel.p && panel.p.isPlaying ? 'pause' : 'play', label: panel.p && panel.p.isPlaying ? 'Pause' : 'Play',
                      enabled: panel.p !== null && panel.p.canTogglePlaying },
                    { key: 'next', icon: 'skip-forward', label: 'Next', enabled: panel.p !== null && panel.p.canGoNext }
                ]
                Rectangle {
                    id: control
                    required property var modelData
                    readonly property bool menuStop: true
                    readonly property string label: modelData.label
                    enabled: modelData.enabled
                    implicitWidth: 36
                    implicitHeight: 36
                    radius: 18
                    color: modelData.key === 'play' ? (controlMouse.containsMouse ? Theme.line : Theme.surfaceSunken)
                           : controlMouse.containsMouse ? Theme.surfaceSunken : 'transparent'
                    Accessible.role: Accessible.Button
                    Accessible.name: modelData.label
                    function press() {
                        if (modelData.key === 'previous') MediaService.previous();
                        else if (modelData.key === 'next') MediaService.next();
                        else MediaService.playPause();
                    }
                    Keys.onReturnPressed: press()
                    Keys.onEnterPressed: press()
                    Icon { anchors.centerIn: parent; name: control.modelData.icon; size: 20; color: control.enabled ? Theme.ink : Theme.inkDisabled }
                    FocusRing { targetRadius: 18; shown: control.activeFocus && MenuState.keyboardNav }
                    MouseArea {
                        id: controlMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: control.press()
                    }
                }
            }
        }
        MenuSection {
            visible: MediaService.players.length > 1
            text: 'Players'
        }
        Repeater {
            model: MediaService.players.length > 1 ? MediaService.players : []
            MenuRow {
                required property var modelData
                icon: modelData.isPlaying ? 'play' : 'music'
                label: 'Playing in ' + (modelData.identity || 'a player')
                detail: modelData.trackTitle || ''
                selected: modelData === MediaService.active
                onActivated: MediaService.setActive(modelData)
            }
        }
        MenuSeparator { visible: panel.p !== null && panel.p.canRaise }
        MenuRow {
            visible: panel.p !== null && panel.p.canRaise
            icon: 'external'
            label: 'Open ' + (panel.p ? panel.p.identity : '')
            onActivated: { panel.p.raise(); if (panel.menu) panel.menu.close(); }
        }
    }
}
