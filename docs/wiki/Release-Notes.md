# Release notes

## Arctic Linux 0.1.0

The first release of Arctic Linux: one live USB image that you can try without changing your
computer, and a step-by-step installer that sets up an encrypted Fedora 44 system with the Mango
desktop and the apps you pick.

**Download:** [GitHub releases](https://github.com/yuvalkolodkingal/O-Tism/releases). The image is
`Arctic-Linux-0.1-x86_64.iso` with its `.sha256`. See
[Download and create a USB](Download-and-Create-a-USB).

### What's in it

**Base system**

- Fedora 44 (x86_64), with Fedora's kernel, packages and repositories. `arctic-release` identifies
  the system as "Arctic Linux 0.1 (Fedora 44 base)".
- Starts on UEFI (through Fedora's signed shim) and BIOS computers.
- SELinux enforcing, `root` locked, no SSH server, zram swap as on Fedora.
- Flatpak and Nix preinstalled, with SELinux file contexts for `/nix`.

**Live USB**

- Boot menu with **Try Arctic Linux**, **Install Arctic Linux**, **Safe graphics mode**,
  **Check USB for errors** and **Boot from first disk**, in the Arctic GRUB theme.
- Try mode: the full desktop, with the "You're trying Arctic Linux" welcome card, a Live session
  tag and an Install item on the bar. Zen Browser is preinstalled when the image stays within
  GitHub's 2 GiB limit; the release's own notes mention it when this build has it.
- Install mode opens the installer full screen.

**Installer**

- A wizard for non-experts: Welcome, Keyboard, Network, Time zone, Disk, Encryption, Account,
  Apps, Summary, Installing, and Done, with an attention screen when something needs a decision.
  Nothing is written to disk before the Summary.
- 27 languages and 30 keyboard layouts. Non-Latin layouts add English (US) for passwords.
- Wi-Fi from inside the installer; time zone found from your network.
- **Erase disk and install** (GPT, LUKS2 with argon2id, btrfs with `@`, `@home`, `@var_log`,
  `@nix`, zstd) or **Install alongside** another system in existing free space.
- Passphrase strength meter and a four-word passphrase suggestion.
- A Ninite-style app picker with 28 apps in 8 categories. Defaults: Zen Browser, Zed, kitty, zsh,
  yazi, Thunar, Collabora Office and VLC. Apps already on the USB stick are copied, the rest are
  downloaded; media codecs (RPM Fusion, FFmpeg, OpenH264) are always added.
- Optional apps that fail can be retried or skipped; core failures offer Try again, Change your
  answers and Save log to USB.
- An engine (`arcticd`, Go) and a separate UI (Quickshell), talking JSON over a socket. The same
  engine runs unattended installs from a profile for testing.

**Desktop**

- Mango 0.17.3, a tiling Wayland window manager: 2px borders with an amber focused border, 10px
  radius, 8px gaps, five workspaces, overview, touchpad gestures.
- The Arctic shell (Quickshell): top bar, screen frame, launcher with `=` calculator and `>`
  commands, Get apps console (dnf and Flatpak), wallpaper picker, power menu, shortcut sheet,
  volume and brightness OSD, lock screen, polkit password dialog and the live welcome card.
- Two themes, Winter and Polar night, switched live with `Super + Shift + T`, covering the shell,
  kitty, notifications, GTK, Mango, the lock screen and the wallpapers.
- Six wallpapers (Snowfield, Aurora and Fox in both themes).
- kitty with the Arctic palette and JetBrains Mono; zsh with the `~ ❯` prompt; the animated
  `arctic-fetch` fox greeting.
- Arctic login screen (SDDM, running on Mango), boot splash with the disk passphrase prompt
  (Plymouth), and boot menu (GRUB).
- Reduced motion (`arctic-motion off`), a waybar-based fallback desktop (`ARCTIC_SHELL=waybar`),
  and settings files Arctic never overwrites (`~/.config/mango/user.conf` and others).
- `arctic-firstboot`, which finishes installing apps put off during an unattended install.

**Building and testing**

- `tools/build-rpms.sh`, `tools/build-iso.sh`, `tools/test-iso.sh` and `tools/test-install.sh`, all
  running in Fedora 44 containers; CI for the engine, shell, scripts, QML and RPM builds, and a
  workflow that builds the ISO and publishes releases.

### Known limitations

- **The installer's screens are in English.** The language you pick sets your installed system's
  language.
- **No system updates during install.** The network screen mentions downloading the latest
  security updates, but version 0.1 installs the system as it is on the USB stick. Run
  `sudo dnf upgrade` after your first login.
- **Arctic's own packages don't update online yet.** Fedora's packages update with `dnf upgrade`,
  but the desktop, shell, branding and Mango change only with a new Arctic Linux release. The
  Arctic repository is defined but disabled until it's published.
- **Upgrading to a newer Fedora release** isn't covered yet.
- **No NVIDIA driver setup.** Arctic Linux uses the open drivers that come with Fedora. If the
  screen stays black, use **Safe graphics mode**.
- **Install alongside doesn't resize partitions.** It needs at least 40 GB of free, unused space
  that you make beforehand (for example with Windows' Disk Management).
- **Skipped apps aren't retried.** An app you skip in the installer isn't installed; add it later
  with Get apps. The installer's messages call this "the Software app".
- **The live session may have no browser** when the image was built without Zen.
- **The live session's VLC** doesn't include the RPM Fusion plugins; they're added, with the other
  codecs, when you install.
- **Some apps come from outside Fedora and Flathub's verified apps:** yazi from the
  `lihaohong/yazi` COPR; Zed, Signal and Steam from Flathub builds that aren't verified by their
  developers.
- **No snapshots.** The system uses btrfs, but no snapshot or rollback tool is set up.
- **Small differences from the design:** the design's `Super + B` bar focus isn't there yet
  (everything on the bar has its own shortcut), and the lock screen doesn't show how many
  notifications are hidden.
- **Testing:** version 0.1 has been tested mainly in QEMU virtual machines (UEFI and BIOS). Please
  [report](https://github.com/yuvalkolodkingal/O-Tism/issues) how it works on your computer.
