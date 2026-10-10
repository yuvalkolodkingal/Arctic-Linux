# Supplemental local dictation measurements

These reports measure Voxtype 1.1.0 in a Fedora 44 container with glibc 2.43 and
network disabled. They do not qualify an ISO, GPU support, microphone capture,
Wayland insertion, installation, or general Whisper accuracy parity. Audio,
reference text, and transcripts are not published here.

Each accuracy run uses exactly the same first five English and five Hebrew test
rows from the pinned FLEURS corpus, with explicit language selection and two CPU
threads. Every clip starts a fresh process and includes model initialization.
The reports bind the corpus, audio, model, binary, configuration and harness by
checksum and disclose text normalization. Punctuation and Hebrew vowel marks
are ignored; Hebrew final letters remain distinct.

| CPU binary / multilingual model | English WER / CER | Hebrew WER / CER | Result |
|---|---:|---:|---|
| Portable baseline / Small | 7.77% / 2.77% | 42.00% / 12.18% | 10/10 clips completed |
| AVX2 / Small | 7.77% / 2.77% | 42.00% / 12.18% | 10/10; identical hypotheses to baseline |
| AVX2 / Turbo Q5_0 | 7.77% / 2.35% | 23.00% / 7.14% | 10/10 clips completed |

The Turbo Q5_0 run took 480.04 seconds for 40.86 seconds of English audio and
351.29 seconds for 59.82 seconds of Hebrew audio; its longest clip took 126.70
seconds. Other evaluations shared the host during these runs, so elapsed times
are preliminary and do not establish a causal speed improvement. A portable
baseline Turbo pilot was stopped after approximately 31 minutes with only three
of ten clips complete. Those clips took 817.97, 496.49 and 578.82 seconds, each
exceeding the controller's 240-second transcription bound. Its failed partial
report supports keeping Small on legacy CPUs; it provides no complete accuracy
measurement for portable Turbo.

The genuine missing-microphone trial started the pinned portable daemon and
model without an audio device/session. It observed the microphone error,
terminated the owned engine, and erased its private files. This verifies that
specific container failure path only.

Final-image acceptance still needs online setup, offline queue and recovery,
actual recording, Hebrew/English insertion, cancellation and locking, missing
models and microphones, and a failed GPU attempt followed by an explicit CPU
retry. Source and container reports cannot replace those tests.
