pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Services.UPower

// Power mode (power saver / balanced / performance) through the power-profiles D-Bus API that
// tuned-ppd provides (org.freedesktop.UPower.PowerProfiles), with Quickshell's PowerProfiles.
// tuned-ppd ships no powerprofilesctl, so nothing here runs a command. Hidden without the service.
Singleton {
    id: power
    property bool available: false
    readonly property int profile: PowerProfiles.profile
    readonly property bool hasPerformance: PowerProfiles.hasPerformanceProfile
    readonly property string degradation: PowerProfiles.degradationReason === PerformanceDegradationReason.HighTemperature
        ? 'Performance is limited because the computer is hot.'
        : PowerProfiles.degradationReason === PerformanceDegradationReason.LapDetected
        ? 'Performance is limited because the computer is on your lap.' : ''
    readonly property var modes: [
        { profile: PowerProfile.PowerSaver, key: 'power-saver', label: 'Power saver', icon: 'leaf', detail: 'Longer battery life, a bit slower' },
        { profile: PowerProfile.Balanced, key: 'balanced', label: 'Balanced', icon: 'gauge', detail: 'Speed and battery life in balance' },
        { profile: PowerProfile.Performance, key: 'performance', label: 'Performance', icon: 'bolt', detail: 'Fastest, uses more power' }
    ].filter(m => m.profile !== PowerProfile.Performance || hasPerformance)
    readonly property var current: modes.find(m => m.profile === profile) || null

    function set(p) { if (available) PowerProfiles.profile = p; }
    // Balanced → Power saver → Performance → Balanced (the Quick Settings tile).
    function cycle() {
        const seq = [PowerProfile.Balanced, PowerProfile.PowerSaver, PowerProfile.Performance]
            .filter(p => modes.some(m => m.profile === p));
        set(seq[(seq.indexOf(profile) + 1) % seq.length]);
    }

    Process {
        running: true
        command: ['gdbus', 'introspect', '--system', '--dest', 'org.freedesktop.UPower.PowerProfiles',
                  '--object-path', '/org/freedesktop/UPower/PowerProfiles']
        stdout: StdioCollector {}
        onExited: code => power.available = code === 0
    }
}
