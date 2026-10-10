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

Two additional research manifests select the optimized Haswell/x86-64-v3 CPU
asset: `pins-small-avx2-research.json` keeps small, and
`pins-turbo-q5-avx2-research.json` selects quantized turbo. Both retain the exact
ten utterances and two threads. The binary is 19,153,728 bytes, SHA-256
`e7d5de68cc8fc610c3c961c47f879451db9bee4a2df152e9a66f1078072e7f28`.
Upstream's v1.1.0 `Dockerfile.build` uses `target-cpu=haswell` and disables
GGML native tuning, AVX512, GFNI and AVXVNNI; its release workflow verifies the
x86-64-v3 ISA floor. Keep CPU variant explicit in measurement reports rather
than labelling an AVX2 run as the baseline. Comparing model and CPU changes in
separate runs helps attribute accuracy and speed differences.

An eventual production selector should use the intersection of Linux CPU flag
tokens across processors: AVX, AVX2, FMA, F16C, BMI1, BMI2, MOVBE, POPCNT, XSAVE
and LZCNT (Linux commonly calls it `abm`). Linux's exposed AVX flag reflects
available OS AVX state; literal `osxsave` is not present on all suitable kernels.
Retain the v2 baseline, and handle a genuine optimized CPU SIGILL with explicit
baseline retry. None of these research manifests changes production selection.
