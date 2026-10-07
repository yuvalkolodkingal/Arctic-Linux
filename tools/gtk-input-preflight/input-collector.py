#!/usr/bin/env python3
"""Explicit new input collector: copied owned-stream primitive, debug stderr allowed."""
import hashlib,json,os,selectors,signal,subprocess,time
from pathlib import Path
SCAN_BYTES=65536
DEADLINE_SECONDS=30


def require(value, message):
    if not value:
        raise RuntimeError(message)


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def run_input_stream(argv, callback, meta_path, *, timeout=DEADLINE_SECONDS,
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
