// Displays: the arrangement (drag the screens; arrow keys move the selected one), the main
// display, resolution, refresh rate, scale, rotation and on/off of each.
// The page only draws: every move goes through the helper (display-arrange), which keeps the
// layout the way Mango needs it — every display touching another edge to edge, none
// overlapping, the top-left corner at 0,0 — and computes each display's size in the layout
// (logicalWidth/logicalHeight: the mode, turned for portrait, divided by the scale).
// Apply tries the layout at once (wlr-randr, through the helper) and asks "Keep these display
// settings?" for 15 seconds, like GNOME; without an answer it goes back, and a watchdog in the
// helper goes back after 20 seconds even if Settings itself is gone (a mode the screen can't
// show would otherwise leave it black). Kept layouts are saved as Mango monitorrule lines in
// settings.conf, so they hold after the next login.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Templates as T
import ".."
import "../components"

Page {
    id: page
    title: "Displays"
    lede: "Position, size and sharpness of each screen. You get 15 seconds to keep a change before it goes back."

    property var info: ({ outputs: [], arranged: [], rules: [], problems: [], backend: "", canApply: false, canChangeMode: false })
    property var edit: []
    property string selectedName: ""
    property bool trying: false
    property int countdown: 0
    // Moves go to the helper one at a time; only the newest answer counts.
    property int arrangeSeq: 0
    property bool arranging: false
    readonly property int selected: Math.max(0, edit.findIndex(o => o.name === selectedName))
    readonly property var output: edit.length > selected ? edit[selected] : null
    readonly property var original: output ? (info.outputs || []).find(o => o.name === output.name) || null : null
    readonly property int onCount: edit.filter(o => o.enabled).length
    readonly property bool dirty: edit.length > 0 && (!same(edit, info.arranged || []) || (info.problems || []).length > 0)
    readonly property var transforms: [{ value: "normal", label: "Normal" }, { value: "90", label: "Portrait (90°)" },
        { value: "180", label: "Upside down (180°)" }, { value: "270", label: "Portrait (270°)" },
        { value: "flipped", label: "Mirrored" }, { value: "flipped-90", label: "Mirrored, portrait (90°)" },
        { value: "flipped-180", label: "Mirrored, upside down" }, { value: "flipped-270", label: "Mirrored, portrait (270°)" }]
    readonly property var scales: [1, 1.25, 1.5, 1.75, 2, 2.5, 3]

    function same(a, b) {
        const keys = ["name", "enabled", "width", "height", "refresh", "x", "y", "scale", "transform", "adaptiveSync"];
        return a.length === b.length && a.every((o, i) => keys.every(k => o[k] === b[i][k]));
    }
    function load() {
        Backend.call(["displays"], r => {
            if (!r.ok)
                return;
            page.arrangeSeq++;
            page.arranging = false;
            page.info = r;
            page.edit = r.arranged || [];
            if (!page.edit.some(o => o.name === page.selectedName))
                page.selectedName = (page.edit.find(o => o.main) || page.edit[0] || { name: "" }).name;
        });
    }
    // One move of the editor (display-arrange), e.g. ["--nudge", "DP-1", "left"].
    function arrange(args) {
        const seq = ++arrangeSeq;
        arranging = true;
        Backend.call(["display-arrange", JSON.stringify(edit)].concat(args), r => {
            if (seq !== page.arrangeSeq)
                return;
            page.arranging = false;
            page.edit = r.ok ? r.outputs : page.edit.slice();
        });
    }
    // A control of the selected display changed; a new size moves the others round it.
    function change(values) {
        const list = edit.slice();
        list[selected] = Object.assign({}, list[selected], values);
        edit = list;
        if (values.width !== undefined || values.scale !== undefined || values.transform !== undefined)
            arrange(["--anchor", list[selected].name]);
    }
    // "150% · portrait" under a display's size in the arrangement.
    function describe(o) {
        const turned = { "90": "portrait", "270": "portrait", "180": "upside down", "flipped": "mirrored",
            "flipped-90": "mirrored portrait", "flipped-180": "mirrored, upside down", "flipped-270": "mirrored portrait" };
        const parts = [];
        if (o.scale && o.scale !== 1)
            parts.push(Math.round(o.scale * 100) + "%");
        if (turned[o.transform])
            parts.push(turned[o.transform]);
        return parts.join(" · ");
    }
    function modesOf(name) {
        const o = (info.outputs || []).find(x => x.name === name);
        return o ? o.modes : [];
    }
    function sizes(name) {
        const seen = {}, out = [];
        modesOf(name).slice().sort((a, b) => b.width * b.height - a.width * a.height).forEach(m => {
            const key = m.width + "x" + m.height;
            if (seen[key])
                return;
            seen[key] = true;
            out.push({ value: key, label: m.width + " × " + m.height + (m.preferred ? "  (best)" : "") });
        });
        return out;
    }
    function rates(name, w, h) {
        return modesOf(name).filter(m => m.width === w && m.height === h).sort((a, b) => b.refresh - a.refresh)
            .map(m => ({ value: String(m.refresh), label: (Math.round(m.refresh * 100) / 100) + " Hz" }));
    }
    function apply() {
        Backend.call(["display-try", JSON.stringify(edit)], r => {
            if (!r.ok) {
                page.load();
                return;
            }
            if (r.layout)
                page.edit = r.layout;
            page.trying = true;
            page.countdown = Math.max(5, (r.revertAfter || 20) - 5);
            tick.start();
            confirm.open();
        });
    }
    function keep() {
        tick.stop();
        confirm.close();
        page.trying = false;
        Backend.call(["display-keep"], r => {
            if (r.ok) {
                const off = r.sessionOnly || [];
                Backend.notify("success", off.length ? "Display settings kept. " + off.join(", ") + (off.length > 1 ? " stay" : " stays") + " off until you log out (it’s never saved as off, so no login starts on a dark screen)." : "Display settings kept", false);
                page.load();
                Backend.refresh();
            }
        });
    }
    function revert() {
        tick.stop();
        confirm.close();
        page.trying = false;
        Backend.call(["display-revert"], _r => page.load());
    }
    onShown: {
        if (!trying)
            load();
        loadNight();
    }

    // ---- Night light (arctic-nightlight runs wlsunset; its schedule is nightlight.conf)
    property var night: ({ helper: false })
    function loadNight() {
        Backend.call(["nightlight"], r => { if (r.ok) page.night = r; }, true);
    }
    function setNight(args, message) {
        Backend.call(["nightlight-set"].concat(args), r => {
            if (r.ok) {
                page.night = r;
                if (message)
                    Backend.notify("success", message, false);
            } else {
                page.loadNight();
            }
        });
    }
    function halfHours(first, count, current) {
        const out = [];
        for (let i = 0; i < count; i++) {
            const m = (first * 60 + i * 30) % (24 * 60);
            const t = (m < 600 ? "0" : "") + Math.floor(m / 60) + ":" + (m % 60 === 0 ? "00" : "30");
            out.push({ value: t, label: t });
        }
        if (current && !out.some(o => o.value === current))
            out.unshift({ value: current, label: current });
        return out;
    }
    readonly property string nightState: {
        const n = page.night;
        if (n.error)
            return n.error;
        if (n.active)
            return "On now" + (n.untilText ? ", until " + n.untilText : n.nextChangeText ? ", until " + n.nextChangeText : "") + ".";
        if (n.untilText)
            return "Off until " + n.untilText + ".";
        return n.nextChangeText ? "Turns on at " + n.nextChangeText + "." : "Off.";
    }

    Timer {
        id: tick
        interval: 1000
        repeat: true
        onTriggered: {
            page.countdown--;
            if (page.countdown <= 0)
                page.revert();
        }
    }

    ArBanner {
        visible: page.info.backend === "" && Backend.ready
        width: parent.width
        kind: "warning"
        title: "Settings can’t see your displays"
        text: "It needs wlr-randr (or Mango’s mmsg) for that." + (Backend.caps.wdisplays ? " wdisplays can still change them for this session." : "")
        actionText: Backend.caps.wdisplays ? "Open wdisplays" : ""
        onAction: Backend.launch(["wdisplays"])
    }
    ArBanner {
        visible: page.info.backend === "mmsg"
        width: parent.width
        kind: "info"
        text: "Without wlr-randr, Settings can change scale, rotation and position, but not the resolution. Install it with <b>sudo dnf install wlr-randr</b>."
    }
    ArBanner {
        visible: (page.info.problems || []).length > 0 && !page.trying
        width: parent.width
        kind: "info"
        text: "Some of your displays overlap or don’t touch, so the pointer can’t go everywhere. Settings has lined them up: press <b>Apply</b> to use this."
    }

    Group {
        visible: page.edit.length > 0
        title: page.edit.length > 1 ? "Arrangement" : "Your display"
        desc: page.onCount > 1 ? "Drag the displays to match your desk; they snap to each other’s edges. Arrow keys move the selected one." : ""
        SettingRow {
            searchKey: "displays.arrange"
            title: ""
            stacked: true
            resettable: false
            Column {
                width: parent.width
                spacing: Theme.space3
                Item {
                    id: canvas
                    width: parent.width
                    // As tall as the layout needs at the full width (a stack or a portrait
                    // display gets more room), within 220–340 px; one display needs little.
                    height: Math.round(Math.max(220, Math.min(page.onCount > 1 ? 340 : 240, spanH * (width - 2 * padX) / spanW + 2 * padY)))
                    enabled: !page.trying
                    readonly property var shown: page.edit.filter(o => o.enabled)
                    readonly property real minX: shown.length ? Math.min.apply(null, shown.map(o => o.x)) : 0
                    readonly property real minY: shown.length ? Math.min.apply(null, shown.map(o => o.y)) : 0
                    readonly property real spanW: shown.length ? Math.max.apply(null, shown.map(o => o.x + o.logicalWidth)) - minX : 1
                    readonly property real spanH: shown.length ? Math.max.apply(null, shown.map(o => o.y + o.logicalHeight)) - minY : 1
                    // Room round the layout to drop a display on any side of it.
                    readonly property int padX: Theme.space10 + Theme.space6
                    readonly property int padY: Theme.space8
                    readonly property real k: Math.min((width - 2 * padX) / spanW, (height - 2 * padY) / spanH)
                    readonly property real originX: (width - spanW * k) / 2
                    readonly property real originY: (height - spanH * k) / 2
                    Accessible.role: Accessible.Grouping
                    Accessible.name: "Arrangement of the displays"
                    Behavior on height {
                        NumberAnimation { duration: Theme.durationBase; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeStandard }
                    }

                    Rectangle {
                        anchors.fill: parent
                        radius: Theme.radiusMd
                        color: Theme.surfaceSunken
                        border.width: 1
                        border.color: Theme.line
                    }
                    Repeater {
                        // By count, so a move keeps each display's item (focus, animation).
                        model: page.edit.length
                        T.AbstractButton {
                            id: screen
                            required property int index
                            readonly property var o: page.edit[index] || ({ name: "", enabled: false, x: 0, y: 0, logicalWidth: 1, logicalHeight: 1 })
                            readonly property bool chosen: page.selectedName === o.name
                            readonly property bool dragging: drag.active
                            // Dropped and waiting for the helper: it stays where it was dropped.
                            property bool dropped: false
                            readonly property real homeX: canvas.originX + (o.x - canvas.minX) * canvas.k + 2
                            readonly property real homeY: canvas.originY + (o.y - canvas.minY) * canvas.k + 2
                            function settle() {
                                dropped = false;
                                x = homeX;
                                y = homeY;
                            }
                            // x and y are set, not bound: the drag handler moves the item itself.
                            Component.onCompleted: settle()
                            onHomeXChanged: if (!dragging && !dropped) x = homeX
                            onHomeYChanged: if (!dragging && !dropped) y = homeY
                            visible: o.enabled
                            z: dragging ? 10 : chosen ? 2 : 1
                            width: Math.max(8, o.logicalWidth * canvas.k - 4)
                            height: Math.max(8, o.logicalHeight * canvas.k - 4)
                            padding: 0
                            focusPolicy: Qt.StrongFocus
                            hoverEnabled: true
                            Accessible.role: Accessible.RadioButton
                            Accessible.name: o.name + ", " + (o.width ? o.width + " × " + o.height : o.logicalWidth + " × " + o.logicalHeight) + (o.main && page.onCount > 1 ? ", main display" : "")
                            Accessible.description: page.onCount > 1 ? "The arrow keys move it along the other displays" : ""
                            Accessible.checked: chosen
                            onClicked: page.selectedName = o.name
                            Behavior on x {
                                enabled: !screen.dragging && !Theme.reduceMotion
                                NumberAnimation { duration: Theme.durationBase; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeStandard }
                            }
                            Behavior on y {
                                enabled: !screen.dragging && !Theme.reduceMotion
                                NumberAnimation { duration: Theme.durationBase; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeStandard }
                            }
                            Connections {
                                target: page
                                // The helper answered (or a move failed): go to the new place once
                                // every binding has caught up.
                                function onEditChanged() {
                                    if (screen.dropped)
                                        Qt.callLater(screen.settle);
                                }
                            }
                            DragHandler {
                                id: drag
                                target: screen
                                enabled: page.onCount > 1 && !page.trying
                                cursorShape: Qt.ClosedHandCursor
                                // Keep at least half of it on the canvas.
                                xAxis.minimum: -screen.width / 2
                                xAxis.maximum: canvas.width - screen.width / 2
                                yAxis.minimum: -screen.height / 2
                                yAxis.maximum: canvas.height - screen.height / 2
                                onActiveChanged: {
                                    if (active) {
                                        page.selectedName = screen.o.name;
                                        return;
                                    }
                                    // Dropped: the helper finds the nearest place touching another
                                    // display (lined up with one when within 12 px on screen).
                                    screen.dropped = true;
                                    page.arrange(["--move", screen.o.name,
                                        Math.round(screen.o.x + (screen.x - screen.homeX) / canvas.k),
                                        Math.round(screen.o.y + (screen.y - screen.homeY) / canvas.k),
                                        "--threshold", Math.round(12 / canvas.k)]);
                                }
                            }
                            Keys.onPressed: event => {
                                const dirs = { [Qt.Key_Left]: "left", [Qt.Key_Right]: "right", [Qt.Key_Up]: "up", [Qt.Key_Down]: "down" };
                                if (!(event.key in dirs) || page.onCount < 2)
                                    return;
                                event.accepted = true;
                                page.selectedName = o.name;
                                if (!page.arranging)
                                    page.arrange(["--nudge", o.name, dirs[event.key]]);
                            }
                            onActiveFocusChanged: if (activeFocus) page.ensureVisible(screen)
                            background: Rectangle {
                                radius: Theme.radiusSm
                                color: screen.chosen ? Theme.accentSoft : screen.hovered || screen.dragging ? Theme.surface : Theme.surfaceRaised
                                border.width: screen.chosen ? 2 : 1
                                border.color: screen.chosen ? Theme.accentEdge : screen.hovered ? Theme.lineStrong : Theme.line
                                opacity: screen.dragging ? 0.9 : 1
                                Behavior on color {
                                    ColorAnimation { duration: Theme.durationFast }
                                }
                                FocusRing {
                                    show: screen.visualFocus
                                    radius: Theme.radiusSm
                                    gapColor: Theme.surfaceSunken
                                }
                            }
                            // Name, mode, then (as room allows) "Main" and scale · rotation.
                            contentItem: Item {
                                clip: true
                                Column {
                                    width: parent.width
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 0
                                    ArText {
                                        width: parent.width - 2 * Theme.space1
                                        x: Theme.space1
                                        horizontalAlignment: Text.AlignHCenter
                                        text: screen.o.name
                                        size: screen.width < 110 ? 12 : 13
                                        lh: 18
                                        weight: Font.DemiBold
                                        elide: Text.ElideMiddle
                                    }
                                    ArText {
                                        visible: screen.height >= 44
                                        width: parent.width - 2 * Theme.space1
                                        x: Theme.space1
                                        horizontalAlignment: Text.AlignHCenter
                                        text: screen.o.width ? screen.o.width + " × " + screen.o.height : screen.o.logicalWidth + " × " + screen.o.logicalHeight
                                        size: screen.width < 110 ? 11 : 12
                                        lh: 16
                                        color: Theme.inkMuted
                                        elide: Text.ElideRight
                                    }
                                    ArText {
                                        visible: text !== "" && screen.height >= 64
                                        width: parent.width - 2 * Theme.space1
                                        x: Theme.space1
                                        horizontalAlignment: Text.AlignHCenter
                                        text: page.describe(screen.o)
                                        size: screen.width < 110 ? 11 : 12
                                        lh: 16
                                        color: Theme.inkSubtle
                                        elide: Text.ElideRight
                                    }
                                    Item {
                                        visible: screen.o.main && page.onCount > 1 && screen.height >= (page.describe(screen.o) !== "" ? 88 : 68)
                                        width: parent.width
                                        height: 24
                                        ArTag {
                                            anchors.horizontalCenter: parent.horizontalCenter
                                            anchors.bottom: parent.bottom
                                            text: "Main"
                                            textSize: 10
                                            kind: screen.chosen ? "accent" : ""
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                // Displays that are off: not in the arrangement, but you can pick them here.
                Flow {
                    visible: page.onCount < page.edit.length
                    width: parent.width
                    spacing: Theme.space2
                    ArText {
                        text: "Off:"
                        size: 13
                        lh: Theme.controlSm
                        color: Theme.inkMuted
                    }
                    Repeater {
                        model: page.edit.length
                        T.AbstractButton {
                            id: chip
                            required property int index
                            readonly property var o: page.edit[index] || ({ name: "", enabled: true })
                            readonly property bool chosen: page.selectedName === o.name
                            visible: !o.enabled
                            implicitWidth: chipText.implicitWidth + leftPadding + rightPadding
                            implicitHeight: Theme.controlSm
                            leftPadding: Theme.space3
                            rightPadding: Theme.space3
                            focusPolicy: Qt.StrongFocus
                            hoverEnabled: true
                            Accessible.role: Accessible.RadioButton
                            Accessible.name: o.name + ", off"
                            Accessible.checked: chosen
                            onClicked: page.selectedName = o.name
                            background: Rectangle {
                                radius: Theme.radiusSm
                                color: chip.chosen ? Theme.accentSoft : chip.hovered ? Theme.surface : Theme.surfaceSunken
                                border.width: chip.chosen ? 2 : 1
                                border.color: chip.chosen ? Theme.accentEdge : Theme.line
                                FocusRing {
                                    show: chip.visualFocus
                                    radius: Theme.radiusSm
                                    gapColor: Theme.surfaceRaised
                                }
                            }
                            contentItem: ArText {
                                id: chipText
                                text: chip.o.name
                                size: 13
                                lh: 18
                                verticalAlignment: Text.AlignVCenter
                                color: Theme.inkMuted
                            }
                        }
                    }
                }
            }
        }
    }

    Group {
        visible: page.output !== null
        title: page.original ? (page.original.description || page.original.name) : ""
        desc: page.original && page.original.make ? page.original.make + (page.original.model ? " " + page.original.model : "") + " · " + page.original.name : ""
        SettingRow {
            searchKey: "displays.use"
            visible: page.edit.length > 1
            enabled: !page.trying
            title: "Use this display"
            desc: page.output && page.output.enabled && page.onCount === 1 ? "The only display that’s on stays on." : ""
            resettable: false
            RowSwitch {
                Accessible.name: "Use this display"
                enabled: !(page.output && page.output.enabled && page.onCount === 1)
                checked: page.output ? page.output.enabled : true
                onToggled: page.arrange([checked ? "--enable" : "--disable", page.output.name])
            }
        }
        SettingRow {
            searchKey: "displays.main"
            visible: page.onCount > 1 && page.output !== null && page.output.enabled
            enabled: !page.trying
            title: "Main display"
            desc: page.output && page.output.main ? "This is where the pointer, your first windows and the launcher start when you log in. Mango starts at the top-left corner, so the main display sits there." : "Move it to the top-left corner, where you start when you log in."
            resettable: false
            Item {
                implicitWidth: page.output && page.output.main ? mainTag.width : makeMain.implicitWidth
                implicitHeight: Theme.controlMd
                ArTag {
                    id: mainTag
                    visible: page.output !== null && page.output.main
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.right: parent.right
                    text: "Main display"
                    kind: "accent"
                }
                ArButton {
                    id: makeMain
                    visible: page.output !== null && !page.output.main
                    anchors.right: parent.right
                    text: "Make main"
                    variant: "secondary"
                    gapColor: Theme.surfaceRaised
                    onClicked: page.arrange(["--main", page.output.name])
                }
            }
        }
        SettingRow {
            searchKey: "displays.resolution"
            visible: page.info.canChangeMode === true
            enabled: page.output ? page.output.enabled && !page.trying : false
            title: "Resolution"
            desc: "The best one is the screen’s own. Lower ones look less sharp."
            resettable: false
            ArSelect {
                width: 230
                model: page.output ? page.sizes(page.output.name) : []
                value: page.output ? page.output.width + "x" + page.output.height : ""
                onActivated: v => {
                    const wh = v.split("x").map(Number);
                    const best = page.rates(page.output.name, wh[0], wh[1]);
                    page.change({ width: wh[0], height: wh[1], refresh: best.length ? Number(best[0].value) : 0 });
                }
            }
        }
        SettingRow {
            searchKey: "displays.refresh"
            visible: page.info.canChangeMode === true && page.output !== null && page.rates(page.output.name, page.output.width, page.output.height).length > 1
            enabled: page.output ? page.output.enabled && !page.trying : false
            title: "Refresh rate"
            desc: "Higher is smoother, if the screen supports it."
            resettable: false
            ArSelect {
                width: 180
                model: page.output ? page.rates(page.output.name, page.output.width, page.output.height) : []
                value: page.output ? String(page.output.refresh) : ""
                onActivated: v => page.change({ refresh: Number(v) })
            }
        }
        SettingRow {
            searchKey: "displays.scale"
            enabled: page.output ? page.output.enabled && !page.trying : false
            title: "Scale"
            desc: page.output ? "Everything drawn " + Math.round(page.output.scale * 100) + "% of its size, so the desktop is " + page.output.logicalWidth + " × " + page.output.logicalHeight + " here. Use more on small, sharp screens." : ""
            resettable: false
            ArSelect {
                width: 180
                model: page.scales.map(s => ({ value: String(s), label: Math.round(s * 100) + "%" }))
                value: page.output ? String(page.output.scale) : "1"
                onActivated: v => page.change({ scale: Number(v) })
            }
        }
        SettingRow {
            searchKey: "displays.rotation"
            enabled: page.output ? page.output.enabled && !page.trying : false
            title: "Rotation"
            desc: "Portrait for a screen turned on its side."
            resettable: false
            ArSelect {
                width: 240
                model: page.transforms
                value: page.output ? page.output.transform : "normal"
                onActivated: v => page.change({ transform: v })
            }
        }
        SettingRow {
            enabled: page.output ? page.output.enabled && !page.trying : false
            title: "Variable refresh rate"
            desc: "Smoother games and video on screens that support it (FreeSync, G-Sync compatible)."
            resettable: false
            RowSwitch {
                Accessible.name: "Variable refresh rate"
                checked: page.output ? page.output.adaptiveSync === true : false
                onToggled: page.change({ adaptiveSync: checked })
            }
        }
    }

    Row {
        visible: page.edit.length > 0
        spacing: Theme.space2
        ArButton {
            text: "Apply"
            variant: "primary"
            enabled: page.dirty && page.info.canApply === true && !page.trying && !page.arranging
            onClicked: page.apply()
        }
        ArButton {
            text: "Discard changes"
            variant: "ghost"
            enabled: page.dirty && !page.trying
            onClicked: page.load()
        }
    }

    Group {
        visible: (page.info.rules || []).length > 0
        title: "Saved layout"
        SettingRow {
            title: "Kept for " + (page.info.rules || []).map(r => r.name).join(", ")
            desc: "Mango sets these displays up this way whenever it starts. Forget it to use each screen’s own best mode again."
            resettable: false
            ArButton {
                text: "Forget"
                variant: "secondary"
                gapColor: Theme.surfaceRaised
                onClicked: Backend.call(["display-forget"], r => {
                    if (r.ok) {
                        page.info = r;
                        page.edit = r.arranged || [];
                        Backend.notify("success", "Saved layout forgotten. It applies the next time Mango starts.", false);
                    }
                })
            }
        }
    }

    Group {
        visible: page.night.helper === true
        title: "Night light"
        desc: "A warmer screen in the evening is easier on the eyes. Super + Ctrl + N turns it on or off right away."
        SettingRow {
            searchKey: "displays.nightlight"
            title: "Night light"
            desc: page.night.available === false ? "Night light needs wlsunset: sudo dnf install wlsunset." : page.nightState
            resettable: false
            ArSelect {
                width: 220
                enabled: page.night.available !== false
                model: [{ value: "off", label: "Off" }, { value: "sunset", label: "Sunset to sunrise" },
                    { value: "hours", label: "Custom hours" }, { value: "always", label: "Always on" }]
                value: page.night.mode || "off"
                onActivated: v => page.setNight(["mode=" + v], "Night light changed")
            }
        }
        SettingRow {
            visible: page.night.mode === "sunset"
            title: "Where the sun sets"
            desc: page.night.fallback ? "Your time zone doesn’t say where you are, so night light uses the custom hours (" + page.night.from + " to " + page.night.to + ") instead. Pick a city as your time zone to follow the sun."
                : page.night.location === "manual" ? "The location in ~/.config/arctic/nightlight.conf (lat, lon)."
                : "The location of your time zone, " + String(page.night.location).replace(/_/g, " ") + ". Nothing is looked up online."
            resettable: false
        }
        SettingRow {
            visible: page.night.mode === "hours"
            searchKey: "displays.nighthours"
            title: "Hours"
            desc: "It warms up over half an hour from the first time and is back to normal by the second."
            resettable: false
            Row {
                spacing: Theme.space2
                ArSelect {
                    width: 110
                    model: page.halfHours(16, 16, page.night.from)
                    value: page.night.from || "20:00"
                    onActivated: v => page.setNight(["from=" + v], "Hours changed")
                }
                ArText {
                    text: "to"
                    size: 14
                    lh: 40
                    color: Theme.inkMuted
                }
                ArSelect {
                    width: 110
                    model: page.halfHours(4, 16, page.night.to)
                    value: page.night.to || "07:00"
                    onActivated: v => page.setNight(["to=" + v], "Hours changed")
                }
            }
        }
        SettingRow {
            visible: page.night.mode !== "off" || page.night.active === true
            searchKey: "displays.warmth"
            title: "Warmth"
            desc: "Further right is warmer and dimmer. It changes as soon as you let go."
            resettable: false
            ArSlider {
                accessibleName: "Night light warmth"
                valueText: (6000 - value * 100) + " kelvin"
                from: 0; to: 35; stepSize: 1
                value: (6000 - (page.night.temp || 4000)) / 100
                onCommitted: v => page.setNight(["temp=" + (6000 - Math.round(v) * 100)], "")
            }
        }
        SettingRow {
            visible: page.night.available !== false && !page.night.error
            title: page.night.active ? "Turn it off for now" : "Turn it on now"
            desc: page.night.mode === "sunset" || page.night.mode === "hours" ? "Until the schedule changes anyway." : "Until you log out."
            resettable: false
            ArButton {
                text: page.night.active ? "Turn off" : "Turn on"
                variant: "secondary"
                gapColor: Theme.surfaceRaised
                onClicked: page.setNight(["now", page.night.active ? "off" : "on"], "")
            }
        }
    }

    ArDialog {
        id: confirm
        parent: T.Overlay.overlay
        title: "Keep these display settings?"
        body: "Going back to the previous settings in " + page.countdown + (page.countdown === 1 ? " second." : " seconds.")
        iconName: "display"
        closePolicy: T.Popup.NoAutoClose
        buttons: [
            ArButton {
                text: "Revert"
                variant: "secondary"
                onClicked: page.revert()
            },
            ArButton {
                text: "Keep changes"
                variant: "primary"
                focus: true
                onClicked: page.keep()
            }
        ]
    }
}
