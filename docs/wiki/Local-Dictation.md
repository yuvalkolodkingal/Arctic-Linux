# Local dictation

Arctic integrates the official [VoxType](https://github.com/peteonrails/voxtype)
**1.1.1** daemon with a local multilingual Whisper model. It supports Hebrew and
English. Audio is processed on your computer.

## Installation and readiness

The live image contains Arctic's setup, Settings and status integration. The
VoxType executable and model weights stay out of the ISO.

- **Online installation** downloads and verifies one CPU binary and one model
  in a bounded, nonfatal setup attempt.
- **Offline installation** saves a first-boot queue. Connect after installation;
  the background timer retries without delaying login.
- **Settings → Dictation** shows queued, downloading, ready and error states.
  **Set up / retry…** or **Verify / repair setup…** requests administrator
  authorization and safely resumes a partial download.

| Selected CPU path | Fixed app + model download |
|---|---:|
| Baseline + Whisper Small | 506,440,871 bytes (506.4 MB) |
| AVX2 + Whisper Large v3 Turbo Q5 | 593,457,131 bytes (593.5 MB) |

The modern path is used only after a conservative CPU capability check. Missing
system packages add to these totals. Optional Vulkan acceleration is a separate
**66,575,872-byte (66.6 MB)** download. Setup verifies upstream signatures,
exact sizes and SHA-256 hashes before publishing any file as ready.

When an existing Arctic system updates from VoxType 1.1.0, its verified model,
selected profile and receipt-bound user are retained. The new 1.1.1 executable downloads through
the same retryable queue; the previous payload remains intact until the new
binary, model and configuration verify and the direct receipt and marker are
durable. The exact official 1.1.0 binary remains usable while Settings shows
that its update is pending; the launcher switches versions only when the new
receipt is published. A restart during the update resumes from that queue. Vulkan is
re-enabled only after the 1.1.1 Vulkan binary passes its local model check.
If the old receipt is damaged, the offline attempt preserves it and the payload;
the next online retry quarantines that receipt and performs a signed repair.
The setup timer also recreates a missing queue after an interrupted package
transaction. An old payload that fails its strict hash check is never launched.

## Record and insert

1. Focus the text field where the words should go.
2. Press **`Super + Ctrl + X`** to begin recording.
3. Speak, then press the same keys to stop, transcribe and insert.
4. Press **`Super + Ctrl + Backspace`** to cancel without inserting.

Mango runs the transcript-free `arctic-dictation-toggle` readiness helper,
which invokes `voxtype record toggle` only when setup is ready. Cancel invokes
`voxtype record cancel` directly.
VoxType inserts through `wtype`; Arctic does not enable VoxType's input-device
hotkey listener. The recording/transcribing indicator remains visible while the
taskbar hides. Locking cancels active work and stops the daemon until unlock.

The 60-second recording limit stops and transcribes what was captured. There is
no Arctic 240-second transcription timeout in the direct integration.

Choose **Detect language**, **Hebrew · עברית**, or **English** in Settings.
Constrained detection and transcription both run locally.

## Acceleration and recovery

CPU is selected after initial setup. Vulkan can be enabled explicitly on
supported hardware; setup first runs a real local model check. If Vulkan later
fails during inference, VoxType does not guarantee an automatic CPU retry. The
failed phrase is not retranscribed: open **Settings → Dictation**, select
**CPU**, and record again.

The official Vulkan binary can load its model on CPU when no render node is
available after its startup wait; upstream has no option to require GPU use.
Arctic reports that fallback as an error instead of accepting it as Vulkan
acceleration. Select CPU explicitly, or repair the driver and enable Vulkan
again.

The setup check requires VoxType's observed post-initialization Vulkan marker.
An exit code of zero or a message saying GPU use was requested is insufficient;
fallback, contradictory and unknown results keep CPU selected. The generated
silence transcript is discarded. Setup parses a bounded private stderr stream
only for the official acceleration outcome and does not save or display it.

| Problem | What to do |
|---|---|
| Setup is queued or a file is missing | Connect and choose **Set up / retry…**. |
| Microphone cannot open | Select and unmute the input in **Settings → Sound**, then try again. |
| Vulkan fails | Select **CPU**, then make a new recording. |
| Text is not inserted | Focus a writable field and retry; the app may reject Wayland virtual-keyboard input. |
| VoxType service is stopped | Open Dictation settings and repair or restart setup. |

Models load on demand when recording begins and unload after transcription.
This saves idle RAM and VRAM, with a short delay when a recording starts.

## Privacy

Arctic fixes VoxType to local Whisper mode, disables remote inference, upstream
hotkey listening, transcript notifications, clipboard fallback, auto-submit and
transcript post-processing. The user service runs with error-only logging and
clears inherited settings that could change this policy. The status shown by
Arctic contains fixed state and error text, never speech or a transcript.

The service can use only local Unix sockets for Wayland and PipeWire. Internet
sockets remain blocked even if the user configuration or post-processing
command is changed.

The final release qualification still audits the exact image's journal and
notifications. A source configuration is not proof that every runtime path is
free of transcript excerpts.

## Commands and files

```sh
arctic-dictation status
arctic-dictation retry
arctic-dictation set-language he        # auto, he or en
arctic-dictation set-backend cpu        # cpu or vulkan
voxtype record toggle
voxtype record cancel
voxtype status
```

The managed user config is `~/.config/voxtype/config.toml`; native runtime state
is `$XDG_RUNTIME_DIR/voxtype/state`. Verified binaries and models are under
`/opt/arctic/voxtype`, with setup state and a public verification receipt under
`/var/lib/arctic/dictation`.

See [the pinned files and implementation details](https://github.com/yuvalkolodkingal/Arctic-Linux/blob/main/docs/DICTATION.md)
and the [official VoxType documentation](https://voxtype.io/docs/).

## What has been measured

[Exact-image run 38699057684](https://github.com/yuvalkolodkingal/Arctic-Linux/actions/runs/38699057684)
tested official VoxType 1.1.1 on both CPU profiles. It used the first five public
FLEURS rows for each language, with explicit language selection and no retries.
The English fixture contains 103 reference words and 40.86 seconds of audio; the
Hebrew fixture contains 100 reference words and 59.82 seconds.

| CPU profile | English WER | English CER | Hebrew WER | Hebrew CER | Median elapsed, EN / HE |
|---|---:|---:|---:|---:|---:|
| Small v2 | 8/103 (7.77%) | 12/469 (2.56%) | 41/100 (41.0%) | 56/476 (11.76%) | 76.573 s / 84.000 s |
| Turbo Q5 v3 | 7/103 (6.80%) | 12/469 (2.56%) | 21/100 (21.0%) | 27/476 (5.67%) | 37.260 s / 40.574 s |

Elapsed time runs from recording through insertion, so it includes the clip's
own duration and insertion overhead as well as local transcription. These are
virtual-source public read-speech results from a small fixed sample. They do not
establish general accuracy, Whisper parity, mixed-language behavior, physical-
microphone performance, GPU acceleration or speed on your hardware.

The CPU transcription and insertion sublane is complete. The run created both
target disks but stopped during the online-installed microphone fixture, before
an offline-installed recovery report was emitted. The broader v1.2.1 dictation
record still requires online and offline setup recovery, CPU recovery after a
controlled Vulkan failure, missing models, physical microphone failure,
cancellation, locking and transcript-leakage checks:

| Exact-image field | Result |
|---|---|
| Small v2 CPU transcription and insertion | **Passed run 38699057684; measurements above** |
| Turbo Q5 v3 CPU transcription and insertion | **Passed run 38699057684; measurements above** |
| Online setup and offline first-boot recovery | **Pending final qualification** |
| Controlled Vulkan failure and explicit CPU recovery | **Pending final qualification** |
| Physical microphone failure and cancellation | **Pending final qualification** |
| Log, notification and status privacy audit | **Pending final qualification** |

An older candidate VM run measured online/offline paths through the retired
Arctic runtime controller. Its service, installer, cancellation, GPU recovery
and privacy results cannot qualify the direct official VoxType integration.
