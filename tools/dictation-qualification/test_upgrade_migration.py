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
import time
import unittest


ROOT = Path(__file__).resolve().parents[2]
SETUP = ROOT / "packaging/dictation/arctic-voxtype-setup"
STATUS = ROOT / "packaging/dictation/arctic-dictation"
LAUNCHER = ROOT / "packaging/dictation/voxtype"
CONFIGURE = ROOT / "packaging/dictation/arctic-voxtype-configure"
SOURCE_COMMIT = "e2638ca63f566f1682bcedc0abea8e4b25211c21"
PROFILE_SHA = {
    "small-v2": "d4b9326169fe0773b36857ce4b2c52d31294c4c421933c5fbb41422227e92756",
    "turbo-q5-v3": "dfc1e2252ca033888fd0262f73fd4643066c736b9d696e4b7481875e76ed4191",
}
ASSETS = {
    "cpu": ("voxtype-cpu", b"#!/bin/sh\nprintf 'idle\\n'\n", 0o755),
    "avx2": ("voxtype-cpu-avx2", b"#!/bin/sh\nprintf 'idle\\n'\n", 0o755),
    "vulkan": ("voxtype-vulkan", b"#!/bin/sh\nprintf 'idle\\n'\n", 0o755),
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
    "cpu": ("voxtype-baseline", b"#!/bin/sh\nprintf 'baseline\\n'\n", 0o755),
    "avx2": ("voxtype-avx2", b"#!/bin/sh\nprintf 'avx2\\n'\n", 0o755),
    "vulkan": ("voxtype-vulkan", b"#!/bin/sh\nprintf 'vulkan\\n'\n", 0o755),
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
            "#!/bin/sh\n[ \"$1\" = -u ] || exit 2\n"
            "printf 'runuser:%s\\n' \"$2\" >>\"$ARCTIC_MIGRATION_TRACE\"\n"
            "shift 2\n[ \"$1\" = -- ] || exit 2\nshift\nexec \"$@\"\n",
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

    def _direct_receipt(self, profile, backend="cpu", user=None):
        cpu = "baseline" if profile == "small-v2" else "avx2"
        binary_key = "cpu" if cpu == "baseline" else "avx2"
        model_key = "small" if profile == "small-v2" else "turbo"
        model_name, model_data, _mode = ASSETS[model_key]
        _old_name, binary_data, _mode = ASSETS[binary_key]
        receipt = {
            "integration": "upstream-direct-v1", "version": "1.1.0",
            "source_commit": SOURCE_COMMIT,
            "release_signing_fingerprint": "9CCF7915B750CAE8B095ED1AA3FC9F33FD209279",
            "user": self.user if user is None else user,
            "profile": profile, "binary": "voxtype-" + cpu,
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

    def _fixture_setup(self, crash_before_marker=False, online_failure=False,
                       crash_after_vulkan_receipt=False, crash_after_cpu_selector=False):
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
        ).replace(
            "timeout 120", "timeout 1"
        ).replace(
            "timeout 15", "timeout 1"
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
        if crash_after_vulkan_receipt:
            commit = 'update_receipt_backend vulkan "$VULKAN_BYTES" "$VULKAN_SHA"'
            self.assertIn(commit, text)
            text = text.replace(commit, commit + "\n            exit 92", 1)
        if crash_after_cpu_selector:
            start = text.index("set_backend() {")
            commit = 'durable_atomic_text "$STATE/backend" 0644 cpu'
            self.assertIn(commit, text[start:])
            tail = text[start:].replace(commit, commit + "\n            exit 93", 1)
            text = text[:start] + tail
        suffix = ("-crash" if crash_before_marker else
                  "-network-failure" if online_failure else
                  "-vulkan-receipt-crash" if crash_after_vulkan_receipt else
                  "-cpu-selector-crash" if crash_after_cpu_selector else "")
        path = self.root / ("setup" + suffix)
        self._write_executable(path, text)
        return path

    def _fixture_status(self):
        text = STATUS.read_text().replace(
            "/var/lib/arctic/dictation", str(self.state)
        ).replace(
            "/usr/libexec/arctic/arctic-voxtype-host-profile", str(self.bin / "host-profile")
        ).replace(
            "/opt/arctic/voxtype/1.1.1", str(self.current_payload)
        ).replace(
            "/opt/arctic/voxtype/1.1.0", str(self.payload)
        ).replace(
            "/opt/arctic/voxtype/models", str(self.models)
        ).replace(
            str(CURRENT_PRODUCTION["vulkan"][0]), str(len(CURRENT_ASSETS["vulkan"][1]))
        ).replace(
            CURRENT_PRODUCTION["vulkan"][1], digest(CURRENT_ASSETS["vulkan"][1])
        )
        for key in ("cpu", "avx2", "vulkan"):
            size, sha = PRODUCTION[key]
            text = text.replace(str(size), str(len(ASSETS[key][1])))
            text = text.replace(sha, digest(ASSETS[key][1]))
        for key in ("small", "turbo"):
            size, sha = PRODUCTION[key]
            text = text.replace(str(size), str(len(ASSETS[key][1])))
            text = text.replace(sha, digest(ASSETS[key][1]))
        path = self.root / "status"
        self._write_executable(path, text)
        return path

    def _fixture_launcher(self):
        text = LAUNCHER.read_text().replace(
            "current_lib=/opt/arctic/voxtype/1.1.1", "current_lib=" + str(self.current_payload)
        ).replace(
            "previous_lib=/opt/arctic/voxtype/1.1.0", "previous_lib=" + str(self.payload)
        ).replace(
            "/var/lib/arctic/dictation", str(self.state)
        ).replace(
            "/usr/libexec/arctic/arctic-voxtype-host-profile", str(self.bin / "host-profile")
        )
        for key in ("cpu", "avx2", "vulkan"):
            size, sha = CURRENT_PRODUCTION[key]
            text = text.replace(str(size), str(len(CURRENT_ASSETS[key][1])))
            text = text.replace(sha, digest(CURRENT_ASSETS[key][1]))
            old_size, old_sha = PRODUCTION[key]
            text = text.replace(str(old_size), str(len(ASSETS[key][1])))
            text = text.replace(old_sha, digest(ASSETS[key][1]))
        path = self.root / "launcher"
        self._write_executable(path, text)
        return path

    def _fixture_configure(self):
        text = CONFIGURE.read_text().replace(
            "/opt/arctic/voxtype/models", str(self.models)
        ).replace(
            "/opt/arctic/voxtype/1.1.1", str(self.current_payload)
        )
        path = self.root / "configure-real"
        self._write_executable(path, text)
        return path

    def _status(self):
        runtime = self.root / "runtime"
        runtime.mkdir(mode=0o700, exist_ok=True)
        shutil.copy2(self._fixture_launcher(), self.bin / "voxtype")
        result = subprocess.run(
            [str(self._fixture_status()), "status"],
            env=dict(os.environ, PATH=str(self.bin) + ":/usr/bin:/bin",
                     XDG_RUNTIME_DIR=str(runtime), HOME=str(self.root)),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=10,
        )
        return json.loads(result.stdout)

    def _run(self, script, check=True, verb="--migrate-legacy", user=None):
        env = dict(os.environ, PATH=str(self.bin) + ":/usr/bin:/bin",
                   ARCTIC_MIGRATION_TRACE=str(self.trace),
                   ARCTIC_CURRENT_ASSETS=str(self.current_assets), PKEXEC_UID=str(self.uid))
        if verb == "--install-offline":
            argv = [str(script), "--install", self.user, "--offline"]
        elif verb in ("--backend-cpu", "--backend-vulkan"):
            argv = [str(script), "--backend", verb.removeprefix("--backend-")]
        else:
            argv = [str(script), verb] + ([self.user if user is None else user]
                                          if verb == "--migrate-legacy" else [])
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

    def test_current_1_1_1_receipt_queues_trusted_config_migration_once(self):
        self._prepare_current_vulkan()
        setup = self._fixture_setup()
        self._run(setup, verb="--queue-config-resident-v1")
        pending = self.state / "config-resident-v1.pending"
        self.assertEqual(pending.read_bytes(), b"resident-model-v1\n")
        self.assertEqual(pending.stat().st_mode & 0o777, 0o644)

        generation = self.state / "config-generation-resident-v1.json"
        self._json("config-generation-resident-v1.json", {
            "schema": "arctic-voxtype-config-generation-v1",
            "migration": "resident-model-v1", "user": self.user,
            "generation": "resident-model-v1", "outcome": "already-current",
        })
        self._run(setup, verb="--queue-config-resident-v1")
        self.assertFalse(pending.exists())
        self.assertEqual(json.loads(generation.read_text())["outcome"], "already-current")

    def _assert_strict_cpu_receipt(self):
        receipt = json.loads((self.state / "verified.json").read_text())
        self.assertEqual(self.state.joinpath("verified.json").stat().st_mode & 0o777, 0o644)
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

    def test_cpu_transition_crash_mismatch_fails_closed_and_retries(self):
        self._prepare_current_vulkan()
        crashed = self._run(self._fixture_setup(crash_after_cpu_selector=True),
                            check=False, verb="--backend-cpu")
        self.assertEqual(crashed.returncode, 93, crashed.stderr.decode())
        self.assertEqual((self.state / "backend").read_text(), "cpu\n")
        self.assertEqual(json.loads((self.state / "verified.json").read_text())["backend"],
                         "vulkan")
        launched = subprocess.run([str(self._fixture_launcher()), "status"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertEqual(launched.returncode, 69)
        status = self._status()
        self.assertEqual((status["state"], status["ready"]), ("error", False))
        self.assertIn("interrupted", status["error"])
        self._run(self._fixture_setup(), verb="--backend-cpu")
        self._assert_strict_cpu_receipt()

    def test_launcher_uses_attested_cpu_profile_not_current_host_probe(self):
        self.models.mkdir(mode=0o755)
        self._write(self.models / "ggml-small.bin", ASSETS["small"][1], 0o644)
        self._write(self.models / "ggml-large-v3-turbo-q5_0.bin", ASSETS["turbo"][1], 0o644)
        for key in ("cpu", "avx2"):
            name, data, mode = CURRENT_ASSETS[key]
            self._write(self.current_payload / name, data, mode)
        self._write(self.state / "backend", b"cpu\n", 0o644)
        self._write(self.state / "upstream-direct-v1", b"upstream-direct-v1\n", 0o644)
        launcher = self._fixture_launcher()

        # host-profile fixture reports turbo, but a preserved small receipt
        # must still execute only its attested baseline binary.
        self._json("verified.json", self._current_receipt("small-v2"))
        small = subprocess.run([str(launcher), "--version"], text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               check=True, timeout=10)
        self.assertEqual(small.stdout, "baseline\n")

        self._json("verified.json", self._current_receipt("turbo-q5-v3"))
        turbo = subprocess.run([str(launcher), "--version"], text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               check=True, timeout=10)
        self.assertEqual(turbo.stdout, "avx2\n")

        self._write_executable(self.bin / "host-profile",
                               "#!/bin/sh\nprintf '%s\\n' small-v2\n")
        unsafe = subprocess.run([str(launcher), "--version"], text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertEqual(unsafe.returncode, 69)
        self.assertEqual(unsafe.stdout, "")

        malformed = self._current_receipt("small-v2")
        malformed["binary"] = "voxtype-avx2"
        self._json("verified.json", malformed)
        rejected = subprocess.run([str(launcher), "--version"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertEqual(rejected.returncode, 69)

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

    def test_exit_zero_cpu_fallback_cannot_publish_vulkan(self):
        self._prepare_current_vulkan()
        self._write_executable(self.bin / "vulkaninfo", "#!/bin/sh\nexit 0\n")
        self._write_executable(
            self.current_assets / "voxtype-vulkan",
            "#!/bin/sh\n"
            "printf '%s\\n' 'whisper_init_with_params_no_state: use gpu = 1' >&2\n"
            "printf '%s\\n' 'whisper_backend_init_gpu: no GPU found' >&2\n"
            "exit 0\n",
        )
        failed = self._run(self._fixture_setup(), check=False, verb="--backend-vulkan")
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual((self.state / "backend").read_text(), "cpu\n")
        self._assert_strict_cpu_receipt()
        self.assertEqual((self.state / "setup.error").read_text(), "backend-vulkan\n")

    def test_wedged_vulkaninfo_is_bounded_and_retry_lock_is_available(self):
        self._prepare_current_vulkan()
        self._write_executable(self.bin / "vulkaninfo", "#!/bin/sh\nsleep 2\n")
        started = time.monotonic()
        failed = self._run(self._fixture_setup(), check=False, verb="--backend-vulkan")
        elapsed = time.monotonic() - started
        self.assertNotEqual(failed.returncode, 0)
        self.assertLess(elapsed, 1.8)
        self.assertEqual((self.state / "backend").read_text(), "cpu\n")
        self._assert_strict_cpu_receipt()
        self.assertEqual((self.state / "setup.error").read_text(), "backend-vulkan\n")

        self._write_executable(self.bin / "vulkaninfo", "#!/bin/sh\nexit 0\n")
        self._write_executable(
            self.current_assets / "voxtype-vulkan",
            "#!/bin/sh\n"
            "printf '%s\\n' 'whisper_backend_init_gpu: using Vulkan0 backend' >&2\n"
            "exit 0\n",
        )
        # A timed-out probe released the global lock and a normal retry can
        # complete rather than returning the setup-busy code.
        self._run(self._fixture_setup(), verb="--backend-vulkan")
        self.assertEqual((self.state / "backend").read_text(), "vulkan\n")
        self.assertEqual(json.loads((self.state / "verified.json").read_text())["backend"],
                         "vulkan")

    def test_vulkan_proof_accepts_official_device_outcome_without_backend_word(self):
        self._prepare_current_vulkan()
        self._write_executable(self.bin / "vulkaninfo", "#!/bin/sh\nexit 0\n")
        self._write_executable(
            self.current_assets / "voxtype-vulkan",
            "#!/bin/sh\n"
            "printf '%s\\n' 'ggml_vulkan: Found 1 Vulkan devices:' >&2\n"
            "printf '%s\\n' 'whisper_backend_init_gpu: found GPU device 0: "
            "llvmpipe (LLVM 20.1.8, 256 bits) (type: 2, cnt: 1)' >&2\n"
            "exit 0\n",
        )
        self._run(self._fixture_setup(), verb="--backend-vulkan")
        self.assertEqual((self.state / "backend").read_text(), "vulkan\n")
        self.assertEqual(json.loads((self.state / "verified.json").read_text())["backend"],
                         "vulkan")

    def test_vulkan_proof_rejects_contradiction_intent_unknown_oversize_and_nonzero(self):
        self._prepare_current_vulkan()
        self._write_executable(self.bin / "vulkaninfo", "#!/bin/sh\nexit 0\n")
        cases = {
            "positive-and-negative": (
                "printf '%s\\n' 'whisper_backend_init_gpu: found GPU device 0: llvmpipe' >&2\n"
                "printf '%s\\n' 'ggml_vulkan: Found 0 Vulkan devices' >&2\n", 0),
            "init-failure-after-positive": (
                "printf '%s\\n' 'whisper_backend_init_gpu: found GPU device 0: llvmpipe' >&2\n"
                "printf '%s\\n' 'whisper_backend_init_gpu: using Vulkan0 backend' >&2\n"
                "printf '%s\\n' 'whisper_backend_init_gpu: failed to initialize Vulkan0 backend' >&2\n",
                0),
            "init-failure-before-positive": (
                "printf '%s\\n' 'whisper_backend_init_gpu: failed to initialize Vulkan0 backend' >&2\n"
                "printf '%s\\n' 'whisper_backend_init_gpu: found GPU device 0: llvmpipe' >&2\n"
                "printf '%s\\n' 'whisper_backend_init_gpu: using Vulkan0 backend' >&2\n",
                0),
            "intent-only": (
                "printf '%s\\n' 'whisper_init_with_params_no_state: use gpu = 1' >&2\n", 0),
            "unknown": ("printf '%s\\n' 'model initialized' >&2\n", 0),
            "oversize": ("head -c 1048577 /dev/zero >&2\n", 0),
            "nonzero-after-positive": (
                "printf '%s\\n' 'whisper_backend_init_gpu: using Vulkan0 backend' >&2\n", 7),
        }
        for name, (body, code) in cases.items():
            with self.subTest(name=name):
                self._write_executable(
                    self.current_assets / "voxtype-vulkan",
                    "#!/bin/sh\n" + body + f"exit {code}\n",
                )
                failed = self._run(self._fixture_setup(), check=False, verb="--backend-vulkan")
                self.assertNotEqual(failed.returncode, 0)
                self.assertEqual((self.state / "backend").read_text(), "cpu\n")
                self._assert_strict_cpu_receipt()
                self.assertEqual((self.state / "setup.error").read_text(), "backend-vulkan\n")

        self._write_executable(self.current_assets / "voxtype-vulkan",
                               "#!/bin/sh\nsleep 2\nexit 0\n")
        timed_out = self._run(self._fixture_setup(), check=False, verb="--backend-vulkan")
        self.assertNotEqual(timed_out.returncode, 0)
        self.assertEqual((self.state / "backend").read_text(), "cpu\n")
        self._assert_strict_cpu_receipt()

    def test_positive_gpu_proof_is_published_receipt_before_backend(self):
        self._prepare_current_vulkan()
        self._write_executable(self.bin / "vulkaninfo", "#!/bin/sh\nexit 0\n")
        self._write_executable(
            self.current_assets / "voxtype-vulkan",
            "#!/bin/sh\n"
            "printf '%s\\n' 'whisper_init_with_params_no_state: use gpu = 1' >&2\n"
            "printf '%s\\n' 'whisper_backend_init_gpu: using Vulkan0 backend' >&2\n"
            "exit 0\n",
        )
        self._run(self._fixture_setup(), verb="--backend-vulkan")
        receipt = json.loads((self.state / "verified.json").read_text())
        self.assertEqual((receipt["backend"], (self.state / "backend").read_text()),
                         ("vulkan", "vulkan\n"))
        self.assertEqual((self.state / "verified.json").stat().st_mode & 0o777, 0o644)
        self.assertFalse((self.state / "setup.error").exists())

        # Simulate power loss after the durable receipt but before selector.
        self._run(self._fixture_setup(), verb="--backend-cpu")
        crashed = self._run(self._fixture_setup(crash_after_vulkan_receipt=True),
                            check=False, verb="--backend-vulkan")
        self.assertEqual(crashed.returncode, 92, crashed.stderr.decode())
        self.assertEqual(json.loads((self.state / "verified.json").read_text())["backend"],
                         "vulkan")
        self.assertEqual((self.state / "backend").read_text(), "cpu\n")
        launched = subprocess.run([str(self._fixture_launcher()), "status"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertEqual(launched.returncode, 69)
        status = self._status()
        self.assertEqual((status["state"], status["ready"], status["backend"]),
                         ("error", False, "cpu"))
        self.assertIn("interrupted", status["error"])
        self._run(self._fixture_setup(), verb="--backend-cpu")
        self._assert_strict_cpu_receipt()

    def test_offline_update_keeps_verified_old_service_and_shortcut_ready(self):
        self.models.mkdir(mode=0o755)
        self._write(self.models / "ggml-small.bin", ASSETS["small"][1], 0o644)
        config = self.root / ".config/voxtype/config.toml"
        config.parent.mkdir(parents=True, mode=0o700)
        self._write(config, b'[whisper]\nlanguage = ["he", "en"]\n', 0o600)
        self._json("verified.json", self._direct_receipt("small-v2"))
        self._write(self.state / "upstream-direct-v1", b"upstream-direct-v1\n", 0o644)
        migrated = self._run(self._fixture_setup(), check=False)
        self.assertNotEqual(migrated.returncode, 0)
        self.assertEqual((self.state / "setup.error").read_text(), "setup\n")
        self._run(self._fixture_setup(), verb="--install-offline")
        self.assertFalse((self.state / "setup.error").exists())
        self.assertEqual((self.state / "setup.state").read_text(), "queued\n")
        status = self._status()
        self.assertEqual((status["state"], status["ready"], status["error"],
                          status["version"], status["upgrade_pending"]),
                         ("ready", True, "", "1.1.0", True))
        launched = subprocess.run([str(self._fixture_launcher()), "record", "toggle"],
                                  text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  check=True, timeout=10)
        self.assertEqual(launched.stdout, "idle\n")
        unit = (ROOT / "packaging/systemd/voxtype.service").read_text()
        self.assertIn("ExecStart=/usr/bin/voxtype", unit)

    def test_old_vulkan_receipt_survives_staged_cpu_selector_and_host_is_safe(self):
        self.models.mkdir(mode=0o755)
        self._write(self.models / "ggml-large-v3-turbo-q5_0.bin", ASSETS["turbo"][1], 0o644)
        self._json("verified.json", self._direct_receipt("turbo-q5-v3", "vulkan"))
        self._write(self.state / "upstream-direct-v1", b"upstream-direct-v1\n", 0o644)
        self._write(self.state / "pending", b"1.1.1\n", 0o644)
        # Simulate the crash boundary after 1.1.1 staged its CPU selector but
        # before the current receipt was atomically published.
        self._write(self.state / "backend", b"cpu\n", 0o644)
        launched = subprocess.run([str(self._fixture_launcher()), "status"], text=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  check=True, timeout=10)
        self.assertEqual(launched.stdout, "idle\n")

        self._write_executable(self.bin / "host-profile",
                               "#!/bin/sh\nprintf '%s\\n' small-v2\n")
        unsafe = subprocess.run([str(self._fixture_launcher()), "status"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertEqual(unsafe.returncode, 69)

    def test_corrupt_old_payload_fails_closed_and_is_not_migrated(self):
        self.models.mkdir(mode=0o755)
        self._write(self.models / "ggml-small.bin", ASSETS["small"][1], 0o644)
        self._json("verified.json", self._direct_receipt("small-v2"))
        self._write(self.state / "upstream-direct-v1", b"upstream-direct-v1\n", 0o644)
        binary = self.payload / "voxtype-baseline"
        damaged = binary.read_bytes().replace(b"idle", b"evil")
        self.assertEqual(len(damaged), len(binary.read_bytes()))
        self._write(binary, damaged, 0o755)
        failed = self._run(self._fixture_setup(), check=False)
        self.assertNotEqual(failed.returncode, 0)
        self.assertFalse((self.current_payload / "voxtype-baseline").exists())
        self.assertEqual((self.state / "previous-direct-rejected").read_text(), "rejected\n")
        refused = subprocess.run([str(self._fixture_launcher()), "status"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertEqual(refused.returncode, 69)
        status = self._status()
        self.assertEqual((status["ready"], status["state"]), (False, "error"))
        self.assertTrue((self.state / "pending").is_file())

    def test_extra_receipt_field_is_rejected_by_migration_and_runtime(self):
        self.models.mkdir(mode=0o755)
        self._write(self.models / "ggml-small.bin", ASSETS["small"][1], 0o644)
        receipt = self._direct_receipt("small-v2")
        receipt["unexpected"] = "field"
        self._json("verified.json", receipt)
        self._write(self.state / "upstream-direct-v1", b"upstream-direct-v1\n", 0o644)
        failed = self._run(self._fixture_setup(), check=False)
        self.assertNotEqual(failed.returncode, 0)
        self.assertTrue((self.state / "previous-direct-rejected").is_file())
        refused = subprocess.run([str(self._fixture_launcher()), "status"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertEqual(refused.returncode, 69)

    def test_timer_reconstructs_missing_queue_from_previous_receipt(self):
        self.models.mkdir(mode=0o755)
        self._write(self.models / "ggml-small.bin", ASSETS["small"][1], 0o644)
        config = self.root / ".config/voxtype/config.toml"
        config.parent.mkdir(parents=True, mode=0o700)
        self._write(config, b'[whisper]\nlanguage = ["he", "en"]\n', 0o600)
        self._json("verified.json", self._direct_receipt("small-v2"))
        self._write(self.state / "upstream-direct-v1", b"upstream-direct-v1\n", 0o644)
        condition = self._run(self._fixture_setup(), verb="--needs-resume")
        self.assertEqual(condition.returncode, 0)
        self.assertFalse((self.state / "pending").exists())
        before = self._status()
        self.assertEqual((before["ready"], before["version"], before["upgrade_pending"]),
                         (True, "1.1.0", False))

        self._run(self._fixture_setup(), verb="--resume")
        receipt = json.loads((self.state / "verified.json").read_text())
        self.assertEqual(receipt["version"], "1.1.1")
        self.assertFalse((self.state / "pending").exists())
        self.assertFalse((self.state / "previous-direct-rejected").exists())
        no_work = self._run(self._fixture_setup(), check=False, verb="--needs-resume")
        self.assertEqual(no_work.returncode, 1)
        self.assertEqual((self.state / "setup.state").read_text(), "ready\n")
        self.assertFalse((self.state / "setup.error").exists())

    def test_online_resume_switches_atomically_to_current_and_cleans_old(self):
        self.models.mkdir(mode=0o755)
        self._write(self.models / "ggml-small.bin", ASSETS["small"][1], 0o644)
        config = self.root / ".config/voxtype/config.toml"
        config.parent.mkdir(parents=True, mode=0o700)
        self._write(config, b'[whisper]\nlanguage = ["he", "en"]\n', 0o600)
        self._json("verified.json", self._direct_receipt("small-v2"))
        self._write(self.state / "upstream-direct-v1", b"upstream-direct-v1\n", 0o644)
        self._run(self._fixture_setup(), verb="--install-offline")
        old = subprocess.run([str(self._fixture_launcher()), "status"], text=True,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             check=True, timeout=10)
        self.assertEqual(old.stdout, "idle\n")

        self._run(self._fixture_setup(), verb="--resume")
        receipt = json.loads((self.state / "verified.json").read_text())
        self.assertEqual((receipt["version"], receipt["backend"]), ("1.1.1", "cpu"))
        current = subprocess.run([str(self._fixture_launcher()), "status"], text=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 check=True, timeout=10)
        self.assertEqual(current.stdout, "baseline\n")
        self.assertFalse((self.state / "pending").exists())
        self.assertFalse((self.payload / "voxtype-baseline").exists())
        status = self._status()
        self.assertEqual((status["version"], status["upgrade_pending"]), ("1.1.1", False))

    def test_pending_old_runtime_does_not_project_unrecognized_journal_text(self):
        self.models.mkdir(mode=0o755)
        self._write(self.models / "ggml-small.bin", ASSETS["small"][1], 0o644)
        config = self.root / ".config/voxtype/config.toml"
        config.parent.mkdir(parents=True, mode=0o700)
        self._write(config, b'[whisper]\nlanguage = ["he", "en"]\n', 0o600)
        self._json("verified.json", self._direct_receipt("small-v2"))
        self._write(self.state / "upstream-direct-v1", b"upstream-direct-v1\n", 0o644)
        self._write(self.state / "pending", b"1.1.1\n", 0o644)
        secret = "PRIVATE-TRANSCRIPT-SHOULD-NOT-LEAK"
        self._write_executable(self.bin / "journalctl",
                               "#!/bin/sh\nprintf '%s\\n' '" + secret + "'\n")
        status = self._status()
        self.assertNotIn(secret, json.dumps(status))
        self.assertEqual((status["ready"], status["upgrade_pending"]), (True, True))

    def test_precommit_config_validation_uses_exact_verified_binary_fresh_and_upgrade(self):
        self.models.mkdir(mode=0o755)
        model = self.models / "ggml-small.bin"
        self._write(model, ASSETS["small"][1], 0o644)
        binary = self.current_payload / "voxtype-baseline"
        home = self.root / "home"
        home.mkdir(mode=0o700)
        calls = home / "validator-calls"
        self._write_executable(
            binary,
            "#!/bin/sh\n"
            "[ \"$1\" = --config ] && [ -f \"$2\" ] && "
            "[ \"$3 $4 $5 $6\" = 'config get whisper.language --json' ] || exit 64\n"
            f"printf '%s\\n' \"$2\" >>{calls}\n",
        )
        # The strict runtime launcher must remain closed before commit.
        launch = subprocess.run([str(self._fixture_launcher()), "status"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertEqual(launch.returncode, 69)

        helper = self._fixture_configure()
        env = dict(os.environ, HOME=str(home))
        run_as_user = {}
        if os.geteuid() == 0:
            # rpmbuild runs %check as root, while production always invokes
            # this helper through runuser for the selected desktop account.
            # Preserve the helper's root refusal and exercise the real user
            # boundary rather than weakening it for the build environment.
            rejected = subprocess.run([str(helper), str(model), str(binary)], env=env,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      timeout=10)
            self.assertEqual(rejected.returncode, 77)
            self.assertFalse((home / ".config").exists())
            nobody = pwd.getpwnam("nobody")
            self.root.chmod(0o755)
            os.chown(home, nobody.pw_uid, nobody.pw_gid)
            run_as_user = {"user": nobody.pw_uid, "group": nobody.pw_gid,
                           "extra_groups": []}

        subprocess.run([str(helper), str(model), str(binary)], env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=10,
                       **run_as_user)
        config = home / ".config/voxtype/config.toml"
        self.assertIn('language = ["he", "en"]', config.read_text())

        config.write_text("[whisper]\nlanguage = \"en\"\n")
        config.chmod(0o600)
        subprocess.run([str(helper), str(model), str(binary)], env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=10,
                       **run_as_user)
        self.assertEqual((config.parent / "config.toml.pre-arctic-voxtype-v1").read_text(),
                         "[whisper]\nlanguage = \"en\"\n")
        self.assertEqual(len(calls.read_text().splitlines()), 2)

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

    def test_direct_receipt_user_overrides_passwd_first_migration_user(self):
        first, bound = "user-a", "user-b"
        first_home, bound_home = self.root / "home-a", self.root / "home-b"
        first_home.mkdir(mode=0o700); bound_home.mkdir(mode=0o700)
        self._write_executable(
            self.bin / "getent",
            "#!/bin/sh\n[ \"$1\" = passwd ] || exit 2\n"
            f"case \"$2\" in\n"
            f"  {first}) printf '%s\\n' '{first}:x:1001:1001::{first_home}:/bin/bash' ;;\n"
            f"  {bound}) printf '%s\\n' '{bound}:x:1002:1002::{bound_home}:/bin/bash' ;;\n"
            "  *) exit 2 ;;\nesac\n",
        )
        self._write_executable(
            self.bin / "id",
            "#!/bin/sh\n"
            f"[ \"${{1:-}}:${{2:-}}\" != '-u:{bound}' ] || {{ printf '%s\\n' 1002; exit 0; }}\n"
            "exec /usr/bin/id \"$@\"\n",
        )
        self.models.mkdir(mode=0o755)
        self._write(self.models / "ggml-small.bin", ASSETS["small"][1], 0o644)
        self._json("verified.json", self._direct_receipt("small-v2", user=bound))
        self._write(self.state / "upstream-direct-v1", b"upstream-direct-v1\n", 0o644)

        result = self._run(self._fixture_setup(), check=False, user=first)
        if result.returncode != 0:
            self._run(self._fixture_setup(), verb="--resume")
        receipt = json.loads((self.state / "verified.json").read_text())
        self.assertEqual(receipt["user"], bound)
        runusers = [line for line in self.trace.read_text().splitlines()
                    if line.startswith("runuser:")]
        self.assertIn("runuser:" + bound, runusers)
        self.assertNotIn("runuser:" + first, runusers)

    def test_direct_receipt_missing_bound_user_fails_closed(self):
        missing = "removed-user"
        self._write_executable(
            self.bin / "getent",
            "#!/bin/sh\n[ \"$1\" = passwd ] || exit 2\n"
            f"[ \"$2\" != {self.user} ] || exec /usr/bin/getent \"$@\"\n"
            "exit 2\n",
        )
        self.models.mkdir(mode=0o755)
        self._write(self.models / "ggml-small.bin", ASSETS["small"][1], 0o644)
        self._json("verified.json", self._direct_receipt("small-v2", user=missing))
        self._write(self.state / "upstream-direct-v1", b"upstream-direct-v1\n", 0o644)
        failed = self._run(self._fixture_setup(), check=False)
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual((self.state / "setup.error").read_text(), "setup\n")
        self.assertEqual(json.loads((self.state / "verified.json").read_text())["user"], missing)

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
