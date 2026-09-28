import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."
import "GetApps.js" as GetAppsLogic

// The job strip at the bottom of the Get apps pages: what is installing or being removed, its
// progress (amber fill, or a moving bar before there are numbers), the step, and Stop / Cancel.
// A finished job stays for a minute with its outcome. Show details reveals the runner's
// transcript. Jobs belong to AppsService, so they carry on when the launcher closes.
ColumnLayout {
    id: card
    property bool detailsOpen: false
    property double now: Date.now()
    readonly property var jobs: AppsService.jobs
    readonly property var shown: {
        const active = jobs.find(j => j.phase === 'running') || jobs.find(j => j.phase === 'waiting');
        if (active) return active;
        for (let i = jobs.length - 1; i >= 0; i--)
            if (jobs[i].finishedAt && now - jobs[i].finishedAt < 60000 && jobs[i].phase !== 'cancelled') return jobs[i];
        return null;
    }
    readonly property int waiting: jobs.filter(j => j.phase === 'waiting').length - (shown && shown.phase === 'waiting' ? 1 : 0)
    readonly property bool failed: shown !== null && shown.phase === 'failed'
    readonly property bool done: shown !== null && shown.phase === 'done'
    readonly property bool active: shown !== null && (shown.phase === 'running' || shown.phase === 'waiting')
    visible: shown !== null
    spacing: Theme.space2

    function showDetails() { detailsOpen = true; }

    Timer { interval: 5000; repeat: true; running: card.shown !== null && !card.active; onTriggered: card.now = Date.now() }
    onShownChanged: now = Date.now()
    Binding { target: AppsService; property: 'transcript'; value: card.detailsOpen && card.visible; when: card.visible }

    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.line }
    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space3
        Icon {
            name: card.failed ? 'x-circle' : card.done ? 'check-circle' : card.shown && card.shown.phase === 'waiting' ? 'clock'
                  : card.shown && card.shown.kind === 'remove' ? 'trash' : 'download'
            size: 20
            color: card.failed ? Theme.error : card.done ? Theme.success : Theme.inkMuted
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space2
                Text {
                    Layout.fillWidth: true
                    text: card.shown ? (card.failed ? (card.shown.kind === 'remove' ? card.shown.name + ' wasn’t removed' : card.shown.name + ' wasn’t installed')
                                        : GetAppsLogic.jobLabel(card.shown)) + (card.waiting > 0 ? ' · ' + card.waiting + ' more waiting' : '') : ''
                    textFormat: Text.PlainText
                    color: Theme.ink
                    font.family: Theme.fontSans
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }
                Text {
                    visible: card.active && card.shown.percent !== null && card.shown.percent !== undefined
                    text: (card.shown && card.shown.percent !== null ? card.shown.percent : 0) + '%'
                    color: Theme.inkMuted
                    font.family: Theme.fontSans
                    font.pixelSize: 12
                    font.features: { 'tnum': 1 }
                }
            }
            // 4px progress: the amber fill, or a moving segment until dnf/flatpak report numbers.
            Rectangle {
                id: track
                Layout.fillWidth: true
                visible: card.active
                implicitHeight: 4
                radius: 2
                color: Theme.surfaceSunken
                clip: true
                readonly property bool known: card.shown !== null && card.shown.percent !== null && card.shown.percent !== undefined
                Rectangle {
                    visible: track.known
                    width: track.width * Math.max(0, Math.min(100, card.shown && card.shown.percent || 0)) / 100
                    height: parent.height
                    radius: 2
                    color: Theme.accent
                    Behavior on width { NumberAnimation { duration: Theme.durationBase } }
                }
                Rectangle {
                    id: sweep
                    visible: !track.known && card.shown !== null && card.shown.phase === 'running'
                    width: track.width / 4
                    height: parent.height
                    radius: 2
                    color: Theme.accent
                    NumberAnimation on x {
                        running: sweep.visible && !Theme.reduceMotion
                        from: -sweep.width; to: track.width
                        duration: 1400
                        loops: Animation.Infinite
                    }
                }
            }
            Text {
                Layout.fillWidth: true
                visible: text !== ''
                text: !card.shown ? '' : card.failed ? card.shown.message
                      : card.done ? (card.shown.kind === 'install' ? 'It’s in the launcher.' : '')
                      : card.shown.phase === 'waiting' ? 'Waiting for the change before it'
                      : card.shown.step || 'Starting…'
                textFormat: Text.PlainText
                color: card.failed ? Theme.error : Theme.inkMuted
                font.family: Theme.fontSans
                font.pixelSize: 12
                wrapMode: Text.Wrap
                maximumLineCount: 2
                elide: Text.ElideRight
            }
        }
        // A dnf change after updates were downloaded: arctic-update prepares them again.
        Text {
            visible: card.shown !== null && card.shown.source === 'dnf' && UpdateService.ready
            Layout.maximumWidth: 220
            text: 'The updates waiting for a restart are prepared again two minutes after this.'
            color: Theme.inkSubtle
            font.family: Theme.fontSans
            font.pixelSize: 12
            wrapMode: Text.Wrap
        }
        ArcticButton {
            variant: 'ghost'; size: 'sm'
            text: card.detailsOpen ? 'Hide details' : 'Show details'
            visible: card.shown !== null && card.shown.phase !== 'waiting'
            onClicked: card.detailsOpen = !card.detailsOpen
        }
        ArcticButton {
            variant: 'secondary'; size: 'sm'
            visible: card.active
            text: card.shown && card.shown.phase === 'waiting' ? 'Cancel' : 'Stop'
            onClicked: AppsService.cancel(card.shown.id)
        }
    }
    Rectangle {
        Layout.fillWidth: true
        visible: card.detailsOpen
        implicitHeight: 200
        color: Theme.surfaceSunken
        radius: Theme.radiusMd
        border.width: 1
        border.color: Theme.line
        ScrollView {
            id: scroll
            anchors.fill: parent
            anchors.margins: Theme.space2
            clip: true
            TextArea {
                text: AppsService.consoleOutput
                readOnly: true
                selectByMouse: true
                textFormat: TextEdit.PlainText
                wrapMode: TextEdit.NoWrap
                font.family: Theme.fontMono
                font.pixelSize: 12
                color: Theme.ink
                selectionColor: Theme.selection
                selectedTextColor: Theme.ink
                padding: 0
                background: null
                onTextChanged: Qt.callLater(() => { if (scroll.contentItem) scroll.contentItem.contentY = Math.max(0, scroll.contentHeight - scroll.availableHeight); })
            }
        }
    }
}
