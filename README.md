# Arctic Linux

A calm, keyboard-first desktop on **Fedora 44** and the **Mango** tiling Wayland window manager,
with an identity drawn from the arctic fox. One live USB: boot it to **Try Arctic Linux** or
**Install Arctic Linux**. The installer is a step-by-step wizard with a Ninite-style app picker,
and it only downloads the apps you pick.

- **Desktop:** Mango, a Quickshell shell (bar, launcher with calculator and commands, wallpaper
  picker, Get apps console, OSD, lock screen), Arctic Settings (`Super + S`), mako, kitty + zsh with the animated `arctic-fetch`
  fox, two themes (Winter and Polar night) switched with `Super + Shift + T`.
- **Default apps (all swappable in the installer):** Zen, Zed, kitty, zsh, yazi, Thunar,
  Collabora Office, VLC. Nix and Flatpak come preinstalled.
- **Installer:** a Go engine (`arcticd`) behind a Quickshell wizard. Disk encryption is on by
  default (LUKS2 + btrfs).

## Try it

Download the ISO from the [releases](https://github.com/yuvalkolodkingal/O-Tism/releases), write
it to a USB stick (4 GB or more), for example with Fedora Media Writer or
`sudo dd if=Arctic-Linux-0.2-x86_64.iso of=/dev/sdX bs=4M status=progress oflag=sync`, and boot it.

## Updates

Fedora's packages come from Fedora's repositories. Arctic's own packages (desktop, shell, installer,
branding, Mango) come from the signed **Arctic package repository** on this project's GitHub Pages
site, https://yuvalkolodkingal.github.io/O-Tism/, which `arctic-release` sets up with its key:

| Channel | Built from | On an installed system |
|---|---|---|
| `stable` | every push to `main` | on |
| `testing` | every push to the development branch (`claude/busy-goodall-j42hmi`) | off; `sudo dnf config-manager setopt arctic-testing.enabled=1` to follow it, `=0` to go back |

Every build's Release carries its commit's UTC time, its UTC build time and the commit
(`…-0.2.0-1.20260928030512.202609280310.gitabc1234.fc44`), so builds of newer code update the
ones before them, including the packages an ISO installed. Each push to `main` is therefore a
full update of Arctic's packages (about 9 MB) for every stable system.
`.github/workflows/repo.yml` builds, signs, checks with dnf5 and publishes each push; the
details are in `docs/BUILD-SPEC.md` §9. Installed Arctic Linux 0.1? See the
[0.2.0 release notes](docs/wiki/Release-Notes.md#upgrading-from-01) to switch it to the repository.

## Repository

| Path | What |
|---|---|
| `design/` | Design system: tokens, brand book, guidelines, fonts, logos, icons, wallpapers |
| `shell/` | The desktop shell (Quickshell/QML), grown from a personal Quickshell setup |
| `dotfiles/` | The home directory defaults (`/etc/skel`) and `arctic-*` helper commands |
| `installer-ui/` | The installer wizard (Quickshell/QML) |
| `settings/` | Arctic Settings, the settings app (Quickshell/QML, `Super + S`) |
| `cmd/`, `internal/` | The installer engine (Go, standard library only) |
| `modules/`, `profiles/` | The app catalog and install profiles |
| `branding/` | Login screen (SDDM), boot menu (GRUB), boot splash (Plymouth), logos |
| `packaging/` | RPM specs (`arctic-linux.spec`, `mangowm.spec`) and system files |
| `live/`, `iso/kiwi/` | The live session and the kiwi-ng ISO description |
| `tools/` | `build-rpms.sh`, `build-iso.sh`, `test-iso.sh`, `test-install.sh`, `publish-repo.sh` and `test-repo.sh` (the package repository) |
| `docs/` | `PLAN.md` (why) and `BUILD-SPEC.md` (the contracts between components) |

## Build

Needs Docker (the builds run in Fedora 44 containers; the ISO build needs `--privileged`).

```sh
tools/build-rpms.sh     # RPMs → out/repo
tools/build-iso.sh      # live ISO → out/iso (about 20 minutes, ~15 GB scratch)
tools/test-iso.sh --firmware uefi --mode try    # boot it in QEMU, screenshots in out/test
tools/test-install.sh --firmware uefi           # install to a VM disk, boot it, log in (~1.5 h without KVM)
```

CI (`.github/workflows/ci.yml`) runs the Go, Python and Node tests, shellcheck and qmllint, builds
the RPMs and checks an unsigned test repository with dnf5. `.github/workflows/iso.yml` builds the
ISO and publishes a release for `v*` tags; `.github/workflows/repo.yml` publishes the package
repository.
