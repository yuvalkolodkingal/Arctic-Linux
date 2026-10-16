import copy
import hashlib
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from showcase import publish_video as publisher


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def png(width: int = 1920, height: int = 1080, suffix: bytes = b"") -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + width.to_bytes(4, "big") + height.to_bytes(4, "big") + suffix


class PublishVideoTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.target = "d" * 40
        self.render_source = "e" * 40
        self.run_id = 500
        self.artifact_id = 501
        self.video = b"reviewed-mp4" * 100_000
        self.captions = "\n\n".join(
            f"{index}\n00:00:00,000 --> 00:00:01,000\nCue {index}"
            for index in range(1, 131)
        ) + "\n"
        self.vtt = "WEBVTT\n\n" + "\n\n".join(
            f"{index}\n00:00:00.000 --> 00:00:01.000\nCue {index}"
            for index in range(1, 131)
        ) + "\n"
        self.poster = png(suffix=b"poster")
        self.frames = {name: png(suffix=name.encode()) for name in publisher.FRAMES}
        self.base_receipt = {
            "license": {"publication_confirmation": {"status": "pending"}},
            "validation": {
                "human_listening_review": {"status": "pending"},
                "final_render_verified": False,
                "final_render_review": None,
            },
            "stable": "render-input",
        }
        self.receipt = copy.deepcopy(self.base_receipt)
        self.receipt["license"]["publication_confirmation"] = {
            "status": "confirmed", "scope": "public_video"
        }
        self.receipt["validation"].update({
            "human_listening_review": {"status": "approved"},
            "final_render_verified": True,
        })
        self._write_repository_files()
        self.members = self._candidate_members()
        self.archive = self.root / "candidate.zip"
        self._seal_archive()

    def _write_repository_files(self):
        files = {
            "showcase/poster.png": self.poster,
            "showcase/captions.srt": self.captions.encode(),
            "showcase/captions.vtt": self.vtt.encode(),
            "showcase/chapters.txt": b"00:00 Introduction\n",
            "showcase/timing.json": b'{"render_ready":true}\n',
            "showcase/asset-provenance.json": b"[]\n",
            "showcase/revision-2026-10-12/alignment-provenance.json": b"{}\n",
            "tools/qualified-release/manifest.json": json.dumps({"main_sha": self.target}).encode(),
        }
        for name, data in files.items():
            path = self.repository / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def _candidate_members(self):
        validation = {
            "source_commit": self.render_source,
            "workflow_run": f"https://github.com/yuvalkolodkingal/Arctic-Linux/actions/runs/{self.run_id}",
            "video": {
                "bytes": len(self.video), "sha256": sha(self.video),
                "duration_seconds": 582.356463, "subtitle_codec": "mov_text",
                "subtitle_cues": 130,
            },
            "full_decode_errors": 0,
            "published": False,
        }
        result = {
            f"renders/{publisher.VIDEO_NAME}": self.video,
            "captions.srt": self.captions.encode(),
            "captions.vtt": self.vtt.encode(),
            "chapters.txt": b"00:00 Introduction\n",
            "timing.json": b'{"render_ready":true}\n',
            "asset-provenance.json": b"[]\n",
            "revision-2026-10-12/alignment-provenance.json": b"{}\n",
            "revision-2026-10-12/voice-timing.json": json.dumps(self.base_receipt).encode(),
            "renders/validation/ffprobe.json": b"{}\n",
            "renders/validation/muxed-captions.srt": self.captions.encode(),
            "renders/validation/render-validation.json": json.dumps(validation).encode(),
            "renders/validation/frames.tsv": b"0.500\tintro\n",
        }
        result.update({f"renders/validation/{name}": data for name, data in self.frames.items()})
        return result

    def _seal_archive(self):
        if self.archive.exists():
            self.archive.unlink()
        with zipfile.ZipFile(self.archive, "w", compression=zipfile.ZIP_STORED) as output:
            for name, data in sorted(self.members.items()):
                output.writestr(name, data)
        archive_hash = publisher.digest(self.archive)
        archive_bytes = self.archive.stat().st_size
        review = {
            "status": "approved",
            "source_commit": self.render_source,
            "render": {
                "workflow_run": f"https://github.com/yuvalkolodkingal/Arctic-Linux/actions/runs/{self.run_id}",
                "source_commit": self.render_source,
                "artifact_id": self.artifact_id,
                "artifact_name": "Arctic-Linux-Showcase-River-1080p-candidate",
                "archive_bytes": archive_bytes,
                "archive_sha256": archive_hash,
            },
            "video": {
                "name": publisher.VIDEO_NAME, "bytes": len(self.video),
                "sha256": sha(self.video), "duration_seconds": 582.356463,
            },
            "checks": {},
            "human_frame_review": {
                "frames": {name: sha(data) for name, data in self.frames.items()}
            },
        }
        self.receipt["validation"]["final_render_review"] = review
        receipt_path = self.repository / publisher.RECEIPT_PATH
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(self.receipt))
        self.artifact_metadata = self.root / "artifact.json"
        self.artifact_metadata.write_text(json.dumps({
            "id": self.artifact_id,
            "name": review["render"]["artifact_name"],
            "size_in_bytes": archive_bytes,
            "digest": "sha256:" + archive_hash,
            "expired": False,
            "workflow_run": {"id": self.run_id, "head_sha": self.render_source},
        }))
        self.run_metadata = self.root / "run.json"
        self.run_metadata.write_text(json.dumps({
            "id": self.run_id, "html_url": review["render"]["workflow_run"],
            "head_sha": self.render_source, "status": "completed", "conclusion": "success",
            "run_attempt": 1,
        }))

    def stage(self):
        stage = self.root / "public"
        admission = {
            "source_tag": "showcase-river-source-2026-10-12",
            "master_asset": "river.mp3", "master_bytes": "13978270",
            "master_sha256": "f" * 64, "master_duration": "582.356463",
            "admission": "public_video", "publication_scope": "public_video",
            "source_audio_redistribution": "false",
        }
        with mock.patch.object(publisher, "resolve_publication", return_value=admission), \
             mock.patch.object(publisher, "resolve", return_value={"admission": "private_render"}):
            manifest = publisher.stage_candidate(
                repository=self.repository,
                receipt_path=self.repository / publisher.RECEIPT_PATH,
                artifact_path=self.archive,
                artifact_metadata_path=self.artifact_metadata,
                run_metadata_path=self.run_metadata,
                target_commit=self.target,
                stage=stage,
                invoke_resolver=False,
            )
        return stage, manifest

    def test_exact_reviewed_candidate_stages_only_public_video_package(self):
        stage, manifest = self.stage()
        expected = {*publisher.PUBLIC_NAMES.values(), "Arctic-Linux-Showcase-Poster.png"}
        self.assertEqual(set(manifest["assets"]), expected)
        self.assertFalse(manifest["source_audio_included"])
        self.assertEqual({path.name for path in stage.iterdir()}, {
            *expected, "publication-manifest.json"
        })
        self.assertFalse(any(path.suffix == ".mp3" for path in stage.iterdir()))

    def test_candidate_with_source_mp3_is_rejected_even_before_staging(self):
        self.members["river-source.mp3"] = b"private audio"
        self._seal_archive()
        with self.assertRaisesRegex(ValueError, "inventory differs"):
            self.stage()

    def test_tampered_reviewed_frame_is_rejected(self):
        frame = next(iter(publisher.FRAMES))
        self.members[f"renders/validation/{frame}"] += b"tamper"
        self._seal_archive()
        # Preserve the human-reviewed digest while updating only the archive receipt.
        self.receipt["validation"]["final_render_review"]["human_frame_review"]["frames"][frame] = sha(self.frames[frame])
        (self.repository / publisher.RECEIPT_PATH).write_text(json.dumps(self.receipt))
        with self.assertRaisesRegex(ValueError, "representative frame differs"):
            self.stage()

    def test_archive_digest_mismatch_is_rejected(self):
        self.archive.write_bytes(self.archive.read_bytes() + b"tamper")
        with self.assertRaisesRegex(ValueError, "byte size differs"):
            self.stage()

    def test_release_verification_checks_inventory_urls_and_download_hashes(self):
        stage, manifest = self.stage()
        release = {
            "tagName": manifest["tag"], "isDraft": False, "isPrerelease": False,
            "targetCommitish": self.target,
            "assets": [],
        }
        for name, expected in manifest["assets"].items():
            release["assets"].append({
                "name": name, "size": expected["bytes"],
                "url": f"https://github.com/{publisher.REPOSITORY_SLUG}/releases/download/{publisher.RELEASE_TAG}/{name}",
            })
        release_path = self.root / "release.json"
        release_path.write_text(json.dumps(release))
        downloaded = self.root / "downloaded"
        downloaded.mkdir()
        for name in manifest["assets"]:
            shutil.copyfile(stage / name, downloaded / name)
        publisher.verify_release(
            release_path, stage / "publication-manifest.json", downloaded
        )
        release["assets"][0]["url"] = "https://example.invalid/unreviewed"
        release_path.write_text(json.dumps(release))
        with self.assertRaisesRegex(ValueError, "metadata differs"):
            publisher.verify_release(
                release_path, stage / "publication-manifest.json", downloaded
            )


if __name__ == "__main__":
    unittest.main()
