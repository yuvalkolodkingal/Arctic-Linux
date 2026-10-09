# Arctic Settings

The settings app of Arctic Linux: a hyprmod-like editor for Mango and the Arctic desktop, written
for [Quickshell](https://quickshell.org) in the Arctic look. `Super + S`, the launcher, or the
first item of the power menu (`Super + Esc`) open it.

```sh
arctic-settings                 # open it (a second call brings the window forward)
arctic-settings displays        # open it on a page
quickshell -p settings          # from a checkout
```

Pages: Appearance, Windows, Displays, Keyboard and mouse, Shortcuts, Default apps, Network,
Sharing, Bluetooth, Sound, Dictation, Updates, Power and lock, Startup apps, Printers and scanners, Date and
time, Users and sign-in, About. `Ctrl + F` (or `/`, or just typing
in the page list) searches every setting; a result opens its page and highlights the row. `↑ ↓`
in the page list switch pages, `Tab` goes into the page, `Esc` comes back, `Ctrl + PgUp/PgDn`
switch pages from anywhere, `Ctrl + Z` undoes the last change, `Ctrl + Q` closes Settings.

## Why our own app

[hyprmod](https://github.com/BlueManCZ/hyprmod) (GTK4/libadwaita, Python, GPL-3.0) is built on
five Hyprland-only libraries (hyprland-config, -schema, -state, -monitors, -socket) and applies
changes with `hyprctl keyword`; Mango has neither that config language nor that IPC, and a GTK
app wouldn't look like Arctic. No Mango settings GUI exists besides monitor-layout tools
([mdisplay](https://github.com/ernestoCruz05/mdisplay)). So Settings borrows hyprmod's model —
its own managed file that the main config sources, changes applied live, a "changed" mark and
reset per option, search, undo — and is built from Arctic's own parts.

## How it's put together

| Part | Files |
|---|---|
| Window, page rail, search, toast | `shell.qml`, `Main.qml`, `SearchIndex.js`, `Toast.qml` |
| Page scaffolding | `Page.qml` (title, lede, scroll, reveal a row), `Group.qml` (a card of rows), `SettingRow.qml` (title, why, control, "Changed" + Reset, "user.conf wins" note), `RowSwitch.qml`, `PickerDialog.qml` |
| Pages | `pages/*Page.qml` |
| Look | `Theme.qml` (the design tokens of the current theme: `~/.config/arctic/current/theme.json`, live), `components/` (the installer's components, ported unchanged — `tests/test_app_files.py` keeps them in sync — plus `ArSlider` and `ArSegmented`) |
| Backend | `Backend.qml` runs `scripts/arctic_settings.py`, which does every read and write and prints JSON |

Quickshell keeps imports inside each application's config root. Dictation uses
the canonical parser in `shell/DictationStatus.js`, bundled as an identical local
`settings/DictationStatus.js` resource. After changing the parser, run
`cp shell/DictationStatus.js settings/DictationStatus.js`; the consistency checks
reject drift, and RPM installation uses the canonical source for both apps.

## What it changes

Settings never runs as root. The few system-wide changes ask for your password: through polkit
(`timedatectl`, `localectl`, `hostnamectl`, AccountsService) or `pkexec` and Settings' root helper
(`packaging/system/arctic-system-helper`: the firewall, remote login and snapshots; its arguments
are checked against fixed tables). The system commands (night light to users) live in
`scripts/arctic_system.py`, which `arctic_settings.py` merges in. Every file is written atomically (temporary file + rename), validated first
(the helper's own table of Mango keys, then `mango -c FILE -p`), and the previous version is kept
in `~/.local/state/arctic/settings-backups` (the newest 20 of each). (an empty `.absent` marker when
there was no file yet, so even the first change can be undone). Writes take a lock
(`$XDG_RUNTIME_DIR/arctic-settings.lock`), so quick changes one after another never overwrite
each other. A display switched off is never saved (`disable:1` would keep a laptop's only screen
dark the next time it starts without its dock): off lasts until you log out.

| Setting | Written to | Applied with |
|---|---|---|
| Windows, keyboard, touchpad, mouse, pointer, default layout, your shortcuts, startup apps, kept display layouts | `~/.config/mango/settings.conf` (`key=value`, `tagrule=id:*,…`, `bind=…,spawn_shell,…`, `exec-once=…`, `monitorrule=…`) | `mmsg dispatch reload_config` |
| — | `~/.config/mango/config.conf` gets `source-optional=~/.config/mango/settings.conf` before the `user.conf` line if it lacks it | |
| Theme, colours from the wallpaper, light/dark | through `arctic-theme set\|auto\|mode` (the older `arctic-theme winter\|polar-night` when that's all there is) | |
| Wallpaper | through the shell's `scripts/wallpapers.py apply` → `arctic-wallpaper` | |
| Shared SDDM/lock wallpaper, opt-in desktop sync | `arctic-login-wallpaper` → confined system D-Bus publisher; administrator authorization for explicit changes | public system copy; [scope and privacy](../docs/LOGIN-WALLPAPER.md) |
| Reduce motion | through `arctic-motion on\|off` | |
| Text size in GTK apps, pointer for GTK apps | `gsettings` `org.gnome.desktop.interface` `text-scaling-factor`, `cursor-theme`, `cursor-size` | |
| Displays (arrange) | nothing: the helper's `display-arrange` works out every drag, arrow key, **Make main**, on/off and size change (displays touch edge to edge, never overlap, top-left at 0,0; the main display is the one there, where Mango starts the pointer) | |
| Displays (try) | `wlr-randr --output …` (not saved); `$XDG_RUNTIME_DIR/arctic-settings-display.json` holds the layout to go back to | a watchdog reverts after 20 s unless kept |
| Displays (keep) | `monitorrule=name:^OUT$,width:…,height:…,refresh:…,x:…,y:…,scale:…,rr:…,vrr:…` in settings.conf, the main display's first | Mango already shows it (no reload) |
| Default apps | `~/.config/arctic/default-apps` (`role=command`, read by `arctic-open`) and `~/.config/mimeapps.list` `[Default Applications]` (as `xdg-mime default`) | |
| Lock / suspend timeouts | `~/.config/arctic/idle.conf` (`lock_after=`, `suspend_after=` seconds, 0 = never) | `arctic-session idle --restart` (swayidle) |
| Power mode | tuned-ppd over D-Bus (`gdbus`, `org.freedesktop.UPower.PowerProfiles`) | |
| Wi-Fi | `nmcli radio wifi on\|off` | |
| Bluetooth, sound | BlueZ and PipeWire directly (Quickshell.Bluetooth, Quickshell.Services.Pipewire) | |
| Updates | `arctic-update status --json`, `now`, `apply`, `channel stable\|testing`, `auto on\|off` | |
| Night light (Displays) | through `arctic-nightlight set KEY=VALUE…` / `on\|off --quiet` (`~/.config/arctic/nightlight.conf`) | the helper restarts wlsunset |
| Keep awake | through `arctic-keep-awake on [MINUTES]\|off --quiet` (`$XDG_RUNTIME_DIR/arctic/keep-awake`) | `arctic-session idle --restart` |
| Apps that start themselves (Startup apps) | `~/.config/autostart/ID.desktop`: a copy with `Hidden=true` to switch one off, removed again when nothing of yours is left | next login (systemd's XDG autostart) |
| Default printer, cancel jobs | `lpoptions -d NAME` (`~/.cups/lpoptions`), `cancel -a NAME` | |
| Time zone, network time, clock, language | `timedatectl set-timezone\|set-ntp\|set-time`, `localectl set-locale LANG=…` (systemd, polkit asks for the password) | |
| Times on battery, dimming, screens off after the lock (Power and lock) | `~/.config/arctic/idle.conf` (`lock_after_battery=`, `suspend_after_battery=`, `dim_before_lock=`, `screen_off_after=`) | `arctic-session idle --restart` |
| Closing the lid (Power and lock) | `~/.config/arctic/lid.conf` (`when_closed=`) | `arctic-session lid --restart` |
| Lighter effects, game mode (Windows) | through `arctic-effects lighter\|game …` (`~/.config/arctic/effects.conf`, sourced by config.conf) | Mango reloads |
| Computer name (About) | `hostnamectl set-hostname --static` (polkit) | |
| Your name and picture (Users and sign-in) | AccountsService (`SetRealName`, `SetIconFile`) and `~/.face` | |
| Fingerprint on the lock screen | `~/.config/arctic/shell.json` (`lock_fingerprint`) | the shell watches the file |
| Firewall allows, remote login (Sharing); snapshots (Updates) | `pkexec arctic-system-helper firewall-allow\|ssh\|ssh-password\|snapshot-create …` | |
| Flatpak apps and firmware (Updates) | through `arctic-update flatpak\|firmware` | |

settings.conf is sourced after Arctic's files, `keyboard.conf` and `motion.conf`, and before
`user.conf`, so your own `user.conf` still wins (Settings says so on the row). Animations are
switched back on by removing `animations=0`, never by writing `animations=1`, so reduced motion
keeps working. Mango uses the first bind for a key, so a shortcut on a taken key is refused.

When a tool is missing, its controls say so instead of failing: no `arctic-update` → how to
update with dnf; the older `arctic-theme` → only Winter and Polar night; no `wlr-randr` → scale,
rotation and position only (plus wdisplays if installed); no NetworkManager, BlueZ or PipeWire →
a note.

Dictation uses the local `arctic-dictation` controller. Settings shows setup, download,
recording, transcription and error states; language and acceleration can change while idle.
The online installer downloads VoxType and a multilingual Whisper model after the OS copy;
offline installation queues retryable setup. Recording stays unavailable until both are
verified. Setup discloses app and model download sizes before authorization. The live ISO
contains only the controller and frontend.

Focus a text field and release **Super + Ctrl + X** to start recording; the same shortcut
stops and inserts text. **Super + Ctrl + Backspace** cancels. On the visible taskbar, the
dictation pill can start, stop or cancel without focusing Settings. With a hidden taskbar,
the pill shows recording or transcription status and the shortcuts remain available.
QML consumes status only and never receives the transcript.

## Developing

```sh
python3 -m unittest discover -s settings/tests -v       # backend + consistency (Mango checks when installed)
/usr/lib64/qt6/bin/qmllint -I settings $(find settings -name '*.qml')
settings/dev/headless.sh --smoke --fixtures              # every page in a headless sway, screenshots
settings/dev/headless.sh page displays shot displays      # one screenshot
settings/dev/headless.sh --outputs 3 page displays shot displays   # the arrangement, three displays
```

`dev/headless.sh` needs sway, grim, quickshell and python3 (Fedora container: see the CI job).
`--outputs 2|3` adds sway headless displays (2560 × 1440 at 150 %, and 1920 × 1080 turned 90°)
next to the first; `--smoke` also plugs them in after the page tour and checks the Displays page
gets them.
`--fixtures` adds test desktop entries, the installer's default-apps and an `arctic-update`
stand-in, for screenshots only. Screenshots of every page (Polar night) are in
`dev/screenshots/`.
