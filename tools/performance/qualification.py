#!/usr/bin/env python3
"""Run one reviewed, frozen external six-boot lane on a retained exact ISO."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import types
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
# Nested command waits allow 90s and prepared-image RPC waits another 90s.
# Leave bounded headroom for status writes and handler/engine transitions. This
# changes cancellation grace, not the original 120-minute measurement budget.
CLEANUP_GRACE_SECONDS = 300


def load(name, path):
    root = ROOT.resolve()
    path = path.absolute()
    if (not path.is_file() or path.is_symlink() or not path.is_relative_to(root)
            or path.resolve() != path):
        raise ValueError('Execution helper is not a regular contained source file')
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True, timeout=120).strip()
    if os.environ.get('GITHUB_ACTIONS') == 'true' and head != os.environ.get('GITHUB_SHA'):
        raise ValueError('Execution helper HEAD differs from actual Actions source')
    expected = subprocess.check_output(['git', '-C', str(root), 'show', 'HEAD:' + path.relative_to(root).as_posix()], timeout=120)
    content = path.read_bytes()
    if content != expected:
        raise ValueError('Execution helper bytes differ from Git HEAD')
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(content, str(path), 'exec'), module.__dict__)
    return module


C = None


@contextmanager
def signal_transition():
    """Make parent handler transitions atomic; never hold this mask across spawn."""
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


@contextmanager
def defer_signals():
    """Queue cancellation during owned-resource handoffs, without masking children."""
    pending = []
    previous = {}
    def queued(signum, frame):
        pending.append(signum)
    try:
        with signal_transition():
            for signum in (signal.SIGTERM, signal.SIGINT):
                previous[signum] = signal.signal(signum, queued)
        yield pending
    finally:
        with signal_transition():
            for signum, handler in previous.items():
                signal.signal(signum, handler)


@contextmanager
def evidence_deadline(seconds=60):
    """Bound each final evidence attempt while leaving TERM/INT deferred."""
    started = time.monotonic()
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    def expired(signum, frame):
        raise TimeoutError('External paired evidence finalization timed out')
    previous_handler = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] or previous_timer[1]:
            signal.setitimer(signal.ITIMER_REAL,
                max(.000001, previous_timer[0] - (time.monotonic() - started))
                if previous_timer[0] else 0, previous_timer[1])


def stop_owned(child):
    """Attempt every bounded stop/reap action for this invocation's process group."""
    errors = []
    if child is None:
        return errors
    def attempt(label, action):
        try:
            return action()
        except BaseException as error:
            if not isinstance(error, ProcessLookupError):
                errors.append(label + ': ' + type(error).__name__)
            return None
    alive = attempt('poll', child.poll) is None
    if alive:
        attempt('TERM', lambda: os.killpg(child.pid, signal.SIGTERM))
    reaped = attempt('wait', lambda: child.wait(timeout=CLEANUP_GRACE_SECONDS))
    if reaped is None:
        attempt('KILL', lambda: os.killpg(child.pid, signal.SIGKILL))
        attempt('reap', lambda: child.wait(timeout=15))
    return errors


def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True, timeout=120).strip()


def files(root, names):
    result = {}
    for name in names:
        path = root/name
        C.require(path.is_file() and not path.is_symlink()
            and path.resolve().is_relative_to(root.resolve()), 'Unsafe pinned source: ' + name)
        blob = subprocess.check_output(['git', '-C', str(root), 'show', 'HEAD:' + name], timeout=120)
        C.require(path.read_bytes() == blob, 'Working source differs from Git: ' + name)
        result[name] = C.digest(blob)
    return result


def activation(manifest_path):
    global C
    C = load('paired_contract', ROOT/'tools/performance/contract.py')
    C.require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
        and os.environ.get('GITHUB_REPOSITORY') == 'yuvalkolodkingal/Arctic-Linux'
        and os.environ.get('GITHUB_REF') == 'refs/heads/' + C.BRANCH
        and os.environ.get('GITHUB_WORKFLOW') == 'Frozen exact-image paired performance qualification'
        and os.environ.get('GITHUB_EVENT_NAME') == 'push' and os.environ.get('GITHUB_RUN_ATTEMPT') == '1',
        'Requires the owned first-attempt external paired lane')
    C.require(re.fullmatch('[1-9][0-9]*', os.environ.get('GITHUB_RUN_ID', '')), 'Invalid owned Actions run ID')
    head = os.environ['GITHUB_SHA']
    C.require(re.fullmatch('[0-9a-f]{40}', head) and git(ROOT, 'rev-parse', 'HEAD') == head
        and not git(ROOT, 'status', '--porcelain'), 'Execution source differs or is dirty')
    event = C.parse_json(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes())
    marker = ROOT/C.MARKER
    C.require(marker.is_file() and not marker.is_symlink(), 'Activation marker must be a regular source file')
    raw_marker = marker.read_bytes()
    parent = raw_marker.decode('ascii').strip()
    C.require(re.fullmatch('[0-9a-f]{40}', parent) and event['before'] == parent == git(ROOT, 'rev-parse', 'HEAD^')
        and git(ROOT, 'rev-list', '--parents', '-n', '1', head).split() == [head, parent]
        and raw_marker == (parent+'\n').encode()
        and event['after'] == head and git(ROOT, 'diff', '--no-renames', '--name-only', parent, head).splitlines() == [C.MARKER],
        'External activation is not the reviewed sole-marker child')
    C.require(manifest_path.resolve() == (ROOT/C.MANIFEST).resolve(), 'Use the pinned external manifest')
    C.require(manifest_path.is_file() and not manifest_path.is_symlink()
        and manifest_path.stat().st_size <= 128*1024, 'Unsafe/oversized external execution manifest')
    files(ROOT, {C.MARKER, C.MANIFEST})
    plan = C.parse_json(manifest_path.read_bytes())
    C.require(plan.get('ready') is True and plan.get('performance_mode') == C.MODE, 'External execution is disabled')
    C.validate_plan(plan, candidate_source_files=plan['candidate_source_files'],
        execution_files=files(ROOT, C.EXECUTION_FILES), observer=C.observer_hashes(ROOT))
    return plan, parent


def verify(plan, source, inputs):
    C.require(git(source, 'rev-parse', 'HEAD') == plan['image']['source_sha']
        and not git(source, 'status', '--porcelain'), 'Candidate source differs or is dirty')
    C.validate_plan(plan, candidate_source_files=files(source, C.CANDIDATE_SOURCE_FILES),
        execution_files=files(ROOT, C.EXECUTION_FILES), observer=C.observer_hashes(ROOT))
    image = plan['image']
    path = inputs/'iso'/image['name']
    C.require(path.is_file() and not path.is_symlink() and path.stat().st_size == image['bytes']
        and sha(path) == image['sha256'], 'Actual candidate ISO bytes differ')
    receipt_path = inputs/'PERFORMANCE-PLAN.json'
    C.require(receipt_path.is_file() and not receipt_path.is_symlink()
        and sha(receipt_path) == image['producer_receipt_sha256'], 'Actual producer receipt differs')
    fetch = load('paired_fetch', ROOT/'tools/native-functional/fetch-image.py')
    receipt = fetch.read_receipt(receipt_path.read_bytes(), image)
    run = fetch.api('/actions/runs/' + str(image['run_id']))
    C.require(run['run_attempt'] == 1, 'Producer was rerun')
    fetch.validate(image, run, fetch.api('/actions/artifacts/' + str(image['artifact_id'])))
    jobs = fetch.api('/actions/runs/' + str(image['run_id']) + '/jobs?filter=all&per_page=100')
    C.require(jobs['total_count'] == len(jobs['jobs']), 'Incomplete producer jobs')
    fetch.validate_external_producer_steps(image, jobs['jobs'])
    return receipt


def baseline(out):
    out.mkdir()
    subprocess.run(['gh', 'release', 'download', 'v1.2.0', '--repo', 'yuvalkolodkingal/Arctic-Linux',
        '--dir', str(out), '--pattern', C.BASELINE['name'] + '.part00',
        '--pattern', C.BASELINE['name'] + '.part01'], check=True, timeout=15*60)
    path = out/C.BASELINE['name']
    with path.open('xb') as target:
        for number in ('00', '01'):
            part = out/(C.BASELINE['name'] + '.part' + number)
            C.require(part.is_file() and not part.is_symlink(), 'Original baseline part missing/unsafe')
            with part.open('rb') as source:
                shutil.copyfileobj(source, target, 8*1024*1024)
            part.unlink()
    C.require(path.stat().st_size == C.BASELINE['bytes'] and sha(path) == C.BASELINE['sha256'],
        'Original immutable baseline bytes differ')
    return path


def execution_state(plan, parent, manifest_path, status):
    return dict(schema='arctic-external-paired-execution-v1', status=status, release_acceptance=False,
        run_id=int(os.environ['GITHUB_RUN_ID']), run_attempt=1, execution_source_sha=os.environ['GITHUB_SHA'],
        reviewed_parent_sha=parent, image=plan['image'], baseline=C.BASELINE,
        plan_sha256=sha(manifest_path), observer=plan['observer'],
        candidate_source_files=plan['candidate_source_files'], execution_files=plan['execution_files'], files={})


def collect(work, evidence, plan, parent, manifest_path, status, *, ownership):
    evidence.mkdir(exist_ok=False)
    created = evidence.lstat()
    ownership.append((created.st_dev, created.st_ino))
    if work.exists():
        for path in sorted(work.rglob('*')):
            if path.is_symlink():
                raise ValueError('Paired diagnostics symlink')
            if not path.is_file() or path.suffix not in {'.json', '.log', '.txt', '.tsv', '.png'}:
                continue
            relative = path.relative_to(work)
            target = evidence/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        if (work/'frozen-observer.py').is_file():
            shutil.copyfile(work/'frozen-observer.py', evidence/'observer-source.txt')
    return execution_state(plan, parent, manifest_path, status)


def write_execution(evidence, state):
    state['files'] = {path.relative_to(evidence).as_posix(): dict(bytes=path.stat().st_size, sha256=sha(path))
        for path in sorted(evidence.rglob('*')) if path.is_file() and path.name != 'execution.json'}
    (evidence/'execution.json').write_text(json.dumps(state, indent=2) + '\n')


class DirectoryArchive:
    """Use the exact same replay contract before upload and during publication."""
    def __init__(self, root):
        self.root = root
    def infolist(self):
        return [self.getinfo(path.relative_to(self.root).as_posix())
            for path in sorted(self.root.rglob('*')) if path.is_file()]
    def getinfo(self, name):
        info = zipfile.ZipInfo(name)
        info.file_size = (self.root/name).stat().st_size
        info.external_attr = 0o100644 << 16
        return info
    def read(self, name):
        return (self.root/name).read_bytes()


def run(args):
    plan, parent = activation(args.manifest)
    C.require(not args.work.exists() and not args.evidence.exists() and not args.screened.exists(),
        'External work/evidence directories must be unused')
    receipt = verify(plan, args.source, args.inputs)
    original = baseline(args.work.parent/'baseline')
    external = dict(schema='arctic-external-paired-context-v1', run_id=int(os.environ['GITHUB_RUN_ID']),
        execution_source_sha=os.environ['GITHUB_SHA'], reviewed_parent_sha=parent,
        plan_sha256=sha(args.manifest), observer=plan['observer'],
        image_source_sha=plan['image']['source_sha'], candidate_iso_sha256=plan['image']['sha256'])
    context = args.work.parent/'external-context.json'
    context.write_text(json.dumps(external, indent=2) + '\n')
    verify(plan, args.source, args.inputs)  # Recheck exact inputs immediately before any VM.
    code = 1
    passed = False
    child = None
    failure = None
    errors = []
    def interrupted(signum, frame):
        raise InterruptedError('External paired lane interrupted: ' + str(signum))
    previous = {}
    try:
        with signal_transition():
            for signum in (signal.SIGTERM, signal.SIGINT):
                previous[signum] = signal.signal(signum, interrupted)
    except BaseException:
        with signal_transition():
            for signum, handler in previous.items():
                signal.signal(signum, handler)
        raise
    try:
        with defer_signals() as acquisition_signals:
            child = subprocess.Popen(['timeout', '--signal=TERM', f'--kill-after={CLEANUP_GRACE_SECONDS}s', '120m', sys.executable, '-B',
                str(ROOT/'tools/performance/run-paired.py'), '--baseline', str(original),
                '--candidate', str(args.inputs/'iso'/plan['image']['name']), '--out', str(args.work),
                '--candidate-source-root', str(args.source), '--candidate-source-sha', plan['image']['source_sha'],
                '--external-context', str(context)], cwd=ROOT, start_new_session=True)
        if acquisition_signals:
            raise InterruptedError('External paired lane interrupted during owned child acquisition')
        code = child.wait()
        verify(plan, args.source, args.inputs)
        passed = code == 0
    except BaseException as error:
        failure = error
    finally:
        state = None
        cleanup_signals = []
        try:
            try:
                with defer_signals() as cleanup_signals:
                    errors.extend(stop_owned(child))
                    def attempt(label, action):
                        try:
                            with evidence_deadline():
                                return action()
                        except BaseException as error:
                            errors.append(label + ': ' + type(error).__name__)
                            return None
                    def status():
                        return ('frozen_external_paired_regression_gate_passed'
                            if passed and failure is None and not errors and not cleanup_signals
                            else 'frozen_external_paired_failed')
                    evidence_ownership = []
                    state = attempt('collect', lambda: collect(args.work, args.evidence,
                        plan, parent, args.manifest, status(), ownership=evidence_ownership))
                    def require_owned_evidence():
                        current = args.evidence.lstat()
                        C.require(bool(evidence_ownership) and stat.S_ISDIR(current.st_mode)
                            and (current.st_dev, current.st_ino) == evidence_ownership[0],
                            'Evidence is not the exclusively acquired owned directory')
                    if state is None and evidence_ownership:
                        require_owned_evidence()
                        state = execution_state(plan, parent, args.manifest, 'frozen_external_paired_failed')
                    if state is not None:
                        require_owned_evidence()
                        attempt('producer receipt', lambda: shutil.copyfile(args.inputs/'PERFORMANCE-PLAN.json',
                            args.evidence/'producer-receipt.json'))
                        def save():
                            require_owned_evidence()
                            state['status'] = status()
                            (args.evidence/'runner-cleanup.json').write_text(json.dumps(dict(
                                schema='arctic-external-paired-cleanup-v1', release_acceptance=False,
                                child_acquired=child is not None, failure_type=type(failure).__name__ if failure else None,
                                errors=errors, deferred_signals=cleanup_signals), indent=2) + '\n')
                            write_execution(args.evidence, state)
                        saved_counts = (len(errors), len(cleanup_signals))
                        attempt('save', save)
                        screen = attempt('screen helper', lambda: load('paired_screen',
                            ROOT/'tools/native-functional/screen-evidence.py'))
                        screened_owned = False
                        if screen is not None:
                            def screen_owned():
                                nonlocal screened_owned
                                require_owned_evidence()
                                screen.screen_external(args.evidence, args.screened)
                                screened_owned = True
                            attempt('screen', screen_owned)
                        # A queued cancellation during copying/screening must never leave
                        # a PASS receipt. Replace only the directory this call created.
                        if (len(errors), len(cleanup_signals)) != saved_counts:
                            attempt('save failed state', save)
                            if screened_owned:
                                attempt('replace owned screening', lambda: shutil.rmtree(args.screened))
                            if screen is not None:
                                attempt('screen failed state', screen_owned)
                    if cleanup_signals and failure is None:
                        failure = InterruptedError('External paired lane interrupted during finalization')
                    if errors and failure is None:
                        failure = RuntimeError('External paired owned cleanup/evidence failed: ' + ', '.join(errors))
            except BaseException as error:
                # In particular, a signal pending during atomic handler restore
                # may run the restored raising handler at unmask. Still reseal
                # the already-collected evidence as failed before propagating.
                if failure is None:
                    failure = error
            # Include signals queued after the body's last check, immediately
            # before the defer context restored its handlers. This is also a
            # failed run; never swallow it or leave its screened PASS snapshot.
            if cleanup_signals or failure is not None:
                if failure is None:
                    failure = InterruptedError('External paired lane interrupted during finalization')
                if state is not None and state['status'] != 'frozen_external_paired_failed':
                    with defer_signals():
                        attempt('save late cancellation', save)
                        if screened_owned:
                            attempt('replace owned late screening', lambda: shutil.rmtree(args.screened))
                        if screen is not None:
                            attempt('screen late cancellation', screen_owned)
        finally:
            with signal_transition():
                for signum, handler in previous.items():
                    signal.signal(signum, handler)
    if failure is not None:
        raise failure
    if code:
        raise RuntimeError('Original six-boot runner failed; preserve this first attempt')
    comparator = load('paired_compare', ROOT/'tools/performance/compare.py')
    C.validate_evidence(DirectoryArchive(args.screened), plan=plan, plan_sha256=sha(args.manifest),
        image=plan['image'], execution_source_sha=os.environ['GITHUB_SHA'], reviewed_parent_sha=parent,
        execution_run_id=int(os.environ['GITHUB_RUN_ID']), comparator=comparator, producer_receipt=receipt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--activation-source', action='store_true')
    for name in ('source', 'inputs', 'work', 'evidence', 'screened'):
        parser.add_argument('--' + name, type=Path)
    args = parser.parse_args()
    if args.activation_source:
        plan, _ = activation(args.manifest)
        print(plan['image']['source_sha'])
    else:
        if not all(getattr(args, name) is not None for name in ('source', 'inputs', 'work', 'evidence', 'screened')):
            raise ValueError('External lane needs source, inputs, work, evidence and screened paths')
        run(args)


if __name__ == '__main__':
    main()
