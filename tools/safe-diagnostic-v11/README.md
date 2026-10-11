# Bounded same-image Safe GL completion experiment

This disposable diagnostic retains the original Safe boot baseline and two
separately authenticated SDDM restarts. Both use the existing software renderer,
security, cursor, profile, configuration, CPU counters and capture fixtures.
The default arm has no preload. The completion arm supplies one protected,
compiled interposer only to the newly attested Mango process. It calls the real
`glFlush`, then the real `glFinish`. SceneFX visibility/damage and DRM legacy
selectors remain unset in both arms.

A private, exclusively acquired 0600 counter uses FD 198 and a fixed 144-byte
x86_64 little-endian ABI. It binds nonce, UID, PID/start ticks, Mango executable
inode, exact packaged SceneFX inode and its proven dynamic-call return offset.
The armed constructor clears the preload environment and sets close-on-exec;
unarmed script interpreters preserve the trusted original exec chain. Forked
children remain unarmed. Readiness and two later observations require the same
owned descriptor and mapped compiled-library hash, a coherent zero-writer
snapshot, resolved real symbols and positive completed SceneFX call-site counts.
The counters cover authenticated top-level entries and completions; nested real
Flush calls pass through without counters or another Finish. These counts prove
the calls returned; they do not prove GPU completion or correct pixels. The raw counter remains private in the guest. Only a closed
typed projection and its packet hash enter the existing screened report.

The original 35/80/125-second baselines and QMP-before, raw Wayland readback,
QMP-after brackets remain unchanged. Readback can force repaint, so a clean raw
buffer cannot establish intact scanout. All original media must be viewed.
Mango-only CPU measurements exclude the rest of the graphics stack and the
single fixed order does not establish performance parity.

Each of the three original archive compartments retains the 40-member,
32 MiB/member, 128 MiB-expanded bounds, whole privacy screening and unmodified
primary-failure rules. The dedicated diagnostic driver budget remains 15 minutes;
product, startup and performance acceptance limits are unchanged. Owned cleanup
checks inode/FD identity and preserves foreign replacements and the first error.

Source preparation is disabled. Separate operational preparation changes only
`ready` to true; strict first-push sole-marker activation is required.
Every image, release, observer and performance acceptance flag remains false.
There is no product change or release qualification in this experiment.
