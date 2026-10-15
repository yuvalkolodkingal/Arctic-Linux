import copy
import contextlib
import io
import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

from PIL import Image, PngImagePlugin

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import contract as c
import guest
import host


def installed_proof():
    marker = {"schema": "arctic-installed-image-provenance-v1", "image": copy.deepcopy(c.IMAGE),
              "disk_serial": c.VM_DISK_SERIAL, "installation_id": "1" * 32,
              "source_device": "/dev/sr0", "probe": copy.deepcopy(c.PROBE_IDENTITY),
              "channel_access": copy.deepcopy(c.CHANNEL_ACCESS),
              "release_acceptance": False}
    raw = (json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n").encode()
    return {"disk_serial": c.VM_DISK_SERIAL, "root_device": "/dev/vda3",
            "root_chain": ["vda3", "vda"], "live": False, "marker_path": c.INSTALL_MARKER,
            "marker_sha256": __import__("hashlib").sha256(raw).hexdigest(),
            "marker_immutable": True, "image": copy.deepcopy(c.IMAGE),
            "probe": copy.deepcopy(c.PROBE_IDENTITY),
            "channel_access": copy.deepcopy(c.CHANNEL_ACCESS),
            "installation_id_sha256": c.hashed("1" * 32)}


def installed_snapshot(scene="dictationsetup"):
    marker = {"schema": "arctic-installed-image-provenance-v1", "image": copy.deepcopy(c.IMAGE),
              "disk_serial": c.VM_DISK_SERIAL, "installation_id": "1" * 32,
              "source_device": "/dev/sr0", "probe": copy.deepcopy(c.PROBE_IDENTITY),
              "channel_access": copy.deepcopy(c.CHANNEL_ACCESS),
              "release_acceptance": False}
    return {"cmdline": "BOOT_IMAGE=/boot/vmlinuz root=/dev/vda3 ro",
            "root_device": "/dev/vda3",
            "lsblk": [{"name": "vda", "kname": "vda", "type": "disk",
                        "serial": c.VM_DISK_SERIAL, "pkname": None,
                        "children": [{"name": "vda3", "kname": "vda3", "type": "part",
                                      "serial": None, "pkname": "vda"}]}],
            "marker_bytes": (json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n").encode(),
            "marker_mode": 0o100444, "marker_uid": 0, "marker_immutable": True,
            "boot_id": "boot-a", "desktop_uid": 1000,
            "output": identity_output(), "surface": identity_surface(scene)}


def identity_output():
    return {"name": "Virtual-1", "width": 1280, "height": 800, "scale": 1, "count": 1}


def identity_surface(scene):
    return {"kind": "client-title" if scene != "updates" else "layer-namespace",
            "identity": "Arctic Settings" if scene != "updates" else "arctic-whats-new",
            "count": 1, "focused": True}


def identity(scene):
    return {"image": copy.deepcopy(c.IMAGE), "installed": installed_proof(), "boot_id": "boot-a",
            "desktop_uid": 1000,
            "output": identity_output(), "surface": identity_surface(scene)}


def session(scene, facts, random=lambda size: b"\x55" * size):
    return guest.Session(scene, facts, identity(scene), random=random)


def dictation_facts():
    return {"phase": "online-installed",
            "status": {"ok": True, "ready": True, "state": "ready", "version": "1.1.1",
                       "profile": "turbo-q5-v3", "model": "large-v3-turbo-q5_0",
                       "cpu_variant": "avx2", "model_download_bytes": 574041195,
                       "download_bytes": 593457131, "compatibility_required": False},
            "settings_ready": True, "settings_page": "dictation", "settings_clients": 1,
            "recording": False, "transcribing": False, "receiver_empty": True, "transcript_files": 0}


def wallpaper_facts():
    item = {"slug": "butterfly-in-gold", "name": "Butterfly in Gold", "arctic": True,
            "hideable": True, "key": "/usr/share/backgrounds/arctic/butterfly-in-gold.jpg",
            "path": "/usr/share/backgrounds/arctic/butterfly-in-gold.jpg"}
    return {"target": {"slug": "butterfly-in-gold", "name": "Butterfly in Gold"},
            "before": {"items": [item], "hiddenArctic": [], "current": "city-afterglow"},
            "hidden": {"items": [], "hiddenArctic": [{"slug": "butterfly-in-gold", "name": "Butterfly in Gold"}],
                       "current": "city-afterglow"},
            "restored": {"items": [item], "hiddenArctic": [], "current": "city-afterglow"},
            "file_hashes": [c.WALLPAPER_SHA256] * 3,
            "dialog": {"title": "Hide “Butterfly in Gold”?",
                       "body": "This packaged picture is hidden from the picker and automatic changes. You can restore it below."}}


def updates_facts():
    return {"installed": True, "live": False, "notes_source_sha256": c.WHATS_NEW_SHA256,
            "notes_installed_sha256": c.WHATS_NEW_SHA256, "ipc": "arctic-shell-ipc whatsnew open",
            "surface": "arctic-whats-new"}


def execution():
    return copy.deepcopy(c.REVIEWED_EXECUTION)


def vm_provenance():
    argv = ["/usr/bin/qemu-system-x86_64", "-machine", "q35,accel=kvm", "-cpu", "host",
            "-smp", "4", "-m", "4096", "-display", "none", "-device",
            "virtio-vga,max_outputs=1,edid=on,xres=1280,yres=800", "-qmp",
            "unix:/tmp/arctic-test/qmp.sock,server=on,wait=off", "-serial",
            "file:/tmp/arctic-test/serial.log", "-monitor", "none", "-drive",
            "file=/proc/self/fd/7,format=raw,media=cdrom,readonly=on,if=none,id=arcticiso",
            "-device", "ide-cd,drive=arcticiso,id=arcticcd,bootindex=1", "-drive",
            "file=/proc/self/fd/8,format=raw,if=none,id=arcticdisk", "-device",
            "virtio-blk-pci,drive=arcticdisk,serial=ARCTICSHOWCASE121,bootindex=0",
            "-netdev", "user,id=arcticnet", "-device", "virtio-net-pci,netdev=arcticnet",
            "-device", "qemu-xhci", "-device", "usb-tablet", "-rtc", "base=utc",
            "-chardev", "socket,id=arcticshowcase,path=/tmp/arctic-test/channel.sock,server=off",
            "-device", "virtio-serial-pci,id=arcticserial", "-device",
            "virtserialport,bus=arcticserial.0,chardev=arcticshowcase,name=" + c.VM_CHANNEL]
    encoded = json.dumps(argv, ensure_ascii=False, separators=(",", ":")).encode()
    return {"schema": "arctic-showcase-capture-vm-v1",
            "qemu": {"path": "/usr/bin/qemu-system-x86_64", "bytes": 12345,
                     "sha256": "c" * 64},
            "candidate": {"name": c.IMAGE["name"], "bytes": c.IMAGE["bytes"],
                          "sha256": c.IMAGE["sha256"],
                          "handoff": "verified held file descriptor"},
            "installed_disk": {"format": "raw", "bytes": c.VM_DISK_BYTES,
                               "serial": c.VM_DISK_SERIAL, "bootindex": 0,
                               "initial_state": "new zero-filled sparse file",
                               "handoff": "new held file descriptor"},
            "channel": {"name": c.VM_CHANNEL,
                        "transport": "virtio-serial over owned AF_UNIX", "host_role": "server"},
            "lifecycle": "one QEMU process from blank-disk exact-ISO boot through all captures",
            "qemu_argv": argv,
            "qemu_argv_sha256": __import__("hashlib").sha256(encoded).hexdigest(),
            "qemu_argv_bytes": len(encoded)}


def controller_trace():
    def screen(expectation):
        width, height = ((1920, 1080) if expectation == "install-boot-menu-selected"
                         else (1280, 800))
        return {"bytes": 1234, "sha256": "a" * 64,
                "ocr_sha256": "b" * 64, "expectation": expectation,
                "width": width, "height": height}
    rows = [
        ("live-boot", "keys", {"names": ["home"]}),
        ("live-boot", "screen", screen("install-boot-menu")),
        ("live-boot", "keys", {"names": ["down"]}),
        ("live-boot", "screen", screen("install-boot-menu-selected")),
        ("live-boot", "keys", {"names": ["ret"]}),
        ("live-boot", "screen", screen("live-installer-visible")),
        ("live-console", "keys", {"names": ["ctrl-alt-f6"]}),
        ("live-console", "screen", screen("live-console-login")),
        ("live-console", "text", {"command": "live-username", "characters": 8,
                                    "sha256": "4f8841fb7db59dee76d1f5b74e14010bb1beabce549fa6da7b790f5497dd0f94"}),
        ("live-console", "keys", {"names": ["ret"]}),
        ("live-console", "keys", {"names": ["ret"]}),
        ("live-install", "text", {"command": "live-install", "characters": 623,
                                    "sha256": "86818a073728d6702ca128ccb0b3c4e881a170f3887d7386129047ec97a14bde"}),
        ("live-install", "keys", {"names": ["ret"]}),
        ("live-install", "command", {"id": "live-install"}),
        ("install-complete", "screen", screen("installer-done")),
        ("installed-transition", "qmp", {"operation": "eject-exact-iso"}),
        ("installed-transition", "qmp", {"operation": "system-reset"}),
        ("installed-console", "keys", {"names": ["ctrl-alt-f6"]}),
        ("installed-boot", "screen", screen("installed-login-ready")),
        ("installed-console", "text", {"command": "installed-username", "characters": 14,
                                         "sha256": "b8214c27644e8af628d5030b053746bea3f72aca7325a066a912de18aef48c0a"}),
        ("installed-console", "keys", {"names": ["ret"]}),
        ("installed-console", "screen", screen("installed-password-prompt")),
        ("installed-console", "secret", {"source": "reviewed-disposable-controller-constant",
                                           "characters": 38}),
        ("installed-console", "keys", {"names": ["ret"]}),
        ("installed-console", "screen", screen("installed-fetch-greeting")),
        ("installed-console", "keys", {"names": ["ret"]}),
        ("installed-console", "keys", {"names": ["ctrl-l"]}),
        ("installed-console", "screen", screen("installed-fetch-cleared")),
        ("installed-console", "screen", screen("installed-shell-ready")),
        ("installed-console", "text", {"command": "installed-shell-proof", "characters": 119,
                                         "sha256": "d4e0d2a1ef814035fdc94ff2ff81ebddd74658f5ea8389a4784c75a2bca36466"}),
        ("installed-console", "keys", {"names": ["ret"]}),
        ("installed-console", "screen", screen("installed-shell")),
        ("installed-scenes", "text", {"command": "installed-scenes", "characters": 548,
                                        "sha256": "f1418f9787b417445c2792a686e024986367ec186f1ff5d798a463fa938d4d06"}),
        ("installed-scenes", "keys", {"names": ["ret"]}),
        ("installed-console", "screen", screen("installed-sudo-password")),
        ("installed-console", "secret", {"source": "reviewed-disposable-controller-constant",
                                           "characters": 38}),
        ("installed-console", "keys", {"names": ["ret"]}),
        ("installed-scenes", "command", {"id": "installed-scenes"}),
        ("installed-boot", "screen", screen("first-login-welcome")),
        ("installed-boot", "keys", {"names": ["esc"]}),
        ("installed-boot", "screen", screen("first-login-dismissed")),
        ("dictation-readiness", "command", {"id": "dictation-readiness"}),
        ("dictationsetup", "command", {"id": "dictationsetup"}),
        ("dictationsetup", "screen", screen("dictation-ready-page")),
        ("dictationsetup", "screen", screen("dictation-ready-page")),
        ("winter", "command", {"id": "winter"}),
        ("winter", "screen", screen("wallpaper-page")),
        ("winter", "pointer", {"x": 500, "y": 300, "button": "left",
                                  "target": "wallpaper-hide-button"}),
        ("winter", "screen", screen("wallpaper-hide-dialog")),
        ("winter", "screen", screen("wallpaper-hide-dialog")),
        ("updates", "command", {"id": "updates"}),
        ("updates", "screen", screen("whats-new-layer")),
        ("updates", "screen", screen("whats-new-layer")),
        ("shutdown", "qmp", {"operation": "quit"}),
        ("shutdown", "cleanup", {"private_runtime_removed": True,
                                    "process_group_stopped": True,
                                    "open_image_descriptors": 0,
                                    "retained_source": "screened-normalized-pngs-only"}),
    ]
    value = {"schema": "arctic-showcase-unattended-trace-v1",
             "contract": copy.deepcopy(c.CONTROLLER), "tooling_sha256": "d" * 64,
             "events": [{"index": index, "stage": stage, "kind": kind, "detail": detail}
                        for index, (stage, kind, detail) in enumerate(rows)],
             "status": "completed", "guest_diagnostics_used": False,
             "release_acceptance": False}
    c.controller_trace(value)
    return value


class DiagnosticChecks(unittest.TestCase):
    def test_three_scene_diagnostic_checks(self):
        self.assertEqual(guest.dictation(dictation_facts())["profile"], "turbo-q5-v3")
        self.assertTrue(guest.wallpaper(wallpaper_facts())["returned_after_restore"])
        self.assertFalse(guest.updates(updates_facts())["automatic_trigger_proved"])

    def test_dictation_rejects_recording_and_small_download(self):
        for mutate in (lambda value: value.update(recording=True),
                       lambda value: value["status"].update(download_bytes=9),
                       lambda value: value["status"].update(download_bytes=593457131.0),
                       lambda value: value["status"].update(model_download_bytes=574041195.0)):
            value = dictation_facts(); mutate(value)
            with self.assertRaises(c.Invalid): guest.dictation(value)

    def test_wallpaper_rejects_current_or_changed_file(self):
        value = wallpaper_facts(); value["before"]["current"] = value["before"]["items"][0]["key"]
        with self.assertRaises(c.Invalid): guest.wallpaper(value)
        value = wallpaper_facts(); value["file_hashes"][2] = "3" * 64
        with self.assertRaises(c.Invalid): guest.wallpaper(value)

    def test_wallpaper_rejects_slug_only_or_changed_restored_item(self):
        value = wallpaper_facts(); value["restored"]["items"] = [{"slug": "butterfly-in-gold"}]
        with self.assertRaises(c.Invalid): guest.wallpaper(value)
        value = wallpaper_facts(); value["restored"]["items"][0]["name"] = "Changed"
        with self.assertRaises(c.Invalid): guest.wallpaper(value)

    def test_updates_rejects_live_or_changed_notes(self):
        value = updates_facts(); value["live"] = True
        with self.assertRaises(c.Invalid): guest.updates(value)
        value = updates_facts(); value["notes_installed_sha256"] = "3" * 64
        with self.assertRaises(c.Invalid): guest.updates(value)


class Protocol(unittest.TestCase):
    def session(self):
        return session("dictationsetup", dictation_facts(), random=lambda size: b"\x11" * size)

    def test_request_and_ack_are_one_use(self):
        session = self.session(); marker = session.marker()
        with self.assertRaises(c.Invalid): session.marker()
        value = c.strict_json(marker[len(c.REQUEST_PREFIX):]); c.request(value)
        ack = {"schema": "arctic-showcase-capture-ack-v1", "scene": value["scene"],
               "nonce": value["nonce"], "capture_sha256": "4" * 64, "release_acceptance": False}
        result = session.accept(c.ACK_PREFIX + json.dumps(ack))
        self.assertFalse(result["release_acceptance"])
        with self.assertRaises(c.Invalid): session.accept(c.ACK_PREFIX + json.dumps(ack))
        with self.assertRaises(c.Invalid): session.marker()

    def test_wrong_nonce_and_oversized_diagnostics_fail(self):
        session = self.session(); value = copy.deepcopy(session.value)
        value["diagnostics"] = {"padding": "x" * 40_000}
        with self.assertRaises(c.Invalid): c.request(value)
        ack = {"schema": "arctic-showcase-capture-ack-v1", "scene": "dictationsetup",
               "nonce": "2" * 32, "capture_sha256": "4" * 64, "release_acceptance": False}
        with self.assertRaises(c.Invalid): session.accept(c.ACK_PREFIX + json.dumps(ack))

    def test_string_hash_types_are_strict(self):
        session = self.session(); value = copy.deepcopy(session.value)
        value["nonce"] = int("1" * 32)
        with self.assertRaises(c.Invalid): c.request(value)
        bad = execution(); bad["source_sha"] = int("1" * 40)
        with self.assertRaises(c.Invalid): c.execution(bad)

    def test_changed_guest_observations_are_only_untrusted_diagnostics(self):
        changed = dictation_facts(); changed["recording"] = True
        value = guest.Session("dictationsetup", changed, {"forged": True}).value
        c.request(value)
        self.assertEqual(value["diagnostics"]["acceptance_effect"], "none")

    def test_installed_proof_rejects_live_iso_wrong_and_rootless_disks(self):
        value = installed_snapshot()
        self.assertEqual(guest.installed_from_snapshot(value)["root_chain"], ["vda3", "vda"])
        live = copy.deepcopy(value); live["cmdline"] += " rd.live.image"
        wrong = copy.deepcopy(value); wrong["lsblk"][0]["serial"] = "OPERATOR-DISK"
        rootless = copy.deepcopy(value); rootless["root_device"] = "overlay"
        for bad in (live, wrong, rootless):
            with self.assertRaises(c.Invalid):
                guest.installed_from_snapshot(bad)

    def test_operator_identity_and_scene_json_flags_are_not_accepted(self):
        import capture_vm
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            capture_vm.parser().parse_args(["guest", "--scene", "winter", "--facts", "/tmp/f.json",
                                            "--identity", "/tmp/i.json"])

    def test_self_asserted_actions_execution_is_rejected(self):
        claimed = copy.deepcopy(c.REVIEWED_EXECUTION)
        claimed.update(run_id=999, artifact_id=888, source_sha="a" * 40,
                       artifact_digest="sha256:" + "b" * 64)
        with self.assertRaises(c.Invalid):
            c.execution(claimed)

    def test_fetch_redraw_is_one_control_l_before_the_prompt_gate(self):
        value = controller_trace()
        redraw = next(event for event in value["events"]
                      if event["kind"] == "keys"
                      and event["detail"] == {"names": ["ctrl-l"]})
        redraw["detail"] = {"names": ["ret"]}
        with self.assertRaisesRegex(c.Invalid, "fetch redraw|key inventory"):
            c.controller_trace(value)

    def test_root_owned_world_readable_marker_is_accepted_but_not_writable(self):
        value = installed_snapshot()
        self.assertEqual(value["marker_mode"] & 0o777, 0o444)
        self.assertEqual(guest.installed_from_snapshot(value)["channel_access"], c.CHANNEL_ACCESS)
        for mode in (0o100400, 0o100440, 0o100464, 0o100666):
            changed = copy.deepcopy(value); changed["marker_mode"] = mode
            with self.assertRaises(c.Invalid):
                guest.installed_from_snapshot(changed)


class Host(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()

    @staticmethod
    def qmp(path, size=(1280, 800), metadata=False, mode="RGB"):
        image = Image.new(mode, size, "#233041")
        if metadata:
            info = PngImagePlugin.PngInfo()
            info.add_text("private", metadata if type(metadata) is str else "removed")
            image.save(path, pnginfo=info)
        else:
            image.save(path)

    @staticmethod
    def append_before_iend(path, kind, payload):
        data = path.read_bytes()
        if data[-8:-4] != b"IEND":
            raise AssertionError("test PNG has no final IEND")
        chunk = (struct.pack(">I", len(payload)) + kind + payload
                 + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))
        path.write_bytes(data[:-12] + chunk + data[-12:])

    def marker(self, scene="dictationsetup"):
        facts = {"dictationsetup": dictation_facts, "winter": wallpaper_facts,
                 "updates": updates_facts}[scene]()
        return session(scene, facts).marker()

    def test_capture_normalizes_and_stays_unreviewed(self):
        session = globals()["session"]("dictationsetup", dictation_facts())
        capture = host.Capture(self.root, execution(), vm_provenance(), c.OCR_IDENTITY, lambda path: self.qmp(path),
                               lambda path: "Arctic Settings")
        ack, receipt = capture.consume(session.marker(), "dictationsetup")
        completion = session.accept(ack)
        receipt = host.finalize_receipt(receipt, controller_trace())
        self.assertTrue(ack.startswith(c.ACK_PREFIX))
        self.assertEqual(receipt["status"], "captured_unreviewed")
        self.assertEqual(receipt["privacy"]["human"], "pending")
        self.assertFalse(receipt["release_acceptance"])
        self.assertFalse((self.root / "dictationsetup-qmp-original.png").exists())
        with Image.open(self.root / receipt["output"]["path"]) as image:
            self.assertEqual(image.info, {})
        with self.assertRaises(c.Invalid): capture.consume(self.marker(), "dictationsetup")

    def test_wrong_dimensions_fail(self):
        capture = host.Capture(self.root, execution(), vm_provenance(), c.OCR_IDENTITY, lambda path: self.qmp(path, (1279, 800)),
                               lambda path: "clean")
        with self.assertRaises(c.Invalid): capture.consume(self.marker(), "dictationsetup")

    def test_rgba_capture_is_rejected_instead_of_converted(self):
        capture = host.Capture(self.root, execution(), vm_provenance(), c.OCR_IDENTITY, lambda path: self.qmp(path, mode="RGBA"),
                               lambda path: "clean")
        with self.assertRaises(c.Invalid): capture.consume(self.marker(), "dictationsetup")
        self.assertEqual(list(self.root.glob("*.png")), [])

    def test_source_metadata_is_rejected_and_deleted(self):
        capture = host.Capture(self.root, execution(), vm_provenance(),
                               c.OCR_IDENTITY,
                               lambda path: self.qmp(path, metadata="secret transcript phrase"),
                               lambda path: "clean")
        with self.assertRaises(c.Invalid): capture.consume(self.marker(), "dictationsetup")
        self.assertEqual(list(self.root.glob("*.png")), [])

    def test_post_idat_text_chunk_is_rejected_and_deleted(self):
        def qmp(path):
            self.qmp(path)
            self.append_before_iend(path, b"tEXt", b"transcript\x00secret transcript phrase")

        capture = host.Capture(self.root, execution(), vm_provenance(), c.OCR_IDENTITY, qmp, lambda path: "clean")
        with self.assertRaises(c.Invalid): capture.consume(self.marker(), "dictationsetup")
        self.assertEqual(list(self.root.glob("*.png")), [])

    def test_unknown_ancillary_chunk_is_rejected_and_deleted(self):
        def qmp(path):
            self.qmp(path)
            self.append_before_iend(path, b"prIv", b"secret transcript phrase")

        capture = host.Capture(self.root, execution(), vm_provenance(), c.OCR_IDENTITY, qmp, lambda path: "clean")
        with self.assertRaises(c.Invalid): capture.consume(self.marker(), "dictationsetup")
        self.assertEqual(list(self.root.glob("*.png")), [])

    def test_bad_crc_and_trailing_bytes_are_rejected_and_deleted(self):
        for index, mutate in enumerate((lambda data: data[:-1] + bytes([data[-1] ^ 1]),
                                        lambda data: data + b"secret trailing bytes",
                                        lambda data: data[:8] + b"\xff\xff\xff\xff" + data[12:])):
            root = self.root / str(index)

            def qmp(path, mutate=mutate):
                self.qmp(path)
                path.write_bytes(mutate(path.read_bytes()))

            capture = host.Capture(root, execution(), vm_provenance(), c.OCR_IDENTITY, qmp, lambda path: "clean")
            with self.assertRaises(c.Invalid): capture.consume(self.marker(), "dictationsetup")
            self.assertEqual(list(root.glob("*.png")), [])

    def test_failed_request_nonce_is_burned_but_fresh_request_can_retry(self):
        calls = []

        def qmp(path):
            calls.append(path)
            self.qmp(path)

        capture = host.Capture(self.root, execution(), vm_provenance(), c.OCR_IDENTITY, qmp, lambda path: "/root/private.txt")
        marker = self.marker()
        with self.assertRaises(c.Invalid): capture.consume(marker, "dictationsetup")
        capture.ocr = lambda path: "clean"
        with self.assertRaises(c.Invalid): capture.consume(marker, "dictationsetup")
        self.assertEqual(len(calls), 1)
        fresh = session("dictationsetup", dictation_facts(),
                        random=lambda size: b"\x56" * size).marker()
        ack, receipt = capture.consume(fresh, "dictationsetup")
        self.assertTrue(ack.startswith(c.ACK_PREFIX))
        self.assertEqual(receipt["status"], "captured_unreviewed")
        self.assertEqual(len(calls), 2)

    def test_privacy_patterns_fail(self):
        for index, text in enumerate(("me@example.com", "192.168.1.2", "aa:bb:cc:dd:ee:ff",
                                      "2001:db8::1", "/home/alice/private", "/var/home/bob/private",
                                      "Open [/root/.ssh/id_ed25519]",
                                      "Open (/home/alice/private.txt)", "private_sentinel",
                                      "secret transcript phrase")):
            root = self.root / str(index)
            capture = host.Capture(root, execution(), vm_provenance(), c.OCR_IDENTITY, lambda path: self.qmp(path), lambda path, text=text: text,
                                   private_fragments=("secret transcript phrase",))
            with self.assertRaises(c.Invalid): capture.consume(self.marker(), "dictationsetup")
            self.assertEqual(list(root.glob("*.png")), [])

    def test_execution_tamper_fails_and_guest_completion_is_not_receipt_evidence(self):
        bad = execution(); bad["artifact_digest"] = "sha256:" + "x" * 64
        with self.assertRaises(c.Invalid): host.Capture(self.root, bad, vm_provenance(), c.OCR_IDENTITY, lambda path: None, lambda path: "")
        session = globals()["session"]("dictationsetup", dictation_facts())
        capture = host.Capture(self.root, execution(), vm_provenance(), c.OCR_IDENTITY, lambda path: self.qmp(path), lambda path: "clean")
        ack, receipt = capture.consume(session.marker(), "dictationsetup")
        session.accept(ack)
        self.assertIs(host.finalize_receipt(receipt, controller_trace()), receipt)

    def test_guest_marker_context_does_not_enter_receipt(self):
        capture = host.Capture(self.root, execution(), vm_provenance(), c.OCR_IDENTITY,
                               lambda path: self.qmp(path), lambda path: "clean")
        _, receipt = capture.consume(self.marker(), "dictationsetup")
        self.assertNotIn("installation_seal_sha256", receipt)
        self.assertFalse(receipt["guest_context"]["used_for_capture_gate"])

    def test_fresh_forged_guest_json_cannot_change_host_acceptance_receipt(self):
        roots = self.root / "legit", self.root / "forged"
        receipts = []
        for root, marker in ((roots[0], self.marker()), (roots[1], None)):
            capture = host.Capture(root, execution(), vm_provenance(), c.OCR_IDENTITY,
                                   lambda path: self.qmp(path), lambda path: "clean")
            if marker is None:
                forged = {"schema": "arctic-showcase-capture-request-v1",
                          "scene": "dictationsetup", "nonce": "f" * 32,
                          "diagnostics": {"fresh": True, "root_forged": True,
                                          "claims": {"anything": "accepted"}},
                          "release_acceptance": False}
                marker = c.REQUEST_PREFIX + json.dumps(forged, sort_keys=True,
                                                       separators=(",", ":"))
            _, receipt = capture.consume(marker, "dictationsetup")
            receipts.append(host.finalize_receipt(receipt, controller_trace()))
        self.assertEqual(receipts[0], receipts[1])
        self.assertFalse(receipts[1]["release_acceptance"])
        self.assertEqual(receipts[1]["privacy"]["human"], "pending")

    def test_completion_rejects_tampered_human_review(self):
        session = globals()["session"]("dictationsetup", dictation_facts())
        capture = host.Capture(self.root, execution(), vm_provenance(), c.OCR_IDENTITY, lambda path: self.qmp(path), lambda path: "clean")
        ack, receipt = capture.consume(session.marker(), "dictationsetup")
        session.accept(ack)
        receipt["privacy"]["human"] = "passed"
        with self.assertRaises(c.Invalid): host.finalize_receipt(receipt, controller_trace())


if __name__ == "__main__": unittest.main()
