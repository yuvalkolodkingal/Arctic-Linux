"""Independent acceptance of exact-image prepared installer restoration evidence.

This contract does not qualify an image by itself. All twelve physical images
also require manual review, and the separate original native/install gates apply.
"""
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sys
from types import FunctionType

_ASSERTION_TOKEN = object()

PACKAGED_SOURCES = {('/usr/share/arctic/installer-ui/' + name): ('installer-ui/' + name)
                   for name in ('shell.qml', 'Engine.qml', 'Wizard.qml', 'Frame.qml', 'steps/KeyboardStep.qml')}
PACKAGED_SOURCES['/usr/bin/arctic-installer'] = 'packaging/arctic-linux.spec'
EXECUTION_FILES = tuple(sorted({
    '.github/workflows/installer-candidate-20261009.yml',
    *('tools/installer-qualification/' + name for name in
      ('runner.py', 'driver.py', 'controller.py', 'contract.py', 'evidence.py', 'guest.py', 'run-live.sh')),
    'tools/lib/container.sh', 'tools/lib/vmtest.py', 'tools/lib/iso_startup.py',
    'tools/performance/prepare-vm-tools.sh', 'tools/native-functional/prepare-taskbar-tools.sh',
    'tools/native-functional/fetch-image.py', 'tools/native-functional/screen-evidence.py', 'tools/native-functional/taskbar-display.py',
    'tools/native-functional/native_smoke.py', 'tools/native-functional/taskbar-runtime.py',
    'tools/native-functional/taskbar-screencopy.c', 'shell/dev/virtual-pointer.c',
    'shell/dev/wlr-screencopy-unstable-v1.xml'}))
CONTEXT_KEYS = {'schema', 'source_sha', 'iso_sha256', 'iso_bytes', 'execution_sha', 'binding_id',
                'checker_sha256', 'runtime_sha256', 'native_sha256', 'capture_sha256'}
GUEST_IMAGES = tuple(['baseline.png'] + [kind + '-' + str(cycle) + '.png' for kind in ('vt', 'output')
                                      for cycle in range(3)] + ['output-0-relocated.png', 'output-2-relocated.png'])
HOST_EXECUTION_FILES = ('tools/installer-qualification/driver.py', 'tools/installer-qualification/controller.py',
                        'tools/installer-qualification/run-live.sh', 'tools/native-functional/taskbar-display.py',
                        'tools/lib/vmtest.py', 'tools/lib/iso_startup.py')
REQUIRED_IMAGES = tuple(sorted(['installer/' + name for name in GUEST_IMAGES] +
                             ['host/installer-vt-away-' + str(cycle) + '.png' for cycle in range(3)]))
ARCHIVE_FILES = tuple(sorted({'execution.json', 'upload-screening.json', 'provision.log', 'capture-build.log',
    'installer-harness.log', 'vm-base-image-id.txt', 'vm-prepared-image-id.txt',
    'host/host-execution.json', 'host/installer-host-transitions.json', 'host/serial.log',
    'host/installer-port.log.bounded-prefix.bin', 'host/qemu-installer-live.log.bounded-prefix.bin',
    'installer/installer-report.json', 'installer/installer-state.json', 'installer/transport-manifest.json',
    'installer/installer-provenance.json', 'installer/serial-installer-report.json', *REQUIRED_IMAGES}))

KEYBOARD = {'layout': 'il', 'variant': '', 'xkb': {'layout': 'us,il', 'variant': '',
            'options': 'grp:alt_shift_toggle', 'keymap': 'us', 'latin': False}}


def require(value, message):
    if not value:
        error = RuntimeError(message)
        frame = sys._getframe(1)
        if frame.f_code.co_name == 'exact' and frame.f_globals.get('require') is require:
            frame = frame.f_back
        owner = frame.f_globals
        function = owner.get(frame.f_code.co_name)
        source = frame.f_code.co_filename
        known_owner = owner is globals() or (owner.get('require') is require and
            owner.get('__file__') == str(Path(__file__).with_name('active-contract.py')))
        if known_owner and type(function) is FunctionType and function.__code__ is frame.f_code:
            key = (source.rsplit('/', 1)[-1], frame.f_code.co_name,
                   frame.f_lineno - frame.f_code.co_firstlineno)
            code = _ASSERTION_SITES.get(key)
            if code is not None:
                error._arctic_installer_assertion = (_ASSERTION_TOKEN, code)
        del frame
        raise error


def digest(data):
    return hashlib.sha256(data).hexdigest()


def same(value, expected):
    return json.dumps(value, sort_keys=True, allow_nan=False) == json.dumps(expected, sort_keys=True, allow_nan=False)


def hash_value(value):
    return digest(json.dumps(value, sort_keys=True).encode())


def is_hash(value, length=64):
    return type(value) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', value) is not None


def packaged_source_hashes(tree):
    tree = Path(tree)
    result = {}
    for installed, source in PACKAGED_SOURCES.items():
        data = (tree / source).read_bytes()
        if installed == '/usr/bin/arctic-installer':
            # This exact generated entry point is the spec's current fallback.
            # An alternate dotfile wrapper is not silently accepted.
            require(not (tree / 'dotfiles/.local/bin/arctic-installer').exists(), 'alternate installer wrapper needs review')
            start = b"[ -f dotfiles/.local/bin/arctic-installer ] || cat > %{buildroot}%{_bindir}/arctic-installer << 'EOF'\n"
            require(data.count(start) == 1, 'installer wrapper source heredoc differs')
            data = data.split(start, 1)[1].split(b'\nEOF\n', 1)[0] + b'\n'
            require(data.startswith(b'#!/bin/sh\n') and data.endswith(b'exec quickshell -p /usr/share/arctic/installer-ui "$@"\n'),
                    'installer wrapper source differs')
        result[installed] = dict(bytes=len(data), sha256=digest(data))
    return result


def context_check(value):
    require(type(value) is dict and set(value) == CONTEXT_KEYS and value['schema'] == 'arctic-installer-context-v1',
            'installer context fields differ')
    require(all(is_hash(value[k], 40) for k in ('source_sha', 'execution_sha')) and
            all(is_hash(value[k]) for k in CONTEXT_KEYS if k.endswith('sha256')) and
            type(value['iso_bytes']) is int and 0 < value['iso_bytes'] < 2_000_000_000 and
            is_hash(value['binding_id'], 32), 'installer context identities differ')


def engine_check(value):
    require(type(value) is dict and set(value) == {'hello', 'wizard', 'welcome', 'keyboard', 'install'}, 'engine snapshot incomplete')
    hello = value['hello']
    require(hello.get('live') is True and hello.get('mock') is False and hello.get('state') == 'wizard' and
            hello.get('engine_version') == '1.2.1' and type(hello.get('protocol_version')) is int and
            hello['protocol_version'] == 1 and hello.get('firmware') in ('uefi', 'bios'), 'real engine identity differs')
    require(value['wizard']['current'] == 'keyboard' and value['wizard']['state'] == 'wizard' and
            value['keyboard']['data'] == KEYBOARD, 'actual engine prepared Hebrew state differs')
    options = value['install']['options']
    require(options.get('modules') == [] and not any(options.get(k) for k in ('progress', 'attention', 'failed')),
            'installer gate triggered installation work')


def identity_check(value, uid):
    require(type(value) is dict and set(value) == {'gui', 'bridge', 'daemon', 'service', 'listener'}, 'process proof incomplete')
    for name, owner, executable in (('gui', uid, '/usr/bin/quickshell'), ('bridge', uid, '/usr/bin/arctic-install'),
                                    ('daemon', 0, '/usr/bin/arcticd')):
        proc = value[name]
        require(type(proc['pid']) is int and proc['pid'] > 1 and type(proc['uid']) is int and proc['uid'] == owner and type(proc['ppid']) is int and proc['ppid'] >= 0 and
                type(proc['start_ticks']) is int and proc['start_ticks'] > 0 and proc['executable'] == executable and
                is_hash(proc['executable_sha256']) and proc['overrides_absent'] is True, 'actual process proof differs: ' + name)
    require(Path(value['gui']['argv'][0]).name == 'quickshell' and Path(value['bridge']['argv'][0]).name == 'arctic-install' and
            Path(value['daemon']['argv'][0]).name == 'arcticd' and value['gui']['argv'][1:] == ['-p', '/usr/share/arctic/installer-ui'] and len(value['gui']['argv']) == 3 and
            value['bridge']['argv'][1:] == ['bridge'] and len(value['bridge']['argv']) == 2 and
            len(value['daemon']['argv']) == 1 and value['bridge']['ppid'] == value['gui']['pid'], 'real process invocation/linkage differs')
    service = value['service']
    require(service['MainPID'] == str(value['daemon']['pid']) and service['ActiveState'] == 'active' and
            service['NRestarts'] == '0' and is_hash(service['InvocationID'], 32) and
            service['ExecMainStartTimestampMonotonic'].isdigit() and int(service['ExecMainStartTimestampMonotonic']) > 0,
            'actual engine service continuity proof differs')
    listener = value['listener']
    require(set(listener) == {'path', 'filesystem_device', 'filesystem_inode', 'uid', 'mode', 'stream_inode', 'serving_pid', 'listening_fds'} and
            listener['path'] == '/run/arcticd.sock' and type(listener['uid']) is int and listener['uid'] == 0 and listener['mode'] == 0o660 and
            listener['serving_pid'] == value['daemon']['pid'] and all(type(listener[k]) is int and listener[k] > 0 for k in
            ('filesystem_device', 'filesystem_inode', 'stream_inode')) and type(listener['listening_fds']) is list and
            1 <= len(listener['listening_fds']) <= 4 and len(set(listener['listening_fds'])) == len(listener['listening_fds']) and
            all(type(fd) is int and fd >= 0 for fd in listener['listening_fds']), 'default root serving listener differs')


def outputs_check(outputs, count):
    require(type(outputs) is list and len(outputs) <= 2 and len({o['name'] for o in outputs}) == len(outputs) and
            all(o.get('name') in ('Virtual-1', 'Virtual-2') and type(o.get('enabled')) is bool for o in outputs),
            'actual output inventory differs')
    enabled = [o for o in outputs if o['enabled']]
    require(len(enabled) == count, 'actual enabled output count differs')
    return enabled


def visible_check(item, count=2):
    state, visible, outputs = item['state'], item['visible'], item['outputs']
    require(state.get('page') == state.get('current') == 'keyboard' and state.get('keyboard') == 'il' and
            state.get('view') == 'step' and all(state.get(k) is True for k in ('connected', 'ready', 'valid')) and
            state.get('busy') is False and not any(state.get(k) for k in ('failure', 'error', 'fields')),
            'GUI prepared page/readiness changed')
    win = state['window']
    require(visible['window'] == win and win.get('visible') is True and win.get('backing_visible') is True,
            'actual backing window is not visible')
    layers = visible['layers']
    require(type(layers) is list and len(layers) == 1 and layers[0].get('name') == 'arctic-installer' and
            layers[0].get('layer') == 'top' and layers[0].get('monitor') == win['screen'], 'missing or duplicate mapped installer')
    enabled = outputs_check(outputs, count)
    matches = [o for o in enabled if o['name'] == win['screen']]
    require(len(matches) == 1 and visible['output'] == matches[0], 'window does not use actual enabled output')
    output = matches[0]
    modes = [m for m in output['modes'] if m.get('current') is True]
    require(len(modes) == 1 and output.get('transform') == 'normal', 'current physical mode differs')
    mode, scale = modes[0], output['scale']
    require(type(scale) in (int, float) and math.isfinite(scale) and .5 <= scale <= 3 and
            all(type(mode[k]) is int and 360 <= mode[k] <= 8192 for k in ('width', 'height')) and
            all(type(win[k]) in (int, float) and math.isfinite(win[k]) and abs(win[k] - mode[k] / scale) <= 1 for k in ('width', 'height')) and
            visible['physical_size'] == [mode['width'], mode['height']], 'installer full output geometry differs')


def capture_check(capture, expected_name, visible, files, image_loader):
    from PIL import Image, ImageColor
    require(capture.get('path') == expected_name and expected_name in files and
            files[expected_name]['bytes'] == capture['bytes'] and files[expected_name]['sha256'] == capture['sha256'],
            'capture inventory/hash binding differs')
    data = image_loader(expected_name)
    require(0 < len(data) <= 4 * 1024 * 1024 and len(data) == capture['bytes'] and digest(data) == capture['sha256'] and
            data.startswith(b'\x89PNG\r\n\x1a\n'), 'physical capture bytes differ')
    with Image.open(io.BytesIO(data)) as image:
        require(list(image.size) == visible['physical_size'] == capture['size'], 'capture physical dimensions differ')
        rgb = image.convert('RGB'); x, y = rgb.width - 10, rgb.height // 2
        require(capture['region'] == [x - 1, y - 1, x + 2, y + 2] and capture['tolerance'] == 3, 'capture pixel region differs')
        expected = list(ImageColor.getrgb(visible['window']['background'])[:3])
        pixels = [list(rgb.getpixel((xx, yy))) for yy in range(y - 1, y + 2) for xx in range(x - 1, x + 2)]
        require(expected == capture['background'] and pixels == capture['pixels'] and
                all(max(abs(a - b) for a, b in zip(pixel, expected)) <= 3 for pixel in pixels), 'installer physical pixels absent')


def validate_report(report, expected_context, files, image_loader, source_hashes=None):
    context_check(expected_context)
    require(report.get('schema') == 'arctic-live-installer-restoration-v1' and report.get('stage') == 'live' and
            report.get('status') == 'passed' and report.get('release_acceptance') is False and
            same(report.get('context'), expected_context) and report.get('errors') == [] and report.get('captures') == 9,
            'installer report failed or is not exact live context')
    require(type(report['desktop_uid']) is int and report['desktop_uid'] >= 1000 and
            re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', report['boot_id']) and
            type(report['active_desktop_session']) is str and report['active_desktop_session'] and
            type(report['original_vt']) is int and 1 <= report['original_vt'] <= 63 and report['original_vt'] != 6,
            'real boot/session/VT identity differs')
    baseline = report['baseline']; engine_check(baseline['engine']); identity_check(baseline['identities'], report['desktop_uid'])
    require(baseline['initial_wizard']['current'] == 'welcome' and baseline['rpc_peer']['uid'] == 0,
            'real initial wizard/root RPC peer differs')
    require(source_hashes is not None and same(baseline['packaged_sources'], source_hashes) and
            set(source_hashes) == set(PACKAGED_SOURCES), 'packaged GUI bytes differ from exact image source')
    keyboard = baseline['keyboard_files']
    require(set(keyboard) == {'/etc/arctic/mango/keyboard.conf', '/home/liveuser/.config/arctic/live-keyboard.conf'} and
            all(is_hash(v['sha256']) and type(v['bytes']) is int and 0 < v['bytes'] <= 16384 and
                type(v['mode']) is int and v['mode'] & 0o022 == 0 for v in keyboard.values()) and
            keyboard['/etc/arctic/mango/keyboard.conf']['uid'] == 0 and
            keyboard['/home/liveuser/.config/arctic/live-keyboard.conf']['uid'] == report['desktop_uid'], 'protected Hebrew config proof differs')
    drm = baseline['drm_heads']
    require(drm['pci_vendor'] == '0x1af4' and drm['pci_device'] == '0x1050' and
            drm['driver'].endswith('/virtio_gpu') and set(drm['outputs']) == {'Virtual-1', 'Virtual-2'} and
            all(drm['outputs']['Virtual-' + str(n + 1)]['head'] == n and
                type(drm['outputs']['Virtual-' + str(n + 1)]['connector_id']) is int and
                drm['outputs']['Virtual-' + str(n + 1)]['connector_id'] > 0 for n in (0, 1)), 'actual single virtio head binding differs')
    visible_check(baseline); capture_check(baseline['capture'], 'baseline.png', baseline['visible'], files, image_loader)
    cases = report['cases']
    require(type(cases) is list and len(cases) == 6 and all(type(c['cycle']) is int for c in cases) and [(c['kind'], c['cycle']) for c in cases] ==
            [(kind, cycle) for kind in ('vt', 'output') for cycle in range(3)], 'installer restoration matrix differs')
    requests = []
    for case in cases:
        require(case['status'] == 'passed', 'installer case failed')
        for key in ('engine', 'identities', 'keyboard_files', 'gui_log_counts'):
            require(same(case[key], baseline[key]), 'prepared engine/process/config state changed: ' + key)
        visible_check(case); capture_check(case['capture'], case['kind'] + '-' + str(case['cycle']) + '.png', case['visible'], files, image_loader)
        disruption = case['disruption']
        if case['kind'] == 'vt':
            away = disruption['away']
            require(away == disruption['request']['away'] and away['active'] is False and away['foreground'] == 'tty6' and
                    away['uid'] == report['desktop_uid'] and away['session'] == report['active_desktop_session'] and
                    away['vt'] == report['original_vt'] and disruption['returned_vt'] == report['original_vt'], 'actual VT-away/return proof differs')
            for key in ('engine', 'identities', 'keyboard_files', 'gui_log_counts'):
                require(same(disruption['prepared_state'][key], baseline[key]), 'VT-away changed prepared state')
            requests.append(disruption['request'])
        else:
            mode = 'all' if case['cycle'] == 1 else 'hosting-only'
            require(disruption['mode'] == mode and disruption['hosting_output'] in drm['outputs'] and
                    disruption['hosting_head'] == drm['outputs'][disruption['hosting_output']]['head'], 'lost hosting head identity differs')
            unavailable = disruption['unavailable']; count = 0 if mode == 'all' else 1
            outputs_check(unavailable['outputs'], count)
            require(unavailable['enabled_output_count'] == count, 'output absence observation differs')
            for key in ('engine', 'identities', 'keyboard_files', 'gui_log_counts'):
                require(same(unavailable[key], baseline[key]), 'output loss changed prepared state')
            if mode == 'all':
                require(unavailable['installer_layers'] == [], 'installer remained mapped without real output')
            else:
                visible_check(unavailable, 1)
                require(unavailable['visible']['window']['screen'] != disruption['hosting_output'], 'installer did not move from lost hosting output')
                capture_check(unavailable['capture'], 'output-' + str(case['cycle']) + '-relocated.png', unavailable['visible'], files, image_loader)
            request = disruption['restore_request']
            require(same(request['outputs'], unavailable['outputs']) and request['outputs_sha256'] == hash_value(unavailable['outputs']) and
                    request['enabled_output_count'] == count, 'host restore request differs from real guest absence')
            requests.extend([disruption['disconnect_request'], request])
    expected = [('vt-away', n) for n in range(3)] + [(kind, n) for n in range(3) for kind in ('output-disconnect', 'output-restore')]
    require([(r['kind'], r['cycle']) for r in requests] == expected and all(r['binding_id'] == expected_context['binding_id'] and
            r['boot_id'] == report['boot_id'] and r['schema'] == 'arctic-installer-request-v1' and
            r['engine_sha256'] == hash_value(baseline['engine']) for r in requests), 'actual disruption requests differ')
    cleanup, security = report['cleanup'], report['security']
    require(cleanup.get('errors') == [] and all(cleanup.get(k) is True for k in
            ('original_vt_restored', 'owned_gui_stopped', 'owned_bridge_stopped', 'engine_retained')) and
            cleanup.get('pretest_wizard_reset_claim') is False and cleanup.get('engine_snapshot_sha256') == hash_value(baseline['engine']), 'installer cleanup/retained engine proof differs')
    require(security.get('selinux') == 'Enforcing' and type(security.get('observed_new_avcs')) is int and security.get('observed_new_avcs') == 0 and
            type(security.get('audit_enabled')) is bool, 'live installer security interval failed')
    require({name for name in files if name.endswith('.png')} == set(GUEST_IMAGES), 'guest capture inventory differs')
    return dict(schema=report['schema'], status='passed_pending_manual_visual_review', cases=6, guest_images=list(GUEST_IMAGES),
                requests=requests, scope='Prepared idle Hebrew wizard; no in-flight installation preservation claim', release_acceptance=False)


def validate_execution(state, expected_image, execution_source, serial_bytes=None, image_loader=None):
    require(state.get('schema') == 'arctic-installer-execution-v1' and
            state.get('status') == 'live_installer_restoration_passed_pending_manual_visual_review' and
            state.get('release_acceptance') is False and same(state.get('image'), expected_image) and
            state.get('execution', {}).get('source_sha') == execution_source and is_hash(execution_source, 40), 'installer execution identity/status differs')
    context = state['context']; context_check(context)
    require(context['source_sha'] == expected_image['source_sha'] and context['iso_sha256'] == expected_image['sha256'] and
            context['iso_bytes'] == expected_image['bytes'] and context['execution_sha'] == execution_source,
            'installer context is not exact candidate/execution')
    inputs = state['source_inputs']
    require(set(inputs) == set(EXECUTION_FILES) and all(is_hash(v) for v in inputs.values()) and
            context['checker_sha256'] == inputs['tools/installer-qualification/guest.py'] and
            context['runtime_sha256'] == inputs['tools/native-functional/taskbar-runtime.py'] and
            context['native_sha256'] == inputs['tools/native-functional/native_smoke.py'], 'installer source input inventory differs')
    build = state['build']
    require(build.get('schema') == 'arctic-taskbar-tools-v1' and build.get('release_acceptance') is False and
            build['binaries']['raw-screencopy'] == context['capture_sha256'] and
            all(build['sources'][name] == inputs[name] for name in
                ('tools/native-functional/taskbar-screencopy.c', 'shell/dev/virtual-pointer.c', 'shell/dev/wlr-screencopy-unstable-v1.xml')),
            'physical capture compiler/source/ELF provenance differs')
    guest, host = state['guest'], state['host']
    require(guest.get('status') == 'passed' and same(guest.get('context'), context) and same(host.get('context'), context) and
            host.get('status') == 'host_completed_pending_guest_evidence_validation_and_visual_review' and
            host.get('iso_booted') is True and host.get('errors') == [] and
            host.get('owned_qemu_stopped') is True and host.get('owned_private_bus_closed') is True,
            'installer guest/host execution or cleanup failed')
    require(set(host['execution_inputs']) == set(HOST_EXECUTION_FILES) and
            all(inputs[name] == value for name, value in host['execution_inputs'].items()) and
            len(host['host_transitions']) == 9 and set(state['required_images']) == set(REQUIRED_IMAGES) and
            all(is_hash(v) for v in state['required_images'].values()), 'installer host input/capture inventory differs')
    proof = host['display_preparation']
    require(proof['controller_sha256'] == inputs['tools/native-functional/taskbar-display.py'] and
            proof['status'] == 'uiinfo_applied_pending_guest_two_output_evidence' and proof['gpu_id'] == 'arctic_taskbar_gpu' and
            proof['display_backend'] == 'dbus' and proof['qemu_uid'] == 0 and
            type(proof['qemu_pid']) is int and proof['qemu_pid'] > 1 and type(proof['qemu_uid']) is int and
            type(proof['bus_pid']) is int and proof['bus_pid'] > 1 and re.fullmatch(r':[0-9]+\.[0-9]+', proof['bus_owner']) and
            len(proof['heads']) == 2 and {h['head'] for h in proof['heads']} == {0, 1} and
            len({h['console_id'] for h in proof['heads']}) == 2 and len({h['device_address'] for h in proof['heads']}) == 1 and
            all(type(h['head']) is int and type(h['console_id']) is int and h['console_id'] >= 0 and
                h['width'] == 1280 and h['height'] == 720 for h in proof['heads']) and proof['guest_monitor_verification_required'] is True,
            'actual owned two-head display preparation differs')
    report = guest['report']
    require(same(report['context'], context) and report['status'] == 'passed' and report['release_acceptance'] is False and
            guest['collector']['boot_id'] == report['boot_id'] and guest['collector']['desktop_uid'] == report['desktop_uid'] and
            guest['collector']['active_desktop_session'] == report['active_desktop_session'], 'transport report identity differs')
    requests = []
    for case in report['cases']:
        d = case['disruption']
        requests.extend([d['request']] if case['kind'] == 'vt' else [d['disconnect_request'], d['restore_request']])
    require(same(guest['requests'], requests) and same([r['request'] for r in host['host_transitions']], requests),
            'host receipts do not match actual guest disruptions')
    expected = [('vt-away', n) for n in range(3)] + [(kind, n) for n in range(3) for kind in ('output-disconnect', 'output-restore')]
    require([(r['kind'], r['cycle']) for r in requests] == expected, 'host transition matrix differs')
    owners = set()
    for receipt in host['host_transitions']:
        request = receipt['request']
        # Guest emits sorted JSON using the same canonical serialization; this
        # binds each host operation to exactly one complete UART request.
        require(receipt['request_sha256'] == hash_value(request) and request['binding_id'] == context['binding_id'] and
                request['boot_id'] == report['boot_id'] and request['engine_sha256'] == hash_value(report['baseline']['engine']),
                'host UART request digest/boot/prepared state differs')
        if request['kind'] == 'vt-away':
            cap = receipt['capture']; name = 'installer-vt-away-' + str(request['cycle']) + '.png'
            require(cap['path'] == name and cap.get('console_pixel_guard_passed') is True and
                    cap.get('manual_console_review_required') is True and state['required_images']['host/' + name] == cap['sha256'] and
                    type(cap['bytes']) is int and 0 < cap['bytes'] <= 4 * 1024 * 1024, 'host VT console capture binding differs')
        else:
            transition = receipt['display']; head = request['hosting_head']
            expected_heads = ({0, 1} if request['kind'] == 'output-restore' else
                              (set() if request['mode'] == 'all' else {0, 1} - {head}))
            require(transition['schema'] == 'arctic-installer-host-output-v1' and transition['qemu_pid'] == proof['qemu_pid'] and
                    transition['qemu_uid'] == 0 and transition['gpu_id'] == proof['gpu_id'] and
                    re.fullmatch(r':[0-9]+\.[0-9]+', transition['bus_owner']) and transition['enabled_heads'] == sorted(expected_heads) and
                    transition['applied'] == [dict(head=n, width=1280 if n in expected_heads else 0, height=720 if n in expected_heads else 0,
                                                   xoff=n * 1280, yoff=0) for n in (0, 1)], 'host actual output operation differs')
            owners.add(transition['bus_owner'])
    require(host['firmware'] == report['baseline']['engine']['hello']['firmware'], 'host and actual engine firmware differ')
    argv = host['qemu_argv']
    require(type(argv) is list and argv[:11] == ['qemu-system-x86_64', '-machine', 'q35', '-accel', 'kvm', '-cpu', 'max', '-smp', '2', '-m', '4096'] and
            argv.count('-display') == 1 and re.fullmatch(r'dbus,addr=unix:path=/tmp/arctic-tb-display-[A-Za-z0-9_-]+/bus,gl=off', argv[argv.index('-display') + 1]) and
            argv.count('-S') == 1 and argv.count('-nic') == 1 and argv[argv.index('-nic') + 1] == 'none' and
            argv.count('virtio-vga,id=arctic_taskbar_gpu,max_outputs=2') == 1 and '-fsdev' not in argv and '-virtfs' not in argv and
            all('readonly=on' in argv[n + 1] or argv[n + 1].startswith('if=pflash,format=raw,unit=1,file=')
                for n, arg in enumerate(argv) if arg == '-drive'), 'installer VM hardware/isolation differs')
    auth = host['console_authentication']
    require(auth['status'] == 'exact_liveuser_uid_response' and is_hash(auth['nonce'], 32), 'actual console authentication receipt differs')
    require(type(serial_bytes) is bytes and len(serial_bytes) <= 8 * 1024 * 1024 and digest(serial_bytes) == guest['serial']['sha256'] == state['transport']['serial_sha256'] and
            len(serial_bytes) == guest['serial']['bytes'], 'protected actual serial identity differs')
    auth_lines = [line for line in serial_bytes.decode('utf-8').splitlines() if line.startswith('ARCTIC-CONSOLE-READY=')]
    require(auth_lines == ['ARCTIC-CONSOLE-READY=' + auth['nonce'] + ' user=liveuser uid=' + str(report['desktop_uid'])], 'actual live console UID response differs')
    require(image_loader is not None, 'physical host media replay required')
    for path, expected in state['required_images'].items():
        data = image_loader(path)
        require(0 < len(data) <= 4 * 1024 * 1024 and digest(data) == expected, 'required physical image map differs: ' + path)
    from PIL import Image
    for receipt in host['host_transitions'][:3]:
        cap = receipt['capture']; path = 'host/' + cap['path']; data = image_loader(path)
        require(len(data) == cap['bytes'] and digest(data) == cap['sha256'] == state['required_images'][path] and
                data.startswith(b'\x89PNG\r\n\x1a\n'), 'host VT-away capture bytes differ')
        with Image.open(io.BytesIO(data)) as image:
            require(image.size == (1280, 720), 'host VT-away physical dimensions differ')
            histogram = image.convert('L').histogram()
            require(sum(histogram[:17]) / (image.width * image.height) > .90 and sum(histogram[160:]) >= 30,
                    'host away capture no longer shows console pixel pattern')
    require(state['transport']['report_sha256'] == digest((json.dumps(report, sort_keys=True, allow_nan=False) + '\n').encode()), 'transport report serialized bytes differ')
    require(owners == {proof['bus_owner']}, 'owned QEMU display bus identity changed')
    require(state['transport']['status'] == 'passed' and state['transport']['report_path'] == 'installer/installer-report.json' and
            is_hash(state['transport']['report_sha256']), 'installer report transport binding differs')
    return dict(status='passed_pending_manual_visual_review', images=list(REQUIRED_IMAGES), release_acceptance=False)


# Closed source call sites. IDs identify assertions, never private error values.
_ASSERTION_SITES = {
    ('contract.py', 'packaged_source_hashes', 8): 'idle-001',
    ('contract.py', 'packaged_source_hashes', 10): 'idle-002',
    ('contract.py', 'packaged_source_hashes', 12): 'idle-003',
    ('contract.py', 'context_check', 1): 'idle-004',
    ('contract.py', 'context_check', 3): 'idle-005',
    ('contract.py', 'engine_check', 1): 'idle-006',
    ('contract.py', 'engine_check', 3): 'idle-007',
    ('contract.py', 'engine_check', 6): 'idle-008',
    ('contract.py', 'engine_check', 9): 'idle-009',
    ('contract.py', 'identity_check', 1): 'idle-010',
    ('contract.py', 'identity_check', 5): 'idle-011',
    ('contract.py', 'identity_check', 8): 'idle-012',
    ('contract.py', 'identity_check', 13): 'idle-013',
    ('contract.py', 'identity_check', 18): 'idle-014',
    ('contract.py', 'outputs_check', 1): 'idle-015',
    ('contract.py', 'outputs_check', 5): 'idle-016',
    ('contract.py', 'visible_check', 2): 'idle-017',
    ('contract.py', 'visible_check', 7): 'idle-018',
    ('contract.py', 'visible_check', 10): 'idle-019',
    ('contract.py', 'visible_check', 14): 'idle-020',
    ('contract.py', 'visible_check', 17): 'idle-021',
    ('contract.py', 'visible_check', 19): 'idle-022',
    ('contract.py', 'capture_check', 2): 'idle-023',
    ('contract.py', 'capture_check', 6): 'idle-024',
    ('contract.py', 'capture_check', 9): 'idle-025',
    ('contract.py', 'capture_check', 11): 'idle-026',
    ('contract.py', 'capture_check', 14): 'idle-027',
    ('contract.py', 'validate_report', 2): 'idle-028',
    ('contract.py', 'validate_report', 6): 'idle-029',
    ('contract.py', 'validate_report', 12): 'idle-030',
    ('contract.py', 'validate_report', 14): 'idle-031',
    ('contract.py', 'validate_report', 17): 'idle-032',
    ('contract.py', 'validate_report', 23): 'idle-033',
    ('contract.py', 'validate_report', 30): 'idle-034',
    ('contract.py', 'validate_report', 34): 'idle-035',
    ('contract.py', 'validate_report', 36): 'idle-036',
    ('contract.py', 'validate_report', 41): 'idle-037',
    ('contract.py', 'validate_report', 45): 'idle-038',
    ('contract.py', 'validate_report', 49): 'idle-039',
    ('contract.py', 'validate_report', 53): 'idle-040',
    ('contract.py', 'validate_report', 55): 'idle-041',
    ('contract.py', 'validate_report', 57): 'idle-042',
    ('contract.py', 'validate_report', 60): 'idle-043',
    ('contract.py', 'validate_report', 63): 'idle-044',
    ('contract.py', 'validate_report', 67): 'idle-045',
    ('contract.py', 'validate_report', 71): 'idle-046',
    ('contract.py', 'validate_report', 74): 'idle-047',
    ('contract.py', 'validate_report', 76): 'idle-048',
    ('contract.py', 'validate_execution', 1): 'idle-049',
    ('contract.py', 'validate_execution', 6): 'idle-050',
    ('contract.py', 'validate_execution', 10): 'idle-051',
    ('contract.py', 'validate_execution', 15): 'idle-052',
    ('contract.py', 'validate_execution', 21): 'idle-053',
    ('contract.py', 'validate_execution', 26): 'idle-054',
    ('contract.py', 'validate_execution', 31): 'idle-055',
    ('contract.py', 'validate_execution', 42): 'idle-056',
    ('contract.py', 'validate_execution', 49): 'idle-057',
    ('contract.py', 'validate_execution', 52): 'idle-058',
    ('contract.py', 'validate_execution', 58): 'idle-059',
    ('contract.py', 'validate_execution', 63): 'idle-060',
    ('contract.py', 'validate_execution', 70): 'idle-061',
    ('contract.py', 'validate_execution', 76): 'idle-062',
    ('contract.py', 'validate_execution', 78): 'idle-063',
    ('contract.py', 'validate_execution', 85): 'idle-064',
    ('contract.py', 'validate_execution', 86): 'idle-065',
    ('contract.py', 'validate_execution', 89): 'idle-066',
    ('contract.py', 'validate_execution', 90): 'idle-067',
    ('contract.py', 'validate_execution', 93): 'idle-068',
    ('contract.py', 'validate_execution', 97): 'idle-069',
    ('contract.py', 'validate_execution', 100): 'idle-070',
    ('contract.py', 'validate_execution', 102): 'idle-071',
    ('contract.py', 'validate_execution', 104): 'idle-072',
    ('contract.py', 'validate_execution', 105): 'idle-073',
    ('contract.py', 'validate_execution', 106): 'idle-074',
    ('active-contract.py', 'exact', 1): 'active-001',
    ('active-contract.py', 'context_check', 1): 'active-002',
    ('active-contract.py', 'context_check', 2): 'active-003',
    ('active-contract.py', 'context_check', 6): 'active-004',
    ('active-contract.py', 'engine_check', 1): 'active-005',
    ('active-contract.py', 'engine_check', 3): 'active-006',
    ('active-contract.py', 'engine_check', 5): 'active-007',
    ('active-contract.py', 'engine_check', 8): 'active-008',
    ('active-contract.py', 'engine_check', 9): 'active-009',
    ('active-contract.py', 'engine_check', 10): 'active-010',
    ('active-contract.py', 'engine_check', 11): 'active-011',
    ('active-contract.py', 'engine_check', 13): 'active-012',
    ('active-contract.py', 'engine_check', 14): 'active-013',
    ('active-contract.py', 'engine_check', 16): 'active-014',
    ('active-contract.py', 'engine_check', 17): 'active-015',
    ('active-contract.py', 'engine_check', 21): 'active-016',
    ('active-contract.py', 'engine_check', 22): 'active-017',
    ('active-contract.py', 'engine_check', 27): 'active-018',
    ('active-contract.py', 'engine_check', 29): 'active-019',
    ('active-contract.py', 'engine_check', 30): 'active-020',
    ('active-contract.py', 'identity_check', 3): 'active-021',
    ('active-contract.py', 'identity_check', 4): 'active-022',
    ('active-contract.py', 'target_check', 1): 'active-023',
    ('active-contract.py', 'target_check', 2): 'active-024',
    ('active-contract.py', 'writer_check', 1): 'active-025',
    ('active-contract.py', 'writer_check', 3): 'active-026',
    ('active-contract.py', 'writer_check', 4): 'active-027',
    ('active-contract.py', 'writer_check', 13): 'active-028',
    ('active-contract.py', 'writer_check', 14): 'active-029',
    ('active-contract.py', 'visible_check', 2): 'active-030',
    ('active-contract.py', 'visible_check', 3): 'active-031',
    ('active-contract.py', 'config_check', 1): 'active-032',
    ('active-contract.py', 'config_check', 2): 'active-033',
    ('active-contract.py', 'config_check', 4): 'active-034',
    ('active-contract.py', 'config_check', 6): 'active-035',
    ('active-contract.py', 'config_check', 8): 'active-036',
    ('active-contract.py', 'keyboard_check', 1): 'active-037',
    ('active-contract.py', 'keyboard_check', 5): 'active-038',
    ('active-contract.py', 'keyboard_check', 6): 'active-039',
    ('active-contract.py', 'sample_check', 2): 'active-040',
    ('active-contract.py', 'sample_check', 10): 'active-041',
    ('active-contract.py', 'sample_check', 12): 'active-042',
    ('active-contract.py', 'sample_check', 14): 'active-043',
    ('active-contract.py', 'sample_check', 20): 'active-044',
    ('active-contract.py', 'sample_check', 21): 'active-045',
    ('active-contract.py', 'sample_check', 24): 'active-046',
    ('active-contract.py', 'sample_check', 25): 'active-047',
    ('active-contract.py', 'sample_check', 28): 'active-048',
    ('active-contract.py', 'validate_catalog_selection', 2): 'active-049',
    ('active-contract.py', 'validate_catalog_selection', 7): 'active-050',
    ('active-contract.py', 'validate_catalog_selection', 11): 'active-051',
    ('active-contract.py', 'validate_catalog_selection', 13): 'active-052',
    ('active-contract.py', 'validate_catalog_selection', 16): 'active-053',
    ('active-contract.py', 'validate_report', 2): 'active-054',
    ('active-contract.py', 'validate_report', 5): 'active-055',
    ('active-contract.py', 'validate_report', 9): 'active-056',
    ('active-contract.py', 'validate_report', 16): 'active-057',
    ('active-contract.py', 'validate_report', 20): 'active-058',
    ('active-contract.py', 'validate_report', 25): 'active-059',
    ('active-contract.py', 'validate_report', 26): 'active-060',
    ('active-contract.py', 'validate_report', 28): 'active-061',
    ('active-contract.py', 'validate_report', 31): 'active-062',
    ('active-contract.py', 'validate_report', 33): 'active-063',
    ('active-contract.py', 'validate_report', 34): 'active-064',
    ('active-contract.py', 'validate_report', 40): 'active-065',
    ('active-contract.py', 'validate_report', 41): 'active-066',
    ('active-contract.py', 'validate_report', 44): 'active-067',
    ('active-contract.py', 'validate_report', 51): 'active-068',
    ('active-contract.py', 'validate_report', 56): 'active-069',
    ('active-contract.py', 'validate_report', 58): 'active-070',
    ('active-contract.py', 'validate_report', 61): 'active-071',
    ('active-contract.py', 'validate_report', 63): 'active-072',
    ('active-contract.py', 'validate_report', 67): 'active-073',
    ('active-contract.py', 'validate_report', 73): 'active-074',
    ('active-contract.py', 'validate_report', 75): 'active-075',
    ('active-contract.py', 'validate_report', 78): 'active-076',
    ('active-contract.py', 'validate_report', 79): 'active-077',
    ('active-contract.py', 'validate_report', 82): 'active-078',
    ('active-contract.py', 'validate_report', 86): 'active-079',
    ('active-contract.py', 'validate_report', 95): 'active-080',
    ('active-contract.py', 'validate_report', 97): 'active-081',
    ('active-contract.py', 'validate_report', 101): 'active-082',
    ('active-contract.py', 'validate_report', 104): 'active-083',
    ('active-contract.py', 'validate_report', 106): 'active-084',
    ('active-contract.py', 'validate_report', 111): 'active-085',
    ('active-contract.py', 'validate_report', 115): 'active-086',
    ('active-contract.py', 'validate_report', 119): 'active-087',
    ('active-contract.py', 'validate_report', 121): 'active-088',
    ('active-contract.py', 'validate_report', 124): 'active-089',
    ('active-contract.py', 'validate_report', 125): 'active-090',
    ('active-contract.py', 'validate_report', 126): 'active-091',
    ('active-contract.py', 'validate_report', 131): 'active-092',
    ('active-contract.py', 'validate_report', 134): 'active-093',
    ('active-contract.py', 'validate_report', 135): 'active-094',
    ('active-contract.py', 'validate_report', 137): 'active-095',
    ('active-contract.py', 'disk_io_check', 1): 'active-096',
    ('active-contract.py', 'disk_io_check', 3): 'active-097',
    ('active-contract.py', 'disk_io_check', 5): 'active-098',
    ('active-contract.py', 'disk_io_check', 9): 'active-099',
    ('active-contract.py', 'disk_io_check', 10): 'active-100',
    ('active-contract.py', 'disk_io_check', 12): 'active-101',
    ('active-contract.py', 'pairs', 3): 'active-102',
    ('active-contract.py', 'strict_json', 7): 'active-103',
    ('active-contract.py', 'installed_boot_check', 1): 'active-104',
    ('active-contract.py', 'installed_boot_check', 3): 'active-105',
    ('active-contract.py', 'installed_boot_check', 9): 'active-106',
    ('active-contract.py', 'installed_boot_check', 10): 'active-107',
    ('active-contract.py', 'installed_boot_check', 13): 'active-108',
    ('active-contract.py', 'installed_boot_check', 14): 'active-109',
    ('active-contract.py', 'installed_boot_check', 17): 'active-110',
    ('active-contract.py', 'installed_boot_check', 20): 'active-111',
    ('active-contract.py', 'installed_boot_check', 21): 'active-112',
    ('active-contract.py', 'installed_boot_check', 23): 'active-113',
    ('active-contract.py', 'installed_boot_check', 24): 'active-114',
    ('active-contract.py', 'installed_boot_check', 28): 'active-115',
    ('active-contract.py', 'installed_boot_check', 32): 'active-116',
    ('active-contract.py', 'installed_boot_check', 34): 'active-117',
    ('active-contract.py', 'installed_boot_check', 36): 'active-118',
    ('active-contract.py', 'vm_argv_check', 1): 'active-119',
    ('active-contract.py', 'vm_argv_check', 6): 'active-120',
    ('active-contract.py', 'vm_argv_check', 12): 'active-121',
    ('active-contract.py', 'vm_argv_check', 15): 'active-122',
    ('active-contract.py', 'vm_argv_check', 17): 'active-123',
    ('active-contract.py', 'vm_argv_check', 21): 'active-124',
    ('active-contract.py', 'vm_argv_check', 23): 'active-125',
    ('active-contract.py', 'vm_argv_check', 26): 'active-126',
    ('active-contract.py', 'vm_argv_check', 33): 'active-127',
    ('active-contract.py', 'vm_argv_check', 36): 'active-128',
    ('active-contract.py', 'vm_argv_check', 38): 'active-129',
    ('active-contract.py', 'vm_argv_check', 40): 'active-130',
    ('active-contract.py', 'vm_argv_check', 43): 'active-131',
    ('active-contract.py', 'password_prompts_check', 1): 'active-132',
    ('active-contract.py', 'password_prompts_check', 3): 'active-133',
    ('active-contract.py', 'password_prompts_check', 4): 'active-134',
    ('active-contract.py', 'password_prompts_check', 8): 'active-135',
    ('active-contract.py', 'password_prompts_check', 12): 'active-136',
    ('active-contract.py', 'password_prompts_check', 13): 'active-137',
    ('active-contract.py', 'password_prompts_check', 23): 'active-138',
    ('active-contract.py', 'password_prompts_check', 27): 'active-139',
    ('active-contract.py', 'password_prompts_check', 33): 'active-140',
    ('active-contract.py', 'password_prompts_check', 36): 'active-141',
    ('active-contract.py', 'exported_inventories_check', 6): 'active-142',
    ('active-contract.py', 'exported_inventories_check', 10): 'active-143',
    ('active-contract.py', 'exported_inventories_check', 11): 'active-144',
    ('active-contract.py', 'exported_inventories_check', 20): 'active-145',
    ('active-contract.py', 'exported_inventories_check', 22): 'active-146',
    ('active-contract.py', 'exported_inventories_check', 27): 'active-147',
    ('active-contract.py', 'exported_inventories_check', 28): 'active-148',
    ('active-contract.py', 'exported_inventories_check', 29): 'active-149',
    ('active-contract.py', 'exported_inventories_check', 32): 'active-150',
    ('active-contract.py', 'exported_inventories_check', 34): 'active-151',
    ('active-contract.py', 'exported_inventories_check', 39): 'active-152',
    ('active-contract.py', 'exported_inventories_check', 41): 'active-153',
    ('active-contract.py', 'exported_inventories_check', 43): 'active-154',
    ('active-contract.py', 'exported_inventories_check', 50): 'active-155',
    ('active-contract.py', 'exported_inventories_check', 53): 'active-156',
    ('active-contract.py', 'exported_inventories_check', 59): 'active-157',
    ('active-contract.py', 'exported_inventories_check', 61): 'active-158',
    ('active-contract.py', 'exported_inventories_check', 63): 'active-159',
    ('active-contract.py', 'exported_inventories_check', 65): 'active-160',
    ('active-contract.py', 'exported_inventories_check', 69): 'active-161',
    ('active-contract.py', 'exported_inventories_check', 70): 'active-162',
    ('active-contract.py', 'exported_inventories_check', 72): 'active-163',
    ('active-contract.py', 'exported_inventories_check', 74): 'active-164',
    ('active-contract.py', 'exported_inventories_check', 76): 'active-165',
    ('active-contract.py', 'exported_inventories_check', 77): 'active-166',
    ('active-contract.py', 'exported_inventories_check', 79): 'active-167',
    ('active-contract.py', 'exported_inventories_check', 84): 'active-168',
    ('active-contract.py', 'exported_inventories_check', 87): 'active-169',
    ('active-contract.py', 'exported_inventories_check', 89): 'active-170',
    ('active-contract.py', 'exported_inventories_check', 92): 'active-171',
    ('active-contract.py', 'exported_inventories_check', 94): 'active-172',
    ('active-contract.py', 'exported_inventories_check', 96): 'active-173',
    ('active-contract.py', 'exported_inventories_check', 97): 'active-174',
    ('active-contract.py', 'exported_inventories_check', 98): 'active-175',
    ('active-contract.py', 'exported_inventories_check', 101): 'active-176',
    ('active-contract.py', 'exported_inventories_check', 103): 'active-177',
    ('active-contract.py', 'exported_inventories_check', 106): 'active-178',
    ('active-contract.py', 'exported_inventories_check', 113): 'active-179',
    ('active-contract.py', 'exported_inventories_check', 115): 'active-180',
    ('active-contract.py', 'exported_inventories_check', 118): 'active-181',
    ('active-contract.py', 'exported_inventories_check', 119): 'active-182',
    ('active-contract.py', 'exported_inventories_check', 125): 'active-183',
    ('active-contract.py', 'exported_inventories_check', 128): 'active-184',
    ('active-contract.py', 'exported_inventories_check', 129): 'active-185',
    ('active-contract.py', 'exported_inventories_check', 131): 'active-186',
    ('active-contract.py', 'validate_execution', 2): 'active-187',
    ('active-contract.py', 'validate_execution', 9): 'active-188',
    ('active-contract.py', 'validate_execution', 13): 'active-189',
    ('active-contract.py', 'validate_execution', 20): 'active-190',
    ('active-contract.py', 'validate_execution', 25): 'active-191',
    ('active-contract.py', 'validate_execution', 29): 'active-192',
    ('active-contract.py', 'validate_execution', 30): 'active-193',
    ('active-contract.py', 'validate_execution', 34): 'active-194',
    ('active-contract.py', 'validate_execution', 44): 'active-195',
    ('active-contract.py', 'validate_execution', 45): 'active-196',
    ('active-contract.py', 'validate_execution', 48): 'active-197',
    ('active-contract.py', 'validate_execution', 52): 'active-198',
    ('active-contract.py', 'validate_execution', 58): 'active-199',
    ('active-contract.py', 'validate_execution', 61): 'active-200',
    ('active-contract.py', 'validate_execution', 67): 'active-201',
    ('active-contract.py', 'validate_execution', 73): 'active-202',
    ('active-contract.py', 'validate_execution', 78): 'active-203',
    ('active-contract.py', 'validate_execution', 80): 'active-204',
    ('active-contract.py', 'validate_execution', 81): 'active-205',
    ('active-contract.py', 'validate_execution', 83): 'active-206',
    ('active-contract.py', 'validate_execution', 85): 'active-207',
    ('active-contract.py', 'validate_execution', 88): 'active-208',
    ('active-contract.py', 'validate_execution', 93): 'active-209',
    ('active-contract.py', 'validate_execution', 95): 'active-210',
    ('active-contract.py', 'validate_execution', 97): 'active-211',
    ('active-contract.py', 'validate_execution', 99): 'active-212',
    ('active-contract.py', 'validate_execution', 105): 'active-213',
    ('active-contract.py', 'validate_execution', 106): 'active-214',
}
