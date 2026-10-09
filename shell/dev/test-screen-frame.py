#!/usr/bin/env python3
"""Test real Bar/ScreenFrame surfaces in a private, two-output compositor.

No production session is contacted. Screenshots contain only the private test
desktop. --baseline-ref replays the old ScreenFrame first and records whether
the same covered-mode transitions reproduce a stale native window geometry.
"""
import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

from PIL import Image, ImageColor

SOURCE = Path(__file__).resolve().parents[1]


class FrameGeometryError(AssertionError):
    """Only a native frame dimension mismatch establishes baseline reproduction."""


def inner_frame_probe_points(surface, scale, frame_width, capture_width, capture_height):
    # The right/bottom path is at w-f+0.5 with a one-logical-pixel stroke,
    # so its outer edge ends at w-f+1. Choose the first whole physical pixel
    # beyond that edge. Adding one *physical* pixel to the cutout can still
    # land on the antialiased hairline at fractional or double scale.
    padding = surface.get('edgeOverscan', 0)
    return ((math.ceil((surface['width'] - padding - frame_width + 1) * scale), capture_height // 2),
            (capture_width // 2, math.ceil((surface['height'] - padding - frame_width + 1) * scale)))


def validate_preview(process, log_path):
    assert process.poll() is None, 'private preview exited: ' + log_path.read_text()
    errors = re.findall(r'TypeError|ReferenceError|SyntaxError|is not a type|Cannot assign|Unable to assign|Failed to load',
                        log_path.read_text())
    assert not errors, errors


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def wait(predicate, message, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.05)
    raise AssertionError(message)


def exercise(base, out, compositor, frame_source=None):
    out.mkdir(parents=True)
    runtime = base / 'runtime'
    runtime.mkdir(mode=0o700)
    shell = base / 'shell'
    shutil.copytree(SOURCE, shell, ignore=shutil.ignore_patterns('tests', 'dev'))
    shutil.copy2(SOURCE / 'dev/BarHarness.qml', shell / 'bar-test.qml')
    if frame_source:
        (shell / 'ScreenFrame.qml').write_text(frame_source)
    # Expose geometry from the unmodified baseline too, without changing bindings.
    frame = shell / 'ScreenFrame.qml'
    text = frame.read_text()
    if 'readonly property var surface: frame' not in text:
        text = text.replace('required property var modelData',
                            'required property var modelData\n    readonly property var surface: frame', 1)
        frame.write_text(text)
    env = dict(os.environ, HOME=str(base / 'home'), XDG_RUNTIME_DIR=str(runtime),
               XDG_CONFIG_HOME=str(base / 'config'), XDG_CACHE_HOME=str(base / 'cache'),
               XDG_STATE_HOME=str(base / 'state'), WLR_BACKENDS='headless',
               WLR_HEADLESS_OUTPUTS='2', WLR_LIBINPUT_NO_DEVICES='1',
               QT_QPA_PLATFORM='wayland', QT_QUICK_BACKEND='software',
               QT_QPA_PLATFORMTHEME='generic', QT_NO_XDG_DESKTOP_PORTAL='1',
               ARCTIC_FORCE_LIVE='0')
    for key in ('WAYLAND_DISPLAY', 'DISPLAY', 'SWAYSOCK', 'DBUS_SESSION_BUS_ADDRESS',
                'MANGO_INSTANCE_SIGNATURE', 'MANGO_SOCKET'):
        env.pop(key, None)
    is_sway = Path(compositor).name == 'sway'
    env['WLR_RENDERER'] = 'pixman' if is_sway else 'gles2'
    env['WLR_RENDERER_ALLOW_SOFTWARE'] = '1'
    if not is_sway:
        # Scenefx 0.5 requires this explicit switch to create EGL without a DRM
        # render node. It applies only to the owned private test compositor.
        env['WLR_RENDERER_FORCE_SOFTWARE'] = '1'
        env['LIBGL_ALWAYS_SOFTWARE'] = '1'
    bus = subprocess.Popen(['dbus-daemon', '--session', '--nofork', '--nopidfile', '--print-address=1'],
                           env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    processes = [bus]
    results = []
    try:
        env['DBUS_SESSION_BUS_ADDRESS'] = bus.stdout.readline().strip()
        assert env['DBUS_SESSION_BUS_ADDRESS'], 'private bus did not start'
        config = base / 'compositor.conf'
        config.write_text('output HEADLESS-1 resolution 1024x768 position 0 0\n'
                          'output HEADLESS-2 resolution 900x1600 position 1024 0\n'
                          'default_border none\n' if is_sway else
                          'xkb_rules_layout=us\nanimations=0\n')
        if is_sway:
            compositor = shutil.copyfile(compositor, base / 'sway')
            Path(compositor).chmod(0o755)
        with (out / 'compositor.log').open('w') as log:
            display = subprocess.Popen([compositor, '-c', str(config)], env=env, stdout=log, stderr=log)
            processes.append(display)
        wait(lambda: any(p.is_socket() for p in runtime.glob('wayland-*')) or display.poll() is not None,
             'private Wayland socket missing')
        assert display.poll() is None, (out / 'compositor.log').read_text()
        env['WAYLAND_DISPLAY'] = next(p.name for p in runtime.glob('wayland-*') if p.is_socket())
        if not is_sway:
            wait(lambda: any(p.is_socket() for p in runtime.glob('mango-*.sock')), 'private Mango IPC missing')
            env['MANGO_INSTANCE_SIGNATURE'] = str(next(runtime.glob('mango-*.sock')))

        def run(*words):
            return subprocess.check_output(list(map(str, words)), env=env, text=True, timeout=15).strip()

        outputs = json.loads(run('wlr-randr', '--json'))
        assert len(outputs) == 2 and all(o['name'].startswith('HEADLESS-') for o in outputs), outputs
        names = [o['name'] for o in outputs]
        for name, mode, position in zip(names, ('1024x768', '900x1600'), ('0,0', '1024,0')):
            run('wlr-randr', '--output', name, '--custom-mode', mode, '--pos', position)
        with (out / 'shell.log').open('w') as log:
            preview = subprocess.Popen(['quickshell', '--no-color', '-p', str(shell / 'bar-test.qml')],
                                       env=env, stdout=log, stderr=log)
            processes.append(preview)

        def ipc(*words):
            return run('quickshell', 'ipc', '-p', shell / 'bar-test.qml', 'call', 'testbar', *words)

        def state():
            return json.loads(ipc('frameState'))

        # A failed QML process should expose its log rather than become an IPC timeout.
        for _ in range(100):
            assert preview.poll() is None, (out / 'shell.log').read_text()
            try:
                if len(state()['surfaces']) == 2:
                    break
            except subprocess.CalledProcessError:
                pass
            time.sleep(.05)
        assert len(state()['surfaces']) == 2
        pointer_path = base / 'pointer'
        subprocess.run(['gcc', str(SOURCE / 'dev/virtual-pointer.c'), '-lwayland-client', '-o', str(pointer_path)], check=True)
        pointer = subprocess.Popen([str(pointer_path)], env=env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, text=True)
        processes.append(pointer)
        assert pointer.stdout.readline().strip() == 'READY'
        pointer.stdin.write('move 200 200 1924 1600\n')
        pointer.stdin.flush()
        assert pointer.stdout.readline().strip() == 'OK'
        ipc('cover', 'false')

        for mode, suffix in (('client-header', '.h'), ('private-code', '.c')):
            subprocess.run(['wayland-scanner', mode, str(SOURCE / 'dev/wlr-screencopy-unstable-v1.xml'),
                            str(base / ('screencopy-client' + suffix))], check=True)
        capture_path = base / 'raw-screencopy'
        subprocess.run(['gcc', '-std=c11', '-Wall', '-Wextra', '-Wno-unused-parameter',
                        '-Werror', str(SOURCE / 'dev/raw-screencopy.c'),
                        str(base / 'screencopy-client.c'), '-I', str(base),
                        '-lwayland-client', '-o', str(capture_path)], check=True)

        def snapshot(label, check_pixels):
            validate_preview(preview, out / 'shell.log')
            actual = state()
            print('Frame snapshot:', label, json.dumps(actual), flush=True)
            for name in names:
                path = out / f'{label}-{name}.png'
                output = next(o for o in json.loads(run('wlr-randr', '--json')) if o['name'] == name)
                scale = output['scale']
                # Grim defaults to the highest scale across outputs, even with
                # -o. Bind the capture to this output's actual physical scale.
                run('grim', '-o', name, '-s', scale, out / f'grim-{label}-{name}.png')
                # Read the native output buffer without resampling rounded
                # logical output dimensions. Keep Grim's image for comparison.
                raw = base / 'capture.ppm'
                run(capture_path, name, raw)
                with Image.open(raw) as native:
                    mode = next(m for m in output['modes'] if m['current'])
                    assert native.size == (mode['width'], mode['height']), (name, native.size, mode)
                    native.save(path)
                with Image.open(path) as capture:
                    surface = next(s for s in actual['surfaces'] if s['screen'] == name)
                    expected = (round(capture.width / scale), round(capture.height / scale))
                    # Require configured native dimensions, not just requested Theme margins.
                    if abs(surface['width'] - expected[0]) > 1 or abs(surface['height'] - expected[1]) > 1:
                        # Validate before classifying the baseline mismatch as a reproduction.
                        validate_preview(preview, out / 'shell.log')
                        raise FrameGeometryError((label, surface, expected))
                    if check_pixels:
                        image = capture.convert('RGB')
                        ground = ImageColor.getrgb(actual['ground'])[:3]
                        for x, y in ((capture.width // 2, 0),
                                     (capture.width // 2, capture.height - 1),
                                     (0, capture.height // 2),
                                     (capture.width - 1, capture.height // 2),
                                     (capture.width // 2, round(2 * scale)),
                                     (capture.width // 2, capture.height - 1 - round(2 * scale)),
                                     (round(2 * scale), capture.height // 2),
                                     (capture.width - 1 - round(2 * scale), capture.height // 2)):
                            pixel = image.getpixel((x, y))
                            assert max(abs(a - b) for a, b in zip(pixel, ground)) <= 3, (label, name, (x, y), pixel, ground)
                        # Detect an old inset ring still painted beneath the hidden bar.
                        # Overscan must not move/thin the original inner right or
                        # bottom edge. Sample just outside each expected hairline.
                        for x, y in inner_frame_probe_points(surface, scale, actual['frameWidth'],
                                                             capture.width, capture.height):
                            pixel = image.getpixel((x, y))
                            assert max(abs(a - b) for a, b in zip(pixel, ground)) <= 3, (label, name, 'inner frame moved', (x, y), pixel, ground)
                        edge = label.split('-')[1]
                        x, y = {'top': (capture.width // 2, round(58 * scale)),
                                'bottom': (capture.width // 2, capture.height - round(58 * scale)),
                                'left': (round(58 * scale), capture.height // 2),
                                'right': (capture.width - round(58 * scale), capture.height // 2)}[edge]
                        assert image.getpixel((x, y)) == (33, 131, 79), (label, name, 'interior is not backdrop')
            results.append(dict(case=label, state=actual))

        if not is_sway and not frame_source:
            # Exercise the real installer too: its single persistent Top window
            # receives closed when all outputs disappear, unlike the frame's
            # per-screen Variants. Readiness alone cannot prove it remapped.
            installer_source = SOURCE.parent / 'installer-ui'
            installer_env = dict(env, ARCTIC_INSTALLER_BRIDGE='python3 ' +
                                 str(installer_source / 'dev/mock-bridge.py'),
                                 ARCTIC_LIVE_KEYBOARD='true',
                                 ARCTIC_MOCK_LOG=str(out / 'installer-engine.log'))
            with (out / 'installer.log').open('w') as log:
                installer = subprocess.Popen(['quickshell', '--no-color', '-p', str(installer_source)],
                                             env=installer_env, stdout=log, stderr=log)
                processes.append(installer)

            def installer_ipc(*words):
                validate_preview(installer, out / 'installer.log')
                return run('quickshell', 'ipc', '--pid', installer.pid, 'call', 'installer', *words)

            def installer_state():
                try:
                    return json.loads(installer_ipc('state'))
                except subprocess.CalledProcessError:
                    return {}

            def installer_ready(page, keyboard=None):
                actual = installer_state()
                return (actual.get('page') == page and actual.get('ready') is True
                        and (keyboard is None or actual.get('keyboard') == keyboard))

            wait(lambda: installer_ready('welcome'), 'private installer did not reach ready welcome')
            assert installer_ipc('next') == 'ok'
            wait(lambda: installer_ready('keyboard'), 'private keyboard form was not ready')
            assert installer_ipc('fill', json.dumps(dict(layout='de'))) == 'ok'
            wait(lambda: installer_ready('keyboard', 'de'), 'private keyboard choice did not save')
            initial_installer = installer_state()
            installer_pid = installer.pid

            def verify_installer(label):
                actual = installer_state()
                window = actual['window']
                assert actual['page'] == initial_installer['page'] == 'keyboard'
                assert actual['keyboard'] == initial_installer['keyboard'] == 'de'
                assert actual['connected'] is True and actual['ready'] is True and not actual['failure']
                assert window['visible'] is True and window['backing_visible'] is True
                layers = json.loads(run('mmsg', 'get', 'all-layers'))['layers']
                mapped = [layer for layer in layers if layer['name'] == 'arctic-installer']
                assert len(mapped) == 1 and mapped[0]['layer'] == 'top', mapped
                assert mapped[0]['monitor'] == window['screen'] and window['screen'] in names
                output = next(o for o in json.loads(run('wlr-randr', '--json'))
                              if o['name'] == window['screen'])
                mode = next(m for m in output['modes'] if m['current'])
                assert abs(window['width'] - mode['width'] / output['scale']) <= 1
                assert abs(window['height'] - mode['height'] / output['scale']) <= 1
                raw = base / 'installer-capture.ppm'
                run(capture_path, window['screen'], raw)
                with Image.open(raw) as image:
                    image.save(out / (label + '.png'))
                    pixel = image.convert('RGB').getpixel((image.width - 10, image.height // 2))
                    background = ImageColor.getrgb(window['background'])[:3]
                    assert max(abs(a - b) for a, b in zip(pixel, background)) <= 3, (label, pixel, background)
                assert installer.poll() is None and installer.pid == installer_pid
                assert (out / 'installer-engine.log').read_text().count('"method": "Hello"') == 1
                results.append(dict(case=label, installer_pid=installer_pid, state=actual, layers=mapped))
                print('Installer restoration:', label, json.dumps(actual), flush=True)

            ipc('cover', 'false')
            time.sleep(.3)
            verify_installer('installer-before-output-loss')
            # Exercise the real output destroy signal with Bottom/Top layers
            # and covered frame surfaces still mapped. Recreating all outputs
            # must retain the compositor and preview processes across cycles.
            compositor_pid = display.pid
            for cycle in range(3):
                ipc('cover', 'true')
                time.sleep(.2)
                run('mmsg', 'dispatch', 'destroy_all_virtual_output')
                assert display.poll() is None, (out / 'compositor.log').read_text()
                wait(lambda: not json.loads(run('wlr-randr', '--json')),
                     'destroyed outputs remain advertised')
                # Qt can retain a screen model while the backend has no
                # outputs. Record that transient state; require the real
                # output inventory to be empty and exact restored models below.
                transient = state()
                results.append(dict(case=f'outputs-unavailable-{cycle}', state=transient))
                print('No advertised outputs; transient Qt frame models:', json.dumps(transient), flush=True)
                for _ in range(2):
                    run('mmsg', 'dispatch', 'create_virtual_output')
                wait(lambda: len(json.loads(run('wlr-randr', '--json'))) == 2,
                     'recreated outputs were not advertised')
                names = sorted(output['name'] for output in json.loads(run('wlr-randr', '--json')))
                assert len(set(names)) == 2 and all(name.startswith('HEADLESS-') for name in names)
                for name, mode, position in zip(names, ('1024x768', '900x1600'), ('0,0', '1024,0')):
                    run('wlr-randr', '--output', name, '--custom-mode', mode, '--pos', position)
                def frames_restored():
                    surfaces = state()['surfaces']
                    return len(surfaces) == 2 and {surface['screen'] for surface in surfaces} == set(names)

                wait(frames_restored, 'frame surfaces did not return on recreated outputs')
                validate_preview(preview, out / 'shell.log')
                assert display.poll() is None and display.pid == compositor_pid
                ipc('cover', 'false')
                pointer.stdin.write('move 200 200 1924 1600\n')
                pointer.stdin.flush()
                assert pointer.stdout.readline().strip() == 'OK'
                time.sleep(.2)
                def installer_restored():
                    window = installer_state().get('window', {})
                    return (window.get('visible') is True and window.get('backing_visible') is True
                            and window.get('screen') in names)

                wait(installer_restored, 'installer did not show again after output restoration')
                verify_installer(f'installer-restored-{cycle}')
                results.append(dict(case=f'output-teardown-{cycle}', compositor_pid=compositor_pid,
                                    state=state()))
                print(f'Output teardown cycle {cycle}: same Mango/preview processes survived.', flush=True)
            stop(installer)

            # Exercise the production observer against actual private Mango and
            # Foot before the unchanged frame matrix. Keep its precision result
            # separate: this forced-software, headless rendering fixture is not
            # the ISO's guest graphics/session. Every failed bracket remains a
            # failed measurement; only the full paired ISO run can qualify it.
            observer_spec = importlib.util.spec_from_file_location('native_mapping_observer',
                SOURCE.parent / 'tools/performance/guest.py')
            observer = importlib.util.module_from_spec(observer_spec)
            observer_spec.loader.exec_module(observer)
            fields = ('PATH', 'HOME', 'LANG', 'XDG_RUNTIME_DIR', 'XDG_CONFIG_HOME',
                'XDG_CACHE_HOME', 'XDG_STATE_HOME', 'WAYLAND_DISPLAY',
                'MANGO_INSTANCE_SIGNATURE', 'DBUS_SESSION_BUS_ADDRESS',
                'QT_QPA_PLATFORM', 'QT_NO_XDG_DESKTOP_PORTAL')
            prefix = ['env'] + [f'{key}={env[key]}' for key in fields if key in env]
            observer.emit = lambda check, value: print('ARCTIC-PERFORMANCE ' + json.dumps(
                dict(stage='private-frame-fixture', check=check, value=value)), flush=True)
            measurements = []
            raw_observations = []
            for launch in range(4):
                brackets = []
                elapsed = observer.startup(prefix, ['foot'], ('foot',), timeout=30,
                    hold_seconds=.1, observations=brackets,
                    poll_seconds=observer.ROLE_POLL_SECONDS, label='private-foot')
                assert len(brackets) == 1
                bracket = brackets[0]
                limit = min(.005, elapsed*.025)
                raw_observations.append(bracket)
                measurements.append(dict(launch=launch, observed_seconds=elapsed,
                    lower_seconds=bracket['lower_seconds'], upper_seconds=bracket['upper_seconds'],
                    interval_seconds=bracket['interval_seconds'], observer=bracket['observer'],
                    precision_limit_seconds=limit, precision_valid=bracket['interval_seconds'] <= limit))
            precision = dict(case='native-foot-observer-precision',
                status=('measurement_precision_gate_passed' if all(m['precision_valid'] for m in measurements)
                        else 'measurement_precision_gate_failed'), measurements=measurements,
                scope='Private forced-software/headless fixture; not ISO qualification')
            (out / 'native-foot-precision.json').write_text(json.dumps(
                dict(precision, raw_observations=raw_observations), indent=2)+'\n')
            results.append(precision)
            print('ARCTIC-NATIVE-FOOT-PRECISION ' + json.dumps(precision), flush=True)

        # Keep mixed-DPI coverage and exercise both rounded physical axes.
        # One common scale-1 profile already covers both outputs; then scale
        # landscape and portrait independently to include the latter's
        # 1600/1.5 fractional logical height without duplicate captures.
        profiles = ((names[0], 1), (names[0], 1.5), (names[0], 2),
                    (names[1], 1.5), (names[1], 2))
        for scaled_output, scale in profiles:
            for name in names:
                run('wlr-randr', '--output', name, '--scale', scale if name == scaled_output else 1)
            suffix = '' if scaled_output == names[0] else '-portrait'
            for edge in ('top', 'bottom', 'left', 'right'):
                for cycle in range(3):
                    ipc('cover', 'false')
                    ipc('configure', edge, '56', 'false')
                    time.sleep(.3)
                    # Enter both hiding modes while the Bottom frame has no exposed pixels.
                    ipc('cover', 'true')
                    time.sleep(.2)
                    for mode in ('auto', 'always', 'dodge', 'always', 'auto'):
                        ipc('mode', mode)
                        time.sleep(.3)
                        if mode != 'always':
                            snapshot(f'covered-{edge}-{mode}-{scale}-{cycle}{suffix}', False)
                    ipc('cover', 'false')
                    wait(lambda: all(b['reveal'] == 0 for b in json.loads(ipc('state'))), 'auto bars did not hide')
                    # Capture after exposure and verify the visible artwork on all four edges.
                    time.sleep(.2)
                    snapshot(f'exposed-{edge}-auto-{scale}-{cycle}{suffix}', True)
                    before = state()
                    ipc('focus', names[0])
                    time.sleep(.3)
                    assert state()['surfaces'] == before['surfaces'], 'reveal resized the frame'
                    ipc('focus', names[0])
            # Both outputs remain independent at different scales and aspect ratios.
        validate_preview(preview, out / 'shell.log')
        return results
    finally:
        for process in reversed(processes):
            stop(process)
        (out / 'results.json').write_text(json.dumps(results, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compositor', default='sway')
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--baseline-ref')
    args = parser.parse_args()
    compositor = shutil.which(args.compositor)
    if not compositor:
        raise SystemExit('Missing compositor: ' + args.compositor)
    args.out.mkdir(parents=True, exist_ok=True)
    if args.baseline_ref:
        source = subprocess.check_output(['git', 'show', args.baseline_ref + ':shell/ScreenFrame.qml'], text=True)
        with tempfile.TemporaryDirectory(prefix='arctic-frame-baseline-') as temp:
            try:
                exercise(Path(temp), args.out / 'baseline', compositor, source)
                result = dict(reproduced=False, detail='baseline passed this replay')
            except FrameGeometryError as error:
                result = dict(reproduced=True, detail=str(error))
            (args.out / 'baseline-result.json').write_text(json.dumps(result, indent=2))
            print('Baseline:', json.dumps(result), flush=True)
    with tempfile.TemporaryDirectory(prefix='arctic-frame-candidate-') as temp:
        exercise(Path(temp), args.out / 'candidate', compositor)
    print('Screen frame: covered mode changes, four edges, three scales, two outputs and stable reveals passed.', flush=True)


if __name__ == '__main__':
    main()
