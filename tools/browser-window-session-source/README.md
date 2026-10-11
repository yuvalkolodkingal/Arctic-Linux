# Browser window and session startup source preparation

This disabled preparation adds optional numeric function timings to the
previously reviewed browser-only observer. It is for a separate installed-image
diagnostic boot. There is no workflow, activation marker or product change.
The context is `ready: false` and its image remains null. Final paired
qualification still uses its original workload, 45-second preconditioning,
10% regression limits and 5-millisecond precision limit.

The prior admitted b871 diagnostic had about 727–821 milliseconds between
completed application registration and the native map lower bound in its
three instrumented repeats. Those times are not final paired measurements.
The previous probes did not attribute that region to a particular session,
window, WebKit process or renderer. Synchronous DBus observations did not show
a long service timeout, and no profile-migrator spawn was observed.

`profile.py` preserves the reviewed collector except for 18 optional timing
symbols and browser dynamic-symbol inventory. The low-frequency additions
cover application window registration, root content/default size, libadwaita
tab/content setup, WebKit settings/session state and generic asynchronous file
read dispatch/completion. Five optional Epiphany symbols cover session resume,
session load, URI opening, tab construction and window construction. The
collector resolves these only from the dynamically exported function table of
the verified, whole-hashed RPM-owned browser ELF. A missing symbol is reported
as absent. It does not infer offsets from upstream code, local host files,
unverified debuginfo or a guessed Fedora build.

New probes fetch no arguments, return values, object pointers or strings.
Reports contain the existing fixed phase labels and numeric timing/lifecycle
fields. A generic GIO read is not identified as a session read merely because
it occurs nearby. Async dispatch duration is not completion latency. The
existing widget visibility probe does not identify a particular window or its
content. Nested spans are not additive budgets. Optional missing Epiphany
symbols can leave static session attribution unavailable.

The original 8,192-event and line/buffer caps, trace drain/loss checks,
RPM/library identity checks, exact exec gate, ownership/cancellation cleanup,
normal `epiphany --new-window` invocation, recording-free workload and SELinux
requirements remain unchanged. Extra probes may add overhead or exhaust the
unchanged event cap; that fails collection rather than silently sampling.
Original DBus identifier probes retain their prior exact-GIO-ABI limitation.
New no-argument timings require no object-layout or parameter-ABI inference.

No browser feature, session restore, portal, keyring, accessibility, sandbox,
renderer or scheduling policy is changed. A new measurement needs independent
Source review, an exact final image tuple, complete operational pins and Root
activation on a separate disposable boot/disk. Existing process-persistence
questions do not waive the final paired browser regression flags.

Run the focused synthetic controls with:

```sh
python tools/browser-window-session-source/test_source.py
```

The controls compile a real owned ELF and exercise the actual changed inventory
using a clearly labelled virtual RPM/path provider. They also drive the
unchanged decoder/reader with controlled pipe events and real cancellation.
They do not establish Fedora exports, a kernel uprobe execution, a startup
cause, a product optimization or release qualification.
