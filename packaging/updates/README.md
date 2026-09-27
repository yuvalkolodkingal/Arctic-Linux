# Automatic updates and snapshots

Installed by `arctic-desktop-config` (`packaging/arctic-linux.spec`). The user guide is the
wiki's [Updates](../../docs/wiki/Updates.md) page.

| File | Installed as | What it does |
|---|---|---|
| `../../dotfiles/.local/bin/arctic-update` | `/usr/bin/arctic-update` | The command: `status`, `now`, `apply`, `channel`, `auto`, `metered`, and `stage` for the timer |
| `arctic-update-helper` | `/usr/libexec/arctic/arctic-update-helper` | Its file handling in Python: `update.conf`, dnf5's offline state, the status file |
| `update.conf` | `/etc/arctic/update.conf` (config) | `AUTO=download-and-install-on-reboot\|download-only\|off`, `METERED=skip\|allow` |
| `../systemd/arctic-update-stage.{service,timer}` | `/usr/lib/systemd/system/` | The daily check, 10 minutes after boot and then daily; never on the live USB |
| `snapper.actions` | `/etc/dnf/libdnf5-plugins/actions.d/arctic-snapper.actions` (config) | A snapper pre/post snapshot pair around every dnf transaction, once `/etc/snapper/configs/root` exists |
| `test_arctic_update.py` | (not installed) | `python3 -m unittest discover -s packaging/updates` (also run by the spec's `%check` and CI) |

## How an update travels

1. `arctic-update-stage.timer` starts `arctic-update stage` (root, lowest CPU and I/O
   priority). It does nothing with `AUTO=off`, on a metered connection with `METERED=skip`
   (`nmcli -t -f METERED general`) or without a connection.
2. `dnf5 upgrade --offline -y --refresh` downloads the updates to `/var/lib/dnf/offline/packages`,
   tests the transaction and stores it in `/usr/lib/sysimage/libdnf5/offline`
   (`offline-transaction-state.toml` with status `download-complete`, `transaction.json`). The
   running system is not touched.
3. arctic-update arms it the way `dnf5 offline reboot` does, without the reboot: the state's
   status becomes `ready` (only that line changes, only from `download-complete`), then
   `/system-update` links to that directory; `dnf5 offline status` must still accept it. It
   writes `/var/lib/arctic/update-status.json` for the shell (state, packages, download_mb,
   staged_at, checked_at, channel, armed, message).
4. The shell shows "Updates ready" in the bar while that file says `ready` and `/system-update`
   exists; a dnf transaction in the meantime invalidates the download and dnf5 removes the link.
5. At the next restart systemd boots into `system-update.target`: dnf5-offline-transaction.service
   installs the updates before the desktop starts (snapper takes its pre/post pair) and
   restarts into the updated system.

A check that fails keeps the update downloaded before it scheduled; a check that finds nothing
new keeps it too as long as dnf5 accepts it (an unreachable repository looks like "nothing to
do"). A stored transaction dnf5 can't use (`incomplete`, unreadable) is removed with
`dnf5 offline clean`; one invalidated by a dnf transaction is replaced by the next check, which
reuses the packages already downloaded (and deletes the ones no longer needed). Switching the
channel removes the stored transaction.

dnf5-automatic (`dnf5-plugin-automatic`) is not used: it can only install into the running
system; `80-arctic.preset` keeps its timer disabled.
