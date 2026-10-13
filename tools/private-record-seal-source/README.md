# Disabled private record seal Source

This default-off Source can encrypt exactly one original serial-install.log record after the existing exact scanner traceback and closed unit/member observation agree. It never admits the record to the public scanner, changes no acceptance rule, and does not establish a runtime cause or release acceptance.

The record is put inside a fixed 16 KiB random-padded envelope and sent only to the pinned official age 1.2.1 executable through stdin. age writes binary ciphertext directly to an exclusive file; stderr is discarded and no plaintext file, digest, length, value, excerpt, argument, environment value or receipt field is produced. The only public outputs are record.age and a closed receipt. The original exception and all privacy, runtime, and release gates remain unchanged.

The operational manifest intentionally has no recipient. Generate an age X25519 identity on a local executor outside GitHub, retain the private key there, independently review the public age1 recipient and its SHA-256 over the recipient plus newline, then author a separate ready preparation. Never commit or upload the private identity.

After download, verify record.age against receipt.json, obtain the pinned age 1.2.1 binary, and decrypt locally:

    sha256sum record.age
    age --decrypt -i /private/path/arctic-review-identity.txt -o record-envelope.bin record.age

Parse record-envelope.bin locally only: verify the 25-byte magic ARCTIC-PRIVATE-RECORD-V1 followed by NUL, read the next four bytes as an unsigned big-endian length, and inspect exactly that many following bytes. Delete the plaintext envelope when review is complete.
