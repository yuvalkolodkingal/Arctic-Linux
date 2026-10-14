// Settings controls upstream VoxType through its public commands. No transcript is displayed here.
pragma ComponentBehavior: Bound
import QtQuick
import ".."
import "../components"
import "../DictationStatus.js" as Status

Page {
    id: page
    title: "Dictation"
    lede: "Type by speaking with VoxType and a multilingual Whisper model on this computer."
    readonly property var status: DictationService.status
    readonly property bool settingUp: status.state === 'queued' || status.state === 'downloading'
    readonly property bool downloading: status.state === 'downloading'
    readonly property bool canConfigure: !DictationService.active && !DictationService.busy
    onShown: DictationService.refresh()
    function prepare() { setupDialog.open(); }

    Timer {
        interval: page.settingUp || DictationService.active ? 1500 : 15000
        repeat: true
        running: page.visible
        onTriggered: DictationService.refresh()
    }

    ArBanner {
        width: parent.width
        kind: page.status.state === 'error' ? 'error' : page.status.ready ? 'success' : 'info'
        title: DictationService.headline
        // ArBanner accepts styled text; escape the controller's plain error sentence.
        text: DictationService.detail.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    }

    Group {
        title: "Local setup"
        desc: "Online installation prepares dictation. An offline installation queues setup for a later connection; a failed download does not stop OS installation."
        SettingRow {
            searchKey: "dictation.setup"
            title: "App and Whisper model"
            desc: Status.setupDescription(page.status)
            resettable: false
            stacked: true
            Column {
                width: parent.width
                spacing: Theme.space3
                ArProgress {
                    width: parent.width
                    visible: page.status.state === 'downloading'
                    label: "Downloading and verifying"
                    indeterminate: true
                    valueText: ""
                }
                Row {
                    spacing: Theme.space2
                    ArButton {
                        text: page.status.ready ? "Verify / repair setup…" : page.status.state === 'downloading' ? "Setup running" : "Set up / retry…"
                        iconName: "download"
                        enabled: page.canConfigure && Status.profileKnown(page.status) && !page.downloading
                        gapColor: Theme.surfaceRaised
                        onClicked: page.prepare()
                    }
                    ArButton {
                        text: "Refresh"
                        variant: "ghost"
                        enabled: !DictationService.busy
                        gapColor: Theme.surfaceRaised
                        onClicked: DictationService.refresh()
                    }
                }
            }
        }

    }

    Group {
        title: "Recording"
        SettingRow {
            searchKey: "dictation.record"
            title: "Start and stop"
            desc: "Focus the text field in your app before recording. Super + Ctrl + X starts; the same keys stop and insert the result. The microphone pill remains visible while the taskbar is hidden."
            resettable: false
            stacked: true
            Row {
                spacing: Theme.space2
                ArKbd { text: "Super + Ctrl + X"; anchors.verticalCenter: parent.verticalCenter }
            }
        }
        SettingRow {
            searchKey: "dictation.cancel"
            title: "Cancel without inserting text"
            desc: "Super + Ctrl + Backspace cancels recording or transcription. With the taskbar visible, right-click the dictation pill to cancel. Locking the desktop also cancels."
            resettable: false
            Row {
                spacing: Theme.space2
                ArKbd { text: "Super + Ctrl + Backspace"; anchors.verticalCenter: parent.verticalCenter }
                ArButton {
                    text: "Cancel"
                    enabled: DictationService.active && !DictationService.busy
                    gapColor: Theme.surfaceRaised
                    onClicked: DictationService.cancel()
                }
            }
        }
        SettingRow {
            searchKey: "dictation.language"
            title: "Language"
            desc: "Use the multilingual model for Hebrew and English. Language detection is local; choosing a language can help short recordings."
            resettable: false
            ArSelect {
                width: 220
                enabled: page.status.ready && page.canConfigure
                Component.onCompleted: combo.Accessible.name = "Dictation language"
                model: [{ value: "auto", label: "Detect language" }, { value: "he", label: "Hebrew · עברית" }, { value: "en", label: "English" }]
                value: page.status.language
                onActivated: v => DictationService.run(['set-language', v])
            }
        }
        SettingRow {
            searchKey: "dictation.backend"
            title: "Acceleration"
            desc: Status.accelerationDetail(page.status)
            resettable: false
            ArSelect {
                width: 220
                enabled: page.status.ready && page.canConfigure
                Component.onCompleted: combo.Accessible.name = "Dictation acceleration"
                model: Status.backends(page.status)
                value: page.status.backend
                onActivated: v => DictationService.run(['set-backend', v])
            }
        }
    }

    Group {
        title: "Privacy"
        SettingRow {
            searchKey: "dictation.privacy"
            title: "Audio stays here"
            desc: "Transcription runs locally. Network access downloads the app and model during setup; it does not send recordings. Status, logs and notifications do not show your transcript. Text is inserted only after an explicit recording is stopped."
            resettable: false
        }
    }

    ArDialog {
        id: setupDialog
        title: "Prepare local dictation?"
        body: Status.setupConsent(page.status)
        ArButton {
            text: "Download and verify"
            enabled: page.canConfigure && !page.downloading && Status.profileKnown(page.status)
            onClicked: { setupDialog.close(); DictationService.run(['retry']); }
        }
    }
}
