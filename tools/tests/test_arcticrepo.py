"""Tests for tools/lib/arcticrepo.py: rpm version order, pruning, manifests, fetching the site.

    python3 -m unittest discover -s tools/tests -p 'test_*.py' -v

Synthetic NEVRAs only; nothing here needs a network, a key or real RPMs. With python3-rpm
installed the pure-Python rpmvercmp() is also checked against rpm.labelCompare.
"""

import functools
import hashlib
import http.server
import io
import json
import os
import sys
import tarfile
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import arcticrepo as ar  # noqa: E402

# (a, b, rpmvercmp(a, b)): rpm's own test suite (tests/rpmvercmp.at) plus Arctic's releases.
VERCMP = [
    ("1.0", "1.0", 0), ("1.0", "2.0", -1), ("2.0", "1.0", 1),
    ("2.0.1", "2.0.1", 0), ("2.0", "2.0.1", -1), ("2.0.1", "2.0", 1),
    ("2.0.1a", "2.0.1a", 0), ("2.0.1a", "2.0.1", 1), ("2.0.1", "2.0.1a", -1),
    ("5.5p1", "5.5p1", 0), ("5.5p1", "5.5p2", -1), ("5.5p2", "5.5p1", 1),
    ("5.5p10", "5.5p10", 0), ("5.5p1", "5.5p10", -1), ("5.5p10", "5.5p1", 1),
    ("10xyz", "10.1xyz", -1), ("10.1xyz", "10xyz", 1),
    ("xyz10", "xyz10", 0), ("xyz10", "xyz10.1", -1), ("xyz10.1", "xyz10", 1),
    ("xyz.4", "xyz.4", 0), ("xyz.4", "8", -1), ("8", "xyz.4", 1), ("xyz.4", "2", -1), ("2", "xyz.4", 1),
    ("5.5p2", "5.6p1", -1), ("5.6p1", "5.5p2", 1), ("5.6p1", "6.5p1", -1), ("6.5p1", "5.6p1", 1),
    ("6.0.rc1", "6.0", 1), ("6.0", "6.0.rc1", -1),
    ("10b2", "10a1", 1), ("10a2", "10b2", -1),
    ("1.0aa", "1.0aa", 0), ("1.0a", "1.0aa", -1), ("1.0aa", "1.0a", 1),
    ("10.0001", "10.0001", 0), ("10.0001", "10.1", 0), ("10.1", "10.0001", 0),
    ("10.0001", "10.0039", -1), ("10.0039", "10.0001", 1),
    ("4.999.9", "5.0", -1), ("5.0", "4.999.9", 1),
    ("20101121", "20101121", 0), ("20101121", "20101122", -1), ("20101122", "20101121", 1),
    ("2_0", "2_0", 0), ("2.0", "2_0", 0), ("2_0", "2.0", 0),
    ("a", "a", 0), ("a+", "a+", 0), ("a+", "a_", 0), ("a_", "a+", 0),
    ("+a", "+a", 0), ("+a", "_a", 0), ("_a", "+a", 0),
    ("+_", "+_", 0), ("_+", "+_", 0), ("_+", "_+", 0), ("+", "_", 0), ("_", "+", 0),
    ("1.0~rc1", "1.0~rc1", 0), ("1.0~rc1", "1.0", -1), ("1.0", "1.0~rc1", 1),
    ("1.0~rc1", "1.0~rc2", -1), ("1.0~rc2", "1.0~rc1", 1),
    ("1.0~rc1~git123", "1.0~rc1~git123", 0), ("1.0~rc1~git123", "1.0~rc1", -1), ("1.0~rc1", "1.0~rc1~git123", 1),
    ("1.0^", "1.0^", 0), ("1.0^", "1.0", 1), ("1.0", "1.0^", -1),
    ("1.0^git1", "1.0^git1", 0), ("1.0^git1", "1.0", 1), ("1.0", "1.0^git1", -1),
    ("1.0^git1", "1.0^git2", -1), ("1.0^git2", "1.0^git1", 1),
    ("1.0^git1", "1.01", -1), ("1.01", "1.0^git1", 1),
    ("1.0^20160101", "1.0^20160101", 0), ("1.0^20160101", "1.0.1", -1), ("1.0.1", "1.0^20160101", 1),
    ("1.0^20160101^git1", "1.0^20160101^git1", 0), ("1.0^20160102", "1.0^20160101^git1", 1),
    ("1.0^20160101^git1", "1.0^20160102", -1),
    ("1.0~rc1^git1", "1.0~rc1^git1", 0), ("1.0~rc1^git1", "1.0~rc1", 1), ("1.0~rc1", "1.0~rc1^git1", -1),
    ("1.0^git1~pre", "1.0^git1~pre", 0), ("1.0^git1", "1.0^git1~pre", 1), ("1.0^git1~pre", "1.0^git1", -1),
    # Arctic: every build's Release is 1.<UTC commit yyyymmddHHMMSS>.<UTC build yyyymmddHHMM>
    # .git<commit>.fc44. Newer code wins, whenever it was built:
    ("1.20260928031005.202609280310.gitabc1234.fc44", "1.20260928031006.202609280311.git0000000.fc44", -1),
    ("1.20260927120000.202610050000.gitaaaaaaa.fc44", "1.20260928090000.202609280905.gitbbbbbbb.fc44", -1),
    ("1.20261231235959.202701010000.gitabc1234.fc44", "1.20270101000000.202701010001.gitdef5678.fc44", -1),
    # the same commit built again: the later build wins
    ("1.20260928031005.202609280310.gitabc1234.fc44", "1.20260928031005.202609281200.gitabc1234.fc44", -1),
    # every build of this scheme is newer than the builds of the earlier 1.<build time>.git… one
    ("1.202612312359.gitabc1234.fc44", "1.20260927000000.202609270001.gitabc1234.fc44", -1),
    ("1.202609280310.gitabc1234.fc44", "1.202609280311.git0000000.fc44", -1),
    # an unsuffixed local build (--release-suffix none) is older than any snapshot build
    ("1.fc44", "1.20260928031005.202609280310.gitabc1234.fc44", -1),
]


def pkg(nevra: str, path: str = "") -> ar.Pkg:
    """'name-[epoch:]version-release.arch' → Pkg."""
    rest, arch = nevra.rsplit(".", 1)
    rest, release = rest.rsplit("-", 1)
    name, version = rest.rsplit("-", 1)
    epoch = "0"
    if ":" in version:
        epoch, version = version.split(":", 1)
    return ar.Pkg(name, epoch, version, release, arch, path or f"/r/{name}-{version}-{release}.{arch}.rpm")


class VersionOrder(unittest.TestCase):
    def test_rpmvercmp(self):
        for a, b, want in VERCMP:
            with self.subTest(a=a, b=b):
                self.assertEqual(ar.rpmvercmp(a, b), want)

    @unittest.skipIf(ar.rpm is None, "python3-rpm is not installed")
    def test_matches_rpm(self):
        for a, b, _ in VERCMP:
            with self.subTest(a=a, b=b):
                self.assertEqual(ar.rpmvercmp(a, b), ar.rpm.labelCompare(("0", a, "1"), ("0", b, "1")))

    def test_label_compare_epoch_first(self):
        self.assertEqual(ar.label_compare(("1", "0.1", "1"), ("0", "9.9", "9")), 1)
        self.assertEqual(ar.label_compare((None, "1", "1"), ("0", "1", "1")), 0)
        self.assertEqual(ar.label_compare(("", "1", "1.fc44"), ("0", "1", "2.fc44")), -1)


class Prune(unittest.TestCase):
    def names(self, pkgs):
        return sorted(p.nevra for p in pkgs)

    def test_keeps_newest_three_builds_per_name(self):
        builds = [f"1.2026092{d}0310.gitabc{d}234.fc44" for d in range(5)]
        pkgs = [pkg(f"arctic-shell-0.2.0-{r}.noarch") for r in builds]
        pkgs += [pkg(f"arctic-installer-0.2.0-{r}.x86_64") for r in builds]
        kept, removed = ar.plan_prune(pkgs, 3)
        self.assertEqual(len(kept), 6)
        self.assertEqual(self.names(removed), self.names([
            pkg(f"arctic-shell-0.2.0-{builds[0]}.noarch"), pkg(f"arctic-shell-0.2.0-{builds[1]}.noarch"),
            pkg(f"arctic-installer-0.2.0-{builds[0]}.x86_64"), pkg(f"arctic-installer-0.2.0-{builds[1]}.x86_64")]))

    def test_order_is_rpm_order_not_file_order(self):
        # A version bump beats a newer build time of the older version, 10 > 9, ~ sorts first.
        pkgs = [pkg("mangowm-0.17.3-1.202609280310.gitaaaaaaa.fc44.x86_64"),
                pkg("mangowm-0.9.0-1.202612310000.gitbbbbbbb.fc44.x86_64"),
                pkg("mangowm-0.18.0~rc1-1.202609010000.gitccccccc.fc44.x86_64"),
                pkg("mangowm-0.18.0-1.202608010000.gitddddddd.fc44.x86_64"),
                pkg("mangowm-0.10.0-1.fc44.x86_64")]
        kept, removed = ar.plan_prune(pkgs, 2)
        self.assertEqual(self.names(kept), ["mangowm-0.18.0-1.202608010000.gitddddddd.fc44.x86_64",
                                            "mangowm-0.18.0~rc1-1.202609010000.gitccccccc.fc44.x86_64"])
        self.assertEqual(len(removed), 3)

    def test_epoch_wins(self):
        pkgs = [pkg("foo-1:0.1-1.fc44.noarch"), pkg("foo-2.0-1.fc44.noarch"), pkg("foo-3.0-1.fc44.noarch")]
        kept, _ = ar.plan_prune(pkgs, 1)
        self.assertEqual(self.names(kept), ["foo-1:0.1-1.fc44.noarch"])

    def test_one_build_in_several_files_counts_once(self):
        # The same EVR for two arches (a package that turned noarch) is one build.
        r = ["1.202609010000.gita.fc44", "1.202609020000.gitb.fc44", "1.202609030000.gitc.fc44"]
        pkgs = [pkg(f"bar-1.0-{r[0]}.x86_64"), pkg(f"bar-1.0-{r[1]}.x86_64"), pkg(f"bar-1.0-{r[1]}.noarch"),
                pkg(f"bar-1.0-{r[2]}.noarch")]
        kept, removed = ar.plan_prune(pkgs, 2)
        self.assertEqual(self.names(removed), [f"bar-1.0-{r[0]}.x86_64"])
        self.assertEqual(len(kept), 3)

    def test_few_builds_and_sources(self):
        pkgs = [pkg("arctic-linux-0.2.0-1.202609280310.gitabc1234.fc44.src"),
                pkg("arctic-linux-0.2.0-1.202609290310.gitabc1235.fc44.src"),
                pkg("mangowm-0.17.3-1.202609290310.gitabc1235.fc44.src")]
        kept, removed = ar.plan_prune(pkgs, 3)
        self.assertEqual((len(kept), removed), (3, []))
        kept, removed = ar.plan_prune(pkgs, 1)
        self.assertEqual(self.names(removed), ["arctic-linux-0.2.0-1.202609280310.gitabc1234.fc44.src"])

    def test_keep_must_be_positive(self):
        with self.assertRaises(ValueError):
            ar.plan_prune([pkg("a-1-1.noarch")], 0)

    def test_cmd_prune_deletes_files(self):
        with tempfile.TemporaryDirectory() as d:
            names = [f"arctic-fonts-0.2.0-1.2026092{i}0000.git000000{i}.fc44.noarch.rpm" for i in range(4)]
            for n in names + ["README"]:
                open(os.path.join(d, n), "w").close()
            orig = ar.read_package
            ar.read_package = ar.parse_filename  # dummy files have no rpm header
            try:
                self.assertEqual(ar.main(["prune", "--dir", d, "--keep", "3"]), 0)
            finally:
                ar.read_package = orig
            self.assertEqual(sorted(os.listdir(d)), sorted(names[1:] + ["README"]))

    def test_parse_filename(self):
        p = ar.parse_filename("/x/sddm-wayland-mango-0.2.0-1.202609280310.gitabc1234.fc44.noarch.rpm")
        self.assertEqual((p.name, p.version, p.release, p.arch),
                         ("sddm-wayland-mango", "0.2.0", "1.202609280310.gitabc1234.fc44", "noarch"))
        with self.assertRaises(ValueError):
            ar.parse_filename("notes.txt")


def make_site(root: str) -> dict:
    """A small two-channel site with its manifest."""
    files = {
        "RPM-GPG-KEY-arctic": b"-----BEGIN PGP PUBLIC KEY BLOCK-----\n...\n",
        "index.html": b"<!doctype html><title>x</title>",
        "repo/stable/fedora-44/x86_64/arctic-shell-0.2.0-1.2026.noarch.rpm": b"stable rpm" * 100,
        "repo/stable/fedora-44/x86_64/repodata/repomd.xml": b"<repomd/>",
        "repo/testing/fedora-44/x86_64/arctic-shell-0.2.0-1.2027.noarch.rpm": b"testing rpm" * 100,
        "repo/testing/fedora-44/source/arctic-linux-0.2.0-1.2027.src.rpm": b"srpm",
    }
    for rel, data in files.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
    return ar.write_manifest(root)


class Manifest(unittest.TestCase):
    def test_manifest_lists_every_file_but_itself(self):
        with tempfile.TemporaryDirectory() as d:
            doc = make_site(d)
            paths = [f["path"] for f in doc["files"]]
            self.assertNotIn("manifest.json", paths)
            self.assertIn("repo/testing/fedora-44/source/arctic-linux-0.2.0-1.2027.src.rpm", paths)
            f = next(f for f in doc["files"] if f["path"] == "index.html")
            self.assertEqual(f["sha256"], hashlib.sha256(b"<!doctype html><title>x</title>").hexdigest())
            self.assertEqual(ar.verify_tree(d, doc), [])
            with open(os.path.join(d, "index.html"), "a") as fh:
                fh.write("tampered")
            os.remove(os.path.join(d, "RPM-GPG-KEY-arctic"))
            self.assertEqual(sorted(ar.verify_tree(d, doc)), ["changed index.html", "missing RPM-GPG-KEY-arctic"])


class Server:
    """A local static web server (no proxy) for fetch tests."""

    def __init__(self, root: str):
        handler = functools.partial(_QuietHandler, directory=root)
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get(self, url, timeout=60):
        try:
            with self.opener.open(url, timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, b""

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def list_directory(self, path):  # like Pages: no directory listings
        self.send_error(404)
        return None


def pages_artifact(site: str) -> bytes:
    """What actions/upload-pages-artifact uploads: a zip holding artifact.tar of ./…"""
    tbuf = io.BytesIO()
    with tarfile.open(fileobj=tbuf, mode="w") as t:
        t.add(site, arcname=".")
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as z:
        z.writestr("artifact.tar", tbuf.getvalue())
    return zbuf.getvalue()


def fake_gh(artifact: bytes | None, runs: list | None = None, fail: dict | None = None):
    """A gh_api stand-in: two successful runs (9 the newest) whose github-pages artifact is
    `artifact` (None: expired). fail maps a path suffix to the exception that call raises."""
    runs = [{"id": 7, "run_started_at": "2026-09-27T10:00:00Z", "head_branch": "main"},
            {"id": 9, "run_started_at": "2026-09-28T10:00:00Z", "head_branch": "main"}] if runs is None else runs

    def gh(args, binary=False):
        path = next(a for a in args if a.startswith("repos/"))
        for suffix, exc in (fail or {}).items():
            if path.endswith(suffix):
                raise exc
        if path.endswith("/runs"):
            return {"workflow_runs": runs}
        if path.endswith("/runs/9/artifacts"):
            return {"artifacts": [{"id": 99, "name": "github-pages", "expired": artifact is None}]}
        if path.endswith("/artifacts/99/zip"):
            return artifact
        raise AssertionError(f"unexpected gh api {args}")
    return gh


class _Done:
    def __init__(self, returncode, stdout=b"", stderr=b""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class GhApi(unittest.TestCase):
    """gh_api retries what may be transient and tells 'not found' apart from failures."""

    def call(self, answers, **kw):
        calls, sleeps = [], []

        def run(cmd, **_):
            calls.append(cmd)
            return answers[min(len(calls), len(answers)) - 1]
        return ar.gh_api(["repos/o/r/x"], run=run, sleep=sleeps.append, **kw), calls, sleeps

    def test_retries_then_succeeds(self):
        got, calls, sleeps = self.call([_Done(1, stderr=b"HTTP 502: Bad Gateway"), _Done(1, stderr=b"timeout"),
                                        _Done(0, stdout=b'{"ok": 1}')])
        self.assertEqual(got, {"ok": 1})
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(sleeps), 2)

    def test_not_found_is_not_retried(self):
        with self.assertRaises(ar.GhNotFound):
            self.call([_Done(1, stderr=b"gh: Not Found (HTTP 404)")])

    def test_gives_up_with_a_fetch_error(self):
        with self.assertRaises(ar.FetchError) as cm:
            self.call([_Done(1, stderr=b"HTTP 500: Internal Server Error")], attempts=3)
        self.assertNotIsInstance(cm.exception, ar.GhNotFound)
        self.assertIn("failed 3 times", str(cm.exception))

    def test_binary_and_bad_json(self):
        got, _, _ = self.call([_Done(0, stdout=b"PK\x03\x04zip")], binary=True)
        self.assertEqual(got, b"PK\x03\x04zip")
        with self.assertRaises(ar.FetchError):
            self.call([_Done(0, stdout=b"<html>")], attempts=2)


class Fetch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.live = os.path.join(self.tmp.name, "live")
        self.dest = os.path.join(self.tmp.name, "dest")
        os.makedirs(self.live)
        os.makedirs(self.dest)
        self.srv = Server(self.live)

    def tearDown(self):
        self.srv.close()
        self.tmp.cleanup()

    def fetch(self, gh=None, **kw):
        return ar.fetch_previous(self.dest, self.srv.url + "/", "o/r" if gh else None, "repo.yml" if gh else None,
                                 get=self.srv.get, gh=gh or ar.gh_api, **kw)

    def test_nothing_published_is_a_first_publish(self):
        self.assertEqual(self.fetch(), "fresh")
        self.assertEqual(os.listdir(self.dest), [])

    def test_downloads_the_live_site(self):
        doc = make_site(self.live)
        self.assertEqual(self.fetch(), "live")
        self.assertEqual(ar.verify_tree(self.dest, doc), [])

    def test_incomplete_live_site_fails(self):
        make_site(self.live)
        os.remove(os.path.join(self.live, "repo/testing/fedora-44/source/arctic-linux-0.2.0-1.2027.src.rpm"))
        with self.assertRaises(ar.FetchError):
            self.fetch()

    def test_corrupt_live_file_fails(self):
        make_site(self.live)
        with open(os.path.join(self.live, "index.html"), "ab") as f:
            f.write(b"!")
        with self.assertRaises(ar.FetchError):
            self.fetch()

    def test_unsafe_manifest_path_fails(self):
        doc = make_site(self.live)
        doc["files"].append({"path": "../escape", "size": 1, "sha256": "0" * 64})
        with open(os.path.join(self.live, "manifest.json"), "w") as f:
            json.dump(doc, f)
        with self.assertRaises(ar.FetchError):
            self.fetch()
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "escape")))

    def test_foreign_site_fails_unless_starting_fresh(self):
        with open(os.path.join(self.live, "index.html"), "w") as f:
            f.write("someone else's page")
        with self.assertRaises(ar.FetchError):
            self.fetch()
        self.assertEqual(self.fetch(start_fresh=True), "fresh")

    def test_artifact_used_when_it_is_what_is_live(self):
        make_site(self.live)
        blob = pages_artifact(self.live)
        with open(os.path.join(self.live, "manifest.json")) as f:
            doc = json.load(f)
        self.assertEqual(self.fetch(gh=fake_gh(blob)), "artifact")
        self.assertEqual(ar.verify_tree(self.dest, doc), [])

    def test_stale_artifact_falls_back_to_the_live_site(self):
        make_site(self.live)
        blob = pages_artifact(self.live)
        with open(os.path.join(self.live, "index.html"), "w") as f:
            f.write("newer")
        doc = ar.write_manifest(self.live)
        self.assertEqual(self.fetch(gh=fake_gh(blob)), "live")
        with open(os.path.join(self.dest, "index.html")) as f:
            self.assertEqual(f.read(), "newer")
        self.assertEqual(ar.verify_tree(self.dest, doc), [])

    def test_newer_artifact_wins_over_a_lagging_live_site(self):
        make_site(self.live)
        newer = os.path.join(self.tmp.name, "newer")
        make_site(newer)
        with open(os.path.join(newer, "index.html"), "w") as f:
            f.write("deployed last")
        doc = ar.write_manifest(newer)
        doc["generated"] = "2999-01-01T00:00:00Z"
        with open(os.path.join(newer, "manifest.json"), "w") as f:
            json.dump(doc, f)
        self.assertEqual(self.fetch(gh=fake_gh(pages_artifact(newer))), "artifact")
        with open(os.path.join(self.dest, "index.html")) as f:
            self.assertEqual(f.read(), "deployed last")

    def test_expired_artifact_falls_back_to_the_live_site(self):
        make_site(self.live)
        self.assertEqual(self.fetch(gh=fake_gh(None)), "live")

    def test_artifact_gone_while_downloading_falls_back_to_the_live_site(self):
        make_site(self.live)
        gone = ar.GhNotFound("gh api repos/o/r/actions/artifacts/99/zip: HTTP 410")
        self.assertEqual(self.fetch(gh=fake_gh(b"x", fail={"/artifacts/99/zip": gone})), "live")

    def test_broken_artifact_falls_back_to_the_live_site(self):
        make_site(self.live)
        self.assertEqual(self.fetch(gh=fake_gh(b"not a zip")), "live")

    def test_api_errors_fail_even_with_a_live_site(self):
        # The live site may be a stale CDN copy: without the API's answer, don't guess.
        make_site(self.live)
        for suffix in ("/runs", "/runs/9/artifacts", "/artifacts/99/zip"):
            with self.subTest(suffix):
                err = ar.FetchError(f"gh api {suffix}: failed 4 times: HTTP 502")
                with self.assertRaises(ar.FetchError):
                    self.fetch(gh=fake_gh(pages_artifact(self.live), fail={suffix: err}))
                self.assertEqual(os.listdir(self.dest), [])

    def test_first_publish_when_the_workflow_never_succeeded(self):
        self.assertEqual(self.fetch(gh=fake_gh(None, runs=[])), "fresh")

    def test_nothing_live_after_earlier_publishes_fails(self):
        # Pages briefly answering 404 must not look like a first publish.
        with self.assertRaises(ar.FetchError):
            self.fetch(gh=fake_gh(None))
        with self.assertRaises(ar.FetchError):
            self.fetch(gh=fake_gh(b"not a zip"))
        self.assertEqual(self.fetch(gh=fake_gh(None), start_fresh=True), "fresh")

    def test_artifact_restores_an_empty_site(self):
        src = os.path.join(self.tmp.name, "old")
        doc = make_site(src)
        self.assertEqual(self.fetch(gh=fake_gh(pages_artifact(src))), "artifact")
        self.assertEqual(ar.verify_tree(self.dest, doc), [])

    def test_unsafe_artifact_is_rejected(self):
        tbuf = io.BytesIO()
        with tarfile.open(fileobj=tbuf, mode="w") as t:
            info = tarfile.TarInfo("../evil")
            info.size = 1
            t.addfile(info, io.BytesIO(b"x"))
        with self.assertRaises(ar.FetchError):
            ar.extract_pages_artifact(tbuf.getvalue(), self.dest)
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "evil")))

    def test_cmd_fetch_needs_an_empty_dest(self):
        open(os.path.join(self.dest, "x"), "w").close()
        self.assertEqual(ar.main(["fetch", "--dest", self.dest, "--base-url", self.srv.url]), 2)


class Index(unittest.TestCase):
    def test_index_and_channel_info(self):
        with tempfile.TemporaryDirectory() as d:
            make_site(d)
            bi = os.path.join(d, "BUILD-INFO")
            with open(bi, "w") as f:
                f.write("version=0.2.0\ngit_commit=abcdef1234567890\nrpm=arctic-shell-0.2.0-1.2027.noarch\n")
            env = dict(os.environ)
            os.environ.update(GITHUB_RUN_ID="5", GITHUB_REPOSITORY="o/r", ARCTIC_SOURCE_REF="claude/busy-goodall-j42hmi")
            try:
                ar.main(["channel-info", "--site", d, "--channel", "testing", "--releasever", "44", "--build-info", bi])
            finally:
                os.environ.clear()
                os.environ.update(env)
            with open(os.path.join(d, "repo/testing/fedora-44/PUBLISH-INFO.json")) as f:
                info = json.load(f)
            self.assertEqual((info["git_commit"], info["ref"], info["packages"]),
                             ("abcdef1234567890", "claude/busy-goodall-j42hmi", ["arctic-shell-0.2.0-1.2027.noarch"]))
            self.assertTrue(info["run"].endswith("/o/r/actions/runs/5"))
            orig = ar.read_package
            ar.read_package = ar.parse_filename
            try:
                page = ar.render_index(d, "https://example.org/O-Tism/", "ABCD1234ABCD1234")
            finally:
                ar.read_package = orig
            self.assertIn("Stable", page)
            self.assertIn("Testing", page)
            self.assertIn("https://example.org/O-Tism/repo/testing/fedora-44/x86_64/", page)
            self.assertIn("abcdef123456", page)
            self.assertIn("ABCD 1234 ABCD 1234", page)


if __name__ == "__main__":
    unittest.main()
