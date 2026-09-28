# Arctic Linux 0.3 — System, power, hardware and network features

Part of the [0.3 plan](../PLAN-0.3.md).

This section covers request #6 ("research all useful desktop and omarchy features we need to add")
for the system area: power, displays, session services, updates, hardware and the local
network. It ships in Arctic Linux 0.3.0 (D1) and follows D8 (every P0 and P1 item, the P2 items
unless one is marked deferred with its reason, every correction in `gap-verification.json`), D9
(colours only from tokens, amber only for "here", new icons in the `design-data.js` style) and D7
(every new key is checked against every existing bind and against the Alt+Shift layout toggle).

Gap items covered here:

| Priority | Items |
|---|---|
| P0 | `night-light`, `keep-awake`, `low-battery-warnings` (daemon and logic; the menu and notification UI are in the bar-menus section, 5.6) |
| P1 | `battery-health-limit` (backend), `xdg-autostart`, `printing`, `removable-drives`, `date-time-region`, `unified-updates` (system parts; the Get apps parts are in the Get apps section, 6.14) |
| P1, missed gaps | input methods (fcitx5) for Chinese, Japanese and Korean; laptop lid close and clamshell |
| P2 | `power-menu-extras`, `display-mode-mirror`, `idle-dim`, `game-mode`, `system-tools`, `firewall-ssh`, `share-localsend-kdeconnect`, `snapshots-ui`, `fedora-upgrade-whats-new`, `users-sign-in` |
| P2, missed gaps | scanning; phone, camera and network-share access in the file manager (gvfs backends); hybrid GPU launch; SSH agent (gcr-ssh-agent); lighter effects on virtual machines and software rendering; app idle inhibitors (the `Inhibit=none` portal) |
| Decision only | hibernation (not set up in 0.3.0; 4.7 says why) |

Every correction from `gap-verification.json` for these items is applied; 2.3 lists them.
Facts marked ✅ were checked on 2026-09-28 in the repository at `51cce98` (Arctic Linux 0.2.1),
in Mango 0.17.3's source, in Quickshell's source at Fedora's snapshot commit `dacfa9d`, or in
Fedora 44's package metadata (mdapi). 🔍 marks a claim that still needs a hands-on check; each
one names what proves it (collected in 16.2).

---

### 1. What ships

| Piece | Where | Replaces |
|---|---|---|
| Night light: off / sunset to sunrise / custom hours / always, warmth 3000–5500 K, `Super + Ctrl + N`, Quick Settings tile, bar indicator | `arctic-nightlight` (daemon supervising wlsunset), `NightLightService.qml`, Settings → Displays | nothing |
| Keep awake: 30 min / 1 h / 2 h / until turned off, `Super + Ctrl + I`, tile, indicator; apps that ask to keep the screen on (video calls, presentations) are honoured | `IdleService.qml` (Quickshell `IdleInhibitor`), `arctic-awake`, `scripts/screensaver-bridge.py` | nothing |
| Idle: dim with "Locking in 30 s" before the lock, screen off after locking, separate battery times | `IdlePipeline.qml`, `IdleDim.qml`, `IdlePlan.js` (Quickshell `IdleMonitor`) | swayidle as the only idle owner (it stays as a backstop and in the waybar session) |
| Laptop lid: suspend, lock and turn the screen off, or keep running; clamshell with another screen | `switchbind=fold/unfold` → `arctic-display lid`, `arctic-session lid` (logind inhibitor), Settings → Power and lock | the read-only lid row |
| Display mode: laptop only / duplicate / extend / other screen only, `Super + P` and the display key | `arctic-display`, `DisplayModePanel.qml`, wl-mirror | nothing |
| Power menu: install warning, windows closed gracefully, Hibernate when available, Restart into firmware setup | `PowerMenu.qml`, `arctic-power prepare` | the unchecked actions |
| Low battery: the waybar-session watcher, the critical action spelled out, hibernation decision | `arctic-session battery`, `battery.py watch --notify` | nothing |
| Lighter effects in virtual machines and without a GPU driver; game mode | `arctic-effects`, `~/.config/arctic/effects.conf`, Settings → Windows | nothing |
| Run an app on the discrete GPU (`Shift + Enter` in the launcher; `PrefersNonDefaultGPU` honoured) | `arctic-gpu`, `GpuService.qml`, switcheroo-control | environment variables typed by hand |
| Apps' "Start on login" works (XDG autostart) | `mango-session.target.d/arctic-autostart.conf`, Settings → Startup apps | nothing (`~/.config/autostart` was ignored) |
| Date and time: time zone search, automatic time, 24/12-hour clock, date on the bar, first day of the week, system language | Settings → Date and time (new page) | installer-only settings |
| Users and sign-in: picture, name, password, disk passphrase, fingerprint, security key | Settings → Users and sign-in (new page), `pam/arctic-lock-fingerprint` | `~/.face` by hand |
| Input methods (Fcitx 5) for Chinese, Japanese and Korean | Settings → Keyboard and mouse | nothing |
| SSH keys unlocked once per session (gcr-ssh-agent) | preset, `/etc/profile.d/arctic-ssh-agent.sh` | no agent |
| Activity (`Ctrl + Shift + Esc`), restart sound / Wi-Fi / Bluetooth / the shell | `arctic-restart`, Settings → About | nothing |
| Flathub apps updated daily (system and per-user installations); firmware updates listed and installed | `arctic-flatpak-update.{service,timer}` (system and user), `arctic-update flatpak`, Settings → Updates | "run `flatpak update` yourself" |
| Snapshots: list, undo an update, take one now | Settings → Updates, `arctic-system-helper` | the snapper CLI |
| Next Fedora release offered in Settings; "What's new" after an Arctic update | `arctic-update upgrade`, `WhatsNew.qml` | the wiki |
| Printing and scanning | CUPS, ipp-usb, avahi, sane-airscan, simple-scan, Settings → Printers and scanners (new page) | nothing (ghostscript was even excluded) |
| USB drives and SD cards mount and can be ejected from the bar; phones, cameras and network shares in Files | `scripts/drives.py` (Gio), `DrivesService.qml`, `DrivesItem.qml`, `DrivesPanel.qml`, gvfs backends | Thunar mounting on click |
| Firewall status and allows, remote login (SSH), computer name | Settings → Sharing (new page), `arctic-system-helper` | `firewall-cmd` by hand |
| Share menu (LocalSend), KDE Connect | `arctic-share`, `SharePanel.qml` (`Super + Ctrl + S`), Thunar action, catalog module `kdeconnect` | nothing |

Not in 0.3.0, each with its reason in 17: setting up hibernation, booting into a snapshot, a
per-user language, a print-job indicator on the bar, Nix profile upgrades, the installer
pre-ticking an input method by language, a suspend on/off switch.

---

### 2. Current state (0.2.1)

#### 2.1 Session services

- `dotfiles/.config/mango/arctic/autostart.conf:10-16` runs `arctic-theme apply`, then
  `arctic-session shell|mako|nm-applet|clipboard|idle` and `arctic-welcome` as `exec-once` lines.
- `dotfiles/.local/bin/arctic-session:21-66` is one `case` over those services. `run_once`
  (14-19) skips a service whose process name is already running.
- Idle is swayidle only: `arctic-session idle` (40-64) reads `~/.config/arctic/idle.conf`
  (`lock_after=`, `suspend_after=`, seconds, 0 = never), runs `swayidle -w timeout <lock>
  arctic-lock timeout <suspend> 'systemctl suspend' before-sleep arctic-lock`, and exits in the
  live session (44). There is no dim step, no battery/AC split and no keep-awake toggle.
- Mango starts `mango-session.target` itself after `systemctl --user import-environment
  DISPLAY WAYLAND_DISPLAY XDG_CURRENT_DESKTOP XDG_SESSION_TYPE XCURSOR_THEME XCURSOR_SIZE
  MANGO_INSTANCE_SIGNATURE` (Mango `src/main.c:235-277`) ✅, and sets `XDG_CURRENT_DESKTOP=mango`
  (`main.c:370`) ✅. `mango-session.target` binds `graphical-session.target`
  (`assets/mango-session.target`, packaged by `packaging/mangowm.spec:84`) ✅.
- `~/.config/autostart` is not read: `settings/pages/StartupPage.qml:1-3`, `docs/PLAN.md:328`.
- Mango's `env=` expands only `~/` (`src/config/parse_config.c:1909-1960`) ✅, so a
  `$XDG_RUNTIME_DIR` path can't be set there; `/etc/profile.d` scripts reach the session
  (`packaging/desktop/arctic-graphics.sh` relies on it).
- `dotfiles/.config/mango/config.conf:22-32` sources `arctic/look.conf`, the theme colours,
  `arctic/input.conf`, `/etc/arctic/mango/keyboard.conf`, `arctic/{apps,binds,rules,autostart}.conf`,
  `~/.config/arctic/motion.conf`, `settings.conf`, `user.conf`, in that order. Later files win for
  options; for binds the first one wins (13-19).

#### 2.2 Power, displays and hardware

- Power menu: `shell/PowerMenu.qml:14-23` lists Settings, Lock, Log out, Suspend, Restart, Shut
  down (Settings, Restart, Shut down in the live session); `run()` (35-40) calls
  `arctic-power <id>`, which acts at once (`dotfiles/.local/bin/arctic-power:12-21`); the fuzzel
  fallback is 24-37. No checks, no hibernate, no firmware setup.
- Lid: `settings/pages/PowerPage.qml:89-97` is read-only text ("decided by systemd-logind").
  Logind's defaults apply: `HandleLidSwitch=suspend`, `HandleLidSwitchDocked=ignore`.
  `binds.conf` has no `switchbind` lines. Mango 0.17.3 has `switchbind=fold|unfold,…`
  (`src/config/parse_config.c:2293`, `docs/bindings/mouse-gestures.md:109-133`) ✅; its handler
  (`src/input/switch.c:10-31`) does not check the switch type, so a 2-in-1's tablet-mode switch
  fires the same bindings ✅, and only the first `switchbind` per fold state is used
  (`same_switchbind_key`, `parse_config.c:2525`) ✅.
- Monitors: Mango has `disable_monitor`, `enable_monitor`, `toggle_monitor`, `sleep_monitor`,
  `wakeup_monitor` (`docs/bindings/keys.md:209-214`) ✅. `sleep_monitor` acts on the first monitor
  that matches its spec and keeps the output in the layout (`src/dispatch/bind.c:2452-2478`,
  `src/manage/monitor.c:1021`) ✅; a config reload skips disabled outputs
  (`reapply_monitor_rules`, `parse_config.c:4480-4482`) ✅, so a monitor turned off at run time
  stays off across `reload_config`. There is no mirroring.
- `mmsg get all-monitors` answers `{"monitors":[{"name","active","x","y","width","height","scale",…}]}`
  and `mmsg get all-clients` `{"clients":[{"id","pid","appid","title",…}]}` (`src/ipc/ipc.c:559-620,
  725-739`) ✅. `mmsg dispatch <fn>,<args> client,<id>` targets one window (`docs/ipc.md:77`) ✅;
  `killclient` without `force` asks the window to close (`keys.md:100`) ✅.
- `setoption key,value` changes an option until the next reload (`keys.md:208`, `bind.c:2204-2209`) ✅.
  Every Settings save runs `reload_config` (`settings/scripts/arctic_settings.py:628-633`), so a
  `setoption` change would be undone by the next Settings change.
- Battery: `shell/Bar.qml:211-231` only turns the icon red at ≤ 10 %; the bar-menus section adds
  `BatteryService.qml` and `scripts/battery.py`.
- No wlsunset, gammastep, udiskie, CUPS, fcitx, switcheroo-control, gcr or fprintd in any
  Requires (`packaging/arctic-linux.spec:157-220, 402-482`). `iso/kiwi/config.kiwi:183` ignores
  ghostscript. The ISO has Fedora's `@core` (`config.kiwi:60`), whose defaults include fwupd,
  firewalld and zram-generator-defaults; openssh-server is mandatory ✅ (comps-f44).
- Graphics: `packaging/desktop/arctic-graphics.sh` sets `WLR_RENDERER_ALLOW_SOFTWARE=1` and,
  in VMs, `WLR_NO_HARDWARE_CURSORS=1`. Hybrid laptops are documented only with environment
  variables (`docs/wiki/Drivers.md:145-156`).
- Swap: zram only (`docs/wiki/Release-Notes.md:262`); the installer writes no swapfile and no
  `resume=` (no `mkswap|swapfile|resume=` in `internal/`) ✅.

#### 2.3 Corrections applied from the research

- `night-light`: wlsunset's `-d` only applies to manual `-S`/`-s` times; temperature can't change
  at run time; `SIGUSR1` cycles modes whose current state can't be read. The daemon restarts
  wlsunset with new arguments instead of signalling it, and uses `-d` only for custom hours (5.1).
- `keep-awake`: Mango counts an inhibitor whose surface's scene node is enabled, not whether it is
  covered (`src/manage/misc.c:333-361`) ✅, so an inhibitor on the bar works under a fullscreen
  window. `Super + Ctrl + I` is free.
- `low-battery-warnings`: with UPower 1.91.4, `CriticalPowerAction=Auto` means logind `Sleep()`,
  which follows `SleepOperation=` (`suspend-then-hibernate suspend hibernate`); on Arctic that
  resolves to suspend. The critical text names the resolved action, never "hibernate" by default.
- `battery-health-limit`: the limit applied is UPower's `ChargeEndThreshold`. The polkit question
  is settled: `org.freedesktop.UPower.enable-charging-limit` is `allow_active=yes` in UPower
  1.91.4 (`policy/org.freedesktop.upower.policy.in:23-28`) ✅, so no password.
- `xdg-autostart`: `xdg-desktop-autostart.target` has `RefuseManualStart=yes`; a `Wants=` drop-in
  on `mango-session.target` pulls it in (6.1). `XDG_CURRENT_DESKTOP` is `mango` ✅.
- `printing`: dropping the ghostscript ignore is required (libcupsfilters requires ghostscript);
  cups-pk-helper is added; the security argument for leaving cups-browsed out is not Omarchy's
  FAQ (it says discovery is off "while it's reworked"). Arctic leaves cups-browsed out because
  CUPS 2.4 creates temporary queues for driverless printers on its own (8.1).
- `removable-drives`: Omarchy runs udiskie with `--no-notify`. Arctic uses neither udiskie nor its
  notifications; the shell watches Gio's volume monitor (8.2).
- `unified-updates`: fwupd and firewalld are `@core` defaults, so almost certainly in the ISO;
  `fwupdmgr` authorises through polkit itself, so no `pkexec fwupdmgr`.
- `display-mode-mirror`: Mango has lid bindings (`switchbind`); no logind `LidClosed` watcher is
  needed for clamshell. `Super + P` is free.
- `power-menu-extras`: Hibernate will rarely show because Arctic sets up no disk swap (4.7). The
  syntax is `mmsg dispatch killclient client,<id>`. Omarchy schedules the restart and then closes
  windows; Arctic closes windows first, waits up to 5 s, and asks when some stay open (4.6).
- `idle-dim`: `IdleMonitor` is in Fedora's snapshot (`src/wayland/idle_notify/monitor.hpp` at
  `dacfa9d`, with `enabled`, `timeout`, `respectInhibitors`, `isIdle`) ✅; the dependency on
  Quickshell 0.3.1 is dropped.
- `firewall-ssh`: firewalld is in `@core` and enabled by `packaging/release/90-default.preset:70`;
  `80-arctic.preset:41-45` disables sshd on purpose. Arctic's `os-release` has no `VARIANT_ID`,
  so firewalld's `%posttrans` picks `firewalld-standard.conf` (`DefaultZone=public`) and the
  server polkit policy (`auth_admin_keep` even for reading the permanent config) ✅ (Fedora
  `firewalld.spec`, f44). The `public` zone allows `ssh` and `dhcpv6-client` only ✅. The service
  file is `kdeconnect` ✅; LocalSend has none (port 53317).
- `share-localsend-kdeconnect`: Omarchy sends with `localsend --headless send`; Arctic's LocalSend
  is the Flathub app, so the headless path is 🔍 and has a fallback (8.4).
- `snapshots-ui`: `--jsonout` exists in snapper 0.13.0; the pre-upgrade snapshot is automatic
  (`packaging/updates/snapper.actions`). Snapshots stay root's: the installer sets no
  `ALLOW_GROUPS` on purpose (`internal/installer/installer.go:1573-1578`), so Settings goes
  through a polkit helper.
- `fedora-upgrade-whats-new`: `arctic-update-helper` treats any transaction whose
  `target_releasever` differs from `system_releasever` as someone else's
  (`owner()`, `packaging/updates/arctic-update-helper:195-204`; `OUR_COMMANDS` at 56); the upgrade flow extends the helper (7.3).
- `users-sign-in`: the package is `pam-u2f` (hyphen) ✅.
- `system-tools`: `Ctrl + Shift + Esc` is free unless the layout switch is `grp:ctrl_shift_toggle`
  (9.1).
- Missed gaps: fcitx5 (6.4), hibernation (4.7), hybrid GPU (5.4), scanning (8.1), gvfs backends
  (8.2), SSH agent (6.5), lighter effects in VMs (5.3), lid close (4.5), the `Inhibit=none`
  portal (4.1.4).

---

### 3. Shared design

#### 3.1 Where the code lives

- **Helpers** that keybinds, the shell, Settings and the waybar session all use go in
  `dotfiles/.local/bin/arctic-*` (installed to `/usr/bin` by arctic-desktop-config, spec:642):
  `arctic-nightlight`, `arctic-awake`, `arctic-display`, `arctic-effects`, `arctic-gpu`,
  `arctic-share`, `arctic-restart`. Python helpers use the standard library only.
- **Shell-only helpers** go in `shell/scripts/`: `drives.py`, `screensaver-bridge.py`.
- **Settings backend**: a new module `settings/scripts/arctic_system.py` holds the new commands.
  `arctic_settings.py` imports it (its folder is `sys.path[0]`) and merges
  `arctic_system.COMMANDS` into `COMMANDS` (2546-2562) and `arctic_system.WRITERS` into `WRITERS`
  (2567-2569). It reuses `run`, `which`, `atomic_write`, `backup`, `Failure`, `Paths` and
  `shell_script` from `arctic_settings`. This keeps the 2592-line file from doubling and gives the
  new code its own test file.
- **Root**: one helper, `packaging/system/arctic-system-helper` →
  `/usr/libexec/arctic/arctic-system-helper`, run with `pkexec` (3.3). Everything else runs as the
  user and asks through the owning service's polkit action (timedated, hostnamed, AccountsService,
  fwupd, systemd, NetworkManager), whose prompt is the shell's `PolkitDialog`.

#### 3.2 Output contract

The same contract as the bar-menus helpers and Settings' `Backend.qml`: a one-shot command prints
exactly one JSON line, `{"ok":true,…}` (exit 0) or `{"ok":false,"error":"<a sentence>","code":"<code>"}`
(exit 1); a usage error exits 2; keys are snake_case; long-running `watch`/`daemon` modes print one
JSON object per line with a `type`. Bash helpers take `--json` for the machine form and print
sentences otherwise.

#### 3.3 The root helper and its polkit action

`packaging/polkit/org.arcticlinux.system.policy` (arctic-desktop-config), modelled on
`packaging/polkit/org.arcticlinux.pkexec.dnf.policy`:

```xml
<action id="org.arcticlinux.system">
  <description>Change system settings</description>
  <message>Enter your password to change system settings</message>
  <icon_name>preferences-system</icon_name>
  <defaults>
    <allow_any>auth_admin</allow_any>
    <allow_inactive>auth_admin</allow_inactive>
    <allow_active>auth_admin_keep</allow_active>
  </defaults>
  <annotate key="org.freedesktop.policykit.exec.path">/usr/libexec/arctic/arctic-system-helper</annotate>
</action>
```

`arctic-system-helper VERB [ARGS…]` (python3, standard library, runs as root through pkexec):

| Verb | Does | Output |
|---|---|---|
| `snapshots` | `snapper --no-dbus --jsonout -c root list` → pairs and singles (7.2) | `{"ok":true,"config":true,"pairs":[…],"singles":[…]}` |
| `snapshot-create TEXT` | `snapper --no-dbus -c root create -t single -c number -p -d TEXT` (TEXT ≤ 80 printable characters) | `{"ok":true,"number":44}` |
| `snapshot-undo PRE POST` | checks that PRE/POST is a listed pair, then `snapper --no-dbus -c root undochange PRE..POST`; run in a terminal (3.4), prints snapper's lines and a last sentence | text |
| `firewall-allow NAME on\|off` | NAME ∈ `localsend` (53317/tcp, 53317/udp), `kdeconnect` (service), `mdns` (service), `ssh` (service); `firewall-cmd --zone=<default> --add-…` and the same with `--permanent` | `{"ok":true,"allowed":true}` |
| `ssh on\|off` | `systemctl enable --now sshd.service` / `disable --now sshd.service sshd.socket` | `{"ok":true,"enabled":true,"active":true}` |
| `ssh-password on\|off` | removes / writes `/etc/ssh/sshd_config.d/40-arctic-keys-only.conf` (`PasswordAuthentication no`, `KbdInteractiveAuthentication no`), `sshd -t`, `systemctl try-reload-or-restart sshd.service` | `{"ok":true,"password_login":false}` |
| `fingerprint-login on\|off` | `authselect enable-feature with-fingerprint` / `disable-feature` | `{"ok":true}` |
| `security-key-login on\|off` | `authselect enable-feature with-pam-u2f` / `disable-feature` | `{"ok":true}` |

Rules: arguments are checked against fixed tables before anything runs; commands are argv
lists, never a shell; each verb logs one line with `logger -t arctic-system-helper`; nothing is
read from the caller's environment except `PKEXEC_UID` (to name the user in the log). A failure
answers with a sentence ("The firewall isn't running, so there's nothing to allow."). The
`auth_admin_keep` grant covers the next few minutes, so turning on SSH and then its firewall
allow asks once.

Settings reaches it with `pkexec /usr/libexec/arctic/arctic-system-helper …` from
`arctic_system.py` (`HELPER` constant; `ARCTIC_SYSTEM_HELPER` overrides it in tests).

#### 3.4 Long or interactive jobs open a terminal window

Firmware updates, undoing a snapshot, the Fedora upgrade download, `passwd`, the disk
passphrase, fingerprint enrolment and registering a security key take a while or ask questions.
They run in the user's terminal through the Get apps section's `arctic-open terminal --app-id ID
[--hold] -e …` (its 6.11), with ids under `org.arcticlinux.TerminalApp.Float.` so its float rule
applies (1000×640, centred):

| Job | Command |
|---|---|
| Firmware | `arctic-open terminal --app-id org.arcticlinux.TerminalApp.Float.Firmware --hold -e fwupdmgr update` |
| Undo an update | `… Float.Snapshot --hold -e pkexec /usr/libexec/arctic/arctic-system-helper snapshot-undo 41 42` |
| Fedora upgrade | `… Float.Upgrade --hold -e arctic-update upgrade download` |
| Password | `… Float.Password --hold -e passwd` |
| Disk passphrase | `… Float.Disk --hold -e pkexec /usr/sbin/cryptsetup luksChangeKey /dev/disk/by-uuid/<UUID>` |
| Fingerprint | `… Float.Fingerprint --hold -e fprintd-enroll -f right-index-finger` |
| Security key | `… Float.SecurityKey --hold -e sh -c 'mkdir -p ~/.config/Yubico && pamu2fcfg >> ~/.config/Yubico/u2f_keys'` |
| Input method install | `… Float.Install --hold -e pkexec /usr/bin/dnf5 install -y fcitx5 …` (6.4) |

The Settings row that starts one says so ("Opens a terminal window: it asks for your current
password, then the new one twice.").

#### 3.5 Shell integration

- **Toggle registry** (bar-menus section 5.11, `shell/ToggleRegistry.qml`): this section adds
  three `Toggle` entries. Tiles, `arctic-shell-ipc toggle set <key>` and mode indicators come
  with them.

| key | label | icon | active when | toggle does | page | indicator |
|---|---|---|---|---|---|---|
| `nightlight` | Night light | `night-light` | `NightLightService.active` | `arctic-nightlight toggle` | `nightlight` | yes |
| `awake` | Keep awake | `cup` | `IdleService.active` | `IdleService.toggle()` | `awake` | yes |
| `gamemode` | Game mode | `gamepad` | `EffectsService.game` | `arctic-effects game toggle` | — | yes |

  `detail`: "On until 06:42" / "Starts at 19:05"; "Until 15:30" / "Until you turn it off";
  "Animations and gaps off".
- **Bar menus** (the bar-menus section's `BarMenu.qml` host and toolkit): new panels
  `displaymode` (5.2), `drives` (8.2), `share` (8.4), and Quick Settings sub-pages `nightlight`
  (5.1) and `awake` (4.1). They use `MenuList`, `MenuRow`, `MenuSwitchRow`, `MenuSlider`,
  `MenuSection` and `MenuPage` as defined there; nothing here draws its own rows.
- **OSD**: a short message pill (icon + text), e.g. "Night light on until 06:42". If the
  osd-kinds work has not added it, this section adds `Osd.showMessage(icon, text)` to
  `shell/Osd.qml` (the volume pill's frame, 20 px icon, 15 px text, no bar) and IPC
  `osd message(icon: string, text: string)`. Helpers call `arctic-shell-ipc osd message …` and
  fall back to `notify-send -a "Arctic Linux" -t 2000`.
- **IPC targets** added to `shell/shell.qml` (typed parameters; no function named `show` or
  `list`, `shell.qml:127`):

| Target | Functions |
|---|---|
| `idle` | `toggle()`, `on(minutes: int)` (0 = until turned off), `off()`, `status(): string` (JSON), `inhibit(cookie: int, app: string, reason: string)`, `uninhibit(cookie: int)` |
| `nightlight` | `toggle()`, `refresh()` |
| `display` | `menu()` (open, or move to the next row when open), `mode(name: string)` |
| `drives` | `open()`, `eject(id: string)` |
| `share` | `menu()` |
| `whatsnew` | `open()` |

- **Mode indicators**: night light, keep awake and game mode show as 16 px `inkMuted` glyphs left
  of the clock (bar-menus 5.12). None is amber (D9).

#### 3.6 Settings pages

New pages (`settings/pages/*.qml`, `settings/pages/qmldir`, `settings/SearchIndex.js` `PAGES`).
`arctic-settings` accepts `^[a-z]+$` page ids (`dotfiles/.local/bin/arctic-settings:33`), so
the ids have no hyphens.

| id | Title | Icon | Goes after | Section |
|---|---|---|---|---|
| `sharing` | Sharing | `send` (in Settings' design icons) | `network` | 8.3 |
| `printers` | Printers and scanners | `printer` (new, `SettingsIcons.js` `EXTRA`) | `sound` | 8.1 |
| `datetime` | Date and time | `clock` | `power` | 6.2 |
| `users` | Users and sign-in | `user` | `datetime` | 6.3 |

Changed pages: Displays (night light), Power and lock (idle times, dim, screen off, lid),
Windows (effects, game mode), Keyboard and mouse (input method), Default apps (drives), Startup
apps (XDG entries), Updates (Flathub, firmware, snapshots, next Fedora), About (computer name,
troubleshooting). The Users page and the SSH group are hidden in the live session.

The search `words` are listed per item below; `settings/SearchIndex.js` gets one
`PAGES` entry per new page and every `ENTRIES` row named in 4–8.

#### 3.7 Files

| File | Written by | Read by |
|---|---|---|
| `~/.config/arctic/nightlight.conf` | `arctic-nightlight set` (Settings) | the night-light daemon |
| `$XDG_RUNTIME_DIR/arctic/nightlight.json` | the daemon | `NightLightService.qml`, `arctic-nightlight status` |
| `$XDG_RUNTIME_DIR/arctic/keep-awake.json` | `IdleService.qml` | the shell after a restart |
| `~/.config/arctic/idle.conf` (+ `lock_after_battery`, `suspend_after_battery`, `dim_before_lock`, `screen_off_after`) | Settings `idle-set` | `IdlePipeline.qml`, `arctic-session idle` |
| `~/.config/arctic/lid.conf` (`when_closed=suspend\|lock\|screen-off`) | Settings `lid-set` | `arctic-display lid`, `arctic-session lid` |
| `$XDG_RUNTIME_DIR/arctic/display.json` | `arctic-display` | `arctic-display`, `DisplayModePanel.qml` |
| `~/.config/arctic/effects.json`, `~/.config/arctic/effects.conf` | `arctic-effects` | Mango (`config.conf`), `EffectsService.qml`, Settings |
| `~/.config/arctic/shell.json` (+ `clock_format`, `clock_date`, `week_start`, `automount`, `automount_notify`, `lock_fingerprint`) | Settings `shell-set` (bar-menus 9.4) | `Session.qml` |
| `~/.config/autostart/<id>.desktop` | Settings `startup-xdg-set`, apps | systemd-xdg-autostart-generator |
| `~/.local/state/arctic/flatpak-update.json` | `arctic-update flatpak --user` | Settings |
| `~/.local/state/arctic/whats-new-seen` | `WhatsNew.qml` | `WhatsNew.qml` |
| `/etc/ssh/sshd_config.d/40-arctic-keys-only.conf` | the root helper | sshd |

The `shell.json` key spelling follows whatever the bar-menus review picks for `battery_warnings`
(its open issue 15); this section writes snake_case keys.

#### 3.8 New icons (D9)

New glyphs go into the bar-menus section's `shell/assets/icons-extra.js` (`EXTRA`), on the
24-unit grid, 1.75 stroke, round caps and joins, no fills except small `currentColor` dots.
Settings gets exact copies in `settings/assets/SettingsIcons.js` `EXTRA` where a page uses them,
and the copy test (bar-menus 12.2) covers them.

| Name | Drawing | Used by |
|---|---|---|
| `night-light` | the existing `moon` crescent plus two short rays at 18,5 and 20,9 | toggle, indicator, Displays |
| `cup` | mug 5→16 × 9→19 (radius 2), handle arc on the right, two steam lines above | keep awake |
| `printer` | paper rect 7→17 × 3→8, body 3→21 × 8→17 (radius 2), output rect 7→17 × 14→21 | Printers page, Settings rail |
| `scanner` | flat body 3→21 × 12→18 (radius 2), lid line at y 9, light slit dot | Printers page |
| `eject` | triangle 12,5 / 19,13 / 5,13 and a bar 5→19 at y 17 | drives |
| `screens` | two overlapping `display` rects offset by 4 | display mode |
| `fingerprint` | three concentric open arcs and a centre stroke | Users page |
| `history` | `clock` with a counter-clockwise arrow head at 4,8 | snapshots |
| `share` | three dots (r 2) joined by two lines, the usual share glyph | share menu |

Existing glyphs cover the rest: `gamepad`, `usb`, `disk`, `shield-check`, `shield-lock`, `cpu`,
`language`, `user`, `clock`, `terminal`, `refresh`, `restart`, `sleep`, `power`, `lock`, and the
bar-menus additions `phone`, `laptop`, `display`, `key`, `sun`, `dots`, `gauge`.

#### 3.9 Live session and the waybar fallback

| Feature | Quickshell session | Waybar session (`ARCTIC_SHELL=waybar`) | Live USB |
|---|---|---|---|
| Night light | yes | yes (daemon is shell-independent) | yes |
| Keep awake | shell inhibitor | `arctic-awake` pauses swayidle | nothing locks anyway |
| Idle dim, battery times | yes | swayidle (plugged-in times) | off |
| Lid | yes | yes (bind + helper) | logind default |
| Display mode | `Super + P` menu | `arctic-display menu` (fuzzel) | yes |
| Drives on the bar, automount | yes | Thunar mounts on click (as today) | yes |
| Share menu | panel | `arctic-share menu` (fuzzel) | yes |
| Power menu checks | yes | fuzzel asks | Restart / Shut down only |
| Low-battery notifications | the shell (bar-menus 5.6) | `arctic-session battery` | yes |
| Settings pages | yes | yes | Users and SSH hidden; Updates as today |

---

### 4. Power

#### 4.1 Keep awake (P0, `keep-awake`)

**4.1.1 Service.** New singleton `shell/IdleService.qml` (registered in `shell/qmldir`):

| Property / function | Meaning |
|---|---|
| `userUntil` | `null` (off), `0` (until turned off) or an epoch in ms |
| `apps` | map cookie → `{app, reason, since}` from the ScreenSaver bridge (4.1.4) |
| `active` | `userUntil !== null` |
| `inhibiting` | `active \|\| Object.keys(apps).length > 0` |
| `detail` | "Until 15:30", "Until you turn it off", "Zoom is keeping the screen on" |
| `set(minutes)` | 0 = until turned off; writes `$XDG_RUNTIME_DIR/arctic/keep-awake.json`: `{"until":"2026-09-28T15:30:00+03:00"}`, or `{"until":null}` for "until turned off"; no file = off |
| `toggle()` | off → on with the last duration used (default: until turned off); on → off |
| `off()` | clears the file |

- The inhibitor: `Bar.qml` gets `IdleInhibitor { window: bar; enabled: IdleService.inhibiting &&
  bar.screen === Quickshell.screens[0] }` (`Quickshell.Wayland`, present at `dacfa9d`:
  `src/wayland/idle_inhibit/inhibitor.hpp:27-37`, `enabled` and `window`) ✅. If the first screen
  goes away (clamshell, 4.5), the binding moves the inhibitor to the next bar.
- A `Timer` ends a timed keep-awake at `userUntil`; at start the service reads the runtime file,
  so `arctic-shell --restart` keeps it, and logging out ends it.
- `look.conf` gains `idleinhibit_when_fullscreen=1` after the "Focus behaviour" block (85-88), so
  a focused fullscreen window (video, a game) keeps the screen on even without asking
  (`docs/configuration/miscellaneous.md:55`) ✅. `settings/tests/mango-0.17.3-keys.txt:131` already
  lists the key, so `mango -p` accepts it.

**4.1.2 Where it shows.**
- Tile `awake` (3.5); its chevron opens the Quick Settings sub-page `awake`: a `MenuSection`
  "Keep the screen on" with radio rows "For 30 minutes", "For 1 hour", "For 2 hours", "Until I
  turn it off", then "Turn off" when on. Apps holding it are listed below ("Zoom · Video call").
- Mode indicator: `cup`, tooltip "Staying awake until 15:30 · click to stop" or "Zoom is keeping
  the screen on" (clicking an app-only indicator opens the sub-page instead of stopping it).
- OSD message on every change: `cup` "Staying awake until 15:30" / "Keep awake is off".
- `Super + Ctrl + I` (9.1) → `arctic-awake toggle`.

**4.1.3 `dotfiles/.local/bin/arctic-awake`** (bash) for keys and the waybar session:

```
arctic-awake toggle | on [MINUTES] | off | status [--json]
```

- With the shell: `arctic-shell-ipc idle toggle|on N|off|status`.
- Without it (waybar session): `on` stops swayidle (`pkill -u "$UID" -x swayidle`) and, for a
  duration, starts `setsid -f sh -c 'sleep N; arctic-session idle'` (its PID in
  `$XDG_RUNTIME_DIR/arctic/awake-timer.pid`, killed by `off`); `off` runs `arctic-session idle`.
  `status --json` → `{"ok":true,"active":true,"until":"…"|null,"owner":"shell|swayidle"}`.

**4.1.4 Apps that ask to stay awake** (missed gap: `Inhibit=none` portal). Mango's
`mango-portals.conf` sets `org.freedesktop.impl.portal.Inhibit=none` ✅ (Mango
`assets/mango-portals.conf`), and nothing on the session bus owns `org.freedesktop.ScreenSaver`,
so Chromium, Electron and WebKitGTK apps that keep the screen on through D-Bus (video calls,
presentations, web apps from the engine section) can't.
- New `shell/scripts/screensaver-bridge.py` (python3-dbus + GLib, both added to arctic-shell by
  the bar-menus section): owns `org.freedesktop.ScreenSaver` at `/org/freedesktop/ScreenSaver`
  and `/ScreenSaver`, implements `Inhibit(s app, s reason) → u cookie`, `UnInhibit(u)`,
  `GetActive() → b` (false), `SimulateUserActivity()` (no-op) and `Lock()` (runs `arctic-lock`),
  drops a sender's cookies when its name vanishes (`NameOwnerChanged`), and prints JSON lines
  `{"type":"inhibit","cookie":5,"app":"Zoom","reason":"Video call"}` /
  `{"type":"uninhibit","cookie":5}`. At most 32 cookies per sender; app and reason cut to 64
  characters.
- `IdleService.qml` runs it as a `Process` (restarted with backoff 1, 2, 4 … 60 s) and fills
  `apps`. If another process already owns the name, the bridge exits with
  `{"type":"error","code":"name-taken"}` and the service stops trying.
- `packaging/mangowm.spec` `%install`: after `%meson_install`, `sed -i
  's/^org.freedesktop.impl.portal.Inhibit=none$/org.freedesktop.impl.portal.Inhibit=gtk/'
  %{buildroot}%{_datadir}/xdg-desktop-portal/mango-portals.conf`, so Flatpak apps' Inhibit portal
  calls reach xdg-desktop-portal-gtk, which falls back to `org.freedesktop.ScreenSaver` when
  there's no GNOME session manager 🔍 (16.2 #3). The changelog entry says why.

**4.1.5 Tests.**
- `shell/tests/test_screensaver_bridge.py`: the cookie table (add, remove, vanish, cap, truncation)
  as pure functions; D-Bus is not needed for them.
- `shell/tests/test-idle-service.cjs`: `IdleCore.js` (the pure part of `IdleService`: expiry,
  `detail` text in 24/12-hour clocks, toggle with the last duration).
- `mango -p` in `%check` (spec:886-897) covers `idleinhibit_when_fullscreen=1`.
- Hands-on: 16.2 #1, #2, #3.

#### 4.2 Low and critical battery warnings: the logic (P0, `low-battery-warnings`)

The bar-menus section owns the UI and the helper (`BatteryService.qml`, `scripts/battery.py
status|watch|limit`, its 5.6 and 6.5): `WarningLevel` from UPower's DisplayDevice, the critical
action resolved through `GetCriticalAction()` and logind, one notification per discharge. This
section adds what runs without the shell and fixes the facts the texts rely on.

- **UPower's configuration stays Fedora's**: `PercentageLow=20`, `PercentageCritical=5`,
  `PercentageAction=2`, `CriticalPowerAction=Auto` (UPower 1.91.4) ✅. Arctic ships no
  `/etc/UPower/UPower.conf.d` drop-in. With zram only, logind's `SleepOperation=` resolves `Sleep`
  to plain suspend (4.7), so the critical text reads "Arctic will suspend at 2 %. Plug in to keep
  working." A suspended laptop at 2 % still loses unsaved work when the battery runs out; the FAQ
  says so (13).
- **Waybar session**: `battery.py watch` gains `--notify` (a shared edit to the bar-menus helper):
  on `low` it runs `notify-send -a "Arctic Linux" -i battery-caution -u normal "Battery at 20 %"
  "About 40 minutes left. Plug in soon."`; on `critical` the same with `-u critical` and the
  action sentence; once per discharge; reset when `state` becomes charging. New
  `arctic-session battery` runs `python3 <shell dir>/scripts/battery.py watch --notify` only when
  `shell_session` (bar-menus 6.7) is false and a battery is present (`/sys/class/power_supply/*/type`
  = `Battery` with `scope` not `Device`); in both sessions it also re-applies the charge limit when
  4.3 needs it. `autostart.conf` gets `exec-once=arctic-session battery`.
- **Tests**: `shell/tests/test_battery.py` (bar-menus) gains a `--notify` case: a discharge that
  passes low and critical sends one notification each; repeated `warning_level` lines send
  nothing more; after charging, the next discharge sends one low notification again.

#### 4.3 Battery health and the charge limit: the backend (P1, `battery-health-limit`)

No second implementation: `battery.py status|limit` (bar-menus 6.5) is the backend, and the
Battery panel and Power page rows are there (bar-menus 5.6, 9.4). Facts settled here for it:

- `EnableChargeThreshold(b)` needs `org.freedesktop.UPower.enable-charging-limit`, which is
  `allow_active=yes` ✅, so `battery.py limit on` never prompts. Its 🔍 (bar-menus 2.7, 12.4)
  closes.
- The switch is hidden unless `ChargeThresholdSupported` is true; the label uses
  `ChargeEndThreshold` ("Limit charging to 80 %") and the detail `ChargeStartThreshold` ("Charging
  starts again below 75 %").
- 🔍 whether UPower 1.91.4 re-applies an enabled limit after a reboot (16.2 #6). If it doesn't:
  `battery.py limit on|off` also records `"charge_limit": true|false` in
  `~/.config/arctic/shell.json`, and `arctic-session battery` (4.2) runs `battery.py limit on` at
  login when it is true (in both sessions for this one job).

#### 4.4 Idle: dim before locking, screen off, battery times (P2, `idle-dim`)

**4.4.1 Settings file.** `~/.config/arctic/idle.conf` keeps `lock_after=` and `suspend_after=`
(plugged in) and gains:

```
lock_after_battery=180        # missing: same as lock_after
suspend_after_battery=600     # missing: same as suspend_after
dim_before_lock=1             # 1: dim for 30 s with "Locking in 30 s" first
screen_off_after=60           # seconds after the lock; 0 = leave the screen on
```

Existing files keep working; missing keys mean "same as plugged in", so nothing changes for
anyone until they choose.

**4.4.2 Plan.** New `shell/IdlePlan.js` (pure, Node-tested):
`plan(conf, onBattery) → {dim, lock, screenOff, suspend}` in seconds, `null` for off. `dim` =
`lock − 30` when `dim_before_lock` and `lock ≥ 60`; `screenOff` = `lock + screen_off_after`;
`suspend` is never earlier than `lock` (Settings already refuses that, `arctic_settings.py:2034-2035`).

**4.4.3 Pipeline.** New `shell/IdlePipeline.qml` (a `Scope` instantiated in `shell.qml`):
- `FileView` on `idle.conf` (`watchChanges`), `UPower.onBattery`, `Session.live`.
- Four `IdleMonitor`s (`Quickshell.Wayland`), each `respectInhibitors: true`, `enabled:
  !Session.live && plan.<step> !== null`, `timeout: plan.<step>`:
  - dim → `IdleDim.begin(30)`;
  - lock → `shell.lock()`;
  - screen off (only while `LockScreen.secure`) → `mmsg dispatch sleep_monitor,<name>` for
    every name in `Quickshell.screens` (one call per output: `sleep_monitor` stops at the first
    match);
  - suspend → `systemctl suspend`.
- When a monitor's `isIdle` turns false: `IdleDim.cancel()` and, if screens were put to sleep,
  `mmsg dispatch wakeup_monitor,<name>` for each. Mango doesn't wake them on input by itself
  (`sleep_monitor` sets `only_sleep`, cleared only by `wakeup_monitor`/output power) ✅.
- Keep awake and apps' inhibitors pause every step, because the monitors respect inhibitors ✅.

**4.4.4 The dim layer.** New `shell/IdleDim.qml`: `Variants` over `Quickshell.screens`, a
`PanelWindow` per screen on the Overlay layer, namespace `arctic-idle-dim`, anchored to all
edges, `exclusionMode: Ignore`, `mask: Region {}` (input passes through), transparent. Inside:
a full-size `Rectangle` in `Theme.scrim` whose opacity goes 0 → 1 over 30 s (`Theme.reduceMotion`:
straight to 1), and a centred pill (`surfaceRaised`, `radiusLg`, `space3` padding): `lock` icon,
"Locking in 30 s" (counts down, tabular figures, 15/600 `ink`), "Move the mouse or press a key to
stay" (13 `inkMuted`). `rules.conf:117` adds `idle-dim` to the no-blur/no-shadow/no-animation
namespaces.

**4.4.5 swayidle stays as a backstop.** If the shell dies, nothing would lock an idle session.
`arctic-session idle` keeps swayidle running in both sessions:
- waybar session: as today (plugged-in times);
- Quickshell session (`shell_session` true): `timeout <max(lock_after, lock_after_battery) + 60>
  arctic-lock`, `timeout <max(suspend_after, suspend_after_battery) + 60> 'systemctl suspend'`,
  `before-sleep arctic-lock`. While the shell works it has locked a minute earlier, so the
  backstop's lock is a no-op (`arctic-lock` asks the shell, which is already locked). It is also
  what locks before every suspend (lid, menu, idle).

**4.4.6 Settings → Power and lock.** Group "When you're away" (44-70):
- With a battery: an `ArSegmented` "Plugged in | On battery" above the rows chooses which pair
  the two selects edit; its desc: "On battery, shorter times save power."
- New rows: "Dim the screen before it locks" (`ArToggle`, `power.dim`), "Turn the screen off
  after locking" (`ArSelect`: 30 seconds, 1 minute, 2 minutes, 5 minutes, Never; `power.screenoff`).
- `arctic_settings.py`: `read_idle` (2002-2011) reads the new keys; `cmd_idle` (2019-2023) adds
  `lock_battery`, `suspend_battery`, `dim`, `screen_off`, `shell_owned` (`arctic-shell-ipc shell
  live` answered); `idle-set LOCK SUSPEND [--battery LOCK SUSPEND] [--dim on|off] [--screen-off
  SECONDS]` keeps its two-argument form. It still restarts the backstop
  (`arctic-session idle --restart`); the shell follows the file.
- Search entries: `power.dim` "Dim the screen before it locks" (words "fade dim warning locking
  soon"), `power.screenoff` "Turn the screen off after locking" (words "display off dpms blank"),
  `power.battery.times` "Times on battery".

**4.4.7 Tests.**
- `shell/tests/test-idle-plan.cjs`: defaults, battery fallback to plugged-in values, dim only when
  the lock is ≥ 60 s, never-lock with suspend, screen off after lock.
- `settings/tests/test_arctic_system.py`: `idle.conf` round trip with the new keys, the old
  two-argument call, refused orders.
- 16.2 #4 (the dim layer passes input through; monitors wake), #5 (pipeline and backstop together).

#### 4.5 Laptop lid and clamshell (missed gap, P1)

**4.5.1 Behaviour.**
- Another screen connected when the lid closes: the laptop panel turns off
  (`disable_monitor`), windows move to the other screen, nothing suspends. Logind already
  ignores the lid when docked (`HandleLidSwitchDocked=ignore`; logind counts more than one
  connected display as docked). Opening the lid turns the panel back on.
- No other screen: what the person chose in Settings: **Suspend** (default; logind does it,
  swayidle's `before-sleep` locks first), **Lock and turn the screen off**, or **Keep running with
  the screen off**.
- For the last two, logind must not suspend: `arctic-session lid` holds `systemd-inhibit
  --what=handle-lid-switch --mode=block --who="Arctic Linux" --why="Closing the lid does what you
  chose in Settings" sleep infinity` (`org.freedesktop.login1.inhibit-handle-lid-switch` is
  `allow_active=yes`). It holds nothing when the choice is Suspend, and if the session dies the
  lock goes with it, so logind's default returns. No `/etc/systemd/logind.conf.d` file is
  written and nothing needs root.

**4.5.2 Binds** (`binds.conf`, new block after "Hardware keys", 86-95):

```
# ---- Laptop lid ---------------------------------------------------------
switchbind=fold,spawn,arctic-display lid closed
switchbind=unfold,spawn,arctic-display lid open
```

Only the first `switchbind` per state counts (2.2), so a user's own lid binding in `user.conf`
is shadowed; the shortcuts section's collision check (D7) must read `switchbind` lines too (15).

**4.5.3 `arctic-display lid closed|open`** (5.2 has the whole helper):
- `closed`: first confirms the lid is really closed (`/proc/acpi/button/lid/*/state` says
  `closed`, else logind's `LidClosed` property through `gdbus call --system --dest
  org.freedesktop.login1 … Get org.freedesktop.login1.Manager LidClosed`); a tablet-mode switch
  on a 2-in-1 fires the same binding, so without a closed lid it does nothing. Then: an external
  output connected and enabled → `mmsg dispatch disable_monitor,<internal>`, stop a mirror that
  shows the internal panel, record `internal_off_by: "lid"`; otherwise per `lid.conf`: `suspend`
  → nothing; `lock` → `arctic-lock`, then `sleep_monitor,<internal>`; `screen-off` →
  `sleep_monitor,<internal>`.
- `open`: `enable_monitor,<internal>` if `internal_off_by` is `lid`; `wakeup_monitor,<internal>`
  if it was put to sleep.
- The internal output is the connected DRM connector named `eDP-*`, `LVDS-*` or `DSI-*`
  (`/sys/class/drm/card*-<name>/status`); Mango's output names are the connector names.

**4.5.4 Unplugging while the lid is closed.** `arctic-session display` (new) runs
`arctic-display watch`: `udevadm monitor --udev --subsystem-match=drm` lines trigger a re-check;
when no external output is connected and the internal one is off by `lid` or by the display
mode (5.2), it enables the internal panel again and shows the OSD message "Laptop screen on".
🔍 whether logind then suspends a closed, undocked laptop after its hold-off (16.2 #8).

**4.5.5 Settings → Power and lock.** Group "Laptop lid" (89-97) becomes, shown only when
`/proc/acpi/button/lid` exists:
- "When you close the lid" (`ArSelect`, `power.lid`): Suspend / Lock and turn the screen off /
  Keep running with the screen off. Desc: "With another screen plugged in, closing the lid turns
  the laptop screen off and your windows move to the other screen."
- `arctic_system.py`: `lid` → `{"ok":true,"present":true,"when_closed":"suspend","inhibitor":false}`;
  `lid-set suspend|lock|screen-off` writes `lid.conf` (atomic, backed up, in `WRITERS`) and runs
  `arctic-session lid --restart`.
- Search: `power.lid` "When you close the lid" (words "laptop lid switch clamshell docked
  external monitor").

**4.5.6 Tests.** `shell/tests/test_display.py` (5.2): lid decisions for every mix of lid state,
tablet-mode false alarm, external connected/disabled, `lid.conf` value; recovery in `watch`.
16.2 #7, #8.

#### 4.6 Power menu extras (P2, `power-menu-extras`)

**4.6.1 Rows.** `shell/PowerMenu.qml` (its rows move to the bar-menus toolkit's `MenuRow`, its
WP-A) gets:
- "Hibernate" (`sleep` glyph), after Suspend, only when logind's
  `CanHibernate` answers `yes`.
- A last row "More" (`dots`, chevron) opening a `MenuPage` with "Restart into firmware setup"
  (`cpu`), only when `CanRebootToFirmwareSetup` answers `yes`; the row is hidden when the page
  would be empty. The main list stays at six or seven rows.
- Both answers come from one `gdbus call --system --dest org.freedesktop.login1 --object-path
  /org/freedesktop/login1 --method org.freedesktop.login1.Manager.CanHibernate` (and
  `…CanRebootToFirmwareSetup`) when the menu opens.

**4.6.2 Before Restart, Shut down and Log out.** New `arctic-power prepare
restart|poweroff|logout --json`:
1. **Busy check** (before touching any window): the Get apps runner (`AppsService.busy`,
   Get apps section 3.10, passed in by the shell as `--apps-busy "<label>"`), a `dnf5`, `rpm`,
   `flatpak` or `fwupdmgr` process (`pgrep -x`), the `arctic-update` lock (`busy()`,
   `arctic-update:125-129`). Any → `{"ok":true,"busy":[{"what":"dnf5","label":"Installing GIMP"}],"open":[]}`
   and nothing else happens.
2. **Close windows**: `mmsg get all-clients`, then `mmsg dispatch killclient client,<id>` for
   each (a normal close request), then poll every 250 ms for up to 5 s.
3. Answer `{"ok":true,"busy":[],"open":[{"id":12,"appid":"dev.zed.Zed","title":"main.rs — Zed"}]}`.

The shell's menu, after the person picks Restart / Shut down / Log out:
- busy → a sheet in the menu: `alert` (in `warning`) "An app is still installing" /
  "Restarting now can leave GIMP half-installed." / buttons "Restart anyway" (secondary) and
  "Wait" (the one primary button: it is the safe choice; `design/brand-book.md:6`);
- windows left open → "Zed is still open" / "It may be asking whether to save changes." /
  "Restart anyway" and "Cancel" (primary "Cancel");
- otherwise `arctic-power restart|poweroff|logout` as today.

The fuzzel fallback (`arctic-power` with no argument, no shell) runs `prepare` before it acts and
asks the same question through `fuzzel --dmenu` (items "Restart anyway", "Cancel"); `arctic-power
restart|poweroff|logout` with an argument still acts at once, which is what the shell calls after
its own check. New actions: `arctic-power
hibernate` (`systemctl hibernate`) and `arctic-power firmware` (`systemctl reboot
--firmware-setup`). Usage text (3-9, 19) and `dotfiles/README.md:76` list them.

**4.6.3 Keys.** `Super + Esc` unchanged. The power key opening the menu is the hardware-keys
item's (other section); this menu is what it opens.

**4.6.4 Tests.** `shell/tests/test_power_prepare.py` runs `arctic-power prepare` against a fake
`mmsg` and `pgrep` on `PATH` (clients that close, one that stays, a busy dnf5) and checks the
JSON; ShellCheck covers the script.

#### 4.7 Hibernation: the decision

Arctic Linux 0.3.0 does not set up hibernation. The reasons:

1. **No disk swap.** Arctic installs zram swap only, as Fedora does; a hibernation image needs a
   disk swap at least as large as the memory in use, `resume=` and `resume_offset=` kernel
   arguments, and dracut's `resume` module. The installer does none of this (2.2), so logind
   reports `CanHibernate=na`.
2. **Secure Boot.** Fedora's kernels turn on lockdown when booted with Secure Boot, and lockdown
   forbids hibernating to swap that isn't signed and encrypted by the kernel
   (kernel_lockdown(7)). Arctic keeps Secure Boot on (shim, MOK enrolment for NVIDIA), so for many
   installs the menu row could never work.
3. **Arctic's layout is untested for it.** A swapfile on btrfs inside LUKS2 needs a no-COW
   subvolume and `btrfs inspect-internal map-swapfile -r` for the offset. A resume that fails
   loses the whole session, which is worse than the suspend that happens today.

What 0.3.0 does instead:
- The power menu shows Hibernate only when logind says `yes` (someone set it up by hand, Secure
  Boot off).
- Low-battery texts name the action that will really happen (4.2).
- The FAQ explains why there's no Hibernate and what happens at 2 % (13).
- Revisit when a hibernation setup can be tested on Arctic's LUKS2 + btrfs layout with Secure
  Boot off, as an opt-in helper like Omarchy's `omarchy-hibernation-setup` (17).

---

### 5. Displays and graphics

#### 5.1 Night light (P0, `night-light`)

**5.1.1 Tool.** wlsunset 0.4.0 (Fedora 44 ✅, `wlsunset-0.4.0-4.fc43`). Mango creates the
`wlr_gamma_control_manager_v1` (`src/main.c:548`) ✅. Quickshell has no gamma API, so a small
daemon supervises one wlsunset process. gammastep (also in F44) is not used: one tool is enough,
and wlsunset's arguments cover every mode below.

**5.1.2 Settings file** `~/.config/arctic/nightlight.conf` (written only by the helper):

```
# Written by arctic-nightlight (Settings → Displays → Night light).
mode=schedule          # off | schedule | always
schedule=sunset        # sunset (sunset to sunrise where you are) | custom (from/to below)
temp=4000              # warmth at night, 3000–5500 K
from=20:00             # custom: warm from…
to=07:00               # …until
latitude=              # empty: from your time zone
longitude=
```

Defaults when the file is missing: `mode=off`, `schedule=sunset`, `temp=4000`, `from=20:00`,
`to=07:00`.

**5.1.3 Location** without geoclue or the network: the time zone's coordinates from
`/usr/share/zoneinfo/zone1970.tab` (tzdata ✅; ISO 6709 `±DDMM±DDDMM` or `±DDMMSS±DDDMMSS`),
the zone from the `/etc/localtime` link. A zone that isn't in the table (`UTC`, `Etc/*`) has no
location: `schedule=sunset` then behaves as `custom` with the configured hours, and the status
says "Arctic doesn't know where UTC is: pick hours or enter a location." Manual
`latitude`/`longitude` win. Changing the time zone (6.2) runs `arctic-nightlight reload`.

**5.1.4 wlsunset arguments** (the daemon restarts wlsunset whenever the wanted arguments change;
it never signals it):

| State | Command |
|---|---|
| off, or paused | no wlsunset (the gamma ramp resets when the client goes) |
| schedule, sunset | `wlsunset -t TEMP -T 6500 -l LAT -L LON` |
| schedule, custom | `wlsunset -t TEMP -T 6500 -S TO -s FROM -d 1800` (`-d 0` with reduced motion; `-d` only applies to manual times ✅) |
| always, or turned on now | `wlsunset -t TEMP -T TEMP+1 -S 06:00 -s 18:00 -d 0` (day and night 1 K apart, so it's warm all day) 🔍 16.2 #9 |

**5.1.5 `dotfiles/.local/bin/arctic-nightlight`** (python3, standard library):

```
arctic-nightlight status [--json]
arctic-nightlight toggle | on | off
arctic-nightlight set KEY=VALUE…        mode= schedule= temp= from= to= latitude= longitude=
arctic-nightlight reload                re-read the file and the time zone
arctic-nightlight daemon                arctic-session nightlight runs it, once per session
```

- `set` validates (temp 3000–5500 in steps of 100, `HH:MM`, latitude −90…90, longitude
  −180…180), writes the file atomically and signals the daemon (`SIGHUP` to the PID in
  `$XDG_RUNTIME_DIR/arctic/nightlight.pid`).
- **toggle** is predictable and never edits the file; it sets a run-time override that ends at
  the next scheduled change:
  - scheduled and warm now → off until tonight's start ("Night light off until 19:05");
  - scheduled and not warm → on until tomorrow's end ("Night light on until 06:42");
  - always → off until toggled again or the next login;
  - off → on until toggled again or the next login.
  `on`/`off` set the same overrides explicitly.
- **daemon**: takes `flock` on `$XDG_RUNTIME_DIR/arctic/nightlight.lock` (a second one exits 0),
  writes its PID, computes the wanted state, starts wlsunset as its child, writes
  `nightlight.json` atomically, then sleeps until the next boundary (override end, schedule
  start/end for the status text) or a signal. wlsunset exiting on its own is restarted with
  backoff 1, 2, 4 … 60 s; after five fast failures the status says "Night light doesn't work on
  this screen." The daemon exits when the Wayland socket (`$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY`)
  is gone. Missing wlsunset → `available:false`, and it exits.
- **Sun times** for the status and for toggle's boundaries: NOAA's solar equations for civil
  dawn and dusk (sun 6° below the horizon), in a pure function `sun_times(date, lat, lon, tz)`.
  wlsunset does its own sun maths; the status says "about" ("On until about 06:40") 🔍 16.2 #10.
- `status --json` / `nightlight.json`:

```json
{"ok":true,"available":true,"mode":"schedule","schedule":"sunset","temp":4000,"from":"20:00","to":"07:00",
 "active":true,"override":"none","next_change":"2026-09-29T06:42:00+03:00",
 "location":{"source":"timezone","zone":"Asia/Jerusalem","latitude":31.7806,"longitude":35.2239},
 "running":true,"message":""}
```

**5.1.6 Session.** `arctic-session nightlight` → `run_once`-style start of `arctic-nightlight
daemon` (the lock file decides, not the process name: a python script's `comm` is `python3`).
`autostart.conf` gains `exec-once=arctic-session nightlight` (both sessions; the live session
too).

**5.1.7 Shell.** New singleton `shell/NightLightService.qml`: a `FileView` on `nightlight.json`
(`watchChanges`) gives `available`, `active`, `mode`, `detail` ("On until 06:42", "Starts at
19:05", "Off"); `toggle()` runs `arctic-nightlight toggle` and then the OSD message
(`night-light`, the helper's sentence). Toggle entry `nightlight` (3.5). Quick Settings
sub-page `nightlight`: radio rows "Off", "Sunset to sunrise", "Custom hours" (detail "20:00–07:00"),
"Always on"; a `MenuSlider` "Warmth" 3000–5500 K (moving it runs `arctic-nightlight set temp=…`
250 ms after the last move); footer "Night light settings" → `arctic-settings displays`. The
bar-menus Display page has a slot for these rows (`DisplayPanel.extraRows`, its 5.8): a
`MenuSwitchRow` "Night light" with the same detail.

**5.1.8 Settings → Displays.** New group "Night light" after "Saved layout" (564-586):
- "Night light" `ArSegmented` (`displays.nightlight`): Off / Sunset to sunrise / Custom hours /
  Always.
- "Warmth" `ArSlider` 3000–5500 K, step 100, value "4000 K" (`displays.nightlight.warmth`);
  moving it previews (the daemon restarts wlsunset; 250 ms debounce).
- Custom hours: two `ArSelect`s "From" / "To" in 30-minute steps.
- Location row (sunset mode): "Sunset and sunrise for Jerusalem (your time zone)" and a ghost
  button "Use my own location" revealing two `ArInput`s (latitude, longitude).
- The group's desc is the daemon's status sentence.
- `arctic_system.py`: `nightlight` (→ `arctic-nightlight status --json`), `nightlight-set
  KEY=VALUE…` (→ `arctic-nightlight set …`; in `WRITERS`).
- Search: `displays.nightlight` "Night light" (words "blue light warm evening colour temperature
  redshift flux sunset"), `displays.nightlight.warmth` "Night light warmth".

**5.1.9 Tests.**
- `shell/tests/test_nightlight.py` (loads `dotfiles/.local/bin/arctic-nightlight` with
  `importlib.machinery.SourceFileLoader`): config parsing and validation; `zone1970.tab` parsing
  (both coordinate forms, a fixture file); `sun_times` against published values (Jerusalem
  2026-06-21, Reykjavik 2026-12-21, Sydney 2026-06-21, an equator case; ± 2 min); the
  wlsunset argv table for every state; toggle overrides and their end times across midnight and
  across a DST change; status JSON.
- 16.2 #9, #10, #11 (gamma on Mango with scenefx, two monitors, the lock screen).

#### 5.2 Display mode: duplicate, extend, one screen (P2, `display-mode-mirror`)

**5.2.1 `dotfiles/.local/bin/arctic-display`** (python3, standard library; `wlr-randr` becomes a
Requires of arctic-desktop-config, 11.1):

```
arctic-display status [--json]
arctic-display mode laptop | mirror | extend | external | only NAME
arctic-display lid closed | open        (4.5)
arctic-display watch                    (arctic-session display)
arctic-display menu                     (the shell's panel over IPC; fuzzel without the shell)
```

- Outputs: connected connectors from `/sys/class/drm/card*-*/status`, enabled state and names
  from `wlr-randr --json`. Internal = `eDP-*`, `LVDS-*`, `DSI-*`.
- `laptop`: `mmsg dispatch disable_monitor,<each external>`, `enable_monitor,<internal>`.
- `extend`: enable all; stop mirrors.
- `external`: enable externals, `disable_monitor,<internal>`; `internal_off_by: "mode"`.
- `mirror`: enable all, then one `wl-mirror --fullscreen-output <external> <internal>` per
  external (wl-mirror 0.18.5, F44 ✅; `--fullscreen-output O` ✅; app id `at.yrlf.wl_mirror` ✅),
  started detached, PIDs in `display.json`. 🔍 16.2 #12: Mango honours the fullscreen-on-output
  request; fallback: after the window maps, `mmsg dispatch tagmon,<external> client,<id>` and
  `togglefullscreen client,<id>`.
- `only NAME` (desktops with several screens): that one on, the rest off.
- Every change is run-time only (Settings' saved `monitorrule` lines are untouched), so a
  restart or a re-plug is back to the saved layout; Mango keeps a disabled output off across
  `reload_config` ✅ (2.2).
- `status --json`: `{"ok":true,"outputs":[{"name":"eDP-1","internal":true,"connected":true,"enabled":true,"description":"BOE 0x0BCA"}],"mode":"extend","mirror":false,"internal_off_by":null,"choices":["laptop","mirror","extend","external"]}`.
- `watch` (4.5.4) also stops a mirror whose target output went away.

**5.2.2 Shell.** New `shell/DisplayModePanel.qml` (panel `displaymode`) and pure
`shell/DisplayModes.js` (`rows(status)` → labelled rows; tested):
- Laptop with one other screen: "Laptop screen only", "Duplicate", "Extend", "Second screen
  only" (radio rows, `screens` icon in the header "Screens"; the current mode has the `selected`
  look).
- Desktop with several screens: "Extend", "Duplicate" (the main screen on the others), then
  "Only <description>" per screen.
- One screen: a single row "Only one screen is connected." and the footer.
- Footer "Display settings" → `arctic-settings displays`.
- Enter applies (`arctic-display mode …`), closes the panel, shows the OSD message ("Duplicate").
- It opens under the right end of the bar like Quick Settings (no bar item).
- `Super + P` or the display key again while open moves to the next row (as Windows' Win+P);
  Enter applies. If a screen goes black, `Super + P`, `Home`, `Enter` gets the laptop screen
  back without seeing anything (documented in Keyboard-Shortcuts).
- IPC `display menu()` / `mode(name)`.

**5.2.3 Rules.** `rules.conf`: `windowrule=noblur:1,noshadow:1,noanim:1,appid:^at\.yrlf\.wl_mirror$`
after the floats (131-136).

**5.2.4 Tests.** `shell/tests/test_display.py` (fake `/sys` tree, fake `wlr-randr`/`mmsg`/`wl-mirror`
on `PATH`): the dispatch sequence per mode, mirror PIDs, `watch` recovery, lid (4.5.6).
`shell/tests/test-display-modes.cjs`: rows for laptop+1, laptop+2, desktop×3, one screen.

#### 5.3 Lighter effects on virtual machines, and game mode (missed gap; P2 `game-mode`)

**5.3.1 Why a file.** Omarchy's VM default (`b18ab49`) cut CPU per interaction 4–10× under
llvmpipe. Arctic's live ISO is often tried in a VM. `setoption` would be undone by every Settings
change (2.2), so both features write a Mango include that is sourced after `settings.conf`.

**5.3.2 `dotfiles/.local/bin/arctic-effects`** (bash):

```
arctic-effects status [--json]     {"ok":true,"lighter":"auto","lighter_active":true,"reason":"vm","game":false,"game_auto":false}
arctic-effects lighter auto|on|off
arctic-effects game on|off|toggle [--auto]
arctic-effects apply               (arctic-session effects, at login: game mode off, lighter re-detected)
```

- State: `~/.config/arctic/effects.json` `{"lighter":"auto|on|off","game":false,"game_auto":false,"game_by":"user|gamemode"}`.
- Lighter is active when `on`, or `auto` and (`systemd-detect-virt --vm --quiet` succeeds, or no
  `/dev/dri/renderD*` exists: simpledrm in "Safe graphics mode" has none).
- `~/.config/arctic/effects.conf` is regenerated from the state (a comment-only file when nothing
  is on):

```
# Written by arctic-effects. ~/.config/mango/config.conf sources it after settings.conf.
# Lighter effects (virtual machine)
animations=0
layer_animations=0
blur=0
blur_layer=0
shadows=0
layer_shadows=0
# Game mode
gappih=0
gappiv=0
gappoh=0
gappov=0
```

- When the file's content changed: `mmsg dispatch reload_config`, `arctic-shell-ipc shell reload`.
- **The source line.** `dotfiles/.config/mango/config.conf` gains
  `source-optional=~/.config/arctic/effects.conf` between the `settings.conf` (31) and `user.conf`
  (32) lines, and its header comment (6-11) names it. Existing homes have a copy of that file, so
  `arctic-effects` inserts the line before the `user.conf` line when it is missing (backup to
  `~/.local/state/arctic/settings-backups/config.conf.<timestamp>`, as Settings' `ensure_sourced`,
  `arctic_settings.py:601-625`).
- `autostart.conf` gains `exec-once=arctic-session effects` before `arctic-session shell`; the
  first login in a VM reloads Mango once, later logins find the file already right.

**5.3.3 Shell.** New singleton `shell/EffectsService.qml` (`FileView` on `effects.json`: `lighter`,
`game`). `Theme.qml` (shared edit): durations are 0 when `Session.reduceMotion ||
EffectsService.lighterActive` (as `reduceMotion` today, 102-107), and `frost` becomes
`surfaceRaised` at full opacity when lighter is active (brand book: "Where blur is unavailable
(… software rendering) use surface-raised at full opacity", `design/brand-book.md:75`). Toggle
`gamemode` (3.5).

**5.3.4 Game mode while a game runs** (optional sub-item; off by default): with the `gamemode`
module installed, new `shell/GameModeService.qml` runs `gdbus monitor --session --dest
com.feralinteractive.GameMode` and reads `ClientCount`; with `game_auto` on, a count above 0
runs `arctic-effects game on --auto`, and 0 runs `game off` only when `game_by` is `gamemode`.

**5.3.5 Settings → Windows.** New group "Effects" after "Motion and effects" (131-211):
- "Lighter effects" `ArSegmented` Automatic / On / Off (`windows.lighter`); desc "Turns off
  animations, blur and shadows. Automatic turns them off in virtual machines and without a
  graphics driver." plus the reason when active ("On now: this is a virtual machine.").
- "Game mode" `ArToggle` (`windows.gamemode`), desc "No animations, blur, shadows or gaps until you
  turn it off or log out."
- "Turn on game mode while a game runs" `ArToggle`, only with gamemode installed.
- A banner at the top of the page while either is on: "Lighter effects are on, so animations,
  blur and shadows are off." (the page's switches show the effective values, which now come from
  `effects.conf`).
- `arctic_system.py`: `effects`, `effects-set lighter auto|on|off`, `effects-set game on|off`,
  `effects-set game-auto on|off` (→ `arctic-effects`).

**5.3.6 Tests.** `shell/tests/test_effects.py` runs `arctic-effects` in a scratch `HOME` with fake
`systemd-detect-virt`, `mmsg` and a fake `/dev/dri` root (`ARCTIC_EFFECTS_DRI` for tests): state
round trip, generated file for each combination, source-line insertion (present, missing,
missing user.conf line), reload only on change. `%check`'s `mango -p` run on the skel home
(spec:886-897) proves the new `source-optional` line parses.

#### 5.4 Run an app on the discrete GPU (missed gap, P2)

**5.4.1 Tool.** switcheroo-control 3.0 (F44 ✅) serves `net.hadess.SwitcherooControl` and ships
`switcherooctl launch [--gpu=N|-g N] COMMAND…`, which defaults to the first discrete GPU and sets
that GPU's environment (for NVIDIA the PRIME offload variables) before `execvp` ✅
(`src/switcherooctl.in:60-66, 122-134`). `90-default.preset:302` enables its service ✅; arctic-desktop
now requires it (11.1).

**5.4.2 `dotfiles/.local/bin/arctic-gpu`** (python3):

```
arctic-gpu status --json   {"ok":true,"hybrid":true,
                            "gpus":[{"index":0,"name":"Intel Graphics","default":true,"discrete":false},
                                    {"index":1,"name":"NVIDIA GeForce RTX 4060 Laptop GPU","default":false,"discrete":true}],
                            "prefers":["com.valvesoftware.Steam","steam"]}
arctic-gpu run COMMAND…    exec switcherooctl launch COMMAND…
```

- GPUs from `switcherooctl list` (its `Device:`, `Name:`, `Default:`, `Discrete:` lines ✅);
  `hybrid` = more than one GPU and one of them discrete.
- `prefers`: desktop ids whose entry has `PrefersNonDefaultGPU=true` or
  `X-KDE-RunOnDiscreteGpu=true`, from the XDG data dirs and both Flatpak export dirs.

**5.4.3 Shell.** New singleton `shell/GpuService.qml` (runs `status` at start and 2 s after the
desktop entries change): `hybrid`, `discreteName`, `prefers`. `Launcher.qml` `activate(item,
alternate)` (83-106; shared edit), case `'app'`, not `runInTerminal`: when `GpuService.hybrid`
and (`alternate` or `prefers` has the id) → `Quickshell.execDetached({command:
['switcherooctl','launch'].concat(item.entry.command), workingDirectory: …})`; otherwise
`item.entry.execute()` as today. The footer hint for a selected app on a hybrid machine:
"Shift + Enter · run on NVIDIA GeForce RTX 4060". The row's actions (the Get apps section adds a
right-click sheet) get "Run on NVIDIA GeForce RTX 4060".

**5.4.4 Docs and tests.** `docs/wiki/Drivers.md` "Laptops with two graphics chips" (145-156):
Shift+Enter in the launcher first, the variables after. `shell/tests/test_gpu.py`: `switcherooctl
list` fixtures (one GPU, Intel+NVIDIA, AMD+AMD dGPU, no service), the `prefers` scan over a fake
data dir. 16.2 #13.

---

### 6. Session and system

#### 6.1 XDG autostart (P1, `xdg-autostart`)

**6.1.1 Pulling the target in.** New `packaging/systemd/user/mango-session.target.d/arctic-autostart.conf`
→ `/usr/lib/systemd/user/mango-session.target.d/arctic-autostart.conf` (arctic-desktop-config):

```ini
# Arctic Linux: start the apps that asked to start at login (~/.config/autostart and
# /etc/xdg/autostart), as other desktops do. xdg-desktop-autostart.target refuses a manual
# start; a session target pulls it in (systemd.special(7)).
[Unit]
Wants=xdg-desktop-autostart.target
```

Mango imports `XDG_CURRENT_DESKTOP=mango` and the display variables before it starts
`mango-session.target` (2.1), so systemd-xdg-autostart-generator's units see them and their
`OnlyShowIn`/`NotShowIn`/`TryExec`/`Hidden`/`X-GNOME-Autostart-enabled` checks work ✅.

**6.1.2 What would start twice.** F44 packages in the image with autostart files ✅ (mdapi):
`blueman.desktop` (no restriction ✅), `nm-applet.desktop` (`NotShowIn=KDE;GNOME;Budgie;COSMIC;` ✅,
so it runs under Mango), `lxqt-policykit-agent.desktop` (`OnlyShowIn=LXQt`), three
`gnome-keyring-*.desktop` (`OnlyShowIn=GNOME;Unity;MATE;` ✅), `at-spi-dbus-bus.desktop`,
`spice-vdagent.desktop`, `xdg-user-dirs.desktop`, plus `kdeconnectd` and `fcitx5-autostart` when
installed. In the Quickshell session the shell has its own network menu and Bluetooth agent
(bar-menus section), so blueman's applet and nm-applet must start only in the waybar session:

```ini
# /usr/lib/systemd/user/app-blueman@autostart.service.d/arctic.conf
# /usr/lib/systemd/user/app-nm\x2dapplet@autostart.service.d/arctic.conf
# Arctic Linux: the shell has its own Bluetooth / network menus and agents; these applets
# start only in the fallback desktop (ARCTIC_SHELL=waybar).
[Service]
ExecCondition=/usr/bin/arctic-session fallback-only
```

- `ExecCondition=` may appear more than once, and the generated unit already has one for
  `OnlyShowIn`; drop-ins apply to generated units. 🔍 16.2 #14: the unit names on F44
  (`systemctl --user list-units --all 'app-*@autostart.service'`).
- New `arctic-session fallback-only`: exits 0 when the waybar session is in use (`ARCTIC_SHELL`
  is `waybar` in the environment, or an `env=ARCTIC_SHELL,waybar` line in `~/.config/mango/user.conf`
  or `settings.conf`, or quickshell / the shell folder is missing), else 1. The systemd user
  manager doesn't import `ARCTIC_SHELL`, hence the config check. It shares its test with the
  bar-menus section's `shell_session`.
- `arctic-session nm-applet` (36) keeps `run_once`, so XDG and `autostart.conf` never start two.
- The spec installs the drop-ins from `packaging/systemd/user/` with `cp -a` and lists them with a
  glob (`%{_userunitdir}/app-*@autostart.service.d/`), so the `\x2d` never appears in `%files`.

**6.1.3 Settings → Startup apps.** Comment (1-3) and lede (13): "Apps and commands that start when
you log in, including apps whose own "Start on login" you turned on." New group "Apps that start
by themselves" between "Yours" (26-93) and "Started by Arctic" (95-108):
- one row per entry that would run under Mango (merged by desktop id, `~/.config/autostart`
  wins): icon, name, "Added by the app" / "From the system", an `ArToggle`;
- off → `~/.config/autostart/<id>.desktop`: a copy of the system file with `Hidden=true` and
  `X-Arctic-Hidden=true`, or, for a file the app wrote itself, `Hidden=true` added in place;
- on → delete our copy (`X-Arctic-Hidden=true`), or remove `Hidden=true` /
  `X-GNOME-Autostart-enabled=false` from the app's own file;
- entries excluded for Mango (`OnlyShowIn`/`NotShowIn`), `NoDisplay` session plumbing
  (`at-spi-dbus-bus`, `xdg-user-dirs`, `spice-vdagent`) and the two applets of 6.1.2 are not
  listed;
- "Changes apply the next time you log in" (the generator runs when the user manager starts).
- `arctic_system.py`: `startup` gains `"xdg":[{"id","name","icon","source":"system|user","enabled"}]`
  (it wraps `cmd_startup`, 956-966); `startup-xdg-set ID on|off` (in `WRITERS`; the id must match
  `^[A-Za-z0-9._-]+$` and name an existing entry).
- Search: `startup.xdg` "Apps that start by themselves" (words "autostart login discord steam
  nextcloud start on login background").

**6.1.4 Docs.** `docs/PLAN.md:328` ("Mango doesn't process XDG autostart") becomes "Arctic pulls
in `xdg-desktop-autostart.target` from `mango-session.target`"; `docs/wiki/Settings.md` Startup
apps (254-261).

**6.1.5 Tests.** `settings/tests/test_arctic_system.py`: listing with a fake
`XDG_CONFIG_DIRS`/`XDG_CONFIG_HOME` (system only, user override, `Hidden`, `OnlyShowIn=GNOME`,
`NotShowIn=mango`), on/off round trips, refused ids. `ci.yml` `units` job (100-115):
`systemd-analyze verify --user` of a copy of `mango-session.target` with the drop-in. 16.2 #14,
#15 (Flathub apps' "run in background" through the Background portal).

#### 6.2 Date, time and language (P1, `date-time-region`)

**6.2.1 New page `settings/pages/DateTimePage.qml`** (id `datetime`, "Date and time", `clock`):

| Group | Row | Control | Backend |
|---|---|---|---|
| Time zone | "Time zone" (`datetime.zone`) | the current zone ("Jerusalem · Israel · UTC+3") and a "Change" button opening a search dialog (`PickerDialog`-style list with a filter field): rows "Jerusalem — Israel — UTC+3", matching city, country or zone name | `timezones`, `timezone-set ZONE` |
| Time | "Set the time automatically" (`datetime.ntp`) | `ArToggle` | `ntp-set on\|off` |
| Time | "Date and time" | `ArInput`s (date, time), enabled only when automatic time is off | `time-set "YYYY-MM-DD HH:MM"` |
| Clock | "Clock" (`datetime.clock`) | `ArSegmented` Automatic / 24-hour / 12-hour | `shell-set clock_format auto\|24h\|12h` |
| Clock | "Show the date on the bar" (`datetime.date`) | `ArToggle` (default on, as today) | `shell-set clock_date true\|false` |
| Clock | "First day of the week" (`datetime.week`) | `ArSelect` Automatic / Monday / Sunday / Saturday | `shell-set week_start …` |
| Language | "Language" (`datetime.language`) | `ArSelect` of installed locales; desc "For everyone on this computer, from the next login." | `locale-set LOCALE` |

`arctic_system.py`:
- `datetime` → `timedatectl show` (key=value: `Timezone`, `NTP`, `NTPSynchronized`, `CanNTP`)
  plus `localectl status` and `localectl list-locales`:
  `{"ok":true,"timezone":"Asia/Jerusalem","utc_offset":"+03:00","ntp":true,"synced":true,"can_ntp":true,"locale":"en_US.UTF-8","locales":[{"id":"he_IL.UTF-8","name":"עברית (ישראל)"}],"clock_format":"auto","clock_date":true,"week_start":"auto"}`.
- `timezones` → every zone from `timedatectl list-timezones`, with the city (last path part,
  `_` → space), the country from `zone1970.tab` + `iso3166.tab`, and the current UTC offset from
  Python's `zoneinfo`.
- `timezone-set ZONE` (must be in that list) → `timedatectl set-timezone ZONE`
  (`org.freedesktop.timedate1.set-timezone`, `auth_admin_keep`, the shell's dialog), then
  `arctic-nightlight reload`.
- `ntp-set on|off` → `timedatectl set-ntp true|false`; `time-set` → `timedatectl set-time` (refused
  while NTP is on).
- `locale-set LOCALE` (must be in `localectl list-locales`) → `localectl set-locale LANG=LOCALE`.
  More languages come from Get apps (`glibc-langpack-*`); the row says so.
- `shell-set` keys added: `clock_format`, `clock_date`, `week_start`.
- Every write that goes through polkit and is dismissed answers "You closed the password prompt.
  Nothing changed." (exit code 1 from `timedatectl` with "Interactive authentication required" or
  "Access denied" on stderr).

**6.2.2 Shell.**
- New pure `shell/ClockFormat.js`: `timeFormat(setting, localeTimeFormat)` → `'hh:mm'` or
  `'h:mm AP'` (automatic = 12-hour when the locale's short time format contains `AP`/`ap`),
  `barText(date, settings)`; Node-tested.
- `Bar.qml` clock (88-96; the bar-menus section turns it into `clockItem`): text from
  `ClockFormat.barText`; a middle click opens `arctic-settings datetime` (Omarchy's middle-click
  time-zone picker).
- `LockScreen.qml:129` uses `ClockFormat` for the time.
- The bar-menus `CalendarPanel.qml` takes the first day from `Session.settings.week_start` when it
  isn't `auto` (else `Qt.locale().firstDayOfWeek`, as planned there).
- 🔍 16.2 #16: the shell's clock follows a time-zone change without a restart (Qt/glibc re-read
  `/etc/localtime`). If not, `timezone-set` answers `"restart_shell":true` and the page offers
  "Restart the desktop shell to update the clock".

**6.2.3 Search.** `datetime.zone` "Time zone" (words "timezone travel region city utc gmt"),
`datetime.ntp` "Set the time automatically" (words "ntp clock sync internet time"),
`datetime.clock` "Clock" (words "24-hour 12-hour am pm format"), `datetime.date` "Show the date on
the bar", `datetime.week` "First day of the week" (words "monday sunday calendar"),
`datetime.language` "Language" (words "locale region translation").

**6.2.4 Tests.** `settings/tests/test_arctic_system.py`: `timedatectl show` / `localectl` parsing
(fixtures), zone list building with a small fixture `zone1970.tab`/`iso3166.tab`, refusals.
`shell/tests/test-clock-format.cjs`. The headless smoke test (12.4) loads the page with stand-in
`timedatectl` and `localectl`.

#### 6.3 Users and sign-in (P2, `users-sign-in`)

**6.3.1 New page `settings/pages/UsersPage.qml`** (id `users`, "Users and sign-in", `user`;
hidden in the live session):

| Group | Row | Does |
|---|---|---|
| You | picture (96 px circle, `RoundedImage`-style) + "Change picture" / "Remove" | `user-avatar PATH` / `user-avatar --remove` |
| You | "Name" `ArInput` (`users.name`) | `user-name NAME` |
| You | "Username" (read-only) | — |
| Password | "Change your password" (`users.password`) | terminal: `passwd` (3.4) |
| Disk encryption (only when `/` is on LUKS) | "Change the disk passphrase" (`users.disk`) | terminal: `pkexec /usr/sbin/cryptsetup luksChangeKey /dev/disk/by-uuid/<UUID>` |
| Fingerprint (only with a reader) | "Fingerprints" list ("Right index finger"), "Add a fingerprint", "Remove all" (`users.fingerprint`) | terminal `fprintd-enroll`; `fprintd-delete $USER` |
| Fingerprint | "Unlock the screen with your fingerprint" `ArToggle` | `shell-set lock_fingerprint true\|false` |
| Fingerprint | "Use it for administrator prompts" `ArToggle` | root helper `fingerprint-login on\|off` |
| Security key (only with pam-u2f installed) | "Add a security key", "Use it for administrator prompts" (`users.key`) | terminal `pamu2fcfg`; helper `security-key-login on\|off` |

`arctic_system.py`:
- `users` → `{"ok":true,"user":"yuval","name":"Yuval","has_picture":true,"luks":{"present":true,"uuid":"…"},"fingerprint":{"reader":true,"fingers":["right-index-finger"],"login":false},"security_key":{"installed":false,"registered":false,"login":false},"live":false}`.
  LUKS: `lsblk -J -o NAME,TYPE,FSTYPE,UUID,MOUNTPOINTS` → the `crypto_LUKS` ancestor of `/`.
  Reader: `gdbus call --system --dest net.reactivated.Fprint --object-path
  /net/reactivated/Fprint/Manager --method net.reactivated.Fprint.Manager.GetDevices` non-empty;
  fingers: `fprintd-list $USER`. Login features: `authselect current` lists `with-fingerprint`,
  `with-pam-u2f`.
- `user-avatar PATH`: Pillow (already required by arctic-desktop-config) opens the picture,
  applies EXIF rotation, crops the centre square, scales to 256×256 and writes `~/.face` (PNG,
  0644); then `gdbus call --system --dest org.freedesktop.Accounts --object-path
  /org/freedesktop/Accounts/User<uid> --method org.freedesktop.Accounts.User.SetIconFile
  ~/.face` so SDDM, which reads AccountsService's copy, shows it (`org.freedesktop.accounts.change-own-user-data`
  is allowed for the active user). `--remove` deletes `~/.face` and sets an empty icon.
- `user-name NAME` (≤ 64 characters, no `:` or control characters) → `…User.SetRealName`.
- Terminal jobs as 3.4; `passwd` changes the login keyring's password too through Fedora's
  `/etc/pam.d/passwd` (`-password optional pam_gnome_keyring.so use_authtok`) 🔍 16.2 #17.
- `Session.qml` (shared edit) re-checks `~/.face` with a `FileView` so the lock screen shows a new
  picture without a restart.

**6.3.2 Fingerprint on the lock screen.** New `shell/pam/arctic-lock-fingerprint`:

```
# Fingerprint for the Arctic lock screen, run next to pam/arctic-lock (password).
auth required pam_fprintd.so max-tries=3 timeout=30
```

`LockScreen.qml` (shared edit, 51-78) runs a second `PamContext` with this config when
`Session.settings.lock_fingerprint !== false`, a reader exists and the lid is open (logind
`LidClosed`); success on either context unlocks. The status line under the field says "Or touch
the fingerprint reader"; three failures stop the fingerprint context until the next lock
(Omarchy runs separate password and fingerprint services the same way ✅).

**6.3.3 Packages.** arctic-desktop: `Requires: accountsservice`; `Recommends: fprintd, fprintd-pam,
pam-u2f, pamu2fcfg` (all F44 ✅).

**6.3.4 Search.** `users.picture` "Your picture" (words "avatar photo face account"), `users.name`,
`users.password` "Change your password", `users.disk` "Disk encryption passphrase" (words "luks
encryption unlock boot"), `users.fingerprint` "Fingerprint" (words "fprint biometric reader
unlock"), `users.key` "Security key" (words "yubikey fido u2f").

**6.3.5 Tests.** `settings/tests/test_arctic_system.py`: `lsblk` JSON → LUKS UUID (plain, LUKS
root, LVM on LUKS), `fprintd-list` and `authselect current` parsing, avatar crop/scale with a
generated picture, name validation. `shell/tests/test_system_helper.py`: every verb's argv and its
refusals (fake `authselect`). 16.2 #17-#19.

#### 6.4 Input methods: Fcitx 5 (missed gap, P1)

**6.4.1 Packages** (F44 ✅): `fcitx5` 5.1.23, `fcitx5-gtk`, `fcitx5-qt`, `fcitx5-configtool`,
`fcitx5-autostart` (it ships `/etc/xdg/autostart/org.fcitx.Fcitx5.desktop` and
`/etc/profile.d/fcitx5.sh`, which sets `GTK_IM_MODULE`, `QT_IM_MODULE`, `XMODIFIERS`,
`INPUT_METHOD` for graphical sessions ✅), engines `fcitx5-chinese-addons`, `fcitx5-mozc`,
`fcitx5-hangul` (also `fcitx5-rime`, `fcitx5-anthy`). Mango implements input-method-v2 and
text-input-v3 ✅. They are not in the image: `fcitx5.sh` changes every graphical session, and
most people don't need it. Settings installs them on request.

**6.4.2 Settings → Keyboard and mouse.** New group "Input method" after "Typing" (165-206)
(`input.im`):
- Not installed: desc "Type Chinese, Japanese, Korean and other languages that need more than a
  keyboard layout." Rows "Chinese (Pinyin and more)", "Japanese (Mozc)", "Korean (Hangul)" with
  checkboxes and an "Install" button → terminal `pkexec /usr/bin/dnf5 install -y fcitx5
  fcitx5-gtk fcitx5-qt fcitx5-configtool fcitx5-autostart <engines>` (3.4; the Get apps polkit
  action `org.arcticlinux.pkexec.dnf`, D2 unchanged).
- Installed, not running yet: "Log out and back in to start Fcitx 5."
- Running: "Configure" → `fcitx5-configtool`; "Switch between keyboard and input method with
  Ctrl + Space" (Fcitx's default trigger; no Arctic bind uses `Ctrl + Space`).
- `arctic_system.py`: `im` → `{"ok":true,"installed":["fcitx5","fcitx5-mozc"],"running":true,"engines":[{"id":"mozc","package":"fcitx5-mozc","label":"Japanese (Mozc)","installed":true}]}`
  (`rpm -q`, `pgrep -x fcitx5`); `im-install ENGINE…` opens the terminal; `im-configure`.
- Search: `input.im` "Input method" (words "chinese japanese korean pinyin mozc hangul ime fcitx
  cjk").

**6.4.3 Session.** Fcitx starts through XDG autostart (6.1) and shows its tray icon, which the bar's
QML tray menus draw (the bar IM indicator). `rules.conf`: `windowrule=isfloating:1,width:720,height:560,appid:^org\.fcitx\.fcitx5-config-qt$`
🔍 the app id (16.2 #20). 🔍 16.2 #21: typing Japanese in a GTK 4 app, a Qt 6 app, a Flatpak
(Zen) and a Chromium `--app` web app, and that Fcitx and Arctic's layout chip (bar-menus 5.9)
agree on the active layout.

**6.4.4 Interfaces.** The first-login welcome (other section) can point a zh/ja/ko installer
language at this group. Pre-ticking engines in the installer is deferred (17).

#### 6.5 SSH agent: gcr-ssh-agent (missed gap, P2)

- `gcr` 4.4 (F44 ✅) ships `/usr/libexec/gcr-ssh-agent`, `gcr4-ssh-askpass` and the user units
  `gcr-ssh-agent.socket`/`.service` ✅; the socket's `ExecStartPost` sets `SSH_AUTH_SOCK` in the
  user manager ✅. Its `%post` presets only the `.service` ✅, and `99-default-disable-user.preset`
  disables the socket, so nothing turns it on today.
- arctic-desktop: `Requires: gcr` (its GTK 4 dependency is already pulled in by arctic-webapps).
- `packaging/release/80-arctic-user.preset`: `enable gcr-ssh-agent.socket`.
- arctic-desktop-config `%posttrans`: once (marker `/var/lib/arctic/.ssh-agent-preset`, like
  `.update-presets` at spec:954-957) `systemctl --global preset gcr-ssh-agent.socket`.
- New `packaging/desktop/arctic-ssh-agent.sh` → `/etc/profile.d/arctic-ssh-agent.sh`, so apps
  started by Mango (which inherits the login shell's environment) find it:

```sh
# shellcheck shell=sh
# /etc/profile.d/arctic-ssh-agent.sh (arctic-desktop-config)
# SSH keys: gcr-ssh-agent (the user unit gcr-ssh-agent.socket) holds them for the session and
# asks for a key's passphrase in a dialog. An agent you start yourself wins.
if [ -z "${SSH_AUTH_SOCK:-}" ] && [ -n "${XDG_RUNTIME_DIR:-}" ] && [ -S "$XDG_RUNTIME_DIR/gcr/ssh" ]; then
  export SSH_AUTH_SOCK="$XDG_RUNTIME_DIR/gcr/ssh"
fi
```

- Docs: `docs/wiki/Terminal-and-Shell.md` gets "SSH keys" (the agent, `ssh-add -l`, turning it off
  with `systemctl --user disable --now gcr-ssh-agent.socket`).
- Tests: ShellCheck covers the new profile script (`ci.yml:53` includes `packaging/desktop/*.sh`);
  16.2 #22 (`ssh-add -l` in kitty; a git push from Zed shows the passphrase dialog once).

#### 6.6 System tools: Activity and restarts (P2, `system-tools`)

- **Activity**: `bind=CTRL+SHIFT,Escape,spawn,arctic-open terminal --app-id
  org.arcticlinux.TerminalApp.Float.Activity -e btop` (9.1). btop is themed
  (`dotfiles/.config/btop`) and recommended (spec:482); without it the terminal says so.
- **`dotfiles/.local/bin/arctic-restart`** (bash): `arctic-restart sound|wifi|bluetooth|shell
  [--json]`:
  - `sound`: `systemctl --user restart pipewire.service pipewire-pulse.service wireplumber.service`;
  - `wifi`: `nmcli radio wifi off`, 1 s, `nmcli radio wifi on` (NetworkManager allows the active
    user);
  - `bluetooth`: `systemctl restart bluetooth.service` (systemd's polkit, `auth_admin_keep`);
  - `shell`: `arctic-shell --restart`.
  Each ends with the OSD message ("Sound restarted") or, for `shell`, a notification. The usage
  text says it restarts part of the desktop, not the computer (`arctic-power restart` does that).
- **Settings → About**: new group "If something stops working" after "Help and feedback"
  (115-150): buttons "Restart sound", "Restart Wi-Fi", "Restart Bluetooth", "Restart the desktop
  shell" (`about.troubleshoot`, words "fix broken no sound wifi bluetooth restart reset"),
  `arctic_system.py` `troubleshoot NAME` → `arctic-restart NAME --json`.
- **Computer name** (About, "Computer name", 110): becomes editable ("Change…" → an `ArDialog`
  with a field; `hostname-set NAME` → `hostnamectl set-hostname NAME`, RFC 1123 label ≤ 63
  characters); desc "Other computers on the network see it as arctic.local."
- The command menu and launcher (other sections) may list `arctic-restart` entries; the
  commands are stable.
- Tests: `shell/tests/test_restart.py` runs `arctic-restart --json` with fake `systemctl`/`nmcli`
  and checks argv; hostname validation in `test_arctic_system.py`.

---

### 7. Updates

#### 7.1 Flathub apps and firmware (P1, `unified-updates`)

**7.1.1 Flatpak: timers.** Flatpak updates are safe while apps run (the new version starts next
time), so they are applied daily rather than staged for a restart.

- System installation (the Get apps default for wheel users, Get apps section 6.9): new
  `packaging/systemd/arctic-flatpak-update.service` and `.timer` (arctic-desktop-config):

```ini
[Unit]
Description=Arctic Linux: update Flatpak apps
Documentation=https://github.com/yuvalkolodkingal/Arctic-Linux/wiki/Updates
ConditionKernelCommandLine=!rd.live.image
ConditionPathExists=/var/lib/flatpak/repo
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/arctic-update flatpak --system --if-auto
Nice=19
IOSchedulingClass=idle
TimeoutStartSec=2h
```

  Timer: `OnBootSec=15min`, `OnCalendar=daily`, `RandomizedDelaySec=1h`, `Persistent=true`,
  `WantedBy=timers.target`.
- Per-user installations (non-wheel users, Get apps' `--user` path): the same pair as user units
  in `packaging/systemd/user/` → `/usr/lib/systemd/user/`, `ExecStart=/usr/bin/arctic-update
  flatpak --user --if-auto`, `ConditionPathExists=%h/.local/share/flatpak/repo`.
- Presets: `80-arctic.preset` `enable arctic-flatpak-update.timer`; `80-arctic-user.preset`
  `enable arctic-flatpak-update.timer` (its `enable arctic-*.service` line doesn't match timers).
  Existing systems get them once from arctic-desktop-config `%posttrans` (marker
  `/var/lib/arctic/.flatpak-update-presets`: `systemctl --no-reload preset
  arctic-flatpak-update.timer` and `systemctl --global preset arctic-flatpak-update.timer`), as
  `.update-presets` does (spec:951-957). `iso/kiwi/config.sh` (after 65-66): `systemctl enable
  arctic-flatpak-update.timer fwupd-refresh.timer || :` and `systemctl --global enable
  arctic-flatpak-update.timer gcr-ssh-agent.socket || :`.

**7.1.2 `arctic-update flatpak`** (new subcommand, `dotfiles/.local/bin/arctic-update`, usage at
3-12 and 58-76):

```
arctic-update flatpak [--system|--user] [--if-auto]   update Flatpak apps now
arctic-update flatpak-auto [on|off]                   FLATPAK= in /etc/arctic/update.conf
```

- `--if-auto`: does nothing when `FLATPAK=off`; skips a metered connection unless
  `METERED=allow` and an offline one (`connection_metered`/`connection_offline`, 155-157), like
  the daily check.
- Runs `flatpak update --<installation> --noninteractive -y`, then `flatpak uninstall
  --<installation> --unused --noninteractive -y` (explicitly installed runtimes are pinned).
- Records: system → `status_set flatpak_checked_at=@now flatpak_updated=N "flatpak_message=…"`
  (the root status file); user → `~/.local/state/arctic/flatpak-update.json` with the same keys.
  N comes from counting `Updating` lines 🔍 16.2 #23 (the exact `--noninteractive` output of
  flatpak 1.18.2); a failure keeps the last error sentence.
- `update.conf` gains, documented like `METERED`: `FLATPAK=auto` (`auto`: update Flatpak apps
  daily; `off`: don't). `arctic-update-helper`: `DEFAULTS["FLATPAK"]="auto"`, aliases like `AUTO`
  (`on`→`auto`), `config` prints `flatpak=…`, `STATUS_TYPES` gains `flatpak_updated: int`.
- `status --json` (`build_report`, helper 498-546) adds
  `"flatpak":{"auto":"auto","checked_at":"…","updated":3,"message":""}`.

**7.1.3 Firmware.** fwupd 2.1.8 (F44 ✅, in `@core`; arctic-desktop now lists it). Its metadata
timer `fwupd-refresh.timer` is disabled by `99-default-disable.preset`; `80-arctic.preset` gains
`enable fwupd-refresh.timer`, and existing systems get it once through the same marker as 7.1.1.
- `arctic_system.py` `updates` (wrapping `cmd_updates`, 2333-2350) adds
  `"firmware":{"supported":true,"devices":[{"id":"…","name":"System Firmware","vendor":"Framework","current":"3.05","update":"3.08","needs_restart":true,"summary":"…"}]}`
  from `fwupdmgr get-devices --json` (any device with the `updatable` flag → `supported`) and
  `fwupdmgr get-updates --json` (run as the user; its "nothing to do" exit code 2 is not an
  error) 🔍 16.2 #24 (the JSON field names and exit codes of fwupd 2.1.8).
- `update-run firmware` opens the terminal job `fwupdmgr update` (3.4); fwupdmgr asks polkit
  itself and asks before restarting.
- `shell/UpdateService.qml` (shared edit): once 5 minutes after start and then every 24 h, runs
  `fwupdmgr get-updates --json`; one notification per device and version (key cached in
  `~/.cache/arctic/firmware-notified`): "A firmware update is ready" / "System Firmware 3.08 for
  your Framework Laptop. Install it from Settings → Updates." with action "Open Settings"
  (`arctic-settings updates`). Not in the live session.

**7.1.4 Settings → Updates.** Page comment and groups (53-132):
- "Status" keeps the system rows; new group "Apps from Flathub": "Update Flathub apps
  automatically" `ArToggle` (`update-run flatpak-auto on|off` → `arctic-update flatpak-auto`,
  pkexec as for `auto`), desc "Every day, in the background. Apps you have open update the next
  time you start them." and the last result ("Updated 3 apps this morning."), button "Update now"
  (`update-run flatpak` → `arctic-update flatpak --system` and, when the user has a user
  installation, `--user`; detached, like `now`).
- New group "Firmware" (only when `supported`): one row per update ("System Firmware · 3.05 →
  3.08 · restarts the computer"), button "Install" (terminal); "Your firmware is up to date." when
  none.
- Search: `updates.flatpak` "Update Flathub apps automatically" (words "flatpak flathub apps zen
  zed"), `updates.firmware` "Firmware" (words "bios uefi fwupd lvfs dock ssd").
- `docs/wiki/Updates.md` "Flatpak and Nix apps" (232-239) is rewritten (Flatpak apps update
  daily; Nix stays manual, 17).

**7.1.5 Tests.** `packaging/updates/test_arctic_update.py`: `flatpak` with a fake `flatpak` on
`PATH` (success, failure, metered skip, `FLATPAK=off`), `flatpak-auto` editing `update.conf`
with its comments kept, the new report fields. `ci.yml` `units` job verifies the four new units.
`settings/tests/test_arctic_system.py`: fwupdmgr fixtures (no devices, updatable device with and
without an update, exit code 2).

#### 7.2 Snapshots in Settings (P2, `snapshots-ui`)

- **Listing** needs root (2.3). Settings → Updates gets a group "Snapshots" (`updates.snapshots`,
  words "undo rollback restore snapper btrfs"), collapsed behind a button "Show snapshots" whose
  desc says "Asks for your password: snapshots hold the whole system." It calls `snapshots` →
  `pkexec … arctic-system-helper snapshots`.
- The helper parses `snapper --no-dbus --jsonout -c root list` 🔍 16.2 #25 (the key names in
  snapper 0.13.0; the parser accepts `pre-number`/`pre_number`) and pairs pre and post snapshots:

```json
{"ok":true,"config":true,
 "pairs":[{"pre":41,"post":42,"date":"2026-09-27T10:12:03+03:00","command":"dnf5 install -y gimp","kind":"install","title":"Installed gimp"},
          {"pre":39,"post":40,"date":"2026-09-26T07:02:11+03:00","command":"dnf5 upgrade --offline -y --refresh","kind":"update","title":"System update"}],
 "singles":[{"number":43,"date":"…","title":"Taken from Settings"}]}
```

  `title` comes from the recorded dnf command (`snapper.actions` stores it as the description):
  `upgrade`/`distro-sync`/offline → "System update", `install NAME…` → "Installed NAME",
  `remove` → "Removed NAME", `system-upgrade` → "Fedora upgrade", anything else → the command.
  No package count: `snapper status PRE..POST` is too slow to run for every row.
- **Rows**: "System update · 26 Sep 07:02" with "Undo". Undo opens a confirmation (`ArDialog`):
  "Undo “Installed gimp”?" / "Files it changed go back to how they were on 27 September at 10:12.
  Your home folder isn't touched. Restart afterwards." / "Undo" (primary) and "Cancel". Then the
  terminal job `snapshot-undo 41 42` (3.4), which ends with "Done. Restart to finish:
  arctic-power restart".
- "Take a snapshot now" → `snapshot-create "Taken from Settings"` (quick; a toast "Snapshot 44
  taken").
- Without snapper's root configuration (0.1 installs, the live USB): the group says "Snapshots
  aren't set up on this system." and links the wiki (`docs/wiki/Updates.md:224-230`).
- Btrfs Assistant, when installed, gets a row "Browse snapshots in Btrfs Assistant".
- Booting into a snapshot stays out (17).
- Tests: `shell/tests/test_system_helper.py` pairs and titles from a snapper JSON fixture, and
  refuses an undo of numbers that aren't a listed pair.

#### 7.3 The next Fedora release, and What's new (P2, `fedora-upgrade-whats-new`)

**7.3.1 Offering the upgrade.** Arctic publishes a new tree only once the Fedora release is GA
and CI passes (`docs/PLAN.md` §10; `docs/BUILD-SPEC.md:647-653`), so its presence is the signal.

```
arctic-update upgrade check [--json]   {"ok":true,"available":true,"current":44,"next":45,"notes":"https://github.com/yuvalkolodkingal/Arctic-Linux/wiki/Release-Notes"}
arctic-update upgrade download         dnf5 system-upgrade download --releasever=<next> -y   (root; run in a terminal)
arctic-update upgrade cancel           dnf5 offline clean, only for Arctic's own upgrade transaction
arctic-update apply                    also installs a downloaded upgrade (dnf5 offline reboot)
```

- `check` runs as the user: `curl -fsI --max-time 20` on the `arctic` repository's `baseurl`
  from `/usr/share/dnf5/repos.d/arctic.repo` with `$releasever` = current + 1 and `$basearch`,
  plus `repodata/repomd.xml`. The channel's file is used when testing is on.
- `download` (as root: `as_root`, 96-104) → `dnf5 system-upgrade download --releasever=N -y`;
  snapper's actions take the pre/post snapshot around it automatically ✅.
- **The helper's ownership rule** (195-204): `owner()` gains a third class, `ours-upgrade`, when
  `cmd_line` is Arctic's upgrade command (`OUR_UPGRADE = "dnf5 system-upgrade download
  --releasever={N} -y"` 🔍 16.2 #26: the exact line dnf5 records) and `target_releasever ==
  system_releasever + 1`. `held()` is false for it; `build_report` returns
  `state:"ready","upgrade":{"to":45}` and the ready message "Fedora 45 is downloaded. Restart to
  upgrade: installing takes a while, and the computer restarts again at the end." The daily `stage` leaves an `ours-upgrade` transaction alone
  (as it leaves a foreign one) and records `upgrade_to=45`.
- **Settings → Updates**: when `check` answers `available`, a row at the top of "Status":
  "Fedora 45 is ready for Arctic Linux" / "Downloads a few gigabytes in a terminal window, then
  installs at a restart. A snapshot is taken first." / buttons "Release notes" (xdg-open) and "Upgrade…" (terminal job
  `arctic-update upgrade download`). While a downloaded upgrade waits: "Restart to upgrade to
  Fedora 45" with "Restart and upgrade" and "Cancel the upgrade".
- **Bar**: `shell/UpdateStatus.js` (shared file; pure functions tested by
  `shell/tests/test-update-status.cjs`) gains the `upgrade` field: `summary()` → "Restart to
  upgrade", `detail()` → "Fedora 45 is downloaded", `notification()` accordingly.
- Tests: `packaging/updates/test_arctic_update.py` with fake state files: an `ours-upgrade`
  transaction is ready and not held; a foreign `system-upgrade` is still held; `stage` doesn't
  replace it; `check` against a local HTTP server fixture (`python3 -m http.server` in the test)
  for 200 and 404. `packaging/updates/test-dnf5-offline.sh` (the real-dnf5 CI job) gains a
  `system-upgrade download` case against a local repository with `--releasever` + 1 🔍 whether
  that runs in the container (16.2 #26).

**7.3.2 What's new after an Arctic update.**
- New `packaging/release/whats-new.json` → `/usr/share/arctic/whats-new.json` (arctic-release),
  hand-written per release:

```json
{"version":"0.3","title":"What’s new in Arctic Linux 0.3",
 "items":[{"icon":"package","title":"Get apps","text":"Flathub, Fedora packages and web apps, each with search. Remove apps from the same place."},
          {"icon":"sliders","title":"Menus on the bar","text":"Wi-Fi, Bluetooth, sound, battery and a calendar open right under the bar. Super + A opens Quick settings."},
          {"icon":"night-light","title":"Night light","text":"Warmer colours in the evening: Super + Ctrl + N, or Settings → Displays."}],
 "notes_url":"https://github.com/yuvalkolodkingal/Arctic-Linux/wiki/Release-Notes"}
```

- New `shell/WhatsNew.qml`: a card like `LiveWelcome.qml` (frosted, `radiusXl`, centred), shown
  once at shell start when `/usr/lib/os-release` `VERSION_ID` is newer than
  `~/.local/state/arctic/whats-new-seen`. A missing file (a fresh install) records the version
  and shows nothing (the first-login welcome, another section, covers new installs). Items: icon
  tile, title (15/600), text (13 `inkMuted`); buttons "Read the release notes" (secondary →
  xdg-open) and "Got it" (primary). Enter = Got it, Esc = close; both record the version. IPC
  `whatsnew open()`; not in the live session.
- `%check` (spec:792-897) fails when `whats-new.json`'s `version` isn't `%{arctic_version}`.
- Tests: `shell/tests/test-whats-new.cjs` for `WhatsNewCore.js` (version comparison "0.10" >
  "0.9", missing file, same version).

---

### 8. Hardware and the local network

#### 8.1 Printing (P1, `printing`) and scanning (missed gap, P2)

**8.1.1 Packages** (all F44 ✅). arctic-desktop:
- `Requires: cups` (2.4.16), `cups-filters` (needs libcupsfilters, which requires ghostscript),
  `cups-pk-helper` (lets system-config-printer administer queues through polkit), `ipp-usb`
  (driverless USB printers and scanners), `avahi` and `nss-mdns` (finding network printers and
  `*.local` names). nss-mdns's `%posttrans` runs `authselect enable-feature with-mdns4` ✅.
- `Recommends: system-config-printer` ("Print Settings", for adding and configuring queues),
  `sane-airscan` (driverless eSCL/WSD scanners), `simple-scan` ("Document Scanner").
- Not added: `cups-browsed`. CUPS 2.4 creates temporary queues for driverless (IPP Everywhere,
  AirPrint) printers it finds through Avahi, so GTK and Qt print dialogs list network printers
  without it; cups-browsed adds a daemon that creates permanent queues for everything on the
  network, which Arctic doesn't want by default.
- `cups.socket` and `cups.path` are enabled by `90-default.preset:58-61` ✅; `avahi-daemon` by
  `:55` ✅. Updated systems get them through the packages' own `%systemd_post` presets on first
  install.
- `iso/kiwi/config.kiwi:182-183`: delete `<ignore name="ghostscript"/>` and reword the comment
  to cover only `cpp`. 🔍 16.2 #27: the ISO stays under 2 GiB (`docs/PLAN.md:336`); measure with
  `tools/build-iso.sh` before and after.
- Mango: `rules.conf` float rule `windowrule=isfloating:1,width:760,height:520,appid:^system-config-printer$`
  🔍 the app id (16.2 #28).

**8.1.2 Network discovery through the firewall.** Arctic's default zone is `public` (2.3), which
doesn't allow `mdns`, so Avahi can't hear printers' announcements 🔍 16.2 #29 (a network printer
shows up with and without the allow). The image allows it: `iso/kiwi/config.sh` (services block,
55-66) `firewall-offline-cmd --zone=public --add-service=mdns || :`; existing systems once from
arctic-desktop-config `%posttrans` (marker `/var/lib/arctic/.firewall-mdns`): if firewalld is
running, `firewall-cmd --permanent --zone="$(firewall-cmd --get-default-zone)" --add-service=mdns`
and `firewall-cmd --reload`, else `firewall-offline-cmd --add-service=mdns`. Settings → Sharing
shows it as a switch (8.3), so it can be turned off.

**8.1.3 New page `settings/pages/PrintersPage.qml`** (id `printers`, "Printers and scanners",
`printer`):

| Group | Rows |
|---|---|
| Printers | one row per queue: name (the queue's description), state tag (`ArTag`: Ready / Printing / Stopped, the last in `error`), "Default" tag; actions: "Make default", "Print a test page", "Settings" (opens Print Settings on it). Empty: "No printers yet." |
| Found on the network | driverless printers CUPS found but hasn't added: "These already work from any app's Print dialog." |
| Add a printer | button "Add a printer" → `system-config-printer` (missing: "Install Print Settings" → `arctic-shell-ipc apps search dnf system-config-printer`) |
| Print jobs | one row per job: title, printer, size; "Cancel" |
| Scanners | "Scan a document" → `simple-scan` (missing: install row as above). Desc: "USB and network scanners that support driverless scanning are found by themselves." |

`arctic_system.py` (every command with `LC_ALL=C`):
- `printers` → `lpstat -r` (scheduler running), `lpstat -d`, `lpstat -l -p` (queues, state,
  alerts), `lpstat -e` (all destinations; those not in `-p` are "found on the network"), `lpstat
  -v` (URIs), `lpstat -o` (jobs):

```json
{"ok":true,"cups":true,"running":true,
 "printers":[{"name":"HP_OfficeJet","info":"HP OfficeJet Pro 9010","state":"idle","message":"","default":true,"uri":"ipp://hp.local/ipp/print"}],
 "discovered":[{"name":"Brother_HL_L2350DW","info":"Brother HL-L2350DW"}],
 "jobs":[{"id":"HP_OfficeJet-42","printer":"HP_OfficeJet","title":"report.pdf","user":"yuval","size":123456,"mine":true}],
 "tools":{"system_config_printer":true,"simple_scan":true}}
```

- `printer-default NAME` → `lpoptions -d NAME` (the user's default; no root).
- `printer-test NAME` → `lp -d NAME /usr/share/cups/data/testprint` 🔍 the path in F44's
  cups/cups-filters (16.2 #28).
- `printer-cancel JOB` → `cancel JOB` (own jobs; others' need root and are shown without Cancel).
- `printer-settings [NAME]`, `scan` → start the tools detached.
- `TOOLS` (2519-2524): `lpstat`, `systemConfigPrinter: 'system-config-printer'`, `simpleScan:
  'simple-scan'`.
- No bar item for print jobs (17).
- Search: `printers.list` "Printers" (words "printer print cups paper ink toner"),
  `printers.add` "Add a printer", `printers.jobs` "Print jobs" (words "queue cancel stuck"),
  `printers.scan` "Scan a document" (words "scanner scan sane airscan").

**8.1.4 Tests.** `settings/tests/test_arctic_system.py` with `lpstat` fixtures captured from CUPS
2.4.16 on F44 🔍 (16.2 #28): no printers, one USB + one discovered, a stopped queue with an
alert, jobs of two users, the scheduler stopped. The headless smoke test uses a stand-in `lpstat`.

#### 8.2 Drives, phones, cameras and network shares (P1, `removable-drives`; missed gap: gvfs backends)

**8.2.1 Approach.** No udiskie: `shell/scripts/drives.py` uses Gio's volume monitor (the one
Thunar and GTK file dialogs use), which already knows which volumes should mount by themselves
(`g_volume_should_automount`, from udisks2's `HintAuto`/`HintIgnore`/`HintSystem`) and also lists
MTP phones, iPhones (AFC) and cameras (gPhoto2) from the gvfs backends. One process gives the bar
list, automount, notifications and eject.

**8.2.2 Packages.** arctic-shell: `Requires: gvfs` (the udisks2 volume monitor; Thunar pulled it
in until now, and the installer may remove Thunar) and `python3-gobject-base` (also added by the
bar-menus section). arctic-desktop: `Recommends: gvfs-mtp, gvfs-gphoto2, gvfs-afc, gvfs-smb`
(F44 ✅; gvfs-afc brings usbmuxd and libimobiledevice ✅). Thunar Requires only `gvfs` ✅, which
is why plugging in a phone shows nothing today. Network shares need gvfs-smb and Avahi (8.1).

**8.2.3 `shell/scripts/drives.py`** (python3 + `gi.repository.Gio/GLib`):

```
drives.py watch [--automount] [--notify-initial]   JSON lines (below)
drives.py list | mount ID | unmount ID | eject ID  one JSON line
```

- Listed: volumes and mounts that are removable, ejectable or come from the MTP, AFC or gPhoto2
  monitors; internal disks' partitions are not.
- IDs: the volume's `unix-device` identifier, else its UUID, else the activation root URI.
- `watch` lines:

```json
{"type":"drives","drives":[{"id":"/dev/sdb1","name":"Photos","kind":"usb","mounted":true,"path":"/run/media/yuval/Photos","size":31914983424,"free":12884901888,"can_eject":true,"encrypted":false}]}
{"type":"mounted","id":"/dev/sdb1","name":"Photos","path":"/run/media/yuval/Photos","automatic":true}
{"type":"ejected","id":"/dev/sdb1","name":"Photos"}
{"type":"error","id":"/dev/sdb1","code":"busy","error":"Something is still using “Photos”. Close the files and windows open on it, then eject it again."}
```

  `kind`: `usb`, `sd`, `optical`, `phone`, `camera`, `disk`.
- Automount (`--automount`): only for volumes added after `watch` started (a shell restart
  doesn't remount a drive you unmounted), only when `should_automount()` is true, never for
  encrypted volumes (they get `{"type":"locked",…}` and the notification "Encrypted drive
  “Backup” — open it in Files to unlock it").
- `eject` uses `g_mount_eject_with_operation` / `g_drive_eject_with_operation` (unmounts and powers
  the USB device off), `unmount` only unmounts.

**8.2.4 Shell.**
- New singleton `shell/DrivesService.qml`: runs `drives.py watch` (with `--automount` unless
  `Session.settings.automount === false`; restarted when the setting changes), keeps `drives`,
  sends notifications through the shell's notification server (bar-menus 5.4) or `notify-send -A`:
  - mounted: `usb` icon, "“Photos” is ready" / "Eject it from the bar before you unplug it."
    Actions "Open" (`xdg-open PATH`) and "Eject". Off when `automount_notify` is false.
  - ejected: "You can unplug “Photos”".
  - errors: the sentence from the helper.
- New `shell/DrivesItem.qml` in the bar's right group before the tray (`Bar.qml` 149-177, shared
  edit): the `usb` icon, visible while a drive is mounted or a phone/camera volume exists; tooltip
  "Photos · Pixel 8"; left click → `togglePanel('drives')`; `hasMenu: true`.
- New `shell/DrivesPanel.qml` (panel `drives`, width 320): header "Drives"; a `MenuRow` per drive
  (icon by kind; name; detail "12 GB free of 32 GB" / "Phone · open it in Files" / "Not opened")
  with a trailing icon button `eject` ("Eject Photos", focusable with Tab); Enter opens (mounting
  first when needed), the actions page (Menu key) has "Open", "Eject", "Unmount only". Footer:
  "Files" (`arctic-open files`) and "Disks" when gnome-disks is installed.
- IPC `drives open()`, `drives eject(id: string)`.

**8.2.5 Settings → Default apps.** New group "Drives and phones" after the existing one (17-68):
"Open drives when you plug them in" (`ArToggle`, `shell-set automount true|false`, desc "They
appear in Files and on the bar. Encrypted drives open in Files, where you type their
passphrase."), "Tell me when a drive is ready" (`automount_notify`). Search: `apps.drives`
"Drives and phones" (words "usb stick sd card automount mount eject phone android iphone camera
mtp").

**8.2.6 Waybar session**: nothing changes (Thunar mounts on click); the wiki says so.

**8.2.7 Tests.** `shell/tests/test_drives.py`: the pure parts (row building from plain dicts that
stand in for Gio objects, kind detection, sizes, the automount decision table:
initial/added × should_automount × encrypted × setting). 16.2 #30 (USB stick, SD card, Android
phone in file-transfer mode, iPhone after "Trust", a camera, an SMB share from Thunar's "Browse
Network").

#### 8.3 Firewall, remote login and the Sharing page (P2, `firewall-ssh`)

**8.3.1 New page `settings/pages/SharingPage.qml`** (id `sharing`, "Sharing", `send`):

| Group | Row | Does |
|---|---|---|
| This computer | "Name on the network" (read-only: `arctic.local`; "Change it in About") | — |
| This computer | "Firewall" (read-only: "On · public zone" / "Off"); button "Firewall settings" when `firewall-config` is installed | — |
| Nearby | "Find printers and devices on the network" (`sharing.mdns`) | helper `firewall-allow mdns on\|off` |
| Nearby | "Let LocalSend receive files" (`sharing.localsend`; shown when LocalSend is installed, else a row "Install LocalSend" → Get apps) | helper `firewall-allow localsend on\|off` |
| Nearby | "Let KDE Connect reach this computer" (`sharing.kdeconnect`; shown when kdeconnectd is installed) | helper `firewall-allow kdeconnect on\|off` |
| Remote login (hidden in the live session) | "Remote login (SSH)" `ArToggle` (`sharing.ssh`) | helper `ssh on\|off` |
| Remote login | "Allow password login" `ArToggle`, default off when SSH is turned on here | helper `ssh-password on\|off` |
| Remote login | "Connect with: `ssh yuval@arctic.local`", the host key fingerprint (`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`) | — |

- With password login off and no `~/.ssh/authorized_keys`, a warning banner: "Nobody can log in
  yet: add a public key to ~/.ssh/authorized_keys, or allow password login."
- Turning SSH on also runs `firewall-allow ssh on` (the `public` zone already allows it; another
  zone may not).
- `arctic_system.py` `sharing`:

```json
{"ok":true,"hostname":"arctic","mdns_name":"arctic.local","avahi":true,
 "firewall":{"running":true,"zone":"public","services":["ssh","dhcpv6-client","mdns"],"ports":["53317/tcp","53317/udp"],"readable":true},
 "allows":{"mdns":true,"localsend":true,"kdeconnect":false},
 "installed":{"localsend":true,"kdeconnect":false,"firewall_config":false},
 "ssh":{"installed":true,"enabled":false,"active":false,"password_login":true,"authorized_keys":false,"fingerprint":"SHA256:…"},
 "live":false}
```

  Firewall reads use `firewall-cmd --state`, `--get-default-zone`, `--zone=Z --list-services`,
  `--zone=Z --list-ports` (runtime queries; `org.fedoraproject.FirewallD1.info` is `yes` in both
  policies ✅). 🔍 16.2 #31: if a query still asks for a password with the server policy, the
  page shows `readable:false` ("Firewall details need your password") with a "Show" button that
  reads them through the root helper. SSH state: `systemctl is-enabled|is-active sshd.service`;
  password login = our drop-in is absent.
- Writes go through the root helper (3.3) so they share one prompt.
- Search: `sharing.firewall` "Firewall" (words "ports allow block security incoming"),
  `sharing.ssh` "Remote login (SSH)" (words "ssh sshd remote server login terminal"),
  `sharing.localsend` "LocalSend" (words "airdrop send files nearby"), `sharing.kdeconnect`
  "KDE Connect" (words "phone android gsconnect"), `sharing.mdns` "Find printers and devices"
  (words "mdns avahi bonjour discovery").

**8.3.2 Packages.** arctic-desktop: `Requires: firewalld` (already in `@core`; listed so it is
never left out), `Recommends: firewall-config`. openssh-server is in `@core` ✅ and stays disabled
by `80-arctic.preset:41-45`.

**8.3.3 Tests.** `shell/tests/test_system_helper.py`: every `firewall-allow` argv (runtime and
permanent, default zone), the sshd drop-in contents and `sshd -t` failure path, refusals.
`settings/tests/test_arctic_system.py`: `firewall-cmd` output fixtures, the banner logic.
16.2 #31, #32.

#### 8.4 Share menu (LocalSend) and KDE Connect (P2, `share-localsend-kdeconnect`)

**8.4.1 `dotfiles/.local/bin/arctic-share`** (bash):

```
arctic-share clipboard | files PATH… | receive | menu | status [--json]
```

- LocalSend is the Flathub app `org.localsend.localsend_app` (`modules/sync/localsend/module.toml`),
  found with `flatpak info` (system or user), or a `localsend` binary.
- `files PATH…`: `flatpak run org.localsend.localsend_app --headless send PATH…` 🔍 16.2 #33
  (the Flathub build's headless mode and its access to the paths; Omarchy uses `localsend
  --headless send` ✅). Fallback: open LocalSend and notify "Pick the files in LocalSend."
- `clipboard`: `wl-paste` into `$XDG_DOWNLOAD_DIR/Clipboard <YYYY-MM-DD HH.MM>.txt` (or `.png` for
  an image type), then `files` with it.
- `receive`: open LocalSend.
- Not installed: a notification "LocalSend isn't installed" with an "Install" action →
  `arctic-shell-ipc apps search flatpak org.localsend.localsend_app`.
- `menu`: the shell's panel (`arctic-shell-ipc share menu`); without the shell, a fuzzel list.

**8.4.2 Shell.** New `shell/SharePanel.qml` (panel `share`, opened by `Super + Ctrl + S` under the
right end of the bar, no bar item): header "Share"; rows "Send the clipboard", "Send files…"
(opens LocalSend), "Receive files", and, with KDE Connect installed, "Phone (KDE Connect)" →
`kdeconnect-app`. Without LocalSend: one row "Install LocalSend" with desc "Send files to phones
and computers nearby." Footer "Sharing settings" (`arctic-settings sharing`). IPC `share menu()`.

**8.4.3 Thunar.** New `dotfiles/.config/Thunar/uca.xml` (skel): Thunar's own "Open Terminal
Here" action, with `arctic-open terminal` as the command, plus "Send with LocalSend" (`arctic-share
files %F`, for files and folders). A user file replaces Thunar's system one entirely, so both
actions are in it; existing homes are not changed (the wiki shows how to add the action).

**8.4.4 KDE Connect.** New catalog module `modules/sync/kdeconnect/module.toml` (dnf
`kde-connect`, which brings `kdeconnectd` ✅; category `sync`, default false, `in_live_image =
false`, `icon = "phone"`, summary "Your phone's notifications, files and clipboard on the
computer."), appended to the `sync` category's `modules` (`modules/catalog.toml:185`).
`TestTileAssets` (`internal/catalog/catalog_test.go:121-146`) requires
`installer-ui/assets/tiles/kdeconnect-{light,dark}.svg` and an `APPS` entry `"kdeconnect"` in
`installer-ui/assets/Icons.js`; that file comes from the design bundle, so the tile goes into the
bundle first and is exported (16.1), and `settings/assets/tiles/` gets the same two files.
`kdeconnectd` starts through XDG autostart (6.1, `org.kde.kdeconnect.daemon.desktop` ✅) and its
tray icon shows on the bar. The firewall allow is on the Sharing page.

**8.4.5 Tests.** `shell/tests/test_share.py` runs `arctic-share --dry-run` (prints argv) for each
command with fake `flatpak`/`wl-paste`; the catalog's Go tests cover the new module and tiles.

---

### 9. Keyboard behaviour

#### 9.1 Global keys (`dotfiles/.config/mango/arctic/binds.conf`)

New lines at the end of "Launch" (13-23), and a new "Laptop lid" block after "Hardware keys" (86-95):

```
# ---- Launch -------------------------------------------------------------
bind=SUPER+CTRL,n,spawn,arctic-nightlight toggle
bind=SUPER+CTRL,i,spawn,arctic-awake toggle
bind=SUPER+CTRL,s,spawn,arctic-share menu
bind=SUPER,p,spawn,arctic-display menu
bind=CTRL+SHIFT,Escape,spawn,arctic-open terminal --app-id org.arcticlinux.TerminalApp.Float.Activity -e btop
# The laptop's display key (Fn + a function key on many laptops) opens the same menu.
bind=NONE,XF86Display,spawn,arctic-display menu

# ---- Laptop lid ---------------------------------------------------------
switchbind=fold,spawn,arctic-display lid closed
switchbind=unfold,spawn,arctic-display lid open
```

`XF86Display` uses `bind`, not `bindl`: the menu can't be used on the lock screen. The lid
bindings work while locked (Mango's switch handler doesn't check the lock, `switch.c:21-29`) ✅.

| Key | Action | Clash check (every bind in `binds.conf`, `apps.conf` and the other 0.3.0 sections' plans) |
|---|---|---|
| `Super + Ctrl + N` | night light on/off | only `Super + Ctrl + ←→↑↓` are bound (45-48); the bar-menus keys are `Super + Ctrl + W/B/A/P/D/T/M`; emoji `Super + Ctrl + E`, capture `Super + Ctrl + C`, reminders `Super + Ctrl + R` are other letters |
| `Super + Ctrl + I` | keep awake on/off | free |
| `Super + Ctrl + S` | share menu | free (reserved for share in the bar-menus plan's table) |
| `Super + P` | display mode menu (again: next row) | free; `Super + Ctrl + P` is the battery menu (bar-menus) |
| `XF86Display` | display mode menu | free; many laptops send `Super + P` for their display key anyway |
| `Ctrl + Shift + Esc` | Activity (btop, floating) | free; clashes with the layout switch only when Settings' "Switch layouts with" is `grp:ctrl_shift_toggle` (`arctic_settings.py:2053`): Ctrl+Shift then also flips the layout |
| lid `fold` / `unfold` | `arctic-display lid closed/open` | no `switchbind` exists; a user's own lid binding is shadowed (first wins) |

- None of these holds Alt and Shift together, so `grp:alt_shift_toggle` (the installer default,
  `internal/wizard/locale.go:153`) and `grp:lalt_lshift_toggle` never fire with them; none holds
  Alt + Space (`grp:alt_space_toggle`) or Caps Lock (`grp:caps_toggle`, `grp:alt_caps_toggle`);
  `grp:toggle` (Right Alt) and `grp:shifts_toggle` don't involve them.
- `Ctrl + Shift + Esc` and `grp:ctrl_shift_toggle`: the shortcuts section's collision check (D7)
  reports it; `docs/wiki/Keyboard-Shortcuts.md` says so under "Changing a shortcut".
- The collision check also reads `switchbind` lines (only one per fold state is used).
- Omarchy uses `Super + Ctrl + N` (night light), `Super + Ctrl + I` (idle) and `Super + Ctrl + S`
  (share) ✅; Arctic keeps its Windows-style `Super + P` and `Ctrl + Shift + Esc` instead of
  Omarchy's `Super + Ctrl + Alt + Delete` (mirror) and `Super + Ctrl + T` (activity; Arctic's is
  the calendar).
- Fedora's fcitx5 trigger `Ctrl + Space` is not an Arctic bind.

#### 9.2 Inside the new menus, cards and pages

| Where | Keys |
|---|---|
| Display mode panel | Up/Down move; `Super + P` or the display key moves to the next row while open; Home/End first/last; Enter applies and closes; Esc closes without a change |
| Drives panel | Up/Down rows; Enter opens the drive (mounting first); Tab reaches the row's Eject button (Enter/Space ejects); Menu key or Shift+F10 opens the row's actions (Open, Eject, Unmount only); Esc closes |
| Share panel | Up/Down, Enter runs the row, Esc closes |
| Quick Settings sub-pages `awake`, `nightlight` | the bar-menus toolkit keys (its 8.2): Up/Down, Enter/Space picks a radio row, Left/Right on the warmth slider (−/+ 100 K; PgUp/PgDn ±500 K), Left or Esc goes back |
| Idle dim layer | none of its own: any key or pointer movement cancels it (the idle monitors see the activity) |
| What's new card | Enter = Got it, Esc closes, Tab moves between the two buttons |
| Power menu sheets ("still installing", "still open") | Enter = the primary button (Wait / Cancel), Tab to "Restart anyway", Esc = Cancel |
| Settings pages | the Settings conventions (`settings/Main.qml:1-3`): Tab through rows, Space/Enter on toggles and buttons, arrows in segmented controls and selects; the time-zone and startup lists filter as you type |

Every focusable control shows the focus ring only after a key press; focus ring colour is `focus`
(amber, the "here" use, D9).

#### 9.3 `dotfiles/.local/share/arctic/keys.txt`

"System" (36-45) gains, one entry per line (`parse_sheet`, `arctic_settings.py:869-882`, splits at
the first run of two spaces):

```
    Super + Ctrl + N         Night light
    Super + Ctrl + I         Keep awake
    Super + P                Screens: duplicate, extend or one screen
    Super + Ctrl + S         Share with LocalSend
    Ctrl + Shift + Esc       Activity (what's running)
```

If the generated-keys-sheet work replaces `keys.txt` with text from `binds.conf`, these become the
bind comments.

---

### 10. File-by-file changes

#### 10.1 New files

| File | Package | What |
|---|---|---|
| `dotfiles/.local/bin/arctic-nightlight` | arctic-desktop-config | 5.1.5 |
| `dotfiles/.local/bin/arctic-awake` | arctic-desktop-config | 4.1.3 |
| `dotfiles/.local/bin/arctic-display` | arctic-desktop-config | 5.2.1, 4.5.3 |
| `dotfiles/.local/bin/arctic-effects` | arctic-desktop-config | 5.3.2 |
| `dotfiles/.local/bin/arctic-gpu` | arctic-desktop-config | 5.4.2 |
| `dotfiles/.local/bin/arctic-share` | arctic-desktop-config | 8.4.1 |
| `dotfiles/.local/bin/arctic-restart` | arctic-desktop-config | 6.6 |
| `dotfiles/.config/Thunar/uca.xml` | arctic-desktop-config (skel) | 8.4.3 |
| `packaging/system/arctic-system-helper` | arctic-desktop-config → `/usr/libexec/arctic/` | 3.3 |
| `packaging/polkit/org.arcticlinux.system.policy` | arctic-desktop-config | 3.3 |
| `packaging/desktop/arctic-ssh-agent.sh` | arctic-desktop-config → `/etc/profile.d/` | 6.5 |
| `packaging/systemd/arctic-flatpak-update.service`, `.timer` | arctic-desktop-config | 7.1.1 |
| `packaging/systemd/user/arctic-flatpak-update.service`, `.timer` | arctic-desktop-config → `/usr/lib/systemd/user/` | 7.1.1 |
| `packaging/systemd/user/mango-session.target.d/arctic-autostart.conf` | arctic-desktop-config | 6.1.1 |
| `packaging/systemd/user/app-blueman@autostart.service.d/arctic.conf`, `packaging/systemd/user/app-nm\x2dapplet@autostart.service.d/arctic.conf` | arctic-desktop-config | 6.1.2 |
| `packaging/release/whats-new.json` | arctic-release → `/usr/share/arctic/whats-new.json` | 7.3.2 |
| `shell/IdleService.qml`, `shell/IdleCore.js` | arctic-shell | 4.1 |
| `shell/IdlePipeline.qml`, `shell/IdleDim.qml`, `shell/IdlePlan.js` | arctic-shell | 4.4 |
| `shell/NightLightService.qml` | arctic-shell | 5.1.7 |
| `shell/DisplayModePanel.qml`, `shell/DisplayModes.js` | arctic-shell | 5.2.2 |
| `shell/EffectsService.qml`, `shell/GameModeService.qml` | arctic-shell | 5.3 |
| `shell/GpuService.qml` | arctic-shell | 5.4.3 |
| `shell/ClockFormat.js` | arctic-shell | 6.2.2 |
| `shell/pam/arctic-lock-fingerprint` | arctic-shell | 6.3.2 |
| `shell/DrivesService.qml`, `shell/DrivesItem.qml`, `shell/DrivesPanel.qml`, `shell/scripts/drives.py` | arctic-shell | 8.2 |
| `shell/SharePanel.qml` | arctic-shell | 8.4.2 |
| `shell/WhatsNew.qml`, `shell/WhatsNewCore.js` | arctic-shell | 7.3.2 |
| `shell/scripts/screensaver-bridge.py` | arctic-shell | 4.1.4 |
| `settings/scripts/arctic_system.py` | arctic-settings | 3.1 |
| `settings/pages/DateTimePage.qml`, `UsersPage.qml`, `PrintersPage.qml`, `SharingPage.qml` | arctic-settings | 6.2, 6.3, 8.1, 8.3 |
| `modules/sync/kdeconnect/module.toml`, `installer-ui/assets/tiles/kdeconnect-{light,dark}.svg`, `settings/assets/tiles/kdeconnect-{light,dark}.svg` | arctic-installer / arctic-settings | 8.4.4 |
| Tests: `shell/tests/test_nightlight.py`, `test_display.py`, `test_effects.py`, `test_gpu.py`, `test_drives.py`, `test_share.py`, `test_restart.py`, `test_power_prepare.py`, `test_screensaver_bridge.py`, `test_system_helper.py`, `test-idle-plan.cjs`, `test-idle-service.cjs`, `test-display-modes.cjs`, `test-clock-format.cjs`, `test-whats-new.cjs`; `settings/tests/test_arctic_system.py`; fixtures under `shell/tests/fixtures/system/` and `settings/tests/fixtures/system/` | — | 12 |

#### 10.2 Changed files

| File | Change |
|---|---|
| `dotfiles/.local/bin/arctic-session` | usage (6, 65) and header; new `nightlight`, `lid [--restart]`, `display`, `effects`, `battery`, `fallback-only`; `idle` (40-64) reads the battery keys and runs the backstop in the shell session (4.4.5) |
| `dotfiles/.local/bin/arctic-power` | `prepare`, `hibernate`, `firmware`; fuzzel path runs `prepare` (4.6.2) |
| `dotfiles/.local/bin/arctic-update` | `flatpak`, `flatpak-auto`, `upgrade check\|download\|cancel`; `apply` handles an upgrade; usage (3-12, 58-76) |
| `dotfiles/.local/bin/arctic-shell-ipc` | usage list (6-8) adds `idle`, `nightlight`, `display`, `drives`, `share`, `whatsnew`, `osd message` |
| `dotfiles/.config/mango/config.conf` | `source-optional=~/.config/arctic/effects.conf` between 31 and 32; header (6-11) |
| `dotfiles/.config/mango/arctic/autostart.conf` | `exec-once=arctic-session effects` (before `shell`), `nightlight`, `lid`, `display`, `battery`; comment (1-8) |
| `dotfiles/.config/mango/arctic/binds.conf` | 9.1 |
| `dotfiles/.config/mango/arctic/look.conf` | `idleinhibit_when_fullscreen=1` in "Focus behaviour" (85-88) |
| `dotfiles/.config/mango/arctic/rules.conf` | 117: namespaces add `idle-dim`, `whatsnew`; float rules for `system-config-printer`, `org.fcitx.fcitx5-config-qt`; `at.yrlf.wl_mirror` no-blur rule |
| `dotfiles/.local/share/arctic/keys.txt` | 9.3 |
| `dotfiles/README.md` | helper table (57-85): the seven new helpers, `arctic-power` and `arctic-update` additions |
| `dotfiles/install.sh` | `PACKAGES` (36-41): wlsunset wl-mirror wlr-randr gvfs python3-gobject-base switcheroo-control |
| `packaging/updates/arctic-update-helper` | `FLATPAK` setting, `flatpak_*` and `upgrade_to` status keys, `ours-upgrade` owner class, report fields (7.1.2, 7.3.1) |
| `packaging/updates/update.conf` | `FLATPAK=auto` with its comment |
| `packaging/release/80-arctic.preset` | `enable arctic-flatpak-update.timer`, `enable fwupd-refresh.timer` |
| `packaging/release/80-arctic-user.preset` | `enable arctic-flatpak-update.timer`, `enable gcr-ssh-agent.socket` |
| `packaging/arctic-linux.spec` | 11.1 |
| `packaging/mangowm.spec` | `Inhibit=gtk` (4.1.4), `Release` bump, changelog |
| `iso/kiwi/config.kiwi` | 182-183: drop the ghostscript ignore |
| `iso/kiwi/config.sh` | services block (55-66): timers, user units, `mdns` firewall allow |
| `shell/shell.qml` | instances `IdlePipeline {}`, `IdleDim { id: idleDim }`, `WhatsNew { id: whatsNew }`; IPC targets (3.5); header comment (7-15); `closePopovers` includes `whatsNew` |
| `shell/qmldir` | the new singletons and types |
| `shell/Bar.qml` | `IdleInhibitor` (4.1.1), `DrivesItem` (8.2.4), clock text and middle click (6.2.2) |
| `shell/LockScreen.qml` | fingerprint `PamContext` (6.3.2), clock format (129) |
| `shell/PowerMenu.qml` | Hibernate, More → firmware setup, the prepare sheets (4.6) |
| `shell/Osd.qml` | `showMessage(icon, text)` when osd-kinds hasn't added it (3.5) |
| `shell/Session.qml` | `~/.face` watch; new `shell.json` keys exposed (`clockFormat`, `clockDate`, `weekStart`, `automount`, `automountNotify`, `lockFingerprint`) |
| `shell/Theme.qml` | durations and frost under lighter effects (5.3.3) |
| `shell/Launcher.qml` | GPU launch in `activate` (83-106), footer hint (5.4.3) |
| `shell/UpdateService.qml`, `shell/UpdateStatus.js`, `shell/UpdatePopover.qml` | firmware notification (7.1.3), upgrade state (7.3.1) |
| `shell/ToggleRegistry.qml`, `shell/BarMenu.qml`, `shell/QuickSettingsPanel.qml`, `shell/assets/icons-extra.js` (bar-menus files) | toggles, panels, sub-pages, icons (3.5, 3.8) |
| `shell/scripts/battery.py` (bar-menus) | `watch --notify` (4.2) |
| `shell/README.md` | IPC table (69-88) and the new pieces (35-53) |
| `settings/scripts/arctic_settings.py` | import `arctic_system`, merge `COMMANDS`/`WRITERS`; docstring (1-50) lists the new commands; `read_idle`/`cmd_idle`/`cmd_idle_set` (2002-2048: new keys; writes keep unknown lines); `TOOLS` (2519-2524) adds `wlsunset`, `lpstat`, `systemConfigPrinter`, `simpleScan`, `fwupdmgr`, `snapper`, `firewallCmd`, `switcherooctl`, `fcitx5`, `fprintd` |
| `settings/pages/DisplaysPage.qml` | "Night light" group (5.1.8) |
| `settings/pages/PowerPage.qml` | comment (1-3), idle rows (44-70), lid group (89-97) |
| `settings/pages/WindowsPage.qml` | "Effects" group and banner (5.3.5) |
| `settings/pages/InputPage.qml` | "Input method" group (6.4.2) |
| `settings/pages/AppsPage.qml` | "Drives and phones" group (8.2.5) |
| `settings/pages/StartupPage.qml` | comment, lede, XDG group (6.1.3) |
| `settings/pages/UpdatesPage.qml` | Flathub, firmware, snapshots, next Fedora (7.1.4, 7.2, 7.3.1) |
| `settings/pages/AboutPage.qml` | editable computer name, troubleshooting group (6.6) |
| `settings/pages/qmldir`, `settings/SearchIndex.js` | four pages; every search key named in 4–8 |
| `settings/assets/SettingsIcons.js` | `printer`, `night-light`, `fingerprint`, `history`, `screens` copies |
| `settings/dev/headless.sh` | `--fixtures` stand-ins: `timedatectl`, `localectl`, `lpstat`, `fwupdmgr`, `firewall-cmd`, `arctic-nightlight`, `switcherooctl` |
| `settings/README.md` | "What it changes" (39-76): the new files and the root helper |
| `modules/catalog.toml` | `sync` modules adds `kdeconnect` |
| `.github/workflows/ci.yml` | `units` (100-115): the new system and user units; `shellcheck` already covers `dotfiles/.local/bin/*` and `packaging/desktop/*.sh` (53-54) |

---

### 11. Packaging deltas

#### 11.1 `packaging/arctic-linux.spec`

**arctic-desktop-config** (157-220):
- `Requires: wlsunset`, `wl-mirror`, `wlr-randr` (arctic-display; arctic-settings already requires
  it), `glib2` (gdbus in the helpers), `systemd-udev` (udevadm, for `arctic-display watch`),
  `polkit` (pkexec for the root helper).
- `%install` (after 673-685):
  ```
  install -Dpm 0644 packaging/systemd/arctic-flatpak-update.service %{buildroot}%{_unitdir}/arctic-flatpak-update.service
  install -Dpm 0644 packaging/systemd/arctic-flatpak-update.timer %{buildroot}%{_unitdir}/arctic-flatpak-update.timer
  install -d %{buildroot}%{_userunitdir}
  cp -a packaging/systemd/user/. %{buildroot}%{_userunitdir}/
  install -Dpm 0755 packaging/system/arctic-system-helper %{buildroot}%{_libexecdir}/arctic/arctic-system-helper
  install -Dpm 0644 packaging/polkit/org.arcticlinux.system.policy %{buildroot}%{_datadir}/polkit-1/actions/org.arcticlinux.system.policy
  install -Dpm 0644 packaging/desktop/arctic-ssh-agent.sh %{buildroot}%{_sysconfdir}/profile.d/arctic-ssh-agent.sh
  ```
- `%files` (1082-1122): the two system units, `%{_userunitdir}/arctic-flatpak-update.service`,
  `%{_userunitdir}/arctic-flatpak-update.timer`, `%dir %{_userunitdir}/mango-session.target.d`,
  `%{_userunitdir}/mango-session.target.d/arctic-autostart.conf`,
  `%{_userunitdir}/app-*@autostart.service.d/`, `%{_libexecdir}/arctic/arctic-system-helper`,
  `%{_datadir}/polkit-1/actions/org.arcticlinux.system.policy`,
  `%{_sysconfdir}/profile.d/arctic-ssh-agent.sh`. The `arctic-*` helpers come in through the
  existing `desktop-config.files` list (702-703).
- `%post`/`%preun` (943-947): `%systemd_post arctic-flatpak-update.timer`, `%systemd_user_post
  arctic-flatpak-update.timer`, and the matching `%systemd_preun` / `%systemd_user_preun`.
- `%posttrans` (949-963): the one-time markers `.flatpak-update-presets` (7.1.1, including
  `fwupd-refresh.timer`), `.ssh-agent-preset` (6.5), `.firewall-mdns` (8.1.2).
- Description (222-237): night light, keep awake, display modes, lid, effects, Flatpak and
  firmware updates, the system helper.

**arctic-shell** (240-253): `Requires: gvfs`; `python3-gobject-base` and `python3-dbus` (also the
bar-menus section's). Description (254-257): idle, drives, display modes, what's new.

**arctic-settings** (260-287): no new Requires (Pillow comes with arctic-desktop-config); the
description's "nothing needs root" (286-287) becomes "Changes to the system (time zone, firewall,
snapshots, sign-in) ask for your password through polkit."

**arctic-release** (68-91, 568-572, 1030-1061): the preset lines (11.2); `install -Dpm 0644
packaging/release/whats-new.json %{buildroot}%{_datadir}/arctic/whats-new.json` and the file in
`%files`; description (84-91) mentions it.

**arctic-desktop** (402-482):
- Requires: `cups`, `cups-filters`, `cups-pk-helper`, `ipp-usb`, `avahi`, `nss-mdns`, `firewalld`,
  `fwupd`, `switcheroo-control`, `gcr`, `accountsservice`.
- Recommends: `system-config-printer`, `sane-airscan`, `simple-scan`, `gvfs-mtp`, `gvfs-gphoto2`,
  `gvfs-afc`, `gvfs-smb`, `fprintd`, `fprintd-pam`, `pam-u2f`, `pamu2fcfg`, `firewall-config`.
- The Get apps section computes its protected list from this closure (its 6.8), so the new
  Requires can't be removed from Get apps and the Recommends can.
- Description (484-487): printing, firmware, sharing.

**`%check`** (792-897): the loop at 825-832 already parses `/usr/libexec/arctic/*` (the root
helper) and bash-checks `/usr/bin/arctic-update`; add the new bash helpers to it
(`arctic-awake`, `arctic-effects`, `arctic-share`, `arctic-restart`) and `python3 -c 'import
ast…'` for `arctic-nightlight`, `arctic-display`, `arctic-gpu`; check that `whats-new.json` parses
and its `version` is `%{arctic_version}`; `mango -p` on the skel home (886-897) covers the new
`binds.conf`, `look.conf` and `config.conf` lines.

**Version**: `Version: 0.3.0` (36) and `%global arctic_version 0.3` (30) with the rest of the
release (D1); `packaging/release/os-release` follows.

#### 11.2 Presets

- `packaging/release/80-arctic.preset`: after the updates block (16-21) `enable
  arctic-flatpak-update.timer`, `enable fwupd-refresh.timer` with a comment each.
- `packaging/release/80-arctic-user.preset`: `enable arctic-flatpak-update.timer`, `enable
  gcr-ssh-agent.socket`; the comment (1-3, 55-58) explains that XDG autostart now runs.

#### 11.3 Image

- `iso/kiwi/config.kiwi:182-183`: ghostscript no longer ignored (8.1.1). `plusRecommended`
  (58) pulls in every new Recommends.
- `iso/kiwi/config.sh` (55-66): `systemctl enable arctic-flatpak-update.timer fwupd-refresh.timer ||
  :`, `systemctl --global enable arctic-flatpak-update.timer gcr-ssh-agent.socket || :`,
  `firewall-offline-cmd --zone=public --add-service=mdns || :`.
- 🔍 16.2 #27: the ISO size delta (CUPS stack, ghostscript, gvfs backends, fwupd, gcr).

#### 11.4 `packaging/mangowm.spec`

`%install`: the `sed` of 4.1.4 on `mango-portals.conf`; `%changelog` entry "Inhibit portal:
gtk (Arctic's shell answers org.freedesktop.ScreenSaver)"; `Release` rebuilt by the snapshot
macro as usual.

#### 11.5 Non-RPM install

`dotfiles/install.sh` `PACKAGES` (36-41) adds `wlsunset wl-mirror wlr-randr gvfs python3-gobject-base
switcheroo-control`; printing and the rest stay packaging-only.

---

### 12. Tests

#### 12.1 Python (standard library `unittest`; CI jobs already running these folders)

| File | Job (`ci.yml`) | Covers |
|---|---|---|
| `shell/tests/test_nightlight.py` | `shell-tests` (78-82) | config, zone1970.tab, sun times, wlsunset argv per state, toggle overrides across midnight and DST, status JSON (5.1.9) |
| `shell/tests/test_display.py` | `shell-tests` | modes → `mmsg`/`wl-mirror` calls, lid decisions incl. the tablet-mode false alarm, `watch` recovery (5.2.4, 4.5.6) |
| `shell/tests/test_effects.py` | `shell-tests` | state, generated `effects.conf`, source-line insertion, reload only on change (5.3.6) |
| `shell/tests/test_gpu.py` | `shell-tests` | `switcherooctl list` fixtures, `prefers` scan (5.4.4) |
| `shell/tests/test_drives.py` | `shell-tests` | rows, kinds, the automount decision table (8.2.7); Gio is not imported by the pure module |
| `shell/tests/test_share.py`, `test_restart.py`, `test_power_prepare.py` | `shell-tests` | argv with fake commands on `PATH` (8.4.5, 6.6, 4.6.4) |
| `shell/tests/test_screensaver_bridge.py` | `shell-tests` | the cookie table (4.1.5) |
| `shell/tests/test_system_helper.py` | `shell-tests` | every root-helper verb's argv, validation and refusals, snapper pairing (3.3, 7.2, 8.3.3) |
| `shell/tests/test_battery.py` (bar-menus) | `shell-tests` | the `--notify` case (4.2) |
| `settings/tests/test_arctic_system.py` | `shell-tests` (89-90) | every new Settings command with fixtures: idle keys, lid, XDG autostart, `timedatectl`/`localectl`, zones, users (`lsblk`, `fprintd-list`, `authselect`, avatar), IM, `lpstat`, `fwupdmgr`, `firewall-cmd`, sharing state, hostname |
| `packaging/updates/test_arctic_update.py` | `shell-tests` (87-88) | `flatpak`, `flatpak-auto`, `upgrade check`, `ours-upgrade` ownership, report fields (7.1.5, 7.3.1) |

Commands that need root or hardware are replaced by stand-ins on `PATH` in each test; the helpers
take `ARCTIC_*` overrides only for paths (`ARCTIC_SYSTEM_HELPER`, `ARCTIC_EFFECTS_DRI`,
`ARCTIC_SYSFS_ROOT`, `ARCTIC_ZONEINFO`), never when run as root by systemd (the
`ARCTIC_UPDATE_TEST_ROOT` rule, `arctic-update:24-33`).

#### 12.2 Node (`shell/tests/*.cjs`, `ci.yml:91-97`)

`test-idle-plan.cjs`, `test-idle-service.cjs`, `test-display-modes.cjs`, `test-clock-format.cjs`,
`test-whats-new.cjs`, plus new cases in `test-update-status.cjs` (the upgrade state).

#### 12.3 Static checks

- ShellCheck (`ci.yml:41-63`) covers the new bash helpers (`dotfiles/.local/bin/*`) and
  `packaging/desktop/arctic-ssh-agent.sh`.
- `units` job (100-115): `systemd-analyze verify` for `arctic-flatpak-update.service/.timer`
  (installing `arctic-update` first, as today) and, with `--user`, the user pair and a copy of
  `mango-session.target` plus the drop-in.
- qmllint job (130-149) picks up the new QML files.
- RPM job (186-208): the spec builds; `%check` runs the whats-new version check and `mango -p`.
- Go (`ci.yml:17-39`): `internal/catalog` tests with the `kdeconnect` module and tiles.

#### 12.4 Headless

`settings/dev/headless.sh --smoke --fixtures` opens every page, so the four new pages load with
the stand-ins added to `--fixtures` (10.2). Screenshots of each go to the CI artifact
(`settings-screenshots`), both themes.

#### 12.5 Hands-on

The 🔍 list in 16.2, run before the pull request is merged (D10) on: one Intel laptop, one AMD
laptop, one NVIDIA hybrid laptop, one desktop with two monitors, a QEMU VM (virtio-gpu and
simpledrm), a network printer with IPP Everywhere, a USB scanner or an eSCL network scanner, an
Android phone, an iPhone, a camera, and a laptop with a fingerprint reader.

---

### 13. Docs to update

| File | Change |
|---|---|
| `docs/wiki/Settings.md` | new sections Sharing, Printers and scanners, Date and time, Users and sign-in; Displays (129-172) night light; Windows (112-128) effects; Keyboard and mouse (173-184) input method; Default apps (197-206) drives; Updates (231-239); Power and lock (240-252) idle times, dim, screen off, lid; Startup apps (254-261); About (263-271) |
| `docs/wiki/Keyboard-Shortcuts.md` | System (62-76) the five keys; Hardware keys (78-88) the display key; a "Laptop lid" note; "Changing a shortcut" (152-) the `grp:ctrl_shift_toggle` clash and "if the screen goes black: Super + P, Home, Enter" |
| `docs/wiki/Updates.md` | "Flatpak and Nix apps" (232-239) rewritten; new "Firmware", "Undoing an update in Settings" (with the snapshot section, 195-230) and "Upgrading to the next Fedora" |
| `docs/wiki/Troubleshooting.md` | "Sound, Bluetooth or brightness" (307-316): the restart buttons; "The screen locks too soon, or the computer sleeps" (318-323): battery times, keep awake; new: "A printer isn't found", "A USB drive or phone doesn't show up", "Closing the lid doesn't do what I chose", "The screen went black after choosing a display mode" |
| `docs/wiki/FAQ.md` | "Why is there no Hibernate?", "What happens when the battery is almost empty?", "Can I print and scan?" |
| `docs/wiki/Drivers.md` | "Laptops with two graphics chips" (145-156): Shift+Enter in the launcher |
| `docs/wiki/Terminal-and-Shell.md` | "SSH keys" (the agent), Activity (`Ctrl + Shift + Esc`) |
| `docs/wiki/Desktop-Tour.md` | night light, keep awake, the drives item, Super+P, sharing |
| `docs/wiki/Apps-and-Software.md` | KDE Connect module; LocalSend's share menu and Thunar action; input methods |
| `docs/wiki/Release-Notes.md` | the 0.3.0 entries for everything in 1 |
| `docs/PLAN.md` | 328 (XDG autostart); §7's session bullets (the units that exist now); §10 "A friendlier upgrade flow comes later" → Settings → Updates |
| `docs/BUILD-SPEC.md` | Settings pages list (186-187), "Files it writes" (193-205: `nightlight.conf`, `lid.conf`, `effects.*`, `shell.json` keys, `~/.config/autostart`, `~/.face`), "Commands it calls" (207-215: the new tools and the root helper); the arctic-desktop-config row (69): helpers, units, polkit policy, profile script |
| `dotfiles/README.md`, `shell/README.md`, `settings/README.md` | 10.2 |

---

### 14. Work packages and order

| WP | Name | Owns (new files) | Depends on |
|---|---|---|---|
| S0 | Foundations: root helper, Settings module, icons, OSD message | `packaging/system/arctic-system-helper`, `packaging/polkit/org.arcticlinux.system.policy`, `settings/scripts/arctic_system.py`, `shell/tests/test_system_helper.py`, `settings/tests/test_arctic_system.py` | bar-menus WP-A (`icons-extra.js`) |
| S1 | Night light | `arctic-nightlight`, `NightLightService.qml`, `test_nightlight.py`, fixtures | S0; bar-menus WP-J (registry, Quick Settings) |
| S2 | Keep awake and app inhibitors | `IdleService.qml`, `IdleCore.js`, `scripts/screensaver-bridge.py`, `arctic-awake`, tests | S0, bar-menus WP-J |
| S3 | Idle pipeline | `IdlePipeline.qml`, `IdleDim.qml`, `IdlePlan.js`, tests | S2 |
| S4 | Lid, clamshell, display modes | `arctic-display`, `DisplayModePanel.qml`, `DisplayModes.js`, tests | S0, bar-menus WP-A |
| S5 | Power menu extras, low-battery fallback | `test_power_prepare.py` | S0, bar-menus WP-A and WP-H, Get apps WP-A4 (`AppsService.busy`) |
| S6 | Lighter effects and game mode | `arctic-effects`, `EffectsService.qml`, `GameModeService.qml`, `test_effects.py` | S0 |
| S7 | Discrete GPU launch | `arctic-gpu`, `GpuService.qml`, `test_gpu.py` | Get apps WP-A4 (launcher row actions) |
| S8 | XDG autostart | the target and service drop-ins | — |
| S9 | Date and time | `DateTimePage.qml`, `ClockFormat.js`, tests | S0, bar-menus WP-G (calendar), WP-H (`shell-set`) |
| S10 | Users and sign-in | `UsersPage.qml`, `pam/arctic-lock-fingerprint` | S0, Get apps WP-A8 (`arctic-open --app-id`) |
| S11 | Input methods, SSH agent, system tools | `arctic-restart`, `arctic-ssh-agent.sh`, `test_restart.py` | S0, S8, Get apps WP-A8 |
| S12 | Flathub and firmware updates | the four `arctic-flatpak-update` units | S0 |
| S13 | Snapshots, next Fedora, What's new | `whats-new.json`, `WhatsNew.qml`, `WhatsNewCore.js`, `test-whats-new.cjs` | S0, S12 |
| S14 | Printing and scanning | `PrintersPage.qml` | S0 |
| S15 | Drives, phones, network shares | `DrivesService.qml`, `DrivesItem.qml`, `DrivesPanel.qml`, `scripts/drives.py`, `test_drives.py` | bar-menus WP-A, WP-F (notification actions) |
| S16 | Sharing page, firewall, SSH, share menu, KDE Connect | `SharingPage.qml`, `SharePanel.qml`, `arctic-share`, `uca.xml`, `modules/sync/kdeconnect/*`, tiles, `test_share.py` | S0, S14 (mdns), design bundle tile |
| S17 | Packaging, CI, docs | — | all |

Order: S0 → (S1, S2, S4, S6, S8, S12, S14 in parallel) → (S3, S5, S9, S10, S11, S13, S15, S16)
→ S7 once the launcher changes of the Get apps section have landed → S17. Each package lands with
its tests and green CI; the spec and preset edits are listed per package (the structured summary)
so they merge one by one. The merge to main is one pull request (D10).

---

### 15. Interfaces with other sections

| Section | This section needs | This section gives |
|---|---|---|
| Bar menus (D5) | `BarMenu.qml` host and toolkit, `ToggleRegistry.qml`/`Toggle.qml`, Quick Settings sub-pages, `DisplayPanel.extraRows`, `icons-extra.js`, `BatteryService`/`battery.py` (adds `--notify`), `shell-set` (adds keys), `shell_session` in `arctic-session`, `ModeIndicators`, python3-dbus and python3-gobject-base in arctic-shell | three toggles, three panels, two sub-pages; the charge-limit polkit answer (its 🔍 closes); night-light and display-mode rows for its Display page; `CalendarPanel` reads `week_start` |
| Get apps (D2/D3) | `arctic-open terminal --app-id` and its `TerminalApp.Float.` rule (6.11 there), `AppsService.busy`/`currentLabel` (3.10 there), IPC `apps search <source> <text>` | the Flatpak timers for system and user installations (its 6.14 asks for both); the new arctic-desktop Requires enter its protected closure; GPU launch in `Launcher.activate` |
| Shortcuts (D7) | the collision check reads the lines of 9.1 including `switchbind`, and warns about `Ctrl + Shift + Esc` with `grp:ctrl_shift_toggle`; `keys.txt` merge | the new keys and their texts |
| Notifications (D6) | actions on notifications ("Open", "Eject", "Open Settings") through the shell's server or `notify-send -A` | — |
| Web app engine (D4) | — | the `org.freedesktop.ScreenSaver` bridge, so WebKitGTK and Chromium `--app` windows can keep the screen on (🔍 16.2 #3); gcr's GTK 4 is already there because of arctic-webapps |
| Hardware keys (P0, other section) | the power key opens `PowerMenu` (4.6 adds its rows) | `XF86Display` is bound here |
| OSD kinds (P2, other section) | an icon-and-text OSD; if it lands first, this section uses it | otherwise `Osd.showMessage` here |
| Command menu / launcher search modes (P1/P2, other sections) | — | stable commands to list: `arctic-restart sound\|wifi\|bluetooth\|shell`, `arctic-display mode …`, `arctic-share …`, `arctic-nightlight toggle`, `arctic-awake on N`, `arctic-effects game toggle` |
| First-login welcome (P1, other section) | — | an input-method hint for zh/ja/ko installs (6.4.4); What's new skips fresh installs, so the two never both appear |
| User hooks (P2, other section) | — | events it can fire: `battery-low` (bar-menus' BatteryService), `lock`/`unlock` (LockScreen), `post-update` (arctic-update, including `flatpak`) |
| Release (D1, D10) | Version 0.3.0; `whats-new.json` text reviewed with the release notes | — |

---

### 16. Open issues and unverified points

#### 16.1 Open decisions (each with a recommendation)

1. **KDE Connect tile.** The catalog test needs an `APPS` entry and two tile SVGs from the design
   bundle (`shell/dev/export-design-assets.cjs` and the installer's generated `Icons.js`).
   *Recommendation*: draw the tile in the bundle (category tint `info-soft`, `phone` glyph, per
   brand book 103) before S16; if it can't be ready, ship S16 without the catalog module (Get
   apps' Fedora packages page still installs `kde-connect`).
2. **Printing in the image vs. at install.** *Recommendation*: in the image (Requires), because
   printing is expected to work on first boot and on the live USB. If 16.2 #27 shows the ISO over
   2 GiB, move `system-config-printer`, `simple-scan` and the gvfs backends to a hidden
   `modules/_system/printing` module installed online (the `catalog_test.go:91,188` lists change
   with it).
3. **Default battery idle times.** *Recommendation*: the same as plugged in until the person
   picks (no behaviour change on update); revisit after feedback.
4. **mdns in the firewall's default zone** on existing systems (8.1.2) changes their firewall on
   update. *Recommendation*: do it (printers and `.local` names don't work otherwise; mDNS is
   UDP 5353 multicast only), with a release-notes line and the Sharing switch to undo it.
5. **Password login when SSH is turned on from Settings.** *Recommendation*: off by default, with
   the banner of 8.3.1; the command-line path (`sudo systemctl enable --now sshd`) keeps Fedora's
   default and the wiki says so.
6. **`shell.json` key spelling**: follow the bar-menus review (its open issue); this section uses
   snake_case.
7. **Where the effects source line goes** for users who replaced `config.conf` with their own
   file: `arctic-effects` inserts before the `user.conf` line, or appends; *recommendation*: never
   edit a `config.conf` that has no `settings.conf` line either (it is clearly hand-made) and say
   in Settings that effects need the line.

#### 16.2 Unverified (🔍), and what proves each one

| # | Claim | Proof |
|---|---|---|
| 1 | The bar's `IdleInhibitor` keeps swayidle and `IdleMonitor` idle under a fullscreen window | a video fullscreen on another workspace for longer than the lock time, keep awake on |
| 2 | The inhibitor moves to the next bar when screen 0 is disabled (clamshell), and keep awake survives `arctic-shell --restart` | laptop + monitor, lid closed, keep awake on, wait past the lock time |
| 3 | xdg-desktop-portal-gtk's Inhibit falls back to `org.freedesktop.ScreenSaver`; Chromium/Electron and WebKitGTK call the bridge | a YouTube video in Chromium `--app`, a Flatpak (Zen), a web app from the engine; `dbus-monitor` shows `Inhibit` |
| 4 | The dim layer lets input through; `wakeup_monitor` brings every screen back | idle with two monitors, move the mouse during the dim and after screen off |
| 5 | Shell pipeline and swayidle backstop never suspend twice or lock while the person is typing | 30 min of idle/wake cycles on battery and AC, `journalctl --user` |
| 6 | UPower 1.91.4 re-applies an enabled charge limit after a reboot | ThinkPad or Framework: enable, reboot, `upower -d` |
| 7 | `switchbind=fold/unfold` fires on the lid under Mango; a 2-in-1's tablet switch doesn't turn the panel off | two laptops and one 2-in-1 |
| 8 | Logind suspends a closed laptop after its last monitor is unplugged, and the panel is back on when it wakes | unplug HDMI with the lid closed |
| 9 | wlsunset accepts `-T` one kelvin above `-t` and stays warm all day | run it at noon, look |
| 10 | The status's civil dawn/dusk is within ~15 min of wlsunset's transitions | compare at a known location over a week |
| 11 | Gamma works on Mango with scenefx on two monitors and on the lock screen | night light on, lock, second monitor |
| 12 | Mango puts `wl-mirror --fullscreen-output` on the requested output | projector test; else the `tagmon` fallback |
| 13 | `switcherooctl launch` runs Steam and glxgears on the NVIDIA GPU; `prefers` includes Steam's Flatpak id | NVIDIA hybrid laptop, `nvidia-smi` |
| 14 | The generated unit names are `app-blueman@autostart.service` and `app-nm\x2dapplet@autostart.service`, and the `ExecCondition` drop-ins skip them in the Quickshell session | `systemctl --user list-units --all 'app-*@autostart.service'` on F44 |
| 15 | Flathub apps' "Start on login" (Background portal) writes `~/.config/autostart` with Arctic's portals | Discord or Nextcloud from Flathub |
| 16 | The shell's clock follows a time-zone change without a restart | change the zone in Settings, watch the bar |
| 17 | `passwd` also changes the login keyring's password | change it, log out and in, `secret-tool` or a saved Wi-Fi password |
| 18 | `SetIconFile(~/.face)` makes SDDM show the picture | change it, log out |
| 19 | The fingerprint `PamContext` unlocks the lock screen; `with-fingerprint` covers sudo and the shell's polkit dialog; `with-pam-u2f` likewise | laptop with a reader; a YubiKey |
| 20 | fcitx5-configtool's Wayland app id is `org.fcitx.fcitx5-config-qt` | `mmsg get all-clients` |
| 21 | Japanese input works in a GTK 4 app, a Qt 6 app, Zen (Flatpak) and a Chromium `--app` window; Fcitx and the layout chip agree | install mozc, type |
| 22 | `ssh-add -l` works in kitty and a git push from Zed shows gcr's passphrase dialog once | a key with a passphrase |
| 23 | `flatpak update --noninteractive` output lets `arctic-update` count updated apps | capture on F44 with flatpak 1.18.2 |
| 24 | `fwupdmgr get-devices --json`/`get-updates --json` field names and "nothing to do" exit code in fwupd 2.1.8 | a laptop with LVFS firmware; a VM |
| 25 | `snapper --jsonout list` key names in snapper 0.13.0 | run on an installed system |
| 26 | The `cmd_line` dnf5 records for `system-upgrade download --releasever=N -y`, and whether the real-dnf5 CI job can test it | an F44 VM against F45 branched; the container job |
| 27 | The ISO stays ≤ 2 GiB with the CUPS stack, ghostscript, gvfs backends and gcr | `tools/build-iso.sh`, before and after |
| 28 | system-config-printer's app id, `/usr/share/cups/data/testprint` in F44, and `lpstat` output formats | a CUPS 2.4.16 system; fixtures captured then |
| 29 | Network printers are found only with `mdns` allowed in the `public` zone | IPP Everywhere printer, with and without |
| 30 | USB stick, SD card, Android (file transfer), iPhone after "Trust", a camera and an SMB share all show in the drives menu or Thunar | the devices |
| 31 | `firewall-cmd` runtime queries don't ask for a password under the server polkit policy | as a wheel user in a terminal |
| 32 | SSH on, key-only login from another machine works; password login off refuses passwords | a second computer |
| 33 | The Flathub LocalSend supports `--headless send` and can read the files it is given | send a file to a phone |

---

### 17. Deferred, with reasons

- **Setting up hibernation**: 4.7 (no disk swap, Secure Boot lockdown, untested on LUKS2 + btrfs).
  The Hibernate row still appears when logind allows it.
- **A suspend on/off switch** (Omarchy's `omarchy-toggle-suspend`): "Suspend after: Never" and the
  lid's "Keep running" already cover machines where suspend misbehaves; the menu row stays.
- **Booting into a snapshot**: grub-btrfs is not in Fedora 44; Settings can undo from a running
  system, and the wiki covers the live USB.
- **A per-user language** (`~/.config/environment.d` and `~/.i18n`): the system language is in
  Date and time; a per-user language needs the SDDM session and the shell to agree and wasn't
  in the gap item's first phase.
- **Region formats** (LC_TIME, LC_NUMERIC separately): same reason.
- **A print-job indicator on the bar**: CUPS has no user-session job feed without polling
  `lpstat`; the Printers page lists and cancels jobs.
- **Nix profile upgrades** (the gap's optional switch): the installer puts Nix apps in root's
  default profile, pinned to a nixpkgs revision (`modules/catalog.toml:17`), so `nix profile
  upgrade --all` wouldn't change them; revisit with a pin-bump flow.
- **Pre-ticking an input method in the installer by language**: it needs a catalog category and
  wizard changes owned by the installer; the Settings flow and the welcome hint cover it.
- **Omarchy's hybrid-GPU mode switch** (moving the whole desktop to the dGPU): Arctic keeps the
  desktop on the integrated GPU (`arctic-graphics.sh:13-19`) and launches single apps on the
  discrete one.
- **gammastep as a second night-light backend**: one tool is enough while wlsunset works on
  Mango.
