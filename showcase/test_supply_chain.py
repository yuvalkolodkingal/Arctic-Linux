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
            "name": "Arctic-Linux-1.2-candidate-38707130991-1-x86_64.iso",
            "bytes": 1936185344,
            "sha256": "92fe2a1bcb9a67b8ed72e7b38d065e7e68ae26a38e930042a752aae7146e8d66",
            "source_sha": "fc501fdf90c17c617b15b8b13038d062d519fcc6",
            "run_id": 38707130991,
            "artifact_id": 11961831325,
            "archive_bytes": 1936373046,
            "archive_sha256": "1c1e3e34e240b9e6ec592e3bce23330378e6bc2a7815ab295080fa61925082c3",
            "producer_mode": "frozen-external-paired-v1",
            "producer_receipt_sha256": "9d755876dc45d143506da8b52cf98d92205ab1d2f014355de612db0bb04bc9b4",
        })
        self.assertFalse(manifest["release_acceptance"])
        expected_paths = {
            ".github/workflows/showcase-exact-capture-20261014.yml",
            "tools/native-functional/fetch-image.py",
            *{
                f"showcase/capture/exact_image/{name}"
                for name in (
                    "automation.py", "bundle.py", "capture_probe.py", "capture_vm.py",
                    "contract.py", "guest.py", "host.py", "unattended.py", "validate_bundle.py",
                )
            },
        }
        self.assertEqual(set(manifest["execution_files"]), expected_paths)
        for relative_path, expected_digest in manifest["execution_files"].items():
            path = REPOSITORY / relative_path
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected_digest)

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
        exact = workflows["showcase-exact-capture-20261014.yml"]
        self.assertIn("id: reviewed", exact)
        self.assertIn("candidate_name=image['name']", exact)
        self.assertIn("steps.reviewed.outputs.candidate_name", exact)
        self.assertNotIn("candidate-38536710765-1-x86_64.iso", exact)


if __name__ == "__main__":
    unittest.main()
