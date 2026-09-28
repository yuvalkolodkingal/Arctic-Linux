# Apps and software

Arctic Linux starts with the apps you pick in the installer, from a catalog of 126. Afterwards
you can add almost anything from three places: Fedora's own packages (dnf), Flathub (Flatpak) and
Nix. The quickest way is **Get apps** (`Super + Shift + A`).

## The default apps

These are ticked for you in the installer. Every one can be swapped or unticked.

| Role | Default | Opens with | Comes from |
|---|---|---|---|
| Browser | **Zen Browser**: calm, privacy-first, with vertical tabs | `Super + W` | Flathub |
| Code editor | **Zed**: fast, modern code editor | `Super + E` | Flathub (community build) |
| Terminal | **kitty**: fast, GPU-drawn terminal | `Super + Enter` | Fedora |
| Shell | **zsh**: friendly shell with smart completion | inside the terminal | Fedora |
| File manager | **Thunar**: simple windowed file manager | `Super + F` | Fedora |
| File manager in the terminal | **yazi** | `Super + Shift + F` | COPR `lihaohong/yazi` (Nix as a fallback) |
| Office | **Collabora Office**: documents, spreadsheets and slides | the launcher | Flathub |
| Video | **VLC**: plays almost any video or audio file | the launcher | Fedora |

## Everything the installer offers

The installer's app picker has **126 apps in 21 sections**. The first seven sections (browser,
editor, terminal, shell, file manager, office and video) are always open, with the defaults
ticked. The other fourteen sit under **More apps**: they start folded, and nothing in them is
ticked until you pick it. Open a section, or type in the **Search 126 apps** box to look through
every app by name, description or section (try *music*, *PDF* or *games*).

- **Pick one** sections (browser, terminal, shell) need exactly one app; it becomes your default.
  Office is **pick one or none**. Every other section is **pick any**.
- Apps marked **Proprietary** aren't open source.
- A few apps need another one: **Podman Desktop** needs **Podman**, and **lazygit** needs
  **Git**. The installer tells you on Next if one is missing.
- When an app has more than one source, the installer tries them in the order shown and uses the
  first that works. Apps that come from Flathub bring a shared runtime the first time, which the
  download estimate at the bottom of the picker includes.

In the tables, **Fedora** means Fedora 44's own packages, **RPM Fusion** the RPM Fusion
repositories (which the installer always adds), **Flathub** a Flatpak app, **COPR** a community
package repository, and **Nix** the Nix package manager.

### Browser

| App | What it is | Comes from |
|---|---|---|
| **Zen Browser** (ticked) | Calm, privacy-first browser with vertical tabs. | Flathub |
| Firefox | The classic open-source browser. | Fedora, else Flathub |
| Brave | Blocks ads and trackers out of the box. | Flathub |
| Google Chrome · *Proprietary* | Google's browser, synced to your account. | Flathub |
| LibreWolf | Firefox tuned for privacy, with no telemetry. | Flathub |
| Chromium | Open-source base of Chrome. | Fedora, else Flathub |
| Vivaldi · *Proprietary* | Feature-packed browser you can reshape. | Flathub |

### Editor

| App | What it is | Comes from |
|---|---|---|
| **Zed** (ticked) | Fast, modern code editor. | Flathub |
| Visual Studio Code · *Proprietary* | Microsoft's popular code editor. | Flathub |
| VSCodium | VS Code without the telemetry. | Flathub |
| Neovim | Keyboard-driven text editor for the terminal. | Fedora |
| Helix | Modal editor that works out of the box. | Fedora |
| Kate | KDE's capable text and code editor. | Fedora, else Flathub |
| Emacs | The endlessly extensible editor. | Fedora, else Flathub |
| Text Editor | Simple notepad for everyday text. | Fedora, else Flathub |

### Terminal

| App | What it is | Comes from |
|---|---|---|
| **kitty** (ticked) | Fast, GPU-drawn terminal. | Fedora |
| Ghostty | Fast, native terminal with sensible defaults. | COPR `scottames/ghostty` |
| Alacritty | Minimal GPU terminal. | Fedora |
| foot | Lightweight Wayland terminal. | Fedora |
| Konsole | KDE's terminal with tabs, splits and profiles. | Fedora |

### Shell

| App | What it is | Comes from |
|---|---|---|
| **zsh** (ticked) | Friendly shell with smart completion. | Fedora |
| fish | Shell with suggestions as you type. | Fedora |
| bash | The standard Linux shell. | Fedora |

### File manager

| App | What it is | Comes from |
|---|---|---|
| **yazi** (ticked) | Quick file manager inside the terminal. | COPR `lihaohong/yazi`, else Nix |
| **Thunar** (ticked) | Simple windowed file manager. | Fedora |
| Files (Nautilus) | GNOME's file manager. | Fedora |
| Dolphin | KDE's file manager with tabs and split view. | Fedora |
| Nemo | Familiar, full-featured file manager. | Fedora |
| PCManFM-Qt | Very light windowed file manager. | Fedora |

### Office

| App | What it is | Comes from |
|---|---|---|
| **Collabora Office** (ticked) | Documents, spreadsheets and slides. | Flathub |
| LibreOffice | The full classic office suite. | Flathub, else Fedora |
| ONLYOFFICE | Office suite close to Microsoft formats. | Flathub |

### Video

| App | What it is | Comes from |
|---|---|---|
| **VLC** (ticked) | Plays almost any video or audio file. | Fedora, with RPM Fusion's codec plugins |
| mpv | Minimal, keyboard-driven player. | Fedora, else Flathub |
| Celluloid | Simple player built on mpv. | Fedora, else Flathub |
| Haruna | Feature-rich player built on mpv. | Fedora, else Flathub |
| Kodi | Media centre for your TV, films and music. | RPM Fusion, else Flathub |
| Jellyfin Media Player | Watch your Jellyfin server's library. | Flathub |

### More apps

These start folded in the picker, and nothing here is ticked by default.

#### Music & audio

| App | What it is | Comes from |
|---|---|---|
| Spotify · *Proprietary* | Stream music and podcasts. | Flathub |
| Strawberry | Music player for big local collections. | Fedora, else Flathub |
| Tauon | Stylish player for your music library. | Flathub |
| Amberol | Plays music, and nothing else. | Flathub |
| Rhythmbox | Classic music library and radio player. | Fedora, else Flathub |
| Shortwave | Listen to internet radio stations. | Flathub |
| Easy Effects | Equaliser and effects for all your sound. | Flathub, else Fedora |

#### Photos

| App | What it is | Comes from |
|---|---|---|
| Image Viewer (Loupe) | Fast, simple image viewer. | Fedora, else Flathub |
| gThumb | Browse, view and touch up photos. | Fedora, else Flathub |
| Shotwell | Import and organise your photos. | Fedora, else Flathub |
| digiKam | Professional photo management. | Flathub |
| darktable | Develop RAW photos like a darkroom. | Fedora, else Flathub |
| RawTherapee | Detailed RAW photo processing. | Fedora, else Flathub |

#### Graphics & design

| App | What it is | Comes from |
|---|---|---|
| GIMP | Photo editing and painting. | Fedora, else Flathub |
| Krita | Digital painting for artists. | Flathub, else Fedora |
| Inkscape | Vector drawing. | Fedora, else Flathub |
| Blender | 3D modelling, animation and rendering. | Flathub |
| Pinta | Easy drawing and image editing. | Flathub |
| FreeCAD | 3D design for real-world objects. | Flathub |

#### Recording & editing

| App | What it is | Comes from |
|---|---|---|
| OBS Studio | Screen recording and streaming. | Flathub |
| GPU Screen Recorder | Record gameplay with almost no slowdown. | Flathub |
| Kooha | Record your screen in one click. | Flathub |
| Audacity | Record and edit audio. | Fedora, else Flathub |
| Kdenlive | Full-featured video editor. | Flathub, else Fedora |
| Shotcut | Straightforward video editor. | Fedora, else Flathub |
| HandBrake | Convert videos to other formats. | RPM Fusion, else Flathub |

#### Chat & calls

| App | What it is | Comes from |
|---|---|---|
| Signal | Private messaging. | Flathub |
| Discord · *Proprietary* | Voice, video and text chat for communities. | Flathub |
| Telegram | Fast messaging that syncs everywhere. | RPM Fusion, else Flathub |
| Element | Secure chat on the Matrix network. | Flathub |
| Slack · *Proprietary* | Team chat for work. | Flathub |
| Zoom · *Proprietary* | Video meetings and calls. | Flathub |
| ZapZap | WhatsApp in its own window (unofficial). | Flathub |

#### Email & calendar

| App | What it is | Comes from |
|---|---|---|
| Thunderbird | Email, calendar and contacts in one. | Flathub, else Fedora |
| Evolution | Email and calendar, with Exchange support. | Fedora, else Flathub |
| Betterbird | Thunderbird with extra fixes and features. | Flathub |

#### Notes & tasks

| App | What it is | Comes from |
|---|---|---|
| Obsidian · *Proprietary* | Markdown notes, linked like a second brain. | Flathub |
| Joplin | Notes and to-dos that sync anywhere. | Flathub |
| Logseq | Outliner for daily notes and ideas. | Flathub |
| AppFlowy | Docs, wikis and boards, like Notion. | Flathub |
| Standard Notes | Simple notes, end-to-end encrypted. | Flathub |
| Xournal++ | Handwritten notes and PDF annotation. | Flathub, else Fedora |
| Planify | To-do lists and task planning. | Flathub |

#### PDF & e-books

| App | What it is | Comes from |
|---|---|---|
| Papers | Clean, simple PDF reader. | Fedora, else Flathub |
| Okular | Reads PDFs, e-books and comics, with notes. | Flathub, else Fedora |
| Zathura | Minimal, keyboard-driven PDF reader. | Fedora, else Flathub |
| Foliate | Comfortable e-book reader. | Fedora, else Flathub |
| calibre | Organise and convert your e-book library. | Fedora, else Flathub |
| PDF Arranger | Merge, split and reorder PDF pages. | Fedora, else Flathub |

#### Games

| App | What it is | Comes from |
|---|---|---|
| Steam · *Proprietary* | Games and the Steam store. | RPM Fusion, else Flathub |
| Heroic | Plays your Epic, GOG and Amazon games. | Flathub |
| Lutris | One library for games from everywhere. | Flathub, else Fedora |
| Bottles | Run Windows apps and games. | Flathub |
| Prism Launcher | Manage Minecraft versions and mods. | Flathub |
| ProtonPlus | Adds newer Proton versions for Windows games. | Flathub |
| MangoHud | On-screen FPS and hardware stats in games. | Fedora |
| GameMode | Gives games full speed while they run. | Fedora |

#### Passwords & privacy

| App | What it is | Comes from |
|---|---|---|
| KeePassXC | Offline password manager you control. | Fedora, else Flathub |
| Bitwarden | Open-source password manager with sync. | Flathub |
| 1Password · *Proprietary* | Password manager for families and teams. | Flathub |
| Proton Pass | Encrypted passwords from Proton. | Flathub |
| Authenticator | Two-factor codes for your accounts. | Flathub |
| Proton VPN | Free, no-logs VPN from Proton. | Flathub |
| Tor Browser | Browse anonymously over Tor. | Flathub |

#### Downloads & sync

| App | What it is | Comes from |
|---|---|---|
| qBittorrent | Full-featured torrent downloader. | Fedora, else Flathub |
| Transmission | Simple, light torrent downloader. | Fedora, else Flathub |
| Syncthing | Syncs folders between your devices, privately. | Fedora |
| Nextcloud | Syncs files with your Nextcloud server. | Fedora, else Flathub |
| LocalSend | Send files to nearby phones and computers. | Flathub |

#### Developer tools

| App | What it is | Comes from |
|---|---|---|
| Git | Version control, with the GitHub command line. | Fedora |
| lazygit | Git in a friendly terminal interface. | Nix |
| Meld | Compare files and folders side by side. | Fedora, else Flathub |
| DBeaver | One tool for every database. | Flathub |
| Bruno | Test APIs, with collections kept in Git. | Flathub |

#### Containers & VMs

| App | What it is | Comes from |
|---|---|---|
| Podman | Run containers without a background daemon. | Fedora |
| Podman Desktop | Manage containers and images visually. | Flathub |
| Distrobox | Use other Linux distros inside containers. | Fedora |
| GNOME Boxes | Try other systems in virtual machines. | Fedora, else Flathub |
| Virtual Machine Manager | Advanced virtual machines with KVM. | Fedora |
| Waydroid | Android apps. Gets 1 GB on first run. | Fedora |

#### Utilities

| App | What it is | Comes from |
|---|---|---|
| Flathub | Adds the Flathub app store (Flatpak). | Flathub (adds the store only) |
| Bazaar | Browse and install apps from Flathub. | Flathub |
| Flatseal | Review what each Flatpak app may access. | Flathub, else Fedora |
| Mission Center | See what's using your CPU, memory and GPU. | Flathub |
| GNOME Disks | Format drives and write disk images. | Fedora |
| Pika Backup | Easy, encrypted backups of your files. | Flathub |
| File Roller | Open and create zip and other archives. | Fedora, else Flathub |
| Btrfs Assistant | Browse and restore system snapshots. | Fedora |

The **Flathub** entry only adds the Flathub app store, with no app. **Bazaar** is an app store
for Flathub apps. **Btrfs Assistant** shows the system snapshots Arctic Linux takes around every
update (see [Updates](Updates#undoing-an-update)).

## Drivers

When the installer finds hardware that works better with a driver from RPM Fusion, a **Drivers**
section comes first in the picker, with the driver already ticked for the card it found. There's
no Drivers section when nothing needs one.

| Driver | For | Packages |
|---|---|---|
| **NVIDIA driver** | NVIDIA GeForce RTX 20 series (Turing) and newer, including the NVIDIA card in hybrid laptops | `akmod-nvidia`, CUDA libraries, `libva-nvidia-driver` |
| **NVIDIA driver (580 series)** | NVIDIA GeForce GTX 750 to GTX 1080 Ti and Titan V (Maxwell, Pascal and Volta) | `akmod-nvidia-580xx` (the last series for these cards) |
| **Intel video acceleration** | Intel graphics from Broadwell (5th generation Core) on, and Arc | `intel-media-driver`, with H.264 and H.265 |
| **AMD video acceleration** | AMD Radeon graphics and APUs with a video decoder | `mesa-va-drivers-freeworld`, `mesa-vulkan-drivers-freeworld` |
| **Broadcom Wi-Fi driver** | Broadcom Wi-Fi chips that have no working open driver (BCM4311, BCM4312, BCM4321, BCM4322, BCM4331, BCM43142, BCM4352, BCM4360) | `akmod-wl`, `broadcom-wl` |

The NVIDIA and Broadcom drivers are built for your kernel on your computer (by akmods) and are
built again for every new kernel. With Secure Boot on, you confirm their key once after the
install; see [Install Arctic Linux](Install-Arctic-Linux#secure-boot-and-your-driver). Older
NVIDIA cards (Kepler and before) keep the open driver: their NVIDIA drivers don't work with Mango.
Everything about drivers, including adding one later, is on [Drivers](Drivers).

## Always added

Whatever you pick, the installer also adds:

- **Media codecs**: the RPM Fusion repositories (free and nonfree), full FFmpeg and OpenH264, so
  most video and audio formats play.
- **Flatpak** and **Nix**, ready to use, and the adw-gtk3 theme for Flatpak apps, so they follow the Arctic theme.
- **bash**, even if you picked another shell.

Your browser, office suite, video player and file manager become the defaults for opening web
links, documents, videos and folders.

## Get apps

![The Get apps console suggesting packages for a typed name](images/get-apps.png)

**Get apps** is a small console for installing software. Open it with `Super + Shift + A`, or
choose **Get apps** in the launcher (`Super + Space`).

What you can type:

| Type | Does |
|---|---|
| `htop` | Installs `htop` from Fedora (`pkexec dnf5 install -y htop`). You can list several names. |
| `flathub:org.gimp.GIMP` | Installs an app from Flathub (`flatpak install -y flathub org.gimp.GIMP`) |
| `dnf search editor` | Searches Fedora's packages. `dnf info`, `dnf list` and other questions run without a password. |
| `dnf install …`, `dnf remove …`, `dnf upgrade` | Runs as `pkexec dnf5 … -y` |
| `flatpak install flathub …`, `flatpak uninstall …`, `flatpak update` | Runs as typed, with `-y` added |

- **Installs run on their own.** Nothing stops at dnf's or Flatpak's `Is this ok [y/N]`: the
  console answers yes for you (unless you typed `-y` or `--assumeno` yourself).
- **Your password is asked once, in a dialog.** dnf runs through `pkexec`, so the desktop's
  password dialog appears; type your account password there. It's remembered for a few minutes,
  so a second install right after the first doesn't ask again. Installing from Flathub needs no
  password at all.
- As you type an app's name, matching packages from Fedora and Flathub are suggested. `Tab`
  completes a name. The list of names is saved on your computer and refreshed once a day; the
  **Refresh list** button updates it now.
- If a command still asks for something in the console (for example a `sudo` you typed), answer
  there. A password is hidden as you type and never saved or logged.
- `Ctrl + C` (or **Stop**) stops the running command. **Clear** empties the console.
- A Flatpak app installed here gets its Arctic colours straight away (Zed, for example).

It runs `dnf` and `flatpak` only; it isn't a general terminal. The installer's messages mention
"the Software app": that's Get apps.

## dnf: Fedora's packages

Arctic Linux uses Fedora 44's package repositories, and the installer adds RPM Fusion. From a
terminal:

```sh
dnf search thunderbird            # find a package
sudo dnf install thunderbird      # install it
sudo dnf remove thunderbird       # remove it
sudo dnf upgrade                  # update everything installed with dnf
```

## Flatpak and Flathub

Flathub has many desktop apps, each running in its own sandbox. If you installed any Flatpak app
in the installer (the defaults include Zen, Zed and Collabora Office) or ticked **Flathub**, the
Flathub remote is already set up. If it isn't, add it once:

```sh
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
```

Then:

```sh
flatpak search spotify
flatpak install flathub com.spotify.Client
flatpak update                    # update every Flatpak app
flatpak list                      # what's installed
```

Installed Flatpak apps appear in the launcher.

## Nix

The Nix package manager comes preinstalled, with its background service running and the SELinux
settings it needs (Arctic's `arctic-selinux` package). It's handy for command-line tools that
aren't in Fedora, or for newer versions. For graphical apps, use Flatpak: apps from Nix often
can't use the graphics card on Fedora without extra setup.

Nix's newer commands are switched off by default, so pass the option each time:

```sh
nix --extra-experimental-features 'nix-command flakes' run nixpkgs#cowsay -- hello
nix --extra-experimental-features 'nix-command flakes' profile add nixpkgs#ripgrep
```

or turn them on once for your account:

```sh
mkdir -p ~/.config/nix
echo 'experimental-features = nix-command flakes' >> ~/.config/nix/nix.conf
nix profile add nixpkgs#ripgrep
```

Open a new terminal afterwards so the new commands are found.

## Updates

Everything installed with dnf (the system, Arctic's own packages, apps from Fedora and RPM
Fusion) updates by itself: downloaded in the background every day and installed the next time
the computer starts. Arctic's own packages come from its signed package repository. The
**Updates** page in Settings (`Super + S`) shows what's waiting and switches the channel; see
[Updates](Updates). Flatpak and Nix apps you update yourself:

```sh
flatpak update        # Flatpak apps
nix profile upgrade --all    # Nix packages in your profile (with the options above)
```

## Changing which app opens

`Super + Enter`, `Super + W`, `Super + E`, `Super + F` and `Super + Shift + F` open the apps you
picked in the installer. To change them, and the apps that open links and files, open Settings
(`Super + S`) and choose **Default apps** (see [Settings](Settings#default-apps)). The files
behind it are on
[Themes and customisation](Themes-and-Customisation#default-apps).
