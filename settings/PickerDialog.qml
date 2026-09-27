// Pick one thing from a long list (keyboard layouts, apps): a dialog with a search field and
// the installer's list (ArList + ArListRow). Type to narrow it, ↑/↓ to move, Enter to pick.
// items = [{value, label, desc}]; `picked(value)` when the person chooses.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Templates as T
import "components"

ArDialog {
    id: picker
    property var items: []
    property string actionText: "Add"
    property string query: ""
    readonly property var shown: {
        const q = query.trim().toLowerCase();
        return q === "" ? items : items.filter(i => String(i.label).toLowerCase().indexOf(q) >= 0 || String(i.value).toLowerCase().indexOf(q) >= 0);
    }
    signal picked(string value)

    parent: T.Overlay.overlay
    width: 520
    function start() {
        query = "";
        search.text = "";
        list.currentIndex = -1;
        open();
        search.forceActiveFocus();
    }
    function choose() {
        const item = shown[list.currentIndex];
        if (!item)
            return;
        close();
        picked(item.value);
    }

    ArInput {
        id: search
        width: parent.width
        iconName: "search"
        placeholder: "Search"
        accessibleName: "Search"
        onTextChanged: {
            picker.query = text;
            list.currentIndex = picker.shown.length ? 0 : -1;
        }
        input.Keys.onDownPressed: {
            list.forceActiveFocus();
            list.currentIndex = Math.min(picker.shown.length - 1, list.currentIndex + 1);
        }
        onAccepted: picker.choose()
    }
    ArList {
        id: list
        width: parent.width
        height: 300
        maxHeight: 300
        model: picker.shown
        accessibleName: picker.title
        onActivated: picker.choose()
        Keys.onReturnPressed: picker.choose()
        delegate: ArListRow {
            required property var modelData
            required property int index
            width: ListView.view.width
            first: index === 0
            title: modelData.label
            desc: modelData.desc || ""
            selected: ListView.isCurrentItem
            showFocus: list.showFocus && ListView.isCurrentItem
            onClicked: list.clickRow(index)
        }
    }
    buttons: [
        ArButton {
            text: "Cancel"
            variant: "ghost"
            onClicked: picker.close()
        },
        ArButton {
            text: picker.actionText
            variant: "primary"
            enabled: list.currentIndex >= 0 && list.currentIndex < picker.shown.length
            onClicked: picker.choose()
        }
    ]
}
