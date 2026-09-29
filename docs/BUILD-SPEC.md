# Arctic Linux v0.2 — build spec (contracts between components)

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
cmd/arctic-webapp/      web-app manager (Go, CGO_ENABLED=0; §11)
cmd/arctic-webapp-host/ web-app window (Go + cgo, WebKitGTK 6.0; §11)
internal/webapp/…       web-app core, discovery, icons, policies (pure Go); internal/webkit/ the cgo shim
internal/…              engine packages (Go)
modules/<slot>/<id>/module.toml   app catalog (see §5)
profiles/defaults.toml, profiles/ci/*.toml
shell/                  Quickshell desktop shell (bar, launcher, wallpapers, Get apps and Remove apps, OSD, lock, live welcome)
installer-ui/           Quickshell installer frontend (the 12-step wizard)
settings/               Arctic Settings, the settings app (Quickshell; §3.2)
branding/sddm/arctic/   SDDM Qt6 QML login theme
branding/grub/arctic/   GRUB theme (live ISO boot menu + installed system)
branding/plymouth/arctic/  Plymouth script theme
branding/logos/         generated PNG/SVG logos for system-logos
dotfiles/               user home tree → /etc/skel
design/                 design system sources (read-only input)
design/themegen/        theme engine (arctic-themegen): palettes → theme folders, templates, wallpaper colours (§10)
packaging/arctic-linux.spec   ONE spec, many subpackages (§2), Source0 = repo tarball
packaging/mangowm.spec        Mango built from upstream
live/                   live-session files (livesys session, arctic-live-session, sddm live conf)
iso/kiwi/               kiwi-ng description for the live ISO
tools/build-rpms.sh     builds all RPMs in a Fedora 44 container → out/repo (createrepo_c), out/BUILD-INFO;
                        every build gets its own Release (§9)
tools/build-iso.sh      builds the ISO with kiwi-ng in a privileged Fedora 44 container → out/iso
tools/publish-repo.sh   adds a build to one channel of the package repository site: signs, prunes,
                        createrepo_c, repomd.xml.asc, index + manifest (§9); --no-sign for local tests
tools/test-repo.sh      dnf5 checks in Fedora 44 containers: arctic-release, offline behaviour,
                        repoquery against a published site
tools/lib/arcticrepo.py prune / manifest / fetch (the published site) / index for the repository
tools/tests/            unit tests for tools/lib (python3 -m unittest discover -s tools/tests)
tools/test-iso.sh       boots the ISO in QEMU (no KVM needed), takes screenshots
tools/test-install.sh   installs from the ISO to a VM disk (arctic-install unattended, profiles/ci/offline.toml),
                        then boots it: LUKS prompt, SDDM login, desktop, logs over the serial port;
                        --test-hardware nvidia-laptop --online-via-proxy with profiles/ci/nvidia.toml
                        builds the NVIDIA akmod online (arctic-install unattended --test-hardware
                        NAME --test-online: VM-test aids that fake the PCI devices / the online check)
tools/lib/              container.sh (docker/podman + proxy), vmtest.py (QEMU/QMP helpers for the tests)
.github/workflows/ci.yml   go test, shellcheck, python tests, node tests, qmllint
.github/workflows/iso.yml  build RPMs + ISO, upload artifact, publish release (tag or manual)
.github/workflows/repo.yml build, sign and publish the RPMs to the package repository on GitHub Pages (§9)
```

## 2. RPM packages (all from `packaging/arctic-linux.spec` unless noted)

Version 0.3.0, `Release: 1%{?arctic_snapshot}%{?dist}` (every build its own Release, §9).
`Source0: arctic-linux-%{version}.tar.gz` made by `git archive --prefix=arctic-linux-0.3.0/` of the
working tree (tools/build-rpms.sh; uncommitted and untracked files are included through a
throwaway index, and so is the repository key, §9). noarch unless it contains Go binaries.
The one other source is `Source1`, the Nerd Fonts "Symbols Only" release for
`arctic-fonts-symbols` (Fedora has no symbols-only Nerd Font): pinned in the spec by
`nerd_version` and `nerd_sha256`, downloaded by tools/build-rpms.sh next to the Mango tarball and
checked against the SHA-256 there and again in `%prep`.

| Subpackage | Installs | Notes |
|---|---|---|
| `arctic-release` | `/usr/lib/os-release` (NAME="Arctic Linux", ID=arctic, ID_LIKE=fedora, VERSION_ID=0.2, PRETTY_NAME="Arctic Linux 0.2 (Fedora 44 base)", LOGO=arctic-logo-icon, HOME_URL; LOGO names the icon arctic-logos installs in hicolor and `/usr/share/pixmaps`, checked in `%check`; fastfetch has no built-in Arctic logo and would draw Fedora's by ID_LIKE, hence the fox in the fastfetch layouts, §3.1), `/etc/os-release` symlink, `/usr/lib/rpm/macros.d/macros.dist` (%fedora 44, %dist .fc44), `/etc/dnf/plugins/copr.d/arctic.conf` ([main] distribution=fedora), `/usr/share/dnf5/repos.d/arctic.repo` + `arctic-testing.repo` (the Arctic package repository, §9: stable on, testing off) and its key `/etc/pki/rpm-gpg/RPM-GPG-KEY-arctic` (without a key at build time both repo files ship `enabled=0`), presets `/usr/lib/systemd/system-preset/80-arctic.preset` (also: no sshd, as Fedora's desktop editions), `/usr/lib/systemd/user-preset/80-arctic.preset` | Provides `system-release`, `system-release(44)`, `system-release(releasever) = 44`, `base-module(platform:f44)`; Requires `fedora-repos(44)`; Conflicts `fedora-release-common`, `generic-release`. Model on Fedora's generic-release.spec. MUST be proven installable in place of fedora-release in a F44 container (`dnf install --allowerasing arctic-release`). |
| `arctic-logos` | `/usr/share/pixmaps/{fedora,system}-logo*.png` equivalents, `/usr/share/pixmaps/arctic-logo-icon.{png,svg}` (os-release `LOGO`), `/usr/share/icons/hicolor/*/apps/arctic-logo-icon.png`, `/usr/share/arctic/logos/*.svg` | Provides `system-logos`, `system-logos(%{version})`; Conflicts `fedora-logos`, `generic-logos`. Must satisfy what sddm/plymouth require from system-logos. |
| `arctic-backgrounds` | `/usr/share/backgrounds/arctic/*.svg` + rendered `*.png` (3840×2160) | The 6 design wallpapers. Provides `desktop-backgrounds-compat` if needed by sddm. |
| `arctic-fonts` | `/usr/share/fonts/arctic/Figtree-*.woff2` (+ `.ttf` if converted) | JetBrains Mono comes from `jetbrains-mono-fonts-all`. |
| `arctic-fonts-symbols` | `/usr/share/fonts/arctic-symbols/SymbolsNerdFont{,Mono}-Regular.ttf` ← Source1, `/usr/share/fontconfig/conf.avail/66-arctic-nerd-symbols.conf` ← `packaging/fonts/` (+ its link in `/etc/fonts/conf.d/`) | noarch. The symbols appended weakly after `monospace`, JetBrains Mono and Adwaita Mono, so the terminal's icons (yazi, eza, prompts) work with any code font. License from the release's LICENSE and readme: MIT AND CC-BY-4.0 AND Apache-2.0 AND OFL-1.1-RFN AND OFL-1.1 AND Unlicense. Recommended by `arctic-shell` (with `arctic-themes-extra`), listed in `config.kiwi`. |
| `arctic-selinux` | `/usr/share/selinux/packages/arctic-nix.pp` | Built from `packaging/selinux/arctic-nix.te/.fc` (`/nix` contexts, see PLAN §6.6). %post: semodule install; `%selinux_modules_install`. |
| `arctic-desktop-config` | `/etc/skel/` ← `dotfiles/` (minus install.sh/README and the files below), `/usr/bin/arctic-*` ← `dotfiles/.local/bin/*`, `/usr/share/arctic/mango/*.conf` ← `dotfiles/.config/mango/arctic/` (skel has links to them), `/usr/share/arctic/keys.txt`, `/usr/share/arctic/themes/{winter,polar-night}/` (rendered by the engine in %build; skel's `~/.config/arctic/current` links there), `/usr/share/arctic/themegen/` + `/usr/bin/arctic-themegen` (theme engine, §10), `/usr/share/arctic/theme-hooks.d/` ← `packaging/theme-hooks.d/`, `/etc/arctic/default-apps` (defaults), app theming (§3.1): `/etc/dconf/db/distro.d/10-arctic` (+ `%ghost` compiled `/etc/dconf/db/distro`), `/var/lib/flatpak/overrides/global`, `/usr/lib/environment.d/50-arctic-qt.conf`; fastfetch (§3.1): `/usr/share/arctic/fastfetch/{greeting.jsonc,logo.txt}` ← `dotfiles/.local/share/arctic/fastfetch/`, `/etc/xdg/fastfetch/config.jsonc` → the Polar night theme's `fastfetch/config.jsonc` (accounts without the skel link: root, older accounts); `neofetch`: `/usr/libexec/arctic/neofetch` ← `dotfiles/.local/bin/neofetch` (fastfetch with the theme's `fastfetch/neofetch.jsonc`; a real neofetch found on `PATH` runs instead) and `%ghost /usr/bin/neofetch` → it, created in `%posttrans` only when that name is free: a `%ghost` never conflicts with another package's file, so a neofetch package (none in Fedora 44) installs over it, and `%triggerpostun -- neofetch` links it again when that package goes (rpm leaves the shared path's file behind) | Requires the desktop runtime (§3), python3-pillow (wallpaper colours) and adw-gtk3-theme, qt5ct, qt6ct, dconf (§3.1), fastfetch. Provides `neofetch = %{version}-%{release}` (satisfies what depends on neofetch; `dnf install neofetch` says it is there, and would install a real neofetch package by name). No `Conflicts: neofetch`: it would make installing a real neofetch remove arctic-desktop-config (and arctic-desktop). Helper scripts must look in XDG dirs: `~/.local/share/arctic/…` then `/usr/share/arctic/…`, and wallpapers in `/usr/share/backgrounds/arctic`. |
| `arctic-shell` | `/usr/share/arctic/shell/` ← `shell/`, `/usr/bin/arctic-shell` (`exec quickshell -p /usr/share/arctic/shell "$@"`) | Requires quickshell, python3, python3-pillow, python3-pyte, polkit (pkexec, for Get apps), python3-dbus, python3-gobject-base (the Bluetooth pairing agent), glib2, pipewire-utils; Recommends appstream-data (Fedora app names and icons in Get apps), ddcutil (external monitors' brightness), qrencode (Wi-Fi share), NetworkManager-openvpn. %check runs `shell/tests/test_apps.py`. |
| `arctic-settings` | `/usr/share/arctic/settings/` ← `settings/` (minus tests/, dev/), `/usr/bin/arctic-settings` ← `dotfiles/.local/bin/arctic-settings`, `/usr/share/applications/org.arcticlinux.Settings.desktop`, `/usr/share/icons/hicolor/scalable/apps/org.arcticlinux.Settings.svg` ← `packaging/settings/` | noarch. Requires quickshell, qt6-qtdeclarative, qt6-qtsvg, qt6-qtwayland, python3, wlr-randr, arctic-desktop-config, arctic-shell, arctic-fonts; Recommends nm-connection-editor, blueman, pavucontrol, xdg-utils. %check runs `settings/tests`. Required by `arctic-desktop`. |
| `arctic-installer` | `/usr/bin/arcticd`, `/usr/bin/arctic-install`, `/usr/share/arctic/catalog/` ← `modules/`, `/usr/share/arctic/profiles/`, `/usr/share/arctic/installer-ui/` ← `installer-ui/`, `/usr/bin/arctic-installer` (`exec quickshell -p /usr/share/arctic/installer-ui "$@"`), `/usr/lib/systemd/system/arcticd.{socket,service}`, `/usr/share/applications/org.arcticlinux.Installer.desktop` | arch x86_64 (Go). BuildRequires golang. Go builds offline: vendor modules or stdlib only (prefer stdlib only; `github.com/BurntSushi/toml` allowed only if vendored). |
| `arctic-webapps` | `/usr/bin/arctic-webapp`, `/usr/libexec/arctic/arctic-webapp-host` | arch x86_64. The manager is pure Go; the host is cgo against WebKitGTK 6.0 and GTK 4 (BuildRequires gcc, `pkgconfig(webkitgtk-6.0)`, `pkgconfig(gtk4)`, `pkgconfig(libsoup-3.0)`). Requires `webkitgtk6.0 >=` the version built against, librsvg2-tools, hicolor-icon-theme, publicsuffix-list. %check: the host's NEEDED, no NEEDED in the manager, `--version` of both, `render-sample` + desktop-file-validate. Required by `arctic-desktop`; Recommended by `arctic-shell` (§11). |
| `sddm-wayland-mango` | `/usr/lib/sddm/sddm.conf.d/10-arctic.conf`, `/usr/libexec/arctic/sddm-compositor-mango`, `/usr/share/arctic/sddm/greeter.conf` | Provides+Conflicts `sddm-greeter-displayserver`. Requires sddm, mangowm, layer-shell-qt. Config per PLAN §7. If the mango greeter can't be made to work in the VM test, ship `10-arctic.conf` for `sddm-wayland-generic` (weston) instead and note it. |
| `arctic-sddm-theme` | `/usr/share/sddm/themes/arctic/` ← `branding/sddm/arctic/` | Requires sddm, qt6-qtdeclarative, qt6-qt5compat only if used. |
| `arctic-plymouth-theme` | `/usr/share/plymouth/themes/arctic/` ← `branding/plymouth/arctic/` | Requires plymouth-plugin-script. %post: `plymouth-set-default-theme arctic` (no initrd rebuild in %post). |
| `arctic-grub-theme` | `/boot/grub2/themes/arctic/` ← `branding/grub/arctic/` (+ `/usr/share/arctic/grub-theme/` copy) | Installed system sets `GRUB_THEME`; the ISO uses the same files. |
| `arctic-live` | `/usr/libexec/livesys/sessions.d/livesys-arctic`, `/usr/libexec/arctic/live-session`, `/usr/share/arctic/mango/live.conf` | Only in the live image. |
| `mangowm` (packaging/mangowm.spec) | upstream mango 0.17.3 | BuildRequires meson, gcc, `pkgconfig(wlroots-0.20)`, `pkgconfig(scenefx-0.5)`, wayland-devel, wayland-protocols-devel, libinput-devel, libxkbcommon-devel, pcre2-devel, pixman-devel, cjson-devel, pango-devel, libdrm-devel, xcb deps (`xorg-x11-server-Xwayland-devel`/libxcb-devel, xcb-util-wm-devel). `Source0: https://github.com/mangowm/mango/archive/refs/tags/0.17.3.tar.gz`. `/etc/mango/config.conf` marked `%config(noreplace)`. |

Metapackage: `arctic-desktop` (subpackage, no files) Requires everything a desktop needs:
mangowm, sddm, sddm-wayland-mango, arctic-sddm-theme, arctic-shell, arctic-settings, arctic-desktop-config,
arctic-backgrounds, arctic-fonts, arctic-logos, arctic-release, arctic-plymouth-theme,
arctic-grub-theme, kitty, kitty-shell-integration, zsh, fastfetch, swaybg, swayidle,
swaylock, grim, slurp, wl-clipboard, cliphist, brightnessctl, playerctl, wireplumber,
pipewire-pulseaudio, NetworkManager-wifi, bluez,
xdg-desktop-portal-wlr, xdg-desktop-portal-gtk, xdg-user-dirs, xdg-utils, libnotify,
librsvg2-tools, jetbrains-mono-fonts-all, google-noto-sans-fonts, polkit, gnome-keyring,
gnome-keyring-pam, Thunar, qt6-qtwayland, qt5-qtwayland, xorg-x11-server-Xwayland,
fuzzel (fallback launcher), flatpak, nix, nix-daemon, arctic-selinux, python3-pillow,
adw-gtk3-theme, qt5ct, qt6ct (§3.1); Recommends btop, mako (the waybar session's notification
daemon; the shell is its own notification server), pavucontrol, network-manager-applet and
blueman (the shell draws its own sound, network and Bluetooth menus and pairs with its own
agent; the waybar session and the menus' "More…" links still use them). arctic-shell Requires glib2 (gdbus).

## 3. Desktop session (installed and live)

SDDM (theme `arctic`, greeter on mango or weston) → `mango.desktop` → `~/.config/mango/config.conf`
(from /etc/skel). Autostart (`dotfiles/.config/mango/arctic/autostart.conf`):
`arctic-theme apply`, `arctic-shell` (Quickshell: bar, launcher, wallpapers, OSD, lock, live
welcome, notification server), `arctic-session mako|nm-applet|clipboard|idle`, `arctic-settings
--check-binds` (once: where shortcuts moved, your shortcuts an Arctic key shadows). The Quickshell
polkit agent is used if `Quickshell.Services.Polkit` works, else lxqt-policykit via
`arctic-session polkit`. Notifications work the same way: the shell owns
`org.freedesktop.Notifications` (toasts, the notification centre, do not disturb), so
`arctic-session mako` does nothing in the shell's session; the shell stops a mako started early by
D-Bus activation and runs `arctic-session mako --fallback` if nobody could take the name.
waybar/fuzzel configs stay in the dotfiles as a fallback (`ARCTIC_SHELL=waybar`).

Quickshell IPC (for keybinds): `quickshell -p /usr/share/arctic/shell ipc call <target> <fn>`,
wrapped by `arctic-shell-ipc <target> <fn>` (in arctic-shell). Targets: `launcher toggle`,
`wallpapers toggle`, `apps install|remove|open <page>|source <name>|search <page> <text>|uninstall
<desktop-id>` (Get apps), `power toggle`, `osd volume|brightness|brightnessLevel`, `lock lock`, `keys toggle`,
`notifications center|dismiss|dismissAll|invoke|dnd <mode>` (through `arctic-notify` and
`arctic-dnd`, which fall back to makoctl), `keyboard next|set|menu`, `clipboard toggle`,
`emoji toggle`, `record open|refresh`, `share pick <fifo>`, `capture freeze <dir>|thaw`, and for
the bar's own menus `panel toggle|open|close <name>` (network, bluetooth, sound, battery,
calendar, media, display, notifications, keyboard), `quick toggle|open [page]` (Quick Settings),
`toggle set|get|states|refresh`, `bar focus` (keyboard mode), `bluetooth pair`,
`media playPause|next|previous`, `audio nextOutput`. Mango binds (Super + A,
Super + Ctrl + W/B/A/P/D/T/M, Super + Alt + B) and the arctic-* helpers call these.
Capture (arctic-desktop-config): `arctic-screenshot`, `arctic-ocr`, `arctic-colorpick` and
`arctic-record` select with slurp and capture with grim / wf-recorder; `arctic-capture` parses
Mango's IPC for them. Screen sharing in Mango sessions: `/etc/xdg/xdg-desktop-portal-wlr/mango`
(`chooser_type=simple`) runs `/usr/libexec/arctic/arctic-share-picker`, which lists every monitor
and window (the shell's "Share your screen" card over IPC, else fuzzel) and prints
xdg-desktop-portal-wlr's `Monitor: <output>` / `Window: <id>`.

### 3.1 App theming

Every app and menu follows the active theme (`~/.config/arctic/current`, switched by
`arctic-theme`): either it reads its colours through that link, or a theme hook updates it.
App colour files are templates in `design/themegen/templates/` (placeholder syntax: the theme
engine's interface; checked by `design/themegen/tests/test_app_templates.py`), rendered into
every theme folder: `templates/<path>.tmpl` → `<theme>/<path>`.

**Toolkits and system settings**

| What | Mechanism | Files |
|---|---|---|
| GTK 3 apps (Thunar, Zen's menus, Inkscape, …) | Theme `adw-gtk3` / `adw-gtk3-dark` (package `adw-gtk3-theme`), which uses libadwaita's named colours, so the theme's `gtk.css` recolours it | `~/.config/gtk-3.0/gtk.css` imports `arctic-colors.css` (dotfiles: link to `../arctic/current/gtk.css`; the 10-gtk hook replaces it with a copy); `settings.ini` (`gtk-theme-name=adw-gtk3`, dark variant via `gtk-application-prefer-dark-theme`) |
| GTK 4 / libadwaita apps (Nautilus, Celluloid, GNOME apps) | `color-scheme` through the settings portal; colours from `~/.config/gtk-4.0/gtk.css` | `~/.config/gtk-4.0/{gtk.css,arctic-colors.css,settings.ini}` (no `gtk-application-prefer-dark-theme`: libadwaita rejects it) |
| gsettings defaults | dconf **distro** database (Fedora's `/etc/dconf/profile/user` reads user → local → site → distro; `local.d` stays the administrator's) | `packaging/dconf/10-arctic` → `/etc/dconf/db/distro.d/10-arctic`, `dconf update` in `%posttrans`: `org.gnome.desktop.interface` gtk-theme `adw-gtk3-dark`, color-scheme `prefer-dark`, accent-color `yellow`, icon-theme `Adwaita`, cursor-theme `Adwaita`, cursor-size 24, font-name `Figtree 11`, document-font-name `Figtree 11`, monospace-font-name `JetBrains Mono 10` |
| Portals | Mango's `/usr/share/xdg-desktop-portal/mango-portals.conf` (`default=gtk`): xdg-desktop-portal-gtk implements `org.freedesktop.impl.portal.Settings` (color-scheme, contrast, and the `org.gnome.desktop.interface` keys). It has no `accent-color`: libadwaita's accent comes from `gtk.css` | — |
| Qt 5 and Qt 6 apps (VLC, OBS, …) | `QT_QPA_PLATFORMTHEME=qt6ct` (qt5ct and qt6ct both register the keys `qt5ct` and `qt6ct`): Fusion, the theme's palette, Figtree 11 / JetBrains Mono 10, Adwaita icons, portal file dialogs. qt5ct/qt6ct watch their config folder and re-read the palette ~3 s after it changes (20-qt hook). Kvantum is not used: Fedora's build pulls the same KDE Frameworks, and its themes are SVGs, not a palette | `templates/qt6ct/colors/arctic.conf.tmpl` (22 roles), `templates/qt5ct/colors/arctic.conf.tmpl` (21); `~/.config/qt6ct/qt6ct.conf`, `~/.config/qt5ct/qt5ct.conf` (`color_scheme_path=~/.config/arctic/current/qt*ct/colors/arctic.conf`, `custom_palette=true`); `env=QT_QPA_PLATFORMTHEME,qt6ct` in `~/.config/mango/arctic/look.conf` (apps started from the desktop) and `~/.config/environment.d/10-arctic.conf` plus the package's `/usr/lib/environment.d/50-arctic-qt.conf` (D-Bus/systemd activated apps; read after, so it also replaces the `xdgdesktopportal` of copies made by 0.1). The Arctic shell and the installer keep `qt6ct` too: the launcher's apps inherit the shell's environment, and the shell's controls take colours and fonts from `Theme.qml` |
| Icons | Adwaita (+ AdwaitaLegacy, in the image already) for GTK and Qt. Papirus (with amber folders) was considered: 116 MB installed, and `papirus-folders` is not in Fedora | dconf, `settings.ini`, `qt*ct.conf` |
| Cursor | Adwaita 24 px (in the image already; Bibata is not in Fedora). Mango's `cursor_theme`/`cursor_size` also export `XCURSOR_THEME`/`XCURSOR_SIZE` to apps and to systemd/D-Bus | `~/.config/mango/arctic/look.conf`, dconf, `settings.ini`, `environment.d` |
| Flatpak apps | Global override `filesystems=xdg-config/gtk-3.0:ro;xdg-config/gtk-4.0:ro;xdg-config/fontconfig:ro;` (Flatpak also binds these into the app's own config folder, which is where GTK looks). They can't see `/usr/share/arctic`, hence the copy in `arctic-colors.css`. No `GTK_THEME` (it would replace libadwaita's stylesheet). GTK 3 Flatpaks load the theme named by the portal's `gtk-theme` from the runtime extensions `org.gtk.Gtk3theme.adw-gtk3` / `-dark`: hidden catalog modules `modules/_system/adw-gtk3-flatpak`, `adw-gtk3-dark-flatpak` (always installed from Flathub, deferred to first boot when offline; Flatpak also fetches the active one itself with any app install, since the dconf default names it). `tools/build-iso.sh` adds both when it preinstalls Zen. Host icon themes are visible to Flatpak apps in `/run/host/share/icons` | `packaging/flatpak/global` → `/var/lib/flatpak/overrides/global` (`%config(noreplace)`; `flatpak override --system` edits the same file) |

**Apps**

| App | Mechanism | Template → theme file | Wiring | Live |
|---|---|---|---|---|
| Quickshell shell, launcher, OSD, lock | `shell/Theme.qml` watches `theme.json` | (engine) | — | yes |
| Mango, kitty, mako, fuzzel, swaylock, waybar | the engine's existing outputs | (engine) | `include`/`source=` of `~/.config/arctic/current/…` | built-in reloads |
| Thunar | GTK 3 (above) | — | — | light/dark: yes; colours: next start (GTK reads `gtk.css` once) |
| VLC | Qt 5 via qt5ct (above) | `qt5ct/colors/arctic.conf` | `~/.config/qt5ct/qt5ct.conf` | yes (20-qt) |
| Zed (Flatpak `dev.zed.Zed`, or native) | theme family "Arctic" (one theme, `appearance` = the palette's mode), Zed schema v0.2.0 | `zed/themes/arctic.json` | 30-zed hook copies it to `~/.var/app/dev.zed.Zed/config/zed/themes/` (Flatpak) and `~/.config/zed/themes/` (native, if that folder exists) and writes `settings.json` (`"theme": "Arctic"`, fonts) only where none exists; skel ships `~/.config/zed/settings.json` | yes (Zed reloads theme files) |
| yazi | `theme.toml` (keys of yazi 26.x's preset only) | `yazi/theme.toml` | `~/.config/yazi/theme.toml` → `../arctic/current/yazi/theme.toml` | next start |
| btop | theme file | `btop/arctic.theme` | `~/.config/btop/themes/arctic.theme` → `../../arctic/current/btop/arctic.theme`; `~/.config/btop/btop.conf` `color_theme = "arctic"`, `theme_background = false` | next start |
| zsh prompt, completion menu, zsh plugins | `ARCTIC_PROMPT_COLORS` (24-bit when `COLORTERM=truecolor`, else ANSI 2/3/1/8), `ma=` selection colour, `ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE`, `ZSH_HIGHLIGHT_STYLES` | `zsh/colors.zsh` | `~/.zshrc` sources it and re-sources it before the next prompt when the link or file changes | next prompt |
| fzf | options file | `fzf/fzfrc` | `FZF_DEFAULT_OPTS_FILE` in `~/.zshrc` and `~/.bashrc.d/arctic.sh` (your `FZF_DEFAULT_OPTS` still apply on top) | every run |
| fastfetch, `neofetch` | whole fastfetch layouts (JSONC has no include), colours as `#rrggbb` (fastfetch ≥ 2.42): the fox (`logo.txt`, the mark in quadrant blocks, `branding/tools/fastfetch_logo.py`) in `term-foreground` with `ansi-3` eyes; `config.jsonc`: keys `ansi-6`, user `ansi-3` bold, rule `ansi-8`, percentages `success`/`warning`/`error`, lines os kernel uptime packages shell wm terminal theme cpu gpu memory disk updates (os, wm, theme, updates from `arctic-fetch --info …`: "Arctic Linux 0.2 (Fedora 44)", "Mango", the theme's label, the update status file — never dnf or the network); `neofetch.jsonc`: fastfetch's neofetch preset with neofetch's key names, keys and title `accent-text` | `fastfetch/config.jsonc`, `fastfetch/neofetch.jsonc` | `~/.config/fastfetch/config.jsonc` → `../arctic/current/fastfetch/config.jsonc` (a copy of yours replaces the link); `neofetch` reads `~/.config/fastfetch/neofetch.jsonc`, else the active theme's, else Polar night's, else fastfetch's `neofetch` preset. arctic-fetch's info column is `fastfetch --config greeting.jsonc --logo none --pipe false` (`~/.local/share/arctic/fastfetch/`, else `/usr/share/arctic/fastfetch/`; palette slots, like the fox) | every run |
| bat, delta (not installed) | `BAT_THEME=ansi` (delta honours it): the terminal's palette | — | `~/.zshrc`, `~/.bashrc.d/arctic.sh` | yes |
| bash prompt | ANSI colours (the terminal palette) | — | — | yes |
| foot, Alacritty (terminal alternatives) | same palette as kitty | `foot/colors.ini` (`[colors-<mode>]` + `initial-color-theme`), `alacritty/colors.toml` | `~/.config/foot/foot.ini` `include=~/.config/arctic/current/foot/colors.ini`; `~/.config/alacritty/alacritty.toml` `general.import` | new windows |
| Zen Browser | light/dark through the portal (`prefers-color-scheme`); optional accent: pref `zen.theme.accent-color` | `zen/user.js` | 40-zen hook, only with `"zen_theme": true` in `~/.config/arctic/settings.json` (`arctic-theme zen on\|off`): a marked block in each profile's `user.js` (Flatpak `~/.var/app/app.zen_browser.zen/.zen` or `…/config/zen`, `~/.zen`, `~/.config/zen`), removed again when off. userChrome.css is not used (needs a legacy-stylesheet pref and breaks with Zen updates) | next start |
| Collabora Office (Flatpak, KDE runtime, a Qt WebEngine shell around the Collabora Online UI) | light/dark through the portal (Qt's colour scheme → the web UI's `prefers-color-scheme`); no accent | — | — | — |
| Firefox, Chromium, Electron apps (Signal) | portal colour scheme | — | — | yes |
| Nautilus, Celluloid, LibreOffice (GTK 3 VCL), GIMP, Inkscape | GTK 3/4 (above) | — | — | as GTK |
| Not themed: Helix, Neovim, VSCodium, OnlyOffice, Steam, mpv's OSD, fish (uses the terminal's ANSI colours) | their own themes | — | — | — |
| Tray menus | drawn by the shell (QsMenuOpener) in the bar-menu style, from the shell's tokens | — | — | yes |
| GTK/Qt context menus, dialogs | inherit their toolkit's theme; Mango draws no menus | — | — | — |

**Theme hooks** (`packaging/theme-hooks.d/` → `/usr/share/arctic/theme-hooks.d/`, run by
`arctic-theme reload` after the built-in reloads with `ARCTIC_THEME_DIR` (realpath of `current`),
`ARCTIC_THEME_MODE=dark|light` and `ARCTIC_THEME_NAME`, 5 s each; each is quick, exits 0 and
touches only files it wrote or links it shipped). GTK has one owner: after the hooks,
arctic-theme sets `color-scheme` and `gtk-theme` (`adw-gtk3-dark`/`adw-gtk3`, through `''` when
the name is unchanged so GTK re-reads `gtk.css`; plain Adwaita only when adw-gtk3 is missing)
and `gtk-application-prefer-dark-theme` in `~/.config/gtk-3.0/settings.ini`, so GTK apps restyle
once, with the copies `10-gtk` just made:

| Hook | Does |
|---|---|
| `10-gtk` | `~/.config/gtk-{3,4}.0/arctic-colors.css` = copy of `$ARCTIC_THEME_DIR/gtk.css` (replaces the shipped link or its own earlier copy, never your file) |
| `20-qt` | replaces `~/.config/qt5ct/qt5ct.conf` and `qt6ct.conf` with identical copies, which makes running Qt apps re-read the palette |
| `30-zed` | copies `zed/themes/arctic.json` into Zed's themes folders (above) |
| `40-zen` | the optional Zen accent (above) |

**Packages** (`arctic-desktop-config` Requires, also listed in `iso/kiwi/config.kiwi`):
`adw-gtk3-theme`, `qt6ct`, `qt5ct`, `adwaita-icon-theme`, `adwaita-cursor-theme`, `dconf`,
`flatpak`, `fastfetch` (2.60 in Fedora 44, 2.68 in its updates: the layouts use only modules and
options both have, checked by `design/themegen/tests/test_fastfetch.py`); `arctic-desktop`
Recommends `btop`. Added to the image (dnf5 against Fedora 44, vs the
0.1 image's package list): adw-gtk3-theme 1.1 MB, btop 1.8 MB (+ rocm-smi 2.9 MB, its weak
dependency), qt5ct + qt6ct about 150 MB installed / 63 MB download, because Fedora builds them
with KDE colour-scheme support: KDE Frameworks 5 and 6 (ki18n 17 + 18 MB, kwidgetsaddons 7 + 5 MB,
…), `breeze-icon-theme` 26 MB and `kf6-breeze-icons` 25 MB (kf5/kf6-kiconthemes) and
`plasma-breeze-common` 40 MB (mostly Plasma's "Next" wallpaper, via kf5-kconfigwidgets). qt6ct
alone is 80 MB of that; no default app is a Qt 6 widget app, so it is the first thing to drop if
the ISO needs room (Qt 5 apps stay themed through qt5ct, which also answers to "qt6ct").

### 3.2 Settings app (arctic-settings)

A standalone Quickshell app (`settings/shell.qml`, a `FloatingWindow` titled "Arctic Settings";
Mango floats it by title, `rules.conf`), opened by `arctic-settings [page]` (`Super + S`, since
`Super + ,`/`.` already move focus between monitors in `binds.conf`; the
launcher; the first item of the shell's power menu and of `arctic-power`'s fuzzel fallback).
Pages: appearance, windows, displays, input, shortcuts, apps, network, bluetooth, sound,
updates, power, startup, about. It looks native because it reuses the installer's components
(`settings/components` = `installer-ui/components`, checked by `settings/tests/test_app_files.py`)
on the live tokens (`~/.config/arctic/current/theme.json`, like the shell's Theme.qml).
Every read and write goes through `settings/scripts/arctic_settings.py` (JSON out, tested).

**Files it writes** (user-level only; atomic; validated with its key table and `mango -c FILE -p`;
previous versions in `~/.local/state/arctic/settings-backups/`):

| File | Contents |
|---|---|
| `~/.config/mango/settings.conf` | Mango options (only keys Mango 0.17.3 parses: gaps, borders, radius, animations + durations, blur, shadows, opacity, focus, `new_is_master`, `default_mfact`, cursor, repeat, `xkb_rules_*` (empty = `key= # none`), trackpad and mouse), `tagrule=id:*,layout_name:<layout>`, `monitorrule=name:^<out>$,…`, `keymode=default` + `bind=MODS,KEY,spawn_shell,COMMAND`, `exec-once=` startup apps; unknown lines are kept at the end |
| `~/.config/mango/config.conf` | `source-optional=~/.config/mango/settings.conf` inserted before the `user.conf` line when missing (the skel copy has it) |
| `~/.config/arctic/default-apps` | `role=command` for browser, terminal, files, editor (read by `arctic-open` after `/etc/arctic/default-apps`) |
| `~/.config/mimeapps.list` | `[Default Applications]` for links and files (as `xdg-mime default`) |
| `~/.config/arctic/idle.conf` | `lock_after=`, `suspend_after=` (seconds, 0 = never), read by `arctic-session idle` |
| `$XDG_RUNTIME_DIR/arctic-settings-display.json` | the display layout to go back to while a change waits to be kept |
| `~/Pictures/Wallpapers/` (your wallpaper folder) | pictures you add (copied after Pillow decodes them; renamed/deleted only inside that folder, never the one in use); Wallhaven downloads in `wallhaven/wallhaven-<id>.<ext>` |
| `~/.config/arctic/wallhaven.json` (mode 600) | Wallhaven filters (`categories`, `purity` — NSFW only with a key —, `sorting`, `range`, `fit`) and the optional `api_key` (never sent to the UI) |

**Commands it calls** (each missing one hides or explains its controls): `mmsg dispatch
reload_config`, `mmsg get all-devices|all-clients`, `mango -p`; `arctic-theme set <name>|auto
on|off|mode auto|dark|light|current --json|list --json` (the theming engine; falls back to
`arctic-theme winter|polar-night`); `arctic-update status --json|now|apply|channel
stable|testing|auto on|off` (the updater); `arctic-motion on|off`; the shell's
`scripts/wallpapers.py list|apply` (→ `arctic-wallpaper`); `arctic-session idle --restart`;
`wlr-randr --json` / `wlr-randr --output …`; `nmcli`; `gdbus` (power profiles, tuned-ppd);
`gsettings` (GTK text size, cursor); tools it opens: `nm-connection-editor`, `blueman-manager`,
`pavucontrol`/`pwvucontrol`, `wdisplays`, `arctic-shell-ipc apps install|remove`, `xdg-open`.
Bluetooth and sound use BlueZ and PipeWire directly (Quickshell.Bluetooth, .Services.Pipewire).

Wallpapers (Appearance): the shell's `scripts/wallpapers.py` (`list`, `apply`, `import`, `delete`,
`rename`) and `scripts/wallhaven.py` (`search`, `preview`, `download`, `set`, `state`, `key`,
`prefs`; stdlib urllib + Pillow), through the helper's `wallpaper-import|delete|rename` and
`wallhaven …`. Only wallhaven.py talks to the network: https://wallhaven.cc/api/v1/search (and
`/settings` to check a key), thumbnails and pictures from th./w.wallhaven.cc (URLs checked); API
calls are counted in `~/.cache/arctic/wallhaven/api-calls.json` under a lock (45 a minute: wait up
to 8 s, else `{"wait": N}`), searches cached 15 min, thumbnails in `~/.cache/arctic/wallhaven/`;
offline answers `{"ok": false, "offline": true}`. "Fit my screens" = `atleast` of the largest
enabled output and each output's `ratios` (`wlr-randr --json`, rotation applied). "Add pictures…"
is QtQuick.Dialogs' FileDialog (the portal through qt6ct), plus a DropArea for `file://` URLs.

Displays: an arrangement editor (every display a rectangle to scale; drag and drop, or `Tab` to
one and move it with the arrow keys) whose geometry is all in the helper, as pure tested functions:
`arctic_settings.py display-arrange LAYOUT [--move NAME X Y [--threshold PX] | --nudge NAME
left|right|up|down | --main NAME | --enable NAME | --disable NAME | --anchor NAME]` (nothing is
applied). Positions are logical px; a display's size there is its mode, turned for 90°/270°,
divided by the scale in single precision and cut to whole pixels (wlroots
`wlr_output_effective_resolution`: 2560×1600 at 150 % is 1706×1066). Every display that is on
touches another along an edge (a dropped one by at least 1/8 of the shorter edge), none overlap,
and the top-left corner is 0,0 (XWayland misreads clicks at negative positions); a drop goes to
the nearest such place, lined up with the others' edges or centres within 12 screen px, and
displays left unconnected follow; after a scale, rotation or mode change the others settle round
that display on the side they were on; the last display that is on can't be switched off.
Apply runs `wlr-randr` at once (the tidied layout) and asks to keep it for 15 s; a detached
watchdog (`arctic_settings.py display-revert --if-pending TOKEN --after 20`) puts the old layout
back even if Settings is gone; kept layouts become `monitorrule` lines, the main display's
first; a display switched off is never saved (`disable:1` would also blank a laptop's only
screen), so off lasts until logout. Rules of displays that aren't connected (or are off) stay,
without `x`/`y` where they would overlap the kept layout (one rule per display: the monitor at
home must not come back on top of the laptop's place from work).

Mango 0.17.3's `monitorrule` (read in the 0.17.3 tarball: `src/config/parse_config.c`,
`parse_option`, the `monitorrule` branch; applied by `src/manage/monitor.c`
`apply_rule_to_state`): comma-separated `key:value`, e.g.
`monitorrule=name:^HDMI-A-1$,width:3840,height:2160,refresh:60,x:1706,y:0,scale:2,rr:0,vrr:0`.
`name` is a regex (hence `^…$`; `make`, `model`, `serial` also match); `x`/`y` are logical px
(left out: placed automatically, `wlr_output_layout_add_auto`); `scale`; `rr` 0–7 is the
`wl_output_transform` (1 = 90, 2 = 180, 3 = 270, 4 = flipped, 5–7 = flipped-90/180/270, the order
of wlr-randr's names); `vrr` 0/1; the mode is used only when `width`, `height` and `refresh` are
all set, else the preferred one; also `disable`, `custom`, `hdr`, `hdr_*`, `icc`. A new output
takes the first rule that matches (`handle_new_output`), a config reload the last one
(`parse_config.c` `reapply_monitor_rules`), so Settings writes one `^NAME$` rule per display.

Main display: Mango has no primary output (no option or dispatch for one in 0.17.3; `monitor.c`
`set_selected_monitor` keeps XWayland's RandR primary on the focused display,
`xwayland_primary.c`). At login `main.c` selects the monitor under the pointer, which starts at
0,0, so that display is where you start: focus, the first windows, the launcher, OSD and menus (the
shell follows the focused output, `shell/Outputs.qml`) and mako's notifications (no `output=`).
The bar is on every display (`Variants` over `Quickshell.screens`). So Settings' "main display"
is the one covering the layout's top-left corner (else the one nearest to it, where Mango moves
the pointer), and **Make main** swaps it with the display there; nothing stores a primary
separately.

The live image (`iso/kiwi/config.kiwi`, and so the installed system) lists `arctic-settings`,
`nm-connection-editor`, `blueman`, `pavucontrol` and `wlr-randr` explicitly.

IPC: `quickshell -p /usr/share/arctic/settings ipc call settings open|reveal|search|page|pages|ready|set|value|quit`
(`arctic-settings` uses `page`/`open`; `settings/dev/headless.sh` the rest).

### 3.3 System helpers (0.3)

Command-line helpers in `dotfiles/.local/bin` (→ /usr/bin); each status prints one JSON line,
`{"ok": true, …}` or `{"ok": false, "error": "<sentence>"}`. Settings' commands for them are in
`settings/scripts/arctic_system.py`; the bar and Quick Settings use the same commands.

| Helper | Does | State |
|---|---|---|
| `arctic-nightlight on\|off\|toggle [--quiet]\|status --json\|set K=V…\|apply` | night light (wlsunset) on a schedule: sunset to sunrise (location from the time zone), custom hours or always | `~/.config/arctic/nightlight.conf`; `$XDG_RUNTIME_DIR/arctic/nightlight.json` |
| `arctic-keep-awake on [MIN]\|off\|toggle [--quiet]\|status --json` | no lock or suspend for a while | `$XDG_RUNTIME_DIR/arctic/keep-awake` (end time, 0 = until off) |
| `arctic-screensaver run\|status` | answers `org.freedesktop.ScreenSaver` (apps keeping the screen on) | `$XDG_RUNTIME_DIR/arctic/inhibitors.json` |
| `arctic-display status --json\|mode [NAME]\|lid-closed\|lid-opened\|screens off\|on` | Super+P / display key, the lid (`switchbind=fold\|unfold`), screens off after the lock | `$XDG_RUNTIME_DIR/arctic/display.json`; `~/.config/arctic/lid.conf` |
| `arctic-effects status\|lighter auto\|on\|off\|game on\|off\|toggle\|apply` | lighter effects in VMs / without a GPU driver; game mode | `~/.config/arctic/effects.{json,conf}` (config.conf sources the .conf) |
| `arctic-power can\|prepare\|hibernate\|firmware\|…` | power menu checks (busy installs, closing windows gracefully, Hibernate, firmware setup) | — |
| `arctic-drives list\|eject DEV` | removable drives (udisks2; udiskie mounts them) | `~/.config/arctic/drives.conf` |
| `arctic-share`, `arctic-gpu`, `arctic-restart`, `arctic-sysmon` | LocalSend / KDE Connect; discrete GPU (switcheroo-control); restart sound, Wi-Fi, Bluetooth, the shell; system monitor | — |

`arctic-session idle` (swayidle) reads `~/.config/arctic/idle.conf`: `lock_after=`,
`suspend_after=` (plugged in), `lock_after_battery=`, `suspend_after_battery=` (missing = the
same), `dim_before_lock=`, `screen_off_after=`; keep awake and `inhibitors.json` drop the lock and
suspend timeouts. `arctic-session power-watch` restarts it when the power source changes.
`arctic-session nightlight|drives|lid|effects|screensaver` start the rest from autostart.conf.
System-wide changes: polkit (`timedatectl`, `localectl`, `hostnamectl`, AccountsService) or
`pkexec /usr/libexec/arctic/arctic-system-helper` (action `org.arcticlinux.system`,
`auth_admin_keep`; firewall allows, sshd, keys-only SSH, snapper). Units:
`arctic-flatpak-update.timer` (system and user), `gcr-ssh-agent.socket` (user preset), and the
XDG autostart drop-ins (`mango-session.target.d/arctic-autostart.conf`).

## 4. Engine ↔ installer UI protocol

- `arcticd` listens on `/run/arcticd.sock` (systemd socket activation: `arcticd.socket`,
  `ListenStream=/run/arcticd.sock`, `SocketMode=0660`, `SocketGroup=wheel`; `arcticd.service`
  runs as root). `arcticd --socket PATH` and `arcticd --mock` for development: mock mode
  simulates disks, Wi-Fi, locales and an install with realistic progress and one optional-app
  failure, and never touches the system.
- The UI runs `arctic-install bridge [--socket PATH]`, which relays newline-delimited JSON
  between its stdin/stdout and the socket (Quickshell `Process` + `SplitParser`, as in
  `shell/AppsService.qml`). `arctic-install bridge --mock` starts an in-process mock engine
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
| `CheckPassphrase` | `{text}` | `{score:0-4, label:"Too short"\|"Weak"\|"Fair"\|"Good"\|"Strong", words:int, ok:bool}` (ok = score ≥ 2 "Fair"). Advisory only: the score drives the meter and the weak-secret warnings (§4.1 rows 6–7); Next, the Summary and Start accept any non-empty passphrase or password |
| `SuggestPassphrase` | — | `{text:"four random words"}` (EFF short wordlist, embedded) |
| `SuggestAccount` | `{full_name}` | `{username, hostname}` (hostname = `{username}-{model}` from DMI, lowercased, `-` joined) |
| `SetSecrets` | `{luks_passphrase?, user_password?}` | `{ok}` (kept in memory only, never logged or written; an empty string clears it, and Next / Start then refuse with `Type a passphrase.` / `Type a password.`) |
| `EstimateDownload` | `{selection}` | `{apps:int, drivers?:int, bytes:int, label:"9 apps · 1.4 GB download"}` (drivers are not apps: `"8 apps + 2 drivers · 3 GB download"`) |
| `GetSummary` | — | `{rows:[{step, icon, label, value}], warning, primary_label}` (rows for welcome, keyboard, timezone, disk, encryption, account, apps — each `step` is a Goto target; primary "Erase disk and install" or "Install alongside {OS}"). A secret below its `min_score` is noted in its row, not in `warning` (the Summary page doesn't scroll, so neither gets taller): the encryption row's value becomes "On — easy-to-guess passphrase; you’ll type it each time the computer starts" (encryption on), and the account row's value ends with ", easy-to-guess password". When a driver was detected an 8th row follows: `{step:"apps", icon:"cpu", label:"Drivers", value:"NVIDIA driver for your NVIDIA GeForce RTX 4060 Max-Q / Mobile; …"}` (+ ". Secure Boot is on: you’ll confirm the driver’s key once after restarting" when a built driver needs the key; "None — …" when all were unticked). The UI takes the row's `icon` |
| `Start` | — | `{ok}` then events. Also "Try again" after a failure. Re-probes the disks first: if the chosen disk is gone, is not the same device (model/serial/WWN/size) or, alongside, its partitions or free space changed, it answers `{code:"state"}` and refuses until the Disk step is passed again |
| `RetryModule` / `SkipModule` | `{id}` | `{ok}` |
| `SaveLog` | — | `{path, on_usb, device?, label?, safe_to_remove, message}`: to a FAT/exFAT file system on a removable disk that is not the install medium (mounted in place, else mounted, written, synced and unmounted: `path` is then the file's path on the stick and `safe_to_remove` true), else `/home/liveuser` or /tmp (lost on restart). `message` is the sentence to show |
| `Reboot` | — | `{ok}` |
| `Subscribe` | — | `{ok}` then events on this connection |

- Events:
  - `{"event":"progress","percent":0-100,"phase":"disk"|"copy"|"configure"|"bootloader"|"apps"|"finalize","status":"Installing Zed, your code editor…","eta_seconds":420,"substeps":[{"id":"disk","label":"Preparing the disk","state":"done"|"active"|"todo"},…4 items: disk, system ("Copying Arctic Linux"), apps ("Installing your apps"), finish ("Setting up your account")]}`
  - `{"event":"module","id":"zed","name":"Zed","status":"queued"|"downloading"|"installed"|"failed"|"skipped"|"deferred","percent":0-100}`
  - `{"event":"attention","module":{"id","name"},"message":"The download server didn't answer.","optional":true}` → UI shows step 11 (Try again / Skip {App}); core failures: `{"event":"failed","message":"…","fatal":true,"can_change":true}` → Save log / Try again / Change (Back or Goto).
  - `{"event":"done","apps_installed":9,"first_name":"Noa","notes"?:["…"],"drivers"?:[{id,name,device,status:"installed"|"deferred"|"skipped",text}],"secure_boot"?:{code,title,intro,steps:[…],note,failed?}}` — `drivers` lists what happened to each ticked driver with a sentence for it (drivers get no `module` events and are not in `apps_installed`); `secure_boot` is present when the akmods signing key waits for enrolment in shim's MokManager on the next restart (Secure Boot enforced, UEFI, a driver built by akmods): `code` is the one-time password (8 digits, typed on the number row — MokManager reads the keyboard as US QWERTY), `steps` the MokManager screens. `notes`: sentences about a success with a caveat (the new disk couldn’t be closed at the end), a banner on the Done screen. With `failed:true` (mokutil refused) there is no code and the steps say how to enroll the key by hand. Driver failures use the `attention` event like apps (title "The NVIDIA driver couldn’t be installed", skip label "Skip the driver").
  - Status lines follow `design/guidelines/20-installer-copy.md`.

### 4.1 Wizard steps (ids fixed; copy = design/guidelines/20-installer-copy.md)

| # | id | data | options |
|---|---|---|---|
| 1 | `welcome` | `{language:"en_US.UTF-8"}` | `{languages:[{id,name(native),english}], suggested}` |
| 2 | `keyboard` | `{layout:"us", variant:"", xkb:{layout, variant, options, keymap, latin}}` (`xkb` is read-only, what the choice gives: Latin layouts alone; non-Latin ones as `us,<layout>` with `grp:alt_shift_toggle` and a Latin console keymap). A valid SetStep also writes `xkb` to the live system's `/etc/arctic/mango/keyboard.conf` (sourced by the live session); the UI then runs `mmsg dispatch reload_config`, so passwords are typed as on the installed system | `{layouts:[{layout,variant,name,description,suggested:bool}]}` |
| 3 | `network` | `{}` | `{online,wired,ssid,driver_hint?}` (+ ScanWifi/ConnectWifi); auto-skipped when wired & online. `driver_hint` is set when a detected Wi-Fi card only works once its driver is installed (Broadcom wl): how to get online meanwhile |
| 4 | `timezone` | `{timezone:"Asia/Jerusalem", auto_time:true}` | `{detected:{city,timezone,source:"network"\|"default"}, regions:{Europe:[{city,timezone}],…}}` |
| 5 | `disk` | `{disk:"/dev/nvme0n1", mode:"erase"\|"alongside"}` | `{disks:[{path,model,size_bytes,size_label,removable,install_media:bool,existing_os:[…],alongside_possible:bool,alongside_label:"Uses 120 GB of free space"}]}` (install media excluded; alongside needs ≥ 40 GB free, on UEFI an ESP to share, on MBR room for two primary partitions) |
| 6 | `encryption` | `{enabled:true}` | `{min_score:2, weak_warning, passphrase_set, strength?}` (passphrase via SetSecrets; `strength` is the saved one's CheckPassphrase result). `min_score` is the warning threshold, not a gate: below it the step shows `weak_warning` ("This passphrase is easy to guess: someone who has your computer could read your files. You can still use it.") in a warning banner and Next still works. Next needs a passphrase (both fields matching, English (US) characters on a non-Latin layout — checked by the UI) |
| 7 | `account` | `{full_name, username, hostname, autologin:false}` (username: not a user or group the copied system has) | `{hostname_hint:"Suggested from your name and computer", min_score:1, weak_warning, weak_disk_warning, password_set, strength?}` (password via SetSecrets). As on step 6, `min_score` only warns: below it `weak_warning` ("This password is easy to guess: someone at your computer could log in as you. You can still use it."); with "Use this password for the disk passphrase too", below "Fair" (`ok` false) `weak_disk_warning` ("This password is easy to guess: someone who has your computer could read your files. You can still use it."). Any non-empty password is accepted |
| 8 | `apps` | `{selection:{drivers:["nvidia","intel-media"],browser:["zen"],editor:["zed"],…}}` | catalog: `{categories:[{id,name,choice:"one"\|"any",note,hardware?}], modules:[{id,name,summary,category,default,tile,download_mb,source,in_live_image,device?}]}` — the `drivers` category (`hardware:true`) comes first and is present only when a driver matched this computer's hardware; its modules carry `device` (the detected card's name, also filled into `summary`) and are `default` (ticked) when detected. Selecting a driver whose hardware wasn't found is a field error on `drivers` |
| 9 | `summary` | — | via GetSummary |
| 10 | `install` | — | events |
| 11 | (attention/error, not a step) | | |
| 12 | `done` | — | `{apps_installed, first_name}`; options `{card_title, card, secondary, drivers?, secure_boot?}` (as in the `done` event) |

Categories for the picker come from the design (`CATEGORIES` in the design bundle.js):
browser "one" ("Becomes your default browser."), editor "many", terminal "one" ("Opens with
Super + Enter."), shell "one" ("What runs inside the terminal."; bash always installed), files
"many", office "one", video "many". These seven sections are always open. After them,
under "More apps", come the optional groups, all "many", marked `collapsed = true` in
`modules/catalog.toml` (they start folded and nothing in them is ticked by default): music,
photos, graphics, recording, chat, email, notes, reading, gaming, security, sync, dev,
containers and extras (utilities). The picker has a search box across every app, and
`proprietary = true` modules carry a Proprietary tag. Tiles for the design's 28 apps are the
design's own; every other module gets a tile drawn the same way (category tint + one line
glyph from its `icon`) by `installer-ui/dev/export-assets.js`.

## 5. Catalog manifest

`modules/<category>/<id>/module.toml` as in PLAN §4.1, fields: `id, name, summary, category,
default, tile, icon, in_live_image, gpu, proprietary, requires, conflicts, [[install]] method = "dnf"|"copr"|"flatpak"|"nix"
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
After the driver transaction the engine also waits (≤ 20 min) until no process runs inside the
target any more (root under /mnt: the background akmods build may take its lock after the
flock). Finalize (internal/installer/release.go): wait for work left in the target, SIGTERM then
SIGKILL helpers (gpg-agent, keyboxd, dbus …) — only processes whose root is the target; `umount
--recursive` (3 tries, then lazy), `sync`, then for LUKS: unmount leftover copies of the target's
mounts in other mount namespaces (`nsenter --target PID --mount -- umount --recursive --lazy`;
services started during the install copy every mount), `udevadm settle` and `cryptsetup close`
with a 0/1/2/4/8 s backoff, `dmsetup remove --retry`, `dmsetup remove --deferred`. The install
is `committed` once the user exists (bootloader done): cleanup then never removes the boot entry
or partitions (the MOK request is still revoked). Once the system is complete (relabelled,
snapper), a release failure is not a failure: logged, the Done event gets a note. dnf in the
chroot and flatpak install/remote-add are run again after 5/15/45 s when they fail on the network
(curl/librepo errors; dnf5's own retries=10 covers downloads, not the metalink).
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
Volume id `Arctic-Linux-0.3` (the installer finds its media by the `Arctic-Linux` prefix). Output
`out/iso/Arctic-Linux-0.3-x86_64.iso` + `.sha256`; `.build-info` also gets the packages' version,
Release suffix, commit and `arctic_repos=enabled|disabled` from out/BUILD-INFO.

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

## 9. Package repository: versions, channels, publishing

Arctic's own packages (all of `arctic-linux.spec` and `mangowm`) update from a signed dnf
repository on the project's GitHub Pages site; Fedora's packages keep coming from Fedora. No COPR.

**Versions.** Both specs: `Release: 1%{?arctic_snapshot}%{?dist}`. `tools/build-rpms.sh` defines
`arctic_snapshot` as `.<commit time>.<build time>.git<commit, 7 hex>` (`--release-suffix auto`,
the default; `none` gives `1.fc44`; any other value is used as given; env
`ARCTIC_RELEASE_SUFFIX`): the commit's committer date as UTC `yyyymmddHHMMSS`, then the build's UTC
`yyyymmddHHMM`, e.g. `arctic-shell-0.2.0-1.20260928030512.202609280310.gitabc1234.fc44`. rpm
compares the commit time first, so a build of newer code is always the newer package, whenever it
was built: the repository's builds of later commits update what an ISO installed, even an ISO
built afterwards from an older commit (a re-run for an old tag), and a stable build of a later
commit updates a testing build. The same commit built twice: the later build wins. (Outside a
git checkout the build time stands in for the commit time.) Every build of every commit is a new
Release of all 15 packages, so each publish to stable is a full Arctic update (about 9 MB) for
every stable system, and every package's scriptlets run again: they are written for that
(arctic-plymouth-theme sets the splash only on first install; arctic-selinux skips `semodule`
when its module is unchanged). Version stays the spec's (arctic-linux 0.3.0, mangowm 0.17.3); a
release bumps it with a `%changelog` entry. The ISO workflow builds through the same script, so
the same scheme applies there. `out/BUILD-INFO` (key=value): `version`, `release_suffix`,
`build_time`, `commit_time`, `git_commit`, `git_dirty`, `specs`, `gpg_key` (fingerprint),
`arctic_repos` (`enabled|disabled|not-built`), one `rpm=`/`srpm=` line per package built.

**Site layout** (https://yuvalkolodkingal.github.io/Arctic-Linux/):

```
repo/<channel>/fedora-<releasever>/x86_64/     x86_64 + noarch RPMs, repodata/ (+ repomd.xml.asc)
repo/<channel>/fedora-<releasever>/source/     SRPMs, repodata/ (+ repomd.xml.asc)
repo/<channel>/fedora-<releasever>/PUBLISH-INFO.json   when, which commit, ref and workflow run
RPM-GPG-KEY-arctic                             the public signing key
arctic.repo, arctic-testing.repo               repo files for other Fedora 44 systems (enabled, https gpgkey)
index.html, manifest.json                      landing page; every file with size and sha256
```

Channels: `stable` ← pushes to `main`; `testing` ← pushes to `claude/busy-goodall-j42hmi`
(`repo-testing.yml` starts `repo.yml` on `main` with channel `testing` and that commit, see *Pages
setup*), or Actions → Repository → Run workflow with any channel and ref. Each directory keeps the newest 3 builds (distinct epoch:version-release in rpm order) of every
package name. No debuginfo. One build is ~9 MB of RPMs + ~11 MB of SRPMs, so both channels
stay far below the 900 MB budget `publish-repo.sh` enforces (Pages sites are limited to 1 GB).

**On the system** (`arctic-release`): `/usr/share/dnf5/repos.d/arctic.repo` holds `[arctic]`
(`baseurl=…/repo/stable/fedora-$releasever/$basearch/`, `enabled=1`, `gpgcheck=1`,
`repo_gpgcheck=1`, `gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-arctic`, `metadata_expire=6h`,
`skip_if_unavailable=True` — the live USB and the installer work offline —, `priority=90`, before
Fedora's 99) and `[arctic-source]` (off); `arctic-testing.repo` the same for testing, all off. They
are package files, replaced on updates; choices are overrides in `/etc/dnf/repos.override.d/`
(`sudo dnf config-manager setopt arctic-testing.enabled=1` writes `99-config_manager.repo`).
dnf5 5.4 on Fedora 44 reads `/etc/yum.repos.d`, `/etc/distro.repos.d` and `/usr/share/dnf5/repos.d`
(`dnf5 --dump-main-config`); a file of the same name in `/etc/yum.repos.d` hides the one in
`/usr/share/dnf5/repos.d`. Every package is signed and checked (`gpgcheck=1`): dnf imports the key
into the rpmdb on first use (`-y`, as unattended updates run, accepts it; an interactive `dnf`
asks once). `repomd.xml` is signed too (`repomd.xml.asc`) and checked (`repo_gpgcheck=1`): dnf
imports the key for that check into the repository's cache on the first run with `-y`, which the
automatic update check (`arctic-update stage`), `arctic-firstboot` and Get apps all use. Until
then a dnf run without `-y` — `dnf-makecache.timer`, a declined prompt — skips the repository
(verified on F44: "repomd.xml GPG signature verification error: Signing key not found", exit
status 0), and so does any run after `dnf clean all` until the next `-y` run. Fedora's own
`fedora`/`updates` repositories set `skip_if_unavailable=False`, so they, not Arctic's, are what
fails offline; Arctic's are skipped quietly, which is why publishing checks the site with dnf5
before deploying it (below).

**The key.** `/etc/pki/rpm-gpg/RPM-GPG-KEY-arctic` is installed from
`packaging/release/RPM-GPG-KEY-arctic` (rsa4096 "Arctic Linux Packages", fingerprint
`80F7 5DE9 A23B 6322 46FD 1FF1 BD1A 642B 5436 645A`, the public half of the repository secret).
`tools/build-rpms.sh` can also put a key into Source0 from `--gpg-public-key FILE` or
`ARCTIC_GPG_PUBLIC_KEY` (its content; ci.yml, iso.yml and repo.yml pass the repository secret),
and publishing checks that the committed key is the signing key. Without any key the build still succeeds but
warns, and arctic-release ships both repo files with `enabled=0`; `--require-gpg-key`
(`ARCTIC_REQUIRE_GPG_KEY=1`, repo.yml) makes that an error. The spec's `%check` enforces: key ⇔
`[arctic]` enabled, testing always off, no secret key material. No tool here ever generates or stores a secret
key; signing happens only in repo.yml with the secrets.

**Publishing** (`.github/workflows/repo.yml`; the steps are scripts that run locally too):

1. Channel from the event (push to main → stable, `workflow_dispatch` → input `channel` built
   from input `ref`, default the workflow's commit). Then `gh api repos/<repo>/pages`
   (`pages: read`): no Pages site, a source other than GitHub Actions, or a site URL other than
   the one the packages point at fails the run at once, with what to change.
2. `tools/build-rpms.sh --src <checkout of ref>` with `ARCTIC_GPG_PUBLIC_KEY` and
   `ARCTIC_REQUIRE_GPG_KEY=1`.
3. `tools/lib/arcticrepo.py fetch`: the site as published, so a publish of one channel keeps the
   other. Source: the last successful repo.yml run's `github-pages` artifact (uploaded with
   `retention-days: 90`, downloaded with `gh api` and `actions: read`) when its manifest.json is
   the live one, or newer (the live site still serving the deployment before); else every file
   listed in the live manifest.json, fetched with a cache-busting query and checked against size
   and sha256. Nothing live (404) → the artifact if there is one; a first publish only when
   the runs query worked and repo.yml has never succeeded (else Pages may just be briefly
   unavailable: the run fails). `gh api` calls are retried with backoff; one that keeps failing
   fails the run (404/410 for an artifact that expired meanwhile falls back to the live site, as
   does an artifact that doesn't match its manifest). A live site that can't be fetched
   completely, or one without manifest.json, fails the run; the `start_fresh` input starts both
   channels over on purpose.
4. `tools/publish-repo.sh` (in a fedora:44 container): imports `ARCTIC_GPG_PRIVATE_KEY`
   (`--pinentry-mode loopback`, `ARCTIC_GPG_PASSPHRASE` through a passphrase file; empty works),
   takes its fingerprint and requires `ARCTIC_GPG_PUBLIC_KEY` and a committed
   `packaging/release/RPM-GPG-KEY-arctic` to have the same one; signs every new RPM and SRPM
   (packages already published — same `SHA256HEADER` — are skipped) with
   `rpmsign --addsign` (RPM 6: `%_openpgp_sign gpg`, `%_openpgp_sign_id <fingerprint>`,
   `%_gpg_path`, `%_gpg_sign_cmd_extra_args --batch --yes --pinentry-mode loopback
   --passphrase-file …`) and checks each with `rpmkeys -Kv` against an rpmdb holding only the
   public key; refuses a new arctic-release without that key or with `[arctic]` disabled (it
   would switch updates off for everyone who installs it); prunes; requires every package left
   in the channel to verify (`--resign-old` / the `resign_old` input re-signs after a key
   change); `createrepo_c --update --retain-old-md-by-age=2d` (the metadata a new repomd.xml
   replaces stays two days: Pages lets caches serve the old repomd.xml for up to 10 minutes, and
   the files it names must still be there; the mtimes survive through the Pages artifact); signs
   `repodata/repomd.xml` (detached, armored, checked with gpg); writes the key, the .repo files,
   PUBLISH-INFO.json, index.html and manifest.json; fails over the size budget.
5. `tools/test-repo.sh --signed --channel <channel>`: in fedora:44 with `--network none`, the
   new arctic-release replaces fedora-release, and dnf5 reads the site through `file://` the way
   clients do, with every check on (`gpgcheck=1`, `repo_gpgcheck=1`, `skip_if_unavailable=0`):
   `dnf5 -y makecache` verifies `repomd.xml.asc` (librepo, through rpm-sequoia on F44) for the
   binary and source repositories, `repoquery` lists exactly the channel's files, and dnf5
   installs arctic-backgrounds and reinstalls the new arctic-release from it, checking their
   signatures against the key from arctic-release. Any error fails the run before anything is
   uploaded (gpg and rpmkeys alone in step 4 don't prove what dnf5 accepts).
6. `actions/upload-pages-artifact` (`retention-days: 90`), then the deploy job:
   `actions/deploy-pages` in the `github-pages` environment (`pages: write`, `id-token: write`),
   a check that the deployment's `page_url` is the base URL (fails otherwise) and that the live
   manifest.json is the one just deployed (warns: the CDN may lag).

Permissions: `contents: read` (build job also `actions: read`, `pages: read`). All runs share the
concurrency group `arctic-repository-pages` (`cancel-in-progress: false`), so no two publishes
overlap; GitHub keeps one waiting run per group, so a waiting run can be superseded (shown as
cancelled) — the next push to main, or a re-run, publishes again.

**Pages setup.** Settings → Pages → Source: GitHub Actions (step 1 fails until it is). Secrets
`ARCTIC_GPG_PRIVATE_KEY`, `ARCTIC_GPG_PASSPHRASE` (may be empty), `ARCTIC_GPG_PUBLIC_KEY`; optional
variable `ARCTIC_PAGES_URL` for a custom domain. The `github-pages` environment lets only the
default branch deploy, and a new run waiting in the shared concurrency group would replace a
waiting stable run. So pushes to `claude/busy-goodall-j42hmi` run `repo-testing.yml`, which waits
until no publish is running or waiting and then starts `repo.yml` on `main` with channel `testing`
and the pushed commit as `ref` (a newer push cancels an older forward that is still waiting).

**Release ISOs** (`.github/workflows/iso.yml`) build with `ARCTIC_REQUIRE_GPG_KEY=1` in this
repository (forks without the secret still build, with the Arctic repositories off), and a
release is refused unless the ISO's `.build-info` says `arctic_repos=enabled`: an ISO whose
arctic-release lacks the key would install systems that never get Arctic updates.

**Changing the key** needs a transition release: installed systems only trust the key their
arctic-release carries, so an arctic-release that trusts both keys has to reach them (signed with
the old key) before packages are signed with the new one (`resign_old`). The checks above expect
exactly one key everywhere today; a key change starts by relaxing them for the transition.

**Locally, without a key:** `tools/publish-repo.sh --no-sign --site out/site --channel testing`
(unsigned packages, no repomd.xml.asc) and `tools/test-repo.sh`: arctic-release replaces
fedora-release, `dnf5 repolist --all`, the testing override, `dnf5 makecache`/`repoquery` with
`--network none` succeed (the Arctic repositories are skipped) and fail with
`skip_if_unavailable=0`, and `dnf5 repoquery --repo arctic` / `--repo arctic-testing` against the
site served over HTTP lists exactly its packages (gpgcheck and repo_gpgcheck off for that
unsigned test repository only). `tools/test-repo.sh --signed` against such an unsigned site
fails, as it must ("GPG verification is enabled, but GPG signature is not available"; with only
`repo_gpgcheck` off: "The package is not signed"); it passes only on a site signed with the key
arctic-release carries, i.e. in repo.yml.

**A new Fedora release** (F45): the site keeps one tree per release,
`repo/<channel>/fedora-<releasever>/`, and arctic-release's `baseurl` uses `$releasever`, so each
system reads its own. Build with `dist_version` 45 (and `ARCTIC_FEDORA_IMAGE` set to the F45
image) and publish: the builds land in `fedora-45` next to `fedora-44`, which keeps its last
builds. Publish fedora-45 before F44 systems upgrade (`dnf system-upgrade` then finds Arctic's F45
packages); fedora-44 gets no new builds once main moves on. The landing page's "Fedora 44" text
(`tools/lib/arcticrepo.py`) and the size budget (two trees) need a look then.
## 10. Theming (theme engine, palettes, `arctic-theme`)

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

## 11. Web apps (`arctic-webapps`)

Any website as an app with its own launcher entry, icon, window, Wayland app_id and signed-in
profile (user guide: `docs/wiki/Web-Apps.md`). Everything is per user; nothing needs root.

**Pieces.** `/usr/bin/arctic-webapp` (the manager: pure Go, `CGO_ENABLED=0`, a PIE with no
DT_NEEDED; never loads GTK or WebKit) and `/usr/libexec/arctic/arctic-webapp-host` (one app's
window: Go + a hand-written C shim, cgo against WebKitGTK 6.0, GTK 4 and libsoup 3; only
`arctic-webapp run` starts it; `ARCTIC_WEBAPP_HOST` overrides the path for development). cgo
lives only in `internal/webkit/` and `cmd/arctic-webapp-host/`, and every file there starts
with `//go:build cgo && webkit` (a test enforces it), so `go test ./...` without WebKit headers
skips them and no stub host can be built. Every decision the window makes (scope, navigation,
permissions, downloads, crashes, theme) is pure Go in `internal/webapp/policy` and
`internal/webapp/theme`; the shim reports facts and applies answers. The host links with
`-z now`, so it never calls a WebKitGTK symbol newer than the version it is built against, and
the package Requires `webkitgtk6.0 >= <that version>`. A Chromium-family browser is the per-app
fallback engine for sites that need WebRTC calls or Widevine DRM, which Fedora's WebKitGTK lacks.

**Ids.** `org.arcticlinux.WebApp.<Slug>_<hash>`, grammar
`^org\.arcticlinux\.WebApp\.[A-Za-z][A-Za-z0-9]{0,31}_[0-9a-f]{6,8}$` (also a valid GApplication
id; no `-`). Slug: the name's ASCII letters and digits in CamelCase, else the site label, else
`App`. Hash: the first 6 hex digits of SHA-256 over the identity (the manifest `id`, else the
start URL without fragment; `#N` appended for copy N), 8 when another identity holds the 6-digit
id. The id is the GApplication id, the Wayland app_id, the `.desktop` basename, `StartupWMClass`
(WebKit engine), the D-Bus name and the first icon name. Reinstalling a site whose data was kept
reuses the kept id, so you stay signed in. Mango's `activation_bypass` rule for
`^org\.arcticlinux\.WebApp\.` (rules.conf; mangowm ≥ 0.17.3) lets a second start raise the
window.

**Files.**

| What | Path | Mode | Writer |
|---|---|---|---|
| Registry lock (flock; shared for readers, exclusive for writes, 5 s → `busy`) | `$XDG_DATA_HOME/arctic/webapps/.lock` | 0600 | manager |
| Record (schema 1) / kept record | `…/webapps/<id>/app.json` / `app.removed.json` | 0600 (dir 0700) | manager |
| Source icon (≤ 512 px PNG) | `…/webapps/<id>/icon.png` | 0600 | manager |
| Window state, permissions | `…/webapps/<id>/state.json`, `permissions.json` | 0600 | host |
| WebKit profile (cookies.sqlite, storage) | `…/webapps/<id>/profile/` | 0700 | WebKit |
| WebKit cache | `$XDG_CACHE_HOME/arctic/webapps/<id>/` | 0700 | WebKit |
| Browser profile | `…/webapps/<id>/chromium/` (dnf Chromium) or `~/.var/app/<ref>/data/arctic-webapps/<id>/` (Flatpak) | 0700 | browser |
| Launcher entry | `$XDG_DATA_HOME/applications/<id>.desktop` | 0644 | manager |
| Icons (48, 64, 128, 256, 512 px) | `$XDG_DATA_HOME/icons/hicolor/<n>x<n>/apps/<icon>.png`, `<icon>` = `<id>` then `<id>.r<N>` after each change | 0644 | manager |
| Log (1 MiB, one rotation, URLs without query) | `$XDG_STATE_HOME/arctic/webapps/<id>.log` | 0600 | host |
| Pid file (primary instance only), previews | `$XDG_RUNTIME_DIR/arctic-webapp/<id>.pid`, `inspect-<token>/` | 0700 dir | host / manager |

All writes are atomic (temp file, fsync, rename). `app.json` holds `schema, render,
engine_version, id, copy, name, name_source, input_url, start_url, manifest_url, manifest_id,
scope{site,scheme,manifest}, extra_domains, category, theme_color, icon{name,rev,source,url,sha256,purpose},
runtime (webkit | chromium:brave|chrome|vivaldi|chromium|ungoogled), wm_class, handlers ([] |
["mailto"]), options{links: browser|app, notifications: allow|ask|block, devtools, rendering:
auto|software}, tls_exceptions[{host,sha256,pem}] (private-network hosts only), user_set,
created, updated`. A record whose id doesn't match its directory, whose URLs aren't http(s), or
with an unknown value is refused.

**`.desktop` keys, in order:** `Type=Application`, `Version=1.5`, `Name`, `Comment=Web app · <host>`,
`Exec=arctic-webapp run <id>` (`… %u` only for a mail-link app), `TryExec=arctic-webapp`,
`Icon=<icon>`, `Terminal=false`, `StartupNotify=true`, `StartupWMClass`, `SingleMainWindow=true`,
`Categories=<Main>;X-Arctic-WebApp;` (Calendar → `Office;Calendar;X-Arctic-WebApp;`),
`Keywords=web;app;<host>;`, `MimeType=x-scheme-handler/mailto;` (mail-link apps only),
`X-Arctic-WebApp-Id`, `X-Arctic-WebApp-URL`, `X-Arctic-WebApp-Runtime`, `X-Arctic-WebApp-Schema=1`.
Never a URL in Exec, never `WebBrowser` or `NoDisplay`. `arctic-webapp render-sample DIR` writes
two fixture entries for `desktop-file-validate` in `%check`.

**CLI.** `arctic-webapp inspect URL | install (URL | --preview TOKEN) [options] | list [--sizes]
[--kept] | show ID | run ID [URI] [--url URL] | launch ID [--url URL] | update (ID… | --all) |
set ID [options] | clear-data ID | remove ID… [--keep-data] | forget ID… | icon ID --from-file F
--source host-favicon | trust-certificate ID --host H --pem F | repair | runtimes | serve |
render-sample DIR | version [--webkit]`. Exit 0 ok, 1 error, 2 usage; messages on stderr start
`arctic-webapp: `. It refuses to run as root (CI containers set `ARCTIC_WEBAPP_ALLOW_ROOT=1`).
With `--json`: exactly one line on stdout, `{"ok":true,…}` or
`{"ok":false,"code":"<code>","error":"<sentence>"[,"fields":{…}]}` (`fields` only with code
`invalid`), nothing on stderr and no progress lines. Success shapes: `inspect` `{"preview":…}`,
`install` `{"app","desktop_file","launched"}`, `list` `{"apps":[…],"kept":[…]}` (`kept` with
`--kept`), `show` `{"app"}`, `launch` `{"pid"}` or `{"focused":true}`, `update`
`{"updated":[{"id","changed","kept"}]}`, `set` `{"app","applied": live|next_start|saved}`,
`remove` `{"removed":[{"id","stopped","kept_data"}]}`, `repair` `{"repaired","orphans_removed"}`,
`runtimes` `{"runtimes"}`, `version` `{"version","host","host_present"[,"webkit_version"]}`,
`clear-data`/`forget` `{}`. App info: `id, name, url, host, icon_name, icon_path (128 px),
category, runtime, runtime_available, running, links, notifications, devtools, rendering,
extra_domains, handlers, handlers_supported, tls_exceptions[{host,sha256}], data_bytes (null
without --sizes), problem ("" | no-desktop-file | no-registry | runtime-missing), created, updated`.

**`serve`** (the shell's Get apps and Remove apps pages): JSON lines on stdin/stdout in the §4
envelope, snake_case. Methods `Hello` (`engine_version, protocol_version, runtimes[{id, name,
available, drm, webrtc, install?{module, method, ref?}}]`), `Runtimes`, `Inspect{url}` (a new
one cancels the previous), `Install{token | url, name, icon (index | "monogram"), icon_file,
icon_url, category, runtime, links, notifications, mail_links, new_copy, launch}`,
`List{sizes, kept}`, `Get{id, sizes}`, `Launch{id, url}`, `Update{ids, all}`, `Set{id, name,
icon{file | monogram | url | {} = from the site}, category, runtime, links, extra_domains,
add_domain, remove_domain, notifications, mail_links, devtools, rendering, reset_permissions,
forget_certificate}`, `Remove{ids, keep_data}`, `Forget{ids}`, `ClearData{id}`,
`Cancel{request}`. Events: `{"event":"progress","request","stage": page|manifest|icons|render,
"message"}` and `{"event":"changed","ids"}` (after the response to a write). Error codes:
`invalid` (with `fields`), `bad_request`, `unknown_method`, `not_found`, `state`, `offline`,
`timeout`, `internal`, `exists`, `fetch`, `http`, `tls`, `too_large`, `not_html`, `busy`,
`unsupported`. `serve` exits on end of input and deletes its previews. The Inspect result
(`preview`): `token, url, final_url, host, host_ascii, secure, name, name_source, short_name,
start_url, scope, manifest_url, display, theme_color, category, suggested_id, installed,
icons[{index, source, purpose, size, format, path}], recommended_icon, handlers_supported,
warnings[{code: drm_unsupported|calls_unsupported|login_wall|insecure, message}],
suggested_runtime`; its token stays installable for an hour.

**Discovery rules.** http(s) only; https is added when there is no scheme; no userinfo, no
control characters, ≤ 2,048 bytes. Fetch: dial and TLS 5 s, headers 10 s, 30 s per inspect,
TLS ≥ 1.2 and never an unverified certificate, ≤ 5 redirects and never https → http, HTML read
to 1 MiB, manifest 256 KiB, images 2 MiB (≤ 4096 px, checked before decoding), 8 MiB in all. The
user agent is WebKitGTK's own (pinned by the host's smoke test). Once the page came from a public
address, its manifest and icons may not come from loopback, private or link-local addresses
(checked at connect time). The page's JavaScript never runs. If the page redirected to another
site (a sign-in wall), that page's name and icons are ignored and the typed origin is probed.
Scope = the start URL's registrable domain from Fedora's Public Suffix List (exact host:port for
IP addresses and localhost) plus extra domains. Icons: never `og:image`, never third-party
favicon services; WebP/AVIF/JXL are skipped; SVG goes through `rsvg-convert` (stdin, argv, 5 s)
and is never installed; letter icons use the app-tile tints (never amber).

**Window rules.** Only user link clicks (and gesture-driven "other" navigations) to pages out of
scope leave the app, for your default browser (`x-scheme-handler/https`); redirects, script
navigations and form posts stay, so single sign-on works. `window.open` makes a popup in the
same session with `window.opener` kept (OAuth). Permissions: stored per origin; notifications
follow the app's option (allowed for in-scope origins by default); camera, microphone, screen,
location, clipboard ask in a banner outside the page; EME is denied. Downloads go to the XDG
download directory under a safe unique name. A web-process crash reloads once a minute, then
shows a banner. `SIGHUP` re-reads app.json (links, extra domains, notifications, devtools,
certificates); `SIGTERM` quits after saving state. `run` removes
`WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS` from the environment, adds the NVIDIA workarounds on
the proprietary driver and software rendering on request. Chromium-family runtimes run
`--app=<url> --user-data-dir=<per-app>` (never `--no-sandbox` or `--class`); a running one is
focused with `mmsg` instead of opening a second window.
