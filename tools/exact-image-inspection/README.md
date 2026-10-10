# Exact candidate Mango inspection

This disabled static lane prepares evidence for independent review of the next
candidate's actual Mango and wlroots executable bytes. It cannot admit an
observer profile, satisfy performance acceptance, qualify an ISO or publish.
The three existing whole-executable profiles in `tools/performance/causal.py`
remain unchanged.

After a new artifact-only producer succeeds on its first attempt, explicitly pin
its complete image identity in `execution-manifest.json`: successful run/source,
ISO name/bytes/SHA-256, original artifact ID/ZIP bytes/SHA-256, external mode and
the original `PERFORMANCE-PLAN.json` SHA-256. Pin all seven `source_files` to the
actual candidate source tree using Git blob SHA, SHA-256, byte count and regular
file mode. Recalculate all three `execution_files` from the reviewed preparation
checkout. Leave every acceptance/profile flag false. Set `ready=true` only after
independent review of those exact pins.

Publish this reviewed preparation with no activation marker. Activate only by
creating `.github/exact-image-mango-20261010.activate` containing the immediate
reviewed parent SHA and a newline as the sole change on
`codex/inspect-exact-image-mango-20261010`. The hosted first-attempt guard checks
the event, sole parent, exact marker bytes, current remote ref and actual tracked
execution files before downloading or installing inspection tools.

The fetcher requires the successful first-attempt original producer API identity,
strict sub-2,000,000,000-byte image, signed stable-repository BUILD-INFO and the
original external producer receipt with all three successful startup modes.
It also checks the producer size/startup/receipt/upload steps succeeded and its
performance and release-publication steps were skipped. Archive digest, original
ZIP inventory/CRC, ISO digest and receipt checks precede extraction.

The reader reuses the retained-image inspector's pinned official Fedora image,
signed exact erofs-utils/xz dependencies and filtered EROFS extraction. Reader
containers have no network, a read-only root, no capabilities, no new privileges
and the hosted runner UID/GID. It extracts only Mango, RPMDB and the single
regular wlroots library selected by that image's RPMDB. Neither executable runs.
The evidence includes exact ELF bytes, SHA-256, RPMDB file-digest matches,
sections, headers, symbols, dependencies, unwind data and full disassembly. This
is not verification of target RPM signatures, every installed file or compiled
header offsets. Evidence is bounded below 31 MiB; partial failure remains failure.

An independent reviewer must inspect the actual full mapping/getter control flow
and field chains before a changed executable or ABI receives any new explicit
observer/comparator profile. This lane creates no such profile. Runtime readiness,
kernel-format/loss/precision checks and six original paired boots remain separate
requirements.
