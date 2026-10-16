#!/usr/bin/env python3
"""Publish an already screened, hash-bound review bundle to a private draft release."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
import zipfile


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "yuvalkolodkingal/Arctic-Linux"
SOURCE_BRANCH = "codex/private-media-review-exporter-20261016"
MARKER = ".github/private-media-review-export-20261016.activate"
MANIFEST = "tools/private-media-review/manifest.json"
REVIEW_SCHEMA = "arctic-private-qualification-media-review-result-v1"
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
SAFE_PNG = re.compile(r"[a-z0-9][a-z0-9._-]{0,199}\.png")
MAX_BUNDLE_BYTES = 252_000_000
MAX_ASSETS = 257
MAX_ASSET_BYTES = 32_000_000
MAX_REVIEW_BYTES = 2_000_000
MAX_API_BYTES = 2_000_000


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(type(key) is str and key not in result, "Duplicate or invalid JSON field")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def digest_file(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True,
                                   timeout=120).strip()


def validate_activation(manifest_path):
    require(os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
            and os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
            and os.environ.get("GITHUB_REF") == "refs/heads/" + SOURCE_BRANCH
            and os.environ.get("GITHUB_EVENT_NAME") == "push"
            and os.environ.get("GITHUB_RUN_ATTEMPT") == "1",
            "Requires the dedicated first-attempt GitHub-hosted draft publication lane")
    event = strict_json(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    preparation = (ROOT / MARKER).read_text().strip()
    activation = git("rev-parse", "HEAD")
    require(HEX40.fullmatch(preparation) and event.get("before") == preparation
            and event.get("after") == os.environ.get("GITHUB_SHA") == activation
            and git("rev-list", "--parents", "-n", "1", "HEAD").split() == [activation, preparation]
            and git("diff", "--no-renames", "--name-only", preparation, activation).splitlines() == [MARKER]
            and not git("status", "--porcelain"),
            "Draft publication activation is not the reviewed marker-only child")
    manifest = strict_json(Path(manifest_path).read_text())
    release = manifest.get("draft_release")
    require(manifest.get("repository") == REPOSITORY
            and manifest.get("source_branch") == SOURCE_BRANCH and manifest.get("ready") is True
            and manifest.get("review_only") is True and type(manifest.get("artifacts")) is list
            and type(release) is dict and release.get("draft") is True
            and release.get("prerelease") is False and release.get("public") is False
            and release.get("human_review") == "pending"
            and release.get("release_acceptance") is False
            and re.fullmatch(r"private-qualification-review-[0-9]{8}", release.get("tag", "")),
            "Draft publication manifest is not a private pending review")
    return manifest, preparation, activation


def safe_bundle_member(info):
    name = info.filename
    require(type(name) is str and name and "\x00" not in name and "\\" not in name,
            "Unsafe screened bundle member")
    path = PurePosixPath(name)
    require(not path.is_absolute() and len(path.parts) == 1 and path.parts[0] not in (".", "..")
            and (name == "REVIEW-MANIFEST.json" or SAFE_PNG.fullmatch(name)),
            "Screened bundle member is not a declared flat review asset")
    mode = (info.external_attr >> 16) & 0o170000
    require(mode in (0, stat.S_IFREG) and not info.is_dir() and not info.flag_bits & 0x1
            and info.compress_type == zipfile.ZIP_STORED,
            "Screened bundle member type or compression differs")
    maximum = MAX_REVIEW_BYTES if name == "REVIEW-MANIFEST.json" else MAX_ASSET_BYTES
    require(0 < info.file_size <= maximum and info.compress_size == info.file_size,
            "Screened bundle member exceeds its bound")
    return name


def artifact_projection(artifact):
    return {
        "archive_bytes": artifact["archive_bytes"], "archive_sha256": artifact["archive_sha256"],
        "artifact_id": artifact["artifact_id"], "artifact_name": artifact["artifact_name"],
        "head_sha": artifact["head_sha"], "lane": artifact["lane"],
        "run_attempt": artifact["run_attempt"], "run_id": artifact["run_id"],
        "workflow_id": artifact["workflow_id"], "workflow_path": artifact["workflow_path"],
    }


def unpack_bundle(bundle, expected_sha256, manifest, preparation, activation, destination):
    bundle = Path(bundle)
    require(type(expected_sha256) is str and HEX64.fullmatch(expected_sha256)
            and bundle.is_file() and not bundle.is_symlink()
            and 0 < bundle.stat().st_size <= MAX_BUNDLE_BYTES
            and digest_file(bundle) == expected_sha256,
            "Screened bundle differs from the read-only job's hash binding")
    with zipfile.ZipFile(bundle) as archive:
        listed = archive.infolist()
        require(2 <= len(listed) <= MAX_ASSETS, "Screened bundle asset count is invalid")
        infos = {}
        for info in listed:
            name = safe_bundle_member(info)
            require(name not in infos, "Screened bundle contains duplicate assets")
            infos[name] = info
        require("REVIEW-MANIFEST.json" in infos, "Screened review manifest is absent")
        review = strict_json(archive.read(infos["REVIEW-MANIFEST.json"]).decode("utf-8"))
        require(set(review) == {"schema", "review_only", "release_acceptance", "human_review",
                               "repository", "preparation_sha", "activation_sha", "draft_release",
                               "artifacts", "assets", "asset_count", "png_count", "png_bytes", "privacy"}
                and review["schema"] == REVIEW_SCHEMA and review["review_only"] is True
                and review["release_acceptance"] is False and review["human_review"] == "pending"
                and review["repository"] == REPOSITORY and review["preparation_sha"] == preparation
                and review["activation_sha"] == activation
                and review["draft_release"] == manifest["draft_release"]
                and review["artifacts"] == [artifact_projection(item) for item in manifest["artifacts"]]
                and review["privacy"] == {"audio_exported": False, "logs_exported": False,
                                          "raw_archives_exported": False,
                                          "transcripts_exported": False},
                "Screened review manifest identity or pending state differs")
        require(type(review["assets"]) is list and review["asset_count"] == len(review["assets"]) + 1
                and review["png_count"] == len(review["assets"]),
                "Screened review manifest counts differ")
        expected = {}
        total = 0
        fields = {"artifact_id", "asset_name", "bytes", "height", "kind", "lane", "member",
                  "privacy_class", "sha256", "width", "screening"}
        for item in review["assets"]:
            require(type(item) is dict and set(item) == fields and item["kind"] == "png"
                    and item["privacy_class"] == "screened-synthetic-vm-ui"
                    and item["screening"] == ["producer-inventory-exact", "png-metadata-absent",
                                               "ocr-sensitive-shapes-absent"]
                    and SAFE_PNG.fullmatch(item["asset_name"])
                    and item["asset_name"] not in expected
                    and type(item["bytes"]) is int and 0 < item["bytes"] <= MAX_ASSET_BYTES
                    and type(item["sha256"]) is str and HEX64.fullmatch(item["sha256"]),
                    "Screened PNG record is malformed")
            expected[item["asset_name"]] = (item["bytes"], item["sha256"])
            total += item["bytes"]
        require(set(infos) == set(expected) | {"REVIEW-MANIFEST.json"}
                and review["png_bytes"] == total, "Screened bundle inventory differs")
        destination.mkdir(mode=0o700)
        records = {}
        for name, (size, digest) in expected.items():
            raw = archive.read(infos[name])
            require(len(raw) == size and hashlib.sha256(raw).hexdigest() == digest,
                    "Screened PNG differs from its review record")
            path = destination / name
            with path.open("xb") as stream:
                stream.write(raw)
            path.chmod(0o600); records[name] = {"bytes": size, "sha256": digest}
        review_raw = archive.read(infos["REVIEW-MANIFEST.json"])
        review_path = destination / "REVIEW-MANIFEST.json"
        with review_path.open("xb") as stream:
            stream.write(review_raw)
        review_path.chmod(0o600)
        records[review_path.name] = {"bytes": len(review_raw),
                                     "sha256": hashlib.sha256(review_raw).hexdigest()}
        return records


def api_request(method, endpoint, *, payload=None, raw=None, content_type="application/json"):
    require((payload is None) != (raw is None) or (payload is None and raw is None),
            "API request body is ambiguous")
    token = os.environ.get("GH_TOKEN")
    require(type(token) is str and token, "GitHub token is unavailable")
    url = endpoint if endpoint.startswith("https://") else "https://api.github.com/" + endpoint
    data = None
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode()
    elif raw is not None:
        data = raw
    request = Request(url, data=data, method=method, headers={
        "Accept": "application/vnd.github+json", "Authorization": "Bearer " + token,
        "Content-Type": content_type, "User-Agent": "arctic-private-review-publisher",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with urlopen(request, timeout=120) as response:
            body = response.read(MAX_API_BYTES + 1)
            require(len(body) <= MAX_API_BYTES, "GitHub API response exceeds its bound")
            return response.status, body
    except HTTPError as error:
        body = error.read(MAX_API_BYTES + 1)
        require(len(body) <= MAX_API_BYTES, "GitHub API error response exceeds its bound")
        return error.code, body
    except URLError as error:
        raise RuntimeError("GitHub API transport failed") from error


def api_json(method, endpoint, expected_status, **kwargs):
    status, raw = api_request(method, endpoint, **kwargs)
    require(status == expected_status, f"GitHub API status differs: {status}")
    if not raw:
        return None
    try:
        return strict_json(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise RuntimeError("GitHub API JSON is invalid") from error


def require_absent(endpoint, label):
    status, _ = api_request("GET", endpoint)
    if status == 404:
        return
    if status == 200:
        raise RuntimeError(label + " already exists")
    raise RuntimeError(f"{label} absence check returned HTTP {status}")


def resolve_tag(tag, activation):
    value = api_json("GET", f"repos/{REPOSITORY}/git/ref/tags/{quote(tag, safe='')}", 200)
    require(type(value) is dict and type(value.get("object")) is dict,
            "Created review tag reference is malformed")
    target = value["object"]
    for _ in range(4):
        require(type(target.get("sha")) is str and HEX40.fullmatch(target["sha"])
                and target.get("type") in ("commit", "tag"), "Created review tag target is malformed")
        if target["type"] == "commit":
            require(target["sha"] == activation, "Created review tag does not resolve to activation")
            return
        value = api_json("GET", f"repos/{REPOSITORY}/git/tags/{target['sha']}", 200)
        require(type(value) is dict and type(value.get("object")) is dict,
                "Annotated review tag object is malformed")
        target = value["object"]
    raise RuntimeError("Created review tag chain exceeds its bound")


def verify_absent_after_cleanup(release_tag_endpoint, ref_endpoint):
    problems = []
    for endpoint, label in ((release_tag_endpoint, "release"), (ref_endpoint, "tag")):
        try:
            status, _ = api_request("GET", endpoint)
            if status != 404:
                problems.append(label + f" remained with HTTP {status}")
        except BaseException:
            problems.append(label + " absence could not be verified")
    if problems:
        raise RuntimeError("Incomplete private draft cleanup: " + "; ".join(problems))


def cleanup_created(release_id, tag, tag_created):
    release_tag_endpoint = f"repos/{REPOSITORY}/releases/tags/{quote(tag, safe='')}"
    ref_endpoint = f"repos/{REPOSITORY}/git/ref/tags/{quote(tag, safe='')}"
    problems = []
    if release_id is not None:
        try:
            status, _ = api_request("DELETE", f"repos/{REPOSITORY}/releases/{release_id}")
            if status not in (204, 404):
                problems.append(f"release deletion returned HTTP {status}")
        except BaseException:
            problems.append("release deletion failed")
    if tag_created:
        try:
            status, _ = api_request("GET", ref_endpoint)
            if status == 200:
                status, _ = api_request("DELETE", f"repos/{REPOSITORY}/git/refs/tags/{quote(tag, safe='')}")
                if status != 204:
                    problems.append(f"tag deletion returned HTTP {status}")
            elif status != 404:
                problems.append(f"tag cleanup check returned HTTP {status}")
        except BaseException:
            problems.append("tag deletion failed")
    try:
        verify_absent_after_cleanup(release_tag_endpoint, ref_endpoint)
    except BaseException:
        problems.append("release/tag absence verification failed")
    if problems:
        raise RuntimeError("Incomplete private draft cleanup: " + "; ".join(problems))


def publish(manifest_path, bundle, bundle_sha256):
    manifest, preparation, activation = validate_activation(manifest_path)
    release = manifest["draft_release"]
    tag = release["tag"]
    release_tag_endpoint = f"repos/{REPOSITORY}/releases/tags/{quote(tag, safe='')}"
    ref_endpoint = f"repos/{REPOSITORY}/git/ref/tags/{quote(tag, safe='')}"
    require_absent(release_tag_endpoint, "Private review release")
    require_absent(ref_endpoint, "Private review tag")
    release_id = None
    tag_created = False
    with tempfile.TemporaryDirectory(prefix="arctic-private-publish-",
                                     dir=os.environ.get("RUNNER_TEMP")) as temporary:
        private = Path(temporary); private.chmod(0o700)
        output = private / "assets"
        assets = unpack_bundle(bundle, bundle_sha256, manifest, preparation, activation, output)
        try:
            created_ref = api_json("POST", f"repos/{REPOSITORY}/git/refs", 201,
                                   payload={"ref": "refs/tags/" + tag, "sha": activation})
            require(type(created_ref) is dict and created_ref.get("ref") == "refs/tags/" + tag,
                    "Created private review tag differs")
            tag_created = True
            resolve_tag(tag, activation)
            body = ("Private qualification media for collaborator review only. "
                    "Human review is pending; this draft is not release acceptance and must not be published.")
            created = api_json("POST", f"repos/{REPOSITORY}/releases", 201, payload={
                "tag_name": tag, "target_commitish": activation, "name": release["name"],
                "body": body, "draft": True, "prerelease": False, "make_latest": "false",
            })
            release_id = created.get("id")
            require(type(release_id) is int and created.get("draft") is True
                    and created.get("prerelease") is False and created.get("tag_name") == tag
                    and created.get("target_commitish") == activation,
                    "Created review destination is not the exact private draft")
            resolve_tag(tag, activation)
            for name in sorted(assets):
                path = output / name
                require(path.is_file() and not path.is_symlink()
                        and path.stat().st_size == assets[name]["bytes"]
                        and digest_file(path) == assets[name]["sha256"],
                        "Draft asset differs before upload")
                content_type = "image/png" if name.endswith(".png") else "application/json"
                uploaded = api_json("POST",
                    f"https://uploads.github.com/repos/{REPOSITORY}/releases/{release_id}/assets?name={quote(name)}",
                    201, raw=path.read_bytes(), content_type=content_type)
                require(uploaded.get("name") == name and uploaded.get("size") == assets[name]["bytes"]
                        and uploaded.get("digest") == "sha256:" + assets[name]["sha256"],
                        "Uploaded draft asset identity differs")
            final = api_json("GET", f"repos/{REPOSITORY}/releases/{release_id}", 200)
            listed = []
            for page in range(1, math.ceil(len(assets) / 100) + 1):
                batch = api_json("GET",
                    f"repos/{REPOSITORY}/releases/{release_id}/assets?per_page=100&page={page}", 200)
                require(type(batch) is list and 1 <= len(batch) <= 100,
                        "Private draft asset page is malformed")
                listed.extend(batch)
            require(final.get("draft") is True and final.get("prerelease") is False
                    and final.get("tag_name") == tag and final.get("name") == release["name"]
                    and final.get("target_commitish") == activation
                    and {item.get("name") for item in listed} == set(assets),
                    "Private draft release verification differs")
            by_name = {item["name"]: item for item in listed}
            for name, pin in assets.items():
                require(by_name[name].get("size") == pin["bytes"]
                        and by_name[name].get("digest") == "sha256:" + pin["sha256"],
                        "Private draft asset verification differs")
            resolve_tag(tag, activation)
            print(json.dumps({"draft_release_id": release_id, "draft": True,
                              "human_review": "pending", "asset_count": len(assets)}, sort_keys=True))
        except BaseException as original:
            try:
                cleanup_created(release_id, tag, tag_created)
            except BaseException as cleanup:
                raise RuntimeError("Private draft failed and cleanup could not be verified") from cleanup
            raise original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--bundle-sha256", required=True)
    args = parser.parse_args()
    publish(args.manifest, args.bundle, args.bundle_sha256)


if __name__ == "__main__":
    main()
