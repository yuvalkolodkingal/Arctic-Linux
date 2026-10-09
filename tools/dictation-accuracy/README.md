# Dictation accuracy research

This lane measures real local transcription through the pinned Voxtype 1.1.0
CPU baseline and multilingual Whisper small model. It is research evidence,
not ISO qualification. It makes no Whisper parity claim and imposes no invented
accuracy acceptance threshold.

`pins.json` records the immutable official `google/fleurs` dataset commit,
reviewed parquet sizes and SHA-256 values, and runtime/model release pins.
Preparation downloads 872,007,231 bytes of dataset files and 506,181,191 bytes
of runtime/model payload. It verifies every complete download before use.
The first five rows of each English and Hebrew test file are selected in file
order. A bad row fails preparation; it never selects an easier replacement.
Preparation needs Python, pyarrow and soundfile. Measurement needs only Python
and the verified local runtime/model files.

The source recordings are decoded at their native mono 16 kHz PCM16 format and
written to WAV without resampling, denoising, clipping or trimming. The private
bundle contains ten WAVs, original references and a hashed fixture manifest.
The upstream read-speech dataset is licensed CC-BY-4.0. Attribution:
Google FLEURS, *FLEURS: Few-shot Learning Evaluation of Universal
Representations of Speech*, Conneau et al. (2022),
<https://huggingface.co/datasets/google/fleurs> and
<https://arxiv.org/abs/2205.12446>. Source commit:
`70bb2e84b976b7e960aa89f1c648e09c59f894dd`. Conversion to PCM16 WAV is the
only fixture change. Keep this attribution with any redistributed audio.

Run the **Dictation accuracy research** Actions workflow after the source
checks pass. It fetches the files, disables networking through a new network
namespace, and runs ten actual CPU transcriptions. In a prepared test host:

```sh
python3 tools/dictation-accuracy/accuracy.py prepare \
  --cache /tmp/fleurs-cache --bundle /tmp/fleurs-private --payload /tmp/voxtype-private
# Read fixture_manifest_sha256 from /tmp/fleurs-private/summary.json.
sudo unshare --net -- python3 tools/dictation-accuracy/accuracy.py measure \
  --bundle /tmp/fleurs-private --fixture-sha256 THE_PREPARED_MANIFEST_HASH \
  --binary /tmp/voxtype-private/voxtype-cpu --model /tmp/voxtype-private/ggml-small.bin \
  --output /tmp/accuracy-private --threads 2
```

The installed payload can instead be read from `/opt/arctic/voxtype/1.1.0/`.
The CPU baseline is intentional: a successful accelerated run does not prove
CPU fallback. GPU failure recovery, the microphone, cancel, recording status
and Hebrew/English insertion need separate installed-image tests.

Voxtype's file command prints a fixed header followed by the transcript, even
with `--quiet`. The parser verifies that exact pinned 1.1.0 header and audio
frame count, then scores only the transcript. `RUST_LOG=off` prevents upstream
info-level excerpts. Child stdout/stderr, references and generated configuration
remain in private files. The script prints only the report. Never upload the
private bundle, raw output directory or transcripts; the workflow exports only
`report.json`. Its tested stderr check looks for the hypothesis prefix and
does not claim to prove the absence of every possible log disclosure.

The `arctic-dictation-accuracy-v1` report has `status: passed` only after all ten
verified samples complete successfully. Each language includes reference word
and character counts, Levenshtein edit counts, micro-averaged WER and CER, total
audio duration and integer nanosecond elapsed time. WER may exceed 1.0 when
insertions exceed reference words. Normalization uses Unicode compatibility
normalization and case folding, removes Hebrew vowel/cantillation marks and
bidi controls, ignores punctuation, and retains Hebrew final-letter distinctions.
CER excludes spaces. The normalization definition appears in every report.

Each sample launches a fresh process, so wall time includes model initialization
and transcription. Runtime and real-time factor describe that host and those
short recordings, rather than interactive dictation latency. The report binds
the source files, fixture manifest, audio, references, hypothesis, binary,
model, configuration, harness and pins with hashes. It never embeds transcript
text. Five read-speech utterances per language are too few to establish general
accuracy, mixed-language behavior or equivalence with OpenAI Whisper.

Source checks:

```sh
python3 -m unittest discover -s tools/dictation-accuracy -p 'test_*.py'
```
