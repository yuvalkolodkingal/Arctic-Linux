import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import "PackageSearch.js" as PackageSearch

ColumnLayout {
    id: terminal
    property bool jobRunning: false
    property bool secret: false
    property string output: ''
    property string notice: ''
    property bool started: false
    property bool submitting: false
    property var packages: []
    property var matches: []
    property string indexError: ''
    property string completedText: '\u0000'
    readonly property bool suggestionsOpen: !jobRunning && !secret && !submitting && completedText !== input.text && PackageSearch.context(input.text, input.cursorPosition).allowed
    function updateMatches() {
        if (jobRunning || secret || submitting) return;
        const ctx = PackageSearch.context(input.text, input.cursorPosition);
        matches = ctx.allowed ? PackageSearch.search(packages, ctx.query) : [];
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
    Timer { id: filterTimer; interval: 60; onTriggered: terminal.updateMatches() }
    Process {
        id: packageIndex
        command: ['python3', Quickshell.env('HOME') + '/.config/quickshell/scripts/package-index.py']
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const result = JSON.parse(text);
                    terminal.packages = result.packages || [];
                    terminal.indexError = result.error || '';
                    terminal.updateMatches();
                } catch (e) { terminal.indexError = 'Could not read the package list.'; }
            }
        }
    }
    signal backRequested()
    spacing: 10
    onVisibleChanged: if (visible) entrance.restart()
    NumberAnimation { id: entrance; target: terminal; property: 'opacity'; from: 0; to: 1; duration: Theme.motionDuration; easing.type: Easing.OutCubic }
    function open() {
        if (!backend.running) { started = true; backend.running = true; }
        if (!packages.length && !packageIndex.running) packageIndex.running = true;
        updateMatches();
        input.forceActiveFocus();
    }
    function send(action, text) {
        if (!backend.running) return;
        backend.write(JSON.stringify({action: action, text: text || '', secret: terminal.secret}) + '\n');
    }
    Process {
        id: backend
        command: [Quickshell.env('HOME') + '/.config/quickshell/scripts/install-terminal.py']
        stdinEnabled: true
        stdout: SplitParser {
            onRead: data => {
                try {
                    const state = JSON.parse(data);
                    const wasSecret = terminal.secret;
                    terminal.jobRunning = state.running;
                    terminal.submitting = false;
                    terminal.secret = state.secret;
                    if (wasSecret !== state.secret) input.clear();
                    terminal.output = state.output;
                    terminal.notice = state.notice;
                } catch (e) { terminal.notice = 'Could not read terminal output.'; }
            }
        }
        onExited: {
            terminal.jobRunning = false;
            terminal.secret = false;
            input.clear();
            terminal.notice = 'Console disconnected. Reopen Install to reconnect.';
        }
    }
    RowLayout {
        Layout.fillWidth: true
        PickerButton { text: 'Back'; onClicked: terminal.backRequested() }
        Text { text: 'Install'; color: Theme.text; font.family: Theme.font; font.pixelSize: 14 }
        Item { Layout.fillWidth: true }
        PickerButton { text: 'Refresh'; enabled: !terminal.jobRunning && !terminal.submitting && !packageIndex.running; onClicked: { terminal.indexError = ''; packageIndex.running = true; } }
        PickerButton { text: 'Clear'; enabled: !terminal.jobRunning; onClicked: terminal.send('clear') }
        PickerButton { text: 'Ctrl+C'; enabled: terminal.jobRunning; onClicked: terminal.send('interrupt') }
    }
    Rectangle {
        Layout.fillWidth: true
        Layout.fillHeight: true
        color: Theme.surface
        radius: 6
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 12
            visible: terminal.suggestionsOpen
            spacing: 8
            Text {
                Layout.fillWidth: true
                text: packageIndex.running ? 'Loading packages…' : terminal.indexError || terminal.matches.length + ' / ' + terminal.packages.length + ' packages · Tab to complete'
                color: Theme.muted
                font.family: Theme.font
                font.pixelSize: 11
            }
            ListView {
                id: packageList
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: terminal.matches
                keyNavigationWraps: true
                highlightMoveDuration: 0
                ScrollBar.vertical: ScrollBar {}
                delegate: Button {
                    id: suggestion
                    required property string modelData
                    required property int index
                    width: packageList.width
                    height: 30
                    hoverEnabled: true
                    focusPolicy: Qt.NoFocus
                    onClicked: { packageList.currentIndex = index; terminal.completeSelection(); }
                    background: Rectangle {
                        radius: 4
                        color: packageList.currentIndex === suggestion.index ? Theme.accent : suggestion.hovered ? Theme.background : 'transparent'
                    }
                    contentItem: Text {
                        text: suggestion.modelData
                        color: packageList.currentIndex === suggestion.index ? '#111318' : Theme.text
                        font.family: 'DejaVu Sans Mono'
                        font.pixelSize: 12
                        elide: Text.ElideRight
                        verticalAlignment: Text.AlignVCenter
                    }
                    leftPadding: 8
                }
                Text {
                    anchors.centerIn: parent
                    visible: !packageIndex.running && !terminal.indexError && packageList.count === 0
                    text: terminal.packages.length ? 'No matching packages' : 'No packages found'
                    color: Theme.muted
                    font.family: Theme.font
                    font.pixelSize: 12
                }
            }
        }
        ScrollView {
            id: scroll
            visible: !terminal.suggestionsOpen
            anchors.fill: parent
            anchors.margins: 12
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
                font.family: 'DejaVu Sans Mono'
                font.pixelSize: 12
                color: Theme.text
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
        color: Theme.muted
        wrapMode: Text.Wrap
        font.family: Theme.font
        font.pixelSize: 12
    }
    RowLayout {
        Layout.fillWidth: true
        Text { text: terminal.secret ? 'Password' : terminal.jobRunning ? '›' : '$'; color: Theme.accent; font.family: 'DejaVu Sans Mono'; font.pixelSize: 13 }
        TextField {
            id: input
            Layout.fillWidth: true
            implicitHeight: 40
            enabled: backend.running
            placeholderText: terminal.secret ? 'Password' : terminal.jobRunning ? 'Response…' : 'emerge --ask package'
            echoMode: terminal.secret ? TextInput.Password : TextInput.Normal
            inputMethodHints: terminal.secret ? Qt.ImhSensitiveData | Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase : Qt.ImhNoPredictiveText
            color: Theme.text
            placeholderTextColor: Theme.muted
            font.family: 'DejaVu Sans Mono'
            font.pixelSize: 12
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
                if (terminal.suggestionsOpen && terminal.matches.length) {
                    terminal.completeSelection(); return;
                }
                if (!terminal.jobRunning && !text.trim()) return;
                if (!terminal.jobRunning) terminal.submitting = true;
                terminal.send(terminal.jobRunning ? 'input' : 'start', text);
                clear();
            }
            Keys.onPressed: event => {
                if (terminal.suggestionsOpen && (event.key === Qt.Key_Down || event.key === Qt.Key_Up)) {
                    if (event.key === Qt.Key_Down) packageList.incrementCurrentIndex(); else packageList.decrementCurrentIndex();
                    event.accepted = true; return;
                }
                if (terminal.suggestionsOpen && event.key === Qt.Key_Tab) {
                    terminal.completeSelection(); event.accepted = true; return;
                }
                if ((event.modifiers & Qt.ControlModifier) && event.key === Qt.Key_C && terminal.jobRunning) {
                    terminal.send('interrupt'); clear(); event.accepted = true;
                }
            }
            background: Rectangle { radius: 6; color: Theme.surface; border.width: input.activeFocus ? 1 : 0; border.color: Theme.accent }
        }
    }
}
