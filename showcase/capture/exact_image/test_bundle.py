import copy
import contextlib
import base64
import gzip
import hashlib
import io
import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import tarfile
import types
import unittest
from unittest import mock
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import bundle
import capture_vm
import contract as c
import guest
import host
from test_capture import (controller_trace, dictation_facts, execution, installed_proof, session,
                          updates_facts, vm_provenance, wallpaper_facts)


class ExportedBundle(unittest.TestCase):
    def setUp(self):
        self.ocr_identity = mock.patch.object(bundle, "approved_ocr_identity",
                                              return_value=copy.deepcopy(c.OCR_IDENTITY))
        self.ocr_identity.start()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.capture_root = self.root / "private"
        self.receipts = []
        capture = host.Capture(self.capture_root, execution(), vm_provenance(), c.OCR_IDENTITY, self.qmp,
                               lambda path: "clean")
        facts = {"dictationsetup": dictation_facts, "winter": wallpaper_facts,
                 "updates": updates_facts}
        for index, scene in enumerate(c.SCENES):
            guest_session = session(scene, facts[scene](),
                                    random=lambda size, index=index: bytes([index + 1]) * size)
            ack, receipt = capture.consume(guest_session.marker(), scene)
            guest_session.accept(ack)
            self.receipts.append(host.finalize_receipt(receipt, controller_trace()))
        self.serial = 0

    def tearDown(self):
        self.ocr_identity.stop()
        self.temp.cleanup()

    @staticmethod
    def qmp(path):
        Image.new("RGB", (1280, 800), "#233041").save(path)

    def export(self, name=None):
        self.serial += 1
        name = name or f"bundle-{self.serial}"
        target = self.root / name
        archive = self.root / f"{name}.tar"
        digest_path = self.root / f"{name}.digest.json"
        manifest, digest = bundle.export(self.capture_root, self.receipts, target, archive,
                                         digest_path)
        return target, archive, digest_path, manifest, digest

    def test_export_validates_exact_receipts_pixels_archive_and_external_pin(self):
        target, archive, digest_path, manifest, digest = self.export()
        checked, receipts = bundle.validate(target, digest, archive)
        self.assertEqual([value["scene"] for value in receipts], list(c.SCENES))
        self.assertEqual(checked, manifest)
        self.assertEqual(manifest["privacy"],
                         {"automated": "passed_and_rechecked_after_export", "human": "pending"})
        self.assertFalse(manifest["release_acceptance"])
        self.assertEqual(digest["manifest"], digest["members"]["bundle.json"])
        self.assertEqual(digest["archive"]["sha256"], c.sha256(archive))
        self.assertTrue(c.fullmatch(c.HEX64, c.sha256(digest_path)))
        self.assertFalse(any("qmp-original" in path.name for path in target.rglob("*")))
        self.assertTrue(all(value["capture"]["retained"] is False
                            and value["capture"]["exported"] is False for value in receipts))

    def test_receipt_parallel_schema_or_review_promotion_fails(self):
        for mutate in (lambda value: value.update(bundle_schema="parallel"),
                       lambda value: value["privacy"].update(human="passed"),
                       lambda value: value.update(release_acceptance=True),
                       lambda value: value["scene_contract"].update(target="forged"),
                       lambda value: value["guest_context"].update(used_for_capture_gate=True),
                       lambda value: value["ocr"].update(sha256="0" * 64),
                       lambda value: value["limitations"].clear(),
                       lambda value: value["vm"]["channel"].update(name="fake")):
            value = copy.deepcopy(self.receipts[0])
            mutate(value)
            with self.assertRaises(c.Invalid):
                c.receipt(value)

    def test_capture_sha256_mutation_fails_bound_receipt_digest(self):
        target, archive, _, _, digest = self.export()
        receipt_path = target / "receipts" / "updates.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["capture"]["sha256"] = "f" * 64
        receipt_path.write_bytes(bundle._json_bytes(receipt))
        os.chmod(receipt_path, 0o600)
        with self.assertRaises(c.Invalid):
            bundle.validate(target, digest, archive)

    def test_privacy_png_rewrite_fails_even_with_recomputed_transport_digests(self):
        target, archive, _, _, _ = self.export()
        output = target / "captures" / "winter.png"
        image = Image.new("RGB", (1280, 800), "white")
        ImageDraw.Draw(image).text((30, 30), "me@example.com", fill="black")
        image.save(output, format="PNG", optimize=True)
        os.chmod(output, 0o600)
        with Image.open(output) as decoded:
            pixels = hashlib.sha256(decoded.tobytes()).hexdigest()
        receipt_path = target / "receipts" / "winter.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["output"].update(bytes=output.stat().st_size, sha256=c.sha256(output),
                                 pixel_sha256=pixels)
        receipt["capture"]["pixel_sha256"] = pixels
        receipt_path.write_bytes(bundle._json_bytes(receipt))
        os.chmod(receipt_path, 0o600)
        manifest_path = target / bundle.BUNDLE_NAME
        manifest = json.loads(manifest_path.read_text())
        manifest["scenes"]["winter"].update(
            bytes=output.stat().st_size, sha256=c.sha256(output),
            receipt_bytes=receipt_path.stat().st_size, receipt_sha256=c.sha256(receipt_path))
        manifest_path.write_bytes(bundle._json_bytes(manifest))
        os.chmod(manifest_path, 0o600)
        archive.unlink()
        archive_record = bundle._archive(target, archive)
        digest = bundle._digest_contract(target, archive_record)
        with self.assertRaisesRegex(c.Invalid, "private text pattern in capture"):
            bundle.validate(target, digest, archive)

    def test_extra_member_and_mixed_provenance_fail(self):
        target, archive, _, _, digest = self.export()
        (target / "unexpected").write_text("no", encoding="utf-8")
        with self.assertRaises(c.Invalid):
            bundle.validate(target, digest, archive)
        mixed = copy.deepcopy(self.receipts)
        mixed[2]["execution"] = dict(mixed[2]["execution"])
        mixed[2]["execution"]["run_id"] += 1
        with self.assertRaises(c.Invalid):
            bundle.export(self.capture_root, mixed, self.root / "mixed", self.root / "mixed.tar",
                          self.root / "mixed.digest.json")


class WrapperProtocol(unittest.TestCase):
    def test_uaccess_rule_precedes_seat_late_and_nonroot_opens_device_path(self):
        self.assertLess(Path(c.CHANNEL_RULE_PATH).name, "73-seat-late.rules")
        self.assertIn(b'TAG+="uaccess"', c.CHANNEL_RULE)
        self.assertIn(b'MODE="0600"', c.CHANNEL_RULE)
        self.assertGreater(os.geteuid(), 0)
        with tempfile.TemporaryDirectory() as temp:
            rule = Path(temp) / Path(c.CHANNEL_RULE_PATH).name
            rule.write_bytes(c.CHANNEL_RULE)
            verified = subprocess.run(["/usr/bin/udevadm", "verify", "--no-summary",
                                       "--no-style", str(rule)], check=False,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(verified.returncode, 0, verified.stderr.decode())
        real_lstat = Path.lstat

        def protected_lstat(path, *args, **kwargs):
            info = real_lstat(path, *args, **kwargs)
            if path == Path("/dev/null"):
                return types.SimpleNamespace(st_mode=stat.S_IFCHR | 0o660, st_uid=0)
            return info

        with mock.patch.object(Path, "lstat", autospec=True, side_effect=protected_lstat):
            descriptor = capture_vm._open_guest_channel(Path("/dev/null"))
        try:
            self.assertGreaterEqual(descriptor, 0)
        finally:
            os.close(descriptor)

    def test_owned_channel_tooling_contains_exact_reviewed_probe(self):
        encoded, compressed_sha = capture_vm._tooling_payload()
        compressed = base64.b64decode(encoded, validate=True)
        self.assertEqual(hashlib.sha256(compressed).hexdigest(), compressed_sha)
        with tarfile.open(fileobj=io.BytesIO(gzip.decompress(compressed)), mode="r:") as archive:
            self.assertEqual(tuple(archive.getnames()), capture_vm.TOOLING_FILES)
            probe = archive.extractfile("capture_probe.py").read()
        self.assertEqual(len(probe), c.PROBE_IDENTITY["bytes"])
        self.assertEqual(hashlib.sha256(probe).hexdigest(), c.PROBE_IDENTITY["sha256"])

    def test_installed_archive_is_extractable_and_executable_by_nonroot_desktop_user(self):
        self.assertGreater(os.geteuid(), 0, "test must exercise the non-root path")
        encoded, _ = capture_vm._tooling_payload()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "arctic-showcase-tooling"
            root.mkdir(mode=0o700)
            with tarfile.open(fileobj=io.BytesIO(gzip.decompress(
                    base64.b64decode(encoded, validate=True))), mode="r:") as archive:
                # The payload is produced in-process from the reviewed fixed member list;
                # preserve its exact 0555 modes instead of the generic data filter's
                # user-write normalization.
                archive.extractall(root, filter="fully_trusted")
            for name in capture_vm.TOOLING_FILES:
                path = root / name
                self.assertEqual(path.stat().st_uid, os.geteuid())
                self.assertEqual(path.stat().st_mode & 0o777, 0o555)
                self.assertTrue(os.access(path, os.R_OK | os.X_OK))
            result = subprocess.run([str(root / "capture_probe.py")], check=False,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 1)
            self.assertIn(b" SCENE", result.stderr)

    def test_bounded_line_channel_round_trip(self):
        first, second = socket.socketpair()
        try:
            writer = capture_vm.Lines(first.fileno(), 1)
            reader = capture_vm.Lines(second.fileno(), 1)
            writer.write("one")
            writer.write("two")
            self.assertEqual(reader.read(), "one")
            self.assertEqual(reader.read(), "two")
        finally:
            first.close()
            second.close()

    def test_installed_shell_exchange_is_fresh_bounded_and_exact(self):
        calls = []

        class Channel:
            def write(self, line):
                calls.append(("write", line))

            def read(self, timeout=None):
                calls.append(("read", timeout))
                return (c.SHELL_SESSION_PREFIX + "ab" * 16
                        + " 1000 arcticshowcase arctic-showcase fish")

        nonce, response = capture_vm._installed_shell_exchange(
            Channel(), random=lambda size: b"\xab" * size)
        self.assertEqual(nonce, "ab" * 16)
        self.assertEqual(calls, [
            ("write", c.SHELL_CHALLENGE_PREFIX + nonce), ("read", 30),
        ])
        c.installed_shell_session_proof(nonce, response)
        calls.clear()
        with self.assertRaisesRegex(c.Invalid, "shell challenge differs"):
            capture_vm._installed_shell_exchange(
                Channel(), random=lambda _size: b"too-short")
        self.assertEqual(calls, [])

    def test_fixed_vm_rejects_wrong_disk_and_fake_channel_or_server(self):
        qmp, channel = Path("/run/qmp"), Path("/run/channel")
        command = capture_vm._qemu_command(qmp, channel, 7, 8, "none", "tcg")
        capture_vm._validate_qemu_command(command, qmp, channel, 7, 8, "none", "tcg")
        self.assertIn(f"virtio-blk-pci,drive=arcticdisk,serial={c.VM_DISK_SERIAL},bootindex=0",
                      command)
        self.assertIn("virtio-vga,max_outputs=1,edid=on,xres=1280,yres=800", command)
        self.assertIn("ide-cd,drive=arcticiso,id=arcticcd,bootindex=1", command)
        self.assertFalse(any("arcticiso" in item and "bootindex=0" in item for item in command))
        mutations = []
        wrong_disk = list(command)
        wrong_disk[wrong_disk.index("file=/proc/self/fd/8,format=raw,if=none,id=arcticdisk")] = \
            "file=/tmp/operator-disk,format=raw,if=none,id=arcticdisk"
        mutations.append(wrong_disk)
        wrong_channel = [item.replace(c.VM_CHANNEL, "org.example.fake") for item in command]
        mutations.append(wrong_channel)
        fake_server = list(command)
        fake_server[0] = "/tmp/qemu-system-x86_64"
        mutations.append(fake_server)
        for value in mutations:
            with self.assertRaises(c.Invalid):
                capture_vm._validate_qemu_command(value, qmp, channel, 7, 8, "none", "tcg")

    def test_arbitrary_true_binary_cannot_replace_approved_ocr(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            capture_vm.parser().parse_args(["host", "--candidate-iso", "/tmp/candidate.iso",
                                            "--output", "/tmp/out", "--ocr", "/usr/bin/true"])
        self.assertNotIn("--ocr", capture_vm.parser().format_help())

    def test_fake_channel_peer_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "channel.sock"
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(str(path))
            listener.listen(1)
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            thread = threading.Thread(target=lambda: client.connect(str(path)))
            thread.start()
            fake_process = types.SimpleNamespace(pid=os.getpid() + 100000)
            try:
                with self.assertRaises(c.Invalid):
                    capture_vm._accept_qemu(listener, fake_process, 1)
            finally:
                thread.join()
                client.close()
                listener.close()

    def test_iso_eject_targets_the_fixed_frontend_id(self):
        qmp = capture_vm.QMP.__new__(capture_vm.QMP)
        qmp.command = mock.Mock(return_value={})
        qmp.eject_iso()
        qmp.command.assert_called_once_with(
            "eject", {"id": "arcticcd", "force": True})

    def test_process_group_shutdown_reaps_descendant(self):
        with tempfile.TemporaryDirectory() as temp:
            capture_vm._become_subreaper()
            pid_path = Path(temp) / "child.pid"
            code = ("import subprocess,time,sys;"
                    "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
                    f"open({str(pid_path)!r},'w').write(str(p.pid));"
                    "time.sleep(60)")
            process = subprocess.Popen([sys.executable, "-c", code], start_new_session=True)
            deadline = time.monotonic() + 3
            while not pid_path.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(pid_path.exists())
            child_pid = int(pid_path.read_text())
            capture_vm._stop_process_group(process, term_timeout=1, kill_timeout=1)
            self.assertIsNotNone(process.returncode)
            deadline = time.monotonic() + 2
            while Path(f"/proc/{child_pid}").exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertFalse(Path(f"/proc/{child_pid}").exists())

    def test_cleanup_exceptions_do_not_skip_later_resources(self):
        calls = []

        def fail():
            calls.append("qmp")
            raise OSError("close failed")

        error = capture_vm._close_independently(
            [fail, lambda: calls.append("channel"), lambda: calls.append("listener"),
             lambda: calls.append("runtime")])
        self.assertIsInstance(error, OSError)
        self.assertEqual(calls, ["qmp", "channel", "listener", "runtime"])

    def test_guest_ready_and_host_go_are_distinct_control_messages(self):
        self.assertNotEqual(capture_vm.READY_PREFIX, capture_vm.GO_PREFIX)
        self.assertTrue(capture_vm.GO_PREFIX.endswith(" "))


if __name__ == "__main__":
    unittest.main()
