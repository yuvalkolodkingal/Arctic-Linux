// Displays: resolution, refresh rate, scale, rotation and arrangement.
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
    lede: "Size, sharpness and position of each screen. You get 15 seconds to keep a change before it goes back."

    property var info: ({ outputs: [], rules: [], backend: "", canApply: false, canChangeMode: false })
    property var edit: []
    property int selected: 0
    property bool dirty: false
    property bool trying: false
    property int countdown: 0
    readonly property var output: edit.length > selected ? edit[selected] : null
    readonly property var original: info.outputs && info.outputs.length > selected ? info.outputs[selected] : null
    readonly property var transforms: [{ value: "normal", label: "Normal" }, { value: "90", label: "Portrait (90°)" },
        { value: "180", label: "Upside down" }, { value: "270", label: "Portrait (270°)" }]
    readonly property var scales: [1, 1.25, 1.5, 1.75, 2, 2.5, 3]

    function load() {
        Backend.call(["displays"], r => {
            if (!r.ok)
                return;
            page.info = r;
            page.edit = r.outputs.map(o => ({ name: o.name, enabled: o.enabled, width: o.width, height: o.height,
                    refresh: o.refresh, x: o.x, y: o.y, scale: o.scale, transform: o.transform,
                    adaptiveSync: o.adaptiveSync }));
            page.selected = Math.min(page.selected, Math.max(0, r.outputs.length - 1));
            page.dirty = false;
        });
    }
    function change(values) {
        const list = edit.slice();
        list[selected] = Object.assign({}, list[selected], values);
        edit = list;
        dirty = true;
    }
    function logical(o) {
        const turned = o.transform === "90" || o.transform === "270" || o.transform === "flipped-90" || o.transform === "flipped-270";
        const w = turned ? o.height : o.width, h = turned ? o.width : o.height;
        const s = o.scale || 1;
        const orig = (info.outputs || []).find(x => x.name === o.name) || {};
        return { w: Math.round((w || orig.logicalWidth * s || 1280) / s), h: Math.round((h || orig.logicalHeight * s || 800) / s) };
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
    // Where the selected display sits next to another: right:NAME, left:…, above:…, below:…
    function relation(o) {
        for (let i = 0; i < edit.length; i++) {
            const other = edit[i];
            if (other.name === o.name || !other.enabled)
                continue;
            const a = logical(o), b = logical(other);
            if (o.x === other.x + b.w && o.y === other.y) return "right:" + other.name;
            if (o.x + a.w === other.x && o.y === other.y) return "left:" + other.name;
            if (o.y + a.h === other.y && o.x === other.x) return "above:" + other.name;
            if (o.y === other.y + b.h && o.x === other.x) return "below:" + other.name;
        }
        return "here";
    }
    function place(value) {
        if (value === "here")
            return;
        const where = value.split(":")[0], other = edit.find(x => x.name === value.slice(where.length + 1));
        if (!other)
            return;
        const a = logical(output), b = logical(other);
        const pos = where === "right" ? { x: other.x + b.w, y: other.y } : where === "left" ? { x: other.x - a.w, y: other.y }
                  : where === "above" ? { x: other.x, y: other.y - a.h } : { x: other.x, y: other.y + b.h };
        change(pos);
    }
    function apply() {
        Backend.call(["display-try", JSON.stringify(edit)], r => {
            if (!r.ok) {
                page.load();
                return;
            }
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
                Backend.notify("success", "Display settings kept", false);
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
    onShown: if (!trying) load()

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

    Group {
        visible: page.edit.length > 0
        title: page.edit.length > 1 ? "Arrangement" : "Your display"
        desc: page.edit.length > 1 ? "Click a display to change it. Move the pointer off an edge to reach the next one." : ""
        SettingRow {
            searchKey: "displays.arrange"
            title: ""
            stacked: true
            resettable: false
            Item {
                id: canvas
                width: parent.width
                height: 200
                readonly property var boxes: page.edit.map(o => {
                    const l = page.logical(o);
                    return { x: o.x, y: o.y, w: l.w, h: l.h };
                })
                readonly property real minX: Math.min.apply(null, boxes.map(b => b.x).concat([0]))
                readonly property real minY: Math.min.apply(null, boxes.map(b => b.y).concat([0]))
                readonly property real spanW: Math.max.apply(null, boxes.map(b => b.x + b.w).concat([1])) - minX
                readonly property real spanH: Math.max.apply(null, boxes.map(b => b.y + b.h).concat([1])) - minY
                readonly property real k: Math.min((width - 16) / spanW, (height - 16) / spanH)
                Rectangle {
                    anchors.fill: parent
                    radius: Theme.radiusMd
                    color: Theme.surfaceSunken
                }
                Repeater {
                    model: page.edit
                    T.AbstractButton {
                        id: screen
                        required property var modelData
                        required property int index
                        readonly property var box: canvas.boxes[index] || ({ x: 0, y: 0, w: 1, h: 1 })
                        x: (canvas.width - canvas.spanW * canvas.k) / 2 + (box.x - canvas.minX) * canvas.k
                        y: (canvas.height - canvas.spanH * canvas.k) / 2 + (box.y - canvas.minY) * canvas.k
                        width: box.w * canvas.k - 2
                        height: box.h * canvas.k - 2
                        focusPolicy: Qt.StrongFocus
                        hoverEnabled: true
                        Accessible.role: Accessible.RadioButton
                        Accessible.name: modelData.name
                        Accessible.checked: page.selected === index
                        onClicked: page.selected = index
                        Keys.onReturnPressed: page.selected = index
                        background: Rectangle {
                            radius: Theme.radiusSm
                            color: screen.modelData.enabled ? (page.selected === screen.index ? Theme.accentSoft : Theme.surfaceRaised) : Theme.surface
                            border.width: page.selected === screen.index ? 2 : 1
                            border.color: page.selected === screen.index ? Theme.accentEdge : screen.hovered ? Theme.lineStrong : Theme.line
                            FocusRing {
                                show: screen.visualFocus
                                radius: Theme.radiusSm
                                gapColor: Theme.surfaceSunken
                            }
                        }
                        contentItem: Column {
                            spacing: 0
                            topPadding: Math.max(0, (screen.height - 40) / 2)
                            ArText {
                                width: screen.width
                                horizontalAlignment: Text.AlignHCenter
                                text: screen.modelData.name
                                size: 13
                                lh: 18
                                weight: Font.DemiBold
                                elide: Text.ElideRight
                            }
                            ArText {
                                width: screen.width
                                horizontalAlignment: Text.AlignHCenter
                                text: screen.modelData.enabled ? (screen.modelData.width ? screen.modelData.width + " × " + screen.modelData.height : "") : "Off"
                                size: 12
                                lh: 16
                                color: Theme.inkMuted
                                elide: Text.ElideRight
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
            visible: page.edit.length > 1
            title: "Use this display"
            resettable: false
            RowSwitch {
                Accessible.name: "Use this display"
                checked: page.output ? page.output.enabled : true
                onToggled: page.change({ enabled: checked })
            }
        }
        SettingRow {
            searchKey: "displays.resolution"
            visible: page.info.canChangeMode === true
            enabled: page.output ? page.output.enabled : false
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
            enabled: page.output ? page.output.enabled : false
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
            enabled: page.output ? page.output.enabled : false
            title: "Scale"
            desc: page.output ? "Everything drawn " + Math.round(page.output.scale * 100) + "% of its size. Use more on small, sharp screens." : ""
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
            enabled: page.output ? page.output.enabled : false
            title: "Rotation"
            resettable: false
            ArSelect {
                width: 200
                model: page.transforms
                value: page.output ? page.output.transform : "normal"
                onActivated: v => page.change({ transform: v })
            }
        }
        SettingRow {
            visible: page.edit.length > 1
            enabled: page.output ? page.output.enabled : false
            title: "Position"
            desc: "Next to which display this one sits."
            resettable: false
            ArSelect {
                width: 240
                model: {
                    const out = [{ value: "here", label: "Where it is now" }];
                    page.edit.forEach(o => {
                        if (!page.output || o.name === page.output.name || !o.enabled)
                            return;
                        out.push({ value: "right:" + o.name, label: "Right of " + o.name });
                        out.push({ value: "left:" + o.name, label: "Left of " + o.name });
                        out.push({ value: "above:" + o.name, label: "Above " + o.name });
                        out.push({ value: "below:" + o.name, label: "Below " + o.name });
                    });
                    return out;
                }
                value: page.output ? page.relation(page.output) : "here"
                onActivated: v => page.place(v)
            }
        }
        SettingRow {
            enabled: page.output ? page.output.enabled : false
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
            enabled: page.dirty && page.info.canApply === true && !page.trying
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
                        Backend.notify("success", "Saved layout forgotten. It applies the next time Mango starts.", false);
                    }
                })
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
