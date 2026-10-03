# Release notes

## Arctic Linux 1.1.0

Download `Arctic-Linux-1.1-x86_64.iso` from the
[1.1.0 release](https://github.com/yuvalkolodkingal/Arctic-Linux/releases/tag/v1.1.0).

- Web-app websites follow the desktop's light/dark theme live, along with their windows.
  Sites with their own appearance setting should be set to **System** or **Automatic**.
- Chromium comes with the web-app package. New WhatsApp apps and other calling sites select
  an available Chromium-family engine automatically; terminal installs now use the same
  engine recommendation as Get apps.
- Existing WhatsApp apps can switch to Chromium in **Settings → Web apps**. Pair again if
  requested; the original profile is preserved. Web calling still depends on the site's
  availability and account support.
- This ISO includes the WhatsApp preview/install fix, accelerated video playback changes,
  and Fish and Nautilus as the installer defaults.

Existing systems can update with `sudo dnf --refresh upgrade`, then restart the desktop shell
with `arctic-shell --restart`. There is no need to reinstall the OS.

## Arctic Linux 1.0.0

Arctic Linux 1.0 is the first stable release: the 0.3 desktop, with the fixes that followed it.
Download `Arctic-Linux-1.0-x86_64.iso` from the
[1.0.0 release](https://github.com/yuvalkolodkingal/Arctic-Linux/releases/tag/v1.0.0).

**Getting it:** an installed Arctic Linux 0.3 updates to 1.0 by itself, like any other update.

- **The shortcut sheet (`Super + /`) and the theme** no longer come up empty when a file read
  fails the first time: they retry.
- **The 3D terminal greeting** (`arctic-fetch`) is its own package, `arctic-fetch-3d`, which comes
  with the update.

## Arctic Linux 0.3.0

Arctic Linux 0.3 installs apps from one place and turns any website into an app, gives every item
on the bar its own menu, shows notifications itself, and adds the everyday tools people missed:
screenshots you can draw on, screen recording, night light, printing and scanning, a command
menu for every system action, and more themes.

**Getting it:** an installed Arctic Linux 0.2 updates to 0.3 by itself, like any other update: it
downloads in the background and installs the next time the computer starts. At the first login
after that, a **What's new** card sums up the release.

### What changes when you update

- **`Super + B` opens your browser.** `Super + W`, where it was, is free for a shortcut of your
  own.
- **The bell opens the notification centre.** Click it for your notifications; right-click it for
  do not disturb (in 0.2 a click turned do not disturb on or off). The Arctic shell shows
  notifications itself now: mako only runs in the waybar fallback session, so settings in
  `~/.config/mako` no longer apply to the Arctic desktop. Choose per app in **Settings →
  Notifications** instead.
- **Get apps starts with a choice** of where the app comes from: Flathub, Fedora packages, web
  apps, terminal apps, Remove apps or the console.
- **nm-applet, Blueman and the volume control (pavucontrol) are only recommended now**: the bar's
  own menus do their work, and nm-applet only starts in the waybar session. They stay installed,
  but you can remove them without removing the desktop.
- **Apps that set themselves to start at login** (Discord, Steam, Nextcloud, KDE Connect…) now
  start, as on other desktops. Switch any of them off in **Settings → Startup apps**.
- **New packages come with the update**, so it is a bigger download than usual: the web-app
  engine (`arctic-webapps`, on WebKitGTK 6.0), printing and scanning (CUPS, `ipp-usb`, Avahi,
  `sane-airscan` and Document Scanner), firmware updates (fwupd), the colour emoji font, Nerd Font
  symbols for the terminal (`arctic-fonts-symbols`), the extra themes (`arctic-themes-extra`), and
  `fd`, `qalculate` and `wl-kbptr` for the launcher's search and the keyboard pointer.

### Get apps and Remove apps

- **One place to install anything** (`Super + Shift + A`): **Flathub apps** (with the
  **Verified** badge), **Fedora packages** (the app catalogue, or every package with its
  repository), **Web apps**, **Terminal apps** (a program like `btop` in the launcher) and a
  **Console** for `dnf` and `flatpak` commands. Press a card's digit, or use the arrow keys.
- **Installs keep going when you close the launcher.** A strip at the bottom shows progress,
  **Show details** shows dnf's or Flatpak's own output, and a notification says when the app is
  ready.
- **Remove apps** has a tab per source: Flatpak, Fedora packages, web apps and terminal apps.
  Before anything goes, it shows every package dnf would remove with it, takes a snapshot when
  snapshots are set up, and keeps an app's settings and sign-in unless you tick the box. You can
  also select an app in the launcher and press `Shift + Delete`.
- **Arctic protects itself:** a removal that would take the desktop, the package manager, your
  login shell or your only terminal along is refused, and says why.

See [Apps and software](Apps-and-Software#get-apps).

### Web apps

- **Any website as an app**, with its own launcher entry, icon, window and sign-in, kept apart
  from your browser: Get apps → **Web apps**, type the address, **Add app**. From a terminal:
  `arctic-webapp install music.youtube.com`.
- The window has Back, Forward and Reload, find in page and zoom; links to other sites open in
  your browser, while sign-in pages stay in the app. Camera, microphone and location requests ask
  in a bar outside the page, and the app's notifications show in the notification centre under its
  name.
- **Calls and protected video** (Meet, Teams, Netflix, Spotify…) need a Chromium-family engine:
  the preview suggests Brave, Chrome, Vivaldi or Chromium, and the app then opens in that
  browser's app window, still with its own profile.
- **Settings → Web apps** changes a web app's name, icon, engine, notifications and permissions.

See [Web apps](Web-Apps).

### Menus on the bar

- **Every item on the bar opens Arctic's own menu**, in the desktop's style, instead of a separate
  app: see [Menus on the bar](Bar-Menus).
  - **Network:** Wi-Fi networks with their signal, the password asked right under the network,
    hidden networks and company or school Wi-Fi (eduroam), VPN and Tailscale switches (with
    exit nodes), airplane mode, a hotspot, and **Share with a phone…** (a QR code of a saved
    network).
  - **Bluetooth:** your devices with their battery, and pairing, with the codes in Arctic's own
    dialog.
  - **Sound:** where sound plays, the microphone, a volume for each app, and headphone or speaker
    ports and profiles.
  - **Battery:** power mode, **Limit charging to 80 %** on laptops that support it, battery
    health and your mouse's or headphones' battery. Arctic warns once when the battery is low and
    again when it's about to run out.
  - **The clock** opens a calendar with week numbers; **what's playing** sits next to it, with
    its own menu, and on the lock screen.
  - **Tray icons'** menus are drawn in the same style.
- **Quick settings** on `Super + A`: Wi-Fi, Bluetooth, do not disturb, dark style, power mode,
  microphone, VPN and airplane mode, with volume and brightness sliders.
- **Keys:** `Super + Ctrl + W`, `B`, `A`, `P`, `T`, `M` and `D` open the network, Bluetooth,
  sound, battery, calendar, media and brightness menus; `Super + Alt + B` walks the bar with the
  arrow keys. In a menu, the arrow keys, `Enter` and `Esc` do what you'd expect, and `Ctrl + Tab`
  moves to the next menu. `Shift + Mute` sends sound to the next output.
- **The brightness keys** change the screen you're on, external monitors included when they
  accept DDC/CI.
- **"Mic", "Camera" and "Sharing"** show next to the clock while an app uses them.
- **A saved Wi-Fi network whose password changed** asks for the new one in a notification.
- nm-applet no longer starts with the Arctic shell (the waybar fallback still has it), and
  Blueman's tray icon is hidden: the menus do their work. nm-applet, Blueman and the volume
  control (pavucontrol) are still installed, but you can now remove them without removing the
  desktop.

### Notifications and do not disturb

- **Pop-ups** appear in the top-right corner of the screen you're on, up to three at a time.
  Urgent ones have a red edge and stay until you close them. Click one to act on it.
- **The notification centre** (the bell, or `Super + Alt + N`) groups them by app and keeps the
  last 50, also after a restart. `Super + Alt + ,` acts on the newest one. The lock screen only
  says how many arrived, never what they say.
- **Do not disturb** for an hour, until tomorrow, until you turn it off, or every day between two
  times (**Settings → Notifications**). Arctic's own alerts and urgent notifications still show,
  and you can let an app through or keep even its urgent ones quiet.
- **Per app:** pop-ups, only the centre, or nothing, in **Settings → Notifications**.

See [Notifications](Notifications).

### Shortcuts and capture

- **`Super + B` opens your browser.** It was `Super + W`, which is now free for a shortcut of
  your own. If you had bound `Super + B` yourself, Settings > Shortcuts shows that it no longer
  runs (Arctic's shortcuts come first), so you can move it to another key.
- **`Super + Shift + S` takes a screenshot of an area**, as on Windows; `Print` still does. The
  screen freezes while you drag over an area or click a window, so menus and tooltips stay in it. `Shift + Print` now takes the screen you're on (not every
  screen at once), window screenshots leave out the border, and `Ctrl + Print` copies an area
  without saving it.
- **The screenshot notification does more:** click it to open the picture; its buttons show it in
  your file manager, open it in an editor to draw arrows, text and boxes (swappy), or move it to
  the trash.
- **Copy text from the screen** with `Super + Ctrl + Print` (text recognition, in your language),
  and **read QR codes** (`arctic-ocr --qr`; sign-in codes stay out of clipboard history).
- **Pick a colour** anywhere with `Super + Shift + C`: it's copied as `#rrggbb`.
- **Record the screen** with `Super + Alt + R`: click a screen or drag an area, press again to
  stop. Recordings go to `~/Videos/Screencasts`, using your graphics card's encoder when it has one.
- **Sharing your screen** in a video call or OBS shows a list of your screens and windows, so you
  can share a single window.
- **Clipboard history** (`Super + V`) is a panel with search and pictures: `Enter` copies, `Shift +
  Enter` also pastes, `Delete` removes. It's blacked out in screenshots and screen shares.
- **Emoji** with `Super + Ctrl + E`: search by name, `Enter` types it. The live USB and new installs
  get the colour emoji font.
- **Switching windows:** `Alt + Tab` (`` Alt + ` `` goes back; `Alt + Shift` would switch your keyboard
  layout), `Super + Alt + Tab` for every workspace, `Super + J` to jump to a window by its letter,
  `Super + Backspace` for the previous one.
- **More window keys:** `Super + H` hides a window (`Super + Shift + H` brings it back),
  `Super + Shift + P` pins one over every workspace, `Super + Alt` + arrows make tab groups.
- **A scratch workspace** over the current one (`` Super + ` ``) and a **drop-down terminal**
  (`Super + Alt + Enter`).
- **Hardware keys:** the keyboard-light, touchpad, calculator and search keys work.
- **Settings > Keyboard and mouse** has a **Compose key** (press it, then two keys to type é, ©…),
  and says which shortcuts your layout-switch key would also fire; Settings refuses a new shortcut
  that holds that key.
- Upgrading? If you replaced `~/.config/mango/arctic/binds.conf` or `apps.conf` with your own copy,
  it doesn't get the new keys: compare it with `/usr/share/arctic/mango/`.

### Night light, printing, drives, screens and sharing

- **Night light** (`Super + Ctrl + N`): warmer colours from sunset to sunrise (worked out from your
  time zone, without looking up your location), on hours you choose, or always. **Keep awake**
  (`Super + Ctrl + I`): no lock or sleep while you present or download; video calls and films
  keep the screen on by themselves. See [Night light and keep awake](Night-Light-and-Keep-Awake).
- **Printing and scanning** work without drivers for most printers and scanners made in the last
  ten years, over USB or the network. **Settings → Printers and scanners** shows them; **Document
  Scanner** scans to PDF. See [Printing and scanning](Printing-and-Scanning).
- **USB drives and SD cards** are ready as soon as you plug them in, with a notification; eject
  them in Thunar. **Phones, iPhones and cameras** show up in Thunar, and so do Windows and NAS
  shares (`smb://`). See [Drives, phones and cameras](Drives-and-Phones).
- **Screens:** `Super + P` duplicates or extends your screen for a projector. Closing the lid with
  a monitor plugged in keeps you working on the monitor; without one, **Settings → Power and
  lock** says whether the laptop suspends, locks or keeps running. **Lighter effects** turn
  themselves on in a virtual machine, and **game mode** drops the gaps between windows. See
  [Screens and the laptop lid](Screens-and-Laptop-Lid).
- **Sharing:** `Super + Ctrl + S` sends the clipboard or files to phones and computers nearby with
  LocalSend (from Get apps), or opens KDE Connect. **Settings → Sharing** shows what the firewall
  lets in and turns remote login (SSH) on or off. See [Sharing and phones](Sharing-and-Phones).
- **Updates for everything:** Flatpak apps are updated every day, firmware updates from fwupd are
  offered in **Settings → Updates**, and **Undo…** there takes back one update. See
  [Updates](Updates#flatpak-apps-firmware-and-nix).
- **More in Settings:** **Date and time** (time zone, network time, the computer's language),
  **Users and sign-in** (your picture, name, password and fingerprint; a saved fingerprint also
  unlocks the lock screen), **Startup apps** with the apps that start themselves, and the
  computer's name in **About**.
- `Ctrl + Shift + Esc` shows what's running (a system monitor). On a laptop with two graphics
  chips, `Shift + Enter` on an app in the launcher runs it on the discrete one.

### The command menu, themes and the rest of the desktop

- **The command menu** (`Super + Alt + Space`): every system action in one keyboard menu:
  capture, toggles, themes, every Settings page, installing and removing apps, updates and power.
  `Super + Ctrl + C` opens it at Capture. Add rows of your own in `~/.config/arctic/menu.json`.
  See [Command menu](Command-Menu).
- **The launcher finds more than apps:** Settings pages and single settings, open windows, an
  app's own actions, files in your home folder, unit conversions (`10 km to mi`) and a web search
  (start with `?`). The apps you open most come first.
- **Reminders:** `Super + Ctrl + R`, then `10m tea` or `17:30 call Ana`; a notification you can't
  miss says it when it's time.
- **Weather** (off until you turn it on in **Settings → Appearance**): now and five days under the
  calendar, from Open-Meteo, without an account. **Show the temperature on the bar** puts it next
  to the clock.
- **Themes:** ten more looks in **Settings → Appearance → More themes** (Nord, Catppuccin, Gruvbox,
  Tokyo Night, Rosé Pine, Everforest), **Add a theme from the web** (Omarchy themes work; only their
  colours and pictures are kept), **light by day, dark at night**, and a wallpaper that changes by
  itself every 30 minutes, hour or day. See [Themes and customisation](Themes-and-Customisation).
- **Accessibility**, a new Settings page: **High contrast** in any theme, a bigger text size for
  apps and the terminal, pointer size, reduced motion, and a **keyboard pointer**
  (`Super + Alt + K`) that moves and clicks the mouse from the keyboard.
- **The bar:** a red **Recording 01:23** pill while you record the screen (click it to stop), and
  `Super + Shift + Space` hides the bar until you press it again; the microphone, camera and
  recording pills stay in the corner meanwhile. See [Menus on the bar](Bar-Menus#hiding-the-bar).
- **Short notices** on the screen for Caps Lock, Num Lock and the keyboard layout.
- **A welcome card** at a new account's first login shows the keys that get you everywhere.
- **Hooks:** scripts of yours in `~/.config/arctic/` run when the wallpaper or font changes, the
  screen locks or unlocks, the battery is low, after an update and at every login. See
  [Hooks for other events](Themes-and-Customisation#hooks-for-other-events).
- **Icons in the terminal:** the Nerd Font symbols yazi, eza and prompts use are installed, after
  the code font.

### Known limitations

- **Web apps on the Arctic engine can't make calls or play protected video**: pick a
  Chromium-family engine for those sites (the preview suggests one).
- **No screen reader, magnifier or on-screen keyboard yet**: none works with Mango on Fedora 44;
  Settings → Accessibility says so.
- **Hiding the bar and the command menu need the Arctic shell**: in the waybar fallback session,
  `Super + Shift + Space` does nothing and the command menu opens in fuzzel.

## Arctic Linux 0.2.1

A fix release for 0.2, with a few additions to Settings and the terminal.

**Download:** [GitHub releases](https://github.com/yuvalkolodkingal/Arctic-Linux/releases). The image is
`Arctic-Linux-0.2-x86_64.iso` with its `.sha256`.

### The project has a new address

The repository is now <https://github.com/yuvalkolodkingal/Arctic-Linux> (it was `O-Tism`), and
Arctic's package repository is <https://yuvalkolodkingal.github.io/Arctic-Linux/>. Old GitHub
links still lead to the right place, but the package repository's old address doesn't.

**If you installed 0.2.0**, your system still looks for Arctic's updates at the old address.
Run this once (then updates work as before):

```sh
sudo dnf upgrade --refresh --setopt=arctic.baseurl=https://yuvalkolodkingal.github.io/Arctic-Linux/repo/stable/fedora-44/x86_64/ arctic-release
```

See [Troubleshooting](Troubleshooting#updates-stopped-after-the-repository-was-renamed).

### Installer

- **A finished install is never thrown away at the last step.** On an NVIDIA laptop with an
  encrypted disk, 0.2.0 could fail at *Setting up your account* because the encrypted disk was
  still in use, and then removed the new boot entry. The installer now waits for the NVIDIA
  driver build that runs in the background, stops helpers left running in the new system,
  releases copies of its disks held by other services, and tries closing the disk again. If it
  still can't be closed, the install counts as done and the Done screen says a restart finishes
  it. Once the account is created, a failure no longer removes the boot entry or partitions.
- **One network hiccup no longer fails an app.** dnf and Flatpak downloads that fail because of
  the network are tried again three times.
- **A short passphrase or password no longer stops you.** Any disk passphrase or account password
  is accepted once you've typed it twice; below **Fair** (or under 8 characters for the password)
  the step shows a warning that it's easy to guess, and its Summary row notes it.

### Settings

- **Wallpapers:** add your own pictures with the file chooser or by dragging them from Files;
  rename and delete them. **Wallhaven:** search wallhaven.cc and set a wallpaper with one click,
  with filters that fit your screens and an optional API key. See [Settings](Settings#appearance).
- **Displays:** arrange your screens by dragging them. See [Settings](Settings#displays).

### Terminal

- **fastfetch** in the Arctic design, in the theme's colours, and a **neofetch** command. See
  [Terminal and shell](Terminal-and-Shell).

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
