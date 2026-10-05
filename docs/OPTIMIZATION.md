# Arctic Linux optimization candidate

Work is local on `codex/optimize-preserve-functionality`, based on main
`f1e3c518ae6a1d8d0fd85dcf117baa8341701703` (includes PR 18's lock-clock fix).
No main merge, tags, package repository publication, or public release is authorized.
The approved wallpaper merge on main `cdf4960f567842e853b6b3503c542d739ff215f7`
has been reconciled locally and is included in the combined candidate.

The target is **1,500,000,000 bytes**, decimal 1.5 GB, approximately 1.397 GiB.
GB means 1,000,000,000 bytes; GiB means 1,073,741,824 bytes. This is a target,
not permission to remove functionality or move offline features to network downloads.
Priority order: stability and feature parity, responsive desktop and low memory,
then image size. "As fast as possible" and "as small as possible" have competing
compression costs; measurements decide the compromise.

## Baseline evidence

The public v1.2.0 ISO has been downloaded and independently verified:

| Measurement | Baseline |
|---|---:|
| ISO bytes | 2,322,073,600 |
| SHA-256 | `054db5c43cae47fb60f8f43efc8e052b569aa1b14e8f15adcb15cdc48265182f` |
| Reduction needed for target | 822,073,600 bytes (35.40%) |
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
over the target**. It is not a meaningful size optimization or a qualified stable
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

The first candidate is `out/iso-candidate/Arctic-Linux-1.2-optimized-candidate-x86_64.iso`:
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
The pending wallpaper PR is not yet in this first candidate. Its head
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
emulated core, so future comparison uses the same `cpu-30-pss-6-v1` sampler on
both installed systems. The current sampler is `cpu-30-pss-6-v2-awake`: it uses
Arctic's session-only Keep awake feature during the probe and restores it afterward.
This prevents the normal five-minute idle lock from interfering with slow emulated
GUI launches; it does not change lock settings or system security policy. Both
images use identical conditions, and these observations remain separate from the
earlier preliminary samples. Summary files report the actual count for every metric; no
PSS observations are duplicated to pretend there were 30 scans. Reuse the
same tools and observer for both builds. Startup closes only newly opened test windows.

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
These checks run after the repeated performance measurements. Explicit
`--online-via-proxy` testing can now provision TLS trust/proxy settings in an
already-installed disposable guest; TLS verification stays enabled and this trust
never enters the ISO.

The local CI draft makes only artifact-only `workflow_dispatch` builds (`release=false`)
use `.preview` RPM release suffixes. Normal signed stable updates can therefore
replace test packages even if their source commit predates the test branch.
Release builds retain the existing numeric version scheme. This workflow has not
been pushed or dispatched; remote branch publication still requires approval.
An Actions rebuild will produce different ISO bytes and requires its own checksum
and qualification evidence. `boot_test` does not include the separate Nix/update
acceptance flow, and its existing continue-on-error setting is not a stability gate.
