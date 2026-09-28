# Arctic Linux — Execution Plan (v2)

This plan covers the backend: the installer engine, the module catalog, packaging, the live ISO, CI
and the release. **Frontends and dotfiles are out of scope until they are provided.** That means the
installer screens, the SDDM theme visuals, the fetch animation and all user configs. Each one has a
defined hook point in this plan.

Facts marked ✅ were checked against primary sources (Fedora mdapi/src, Flathub API, search.nixos.org,
upstream repos) on 2026-09-27. Facts marked 🔍 are unverified and must be proven in the phase named next to them.

---

## 1. Decisions

| # | Decision |
|---|---|
| D1 | **Name:** Arctic Linux. The internal identifier and package prefix is `arctic` (`arctic-installer`, `arctic-release`, …). The repository was called `O-Tism` until it was renamed `Arctic-Linux` on GitHub (0.2.1); the Go module path keeps `github.com/yuvalkolodkingal/o-tism`. |
| D2 | **Base:** Fedora **stable**. Fedora 44 is current ✅ (GA 2026-04-28). Fedora 45 GA is due 2026-10-20 ✅. Development starts on F44, and the first public release will most likely ship on F45 (see §10). |
| D3 | **WM:** "Mango" = **MangoWM**, formerly MangoWC/maomaowm ✅. Upstream is now `github.com/mangowm/mango`, v0.17.3. The package is `mangowm`, the binary `mango`, the IPC client `mmsg`, and the session file `mango.desktop`. We need version ≥ 0.17.1, which ships `mango-session.target`. |
| D4 | **One generic live ISO.** Its boot menu offers **Try Arctic Linux** (the full OS running from the USB, nothing written to disk) and **Install Arctic Linux** (goes straight into the installer). |
| D5 | **Installer** = a step-by-step wizard for non-experts, with a **Ninite-style app picker** as one of its steps. The engine owns the whole flow, so the frontend only draws it. |
| D6 | **Online installer.** The base system comes from the ISO, and the apps you pick are downloaded during install. |
| D7 | **Login manager:** SDDM with a custom `arctic` theme. The visuals come with the design. |
| D8 | **Flatpak** (Flathub) is acceptable for apps Fedora doesn't ship. |
| D9 | **Disk layout:** GPT, 1 GiB ESP, LUKS2 on by default, btrfs subvolumes `@ @home @var_log @nix`, zstd. The additions GRUB needs are in §6.2. |
| D10 | **Installer backend:** Go. |
| D11 | **Defaults, every one swappable:** kitty · zsh (bash installed too) · animated fetch · Zen · Zed · yazi + Thunar · Collabora Office · VLC · Nix preinstalled. |
| D12 | There is **no ISO generator and no per-user ISO.** A profile file exists only for unattended/CI installs. |

## 2. Architecture

```
USB boot menu (GRUB)
 ├─ Try Arctic Linux      → arctic.mode=try
 ├─ Install Arctic Linux  → arctic.mode=install
 ├─ Safe graphics         → nomodeset
 └─ Check USB for errors  → rd.live.check
          │
          ▼
Live system (Fedora 44 + MangoWM), livesys → SDDM autologin (liveuser, mango.desktop)
 └─ mango exec-once → arctic-live-session reads /proc/cmdline
      ├─ try:     normal desktop (bar, apps) + "Install Arctic Linux" button/launcher
      └─ install: installer frontend full-screen (placeholder until the frontend is provided)
                         │  JSON API over unix socket (/run/arcticd.sock, group wheel)
                         ▼
arcticd (Go, root, socket-activated) ── the installer engine
 ├─ Wizard model: ordered steps, state, defaults, validation   (§5)
 ├─ Catalog: modules + slots (shipped in the ISO)               (§4)
 ├─ Planner: selection → ordered, idempotent step plan
 └─ Executor: disk → copy live image → configure → bootloader
             → app diff (remove / add: dnf, Flatpak, Nix) → hooks → relabel → done
                         ▼
Installed Arctic Linux: SDDM (arctic theme) → mango.desktop → graphical-session.target
```

### Key design choices

1. **Install by copying the live image, then changing only what's different.** This is how Fedora's own
   installer (Anaconda) installs from live media. The live root filesystem already contains the full base
   system, the default desktop and the default native apps. The engine copies it to the target, which is
   local and takes minutes. It then removes live-only packages, uninstalls default apps the user unticked,
   and downloads only the extra apps the user ticked. Default installs download only Zed and Collabora.
   *Fallback if the Phase 3 spike fails:* a `dnf5 --installroot` bootstrap. The researched sequence for it
   is kept in Appendix A.
2. **Everything is a module.** Apps, the WM, desktop components and Nix are all manifests. The engine has
   no app-specific code.
3. **Slots.** Each category (`browser`, `terminal`, …) is a slot with a default module and a rule for
   single or multiple choice. The Ninite picker is a rendering of the slots.
4. **The engine owns the wizard.** Steps, defaults, validation and copy intent live in Go. The frontend is
   a thin renderer, and an unattended profile walks the same steps (used by CI).
5. **No chroot for Flatpak or Nix.** Both are driven from the live host into `/mnt`, the same way
   Anaconda and nixos-install do it ✅. Nothing needs systemd or D-Bus inside a chroot.

## 3. Repository layout

```
Arctic-Linux/  (repo; product = Arctic Linux)
├── cmd/
│   ├── arcticd/              # installer engine daemon (root, socket-activated)
│   └── arctic-install/       # CLI client: --profile x.toml --unattended | --dry-run | --interactive-stub
├── internal/
│   ├── wizard/               # step model: steps, state machine, defaults, validation, i18n keys
│   ├── catalog/              # manifest loader, slots, deps/conflicts graph, catalog.json export
│   ├── profile/              # unattended profile schema (CI/automation only)
│   ├── planner/              # selection + hardware → ordered plan; diff vs live image content
│   ├── executor/             # Runner interface: real / dry-run / fake; retries; resumable checkpoints
│   ├── disk/                 # probe, partition, LUKS2, btrfs subvols, mount, fstab/crypttab
│   ├── copy/                 # live rootfs → /mnt copy (rsync -aAXH semantics), live cleanup
│   ├── system/               # machine-id, systemd-firstboot --root, users (pre-hashed pw), services
│   ├── bootloader/           # kernel-install/dracut, grub2-mkconfig, efibootmgr / grub2-install
│   ├── pkg/{dnf,flatpak,nix} # backends + progress parsers
│   ├── selinux/              # setfiles -r relabel, .autorelabel fallback
│   ├── network/              # NetworkManager D-Bus (Wi-Fi scan/connect), connectivity checks
│   ├── hwdetect/             # firmware mode, CPU/GPU (NVIDIA → RPM Fusion akmods), laptop, disks
│   ├── api/                  # versioned JSON API + event stream
│   └── log/                  # structured logs → /var/log/arctic-install/ on target
├── modules/                  # catalog manifests, one dir per module (see §4)
├── profiles/{defaults.toml,ci/*.toml}
├── iso/kiwi/                 # kiwi-ng description (derived from fedora-kiwi-descriptions)
├── packaging/                # RPM specs; built by tools/build-rpms.sh, signed and published to the
│                             #   Arctic package repository on GitHub Pages (BUILD-SPEC §9; no COPR)
│   ├── mangowm.spec              # fork of Terra's spec, built on Fedora's wlroots 0.20 + scenefx 0.5
│   ├── arctic-release.spec       # modeled on generic-release (os-release, macros.dist, repos, copr conf)
│   ├── arctic-logos.spec         # Provides system-logos (Fedora trademark rules)
│   ├── arctic-selinux.spec       # /nix file contexts policy module
│   ├── sddm-wayland-mango.spec   # SDDM greeter running on mango (layer-shell)
│   ├── arctic-sddm-theme.spec    # placeholder Qt6 QML theme ← DESIGN HOOK
│   ├── arctic-desktop-config.spec# mango base config, user units (polkit, idle, nm-applet), skel
│   ├── arctic-fetch.spec         # fetch wrapper (fastfetch) ← DOTFILES/DESIGN HOOK for animation
│   ├── arctic-live.spec          # livesys session script, live-session launcher, installer .desktop
│   └── arctic-installer.spec     # arcticd, CLI, catalog, systemd units
├── hooks/
│   ├── frontend/README.md    # API contract the frontend implements against
│   └── dotfiles/             # empty until dotfiles are provided
├── test/{vm,fixtures}/       # QEMU harness
├── docs/
└── Makefile, go.mod
```

## 4. Module catalog

### 4.1 Manifest (`modules/<slot>/<id>/module.toml`)

```toml
id          = "zen"
name        = "Zen Browser"
slot        = "browser"
summary     = "Fast, private Firefox-based browser"   # one line for the picker
default     = true
in_live_image = true          # already installed in the live rootfs → no download if kept
gpu         = true            # GUI app → Nix method forbidden (needs nixGL on Fedora)

requires    = []
conflicts   = []

[[install]]                   # first available method wins
method   = "flatpak"
remote   = "flathub"
ref      = "app.zen_browser.zen"
verified = true
runtime  = "org.freedesktop.Platform//25.08"
download_mb = 160             # regenerated by CI from the Flathub API

[defaults]                    # declarative, written to /etc/xdg/mimeapps.list
desktop_id = "app.zen_browser.zen.desktop"
mime = ["x-scheme-handler/http", "x-scheme-handler/https", "text/html"]

[session]                     # only for desktop components
# unit = "arctic-polkit-agent.service"  |  dbus = true  |  exec_once = "..."
# binds = ["bind=Alt,Return,spawn,kitty"]  → written to /etc/arctic/mango/apps.conf

[hooks]                       # only vetted scripts shipped inside the catalog; never user input
post = []
```

**Security rules:** profiles and API input can only reference module IDs. They can never contain commands.
Hooks are fixed scripts in the signed `arctic-installer` RPM.

### 4.2 Slots and defaults (Fedora 44, verified ✅)

| Slot (picker category) | Choice | Default | Source (priority order) | Alternatives |
|---|---|---|---|---|
| Browser | single | **Zen** | Flatpak `app.zen_browser.zen` (verified) · Terra `zen-browser` | Firefox (dnf), Brave `com.brave.Browser`, Ungoogled Chromium `io.github.ungoogled_software.ungoogled_chromium`, Chromium (dnf) |
| Code editor | single/none | **Zed** | Flatpak `dev.zed.Zed` (community, unverified, ~940 MB runtime) · Terra `zed` | VSCodium `com.vscodium.codium`, Neovim (dnf) |
| Terminal | single | **kitty** | dnf `kitty` (+ `kitty-shell-integration`) | foot, alacritty (dnf) |
| Shell | single default + extras | **zsh** (default), bash (always) | dnf | fish (dnf) |
| File manager (TUI) | multi | **yazi** | COPR `lihaohong/yazi` (26.9.1) · nix `yazi` | — |
| File manager (GUI) | multi | **Thunar** | dnf `Thunar` (capital T; pulls gvfs, tumbler) | Nautilus, PCManFM-Qt (dnf) |
| Office | single/none | **Collabora Office** | Flatpak `com.collaboraoffice.Office` (verified) | LibreOffice (dnf / `org.libreoffice.LibreOffice`), ONLYOFFICE `org.onlyoffice.desktopeditors` |
| Video | single | **VLC** | dnf `vlc` + RPM Fusion `vlc-plugins-freeworld` | mpv (dnf) |
| Fetch | single/none | **arctic-fetch** | Arctic repository (wraps `fastfetch`) | fastfetch plain |
| Extras | multi | — | per module | e.g. Steam, OBS, Discord, GIMP, Spotify … (added over time) |

**Collapsed "Desktop components" group**, with defaults most users never touch:

| Slot | Default | Alternatives |
|---|---|---|
| Bar | waybar (`ext/workspaces` module; Fedora's waybar 0.15 has no mango module) | mangobar |
| Launcher | fuzzel | rofi (2.0, has Wayland support) |
| Notifications | mako | dunst, SwayNotificationCenter |
| Polkit agent | lxqt-policykit | mate-polkit, xfce-polkit |
| Lock / idle | swaylock + swayidle | gtklock |
| Wallpaper | swaybg | — |

**Mandatory (not shown in the picker):**
- `desktop-base`: mangowm, sddm, sddm-wayland-mango, arctic-sddm-theme, layer-shell-qt, the xdg-desktop-portal family (-wlr, -gtk), slurp, grim, wl-clipboard, cliphist, pipewire (+ pulseaudio, alsa, wireplumber), NetworkManager-wifi, network-manager-applet, Xwayland, qt5/qt6-qtwayland, polkit, gnome-keyring (+ pam), xdg-user-dirs, xdg-utils, libnotify, brightnessctl, playerctl, tuned-ppd, mesa-dri-drivers.
- `nix`: Fedora RPMs `nix nix-daemon` plus `arctic-selinux` (§6.6).
- `flatpak`: flatpak with the Flathub remote.
- `codecs`: RPM Fusion free/nonfree, ffmpeg swap, openh264.

**Catalog rules:**
- Nix only for CLI/TUI modules (`gpu=false`).
- Every Flatpak install names its remote explicitly.
- CI checks every Flatpak ID, dnf package and nix attribute on each build and regenerates `download_mb`.
- Removed as invalid ✅: `com.collabora.Office` (wrong ID), `nixpkgs#zen-browser` (does not exist), Nix fallbacks for GUI apps and the WM.

The catalog ships inside the ISO, versioned with it. There is no online catalog refresh in v1: the ISO is rebuilt regularly instead, which keeps the picker and the installer in sync.

## 5. Installer wizard (engine-owned flow)

One decision per screen. The recommended choice is pre-selected, Back/Next are always available, and
nothing touches the disk before **Summary → Install**.

| # | Step | Asks | Default / behavior | Validation |
|---|---|---|---|---|
| 1 | Welcome & language | UI language | From firmware/locale guess | — |
| 2 | Keyboard | Layout + variant, test field | Suggested from language | Also applied live to the mango session (`mmsg dispatch reload_config` 🔍 P3) so passphrases are typed on the right layout |
| 3 | Network | Wi-Fi list / wired status | Auto-skip if already online | Required. Copy explains that apps are downloaded (~2 GB for the default set). Done inside `arcticd` via NetworkManager D-Bus, with no polkit prompt. |
| 4 | Timezone | Region/city | GeoIP guess if online | — |
| 5 | Disk | Which disk; **Erase disk & install (encrypted)** or **Install alongside** (free space) | Erase + encrypt on the largest non-USB disk | Hides the live USB. Warns about existing OSes. Size ≥ 40 GB. |
| 6 | Encryption | Passphrase ×2, strength meter | On (a toggle can turn it off, with a warning) | pwquality score; typed on the chosen layout |
| 7 | Account | Full name, username (auto), password ×2, computer name (auto), "Log in automatically" | Autologin off | POSIX username rules, pwquality. Password hashed in Go (yescrypt), never written to disk in plaintext. |
| 8 | Apps (Ninite picker) | Categories from §4.2 with defaults ticked | Defaults | Conflicts resolved; shows total download size (shared runtimes counted once) |
| 9 | Summary | Everything above in plain language | — | Explicit "Erase disk X and install" confirmation |
| 10 | Installing | Progress bar, current action, per-app status | — | Optional-app failures don't stop the install |
| 11 | Error (only if needed) | What failed, Retry / Skip (optional apps) / Save log | — | — |
| 12 | Done | "Remove the USB and restart" · apps that finish after reboot are listed | — | — |

**API (v1, JSON over `/run/arcticd.sock`, SocketGroup=wheel, mode 0660):**

| Call | Purpose |
|---|---|
| `GetWizard` | Step list, current step, per-step state/defaults/options |
| `SetStep(id, data)` → `{ok, errors[]}` | Validation errors come back as message keys, so the frontend can translate them |
| `Next`, `Back` | Wizard navigation |
| `GetCatalog` | Slots and modules with names, summaries, icons, sizes, defaults, conflicts |
| `ListDisks` | Disks and layout preview |
| `ScanWifi` / `ConnectWifi` | Network step |
| `SetSecrets` | Passphrase and password, kept in memory only, never logged |
| `Start`, `Abort` | Begin or cancel the install |
| `Events` (stream) | `{phase, module?, label, percent, bytes?, status: queued/downloading/installed/failed/deferred}` |
| `Reboot` | Finish |

Unattended mode walks the same steps from `profile.toml` (CI only; secrets come from environment variables).

## 6. Install pipeline (what `arcticd` executes)

Every step is idempotent, checkpointed, logged and has a dry-run mode.

### 6.1 Preflight
- Firmware mode (UEFI or BIOS), RAM, disk size, AC power on laptops.
- Connectivity to the Fedora mirrors, Flathub and cache.nixos.org.
- Clock sync, GPU detection.

### 6.2 Disk (default layout)

| Part | Size | Content | Why |
|---|---|---|---|
| p1 | 1 MiB | BIOS boot (EF02) | Required for BIOS boot from GPT ✅ (always created) |
| p2 | 1 GiB | ESP, vfat, `/boot/efi` | User decision |
| p3 | 2 GiB | ext4 `/boot`, unencrypted | GRUB can't unlock LUKS2 with argon2id ✅. 2 GiB is Fedora's default since F43 ✅. |
| p4 | rest | LUKS2 (argon2id) → btrfs `@`, `@home`, `@var_log`, `@nix`, `compress=zstd:1` | User decision |

- `crypttab`: `luks-<UUID> UUID=<UUID> none discard`.
- Kernel cmdline: `root=UUID=<btrfs> ro rootflags=subvol=@ rd.luks.uuid=luks-<UUID> rhgb quiet`.
- "Install alongside" reuses the existing ESP and creates p3/p4 in free space.

### 6.3 Copy the base system
1. Copy the live root filesystem's read-only base (the squashfs root) to `/mnt` with `-aAXH` semantics, skipping `/proc /sys /dev /run /tmp`. 🔍 P3: confirm where the base is mounted on a F44 live boot (`/run/rootfsbase`) and measure the copy time.
2. Remove live-only packages offline in the chroot: `livesys-scripts`, `arctic-live`, `arctic-installer`, `dracut-live`, anaconda-free leftovers. Delete the liveuser traces. livesys creates liveuser at boot, so the squashfs should be clean. 🔍 P3: verify.
3. Mount `/proc /sys /dev /run` into `/mnt` for the next steps.

### 6.4 System configuration
- `systemd-machine-id-setup --root=/mnt`.
- `systemd-firstboot --root=/mnt` for locale, keymap, timezone and hostname.
- `fstab` and `crypttab`.
- User: `useradd -R /mnt -m -G wheel -s /bin/zsh -p <hash>`. Pre-hashing avoids F45's PAM change to `chpasswd` ✅. Root is locked.
- Keyboard layout written to three places: vconsole, `/etc/arctic/mango/keyboard.conf` (`xkb_rules_*`) and `/etc/arctic/sddm-keyboard.conf` (for the greeter).
- `/etc/arctic/mango/apps.conf` generated from the chosen slots (terminal/launcher binds, autostarts).
- `systemctl --root=/mnt enable sddm.service`, then `set-default graphical.target`. Also `--global enable` for the session units.
- Autologin only if chosen: `/etc/sddm.conf.d/50-arctic-autologin.conf`.
- Copy the Wi-Fi profiles from the live session into the target.

### 6.5 Bootloader
1. Write `/etc/default/grub`, then `/etc/kernel/cmdline`. Without the cmdline file, Fedora copies the live ISO's `/proc/cmdline` ✅.
2. Run `kernel-install add <kver>` (or `depmod` + `dracut -f`) in the chroot, which builds a host-only initramfs with LUKS/btrfs and a BLS entry.
3. Run `grub2-mkconfig -o /boot/grub2/grub.cfg`.
4. UEFI: `efibootmgr -c -L "Arctic Linux" -l '\EFI\fedora\shimx64.efi'`. The signed shim/GRUB must stay under `/EFI/fedora` ✅, so Secure Boot works. BIOS: `grub2-install --target=i386-pc <disk>`.

### 6.6 Apps (diff against the live image)
1. **Remove** unticked default modules offline: `dnf remove` in the chroot, `flatpak uninstall` with the `FLATPAK_*` variables.
2. **dnf** installs: one batched transaction in the chroot. Includes the codecs module (RPM Fusion from repo files and keys baked into the ISO via `distribution-gpg-keys`; never `--nogpgcheck`), `ffmpeg` swap, `vlc-plugins-freeworld`, and NVIDIA akmods when detected.
3. **Flatpak** from the live host, no chroot ✅:
   ```
   export FLATPAK_SYSTEM_DIR=/mnt/var/lib/flatpak FLATPAK_CONFIG_DIR=/mnt/etc/flatpak \
          FLATPAK_OS_CONFIG_DIR=/mnt/usr/share/flatpak FLATPAK_DOWNLOAD_TMPDIR=/mnt/var/tmp LC_ALL=C.UTF-8
   flatpak remote-add --system --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
   flatpak install --system -y flathub <id>      # one call per module; parse "Installing i/n … NN%"
   touch /mnt/var/lib/flatpak/.fedora-initialized  # stop Fedora's OCI remote being added at first boot
   ```
4. **Nix**: installed as Fedora RPMs (`nix`, `nix-daemon`), already in the live image ✅. `arctic-selinux` adds the `/nix` file contexts, reusing the NixOS installer's `nix.fc` (LGPL-2.1, credited). The key rule is `/nix/var/nix/daemon-socket(/.*)? → var_run_t`, which fixes Fedora bug 2525943.
   - Enable `nix-daemon.service`, and switch to the socket only once CI shows no AVC denials.
   - `auto-optimise-store = false` (Fedora bug 2416675).
   - Nix apps go system-wide from the live host:
     `nix --store /mnt profile add --profile /mnt/nix/var/nix/profiles/default <pinned installables> --log-format internal-json`.
   - Fedora's `/etc/profile.d/nix-daemon.sh` already puts that profile on everyone's PATH ✅.
   - The nixpkgs pin lives in the catalog.
5. **Failure policy:** each optional module gets one retry, then is deferred to `/var/lib/arctic/pending.json`. `arctic-firstboot.service` (oneshot, after network-online) retries it without blocking login and shows a notification. Steps 6.2–6.5 are fatal, and the error screen offers retry or save log.

### 6.7 Hooks and finalize
1. Run the dotfiles hook. `/etc/skel/.config/mango/config.conf` is a thin file of `source=` lines: `/usr/share/arctic/mango/base.conf`, `/etc/arctic/mango/{keyboard,apps}.conf`, then `source-optional=~/.config/mango/user.conf` ← DOTFILES. Never edit `/etc/mango/config.conf`: the package overwrites it on every update ✅. The animated fetch goes in `.zshrc` (interactive shells only), never `.zprofile` ✅.
2. Write `/etc/xdg/mimeapps.list` from each module's `[defaults]`.
3. Copy the install log to the target.
4. **SELinux relabel before unmount** ✅: `setfiles -F -r /mnt -e /mnt/proc -e /mnt/sys -e /mnt/dev -e /mnt/run -e /mnt/boot/efi /mnt/etc/selinux/targeted/contexts/files/file_contexts /mnt`. If it fails, fall back to `echo -F > /mnt/.autorelabel`.
5. Unmount, close LUKS, go to the Done screen.

**Time budget (goal: under 10 minutes on a 100 Mbit/s link, SSD):**

| Stage | Estimate |
|---|---|
| Copy | ~2 min |
| Configure + bootloader + initramfs | ~2 min |
| Default online apps (Zed + Collabora, ~1.9 GB including runtimes) | ~3–5 min |
| Relabel | ~1 min |

## 7. Login manager and session

- **Greeter:** `sddm` plus our `sddm-wayland-mango` package. It Provides `sddm-greeter-displayserver` and ships `/usr/lib/sddm/sddm.conf.d/10-arctic.conf`:
  ```
  [General]  DisplayServer=wayland  GreeterEnvironment=QT_WAYLAND_SHELL_INTEGRATION=layer-shell  InputMethod=
  [Wayland]  CompositorCommand=/usr/libexec/arctic/sddm-compositor-mango
  [Theme]    Current=arctic
  ```
  - The wrapper unsets `DBUS_SESSION_BUS_ADDRESS` and runs `mango -c /usr/share/arctic/sddm/greeter.conf`. That config has no binds and no exec lines, plus `source-optional=/etc/arctic/sddm-keyboard.conf`.
  - Mango as the greeter compositor is untested 🔍 P1. The fallback is `sddm-wayland-generic` (weston), which is in Fedora ✅.
  - Exclude `sddm-x11`, `sddm-wayland-plasma` and `sddm-themes`.
- **Theme:** `arctic-sddm-theme` installs to `/usr/share/sddm/themes/arctic/`. It needs `metadata.desktop` with `QtVersion=6` and `Theme-Id=arctic`, because Fedora's greeter is Qt6-only ✅. It must have a user field, a password field (empty passwords allowed for liveuser), a session picker, a keyboard indicator, power buttons and error text. The placeholder is minimal, and the design later replaces only the QML and assets (**DESIGN HOOK**). Preview it with `sddm-greeter-qt6 --test-mode --theme …`.
- **Session:** the stock `mango.desktop` starts `mango-session.target`, which binds `graphical-session.target`. `arctic-desktop-config` ships user units `WantedBy=graphical-session.target` for the polkit agent, swayidle and nm-applet. Each has `ConditionUser=!@system`, so they never run in the greeter. waybar and mako are started by D-Bus or units. Mango doesn't process XDG autostart ✅.

## 8. Live ISO

- **Build:** kiwi-ng, derived from Fedora's own `fedora-kiwi-descriptions` ✅ (F44 branch). The ISO is hybrid, UEFI and BIOS, and keeps Fedora's signed shim, so Secure Boot works.
- **Contents:**
  - Everything in the default install except the online-only apps. That covers desktop-base, kitty, zsh, yazi, Thunar, VLC, arctic-fetch, Nix and **Zen (Flatpak preinstalled)**, so Try mode has a working browser.
  - Plus `livesys-scripts`, `arctic-live`, `arctic-installer`, the RPM Fusion repo files and arctic-release's Arctic repository files, `distribution-gpg-keys`, `policycoreutils`, and the same `selinux-policy-targeted` as the target. SELinux stays enabled in the live system.
  - **Size target: ≤ 2 GiB**, because GitHub Releases limits each asset to 2 GiB. If it's over, see §12.
- **Boot menu:** the entries in §2. Every entry has `rd.live.image` plus `arctic.mode=try|install`.
  - 🔍 P2: how kiwi lets us customize the GRUB (EFI and BIOS) menu entries: a kiwi template/option, or post-processing grub.cfg.
- **Live session:**
  - `/etc/sysconfig/livesys` sets `livesys_session="arctic"`. `/usr/libexec/livesys/sessions.d/livesys-arctic` writes `/etc/sddm.conf.d/90-arctic-live.conf` (`[Autologin] User=liveuser Session=mango.desktop`), creates the mango config for liveuser, and disables locking. This follows the pattern of Fedora's Sway and miracle-wm live spins ✅.
  - The mango `exec-once=/usr/libexec/arctic/live-session` reads `/proc/cmdline`. In install mode it launches the installer frontend full-screen (`windowrule=isfullscreen:1,appid:org.arcticlinux.Installer`) with no bar. In try mode it starts the full desktop.
  - Mango has no desktop icons ✅, so the "Install Arctic Linux" button goes in three places: a waybar button, a launcher entry (`org.arcticlinux.Installer.desktop`) and a wallpaper hint.
- **Frontend placeholder** until the real UI arrives: `kitty --class org.arcticlinux.Installer -e arctic-install --interactive-stub`. This is a plain-text walkthrough of the same API, not a design.

## 9. Phases and milestones

| Phase | Weeks | Work | Done when |
|---|---|---|---|
| **P0 Foundations** | 1 | Go module, lint, CI. `catalog`, `profile` and `wizard` packages. `catalog.json` export. Planner with dry-run. | `arctic-install --profile profiles/defaults.toml --dry-run` prints the full plan. Every wizard step validates in unit tests. |
| **P1 Packaging & repository** | 2–3 | Arctic package repository (signed, GitHub Pages). mangowm fork spec. arctic-release/logos/selinux. sddm-wayland-mango. Placeholder theme. arctic-desktop-config, arctic-fetch, arctic-live. | A plain Fedora 44 VM with these RPMs boots SDDM on the mango greeter, logs into Mango, and has portals, polkit agent, notifications and bar. No AVC denials. |
| **P2 Live ISO** | 4 | kiwi description, boot menu, livesys-arctic, Try and Install modes, Zen preinstalled. | The ISO boots UEFI and BIOS in QEMU. Try mode shows the desktop and the install button. Install mode shows the placeholder installer full-screen. Size ≤ 2 GiB. |
| **P3 Engine core** | 5–6 | Spike on the copy approach first (else Appendix A). Then disk, copy, system, bootloader, relabel. | From the ISO, unattended install of the default layout on UEFI and BIOS, with and without LUKS. Reboots to SDDM, logs in, zsh is the default shell. Under 5 minutes before apps. |
| **P4 Apps stage** | 7 | dnf, Flatpak and Nix backends. Diff and remove. Progress parsing. Deferred retry service. Codecs. NVIDIA. | The default profile and one alternative profile (Firefox + foot + mpv + LibreOffice) install exactly the chosen apps. `nix run nixpkgs#hello` works as a user. No `fedora` flatpak remote. `/nix/store/*/bin` is labeled `bin_t`. |
| **P5 API & wizard complete** | 8 | API v1 frozen with docs. Event stream. NM Wi-Fi. Disk "alongside" mode. i18n keys. Stub client. | The stub client completes every wizard path through the API alone, which proves a frontend can. `hooks/frontend/README.md` is written. |
| **P6 Hardening** | 9 | CI VM matrix on every PR. Resume after network drop. Error paths. Real hardware (Intel, AMD, NVIDIA laptop). | The whole matrix is green. The failure-injection tests pass (see §11). |
| **P7 Release v0.1** | 10 | Rebase on F45 if it's GA and verified. Signed ISO, checksums, release notes. | A tagged release with the ISO downloadable. |

**Waiting on you:** the installer frontend (all wizard screens including the Ninite picker), the SDDM theme
visuals, the dotfiles (mango/waybar/kitty/zsh configs) and the fetch animation. These plug into P5, P7 and
§6.7 without changing the engine.

## 10. Fedora release tracking

- `releasever` is pinned per ISO build: 44 now.
- A new Fedora stable becomes the base only after it's GA **and** CI passes with it:
  1. Build Arctic's packages for it (`dist_version`, the build image) and publish them: the
     repository keeps one tree per Fedora release (`repo/<channel>/fedora-$releasever/`, and
     arctic-release's `baseurl` uses `$releasever`), so the new builds go into `fedora-45` next to
     `fedora-44`. Publish them before F44 systems upgrade; `fedora-44` keeps its last builds.
     BUILD-SPEC §9 ("A new Fedora release") has the details.
  2. Re-verify the catalog.
  3. Rebuild the ISO.
- F45-specific changes the engine already accounts for ✅:
  - Repo files move to `/usr/share/dnf5/repos.d`, and keys to `/usr/share/pki/rpm-gpg`. Never hardcode `/etc/yum.repos.d`.
  - RPM signatures become mandatory, so all Arctic RPMs are signed.
  - `chpasswd` goes through PAM, so passwords are pre-hashed.
  - The console moves to kmscon.
- **Installed systems** upgrade the Fedora way with `dnf system-upgrade`. `arctic-release` is bumped per release. A friendlier upgrade flow comes later.

## 11. Testing

| Level | What |
|---|---|
| Unit | Catalog validation, slot resolution, dependency ordering, wizard validation, progress parsers (Flatpak lines, Nix internal-json), planner golden files |
| Executor | Fake Runner checks the exact command sequence per profile, including the remove/add diff |
| Catalog CI | Every Flatpak ID and verified flag checked against the Flathub API. Every dnf package resolves on the target release. Every nix attribute evaluates. Sizes regenerated. |
| VM (QEMU/OVMF, KVM) | UEFI and BIOS × LUKS on/off × default and alternative profiles. Boot → install → reboot → checks over the serial console: SDDM greeter up, `graphical-session.target` active, portals and polkit working, apps present, no AVC denials, Nix and Flatpak working, greeter keyboard matches the choice. |
| Failure injection | Flathub unreachable (app deferred, install succeeds), mirror down, disk too small, wrong passphrase confirmation, abort before and after the disk step |
| Live | Try mode desktop and install button. Install mode full-screen installer. Media check entry. Safe-graphics entry. |
| Hardware (per release) | Intel laptop, AMD desktop, NVIDIA laptop, one BIOS-only machine |

## 12. Risks

| Risk | Mitigation |
|---|---|
| mangowm isn't in Fedora, and Terra's spec is lightly maintained | Own fork of the spec, built on Fedora's wlroots 0.20 and scenefx 0.5 and published in the Arctic repository ✅, pinned version, Terra (`includepkgs=mangowm`) as the emergency fallback |
| Mango as the SDDM greeter compositor is untested | The weston greeter (`sddm-wayland-generic`) as a catalog fallback, and a CI check |
| SDDM lost Fedora KDE to Plasma Login Manager in F44 ✅, so upstream may slow down | The login manager is a slot. greetd + tuigreet is the emergency alternative. |
| Nix with SELinux enforcing (Fedora bugs 2525943, 2416675) | arctic-selinux file contexts, `auto-optimise-store=false`, enforcing CI |
| The live-image copy approach has an unknown detail | P3 spike first. The dnf installroot fallback is already researched (Appendix A). |
| The ISO is over 2 GiB (GitHub asset limit) | Move Zen to online-only, or host the ISO elsewhere (open question) |
| Zed Flatpak is community-made and adds ~940 MB | Accepted for v1 (Flatpak is OK). Switch to Terra or an own RPM in the Arctic repository later if needed. |
| Flathub IDs change (as the Collabora ID did) | Catalog CI checks IDs on every build |
| Slow network makes "minutes" slip | Defaults ship in the ISO. Only Zed and Collabora download. Optional apps can be deferred to first boot. |
| Fedora 45 changes | Handled in §10, re-verified at F45 GA |

## 13. Open questions

1. **Autologin:** should "Log in automatically" default to on when disk encryption is on? That's the Omarchy style: one password at boot, but the keyring isn't unlocked automatically.
2. **Snapshots:** add snapper with btrfs snapshots as an optional module, and should it be on by default?
3. **ISO hosting** if it grows past 2 GiB: GitHub Releases, or a mirror or CDN?
4. **Zed source:** keep the unverified Flathub build, or package the official release in the Arctic repository?

---

## Appendix A — Fallback: dnf5 installroot bootstrap (researched ✅)

1. Mount the target at `/mnt`, including `/boot` and `/boot/efi`. Mount `proc`, rbind `sys` and `dev`, and put a tmpfs on `run`. Then run `systemd-machine-id-setup --root=/mnt`.
2. Write `/etc/default/grub`, then `/etc/kernel/cmdline`.
3. Run the base transaction:
   ```
   dnf5 --installroot=/mnt --use-host-config --releasever=44 \
     --setopt=install_weak_deps=False --setopt=max_parallel_downloads=10 -y \
     --exclude='fedora-release*,fedora-logos*' install @core <firmware> kernel dracut btrfs-progs cryptsetup \
     dosfstools grub2-tools grubby arctic-release arctic-logos glibc-langpack-XX NetworkManager-wifi \
     (shim-x64 grub2-efi-x64 efibootmgr | grub2-pc grub2-pc-modules)
   ```
   On-ISO RPMs can be served with `--repofrompath=arctic-media,/run/initramfs/live/arctic-repo`.
4. Continue with §6.4 → §6.7.
