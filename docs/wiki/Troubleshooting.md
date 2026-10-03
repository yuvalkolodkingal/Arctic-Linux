# Troubleshooting

Something not working? Find the closest heading below. If nothing here helps, open an
[issue](https://github.com/yuvalkolodkingal/Arctic-Linux/issues) and include what you tried and, for
installer problems, the log (see [Saving the installer log](#saving-the-installer-log)).

## Starting from the USB stick

### The USB stick doesn't start

- **Use the boot menu key** while the computer starts (often `F12`, `F11`, `F10`, `F8` or `Esc`)
  and pick the USB stick. On some computers it's listed twice; try the entry with "UEFI" in it
  first.
- **Try another USB port**, preferably one directly on the computer rather than a hub.
- **Write the stick again**, after [checking the download](Download-and-Create-a-USB#2-check-the-download).
  That rules out a damaged download or a badly written stick.
- **Secure Boot:** the stick uses Fedora's signed boot loader, which most computers accept. If
  yours refuses it, turn Secure Boot off in the firmware settings, or look for an option to allow
  Microsoft's third-party UEFI certificate.

### The screen stays black or looks wrong

Choose **Safe graphics mode** in the boot menu. It starts the same live session with basic
graphics (the `nomodeset` option), which works on almost any screen but may be slower and may not
support every resolution. Arctic Linux also allows software drawing when there's no working
graphics driver, which is what virtual machines and Safe graphics mode need.

If Safe graphics mode works but the normal entry doesn't, the graphics driver is the likely
problem. The live USB always uses the open drivers; NVIDIA cards often need Safe graphics mode
there. The installer then sets up NVIDIA's own driver for the installed system (see
[Drivers](Drivers)).

### Arctic Linux behaves strangely or crashes on the live USB

Choose **Check USB for errors** in the boot menu. It reads the whole stick and checks it before
starting. If it finds errors, write the stick again, or use another stick.

### The welcome card doesn't appear

On a slow computer the desktop can take a while to start; the card waits up to a minute for it.
You can always start the installer with `Super + I` or the **Install** item on the bar.

## Installing

### "No disk to install on"

Arctic Linux needs a disk of at least 40 GB that isn't the USB stick you started from. Some
computers hide their internal disk behind a RAID or "Intel RST" setting; switching the storage
mode to AHCI in the firmware settings makes it visible (Windows may need preparing for that
change first).

### "Install alongside" isn't offered

The choice only appears when the disk you picked has all of these:

- **At least 40 GB of free, unused space.** Arctic Linux doesn't shrink other systems; make the
  space first (for Windows, see [Installing alongside Windows](Install-Arctic-Linux#installing-alongside-windows)).
- **An EFI system partition to share** (UEFI computers).
- **Room for two more partitions** on older MBR disks, which allow only four.

### I can't get past the network step

Next stays off until you're online, because the installer downloads your apps.

- Plug in a network cable if you can; the step then passes by itself.
- *"Wrong password. Check it and try again."* The Wi-Fi password is case-sensitive.
- *"No Wi-Fi networks found."* Move closer to the router, or check that Wi-Fi isn't switched off
  with a key or switch on the laptop.

### The passphrase or password isn't accepted

Since Arctic Linux 0.2.1 a short or weak passphrase or password is never refused: the installer
may warn that it's easy to guess (a disk passphrase below **Fair**, a password under 8
characters), and **Next** stays on. If **Next** is still off:

- Type it in both fields, the same way. *"Passphrases don't match yet."* or *"Passwords don't
  match yet."* means the second field differs; **Show** (the eye) lets you compare them.
- With a Hebrew, Arabic, Greek, Russian or Ukrainian keyboard, the disk passphrase (and the
  password, with **Use this password for the disk passphrase too**) must use English (US)
  letters, numbers and symbols.

The warning *"This passphrase is easy to guess"* is advice, not an error. For a stronger one,
**Suggest a passphrase** makes one from four random words; a short sentence also works.
Arctic Linux 0.2.0 and older required **Fair** for the disk passphrase and 8 characters for the
password.

### "That name is taken by the system"

Some usernames are already used by Arctic Linux itself (for example `root`). Pick another. A
username starts with a lowercase letter and uses only lowercase letters, numbers, `-` and `_`, up
to 32 characters.

### The install stops at "removing live-only packages" (Arctic Linux 0.1)

Arctic Linux 0.1.0 could fail on real computers at this point, with scriptlets failing with exit
code 127 in the log: the copied system had no SELinux labels yet, so SELinux stopped the package
scripts from running. The same bug also made some finished 0.1 installs refuse every login (see
[The login screen goes straight back](#the-login-screen-goes-straight-back-after-the-password)).
The 0.2 installer labels the system right after copying it, and again at the end, including
`/home`, `/var/log`, `/nix` and `/boot`. Download the 0.2 image
(`Arctic-Linux-1.1-x86_64.iso`) and write the stick again.

### "The NVIDIA driver couldn't be installed"

*"The driver didn't build for this computer's kernel."* The driver is built on the computer
while installing (see [Drivers](Drivers#how-the-nvidia-and-broadcom-drivers-are-installed)). Press
**Try again**; if it keeps failing, press **Skip the driver**. The rest of the install carries on,
your card keeps the open-source driver, and you can
[add the driver later](Drivers#adding-a-driver-you-skipped). The same goes for the Broadcom Wi-Fi
driver.

### An app couldn't be downloaded

The installer pauses on **One app needs attention**. Press **Try again** first: most download
problems are brief. If it keeps failing, press **Skip {app}**. The rest of the install carries on
and you can add the app later with [Get apps](Apps-and-Software#get-apps).

### The install failed at the very end (Arctic Linux 0.2.0, encrypted disk)

On some computers (seen on an NVIDIA laptop) 0.2.0 finished installing and then failed at
**Setting up your account** with *"cryptsetup close … Device or resource busy"*: the encrypted
disk was still held by something the install had started, and the installer then removed the
new boot entry. Install again with 0.2.1: it lets go of the disk properly, and a disk that still
can't be closed at the very end no longer counts as a failure. The Done screen then says so;
restarting closes it and nothing is lost.

### "Something went wrong while installing"

A part of the system itself couldn't be installed.

1. Press **Save log to USB** (see below) so you have the details.
2. Press **Try again**. The installer checks the disk again and starts over.
3. If the problem is one of your answers (for example the disk), press **Change your answers** to go
   back to the Summary with everything kept, change it, and install again.

**Show details** shows the error message itself. If you installed alongside another system, the
partitions the installer added are removed again after a failure; your other system is left as it
was.

### "The disk changed since you picked it"

The disk you chose was unplugged, replaced, or its partitions changed after you picked it. Go back
to the Disk step, check your choice and continue.

### Saving the installer log

**Save log to USB** writes a file called `arctic-install-<date>-<time>.log`:

- **To a USB stick**, if one is plugged in that is formatted as FAT or exFAT (most sticks are) and
  isn't the Arctic Linux stick. A Ventoy stick you started Arctic Linux from counts as the Arctic
  Linux stick and is skipped (its partition is busy while the live session runs). When the message
  says *"You can unplug it now"*, it's safe to remove.
- **Otherwise to `/home/liveuser`** in the live session. That copy is lost when the computer
  restarts, so plug in a second USB stick and save again to keep it.

In the live session, the installer's full log is also at `/var/log/arctic-install/engine.log`.
After a successful install, a copy is kept on the new system in `/var/log/arctic-install/`.

## After installing

### The computer starts Windows (or the old system) instead of Arctic Linux

Open the firmware's boot menu and choose **Arctic Linux**, or move it to the top of the boot order
in the firmware settings. If you installed alongside another system, the Arctic Linux menu lists
both.

### A blue screen says "Perform MOK management"

That's the one step Secure Boot needs for the NVIDIA or Broadcom driver. Press any key within 10
seconds, choose **Enroll MOK**, **Continue**, **Yes**, type the one-time code from the installer's
Done screen, then **Reboot**. Missed it, or lost the code? Arctic Linux still starts, only without
the driver; see [Missed the blue screen](Drivers#missed-the-blue-screen).

### The NVIDIA or Wi-Fi driver isn't working

- **With Secure Boot on**, the driver only starts once its key is enrolled (above). Check with
  `mokutil --test-key /etc/pki/akmods/certs/public_key.der`.
- **Installed offline**, the driver is installed the first time the computer is online, and starts
  after the restart that follows.
- **Black screen, or it stopped after an update:** see [Drivers](Drivers#troubleshooting), which
  also covers going back to `nouveau` and rebuilding with `akmods`.
- `nvidia-smi` shows whether NVIDIA's driver is running.

### The disk passphrase isn't accepted

- Check Caps Lock; a hint appears when it's on.
- With a Hebrew, Arabic, Greek, Russian or Ukrainian keyboard, type it with the English (US)
  layout, as the installer asked.
- If you used **Use this password for the disk passphrase too**, type your account password.

There's no way to recover an encrypted disk without its passphrase.

### The login screen doesn't accept my password

Check Caps Lock (the login screen shows a hint) and the keyboard layout shown in the bottom-right
corner. If you picked a non-Latin layout, English (US) comes first and `Alt + Shift` switches.

### The login screen goes straight back after the password

The password is right, but the desktop can't start. On systems installed with Arctic Linux
0.1.0 the usual cause is missing SELinux labels on your home folder: the login can't enter it and
returns to the login screen. Relabel the whole system once:

1. Restart, and in the boot menu (it shows for 5 seconds) press `e` on the first entry.
2. At the end of the line that starts with `linux`, add a space and `autorelabel=1`, then press
   `Ctrl + X`.
3. The computer labels every file (a few minutes) and restarts by itself. Log in normally.

If you can log in on a text console (`Ctrl + Alt + F3`), `sudo touch /.autorelabel` and a restart
do the same. Installs made with 0.2 are labelled correctly. If it isn't SELinux, see
[The desktop has no bar](#the-desktop-has-no-bar-or-the-launcher-doesnt-open) and the session
log (`journalctl -b` from a text console).

### The desktop has no bar, or the launcher doesn't open

The keyboard shortcuts still work without the bar. Press `Super + Enter` for a terminal and restart
the shell:

```sh
arctic-shell --restart
```

To see why it stopped, run it in the terminal with its log:

```sh
arctic-shell --stop
arctic-shell --foreground
```

If it still won't run, switch to the **fallback desktop** (waybar, fuzzel and swaylock). Add this
line to `~/.config/mango/user.conf`, then log out (`Super + Esc`) and back in:

```ini
env=ARCTIC_SHELL,waybar
```

Your shortcuts stay the same. Delete the line to go back to the Arctic shell. If a change of your
own in `~/.config/mango/` is the cause, move `user.conf` away and press `Super + Shift + R`.

### No network

- Click the network icon on the bar (`Super + Ctrl + W`) to pick a Wi-Fi network; see
  [Menus on the bar](Bar-Menus#network-and-wi-fi-super--ctrl--w). **Edit connections…** at the
  bottom opens the connection editor.
- **"“Home” needs its Wi-Fi password again":** the saved password stopped working (the router's
  password changed). Click **Enter password** in the notification and type the new one.
- **A company or school network (eduroam) won't join:** check the sign-in method with your IT
  department; networks that need a certificate of your own are set up in **Edit connections…**.
- From a terminal:

  ```sh
  nmcli device wifi list
  nmcli device wifi connect "My network" --ask
  ```

### Updates stopped after the repository was renamed

The project moved from `github.com/yuvalkolodkingal/O-Tism` to
`github.com/yuvalkolodkingal/Arctic-Linux`, and its package repository moved with it to
<https://yuvalkolodkingal.github.io/Arctic-Linux/>. GitHub Pages doesn't forward the old
address, so a system installed from **0.2.0** looks for Arctic's updates in the wrong place (dnf
skips the repository quietly). Fedora's updates are not affected. Run this once:

```sh
sudo dnf upgrade --refresh --setopt=arctic.baseurl=https://yuvalkolodkingal.github.io/Arctic-Linux/repo/stable/fedora-44/x86_64/ arctic-release
```

It brings the new `arctic-release`, which has the new address built in; from then on updates
work as before (`sudo dnf upgrade`, or wait for the automatic update). Nothing is left behind to
undo. If you use the testing channel, run it with `arctic-testing.baseurl=…/repo/testing/…`
instead.

### An app is missing after installing

- **You skipped it in the installer:** install it with [Get apps](Apps-and-Software#get-apps).
- **It was put off during an automated install:** it's in `/var/lib/arctic/pending.json`, and
  `arctic-firstboot` installs it once you're online. Check on it, or try again now:

  ```sh
  cat /var/lib/arctic/pending.json
  journalctl -u arctic-firstboot
  sudo systemctl start arctic-firstboot
  ```

- **`Super + B` (or E, F) says "No app set":** the app for that role isn't installed. Install one,
  or set another in `~/.config/arctic/default-apps` (see
  [Themes and customisation](Themes-and-Customisation#default-apps)).

### SELinux

SELinux is on (enforcing), as on Fedora. The installer labels every file before it finishes. If
that step fails, it marks the system to relabel itself on the first start instead, which takes a
few minutes and restarts the computer once.

If something is blocked and you suspect SELinux:

```sh
getenforce                          # should print Enforcing
sudo ausearch -m avc -ts recent     # recent SELinux denials
```

To relabel the whole system at the next start:

```sh
sudo touch /.autorelabel
sudo reboot
```

For Nix, Arctic's `arctic-selinux` package labels `/nix`. If Nix commands are denied after you
moved or restored `/nix`, restore the labels with `sudo restorecon -R /nix`.

### Sound, Bluetooth or brightness

- **Sound:** click the volume icon on the bar for the sound menu: where sound plays, the
  microphone and a volume per app. A device's `…` (or the `›` on its slider) switches between
  headphones and speakers and picks the profile (for example a headset's microphone mode).
- **Bluetooth:** the Bluetooth icon only appears when the computer has a Bluetooth adapter. Click it
  for the Bluetooth menu. **Pair a new device** shows codes in Arctic's own dialog; if no dialog
  appears while pairing, another Bluetooth program (such as Blueman's applet) took over pairing:
  close it, open the menu's pairing page again and retry.
- **The "Mic" or "Camera" indicator doesn't show for an app:** it shows for apps that use the
  microphone or camera through PipeWire (browsers, OBS, video calls). Apps that open the camera
  device directly aren't seen.
- **Broadcom Wi-Fi:** some Broadcom cards only work with the driver the installer adds; see
  [Drivers](Drivers#wi-fi-doesnt-work-on-a-broadcom-card).
- **Brightness keys:** these change the built-in screen; external monitors usually have their own
  buttons.

### The screen locks too soon, or the computer sleeps

The screen locks after 5 minutes without use and the computer suspends after 15. Change the
times (or turn them off) in [Settings](Settings#power-and-lock) (`Super + S`), **Power and lock**.
They're saved in `~/.config/arctic/idle.conf` (`lock_after=` and `suspend_after=`, in seconds, 0
for never) and apply at once. The same file holds `lock_after_battery=` and
`suspend_after_battery=` (on battery), `dim_before_lock=` (seconds; 0 turns dimming off) and
`screen_off_after=` (seconds after the lock; 0 leaves the screens on).

The screens turn off a minute after the lock; a key or the mouse turns them on again. If a
screen doesn't come back on your hardware, set **Turn the screens off after locking** to
**Never** and tell us in an issue.

### A shortcut I made doesn't work

- **Settings > Shortcuts says "Doesn't run":** Arctic uses those keys now (0.3 moved the browser to
  `Super + B` and added `Super + Shift + S`, `Alt + Tab` and others), and Arctic's shortcuts come
  first. Remove yours and add it on another key.
- **It holds Alt and Shift:** with two keyboard layouts, `Alt + Shift` switches the layout, so such
  a shortcut switches it too. Pick other keys, or another switch key in Settings.
- **You replaced `binds.conf` with your own copy:** it doesn't get Arctic's new shortcuts. Compare
  it with `/usr/share/arctic/mango/binds.conf`.

### Screen sharing shows no list of screens

The list comes from `/etc/xdg/xdg-desktop-portal-wlr/mango`, which xdg-desktop-portal-wlr reads in
Mango sessions. Log out and back in after installing Arctic's update (the portal reads its
settings when it starts), or run `systemctl --user restart xdg-desktop-portal-wlr`.

### Recording won't start

`Super + Alt + R` tries your graphics card's video encoders, then one on the processor. What
went wrong is in `$XDG_RUNTIME_DIR/arctic/record.log` (`/run/user/1000/arctic/record.log`), and
`~/.cache/arctic/record-codec` remembers the encoder that worked (delete it to try them all
again). `wf-recorder` must be installed.

### A setting doesn't stick

- Settings shows a note on the row when your own `~/.config/mango/user.conf` sets the same thing:
  `user.conf` is read last and wins. Remove the line there.
- A display you switch off in Settings comes back at the next login, on purpose.
- Startup apps start from the next login.
- To undo changes, press `Ctrl + Z` in Settings, or use the copies in
  `~/.local/state/arctic/settings-backups/`. See [Settings](Settings#if-settings-wont-open).

## Getting more information

| What | Command |
|---|---|
| Your desktop session's messages | `journalctl --user -b` |
| The whole system's messages since start-up | `journalctl -b` |
| Services that failed | `systemctl --failed` |
| Which Arctic Linux you have | `cat /etc/os-release` (or Settings, **About**) |
| Graphics driver in use | `lspci -k \| grep -EA3 'VGA\|3D'`, `nvidia-smi` |
| Secure Boot and the driver key | `mokutil --sb-state`, `mokutil --test-key /etc/pki/akmods/certs/public_key.der` |
| The shell with its log | `arctic-shell --stop; arctic-shell --foreground` |
