# Exact live-image installer restoration qualification

This additive test lane boots the reviewed candidate ISO in a fresh disposable
KVM VM with no target disk, networking or OS installation. It uses the shipped
installer, client bridge, systemd-activated daemon and compositor. The original
native eight checks, CLI installation lanes and performance observer are unchanged
and remain independently required on the same image.

The lane is disabled: `execution-manifest.json` has `ready: false`, and no
`.github/qualification-20261009.installer` activation file is included. After the
final image build and independent source review, the release owner must pin the
exact build/artifact/ISO identities and execution input hashes, then activate with
one reviewed marker-only commit on `codex/qualification-dispatch-20261009`.

The checker advances the already opened real wizard from welcome to keyboard and
chooses Hebrew through its supported IPC. It verifies the actual engine's
`us,il` layout with Alt+Shift, protected live configuration, root service identity,
listener FD, GUI/bridge ELF paths, PIDs and process start ticks. The prepared idle
keyboard state is the baseline. It never calls Start or disk operations and does
not claim preservation of an installation in progress or reset of pre-test wizard
flags. The virtual machine is discarded afterward.

Three cycles switch to actual VT6 and return to the discovered graphical VT.
Three more cycles disconnect the output currently hosting the installer, both
outputs, then the currently hosting output again. The host controls actual QEMU
virtio GPU heads with the supported private D-Bus `SetUIInfo` API. The guest must
independently observe its real DRM connector and compositor output/layer changes.
Hosting-output loss must move exactly one mapped installer to the remaining
output; total output loss must leave no mapped installer, then restore exactly
one visible installer. Every restored case preserves page, Hebrew choice, daemon,
bridge and GUI identities, engine snapshots and keyboard hashes.

There are nine guest captures (baseline, six restored cases, two relocated cases)
and three host VT-away captures. The independent contract replays PNG hashes,
physical dimensions and actual installer background pixels; console captures must
pass a dark-screen/text-pixel guard. All twelve captures still require manual
review against the exact candidate and artifact archive. These pixel guards alone
are not sufficient release acceptance. The prepared idle engine scope and any
unavailable connection-log/audit telemetry remain explicit limitations.

Guest transport is a bounded named virtio port, bound to the UART completion and
nine host requests with exact token, source, ISO, execution, boot, UID and session
identities. The extractor rejects malformed framing, duplicate JSON fields,
invalid paths, mismatched hashes, oversized chunks and decompression expansion.
Valid failed evidence is retained with a failed state. Protected complete UART is
retained for independent live-account authentication and transition replay; the
large port stream is retained only as a bounded diagnostic prefix plus full hash.
SELinux must remain Enforcing and the complete mutation/cleanup interval must show
no new AVCs. Cleanup attempts VT and output restoration, stops only the owned GUI
and VM/private bus, and preserves the actual root engine until VM shutdown.

Host dependencies and compiled capture helpers are test fixtures, not ISO payload.
Their binary and compiler/source provenance is recorded. QEMU's `ui-dbus` module
also requires `ui-opengl` even when `gl=off`; existing native preparation installs
those host modules. A stopped-VM API capability check is not proof that the live
installer passed these six cycles.

Run source controls (synthetic fixtures, not VM qualification):

```sh
python3 -B -m unittest discover -s tools/installer-qualification -p 'test_*.py'
bash -n tools/installer-qualification/run-live.sh
```

The candidate workflow uploads `candidate-installer-restoration`. A successful
`execution.json` is still marked
`live_installer_restoration_passed_pending_manual_visual_review`, with
`release_acceptance: false`. Publication requires the separate mandatory publisher
checks, all twelve manual capture reviews and the other exact-image gates.
