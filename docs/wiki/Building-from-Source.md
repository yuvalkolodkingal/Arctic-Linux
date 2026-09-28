# Building from source

Everything in Arctic Linux is built from the [repository](https://github.com/yuvalkolodkingal/O-Tism):
the RPM packages, the live ISO, and the tests that boot and install it in a virtual machine. The
builds run inside Fedora 44 containers, so your own machine only needs a container engine.

## Requirements

- **Linux** with **Docker** or **Podman**. The scripts use whichever is installed (Docker first);
  set `CONTAINER_ENGINE=podman` to choose.
- **Privileged containers** for the ISO build (kiwi needs loop devices).
- **Disk space:** about 15 GB of scratch space for the ISO build (the script warns below 12 GB).
- **Time:** the ISO build takes about 20 minutes on top of the RPMs.
- **For the VM tests:** nothing extra. QEMU runs inside a container. `/dev/kvm` makes it much
  faster but isn't required (without it, a full install test takes about 1.5 hours).
- **Behind a proxy:** `HTTPS_PROXY` is passed into the containers, and `ARCTIC_CA_BUNDLE` adds an
  extra CA certificate. Nothing proxy-specific is added when these aren't set.
- `ARCTIC_FEDORA_IMAGE` changes the container image (default
  `registry.fedoraproject.org/fedora:44`).

## Quick start

```sh
git clone https://github.com/yuvalkolodkingal/O-Tism.git
cd O-Tism
tools/build-rpms.sh                                  # RPMs → out/repo
tools/build-iso.sh                                   # live ISO → out/iso
tools/test-iso.sh --firmware uefi --mode try         # boot it in QEMU, screenshots in out/test
tools/test-install.sh --firmware uefi                # install to a VM disk, boot it, log in
```

## Build the RPMs: `tools/build-rpms.sh`

Builds every package in a Fedora 44 container and makes `out/repo` a dnf repository
(createrepo_c).

```sh
tools/build-rpms.sh                  # mangowm + arctic-linux
tools/build-rpms.sh --only arctic    # only packaging/arctic-linux.spec
tools/build-rpms.sh --only mangowm   # only packaging/mangowm.spec
tools/build-rpms.sh --src DIR        # build from another directory
tools/build-rpms.sh --out DIR        # output directory (default out/)
tools/build-rpms.sh --release-suffix none            # Release 1.fc44 instead of a snapshot
tools/build-rpms.sh --gpg-public-key FILE            # the Arctic repository key for arctic-release
```

- Every build gets its own Release: `1.<commit time>.<build time>.git<commit>` (both UTC), for
  example `arctic-shell-0.2.0-1.20260928030512.202609280310.gitabc1234.fc44`. A build of a newer
  commit is always newer, however late an older commit gets built, and `dnf upgrade` picks it
  up; the same commit built again is newer than its earlier build. `--release-suffix` (or
  `ARCTIC_RELEASE_SUFFIX`) takes `auto` (that, the default), `none` or a suffix of your own.
- `arctic-release` ships the Arctic package repository's public key. It comes from
  `--gpg-public-key FILE`, the `ARCTIC_GPG_PUBLIC_KEY` environment variable (the key itself) or
  a committed `packaging/release/RPM-GPG-KEY-arctic`. Without one the build still works, but
  warns loudly and `arctic-release` ships the Arctic repositories **disabled**: fine for a local
  test, not for a system that should get updates.
- `out/BUILD-INFO` lists what the build produced (version, Release suffix, commit, key
  fingerprint, `arctic_repos=enabled|disabled`, every package).

- `packaging/arctic-linux.spec` builds every Arctic package from one source tarball. The tarball
  is made from your working tree, **including uncommitted and untracked files**, so you can test
  changes without committing.
- `packaging/mangowm.spec` builds Mango 0.17.3 from upstream. The release tarball is downloaded
  once and cached in `out/sources/`.
- Output: `out/repo/*.rpm` + repodata, `out/srpms/`, `out/debug/`, `out/BUILD-INFO`, and build
  logs in `out/logs/rpmbuild-*.log`. Earlier builds of the same spec are removed from `out/`.

The packages it builds:

| Package | What it installs |
|---|---|
| `arctic-release` | os-release ("Arctic Linux 0.2 (Fedora 44 base)"), dnf and systemd presets, the Arctic package repository (stable on, testing off) and its key; replaces `fedora-release` |
| `arctic-logos` | The fox mark under the names Fedora's logo packages use |
| `arctic-backgrounds` | The six wallpapers, SVG and 3840×2160 PNG |
| `arctic-fonts` | Figtree |
| `arctic-selinux` | SELinux file contexts for `/nix` |
| `arctic-desktop-config` | `/etc/skel`, the Mango configuration, the themes, the `arctic-*` commands, `arctic-firstboot`, the theme engine (`arctic-themegen`) and theme hooks, automatic updates and snapper's snapshots around dnf transactions, the app-theming defaults (dconf, Flatpak) |
| `arctic-shell` | The Quickshell desktop shell and `arctic-shell` |
| `arctic-settings` | Arctic Settings (`arctic-settings`, `Super + S`) |
| `arctic-installer` | `arcticd`, `arctic-install`, the app catalog (with the drivers), the installer UI, the systemd socket |
| `sddm-wayland-mango` | Runs the SDDM login screen on Mango |
| `arctic-sddm-theme` | The login screen |
| `arctic-plymouth-theme` | The boot splash and disk passphrase prompt |
| `arctic-grub-theme` | The boot menu theme |
| `arctic-live` | Live USB session only (removed by the installer) |
| `arctic-desktop` | Metapackage: everything a desktop needs |
| `mangowm` | The Mango window manager |

The spec's `%check` validates the Mango configuration with `mango -p` when mangowm is in the build
root.

## Build the ISO: `tools/build-iso.sh`

Builds the live ISO with kiwi-ng from `iso/kiwi/` in a privileged Fedora 44 container, using
Fedora 44 + updates and the local repository from `build-rpms.sh`.

```sh
tools/build-iso.sh                        # → out/iso/Arctic-Linux-0.2-x86_64.iso (+ .sha256)
tools/build-iso.sh --repo DIR             # the local RPM repository (default out/repo)
tools/build-iso.sh --work DIR             # kiwi scratch space (default out/kiwi-work, ~15 GB)
tools/build-iso.sh --keep-work            # keep the scratch space afterwards
tools/build-iso.sh --cache DIR            # keep kiwi's package cache between builds
tools/build-iso.sh --out DIR              # output directory (default out/iso)
tools/build-iso.sh --zen auto|yes|no      # preinstall Zen Browser (default auto)
tools/build-iso.sh --create-only          # reuse a kept image root, only run the create step
tools/build-iso.sh --debug                # kiwi --debug
```

It runs `kiwi-ng system prepare` (packages and `iso/kiwi/config.sh`), installs Zen Browser from
Flathub into the image, then `kiwi-ng system create`. With `--zen auto`, Zen is kept only while
the ISO stays within GitHub's 2 GiB asset limit; otherwise the image is built again without it.

Output in `out/iso/`: the ISO, its `.sha256`, the package list (`.packages`) and `.build-info`,
which says `zen_preinstalled=1` or `0`.

The boot menu comes from `iso/kiwi/grub-arctic.cfg.iso-template`. Each entry boots with
`rd.live.image` and `arctic.mode=try` or `arctic.mode=install`; Safe graphics adds `nomodeset`,
Check USB adds `rd.live.check`. Adding `arctic.greeter=1` (press `e` on an entry) skips the live
autologin and shows the SDDM login screen, which is useful for testing it.

## Boot it in QEMU: `tools/test-iso.sh`

```sh
tools/test-iso.sh                              # UEFI (OVMF), "Try Arctic Linux", 15 minutes
tools/test-iso.sh --firmware bios              # SeaBIOS
tools/test-iso.sh --mode install               # the "Install Arctic Linux" entry
tools/test-iso.sh --mode safe|check|disk       # the other boot menu entries
tools/test-iso.sh --timeout 600 --interval 60  # run time and seconds between screenshots
tools/test-iso.sh --kvm                        # use /dev/kvm
tools/test-iso.sh --secureboot                 # UEFI with Secure Boot on
tools/test-iso.sh --append 'ARGS'              # add kernel arguments
tools/test-iso.sh --debug                      # the whole journal on the serial port
tools/test-iso.sh --collect                    # copy the session log, failed units and warnings to serial.log
tools/test-iso.sh --memory 4096 --smp 4 --vga std --iso PATH
```

Screenshots go to `out/test/<firmware>-<mode>/`: the boot menu, the splash, then one every
`--interval` seconds, plus `serial.log`. The VM gets an empty 64 GB disk for the installer.

## Install it in QEMU: `tools/test-install.sh`

The end-to-end test: install Arctic Linux from the ISO to a VM disk, then boot the result.

```sh
tools/test-install.sh                        # UEFI: install, then boot the installed disk
tools/test-install.sh --firmware bios
tools/test-install.sh --stage install        # only the install (fresh disk)
tools/test-install.sh --stage boot           # only boot a disk a previous run installed
tools/test-install.sh --profile FILE         # default profiles/ci/offline.toml
tools/test-install.sh --installer BIN        # test a freshly built arctic-install without rebuilding the ISO
tools/test-install.sh --kvm --memory 6144 --smp 4 --install-timeout 7200
```

**Install stage:** boots **Try Arctic Linux**, opens a terminal in the live desktop and runs
`arctic-install unattended` with the profile and test secrets from a small data CD, logging to the
serial port. **Boot stage:** boots the installed disk, types the disk passphrase at the Plymouth
prompt and the password at the SDDM login, waits for the desktop, then collects failed units,
warnings, `pending.json`, `getenforce` and the user's shell. Screenshots of every step land in
`out/test/install/<firmware>/`.

The VM has no internet in some environments, so the default profile installs offline and the
downloaded apps (Zen, Zed, the codecs) are put off to `arctic-firstboot`.

## Screenshots for this wiki: `tools/screenshot-tour.sh`

Takes the screenshots in `docs/wiki/images/` from the real Arctic Linux in QEMU (UEFI, 1280×800),
pressing the real shortcuts and waiting for the screen to settle before each shot.

```sh
tools/screenshot-tour.sh                     # both phases: the live USB, then the installed disk
tools/screenshot-tour.sh --phase live        # boot menu, splash, live desktop, shell, terminal, installer
tools/screenshot-tour.sh --phase installed   # passphrase prompt, login screen, desktop, lock screen
tools/screenshot-tour.sh --only launcher,keys        # retake some images (--skip leaves some out)
tools/screenshot-tour.sh --disk-dir DIR      # an install made by tools/test-install.sh (default out/test/install/uefi)
tools/screenshot-tour.sh --kvm               # use /dev/kvm
```

The installer screenshots are taken in the live session with the engine's demo mode, which shows
example disks and networks and never writes to a disk. The installed-system shots boot a copy of
the disk `tools/test-install.sh` made (the original is never written). A full run takes about 45
minutes without KVM. The other options are described at the top of the script.

## Unattended installs

`arctic-install` is the installer engine's command-line side:

```sh
arctic-install plan --profile profiles/defaults.toml       # print every command it would run (dry run)
arctic-install plan --profile FILE --firmware bios --inventory mock
sudo arctic-install unattended --profile FILE              # install from a profile (live USB, root)
arctic-install catalog [--json]                            # print the app catalog
arctic-install version
```

A profile answers every wizard step with module ids only, never commands. Secrets come from the
environment: `ARCTIC_LUKS_PASSPHRASE` and `ARCTIC_USER_PASSWORD`. Examples: `profiles/defaults.toml`
(what pressing `Enter` everywhere gives), `profiles/ci/default.toml`, `profiles/ci/offline.toml`
and `profiles/ci/alternative.toml` (Firefox, foot, fish, Nautilus, mpv, LibreOffice, alongside, no
encryption, German keyboard). In unattended mode an app that can't be downloaded is retried once,
then put off to first boot.

## Working on one part without building an ISO

| Part | Run it | Tests |
|---|---|---|
| Installer engine (Go, standard library only) | `go run ./cmd/arctic-install plan --profile profiles/defaults.toml --inventory mock` | `go vet ./... && go test ./...` |
| Installer UI | `installer-ui/dev/run.sh` (Python mock engine, no root). `ARCTIC_INSTALLER_THEME=light` for Winter, `ARCTIC_MOCK_FAIL=steam` to see a failure, `ARCTIC_INSTALLER_BRIDGE="arctic-install bridge --mock"` for the Go mock | `python3 -m unittest installer-ui/dev/test_mock_bridge.py`, `installer-ui/dev/test-headless.sh` |
| Desktop shell | `arctic-shell --foreground` in a Mango, Hyprland or sway session, or `shell/dev/headless.sh` (headless sway, screenshots in `shell/dev/screenshots/`) | `python3 -m unittest discover -s shell/tests`, `node shell/tests/test-launcher.cjs`, `node shell/tests/test-package-search.cjs` |
| Dotfiles | `dotfiles/install.sh` into your own home (`--theme winter`, `--no-shell`, `--target DIR`) | ShellCheck |
| First-boot service | — | `python3 -m unittest discover -s packaging/firstboot` |
| Login screen, boot menu, splash | `branding/tools/preview-sddm.sh`, `preview-grub.sh`, `preview-plymouth.sh` | Screenshots in `branding/*/preview/` |
| Branding assets | `branding/tools/build-all.sh` | — |
| Theme files | `python3 design/tools/gen-desktop-themes.py` | — |

QML is checked with `qmllint` (`/usr/lib64/qt6/bin/qmllint`, from `qt6-qtdeclarative-devel`).

## Continuous integration

| Workflow | Runs on | Does |
|---|---|---|
| `.github/workflows/ci.yml` | Every push and pull request | `go vet` and `go test`; ShellCheck on the scripts; the Python and Node tests (shell, `arctic-firstboot`, the repository tools); `qmllint` on the shell, installer and login theme; `rpmspec` parses both specs; then a full `tools/build-rpms.sh`, an unsigned test publish and `tools/test-repo.sh` (dnf5 against it), with the RPMs uploaded as an artifact |
| `.github/workflows/repo.yml` | Pushes to `main` (stable), pushes to the development branch through `repo-testing.yml` (testing), or by hand (any channel from any `ref`) | Builds the RPMs, signs them, checks the signed site with dnf5 and publishes it to the Arctic package repository on GitHub Pages (see below) |
| `.github/workflows/iso.yml` | Tags `v*`, or by hand | Builds the RPMs (the repository key is required) and the ISO, uploads them as an artifact, boots the ISO in QEMU (UEFI Try and BIOS Install) with screenshots, and publishes a GitHub release (refused if the ISO's Arctic repositories are off) |
| `.github/workflows/wiki.yml` | Pushes to `main` that change `docs/wiki/`, or by hand | Publishes `docs/wiki/` to this wiki |

### The package repository

Installed systems update Arctic's own packages from a signed dnf repository on this project's
GitHub Pages site, https://yuvalkolodkingal.github.io/O-Tism/, with two channels:

| Channel | Built from | On an Arctic system |
|---|---|---|
| `stable` | every push to `main` | `[arctic]`, on |
| `testing` | every push to `claude/busy-goodall-j42hmi` | `[arctic-testing]`, off: `sudo dnf config-manager setopt arctic-testing.enabled=1` |

`repo.yml` builds the RPMs, signs every new package and the metadata with the repository key
(the `ARCTIC_GPG_*` secrets), keeps the last three builds of each package, checks the result with
dnf5 the way installed systems read it (`tools/test-repo.sh --signed`: signatures on, only the
key from `arctic-release`) and deploys the site with both channels. **Actions → Repository → Run
workflow** publishes a channel by hand, from any branch, tag or commit (`ref`). Pushes to the
development branch publish testing through `repo-testing.yml`, which starts `repo.yml` on `main`
for the pushed commit once no other publish is running or waiting (the `github-pages` environment
only lets `main` deploy, and a new waiting run would replace a waiting stable one). It fails
straight away, saying what to change, when GitHub Pages isn't set to **GitHub Actions** (Settings
→ Pages). Every push to `main` is a new Release of every Arctic package, so it is a full (small)
Arctic update for every stable system. To try the tooling locally without a key:

```sh
tools/build-rpms.sh
tools/publish-repo.sh --no-sign --site out/site --channel testing   # unsigned, local only
tools/test-repo.sh                                                    # dnf5 against it, offline checks
```

The details (layout, pruning, signing, the Pages setup): `docs/BUILD-SPEC.md` §9 in the
repository.

### Making a release

Push a tag that starts with `v`, for example `v0.2.0`. `iso.yml` builds everything and creates the
release **Arctic Linux 0.2.0** with the ISO and its `.sha256`, and writes release notes that say
whether Zen is preinstalled. If the ISO is larger than 2 GiB, it's split into `.partNN` files with
instructions for joining them.

Running `iso.yml` by hand (**Actions → ISO → Run workflow**) builds the ISO as an artifact.
Tick **release** to also publish a prerelease (tag `v0.2.0-build.<run number>` unless you give
one), and untick **boot_test** to skip the QEMU boot.

### Publishing the wiki

The wiki is written in `docs/wiki/` (one Markdown file per page, `_Sidebar.md`, `_Footer.md` and
`images/`) and published by `wiki.yml`, which copies the folder into the wiki's own repository.
GitHub only creates that repository after the first wiki page is saved, so once per repository:
open the **Wiki** tab, click **Create the first page**, save it, then run the workflow (**Actions →
Wiki → Run workflow**). It replaces that first page with `docs/wiki/Home.md`.
