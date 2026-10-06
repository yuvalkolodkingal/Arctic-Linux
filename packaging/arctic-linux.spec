# Arctic Linux: every Arctic package from one spec and one source tarball (docs/BUILD-SPEC.md §2).
#
# Source0 is `git archive --prefix=arctic-linux-%%{version}/` of the repository (made by
# tools/build-rpms.sh, which also includes uncommitted work). The subpackages install straight
# from the repository tree:
#
#   arctic-release         packaging/release/                  os-release, macros.dist, presets,
#                                                              the Arctic repositories + key
#   arctic-logos           branding/logos/ (install-path tree) system-logos
#   arctic-backgrounds     design/wallpapers/*.svg (+ PNG rendered here)
#   arctic-fonts           branding/fonts/Figtree-*.ttf (else design/fonts/Figtree-*.woff2)
#   arctic-fonts-symbols   Nerd Fonts "Symbols Only" (Source1, the one download) + packaging/fonts
#   arctic-selinux         packaging/selinux/arctic-nix.{te,fc} (compiled here)
#   arctic-desktop-config  dotfiles/ → /etc/skel (Mango config, themes → /usr/share/arctic),
#                          dotfiles/.local/bin → /usr/bin, packaging/updates/ (automatic updates,
#                          snapper snapshots around dnf transactions), design/themegen →
#                          /usr/share/arctic/themegen (the theme engine; Winter and Polar night are rendered with it here),
#                          packaging/theme-hooks.d → /usr/share/arctic, packaging/dconf, packaging/flatpak
#                          (app theming defaults)
#   arctic-shell           shell/ → /usr/share/arctic/shell
#   arctic-settings        settings/ → /usr/share/arctic/settings, arctic-settings, packaging/settings/
#   arctic-installer       cmd/ + internal/ (Go), modules/, profiles/, installer-ui/, packaging/systemd/
#   arctic-webapps         cmd/arctic-webapp (Go) + cmd/arctic-webapp-host (Go + cgo: WebKitGTK 6.0, GTK 4),
#                          internal/webapp/, internal/webkit/
#   sddm-wayland-mango     packaging/sddm-wayland-mango/
#   arctic-sddm-theme      branding/sddm/arctic/
#   arctic-plymouth-theme  branding/plymouth/arctic/ (+ branding/plymouth/dracut/, the initrd hook)
#   arctic-grub-theme      branding/grub/arctic/
#   arctic-live            live/
#   arctic-desktop         (metapackage)

%global dist_version    44
%global arctic_version  1.2
%global selinuxtype     targeted
# Pure Go commands omit native symbol/debug tables; Go runtime stack metadata and
# the GNU build ID remain. The cgo host keeps Fedora's external-link flags below.
%global debug_package   %{nil}
# ---- stream 1 (web apps): arctic-webapp-host is cgo, linked externally with Fedora's flags;
# brp-strip strips it too. Its WebKitGTK floor is the version it was built against (it links
# with -z now, so a newer symbol would stop it starting on an older WebKitGTK;
# docs/BUILD-SPEC.md §11). The fallback keeps rpmspec -q and dnf builddep working before the
# -devel package is installed.
%global webkit_built    %(pkg-config --modversion webkitgtk-6.0 2>/dev/null || echo 2.50)
# --- stream 6: Nerd Font symbols (arctic-fonts-symbols). Fedora has no symbols-only Nerd Font,
# so the upstream release is Source1, pinned by version and SHA-256 (checked in %%prep);
# tools/build-rpms.sh downloads it next to the Mango tarball.
%global nerd_version    3.5.1
%global nerd_sha256     01172f37db8543edb102e5cb5c64101c9f4686630804d49b419aa07b23a69996
# --- end stream 6

Name:           arctic-linux
Version:        1.2.0
# tools/build-rpms.sh defines arctic_snapshot as .<UTC commit time>.<UTC build time>.git<commit>,
# so builds of newer commits are newer packages (docs/BUILD-SPEC.md §9).
Release:        1%{?arctic_snapshot}%{?dist}
Summary:        Arctic Linux: a Fedora-based desktop with the Mango window manager
# ISC covers the vendored 3D greeting (fetch/, a fork of areofyl/fetch). Its text is fetch/LICENSE
# in the source package and fetch/README.md names it; TODO: ship it as a %license in
# arctic-desktop-config too (it needs renaming, as %license flattens and would collide with
# the project's own LICENSE above).
License:        MIT AND LGPL-2.1-or-later AND OFL-1.1 AND ISC
URL:            https://github.com/yuvalkolodkingal/Arctic-Linux
Source0:        arctic-linux-%{version}.tar.gz
# --- stream 6
Source1:        https://github.com/ryanoasis/nerd-fonts/releases/download/v%{nerd_version}/NerdFontsSymbolsOnly.tar.xz#/NerdFontsSymbolsOnly-%{nerd_version}.tar.xz
# --- end stream 6

ExclusiveArch:  x86_64

BuildRequires:  golang >= 1.22
BuildRequires:  librsvg2-tools
BuildRequires:  selinux-policy-devel
BuildRequires:  make
BuildRequires:  systemd-rpm-macros
BuildRequires:  desktop-file-utils
BuildRequires:  findutils
BuildRequires:  tar
# --- stream 6: Source1 is a .tar.xz
BuildRequires:  xz
# --- end stream 6
# %%check: packaging/updates' unit tests (arctic-update's helper)
BuildRequires:  python3
# The theme engine renders the static themes in %%build; %%check runs its tests.
# %%py_byte_compile
BuildRequires:  python3-rpm-macros
BuildRequires:  python3-pillow
# ---- stream 1 (web apps): arctic-webapp-host (cgo): the C compiler, WebKitGTK 6.0, GTK 4,
# libsoup 3; readelf in %%check
BuildRequires:  gcc
# The 3D greeting (fetch/) includes <math.h> and links -lm: both need glibc-devel, which used to
# arrive only transitively through pkgconfig(webkitgtk-6.0). Ask for it: the C build must not
# depend on an unrelated subpackage's dependency chain.
BuildRequires:  glibc-devel
BuildRequires:  binutils
BuildRequires:  pkgconfig(webkitgtk-6.0)
BuildRequires:  pkgconfig(gtk4)
BuildRequires:  pkgconfig(libsoup-3.0)

%description
Arctic Linux is a Fedora %{dist_version} based desktop built around the Mango Wayland
compositor, a Quickshell desktop shell, SDDM and a step-by-step installer.
This source package builds all Arctic Linux subpackages.

# ---------------------------------------------------------------------------------------------
%package -n arctic-release
Summary:        Arctic Linux release files
BuildArch:      noarch
Provides:       system-release
Provides:       system-release(%{dist_version})
Provides:       system-release(releasever) = %{dist_version}
Provides:       base-module(platform:f%{dist_version})
Provides:       arctic-release(%{arctic_version})
Conflicts:      system-release
Conflicts:      fedora-release
Conflicts:      fedora-release-common
Conflicts:      fedora-release-identity
Conflicts:      generic-release
Conflicts:      generic-release-common
Requires:       fedora-repos(%{dist_version})

%description -n arctic-release
Release files that identify the system as Arctic Linux %{arctic_version} on a Fedora
%{dist_version} base: os-release, the rpm dist macros, /etc/issue, the systemd presets
(Fedora's policy plus Arctic's: SDDM, the installer socket, nix-daemon, no SSH
server) and dnf defaults. It replaces fedora-release; Fedora's repositories
(fedora-repos) stay in use. It adds the signed Arctic package repository (the
stable channel on, the testing channel off) and the key its packages are signed
with.

# ---------------------------------------------------------------------------------------------
%package -n arctic-logos
Summary:        Arctic Linux logos and icons
BuildArch:      noarch
Provides:       system-logos = %{version}-%{release}
Provides:       system-logos(%{version})
Conflicts:      system-logos
Conflicts:      fedora-logos
Conflicts:      generic-logos
# Directory owners.
Requires:       hicolor-icon-theme

%description -n arctic-logos
The Arctic Linux fox mark and lockups under the names Fedora's system-logos packages use
(/usr/share/pixmaps/system-logo-white.png for SDDM and Plymouth, fedora-logo*.png, the
hicolor arctic-logo-icon / fedora-logo-icon / start-here icons) and the brand SVGs in
/usr/share/arctic/logos.

# ---------------------------------------------------------------------------------------------
%package -n arctic-backgrounds
Summary:        Arctic Linux wallpapers
BuildArch:      noarch
# SDDM requires desktop-backgrounds-compat for /usr/share/backgrounds/default.*; Arctic's
# default wallpaper takes its place (and keeps Fedora's 10 MB f44-backgrounds out).
Provides:       desktop-backgrounds-compat = %{version}-%{release}
Conflicts:      desktop-backgrounds-compat

%description -n arctic-backgrounds
The six Arctic Linux wallpapers (snowfield, aurora and fox, each in Winter and Polar night)
as SVG and as 3840×2160 PNG in /usr/share/backgrounds/arctic, plus the
/usr/share/backgrounds/default{,-dark}.png names other programs look for.

# ---------------------------------------------------------------------------------------------
%package -n arctic-fonts
Summary:        Figtree, the Arctic Linux interface typeface
BuildArch:      noarch
License:        OFL-1.1
Requires:       fontpackages-filesystem

%description -n arctic-fonts
Figtree (SIL Open Font License), the interface typeface of Arctic Linux, installed system
wide. JetBrains Mono comes from Fedora's jetbrains-mono-fonts-all.

# --- stream 6 (Nerd Font symbols) -------------------------------------------------------------
%package -n arctic-fonts-symbols
Summary:        Nerd Font symbols for the terminal (icons in yazi, eza and prompts)
BuildArch:      noarch
# The release's LICENSE (MIT, the patcher) and its readme's table of icon sets: Codicons and Font
# Awesome CC-BY-4.0, Material Design Apache-2.0, Pomicons OFL-1.1-RFN, Weather Icons OFL-1.1,
# Font Logos Unlicense, the rest MIT.
License:        MIT AND CC-BY-4.0 AND Apache-2.0 AND OFL-1.1-RFN AND OFL-1.1 AND Unlicense
Requires:       fontpackages-filesystem
Requires:       fontconfig

%description -n arctic-fonts-symbols
The "Symbols Only" fonts of Nerd Fonts %{nerd_version} (Symbols Nerd Font and Symbols Nerd Font
Mono), set up as a fallback after the code font, so file managers like yazi, eza --icons and
shell prompts show their icons in any terminal without a patched font.
# --- end stream 6

# ---------------------------------------------------------------------------------------------
%package -n arctic-selinux
Summary:        SELinux file contexts for Nix on Arctic Linux
BuildArch:      noarch
License:        LGPL-2.1-or-later
Requires:       selinux-policy-%{selinuxtype}
Requires(post): selinux-policy-%{selinuxtype}
Requires(post): policycoreutils
# %%pre / %%post compare the module with the installed one (cp, cmp).
Requires(pre):  coreutils
Requires(post): coreutils
Requires(post): diffutils
Requires(postun): policycoreutils
%{?selinux_requires}

%description -n arctic-selinux
The arctic-nix policy module: SELinux labels for the Nix store (/nix/store/*/bin → bin_t,
lib, share, man, etc) and the Nix daemon socket (var_run_t, Fedora bug 2525943), based on
the NixOS nix-installer policy.

# ---------------------------------------------------------------------------------------------
%package -n arctic-desktop-config
Summary:        Arctic Linux desktop configuration and helper commands
BuildArch:      noarch
Requires:       mangowm >= 0.17.3
Requires:       arctic-backgrounds = %{version}-%{release}
Requires:       arctic-fonts = %{version}-%{release}
Requires:       arctic-logos = %{version}-%{release}
Requires:       bash
Requires:       python3
# arctic-themegen: colours from wallpapers
Requires:       python3-pillow
# The unprivileged, D-Bus-activated shared login wallpaper publisher.
Requires:       python3-dbus
Requires:       python3-gobject-base
Requires:       polkit
%{?systemd_requires}
# kitty and fish are the default terminal and shell, but the installer lets people pick others
# and removes the unticked ones (dnf remove --no-autoremove), so they must be weak deps.
Recommends:     fish
Recommends:     kitty
Requires:       libnotify
Requires:       procps-ng
Requires:       util-linux
Requires:       librsvg2-tools
# Stream 3b (notifications): the Arctic shell is its own notification server; mako is the
# waybar session's daemon (and the shell's fallback), so it is a weak dependency now.
Recommends:     mako
Requires:       swaybg
Requires:       swayidle
Requires:       swaylock
Requires:       grim
Requires:       slurp
Requires:       wl-clipboard
Requires:       cliphist
Requires:       brightnessctl
Requires:       playerctl
# fastfetch draws `fastfetch` (the themes' fastfetch/config.jsonc), `neofetch` and the info
# column of the arctic-fetch greeting.
Requires:       fastfetch
# Fedora 44 has no neofetch: `neofetch` here is fastfetch with the neofetch layout. Its
# /usr/bin/neofetch is a %%ghost link made in %%posttrans only while nothing else is there, so a
# real neofetch package installs over it without a file conflict (docs/BUILD-SPEC.md §2).
Provides:       neofetch = %{version}-%{release}
# The 3D greeting is compiled, so it lives in its own arch package: this one stays noarch.
Requires:       arctic-fetch-3d = %{version}-%{release}
Requires:       jetbrains-mono-fonts-all
# App theming (docs/BUILD-SPEC.md "App theming"): GTK 3 apps use adw-gtk3, which takes the
# theme's colours from ~/.config/gtk-3.0/gtk.css; Qt 5/6 apps use qt5ct/qt6ct (Fusion + the
# theme's palette); the dconf defaults name Adwaita icons and cursors.
Requires:       adw-gtk3-theme
Requires:       qt6ct
Requires:       qt5ct
Requires:       adwaita-icon-theme
Requires:       adwaita-cursor-theme
Requires:       dconf
# /var/lib/flatpak/overrides/global (Flatpak apps read the GTK colours).
Requires:       flatpak
Requires(posttrans): dconf
Requires(postun): dconf
Recommends:     waybar
Recommends:     fuzzel
Recommends:     lxqt-policykit
Recommends:     network-manager-applet
# arctic-update: offline updates (dnf5 upgrade --offline, dnf5-offline-transaction.service),
# channels (dnf5 config-manager, in dnf5-plugins), snapshots around every dnf transaction
# (the actions plugin runs snapper), the metered check (nmcli, when NetworkManager is there).
Requires:       dnf5
Requires:       dnf5-plugins
Requires:       libdnf5-plugin-actions
Requires:       snapper
Requires:       btrfs-progs
Requires:       findutils
# Stream 4 (shortcuts and capture): gio and gdbus for the screenshot notification's buttons
# (open, show in Files, move to the trash); swappy edits screenshots (satty isn't in Fedora;
# swappy's weak deps bring its icon font); wf-recorder records the screen (arctic-record);
# tesseract (its data package brings English) and zxing-cpp read text and QR codes (arctic-ocr).
Requires:       glib2
Recommends:     swappy
Recommends:     wf-recorder
Recommends:     tesseract
Recommends:     python3-zxing-cpp
# Stream 5 (system): night light (arctic-nightlight runs wlsunset; tzdata's zone1970.tab gives
# the time zone's location), keep awake (arctic-keep-awake, through arctic-session's swayidle).
Requires:       wlsunset
Requires:       tzdata
# Removable drives: udiskie mounts them with a notification (arctic-session drives);
# arctic-drives lists and ejects them (lsblk, udisksctl).
Requires:       udiskie
Requires:       udisks2
# Screens and the lid: arctic-display (wlr-randr, Mango's mmsg; Duplicate needs wl-mirror),
# arctic-session lid (systemd-inhibit); lighter effects and game mode: arctic-effects.
Requires:       wlr-randr
Recommends:     wl-mirror
# Apps that keep the screen on through org.freedesktop.ScreenSaver: arctic-screensaver.
Requires:       python3-dbus
Requires:       python3-gobject-base

%description -n arctic-desktop-config
The Arctic Linux desktop configuration: the Mango configuration, the Winter and Polar night
theme files and the keyboard cheat sheet in /usr/share/arctic (new home directories link to
them, so updates reach everyone), the home directory defaults in /etc/skel (kitty, fish, zsh, GTK,
waybar, fuzzel, mako), the arctic-* helper commands in /usr/bin and /etc/arctic/default-apps.
Automatic updates: arctic-update-stage.timer downloads updates daily and
schedules them to be installed at the next restart (dnf5 offline updates);
arctic-update shows and changes that (/etc/arctic/update.conf). Snapper takes
a snapshot before and after every dnf transaction once the installer has set
it up for the root file system (arctic-snapper.actions, libdnf5 actions).

It also has the theme engine (arctic-themegen, /usr/share/arctic/themegen), which makes a
theme from the wallpaper when colours follow it (arctic-theme auto on), and the theme hooks
in /usr/share/arctic/theme-hooks.d (GTK, Qt, Zed, Zen). App theming: the GTK, icon, cursor
and font defaults for GTK/libadwaita and Flatpak apps (dconf distro database) and the Flatpak
overrides that let Flatpak apps read the GTK colours.

# --- stream 6 (theme gallery) ------------------------------------------------------------------
%package -n arctic-themes-extra
Summary:        More themes for Arctic Linux: Nord, Catppuccin, Gruvbox, Tokyo Night, Rosé Pine, Everforest
BuildArch:      noarch
Requires:       arctic-desktop-config = %{version}-%{release}

%description -n arctic-themes-extra
Optional themes for Arctic Linux, made from the colours of Nord, Catppuccin, Gruvbox, Tokyo
Night, Rosé Pine and Everforest by Arctic's theme engine: the same roles and contrast
guarantees as Winter and Polar night, with the amber "here" accent kept. Pick one in
Settings > Appearance or with arctic-theme set NAME.
# --- end stream 6

# ---------------------------------------------------------------------------------------------
%package -n arctic-shell
Summary:        Arctic Linux desktop shell (Quickshell)
BuildArch:      noarch
Requires:       quickshell
Requires:       qt6-qtdeclarative
Requires:       qt6-qtsvg
Requires:       qt6-qtwayland
Requires:       python3
Requires:       python3-pillow
Requires:       python3-pyte
# ---- stream 2 (Get apps): Fedora's app catalogue, for app names, summaries and icons on the
# Fedora packages page (without it the page lists every package by name)
Recommends:     appstream-data
# ---- end stream 2
# pkexec, for Get apps
Requires:       polkit
# Stream 3b (notifications): gdbus checks who owns org.freedesktop.Notifications.
Requires:       glib2
Requires:       arctic-fonts = %{version}-%{release}
# Stream 4 (input): the emoji picker lists unicode-emoji's emoji in the colour emoji font and
# types them with wtype (the clipboard panel's paste uses it too); without wtype they're copied.
Requires:       unicode-emoji
Requires:       google-noto-color-emoji-fonts
Recommends:     wtype
# Get apps → Web apps and Remove apps → Web apps (stream 1); hidden when it is missing
Recommends:     arctic-webapps = %{version}-%{release}
# Stream 3a (bar menus): the Bluetooth pairing agent and battery.py talk D-Bus with
# python3-dbus and a GLib main loop; gdbus (glib2, above) checks for the power-profiles
# service; audio.py reads ports and profiles with pw-dump and pw-cli; ddcutil sets external
# monitors' brightness. (The network menu hides itself without nmcli.)
Requires:       python3-dbus
Requires:       python3-gobject-base
Requires:       pipewire-utils
Recommends:     ddcutil
# Sharing a Wi-Fi network as a QR code; importing OpenVPN files (Settings → Network)
Recommends:     qrencode
# NetworkManager-openvpn is installer opt-in or installed explicitly from Settings.
# --- stream 6 (launcher, command menu): the launcher finds files with fd and converts units
# with qalc when they are installed.
Recommends:     fd-find
Recommends:     qalculate
# The keyboard pointer (Super + Alt + K, arctic-kbptr).
Recommends:     wl-kbptr
# The theme gallery in Settings > Appearance.
Recommends:     arctic-themes-extra = %{version}-%{release}
# Icons in the terminal (yazi, eza --icons, prompts).
Recommends:     arctic-fonts-symbols = %{version}-%{release}
# --- end stream 6

%description -n arctic-shell
The Arctic Linux desktop shell, written for Quickshell: top bar with its own menus (network
and Wi-Fi, Bluetooth with a pairing agent, sound, battery and power mode, calendar, media,
tray menus) and Quick Settings, launcher with Get apps (Flathub, Fedora packages, web apps,
terminal apps, a console) and Remove apps, wallpaper picker, on-screen display, lock screen,
the live-session welcome card, and the notification server with its pop-ups and notification
centre.
Start it with arctic-shell; arctic-shell-ipc calls into a running shell.

# ---------------------------------------------------------------------------------------------
%package -n arctic-settings
Summary:        Arctic Settings, the settings app of Arctic Linux
BuildArch:      noarch
Requires:       quickshell
Requires:       qt6-qtdeclarative
Requires:       qt6-qtsvg
Requires:       qt6-qtwayland
Requires:       python3
Requires:       hicolor-icon-theme
# gdbus (power modes over D-Bus) and gsettings (GTK text size, pointer)
Requires:       glib2
# arctic-theme, arctic-motion, arctic-wallpaper, arctic-session, arctic-open; the wallpaper list
Requires:       arctic-desktop-config = %{version}-%{release}
Requires:       arctic-shell = %{version}-%{release}
Requires:       arctic-fonts = %{version}-%{release}
# Displays: list modes and try a layout (wlr-output-management)
Requires:       wlr-randr
# The tools the Network, Bluetooth and Sound pages open (arctic-desktop pulls them in too)
Recommends:     nm-connection-editor
Recommends:     blueman
Recommends:     pavucontrol
Recommends:     xdg-utils

%description -n arctic-settings
Arctic Settings: appearance and themes, windows (Mango gaps, borders, animations, focus,
layout), displays, keyboard and mouse, shortcuts, default apps, network, Bluetooth, sound,
updates, power and lock, startup apps, printers and scanners, date and time. Changes go to
~/.config/mango/settings.conf and the Arctic helpers; only the time zone, the clock and the
language ask for the password (systemd, polkit). Start it with arctic-settings (Super+S).

# ---------------------------------------------------------------------------------------------
%package -n arctic-installer
Summary:        Arctic Linux installer: engine (arcticd), CLI, app catalog and wizard UI
Requires:       quickshell
Requires:       qt6-qtdeclarative
Requires:       qt6-qtsvg
Requires:       arctic-fonts = %{version}-%{release}
Requires:       arctic-desktop-config = %{version}-%{release}
# What the engine runs (docs/BUILD-SPEC.md §6).
Requires:       util-linux
Requires:       gdisk
Requires:       parted
Requires:       cryptsetup
Requires:       btrfs-progs
Requires:       dosfstools
Requires:       e2fsprogs
Requires:       rsync
Requires:       efibootmgr
Requires:       grub2-tools
Requires:       dracut
Requires:       systemd-udev
Requires:       shadow-utils
Requires:       policycoreutils
Requires:       openssl
Requires:       NetworkManager
Requires:       flatpak
Requires:       dnf5
# Drivers: device names for the Apps step (pci.ids), grubby for their kernel arguments and
# mokutil to queue the akmods key for enrolment when Secure Boot is on. The installed system
# is a copy of the live image, so mokutil stays for arctic-firstboot when this package goes.
Requires:       hwdata
Requires:       grubby
Requires:       mokutil
%{?systemd_requires}

%description -n arctic-installer
The Arctic Linux installer. arcticd is the engine (root, socket-activated on
/run/arcticd.sock for the wheel group); arctic-install is its command-line client
(dry-run, unattended installs, and the JSON bridge the UI uses); arctic-installer starts
the 12-step wizard, written for Quickshell. The app catalog and install profiles are in
/usr/share/arctic.

# ---------------------------------------------------------------------------------------------
# ---- stream 1 (web apps)
%package -n arctic-webapps
Summary:        Arctic Linux web apps: any website as an app with its own window and icon
# libwebkitgtk-6.0.so.4 and libgtk-4.so.1 come from the automatic soname Requires. WebKitGTK has
# no symbol versions and the host is linked with -z now, so the floor is the version it was
# built against (docs/BUILD-SPEC.md §11).
Requires:       webkitgtk6.0%{?_isa} >= %{webkit_built}
# WebKit plays through GStreamer. The bad-free package carries the modern VA-API and
# NVDEC decoder plugins; a GPU driver alone doesn't make them available. Keep demuxers
# and streaming sources installed too, even with weak dependencies disabled.
Requires:       gstreamer1-plugins-bad-free%{?_isa}
Requires:       gstreamer1-plugins-good%{?_isa}
# A working WebRTC engine for WhatsApp, Meet and other calling sites. Get apps selects it
# automatically for these sites, without replacing the user's default browser.
Requires:       chromium%{?_isa}
# SVG icons and letter icons → PNG
Requires:       librsvg2-tools
# ~/.local/share/icons/hicolor is found through hicolor's index.theme
Requires:       hicolor-icon-theme
# A web app's scope uses registrable domains from the Public Suffix List
Requires:       publicsuffix-list
Recommends:     arctic-desktop-config = %{version}-%{release}
Recommends:     arctic-fonts = %{version}-%{release}

%description -n arctic-webapps
Any website as an app: its own window, icon, launcher entry and sign-in, separate from your
browser. arctic-webapp adds, lists, changes and removes web apps (the launcher's Get apps and
Remove apps use it, and nothing needs a password); each app window is arctic-webapp-host, built
on WebKitGTK. Sites that need protected media or video calls can open in a Chromium-family
browser instead.

# ---------------------------------------------------------------------------------------------
%package -n arctic-fetch-3d
Summary:        Arctic Linux 3D terminal greeting (arctic-fetch)
License:        ISC
Recommends:     arctic-desktop-config = %{version}-%{release}

%description -n arctic-fetch-3d
arctic-fetch-3d, the spinning 3D fox greeting built from fetch.c (a fork of areofyl/fetch).
The arctic-fetch wrapper in arctic-desktop-config runs it, and falls back to the text fox
where it isn't installed.

# ---------------------------------------------------------------------------------------------
%package -n sddm-wayland-mango
Summary:        SDDM greeter on the Mango Wayland compositor
BuildArch:      noarch
Provides:       sddm-greeter-displayserver
Conflicts:      sddm-greeter-displayserver
Requires:       sddm
Requires:       mangowm >= 0.17.3
Requires:       layer-shell-qt
Requires:       qt6-qtwayland
Requires:       adwaita-cursor-theme
Requires:       arctic-sddm-theme = %{version}-%{release}

%description -n sddm-wayland-mango
Configuration for SDDM to run its Qt 6 greeter on Mango (as layer-shell surfaces), with a
minimal compositor configuration: no key bindings, no autostart, the arctic theme.

# ---------------------------------------------------------------------------------------------
%package -n arctic-sddm-theme
Summary:        Arctic Linux login screen theme for SDDM
BuildArch:      noarch
Requires:       sddm
Requires:       qt6-qtdeclarative
Requires:       qt6-qtsvg
Recommends:     qt6-qt5compat
Requires:       arctic-backgrounds = %{version}-%{release}

%description -n arctic-sddm-theme
The Arctic Linux SDDM theme (Qt 6 QML): the frosted login card over the Polar night
wallpaper, with user, password, session, keyboard and power controls.

# ---------------------------------------------------------------------------------------------
%package -n arctic-plymouth-theme
Summary:        Arctic Linux boot splash (Plymouth)
BuildArch:      noarch
Requires:       plymouth-plugin-script
Requires(post): plymouth-scripts

%description -n arctic-plymouth-theme
The Arctic Linux boot splash: the fox mark breathing over the Polar night ground with three
amber dots, and the disk passphrase prompt; with arctic.reduce_motion=1 on the kernel command
line (a dracut module in the initramfs tells the splash) the mark and dots stay still.
Installing it makes it the default theme (the initramfs is not rebuilt here).

# ---------------------------------------------------------------------------------------------
%package -n arctic-grub-theme
Summary:        Arctic Linux GRUB theme
BuildArch:      noarch
Requires:       grub2-common

%description -n arctic-grub-theme
The Arctic Linux GRUB theme, used by the live USB boot menu and the installed system
(GRUB_THEME=/boot/grub2/themes/arctic/theme.txt).

# ---------------------------------------------------------------------------------------------
%package -n arctic-live
Summary:        Arctic Linux live USB session
BuildArch:      noarch
Requires:       livesys-scripts
Requires:       arctic-desktop-config = %{version}-%{release}
Requires:       sudo
Recommends:     arctic-installer = %{version}-%{release}

%description -n arctic-live
Live USB pieces: the livesys session "arctic" (SDDM autologin of liveuser into Mango,
no screen lock, passwordless sudo), and the live-session launcher that opens the installer
full screen when the boot menu's "Install Arctic Linux" entry was chosen, and the helper
that applies the installer's keyboard layout to the live session.
Only for the live image; the installer removes it from installed systems.

# ---------------------------------------------------------------------------------------------
%package -n arctic-desktop
Summary:        Arctic Linux desktop (metapackage)
BuildArch:      noarch
Requires:       arctic-release = %{version}-%{release}
Requires:       arctic-logos = %{version}-%{release}
Requires:       arctic-backgrounds = %{version}-%{release}
Requires:       arctic-fonts = %{version}-%{release}
Requires:       arctic-selinux = %{version}-%{release}
Requires:       arctic-desktop-config = %{version}-%{release}
Requires:       arctic-shell = %{version}-%{release}
Requires:       arctic-settings = %{version}-%{release}
# Web apps (stream 1): Requires, so existing installs get it through arctic-update
Requires:       arctic-webapps = %{version}-%{release}
Requires:       sddm-wayland-mango = %{version}-%{release}
Requires:       arctic-sddm-theme = %{version}-%{release}
Requires:       arctic-plymouth-theme = %{version}-%{release}
Requires:       arctic-grub-theme = %{version}-%{release}
Requires:       mangowm >= 0.17.3
Requires:       sddm
# Swappable in the installer's app picker (terminal, shell, file manager, video): weak deps,
# so unticking one doesn't remove this metapackage.
Recommends:     kitty
Recommends:     kitty-shell-integration
Recommends:     fish
Recommends:     nautilus
Recommends:     vlc
Requires:       fastfetch
# Stream 3b (notifications): the Arctic shell is its own notification server; mako is the
# waybar session's daemon (and the shell's fallback), so it is a weak dependency now.
Recommends:     mako
Requires:       swaybg
Requires:       swayidle
Requires:       swaylock
Requires:       grim
Requires:       slurp
Requires:       wl-clipboard
Requires:       cliphist
Requires:       brightnessctl
Requires:       playerctl
Requires:       wireplumber
Requires:       pipewire-pulseaudio
# Stream 3a (bar menus): the shell draws the network, Bluetooth and sound menus and pairs with
# its own agent, so the applet, the Bluetooth manager and the mixer are weak dependencies (the
# waybar session and the menus' "Edit connections…" links still use them); BlueZ itself stays.
Recommends:     pavucontrol
Recommends:     network-manager-applet
Requires:       NetworkManager-wifi
Recommends:     blueman
Requires:       bluez
Requires:       xdg-desktop-portal-wlr
Requires:       xdg-desktop-portal-gtk
Requires:       xdg-user-dirs
Requires:       xdg-utils
Requires:       libnotify
Requires:       librsvg2-tools
Requires:       jetbrains-mono-fonts-all
Requires:       google-noto-sans-fonts
# Scripts the installer's language list (and the installed system) needs beyond Latin,
# Greek and Cyrillic: Hebrew, Arabic, Chinese/Japanese/Korean.
Requires:       google-noto-sans-hebrew-fonts
Requires:       google-noto-sans-arabic-vf-fonts
Requires:       google-noto-sans-cjk-vf-fonts
Requires:       polkit
Requires:       gnome-keyring
Requires:       gnome-keyring-pam
Requires:       qt6-qtwayland
Requires:       qt5-qtwayland
Requires:       xorg-x11-server-Xwayland
Requires:       fuzzel
Requires:       flatpak
Requires:       nix
Requires:       nix-daemon
Requires:       python3-pillow
Requires:       layer-shell-qt
Requires:       tuned-ppd
Requires:       mesa-dri-drivers
# Updates and rollback (arctic-update, snapper snapshots of the btrfs root).
Requires:       snapper
Requires:       libdnf5-plugin-actions
Requires:       btrfs-progs
Recommends:     waybar
Recommends:     lxqt-policykit
Recommends:     adwaita-cursor-theme
# Toolkit theming (also required by arctic-desktop-config): GTK 3 and Qt 5/6 apps.
Requires:       adw-gtk3-theme
Requires:       qt6ct
Requires:       qt5ct
# The terminal system monitor, themed like the rest (btop/arctic.theme).
Recommends:     btop
# Stream 5 (system): printing and scanning. Driverless printers (IPP Everywhere, AirPrint) over
# USB (ipp-usb) and the network (avahi + nss-mdns; cups-browsed stays out, CUPS and the print
# dialogs find network printers themselves); system-config-printer administers queues through
# cups-pk-helper (polkit); Settings > Printers and scanners. cups.socket/cups.path are enabled
# by preset. Scanners: sane-airscan (driverless eSCL/WSD) and Document Scanner.
Requires:       cups
Requires:       cups-filters
Requires:       ghostscript
Requires:       ipp-usb
Requires:       avahi
Requires:       nss-mdns
Requires:       cups-pk-helper
Requires:       system-config-printer
Recommends:     gutenprint-cups
Recommends:     sane-airscan
Recommends:     sane-backends-drivers-scanners
Recommends:     simple-scan
# Stream 5 (system): firmware updates (arctic-update firmware; also in @core).
Requires:       fwupd
# Stream 5 (system): SSH keys once per session (gcr-ssh-agent), the firewall Settings shows
# (firewalld, in @core too), system monitor (Ctrl+Shift+Esc falls back to btop).
Requires:       gcr
Requires:       firewalld
Recommends:     firewall-config
# Users and sign-in (AccountsService: name and picture; fprintd: fingerprints) and running an app
# on a laptop's discrete graphics chip (arctic-gpu → switcherooctl).
Requires:       accountsservice
Recommends:     fprintd
# The lock screen takes a saved fingerprint too (shell/pam/arctic-lock-fingerprint).
Recommends:     fprintd-pam
Requires:       switcheroo-control
# Stream 5 (system): phones (MTP, iPhone), cameras and network shares in Thunar (gvfs).
Recommends:     gvfs
Recommends:     gvfs-mtp
Recommends:     gvfs-afc
Recommends:     gvfs-gphoto2
Recommends:     gvfs-smb

%description -n arctic-desktop
Pulls in everything an Arctic Linux desktop needs: Mango, SDDM with the arctic theme and
the Mango greeter, the Quickshell shell, the desktop configuration, branding, audio,
networking, portals, Flatpak and Nix.

# =============================================================================================
%prep
%autosetup -n arctic-linux-%{version}
# --- stream 6: Source1 (Nerd Font symbols), only as the pinned release
echo "%{nerd_sha256}  %{SOURCE1}" | sha256sum -c --quiet -
mkdir -p _build/nerd-symbols
tar -xJf %{SOURCE1} -C _build/nerd-symbols
# --- end stream 6

%build
# ---- Go: arcticd + arctic-install (stdlib only, or vendored modules) ----
if [ -f go.mod ]; then
  export GOTOOLCHAIN=local CGO_ENABLED=0 GOPROXY=off GOFLAGS="-buildmode=pie -trimpath"
  if [ -d vendor ]; then GOFLAGS="$GOFLAGS -mod=vendor"; fi
  export GOFLAGS
  # The container wrapper supplies a builder/native-library-qualified cache.
  # Direct rpmbuild keeps its isolated default; no build cache enters the RPM.
  export GOCACHE="${ARCTIC_GOCACHE:-$PWD/_build/gocache}" GOPATH="$PWD/_build/gopath"
  mkdir -p _build/bin
  for cmd in arcticd arctic-install arctic-webapp; do
    go build -ldflags "-s -w -B gobuildid" -o "_build/bin/$cmd" "./cmd/$cmd"
  done
  # ---- stream 1 (web apps): the window (docs/BUILD-SPEC.md §11), cgo against WebKitGTK 6.0
  # and GTK 4. Go reads CGO_CFLAGS/CGO_LDFLAGS, not the CFLAGS/LDFLAGS rpm exports; -tags
  # webkit selects its files (without it the package has no Go files, so no stub can ship).
  CGO_ENABLED=1 CGO_CFLAGS="%{build_cflags}" CGO_LDFLAGS="%{build_ldflags}" \
    go build -tags webkit -ldflags "-B gobuildid -linkmode=external" \
      -o _build/bin/arctic-webapp-host ./cmd/arctic-webapp-host
else
  echo "error: go.mod is missing: the installer engine (cmd/, internal/) is not in the tree" >&2
  exit 1
fi

# ---- SELinux module ----
make -C packaging/selinux -f %{_datadir}/selinux/devel/Makefile arctic-nix.pp

# ---- Static themes: Winter and Polar night, rendered by the theme engine (design/themegen)
# from the design tokens. dotfiles/.config/arctic/themes holds the same files, for
# dotfiles/install.sh; %%check makes sure they match.
export PYTHONDONTWRITEBYTECODE=1
rm -rf _build/themes
for t in winter polar-night; do
  PYTHONPATH=design python3 -m themegen builtin "$t" \
    | PYTHONPATH=design python3 -m themegen render --palette - --out "_build/themes/$t" --quiet
done
# --- stream 6: the theme gallery (design/themes/*/colors.toml); `named` refuses a palette that
# can't meet the contrast guarantees, so a bad one fails the build.
rm -rf _build/themes-extra
for toml in design/themes/*/colors.toml; do
  t="$(basename "$(dirname "$toml")")"
  PYTHONPATH=design python3 -m themegen named --colors "$toml" --name "$t" \
    | PYTHONPATH=design python3 -m themegen render --palette - --out "_build/themes-extra/$t" --quiet
done
# --- end stream 6

# ---- Wallpapers: SVG → 3840×2160 PNG ----
mkdir -p _build/backgrounds
for svg in design/wallpapers/*.svg; do
  cp -p "$svg" _build/backgrounds/
  rsvg-convert -w 3840 -h 2160 -o "_build/backgrounds/$(basename "$svg" .svg).png" "$svg"
done

# ---- The 3D greeting: fetch.c (fetch/), a vendored fork of areofyl/fetch, built as
# arctic-fetch-3d. The wrapper (dotfiles/.local/bin/arctic-fetch) runs it, and falls back to
# the bash fox where it isn't installed, so this is the only part of the fetch that can fail.
make -C fetch

%install
# ---------------------------------------------------------------- arctic-release
rel=packaging/release
install -Dpm 0644 $rel/os-release %{buildroot}%{_prefix}/lib/os-release
install -d %{buildroot}%{_sysconfdir}
ln -s ../usr/lib/os-release %{buildroot}%{_sysconfdir}/os-release
echo "Arctic Linux release %{arctic_version} (Fedora %{dist_version} base)" > %{buildroot}%{_prefix}/lib/arctic-release
ln -s arctic-release %{buildroot}%{_prefix}/lib/fedora-release
echo "cpe:/o:arcticlinux:arctic_linux:%{arctic_version}" > %{buildroot}%{_prefix}/lib/system-release-cpe
ln -s ../usr/lib/arctic-release %{buildroot}%{_sysconfdir}/arctic-release
ln -s ../usr/lib/arctic-release %{buildroot}%{_sysconfdir}/fedora-release
ln -s arctic-release %{buildroot}%{_sysconfdir}/redhat-release
ln -s arctic-release %{buildroot}%{_sysconfdir}/system-release
ln -s ../usr/lib/system-release-cpe %{buildroot}%{_sysconfdir}/system-release-cpe
install -pm 0644 $rel/issue %{buildroot}%{_prefix}/lib/issue
install -pm 0644 $rel/issue.net %{buildroot}%{_prefix}/lib/issue.net
ln -s ../usr/lib/issue %{buildroot}%{_sysconfdir}/issue
ln -s ../usr/lib/issue.net %{buildroot}%{_sysconfdir}/issue.net
install -Dpm 0644 $rel/macros.dist %{buildroot}%{_rpmconfigdir}/macros.d/macros.dist
install -Dpm 0644 $rel/copr-arctic.conf %{buildroot}%{_sysconfdir}/dnf/plugins/copr.d/arctic.conf
install -Dpm 0644 $rel/20-arctic-dnf-defaults.conf %{buildroot}%{_datadir}/dnf5/libdnf.conf.d/20-arctic-defaults.conf
# The Arctic repositories (docs/BUILD-SPEC.md §9), signed with the key in
# packaging/release/RPM-GPG-KEY-arctic: committed, or put into Source0 by tools/build-rpms.sh
# (--gpg-public-key / ARCTIC_GPG_PUBLIC_KEY). Without the key nothing from them could pass
# gpgcheck, so they are shipped disabled; the build still succeeds (local test builds).
install -d %{buildroot}%{_datadir}/dnf5/repos.d
printf '%%s\n' %{_datadir}/dnf5/repos.d/arctic.repo %{_datadir}/dnf5/repos.d/arctic-testing.repo > release.files
if [ -s $rel/RPM-GPG-KEY-arctic ]; then
  install -Dpm 0644 $rel/RPM-GPG-KEY-arctic %{buildroot}%{_sysconfdir}/pki/rpm-gpg/RPM-GPG-KEY-arctic
  echo %{_sysconfdir}/pki/rpm-gpg/RPM-GPG-KEY-arctic >> release.files
  install -pm 0644 $rel/arctic.repo $rel/arctic-testing.repo %{buildroot}%{_datadir}/dnf5/repos.d/
else
  echo "warning: $rel/RPM-GPG-KEY-arctic is missing: arctic-release ships the Arctic repositories DISABLED" >&2
  for f in arctic.repo arctic-testing.repo; do
    sed -e '1i # DISABLED: this arctic-release was built without the repository key (tools/build-rpms.sh).' \
        -e 's/^enabled=1$/enabled=0/' $rel/$f > %{buildroot}%{_datadir}/dnf5/repos.d/$f
    touch -r $rel/$f %{buildroot}%{_datadir}/dnf5/repos.d/$f
  done
fi
install -Dpm 0644 $rel/80-arctic.preset %{buildroot}%{_presetdir}/80-arctic.preset
install -pm 0644 $rel/85-display-manager.preset $rel/90-default.preset $rel/99-default-disable.preset %{buildroot}%{_presetdir}/
install -Dpm 0644 $rel/80-arctic-user.preset %{buildroot}%{_userpresetdir}/80-arctic.preset
install -pm 0644 $rel/90-default-user.preset %{buildroot}%{_userpresetdir}/90-default-user.preset
install -pm 0644 $rel/99-default-disable-user.preset %{buildroot}%{_userpresetdir}/99-default-disable.preset

# ---------------------------------------------------------------- arctic-logos
# branding/logos mirrors the install paths (usr/…, etc/…).
cp -a branding/logos/. %{buildroot}/
(cd branding/logos && find . -type f -o -type l) | sed 's,^\.,,' | while read -r f; do
  case "$f" in
    /etc/*) echo "%%config(noreplace) $f" ;;
    *) echo "$f" ;;
  esac
done > logos.files
(cd branding/logos && find ./usr/share/arctic -type d 2>/dev/null) | sed 's,^\.,%%dir ,' >> logos.files
test -s logos.files

# ---------------------------------------------------------------- arctic-backgrounds
install -d %{buildroot}%{_datadir}/backgrounds/arctic
install -pm 0644 _build/backgrounds/* %{buildroot}%{_datadir}/backgrounds/arctic/
ln -s arctic/aurora-winter.png %{buildroot}%{_datadir}/backgrounds/default.png
ln -s arctic/aurora-polar-night.png %{buildroot}%{_datadir}/backgrounds/default-dark.png

# ---------------------------------------------------------------- arctic-fonts
install -d %{buildroot}%{_datadir}/fonts/arctic
if ls branding/fonts/Figtree-*.ttf >/dev/null 2>&1; then
  install -pm 0644 branding/fonts/Figtree-*.ttf %{buildroot}%{_datadir}/fonts/arctic/
else
  install -pm 0644 design/fonts/Figtree-*.woff2 %{buildroot}%{_datadir}/fonts/arctic/
fi
# --- stream 6: arctic-fonts-symbols (after the code font in fontconfig's fallback list)
install -d %{buildroot}%{_datadir}/fonts/arctic-symbols
install -pm 0644 _build/nerd-symbols/SymbolsNerdFont-Regular.ttf _build/nerd-symbols/SymbolsNerdFontMono-Regular.ttf \
  %{buildroot}%{_datadir}/fonts/arctic-symbols/
install -Dpm 0644 packaging/fonts/66-arctic-nerd-symbols.conf \
  %{buildroot}%{_datadir}/fontconfig/conf.avail/66-arctic-nerd-symbols.conf
install -d %{buildroot}%{_sysconfdir}/fonts/conf.d
ln -s %{_datadir}/fontconfig/conf.avail/66-arctic-nerd-symbols.conf %{buildroot}%{_sysconfdir}/fonts/conf.d/
# --- end stream 6

# ---------------------------------------------------------------- arctic-selinux
install -Dpm 0644 packaging/selinux/arctic-nix.pp %{buildroot}%{_datadir}/selinux/packages/arctic-nix.pp

# ---------------------------------------------------------------- arctic-desktop-config
# arctic-firstboot finishes app installs the installer put off (/var/lib/arctic/pending.json).
# It lives here, not in arctic-installer, because the installer is removed from the new system.
install -Dpm 0644 packaging/systemd/arctic-firstboot.service %{buildroot}%{_unitdir}/arctic-firstboot.service
install -Dpm 0755 packaging/firstboot/arctic-firstboot %{buildroot}%{_libexecdir}/arctic/arctic-firstboot
# New accounts start from /etc/skel. What Arctic keeps up to date is installed once, in
# /usr/share/arctic, and the home directory only points at it, so package updates reach
# accounts that already exist (a copy in the home directory would never change again):
#   ~/.config/mango/arctic/*.conf  links to /usr/share/arctic/mango/*.conf; replacing a link
#                                  with a copy keeps that file as the person edited it
#   ~/.config/arctic/current       link to /usr/share/arctic/themes/polar-night (arctic-theme
#                                  switches it; a theme copied to ~/.config/arctic/themes wins)
#   keys.txt                       not copied: the shell and arctic-keys fall back to
#                                  /usr/share/arctic/keys.txt
# The links are absolute on purpose (rpmbuild warns): useradd copies them into home
# directories, where a relative link would point elsewhere. dotfiles/install.sh (no packages)
# copies all of these into the home directory instead.
install -d %{buildroot}%{_sysconfdir}/skel
tar -C dotfiles --exclude=./install.sh --exclude=./README.md --exclude=./.local/bin \
    --exclude=./.local/share/arctic --exclude=./.config/mango/arctic \
    --exclude=./.config/arctic/themes --exclude=./.config/arctic/current \
    --exclude=./.zshrc --exclude=./.zprofile -cf - . \
  | tar -C %{buildroot}%{_sysconfdir}/skel -xf -
install -d %{buildroot}%{_datadir}/arctic/mango %{buildroot}%{_sysconfdir}/skel/.config/mango/arctic
for f in dotfiles/.config/mango/arctic/*.conf; do
  f="${f##*/}"
  install -pm 0644 "dotfiles/.config/mango/arctic/$f" %{buildroot}%{_datadir}/arctic/mango/
  ln -s "%{_datadir}/arctic/mango/$f" "%{buildroot}%{_sysconfdir}/skel/.config/mango/arctic/$f"
done
# zsh owns /etc/skel/.zshrc and .zprofile: Arctic's versions are kept here and copied over
# zsh's (unmodified) ones by the %%posttrans / %%triggerin scriptlets below.
install -d %{buildroot}%{_datadir}/arctic/skel
for f in .zshrc .zprofile; do
  if [ -f "dotfiles/$f" ]; then install -pm 0644 "dotfiles/$f" %{buildroot}%{_datadir}/arctic/skel/; fi
done
# The starting theme (dotfiles/install.sh does the same for a home directory).
ln -sfn %{_datadir}/arctic/themes/polar-night %{buildroot}%{_sysconfdir}/skel/.config/arctic/current
echo polar-night > %{buildroot}%{_sysconfdir}/skel/.config/arctic/theme
install -d %{buildroot}%{_bindir}
install -pm 0755 dotfiles/.local/bin/* %{buildroot}%{_bindir}/
# neofetch: the wrapper lives in /usr/libexec/arctic and /usr/bin/neofetch is a %%ghost link to
# it (made in %%posttrans), so a real neofetch package can take the name: a %%ghost never
# conflicts with another package's file (%%triggerpostun below puts the link back after it).
install -d %{buildroot}%{_libexecdir}/arctic
mv %{buildroot}%{_bindir}/neofetch %{buildroot}%{_libexecdir}/arctic/neofetch
ln -s ../libexec/arctic/neofetch %{buildroot}%{_bindir}/neofetch
# fastfetch: the layout of arctic-fetch's info column and the fox as a text logo (the themes
# carry fastfetch/config.jsonc and fastfetch/neofetch.jsonc, from templates). Accounts without
# ~/.config/fastfetch/config.jsonc (root; accounts made before it was in /etc/skel) get the
# Polar night one through fastfetch's system config.
install -d %{buildroot}%{_datadir}/arctic/fastfetch
install -pm 0644 dotfiles/.local/share/arctic/fastfetch/* %{buildroot}%{_datadir}/arctic/fastfetch/
install -d %{buildroot}%{_sysconfdir}/xdg/fastfetch
ln -s %{_datadir}/arctic/themes/polar-night/fastfetch/config.jsonc %{buildroot}%{_sysconfdir}/xdg/fastfetch/config.jsonc
install -Dpm 0644 dotfiles/.local/share/arctic/keys.txt %{buildroot}%{_datadir}/arctic/keys.txt
install -d %{buildroot}%{_datadir}/arctic/themes
cp -a _build/themes/. %{buildroot}%{_datadir}/arctic/themes/
# --- stream 6: the theme gallery (arctic-themes-extra)
install -d %{buildroot}%{_datadir}/arctic/themes-extra
cp -a _build/themes-extra/. %{buildroot}%{_datadir}/arctic/themes-extra/
# The theme engine (arctic-themegen, run by arctic-theme) and the design data it reads.
themegen=%{buildroot}%{_datadir}/arctic/themegen
install -d "$themegen/data/exports" "$themegen/data/icons" "$themegen/data/logos"
tar -C design/themegen --exclude=./tests --exclude=__pycache__ -cf - . | tar -C "$themegen" -xf -
install -pm 0644 design/exports/arctic-tokens.json design/exports/gtk-arctic-*.css "$themegen/data/exports/"
install -pm 0644 design/icons/*.svg "$themegen/data/icons/"
install -pm 0644 design/logos/arctic-mark-16-*.svg "$themegen/data/logos/"
# Outside site-packages brp-python-bytecompile skips it: compile here, or every run would
# compile from source (and fail to write __pycache__ into /usr/share).
%py_byte_compile %{python3} %{buildroot}%{_datadir}/arctic/themegen
install -Dpm 0644 packaging/desktop/default-apps %{buildroot}%{_sysconfdir}/arctic/default-apps
install -d %{buildroot}%{_sysconfdir}/arctic/mango
install -Dpm 0644 packaging/desktop/arctic-graphics.sh %{buildroot}%{_sysconfdir}/profile.d/arctic-graphics.sh
install -Dpm 0755 packaging/nix/arctic-nix-system %{buildroot}%{_libexecdir}/arctic-nix-system
install -Dpm 0644 packaging/nix/org.arcticlinux.nix.policy %{buildroot}%{_datadir}/polkit-1/actions/org.arcticlinux.nix.policy
install -Dpm 0644 packaging/desktop/arctic-nix.sh %{buildroot}%{_sysconfdir}/profile.d/zz-arctic-nix.sh
install -Dpm 0644 packaging/environment.d/60-arctic-nix.conf %{buildroot}%{_prefix}/lib/environment.d/60-arctic-nix.conf
# Stream 5 (system): the SSH agent's socket for the session (gcr-ssh-agent), and the root helper
# Settings uses for the firewall, remote login and snapshots (pkexec, org.arcticlinux.system).
install -Dpm 0644 packaging/desktop/arctic-ssh-agent.sh %{buildroot}%{_sysconfdir}/profile.d/arctic-ssh-agent.sh
install -Dpm 0755 packaging/system/arctic-system-helper %{buildroot}%{_libexecdir}/arctic/arctic-system-helper
install -Dpm 0644 packaging/systemd/arctic-login-wallpaper.service %{buildroot}%{_unitdir}/arctic-login-wallpaper.service
install -Dpm 0644 packaging/system/arctic-wallpaper.sysusers %{buildroot}%{_sysusersdir}/arctic-wallpaper.conf
install -Dpm 0644 packaging/system/org.arcticlinux.Wallpaper.service %{buildroot}%{_datadir}/dbus-1/system-services/org.arcticlinux.Wallpaper.service
install -Dpm 0644 packaging/system/org.arcticlinux.Wallpaper.conf %{buildroot}%{_datadir}/dbus-1/system.d/org.arcticlinux.Wallpaper.conf
install -Dpm 0644 packaging/polkit/org.arcticlinux.wallpaper.policy %{buildroot}%{_datadir}/polkit-1/actions/org.arcticlinux.wallpaper.policy
install -Dpm 0644 packaging/polkit/org.arcticlinux.system.policy \
  %{buildroot}%{_datadir}/polkit-1/actions/org.arcticlinux.system.policy
# Reading the firewall's rules (Settings > Sharing) without a password in the active session.
install -Dpm 0644 packaging/polkit/50-arctic-firewalld-read.rules \
  %{buildroot}%{_datadir}/polkit-1/rules.d/50-arctic-firewalld-read.rules
# Thunar's Send To menu: LocalSend (arctic-share files).
install -Dpm 0644 packaging/desktop/arctic-sendto-localsend.desktop \
  %{buildroot}%{_datadir}/Thunar/sendto/arctic-sendto-localsend.desktop
# Automatic updates (arctic-update, in /usr/bin with the helpers above) and snapshots.
install -Dpm 0644 packaging/systemd/arctic-update-stage.service %{buildroot}%{_unitdir}/arctic-update-stage.service
install -Dpm 0644 packaging/systemd/arctic-update-stage.timer %{buildroot}%{_unitdir}/arctic-update-stage.timer
install -Dpm 0644 packaging/systemd/arctic-update-restage.timer %{buildroot}%{_unitdir}/arctic-update-restage.timer
# Stream 5 (system): Flatpak apps are updated daily too (arctic-update flatpak --auto).
install -Dpm 0644 packaging/systemd/arctic-flatpak-update.service %{buildroot}%{_unitdir}/arctic-flatpak-update.service
install -Dpm 0644 packaging/systemd/arctic-flatpak-update.timer %{buildroot}%{_unitdir}/arctic-flatpak-update.timer
install -Dpm 0644 packaging/systemd/user/arctic-flatpak-update.service %{buildroot}%{_userunitdir}/arctic-flatpak-update.service
install -Dpm 0644 packaging/systemd/user/arctic-flatpak-update.timer %{buildroot}%{_userunitdir}/arctic-flatpak-update.timer
install -Dpm 0755 packaging/updates/arctic-update-helper %{buildroot}%{_libexecdir}/arctic/arctic-update-helper
install -Dpm 0644 packaging/updates/update.conf %{buildroot}%{_sysconfdir}/arctic/update.conf
install -Dpm 0644 packaging/updates/snapper.actions \
  %{buildroot}%{_sysconfdir}/dnf/libdnf5-plugins/actions.d/arctic-snapper.actions
install -Dpm 0644 packaging/updates/update.actions \
  %{buildroot}%{_sysconfdir}/dnf/libdnf5-plugins/actions.d/arctic-update.actions
# The status file the shell's bar indicator watches (written by arctic-update).
install -d %{buildroot}%{_sharedstatedir}/arctic
touch %{buildroot}%{_sharedstatedir}/arctic/update-status.json
# App theming (docs/BUILD-SPEC.md "App theming"): the hooks `arctic-theme reload` runs after a
# theme change, GTK/icon/cursor/font defaults in dconf's "distro" database (Fedora's dconf
# profile reads it after the user's and the administrator's), and Flatpak overrides.
# theme-hooks.d: executables run after every theme switch (other packages may add theirs).
install -d %{buildroot}%{_datadir}/arctic/theme-hooks.d
install -pm 0755 packaging/theme-hooks.d/* %{buildroot}%{_datadir}/arctic/theme-hooks.d/
install -Dpm 0644 packaging/dconf/10-arctic %{buildroot}%{_sysconfdir}/dconf/db/distro.d/10-arctic
# The compiled database `dconf update` writes in %%posttrans: owned (%%ghost) so that erase
# removes it and rpm -V knows it.
touch %{buildroot}%{_sysconfdir}/dconf/db/distro
install -Dpm 0644 packaging/flatpak/global %{buildroot}%{_localstatedir}/lib/flatpak/overrides/global
# QT_QPA_PLATFORMTHEME=qt6ct for systemd/D-Bus started apps, system-wide so that accounts with
# an older copied ~/.config/environment.d/10-arctic.conf (xdgdesktopportal) follow too.
install -Dpm 0644 packaging/environment.d/50-arctic-qt.conf %{buildroot}%{_prefix}/lib/environment.d/50-arctic-qt.conf
# Stream 4 (capture): the screen-share picker xdg-desktop-portal-wlr runs in Mango sessions.
install -Dpm 0644 packaging/desktop/xdg-desktop-portal-wlr.ini %{buildroot}%{_sysconfdir}/xdg/xdg-desktop-portal-wlr/mango
# Mango owns its upstream /usr/share portal defaults. Arctic's system preferences
# override those through the portal's /etc/xdg search path without sharing a file.
install -Dpm 0644 packaging/desktop/mango-portals.conf %{buildroot}%{_sysconfdir}/xdg/xdg-desktop-portal/mango-portals.conf
install -Dpm 0755 packaging/desktop/arctic-share-picker %{buildroot}%{_libexecdir}/arctic/arctic-share-picker
# Stream 5 (system): XDG autostart in the Mango session (packaging/desktop/autostart): the
# session target wants xdg-desktop-autostart.target, and the entries Arctic starts itself or
# doesn't use stay off there (drop-ins for the units systemd-xdg-autostart-generator makes;
# the names are systemd-escaped desktop ids, "-" is \x2d).
install -Dpm 0644 packaging/desktop/autostart/mango-session-autostart.conf \
  %{buildroot}%{_userunitdir}/mango-session.target.d/arctic-autostart.conf
for id in 'nm\x2dapplet' 'blueman' 'geoclue\x2ddemo\x2dagent'; do
  install -Dpm 0644 packaging/desktop/autostart/arctic-starts-it.conf \
    "%{buildroot}%{_userunitdir}/app-${id}@autostart.service.d/arctic.conf"
done
# arctic-shell, arctic-shell-ipc, arctic-settings and arctic-installer belong to their own
# subpackages; neofetch is listed below (%%ghost).
(cd dotfiles/.local/bin && ls) | grep -vxE 'arctic-shell|arctic-shell-ipc|arctic-settings|arctic-installer|neofetch' \
  | sed 's,^,%{_bindir}/,' > desktop-config.files
# /usr/share/arctic/mango is shared with arctic-live (live.conf).
(cd dotfiles/.config/mango/arctic && ls -- *.conf) | sed 's,^,%{_datadir}/arctic/mango/,' >> desktop-config.files

# ---------------------------------------------------------------- arctic-shell
install -d %{buildroot}%{_datadir}/arctic/shell
# tests/ and dev/ (design export scripts, Node) are development-only.
tar -C shell --exclude=./tests --exclude=./dev -cf - . | tar -C %{buildroot}%{_datadir}/arctic/shell -xf -
# The launchers come from dotfiles/.local/bin when the dotfiles have them (installed above
# with the other helpers); otherwise minimal ones.
if [ ! -f dotfiles/.local/bin/arctic-shell ]; then
cat > %{buildroot}%{_bindir}/arctic-shell << 'EOF'
#!/bin/sh
# Arctic Linux desktop shell (Quickshell config in /usr/share/arctic/shell).
exec quickshell -p /usr/share/arctic/shell "$@"
EOF
fi
if [ ! -f dotfiles/.local/bin/arctic-shell-ipc ]; then
cat > %{buildroot}%{_bindir}/arctic-shell-ipc << 'EOF'
#!/bin/sh
# arctic-shell-ipc <target> <function> [args…]: call into the running Arctic shell,
# e.g. arctic-shell-ipc launcher toggle
exec quickshell -p /usr/share/arctic/shell ipc call "$@"
EOF
fi
chmod 0755 %{buildroot}%{_bindir}/arctic-shell %{buildroot}%{_bindir}/arctic-shell-ipc
# Get apps: pkexec dnf5 (install and remove) with the password kept for a few minutes.
install -Dpm 0644 packaging/polkit/org.arcticlinux.pkexec.dnf.policy \
  %{buildroot}%{_datadir}/polkit-1/actions/org.arcticlinux.pkexec.dnf.policy

# ---------------------------------------------------------------- arctic-fetch-3d
# The 3D greeting, built above from fetch/. arctic-fetch (a wrapper in dotfiles/.local/bin,
# installed with the other helpers) runs it, so the wrapper is what the shell calls; the
# config here is the system default it reads when you haven't written your own.
install -d %{buildroot}%{_libexecdir}/arctic
install -pm 0755 fetch/arctic-fetch-3d %{buildroot}%{_libexecdir}/arctic/arctic-fetch-3d
install -d %{buildroot}%{_datadir}/arctic/fetch
install -pm 0644 fetch/config %{buildroot}%{_datadir}/arctic/fetch/config

# ---------------------------------------------------------------- arctic-settings
# /usr/bin/arctic-settings was installed with the other helpers (dotfiles/.local/bin).
install -d %{buildroot}%{_datadir}/arctic/settings
# tests/ and dev/ (headless screenshots) are development-only.
tar -C settings --exclude=./tests --exclude=./dev --exclude=./README.md -cf - . | tar -C %{buildroot}%{_datadir}/arctic/settings -xf -
chmod 0755 %{buildroot}%{_datadir}/arctic/settings/scripts/arctic_settings.py
desktop-file-install --dir=%{buildroot}%{_datadir}/applications packaging/settings/org.arcticlinux.Settings.desktop
install -Dpm 0644 packaging/settings/org.arcticlinux.Settings.svg \
  %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/org.arcticlinux.Settings.svg

# ---------------------------------------------------------------- arctic-webapps (stream 1)
install -pm 0755 _build/bin/arctic-webapp %{buildroot}%{_bindir}/
install -Dpm 0755 _build/bin/arctic-webapp-host %{buildroot}%{_libexecdir}/arctic/arctic-webapp-host

# ---------------------------------------------------------------- arctic-installer
install -pm 0755 _build/bin/arcticd _build/bin/arctic-install %{buildroot}%{_bindir}/
install -d %{buildroot}%{_datadir}/arctic/catalog %{buildroot}%{_datadir}/arctic/profiles %{buildroot}%{_datadir}/arctic/installer-ui
tar -C modules --exclude='*.go' -cf - . | tar -C %{buildroot}%{_datadir}/arctic/catalog -xf -
tar -C profiles --exclude='*.go' -cf - . | tar -C %{buildroot}%{_datadir}/arctic/profiles -xf -
tar -C installer-ui --exclude=./tests --exclude=./dev -cf - . | tar -C %{buildroot}%{_datadir}/arctic/installer-ui -xf -
[ -f dotfiles/.local/bin/arctic-installer ] || cat > %{buildroot}%{_bindir}/arctic-installer << 'EOF'
#!/bin/sh
# Arctic Linux installer (Quickshell wizard in /usr/share/arctic/installer-ui). It talks to
# arcticd through `arctic-install bridge`.
exec quickshell -p /usr/share/arctic/installer-ui "$@"
EOF
chmod 0755 %{buildroot}%{_bindir}/arctic-installer
install -Dpm 0644 packaging/systemd/arcticd.socket %{buildroot}%{_unitdir}/arcticd.socket
install -Dpm 0644 packaging/systemd/arcticd.service %{buildroot}%{_unitdir}/arcticd.service
desktop-file-install --dir=%{buildroot}%{_datadir}/applications packaging/installer/org.arcticlinux.Installer.desktop
install -d %{buildroot}%{_localstatedir}/log/arctic-install

# ---------------------------------------------------------------- sddm-wayland-mango
install -Dpm 0644 packaging/sddm-wayland-mango/10-arctic.conf %{buildroot}%{_prefix}/lib/sddm/sddm.conf.d/10-arctic.conf
install -Dpm 0755 packaging/sddm-wayland-mango/sddm-compositor-mango %{buildroot}%{_libexecdir}/arctic/sddm-compositor-mango
install -Dpm 0644 packaging/sddm-wayland-mango/greeter.conf %{buildroot}%{_datadir}/arctic/sddm/greeter.conf

# ---------------------------------------------------------------- arctic-sddm-theme
install -d %{buildroot}%{_datadir}/sddm/themes/arctic
cp -a branding/sddm/arctic/. %{buildroot}%{_datadir}/sddm/themes/arctic/

# ---------------------------------------------------------------- arctic-plymouth-theme
install -d %{buildroot}%{_datadir}/plymouth/themes/arctic
cp -a branding/plymouth/arctic/. %{buildroot}%{_datadir}/plymouth/themes/arctic/
# The initrd hook for arctic.reduce_motion=1: it links /run/arctic/reduce-motion.png, which
# arctic.script looks for. The scripts stay executable (the hook becomes an ExecStartPre).
dracutmod=%{buildroot}%{_prefix}/lib/dracut/modules.d/90arctic-plymouth
install -d "$dracutmod"
install -pm 0755 branding/plymouth/dracut/90arctic-plymouth/module-setup.sh \
                 branding/plymouth/dracut/90arctic-plymouth/arctic-reduce-motion.sh "$dracutmod/"
install -pm 0644 branding/plymouth/dracut/90arctic-plymouth/arctic-reduce-motion.conf "$dracutmod/"

# ---------------------------------------------------------------- arctic-grub-theme
install -d %{buildroot}/boot/grub2/themes/arctic %{buildroot}%{_datadir}/arctic/grub-theme
cp -a branding/grub/arctic/. %{buildroot}/boot/grub2/themes/arctic/
cp -a branding/grub/arctic/. %{buildroot}%{_datadir}/arctic/grub-theme/

# ---------------------------------------------------------------- arctic-live
install -Dpm 0755 live/livesys-arctic %{buildroot}%{_libexecdir}/livesys/sessions.d/livesys-arctic
install -Dpm 0755 live/live-session %{buildroot}%{_libexecdir}/arctic/live-session
install -Dpm 0755 live/live-keyboard %{buildroot}%{_libexecdir}/arctic/live-keyboard
install -Dpm 0644 live/live.conf %{buildroot}%{_datadir}/arctic/mango/live.conf

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/org.arcticlinux.Installer.desktop
# arctic-release: the key and enabled repositories go together; never secret key material;
# the testing channel is always off by default.
key=%{buildroot}%{_sysconfdir}/pki/rpm-gpg/RPM-GPG-KEY-arctic
repos=%{buildroot}%{_datadir}/dnf5/repos.d
for id in arctic arctic-source arctic-testing arctic-testing-source; do
  grep -qx "\[$id\]" $repos/arctic.repo $repos/arctic-testing.repo || { echo "error: no [$id] repository" >&2; exit 1; }
done
if [ -e "$key" ]; then
  grep -q -- '-----BEGIN PGP PUBLIC KEY BLOCK-----' "$key" || { echo "error: $key is not an armored public key" >&2; exit 1; }
  if grep -q 'PRIVATE KEY' "$key"; then echo "error: $key holds a private key" >&2; exit 1; fi
  grep -qx 'enabled=1' $repos/arctic.repo || { echo "error: arctic.repo is not enabled" >&2; exit 1; }
elif grep -qx 'enabled=1' $repos/arctic.repo; then
  echo "error: arctic.repo is enabled without its key" >&2; exit 1
fi
if grep -qx 'enabled=1' $repos/arctic-testing.repo; then
  echo "error: arctic-testing.repo must be disabled by default" >&2; exit 1
fi
# The theme engine: colour maths, templates, wallpaper palettes and their contrast guarantees,
# arctic-theme / arctic-wallpaper, and that dotfiles/.config/arctic/themes is current.
# (ARCTIC_PERF_BUDGET: builders are slower and busier than a desktop.)
ARCTIC_PERF_BUDGET=10 PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s design/themegen/tests
# The installed engine renders from the installed data exactly what %%build made.
tg="%{buildroot}%{_bindir}/arctic-themegen"
ARCTIC_THEMEGEN_DIR=%{buildroot}%{_datadir}/arctic/themegen PYTHONDONTWRITEBYTECODE=1 python3 "$tg" builtin winter > _build/winter.json
rm -rf _build/check-theme
ARCTIC_THEMEGEN_DIR=%{buildroot}%{_datadir}/arctic/themegen PYTHONDONTWRITEBYTECODE=1 \
  python3 "$tg" render --palette _build/winter.json --out _build/check-theme --quiet
diff -r _build/check-theme %{buildroot}%{_datadir}/arctic/themes/winter
desktop-file-validate %{buildroot}%{_datadir}/applications/org.arcticlinux.Settings.desktop
desktop-file-validate %{buildroot}%{_datadir}/Thunar/sendto/arctic-sendto-localsend.desktop
# Settings' backend: the file formats it reads and writes (uses `mango -p` when installed).
python3 -m unittest discover -s settings/tests -p 'test_*.py'
# ---- stream 2 (Get apps): apps.py's contracts, the job commands, and that
# protected-packages.conf covers modules/_system/desktop-base.
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s shell/tests -p 'test_apps.py'
# ---- end stream 2
for s in %{buildroot}%{_libexecdir}/arctic/* %{buildroot}%{_libexecdir}/livesys/sessions.d/livesys-arctic \
         %{buildroot}%{_bindir}/arctic-shell %{buildroot}%{_bindir}/arctic-installer %{buildroot}%{_bindir}/arctic-update \
         %{buildroot}%{_datadir}/arctic/theme-hooks.d/*; do
  # arctic-webapp-host (stream 1) is an ELF binary, not a script
  case "$(head -c4 "$s")" in "$(printf '\177ELF')") continue ;; esac
  case "$(head -n1 "$s")" in
    *python*) python3 -c 'import ast,sys; ast.parse(open(sys.argv[1]).read())' "$s" ;;
    *) bash -n "$s" ;;
  esac
done
# arctic-update's file handling (update.conf, dnf5's offline state, the status file).
python3 -m unittest discover -s packaging/updates -p 'test_*.py'
# ---- stream 1 (web apps): the host is the real cgo build and the manager is cgo-free; both
# start without a display; the launcher entries the manager writes are valid.
readelf -d %{buildroot}%{_libexecdir}/arctic/arctic-webapp-host | grep -q 'NEEDED.*libwebkitgtk-6\.0\.so\.4'
if readelf -d %{buildroot}%{_bindir}/arctic-webapp | grep -q NEEDED; then
  echo "error: arctic-webapp must not link any library (CGO_ENABLED=0)" >&2; exit 1
fi
%{buildroot}%{_libexecdir}/arctic/arctic-webapp-host --version
%{buildroot}%{_bindir}/arctic-webapp version
rm -rf _build/webapp-sample
%{buildroot}%{_bindir}/arctic-webapp render-sample _build/webapp-sample
desktop-file-validate _build/webapp-sample/*.desktop
test -f %{buildroot}%{_datadir}/sddm/themes/arctic/metadata.desktop || \
  { echo "error: branding/sddm/arctic has no metadata.desktop" >&2; exit 1; }
test -f %{buildroot}%{_datadir}/plymouth/themes/arctic/arctic.plymouth || \
  { echo "error: branding/plymouth/arctic has no arctic.plymouth" >&2; exit 1; }
for f in module-setup.sh arctic-reduce-motion.sh; do
  test -x %{buildroot}%{_prefix}/lib/dracut/modules.d/90arctic-plymouth/$f || \
    { echo "error: 90arctic-plymouth/$f is missing or not executable" >&2; exit 1; }
  bash -n %{buildroot}%{_prefix}/lib/dracut/modules.d/90arctic-plymouth/$f
done
test -f %{buildroot}/boot/grub2/themes/arctic/theme.txt || \
  { echo "error: branding/grub/arctic has no theme.txt" >&2; exit 1; }
test -f %{buildroot}%{_datadir}/pixmaps/system-logo-white.png || \
  { echo "error: branding/logos has no usr/share/pixmaps/system-logo-white.png" >&2; exit 1; }
# os-release LOGO= names the icon fastfetch and others look up.
logo="$(sed -n 's/^LOGO=//p' %{buildroot}%{_prefix}/lib/os-release)"
test -n "$logo" && test -f "%{buildroot}%{_datadir}/pixmaps/$logo.png" && test -f "%{buildroot}%{_datadir}/pixmaps/$logo.svg" || \
  { echo "error: os-release LOGO=$logo has no /usr/share/pixmaps/$logo.png and .svg" >&2; exit 1; }
# neofetch (a %%ghost link to the wrapper) and fastfetch's system config (a link into the themes).
test -x %{buildroot}%{_libexecdir}/arctic/neofetch
# The 3D greeting: a real ELF binary that reports its version and renders. Without this, a C
# build that produced an empty or non-executable file would still package and only fail on a
# user's first run of arctic-fetch.
f3d=%{buildroot}%{_libexecdir}/arctic/arctic-fetch-3d
test -x "$f3d" || { echo "error: arctic-fetch-3d is missing or not executable" >&2; exit 1; }
test "$(head -c4 "$f3d")" = "$(printf '\177ELF')" || { echo "error: arctic-fetch-3d is not an ELF binary" >&2; exit 1; }
"$f3d" --version >/dev/null || { echo "error: arctic-fetch-3d does not run" >&2; exit 1; }
test -s "%{buildroot}%{_datadir}/arctic/fetch/config" || \
  { echo "error: the arctic-fetch system config is missing or empty" >&2; exit 1; }
test "$(readlink %{buildroot}%{_bindir}/neofetch)" = ../libexec/arctic/neofetch
test -f "%{buildroot}$(readlink %{buildroot}%{_sysconfdir}/xdg/fastfetch/config.jsonc)"
for t in winter polar-night; do
  for f in config.jsonc neofetch.jsonc; do
    test -f %{buildroot}%{_datadir}/arctic/themes/$t/fastfetch/$f || { echo "error: theme $t has no fastfetch/$f" >&2; exit 1; }
  done
done
# The links /etc/skel keeps into /usr/share/arctic must resolve.
skel_links="$(find %{buildroot}%{_sysconfdir}/skel -type l)"
test -n "$skel_links"
for l in $skel_links; do
  t="$(readlink "$l")"
  case "$t" in /*) test -e "%{buildroot}$t" || { echo "error: $l -> $t: not in the package" >&2; exit 1; } ;; esac
done
# Relative links (yazi, btop, GTK, qt*ct colour schemes …) go through ~/.config/arctic/current:
# in a copy of skel whose `current` is the buildroot's theme, every link must resolve.
lhome="$PWD/_build/linkhome"; rm -rf "$lhome"; mkdir -p "$lhome"
cp -a %{buildroot}%{_sysconfdir}/skel/. "$lhome/"
for l in $(find "$lhome" -type l); do
  t="$(readlink "$l")"
  case "$t" in /*) ln -sfn "%{buildroot}$t" "$l" ;; esac
done
dangling="$(find -L "$lhome" -type l)"
if [ -n "$dangling" ]; then echo "error: dangling links in /etc/skel:" >&2; echo "$dangling" >&2; exit 1; fi
# The qt*ct colour schemes are absolute paths inside ~/.config/arctic/current.
for q in qt5ct qt6ct; do
  p="$(sed -n 's,^color_scheme_path=,,p' "$lhome/.config/$q/$q.conf")"
  case "$p" in "~/"*) p="$lhome/${p#\~/}" ;; esac
  test -z "$p" || test -f "$p" || { echo "error: $q color_scheme_path $p is missing" >&2; exit 1; }
done
# Mango configs: validated when mangowm is installed in the build root (tools/build-rpms.sh
# installs the freshly built one); `mango -c FILE -p` rejects unknown keys.
if command -v mango >/dev/null 2>&1; then
  mango -c %{buildroot}%{_datadir}/arctic/sddm/greeter.conf -p
  mango -c %{buildroot}%{_datadir}/arctic/mango/live.conf -p
  home="$PWD/_build/home"; rm -rf "$home"; mkdir -p "$home"
  cp -a %{buildroot}%{_sysconfdir}/skel/. "$home/"
  # A new account as it will be: its links point into /usr/share, here still the buildroot.
  for l in $(find "$home" -type l); do
    t="$(readlink "$l")"
    case "$t" in /*) ln -sfn "%{buildroot}$t" "$l" ;; esac
  done
  HOME="$home" mango -c "$home/.config/mango/config.conf" -p
fi

# ---------------------------------------------------------------------------------------------
# Every build has a new Release, so every Arctic update updates arctic-selinux too; its module
# rarely changes. semodule rebuilds the whole policy (the slowest step of an update), so an
# update skips it when the module is byte-for-byte the one installed (the build is
# reproducible) and semodule has it; anything else installs it as usual.
%global arctic_selinux_state %{_localstatedir}/lib/rpm-state/arctic-selinux

%pre -n arctic-selinux
%selinux_relabel_pre -s %{selinuxtype}
rm -rf %{arctic_selinux_state} || :
if [ $1 -gt 1 ] && [ -f %{_datadir}/selinux/packages/arctic-nix.pp ]; then
  mkdir -p %{arctic_selinux_state} && \
    cp -p %{_datadir}/selinux/packages/arctic-nix.pp %{arctic_selinux_state}/arctic-nix.pp || :
fi

%post -n arctic-selinux
if [ $1 -gt 1 ] && cmp -s %{arctic_selinux_state}/arctic-nix.pp %{_datadir}/selinux/packages/arctic-nix.pp && \
   [ -e %{_sharedstatedir}/selinux/%{selinuxtype}/active/modules/200/arctic-nix ]; then
  : # the same module is installed already
else
%selinux_modules_install -s %{selinuxtype} %{_datadir}/selinux/packages/arctic-nix.pp
fi
rm -rf %{arctic_selinux_state} || :

%postun -n arctic-selinux
%selinux_modules_uninstall -s %{selinuxtype} arctic-nix

%posttrans -n arctic-selinux
%selinux_relabel_post -s %{selinuxtype}

# /etc/skel/.zshrc and .zprofile belong to zsh (%%config(noreplace)). Put Arctic's versions in
# place when zsh's are unmodified; an administrator's own edits are left alone. zsh updates
# then leave them untouched (.rpmnew), and the trigger re-applies after a zsh reinstall.
%global arctic_skel_zsh \
for f in .zshrc .zprofile; do \
  src=%{_datadir}/arctic/skel/$f; dst=%{_sysconfdir}/skel/$f; \
  [ -f "$src" ] || continue; \
  cmp -s "$src" "$dst" 2>/dev/null && continue; \
  if [ -e "$dst" ] && rpm -qf "$dst" >/dev/null 2>&1 && rpm -Vf "$dst" 2>/dev/null | grep -q " $dst\$"; then \
    continue; \
  fi; \
  cp -p "$src" "$dst" || :; \
done

%post -n arctic-desktop-config
systemd-sysusers %{_sysusersdir}/arctic-wallpaper.conf || :
%systemd_post arctic-login-wallpaper.service
%systemd_post arctic-firstboot.service arctic-update-stage.timer
%systemd_post arctic-flatpak-update.timer

%preun -n arctic-desktop-config
%systemd_preun arctic-login-wallpaper.service
%systemd_preun arctic-firstboot.service arctic-update-stage.timer arctic-update-restage.timer arctic-update-stage.service
%systemd_preun arctic-flatpak-update.timer arctic-flatpak-update.service

%posttrans -n arctic-desktop-config
%{arctic_skel_zsh}
# Systems installed before automatic updates existed (0.1) get the new timers once, as the
# presets say (%%systemd_post presets only on a first install). Removing the marker doesn't
# undo a choice: `arctic-update auto off` also sets AUTO=off, which the timer's check honours.
if [ ! -e %{_sharedstatedir}/arctic/.update-presets ]; then
  systemctl --no-reload preset arctic-update-stage.timer snapper-cleanup.timer >/dev/null 2>&1 || :
  mkdir -p %{_sharedstatedir}/arctic && touch %{_sharedstatedir}/arctic/.update-presets || :
fi
# Stream 5: the SSH agent's socket for every user, once (the user preset covers new users).
if [ ! -e %{_sharedstatedir}/arctic/.ssh-agent-preset ]; then
  systemctl --global --no-reload preset gcr-ssh-agent.socket >/dev/null 2>&1 || :
  mkdir -p %{_sharedstatedir}/arctic && touch %{_sharedstatedir}/arctic/.ssh-agent-preset || :
fi
# Stream 5: the same once for the Flatpak update timer (new in 0.3).
if [ ! -e %{_sharedstatedir}/arctic/.flatpak-update-preset ]; then
  systemctl --no-reload preset arctic-flatpak-update.timer >/dev/null 2>&1 || :
  systemctl --global --no-reload preset arctic-flatpak-update.timer >/dev/null 2>&1 || :
  mkdir -p %{_sharedstatedir}/arctic && touch %{_sharedstatedir}/arctic/.flatpak-update-preset || :
fi
# Compile /etc/dconf/db/distro.d (the Arctic GTK/icon/cursor/font defaults).
if [ -x %{_bindir}/dconf ]; then %{_bindir}/dconf update || :; fi
# `neofetch`: link the wrapper unless something (a neofetch package) has the name already.
if [ ! -e %{_bindir}/neofetch ] && [ ! -L %{_bindir}/neofetch ]; then
  ln -s ../libexec/arctic/neofetch %{_bindir}/neofetch || :
fi

%postun -n arctic-desktop-config
%systemd_postun_with_restart arctic-login-wallpaper.service
if [ "$1" -eq 0 ] && [ -x %{_bindir}/dconf ]; then %{_bindir}/dconf update || :; fi

%triggerin -n arctic-desktop-config -- zsh
%{arctic_skel_zsh}

# A neofetch package installed its /usr/bin/neofetch over the wrapper's link (the %%ghost there
# doesn't conflict). Removing that package leaves its file behind, because the path is also
# ours: point the name at the wrapper again.
%triggerpostun -n arctic-desktop-config -- neofetch
if [ "$2" -eq 0 ] && [ "$(readlink %{_bindir}/neofetch 2>/dev/null)" != ../libexec/arctic/neofetch ]; then
  ln -sfn ../libexec/arctic/neofetch %{_bindir}/neofetch || :
fi
:

# Removing zsh (unticked in the installer's app picker) saves the Arctic versions put in place
# above as .zshrc.rpmsave / .zprofile.rpmsave, which useradd would then copy into every new
# home directory. Drop them unless an administrator changed them.
%triggerpostun -n arctic-desktop-config -- zsh
if [ "$2" -eq 0 ]; then
  for f in .zshrc .zprofile; do
    if cmp -s %{_sysconfdir}/skel/$f.rpmsave %{_datadir}/arctic/skel/$f; then
      rm -f %{_sysconfdir}/skel/$f.rpmsave
    fi
  done
fi
:

# The live image sets livesys_session="arctic" in livesys-scripts' /etc/sysconfig/livesys
# (iso/kiwi/config.sh), so removing livesys-scripts, as the installer does, would leave
# /etc/sysconfig/livesys.rpmsave behind on every installed system. Drop it when that line is
# all it holds.
%triggerpostun -n arctic-desktop-config -- livesys-scripts
if [ "$2" -eq 0 ] && [ -f %{_sysconfdir}/sysconfig/livesys.rpmsave ] && \
   ! grep -Evq '^[[:space:]]*(#|$)|^livesys_session="?arctic"?[[:space:]]*$' %{_sysconfdir}/sysconfig/livesys.rpmsave; then
  rm -f %{_sysconfdir}/sysconfig/livesys.rpmsave
fi
:

%post -n arctic-installer
%systemd_post arcticd.socket arcticd.service

%preun -n arctic-installer
%systemd_preun arcticd.socket arcticd.service

%postun -n arctic-installer
%systemd_postun arcticd.socket arcticd.service

%post -n arctic-plymouth-theme
# Make arctic the default splash when the package is first installed (the image build; the
# installer copies that system and rebuilds the initramfs). Updates leave the chosen theme alone.
# The splash is in the initramfs: a changed theme shows once it is rebuilt (the next kernel
# update, or `sudo dracut -f`).
if [ $1 -eq 1 ] && [ -x %{_sbindir}/plymouth-set-default-theme ]; then
  %{_sbindir}/plymouth-set-default-theme arctic || :
fi

%postun -n arctic-plymouth-theme
if [ $1 -eq 0 ] && [ -x %{_sbindir}/plymouth-set-default-theme ]; then
  if [ "$(%{_sbindir}/plymouth-set-default-theme 2>/dev/null)" = arctic ]; then
    %{_sbindir}/plymouth-set-default-theme --reset || :
  fi
fi

# ---------------------------------------------------------------------------------------------
%files -n arctic-release -f release.files
%license LICENSE
%doc packaging/release/README.md
%{_prefix}/lib/os-release
%{_prefix}/lib/arctic-release
%{_prefix}/lib/fedora-release
%{_prefix}/lib/system-release-cpe
%{_sysconfdir}/os-release
%{_sysconfdir}/arctic-release
%{_sysconfdir}/fedora-release
%{_sysconfdir}/redhat-release
%{_sysconfdir}/system-release
%{_sysconfdir}/system-release-cpe
%attr(0644,root,root) %{_prefix}/lib/issue
%config(noreplace) %{_sysconfdir}/issue
%attr(0644,root,root) %{_prefix}/lib/issue.net
%config(noreplace) %{_sysconfdir}/issue.net
%attr(0644,root,root) %{_rpmconfigdir}/macros.d/macros.dist
%dir %{_sysconfdir}/dnf/plugins/copr.d
%config(noreplace) %{_sysconfdir}/dnf/plugins/copr.d/arctic.conf
%dir %{_datadir}/dnf5/libdnf.conf.d
%{_datadir}/dnf5/libdnf.conf.d/20-arctic-defaults.conf
%dir %{_datadir}/dnf5/repos.d
%dir %{_presetdir}
%{_presetdir}/80-arctic.preset
%{_presetdir}/85-display-manager.preset
%{_presetdir}/90-default.preset
%{_presetdir}/99-default-disable.preset
%dir %{_userpresetdir}
%{_userpresetdir}/80-arctic.preset
%{_userpresetdir}/90-default-user.preset
%{_userpresetdir}/99-default-disable.preset

%files -n arctic-logos -f logos.files
%license LICENSE

%files -n arctic-backgrounds
%dir %{_datadir}/backgrounds
%{_datadir}/backgrounds/arctic/
%{_datadir}/backgrounds/default.png
%{_datadir}/backgrounds/default-dark.png

%files -n arctic-fonts
%{_datadir}/fonts/arctic/

# --- stream 6
%files -n arctic-fonts-symbols
%license _build/nerd-symbols/LICENSE
%doc _build/nerd-symbols/README.md
%{_datadir}/fonts/arctic-symbols/
%{_datadir}/fontconfig/conf.avail/66-arctic-nerd-symbols.conf
%{_sysconfdir}/fonts/conf.d/66-arctic-nerd-symbols.conf
# --- end stream 6

%files -n arctic-selinux
%license LICENSE
%dir %{_datadir}/selinux/packages
%doc packaging/selinux/arctic-nix.te packaging/selinux/arctic-nix.fc
%{_datadir}/selinux/packages/arctic-nix.pp
%ghost %verify(not md5 size mode mtime) %{_sharedstatedir}/selinux/%{selinuxtype}/active/modules/200/arctic-nix

%files -n arctic-desktop-config -f desktop-config.files
%license LICENSE
%doc dotfiles/README.md
%{_sysconfdir}/skel/.[!.]*
%dir %{_datadir}/arctic/skel
%{_datadir}/arctic/skel/.[!.]*
%dir %{_sysconfdir}/arctic
%dir %{_sysconfdir}/arctic/mango
%config(noreplace) %{_sysconfdir}/arctic/default-apps
%{_sysconfdir}/profile.d/arctic-graphics.sh
%{_libexecdir}/arctic-nix-system
%{_datadir}/polkit-1/actions/org.arcticlinux.nix.policy
%{_sysconfdir}/profile.d/zz-arctic-nix.sh
%{_prefix}/lib/environment.d/60-arctic-nix.conf
%{_sysconfdir}/profile.d/arctic-ssh-agent.sh
%{_libexecdir}/arctic/arctic-system-helper
%{_unitdir}/arctic-login-wallpaper.service
%{_sysusersdir}/arctic-wallpaper.conf
%{_datadir}/dbus-1/system-services/org.arcticlinux.Wallpaper.service
%{_datadir}/dbus-1/system.d/org.arcticlinux.Wallpaper.conf
%{_datadir}/polkit-1/actions/org.arcticlinux.wallpaper.policy
%{_datadir}/polkit-1/actions/org.arcticlinux.system.policy
%{_datadir}/polkit-1/rules.d/50-arctic-firewalld-read.rules
%{_datadir}/Thunar/sendto/arctic-sendto-localsend.desktop
%dir %{_datadir}/arctic
%dir %{_datadir}/arctic/mango
%{_datadir}/arctic/keys.txt
%{_datadir}/arctic/themes/
%{_datadir}/arctic/themegen/
%dir %{_datadir}/arctic/fastfetch
%{_datadir}/arctic/fastfetch/greeting.jsonc
%{_datadir}/arctic/fastfetch/logo.txt
%dir %{_sysconfdir}/xdg/fastfetch
%config(noreplace) %{_sysconfdir}/xdg/fastfetch/config.jsonc
%ghost %{_bindir}/neofetch
%dir %{_datadir}/arctic/theme-hooks.d
%{_datadir}/arctic/theme-hooks.d/*
%config(noreplace) %{_sysconfdir}/dconf/db/distro.d/10-arctic
%ghost %{_sysconfdir}/dconf/db/distro
%dir %{_localstatedir}/lib/flatpak/overrides
%config(noreplace) %{_localstatedir}/lib/flatpak/overrides/global
%{_prefix}/lib/environment.d/50-arctic-qt.conf
# Stream 5 (system): XDG autostart drop-ins
%dir %{_userunitdir}/mango-session.target.d
%{_userunitdir}/mango-session.target.d/arctic-autostart.conf
%{_userunitdir}/app-*@autostart.service.d/
%{_unitdir}/arctic-firstboot.service
%dir %{_libexecdir}/arctic
%{_libexecdir}/arctic/arctic-firstboot
%{_libexecdir}/arctic/neofetch
%{_unitdir}/arctic-update-stage.service
%{_unitdir}/arctic-update-stage.timer
%{_unitdir}/arctic-update-restage.timer
%{_unitdir}/arctic-flatpak-update.service
%{_unitdir}/arctic-flatpak-update.timer
%{_userunitdir}/arctic-flatpak-update.service
%{_userunitdir}/arctic-flatpak-update.timer
%{_libexecdir}/arctic/arctic-update-helper
%config(noreplace) %{_sysconfdir}/arctic/update.conf
%config(noreplace) %{_sysconfdir}/dnf/libdnf5-plugins/actions.d/arctic-snapper.actions
%config(noreplace) %{_sysconfdir}/dnf/libdnf5-plugins/actions.d/arctic-update.actions
%dir %{_sharedstatedir}/arctic
%ghost %attr(0644,root,root) %verify(not md5 size mtime) %{_sharedstatedir}/arctic/update-status.json
# Stream 4 (capture): the screen-share picker.
%dir %{_sysconfdir}/xdg/xdg-desktop-portal-wlr
%config(noreplace) %{_sysconfdir}/xdg/xdg-desktop-portal-wlr/mango
%dir %{_sysconfdir}/xdg/xdg-desktop-portal
%config(noreplace) %{_sysconfdir}/xdg/xdg-desktop-portal/mango-portals.conf
%{_libexecdir}/arctic/arctic-share-picker

# --- stream 6
%files -n arctic-themes-extra
%license LICENSE
%{_datadir}/arctic/themes-extra/

%files -n arctic-shell
%dir %{_datadir}/arctic
%license LICENSE
%{_bindir}/arctic-shell
%{_bindir}/arctic-shell-ipc
%{_datadir}/arctic/shell/
%{_datadir}/polkit-1/actions/org.arcticlinux.pkexec.dnf.policy

%files -n arctic-settings
%dir %{_datadir}/arctic
%license LICENSE
%doc settings/README.md
%{_bindir}/arctic-settings
%{_datadir}/arctic/settings/
%{_datadir}/applications/org.arcticlinux.Settings.desktop
%{_datadir}/icons/hicolor/scalable/apps/org.arcticlinux.Settings.svg

%files -n arctic-installer
%dir %{_datadir}/arctic
%license LICENSE
%{_bindir}/arcticd
%{_bindir}/arctic-install
%{_bindir}/arctic-installer
%{_datadir}/arctic/catalog/
%{_datadir}/arctic/profiles/
%{_datadir}/arctic/installer-ui/
%{_unitdir}/arcticd.socket
%{_unitdir}/arcticd.service
%{_datadir}/applications/org.arcticlinux.Installer.desktop
%dir %{_localstatedir}/log/arctic-install

# ---- stream 1 (web apps)
%files -n arctic-webapps
%license LICENSE
%{_bindir}/arctic-webapp
%dir %{_libexecdir}/arctic
%{_libexecdir}/arctic/arctic-webapp-host

%files -n arctic-fetch-3d
%license LICENSE
# The 3D greeting, and the system default for its config (the wrapper is %%{_bindir}/arctic-fetch,
# in arctic-desktop-config).
%dir %{_libexecdir}/arctic
%{_libexecdir}/arctic/arctic-fetch-3d
%dir %{_datadir}/arctic
%dir %{_datadir}/arctic/fetch
# noreplace, like update.conf and the other system defaults: the wrapper reads the user's own
# ~/.config/arctic/fetch/config first, so an admin who edited this one keeps their edits.
%config(noreplace) %{_datadir}/arctic/fetch/config

%files -n sddm-wayland-mango
%dir %{_datadir}/arctic
%{_prefix}/lib/sddm/sddm.conf.d/10-arctic.conf
%dir %{_libexecdir}/arctic
%{_libexecdir}/arctic/sddm-compositor-mango
%dir %{_datadir}/arctic/sddm
%{_datadir}/arctic/sddm/greeter.conf

%files -n arctic-sddm-theme
%{_datadir}/sddm/themes/arctic/

%files -n arctic-plymouth-theme
%{_datadir}/plymouth/themes/arctic/
%{_prefix}/lib/dracut/modules.d/90arctic-plymouth/

%files -n arctic-grub-theme
%dir %{_datadir}/arctic
%dir /boot/grub2/themes
/boot/grub2/themes/arctic/
%{_datadir}/arctic/grub-theme/

%files -n arctic-live
%dir %{_datadir}/arctic
%{_libexecdir}/livesys/sessions.d/livesys-arctic
%dir %{_libexecdir}/arctic
%{_libexecdir}/arctic/live-session
%{_libexecdir}/arctic/live-keyboard
%dir %{_datadir}/arctic/mango
%{_datadir}/arctic/mango/live.conf

%files -n arctic-desktop
# metapackage: no files

%changelog
* Sun Oct 04 2026 Arctic Linux <arctic@arcticlinux.org> - 1.2.0-1
- Nix integration, taskbar fixes, two-row Get apps and reliable update checks.

* Sat Oct 03 2026 Arctic Linux <arctic@arcticlinux.org> - 1.1.0-1
- Web-app pages follow desktop light/dark switches without a reload
- Include Chromium for WebRTC calls; recommend it for WhatsApp and honor the
  preview's engine recommendation in terminal installs too
- Explicit Mango portal selection for theme settings, file dialogs and screen capture
- Fish and Nautilus defaults, installable WhatsApp previews, accelerated web-app playback

* Tue Sep 29 2026 Arctic Linux <arctic@arcticlinux.org> - 1.0.0-1
- Arctic Linux 1.0: the first stable release, the 0.3 desktop with its fixes
- The 3D terminal greeting (arctic-fetch-3d) is its own x86_64 package, required by
  arctic-desktop-config; it links as a PIE with Fedora's hardening flags
- The shortcut sheet (Super + /) and the theme recover from a failed file read instead of
  coming up empty

* Mon Sep 28 2026 Arctic Linux <arctic@arcticlinux.org> - 0.3.0-1
- Get apps opens to a chooser: Flathub apps, Fedora packages, web apps, terminal apps and a
  console; Remove apps lists what you installed per source and shows every package a removal
  takes with it; Delete on a launcher app removes it
- Web apps: arctic-webapp (Go) turns any website into an app with its own window, icon, sign-in
  and scope, in the new arctic-webapps package (arctic-webapp-host on WebKitGTK 6.0, with a
  Chromium-family runtime for protected video and calls)
- Every bar item opens an Arctic menu (Wi-Fi and network, Bluetooth with the shell's own pairing
  agent, sound, battery and power, calendar, media, brightness, tray menus); Quick Settings on
  Super + A; the shell is the notification server, with a notification centre and do not disturb
- Super + B opens the browser (Super + W is free); Super + Shift + S takes a screenshot; text and
  QR codes from the screen, a colour picker, screen recording, a screen-share picker, clipboard
  history and emoji panels, Alt + Tab, a drop-down terminal
- Night light, keep awake, XDG autostart, printing and scanning, USB drives and phones, Flatpak
  and firmware updates, the laptop lid and screen modes, Users, Sharing, and more Settings pages
- A command menu on Super + Alt + Space, launcher search for settings, windows, files and units,
  more OSD kinds, automatic light and dark, a theme gallery, an Accessibility page, a first-login
  welcome, reminders and user hooks

* Mon Sep 28 2026 Arctic Linux <arctic@arcticlinux.org> - 0.2.1-1
- The repository moved to github.com/yuvalkolodkingal/Arctic-Linux: the package
  repository is now https://yuvalkolodkingal.github.io/Arctic-Linux/ (Pages doesn't
  redirect, so 0.2.0 systems need the one-line fix in the release notes)
- Installer: a finished install is never thrown away because the encrypted disk
  couldn't be closed at the end; processes left in the new system and copies of its
  mounts in other mount namespaces are released first, closing is retried; dnf and
  flatpak retry network failures
- Settings: Wallhaven browser, add/rename/delete your own wallpapers, a display
  arrangement editor
- fastfetch in the Arctic design (colours follow the theme) and a neofetch command

* Sun Sep 27 2026 Arctic Linux <arctic@arcticlinux.org> - 0.2.0-1
- Arctic Linux 0.2: arctic-release enables the signed Arctic package repository (GitHub
  Pages; stable channel on, testing channel off) and ships its public key
- Every build has its own Release, 1.<UTC commit time>.<UTC build time>.git<commit>,
  so builds of newer code update the ones before them
- arctic-plymouth-theme sets the default splash on the first install only; arctic-selinux
  skips reinstalling an unchanged module on updates

* Sun Sep 27 2026 Arctic Linux <arctic@arcticlinux.org> - 0.1.0-1
- Arctic Linux 0.1: first build of all subpackages from one spec
