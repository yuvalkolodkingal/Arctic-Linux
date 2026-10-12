# Bounded complete CSI Source correction

This disabled component separates complete ASCII CSI headers of at most 4096
characters in the source privacy view. It retains the original ESC marker and
masks the remaining header positions with spaces, preserving the unsigned
position map and the unchanged outer display-view scan. Raw bytes and original
privacy patterns, allowed spans, OSC/DCS payloads, rejection site 139 and limits
remain unchanged. Genuine display-joined secrets remain rejected.

Only scanner.classification_view and helper.diagnostic_view_alignment change
against the accepted 8b9/a92 component. Diagnostic replay streams bounded blocks
and accepts only that exact projection. This corrects declared synthetic legal
CSI A/h/B boundary counterexamples. The actual BIOS failure operand and cause
remain unknown. This component is not a current image qualification or release
acceptance. Historical default build/CLI paths are unchanged and are not an
operational binding; a separately reviewed lane must explicitly select these
whole bytes, generated Source sites and complete Source dependency inventories.
