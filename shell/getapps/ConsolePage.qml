pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."
import "../PackageSearch.js" as PackageSearch

// Get apps → Console: a small terminal for dnf and Flatpak (from the original shell's install
// console), for power users. Type an app name to install it, or a dnf / flatpak command; the
// commands run in a real PTY (scripts/install-terminal.py, owned by AppsService, which runs the
// other pages' installs and removals in the same PTY — they show here too). Installs run
// unattended (-y) and dnf gets root through pkexec, whose password dialog is the shell's
// PolkitDialog; typed removals list what goes and ask [y/N] here. Anything a program asks is
// answered on the input line, password input masked and never logged or stored. Tab completes
// package names from the cached index (scripts/package-index.py).
ColumnLayout {
    id: terminal
    readonly property bool jobRunning: AppsService.consoleRunning || AppsService.job !== null
    readonly property bool guiJob: AppsService.job !== null
    readonly property bool secret: AppsService.consoleSecret
    readonly property string output: AppsService.consoleOutput
    readonly property string notice: AppsService.consoleNotice
    readonly property bool submitting: AppsService.consoleSubmitting
    readonly property var packages: AppsService.packages
    readonly property var index: AppsService.packageIndex
    property var matches: []
    property string source: 'all'
    readonly property bool indexRefreshing: AppsService.indexRefreshing
    readonly property string indexError: AppsService.indexError
    property string completedText: '\u0000'
    readonly property bool suggestionsOpen: !jobRunning && !secret && !submitting && input.text.length > 0
                                            && completedText !== input.text && PackageSearch.context(input.text, input.cursorPosition).allowed
    signal backRequested()
    readonly property Item inputItem: input
    spacing: Theme.space3

    function back() { return false; }
    onSecretChanged: input.clear()
    onIndexChanged: updateMatches()
    Binding { target: AppsService; property: 'transcript'; value: true; when: terminal.visible }

    function updateMatches() {
        if (jobRunning || secret || submitting) return;
        const ctx = PackageSearch.context(input.text, input.cursorPosition);
        terminal.source = ctx.source;
        matches = ctx.allowed ? PackageSearch.search(index, ctx.query, ctx.source).slice(0, 200) : [];
        packageList.currentIndex = matches.length ? 0 : -1;
    }
    function completeSelection() {
        if (packageList.currentIndex < 0 || !matches.length) return;
        const result = PackageSearch.complete(input.text, input.cursorPosition, matches[packageList.currentIndex]);
        input.text = result.text;
        input.cursorPosition = result.cursor;
        completedText = result.text;
        input.forceActiveFocus();
    }
    function open() {
        AppsService.ensureStarted();
        updateMatches();
        input.forceActiveFocus();
    }
    function send(action, text) { AppsService.consoleSend(action, text); }

    Timer { id: filterTimer; interval: 60; onTriggered: terminal.updateMatches() }

    // ---- header -----------------------------------------------------------------------
    PageHeader {
        title: 'Console'
        onBack: terminal.backRequested()
        ArcticButton {
            variant: 'ghost'; size: 'sm'; iconName: 'refresh'; text: 'Refresh list'
            enabled: !terminal.jobRunning && !terminal.indexRefreshing
            onClicked: AppsService.refreshIndex(true)
        }
        ArcticButton { variant: 'ghost'; size: 'sm'; text: 'Clear'; enabled: !terminal.jobRunning; onClicked: terminal.send('clear') }
        ArcticButton { variant: 'secondary'; size: 'sm'; text: 'Stop  Ctrl+C'; enabled: terminal.jobRunning; onClicked: terminal.send('interrupt') }
    }

    // ---- terminal well (or package suggestions while typing a name) -----------------------
    Rectangle {
        Layout.fillWidth: true
        Layout.fillHeight: true
        color: Theme.surfaceSunken
        radius: Theme.radiusMd
        border.width: 1
        border.color: Theme.line

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Theme.space3
            visible: terminal.suggestionsOpen
            spacing: Theme.space2
            Text {
                Layout.fillWidth: true
                text: terminal.indexError ? terminal.indexError
                      : !terminal.packages.length ? (terminal.indexRefreshing || !AppsService.indexLoaded ? 'Getting the package list… this takes a minute the first time.' : 'No package list yet.')
                      : terminal.matches.length + (terminal.matches.length >= 200 ? '+' : '') + ' matches · Tab or Enter completes'
                           + (terminal.indexRefreshing ? ' · updating the list' : '')
                color: Theme.inkMuted
                font.family: Theme.fontSans
                font.pixelSize: 12
                font.weight: Font.Medium
            }
            ListView {
                id: packageList
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: terminal.matches
                keyNavigationWraps: true
                highlightMoveDuration: 0
                spacing: 2
                ScrollBar.vertical: ScrollBar {}
                delegate: Rectangle {
                    id: suggestion
                    required property string modelData
                    required property int index
                    readonly property bool selected: packageList.currentIndex === index
                    readonly property bool app: modelData.startsWith('flathub:')
                    width: packageList.width
                    height: 30
                    radius: Theme.radiusSm
                    color: selected ? Theme.accentSoft : hover.containsMouse ? Theme.surfaceRaised : 'transparent'
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Theme.space2
                        anchors.rightMargin: Theme.space2
                        spacing: Theme.space2
                        Icon { name: suggestion.app ? 'package' : 'download'; size: 16; color: Theme.inkMuted }
                        Text {
                            Layout.fillWidth: true
                            text: suggestion.app ? suggestion.modelData.slice(8) : suggestion.modelData
                            color: Theme.ink
                            font.family: Theme.fontMono
                            font.pixelSize: 13
                            elide: Text.ElideRight
                        }
                        Text {
                            text: suggestion.app ? 'Flathub' : 'Fedora'
                            color: Theme.inkMuted
                            font.family: Theme.fontSans
                            font.pixelSize: 12
                        }
                    }
                    MouseArea {
                        id: hover
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: { packageList.currentIndex = suggestion.index; terminal.completeSelection(); }
                    }
                }
                Text {
                    anchors.centerIn: parent
                    visible: terminal.packages.length > 0 && packageList.count === 0
                    text: 'No matching packages'
                    color: Theme.inkMuted
                    font.family: Theme.fontSans
                    font.pixelSize: 13
                }
            }
        }
        ScrollView {
            id: scroll
            visible: !terminal.suggestionsOpen
            anchors.fill: parent
            anchors.margins: Theme.space3
            clip: true
            contentWidth: transcript.implicitWidth
            contentHeight: transcript.implicitHeight
            TextArea {
                id: transcript
                text: terminal.output
                readOnly: true
                selectByMouse: true
                textFormat: TextEdit.PlainText
                wrapMode: TextEdit.NoWrap
                font.family: Theme.fontMono
                font.pixelSize: 13
                color: Theme.ink
                selectionColor: Theme.selection
                selectedTextColor: Theme.ink
                padding: 0
                background: null
                onTextChanged: Qt.callLater(() => { if (scroll.contentItem) scroll.contentItem.contentY = Math.max(0, scroll.contentHeight - scroll.availableHeight); })
            }
        }
    }

    Text {
        Layout.fillWidth: true
        visible: text.length > 0
        text: terminal.notice
        color: Theme.inkMuted
        wrapMode: Text.Wrap
        font.family: Theme.fontSans
        font.pixelSize: 13
    }

    // ---- input line ---------------------------------------------------------------------
    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space2
        Item {
            Layout.preferredWidth: 20
            Layout.preferredHeight: 20
            Icon { anchors.centerIn: parent; visible: terminal.secret; name: 'lock'; size: 18; color: Theme.accentText }
            Text {
                anchors.centerIn: parent
                visible: !terminal.secret
                text: terminal.jobRunning ? '›' : '$'
                color: Theme.accentText
                font.family: Theme.fontMono
                font.pixelSize: 15
                font.weight: Font.Bold
            }
        }
        ArcticField {
            id: input
            Layout.fillWidth: true
            enabled: !terminal.guiJob
            font.family: Theme.fontMono
            font.pixelSize: 13
            placeholderText: terminal.guiJob ? AppsService.currentLabel + '… the Console waits for it' : terminal.secret ? 'Password (hidden)' : terminal.jobRunning ? 'Answer the prompt above…' : 'App name, or a dnf or flatpak command'
            echoMode: terminal.secret ? TextInput.Password : TextInput.Normal
            inputMethodHints: terminal.secret ? Qt.ImhSensitiveData | Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase : Qt.ImhNoPredictiveText
            selectByMouse: !terminal.secret
            onTextEdited: {
                if (!terminal.jobRunning && !terminal.secret && !terminal.submitting) {
                    terminal.completedText = '\u0000';
                    filterTimer.restart();
                }
            }
            onCursorPositionChanged: if (!terminal.jobRunning && !terminal.secret && !terminal.submitting) filterTimer.restart()
            onAccepted: {
                if (terminal.submitting) return;
                if (filterTimer.running) { filterTimer.stop(); terminal.updateMatches(); }
                if (terminal.suggestionsOpen && terminal.matches.length && input.text !== terminal.matches[packageList.currentIndex]) {
                    terminal.completeSelection();
                    return;
                }
                if (!terminal.jobRunning && !text.trim()) return;
                if (terminal.guiJob) return;
                terminal.send(terminal.jobRunning ? 'input' : 'start', text);
                clear();
            }
            Keys.onPressed: event => {
                if (terminal.suggestionsOpen && (event.key === Qt.Key_Down || event.key === Qt.Key_Up)) {
                    if (event.key === Qt.Key_Down) packageList.incrementCurrentIndex(); else packageList.decrementCurrentIndex();
                    event.accepted = true;
                    return;
                }
                if (terminal.suggestionsOpen && event.key === Qt.Key_Tab) {
                    terminal.completeSelection();
                    event.accepted = true;
                    return;
                }
                if ((event.modifiers & Qt.ControlModifier) && event.key === Qt.Key_C && terminal.jobRunning) {
                    terminal.send('interrupt');
                    clear();
                    event.accepted = true;
                }
            }
        }
    }
}
