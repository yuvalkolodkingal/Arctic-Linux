# Updates

Arctic Linux keeps itself up to date with plain `dnf`, the standard Fedora updater. Once a day
it downloads and installs updates in the background, while you work. Most updates need nothing
from you. Only a new kernel, a graphics driver or firmware needs a restart to start working, and
the computer never restarts by itself.

## How updates work

1. **A check every day.** About ten minutes after the computer starts, and once a day after
   that, Arctic Linux looks for updates to everything installed with dnf: Fedora's packages,
   Arctic's own (the desktop, the shell, Mango, the installer's apps), RPM Fusion and any other
   repository you added. Flatpak apps are updated every day too, in their own way, and firmware
   when you ask (see [below](#flatpak-apps-firmware-and-nix)).
2. **Installed in the background.** It runs `dnf upgrade`, at the lowest priority, with ten
   downloads at a time. A snapshot is taken before and after, so an update can be undone
   ([below](#snapshots)).
3. **A restart only when it is needed.** Afterwards dnf is asked whether anything it installed
   only starts working after a restart: a kernel, core system libraries, firmware, or a
   graphics driver such as NVIDIA's. If so the bar shows **Restart when you like**, and a
   notification says so once. Restart whenever it suits you; until then the computer keeps
   running what it was running.

An app that is updated while it is open keeps running its old version until you close and
reopen it; the desktop bar and launcher pick up their new version at your next login. On the
live USB nothing is downloaded: nothing there survives a restart.

**Kernels.** Two are kept: the one that is running, which is known to start, and the newest.
Each new kernel replaces the older spare (`installonly_limit=2`).

**Prefer updates at start-up?** `arctic-update install restart` goes back to how Arctic Linux
updated up to 1.2.2: updates are downloaded in the background and installed the next time the
computer starts, before the desktop. With an encrypted disk the passphrase is asked once: unless
a kernel, driver or firmware changed, the computer goes straight on to the login screen.
`arctic-update install now` returns to the default.

## What’s New after an Arctic update

After an existing account receives a new Arctic package build, the desktop shows a **What’s New**
card once at the next login. Closing it records that exact packaged update for this account, so
the same card does not interrupt later logins. A later Arctic update carries a different ID and
can show its own summary. Fresh accounts already see First Login, and the live USB never opens
the card automatically.

Open **Settings → Updates → Release notes** for the full notes. To reopen the installed summary
card itself, run:

```sh
arctic-shell-ipc whatsnew open
```

The card describes the package build installed on this computer. The release page remains the
source for an ISO's checksum, size and exact qualification results.

## The bar

| You see | It means |
|---|---|
| Nothing | Up to date, or updates were installed and need nothing from you. Open Settings for the last check or an error. |
| **Restart when you like** (amber, on the right of the bar) | Updates are installed; a new kernel, driver or firmware starts working after a restart. Click for the card. |
| **Restart to update** | Only with `arctic-update install restart` or `auto download-only`: updates are downloaded and will be installed the next time the computer starts. |

The card has **Restart now** (save your work first) and **Later**.
`arctic-shell-ipc updates toggle` opens the card from a key binding.

## The `arctic-update` command

Everything the daily check does, from a terminal. Commands that change something ask for your
password.

| Command | Does |
|---|---|
| `arctic-update` | Shows the channel, automatic updates, the last check and what's waiting |
| `arctic-update status --json` | The same as JSON, for scripts |
| `arctic-update now` | Checks and installs now, with dnf's progress. Says whether a restart is needed. |
| `arctic-update install` | Shows when updates are installed; `install now` (the default) or `install restart` changes it |
| `arctic-update now --sync` | The same, but syncs every package to the versions in the enabled repositories: after leaving testing, packages go back to the stable builds (this also downgrades anything newer than the repositories have, such as packages from updates-testing or your own builds) |
| `arctic-update now --replace` | Checks even when another command prepared an offline transaction (see [below](#offline-transactions-of-your-own)), and cancels that one |
| `arctic-update apply` | Restarts now and installs updates stored for a restart (`install restart`, `auto download-only`; asks first, `--yes` doesn't) |
| `arctic-update channel` | Shows the channel; `channel stable` or `channel testing` switches |
| `arctic-update auto` | Shows automatic updates; `auto on`, `auto download-only` or `auto off` changes them |
| `arctic-update metered` | Shows what happens on metered connections; `metered skip` or `metered allow` changes it |
| `arctic-update flatpak` | Updates your Flatpak apps now (see [below](#flatpak-apps-firmware-and-nix)) |
| `arctic-update firmware` | Lists firmware updates for this computer's devices; `firmware install` installs them |
| `arctic-update help` | The list of commands |

```text
$ arctic-update
Channel     stable (released builds)
Automatic   on: installs updates by itself, in the background
Metered     no downloads on metered connections
Last check  Sun 27 Sep 2026 06:12
Waiting     12 updates installed.
```

`sudo dnf upgrade` does exactly the same; use whichever you like. After your own dnf command
Arctic Linux also checks whether a restart is needed and tells you in the bar.

## Channels

For normal updates, keep **stable** selected. The enabled repository is **arctic**; **arctic-testing**
is disabled. **The testing channel is not required.** The v1.2.1 package set described in the
current release notes is prepared for qualification and publication; leave stable selected and
it will become available there after it is published. Both RPM signatures and signed repository
metadata are verified against the Arctic key shipped by `arctic-release`.

```sh
arctic-update channel stable
arctic-update now                # install the available signed updates
```

The Arctic signing-key fingerprint is
`80F75DE9A23B632246FD1FF1BD1A642B5436645A`. Fedora's own packages use Fedora's keys.
The stable repository is [available here](https://yuvalkolodkingal.github.io/Arctic-Linux/repo/stable/fedora-44/x86_64/).

Arctic's own packages come in two channels. Fedora's packages come from Fedora's repositories on
both.

| Channel | Builds | For |
|---|---|---|
| **stable** (the default) | Released versions, from the `main` branch | Everyday use |
| **testing** | Development builds, published on every push to the development branch | Trying new things first, and helping find problems before a release. They can break. |

```sh
arctic-update channel testing    # testing builds on top of stable
arctic-update now                # get them now
```

Switching back:

```sh
arctic-update channel stable
```

Packages you already updated from testing are newer than the stable ones, so they stay until a
newer stable build replaces them, usually at the next release. To go back to the stable builds
right away:

```sh
arctic-update now --sync
```

`--sync` is a `dnf distro-sync`: every package goes to the version in the repositories that are
enabled, not only Arctic's. Packages you installed from a repository that is disabled now
(updates-testing, say) or built yourself are moved back too; `dnf history` shows what changed.

Switching channels drops updates that were downloaded but not installed yet; the next check
downloads the right ones.

## Turning automatic updates off

```sh
arctic-update auto download-only   # download in the background, install with arctic-update apply
arctic-update auto off             # no daily check; arctic-update now checks by hand
arctic-update auto on              # back to the default
```

With `auto download-only` the updates are downloaded and kept for a restart: `arctic-update
apply` restarts and installs them, and `arctic-update now` installs everything right away
without a restart. `arctic-update now` always works, whatever this setting.

The settings live in `/etc/arctic/update.conf`, which you can also edit (`AUTO=`, `INSTALL=`
and `METERED=`); the next check reads them. `journalctl -u arctic-update-stage` shows what each
check did.

## Offline transactions of your own

dnf can prepare other changes for the next restart too: `sudo dnf install --offline <package>`,
or `sudo dnf system-upgrade download --releasever=45` for the next Fedora release. There is room
for one such change at a time, so Arctic Linux leaves yours alone: the daily check doesn't
download its updates while yours waits (`arctic-update` says so), and `arctic-update now` and
`arctic-update channel` stop and ask you to decide:

```sh
sudo dnf5 offline status           # what is waiting
sudo dnf5 offline reboot           # restart now and do it
sudo dnf5 offline clean            # or throw it away
arctic-update now --replace        # or cancel it and get Arctic's updates instead
```

Once yours is done or removed, the daily updates carry on.

## Metered connections

On a metered connection (a phone hotspot, a plan with a data cap) the daily check waits for a
connection that isn't metered. NetworkManager guesses which connections are metered (phone
hotspots usually are); you can say so yourself:

```sh
nmcli connection show                                  # the connection names
nmcli connection modify "Phone hotspot" connection.metered yes
```

To download updates on metered connections too:

```sh
arctic-update metered allow
```

`arctic-update now` always downloads, because you asked (it tells you when the connection is
metered).

## Undoing an update

Updates rarely go wrong, but when one does, there are several ways back. Try them in this order.

### Undo it with dnf

dnf remembers every transaction, including the updates installed at a restart:

```sh
dnf history list                  # the most recent first; note the ID
dnf history info 42               # what transaction 42 changed
sudo dnf history undo 42          # put the previous versions back
```

This needs the previous versions to still be available for download. Fedora keeps only the
newest update of each package, so for Fedora's packages it doesn't always work; the next ways
do.

### Start the previous kernel

If the computer doesn't start properly after an update that brought a new kernel, restart and
pick the entry with the older version number in the boot menu (it shows for 3 seconds; press
any arrow key to stop the countdown). Two kernels are kept: the one that was running when the
new one arrived, and the new one.

### Snapshots

Arctic Linux takes a snapshot of the system (a snapper snapshot of the root file system, `/`)
right before and right after every dnf transaction, including the updates installed at a
restart. The ten newest snapshots are kept (the last five transactions; `NUMBER_LIMIT` in
`/etc/snapper/configs/root`), older ones are deleted every hour. Your home folder is not part of
them, and neither are `/var/log` and `/nix`: they are separate subvolumes, so going back never
loses your files.

```sh
sudo snapper -c root list                           # the pairs: pre and post, with the dnf command
sudo snapper -c root status 41..42                  # which files changed between snapshot 41 and 42
sudo snapper -c root diff 41..42 /etc/some.conf     # how one file changed
sudo snapper -c root undochange 41..42              # put every changed file back as it was in 41
```

After `undochange`, restart. It restores files, not the list of installed packages that dnf
shows, so prefer `dnf history undo` when it works; use `undochange` when dnf itself is broken, or
to get back one configuration file (`undochange 41..42 /etc/some.conf`). Every `snapper` command
needs `sudo`: the snapshots are the whole system as it was, so only administrators, with their
password, can see, delete or restore them.

**Btrfs Assistant** shows the same snapshots in a window: browse them, compare files and restore
them. Tick it under **Utilities** (in **More apps**) in the installer, or install it with
`sudo dnf install btrfs-assistant`.

The boot menu can't start the computer from a snapshot: snapshots are for putting files back
from a running system (or from the live USB, with the disk opened there). To get back a system
that doesn't start, start the previous kernel, or start the live USB and restore from there.

Installed with Arctic Linux 0.1? Its installer didn't set up snapshots. Once your system has the
updated Arctic packages, turn them on:

```sh
sudo snapper -c root create-config /
sudo snapper -c root set-config NUMBER_LIMIT=10 NUMBER_LIMIT_IMPORTANT=5 TIMELINE_CREATE=no
```

## The next Fedora release

Arctic Linux publishes its packages for a new Fedora release once that release is out and Arctic
works on it. From then on **Settings → Updates** shows **Fedora 45 is ready for Arctic Linux**
(`arctic-update upgrade check` says the same). **Upgrade…** opens a terminal window that
downloads the new release (a few gigabytes, `dnf5 system-upgrade download`; a snapshot is taken
first), then asks whether to restart: the upgrade installs during that restart, and the computer
restarts once more at the end. Your files, settings and apps stay. **Release notes** says what
changes.

```sh
arctic-update upgrade check        # is the next release ready?
arctic-update upgrade download     # download it, then restart into the upgrade
```

The daily update check leaves a downloaded upgrade alone; `arctic-update` shows it as waiting
for `dnf5 offline reboot`.

## What's new

The first time you log in after each Arctic update, a card says what changed, with **Read the
release notes**. Each packaged update has a unique note ID, so every update's card shows once per
account; a brand-new account gets the welcome card instead. `arctic-shell-ipc whatsnew open`
shows the current card again. Its text is `/usr/share/arctic/shell/whats-new.json`.

## Flatpak apps, firmware and Nix

**Optional Flatpak apps** (for example Zen, Zed or Collabora Office from Flathub) are updated every day, about
twenty minutes after the computer starts and then daily (`arctic-flatpak-update.timer`, which
runs `arctic-update flatpak --auto`). They're updated in place: an app that's open keeps running
the version it started with and gets the new one the next time you open it. Runtimes no app uses
any more are removed afterwards. The daily run follows the same settings as the system updates:
it only runs with automatic updates **on** (not with `download-only` or `off`), and not on a
metered connection unless `METERED=allow`.

To update them right away: **Settings → Updates → Update apps now**, or

```sh
arctic-update flatpak           # your apps, and the ones installed for everyone
```

`arctic-update` shows how the last run went ("Flatpak apps  2 apps updated").

**Firmware** (the BIOS/UEFI, docks, keyboards, SSDs and other devices whose makers publish updates
through the [Linux Vendor Firmware Service](https://fwupd.org)) comes from fwupd, which keeps its
list of updates current by itself. **Settings → Updates → Firmware** says what's available;
**Install in a terminal** runs `fwupdmgr update`, which shows its progress and asks before it
restarts the computer. From a terminal:

```sh
arctic-update firmware          # what's available
arctic-update firmware install  # install it (fwupdmgr update)
```

Plug a laptop in before a firmware update, and don't switch it off while it runs.

**Nix** packages in your profile are yours to update:

```sh
nix profile upgrade --all
```

## Fixing it on the go

For developers: when something in Arctic Linux itself bothers you, you can fix it on the machine
you're using and send the fix upstream.

**Get the source:**

```sh
git clone https://github.com/yuvalkolodkingal/Arctic-Linux ~/src/Arctic-Linux
```

**The shell** (bar, launcher, popovers) is QML that runs straight from the checkout. Stop the
installed one and run yours; its messages appear in the terminal:

```sh
arctic-shell --stop
quickshell -p ~/src/Arctic-Linux/shell
```

Save a file and restart it (`Ctrl + C`, then the same command) to see the change. `arctic-shell`
starts the installed shell again; `ARCTIC_SHELL_DIR=~/src/Arctic-Linux/shell arctic-shell --restart`
makes it use yours in the background. See the shell's
[README](https://github.com/yuvalkolodkingal/Arctic-Linux/tree/main/shell) for the tests.

**Mango** (windows, shortcuts, gaps): put your settings in `~/.config/mango/user.conf` and press
`Super + Shift + R` to reload. See [Themes and customisation](Themes-and-Customisation#mango-settings-in-userconf).

**The packages:** build them from your checkout (uncommitted changes included) and install the
ones you have:

```sh
cd ~/src/Arctic-Linux
tools/build-rpms.sh                           # → out/repo, in a Fedora container
sudo dnf upgrade ./out/repo/*.rpm             # installs newer versions of the packages you have
```

This installs into the running system, like any `dnf upgrade`: restart the shell or log out and
back in to see the change. A build with the same version as the installed package needs
`sudo dnf reinstall ./out/repo/<package>.rpm` instead. Local builds aren't signed, and the next
update from the channel replaces them. See [Building from source](Building-from-Source).

**Share it:** switch to the testing channel (`arctic-update channel testing`) to run the latest
development builds, and send your change as a pull request. Every push to the development branch
publishes a testing build, so once it's merged, every testing machine gets it at its next check.
