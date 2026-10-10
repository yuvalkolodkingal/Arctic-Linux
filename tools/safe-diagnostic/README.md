# Exact-image Safe rendering diagnostic

This lane observes the original successful A2 ISO from run38032256030. It does
not build an ISO, change the installed product, qualify an image, admit a
performance observer, or authorize release. The four acceptance/profile flags
remain false. `ready` only enables this narrowly bound diagnostic after review.

The dedicated branch is `codex/safe-diagnostic-v6-20261010`. Publication of the
preparation does not start the workflow: its activation marker is absent.
After source review, the only accepted activation is a first-attempt hosted
push whose sole child change adds `.github/safe-diagnostic-v6-20261010.activate`
with the reviewed parent SHA plus one newline. The guard validates the live
branch ref, sole ancestry, preparation-only path scope,14 execution hashes,
eight original source blob records and ten exact image/producer pins. Root
owns remote publication and activation.

The unchanged, pinned native image fetcher verifies the successful first-attempt
producer, original archive and ISO hashes, original producer receipt, strict
size and startup gates. This does not make the ISO visually acceptable.

The VM uses real KVM, q35, virtio VGA,4vCPU,4096MiB, original UEFI firmware and
the actual Safe GRUB entry (`arctic.mode=try nomodeset`), without extra kernel or
renderer overrides. A blank64GiB disk matches the original boot fixture. An
additional root-owned read-only test CD and duplex virtio evidence port are
explicit fixture differences. The host container has no network; the guest
uses the original restricted user networking and has no audio/input devices
added for dictation. SELinux must already be Enforcing before and after.

After menu selection, the host records original QMP PNGs at35,80 and125seconds.
No VT switch, terminal launch or Wayland readback occurs before those captures.
These are the only unperturbed baseline frames. The later authenticated VT6
login, read-only CD setup and actual Wayland VT restoration are interventions.

Three later samples are ordered `restored-desktop`, `terminal-initial`, and
`terminal-repaint`. Each brackets one real Wayland screencopy with QMP-before
and QMP-after. Readback can trigger repaint: both QMP frames are retained even
if readback changes the defect. Host and guest monotonic clocks are separate;
the authenticated ordered protocol binds the bracket rather than comparing
unrelated absolute clocks. Each bracket has a25second maximum.

Every sample retains the exact wl_shm stride×height buffer (`.shm.rgb`), a
descriptor with format/stride/flags and actual output geometry/scale/transform,
and original packed P6 RGB bytes (`.rgb`). Packed RGB is a derived channel and
orientation conversion, not the original stride buffer. The host independently
reconstructs the RGB from the original raw buffer, verifies byte equality and
produces a clearly named lossless derived PNG, without resizing. Original QMP
PNG bytes are never converted or replaced. Only the synthetic Foot fixture
created by this invocation is observed and cleaned up using an acquired pidfd
and child process ancestry; existing apps and Mango are preserved.

Whitelisted actual Mango renderer variables, mapped renderer library hashes,
DRM FDs, existing kernel framebuffer/DRM attributes, selected output metadata
and bounded renderer journal lines are recorded. No full environment, audio,
dictation text, shell history or credentials are collected. No debugfs is
mounted. Missing renderer/allocator facts remain unknown. All text is screened
before guest transport and again before upload, preserving original bytes or
rejecting the upload; no secret-bearing excerpts are printed.

Decoded original guest members are retained byte-exact, with independent size,
hash, chunk order and bounded decompression checks. The encoded wire is hashed
and counted rather than duplicated. Bounds are32MiB/member,128MiB aggregate,
40 exported files,200MiB wire,20minute host preparation/VM step,10minute VM
driver and40minute workflow. Containers have unique acquired IDs/labels and
are removed only after identity validation. Owned QEMU processes and disposable
disk/firmware state are cleaned up on success, failure or deadline.

`python3 -B -m unittest discover -s tools/safe-diagnostic -p 'test_*.py' -v`
runs source-only guard, transport, privacy and raw-conversion controls. These
controls provide no hardware, Safe rendering, performance or release result.
The actual Fedora compiler build and same-image KVM diagnostic are still required.

Preparation sets the compiled helper to0755 inside its owning container and
records its UID, GID, mode, size and checksum. The host checks that regular-file
record and reads the executable without changing its permissions. Creation
modes in both owned containers keep original diagnostic files readable for the
host export. Generated files and container originals are never overwritten by
the host; its helpers, context, bootstrap and export directories are new files
under the host-owned output directory. The ownership source control uses only
an already cached image, no network or pulls, and a labelled disposable tiny
file to demonstrate actual different-UID host chmod refusal and owner success.
It reports a prerequisite skip when that cached fixture is unavailable.
Safev5 records the exact Docker preparation, Docker VM, bootstrap-CD and timeout
driver exit codes separately. Child stdout/stderr are new owned mode-0600 private
files with the existing 32 MiB per-file bound. Their text, command arguments,
environment and exception messages are never exported. Only validated fixed
stage/status/exit-code/exception-class records and stream size/SHA-256 metadata
enter the existing strict original-byte privacy screen. A completed stage with a
nonzero exit code remains a failure.

The host records early root/KVM, context, image and library failure stages before
any VM capture, with all acceptance flags false. Temporary cleanup covers only
paths acquired by this invocation; report and cleanup failures preserve the
primary error, including when export, screening or container cleanup also fails.
An owned subprocess leader remains unreaped until its original process group
has received bounded TERM/KILL cleanup; repeated TERM cannot interrupt that
cleanup. Private inherited pipes cannot make an exited leader leave a running
descendant behind.

Firmware and disk temporaries are exclusively created without following
symlinks. Their open file descriptors retain device/inode/type/UID identities
until cleanup, which refuses foreign replacements. Disk initialization uses the
passed reserved descriptor via `/proc/self/fd`; the64GiB qcow2 disk remains the
same. QMP and evidence socket identities are acquired only after the owned VM
starts. Safev4's authenticated original host report reached the QEMU invocation
after checked passed-descriptor initialization and inode verification. A separate
qemu-img exit receipt was not recorded. Local replacement controls use an
explicitly synthetic blocked disk initializer.

Safev5 places only the additional diagnostic CD on `bus=ide.1`, a distinct q35
AHCI port. The original boot CD and boot order remain unchanged. Safev4's
original screened QEMU log rejected the default second unit on the first port,
before any guest capture. The narrow cached-QEMU source control uses two tiny
synthetic CD files, paused TCG and QMP; it boots no OS and validates no Safe
rendering. It must reproduce the old failure and observe both read-only CDs on
separate ports after the correction. Its cached-image prerequisite is disclosed
as a skip when unavailable.

The QMP topology observes the unchanged boot CD on its original default port
and the data CD on `ide.1`; it does not establish Linux `sr` enumeration.
Both console execution and the bootstrap resolve the unique `ARCTICSAFE` label,
require successful discovery and label queries, verify the selected block
device, and reject missing, duplicate or changed labels. The bootstrap mounts
that selected device read-only with the original `nodev,nosuid` flags. These
are the three narrow CD consumer corrections; the raw screencopy C helper
remains byte-identical to Safev4. Safev6 annotates the original guest operations
without changing their capture behavior. Real tiny xorriso and
blkid controls verify the generated fixture label and embedded bootstrap;
separate source-extracted guard controls explicitly use synthetic root/block
predicates and perform no guest mount or device access.

This adds diagnostic evidence, without a guessed product fix or
rendering acceptance. Local tiny controls use explicitly synthetic ISO/KVM
attestations or blocked VM construction and cannot demonstrate image behavior.

Safev6 adds a guest phase and exception-class receipt after the original
root-owned context has passed strict validation. Only fixed source-known phase
and class enums, the reviewed execution SHA, image source SHA and nonce are
emitted; exception text, commands, accounts, paths and environment are excluded.
An early failure before validated context emits the original generic failure
marker and no status JSON. The original primary capture failure is retained
across existing guest cleanup. The host wrapper accepts at most one exact
nonce/context-bound record and projects only its strict fixed schema through
the existing original-byte privacy screen. A projection/reporting failure
preserves an existing primary failure. Captures, boot flags, renderer settings,
CD label/bus, readbacks, timing, security and cleanup remain unchanged.
