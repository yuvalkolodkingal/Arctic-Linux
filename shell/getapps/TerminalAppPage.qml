pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Dialogs
import QtQuick.Layouts
import ".."

// Get apps → Terminal apps: a terminal program (btop, yazi, a script of yours) as its own
// launcher entry, opening in your terminal as a floating or tiled window (scripts/apps.py
// terminal-app add writes the entry in ~/.local/share/applications; the launcher picks it up by
// itself). Nothing is installed here: a program that isn't installed yet is one search away in
// Fedora packages. Remove apps lists these entries under Terminal apps.
FocusScope {
    id: page
    property string window: 'float'
    property string picture: ''
    property string error: ''
    property string errorCode: ''
    property string done: ''
    property bool adding: false
    readonly property string program: command.text.trim().split(/\s+/)[0] || ''
    readonly property string displayName: nameField.text.trim() || (program ? program.charAt(0).toUpperCase() + program.slice(1) : '')
    readonly property Item inputItem: command
    signal backRequested()
    signal openPage(string name, string text)

    function back() {
        if (command.text || nameField.text) { command.text = ''; nameField.text = ''; error = ''; done = ''; return true; }
        return false;
    }
    function add() {
        if (adding || !program) return;
        adding = true;
        error = ''; errorCode = ''; done = '';
        const args = ['terminal-app', 'add', '--name', displayName, '--command', command.text.trim(), '--window', window]
                     .concat(picture ? ['--icon', picture] : []);
        AppsService.helper(args, r => {
            page.adding = false;
            if (!r.ok) { page.error = r.error; page.errorCode = r.code || ''; return; }
            page.done = r.app.name + ' is in the launcher.';
            command.text = ''; nameField.text = ''; page.picture = '';
        });
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.space3

        PageHeader { title: 'Terminal apps'; onBack: page.backRequested() }
        Text {
            Layout.fillWidth: true
            text: 'Put a terminal program in the launcher, like btop or yazi. It opens in your terminal, in a window of its own.'
            color: Theme.inkMuted
            font.family: Theme.fontSans
            font.pixelSize: 13
            wrapMode: Text.Wrap
        }
        GridLayout {
            Layout.fillWidth: true
            columns: 2
            columnSpacing: Theme.space3
            rowSpacing: Theme.space3
            Text { text: 'Command'; color: Theme.inkMuted; font.family: Theme.fontSans; font.pixelSize: 13; Layout.preferredWidth: 90 }
            ArcticField {
                id: command
                Layout.fillWidth: true
                focus: true
                font.family: Theme.fontMono
                placeholderText: 'btop'
                onTextEdited: { page.error = ''; page.done = ''; }
                Keys.onReturnPressed: page.add()
                Keys.onEnterPressed: page.add()
            }
            Text { text: 'Name'; color: Theme.inkMuted; font.family: Theme.fontSans; font.pixelSize: 13 }
            ArcticField {
                id: nameField
                Layout.fillWidth: true
                maximumLength: 64
                placeholderText: page.displayName || 'Btop'
                Keys.onReturnPressed: page.add()
                Keys.onEnterPressed: page.add()
            }
            Text { text: 'Window'; color: Theme.inkMuted; font.family: Theme.fontSans; font.pixelSize: 13 }
            Segmented {
                model: [{ key: 'float', label: 'Floating' }, { key: 'tile', label: 'Tiled' }]
                current: page.window
                onActivated: key => page.window = key
            }
            Text { text: 'Icon'; color: Theme.inkMuted; font.family: Theme.fontSans; font.pixelSize: 13 }
            RowLayout {
                spacing: Theme.space2
                AppTile { size: 36; imageSource: page.picture; iconName: page.picture ? '' : page.program; fallbackGlyph: 'prompt'; tint: 'slate900' }
                ArcticButton { variant: 'secondary'; size: 'sm'; text: 'Choose a picture…'; onClicked: pictureDialog.open() }
                ArcticButton { visible: page.picture !== ''; variant: 'ghost'; size: 'sm'; text: 'Use its own icon'; onClicked: page.picture = '' }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            visible: page.error !== ''
            spacing: Theme.space2
            Icon { Layout.alignment: Qt.AlignTop; name: 'x-circle'; size: 16; color: Theme.error }
            Text { Layout.fillWidth: true; text: page.error; color: Theme.error; font.family: Theme.fontSans; font.pixelSize: 13; wrapMode: Text.Wrap }
            ArcticButton {
                visible: page.errorCode === 'missing'
                variant: 'secondary'; size: 'sm'
                text: 'Find ' + page.program + ' in Fedora packages'
                onClicked: page.openPage('dnf', page.program)
            }
        }
        RowLayout {
            visible: page.done !== ''
            spacing: Theme.space2
            Icon { name: 'check-circle'; size: 16; color: Theme.success }
            Text { text: page.done; color: Theme.ink; font.family: Theme.fontSans; font.pixelSize: 13 }
        }
        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            ArcticButton {
                variant: 'primary'
                enabled: page.program !== '' && !page.adding
                text: 'Add ' + (page.displayName || 'app')
                onClicked: page.add()
            }
        }
        Item { Layout.fillHeight: true }
    }
    FileDialog {
        id: pictureDialog
        title: 'Choose a picture for the app'
        nameFilters: ['Pictures (*.png *.jpg *.jpeg *.webp)']
        onAccepted: page.picture = decodeURIComponent(String(selectedFile).replace(/^file:\/\//, ''))
    }
}
