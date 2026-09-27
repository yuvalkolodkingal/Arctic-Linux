#!/usr/bin/env python3
"""Event-driven workspace bridge for Mango and Hyprland."""
import argparse
import json
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import time


def run(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=4)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'Workspace command failed')
    return result.stdout


def hypr_instance():
    instances = json.loads(run(['hyprctl', 'instances', '-j']))
    display = os.environ.get('WAYLAND_DISPLAY', '')
    return next(item['instance'] for item in instances if item.get('wl_socket') == display)


def normalize_mango(data, monitor):
    output = next((item for item in data.get('all_tags', []) if item.get('monitor') == monitor), None)
    if output is None:
        return []
    return [dict(id=tag['index'], label=str(tag['index']), active=tag['is_active'], occupied=tag['client_count'] > 0, urgent=tag['is_urgent']) for tag in output['tags']]


def emit(rows, error=''):
    print(json.dumps(dict(workspaces=rows, error=error)), flush=True)


def mango_watch(monitor):
    process = subprocess.Popen(['mmsg', 'watch', 'all-tags'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        for line in process.stdout:
            data = json.loads(line)
            emit(normalize_mango(data, monitor))
    finally:
        process.terminate()
        process.wait(timeout=3)


def hypr_watch(monitor, instance):
    directory = Path(os.environ['XDG_RUNTIME_DIR'])/'hypr'/instance
    events = socket.socket(socket.AF_UNIX)
    events.connect(str(directory/'.socket2.sock'))
    def snapshot():
        monitors = json.loads(run(['hyprctl','-i',instance,'monitors','-j']))
        workspaces = json.loads(run(['hyprctl','-i',instance,'workspaces','-j']))
        current = next((m['activeWorkspace']['id'] for m in monitors if m['name'] == monitor), None)
        entries = {w['id']: w for w in workspaces if w['id'] >= 0 and w.get('monitor') == monitor}
        ids = sorted(set(range(1, 10)) | set(entries))
        emit([dict(id=i, label=entries.get(i,{}).get('name',str(i)), active=i==current, occupied=entries.get(i,{}).get('windows',0)>0, urgent=False) for i in ids])
    snapshot()
    while True:
        if not events.recv(65536):
            break
        # Coalesce one burst of window/workspace events without periodic polling.
        until = time.monotonic() + 0.06
        while select.select([events],[],[],max(0,until-time.monotonic()))[0]:
            if not events.recv(65536):
                return
            if time.monotonic() >= until:
                break
        snapshot()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['watch','switch'])
    parser.add_argument('monitor')
    parser.add_argument('workspace', nargs='?', type=int)
    args = parser.parse_args()
    mango = bool(os.environ.get('MANGO_INSTANCE_SIGNATURE'))
    if args.mode == 'switch':
        if args.workspace is None or args.workspace < 0:
            raise ValueError('Invalid workspace')
        if mango:
            for command in ('focusmon,'+args.monitor, f'view,{args.workspace},0'):
                response = json.loads(run(['mmsg','dispatch',command]))
                if not response.get('success'):
                    raise RuntimeError('Mango rejected workspace switch')
        else:
            instance = hypr_instance()
            run(['hyprctl','-i',instance,'dispatch',f'hl.dsp.focus({{ workspace = {args.workspace} }})'])
    elif mango:
        mango_watch(args.monitor)
    else:
        hypr_watch(args.monitor, hypr_instance())

if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: exit(0))
    try:
        main()
    except (OSError, ValueError, RuntimeError, StopIteration, subprocess.SubprocessError):
        emit([], 'Workspace connection unavailable')
        raise SystemExit(1)
