# Based on Fedora 44's scenefx-0.5-1 spec, Damian Daniel <damian@danielovci.net>.
# Retain Fedora's runtime/devel names and ABI; Arctic changes forced-software
# completion only. Release 2 outranks the observed Fedora 0.5-1 packages.
%global scenefx_sha256 0fa8ecca0e310f813efd052624c5ed7d9153d6a0fdead5cc957d34c07f9a86c6

Name:           scenefx
Version:        0.5
Release:        2%{?arctic_snapshot}%{?dist}
Summary:        A drop-in replacement for the wlroots scene API with eye-candy effects

License:        MIT
URL:            https://github.com/wlrfx/scenefx
Source0:        %{url}/archive/refs/tags/%{version}/%{name}-%{version}.tar.gz
Source1:        test_safe_completion.py
Patch0:         scenefx-safe-software-completion.patch
Provides:       scenefx(arctic-software-sync) = %{version}

BuildRequires:  gcc
BuildRequires:  meson
BuildRequires:  python3
BuildRequires:  pkgconfig(wayland-server) >= 1.24.0
BuildRequires:  pkgconfig(wayland-protocols)
BuildRequires:  pkgconfig(wayland-scanner)
BuildRequires:  pkgconfig(wlroots-0.20) >= 0.20.0
BuildRequires:  pkgconfig(libdrm) >= 2.4.129
BuildRequires:  pkgconfig(xkbcommon) >= 1.8.0
BuildRequires:  pkgconfig(pixman-1) >= 0.43.0
BuildRequires:  pkgconfig(egl)
BuildRequires:  pkgconfig(glesv2)
BuildRequires:  pkgconfig(gbm)
BuildRequires:  pkgconfig(lcms2)

%description
scenefx is a drop-in replacement for the wlroots scene API that allows
Wayland compositors to render surfaces with eye-candy effects -- including
blur, drop shadows, and rounded corners -- while keeping the simplicity of
the standard wlroots scene API. It is used by compositors such as SwayFX,
MangoWC, and mwc.

%package devel
Summary:        Development files for %{name}
Requires:       %{name}%{?_isa} = %{version}-%{release}
Requires:       pkgconfig(wlroots-0.20)

%description devel
Header files and pkgconfig data needed to build Wayland compositors
against scenefx.

%prep
echo "%{scenefx_sha256}  %{SOURCE0}" | sha256sum -c --strict -
%autosetup -p1 -n %{name}-%{version}

%build
%meson -Dexamples=false
%meson_build

%install
%meson_install

%check
# Compile and exercise the actual patched submit function with controlled GL/EGL
# calls, including timeline failures and exact Safe-mode versus hardware ordering.
python3 %{SOURCE1} --source .

%files
%license LICENSE
%doc README.md
%{_libdir}/libscenefx-%{version}.so

%files devel
%{_libdir}/pkgconfig/scenefx-%{version}.pc
%{_includedir}/scenefx-%{version}/

%changelog
* Sun Oct 11 2026 Arctic Linux <arctic@arcticlinux.org> - 0.5-2
- Complete frames in the existing forced-software, non-timeline Safe path
- Preserve Fedora's MIT sources, names, public API and 0.5 library ABI

* Mon Sep 07 2026 Damian Daniel <damian@danielovci.net> - 0.5-1
- Initial packaging
