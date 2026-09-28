# FAQ

## About Arctic Linux

### What is Arctic Linux?

A desktop operating system built on **Fedora 44**. It uses Fedora's packages and repositories,
and adds its own desktop (the Mango window manager and a shell written for it), a look based on
the arctic fox, a step-by-step installer and a set of apps you choose while installing.

### Is it Fedora?

Underneath, yes: the kernel, the system and most packages are Fedora's, and `sudo dnf upgrade`
updates them from Fedora's servers. Arctic Linux replaces Fedora's branding and release files with
its own, and adds its desktop on top. It's an independent project, not an official Fedora edition.

### Is it free?

Yes. Arctic Linux's own code is under the MIT licence; the fonts are under the SIL Open Font
Licence, and the Nix SELinux policy under the LGPL. The apps it installs keep their own licences.
Apps that aren't open source are marked **Proprietary** in the installer. The drivers it offers
for your hardware come from RPM Fusion: the NVIDIA and Broadcom drivers aren't open source, and
the Intel and AMD video drivers include formats Fedora can't ship. You can untick all of them.

### Who is it for?

People who'd like a calm, tidy desktop that mostly stays out of the way, and who enjoy (or want to
learn) using the keyboard. You don't need to know Linux to install it: the installer explains
each step in plain words.

### What's a tiling window manager?

Instead of piling windows on top of each other, a tiling window manager places them side by side
so they fill the screen without overlapping. Open a second window and the screen splits in two;
close one and the other grows back. You can still make any window float with `Super + T`. See
[Desktop tour](Desktop-Tour#windows-and-workspaces).

### What's Mango?

[Mango](https://github.com/mangowm/mango) (MangoWM) is the Wayland window manager Arctic Linux
uses. It draws the windows, borders, gaps and animations. Arctic Linux 0.2 ships Mango 0.17.3, packaged
as `mangowm` in the Arctic package repository, so it updates with the rest of the system.

## Trying and installing

### Does trying it change my computer?

No. **Try Arctic Linux** runs entirely from the USB stick and memory. Nothing is written to your
disks, and nothing you do is kept after you restart.

### Can I keep Windows?

Yes. Make at least 40 GB of free space in Windows first, then choose **Install alongside Windows**
in the installer. You pick which system to start each time the computer starts. See
[Installing alongside Windows](Install-Arctic-Linux#installing-alongside-windows).

### Why does the installer need the internet?

Only some apps are on the USB stick. The others (for example Zen Browser, Zed and Collabora
Office by default) are downloaded while Arctic Linux installs, along with the media codecs. That
keeps the USB image small and the apps current.

### How long does installing take?

About 10 minutes on a typical computer, plus the time to download your apps. The download size
is shown on the Apps step.

### Do I have to encrypt my disk?

No, but it's on by default and we recommend it: if your computer is lost or stolen, nobody can
read your files. You can turn it off on the Encryption step. If you keep it, don't forget the
passphrase: there's no way to recover the files without it.

### Can I use one password for everything?

Yes. On the Account step, turn on **Use this password for the disk passphrase too**. You can also
turn on **Log in automatically**, so you type your password only once, when the computer starts.

### Does it work on older computers?

It needs a 64-bit (x86_64) PC. Both UEFI and older BIOS computers are supported, and it needs a
disk of at least 40 GB.

### Does Secure Boot work?

Yes. The USB stick and the installed system both start through Fedora's signed boot loader (shim),
which is what Secure Boot checks. If your computer refuses to start it, see
[Troubleshooting](Troubleshooting#the-usb-stick-doesnt-start).

If you install the NVIDIA or Broadcom Wi-Fi driver, there's one extra step at the first restart:
a blue **Perform MOK management** screen, where you confirm the driver's key with a code the
installer shows you. You don't have to turn Secure Boot off. See
[Drivers](Drivers#secure-boot-confirming-the-drivers-key).

### What about NVIDIA graphics?

From version 0.2 the installer finds NVIDIA cards and installs NVIDIA's own driver, ticked in a
**Drivers** section of the Apps step: the current driver for GeForce RTX 20, GTX 16 and newer, and
the 580 series for GTX 750 to 1080 Ti. It's built for your kernel while installing, so it works
from the first login. On the live USB the open driver is used; if the screen stays black there,
use **Safe graphics mode**. See [Drivers](Drivers).

### What other drivers does it set up?

Only what your computer needs: video acceleration for Intel and AMD graphics (so H.264 and H.265
video plays on the graphics chip), and Broadcom's driver for the Broadcom Wi-Fi cards that have no
working open driver. Each shows up ticked in the **Drivers** section only when the installer finds
that hardware. See [Drivers](Drivers).

### I installed 0.1 and my login keeps going back to the login screen.

That's a known 0.1.0 bug: the installer left the home folder without SELinux labels. A one-time
relabel fixes it; see
[Troubleshooting](Troubleshooting#the-login-screen-goes-straight-back-after-the-password).
The 0.2 installer doesn't have this problem.

## Using Arctic Linux

### How do I install an app?

Press `Super + Shift + A` for **Get apps**, pick **Flathub apps** or **Fedora packages**, type the
app's name and press `Enter`. You can also use `dnf`, `flatpak` or Nix from a terminal. See
[Apps and software](Apps-and-Software).

### How do I remove an app?

Select it in the launcher (`Super + Space`) and press `Shift + Delete`, or open **Get apps → Remove
apps**. You see exactly what goes before anything is removed. Packages Arctic Linux needs (the
desktop, Blueman, the volume control, your only terminal, your login shell) can't be removed
there, and the page says why. See [Remove apps](Apps-and-Software#remove-apps).

### Where's the Software app the installer mentions?

That's **Get apps** (`Super + Shift + A`).

### Is there a settings app?

Yes, from version 0.2: **Settings** (`Super + S`, or the first item of the power menu). It
changes the look, windows, displays, keyboard and mouse, shortcuts, default apps, network,
Bluetooth, sound, updates, power and startup apps. See [Settings](Settings).

### How do I update?

You don't have to: updates download in the background every day and are installed the next time
the computer starts (the bar shows **Restart to update** when some are waiting). To check now,
run `arctic-update now`; Flatpak apps update with `flatpak update`. See [Updates](Updates).

### How do I switch to a light theme?

Press `Super + Shift + T`, or pick Winter in [Settings](Settings#appearance), **Appearance**. See
[Themes and customisation](Themes-and-Customisation).

### I don't have a Super key.

`Super` is the key with the Windows logo on most PC keyboards (between `Ctrl` and `Alt`), and
`Command` on Apple keyboards. Everything on the bar also works with the mouse.

### How do I see every shortcut?

`Super + /`. Or read [Keyboard shortcuts](Keyboard-Shortcuts).

### Can I use GNOME or KDE apps?

Yes. Any app from Fedora or Flathub runs, whichever desktop it was made for.

### Can I install a different desktop?

Arctic Linux has one desktop session, Mango. Fedora's other desktops are in its repositories,
but mixing them with Arctic's desktop isn't something we've tested.

### Where are my settings?

What you change in [Settings](Settings) goes to `~/.config/mango/settings.conf` and a few files in
`~/.config/arctic/` (the page lists them all). Your own hand-written settings are in your home
folder too: `~/.config/mango/user.conf` for the window manager,
`~/.config/kitty/user.conf` for the terminal, `~/.zshrc.local` for zsh and
`~/.config/arctic/` for the theme, wallpaper and default apps. See
[Themes and customisation](Themes-and-Customisation#your-own-settings-files).

### Can I snapshot or roll back my system?

Yes, from version 0.2. The system uses btrfs, and snapper takes a snapshot before and after every
dnf transaction, so you can put back files an update changed. See
[Updates](Updates#snapshots).

## The project

### Why do some links say O-Tism?

The repository was called O-Tism until 0.2.1, when it was renamed Arctic-Linux. GitHub forwards
the old repository links, but not the package repository on GitHub Pages: 0.2.0 systems need a
one-line fix to keep getting updates (see
[Troubleshooting](Troubleshooting#updates-stopped-after-the-repository-was-renamed)). The Go
module path inside the source still says `o-tism`.

### How can I help?

Try it, report what doesn't work, and see [Contributing](Contributing).
