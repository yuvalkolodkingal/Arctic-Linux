# Automatic updates and snapshots

Installed by `arctic-desktop-config` (`packaging/arctic-linux.spec`). The user guide is the
wiki's [Updates](../../docs/wiki/Updates.md) page.

| File | Installed as | What it does |
|---|---|---|
| `../../dotfiles/.local/bin/arctic-update` | `/usr/bin/arctic-update` | The command: `status`, `now`, `apply`, `channel`, `auto`, `metered`, and `stage` for the timer, `after-transaction` for dnf's hook |
| `arctic-update-helper` | `/usr/libexec/arctic/arctic-update-helper` | Its file handling in Python: `update.conf`, dnf5's offline state, the status file |
| `arctic-update-finish`, `50-arctic-finish.conf` | `/usr/libexec/arctic/arctic-update-finish`, `/usr/lib/systemd/system/dnf5-offline-transaction.service.d/50-arctic-finish.conf` | How the update boot ends: a soft-reboot when only programs changed (see "Leaving the update boot") |
| `update.conf` | `/etc/arctic/update.conf` (config) | `AUTO=download-and-install-on-reboot\|download-only\|off`, `INSTALL=now\|restart`, `METERED=skip\|allow` |
| `../systemd/arctic-update-stage.{service,timer}` | `/usr/lib/systemd/system/` | The daily check, 10 minutes after boot and then daily; never on the live USB |
| `../systemd/arctic-update-restage.timer` | `/usr/lib/systemd/system/` | The same check two minutes after a dnf transaction invalidated the downloaded updates |
| `../systemd/arctic-flatpak-update.{service,timer}` | `/usr/lib/systemd/system/` | `arctic-update flatpak --auto`: Flatpak apps (the system installation) updated in place, daily, with the same AUTO and METERED settings; the result in `/var/lib/arctic/flatpak-status.json` (`status` shows it) |
| `update.actions` | `/etc/dnf/libdnf5-plugins/actions.d/arctic-update.actions` (config) | dnf's post-transaction hook: `arctic-update after-transaction` |
| `snapper.actions` | `/etc/dnf/libdnf5-plugins/actions.d/arctic-snapper.actions` (config) | A snapper pre/post snapshot pair around every dnf transaction, once `/etc/snapper/configs/root` exists |
| `test_arctic_update_finish.py` | (not installed) | Unit tests of `arctic-update-finish` under a scratch root with a scripted systemctl |
| `test_arctic_update.py`, `testdata/fake-dnf5` | (not installed) | Unit tests of the helper and scenario tests of `arctic-update` with a scripted dnf5 under a scratch root (`ARCTIC_UPDATE_TEST_ROOT`): `python3 -m unittest discover -s packaging/updates` (also the spec's `%check` and CI) |
| `test-dnf5-offline.sh` | (not installed) | The same flow with the real dnf5 and a local repository, in a throwaway Fedora 44 container (CI's "dnf5 offline updates" job): pins the dnf5 behaviour and messages this relies on |

## Installing now (the default since 1.2.3)

`INSTALL=now` in `update.conf` (also when the line is missing, as in a file from before 1.2.3):

1. `arctic-update-stage.timer` starts `arctic-update stage` as before (AUTO, METERED, the wait
   for arctic-firstboot and the lock are unchanged). The unit runs with `CPUWeight=idle`, so
   the transaction (scriptlets, a kernel's initramfs, a driver build) only gets processor time
   the desktop doesn't want; `Nice=19` alone made animations stutter while updates installed.
2. It runs `dnf5 upgrade -y --refresh` with the strict Arctic repository overrides: exactly
   `sudo dnf upgrade`. Snapper's pre/post pair comes from `arctic-snapper.actions`. An offline
   transaction arctic-update itself stored earlier (INSTALL=restart, or 1.2.2) is unscheduled
   and cleaned first; someone else's is left alone and nothing is installed (`now --replace`).
3. Is a restart needed to start using it? `dnf5 needs-restarting` (exit 1 and "Reboot is
   required": core packages installed since this boot) or, for drivers outside Fedora, anything
   changed under the running kernel's `/usr/lib/modules/<release>`, `/usr/lib/firmware` or
   `/usr/src/akmods` since a marker made before the transaction.
4. The status file gets `installed`, `installed_at` (the shell runs the post-update hooks and
   What's New) and, when a restart is needed, `restart_boot` (this boot's id) and
   `restart_packages`. `status --json` reports `restart_needed` only while `restart_boot` is
   the running boot; the bar shows **Restart when you like** on the same condition.
5. After a dnf transaction of your own, `arctic-update after-transaction` (the dnf hook) starts
   `arctic-update restart-check` 20 seconds later (a transient unit), which records the same
   note. arctic-update's own transaction sets `ARCTIC_UPDATE_RUNNING` and is skipped.

`AUTO=download-only` still stores an offline transaction without scheduling it; `apply`
restarts into it, `now` installs everything without a restart. dnf's own defaults for Arctic
are in `packaging/release/20-arctic-dnf-defaults.conf`: `max_parallel_downloads=10` and
`installonly_limit=2` (the running kernel and the newest).

The packaged shell does not reload itself when its files change (`Quickshell.watchFiles` is
off under `/usr`), so a transaction never reloads the bar or the lock screen halfway through.

## How an update travels at a restart (INSTALL=restart)

1. `arctic-update-stage.timer` starts `arctic-update stage` (root, lowest CPU and I/O
   priority). It does nothing with `AUTO=off`, on a metered connection with `METERED=skip`
   (`nmcli -t -f METERED general`) or without a connection, and waits while
   `arctic-firstboot.service` is installing apps (up to an hour).
2. `dnf5 upgrade --offline -y --refresh` with strict Arctic repository overrides downloads the updates to `/var/lib/dnf/offline/packages`,
   tests the transaction and stores it in `/usr/lib/sysimage/libdnf5/offline`
   (`offline-transaction-state.toml` with status `download-complete`, `transaction.json`). The
   running system is not touched. When packages were installed or removed while it ran (the
   rpm database changed), it checks again (up to three times).
3. arctic-update arms it the way `dnf5 offline reboot` does, without the reboot: the state's
   status becomes `ready` (only that line changes, only from `download-complete`), then
   `/system-update` links to that directory; `dnf5 offline status` must still accept it. It
   writes `/var/lib/arctic/update-status.json` for the shell (state, packages, download_mb,
   staged_at, notify_key, checked_at, channel, armed, armed_boot, armed_at, boot_failures,
   install_error, install_failed_at, message).
4. The shell shows **Restart to update** in the bar while that file says `ready` and armed and
   `/system-update` exists, and announces each set of updates once (`notify_key`: the same
   updates stored again by the next daily check don't count). A dnf transaction in the
   meantime invalidates the download (dnf5 removes the link); `arctic-update.actions` then has
   it checked again two minutes later, reusing the packages already downloaded.
5. At the next restart systemd boots into `system-update.target`: dnf5-offline-transaction.service
   installs the updates before the desktop starts (snapper takes its pre/post pair) and
   starts the updated system (see "Leaving the update boot").
6. The first check after that restart looks at what became of it (the status file says it was
   armed in an earlier boot): no stored transaction any more means installed; status
   `transaction-incomplete`, or still `ready` without the link while the journal shows
   dnf5-offline-transaction.service ran, means the install failed. A failure is recorded
   (`boot_failures`, the end of dnf5's output in `install_error`; the shell notifies once) and
   the updates are downloaded and scheduled once more; after two failures in a row nothing is
   scheduled automatically until `arctic-update now` succeeds.

## Leaving the update boot

Stock dnf5 ends the update boot with a full restart: firmware, boot menu, initramfs and, on an
encrypted disk, the passphrase a second time (unlock, install, restart, unlock again). The
drop-in `50-arctic-finish.conf` sets `DNF_SYSTEM_UPGRADE_NO_REBOOT=1`, so dnf5 leaves that to
`arctic-update-finish`:

| After a successful transaction | The update boot ends with |
|---|---|
| Only programs and libraries changed | `systemctl soft-reboot`: the kernel keeps running, the disk stays unlocked, systemd starts the updated system |
| Anything under `/usr/lib/modules`, `/usr/lib/firmware` or `/usr/src/akmods` was added, replaced or removed (a kernel, NVIDIA's driver, firmware, microcode) | a full restart, the only thing that loads them |
| A release upgrade (`dnf5 system-upgrade`, or `target_releasever` differs) | a full restart |
| `dnf5 offline reboot --poweroff` | power off |
| `prepare` did not run, or `soft-reboot` was refused | a full restart |

`prepare` (ExecStartPre, never fatal) notes the request and leaves a marker in
`/run/arctic/update-boot`; `finish` (ExecStartPost) waits for shutdown inhibitors as dnf5 does
(akmods, at most five minutes), compares inode change times with the marker (rpm gives files
their build time, so modification times say nothing) and asks systemd. If even the restart is
refused the unit fails and dnf5's cleanup unit restarts. A failed transaction never reaches
`finish`: `dnf5-offline-transaction-cleanup.service` restarts as before. A soft-reboot keeps
the kernel's boot id, which still differs from the boot the update was scheduled in, so the
check in step 6 works unchanged.

**Someone else's offline transaction.** dnf5 keeps one offline transaction, whoever prepared it
(`dnf5 install --offline`, `dnf5 system-upgrade download`, dnf5daemon). The state's `cmd_line`
says whose: arctic-update's own use `dnf5 upgrade --offline -y --refresh` or
`dnf5 distro-sync --offline -y --refresh`, with strict `skip_if_unavailable=False`
overrides for `arctic` and `arctic-testing`, the matching `verb`, and no release change
(`target_releasever` = `system_releasever`). The exact legacy command forms remain recognized
so queued updates survive an Arctic upgrade. Any other stored transaction (except a
half-written `download-incomplete` one, which dnf5 itself ignores) is left alone: the daily
check doesn't unschedule, clean, replace, prune or schedule it and says so in the status file;
`now` and `channel` refuse unless given `--replace`, `apply` refuses.

**What arctic-update reads.** The class of the stored transaction comes from the state file
(`status`) and the link. `dnf5 offline status` is read only for its "has been modified since the
offline transaction was prepared" sentence (stale: dnf5 replaces it at the next check); any
other output means "trust the state file", since `dnf5 offline _execute` checks the rpm database
again at the boot and the cleanup unit removes the link if it refuses. `dnf5 offline clean` runs
only for arctic-update's own transaction that no longer applies, for one that failed at a boot,
or when you asked (`--replace`, switching the channel), never for an unreadable or unknown
state.

A check that fails keeps the update downloaded before (and scheduled, when it was); a check
that finds nothing new keeps arctic-update's own too as long as dnf5 accepts it (an unreachable
repository looks like "nothing to do"). `auto off` and `auto download-only` unschedule a waiting
update but keep it downloaded (`arctic-update apply` installs it); with `download-only` the
daily check keeps an update scheduled by `arctic-update now` scheduled. Switching the channel
removes the stored transaction.

dnf5-automatic (`dnf5-plugin-automatic`) is not used: it can only install into the running
system; `80-arctic.preset` keeps its timer disabled.

## Manual checks and repository failures (1.2)

Settings keeps **Check now** available when updates are already queued. Its helper waits for
the actual command result while the UI polls progress; authorization cancellation is an
error, and closing Settings does not send a broken stdout pipe to the detached updater.
The page displays repository errors, pending foreign transactions and automatic-update
modes correctly. An unchecked system is not labeled up to date.

Both manual and scheduled checks retain `--refresh` and require available metadata from
the enabled Arctic stable/testing repository. This overrides `skip_if_unavailable` only
for those two IDs during update checks. Live/installer defaults, disabled repositories,
third-party repository policies, package signatures and metadata caches are unchanged.
A failed check retains a valid prior download and exposes `check_error`; a successful retry
clears it. Unknown or foreign offline transactions remain untouched.

The real-DNF container suite exercises the Settings backend with newly published RPMs and
a warm cache, refreshes an existing queue to a newer RPM, checks Arctic-unavailable failure
and optional-repository skipping, then executes the resulting offline transaction. These
controlled fixture RPMs are unsigned; production signature settings are not changed. The
headless Settings suite verifies rendering separately. Native ISO validation remains a
separate enforcing-SELinux installation/update/reboot check.
