import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parent
HYPERFRAMES_INTEGRITY = (
    "sha512-dIHdDQ//Wapovreuc0q2B+xLS5gbDUSles3ysXafkvxC4YXzZjc3NPvMqweEi5IZQDXefxZOJws5AgDByOiRAQ=="
)
ACTIONS = {
    "checkout": ("34e114876b0b11c390a56381ad16ebd13914f8d5", "4.3.1"),
    "setup-python": ("a26af69be951a213d495a4c3e4e4022e16d87065", "5.6.0"),
    "setup-node": ("49933ea5288caeca8642d1e84afbd3f7d6820020", "4.4.0"),
    "upload-artifact": ("ea165f8d65b6e75b540449e92b4886f43607fa02", "4.6.2"),
}


class SupplyChainTest(unittest.TestCase):
    def test_exact_capture_execution_manifest_matches_repository_bytes(self):
        manifest_path = ROOT / "capture/exact_image/execution-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        self.assertTrue(manifest["ready"])
        self.assertEqual(manifest["image"], {
            "name": "Arctic-Linux-1.2-candidate-38823208615-1-x86_64.iso",
            "bytes": 1936271360,
            "sha256": "c13c4589d7b522fec7dbd5eeafec00cf9088d8788cdfb6771a7382285846d7c7",
            "source_sha": "cfc39dad61125e4fa8fb7906ac14f4c360b58228",
            "run_id": 38823208615,
            "artifact_id": 12016177474,
            "archive_bytes": 1936459062,
            "archive_sha256": "5f77dbf607abdada5ed140ae8635314554d5d2f03f88f1f5831e3d53bc18cf23",
            "producer_mode": "frozen-external-paired-v1",
            "producer_receipt_sha256": "82d102432819e8cc2f9d27b020f54a21021a176daa930e675c75229273ab7330",
        })
        self.assertFalse(manifest["release_acceptance"])
        expected_paths = {
            ".github/workflows/showcase-exact-capture-20261014.yml",
            "tools/native-functional/fetch-image.py",
            "showcase/capture/exact_image/automation.py",
            "showcase/capture/exact_image/bundle.py",
            "showcase/capture/exact_image/capture_probe.py",
            "showcase/capture/exact_image/capture_vm.py",
            "showcase/capture/exact_image/contract.py",
            "showcase/capture/exact_image/guest.py",
            "showcase/capture/exact_image/host.py",
            "showcase/capture/exact_image/unattended.py",
            "showcase/capture/exact_image/validate_bundle.py",
        }
        self.assertEqual(set(manifest["execution_files"]), expected_paths)
        for relative, expected in manifest["execution_files"].items():
            self.assertEqual(
                hashlib.sha256((REPOSITORY / relative).read_bytes()).hexdigest(),
                expected,
            )
        self.assertFalse((REPOSITORY / ".github/qualification-20261014.showcase-capture").exists())

    def test_gsap_committed_bytes_and_prepare_pin_match(self):
        asset = ROOT / "assets/gsap.min.js"
        payload = asset.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        self.assertEqual(len(payload), 72_777)
        self.assertEqual(digest, "19e3ad578c9c583ddf9bdca2ad87bb55c3d70b331058e28abacab898f799b2ee")
        source = (ROOT / "prepare-assets.py").read_text()
        self.assertIn("expected_bytes=72_777", source)
        self.assertIn(f"expected_sha256='{digest}'", source)

    def test_hyperframes_uses_exact_dependency_and_integrity_lock(self):
        package = json.loads((ROOT / "package.json").read_text())
        lock = json.loads((ROOT / "package-lock.json").read_text())
        self.assertEqual(package["devDependencies"], {"hyperframes": "0.8.114"})
        self.assertTrue(all("npx" not in command for command in package["scripts"].values()))
        hyperframes = lock["packages"]["node_modules/hyperframes"]
        self.assertEqual(hyperframes["version"], "0.8.114")
        self.assertEqual(hyperframes["integrity"], HYPERFRAMES_INTEGRITY)
        registry_packages = [
            value for value in lock["packages"].values()
            if value.get("resolved", "").startswith("https://registry.npmjs.org/")
        ]
        self.assertTrue(registry_packages)
        self.assertTrue(all(value.get("integrity", "").startswith("sha512-") for value in registry_packages))

    def test_showcase_workflows_pin_official_actions_and_use_npm_ci(self):
        workflow_dir = REPOSITORY / ".github/workflows"
        workflows = {
            path.name: path.read_text()
            for path in workflow_dir.glob("showcase-*.yml")
        }
        expected = {
            "showcase-exact-capture-20261014.yml": {"checkout", "upload-artifact"},
            "showcase-river-render.yml": {"checkout", "setup-python", "setup-node", "upload-artifact"},
            "showcase-river-verify.yml": {"checkout", "setup-python", "upload-artifact"},
        }
        self.assertEqual(set(workflows), set(expected))
        pattern = re.compile(
            r"uses:\s+actions/([a-z-]+)@([0-9a-f]{40})\s+#\s+v([0-9.]+)$",
            re.MULTILINE,
        )
        for name, source in workflows.items():
            found = {action: (commit, version) for action, commit, version in pattern.findall(source)}
            self.assertEqual(set(found), expected[name])
            self.assertEqual(found, {action: ACTIONS[action] for action in expected[name]})
            self.assertNotRegex(source, r"uses:\s+actions/[a-z-]+@(v[0-9]+|main)\b")
        render = workflows["showcase-river-render.yml"]
        self.assertIn("npm ci --ignore-scripts --no-audit --no-fund", render)
        self.assertIn("cache-dependency-path: showcase/package-lock.json", render)


if __name__ == "__main__":
    unittest.main()
