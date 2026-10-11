# Disabled matching public-key format correction

RPM's public-key import CLI requires an armored public-key block. The proposed host runner adds only `--armor` to its existing exact-fingerprint export and binds its 1672-byte output. The proposed producer binds that same armored output by SHA-256 before the unchanged isolated RPM import and full source-package signature verification.

The armored body decodes to the identical 1176-byte Fedora 44 public-key packets, including all original subkeys and signatures; the fingerprint and official bundle remain unchanged. The receipt retains the exact GPG export, isolated RPM import, and full signed original Epiphany SRPM check. Official TLS key provenance is retained; no out-of-band fingerprint trust is claimed.

These copies cannot activate a workflow or build. All existing source, SDK, spec, patch, package layout, validation, deadlines, logs, privacy, and container cleanup remain unchanged. Existing historical and current failures are not attributed to this format defect. Hosted execution, output binary identity, performance, and release acceptance remain unproven.
