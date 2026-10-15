import hashlib
import os
import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
D = ROOT / "packaging/dictation"


class DirectUpstreamIntegration(unittest.TestCase):
    def test_status_projects_official_upstream_microphone_disconnect_errors(self):
        adapter = (D / "arctic-dictation").read_text()
        self.assertIn("*'Audio stream error, capture is now dead:'*", adapter)
        self.assertIn("*'failed during this recording; the transcript will be short or empty.'*", adapter)
        self.assertLess(adapter.index("*'Audio stream error, capture is now dead:'*"),
                        adapter.index("*'Transcription failed:'*"))

    def test_shells_parse_and_old_runtime_is_gone(self):
        for name, shell in (("voxtype", "sh"), ("arctic-dictation", "sh"), ("arctic-dictation-toggle", "sh"), ("arctic-voxtype-setup", "bash"),
                            ("arctic-voxtype-configure", "sh"),
                            ("arctic-voxtype-host-profile", "sh")):
            subprocess.run([shell, "-n", str(D / name)], check=True)
        subprocess.run(["python3", "-m", "py_compile",
                        str(D / "arctic-voxtype-migrate-config")], check=True)
        for name in ("dictation.py", "child_exec.py", "arctic-dictation-install", "arctic-dictation-setup"):
            self.assertFalse((D / name).exists(), name)

    def test_runtime_controls_call_upstream_directly(self):
        adapter = (D / "arctic-dictation").read_text()
        self.assertNotIn("record toggle", adapter)
        self.assertNotIn("record cancel", adapter)
        binds = (ROOT / "dotfiles/.config/mango/arctic/binds.conf").read_text()
        self.assertIn("spawn,arctic-dictation-toggle", binds)
        self.assertIn("voxtype record cancel", binds)
        self.assertIn("voxtype record toggle", (D / "arctic-dictation-toggle").read_text())
        shell = (ROOT / "shell/DictationService.qml").read_text()
        self.assertIn("['voxtype', 'record', 'toggle']", shell)
        self.assertIn("Session.runtimeDir + '/voxtype/state'", shell)
        settings = (ROOT / "settings/pages/DictationPage.qml").read_text()
        self.assertEqual(settings.count("enabled: page.status.ready && page.canConfigure"), 2)

    def test_release_identity_integrity_and_privacy_are_pinned(self):
        setup = (D / "arctic-voxtype-setup").read_text()
        config = (D / "arctic-voxtype-configure").read_text()
        for value in (
            "014c56105b2f071bb3457c51a95c38be380e5124",
            "9CCF7915B750CAE8B095ED1AA3FC9F33FD209279",
            "394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2",
            "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b",
            "download_pinned", "verify_signature",
        ):
            self.assertIn(value, setup)
        for value in ('language = ["he", "en"]', 'driver_order = ["wtype"]',
                      "fallback_to_clipboard = false", "on_demand_loading = false",
                      "filter_filler_words = false"):
            self.assertIn(value, config)
        unit = (ROOT / "packaging/systemd/voxtype.service").read_text()
        self.assertIn("UnsetEnvironment=RUST_LOG", unit)
        self.assertIn("ExecStart=/usr/bin/voxtype --config %h/.config/voxtype/config.toml -q daemon", unit)
        self.assertIn("VOXTYPE_REMOTE_ENDPOINT", unit)
        self.assertIn("VOXTYPE_WHISPER_API_KEY", unit)
        for name in (
            "VOXTYPE_ON_DEMAND_LOADING", "VOXTYPE_THREADS", "VOXTYPE_GPU_ISOLATION", "VOXTYPE_GPU_DEVICE",
            "VOXTYPE_FLASH_ATTENTION", "VOXTYPE_VULKAN_DEVICE", "VOXTYPE_OPENVINO_DIR", "VOXTYPE_OPENVINO_DEVICE",
            "VOXTYPE_OPENVINO_MODEL", "VOXTYPE_MAX_DURATION_SECS", "VOXTYPE_AUDIO_DEVICE", "VOXTYPE_AUDIO_FEEDBACK",
            "VOXTYPE_PAUSE_MEDIA", "VOXTYPE_DUCK_MEDIA", "VOXTYPE_DUCK_MEDIA_VOLUME_PERCENT", "VOXTYPE_DUCK_MEDIA_FADE_MS",
            "VOXTYPE_WTYPE_SHIFT_PREFIX", "VOXTYPE_PRE_TYPE_DELAY", "VOXTYPE_TYPE_DELAY", "VOXTYPE_DOTOOL_XKB_LAYOUT",
            "VOXTYPE_DOTOOL_XKB_VARIANT", "VOXTYPE_EITYPE_XKB_LAYOUT", "VOXTYPE_EITYPE_XKB_VARIANT",
            "VOXTYPE_RESTORE_CLIPBOARD_DELAY_MS", "SONIOX_API_KEY",
        ):
            self.assertIn(name, unit)
        self.assertIn("UMask=0077", unit)
        self.assertIn("RestrictAddressFamilies=AF_UNIX", unit)
        self.assertNotIn("input", unit.lower())

    def test_embedded_key_has_expected_fingerprint(self):
        out = subprocess.check_output(["gpg", "--batch", "--show-keys", "--with-colons", str(D / "voxtype-release-key.asc")], text=True)
        fingerprints = [line.split(":")[9] for line in out.splitlines() if line.startswith("fpr:")]
        self.assertIn("9CCF7915B750CAE8B095ED1AA3FC9F33FD209279", fingerprints)

    def test_receipt_is_atomic_public_and_versioned(self):
        setup = (D / "arctic-voxtype-setup").read_text()
        self.assertIn('"integration":"upstream-direct-v1"', setup)
        self.assertIn('durable_atomic_text "$STATE/verified.json" 0644 "$receipt_json"', setup)
        self.assertIn('durable_atomic_text "$STATE/upstream-direct-v1" 0644 upstream-direct-v1', setup)
        self.assertIn("os.fsync(stream.fileno())", setup)
        self.assertIn("os.replace(temporary, path)", setup)
        self.assertIn("os.fsync(directory)", setup)
        service = (ROOT / "packaging/systemd/voxtype.service").read_text()
        self.assertIn("ConditionPathExists=/var/lib/arctic/dictation/upstream-direct-v1", service)
        self.assertIn("ConditionPathExists=%h/.config/voxtype/config.toml", service)

    def test_resident_config_migration_is_deferred_and_generation_tracked(self):
        setup = (D / "arctic-voxtype-setup").read_text()
        spec = (ROOT / "packaging/arctic-linux.spec").read_text()
        unit = (ROOT / "packaging/systemd/arctic-voxtype-config-migration.service").read_text()
        for value in ("config-resident-v1.pending", "config-generation-resident-v1.json",
                      "arctic-voxtype-config-generation-v1", "resident-model-v1",
                      "custom-preserved", "--migrate-config-resident-v1"):
            self.assertIn(value, setup)
        self.assertIn("arctic-voxtype-migrate-config", spec)
        self.assertIn("multi-user.target.wants/arctic-voxtype-config-migration.service", spec)
        self.assertIn("--queue-config-resident-v1", spec)
        self.assertIn("Before=systemd-user-sessions.service user@.service", unit)
        lowered = unit.lower()
        for dependency in ("after=network", "wants=network", "requires=network"):
            self.assertNotIn(dependency, lowered)
        self.assertIn("PrivateNetwork=yes", unit)

    def test_status_protocol_has_no_transcript_field(self):
        adapter = (D / "arctic-dictation").read_text()
        payload = re.search(r"printf '(\\?\{.*?\\n)'", adapter)
        self.assertIsNotNone(payload)
        self.assertNotIn("transcript", payload.group(1).lower())
        self.assertNotIn("audio", payload.group(1).lower())

    def test_status_requires_intact_selected_binary_and_model(self):
        adapter = (D / "arctic-dictation").read_text()
        self.assertIn('integrity_ready=false', adapter)
        self.assertIn('ready=$integrity_ready', adapter)
        for value in (
            '/opt/arctic/voxtype/1.1.1/voxtype-baseline', '18838904',
            '/opt/arctic/voxtype/1.1.1/voxtype-avx2', '19415936',
            '/opt/arctic/voxtype/1.1.1/voxtype-vulkan', '66575872',
            '/opt/arctic/voxtype/models/ggml-small.bin', '487601967',
            '/opt/arctic/voxtype/models/ggml-large-v3-turbo-q5_0.bin', '574041195',
            'The verified local Whisper model is missing or damaged.',
            'Dictation is not prepared for this account.',
            'This build has Vulkan support, so transcription will fall back to CPU',
            'VoxType could not start on Vulkan and is using CPU.',
        ):
            self.assertIn(value, adapter)

    def test_previous_direct_release_remains_runnable_only_while_receipt_is_authoritative(self):
        launcher = (D / "voxtype").read_text()
        adapter = (D / "arctic-dictation").read_text()
        setup = (D / "arctic-voxtype-setup").read_text()
        for value in (
            "/opt/arctic/voxtype/1.1.0", '"version":"1.1.0"',
            "e2638ca63f566f1682bcedc0abea8e4b25211c21",
            "1c9d78b4f6805e4f12ba3670949d3c22788269bdbc54215afffa42cafd0b4a7a",
            "e7d5de68cc8fc610c3c961c47f879451db9bee4a2df152e9a66f1078072e7f28",
            "db2c7938392ff08ec8b50b8afb90f8bd3d0111eccf5943df2f51c40a0368fec2",
        ):
            self.assertIn(value, launcher)
        self.assertIn("backend=$receipt_backend", launcher)
        self.assertIn("previous-direct-rejected", launcher)
        self.assertIn("upgrade_pending=true", adapter)
        self.assertIn('"upgrade_pending":%s', adapter)
        self.assertIn("def exact_file(path, mode, size, digest):", setup)
        self.assertIn("hashlib.sha256()", setup)
        self.assertIn('durable_atomic_text "$PREVIOUS_REJECTED" 0644 rejected', setup)
        self.assertIn('previous_direct_user >/dev/null', setup)
        service = (ROOT / "packaging/systemd/arctic-dictation-setup.service").read_text()
        self.assertIn("ExecCondition=/usr/libexec/arctic/arctic-voxtype-setup --needs-resume", service)
        self.assertNotIn("ConditionPathExists=/var/lib/arctic/dictation/pending", service)

    def test_mutations_return_safe_status_and_persist_setup_errors(self):
        adapter = (D / "arctic-dictation").read_text()
        setup = (D / "arctic-voxtype-setup").read_text()
        self.assertGreaterEqual(adapter.count('\n        status\n'), 3)
        self.assertIn('backend-vulkan', setup)
        self.assertIn('"$STATE/setup.error"', setup)
        self.assertNotIn('echo "$recent"', adapter)
        self.assertIn('flock --exclusive --timeout 10 9', setup)
        self.assertIn('stat -c %u:%a "$lockdir"', setup)
        self.assertLess(setup.index('acquire_setup_lock\ncase'), setup.index('    --install)'))
        self.assertIn('reuse_legacy_model', setup)
        self.assertIn('cp --reflink=auto', setup)
        self.assertLess(setup.index('durable_atomic_text "$STATE/upstream-direct-v1"'),
                        setup.index('\n    cleanup_legacy_payload'))

    def test_offline_upgrade_uses_shipped_signed_provenance_before_switching(self):
        setup = (D / "arctic-voxtype-setup").read_text()
        spec = (ROOT / "packaging/arctic-linux.spec").read_text()
        provenance = D / "provenance/v1.1.1"
        expected = {
            "SHA256SUMS.txt": (2931, "a93de5d79f6180626181aaf2315cc8415b084914b9f69a71e71bfb56bae1a32e"),
            "SHA256SUMS.txt.asc": (228, "2bce1ff42615d322b1e686f05373c99889d506e230d5f5512aeb22d728510af8"),
            "voxtype-1.1.1-linux-x86_64-baseline.asc": (228, "abd5e8b0c7b50987c6094105732ada464a2699f9b64f4e3fb47e3d005a30794e"),
            "voxtype-1.1.1-linux-x86_64-avx2.asc": (228, "e1c8606f7b54535193fe23f6c08808a1b60470e24b6641b1d3e4da5259991ead"),
        }
        for name, (size, digest) in expected.items():
            payload = (provenance / name).read_bytes()
            self.assertEqual(len(payload), size, name)
            self.assertEqual(hashlib.sha256(payload).hexdigest(), digest, name)
        with tempfile.TemporaryDirectory() as folder:
            env = dict(os.environ, GNUPGHOME=folder)
            os.chmod(folder, 0o700)
            subprocess.run(["gpg", "--batch", "--import", str(D / "voxtype-release-key.asc")],
                           env=env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["gpg", "--batch", "--verify", str(provenance / "SHA256SUMS.txt.asc"),
                            str(provenance / "SHA256SUMS.txt")], env=env, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        sums = (provenance / "SHA256SUMS.txt").read_text()
        for line in (
            "cc051aac0870e21d7378edbcde3ceff10238af12a11650ab897d0ad9195225af  voxtype-1.1.1-linux-x86_64-baseline",
            "3462262980e5a75391ffdeb7d3b63f9f638d6261df042f04f9119dfb7aab7770  voxtype-1.1.1-linux-x86_64-avx2",
        ):
            self.assertIn(line, sums)
        packaged = setup[setup.index("prepare_packaged_release_metadata() {"):
                         setup.index("\n}\n", setup.index("prepare_packaged_release_metadata() {")) + 3]
        self.assertIn('verify_signature "$PROVENANCE/SHA256SUMS.txt.asc"', packaged)
        self.assertIn('verify_signature "$PROVENANCE/$name.asc" "$source"', packaged)
        self.assertIn('trusted_exact_file "$source" 755', packaged)
        migration = setup[setup.index("    --migrate-legacy)"):
                          setup.index("    --resume)", setup.index("    --migrate-legacy)"))]
        self.assertIn('setup_user "$2" legacy-only', migration)
        setup_user = setup[setup.index("setup_user() {"):setup.index("\n}\n", setup.index("setup_user() {")) + 3]
        self.assertLess(setup_user.index("legacy_payload_usable"), setup_user.index("prepare_release_metadata"))
        self.assertIn('legacy_selection=$(legacy_profile "$host_profile")', setup_user)
        self.assertIn("read -r selected_profile receipt_user", setup_user)
        self.assertIn('valid_user "$receipt_user"', setup_user)
        self.assertLess(setup_user.index('user=$receipt_user'),
                        setup_user.index('home=$(getent passwd "$user"'))
        self.assertIn('quarantine_invalid_legacy_state', setup_user)
        self.assertIn('[[ $legacy_state == valid ]] && legacy_payload_usable', setup_user)
        self.assertIn('[[ $mode != legacy-only ]] || return 1', setup_user)
        self.assertIn('trusted_exact_file "$target" 755', setup)
        self.assertIn('trusted_exact_file "$target" 644', setup)
        prepare_state = setup[setup.index("prepare_state_dir() {"):
                              setup.index("\n}\n", setup.index("prepare_state_dir() {")) + 3]
        self.assertIn('durable_sync_tree "$STATE" "$STATE_ROOT"', prepare_state)
        queue = setup[setup.index("queue_user() {"):
                      setup.index("\n}\n", setup.index("queue_user() {")) + 3]
        self.assertLess(queue.index("prepare_state_dir"),
                        queue.index('durable_remove "$STATE/setup.error"'))
        self.assertLess(queue.index('durable_remove "$STATE/setup.error"'),
                        queue.index('durable_atomic_text "$STATE/pending"'))
        posttrans = spec[spec.index("# Direct-upstream dictation replaced"):
                         spec.index("# Migrate old boot-wanted", spec.index("# Direct-upstream dictation replaced"))]
        self.assertIn('arctic-voxtype-setup --migrate-legacy "$user"', posttrans)
        self.assertRegex(posttrans, r'if ! .*--migrate-legacy.*; then[\s\S]*--install "\$user" --offline[\s\S]*arctic-dictation-setup\.timer')
        self.assertLess(setup.index('durable_atomic_text "$STATE/verified.json"'),
                        setup.index('durable_atomic_text "$STATE/upstream-direct-v1"'))
        self.assertLess(setup.index('durable_sync_tree "$DEST"'),
                        setup.index('durable_atomic_text "$STATE/verified.json"'))
        self.assertLess(setup.index('durable_sync_tree "$MODELS"'),
                        setup.index('durable_atomic_text "$STATE/verified.json"'))
        self.assertLess(setup.index('durable_atomic_text "$STATE/upstream-direct-v1"'),
                        setup.index('\n    cleanup_legacy_payload'))
        self.assertLess(setup_user.index('durable_atomic_text "$STATE/upstream-direct-v1"'),
                        setup_user.index('\n    trap - ERR'))
        self.assertLess(setup.index('\n    cleanup_legacy_payload'),
                        setup.index('durable_remove "$STATE/pending"'))
        self.assertIn('systemctl --user daemon-reload >/dev/null 2>&1 || :', setup_user)
        self.assertIn('systemctl --user enable --now voxtype.service >/dev/null 2>&1 || :', setup_user)

        # Vulkan is published only after the official post-init marker is
        # observed; intent, exit zero, and device enumeration are insufficient.
        self.assertIn('whisper_backend_init_gpu:', setup)
        self.assertIn('found gpu device', setup)
        self.assertIn('"using" in line and "backend" in line', setup)
        self.assertLess(setup.index('update_receipt_backend vulkan'),
                        setup.index('durable_atomic_text "$STATE/backend" 0644 vulkan'))
        launcher = (D / "voxtype").read_text()
        self.assertIn('backend state is incomplete', launcher)
        self.assertIn('[ "$backend" != "$receipt_backend" ]', launcher)

    def test_runtime_error_cache_is_per_uid_and_no_follow(self):
        adapter = (D / "arctic-dictation").read_text()
        self.assertIn('base=${XDG_RUNTIME_DIR:-/run/user/$uid}', adapter)
        self.assertIn('runtime=/tmp/arctic-$uid', adapter)
        self.assertIn('[ ! -L "$runtime" ]', adapter)
        self.assertIn('stat -c %u:%a "$runtime"', adapter)
        self.assertNotIn('${XDG_RUNTIME_DIR:-/tmp}/arctic', adapter)

    def test_bad_complete_partial_is_restarted_and_unready_pill_opens_settings(self):
        setup = (D / "arctic-voxtype-setup").read_text()
        self.assertRegex(setup, r'\[ -f "\$part" \].*stat -c %s.*-ge "\$bytes".*rm -f')
        indicator = (ROOT / "shell/ModeIndicators.qml").read_text()
        self.assertIn("['unavailable', 'queued', 'downloading', 'ready', 'error'].includes", indicator)
        self.assertIn("if (!DictationService.status.ready", indicator)

    def test_haswell_profile_requires_every_flag_on_every_logical_cpu(self):
        helper = D / "arctic-voxtype-host-profile"
        required = "avx avx2 fma f16c bmi1 bmi2 movbe popcnt xsave abm"
        def classify(flag_lines):
            text = "".join(f"processor : {i}\nflags : {flags}\n" for i, flags in enumerate(flag_lines))
            with tempfile.NamedTemporaryFile("w", delete=False) as fixture:
                fixture.write(text); path = fixture.name
            try:
                return subprocess.check_output([str(helper), "--cpuinfo", path], text=True).strip()
            finally:
                pathlib.Path(path).unlink()
        self.assertEqual(classify([required, required]), "turbo-q5-v3")
        for missing in required.split():
            flags = " ".join(flag for flag in required.split() if flag != missing)
            self.assertEqual(classify([flags, flags]), "small-v2", missing)
        mixed = " ".join(flag for flag in required.split() if flag != "fma")
        self.assertEqual(classify([required, mixed]), "small-v2")

    def test_user_config_rejects_symlinks_without_touching_targets(self):
        helper = D / "arctic-voxtype-configure"
        helper_text = helper.read_text()
        self.assertIn('sync_user_file "$config"', helper_text)
        self.assertIn('os.fsync(parent)', helper_text)
        model = "/opt/arctic/voxtype/models/ggml-small.bin"
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder); home = root / "home"; home.mkdir()
            outside = root / "outside"; outside.mkdir()
            (home / ".config").symlink_to(outside, target_is_directory=True)
            linked_dir = subprocess.run([str(helper), model], env=dict(os.environ, HOME=str(home)), capture_output=True)
            self.assertNotEqual(linked_dir.returncode, 0)
            self.assertEqual(list(outside.iterdir()), [])
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder); home = root / "home"; directory = home / ".config/voxtype"
            directory.mkdir(parents=True); target = root / "target"; target.write_text("root-readable sentinel")
            (directory / "config.toml").symlink_to(target)
            linked_config = subprocess.run([str(helper), model], env=dict(os.environ, HOME=str(home)), capture_output=True)
            self.assertNotEqual(linked_config.returncode, 0)
            self.assertEqual(target.read_text(), "root-readable sentinel")
            self.assertFalse((directory / "config.toml.pre-arctic-voxtype-v1").exists())
        setup = (D / "arctic-voxtype-setup").read_text()
        configure_start = setup.index("configure_user() {")
        configure = setup[configure_start:setup.index("\n}\n", configure_start) + 3]
        self.assertIn("as_user", configure)
        self.assertIn('"$DEST/voxtype-$cpu"', setup)
        self.assertIn('"$validator" --config', helper.read_text())
        for root_operation in ("install ", "chown", "mktemp", "mv "):
            self.assertNotIn(root_operation, configure)

    def test_activation_guard_calls_only_upstream_and_never_exposes_command_error(self):
        helper = D / "arctic-dictation-toggle"
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder); log = root / "calls"
            def stub(name, body):
                path = root / name
                path.write_text("#!/bin/sh\n" + body + "\n"); path.chmod(0o755)
            stub("arctic-dictation", 'printf \'%s\\n\' "$STATUS"')
            stub("voxtype", 'printf \'voxtype %s\\n\' "$*" >>"$CALLS"; printf \'private transcript\\n\' >&2; exit "${VOXTYPE_RC:-0}"')
            stub("notify-send", 'printf \'notify %s\\n\' "$*" >>"$CALLS"')
            env = dict(os.environ, PATH=str(root) + ":/usr/bin:/bin", CALLS=str(log))
            env["STATUS"] = '{"state":"unavailable","ready":false}'
            unavailable = subprocess.run([str(helper)], env=env, text=True, capture_output=True)
            self.assertEqual(unavailable.returncode, 69)
            self.assertNotIn("private", unavailable.stdout + unavailable.stderr)
            self.assertNotIn("voxtype", log.read_text())
            log.write_text("")
            env["STATUS"] = '{"state":"ready","ready":true}'
            ready = subprocess.run([str(helper)], env=env, text=True, capture_output=True)
            self.assertEqual(ready.returncode, 0)
            self.assertEqual(log.read_text().strip(), "voxtype record toggle")
            log.write_text(""); env["VOXTYPE_RC"] = "1"
            failed = subprocess.run([str(helper)], env=env, text=True, capture_output=True)
            self.assertEqual(failed.returncode, 69)
            self.assertNotIn("private", failed.stdout + failed.stderr)
            self.assertIn("Dictation is not ready", log.read_text())

    def test_active_state_clears_stale_sanitized_error(self):
        adapter = (D / "arctic-dictation").read_text()
        active = adapter.index('if [ "$state" = recording ]')
        clear = adapter.index('rm -f "$runtime/voxtype-error"', active)
        scan = adapter.index("journalctl --user", clear)
        self.assertLess(active, clear)
        self.assertLess(clear, scan)
        self.assertNotIn("*'Vulkan'*", adapter)
        self.assertNotIn("*'GPU'*", adapter)
        self.assertNotIn("*'model not found'*", adapter)
        self.assertIn("*'Output failed:'*", adapter)
        self.assertIn("Focus a writable text field", adapter)
        self.assertIn("--since '-30 seconds'", adapter)
        self.assertNotIn("marker_time=", adapter)


if __name__ == "__main__":
    unittest.main()
