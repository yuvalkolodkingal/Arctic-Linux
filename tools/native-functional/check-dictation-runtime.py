#!/usr/bin/python3
"""Supplemental direct VoxType missing-microphone probe, never ISO qualification.

Run in an isolated Fedora container with no audio devices or session sockets.
Mount the selected official VoxType 1.1.0 binary and model at their production
paths. Raw runtime output remains private and is projected to fixed categories.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time


PINS = {
    "small-v2": {
        "binary": ("voxtype-baseline", 18579224,
                   "1c9d78b4f6805e4f12ba3670949d3c22788269bdbc54215afffa42cafd0b4a7a"),
        "model": ("ggml-small.bin", 487601967,
                  "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b"),
        "model_id": "small",
    },
    "turbo-q5-v3": {
        "binary": ("voxtype-avx2", 19153728,
                   "e7d5de68cc8fc610c3c961c47f879451db9bee4a2df152e9a66f1078072e7f28"),
        "model": ("ggml-large-v3-turbo-q5_0.bin", 574041195,
                  "394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2"),
        "model_id": "large-v3-turbo-q5_0",
    },
}
MICROPHONE_ERRORS = (
    b"Failed to start audio:", b"Failed to create audio capture:",
    b"no input device", b"No input device", b"microphone",
)


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def verify_file(path, pin, executable=False):
    path = Path(path)
    name, size, digest = pin
    if (path.name != name or not path.is_file() or path.is_symlink()
            or path.stat().st_size != size or sha256(path) != digest
            or (executable and not os.access(path, os.X_OK))):
        raise SystemExit("The pinned official VoxType payload failed verification.")


def config_text(model):
    return f'''engine = "whisper"
state_file = "auto"

[hotkey]
enabled = false

[audio]
device = "default"
sample_rate = 16000
max_duration_secs = 10

[whisper]
mode = "local"
model = "{model}"
language = ["he", "en"]
translate = false

[output]
mode = "type"
driver_order = ["wtype"]
fallback_to_clipboard = false

[output.notification]
on_recording_start = false
on_recording_stop = false
on_transcription = false
'''


class FixedErrorProjection:
    """Consume bounded private stderr and retain only a fixed Boolean."""
    def __init__(self, stream):
        self.stream = stream
        self.bytes = 0
        self.microphone = False
        self.overflow = False

    def run(self):
        tail = b""
        while True:
            chunk = os.read(self.stream.fileno(), 4096)
            if not chunk:
                return
            self.bytes += len(chunk)
            if self.bytes > 1024 * 1024:
                self.overflow = True
                return
            material = tail + chunk
            if any(needle in material for needle in MICROPHONE_ERRORS):
                self.microphone = True
            tail = material[-128:]


def wait_for(predicate, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.025)
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=tuple(PINS), required=True)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    profile = PINS[args.profile]
    binary = args.binary or Path("/opt/arctic/voxtype/1.1.0") / profile["binary"][0]
    model = args.model or Path("/opt/arctic/voxtype/models") / profile["model"][0]
    verify_file(binary, profile["binary"], executable=True)
    verify_file(model, profile["model"])

    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    if Path("/dev/snd").exists() or any((runtime / name).exists()
                                       for name in ("pipewire-0", "pulse/native")):
        raise SystemExit("This negative probe requires a container with no audio session.")

    result = {
        "schema": 2, "qualification": "supplemental-direct-upstream-runtime",
        "voxtype_version": "1.1.0", "profile": args.profile,
        "binary_sha256": profile["binary"][2], "model": profile["model_id"],
        "model_sha256": profile["model"][2], "microphone": "intentionally-absent",
        "gpu_tested": False, "iso_tested": False, "transcript_published": False,
        "passed": False, "daemon_started": False, "microphone_error_observed": False,
    }
    begin = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="arctic-microphone-negative-") as directory:
        root = Path(directory)
        home, xdg_config, xdg_runtime = root / "home", root / "config", root / "runtime"
        for path in (home, xdg_config / "voxtype", xdg_runtime):
            path.mkdir(parents=True, mode=0o700)
        config = xdg_config / "voxtype/config.toml"
        config.write_text(config_text(model))
        config.chmod(0o600)
        env = {
            "HOME": str(home), "XDG_CONFIG_HOME": str(xdg_config),
            "XDG_RUNTIME_DIR": str(xdg_runtime),
            "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
        }
        process = subprocess.Popen(
            [str(binary), "-q", "--config", str(config), "daemon"], env=env,
            start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        projection = FixedErrorProjection(process.stderr)
        reader = threading.Thread(target=projection.run, daemon=True)
        reader.start()
        state = xdg_runtime / "voxtype/state"
        try:
            result["daemon_started"] = wait_for(
                lambda: process.poll() is None and state.is_file(), 8)
            if result["daemon_started"]:
                control = subprocess.run(
                    [str(binary), "-q", "--config", str(config), "record", "start"],
                    env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=5)
                result["record_start_returncode"] = control.returncode
                wait_for(lambda: projection.microphone or projection.overflow
                         or process.poll() is not None, 8)
            result["microphone_error_observed"] = projection.microphone
            result["passed"] = projection.microphone and not projection.overflow
            result["error_category"] = (
                "microphone" if projection.microphone else
                "private-output-overflow" if projection.overflow else
                "missing-microphone-error-not-observed")
        except (OSError, subprocess.TimeoutExpired):
            result["error_category"] = "runtime-control-failed"
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=3)
            reader.join(timeout=2)
            result["owned_engine_terminated"] = process.poll() is not None
            result["private_transcript_files_erased"] = not any(
                path.name.startswith(("transcript", ".transcript"))
                for path in (xdg_runtime / "voxtype").glob("*"))
    result["elapsed_seconds"] = round(time.monotonic() - begin, 3)
    result["limitations"] = [
        "No real microphone was present; this checks a genuine runtime failure.",
        "No Vulkan device, text insertion, accuracy or exact-image installation was tested.",
    ]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0 if (result["passed"] and result["owned_engine_terminated"]
                 and result["private_transcript_files_erased"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
