.pragma library

// Weather for the calendar (WeatherService.qml, WeatherCard.qml, WeatherItem.qml): WMO weather
// codes as Open-Meteo reports them -> words and a glyph, temperatures, day names and "updated"
// text. Pure, so tests/test-weather.cjs runs it in Node.
//
// The glyphs follow the design's icon rules (24 grid, 1.75 stroke set by the builder, round caps
// and joins, no fill) and live here until the design system has weather glyphs of its own; sun,
// moon and snowflake are the shell's own drawings (icons-extra / design-data).

var GLYPHS = {
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2 M12 19.5v2 M2.5 12h2 M19.5 12h2 M5.3 5.3l1.4 1.4 M17.3 17.3l1.4 1.4 M5.3 18.7l1.4-1.4 M17.3 6.7l1.4-1.4"/>',
    moon: '<path d="M19 14.5A7.5 7.5 0 1 1 9.5 5a6 6 0 0 0 9.5 9.5z"/>',
    cloud: '<path d="M7.5 18h9.5a4 4 0 0 0 .5-7.97 5.5 5.5 0 0 0-10.4 1.1A3.5 3.5 0 0 0 7.5 18z"/>',
    'cloud-sun': '<circle cx="8" cy="8" r="2.5"/><path d="M8 3.5v1 M3.5 8h1 M4.8 4.8l.7.7 M11.2 4.8l-.7.7"/>'
        + '<path d="M10 19.5h8a3.5 3.5 0 0 0 .4-6.98 4.8 4.8 0 0 0-9.1 1A3 3 0 0 0 10 19.5z"/>',
    'cloud-moon': '<path d="M11 7.2A3.6 3.6 0 1 1 6.3 3a3 3 0 0 0 4.7 4.2z"/>'
        + '<path d="M10 19.5h8a3.5 3.5 0 0 0 .4-6.98 4.8 4.8 0 0 0-9.1 1A3 3 0 0 0 10 19.5z"/>',
    'cloud-rain': '<path d="M7.5 15h9.5a4 4 0 0 0 .5-7.97 5.5 5.5 0 0 0-10.4 1.1A3.5 3.5 0 0 0 7.5 15z"/>'
        + '<path d="M8.5 18l-1 2.5 M12.5 18l-1 2.5 M16.5 18l-1 2.5"/>',
    'cloud-lightning': '<path d="M7.5 15h9.5a4 4 0 0 0 .5-7.97 5.5 5.5 0 0 0-10.4 1.1A3.5 3.5 0 0 0 7.5 15z"/>'
        + '<path d="M12.5 15.5L10.5 19h3l-2 3.5"/>',
    fog: '<path d="M4 9h16 M6 13h13 M4 17h11"/>',
    snowflake: '<path d="M12 3v18 M4.2 7.5l15.6 9 M4.2 16.5l15.6-9 M9.6 4.6L12 6.6l2.4-2 M9.6 19.4L12 17.4l2.4 2"/>'
};

// WMO code -> [words, day glyph, night glyph] (Open-Meteo's "Weather variable documentation").
function describe(code, isDay) {
    var c = Number(code);
    var row;
    if (c === 0) row = ['Clear', 'sun', 'moon'];
    else if (c === 1) row = ['Mostly clear', 'cloud-sun', 'cloud-moon'];
    else if (c === 2) row = ['Partly cloudy', 'cloud-sun', 'cloud-moon'];
    else if (c === 3) row = ['Cloudy', 'cloud', 'cloud'];
    else if (c === 45 || c === 48) row = ['Fog', 'fog', 'fog'];
    else if (c >= 51 && c <= 57) row = ['Drizzle', 'cloud-rain', 'cloud-rain'];
    else if (c >= 61 && c <= 67) row = [c === 66 || c === 67 ? 'Freezing rain' : 'Rain', 'cloud-rain', 'cloud-rain'];
    else if ((c >= 71 && c <= 77) || c === 85 || c === 86) row = ['Snow', 'snowflake', 'snowflake'];
    else if (c >= 80 && c <= 82) row = ['Showers', 'cloud-rain', 'cloud-rain'];
    else if (c >= 95 && c <= 99) row = ['Thunderstorm', 'cloud-lightning', 'cloud-lightning'];
    else row = ['Cloudy', 'cloud', 'cloud'];
    return { text: row[0], glyph: isDay === false ? row[2] : row[1] };
}

// "21°" (rounded; the unit is the reading's: °C for metric, °F for imperial, said once elsewhere).
function tempText(t) {
    if (t === null || t === undefined || isNaN(Number(t))) return '–';
    var n = Math.round(Number(t));
    return (n === 0 ? 0 : n) + '°';
}

function unitText(units) {
    return units === 'imperial' ? '°F' : '°C';
}

var DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

// "2026-09-29" -> "Tue"; today -> "Today".
function dayName(date, today) {
    if (date === today) return 'Today';
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(date || ''));
    if (!m) return '';
    return DAYS[new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])).getUTCDay()];
}

// "updated 14:05", or "updated 2 h ago" when the reading is old (offline).
function updatedText(fetchedAt, nowSeconds) {
    if (!fetchedAt) return '';
    var age = nowSeconds - fetchedAt;
    if (age >= 2 * 3600) return 'updated ' + Math.floor(age / 3600) + ' h ago';
    var d = new Date(fetchedAt * 1000);
    var hh = String(d.getHours()), mm = String(d.getMinutes());
    return 'updated ' + (hh.length < 2 ? '0' : '') + hh + ':' + (mm.length < 2 ? '0' : '') + mm;
}

// A glyph as an image source, drawn in exactly the colour asked for (the design's icon builder).
function icon(name, color) {
    var s = String(color);
    var ink = s.length === 9 ? '#' + s.slice(3) : s;
    var body = GLYPHS[name] || GLYPHS.cloud;
    return 'data:image/svg+xml;utf8,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="'
        + ink + '" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">' + body + '</svg>');
}

// One line for a tooltip or screen reader: "Partly cloudy, 21° in Jerusalem".
function summary(reading) {
    if (!reading || !reading.current) return '';
    var d = describe(reading.current.code, reading.current.is_day);
    return d.text + ', ' + tempText(reading.current.temp) + (reading.place ? ' in ' + reading.place : '');
}
