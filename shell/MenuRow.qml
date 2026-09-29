import QtQuick
import QtQuick.Layouts

// One row of a bar menu (design Menu item): 34px, 44px with a detail line; radius-sm, 18px icon,
// 15px label, 12px detail in ink-muted. Hover and the keyboard's current row are surface-sunken.
// `selected` is the current choice (the connected network, the default output): accent-soft
// with a 1px accent edge and a check — never colour alone. `errorText` adds a line under the
// label saying what went wrong. Enter, Space or a click activate; right click, the Menu key or
// Shift+F10 ask for the row's actions (`secondary`); Right opens a row with a chevron.
Item {
    id: row
    property string icon: ''
    property string iconBase: ''        // drawn under `icon` in ink-disabled (signal meters)
    property color iconColor: destructive ? Theme.error : Theme.ink
    property string image: ''           // a picture (app icon) instead of a glyph
    property string label: ''
    property string detail: ''
    property string errorText: ''
    property string trailing: ''        // '', check, lock, chevron, external, spinner, kbd, text, dots
    property string trailingText: ''
    property string kbd: ''
    property bool selected: false
    property string toggle: ''          // 'checkbox' or 'radio' (tray menus): drawn with `checked`
    property bool checked: false
    property bool busy: false
    property bool destructive: false
    property int labelWeight: Font.Normal
    readonly property bool menuStop: true
    readonly property bool highlighted: enabled && (mouse.containsMouse || (activeFocus && MenuState.keyboardNav))
    signal activated()
    signal secondary()
    signal deleteRequested()

    Layout.fillWidth: true
    implicitWidth: layout.implicitWidth + 2 * Theme.space3
    implicitHeight: Math.max(detail !== '' || errorText !== '' ? 44 : 34, layout.implicitHeight + 2 * 6)
    Accessible.role: Accessible.MenuItem
    Accessible.name: label
    Accessible.description: errorText || detail
    Accessible.checked: selected || checked

    Keys.onPressed: event => {
        MenuState.keyboardNav = true;
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
            if (row.enabled) row.activated();
        } else if (event.key === Qt.Key_Menu || (event.key === Qt.Key_F10 && (event.modifiers & Qt.ShiftModifier))) {
            row.secondary();
        } else if (event.key === Qt.Key_Right && row.trailing === 'chevron') {
            row.activated();
        } else if (event.key === Qt.Key_Delete) {
            row.deleteRequested();
        } else {
            return;
        }
        event.accepted = true;
    }

    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusSm
        color: row.selected ? Theme.accentSoft : row.highlighted ? Theme.surfaceSunken : 'transparent'
        border.width: row.selected ? (row.highlighted && row.activeFocus && MenuState.keyboardNav ? 2 : 1) : 0
        border.color: row.highlighted && row.activeFocus && MenuState.keyboardNav ? Theme.focus : Theme.accentEdge
        Behavior on color { ColorAnimation { duration: Theme.durationFast } }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        enabled: row.enabled
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        cursorShape: Qt.PointingHandCursor
        onPositionChanged: MenuState.keyboardNav = false
        onClicked: m => {
            MenuState.keyboardNav = false;
            if (m.button === Qt.RightButton) row.secondary();
            else row.activated();
        }
    }
    RowLayout {
        id: layout
        anchors.fill: parent
        anchors.leftMargin: Theme.space3
        anchors.rightMargin: Theme.space3
        spacing: Theme.space2 + 2
        Item {
            visible: row.icon !== '' || row.image !== ''
            Layout.preferredWidth: 18
            Layout.preferredHeight: 18
            Layout.alignment: Qt.AlignVCenter
            Icon {
                visible: row.iconBase !== ''
                name: row.iconBase || 'help'
                size: 18
                color: Theme.inkDisabled
            }
            Icon {
                visible: row.icon !== '' && row.image === ''
                name: row.icon || 'help'
                size: 18
                color: row.enabled ? row.iconColor : Theme.inkDisabled
            }
            Image {
                visible: row.image !== ''
                anchors.fill: parent
                source: row.image
                sourceSize: Qt.size(18, 18)
                fillMode: Image.PreserveAspectFit
                asynchronous: true
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
            spacing: 1
            Text {
                Layout.fillWidth: true
                text: row.label
                textFormat: Text.PlainText
                elide: Text.ElideRight
                color: !row.enabled ? Theme.inkDisabled : row.destructive ? Theme.error : Theme.ink
                font.family: Theme.fontSans
                font.pixelSize: 15
                font.weight: row.labelWeight
            }
            Text {
                Layout.fillWidth: true
                visible: row.detail !== '' && row.errorText === ''
                text: row.detail
                textFormat: Text.PlainText
                elide: Text.ElideRight
                color: row.enabled ? Theme.inkMuted : Theme.inkDisabled
                font.family: Theme.fontSans
                font.pixelSize: 12
                font.features: { 'tnum': 1 }
            }
            Text {
                Layout.fillWidth: true
                visible: row.errorText !== ''
                text: row.errorText
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                color: Theme.error
                font.family: Theme.fontSans
                font.pixelSize: 12
                lineHeight: 1.2
            }
        }
        // A tray menu's check box or radio item.
        Rectangle {
            visible: row.toggle !== ''
            Layout.preferredWidth: 16
            Layout.preferredHeight: 16
            radius: row.toggle === 'radio' ? 8 : Theme.radiusXs
            color: 'transparent'
            border.width: 1.5
            border.color: row.enabled ? Theme.lineStrong : Theme.line
            Icon {
                visible: row.toggle === 'checkbox' && row.checked
                anchors.centerIn: parent
                name: 'check'
                size: 14
                color: row.enabled ? Theme.ink : Theme.inkDisabled
            }
            Rectangle {
                visible: row.toggle === 'radio' && row.checked
                anchors.centerIn: parent
                width: 8
                height: 8
                radius: 4
                color: row.enabled ? Theme.ink : Theme.inkDisabled
            }
        }
        Spinner {
            visible: row.busy || row.trailing === 'spinner'
            running: visible
        }
        Icon {
            readonly property string glyph: row.selected && row.trailing === '' ? 'check'
                : ['check', 'lock', 'chevron', 'external'].indexOf(row.trailing) >= 0 ? (row.trailing === 'chevron' ? 'chevron-right' : row.trailing) : ''
            visible: glyph !== '' && !row.busy
            name: glyph || 'help'
            size: glyph === 'lock' ? 14 : 16
            color: glyph === 'check' && row.selected ? Theme.accentText : Theme.inkMuted
        }
        Kbd {
            visible: row.kbd !== '' || row.trailing === 'kbd'
            text: row.kbd || row.trailingText
        }
        Text {
            visible: row.trailing === 'text'
            text: row.trailingText
            textFormat: Text.PlainText
            color: Theme.inkMuted
            font.family: Theme.fontSans
            font.pixelSize: 13
            font.features: { 'tnum': 1 }
        }
        // "More actions" for rows whose right click opens a page (discoverable with a pointer).
        Rectangle {
            visible: row.trailing === 'dots'
            Layout.preferredWidth: 26
            Layout.preferredHeight: 26
            radius: Theme.radiusSm
            color: dotsMouse.containsMouse ? Theme.line : 'transparent'
            Icon { anchors.centerIn: parent; name: 'dots'; size: 16; color: Theme.inkMuted }
            MouseArea {
                id: dotsMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: row.secondary()
            }
        }
    }
}
