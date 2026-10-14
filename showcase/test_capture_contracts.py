import hashlib
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from showcase.capture_contracts import (
    CAPTURES,
    REVIEWED,
    CaptureContractError,
    contracts_from_provenance,
    pending_contract,
    preserve_reviewed_contracts,
    validate_contract,
)


class CaptureContractsTest(unittest.TestCase):
    def test_current_pending_contracts_are_closed(self):
        root = Path(__file__).resolve().parents[1]
        import json
        provenance = json.loads((root / "showcase/asset-provenance.json").read_text())
        contracts = contracts_from_provenance(provenance, root)
        self.assertEqual(set(contracts), set(CAPTURES))
        self.assertTrue(all(item["source"] is None for item in contracts.values()))

    def test_reviewed_capture_requires_exact_pixels_receipt_and_human_review(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / CAPTURES["dictationrecord"]["output"]
            output.parent.mkdir(parents=True)
            Image.new("RGB", (1280, 800), "#12171e").save(output)
            contract = pending_contract("dictationrecord")
            contract.update({
                "status": REVIEWED,
                "source": "exact-image-showcase-captures/dictationrecord.png",
                "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "qualified_iso": {
                    "name": "Arctic-Linux-final-x86_64.iso",
                    "bytes": 1_500_000_000,
                    "sha256": "a" * 64,
                    "source_commit": "b" * 40,
                    "workflow_run": "https://github.com/yuvalkolodkingal/Arctic-Linux/actions/runs/123",
                },
                "human_review": {
                    "status": "approved",
                    "reviewer": "release reviewer",
                    "reviewed_at": "2026-10-14T12:34:56Z",
                },
            })
            self.assertIs(validate_contract("dictationrecord", contract, root), contract)
            preserved = preserve_reviewed_contracts(
                [{"scene": "dictationrecord", "capture_contract": contract}], root
            )
            self.assertEqual(preserved["dictationrecord"], contract)
            output.write_bytes(output.read_bytes() + b"tampered")
            with self.assertRaises(CaptureContractError):
                validate_contract("dictationrecord", contract, root)

    def test_reviewed_claim_cannot_be_silently_incomplete(self):
        contract = pending_contract("dictationsetup")
        contract["status"] = REVIEWED
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(CaptureContractError):
                validate_contract("dictationsetup", contract, Path(folder))

    def test_recovery_requires_two_independently_hashed_reviewed_images(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            outputs = CAPTURES["dictationrecovery"]["output"]
            digests = {}
            for key, name in outputs.items():
                output = root / name
                output.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (1280, 800), "#12171e" if key == "gpu_failure" else "#eef2f5").save(output)
                digests[key] = hashlib.sha256(output.read_bytes()).hexdigest()
            contract = pending_contract("dictationrecovery")
            contract.update({
                "status": REVIEWED,
                "source": {
                    "gpu_failure": "dictation-qualification/gpu-failure.png",
                    "cpu_ready": "dictation-qualification/cpu-ready.png",
                },
                "sha256": digests,
                "qualified_iso": {
                    "name": "Arctic-Linux-final-x86_64.iso",
                    "bytes": 1_500_000_000,
                    "sha256": "a" * 64,
                    "source_commit": "b" * 40,
                    "workflow_run": "https://github.com/yuvalkolodkingal/Arctic-Linux/actions/runs/123",
                },
                "human_review": {
                    "status": "approved",
                    "reviewer": "release reviewer",
                    "reviewed_at": "2026-10-14T12:34:56Z",
                },
            })
            self.assertIs(validate_contract("dictationrecovery", contract, root), contract)
            contract["source"].pop("cpu_ready")
            with self.assertRaisesRegex(CaptureContractError, "paired capture fields differ"):
                validate_contract("dictationrecovery", contract, root)


if __name__ == "__main__":
    unittest.main()
