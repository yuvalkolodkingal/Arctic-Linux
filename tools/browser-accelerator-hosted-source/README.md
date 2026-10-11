# Disabled hosted matching-SRPM A/B producer

This executable producer is prepared for a future reviewed GitHub Actions lane,
inside one disposable rootful Fedora44 container. Its context is disabled. It
performs no work when imported; no producer invocation or package build has run
locally. It must not be activated by a standalone context change: a reviewed
host workflow, source/pin admission, exact container proof, whole-original
private build-log retention and uploader are still required.

The producer verifies the exact official signed 50.6-1.fc44 SRPM against the
retained Fedora44 primary key. It decodes only the three whole hash-bound source
members using a bounded flat-name CPIO parser. It prepares each variant in the
same build path: the baseline spec and sources are exact, and the candidate adds
only the reviewed Patch1 declaration and exact accelerator patch. Fedora's
original rpmbuild phases/checks/options remain active. Both variants use one
resolved package/dependency and RPM macro census, which must remain identical
across both builds. Their build trees/RPMs/logs stay private.

Exact F10-matching GTK, GLib, libadwaita, WebKit and libsecret development packages
are required. An unavailable version or changed dependency state fails before
claiming ABI fidelity. The selected key has official HTTPS provenance; no
independent out-of-band trust is claimed. The source RPM's i686 header is its
packaging metadata; both actual builds explicitly target x86_64.

The unactivated host must own the entire disposable container and stop/remove
its exact container identity on timeout/cancellation. Producer subprocesses run
inside that disposable container. The host must preserve complete original logs
and both custom runtime/debuginfo packages before any extraction or upload. A
new exact-ELF/debuglink/ABI/runtime-map Source admission is needed after actual
production; the existing signed-image collector does not admit these custom
ELFs. No overlay, VM, stable RPM, optimization, regression or release pass is
claimed by this preparation.

`gtk-control.c` is a future hosted real GTK control using the exact signed
accelerator table and exact candidate C block. It checks semantic key/modifier
identity, ordered alternatives, multiple application lifetimes, per-window
action-group dispatch, direction changes and dynamic extension/shell remaps.
It deliberately tests the disclosed foreign default-remap policy. The producer
will compile it with the exact GTK SDK and run it on an isolated Xvfb/session
bus; this is a GTK API control, not compositor or actual keyboard-event proof
and not a renderer override in the measured browser workload. It has not run
locally. Host preparation must supply compiler/pkg-config/dbus-run-session/Xvfb
tools before producer execution; no tool acquisition has occurred here.
