# Arctic Linux

![The Arctic Linux desktop in the Polar night theme](images/live-desktop.png)

Arctic Linux is a calm, keyboard-first desktop built on **Fedora 44** and the **Mango** tiling
window manager. Its look comes from the arctic fox: snow-white and blue-grey surfaces, rounded
corners, and one warm amber colour that shows you where you are.

One USB stick does everything. Start your computer from it to **try Arctic Linux** without
changing anything, then **install it** when you're ready. The installer asks one plain question
per screen, encrypts your disk by default and only downloads the apps you pick.

## Start here

| You want to… | Read |
|---|---|
| Put Arctic Linux on a USB stick | [Download and create a USB](Download-and-Create-a-USB) |
| Look around without installing | [Try Arctic Linux](Try-Arctic-Linux) |
| Install it on your computer | [Install Arctic Linux](Install-Arctic-Linux) |
| Know what happens the first time it starts | [First boot](First-Boot) |
| Learn your way around the desktop | [Desktop tour](Desktop-Tour) and [Keyboard shortcuts](Keyboard-Shortcuts) |
| Add, remove or change apps | [Apps and software](Apps-and-Software) |
| Change colours, wallpaper and settings | [Themes and customisation](Themes-and-Customisation) |
| Use the terminal | [Terminal and shell](Terminal-and-Shell) |
| Fix something that isn't working | [Troubleshooting](Troubleshooting) and [FAQ](FAQ) |

## What you get

- **Mango**, a tiling window manager for Wayland. Windows arrange themselves side by side with
  small gaps and rounded corners, and the window you're using has an amber border.
- **A desktop shell** made for Arctic Linux: the top bar, a launcher that also works as a
  calculator and a command runner, a wallpaper picker, a **Get apps** console, volume and
  brightness pop-ups, a power menu and a lock screen.
- **Two themes**, Winter (light) and Polar night (dark). `Super + Shift + T` switches the whole
  desktop between them.
- **kitty and zsh** with an animated fox greeting in every new terminal.
- **Default apps you can swap in the installer:** Zen Browser, Zed, kitty, zsh, yazi, Thunar,
  Collabora Office and VLC. Flatpak and Nix come preinstalled.
- **Disk encryption on by default** (LUKS2), with the btrfs file system.

Everything has a keyboard shortcut, and everything also works with a mouse or touchpad.
Press `Super + /` on the desktop to see every shortcut.

## For developers

- [Building from source](Building-from-Source): the RPMs, the live ISO and the VM tests.
- [Architecture](Architecture): how the live session, the installer and the desktop fit together.
- [Design system](Design-System): colours, type, spacing and motion.
- [Contributing](Contributing): how to work on Arctic Linux.
- [Release notes](Release-Notes): what's in each version, what isn't yet, and upgrading from 0.1.

## About this wiki

These pages live in [`docs/wiki`](https://github.com/yuvalkolodkingal/O-Tism/tree/main/docs/wiki)
in the repository and are published here by GitHub Actions, so a change to the docs goes through
the same review as a change to the code. Most screenshots were taken from Arctic Linux 0.1
running in a virtual machine (`tools/screenshot-tour.sh`), so small details may differ in later
versions. The installer screenshots use its demo mode, so the disks, networks and names in them
are examples.
