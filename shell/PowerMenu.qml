pragma ComponentBehavior: Bound
import QtQuick
import Quickshell

// The power menu (design Menu), under the bar's power item or from Super + Esc.
// Items name what will happen. Settings comes first (the system menu is where people look for
// it); on the live USB there is nothing to lock or log out of, so Restart and Shut down follow.
// The actions run `arctic-power <action>`; Settings runs `arctic-settings`. Rows and keys are
// the bar menus' (MenuList, MenuRow): arrows, Home/End, a letter jumps, Enter runs, Esc closes.
Popover {
    id: menu
    required property var shell
    readonly property var actions: Session.live
        ? [ { id: 'settings', label: 'Settings', icon: 'sliders', keys: 'Super + S' },
            { id: 'restart', label: 'Restart', icon: 'restart' },
            { id: 'poweroff', label: 'Shut down', icon: 'power' } ]
        : [ { id: 'settings', label: 'Settings', icon: 'sliders', keys: 'Super + S' },
            { id: 'lock', label: 'Lock screen', icon: 'lock', keys: 'Super + L' },
            { id: 'logout', label: 'Log out', icon: 'log-out' },
            { id: 'suspend', label: 'Suspend', icon: 'sleep' },
            { id: 'restart', label: 'Restart', icon: 'restart' },
            { id: 'poweroff', label: 'Shut down', icon: 'power' } ]

    layerName: 'arctic-power'
    placement: 'point'
    scrim: false
    cardColor: Theme.surfaceRaised
    cardRadius: Theme.radiusLg
    shadow: 2
    cardWidth: 232
    cardHeight: list.implicitHeight
    focusItem: list
    // The first row is highlighted on open, from the keyboard (Super + Esc) or a click, as before.
    onOpened: { MenuState.keyboardNav = true; Qt.callLater(() => list.start()); }

    function run(action) {
        close();
        if (action.id === 'lock') shell.lock();
        else if (action.id === 'settings') Quickshell.execDetached(['arctic-settings']);
        else Quickshell.execDetached(['arctic-power', action.id]);
    }

    MenuList {
        id: list
        anchors.fill: parent
        focus: true
        Repeater {
            model: menu.actions
            MenuRow {
                required property var modelData
                icon: modelData.icon
                label: modelData.label
                kbd: modelData.keys || ''
                onActivated: menu.run(modelData)
            }
        }
    }
}
