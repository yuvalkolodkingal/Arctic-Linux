pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Services.UPower
import "BatteryModel.js" as BatteryModel

// The laptop battery for the bar item, the battery menu and the lock screen (UPower through
// Quickshell), what UPower has beyond that (scripts/battery.py: charge limit, warning levels,
// the critical action), other devices' batteries, and the low and critical warnings: one
// notification each per discharge, cleared when charging starts. Settings' "Warn me when the
// battery is low" (shell.json batteryWarnings) turns the low one off; the critical one always
// shows, even under do not disturb (an Arctic alert). Once per discharge, at the low level, your
// battery-low hooks run too (arctic-hook battery-low PERCENT, when it is installed), whether the
// warning shows or not.
Singleton {
    id: battery
    // UPower's aggregate includes all laptop batteries, weighted by capacity.
    readonly property var device: UPower.displayDevice
    readonly property bool present: device !== null && device.ready && device.isLaptopBattery && device.isPresent
    readonly property int percent: present ? BatteryModel.percentage(device.percentage) : -1
    readonly property bool chargeKnown: percent >= 0
    readonly property string percentText: BatteryModel.percentageText(percent)
    readonly property bool charging: present && (device.state === UPowerDeviceState.Charging || device.state === UPowerDeviceState.PendingCharge)
    readonly property bool full: present && device.state === UPowerDeviceState.FullyCharged
    readonly property bool onBattery: UPower.onBattery
    readonly property bool health: present && device.healthSupported
    readonly property int healthPercent: health ? Math.round(device.healthPercentage) : 0
    readonly property bool low: present && chargeKnown && !charging && !full && percent <= info.percentage_low
    readonly property string timeText: full ? 'Fully charged'
        : charging ? (device.timeToFull > 0 ? 'Charging · full in ' + duration(device.timeToFull) : 'Charging')
        : present && device.state === UPowerDeviceState.Unknown ? 'Status unavailable'
        : present && device.timeToEmpty > 0 ? duration(device.timeToEmpty) + ' left'
        : present && !onBattery ? 'Plugged in, not charging' : ''
    // Mice, keyboards, headsets, phones: UPower devices that report a charge.
    readonly property var peripherals: UPower.devices.values.filter(d => d.ready && !d.isLaptopBattery && d.isPresent
        && d.type !== UPowerDeviceType.LinePower && d.type !== UPowerDeviceType.Battery && d.type !== UPowerDeviceType.Ups && d.percentage > 0)
    property var info: ({ percentage_low: 20, percentage_critical: 5, percentage_action: 2, critical_action: 'suspend',
                          threshold_supported: false, threshold_enabled: false, threshold_end: 0 })
    property bool warnedLow: false
    property bool warnedCritical: false
    property bool hookedLow: false
    property var warnedDevices: ({})

    function duration(seconds) {
        const h = Math.floor(seconds / 3600), m = Math.round((seconds % 3600) / 60);
        return h > 0 ? h + ' h ' + m + ' min' : m + ' min';
    }
    function kindOf(d) {
        switch (d.type) {
        case UPowerDeviceType.Mouse: return { icon: 'mouse', name: 'Mouse' };
        case UPowerDeviceType.Keyboard: return { icon: 'keyboard', name: 'Keyboard' };
        case UPowerDeviceType.Phone: return { icon: 'phone', name: 'Phone' };
        case UPowerDeviceType.GamingInput: return { icon: 'gamepad', name: 'Controller' };
        case UPowerDeviceType.Headset: return { icon: 'headset', name: 'Headset' };
        case UPowerDeviceType.Headphones: return { icon: 'headphones', name: 'Headphones' };
        }
        return { icon: 'battery', name: 'Device' };
    }
    function refresh() { if (!query.running) query.running = true; }
    function percentOf(d) { return BatteryModel.percentage(d.percentage); }
    function percentTextOf(d) { return BatteryModel.percentageText(percentOf(d)); }
    function setLimit(on, callback) {
        limit.callback = callback || null;
        limit.command = ['python3', Session.scripts + '/battery.py', 'limit', on ? 'on' : 'off'];
        limit.running = true;
    }
    function notify(args) { Quickshell.execDetached(['notify-send'].concat(args)); }

    function check() {
        if (!present) return;
        if (charging || full || !onBattery) { warnedLow = false; warnedCritical = false; hookedLow = false; return; }
        if (!chargeKnown) return;
        if (percent <= info.percentage_low && !hookedLow) {
            hookedLow = true;
            Quickshell.execDetached(['sh', '-c', 'command -v arctic-hook >/dev/null 2>&1 && exec arctic-hook battery-low "$1"', 'sh', String(percent)]);
        }
        if (percent <= info.percentage_critical && !warnedCritical) {
            warnedCritical = true;
            warnedLow = true;
            const verb = info.critical_action;
            notify(['-u', 'critical', '-a', 'Arctic Linux', '-i', 'battery-caution', '-h', 'boolean:x-arctic-alert:true',
                    'Battery at ' + percent + ' %',
                    verb === 'nothing' ? 'Plug in to keep working.'
                        : 'Arctic will ' + verb + ' at ' + info.percentage_action + ' %. Plug in to keep working.']);
        } else if (percent <= info.percentage_low && !warnedLow && Session.settings.batteryWarnings !== false) {
            warnedLow = true;
            notify(['-a', 'Arctic Linux', '-i', 'battery-low', 'Battery at ' + percent + ' %',
                    (device.timeToEmpty > 0 ? 'About ' + duration(device.timeToEmpty) + ' left. ' : '') + 'Plug in soon.']);
        }
    }
    function checkPeripherals() {
        const seen = Object.assign({}, warnedDevices);
        peripherals.forEach(d => {
            const key = d.nativePath || d.model;
            const p = percentOf(d);
            if (p < 0) return;
            if (p > 15) { seen[key] = false; return; }
            if (p <= 10 && !seen[key]) {
                seen[key] = true;
                notify(['-a', 'Arctic Linux', '-i', 'battery-low', kindOf(d).name + ' battery at ' + p + ' %', d.model || '']);
            }
        });
        warnedDevices = seen;
    }
    onPercentChanged: check()
    onChargingChanged: check()
    onOnBatteryChanged: check()
    onPeripheralsChanged: checkPeripherals()
    Timer { interval: 120000; running: battery.peripherals.length > 0; repeat: true; onTriggered: battery.checkPeripherals() }

    Process {
        id: query
        command: ['python3', Session.scripts + '/battery.py', 'status']
        running: battery.present
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const data = JSON.parse(text);
                    if (data.ok) { battery.info = Object.assign({}, battery.info, data); battery.check(); }
                } catch (e) {}
            }
        }
    }
    Process {
        id: limit
        property var callback: null
        stdout: StdioCollector {
            onStreamFinished: {
                let result = null;
                try { result = JSON.parse(text); } catch (e) {}
                if (!result) result = { ok: false, error: 'The battery helper didn’t answer.' };
                if (limit.callback) limit.callback(result);
                battery.refresh();
            }
        }
    }
}
