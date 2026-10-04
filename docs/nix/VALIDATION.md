# Validation record

The final production-code candidate `602f2a0` passed all 26 CI checks and
[enforcing KVM acceptance](https://github.com/yuvalkolodkingal/Arctic-Linux/actions/runs/37189777884).
No OS release or physical-machine change was performed. Earlier checkpoints below
are retained as history; the final qualification section defines the current boundary.

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

Outstanding gates at the initial container-only checkpoint:

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
At this checkpoint the native VM gate was still pending. Later results below
qualify representative Nix/desktop behavior, not hardware compatibility.

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

## First enforcing installed-VM result

[Run 37186553993](https://github.com/yuvalkolodkingal/Arctic-Linux/actions/runs/37186553993)
built and installed head `5938f6e` under QEMU/KVM with SELinux Enforcing.
Live mutation refusal, installed daemon, encrypted persistent `/nix` mount,
root ownership, actual search/install/CLI execution, desktop-entry/icon discovery,
login PATH/XDG directories, two-user isolation, update/remove/rollback and retained
trust settings passed. No matching new Nix/Foot AVC was found in that test window.
The reported store label was `default_t`; merely recording labels is not proof of
upstream SELinux support or confinement for every application.

The run failed its graphical window checks because the probe omitted
`MANGO_INSTANCE_SIGNATURE`; it did not reach DNF upgrade/reboot. An earlier probe
startup race also failed before IPC was ready. These are harness failures, not
passing graphics or update evidence. The corrected probe waits for readiness and
obtains the instance signature from matching session children (Mango sets it after
exec, so its original `/proc` environment lacks it). A regression checks missing,
matching and ambiguous session environments. The next exact-head run must still
pass the actual window and update/reboot assertions.

Four-edge/taskbar and packaged-key remapping tests: Settings 209 tests (1 skipped),
shell 287 (5 skipped); six customization tests also passed with native Mango
0.17.3 parsing in Fedora. All Settings pages, three-display arrangement and
valid/invalid writes passed headless smoke. Sidebars were rendered at 800×480,
including keyboard auto-hide reveal and an urgent recording fixture remaining
visible while collapsed. No actual recording was performed. All 26 CI checks,
including Fedora RPM builds, passed at `6407623` before the probe correction.


## Final representative qualification (2026-10-04)

Production code: `602f2a00a737a82e0ff9b94ffb49145499038994`.
[ISO/KVM run 37189777884](https://github.com/yuvalkolodkingal/Arctic-Linux/actions/runs/37189777884)
passed. Its `nix-acceptance` artifact contains serial assertions and screenshots;
its ISO was a test artifact, not a published release. Final documentation edits
after this SHA do not change the production code or test harness.

- Fresh encrypted installation and live mutation refusal passed with SELinux
  Enforcing, without policy or security-setting changes. `/nix` mounted its own
  persistent Btrfs subvolume; daemon and ownership checks passed on both boots.
- Actual search/install, Hello execution, update/remove/rollback and cross-user
  isolation passed. Desktop-entry discovery changed from absent to present;
  icons loaded; executing the entry created a Mango client for at least five
  seconds, with the executable verified under `/nix/store`. Direct Foot launch
  also passed before and after reboot. The real login PATH/XDG directories passed.
- Native Mango parsed remapped configurations and retained recovery bindings.
  The remap and right-side taskbar preference survived reboot; restoring built-in
  defaults restored packaged symlinks. Headless checks separately covered all
  four edges, small screens, inward menus and keyboard auto-hide reveal.
- DNF loaded Fedora, Arctic and the already configured RPM Fusion repositories
  successfully with signature verification retained. It reported **Nothing to do**.
  A subsequent boot had a different boot ID and preserved the Nix generation,
  binaries and graphical launch. This proves repository/update-check operation
  and reboot persistence, **not a newer package/engine or Fedora-version migration**.
  Nix stayed at 2.34.8; `engine-version-change` is explicitly `unrun`.
- Trust settings remained signatures required, sandbox enabled and root-only
  trusted users. No matching new Nix/Foot AVC was found in the journal test window.
  These are configuration/journal checks, not adversarial signature or sandbox tests.
- Final local suites: Settings 210 tests (1 skipped), shell 287 (5 skipped), tools
  37 (1 skipped). Seven customization tests also passed with native Mango 0.17.3.
  All 26 ordinary CI checks passed on the production-code candidate, including
  Fedora RPM builds, native config parsing, Go/Python/Node checks and GUI smoke.

### Remaining limits and merge assessment

The representative fresh-install, enforcing-SELinux, GUI and reboot gates are
satisfied. The engine and daemon still belong to Fedora RPMs; this change does
not introduce a new engine installer, trust policy or OS upgrade mechanism.
A future newer engine/Fedora-version migration remains untested, as do daemon/
mount failure injection, disk-full/interrupted-download recovery, adversarial
cache/sandbox scenarios, and the administrative dialog as a complete UI flow.
The shared-profile transaction itself was tested with the native daemon in the
Fedora container; do not describe that as an enforcing-VM shared-update test.

Optional network/account connections and GPU/Proton execution are unqualified.
Their setup remains explicit and guarded: no automatic authentication, traffic
routing, repository trust, driver-generation replacement or Secure Boot enrollment.
Planner fixtures and ordinary package installation paths do not certify hardware
compatibility. These limits must remain visible; they are not invented passing
checks or permission to perform those actions on a user's machine.
