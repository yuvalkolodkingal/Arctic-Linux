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
| `arctic-release` | `/usr/lib/os-release` (NAME="Arctic Linux", ID=arctic, ID_LIKE=fedora, VERSION_ID=0.1, PRETTY_NAME="Arctic Linux 0.1 (Fedora 44 base)", LOGO=arctic-logo-icon, HOME_URL), `/etc/os-release` symlink, `/usr/lib/rpm/macros.d/macros.dist` (%fedora 44, %dist .fc44), `/etc/dnf/plugins/copr.d/arctic.conf` ([main] distribution=fedora), `/usr/share/dnf5/repos.d/arctic.repo` (the Arctic package repository, `enabled=0` with a placeholder address until the Arctic COPR is published), presets `/usr/lib/systemd/system-preset/80-arctic.preset` (also: no sshd, as Fedora's desktop editions), `/usr/lib/systemd/user-preset/80-arctic.preset` | Provides `system-release`, `system-release(44)`, `system-release(releasever) = 44`, `base-module(platform:f44)`; Requires `fedora-repos(44)`; Conflicts `fedora-release-common`, `generic-release`. Model on Fedora's generic-release.spec. MUST be proven installable in place of fedora-release in a F44 container (`dnf install --allowerasing arctic-release`). |
| `arctic-logos` | `/usr/share/pixmaps/{fedora,system}-logo*.png` equivalents, `/usr/share/icons/hicolor/*/apps/arctic-logo-icon.png`, `/usr/share/arctic/logos/*.svg` | Provides `system-logos`, `system-logos(%{version})`; Conflicts `fedora-logos`, `generic-logos`. Must satisfy what sddm/plymouth require from system-logos. |
| `arctic-backgrounds` | `/usr/share/backgrounds/arctic/*.svg` + rendered `*.png` (3840×2160) | The 6 design wallpapers. Provides `desktop-backgrounds-compat` if needed by sddm. |
| `arctic-fonts` | `/usr/share/fonts/arctic/Figtree-*.woff2` (+ `.ttf` if converted) | JetBrains Mono comes from `jetbrains-mono-fonts-all`. |
| `arctic-selinux` | `/usr/share/selinux/packages/arctic-nix.pp` | Built from `packaging/selinux/arctic-nix.te/.fc` (`/nix` contexts, see PLAN §6.6). %post: semodule install; `%selinux_modules_install`. |
| `arctic-desktop-config` | `/etc/skel/` ← `dotfiles/` (minus install.sh/README and the files below), `/usr/bin/arctic-*` ← `dotfiles/.local/bin/*`, `/usr/share/arctic/mango/*.conf` ← `dotfiles/.config/mango/arctic/` (skel has links to them), `/usr/share/arctic/keys.txt`, `/usr/share/arctic/themes/{winter,polar-night}/` (skel's `~/.config/arctic/current` links there), `/etc/arctic/default-apps` (defaults) | Requires the desktop runtime (§3). Helper scripts must look in XDG dirs: `~/.local/share/arctic/…` then `/usr/share/arctic/…`, and wallpapers in `/usr/share/backgrounds/arctic`. |
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
| `EstimateDownload` | `{selection}` | `{apps:int, drivers?:int, bytes:int, label:"9 apps · 1.4 GB download"}` (drivers are not apps: `"8 apps + 2 drivers · 3 GB download"`) |
| `GetSummary` | — | `{rows:[{step, icon, label, value}], warning, primary_label}` (rows for welcome, keyboard, timezone, disk, encryption, account, apps — each `step` is a Goto target; primary "Erase disk and install" or "Install alongside {OS}"). When a driver was detected an 8th row follows: `{step:"apps", icon:"cpu", label:"Drivers", value:"NVIDIA driver for your NVIDIA GeForce RTX 4060 Max-Q / Mobile; …"}` (+ ". Secure Boot is on: you’ll confirm the driver’s key once after restarting" when a built driver needs the key; "None — …" when all were unticked). The UI takes the row's `icon` |
| `Start` | — | `{ok}` then events. Also "Try again" after a failure. Re-probes the disks first: if the chosen disk is gone, is not the same device (model/serial/WWN/size) or, alongside, its partitions or free space changed, it answers `{code:"state"}` and refuses until the Disk step is passed again |
| `RetryModule` / `SkipModule` | `{id}` | `{ok}` |
| `SaveLog` | — | `{path, on_usb, device?, label?, safe_to_remove, message}`: to a FAT/exFAT file system on a removable disk that is not the install medium (mounted in place, else mounted, written, synced and unmounted: `path` is then the file's path on the stick and `safe_to_remove` true), else `/home/liveuser` or /tmp (lost on restart). `message` is the sentence to show |
| `Reboot` | — | `{ok}` |
| `Subscribe` | — | `{ok}` then events on this connection |

- Events:
  - `{"event":"progress","percent":0-100,"phase":"disk"|"copy"|"configure"|"bootloader"|"apps"|"finalize","status":"Installing Zed, your code editor…","eta_seconds":420,"substeps":[{"id":"disk","label":"Preparing the disk","state":"done"|"active"|"todo"},…4 items: disk, system ("Copying Arctic Linux"), apps ("Installing your apps"), finish ("Setting up your account")]}`
  - `{"event":"module","id":"zed","name":"Zed","status":"queued"|"downloading"|"installed"|"failed"|"skipped"|"deferred","percent":0-100}`
  - `{"event":"attention","module":{"id","name"},"message":"The download server didn't answer.","optional":true}` → UI shows step 11 (Try again / Skip {App}); core failures: `{"event":"failed","message":"…","fatal":true,"can_change":true}` → Save log / Try again / Change (Back or Goto).
  - `{"event":"done","apps_installed":9,"first_name":"Noa","drivers"?:[{id,name,device,status:"installed"|"deferred"|"skipped",text}],"secure_boot"?:{code,title,intro,steps:[…],note,failed?}}` — `drivers` lists what happened to each ticked driver with a sentence for it (drivers get no `module` events and are not in `apps_installed`); `secure_boot` is present when the akmods signing key waits for enrolment in shim's MokManager on the next restart (Secure Boot enforced, UEFI, a driver built by akmods): `code` is the one-time password (8 digits, typed on the number row — MokManager reads the keyboard as US QWERTY), `steps` the MokManager screens. With `failed:true` (mokutil refused) there is no code and the steps say how to enroll the key by hand. Driver failures use the `attention` event like apps (title "The NVIDIA driver couldn’t be installed", skip label "Skip the driver").
  - Status lines follow `design/guidelines/20-installer-copy.md`.

### 4.1 Wizard steps (ids fixed; copy = design/guidelines/20-installer-copy.md)

| # | id | data | options |
|---|---|---|---|
| 1 | `welcome` | `{language:"en_US.UTF-8"}` | `{languages:[{id,name(native),english}], suggested}` |
| 2 | `keyboard` | `{layout:"us", variant:"", xkb:{layout, variant, options, keymap, latin}}` (`xkb` is read-only, what the choice gives: Latin layouts alone; non-Latin ones as `us,<layout>` with `grp:alt_shift_toggle` and a Latin console keymap). A valid SetStep also writes `xkb` to the live system's `/etc/arctic/mango/keyboard.conf` (sourced by the live session); the UI then runs `mmsg dispatch reload_config`, so passwords are typed as on the installed system | `{layouts:[{layout,variant,name,description,suggested:bool}]}` |
| 3 | `network` | `{}` | `{online,wired,ssid,driver_hint?}` (+ ScanWifi/ConnectWifi); auto-skipped when wired & online. `driver_hint` is set when a detected Wi-Fi card only works once its driver is installed (Broadcom wl): how to get online meanwhile |
| 4 | `timezone` | `{timezone:"Asia/Jerusalem", auto_time:true}` | `{detected:{city,timezone,source:"network"\|"default"}, regions:{Europe:[{city,timezone}],…}}` |
| 5 | `disk` | `{disk:"/dev/nvme0n1", mode:"erase"\|"alongside"}` | `{disks:[{path,model,size_bytes,size_label,removable,install_media:bool,existing_os:[…],alongside_possible:bool,alongside_label:"Uses 120 GB of free space"}]}` (install media excluded; alongside needs ≥ 40 GB free, on UEFI an ESP to share, on MBR room for two primary partitions) |
| 6 | `encryption` | `{enabled:true}` | `{min_score:2}` (passphrase via SetSecrets) |
| 7 | `account` | `{full_name, username, hostname, autologin:false}` (username: not a user or group the copied system has) | `{hostname_hint:"Suggested from your name and computer"}` (password via SetSecrets) |
| 8 | `apps` | `{selection:{drivers:["nvidia","intel-media"],browser:["zen"],editor:["zed"],…}}` | catalog: `{categories:[{id,name,choice:"one"\|"any",note,hardware?}], modules:[{id,name,summary,category,default,tile,download_mb,source,in_live_image,device?}]}` — the `drivers` category (`hardware:true`) comes first and is present only when a driver matched this computer's hardware; its modules carry `device` (the detected card's name, also filled into `summary`) and are `default` (ticked) when detected. Selecting a driver whose hardware wasn't found is a field error on `drivers` |
| 9 | `summary` | — | via GetSummary |
| 10 | `install` | — | events |
| 11 | (attention/error, not a step) | | |
| 12 | `done` | — | `{apps_installed, first_name}`; options `{card_title, card, secondary, drivers?, secure_boot?}` (as in the `done` event) |

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

**Drivers** (`modules/drivers/<id>/`): the `drivers` category in `catalog.toml` has
`hardware = true` (must be `choice = "any"`, not required) and is listed first. Its modules are
offered — ticked — only when one of their `[[detect]]` rules matches a PCI device of the
computer (engine start: `/sys/bus/pci/devices/*/{vendor,device,class,boot_vga,driver}` named
from hwdata's `pci.ids`; Secure Boot from efivarfs `SecureBoot`/`SetupMode` and shim's
`MokSBStateRT`). The schema is strict (unknown keys are errors):

```toml
[[detect]]                    # one or more; any rule matching any device offers the driver
bus = "pci"                   # only "pci"
vendor = "10de"               # four lower-case hex digits
class = ["0300", "0302"]      # class+subclass, ≥ 1 (0300 VGA, 0302 3D controller, 0380, 0280 Wi-Fi)
device_min = "1e00"           # inclusive range … (either bound may be left out)
device_max = "ffff"
# devices = ["43a0", "43b1"]  # … or an explicit list, not both
# exclude = ["1f9d"]          # never these devices
[akmod]                       # a kernel module akmods builds (first [[install]] must be dnf
name = "nvidia"               #   with rpmfusion-nonfree): akmods --akmod <name>
module = "nvidia"             #   modinfo -k <kver> <module> proves the build
[boot]
kernel_args = ["rd.driver.blacklist=nouveau,nova_core", "modprobe.blacklist=nouveau,nova_core", "nvidia-drm.modeset=1"]
luks_display_args = ["plymouth.use-simpledrm=1"]  # + when LUKS and the device draws the boot screen
network_hint = "Your {device} needs …"             # Network step note ({device} = detected name)
```

`[[detect]]`, `[akmod]`, `[boot]` and `network_hint` are only allowed in a hardware category and
required there (`[[detect]]`); drivers can't be hidden or `always`. `{device}` in `summary` is
filled with the detected device's name. Shipped: `nvidia` (Turing and newer, `akmod-nvidia` +
`xorg-x11-drv-nvidia-cuda` + `libva-nvidia-driver`), `nvidia-580xx` (Maxwell–Volta, the last
series for them; conflicts with `nvidia`), `broadcom-wl` (`akmod-wl`, chips with no working
in-kernel driver), `intel-media` (RPM Fusion `intel-media-driver`, Broadwell and newer) and
`amd-video` (`mesa-va-drivers-freeworld` installed beside Fedora's VA driver — in F44
`mesa-dri-drivers` provides `mesa-va-drivers`, so it is never swapped — and a
`mesa-vulkan-drivers-freeworld` swap; GCN/r600-class device ranges only, not R100–R500). A
`swap` runs only when `rpm -q <old>` finds that exact package (dnf swap would follow provides).
Kepler and
older NVIDIA cards get nothing (their drivers have no GBM, which Mango needs). The
`[runtimes]` entry `akmods` sizes the build tools, counted once. Mock fixtures:
`internal/hw/fixtures.go` (`arcticd --mock --mock-hw NAME`, `arctic-install plan --hardware
mock:NAME [--secure-boot] [--offline]`; the mock default is `nvidia-laptop`, Secure Boot on).

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
unused runtimes when not), setfiles relabel, unmount. Drivers (internal/installer/drivers.go):
installed in the chroot in the apps' dnf transaction with the RPM Fusion repositories; for an
akmod driver `akmods` is installed with `kernel-devel-matched-<kver>` of each installed kernel
(else, when that version has left the repositories, the newest complete kernel: `kernel
kernel-core kernel-modules kernel-modules-core kernel-modules-extra kernel-devel-matched` — never
the partial kernel dnf would pick for akmods alone) and its key created (`kmodgenca -a`) first;
after the transaction the engine waits on `/run/akmods/akmods.lock` for the %posttrans build
(which installs its kmod with dnf), then `akmods --force --kernels <kver> --akmod <name>` runs
for each kernel with its kernel-devel and `modinfo` checks the module (failure → attention: Try
again / Skip, which removes the packages again; unattended → put off: no kernel arguments, the
package's own nouveau blacklist removed again, and the driver goes to pending.json for
arctic-firstboot). akmods' `modprobe` of freshly built modules when the kernel version equals
the live one is accepted (it cannot take over a bound device). The `[boot]` kernel arguments of
the built drivers go on with `grubby --update-kernel=ALL --args=…` (boot entries,
GRUB_CMDLINE_LINUX and /etc/kernel/cmdline) — so only when an NVIDIA driver is built. With
Secure Boot enforced on UEFI, `mokutil --import /etc/pki/akmods/certs/public_key.der
--hash-file /dev/stdin` gets the SHA-512 crypt hash of the engine's random one-time code (shown
on the Done screen, never logged); if the install fails afterwards, cleanup runs `mokutil
--revoke-import`. Offline at Start,
drivers are not tried: they go to `/var/lib/arctic/pending.json` with `akmod` and
`kernel_args`, plus `"mok_hash":"/var/lib/arctic/mok.hash"` (Secure Boot), and
arctic-firstboot installs (akmods with kernel-devel and the key before the driver, as the
engine), builds, adds the arguments and queues the key once online.
Hybrid laptops keep rendering on the integrated GPU (wlroots uses the `boot_vga` card);
`/etc/profile.d/arctic-graphics.sh` sets `LIBVA_DRIVER_NAME=nvidia`, `NVD_BACKEND=direct` and
`__GLX_VENDOR_LIBRARY_NAME=nvidia` only when NVIDIA's driver drives the boot display. The target directory is made a private
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
