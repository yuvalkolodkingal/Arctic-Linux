# Arctic Linux optimization candidate

Work is local on `codex/optimize-preserve-functionality`, based on main
`f1e3c518ae6a1d8d0fd85dcf117baa8341701703` (includes PR 18's lock-clock fix).
No main merge, tags, package repository publication, or public release is authorized.
The concurrent wallpaper work must be reconciled into the candidate before final acceptance.

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

Use QEMU q35, 2 vCPUs, 4096 MiB, virtio GPU/disk/network, UEFI OVMF, UTC RTC,
identical offline profile, no internet forwarding, SELinux enforcing. Also test BIOS,
Safe graphics and UEFI Secure Boot. This cloud host exposes no `/dev/kvm`: TCG
software emulation can validate functionality, but timings are only emulated
relative measurements and must never be presented as physical gaming benchmarks.

`tools/test-install.sh --iso ISO --memory 4096 --smp 2
--guest-check tools/performance/guest.py --out RESULT_DIR` installs offline and
boots the resulting encrypted system. The probe records boot critical chain,
filesystem use, 30 one-second idle samples after 60 seconds settling, per-process
PSS/private bytes, MemAvailable, Cached, SReclaimable, CPU busy percentage, shell
launch/IPC time and time to a newly mapped Kitty, Nautilus and Zen window.
The first launch after a fresh boot and subsequent warm launches are distinguished;
no cache dropping. Observer memory is included and its PID is recorded. Reuse the
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
