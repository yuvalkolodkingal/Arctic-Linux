This is an audit-only, separately versioned acceptance prototype for a **fresh installation of the exact existing candidate ISO**. It is prepared for independent review; no VM run or workflow dispatch has occurred. The original run 37507582946 and its actual result must remain recorded separately.

ISO identity: source `fe4742c8b9414c45f0bcbb0a4191f116383c60d1`, build-reported SHA256 `84c9c88ebcbcaf69dbabf56509a9ceb2db58e5dc41d7bae12093edba12f60718`, 1,880,244,224 bytes. The executor must verify the actual ISO bytes against this checksum before any authorized run. The checker binds source/package/helper identity in the guest; the embedded ISO checksum is an identity label, **not an independent in-guest byte verification**.

- `guest-check-dnf-v1.py` explicitly runs ordinary DNF upgrade and reboot acceptance.
- `guest-check-offline-v1.py` explicitly runs `arctic-update now --sync`, signed offline staging and reboot/history acceptance with the exact expected stable source. Run it in its own fresh installation; it is separate coverage.
- `prepare-v1.py` deterministically builds both complete standalone copies from pinned source, inserts `recovery-extension-v1.py`, and writes `parity-v1.json`. It writes only this audit directory.
- `test_recovery_v1.py` contains 20 focused controls, including numerous negative cases. `run-existing-tests-v1.py` runs the 36 exact original acceptance regressions against the prototype.

Live and first installed browser checks retain the original `arctic-open browser <file URI>` gate and original browser implementation. The new compatibility mode is selected before invocation, after the saved successful first phase and update, changed boot ID, exact candidate/source/checker proof and exact older-stable RPM owner/NEVRA/epoch/helper SHA are verified. Legacy state is rejected. State is written only after every mandatory first-pass and chosen update check passes, and is bound to the revised checker bytes and update method. There is no host-attestation or retained-original-disk route.

In that verified older-stable mode, the configured no-argument opener must exit successfully and map one fresh visible native Wayland Epiphany window for five seconds. The HTML fixture MIME type and all four browser handler defaults are mandatory. Literal `xdg-open <absolute fixture path>` must render the unique JavaScript-ready title in the same proven UI/window, retained for 45 seconds. Complete UI PID/start/executable identity is rechecked; original WebKitGTK6 descendant, namespace, Seccomp 2, NoNewPrivs 1 and sandbox-environment checks remain mandatory. Failures never trigger a direct-browser retry, helper replacement, security relaxation or alternative browser selection.

All 31 original top-level functions except `main` are byte and AST identical, including the original browser, Nix Foot/profile/export/rollback helpers, signature checks and AVC helper. The 50 distinct original non-browser `check` calls retain AST parity, including both occurrences of the AVC gate. Existing nested update, trust, desktop-customization and profile functions retain AST parity. The two complete copies differ only in their explicit entrypoint update method.

After independent review and authorization, use a new unused output directory for each method. These are command templates, not executed actions:

```bash
# First verify the immutable ISO bytes; require available KVM through the existing harness.
# Select exactly one checker and a new output path for that update method.
tools/test-install.sh --iso '<byte-verified existing ISO path>' \
  --kvm --memory 4096 --smp 2 --boot-append '' --install-timeout 2400 \
  --boot-network online --guest-check '<pinned guest-check-dnf-v1.py path>' \
  --out '<new unused same-ISO DNF qualification output>'

# Preserve the first boot evidence before the harness starts the second boot.
cp '<new output>/serial-boot.log' '<new output>/serial-before-update-reboot.log'
tools/test-install.sh --stage boot --kvm --memory 4096 --smp 2 --boot-append '' \
  --boot-network online --guest-check '<same pinned guest-check-dnf-v1.py path>' \
  --out '<same new DNF qualification output>'
```

The offline variant uses `guest-check-offline-v1.py` in both stages and a different fresh output/disk. The installed boot needs the existing authorized network path for Nix fetching and updates; live installation keeps the original offline restrictions. The harness removes or rewrites some files in its output, so never point it at the original run's evidence or an existing unrelated directory. No ISO rebuild, source merge or publication is involved in this prototype.

Remaining qualification: independent review, original run outcome, authorized executor access to the byte-verified same ISO, and actual fresh VM runs. Host controls are not proof of GUI behavior, successful updates, codecs, accessibility, physical hardware or performance.
