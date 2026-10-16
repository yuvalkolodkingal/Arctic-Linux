#!/usr/bin/env python3
"""Read one pinned showcase failure artifact and emit only closed safe fields."""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "yuvalkolodkingal/Arctic-Linux"
REPO_API = "repos/" + REPOSITORY
RUN_ID = 38_839_101_249
RUN_ATTEMPT = 1
SOURCE_SHA = "c2a6944f544bc7b20fdb25a4e788938e3ca72714"
SOURCE_BRANCH = "codex/showcase-exact-capture-20261014"
SOURCE_WORKFLOW = ".github/workflows/showcase-exact-capture-20261014.yml"
BRANCH = "codex/read-showcase-failure-388391-20261016"
WORKFLOW_NAME = "Read bounded showcase failure for run 38839101249"
ACTIVATION = Path(".github/showcase-failure-reader-388391.activate")
READER = Path("tools/showcase-failure-reader/read.py")
CONTRACT = Path("showcase/capture/exact_image/contract.py")
READER_WORKFLOW = Path(".github/workflows/read-showcase-failure-388391.yml")
ARTIFACT = {
    "id": 12_021_566_420,
    "name": "exact-image-showcase-failure-projection",
    "bytes": 7_435,
    "sha256": "9944a92810ed2972713ab05a0844b4450e10c8f4acabff598e2540f735d135e5",
}
MEMBER = "failure-projection.json"
MANIFEST_FIELDS = {
    "schema", "ready", "repository", "run_id", "run_attempt", "source_sha",
    "source_branch", "source_workflow", "reader_sha256", "contract_sha256",
    "reader_workflow_sha256", "artifact",
}
ARTIFACT_FIELDS = {"id", "name", "bytes", "sha256"}


def require(value):
    if not value:
        raise RuntimeError("safe showcase reader rejected artifact")


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value, length=64):
    return type(value) is str and re.fullmatch("[0-9a-f]{" + str(length) + "}", value) is not None


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(type(key) is str and key not in result)
        result[key] = value
    return result


def strict_json(raw, maximum):
    require(type(raw) is bytes and 0 < len(raw) <= maximum)
    try:
        return json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=unique,
                          parse_constant=lambda _value: require(False))
    except (UnicodeError, ValueError, TypeError, RuntimeError) as error:
        raise RuntimeError("safe showcase reader rejected artifact") from error


def read_json_file(path, maximum):
    require(path.is_file() and not path.is_symlink())
    return strict_json(path.read_bytes(), maximum)


def validate_manifest(manifest):
    require(type(manifest) is dict and set(manifest) == MANIFEST_FIELDS)
    require(manifest["schema"] == "arctic-showcase-failure-reader-v1"
            and manifest["ready"] is True and manifest["repository"] == REPOSITORY
            and manifest["run_id"] == RUN_ID and manifest["run_attempt"] == RUN_ATTEMPT
            and manifest["source_sha"] == SOURCE_SHA
            and manifest["source_branch"] == SOURCE_BRANCH
            and manifest["source_workflow"] == SOURCE_WORKFLOW)
    for key in ("reader_sha256", "contract_sha256", "reader_workflow_sha256"):
        require(digest(manifest[key]))
    require(sha256((ROOT / READER).read_bytes()) == manifest["reader_sha256"]
            and sha256((ROOT / CONTRACT).read_bytes()) == manifest["contract_sha256"]
            and sha256((ROOT / READER_WORKFLOW).read_bytes()) == manifest["reader_workflow_sha256"])
    pin = manifest["artifact"]
    require(type(pin) is dict and set(pin) == ARTIFACT_FIELDS and pin == ARTIFACT)
    return manifest


def activation_guard():
    require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
            and os.environ.get("GITHUB_EVENT_NAME") == "push"
            and os.environ.get("GITHUB_REF") == "refs/heads/" + BRANCH
            and os.environ.get("GITHUB_WORKFLOW") == WORKFLOW_NAME
            and os.environ.get("GITHUB_RUN_ATTEMPT") == "1")
    child = os.environ.get("GITHUB_SHA", "")
    require(digest(child, 40))
    marker = ROOT / ACTIVATION
    require(marker.is_file() and not marker.is_symlink() and marker.stat().st_size == 41)
    parent = marker.read_text().strip()
    require(digest(parent, 40))
    event = read_json_file(Path(os.environ["GITHUB_EVENT_PATH"]), 1_000_000)
    require(event.get("before") == parent and event.get("after") == child)
    parents = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-list", "--parents", "-n", "1", child],
        text=True, timeout=30).split()
    changed = subprocess.check_output(
        ["git", "-C", str(ROOT), "diff", "--name-only", parent, child],
        text=True, timeout=30).splitlines()
    require(parents == [child, parent] and changed == [ACTIVATION.as_posix()]
            and marker.read_bytes() == (parent + "\n").encode()
            and not subprocess.check_output(
                ["git", "-C", str(ROOT), "status", "--porcelain"],
                text=True, timeout=30).strip())


def api(path):
    result = subprocess.run(["gh", "api", REPO_API + path], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=60, check=False)
    require(result.returncode == 0 and 0 < len(result.stdout) <= 20_000_000)
    return strict_json(result.stdout, 20_000_000)


def download(artifact_id, target):
    require(artifact_id == ARTIFACT["id"] and not target.exists())
    with target.open("xb") as output:
        result = subprocess.run(
            ["gh", "api", REPO_API + "/actions/artifacts/" + str(artifact_id) + "/zip"],
            stdout=output, stderr=subprocess.PIPE, timeout=120, check=False)
    require(result.returncode == 0)


def validate_run(run, jobs):
    require(type(run) is dict and run.get("id") == RUN_ID
            and run.get("run_attempt") == RUN_ATTEMPT and run.get("head_sha") == SOURCE_SHA
            and run.get("head_branch") == SOURCE_BRANCH and run.get("path") == SOURCE_WORKFLOW
            and run.get("event") == "push" and run.get("status") == "completed"
            and run.get("conclusion") == "failure")
    require(type(jobs) is dict and jobs.get("total_count") == 1
            and type(jobs.get("jobs")) is list and len(jobs["jobs"]) == 1)
    job = jobs["jobs"][0]
    require(job.get("name") == "capture" and job.get("status") == "completed"
            and job.get("conclusion") == "failure")
    steps = {step.get("name"): step.get("conclusion") for step in job.get("steps", [])}
    require(steps.get("Install once and capture three host-screened exact-image scenes") == "failure"
            and steps.get("Validate bounded privacy-safe failure projection") == "success"
            and steps.get("Upload bounded showcase failure projection") == "success")


def load_contract():
    spec = importlib.util.spec_from_file_location("safe_showcase_contract", ROOT / CONTRACT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def safe_member(item):
    path = PurePosixPath(item.filename)
    mode = item.external_attr >> 16
    require(path == PurePosixPath(MEMBER) and not item.is_dir()
            and stat.S_IFMT(mode) in (0, stat.S_IFREG) and not (item.flag_bits & 0x1)
            and item.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
            and 0 < item.file_size <= 32_768 and 0 <= item.compress_size <= ARTIFACT["bytes"])


def safe_projection(value, contract):
    contract.capture_failure(value)
    booleans = {
        "release_acceptance": value["release_acceptance"],
        "private_runtime_removed": value["private_runtime_removed"],
        "screens_exported": value["screens_exported"],
        "logs_exported": value["logs_exported"],
        "pixels_exported": value["pixels_exported"],
        "live_startup_present": value["live_startup"] is not None,
        "installed_startup_present": value["installed_startup"] is not None,
    }
    require(value["status"] == "failed"
            and value["host_phase"] in (
                "vm-start", "live-boot", "live-install", "install-screen-verification",
                "installed-transition", "installed-boot", "capture-scenes", "cleanup")
            and value["failure_code"] in (
                "private-channel-timeout", "guest-install-failed", "capture-contract-failed",
                "guest-scene-failed", "vm-exited", "cleanup-failed", "host-io-failed")
            and value["guest_scene_stage"] in (None, "bootstrap", "dictationsetup", "winter", "updates")
            and all(type(item) is bool for item in booleans.values()))
    return {"status": value["status"], "host_phase": value["host_phase"],
            "failure_code": value["failure_code"],
            "guest_scene_stage": value["guest_scene_stage"] or "none", **booleans}


def inspect(manifest, api_call=api, downloader=download):
    validate_manifest(manifest)
    validate_run(api_call("/actions/runs/" + str(RUN_ID)),
                 api_call("/actions/runs/" + str(RUN_ID) + "/jobs?filter=all&per_page=100"))
    artifact = api_call("/actions/artifacts/" + str(ARTIFACT["id"]))
    require(type(artifact) is dict and artifact.get("id") == ARTIFACT["id"]
            and artifact.get("name") == ARTIFACT["name"] and artifact.get("expired") is False
            and artifact.get("size_in_bytes") == ARTIFACT["bytes"]
            and artifact.get("digest") == "sha256:" + ARTIFACT["sha256"]
            and type(artifact.get("workflow_run")) is dict
            and artifact["workflow_run"].get("id") == RUN_ID
            and artifact["workflow_run"].get("head_sha") == SOURCE_SHA)
    with tempfile.TemporaryDirectory(prefix="arctic-showcase-safe-reader-") as directory:
        target = Path(directory) / "artifact.zip"
        downloader(ARTIFACT["id"], target)
        archive_raw = target.read_bytes()
        require(len(archive_raw) == ARTIFACT["bytes"] and sha256(archive_raw) == ARTIFACT["sha256"])
        try:
            with zipfile.ZipFile(io.BytesIO(archive_raw)) as archive:
                items = archive.infolist()
                require(len(items) == 1 and items[0].filename == MEMBER)
                safe_member(items[0])
                value = strict_json(archive.read(MEMBER), 32_768)
        except (OSError, ValueError, zipfile.BadZipFile, KeyError) as error:
            raise RuntimeError("safe showcase reader rejected artifact") from error
    return safe_projection(value, load_contract())


def emit(projection, output):
    keys = ("status", "host_phase", "failure_code", "guest_scene_stage",
            "release_acceptance", "private_runtime_removed", "screens_exported",
            "logs_exported", "pixels_exported", "live_startup_present",
            "installed_startup_present")
    require(type(projection) is dict and set(projection) == set(keys)
            and all(type(projection[key]) is bool for key in keys[4:]))
    tokens = []
    for key in keys:
        value = projection[key]
        rendered = ("true" if value is True else "false" if value is False else value)
        require(type(rendered) is str and re.fullmatch("[a-z0-9-]+", rendered))
        tokens.append(key + "=" + rendered)
    print("ARCTIC-SHOWCASE-SAFE-FAILURE " + " ".join(tokens), file=output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    activation_guard()
    emit(inspect(read_json_file(args.manifest, 32_768)), os.sys.stdout)


if __name__ == "__main__":
    main()
