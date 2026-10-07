#!/usr/bin/env python3
"""Host CLI for one reviewed artifact-only codec audit. Defaults remain blocked."""
from pathlib import Path
import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import time
import urllib.request
from core import (Deadline, require, private_dir, validate_inputs, validate_binding,
    sha_file, write_json, check_artifact, ISO_BYTES, ISO_SHA, CANDIDATE, RUN, ARTIFACT,
    PhaseFailure, failure_detail, reap_owned, close_observed)

HERE = Path(__file__).resolve().parent
STAGES = ("archive", "extract", "metadata", "solve", "payloads", "compress")
PHASE_LIMITS = (300, 900, 900, 900, 600, 600)


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True, timeout=10).strip()


def source_guard(expected_sha, deployed=True):
    pins = json.loads((HERE / "execution-pins.json").read_text())
    root = HERE.parents[1]
    require(git(root, "rev-parse", "HEAD") == expected_sha, "execution source head differs")
    require(not git(root, "status", "--porcelain", "--untracked-files=no"), "dirty execution source")
    for logical, row in pins["files"].items():
        path = root / logical
        require(path.is_file() and not path.is_symlink() and sha_file(path) == row["sha256"],
            "changed execution source:" + logical)
        index = git(root, "ls-files", "--stage", "--", logical).split()
        require(len(index) >= 4 and index[0] == row["git_mode"], "canonical Git mode differs")
        require(not path.stat().st_mode & 0o022, "group/other-writable source")
    return pins


def official_metadata(path, token, limit=100000):
    require(token, "authorized read-only workflow token missing")
    request = urllib.request.Request("https://api.github.com/repos/yuvalkolodkingal/Arctic-Linux/" + path,
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
            "User-Agent": "Arctic-codec-artifact-audit"})
    from worker import NoRedirect
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=30) as response:
        data = response.read(limit + 1)
    require(len(data) <= limit, "official metadata bound")
    return json.loads(data)


def preflight(root, source_sha):
    # No network or image access occurs until all exact source/binding gates pass.
    started = time.monotonic()
    parent = Path(os.environ["RUNNER_TEMP"]).resolve()
    root = private_dir(root, parent, fresh=True)
    (root / "evidence").mkdir(mode=0o700)
    (root / "inputs").mkdir(mode=0o700)
    (root / "image").mkdir(mode=0o700)
    work = root / "work"
    work.mkdir(mode=0o700)
    (work / "home").mkdir(mode=0o700)
    (work / "home-config").mkdir(mode=0o700)
    passed, failure = False, None
    try:
        source_guard(source_sha)
        spec = json.loads((HERE / "workflow-inputs.json").read_text())
        validate_inputs(json.loads(os.environ["CODEC_ALL_INPUTS"]), spec, source_sha,
            os.environ.get("GITHUB_EVENT_NAME"))
        require(os.environ.get("GITHUB_SHA") == source_sha, "workflow source head differs")
        binding = json.loads((HERE / "runtime-binding.json").read_text())
        validate_binding(binding)
        review = HERE / "independent-worker-review.json"
        require(review.is_file() and not review.is_symlink() and
            sha_file(review) == binding["execution_review_sha256"], "source review bytes unbound")
        tools = binding.get("tools_artifact")
        require(type(tools) is dict and tools.get("review_sha256") and tools.get("image_manifest_sha256"),
            "reviewed tools artifact binding BLOCKED")
        require(shutil.disk_usage(root).free >= 32000000000, "CI initial free disk below32GB")
        token = os.environ.get("GH_TOKEN", "")
        original = official_metadata("actions/artifacts/" + str(ARTIFACT), token)
        check_artifact(original)
        tool_metadata = official_metadata("actions/artifacts/" + str(tools["artifact_id"]), token)
        require(tool_metadata["id"] == tools["artifact_id"] and not tool_metadata["expired"] and
            tool_metadata["workflow_run"]["id"] == tools["run_id"] and
            tool_metadata["workflow_run"]["head_sha"] == tools["source_sha"], "wrong tools artifact provenance")
        context = {"started_monotonic": started, "source_sha": source_sha,
            "run": int(os.environ["GITHUB_RUN_ID"]), "attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
            "owner_uid": os.getuid(), "owner_gid": os.getgid(),
            "initial_free_disk_bytes": shutil.disk_usage(root).free,
            "binding_sha256": sha_file(HERE / "runtime-binding.json"),
            "host_boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip()}
        write_json(work / "context.json", context)
        write_json(root / "evidence/official-ISO-artifact.json", original)
        write_json(root / "evidence/official-tools-artifact.json", tool_metadata)
        env = os.environ.get("GITHUB_ENV")
        if env:
            with Path(env).open("a") as stream:
                stream.write("CODEC_ROOT=" + str(root) + "\n")
                stream.write("CODEC_TOOLS_RUN=" + str(tools["run_id"]) + "\n")
                stream.write("CODEC_TOOLS_ARTIFACT=" + str(tools["artifact_id"]) + "\n")
        passed = True
    except Exception as error:
        failure = type(error).__name__ + ": " + str(error)
        raise
    finally:
        write_json(root / "evidence/preflight.json", {"passed": passed, "failure": failure,
            "source_sha": source_sha, "actual_solver_payload_ISO_work": "UNRUN"})


def bounded_host(argv, deadline, timeout, log, cleanup=None):
    # Keep reap and production callback inside this phase/global bound.
    budget = deadline.remaining(timeout)
    end = time.monotonic() + budget
    reserve = min(15., budget / 2.)
    work_end = end - reserve
    primary, secondary, stream, process = None, [], None, None
    try:
        stream = log.open("xb")
        process = subprocess.Popen(argv, stdout=stream, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, start_new_session=True)
        while process.poll() is None:
            require(time.monotonic() < work_end, "bounded host phase timeout")
            require(log.stat().st_size <= 1000000, "bounded host log")
            time.sleep(min(.05, max(.001, work_end - time.monotonic())))
        require(time.monotonic() <= work_end, "post-exit host phase timeout")
        require(log.stat().st_size <= 1000000, "post-exit bounded host log")
        require(process.returncode == 0, "host phase failed")
    except BaseException as error:
        primary = error
        reap_owned(process, end, secondary)
        if cleanup:
            try:
                cleanup()
            except Exception as error:
                secondary.append(failure_detail(error))
    finally:
        close_observed(stream, secondary)
    record = {"argv": argv, "phase_end_monotonic": end,
        "exit_status": process.returncode if process is not None else None,
        "primary_failure": failure_detail(primary) if primary else None,
        "cleanup_or_close_failures": secondary}
    try:
        write_json(log.with_name(log.name + ".phase.json"), record)
    except Exception as error:
        secondary.append(failure_detail(error))
    if primary is not None or secondary:
        raise PhaseFailure(primary, secondary) from primary


def run(root, source_sha):
    parent = Path(os.environ["RUNNER_TEMP"]).resolve()
    root = private_dir(root, parent)
    work = private_dir(root / "work", root)
    context = json.loads((work / "context.json").read_text())
    require(context["source_sha"] == source_sha and context["owner_uid"] == os.getuid() and
        context["owner_gid"] == os.getgid(), "same-run context/source/owner differs")
    require(context["run"] == int(os.environ["GITHUB_RUN_ID"]) and
        context["attempt"] == int(os.environ["GITHUB_RUN_ATTEMPT"]), "stale run context")
    require(context["host_boot_id"] == Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "host boot changed")
    source_guard(source_sha)
    binding = json.loads((HERE / "runtime-binding.json").read_text())
    validate_binding(binding)
    require(context["binding_sha256"] == sha_file(HERE / "runtime-binding.json"), "binding changed")
    deadline = Deadline(context["started_monotonic"], 3600)
    # Reserve180s for bounded evidence/cleanup plus GitHub's upload transport.
    require(deadline.remaining(3600) > 180, "evidence/upload reserve exhausted")
    deadline.end -= 180
    tools = binding["tools_artifact"]
    archive = root / "tools/tool-image.tar"
    passed, failure, primary = False, None, None
    try:
        require(archive.is_file() and not archive.is_symlink() and archive.stat().st_size == tools["archive_bytes"]
            and sha_file(archive) == tools["archive_sha256"], "tools image archive differs")
        bounded_host(["docker", "load", "--input", str(archive)], deadline, 180,
            root / "evidence/tools-image-load.log")
        image_id = subprocess.check_output(["docker", "image", "inspect", binding["worker_image"],
            "--format", "{{.Id}}"], text=True, timeout=deadline.remaining(15)).strip()
        require(image_id == binding["worker_image"], "immutable tools image identity differs")
        manifest = root / "tools/tool-image-manifest.json"
        require(manifest.is_file() and not manifest.is_symlink() and
            sha_file(manifest) == tools["image_manifest_sha256"], "tools manifest differs")
        obj = json.loads(manifest.read_text())
        require(obj["image_id"] == image_id and obj["tool_packages"] == binding["tool_packages"] and
            obj["tool_file_hashes"] == binding["tool_file_hashes"] and
            obj["status"] == "SIGNED_INPUTS_AND_API_CONTROLS_PASS", "actual tools manifest differs")
        image = root / "inputs/iso/Arctic-Linux-1.2-candidate-37507582946-1-x86_64.iso"
        require(image.is_file() and not image.is_symlink() and image.stat().st_size == ISO_BYTES
            and sha_file(image) == ISO_SHA, "actual exact ISO bytes differ")
        for stage, limit in zip(STAGES, PHASE_LIMITS):
            source_guard(source_sha)
            name = "arctic-codec-" + str(context["run"]) + "-" + str(context["attempt"]) + "-" + stage
            argv = ["docker", "run", "--rm", "--pull=never", "--name", name,
                "--label", "arctic.codec.source=" + source_sha,
                "--label", "arctic.codec.context=" + sha_file(work / "context.json"),
                "--user", str(os.getuid()) + ":" + str(os.getgid()), "--read-only", "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true", "--pids-limit=512", "--memory=8g", "--cpus=4",
                "--network", "bridge" if stage in ("metadata", "payloads") else "none",
                "--env", "HOME=/work/home", "--env", "XDG_CONFIG_HOME=/work/home-config",
                "--env", "LANG=C.UTF-8", "--env", "PATH=/usr/bin:/usr/sbin",
                "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=256m",
                "-v", str(HERE) + ":/source:ro", "-v", str(work) + ":/work:rw",
                "-v", str(root / "inputs") + ":/input:ro"]
            if stage == "extract":
                argv += ["-v", str(root / "image") + ":/extracted:rw"]
            elif stage != "archive":
                require((root / "image/root").is_dir() and not (root / "image/root").is_symlink(), "actual root missing/linked")
                argv += ["-v", str(root / "image/root") + ":/image:ro"]
            argv += ["--entrypoint", "/usr/bin/python3", image_id,
                "-E", "-s", "-B", "/source/worker.py", stage]
            write_json(root / ("evidence/" + stage + "-actual-argv.json"), argv)

            cleanup_end = time.monotonic() + deadline.remaining(limit)

            def cleanup_owned():
                remaining = lambda: max(0., min(5., cleanup_end - time.monotonic()))
                require(remaining() > 0, "owned-container cleanup deadline exhausted")
                inspect = subprocess.run(["docker", "container", "inspect", name], capture_output=True,
                    text=True, timeout=remaining())
                if inspect.returncode:
                    return
                obj = json.loads(inspect.stdout)[0]
                labels = obj["Config"]["Labels"]
                require(labels.get("arctic.codec.source") == source_sha and
                    labels.get("arctic.codec.context") == sha_file(work / "context.json"), "cleanup owner differs")
                subprocess.run(["docker", "container", "rm", "--force", obj["Id"]],
                    check=True, stdout=subprocess.DEVNULL, timeout=remaining())

            bounded_host(argv, deadline, limit, root / ("evidence/" + stage + "-host.log"), cleanup_owned)
            record = json.loads((work / (stage + "-observed.json")).read_text())
            require(record["passed"] and record["context_sha256"] == sha_file(work / "context.json") and
                record["binding_sha256"] == context["binding_sha256"], "actual phase absent/failed/stale")
        passed = True
    except Exception as error:
        primary = error
        failure = failure_detail(error)
        raise
    finally:
        # No blanket deletion or cleanup of a container/image/system outside this run.
        try:
            collection_errors = collect(root, context, passed, failure)
        except Exception as error:
            raise PhaseFailure(primary, [failure_detail(error)]) from primary
        if collection_errors and primary is None:
            raise PhaseFailure(None, collection_errors)


def collect(root, context, passed, failure):
    evidence, work = root / "evidence", root / "work"
    errors = []
    try:
        deadline = Deadline(context["started_monotonic"], 3600)
        total = sum(p.stat().st_size for p in evidence.iterdir() if p.is_file())
        for path in work.iterdir():
            deadline.remaining(1)
            if (path.suffix not in (".json", ".stderr") and not
                (path.name.startswith("signature-") and path.suffix == ".stdout")) or not path.is_file() or path.is_symlink():
                continue
            require(path.stat().st_size <= 5000000, "individual evidence bound:" + path.name)
            total += path.stat().st_size
            require(total <= 19000000, "total evidence reserve/bound")
            shutil.copyfile(path, evidence / ("worker-" + path.name))
    except Exception as error:
        errors.append(failure_detail(error))
    write_json(evidence / "final-observed-status.json", {"source": context["source_sha"],
        "run": context["run"], "attempt": context["attempt"], "passed": passed and not errors,
        "primary_failure": failure, "collection_failures": errors,
        "valid_ISO": False, "runtime_playback": "UNRUN", "compressed_whole_ISO_delta": "UNRUN"})
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "run"))
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    (preflight if args.mode == "preflight" else run)(args.root, args.source_sha)


if __name__ == "__main__":
    main()
