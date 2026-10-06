#!/usr/bin/env python3
"""Finite, complete interval scan for this disposable diagnostic; no policy changes."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import time

SCAN_BYTES = 16 * 1024 * 1024
SCAN_RECORDS = 8192
RECORD_BYTES = 256 * 1024
PRESERVE_BYTES = 8 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
AUDIT_BYTES = 4 * 1024 * 1024
DEADLINE_SECONDS = 60
SMALL_COMMAND_BYTES = 3 * 1024 * 1024
SMALL_COMMAND_COUNT = 14
AVC = re.compile(r'avc:\s*denied|type=(?:USER_)?AVC\b', re.I)


def require(value, message):
    if not value:
        raise RuntimeError(message)


def strict_json(data):
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    def invalid(value):
        raise RuntimeError('non-finite JSON constant: ' + value)
    return json.loads(data.decode('utf-8', errors='strict'), object_pairs_hook=pairs, parse_constant=invalid)


def message_values(value):
    """journalctl --all JSON strings, binary octets, or repeated values; no coercion."""
    if isinstance(value, str):
        return [value]
    require(isinstance(value, list) and value, 'journal MESSAGE missing/null/ambiguous representation')
    if all(type(item) is int for item in value):
        require(all(0 <= item <= 255 for item in value), 'journal MESSAGE invalid binary octet')
        return [bytes(value).decode('utf-8', errors='strict')]
    result = []
    for item in value:
        require(isinstance(item, str) or (isinstance(item, list) and item and
                all(type(part) is int and 0 <= part <= 255 for part in item)),
                'journal MESSAGE mixed/malformed repeated representation')
        result.extend([item] if isinstance(item,str) else [bytes(item).decode('utf-8',errors='strict')])
    return result


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def run_stream(argv, callback, meta_path, *, timeout=DEADLINE_SECONDS,
               limit=SCAN_BYTES, stderr_limit=64*1024, finish_callback=None):
    """Hash/count every observed byte; incomplete state survives any collector failure."""
    need_unused = [meta_path, meta_path.with_suffix('.stderr.log')]
    require(not any(p.exists() for p in need_unused), 'command evidence must be unused')
    record = dict(argv=list(argv), complete=False, timeout_seconds=timeout,
                  stdout_bound_bytes=limit, stderr_bound_bytes=stderr_limit,
                  stdout_observed_bytes=0, stderr_observed_bytes=0,
                  monotonic_start_seconds=time.monotonic(), exit_status=None,
                  timed_out=False, error=None, only_owned_child_reaped=False)
    save(meta_path, record)
    child = selector = descriptor = None
    hashes = {name:hashlib.sha256() for name in ('stdout', 'stderr')}
    stderr = bytearray()
    failure = None
    def retire(sig):
        if child is None or child.poll() is not None:
            return
        try:
            if descriptor is None:
                child.send_signal(sig)  # Direct unreaped child, never a searched PID.
            else:
                signal.pidfd_send_signal(descriptor, sig)
        except ProcessLookupError:
            pass
    try:
        child = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        record['child_pid'] = child.pid
        descriptor = os.pidfd_open(child.pid)
        selector = selectors.DefaultSelector()
        for name, stream in (('stdout', child.stdout), ('stderr', child.stderr)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        while selector.get_map():
            if time.monotonic() - record['monotonic_start_seconds'] > timeout:
                record['timed_out'] = True
                raise RuntimeError('security command deadline exceeded')
            for key, _ in selector.select(.1):
                data = os.read(key.fd, 32768)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                name = key.data
                record[name + '_observed_bytes'] += len(data)
                hashes[name].update(data)
                bound = limit if name == 'stdout' else stderr_limit
                require(record[name + '_observed_bytes'] <= bound,
                        'security command ' + name + ' byte bound exceeded')
                if name == 'stdout':
                    callback(data)
                else:
                    stderr.extend(data)
        require(time.monotonic()-record['monotonic_start_seconds'] <= timeout,
                'security command deadline exceeded before wait')
        record['exit_status'] = child.wait(timeout=max(.01, timeout-(time.monotonic()-record['monotonic_start_seconds'])))
        require(record['exit_status'] == 0, 'security command returned nonzero')
        require(not stderr, 'security command stderr is nonempty; cursor/output validity unproved')
        if finish_callback is not None:
            finish_callback()
        record['complete'] = True
    except BaseException as exc:
        failure = exc
        record['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        try:
            retire(signal.SIGTERM)
            if child is not None:
                try:
                    record['exit_status'] = child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    retire(signal.SIGKILL)
                    record['exit_status'] = child.wait(timeout=3)
                record['only_owned_child_reaped'] = True
        except BaseException as exc:
            record['complete'] = False
            record['error'] = (record['error'] or '') + '; owned cleanup: ' + str(exc)
            failure = failure or exc
        finally:
            if child is not None:
                child.stdout.close(); child.stderr.close()
            if selector is not None:
                selector.close()
            if descriptor is not None:
                os.close(descriptor)
            meta_path.with_suffix('.stderr.log').write_bytes(stderr)
            record.update(monotonic_end_seconds=time.monotonic(),
                          stdout_observed_sha256=hashes['stdout'].hexdigest(),
                          stderr_observed_sha256=hashes['stderr'].hexdigest(),
                          stderr_retained_bytes=len(stderr))
            save(meta_path, record)
    if failure is not None:
        raise failure
    return record


class JournalScan:
    def __init__(self, root, boot, end_cursor, start_cursor=None):
        self.root, self.boot, self.end_cursor = root, boot, end_cursor
        self.pending = bytearray()
        self.records = self.trusted = self.denials = self.retained = 0
        self.seen_end = False
        self.last_cursor = None
        self.denial_messages = []
        self.parts = []
        self.part = None
        self.part_bytes = 0
        self.complete = False
        self.start_cursor = start_cursor
        self.cursors = set()
        self.no_new_records = False

    def preserve(self, line):
        require(self.retained + len(line) <= PRESERVE_BYTES,
                'complete trusted/denial preservation byte bound exceeded')
        if self.part is None or self.part_bytes + len(line) > CHUNK_BYTES:
            self.close_part()
            path = self.root / ('trusted-or-denial-%02d.log' % len(self.parts))
            self.parts.append(dict(path=path.name, bytes=0))
            self.part = path.open('xb')
            self.part_bytes = 0
        self.part.write(line)
        self.part_bytes += len(line)
        self.retained += len(line)
        self.parts[-1]['bytes'] = self.part_bytes

    def close_part(self):
        if self.part is not None:
            self.part.close()
            path = self.root / self.parts[-1]['path']
            self.parts[-1]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            self.part = None

    def feed(self, data):
        self.pending.extend(data)
        while b'\n' in self.pending:
            line, _, remainder = self.pending.partition(b'\n')
            self.pending[:] = remainder
            require(len(line) + 1 <= RECORD_BYTES, 'journal newline record exceeds bound')
            value = strict_json(line)
            require(isinstance(value, dict) and value.get('_BOOT_ID') == self.boot,
                    'journal record missing/current-boot identity differs')
            cursor = value.get('__CURSOR')
            require(isinstance(cursor, str) and 0 < len(cursor) <= 4096 and '\x00' not in cursor,
                    'journal record cursor unavailable')
            require(cursor != self.start_cursor and cursor not in self.cursors,
                    'journal cursor repeated or includes excluded initial cursor')
            self.cursors.add(cursor)
            self.records += 1
            require(self.records <= SCAN_RECORDS, 'journal record count bound exceeded')
            self.last_cursor = cursor
            self.seen_end |= cursor == self.end_cursor
            transport = value.get('_TRANSPORT')
            require(isinstance(transport, str), 'journal trusted transport metadata unavailable')
            trusted = transport in ('audit', 'kernel')
            messages = message_values(value.get('MESSAGE'))
            matched = [message for message in messages if AVC.search(message)]
            denied = bool(matched)
            self.trusted += trusted
            self.denials += denied
            if denied:
                self.denial_messages.extend(matched)
            if trusted or denied:
                self.preserve(bytes(line) + b'\n')
        require(len(self.pending) < RECORD_BYTES, 'journal pending newline record exceeds bound')

    def finish(self, no_new_records=False):
        require(not self.pending, 'journal ended with partial newline record')
        require(self.seen_end or (no_new_records and self.records == 0),
                'journal did not include fixed interval end cursor')
        self.complete = True
        self.no_new_records = no_new_records and self.records == 0

    def report(self):
        self.close_part()
        return dict(complete=self.complete, observed_records=self.records,
                    start_cursor=self.start_cursor,end_cursor=self.end_cursor,no_new_records=self.no_new_records,
                    trusted_kernel_audit_records=self.trusted, matching_denial_records=self.denials,
                    retained_bytes=self.retained, unfinished_record_bytes=len(self.pending),
                    fixed_end_cursor_seen=self.seen_end, last_cursor=self.last_cursor, parts=self.parts,
                    limits=dict(scan_bytes=SCAN_BYTES, records=SCAN_RECORDS, newline_record_bytes=RECORD_BYTES,
                                retained_trusted_or_denial_bytes=PRESERVE_BYTES, chunk_bytes=CHUNK_BYTES))


class SecurityInterval:
    def __init__(self, native, root, *, audit_file=Path('/var/log/audit/audit.log'), boot_file=Path('/proc/sys/kernel/random/boot_id')):
        self.native, self.root, self.audit_file = native, root, audit_file
        require(not root.exists(), 'security evidence output must be unused')
        root.mkdir()
        self.states = []
        self.boot = boot_file.read_text().strip().replace('-', '')
        require(re.fullmatch('[0-9a-f]{32}', self.boot), 'actual current boot ID unavailable')
        self.audit_offset = self.audit_identity()
        self.before = self.state()
        self.cursor = self.tail('start')
        self.scan = None
        self.failure = None

    def small(self, argv, name):
        data = bytearray()
        try:
            record = run_stream(argv, data.extend, self.root / (name + '.json'), timeout=15, limit=64*1024)
        finally:
            # Consolidate only new command framing. Raw bytes remain reversible and
            # command errors/counters survive; inherited transport limits are unchanged.
            meta = self.root / (name + '.json')
            stderr = meta.with_suffix('.stderr.log')
            if meta.is_file() and stderr.is_file():
                path = self.root / 'small-commands.log'
                prior = path.read_bytes() if path.exists() else b''
                require(prior.count(b'\n') < SMALL_COMMAND_COUNT, 'small security command count exceeded')
                line = json.dumps(dict(name=name, command=strict_json(meta.read_bytes()),
                    stdout_base64=base64.b64encode(data).decode('ascii'),
                    stderr_base64=base64.b64encode(stderr.read_bytes()).decode('ascii')),
                    sort_keys=True, separators=(',', ':')).encode() + b'\n'
                require(len(prior) + len(line) <= SMALL_COMMAND_BYTES, 'small security command framing byte bound exceeded')
                with path.open('ab') as stream:
                    stream.write(line)
                meta.unlink(); stderr.unlink()
        return bytes(data), record

    def state(self):
        index = len(self.states)
        enforcing, first = self.small(['getenforce'], 'state-%02d-selinux' % index)
        audit, second = self.small(['auditctl', '-s'], 'state-%02d-audit' % index)
        value = dict(selinux=enforcing.decode('utf-8', errors='strict').strip(),
                     audit=self.native.parse_audit_status(audit.decode('utf-8', errors='strict')),
                     commands=[first, second], monotonic_seconds=time.monotonic())
        self.states.append(value)
        save(self.root / 'states.json', self.states)
        return value

    def tail(self, name):
        data, record = self.small(['journalctl', '-b', '--no-pager', '--all', '-n', '1', '-o', 'json'], name + '-cursor')
        require(data.endswith(b'\n') and data.count(b'\n') == 1, 'journal cursor framing unavailable')
        value = strict_json(data[:-1])
        require(value.get('_BOOT_ID') == self.boot and isinstance(value.get('__CURSOR'), str)
                and value['__CURSOR'] and '\x00' not in value['__CURSOR'], 'journal cursor/current boot unavailable')
        return value['__CURSOR']

    def audit_identity(self):
        try:
            info = self.audit_file.lstat()
        except FileNotFoundError:
            return None
        require(stat.S_ISREG(info.st_mode), 'audit log is not a regular file')
        return dict(device=info.st_dev, inode=info.st_ino, offset=info.st_size)

    def audit_interval(self):
        after = self.audit_identity()
        record = dict(complete=False, before=self.audit_offset, after=after, bytes=0,
                      limit_bytes=AUDIT_BYTES, observed_matching_denials=0)
        save(self.root / 'audit-interval.json', record)
        try:
            if after is None:
                require(self.audit_offset is None, 'audit log disappeared')
                record.update(complete=True, scope='audit log absent throughout; complete trusted journal scan remains mandatory')
                return ''
            offset = self.audit_offset['offset'] if self.audit_offset else 0
            require(self.audit_offset is None or (after['device'], after['inode']) ==
                    (self.audit_offset['device'], self.audit_offset['inode']), 'audit log rotated')
            require(after['offset'] >= offset, 'audit log truncated')
            count = after['offset'] - offset
            record['bytes'] = count
            require(count <= AUDIT_BYTES, 'complete audit-file interval byte bound exceeded')
            with self.audit_file.open('rb') as stream:
                info = os.fstat(stream.fileno())
                require((info.st_dev, info.st_ino, info.st_size) == (after['device'], after['inode'], after['offset']),
                        'audit log changed before interval read')
                stream.seek(offset)
                data = stream.read(count)
                final = os.fstat(stream.fileno())
                require(len(data) == count and (final.st_dev, final.st_ino, final.st_size) ==
                        (info.st_dev, info.st_ino, info.st_size), 'audit log changed during interval read')
            require(not data or data.endswith(b'\n'), 'audit interval ended with partial record')
            require(self.audit_identity() == after, 'audit path changed after interval read')
            (self.root / 'audit-interval.log').write_bytes(data)
            text = data.decode('utf-8', errors='replace')  # Same denial semantics as frozen native library.
            record.update(complete=True, sha256=hashlib.sha256(data).hexdigest(),
                          observed_matching_denials=sum(bool(AVC.search(line)) for line in text.splitlines()))
            return text
        except BaseException as exc:
            record['error'] = type(exc).__name__ + ': ' + str(exc)
            raise
        finally:
            save(self.root / 'audit-interval.json', record)

    def finish(self):
        try:
            after = self.state()  # Raw state evidence survives later scan failure.
            end = self.tail('end')
            self.scan = JournalScan(self.root, self.boot, end, self.cursor)
            run_stream(['journalctl', '-b', '--no-pager', '--all', '--after-cursor', self.cursor, '-o', 'json'],
                       self.scan.feed, self.root / 'whole-interval-command.json',
                       finish_callback=lambda:self.scan.finish(no_new_records=end == self.cursor))
            audit_text = self.audit_interval()
            value = self.native.verify_security(self.before, after, '\n'.join(self.scan.denial_messages) + '\n' + audit_text)
            value.update(complete=True, states=self.states, journal=self.scan.report(),
                         scope='complete current-boot after-cursor journal scan; all trusted audit/kernel and any denial raw records preserved; exact audit-file interval')
            save(self.root / 'security-report.json', value)
            return value
        except BaseException as exc:
            self.failure = type(exc).__name__ + ': ' + str(exc)
            save(self.root / 'security-report.json', self.failed(self.failure))
            raise

    def failed(self, error):
        return dict(complete=False, error=error, states=self.states,
                    journal=self.scan.report() if self.scan else None,
                    observed_new_avcs=None, scope='incomplete interval; never zero-AVC or Enforcing acceptance')
