# Release notes

## Arctic Linux 0.2.0

Arctic Linux 0.2 installs on real hardware, sets up the drivers your computer needs, offers 126
apps in the installer, takes its colours from your wallpaper, has a settings app, and updates
itself, its own packages included.

**Download:** [GitHub releases](https://github.com/yuvalkolodkingal/Arctic-Linux/releases). The image is
`Arctic-Linux-0.2-x86_64.iso` with its `.sha256`. See
[Download and create a USB](Download-and-Create-a-USB).

### Installer fixes

- **Installs work on real hardware with SELinux.** Version 0.1.0 installs failed on real
  computers at *"removing live-only packages"* (rpm couldn't run the packages' scripts: exit 127),
  and some that finished sent you straight back to the login screen. The copied system is now
  labelled for SELinux right after it is copied, before anything runs in it, and again at the
  end, and every mounted part (`/`, `/home`, `/var/log`, `/nix` and `/boot`) is labelled
  explicitly. If removing the live-only packages still fails, they are removed without their
  scripts and their services turned off.
- **Save log to USB with Ventoy.** A Ventoy stick you started Arctic Linux from is recognised as
  the install medium and skipped, instead of failing to mount; the log goes to another FAT or
  exFAT stick.
- **The Summary** lists at most 12 apps, then *"and N more"*.
- **Snapshots.** The installer sets up snapper for the system, so every update is bracketed by
  snapshots (see [Updates](Updates#snapshots)).

### Drivers

- **Non-free drivers, found for you.** The installer looks at your computer's PCI devices and,
  when one needs it, offers a **Drivers** section at the top of the app picker, already ticked
  and naming your hardware: the **NVIDIA driver** (`akmod-nvidia`, GeForce RTX 20 series/Turing
  and newer), the **NVIDIA driver (580 series)** (`akmod-nvidia-580xx`, GTX 750 to GTX 1080 Ti and
  Titan V), **Intel video acceleration** (`intel-media-driver`), **AMD video acceleration**
  (the Mesa "freeworld" VA-API and Vulkan drivers) and the **Broadcom Wi-Fi driver**
  (`akmod-wl`). They come from RPM Fusion.
- The NVIDIA and Broadcom drivers are built for your kernel during the install, and the kernel
  arguments the NVIDIA driver needs are added. Hybrid laptops keep the desktop on the built-in
  graphics.
- **Secure Boot:** Arctic Linux signs the drivers it builds with its own key and asks your
  computer to trust it. After the install, the Done screen shows an eight-digit one-time code and
  the steps: at the first restart, on the blue **Perform MOK management** screen, choose
  **Enroll MOK** → **Continue** → **Yes**, type the code, and **Reboot**.
- The Summary has a **Drivers** row, the Network step tells you when your Wi-Fi card only works
  once its driver is installed, and the Done screen says what happened to each driver.
- Installing offline? The drivers are installed, built and signed the first time Arctic Linux is
  online.

See [Drivers](Drivers).

### Apps

- **126 apps in 21 sections** in the installer. The seven main sections (browser, editor,
  terminal, shell, file manager, office, video) now have more choices, such as Brave, Google
  Chrome, LibreWolf, Vivaldi, Visual Studio Code, Kate, Emacs, Ghostty, Konsole, Dolphin, Nemo,
  Haruna, Kodi and Jellyfin. Fourteen more sections sit folded under **More apps**: Music &
  audio, Photos, Graphics & design, Recording & editing, Chat & calls, Email & calendar, Notes &
  tasks, PDF & e-books, Games, Passwords & privacy, Downloads & sync, Developer tools,
  Containers & VMs and Utilities. Nothing in them is ticked by default.
- A **search box** looks through every app; apps that aren't open source are tagged
  **Proprietary**; apps that need another one (Podman Desktop, lazygit) say so.
- The defaults are the same as in 0.1: Zen Browser, Zed, kitty, zsh, yazi, Thunar, Collabora
  Office and VLC. See [Apps and software](Apps-and-Software).
- **Get apps installs without questions.** No more `Is this ok [y/N]`: installs run with `-y`,
  dnf runs through `pkexec dnf5`, and your password is asked once, in the desktop's password
  dialog, then remembered for a few minutes. Installing from Flathub needs no password.

### Colours and themes

- **A theme engine.** Every theme is made from one palette by `arctic-themegen`, which renders
  the colours for the shell, Mango, the terminals and every themed app, and checks the contrast.
- **Colours from your wallpaper.** With **Match colours to wallpaper** (on by default, a switch
  in the wallpaper picker and in Settings), your own pictures give the whole desktop their
  accent colour and tint. Light or dark follows the picture, or you choose. Text always keeps a
  contrast of at least 7:1 (4.5:1 for secondary text, the accent's text and terminal colours).
  Arctic's own wallpapers keep Winter and Polar night.
- **`arctic-theme`** has new commands: `set`, `auto`, `mode`, `current`, `list`, `reload` and
  `zen`. The 0.1 commands still work.
- **Your apps follow the theme:** GTK 3 apps through adw-gtk3, GTK 4 and libadwaita apps, Qt 5
  and Qt 6 apps through qt5ct and qt6ct, Flatpak apps (read-only access to your GTK and font
  settings, and adw-gtk3 for Flatpak), Zed, yazi, btop, fzf, the zsh prompt and plugins, foot
  and Alacritty, and optionally Zen Browser's accent. Adwaita icons and pointer everywhere.
- **Theme hooks** in `~/.config/arctic/theme-hooks.d/` run after every theme change, for apps of
  your own.

See [Themes and customisation](Themes-and-Customisation).

### Arctic Settings

- A settings app in the Arctic look: `Super + S`, **Settings** in the launcher, or the first
  item of the power menu. Thirteen pages: Appearance, Windows, Displays, Keyboard and mouse,
  Shortcuts, Default apps, Network, Bluetooth, Sound, Updates, Power and lock, Startup apps and
  About.
- Changes apply at once. Search finds any setting, each changed setting can be reset, and
  `Ctrl + Z` undoes. A new display layout goes back by itself unless you keep it.
- It writes only your own files (`~/.config/mango/settings.conf` and a few others) and keeps the
  previous versions; your `~/.config/mango/user.conf` still wins.

See [Settings](Settings).

### Updates

- **Arctic's own packages update online.** The desktop, the shell, the installer, the branding
  and Mango come from the Arctic package repository on the project's GitHub Pages site,
  <https://yuvalkolodkingal.github.io/Arctic-Linux/>, which `arctic-release` sets up together with its
  signing key. Fedora's packages keep coming from Fedora's repositories.
- **Signed.** Every package in the repository is signed, and so is the repository's metadata;
  dnf checks both (`gpgcheck=1`, `repo_gpgcheck=1`) before it installs anything. Each release of
  the repository is checked with dnf before it goes online.
- **Two channels.** **stable** (on) is built from every change to the main branch; **testing**
  (off) is published on every push to the development branch, for people who want to try
  changes first. Every change to stable is a new build of all of Arctic's packages, a download
  of about 9 MB.
- **Automatic updates.** Updates download in the background and are installed the next time the
  computer starts, never into the running desktop; the bar shows **Restart to update** when some
  are waiting. `arctic-update` and the **Updates** page in Settings show and change all of this,
  including the channel. See [Updates](Updates).
- **Undo.** dnf's history, the previous kernels and system snapshots taken around every update
  give you ways back. See [Updates](Updates#undoing-an-update).

### Upgrading from 0.1

**If your 0.1 install doesn't let you log in** (the login screen comes straight back), relabel
it for SELinux first: see
[Troubleshooting](Troubleshooting#the-login-screen-goes-straight-back-after-the-password). If
your 0.1 install stopped at *"removing live-only packages"*, install again with the 0.2 USB
stick.

Arctic Linux 0.1 shipped with the Arctic repository switched off (its `arctic.repo` pointed at a
placeholder address), so a 0.1 system doesn't see the new packages until you add the repository
once. Put the published repository file in `/etc/yum.repos.d/` under the same name, where it takes
the place of 0.1's disabled copy:

```sh
sudo curl -fsSL -o /etc/yum.repos.d/arctic.repo https://yuvalkolodkingal.github.io/Arctic-Linux/arctic.repo
sudo dnf upgrade
```

dnf asks whether to import the Arctic Linux key. Check that the fingerprint it shows is the one on
<https://yuvalkolodkingal.github.io/Arctic-Linux/>, then answer `y`. The upgrade brings the 0.2
`arctic-release`, which has the repository and its key built in. Remove the file you added, so
the system follows `arctic-release`'s settings from now on, and restart:

```sh
sudo rm /etc/yum.repos.d/arctic.repo
sudo systemctl reboot
```

From then on, updates arrive by themselves. The shell, Settings (`Super + S`), the theme engine
and wallpaper colours work straight away.

**Your account's own files.** New accounts get the 0.2 versions of the GTK, Qt, btop, yazi, zsh
and other settings files from `/etc/skel`; an account made by 0.1 keeps the ones it has. To add
the files that are new in 0.2 without touching any you already have:

```sh
cp -rn /etc/skel/.config/. ~/.config/
```

For the app theming, also replace these 0.1 files, if you haven't edited them:

```sh
cp /etc/skel/.config/gtk-3.0/gtk.css /etc/skel/.config/gtk-3.0/settings.ini ~/.config/gtk-3.0/
cp /etc/skel/.config/gtk-4.0/gtk.css ~/.config/gtk-4.0/
cp /etc/skel/.config/environment.d/10-arctic.conf ~/.config/environment.d/
cp /usr/share/arctic/skel/.zshrc ~/.zshrc
```

Then log out and back in. **Snapshots** aren't set up on a 0.1 system; to turn them on, see
[Updates](Updates#snapshots).

### Known limitations

- **The installer's screens are in English.** The language you pick sets your installed system's
  language.
- **No system updates during install.** The system is installed as it is on the USB stick;
  updates download in the background after your first login and are installed at the next
  restart.
- **Upgrading to a newer Fedora release** isn't covered yet.
- **Install alongside doesn't resize partitions.** It needs at least 40 GB of free, unused space
  that you make beforehand.
- **Older NVIDIA cards** (Kepler, GeForce GTX 600/700 series before the GTX 750, and older) keep
  the open-source driver: NVIDIA's drivers for them don't work with Mango.
- **The drivers need RPM Fusion's builds to keep up with Fedora.** When Fedora's Mesa is newer
  than RPM Fusion's freeworld build, AMD video acceleration can't be installed for a few days;
  the installer asks whether to try again or skip.
- **The installer's messages mention "the Software app"**: that's Get apps.
- **Some apps come from outside Fedora and Flathub's verified apps:** yazi and Ghostty from COPR,
  and several Flathub apps (among them Zed, Signal and Steam) from builds that aren't verified
  by their developers.
- **Testing:** version 0.2 has been tested mainly in QEMU virtual machines and the installer's
  demo mode, and the driver detection with simulated hardware. Please
  [report](https://github.com/yuvalkolodkingal/Arctic-Linux/issues) how it works on your computer.

## Arctic Linux 0.1.0

The first release of Arctic Linux: one live USB image that you can try without changing your
computer, and a step-by-step installer that sets up an encrypted Fedora 44 system with the Mango
desktop and the apps you pick.

**Download:** [GitHub releases](https://github.com/yuvalkolodkingal/Arctic-Linux/releases). The image is
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
  [report](https://github.com/yuvalkolodkingal/Arctic-Linux/issues) how it works on your computer.
