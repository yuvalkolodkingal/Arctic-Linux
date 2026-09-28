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
#   sddm-wayland-mango     packaging/sddm-wayland-mango/
#   arctic-sddm-theme      branding/sddm/arctic/
#   arctic-plymouth-theme  branding/plymouth/arctic/ (+ branding/plymouth/dracut/, the initrd hook)
#   arctic-grub-theme      branding/grub/arctic/
#   arctic-live            live/
#   arctic-desktop         (metapackage)

%global dist_version    44
%global arctic_version  0.2
%global selinuxtype     targeted
# Go binaries are built with the Go linker (CGO_ENABLED=0); no separate debuginfo.
%global debug_package   %{nil}

Name:           arctic-linux
Version:        0.2.1
# tools/build-rpms.sh defines arctic_snapshot as .<UTC commit time>.<UTC build time>.git<commit>,
# so builds of newer commits are newer packages (docs/BUILD-SPEC.md §9).
Release:        1%{?arctic_snapshot}%{?dist}
Summary:        Arctic Linux: a Fedora-based desktop with the Mango window manager
License:        MIT AND LGPL-2.1-or-later AND OFL-1.1
URL:            https://github.com/yuvalkolodkingal/Arctic-Linux
Source0:        arctic-linux-%{version}.tar.gz

ExclusiveArch:  x86_64

BuildRequires:  golang >= 1.22
BuildRequires:  librsvg2-tools
BuildRequires:  selinux-policy-devel
BuildRequires:  make
BuildRequires:  systemd-rpm-macros
BuildRequires:  desktop-file-utils
BuildRequires:  findutils
BuildRequires:  tar
# %%check: packaging/updates' unit tests (arctic-update's helper)
BuildRequires:  python3
# The theme engine renders the static themes in %%build; %%check runs its tests.
# %%py_byte_compile
BuildRequires:  python3-rpm-macros
BuildRequires:  python3-pillow

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
Requires:       mangowm >= 0.17.1
Requires:       arctic-backgrounds = %{version}-%{release}
Requires:       arctic-fonts = %{version}-%{release}
Requires:       arctic-logos = %{version}-%{release}
Requires:       bash
Requires:       python3
# arctic-themegen: colours from wallpapers
Requires:       python3-pillow
%{?systemd_requires}
# kitty and zsh are the default terminal and shell, but the installer lets people pick others
# and removes the unticked ones (dnf remove --no-autoremove), so they must be weak deps.
Recommends:     zsh
Recommends:     kitty
Requires:       libnotify
Requires:       procps-ng
Requires:       util-linux
Requires:       librsvg2-tools
Requires:       mako
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

%description -n arctic-desktop-config
The Arctic Linux desktop configuration: the Mango configuration, the Winter and Polar night
theme files and the keyboard cheat sheet in /usr/share/arctic (new home directories link to
them, so updates reach everyone), the home directory defaults in /etc/skel (kitty, zsh, GTK,
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
# pkexec, for Get apps
Requires:       polkit
Requires:       arctic-fonts = %{version}-%{release}
# Stream 3a (bar menus): the Bluetooth pairing agent and battery.py talk D-Bus with
# python3-dbus and a GLib main loop; gdbus checks for the power-profiles service; ddcutil
# sets external monitors' brightness. (The network menu hides itself without nmcli.)
Requires:       python3-dbus
Requires:       python3-gobject-base
Requires:       glib2
Recommends:     ddcutil

%description -n arctic-shell
The Arctic Linux desktop shell, written for Quickshell: top bar with its own menus (network
and Wi-Fi, Bluetooth with a pairing agent, sound, battery and power mode, calendar, media,
tray menus) and Quick Settings, launcher, wallpaper picker, the get-apps console, on-screen
display, lock screen and the live-session welcome card.
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
updates, power and lock, startup apps. Changes go to ~/.config/mango/settings.conf and the
Arctic helpers; nothing needs root. Start it with arctic-settings (Super+S).

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
%package -n sddm-wayland-mango
Summary:        SDDM greeter on the Mango Wayland compositor
BuildArch:      noarch
Provides:       sddm-greeter-displayserver
Conflicts:      sddm-greeter-displayserver
Requires:       sddm
Requires:       mangowm >= 0.17.1
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
Requires:       sddm-wayland-mango = %{version}-%{release}
Requires:       arctic-sddm-theme = %{version}-%{release}
Requires:       arctic-plymouth-theme = %{version}-%{release}
Requires:       arctic-grub-theme = %{version}-%{release}
Requires:       mangowm >= 0.17.1
Requires:       sddm
# Swappable in the installer's app picker (terminal, shell, file manager, video): weak deps,
# so unticking one doesn't remove this metapackage.
Recommends:     kitty
Recommends:     kitty-shell-integration
Recommends:     zsh
Recommends:     Thunar
Recommends:     vlc
Requires:       fastfetch
Requires:       mako
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
Requires:       pavucontrol
Requires:       network-manager-applet
Requires:       NetworkManager-wifi
Requires:       blueman
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

%description -n arctic-desktop
Pulls in everything an Arctic Linux desktop needs: Mango, SDDM with the arctic theme and
the Mango greeter, the Quickshell shell, the desktop configuration, branding, audio,
networking, portals, Flatpak and Nix.

# =============================================================================================
%prep
%autosetup -n arctic-linux-%{version}

%build
# ---- Go: arcticd + arctic-install (stdlib only, or vendored modules) ----
if [ -f go.mod ]; then
  export GOTOOLCHAIN=local CGO_ENABLED=0 GOPROXY=off GOFLAGS="-buildmode=pie -trimpath"
  if [ -d vendor ]; then GOFLAGS="$GOFLAGS -mod=vendor"; fi
  export GOFLAGS
  export GOCACHE="$PWD/_build/gocache" GOPATH="$PWD/_build/gopath"
  mkdir -p _build/bin
  for cmd in arcticd arctic-install; do
    go build -ldflags "-B gobuildid" -o "_build/bin/$cmd" "./cmd/$cmd"
  done
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

# ---- Wallpapers: SVG → 3840×2160 PNG ----
mkdir -p _build/backgrounds
for svg in design/wallpapers/*.svg; do
  cp -p "$svg" _build/backgrounds/
  rsvg-convert -w 3840 -h 2160 -o "_build/backgrounds/$(basename "$svg" .svg).png" "$svg"
done

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
# Automatic updates (arctic-update, in /usr/bin with the helpers above) and snapshots.
install -Dpm 0644 packaging/systemd/arctic-update-stage.service %{buildroot}%{_unitdir}/arctic-update-stage.service
install -Dpm 0644 packaging/systemd/arctic-update-stage.timer %{buildroot}%{_unitdir}/arctic-update-stage.timer
install -Dpm 0644 packaging/systemd/arctic-update-restage.timer %{buildroot}%{_unitdir}/arctic-update-restage.timer
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
# Get apps: pkexec dnf5 with the password kept for a few minutes.
install -Dpm 0644 packaging/polkit/org.arcticlinux.pkexec.dnf.policy \
  %{buildroot}%{_datadir}/polkit-1/actions/org.arcticlinux.pkexec.dnf.policy

# ---------------------------------------------------------------- arctic-settings
# /usr/bin/arctic-settings was installed with the other helpers (dotfiles/.local/bin).
install -d %{buildroot}%{_datadir}/arctic/settings
# tests/ and dev/ (headless screenshots) are development-only.
tar -C settings --exclude=./tests --exclude=./dev --exclude=./README.md -cf - . | tar -C %{buildroot}%{_datadir}/arctic/settings -xf -
chmod 0755 %{buildroot}%{_datadir}/arctic/settings/scripts/arctic_settings.py
desktop-file-install --dir=%{buildroot}%{_datadir}/applications packaging/settings/org.arcticlinux.Settings.desktop
install -Dpm 0644 packaging/settings/org.arcticlinux.Settings.svg \
  %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/org.arcticlinux.Settings.svg

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
# Settings' backend: the file formats it reads and writes (uses `mango -p` when installed).
python3 -m unittest discover -s settings/tests -p 'test_*.py'
for s in %{buildroot}%{_libexecdir}/arctic/* %{buildroot}%{_libexecdir}/livesys/sessions.d/livesys-arctic \
         %{buildroot}%{_bindir}/arctic-shell %{buildroot}%{_bindir}/arctic-installer %{buildroot}%{_bindir}/arctic-update \
         %{buildroot}%{_datadir}/arctic/theme-hooks.d/*; do
  case "$(head -n1 "$s")" in
    *python*) python3 -c 'import ast,sys; ast.parse(open(sys.argv[1]).read())' "$s" ;;
    *) bash -n "$s" ;;
  esac
done
# arctic-update's file handling (update.conf, dnf5's offline state, the status file).
python3 -m unittest discover -s packaging/updates -p 'test_*.py'
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
%systemd_post arctic-firstboot.service arctic-update-stage.timer

%preun -n arctic-desktop-config
%systemd_preun arctic-firstboot.service arctic-update-stage.timer arctic-update-restage.timer arctic-update-stage.service

%posttrans -n arctic-desktop-config
%{arctic_skel_zsh}
# Systems installed before automatic updates existed (0.1) get the new timers once, as the
# presets say (%%systemd_post presets only on a first install). Removing the marker doesn't
# undo a choice: `arctic-update auto off` also sets AUTO=off, which the timer's check honours.
if [ ! -e %{_sharedstatedir}/arctic/.update-presets ]; then
  systemctl --no-reload preset arctic-update-stage.timer snapper-cleanup.timer >/dev/null 2>&1 || :
  mkdir -p %{_sharedstatedir}/arctic && touch %{_sharedstatedir}/arctic/.update-presets || :
fi
# Compile /etc/dconf/db/distro.d (the Arctic GTK/icon/cursor/font defaults).
if [ -x %{_bindir}/dconf ]; then %{_bindir}/dconf update || :; fi
# `neofetch`: link the wrapper unless something (a neofetch package) has the name already.
if [ ! -e %{_bindir}/neofetch ] && [ ! -L %{_bindir}/neofetch ]; then
  ln -s ../libexec/arctic/neofetch %{_bindir}/neofetch || :
fi

%postun -n arctic-desktop-config
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
%{_unitdir}/arctic-firstboot.service
%dir %{_libexecdir}/arctic
%{_libexecdir}/arctic/arctic-firstboot
%{_libexecdir}/arctic/neofetch
%{_unitdir}/arctic-update-stage.service
%{_unitdir}/arctic-update-stage.timer
%{_unitdir}/arctic-update-restage.timer
%{_libexecdir}/arctic/arctic-update-helper
%config(noreplace) %{_sysconfdir}/arctic/update.conf
%config(noreplace) %{_sysconfdir}/dnf/libdnf5-plugins/actions.d/arctic-snapper.actions
%config(noreplace) %{_sysconfdir}/dnf/libdnf5-plugins/actions.d/arctic-update.actions
%dir %{_sharedstatedir}/arctic
%ghost %attr(0644,root,root) %verify(not md5 size mtime) %{_sharedstatedir}/arctic/update-status.json

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
