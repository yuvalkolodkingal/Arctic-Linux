#!/usr/bin/env python3
"""Mango's event-driven, global logical window rectangles for taskbar dodging.

Two persistent subscriptions, shared across outputs. Coalesce bursts for 60ms without
waiting for silence (continuous dragging must not starve updates), deduplicate the
geometry, and fail visible on malformed/disconnected IPC. No periodic queries/polling.
"""
import json
import math
import os
import selectors
import signal
import subprocess
import sys
import time


def rectangle(value):
    result = {key: value[key] for key in ('x', 'y', 'width', 'height')}
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
               for v in result.values()) or result['width'] <= 0 or result['height'] <= 0:
        raise ValueError('Invalid logical rectangle')
    return result


def normalize(monitors, clients):
    outputs = [{**rectangle(m), 'name': m['name']} for m in monitors]
    by_name = {m['name']: m for m in monitors}
    windows = []
    for c in clients:
        m = by_name.get(c.get('monitor'))
        if not m or m.get('hide_clients') or c.get('is_visible') is not True:
            continue
        if c.get('is_minimized') or c.get('is_swallowedby'):
            continue
        # Visibility is authoritative for scratchpads/sticky windows. Also guard a transient
        # workspace-change race between the monitor and client subscriptions.
        if not (c.get('is_global') or c.get('is_unglobal') or c.get('is_overlay')):
            if not set(c.get('tags', [])).intersection(m.get('active_tags', [])):
                continue
        box = rectangle(m if c.get('is_fullscreen') else c)
        windows.append(box)
    windows.sort(key=lambda box: (box['x'], box['y'], box['width'], box['height']))
    outputs.sort(key=lambda m: m['name'])
    return dict(ready=True, monitors=outputs, windows=windows)


def emit(data):
    print(json.dumps(data, separators=(',', ':')), flush=True)


def watch():
    selector = selectors.DefaultSelector()
    processes = []
    states = {}
    buffers = {}
    pending = None
    last = None
    try:
        for kind in ('all-monitors', 'all-clients'):
            p = subprocess.Popen(['mmsg', 'watch', kind], stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, bufsize=0)
            processes.append(p)
            selector.register(p.stdout, selectors.EVENT_READ, kind)
            buffers[kind] = b''
        while True:
            timeout = None if pending is None else max(0, pending - time.monotonic())
            for key, _ in selector.select(timeout):
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    raise RuntimeError('Mango geometry stream disconnected')
                kind = key.data
                buffers[kind] += chunk
                if len(buffers[kind]) > 4 * 1024 * 1024:
                    raise ValueError('Unbounded Mango stream')
                while b'\n' in buffers[kind]:
                    line, buffers[kind] = buffers[kind].split(b'\n', 1)
                    data = json.loads(line)
                    field = 'monitors' if kind == 'all-monitors' else 'clients'
                    if not isinstance(data.get(field), list):
                        raise ValueError('Invalid Mango stream')
                    states[kind] = data[field]
                    if pending is None:
                        pending = time.monotonic() + .06
            if pending is not None and time.monotonic() >= pending:
                pending = None
                if len(states) == 2:
                    data = normalize(states['all-monitors'], states['all-clients'])
                    if data != last:
                        emit(data)
                        last = data
    finally:
        selector.close()
        for p in processes:
            p.terminate()
        for p in processes:
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()


def main():
    if not os.environ.get('MANGO_INSTANCE_SIGNATURE'):
        emit(dict(ready=False, monitors=[], windows=[], error='Window geometry requires Mango'))
        return 2
    try:
        capability=subprocess.run(['mmsg','get','capabilities'],capture_output=True,text=True,timeout=4)
        if capability.returncode or json.loads(capability.stdout).get('client_geometry_events') is not True:
            emit(dict(ready=False, monitors=[], windows=[], error='Dodge windows needs the updated Mango package'))
            return 2
        watch()
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError):
        emit(dict(ready=False, monitors=[], windows=[], error='Window geometry unavailable'))
        return 1
    return 0


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    raise SystemExit(main())
