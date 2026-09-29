# Arctic Linux 0.3 — Custom bar menus and Quick Settings

Part of the [0.3 plan](../PLAN-0.3.md).

Request #3: "all dropdowns are customized (wifi, bluetooth, etc)". Every bar item opens an
Arctic menu drawn by the shell instead of nm-applet's QMenu, blueman-manager, pavucontrol or
Qt's stock tray QMenu. A Quick Settings card (`Super + A`) hosts the same panels. This ships in
Arctic Linux 0.3.0 (D1) and follows D5 (per-item menus, QML tray menus, Quick Settings, nmcli
helper for Wi-Fi, python3-dbus BlueZ agent, Fedora 44's Quickshell 0.2.1 snapshot), D6 (a shell
NotificationServer replaces mako in the Quickshell session), D7 (every new key checked) and D9
(tokens only, amber only for "here", new icons in the design-data.js style).

Gap items covered here: `control-center`, `panel-hotkeys-bar-focus`, `mode-indicators`,
`privacy-indicators`, `audio-panel-scope`, `bluetooth-pairing-agent`, `notification-center`,
`calendar-popover`, `media-controls`, `battery-health-limit`, `keyboard-layout-indicator`,
`wifi-extras`, `vpn-quick-connect`, `external-brightness-ddc`, `low-battery-warnings` (UI part)
and `quickshell-031` (deferred, 16). Every correction from `gap-verification.json` for these
items is applied; they are listed in 2.7.

🔍 marks a claim that still needs a hands-on check; each one says what proves it. All
file:line references were checked against the repository at `51cce98` (Arctic Linux 0.2.1).

### 1. What ships

| Piece | Where | Replaces |
|---|---|---|
| One menu host, `BarMenu.qml`, and a shared toolkit (`MenuRow`, `MenuSwitchRow`, `MenuSlider`, `MenuSection`, …) | shell/ | the one-off rows in `PowerMenu.qml` and `UpdatePopover.qml` |
| Network menu: Wi-Fi scan / join / password / forget / hidden network / 802.1X / share as QR / hotspot, wired row, VPN and WireGuard switches, Tailscale row, airplane mode | `NetworkPanel.qml`, `scripts/network.py` | nm-applet's QMenu and GTK password dialogs, nm-connection-editor as the click target |
| Bluetooth menu: power, scan, pair, connect, forget, rename, battery; pairing codes in a shell dialog | `BluetoothPanel.qml`, `BluetoothPairDialog.qml`, `scripts/bt-agent.py` | blueman-manager as the click target, blueman's agent |
| Sound menu: output/input sliders and device pickers, ports and profiles, per-app volume, mute | `SoundPanel.qml`, `scripts/audio.py` | pavucontrol as the click target |
| Notifications: the shell owns `org.freedesktop.Notifications`, toasts, a notification centre on the bell, do not disturb with durations and a schedule, per-app rules, history across restarts, "N notifications" on the lock screen | `NotificationService.qml`, `Toasts.qml`, `NotificationCenter.qml`, `arctic-notify` | mako in the Quickshell session |
| Calendar on the clock | `CalendarPanel.qml` | nothing (the clock had no action) |
| Battery and power: charge state, power mode over D-Bus, charge limit, health, peripheral batteries, low / critical warnings | `BatteryPanel.qml`, `BatteryService.qml`, `PowerService.qml`, `scripts/battery.py` | nothing (the battery item was `interactive: false`) |
| Media (MPRIS) on the bar, in a menu and on the lock screen | `MediaItem.qml`, `MediaPanel.qml`, `MediaService.qml` | nothing |
| Display page: brightness for the laptop panel and DDC/CI monitors | `DisplayPanel.qml`, `BrightnessService.qml`, `scripts/brightness.py` | nothing |
| Keyboard layout chip, layout menu, layout OSD, lock-screen reset | `KeyboardItem.qml`, `KeyboardPanel.qml`, `KeyboardService.qml`, `scripts/keyboard.py` | nothing |
| Tray menus drawn in QML | `TrayPanel.qml` (QsMenuOpener) | QsMenuAnchor → Qt Widgets QMenu |
| Quick Settings (`Super + A`) with a toggle registry used by tiles, IPC and mode indicators | `QuickSettingsPanel.qml`, `QuickTile.qml`, `ToggleRegistry.qml`, `Toggle.qml` | nothing |
| Mode and privacy indicators left of the clock | `ModeIndicators.qml`, `PrivacyService.qml` | nothing |
| Panel hotkeys and bar keyboard focus | `binds.conf`, `Bar.qml` | the never-built "Super + B bar focus" |

Not in 0.3.0, each with its reason in 16: packaging Quickshell 0.3.1 (D5), a NetworkManager
secret agent in the shell, per-app output routing, a live microphone level meter, editing
the Quick Settings tile set, Wi-Fi band pinning and DNS pickers, a tray drawer.

### 2. Current state

#### 2.1 What each bar item does today (`shell/Bar.qml`)

| Item | Lines | Left click | Other | Kind |
|---|---|---|---|---|
| Fox mark | 48-55 | `shell.toggleLauncher` | — | Arctic popover |
| Workspaces | 56-60 | switch workspace | — | no menu |
| Live session tag | 61-84 | tooltip only | — | — |
| Clock | 88-96 | plain `Text`, no MouseArea | — | none |
| Install (live) | 105-117 | `arctic-start-installer` | — | — |
| Restart to update | 118-122 (`UpdateIndicator.qml`) | `shell.toggleUpdates` → `UpdatePopover` | — | Arctic popover |
| Bell | 125-134 | `DndService.toggle()` (131) | right: `makoctl restore` (132) | none |
| Bluetooth | 135-147 | `execDetached(['blueman-manager'])` (144) | right: `adapter.enabled` toggle (145) | stock GTK app |
| Tray | 149-177 | `onlyMenu && hasMenu ? menu.open() : activate()` (164) | middle 165, right 166, scroll 167; filter `i.id !== 'nm-applet'` (151); `QsMenuAnchor` 169-175 | Qt Widgets QMenu (qt6ct/Fusion) |
| Network | 179-199 | nm-applet's DBusMenu via a second `QsMenuAnchor` (192-198) when the applet exists (182), else `nm-connection-editor` (186-189) | right: `nm-connection-editor` (190) | stock QMenu + GTK dialogs |
| Volume | 200-210 | `execDetached(['pavucontrol'])` (206) | right: mute (207), scroll: ±5 % (208) | stock app |
| Battery | 211-231 | `interactive: false` (223), tooltip only | — | none |
| Power | 232-238 | `shell.togglePower(screen, x)` (236) | — | Arctic popover |

`Bar.qml:29-30` routes hover to one `BarTooltip` per bar (`:33`); the tooltip keeps showing
while a menu is open. `BarItem.qml:16` has `keyboardFocused` with a `FocusRing` (`:35`) but
nothing sets it.

#### 2.2 Menu infrastructure

- `shell/Popover.qml:12-114`: a full-screen `PanelWindow` on the Overlay layer, below the bar
  (`margins.top: Theme.barHeight`, 40), exclusive keyboard while open (44, `grabKeyboard`
  property at 17), optional scrim whose MouseArea closes on outside press (69-81), Esc closes
  (99). `placement: 'point'` centres the card on `pointX` clamped to the screen (94) at
  `y = space1 + frameWidth` (97). The card is `PopupSurface` (`clip: true`) with a 1 px
  `Theme.line` border and no shadow (90-91). Height is whatever `cardHeight` says; nothing caps
  it to the screen.
- `shell/PowerMenu.qml` (90 lines): preset at 25-32 (`placement 'point'`, `scrim false`,
  `surfaceRaised`, `radiusLg`, width 232, `cardHeight: column.implicitHeight + 2*space1`),
  keys at 48-53 (Down/Up/Tab cycle, Return/Enter run, Esc close), 34 px rows at 56-87
  (`radiusSm`, `surfaceSunken` when selected, 18 px icon, 15 px label, optional `Kbd`).
  (The research map's "162-242" lines for this file are wrong; the file is 90 lines.)
- `shell/UpdatePopover.qml` (96 lines): the same preset at 9-16, width 340, `ArcticButton`s
  with `KeyNavigation` (72-93).
- `shell/shell.qml`: `closePopovers()` lists `[launcher, wallpapers, power, keys, updates]`
  (20-22); `present()` (23-27); `togglePower(screen, x)` (42-47) and `toggleUpdates` (49-55)
  take the bar item's centre from `item.mapToItem(null, item.width / 2, 0).x`
  (`Bar.qml:120, 236`); instances at 73-81 (`PolkitDialog {}` has no id, 81); IPC handlers at
  84-143 (`launcher`, `apps`, `wallpapers`, `power`, `keys`, `osd`, `lock`, `welcome`, `dnd`,
  `updates`, `shell`).
- Controls in the shell: `ArcticSwitch.qml` (40×24), `ArcticButton.qml`, `ArcticField.qml`
  (Controls.Basic `TextField`, error/success states), `Kbd.qml`, `Tip.qml`, `FocusRing.qml`
  (`shown`, `targetRadius`), `Icon.qml` (`assets/Icons.js` over the generated
  `assets/design-data.js`). No slider, list row, spinner, section header or shadow helper.
  Settings has `settings/components/ArSlider.qml` and `ShadowRect.qml` (offset layers,
  `Theme.shadowSm`/`shadowMd` at `settings/Theme.qml:75-77`).
- Mango's layer rules (`dotfiles/.config/mango/arctic/rules.conf`): line 15 gives
  `noblur:1,noshadow:1,noanim:1` to `^arctic-(frame|frame-reserve|launcher|popover|wallpapers|power|keys|polkit|osd|desktop)$`.
  `arctic-updates` (`UpdatePopover.qml:9`) is missing from that list today, so Mango may blur,
  shadow and animate the updates card; this section fixes it together with the new layers.
  Lines 4-7 note that a later matching layer rule resets `noblur/noanim/noshadow` to 0 unless
  it sets them.

#### 2.3 Data sources today

- Network: `shell/NetworkService.qml` (singleton, 55 lines) runs
  `nmcli -t -f TYPE,STATE,CONNECTION device status && echo "radio:$(nmcli radio wifi)"` (25),
  re-read on `nmcli monitor` (49) with a 250 ms debounce (54). Exposes `available`, `kind`,
  `state`, `name`, `wifiEnabled`, `iconName`, `summary`. No scan, no connect. The comment at
  line 8 says Quickshell.Networking has no wired devices in this release.
- Audio: `shell/AudioService.qml` (35 lines): default sink only (`setVolume` 19, `step` 24,
  `toggleMute` 25, `PwObjectTracker` on the sink 27, `changed` for the OSD 32-33).
- Do not disturb: `shell/DndService.qml` (25 lines) reads `makoctl mode`; `toggle()` runs
  `arctic-dnd toggle`. `dotfiles/.local/bin/arctic-dnd:16-27` toggles mako's
  `do-not-disturb` mode and prints waybar JSON for `status`.
- Bluetooth, battery, tray: `Quickshell.Bluetooth`, `Quickshell.Services.UPower` and
  `Quickshell.Services.SystemTray` imported directly in `Bar.qml:6-8`. `LockScreen.qml:246-282`
  repeats the battery percentage maths.
- Settings backend (`settings/scripts/arctic_settings.py`): `_ppd` (1696-1703) and
  `cmd_power_profile` (1706-1730) talk to tuned-ppd with gdbus (both bus names); `nmcli_fields`
  (2373-2388), `cmd_network` (2391-2415), `cmd_wifi` (2418-2424); `shell_script()` (2247-2252)
  already lets Settings run the shell's scripts (the Wallhaven browser uses it, 2315); `TOOLS`
  caps (2519-2524).
- Installer Wi-Fi (root engine, reused for ideas only): `internal/host/host.go` `splitTerse`
  (376-395), `ParseWifiList` (397-429: dedupe by SSID keeping the best signal, connected first,
  then signal, then name), `ScanWifi` (431-438), `securityOf` (440-452), `ConnectWifi`
  (471-510: `sae` only for WPA3-only, 802.1X refused, `--wait 40`, profile deleted on failure,
  timeout vs bad-password copy). UX reference: `installer-ui/steps/NetworkStep.qml`.

#### 2.4 Stock tools, autostart and packages

- `dotfiles/.config/mango/arctic/autostart.conf:12-13`: `exec-once=arctic-session mako` and
  `exec-once=arctic-session nm-applet`; `dotfiles/.local/bin/arctic-session:31` runs mako,
  `:36` runs `nm-applet --indicator`. blueman-applet is not autostarted, but blueman ships a
  D-Bus activation file for `org.blueman.Applet`, so it starts with blueman-manager and then
  registers its own BlueZ agent and a tray icon.
- mako ships `fr.emersion.mako.service` (`Name=org.freedesktop.Notifications`,
  `Exec=/usr/bin/mako`; mako's `meson.build:112-117` installs it into
  `$datadir/dbus-1/services`), so any `notify-send` while nobody owns the name starts mako
  (🔍 that Fedora's mako package ships the file: `rpm -ql mako`, part of 12.4 #7).
- Float rules for the stock tools: `rules.conf:30-32`.
- Spec (`packaging/arctic-linux.spec`): arctic-desktop-config `Requires: mako` (177),
  `Recommends: network-manager-applet` (211); arctic-shell Requires at 243-252 (quickshell,
  qt6-qtdeclarative, qt6-qtsvg, qt6-qtwayland, python3, python3-pillow, python3-pyte, polkit,
  arctic-fonts); arctic-settings `Recommends` nm-connection-editor, blueman, pavucontrol
  (278-280); arctic-desktop `Requires` mako (427), pavucontrol (439), network-manager-applet
  (440), NetworkManager-wifi (441), blueman (442), tuned-ppd (468). No package requires
  `bluez` directly (blueman pulls it in).
- `iso/kiwi/config.kiwi:58` uses `patternType="plusRecommended"`, and 69-71 list
  nm-connection-editor, blueman and pavucontrol explicitly. `dotfiles/install.sh:37-40` lists
  the same tools for the non-RPM install.
- Waybar fallback (`ARCTIC_SHELL=waybar`): `dotfiles/.config/waybar/config.jsonc:78-79`
  (bell: `arctic-dnd toggle`, `makoctl restore`), `:89` blueman-manager, `:107`
  nm-connection-editor, `:117` pavucontrol. Unchanged by this section.

#### 2.5 Settings pages

- `settings/pages/NetworkPage.qml`: header comment 1-3 ("Joining a Wi-Fi network is done from
  the bar's network menu (nm-applet)…"), lede 12 ("Join a Wi-Fi network from the network icon
  on the bar."), 4 s poll of `network` (14-23), Wi-Fi switch (40-54), device rows (55-83),
  "More" group with nm-connection-editor (88-99) and nmtui (100-112).
- `settings/pages/BluetoothPage.qml`: comment 1-3 (pairing in blueman-manager), devices from
  Quickshell.Bluetooth (15), Connect/Disconnect/Forget (60-77), "Pair a new device" →
  `Backend.launch(['blueman-manager'])` behind `caps.blueman` (80-91).
- `settings/pages/SoundPage.qml`: filters at 14-16, `preferredDefaultAudioSink/Source` at
  46/86, "More" group (115-128) opens pwvucontrol or pavucontrol for per-app volume and
  profiles.
- `settings/pages/PowerPage.qml`: `power-profile` call (34), "Power mode" group with
  `ArSegmented` (72-87), lid (89-97). No battery group.
- `settings/SearchIndex.js`: `PAGES` (network 19, bluetooth 21, power 27) and search rows
  (`network.wifi` 87, `network.connections` 88).

#### 2.6 Quickshell on Fedora 44 (checked in the source at `dacfa9d`)

Fedora 44 ships `quickshell-0.2.1^git20260209.dacfa9d`. Checked with
`git merge-base --is-ancestor <commit> dacfa9d` in a clone of quickshell-mirror:

| API or fix | In dacfa9d? | Consequence here |
|---|---|---|
| `Quickshell.Networking` (Wi-Fi only; `connect()`, `forget()`, `scannerEnabled`) | yes (db37dc5) | not used: see next rows |
| `WifiNetwork.connectWithPsk`, settings, connection status (20c691c, author date 2026-02-01) | **no**, merged after the snapshot | `desktop-quickshell.json` says it is in the snapshot; that is wrong. Joining WPA networks needs the nmcli helper (D5). |
| Wired devices (d60498a) | no | wired state stays in `NetworkService` (nmcli) |
| "Fixed crashes when a wifi network disappear" (0.3.1; ead3b00 UAF fixes) | no | the network list must not come from `Quickshell.Networking` on F44; `network.py` scans with nmcli |
| NM service watcher (0f9939c) | no | — |
| `NotificationServer`, `Notification`, `NotificationAction` | yes | D6 is possible on F44 |
| NotificationClosed ordering fix (4df562d) | no | every received notification is set `tracked = true` at once (5.4) |
| Notification action text updates (86b4275) | no | action labels are read once |
| `PwNodeLinkTracker` ignores monitor streams (eecc2f8) | yes | privacy indicators are usable |
| `PwNodePeakMonitor` (11d6d67) | yes; its crash fix (7e6c7ae, 0.3.1) is not | no live mic meter on F44 (16) |
| PipeWire default-node crash fixes (36517a2 "crashes when default pipewire devices are lost", 13fe9b0) | no | 🔍 risk for every default-sink change, already present today in `AudioService`; tested in 12.4 |
| DBusMenu `onItemPropertiesUpdated` (11a71d2), `/NO_DBUSMENU` (39e14d3) | no | tray menus re-open their `QsMenuOpener` on every open; empty menus fall back (5.10) |
| Tray title/description change signals (26531fc) | yes | — |
| `Quickshell.Bluetooth` adapter/device API; no BlueZ Agent1 anywhere (not on master either) | yes | pairing needs `bt-agent.py` |
| `Quickshell.Services.UPower` `PowerProfiles` singleton (`profile` writable, `hasPerformanceProfile`, `degradationReason`), `UPowerDevice.healthPercentage/healthSupported`, `UPower.devices`, `UPower.onBattery` | yes | power mode and health without gdbus; charge threshold and `WarningLevel` are not exposed, so `battery.py` uses gdbus |
| `Quickshell.Services.Mpris` (`position`, `canSeek`, `identity`, `canRaise`, `desktopEntry`) | yes | — |
| `QsMenuOpener` / `QsMenuEntry` (`isSeparator`, `enabled`, `text`, `icon`, `buttonType`, `checkState`, `hasChildren`, `triggered`; an entry is itself a `QsMenuHandle`) | yes | nested tray menus open a second opener on the entry |
| `Quickshell.hasVersion(major, minor)`, `Quickshell.processId`, `DesktopEntries.byId/heuristicLookup` | yes | feature gates and notification-owner check |
| `FileView.setText()`, `atomicWrites`; `Process.write()`, `stdinEnabled` | yes | history and helpers |
| `JsonAdapter` array crash fix (0.3.1) | no | `JsonAdapter` is not used; JSON is parsed by hand |

The NotificationServer retries registration when the current owner of
`org.freedesktop.Notifications` disappears (`server.cpp` `onServiceUnregistered` →
`tryRegister`), and `GetServerInformation` answers name `quickshell`.

#### 2.7 Corrections applied from the research

- `quickshell-031`: the snapshot lacks PSK/saved-connection support and wired devices, so the
  Wi-Fi menu uses nmcli (D5). Packaging 0.3.1 is deferred; the reasons and the fixes this
  section works around are in 16.
- `control-center`: tuned-ppd ships no `powerprofilesctl`; power mode uses Quickshell's
  `PowerProfiles` singleton (D-Bus), with Settings' gdbus path as it is.
- `control-center`, `audio-panel-scope`: retiring the stock GUIs means moving pavucontrol,
  blueman and network-manager-applet from `Requires` to `Recommends` in arctic-desktop (11).
- `notification-center`: mako is a hard `Requires` in both arctic-desktop-config (177) and
  arctic-desktop (427); both change (11). Omarchy does not let critical notifications through
  do not disturb; Arctic's rule in 5.4.5 is presented as Arctic's own, with the abuse case
  handled by a per-app rule.
- `media-controls`: Omarchy's media widget is left = play/pause, middle = next, right = popup.
  Arctic keeps its own rule (left click opens the item's menu everywhere) and does not claim
  Omarchy's mapping.
- `low-battery-warnings`: UPower 1.91.4's `CriticalPowerAction=Auto` means logind `Sleep()`,
  which follows `SleepOperation=` (default `suspend-then-hibernate suspend hibernate`); Arctic
  sets up no swap for hibernation, so the result is usually suspend. The warning text asks
  UPower `GetCriticalAction()` and resolves `Sleep` through logind; thresholds come from the
  DisplayDevice `WarningLevel` property, not from re-parsing the config.
- `battery-health-limit`: the limit applied is UPower's `ChargeEndThreshold`, so the switch is
  labelled with that number, not a fixed 80 %. The polkit rule for `EnableChargeThreshold` is
  🔍 (12.4).
- `keyboard-layout-indicator`: in Mango 0.17.3 `switch_keyboard_layout` with an argument `N`
  in `1..layouts` selects layout `N-1`; `0` or no argument cycles
  (`src/dispatch/bind.c:1346-1350`, argument clamped 0-100 at `parse_config.c:4959`). The docs'
  "(0, 1, 2…)" is wrong, and the gap item's "dispatch `switch_keyboard_layout,0` on lock" would
  cycle instead of resetting. The lock screen sends `switch_keyboard_layout,1`.
  `mmsg watch keyboardlayout` prints `{"layout":"<name>"}` where the name is
  `xkb_keymap_layout_get_name()` (`ipc.c:81-94`, `1080-1083`), the long layout name such as
  "English (US)", not a code. The real layouts live in `/etc/arctic/mango/keyboard.conf`
  (installer) and `settings.conf` (Settings); `input.conf:4` is only the fallback.
- `panel-hotkeys-bar-focus`: Super+Ctrl+A/W/B/D/P and Super+Alt+B are free. Omarchy's
  Super+Ctrl+1…9 "bar panel N" is not added (16).
- `privacy-indicators`: the polkit layer namespace is `arctic-polkit`; `shield_when_capture` is
  valid as a window rule and a layer rule; apps that open `/dev/video*` directly do not show.
- `external-brightness-ddc`: Fedora's ddcutil already ships
  `/usr/lib/modules-load.d/ddcutil.conf` and `/usr/lib/udev/rules.d/60-ddcutil-i2c.rules`, so
  Arctic adds no modules-load or udev files. Noctalia's 30 s cool-down after 3 failures is kept.
- `calendar-popover`: Super+Ctrl+T is free in Arctic (Omarchy uses it for btop; Arctic's
  activity key is Ctrl+Shift+Escape in the system-tools item).
- Missed gaps that touch this section: the Alt+Shift layout-toggle clash (8.1), notification
  hotkeys "invoke newest" and "open history" (8.1, without Omarchy's Super+Shift+Alt+comma,
  which contains Alt+Shift), and new Arctic binds silently shadowing user binds (handled by the
  shortcuts section's collision check; every key below is in `binds.conf`, so that check sees
  it).

### 3. Design

#### 3.1 One menu host, many panels

- **`BarMenu.qml`** is the only popover for bar menus: a `Popover` with `placement: 'point'`,
  `scrim: false`, `cardColor: surfaceRaised`, `cardRadius: radiusLg`, `shadow: 2`
  (shadow-md), `layerName: 'arctic-menu'`. It has a `panel` property (a panel id) and a
  `Loader` that loads the panel component. Switching panels changes the card's width, height and
  `pointX` with `durationBase` / `easeStandard` (instant under reduced motion).
- **Panels** are plain `Item`s with `implicitWidth`/`implicitHeight`, a `title`, a
  `focusItem` and optional `pages`. The same component renders in `BarMenu` (under its bar item)
  and inside Quick Settings (as a sub-page with a back row). Panel ids: `network`, `bluetooth`,
  `sound`, `notifications`, `calendar`, `battery`, `media`, `display`, `keyboard`, `tray`,
  `quick`.
- **Width**: network 340, bluetooth 340, sound 360, notifications 380, calendar 300, battery
  320, media 340, display 340, keyboard 260, tray 200-320 (from its content), quick 380.
- **Height**: `min(content, popover.height - 2*space4 - frameWidth)`; the panel body scrolls
  inside (`Flickable`, `boundsBehavior: StopAtBounds`, a 4 px `inkSubtle` scroll indicator only
  while moving). The current row is kept visible (`ensureVisible` in `MenuList`).
- **Why one host**: the one-at-a-time rule holds by construction, moving to the neighbouring
  menu (Ctrl+Tab) is a content swap, and only one extra layer surface exists.
- `PowerMenu.qml` and `UpdatePopover.qml` keep their own `Popover`s (the power menu is reached
  from `arctic-power` and must keep working exactly as today), but their rows and card move onto
  the toolkit (`MenuRow`, `shadow: 2`) so every menu looks the same.

#### 3.2 One popover at a time (`shell/shell.qml`)

```qml
// 20-22 becomes:
function closePopovers(except) {
    [launcher, wallpapers, power, keys, updates, barMenu, wifiShare]
        .forEach(p => { if (p !== except && p.open) p.close(); });
}
readonly property bool modalOpen: polkit.active || btPair.open
property var bars: ({})                 // screen name → Bar, filled by Bar.qml
function panelAnchor(screen, name) {   // x of the bar item that owns `name`, or null
    const bar = screen ? bars[screen.name] : null;
    return bar ? bar.anchorFor(name) : null;
}
function togglePanel(name, screen, x, options) {
    const target = screen || Outputs.focused;
    if (barMenu.open && barMenu.screen === target && barMenu.panel === name) { barMenu.close(); return; }
    openPanel(name, target, x, options);
}
function openPanel(name, screen, x, options) {
    const target = screen || Outputs.focused;
    const anchor = x !== undefined ? x : panelAnchor(target, name);
    if (anchor === null && name !== 'quick' && name !== 'display') {
        if (name === 'battery') return openQuick('battery', target);   // desktop: no battery item
        return;                                                          // item hidden: nothing to open
    }
    barMenu.panel = name;
    barMenu.options = options || {};
    barMenu.pointX = anchor !== null ? anchor : target.width - Theme.space2 - Theme.frameWidth - 190;
    present(barMenu, target);
}
function openQuick(page, screen) { openPanel('quick', screen, undefined, { page: page || '' }); }
```

- `present()` (23-27) is unchanged; `close()` rather than `open = false` so `dismissed` fires
  and panels can stop scans.
- `togglePower` and `toggleUpdates` stay; they now close `barMenu` through `closePopovers`.
- The launcher, wallpapers and keys sheet close any open bar menu, and opening a bar menu closes
  them (all through `present`).
- `modalOpen` drives `barMenu.grabKeyboard: !shell.modalOpen` (3.3).
- `Lock` (`shell.lock()`, 59-62) already calls `closePopovers(null)`; it now also closes
  `btPair` by rejecting the pending request.

#### 3.3 Dialogs over menus and keyboard grabs

Mango gives keyboard focus to the first exclusive layer surface it finds, scanning Overlay,
then Top, then Bottom (`src/manage/layer.c:50-104`, `reset_exclusive_layers_focus`). With two
exclusive Overlay surfaces the winner depends on list order. So:

- Only one Overlay surface asks for exclusive focus at a time. `BarMenu` binds
  `grabKeyboard: !shell.modalOpen`; when the polkit dialog or the pairing dialog closes, the
  menu takes focus back (`focusContent()` on `modalOpenChanged`).
- `PolkitDialog` gets `id: polkit` in `shell.qml:81` and `readonly property bool active:
  dialog.open` so the menu can yield (the Wi-Fi share card and hotspot read secrets through
  polkit).
- The bar's own keyboard mode (8.3) is on the Top layer, so an open menu (Overlay) wins while it
  is open and the bar gets focus back when it closes.

#### 3.4 Visual rules

- Card: `surfaceRaised`, 1 px `line`, `radiusLg`, shadow-md drawn by `ShadowLayers.qml` (a
  port of `settings/components/ShadowRect.qml` layers, placed behind the `PopupSurface`
  because the surface clips), `space1` (4 px) inset around lists. `Theme.qml` gains `shadowSm`
  and `shadowMd` with the values of `settings/Theme.qml:75-77`.
- Rows: 34 px (one line) or 44 px (with detail), `radiusSm`, 18 px icon in `ink`
  (`inkMuted` when disabled), 15 px label, 12 px detail in `inkMuted`, `space3` side padding.
  Hover and keyboard highlight: `surfaceSunken`. The current choice (default output, connected
  network, active power mode): `accentSoft` fill, 1 px `accentEdge`, a check icon in
  `accentText`. Never colour alone: a check, a word ("Connected") or both.
- Section labels: overline 11 px, uppercase, +0.08em, `inkSubtle`.
- Amber appears only for: the one primary button of a view (Connect, Pair, Allow), focus rings,
  switch/slider fills and checked tiles (checked controls), the current selection. Never for
  icons at rest, section labels, unread counts or status.
- Status (connected, battery low, recording, microphone in use) always travels with an icon and
  a word, in `success`/`warning`/`error`/`info` only for status.
- Motion: menus open with the existing `PopupSurface` fade and 0.98 scale over `fadeSlow`
  (unchanged) and close over `durationFast`; content switches animate size over `durationBase`;
  reduced motion keeps fades only.
- Copy: sentence case, buttons start with a verb, errors say what happened and what to do
  (installer Wi-Fi copy reused).

#### 3.5 New icons

`design-data.js` is generated by `shell/dev/export-design-assets.cjs` from the design bundle
and must not be edited. New glyphs go into a new `shell/assets/icons-extra.js`
(`var EXTRA = {…}`), the same pattern as `settings/assets/SettingsIcons.js` (which already
carries `display` and `mouse`). `shell/assets/Icons.js` `has()`/`icon()` look in `Data.ICONS`,
then `Extra.EXTRA`. All glyphs: 24-unit grid, 1.75 stroke (set by `Icons.icon`), round caps and
joins, 2 px corner radius on shapes, `currentColor` only for small filled dots, no fills
otherwise. Move them into the design system when it grows them (comment in the file).

| Name | Drawing (24 grid) | Used by |
|---|---|---|
| `wifi-1`, `wifi-2` | the existing `wifi` arcs minus the outer one / outer two (dot at 12,19.3 kept) | signal meter: drawn over `wifi` in `inkDisabled` (`SignalIcon.qml`); `wifi` alone = strong |
| `headphones` | headband arc 5→19 at y 13, two 3×6 rounded ear cups | Bluetooth, Sound |
| `headset` | `headphones` plus a boom from the left cup to 14,20 | Bluetooth, Sound |
| `speaker` | 12×18 rounded rect, circles r 3.5 (woofer) and r 1 (tweeter) | Sound outputs |
| `mouse`, `display` | copied byte-for-byte from `settings/assets/SettingsIcons.js` | Bluetooth, Display page |
| `phone` | 10×18 rounded rect, 2 px notch line at the bottom | Bluetooth |
| `laptop` | 16×10 screen rect, base line 2→22 at y 18 | Bluetooth (`computer`) |
| `pause`, `skip-back`, `skip-forward` | two 2×12 bars; triangle + bar | Media |
| `mic-off` | the existing `mic` with a 4→20 diagonal | Sound, indicators |
| `airplane` | top-view plane, 1.75 stroke | airplane tile/indicator |
| `key` | ring r 3.5 at 8,15 with a shaft to 20,7 and two teeth | VPN rows, tile, indicator |
| `bell-dot` | the existing `bell` plus a filled r 2.2 dot at 18,6 | bell with unseen notifications |
| `leaf`, `gauge`, `bolt` | power saver / balanced / performance | Battery panel, power tile |
| `hotspot` | dot with two outward arc pairs | Network |
| `qr-code` | three finder squares and dots | Network share |
| `dots` | three 1.1-radius dots on y 12 | row "More actions" |
| `screen-share` | `display` with an up arrow inside | privacy indicator |
| `sun` | circle r 4 and 8 rays | dark-mode tile when off |

Settings needs `wifi-1`, `wifi-2`, `key`, `leaf`, `gauge`, `bolt` and `bell-dot` too: they are
added to `settings/assets/SettingsIcons.js` `EXTRA` as exact copies, and a test keeps the copies
identical (12.2).

### 4. The menu toolkit (new files in `shell/`, registered in `shell/qmldir`)

| File | What it is | API |
|---|---|---|
| `BarMenu.qml` | the popover described in 3.1 | `panel`, `options`, `shell` (required), `pointX`; `show(panel)`; `panelLoaded(item)` |
| `ShadowLayers.qml` | shadow-sm / shadow-md behind a card | `target`, `elevation` (1 or 2), `radius`; opacity follows `target.reveal` |
| `MenuList.qml` | a `FocusScope` with the keyboard model (8.2) over "stops" | `stops` (ordered list of `MenuRow`-like items), `current`, `keyboardNav`; `next()`, `prev()`, `first()`, `last()`, `activate()`, `secondary()`, `typeAhead(text)`; signals `back()`, `escape()` |
| `MenuNav.js` | pure keyboard logic used by `MenuList` (tested in Node) | `step(stops, current, dir, wrap)`, `group(stops, current, dir)`, `match(stops, from, prefix)` |
| `MenuRow.qml` | one row | `icon`, `iconBase` (drawn under `icon` in `inkDisabled`, for signal meters), `label`, `detail`, `trailing` (`''`, `check`, `lock`, `chevron`, `external`, `spinner`, `kbd`, `text`, `dots`), `trailingText`, `kbd`, `selected`, `current`, `busy`, `enabled`, `destructive`; signals `activated()`, `secondary()`; `Accessible.role: MenuItem` |
| `MenuSwitchRow.qml` | label + detail + `ArcticSwitch` | `checked`, `busy`; signal `toggled(bool)`; Space/Enter toggle; `Accessible.role: CheckBox` |
| `MenuSlider.qml` | icon button + `ArcticSlider` + value text (3 ch, tabular) + optional chevron | `icon`, `mutedIcon`, `value`, `muted`, `label` (accessible), `showChevron`; signals `moved(v)`, `muteToggled()`, `opened()` |
| `ArcticSlider.qml` | port of `settings/components/ArSlider.qml` with shell `FocusRing` (`shown`) | same properties and `committed(value)` |
| `MenuSection.qml` | overline label with optional trailing text/button (e.g. a rescan spinner) | `text`, `trailingText`, `busy` |
| `MenuSeparator.qml` | 1 px `line`, `space1` vertical margin | — |
| `MenuHeader.qml` | panel title (15/600) with optional switch or back chevron ("‹ Wi-Fi") | `title`, `showSwitch`, `checked`, `switchEnabled`, `backText`; signals `toggled(bool)`, `back()` |
| `MenuPage.qml` | a sub-page inside a panel: header with back + a `MenuList` body; Left/Backspace/Esc go back | `title`, `backText`; signal `back()` |
| `MenuField.qml` | inline form row: `ArcticField` (+ eye toggle for secrets) and buttons | `secret` (echo Password, `ImhSensitiveData|ImhNoPredictiveText|ImhNoAutoUppercase`), `placeholder`, `error`, `errorText`, `primaryText`, `busy`; signals `submitted(text)`, `cancelled()`; clears its text on hide |
| `Spinner.qml` | 16 px ring, `inkMuted` arc; reduced motion: a still "…" | `running` |
| `SignalIcon.qml` | `wifi` in `inkDisabled` with `wifi-1`/`wifi-2`/`wifi` over it in `ink` | `signal` (0-100); thresholds 34/67 as `NetworkStep.qml:43-45` |
| `QuickTile.qml` | Quick Settings tile (5.11) | `toggle` (a `Toggle`) |
| `Toggle.qml` | a `QtObject` for the registry (5.11) | see 5.11 |

`Popover.qml` gains, all backwards compatible:
- `shadow` (0 default, 1, 2): a `ShadowLayers` sibling behind `surface`.
- `maxCardHeight` (read-only): `height - 2*Theme.space4 - Theme.frameWidth` for `point`
  placement; `BarMenu` caps `cardHeight` with it.
- `Behavior` on `cardWidth`/`cardHeight` when `animateSize: true` (`BarMenu` only).

`BarItem.qml` gains `active` (its menu is open: `surfaceSunken` like hover) and
`Accessible.role: hasMenu ? Accessible.ButtonMenu : Accessible.Button` with a `hasMenu`
property. `keyboardFocused` (16) is now driven by the bar keyboard mode.

### 5. Panels

#### 5.1 Network (`NetworkPanel.qml`, `scripts/network.py`)

**Layout (top to bottom)**

1. `MenuHeader` "Wi-Fi" with a switch bound to `NetworkService.wifi.enabled`; toggling runs
   `network.py radio wifi on|off`. Disabled with the detail "Turned off by a switch on the
   computer" when the hardware radio is off, and "Airplane mode is on" (with a "Turn off
   airplane mode" row) in airplane mode. Hidden when there is no Wi-Fi device.
2. Wired row (only when an Ethernet device exists): `ethernet` icon, "Wired", detail
   "Connected" / "Connecting…" / "Cable unplugged". Not clickable.
3. Wi-Fi list (the watch helper scans only while the menu is open; format in 6.1): one row per SSID,
   deduplicated with the best signal, sorted connected → saved → signal → name. Row:
   `SignalIcon`, SSID, trailing `lock` when secured, detail:
   - connected: "Connected · strong signal" (`selected` look: `accentSoft` + check);
   - activating: "Connecting…" with a spinner;
   - saved: "Saved · good signal";
   - secured: "Secured · weak signal"; enterprise: "Company login (802.1X)";
   - open/OWE: "Open network" / "Open network, encrypted".
   Signal words: strong ≥ 67, good ≥ 34, weak below.
4. Row actions:
   - Enter/click on a saved or open network: `network.py connect --uuid U` / `--ssid S
     --security open|owe`. The row shows a spinner; on failure an error line appears under it.
   - Enter/click on a new secured network: the row expands into a `MenuField` ("Password for
     “Home”", eye toggle, primary "Connect", ghost "Cancel"). Submit runs
     `network.py connect --ssid S --security wpa-psk|sae|wep --ask` and writes
     `{"secret":"…"}` to its stdin. Auth errors keep the field open, select its text and show
     "That password didn’t work for “Home”. Check it and try again."
   - Enterprise network: opens the "Company Wi-Fi" page (item 7).
   - Right-click, the `dots` button, Menu key or Shift+F10 on a row opens its actions page:
     "Disconnect" (connected), "Forget this network" (saved; asks inline "Forget “Home”? You’ll
     need the password to join again." with a destructive "Forget" and "Cancel"), "Share with a
     phone…" (saved PSK/SAE/open networks, not enterprise), "Connect automatically" switch
     (`connection.autoconnect`). Delete on a saved row goes straight to the forget question.
5. "Join another network…" row → page with: Network name (SSID), Security as `MenuRow` radio
   list (None / WPA or WPA2 Personal / WPA3 Personal / WEP / WPA or WPA2 Enterprise), password
   `MenuField` (not for None), "Join" primary. Enterprise continues to the Company Wi-Fi page.
6. VPN section (only when VPN or WireGuard profiles exist): one `MenuSwitchRow` per profile
   (`key` icon, name, detail "Connected" / "WireGuard" / "OpenVPN"). Turning one on runs
   `network.py vpn-up --uuid U`; when that fails for missing secrets the row expands into a
   `MenuField` ("Password for “Work VPN”") and retries with `--ask`. "Add a VPN…" row →
   `arctic-settings network` (import lives in Settings, 9.1).
7. Company Wi-Fi page (802.1X): Sign-in method (PEAP / TTLS; EAP-TLS is refused with
   "“eduroam” needs a certificate to sign in. Set it up in Edit connections."), Inner method
   (MSCHAPv2 / PAP / GTC; MSCHAPv2 default), Username, Anonymous identity (optional), Domain
   (optional, `802-1x.domain-suffix-match`), Certificate: "Use the system certificates"
   (default, `802-1x.system-ca-certs yes`) / "Don’t check (not recommended)" (asks once more),
   password `MenuField`, "Join". Runs `network.py enterprise …` with the password on stdin.
   A CA file path is picked in Settings (a file dialog cannot open over a layer-shell menu).
8. Tailscale row (only when `tailscale` is installed, 🔍 12.4): `MenuSwitchRow` "Tailscale"
   (detail: tailnet name or "Signed out"), exit-node page listing peers with
   `ExitNodeOption: true` plus "None". If `tailscale up` answers "access denied", the row offers
   "Let Arctic switch Tailscale" → `pkexec tailscale set --operator=$USER` (polkit dialog), then
   retries.
9. Hotspot row (only when the Wi-Fi device supports AP mode): `MenuSwitchRow` "Hotspot"
   (detail "Off" / "On · 2 devices" / "Shares your wired connection"). Turning it on while
   connected to Wi-Fi asks inline "Turning on the hotspot disconnects “Home”." with "Turn on".
   When on, "Show the name and password…" opens the share card.
10. Footer: "Network settings" (`arctic-settings network`, `sliders` icon) and "Edit
    connections…" (`nm-connection-editor`, `external` trailing icon, only when installed;
    closes the menu first).

**Share card (`WifiShare.qml`)**: a separate `Popover` (`placement 'center'`, `layerName:
'arctic-wifi-share'`, width 360) so it alone is shielded in screen captures (11.5). Shows the QR
code (`network.py share --uuid U`, SVG from qrencode via a `data:` URL), the network name,
"Scan this with a phone camera to join.", a "Show password" toggle that re-runs with
`--reveal` (the password is kept only in the card's property and cleared on close), and
"Done". Reading a system-owned secret asks polkit (🔍 12.4); dismissing polkit shows "Arctic
needs your password to read the Wi-Fi password."

**When NetworkManager needs a password on its own**: nm-applet no longer runs in the Quickshell
session (6.7), so there is no secret agent for NetworkManager-initiated requests (a saved
network whose password changed). `network.py watch` reports a device state change to FAILED
with reason `NO_SECRETS` (7) as `{"type":"needs_secrets",…}`; `NetworkService` posts a toast
"“Home” needs its Wi-Fi password again" with the action "Enter password", which opens the
network menu with that network's password field open. Joining from the menu always has an agent
(nmcli itself, through `passwd-file`).

**Airplane mode**: `network.py airplane on` saves the current Wi-Fi, Bluetooth and WWAN soft
states to `~/.local/state/arctic/airplane.json` and runs `rfkill block wlan`, `rfkill block
bluetooth`, `rfkill block wwan`; `off` unblocks the ones that were on. State comes from
`rfkill --json`. If `/dev/rfkill` is not writable (🔍 12.4, uaccess), it falls back to
`nmcli radio all off` plus `adapter.enabled = false` from QML. The toggle shows an `airplane`
glyph in the mode indicators (5.12); a separate OSD kind belongs to the osd-kinds work.

**`shell/NetworkService.qml` changes**: it runs `python3 Session.scripts/network.py watch`
(stdin enabled) instead of its own `nmcli` query and `nmcli monitor` (25, 49), restarting it
after an exit with a 3 s timer (the `Workspaces.qml` pattern). It keeps `available`, `kind`,
`state`, `name`, `wifiEnabled`, `iconName` and `summary` with today's meanings, so `Bar.qml` and
`LockScreen.qml:282` keep working, and adds `wifi` (`{device, hardware, enabled, apCapable}`),
`airplane`, `wired`, `active`, `vpn`, `hotspot`, `networks`, `scanning`, `setScanning(on)`
(sends `{"op":"scan","on":…}`; the network panel turns it on in `Component.onCompleted` and off
in `Component.onDestruction` and on `BarMenu.dismissed`), `rescan()`, `run(args, secret,
callback)` (one-shot `Process` per action with `stdinEnabled`; the secret, when given, is
written as one JSON line, which is all the helper reads, and the QML string is cleared), and the
signal `needsSecrets(uuid, ssid)`. The line-8 comment becomes: "Wi-Fi through network.py (nmcli); Quickshell.Networking is not used on
Fedora 44's snapshot (no PSK support, a crash when a network disappears)."

#### 5.2 Bluetooth (`BluetoothPanel.qml`, `BluetoothService.qml`, `BluetoothPairDialog.qml`, `scripts/bt-agent.py`)

**Layout**

1. `MenuHeader` "Bluetooth" with a switch on `adapter.enabled`. The bar item and the panel are
   hidden without `Bluetooth.defaultAdapter` (unchanged rule).
2. "Your devices": `adapter.devices.values.filter(d => d.paired || d.connected)`, connected
   first, then name. Row: device icon (map below), name, detail "Connected · battery 80 %" /
   "Not connected" / "Connecting…" / "Disconnecting…". Enter/click toggles
   `connect()`/`disconnect()`. Secondary opens the device page: Connect/Disconnect, "Let it
   connect without asking" switch (`trusted`), "Rename…" (`MenuField` writing `device.name`), battery
   (when `batteryAvailable`), "Forget this device" (inline confirm: "Forget “MX Keys”? You’ll
   need to pair it again.").
3. "Pair a new device" row → pairing page:
   - on open: `BluetoothService.claimDefault()` (the agent re-requests the default agent),
     `adapter.pairable = true`, `adapter.discoverable = true`, `adapter.discovering = true`;
     detail line "Visible as “<adapter.name>” while this is open";
   - list `devices.filter(d => !d.paired && d.deviceName !== '')`, name sorted, spinner in the
     section header while discovering; a 60 s timer stops discovery and shows "Search again";
   - Enter/click on a device: row spinner, `device.pair()`; when `paired` becomes true:
     `device.trusted = true; device.connect()`; Esc or "Cancel" calls `device.cancelPair()`;
     a pair that ends with `pairing === false && !paired` shows "Couldn’t pair with “X”. Make
     sure it’s in pairing mode, then try again.";
   - on close (page back, menu close, `dismissed`): `discovering = false`, `discoverable`
     restored to its previous value.
4. Footer: "Bluetooth settings" (`arctic-settings bluetooth`) and "More Bluetooth options…"
   (`blueman-manager`, only when installed; closes the menu first).

Device icon map (`BluetoothService.iconFor(device.icon)`): `audio-headset` → `headset`,
`audio-headphones` → `headphones`, `audio-card` / `multimedia-player` → `speaker`,
`input-keyboard` → `keyboard`, `input-mouse` → `mouse`, `input-gaming` → `gamepad`,
`input-tablet` → `pen-nib`, `phone` → `phone`, `computer` → `laptop`, `video-display` →
`display`, `camera-*` → `camera`, anything else → `bluetooth`.

**The agent (`scripts/bt-agent.py`)**: python3-dbus with a GLib main loop, run by
`BluetoothService.qml` as a `Process` with `stdinEnabled` while an adapter exists (restart after
exit with a 5 s back-off, at most 3 times a minute). It:
- exports `org.bluez.Agent1` at `/org/arcticlinux/shell/agent`, calls
  `org.bluez.AgentManager1.RegisterAgent(path, "KeyboardDisplay")` and `RequestDefaultAgent`;
- re-registers when `org.bluez` reappears (NameOwnerChanged) and re-requests the default agent
  when `org.blueman.Applet` disappears (blueman-applet registers itself as the default agent
  and `RequestDefaultAgent` is last-wins) and whenever the shell sends `{"op":"default"}`;
- answers methods asynchronously (`async_callbacks`) and forwards them to the shell as JSON
  lines (6.2); a request with no answer after 90 s is rejected with `org.bluez.Error.Canceled`;
- auto-accepts `AuthorizeService` for devices that are both paired and trusted; asks otherwise;
- never logs PINs or passkeys.

**The dialog (`BluetoothPairDialog.qml`)**: a `Popover` `placement 'center'`, `layerName:
'arctic-bt-pair'`, `surfaceRaised`, width 420, modelled on `PolkitDialog.qml:26-114` (icon
chip in `infoSoft` with the device icon, title 20/600, body 15, buttons ghost + primary).
Esc, Cancel or a click outside rejects. A `cancel` line from the agent closes it.

| Request | Title | Body | Input | Buttons |
|---|---|---|---|---|
| `confirm` (RequestConfirmation) | Pair with “Pixel 9”? | Check that “Pixel 9” shows the same code. | code shown as `042 917` (mono 28, tabular) | Cancel · **Pair** |
| `passkey` (RequestPasskey) | Enter the code shown on “Car kit” | — | 6-digit field | Cancel · **Pair** |
| `pin` (RequestPinCode) | Enter the PIN for “Headset” | Often 0000 or 1234, or printed in the manual. | 1-16 characters, `ImhSensitiveData` | Cancel · **Pair** |
| `show_passkey` (DisplayPasskey) | Type this code on “MX Keys” | Then press Enter on that keyboard. | code + one dot per typed digit (`entered`) | Cancel |
| `show_pin` (DisplayPinCode) | Type this PIN on “Keyboard” | Then press Enter on that keyboard. | PIN | Cancel |
| `authorize` (RequestAuthorization) | “Pixel 9” wants to pair with this computer | — | — | Don’t pair · **Pair** |
| `service` (AuthorizeService) | Allow “Pixel 9” to connect for audio? | — | — | Don’t allow · **Allow** |

Service labels from UUIDs: A2DP/AVRCP/HFP/HSP → "audio", HID/HOGP → "typing and pointing",
OBEX → "file transfer", PAN → "network sharing", anything else → "a service".

#### 5.3 Sound (`SoundPanel.qml`, `scripts/audio.py`, `AudioService.qml`)

1. "Output": `MenuSlider` for the default sink (`AudioService.setVolume`, mute button, value
   "64 %"); then one row per sink (`Pipewire.nodes` with `audio && !isStream && isSink`, the
   filter of `SoundPage.qml:14-16`), icon by `device.bus`/form factor (`speaker`, `headphones`,
   `headset`, `display` for HDMI), label `description || nickname || name`, detail = the active
   port ("Headphones", "Speakers") when the device has more than one. The default sink has the
   `selected` look; Enter picks a sink (`Pipewire.preferredDefaultAudioSink = node`).
   Secondary on a sink opens its device page: ports (routes) and profiles as radio rows from
   `audio.py devices`, e.g. "High fidelity playback (A2DP)" / "Headset with microphone (HFP)".
2. "Input": `MenuSlider` for the default source (mic icon, `mic-off` when muted) and one row per
   source (`media.class` starting with `Audio/Source`), same interaction.
3. "Apps" (only while something plays): one `MenuSlider` per `AudioOutStream` node
   (`isStream && isSink`), icon from `properties['application.icon-name']` via
   `Quickshell.iconPath(name, true)` (fallback `volume`), label
   `properties['application.name'] || properties['media.name']`, value and mute on the stream's
   `audio`. A `PwObjectTracker` tracks these nodes only while the panel is loaded.
4. Footer: "Sound settings" (`arctic-settings sound`) and "Volume control…" (pwvucontrol, else
   pavucontrol, only when installed).

`AudioService.qml` gains `source`, `sinks`, `sources`, `streams`, `setSourceVolume`,
`toggleSourceMute`, `setDefaultSink(node)`, `nextOutput()` (next sink by description, wraps) and
an "output changed" toast: when `defaultAudioSink` changes after `settled` and the change did
not come from the menu, post a transient low-urgency notification "Sound now plays on
Headphones" (app "Sound", icon `volume`).

Not in 0.3.0: per-app output routing (16) and a live mic meter on F44 (gated on
`Quickshell.hasVersion(0, 3)`, 16).

#### 5.4 Notifications (`NotificationService.qml`, `Toasts.qml`, `ToastCard.qml`, `NotificationCard.qml`, `NotificationCenter.qml`, `NotificationRules.js`, `arctic-notify`)

##### 5.4.1 Owning the bus name

- `NotificationService.qml` (singleton) contains a `NotificationServer` with
  `keepOnReload: true`, `actionsSupported: true`, `actionIconsSupported: false`,
  `bodySupported: true`, `bodyMarkupSupported: false` (bodies are shown as `PlainText`),
  `bodyHyperlinksSupported: false`, `imageSupported: true`, `persistenceSupported: true`,
  `inlineReplySupported: false`, `extraHints: ['x-canonical-private-synchronous']`.
- `onNotification: n => { n.tracked = true; … }` for every notification, before anything else,
  so NotificationClosed is never sent from inside `Notify` (the ordering fix 4df562d is not in
  F44). Toasts, history and do not disturb decide what shows; closing is always an explicit
  `dismiss()` or `expire()`.
- Ownership check 3 s after start and whenever `refreshOwner()` is called: `gdbus call
  --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus --method
  org.freedesktop.DBus.GetConnectionUnixProcessID org.freedesktop.Notifications` and compare
  the pid with `Quickshell.processId` → `owned`.
  - Not owned and the owner's `/proc/<pid>/comm` is `mako` (mako was D-Bus-activated by an early
    `notify-send`, 2.4): run `pkill -u <uid> -x mako`; Quickshell's server re-registers when
    the name is released (2.6). Check again after 1 s.
  - Owned by anything else (dunst, swaync installed by the person): leave it; `owned` stays
    false, the bell falls back to today's behaviour (`DndService` over makoctl when mako owns
    it, hidden otherwise) and the centre shows "Another notification service is running
    (dunst). Arctic’s notification centre is off."
- The waybar session never runs the shell, so mako keeps working there (6.7).

##### 5.4.2 Toasts (`Toasts.qml`, `ToastCard.qml`)

- One `PanelWindow` per session on the focused output (`Outputs.focused`), Overlay layer,
  namespace `arctic-toasts`, anchors top/right, margins top `barHeight + space2`, right
  `space2 + frameWidth`, `exclusionMode: Ignore`, no keyboard focus.
- Cards: 340 px, `radiusLg`, `surfaceRaised`, 1 px `line`, shadow-md, `space3` padding; app icon
  or image (36 px, `RoundedImage`), summary 15/600, body 13 (3 lines, elided), up to 3 action
  buttons (`ArcticButton` sm secondary; the `default` action is the card click), a close button
  on hover or focus. Critical: a 3 px `error` bar on the left edge plus the word "Urgent" beside
  the app name (never colour alone). A `value` hint (0-100) draws the OSD-style bar (keeps the
  `arctic-osd` fallback notifications readable).
- Stack newest on top, at most 3 visible plus a "2 more" row that opens the centre.
- Timeouts: the app's `expireTimeout` when > 0; 0 = stays until dismissed (mako's current
  behaviour with `ignore-timeout=0`); unset: low 5 s, normal 8 s, critical until dismissed.
  Hover pauses the timer. Expiring a toast hides it and keeps the notification in the centre;
  it does not call `expire()` unless the app asked for a timeout.
- Click: default action if any (`action.invoke()`), else focus the sender's window
  (`ToplevelManager.toplevels` with `appId` matching `desktopEntry`, `activate()`), else nothing.
- `x-canonical-private-synchronous`: a new notification with the same tag replaces the previous
  toast in place (the old one is dismissed). `replaces_id` is handled by the server (the same
  object updates).
- Hidden while the session is locked (the lock screen shows the count instead). Shown above
  fullscreen windows on purpose (Overlay layer: calls and alarms); do not disturb is the way to
  keep a fullscreen game or talk quiet.

##### 5.4.3 The centre (bell → `NotificationCenter.qml`, panel id `notifications`)

- `MenuHeader` "Notifications"; a `MenuSwitchRow` "Do not disturb" (detail "Off" / "On until
  you turn it off" / "On until 15:40" / "On until tomorrow" / "On by schedule until 07:00"); its
  chevron (Right key) opens the durations page: "For 1 hour", "Until tomorrow" (08:00 next
  day, local time), "Until I turn it off", "Turn off".
- Groups by app (`desktopEntry || appName`), newest group first. Group header: app icon (from
  `DesktopEntries.byId(desktopEntry)` → `Quickshell.iconPath`), app name, count, "Clear" (`x`
  icon button, Delete key). The three newest groups start expanded; older ones collapse to one
  stacked card ("5 from Signal"). Left/Right collapse/expand.
- `NotificationCard.qml`: summary, body (expand on Enter when elided), relative time ("2 min
  ago", tabular), image, action buttons (Tab reaches them). Enter runs the default action,
  Delete dismisses, Shift+Delete clears all. Entries restored from history (previous session)
  show no action buttons; Enter focuses or opens the app (`DesktopEntry.execute()`).
- Empty state: `bell` icon, "No notifications", "New ones appear here, including those that
  arrive while do not disturb is on."
- Footer: "Clear all" (ghost) and "Notification settings" (`arctic-settings notifications`).
- The bell shows `bell-off` under do not disturb, `bell-dot` when something arrived since the
  centre was last opened (tooltip "3 new notifications"), else `bell`. Opening the centre marks
  everything seen.

##### 5.4.4 History and state

- `~/.local/state/arctic/notifications.json`: `{"version":1,"items":[…]}`, newest first,
  capped at 50, written with one `FileView` (`atomicWrites: true`) at most once per second.
  Item: `{"id":…,"app_name":…,"app_icon":…,"desktop_entry":…,"summary":…,"body":…,
  "urgency":"low|normal|critical","time":1759070000,"image":"file:///…"}`. Image-data pixmaps
  are not persisted. `transient` notifications and apps with "keep out of history" are never
  written. The folder is created with `install -d -m 0700`.
- `~/.local/state/arctic/notification-apps.json`: apps seen (`desktop_entry`, `app_name`,
  `icon`, `last_seen`) for the Settings rules list.
- `~/.local/state/arctic/dnd.json`: `{"mode":"off|on|until","until":1759080000}`; survives
  restarts; a `Timer` ends timed modes.
- `~/.config/arctic/notifications.json` (written by Settings, watched by the shell):
  ```json
  {"history": true,
   "dnd_schedule": {"enabled": false, "from": "22:00", "to": "07:00"},
   "apps": {"org.signal.Signal": {"toasts": true, "history": true,
                                  "allow_during_dnd": false, "silence_urgent": false}}}
  ```
- `LockScreen.qml`: under the clock, "3 notifications" (count only, `inkMuted`, 13 px) for
  notifications received while locked; hidden at 0. Replaces the README's "can't count hidden
  notifications" note.

##### 5.4.5 Do not disturb (Arctic's rule)

`NotificationRules.js` `decide(n, state, rules)` returns `{toast, history, sound}`:
- Off: toast unless the app's rule says `toasts: false`.
- On (manual, timed or schedule): no toast, but history (nothing is lost), except
  - Arctic's own system alerts (`appName` "Arctic Linux", hint `x-arctic-alert: true`: critical
    battery, failed update) always toast;
  - critical notifications toast unless the app has `silence_urgent: true`;
  - apps with `allow_during_dnd: true` toast.
- This keeps 0.2's behaviour (mako's DND mode showed critical ones) and answers Omarchy's
  reason for blocking critical (chat apps that mark everything critical) with a per-app switch
  in Settings.
- `DndService.qml` becomes a facade: `active`, `available`, `set(mode, until)`, `toggle()`
  → `NotificationService` when `owned`, else today's makoctl path.

##### 5.4.6 Commands

- `arctic-notify` (new, `dotfiles/.local/bin/arctic-notify`):
  `arctic-notify dismiss|dismiss-all|invoke|center|count` →
  `arctic-shell-ipc notifications dismiss|dismissAll|invoke|toggle|count`; without the shell:
  `makoctl dismiss`, `makoctl dismiss --all`, `makoctl invoke`, `makoctl restore`, and
  `makoctl list -j` counted with python3 (🔍 12.4 JSON shape) for `count`.
- `arctic-dnd` (existing): `toggle|on|off|status` plus new `for 1h|until-tomorrow`. It calls
  `arctic-shell-ipc notifications dnd <mode>` first; that returns `on`/`off`, or `unowned`
  when the shell does not own the bus name, in which case the makoctl code at lines 16-27 runs
  as today. `status` keeps its waybar JSON.

#### 5.5 Calendar (`CalendarPanel.qml`, `CalendarGrid.js`)

- The clock (`Bar.qml:88-96`) becomes a `BarItem` (`id: clockItem`, text as today, 13/600,
  tabular) anchored at the bar centre; left click → `togglePanel('calendar')`; tooltip
  "Monday 28 September 2026 · Super + Ctrl + T".
- Header: full date (16/600) and time zone ("Asia/Jerusalem · UTC+3", from `timedatectl show
  -p Timezone --value` once per open, fallback `/etc/localtime` link).
- Month grid: 7 columns plus an ISO week column (`W39`, 11 px `inkSubtle`); first day of the
  week from `Qt.locale().firstDayOfWeek`; other-month days in `inkSubtle`; today = `accentSoft`
  fill + 1 px `accentEdge` (the current day is "here"); the keyboard day has the focus ring.
  Month title "September 2026" with ‹ › buttons.
- Keys: arrows move the day, PgUp/PgDn month, Shift+PgUp/PgDn year, Home = today, Esc closes.
- `CalendarGrid.js` (pure, tested): `monthGrid(year, month, firstDay)` → 6×7 cells with
  `{date, inMonth, isToday}`, `isoWeek(date)`.
- Designed to host events later (P2 in the gap list, not in this section).

#### 5.6 Battery and power (`BatteryPanel.qml`, `BatteryService.qml`, `PowerService.qml`, `scripts/battery.py`)

- `BatteryService.qml` (singleton): `present`, `percent`, `charging`, `full`, `timeText`,
  `onBattery` from `UPower.displayDevice`/`UPower.onBattery` (the maths now in `Bar.qml:213-228`
  and `LockScreen.qml:249-275` move here), `health` (`healthSupported` → `healthPercentage`),
  `peripherals` (`UPower.devices` that are not the laptop battery and report a percentage:
  mouse, keyboard, headset, gaming input, phone), plus `battery.py status` for
  `warningLevel`, `criticalAction`, `threshold*`.
- `PowerService.qml` (singleton): `available` (one `gdbus introspect --system --dest
  org.freedesktop.UPower.PowerProfiles --object-path /org/freedesktop/UPower/PowerProfiles`
  at start), `profile` bound to `PowerProfiles.profile` (writable), `hasPerformance`,
  `degradation` (`degradationReason` → "Performance is limited because the computer is hot." /
  "…because it is on your lap.").
- Panel (bar battery item, `Super + Ctrl + P`; on desktops `Super + Ctrl + P` opens Quick
  Settings on this page without the battery rows):
  1. Header "Battery" with "87 %" and detail "2 h 10 min left" / "Charging · full in 40 min" /
     "Plugged in, not charging (limit 80 %)" / "Fully charged".
  2. "Power mode": three radio rows `leaf` Power saver ("Longer battery life, a bit slower"),
     `gauge` Balanced, `bolt` Performance (hidden without `hasPerformance`); the active one has
     the `selected` look; the degradation sentence under them when set.
  3. "Limit charging to 80 %" `MenuSwitchRow` (the number is `threshold_end`), only when
     `threshold_supported`; detail "Keeps the battery healthy when the laptop stays plugged
     in." Toggling runs `battery.py limit on|off` (polkit 🔍).
  4. "Battery health 91 %" row with detail "of its original capacity" (only with
     `healthSupported`).
  5. "Other devices" (only when there are peripherals): `mouse`/`keyboard`/`headset` rows with
     "40 %".
  6. Footer "Power settings" (`arctic-settings power`).
- Low and critical warnings (UI part): `battery.py watch` streams `WarningLevel` changes of
  `/org/freedesktop/UPower/devices/DisplayDevice`. On `low`: one normal notification "Battery
  at 20 %" / "About 40 minutes left. Plug in soon." On `critical`: one critical Arctic alert
  (`x-arctic-alert`, shows under do not disturb) "Battery at 5 %" / "Arctic will suspend at
  2 %. Plug in to keep working." with the verb from `critical_action` (suspend / hibernate /
  shut down) and the percentage from `percentage_action`. Each fires once per discharge and
  clears when charging starts. Peripherals: one normal notification at 10 % ("Mouse battery at
  10 %"). The shell's `Session.settings.batteryWarnings` (from `~/.config/arctic/shell.json`,
  default true) turns the laptop warnings off; the critical one always shows.
- OSD: `Osd.qml` gains `showPower(onBattery)` ("Charging" with `battery-charging`, "On
  battery" with `battery`), fired on `UPower.onBattery` changes after start-up.
- The bar icon keeps its `error` colour at ≤ 10 % and now also carries the word: the item text
  becomes "10 % · Low" at or below `percentage_low`.

#### 5.7 Media (`MediaService.qml`, `MediaItem.qml`, `MediaPanel.qml`)

- `MediaService.qml` (singleton): `players` (`Mpris.players.values`), `active` (the playing one,
  else the last one that played, else the first), `setActive(p)`, `playPause()`, `next()`,
  `previous()`.
- `MediaItem.qml` (bar, right of the clock; only while a player exists): `music` icon (or
  `pause` while playing) + title capped at 180 px, elided. Left click → `togglePanel('media')`,
  middle → play/pause, scroll → next/previous. Tooltip "Title — Artist · Super + Ctrl + M".
- Panel: cover (`trackArtUrl`, 64 px `RoundedImage`, `music` tile fallback), title 15/600,
  artist 13 `inkMuted`, album 12 `inkSubtle`; a seek `ArcticSlider` only when
  `canSeek && positionSupported && length > 0` (a `Timer` emits `positionChanged()` every 1 s
  while the panel is open and playing, as the Quickshell docs advise); previous / play-pause /
  next as 36 px icon buttons (none is amber; play-pause sits on a `surfaceSunken` circle);
  "Playing in Spotify" rows for each player when there is more than one (the active one has the
  `selected` look); "Open Spotify" when `canRaise`.
- Lock screen (`LockScreen.qml`, under the password message): one compact row, title — artist,
  play/pause and next buttons, only while a player exists.
- Media keys stay on `playerctl` (`binds.conf:93-95`), which works without the shell.

#### 5.8 Display (`DisplayPanel.qml`, `BrightnessService.qml`, `scripts/brightness.py`)

- No bar item; reached from Quick Settings (brightness slider chevron) and `Super + Ctrl + D`
  (`quick open display`).
- One `MenuSlider` (`brightness` icon) per display that `brightness.py list` returns: the laptop
  panel through brightnessctl, external monitors through DDC/CI (ddcutil). Label = the monitor
  model or output name ("DELL U2723QE"). Monitors that do not answer are hidden.
- Night light and display mode rows belong to their own sections; this page has a slot for them
  (`DisplayPanel.extraRows`).
- Footer: "Display settings" (`arctic-settings displays`).
- Keys (`arctic-osd brightness up|down`) act on the focused output (Mango `mmsg get
  all-monitors`, `"active": true`, `ipc.c:596`), not only the laptop panel (6.4). The OSD shows
  the monitor name when there is more than one display.

#### 5.9 Keyboard layout (`KeyboardService.qml`, `KeyboardItem.qml`, `KeyboardPanel.qml`, `scripts/keyboard.py`)

- `KeyboardService.qml` runs `keyboard.py watch` (6.6) and exposes `layouts`
  (`[{code, variant, name, short}]`), `index`, `shortName` ("EN").
- `KeyboardItem.qml` on the bar (right group, before network), visible only with more than one
  layout: text chip `EN` (13/600, tabular). Left click → next layout (`keyboard.py next`),
  right click → `togglePanel('keyboard')`. Tooltip "English (US) · switch with Alt + Shift"
  (the configured `grp:` key, from `keyboard.py`).
- Panel: one radio row per layout ("English (US)", "Hebrew"), the active one `selected`;
  footer "Keyboard settings" (`arctic-settings input`).
- `Osd.qml` gains `showLayout(name)` ("Hebrew" with the `keyboard` icon) on every change that
  did not come from the lock screen.
- `LockScreen.qml`: in `lock()` (31-45) run `keyboard.py set 0` (→ `mmsg dispatch
  switch_keyboard_layout,1`, the first layout) when there is more than one layout; show the
  chip beside the password field; show "Caps Lock is on" under the field while
  `/sys/class/leds/*::capslock/brightness` reads 1 (polled every 500 ms only while locked;
  🔍 12.4).

#### 5.10 Tray menus (`TrayPanel.qml`)

- Left click keeps today's rule (`Bar.qml:164`): `onlyMenu && hasMenu` → open the menu, else
  `activate()`. Right click → menu when `hasMenu`. Middle and scroll unchanged.
- The menu is `togglePanel('tray', screen, x, { item: modelData })`. `TrayPanel` holds a stack
  of `QsMenuOpener`s: the root one has `menu: item.menu`; an entry with `hasChildren` pushes
  `QsMenuOpener { menu: entry }` and shows a "‹ Back" row (Left, Backspace or Esc go back).
- Rows: `isSeparator` → `MenuSeparator`; `text` with mnemonic underscores removed (`_x` → `x`,
  `__` → `_`; 🔍 12.4 whether Quickshell already strips them); `icon` via an `Image` 16 px when
  not empty; `buttonType` CheckBox → a 16 px box with `check` when `checkState ===
  Qt.Checked`, RadioButton → a dot; `enabled === false` → disabled row; `hasChildren` →
  `chevron`. Activation: `entry.triggered()`, then close the menu (not for entries with
  children).
- Width: the widest label + 2×`space3` + icon, clamped 200-320.
- F44 workarounds: each open sets the opener's `menu` to null and back (11a71d2 "some DbusMenu
  updates being dropped" is not in F44); if the opener has no children 300 ms after opening,
  close and call `activate()` when `!onlyMenu`, else show one disabled row "This app has no
  menu" (apps that use `/NO_DBUSMENU`, 39e14d3).
- The tray filter at `Bar.qml:151` also hides `blueman` ids (`i.id.startsWith('blueman')`,
  🔍 12.4 the id blueman-applet registers) so a blueman-applet started by "More Bluetooth
  options…" does not add a second Bluetooth icon.
- `//@ pragma UseQApplication` (`shell.qml:1`) stays: `Wallpapers.qml:135` still uses
  `FolderDialog`.

#### 5.11 Quick Settings and the toggle registry

**`Toggle.qml`** (a `QtObject`):

| Property | Meaning |
|---|---|
| `key` | id used by IPC and indicators (`wifi`, `bluetooth`, …) |
| `label`, `icon`, `iconOff` | tile text and icons |
| `available` | hide the tile, IPC answers `unavailable` |
| `active` | on/off (checked) |
| `detail` | second line ("Home", "Balanced", "On until 15:40") |
| `busy` | spinner |
| `kind` | `switch` (on/off) or `cycle` (power mode) |
| `page` | Quick Settings sub-page for the chevron (panel id), or `''` |
| `indicator` | show in `ModeIndicators` while `active` |
| `tone` | `normal`, `warning`, `error` (indicator pill colours) |
| `keys` | shortcut text for tooltips ("Super + Shift + N") |
| `set(on)`, `toggle()` | functions |

**`ToggleRegistry.qml`** (singleton) holds them in display order and has `byKey(key)`,
`set(key, mode)`, `states()` (JSON map). This section adds:

| key | active when | toggle does | page | indicator |
|---|---|---|---|---|
| `wifi` | `NetworkService.wifi.enabled` | `network.py radio wifi on\|off` | `network` | no |
| `bluetooth` | `adapter.enabled` | `adapter.enabled = !…` | `bluetooth` | no |
| `dnd` | `DndService.active` | `DndService.toggle()` | durations page | no (the bell shows it) |
| `power-mode` (cycle) | never "checked"; detail = mode | Balanced → Power saver → Performance → Balanced | `battery` | no |
| `dark-mode` | `Theme.dark` | `arctic-theme toggle` | — | no |
| `airplane` | all radios soft-blocked | `network.py airplane on\|off` | — | yes (`airplane`) |
| `mic` | default source not muted | `AudioService.toggleSourceMute()` | `sound` | when muted: `mic-off` |
| `vpn` | any VPN/WireGuard active | on: `vpn-up` of the most recently used profile; off: `vpn-down` of all active | `network` | yes (`key`) |

Night light, keep awake, screen recording and game mode add their own `Toggle` entries to
`ToggleRegistry.qml` in their sections (the file is shared); the tile, IPC and indicator come
for free.

**`QuickSettingsPanel.qml`** (panel `quick`, `Super + A`, width 380, under the right end of
the bar):
1. Top row: battery summary ("87 % · 2 h 10 min left", hidden without a battery) and three icon
   buttons: Settings (`sliders` → `arctic-settings`), Lock (`lock` → `shell.lock()`), Power
   (`power` → `togglePower`).
2. Sliders: output volume (`MenuSlider`, chevron → `sound` page) and brightness (the focused
   display, chevron → `display` page; hidden when `BrightnessService` finds none).
3. Tiles: a 2-column grid of `QuickTile`s (168×56, `radiusMd`, `space2` gap). A tile is a split
   button: the main part toggles (Space/Enter), the chevron segment (when `page` is set) opens
   the sub-page (Right key). Off: `surfaceSunken`, `ink`, detail "Off". On: `accentSoft` fill,
   1 px `accentEdge`, icon in `accentText`, detail "On" or the state word. Cycle tiles stay
   `surfaceSunken` and show the mode word.
4. Now playing (when a player exists): one row, title — artist, play/pause; chevron → `media`.
5. Sub-pages: the panels of 5.1-5.8 inside a `MenuPage` with "‹ Quick settings". Esc goes back,
   then closes.

IPC: `quick toggle`, `quick open <page>`; `toggle set <key> on|off|toggle`, `toggle get <key>`
(`on`/`off`/`unavailable`), `toggle states` (JSON). The launcher/command-menu sections can list
`ToggleRegistry` entries as commands.

#### 5.12 Mode and privacy indicators (`ModeIndicators.qml`, `PrivacyService.qml`)

- A `RowLayout` anchored left of the clock (`anchors.right: clockItem.left`, margin `space2`).
- Privacy pills first, while in use: `warningSoft` pill, `warning` icon and a word: `mic`
  "Mic", `camera` "Camera", `screen-share` "Sharing". Tooltip "Microphone in use by Firefox,
  OBS". Click on "Mic" opens the sound menu.
- Mode glyphs next: every registry toggle with `indicator: true` and `active`, as 16 px
  `inkMuted` icons with tooltip and `Accessible.name` ("Airplane mode is on · click to turn it
  off"); click toggles. A toggle with `tone: 'error'` (screen recording) is an `errorSoft` pill
  with a word and the elapsed time ("Recording 01:23").
- Hovering the cluster for 300 ms reveals the inactive indicator toggles dimmed (`inkSubtle`,
  🔍 3:1 on `frost` in both themes, 12.4); clicking one turns it on.
- `PrivacyService.qml`: tracks `Pipewire.nodes` that are streams (`PwObjectTracker`, bounded to
  stream nodes) and classifies with `PwNodeLinkTracker` (monitor streams are ignored in F44):
  `media.class` `Stream/Input/Audio` linked → microphone (by `application.name`);
  `Stream/Input/Video` linked → camera; a `Video/Source` node whose `node.name` starts with
  `xdpw` (xdg-desktop-portal-wlr's screencast, 🔍 12.4) with a consumer link → screen sharing
  (the consumer's `application.name`). Apps that read `/dev/video*` directly are not seen; the
  wiki says so.
- Capture shielding (Mango 0.17.3 `shield_when_capture`, 11.5): the polkit, pairing and Wi-Fi
  share layers, and KeePassXC / Bitwarden windows.

### 6. Helpers and data formats

Conventions for every new helper in `shell/scripts/`: Python 3 standard library only unless
named; one-shot commands print exactly one JSON line, `{"ok":true,…}` or
`{"ok":false,"error":"<a sentence>","code":"<code>"}`, exit 0/1; long-running `watch` modes
print one JSON object per line with a `type`; keys are snake_case; secrets are read from stdin
as one line `{"secret":"…"}` (at most 4 KiB, refused if it contains a newline or NUL) and are
never on argv, in the environment, in files or in logs; stderr of child processes is summarised,
never echoed with secrets. Settings reaches the same scripts through `shell_script()`
(`arctic_settings.py:2247-2252`).

#### 6.1 `shell/scripts/network.py`

```
network.py watch                 long-running (NetworkService); commands on stdin:
                                 {"op":"scan","on":true|false}  {"op":"rescan"}
network.py status                one "state" object
network.py scan [--rescan]       {"ok":true,"networks":[…]}
network.py saved                 {"ok":true,"saved":[{"uuid","name","ssid","security","autoconnect","last_used"}]}
network.py connect --uuid U [--ask]
network.py connect --ssid S --security open|owe|wep|wpa-psk|sae [--hidden] [--ask]
network.py enterprise --ssid S --eap peap|ttls --phase2 mschapv2|pap|gtc --identity ID
                      [--anonymous-identity A] [--domain D] (--system-ca|--ca-cert PATH|--no-ca) [--hidden]
network.py disconnect --uuid U
network.py forget (--uuid U… | --ssid S)
network.py autoconnect --uuid U on|off
network.py radio wifi on|off
network.py airplane on|off
network.py vpn-up --uuid U [--ask] | vpn-down --uuid U
network.py vpn-import --type openvpn|wireguard --file PATH
network.py share --uuid U [--reveal]
network.py hotspot on [--ssid NAME] | off
network.py tailscale status|up|down|operator|exit-node [IP|none]
```

Watch output:

```json
{"type":"state","nm_running":true,
 "wifi":{"device":"wlp2s0","hardware":true,"enabled":true,"ap_capable":true},
 "airplane":false,
 "wired":[{"device":"enp3s0","state":"connected","connection":"Wired connection 1"}],
 "active":[{"uuid":"…","name":"Home","type":"wifi","device":"wlp2s0","state":"activated","ssid":"Home"}],
 "vpn":[{"uuid":"…","name":"Work","kind":"openvpn","active":false,"last_used":1759000000}],
 "hotspot":{"active":false,"uuid":null,"ssid":null,"clients":0}}
{"type":"networks","networks":[{"ssid":"Home","signal":82,"band":"5 GHz","security":"wpa-psk",
  "in_use":true,"saved":true,"uuid":"…","hidden":false}]}
{"type":"needs_secrets","uuid":"…","ssid":"Home","device":"wlp2s0"}
{"type":"error","error":"NetworkManager isn’t running.","code":"nm_down"}
```

How it works:
- State: `nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device status`, `nmcli -t -f
  NAME,UUID,TYPE,ACTIVE,DEVICE,TIMESTAMP connection show`, `nmcli radio`, `nmcli -g
  WIFI-PROPERTIES.AP device show <dev>`, `rfkill --json`. Re-read on `nmcli monitor` lines
  (250 ms debounce, as `NetworkService.qml:54`).
- Scan (only while a menu asked for it): `nmcli device wifi rescan` (errors from NM's scan
  rate limit are ignored), then `nmcli -t -f IN-USE,SSID,SIGNAL,FREQ,SECURITY device wifi list
  --rescan no` every 8 s (the installer's interval). Parsing ports `splitTerse` /
  `ParseWifiList` (`host.go:376-429`); saved networks are matched by SSID through one
  `nmcli -g connection.uuid,802-11-wireless.ssid connection show <uuid>…` call for all Wi-Fi
  profiles (🔍 multi-profile output format, 12.4).
- Security (from nmcli's SECURITY, ported from `host.go:474-487`): empty → `open`; `OWE` →
  `owe`; `WEP` → `wep`; contains `802.1X` → `enterprise`; `WPA3` without `WPA2`/`WPA1` → `sae`;
  other WPA → `wpa-psk`.
- New network: `nmcli connection add type wifi ifname <dev> con-name <ssid> ssid <ssid>
  [802-11-wireless.hidden yes] [wifi-sec.key-mgmt wpa-psk|sae|none|owe] [wifi-sec.wep-key-type
  key|passphrase]` (no secret), then `nmcli --wait 40 connection up uuid <new> passwd-file
  /dev/fd/<r>` with `pass_fds=(r,)`; the pipe carries one line
  `802-11-wireless-security.psk:<secret>` (`wep-key0` for WEP). The profile is deleted if the
  activation fails. 🔍 12.4: NetworkManager accepting the secretless profile, nmcli reading the
  pipe, and the secret being saved (NM saves agent-returned system-owned secrets when the agent
  may modify the connection).
- Saved network with a new password: `connection up uuid <u> passwd-file /dev/fd/<r>` (profile
  kept on failure).
- Enterprise: `connection add … wifi-sec.key-mgmt wpa-eap 802-1x.eap peap|ttls
  802-1x.phase2-auth <m> 802-1x.identity <id> [802-1x.anonymous-identity …]
  [802-1x.domain-suffix-match …] (802-1x.system-ca-certs yes | 802-1x.ca-cert <path>)`; secret
  line `802-1x.password:<secret>`.
- VPN: `connection up uuid <u>` first; on missing secrets the menu asks and retries with the
  line `vpn.secrets.password:<secret>`. WireGuard keys live in the profile. Import:
  `nmcli connection import type openvpn|wireguard file <path>`.
- Share: `nmcli -s -g 802-11-wireless-security.psk connection show uuid <u>` (polkit may ask),
  payload `WIFI:T:WPA;S:<ssid>;P:<psk>;;` (`T:nopass` for open; `H:true;` for hidden; `\ ; , :
  "` escaped with `\`), rendered by `qrencode -t SVG -m 2 -l M -o -` with the payload on
  **stdin**. Output `{"ok":true,"ssid":…,"svg":"<svg…>"}` plus `"password"` only with
  `--reveal`. Refused for enterprise networks.
- Hotspot: `connection add type wifi ifname <dev> con-name "Arctic hotspot" ssid <name>
  802-11-wireless.mode ap ipv4.method shared wifi-sec.key-mgmt wpa-psk`, then `connection up
  … passwd-file` with a generated 12-character password (lowercase letters and digits, no
  look-alikes), stored by NetworkManager; the share card shows it. 🔍 12.4 that AP mode takes
  its PSK through `passwd-file`; if not, the fallback in 12.4 applies.
- `needs_secrets`: `gdbus monitor --system --dest org.freedesktop.NetworkManager` is read in
  `watch`; a line `…/Devices/N: org.freedesktop.NetworkManager.Device.StateChanged (uint32 120,
  uint32 …, uint32 7)` (FAILED, NO_SECRETS) for a Wi-Fi device whose last activation was a saved
  profile produces the event (🔍 12.4 exact line format; the parser is unit-tested against
  recorded lines).
- Error codes and copy (nmcli exit statuses 3 = timeout, 4 = activation failed, 8 = NM not
  running, 10 = not found):

| code | When | Sentence |
|---|---|---|
| `auth` | exit 4 with "Secrets were required" / reason 7 or 8 | That password didn’t work for “Home”. Check it and try again. |
| `timeout` | exit 3, or "timed out" | “Home” didn’t answer. Move closer to the router and try again. |
| `not_found` | exit 10 | “Home” is out of range now. |
| `nm_down` | exit 8 | NetworkManager isn’t running, so Wi-Fi can’t be changed. |
| `radio_off` | Wi-Fi off | Wi-Fi is off. Turn it on first. |
| `needs_certificate` | EAP-TLS | “eduroam” needs a certificate to sign in. Set it up in Edit connections. |
| `denied` | polkit refused | Arctic needs your permission to change this network. |
| `failed` | anything else | Couldn’t connect to “Home”. <first line of nmcli's error, ≤ 100 characters> |

- Fixture mode for screenshots and tests: `ARCTIC_NETWORK_FIXTURE=<file.json>` makes `watch`,
  `status`, `scan` and `saved` answer from the file and every change command succeed without
  running anything.

#### 6.2 `shell/scripts/bt-agent.py`

- Needs `python3-dbus` and GLib from python3-gobject (11.1). Protocol, stdout:
  ```json
  {"type":"ready","default":true}
  {"type":"request","id":3,"kind":"confirm","device":"/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF",
   "address":"AA:BB:CC:DD:EE:FF","name":"Pixel 9","icon":"phone","passkey":"042917"}
  {"type":"request","id":4,"kind":"show_passkey","name":"MX Keys","passkey":"042917","entered":3}
  {"type":"request","id":5,"kind":"service","name":"Pixel 9","service":"audio","uuid":"0000110d-…"}
  {"type":"cancel","id":3}
  {"type":"released"}
  {"type":"error","error":"Bluetooth isn’t running."}
  ```
  kinds: `confirm`, `passkey`, `pin`, `show_passkey`, `show_pin`, `authorize`, `service`.
  stdin: `{"op":"reply","id":3,"accept":true,"value":"1234"}`, `{"op":"default"}`,
  `{"op":"quit"}`.
- Validation: passkey replies 0-999999 (sent as uint32), PIN 1-16 printable characters;
  anything else is rejected with `org.bluez.Error.Rejected`.
- Pure parts (request building, reply validation, icon and service-name maps) are functions
  testable without D-Bus.

#### 6.3 `shell/scripts/audio.py`

```
audio.py devices                 {"ok":true,"devices":[{"id":45,"name":"alsa_card.pci-0000_00_1f.3",
                                  "description":"Built-in Audio","bus":"pci|usb|bluetooth",
                                  "profiles":[{"index":1,"name":"output:analog-stereo+input:analog-stereo",
                                               "description":"Analog Stereo Duplex","available":"yes","active":true}],
                                  "routes":[{"index":3,"device":7,"name":"analog-output-headphones",
                                             "description":"Headphones","direction":"output","available":"yes","active":true}]}]}
audio.py profile DEVICE_ID INDEX         wpctl set-profile DEVICE_ID INDEX
audio.py route DEVICE_ID ROUTE DEVICE    pw-cli set-param DEVICE_ID Route '{ index: ROUTE, device: DEVICE, save: true }'
```

Parses `pw-dump` (package pipewire-utils): objects of type `PipeWire:Interface:Device` with
`media.class` `Audio/Device`, `info.params.EnumProfile`, `Profile`, `EnumRoute`, `Route`. Sinks
map to devices through the node property `device.id` (valid while tracked). 🔍 12.4 the `Route`
write syntax and whether WirePlumber 0.5 on F44 offers `wpctl set-route` instead.

#### 6.4 `shell/scripts/brightness.py` and `arctic-osd`

```
brightness.py list                       {"ok":true,"displays":[
                                           {"output":"eDP-1","kind":"backlight","device":"intel_backlight","percent":60},
                                           {"output":"DP-1","kind":"ddc","bus":5,"model":"DELL U2723QE","percent":40}]}
brightness.py set OUTPUT PERCENT         {"ok":true,"output":"DP-1","percent":50}
brightness.py step OUTPUT|focused +5|-5  {"ok":true,"output":"DP-1","percent":45,"label":"DELL U2723QE"}
```

- Backlight: `brightnessctl -m -c backlight` (the internal output is the one named `eDP-*`,
  `LVDS-*` or `DSI-*`); step down keeps `arctic-osd`'s 1 % floor.
- DDC: `ddcutil detect --terse` (bus, `DRM connector: card1-DP-1` → output `DP-1`, model),
  cached in `~/.cache/arctic/ddc.json` for 10 minutes; `ddcutil --bus N getvcp 10 --terse`
  (`VCP 10 C 50 100`), `ddcutil --bus N setvcp 10 <value>`. After 3 failures a bus is skipped
  for 30 s. Only when `ddcutil` is installed (Recommends, 11).
- `focused`: `mmsg get all-monitors` → the monitor with `"active": true`.
- `dotfiles/.local/bin/arctic-osd` `brightness up|down` (41-50) becomes
  `python3 <shell>/scripts/brightness.py step focused ±5` when the shell scripts exist, then
  `arctic-shell-ipc osd brightnessLevel <percent> <label>`; the brightnessctl lines stay as the
  fallback. New `arctic-osd output next` → `arctic-shell-ipc audio nextOutput` (exits 1
  without the shell; documented).

#### 6.5 `shell/scripts/battery.py`

```
battery.py status   {"ok":true,"present":true,"path":"/org/freedesktop/UPower/devices/battery_BAT0",
                     "warning_level":"none|low|critical|action","percentage_low":20,"percentage_critical":5,
                     "percentage_action":2,"critical_action":"suspend|hibernate|poweroff",
                     "threshold_supported":true,"threshold_enabled":false,"threshold_start":75,"threshold_end":80}
battery.py limit on|off   gdbus call --system --dest org.freedesktop.UPower --object-path PATH
                          --method org.freedesktop.UPower.Device.EnableChargeThreshold true|false
battery.py watch          {"type":"warning_level","level":"low"} per change
```

- `WarningLevel` (1 none, 2 discharging/UPS, 3 low, 4 critical, 5 action) and the
  `ChargeThreshold*` properties through `gdbus call … org.freedesktop.DBus.Properties.GetAll
  org.freedesktop.UPower.Device`; `watch` reads `gdbus monitor --system --dest
  org.freedesktop.UPower --object-path /org/freedesktop/UPower/devices/DisplayDevice`.
- `critical_action`: `org.freedesktop.UPower.GetCriticalAction`; `Sleep` (and `Suspend`,
  `HybridSleep`) is resolved through `SleepOperation=` from `/etc/systemd/sleep.conf` and
  `sleep.conf.d` (default `suspend-then-hibernate suspend hibernate`) and logind
  `CanSuspendThenHibernate` / `CanSuspend` / `CanHibernate` (first `yes` wins).
- Percentages: `PercentageLow/Critical/Action` from `/etc/UPower/UPower.conf` and
  `/etc/UPower/UPower.conf.d/*.conf` (last wins), for copy only.

#### 6.6 `shell/scripts/keyboard.py`

```
keyboard.py watch        {"type":"layouts","layouts":[{"code":"us","variant":"","name":"English (US)","short":"en"},
                          {"code":"il","variant":"","name":"Hebrew","short":"he"}],"switch_key":"grp:alt_shift_toggle"}
                         {"type":"active","index":1,"name":"Hebrew"}
keyboard.py set INDEX    mmsg dispatch switch_keyboard_layout,INDEX+1   (Mango: 1-based, 0 cycles)
keyboard.py next         mmsg dispatch switch_keyboard_layout,0
```

- Layouts: the last `xkb_rules_layout=`, `xkb_rules_variant=`, `xkb_rules_options=` in the
  order Mango sources them (`dotfiles/.config/mango/config.conf:22-32`: `arctic/input.conf`,
  `/etc/arctic/mango/keyboard.conf`, `settings.conf`, `user.conf`). Names and short names from
  `/usr/share/X11/xkb/rules/evdev.xml` (`description`, `shortDescription`).
- Active: `mmsg watch keyboardlayout` → `{"layout":"Hebrew"}` mapped back to an index by
  description (variant descriptions such as "Hebrew (lyx)" included; 🔍 12.4 that Mango's name
  equals evdev.xml's description for every installer layout).
- `KeyboardService.qml` re-runs `layouts` when those files change (`FileView`
  `watchChanges`).

#### 6.7 Session helpers

- `dotfiles/.local/bin/arctic-session`: new function `shell_session` (the test at 22-24:
  `ARCTIC_SHELL != waybar`, quickshell present, `arctic-shell --path` succeeds). `mako)` (31)
  and `nm-applet)` (36) do nothing when `shell_session` is true; usage (6, 65) and the header
  comment say so. `autostart.conf:12-13` keep their lines (the fallback still needs them) with
  a comment.
- `dotfiles/.local/bin/arctic-notify`: new (5.4.6). `arctic-dnd`: IPC first (5.4.6).
- `dotfiles/.local/bin/arctic-shell-ipc:5-7`: the target list in the usage text adds the new
  targets (7).

### 7. `shell.qml`, `Bar.qml` and IPC

#### 7.1 `shell/shell.qml`

- Header comment 7-15: the new surfaces and targets.
- 20-22, new functions: 3.2.
- Instances after 81: `BarMenu { id: menuHost; shell: shell }`, `Toasts {}`,
  `BluetoothPairDialog { id: btPair }`, `WifiShare { id: wifiShare }`; `PolkitDialog { id:
  polkit }` (81). An id is not visible from other files, so `shell.qml` also declares
  `readonly property var barMenu: menuHost` (used as `barMenu` in 3.2 and as
  `bar.shell.barMenu` in `Bar.qml`).
- `Variants { Bar { shell: shell } }` (68-71): each `Bar` registers `shell.bars[screen.name]`.
- IPC handlers (after 143):

| Target | Functions |
|---|---|
| `panel` | `toggle(name)`, `open(name)`, `close()` — names: network, bluetooth, sound, notifications, calendar, battery, media, display, keyboard |
| `quick` | `toggle()`, `open(page: string)` (empty = main page) |
| `toggle` | `set(key, mode)` (`on`/`off`/`toggle`), `get(key): string`, `states(): string` |
| `notifications` | `toggle()`, `dismiss()`, `dismissAll()`, `invoke()`, `count(): int`, `dnd(mode): string` (`on`, `off`, `toggle`, `1h`, `tomorrow`, `state`; returns `on`/`off`/`unowned`), `clearHistory()` |
| `dnd` | `refresh()` kept for old `arctic-dnd` copies |
| `bluetooth` | `pair()` (opens the Bluetooth menu on the pairing page) |
| `media` | `playPause()`, `next()`, `previous()` |
| `audio` | `nextOutput()` |
| `keyboard` | `next()`, `set(index: int)` |
| `bar` | `focus()` (keyboard mode, 8.3) |
| `osd` | adds `brightnessLevel(percent: int, label: string)` |

Every function declares its parameter and return types (`string`, `int`, `bool`), as
Quickshell's `IpcHandler` requires. No function is named `show` (`shell.qml:127` explains why)
or `list`.

#### 7.2 `shell/Bar.qml` (line by line)

- Imports (6-8) unchanged (`MediaItem.qml` imports `Quickshell.Services.Mpris` itself).
- 29-30: `hint()` does nothing while `bar.shell.barMenu.open && bar.shell.barMenu.screen ===
  bar.screen`; opening a menu releases the current tooltip.
- New `anchorFor(name)`: returns `item.mapToItem(null, item.width / 2, 0).x` for the visible item
  that owns the panel (`bellItem`, `bluetoothItem`, `networkItem`, `volumeItem`, `batteryItem`,
  `clockItem`, `mediaItem`, `keyboardItem`), else `null`.
- 88-96: the clock `Text` → `BarItem` `clockItem` (5.5); `ModeIndicators` to its left,
  `MediaItem` to its right.
- 125-134 bell: `iconName` from `NotificationService` (5.4.3); left → `togglePanel
  ('notifications', …)`; right → do not disturb on/off (the old left-click action); `visible:
  NotificationService.owned || DndService.available`; when not owned, the 0.2 behaviour.
- 135-147 Bluetooth: left → `togglePanel('bluetooth', …)`; right (145) unchanged; tooltip adds
  the first connected device's battery ("Connected to MX Keys · 80 %").
- 149-177 tray: filter (151) adds `blueman*`; 164/166 open `togglePanel('tray', bar.screen,
  x, { item: modelData })`; delete `QsMenuAnchor` 169-175.
- 179-199 network: delete `applet` (182), the branch (186-189) and `QsMenuAnchor` (192-198);
  left → `togglePanel('network', …)`; right → `arctic-settings network`.
- 200-210 volume: left → `togglePanel('sound', …)`; right (207) and scroll (208) unchanged.
- 211-231 battery: bind to `BatteryService`; `interactive: true` (223); left →
  `togglePanel('battery', …)`.
- New `KeyboardItem` between the tray Repeater and `networkItem`.
- Every item with a menu sets `hasMenu: true` and `active: bar.shell.barMenu.open &&
  bar.shell.barMenu.panel === '<name>' && bar.shell.barMenu.screen === bar.screen`.
- Bar keyboard mode (8.3): `focusMode`, `WlrLayershell.keyboardFocus: focusMode ?
  Exclusive : None`, a `Keys` handler on a `FocusScope` over the two `RowLayout`s and the
  centre cluster, `stops` = visible interactive items left to right.

### 8. Keyboard behaviour

#### 8.1 Global keys (`dotfiles/.config/mango/arctic/binds.conf`)

New block after "Notifications" (73-76), and edits there:

```
# ---- Notifications ------------------------------------------------------
bind=SUPER,Delete,spawn,arctic-notify dismiss
bind=SUPER+SHIFT,Delete,spawn,arctic-notify dismiss-all
bind=SUPER+SHIFT,n,spawn,arctic-dnd toggle
bind=SUPER+ALT,n,spawn,arctic-notify center
bind=SUPER+ALT,comma,spawn,arctic-notify invoke

# ---- Menus on the bar (Omarchy-style panel keys) --------------------------
bind=SUPER,a,spawn,arctic-shell-ipc quick toggle
bind=SUPER+CTRL,w,spawn,arctic-shell-ipc panel toggle network
bind=SUPER+CTRL,b,spawn,arctic-shell-ipc panel toggle bluetooth
bind=SUPER+CTRL,a,spawn,arctic-shell-ipc panel toggle sound
bind=SUPER+CTRL,p,spawn,arctic-shell-ipc panel toggle battery
bind=SUPER+CTRL,d,spawn,arctic-shell-ipc quick open display
bind=SUPER+CTRL,t,spawn,arctic-shell-ipc panel toggle calendar
bind=SUPER+CTRL,m,spawn,arctic-shell-ipc panel toggle media
bind=SUPER+ALT,b,spawn,arctic-shell-ipc bar focus
```

and in "Hardware keys" (87-95): `bindl=SHIFT,XF86AudioMute,spawn,arctic-osd output next`.

| Key | Action | Clash check |
|---|---|---|
| Super + A | Quick Settings | unbound in binds.conf and apps.conf (Super+Shift+A = Get apps is a different combo) |
| Super + Ctrl + W / B / A / P / D / T / M | network, Bluetooth, sound, battery, display, calendar, media | only Super+Ctrl+arrows are bound (45-48); night light (Super+Ctrl+N), keep awake (Super+Ctrl+I), emoji (Super+Ctrl+E), capture menu (Super+Ctrl+C), share (Super+Ctrl+S) and reminders (Super+Ctrl+R) in other sections use other letters |
| Super + Alt + N | notification centre | free; command-menu (Super+Alt+Space), recording (Super+Alt+R), drop-down terminal (Super+Alt+Return), window extras (Super+Alt+G, Super+Alt+arrows), keyboard pointer (Super+Alt+K) use other keys |
| Super + Alt + comma | run the newest notification's default action | free (Super+comma = focusmon 68, Super+Shift+comma = tagmon 70) |
| Super + Alt + B | bar keyboard mode | free; replaces the design's Super+B, which D7 gives to the browser |
| Shift + XF86AudioMute | next sound output | free (only plain XF86AudioMute is bound, 89) |
| Super + Delete, Super + Shift + Delete, Super + Shift + N | unchanged keys, new commands | — |

Layout-switch keys from Settings (`arctic_settings.py:2053-2054`): none of the new keys holds
Alt and Shift together (`grp:alt_shift_toggle`, `grp:lalt_lshift_toggle`), Ctrl and Shift
together (`grp:ctrl_shift_toggle`), Alt + Space (`grp:alt_space_toggle`) or Caps Lock
(`grp:caps_toggle`, `grp:alt_caps_toggle`). With `grp:toggle` (Right Alt alone switches
layouts) the Super + Alt keys must be pressed with the left Alt; `Keyboard-Shortcuts.md` says
so. Omarchy's "open history" key Super+Shift+Alt+comma is not copied because it holds Alt+Shift.
The shortcuts section's collision check (D7) reads these lines from binds.conf like every other
Arctic bind.

`dotfiles/.local/share/arctic/keys.txt`: a new "Menus" block after "Everyday" (4-13) and edits
in "System" (36-45):

```
  Menus
    Super + A                Quick settings
    Super + Ctrl + W         Network and Wi-Fi
    Super + Ctrl + B         Bluetooth
    Super + Ctrl + A         Sound
    Super + Ctrl + P         Battery and power mode
    Super + Ctrl + D         Brightness
    Super + Ctrl + T         Calendar
    Super + Ctrl + M         Media
    Super + Alt + N          Notifications
    Super + Alt + B          Use the bar with the keyboard
```

One entry per line: `parse_sheet` (`arctic_settings.py:869-882`) and `KeysSheet.qml` split a
line into keys and text at the first run of two or more spaces, so two entries on one line would
break. "System" (36-45; the sheet has no hardware block) gains
`    Super + Alt + ,          Open the newest notification` and
`    Shift + Mute key         Next sound output`, and line 41 keeps "Dismiss notification
(Shift: all)". If the generated-keys-sheet work replaces keys.txt with output from binds.conf,
these texts become the bind comments instead.

#### 8.2 Inside a menu (`MenuList`, every panel)

| Key | Does |
|---|---|
| Up / Down | previous / next row, switch or slider; skips disabled rows; wraps |
| Home / End, PgUp / PgDn | first / last; 5 rows |
| Enter | activate the row (connect, pick device, run action); on a switch row toggle |
| Space | toggle a switch row or tile; on a slider: mute |
| Left / Right | on a slider: −5 / +5 % (PgUp/PgDn ±10, Home/End 0/100 while the slider has focus); on a row with a chevron: Right opens the page; in a page: Left goes back; in the calendar: move the day |
| Tab / Shift+Tab | next / previous group (header switch → list → footer), and into a card's buttons |
| Ctrl+Tab / Ctrl+Shift+Tab | the neighbouring bar menu on the same bar (order of the bar items), keeping the menu open |
| Menu key, Shift+F10, right click | the row's actions page |
| Delete | forget (saved network, device), dismiss (notification), clear group (group header) |
| Shift+Delete | clear all notifications (centre) |
| letters | type-ahead: jump to the next row whose label starts with what was typed in the last 800 ms (off while a text field has focus) |
| Esc | leave a text field / go back one page / close the menu |

The focus ring shows only after a key press (`keyboardNav`, the `ArSelect.qml` pattern) and
disappears on pointer movement; hover and keyboard highlight share the `surfaceSunken` look.

#### 8.3 The bar with the keyboard (`Super + Alt + B`)

- `bar focus` puts the bar on the focused output in keyboard mode: `keyboardFocus: Exclusive`,
  the first stop (fox mark) gets `keyboardFocused`.
- Left / Right move across the visible items (fox, each workspace, indicators, clock, media,
  Install/Update, bell, Bluetooth, tray items, keyboard chip, network, volume, battery, power);
  Home / End jump to the ends.
- Enter, Space or Down open the item's menu (or run its click action); the menu takes the keys
  (Overlay wins over Top, 3.3); closing it with Esc returns to bar mode on the same item.
- Esc, `Super + Alt + B` again, a pointer click on the bar, running an action that opens a
  window, or 10 s without a key leave bar mode (`keyboardFocus: None`).
- Screen readers: every item has `Accessible.name` from its tooltip (as today, `BarItem.qml:33`).

### 9. Settings app changes

#### 9.1 Network (`settings/pages/NetworkPage.qml`)

- Comment 1-3: joining happens in the shell's network menu (`network.py`); the editor is for
  proxies and fixed addresses.
- Lede 12: "Your connections. Join a Wi-Fi network from the network menu on the bar
  (Super + Ctrl + W)."
- New group "Saved Wi-Fi networks": rows from `Backend.call(['network-saved'])` with "Forget"
  (`network-forget UUID`), search key `network.saved`.
- New group "VPN": profiles from the same call (`vpn`), a Connect/Disconnect button each, and
  "Import a VPN file…" (a `FileDialog`, as `AppearancePage.qml:361`, filter `*.ovpn *.conf`) →
  `vpn-import openvpn|wireguard PATH`; the type is guessed from the file (`[Interface]` →
  WireGuard). Search key `network.vpn`. Company Wi-Fi with a CA file: "Add company Wi-Fi…"
  opens the shell menu's page, and a CA certificate can be picked here (`network-ca-set UUID
  PATH`).
- "More" (86-113) unchanged.
- `arctic_settings.py`: `network-saved`, `network-forget UUID…`, `vpn-import TYPE PATH`,
  `vpn-up UUID`, `vpn-down UUID`, `network-ca-set UUID PATH`, each running
  `shell_script(paths, 'network.py')` and passing its JSON through (`ok`/`error`).
  `cmd_network`/`cmd_wifi` stay.

#### 9.2 Bluetooth (`settings/pages/BluetoothPage.qml`)

- Comment 1-3: pairing and codes happen in the shell's Bluetooth menu and dialog.
- 80-91: desc "Finds devices near you. Pairing codes appear in Arctic’s own dialog."; button
  "Pair a device" → `Backend.call(['bluetooth-pair'])`; enabled when the shell runs or blueman
  is installed.
- New row "More Bluetooth options" (`caps.blueman`): "Open the Bluetooth manager" →
  `blueman-manager`, desc "File transfer and advanced settings."
- `arctic_settings.py` `bluetooth-pair`: runs `arctic-shell-ipc bluetooth pair`; on a non-zero
  exit launches `blueman-manager` when installed and answers `{"ok":true,"opened":"blueman"}`,
  else `{"ok":false,"error":"The Arctic shell isn’t running, and the Bluetooth manager isn’t
  installed."}`.

#### 9.3 Sound (`settings/pages/SoundPage.qml`)

- Comment 1-3 and the "More" group (115-128): title "Volume per app and device profiles", desc
  "The sound menu on the bar has both (Super + Ctrl + A). The volume control is there for
  everything else."; buttons "Open the sound menu" (`arctic-shell-ipc panel open sound`) and
  "Open the volume control" (unchanged, behind the caps).

#### 9.4 Power (`settings/pages/PowerPage.qml`)

- New group "Battery" (only when `battery` answers `present: true`), after "Power mode"
  (72-87): "Limit charging to 80 %" (`battery-limit on|off`, hidden without
  `threshold_supported`, label with `threshold_end`), "Battery health" (read-only), "Warn me when
  the battery is low" (`shell-set battery_warnings true|false`). Search keys `power.battery`,
  `power.limit`, `power.warnings`.
- `arctic_settings.py`: `battery` (→ `battery.py status`), `battery-limit on|off`,
  `shell-set KEY VALUE` (atomic write of `~/.config/arctic/shell.json`; keys allowed:
  `battery_warnings`; `Session.qml` reads them as `settings.batteryWarnings` via a small key map,
  or the key is spelled `batteryWarnings` to match `frame` — decide in review, 15).

#### 9.5 Notifications (new `settings/pages/NotificationsPage.qml`)

- Groups: "Do not disturb" (switch, durations `ArSegmented`: Until I turn it off / 1 hour /
  Until tomorrow; "On a schedule" switch with from/to times); "History" ("Keep notifications
  after they’re dismissed" switch, "Clear history" button); "Apps" (every app from
  `notification-apps.json`: switches "Show pop-ups", "Keep in history", "Show during do not
  disturb", "Hide its urgent notifications during do not disturb").
- `arctic_settings.py`: `notifications` (reads both files and whether the shell owns the bus
  name via `arctic-shell-ipc notifications dnd state`), `notification-set KEY VALUE`,
  `notification-rule-set APP KEY on|off`, `notification-history-clear`. Writes are atomic and
  go through `settings_lock` (added to `WRITERS`, 2567-2569).
- `settings/pages/qmldir`, `settings/SearchIndex.js` (`PAGES` entry `notifications`, icon
  `bell`, words "alerts do not disturb dnd history banners pop-ups"; rows
  `notifications.dnd`, `notifications.history`, `notifications.apps`).
- `TOOLS` (2519-2524): add `shellIpc: 'arctic-shell-ipc'`, `qrencode`, `ddcutil`, `tailscale`.

### 10. What stays, and fallbacks

| Tool | Stays because | Reached from |
|---|---|---|
| nm-connection-editor | proxies, fixed addresses, EAP-TLS, uncommon VPN types | "Edit connections…" (network menu), Settings → Network |
| blueman-manager | file transfer, advanced adapter settings; its applet is the agent in the waybar session | "More Bluetooth options…" (Bluetooth menu), Settings → Bluetooth |
| pavucontrol / pwvucontrol | everything the sound menu doesn't do (routing, sample formats) | "Volume control…" (sound menu), Settings → Sound |
| nm-applet | the waybar session's network menu and secret agent | autostart in the waybar session only (6.7) |
| mako | the waybar session; D-Bus activation when the shell isn't running | autostart in the waybar session; handed over to the shell (5.4.1) |
| nmtui | terminal fallback | Settings → Network |
| waybar clicks (`config.jsonc:78-79, 89, 107, 117`) | fallback desktop | unchanged |

Hide, don't fake (`Bar.qml:13`, `shell/README.md:116-118`): no adapter → no Bluetooth item or
tile; no nmcli → no network item, Wi-Fi/airplane/VPN tiles; no battery → no battery item;
no power-profiles service → no power rows; no player → no media item; one layout → no layout
chip; no DDC/backlight → no brightness slider; the notification centre off when another daemon
owns the name.

### 11. Packaging deltas (`packaging/arctic-linux.spec`)

#### 11.1 arctic-shell (240-253)

- Add `Requires: python3-dbus` and `Requires: python3-gobject-base` (bt-agent.py; 🔍 12.4 that
  `from gi.repository import GLib` works with only -base on F44, else `python3-gobject`),
  `Requires: glib2` (gdbus for notifications ownership, battery, network events), `Requires:
  pipewire-utils` (pw-dump, pw-cli for audio.py), `Requires: util-linux` (rfkill; already
  pulled by arctic-desktop-config).
- `Recommends: qrencode` (Wi-Fi share), `Recommends: NetworkManager-openvpn` (VPN import).
- Description (254-257): add the bar menus, Quick Settings, notification daemon and agents.

#### 11.2 arctic-desktop (402-482)

- `Requires: pavucontrol` (439), `network-manager-applet` (440), `blueman` (442) →
  `Recommends:`; add `Requires: bluez` (blueman pulled it in until now).
- `Requires: mako` (427) → `Recommends: mako`; same in arctic-desktop-config (177). mako stays
  in the image through `plusRecommended` (`config.kiwi:58`).
- `Recommends: ddcutil`, `Recommends: qrencode`, `Recommends: NetworkManager-openvpn`.
- arctic-settings keeps its Recommends (278-280).

#### 11.3 Image and non-RPM install

- `iso/kiwi/config.kiwi:66-71`: no package change (plusRecommended pulls the new Recommends);
  the comment at 66-67 becomes "the tools behind the bar menus' and Settings' "More…" links".
- `dotfiles/install.sh:37-40`: add `python3-dbus python3-gobject-base pipewire-utils qrencode`.

#### 11.4 Version

- The spec `Version:` (36) becomes 0.3.0 with the rest of the release (D1); nothing here depends
  on it.

#### 11.5 Mango rules (`dotfiles/.config/mango/arctic/rules.conf`)

- Line 15 regex adds `updates|menu|toasts|bt-pair|wifi-share`:
  `^arctic-(frame|frame-reserve|launcher|popover|wallpapers|power|keys|polkit|osd|desktop|updates|menu|toasts|bt-pair|wifi-share)$`.
- New rule after it (repeats the three flags because a later matching rule resets them, lines
  4-7): `layerrule=noblur:1,noshadow:1,noanim:1,shield_when_capture:1,layer_name:^arctic-(polkit|bt-pair|wifi-share)$`.
- Windows: `windowrule=shield_when_capture:1,appid:^org\.keepassxc\.KeePassXC$` and
  `windowrule=shield_when_capture:1,appid:^Bitwarden$` (🔍 12.4 the Bitwarden app id on
  Wayland, Flatpak and RPM).
- Float rules 30-32 stay.

### 12. Tests

#### 12.1 Python (`shell/tests`, run by CI `shell-tests`, `ci.yml:78-82`)

- `test_network.py` (fake `nmcli`, `gdbus`, `rfkill`, `qrencode` in a temp PATH, the
  `fake_command` pattern of `test_helpers.py`):
  - no argv of any fake command ever contains the secret; the secret arrives through the
    `passwd-file` fd with the right setting name per security type (PSK, SAE, WEP, 802.1X,
    VPN, hotspot);
  - `splitTerse` escapes (`Café\:5G`), dedupe with best signal, sort order, security mapping
    for every SECURITY string in the table;
  - error mapping for exit codes 3, 4 (+ "Secrets were required"), 8, 10 and polkit denial;
    the new profile is deleted on failure, a saved one is kept;
  - `needs_secrets` parsing of recorded `gdbus monitor` lines;
  - QR payload escaping and `T:nopass`, and the payload goes to qrencode's stdin;
  - `--ask` refuses newlines, NUL and > 4 KiB; fixture mode answers without running commands.
- `test_bt_agent.py`: request building for every kind (zero-padded passkeys), reply validation
  (0-999999, PIN length), icon and service maps; with `dbus-run-session` and
  `python3 -m dbusmock --template bluez5` available (🔍 12.4 that the template has
  AgentManager1), registration, `RequestDefaultAgent`, a `RequestConfirmation` round trip and
  the 90 s cancel (clock injected); skipped otherwise.
- `test_audio.py`: `pw-dump` fixtures (built-in card with headphone/speaker routes, a Bluetooth
  headset with A2DP/HFP profiles, USB), command lines for profile and route.
- `test_brightness.py`: `ddcutil detect --terse` and `getvcp` parsing, connector → output
  mapping, cache expiry, 3-failure cool-down, backlight floor, `focused` from a recorded
  `all-monitors` answer.
- `test_battery.py`: `GetAll` and `monitor` output parsing, `WarningLevel` mapping, sleep
  resolution from `sleep.conf` + logind answers, UPower.conf drop-ins.
- `test_keyboard.py`: config-chain parsing (last value wins), evdev.xml names and short names,
  name → index mapping, `set 0` → `switch_keyboard_layout,1`, `next` → `,0`.
- CI: `ci.yml:74` adds `python3-dbus python3-gobject-base python3-dbusmock dbus-daemon` to the
  `shell-tests` install line (🔍 python3-dbusmock in F44).

#### 12.2 Node (`shell/tests/*.cjs`, `ci.yml:91-97`)

- `test-menu-nav.cjs`: `MenuNav.js` stepping, wrap, disabled skip, groups, type-ahead.
- `test-calendar-grid.cjs`: `CalendarGrid.js` weeks for Monday/Sunday starts, ISO week 53
  years (2026-12-31 is W53), leap Februaries, today marking.
- `test-notification-rules.cjs`: `NotificationRules.js` `decide()` for every row of 5.4.5,
  schedule across midnight, synchronous-tag replacement, history cap and transient skip,
  grouping.
- `test-icons.cjs`: every `name: '…'` / `iconName: '…'` literal in `shell/*.qml` resolves in
  `design-data.js` or `icons-extra.js`; no `EXTRA` name shadows a design name; every `EXTRA`
  body parses as SVG path data; the glyphs shared with `settings/assets/SettingsIcons.js` are
  byte-identical.

#### 12.3 QML and screenshots

- qmllint (`ci.yml:129-148`) over all new files.
- New CI job `shell-headless` (like `settings-headless`, `ci.yml:150-168`): installs quickshell,
  sway, grim, pipewire, wireplumber, pipewire-utils, python3-dbus, python3-gobject-base,
  dbus-daemon, libnotify; runs `shell/dev/headless.sh` with `ARCTIC_NETWORK_FIXTURE` and these
  steps, fails when `/tmp/arctic-shell.log` has QML errors, uploads the screenshots:
  `ipc panel open network sleep 1 shot network-menu`, `ipc panel open sound sleep 1 shot
  sound-menu` (the null sink the script creates), `sh notify-send -a Test "Hello" "World" sleep
  1 shot toast`, `ipc panel open notifications sleep 1 shot notification-centre`, `ipc quick
  toggle sleep 1 shot quick-settings`, `ipc panel open calendar sleep 1 shot calendar`, `ipc
  power toggle sleep 1 shot power-menu`, both themes.
- `shell/dev/headless.sh`: stop starting mako (the shell owns notifications); `--mako` starts
  it first to test the hand-over (5.4.1); `--fixtures` also starts
  `shell/tests/fixtures/sni-menu.py` (a python3-dbus StatusNotifierItem with a DBusMenu:
  separator, checkbox, radio pair, disabled entry, submenu, icon). Tray menus have no IPC, so the
  screenshot step clicks the tray icon: `point <x> 17 click sleep 1 shot tray-menu` (pointer
  steps are unreliable in headless sway, `headless.sh:14-17`; the step is informative and does
  not fail the job).
- Settings: `test_arctic_settings.py` for the new commands (fake `arctic-shell-ipc`, fake
  scripts via `ARCTIC_SHELL_DIR`), `bluetooth-pair` fallback, `shell-set` whitelist, rule and
  history writes; `settings/dev/headless.sh --smoke` covers `NotificationsPage`.

#### 12.4 Hands-on checks on Fedora 44 hardware (🔍 list, each with its proof)

| # | Claim | Proof |
|---|---|---|
| 1 | `nmcli connection add … wifi-sec.key-mgmt wpa-psk` without a PSK is accepted, `connection up … passwd-file /dev/fd/N` reads the pipe, and the PSK is saved (reconnect after reboot works) | join WPA2, WPA3 and WEP networks from the menu on a laptop; `sudo cat /etc/NetworkManager/system-connections/Home.nmconnection` has `psk=`; `ps -eo args` during the join never shows it. Fallback if it fails: `network.py` calls `AddAndActivateConnection2` over python3-dbus (already a Requires), the secret travelling only over D-Bus |
| 2 | a normal wheel user (and liveuser) may create system connections without a polkit prompt | same test on an installed system and the live USB; if a prompt appears the shell's polkit dialog handles it |
| 3 | `passwd-file` values with `:`, `\` and trailing spaces | passwords `a:b\c ` on a test AP |
| 4 | AP mode takes its PSK through `passwd-file` | hotspot on; a phone joins with the shown password |
| 5 | `gdbus monitor` line format for `Device.StateChanged` and reason 7 after a router password change | change the AP password; the toast appears |
| 6 | NetworkManager-initiated secret requests fail cleanly with no agent (no hang) | as 5, plus a VPN with a stored password removed |
| 7 | Quickshell's server takes the name after `pkill mako`; `GetConnectionUnixProcessID` equals `Quickshell.processId` | `notify-send` before the shell starts (autostart order), then check `busctl --user status org.freedesktop.Notifications` |
| 8 | notify-send `-A` actions, `-w`, replaces_id, `x-canonical-private-synchronous`, `arctic-welcome`'s blocking actions | run each against the shell |
| 9 | PipeWire default-sink crashes (36517a2/13fe9b0 absent): switch outputs from the menu, unplug headphones, disconnect a BT headset with the menu open and closed | if the shell crashes, route default changes through `wpctl set-default ID` and note the crash in the 0.3.1 follow-up |
| 10 | blueman-applet's SNI id and default-agent fight | open "More Bluetooth options…", close blueman, pair a keyboard: the Arctic dialog shows |
| 11 | keyboard pairing (DisplayPasskey), phone pairing (RequestConfirmation), legacy PIN (RequestPinCode), incoming phone AuthorizeService | pair each kind |
| 12 | python3-gobject-base is enough for `GLib.MainLoop` | `dnf install python3-dbus python3-gobject-base` in a clean container, run `bt-agent.py` |
| 13 | python3-dbusmock in F44 and its bluez5 template has AgentManager1 | CI container |
| 14 | `/dev/rfkill` is writable by the active session user (uaccess) | `rfkill block wlan` as the user on F44 |
| 15 | `EnableChargeThreshold` polkit rule and the threshold values UPower reports | a ThinkPad and a laptop without support (switch hidden) |
| 16 | Caps Lock LED path | two keyboards (laptop, USB) |
| 17 | Mango's layout name equals evdev.xml's description for layouts the installer offers | switch through us/il/de/ru/ara on a test install |
| 18 | tray menus: mnemonic underscores, property updates, `/NO_DBUSMENU` apps | Steam, Discord (Flatpak), nm-applet in waybar mode, the fixture |
| 19 | privacy: xdpw node name, camera via the portal vs V4L2 | Firefox/Chromium with portal camera, OBS, a screen share in a browser |
| 20 | `inkSubtle` icons on `frost` reach 3:1 in both themes | contrast check with the token values |
| 21 | Route write syntax (`pw-cli set-param … Route`) or `wpctl set-route` | switch headphones ↔ speakers on a laptop jack |
| 22 | `nmcli -g … connection show <uuid>…` output for several profiles | two saved networks |
| 23 | tailscale operator flow | `dnf install tailscale`, sign in, toggle from the menu |
| 24 | `makoctl list -j` shape (only for `arctic-notify count` without the shell) | waybar session |
| 25 | Bitwarden Wayland app id | install the Flatpak and the RPM, `mmsg get focusing-client` |

### 13. Docs to update

- `shell/README.md`: deps (31-33: python3-dbus, python3-gobject-base, glib2, pipewire-utils;
  the bar no longer needs mako); surfaces table (37-52: bar menus, Quick Settings, toasts and
  notification centre, pairing dialog, helpers); IPC table (75-87, 7.1); Developing (89-98: new
  tests, fixture flags); design notes (116-118: the lock screen now counts notifications; "the
  bell without mako" → "the bell without a notification service").
- `docs/BUILD-SPEC.md`: package list (80-90), autostart (94-99: mako and nm-applet only in the
  waybar session; the shell owns notifications), IPC (101-104), app theming line 149 ("tray
  menus" are drawn by the shell now; GTK/Qt context menus and dialogs still inherit their
  toolkit's theme), Settings' tools (208-215), line 264 (mako's notifications → the shell's
  toasts follow the focused output), kiwi note (271-272).
- `docs/PLAN.md`: 180 (Notifications row: the Arctic shell; mako in the fallback), 328 (no
  nm-applet unit in the shell session).
- `docs/wiki/Desktop-Tour.md`: the right-hand table (29-39), a new "Quick settings" section,
  "Notifications and do not disturb" (157-165), media, calendar, indicators, keyboard chip.
- `docs/wiki/Keyboard-Shortcuts.md`: System (62-76) and a new "Menus" table; the Right Alt note
  (8.1); "In a menu" keys (8.2); bar keyboard mode (8.3).
- `docs/wiki/Settings.md`: Network (211-213), Bluetooth (218-221), Sound, Power, new
  Notifications page.
- `docs/wiki/Troubleshooting.md`: "No network" (242-250: the menu, nmcli fallback kept), new
  entries "Pairing asks for a code", "Notifications don't appear / another notification
  service", "The mic indicator doesn't show for my browser" (V4L2).
- `docs/wiki/Architecture.md:203` (autostart) and the shell section (helpers, agents).
- `docs/wiki/Release-Notes.md`: 0.3.0 entry with the behaviour changes: the bell's left click
  opens the centre (right click toggles do not disturb); do not disturb keeps urgent
  notifications unless an app is silenced; nm-applet, mako, blueman and pavucontrol are no
  longer hard dependencies; bar focus is Super + Alt + B.
- `dotfiles/README.md:138-141`: both notes are resolved (bar keyboard access, lock-screen count).
- `design/guidelines/10-platforms.md:16`: Notifications row → the shell's toasts (`Toasts.qml`,
  same tokens), mako for the fallback.

### 14. Interfaces with other sections, work packages and order

#### 14.1 What other sections rely on, or give

- **Shortcuts (D7)**: screenshot notifications with actions (`notify-send -A`) need the shell's
  server to advertise `actions` (5.4.1) and to keep an action-waiting `notify-send` alive until
  a button or dismissal (the server never closes a notification on its own, 5.4.2). Its
  collision check over Arctic's binds sees the keys in 8.1. Super+B (browser) and the unbound
  Super+W are theirs; bar focus moves to Super+Alt+B here.
- **Omarchy features**: night light, keep awake, screen recording and game mode add `Toggle`
  entries to `ToggleRegistry.qml` (tile, `toggle set`, indicator). Hardware keys may bind
  `XF86RFKill` to `arctic-shell-ipc toggle set airplane toggle` (🔍 whether the kernel's
  rfkill-input already toggles, which would double it). OSD kinds may absorb `showLayout` and
  `showPower`. The command menu and launcher modes can list `ToggleRegistry` entries and
  `panel` targets. The generated keys sheet takes the texts in 8.1.
- **Web app engine (s2)**: web-app notifications reach this server through GTK/GNotification
  with a `desktop-entry` hint equal to the web app id, so per-app rules and grouping work per web
  app. Nothing else is shared.
- **Get apps / Remove apps**: none; both stay in the launcher popover (closed by
  `closePopovers` like today).

#### 14.2 Work packages and order

1. **A. Toolkit and host** (everything else depends on it).
2. **F. Notifications** (toasts are used by B, D, H for their messages) and **B. Network**,
   **C. Bluetooth**, **D. Sound** in parallel.
3. **E. Tray**, **G. Calendar**, **H. Battery/power**, **I. Media**, **K. Keyboard layout**.
4. **J. Quick Settings, registry, indicators, display** (binds the services of B-K).
5. **L. Bar keyboard mode and panel keys** (needs every panel).
6. **M. Packaging, CI and docs** (lands with the last package; the spec edits are listed per
   package so they can merge one by one).

| Package | New files it owns | Shared files it edits |
|---|---|---|
| A. Toolkit and host | `BarMenu.qml`, `ShadowLayers.qml`, `MenuList.qml`, `MenuNav.js`, `MenuRow.qml`, `MenuSwitchRow.qml`, `MenuSlider.qml`, `ArcticSlider.qml`, `MenuSection.qml`, `MenuSeparator.qml`, `MenuHeader.qml`, `MenuPage.qml`, `MenuField.qml`, `Spinner.qml`, `SignalIcon.qml`, `assets/icons-extra.js`, `tests/test-menu-nav.cjs`, `tests/test-icons.cjs` | `Popover.qml`, `Theme.qml`, `assets/Icons.js`, `BarItem.qml`, `PowerMenu.qml`, `UpdatePopover.qml`, `qmldir`, `shell.qml` (3.2, 3.3, `panel` IPC), `Bar.qml` (tooltip, `anchorFor`, registration), `rules.conf` line 15, `settings/assets/SettingsIcons.js` |
| B. Network | `NetworkPanel.qml`, `WifiShare.qml`, `scripts/network.py`, `tests/test_network.py`, `tests/fixtures/network/*.json` | `NetworkService.qml`, `Bar.qml` 179-199, `shell.qml`, `NetworkPage.qml`, `arctic_settings.py`, `SearchIndex.js`, `arctic-session`, spec, `rules.conf` |
| C. Bluetooth | `BluetoothPanel.qml`, `BluetoothService.qml`, `BluetoothPairDialog.qml`, `scripts/bt-agent.py`, `tests/test_bt_agent.py` | `Bar.qml` 135-151, `shell.qml`, `BluetoothPage.qml`, `arctic_settings.py`, spec, `install.sh`, `ci.yml`, `rules.conf` |
| D. Sound | `SoundPanel.qml`, `scripts/audio.py`, `tests/test_audio.py`, `tests/fixtures/pw-dump-*.json` | `AudioService.qml`, `Bar.qml` 200-210, `SoundPage.qml`, `binds.conf`, `arctic-osd`, `keys.txt`, spec |
| E. Tray | `TrayPanel.qml`, `tests/fixtures/sni-menu.py` | `Bar.qml` 149-177, `headless.sh` |
| F. Notifications | `NotificationService.qml`, `Toasts.qml`, `ToastCard.qml`, `NotificationCard.qml`, `NotificationCenter.qml`, `NotificationRules.js`, `tests/test-notification-rules.cjs`, `dotfiles/.local/bin/arctic-notify`, `settings/pages/NotificationsPage.qml` | `DndService.qml`, `Bar.qml` 125-134, `LockScreen.qml`, `shell.qml`, `arctic-dnd`, `arctic-session`, `binds.conf` 73-76, `keys.txt`, `rules.conf`, `headless.sh`, spec (mako), `settings/pages/qmldir`, `SearchIndex.js`, `arctic_settings.py`, `design/guidelines/10-platforms.md` |
| G. Calendar | `CalendarPanel.qml`, `CalendarGrid.js`, `tests/test-calendar-grid.cjs` | `Bar.qml` 88-96, `binds.conf`, `keys.txt` |
| H. Battery and power | `BatteryPanel.qml`, `BatteryService.qml`, `PowerService.qml`, `scripts/battery.py`, `tests/test_battery.py` | `Bar.qml` 211-231, `LockScreen.qml` 246-282, `Osd.qml`, `PowerPage.qml`, `arctic_settings.py`, `SearchIndex.js`, `Session.qml` (setting key), `binds.conf`, `keys.txt` |
| I. Media | `MediaService.qml`, `MediaItem.qml`, `MediaPanel.qml` | `Bar.qml` centre, `LockScreen.qml`, `shell.qml`, `binds.conf`, `keys.txt` |
| J. Quick Settings, registry, indicators, display | `QuickSettingsPanel.qml`, `QuickTile.qml`, `Toggle.qml`, `ToggleRegistry.qml`, `ModeIndicators.qml`, `PrivacyService.qml`, `DisplayPanel.qml`, `BrightnessService.qml`, `scripts/brightness.py`, `tests/test_brightness.py` | `shell.qml` (`quick`/`toggle` IPC), `Bar.qml` centre, `arctic-osd`, `Osd.qml`, `binds.conf`, `keys.txt`, `rules.conf` (shield rules), spec (ddcutil) |
| K. Keyboard layout | `KeyboardService.qml`, `KeyboardItem.qml`, `KeyboardPanel.qml`, `scripts/keyboard.py`, `tests/test_keyboard.py` | `Bar.qml` right group, `LockScreen.qml`, `Osd.qml`, `shell.qml` |
| L. Bar keyboard mode and panel keys | — | `Bar.qml`, `BarItem.qml`, `shell.qml` (`bar` IPC), `binds.conf`, `keys.txt`, `dotfiles/README.md` |
| M. Packaging, CI, docs | new CI job `shell-headless` | spec, `config.kiwi` comment, `install.sh`, `ci.yml`, `arctic-shell-ipc` usage, `shell/README.md`, `docs/BUILD-SPEC.md`, `docs/PLAN.md`, `docs/wiki/*` (13) |

Each package lands with its tests and a green CI; the merge to main is one pull request (D10).

### 15. Open issues

- `shell.json` key spelling for new shell settings (`batteryWarnings` like `frame`, or
  snake_case like the helpers' JSON): pick one in review; Settings writes what the shell reads.
- If a later release adopts Omarchy's Super+C/V/X/A clipboard keys (a missed-gap note), Super+A
  collides with Quick Settings.
- mako moving to `Recommends` means a person who removes it has no notifications in the waybar
  session; the release notes say so.
- Toast shielding: toasts are not shielded in screen captures (they would show as black boxes in
  recordings); only the polkit, pairing and Wi-Fi share layers are. Revisit if people ask.
- Whether the tray should get Omarchy's hidden drawer later (P3 in the research; not planned).
- Night light, keep awake, screen recording and game mode tiles depend on their sections adding
  `Toggle` entries; Quick Settings ships without them if those sections land later.
- The hands-on list in 12.4 must be run on at least one Intel and one AMD laptop and one
  desktop with a DDC monitor before the pull request is merged.

### 16. Deferred, with reasons

- **Packaging Quickshell 0.3.1 (`quickshell-031`)**, per D5. Documented follow-up: a
  `packaging/quickshell.spec` from the v0.3.1 tag like `packaging/mangowm.spec`, with
  `-DCRASH_HANDLER=OFF` or a bundled cpptrace (`-DVENDOR_CPPTRACE=ON`, sources vendored because
  FetchContent needs the network; cpptrace is not in F44), BuildRequires vulkan-headers, glib2,
  polkit; `Requires: quickshell >= 0.3.1` in arctic-shell, arctic-settings, arctic-installer
  (243, 263, 292). What it would change here: `Quickshell.Networking` (with `connectWithPsk`,
  `connectionFailed`, wired devices) could replace parts of `network.py`; the Wi-Fi-disappears
  crash, the PipeWire default-node crashes, the `PwNodePeakMonitor` crash, DBusMenu update drops
  and the NotificationClosed ordering are fixed; the mic meter can appear. Until then this
  section uses only snapshot APIs and the workarounds named in 2.6.
- **A NetworkManager secret agent in the shell**: NetworkManager-initiated prompts are rare
  (changed passwords, VPN re-auth); the `needs_secrets` toast covers the common case, and
  SAML/OpenConnect VPN auth dialogs need their own binaries anyway. Revisit with Quickshell 0.3.x
  or if 12.4 #6 shows hangs.
- **Per-app output routing** (`pw-metadata target.object`): the API on WirePlumber 0.5 is
  unverified and routing needs a design of its own.
- **Live microphone level meter**: `PwNodePeakMonitor` crashes on mismatched channels in the F44
  snapshot; gated on `Quickshell.hasVersion(0, 3)`.
- **Editing the Quick Settings tile set** (DMS/macOS style): not in the gap proposal; the order is
  fixed and tiles hide when unavailable.
- **Omarchy's Super+Ctrl+1…9 "bar panel N"**: positions change with the live tag, tray icons,
  battery and media items, so numbered keys would open different menus on different machines; the
  named keys cover every menu.
- **DNS provider picker and Wi-Fi band pinning** (Omarchy setup menu): P3 in the research.
- **Tray drawer**: P3 in the research.
- **bluez-tools `bt-agent` as a no-UI fallback**: not needed; the waybar session keeps blueman's
  agent.
