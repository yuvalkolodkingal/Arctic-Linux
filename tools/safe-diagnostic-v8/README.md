# Exact-image Safe debug and legacy-DRM diagnostic

This is one artifact-only experiment against the frozen A2 candidate. It cannot
qualify a release, optimization, new product image or the initial Safe boot.
Every acceptance flag stays false. The original Safe Try `nomodeset` boot and
1920×1080 QMP-only captures at 35, 80 and 125 seconds remain unchanged.

After that baseline, two fresh SDDM sessions run in fixed order: `default-restart`
and `legacy-restart`. Both preserve the exact trusted packaged session script,
profiles, desktop arguments, software-rendering settings, security, configuration,
library hashes and authenticated new session/VT/IPC identities. Both append one
Mango `-d` argument before initialization; both unset the two prior SceneFX
visibility/damage variables. The first unsets `WLR_DRM_NO_ATOMIC`; only the second
exports `WLR_DRM_NO_ATOMIC=1`. A pre-existing libliftoff selector is rejected.
An unavailable legacy interface can fail rather than produce a substitute result.

Matching packaged wlroots 0.20.2 source recognizes that selector and bypasses the
atomic FB_DAMAGE_CLIPS commit path. This supports a finite diagnostic comparison,
not a claim that atomic damage caused the original defects. Matching Mango 0.17.3
explicitly creates the SceneFX renderer; a generic Pixman selector would not
select a compatible SceneFX implementation. The forced-software DRM-global guard,
normal hardware behavior and SELinux Enforcing remain unchanged. The earlier
SceneFX visibility/damage switches alone and together still left damaged frames.

Debug logging is symmetric and changes timing/cost. Mango's default WLR_ERROR
level previously hid allocator startup observations. Its actual stderr file is
read only if it is the exact protected regular SDDM user log currently held by
that PID. A nonce/arm/PID sentinel in the acquired trusted wrapper binds the
exec chain. PID-scoped journal capture is an alternative when stderr is not that
file, but it too must contain the exact current nonce/arm/PID sentinel. Old
same-boot records at a reused PID cannot supply new-process observations. A
missing or conflicting sentinel leaves the projection unbound and unknown. One early snapshot is bounded to 1 MiB; the entire original snapshot must
pass the unchanged privacy scanner before any closed projection. No raw log,
path, arbitrary GL string, transcript or exception message leaves the guest.
Source-owned renderer/platform/allocator/interface markers and a closed renderer
class remain unknown if absent. Try logs do not prove allocator construction.
Private logging continues during the bounded experiment; its cost is included in
both arms and is not a normal-product performance measurement.

A separate, deadline-controlled read-only DRM metadata worker binds current
Mango PID/start identity and its actual card nodes. It uses fixed public Linux
UAPI requests, a separate O_RDONLY/CLOEXEC/NOFOLLOW card FD, bounded arrays and
closed numeric/enum observations. It requests no client caps or modeset/master
changes. GETFB2 may allocate private GEM handles; closing only this worker's FD
releases those file-owned handles. No Mango FD or handle namespace is reused.
Without atomic/universal client caps, hidden planes and FB_DAMAGE_CLIPS remain
unknown, not unsupported. Sequential resource observations are not an atomic
snapshot. Permission errors and inaccessible fields remain unknown. The 20-second
worker timeout uses normal kill/reap; a kernel task in uninterruptible sleep can
delay reaping, so no real-time deadline guarantee is claimed.

Each arm retains QMP-only captures at 35/80/125 seconds after authenticated ready,
then the unchanged restored desktop and synthetic Foot launch/repaint phases.
Every raw Wayland capture is bracketed by QMP-before and QMP-after. Readback may
force repaint; an intact raw frame cannot isolate scanout or prove a fix.
Original stride bytes, pixel format, metadata, packed RGB and lossless derived
PNGs retain the existing source guards and privacy oracle. Mango-only 100 Hz CPU
and RSS counters are one fixed-order observation with warm-cache, clock-boundary,
logging, startup/preconditioning and readback confounders.

The three separately screened artifacts keep the original bounds: 40 members,
32 MiB/member, 128 MiB expanded per compartment and 200 MiB guest wire. The same
15-minute diagnostic driver, 19-minute wrapper, 20-minute step and 40-minute job
bounds remain. Primary failures survive cleanup/reporting failures; all acquired
process, inode, FD, wrapper and configuration identities remain guarded.

Preparation adds exactly the nine new diagnostic paths and one literal v8 branch
exclusion in generic CI. The activation guard verifies that exclusion against the
immutable parent's whole CI bytes, all other inherited paths/markers/plans, the
first-attempt hosted push and the sole fresh 41-byte marker child. No existing
workflow acceptance limit, source plan, image pin or product configuration changes.
Source tests attest fixtures and guarded operations; actual KVM captures and full
original media review remain necessary before interpreting this experiment.
