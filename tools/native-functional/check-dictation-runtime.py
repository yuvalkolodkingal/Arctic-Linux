#!/usr/bin/python3
"""Supplemental real Voxtype missing-microphone probe, never ISO qualification.

Run in an isolated Fedora container with no audio devices/session sockets. Mount
verified CPU/model files at the production /opt/arctic/voxtype/1.1.0 paths. This
script records no real user's microphone and publishes no raw engine output.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controller", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("arctic_dictation", args.controller)
    controller = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(controller)
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    if Path("/dev/snd").exists() or any((runtime / name).exists() for name in ("pipewire-0", "pulse/native")):
        raise SystemExit("This negative probe requires a container with no microphone/audio session.")
    for key in ("cpu", "model"):
        name, _url, size, digest = controller.ASSETS[key]
        path = controller.PAYLOAD / name
        if path.stat().st_size != size or controller.sha256(path) != digest:
            raise SystemExit("The pinned CPU/model files failed byte/SHA verification.")
    result = {"schema": 1, "qualification": "supplemental-container-runtime",
              "voxtype_version": controller.VERSION, "engine": "real-pinned-cpu",
              "model": "small-multilingual", "microphone": "intentionally-absent",
              "gpu_tested": False, "iso_tested": False, "transcript_published": False,
              "passed": False, "daemon_started": False, "microphone_error_observed": False}
    begin = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="arctic-microphone-negative-") as directory:
        shared = Path(directory)
        private = shared / "dictation"
        private.mkdir(mode=0o700)
        broker = controller.Broker(shared, private)
        config = private / "config.toml"
        config.write_text(controller.voxtype_config(private, "auto"))
        config.chmod(0o600)
        env = controller.child_environment(private)
        binary = str(controller.PAYLOAD / controller.ASSETS["cpu"][0])
        # Same parent-death exec guard as the installed controller. This is an
        # actual engine invocation, not a fake model/audio/daemon implementation.
        process = subprocess.Popen(["/usr/bin/python3", "-I", str(args.controller.with_name("child_exec.py")),
                                    str(os.getpid()), binary, "--quiet", "--config", str(config), "daemon"],
                                   env=env, start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        broker.process = process
        readers = [threading.Thread(target=broker.drain, args=(stream, process), daemon=True)
                   for stream in (process.stdout, process.stderr)]
        for reader in readers:
            reader.start()
        try:
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline and process.poll() is None and not broker.failure:
                if (private / "voxtype-state").exists():
                    result["daemon_started"] = True
                    break
                time.sleep(0.025)
            if result["daemon_started"]:
                control = subprocess.run([binary, "--quiet", "--config", str(config), "record", "start"],
                                         env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                result["record_start_returncode"] = control.returncode
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline and not broker.failure and process.poll() is None:
                    time.sleep(0.025)
            result["microphone_error_observed"] = broker.failure == "microphone"
            result["passed"] = result["microphone_error_observed"]
            result["error_category"] = broker.failure or "missing-microphone-error-not-observed"
        except (OSError, subprocess.TimeoutExpired):
            result["error_category"] = "runtime-control-failed"
        finally:
            broker.terminate()
            for reader in readers:
                reader.join(timeout=2)
            result["owned_engine_terminated"] = process.poll() is not None
            result["private_transcript_files_erased"] = not any(private.glob("*transcript*"))
    result["elapsed_seconds"] = round(time.monotonic() - begin, 3)
    result["limitations"] = ["No real microphone was present; this checks a genuine runtime failure.",
                             "No Vulkan device, text insertion, accuracy or exact-image installation was tested."]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    return 0 if result["passed"] and result["owned_engine_terminated"] and result["private_transcript_files_erased"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
