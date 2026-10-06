#!/usr/bin/env python3
"""Drain one owned diagnostic child's raw streams, failing above combined 2 MiB."""
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time


def run_owned(root, argv, *, limit=2*1024*1024, deadline=180):
    outputs = {'stdout':root/'pcmanfm-stdout.log','stderr':root/'pcmanfm-wayland-stderr.log'}
    error = root/'pcmanfm-wayland-error.json'
    if any(p.exists() for p in (*outputs.values(),error)):
        raise RuntimeError('Wayland evidence must be unused')
    child = None; descriptor = None; sel = None; failed = None; count = 0; result = 74
    saved_handlers = {}; targets = {}; caught = None
    def send(sig):
        if child is None or child.poll() is not None:
            return
        try:
            if descriptor is not None:
                signal.pidfd_send_signal(descriptor,sig)
            else:
                # Only our direct unreaped child is signalled, never a searched PID.
                child.send_signal(sig)
        except ProcessLookupError:
            pass
    try:
        child = subprocess.Popen(argv, env=dict(os.environ, WAYLAND_DEBUG='client'),
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        descriptor = os.pidfd_open(child.pid)
        sel = selectors.DefaultSelector()
        for name,stream in (('stdout',child.stdout),('stderr',child.stderr)):
            targets[name] = outputs[name].open('xb')
            os.set_blocking(stream.fileno(),False); sel.register(stream,selectors.EVENT_READ,data=name)
        started = time.monotonic()
        def interrupted(signum, _):
            nonlocal failed
            failed = 'owned wrapper interrupted by signal '+str(signum)
            send(signal.SIGTERM)
        for sig in (signal.SIGTERM, signal.SIGINT):
            saved_handlers[sig] = signal.getsignal(sig); signal.signal(sig, interrupted)
        while sel.get_map():
            if time.monotonic()-started > deadline:
                failed = 'owned Wayland child exceeded deadline'
            if failed:
                break
            for key,_ in sel.select(.2):
                data = os.read(key.fd,65536)
                if not data:
                    sel.unregister(key.fileobj);continue
                count += len(data)
                if count > limit:
                    failed = 'combined Wayland/stdout log exceeded 2 MiB; required evidence incomplete'
                    break
                targets[key.data].write(data)
        if failed:
            send(signal.SIGTERM)
        try: result = child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            failed = failed or 'owned child failed to retire after stream completion'
            send(signal.SIGKILL);result=child.wait(timeout=3)
    except BaseException as exc:
        failed = type(exc).__name__+': '+str(exc); caught = exc
    finally:
        # Setup and preservation failures must still reap only the direct owned child.
        try:
            send(signal.SIGTERM)
            if child is not None:
                try: child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    send(signal.SIGKILL);child.wait(timeout=3)
        except BaseException as exc:
            failed = (failed+'; ' if failed else '')+'owned cleanup: '+str(exc)
            caught = caught or exc
        finally:
            for stream in ((child.stdout,child.stderr) if child is not None else ()):
                if stream is not None: stream.close()
            if sel is not None: sel.close()
            if descriptor is not None: os.close(descriptor)
            for stream in targets.values(): stream.close()
            for sig, handler in saved_handlers.items(): signal.signal(sig,handler)
        if failed:
            error.write_text(json.dumps(dict(error=failed, bytes_observed=count, preservation_complete=False,
                streams={name:path.name for name,path in outputs.items()},combined_limit_bytes=limit)))
    if caught is not None:
        raise caught
    return 74 if failed else result


def main():
    if len(sys.argv) != 2 or os.geteuid() == 0:
        raise RuntimeError('requires owned evidence directory as desktop UID')
    root = Path(sys.argv[1])
    if not root.is_dir() or root.is_symlink() or root.stat().st_uid != os.getuid():
        raise RuntimeError('unproved diagnostic evidence directory')
    return run_owned(root,['/usr/bin/arctic-open', 'files'])


if __name__ == '__main__':
    raise SystemExit(main())
