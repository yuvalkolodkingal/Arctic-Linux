# Qualified release assets

`prepare.py` runs only in the reviewed hosted publication lane after the retained
image and each separate qualification artifact pass their existing contracts.
The generated `release-notes.md` is the actual publisher body, rather than a
separately maintained draft. It presents the validated ISO bytes and checksum,
paired comparison medians and observation widths, and both dictation CPU
profiles' online/recovered English and Hebrew aggregate measurements.

`release_notes(proof, comparison)` only formats already-validated evidence. In
external performance mode it receives the independently replayed comparison;
the legacy mode receives the same comparison already checked by its existing
proof function. It never downloads evidence, substitutes historical results,
changes a gate, certifies a physical GPU or claims Whisper accuracy parity.
The formatter remains inside the already hash-pinned publisher helper.

Storage means root-filesystem allocated bytes, not whole-disk use or the storage
of a dictation-ready system. Paired offline installations precede the dictation
payload download. Dictation download sizes describe pinned asset bytes;
dependencies can add space. Aggregate elapsed time includes recording and
controller insertion completion, rather than isolated decoder latency.

Relevant source controls, including original-serial replay and invalid-input
rejection, run with:

```sh
python3 -B -m unittest discover -s tools/tests -p test_qualified_release.py
python3 -B -m unittest discover -s tools/tests -p test_external_performance_publication.py
```

Synthetic formatter or publication rehearsals exercise source behavior only.
They do not qualify an ISO, replace VM evidence or authorize publication.
