#!/usr/bin/env python3
"""Reproducible measurements, ONLY in a disposable QEMU guest.

Use with tools/test-install.sh --guest-check tools/performance/guest.py.
Never drops caches, changes services, removes packages, or alters kernel knobs.
The observer's allocations are included and identified in process snapshots.
"""
import json
import os
from pathlib import Path
import pwd
import statistics
import subprocess
import sys
import time


def run(argv, timeout=45):
    return subprocess.check_output(argv, text=True, stderr=subprocess.STDOUT,
                                   timeout=timeout).strip()


def emit(check, value):
    print('ARCTIC-PERFORMANCE ' + json.dumps(dict(stage=sys.argv[1], check=check, value=value)), flush=True)


def desktop():
    for path in Path('/proc').glob('[0-9]*'):
        try:
            if (path / 'comm').read_text().strip() != 'mango' or path.stat().st_uid == 0:
                continue
            user = pwd.getpwuid(path.stat().st_uid)
            runtime = Path('/run/user') / str(user.pw_uid)
            sockets = [p for p in runtime.glob('wayland-*') if p.is_socket()]
            signatures = set()
            for child in Path('/proc').glob('[0-9]*'):
                try:
                    if child.stat().st_uid != user.pw_uid:
                        continue
                    env = dict(item.split('=', 1) for item in (child/'environ').read_bytes().decode().split('\0') if '=' in item)
                    if env.get('XDG_RUNTIME_DIR') == str(runtime) and env.get('MANGO_INSTANCE_SIGNATURE'):
                        signatures.add(env['MANGO_INSTANCE_SIGNATURE'])
                except (OSError, UnicodeError):
                    continue
            if len(sockets) != 1 or len(signatures) != 1:
                continue
            return ['runuser', '-u', user.pw_name, '--', 'env',
                    'HOME=' + user.pw_dir, 'XDG_RUNTIME_DIR=' + str(runtime),
                    'WAYLAND_DISPLAY=' + sockets[0].name, 'XDG_SESSION_TYPE=wayland',
                    'DBUS_SESSION_BUS_ADDRESS=unix:path=' + str(runtime/'bus'),
                    'MANGO_INSTANCE_SIGNATURE=' + signatures.pop()]
        except (OSError, UnicodeError, KeyError):
            continue
    raise RuntimeError('No unique non-root Mango session')


def snapshot():
    memory = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        memory[key] = int(value.split()[0]) * 1024
    processes = []
    skipped = []
    for path in Path('/proc').glob('[0-9]*'):
        try:
            values = {}
            for line in (path/'smaps_rollup').read_text().splitlines()[1:]:
                key, value = line.split(':', 1)
                values[key] = int(value.split()[0]) * 1024
            processes.append(dict(pid=int(path.name), name=(path/'comm').read_text().strip(),
                                  pss_bytes=values.get('Pss', 0),
                                  private_bytes=values.get('Private_Clean', 0) + values.get('Private_Dirty', 0)))
        except (OSError, ValueError):
            skipped.append(int(path.name))
    return dict(memory_bytes=memory, process_pss_bytes=sum(p['pss_bytes'] for p in processes),
                process_private_bytes=sum(p['private_bytes'] for p in processes),
                top_processes=sorted(processes, key=lambda p: p['pss_bytes'], reverse=True)[:30],
                observer_pid=os.getpid(), skipped_pids=skipped)


def cpu_ticks():
    values = list(map(int, Path('/proc/stat').read_text().splitlines()[0].split()[1:9]))
    return sum(values), values[3] + values[4]


def clients(prefix):
    return {str(c['id']): c for c in json.loads(run(prefix + ['mmsg', 'get', 'all-clients']))['clients']}


def startup(prefix, command, pattern):
    before = set(clients(prefix))
    started = time.monotonic()
    with open('/tmp/arctic-performance-apps.log', 'a') as output:
        child = subprocess.Popen(prefix + command, stdout=output, stderr=output)
        try:
            while time.monotonic() - started < 120:
                current = clients(prefix)
                windows = [c for key, c in current.items() if key not in before and
                           pattern in str(c.get('appid', c.get('app_id', ''))).lower()]
                if windows:
                    measured = time.monotonic() - started
                    time.sleep(5)
                    emit('app_workload_' + pattern, snapshot())
                    return measured
                time.sleep(.25)
            raise RuntimeError(f'No mapped {pattern} window within 120 s')
        finally:
            # Close the newly launched window using the compositor, not system-wide pkill.
            current = clients(prefix)
            for key in set(current) - before:
                subprocess.run(prefix + ['mmsg', 'dispatch', 'killclient', 'client,' + key],
                               capture_output=True, timeout=15)
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()


def main():
    if os.geteuid() != 0 or run(['systemd-detect-virt', '--vm']) != 'qemu':
        raise RuntimeError('This probe requires root inside a disposable QEMU VM')
    prefix = desktop()
    emit('identity', dict(kernel=run(['uname', '-r']), virtualization='qemu',
                          cpu=run(['lscpu']), boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip()))
    emit('boot', dict(analyze=run(['systemd-analyze']),
                      uptime=Path('/proc/uptime').read_text().strip()))
    emit('security', run(['getenforce']))
    emit('installed_bytes', run(['du', '-sx', '-B1', '--exclude=/proc', '--exclude=/sys', '--exclude=/dev',
                                 '--exclude=/run', '--exclude=/tmp', '/']))
    # Let session initialization settle; record actual elapsed time and memory without flushing caches.
    time.sleep(60)
    samples = []
    for index in range(30):
        before, idle_before = cpu_ticks()
        memory = snapshot()
        time.sleep(1)
        after, idle_after = cpu_ticks()
        memory['cpu_busy_percent'] = 100 * (1 - (idle_after - idle_before) / max(1, after - before))
        samples.append(memory)
    emit('idle_samples', samples)
    for label, command in [('fish', ['fish', '-ic', 'exit']), ('bash', ['bash', '-ic', 'exit']),
                           ('shell_ipc', ['quickshell', '-p', '/usr/share/arctic/shell', 'ipc', 'call', 'bar', 'hidden'])]:
        times = []
        for _ in range(10):
            start = time.monotonic()
            run(prefix + command)
            times.append(time.monotonic() - start)
        emit(label + '_seconds', dict(samples=times, median=statistics.median(times), max=max(times)))
    for pattern, command in [('kitty', ['kitty']), ('org.gnome.nautilus', ['nautilus', '--new-window']),
                             ('zen', ['flatpak', 'run', 'app.zen_browser.zen', 'about:blank'])]:
        samples = [startup(prefix, command, pattern) for _ in range(3)]
        emit('startup_' + pattern + '_seconds', dict(first=samples[0], warm=samples[1:]))
    emit('final_idle', snapshot())
    emit('system_failed_units', run(['systemctl', '--failed', '--no-pager']))
    emit('flatpak', run(['flatpak', 'list', '--system', '--columns=ref,active,size']))
    # Enumerating the dependency graph can be very slow under TCG. A missing supplemental
    # graph must not discard the actual memory/window measurements or block an offline install.
    try:
        emit('critical_chain', run(['systemd-analyze', '--no-pager', 'critical-chain'], timeout=120))
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        emit('critical_chain_unmeasured', str(error))
    emit('done', True)


if __name__ == '__main__':
    main()
