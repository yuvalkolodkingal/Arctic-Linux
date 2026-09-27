# Apps and software

Arctic Linux starts with a small set of apps you pick in the installer. Afterwards you can add
almost anything from three places: Fedora's own packages (dnf), Flathub (Flatpak) and Nix.

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

| Section | Apps | How they're installed |
|---|---|---|
| **Browser** (pick one) | Zen Browser · Firefox · Chromium | Zen: Flathub. Firefox and Chromium: Fedora, with Flathub as a fallback (for Chromium, the Ungoogled Chromium Flatpak). |
| **Editor** (pick any) | Zed · VSCodium · Neovim · Helix | Zed and VSCodium: Flathub. Neovim and Helix: Fedora (they open in your terminal). |
| **Terminal** (pick one) | kitty · Alacritty · foot | Fedora |
| **Shell** (pick one) | zsh · fish · bash | Fedora. bash is always installed; picking it makes it your login shell. |
| **File manager** (pick any) | yazi · Thunar · Nautilus | yazi: COPR (Nix fallback). Thunar and Nautilus: Fedora. |
| **Office** (pick one or none) | Collabora Office · LibreOffice · ONLYOFFICE | Flathub. LibreOffice falls back to Fedora's packages. |
| **Video** (pick any) | VLC · mpv · Celluloid | VLC and mpv: Fedora (mpv has a Flathub fallback). Celluloid: Flathub. |
| **Extras** (pick any, none ticked) | Flathub · Steam · GIMP · Inkscape · Signal · OBS Studio | Flathub. The **Flathub** entry only adds the Flathub app store, with no app. |

When an app has more than one source, the installer tries them in the order above and uses the
first that works.

The installer also always adds, whatever you pick:

- **Media codecs**: the RPM Fusion repositories (free and nonfree), full FFmpeg and OpenH264, so
  most video and audio formats play.
- **Flatpak** and **Nix**, ready to use.
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
| `htop` | Installs `htop` from Fedora (`sudo dnf install htop`). You can list several names. |
| `flathub:org.gimp.GIMP` | Installs an app from Flathub (`flatpak install flathub org.gimp.GIMP`) |
| `dnf search editor` | Searches Fedora's packages. `dnf info`, `dnf list` and other questions run without a password. |
| `dnf install …`, `dnf remove …`, `dnf upgrade` | Runs as `sudo dnf …` |
| `flatpak install flathub …`, `flatpak uninstall …` | Runs as typed |

- As you type an app's name, matching packages from Fedora and Flathub are suggested. `Tab`
  completes a name. The list of names is saved on your computer and refreshed once a day; the
  **Refresh list** button updates it now.
- When a command asks for your password, type your account password in the console. It's hidden
  as you type and never saved or logged.
- When dnf asks `Is this ok [y/N]`, type `y` and press `Enter`.
- `Ctrl + C` (or **Stop**) stops the running command. **Clear** empties the console.

It runs `dnf` and `flatpak` only; it isn't a general terminal. The installer's messages mention
"the Software app": in version 0.1, that's Get apps.

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

```sh
sudo dnf upgrade      # the system and apps: Fedora, RPM Fusion and Arctic's own packages
flatpak update        # Flatpak apps
nix profile upgrade --all    # Nix packages in your profile (with the options above)
```

Arctic's own packages (the desktop, shell, branding and Mango) come from the signed Arctic
package repository and update together with Fedora's. You don't have to run `dnf upgrade`
yourself: updates download in the background and are installed at the next restart. See
[Updates](Updates). Installed Arctic Linux 0.1? Its Arctic repository is switched off; see
[Upgrading from 0.1](Release-Notes#upgrading-from-01).

## Changing which app opens

`Super + Enter`, `Super + W`, `Super + E`, `Super + F` and `Super + Shift + F` open the apps you
picked in the installer. To change them, see
[Themes and customisation](Themes-and-Customisation#default-apps).
