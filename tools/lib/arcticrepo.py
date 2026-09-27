#!/usr/bin/env python3
"""Helpers for the Arctic package repository site (tools/publish-repo.sh, .github/workflows/repo.yml).

    arcticrepo.py prune --dir DIR [--keep 3] [--dry-run]
        Keep the newest N builds (distinct epoch:version-release, rpm order) of every package
        name among DIR/*.rpm and delete the rest.
    arcticrepo.py manifest --site DIR
        Write DIR/manifest.json: every file of the site with its size and sha256.
    arcticrepo.py fetch --dest DIR --base-url URL [--github-repo OWNER/REPO --workflow FILE]
                        [--start-fresh]
        Put the currently published site into DIR (empty), so a publish of one channel keeps
        the other: from the last successful workflow run's github-pages artifact when it is
        the live site (or newer: the live site lagging behind), else by downloading every
        file listed in the live manifest.json (sha256-checked). A live site that exists but
        can't be fetched completely is an error, and so is a GitHub API or artifact download
        that keeps failing (retried first). No live site is a first publish only when the
        workflow has never succeeded before (or without --github-repo); after earlier
        publishes it is an error unless their artifact restores the site.
    arcticrepo.py channel-info --site DIR --channel NAME --releasever N [--build-info FILE]
        Write repo/<channel>/fedora-<N>/PUBLISH-INFO.json (when, from which commit and run).
    arcticrepo.py index --site DIR --base-url URL [--fingerprint FPR]
        Write DIR/index.html, the landing page.

Standard library only; python3-rpm is used when present (headers, rpm.labelCompare), with a
faithful port of rpmvercmp() as the fallback so the tests run anywhere.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import datetime
import functools
import hashlib
import html
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

try:  # python3-rpm (Fedora); optional
    import rpm  # type: ignore
except ImportError:  # pragma: no cover - depends on the host
    rpm = None

MANIFEST = "manifest.json"
CHANNELS = ("stable", "testing")


# ---------------------------------------------------------------------------------------------
# Version comparison


def rpmvercmp(a: str, b: str) -> int:
    """rpm's rpmvercmp() (lib/rpmvercmp.c), including ~ (sorts first) and ^ (sorts after)."""
    if a == b:
        return 0
    i = j = 0
    la, lb = len(a), len(b)

    def sep(s: str, k: int, n: int) -> int:
        while k < n and not (s[k].isascii() and s[k].isalnum()) and s[k] not in "~^":
            k += 1
        return k

    while i < la or j < lb:
        i, j = sep(a, i, la), sep(b, j, lb)
        ca = a[i] if i < la else ""
        cb = b[j] if j < lb else ""
        if ca == "~" or cb == "~":
            if ca != "~":
                return 1
            if cb != "~":
                return -1
            i, j = i + 1, j + 1
            continue
        if ca == "^" or cb == "^":
            if not ca:
                return -1
            if not cb:
                return 1
            if ca != "^":
                return 1
            if cb != "^":
                return -1
            i, j = i + 1, j + 1
            continue
        if not (ca and cb):
            break
        si, sj = i, j
        if ca.isdigit():
            while i < la and a[i].isascii() and a[i].isdigit():
                i += 1
            while j < lb and b[j].isascii() and b[j].isdigit():
                j += 1
            isnum = True
        else:
            while i < la and a[i].isascii() and a[i].isalpha():
                i += 1
            while j < lb and b[j].isascii() and b[j].isalpha():
                j += 1
            isnum = False
        seg_a, seg_b = a[si:i], b[sj:j]
        if not seg_b:
            return 1 if isnum else -1
        if isnum:
            seg_a, seg_b = seg_a.lstrip("0"), seg_b.lstrip("0")
            if len(seg_a) != len(seg_b):
                return 1 if len(seg_a) > len(seg_b) else -1
        if seg_a != seg_b:
            return 1 if seg_a > seg_b else -1
    if i >= la and j >= lb:
        return 0
    return -1 if i >= la else 1


def _epoch(e) -> str:
    return "0" if e in (None, "") else str(e)


def label_compare(evr1: tuple, evr2: tuple) -> int:
    """Compare (epoch, version, release) tuples like rpm.labelCompare (missing epoch = 0)."""
    e1, v1, r1 = _epoch(evr1[0]), evr1[1], evr1[2]
    e2, v2, r2 = _epoch(evr2[0]), evr2[1], evr2[2]
    if rpm is not None:
        return rpm.labelCompare((e1, v1, r1), (e2, v2, r2))
    return rpmvercmp(e1, e2) or rpmvercmp(v1, v2) or rpmvercmp(r1, r2)


# ---------------------------------------------------------------------------------------------
# Packages


@dataclasses.dataclass(frozen=True)
class Pkg:
    name: str
    epoch: str
    version: str
    release: str
    arch: str
    path: str = ""

    @property
    def evr(self) -> tuple:
        return (self.epoch, self.version, self.release)

    @property
    def nevra(self) -> str:
        e = "" if self.epoch in ("", "0", None) else f"{self.epoch}:"
        return f"{self.name}-{e}{self.version}-{self.release}.{self.arch}"


_FILENAME = re.compile(r"^(?P<n>.+)-(?P<v>[^-]+)-(?P<r>[^-]+)\.(?P<a>[^.]+)\.rpm$")


def parse_filename(path: str) -> Pkg:
    """name-version-release.arch.rpm (the epoch isn't in file names: 0)."""
    m = _FILENAME.match(os.path.basename(path))
    if not m:
        raise ValueError(f"not an RPM file name: {path}")
    return Pkg(m["n"], "0", m["v"], m["r"], m["a"], path)


def read_package(path: str) -> Pkg:
    """The package's NEVRA from its header (python3-rpm), else from its file name."""
    if rpm is None:
        return parse_filename(path)
    ts = rpm.TransactionSet()
    ts.setVSFlags(rpm._RPMVSF_NOSIGNATURES | rpm._RPMVSF_NODIGESTS)
    with open(path, "rb") as f:
        h = ts.hdrFromFdno(f.fileno())

    def s(tag) -> str:
        v = h[tag]
        return v.decode() if isinstance(v, bytes) else ("" if v is None else str(v))

    arch = "src" if path.endswith(".src.rpm") else s(rpm.RPMTAG_ARCH)
    return Pkg(s(rpm.RPMTAG_NAME), _epoch(h[rpm.RPMTAG_EPOCH]), s(rpm.RPMTAG_VERSION),
               s(rpm.RPMTAG_RELEASE), arch, path)


def plan_prune(pkgs: list[Pkg], keep: int) -> tuple[list[Pkg], list[Pkg]]:
    """Split pkgs into (kept, removed): per package name, the newest `keep` distinct EVRs stay
    (every file of such a build, e.g. several arches); older builds go."""
    if keep < 1:
        raise ValueError("keep must be at least 1")
    by_name: dict[str, list[Pkg]] = {}
    for p in pkgs:
        by_name.setdefault(p.name, []).append(p)
    kept: list[Pkg] = []
    removed: list[Pkg] = []
    for name in sorted(by_name):
        group = by_name[name]
        evrs: list[tuple] = []
        for p in group:
            if not any(label_compare(p.evr, e) == 0 for e in evrs):
                evrs.append(p.evr)
        evrs.sort(key=functools.cmp_to_key(label_compare), reverse=True)
        newest = evrs[:keep]
        for p in sorted(group, key=lambda p: p.path):
            (kept if any(label_compare(p.evr, e) == 0 for e in newest) else removed).append(p)
    return kept, removed


def cmd_prune(args) -> int:
    files = sorted(os.path.join(args.dir, f) for f in os.listdir(args.dir) if f.endswith(".rpm"))
    kept, removed = plan_prune([read_package(f) for f in files], args.keep)
    for p in removed:
        print(f"prune: {os.path.basename(p.path)}")
        if not args.dry_run:
            os.remove(p.path)
    print(f"{args.dir}: {len(kept)} packages kept, {len(removed)} pruned (keep {args.keep} builds per name)")
    return 0


# ---------------------------------------------------------------------------------------------
# Manifest


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def site_files(site: str) -> list[dict]:
    out = []
    for dirpath, dirnames, filenames in os.walk(site):
        dirnames.sort()
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, site).replace(os.sep, "/")
            if rel == MANIFEST or os.path.islink(full):
                continue
            out.append({"path": rel, "size": os.path.getsize(full), "sha256": sha256_file(full)})
    return sorted(out, key=lambda f: f["path"])


def write_manifest(site: str) -> dict:
    files = site_files(site)
    doc = {
        "format": 1,
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_bytes": sum(f["size"] for f in files),
        "files": files,
    }
    with open(os.path.join(site, MANIFEST), "w") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
        f.write("\n")
    return doc


def cmd_manifest(args) -> int:
    doc = write_manifest(args.site)
    print(f"{os.path.join(args.site, MANIFEST)}: {len(doc['files'])} files, {doc['total_bytes']} bytes")
    return 0


def _safe_rel(path: str) -> bool:
    parts = path.split("/")
    return bool(path) and not path.startswith("/") and ".." not in parts and "" not in parts and "\\" not in path


def manifest_key(doc: dict) -> list:
    return sorted((f["path"], int(f["size"]), f["sha256"]) for f in doc.get("files", []))


def verify_tree(site: str, doc: dict) -> list[str]:
    """Problems between a tree and its manifest (missing files, size or sha256 mismatches)."""
    problems = []
    for f in doc.get("files", []):
        p = os.path.join(site, f["path"])
        if not _safe_rel(f["path"]):
            problems.append(f"unsafe path {f['path']!r}")
        elif not os.path.isfile(p):
            problems.append(f"missing {f['path']}")
        elif os.path.getsize(p) != int(f["size"]) or sha256_file(p) != f["sha256"]:
            problems.append(f"changed {f['path']}")
    return problems


# ---------------------------------------------------------------------------------------------
# Fetching the published site


class FetchError(Exception):
    """The published site can't be fetched reliably: publishing now could lose a channel."""


class GhNotFound(FetchError):
    """gh api answered 404/410: the thing asked for doesn't exist (e.g. an expired artifact)."""


class BadArtifact(FetchError):
    """The artifact was downloaded but is unreadable or doesn't match its manifest."""


class NoArtifact(Exception):
    """There is no usable github-pages artifact, for a known reason (not an error). first_publish:
    the runs query worked and the workflow has never succeeded, so nothing was ever deployed."""

    def __init__(self, msg: str, first_publish: bool = False):
        super().__init__(msg)
        self.first_publish = first_publish


def http_get(url: str, timeout: float = 60) -> tuple[int, bytes]:
    """(status, body); 4xx/5xx statuses are returned, network failures raise OSError."""
    req = urllib.request.Request(url, headers={"User-Agent": "arctic-publish", "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


def live_state(base_url: str, bust: str, get=http_get) -> tuple[str, dict | None]:
    """('present', manifest) | ('empty', None) | ('foreign', None) | ('error', None)."""
    try:
        status, body = get(f"{base_url}/{MANIFEST}?cb={bust}")
        if status == 200:
            try:
                doc = json.loads(body)
                if isinstance(doc, dict) and isinstance(doc.get("files"), list):
                    return "present", doc
            except ValueError:
                pass
            return "error", None
        if status != 404:
            return "error", None
        root_status, _ = get(f"{base_url}/?cb={bust}")
        if root_status == 404:
            return "empty", None
        return ("foreign" if root_status == 200 else "error"), None
    except OSError as e:
        print(f"fetch: {base_url}: {e}", file=sys.stderr)
        return "error", None


def download_live(base_url: str, doc: dict, dest: str, bust: str, get=http_get, workers: int = 8) -> None:
    """Every file in the live manifest into dest, each checked against its size and sha256."""
    files = doc.get("files", [])
    for f in files:
        if not _safe_rel(f.get("path", "")):
            raise FetchError(f"the live manifest lists an unsafe path: {f.get('path')!r}")

    def one(f: dict) -> None:
        url = f"{base_url}/{urllib.parse.quote(f['path'])}?cb={bust}"
        last = ""
        for attempt in range(4):
            try:
                status, body = get(url, timeout=300)
                if status == 200 and len(body) == int(f["size"]) and hashlib.sha256(body).hexdigest() == f["sha256"]:
                    p = os.path.join(dest, f["path"])
                    os.makedirs(os.path.dirname(p), exist_ok=True)
                    with open(p, "wb") as out:
                        out.write(body)
                    return
                last = f"HTTP {status}, {len(body)} bytes" if status != 200 else "size or sha256 mismatch"
            except OSError as e:
                last = str(e)
            time.sleep(min(2 ** attempt, 10) if get is http_get else 0)
        raise FetchError(f"{f['path']}: {last}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        errors = []
        for fut in [pool.submit(one, f) for f in files]:
            try:
                fut.result()
            except FetchError as e:
                errors.append(str(e))
    if errors:
        raise FetchError(f"{len(errors)} of {len(files)} files could not be fetched: " + "; ".join(errors[:5]))


def extract_pages_artifact(blob: bytes, dest: str) -> None:
    """A github-pages artifact (a zip holding artifact.tar, or the tar itself) into dest."""
    data = blob
    if data[:4] == b"PK\x03\x04":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = [n for n in z.namelist() if n.endswith(".tar")]
            if not names:
                raise FetchError("the artifact zip holds no .tar")
            data = z.read(names[0])
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as t:
        members = []
        for m in t.getmembers():
            name = m.name[2:] if m.name.startswith("./") else m.name
            if name in ("", "."):
                continue
            if not _safe_rel(name.rstrip("/")) or not (m.isfile() or m.isdir()):
                raise FetchError(f"unsafe artifact member {m.name!r}")
            members.append(m)
        try:
            t.extractall(dest, members=members, filter="data")
        except TypeError:  # Python without extraction filters (checked above)
            t.extractall(dest, members=members)


_GH_NOT_FOUND = re.compile(r"\bHTTP (404|410)\b")


def gh_api(args: list[str], binary: bool = False, attempts: int = 4, run=subprocess.run, sleep=time.sleep):
    """`gh api ARGS`: the JSON answer (or the raw bytes). Retried with backoff; 404/410 raise
    GhNotFound at once, anything else still failing after `attempts` tries raises FetchError."""
    what = f"gh api {' '.join(args)}"
    last = ""
    for attempt in range(attempts):
        r = run(["gh", "api", *args], capture_output=True, check=False)
        if r.returncode == 0:
            if binary:
                return r.stdout
            try:
                return json.loads(r.stdout)
            except ValueError as e:
                last = f"not JSON: {e}"
        else:
            last = r.stderr.decode(errors="replace").strip() or f"exit status {r.returncode}"
            if _GH_NOT_FOUND.search(last):
                raise GhNotFound(f"{what}: {last}")
        if attempt + 1 < attempts:
            print(f"fetch: {what}: {last} (retrying)", file=sys.stderr)
            sleep(min(5 * 2 ** attempt, 30))
    raise FetchError(f"{what}: failed {attempts} times: {last}")


def artifact_from_last_run(repo: str, workflow: str, dest: str, gh=gh_api) -> str:
    """Extract the github-pages artifact of the workflow's last successful run into dest and
    check it against its manifest.json. Returns a description. Raises NoArtifact when there is
    none to use (no successful run yet, or it expired), BadArtifact when it is broken, FetchError
    when the API or the download keeps failing."""
    current = os.environ.get("GITHUB_RUN_ID", "")
    runs = gh(["-X", "GET", f"repos/{repo}/actions/workflows/{workflow}/runs",
               "-f", "status=success", "-f", "per_page=20"]).get("workflow_runs", [])
    runs = [r for r in runs if str(r.get("id")) != current]
    if not runs:
        raise NoArtifact(f"no successful {workflow} run yet", first_publish=True)
    runs.sort(key=lambda r: r.get("run_started_at") or r.get("created_at") or "", reverse=True)
    run = runs[0]
    arts = gh([f"repos/{repo}/actions/runs/{run['id']}/artifacts", "-X", "GET", "-f", "per_page=100"]).get("artifacts", [])
    art = next((a for a in arts if a.get("name") == "github-pages" and not a.get("expired")), None)
    if art is None:
        raise NoArtifact(f"run {run['id']} has no (unexpired) github-pages artifact")
    what = f"artifact {art['id']} of run {run['id']} ({run.get('head_branch')}, {run.get('run_started_at')})"
    try:
        blob = gh([f"repos/{repo}/actions/artifacts/{art['id']}/zip"], binary=True)
    except GhNotFound as e:  # expired since it was listed
        raise NoArtifact(f"{what}: gone ({e})") from e
    try:
        extract_pages_artifact(blob, dest)
        doc_path = os.path.join(dest, MANIFEST)
        if not os.path.isfile(doc_path):
            raise BadArtifact(f"{what}: no {MANIFEST}")
        with open(doc_path) as f:
            doc = json.load(f)
        problems = verify_tree(dest, doc)
        if problems:
            raise BadArtifact(f"{what}: does not match its manifest: {'; '.join(problems[:5])}")
    except BadArtifact:
        raise
    except (FetchError, OSError, ValueError, KeyError, TypeError, tarfile.TarError, zipfile.BadZipFile) as e:
        raise BadArtifact(f"{what}: unreadable: {e}") from e
    print(f"fetch: {what}: {len(doc['files'])} files, complete")
    return what


def fetch_previous(dest: str, base_url: str, repo: str | None, workflow: str | None,
                   start_fresh: bool = False, get=http_get, gh=gh_api) -> str:
    """Fill the empty dir dest with the published site. Returns what was used: 'artifact',
    'live', 'fresh'. Raises FetchError when the other channel could be lost."""
    base_url = base_url.rstrip("/")
    if start_fresh:
        print("fetch: --start-fresh: publishing without the previous site (both channels start over)")
        return "fresh"
    bust = f"{int(time.time())}{os.getpid()}"
    state, live = live_state(base_url, bust, get)
    print(f"fetch: live site {base_url}: {state}" + (f" ({len(live['files'])} files)" if live else ""))

    # The last successful run's artifact. API and download failures are errors (after retries):
    # guessing instead could start from a stale copy of the other channel, or from nothing.
    art_dir = None
    no_artifact: NoArtifact | None = None
    bad_artifact = ""
    if repo and workflow:
        tmp = tempfile.mkdtemp(prefix="pages-artifact-", dir=os.path.dirname(os.path.abspath(dest)))
        try:
            artifact_from_last_run(repo, workflow, tmp, gh)
            art_dir = tmp
        except NoArtifact as e:
            print(f"fetch: no previous Pages artifact: {e}")
            no_artifact = e
        except BadArtifact as e:  # the live site may still be complete
            print(f"fetch: previous Pages artifact unusable: {e}")
            bad_artifact = str(e)
        finally:
            if art_dir is None:
                shutil.rmtree(tmp, ignore_errors=True)

    def use_artifact() -> str:
        for name in os.listdir(art_dir):
            shutil.move(os.path.join(art_dir, name), os.path.join(dest, name))
        shutil.rmtree(art_dir, ignore_errors=True)
        return "artifact"

    if state == "present":
        if art_dir:
            with open(os.path.join(art_dir, MANIFEST)) as f:
                art_doc = json.load(f)
            if manifest_key(art_doc) == manifest_key(live):
                return use_artifact()
            # Different: the newer one wins. A newer artifact means the live site still serves
            # the deployment before it; a newer live site was deployed from somewhere else.
            if str(art_doc.get("generated", "")) > str(live.get("generated", "")):
                print(f"fetch: the live site ({live.get('generated')}) lags behind the last deployment "
                      f"({art_doc.get('generated')}): using the artifact")
                return use_artifact()
            print("fetch: the live site is newer than the artifact (deployed from elsewhere?): downloading it")
            shutil.rmtree(art_dir, ignore_errors=True)
        download_live(base_url, live, dest, bust, get)
        problems = verify_tree(dest, live)
        if problems:
            raise FetchError("the downloaded live site is incomplete: " + "; ".join(problems[:5]))
        print(f"fetch: downloaded {len(live['files'])} files of the live site")
        return "live"
    if state == "empty":
        if art_dir:
            print("fetch: nothing is live; restoring the last published site from its artifact")
            return use_artifact()
        if not (repo and workflow) or (no_artifact is not None and no_artifact.first_publish):
            print("fetch: nothing published yet: first publish")
            return "fresh"
        why = bad_artifact or str(no_artifact)
        raise FetchError(f"{base_url} serves nothing, but {workflow} has published before and its last site "
                         f"can't be restored ({why}): refusing to deploy a site without the other channel; "
                         "rerun later (Pages may be briefly unavailable), or with --start-fresh to start the "
                         "repository over")
    if art_dir:
        shutil.rmtree(art_dir, ignore_errors=True)
    if state == "foreign":
        raise FetchError(f"{base_url} serves a site without {MANIFEST} (not published by this tooling): "
                         "refusing to replace it; rerun with --start-fresh to start the repository over")
    raise FetchError(f"could not read {base_url}/{MANIFEST}: refusing to publish a site that may lack the "
                     "other channel; rerun later, or with --start-fresh to start the repository over")


def cmd_fetch(args) -> int:
    os.makedirs(args.dest, exist_ok=True)
    if os.listdir(args.dest):
        print(f"fetch: {args.dest} is not empty", file=sys.stderr)
        return 2
    try:
        how = fetch_previous(args.dest, args.base_url, args.github_repo, args.workflow, args.start_fresh)
    except FetchError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"fetch: previous site from: {how}")
    if args.output:
        with open(args.output, "a") as f:
            f.write(f"source={how}\n")
    return 0


# ---------------------------------------------------------------------------------------------
# Channel info and the landing page


def read_build_info(path: str | None) -> dict:
    info: dict = {"rpm": [], "srpm": []}
    if not path or not os.path.isfile(path):
        return info
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k in ("rpm", "srpm"):
                info[k].append(v)
            else:
                info[k] = v
    return info


def cmd_channel_info(args) -> int:
    info = read_build_info(args.build_info)
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    run = ""
    if os.environ.get("GITHUB_RUN_ID") and os.environ.get("GITHUB_REPOSITORY"):
        run = f"{server}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    doc = {
        "channel": args.channel,
        "published": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "version": info.get("version", ""),
        "release_suffix": info.get("release_suffix", ""),
        "git_commit": info.get("git_commit", ""),
        "ref": os.environ.get("ARCTIC_SOURCE_REF", os.environ.get("GITHUB_REF_NAME", "")),
        "run": run,
        "packages": info["rpm"],
    }
    d = os.path.join(args.site, "repo", args.channel, f"fedora-{args.releasever}")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "PUBLISH-INFO.json"), "w") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
        f.write("\n")
    return 0


def _latest_packages(d: str) -> list[Pkg]:
    if not os.path.isdir(d):
        return []
    pkgs = [read_package(os.path.join(d, f)) for f in sorted(os.listdir(d)) if f.endswith(".rpm")]
    latest: dict[str, Pkg] = {}
    for p in pkgs:
        if p.name not in latest or label_compare(p.evr, latest[p.name].evr) > 0:
            latest[p.name] = p
    return [latest[n] for n in sorted(latest)]


def render_index(site: str, base_url: str, fingerprint: str = "") -> str:
    base_url = base_url.rstrip("/")
    e = html.escape
    sections = []
    for ch in CHANNELS:
        ch_root = os.path.join(site, "repo", ch)
        if not os.path.isdir(ch_root):
            continue
        for rel in sorted(os.listdir(ch_root)):
            d = os.path.join(ch_root, rel)
            if not rel.startswith("fedora-"):
                continue
            info = {}
            if os.path.isfile(os.path.join(d, "PUBLISH-INFO.json")):
                with open(os.path.join(d, "PUBLISH-INFO.json")) as f:
                    info = json.load(f)
            rows = "".join(
                f"<tr><td>{e(p.name)}</td><td>{e(p.version)}-{e(p.release)}</td><td>{e(p.arch)}</td></tr>"
                for p in _latest_packages(os.path.join(d, "x86_64")))
            commit = info.get("git_commit", "")
            meta = []
            if info.get("published"):
                meta.append(f"published {e(info['published'])}")
            if commit:
                meta.append(f"commit <code>{e(commit[:12])}</code>")
            if info.get("ref"):
                meta.append(f"from <code>{e(info['ref'])}</code>")
            if info.get("run"):
                meta.append(f"<a href=\"{e(info['run'])}\">build log</a>")
            url = f"{base_url}/repo/{ch}/{rel}/x86_64/"
            sections.append(
                f"<section><h2>{e(ch.capitalize())} <span>{e(rel.replace('fedora-', 'Fedora '))}</span></h2>"
                f"<p class=meta>{' · '.join(meta)}</p>"
                f"<p><a href=\"{e(url)}\">{e(url)}</a></p>"
                f"<table><thead><tr><th>Package</th><th>Newest build</th><th>Arch</th></tr></thead>"
                f"<tbody>{rows}</tbody></table></section>")
    fpr = ""
    if fingerprint:
        fpr = f"<p>Fingerprint: <code>{e(' '.join(fingerprint[i:i + 4] for i in range(0, len(fingerprint), 4)))}</code></p>"
    body = "\n".join(sections) or "<p>Nothing is published yet.</p>"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Arctic Linux packages</title>
<style>
:root {{ --bg: #f4f7fa; --fg: #14202b; --muted: #5b6b79; --line: #d5dee6; --accent: #b86f12; --card: #ffffff; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg: #0e151c; --fg: #e3eaf0; --muted: #8fa0ae; --line: #22303c; --accent: #efa637; --card: #141e27; }}
}}
body {{ margin: 0; background: var(--bg); color: var(--fg); font: 16px/1.5 system-ui, sans-serif; }}
main {{ max-width: 820px; margin: 0 auto; padding: 32px 16px 64px; }}
h1 {{ font-size: 1.8rem; margin: 0 0 4px; }}
h2 {{ font-size: 1.2rem; margin: 0 0 4px; }} h2 span {{ color: var(--muted); font-weight: 400; }}
a {{ color: var(--accent); }}
code, pre {{ font-family: ui-monospace, "JetBrains Mono", monospace; font-size: .9em; }}
pre {{ background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 12px; overflow-x: auto; }}
section {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 16px; margin: 16px 0; overflow-x: auto; }}
.meta {{ color: var(--muted); margin: 0 0 8px; font-size: .9rem; }}
table {{ border-collapse: collapse; width: 100%; font-size: .9rem; }}
th, td {{ text-align: left; padding: 4px 8px 4px 0; border-bottom: 1px solid var(--line); }}
</style>
</head>
<body>
<main>
<h1>Arctic Linux packages</h1>
<p>The signed package repository of <a href="https://github.com/yuvalkolodkingal/O-Tism">Arctic Linux</a>:
the arctic-* packages and mangowm, built for Fedora 44. Arctic Linux has it built in
(arctic-release): <b>stable</b> (builds of the main branch) is on, <b>testing</b> (builds of the
development branch) is off. To follow testing, or to go back:</p>
<pre>sudo dnf config-manager setopt arctic-testing.enabled=1
sudo dnf config-manager setopt arctic-testing.enabled=0</pre>
<p>Repository files for other Fedora 44 systems: <a href="arctic.repo">arctic.repo</a>,
<a href="arctic-testing.repo">arctic-testing.repo</a>
(<code>sudo dnf config-manager addrepo --from-repofile={e(base_url)}/arctic.repo</code>).
Signing key: <a href="RPM-GPG-KEY-arctic">RPM-GPG-KEY-arctic</a>. Every file with its size and
sha256: <a href="manifest.json">manifest.json</a>.</p>
{fpr}
{body}
</main>
</body>
</html>
"""


def cmd_index(args) -> int:
    with open(os.path.join(args.site, "index.html"), "w") as f:
        f.write(render_index(args.site, args.base_url, args.fingerprint or ""))
    return 0


# ---------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prune")
    p.add_argument("--dir", required=True)
    p.add_argument("--keep", type=int, default=3)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_prune)

    p = sub.add_parser("manifest")
    p.add_argument("--site", required=True)
    p.set_defaults(func=cmd_manifest)

    p = sub.add_parser("fetch")
    p.add_argument("--dest", required=True)
    p.add_argument("--base-url", required=True)
    p.add_argument("--github-repo")
    p.add_argument("--workflow")
    p.add_argument("--start-fresh", action="store_true")
    p.add_argument("--output", help="append source=artifact|live|fresh to this file")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("channel-info")
    p.add_argument("--site", required=True)
    p.add_argument("--channel", required=True, choices=CHANNELS)
    p.add_argument("--releasever", required=True)
    p.add_argument("--build-info")
    p.set_defaults(func=cmd_channel_info)

    p = sub.add_parser("index")
    p.add_argument("--site", required=True)
    p.add_argument("--base-url", required=True)
    p.add_argument("--fingerprint")
    p.set_defaults(func=cmd_index)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
