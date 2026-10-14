import copy
import fcntl
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import capture_probe
import contract as c
import guest
from test_capture import dictation_facts, identity, installed_snapshot


class ProbeFixture:
    def __init__(self, runtime):
        self.runtime = runtime
        status = dictation_facts()["status"]
        self.answers = {
            ("/usr/bin/arctic-dictation", "status"): status,
            ("/usr/bin/wlr-randr", "--json"): [{
                "name": "Virtual-1", "enabled": True, "scale": 1,
                "current_mode": {"width": 1280, "height": 800}}],
            ("/usr/bin/mmsg", "get", "all-clients"): {"clients": [{
                "title": "Arctic Settings", "is_visible": True, "is_focused": True}]},
            ("/usr/bin/quickshell", "ipc", "call", "settings", "page"): b"dictation\n",
            ("/usr/bin/quickshell", "ipc", "call", "settings", "ready"): b"true\n",
        }

    def run(self, command, timeout=120):
        key = tuple(command)
        if key not in self.answers:
            raise AssertionError(key)
        value = self.answers[key]
        return value if type(value) is bytes else (json.dumps(value, sort_keys=True) + "\n").encode()

    def json(self, command, timeout=120):
        return capture_probe.strict_json(self.run(command, timeout))

    def read(self, path, maximum=capture_probe.MAX_OUTPUT):
        value = Path(path)
        if value == self.runtime / "arctic/dictation.json":
            return b'{"state":"ready"}\n'
        raise AssertionError(value)

    def glob(self, path, pattern):
        return []


class ReviewedProbe(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_real_probe_dictation_collection_is_summarized_as_untrusted(self):
        runtime = self.root / "runtime"
        (runtime / "arctic/dictation").mkdir(parents=True)
        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(runtime)}, clear=False):
            value = capture_probe.collect("dictationsetup", ProbeFixture(runtime))
        session = guest.Session("dictationsetup", value["facts"], identity("dictationsetup"),
                                random=lambda size: b"\x31" * size)
        self.assertEqual(value["output"]["width"], 1280)
        self.assertEqual(value["surface"]["identity"], "Arctic Settings")
        self.assertTrue(session.marker().startswith(c.REQUEST_PREFIX))

    def test_diagnostic_failure_returns_untrusted_unavailable_report(self):
        with mock.patch.object(guest, "collect_system", side_effect=c.Invalid("forged failure")):
            facts, identity_value = guest.collect_untrusted("dictationsetup")
        self.assertEqual(facts, {"available": False, "trust": "untrusted_guest_diagnostic"})
        request = guest.Session("dictationsetup", facts, identity_value,
                                random=lambda size: b"\x41" * size).value
        c.request(request)
        self.assertEqual(request["diagnostics"]["acceptance_effect"], "none")

    def test_missing_changed_symlink_and_hardlink_probe_fail(self):
        source = HERE / "capture_probe.py"
        valid = guest._verified_probe(source, root_owner=False)
        self.assertEqual(fcntl.fcntl(valid, getattr(fcntl, "F_GET_SEALS", 1034)) & 0xF, 0xF)
        os.close(valid)
        missing = self.root / "missing"
        changed = self.root / "changed"
        shutil.copyfile(source, changed); changed.write_bytes(changed.read_bytes() + b"\n"); changed.chmod(0o700)
        symlink = self.root / "symlink"; symlink.symlink_to(source)
        hard = self.root / "hard"; shutil.copyfile(source, hard); hard.chmod(0o700)
        hard_alias = self.root / "hard-alias"; os.link(hard, hard_alias)
        for path in (missing, changed, symlink, hard):
            with self.subTest(path=path.name), self.assertRaises(c.Invalid):
                guest._verified_probe(path, root_owner=False)

    def test_nonroot_can_read_authenticated_rule_and_marker_but_cannot_write(self):
        self.assertGreater(os.geteuid(), 0, "test must exercise the non-root path")
        rule = self.root / "70-arctic-showcase-capture.rules"
        marker = self.root / "installed-image-provenance.json"
        rule.write_bytes(c.CHANNEL_RULE); rule.chmod(0o644)
        marker.write_bytes(installed_snapshot()["marker_bytes"]); marker.chmod(0o444)
        real_fstat = os.fstat

        def root_owned(fd):
            info = real_fstat(fd)
            return types.SimpleNamespace(st_mode=info.st_mode, st_uid=0,
                                         st_nlink=info.st_nlink, st_size=info.st_size)

        with mock.patch.object(os, "fstat", side_effect=root_owned):
            self.assertEqual(guest.verify_channel_access_rule(rule), c.CHANNEL_ACCESS)
        self.assertEqual(c.strict_json(marker.read_bytes())["probe"], c.PROBE_IDENTITY)
        self.assertFalse(os.access(marker, os.W_OK))

    def test_collect_system_executes_held_verified_probe_and_derives_identity(self):
        runtime = self.root / "runtime"
        (runtime / "arctic/dictation").mkdir(parents=True)
        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(runtime)}, clear=False):
            result = capture_probe.collect("dictationsetup", ProbeFixture(runtime))
        snapshot = installed_snapshot()
        marker = c.strict_json(snapshot["marker_bytes"])
        marker_path = self.root / "installed-marker.json"
        marker_path.write_bytes(snapshot["marker_bytes"]); marker_path.chmod(0o444)
        source = HERE / "capture_probe.py"
        real_read_text = Path.read_text
        real_lstat = Path.lstat

        def read_text(path, *args, **kwargs):
            if str(path) == "/proc/cmdline":
                return snapshot["cmdline"]
            if str(path) == "/proc/sys/kernel/random/boot_id":
                return snapshot["boot_id"]
            return real_read_text(path, *args, **kwargs)

        def lstat(path):
            info = real_lstat(path)
            if path == marker_path:
                return types.SimpleNamespace(st_mode=info.st_mode, st_uid=0,
                                             st_nlink=info.st_nlink, st_size=info.st_size)
            return info

        def run(command, **kwargs):
            if command[0].startswith("/proc/self/fd/"):
                return (json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n").encode()
            if command[:2] == ["/usr/bin/lsattr", "-d"]:
                return b"----i----------------- marker\n"
            if command[:4] == ["/usr/bin/findmnt", "-n", "-o", "SOURCE"]:
                return b"/dev/vda3\n"
            if command[:3] == ["/usr/bin/lsblk", "-J", "-o"]:
                return json.dumps({"blockdevices": snapshot["lsblk"]}).encode()
            raise AssertionError(command)

        def open_probe(_path):
            return os.open(source, os.O_RDONLY)

        with mock.patch.object(c, "INSTALL_MARKER", str(marker_path)), \
             mock.patch.object(guest, "_verified_probe", side_effect=open_probe), \
             mock.patch.object(guest, "verify_channel_access_rule", return_value=dict(c.CHANNEL_ACCESS)), \
             mock.patch.object(guest, "_run", side_effect=run), \
             mock.patch.object(Path, "lstat", autospec=True, side_effect=lstat), \
             mock.patch.object(Path, "read_text", autospec=True, side_effect=read_text):
            facts, actual = guest.collect_system("dictationsetup")
        self.assertEqual(facts, result["facts"])
        self.assertEqual(actual["installed"]["probe"], c.PROBE_IDENTITY)
        self.assertEqual(actual["installed"]["disk_serial"], c.VM_DISK_SERIAL)
        self.assertEqual(marker["probe"], c.PROBE_IDENTITY)


if __name__ == "__main__":
    unittest.main()
