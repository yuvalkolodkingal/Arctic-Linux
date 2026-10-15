#!/usr/bin/env python3
"""Execute the old stable payload to direct VoxType migration with tiny fixtures.

The production hashes, signed-provenance test, and image gates cover the real
assets. This probe executes the root transition itself with size-equivalent
constants replaced by small local files, so CI can exercise profile selection,
the --migrate-legacy entry point, crash recovery, and cleanup without embedding
or downloading hundreds of megabytes.
"""
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SETUP = ROOT / "packaging/dictation/arctic-voxtype-setup"
SOURCE_COMMIT = "e2638ca63f566f1682bcedc0abea8e4b25211c21"
PROFILE_SHA = {
    "small-v2": "d4b9326169fe0773b36857ce4b2c52d31294c4c421933c5fbb41422227e92756",
    "turbo-q5-v3": "dfc1e2252ca033888fd0262f73fd4643066c736b9d696e4b7481875e76ed4191",
}
ASSETS = {
    "cpu": ("voxtype-cpu", b"baseline-fixture\n", 0o755),
    "avx2": ("voxtype-cpu-avx2", b"avx2-fixture\n", 0o755),
    "vulkan": ("voxtype-vulkan", b"vulkan-fixture\n", 0o755),
    "small": ("ggml-small.bin", b"small-model-fixture\n", 0o644),
    "turbo": ("ggml-large-v3-turbo-q5_0.bin", b"turbo-model-fixture\n", 0o644),
}
PRODUCTION = {
    "cpu": (18579224, "1c9d78b4f6805e4f12ba3670949d3c22788269bdbc54215afffa42cafd0b4a7a"),
    "avx2": (19153728, "e7d5de68cc8fc610c3c961c47f879451db9bee4a2df152e9a66f1078072e7f28"),
    "vulkan": (66342968, "db2c7938392ff08ec8b50b8afb90f8bd3d0111eccf5943df2f51c40a0368fec2"),
    "small": (487601967, "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b"),
    "turbo": (574041195, "394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2"),
}
CURRENT_ASSETS = {
    "cpu": ("voxtype-baseline", b"baseline-1.1.1-fixture\n", 0o755),
    "avx2": ("voxtype-avx2", b"avx2-1.1.1-fixture\n", 0o755),
    "vulkan": ("voxtype-vulkan", b"vulkan-1.1.1-fixture\n", 0o755),
}
CURRENT_PRODUCTION = {
    "cpu": (18838904, "cc051aac0870e21d7378edbcde3ceff10238af12a11650ab897d0ad9195225af"),
    "avx2": (19415936, "3462262980e5a75391ffdeb7d3b63f9f638d6261df042f04f9119dfb7aab7770"),
    "vulkan": (66575872, "102a7caa22facc5c257c526ae4a9e63c04c027297fec4ca370209a1f94ae9863"),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


class UpgradeMigrationExecution(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="arctic-upgrade-probe-")
        self.root = Path(self.temp.name)
        self.state_root = self.root / "var/lib"
        self.state = self.state_root / "arctic/dictation"
        self.payload = self.root / "payload"
        self.current_payload = self.root / "current-payload"
        self.current_assets = self.root / "current-assets"
        self.models = self.root / "models"
        self.cache = self.root / "cache"
        self.bin = self.root / "bin"
        self.trace = self.root / "trace"
        # MODELS is intentionally absent: the production migration must create
        # it and fsync every new directory entry through the storage anchor.
        self.state.mkdir(parents=True, mode=0o755)
        for path in (self.root / "var", self.state_root, self.state.parent, self.state):
            path.chmod(0o755)
        for path in (self.payload, self.current_payload, self.current_assets, self.cache, self.bin):
            path.mkdir(mode=0o755)
        self.user = pwd.getpwuid(os.getuid()).pw_name
        self.uid = os.getuid()
        self._write_executable(self.bin / "host-profile", "#!/bin/sh\nprintf '%s\\n' turbo-q5-v3\n")
        self._write_executable(
            self.bin / "configure",
            "#!/bin/sh\nprintf 'config:%s\\n' \"$1\" >>\"$ARCTIC_MIGRATION_TRACE\"\n",
        )
        self._write_executable(
            self.bin / "systemctl",
            "#!/bin/sh\nprintf 'systemctl:%s\\n' \"$*\" >>\"$ARCTIC_MIGRATION_TRACE\"\n"
            "[ \"${1:-}\" != --user ] || exit 42\nexit 0\n",
        )
        self._write_executable(
            self.bin / "runuser",
            "#!/bin/sh\n[ \"$1\" = -u ] || exit 2\nshift 2\n[ \"$1\" = -- ] || exit 2\nshift\nexec \"$@\"\n",
        )
        for name, data, mode in ASSETS.values():
            self._write(self.payload / name, data, mode)
        for variant, old_key in (("baseline", "cpu"), ("avx2", "avx2"), ("vulkan", "vulkan")):
            _name, data, mode = ASSETS[old_key]
            self._write(self.payload / ("voxtype-" + variant), data, mode)
        for name, data, mode in CURRENT_ASSETS.values():
            self._write(self.current_assets / name, data, mode)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _write(path, data, mode):
        path.write_bytes(data)
        path.chmod(mode)

    def _write_executable(self, path, text):
        self._write(path, text.encode(), 0o755)

    def _legacy_receipt(self, profile):
        keys = ("cpu", "model") if profile == "small-v2" else ("cpu", "avx2", "vulkan", "model")
        model = "small" if profile == "small-v2" else "large-v3-turbo-q5_0"
        cpu = "baseline" if profile == "small-v2" else "avx2"
        model_key = "small" if profile == "small-v2" else "turbo"
        files = {}
        for key in keys:
            asset_key = model_key if key == "model" else key
            name, data, _mode = ASSETS[asset_key]
            files[key] = {"sha256": digest(data), "size": len(data),
                          "mtime_ns": (self.payload / name).stat().st_mtime_ns}
        return {
            "version": "1.1.0", "source_commit": SOURCE_COMMIT,
            "profile_sha256": PROFILE_SHA[profile], "profile": profile,
            "model": model, "cpu_variant": cpu,
            "model_download_bytes": len(ASSETS[model_key][1]),
            "download_bytes": 506181191 if profile == "small-v2" else 678117115,
            "files": files,
        }

    def _json(self, name, value):
        path = self.state / name
        path.write_text(json.dumps(value, separators=(",", ":")) + "\n")
        path.chmod(0o644)

    def _direct_receipt(self, profile, backend="cpu"):
        cpu = "baseline" if profile == "small-v2" else "avx2"
        binary_key = "cpu" if cpu == "baseline" else "avx2"
        model_key = "small" if profile == "small-v2" else "turbo"
        model_name, model_data, _mode = ASSETS[model_key]
        _old_name, binary_data, _mode = ASSETS[binary_key]
        receipt = {
            "integration": "upstream-direct-v1", "version": "1.1.0",
            "source_commit": SOURCE_COMMIT,
            "release_signing_fingerprint": "9CCF7915B750CAE8B095ED1AA3FC9F33FD209279",
            "user": self.user, "profile": profile, "binary": "voxtype-" + cpu,
            "binary_bytes": len(binary_data), "binary_sha256": digest(binary_data),
            "model_path": str(self.models / model_name),
            "model": model_name.removeprefix("ggml-"),
            "model_bytes": len(model_data), "model_sha256": digest(model_data),
            "backend": backend,
        }
        if backend == "vulkan":
            vulkan_data = ASSETS["vulkan"][1]
            receipt.update(vulkan_binary="voxtype-vulkan",
                           vulkan_binary_bytes=len(vulkan_data),
                           vulkan_binary_sha256=digest(vulkan_data))
        return receipt

    def _current_receipt(self, profile, backend="cpu"):
        cpu = "baseline" if profile == "small-v2" else "avx2"
        binary_key = "cpu" if cpu == "baseline" else "avx2"
        model_key = "small" if profile == "small-v2" else "turbo"
        model_name, model_data, _mode = ASSETS[model_key]
        _binary_name, binary_data, _mode = CURRENT_ASSETS[binary_key]
        receipt = {
            "integration": "upstream-direct-v1", "version": "1.1.1",
            "source_commit": "014c56105b2f071bb3457c51a95c38be380e5124",
            "release_signing_fingerprint": "9CCF7915B750CAE8B095ED1AA3FC9F33FD209279",
            "user": self.user, "profile": profile, "binary": "voxtype-" + cpu,
            "binary_bytes": len(binary_data), "binary_sha256": digest(binary_data),
            "model_path": str(self.models / model_name),
            "model": model_name.removeprefix("ggml-"),
            "model_bytes": len(model_data), "model_sha256": digest(model_data),
            "backend": backend,
        }
        if backend == "vulkan":
            vulkan_data = CURRENT_ASSETS["vulkan"][1]
            receipt.update(vulkan_binary="voxtype-vulkan",
                           vulkan_binary_bytes=len(vulkan_data),
                           vulkan_binary_sha256=digest(vulkan_data))
        return receipt

    def _fixture_setup(self, crash_before_marker=False, online_failure=False):
        text = SETUP.read_text()
        replacements = {}
        for key, (_name, data, _mode) in ASSETS.items():
            old_size, old_sha = PRODUCTION[key]
            replacements[str(old_size)] = str(len(data))
            replacements[old_sha] = digest(data)
        for key, (_name, data, _mode) in CURRENT_ASSETS.items():
            old_size, old_sha = CURRENT_PRODUCTION[key]
            replacements[str(old_size)] = str(len(data))
            replacements[old_sha] = digest(data)
        for old, new in replacements.items():
            text = text.replace(old, new)
        text = text.replace(
            "readonly STATE=/var/lib/arctic/dictation DEST=/opt/arctic/voxtype/1.1.1 MODELS=/opt/arctic/voxtype/models",
            f"readonly STATE={self.state} DEST={self.current_payload} MODELS={self.models}",
        ).replace(
            "readonly PREVIOUS_DEST=/opt/arctic/voxtype/1.1.0",
            f"readonly PREVIOUS_DEST={self.payload}",
        ).replace(
            "readonly CACHE=/var/cache/arctic/voxtype", f"readonly CACHE={self.cache}"
        ).replace(
            "readonly STATE_ROOT=/var/lib STORAGE_ROOT=/opt",
            f"readonly STATE_ROOT={self.state_root} STORAGE_ROOT={self.root}",
        ).replace(
            "/usr/libexec/arctic/arctic-voxtype-host-profile", str(self.bin / "host-profile")
        ).replace(
            "/usr/libexec/arctic/arctic-voxtype-configure", str(self.bin / "configure")
        ).replace(
            "/opt/arctic/voxtype/models/", str(self.models) + "/"
        ).replace(
            "local lockdir=/run/lock/arctic-voxtype-setup", f"local lockdir={self.root / 'lock'}"
        ).replace(
            "-o root -g root ", ""
        ).replace(
            "== 0:755", f"== {self.uid}:755"
        ).replace(
            "== 0:700", f"== {self.uid}:700"
        ).replace(
            "== 0:644", f"== {self.uid}:644"
        ).replace(
            '== "0:$mode"', f'== "{self.uid}:$mode"'
        ).replace(
            "info.st_uid != 0", f"info.st_uid != {self.uid}"
        ).replace(
            "before.st_uid != 0", f"before.st_uid != {self.uid}"
        ).replace(
            "[[ $EUID -eq 0 ]]", f"[[ $EUID -eq {self.uid} ]]"
        ).replace(
            'if [ -S "/run/user/$uid/bus" ]; then', "if true; then"
        )
        start = text.index("prepare_packaged_release_metadata() {")
        end = text.index("\n}\n", start) + 3
        stub = """prepare_packaged_release_metadata() {
    local tmp=$1 variant=$3 name bytes sha
    local -a values
    name="voxtype-$VERSION-linux-x86_64-$variant"
    mapfile -t values < <(asset_values "$variant")
    bytes=${values[0]}; sha=${values[1]}
    printf '%s  %s\n' "$sha" "$name" >"$tmp/SHA256SUMS.txt"
    printf 'provenance:%s\n' "$variant" >>"$ARCTIC_MIGRATION_TRACE"
}
"""
        text = text[:start] + stub + text[end:]
        start = text.index("prepare_release_metadata() {")
        end = text.index("\n}\n", start) + 3
        if online_failure:
            online = """prepare_release_metadata() {
    printf 'network-failed\n' >>"$ARCTIC_MIGRATION_TRACE"
    return 99
}
"""
        else:
            online = """prepare_release_metadata() {
    printf 'network\n' >>"$ARCTIC_MIGRATION_TRACE"
    printf '%s  voxtype-%s-linux-x86_64-baseline\n%s  voxtype-%s-linux-x86_64-avx2\n' \
        "$BASELINE_SHA" "$VERSION" "$AVX2_SHA" "$VERSION" >"$1/SHA256SUMS.txt"
}
"""
        text = text[:start] + online + text[end:]
        start = text.index("install_asset() {")
        end = text.index("\n}\n", start) + 3
        install_asset = """install_asset() {
    local variant=$1 target="$DEST/voxtype-$1"
    cp -- "$ARCTIC_CURRENT_ASSETS/voxtype-$variant" "$target.new"
    chmod 0755 "$target.new"
    mv -f -- "$target.new" "$target"
}
"""
        text = text[:start] + install_asset + text[end:]
        sync_tree = 'durable_sync_tree() {\n'
        self.assertIn(sync_tree, text)
        text = text.replace(
            sync_tree,
            sync_tree + "    printf 'sync-tree:%s:%s\\n' \"$1\" \"$2\" >>\"$ARCTIC_MIGRATION_TRACE\"\n",
            1,
        )
        if crash_before_marker:
            commit = 'durable_atomic_text "$STATE/upstream-direct-v1" 0644 upstream-direct-v1'
            self.assertIn(commit, text)
            text = text.replace(commit, "exit 91\n    " + commit, 1)
        suffix = "-crash" if crash_before_marker else "-network-failure" if online_failure else ""
        path = self.root / ("setup" + suffix)
        self._write_executable(path, text)
        return path

    def _run(self, script, check=True, verb="--migrate-legacy"):
        env = dict(os.environ, PATH=str(self.bin) + ":/usr/bin:/bin",
                   ARCTIC_MIGRATION_TRACE=str(self.trace),
                   ARCTIC_CURRENT_ASSETS=str(self.current_assets), PKEXEC_UID=str(self.uid))
        if verb == "--install-offline":
            argv = [str(script), "--install", self.user, "--offline"]
        elif verb in ("--backend-cpu", "--backend-vulkan"):
            argv = [str(script), "--backend", verb.removeprefix("--backend-")]
        else:
            argv = [str(script), verb] + ([self.user] if verb == "--migrate-legacy" else [])
        return subprocess.run(argv, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=30, check=check)

    def _assert_legacy_present(self):
        for name, _data, _mode in ASSETS.values():
            self.assertTrue((self.payload / name).is_file(), name)

    def _assert_legacy_removed(self):
        for name, _data, _mode in ASSETS.values():
            self.assertFalse((self.payload / name).exists(), name)

    def _prepare_current_vulkan(self):
        self.models.mkdir(mode=0o755)
        self._write(self.models / "ggml-large-v3-turbo-q5_0.bin", ASSETS["turbo"][1], 0o644)
        for key in ("avx2", "vulkan"):
            name, data, mode = CURRENT_ASSETS[key]
            self._write(self.current_payload / name, data, mode)
        self._json("verified.json", self._current_receipt("turbo-q5-v3", "vulkan"))
        self._write(self.state / "backend", b"vulkan\n", 0o644)
        self._write(self.state / "upstream-direct-v1", b"upstream-direct-v1\n", 0o644)

    def _assert_strict_cpu_receipt(self):
        receipt = json.loads((self.state / "verified.json").read_text())
        self.assertEqual(receipt["backend"], "cpu")
        self.assertEqual(set(receipt), {
            "integration", "version", "source_commit", "release_signing_fingerprint",
            "user", "profile", "binary", "binary_bytes", "binary_sha256",
            "model_path", "model", "model_bytes", "model_sha256", "backend",
        })

    def test_vulkan_to_cpu_removes_vulkan_only_attestation(self):
        self._prepare_current_vulkan()
        self._run(self._fixture_setup(), verb="--backend-cpu")
        self.assertEqual((self.state / "backend").read_text(), "cpu\n")
        self._assert_strict_cpu_receipt()

    def test_failed_vulkan_reenable_leaves_reusable_cpu_receipt_across_crash(self):
        self._prepare_current_vulkan()
        self._write_executable(self.bin / "vulkaninfo", "#!/bin/sh\nexit 44\n")
        failed = self._run(self._fixture_setup(), check=False, verb="--backend-vulkan")
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual((self.state / "backend").read_text(), "cpu\n")
        self.assertEqual((self.state / "setup.error").read_text(), "backend-vulkan\n")
        self._assert_strict_cpu_receipt()
        network_count = self.trace.read_text().splitlines().count("network")

        self._write(self.state / "user", (self.user + "\n").encode(), 0o600)
        self._write(self.state / "pending", b"1.1.1\n", 0o644)
        (self.state / "upstream-direct-v1").unlink()
        crashed = self._run(self._fixture_setup(crash_before_marker=True), check=False,
                            verb="--resume")
        self.assertEqual(crashed.returncode, 91, crashed.stderr.decode())
        self._assert_strict_cpu_receipt()
        self.assertFalse((self.state / "verified.json.rejected-upstream-direct-v1").exists())
        self.assertEqual(self.trace.read_text().splitlines().count("network"), network_count)
        self.assertIn("provenance:avx2", self.trace.read_text().splitlines())

        self._run(self._fixture_setup(), verb="--resume")
        self._assert_strict_cpu_receipt()
        self.assertTrue((self.state / "upstream-direct-v1").is_file())
        self.assertFalse((self.state / "verified.json.rejected-upstream-direct-v1").exists())

    def test_old_stable_profile_wins_and_crash_retries_without_network(self):
        self._json("verified.json", self._legacy_receipt("small-v2"))
        self._json("profile-selection.json", {"selection": "recommended"})
        queued = self._run(self._fixture_setup(), check=False)
        self.assertNotEqual(queued.returncode, 0)
        self.assertTrue((self.state / "pending").is_file())
        self.assertFalse((self.state / "upstream-direct-v1").exists())
        self._assert_legacy_present()

        crashed = self._run(self._fixture_setup(crash_before_marker=True), check=False, verb="--resume")
        self.assertEqual(crashed.returncode, 91, crashed.stderr.decode())
        self.assertTrue((self.state / "pending").is_file())
        self.assertFalse((self.state / "upstream-direct-v1").exists())
        self._assert_legacy_present()
        self.assertTrue(self.models.is_dir())
        self.assertTrue((self.models / "ggml-small.bin").is_file())
        self.assertEqual(json.loads((self.state / "verified.json").read_text())["profile"], "small-v2")

        network_count = self.trace.read_text().splitlines().count("network")
        self._run(self._fixture_setup(), verb="--resume")
        self.assertEqual((self.state / "upstream-direct-v1").read_text(), "upstream-direct-v1\n")
        self.assertFalse((self.state / "pending").exists())
        self.assertFalse((self.state / "verified.json.rejected-upstream-direct-v1").exists())
        self._assert_legacy_removed()
        receipt = json.loads((self.state / "verified.json").read_text())
        self.assertEqual((receipt["profile"], receipt["binary"]), ("small-v2", "voxtype-baseline"))
        self.assertTrue((self.current_payload / "voxtype-baseline").is_file())
        self.assertTrue((self.models / "ggml-small.bin").is_file())
        self.assertEqual(self.trace.read_text().splitlines().count("network"), network_count)

    def test_verified_turbo_wins_over_interrupted_compatibility_change(self):
        self._json("verified.json", self._legacy_receipt("turbo-q5-v3"))
        self._json("profile-selection.json", {"selection": "compatibility"})
        self.assertNotEqual(self._run(self._fixture_setup(), check=False).returncode, 0)
        self._run(self._fixture_setup(), verb="--resume")
        receipt = json.loads((self.state / "verified.json").read_text())
        self.assertEqual((receipt["profile"], receipt["binary"]), ("turbo-q5-v3", "voxtype-avx2"))
        self.assertTrue((self.current_payload / "voxtype-avx2").is_file())
        self.assertTrue((self.models / "ggml-large-v3-turbo-q5_0.bin").is_file())
        self._assert_legacy_removed()

    def test_direct_1_1_0_cpu_upgrade_preserves_profile_and_reuses_model(self):
        self.models.mkdir(mode=0o755)
        self._write(self.models / "ggml-small.bin", ASSETS["small"][1], 0o644)
        self._json("verified.json", self._direct_receipt("small-v2"))
        self._write(self.state / "upstream-direct-v1", b"upstream-direct-v1\n", 0o644)
        self.assertNotEqual(self._run(self._fixture_setup(), check=False).returncode, 0)
        self._run(self._fixture_setup(), verb="--resume")
        receipt = json.loads((self.state / "verified.json").read_text())
        self.assertEqual((receipt["version"], receipt["profile"], receipt["backend"]),
                         ("1.1.1", "small-v2", "cpu"))
        self.assertFalse((self.state / "verified.json.rejected-upstream-direct-v1").exists())
        self.assertTrue((self.current_payload / "voxtype-baseline").is_file())
        self.assertFalse((self.payload / "voxtype-baseline").exists())

    def test_direct_1_1_0_vulkan_upgrade_is_reverified_on_cpu(self):
        self.models.mkdir(mode=0o755)
        self._write(self.models / "ggml-large-v3-turbo-q5_0.bin", ASSETS["turbo"][1], 0o644)
        self._json("verified.json", self._direct_receipt("turbo-q5-v3", "vulkan"))
        self._write(self.state / "upstream-direct-v1", b"upstream-direct-v1\n", 0o644)
        self.assertNotEqual(self._run(self._fixture_setup(), check=False).returncode, 0)
        self._run(self._fixture_setup(), verb="--resume")
        receipt = json.loads((self.state / "verified.json").read_text())
        self.assertEqual((receipt["version"], receipt["profile"], receipt["backend"]),
                         ("1.1.1", "turbo-q5-v3", "cpu"))
        self.assertNotIn("vulkan_binary", receipt)
        self.assertFalse((self.state / "verified.json.rejected-upstream-direct-v1").exists())
        self.assertTrue((self.current_payload / "voxtype-avx2").is_file())
        self.assertFalse((self.payload / "voxtype-vulkan").exists())

    def test_trusted_profile_selection_is_used_without_receipt(self):
        self._json("profile-selection.json", {"selection": "compatibility"})
        self.assertNotEqual(self._run(self._fixture_setup(), check=False).returncode, 0)
        self._run(self._fixture_setup(), verb="--resume")
        receipt = json.loads((self.state / "verified.json").read_text())
        self.assertEqual(receipt["profile"], "small-v2")
        self.assertTrue((self.models / "ggml-small.bin").is_file())

    def test_invalid_receipt_fails_closed_then_online_resume_repairs(self):
        self._json("verified.json", {"profile": "small-v2"})
        self._json("profile-selection.json", {"selection": "compatibility"})
        result = self._run(self._fixture_setup(), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.state / "pending").is_file())
        self.assertFalse((self.state / "upstream-direct-v1").exists())
        self._assert_legacy_present()
        self.assertFalse((self.current_payload / "voxtype-baseline").exists())
        self.assertNotIn("network", self.trace.read_text())
        self.assertNotIn("provenance", self.trace.read_text())

        self._run(self._fixture_setup(), verb="--resume")
        self.assertTrue((self.state / "verified.json.rejected-upstream-direct-v1").is_file())
        self.assertTrue((self.state / "profile-selection.json.rejected-upstream-direct-v1").is_file())
        self.assertEqual(json.loads((self.state / "verified.json").read_text())["profile"], "turbo-q5-v3")
        self.assertEqual((self.state / "setup.state").read_text(), "ready\n")
        self.assertFalse((self.state / "pending").exists())
        self.assertIn("network", self.trace.read_text())
        self._assert_legacy_removed()

    def test_postcommit_user_service_failure_keeps_ready_commit(self):
        self._json("verified.json", self._legacy_receipt("small-v2"))
        self.assertNotEqual(self._run(self._fixture_setup(), check=False).returncode, 0)
        self._run(self._fixture_setup(), verb="--resume")
        self.assertTrue((self.state / "upstream-direct-v1").is_file())
        self.assertEqual((self.state / "setup.state").read_text(), "ready\n")
        self.assertFalse((self.state / "setup.error").exists())
        self.assertFalse((self.state / "pending").exists())
        trace = self.trace.read_text()
        self.assertIn("systemctl:--user daemon-reload", trace)
        self.assertIn("systemctl:--user enable --now voxtype.service", trace)

    def test_invalid_receipt_explicit_retry_repairs_online(self):
        self._json("verified.json", {"profile": "turbo-q5-v3", "files": {}})
        failed = self._run(self._fixture_setup(), check=False)
        self.assertNotEqual(failed.returncode, 0)
        failed_resume = self._run(
            self._fixture_setup(online_failure=True), check=False, verb="--resume"
        )
        self.assertEqual(failed_resume.returncode, 1, failed_resume.stderr.decode())
        self.assertTrue((self.state / "pending").is_file())
        self.assertFalse((self.state / "upstream-direct-v1").exists())
        self.assertEqual((self.state / "setup.state").read_text(), "failed\n")
        self.assertEqual((self.state / "setup.error").read_text(), "setup\n")
        self.assertTrue((self.state / "verified.json.rejected-upstream-direct-v1").is_file())
        self._assert_legacy_present()
        self._run(self._fixture_setup(), verb="--retry")
        self.assertTrue((self.state / "verified.json.rejected-upstream-direct-v1").is_file())
        self.assertTrue((self.state / "upstream-direct-v1").is_file())
        self.assertEqual((self.state / "setup.state").read_text(), "ready\n")
        self.assertFalse((self.state / "setup.error").exists())
        self.assertFalse((self.state / "pending").exists())
        self.assertIn("network", self.trace.read_text())
        self._assert_legacy_removed()

    def test_offline_queue_creates_and_syncs_state_chain_before_writes(self):
        shutil.rmtree(self.state.parent)
        self.assertTrue(self.state_root.is_dir())
        self._run(self._fixture_setup(), verb="--install-offline")
        self.assertEqual((self.state / "user").read_text(), self.user + "\n")
        self.assertEqual((self.state / "pending").read_text(), "1.1.1\n")
        self.assertEqual((self.state / "setup.state").read_text(), "queued\n")
        for path in (self.state.parent, self.state):
            self.assertTrue(path.is_dir())
            self.assertEqual(path.stat().st_mode & 0o777, 0o755)
        trace = self.trace.read_text().splitlines()
        self.assertIn(f"sync-tree:{self.state}:{self.state_root}", trace)


if __name__ == "__main__":
    unittest.main()
