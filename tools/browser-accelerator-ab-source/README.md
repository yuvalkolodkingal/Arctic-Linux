# Disabled accelerator experiment

This Source proposal is not a product optimization, a benchmark pass, or an
activation. Its candidate registers Epiphany50.6's 43 immutable window default
accelerator rows once per live GApplication object. Both direction-dependent
navigation setters still execute on every window. The marker is set only after
all default setters return; an interrupted partial initialization is not marked
complete. GObject owns the marker, so another application and an application
created after disposal must initialize their own defaults.

The exhaustive signed debugsource census covers 341 C/H files. The only other
setter callers are EphyShell's `app.*` shortcuts and extension commands named
`app.webextension-command-*`. Every such caller, including removal and updates,
is unchanged. All local action groups and their window-specific targets are
created for every window. A foreign native component directly rewriting a
`win.*`, `tab.*`, or fixed `toolbar.*` default would now retain its modification
instead of the next constructor resetting it. The pinned application exposes no
such caller. This observable foreign-mutation policy is explicitly part of the
experiment and requires independent review before any product proposal.

Official GTK4.22.5 Source rebuilds shortcut entries and notifies application
windows for every setter call. This is source evidence of redundant work, not a
measurement of the Fedora-patched implementation or proof that the experiment
saves the required launch time. The local compiled controls use real GObject
lifetimes/data with a labelled controlled GTK setter model. They do not attest
actual GTK key dispatch or performance. Hosted real GTK controls and measured
A/B launches remain required.

`profile.py` copies the reviewed signed-image collector with only its hook
inventory and required-phase assertions narrowed. It keeps existing timing,
loss, cleanup, finite event/schema and security limits. Its few no-argument
hooks measure accelerator registration, window construction, and application
entry. It removes the high-frequency generic widget hooks. Native exact-Mango
map proof remains the map observation. It runs on a fresh separate disposable
boot with the unchanged loopback role workload, 45-second precondition, three
fresh five-second launches and original close/reap rules. It cannot substitute
for the full paired gate or explain a measured product cause on its own.

`build_recipe.py` is a disabled hosted build recipe. It prepares baseline and
candidate from the same signed 1:50.6-1.fc44 SRPM, with the baseline spec exact
and the candidate spec changed only by one Patch1 declaration. Both retain
Fedora's original build/check flags. It requires the same container/toolchain,
resolved dependency census, macro census and build path for both. No build is
run locally and no package is installed in the host or image. Produced custom
ELF hashes, Build-IDs, debuglink joins and dependencies must be retained and
reviewed before a new overlay-specific runtime collector can be admitted. The
signed image's exact-ELF profile does not accept guessed custom build identities.
A hosted build-only lane and then a separately reviewed disposable A/B lane are
necessary; neither is currently activated by this proposal.

The 10% regression and 5ms precision gates, browser role, CPU/renderer settings,
profile persistence, session restore, WebKit sandbox, SELinux, portals,
accessibility and application functionality are unchanged. No gate is weakened
and no performance improvement is claimed.
