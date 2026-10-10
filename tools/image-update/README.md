# Same-image Nix and signed update acceptance

This hosted QEMU lane is disabled until its manifest pins the rebuilt ISO, its
successful build artifact, the optimized source deployed to stable Arctic, and
the exact execution-file hashes. Independent review and source checks precede a
single-file activation on `codex/image-update-20261010`.

It installs the same ISO on an encrypted disposable disk with enforcing SELinux,
tests Nix desktop entries and user isolation, and stages the real signed Arctic
offline update. Every replaced preview package must have a higher RPM EVR. An
intermediate restricted-network boot applies the downloaded transaction. A final
offline KVM boot must prove a new boot, changed installed Arctic packages from
the pinned stable source, updater completion/history, retained settings, and Nix
profile and GUI persistence. It never modifies a user's computer or publishes a
release. An unchanged Nix engine version remains explicitly unproven.

Only bounded synthetic VM diagnostics are screened and uploaded; ISO files,
disks, sockets and generated executable payloads are excluded.
