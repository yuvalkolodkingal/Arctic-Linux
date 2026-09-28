# Automatic updates and snapshots

Installed by `arctic-desktop-config` (`packaging/arctic-linux.spec`). The user guide is the
wiki's [Updates](../../docs/wiki/Updates.md) page.

| File | Installed as | What it does |
|---|---|---|
| `../../dotfiles/.local/bin/arctic-update` | `/usr/bin/arctic-update` | The command: `status`, `now`, `apply`, `channel`, `auto`, `metered`, and `stage` for the timer, `after-transaction` for dnf's hook |
| `arctic-update-helper` | `/usr/libexec/arctic/arctic-update-helper` | Its file handling in Python: `update.conf`, dnf5's offline state, the status file |
| `update.conf` | `/etc/arctic/update.conf` (config) | `AUTO=download-and-install-on-reboot\|download-only\|off`, `METERED=skip\|allow` |
| `../systemd/arctic-update-stage.{service,timer}` | `/usr/lib/systemd/system/` | The daily check, 10 minutes after boot and then daily; never on the live USB |
| `../systemd/arctic-update-restage.timer` | `/usr/lib/systemd/system/` | The same check two minutes after a dnf transaction invalidated the downloaded updates |
| `update.actions` | `/etc/dnf/libdnf5-plugins/actions.d/arctic-update.actions` (config) | dnf's post-transaction hook: `arctic-update after-transaction` |
| `snapper.actions` | `/etc/dnf/libdnf5-plugins/actions.d/arctic-snapper.actions` (config) | A snapper pre/post snapshot pair around every dnf transaction, once `/etc/snapper/configs/root` exists |
| `test_arctic_update.py`, `testdata/fake-dnf5` | (not installed) | Unit tests of the helper and scenario tests of `arctic-update` with a scripted dnf5 under a scratch root (`ARCTIC_UPDATE_TEST_ROOT`): `python3 -m unittest discover -s packaging/updates` (also the spec's `%check` and CI) |
| `test-dnf5-offline.sh` | (not installed) | The same flow with the real dnf5 and a local repository, in a throwaway Fedora 44 container (CI's "dnf5 offline updates" job): pins the dnf5 behaviour and messages this relies on |

## How an update travels

1. `arctic-update-stage.timer` starts `arctic-update stage` (root, lowest CPU and I/O
   priority). It does nothing with `AUTO=off`, on a metered connection with `METERED=skip`
   (`nmcli -t -f METERED general`) or without a connection, and waits while
   `arctic-firstboot.service` is installing apps (up to an hour).
2. `dnf5 upgrade --offline -y --refresh` downloads the updates to `/var/lib/dnf/offline/packages`,
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
   restarts into the updated system.
6. The first check after that restart looks at what became of it (the status file says it was
   armed in an earlier boot): no stored transaction any more means installed; status
   `transaction-incomplete`, or still `ready` without the link while the journal shows
   dnf5-offline-transaction.service ran, means the install failed. A failure is recorded
   (`boot_failures`, the end of dnf5's output in `install_error`; the shell notifies once) and
   the updates are downloaded and scheduled once more; after two failures in a row nothing is
   scheduled automatically until `arctic-update now` succeeds.

**Someone else's offline transaction.** dnf5 keeps one offline transaction, whoever prepared it
(`dnf5 install --offline`, `dnf5 system-upgrade download`, dnf5daemon). The state's `cmd_line`
says whose: arctic-update's own are exactly `dnf5 upgrade --offline -y --refresh` or
`dnf5 distro-sync --offline -y --refresh`, with the matching `verb` and no release change
(`target_releasever` = `system_releasever`). Any other stored transaction (except a
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
