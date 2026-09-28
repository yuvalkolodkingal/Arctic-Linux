pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import QtQuick.Layouts
import Quickshell
import Quickshell.Io

// Wallpaper picker (from the original shell): a searchable grid of thumbnails; click one to
// use it. The Arctic wallpapers come first and follow the Winter / Polar night switch; your
// own pictures come from a folder you choose (default ~/Pictures/Wallpapers).
// Applying goes through `arctic-wallpaper`, so the lock screen and the next login agree.
// "Match colours to wallpaper" is `arctic-theme auto on|off` (settings.json "auto_colors",
// on by default): your pictures then colour the whole desktop, Arctic's keep its palettes.
Popover {
    id: picker
    property var items: []
    property string current: ''
    property string applying: ''
    property string status: ''
    property string folder: ''
    property bool folderExists: false
    property string query: ''
    // Colours follow the wallpaper (arctic-theme auto); missing setting = on.
    property bool autoColors: true
    property bool refreshAfter: false
    readonly property var filtered: items.filter(item => item.name.toLowerCase().includes(query.trim().toLowerCase()))
    readonly property string helper: Session.scripts + '/wallpapers.py'

    layerName: 'arctic-wallpapers'
    cardWidth: Math.min(880, width - 32)
    cardHeight: Math.min(640, height - 32)

    function refresh() {
        if (scan.running || apply.running) return;
        status = items.length ? '' : 'Loading your wallpapers…';
        scan.running = true;
    }
    function setAutoColors(on) {
        if (autoSwitch.running) return;
        picker.autoColors = on;
        status = on ? 'Matching the colours to your wallpaper…' : 'Going back to the Arctic colours…';
        autoSwitch.command = ['arctic-theme', 'auto', on ? 'on' : 'off'];
        autoSwitch.running = true;
    }
    function use(item) {
        if (apply.running || !item) return;
        applying = item.key;
        status = 'Setting ' + item.name + '…';
        apply.command = ['python3', helper, 'apply', item.key];
        apply.running = true;
    }
    focusItem: search
    onOpened: refresh()
    // Theme switch: the Arctic thumbnails change with it (after a wallpaper or colour change
    // that is still running, once it's done).
    function themeChanged() {
        if (!picker.open) return;
        if (apply.running || autoSwitch.running) picker.refreshAfter = true;
        else picker.refresh();
    }
    function finished() {
        if (!picker.refreshAfter) return;
        picker.refreshAfter = false;
        Qt.callLater(picker.refresh);
    }
    Connections {
        target: Theme
        function onThemeIdChanged() { picker.themeChanged(); }
        function onDarkChanged() { picker.themeChanged(); }
    }
    FileView {
        id: settingsView
        path: Session.arcticConfig + '/settings.json'
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: {
            try {
                const data = JSON.parse(text());
                picker.autoColors = data.auto_colors !== false;
            } catch (e) { picker.autoColors = true; }
        }
        onLoadFailed: picker.autoColors = true
    }
    Process {
        id: autoSwitch
        stderr: StdioCollector { id: autoErrors }
        onExited: exitCode => {
            settingsView.reload();
            picker.status = exitCode === 0 ? '' : (autoErrors.text.trim().split('\n').pop().replace(/^arctic-theme: /, '') || 'The colours could not be changed.');
            picker.finished();
        }
    }

    Process {
        id: scan
        command: ['python3', picker.helper, 'list']
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const result = JSON.parse(text);
                    if (!result.items) { picker.status = result.error || 'Could not load your wallpapers.'; return; }
                    picker.items = result.items;
                    picker.folder = result.folder;
                    picker.folderExists = result.folderExists;
                    picker.current = result.current;
                    picker.status = '';
                } catch (e) { picker.status = 'Could not load your wallpapers.'; }
            }
        }
    }
    Process {
        id: apply
        onExited: picker.finished()
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const result = JSON.parse(text);
                    if (result.ok) { picker.current = picker.applying; picker.status = ''; }
                    else picker.status = result.error;
                } catch (e) { picker.status = 'Could not set the wallpaper. Please try again.'; }
            }
        }
    }
    Process {
        id: changeFolder
        stdout: StdioCollector {
            onStreamFinished: {
                try { const result = JSON.parse(text); if (result.ok) picker.refresh(); else picker.status = result.error; }
                catch (e) { picker.status = 'Could not open that folder.'; }
            }
        }
    }
    FolderDialog {
        id: folderDialog
        title: 'Choose a folder of wallpapers'
        currentFolder: picker.folderExists ? 'file://' + picker.folder : 'file://' + Session.home
        onAccepted: { changeFolder.command = ['python3', picker.helper, 'folder', selectedFolder.toString()]; changeFolder.running = true; }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.space6
        anchors.topMargin: Theme.space3
        spacing: Theme.space4

        DragHandle {
            Layout.fillWidth: true
            Layout.bottomMargin: -Theme.space2
            windowX: picker.card.x
            windowY: picker.card.y
            onMoved: (nextX, nextY) => picker.dock.moveTo(nextX, nextY)
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space2
            ColumnLayout {
                spacing: 2
                Text { text: 'Wallpapers'; color: Theme.ink; font.family: Theme.fontSans; font.pixelSize: 20; font.weight: Font.DemiBold }
                Text {
                    text: picker.autoColors ? 'Click one to use it. Your pictures colour the desktop; Arctic wallpapers keep the Arctic palette.'
                                            : 'Click one to use it. Arctic wallpapers follow the ' + Theme.themeName + ' theme.'
                    color: Theme.inkMuted
                    font.family: Theme.fontSans
                    font.pixelSize: 13
                }
            }
            Item { Layout.fillWidth: true }
            ArcticButton { variant: 'secondary'; size: 'sm'; iconName: 'folder'; text: 'Choose folder…'; enabled: !apply.running && !changeFolder.running; onClicked: folderDialog.open() }
            ArcticButton { variant: 'ghost'; size: 'sm'; iconName: 'refresh'; iconOnly: true; label: 'Refresh'; enabled: !scan.running && !apply.running; onClicked: picker.refresh() }
            ArcticButton { variant: 'ghost'; size: 'sm'; iconName: 'x'; iconOnly: true; label: 'Close  (Esc)'; onClicked: picker.close() }
        }
        ArcticField {
            id: search
            Layout.fillWidth: true
            iconName: 'search'
            placeholderText: 'Search wallpapers'
            onTextChanged: picker.query = text
            Keys.onDownPressed: { grid.forceActiveFocus(); if (grid.currentIndex < 0) grid.currentIndex = 0; }
            Keys.onReturnPressed: picker.use(picker.filtered[0])
            Keys.onEscapePressed: picker.close()
        }
        GridView {
            id: grid
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            readonly property int columns: Math.max(1, Math.floor(width / 196))
            cellWidth: width / columns
            cellHeight: (cellWidth - Theme.space3) * 0.625 + 40
            model: picker.filtered
            keyNavigationEnabled: true
            currentIndex: -1
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}
            Keys.onReturnPressed: picker.use(picker.filtered[currentIndex])
            Keys.onSpacePressed: picker.use(picker.filtered[currentIndex])
            Keys.onEscapePressed: picker.close()
            Keys.onUpPressed: event => { if (currentIndex < columns) search.forceActiveFocus(); else event.accepted = false; }
            delegate: Item {
                id: cell
                required property var modelData
                required property int index
                readonly property bool isCurrent: picker.current === modelData.key
                readonly property bool keyboard: grid.activeFocus && grid.currentIndex === index
                width: grid.cellWidth
                height: grid.cellHeight
                Rectangle {
                    id: tile
                    anchors.fill: parent
                    anchors.rightMargin: Theme.space3
                    anchors.bottomMargin: Theme.space3
                    radius: Theme.radiusLg
                    color: tileMouse.containsMouse ? Theme.surfaceSunken : 'transparent'
                    Behavior on color { ColorAnimation { duration: Theme.durationFast } }
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.space1
                        spacing: Theme.space1
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: width * 0.625
                            radius: Theme.radiusMd
                            color: Theme.surfaceSunken
                            border.width: cell.isCurrent ? 2 : 1
                            border.color: cell.isCurrent ? Theme.accentEdge : Theme.line
                            RoundedImage {
                                anchors.fill: parent
                                anchors.margins: cell.isCurrent ? 3 : 1
                                radius: Theme.radiusMd - anchors.margins
                                source: cell.modelData.thumb ? 'file://' + cell.modelData.thumb : ''
                                sourceSize.width: 480
                            }
                            Rectangle {
                                visible: cell.isCurrent
                                anchors { right: parent.right; top: parent.top; margins: Theme.space2 }
                                width: 22; height: 22; radius: 11
                                color: Theme.accent
                                border.width: Theme.dark ? 0 : 1
                                border.color: Theme.accentEdge
                                Icon { anchors.centerIn: parent; name: 'check'; size: 14; color: Theme.onAccent }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Layout.leftMargin: 2
                            spacing: Theme.space1
                            Text {
                                Layout.fillWidth: true
                                text: cell.modelData.name
                                color: Theme.ink
                                font.family: Theme.fontSans
                                font.pixelSize: 13
                                font.weight: cell.isCurrent ? Font.DemiBold : Font.Medium
                                elide: Text.ElideRight
                            }
                            Text {
                                visible: cell.modelData.arctic
                                text: 'Follows the theme'
                                color: Theme.inkSubtle
                                font.family: Theme.fontSans
                                font.pixelSize: 12
                            }
                        }
                    }
                    FocusRing { targetRadius: Theme.radiusLg; shown: cell.keyboard }
                    MouseArea {
                        id: tileMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        enabled: !apply.running
                        onClicked: { grid.currentIndex = cell.index; picker.use(cell.modelData); }
                    }
                }
            }
            Text {
                anchors.centerIn: parent
                visible: !scan.running && grid.count === 0
                text: picker.items.length ? 'No wallpapers match “' + picker.query + '”' : 'No wallpapers yet. Choose a folder of pictures.'
                color: Theme.inkMuted
                font.family: Theme.fontSans
                font.pixelSize: 13
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space4
            ArcticSwitch {
                id: autoToggle
                text: 'Match colours to wallpaper'
                checked: picker.autoColors
                enabled: !autoSwitch.running && !apply.running
                onToggled: {
                    picker.setAutoColors(checked);
                    checked = Qt.binding(() => picker.autoColors);
                }
                Keys.onEscapePressed: picker.close()
            }
            Text {
                Layout.fillWidth: true
                text: picker.status || (picker.folderExists ? 'Your pictures: ' + picker.folder.replace(Session.home, '~') : 'Add your own pictures to ~/Pictures/Wallpapers, or choose a folder.')
                color: picker.status ? Theme.ink : Theme.inkMuted
                font.family: Theme.fontSans
                font.pixelSize: 12
                elide: Text.ElideMiddle
            }
            Text {
                text: picker.filtered.length === 1 ? '1 wallpaper' : picker.filtered.length + ' wallpapers'
                color: Theme.inkSubtle
                font.family: Theme.fontSans
                font.pixelSize: 12
            }
        }
    }
}
