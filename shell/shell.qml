import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

ShellRoot {
    id: root
    property var items: []
    property var selected: null
    property string current: ''
    property string applyingPath: ''
    property string status: 'Loading your wallpapers…'
    property string query: ''
    property string folder: ''
    readonly property var filtered: items.filter(item => item.name.toLowerCase().includes(query.toLowerCase()))
    readonly property string helper: Quickshell.env('HOME') + '/.config/quickshell/scripts/wallpapers.py'
    function refresh() { if (!scan.running && !apply.running) scan.running = true; }
    Process {
        id: scan
        command: [root.helper, 'list']
        running: true
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const result = JSON.parse(text);
                    if (!result.items) { root.status = result.error; return; }
                    root.items = result.items;
                    root.folder = result.folder;
                    root.current = result.current;
                    root.selected = root.items.find(item => item.path === root.current) || root.items[0] || null;
                    root.status = root.items.length ? '' : 'No images found in ' + result.folder;
                } catch (e) { root.status = 'Could not load your wallpaper collection.'; }
            }
        }
    }
    Process {
        id: apply
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const result = JSON.parse(text);
                    if (result.ok || result.applied) root.current = root.applyingPath;
                    root.status = result.ok ? '' : result.error;
                    if (result.ok) panel.visible = false;
                } catch (e) { root.status = 'Could not apply wallpaper. Please try again.'; }
            }
        }
    }
    Process {
        id: changeFolder
        stdout: StdioCollector {
            onStreamFinished: {
                try { const result = JSON.parse(text); if (result.ok) root.refresh(); else root.status = result.error; }
                catch (e) { root.status = 'Could not open that folder.'; }
            }
        }
    }
    IpcHandler {
        target: 'wallpapers'
        function toggle(): void { panel.visible = !panel.visible; if (panel.visible) root.refresh(); }
        function open(): void { panel.visible = true; root.refresh(); }
    }
    Variants {
        model: Quickshell.screens
        ScreenFrame { required property var modelData; screen: modelData }
    }
    AppBar {
        onWallpapersRequested: { panel.visible = !panel.visible; if (panel.visible) root.refresh(); }
    }
    PanelWindow {
        id: panel
        visible: false
        anchors { top: true; left: true }
        DockPosition {
            id: wallpaperDock
            screenWidth: panel.screen.width
            screenHeight: panel.screen.height
            widgetWidth: panel.width
            widgetHeight: panel.height
        }
        onVisibleChanged: if (visible) wallpaperSurface.popIn()
        margins.left: wallpaperDock.animatedX
        margins.top: wallpaperDock.animatedY
        implicitWidth: Math.min(960, screen.width - 48)
        implicitHeight: Math.min(700, screen.height - 80)
        color: 'transparent'
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.namespace: 'quickshell-wallpapers'
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.OnDemand
        FolderDialog {
            id: folderDialog
            title: 'Choose your wallpaper folder'
            currentFolder: 'file://' + root.folder
            onAccepted: { changeFolder.command = [root.helper, 'folder', selectedFolder.toString()]; changeFolder.running = true; }
        }
        PopupSurface {
            id: wallpaperSurface
            dockEdge: wallpaperDock.edge
            anchors.fill: parent
            color: Theme.background
            radius: Theme.radius + 4
            border.width: 0
            focus: true
            Keys.onEscapePressed: panel.visible = false
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 24
                spacing: Theme.gap
                DragHandle {
                    Layout.fillWidth: true
                    windowX: panel.margins.left
                    windowY: panel.margins.top
                    onMoved: (nextX, nextY) => wallpaperDock.moveTo(nextX, nextY)
                }
                RowLayout {
                    Layout.fillWidth: true
                    ColumnLayout {
                        spacing: 4
                        Text { text: 'Wallpapers'; color: Theme.text; font.family: Theme.font; font.pixelSize: 26; font.weight: Font.DemiBold }
                    }
                    Item { Layout.fillWidth: true }
                    PickerButton { text: 'Folder…'; enabled: !apply.running && !changeFolder.running; onClicked: folderDialog.open() }
                    PickerButton { text: 'Refresh'; enabled: !scan.running && !apply.running; onClicked: root.refresh() }
                    PickerButton { text: 'Close'; onClicked: panel.visible = false }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 24
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: 12
                        TextField {
                            id: search
                            Layout.fillWidth: true
                            implicitHeight: 40
                            placeholderText: 'Search wallpapers'
                            placeholderTextColor: Theme.muted
                            color: Theme.text
                            font.family: Theme.font
                            font.pixelSize: 13
                            leftPadding: 12
                            onTextChanged: root.query = text
                            background: Rectangle { radius: 8; color: Theme.surface; border.width: search.activeFocus ? 1 : 0; border.color: Theme.accent }
                        }
                        GridView {
                            id: grid
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true
                            cellWidth: width / Math.max(1, Math.floor(width / 165))
                            cellHeight: cellWidth * 0.625 + 40
                            model: root.filtered
                            keyNavigationEnabled: true
                            ScrollBar.vertical: ScrollBar {}
                            delegate: Item {
                                required property var modelData
                                required property int index
                                width: grid.cellWidth
                                height: grid.cellHeight
                                Button {
                                    id: tile
                                    anchors.fill: parent
                                    anchors.rightMargin: 10
                                    anchors.bottomMargin: 10
                                    enabled: !apply.running
                                    hoverEnabled: true
                                    onClicked: {
                                        root.selected = modelData;
                                        grid.currentIndex = index;
                                        root.applyingPath = modelData.path;
                                        root.status = 'Applying…';
                                        apply.command = [root.helper, 'apply', modelData.path];
                                        apply.running = true;
                                    }
                                    background: Rectangle {
                                        radius: 8
                                        color: tile.hovered ? Qt.lighter(Theme.surface, 1.3) : Theme.surface
                                        border.width: root.selected && root.selected.path === modelData.path || tile.activeFocus ? 2 : 0
                                        border.color: Theme.accent
                                    }
                                    contentItem: Column {
                                        spacing: 8
                                        Image { width: parent.width; height: width * 0.625; source: modelData.thumb; asynchronous: true; fillMode: Image.PreserveAspectCrop }
                                        Text { width: parent.width; text: (root.current === modelData.path ? '✓  ' : '') + modelData.name; elide: Text.ElideRight; color: Theme.text; font.family: Theme.font; font.pixelSize: 11 }
                                    }
                                    padding: 6
                                    ToolTip.visible: hovered
                                    ToolTip.text: modelData.name
                                }
                            }
                            Text { anchors.centerIn: parent; visible: !scan.running && grid.count === 0; text: root.items.length ? 'No matching wallpapers' : 'Your collection is empty'; color: Theme.muted; font.family: Theme.font }
                        }
                        Text { text: root.filtered.length + ' wallpapers'; color: Theme.muted; font.family: Theme.font; font.pixelSize: 11 }
                    }
                }

                Text {
                    Layout.fillWidth: true
                    visible: root.status.length > 0
                    text: root.status
                    wrapMode: Text.Wrap
                    color: Theme.muted
                    font.family: Theme.font
                    font.pixelSize: 12
                }
            }
        }
    }
}
