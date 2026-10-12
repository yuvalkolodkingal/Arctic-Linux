# Disabled exact public Fedora 44 DNF UID span remedy

This selected scanner changes only the Source-view handling of one independently public email span. An optional closed `public_DNF_UID_role` argument defaults to no exception. The accepted observer enables it only for the fixed `logs/producer.log` role. A direct caller supplying the literal producer role can admit only that same exact public line; this policy does not authenticate caller or DNF origin.

The match must be the exact public Fedora 44 email inside the whole original vendor-format UserID line, with its original newline boundary, contiguous unmodified bytes, and no extra fields. It does not authorize any email/domain wildcard. The original regex alternatives and order remain exact; all remaining matches are still checked. Unknown/private matches before or after this public span reject the complete member.

The terminal-view and terminal-payload policy remains unchanged. In particular, unrelated complete CSI elsewhere can trigger a second terminal-view scan that still rejects this UID. This conservative limitation is intentional. No normalization, original repair, partial upload or acceptance flag changes occur. The existing c22d diagnostic bit remains available and false for unsupported matches or phases.

Official signed-key-derived UID and pinned DNF formatter Source are bound in the manifest. There is no current UID, actual DNF, SDK, RPM, performance or release success claim. Current/old artifacts, members, logs and providers remain permanently closed. Fresh execution/Source peer/public guard/Root activation are still required.
