# Active installation restoration qualification

This separate disabled lane complements the existing idle wizard, native, CLI
installation, dictation and performance gates. It boots the same final ISO in an
owned UEFI KVM VM with two virtual displays, no network or host block devices,
and one newly created standalone 64 GiB qcow2 target. The target serial, size,
guest block path and pristine state are verified immediately before the shipped
Summary action. Changes to this lane remain disabled until their execution inputs
are reviewed and a fresh activation is prepared. Its retained image pin identifies
the existing candidate; retaining that pin does not qualify changed execution code.

The shipped GUI's normal `fill` and armed `next` actions choose Hebrew, explicitly
consent to offline installation, select the owned disk, disable encryption, keep
the normal app selections and create a disposable fixture account. Summary calls
the real `Wizard.startInstall` and socket-activated engine `Start`. The offline
choice requires the separately reviewed product change to the Network step; an
older GUI cannot silently qualify this lane. No replacement engine, fake progress,
RPC mutation bypass or input-device permission change is used.

Every disruption observation requires the actual copy phase, the original root
`rsync` process directly parented by the same engine, and its real Btrfs mount on
the serialed target partition. The GUI, bridge, engine, listener, protected Hebrew
configuration and safe wizard choices must stay unchanged. Progress must remain
monotonic; all selected queued modules are checked against the candidate catalog.
All 49 shipped QML/qmldir files, catalog and launcher are bound to actual candidate
source bytes. Account answers, passwords, free-form status and engine logs are
excluded from the public guest report.

One cycle changes to real VT6 and returns; one disconnects the display currently
hosting the installer and then reconnects it. Exactly one installer must be mapped
and visible after return and on the remaining display during hosting-output loss.
The existing idle lane still covers three VT cycles and three output-loss cycles,
including loss of both outputs. This active lane makes no claim about active
installation with both displays disconnected.

The target's QEMU writes are capped at 8 MiB/s to retain a genuine running copy
across the transitions. Bounded original QMP write counters must increase at each
host request, including while VT6 is foreground and while the hosting output is
absent. The disconnect request's initial interval occurs before loss; its restore
request independently proves writing during the observed loss. The cap and this
extra lane are not performance measurements and do not alter benchmark limits.

The same engine must finish successfully and the same GUI reach Done. A new owned
QEMU process then boots the same disk and UEFI variables with the live ISO removed.
The unchanged physical greeter classifier must succeed within the original
900-second bound. After a 60-second boot grace, the host checks VT1 through VT5 in
turn so a valid greeter cannot be missed merely because another VT remained active.
Its actual root must be the original target partition, SELinux must be Enforcing,
and the installed console and Mango keyboard must retain `us,il` with Alt+Shift.
Console login and sudo use a random disposable credential stored only in private
test-CD data. Secret input is permitted only after host OCR observes the actual
last getty or sudo password prompt. The Fish home prompt was checked against the
officially signed Fedora 4.6.0 package bytes; that static inspection is not proof of a
future candidate's runtime prompt. After one nonsecret Return, an unrecognized
cosmetic prompt may receive only the nonsecret challenge. That command computes
SHA-256 over the fresh nonce, `$USER`, `id -u` and `id -un` using installed
coreutils, clears its echoed command, and renders three short decimal records.
Each record has a distinct one-digit row marker and the three 20-digit records are
inset, bold and separated by blank rows. Every expected record is absent from the
typed command. Digits-only single-line OCR reads three fixed original-scale row
regions derived from the challenge's ANSI positions and the exact 8×16 console
cells. Each 176×24 OCR canvas holds unchanged response pixels with black padding;
the final crop stops before the following prompt. The original 1280×720 captures
stay unchanged. Whole-frame OCR can interpret identical small glyphs differently,
so it is used for readiness and the private-input guard, rather than response
recognition. The three physical regions must each contain exactly one 20-digit
record with its expected marker in that position. The parser must observe exactly three records with
distinct expected row markers on the physical 1280×720 console within the original
45-second bound. Normally at least two rows must agree on every one of the 19
response digits, and the complete consensus must equal the expected 60-bit
response. If OCR damages the same glyph in multiple rows, authorization instead
requires the three original-scale response-cell pixel regions to be byte-identical
and at least one complete row OCR to equal its expected marker and full 60-bit
response. Pixels alone and near-match text never authorize. Two exact rows without
the third marker cannot pass. Disjoint OCR errors can be corrected; duplicate or
swapped markers, changed response pixels, zero exact rows, split votes, stale
responses and wrong identities fail closed. Sudo input remains forbidden
until that response is observed. Getty and sudo password OCR remain unchanged.

The four live guest captures, actual VT-away host capture and two pre-input console
prompt captures form a mandatory seven-image manual review inventory. The OCR
binary, English model and package provenance are retained; the publisher binds
their receipt and original images without claiming a second OCR runtime replay.
Public prompt receipts contain a fixed prompt kind and the SHA-256 of the actual
observed canonical last line after its exact match, together with its observation
time. Prompt text is not repeated in public JSON. The authenticated shell proof
must fall between the getty and sudo observations.

A failed post-command identity challenge can retain at most three original
1280×720 frames before any sudo command or input. Each frame receives an additional
full-frame OCR pass without the numeric whitelist to withhold private password
echoes. Fixed metadata binds the exact image bytes, dimensions and failure-only
inventory; raw OCR, response digits and differences are excluded from JSON.
Changed inventories, extra fields, images or hashes fail closed. The workflow's
strict original-byte screening must pass before these failure exports are uploaded.
These images never authorize identity, sudo or release. A later successful identity
check removes them, preserving the mandatory seven-image success inventory.

If the real harness fails, the runner still checks the live restoration report
and transport, records that primary failure and performs normal owned cleanup.
It does not read a dependent installed serial stream or claim a completed
execution. A successful harness must supply a typed passed installed-boot receipt
before the private installed UART is read; all existing installed and execution
validation remains required.
Transport, canonical public UART protocol projections, every host request,
candidate/source identities, write counters, installed boot receipt and image
hashes are independently replayed after complete private UART validation.
The random 32-hex `binding_id` binds both UARTs, payload chunks, collector completion
and all host requests to one execution. Legacy field names and extra fields fail
the producer/consumer inventories rather than receiving a scanner exemption.
Credentials, private target images and raw account RPC payloads are never uploaded.
The active security report projects only Enforcing state, audit mode/lost counter,
zero observed AVCs, audit-enabled state and the fixed telemetry scope after native
interval verification. Audit interval bytes, record counts and digests remain private.

Host cleanup restores both owned outputs and the original VT when possible,
attempts termination and reaping of each owned QEMU and closes its private display
bus even when other cleanup stages fail. The running engine is retained until VM
shutdown. Failed or interrupted evidence stays failed. A successful source test
or a passed report pending manual review cannot publish a release.

Source controls, including coherent negative transport/ownership/credential
fixtures, are run with:

```sh
python3 -B -m unittest discover -s tools/installer-qualification -p 'test_*.py'
python3 -B -m unittest discover -s tools/tests -p 'test_installer_active_publication.py'
bash -n tools/installer-qualification/run-live.sh
```

After review and exact-image pinning, the dedicated marker-only workflow runs
`runner.py --active-profile` and uploads `candidate-installer-active-restoration`.
Public release acceptance separately requires its successful first attempt and
seven-image review, plus every original same-image gate.
