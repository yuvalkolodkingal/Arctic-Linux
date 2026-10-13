import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import "WhatsNewCore.js" as Core

// "What's new" after an Arctic Linux update: a frosted card (the live welcome's look) shown once
// for each packaged update-note id that this account has not seen. A fresh account records the
// current id without showing the card because FirstLogin covers it. Enter, Esc or "Got it" closes
// the card and records that id. Never on the live USB. The decision is in WhatsNewCore.js
// (tests/test-whats-new.cjs). IPC: `whatsnew open` shows it again.
Scope {
    id: root
    property bool cardOpen: false
    property bool cardMapped: false
    property var notes: null
    property string seen: ''
    property int pending: 2            // notes and the per-account seen id
    readonly property string stateDir: (Quickshell.env('XDG_STATE_HOME') || Session.home + '/.local/state') + '/arctic'
    readonly property var screen: Outputs.focused

    function show() {
        if (!notes || Session.live)
            return;
        cardMapped = true;
        cardOpen = true;
    }
    function dismiss() {
        cardOpen = false;
        record(notes ? notes.updateId : '');
    }
    function record(v) {
        if (!v)
            return;
        mkdir.updateId = v;
        mkdir.running = true;
    }
    property bool decided: false
    function settle() {
        if (decided || --pending > 0)
            return;
        decided = true;
        const d = Core.decide(seen, notes, Session.live);
        if (d.record)
            record(d.record);
        if (d.show)
            show();
    }

    FileView {
        path: Quickshell.shellDir + '/whats-new.json'
        printErrors: false
        onLoaded: { root.notes = Core.parseNotes(text()); root.settle(); }
        onLoadFailed: root.settle()
    }
    FileView {
        id: seenFile
        path: root.stateDir + '/whats-new-seen'
        printErrors: false
        onLoaded: { root.seen = text().trim(); root.settle(); }
        onLoadFailed: root.settle()
    }
    Process {
        id: mkdir
        property string updateId: ''
        command: ['mkdir', '-p', root.stateDir]
        onExited: seenFile.setText(updateId + '\n')
    }

    PanelWindow {
        screen: root.screen
        visible: root.cardMapped
        anchors { top: true; bottom: true; left: true; right: true }
        color: 'transparent'
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.layer: WlrLayer.Top
        WlrLayershell.namespace: 'arctic-whats-new'
        WlrLayershell.keyboardFocus: root.cardOpen ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.None
        mask: Region { item: card }

        Rectangle {
            id: card
            width: 480
            height: body.implicitHeight + 2 * 28
            x: (parent.width - width) / 2
            y: parent.height / 2 - 0.46 * height
            radius: Theme.radiusXl
            color: Theme.frost
            border.width: 1
            border.color: Theme.line
            opacity: root.cardOpen ? 1 : 0
            Behavior on opacity {
                NumberAnimation {
                    duration: Theme.fadeSlow
                    easing.type: Easing.BezierSpline
                    easing.bezierCurve: Theme.easeStandard
                    onRunningChanged: if (!running && !root.cardOpen) root.cardMapped = false
                }
            }
            focus: true
            Keys.onEscapePressed: root.dismiss()
            Keys.onReturnPressed: root.dismiss()
            Keys.onEnterPressed: root.dismiss()

            ColumnLayout {
                id: body
                anchors.fill: parent
                anchors.margins: 28
                spacing: 0
                Text {
                    Layout.fillWidth: true
                    text: root.notes ? root.notes.title : ''
                    color: Theme.ink
                    wrapMode: Text.Wrap
                    font.family: Theme.fontSans
                    font.pixelSize: 24
                    font.weight: Font.DemiBold
                    lineHeight: 32
                    lineHeightMode: Text.FixedHeight
                }
                Repeater {
                    model: root.notes ? root.notes.items : []
                    RowLayout {
                        id: item
                        required property var modelData
                        Layout.topMargin: 16
                        Layout.fillWidth: true
                        spacing: Theme.space3
                        Rectangle {
                            Layout.alignment: Qt.AlignTop
                            implicitWidth: 36
                            implicitHeight: 36
                            radius: Theme.radiusMd
                            color: Theme.surfaceSunken
                            Icon { anchors.centerIn: parent; name: item.modelData.icon; size: 20; color: Theme.ink }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Text {
                                Layout.fillWidth: true
                                text: item.modelData.title
                                color: Theme.ink
                                wrapMode: Text.Wrap
                                font.family: Theme.fontSans
                                font.pixelSize: 15
                                font.weight: Font.DemiBold
                            }
                            Text {
                                Layout.fillWidth: true
                                text: item.modelData.text
                                color: Theme.inkMuted
                                wrapMode: Text.Wrap
                                font.family: Theme.fontSans
                                font.pixelSize: 13
                                lineHeight: 18
                                lineHeightMode: Text.FixedHeight
                            }
                        }
                    }
                }
                RowLayout {
                    Layout.topMargin: 24
                    spacing: Theme.space2
                    ArcticButton {
                        variant: 'primary'
                        size: 'lg'
                        text: 'Got it'
                        onClicked: root.dismiss()
                    }
                    ArcticButton {
                        visible: !!(root.notes && root.notes.notesUrl)
                        variant: 'ghost'
                        size: 'lg'
                        text: 'Read the release notes'
                        onClicked: {
                            Quickshell.execDetached(['xdg-open', root.notes.notesUrl]);
                            root.dismiss();
                        }
                    }
                }
            }
        }
    }
}
