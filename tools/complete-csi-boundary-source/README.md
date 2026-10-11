# Complete CSI boundary correction (disabled Source)

This component fixes a deterministic Source counterexample in the pinned b3
scanner. A complete `ESC[1@` CSI followed by ordinary `public.example` text
formed the email-shaped match `1@public.example` across a control boundary.
The original terminal projection of those same bytes contained no email.

Only `classification_view` changes in the copied scanner. Its Source view
replaces the final `@` of an exact complete CSI of at most 4,096 ASCII bytes
with one space. It retains every numeric parameter and every original
position. A compact UTF-8 buffer avoids an object per control. Original
evidence bytes, regexes, string payloads, terminal-view scanning, malformed
escape rejection, public-literal contiguity and every existing limit remain
unchanged. Ordinary or terminal-obfuscated credentials remain rejected.

The copied same-Match helper changes only `diagnostic_view_alignment` and its
whole scanner SHA literal. Its bounded replay proves that exact same-position
projection in both directions, without a second complete private view or
exporting values, offsets, lengths or digests. All other helper functions and
finite schemas are byte-preserved through the recorded inverse.

The parent is the exact public BIOS activation 0d267. Its files, workflows,
markers, manifests and image binding are untouched. This adds only these five
regular Source files. The manifest is disabled and no operational selection,
workflow, marker, public reference or VM run is prepared here. The copied
historical scanner/helper CLI paths are not a new operational composition.

Synthetic Source controls establish the parser correction and loaded
Code/globals/site alignment. They do not establish the current BIOS operand,
cause, image installation, whole UART privacy or release qualification. All
actual original acquisition/application leases remain closed.
