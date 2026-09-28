pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "Weather.js" as Weather

// The weather under the calendar's month grid (WeatherService): now, and five days. For the
// calendar panel: Loader { active: WeatherService.enabled; sourceComponent: WeatherCard { width: … } }.
// Opening it asks for a new reading when the last one is older than 30 minutes. No amber: the
// weather isn't "here".
Item {
    id: card
    implicitHeight: body.implicitHeight
    implicitWidth: 280
    Component.onCompleted: WeatherService.refresh(1800)
    Accessible.role: Accessible.StaticText
    Accessible.name: WeatherService.summary || WeatherService.problem

    ColumnLayout {
        id: body
        width: card.width
        spacing: Theme.space3

        // Now: glyph, temperature, words.
        RowLayout {
            visible: !!WeatherService.current
            spacing: Theme.space3
            Image {
                Layout.preferredWidth: 32
                Layout.preferredHeight: 32
                sourceSize: Qt.size(32, 32)
                source: WeatherService.current ? Weather.icon(Weather.describe(WeatherService.current.code, WeatherService.current.is_day).glyph, Theme.ink) : ''
            }
            Text {
                text: WeatherService.current ? Weather.tempText(WeatherService.current.temp) : ''
                color: Theme.ink
                font.family: Theme.fontSans
                font.pixelSize: 28
                font.weight: Font.DemiBold
                font.features: { 'tnum': 1 }
            }
            Text {
                Layout.fillWidth: true
                text: WeatherService.current ? Weather.describe(WeatherService.current.code, WeatherService.current.is_day).text
                                               + (WeatherService.current.feels !== null && WeatherService.current.feels !== undefined
                                                  ? ' · feels ' + Weather.tempText(WeatherService.current.feels) : '') : ''
                color: Theme.inkMuted
                font.family: Theme.fontSans
                font.pixelSize: 13
                wrapMode: Text.WordWrap
            }
        }

        // Five days.
        RowLayout {
            visible: WeatherService.daily.length > 0
            Layout.fillWidth: true
            spacing: 0
            Repeater {
                model: WeatherService.daily
                ColumnLayout {
                    id: day
                    required property var modelData
                    Layout.preferredWidth: body.width / Math.max(1, WeatherService.daily.length)
                    spacing: Theme.space1
                    Accessible.role: Accessible.StaticText
                    Accessible.name: Weather.dayName(modelData.date, WeatherService.daily[0].date) + ', '
                                     + Weather.describe(modelData.code, true).text + ', ' + Weather.tempText(modelData.max)
                                     + ' to ' + Weather.tempText(modelData.min)
                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: Weather.dayName(day.modelData.date, WeatherService.daily[0].date)
                        color: Theme.inkMuted
                        font.family: Theme.fontSans
                        font.pixelSize: 12
                    }
                    Image {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.preferredWidth: 20
                        Layout.preferredHeight: 20
                        sourceSize: Qt.size(20, 20)
                        source: Weather.icon(Weather.describe(day.modelData.code, true).glyph, Theme.ink)
                    }
                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: Weather.tempText(day.modelData.max) + ' ' + Weather.tempText(day.modelData.min)
                        color: Theme.ink
                        font.family: Theme.fontSans
                        font.pixelSize: 12
                        font.features: { 'tnum': 1 }
                    }
                }
            }
        }

        // Where, whose data, how fresh; or why there is nothing to show.
        Text {
            Layout.fillWidth: true
            text: WeatherService.reading
                  ? [WeatherService.place, WeatherService.reading.attribution || 'Open-Meteo.com',
                     Weather.updatedText(WeatherService.reading.fetched_at, WeatherService.now)].filter(s => s).join(' · ')
                  : (WeatherService.problem || 'Getting the weather…')
            color: Theme.inkSubtle
            font.family: Theme.fontSans
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }
    }
}
