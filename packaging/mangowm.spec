# MangoWM for Arctic Linux.
# Forked from Terra's anda/desktops/mangowm/mangowm.spec (Olivia <git@olivia.sh>) with the
# fixes from docs/PLAN.md §12: built against Fedora's own wlroots 0.20 and scenefx 0.5,
# portal/chooser Recommends, and /etc/mango/config.conf kept as %%config(noreplace).
#
# Arctic never edits /etc/mango/config.conf: users get ~/.config/mango/config.conf from
# /etc/skel (arctic-desktop-config), which mango reads instead (the two are not merged).

%global mangowc_ver 0.12.5-1

Name:           mangowm
Version:        0.17.3
# tools/build-rpms.sh defines arctic_snapshot as .<UTC commit time>.<UTC build time>.git<commit>,
# so builds of newer commits are newer packages (docs/BUILD-SPEC.md §9).
Release:        1%{?arctic_snapshot}%{?dist}
Summary:        Lightweight, high-performance Wayland compositor built on dwl
License:        GPL-3.0-or-later AND MIT AND X11 AND CC0-1.0
URL:            https://github.com/mangowm/mango
Source0:        %{url}/archive/refs/tags/%{version}.tar.gz#/mango-%{version}.tar.gz
Patch0:         mango-client-geometry-events.patch

BuildRequires:  meson
BuildRequires:  gcc
BuildRequires:  findutils
BuildRequires:  pkgconfig(wlroots-0.20) >= 0.20.0
BuildRequires:  pkgconfig(scenefx-0.5) >= 0.5.0
BuildRequires:  pkgconfig(wayland-server) >= 1.23.1
BuildRequires:  pkgconfig(wayland-client)
BuildRequires:  pkgconfig(wayland-protocols)
BuildRequires:  wayland-devel
BuildRequires:  pkgconfig(libinput) >= 1.27.1
BuildRequires:  pkgconfig(xkbcommon)
BuildRequires:  pkgconfig(libpcre2-8)
BuildRequires:  pkgconfig(pixman-1)
BuildRequires:  pkgconfig(libcjson)
BuildRequires:  pkgconfig(pangocairo)
BuildRequires:  pkgconfig(libdrm)
# Xwayland support (meson option xwayland=enabled)
BuildRequires:  pkgconfig(xcb)
BuildRequires:  pkgconfig(xcb-icccm)
BuildRequires:  pkgconfig(xcb-randr)
BuildRequires:  xorg-x11-server-Xwayland-devel

# mango-portals.conf prefers gtk + wlr; wlr needs a chooser (slurp).
Recommends:     xdg-desktop-portal-wlr
Recommends:     xdg-desktop-portal-gtk
Recommends:     slurp
Recommends:     xorg-x11-server-Xwayland

Conflicts:      mangowc < %{mangowc_ver}
Obsoletes:      mangowc < %{mangowc_ver}
Provides:       mangowc = %{mangowc_ver}

%description
MangoWM is a modern, lightweight, high-performance Wayland compositor built on
dwl, crafted for speed, flexibility and a customizable desktop experience.
It provides the "mango" compositor, the "mmsg" IPC client, a wayland-sessions
entry, portal preferences and mango-session.target for systemd user units.

%prep
%autosetup -n mango-%{version} -p1

%build
%meson -Dxwayland=enabled
%meson_build

%install
%meson_install

%check
# The compositor validates its own default config without a display (-c must come before -p).
%{buildroot}%{_bindir}/mango -c %{buildroot}%{_sysconfdir}/mango/config.conf -p

%files
%license LICENSE
%doc README.md
%{_bindir}/mango
%{_bindir}/mmsg
%dir %{_sysconfdir}/mango
%config(noreplace) %{_sysconfdir}/mango/config.conf
%{_datadir}/wayland-sessions/mango.desktop
%dir %{_datadir}/xdg-desktop-portal
%{_datadir}/xdg-desktop-portal/mango-portals.conf
%{_mandir}/man1/mmsg.1*
%{_userunitdir}/mango-session.target

%changelog
* Sun Sep 27 2026 Arctic Linux <arctic@arcticlinux.org> - 0.17.3-1
- Arctic Linux build: wlroots 0.20 + scenefx 0.5 from Fedora 44,
  config.conf as %%config(noreplace), portal Recommends
