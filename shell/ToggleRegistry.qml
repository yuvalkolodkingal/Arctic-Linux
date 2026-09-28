pragma Singleton
import QtQuick
import Quickshell

// Every on/off switch the shell knows, in Quick Settings order: the tiles, the `toggle` IPC
// target (`arctic-shell-ipc toggle set wifi off`) and the mode indicators all read this.
// Other sections add their Toggle entries here (the file is shared); helpers they ship
// (arctic-nightlight, arctic-keep-awake) appear as tiles once installed.
Singleton {
    id: registry

    readonly property var toggles: [wifi, bluetooth, dnd, nightLight, keepAwake, darkMode, powerMode, mic, vpn]
    readonly property var visibleToggles: toggles.filter(t => t.available)

    function byKey(key) { return toggles.find(t => t.key === key) || null; }
    // mode: on, off or toggle. Returns the new state, or "unavailable".
    function set(key, mode) {
        const t = byKey(key);
        if (!t || !t.available) return 'unavailable';
        if (mode === 'toggle') t.toggle();
        else t.set(mode === 'on');
        return mode === 'toggle' ? (t.active ? 'off' : 'on') : mode;
    }
    function get(key) {
        const t = byKey(key);
        return !t || !t.available ? 'unavailable' : t.kind === 'cycle' ? t.detail : t.active ? 'on' : 'off';
    }
    function states() {
        const out = {};
        toggles.forEach(t => { out[t.key] = t.available ? (t.kind === 'cycle' ? t.detail : t.active) : null; });
        return JSON.stringify(out);
    }
    function refresh(key) { toggles.forEach(t => { if ((!key || t.key === key) && t.refresh) t.refresh(); }); }

    Toggle {
        id: wifi
        key: 'wifi'
        label: 'Wi-Fi'
        icon: 'wifi'
        iconOff: 'wifi-off'
        page: 'network'
        available: NetworkService.available && NetworkService.wifi !== null
        active: NetworkService.wifiEnabled
        detail: !active ? 'Off' : NetworkService.wifiActive ? NetworkService.wifiActive.name : 'Not connected'
        setter: on => NetworkService.run(['radio', 'wifi', on ? 'on' : 'off'], null, null)
    }
    Toggle {
        id: bluetooth
        key: 'bluetooth'
        label: 'Bluetooth'
        icon: 'bluetooth'
        page: 'bluetooth'
        keys: 'Super + Ctrl + B'
        available: BluetoothService.available
        active: BluetoothService.enabled
        detail: !active ? 'Off' : BluetoothService.connected.length ? BluetoothService.connected[0].name : 'On'
        setter: on => BluetoothService.setEnabled(on)
    }
    Toggle {
        id: dnd
        key: 'dnd'
        label: 'Do not disturb'
        icon: 'bell-off'
        iconOff: 'bell'
        keys: 'Super + Shift + N'
        available: DndService.available
        active: DndService.active
        setter: on => { if (on !== DndService.active) DndService.toggle(); }
    }
    HelperToggle {
        id: nightLight
        key: 'night-light'
        label: 'Night light'
        icon: 'moon'
        helper: 'arctic-nightlight'
        keys: 'Super + Ctrl + N'
        indicator: true
        indicatorText: 'Night light is on · click to turn it off'
    }
    HelperToggle {
        id: keepAwake
        key: 'keep-awake'
        label: 'Keep awake'
        icon: 'coffee'
        helper: 'arctic-keep-awake'
        keys: 'Super + Ctrl + I'
        indicator: true
        indicatorText: 'The screen stays on · click to let it sleep again'
    }
    Toggle {
        id: darkMode
        key: 'dark-mode'
        label: 'Dark style'
        icon: 'brush'
        keys: 'Super + Shift + T'
        available: Tools.has('arctic-theme')
        active: Theme.dark
        detail: active ? 'Dark' : 'Light'
        setter: on => { if (on !== Theme.dark) Quickshell.execDetached(['arctic-theme', 'toggle']); }
    }
    Toggle {
        id: powerMode
        key: 'power-mode'
        label: 'Power mode'
        icon: PowerService.current ? PowerService.current.icon : 'gauge'
        kind: 'cycle'
        page: 'battery'
        keys: 'Super + Ctrl + P'
        available: PowerService.available
        active: false
        detail: PowerService.current ? PowerService.current.label : ''
        setter: on => PowerService.cycle()
    }
    Toggle {
        id: mic
        key: 'mic'
        label: 'Microphone'
        icon: 'mic'
        iconOff: 'mic-off'
        page: 'sound'
        available: AudioService.sourceAvailable
        active: !AudioService.sourceMuted
        detail: active ? 'On' : 'Muted'
        indicator: true
        indicatorShown: available && !active
        indicatorText: 'The microphone is muted · click to unmute'
        setter: on => { if (on === AudioService.sourceMuted) AudioService.toggleSourceMute(); }
    }
    Toggle {
        id: vpn
        key: 'vpn'
        label: 'VPN'
        icon: 'key'
        page: 'network'
        available: NetworkService.available && NetworkService.vpn.length > 0
        active: NetworkService.vpnActive
        detail: active ? NetworkService.vpn.filter(v => v.active).map(v => v.name).join(', ') : 'Off'
        indicator: true
        indicatorText: 'A VPN is on · click to turn it off'
        // On: the profile used most recently; off: every active one.
        setter: on => {
            if (on) {
                const last = NetworkService.vpn.slice().sort((a, b) => b.last_used - a.last_used)[0];
                if (last) NetworkService.run(['vpn-up', '--uuid', last.uuid, '--name', last.name], null, null);
            } else {
                NetworkService.vpn.filter(v => v.active).forEach(v => NetworkService.run(['vpn-down', '--uuid', v.uuid], null, null));
            }
        }
    }
}
