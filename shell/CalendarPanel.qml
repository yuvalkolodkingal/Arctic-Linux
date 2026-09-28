pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import "CalendarGrid.js" as Grid

// The calendar under the clock (Super + Ctrl + T): today's date and time zone, and a month
// with ISO week numbers. Today is marked (accent-soft, the "here" of the calendar); the
// keyboard day has the focus ring. Arrows move the day, PgUp/PgDn the month (Shift: the
// year), Home comes back to today, Esc closes.
FocusScope {
    id: panel
    property var menu: null
    property var today: new Date()
    property var cursor: new Date(today.getFullYear(), today.getMonth(), today.getDate())
    property string zone: ''
    readonly property int firstDay: Qt.locale().firstDayOfWeek
    readonly property var rows: Grid.monthGrid(cursor.getFullYear(), cursor.getMonth(), firstDay, today)
    readonly property var dayNames: {
        const out = [];
        for (let i = 0; i < 7; i++) out.push(Qt.locale().dayName((firstDay + i) % 7, Locale.ShortFormat));
        return out;
    }

    implicitWidth: 300
    implicitHeight: column.implicitHeight + 2 * Theme.space3
    focus: true

    function offsetText() {
        const minutes = -new Date().getTimezoneOffset();
        const sign = minutes >= 0 ? '+' : '−';
        const h = Math.floor(Math.abs(minutes) / 60), m = Math.abs(minutes) % 60;
        return 'UTC' + sign + h + (m ? ':' + String(m).padStart(2, '0') : '');
    }
    function move(date) { cursor = date; }

    Keys.onPressed: event => {
        MenuState.keyboardNav = true;
        const shift = event.modifiers & Qt.ShiftModifier;
        if (event.key === Qt.Key_Left) move(Grid.addDays(cursor, -1));
        else if (event.key === Qt.Key_Right) move(Grid.addDays(cursor, 1));
        else if (event.key === Qt.Key_Up) move(Grid.addDays(cursor, -7));
        else if (event.key === Qt.Key_Down) move(Grid.addDays(cursor, 7));
        else if (event.key === Qt.Key_PageUp) move(Grid.addMonths(cursor, shift ? -12 : -1));
        else if (event.key === Qt.Key_PageDown) move(Grid.addMonths(cursor, shift ? 12 : 1));
        else if (event.key === Qt.Key_Home) move(new Date(today.getFullYear(), today.getMonth(), today.getDate()));
        else return;
        event.accepted = true;
    }

    // The time zone, read once per open.
    Process {
        running: true
        command: ['sh', '-c', 'timedatectl show -p Timezone --value 2>/dev/null || readlink /etc/localtime | sed "s|.*/zoneinfo/||"']
        stdout: StdioCollector { onStreamFinished: panel.zone = text.trim() }
    }
    SystemClock { id: clock; precision: SystemClock.Minutes; onDateChanged: panel.today = date }

    ColumnLayout {
        id: column
        anchors.fill: parent
        anchors.margins: Theme.space3
        spacing: Theme.space2

        ColumnLayout {
            Layout.fillWidth: true
            Layout.leftMargin: Theme.space1
            spacing: 2
            Text {
                text: Qt.locale().toString(panel.today, 'dddd d MMMM yyyy')
                color: Theme.ink
                font.family: Theme.fontSans
                font.pixelSize: 16
                font.weight: Font.DemiBold
                Accessible.role: Accessible.Heading
            }
            Text {
                text: (panel.zone ? panel.zone.replace(/_/g, ' ') + ' · ' : '') + panel.offsetText()
                color: Theme.inkMuted
                font.family: Theme.fontSans
                font.pixelSize: 12
                font.features: { 'tnum': 1 }
            }
        }
        MenuSeparator { Layout.fillWidth: true }
        RowLayout {
            Layout.fillWidth: true
            Text {
                Layout.fillWidth: true
                Layout.leftMargin: Theme.space1
                text: Qt.locale().standaloneMonthName(panel.cursor.getMonth()) + ' ' + panel.cursor.getFullYear()
                color: Theme.ink
                font.family: Theme.fontSans
                font.pixelSize: 15
                font.weight: Font.DemiBold
                Accessible.role: Accessible.Heading
            }
            ArcticButton {
                iconName: 'chevron-left'
                iconOnly: true
                label: 'Previous month'
                variant: 'ghost'
                size: 'sm'
                focusPolicy: Qt.NoFocus
                onClicked: panel.move(Grid.addMonths(panel.cursor, -1))
            }
            ArcticButton {
                iconName: 'chevron-right'
                iconOnly: true
                label: 'Next month'
                variant: 'ghost'
                size: 'sm'
                focusPolicy: Qt.NoFocus
                onClicked: panel.move(Grid.addMonths(panel.cursor, 1))
            }
        }
        GridLayout {
            Layout.fillWidth: true
            columns: 8
            rowSpacing: 2
            columnSpacing: 2
            Item { implicitWidth: 28; implicitHeight: 20 }
            Repeater {
                model: panel.dayNames
                Text {
                    required property string modelData
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    text: modelData
                    color: Theme.inkSubtle
                    font.family: Theme.fontSans
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                }
            }
            Repeater {
                model: panel.rows.length * 8
                Item {
                    id: cell
                    required property int index
                    readonly property var row: panel.rows[Math.floor(index / 8)]
                    readonly property bool weekCell: index % 8 === 0
                    readonly property var day: weekCell ? null : row.days[index % 8 - 1]
                    readonly property bool isCursor: day !== null && Grid.sameDay(day.date, panel.cursor)
                    Layout.fillWidth: true
                    implicitWidth: weekCell ? 28 : 32
                    implicitHeight: 32
                    Rectangle {
                        visible: !cell.weekCell
                        anchors.centerIn: parent
                        width: 32
                        height: 32
                        radius: 16
                        color: cell.day && cell.day.isToday ? Theme.accentSoft : dayMouse.containsMouse ? Theme.surfaceSunken : 'transparent'
                        border.width: cell.day && cell.day.isToday ? 1 : 0
                        border.color: Theme.accentEdge
                        FocusRing { targetRadius: 16; shown: cell.isCursor && MenuState.keyboardNav }
                    }
                    Text {
                        anchors.centerIn: parent
                        text: cell.weekCell ? 'W' + cell.row.week : cell.day.day
                        color: cell.weekCell ? Theme.inkSubtle : cell.day.isToday ? Theme.accentText : cell.day.inMonth ? Theme.ink : Theme.inkSubtle
                        font.family: Theme.fontSans
                        font.pixelSize: cell.weekCell ? 11 : 13
                        font.weight: cell.day && cell.day.isToday ? Font.DemiBold : Font.Normal
                        font.features: { 'tnum': 1 }
                    }
                    MouseArea {
                        id: dayMouse
                        anchors.fill: parent
                        enabled: !cell.weekCell
                        hoverEnabled: true
                        onClicked: { MenuState.keyboardNav = false; panel.move(cell.day.date); }
                    }
                    Accessible.role: cell.weekCell ? Accessible.RowHeader : Accessible.Cell
                    Accessible.name: cell.weekCell ? 'Week ' + cell.row.week : Qt.locale().toString(cell.day.date, 'dddd d MMMM')
                }
            }
        }
    }
}
