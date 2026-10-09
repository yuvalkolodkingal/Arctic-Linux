# Active installation restoration qualification

This separate disabled lane complements the existing idle wizard, native, CLI
installation, dictation and performance gates. It boots the same final ISO in an
owned UEFI KVM VM with two virtual displays, no network or host block devices,
and one newly created standalone 64 GiB qcow2 target. The target serial, size,
guest block path and pristine state are verified immediately before the shipped
Summary action. No activation marker is included; the image remains null and
`ready` remains false until the final image and all execution inputs are reviewed.

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
Its actual root must be the original target partition, SELinux must be Enforcing,
and the installed console and Mango keyboard must retain `us,il` with Alt+Shift.
Console login and sudo use a random disposable credential stored only in private
test-CD data. Secret input is permitted only after host OCR observes the actual
last getty or sudo password prompt. The Fish home prompt was checked against the
officially signed Fedora 4.6.0 package bytes; that static inspection is not proof of a
future candidate's runtime prompt. A mismatch fails before further secret input.

The four live guest captures, actual VT-away host capture and two pre-input console
prompt captures form a mandatory seven-image manual review inventory. The OCR
binary, English model and package provenance are retained; the publisher binds
their receipt and original images without claiming a second OCR runtime replay.
Public prompt receipts contain a fixed prompt kind and the SHA-256 of the actual
observed canonical last line after its exact match, together with its observation
time. Prompt text is not repeated in public JSON. The authenticated shell proof
must fall between the getty and sudo observations; the shell probe is not uploaded.
Transport, original UART, every host request, candidate/source identities, write
counters, installed boot receipt and image hashes are independently replayed.
The random 32-hex `binding_id` binds both UARTs, payload chunks, collector completion
and all host requests to one execution. Legacy field names and extra fields fail
the producer/consumer inventories rather than receiving a scanner exemption.
Credentials, private target images and raw account RPC payloads are never uploaded.

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
