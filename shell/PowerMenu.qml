pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io

// The power menu (design Menu), under the bar's power item or from Super + Esc.
// Items name what will happen. Settings comes first (the system menu is where people look for
// it); on the live USB there is nothing to lock or log out of, so Restart and Shut down follow.
// The actions run `arctic-power <action>`; Settings runs `arctic-settings`.
// Hibernate and "Restart into firmware setup" show only when logind says this computer can
// (`arctic-power can --json`, asked each time the menu opens). Log out, Restart and Shut down
// close the windows first and ask when one stays open (arctic-power prepare). Rows and keys are
// the bar menus' (MenuList, MenuRow): arrows, Home/End, a letter jumps, Enter runs, Esc closes.
Popover {
    id: menu
    required property var shell
    property bool canHibernate: false
    property bool canFirmware: false
    readonly property var actions: base.filter(a => a.id !== 'hibernate' || canHibernate)
        .concat(canFirmware && !Session.live ? [{ id: 'firmware', label: 'Restart into firmware', icon: 'cpu' }] : [])
    readonly property var base: Session.live
        ? [ { id: 'settings', label: 'Settings', icon: 'sliders', keys: 'Super + S' },
            { id: 'restart', label: 'Restart', icon: 'restart' },
            { id: 'poweroff', label: 'Shut down', icon: 'power' } ]
        : [ { id: 'settings', label: 'Settings', icon: 'sliders', keys: 'Super + S' },
            { id: 'lock', label: 'Lock screen', icon: 'lock', keys: 'Super + L' },
            { id: 'logout', label: 'Log out', icon: 'log-out' },
            { id: 'suspend', label: 'Suspend', icon: 'sleep' },
            { id: 'hibernate', label: 'Hibernate', icon: 'sleep' },
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
    onOpened: {
        MenuState.keyboardNav = true;
        Qt.callLater(() => list.start());
        can.running = true;
    }
    Process {
        id: can
        command: ['arctic-power', 'can', '--json']
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const r = JSON.parse(text);
                    menu.canHibernate = r.hibernate === true;
                    menu.canFirmware = r.firmware === true;
                } catch (e) {}
                // New rows replace the old ones: put the keyboard back on the first.
                Qt.callLater(() => { if (menu.open && list.currentIn(list.stops()) < 0) list.start(); });
            }
        }
    }

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
