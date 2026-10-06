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
import resource
import statistics
import subprocess
import sys
import time


def run(argv, timeout=45):
    try:
        return subprocess.check_output(argv, text=True, stderr=subprocess.STDOUT,
                                       timeout=timeout).strip()
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f'Command exited {error.returncode}: {argv!r}\n{error.output[-12000:]}') from error


def emit(check, value):
    print('ARCTIC-PERFORMANCE ' + json.dumps(dict(stage=sys.argv[1], check=check, value=value)), flush=True)


def session_environment(proc_root, uid, runtime, display, base):
    """Keep login paths/session identity; obtain post-exec IPC from children.

    A terminal's shell can add its own XDG_DATA_DIRS. Requiring every child to
    agree would discard the desktop's Flatpak/Nix exports and report a false
    default browser. Keep the login's actual session identity and Qt backend.
    """
    fields = ('PATH', 'XDG_CONFIG_HOME', 'XDG_CONFIG_DIRS', 'XDG_DATA_HOME',
              'XDG_DATA_DIRS', 'XDG_CACHE_HOME', 'DISPLAY', 'XAUTHORITY',
              'XDG_SESSION_ID', 'XDG_SEAT', 'XDG_VTNR', 'XDG_CURRENT_DESKTOP',
              'XDG_SESSION_DESKTOP', 'DESKTOP_SESSION', 'LANG', 'GDK_BACKEND',
              'QT_QPA_PLATFORM', 'MANGO_SOCKET')
    inherited = {key: base[key] for key in fields if base.get(key)}
    signatures = set()
    children = []
    for child in proc_root.glob('[0-9]*'):
        try:
            if child.stat().st_uid != uid:
                continue
            env = dict(item.split('=', 1) for item in
                       (child/'environ').read_bytes().decode().split('\0') if '=' in item)
            if (env.get('XDG_RUNTIME_DIR') == str(runtime)
                    and env.get('WAYLAND_DISPLAY') == display
                    and env.get('MANGO_INSTANCE_SIGNATURE')):
                signatures.add(env['MANGO_INSTANCE_SIGNATURE'])
                children.append(env)
        except (OSError, UnicodeError):
            continue
    if len(signatures) != 1:
        raise RuntimeError(f'Expected one Mango IPC signature, found {len(signatures)}')
    # Xwayland's display can appear after Mango's exec. Portal/application Qt
    # and GTK backend overrides are not session settings: inheriting them can
    # change Quickshell's display identity and hide the live shell from IPC.
    for key in ('DISPLAY', 'XAUTHORITY'):
        if key not in inherited:
            values = {env[key] for env in children if env.get(key)}
            if len(values) == 1:
                inherited[key] = values.pop()
    inherited['MANGO_INSTANCE_SIGNATURE'] = signatures.pop()
    if not all(inherited.get(key) for key in ('PATH', 'XDG_DATA_DIRS', 'XDG_SESSION_ID')):
        raise RuntimeError('Missing actual desktop PATH, XDG_DATA_DIRS or session identity')
    return inherited


def desktop():
    for path in Path('/proc').glob('[0-9]*'):
        try:
            if (path / 'comm').read_text().strip() != 'mango' or path.stat().st_uid == 0:
                continue
            user = pwd.getpwuid(path.stat().st_uid)
            runtime = Path('/run/user') / str(user.pw_uid)
            sockets = [p for p in runtime.glob('wayland-*') if p.is_socket()]
            if len(sockets) != 1:
                continue
            base = dict(item.split('=', 1) for item in
                        (path/'environ').read_bytes().decode().split('\0') if '=' in item)
            inherited = session_environment(Path('/proc'), user.pw_uid, runtime, sockets[0].name, base)
            return ['runuser', '-u', user.pw_name, '--', 'env', '-i',
                    'HOME=' + user.pw_dir, 'XDG_RUNTIME_DIR=' + str(runtime),
                    'USER=' + user.pw_name, 'LOGNAME=' + user.pw_name,
                    'WAYLAND_DISPLAY=' + sockets[0].name, 'XDG_SESSION_TYPE=wayland',
                    'DBUS_SESSION_BUS_ADDRESS=unix:path=' + str(runtime/'bus'),
                    *[key + '=' + value for key, value in inherited.items()]]
        except (OSError, UnicodeError, KeyError):
            continue
    raise RuntimeError('No unique non-root Mango session')


def meminfo():
    memory = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        parts = value.split()
        if len(parts) == 2 and parts[1] == 'kB':
            memory[key] = int(parts[0]) * 1024
    return memory


def snapshot():
    memory = meminfo()
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


def startup(prefix, command, pattern, timeout=300, hold_seconds=5, observations=None):
    before = set(clients(prefix))
    started = time.monotonic()
    last_absent_start = started
    with open('/tmp/arctic-performance-apps.log', 'a') as output:
        child = subprocess.Popen(prefix + command, stdout=output, stderr=output)
        try:
            while time.monotonic() - started < timeout:
                query_started = time.monotonic()
                current = clients(prefix)
                windows = [c for key, c in current.items() if key not in before and
                           pattern in (str(c.get('appid', c.get('app_id', ''))) + ' ' + str(c.get('title', ''))).lower()]
                if windows:
                    measured = time.monotonic() - started
                    time.sleep(hold_seconds)
                    if not any(str(window['id']) in clients(prefix) for window in windows):
                        continue
                    if observations is not None:
                        observations.append(dict(lower_seconds=last_absent_start - started,
                                                 upper_seconds=measured,
                                                 interval_seconds=measured - (last_absent_start - started)))
                    emit('mapped_window_' + pattern, windows)
                    emit('app_workload_' + pattern, snapshot())
                    return measured
                last_absent_start = query_started
                time.sleep(.01)
                if child.poll() not in (None, 0):
                    break
            emit('startup_' + pattern + '_diagnostic', dict(exit_code=child.poll(),
                 clients=list(clients(prefix).values()),
                 launch_output=Path('/tmp/arctic-performance-apps.log').read_text(errors='replace')[-12000:]))
            raise RuntimeError(f'No persistent mapped {pattern} window within {timeout} s')
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


def measure(prefix):
    emit('identity', dict(kernel=run(['uname', '-r']), virtualization=run(['systemd-detect-virt', '--vm']),
                          sampler='cpu-30-pss-6-v5-native-backend', cpu=run(['lscpu']),
                          boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip()))
    emit('boot', dict(analyze=run(['systemd-analyze']),
                      uptime=Path('/proc/uptime').read_text().strip()))
    emit('security', run(['getenforce']))
    emit('installed_bytes', run(['du', '-sx', '-B1', '--exclude=/proc', '--exclude=/sys', '--exclude=/dev',
                                 '--exclude=/run', '--exclude=/tmp', '/'], timeout=300))
    emit('installed_allocation_scope', 'Root filesystem only (du -x); separate mounted trees excluded')
    allocations, devices = [], set()
    for path in ('/', '/boot', '/boot/efi', '/home', '/nix', '/var/log'):
        if not Path(path).is_dir() or (device := os.stat(path).st_dev) in devices:
            continue
        devices.add(device)
        allocations.append(dict(path=path, device=device, du_bytes=int(run([
            'du', '-sx', '-B1', '--exclude=/proc', '--exclude=/sys', '--exclude=/dev',
            '--exclude=/run', '--exclude=/tmp', path], timeout=300).split()[0])))
    emit('installed_mount_allocations', allocations)
    emit('installed_btrfs_usage', run(['btrfs', 'filesystem', 'usage', '--raw', '/'], timeout=120))
    # Let session initialization settle; record actual elapsed time and memory without flushing caches.
    time.sleep(60)
    samples = []
    for index in range(30):
        started = time.monotonic()
        usage = resource.getrusage(resource.RUSAGE_SELF)
        observer_before = usage.ru_utime + usage.ru_stime
        before, idle_before = cpu_ticks()
        # Full process PSS scans are expensive under software emulation. Sample them
        # six times; keep all 30 CPU/meminfo observations and expose observer cost.
        memory = snapshot() if index % 5 == 0 else dict(memory_bytes=meminfo(), observer_pid=os.getpid())
        memory['pss_measured'] = index % 5 == 0
        time.sleep(1)
        after, idle_after = cpu_ticks()
        elapsed = time.monotonic() - started
        usage = resource.getrusage(resource.RUSAGE_SELF)
        memory['observer_cpu_percent_one_core'] = 100 * (
            usage.ru_utime + usage.ru_stime - observer_before) / elapsed
        memory['sample_elapsed_seconds'] = elapsed
        memory['cpu_busy_percent'] = 100 * (1 - (idle_after - idle_before) / max(1, after - before))
        samples.append(memory)
    emit('idle_samples', samples)
    shell_path = run(prefix + ['arctic-shell', '--path'])
    emit('shell_path', shell_path)
    # Match the shipped helper's CLI order and selected shell directory.
    for label, command in [('fish', ['fish', '-ic', 'exit']), ('bash', ['bash', '-ic', 'exit']),
                           ('shell_ipc', ['quickshell', 'ipc', '-p', shell_path, 'call', 'bar', 'hidden'])]:
        times = []
        for _ in range(10):
            start = time.monotonic()
            run(prefix + command)
            times.append(time.monotonic() - start)
        emit(label + '_seconds', dict(samples=times, median=statistics.median(times), max=max(times)))
    for pattern, command in [('kitty', ['kitty']), ('org.gnome.nautilus', ['nautilus', '--new-window']),
                             ('zen', ['flatpak', 'run', 'app.zen_browser.zen', 'about:blank'])]:
        bounds = []
        samples = [startup(prefix, command, pattern, observations=bounds) for _ in range(3)]
        emit('startup_' + pattern + '_seconds', dict(first=samples[0], warm=samples[1:],
             observation_bounds=bounds, poll_sleep_seconds=.01))
    emit('final_idle', snapshot())
    emit('system_failed_units', run(['systemctl', '--failed', '--no-pager']))
    emit('flatpak', run(['flatpak', 'list', '--system', '--columns=ref,active,size']))
    # Enumerating the dependency graph can be very slow under TCG. A missing supplemental
    # graph must not discard the actual memory/window measurements or block an offline install.
    try:
        emit('critical_chain', run(['systemd-analyze', '--no-pager', 'critical-chain'], timeout=120))
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        emit('critical_chain_unmeasured', str(error))
    emit('done', True)


def main(preconditioned=False):
    if (Path(__file__).parent != Path('/run/t') or os.geteuid() != 0
            or run(['systemd-detect-virt', '--vm']) not in ('qemu', 'kvm')):
        raise RuntimeError('This probe requires root inside a disposable QEMU VM')
    prefix = desktop()
    awake = json.loads(run(prefix + ['arctic-keep-awake', 'status', '--json']))
    if awake.get('on'):
        raise RuntimeError('Start measurement with Keep awake off for identical conditions')
    # Slow emulated app launches can outlast the normal five-minute idle lock.
    # Use the shipped session-only feature, then restore it even if a probe fails.
    emit('measurement_conditions', dict(keep_awake_temporary=True, initial_keep_awake=awake))
    run(prefix + ['arctic-keep-awake', 'on', '--quiet'])
    try:
        if preconditioned:
            # Identical cache/profile preparation for both images. No cache
            # flushing, package/service tuning or preference changes.
            for pattern, command in [('kitty', ['kitty']), ('org.gnome.nautilus', ['nautilus', '--new-window']),
                                     ('zen', ['flatpak', 'run', 'app.zen_browser.zen', 'about:blank'])]:
                seconds = startup(prefix, command, pattern, hold_seconds=45)
                emit('precondition_' + pattern, dict(mapped_after_seconds=seconds, persistent_hold_seconds=45,
                     meaning='Cache/profile normalization only; not a cold startup benchmark'))
        emit('measured_payload', dict(
            arctic_shell=run(['rpm', '-q', 'arctic-shell']),
            catalog_sha256=run(['sha256sum', '/usr/share/arctic/shell/AppsService.qml']),
            battery_sha256=run(['sha256sum', '/usr/share/arctic/shell/BatteryService.qml']),
            mangowm=run(['rpm', '-q', 'mangowm']),
            quickshell=run(['rpm', '-q', 'quickshell']),
            kitty=run(['rpm', '-q', 'kitty'])))
        measure(prefix)
    finally:
        emit('keep_awake_restored', json.loads(run(prefix + ['arctic-keep-awake', 'off', '--quiet'])))


if __name__ == '__main__':
    main()
