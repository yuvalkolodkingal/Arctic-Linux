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
| `arctic.repo` | `/usr/share/dnf5/repos.d/arctic.repo`: the Arctic package repository, stable channel (`[arctic]`, enabled; `[arctic-source]`, disabled) on GitHub Pages. Every package signature is checked (`gpgcheck=1`) and so is the signed metadata (`repo_gpgcheck=1`; dnf imports the key into its cache on the first run with `-y` — the automatic update check, first boot and Get apps use `-y` — and a run without `-y` skips the repository until then). `skip_if_unavailable=True`: when the site can't be reached (offline, the live USB, the installer) dnf skips the Arctic repositories instead of failing; Fedora's own repositories still fail offline (`skip_if_unavailable=False`), so offline dnf commands can still fail because of them. Fedora's repositories are unaffected |
| `arctic-testing.repo` | `/usr/share/dnf5/repos.d/arctic-testing.repo`: the testing channel (`[arctic-testing]`, `[arctic-testing-source]`), disabled |
| `RPM-GPG-KEY-arctic` | `/etc/pki/rpm-gpg/RPM-GPG-KEY-arctic`, the repository's public signing key. Not committed yet: `tools/build-rpms.sh` adds it from `--gpg-public-key FILE` or `ARCTIC_GPG_PUBLIC_KEY` (the CI workflows pass the repository secret; repo.yml and, in this repository, iso.yml require it). Built without any key, arctic-release ships both repositories **disabled** (the build warns loudly). To commit it: `curl -fsSL https://yuvalkolodkingal.github.io/O-Tism/RPM-GPG-KEY-arctic -o packaging/release/RPM-GPG-KEY-arctic`; publishing then checks it is the signing key |
| `issue`, `issue.net` | `/usr/lib/issue{,.net}` (+ `/etc` symlinks) |

The Fedora preset and dnf files come from `fedora-release-common-44-18` (MIT license).

Settings in the two `.repo` files are changed with overrides, not by editing them (they are
replaced on updates): `sudo dnf config-manager setopt arctic-testing.enabled=1` writes
`/etc/dnf/repos.override.d/99-config_manager.repo`. The repository itself, its channels and
how packages are versioned and published: `docs/BUILD-SPEC.md` §9.
