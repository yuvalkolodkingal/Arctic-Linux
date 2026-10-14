import hashlib
import io
import tempfile
import unittest
from pathlib import Path

from showcase.asset_integrity import ensure_exact_asset


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class AssetIntegrityTest(unittest.TestCase):
    def test_exact_existing_asset_needs_no_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "asset.js"
            payload = b"immutable asset"
            path.write_bytes(payload)

            def no_network(*_args, **_kwargs):
                raise AssertionError("network used for an exact committed asset")

            status = ensure_exact_asset(
                path, url="https://example.invalid/asset.js", expected_bytes=len(payload),
                expected_sha256=hashlib.sha256(payload).hexdigest(), opener=no_network,
            )
            self.assertEqual(status, "verified-existing")

    def test_changed_download_fails_without_replacing_existing_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "asset.js"
            path.write_bytes(b"existing invalid bytes")
            wanted = b"reviewed bytes"

            with self.assertRaisesRegex(ValueError, "immutable pin"):
                ensure_exact_asset(
                    path, url="https://example.invalid/asset.js", expected_bytes=len(wanted),
                    expected_sha256=hashlib.sha256(wanted).hexdigest(),
                    opener=lambda *_args, **_kwargs: Response(b"changed bytes"),
                )
            self.assertEqual(path.read_bytes(), b"existing invalid bytes")

    def test_exact_download_replaces_invalid_regular_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "asset.js"
            path.write_bytes(b"old")
            wanted = b"reviewed bytes"
            status = ensure_exact_asset(
                path, url="https://example.invalid/asset.js", expected_bytes=len(wanted),
                expected_sha256=hashlib.sha256(wanted).hexdigest(),
                opener=lambda *_args, **_kwargs: Response(wanted),
            )
            self.assertEqual(status, "verified-download")
            self.assertEqual(path.read_bytes(), wanted)

    def test_symlink_destination_is_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.js"
            target.write_bytes(b"reviewed bytes")
            path = root / "asset.js"
            path.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symlinked"):
                ensure_exact_asset(
                    path, url="https://example.invalid/asset.js", expected_bytes=14,
                    expected_sha256=hashlib.sha256(b"reviewed bytes").hexdigest(),
                    opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                        AssertionError("network used for symlink")
                    ),
                )


if __name__ == "__main__":
    unittest.main()
