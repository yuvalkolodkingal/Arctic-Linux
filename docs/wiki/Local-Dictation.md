# Local dictation

Arctic's dictation uses [Voxtype](https://github.com/peteonrails/voxtype) **1.1.0** and a
multilingual Whisper model on your computer. It supports **Hebrew and English**. Setup downloads
the software and model; your recordings are not sent to a transcription service.

## Installation and readiness

The replacement live image contains the small Arctic controller and its Settings integration,
while the Voxtype executable and large model weights stay out of the image.

- **Online installation** downloads and verifies the selected engine/model profile in a bounded
  setup attempt. A network, dependency or model failure does not fail the OS installation.
- **Offline installation** saves a first-boot setup queue. The Done screen says dictation is
  not ready; connect after booting the installed system to finish it.
- **First boot** retries queued setup in the background, initially about 90–120 seconds after
  boot and then about every 15 minutes after a failure. Login does not wait for the download.
- **Settings → Dictation** shows readiness, progress and the next action. **Set up / retry…**
  resumes setup; **Verify / repair setup…** checks a ready installation. Administrator
  authorization is required for software/model setup.

**Ready** requires the verified model and executables, audio dependencies and text-insertion
helpers. It does not promise that a particular microphone, GPU or text field will work.

| Hardware profile | Fixed file download | Model and processing |
|---|---:|---|
| **Small compatibility** | 506,181,191 bytes (506.2 MB) | Multilingual Whisper Small; baseline CPU executable (x86-64-v2) |
| **Turbo hardware profile** | 678,117,115 bytes (678.1 MB) | Multilingual Turbo Q5; AVX2 CPU and Vulkan, with a baseline executable retained |

Missing system packages add to those totals. Setup selects one model; it does not download both
in one attempt. A confirmation discloses the selected profile and download size. HTTPS, exact
byte counts and complete SHA-256 checks are required before installation. Partial files can
resume; an incomplete or mismatched file cannot become a ready model. A profile switch may
briefly need disk space for both the old and replacement model.

**Use compatibility model…** explicitly selects Small after a CPU compatibility problem.
**Use recommended model…** returns to the hardware-selected profile. These require approval in
the desktop's administrator dialog; a recording failure never downloads another model by itself.

## Record and insert

1. Focus the text field in the app where you want the words.
2. Press **`Super + Ctrl + X`** to start recording.
3. Speak, then press the same keys to stop and insert the transcription.
4. Press **`Super + Ctrl + Backspace`** to cancel recording or transcription without inserting.

The Recording/Transcribing indicator stays visible while the taskbar hides. With the bar visible,
right-click its dictation pill to cancel; Settings also has **Cancel**. Stopping explicitly is
required for insertion. A recording left running reaches its 60-second cap and is discarded.
A transcription taking longer than 240 seconds is discarded with an actionable error.

In Settings choose **Detect language**, **Hebrew · עברית**, or **English**. Choosing one language
can help with short phrases. Language detection and transcription both run locally.

## Acceleration and recovery

The Turbo profile can use **Vulkan** on supported hardware; **CPU** can be selected directly.
Small uses its baseline CPU executable. Automatic hardware selection checks the CPU's actual
features rather than assuming a new processor supports the optimized executable.

| Problem | What happens and what to do |
|---|---|
| **GPU initialization or inference fails** | That phrase is discarded. Arctic selects CPU for this session and asks you to record again explicitly; it does not retranscribe the failed recording. |
| **Optimized CPU is incompatible** | The phrase is discarded. Choose **Use compatibility model…**, review its size and finish setup, then record again. |
| **Model or dependency is missing** | Recording stays unavailable. Connect and use **Set up / retry…**. |
| **Microphone is unavailable or muted** | Select and unmute the input in **Settings → Sound**, then record again. |
| **Text cannot be inserted** | Focus a text field and try again. An app may reject Wayland virtual-keyboard insertion. |
| **The screen locks** | Recording/transcription is cancelled; no result is inserted into the locked session. |

Mango runs the shortcuts. Text insertion uses Wayland `wtype`; Arctic does not grant broad access
to input devices or use Voxtype's evdev hotkey listener.

## Privacy

Voxtype's info logging can contain transcript excerpts. Arctic sets `RUST_LOG=error`, disables
transcription notifications, remote/streaming inference and upstream hotkey listening, and
discards raw engine output. Status and error messages contain neither audio nor the transcript.
Private runtime text files use mode 0600 and are removed after insertion, cancellation or
recovery of a stopped controller. Completing a phrase does not press Enter automatically.

## What has been measured

[Candidate VM dictation tests](https://github.com/yuvalkolodkingal/Arctic-Linux/actions/runs/38134898087)
used five fixed public FLEURS recordings per language: **103 English reference words** and
**100 Hebrew reference words**. The online-install and offline-recovery runs measured:

| Model | English word error rate | Hebrew word error rate, online / recovery |
|---|---:|---:|
| Small | 8/103 (7.8%) | 41/100 (41%) / 43/100 (43%) |
| Turbo Q5 | 8/103 (7.8%) | 21/100 (21%) / 23/100 (23%) |

On the two-vCPU test guest, the five English recordings (40.86 seconds of audio) took about
**592–594 seconds with Small** or **367 seconds with Turbo**. The five Hebrew recordings
(59.82 seconds of audio) took about **641–643 seconds with Small** or **391–392 seconds with
Turbo**. Those totals include process/model startup and insertion; they are not pure inference
benchmarks or speed predictions for your computer.

The candidate exercised CPU inference, online setup, offline recovery, missing-model and
microphone failures, cancellation, insertion, and a controlled GPU failure followed by a new CPU
recording. Physical GPU acceleration and a real hardware microphone were not verified by that
VM run. The small read-speech corpus does not establish general accuracy or parity with another
Whisper implementation, and these candidate results do not qualify the new ISO for release.

## Commands and further details

```sh
arctic-dictation status
arctic-dictation set-language he        # auto, he or en
arctic-dictation set-backend cpu        # auto, cpu or vulkan, as supported by the profile
arctic-dictation toggle
arctic-dictation cancel
arctic-dictation retry                 # administrator authorization for setup
```

Each command emits status JSON, never speech. See [the pinned files and implementation details](https://github.com/yuvalkolodkingal/Arctic-Linux/blob/main/docs/DICTATION.md)
and [official Voxtype documentation](https://voxtype.io/docs/). Report hardware problems with the
selected profile/backend, sanitized status error, microphone/GPU details and the action that
failed. Share private recordings or transcripts only when you deliberately choose to do so.
