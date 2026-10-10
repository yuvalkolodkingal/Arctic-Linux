#!/usr/bin/env python3
"""Read-only Safe rendering observation in one authenticated disposable guest."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import signal
import stat
import subprocess
import sys
import time


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = Path('/run/t')
c = load('safe_common', BASE / 'common.py')


def bounded(argv, timeout=20, limit=1024**2):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    c.require(result.returncode == 0 and len(result.stdout) + len(result.stderr) <= limit,
              'Guest observation command failed or exceeded bound')
    return result.stdout.decode().strip()


_guest_phase = 'entry'
_guest_context = None
_guest_primary = None


def _stage(phase):
    global _guest_phase
    c.require(phase in c.GUEST_PHASES, 'Guest source phase differs')
    _guest_phase = phase


def _observed(phase, action):
    _stage(phase)
    return action()


def _emit_status(phase, status, error):
    if _guest_context is None:
        return False
    try:
        value = c.guest_status(phase, status, error, _guest_context)
        print(c.GUEST_STATUS_PREFIX + json.dumps(value, sort_keys=True, allow_nan=False), flush=True)
        return True
    except Exception:
        # A reporting failure cannot replace the primary failure or publish text.
        return False


def execute():
    global _guest_phase, _guest_context, _guest_primary
    _guest_phase, _guest_context, _guest_primary = 'entry', None, None
    try:
        main()
    except Exception as error:
        phase, klass = _guest_primary or (_guest_phase, c.guest_exception_class(error))
        _emit_status(phase, 'exception', klass)
        try:
            print('ARCTIC-SAFE-DIAGNOSTIC-FAILED', flush=True)
        except Exception:
            pass
        return 1
    return 0 if _emit_status('complete', 'completed', None) else 1


def main():
    global _guest_context, _guest_primary
    _stage('entry')
    c.require(sys.argv[1:] == ['--disposable-guest'] and Path(__file__).resolve() == BASE / 'guest.py'
              and os.geteuid() == 0, 'Protected disposable guest entry required')
    _stage('context')
    runtime = load('safe_transport', BASE / 'taskbar-runtime.py')
    screen = load('safe_privacy', BASE / 'screen-evidence.py')
    ctx = c.context(c.strict(runtime.read_regular(BASE / 'context.json', root_owned=True)))
    _guest_context = ctx
    _stage('bundle')
    for name, expected in ctx['bundle'].items():
        raw = runtime.read_regular(BASE / name, root_owned=True)
        c.require(hashlib.sha256(raw).hexdigest() == expected, 'Protected guest bundle hash differs')
    _stage('native-import')
    native = load('safe_native', BASE / 'native_smoke.py')
    _stage('native-guard')
    native.guest_guard('live', True)
    _stage('boot-flags')
    tokens = Path('/proc/cmdline').read_text().strip().split()
    c.require('nomodeset' in tokens and 'arctic.mode=try' in tokens,
              'Requires original Safe Try boot flags')
    _stage('desktop-discovery')
    prefix = native.discover_desktop()
    _stage('mango-identity')
    mangos = []
    for p in Path('/proc').glob('[0-9]*'):
        try:
            if p.stat().st_uid == 1000 and (p / 'comm').read_text().strip() == 'mango':
                mangos.append(p)
        except OSError:
            pass
    c.require(len(mangos) == 1 and pwd.getpwuid(1000).pw_name == 'liveuser', 'Unique real live Mango identity required')
    mango = mangos[0]
    mango_identity = native.identity(int(mango.name), 1000)
    c.require(mango_identity['executable'] == '/usr/bin/mango', 'Actual Mango executable differs')
    _stage('renderer-environment')
    full_env = dict(v.split('=', 1) for v in (mango / 'environ').read_bytes().decode().split('\0') if '=' in v)
    allowed_env = {'WLR_RENDERER', 'WLR_RENDERER_ALLOW_SOFTWARE', 'WLR_RENDERER_FORCE_SOFTWARE',
                   'WLR_NO_HARDWARE_CURSORS', 'WLR_DRM_NO_ATOMIC', 'WLR_SCENE_DEBUG_DAMAGE',
                   'LIBGL_ALWAYS_SOFTWARE', 'MESA_LOADER_DRIVER_OVERRIDE', 'GALLIUM_DRIVER',
                   'WLR_BACKENDS', 'WLR_DRM_DEVICES', 'WLR_HEADLESS_OUTPUTS'}
    observed_env = {k: full_env[k] for k in sorted(allowed_env) if k in full_env}
    c.require(observed_env.get('WLR_RENDERER_FORCE_SOFTWARE') == '1'
              and observed_env.get('LIBGL_ALWAYS_SOFTWARE') == '1'
              and 'WLR_SCENE_DEBUG_DAMAGE' not in observed_env
              and 'WLR_RENDERER' not in observed_env, 'Safe baseline renderer environment differs')
    _stage('renderer-maps')
    maps = (mango / 'maps').read_text()
    c.require(len(maps) < 1024**2, 'Mango map observation exceeds bound')
    mapped = sorted({line.split()[-1] for line in maps.splitlines() if line.split()[-1].startswith('/usr/')
                     and re.search(r'/(?:lib[^/]*(?:EGL|GL|gbm|scenefx|wlroots|pixman|gallium|LLVM|drm|wayland)[^/]*\.so[^/]*|[^/]*dri\.so)$', line.split()[-1])})
    libraries = []
    for name in mapped:
        _stage('library-resolution')
        path = Path(name).resolve(strict=True)
        c.require(str(path).startswith('/usr/') and path.is_file(), 'Mapped renderer library path differs')
        libraries.append(dict(path=str(path), bytes=path.stat().st_size, sha256=c.sha(path),
                              rpm=_observed('library-owner-query', lambda: bounded(['rpm', '-qf', str(path)])).splitlines()))
    _stage('drm-fds')
    dri_fds = []
    for fd in (mango / 'fd').iterdir():
        try:
            target = os.readlink(fd)
            if re.fullmatch('/dev/dri/(?:card|renderD)[0-9]+', target):
                dri_fds.append(dict(fd=int(fd.name), device=target))
        except OSError:
            pass
    _stage('kernel-framebuffer')
    kernel_display = {}
    for name in ('name', 'virtual_size', 'stride', 'bits_per_pixel'):
        path = Path('/sys/class/graphics/fb0') / name
        if path.is_file():
            raw = path.read_bytes()
            c.require(len(raw) < 4096, 'Framebuffer attribute exceeds bound')
            kernel_display[str(path)] = raw.decode().strip()
    _stage('kernel-drm')
    drm = {}
    for path in sorted(Path('/sys/class/drm').glob('card*/*')):
        if path.name not in ('status', 'modes', 'enabled', 'uevent') or not path.is_file():
            continue
        raw = path.read_bytes()
        c.require(len(raw) <= 16384, 'DRM attribute exceeds bound')
        drm[str(path)] = raw.decode().strip()
    _stage('existing-debugfs')
    debugfs = {}
    for path in sorted(Path('/sys/kernel/debug/dri').glob('*/framebuffer')):
        if path.is_file():
            raw = path.read_bytes()
            c.require(len(raw) < 65536, 'Existing debugfs framebuffer exceeds bound')
            debugfs[str(path)] = raw.decode().strip()
    _stage('renderer-journal')
    journal = bounded(['journalctl', '--no-pager', '--boot=0', '-o', 'short-monotonic',
                       '_COMM=mango', '_PID='+mango.name, '-n', '400'])
    renderer_lines = [line for line in journal.splitlines()
                      if re.search(r'renderer|allocator|EGL|GLES|OpenGL|DRM|dmabuf|buffer|stride|damage|llvmpipe|softpipe', line, re.I)]
    _stage('monitor-query')
    monitors = c.strict(bounded([*prefix, 'mmsg', 'get', 'all-monitors']))
    c.require(type(monitors) is dict and len(monitors.get('monitors', [])) == 1, 'Single original output required')
    _stage('output-validation')
    output = monitors['monitors'][0]
    name = output.get('name')
    c.require(type(name) is str and re.fullmatch('[A-Za-z0-9_.-]{1,63}', name), 'Output name differs')
    # Geometry is also independently attested by the Wayland output listener.
    _stage('workspace')
    root = Path('/tmp') / ('arctic-native-smoke-safe-' + ctx['binding_id'])
    root.mkdir(mode=0o700)
    os.chown(root, 1000, 1000)
    _stage('port-open')
    runtime.PORT_NAME = 'arctic-safe-evidence'
    writer, port = runtime.open_port()
    _stage('port-duplex')
    fd = os.open(port['device'], os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_NOCTTY)
    info, other = os.fstat(fd), os.fstat(writer.fd)
    c.require(stat.S_ISCHR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022
              and info.st_rdev == other.st_rdev and info.st_ino == other.st_ino, 'Duplex virtio identity differs')
    writer.close()
    channel = c.Channel(fd, ctx['binding_id'])
    report = dict(schema='arctic-safe-guest-observation-v1', context=ctx,
                  release_acceptance=False, image_qualified=False, performance_acceptance=False,
                  observer_profile_admitted=False, cmdline_tokens=tokens,
                  mango={**mango_identity, 'sha256': c.sha('/usr/bin/mango')},
                  renderer_environment=observed_env, libraries=libraries, drm_fds=dri_fds,
                  kernel_display=kernel_display, drm=drm, existing_debugfs=debugfs,
                  renderer_journal_lines=renderer_lines,
                  renderer_journal_scope=dict(boot='current',pid=int(mango.name),comm='mango',
                                               last_records=400,output='short-monotonic'),
                  monitors=monitors, port=port,
                  packages=_observed('package-query', lambda: bounded(['rpm', '-q', 'mangowm', 'scenefx', 'wlroots', 'mesa-dri-drivers', 'foot'])).splitlines(),
                  selinux_before=_observed('selinux-before', lambda: bounded(['getenforce'])), samples=[], interventions=[],
                  limitations=['Renderer/allocator facts are observations; absent journal or kernel fields remain unknown.',
                               'wl_shm readback can trigger repaint; QMP frames bracket every readback.',
                               'Guest/host monotonic clocks are separate; protocol establishes causal ordering.'])
    foot = None
    foot_fd = None
    try:
        _stage('hello-send')
        channel.send('HELLO', dict(context=ctx, guest_ns=time.monotonic_ns(), output=name))
        _stage('hello-ack')
        channel.expect('HELLO-ACK', dict(execution_sha=ctx['execution_sha']))
        time.sleep(3)
        _stage('capture')
        for label in c.PAIRS:
            if label == 'terminal-initial':
                # Only synthetic public text. No stdin/audio, shell history, or user data.
                script = "printf 'Arctic Safe rendering diagnostic\\n'; sleep 8; i=0; while [ $i -lt 12 ]; do printf 'Synthetic repaint %02d\\n' $i; i=$((i+1)); sleep 1; done; sleep 120"
                foot = subprocess.Popen([*prefix, '/usr/bin/foot', '--title', 'Arctic-Safe-Diagnostic', '/bin/sh', '-c', script],
                                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        start_new_session=True)
                report['interventions'].append(dict(kind='owned-synthetic-Foot-launch', guest_ns=time.monotonic_ns(), wrapper_pid=foot.pid,
                           executable_sha256=c.sha('/usr/bin/foot')))
                time.sleep(2)
                c.require(foot.poll() is None, 'Owned Foot exited before terminal observation')
                deadline = time.monotonic()+10
                clients = []
                while time.monotonic()<deadline:
                    before_clients = c.strict(bounded([*prefix, 'mmsg', 'get', 'all-clients']))
                    clients = [v for v in before_clients.get('clients', []) if v.get('title') == 'Arctic-Safe-Diagnostic'
                               and v.get('is_visible') is True]
                    if clients: break
                    time.sleep(.2)
                c.require(len(clients) == 1 and clients[0].get('is_visible') is True
                          and clients[0].get('is_xwayland') is False and clients[0].get('monitor') == name,
                          'Unique synthetic native Foot window is not mapped on the observed output')
                owned = native.identity(clients[0]['pid'], 1000)
                ancestry = [owned['pid']]
                while ancestry[-1] != foot.pid and len(ancestry)<16:
                    status = Path('/proc')/str(ancestry[-1])/'status'
                    ppid = re.search(r'^PPid:\s+([0-9]+)$', status.read_text(), re.M)
                    c.require(ppid and int(ppid[1])>1, 'Mapped Foot ancestry does not reach the owned wrapper')
                    ancestry.append(int(ppid[1]))
                c.require(owned['executable'] == '/usr/bin/foot' and ancestry[-1] == foot.pid,
                          'Mapped Foot differs from the acquired child tree')
                foot_fd = os.pidfd_open(owned['pid'])
                c.require(native.identity(owned['pid'],1000)==owned, 'Mapped Foot identity changed at pidfd acquisition')
                report['terminal_window'] = dict(identity=owned, monitor=name, title='Arctic-Safe-Diagnostic',
                          visible=True, native_wayland=True, width=clients[0]['width'], height=clients[0]['height'],
                          owned_ancestry=ancestry)
            elif label == 'terminal-repaint':
                time.sleep(22)
            before_request = time.monotonic_ns()
            channel.send('CAPTURE-REQUEST', dict(label=label, guest_ns=before_request))
            ack = channel.expect('QMP-BEFORE', timeout=30)
            c.require(set(ack) == {'label', 'host_ns'} and ack['label'] == label and type(ack['host_ns']) is int,
                      'QMP-before acknowledgement differs')
            start_ns = time.monotonic_ns()
            path = root / (label + '-wayland.rgb')
            capture = subprocess.run([*prefix, str(BASE / 'raw-screencopy'), name, str(path)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
            end_ns = time.monotonic_ns()
            c.require(capture.returncode == 0 and not capture.stdout and len(capture.stderr) <= 16384,
                      'Wayland readback failed or exceeds bounds')
            screen.external_text(capture.stderr)
            (root / (label + '-wayland.log')).write_bytes(capture.stderr)
            descriptor = c.strict(c.regular(Path(str(path)+'.json'), owner=1000).read_bytes())
            c.require(descriptor['width'] == descriptor['output_width'] == 1920
                      and descriptor['height'] == descriptor['output_height'] == 1080
                      and descriptor['output_scale'] == 1 and descriptor['output_transform'] == 0
                      and descriptor['selected_output'] == name and descriptor['outputs_seen'] == 1
                      and descriptor['raw_bytes'] == descriptor['stride'] * descriptor['height']
                      and descriptor['flags'] in (0, 1), 'Original physical output or raw descriptor differs')
            files = {p.name: dict(bytes=c.regular(p).stat().st_size, sha256=c.sha(p))
                     for p in root.iterdir() if p.name.startswith(label + '-wayland')}
            channel.send('CAPTURE-DONE', dict(label=label, guest_ns=end_ns))
            after = channel.expect('QMP-AFTER', timeout=30)
            c.require(set(after) == {'label', 'host_ns'} and after['label'] == label and type(after['host_ns']) is int,
                      'QMP-after acknowledgement differs')
            report['samples'].append(dict(label=label, request_ns=before_request, capture_start_ns=start_ns,
                         capture_end_ns=end_ns, qmp_before_ack=ack, qmp_after_ack=after,
                         descriptor=descriptor, files=files))
        _stage('export')
        report['selinux_after'] = bounded(['getenforce'])
        c.require(report['selinux_before'] == report['selinux_after'] == 'Enforcing', 'SELinux observation differs')
        raw = (json.dumps(report, sort_keys=True, allow_nan=False) + '\n').encode()
        screen.external_text(raw)
        (root / 'guest-report.json').write_bytes(raw)
        # All text members are screened before any byte enters the transport.
        for path in root.iterdir():
            if path.suffix in ('.json', '.log'):
                screen.external_text(c.regular(path).read_bytes())
        c.export_files(channel, root)
        channel.expect('RECEIVED', dict(files=len(c.GUEST_FILES)), timeout=30)
        print('ARCTIC-SAFE-DIAGNOSTIC-COMPLETE', flush=True)
    except BaseException as error:
        _guest_primary = (_guest_phase, c.guest_exception_class(error))
        raise
    finally:
        if foot_fd is not None:
            try:
                signal.pidfd_send_signal(foot_fd, signal.SIGTERM)
            except ProcessLookupError:
                pass
        if foot is not None and foot.poll() is None:
            # This process group was acquired by this exact Popen invocation.
            os.killpg(foot.pid, signal.SIGTERM)
            try:
                foot.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(foot.pid, signal.SIGKILL); foot.wait(timeout=5)
        if foot_fd is not None:
            try:
                signal.pidfd_send_signal(foot_fd, signal.SIGKILL)
            except ProcessLookupError:
                pass
            os.close(foot_fd)
        os.close(fd)


if __name__ == '__main__':
    raise SystemExit(execute())
