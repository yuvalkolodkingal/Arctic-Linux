# Arctic Linux optimization candidate

Work is local on `codex/optimize-preserve-functionality`, based on main
`f1e3c518ae6a1d8d0fd85dcf117baa8341701703` (includes PR 18's lock-clock fix).
The user now authorizes the combined draft PR, exact-head Actions candidate and merge after all gates pass. Existing v1.2.0 tags/assets remain immutable; no stable ISO replacement has been performed.
The approved wallpaper merge on main `cdf4960f567842e853b6b3503c542d739ff215f7`
has been reconciled locally and is included in the combined candidate.

The current firm ceiling is **strictly below 2,000,000,000 bytes**, decimal 2 GB, approximately 1.863 GiB. The preference is **strictly below 1,600,000,000 bytes**, decimal 1.6 GB, approximately 1.490 GiB. The original 1.5 GB request in historical trials is superseded.
GB means 1,000,000,000 bytes; GiB means 1,073,741,824 bytes. This is a target,
not permission to remove functionality or move offline features to network downloads.
Priority order: stability and feature parity, responsive desktop and low memory,
then image size. "As fast as possible" and "as small as possible" have competing
compression costs; measurements decide the compromise.

## Research and execution update, 6 October

The corrected artifact-only workflow [37440736427](https://github.com/yuvalkolodkingal/Arctic-Linux/actions/runs/37440736427)
on exact source `83c2984a794d7036319f012f3400cedbbb4aeed3` completed Nix VM
acceptance successfully. Both offline installation plus installed acceptance and
the reboot acceptance invocation passed. Its required ISO size gate failed;
paired KVM acceptance was disabled and therefore skipped. The metadata artifact
download returned HTTP Forbidden, so exact ISO bytes/SHA and individual Nix
records remain unverified. Artifact archive bytes/digests are not ISO values.
The separate controlled [KVM run 37450977544](https://github.com/yuvalkolodkingal/Arctic-Linux/actions/runs/37450977544)
started only after Nix completed and uses the same source, with release disabled.
It is a separate build; immutable image identities must be compared before
combining evidence. No merge or release is qualified. Screenshot helper exit
status does not establish guest security or visual correctness when collection
was not requested. The native command stripping below is a later packaging
change and is **not in either of these images**.

### Native command symbol tables

The three shipped pure Go Arctic executables already contain no DWARF debug
sections. Their remaining native symbol/string tables can be omitted by Go's
documented [`-s -w` linker flags](https://pkg.go.dev/cmd/link), while retaining
Go runtime stack metadata and `-B gobuildid`. A same-source Fedora Go 1.26.8
control, including the current RPM debug-strip stage, had 28,250,584 logical
bytes across `arctic-install`, `arcticd` and `arctic-webapp`; the stripped build
had 26,362,762, saving **1,887,822 bytes**. A fixed EROFS LZMA 6 / 1 MiB subset
fell from 7,954,432 to 7,655,424 bytes, saving **299,008 bytes**. This is a
three-file subset result, not a full ISO marginal or a route below the ceiling.
Running Fedora's actual `brp-strip` and `brp-strip-comment-note` scripts on
separate copies adjusted alignment: final logical saving was **1,890,936 bytes**,
and the subset fell to 7,647,232 bytes, saving **307,200 bytes**. Original
experiment files remain unchanged. Other RPM hooks and the full ISO still need
exact-head qualification.

Implemented only for these pure Go commands; the cgo WebKit host's Fedora flags
remain intact. PIE, GNU RELRO, non-executable stack, GNU build IDs and Go
`.gopclntab` are present in both variants. Actual offline installer plans,
catalog JSON and web-app render fixtures match, and version/help commands run.
The existing Go suite passed with these flags. Independent review confirmed
all six original artifact hashes, ELF hardening, fixture parity and actual
SIGQUIT traces containing named Go functions and source lines.
Native symbol names are unavailable to ELF debuggers; the shipped binaries
already lacked DWARF, and Go runtime traceback metadata is retained. No runtime
speed or RAM improvement is claimed. Revert this spec linker flag change for
rollback. Exact-head RPM and VM checks remain required before merge.
Evidence: `out/audit/candidate/native-elf-debug-audit.json` and
`out/audit/candidate/go-strip-research.json`, `go-rpm-postprocessing.json`,
and `out/audit/native-strip-review.json`.

### Nix socket activation

An eager Nix daemon in the installed candidate had **19,692,544 bytes PSS** in
one process sample. Upstream socket activation left no Nix daemon process before
use, including after an offline encrypted reboot and desktop login. An untrusted
user's store request then activated the daemon under SELinux enforcing. The
real Foot closure was fetched with the shipped `arctic-nix` command; subsequent
offline profile add, remove and rollback passed, and its native Wayland window
mapped. The profile and window launch survived the restricted-network reboot.
There were no matching new Nix/Foot AVC denials in either successful phase.
No SELinux rules changed. The initial observer's JSON assumption failed on a
warning-prefixed successful store response; that failure and its valid eager
daemon sample remain archived separately from the corrected successful runs.

The candidate now enables `nix-daemon.socket` and disables eager startup in the
release preset, installer module and KIWI setup. Enabling the socket is required
before disabling the service. Installer regression controls reject a missing
socket before service disable/handoff and permit a failed disable to retain
functional Nix. Acceptance checks require the active enabled socket, disabled
eager unit and an actual user store request. Existing installed-user choices
are not migrated. Independent review found that the existing post-update/reboot
branch returned before its AVC gate. A shared denial gate now runs in both
installed passes, starting before the first store request; injected Nix/Foot
denials and journal-read errors fail its controls. Focused installer/catalog Go
checks and 18 Nix/network Python tests passed. Revert these four configuration
paths and installer controls together to restore eager defaults.

This is a single disposable TCG trial on source `244e4dd`, using a copy-on-write
overlay with its original installed disk mounted read-only. Fedora Nix version
2.34.8-1.fc44 and Arctic's Nix policy/session files match the current branch.
It proves the exercised functionality, **not** a net whole-system RAM or boot
gain: socket/PID1 overhead is unmeasured, and the daemon remains resident after
activation. First-request latency, exact-new-image install/update/reboot, Safe
graphics and other production gates remain required before merge. Evidence:
`out/audit/nix-socket-research/` (separate activation and offline-reboot records).

| Priority | Finding and measured result | Action, rollback and acceptance |
| --- | --- | --- |
| 1 | Kitty startup regressed in the completed six TCG samples: first opening +21.03%, subsequent +13.64%. Composition includes approved clock/wallpaper work, a Mango rebuild and package updates, so this cannot be attributed solely to catalog eviction. | Keep the combined merge blocked. The active interleaved KVM comparison must resolve the regression before claiming OS gains. Preserve both raw datasets and exact image/tool identities. |
| 2 | Get apps constructs its chooser at shell startup, even while the launcher shows its home view. Three runs of the exact implemented QML change reduced isolated component PSS median from 88,355,840 to 75,924,480 bytes (12,431,360 saved); its visual tree fell from 146 to 2 items before first opening. | Implemented first-use loading. Pages remain instantiated afterward, preserving drafts and callbacks; AppsService still owns jobs. First opening added about 32.8 ms in this probe. Actual route and repeated hide/show controls passed. Revert the GetApps.qml diff to roll back. Require real desktop/keyboard/Get apps and exact-candidate CI gates. These are component measurements, not a full OS RAM or startup improvement claim. |
| 3 | Source artwork is already export-ignored, but a full shallow checkout still stores 372,297,384 bytes of Git pack data and materializes 390,599,547 bytes. Simple sparse checkout loses its download saving when git archive prefetches all omitted blobs. | Implemented sparse checkout only in OS build jobs plus removal of export-ignored roots from the temporary Source0 index. A cold filtered clone through source archiving took 4.47 s and retained 15,705,100 pack bytes, saving 356,592,284 stored pack bytes. All 2,374 archive members matched original paths, modes, types, links and content hashes. Dirty/untracked sources, public-key blob injection, nested exclusions and the real index were preserved. Roll back the workflow and build-script diffs together. Require exact-head RPM builds; this does not shrink the ISO. |
| 4 | One eager Nix daemon sample had 19,692,544 bytes PSS. A disposable enforcing socket/profile/GUI trial and offline reboot left no daemon before first use; actual untrusted-user activation and persistent Foot/profile rollback passed. | Candidate defaults now use the upstream socket, with mandatory socket enable before eager-service disable and no policy change or existing-user migration. Revert preset, module, KIWI and installer changes together. Exact-image enforcing acceptance remains a merge gate; no whole-OS RAM or boot gain is claimed. |
| 5 | Same-content XZ level 6 / CRC32 live-initrd trial saved 6,607,627 bytes (241,962,859 to 235,355,232), with the 306,176-byte early microcode prefix unchanged. All three decoded CPIO hashes matched `09a6075578897f78af22c5daae673b60479bbee2d247165ca4e2073ea52b063d`. | Rejected for the current speed priority: cached host userspace decode median rose from 0.44 to 1.97 s. Encoding took 153.32 s, maximum RSS 97,620 KiB. It has no Secure Boot, BIOS, encryption or low-RAM boot qualification. Keep current Zstd; no root-owned package payload was changed. |
| 6 | The largest 20 duplicate groups account for 104,476,731 logically repeated bytes, but all already share complete EROFS data mappings. Flatpak objects/deployments also share existing hardlinks; no unreachable objects, DNF downloads or populated Nix store were found. | No generic cleanup, cross-package hardlink replacement or feature deletion. Packed-fragment accounting gives all Flatpak storage coverage 477,196,288 bytes, including shared clusters; it is not a removable-byte estimate. Browser packaging remains a material containment/update choice requiring explicit approval and one actual candidate trial. |

The first-use QML probe used actual production GetApps and its pages in a Qt
software offscreen Window. Both variants suppressed the same package/network
setup call to isolate visual work. It preserves the original behavior after
first use and does not unload hidden pages. Ten additional direct-first-route
cases checked DNF/all and Flatpak queries, console, a web URL and chooser, with
three hide/show cycles per case. An independent source review found no blocking
lifecycle, archive parity or signing-path issue. More aggressive unloading requires
separating visual lifetime from draft state and asynchronous callbacks. Releasing
clipboard/emoji/wallpaper arrays alone is not yet a measured high-impact change;
clipboard previews already disable Qt image caching and wallpaper thumbnails
already bound their decoded width to 480 pixels. No blanket image-cache removal
was adopted.

The checkout tests count **stored pack bytes**, not wire telemetry. One sequential
cold full clone took 38.22 s; the filtered/pruned clone plus source archive took
4.47 s. Network/server variation prevents a general CI speed promise. Bare-tree
tar timestamps retain the build's existing wall-clock behavior, so archive
parity is established by member content/metadata rather than identical tar hashes.
Temporary-index pruning was necessary: both ordinary sparse and explicit-path
archive controls fetched approximately 372 MB of packs. The actual working tree
and real index remain unchanged by source archiving.

Primary references informing these choices: Qt recommends measuring before
optimizing, event-driven work and [lazy creation](https://doc.qt.io/qt-6/qtquick-performance.html);
[Loader.active](https://doc.qt.io/qt-6/qml-qtquick-loader.html) controls object creation;
[checkout v4](https://github.com/actions/checkout/blob/v4/README.md) supports sparse
patterns and non-cone mode. EROFS documents fragments, deduplication and
[cluster-size/random-access costs](https://erofs.docs.kernel.org/en/latest/mkfs.html).
Flatpak documents [OSTree deployment hardlinks](https://docs.flatpak.org/en/latest/under-the-hood.html),
DNF5 documents [download-cache behavior](https://dnf5.readthedocs.io/en/latest/dnf5.conf.5.html),
and Nix documents [GC reachability](https://nix.dev/manual/nix/2.34/command-ref/nix-store/gc)
and supplies a [daemon socket unit](https://raw.githubusercontent.com/NixOS/nix/2.34.8/misc/systemd/nix-daemon.socket.in).
[Dracut](https://dracut-ng.github.io/dracut/man/dracut.conf.5.html) accepts explicit
compression arguments; the [kernel's XZ documentation](https://docs.kernel.org/staging/xz.html)
requires CRC32 or no integrity check for its decoder. These support the bounded
same-content experiment, not a boot qualification for its output.
Fedora's online systemd guide returned an access challenge; no claim is based on
its unavailable body. Arctic's actual RPM/service/process inventories and source
presets take precedence over generic service-removal advice.

Evidence: `out/audit/getapps-lifecycle-summary.json`,
`getapps-lifecycle-research/exact/result.json`,
`checkout-research/{comparison,explicit-archive-comparison,pruned-archive-comparison}.json`,
`checkout-research/guards/result.json`, `compression/initrd-xz6-summary.json`,
`getapps-lifecycle-research/direct-first-route/result.json`, `research-source-review.json`,
and the original inventory/runtime datasets. The separate battery commit remains
`98f663d972ebb3dfcd64cf3793604f6f9400c280` and is independently applicable to approved main.

## Baseline evidence

The public v1.2.0 ISO has been downloaded and independently verified:

| Measurement | Baseline |
|---|---:|
| ISO bytes | 2,322,073,600 |
| SHA-256 | `054db5c43cae47fb60f8f43efc8e052b569aa1b14e8f15adcb15cdc48265182f` |
| Reduction needed for current firm ceiling | At least 322,073,601 bytes (13.87%) |
| EROFS payload | 1,990,950,912 bytes |
| Live initrd | 241,962,859 bytes |
| ISO kernel | 19,011,944 bytes |
| Unique regular-file logical bytes | 5,732,799,947 |
| Unique regular-file allocated bytes after extraction | 5,970,161,664 |
| Total extracted filesystem allocation, including directories | 6,031,958,016 |
| Additional hardlink paths | 24,274 |
| Exact duplicate bytes on separate inodes | 173,854,115 (logical, not ISO savings) |
| Flatpak unique regular-file bytes | 1,542,431,455 |
| Fonts | 164,887,326 logical bytes |
| Translations in `/usr/share/locale` | 311,466,717 logical bytes |

The image already uses LZMA level 6, 1 MiB clusters and EROFS fragments.
The baseline has no DNF downloaded-RPM or repository-metadata cache payload.
Its 15.4 MB AppStream cache supports offline app browsing and is retained.
Nix is installed alongside DNF/Flatpak; no populated Nix store was found to reclaim.
Flatpak's OSTree objects and deployments share hardlinks; summing each tree separately
would falsely report them as redundant copies. Do not delete those objects.

Largest RPM installed-size entries include Chromium (370,995,153 bytes), Mesa Vulkan
(182,331,338), LLVM (147,275,895), kernel-core (106,190,182), NVIDIA firmware
(105,915,244), WebKitGTK (100,778,009). Chromium is a backend for approved web-app
features; Zen remains the default browser. Driver/firmware and translation removal
would narrow functionality. Installed RPM sizes are not compressed ISO size and
must not be added to Flatpak sizes as if all were unique.

Raw evidence: `out/audit/baseline/{iso-layout.txt,payload.json,packages.tsv,directories.tsv}`.
`tools/audit-image.py` is a read-only inventory that counts unique inodes and hashes
same-sized files to identify exact duplicates. Extraction allocation is filesystem-
dependent and is distinct from the installed VM's disk usage.

## First local candidate and completed experiments

The combined candidate, built after incorporating the approved wallpaper work, is
`out/iso-candidate-2/Arctic-Linux-1.2-optimized-candidate-20261005-x86_64.iso`:
**2,321,909,760 bytes**, SHA-256
`f0635b87a05de6bc89b1aa9dbcd0a76db8503a691b28a18552e31a41d6b5a7ef`.
This is only **163,840 bytes (0.0071%) smaller** than v1.2 and **821,909,760 bytes
over the original 1.5 GB target** (the current firm ceiling still requires at least 321,909,761 bytes of reduction). It is not a meaningful size optimization or a qualified stable
release. Its source RPM commit is `244e4dddbe3d08b1446e30d5ac813da4a8c1422d`,
with `.preview.202610052010.git244e4dd` releases that sort below normal stable
releases. The EROFS payload is 1,990,148,096 bytes and the initrd remains
241,962,859 bytes. The build used the original LZMA 6 / 1 MiB settings.
Independent checksum and full EROFS content integrity verification pass;
installed-system qualification is ongoing. The combined prepared root inventory
has 5,734,138,869 unique regular-file logical bytes, 24,274 additional hardlink
paths, no inventory errors, and no added/removed RPM names. All six Flatpak refs
also match the original ISO's full 64-hex active commits, read directly from its
EROFS symlinks. This is an offline
prepared-root inventory, not an installed Btrfs measurement.

KIWI completed image creation, but the metadata wrapper initially failed because
the prepared description is `config.xml`, while its glob only looked for `*.kiwi`.
The completed ISO was recovered without rebuilding or changing its bytes; its
metadata records this recovery. The wrapper now reads the prepared XML explicitly,
requires one description, and retains metadata outside KIWI's temporary paths.
An actual execution in a disposable container verifies the override and metadata
against `config.xml`; Bash syntax and ShellCheck also pass. This changes build
tooling, not the installed system. The original candidate below is superseded.

The superseded first candidate was `out/iso-candidate/Arctic-Linux-1.2-optimized-candidate-x86_64.iso`:
**2,321,430,528 bytes**, SHA-256
`8d40511af887361da91610dfded1e86e86df6ed6d4218909893ce2a82d2b1c69`.
Independent checksum and userspace EROFS full-content integrity checks pass.
This is 643,072 bytes smaller than the release (0.0277%), and **821,430,528 bytes
above the requested target**. It is a test candidate, not a stable release. Its
EROFS is 1,990,307,840 bytes; the initrd is unchanged at 241,962,859 bytes.
The Arctic RPM build records source `85162e3b0cabb390d54d0e61307260f448570d87`.
There are no RPM names added/removed, and Flatpak refs and active commits match.
Fedora Chromium/Chromium-common and xxhash received normal repository updates;
therefore the small image difference cannot be attributed to the memory fix alone.
Its binary has been removed to make room for qualification; checksum and evidence remain.
The pending wallpaper PR was not in this first candidate. Its head
`7b86c31b5bffcce55b5e985a1d317ccd7c177913` has since been merged locally into
this branch for the next candidate; remote main and the owner branch remain untouched.
The owner merged this exact revision to main at
`cdf4960f567842e853b6b3503c542d739ff215f7`; that approved main merge is now
reconciled locally too. Its combined ISO still needs validation.

The actual Quickshell/Qt timer test passes, and a negative control removing the new
busy handler fails with the retained-catalog symptom. No running job is cancelled.
This verifies the fix's behavior, not a numerical RAM claim. Raw evidence is
`out/audit/catalog-eviction-{test,negative-control-result}.log`.

| Completed experiment | Measured result | Decision |
|---|---|---|
| Initrd main frame, same decoded contents, Zstd 19 | 241,656,683 → 236,808,843 bytes; 4,847,840 bytes saved. Encoder 113.21 s, peak RSS 432,604 KiB. Decoder window 4 → 8 MiB. | Retain baseline; small image gain adds memory cost. |
| EROFS Zstd 6 / 64 KiB, two workers, full baseline contents | 2,417,672,192 bytes vs 1,990,950,912-byte baseline payload (+426,721,280, +21.43%). Encoder 350.02 s, 691.10 user CPU s, peak RSS 1,655,344 KiB. Integrity/decode passes. | Retain smaller LZMA profile; the alternative moves farther from the size target. |
| EROFS LZMA 6 / 256 KiB, three workers, full baseline contents | 2,053,722,112 bytes (+62,771,200, +3.15%). Encoder 514.43 s / 1,468.39 user CPU s (overlapped an RPM build). Three full-decode median 55.96 s, peak RSS 25,216 KiB. | Not adopted: larger image and no readback speed gain. |
| Flatpak `ostree prune --no-prune --refs-only` | 15,217 objects, no unreachable objects | No deletion. |
| EROFS LZMA 6 / 1 MiB with global deduplication, one worker | At 465 s only 25,152,292 input bytes had been read; aborted incomplete. | Not adopted; no valid final size or speed measurement. |
| EROFS Zstd 19 / 64 KiB, one worker | Still incomplete after an observed 675 s; aborted. | Not adopted; compare a lower level to completion. |

Three complete userspace content-decode passes give LZMA median 54.24 s (range
52.74–59.89 s), vs Zstd median 7.10 s (7.00–9.67 s); median user CPU times are
50.94 s and 6.22 s. Peak process RSS is about 35,936 and 17,688 KiB, respectively.
These are host readback measurements on retained cache, not boot or application
startup benchmarks. No caches were dropped. Raw timings are
`out/audit/compression/{lzma6-baseline,zstd6-64k}-fsck-{1,2,3}.time`.
The completed smaller-cluster trial above did not improve this tradeoff.

Compression trials use the same extracted baseline file contents and hardlinks;
that audit extraction omits xattrs. They are isolated storage experiments, not
production boot results or substitutes for the exact candidate's security checks.
The original LZMA non-deduplication control was interrupted for workspace pressure;
its partial size is not a measurement. All aborts are recorded explicitly.

## Prioritized work and rollback

| Priority | Change / experiment | Why / expected scope | Rollback |
|---|---|---|---|
| P0 | Reproduce live boot and offline install; collect guest baseline | Establish failures before tuning; Fedora SELinux enforcing, identical VM resources | Original v1.2 ISO is preserved |
| P1 | Re-arm app-list eviction when a background install completes | Current one-shot timer can expire while busy and never evict until Get apps is reopened; preserve running jobs and five-minute grace | Revert the `AppsService.qml` handler |
| P1 | Default local ISO builds to requiring Zen | Current local `auto` mode silently drops Zen above 2 GiB; size must not reduce functionality | Explicit development `--zen no/auto` remains available |
| P1 | Compare EROFS deduplication and compressor/cluster choices on identical payload | Storage deduplication without changing file paths, inode semantics or update behavior; compare LZMA, Zstd and LZ4HC | Keep existing LZMA 6 / 1 MiB profile |
| P2 | Inspect initrd compression and contents, build caches and Flatpak unreachable objects | Retain drivers, boot recovery, installed refs and offline indexes; act only on measured disposable data | Baseline image / retained build root |
| P2 | Profile idle PSS, private allocations, CPU and app/window startup | Separate process allocations, MemAvailable and useful page cache; fix verified duplicated work or retention | Revert each independent change |
| P3 | Audit optional apps/fonts/locales/Nix closure | Identify costs; no removal or network-at-install change without a concrete measured proposal | No change unless separately authorized |

Safe implementation can proceed while the size target remains unproven. Duplicate
logical data alone is much smaller than the required compressed reduction; no
1.5 GB claim is justified by the current measurements.

## Reproducible VM protocol

For full read-only capability evidence after performance measurements, generate a
single data-CD probe with `python3 tools/performance/compose-probe.py OUTPUT.py`.
Add `--wallpaper` for the combined candidate to require the approved publisher.
Feed the generated script to `tools/test-install.sh --guest-check OUTPUT.py`.
The original baseline lacks the new publisher and is measured without that gate.

Use QEMU q35, 2 vCPUs, 4096 MiB, virtio GPU/disk/network, UEFI OVMF, UTC RTC,
identical offline profile, no internet forwarding, SELinux enforcing. Also test BIOS,
Safe graphics and UEFI Secure Boot. This cloud host exposes no `/dev/kvm`: TCG
software emulation can validate functionality, but timings are only emulated
relative measurements and must never be presented as physical gaming benchmarks.

`tools/test-install.sh --iso ISO --memory 4096 --smp 2
--guest-check tools/performance/guest.py --out RESULT_DIR` installs offline and
boots the resulting encrypted system. The probe records boot critical chain,
filesystem use, 30 CPU/meminfo samples after 60 seconds settling, six per-process PSS scans at five-sample intervals, per-process
PSS/private bytes, MemAvailable, Cached, SReclaimable, CPU busy percentage, shell
launch/IPC time and time to a newly mapped Kitty, Nautilus and Zen window.
The first launch after a fresh boot and subsequent warm launches are distinguished;
no cache dropping. The live `du -x /` value describes allocation reported by the
writable live overlay and must not be represented as total installed size. The
installed capability probe also records `btrfs filesystem usage -b /`, including
the filesystem containing its subvolumes, separately from the extracted image's
logical bytes. Observer memory is included and its PID is recorded. Its own CPU percentage on one core
is recorded separately. The preliminary full-scan sampler consumed about 26% of one
emulated core. The current sampler is `cpu-30-pss-6-v4-native-session`: it uses
Arctic's session-only Keep awake feature during the probe and restores it afterward.
This prevents the normal five-minute idle lock from interfering with slow emulated
GUI launches; it does not change lock settings or system security policy. Both
images use identical conditions, and these observations remain separate from the
earlier preliminary samples. Summary files report the actual count for every metric; no
PSS observations are duplicated to pretend there were 30 scans. Reuse the
same tools and observer for both builds. Startup closes only newly opened test windows.

The original v1.2 ISO completed a restricted-network encrypted installation with
SELinux enforcing: installer exit 0, 3,571 seconds under TCG. Zen, terminal,
fish, Nautilus and VLC were installed offline; Zed was deferred. Normal and rescue
initrds were generated. The wrapper failed after the successful installer because
its Bash source was edited while running; this is an instrumentation error, not
a clean harness pass. Harness sources are now frozen during active VM runs.

The first installed benchmark rendered the real desktop and collected six PSS
and 30 CPU observations, but stopped at an incorrectly ordered Quickshell IPC
command. Its measurements are archived as incomplete and do not establish an
optimization result. The current probe uses the shipped
helper's `quickshell ipc -p ... call` order and resolves `arctic-shell --path`;
baseline and candidate use identical regenerated probes. Three complete runs of
each, application startup and functional candidate gates remain pending.

A read-only diagnostic completed a default-argument encrypted graphical boot,
login and desktop collection (harness exit 0). It proved an instrumentation error:
the v3 probe omitted `XDG_DATA_DIRS` when the terminal added a directory, so all
four browser/MIME queries incorrectly reported Chromium. With the actual Mango
login environment, all four report `app.zen_browser.zen.desktop`; the installer's
default-apps and MIME files also select Zen. Browser preferences were not changed.
The real shell has `XDG_SESSION_ID=2`, which v3 also omitted. The v4 probe preserved
login paths/session identity but also inherited a portal-specific Qt backend,
which can differ from the primary shell. The v5 probe obtains only Xwayland's
post-exec display/authentication from children, preserves the login's own toolkit
backend (including its unset state), and uses `env -i`. Four regression tests
cover terminal path changes, missing login data, ambiguous IPC and portal backend
leakage. The shipped [Quickshell revision's display selection](https://raw.githubusercontent.com/quickshell-mirror/quickshell/dacfa9d/src/launch/command.cpp)
treats `wayland;xcb` differently from an unset backend; current upstream differs,
so the installed version is the relevant source. The installed candidate passed default encrypted graphical boot, native Zen
preference, all eight Settings pages and persistent Kitty/Nautilus/Zen windows.
Get apps and lock/PAM still report no running Quickshell instance when using the
shipped helper's configuration path. Preserving session identity did not resolve
that failure. A narrow runtime diagnostic confirms the main shell's live index and
`wayland,wayland-0` connection: explicit verified PID and any-display lookup
both succeed, while the v4 portal backend fails. Get apps chooser passed visual review; the lock stayed secure for at least
65 seconds and unlocked through real password/PAM input without AVC entries.
Normal v5 shipped-helper selection now passes: bar visibility and lock-state
queries succeed without any-display or PID selectors. Nix/update acceptance
remains in progress. No production IPC change is proposed. Exact-ISO UEFI Secure Boot passed with
enrolled OVMF keys, the guest's `SecureBoot enabled` report, enforcing SELinux,
complete collection markers and a visually reviewed Try desktop.

TCG boots with the harness's added `plymouth.use-simpledrm` argument intermittently
went black before passphrase typing; a text recovery boot and the subsequent
default-argument boot succeeded. This does not establish a physical boot defect
or performance improvement. Qualification now uses the image's default kernel
arguments explicitly and retains the failed-run diagnostics.

For comparative performance acceptance, repeat at least three boots after builds
finish, without competing compression/build jobs. Report sample counts, medians
and range/p95 where meaningful; retain raw serial logs and screenshots. Measurements
made during image builds are exploratory and cannot establish a regression gate.
An absent metric is **not measured**, never an invented zero or estimated result.

## Acceptance gates

1. New candidate has a distinct filename, verified byte size and SHA-256; never
   overwrite/retag the public v1.2 release. Missing 1.5 GB target is reported honestly.
2. Exact shipped package/features parity (except reviewed fixes), Zen exports and
   runtime refs retained; app files readable and metadata intact; EROFS integrity check.
3. Live Try desktop, Settings, lock/unlock, terminal, files, Zen, web-app backend,
   accessibility/reduced motion, audio/network menus and fallback desktop remain usable.
4. Offline install to a fresh disposable disk succeeds; reboot and login work;
   kernel/rescue initrds regenerated; encryption, Btrfs and snapshots available.
5. SELinux enforcing; no new relevant AVC denials or failed services. Firewall,
   keyring, firmware, networking, power-management and update capabilities retained.
6. Arctic repository public key/config retained and enabled; signed update path,
   DNF offline update/reboot, Flatpak and Nix GUI installation/rollback tested where
   authorized connectivity allows. Offline deferred optional requests are unchanged.
7. No repeated-boot crash or growth after app/open-close cycles. Investigate any
   >5% increase in median idle PSS/private bytes or >10% slower startup/IPC; reject
   changes whose regressions exceed normal repeat variation. MemAvailable/page cache
   are reported independently. Do not disable swap, flush caches or apply guessed sysctls.
8. Reconcile wallpaper work before final validation and rerun affected desktop/package
   gates on the exact combined commit. Hardware/gaming throughput remains a physical
   test requirement outside this VM; the VM tests only available options and software flows.

Rollback keeps the original ISO, base commit, raw manifests and independent commits.
For candidate regressions revert the relevant commit, rebuild to a new filename and
recheck gates. Installed-system recovery uses existing Snapper/DNF offline paths;
no tuning is performed on the user's offline laptop.

The first successful live measurement run used default NAT, which exposed outside
connectivity in this environment. It was stopped before installation and is preliminary
evidence only. The offline harness now explicitly uses QEMU `restrict=on` and
rejects any outside HTTP response before installing. [QEMU documents isolation](https://www.qemu.org/docs/master/system/invocation.html)
for this setting. `vm-offline` is the fresh restricted-network acceptance run.
Neither host nor laptop networking is changed.

For constrained builders, `tools/build-iso.sh --scratch DIR` places create-stage
intermediates and temporary files on dedicated storage while retaining the package
root in `--work`. This reduces workspace pressure, not the shipped ISO size.
Candidate metadata records the build-tool commit separately from the RPM source commit.

Separate GUI/PAM checks can be composed with `--desktop` and run on an installed
test disk with `tools/test-install.sh --stage boot --guest-check-interactive`.
They request real Settings pages and Get apps, record rendered-page screenshots,
confirm the compositor's secure session lock for at least 65 seconds, and type the
known test password through simulated keyboard input into the normal PAM flow.
Screenshots require visual review; an IPC success alone is not a UI acceptance pass.
These checks are separate from repeated performance measurements. Explicit
`--online-via-proxy` testing can now provision TLS trust/proxy settings in an
already-installed disposable guest; TLS verification stays enabled and this trust
never enters the ISO.

When software emulation makes timing inconclusive, qualify the functional/security
flows first and retain that limitation. `tools/performance/compose-nix-probe.py`
combines native session discovery with the Nix acceptance probe. Its explicit
online mode uses the VM test proxy and a daemon drop-in under `/run`, without
changing the shipped service policy or signature/sandbox settings. It exercises
the user-owned profile, graphical launchers, two-user isolation, removal/rollback,
then `arctic-update now --sync`. Staging must preserve the running package versions,
arm the normal offline flow and download all installed Arctic preview packages;
their RPM signatures are independently checked. After the offline transaction's
intermediate reboot, verify stable versions, the cleared trigger, updater status,
Nix/profile/settings persistence and the actual desktop. An installed preview fix
can be replaced by the current stable repository until an approved main merge;
post-update evidence must identify that source. Preserve a disposable VM snapshot
before updating if later paired measurements are feasible. These are planned gates,
not all completed checks. The first installed Nix run completed 27 checks and
failed one: cold `arctic-nix search hello` hit the shipped 180-second timeout under
TCG. Actual hello/Foot installation, live desktop entry/icon/launch from the Nix
store, session exports, two-user isolation, update/remove/rollback, signature and
sandbox/root-only trust checks, and relevant AVC checks passed. Zen's browser
chrome also passed visual review after a longer painting interval. The cold search
failure is retained; successful installation is not a cold-search/performance pass.
The combined probe correctly skipped signed staging after this failure. One warm
search diagnostic after successful installation also hit the unchanged 180-second
limit; a third search has not been queued. Reading both exact ISOs proves that
`/usr/bin/arctic-nix` and `shell/scripts/nixlib.py` are byte-identical, and both
have Nix/daemon/libraries version `2.34.8-1.fc44`. Thus this branch did not change
the search implementation. TLS-verified reads of the Nix cache and GitHub branch
API return 200, and real cached-package installation passes. Those observations
establish basic connectivity, not a complete search qualification. The Nix
[search manual](https://nix.dev/manual/nix/2.34/command-ref/new-cli/nix3-search)
describes searching evaluated package names/descriptions across package attributes.
Full evaluation under software emulation is a plausible cost, but a controlled
baseline comparison is needed before attributing the timeout to TCG or the proxy.
Neither the timeout nor trust policy has been weakened. Exact source hashes are
in `out/audit/candidate/nix-search-iso-source-parity.json`.

A separate updater probe reuses the signed-ready validator and runs normal
staging/reboot/persistence checks independently. It does not repeat completed
profile operations or fabricate full Nix acceptance. Its first staging attempt
correctly failed unarmed at Cisco's HTTP OpenH264 download: the isolated test
environment exported only the HTTPS proxy. The exact HTTP package route returns
200 with both protocol proxy variables. A targeted retry sets both only inside
the disposable guest, checks all downloaded RPM signatures independently, and
preserves TLS/signature validation. That retry completed normal staging and
cryptographic checks for all 19 downloaded RPMs, but the ready-state probe falsely
rejected RPM 6's lowercase `signature` text. The corrected observer requires a
valid signature for every RPM, accepts either capitalization, and rejects
digest-only unsigned/missing RPMs and bad or untrusted signatures; regression
tests and the real archived 19-RPM output pass. The failed observer record is
retained. A one-time `systemd.unit=graphical.target` diagnostic boot validates the
already-armed transaction and captures exact pre-update persistence state without
re-downloading or repeating Nix search. It is not a default-boot qualification.
The following transaction and persistence boots use default arguments. The
diagnostic instead found the updater's report idle/unarmed. Its readiness check
returned before directly checking the trigger; that report alone does not prove
the trigger had been deleted. Arctic RPM versions still matched the exact
candidate, and deferred first-boot DNF work had run and failed during startup.
Possible transaction invalidation is not proof that packages changed. This failed
diagnostic is retained. The next default boot, intended to run the corrected
staging probe, exited about 100 seconds after QEMU started, before login or the
probe. This may be the offline updater's intermediate reboot; a broken-pipe
desktop-observer failure alone cannot establish its outcome. A new default
postboot reconciliation reads actual package versions, updater state/history,
DNF logs, the real trigger and persistent profile/settings. It derives the prior
active generation number from the recorded successful rollback from 2 to 1;
the full prior store-target hash and numeric barSize were not recorded and are
not claimed equal. No synthetic pre-state file is written, the stale-state guard
is preserved, and no third candidate Nix search or repeated install is performed.
That reconciliation reached a terminal failure: all 17 installed Arctic/SDDM
packages still had the candidate's preview releases. Therefore the attempted
offline update is not qualified, despite an idle/unarmed report and an absent
trigger. Native Nix daemon/mount, active generation 1, hello/Foot, rescue initrd,
enforcing SELinux, no failed units and no AVCs passed after this attempt. The
additional modifier comparison had an observer type error: the built-in binding
API returned `SUPER+ALT` as a string. Its recorded F9 binding matches the request;
Right/Dodge requirements had already passed before the modifier assertion. This
control-flow inference and corrected string/list normalization are recorded in
`modifier-type-diagnosis.json`; the failed probe and record remain preserved.
Actual DNF offline logs and service journals are being collected read-only before
any further transaction. No successful update or post-update persistence claim
is substituted for these observations.
The intermediate update boot uses
`tools/performance/offline-update-boot.py` inside the Fedora QEMU tools container.
It accepts only disposable qcow2/OVMF files under the repo's `out/`, unlocks the
existing encrypted disk, retains restricted networking, and waits for the normal
transaction's reboot without attempting desktop interaction. QEMU exit alone is
an observation; the following native-session probe must establish real installed
versions, cleared offline state and profile/settings persistence. Python syntax
and the physical-device rejection guard pass; the actual transaction is pending.

The performance queue is sequential and waits for the update flow and the two
remaining live boot checks to finish. It retains update evidence and a stable VM
snapshot, restores the candidate's pre-online snapshot and matching OVMF state,
then interleaves three original/candidate boots with one frozen v5 observer,
2 vCPUs, 4 GiB and restricted guest networking. Before each measurement it gives
Kitty, Nautilus and Zen the same 45-second mapped-window preconditioning to
normalize user profiles and app caches. First measured launches therefore mean
new processes after that preconditioning, not first-ever or cold-profile launches.
No caches are dropped. Guest observer costs and host conditions are recorded;
one failed sample stops the queue for diagnosis. At the parent's request, the
single original-ISO Nix runtime control was moved ahead of BIOS/Safe graphics and
performance checks. It saved the baseline disk and OVMF state, ran once with an
empty Nix store, retained a diagnostic snapshot, and restored the baseline before
offline measurements. It failed the same unchanged 180-second inner search limit:
exit 1 after 182.316 seconds including wrapper/observer overhead. Its 87 samples
showed 124.81 seconds of Nix client CPU time, a maximum 420,909,056-byte client RSS,
and later waiting. A source-metadata diagnostic also timed out after 45 seconds.
TLS-verified Nix-cache and GitHub-branch endpoint checks returned 200. This
reproduces the symptom before this optimization branch in the TCG/proxy test
environment; it does not identify a sole cause or qualify full search. The exact
comparison is `out/audit/candidate/nix-search-baseline-comparison.json`. BIOS/Safe
graphics and performance follow the candidate's actual-log diagnosis without
overlapping VMs. Those remaining queues are not completed measurements.

The local CI draft makes only artifact-only `workflow_dispatch` builds (`release=false`)
use `.preview` RPM release suffixes. Normal signed stable updates can therefore
replace test packages even if their source commit predates the test branch.
Release builds retain the existing numeric version scheme. This workflow has not
been pushed or dispatched; remote branch publication still requires approval.
An Actions rebuild will produce different ISO bytes and requires its own checksum
and qualification evidence. `boot_test` does not include the separate Nix/update
acceptance flow, and its existing continue-on-error setting is not a stability gate.


### Offline update diagnosis and direct retry (2026-10-06 01:46 UTC)

The read-only actual service journal now identifies the rejected transaction:
`dnf5-offline-transaction.service` exited 1 because the system had been modified
since staging. `dnf5 offline status` confirms the stale RPM-database cookie; no
completed DNF transaction log exists. The disk is still mounted at the normal
`/@` subvolume and Snapper lists only the current root, so the observations do
not show a snapshot rollback. All failed installed-version checks remain archived.

The firstboot journal records `rpm --import` for the RPM Fusion key during an
intermediate graphical diagnostic boot after staging. A separate Fedora 44/RPM 6
tools-container control showed unchanged cookie after a read-only `rpm -qa`,
but changed cookies after each repeated import of an already trusted key. The
first control forgot to open the RPM database and returned null; it is retained
as inconclusive, not evidence. The corrected control is
`out/audit/candidate/rpm-key-import-cookie-control-opened.json`, with versions
recorded beside it. This establishes that the intervening key import can
invalidate staging; the complete timeline supports that explanation without
asserting that no other database writer existed. No stale-cookie check is bypassed.

One targeted normal restaging attempt is queued after BIOS/Safe graphics. It
checks the actual ready/armed/non-stale state again after all signature and
package queries, records genuine preferences/profile/package versions, then
boots directly into the default offline transaction and verifies the actual
installed versions and latest transaction log on the next default boot. There
is no intermediate graphical diagnostic boot. No firstboot service is removed
or disabled, no repository key/signature/TLS/SELinux policy is weakened, and no
additional candidate Nix search is run. Performance's waiting controller was
paused and replaced with an identical observer queue after this direct attempt;
no advancing VM was stopped. The update gate remains failed until real version
change and post-update persistence pass.


### BIOS and Safe graphics checks (2026-10-06 02:03 UTC)

BIOS Try passed the complete collector, enforcing SELinux, no recorded AVCs,
and visual review of the live bar/welcome/installer entry and working terminal.
UEFI Safe graphics also passed those boot checks; its actual kernel command line
contains `nomodeset`, and the fallback display rendered the live shell and
installer entry. Its journal additionally records `xdg-desktop-portal.service`
startup timeout. Current portal status was not collected, so this is an unresolved
session issue, not a fully qualified Safe graphics result. One identical original
ISO Safe graphics control is queued after the direct update cycle and before
paired measurements. No advancing VM or service is stopped; only the waiting
performance controller was replaced to preserve the sequential order.


### Direct staging and offline test-runtime correction (2026-10-06 02:24 UTC)

Fresh normal signed staging passed all nine recorded checks and its wrapper
(exit 0): current Arctic packages stayed unchanged, all 19 RPM signatures were
reported valid, and actual ready/armed/stored state remained non-stale after
every observer query. Genuine pre-state includes the exact own Nix profile
`/nix/store/1jhnhjcvbkhmrkg86m7s9q9qh1lzp1vq-profile`, Right/Dodge bar position
and hide mode, bar size 32, and modified F9 with SUPER+ALT. The firstboot process
had already exited and was awaiting its normal retry before staging began.

The separate offline QEMU process then failed before starting the guest:
`Virtio VGA not available`. The regular harness installs three QEMU display
module packages at startup, whereas the standalone helper used the base tools
image without that preparation. This is retained as a test-runtime failure, not
a guest transaction failure or an update pass. The helper now records startup
failures and checks for `virtio-vga` before opening a VM. A cached cloud-only
runtime contains the same QEMU 10.2.2 display/core versions as the regular
harness; actual device-list parity and its image ID are recorded in
`out/audit/candidate/qemu-offline-runtime-parity.json`. No ISO bytes or guest
packages changed. The already verified staged transaction resumes directly
with restricted networking; there is no new staging or intervening guest boot.
Its subsequent default boot must still prove actual installed versions and
exact pre-state persistence.

The original ISO Safe graphics control also passed boot/rendering/security
checks and reproduced the portal startup timeout. The current portal unit state
was not collected in either run, and no sole cause is claimed. This symptom is
therefore observed before the optimization branch in this environment; full
Safe session qualification remains open. The original control overlapped
preparation of the cloud test-runtime cache, but no other VM. No timing or
hardware-performance inference is drawn from it. The exact comparison is
`out/audit/candidate/safe-graphics-baseline-comparison.json`.


### Actual update reboot and history-selector diagnosis (2026-10-06 02:45 UTC)

The restricted armed offline guest exited 0 after 180.959 seconds. The following
default boot passed ten recorded checks, including the exact saved own Nix
profile generation, Right/Dodge/bar-size/modified-shortcut preferences, hello
and a persistent mapped Foot window, persistent Nix mount and daemon, rescue
initrd, failed-unit check and AVC check. Its update check failed at
`dnf5 offline log --number=-1`. The original failed check remains recorded.
The frozen function reached that lookup after asserting idle/unarmed/unstored
status, no update errors, trigger removal, changed stable-CDF versions and
retained names of all 17 Arctic packages. Those assertions therefore passed by
control flow, but their actual version rows were not emitted; a full update
acceptance pass is still withheld.

The [exact DNF 5.4.6.0 source](https://raw.githubusercontent.com/rpm-software-management/dnf5/5.4.6.0/dnf5/commands/offline/offline.cpp)
lists positive 1..N indexes and converts supplied numbers with an unsigned
conversion. Thus its negative `-1` selector fails regardless of available
entries. The canonical observer now selects the latest actually listed positive
index, fails on absent history or command failure, and records version/status
and history as separate checks so a late history failure cannot hide earlier
evidence. Three meaningful history regressions and four existing environment/
signature regressions pass. This changes only test tooling; active frozen probes
and candidate ISO bytes remain unchanged.

The updated disk and firmware snapshot are retained as
`candidate-after-update-attempt` / `OVMF_VARS.after-update-attempt.fd`. The
performance controller restored the pre-online candidate and is running six
interleaved original/candidate boots. Read-only inspection of the saved updated
state will follow that quiet sequence without restaging or key imports. No
performance improvement or full Nix/Safe/update qualification is claimed.

## Expanded download/build/runtime execution, 6 October

The user's clarification expands this task to download, build, software and OS performance, with all functionality, security and stability preserved. A minimal network installer is outside scope. The latest firm<2GB/preferred<1.6GB thresholds replace the earlier1.5GB target. Branch pushes, the combined draft PR and exact-head candidate Actions runs are now authorized; merge remains conditional on actual gates passing.

All six sequential 2-vCPU/4096-MiB TCG runs finished with harness exit 0 and complete observer records. Original and candidate checksums were reverified after the queue. The three-boot medians below retain all runs; the detailed ranges and paired differences are in `out/audit/candidate/performance-comparison.json/.csv/.md`, with graphical-target context in `performance-context.json`.

| Observation | Original | Candidate | Interpretation |
|---|---:|---:|---|
| Kernel+initrd+graphical target | 100.211 s | 101.487 s | No demonstrated boot gain |
| Process PSS | 1,001,745,408 B | 1,016,568,320 B | +1.48%; no RAM saving demonstrated |
| Private process allocation | 831,877,120 B | 845,547,520 B | +1.64% |
| Idle sampled CPU | 1.970% | 1.485% | Ranges overlap; baseline boot 2 had 6.292%; no causal gain claim |
| Fish launch | 0.333 s | 0.342 s | Ranges overlap |
| Shell IPC command round trip | 0.475 s | 0.509 s | Ranges overlap |
| Kitty first mapped window after preconditioning | 2.630 s | 3.183 s | +21.03%; investigate gate OPEN |
| Kitty subsequent mapped windows | 3.243 s | 3.685 s | +13.64%; investigate gate OPEN |
| Nautilus first mapped window | 16.947 s | 17.902 s | Ranges overlap |
| Zen first mapped window | 29.794 s | 28.824 s | Ranges overlap |

Kitty's three-boot ranges do not overlap. Its RPM version and fish's RPM version are identical in both images. The full comparison includes approved clock/wallpaper work, Mango rebuilds and normal Fedora updates, so it cannot isolate the catalog fix as the cause. Read-only inspection of both inactive benchmark disks confirms the same shell settings (`{"frame": true}`) and no personal Arctic Nix-profile link in the measured state; later update-acceptance customizations were on a different saved state. The observer includes its own allocation/CPU cost, uses identical 45-second mapped-window preconditioning, and measures mapped windows rather than full paint/readiness. TCG timings cannot establish physical or gaming performance. This candidate does not pass the overall performance acceptance gate.

The saved `candidate-after-update-attempt` snapshot was converted without altering the source and inspected through read-only libguestfs/LUKS/Btrfs mounts, without another installed-OS boot or key import. All 17 Arctic package names are retained and their versions changed from preview to the signed stable CDF build. Actual positive DNF history index 1 selects boot `5b2deaecd84b4b62bb357c7c4218977c`, whose journal records `Transaction complete! Cleaning up and rebooting...`. The offline trigger is absent and the exact personal profile target is retained. These corrected version/history checks supplement the ten already passed default postboot checks; the original wrapper exit 1 and negative-index failure remain archived. The cached on-disk status file still says ready until the next privileged staging check, as documented by the updater; the default postboot status API asserted idle/unarmed/unstored before the late history-selector failure. A fresh persisted `installed_at` is not claimed. Full Nix-search and Safe-graphics portal qualification remain open.

The actual updated `AppsService.qml` hashes to `32dad68507ae29e2e6eec74251cbeb609fae206c57b9f53573da5bd9bad079b8`, matching current public CDF rather than the candidate's `3d5c34c6a79fd5c24c1f733792ef56816089f38678a187337a13f2964c92116e`. Normal stable updates therefore replace this unpublished optimization. Persistence requires an approved merge and signed optimized-package publication; raising preview versions or disabling updates is not an acceptable workaround.

The download/build audit found repeated work outside the shipped image: the RPM container had no persistent DNF package cache, and the spec placed GOCACHE inside each disposable build tree. KIWI's installed DNF5 implementation already uses `system_cachedir` and `keepcache=1`; its `/var/cache/kiwi` cache was only persistent when callers supplied `--cache`, and the ISO workflow did not. This is a missing persistent mount/default, not a KIWI DNF option bug. HTTP and HTTPS build proxy choices also need independent propagation; adding an explicit caller's HTTP proxy avoids the observed HTTP-mirror failure without changing user networking or TLS verification.

The local implementation now provides build-only DNF/Go caches with `--no-cache` rollback. Go reuse is fenced by immutable builder-image identity and native RPM inventory because Go does not automatically detect C-library changes. Go still validates sources, compiler and flags. RPM assembly, native-library dependency resolution, `%check`, payload conflict checks and signing behavior continue to execute. Cache misses and metadata expiry use normal signed repository downloads; no `--cacheonly`, signature bypass or stale metadata policy is introduced. Dedicated cache directories are never installed into the ISO. One full cold/warm pair completed: 253.598 → 229.746 seconds (9.405% lower elapsed time), with all checks passing and identical emitted payload digests. DNF reported 27 + 219 MiB of inbound RPM payload downloads on cold versus 0 B on warm; 227 cached package records were reused. The compiler/native inventory key was identical. Only docs/OPTIMIZATION.md changed between source archives; compiled inputs and emitted payloads were identical. The dedicated cache allocated 583,417,856 bytes. This is one pair, without a confidence interval, and source tarballs were already cached in both. CI restoration/save is now implemented with per-branch/tag cache isolation; its archive/upload overhead and end-to-end gain remain unmeasured. The local KIWI repository cache is invalidated each prepare to prevent an older cached preview RPM from replacing the current build.

The latest size instruction supersedes the previous target: **strictly fewer than 2,000,000,000 decimal bytes**, preferably **strictly fewer than 1,600,000,000 bytes**. The maximum accepted integer sizes are therefore 1,999,999,999 and 1,599,999,999 bytes. The current candidate needs at least 321,909,761 bytes of further reduction for the firm ceiling. Neither threshold is achieved. Battery-indicator repair is now included. The user explicitly authorized publishing the combined branch/draft PR, candidate Actions artifacts and a merge after all actual checks pass; existing v1.2.0 assets remain immutable and the combined merge remains blocked by unresolved gates.


## Battery fix and current independent review

The generic battery artwork used a fixed 9-unit fill in a 12.4-unit interior,
about 72.6%, even when the real charge was 100%. Charging had no live level. The
new optional Icon battery percentage preserves the outline and bolt, fills the
usable interior at 100%, keeps a charge-limited 80% at 80%, and displays unknown
readings explicitly. Quickshell 0.2.1 exposes charge as a fraction; health remains
in its original 0..100 units. UPower's weighted display-device aggregate is
preserved. No charge-limit, hardware, power, network or security policy changes
are involved.

All three exact-source DPI runs (1×/1.5×/2×) pass 14 private-UPower mapping/state
cases and 73 render cases each: 219 rendered cases total, including three
negative controls that reproduce the old partial fill. Actual horizontal/vertical
widgets, charging contrast, accessible text, near-full rounding, charge limits,
unknown values, hot removal/reinsertion and multiple-battery aggregation are
covered. Root independently reviewed the battery source, fixture, matching
source hashes and rendered evidence. These are fixture tests, not physical
laptop or whole-ISO qualification. Raw results and preserved observer failures
are in `out/audit/battery/`; CI now runs the same three scales.

Independent pipeline review found and corrected a mutable builder-tag race.
Both builders now execute the immutable image ID they recorded, with Docker
and Podman forms covered by real host-orchestration tests. The review also
identified a preexisting KIWI gap: remote Fedora RPM signature checking was
disabled in the previous image build. New descriptions explicitly enable
`package_gpgcheck` for Fedora and updates, with their existing distribution keys;
the local unsigned build repository remains the scoped exception. Exact KIWI
11.0.2 source confirms key import before bootstrap and system installs and the
attribute-to-DNF `gpgcheck=1` path. Actual new-image signature validation remains
a gate; the earlier candidate is not retroactively claimed to have had those
checks. See the [KIWI repository schema](https://osinside.github.io/kiwi/image_description/elements.html#repository).

The Actions candidate workflow has an explicit paired KVM acceptance option:
one immutable test-only QEMU/firmware toolchain, two fresh restricted-network encrypted installs, followed by three interleaved
boots of each image at 2 vCPUs/4096 MiB. It verifies the original v1.2 bytes and
SHA256, freezes one observer, uses identical 45-second mapped-app preparation,
retains terminal failures, verifies candidate catalog/RPM source, and reports
all per-boot values and ranges. Gates reject incomplete/inconsistent evidence,
more than 5% median PSS/private-RAM growth or more than 10% median boot/app/CLI
regression. Passing means no measured regression under this protocol, not a
substantial speedup, cold-app gain or physical gaming result. The existing TCG
Kitty regression remains open until actual new evidence resolves it.

Release requests now always run boot checks; opting out is limited to artifact
builds. Oversized artifacts remain downloadable for review, but the strict
2,000,000,000-byte gate fails the job before publication. VM disk/data images
are excluded from screenshot/performance artifacts. No stable ISO asset has
been replaced, and combined merge remains pending all gates.


The completed full-root SquashFS trial (XZ, 1 MiB blocks, x86 BCJ, three workers,
default duplicate-file elimination) produced **2,000,814,080 bytes**, compared
with the original EROFS root's **1,990,950,912 bytes**: **9,863,168 bytes larger**.
Encoder elapsed time was **697.76 s**, user CPU **2,344.22 s**, system CPU **5.51 s**,
peak RSS **808,444 KiB**. Image SHA256 is
`790233f13d15b927a6de914866805c550c2f34e0185ed1470f101b068efe11be`.
The same original root's file contents and 24,274 additional hardlinks were used.
The first ACL-preserving extraction failed because the cloud tmpfs does not
support a POSIX default ACL; that failure is preserved. A fresh normalized
extraction without xattrs completed successfully. This is a size experiment,
not a production image/security qualification. No files were deleted from the
source and the trial is not adopted. Replacing only the original root extent
would project 2,331,936,768 bytes; that is a projection, not an ISO artifact.
Raw commands, tool help, failure logs and timing are in
`out/audit/candidate/squashfs-trial/`. Existing EROFS LZMA 6 / 1 MiB remains the
smallest completed full-feature root profile tested. These trials do not prove
a mathematical lower bound; they have not established a feature-preserving way
to meet the firm 2 GB ceiling.

The KVM observer now samples mapping with 10 ms sleeps and records each
observation's lower/upper timing bounds including IPC cost. Its root-only
`du -x` allocation is labeled explicitly; separate persistent mounted-tree
allocations and Btrfs physical usage are recorded separately. Exact 5%/10%
threshold controls pass, just-over controls fail, and invalid/NaN measurements
fail closed. Timeout/interruption records are preserved; the controller manages
process groups and removes only uniquely named task containers before archiving.
Every VM stage verifies the same QEMU/package/OVMF/SeaBIOS inventory. Actual
KVM/CI results remain pending, and none of these tooling changes clear the
existing runtime regression by themselves.


A cache-corruption control changed one byte in a private copied Fedora RPM.
RPM reported bad payload digests and DNF refused that target with cache-only
mode. The original RPM validated. A normal DNF reinstall then re-downloaded
94.4 KiB, verified it and restored the exact original SHA256. The first
cache-only positive attempt lacked other dependencies in this minimal helper;
that observer limitation is preserved, and the subsequent normal dependency
and poisoned-cache recovery runs passed. The production cache was unchanged.
Cache-only is used solely by this control, never by the production builders.
Evidence: `out/audit/candidate/cache-corruption-control/`.

## Nix acceptance network correction (2026-10-06)

Artifact-only ISO run `37419332624` finished with failed Nix and paired KVM
acceptance; the required size and publication steps were skipped. The supplied
Nix log shows the offline install completed with exit 0 after 1,110 seconds,
followed by a successful encrypted boot/login. Both QEMU phases used
`user,id=net0,restrict=on`. Installed Nix fetches then failed DNS resolution for
`api.github.com`; repository/mirror DNS and later profile checks failed too.
Live checks and installed SELinux, Zen, daemon/store, customization, session-path,
trust-configuration and AVC checks passed. The installed check exited 1 and the
guest powered off normally. These results identify an acceptance harness
network-phase error; Nix fetch/update functionality still requires a successful
rerun. The separate paired KVM failure cause and measurements remain unavailable.

`tools/test-install.sh --boot-network online` now explicitly enables user-mode
NAT for installed boots while preserving the live install's restricted network
and offline reachability assertion. The default remains restricted in both
phases, including paired performance tests. The existing explicit online proxy
mode retains its behavior. The Nix workflow opts in on both installed boots;
the guest checks DNS and verified HTTPS with bounded timeouts before fetching.
A failed preflight exits acceptance with failure and marks dependent operations
unrun. Security, signatures, isolation and functional assertions remain required.
This changes the disposable test VM; it does not configure the user's system.

Local tools regression suite: 69 tests run, one skipped (`python3-rpm` absent).
Coverage executes the actual shell harness and generated QEMU network arguments
for default isolation, boot-only NAT, legacy proxy and invalid input, plus DNS,
TLS/HTTP failure and proxy preflight controls. Bash syntax, workflow YAML and
whitespace checks pass. Independent review and exact-head CI/VM acceptance are
required before this correction qualifies the candidate. Relay evidence and
source-message references are retained in `out/audit/nix-network-diagnosis.json`;
the original failed run metadata and access-denial records are preserved.
