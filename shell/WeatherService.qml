pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import "Weather.js" as Weather

// Weather for the calendar and the bar (scripts/weather.py, Open-Meteo). Nothing is asked until
// shell.json says "weather": true (Settings > Appearance > Weather). Then: 10 s after the shell
// starts, every hour, and when a card asks for it with an older reading (refresh(1800)). Skipped
// while offline; the last reading stays, with its "updated" time.
Singleton {
    id: service

    readonly property bool enabled: Session.settings.weather === true
    readonly property bool showInBar: enabled && Session.settings.barWeather === true && !!current
    readonly property string units: ['metric', 'imperial'].indexOf(Session.settings.weatherUnits) >= 0 ? Session.settings.weatherUnits : 'auto'
    readonly property bool online: !NetworkService.available || NetworkService.state === 'connected'

    property var reading: null           // weather.py's JSON (ok: true), or the last one kept
    property string problem: ''          // why there is no fresh reading ('' when fine)
    readonly property var current: reading ? reading.current : null
    readonly property var daily: reading ? reading.daily || [] : []
    readonly property string place: reading ? reading.place || '' : ''
    readonly property string summary: Weather.summary(reading)
    property real now: Date.now() / 1000

    // maxAge: how old a reading may be (seconds) before weather.py asks again.
    function refresh(maxAge) {
        if (!enabled || fetch.running || !online)
            return;
        fetch.command = ['python3', Session.scripts + '/weather.py', 'now', '--units', service.units,
                         '--max-age', String(maxAge === undefined ? 3600 : maxAge), '--json'];
        fetch.running = true;
    }

    onEnabledChanged: if (enabled) startTimer.restart(); else { reading = null; problem = ''; }
    onUnitsChanged: if (enabled && reading) refresh(0)      // not at start: shell.json arriving isn't a change
    onOnlineChanged: if (enabled && online && !reading) refresh(3600)

    Process {
        id: fetch
        stdout: StdioCollector {
            onStreamFinished: {
                let data = null;
                try { data = JSON.parse(text); } catch (e) { data = null; }
                service.now = Date.now() / 1000;
                if (data && data.ok) {
                    service.reading = data;
                    service.problem = '';
                } else {
                    if (data && data.cached && !service.reading) service.reading = data.cached;
                    service.problem = data && data.error ? data.error : 'The weather couldn’t be read.';
                }
            }
        }
    }
    Timer {
        id: startTimer
        interval: 10000
        running: service.enabled
        onTriggered: service.refresh(3600)
    }
    Timer {
        interval: 3600 * 1000
        repeat: true
        running: service.enabled
        onTriggered: service.refresh(3000)
    }
    Timer {                              // "updated 2 h ago" keeps up
        interval: 60 * 1000
        repeat: true
        running: service.enabled && !!service.reading
        onTriggered: service.now = Date.now() / 1000
    }
}
