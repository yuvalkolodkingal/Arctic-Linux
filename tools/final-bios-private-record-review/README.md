# Reviewed exact-image BIOS private record review

This preparation is based on fbe533529ac913435e8026c313a20aab4549c78a and remains marker-free. It preserves the exact 1,934,641,152-byte image from run 38334358585, offline BIOS install, scanner, privacy rules, security checks, timeouts, closed public observations, runtime gate, and release gate.

The separately reviewed age X25519 public recipient was generated and durably retained outside GitHub. The failure-only wrapper can encrypt the single already-authenticated original serial-install.log record into a fixed 16 KiB envelope. The workflow downloads only pinned official age 1.2.1 bytes and uploads only record.age plus a non-sensitive receipt. Public host evidence remains public-only.

No marker or private key is included. A sole-marker child commit may activate one reviewed first-attempt push after this preparation passes exact-head CI and independent review.
