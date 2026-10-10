# Local dictation

Arctic uses [Voxtype](https://github.com/peteonrails/voxtype) 1.1.0 with local
Whisper inference. The fixed hardware profiles select multilingual `small` on
legacy/unknown x86-64 CPUs and `large-v3-turbo-q5_0` on validated x86-64-v3 CPUs.
Hebrew and English are supported; automatic language selection is constrained to
these two languages.
The controller does not send audio to a service. Accuracy and hardware support
must be reported from measured native tests; source tests establish neither
Whisper accuracy parity nor a qualified ISO.

## Installation and readiness

The live ISO ships the small Arctic controller, settings integration and setup
service and timer. It contains neither the Voxtype executable payload nor model weights.
During an online OS installation, the target system gets a bounded setup attempt.
An offline installation persists a first-boot queue. A dependency, network or
model failure does not fail the OS installation, and the Done screen tells you
that dictation is not ready.

First-boot setup runs in the background when its queue exists, approximately
90–120 seconds after boot, and retries a failure about every 15 minutes. It does
not add an online-network wait to the graphical boot path. Open **Settings → Dictation** to see readiness,
download progress and actionable errors. **Retry setup** asks for administrator
authorization and resumes setup; it also enables reboot recovery for systems
that received dictation through an update. Readiness requires verified payload
files, executable text-insertion tools, the PipeWire ALSA plugin and configuration,
and, for the accelerated profile, the Vulkan loader. Ready means these dependencies are installed; the first
recording can still expose a microphone, GPU or application insertion problem.

The **Small compatibility profile** downloads **506,181,191 bytes** (506.2 MB):
CPU baseline and one multilingual Small model. The **Turbo hardware profile**
downloads **678,117,115 bytes** (678.1 MB): optimized AVX2 CPU, Vulkan, a retained
CPU baseline executable and one multilingual Turbo Q5 model. Both models are
never downloaded by a single setup attempt. These are fixed file totals; missing
system packages require additional downloads.

| File | Bytes | SHA-256 |
|---|---:|---|
| Voxtype CPU baseline | 18,579,224 | `1c9d78b4f6805e4f12ba3670949d3c22788269bdbc54215afffa42cafd0b4a7a` |
| Voxtype CPU AVX2 | 19,153,728 | `e7d5de68cc8fc610c3c961c47f879451db9bee4a2df152e9a66f1078072e7f28` |
| Voxtype Vulkan | 66,342,968 | `db2c7938392ff08ec8b50b8afb90f8bd3d0111eccf5943df2f51c40a0368fec2` |
| Whisper multilingual Small | 487,601,967 | `1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b` |
| Whisper multilingual Turbo Q5 | 574,041,195 | `394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2` |

Both profiles require `pipewire-alsa`, `wtype` and `wl-clipboard`. Turbo additionally
requires `vulkan-loader` and `mesa-vulkan-drivers`. Mesa provides an Intel/AMD Vulkan
ICD; existing proprietary drivers are retained. Executables come from the upstream
v1.1.0 release (source commit `e2638ca63f566f1682bcedc0abea8e4b25211c21`). Small
comes from immutable Whisper.cpp model revision
`80da2d8bfee42b0e836fc3a9890373e5defc00a6`; Turbo Q5 comes from
`98aa99a0a9db05ae2342309f5096248665f7cba3`.

All downloads require HTTPS, exact byte counts and complete SHA-256 verification
before publication. A partial download can resume; a failed hash cannot become
an installed engine or model. Files live under `/opt/arctic/voxtype/1.1.0`, owned
by root, with a verification receipt in `/var/lib/arctic/dictation/verified.json`.
The receipt binds the exact profile, model, fixed descriptor and verified files.
A profile switch keeps the former receipt and model until its replacement is
verified and required dependencies are present; it then removes only the old
model identified by its previous trusted receipt. Temporary disk use can include
both models while replacing one.

## Recording

Focus the text field where the phrase belongs. Press **Super + Ctrl + X** to
start, speak, then press the same shortcut to stop and insert. The recording and
transcribing indicator remains visible when the taskbar hides. Press
**Super + Ctrl + BackSpace** to cancel; cancellation discards the result.
Stopping explicitly is required for insertion. An unattended recording reaches
its 60-second cap and is discarded. Transcription has a 240-second timeout;
phrases that exceed it are discarded with an actionable error.

Choose automatic, Hebrew or English in Settings. Automatic acceleration uses
Vulkan for the Turbo profile when a render device is present; its CPU path uses
the pinned AVX2 executable. The Small profile uses the CPU baseline supporting
x86-64-v2 and does not require Vulkan. Detection intersects exact AVX2, FMA,
F16C, BMI1/2, MOVBE, POPCNT, XSAVE and LZCNT/ABM flags across all processors;
unknown or incomplete flags select Small.

A GPU initialization or transcription failure selects the profile's CPU for the
session and asks you to **record again**. CPU can also be selected directly.
An optimized CPU illegal-instruction failure discards the phrase and offers
**Small compatibility setup** in Settings. This administrator-authorized action
persists the fixed Small profile and downloads its model; it does not retry
Turbo on the baseline executable because that path exceeded the inference limit
in the measured pilot. **Retry setup** retains the selected profile. **Use
recommended profile** explicitly returns to hardware selection. Profile changes
show the pinned bytes and require consent; no failure automatically downloads a
model or retranscribes recorded audio. A microphone failure
points to Sound settings; an insertion failure asks you to focus a text field and
record again. Text insertion uses Wayland `wtype`; it may fail in an application
that does not accept the compositor's virtual keyboard. No broad input-device
access or evdev hotkey listener is granted.

## Privacy and locking

Upstream info logs and default transcription notifications can reveal text.
Arctic explicitly sets `RUST_LOG=error`, disables transcription notifications,
remote/streaming inference and hotkey listening, and discards raw engine output.
Optional spoken punctuation, filler removal and smart submit processing are
disabled, matching the accuracy harness's text-processing settings.
Status JSON and error notices contain no transcript. The only transcript is in
the user's private runtime directory, with mode 0600, and is removed after
insertion, cancellation or dead-controller recovery. The protocol's final newline
is removed before typing, so completing a phrase does not press Enter.

Owned engine and insertion children have a parent-death guard. Cancelling kills
the owned process groups, including in-flight inference. Locking first creates a
private lock marker and cancellation generation without waiting for transcription
shutdown. Startup and insertion check that generation and the session lock. An
unknown lock probe fails closed. The shell clears its marker only after successful
unlock; the fallback supervisor waits for a normal swaylock exit and preserves the
marker after a crash. If lock state cannot be established after a shell crash,
restart the graphical session before recording again.

## Controller and validation contract

The [2026-10-09 Fedora 44 container measurement](evidence/dictation/fedora44-small-cpu-20261009.json)
completed ten actual CPU transcriptions with networking unavailable, using the
pinned runtime and small model. The first five test recordings in file order
from each FLEURS language were selected before inference:

| Language | Reference words | Word edits / WER | Character edits / CER |
|---|---:|---:|---:|
| English | 103 | 8 / 7.8% | 13 / 2.8% |
| Hebrew | 100 | 42 / 42.0% | 58 / 12.2% |

These short read-speech samples do not establish general accuracy or equivalence
with another Whisper implementation. Language was explicitly selected, and the
normalization ignores punctuation and Hebrew vowel/cantillation marks. With two
CPU threads and a fresh process for each recording, English took 399.8 seconds
for 40.86 seconds of audio; Hebrew took 465.4 seconds for 59.82 seconds of audio.
Timing includes model initialization and applies to this host. This report tests
file inference rather than microphones, GPU recovery or insertion in the ISO.
The same ten fixed recordings were then measured with
[Turbo Q5 on AVX2](evidence/dictation/fedora44-turbo-q5-avx2-cpu-20261009.json).
English WER remained 8/103 (7.8%), with CER 11/469 (2.3%). Hebrew improved to WER
23/100 (23.0%) and CER 34/476 (7.1%). Every clip completed within 240 seconds.
[Small on AVX2](evidence/dictation/fedora44-small-avx2-cpu-20261009.json) produced
the same scored hypotheses as the baseline Small run. Timings from these
concurrent host runs are preliminary and do not demonstrate a general speedup.
The [portable Turbo pilot](evidence/dictation/fedora44-turbo-q5-baseline-stopped-pilot-20261009.json)
was stopped after over 31 minutes: its first three completed clips took 818.0,
496.5 and 578.8 seconds, exceeding the controller's inference limit. This supports
retaining Small for the legacy/unknown hardware profile. The limited corpus does
not establish Whisper parity, general dictation accuracy or exact-image readiness.

`arctic-dictation` accepts `status`, `settings`, `start`, `stop`, `toggle`,
`cancel`, `setup`/`retry`, `compatibility-setup`, `recommended-setup`,
`set-language auto|he|en`, and
`set-backend auto|cpu|vulkan`. Shell locking additionally uses `lock`, `unlock`
and `lock-fallback`. Each public command emits one status JSON object, never
speech. The atomic snapshot is `$XDG_RUNTIME_DIR/arctic/dictation.json`; IPC is
a mode-0600 Unix socket checked with same-user peer credentials. Status contains the selected and recommended fixed profile descriptors, byte
counts, readiness, progress and sanitized errors. It never contains audio or text.
Model downloads are a fixed administrator-authorized operation. The privileged
helper accepts no arguments or the fixed `--compatibility`/`--recommended`
selection; it cannot accept arbitrary models, URLs, paths or commands.

CI and RPM `%check` run `packaging/dictation/test_dictation.py`. These controls
cover integrity and resume failures, exact profile receipt binding, one-model
selection, conservative CPU detection, compatibility selection and serialized
profile switching, readiness, offline queue and serialized retry, cancellation before/during startup, owned process termination and parent
death, lock denial, GPU-to-CPU retry selection, microphone/control errors,
explicit-stop insertion, newline removal and transcript/log privacy. Installer
tests check online/offline calls, persisted queues and nonfatal failure notes.
Systemd CI verifies the setup service and timer.

Release qualification additionally requires real native CPU inference and
Hebrew/English metrics with disclosed corpus limits, GPU failure and CPU retry,
missing model and microphone, cancellation during inference, focused application
insertion, lock races, online installation and offline first-boot recovery in the
final image. Test reports must distinguish host/source controls, container inference
and exact-image tests; none substitutes for the others.
