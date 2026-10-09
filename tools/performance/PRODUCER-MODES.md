# Artifact-only performance producer modes

The default `in-producer-paired-v1` mode keeps the six paired KVM boots in the
ISO producer. Image consumers require the first producer attempt and its startup
and paired-performance steps to succeed. An omitted mode in an older reviewed
manifest selects this default; it never selects the external mode.

`frozen-external-paired-v1` explicitly separates image production from performance
measurement so a subsequently audited exact Mango ELF can be admitted without
rebuilding the image. It requires a `workflow_dispatch` at an exact reviewed
`expected_source_sha`, first attempt only, `release=false`, `boot_test=true` and
`performance_acceptance=false`. The producer remains artifact-only. All three
startup tests and the strict decimal size gate still run.

After startup and size succeed, the producer writes `PERFORMANCE-PLAN.json` into
the ISO artifact beside `BUILD-INFO`. Its schema is
`arctic-producer-performance-receipt-v1`. It binds the repository, workflow,
event, exact source/run/attempt, typed dispatch inputs, actual ISO name/size/SHA
and successful startup serial-log identities for UEFI Try, BIOS Install and
UEFI Safe. It states `release_acceptance=false`; it contains no performance
result and makes no qualification claim.

An external image manifest must explicitly pin `image.producer_mode` and the
exact `image.producer_receipt_sha256`. Image fetch also verifies the successful
first-attempt producer job, startup and size steps, receipt and ISO upload steps,
skipped in-producer performance step, and skipped publication job. Missing or
contradictory mode evidence fails closed. Failed historical producers remain
rejected in both modes. The separate frozen lane and publisher must require
their own successful, exact-image, first-attempt six-boot evidence; the receipt
alone never permits publication or weakens another release prerequisite.
