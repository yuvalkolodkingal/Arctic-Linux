# Disabled exact-Epiphany implementation-library observer

This separate-boot diagnostic proposal corrects the five Epiphany function
providers from the launcher to `/usr/lib64/epiphany/libephymain.so`. It also
observes six no-argument session callbacks and window construction/init entries.
It changes no product or performance acceptance rule. Its execution context is
disabled (`ready: false`, `image: null`); there is no workflow or activation.

The official Fedora44-signed epiphany-runtime 1:50.6-1.fc44 launcher whole SHA
matches the previously admitted image launcher. Matching runtime-debuginfo,
debugsource and DWZ packages pass signature checks under the one imported
Fedora44 key, obtained from Fedora's official TLS key bundle/security page.
This is not independent out-of-band key trust. The exact library whole bytes,
GNU Build-ID, debuglink CRC and matching supplementary DWZ Build-ID bind all
static entry offsets. Ten entries have exact DWARF Source lines; resume's entry
line is unavailable. No offset is guessed or substituted.

Before probes, the future guest must verify exact package NVR/RPM files and the
implementation library's canonical path, complete SHA, size, Build-ID and all
five dynamic exports. Static entry offsets are accepted only for that same
whole library. After mapping and the unchanged persistence period, the collector
binds the same browser UID/start-tick generation's implementation-library VMAs
to canonical whole file bytes through the unchanged reviewed `map_files` helper.
That helper compares controlled procfs-link FDs with the canonical FD; it avoids
the invalid Btrfs maps-device versus stat-device comparison. Denied `map_files`
access fails closed; no privilege or security policy is added.

The 45-second precondition, three direct launches, five-second persistence,
original browser arguments/workload, native observer, monotonic raw clock,
8192-event/16384-line caps, zero-loss requirement, cleanup, SELinux, sandbox,
accessibility and portals stay unchanged. New hooks fetch no arguments. Output
contains fixed labels and numeric entry/return spans; unfinished entry-only
spans remain incomplete and unmatched returns reject. Probe durations include
nested work and overhead, and cannot be summed as phase budgets. Overflow
rejects; no silent sampling or filtering is allowed.

The actual image implementation library and its process mappings have not yet
been retained or admitted. The signed-package/static joins and local virtual
RPM/procfs tests do not prove an actual startup cause, first paint, performance
improvement, benchmark qualification or release qualification. Exact GTK/GIO
argument ABI uncertainty remains unchanged. A future diagnostic requires
independent Source review, operational binding and Root-owned activation.
