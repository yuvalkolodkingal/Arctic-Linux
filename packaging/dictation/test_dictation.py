"""Failure and privacy contracts. These do not substitute for native audio tests."""
import hashlib
import copy
import fcntl
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location("dictation", Path(__file__).with_name("dictation.py"))
d = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(d)


class Response(io.BytesIO):
    def __init__(self, body, status=200, headers=None, url="https://example.invalid/pinned"):
        super().__init__(body)
        self.status, self.headers, self.url = status, headers or {}, url

    def geturl(self):
        return self.url


class Downloads(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dest = Path(self.tmp.name) / "test-model.bin"
        self.body = b"verified multilingual model fixture"
        self.asset = (self.dest.name, "https://example.invalid/pinned", len(self.body), hashlib.sha256(self.body).hexdigest())

    def fetch(self, body, **kwargs):
        d.download(self.asset, self.dest, time.monotonic() + 2, lambda count: None,
                   opener=lambda request, timeout: Response(body, **kwargs))

    def test_only_matching_bytes_are_published(self):
        self.fetch(self.body)
        self.assertEqual(self.dest.read_bytes(), self.body)
        self.assertEqual(self.dest.stat().st_mode & 0o777, 0o644)
        self.assertFalse(self.dest.with_name(self.dest.name + ".part").exists())

    def test_corruption_never_becomes_a_model(self):
        with self.assertRaisesRegex(d.Failure, "integrity"):
            self.fetch(b"x" * len(self.body))
        self.assertFalse(self.dest.exists())
        self.assertFalse(self.dest.with_name(self.dest.name + ".part").exists())

    def test_truncated_download_is_retryable(self):
        with self.assertRaisesRegex(d.Failure, "incomplete"):
            self.fetch(self.body[:7])
        self.assertFalse(self.dest.exists())
        self.assertEqual(self.dest.with_name(self.dest.name + ".part").read_bytes(), self.body[:7])

    def test_oversized_download_is_rejected(self):
        with self.assertRaisesRegex(d.Failure, "disclosed size"):
            self.fetch(self.body + b"extra")
        self.assertFalse(self.dest.exists())

    def test_https_cannot_downgrade_on_redirect(self):
        with self.assertRaisesRegex(d.Failure, "insecure"):
            self.fetch(self.body, url="http://example.invalid/model")
        self.assertFalse(self.dest.exists())

    def test_resumes_and_rehashes_entire_partial(self):
        part = self.dest.with_name(self.dest.name + ".part")
        part.write_bytes(self.body[:7])
        requests = []
        def open_partial(request, timeout):
            requests.append(request.get_header("Range"))
            return Response(self.body[7:], status=206, headers={"Content-Range": f"bytes 7-{len(self.body)-1}/{len(self.body)}"})
        with mock.patch.object(d, "trusted_file", side_effect=lambda path, size=None: path.is_file()):
            d.download(self.asset, self.dest, time.monotonic() + 2, lambda count: None, opener=open_partial)
        self.assertEqual(requests, ["bytes=7-"])
        self.assertEqual(self.dest.read_bytes(), self.body)

    def test_rejects_wrong_resume_offset(self):
        self.dest.with_name(self.dest.name + ".part").write_bytes(self.body[:7])
        with mock.patch.object(d, "trusted_file", side_effect=lambda path, size=None: path.is_file()):
            with self.assertRaisesRegex(d.Failure, "invalid partial"):
                self.fetch(self.body[7:], status=206, headers={"Content-Range": "bytes 0-3/4"})
        self.assertFalse(self.dest.exists())

    def test_complete_corrupt_partial_restarts(self):
        self.dest.with_name(self.dest.name + ".part").write_bytes(b"x" * len(self.body))
        with mock.patch.object(d, "trusted_file", side_effect=lambda path, size=None: path.is_file()):
            self.fetch(self.body)
        self.assertEqual(self.dest.read_bytes(), self.body)

    def test_deadline_prevents_unbounded_setup(self):
        with self.assertRaisesRegex(d.Failure, "timed out"):
            d.download(self.asset, self.dest, time.monotonic() - 1, lambda count: None,
                       opener=lambda *_a, **_k: self.fail("expired download opened network"))

    def test_symlink_partial_is_not_followed(self):
        victim = Path(self.tmp.name) / "victim"
        victim.write_bytes(b"keep")
        self.dest.with_name(self.dest.name + ".part").symlink_to(victim)
        with self.assertRaisesRegex(d.Failure, "unsafe"):
            self.fetch(self.body)
        self.assertEqual(victim.read_bytes(), b"keep")


class Setup(unittest.TestCase):
    def test_missing_audio_or_gpu_loader_library_prevents_readiness(self):
        with tempfile.TemporaryDirectory() as temporary:
            audio = Path(temporary) / "libasound_module_pcm_pipewire.so"
            loader = Path(temporary) / "libvulkan.so.1"
            executable = Path(temporary) / "wtype"
            executable.write_bytes(b"executable fixture")
            executable.chmod(0o755)
            audio.write_bytes(b"alsa fixture")
            loader.write_bytes(b"vulkan fixture")
            with mock.patch.object(d, "trusted_file", side_effect=lambda p: p.is_file()):
                self.assertTrue(d.dependencies_ready((audio, loader), (executable,)))
                audio.unlink()
                self.assertFalse(d.dependencies_ready((audio, loader), (executable,)))
                audio.write_bytes(b"alsa fixture")
                loader.unlink()
                self.assertFalse(d.dependencies_ready((audio, loader), (executable,)))

    def test_verified_payload_is_not_ready_when_runtime_dependency_is_removed(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            assets = {"cpu": ("cpu", "https://invalid/pin", 3, "f" * 64)}
            cpu = folder / "cpu"
            cpu.write_bytes(b"cpu")
            cpu.chmod(0o755)
            d.atomic_json(folder / "verified.json", {"version": d.VERSION, "files": {
                "cpu": {"sha256": "f" * 64, "size": 3, "mtime_ns": cpu.stat().st_mtime_ns}}})
            profile = {"id": "small-v2", "model": "small", "cpu_variant": "baseline", "assets": assets,
                       "dependencies": (), "libraries": ()}
            d.atomic_json(folder / "verified.json", {"version": d.VERSION, **d.profile_status({**profile, "assets": {**assets, "model": assets["cpu"]}}),
                "profile_sha256": d.profile_digest({**profile, "assets": {**assets, "model": assets["cpu"]}}), "files": {
                "cpu": {"sha256": "f" * 64, "size": 3, "mtime_ns": cpu.stat().st_mtime_ns},
                "model": {"sha256": "f" * 64, "size": 3, "mtime_ns": cpu.stat().st_mtime_ns}}})
            profile["assets"]["model"] = assets["cpu"]
            with mock.patch.object(d, "trusted_file", return_value=True), \
                    mock.patch.object(d, "dependencies_ready", return_value=False) as dependencies:
                self.assertFalse(d.ready(folder, folder, profile))
            dependencies.assert_called_once_with(profile=profile)

    def test_retry_does_not_reset_active_download_and_enables_reboot_recovery(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(d, "directory"), \
                mock.patch.object(d.subprocess, "run") as run:
            system = Path(temporary)
            d.atomic_json(system / "setup.json", {"state": "downloading", "progress": 0.75})
            fd = os.open(system / "setup.lock", os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                d.request_setup(system)
            finally:
                os.close(fd)
            self.assertEqual(d.read_json(system / "setup.json")["progress"], 0.75)
            commands = [c.args[0] for c in run.call_args_list]
            self.assertIn(["/usr/bin/systemctl", "enable", "--now", "arctic-dictation-setup.timer"], commands)
            self.assertIn(["/usr/bin/systemctl", "start", "--no-block", "arctic-dictation-setup.service"], commands)

    def test_offline_queue_never_attempts_network(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(d.os, "geteuid", return_value=0), \
                mock.patch.object(d, "directory"), mock.patch.object(d.subprocess, "run") as run:
            system = Path(temporary)
            self.assertFalse(d.system_setup(offline=True, system=system))
            run.assert_not_called()
            self.assertEqual(d.read_json(system / "setup.json")["state"], "queued")
            self.assertTrue((system / "pending.json").exists())
            self.assertFalse((system / "verified.json").exists())

    def test_dependency_failure_keeps_queue_and_sanitizes_status(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(d.os, "geteuid", return_value=0), \
                mock.patch.object(d, "directory"), mock.patch.object(d.subprocess, "run", side_effect=OSError("secret transcript must not appear")):
            system = Path(temporary) / "state"
            system.mkdir()
            payload = Path(temporary) / "payload" / "version"
            self.assertFalse(d.system_setup(system=system, payload=payload))
            state = d.read_json(system / "setup.json")
            self.assertEqual(state["state"], "queued")
            self.assertNotIn("secret transcript", json.dumps(state))
            self.assertTrue((system / "pending.json").exists())
            self.assertFalse((system / "verified.json").exists())

    def test_public_manifest_is_pinned_and_outside_iso(self):
        self.assertEqual(d.profile_status(d.PROFILES["small-v2"])["download_bytes"], 506181191)
        self.assertEqual(d.profile_status(d.PROFILES["turbo-q5-v3"])["download_bytes"], 678117115)
        self.assertEqual(d.ASSETS["small"][2], 487601967)
        self.assertEqual(d.ASSETS["turbo"][2], 574041195)
        for _name, url, size, digest in d.ASSETS.values():
            self.assertTrue(url.startswith("https://"))
            self.assertNotIn("/main/", url)
            self.assertGreater(size, 0)
            self.assertEqual(len(digest), 64)
        self.assertEqual(str(d.PAYLOAD), "/opt/arctic/voxtype/1.1.0")


class Profiles(unittest.TestCase):
    flags = "avx avx2 fma f16c bmi1 bmi2 movbe popcnt xsave abm"

    def test_modern_and_legacy_hardware_select_one_multilingual_model(self):
        modern = d.desired_profile("flags: " + self.flags)
        legacy = d.desired_profile("flags: sse4_2 popcnt")
        self.assertEqual(modern["id"], "turbo-q5-v3")
        self.assertEqual(legacy["id"], "small-v2")
        for profile in (modern, legacy):
            self.assertEqual(sum(asset[0].endswith(".bin") for asset in profile["assets"].values()), 1)
        self.assertNotIn("vulkan-loader", legacy["dependencies"])

    def test_cpu_flags_use_all_processors_and_exact_tokens(self):
        self.assertFalse(d.v3_supported("flags: " + self.flags + "\nflags: sse4_2 popcnt"))
        self.assertFalse(d.v3_supported("flags: " + self.flags.replace("avx2", "avx2_fake")))
        self.assertFalse(d.v3_supported("not_flags: " + self.flags))
        self.assertFalse(d.v3_supported("flags: " + self.flags.replace("fma", "")))
        self.assertTrue(d.v3_supported("flags: " + self.flags.replace("abm", "lzcnt")))
        self.assertEqual(d.desired_profile("unknown")["id"], "small-v2")
        self.assertFalse(d.v3_supported("processor: 0\nflags: " + self.flags + "\nprocessor: 1\n"))

    def test_compatibility_selection_is_fixed_root_owned_and_retry_persisted(self):
        with tempfile.TemporaryDirectory() as temporary:
            system = Path(temporary)
            with mock.patch.object(d, "directory"), mock.patch.object(d.subprocess, "run"), \
                    mock.patch.object(d, "trusted_file", side_effect=lambda p, size=None: p.is_file()):
                d.request_setup(system, selection="compatibility")
                self.assertEqual(d.desired_profile("flags: " + self.flags, system)["id"], "small-v2")
                self.assertEqual(d.read_json(system / "pending.json")["profile"], "small-v2")
                d.request_setup(system)
                self.assertEqual(d.read_json(system / "pending.json")["profile"], "small-v2")
                d.request_setup(system, selection="recommended")
                self.assertEqual(d.desired_profile("flags: " + self.flags, system)["id"], "turbo-q5-v3")
                with self.assertRaises(d.Failure):
                    d.request_setup(system, selection="https://unsafe/model.bin")
                d.atomic_json(system / "profile-selection.json", {"selection": "https://unsafe/model.bin"})
                self.assertEqual(d.desired_profile("flags: " + self.flags, system)["id"], "turbo-q5-v3")
            with mock.patch.object(d, "trusted_file", return_value=False):
                self.assertEqual(d.desired_profile("flags: " + self.flags, system)["id"], "turbo-q5-v3")

    def test_profile_change_during_download_does_not_change_queue_or_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            system = Path(temporary)
            d.atomic_json(system / "setup.json", {"state": "downloading", "progress": 0.25})
            with mock.patch.object(d, "directory"), mock.patch.object(d.fcntl, "flock", side_effect=BlockingIOError), \
                    mock.patch.object(d.subprocess, "run") as run:
                with self.assertRaises(d.Failure):
                    d.request_setup(system, selection="compatibility")
            self.assertFalse((system / "profile-selection.json").exists())
            self.assertEqual(d.read_json(system / "setup.json")["progress"], 0.25)
            run.assert_not_called()

    def test_profile_receipt_cannot_substitute_or_add_a_model(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            profile = copy.deepcopy(d.PROFILES["small-v2"])
            profile["assets"] = {"cpu": ("cpu", "https://invalid/pin", 3, "f" * 64),
                                 "model": ("model.bin", "https://invalid/model", 5, "e" * 64)}
            for key, asset in profile["assets"].items():
                (folder / asset[0]).write_bytes(b"x" * asset[2])
                (folder / asset[0]).chmod(0o755 if key == "cpu" else 0o644)
            receipt = {"version": d.VERSION, **d.profile_status(profile), "profile_sha256": d.profile_digest(profile),
                       "files": {key: {"sha256": asset[3], "size": asset[2], "mtime_ns": (folder / asset[0]).stat().st_mtime_ns}
                                 for key, asset in profile["assets"].items()}}
            def check(value):
                d.atomic_json(folder / "verified.json", value)
                return d.ready(folder, folder, profile)
            with mock.patch.object(d, "trusted_file", side_effect=lambda p, size=None: p.is_file() and (size is None or p.stat().st_size == size)), \
                    mock.patch.object(d, "dependencies_ready", return_value=True):
                self.assertTrue(check(receipt))
                for field, value in (("profile", "turbo-q5-v3"), ("model", "large-v3-turbo-q5_0"), ("profile_sha256", "0" * 64)):
                    self.assertFalse(check({**receipt, field: value}))
                wrong = copy.deepcopy(receipt)
                wrong["files"]["model"]["sha256"] = "0" * 64
                self.assertFalse(check(wrong))
                wrong = copy.deepcopy(receipt)
                wrong["files"]["extra-model"] = wrong["files"]["model"]
                self.assertFalse(check(wrong))

    def test_setup_downloads_only_selected_profile_and_failure_preserves_receipt(self):
        for name in ("small-v2", "turbo-q5-v3"):
            with self.subTest(profile=name), tempfile.TemporaryDirectory() as temporary:
                system, payload = Path(temporary) / "state", Path(temporary) / "payload" / "version"
                system.mkdir()
                original = {"old": "verified-receipt"}
                d.atomic_json(system / "verified.json", original)
                selected = d.PROFILES[name]
                downloaded = []
                def fetch(asset, destination, _deadline, progress):
                    downloaded.append(asset[0])
                    destination.write_bytes(b"fixture")
                    progress(asset[2])
                with mock.patch.object(d, "desired_profile", return_value=selected), mock.patch.object(d, "directory"), \
                        mock.patch.object(d.os, "geteuid", return_value=0), \
                        mock.patch.object(d.subprocess, "run", return_value=mock.Mock(returncode=0)), \
                        mock.patch.object(d, "download", side_effect=fetch), mock.patch.object(d, "dependencies_ready", return_value=False):
                    payload.mkdir(parents=True)
                    self.assertFalse(d.system_setup(system=system, payload=payload))
                self.assertEqual(downloaded, [a[0] for a in selected["assets"].values()])
                self.assertEqual(sum(n.endswith(".bin") for n in downloaded), 1)
                self.assertEqual(d.read_json(system / "verified.json"), original)
                state = d.read_json(system / "setup.json")
                self.assertEqual(state["profile"], name)
                self.assertEqual(state["download_bytes"], d.profile_status(selected)["download_bytes"])

    def test_queued_status_uses_matching_profile_disclosure(self):
        with tempfile.TemporaryDirectory() as temporary:
            system = Path(temporary)
            with mock.patch.object(d, "directory"):
                d.queue(system, profile=d.PROFILES["small-v2"])
            with mock.patch.object(d, "SYSTEM", system), mock.patch.object(d, "trusted_file", return_value=True), \
                    mock.patch.object(d, "ready", return_value=False), \
                    mock.patch.object(d, "desired_profile", return_value=d.PROFILES["turbo-q5-v3"]):
                value = d.snapshot()
            self.assertEqual(value["model"], "small")
            self.assertEqual(value["download_bytes"], 506181191)

    def test_persistent_sigill_marker_makes_status_unready_after_broker_exit(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary)
            marker = runtime / "arctic/dictation/compatibility-required.json"
            marker.parent.mkdir(parents=True)
            d.atomic_json(marker, {"required": True})
            with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(runtime)}), \
                    mock.patch.object(d, "trusted_file", return_value=False), mock.patch.object(d, "ready", return_value=True), \
                    mock.patch.object(d, "desired_profile", return_value=d.PROFILES["turbo-q5-v3"]):
                result = d.snapshot({"state": "ready", "compatibility_required": False})
            self.assertFalse(result["ready"])
            self.assertEqual(result["state"], "error")
            self.assertTrue(result["compatibility_required"])
            self.assertIn("Small compatibility setup", result["error"])
            with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(runtime)}), \
                    mock.patch.object(d, "trusted_file", return_value=False), mock.patch.object(d, "ready", return_value=True), \
                    mock.patch.object(d, "desired_profile", return_value=d.PROFILES["small-v2"]):
                compatible = d.snapshot()
            self.assertTrue(compatible["ready"])
            self.assertFalse(compatible["compatibility_required"])
            self.assertEqual(compatible["state"], "ready")

    def test_replaced_model_cleanup_requires_matching_old_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            old = folder / "old-model.bin"
            old.write_bytes(b"model")
            unrelated = folder / "private-user-file"
            unrelated.write_bytes(b"keep")
            asset = (old.name, "https://invalid/pinned", 5, "f" * 64)
            previous = {"files": {"model": {"sha256": "f" * 64, "size": 5, "mtime_ns": old.stat().st_mtime_ns}}}
            with mock.patch.object(d, "ASSETS", {"small": asset, "turbo": d.ASSETS["turbo"]}), \
                    mock.patch.object(d, "trusted_file", side_effect=lambda p, size=None: p.is_file() and (size is None or p.stat().st_size == size)):
                d.cleanup_replaced_model({"files": {"model": {"sha256": "0" * 64}}}, d.PROFILES["turbo-q5-v3"], folder)
                self.assertTrue(old.exists())
                d.cleanup_replaced_model(previous, d.PROFILES["turbo-q5-v3"], folder)
            self.assertFalse(old.exists())
            self.assertEqual(unrelated.read_bytes(), b"keep")


class Sessions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.shared = Path(self.tmp.name)
        self.private = self.shared / "dictation"
        self.private.mkdir(mode=0o700)
        self.refresh = mock.patch.object(d, "notify_refresh")
        self.refresh.start()
        self.addCleanup(self.refresh.stop)
        self.snap = mock.patch.object(d, "snapshot", side_effect=lambda runtime=None: {"ok": True, "state": "ready", "ready": True, **(runtime or {})})
        self.snap.start()
        self.addCleanup(self.snap.stop)
        self.broker = d.Broker(self.shared, self.private)
        self.addCleanup(self.broker.terminate)

    def test_missing_model_prevents_recording(self):
        with mock.patch.object(d, "ready", return_value=False), mock.patch.object(d.subprocess, "Popen") as spawn:
            result = self.broker.start()
        spawn.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertIn("not ready", result["error"])

    def test_gpu_failure_explicitly_selects_cpu_retry(self):
        self.broker.process = mock.Mock()
        self.broker.process.poll.return_value = None
        self.broker.runtime["active_backend"] = "vulkan"
        self.broker.failure = "engine"
        with mock.patch.object(self.broker, "terminate", side_effect=lambda: setattr(self.broker, "process", None)), \
                mock.patch.object(self.broker, "locked", return_value=False):
            self.broker.tick()
        self.assertTrue(self.broker.fallback_cpu)
        result = d.read_json(self.shared / "dictation.json")
        self.assertEqual(result["active_backend"], "cpu")
        self.assertIn("record again", result["error"])

    def test_actual_optimized_cpu_sigill_requires_explicit_small_setup(self):
        child = subprocess.Popen(["/bin/sh", "-c", "kill -ILL $$"], start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        child.wait(timeout=2)
        self.broker.process = child
        self.broker.cpu_variant = "avx2"
        self.broker.runtime["active_backend"] = "cpu"
        with mock.patch.object(self.broker, "locked", return_value=False):
            self.broker.tick()
        result = d.read_json(self.shared / "dictation.json")
        self.assertTrue(result["compatibility_required"])
        self.assertIn("Small compatibility setup", result["error"])
        self.assertEqual(result["active_cpu_variant"], "")
        self.assertIsNone(self.broker.process)
        self.assertTrue((self.private / "compatibility-required.json").exists())
        with mock.patch.object(d, "desired_profile", return_value=d.PROFILES["turbo-q5-v3"]), \
                mock.patch.object(d, "supervised") as run:
            result = self.broker.start()
        run.assert_not_called()
        self.assertTrue(result["compatibility_required"])
        self.assertNotIn("record again", result["error"].lower().split("then")[0])

    def test_small_profile_never_selects_unshipped_vulkan(self):
        process = mock.Mock()
        process.poll.return_value = None
        process.stdout = io.BufferedReader(io.BytesIO(b""))
        process.stderr = io.BufferedReader(io.BytesIO(b""))
        def spawn(*_a, **_k):
            (self.private / "voxtype-state").write_text("idle")
            return process
        with mock.patch.object(d, "desired_profile", return_value=d.PROFILES["small-v2"]), \
                mock.patch.object(d, "ready", return_value=True), mock.patch.object(self.broker, "locked", return_value=False), \
                mock.patch.object(d, "gpu_available", return_value=True), \
                mock.patch.object(d, "preferences", return_value={"backend": "auto", "language": "auto"}), \
                mock.patch.object(d, "supervised", side_effect=spawn) as run, mock.patch.object(self.broker, "record", return_value=0):
            result = self.broker.start()
        self.assertEqual(run.call_args.args[0][0], str(d.PAYLOAD / d.ASSETS["cpu"][0]))
        self.assertEqual(result["active_backend"], "cpu")
        self.assertEqual(result["active_cpu_variant"], "baseline")
        self.broker.process = None
        with mock.patch.object(d, "desired_profile", return_value=d.PROFILES["small-v2"]), \
                mock.patch.object(d, "ready", return_value=True), mock.patch.object(self.broker, "locked", return_value=False), \
                mock.patch.object(d, "preferences", return_value={"backend": "vulkan", "language": "auto"}), \
                mock.patch.object(d, "supervised") as run:
            result = self.broker.start()
        run.assert_not_called()
        self.assertIn("CPU only", result["error"])

    def test_forced_vulkan_preference_allows_cpu_retry_after_gpu_failure(self):
        self.broker.fallback_cpu = True
        process = mock.Mock()
        process.poll.return_value = None
        process.stdout = io.BufferedReader(io.BytesIO(b""))
        process.stderr = io.BufferedReader(io.BytesIO(b""))
        def spawn(*args, **kwargs):
            (self.private / "voxtype-state").write_text("idle")
            return process
        with mock.patch.object(d, "ready", return_value=True), mock.patch.object(self.broker, "locked", return_value=False), \
                mock.patch.object(d, "preferences", return_value={"backend": "vulkan", "language": "auto"}), \
                mock.patch.object(d, "supervised", side_effect=spawn) as run, mock.patch.object(self.broker, "record", return_value=0):
            result = self.broker.start()
        self.assertEqual(result["state"], "recording")
        self.assertEqual(result["active_backend"], "cpu")
        self.assertIn("voxtype-cpu", run.call_args.args[0][0])
        self.broker.process = None

    def test_stop_control_failure_discards_audio(self):
        self.broker.runtime["state"] = "recording"
        with mock.patch.object(self.broker, "record", return_value=1), mock.patch.object(self.broker, "terminate") as stop:
            result = self.broker.command("stop")
        stop.assert_called_once()
        self.assertEqual(result["state"], "error")
        self.assertIn("discarded", result["error"])

    def test_recording_timeout_cannot_implicitly_insert_text(self):
        self.broker.process = mock.Mock()
        self.broker.process.poll.return_value = None
        self.broker.runtime["state"] = "recording"
        (self.private / "voxtype-state").write_text("transcribing")
        with mock.patch.object(self.broker, "locked", return_value=False), \
                mock.patch.object(self.broker, "terminate", side_effect=lambda: setattr(self.broker, "process", None)), \
                mock.patch.object(d, "supervised") as spawn:
            self.broker.tick()
        spawn.assert_not_called()
        self.assertIn("60 second", d.read_json(self.shared / "dictation.json")["error"])

    def test_cancellation_before_start_prevents_engine_launch(self):
        old = d.cancellation(self.private)
        d.mark_cancel(self.private)
        with mock.patch.object(d, "ready", return_value=True), mock.patch.object(self.broker, "locked", return_value=False), \
                mock.patch.object(d, "supervised") as spawn:
            result = self.broker.start(old)
        spawn.assert_not_called()
        self.assertEqual(result["state"], "ready")

    def test_completed_result_without_explicit_stop_is_discarded(self):
        self.broker.process = mock.Mock()
        self.broker.process.poll.return_value = None
        (self.private / "voxtype-state").write_text("idle")
        (self.private / "transcript").write_text("not explicitly approved for insertion\n")
        d.atomic_json(self.private / "transcript.done", {"status": "ok"})
        with mock.patch.object(self.broker, "locked", return_value=False), \
                mock.patch.object(self.broker, "terminate", side_effect=lambda: setattr(self.broker, "process", None)), \
                mock.patch.object(d, "supervised") as spawn:
            self.broker.tick()
        spawn.assert_not_called()
        self.assertIn("explicit stop", d.read_json(self.shared / "dictation.json")["error"])

    def test_cancel_during_initialization_never_sends_record_start(self):
        process = mock.Mock()
        process.poll.return_value = None
        process.stdout = io.BufferedReader(io.BytesIO(b""))
        process.stderr = io.BufferedReader(io.BytesIO(b""))
        with mock.patch.object(d, "ready", return_value=True), mock.patch.object(self.broker, "locked", return_value=False), \
                mock.patch.object(d, "gpu_available", return_value=False), mock.patch.object(d, "supervised", return_value=process), \
                mock.patch.object(d.time, "sleep", side_effect=lambda _s: d.mark_cancel(self.private)), \
                mock.patch.object(self.broker, "terminate", side_effect=lambda: setattr(self.broker, "process", None)), \
                mock.patch.object(self.broker, "record") as record:
            result = self.broker.start()
        record.assert_not_called()
        self.assertEqual(result["state"], "ready")

    def test_lock_returns_without_waiting_for_broker_or_audio_shutdown(self):
        with mock.patch.object(d, "runtime_paths", return_value=(self.shared, self.private)), \
                mock.patch.object(d, "ready", return_value=True), mock.patch.object(d.subprocess, "run") as run:
            before = time.monotonic()
            d.client("lock")
        self.assertLess(time.monotonic() - before, 0.1)
        run.assert_not_called()
        self.assertTrue((self.shared / "dictation-locked").exists())
        self.assertNotEqual(d.cancellation(self.private), "")

    def test_repeated_managed_fallback_lock_keeps_supervisor_generation(self):
        marker = self.shared / "dictation-locked"
        original = {"locked": True, "generation": "same-lock", "supervisor_pid": os.getpid(),
                    "supervisor_start": d.process_start(os.getpid())}
        d.atomic_json(marker, original)
        with mock.patch.object(d, "runtime_paths", return_value=(self.shared, self.private)):
            d.client("lock")
        self.assertEqual(d.read_json(marker), original)

    def test_legacy_watcher_cannot_guess_foreign_unlock_after_crash(self):
        marker = self.shared / "dictation-locked"
        d.atomic_json(marker, {"locked": True, "generation": "unknown-foreign-lock"})
        with mock.patch.object(d, "runtime_paths", return_value=(self.shared, self.private)), \
                mock.patch.object(d.subprocess, "run") as probe:
            d.client("watch-unlock")
        probe.assert_not_called()
        self.assertTrue(marker.exists())

    def test_fallback_supervisor_is_registered_before_lock_initialization(self):
        marker = self.shared / "dictation-locked"
        d.atomic_json(marker, {"locked": True, "generation": "initializing"})
        def spawn(*_a, **_k):
            data = d.read_json(marker)
            self.assertEqual(data["generation"], "initializing")
            self.assertTrue(d.owned_lock_supervisor(data))
            raise OSError("swaylock unavailable")
        with mock.patch.object(d, "runtime_paths", return_value=(self.shared, self.private)), \
                mock.patch.object(d.subprocess, "Popen", side_effect=spawn):
            with self.assertRaises(OSError):
                d.lock_supervisor("initializing", [])
        self.assertTrue(marker.exists())

    def test_dead_broker_cancel_cleans_all_owned_transcript_temps(self):
        for name in ("transcript", ".transcript.123.tmp", "transcript.done", "insertion"):
            (self.private / name).write_text("private phrase")
        (self.private / "unrelated.txt").write_text("keep")
        with mock.patch.object(d, "runtime_paths", return_value=(self.shared, self.private)), \
                mock.patch.object(d.subprocess, "Popen") as spawn:
            result = d.client("cancel")
        spawn.assert_not_called()
        self.assertTrue(result["ready"])
        self.assertFalse((self.private / ".transcript.123.tmp").exists())
        self.assertEqual((self.private / "unrelated.txt").read_text(), "keep")

    def test_protocol_newline_never_reaches_typing_backend(self):
        self.broker.process = mock.Mock()
        self.broker.process.poll.return_value = None
        self.broker.started = time.monotonic()
        self.broker.stopped = time.monotonic() - 1
        (self.private / "transcript").write_text("hello שלום\n")
        d.atomic_json(self.private / "transcript.done", {"status": "ok"})
        captured = []
        def spawn(args, **kwargs):
            captured.append(kwargs["stdin"].read())
            process = mock.Mock()
            process.poll.return_value = None
            return process
        with mock.patch.object(self.broker, "locked", return_value=False), mock.patch.object(d, "supervised", side_effect=spawn):
            self.broker.tick()
        self.assertEqual(captured, ["hello שלום".encode()])
        self.assertNotIn("שלום", (self.shared / "dictation.json").read_text())
        self.broker.process = self.broker.output_process = None

    def test_session_lock_probe_failure_denies_recording_and_insertion(self):
        with mock.patch.object(d.subprocess, "run", return_value=mock.Mock(returncode=1, stdout="")):
            self.assertTrue(d.session_locked(self.shared))

    def test_swaylock_process_probe_error_is_fail_closed(self):
        with mock.patch.object(d.subprocess, "run", side_effect=[mock.Mock(returncode=0, stdout="false"), mock.Mock(returncode=2)]):
            self.assertTrue(d.session_locked(self.shared))

    def test_child_exec_guard_terminates_engine_if_broker_dies(self):
        guard = Path(__file__).with_name("child_exec.py")
        pidfile = self.private / "engine.pid"
        code = "import os,subprocess,time; p=subprocess.Popen(['/usr/bin/python3','-I'," + repr(str(guard)) + ",str(os.getpid()),'/bin/sleep','60']); open(" + repr(str(pidfile)) + ",'w').write(str(p.pid)); time.sleep(60)"
        parent = subprocess.Popen(["/usr/bin/python3", "-c", code], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 2
            while not pidfile.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            child = int(pidfile.read_text())
            time.sleep(0.05)
            parent.terminate()
            parent.wait(timeout=2)
            deadline = time.monotonic() + 2
            state = ""
            while time.monotonic() < deadline:
                proc = Path(f"/proc/{child}/stat")
                if not proc.exists():
                    state = "gone"
                    break
                state = proc.read_text().split(") ", 1)[1].split()[0]
                if state == "Z":
                    break
                time.sleep(0.01)
            self.assertIn(state, ("gone", "Z"))
        finally:
            if parent.poll() is None:
                parent.kill()
                parent.wait()

    def test_microphone_failure_is_actionable(self):
        self.broker.process = mock.Mock()
        self.broker.failure = "microphone"
        with mock.patch.object(self.broker, "terminate", side_effect=lambda: setattr(self.broker, "process", None)), \
                mock.patch.object(self.broker, "locked", return_value=False):
            self.broker.tick()
        self.assertIn("Sound settings", d.read_json(self.shared / "dictation.json")["error"])

    def test_cancel_kills_owned_process_group_and_removes_transcript(self):
        child = subprocess.Popen(["/bin/sh", "-c", "sleep 60 & wait"], start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.broker.process = child
        (self.private / "transcript").write_text("private Hebrew שלום and English")
        with mock.patch.object(self.broker, "record", return_value=0), mock.patch.object(d, "ready", return_value=True):
            before = time.monotonic()
            result = self.broker.command("cancel")
        self.assertLess(time.monotonic() - before, 3)
        self.assertIsNotNone(child.poll())
        self.assertFalse((self.private / "transcript").exists())
        self.assertNotIn("שלום", json.dumps(result))
        self.assertNotIn("private Hebrew", (self.shared / "dictation.json").read_text())

    def test_lock_marker_prevents_recording(self):
        (self.shared / "dictation-locked").write_text("{}")
        with mock.patch.object(d, "ready", return_value=True), mock.patch.object(d.subprocess, "Popen") as spawn:
            result = self.broker.start()
        spawn.assert_not_called()
        self.assertIn("Unlock", result["error"])

    def test_lock_prevents_late_transcript_insertion(self):
        self.broker.process = mock.Mock()
        self.broker.process.poll.return_value = None
        (self.private / "transcript").write_text("should never insert")
        d.atomic_json(self.private / "transcript.done", {"status": "ok"})
        (self.shared / "dictation-locked").write_text("{}")
        with mock.patch.object(self.broker, "terminate", side_effect=lambda: self.broker.erase()), \
                mock.patch.object(d.subprocess, "Popen") as spawn:
            self.broker.tick()
        self.broker.process = None
        spawn.assert_not_called()
        self.assertFalse((self.private / "transcript").exists())

    def test_speech_logs_are_classified_without_leaking_content(self):
        self.broker.process = mock.Mock()
        stream = io.BufferedReader(io.BytesIO(b"ERROR Audio capture failed: secret spoken transcript"))
        self.broker.drain(stream, self.broker.process)
        self.assertEqual(self.broker.failure, "microphone")
        self.assertNotIn("secret spoken", (self.shared / "dictation.json").read_text())
        self.broker.process = None

    def test_forced_local_config_disables_transcript_notifications_and_input(self):
        import tomllib
        config = tomllib.loads(d.voxtype_config(self.private, "auto"))
        self.assertEqual(config["engine"], "whisper")
        self.assertEqual(config["whisper"]["mode"], "local")
        self.assertEqual(config["whisper"]["language"], ["he", "en"])
        self.assertFalse(config["hotkey"]["enabled"])
        self.assertFalse(config["output"]["notification"]["on_transcription"])
        self.assertFalse(config["whisper"]["streaming"])
        self.assertEqual(config["text"], {"spoken_punctuation": False, "filter_filler_words": False,
                                          "smart_auto_submit": False})
        with mock.patch.dict(os.environ, {"RUST_LOG": "trace", "VOXTYPE_ENGINE": "remote"}):
            env = d.child_environment(self.private)
        self.assertEqual(env["RUST_LOG"], "error")
        self.assertNotIn("VOXTYPE_ENGINE", env)
        self.assertEqual(env["PIPEWIRE_RUNTIME_DIR"], os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))

    def test_endpoint_is_published_only_after_it_is_listening(self):
        control = self.private / "control.sock"
        events = []
        class Socket:
            def bind(_self, path):
                events.append("bind")
                self.assertFalse(control.exists())
                Path(path).touch()
            def listen(_self, backlog):
                events.append("listen")
                self.assertFalse(control.exists())
                self.assertEqual(backlog, 4)
            def close(_self):
                events.append("close")
        def usable(_read, _write, _errors, _timeout):
            self.assertEqual(events, ["bind", "listen"])
            self.assertTrue(control.exists())
            self.assertEqual(control.stat().st_mode & 0o777, 0o600)
            return ([], [], [])
        self.broker.last_active = time.monotonic() - 301
        with mock.patch.object(d.socket, "socket", return_value=Socket()), \
                mock.patch.object(d.select, "select", side_effect=usable):
            self.broker.serve()
        self.assertEqual(events, ["bind", "listen", "close"])
        self.assertFalse(control.exists())
        self.assertEqual(list(self.private.glob("control.*.sock")), [])

    def test_lifetime_lock_prevents_duplicate_broker_after_slow_startup(self):
        fd = os.open(self.private / "broker.lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            with mock.patch.object(d, "Broker") as factory:
                self.assertFalse(d.run_broker(self.shared, self.private))
            factory.assert_not_called()
        finally:
            os.close(fd)
        with mock.patch.object(d, "Broker") as factory:
            self.assertTrue(d.run_broker(self.shared, self.private))
        factory.assert_called_once_with(self.shared, self.private)
        factory.return_value.serve.assert_called_once()

    def test_private_socket_survives_disconnected_probe(self):
        self.broker.last_active = time.monotonic() - 301
        # Delay idle exit so the disconnected probe followed by status can arrive.
        self.broker.last_active = time.monotonic()
        thread = threading.Thread(target=self.broker.serve, daemon=True)
        thread.start()
        control = self.private / "control.sock"
        deadline = time.monotonic() + 2
        while not control.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
            probe.connect(str(control))
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(2)
            connection.connect(str(control))
            connection.sendall(b"status\n")
            response = json.loads(connection.recv(4096))
        self.assertTrue(response["ready"])
        self.assertEqual(control.stat().st_mode & 0o777, 0o600)
        self.broker.last_active = time.monotonic() - 301
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
