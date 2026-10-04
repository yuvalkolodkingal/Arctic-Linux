// Shortcuts: Arctic's shortcut sheet (keys.txt, parsed like the shell's KeysSheet), every bind
// in the Mango config, and your own shortcuts that run a command or open an app — written as
// `bind=MODS,KEY,spawn_shell,COMMAND` lines in settings.conf. Mango uses the first bind for a
// key, so a key that is already taken is refused rather than silently ignored, and a bind of yours
// that Arctic took over later (a new default on the same keys) is flagged: it never runs.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Templates as T
import ".."
import "../components"

Page {
    id: page
    title: "Shortcuts"
    lede: "Everything on this desktop has a shortcut. Add your own to open apps or run commands."

    property var binds: ({ sheet: [], all: [], mine: [], shadowed: [] })
    property string filter: ""
    property bool showAll: false
    readonly property string f: filter.trim().toLowerCase()
    function matches(a, b) {
        return f === "" || String(a).toLowerCase().indexOf(f) >= 0 || String(b).toLowerCase().indexOf(f) >= 0;
    }
    // What the bind that wins does, in the sheet's words when it has some ("Browser").
    function winner(s) {
        return s.label + " is " + (s.sheet || s.what) + " in " + s.file;
    }
    readonly property var shadowed: binds.shadowed || []
    onShown: Backend.call(["binds"], r => { if (r.ok) page.binds = r; })

    // Mango runs only the first bind for a key, and Arctic's files come before yours: when an
    // update gives one of your keys to Arctic, say so rather than let it fail silently.
    ArBanner {
        visible: page.shadowed.length > 0
        width: parent.width
        kind: "warning"
        strong: true
        title: page.shadowed.length === 1 ? "One of your shortcuts doesn’t run"
            : page.shadowed.length + " of your shortcuts don’t run"
        text: {
            if (page.shadowed.length === 0)
                return "";
            const s = page.shadowed[0];
            const others = page.shadowed.slice(1).map(o => o.label + " (" + o.what + ", " + o.file + ")");
            return "Arctic’s “" + (s.shadowedBy.sheet || s.shadowedBy.what) + "” shortcut uses " + s.shadowedBy.label
                + ", so yours (" + s.what + ") never runs. Remove it and add it on another key."
                + (s.file === "user.conf" ? " It’s in ~/.config/mango/user.conf." : "")
                + (others.length ? " Also " + others.join(", ") + "." : "");
        }
    }

    ArInput {
        width: 360
        iconName: "search"
        placeholder: "Find a shortcut"
        accessibleName: "Find a shortcut"
        onTextChanged: page.filter = text
    }

    Group {
        title: "Your shortcuts"
        desc: "They run a command or open an app. Super + Shift + R reloads the config if one doesn’t work straight away. Arctic’s own shortcuts come first: if Arctic later uses one of your keys, this page tells you."
        SettingRow {
            searchKey: "shortcuts.mine"
            visible: page.binds.mine.length === 0
            title: "None yet"
            desc: "For example Super + Alt + F to open Firefox, or a key for a script."
            resettable: false
            ArButton {
                text: "Add a shortcut"
                iconName: "plus"
                gapColor: Theme.surfaceRaised
                onClicked: addDialog.start()
            }
        }
        Repeater {
            model: page.binds.mine.filter(b => page.matches(b.label, b.command))
            SettingRow {
                id: mineRow
                required property var modelData
                title: modelData.label
                desc: modelData.shadowedBy ? modelData.command + " · doesn’t run: " + page.winner(modelData.shadowedBy) : modelData.command
                resettable: false
                Row {
                    spacing: Theme.space4
                    Row {
                        visible: !!mineRow.modelData.shadowedBy
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: Theme.space1
                        Icon {
                            name: "alert"
                            size: 16
                            color: Theme.warning
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        ArText {
                            text: "Doesn’t run"
                            size: 13
                            lh: 20
                            weight: Font.DemiBold
                            color: Theme.warning
                        }
                    }
                    ArButton {
                        text: "Edit…"
                        gapColor: Theme.surfaceRaised
                        onClicked: addDialog.edit(mineRow.modelData)
                    }
                    ArButton {
                        variant: "ghost"
                        size: "sm"
                        iconName: "trash"
                        text: "Remove"
                        gapColor: Theme.surfaceRaised
                        onClicked: Backend.call(["bind-remove", String(mineRow.modelData.index)], r => {
                            if (r.ok) {
                                page.binds = r;
                                Backend.refresh();
                                Backend.notify("success", "Shortcut removed", true);
                            }
                        })
                    }
                }
            }
        }
    }
    ArButton {
        visible: page.binds.mine.length > 0
        text: "Add a shortcut"
        iconName: "plus"
        onClicked: addDialog.start()
    }

    ArButton {
        visible: page.binds.mine.length > 0
        text: "Restore default shortcuts…"
        onClicked: resetDialog.open()
    }
    ArDialog {
        id: resetDialog
        parent: T.Overlay.overlay
        title: "Restore default shortcuts?"
        body: "Remove shortcuts added through Settings. Arctic's built-in recovery keys and hand-written user.conf remain. Settings keeps a backup for Undo."
        ArButton {
            text: "Restore defaults"
            onClicked: Backend.call(["bind-reset"], r => {
                if (r.ok) { page.binds = r; resetDialog.close(); Backend.refresh(); }
            })
        }
    }

    Repeater {
        model: page.binds.sheet
        Group {
            id: section
            required property var modelData
            required property int index
            readonly property var matched: modelData.rows.filter(r => page.matches(r.keys, r.what))
            visible: matched.length > 0
            title: modelData.title
            Repeater {
                model: section.matched
                SettingRow {
                    id: sheetRow
                    required property var modelData
                    required property int index
                    searchKey: section.index === 0 && index === 0 ? "shortcuts.sheet" : ""
                    title: modelData.what
                    resettable: false
                    compact: true
                    ArText {
                        text: sheetRow.modelData.keys
                        size: 13
                        lh: 20
                        weight: Font.Bold
                        font.family: Theme.fontMono
                        color: Theme.ink
                    }
                }
            }
        }
    }

    Group {
        title: "Every shortcut in your Mango config"
        desc: "Read from binds.conf, apps.conf, settings.conf and user.conf, in the order Mango reads them."
        SettingRow {
            title: page.showAll ? "Showing " + page.binds.all.length + " shortcuts" : page.binds.all.length + " shortcuts"
            resettable: false
            ArButton {
                text: page.showAll ? "Hide them" : "Show them"
                variant: "secondary"
                gapColor: Theme.surfaceRaised
                onClicked: page.showAll = !page.showAll
            }
        }
        Repeater {
            model: page.showAll ? page.binds.all.filter(b => page.matches(b.label, b.what)) : []
            SettingRow {
                id: rawRow
                required property var modelData
                title: modelData.what || modelData.action
                desc: String(modelData.file).split("/").pop() + (modelData.keymode !== "default" ? " · " + modelData.keymode : "")
                    + (modelData.shadowedBy ? " · doesn’t run (" + page.winner(modelData.shadowedBy) + ")" : "")
                resettable: false
                compact: true
                ArText {
                    text: rawRow.modelData.label
                    size: 13
                    lh: 20
                    weight: Font.Bold
                    font.family: Theme.fontMono
                }
            }
        }
    }

    // ---- add a shortcut: press the keys, then say what it does ----
    ArDialog {
        id: addDialog
        parent: T.Overlay.overlay
        width: 480
        title: editingIndex < 0 ? "Add a shortcut" : "Edit shortcut"
        property int editingIndex: -1
        body: "Press the keys, then type the command it runs (or pick an app)."
        property var mods: []
        property string key: ""
        property string keyLabel: ""
        property string command: ""
        property string error: ""
        function start() {
            editingIndex = -1;
            mods = [];
            key = "";
            keyLabel = "";
            command = "";
            error = "";
            commandField.text = "";
            open();
            capture.forceActiveFocus();
        }
        function edit(entry) {
            start(); editingIndex = entry.index;
            mods = entry.mods === "NONE" ? [] : entry.mods.split("+");
            key = entry.key; keyLabel = entry.label; commandField.text = entry.command;
        }
        function save() {
            if (!key) {
                error = "Press the keys first.";
                return;
            }
            Backend.call((editingIndex < 0 ? ["bind-add"] : ["bind-edit", String(editingIndex)]).concat([mods.length ? mods.join("+") : "NONE", key, command]), r => {
                if (r.ok) {
                    page.binds = r;
                    addDialog.close();
                    Backend.refresh();
                    Backend.notify("success", "Shortcut added: " + addDialog.keyLabel, true);
                } else {
                    addDialog.error = r.error;
                }
            }, true);
        }

        // Qt key → xkb keysym name (what Mango's bind lines use).
        function keysym(event) {
            const k = event.key;
            if (k >= Qt.Key_A && k <= Qt.Key_Z)
                return String.fromCharCode(k).toLowerCase();
            if (k >= Qt.Key_0 && k <= Qt.Key_9)
                return String.fromCharCode(k);
            if (k >= Qt.Key_F1 && k <= Qt.Key_F24)
                return "F" + (k - Qt.Key_F1 + 1);
            const shifted = { [Qt.Key_Exclam]: "1", [Qt.Key_At]: "2", [Qt.Key_NumberSign]: "3", [Qt.Key_Dollar]: "4",
                [Qt.Key_Percent]: "5", [Qt.Key_AsciiCircum]: "6", [Qt.Key_Ampersand]: "7", [Qt.Key_Asterisk]: "8",
                [Qt.Key_ParenLeft]: "9", [Qt.Key_ParenRight]: "0" };
            if (shifted[k])
                return shifted[k];
            const names = { [Qt.Key_Return]: "Return", [Qt.Key_Enter]: "Return", [Qt.Key_Space]: "space",
                [Qt.Key_Backspace]: "BackSpace", [Qt.Key_Delete]: "Delete", [Qt.Key_Insert]: "Insert",
                [Qt.Key_Left]: "Left", [Qt.Key_Right]: "Right", [Qt.Key_Up]: "Up", [Qt.Key_Down]: "Down",
                [Qt.Key_Home]: "Home", [Qt.Key_End]: "End", [Qt.Key_PageUp]: "Page_Up", [Qt.Key_PageDown]: "Page_Down",
                [Qt.Key_Print]: "Print", [Qt.Key_Comma]: "comma", [Qt.Key_Period]: "period", [Qt.Key_Slash]: "slash",
                [Qt.Key_Semicolon]: "semicolon", [Qt.Key_Apostrophe]: "apostrophe", [Qt.Key_BracketLeft]: "bracketleft",
                [Qt.Key_BracketRight]: "bracketright", [Qt.Key_Minus]: "minus", [Qt.Key_Equal]: "equal",
                [Qt.Key_QuoteLeft]: "grave", [Qt.Key_Backslash]: "backslash" };
            return names[k] || "";
        }

        Rectangle {
            id: capture
            width: parent.width
            height: 56
            radius: Theme.radiusMd
            color: Theme.surfaceSunken
            border.width: activeFocus ? 2 : 1
            border.color: activeFocus ? Theme.focus : Theme.lineStrong
            focus: true
            activeFocusOnTab: true
            Accessible.role: Accessible.EditableText
            Accessible.name: "Shortcut keys: " + (addDialog.keyLabel || "none yet")
            ArText {
                anchors.centerIn: parent
                text: addDialog.keyLabel || (capture.activeFocus ? "Press the keys…" : "Click here, then press the keys")
                size: addDialog.keyLabel ? 16 : 14
                lh: 22
                weight: addDialog.keyLabel ? Font.Bold : Font.Normal
                font.family: addDialog.keyLabel ? Theme.fontMono : Theme.fontSans
                color: addDialog.keyLabel ? Theme.ink : Theme.inkMuted
            }
            TapHandler {
                onTapped: capture.forceActiveFocus()
            }
            Keys.onPressed: event => {
                if (event.key === Qt.Key_Tab || event.key === Qt.Key_Backtab || event.key === Qt.Key_Escape) {
                    event.accepted = false;
                    return;
                }
                const name = addDialog.keysym(event);
                event.accepted = true;
                if (!name)
                    return;     // a modifier on its own, or a key Mango can't bind by name
                const mods = [];
                if (event.modifiers & Qt.MetaModifier) mods.push("SUPER");
                if (event.modifiers & Qt.ControlModifier) mods.push("CTRL");
                if (event.modifiers & Qt.AltModifier) mods.push("ALT");
                if (event.modifiers & Qt.ShiftModifier) mods.push("SHIFT");
                addDialog.mods = mods;
                addDialog.key = name;
                const words = { SUPER: "Super", CTRL: "Ctrl", ALT: "Alt", SHIFT: "Shift" };
                addDialog.keyLabel = mods.map(m => words[m]).concat([name.length === 1 ? name.toUpperCase() : name.replace("_", " ")]).join(" + ");
                addDialog.error = "";
            }
        }
        ArInput {
            id: commandField
            width: parent.width
            label: "Command"
            placeholder: "For example: firefox --private-window"
            onTextChanged: {
                addDialog.command = text;
                addDialog.error = "";
            }
            onAccepted: addDialog.save()
        }
        ArButton {
            text: "Or pick an app to open"
            variant: "ghost"
            iconName: "grid"
            onClicked: appPicker.start()
        }
        // An app picked above: start it, or bring back its window when it's open already.
        ArCheck {
            id: focusCheck
            visible: /^(gtk-launch|arctic-open --focus) [A-Za-z0-9._-]+$/.test(addDialog.command.trim())
            checked: true
            text: "If it’s open, bring its window back"
            onToggled: {
                const id = addDialog.command.trim().split(" ").pop();
                commandField.text = (checked ? "arctic-open --focus " : "gtk-launch ") + id;
            }
        }
        ArText {
            visible: addDialog.error !== ""
            width: parent.width
            text: addDialog.error
            size: 13
            lh: 18
            wrapMode: Text.WordWrap
            color: Theme.error
        }
        buttons: [
            ArButton {
                text: "Cancel"
                variant: "ghost"
                onClicked: addDialog.close()
            },
            ArButton {
                text: "Add shortcut"
                variant: "primary"
                enabled: addDialog.key !== "" && addDialog.command.trim() !== ""
                onClicked: addDialog.save()
            }
        ]
    }

    PickerDialog {
        id: appPicker
        property var apps: []
        title: "Open an app"
        actionText: "Use this app"
        items: apps
        onPicked: v => {
            commandField.text = (focusCheck.checked ? "arctic-open --focus " : "gtk-launch ") + v;
            addDialog.open();
        }
        onOpened: if (apps.length === 0) Backend.call(["startup"], r => {
            if (r.ok)
                appPicker.apps = r.apps.map(a => ({ value: a.id, label: a.name }));
        }, true)
    }
}
