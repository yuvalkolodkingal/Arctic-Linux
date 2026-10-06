#!/usr/bin/env python3
"""Collect same-image security/boot evidence; screenshots require human review."""
import argparse
import datetime
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import uuid

_SPEC = importlib.util.spec_from_file_location('recovery_v2', Path(__file__).with_name('vm-only-recovery-v2.py'))
R = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(R)

MODES = {
    'uefi-sb-try': ('uefi-sb-try', ['--firmware', 'uefi', '--mode', 'try', '--secureboot']),
    'uefi-safe': ('uefi-safe', ['--firmware', 'uefi', '--mode', 'safe']),
    'bios-try': ('bios-try', ['--firmware', 'bios', '--mode', 'try']),
}


def subsection(lines, name):
    begin, end = 'ARCTIC-' + name + '-BEGIN', 'ARCTIC-' + name + '-END'
    starts = [i for i, line in enumerate(lines) if line == begin]
    ends = [i for i, line in enumerate(lines) if line == end]
    R.require(len(starts) == len(ends) == 1 and starts[0] < ends[0], 'Missing/duplicate/reversed ' + name + ' section')
    return lines[starts[0]+1:ends[0]]


def status(lines, label, allowed):
    values = [line[len(label):] for line in lines if line.startswith(label)]
    R.require(len(values) == 1 and values[0] in allowed, 'Failed/missing/duplicate ' + label)
    return int(values[0])


def parse(serial, method, screenshots):
    R.require(method in MODES, 'Unknown mode')
    # Whole-line matching rejects the typed command and unrelated startup text.
    lines = [line.strip() for line in serial.splitlines()]
    collected = subsection(lines, 'COLLECT')
    names = ('CMDLINE', 'SECUREBOOT', 'FAILED-UNITS', 'WARNINGS', 'SELINUX', 'AVC')
    sections = {name: subsection(collected, name) for name in names}
    # Prevent a marker from masquerading as data inside another subsection.
    for section in sections.values():
        R.require(not any(re.fullmatch(r'ARCTIC-.*-(BEGIN|END)', line) for line in section), 'Nested collector section')
    selinux = sections['SELINUX']
    R.require(selinux == ['Enforcing'], 'Actual collected SELinux state must be Enforcing')
    cmdline = sections['CMDLINE']
    R.require(len(cmdline) == 1 and 'rd.live.image' in cmdline[0].split(), 'Actual live command line is missing')
    if method == 'uefi-safe':
        R.require('nomodeset' in cmdline[0].split(), 'Safe mode did not boot with nomodeset')
    secureboot = sections['SECUREBOOT']
    if method == 'uefi-sb-try':
        R.require(secureboot == ['SecureBoot enabled'], 'SecureBoot is not enabled inside the guest')
    units = sections['FAILED-UNITS']
    status(units, 'ARCTIC-FAILED-UNITS-EXIT=', {'0'})
    counts = [int(match.group(1)) for line in units if (match := re.fullmatch(r'(\d+) loaded units listed\.', line))]
    R.require(len(counts) == 1, 'Incomplete failed-units report')
    avc = sections['AVC']
    status(avc, 'ARCTIC-AVC-JOURNAL-EXIT=', {'0'})
    filter_exit = status(avc, 'ARCTIC-AVC-FILTER-EXIT=', {'0', '1'})
    denied = [line for line in avc if re.search(r'avc:.*denied', line, re.I)]
    R.require((filter_exit == 0) == bool(denied), 'AVC filter status and captured output disagree')
    R.require(all(line.startswith('ARCTIC-AVC-') or re.search(r'avc:.*denied', line, re.I) for line in avc),
              'Unexpected AVC query output')
    R.require(bool(screenshots), 'No screenshots were preserved for actual visual review')
    # Capture complete sections, including warnings, before failing semantics.
    result = dict(method=method, collector_scoped=True, sections=sections,
                  live_cmdline=cmdline[0], selinux='Enforcing', secureboot_report=secureboot,
                  failed_units_count=counts[0], avc_denials=denied,
                  screenshots=screenshots, visual_review='REQUIRED; no visual pass inferred',
                  status='semantic_collection_passed_pending_visual_review',
                  instrumentation='Test-only --debug/--collect; no vanilla boot-time or idle/performance claim')
    if counts[0] or denied:
        result['status'] = 'semantic_qualification_failed_review_required'
        result['failure_reasons'] = (['Failed units need explicit review'] if counts[0] else []) + (['Current-boot AVC denial(s)'] if denied else [])
    return result


def run(args):
    R.verify(args)  # Actual unsplit ISO hash is rechecked immediately before any VM.
    docker_version = R.require_docker()
    R.require(Path('/dev/kvm').is_char_device(), 'KVM disappeared; TCG fallback prohibited')
    base = args.evidence.parent/'boot-vm'
    R.require(not base.exists(), 'Boot output must be unused')
    suffix, options = MODES[args.method]
    vm = base/suffix
    container = 'arctic-paired-recovery-' + uuid.uuid4().hex
    env = dict(os.environ, CONTAINER_ENGINE='docker', ARCTIC_VM_CONTAINER_NAME=container)
    state = dict(status='running', method=args.method, candidate_source=R.SOURCE,
                 execution_checker_head=os.environ['GITHUB_SHA'], iso_sha256=R.ISO_SHA256,
                 docker_server_version=docker_version,
                 iso_bytes=R.ISO_BYTES, original_result_unchanged=True)
    def save():
        state['recorded_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        R.write_json(args.evidence/'execution.json', state)
    def interrupted(signum, frame):
        raise InterruptedError('Boot collection interrupted by signal ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    save()
    try:
        argv = ['bash', str(args.bundle.parents[1]/'tools/test-iso.sh'), '--iso', str(args.inputs/'iso'/R.ISO),
                '--kvm', '--memory', '4096', '--smp', '2', '--timeout', '600', '--interval', '60',
                '--collect', '--debug', '--out', str(base)] + options
        try:
            # Includes fresh container tool installation, 10-minute boot interval,
            # menu detection, typed collector, and screenshot/VM finalization.
            R.execute(argv, args.evidence/'boot-harness.log', 45*60, args.bundle.parents[1], env, container)
        finally:
            state['evidence'] = R.preserve_phase(vm, args.evidence, 'boot')
            save()
        serial = args.evidence/'boot'/'serial.log'
        R.require(serial.is_file(), 'Collected serial evidence absent')
        screenshots = sorted(name for name in state['evidence'] if name.endswith('.png'))
        result = parse(serial.read_text(errors='replace'), args.method, screenshots)
        R.write_json(args.evidence/'semantic-collection.json', result)
        R.require(result['status'] == 'semantic_collection_passed_pending_visual_review',
                  '; '.join(result.get('failure_reasons', [])))
        state['status'] = result['status']
        save()
    except BaseException as error:
        state['status'] = 'failed_or_unrun'
        state['error'] = str(error)
        save()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('preflight', 'verify', 'run'))
    parser.add_argument('--method', choices=tuple(MODES), required=True)
    for name in ('source', 'bundle', 'inputs', 'evidence'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    for name in ('source', 'bundle', 'inputs', 'evidence'):
        setattr(args, name, getattr(args, name).resolve())
    try:
        if args.phase == 'run':
            run(args)
        else:
            getattr(R, args.phase)(args)
    except BaseException as error:
        if args.evidence.exists():
            R.write_json(args.evidence/('blocked-' + args.phase + '.json'), dict(error=str(error), method=args.method,
                         original_run=R.ORIGINAL_RUN, qualification='Failed/unrun; original outcome unchanged'))
        raise


if __name__ == '__main__':
    main()
