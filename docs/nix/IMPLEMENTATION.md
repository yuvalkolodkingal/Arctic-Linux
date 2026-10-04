# Nix in Arctic Linux: implementation specification

Status: implementation in progress; **not yet qualified for merge**. Base: main
`f78ff04`. This work is separate from release-reliability PR #12. No OS release,
physical-machine changes, external installer, security relaxation or credentials
are part of this change.

## Existing architecture and ownership

Arctic is Fedora 44. `packaging/arctic-linux.spec` already requires Fedora `nix`
and `nix-daemon`; `modules/_system/nix/module.toml` enables the daemon.
`packaging/selinux/arctic-nix.{te,fc}` is an existing local policy, not evidence
that all Nix applications work under SELinux. The installer in
`internal/installer/installer.go` creates a persistent `@nix` Btrfs subvolume,
mounts it at `/nix`, and labels the target. Installer Nix fallbacks currently go
to a root-owned shared profile with a fixed nixpkgs revision from
`modules/catalog.toml`.

The software GUI is `shell/getapps/`, backed by `shell/AppsService.qml`, read-only
`shell/scripts/apps.py`, and serialized PTY jobs from `appslib.py` and
`install-terminal.py`. Settings updates use `settings/pages/UpdatesPage.qml`
and `settings/scripts/arctic_system.py`. DNF's offline update path already
updates the Nix RPMs. Fish has some Nix PATH setup; graphical session exports
need explicit coverage for existing and newly created accounts.

## Proposed behavior and code touchpoints

1. Add an unprivileged `arctic-nix` helper and shared Python backend. All commands
   use argv arrays, `/usr/bin/nix`, explicit daemon store and explicit profile.
   The GUI owns one profile per user, `~/.local/state/nix/profiles/arctic`.
   It never changes another user's profile, the default `nix-env` profile or
   Fedora-owned files. Do not add users to trusted-users. Reject root user-profile
   operations and mutation in live sessions. Missing daemon, offline/network,
   invalid JSON/schema, conflicts and unavailable packages are errors, not an
   empty success or a claim that the system is up to date.
2. Add a distinct **Nix packages** page to Get apps with search, version/source,
   installed packages, remove confirmation, update and rollback actions. Reuse
   the existing job queue and output/error reporting. Add Nix to Remove apps and
   Settings → Updates. Ordinary users need no admin password for their own Nix
   profile. Install/update warnings explain that Nix apps are not Flatpak
   sandboxes and that Fedora hardware/desktop integration may differ.
3. Default to an explicit supported nixpkgs release branch, not a user's mutable
   registry alias. Branch installs can be updated; Nix records the resolved
   revision in its profile manifest. Explicitly pinned packages remain pinned.
   Expose original and locked references in installed metadata; document exact
   reproduction and separate project flakes/lock files. Free software only by
   default; do not silently enable unfree evaluation or accept extra caches.
4. Ship session PATH/XDG_DATA_DIRS setup through RPM-owned files used on every
   login, including existing accounts. Include the user's Arctic profile,
   ordinary Nix profiles and the shared profile so desktop files and icons can
   be found. No arbitrary copying over RPM/Flatpak desktop files. Test new
   installs/removals appearing in the launcher, icon lookup, terminals and
   applications launched by the user systemd manager.
5. Fedora owns Nix binaries, daemon units, build users and base configuration.
   Nix itself updates through Arctic's DNF updater, including Fedora upgrades.
   Retain root-only daemon trust, upstream signed binary-cache defaults and
   sandboxing. Add a mount dependency for `/nix` without replacing Fedora units.
   Do not turn off SELinux or introduce broad allow rules. Audit existing policy
   and RPM configuration before changing anything security-sensitive.
6. Root-owned installer fallback packages need an explicit administrative update
   path: pinned inputs must not be advertised as updated by `profile upgrade`.
   Validate a revision-aware supported Nix operation before enabling this UI.
   If that cannot be verified, report it as a merge blocker rather than silently
   leaving shared software permanently pinned or rewriting user profiles.
7. Document rollback, disk use and garbage collection. Profile rollback is
   separate from OS snapshots; `/nix` and home are outside the root snapshot.
   Keep generations by default. No automatic global GC or removal of another
   user's roots. Removing a package keeps its data and historical generations;
   disk space may only be recovered after deliberate history expiry and GC.

## Stages and acceptance gates

- Architecture/spec and official-source review (this document).
- Backend and argument/schema/failure tests; GUI and session integration.
- Packaging and update lifecycle; docs and reproducible native smoke script.
- Existing Python/JS/Go checks, QML lint and headless GUI navigation/screenshots;
  Fedora RPM build and repository CI. Tests with fake Nix are contract tests,
  not proof of real Nix behavior.
- Real Fedora 44 enforcing-SELinux VM: boot live media (mutations disabled),
  install to disk, verify `/nix` mount/ownership/labels, daemon after reboot,
  install CLI and GUI package as two non-admin users, search/install/remove,
  desktop launch/icons, updates/rollback, cross-user rejection, RPM Nix update,
  shared-profile update, Fedora/Arctic upgrade persistence and no new AVCs.
  Never disable security controls to make this pass.
- Open isolated PR, check its exact head's required CI, inspect final diff and
  merge only after material gates pass. Missing VM/SELinux evidence blocks
  merge even if mock tests and packaging pass. Do not merge PR #12 implicitly.

## Risks and remaining uncertainties

Nix CLI flakes/profiles are officially experimental. Pin supported CLI schema
expectations and reject unknown formats. Search may require a large nixpkgs
fetch/evaluation; bound time/results and show real progress/errors. Nix profiles
can conflict internally and can shadow other package sources in PATH. Store
builds can consume substantial disk space. GPU/Wayland applications may need
host-specific integration; a successful install does not prove launch support.
An unconfined container cannot qualify SELinux, boot-time mounts or real desktop
integration. Existing Arctic policy must not be represented as upstream Fedora
certification.

## Official references consulted

- [Fedora Nix change](https://fedoraproject.org/wiki/Changes/Nix_package_tool):
  RPM lifecycle, daemon and storage responsibilities; Nix packages are outside
  Fedora's QA/support boundary.
- [Fedora Nix daemon](https://packages.fedoraproject.org/pkgs/nix/nix-daemon/fedora-44-updates.html).
- [Nix profile upgrade](https://nix.dev/manual/nix/2.34/command-ref/new-cli/nix3-profile-upgrade.html):
  unlocked refs update; locked refs do not.
- [Nix profile list](https://nix.dev/manual/nix/2.34/command-ref/new-cli/nix3-profile-list.html):
  unique removal names, original/locked references and machine-readable output.
- [Official NixOS installer](https://github.com/NixOS/nix-installer): alternative
  is Beta; not used or mixed with Fedora RPM ownership here.

Test results and any deviation from this specification belong in `VALIDATION.md`.
