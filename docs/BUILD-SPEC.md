# Arctic Linux v0.1 — build spec (contracts between components)

This is the contract every component is built against. `docs/PLAN.md` explains the *why*;
this file fixes the *what*: paths, package names, the engine ↔ UI protocol, and the wizard.
When a detail here turns out to be wrong on a real system, fix it here first, then in code.

Target: **Fedora 44**, x86_64, UEFI + BIOS. Product name "Arctic Linux", identifier `arctic`.
Design system: `design/` (tokens, brand book, guidelines) and the full system in the artifact
https://claude.ai/artifact/8eUAobifhKCoecsG23Fb3i (a local copy of its files is in the session
scratchpad; see each task prompt).

## 1. Repository layout

```
cmd/arcticd/            installer engine daemon (Go, root)
cmd/arctic-install/     engine CLI: dry-run, unattended, bridge (Go)
internal/…              engine packages (Go)
modules/<slot>/<id>/module.toml   app catalog (see §5)
profiles/defaults.toml, profiles/ci/*.toml
shell/                  Quickshell desktop shell (bar, launcher, wallpapers, get-apps console, OSD, lock, live welcome)
installer-ui/           Quickshell installer frontend (the 12-step wizard)
branding/sddm/arctic/   SDDM Qt6 QML login theme
branding/grub/arctic/   GRUB theme (live ISO boot menu + installed system)
branding/plymouth/arctic/  Plymouth script theme
branding/logos/         generated PNG/SVG logos for system-logos
dotfiles/               user home tree → /etc/skel
design/                 design system sources (read-only input)
design/themegen/        theme engine (arctic-themegen): palettes → theme folders, templates, wallpaper colours (§9)
packaging/arctic-linux.spec   ONE spec, many subpackages (§2), Source0 = repo tarball
packaging/mangowm.spec        Mango built from upstream
live/                   live-session files (livesys session, arctic-live-session, sddm live conf)
iso/kiwi/               kiwi-ng description for the live ISO
tools/build-rpms.sh     builds all RPMs in a Fedora 44 container → out/repo (createrepo_c)
tools/build-iso.sh      builds the ISO with kiwi-ng in a privileged Fedora 44 container → out/iso
tools/test-iso.sh       boots the ISO in QEMU (no KVM needed), takes screenshots
tools/test-install.sh   installs from the ISO to a VM disk (arctic-install unattended, profiles/ci/offline.toml),
                        then boots it: LUKS prompt, SDDM login, desktop, logs over the serial port
tools/lib/              container.sh (docker/podman + proxy), vmtest.py (QEMU/QMP helpers for the tests)
.github/workflows/ci.yml   go test, shellcheck, python tests, node tests, qmllint
.github/workflows/iso.yml  build RPMs + ISO, upload artifact, publish release (tag or manual)
```

## 2. RPM packages (all from `packaging/arctic-linux.spec` unless noted)

Version 0.1.0, Release 1%{?dist}. `Source0: arctic-linux-%{version}.tar.gz` made by
`git archive --prefix=arctic-linux-0.1.0/ HEAD` (tools/build-rpms.sh; uncommitted changes are
included via `git stash create`). noarch unless it contains Go binaries.

| Subpackage | Installs | Notes |
|---|---|---|
| `arctic-release` | `/usr/lib/os-release` (NAME="Arctic Linux", ID=arctic, ID_LIKE=fedora, VERSION_ID=0.1, PRETTY_NAME="Arctic Linux 0.1 (Fedora 44 base)", LOGO=arctic-logo-icon, HOME_URL), `/etc/os-release` symlink, `/usr/lib/rpm/macros.d/macros.dist` (%fedora 44, %dist .fc44), `/etc/dnf/plugins/copr.d/arctic.conf` ([main] distribution=fedora), `/usr/share/dnf5/repos.d/arctic.repo` (the Arctic package repository, `enabled=0` with a placeholder address until the Arctic COPR is published), presets `/usr/lib/systemd/system-preset/80-arctic.preset` (also: no sshd, as Fedora's desktop editions), `/usr/lib/systemd/user-preset/80-arctic.preset` | Provides `system-release`, `system-release(44)`, `system-release(releasever) = 44`, `base-module(platform:f44)`; Requires `fedora-repos(44)`; Conflicts `fedora-release-common`, `generic-release`. Model on Fedora's generic-release.spec. MUST be proven installable in place of fedora-release in a F44 container (`dnf install --allowerasing arctic-release`). |
| `arctic-logos` | `/usr/share/pixmaps/{fedora,system}-logo*.png` equivalents, `/usr/share/icons/hicolor/*/apps/arctic-logo-icon.png`, `/usr/share/arctic/logos/*.svg` | Provides `system-logos`, `system-logos(%{version})`; Conflicts `fedora-logos`, `generic-logos`. Must satisfy what sddm/plymouth require from system-logos. |
| `arctic-backgrounds` | `/usr/share/backgrounds/arctic/*.svg` + rendered `*.png` (3840×2160) | The 6 design wallpapers. Provides `desktop-backgrounds-compat` if needed by sddm. |
| `arctic-fonts` | `/usr/share/fonts/arctic/Figtree-*.woff2` (+ `.ttf` if converted) | JetBrains Mono comes from `jetbrains-mono-fonts-all`. |
| `arctic-selinux` | `/usr/share/selinux/packages/arctic-nix.pp` | Built from `packaging/selinux/arctic-nix.te/.fc` (`/nix` contexts, see PLAN §6.6). %post: semodule install; `%selinux_modules_install`. |
| `arctic-desktop-config` | `/etc/skel/` ← `dotfiles/` (minus install.sh/README and the files below), `/usr/bin/arctic-*` ← `dotfiles/.local/bin/*`, `/usr/share/arctic/mango/*.conf` ← `dotfiles/.config/mango/arctic/` (skel has links to them), `/usr/share/arctic/keys.txt`, `/usr/share/arctic/themes/{winter,polar-night}/` (rendered by the engine in %build; skel's `~/.config/arctic/current` links there), `/usr/share/arctic/themegen/` + `/usr/bin/arctic-themegen` (theme engine, §9), `/usr/share/arctic/theme-hooks.d/`, `/etc/arctic/default-apps` (defaults) | Requires the desktop runtime (§3) and python3-pillow (wallpaper colours). Helper scripts must look in XDG dirs: `~/.local/share/arctic/…` then `/usr/share/arctic/…`, and wallpapers in `/usr/share/backgrounds/arctic`. |
| `arctic-shell` | `/usr/share/arctic/shell/` ← `shell/`, `/usr/bin/arctic-shell` (`exec quickshell -p /usr/share/arctic/shell "$@"`) | Requires quickshell, python3, python3-pillow, python3-pyte. |
| `arctic-installer` | `/usr/bin/arcticd`, `/usr/bin/arctic-install`, `/usr/share/arctic/catalog/` ← `modules/`, `/usr/share/arctic/profiles/`, `/usr/share/arctic/installer-ui/` ← `installer-ui/`, `/usr/bin/arctic-installer` (`exec quickshell -p /usr/share/arctic/installer-ui "$@"`), `/usr/lib/systemd/system/arcticd.{socket,service}`, `/usr/share/applications/org.arcticlinux.Installer.desktop` | arch x86_64 (Go). BuildRequires golang. Go builds offline: vendor modules or stdlib only (prefer stdlib only; `github.com/BurntSushi/toml` allowed only if vendored). |
| `sddm-wayland-mango` | `/usr/lib/sddm/sddm.conf.d/10-arctic.conf`, `/usr/libexec/arctic/sddm-compositor-mango`, `/usr/share/arctic/sddm/greeter.conf` | Provides+Conflicts `sddm-greeter-displayserver`. Requires sddm, mangowm, layer-shell-qt. Config per PLAN §7. If the mango greeter can't be made to work in the VM test, ship `10-arctic.conf` for `sddm-wayland-generic` (weston) instead and note it. |
| `arctic-sddm-theme` | `/usr/share/sddm/themes/arctic/` ← `branding/sddm/arctic/` | Requires sddm, qt6-qtdeclarative, qt6-qt5compat only if used. |
| `arctic-plymouth-theme` | `/usr/share/plymouth/themes/arctic/` ← `branding/plymouth/arctic/` | Requires plymouth-plugin-script. %post: `plymouth-set-default-theme arctic` (no initrd rebuild in %post). |
| `arctic-grub-theme` | `/boot/grub2/themes/arctic/` ← `branding/grub/arctic/` (+ `/usr/share/arctic/grub-theme/` copy) | Installed system sets `GRUB_THEME`; the ISO uses the same files. |
| `arctic-live` | `/usr/libexec/livesys/sessions.d/livesys-arctic`, `/usr/libexec/arctic/live-session`, `/usr/share/arctic/mango/live.conf` | Only in the live image. |
| `mangowm` (packaging/mangowm.spec) | upstream mango 0.17.3 | BuildRequires meson, gcc, `pkgconfig(wlroots-0.20)`, `pkgconfig(scenefx-0.5)`, wayland-devel, wayland-protocols-devel, libinput-devel, libxkbcommon-devel, pcre2-devel, pixman-devel, cjson-devel, pango-devel, libdrm-devel, xcb deps (`xorg-x11-server-Xwayland-devel`/libxcb-devel, xcb-util-wm-devel). `Source0: https://github.com/mangowm/mango/archive/refs/tags/0.17.3.tar.gz`. `/etc/mango/config.conf` marked `%config(noreplace)`. |

Metapackage: `arctic-desktop` (subpackage, no files) Requires everything a desktop needs:
mangowm, sddm, sddm-wayland-mango, arctic-sddm-theme, arctic-shell, arctic-desktop-config,
arctic-backgrounds, arctic-fonts, arctic-logos, arctic-release, arctic-plymouth-theme,
arctic-grub-theme, kitty, kitty-shell-integration, zsh, fastfetch, mako, swaybg, swayidle,
swaylock, grim, slurp, wl-clipboard, cliphist, brightnessctl, playerctl, wireplumber,
pipewire-pulseaudio, pavucontrol, network-manager-applet, NetworkManager-wifi, blueman,
xdg-desktop-portal-wlr, xdg-desktop-portal-gtk, xdg-user-dirs, xdg-utils, libnotify,
librsvg2-tools, jetbrains-mono-fonts-all, google-noto-sans-fonts, polkit, gnome-keyring,
gnome-keyring-pam, Thunar, qt6-qtwayland, qt5-qtwayland, xorg-x11-server-Xwayland,
fuzzel (fallback launcher), flatpak, nix, nix-daemon, arctic-selinux, python3-pillow.

## 3. Desktop session (installed and live)

SDDM (theme `arctic`, greeter on mango or weston) → `mango.desktop` → `~/.config/mango/config.conf`
(from /etc/skel). Autostart (`dotfiles/.config/mango/arctic/autostart.conf`):
`arctic-theme apply`, `arctic-shell` (Quickshell: bar, launcher, wallpapers, OSD, lock, live
welcome), `arctic-session mako|nm-applet|clipboard|idle`. The Quickshell polkit agent is used if
`Quickshell.Services.Polkit` works, else lxqt-policykit via `arctic-session polkit`.
waybar/fuzzel configs stay in the dotfiles as a fallback (`ARCTIC_SHELL=waybar`).

Quickshell IPC (for keybinds): `quickshell -p /usr/share/arctic/shell ipc call <target> <fn>`,
wrapped by `arctic-shell-ipc <target> <fn>` (in arctic-shell). Targets: `launcher toggle`,
`wallpapers toggle`, `apps install` (get-apps console), `power toggle`, `osd volume|brightness`,
`lock lock`, `keys toggle`. Mango binds call these.

## 4. Engine ↔ installer UI protocol

- `arcticd` listens on `/run/arcticd.sock` (systemd socket activation: `arcticd.socket`,
  `ListenStream=/run/arcticd.sock`, `SocketMode=0660`, `SocketGroup=wheel`; `arcticd.service`
  runs as root). `arcticd --socket PATH` and `arcticd --mock` for development: mock mode
  simulates disks, Wi-Fi, locales and an install with realistic progress and one optional-app
  failure, and never touches the system.
- The UI runs `arctic-install bridge [--socket PATH]`, which relays newline-delimited JSON
  between its stdin/stdout and the socket (Quickshell `Process` + `SplitParser`, as in
  `shell/InstallConsole.qml`). `arctic-install bridge --mock` starts an in-process mock engine
  instead (same code as `arcticd --mock`), so the UI can run with no daemon and no root.
- Messages (one JSON object per line):
  - request `{"id": 7, "method": "SetStep", "params": {...}}`
  - response `{"id": 7, "result": {...}}` or `{"id": 7, "error": {"code": "invalid", "message": "…", "fields": {"username": "Use lowercase letters, numbers, - and _."}}}`
  - event (no id) `{"event": "progress", ...}` — sent to every connection after `Subscribe`.
- Methods (params → result):

| Method | Params | Result |
|---|---|---|
| `Hello` | `{client:"installer-ui", version}` | `{engine_version, mock:bool, live:bool, firmware:"uefi"\|"bios"}` |
| `GetWizard` | — | `{steps:[{id,title,state:"done"\|"current"\|"todo"\|"error"}], current}` |
| `GetStep` | `{id}` | `{id, title, help, data:{…current values…}, options:{…}}` (per step, §4.1) |
| `SetStep` | `{id, data}` | `{ok:true, data}` or error with `fields` |
| `Next` / `Back` | — | `GetWizard` result (Next validates the current step first; network step only passes when online). After a fatal failure (`state:"failed"`) Back returns to the wizard at Summary |
| `Goto` | `{id}` | `GetWizard` result (only to done steps — used by Summary "Change" links; from the install screen also `summary`). After a fatal failure Goto returns to the wizard (answers and secrets kept; SetStep is refused until then); every UI gets a `wizard` event |
| `ScanWifi` | — | `{networks:[{ssid,signal:0-100,secure:bool,connected:bool}]}` |
| `ConnectWifi` | `{ssid, password}` | `{ok}` or error `{code:"auth"\|"timeout", message}` |
| `NetworkState` | — | `{online:bool, wired:bool, ssid?:string}` |
| `CheckPassphrase` | `{text}` | `{score:0-4, label:"Too short"\|"Weak"\|"Fair"\|"Good"\|"Strong", words:int, ok:bool}` (ok = score ≥ 2 "Fair") |
| `SuggestPassphrase` | — | `{text:"four random words"}` (EFF short wordlist, embedded) |
| `SuggestAccount` | `{full_name}` | `{username, hostname}` (hostname = `{username}-{model}` from DMI, lowercased, `-` joined) |
| `SetSecrets` | `{luks_passphrase?, user_password?}` | `{ok}` (kept in memory only, never logged or written) |
| `EstimateDownload` | `{selection}` | `{apps:int, bytes:int, label:"9 apps · 1.4 GB download"}` |
| `GetSummary` | — | `{rows:[{step, icon, label, value}], warning, primary_label}` (rows for welcome, keyboard, timezone, disk, encryption, account, apps — each `step` is a Goto target; primary "Erase disk and install" or "Install alongside {OS}") |
| `Start` | — | `{ok}` then events. Also "Try again" after a failure. Re-probes the disks first: if the chosen disk is gone, is not the same device (model/serial/WWN/size) or, alongside, its partitions or free space changed, it answers `{code:"state"}` and refuses until the Disk step is passed again |
| `RetryModule` / `SkipModule` | `{id}` | `{ok}` |
| `SaveLog` | — | `{path, on_usb, device?, label?, safe_to_remove, message}`: to a FAT/exFAT file system on a removable disk that is not the install medium (mounted in place, else mounted, written, synced and unmounted: `path` is then the file's path on the stick and `safe_to_remove` true), else `/home/liveuser` or /tmp (lost on restart). `message` is the sentence to show |
| `Reboot` | — | `{ok}` |
| `Subscribe` | — | `{ok}` then events on this connection |

- Events:
  - `{"event":"progress","percent":0-100,"phase":"disk"|"copy"|"configure"|"bootloader"|"apps"|"finalize","status":"Installing Zed, your code editor…","eta_seconds":420,"substeps":[{"id":"disk","label":"Preparing the disk","state":"done"|"active"|"todo"},…4 items: disk, system ("Copying Arctic Linux"), apps ("Installing your apps"), finish ("Setting up your account")]}`
  - `{"event":"module","id":"zed","name":"Zed","status":"queued"|"downloading"|"installed"|"failed"|"skipped"|"deferred","percent":0-100}`
  - `{"event":"attention","module":{"id","name"},"message":"The download server didn't answer.","optional":true}` → UI shows step 11 (Try again / Skip {App}); core failures: `{"event":"failed","message":"…","fatal":true,"can_change":true}` → Save log / Try again / Change (Back or Goto).
  - `{"event":"done","apps_installed":9,"first_name":"Noa"}`
  - Status lines follow `design/guidelines/20-installer-copy.md`.

### 4.1 Wizard steps (ids fixed; copy = design/guidelines/20-installer-copy.md)

| # | id | data | options |
|---|---|---|---|
| 1 | `welcome` | `{language:"en_US.UTF-8"}` | `{languages:[{id,name(native),english}], suggested}` |
| 2 | `keyboard` | `{layout:"us", variant:"", xkb:{layout, variant, options, keymap, latin}}` (`xkb` is read-only, what the choice gives: Latin layouts alone; non-Latin ones as `us,<layout>` with `grp:alt_shift_toggle` and a Latin console keymap). A valid SetStep also writes `xkb` to the live system's `/etc/arctic/mango/keyboard.conf` (sourced by the live session); the UI then runs `mmsg dispatch reload_config`, so passwords are typed as on the installed system | `{layouts:[{layout,variant,name,description,suggested:bool}]}` |
| 3 | `network` | `{}` | `{online,wired,ssid}` (+ ScanWifi/ConnectWifi); auto-skipped when wired & online |
| 4 | `timezone` | `{timezone:"Asia/Jerusalem", auto_time:true}` | `{detected:{city,timezone,source:"network"\|"default"}, regions:{Europe:[{city,timezone}],…}}` |
| 5 | `disk` | `{disk:"/dev/nvme0n1", mode:"erase"\|"alongside"}` | `{disks:[{path,model,size_bytes,size_label,removable,install_media:bool,existing_os:[…],alongside_possible:bool,alongside_label:"Uses 120 GB of free space"}]}` (install media excluded; alongside needs ≥ 40 GB free, on UEFI an ESP to share, on MBR room for two primary partitions) |
| 6 | `encryption` | `{enabled:true}` | `{min_score:2}` (passphrase via SetSecrets) |
| 7 | `account` | `{full_name, username, hostname, autologin:false}` (username: not a user or group the copied system has) | `{hostname_hint:"Suggested from your name and computer"}` (password via SetSecrets) |
| 8 | `apps` | `{selection:{browser:["zen"],editor:["zed"],…}}` | catalog: `{categories:[{id,name,choice:"one"\|"any",note}], modules:[{id,name,summary,category,default,tile,download_mb,source,in_live_image}]}` |
| 9 | `summary` | — | via GetSummary |
| 10 | `install` | — | events |
| 11 | (attention/error, not a step) | | |
| 12 | `done` | — | `{apps_installed, first_name}` |

Categories for the picker come from the design (`CATEGORIES` in the design bundle.js):
browser "one" ("Becomes your default browser."), editor "many", terminal "one" ("Opens with
Super + Enter."), shell "one" ("What runs inside the terminal."; bash always installed), files
"many", office "one", video "many", extras "many" ("Nothing here is ticked by default."). Tile ids = design app tiles (`zen`, `firefox`, `chromium`, `zed`,
`vscodium`, `neovim`, `helix`, `kitty`, `foot`, `alacritty`, `zsh`, `fish`, `bash`, `yazi`,
`thunar`, `nautilus`, `collabora`, `libreoffice`, `onlyoffice`, `vlc`, `mpv`, `celluloid`,
`steam`, `obs`, `gimp`, `inkscape`, `signal`, `flathub`).

## 5. Catalog manifest

`modules/<category>/<id>/module.toml` as in PLAN §4.1, fields: `id, name, summary, category,
default, tile, in_live_image, gpu, requires, conflicts, [[install]] method = "dnf"|"copr"|"flatpak"|"nix"
(+ packages | copr+packages | remote+ref | attr), verified, download_mb, [defaults] desktop_id, mime,
[session] …`. Hidden mandatory modules live in `modules/_system/`. Profiles (`profiles/*.toml`)
reference module ids only.

## 6. Engine behaviour (v0.1 scope)

Real mode implements PLAN §6: preflight, disk (erase layout: 1 MiB bios_grub, 1 GiB ESP, 2 GiB
ext4 /boot, LUKS2 + btrfs @ @home @var_log @nix; alongside: reuse ESP, new /boot + LUKS in free
space, partitions numbered explicitly in the sfdisk script and deleted again if the install
fails; before the first destructive command automounts/swap are released and md/device-mapper
holders stopped, anything else mounted stops the install), copy the live root (`/run/rootfsbase`
if present else the mounted squashfs; rsync -aAXH without `security.selinux` and without
touching the mounted vfat ESP — `/boot/efi/` excluded, its files copied with `rsync -rt`),
remove live-only packages (arctic-live, livesys-scripts, arctic-installer, dracut-live),
machine-id, systemd-firstboot, fstab/crypttab, user (useradd -R, pre-hashed yescrypt/SHA-512 via
`openssl passwd -6` or Go crypt), sddm enable, `/etc/arctic/mango/keyboard.conf` (+ the
greeter's copy and vconsole.conf; non-Latin layouts as `us,<layout>` + `grp:alt_shift_toggle`
with a Latin console keymap),
`/etc/arctic/default-apps`, kernel-install/dracut, grub2-mkconfig, efibootmgr/grub2-install,
app diff (dnf remove/install in chroot, flatpak from host with FLATPAK_* into /mnt, nix via
`nix --store /mnt profile add`; a Flatpak app the image ships — Zen when the ISO fits in 2 GiB —
counts as in the live image whatever the catalog says: kept when ticked, uninstalled with its
unused runtimes when not), setfiles relabel, unmount. The target directory is made a private
mount point first (its mounts must not leak into services' mount namespaces, or LUKS can't be
closed at the end); os-prober only runs for "alongside". Every command goes through a
`Runner` interface; `--dry-run` prints the plan; unit tests use a fake Runner and golden files.

## 7. Live ISO

kiwi-ng 11 (Fedora 44 package `kiwi-cli` + `kiwi-systemdeps-iso-media`), description in
`iso/kiwi/` derived from fedora-kiwi-descriptions (F44). Image type iso, hybrid, UEFI (shim,
Secure Boot) + BIOS. Packages: `arctic-desktop`, `arctic-installer`, `arctic-live`,
livesys-scripts, kernel, dracut-live, Zen Flatpak preinstalled only if the ISO stays ≤ 2 GiB
(else skipped — note it). Repos: Fedora 44 + updates + the local `out/repo`. Boot menu entries
(GRUB, both firmwares): "Try Arctic Linux" (`rd.live.image arctic.mode=try quiet rhgb`),
"Install Arctic Linux" (`… arctic.mode=install`), "Safe graphics mode" (`nomodeset`),
"Check USB for errors" (`rd.live.check`), "Boot from first disk". GRUB theme `arctic`.
Volume id `Arctic-Linux-0.1`. Output `out/iso/Arctic-Linux-0.1-x86_64.iso` + `.sha256`.

Design assets not copied into `design/` (all 78 icons, 30 app tiles, lockups, wallpapers as
SVG strings) can be exported by running the design bundle in node:
`node -e 'const fs=require("fs"),vm=require("vm");const c={window:{},document:{}};vm.createContext(c);vm.runInContext(fs.readFileSync("<design>/components/bundle.js","utf8"),c);const A=c.window.Arctic; /* A.ICONS, A.APPS, A.CATEGORIES, A.appTileSVG(id,{size:64}), A.mark({size,ink,eye}), A.wallpaper(kind,theme,{fill:1}), A.wordmark(size), A.INSTALL_TITLES … */'`
(pass numbers, not objects, where the builder expects a size — check each builder's signature).

## 8. Build environment notes (this session)

- Docker works (start `dockerd` if the socket is missing). Fedora image:
  `registry.fedoraproject.org/fedora:44`. Containers need
  `--network host -e https_proxy=$HTTPS_PROXY -e HTTPS_PROXY=$HTTPS_PROXY -v /root/.ccr/ca-bundle.crt:/etc/pki/ca-trust/source/anchors/ccr.crt:ro`
  and `update-ca-trust` before dnf. The build scripts must detect this (only add the proxy bits
  when `$HTTPS_PROXY` / the CA file exist) so they also work on GitHub runners.
- `--privileged` is needed for kiwi (loop devices). No KVM: QEMU runs with TCG (slow).
- Disk budget ≈ 30 GB free: clean container caches and intermediate kiwi roots.

## 9. Theming (theme engine, palettes, `arctic-theme`)

The contract between the theme engine, the desktop and the apps that call it (the Arctic
Settings app, the wallpaper picker). Keep these CLIs and formats stable; extend, don't change.

### 9.1 Pieces and paths

| What | Where |
|---|---|
| Theme engine (Python package `themegen`, stdlib + Pillow for wallpapers) | `design/themegen/` → `/usr/share/arctic/themegen/` (+ `data/`: `exports/arctic-tokens.json`, `exports/gtk-arctic-*.css`, `icons/*.svg`, `logos/arctic-mark-16-*.svg`); `dotfiles/install.sh` copies it to `~/.local/share/arctic/themegen/` |
| Engine CLI | `/usr/bin/arctic-themegen` (← `dotfiles/.local/bin/arctic-themegen`; finds the engine in `$ARCTIC_THEMEGEN_DIR`, the repository, `~/.local/share/arctic/themegen`, `/usr/share/arctic/themegen`) |
| Templates | `design/themegen/templates/**/<file>.tmpl` → `<theme>/<file>`; your own extra ones in `~/.config/arctic/templates/` (used by `arctic-theme` for the themes it makes) |
| Static themes | `/usr/share/arctic/themes/{winter,polar-night}/`, rendered by the engine in the spec's `%build`; the same files are committed in `dotfiles/.config/arctic/themes/` (regenerate with `python3 design/tools/gen-desktop-themes.py`; a unit test fails when they are stale) |
| Themes of your own | `~/.config/arctic/themes/<name>/` (wins over a system theme of the same name); `wallpaper` is the one made from the wallpaper |
| Active theme | `~/.config/arctic/current` → the theme folder (absolute link for system themes, `themes/<name>` for yours); `~/.config/arctic/theme` holds its name (the shell watches this file) |
| Settings | `~/.config/arctic/settings.json`: `"auto_colors"` (bool, **default true** when missing), `"wallpaper_mode"` (`auto`\|`dark`\|`light`, default `auto`). Other programs may add keys; `arctic-theme` keeps them |
| Hooks | `/usr/share/arctic/theme-hooks.d/` (owned by arctic-desktop-config; packages drop executables here) and `~/.config/arctic/theme-hooks.d/` |

A theme folder holds: `theme.json` (every design token for the shell; colours as QML
`#AARRGGBB`), `gtk.css` (GTK3/4 + libadwaita colours), `theme.env` (sourced by the arctic-*
scripts: `ARCTIC_THEME`, `ARCTIC_THEME_NAME`, `ARCTIC_GROUND`, `ARCTIC_COLOR_SCHEME`,
`ARCTIC_GTK_PREFER_DARK` 1/0, `ARCTIC_WALLPAPER`, `ARCTIC_LOCK_WALLPAPER`, `ARCTIC_THEME_MODE`,
`ARCTIC_THEME_BASE`; values shell-quoted), `palette.json` (the palette it was made from),
`icons/*.svg` (design icons in the theme's ink, `mark.svg`, `download-on-accent.svg`) — these five
are made by code — plus one file per template: `mango-colors.conf`, `kitty.conf`,
`waybar-colors.css`, `mako.ini`, `fuzzel-colors.ini`, `swaylock.conf`, and whatever other
templates add (e.g. `templates/qt6ct/colors/arctic.conf.tmpl` → `qt6ct/colors/arctic.conf`).

### 9.2 Palette (JSON)

```json
{
  "name": "polar-night",            // [a-z0-9][a-z0-9._-]{0,63}: the theme folder name
  "label": "Polar night",           // shown to people; one line
  "mode": "dark",                   // dark | light
  "base": "polar-night",            // the static theme it builds on (defaults: by mode)
  "colors": { "ground": "#12171e", "frost": "#1a212ad1", "...": "every role below" },
  "wallpaper": "aurora-polar-night",     // a design wallpaper name or an absolute path
  "lock_wallpaper": "fox-polar-night",
  "source": { "...": "optional, informational (palettes made from a wallpaper)" }
}
```

Colour roles (all required, `#rrggbb` or `#rrggbbaa`): `ground surface surface-raised
surface-sunken frost scrim line line-strong ink ink-muted ink-subtle ink-disabled ink-inverse
accent accent-hover accent-pressed on-accent accent-text accent-soft accent-edge focus selection
warm warm-soft success success-soft warning warning-soft error error-soft on-error error-hover
info info-soft aurora-1 aurora-2 aurora-3 term-background term-foreground term-cursor
term-cursor-text-color term-selection-background term-selection-foreground ansi-0 … ansi-15`.
Extra roles (`[a-z][a-z0-9-]*`) are allowed and usable in templates. The engine adds `shadow`
(the design's window-shadow colour: `#000000cc` dark, `#12171e33` light) when it is missing.
Optional roles (`shadow`) are always present in a rendered palette, so templates may use them;
a renderer or test with its own role list (e.g. the app-template tests) must include them.
`label`, `base`, `wallpaper` and `lock_wallpaper` default from the mode's static theme.
Static palettes: `arctic-themegen builtin winter|polar-night` (from `arctic-tokens.json`).

### 9.3 Templates

`templates/**/<file>.tmpl` renders to `<theme>/<file>` (path relative to `templates/`, `.tmpl`
dropped). Placeholders, and nothing else (no conditionals, no loops):

| Placeholder | Output |
|---|---|
| `{{role}}` | the palette value as written |
| `{{role\|hex}}` / `{{role\|hexa}}` | `#rrggbb` (alpha dropped) / `#rrggbbaa` (`ff` if none) |
| `{{role\|nohash}}` / `{{role\|nohasha}}` | `rrggbb` / `rrggbbaa` |
| `{{role\|rgb}}` | `r, g, b` |
| `{{role\|rgba}}` | `rgba(r, g, b, a)`, a from the palette alpha (1 if none), up to 3 decimals |
| `{{role\|alpha:0.35}}` | `rgba(r, g, b, 0.35)` |
| `{{role\|argb}}` | `#aarrggbb` (Qt) |
| `{{name}}` `{{label}}` `{{mode}}` `{{wallpaper}}` `{{lock_wallpaper}}` | palette fields |
| `{{scheme}}` / `{{is_dark}}` | `prefer-dark`\|`prefer-light` / `true`\|`false` |
| `{{font.sans}}` / `{{font.mono}}` | `Figtree` / `JetBrains Mono` (design tokens) |

An unknown placeholder or filter, whitespace inside the braces, a filter on a non-colour, a bad
`alpha:` value or an unterminated `{{` is an error naming `file:line` (render exits 2). A
template may not produce `theme.json`, `gtk.css`, `theme.env`, `palette.json` or `icons/…`.
Later template directories override earlier ones file by file (`--templates DIR`).

Rendering writes each file atomically (temp file + rename, unchanged files untouched),
`theme.json` last, and removes files a previous render left behind. It refuses a non-empty
folder without `palette.json` unless `--force`.

### 9.4 Colours from a wallpaper

`arctic-themegen palette --from-wallpaper IMG` (PNG, JPEG, WebP, GIF, BMP, TIFF, SVG via
rsvg-convert): the picture is decoded at ≤ 256 px (JPEG draft mode), reduced to 128 colours
(median cut) and clustered by weighted k-means in OKLab. The accent seed is the cluster with the
best mix of chroma (≥ 0.04 OKLCH) and hue share (the colourfulness-weighted part of the picture
within ±15°, ≥ 1%), as in Material You's scoring (matugen); wallust (Lab/LCH k-means, contrast
check) and pywal (median cut in RGB) were the other references. From the base palette (Polar
night for dark, Winter for light, or `--base`) every role keeps its OKLab lightness, so the
design's steps survive; then:

- neutrals (grounds, surfaces, lines, inks, terminal background/foreground, ANSI 0/7/8/15) are
  tinted toward the picture's colour cast (its mean OKLab a/b), at most 1.3× their base chroma;
- the accent family (accent, hover, pressed, text, soft, edge, focus, selection, terminal
  cursor/selection) takes the seed's hue and its chroma, clamped to 0.10–0.19;
- aurora-1…3 rotate with the seed; ANSI 1–6 and 9–14 move toward the seed hue by half the
  difference, at most 15°, scaled down so neighbouring hues keep ≥ 80% of their distance;
- status colours (success, warning, error, info, on-error) and warm stay as in the base.

Guaranteed (WCAG 2 contrast, enforced by moving lightness, checked by
`arctic-themegen check`): ink on ground/surface ≥ 7:1 (also on raised/sunken); ink-muted
≥ 4.5:1; accent-text on ground ≥ 4.5:1; on-accent on accent ≥ 4.5:1; focus on ground ≥ 3:1;
ANSI 1–6 and 9–14 on term-background ≥ 4.5:1. Greyscale / low-chroma pictures keep the base
accent (a grey picture gives exactly the base palette). `--mode auto` picks light when the
picture's mean OKLab lightness is above 0.62, else dark; with `--base`, auto means the base's
mode and a clash with `--mode` is an error. Output is deterministic; a 3840×2160 picture takes
≈ 0.1–0.2 s (tested < 1 s). The palette's `source` records `image`, `size`, `mtime_ns`,
`mode_setting`, `seed`, `fallback`, `cast`, `mean_lightness` (and, from arctic-theme,
`fingerprint` of the engine and templates).

### 9.5 `arctic-themegen`

```
arctic-themegen render --palette FILE|-|winter|polar-night --out DIR [--templates DIR]... [--force] [--quiet]
arctic-themegen palette --from-wallpaper IMG [--mode auto|dark|light] [--base NAME|FILE] [--name wallpaper] [--label Wallpaper]
arctic-themegen builtin winter|polar-night
arctic-themegen check --palette FILE [--json]
```

Palettes go to stdout as JSON. Exit status 0 ok, 1 a contrast guarantee fails (`check`), 2 bad
input (message on stderr, `arctic-themegen: …`).

### 9.6 `arctic-theme`

| Command | Does |
|---|---|
| `arctic-theme` / `arctic-theme current` | print the active theme's name |
| `arctic-theme current --json` | `{"name", "label", "mode", "base", "dir", "source": "system"\|"user", "colors": {role: "#…"}, "auto_colors": bool, "wallpaper_mode": "auto"\|"dark"\|"light", "wallpaper": saved choice (design name, path or "")}` |
| `arctic-theme list [--json]` | themes you can switch to; JSON: `[{"name", "label", "mode", "base", "dir", "source", "active": bool, "swatches": {"ground", "surface", "accent", "ink"}}]`; text: `* name<TAB>label<TAB>mode<TAB>source` |
| `arctic-theme set NAME` | switch to NAME (`winter`, `polar-night`, `wallpaper`, or yours). Any NAME but `wallpaper` turns auto colours off. `set wallpaper` (re)makes the wallpaper theme from the current wallpaper — even an Arctic one — and leaves auto colours as they are |
| `arctic-theme auto [on\|off]` | print or set auto colours. `on` follows the wallpaper now; `off` while the wallpaper theme is active goes back to Winter / Polar night of the same mode |
| `arctic-theme mode [auto\|dark\|light]` | print or set light/dark for wallpaper colours; re-applies when auto colours are on or the wallpaper theme is active |
| `arctic-theme toggle` | light ⇄ dark: flips `mode` when auto colours are on (or the wallpaper theme is active), else Winter ⇄ Polar night (Super+Shift+T) |
| `arctic-theme reload` | built-in reloads + hooks for the active theme |
| `arctic-theme apply` | at login (Mango autostart): follow the wallpaper if auto colours are on, else re-link the saved theme; then reload |
| `arctic-theme sync [--force] [--no-redraw]` | if auto colours are on, follow the wallpaper now (no-op when up to date); `arctic-wallpaper` runs it |
| `arctic-theme winter\|polar-night\|light\|dark` | kept from v0.1: `winter`/`polar-night` = `set`; `light`/`dark` = `mode` when auto colours are on, else `set winter`/`set polar-night` |

Following the wallpaper: Arctic's own wallpapers (snowfield, aurora, fox — by name or any file
under the design wallpaper folders) keep the static palettes — Winter or Polar night by
`wallpaper_mode`, or the current light/dark for `auto` — so first boot (Polar night, aurora)
looks exactly like the design. Any other picture makes `~/.config/arctic/themes/wallpaper`
(`label` "Wallpaper", `lock_wallpaper` the base's) and switches to it; it is remade only when
the picture (path, size, mtime), `wallpaper_mode` or the engine/templates changed.
Exit status: 0 ok, 1 failure (message on stderr), 2 usage / unknown theme. Commands that
change things take a lock (`~/.config/arctic/.theme.lock`).

`arctic-wallpaper NAME|PICTURE` saves the choice, runs `arctic-theme sync --no-redraw` (skip with
`ARCTIC_WALLPAPER_NO_SYNC=1`), then draws the wallpaper; Arctic wallpapers are drawn in the
theme's variant (`ARCTIC_THEME_BASE` when it is winter/polar-night, else by `ARCTIC_THEME_MODE`).
Without arguments it only redraws (no sync). The wallpaper picker's "Match colours to wallpaper"
switch runs `arctic-theme auto on|off` and reads `settings.json`.

### 9.7 Live reload and hooks

After a switch `arctic-theme` links `current` (atomic rename), rewrites `~/.config/arctic/theme`,
and reloads, best effort (a program that isn't running is skipped):

| Program | How |
|---|---|
| Shell (Quickshell) | automatic: `Theme.qml` watches `~/.config/arctic/theme` and `current/theme.json`; also `arctic-shell-ipc shell reload` (background) |
| Mango | `mmsg dispatch reload_config` (when `MANGO_INSTANCE_SIGNATURE` is set; mango ≥ 0.17.3 IPC) |
| kitty | `pkill -USR1 -u $UID -x kitty` |
| waybar (fallback bar) | `pkill -USR2 -u $UID -x waybar` |
| mako | `makoctl reload` |
| GTK | `gsettings set org.gnome.desktop.interface color-scheme prefer-dark\|prefer-light` and `gtk-theme adw-gtk3-dark\|adw-gtk3` (plain `Adwaita-dark\|Adwaita` only when adw-gtk3 is not installed; set to `''` first when unchanged, so GTK re-reads gtk.css). arctic-theme is the one writer of `gtk-theme` on a switch; the dconf defaults and the GTK theme hook use the same names, so a switch changes it once; `gtk-application-prefer-dark-theme` in `~/.config/gtk-3.0/settings.ini` |
| Wallpaper | `arctic-wallpaper` (background redraw; not for `sync --no-redraw`) |

Then every executable in `/usr/share/arctic/theme-hooks.d/` and `~/.config/arctic/theme-hooks.d/`
runs, in file-name order (a file of yours replaces the system hook with the same name; a
non-executable one disables it; `*~`, `.rpmnew`, `.rpmsave`, `.disabled` and dot files are
skipped), with `ARCTIC_THEME_DIR=<real path of the active theme folder>`,
`ARCTIC_THEME_MODE=dark|light`, `ARCTIC_THEME_NAME=<name>`, stdin from /dev/null and stdout sent
to stderr. Hooks must be fast: each is stopped (its process group killed) after 5 s. A failing or
slow hook is reported on stderr and never fails the switch.
