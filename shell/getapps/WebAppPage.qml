pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import ".."

// Get apps → Web apps: any website as an app, with its own window, icon and sign-in (the
// arctic-webapp engine, through AppsService.web). Type or paste an address: the engine looks at
// the site after a pause (Enter looks now) and offers its name and icons; Add puts it in the
// launcher. The engine's own sentences are shown as they come. Only offered when arctic-webapp
// is installed. Keys: Enter looks at the site or adds the app, Ctrl+Enter adds it, Esc stops a
// running look, then clears the address, then goes back.
FocusScope {
    id: page
    property string initialQuery: ''
    property int request: 0                         // the Inspect running (0: none)
    property string status: ''
    property var preview: null
    property string error: ''
    property string errorCode: ''
    property string inspected: ''                   // the address the preview is for
    property int icon: 0
    property string runtime: 'webkit'
    property bool newCopy: false
    property bool adding: false
    property var added: null                        // the app Install made
    readonly property var runtimes: AppsService.web.runtimes.filter(r => r.available)
    readonly property Item inputItem: field
    signal backRequested()
    signal closeRequested()

    function back() {
        if (request) { AppsService.web.cancel(request); request = 0; status = ''; return true; }
        if (added) { reset(); return true; }
        if (field.text) { field.text = ''; reset(); return true; }
        return false;
    }
    function reset() {
        preview = null; added = null; error = ''; errorCode = ''; status = ''; inspected = ''; newCopy = false; adding = false;
    }
    function inspect() {
        const url = field.text.trim();
        pause.stop();
        if (!url || (url === inspected && (preview || request))) return;
        if (request) AppsService.web.cancel(request);
        preview = null; added = null; error = ''; errorCode = '';
        inspected = url;
        status = 'Looking at ' + url + '…';
        const id = AppsService.web.inspect(url, (result, err) => {
            if (page.request !== id) return;
            page.request = 0;
            page.status = '';
            if (err) { page.error = err.message; page.errorCode = err.code || ''; return; }
            page.preview = result;
            page.icon = result.recommended_icon || 0;
            page.runtime = page.runtimes.some(r => r.id === result.suggested_runtime) ? result.suggested_runtime : 'webkit';
            nameField.text = result.name || result.host || '';
            page.newCopy = false;
        });
        request = id;
    }
    function add(params) {
        if (adding) return;
        adding = true;
        error = '';
        const p = params || { token: preview.token, name: nameField.text.trim() || preview.name, icon: icon, runtime: runtime,
                              links: linksSwitch.checked ? 'browser' : 'app', launch: false };
        if (!params && newCopy) p.new_copy = true;
        AppsService.web.install(p, (result, err) => {
            page.adding = false;
            if (err) { page.error = err.message; page.errorCode = err.code || ''; return; }
            page.added = result.app;
            page.preview = null;
        });
    }
    function accept(ctrl) {
        if (added) { launch(added.id); return; }
        if (preview && (ctrl || field.text.trim() === inspected)) { if (!preview.installed || !preview.installed.length || newCopy) add(); return; }
        inspect();
    }
    function launch(id) {
        AppsService.web.launch(id, (result, err) => { if (err) page.error = err.message; else page.closeRequested(); });
    }

    Component.onCompleted: {
        AppsService.web.start();
        field.text = initialQuery;
        if (initialQuery) inspect();
    }
    Timer { id: pause; interval: 600; onTriggered: page.inspect() }
    Connections {
        target: AppsService.web
        function onProgress(req, stage, message) { if (req === page.request && message) page.status = message; }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.space3

        PageHeader { title: 'Web apps'; onBack: page.backRequested() }
        Text {
            Layout.fillWidth: true
            visible: AppsService.sourcesLoaded && !AppsService.webappPresent
            text: 'Web apps need the web-app engine (the arctic-webapps package). Install it from Fedora packages.'
            color: Theme.inkMuted
            font.family: Theme.fontSans
            font.pixelSize: 13
            wrapMode: Text.Wrap
        }
        ArcticField {
            id: field
            Layout.fillWidth: true
            focus: true
            iconName: 'globe'
            placeholderText: 'Website address, like music.youtube.com'
            inputMethodHints: Qt.ImhUrlCharactersOnly | Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase
            onTextEdited: { if (page.added) page.added = null; if (text.trim()) pause.restart(); else { pause.stop(); if (page.request) AppsService.web.cancel(page.request); page.request = 0; page.reset(); } }
            Keys.onReturnPressed: event => page.accept(event.modifiers & Qt.ControlModifier)
            Keys.onEnterPressed: event => page.accept(event.modifiers & Qt.ControlModifier)
        }
        Text {
            Layout.fillWidth: true
            text: 'It opens in its own window with its own sign-in, separate from your browser.'
            color: Theme.inkMuted
            font.family: Theme.fontSans
            font.pixelSize: 12
            wrapMode: Text.Wrap
        }
        RowLayout {
            visible: page.status !== ''
            spacing: Theme.space2
            Icon { name: 'clock'; size: 14; color: Theme.inkMuted }
            Text { text: page.status; color: Theme.inkMuted; font.family: Theme.fontSans; font.pixelSize: 13 }
        }
        RowLayout {
            Layout.fillWidth: true
            visible: page.error !== ''
            spacing: Theme.space2
            Icon { Layout.alignment: Qt.AlignTop; name: 'x-circle'; size: 16; color: Theme.error }
            Text { Layout.fillWidth: true; text: page.error; color: Theme.error; font.family: Theme.fontSans; font.pixelSize: 13; wrapMode: Text.Wrap }
            ArcticButton {
                visible: page.errorCode === 'offline' && page.inspected !== ''
                variant: 'secondary'; size: 'sm'
                text: 'Add with a letter icon'
                onClicked: page.add({ url: page.inspected, icon: 'monogram', launch: false })
            }
        }

        // ---- the preview ----
        Rectangle {
            Layout.fillWidth: true
            visible: page.preview !== null
            implicitHeight: previewColumn.implicitHeight + 2 * Theme.space4
            radius: Theme.radiusLg
            color: Theme.surfaceRaised
            border.width: 1
            border.color: Theme.line
            ColumnLayout {
                id: previewColumn
                anchors.fill: parent
                anchors.margins: Theme.space4
                spacing: Theme.space3
                RowLayout {
                    spacing: Theme.space2
                    Repeater {
                        model: page.preview ? page.preview.icons.slice(0, 6) : []
                        delegate: Rectangle {
                            id: choice
                            required property var modelData
                            readonly property bool selected: page.icon === modelData.index
                            implicitWidth: 56
                            implicitHeight: 56
                            radius: Theme.radiusMd
                            color: selected ? Theme.accentSoft : Theme.surface
                            border.width: 1
                            border.color: selected ? Theme.accentEdge : Theme.line
                            activeFocusOnTab: true
                            Accessible.role: Accessible.RadioButton
                            Accessible.name: 'Icon ' + (modelData.index + 1)
                            Keys.onSpacePressed: page.icon = modelData.index
                            FocusRing { targetRadius: Theme.radiusMd; shown: choice.activeFocus }
                            AppTile {
                                anchors.centerIn: parent
                                size: 44
                                color: 'transparent'
                                imageSource: choice.modelData.path || ''
                                fallbackGlyph: 'globe'
                            }
                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: page.icon = choice.modelData.index }
                        }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space3
                    Text { text: 'Name'; color: Theme.inkMuted; font.family: Theme.fontSans; font.pixelSize: 13; Layout.preferredWidth: 90 }
                    ArcticField { id: nameField; Layout.fillWidth: true; maximumLength: 64 }
                }
                RowLayout {
                    Layout.fillWidth: true
                    visible: page.runtimes.length > 1
                    spacing: Theme.space3
                    Text { text: 'Open with'; color: Theme.inkMuted; font.family: Theme.fontSans; font.pixelSize: 13; Layout.preferredWidth: 90 }
                    Segmented {
                        model: page.runtimes.map(r => ({ key: r.id, label: r.id === 'webkit' ? r.name + ' (built in)' : r.name }))
                        current: page.runtime
                        onActivated: key => page.runtime = key
                    }
                }
                ArcticSwitch { id: linksSwitch; text: 'Open other sites in your browser'; checked: true }
                Repeater {
                    model: page.preview ? page.preview.warnings || [] : []
                    delegate: RowLayout {
                        id: warning
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: Theme.space2
                        Icon { Layout.alignment: Qt.AlignTop; name: 'alert'; size: 16; color: Theme.warning }
                        Text { Layout.fillWidth: true; text: warning.modelData.message; color: Theme.warning; font.family: Theme.fontSans; font.pixelSize: 13; wrapMode: Text.Wrap }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    visible: !!(page.preview && page.preview.installed && page.preview.installed.length) && !page.newCopy
                    spacing: Theme.space2
                    Icon { name: 'info'; size: 16; color: Theme.info }
                    Text { Layout.fillWidth: true; text: 'You already have this web app.'; color: Theme.ink; font.family: Theme.fontSans; font.pixelSize: 13 }
                    ArcticButton { variant: 'secondary'; size: 'sm'; text: 'Open it'; onClicked: page.launch(page.preview.installed[0].id || page.preview.installed[0]) }
                    ArcticButton { variant: 'ghost'; size: 'sm'; text: 'Add a second copy'; onClicked: page.newCopy = true }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Item { Layout.fillWidth: true }
                    Kbd { text: 'Ctrl + Enter' }
                    ArcticButton {
                        variant: 'primary'
                        enabled: !page.adding && (!(page.preview && page.preview.installed && page.preview.installed.length) || page.newCopy)
                        text: page.adding ? 'Adding…' : 'Add ' + (nameField.text.trim() || (page.preview ? page.preview.name : ''))
                        onClicked: page.add()
                    }
                }
            }
        }

        // ---- done ----
        ColumnLayout {
            Layout.fillWidth: true
            visible: page.added !== null
            spacing: Theme.space3
            RowLayout {
                spacing: Theme.space2
                Icon { name: 'check-circle'; size: 18; color: Theme.success }
                Text {
                    text: page.added ? page.added.name + ' is in the launcher.' : ''
                    color: Theme.ink
                    font.family: Theme.fontSans
                    font.pixelSize: 15
                    font.weight: Font.DemiBold
                }
            }
            RowLayout {
                spacing: Theme.space2
                ArcticButton { variant: 'primary'; text: page.added ? 'Open ' + page.added.name : ''; onClicked: page.launch(page.added.id) }
                ArcticButton { variant: 'ghost'; text: 'Add another'; onClicked: { field.text = ''; page.reset(); field.forceActiveFocus(); } }
            }
        }
        Item { Layout.fillHeight: true }
        Text {
            Layout.fillWidth: true
            visible: Session.live
            text: 'Web apps you add here are gone after a restart.'
            color: Theme.info
            font.family: Theme.fontSans
            font.pixelSize: 12
        }
    }
}
