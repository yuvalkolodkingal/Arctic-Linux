# Bounded same-image Safe full-damage discriminator

Diagnostic only. Keep the original A2 Safe boot baseline and one default debug
restart, then compare a new debug restart with only
`WLR_SCENE_DEBUG_DAMAGE=rerender`. Both arms preserve the original software
renderer, cursor, security, profile, configuration, CPU counter and capture
contracts. Visibility and legacy selectors remain unset. The private FD2
ownership, nonce/PID/start binding, whole-text privacy screening, read-only DRM
queries, and acquired-resource cleanup are unchanged from reviewed v9.

Exact packaged SceneFX 0.5 supports the selector before scene creation. It
forces both repaint damage and pending backend commit damage. This experiment
therefore tests the broad partial-update/buffer-reuse path; it does not isolate
fences, KMS copying, shaders, or an actual graphics cause. Debug logging and
ordered restarted sessions perturb timing. No initial-boot equivalence,
optimization, image qualification, or release acceptance follows from workflow
success or clean raw readbacks.

The original 35/80/125-second boot and arm baselines, Foot fixtures, three
QMP-before/raw-SHM/QMP-after brackets per arm, 20-second capture bound, 15-minute
inner diagnostic deadline, 19-minute wrapper, 20-minute capture step, and
40-minute job budgets remain unchanged. Each compartment retains at most
40 members, 32 MiB per member, and 128 MiB expanded. Source is disabled; only a
separately reviewed operational preparation can be activated through the fresh
sole-marker push guard on `codex/safe-rerender-v10-20261010`.
