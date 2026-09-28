import QtQml

// One switch of the toggle registry (ToggleRegistry.qml): what a Quick Settings tile, the
// `toggle` IPC target and the mode indicators left of the clock all read. `setter(on)` does
// the change; `kind: 'cycle'` tiles (power mode) step instead of switching and are never
// "checked". A toggle that isn't `available` (its helper or device is missing) is hidden
// and answers "unavailable" over IPC.
QtObject {
    property string key: ''
    property string label: ''
    property string icon: 'help'
    property string iconOff: ''
    property bool available: false
    property bool active: false
    property string detail: active ? 'On' : 'Off'
    property bool busy: false
    property string kind: 'switch'      // switch, cycle
    property string page: ''            // Quick Settings page behind the tile's chevron
    property bool indicator: false      // shown left of the clock while `indicatorShown`
    property bool indicatorShown: indicator && active
    property string indicatorText: label + ' is on · click to turn it off'
    property string indicatorOffText: label + ' is off · click to turn it on'   // shown dimmed on hover
    property string tone: 'normal'      // normal, warning, error (indicator pills)
    property string keys: ''            // shortcut for tooltips ("Super + Ctrl + N")
    property var setter: null           // function (on)

    function set(on) { if (available && setter) setter(on); }
    function toggle() { set(kind === 'cycle' ? true : !active); }
}
