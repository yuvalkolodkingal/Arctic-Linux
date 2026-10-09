#!/usr/bin/env python3
"""Pinned public speech fixtures and private, offline Voxtype CPU measurements.

Only summaries are printed. References, hypotheses and raw child output stay
inside private directories and must never be uploaded as workflow logs.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import time
import unicodedata
import urllib.request
import wave


HERE = Path(__file__).resolve().parent
PINS = json.loads((HERE / "pins.json").read_text())
NORMALIZATION = (
    "NFKC, casefold, NFD, remove combining marks and Unicode format controls; "
    "remove apostrophes/geresh within words; other non-letter/non-number "
    "characters become spaces; collapse whitespace. Hebrew final letters "
    "remain distinct. WER uses whitespace tokens. CER excludes whitespace."
)


class Invalid(Exception):
    """A fixed, transcript-free error code safe to put in the public report."""


def require(condition, code):
    if not condition:
        raise Invalid(code)


def sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def private_dir(path, fresh=False):
    path = Path(path).absolute()
    require(not path.is_symlink(), "private-directory-symlink")
    if fresh:
        require(not path.exists(), "output-already-exists")
    path.mkdir(parents=True, exist_ok=not fresh, mode=0o700)
    require(path.is_dir() and path.stat().st_uid == os.getuid(), "private-directory-owner")
    require(path.stat().st_mode & 0o077 == 0, "private-directory-permissions")
    return path


def write_private(path, data):
    with Path(path).open("xb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(data)


def write_json(path, value):
    write_private(path, (json.dumps(value, indent=2, ensure_ascii=True) + "\n").encode())


def verify(path, pin):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "pinned-file-missing-or-symlink")
    require(path.stat().st_size == pin["bytes"], "pinned-file-size")
    require(sha(path) == pin["sha256"], "pinned-file-sha256")
    return {"bytes": pin["bytes"], "sha256": pin["sha256"]}


def download(url, target, pin):
    """Bounded HTTPS transfer; never accepts an unverified cache or partial file."""
    if target.exists():
        verify(target, pin)
        return
    partial = target.with_suffix(target.suffix + ".partial")
    require(not partial.exists(), "partial-download-exists")
    try:
        with urllib.request.urlopen(url, timeout=60) as source, partial.open("xb") as sink:
            os.fchmod(sink.fileno(), 0o600)
            require(source.geturl().startswith("https://"), "download-insecure-redirect")
            total = 0
            for block in iter(lambda: source.read(1024 * 1024), b""):
                total += len(block)
                require(total <= pin["bytes"], "download-size-exceeded")
                sink.write(block)
        verify(partial, pin)
        partial.rename(target)
    finally:
        partial.unlink(missing_ok=True)


def normalize(value):
    text = unicodedata.normalize("NFD", unicodedata.normalize("NFKC", value).casefold())
    chars = []
    for char in text:
        category = unicodedata.category(char)
        if category.startswith("M") or category == "Cf" or char in "'\u2019\u02bc\u05f3":
            continue
        chars.append(char if category[0] in "LN" else " ")
    return " ".join("".join(chars).split())


def edit_distance(reference, hypothesis):
    # Two-row Levenshtein; reference/hypothesis may be word lists or strings.
    previous = list(range(len(hypothesis) + 1))
    for index, left in enumerate(reference, 1):
        current = [index]
        for column, right in enumerate(hypothesis, 1):
            current.append(min(current[-1] + 1, previous[column] + 1,
                               previous[column - 1] + (left != right)))
        previous = current
    return previous[-1]


def metrics(reference, hypothesis):
    reference, hypothesis = normalize(reference), normalize(hypothesis)
    words, characters = reference.split(), reference.replace(" ", "")
    require(bool(words) and bool(characters), "empty-normalized-reference")
    return {"reference_words": len(words), "word_edits": edit_distance(words, hypothesis.split()),
            "reference_characters": len(characters),
            "character_edits": edit_distance(characters, hypothesis.replace(" ", ""))}


def aggregate(samples):
    totals = {name: sum(sample[name] for sample in samples) for name in
              ("reference_words", "word_edits", "reference_characters", "character_edits")}
    require(totals["reference_words"] > 0 and totals["reference_characters"] > 0,
            "empty-language-measurements")
    totals.update(wer=totals["word_edits"] / totals["reference_words"],
                  cer=totals["character_edits"] / totals["reference_characters"])
    return totals


def wav_metadata(path):
    with wave.open(str(path), "rb") as source:
        require(source.getnchannels() == 1 and source.getframerate() == 16000
                and source.getsampwidth() == 2 and source.getcomptype() == "NONE",
                "fixture-wav-format")
        frames = source.getnframes()
        require(0 < frames <= 16000 * 60, "fixture-wav-duration")
        require(len(source.readframes(frames + 1)) == frames * 2, "fixture-wav-truncated")
    return {"audio_frames": frames, "sample_rate": 16000, "audio_seconds": frames / 16000}


def extract_rows(source, language, destination):
    # Preparation-only dependencies. Measurement uses the standard library.
    import pyarrow.parquet as parquet
    import soundfile
    import numpy
    table = parquet.ParquetFile(source)
    columns = {"id", "audio", "raw_transcription"}
    require(columns.issubset(table.schema_arrow.names), "source-parquet-schema")
    rows = next(table.iter_batches(batch_size=5, columns=sorted(columns))).to_pylist()
    require(len(rows) == 5, "source-parquet-too-few-rows")
    samples = []
    for index, row in enumerate(rows):
        name = f"{language}-{index:02d}"
        audio = row["audio"]
        require(isinstance(audio, dict) and isinstance(audio.get("bytes"), bytes),
                "source-audio-not-embedded")
        encoded = audio["bytes"]
        info = soundfile.info(io.BytesIO(encoded))
        require(info.samplerate == 16000 and info.channels == 1 and info.subtype in ("PCM_16", "FLOAT"),
                "source-audio-format")
        if info.subtype == "PCM_16":
            samples_pcm, rate = soundfile.read(io.BytesIO(encoded), dtype="int16")
            saturated = 0
        else:
            samples_float, rate = soundfile.read(io.BytesIO(encoded), dtype="float64")
            require(numpy.isfinite(samples_float).all() and
                    numpy.all(numpy.abs(samples_float) <= 1), "source-audio-amplitude")
            # FLEURS stores normalized float32 WAV. Specify the quantization
            # instead of silently treating a float-to-int cast as PCM decoding.
            quantized = numpy.rint(samples_float * 32768)
            saturated = int(numpy.count_nonzero(quantized > 32767))
            samples_pcm = numpy.clip(quantized, -32768, 32767).astype("int16")
        require(rate == 16000, "source-audio-rate")
        wav = destination / (name + ".wav")
        soundfile.write(wav, samples_pcm, rate, format="WAV", subtype="PCM_16")
        wav.chmod(0o600)
        reference = row["raw_transcription"]
        require(isinstance(reference, str) and bool(normalize(reference)), "source-reference-empty")
        reference_path = destination / (name + ".reference.txt")
        write_private(reference_path, reference.encode("utf-8"))
        require(isinstance(row["id"], int) and 0 <= row["id"] < 10000000,
                "source-id-not-integer")
        samples.append({"sample": name, "language": language, "source_row": index,
                        "source_id": str(row["id"]), "wav": wav.name,
                        "wav_bytes": wav.stat().st_size, "wav_sha256": sha(wav),
                        "source_audio_bytes": len(encoded),
                        "source_audio_sha256": hashlib.sha256(encoded).hexdigest(),
                        "source_audio_subtype": info.subtype,
                        "pcm16_positive_endpoint_saturations": saturated,
                        "reference": reference_path.name,
                        "reference_bytes": reference_path.stat().st_size,
                        "reference_sha256": sha(reference_path), **wav_metadata(wav)})
    return samples


def prepare(args):
    import pyarrow
    import soundfile
    cache = private_dir(args.cache)
    bundle = private_dir(args.bundle, fresh=True)
    samples = []
    for source in PINS["dataset"]["files"]:
        parquet = cache / (source["config"] + ".test.parquet")
        url = ("https://huggingface.co/datasets/" + PINS["dataset"]["repository"] +
               "/resolve/" + PINS["dataset"]["commit"] + "/" + source["path"])
        download(url, parquet, source)
        samples.extend(extract_rows(parquet, source["language"], bundle))
    manifest = {"schema": "arctic-dictation-fixtures-v1", "dataset": PINS["dataset"],
                "conversion": "Native mono 16000Hz PCM16 is preserved; FLOAT WAV is quantized with round-to-nearest ties-to-even after multiplication by 32768, saturating positive endpoint to 32767; no resampling, filtering, gain change or trimming",
                "decoder": {"pyarrow": pyarrow.__version__, "soundfile": soundfile.__version__,
                            "libsndfile": soundfile.__libsndfile_version__},
                "samples": samples}
    write_json(bundle / "fixtures.json", manifest)
    summary = {"schema": manifest["schema"], "samples": len(samples),
               "fixture_manifest_sha256": sha(bundle / "fixtures.json"),
               "dataset_commit": PINS["dataset"]["commit"], "license": PINS["dataset"]["license"]}
    write_json(bundle / "summary.json", summary)
    if args.payload:
        payload = private_dir(args.payload)
        for name, pin in (("voxtype-cpu", PINS["voxtype"]["cpu"]),
                          ("ggml-small.bin", PINS["voxtype"]["model"])):
            download(pin["url"], payload / name, pin)
        (payload / "voxtype-cpu").chmod(0o700)
    print(json.dumps(summary, sort_keys=True))


def fixture_path(bundle, name):
    require(isinstance(name, str) and Path(name).name == name, "fixture-path-escape")
    path = bundle / name
    require(path.is_file() and not path.is_symlink(), "fixture-file-missing-or-symlink")
    return path


def load_fixtures(bundle, expected):
    manifest_path = fixture_path(bundle, "fixtures.json")
    require(sha(manifest_path) == expected, "fixture-manifest-sha256")
    manifest = json.loads(manifest_path.read_text())
    require(manifest.get("schema") == "arctic-dictation-fixtures-v1"
            and manifest.get("dataset") == PINS["dataset"], "fixture-provenance")
    samples = manifest.get("samples", [])
    expected_order = [(language, row) for language in ("en", "he") for row in range(5)]
    require([(s.get("language"), s.get("source_row")) for s in samples] == expected_order,
            "fixture-selection")
    for sample in samples:
        for key in ("wav", "reference"):
            path = fixture_path(bundle, sample[key])
            verify(path, {"bytes": sample[key + "_bytes"], "sha256": sample[key + "_sha256"]})
        metadata = wav_metadata(bundle / sample["wav"])
        require(all(metadata[key] == sample[key] for key in metadata), "fixture-wav-metadata")
        reference = (bundle / sample["reference"]).read_text()
        require(len(reference) <= 10000 and bool(normalize(reference)), "fixture-reference-invalid")
    return samples


def config_text(model, language, threads):
    # These are the 1.1.0 field names; mode is preferred over the legacy backend.
    return f'''engine = "whisper"
[hotkey]
enabled = false
[whisper]
mode = "local"
model = {json.dumps(str(model))}
language = "{language}"
translate = false
threads = {threads}
on_demand_loading = true
gpu_isolation = false
context_window_optimization = false
eager_processing = false
streaming = false
[vad]
enabled = false
[output]
mode = "file"
auto_submit = false
fallback_to_clipboard = false
[output.notification]
on_recording_start = false
on_recording_stop = false
on_transcription = false
[text]
spoken_punctuation = false
filter_filler_words = false
smart_auto_submit = false
'''


def parse_stdout(raw, frames):
    # Pinned 1.1.0 prints this non-logging header even with --quiet. Refuse
    # unexpected prefixes (including info logs) rather than score them as text.
    match = re.fullmatch(
        r'Loading audio file: [^\n]+\nAudio format: 16000 Hz, 1 channel\(s\), Int\n'
        r'Processing (\d+) samples \([0-9.]+s\)\.\.\.\n\n(.+)\n', raw, flags=re.S)
    require(match is not None and int(match.group(1)) == frames, "unexpected-transcribe-output")
    hypothesis = match.group(2).strip()
    require(bool(normalize(hypothesis)), "empty-transcription")
    return hypothesis


def run_transcription(binary, model, sample, bundle, output, threads, timeout):
    config = output / (sample["sample"] + ".toml")
    write_private(config, config_text(model, sample["language"], threads).encode())
    stdout = output / (sample["sample"] + ".stdout.private")
    stderr = output / (sample["sample"] + ".stderr.private")
    env = {"PATH": "/usr/bin:/bin", "HOME": str(output), "LANG": "C.UTF-8",
           "RUST_LOG": "off", "XDG_CONFIG_HOME": str(output), "XDG_DATA_HOME": str(output),
           "XDG_CACHE_HOME": str(output), "XDG_RUNTIME_DIR": str(output)}
    start = time.monotonic_ns()
    with stdout.open("xb") as out, stderr.open("xb") as err:
        os.fchmod(out.fileno(), 0o600)
        os.fchmod(err.fileno(), 0o600)
        child = subprocess.Popen([str(binary), "--quiet", "--config", str(config),
                                  "--language", sample["language"], "transcribe",
                                  str(bundle / sample["wav"]), "--engine", "whisper"],
                                 stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                 env=env, start_new_session=True)
        try:
            code = child.wait(timeout=timeout)
        except BaseException:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
            raise
    elapsed = time.monotonic_ns() - start
    require(code == 0, "transcribe-process-failed")
    require(stdout.stat().st_size <= 1000000 and stderr.stat().st_size <= 1000000,
            "transcribe-output-too-large")
    hypothesis = parse_stdout(stdout.read_text(), sample["audio_frames"])
    reference = (bundle / sample["reference"]).read_text()
    # Info logs may expose the first 50 characters. Child output is private;
    # reject tested leakage in stderr without emitting any matching content.
    logged = normalize(stderr.read_text(errors="replace"))
    excerpt = normalize(hypothesis[:50])
    require(not excerpt or len(excerpt) < 12 or excerpt not in logged, "transcript-in-stderr")
    return {"sample": sample["sample"], "language": sample["language"],
            "source_row": sample["source_row"], "source_id": sample["source_id"],
            "wav_sha256": sample["wav_sha256"], "wav_bytes": sample["wav_bytes"],
            "reference_sha256": sample["reference_sha256"],
            "hypothesis_sha256": hashlib.sha256(hypothesis.encode()).hexdigest(),
            "stdout_sha256": sha(stdout), "stderr_sha256": sha(stderr),
            "config_sha256": sha(config), "elapsed_ns": elapsed,
            "audio_frames": sample["audio_frames"], "sample_rate": 16000,
            "audio_seconds": sample["audio_seconds"],
            "real_time_factor": elapsed / 1e9 / sample["audio_seconds"],
            "stderr_excerpt_check": "no-hypothesis-prefix-match", **metrics(reference, hypothesis)}


def measure(args):
    output = private_dir(args.output, fresh=True)
    report = {"schema": "arctic-dictation-accuracy-v1", "status": "failed",
              "release_acceptance": False, "dataset": PINS["dataset"],
              "fixture_manifest_sha256": args.fixture_sha256, "normalization": NORMALIZATION,
              "backend": "local-whisper-cpu-baseline", "language_mode": "explicit-he-and-en",
              "timing": "monotonic_ns; each fresh process includes model initialization and transcription",
              "threads": args.threads, "samples": [], "languages": {},
              "limitations": ["Only first five read-speech utterances per language; not representative accuracy parity evidence",
                              "No comparison with a separate OpenAI Whisper implementation",
                              "Explicit language selection; automatic detection and mixed-language speech not measured",
                              "File transcription does not test microphone, cancellation, GPU, or text insertion",
                              "Normalization ignores punctuation, capitalization and Hebrew vowel/cantillation marks; no numeral expansion",
                              "Runtime includes fresh model loading and reflects this test host only"]}
    try:
        bundle = Path(args.bundle).resolve()
        samples = load_fixtures(bundle, args.fixture_sha256)
        binary, model = Path(args.binary).resolve(), Path(args.model).resolve()
        report["binary"] = verify(binary, PINS["voxtype"]["cpu"])
        report["model"] = verify(model, PINS["voxtype"]["model"])
        require(os.access(binary, os.X_OK), "cpu-binary-not-executable")
        interfaces = sorted(path.name for path in Path("/sys/class/net").iterdir())
        require(interfaces == ["lo"], "offline-network-namespace-required")
        report["runtime"] = {"machine": platform.machine(), "kernel": platform.release(),
                             "python": platform.python_version(), "network_interfaces": interfaces,
                             "libc": list(platform.libc_ver()),
                             "distribution": {key: value for key, value in platform.freedesktop_os_release().items()
                                              if key in ("ID", "VERSION_ID", "PRETTY_NAME")},
                             "network_namespace": os.readlink("/proc/self/ns/net"),
                             "harness_sha256": sha(__file__), "pins_sha256": sha(HERE / "pins.json")}
        source_commit = os.environ.get("ARCTIC_SOURCE_COMMIT", "")
        require(not source_commit or re.fullmatch(r"[0-9a-f]{40}", source_commit), "source-commit-format")
        report["runtime"]["source_commit"] = source_commit or None
        for sample in samples:
            report["samples"].append(run_transcription(binary, model, sample, bundle, output,
                                                      args.threads, args.timeout))
        for language in ("en", "he"):
            measurements = [s for s in report["samples"] if s["language"] == language]
            require(len(measurements) == 5, "missing-language-measurements")
            report["languages"][language] = {"samples": 5, **aggregate(measurements),
                "audio_seconds": sum(s["audio_seconds"] for s in measurements),
                "elapsed_ns": sum(s["elapsed_ns"] for s in measurements)}
        report["status"] = "passed"
    except Invalid as error:
        report["failure_code"] = str(error)
    except subprocess.TimeoutExpired:
        report["failure_code"] = "transcription-timeout"
    except Exception:
        # Do not echo exceptions: paths, input/output content and downloader
        # errors may contain transcript data or credentials.
        report["failure_code"] = "measurement-error"
    write_json(output / "report.json", report)
    print("ARCTIC-DICTATION-ACCURACY " + json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


def main():
    os.umask(0o077)
    def interrupt(signum, frame):
        raise Invalid("measurement-interrupted")
    signal.signal(signal.SIGINT, interrupt)
    signal.signal(signal.SIGTERM, interrupt)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    preparation = sub.add_parser("prepare")
    preparation.add_argument("--cache", required=True)
    preparation.add_argument("--bundle", required=True)
    preparation.add_argument("--payload", help="Also fetch the reviewed CPU binary and small model into this private directory")
    measurement = sub.add_parser("measure")
    for name in ("bundle", "fixture-sha256", "binary", "model", "output"):
        measurement.add_argument("--" + name, required=True)
    measurement.add_argument("--threads", type=int, default=2)
    measurement.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    require(args.command != "measure" or 1 <= args.threads <= 64, "invalid-threads")
    require(args.command != "measure" or 1 <= args.timeout <= 1800, "invalid-timeout")
    try:
        if args.command == "prepare":
            prepare(args)
            return 0
        return measure(args)
    except Invalid as error:
        print(json.dumps({"status": "failed", "failure_code": str(error)}))
    except Exception:
        print(json.dumps({"status": "failed", "failure_code": "preparation-error"}))
    return 1


if __name__ == "__main__":
    sys.exit(main())
