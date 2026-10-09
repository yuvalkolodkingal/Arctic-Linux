#!/usr/bin/env python3
"""Installed-image taskbar checks on the actual, disposable Mango desktop.

Uses the installed shell and Foot; never substitutes QML or installs packages.
Requires two enabled outputs and reviewed virtual-pointer/raw-screencopy binaries
in /run/t. Captures use physical output buffers, avoiding fractional resampling.
Temporarily changes shell preferences, output scales and empty workspaces. Every
change is restored, including on failure. This is an additional gate: it does
not replace the covered-frame source fixture or qualify a release by itself.
"""
import argparse
import collections
import json
import math
import os
from pathlib import Path
import re
import select
import signal
import stat
import subprocess
import tempfile
import time

from PIL import Image, ImageColor
from native_smoke import (Smoke, SecurityInterval, digest, discover_desktop,
                          execute, guest_guard, identity, require)

EDGES = ('top', 'bottom', 'left', 'right')
SCALES = (1, 1.5, 2)
FRAME = 6  # Installed Theme.qml's reviewed contract, not inferred from preferences.
BAR = 32
FOOT_COLOR = (33, 131, 79)


def rectangle(value):
    result = {key: value[key] for key in ('x', 'y', 'width', 'height')}
    require(all(type(v) in (int, float) and math.isfinite(v) for v in result.values())
            and result['width'] > 0 and result['height'] > 0,
            'invalid authoritative Mango rectangle')
    return result


def reserved_rectangle(baseline, edge, mode, frame=FRAME, bar=BAR):
    """Effective usable-area oracle relative to observed frame-off/zero-zone geometry."""
    require(edge in EDGES and mode in ('always', 'auto', 'dodge'), 'invalid taskbar case')
    result = rectangle(baseline)
    insets = dict.fromkeys(EDGES, frame)
    if mode == 'always':
        insets[edge] += bar
    result['x'] += insets['left']
    result['y'] += insets['top']
    result['width'] -= insets['left'] + insets['right']
    result['height'] -= insets['top'] + insets['bottom']
    return result


def same_rectangle(actual, expected):
    return all(abs(rectangle(actual)[key] - rectangle(expected)[key]) <= 1
               for key in ('x', 'y', 'width', 'height'))


def validate_layers(layers, names, mode, frame):
    """Mango returns mapped layers only; count actual surfaces, not QML instances."""
    require(type(layers) is list and len(set(names)) == len(names), 'invalid layer inventory')
    for namespace, expected, layer in (
        ('arctic-bar', 1, 'top' if mode == 'always' else 'overlay'),
        ('arctic-frame', int(frame), 'bottom'),
        ('arctic-frame-reserve', (3 if mode == 'always' else 4) if frame else 0, 'bottom'),
    ):
        members = [item for item in layers if item.get('name') == namespace]
        counts = collections.Counter(item.get('monitor') for item in members)
        require(set(counts) <= set(names) and all(counts[name] == expected for name in names),
                'missing or duplicate mapped ' + namespace + ': ' + repr(dict(counts)))
        require(all(item.get('layer') == layer for item in members),
                'wrong actual layer for ' + namespace)
    return layers


def pixel_visibility(image, edge, scale):
    """Sample the middle of the bar band, away from its 3px hidden edge trigger."""
    image = image.convert('RGB')
    # A maximized client retains the frame's 6px reserve and Mango's 8px
    # gap. Probe beyond that gap while remaining inside the 32px bar band.
    offset = max(4, round((FRAME + BAR / 2) * scale))
    x, y = {'top': (image.width // 2, offset),
            'bottom': (image.width // 2, image.height - 1 - offset),
            'left': (offset, image.height // 2),
            'right': (image.width - 1 - offset, image.height // 2)}[edge]
    radius = max(2, round(3 * scale))
    require(radius <= x < image.width - radius and radius <= y < image.height - radius,
            'output too small for taskbar pixel oracle')
    values = [image.getpixel((xx, yy)) for yy in range(y-radius, y+radius+1)
              for xx in range(x-radius, x+radius+1)]
    changed = sum(max(abs(a-b) for a, b in zip(value, FOOT_COLOR)) > 10 for value in values)
    return dict(non_foot_fraction=changed/len(values), sampled_pixels=len(values),
                region=[x-radius, y-radius, x+radius+1, y+radius+1])


class Taskbar(Smoke):
    def __init__(self, prefix, pointer, capture):
        super().__init__(prefix, 'installed')
        self.prefix = self.original_prefix  # Exercise the actual shell and user's desktop.
        self.pointer_path = Path(pointer)
        self.capture_path = Path(capture)
        self.pointer = None
        self.pointer_buffer = b''
        self.saved = None
        self.results = []
        self.proof = None

    def query(self, name):
        return json.loads(self.cmd(['mmsg', 'get', name])[1])

    def dispatch(self, command, owned=False):
        argv = ['mmsg', 'dispatch', command]
        if owned:
            self.alive(self.proof)
            argv += ['client,' + self.proof['client_id']]
        require(json.loads(self.cmd(argv)[1]) == {'success': True}, 'Mango dispatch failed: ' + command)

    def ipc(self, *words):
        return self.cmd(['arctic-shell-ipc', *words])[1]

    def monitor(self, name):
        matches = [m for m in self.query('all-monitors')['monitors'] if m.get('name') == name]
        require(len(matches) == 1, 'output inventory changed')
        rectangle(matches[0])
        return matches[0]

    def layers(self, mode, frame=True):
        value = self.query('all-layers')['layers']
        validate_layers(value, self.names, mode, frame)
        return value

    def settings(self, edge, mode, frame=True):
        value = dict(self.saved['settings'], barPosition=edge, barSize=BAR,
                     barHideMode=mode, frame=frame)
        self.write_settings((json.dumps(value, ensure_ascii=False) + '\n').encode())
        self.ipc('shell', 'reload')
        time.sleep(.8)  # Existing reveal/remap animations must finish before observation.
        self.layers(mode, frame)

    def write_settings(self, content):
        require(not self.settings_path.is_symlink(), 'shell preferences became a symlink')
        fd, path = tempfile.mkstemp(prefix='.taskbar-', dir=self.settings_path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(content)
            os.chown(path, self.uid, self.user.pw_gid)
            os.chmod(path, self.saved['mode'])
            os.replace(path, self.settings_path)
        finally:
            Path(path).unlink(missing_ok=True)

    def move_pointer(self, name, edge=None):
        monitors = [self.monitor(n) for n in self.names]
        origin_x = min(m['x'] for m in monitors)
        origin_y = min(m['y'] for m in monitors)
        width = max(m['x'] + m['width'] for m in monitors) - origin_x
        height = max(m['y'] + m['height'] for m in monitors) - origin_y
        m = self.monitor(name)
        x, y = m['width']//2, m['height']//2
        if edge == 'top': y = 0
        if edge == 'bottom': y = m['height']-1
        if edge == 'left': x = 0
        if edge == 'right': x = m['width']-1
        self.pointer.stdin.write(f'move {int(m["x"]+x-origin_x)} {int(m["y"]+y-origin_y)} {math.ceil(width)} {math.ceil(height)}\n')
        self.pointer.stdin.flush()
        require(self.pointer_reply() == 'OK', 'virtual pointer reply failed')

    def pointer_reply(self):
        deadline = time.monotonic() + 3
        while b'\n' not in self.pointer_buffer:
            remaining = deadline - time.monotonic()
            require(remaining > 0 and self.pointer.poll() is None, 'virtual pointer exited or timed out')
            if not select.select([self.pointer.stdout], [], [], remaining)[0]:
                raise RuntimeError('virtual pointer reply timed out')
            data = os.read(self.pointer.stdout.fileno(), 256)
            require(data and len(self.pointer_buffer) + len(data) <= 512, 'invalid virtual pointer reply')
            self.pointer_buffer += data
        line, self.pointer_buffer = self.pointer_buffer.split(b'\n', 1)
        return line.decode('ascii').strip()

    def capture(self, name, label):
        output = next(o for o in json.loads(self.cmd(['wlr-randr', '--json'])[1]) if o['name'] == name)
        scale = output['scale']
        path = self.root / (re.sub('[^a-zA-Z0-9_-]', '_', label) + '.png')
        raw = self.root / 'physical-capture.ppm'
        require(not raw.exists(), 'raw physical capture unexpectedly exists')
        self.cmd([str(self.capture_path), name, str(raw)])
        require(raw.is_file() and 0 < raw.stat().st_size < 64*1024*1024, 'invalid raw physical capture')
        mode = next(m for m in output['modes'] if m.get('current') is True)
        with Image.open(raw) as image:
            require(image.size == (mode['width'], mode['height']),
                    'capture differs from native physical output dimensions')
            image.save(path)
        raw.unlink()
        require(path.is_file() and 0 < path.stat().st_size < 16*1024*1024, 'invalid screenshot')
        return path, scale

    def visibility(self, name, edge, shown, label, expected=None):
        def observed():
            path, scale = self.capture(name, label)
            with Image.open(path) as image:
                value = pixel_visibility(image, edge, scale)
            fraction = value['non_foot_fraction']
            good = fraction >= .6 if shown else fraction <= .1
            return dict(value, path=str(path), sha256=digest(path), visible=shown) if good else None
        value = self.wait(observed, 8, 'actual covered bar ' + ('reveal' if shown else 'hide'))
        self.layers(self.case_mode)
        require(same_rectangle(self.alive(self.proof), expected or self.monitor(name)),
                'bar reveal moved the actual covered client')
        return value

    def maximize(self):
        client = self.alive(self.proof)
        if client.get('is_fullscreen'):
            self.dispatch('togglefullscreen', owned=True)
            self.wait(lambda: not self.alive(self.proof)['is_fullscreen'], 8, 'leave owned fullscreen')
        if not self.alive(self.proof).get('is_maximized'):
            self.dispatch('togglemaximizescreen', owned=True)
        self.wait(lambda: self.alive(self.proof).get('is_maximized') is True, 8, 'owned maximized client')

    def geometry(self, expected):
        self.wait(lambda: same_rectangle(self.alive(self.proof), expected), 8, 'effective reserved geometry')
        return rectangle(self.alive(self.proof))

    def prepare(self):
        require(self.ipc('shell', 'live') == 'false', 'requires the actual installed shell')
        require(self.cmd(['arctic-shell', '--path'])[1] == '/usr/share/arctic/shell',
                'requires canonical installed shell, without a user QML override')
        for program in (self.pointer_path, self.capture_path):
            require(program.parent == Path('/run/t') and program.is_file() and not program.is_symlink(),
                    'capture/pointer must be in the reviewed guest bundle')
        require(self.cmd(['readlink', '-f', '/usr/bin/foot'])[1] == '/usr/bin/foot', 'unexpected Foot binary')
        self.original_outputs = json.loads(self.cmd(['wlr-randr', '--json'])[1])
        require(len(self.original_outputs) == 2 and all(o.get('enabled') is True for o in self.original_outputs),
                'complete acceptance requires exactly two enabled outputs')
        require(all(o.get('transform') == 'normal' for o in self.original_outputs),
                'physical pixel matrix requires two outputs with normal transform')
        self.names = [o['name'] for o in self.original_outputs]
        self.original_monitors = self.query('all-monitors')['monitors']
        require({m['name'] for m in self.original_monitors} == set(self.names), 'Mango/output inventory differs')
        require(all(len(m['active_tags']) == 1 and not m.get('hide_clients') for m in self.original_monitors),
                'requires normal single-workspace desktop outputs')
        self.empty = {m['name']: next((t['index'] for t in reversed(m['tags']) if not t['client_count']), None)
                      for m in self.original_monitors}
        require(all(self.empty.values()), 'each output needs an empty workspace')
        self.original_clients = self.clients()
        self.original_identities = {key: identity(c['pid'], self.uid)
                                    for key, c in self.original_clients.items()}
        require(not any(c.get('is_global') or c.get('is_unglobal') or c.get('is_overlay')
                        for c in self.original_clients.values()), 'close global/overlay apps in this test guest')
        config = next((x.split('=', 1)[1] for x in self.prefix[5:] if x.startswith('XDG_CONFIG_HOME=')),
                      self.user.pw_dir + '/.config')
        self.settings_path = Path(config) / 'arctic/shell.json'
        require(self.settings_path.parent.is_dir() and not self.settings_path.parent.is_symlink(),
                'normal Arctic configuration directory required')
        require(not self.settings_path.is_symlink(), 'refuse symlink shell preferences')
        original = self.settings_path.read_bytes() if self.settings_path.exists() else None
        settings = json.loads(original) if original else {}
        require(type(settings) is dict, 'malformed existing shell preferences')
        mode = stat.S_IMODE(self.settings_path.stat().st_mode) if original is not None else 0o644
        self.saved = dict(settings=settings, bytes=original, mode=mode,
                          hidden=self.ipc('bar', 'hidden'), cursor=self.query('cursorpos'))
        require(self.saved['hidden'] in ('true', 'false'), 'unobserved initial bar visibility')
        if self.saved['hidden'] == 'true': self.ipc('bar', 'toggleHidden')
        for m in self.original_monitors:
            self.dispatch('focusmon,' + m['name'])
            self.dispatch('view,' + str(self.empty[m['name']]) + ',0')
        self.dispatch('focusmon,' + self.names[0])
        self.proof = self.fresh_window(lambda: self.launch([
            '/usr/bin/foot', '-c', '/dev/null', '--app-id=ArcticTaskbarAcceptance',
            '-o', 'colors.background=21834f', '-o', 'main.pad=0x0',
            '/usr/bin/sleep', '1800']), 'foot', '^ArcticTaskbarAcceptance$')
        self.pointer = subprocess.Popen(self.prefix + [str(self.pointer_path)], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        require(self.pointer_reply() == 'READY', 'virtual pointer did not start')

    def matrix(self):
        for name in self.names:
            self.dispatch('tagmon,' + name, owned=True)
            self.dispatch('focusmon,' + name)
            for scale in SCALES:
                for output in self.names:
                    self.cmd(['wlr-randr', '--output', output, '--scale', str(scale if output == name else 1)])
                time.sleep(.8)
                self.move_pointer(name)
                self.settings('top', 'auto', frame=False)
                self.maximize()
                time.sleep(.5)
                baseline = rectangle(self.alive(self.proof))
                m = rectangle(self.monitor(name))
                # Stock Mango's 8px outer gaps. Both sides must be symmetric;
                # a stale/duplicate reserve cannot become a "baseline" oracle.
                require(same_rectangle(baseline, dict(x=m['x']+8, y=m['y']+8,
                        width=m['width']-16, height=m['height']-16)), 'zero-zone baseline differs from installed 8px gaps')
                for edge in EDGES:
                    label = f'{name}-{scale}-{edge}'
                    self.settings(edge, 'always')
                    self.maximize()
                    fixed = self.geometry(reserved_rectangle(baseline, edge, 'always'))
                    # Real covered non-fullscreen surfaces must also hide/reveal
                    # without retaining the Always zone or moving the client.
                    covered = []
                    for mode in ('auto', 'dodge'):
                        self.case_mode = mode
                        self.settings(edge, mode)
                        expected = reserved_rectangle(baseline, edge, mode)
                        effective = self.geometry(expected)
                        self.move_pointer(name)
                        time.sleep(1)
                        hidden = self.visibility(name, edge, False, label+'-'+mode+'-covered-rest', expected)
                        self.move_pointer(name, edge)
                        revealed = self.visibility(name, edge, True, label+'-'+mode+'-covered-reveal', expected)
                        self.move_pointer(name)
                        self.visibility(name, edge, False, label+'-'+mode+'-covered-conceal', expected)
                        require(self.alive(self.proof).get('is_fullscreen') is False,
                                'covered-window phase became fullscreen')
                        covered.append(dict(mode=mode, geometry=effective, rest=hidden, reveal=revealed,
                                            layers=self.layers(mode)))
                    self.settings(edge, 'always')
                    self.geometry(fixed)
                    # Enter hiding mode while a real fullscreen Foot covers the frame.
                    self.dispatch('togglefullscreen', owned=True)
                    self.wait(lambda: self.alive(self.proof)['is_fullscreen'] is True, 8, 'owned fullscreen')
                    self.geometry(m)
                    modes = []
                    for transition_index, mode in enumerate(('auto', 'dodge', 'always', 'auto', 'dodge')):
                        transition_label = label+'-fullscreen-'+str(transition_index)+'-'+mode
                        self.case_mode = mode
                        self.settings(edge, mode)
                        self.move_pointer(name)
                        time.sleep(1)
                        # Mango puts true fullscreen above Top; Always visible
                        # therefore stays covered. Hiding bars use Overlay and
                        # must reveal from the physical edge above fullscreen.
                        hidden = self.visibility(name, edge, False, transition_label+'-rest')
                        revealed = None
                        if mode != 'always':
                            self.move_pointer(name, edge)
                            revealed = self.visibility(name, edge, True, transition_label+'-reveal')
                            self.move_pointer(name)
                            self.visibility(name, edge, False, transition_label+'-conceal')
                        modes.append(dict(mode=mode, rest=hidden, reveal=revealed, layers=self.layers(mode)))
                    self.maximize()
                    hidden_geometry = self.geometry(reserved_rectangle(baseline, edge, 'dodge'))
                    path, actual_scale = self.capture(name, label+'-frame-exposed')
                    with Image.open(path) as image:
                        image = image.convert('RGB')
                        ground = ImageColor.getrgb(self.theme_ground)
                        probes = [(image.width//2, 0), (image.width//2, image.height-1),
                                  (0, image.height//2), (image.width-1, image.height//2)]
                        require(all(max(abs(a-b) for a,b in zip(image.getpixel(p), ground)) <= 3 for p in probes),
                                'exposed installed frame has stale/transparent edge pixels')
                    self.results.append(dict(output=name, scale=scale, edge=edge, baseline=baseline,
                        always_geometry=fixed, hiding_geometry=hidden_geometry, transitions=modes,
                        covered_windows=covered,
                        exposed_frame=dict(path=str(path), sha256=digest(path), scale=actual_scale)))
                    self.trace('taskbar-case-passed', case=self.results[-1])
        require(len(self.results) == len(self.names)*len(SCALES)*len(EDGES)
                and len({(v['output'], v['scale'], v['edge']) for v in self.results}) == len(self.results),
                'complete, unique taskbar case matrix missing')
        return self.results

    def restore(self):
        errors = []
        if self.saved is not None:
            try:
                if self.saved['bytes'] is None:
                    self.settings_path.unlink(missing_ok=True)
                else:
                    self.write_settings(self.saved['bytes'])
                self.ipc('shell', 'reload')
                if self.ipc('bar', 'hidden') != self.saved['hidden']: self.ipc('bar', 'toggleHidden')
            except Exception as exc: errors.append('preferences: ' + str(exc))
        try:
            super().cleanup()
        except Exception as exc: errors.append('owned Foot cleanup: ' + str(exc))
        for output in getattr(self, 'original_outputs', []):
            try:
                p = output['position']
                self.cmd(['wlr-randr', '--output', output['name'], '--scale', str(output['scale']),
                          '--pos', f'{p["x"]},{p["y"]}'])
            except Exception as exc: errors.append('output: ' + str(exc))
        for m in getattr(self, 'original_monitors', []):
            try:
                self.dispatch('focusmon,' + m['name'])
                self.dispatch('view,' + str(m['active_tags'][0]) + ',0')
            except Exception as exc: errors.append('workspace: ' + str(exc))
        try:
            if not hasattr(self, 'original_monitors'):
                require(not errors, 'taskbar cleanup failed: ' + repr(errors))
                return dict(no_desktop_mutation=True)
            selected = next(m for m in self.original_monitors if m['active'])
            self.dispatch('focusmon,' + selected['name'])
            if self.pointer is not None and self.saved is not None:
                c = self.saved['cursor']
                monitors = [self.monitor(n) for n in self.names]
                x = min(m['x'] for m in monitors); y = min(m['y'] for m in monitors)
                w = math.ceil(max(m['x']+m['width'] for m in monitors)-x)
                h = math.ceil(max(m['y']+m['height'] for m in monitors)-y)
                self.pointer.stdin.write(f'move {int(c["x"]-x)} {int(c["y"]-y)} {w} {h}\n')
                self.pointer.stdin.flush()
                require(self.pointer_reply() == 'OK', 'restore pointer failed')
        except Exception as exc: errors.append('focus/pointer: ' + str(exc))
        if self.pointer is not None:
            try:
                self.pointer.stdin.write('quit\n'); self.pointer.stdin.flush(); self.pointer.wait(timeout=3)
            except Exception:
                self.pointer.terminate()
                try: self.pointer.wait(timeout=3)
                except subprocess.TimeoutExpired: errors.append('owned virtual pointer did not exit')
        if self.saved is not None:
            try:
                require((self.settings_path.read_bytes() if self.settings_path.exists() else None) == self.saved['bytes'],
                        'original preferences were not restored exactly')
                require(json.loads(self.cmd(['wlr-randr', '--json'])[1]) == self.original_outputs,
                        'original output configuration was not restored exactly')
                after = self.clients()
                require(all(key in after and after[key]['pid'] == value['pid']
                            and identity(value['pid'], self.uid) == self.original_identities[key]
                            for key, value in self.original_clients.items()), 'pre-existing window disappeared or PID recycled')
                layers = self.query('all-layers')['layers']
                expected = 0 if self.saved['hidden'] == 'true' else 1
                counts = collections.Counter(l.get('monitor') for l in layers if l.get('name') == 'arctic-bar')
                require(all(counts[n] == expected for n in self.names) and set(counts) <= set(self.names),
                        'missing or duplicate bars after restoration')
            except Exception as exc: errors.append('restoration verification: ' + str(exc))
        require(not errors, 'taskbar cleanup failed: ' + repr(errors))
        return dict(settings_bytes_restored=True, outputs_restored=True, original_windows_retained=True,
                    bars_restored=True, only_proved_owned_processes_stopped=True)


def run_checks(prefix, pointer, capture, *, disposable_guest=False):
    guest_guard('installed', disposable_guest)
    security = SecurityInterval()
    task = Taskbar(prefix, pointer, capture)
    report = dict(schema='arctic-installed-taskbar-v1', stage='installed', status='failed',
                  release_acceptance=False, evidence_root=str(task.root), results=task.results,
                  scope='actual installed shell/Foot on two outputs; virtual pointer; no physical hardware claim',
                  reservation_observer='Mango maximized-client rectangles; IPC does not expose raw exclusive-zone values')
    try:
        task.prepare()
        # Carry the actual fresh Wayland Foot identity into the public report;
        # the PID/start time and executed ELF remain checked throughout the matrix.
        report['owned_window'] = dict(task.proof, uid=task.uid)
        theme = Path(task.user.pw_dir) / '.config/arctic/current/theme.json'
        task.theme_ground = json.loads(theme.read_text())['colors']['ground']
        report['installed_inputs'] = {str(p): digest(p) for p in (
            Path('/usr/share/arctic/shell/Bar.qml'), Path('/usr/share/arctic/shell/ScreenFrame.qml'),
            Path('/usr/share/arctic/shell/Session.qml'), Path('/usr/share/arctic/shell/Theme.qml'),
            Path('/usr/share/arctic/shell/VerticalBar.qml'), Path('/usr/share/arctic/shell/BarVisibility.js'),
            Path('/usr/share/arctic/shell/scripts/window_geometry.py'),
            Path('/usr/share/arctic/shell/shell.qml'), Path('/usr/bin/mango'), Path('/usr/bin/mmsg'),
            Path('/usr/bin/foot'), task.pointer_path, task.capture_path, theme)}
        task.matrix()
        report['status'] = 'passed'
    except BaseException as exc:
        report['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        try: report['cleanup'] = task.restore()
        except BaseException as exc:
            report.update(status='failed', cleanup_error=type(exc).__name__ + ': ' + str(exc))
        try: report['security'] = security.finish()
        except BaseException as exc:
            report.update(status='failed', security_error=type(exc).__name__ + ': ' + str(exc))
        (task.root/'taskbar-report.json').write_text(json.dumps(report, indent=2) + '\n')
        print('ARCTIC-NATIVE-TASKBAR ' + json.dumps(report), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disposable-guest', action='store_true', required=True)
    parser.add_argument('--pointer', type=Path, required=True)
    parser.add_argument('--capture', type=Path, required=True)
    args = parser.parse_args()
    require(Path(__file__).resolve() == Path('/run/t/taskbar.py'), 'requires the reviewed /run/t guest bundle')
    def interrupted(signum, _): raise InterruptedError('taskbar test interrupted by signal ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    return int(run_checks(discover_desktop(), args.pointer, args.capture,
                          disposable_guest=args.disposable_guest)['status'] != 'passed')


if __name__ == '__main__':
    raise SystemExit(main())
