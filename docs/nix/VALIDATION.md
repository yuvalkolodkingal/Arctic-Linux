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
  Settings suite originally: 193 tests, 1 skipped. `go test ./...` passed.
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

## Expanded update validation

- Go suite passed with the new optional catalog entries. Shell Python: 285 tests,
  5 skipped. Settings Python: 205 tests, 1 skipped; the added driver-generation
  guard also passes its six-test gaming suite. Final CI reruns the complete suites.
- Added tests cover personal shortcut edit/conflict/reset, unknown settings
  preservation, non-mutating network discovery, current-invocation Tor bootstrap,
  duplicate-instance rejection and fixed command plans; hardware fixtures cover
  AMD, Intel, current/legacy NVIDIA, hybrid, Secure Boot and existing Freeworld.
- Real Nix GUI search rendered 29 results for hello; bottom taskbar and keyboard
  reveal rendered in headless Sway. This is not an installed Mango/multi-monitor
  auto-hide or graphical Nix application compatibility test.
- Settings smoke navigation exposed undefined initial network booleans; fixed.
  The local container also needed the CI-declared wlr-randr dependency for its
  three-display check. No production behavior or tests were weakened.
- No Tor/Tailscale connection, repository trust change, Secure Boot enrollment,
  graphics-driver installation or Steam account action was executed. Native
  network connections and real GPU/Proton/games remain unqualified.

The final PR checks and RPM build are recorded on GitHub for the exact head.
Passing them does not waive the enforcing-SELinux VM and native desktop/hardware
merge gates above.

## Launcher refresh regression found during VM qualification

Fedora's installed Quickshell (0.2.1 git20260209) was tested with a desktop entry
whose Nix-style profile appeared after startup. The entry stayed absent until
an existing XDG applications directory changed. Login setup now creates the
standard user applications directory before Quickshell starts. Successful Nix
mutations atomically update a non-desktop generation marker there, causing the
existing monitor to rescan the profile paths; no desktop entries are copied or
overwritten. The same native reproduction changes from absent to present with
the helper. Tests also preserve unrelated entries and reject paths outside home.

The VM probe now checks real desktop-entry/icon discovery and verifies that the
launched Foot process comes from /nix/store, so an already-installed Fedora Foot
cannot accidentally satisfy the Nix launch check. These new probes are pending
the next exact-head acceptance run.
