#!/usr/bin/env python3
"""Sequential offline KVM installs and three interleaved boots of each image."""
import argparse
from contextlib import contextmanager
import contextlib
import datetime
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import uuid
import types

ROOT = Path(__file__).resolve().parents[2]
BASELINE_SHA256 = '054db5c43cae47fb60f8f43efc8e052b569aa1b14e8f15adcb15cdc48265182f'
BASELINE_PROFILE_SHA256 = 'e6b9aa317521bdaaaf343629bc5de8b914b0a5f58387a0c9fe31754f17c0d20d'


def failure_phase_summary(work, screen_failure):
    """Only fixed observations from bounded private files; never a boot result."""
    screen_codes = {'sensitive_text', 'terminal_escape', 'member_count', 'member_type',
                    'member_size', 'ownership', 'deadline', 'unclassified', 'not_observed'}
    if type(screen_failure) is not str or screen_failure not in screen_codes:
        raise ValueError('Invalid fixed screening code')
    result = dict(schema='arctic-paired-failure-phase-v1',
        status='unqualified_fixed_observations_only', release_acceptance=False,
        performance_acceptance=False, original_evidence_uploaded=False,
        screening_failure=screen_failure, private_owner_verified=False,
        observed_context='none', runner_phase='unavailable',
        read_status=dict(status='unavailable', owner='unavailable', baseline_install='unavailable',
            candidate_install='unavailable', context='unavailable', harness='unavailable', serial='unavailable'),
        markers=dict(baseline_clean_poweroff=False, candidate_clean_poweroff=False,
            qemu_start=False, qemu_exit_before_qmp=False, qmp_not_connected=False,
            default_entry=False, passphrase_prompt=False, missing_passphrase_prompt=False,
            graphical_login=False, missing_graphical_login=False, reported_collection=False,
            reported_incomplete_collection=False, console_restored=False,
            collector_begin=False, collector_end=False),
        smoke_exit='unavailable', console_restore_error='unavailable',
        # envelope-only-begin
        guest_envelope=dict(reason='not_observed',
            counts={key: 'unavailable' for key in ('collector_begin', 'collector_end', 'smoke_exit',
                'tracebacks', 'supported_exceptions', 'unsupported_exception_like_lines',
                'admitted_observer_records', 'frames', 'source_candidates')},
            collector_order='unavailable', frame_status='unavailable', control_status='unavailable',
            last_observer_phase='unavailable',
            # Class tokens are unauthenticated shape observations, not causes.
            exception_shape=dict(reason='not_observed', count='unavailable',
                exception_class='none', format='none'),
            # colored-trace-only-begin
            colored_traceback=dict(reason='not_observed', code='none', exception_class='none',
                frames='unavailable', candidates='unavailable', format='none')),
            # colored-trace-only-end
        # envelope-only-end
        guest_failure=dict(status='unavailable', code='none', exception_class='none',
            last_observer_phase='unavailable'))
    work = Path(work).absolute()
    if work.resolve() != work:
        return result
    try:
        root = os.open(work, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        return result
    if os.fstat(root).st_uid != os.geteuid():
        os.close(root)
        return result
    def read(relative, limit, anchor=None):
        # Every relative name comes from the closed inventories below. Walk
        # directories with openat/O_NOFOLLOW; reject substituted FIFO/devices.
        descriptors = []
        try:
            current = root if anchor is None else anchor
            for part in Path(relative).parts[:-1]:
                current = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
                descriptors.append(current)
                if os.fstat(current).st_uid != os.geteuid():
                    return None, 'unsafe_or_oversized'
            fd = os.open(Path(relative).name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=current)
            with os.fdopen(fd, 'rb') as source:
                info = os.fstat(source.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                        or info.st_size > limit):
                    return None, 'unsafe_or_oversized'
                content = source.read(limit + 1)
                after = os.fstat(source.fileno())
                identity = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
                if (len(content) > limit or len(content) != info.st_size
                        or identity(info) != identity(after)):
                    return None, 'unsafe_or_oversized'
                return content, 'readable'
        except FileNotFoundError:
            return None, 'absent'
        except OSError:
            return None, 'unsafe_or_oversized'
        finally:
            for fd in reversed(descriptors):
                os.close(fd)
    def value(content):
        try:
            return prepared_json(content) if content is not None else None
        except (ValueError, UnicodeError, RecursionError):
            return None
    # envelope-only-begin
    def envelope_count(number):
        return 'zero' if number == 0 else 'one' if number == 1 else 'multiple'
    # exception-shape-only-begin
    def envelope_exception_shape(body, traces):
        shape = result['guest_envelope']['exception_shape']
        if len(traces) != 1:
            shape['reason'] = 'traceback_not_unique'
            return
        if result['guest_envelope']['counts']['admitted_observer_records'] != 'one':
            shape['reason'] = 'observer_not_unique'
            return
        # CPython v3.14.0 Lib/traceback.py _format_final_exc_line and the
        # default _colorize.Traceback theme define these exact token wrappers.
        # This is a source-reference grammar, not a claim about guest colors.
        # Do not strip terminal escapes or classify private message contents.
        classes = {'RuntimeError', 'ValueError', 'InterruptedError', 'TypeError',
            'NameError', 'UnboundLocalError', 'AttributeError', 'KeyError', 'IndexError',
            'OSError', 'FileNotFoundError', 'PermissionError', 'ProcessLookupError',
            'TimeoutError', 'ConnectionError', 'BrokenPipeError', 'ImportError',
            'ModuleNotFoundError', 'AssertionError', 'MemoryError', 'OverflowError',
            'ZeroDivisionError', 'StopIteration', 'KeyboardInterrupt', 'SystemExit'}
        name = r'[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*'
        plain = re.compile('^(' + name + r')(?:: |$)')
        colored = re.compile(r'^\x1b\[1;35m(' + name
            + r')\x1b\[0m(?:: \x1b\[35m([^\x00-\x1f\x7f]*)\x1b\[0m)?$')
        tokens, invalid_control = [], False
        for line in body[traces[0] + 1:]:
            match = colored.fullmatch(line)
            if match:
                tokens.append((match[1], 'python314_default'))
                continue
            match = plain.match(line)
            if match:
                tokens.append((match[1], 'plain'))
                invalid_control |= any(ord(c) < 32 or ord(c) == 127 for c in line)
            elif line.startswith('\x1b') and re.search(name + r'(?:\x1b\[0m)?: ', line):
                # A changed/custom/malformed wrapper is a rejected category.
                invalid_control = True
        shape['count'] = envelope_count(len(tokens))
        if invalid_control:
            shape['reason'] = 'exception_control'
        elif len(tokens) != 1:
            shape['reason'] = 'exception_missing' if not tokens else 'exception_multiplicity'
        elif tokens[0][0] not in classes:
            shape['reason'] = 'unsupported_class'
        else:
            shape.update(reason='class_token_observed', exception_class=tokens[0][0], format=tokens[0][1])
    # exception-shape-only-end
    # colored-trace-only-begin
    def envelope_colored_traceback(body, traces, inventory, source_frames):
        # Exact CPython v3.14.0 default theme grammar, independently projected
        # onto the same pinned 104-site inventory. This never changes admission.
        out = result['guest_envelope']['colored_traceback']
        if len(traces) != 1:
            out['reason'] = 'traceback_not_unique'
            return
        if result['guest_envelope']['counts']['admitted_observer_records'] != 'one':
            out['reason'] = 'observer_not_unique'
            return
        shape = result['guest_envelope']['exception_shape']
        if (shape['reason'] != 'class_token_observed' or shape['format'] != 'python314_default'
                or shape['exception_class'] not in {'RuntimeError', 'ValueError', 'InterruptedError'}):
            out['reason'] = 'exception_not_supported'
            return
        exception = re.compile(r'\x1b\[1;35m(RuntimeError|ValueError|InterruptedError)\x1b\[0m: '
            r'\x1b\[35m([^\x00-\x1f\x7f]*)\x1b\[0m')
        endings = [(i, exception.fullmatch(line)) for i, line in enumerate(body)
            if exception.fullmatch(line)]
        if len(endings) != 1 or endings[0][0] <= traces[0]:
            out['reason'] = 'exception_not_supported'
            return
        # The traceback header is plain in upstream, even in colored output.
        frame = re.compile(r'  File \x1b\[35m"/run/t/guest-check\.py"\x1b\[0m, line '
            r'\x1b\[35m([1-9][0-9]{0,3})\x1b\[0m, in '
            r'\x1b\[35m([A-Za-z_][A-Za-z_0-9]*|<module>)\x1b\[0m')
        frames, contexts = [], set()
        for line in body[traces[0]+1:endings[0][0]]:
            match = frame.fullmatch(line)
            if match:
                number, function = int(match[1]), match[2]
                if not frames and (number, function) == (11, '<module>'):
                    # Exact line 11 of the whole-hash-admitted composed wrapper.
                    contexts = {'measurement["main"](preconditioned=True, causal_precision=True)'}
                else:
                    known = [entry for entry in source_frames
                        if entry['function'] == function and entry['start'] <= number <= entry['end']]
                    if not known:
                        out['reason'] = 'frame_source_unknown'
                        return
                    contexts = {entry['lines'][number-1].strip() for entry in known}
                    for entry in inventory:
                        if entry['line'] <= number <= entry['end_line'] and entry['function'] == function:
                            contexts.update(source['lines'][i-1].strip() for source in known
                                if source['source'] == entry['source']
                                for i in range(entry['line'], entry['end_line']+1))
                frames.append((number, function))
                out['frames'] = envelope_count(len(frames))
                if len(frames) > 128:
                    out['reason'] = 'frame_chain_invalid'
                    return
                continue
            # Only source-equal code context or CPython's exact red caret groups
            # can accompany an admitted frame. No general ANSI normalization.
            if not frames or len(line) > 4096 or not line.startswith('    '):
                out['reason'] = 'frame_unrecognized'
                return
            pieces = re.fullmatch(r'(?:[^\x00-\x1f\x7f]|\t|'
                r'\x1b\[(?:1;31|31)m[^\x00-\x1f\x7f]*\x1b\[0m)*', line)
            if not pieces:
                out['reason'] = 'frame_unrecognized'
                return
            # Extract only the above closed default-theme context grammar.
            text = re.sub(r'\x1b\[(?:1;31|31)m([^\x00-\x1f\x7f]*)\x1b\[0m', r'\1', line).strip()
            if text not in contexts and not (contexts and re.fullmatch(r'[ ~^]*[~^][ ~^]*', text)):
                out['reason'] = 'frame_context_unknown'
                return
        if (not 2 <= len(frames) <= 128 or frames[0] != (11, '<module>')
                or frames[1][1] != 'main' or not 871 <= frames[1][0] <= 942):
            out['reason'] = 'frame_chain_invalid'
            return
        ending = endings[0][1]
        candidates = [entry for entry in inventory
            if entry['line'] <= frames[-1][0] <= entry['end_line'] and entry['function'] == frames[-1][1]
            and entry['exception'] == ending[1]
            and (ending[2] == entry['prefix'] if entry['exact'] else ending[2].startswith(entry['prefix']))]
        out['candidates'] = envelope_count(len(candidates))
        if len(candidates) != 1:
            out['reason'] = 'source_candidate_count'
            return
        entry = candidates[0]
        out.update(reason='source_projection', code=entry['source']+'_'+str(entry['line']),
            exception_class=entry['exception'], format='python314_default')
    # colored-trace-only-end
    def envelope_phase_prefix(body, traces, observer):
        # These fixed observations remain unauthenticated UART categories.
        # Invalid/duplicate identities or phases admit no phase observation.
        keys = {'measurement_conditions', 'rpm_inventory', 'external_execution', 'app_roles',
            'measured_payload', 'pristine_idle_measurement_scope', 'pristine_idle_samples',
            'role_workload', 'role_measurement_order', 'keep_awake_restored', 'done'}
        records, seen, phase, valid = 0, set(), 'unavailable', True
        for line in body[:traces[0]] if traces else body:
            if not line.startswith('ARCTIC-PERFORMANCE '):
                continue
            if len(line.encode()) > 1048576:
                valid = False
                break
            record = value(line[len('ARCTIC-PERFORMANCE '):])
            if (type(record) is not dict or set(record) != {'stage', 'check', 'value'}
                    or record['stage'] != 'installed' or type(record['check']) is not str):
                valid = False
                break
            if record['check'] == 'observer_source_sha256':
                if record['value'] != observer['source_sha256']:
                    valid = False
                    break
                records += 1
            elif record['check'] in keys:
                if record['check'] in seen:
                    valid = False
                    break
                seen.add(record['check'])
                phase = record['check']
        envelope = result['guest_envelope']
        envelope['counts']['admitted_observer_records'] = envelope_count(records) if valid else 'unavailable'
        envelope['last_observer_phase'] = phase if valid and records == 1 else 'unavailable'
    # envelope-only-end
    def guest_failure(content, state, context):
        # Source-bound traceback shape is a diagnostic observation, never
        # authenticated runtime acceptance. All output strings are fixed here.
        import ast
        unknown = dict(status='unknown', code='none', exception_class='none',
            last_observer_phase='unavailable')
        envelope = result['guest_envelope']  # envelope-only
        pins = dict(guest='4892222d52beb2c2007a457f43b4f0389e81b279222e22aa923d49fa6ff1b0d5',
            causal='3195ee9137ca9dbd908c9021336a1f262c298ef51725bc8b2a8619d26c54e4d9')
        observer = dict(source_sha256='515ff75b394b28c9d2d02f0838612cbb86b06e2a24be25580f19554632abe064',
            frozen_sha256='9acbe74ffb8c64b63f9f180246c26ba69ae2ba80c620a1cb8baca8d9fdc4fc79',
            comparator_sha256='4d1fffe1fa047ea23d1902de4b2cd0e5f6fdf6bc5143c61b1e57aa7b2ae687b9')
        if result['smoke_exit'] != 'nonzero':
            envelope['reason'] = 'smoke_not_nonzero'  # envelope-only
            return unknown
        declared = context.get('external_execution')
        if (type(declared) is not dict or declared.get('observer') != observer
                or state.get('observer_sha256') != observer['frozen_sha256']):
            envelope['reason'] = 'observer_context_mismatch'  # envelope-only
            return dict(unknown, status='source_mismatch')
        frozen, status = read('frozen-observer.py', 131072)
        if status != 'readable' or hashlib.sha256(frozen).hexdigest() != observer['frozen_sha256']:
            envelope['reason'] = 'frozen_observer_mismatch'  # envelope-only
            return dict(unknown, status='source_mismatch')
        try:
            source_root = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError:
            envelope['reason'] = 'source_root_unavailable'  # envelope-only
            return dict(unknown, status='source_mismatch')
        inventory = []
        source_frames = []  # colored-trace-only # envelope-only
        try:
            if os.fstat(source_root).st_uid != os.geteuid():
                envelope['reason'] = 'source_directory_owner'  # envelope-only
                return dict(unknown, status='source_mismatch')
            for name, expected in pins.items():
                raw, status = read('tools/performance/' + name + '.py', 131072, source_root)
                if status != 'readable' or hashlib.sha256(raw).hexdigest() != expected:
                    envelope['reason'] = 'source_blob_mismatch'  # envelope-only
                    return dict(unknown, status='source_mismatch')
                tree = ast.parse(raw)
                source_frames.extend(dict(source=name, function=node.name, start=node.lineno,  # colored-trace-only # envelope-only
                    end=node.end_lineno, lines=raw.decode().splitlines()) for node in ast.walk(tree)  # colored-trace-only # envelope-only
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))  # colored-trace-only # envelope-only
                parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
                for node in ast.walk(tree):
                    if (not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call)
                            or not node.exc.args or not isinstance(node.exc.func, ast.Name)
                            or node.exc.func.id not in ('RuntimeError', 'ValueError', 'InterruptedError')):
                        continue
                    first, prefix, exact = node.exc.args[0], None, False
                    if isinstance(first, ast.Constant) and type(first.value) is str:
                        prefix, exact = first.value, True
                    elif (isinstance(first, ast.JoinedStr) and first.values
                            and isinstance(first.values[0], ast.Constant)):
                        prefix = first.values[0].value
                    elif (isinstance(first, ast.BinOp) and isinstance(first.op, ast.Add)
                            and isinstance(first.left, ast.Constant)):
                        prefix = first.left.value
                    if type(prefix) is not str or not prefix or '\n' in prefix or '\r' in prefix:
                        continue
                    function = node
                    while function in parents and not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        function = parents[function]
                    function = function.name if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)) else '<module>'
                    inventory.append(dict(source=name, line=node.lineno, end_line=node.end_lineno,
                        function=function, exception=node.exc.func.id, prefix=prefix, exact=exact,
                        raise_sha256=hashlib.sha256(ast.get_source_segment(raw.decode(), node).encode()).hexdigest()))
        except (ValueError, UnicodeError, SyntaxError):
            envelope['reason'] = 'source_parse_failure'  # envelope-only
            return dict(unknown, status='source_mismatch')
        finally:
            os.close(source_root)
        # Complete 104-site inventory bound to the original frozen observer.
        # A changed source requires a fresh explicit inventory review.
        digest = hashlib.sha256(json.dumps(inventory, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if len(inventory) != 104 or digest != '2d94f03b8519b3a3e4d95f24a2834dec5171997a84e6deba1f02e20fd936701b':
            envelope['reason'] = 'source_inventory_mismatch'  # envelope-only
            return dict(unknown, status='source_mismatch')
        try:
            serial = content.decode('utf-8')
        except UnicodeError:
            envelope['reason'] = 'uart_utf8'  # envelope-only
            return dict(unknown, status='invalid_uart')
        envelope['control_status'] = 'present' if any(ord(c) < 32 and c not in '\t\r\n' or ord(c) == 127 for c in serial) else 'none'  # envelope-only
        if not serial.endswith('\n') or '\x00' in serial:
            envelope['reason'] = 'uart_termination'  # envelope-only
            return dict(unknown, status='invalid_uart')
        # Only LF/CRLF records count. Other terminal/control bytes cannot
        # manufacture an observer record, traceback frame or collector marker.
        lines = [line.removesuffix('\r') for line in serial.split('\n')]
        positions = lambda token: [i for i, line in enumerate(lines) if line == token]
        begins, ends = positions('ARCTIC-COLLECT-BEGIN'), positions('ARCTIC-COLLECT-END')
        exits = [i for i, line in enumerate(lines) if re.fullmatch('ARCTIC-INSTALLED-SMOKE-EXIT=[0-9]{1,3}', line)]
        envelope['counts'].update(collector_begin=envelope_count(len(begins)), collector_end=envelope_count(len(ends)), smoke_exit=envelope_count(len(exits)))  # envelope-only
        if len(begins) != 1 or len(ends) != 1 or len(exits) != 1:
            envelope['reason'] = 'marker_multiplicity'  # envelope-only
            return dict(unknown, status='ambiguous')
        begin, end, exit_at = begins[0], ends[0], exits[0]
        envelope['collector_order'] = 'ordered' if begin < exit_at < end else 'invalid'  # envelope-only
        if not begin < exit_at < end or not 1 <= int(lines[exit_at].rsplit('=', 1)[1]) <= 255:
            envelope['reason'] = 'marker_order' if not begin < exit_at < end else 'smoke_exit_range'  # envelope-only
            return unknown
        body = lines[begin + 1:exit_at]
        traces = [i for i, line in enumerate(body) if line == 'Traceback (most recent call last):']
        exceptions = [i for i, line in enumerate(body)
            if re.match(r'^(?:RuntimeError|ValueError|InterruptedError): ', line)]
        envelope['counts'].update(tracebacks=envelope_count(len(traces)), supported_exceptions=envelope_count(len(exceptions)))  # envelope-only
        envelope['counts']['unsupported_exception_like_lines'] = envelope_count(sum(bool(re.match(r'^(?:[A-Za-z_][A-Za-z_0-9]*\.)*[A-Z][A-Za-z_0-9]*: ', line)) and not re.match(r'^(?:RuntimeError|ValueError|InterruptedError): ', line) for line in body))  # envelope-only
        envelope_phase_prefix(body, traces, observer)  # envelope-only
        envelope_exception_shape(body, traces)  # exception-shape-only # envelope-only
        envelope_colored_traceback(body, traces, inventory, source_frames)  # colored-trace-only # envelope-only
        if len(traces) > 1 or len(exceptions) > 1:
            envelope['reason'] = 'traceback_multiplicity'  # envelope-only
            return dict(unknown, status='ambiguous')
        if len(traces) != 1 or len(exceptions) != 1 or traces[0] >= exceptions[0]:
            envelope['reason'] = 'traceback_order' if len(traces) == len(exceptions) == 1 else 'traceback_missing'  # envelope-only
            return unknown
        phase_keys = {'measurement_conditions', 'rpm_inventory', 'external_execution', 'app_roles',
            'measured_payload', 'pristine_idle_measurement_scope', 'pristine_idle_samples',
            'role_workload', 'role_measurement_order', 'keep_awake_restored', 'done'}
        observer_records, seen_phases, last_phase = 0, set(), 'unavailable'
        envelope['counts']['admitted_observer_records'] = 'zero'  # envelope-only
        for line in body[:traces[0]]:
            if not line.startswith('ARCTIC-PERFORMANCE '):
                continue
            if len(line.encode()) > 1048576:
                envelope['reason'] = 'observer_record_oversized'  # envelope-only
                return dict(unknown, status='invalid_uart')
            record = value(line[len('ARCTIC-PERFORMANCE '):])
            if (type(record) is not dict or set(record) != {'stage', 'check', 'value'}
                    or record['stage'] != 'installed' or type(record['check']) is not str):
                envelope['reason'] = 'observer_record_invalid'  # envelope-only
                return dict(unknown, status='invalid_uart')
            if record['check'] == 'observer_source_sha256':
                observer_records += 1
                if record['value'] != observer['source_sha256']:
                    envelope['reason'] = 'observer_source_mismatch'  # envelope-only
                    return dict(unknown, status='source_mismatch')
                envelope['counts']['admitted_observer_records'] = envelope_count(observer_records)  # envelope-only
            elif record['check'] in phase_keys:
                if record['check'] in seen_phases:
                    envelope['reason'] = 'observer_phase_duplicate'  # envelope-only
                    return dict(unknown, status='ambiguous')
                seen_phases.add(record['check'])
                last_phase = record['check']
        if observer_records != 1:
            envelope['reason'] = 'observer_record_count'  # envelope-only
            return dict(unknown, status='ambiguous' if observer_records else 'unknown')
        envelope['last_observer_phase'] = last_phase  # envelope-only
        # Wrapper line 11 calls the original main. An echoed literal or a
        # traceback from another path cannot supply a source-known code.
        frame = re.compile(r'  File "/run/t/guest-check\.py", line ([1-9][0-9]{0,3}), in ([A-Za-z_][A-Za-z_0-9]*|<module>)')
        frames = []
        envelope['counts']['frames'] = 'zero'  # envelope-only
        for line in body[traces[0] + 1:exceptions[0]]:
            matched = frame.fullmatch(line)
            if matched:
                frames.append((int(matched[1]), matched[2]))
                envelope['counts']['frames'] = envelope_count(len(frames))  # envelope-only
            elif not line.startswith('    ') or len(line) > 4096:
                envelope['frame_status'] = 'control' if any(ord(c) < 32 and c not in '\t\r' or ord(c) == 127 for c in line) else 'unrecognized'  # envelope-only
                envelope['reason'] = 'frame_unrecognized'  # envelope-only
                return unknown
        if (not 2 <= len(frames) <= 128 or frames[0] != (11, '<module>')
                or frames[1][1] != 'main' or not 871 <= frames[1][0] <= 942):
            envelope['frame_status'] = 'invalid_chain'  # envelope-only
            envelope['reason'] = 'frame_chain_invalid'  # envelope-only
            return unknown
        envelope['frame_status'] = 'recognized'  # envelope-only
        exception = body[exceptions[0]]
        candidates = [entry for entry in inventory
            if entry['line'] <= frames[-1][0] <= entry['end_line'] and entry['function'] == frames[-1][1]
            and (exception == entry['exception'] + ': ' + entry['prefix'] if entry['exact']
                 else exception.startswith(entry['exception'] + ': ' + entry['prefix']))]
        envelope['counts']['source_candidates'] = envelope_count(len(candidates))  # envelope-only
        if len(candidates) != 1:
            envelope['reason'] = 'source_candidate_count'  # envelope-only
            return dict(unknown, status='ambiguous' if candidates else 'unknown')
        entry = candidates[0]
        envelope['reason'] = 'source_known_shape'  # envelope-only
        return dict(status='source_known_shape', code=entry['source'] + '_' + str(entry['line']),
            exception_class=entry['exception'], last_observer_phase=last_phase)
    try:
        content, result['read_status']['status'] = read('status.json', 65536)
        state = value(content)
        content, result['read_status']['owner'] = read('vm-prepared-image-owner.json', 4096)
        owner = value(content)
        if (type(state) is not dict or type(owner) is not dict
                or type(state.get('task_id')) is not str or not re.fullmatch('[0-9a-f]{32}', state['task_id'])
                or set(owner) != {'schema', 'release_acceptance', 'task_id', 'container', 'base_id'}
                or owner.get('schema') != 'arctic-paired-test-image-owner-v1'
                or owner.get('release_acceptance') is not False or owner.get('task_id') != state['task_id']
                or type(owner.get('container')) is not str
                or not re.fullmatch('arctic-paired-' + state['task_id'] + '-[0-9a-f]{8}', owner['container'])
                or type(owner.get('base_id')) is not str
                or not re.fullmatch('(?:sha256:)?[0-9a-f]{64}', owner['base_id'])):
            return result
        result['private_owner_verified'] = True
        # Deliberately exclude success/measurement phases from this diagnostic.
        phases = {'prepare_immutable_vm_tools', 'offline_install_baseline', 'offline_install_candidate',
                  'blocked', 'command_interrupted', 'command_timeout', 'prepared_image_cleanup_failed'}
        phase = state.get('phase')
        result['runner_phase'] = phase if type(phase) is str and phase in phases else 'unavailable'
        for image in ('baseline', 'candidate'):
            content, result['read_status'][image + '_install'] = read(image + '-install-harness.log', 1048576)
            if content is not None:
                result['markers'][image + '_clean_poweroff'] = b'ARCTIC-PRISTINE-INSTALL-POWEROFF=clean' in content
        current = None
        # A context file observes preparation only; it proves no boot completion.
        for image, number in (('baseline', 1), ('candidate', 1), ('candidate', 2),
                              ('baseline', 2), ('baseline', 3), ('candidate', 3)):
            prefix = f'runs/{image}/{number}/'
            content, status = read(prefix + 'performance-context.json', 32768)
            if status == 'absent':
                continue
            context = value(content)
            if (type(context) is not dict or context.get('image') != image
                    or type(context.get('boot')) is not int or context['boot'] != number
                    or context.get('collector') != 'console'):
                result['read_status']['context'] = 'unsafe_or_oversized'
                return result
            current = prefix
            current_context = context
            result['read_status']['context'] = status
            result['observed_context'] = f'{image}_{number}'
        if current is None:
            return result
        content, result['read_status']['harness'] = read(current + 'harness.log', 1048576)
        if content is not None:
            literals = dict(qemu_start=b'qemu started (boot):',
                qemu_exit_before_qmp=b'qemu exited: see qemu-boot.log', qmp_not_connected=b'no QMP socket',
                default_entry=b'booting the default entry',
                passphrase_prompt=b'passphrase prompt on screen: boot-31-luks-prompt.png',
                missing_passphrase_prompt=b'no passphrase prompt detected; typing the passphrase anyway',
                graphical_login=b'login screen on screen: boot-41-login.png',
                missing_graphical_login=b'no login screen detected; typing the password anyway',
                reported_collection=b'collected into serial-boot.log (ARCTIC-COLLECT-BEGIN/END, attempt ',
                reported_incomplete_collection=b'collect.sh did not finish (attempt ')
            for key, literal in literals.items():
                result['markers'][key] = literal in content
        content, result['read_status']['serial'] = read(current + 'serial-boot.log', 8388608)
        if content is not None:
            for key, literal in (('console_restored', b'ARCTIC-PERFORMANCE-CONSOLE-RESTORED session='),
                                 ('collector_begin', b'ARCTIC-COLLECT-BEGIN'), ('collector_end', b'ARCTIC-COLLECT-END')):
                result['markers'][key] = literal in content
            exits = re.findall(rb'(?:^|\n)ARCTIC-INSTALLED-SMOKE-EXIT=([0-9]{1,3})(?=\r?(?:\n|$))', content)
            result['smoke_exit'] = ('absent' if not exits else 'ambiguous' if len(exits) != 1
                else 'zero' if exits[0] == b'0' else 'nonzero')
            errors = [(code, literal) for code, literal in (
                ('no_unique_desktop_session', b'RuntimeError: No unique actual desktop session for console restoration'),
                ('invalid_desktop_vt', b'RuntimeError: Invalid actual desktop VT'),
                ('inactive_desktop_vt', b'RuntimeError: Desktop VT did not become active')) if literal in content]
            result['console_restore_error'] = 'none' if not errors else errors[0][0] if len(errors) == 1 else 'multiple'
            result['guest_failure'] = guest_failure(content, state, current_context)
        return result
    finally:
        os.close(root)


@contextlib.contextmanager
def prepared_signal_transition():
    """Brief parent-only mask for atomic handler changes, never across spawn."""
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


@contextlib.contextmanager
def defer_prepared_signals():
    pending, previous = [], {}
    def queued(signum, frame):
        pending.append(signum)
    try:
        with prepared_signal_transition():
            for signum in (signal.SIGTERM, signal.SIGINT):
                previous[signum] = signal.signal(signum, queued)
        yield pending
    finally:
        with prepared_signal_transition():
            for signum, handler in previous.items():
                signal.signal(signum, handler)


def prepared_image_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:sha256:)?[0-9a-f]{64}', value):
        raise ValueError('Invalid prepared image identity')
    return 'sha256:' + value.removeprefix('sha256:')


def prepared_read(path, limit=4096):
    """Read only a small regular receipt; never follow a substituted symlink."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError('Unsafe prepared image receipt')
        content = source.read(limit + 1)
        if len(content) > limit:
            raise ValueError('Oversized prepared image receipt')
        return content


def prepared_json(content):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate prepared image JSON field')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Nonfinite prepared image JSON field')
    return json.loads(content, object_pairs_hook=pairs, parse_constant=invalid)


def prepared_owner(folder, task_id):
    owner = prepared_json(prepared_read(folder/'vm-prepared-image-owner.json'))
    if (not re.fullmatch('[0-9a-f]{32}', task_id)
            or not isinstance(owner, dict)
            or set(owner) != {'schema', 'release_acceptance', 'task_id', 'container', 'base_id'}
            or owner['schema'] != 'arctic-paired-test-image-owner-v1'
            or owner['release_acceptance'] is not False or owner['task_id'] != task_id
            or not isinstance(owner['container'], str)
            or not re.fullmatch('arctic-paired-' + task_id + '-[0-9a-f]{8}', owner['container'])):
        raise ValueError('Prepared image ownership receipt differs from this task')
    prepared_image_id(owner['base_id'])
    return owner


def cleanup_prepared_image(engine, folder, task_id, known_id=None):
    """Recover only this task's immutable labeled image, including lost replies."""
    try:
        owner = prepared_owner(folder, task_id)
    except FileNotFoundError:
        if known_id is not None:
            raise ValueError('Acquired image has no prepared ownership receipt')
        return dict(status='not_acquired', image_id=None, errors=[])
    expected_labels = {'org.arctic.test.vm-tools.scope':'paired-v1',
        'org.arctic.test.vm-tools.task':task_id,
        'org.arctic.test.vm-tools.container':owner['container'],
        'org.arctic.test.vm-tools.base':owner['base_id']}
    def command(argv):
        result = subprocess.run([engine] + argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=30, check=True)
        if len(result.stdout) > 64*1024 or len(result.stderr) > 64*1024:
            raise ValueError('Oversized prepared image engine reply')
        return result.stdout
    identifiers = []
    try:
        raw_id = prepared_read(folder/'vm-prepared-image-id.txt', 80).decode('ascii')
        if not re.fullmatch(r'(?:sha256:)?[0-9a-f]{64}\n', raw_id):
            raise ValueError('Invalid prepared image ID receipt')
        identifiers.append(prepared_image_id(raw_id[:-1]))
    except FileNotFoundError:
        pass
    if known_id is not None:
        identifier = prepared_image_id(known_id)
        if identifiers and identifiers != [identifier]:
            raise ValueError('Prepared image identity handoff differs from receipt')
        identifiers = [identifier]
    if not identifiers:
        raw = command(['image', 'ls', '--no-trunc', '--quiet',
            '--filter', 'label=org.arctic.test.vm-tools.scope=paired-v1',
            '--filter', 'label=org.arctic.test.vm-tools.task=' + task_id])
        identifiers = list(dict.fromkeys(prepared_image_id(line) for line in raw.splitlines()))
        if not identifiers:
            # Intent was written immediately before commit. An interrupted
            # engine RPC may still finish later: absence is not ownership
            # settlement, and cannot be reported as successful cleanup.
            raise RuntimeError('Prepared image commit outcome unresolved; no exact labeled image found')
    if len(identifiers) != 1:
        raise ValueError('Ambiguous prepared image ownership; refusing removal')
    identifier = identifiers[0]
    inventory = prepared_json(command(['image', 'inspect', identifier]))
    if (not isinstance(inventory, list) or len(inventory) != 1
            or not isinstance(inventory[0], dict)
            or prepared_image_id(inventory[0].get('Id')) != identifier
            or not isinstance(inventory[0].get('Config'), dict)
            or not isinstance(inventory[0]['Config'].get('Labels'), dict)
            or any(inventory[0]['Config']['Labels'].get(key) != value
                   for key, value in expected_labels.items())):
        raise ValueError('Prepared image immutable ID or ownership labels differ; refusing removal')
    command(['image', 'rm', identifier])
    return dict(status='removed', image_id=identifier, errors=[])


def finalize_prepared_image(engine, folder, task_id, known_id, state, save):
    """Bound cleanup and retain failed status even after repeated cancellation."""
    pending, failure = [], None
    try:
        with defer_prepared_signals() as pending:
            try:
                state['vm_prepared_image_cleanup'] = cleanup_prepared_image(engine, folder, task_id, known_id)
            except BaseException as error:
                failure = error
                state['vm_prepared_image_cleanup'] = dict(status='blocked', image_id=None,
                    errors=[type(error).__name__])
            state['vm_prepared_image_cleanup']['deferred_signals'] = list(pending)
            if failure or pending:
                state['error'] = 'Prepared image cleanup failed or was interrupted'
                save('blocked')
            else:
                save(state['phase'])
    except BaseException as error:
        failure = error
    if pending and failure is None:
        failure = InterruptedError('Prepared image cleanup interrupted by signal ' + str(pending[0]))
    if failure is not None:
        # Includes signals delivered during restoration or after the yielded body.
        with defer_prepared_signals():
            state['error'] = 'Prepared image cleanup failed or was interrupted'
            state.setdefault('vm_prepared_image_cleanup', dict(status='blocked', image_id=None,
                errors=[type(failure).__name__]))['deferred_signals'] = list(pending)
            save('blocked')
        raise failure


def paired_boot_order():
    # Counterbalance whether an image runs first without adding or discarding
    # boots. Three pairs still provide only a small descriptive distribution.
    return [(number, name) for number in range(1, 4)
            for name in (('baseline', 'candidate') if number % 2 else ('candidate', 'baseline'))]


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--candidate-source-root', type=Path)
    parser.add_argument('--candidate-source-sha')
    parser.add_argument('--external-context', type=Path)
    args = parser.parse_args()
    external = None
    candidate_root = ROOT
    candidate_sources = None
    if any((args.candidate_source_root, args.candidate_source_sha, args.external_context)):
        if not all((args.candidate_source_root, args.candidate_source_sha, args.external_context)):
            raise RuntimeError('External execution requires exact candidate source and context together')
        candidate_root = args.candidate_source_root.resolve()
        if subprocess.check_output(['git', '-C', str(candidate_root), 'rev-parse', 'HEAD'], text=True).strip() != args.candidate_source_sha:
            raise RuntimeError('Candidate source checkout differs from exact image source')
        if subprocess.check_output(['git', '-C', str(candidate_root), 'status', '--porcelain'], text=True).strip():
            raise RuntimeError('Candidate source checkout is dirty')
        external = json.loads(args.external_context.read_text())
        if external.get('schema') != 'arctic-external-paired-context-v1' or external.get('image_source_sha') != args.candidate_source_sha:
            raise RuntimeError('External execution context differs from source')
        contract = types.ModuleType('paired_contract')
        contract_path = ROOT/'tools/performance/contract.py'
        if not contract_path.is_file() or contract_path.is_symlink() or contract_path.resolve() != contract_path:
            raise RuntimeError('External contract must be a regular contained source file')
        execution_head = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
        if execution_head != external.get('execution_source_sha'):
            raise RuntimeError('External contract execution checkout differs')
        expected_contract = subprocess.check_output(['git', '-C', str(ROOT), 'show', 'HEAD:tools/performance/contract.py'])
        contract_bytes = contract_path.read_bytes()
        if contract_bytes != expected_contract:
            raise RuntimeError('External contract bytes differ from Git HEAD')
        contract.__file__ = str(contract_path)
        exec(compile(contract_bytes, contract.__file__, 'exec'), contract.__dict__)
        candidate_sources = {name: sha256(candidate_root / name) for name in contract.CANDIDATE_SOURCE_FILES}
    if not Path('/dev/kvm').is_char_device():
        raise RuntimeError('Native KVM required; no silent TCG fallback')
    if args.baseline.stat().st_size != 2322073600 or sha256(args.baseline) != BASELINE_SHA256:
        raise RuntimeError('Original v1.2 baseline size/checksum differs')
    args.out = args.out.resolve()
    if args.out.exists() and any(args.out.iterdir()):
        raise RuntimeError('Use a new output directory; previous measurements must remain intact')
    args.out.mkdir(parents=True, exist_ok=True)
    probe = args.out / 'frozen-observer.py'
    subprocess.run([sys.executable, str(ROOT / 'tools/performance/compose-paired-probe.py'), str(probe)], check=True)
    if external and sha256(probe) != external['observer']['frozen_sha256']:
        raise RuntimeError('Frozen observer differs from reviewed external execution')
    images = {'baseline': args.baseline.resolve(), 'candidate': args.candidate.resolve()}
    state = dict(acceleration='kvm', memory_mib=4096, vcpus=2, restricted_network=True,
                 observer_sha256=sha256(probe), images={n: dict(path=str(p), bytes=p.stat().st_size,
                 sha256=sha256(p)) for n, p in images.items()}, runs=[],
                 planned_boot_order=[dict(image=name, boot=number) for number, name in paired_boot_order()])

    def save(phase):
        state['phase'] = phase
        state['timestamp_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        (args.out / 'status.json').write_text(json.dumps(state, indent=2) + '\n')
        print(phase, flush=True)

    def require_idle_vm_host():
        if external:
            for name, path in images.items():
                if path.stat().st_size != state['images'][name]['bytes'] or sha256(path) != state['images'][name]['sha256']:
                    raise RuntimeError('Input ISO changed before measurement: ' + name)
            if {name: sha256(candidate_root / name) for name in candidate_sources} != candidate_sources:
                raise RuntimeError('Candidate image-source inputs changed before measurement')
            if subprocess.check_output(['git', '-C', str(candidate_root), 'rev-parse', 'HEAD'], text=True).strip() != args.candidate_source_sha:
                raise RuntimeError('Candidate source HEAD changed before measurement')
            if subprocess.check_output(['git', '-C', str(candidate_root), 'status', '--porcelain'], text=True).strip():
                raise RuntimeError('Candidate source checkout became dirty before measurement')
        active = []
        for comm in Path('/proc').glob('[0-9]*/comm'):
            try:
                if comm.read_text().startswith('qemu-system'):
                    active.append(comm.parent.name)
            except OSError:
                continue
        if active:
            raise RuntimeError('Another QEMU is active; refusing concurrent VM measurements: ' + ','.join(active))
        state['host_loadavg_before_stage'] = Path('/proc/loadavg').read_text().strip()

    engine = os.environ.get('CONTAINER_ENGINE') or ('docker' if shutil.which('docker') else 'podman')
    prepared_id = None
    toolchain_sha = None
    state['task_id'] = uuid.uuid4().hex

    def interrupt(signum, frame):
        raise InterruptedError('Paired acceptance interrupted by signal ' + str(signum))

    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)

    def execute(argv, log, timeout, vm=False, provision=False):
        name = 'arctic-paired-' + state['task_id'] + '-' + uuid.uuid4().hex[:8]
        env = dict(os.environ)
        owns_container = vm or provision
        if owns_container:
            env['ARCTIC_VM_CONTAINER_NAME'] = name
        if vm:
            env.update(ARCTIC_FEDORA_IMAGE=prepared_id, ARCTIC_VM_TOOLS_PREPARED='1', ARCTIC_VM_CONTAINER_NAME=name)
        process = None
        failure = None
        code = None
        errors = []
        acquisition_signals = []
        cleanup_signals = []

        @contextmanager
        def signal_transition():
            # Mask only this parent's handler transition, never child creation.
            previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
            try:
                yield
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, previous)

        @contextmanager
        def defer_signals():
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

        def attempt(label, action):
            try:
                return action()
            except BaseException as error:
                if not isinstance(error, ProcessLookupError):
                    errors.append(label + ': ' + type(error).__name__)
                return None

        def stop_owned():
            if process is None:
                return
            if attempt('poll', process.poll) is None:
                attempt('TERM', lambda: os.killpg(process.pid, signal.SIGTERM))
            # A failed signal or evidence write must not suppress waits/KILL/reap.
            if attempt('wait', lambda: process.wait(timeout=15)) is None:
                if attempt('poll before KILL', process.poll) is None:
                    attempt('KILL', lambda: os.killpg(process.pid, signal.SIGKILL))
                attempt('reap', lambda: process.wait(timeout=15))

        def remove_owned(output):
            if not owns_container:
                return
            # --rm may already have removed it. Prove this exact name absent
            # rather than accepting every failed removal or failing on absence.
            try:
                subprocess.run([engine, 'rm', '--force', name], stdout=output, stderr=output, timeout=30)
            except BaseException:
                pass
            try:
                remaining = subprocess.run([engine, 'ps', '--all', '--filter', 'name=' + name,
                    '--format', '{{.Names}}'], stdout=subprocess.PIPE, stderr=output, timeout=30)
                if remaining.returncode or name.encode() in remaining.stdout.splitlines():
                    errors.append('owned container absence: not proved')
            except BaseException as error:
                errors.append('owned container absence: ' + type(error).__name__)

        def record_failure(output):
            if failure is None:
                return
            state['interrupted_command'] = dict(argv=argv, container=name if owns_container else None,
                error=str(failure), child_acquired=process is not None, cleanup_errors=list(errors),
                deferred_signals=list(acquisition_signals) + list(cleanup_signals))
            attempt('save failed command', lambda: save('command_timeout'
                if isinstance(failure, subprocess.TimeoutExpired) else 'command_interrupted'))
            # Preserve a bounded owned-log failure receipt even if status save fails.
            attempt('write owned failure log', lambda: output.write('ARCTIC-OWNED-COMMAND-CLEANUP=' +
                json.dumps(dict(schema='arctic-paired-owned-command-cleanup-v1', release_acceptance=False,
                    child_acquired=process is not None, failure_type=type(failure).__name__,
                    cleanup_errors=list(errors), deferred_signals=list(acquisition_signals) + list(cleanup_signals))) + '\n'))
            attempt('flush owned failure log', output.flush)

        with log.open('w') as output:
            try:
                # Own the Popen result before restoring a handler that can raise.
                with defer_signals() as acquisition_signals:
                    process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
                if acquisition_signals:
                    raise InterruptedError('Paired acceptance interrupted during owned child acquisition')
                code = process.wait(timeout=timeout)
                if code:
                    raise RuntimeError(f'{log}: harness exit {code}')
            except BaseException as error:
                failure = error
            finally:
                try:
                    with defer_signals() as cleanup_signals:
                        stop_owned()
                        remove_owned(output)
                        if cleanup_signals and failure is None:
                            failure = InterruptedError('Paired acceptance interrupted during owned cleanup')
                        if errors and failure is None:
                            failure = RuntimeError('Paired owned cleanup failed: ' + ', '.join(errors))
                        record_failure(output)
                except BaseException as error:
                    if failure is None:
                        failure = error
                # Include cancellation queued after the body's final check or
                # delivered when the old raising handler is restored at unmask.
                if cleanup_signals and failure is None:
                    failure = InterruptedError('Paired acceptance interrupted at owned cleanup boundary')
                if failure is not None:
                    with defer_signals():
                        record_failure(output)
        if failure is not None:
            raise failure

    def verify_toolchain(folder):
        nonlocal toolchain_sha
        current = sha256(folder / 'vm-toolchain.txt')
        if toolchain_sha is not None and current != toolchain_sha:
            raise RuntimeError('QEMU/firmware/tool inventory changed between stages')
        toolchain_sha = current
        state['vm_toolchain_sha256'] = current

    common = [str(ROOT / 'tools/test-install.sh'), '--kvm', '--memory', '4096', '--smp', '2',
              '--boot-append', '', '--collect-via', 'console']
    profiles = dict(baseline=ROOT/'tools/performance/fixtures/v1.2-offline.toml',
                    candidate=candidate_root/'profiles/ci/offline.toml')
    if sha256(profiles['baseline']) != BASELINE_PROFILE_SHA256:
        raise RuntimeError('Original baseline install profile changed')
    state['profiles'] = {name: dict(path=str(path), sha256=sha256(path)) for name, path in profiles.items()}
    pristine = {}
    try:
        save('prepare_immutable_vm_tools')
        execute(['bash', str(ROOT / 'tools/performance/prepare-vm-tools.sh'), str(args.out), state['task_id']],
                args.out / 'vm-tools-provision.log', 1200, provision=True)
        prepared_id = (args.out / 'vm-prepared-image-id.txt').read_text().strip()
        state['vm_prepared_image_id'] = prepared_id
        if external:
            state['vm_base_image_id'] = (args.out / 'vm-base-image-id.txt').read_text().strip()
        for name, image in images.items():
            require_idle_vm_host()
            save('offline_install_' + name)
            execute(common + ['--stage', 'install', '--iso', str(image), '--install-timeout', '2400',
                              '--profile', str(profiles[name]),
                              '--out', str(args.out / name)], args.out / (name + '-install-harness.log'), 3600, vm=True)
            verify_toolchain(args.out / name)
            if 'ARCTIC-PRISTINE-INSTALL-POWEROFF=clean' not in (args.out/(name+'-install-harness.log')).read_text():
                raise RuntimeError('Installed source did not cleanly power off; first-use snapshot refused')
            pristine[name] = {file: sha256(args.out/name/file) for file in ('target.qcow2', 'OVMF_VARS.fd')}
        state['pristine_installed_sources'] = pristine
        for number, name in paired_boot_order():
            require_idle_vm_host()
            save(f'{name}_boot_{number}')
            archive = args.out / 'runs' / name / str(number)
            archive.mkdir(parents=True, exist_ok=True)
            context = dict(image=name, boot=number, fresh_installed_overlay=True, collector='console',
                           installed_base_sha256=pristine[name]['target.qcow2'],
                           firmware_variables_sha256=pristine[name]['OVMF_VARS.fd'],
                           install_profile_sha256=state['profiles'][name]['sha256'],
                           iso_sha256=state['images'][name]['sha256'])
            if external:
                context.update(external_execution=external, context_id=uuid.uuid4().hex)
            context_path = archive/'performance-context.json'
            context_path.write_text(json.dumps(context, indent=2)+'\n')
            try:
                execute(common + ['--stage', 'boot', '--guest-check', str(probe),
                        '--profile', str(profiles[name]), '--fresh-boot-from', str(args.out/name),
                        '--performance-context', str(context_path), '--out', str(archive)],
                        archive / 'harness.log', 2400, vm=True)
                verify_toolchain(archive)
                if not 'ARCTIC-PERFORMANCE-CONSOLE-RESTORED' in (archive/'serial-boot.log').read_text(errors='replace'):
                    raise RuntimeError('No console-to-desktop VT restoration evidence')
            finally:
                # Per-boot output is already independent. Keep logs on failure,
                # but discard only this fresh overlay/data CD to bound disk use.
                for file in ('target.qcow2', 'data.iso'):
                    (archive/file).unlink(missing_ok=True)
            state['runs'].append(dict(image=name, boot=number, archive=str(archive), harness_exit=0))
        for name, expected in pristine.items():
            if {file: sha256(args.out/name/file) for file in expected} != expected:
                raise RuntimeError('Pristine installed source changed during measurement: '+name)
        if external:
            for name, path in images.items():
                if path.stat().st_size != state['images'][name]['bytes'] or sha256(path) != state['images'][name]['sha256']:
                    raise RuntimeError('Input ISO changed during measurement: ' + name)
            state['input_images_rechecked'] = True
            if {name: sha256(candidate_root / name) for name in candidate_sources} != candidate_sources:
                raise RuntimeError('Candidate image-source inputs changed during measurement')
        argv = [sys.executable, str(ROOT / 'tools/performance/compare.py'),
                '--candidate-commit', (args.candidate_source_sha[:7] if external else
                    subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, text=True).strip()),
                '--candidate-catalog-sha256', sha256(candidate_root / 'shell/AppsService.qml'),
                '--candidate-battery-sha256', sha256(candidate_root / 'shell/BatteryService.qml'), '--out', str(args.out / 'comparison.json')]
        for name in images:
            for number in range(1, 4):
                argv += ['--' + name + '-log', str(args.out / 'runs' / name / str(number) / 'serial-boot.log')]
        result = subprocess.run(argv, cwd=ROOT)
        save('complete_regression_gate_passed' if result.returncode == 0 else 'complete_regression_gate_failed')
        return result.returncode
    except Exception as error:
        state['error'] = str(error)
        save('blocked')
        raise
    finally:
        finalize_prepared_image(engine, args.out, state['task_id'], prepared_id, state, save)


if __name__ == '__main__':
    raise SystemExit(main())
