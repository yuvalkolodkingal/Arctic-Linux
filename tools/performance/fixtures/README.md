`v1.2-offline.toml` is the exact historical profile from commit
`d13da6c:profiles/ci/offline.toml`, preserved for the original public v1.2 ISO.
SHA-256: `e6b9aa317521bdaaaf343629bc5de8b914b0a5f58387a0c9fe31754f17c0d20d`.

Paired runs install this profile on the baseline and the current
`profiles/ci/offline.toml` on the candidate. Both profiles and ISO hashes are
recorded. This keeps the baseline's configured Kitty/Nautilus/Zen roles while
declaring Foot/PCManFM/GNOME Web on the candidate.
