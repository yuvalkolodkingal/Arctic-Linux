import hashlib
import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
D = ROOT / "packaging/dictation"


class DirectUpstreamIntegration(unittest.TestCase):
    def test_shells_parse_and_old_runtime_is_gone(self):
        for name, shell in (("voxtype", "sh"), ("arctic-dictation", "sh"), ("arctic-voxtype-setup", "bash"),
                            ("arctic-voxtype-host-profile", "sh")):
            subprocess.run([shell, "-n", str(D / name)], check=True)
        for name in ("dictation.py", "child_exec.py", "arctic-dictation-install", "arctic-dictation-setup"):
            self.assertFalse((D / name).exists(), name)

    def test_runtime_controls_call_upstream_directly(self):
        adapter = (D / "arctic-dictation").read_text()
        self.assertNotIn("record toggle", adapter)
        self.assertNotIn("record cancel", adapter)
        binds = (ROOT / "dotfiles/.config/mango/arctic/binds.conf").read_text()
        self.assertIn("voxtype record toggle", binds)
        self.assertIn("voxtype record cancel", binds)
        shell = (ROOT / "shell/DictationService.qml").read_text()
        self.assertIn("['voxtype', 'record', 'toggle']", shell)
        self.assertIn("Session.runtimeDir + '/voxtype/state'", shell)
        settings = (ROOT / "settings/pages/DictationPage.qml").read_text()
        self.assertEqual(settings.count("enabled: page.status.ready && page.canConfigure"), 2)

    def test_release_identity_integrity_and_privacy_are_pinned(self):
        setup = (D / "arctic-voxtype-setup").read_text()
        for value in (
            "e2638ca63f566f1682bcedc0abea8e4b25211c21",
            "9CCF7915B750CAE8B095ED1AA3FC9F33FD209279",
            "394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2",
            "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b",
            "download_pinned", "verify_signature", 'language = ["he", "en"]',
            'driver_order = ["wtype"]', "fallback_to_clipboard = false",
            "on_demand_loading = true", "filter_filler_words = false",
        ):
            self.assertIn(value, setup)
        unit = (ROOT / "packaging/systemd/voxtype.service").read_text()
        self.assertIn("UnsetEnvironment=RUST_LOG", unit)
        self.assertIn("ExecStart=/usr/bin/voxtype --config %h/.config/voxtype/config.toml -q daemon", unit)
        self.assertIn("VOXTYPE_REMOTE_ENDPOINT", unit)
        self.assertIn("VOXTYPE_WHISPER_API_KEY", unit)
        for name in ("VOXTYPE_ON_DEMAND_LOADING", "VOXTYPE_MAX_DURATION_SECS", "VOXTYPE_AUDIO_DEVICE", "SONIOX_API_KEY"):
            self.assertIn(name, unit)
        self.assertIn("UMask=0077", unit)
        self.assertNotIn("input", unit.lower())

    def test_embedded_key_has_expected_fingerprint(self):
        out = subprocess.check_output(["gpg", "--batch", "--show-keys", "--with-colons", str(D / "voxtype-release-key.asc")], text=True)
        fingerprints = [line.split(":")[9] for line in out.splitlines() if line.startswith("fpr:")]
        self.assertIn("9CCF7915B750CAE8B095ED1AA3FC9F33FD209279", fingerprints)

    def test_receipt_is_atomic_public_and_versioned(self):
        setup = (D / "arctic-voxtype-setup").read_text()
        self.assertIn('"integration":"upstream-direct-v1"', setup)
        self.assertRegex(setup, r'chmod 0644 "\$receipt"; mv -f')
        self.assertIn('install -m 0644 /dev/stdin "$STATE/upstream-direct-v1"', setup)
        service = (ROOT / "packaging/systemd/voxtype.service").read_text()
        self.assertIn("ConditionPathExists=/var/lib/arctic/dictation/upstream-direct-v1", service)
        self.assertIn("ConditionPathExists=%h/.config/voxtype/config.toml", service)

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
            '/opt/arctic/voxtype/1.1.0/voxtype-baseline', '18579224',
            '/opt/arctic/voxtype/1.1.0/voxtype-avx2', '19153728',
            '/opt/arctic/voxtype/1.1.0/voxtype-vulkan', '66342968',
            '/opt/arctic/voxtype/models/ggml-small.bin', '487601967',
            '/opt/arctic/voxtype/models/ggml-large-v3-turbo-q5_0.bin', '574041195',
            'The verified local Whisper model is missing or damaged.',
            'Dictation is not prepared for this account.',
        ):
            self.assertIn(value, adapter)

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
