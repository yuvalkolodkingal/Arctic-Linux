# O-Tism — Execution Plan (backend, no frontend, no dotfiles)

Scope: everything needed to go from an empty repo to a bootable Fedora-based live USB
whose Go installer installs a working O-Tism system with MangoWC, Nix and the chosen
default apps. **The installer frontend (GUI/TUI) and the dotfiles are out of scope**:
the plan leaves clean hook points for both so they can be added when provided.

---

## 1. Requirements (from the spec)

| Area | Requirement |
|---|---|
| Base distro | Fedora |
| WM | MangoWC (Wayland, wlroots/dwl-based) |
| Experience | Omarchy-like: one download, everything for daily use installed during setup |
| Installer model | **Ninite-like and modular**: pick apps from a categorised checklist, get an installer that is already configured with that selection |
| Install media | Live USB, **online installer** (small ISO, packages pulled from mirrors at install time) |
| Speed | Preconfigured at download time, installs in minutes |
| Installer backend | Go |
| Package managers | dnf (native) + **Nix preinstalled and configured** (+ Flatpak where needed) |
| Terminal | kitty (default, swappable) |
| Shell | zsh default; bash installed but not default |
| Fetch | Animated fetch on by default |
| Default apps (all swappable) | Browser: Zen · Editor: Zed · File managers: yazi (TUI) + Thunar (GUI) · Office: Collabora · Video: VLC |

## 2. Architecture

```
┌────────────── download site (frontend, later) ──────────────┐
│ user ticks apps  ──►  profile.toml  ──►  ISO builder svc    │
└──────────────────────────────┬──────────────────────────────┘
                               │ base ISO + injected profile (xorriso, seconds)
                               ▼
┌──────────────── Live USB (Fedora + MangoWC) ────────────────┐
│  otismd  (Go installer engine, runs as root)                 │
│   ├─ API: JSON over unix socket  ◄── frontend (later)        │
│   ├─ CLI: otism-install --profile … --unattended (testing)   │
│   ├─ Planner: profile + module catalog ─► ordered step plan  │
│   └─ Executor: disk → base system → bootloader → users →     │
│                 Nix → modules → (dotfiles hook) → finalize   │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
                   Installed Fedora + O-Tism
```

### Key design decisions

1. **Ninite-style "preconfigured download" without per-user ISO builds.**
   One signed base ISO is built per release. When a user downloads, the service
   appends their `profile.toml` into the ISO with
   `xorriso -indev base.iso -outdev out.iso -map profile.toml /otism/profile.toml -boot_image any replay`.
   This takes seconds, needs no rebuild and keeps the ISO bootable (BIOS + UEFI + Secure Boot,
   since the Fedora-signed shim/kernel are untouched). ISOs without a profile fall back to
   `defaults.toml`, so the plain ISO still works.
2. **Everything is a module.** Apps, the WM, the shell, the fetch, even Nix are modules
   described by a manifest. The installer core knows nothing about specific apps.
3. **Slots, not hard-coded apps.** Categories like `browser`, `terminal`, `shell` are
   "slots" with a default module. Changing the browser = choosing a different module for
   the `browser` slot. Some slots allow several (e.g. `file-manager`: yazi + Thunar).
4. **Installation into a target root from the live system**:
   `dnf5 --installroot=/mnt --releasever=N --use-host-config install …`.
   No Anaconda. This is what makes it fast and fully under our control.
5. **Package source per module, in priority order**: `dnf` (Fedora/RPM Fusion) →
   `copr` → `flatpak` (Flathub) → `nix`. The first method available for the
   target release wins. dnf is preferred for system integration; Flatpak for GUI apps
   Fedora doesn't ship; Nix for CLI tools Fedora doesn't ship.
6. **Frontend-agnostic engine.** All state, validation and progress go through a
   versioned API, so the future GUI/TUI (and the web picker) consume the same schema.

## 3. Repository layout

```
O-Tism/
├── cmd/
│   ├── otismd/            # installer engine daemon (API server)
│   ├── otism-install/     # headless CLI client (unattended installs, CI)
│   └── otism-isogen/      # injects a profile into the base ISO (download service core)
├── internal/
│   ├── profile/           # profile.toml schema, parsing, validation, defaults merge
│   ├── catalog/           # module manifest loader, slot resolution, dependency/conflict graph
│   ├── planner/           # profile + catalog → ordered, idempotent step list
│   ├── executor/          # runs steps; Runner interface (real / dry-run / fake for tests)
│   ├── disk/              # partitioning, LUKS, btrfs subvolumes, mount, fstab/crypttab
│   ├── bootstrap/         # dnf5 installroot of base system + chroot helpers
│   ├── bootloader/        # GRUB2 (default) / systemd-boot, kernel cmdline
│   ├── system/            # users, hostname, locale, keymap, timezone, services
│   ├── pkg/               # backends: dnf, copr, flatpak, nix
│   ├── network/           # connectivity checks, mirror selection (Wi-Fi config via NM)
│   ├── hwdetect/          # CPU/GPU (NVIDIA → RPM Fusion akmods), laptop, firmware
│   ├── api/               # unix-socket JSON API, event stream (progress/logs)
│   └── log/               # structured logs, copied to /var/log/otism-install on target
├── modules/               # module manifests (one dir per module) — the "Ninite catalog"
│   ├── wm/mangowc/
│   ├── terminal/{kitty,…}/
│   ├── shell/{zsh,bash,fish}/
│   ├── browser/{zen,firefox,…}/
│   └── …
├── profiles/
│   ├── defaults.toml      # the spec's defaults
│   └── examples/
├── iso/
│   ├── kiwi/              # kiwi-ng description for the live image
│   └── overlay/           # files baked into the live system (otismd.service, autostart)
├── packaging/
│   ├── otism-installer.spec   # RPM of the Go binaries + catalog
│   ├── mangowc.spec           # if MangoWC isn't packaged upstream → our COPR
│   └── otism-release.spec     # os-release branding, repo files
├── test/
│   ├── vm/                # QEMU harness: boot ISO, run unattended install, assert
│   └── fixtures/
├── hooks/dotfiles/        # EMPTY placeholder — filled when dotfiles are provided
├── docs/
├── Makefile
└── go.mod
```

## 4. Data formats

### 4.1 Module manifest (`modules/<slot>/<id>/module.toml`)

```toml
id          = "zen"
name        = "Zen Browser"
slot        = "browser"
description = "Firefox-based privacy browser"
default     = true            # default for its slot
tags        = ["gui", "wayland"]

requires    = []              # other module ids
conflicts   = []
provides    = ["x-www-browser"]

[[install]]                   # tried in order; first available wins
method = "flatpak"
remote = "flathub"
ref    = "app.zen_browser.zen"

[[install]]
method = "nix"
attr   = "nixpkgs#zen-browser"

[post]                        # optional, run in target chroot as root / as user
root = ["xdg-settings-default.sh app.zen_browser.zen.desktop"]
user = []

[config]                      # dotfiles hook — intentionally empty for now
dotfiles = []
```

### 4.2 Profile (`profile.toml`, produced by the web picker / defaults)

```toml
schema = 1
release = "43"                # Fedora release

[select]
wm           = ["mangowc"]
terminal     = ["kitty"]
shell        = ["zsh", "bash"]
default_shell = "zsh"
fetch        = ["otism-fetch"]
browser      = ["zen"]
editor       = ["zed"]
file-manager = ["yazi", "thunar"]
office       = ["collabora"]
video        = ["vlc"]
extra        = []             # free-form extra modules

[system]                      # optional: prefill; anything missing is asked by the frontend
hostname = ""
timezone = ""
locale   = ""
keymap   = ""

[disk]                        # never prefilled by the web; always confirmed on the machine
encrypt  = true
fs       = "btrfs"
```

Secrets (passwords, LUKS passphrase) are **never** in the profile; they are only
supplied through the local API at install time.

## 5. Default module catalog (v1)

| Slot | Module | Primary source | Fallback | Notes |
|---|---|---|---|---|
| wm | mangowc | our COPR (if not in Fedora) | nix | + deps: xdg-desktop-portal-wlr, polkit agent, pipewire, NetworkManager |
| terminal | kitty | dnf | — | alternatives: foot, alacritty, wezterm |
| shell | zsh (default) | dnf | — | `chsh`/`useradd -s /bin/zsh` |
| shell | bash | dnf (always present) | — | installed, not default |
| fetch | otism-fetch | our RPM | — | animated fetch; wraps fastfetch — look/animation comes with dotfiles |
| browser | zen | flatpak `app.zen_browser.zen` | nix | alternatives: firefox (dnf), brave, chromium |
| editor | zed | flatpak `dev.zed.Zed` | nix `zed-editor` | alternatives: neovim, vscodium |
| file-manager | yazi | COPR / nix `yazi` | — | TUI |
| file-manager | thunar | dnf | — | GUI (+ gvfs, tumbler) |
| office | collabora | flatpak `com.collabora.Office` | — | alternative: libreoffice (dnf) |
| video | vlc | dnf | flatpak `org.videolan.VLC` | alternative: mpv |
| pkg | nix | Determinate/official multi-user installer | — | mandatory module; see §6.5 |
| pkg | flatpak | dnf + Flathub remote | — | pulled in automatically when any module needs it |

Exact source for each package is re-verified at the start of Phase 3 against the
target Fedora release (availability in Fedora/COPR/Flathub/nixpkgs changes).

## 6. Install pipeline (what otismd executes)

All steps are idempotent, logged, emit progress events, and can run in `--dry-run`.

1. **Preflight** — UEFI/BIOS detection, RAM/disk checks, network reachability to Fedora
   mirrors + Flathub + cache.nixos.org, clock sync, hardware detection.
2. **Disk** — (default) GPT: 1 GiB ESP (vfat) + rest; optional LUKS2; btrfs with
   subvolumes `@`, `@home`, `@var_log`, `@nix` (keeps /nix out of snapshots),
   zstd compression; mount at `/mnt`. Modes: wipe disk, use free space, manual (later via frontend).
3. **Base system** — `dnf5 --installroot=/mnt install` of a minimal set
   (`@core`, kernel, `glibc-langpack-*`, NetworkManager, firmware, `otism-release`),
   enable RPM Fusion free/nonfree (needed for codecs/NVIDIA).
   Speed: parallel downloads, fastest-mirror, and the live ISO ships a local RPM cache
   of the base set so only apps are downloaded.
4. **System config** — fstab/crypttab, hostname, locale, keymap, timezone,
   user + sudo (wheel), root locked, SELinux relabel on first boot, enable services
   (NetworkManager, pipewire user units, greetd or a TTY autologin into MangoWC).
5. **Bootloader** — GRUB2 + shim (Secure Boot OK), dracut regeneration with LUKS/btrfs.
6. **Nix** — install multi-user Nix inside the chroot (SELinux-aware installer),
   `/nix` on its own subvolume, enable flakes, `nix-daemon.service`, add
   `~/.nix-profile/bin` to PATH via `/etc/profile.d` + zsh.
7. **Modules** — resolve slots → module list → dependency order; batch all `dnf`
   installs into one transaction, then COPR, then `flatpak install --system` in one
   call, then `nix profile install` in one call (as the user).
   Post-install hooks run after all packages.
8. **Dotfiles hook** — calls every `hooks/dotfiles/*` and each module's `[config]`; no-op now.
9. **Finalize** — default apps (xdg-mime), copy install log to target, unmount, report.

Failure policy: steps 1–6 abort the install (system unusable otherwise); a failing
optional module in step 7 is retried once, then skipped and reported, and the
install continues.

## 7. Live USB image

- Built with **kiwi-ng** (Fedora's own live image tooling), type `iso`, hybrid, UEFI + BIOS.
- Contents: minimal Fedora + MangoWC session + kitty + NetworkManager/nmcli/iwd
  (Wi-Fi for the online install), `otism-installer` RPM, base RPM cache.
- `otismd.service` starts at boot; the session autostarts the frontend (placeholder:
  a kitty window running `otism-install --interactive-stub` until the real frontend lands).
- Target ISO size: ≤ 1.5 GiB.
- `otism-isogen` produces per-download ISOs by injecting `profile.toml` (§2.1).

## 8. Phases & milestones

### Phase 0 — Foundations (week 1)
- Go module, Makefile, golangci-lint, `go test`, GitHub Actions CI.
- `profile` + `catalog` packages with schemas and validation; `defaults.toml`.
- **Done when:** `otism-install --profile profiles/defaults.toml --dry-run` prints the full ordered plan.

### Phase 1 — Core installer engine (weeks 2–3)
- `executor` with Runner interface (exec, chroot, dry-run, fake).
- `disk`, `bootstrap`, `system`, `bootloader`.
- **Done when:** in a QEMU VM booted from stock Fedora live, the CLI installs a minimal
  bootable Fedora (UEFI and BIOS, with and without LUKS).

### Phase 2 — Package backends & Nix (week 4)
- `pkg/dnf`, `pkg/copr`, `pkg/flatpak`, `pkg/nix`; method fallback logic.
- Nix module with SELinux on, `/nix` subvolume, daemon enabled.
- **Done when:** installed system can `nix run nixpkgs#hello` and `flatpak run` an app after reboot.

### Phase 3 — Module catalog & MangoWC (weeks 5–6)
- Verify and write manifests for every module in §5 plus 1–2 alternatives per slot.
- Package MangoWC (+ `otism-release`, `otism-fetch`) as RPMs in an O-Tism COPR if needed.
- Session startup: greetd/TTY login → MangoWC.
- **Done when:** default profile install boots into MangoWC with kitty, zsh default,
  fetch on terminal open, and Zen/Zed/yazi/Thunar/Collabora/VLC launching.

### Phase 4 — Live ISO (week 7)
- kiwi-ng description, overlay, otismd service, base RPM cache.
- **Done when:** ISO boots on UEFI+BIOS in QEMU and on one real machine, and the
  unattended default install finishes in < 10 min on a fast connection.

### Phase 5 — Ninite pipeline (week 8)
- `otism-isogen` + a minimal HTTP endpoint: `POST profile → ISO download` (backend only).
- `GET /catalog.json` generated from `modules/` for the future web picker.
- ISO checksums/signing.
- **Done when:** a profile selecting non-default apps (e.g. firefox + foot + mpv)
  yields an ISO that installs exactly that selection unattended.

### Phase 6 — API for the frontend (week 9)
- Freeze API v1: `GetCatalog`, `GetProfile`, `SetProfile`, `ListDisks`, `Validate`,
  `SetSecrets`, `Start`, `Events` (progress/log stream), `Abort`, `Reboot`.
- OpenAPI/JSON-schema docs so the frontend can be built against it.
- **Done when:** the CLI uses only the API (proves a frontend can do everything).

### Phase 7 — Hardening & release (week 10)
- VM test matrix in CI (default profile, alt profile, LUKS, BIOS) on every PR to main.
- NVIDIA path (RPM Fusion akmods), laptop bits (power-profiles-daemon, brightness).
- Error reporting, resume after network drop, log upload option.
- v0.1 release: base ISO + catalog + isogen service.

**Waiting on you:** installer frontend (design, then Phase 6 API consumer) and dotfiles
(fill `hooks/dotfiles/` + module `[config]` sections, fetch animation/theme).

## 9. Testing strategy

- **Unit:** profile/catalog validation, slot resolution, dependency ordering, planner output (golden files).
- **Executor:** fake Runner asserting the exact command sequence per profile.
- **Integration:** QEMU + OVMF in CI (KVM-enabled runners): boot ISO → unattended
  install → reboot → assert via serial console/SSH (MangoWC session starts, apps present,
  `nix`/`flatpak` work, zsh default).
- **Manual:** one real laptop (Intel/AMD) and one NVIDIA machine per release.

## 10. Risks

| Risk | Mitigation |
|---|---|
| MangoWC not packaged for Fedora / breaks on updates | Own COPR with pinned version; Nix fallback |
| Nix + SELinux on Fedora | Use an SELinux-aware installer, test in CI with enforcing |
| Zen / Collabora / Zed only via Flatpak | Accept Flatpak for those; Nix fallback where it exists |
| Online install fails mid-way (network) | Retries, resume from last completed step, base RPM cache on ISO |
| "Minutes" install target | One batched transaction per backend, parallel downloads, local base cache |
| Secure Boot | Only Fedora-signed shim/kernel; no custom kernel in v1 |
| Fedora release churn (every ~6 months) | `release` field in profile, catalog re-verification as a release step |

## 11. Open questions for you

1. Fedora release to target first (current stable, e.g. 43)? Follow each new release automatically?
2. Login: greetd (e.g. tuigreet) or TTY autologin into MangoWC?
3. Default disk layout OK (btrfs + LUKS on by default)? Snapshots (snapper) wanted?
4. Is Flatpak acceptable for Zen / Zed / Collabora, or should everything be dnf/Nix?
5. The PDF's "Idea for installer design" image didn't come through — please resend it with the frontend.
6. Where will the download/ISO-generation service be hosted?
