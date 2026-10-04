# Validation record (in progress)

No merge or OS release has been performed. This is a draft implementation.

Tested locally on 2026-10-04:

- Fedora 44 container, Fedora RPM Nix 2.34.8, actual shared daemon and two ordinary
  users. Installed and ran hello; listed the modern manifest; updated, removed
  and rolled back the personal profile. Second user installed hello separately;
  direct access to the first user's profile failed with permission denied.
- Actual nixpkgs search returned attribute names, descriptions and versions.
- Confirmed that a shared pinned profile does **not** update with normal upgrade
  or `--override-flake`. Built a staged modern profile, set it as a generation
  using `nix-env --set`, verified manifest version 3, and rolled back.
- Administrative helper rejected a custom hello shared entry. With an actual
  pinned lazygit installer entry, staging, switching and rollback succeeded.
  The sanitized helper environment lacked the workspace proxy, so Nix reused
  cached upstream metadata. This proves the local transaction, not fetching a
  new upstream revision.
- Shell Python suite: 281 tests passed, 5 skipped (before later admin-helper tests).
  Settings suite: 193 passed, 1 skipped. `go test ./...` passed.
- Nix contract tests: user scope, malformed arguments/schema/JSON, timeouts,
  failed mutations, pinning, foreign links, empty-profile rollback; pass as root
  in Fedora and as an ordinary workspace user. These use mocks and do not prove
  SELinux or OS installation behavior.
- Fedora qmllint: new Nix page parsed cleanly. Existing dynamic Loader warnings
  remain in GetApps.qml. ShellCheck on changed shell commands passed. rpmspec
  parsed the updated package specification.
- Headless Sway/Quickshell rendered the Nix page with no QML runtime errors.
  Missing hardware/session services produced expected DBus/polkit warnings.
  Rendering alone does not establish GUI install/launch behavior.

Test-container HTTPS initially failed because it lacked the execution workspace
CA bundle. The existing workspace bundle was copied into the disposable container
and supplied explicitly; TLS verification and RPM signature checks stayed enabled.
No host trust/security setting was changed.

Outstanding material merge gates:

- Real enforcing-SELinux installed-system VM, fresh install/reboot, relabel,
  daemon/mount failure behavior, unsigned-cache rejection and actual build
  sandbox behavior. The container reports SELinux Disabled and has no /dev/kvm.
- Graphical Nix application launch, icons/portals and refresh after changes;
  Settings authentication and user-service environments on the installed OS.
- Actual newer-version update and engine/OS upgrade persistence; disk-full and
  interrupted-download recovery. Live versus installed behavior in real media.
- Final full CI/RPM build for the eventual PR head. Earlier checks are not a
  substitute for checks on the final commit.
