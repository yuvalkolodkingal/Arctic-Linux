import QtQuick
import "Weather.js" as Weather

// The temperature on the bar, right of the clock (Settings > Appearance > Weather > "Show the
// temperature on the bar"): a glyph and "21°". Shown only with a reading; the bar decides what
// a click opens (the calendar). For Bar.qml: WeatherItem { visible: WeatherService.showInBar }.
BarItem {
    id: item
    tooltip: WeatherService.summary
    Image {
        width: 16
        height: 16
        sourceSize: Qt.size(16, 16)
        source: WeatherService.current ? Weather.icon(Weather.describe(WeatherService.current.code, WeatherService.current.is_day).glyph, item.iconColor) : ''
    }
    Text {
        text: WeatherService.current ? Weather.tempText(WeatherService.current.temp) : ''
        color: item.textColor
        font.family: Theme.fontSans
        font.pixelSize: 13
        font.weight: Font.Medium
        font.features: { 'tnum': 1 }
    }
}
