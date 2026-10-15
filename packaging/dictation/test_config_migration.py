import hashlib
import os
import pathlib
import pwd
import runpy
import signal
import subprocess
import tempfile
import time
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = ROOT / "packaging/dictation/arctic-voxtype-migrate-config"
SETUP = ROOT / "packaging/dictation/arctic-voxtype-setup"
SPEC = ROOT / "packaging/arctic-linux.spec"
UNIT = ROOT / "packaging/systemd/arctic-voxtype-config-migration.service"
BASE_MODEL = "/opt/arctic/voxtype/models/ggml-small.bin"
BASE_VALIDATOR = "/opt/arctic/voxtype/1.1.1/voxtype-baseline"


class ConfigMigration(unittest.TestCase):
    def test_recognized_old_bytes_are_pinned_to_stable_history(self):
        implementation = runpy.run_path(str(SOURCE))
        expected = {
            (BASE_MODEL, '["he", "en"]'): "f79d16b60c8d369074af91d1abcfb9b28bce7510ebd81363dbfb25d5f2b53a19",
            (BASE_MODEL, '"he"'): "a4462a228146a3c033017ea428b611d553eb8c18a6a9433bc79054a7bf2fc8bd",
            (BASE_MODEL, '"en"'): "9824f66ca2aa0f040a44539eee6da0420b6d58b965a520b60299408aeb6d5f31",
            ("/opt/arctic/voxtype/models/ggml-large-v3-turbo-q5_0.bin", '["he", "en"]'):
                "afc226ce6cd362b6c985e61f4e09da6f9ce799a2cf1460dfecc314a6a51a016e",
            ("/opt/arctic/voxtype/models/ggml-large-v3-turbo-q5_0.bin", '"he"'):
                "770f977ec7cdfef9460c13e6ee7e5d2ae48c32e5b674be0c29301ab76b8d2771",
            ("/opt/arctic/voxtype/models/ggml-large-v3-turbo-q5_0.bin", '"en"'):
                "e3909c14ea60e775ef658b72108aa75df8506ff0c104640024870e348c2de025",
        }
        for (model, language), digest in expected.items():
            with self.subTest(model=model, language=language):
                old = implementation["canonical"](model, language, False)
                self.assertEqual(hashlib.sha256(old).hexdigest(), digest)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        self.home = self.root / "home"
        self.directory = self.home / ".config/voxtype"
        self.control = self.home / ".migration-test"
        self.directory.mkdir(parents=True)
        self.control.mkdir()
        self.home.chmod(0o700)
        (self.home / ".config").chmod(0o700)
        self.directory.chmod(0o700)
        self.control.chmod(0o700)
        self.model = self.root / "ggml-small.bin"
        self.validator = self.root / "voxtype-baseline"
        self.helper = self.root / "arctic-voxtype-migrate-config"
        source = SOURCE.read_text().replace(BASE_MODEL, str(self.model)).replace(
            BASE_VALIDATOR, str(self.validator))
        self.helper.write_text(source)
        self.helper.chmod(0o755)
        self._validator(False)
        self.uid = os.getuid()
        self.run_as = {}
        if os.geteuid() == 0:
            account = pwd.getpwnam("nobody")
            self.uid = account.pw_uid
            self.root.chmod(0o755)
            for path in (self.home, self.home / ".config", self.directory,
                         self.control):
                os.chown(path, account.pw_uid, account.pw_gid)
            self.run_as = {"user": account.pw_uid, "group": account.pw_gid,
                           "extra_groups": []}
        self.globals = runpy.run_path(str(self.helper))

    def tearDown(self):
        self.temporary.cleanup()

    def _validator(self, blocking):
        body = "#!/bin/sh\n"
        if blocking:
            body += 'touch "$MIGRATION_READY"\nwhile [ ! -e "$MIGRATION_RELEASE" ]; do sleep 0.02; done\n'
        body += "exit 0\n"
        self.validator.write_text(body)
        self.validator.chmod(0o755)

    def _config(self, language='["he", "en"]', resident=False):
        return self.globals["canonical"](str(self.model), language, resident)

    def _write(self, data):
        config = self.directory / "config.toml"
        config.write_bytes(data)
        config.chmod(0o600)
        if os.geteuid() == 0:
            os.chown(config, self.uid, pwd.getpwnam("nobody").pw_gid)
        return config

    def _run(self, *, env=None, check=False):
        merged = dict(os.environ, HOME=str(self.home))
        if env:
            merged.update(env)
        return subprocess.run([str(self.helper), str(self.model), str(self.validator)],
                              env=merged, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=10, check=check, **self.run_as)

    def _popen(self, env):
        merged = dict(os.environ, HOME=str(self.home), **env)
        return subprocess.Popen([str(self.helper), str(self.model), str(self.validator)],
                                env=merged, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                start_new_session=True, **self.run_as)

    @staticmethod
    def _stop(process):
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.communicate(timeout=10)

    def test_old_managed_languages_migrate_without_changing_other_bytes(self):
        for language in ('["he", "en"]', '"he"', '"en"'):
            with self.subTest(language=language):
                config = self._write(self._config(language, resident=False))
                result = self._run()
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                self.assertEqual(config.read_bytes(), self._config(language, resident=True))
                self.assertEqual(config.stat().st_mode & 0o777, 0o600)

    def test_current_config_is_idempotent(self):
        config = self._write(self._config('"he"', resident=True))
        before = config.read_bytes()
        result = self._run()
        self.assertEqual(result.returncode, 20)
        self.assertEqual(config.read_bytes(), before)

    def test_custom_config_is_preserved_byte_for_byte(self):
        custom = self._config(resident=False).replace(
            b"max_duration_secs = 60", b"max_duration_secs = 45")
        config = self._write(custom)
        result = self._run()
        self.assertEqual(result.returncode, 21)
        self.assertEqual(config.read_bytes(), custom)

    def test_concurrent_user_edit_wins(self):
        config = self._write(self._config(resident=False))
        ready = self.control / "ready"
        release = self.control / "release"
        self._validator(True)
        process = self._popen({"MIGRATION_READY": str(ready),
                               "MIGRATION_RELEASE": str(release)})
        try:
            for _ in range(200):
                if ready.exists():
                    break
                time.sleep(0.01)
            self.assertTrue(ready.exists())
            custom = b'[whisper]\nmodel = "personal-model.bin"\nlanguage = "en"\n'
            self._write(custom)
            release.touch()
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 24, (stdout + stderr).decode())
            self.assertEqual(config.read_bytes(), custom)
        finally:
            self._stop(process)

    def test_crash_before_rename_retries_cleanly(self):
        config = self._write(self._config(resident=False))
        ready = self.control / "ready"
        release = self.control / "release"
        self._validator(True)
        process = self._popen({"MIGRATION_READY": str(ready),
                               "MIGRATION_RELEASE": str(release)})
        try:
            for _ in range(200):
                if ready.exists():
                    break
                time.sleep(0.01)
            self.assertTrue(ready.exists())
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=10)
        finally:
            self._stop(process)
        self.assertEqual(config.read_bytes(), self._config(resident=False))
        self._validator(False)
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(config.read_bytes(), self._config(resident=True))

    def test_symlink_is_never_followed(self):
        outside = self.root / "outside"
        outside.write_bytes(self._config(resident=False))
        (self.directory / "config.toml").symlink_to(outside)
        result = self._run()
        self.assertEqual(result.returncode, 23)
        self.assertEqual(outside.read_bytes(), self._config(resident=False))

    def test_boot_migration_has_no_runtime_control_or_network_path(self):
        helper = SOURCE.read_text()
        unit = UNIT.read_text()
        setup = SETUP.read_text()
        migration = setup[setup.index("migrate_config_resident_v1() {"):
                          setup.index("\n}\n", setup.index("migrate_config_resident_v1() {")) + 3]
        for forbidden in ("systemctl", "record toggle", "record cancel", "curl", "wget"):
            self.assertNotIn(forbidden, helper)
            self.assertNotIn(forbidden, migration)
        self.assertIn("Before=systemd-user-sessions.service user@.service", unit)
        self.assertIn("ConditionPathExists=/var/lib/arctic/dictation/config-resident-v1.pending", unit)
        self.assertIn("PrivateNetwork=yes", unit)
        self.assertIn("RestrictAddressFamilies=AF_UNIX", unit)
        self.assertIn("--queue-config-resident-v1", SPEC.read_text())
        self.assertLess(migration.index("record_config_generation"),
                        migration.rindex('durable_remove "$CONFIG_MIGRATION_PENDING"'))


if __name__ == "__main__":
    unittest.main()
