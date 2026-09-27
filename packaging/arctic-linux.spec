# Arctic Linux: every Arctic package from one spec and one source tarball (docs/BUILD-SPEC.md §2).
#
# Source0 is `git archive --prefix=arctic-linux-%%{version}/` of the repository (made by
# tools/build-rpms.sh, which also includes uncommitted work). The subpackages install straight
# from the repository tree:
#
#   arctic-release         packaging/release/                  os-release, macros.dist, presets
#   arctic-logos           branding/logos/ (install-path tree) system-logos
#   arctic-backgrounds     design/wallpapers/*.svg (+ PNG rendered here)
#   arctic-fonts           branding/fonts/Figtree-*.ttf (else design/fonts/Figtree-*.woff2)
#   arctic-selinux         packaging/selinux/arctic-nix.{te,fc} (compiled here)
#   arctic-desktop-config  dotfiles/ → /etc/skel, dotfiles/.local/bin → /usr/bin
#   arctic-shell           shell/ → /usr/share/arctic/shell
#   arctic-installer       cmd/ + internal/ (Go), modules/, profiles/, installer-ui/, packaging/systemd/
#   sddm-wayland-mango     packaging/sddm-wayland-mango/
#   arctic-sddm-theme      branding/sddm/arctic/
#   arctic-plymouth-theme  branding/plymouth/arctic/
#   arctic-grub-theme      branding/grub/arctic/
#   arctic-live            live/
#   arctic-desktop         (metapackage)

%global dist_version    44
%global arctic_version  0.1
%global selinuxtype     targeted
# Go binaries are built with the Go linker (CGO_ENABLED=0); no separate debuginfo.
%global debug_package   %{nil}

Name:           arctic-linux
Version:        0.1.0
Release:        1%{?dist}
Summary:        Arctic Linux: a Fedora-based desktop with the Mango window manager
License:        MIT AND LGPL-2.1-or-later AND OFL-1.1
URL:            https://github.com/yuvalkolodkingal/O-Tism
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
(Fedora's policy plus Arctic's: SDDM, the installer socket, nix-daemon) and dnf defaults.
It replaces fedora-release; Fedora's repositories (fedora-repos) stay in use.

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
Requires:       fastfetch
Requires:       jetbrains-mono-fonts-all
Recommends:     waybar
Recommends:     fuzzel
Recommends:     lxqt-policykit
Recommends:     network-manager-applet

%description -n arctic-desktop-config
The Arctic Linux home directory defaults (/etc/skel: Mango, kitty, zsh, GTK, the Winter and
Polar night themes), the arctic-* helper commands in /usr/bin, the keyboard cheat sheet,
the theme files in /usr/share/arctic/themes and /etc/arctic/default-apps.

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
Requires:       arctic-fonts = %{version}-%{release}

%description -n arctic-shell
The Arctic Linux desktop shell, written for Quickshell: top bar, launcher, wallpaper picker,
the get-apps console, on-screen display, lock screen and the live-session welcome card.
Start it with arctic-shell; arctic-shell-ipc calls into a running shell.

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
amber dots, and the disk passphrase prompt. Installing it makes it the default theme (the
initramfs is not rebuilt here).

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
full screen when the boot menu's "Install Arctic Linux" entry was chosen.
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
Recommends:     waybar
Recommends:     lxqt-policykit
Recommends:     adwaita-cursor-theme

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
install -d %{buildroot}%{_sysconfdir}/skel
tar -C dotfiles --exclude=./install.sh --exclude=./README.md --exclude=./.local/bin \
    --exclude=./.zshrc --exclude=./.zprofile -cf - . \
  | tar -C %{buildroot}%{_sysconfdir}/skel -xf -
# zsh owns /etc/skel/.zshrc and .zprofile: Arctic's versions are kept here and copied over
# zsh's (unmodified) ones by the %%posttrans / %%triggerin scriptlets below.
install -d %{buildroot}%{_datadir}/arctic/skel
for f in .zshrc .zprofile; do
  if [ -f "dotfiles/$f" ]; then install -pm 0644 "dotfiles/$f" %{buildroot}%{_datadir}/arctic/skel/; fi
done
# The starting theme (dotfiles/install.sh does the same for a home directory).
ln -sfn themes/polar-night %{buildroot}%{_sysconfdir}/skel/.config/arctic/current
echo polar-night > %{buildroot}%{_sysconfdir}/skel/.config/arctic/theme
install -d %{buildroot}%{_bindir}
install -pm 0755 dotfiles/.local/bin/* %{buildroot}%{_bindir}/
install -Dpm 0644 dotfiles/.local/share/arctic/keys.txt %{buildroot}%{_datadir}/arctic/keys.txt
install -d %{buildroot}%{_datadir}/arctic/themes
cp -a dotfiles/.config/arctic/themes/. %{buildroot}%{_datadir}/arctic/themes/
install -Dpm 0644 packaging/desktop/default-apps %{buildroot}%{_sysconfdir}/arctic/default-apps
install -d %{buildroot}%{_sysconfdir}/arctic/mango
install -Dpm 0644 packaging/desktop/arctic-graphics.sh %{buildroot}%{_sysconfdir}/profile.d/arctic-graphics.sh
# arctic-shell, arctic-shell-ipc and arctic-installer belong to their own subpackages.
(cd dotfiles/.local/bin && ls) | grep -vxE 'arctic-shell|arctic-shell-ipc|arctic-installer' \
  | sed 's,^,%{_bindir}/,' > desktop-config.files

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

# ---------------------------------------------------------------- arctic-grub-theme
install -d %{buildroot}/boot/grub2/themes/arctic %{buildroot}%{_datadir}/arctic/grub-theme
cp -a branding/grub/arctic/. %{buildroot}/boot/grub2/themes/arctic/
cp -a branding/grub/arctic/. %{buildroot}%{_datadir}/arctic/grub-theme/

# ---------------------------------------------------------------- arctic-live
install -Dpm 0755 live/livesys-arctic %{buildroot}%{_libexecdir}/livesys/sessions.d/livesys-arctic
install -Dpm 0755 live/live-session %{buildroot}%{_libexecdir}/arctic/live-session
install -Dpm 0644 live/live.conf %{buildroot}%{_datadir}/arctic/mango/live.conf

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/org.arcticlinux.Installer.desktop
for s in %{buildroot}%{_libexecdir}/arctic/* %{buildroot}%{_libexecdir}/livesys/sessions.d/livesys-arctic \
         %{buildroot}%{_bindir}/arctic-shell %{buildroot}%{_bindir}/arctic-installer; do
  case "$(head -n1 "$s")" in
    *python*) python3 -c 'import ast,sys; ast.parse(open(sys.argv[1]).read())' "$s" ;;
    *) bash -n "$s" ;;
  esac
done
test -f %{buildroot}%{_datadir}/sddm/themes/arctic/metadata.desktop || \
  { echo "error: branding/sddm/arctic has no metadata.desktop" >&2; exit 1; }
test -f %{buildroot}%{_datadir}/plymouth/themes/arctic/arctic.plymouth || \
  { echo "error: branding/plymouth/arctic has no arctic.plymouth" >&2; exit 1; }
test -f %{buildroot}/boot/grub2/themes/arctic/theme.txt || \
  { echo "error: branding/grub/arctic has no theme.txt" >&2; exit 1; }
test -f %{buildroot}%{_datadir}/pixmaps/system-logo-white.png || \
  { echo "error: branding/logos has no usr/share/pixmaps/system-logo-white.png" >&2; exit 1; }
# Mango configs: validated when mangowm is installed in the build root (tools/build-rpms.sh
# installs the freshly built one); `mango -c FILE -p` rejects unknown keys.
if command -v mango >/dev/null 2>&1; then
  mango -c %{buildroot}%{_datadir}/arctic/sddm/greeter.conf -p
  mango -c %{buildroot}%{_datadir}/arctic/mango/live.conf -p
  home="$PWD/_build/home"; rm -rf "$home"; mkdir -p "$home"
  cp -a %{buildroot}%{_sysconfdir}/skel/. "$home/"
  HOME="$home" mango -c "$home/.config/mango/config.conf" -p
fi

# ---------------------------------------------------------------------------------------------
%pre -n arctic-selinux
%selinux_relabel_pre -s %{selinuxtype}

%post -n arctic-selinux
%selinux_modules_install -s %{selinuxtype} %{_datadir}/selinux/packages/arctic-nix.pp

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
%systemd_post arctic-firstboot.service

%preun -n arctic-desktop-config
%systemd_preun arctic-firstboot.service

%posttrans -n arctic-desktop-config
%{arctic_skel_zsh}

%triggerin -n arctic-desktop-config -- zsh
%{arctic_skel_zsh}

%post -n arctic-installer
%systemd_post arcticd.socket arcticd.service

%preun -n arctic-installer
%systemd_preun arcticd.socket arcticd.service

%postun -n arctic-installer
%systemd_postun arcticd.socket arcticd.service

%post -n arctic-plymouth-theme
# Make arctic the default splash; the initramfs is rebuilt by the image build / installer.
if [ -x %{_sbindir}/plymouth-set-default-theme ]; then
  %{_sbindir}/plymouth-set-default-theme arctic || :
fi

%postun -n arctic-plymouth-theme
if [ $1 -eq 0 ] && [ -x %{_sbindir}/plymouth-set-default-theme ]; then
  if [ "$(%{_sbindir}/plymouth-set-default-theme 2>/dev/null)" = arctic ]; then
    %{_sbindir}/plymouth-set-default-theme --reset || :
  fi
fi

# ---------------------------------------------------------------------------------------------
%files -n arctic-release
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
%{_datadir}/arctic/keys.txt
%{_datadir}/arctic/themes/
%{_unitdir}/arctic-firstboot.service
%dir %{_libexecdir}/arctic
%{_libexecdir}/arctic/arctic-firstboot

%files -n arctic-shell
%dir %{_datadir}/arctic
%license LICENSE
%{_bindir}/arctic-shell
%{_bindir}/arctic-shell-ipc
%{_datadir}/arctic/shell/

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
%dir %{_datadir}/arctic/mango
%{_datadir}/arctic/mango/live.conf

%files -n arctic-desktop
# metapackage: no files

%changelog
* Sun Sep 27 2026 Arctic Linux <arctic@arcticlinux.org> - 0.1.0-1
- Arctic Linux 0.1: first build of all subpackages from one spec
