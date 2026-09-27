# Arctic Linux

A calm, keyboard-first desktop on **Fedora 44** and the **Mango** tiling Wayland window manager,
with an identity drawn from the arctic fox. One live USB: boot it to **Try Arctic Linux** or
**Install Arctic Linux**. The installer is a step-by-step wizard with a Ninite-style app picker,
and it only downloads the apps you pick.

- **Desktop:** Mango, a Quickshell shell (bar, launcher with calculator and commands, wallpaper
  picker, Get apps console, OSD, lock screen), mako, kitty + zsh with the animated `arctic-fetch`
  fox, two themes (Winter and Polar night) switched with `Super + Shift + T`.
- **Default apps (all swappable in the installer):** Zen, Zed, kitty, zsh, yazi, Thunar,
  Collabora Office, VLC. Nix and Flatpak come preinstalled.
- **Installer:** a Go engine (`arcticd`) behind a Quickshell wizard. Disk encryption is on by
  default (LUKS2 + btrfs).

## Try it

Download the ISO from the [releases](https://github.com/yuvalkolodkingal/O-Tism/releases), write
it to a USB stick (4 GB or more), for example with Fedora Media Writer or
`sudo dd if=Arctic-Linux-0.1-x86_64.iso of=/dev/sdX bs=4M status=progress oflag=sync`, and boot it.

## Repository

| Path | What |
|---|---|
| `design/` | Design system: tokens, brand book, guidelines, fonts, logos, icons, wallpapers |
| `shell/` | The desktop shell (Quickshell/QML), grown from a personal Quickshell setup |
| `dotfiles/` | The home directory defaults (`/etc/skel`) and `arctic-*` helper commands |
| `installer-ui/` | The installer wizard (Quickshell/QML) |
| `cmd/`, `internal/` | The installer engine (Go, standard library only) |
| `modules/`, `profiles/` | The app catalog and install profiles |
| `branding/` | Login screen (SDDM), boot menu (GRUB), boot splash (Plymouth), logos |
| `packaging/` | RPM specs (`arctic-linux.spec`, `mangowm.spec`) and system files |
| `live/`, `iso/kiwi/` | The live session and the kiwi-ng ISO description |
| `tools/` | `build-rpms.sh`, `build-iso.sh`, `test-iso.sh`, `test-install.sh` |
| `docs/` | `PLAN.md` (why) and `BUILD-SPEC.md` (the contracts between components) |

## Build

Needs Docker (the builds run in Fedora 44 containers; the ISO build needs `--privileged`).

```sh
tools/build-rpms.sh     # RPMs → out/repo
tools/build-iso.sh      # live ISO → out/iso (about 20 minutes, ~15 GB scratch)
tools/test-iso.sh --firmware uefi --mode try    # boot it in QEMU, screenshots in out/test
tools/test-install.sh --firmware uefi           # install to a VM disk, boot it, log in (~1.5 h without KVM)
```

CI (`.github/workflows/ci.yml`) runs the Go, Python and Node tests, shellcheck and qmllint.
`.github/workflows/iso.yml` builds the ISO and publishes a release for `v*` tags.
