# Local dictation

Arctic uses [Voxtype](https://github.com/peteonrails/voxtype) 1.1.0 with local
Whisper inference and the multilingual `small` model. Hebrew and English are
supported; automatic language selection is constrained to these two languages.
The controller does not send audio to a service. Accuracy and hardware support
must be reported from measured native tests; source tests establish neither
Whisper accuracy parity nor a qualified ISO.

## Installation and readiness

The live ISO ships the small Arctic controller, settings integration and setup
service. It contains neither the Voxtype executable payload nor model weights.
During an online OS installation, the target system gets a bounded setup attempt.
An offline installation persists a first-boot queue. A dependency, network or
model failure does not fail the OS installation, and the Done screen tells you
that dictation is not ready.

First-boot setup runs in the background when its queue exists and retries a
failure every 15 minutes. Open **Settings → Dictation** to see readiness,
download progress and actionable errors. **Retry setup** asks for administrator
authorization and resumes setup; it also enables reboot recovery for systems
that received dictation through an update. Readiness requires verified payload
files, executable text-insertion tools, the PipeWire ALSA plugin and configuration,
and the Vulkan loader. Ready means these dependencies are installed; the first
recording can still expose a microphone, GPU or application insertion problem.

The pinned downloads total **572,524,159 bytes** (about 572.5 MB):

| File | Bytes | SHA-256 |
|---|---:|---|
| Voxtype CPU baseline | 18,579,224 | `1c9d78b4f6805e4f12ba3670949d3c22788269bdbc54215afffa42cafd0b4a7a` |
| Voxtype Vulkan | 66,342,968 | `db2c7938392ff08ec8b50b8afb90f8bd3d0111eccf5943df2f51c40a0368fec2` |
| Whisper multilingual small | 487,601,967 | `1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b` |

Missing system packages add to this download: `pipewire-alsa`, `wtype`,
`wl-clipboard`, `vulkan-loader` and `mesa-vulkan-drivers`. Mesa provides an Intel/
AMD Vulkan ICD; existing proprietary drivers are retained. Executables come from
the upstream v1.1.0 release (source commit
`e2638ca63f566f1682bcedc0abea8e4b25211c21`), and the model comes from immutable
Whisper.cpp model revision `80da2d8bfee42b0e836fc3a9890373e5defc00a6`.
All downloads require HTTPS, exact byte counts and complete SHA-256 verification
before publication. A partial download can resume; a failed hash cannot become
an installed engine or model. Files live under `/opt/arctic/voxtype/1.1.0`, owned
by root, with a verification receipt in `/var/lib/arctic/dictation/verified.json`.

## Recording

Focus the text field where the phrase belongs. Press **Super + Ctrl + X** to
start, speak, then press the same shortcut to stop and insert. The recording and
transcribing indicator remains visible when the taskbar hides. Press
**Super + Ctrl + BackSpace** to cancel; cancellation discards the result.
Stopping explicitly is required for insertion. An unattended recording reaches
its 60-second cap and is discarded. Transcription has a bounded timeout.

Choose automatic, Hebrew or English in Settings. Automatic acceleration uses
Vulkan on eligible x86-64-v3 machines with a render device; the CPU baseline
supports x86-64-v2. A GPU initialization or transcription failure selects CPU
for the session and asks you to **record again**. It does not promise an automatic
retry of the same audio. CPU can also be selected directly. A microphone failure
points to Sound settings; an insertion failure asks you to focus a text field and
record again. Text insertion uses Wayland `wtype`; it may fail in an application
that does not accept the compositor's virtual keyboard. No broad input-device
access or evdev hotkey listener is granted.

## Privacy and locking

Upstream info logs and default transcription notifications can reveal text.
Arctic explicitly sets `RUST_LOG=error`, disables transcription notifications,
remote/streaming inference and hotkey listening, and discards raw engine output.
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

`arctic-dictation` accepts `status`, `settings`, `start`, `stop`, `toggle`,
`cancel`, `setup`/`retry`, `set-language auto|he|en`, and
`set-backend auto|cpu|vulkan`. Shell locking additionally uses `lock`, `unlock`
and `lock-fallback`. Each public command emits one status JSON object, never
speech. The atomic snapshot is `$XDG_RUNTIME_DIR/arctic/dictation.json`; IPC is
a mode-0600 Unix socket checked with same-user peer credentials. Model downloads
are a fixed administrator-authorized operation, not arbitrary privileged commands.

CI and RPM `%check` run `packaging/dictation/test_dictation.py`. These controls
cover integrity and resume failures, readiness, offline queue and serialized
retry, cancellation before/during startup, owned process termination and parent
death, lock denial, GPU-to-CPU retry selection, microphone/control errors,
explicit-stop insertion, newline removal and transcript/log privacy. Installer
tests check online/offline calls, persisted queues and nonfatal failure notes.
Systemd CI verifies the setup unit.

Release qualification additionally requires real native CPU inference and
Hebrew/English metrics with disclosed corpus limits, GPU failure and CPU retry,
missing model and microphone, cancellation during inference, focused application
insertion, lock races, online installation and offline first-boot recovery in the
final image. Test reports must distinguish host/source controls, container inference
and exact-image tests; none substitutes for the others.
