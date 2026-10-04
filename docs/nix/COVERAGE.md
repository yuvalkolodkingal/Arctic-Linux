# Implemented versus qualified coverage

The implementation is in PR13. “Implemented” is not a claim that a physical
machine, real account or network connection has been tested. No release is
published by the acceptance run.

| Area | Implemented | Evidence so far | Pending / guard |
|---|---|---|---|
| Nix software | Distinct source; search/install/remove/update/rollback; per-user profile; fixed administrative shared fallback update; Fedora owns engine | Enforcing KVM fresh install, live guard, daemon/store/session, two-user transactions, desktop/icon discovery and Nix-store window launch before/after reboot; all 26 CI checks | DNF loaded repositories but had no updates; actual newer engine/Fedora migration and VM shared-profile update untested |
| Shortcuts | Add/edit/remove/reset personal commands and remap packaged actions; conflict/manual-edit guards; protected recovery keys; template synchronization | 210 Settings tests (1 skipped), remap/reset/conflict/default-key-upgrade tests, all-page smoke and native Mango parser/reboot persistence | Physical key presses pending |
| Taskbar | All four edges, thickness, auto-hide, workspace/clock/media/tray visibility, scoped reset | Headless all four edges, inward menus, 800×480 sidebars and keyboard auto-hide reveal; native reboot preference persistence | Real Mango pointer/multi-monitor/scale testing pending; auto-hide disabled live |
| Appearance | Existing themes, fonts, wallpaper and window border/gap settings retained | Existing test suites | No new theme renderer or unrelated redesign; hardware/session persistence qualification pending |
| Tor Browser | Existing optional installer selection; installed detection and launch/install link | Catalog/backend and UI smoke | No real download/bootstrap/navigation test; never assert anonymity |
| Tor client | Optional installer/later RPM; service/process/SOCKS detection; current-invocation bootstrap; explicit start/stop | Fixed-command, non-mutating discovery and duplicate-instance tests | Real Tor connection untested; absent by default; no global routing/DNS changes; alternate instances report unknown bootstrap |
| Tailscale | Optional installer/later Fedora RPM; installed/running/backend state; explicit start/login/disconnect; existing shell exit-node UI retained | Backend/UI tests; Fedora package availability verified | No real authentication/tailnet test; no login, route or exit node selected automatically; service default disabled |
| WireGuard | Existing NetworkManager import/activation retained | Existing network suite | No new provider or key generator; actual tunnel test requires user-selected config |
| OpenVPN | Optional NetworkManager plugin in installer/later setup; existing import/activation retained | Catalog/backend tests | No default dependency; actual provider/tunnel test requires user config |
| Gaming common | Opt-in reviewed Steam + 32/64-bit Vulkan plan; ProtonPlus link; Steam manages Proton/account | Planner fixtures and UI smoke | Requires previously configured RPM Fusion; no purchases/login or game-support guarantee |
| AMD / Intel | Mesa/Vulkan both architectures; existing Freeworld preserved | Device-independent fixture tests | Actual Vulkan rendering/game tests unavailable; transaction remains explicitly user-authorized |
| NVIDIA | Existing catalog generation selection; 32/64-bit libraries; reject unsupported/mixed/different installed generations | Device-independent fixture tests | New driver blocked when Secure Boot enabled/unknown; enrollment/key generation never automatic; actual module/GPU/game test pending |
| Hybrid | Both appropriate package sets; existing discrete-GPU launcher guidance | Planner fixtures | Real GPU offload and display switching require hardware |

## Acceptance workflow

The existing ISO workflow gains `nix_acceptance=true`, used with `release=false`
and `boot_test=false`. It builds the exact selected branch head, then uses the
existing QEMU install harness on `/dev/kvm`. A small `--guest-check` extension
reuses the guest-probe pattern from PR12 without merging its broader release
reliability work. The probes require SELinux Enforcing and QEMU, reject live
mutations, install into a blank VM disk, check mount/ownership, use two ordinary
users, launch a real Nix Foot window in Mango, check login paths and profile
operations, run signed-repository DNF updates and boot again. A same-version Nix
engine is reported unrun for version-change proof, never a successful upgrade.

Screenshots, serial records and logs are uploaded even on failure. Failures are
not continue-on-error and do not authorize security relaxations. Physical GPU,
account-dependent VPN/Tor connectivity, unsigned-cache rejection and adversarial
sandbox/disk-failure tests are not established by this workflow.
