# Current update: expanded implementation specification

The user explicitly included desktop customization, optional privacy/network
connections, and guided gaming setup in the **same Nix update**. PR #13 remains
the review vehicle; work is separated into commits. No ISO publication is
included. The detailed Nix contract is in [IMPLEMENTATION.md](IMPLEMENTATION.md).

## Architecture findings: reuse what is already present

- Appearance already handles theme installation, wallpaper-derived accents,
  light/dark schedules, wallpapers/rotation, code fonts and weather widgets.
  Windows already exposes Mango border/gap/layout options. Reuse these rather
  than introduce another settings store.
- Shortcuts already adds/removes personal commands, detects conflicts and warns
  about shadowed binds. Mango uses the first matching bind. Editing and restoring
  bindings must use that precedence safely, retain recovery commands and avoid
  replacing RPM-managed default files.
- The Quickshell bar currently assumes the top edge. Geometry is shared through
  Theme.topInset with ScreenFrame, Popover and Toasts. Position, size and auto-hide
  must update those consumers together and preserve keyboard recovery.
- NetworkManager already manages WireGuard/OpenVPN imports and activation. The
  shell already controls installed Tailscale and user-directed sign-in/exit nodes;
  Settings needs discovery and optional setup paths. Extra tools must not become
  default dependencies. Remove the current OpenVPN weak dependency in favor of
  explicit installation. Tor Browser is already an optional installer module.
- Steam and ProtonPlus are already optional modules. NVIDIA generation detection,
  akmods, boot arguments, Secure Boot flow and hybrid GPU handling already exist.
  Do not replace that architecture with a universal driver installer. Add the
  missing installed-system setup/status and explicit 32/64-bit Vulkan support.

## Prioritized implementation

1. Finish and validate Nix backend/UI, ordinary users and administrative shared
   fallback updates. Fedora continues to own the engine. Preserve PR #12.
2. Extend existing per-user customization: edit/reset shortcut commands with
   conflict checks and recovery bindings; add safe taskbar controls and widget
   visibility to shell.json, validate allowed values and preserve unknown keys.
   Keep existing theme, wallpaper, font and window controls. Reload without
   destroying user overrides; reset only the settings this UI owns.
3. Optional network tools: installed/service/connection discovery; install-on-
   demand or installer opt-in; no automatic authentication, daemon startup,
   default routes, exit-node selection or traffic redirection. Tor is a per-app
   SOCKS option or Tor Browser, not a VPN. A listening port is not proof of Tor
   identity, bootstrap completion, DNS safety or anonymity. Preserve existing
   configuration/instances; show unknown when evidence is unavailable.
4. Optional gaming setup: detect AMD, Intel, NVIDIA and hybrids, show a concrete
   package plan and obtain OS authorization on action. Reuse RPM Fusion's supported
   driver generation selection. Install Steam/appropriate Vulkan components only
   when requested. Steam manages Proton downloads and account sign-in; never
   purchase a game or rewrite users' Steam credentials/settings automatically.
5. Each feature gets its own tests and reviewable commit, followed by full CI and
   RPM builds. All share the same final merge gate; there is no partial automatic
   merge or release.

## Acceptance and boundaries

- Persistence across logout/reboot and package upgrades; safe reset/undo,
  invalid/conflicting shortcut rejection, continued terminal/launcher/reload
  access; bar menu geometry, auto-hide reveal, different monitor sizes/scales.
- Optional packages absent in the default install; accurate discovery of existing
  services; no duplicate Tor daemon; authentication starts only on a user's click;
  Tor bootstrap unknown versus proven distinct; imported VPN profiles preserved.
- Hardware detection and planned packages tested with AMD/Intel/NVIDIA/hybrid
  fixtures. Native driver/game tests require appropriate hardware. Secure Boot
  enrollment, keys and real networking/security changes require approval at the
  time of action; implementing these UI choices is not permission to execute them
  on the user's machine.
- Actual Mango/Wayland gaming, anti-cheat support, GPU/driver/Proton compatibility
  and Secure Boot cannot be inferred from mocked hardware. Explain these limits
  in the UI/docs. No guarantee that every game or application will work.
- Existing Nix VM/SELinux gates remain mandatory. Missing hardware or native VM
  evidence is a material untested merge risk, even if all unit tests are green.

Estimate after scope expansion: several additional hours for implementation and
CI/GUI checks; hardware and enforcing-SELinux VM qualification is separately
constrained by available execution environments. Record results, not estimates,
in VALIDATION.md.

## Implemented review scope

- Personal shortcut edit/reset and packaged-action remapping preserve system
  templates and unrelated bindings, retain recovery keys and flag ambiguous
  upgrade changes. Taskbar supports all four edges, thickness, auto-hide and workspace/clock/media/tray
  visibility. Reset preserves unrelated JSON keys. Existing appearance controls
  remain the source of truth.
- Tor, Tailscale and NetworkManager OpenVPN are optional catalog selections.
  Settings detects available services and offers explicit terminal transactions.
  Presets prevent newly installed services from auto-starting at boot. Existing
  service configuration is retained. Tor's bootstrap percentage is shown only
  from the current default service invocation; alternate instances show unknown.
  Local SOCKS detection never asserts Tor identity or anonymous connectivity.
  WireGuard continues through existing NetworkManager import/connection controls.
- Gaming setup reuses catalog NVIDIA detection and offers Steam, 32/64-bit Vulkan
  and matching graphics packages. Existing RPM Fusion configuration is required;
  the UI links its setup guide when absent. It does not silently trust repository
  keys, enroll Secure Boot keys or change an existing driver generation. Steam
  performs account login and Proton downloads.

These are implemented behaviors, not claims of installed-machine or hardware
qualification. See [VALIDATION.md](VALIDATION.md) for the remaining merge gates.

## Four-edge taskbar and packaged shortcut implementation

`VerticalBar.qml` provides upright, scrollable controls on left/right edges.
`Bar`, `Theme`, `ScreenFrame`, `Popover`, `BarTooltip` and `Toasts` share the edge
geometry. Privacy and recording indicators stay outside the scrolling controls;
`PrivacyPeek` also exposes urgent indicators while auto-hide collapses the bar.
Settings validates four positions and a 28–56 pixel thickness. Keyboard focus
reveals the bar and scrolls focused controls into view.

`settings/scripts/builtin_shortcuts.py` generates per-user copies of packaged
`apps.conf`/`binds.conf`, changing keys only. State records stable action IDs (original-key IDs for duplicate actions)
and generated-file hashes. It rejects conflicting keys, typing-key capture and
unknown manual edits. Reset restores packaged symlinks. Login synchronization
rebuilds copies from the current RPM templates; removed/changed actions appear
as orphaned overrides for review. No system template is edited. While remaps
exist, Super+Ctrl+Alt+Return opens a terminal, F12 opens shortcut settings and R
reloads Mango. These recovery combinations cannot be reassigned by this editor.

Tests cover remap/reset, package template updates, conflict and manual-edit
refusal, and all four bar positions. Headless rendering covers small sidebars,
auto-hide keyboard reveal and inward menus; installed-VM acceptance additionally
uses Mango's parser and checks remap/bar persistence after DNF update/reboot.
Physical key events and multi-monitor pointer geometry remain separate checks.
