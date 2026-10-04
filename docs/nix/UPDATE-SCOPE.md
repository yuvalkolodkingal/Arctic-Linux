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
