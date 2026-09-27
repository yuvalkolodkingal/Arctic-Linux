import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

PanelWindow {
    id: bar
    signal wallpapersRequested()
    anchors { top: true; left: true; right: true }
    implicitHeight: Theme.barHeight
    color: Theme.background
    WlrLayershell.namespace: 'quickshell-bar'
    WlrLayershell.layer: WlrLayer.Top
    property string searchText: ''
    property string category: ''
    readonly property var categories: [
        { name: 'Install', icon: 'system-software-install', genericName: '', isCategory: true },
        { name: 'Apps', icon: 'applications-other', genericName: '', isCategory: true },
        { name: 'Fetch', icon: 'utilities-terminal', genericName: 'Fastfetch', action: 'fetch' }
    ]
    readonly property var apps: {
        const entries = category === '' ? categories : category === 'Apps' ? DesktopEntries.applications.values : [];
        const query = searchText.trim().toLowerCase();
        const matches = entries.filter(app => !query || (app.name + ' ' + (app.genericName || '') + ' ' + (app.keywords ? app.keywords.join(' ') : '')).toLowerCase().includes(query));
        return category === 'Apps' ? matches.sort((a, b) => a.name.localeCompare(b.name)) : matches;
    }
    function goBack() { category = ''; search.clear(); appList.currentIndex = 0; search.forceActiveFocus(); }
    function toggleApps() { launcher.visible = !launcher.visible; }
    function launch(app) {
        if (!app) return;
        if (app.action === 'fetch') {
            Quickshell.execDetached([Quickshell.env('HOME') + '/.local/bin/kitty', '--hold', '-e', Quickshell.env('HOME') + '/.local/bin/fastfetch']);
            launcher.visible = false;
            return;
        }
        if (app.isCategory) {
            category = app.name;
            search.clear();
            appList.currentIndex = 0;
            if (category === 'Install') installConsole.open(); else search.forceActiveFocus();
            return;
        }
        if (app.runInTerminal) {
            Quickshell.execDetached({command: ['kitty', '-e'].concat(app.command), workingDirectory: app.workingDirectory || Quickshell.env('HOME')});
        } else {
            app.execute();
        }
        launcher.visible = false;
    }
    IpcHandler {
        target: 'apps'
        function toggle(): void { bar.toggleApps(); }
        function open(): void { launcher.visible = true; }
        function install(): void { launcher.visible = true; bar.launch(bar.categories[0]); }
    }
    SystemClock { id: clock; precision: SystemClock.Minutes }
    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 12
        anchors.rightMargin: 16
        spacing: 8
        Workspaces { monitorName: bar.screen.name }
        Item { Layout.fillWidth: true }
        Text { text: Qt.formatDateTime(clock.date, 'ddd, d MMM'); color: Theme.muted; font.family: Theme.font; font.pixelSize: 12 }
        Text { Layout.leftMargin: 12; text: Qt.formatDateTime(clock.date, 'hh:mm'); color: Theme.text; font.family: Theme.font; font.pixelSize: 13; font.weight: Font.Medium }
    }
    PopupWindow {
        id: launcher
        anchor.window: bar
        DockPosition {
            id: launcherDock
            screenWidth: bar.screen.width
            screenHeight: bar.screen.height
            widgetWidth: launcher.width
            widgetHeight: launcher.height
        }
        anchor.rect.x: launcherDock.animatedX
        anchor.rect.y: launcherDock.animatedY
        implicitWidth: Math.min(bar.category === 'Install' ? 720 : 560, bar.screen.width - 32)
        implicitHeight: Math.min(600, bar.screen.height - bar.height - 32)
        color: 'transparent'
        grabFocus: true
        onVisibleChanged: {
            if (visible) { launcherSurface.popIn(); bar.category = ''; search.clear(); appList.currentIndex = 0; search.forceActiveFocus(); }
        }
        PopupSurface {
            id: launcherSurface
            dockEdge: launcherDock.edge
            anchors.fill: parent
            radius: 8
            color: Theme.background
            border.width: 0
            Keys.onEscapePressed: { if (bar.category) bar.goBack(); else launcher.visible = false; }
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 12
                spacing: 8
                DragHandle {
                    Layout.fillWidth: true
                    windowX: launcher.anchor.rect.x
                    windowY: launcher.anchor.rect.y
                    onMoved: (nextX, nextY) => launcherDock.moveTo(nextX, nextY)
                }
                InstallConsole {
                    id: installConsole
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: bar.category === 'Install'
                    onBackRequested: bar.goBack()
                }
                RowLayout {
                    visible: bar.category !== 'Install'
                    Layout.fillWidth: true
                    spacing: 8
                    PickerButton {
                        visible: bar.category !== ''
                        text: 'Back'
                        onClicked: bar.goBack()
                    }
                    TextField {
                        id: search
                        Layout.fillWidth: true
                        implicitHeight: 40
                        placeholderText: bar.category ? 'Search ' + bar.category.toLowerCase() : 'Search'
                        placeholderTextColor: Theme.muted
                        color: Theme.text
                        font.family: Theme.font
                        font.pixelSize: 14
                        selectByMouse: true
                        onTextChanged: { bar.searchText = text; appList.currentIndex = 0; }
                        onAccepted: bar.launch(bar.apps[appList.currentIndex])
                        Keys.onDownPressed: appList.incrementCurrentIndex()
                        Keys.onUpPressed: appList.decrementCurrentIndex()
                        background: Item {}
                    }
                    Text { text: bar.apps.length; color: Theme.muted; font.family: Theme.font; font.pixelSize: 11 }
                }
                Rectangle { visible: bar.category !== 'Install'; Layout.fillWidth: true; height: 1; color: Theme.surface }
                ListView {
                    id: appList
                    visible: bar.category !== 'Install'
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: bar.apps
                    spacing: 2
                    keyNavigationWraps: true
                    highlightMoveDuration: 0
                    ScrollBar.vertical: ScrollBar {}
                    delegate: Button {
                        id: appRow
                        required property var modelData
                        required property int index
                        readonly property bool selected: appList.currentIndex === index
                        width: appList.width
                        height: 38
                        hoverEnabled: true
                        focusPolicy: Qt.NoFocus
                        onHoveredChanged: if (hovered) appList.currentIndex = index
                        onClicked: bar.launch(modelData)
                        background: Rectangle {
                            radius: 4
                            color: appRow.selected ? Theme.accent : appRow.index % 2 ? Theme.surface : 'transparent'
                            opacity: appRow.down ? 0.8 : 1
                        }
                        contentItem: RowLayout {
                            spacing: 12
                            Item {
                                Layout.preferredWidth: 24
                                Layout.preferredHeight: 24
                                Image {
                                    id: icon
                                    anchors.fill: parent
                                    source: modelData.icon ? Quickshell.iconPath(modelData.icon, true) : ''
                                    sourceSize.width: 24; sourceSize.height: 24
                                    fillMode: Image.PreserveAspectFit
                                }
                                Text {
                                    anchors.centerIn: parent
                                    visible: icon.status !== Image.Ready
                                    text: modelData.name.charAt(0).toUpperCase()
                                    color: appRow.selected ? '#111318' : Theme.accent
                                    font.family: Theme.font
                                    font.pixelSize: 16
                                }
                            }
                            Text {
                                Layout.fillWidth: true
                                text: modelData.name
                                color: appRow.selected ? '#111318' : Theme.text
                                font.family: Theme.font
                                font.pixelSize: 13
                                elide: Text.ElideRight
                            }
                            Text {
                                Layout.maximumWidth: 200
                                text: modelData.genericName
                                color: appRow.selected ? '#303238' : Theme.muted
                                font.family: Theme.font
                                font.pixelSize: 11
                                elide: Text.ElideRight
                            }
                        }
                        leftPadding: 10
                        rightPadding: 12
                    }

                }
            }
        }
    }
}
