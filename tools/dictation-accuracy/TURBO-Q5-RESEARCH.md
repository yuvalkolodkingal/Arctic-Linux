# Quantized turbo comparison

`pins-turbo-q5-research.json` is a separate research manifest. It changes no
production download or default. It keeps the pinned CPU binary and both official
FLEURS test splits unchanged, and selects the multilingual
`ggml-large-v3-turbo-q5_0.bin` model from an immutable Whisper.cpp model revision.

Use the existing `accuracy.py` harness unchanged. In a separate offline Fedora 44
container run, mount this research manifest at the harness's `pins.json` path,
pass the verified turbo model as `--model`, and use the existing fixture bundle
with manifest SHA-256
`d97f1daced07fd25e5ddeba3bbb8df7f5af1cccfa216dc0f31acd3ddb2abd2fd`.
Keep `--threads 2`, the identical ten utterances, and a fresh output directory.
The harness SHA-256 for the measured small baseline was
`8df683cee067eb1b20fc7f5bc76e1ed23607e584aad26ec91dfb54939492f6c6`.
Record all model/pins/harness checksums, errors and fresh-process timings. Do not
replace samples, normalize differently, or publish transcripts.

The measured small baseline was English WER 8/103 (7.77%), CER 13/469 (2.77%),
and Hebrew WER 42/100 (42%), CER 58/476 (12.18%). Those results are a material
reason to investigate another model. They do not establish general accuracy,
automatic language detection or mixed-language behavior.

Voxtype v1.1.0's `src/transcribe/whisper.rs` accepts an existing absolute `.bin`
model path and explicitly supports large-v3-turbo; it uses whisper-rs 0.16.0.
Quantized-model compatibility, accuracy, RAM and CPU latency still require the
real run. The tiny read-speech corpus cannot establish Whisper accuracy parity,
GPU support or release qualification. A production model decision needs the
comparison evidence plus actual recording and installation validation.
