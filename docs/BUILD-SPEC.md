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
| `arctic-release` | `/usr/lib/os-release` (NAME="Arctic Linux", ID=arctic, ID_LIKE=fedora, VERSION_ID=0.1, PRETTY_NAME="Arctic Linux 0.1 (Fedora 44 base)", LOGO=arctic-logo-icon, HOME_URL), `/etc/os-release` symlink, `/usr/lib/rpm/macros.d/macros.dist` (%fedora 44, %dist .fc44), `/etc/dnf/plugins/copr.d/arctic.conf` ([main] distribution=fedora), presets `/usr/lib/systemd/system-preset/80-arctic.preset`, `/usr/lib/systemd/user-preset/80-arctic.preset` | Provides `system-release`, `system-release(44)`, `system-release(releasever) = 44`, `base-module(platform:f44)`; Requires `fedora-repos(44)`; Conflicts `fedora-release-common`, `generic-release`. Model on Fedora's generic-release.spec. MUST be proven installable in place of fedora-release in a F44 container (`dnf install --allowerasing arctic-release`). |
| `arctic-logos` | `/usr/share/pixmaps/{fedora,system}-logo*.png` equivalents, `/usr/share/icons/hicolor/*/apps/arctic-logo-icon.png`, `/usr/share/arctic/logos/*.svg` | Provides `system-logos`, `system-logos(%{version})`; Conflicts `fedora-logos`, `generic-logos`. Must satisfy what sddm/plymouth require from system-logos. |
| `arctic-backgrounds` | `/usr/share/backgrounds/arctic/*.svg` + rendered `*.png` (3840×2160) | The 6 design wallpapers. Provides `desktop-backgrounds-compat` if needed by sddm. |
| `arctic-fonts` | `/usr/share/fonts/arctic/Figtree-*.woff2` (+ `.ttf` if converted) | JetBrains Mono comes from `jetbrains-mono-fonts-all`. |
| `arctic-selinux` | `/usr/share/selinux/packages/arctic-nix.pp` | Built from `packaging/selinux/arctic-nix.te/.fc` (`/nix` contexts, see PLAN §6.6). %post: semodule install; `%selinux_modules_install`. |
| `arctic-desktop-config` | `/etc/skel/` ← `dotfiles/` (minus install.sh/README), `/usr/bin/arctic-*` ← `dotfiles/.local/bin/*`, `/usr/share/arctic/keys.txt`, `/usr/share/arctic/themes/{winter,polar-night}/`, `/etc/arctic/default-apps` (defaults) | Requires the desktop runtime (§3). Helper scripts must look in XDG dirs: `~/.local/share/arctic/…` then `/usr/share/arctic/…`, and wallpapers in `/usr/share/backgrounds/arctic`. |
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
| `Next` / `Back` | — | `GetWizard` result (Next validates the current step first; network step only passes when online) |
| `Goto` | `{id}` | `GetWizard` result (only to done steps — used by Summary "Change" links) |
| `ScanWifi` | — | `{networks:[{ssid,signal:0-100,secure:bool,connected:bool}]}` |
| `ConnectWifi` | `{ssid, password}` | `{ok}` or error `{code:"auth"\|"timeout", message}` |
| `NetworkState` | — | `{online:bool, wired:bool, ssid?:string}` |
| `CheckPassphrase` | `{text}` | `{score:0-4, label:"Too short"\|"Weak"\|"Fair"\|"Good"\|"Strong", words:int, ok:bool}` (ok = score ≥ 2 "Fair") |
| `SuggestPassphrase` | — | `{text:"four random words"}` (EFF short wordlist, embedded) |
| `SuggestAccount` | `{full_name}` | `{username, hostname}` (hostname = `{username}-{model}` from DMI, lowercased, `-` joined) |
| `SetSecrets` | `{luks_passphrase?, user_password?}` | `{ok}` (kept in memory only, never logged or written) |
| `EstimateDownload` | `{selection}` | `{apps:int, bytes:int, label:"9 apps · 1.4 GB download"}` |
| `GetSummary` | — | `{rows:[{step, label, value}], warning, primary_label}` (primary "Erase disk and install" or "Install alongside {OS}") |
| `Start` | — | `{ok}` then events |
| `RetryModule` / `SkipModule` | `{id}` | `{ok}` |
| `SaveLog` | — | `{path}` (copies the log to the live USB if writable, else /tmp) |
| `Reboot` | — | `{ok}` |
| `Subscribe` | — | `{ok}` then events on this connection |

- Events:
  - `{"event":"progress","percent":0-100,"phase":"disk"|"copy"|"configure"|"bootloader"|"apps"|"finalize","status":"Installing Zed, your code editor…","eta_seconds":420,"substeps":[{"id":"disk","label":"Preparing the disk","state":"done"|"active"|"todo"},…4 items: disk, system ("Copying Arctic Linux"), apps ("Installing your apps"), finish ("Setting up your account")]}`
  - `{"event":"module","id":"zed","name":"Zed","status":"queued"|"downloading"|"installed"|"failed"|"skipped"|"deferred","percent":0-100}`
  - `{"event":"attention","module":{"id","name"},"message":"The download server didn't answer.","optional":true}` → UI shows step 11 (Try again / Skip {App}); core failures: `{"event":"failed","message":"…","fatal":true}` → Save log / Try again.
  - `{"event":"done","apps_installed":9,"first_name":"Noa"}`
  - Status lines follow `design/guidelines/20-installer-copy.md`.

### 4.1 Wizard steps (ids fixed; copy = design/guidelines/20-installer-copy.md)

| # | id | data | options |
|---|---|---|---|
| 1 | `welcome` | `{language:"en_US.UTF-8"}` | `{languages:[{id,name(native),english}], suggested}` |
| 2 | `keyboard` | `{layout:"us", variant:""}` | `{layouts:[{layout,variant,name,description,suggested:bool}]}` |
| 3 | `network` | `{}` | `{online,wired,ssid}` (+ ScanWifi/ConnectWifi); auto-skipped when wired & online |
| 4 | `timezone` | `{timezone:"Asia/Jerusalem", auto_time:true}` | `{detected:{city,timezone,source:"network"\|"default"}, regions:{Europe:[{city,timezone}],…}}` |
| 5 | `disk` | `{disk:"/dev/nvme0n1", mode:"erase"\|"alongside"}` | `{disks:[{path,model,size_bytes,size_label,removable,install_media:bool,existing_os:[…],alongside_possible:bool,alongside_label:"Uses 120 GB of free space"}]}` (install media excluded; alongside needs ≥ 40 GB free) |
| 6 | `encryption` | `{enabled:true}` | `{min_score:2}` (passphrase via SetSecrets) |
| 7 | `account` | `{full_name, username, hostname, autologin:false}` | `{hostname_hint:"Suggested from your name and computer"}` (password via SetSecrets) |
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
space), copy the live root (`/run/rootfsbase` if present else the mounted squashfs; rsync -aAXH),
remove live-only packages (arctic-live, livesys-scripts, arctic-installer, dracut-live),
machine-id, systemd-firstboot, fstab/crypttab, user (useradd -R, pre-hashed yescrypt/SHA-512 via
`openssl passwd -6` or Go crypt), sddm enable, `/etc/arctic/mango/keyboard.conf`,
`/etc/arctic/default-apps`, kernel-install/dracut, grub2-mkconfig, efibootmgr/grub2-install,
app diff (dnf remove/install in chroot, flatpak from host with FLATPAK_* into /mnt, nix via
`nix --store /mnt profile add`), setfiles relabel, unmount. Every command goes through a
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
