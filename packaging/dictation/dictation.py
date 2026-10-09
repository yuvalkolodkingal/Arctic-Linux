#!/usr/bin/python3
"""Arctic's local-only Voxtype setup and private session controller.

The shipped file contains no model or speech engine. Downloads are pinned, root
owned and verified before they become executable. Audio is held by Voxtype; the
only transcript file lives in the user's private runtime directory and is erased
after insertion or cancellation. No raw upstream output enters logs or notices.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import select
import signal
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

VERSION = "1.1.0"
SOURCE_COMMIT = "e2638ca63f566f1682bcedc0abea8e4b25211c21"
MODEL_COMMIT = "80da2d8bfee42b0e836fc3a9890373e5defc00a6"
TURBO_COMMIT = "98aa99a0a9db05ae2342309f5096248665f7cba3"
RELEASE = "https://github.com/peteonrails/voxtype/releases/download/v1.1.0/"
ASSETS = {
    "cpu": ("voxtype-cpu", RELEASE + "voxtype-1.1.0-linux-x86_64-baseline", 18579224,
            "1c9d78b4f6805e4f12ba3670949d3c22788269bdbc54215afffa42cafd0b4a7a"),
    "avx2": ("voxtype-cpu-avx2", RELEASE + "voxtype-1.1.0-linux-x86_64-avx2", 19153728,
             "e7d5de68cc8fc610c3c961c47f879451db9bee4a2df152e9a66f1078072e7f28"),
    "vulkan": ("voxtype-vulkan", RELEASE + "voxtype-1.1.0-linux-x86_64-vulkan", 66342968,
               "db2c7938392ff08ec8b50b8afb90f8bd3d0111eccf5943df2f51c40a0368fec2"),
    "small": ("ggml-small.bin", "https://huggingface.co/ggerganov/whisper.cpp/resolve/" + MODEL_COMMIT + "/ggml-small.bin",
              487601967, "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b"),
    "turbo": ("ggml-large-v3-turbo-q5_0.bin", "https://huggingface.co/ggerganov/whisper.cpp/resolve/" + TURBO_COMMIT + "/ggml-large-v3-turbo-q5_0.bin",
              574041195, "394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2"),
}
PAYLOAD = Path("/opt/arctic/voxtype") / VERSION
SYSTEM = Path("/var/lib/arctic/dictation")
SCRIPT = Path("/usr/share/arctic/dictation/dictation.py")
AUDIO_DEPENDENCIES = ("pipewire-alsa", "wtype", "wl-clipboard")
AUDIO_LIBRARIES = (Path("/usr/lib64/alsa-lib/libasound_module_pcm_pipewire.so"),
                     Path("/etc/alsa/conf.d/50-pipewire.conf"),
                     Path("/etc/alsa/conf.d/99-pipewire-default.conf"))
PROFILES = {
    "small-v2": {"id": "small-v2", "model": "small", "cpu_variant": "baseline",
                 "assets": {"cpu": ASSETS["cpu"], "model": ASSETS["small"]},
                 "dependencies": AUDIO_DEPENDENCIES, "libraries": AUDIO_LIBRARIES},
    "turbo-q5-v3": {"id": "turbo-q5-v3", "model": "large-v3-turbo-q5_0", "cpu_variant": "avx2",
                    "assets": {"cpu": ASSETS["cpu"], "avx2": ASSETS["avx2"], "vulkan": ASSETS["vulkan"], "model": ASSETS["turbo"]},
                    "dependencies": (*AUDIO_DEPENDENCIES, "vulkan-loader", "mesa-vulkan-drivers"),
                    "libraries": (*AUDIO_LIBRARIES, Path("/usr/lib64/libvulkan.so.1"))},
}


def v3_supported(cpuinfo=None):
    try:
        text = Path("/proc/cpuinfo").read_text() if cpuinfo is None else cpuinfo
        flags = [set(line.split(":", 1)[1].lower().split()) for line in text.splitlines()
                 if line.partition(":")[0].strip() == "flags" and ":" in line]
        processors = sum(line.partition(":")[0].strip() == "processor" for line in text.splitlines())
        if processors and len(flags) != processors:
            return False
        common = set.intersection(*flags) if flags else set()
        return {"avx", "avx2", "fma", "f16c", "bmi1", "bmi2", "movbe", "popcnt", "xsave"} <= common and bool(common & {"abm", "lzcnt"})
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def recommended_profile(cpuinfo=None):
    return PROFILES["turbo-q5-v3" if v3_supported(cpuinfo) else "small-v2"]


def profile_selection(system=None):
    system = SYSTEM if system is None else system
    path = system / "profile-selection.json"
    value = read_json(path) if trusted_file(path) else {}
    return "compatibility" if isinstance(value, dict) and value.get("selection") == "compatibility" else "recommended"


def desired_profile(cpuinfo=None, system=None):
    return PROFILES["small-v2"] if profile_selection(system) == "compatibility" else recommended_profile(cpuinfo)


def profile_status(profile):
    return {"profile": profile["id"], "model": profile["model"], "cpu_variant": profile["cpu_variant"],
            "model_download_bytes": profile["assets"]["model"][2],
            "download_bytes": sum(asset[2] for asset in profile["assets"].values())}


def profile_digest(profile):
    descriptor = {**profile_status(profile), "assets": profile["assets"], "dependencies": profile["dependencies"]}
    return hashlib.sha256(json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Failure(Exception):
    pass


def read_json(path, default=None):
    try:
        with path.open() as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return {} if default is None else default


def directory(path, owner, mode=0o700):
    """Reject symlinks and shared writable directories before creating files."""
    path.mkdir(parents=True, exist_ok=True, mode=mode)
    st = path.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != owner or st.st_mode & 0o022:
        raise Failure("Dictation's private directory has unsafe permissions.")
    os.chmod(path, mode)


def atomic_json(path, value, mode=0o600):
    fd, name = tempfile.mkstemp(prefix="." + path.name + "-", dir=path.parent)
    temporary = Path(name)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def trusted_file(path, size=None):
    try:
        st = path.lstat()
        return (stat.S_ISREG(st.st_mode) and st.st_uid == 0 and not st.st_mode & 0o022
                and (size is None or st.st_size == size))
    except OSError:
        return False


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def dependencies_ready(libraries=None, commands=None, profile=None):
    # Fedora library sonames may be symlinks; inspect their resolved, root-owned
    # targets, never a user PATH substitute. No subprocess or full model rehash
    # belongs in a frequently refreshed readiness check.
    commands = [Path("/usr/bin/wtype"), Path("/usr/bin/wl-copy")] if commands is None else commands
    profile = desired_profile() if profile is None else profile
    paths = [*commands, *(profile["libraries"] if libraries is None else libraries)]
    for path in paths:
        try:
            target = path.resolve(strict=True)
        except OSError:
            return False
        if not trusted_file(target):
            return False
        if path in commands and not target.stat().st_mode & 0o111:
            return False
    return True


def ready(payload=PAYLOAD, system=SYSTEM, profile=None):
    """A root-owned receipt attests hashes; cheap stat checks detect replacement.

    Never repeatedly hash 488 MB from settings polling. Users cannot modify the
    receipt or the payload, and setup always checks the complete SHA before it
    writes this receipt. Missing dependencies still keep readiness false.
    """
    profile = desired_profile(system=system) if profile is None else profile
    receipt = system / "verified.json"
    if not trusted_file(receipt):
        return False
    data = read_json(receipt)
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        return False
    if (data.get("version") != VERSION or data.get("profile") != profile["id"] or
            data.get("profile_sha256") != profile_digest(profile) or
            data.get("model") != profile["model"] or set(data.get("files", {})) != set(profile["assets"])):
        return False
    for key, (name, _url, size, digest) in profile["assets"].items():
        path = payload / name
        if not trusted_file(path, size):
            return False
        recorded = data.get("files", {}).get(key, {})
        st = path.stat()
        if recorded != {"sha256": digest, "size": size, "mtime_ns": st.st_mtime_ns}:
            return False
        if key != "model" and not st.st_mode & 0o111:
            return False
    return dependencies_ready(profile=profile)


def download(asset, destination, deadline, progress, opener=urllib.request.urlopen):
    """Resume private partials, enforce exact length+SHA, then publish atomically."""
    _name, url, size, digest = asset
    if trusted_file(destination, size) and sha256(destination) == digest:
        progress(size)
        return
    part = destination.with_name(destination.name + ".part")
    if part.exists() and not trusted_file(part):
        raise Failure("A cached dictation download has unsafe permissions. Remove it as administrator and retry.")
    offset = part.stat().st_size if part.exists() else 0
    if offset == size:
        if sha256(part) == digest:
            os.chmod(part, 0o644 if destination.name.endswith(".bin") else 0o755)
            os.replace(part, destination)
            progress(size)
            return
        part.unlink()
        offset = 0
    if offset > size:
        part.unlink()
        offset = 0
    request = urllib.request.Request(url, headers={"User-Agent": "Arctic-Dictation/1", "Accept-Encoding": "identity"})
    if offset:
        request.add_header("Range", f"bytes={offset}-")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise Failure("Dictation setup timed out. Connect to the internet and retry.")
    with opener(request, timeout=min(20, remaining)) as response:
        if not response.geturl().startswith("https://"):
            raise Failure("Dictation download redirected to an insecure address.")
        if offset and response.status == 206:
            wanted = f"bytes {offset}-"
            if not response.headers.get("Content-Range", "").startswith(wanted):
                raise Failure("Dictation server returned an invalid partial download. Retry setup.")
        else:
            offset = 0
        fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | (os.O_APPEND if offset else os.O_TRUNC), 0o600)
        with os.fdopen(fd, "ab" if offset else "wb") as stream:
            count = offset
            progress(count)
            while chunk := response.read(256 * 1024):
                if time.monotonic() >= deadline:
                    raise Failure("Dictation setup timed out. Its partial download is saved; retry when online.")
                count += len(chunk)
                if count > size:
                    raise Failure("Dictation download exceeded its disclosed size. Retry setup.")
                stream.write(chunk)
                progress(count)
            stream.flush()
            os.fsync(stream.fileno())
    if part.stat().st_size != size:
        raise Failure("Dictation download is incomplete. Retry setup when the connection is stable.")
    if sha256(part) != digest:
        part.unlink()
        raise Failure("Dictation download failed its integrity check. Retry setup; it was not installed.")
    os.chmod(part, 0o644 if destination.name.endswith(".bin") else 0o755)
    os.replace(part, destination)


def queue(system=SYSTEM, error="", profile=None):
    profile = desired_profile() if profile is None else profile
    directory(system, 0, 0o755)
    atomic_json(system / "setup.json", {"state": "queued", "progress": 0, "error": error,
                "version": VERSION, **profile_status(profile)}, 0o644)
    atomic_json(system / "pending.json", {"version": VERSION, "profile": profile["id"],
                "profile_sha256": profile_digest(profile)}, 0o644)


def request_setup(system=SYSTEM, selection=None):
    """An authenticated retry neither overwrites a running download nor loses reboot recovery."""
    directory(system, 0, 0o755)
    fd = os.open(system / "setup.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if selection is not None:
                raise Failure("Dictation setup is already running. Wait for it to finish before changing profile.")
        else:
            if selection is not None:
                if selection not in ("compatibility", "recommended"):
                    raise Failure("Choose a supported dictation profile.")
                atomic_json(system / "profile-selection.json", {"selection": selection}, 0o644)
            queue(system, profile=desired_profile(system=system))
    finally:
        os.close(fd)
    subprocess.run(["/usr/bin/systemctl", "enable", "--now", "arctic-dictation-setup.timer"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=True)
    subprocess.run(["/usr/bin/systemctl", "start", "--no-block", "arctic-dictation-setup.service"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=True)


def system_setup(offline=False, payload=PAYLOAD, system=SYSTEM, seconds=600):
    if os.geteuid() != 0:
        raise Failure("Dictation setup needs administrator authorization.")
    directory(system, 0, 0o755)
    directory(payload.parent.parent, 0, 0o755)
    directory(payload.parent, 0, 0o755)
    directory(payload, 0, 0o755)
    lock = os.open(system / "setup.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        profile = desired_profile(system=system)
        queue(system, profile=profile)
        if offline:
            return False
        deadline = time.monotonic() + seconds
        try:
            if platform.machine() != "x86_64":
                raise Failure("This Arctic dictation payload requires x86_64 hardware.")
            atomic_json(system / "setup.json", {"state": "downloading", "progress": 0,
                        "error": "", "version": VERSION, **profile_status(profile)}, 0o644)
            result = subprocess.run(["/usr/bin/dnf", "-y", "--setopt=timeout=15", "--setopt=retries=1",
                                     "--setopt=install_weak_deps=False", "install", *profile["dependencies"]],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    timeout=min(120, max(1, deadline - time.monotonic())))
            if result.returncode:
                raise Failure("Dictation dependencies could not be installed. Connect to the internet and retry setup.")
            done = 0
            last_update = [0.0]
            total = profile_status(profile)["download_bytes"]
            previous = read_json(system / "verified.json") if trusted_file(system / "verified.json") else {}
            for key, asset in profile["assets"].items():
                def report(count):
                    now = time.monotonic()
                    if now - last_update[0] >= 0.5 or count == asset[2]:
                        atomic_json(system / "setup.json", {"state": "downloading", "progress": (done + count) / total,
                                    "error": "", "version": VERSION, **profile_status(profile)}, 0o644)
                        last_update[0] = now
                download(asset, payload / asset[0], deadline, report)
                done += asset[2]
            receipt = {"version": VERSION, "source_commit": SOURCE_COMMIT, "profile_sha256": profile_digest(profile),
                       **profile_status(profile), "files": {}}
            for key, asset in profile["assets"].items():
                receipt["files"][key] = {"sha256": asset[3], "size": asset[2], "mtime_ns": (payload / asset[0]).stat().st_mtime_ns}
            subprocess.run(["/usr/sbin/restorecon", "-RF", str(payload), str(system)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=False)
            if not dependencies_ready(profile=profile):
                raise Failure("Dictation audio or text-insertion dependencies are missing. Retry setup.")
            atomic_json(system / "verified.json", receipt, 0o644)
            atomic_json(system / "setup.json", {"state": "ready", "progress": 1, "error": "", "version": VERSION,
                        **profile_status(profile)}, 0o644)
            (system / "pending.json").unlink(missing_ok=True)
            cleanup_replaced_model(previous, profile, payload)
            return True
        except (Failure, OSError, urllib.error.URLError, subprocess.TimeoutExpired) as error:
            # Never put URL exceptions, command output, secrets or user speech in a public status file.
            message = str(error) if isinstance(error, Failure) else "Dictation setup could not finish. Connect to the internet and retry setup."
            queue(system, message, profile)
            return False
    finally:
        os.close(lock)


def cleanup_replaced_model(previous, profile, payload):
    # Only a known, formerly verified model can be removed, and only after the
    # replacement receipt is published. Downloads never fetch both models.
    files = previous.get("files", {}) if isinstance(previous, dict) else {}
    recorded = files.get("model", {}) if isinstance(files, dict) else {}
    for key in ("small", "turbo"):
        name, _url, size, digest = ASSETS[key]
        path = payload / name
        if name == profile["assets"]["model"][0] or not trusted_file(path, size):
            continue
        if recorded == {"sha256": digest, "size": size, "mtime_ns": path.stat().st_mtime_ns}:
            try:
                path.unlink()
            except OSError:
                pass  # An optional old-model cleanup cannot undo successful setup.


def runtime_paths():
    base = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    directory(base, os.getuid())
    shared = base / "arctic"
    directory(shared, os.getuid())
    private = shared / "dictation"
    directory(private, os.getuid())
    return shared, private


def preferences():
    path = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "arctic" / "dictation.json"
    value = read_json(path)
    if not isinstance(value, dict):
        value = {}
    return {"language": value.get("language") if value.get("language") in ("auto", "he", "en") else "auto",
            "backend": value.get("backend") if value.get("backend") in ("auto", "cpu", "vulkan") else "auto"}


def snapshot(runtime=None):
    profile = desired_profile()
    compatibility_required = profile["cpu_variant"] == "avx2" and (
        Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "arctic/dictation/compatibility-required.json").exists()
    available = ready() and not compatibility_required
    setup = read_json(SYSTEM / "setup.json") if trusted_file(SYSTEM / "setup.json") else {}
    if not isinstance(setup, dict):
        setup = {}
    state = "ready" if available else setup.get("state", "unavailable")
    if state == "ready" and not available:
        state = "error"
    # During a download the frozen queue controls the exact progress denominator.
    # Only whitelist IDs are accepted; arbitrary status JSON cannot supply URLs.
    if state in ("queued", "downloading") and setup.get("profile") in PROFILES:
        profile = PROFILES[setup["profile"]]
    result = {"ok": True, "state": state, "ready": available, "progress": setup.get("progress", 0),
              "error": setup.get("error", ""), **profile_status(profile),
              "version": VERSION, "active_backend": "", "active_cpu_variant": "",
              "profile_selection": profile_selection(),
              "recommended_profile": profile_status(recommended_profile()),
              "compatibility_profile": profile_status(PROFILES["small-v2"]),
              "compatibility_required": compatibility_required,
              **preferences()}
    if runtime:
        result.update(runtime)
    if compatibility_required:
        result.update(ready=False, state="error", compatibility_required=True, active_backend="", active_cpu_variant="",
                      error="Optimized CPU inference is incompatible. Choose Small compatibility setup in Settings, then record again.")
    elif profile["cpu_variant"] == "baseline":
        result["compatibility_required"] = False
    if not available and state == "error" and not result["error"]:
        result["error"] = "Dictation files or dependencies are missing. Retry setup."
    return result


def notify_refresh():
    try:
        subprocess.Popen(["/usr/bin/arctic-shell-ipc", "dictation", "refresh"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def child_environment(private):
    # Override ambient remote-engine/logging settings as well as user config discovery.
    env = {k: v for k, v in os.environ.items() if not k.startswith("VOXTYPE_")}
    audio_runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    env.update(RUST_LOG="error", PIPEWIRE_RUNTIME_DIR=audio_runtime,
               PULSE_RUNTIME_PATH=str(Path(audio_runtime) / "pulse"),
               PULSE_SERVER="unix:" + str(Path(audio_runtime) / "pulse/native"),
               XDG_RUNTIME_DIR=str(private), XDG_CONFIG_HOME=str(private),
               XDG_DATA_HOME=str(private), TMPDIR=str(private))
    return env


def voxtype_config(private, language, profile=None):
    profile = desired_profile() if profile is None else profile
    selected = '["he", "en"]' if language == "auto" else json.dumps(language)
    return f'''engine = "whisper"
state_file = {json.dumps(str(private / "voxtype-state"))}
[hotkey]
enabled = false
[audio]
device = "default"
sample_rate = 16000
max_duration_secs = 60
[whisper]
mode = "local"
model = {json.dumps(str(PAYLOAD / profile["assets"]["model"][0]))}
language = {selected}
translate = false
on_demand_loading = true
gpu_isolation = false
context_window_optimization = false
eager_processing = false
streaming = false
[text]
spoken_punctuation = false
filter_filler_words = false
smart_auto_submit = false
[output]
mode = "file"
file_path = {json.dumps(str(private / "transcript"))}
file_mode = "overwrite"
auto_submit = false
fallback_to_clipboard = false
[output.notification]
on_recording_start = false
on_recording_stop = false
on_transcription = false
[osd]
enabled = false
[meeting]
enabled = false
'''


def gpu_available():
    # The Vulkan release has an x86-64-v3 ISA floor; the CPU baseline supports v2.
    try:
        return v3_supported() and any(Path("/dev/dri").glob("renderD*"))
    except OSError:
        return False


def session_locked(shared):
    if (shared / "dictation-locked").exists():
        return True
    try:
        probe = subprocess.run(["/usr/bin/arctic-shell-ipc", "lock", "isLocked"], stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, timeout=1, text=True)
        if probe.returncode != 0 or probe.stdout.strip() != "false":
            return True
        probe = subprocess.run(["/usr/bin/pgrep", "-u", str(os.getuid()), "-x", "swaylock"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1)
        return probe.returncode != 1  # Only pgrep's documented no-match establishes absence.
    except (OSError, subprocess.TimeoutExpired):
        return True  # A failed lock probe cannot establish that output is safe.


def erase_transcripts(private):
    # A namespace created exclusively by this controller. Never follow symlinks
    # and never remove files outside it. Upstream stages .transcript.<pid>.tmp.
    paths = [private / name for name in ("transcript", "transcript.done", "transcript.tmp", "insertion", "voxtype-state")]
    paths.extend(private.glob(".transcript.*.tmp"))
    for path in paths:
        try:
            if path.lstat().st_uid == os.getuid():
                path.unlink()
        except FileNotFoundError:
            pass


def cancellation(private):
    return read_json(private / "cancel.json").get("generation", "")


def mark_cancel(private):
    atomic_json(private / "cancel.json", {"generation": os.urandom(16).hex()})


def supervised(argv, **kwargs):
    # A separate exec wrapper sets Linux parent-death SIGKILL before launching
    # the trusted child. Avoid preexec_fn in the broker's multithreaded process.
    return subprocess.Popen(["/usr/bin/python3", "-I", str(SCRIPT.with_name("child_exec.py")),
                             str(os.getpid()), *argv], start_new_session=True, **kwargs)


def process_start(pid):
    try:
        return Path(f"/proc/{int(pid)}/stat").read_text().split(") ", 1)[1].split()[19]
    except (OSError, ValueError, IndexError, TypeError):
        return ""


def owned_lock_supervisor(marker):
    pid, started = marker.get("supervisor_pid"), marker.get("supervisor_start")
    return bool(pid and started and process_start(pid) == started)


def lock_supervisor(generation, arguments):
    shared, _private = runtime_paths()
    marker = shared / "dictation-locked"
    if any(arg in ("-f", "--daemonize", "--ready-fd") or arg.startswith("--ready-fd=") for arg in arguments):
        raise Failure("The lock supervisor needs a foreground swaylock process.")
    data = read_json(marker)
    if data.get("generation") == generation:
        # Register ownership before swaylock initialization. This does not claim
        # that the compositor is secured: the caller still waits for ready-fd.
        # It only makes another lock request during startup idempotent.
        data.update(supervisor_pid=os.getpid(), supervisor_start=process_start(os.getpid()))
        atomic_json(marker, data)
    read_fd, write_fd = os.pipe()
    try:
        process = subprocess.Popen(["/usr/bin/swaylock", "--ready-fd", str(write_fd), *arguments],
                                   pass_fds=(write_fd,), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        os.close(read_fd)
        raise
    finally:
        os.close(write_fd)
    readers, _, _ = select.select([read_fd], [], [], 10)
    secured = bool(readers and os.read(read_fd, 1))
    os.close(read_fd)
    if not secured:
        process.terminate()
        process.wait(timeout=3)
        raise Failure("The fallback lock could not secure this session.")
    # The caller may now return to swayidle. This detached supervisor remains
    # the real parent, distinguishing a normal unlock from a lock-client crash.
    print("secure", flush=True)
    sys.stdout.close()
    code = process.wait()
    if code == 0 and read_json(marker).get("generation") == generation:
        marker.unlink(missing_ok=True)


class Broker:
    def __init__(self, shared, private):
        self.shared, self.private = shared, private
        self.process = None
        self.output_process = None
        self.runtime = {}
        self.failure = ""
        self.last_active = time.monotonic()
        self.started = 0.0
        self.stopped = 0.0
        self.fallback_cpu = False
        self.cpu_variant = ""
        self.lock_checked = 0.0
        self.lock_state = False
        self.cancel_generation = cancellation(private)
        self.write()

    def write(self, **updates):
        if updates.get("state") in ("ready", "unavailable"):
            updates.setdefault("active_cpu_variant", "")
            updates.setdefault("active_backend", "")
        self.runtime.update(updates)
        value = snapshot(self.runtime)
        atomic_json(self.shared / "dictation.json", value)
        notify_refresh()
        return value

    def erase(self):
        erase_transcripts(self.private)

    def locked(self, force=False):
        if (self.shared / "dictation-locked").exists():
            return True
        now = time.monotonic()
        if force or now - self.lock_checked > 0.5:
            self.lock_state = session_locked(self.shared)
            self.lock_checked = now
        return self.lock_state

    def terminate(self):
        # Own Popen handles only: callers cannot supply a PID or process group.
        for process in (self.output_process, self.process):
            if process and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=0.8)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=2)
        self.process = self.output_process = None
        self.erase()

    def drain(self, stream, process):
        # Classify only. Raw upstream logs are discarded, never stored or shown.
        previous = ""
        try:
            while chunk := stream.read1(512):
                text = previous + chunk.decode("utf-8", "replace").lower()
                if process is self.process and ("error" in text or "failed" in text or "panic" in text):
                    if "audio" in text or "device not available" in text:
                        self.failure = "microphone"
                    elif not self.failure:
                        self.failure = "engine"
                previous = text[-128:]
        finally:
            stream.close()

    def start(self, generation=None):
        if self.process:
            return self.write()
        profile = desired_profile()
        if profile["cpu_variant"] == "avx2" and (self.private / "compatibility-required.json").exists():
            return self.write(ok=False, state="error", compatibility_required=True, active_backend="", active_cpu_variant="",
                              error="Optimized CPU inference is incompatible. Choose Small compatibility setup in Settings, then record again.")
        if not ready(profile=profile):
            return self.write(ok=False, state="error", error="Dictation is not ready. Finish setup before recording.")
        if self.locked(force=True):
            return self.write(ok=False, state="error", error="Unlock the session before recording.")
        generation = cancellation(self.private) if generation is None else generation
        if cancellation(self.private) != generation:
            return self.write(ok=True, state="ready", error="", message="Recording discarded.")
        self.cancel_generation = generation
        self.erase()
        self.failure = ""
        settings = preferences()
        if settings["backend"] == "vulkan" and "vulkan" not in profile["assets"] and not self.fallback_cpu:
            return self.write(ok=False, state="error", error="This Small compatibility profile uses CPU only. Select CPU or automatic acceleration and retry.")
        backend = "cpu" if self.fallback_cpu or settings["backend"] == "cpu" else "vulkan" if "vulkan" in profile["assets"] and gpu_available() else "cpu"
        if settings["backend"] == "vulkan" and backend != "vulkan" and not self.fallback_cpu:
            return self.write(ok=False, state="error", error="Vulkan acceleration is unavailable on this machine. Select CPU and retry.")
        config = self.private / "config.toml"
        config.write_text(voxtype_config(self.private, settings["language"], profile))
        os.chmod(config, 0o600)
        self.env = child_environment(self.private)
        cpu_key = "avx2" if profile["cpu_variant"] == "avx2" else "cpu"
        self.cpu_variant = "avx2" if cpu_key == "avx2" else "baseline"
        binary_key = "vulkan" if backend == "vulkan" else cpu_key
        self.binary = str(PAYLOAD / profile["assets"][binary_key][0])
        self.process = supervised([self.binary, "--quiet", "--config", str(config), "daemon"], env=self.env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for stream in (self.process.stdout, self.process.stderr):
            threading.Thread(target=self.drain, args=(stream, self.process), daemon=True).start()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if cancellation(self.private) != generation or (self.shared / "dictation-locked").exists():
                self.terminate()
                return self.write(ok=True, state="ready", error="", message="Recording discarded.")
            if self.process.poll() is not None or self.failure:
                break
            if (self.private / "voxtype-state").exists():
                break
            time.sleep(0.025)
        if not (self.private / "voxtype-state").exists() or self.process.poll() is not None or self.failure:
            trapped = backend == "cpu" and self.cpu_variant == "avx2" and self.process.poll() == -signal.SIGILL
            self.terminate()
            if backend == "vulkan":
                self.fallback_cpu = True
            if trapped:
                atomic_json(self.private / "compatibility-required.json", {"required": True})
            message = ("Optimized CPU inference is incompatible. Choose Small compatibility setup in Settings, then record again."
                       if trapped else "GPU initialization failed. CPU is selected for this session; record again." if self.fallback_cpu
                       else "The local speech engine could not start. Retry setup or choose CPU.")
            return self.write(ok=False, state="error", error=message, active_backend="cpu" if self.fallback_cpu and not trapped else "",
                              compatibility_required=trapped,
                              active_cpu_variant=profile["cpu_variant"] if self.fallback_cpu and not trapped else "")
        if cancellation(self.private) != generation or self.locked(force=True):
            self.terminate()
            return self.write(ok=True, state="ready", error="", message="Recording discarded.")
        result = self.record("start")
        if cancellation(self.private) != generation or (self.shared / "dictation-locked").exists():
            self.terminate()
            return self.write(ok=True, state="ready", error="", message="Recording discarded.")
        if result:
            self.terminate()
            return self.write(ok=False, state="error", error="Recording could not start. Check the microphone in Sound settings.")
        self.started = time.monotonic()
        self.stopped = 0
        self.last_active = self.started
        return self.write(ok=True, state="recording", error="", compatibility_required=False, active_backend=backend,
                          active_cpu_variant=self.cpu_variant if backend == "cpu" else "")

    def record(self, verb):
        return subprocess.run([self.binary, "--quiet", "--config", str(self.private / "config.toml"), "record", verb],
                              env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3).returncode

    def command(self, verb, generation=None):
        self.last_active = time.monotonic()
        state = self.runtime.get("state")
        if verb == "toggle":
            verb = "stop" if state == "recording" else "start"
        if verb == "start":
            return self.start(generation)
        if verb == "cancel":
            if self.process and self.process.poll() is None:
                try:
                    self.record("cancel")
                except (OSError, subprocess.TimeoutExpired):
                    pass
            self.terminate()
            self.failure = ""
            return self.write(ok=True, state="ready" if ready() else "unavailable", error="", active_backend="", message="Recording discarded.")
        if verb == "stop" and state == "recording":
            if self.record("stop"):
                self.terminate()
                return self.write(ok=False, state="error", error="Recording could not stop safely and was discarded. Record again.")
            self.stopped = time.monotonic()
            return self.write(ok=True, state="transcribing", error="", message="Release the shortcut keys.")
        return snapshot(self.runtime)

    def tick(self):
        if not self.process:
            return
        if self.locked() or cancellation(self.private) != self.cancel_generation:
            self.terminate()
            self.write(ok=True, state="ready", error="", message="Recording discarded on lock.", active_backend="")
            return
        if self.failure or self.process.poll() is not None:
            category = self.failure
            backend = self.runtime.get("active_backend")
            trapped = backend == "cpu" and self.cpu_variant == "avx2" and self.process.poll() == -signal.SIGILL
            self.terminate()
            if trapped:
                atomic_json(self.private / "compatibility-required.json", {"required": True})
                message = "Optimized CPU inference is incompatible. Choose Small compatibility setup in Settings, then record again."
            elif category == "microphone":
                message = "The microphone could not record. Select an input in Sound settings and try again."
            elif backend == "vulkan":
                self.fallback_cpu = True
                message = "GPU transcription failed. CPU is selected for this session; record again."
            else:
                message = "Local transcription failed. Retry setup or record again with CPU."
            self.write(ok=False, state="error", error=message, active_backend="cpu" if self.fallback_cpu and not trapped else "",
                       compatibility_required=trapped,
                       active_cpu_variant=desired_profile()["cpu_variant"] if self.fallback_cpu and not trapped else "")
            return
        state_path = self.private / "voxtype-state"
        state = state_path.read_text().strip() if state_path.exists() else ""
        if state == "transcribing" and self.runtime.get("state") == "recording":
            # Reaching upstream's hard recording cap is not an explicit Stop.
            # Discard instead of unexpectedly inserting after an unattended timer.
            self.terminate()
            self.write(ok=False, state="error", error="Recording reached its 60 second limit and was discarded. Record a shorter phrase and stop to insert it.")
            return
        done = self.private / "transcript.done"
        if done.exists():
            if not self.stopped:
                self.terminate()
                self.write(ok=False, state="error", error="Recording ended without an explicit stop and was discarded. Record again and stop to insert text.")
                return
            outcome = read_json(done)
            if outcome.get("status") == "ok":
                # File contents are never returned through IPC or added to status.
                transcript = (self.private / "transcript").read_text().removesuffix("\n")
                if len(transcript) > 65536:
                    self.terminate()
                    self.write(ok=False, state="error", error="Dictation returned too much text. Record a shorter phrase.")
                    return
                # Wait briefly for compositor shortcut release, without opening input devices.
                if time.monotonic() - self.stopped < 0.4:
                    return
                if self.locked(force=True):
                    self.command("cancel")
                    return
                insertion = self.private / "insertion"
                insertion.write_text(transcript)
                os.chmod(insertion, 0o600)
                with insertion.open("rb") as source:
                    self.output_process = supervised(["/usr/bin/wtype", "-"], stdin=source,
                                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                # Output is asynchronous so cancel requests remain responsive.
                self.erase()
                self.write(state="transcribing", message="Inserting text…")
            elif outcome.get("status") == "empty":
                self.terminate()
                self.write(ok=True, state="ready", error="", message="No speech was detected.")
            else:
                self.failure = "engine"
        if self.output_process and self.output_process.poll() is not None:
            code = self.output_process.returncode
            self.terminate()
            self.write(ok=not code, state="ready" if not code else "error", active_backend="",
                       error="" if not code else "Text insertion failed. Focus a text field and record again.", message="")
        elif time.monotonic() - self.started > 240:
            self.terminate()
            self.write(ok=False, state="error", error="Transcription timed out. Record a shorter phrase or choose CPU.")

    def serve(self):
        control = self.private / "control.sock"
        staged = self.private / ("control." + str(os.getpid()) + "." + os.urandom(8).hex() + ".sock")
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        published_inode = None
        try:
            # A path's existence must mean an endpoint is already listening.
            # Publishing directly at bind() allows clients to race listen() and
            # mistake a live starting broker for a dead controller.
            server.bind(str(staged))
            os.chmod(staged, 0o600)
            server.listen(4)
            published_inode = staged.stat().st_ino
            os.replace(staged, control)
            while True:
                readers, _, _ = select.select([server], [], [], 0.1)
                if readers:
                    connection, _ = server.accept()
                    with connection:
                        connection.settimeout(2)
                        _pid, uid, _gid = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                        if uid != os.getuid():
                            continue
                        command = connection.recv(128).decode("ascii", "ignore").strip()
                        if not command:
                            continue
                        generation = None
                        if command.startswith("{"):
                            try:
                                request = json.loads(command)
                                command = request["verb"]
                                generation = request.get("generation")
                            except (ValueError, KeyError, TypeError):
                                command = "invalid"
                        if command not in ("status", "start", "stop", "toggle", "cancel"):
                            result = snapshot({"ok": False, "error": "Unknown dictation command."})
                        else:
                            try:
                                result = self.command(command, generation)
                            except (OSError, Failure, subprocess.TimeoutExpired):
                                self.terminate()
                                result = self.write(ok=False, state="error", error="Dictation could not complete the request. Retry setup.")
                        try:
                            connection.sendall(json.dumps(result).encode() + b"\n")
                        except (BrokenPipeError, ConnectionResetError):
                            pass
                try:
                    self.tick()
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    self.terminate()
                    self.write(ok=False, state="error", error="Local dictation failed. Record again or retry setup.")
                if not self.process and time.monotonic() - self.last_active > 300:
                    break
        finally:
            self.terminate()
            server.close()
            staged.unlink(missing_ok=True)
            # An older broker must never remove a newer endpoint's pathname.
            try:
                if published_inode is not None and control.lstat().st_ino == published_inode:
                    control.unlink()
            except FileNotFoundError:
                pass


def run_broker(shared, private):
    # Client launch waits are bounded; a slow first startup can outlive one.
    # Hold a separate lock for the complete broker lifetime so another launcher
    # can never create a second audio owner or replace an active status file.
    fd = os.open(private / "broker.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        Broker(shared, private).serve()
        return True


def client(verb):
    shared, private = runtime_paths()
    control = private / "control.sock"
    generation = cancellation(private)
    if verb == "cancel":
        mark_cancel(private)
    if verb == "lock-fallback":
        generation = read_json(shared / "dictation-locked").get("generation")
        if not generation:
            raise Failure("Request the session lock before starting its fallback.")
        supervisor = subprocess.Popen(["/usr/bin/python3", "-I", str(SCRIPT), "_lock-supervisor", generation, *sys.argv[2:]],
                                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
        readers, _, _ = select.select([supervisor.stdout], [], [], 12)
        line = supervisor.stdout.readline() if readers else b""
        supervisor.stdout.close()
        if line.strip() != b"secure":
            raise Failure("The fallback lock could not secure this session.")
        return snapshot({"message": "Session locked."})
    if verb in ("lock", "unlock"):
        marker = shared / "dictation-locked"
        if verb == "lock":
            existing = read_json(marker)
            # Repeated lock requests must retain a known fallback supervisor's
            # generation, so its normal unlock can release this same marker.
            # An unowned/stale marker starts a fresh fail-closed generation.
            if not owned_lock_supervisor(existing):
                atomic_json(marker, {"locked": True, "generation": os.urandom(16).hex()})
            mark_cancel(private)
            # No IPC or child-shutdown wait in the security lock path. The
            # broker observes this generation even during initialization.
            return snapshot({"state": "ready" if ready() else "unavailable", "message": "Recording discarded on lock."})
        marker.unlink(missing_ok=True)
        return snapshot()
    if verb == "watch-unlock":
        # A vanished foreign swaylock can mean a crash with the compositor still
        # locked. Its absence and the shell's *own* unlocked flag cannot prove
        # foreign unlock. Managed supervisors clear on observed normal exit;
        # unknown locks retain their marker until authoritative unlock/session
        # restart. Keep this legacy verb harmless for existing wrapper callers.
        return snapshot()
    if verb in ("retry", "setup", "compatibility-setup", "recommended-setup"):
        client("cancel")
        arguments = ["--compatibility"] if verb == "compatibility-setup" else ["--recommended"] if verb == "recommended-setup" else []
        result = subprocess.run(["/usr/bin/pkexec", "/usr/libexec/arctic/arctic-dictation-setup", *arguments],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        if result.returncode == 0 and verb == "recommended-setup":
            (private / "compatibility-required.json").unlink(missing_ok=True)
        return snapshot({"ok": result.returncode == 0, "error": "" if not result.returncode else "Setup needs administrator authorization. Retry setup."})
    if verb in ("set-language", "set-backend"):
        key = "language" if verb == "set-language" else "backend"
        value = sys.argv[2] if len(sys.argv) == 3 else ""
        if value not in (("auto", "he", "en") if key == "language" else ("auto", "cpu", "vulkan")):
            raise Failure("Choose a supported dictation setting.")
        settings = preferences()
        settings[key] = value
        config = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "arctic"
        directory(config, os.getuid())
        atomic_json(config / "dictation.json", settings)
        if control.exists():
            client("cancel")
        value = snapshot()
        atomic_json(shared / "dictation.json", value)
        notify_refresh()
        return value
    alive = False
    if control.exists():
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                probe.settimeout(0.5)
                probe.connect(str(control))
                alive = True
        except OSError:
            pass
    if not alive:
        lock = os.open(private / "launch.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(lock, "w") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            if control.exists():
                try:
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                        probe.settimeout(0.5)
                        probe.connect(str(control))
                        alive = True
                except OSError:
                    pass
            if not alive:
                control.unlink(missing_ok=True)
                erase_transcripts(private)
                if verb in ("status", "settings", "stop", "cancel"):
                    value = snapshot()
                    atomic_json(shared / "dictation.json", value)
                    return value
                subprocess.Popen(["/usr/bin/python3", "-I", str(SCRIPT), "_broker"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                deadline = time.monotonic() + 3
                while not control.exists() and time.monotonic() < deadline:
                    time.sleep(0.025)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(8)
        connection.connect(str(control))
        request = {"verb": "status" if verb == "settings" else verb, "generation": generation}
        connection.sendall(json.dumps(request).encode() + b"\n")
        chunks = b""
        while not chunks.endswith(b"\n") and len(chunks) <= 16384:
            chunk = connection.recv(4096)
            if not chunk:
                raise Failure("Dictation's session controller stopped. Try recording again.")
            chunks += chunk
        return json.loads(chunks)


def main():
    os.umask(0o077)
    verb = sys.argv[1] if len(sys.argv) > 1 else "status"
    if verb in ("--queue", "--system-setup", "--install"):
        if os.geteuid() != 0:
            raise Failure("Dictation setup needs administrator authorization.")
        if verb == "--queue":
            allowed = {(): None, ("--compatibility",): "compatibility", ("--recommended",): "recommended"}
            arguments = tuple(sys.argv[2:])
            if arguments not in allowed:
                raise Failure("Choose a supported dictation setup operation.")
            request_setup(selection=allowed[arguments])
            return
        success = system_setup(offline="--offline" in sys.argv)
        # Installer callers deliberately treat a dependency/model failure as nonfatal.
        sys.exit(0 if success or verb == "--install" else 1)
    if verb == "_broker":
        # Disable core dumps containing audio/transcripts for the broker and descendants.
        import resource
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        shared, private = runtime_paths()
        run_broker(shared, private)
        return
    if verb == "_lock-supervisor":
        lock_supervisor(sys.argv[2], sys.argv[3:])
        return
    if verb not in ("status", "settings", "start", "stop", "toggle", "cancel", "setup", "retry", "compatibility-setup", "recommended-setup", "set-language", "set-backend", "lock", "unlock", "watch-unlock", "lock-fallback"):
        raise Failure("Unknown dictation command.")
    try:
        result = client(verb)
    except (Failure, OSError, ValueError, subprocess.TimeoutExpired) as error:
        message = str(error) if isinstance(error, Failure) else "Dictation is unavailable. Retry setup or restart your session."
        result = snapshot({"ok": False, "state": "error", "error": message})
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    try:
        main()
    except Failure as error:
        print(json.dumps({"ok": False, "state": "error", "error": str(error)}))
        sys.exit(1)
