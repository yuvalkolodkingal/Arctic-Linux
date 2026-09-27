# arctic-release sources

Installed by the `arctic-release` subpackage of `packaging/arctic-linux.spec`:

| File | Installed as |
|---|---|
| `os-release` | `/usr/lib/os-release` (+ `/etc/os-release` symlink) |
| `macros.dist` | `/usr/lib/rpm/macros.d/macros.dist` (`%fedora 44`, `%dist .fc44`) |
| `80-arctic.preset` | `/usr/lib/systemd/system-preset/80-arctic.preset` |
| `80-arctic-user.preset` | `/usr/lib/systemd/user-preset/80-arctic.preset` |
| `85-display-manager.preset`, `90-default.preset`, `99-default-disable.preset` | Fedora's system presets, unchanged |
| `90-default-user.preset`, `99-default-disable-user.preset` | Fedora's user presets, unchanged |
| `20-arctic-dnf-defaults.conf` | `/usr/share/dnf5/libdnf.conf.d/20-arctic-defaults.conf` (Fedora's dnf5 defaults) |
| `copr-arctic.conf` | `/etc/dnf/plugins/copr.d/arctic.conf` |
| `arctic.repo` | `/usr/share/dnf5/repos.d/arctic.repo`: the Arctic package repository, **disabled** until it is published (placeholder address; Fedora's repositories are unaffected) |
| `issue`, `issue.net` | `/usr/lib/issue{,.net}` (+ `/etc` symlinks) |

The Fedora preset and dnf files come from `fedora-release-common-44-18` (MIT license).
