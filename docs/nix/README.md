# Using Nix in Arctic

Get apps → **Nix packages** searches Nixpkgs and installs packages for your account.
The Installed view removes packages; Update and Roll back operate only on your
Arctic profile. Settings → Updates links to these controls. A graphical package
must provide a desktop file to appear in the launcher. Nix programs are not
application sandboxes; GPU, portals and host integration can differ from Fedora
and Flatpak. Prefer the source that supports your application on your hardware.

Your profile is `~/.local/state/nix/profiles/arctic`. An existing `.nix-profile`
or legacy `nix-env` installation is not imported, overwritten or converted.
Every account has its own profile; users share immutable store objects, not the
right to edit one another's profiles. Log out and back in after the integration
RPM first arrives so the desktop and user services receive PATH/XDG_DATA_DIRS.

```
arctic-nix search hello
arctic-nix install hello
arctic-nix list
arctic-update nix
arctic-nix remove hello
arctic-nix rollback
```

The default input is `github:NixOS/nixpkgs/nixos-26.05`. This is a moving release
branch, not a reproducible pin. `arctic-nix list` reports each original input,
locked URL, attribute and store paths. Keep that output to reproduce a specific
installation, or use `arctic-nix install --revision FULL_40_CHARACTER_COMMIT ATTR`.
Pinned packages stay pinned when updating. For projects, commit a flake.lock
rather than depending on the desktop's current profile. The modern profile/flake
CLI remains experimental; this integration targets Fedora's Nix 2.34 and fails
on unknown manifest formats.

**Nix itself:** Fedora owns `/usr/bin/nix`, the daemon and its build users.
Arctic's ordinary DNF/offline system update updates these RPMs. Do not run
`nix upgrade-nix`, install another Nix distribution over them, or remove the Nix
RPMs while relying on this integration. Existing external installers/receipts
need an administrator-led migration; there is no automatic destructive takeover.

**Shared installer packages:** Settings → Updates → Shared installer Nix packages
opens an administrator-authenticated operation. It is restricted to the
installer's known lazygit/yazi entries with their original pin or the supported
release input. An update builds a complete replacement before switching the
shared profile. It explicitly moves the installer pin to the release branch;
the old pinned generation remains available through Roll back. Custom entries,
priorities or outputs cause a refusal. Other users' personal profiles are never
changed. Avoid simultaneous manual root-profile edits; an observed concurrent
change causes an abort. The helper's own invocations are locked.

Nix may fall back to a cached flake if the network cannot be reached. Read its
output; a completed operation is not proof that the latest remote revision was
retrieved. Running applications continue using their current process/libraries
until restarted. Profile rollback does not restore application data or the OS.
Engine downgrades may also face Nix database compatibility constraints.

**Storage:** the installer mounts the `@nix` subvolume at `/nix`; home and `/nix`
are outside the root snapshot. Fedora's daemon unit already uses
RequiresMountsFor for its store/state directories. Keep `/nix` at its canonical
path, root-owned, and preserve mount and SELinux labels across upgrades. Do not
make it world writable or replace it with a symlink. The GUI disables mutations
in live sessions, where the overlay is temporary.

Removed packages can remain rooted by older profile generations. No history is
silently expired and no automatic global garbage collection is enabled. Inspect
`df -h /nix`, `nix store gc --dry-run` and
`nix profile history --profile ~/.local/state/nix/profiles/arctic` before cleanup.
After choosing to lose older rollback points, an expert can use
`nix profile wipe-history --profile ~/.local/state/nix/profiles/arctic --older-than 30d`
and then ordinary Nix garbage collection. Administrators must account for all
users and shared roots before any system-wide cleanup. Never delete store files
manually. Removing an app does not delete its own files or settings.

**Trust and policy:** free software evaluation is the default. Unfree software
requires a deliberate, legally appropriate Nixpkgs policy; Arctic does not enable
it or accept flake-supplied cache configuration on your behalf. Retain signed
cache verification and the official NixOS cache. Extra caches/keys are an
administrator trust decision. `trusted-users` is root-equivalent access, not an
ordinary package-install permission. Never add desktop users or the wheel group
there, and never add ordinary users to nixbld. Keep SELinux enforcing and build
sandboxing enabled. Fedora 2.34.8 reports sandbox-fallback=true by default;
Arctic does not claim to have hardened or qualified that default in an enforcing
VM. See [validation](VALIDATION.md) for the actual test boundary.
