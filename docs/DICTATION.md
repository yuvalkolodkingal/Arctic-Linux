# Local dictation

Arctic integrates the official [VoxType](https://github.com/peteonrails/voxtype)
1.1.0 release (source commit
`e2638ca63f566f1682bcedc0abea8e4b25211c21`) with its local Whisper engine.
VoxType records, transcribes and inserts text; Arctic supplies installation,
safe defaults, compositor shortcuts, status presentation and lock integration.
Automatic language detection is constrained to Hebrew and English.

The executable payload and model weights are excluded from the live ISO. The
RPM contains only the setup/readiness adapter, a binary selector, the release
key, systemd units and desktop integration.

## Installation and readiness

An online OS installation makes a bounded, nonfatal setup attempt in the target
system. An offline installation writes a retryable queue. A download, integrity,
dependency or model failure never fails the OS installation. The background
timer first retries about 90–120 seconds after boot and then about every 15
minutes while the queue remains. Settings shows dictation as unavailable until
the selected executable and model have been verified.

Setup chooses one CPU path conservatively:

| CPU path | Official binary and model | Fixed download |
|---|---|---:|
| Compatibility | baseline binary and multilingual Whisper Small | 506,181,191 bytes (506.2 MB) |
| Modern | AVX2 binary and multilingual Whisper Large v3 Turbo Q5 | 593,194,923 bytes (593.2 MB) |

Missing RPM dependencies add to those totals. Vulkan is a later, explicit
choice in Settings and adds **66,342,968 bytes (66.3 MB)**. It is not included in
the initial modern CPU total. Enabling Vulkan runs `vulkaninfo` and a real local
model initialization before changing the selected backend. Failure leaves CPU
selected and records an actionable error.

| File | Bytes | SHA-256 |
|---|---:|---|
| VoxType CPU baseline | 18,579,224 | `1c9d78b4f6805e4f12ba3670949d3c22788269bdbc54215afffa42cafd0b4a7a` |
| VoxType CPU AVX2 | 19,153,728 | `e7d5de68cc8fc610c3c961c47f879451db9bee4a2df152e9a66f1078072e7f28` |
| VoxType Vulkan | 66,342,968 | `db2c7938392ff08ec8b50b8afb90f8bd3d0111eccf5943df2f51c40a0368fec2` |
| Whisper multilingual Small | 487,601,967 | `1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b` |
| Whisper multilingual Turbo Q5 | 574,041,195 | `394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2` |

The setup bootstrap pins the upstream signing fingerprint
`9CCF7915B750CAE8B095ED1AA3FC9F33FD209279`, verifies the signed release
manifest and binary signature, then checks the exact byte count and SHA-256 of
every binary. Models come from immutable Whisper.cpp revisions and receive the
same byte-count and SHA-256 checks. Downloads use root-owned resumable partial
files and are published atomically only after verification.

Installed binaries are under `/opt/arctic/voxtype/1.1.0`; models are under
`/opt/arctic/voxtype/models`. `/usr/bin/voxtype` selects the verified CPU or
Vulkan binary. Public setup state is under `/var/lib/arctic/dictation`:

- `pending`, `setup.state` and `setup.error` describe queued or failed setup;
- `verified.json` binds the installed version, source, binary, model, hashes and
  selected hardware path;
- `backend` records `cpu` or `vulkan`;
- `upstream-direct-v1` is published last and allows the user service to start.

The user configuration is `~/.config/voxtype/config.toml`. Setup makes a
one-time backup at `config.toml.pre-arctic-voxtype-v1`, then installs canonical
local-only defaults. The systemd user service runs the official daemon with
that file. VoxType writes its native state to `$XDG_RUNTIME_DIR/voxtype/state`.

## Recording and recovery

Mango invokes the official commands directly:

- `Super + Ctrl + X` runs `voxtype record toggle`;
- `Super + Ctrl + Backspace` runs `voxtype record cancel`.

Focus a writable text field before starting. The first shortcut begins
recording; pressing it again stops, transcribes and inserts through `wtype`.
Cancel discards an active recording or transcription without inserting. The
recording/transcribing indicator remains visible while the taskbar hides.
Locking cancels work and stops `voxtype.service`; a successful unlock starts the
service again.

VoxType's configured 60-second recording limit **stops and transcribes the
captured audio**. The direct integration does not add the former Arctic
controller's 240-second inference timeout. Runtime failures are projected into
fixed, transcript-free messages:

| Failure | Recovery |
|---|---|
| Model or binary missing/damaged | Dictation remains unready; run setup repair. |
| Microphone cannot open | Select and unmute an input in Sound, then record again. |
| Vulkan initialization or inference fails | The phrase is not retried automatically. Select CPU in Dictation settings, then make a new recording. |
| Text insertion fails | Focus a writable field and try again; some apps can reject Wayland virtual-keyboard input. |
| Service is stopped | Start or repair VoxType from Dictation settings. |

CPU is always the explicit recovery path after a Vulkan failure. Arctic does
not claim that upstream automatically falls back, does not retranscribe failed
audio, and does not download a different model in response to a runtime error.

The model is configured for on-demand loading. It loads when recording starts
and unloads after transcription, avoiding a permanently resident Small or
Turbo model at the cost of a short startup delay for each recording.

## Privacy

The managed configuration fixes `engine = "whisper"` and `whisper.mode =
"local"`, disables VoxType's evdev hotkey listener, OSD, transcript
notifications, clipboard fallback, auto-submit, spoken punctuation and filler
removal, and uses only `wtype` for insertion. Mango supplies shortcuts, so no
broad input-device access is granted. Audio is used by the local Whisper engine
and is not sent to a transcription service.

Upstream INFO logging can contain transcript excerpts. `voxtype.service` clears
inherited overrides that could change the engine, model, hotkey, output or
logging policy and starts VoxType with `-q` after removing `RUST_LOG`. Arctic's
status adapter reads only native state and fixed failure prefixes; it never
copies raw journal messages into the UI. Transcript notifications are disabled.
The final exact-image qualification must still inspect logs and notifications;
source configuration alone is not evidence that every runtime path is clean.

## Commands

The Arctic adapter manages setup and safe settings only:

```sh
arctic-dictation status
arctic-dictation retry
arctic-dictation set-language auto   # auto, he or en
arctic-dictation set-backend cpu     # cpu or vulkan
```

`status` returns one sanitized JSON object. Recording remains an upstream
operation:

```sh
voxtype status
voxtype record toggle
voxtype record cancel
systemctl --user status voxtype.service
```

The privileged setup helper accepts only fixed install/resume/retry/backend
operations. It cannot accept an arbitrary URL, model, path or command.

## Measured evidence and release gate

The supplemental Fedora 44 measurements under
[`docs/evidence/dictation/`](evidence/dictation/) used the pinned official
VoxType 1.1.0 binaries and fixed public FLEURS samples. Five English clips had
103 reference words; five Hebrew clips had 100 reference words:

| CPU binary / model | English WER | Hebrew WER |
|---|---:|---:|
| baseline / Small | 8/103 (7.8%) | 42/100 (42.0%) |
| AVX2 / Small | 8/103 (7.8%) | 42/100 (42.0%) |
| AVX2 / Turbo Q5 | 8/103 (7.8%) | 23/100 (23.0%) |

These are short read-speech samples with explicit language selection and
published normalization limits. They do not establish general accuracy,
Whisper parity, microphone quality or performance on another computer. Timing
included fresh model/process startup and some runs shared the host, so it is not
a general speed comparison.

The earlier candidate VM run
[38134898087](https://github.com/yuvalkolodkingal/Arctic-Linux/actions/runs/38134898087)
tested the retired Arctic runtime controller. Its audio hypotheses can inform
model choice, but its installer, service, cancellation, GPU recovery and log
results do **not** qualify this direct integration.

The direct VoxType image remains fail-closed until exact-image tests cover
online installation, offline recovery, Hebrew and English transcription, CPU
fallback after a controlled GPU failure, missing models, microphone failure,
cancellation, focused text insertion, locking, service recovery and transcript
leakage. Source checks and historical candidates do not qualify an ISO.
