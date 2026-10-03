# Release reliability

A successful ISO build or screenshot capture is **not** a release acceptance test. Use this
checklist for every candidate; keep the exact ISO SHA-256, package versions and evidence.
Do not publish based solely on the green source-code CI jobs.

## Existing coverage and the new VM lane

`ci.yml` already runs Go, Python, Node, RPM/repository, real dnf5 offline-transaction,
WebKit/Chromium, Settings and shell tests. `iso.yml` already builds the ISO and captures
UEFI/BIOS screenshots with `tools/test-iso.sh`; that diagnostic step uses
`continue-on-error`. This change leaves the release/publishing workflow alone.

The **Release reliability** workflow is a separate, manually dispatched validation lane for
an **existing** release or RC tag. It does not publish, merge, or build a replacement ISO.
It extends `tools/test-install.sh` and its existing QMP driver, rather than creating another
installer or VM implementation. Run it from the branch containing these changes until merged:

```sh
gh workflow run release-reliability.yml --ref codex/release-reliability \
  -f candidate=v1.1.0 -f version=1.1 -f previous=v1.0.0 -f previous_version=1.0
```

GitHub may require the workflow to exist on the default branch before dispatch is available.
Before that, use the local commands below. A tag must have one ISO plus its checksum, or
contiguous `.part00`, `.part01`, … files. The downloader rejects gaps and checksum mismatches,
records provenance, and never interprets release-asset names as shell commands.

Each UEFI/BIOS matrix job uses KVM, 2 vCPUs, 4 GiB guest RAM and a new 40 GiB sparse qcow2
disk. Budget at least 25 GiB **free** host storage, a working Docker/Podman engine, HTTPS
access to Fedora, Arctic and the app repositories, and 180 minutes per firmware. Matrix jobs
run sequentially. Candidate and previous installations have outer 75/60-minute limits;
upgrade/reboot has 35 minutes. KVM absence fails preflight; it is not reported as an OS boot
failure. Local TCG is possible with the original harness, but needs much longer and is not
part of this bounded CI lane. No host block devices are passed into QEMU.

The automated sequence is:

1. Download the exact tag's ISO and verify its SHA-256.
2. Boot **Try Arctic Linux**, reach the real Mango user session, assert Arctic version and
   live root, fetch HTTPS with certificate validation from inside the guest (DNS + routing +
   TLS + response), and open terminal, Nautilus, Zen, Settings and VLC windows.
3. Use the ISO's actual unattended installer, as a systemd service, on a newly created blank
   disk with the existing encrypted CI profile. A nonzero or missing installer result fails.
4. Boot that disk with the live ISO detached; unlock LUKS, log in, and repeat identity,
   network and application probes. Wait up to ten minutes for deferred first-boot work;
   Zed is required here, but explicitly **unrun** in live mode because it is downloaded at
   installation time. Missing installed applications fail, rather than silently falling back.
5. If a previous tag was supplied, install that ISO into a **different fresh disk**, prove its
   source version, and test the documented same-Fedora update path described below.

GUI probes require a *new*, matching Mango client that stays mapped for five seconds.
Executable presence or a successful detached launcher exit does not pass. Window titles/app
IDs, probe results, application stderr, serial logs, QEMU logs and screenshots are retained.
This is a launch smoke test, not proof that website content, video, microphone or calls work.
The terminal used to run probes also demonstrates real desktop input. The full graphical
installer wizard is a manual test; automation exercises its shared installer engine.

The workflow uploads evidence even on failure (14 days; copy it elsewhere before expiry).
`results.json` and the job summary distinguish **passed**, **failed**, and **unrun**. Missing,
malformed or duplicate guest records fail acceptance. A completed diagnostic collection is
not a passed boot; the harness must also report successful reboot/login. Review screenshots
and all job outcomes, including preflight. A timeout/cancel may leave only partial evidence.

## Reproduce locally

Run from the repository root, as your normal host user. Use a new output directory: the
existing harness deliberately clears its output on a fresh install. Never put valuable data
there. These commands only target qcow2 files; **do not run `guest.py` on a real computer**.

```sh
python3 tools/reliability/fetch-iso.py v1.1.0 out/reliability/candidate-iso
tools/test-install.sh --iso out/reliability/candidate-iso/Arctic-Linux-1.1-x86_64.iso \
  --firmware uefi --kvm --memory 4096 --smp 2 --boot-append '' \
  --reliability-version 1.1 --out "$PWD/out/reliability/candidate"
python3 tools/reliability/report.py out/reliability/candidate
```

Repeat with `--firmware bios` and a different output directory. The profile expects kitty,
Nautilus, Zen, Zed and VLC; a custom app profile needs corresponding probe expectations.
There are no installer binary overrides, fixtures, debug-shell fallbacks or proxy bypasses
in the release lane. External HTTPS failure is reported as a failed network probe; inspect
its log to distinguish repository/service outage from a guest defect.

## Supported upgrade: 1.0 → 1.1 on Fedora 44

The [1.1 release notes](releases/v1.1.0.md) explicitly support
`sudo dnf --refresh upgrade`, then `arctic-shell --restart`; rebooting also restarts the shell.
[Updates](wiki/Updates.md) documents the normal staged/offline update UI and signed stable
repository. This is a package update, **not** installation of a newer ISO over the old root.
[Release notes](wiki/Release-Notes.md#known-limitations) say Fedora major-version upgrades
are not covered. Legacy 0.1 repository migration is separate and not part of this lane.

Install and validate the previous ISO in a separate output directory, then keep that disk for the upgrade:

```sh
python3 tools/reliability/fetch-iso.py v1.0.0 out/reliability/previous-iso
tools/test-install.sh --iso out/reliability/previous-iso/Arctic-Linux-1.0-x86_64.iso \
  --firmware uefi --kvm --boot-append '' --reliability-version 1.0 \
  --out "$PWD/out/reliability/previous"
python3 tools/reliability/report.py out/reliability/previous
cp out/reliability/previous/serial-boot.log out/reliability/previous/serial-before-upgrade.log
tools/test-install.sh --stage boot --firmware uefi --kvm --boot-append '' \
  --reliability-version 1.0 --upgrade-to 1.1 --out "$PWD/out/reliability/previous"
python3 tools/reliability/report.py out/reliability/previous --upgrade
```

This boots the previous disk, proves the source version, writes a user-owned sentinel,
records `arctic-release` NEVRA, executes `dnf -y --refresh upgrade` with the guest's configured
repositories and normal signature checks, powers off cleanly, and boots the disk again.
Acceptance requires a different boot ID, exact target `VERSION_ID`, changed `arctic-release`
NEVRA, preserved user data and all installed smoke probes. Transaction and reboot evidence
are separate. A no-op upgrade, stale source, failed download or target version mismatch fails.
Use a fresh previous installation for every retry; the guest's upgrade state is intentionally
persistent so retrying a completed disk cannot impersonate a clean previous-release upgrade.

**Limit:** stable repositories move. This tests the previous ISO against the **currently
served signed packages**, not an immutable historical snapshot. For an RC whose packages
are not yet available in those repositories, leave `previous` empty and record upgrade as
**unrun: candidate packages unavailable**. Do not substitute stable packages and claim RC
upgrade coverage, disable signatures, or invent a Fedora `--releasever` migration. The
workflow never changes repository channels. Offline-update UI/reboot behavior is still a
manual release check; existing CI covers dnf5 transaction mechanics separately.

## Real computer / volunteer RC checklist (manual)

Do not automatically contact testers. Give willing volunteers this checklist and the exact
candidate tag/checksum, known issues and previous stable fallback. Use a spare computer or
explicitly designated blank drive; back up data and verify a restore before any installation.
Disconnect other drives where possible. Identify the intended USB and install disk by model,
serial and capacity in the UI; do not copy a guessed `/dev/sdX` command from another machine.

- [ ] Record candidate tag, SHA-256, download source, date, firmware mode, Secure Boot state,
  CPU/GPU, RAM, disk model, network adapter, and peripherals. Verify the checksum before
  writing the USB with Fedora Media Writer. Preserve the previous known-good USB separately.
- [ ] Boot the USB in the intended UEFI/BIOS mode. Select **Try Arctic Linux**. Record time to
  desktop and a screenshot. Check keyboard/layout, touchpad/mouse, display scaling, external
  display, sound, brightness, Wi-Fi/Ethernet reconnect, DNS and an HTTPS page in Zen.
- [ ] Open Settings, terminal, files and VLC; open/save a test file, play known local media,
  test audio output/input. Exercise light/dark theme and web apps; test calling only with the
  tester's own consenting account/contact. Record service/account limitations separately.
- [ ] Use the **graphical installer**, review the disk summary, and install only to the
  designated disposable drive. Exercise encryption and account creation. Capture errors and
  `/var/log/arctic-install/` logs. Never publish passwords, pairing codes or personal logs.
- [ ] Shut down, remove the USB, boot the installed disk, unlock, log in, and repeat network
  and app tests including Zed after first-boot downloads finish. Check `systemctl --failed`,
  `journalctl -b -p warning`, `arctic-update status --json`, and pending first-boot work.
- [ ] Restart a second time; check file persistence. Test suspend/resume, lid behavior,
  battery, Bluetooth and hardware-specific drivers where applicable. Label unavailable
  hardware **unrun**, never passed.
- [ ] On a separately backed-up disposable **previous-release** install, save a file and
  record package versions. Exercise the normal **Restart to update** UI, reboot, confirm
  target version and preserved file, and rerun app/network checks. Record exact packages
  and repository channel; use the supported path above. Fedora major upgrade: unsupported.
- [ ] Submit a report voluntarily with the template below. Maintainers review all failures
  and missing required hardware coverage before release. No automated tester outreach occurs.

```text
Candidate/tag + ISO SHA-256:
Previous tag (upgrade only), source/target VERSION_ID, arctic-release NEVRA:
Hardware + firmware/Secure Boot + network:
Stage: live / graphical install / reboot / network / apps / upgrade / suspend
Result: PASSED / FAILED / UNRUN (reason required)
Steps, expected result, actual result, reproducibility:
Evidence: screenshot/log path or artifact URL, workflow run/commit:
Known limitation or blocker, owner, retest result:
```

## Previous ISO fallback

For 1.1, retain [v1.0.0](https://github.com/yuvalkolodkingal/Arctic-Linux/releases/tag/v1.0.0)
(`Arctic-Linux-1.0-x86_64.iso` and its `.sha256`). Download from that exact tag, verify its
checksum, and keep a separately labelled bootable USB. If the candidate cannot boot/install,
stop the test and use the previous USB to recover files or reinstall the disposable test
machine. Reinstalling is destructive and needs a tested backup; booting an old ISO does
**not** downgrade an installed system or roll back user data. Stable repositories may update
an old installation to newer packages again. For installed-system recovery, consult the
[documented snapshot workflow](wiki/Updates.md#snapshots); do not promise automatic rollback.

## Validation of this implementation

Focused failure-path tests are in `tools/tests/test_release_reliability.py`, discovered by
the existing `ci.yml` tools test step. Run `python3 -m unittest discover -s tools/tests -v`
and `bash -n tools/test-install.sh`. They validate evidence parsing, fail-closed behavior,
checksum rejection, and generated guest scripts without pretending to execute a VM.
The PR records actual local results and resource limits. Until a KVM run and human checklist
are attached, this change is an **unvalidated VM harness extension**, not release certification.
