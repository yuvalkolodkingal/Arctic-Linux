"""Independent acceptance of in-flight exact-image installer restoration.

Synthetic controls exercise this contract; they do not qualify an ISO. The
idle restoration lane remains required, and all seven active-lane physical
captures require independent manual review before publication.
"""
import importlib.util
import io
import json
from pathlib import Path
import re
import tomllib

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('active_installer_idle_primitives', HERE / 'contract.py')
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)
require, digest, same, hash_value, is_hash = C.require, C.digest, C.same, C.hash_value, C.is_hash
PACKAGED_SOURCES = dict(C.PACKAGED_SOURCES, **{'/usr/share/arctic/catalog/catalog.toml': 'modules/catalog.toml'})
KEYBOARD = C.KEYBOARD
GUI_FILES = tuple('''Engine.qml Frame.qml Theme.qml Wizard.qml shell.qml qmldir
components/AppGroupHeader.qml components/AppRow.qml components/AppTile.qml components/ArBanner.qml
components/ArButton.qml components/ArCard.qml components/ArCheck.qml components/ArCheckIndicator.qml
components/ArDialog.qml components/ArInput.qml components/ArKbd.qml components/ArList.qml components/ArListRow.qml
components/ArMeter.qml components/ArProgress.qml components/ArRadio.qml components/ArSelect.qml components/ArSteps.qml
components/ArTag.qml components/ArText.qml components/ArToggle.qml components/AuroraBand.qml components/CornerMask.qml
components/FocusRing.qml components/Icon.qml components/Mark.qml components/ShadowRect.qml components/Wordmark.qml components/qmldir
steps/AccountStep.qml steps/AppsStep.qml steps/AttentionView.qml steps/DiskStep.qml steps/DoneStep.qml steps/EncryptionStep.qml
steps/InstallStep.qml steps/KeyboardStep.qml steps/NetworkStep.qml steps/StepPage.qml steps/SummaryStep.qml steps/TimezoneStep.qml
steps/WelcomeStep.qml steps/qmldir'''.split())
PACKAGED_SOURCES.update({'/usr/share/arctic/installer-ui/' + name: 'installer-ui/' + name for name in GUI_FILES})
CONTEXT_KEYS = C.CONTEXT_KEYS | {'active_checker_sha256', 'installed_checker_sha256', 'disk_serial', 'disk_bytes', 'disk_node', 'write_bps'}
GUEST_IMAGES = ('baseline.png', 'vt-0.png', 'output-0-relocated.png', 'output-0.png')
REQUIRED_IMAGES = tuple(sorted(['installer/' + name for name in GUEST_IMAGES] +
    ['host/installer-vt-away-0.png', 'host/installed-getty-password.png', 'host/installed-sudo-password.png']))
EXECUTION_FILES = tuple(sorted((set(C.EXECUTION_FILES) - {'.github/workflows/installer-candidate-20261009.yml'}) |
    {'.github/workflows/installer-active-candidate-20261009.yml', 'tools/installer-qualification/active-contract.py',
     'tools/installer-qualification/active-guest.py', 'tools/installer-qualification/installed-guest.py'}))
HOST_EXECUTION_FILES = C.HOST_EXECUTION_FILES
ARCHIVE_FILES = tuple(sorted((set(C.ARCHIVE_FILES) - set(C.REQUIRED_IMAGES)) | set(REQUIRED_IMAGES) |
    {'host/installed-boot.json', 'host/serial-installed.log', 'host/qemu-installer-installed.log.bounded-prefix.bin'}))
PROCESS_KEYS = {'pid', 'uid', 'start_ticks', 'ppid', 'executable', 'executable_sha256', 'argv', 'overrides_absent'}
ENGINE_KEYS = {'hello', 'wizard', 'keyboard', 'install'}
GUI_KEYS = {'page', 'current', 'view', 'valid', 'busy', 'ready', 'connected', 'failure', 'error', 'fields', 'keyboard', 'percent', 'window'}
SAMPLE_KEYS = {'engine', 'identities', 'keyboard_files', 'config', 'writer', 'elapsed_ns'}
RSYNC_ARGS = ['-aAXH', '--numeric-ids', '--info=progress2', '--no-inc-recursive', '--filter=-x security.selinux'] + [
    '--exclude=' + name for name in ('/dev/*', '/proc/*', '/sys/*', '/run/*', '/tmp/*', '/mnt/*', '/media/*', '/var/tmp/*',
    '/boot/efi/', '/boot/loader/entries/*', '/boot/initramfs-*', '/boot/vmlinuz-0-rescue-*', '/var/cache/dnf/*',
    '/var/cache/libdnf5/*', '/etc/machine-id', '/lost+found')] + ['/run/rootfsbase/', '/mnt/']


def exact(value, keys, message):
    require(type(value) is dict and set(value) == set(keys), message)


def packaged_source_hashes(tree):
    result = C.packaged_source_hashes(tree)
    for installed, source in PACKAGED_SOURCES.items():
        if installed in result:
            continue
        data = (Path(tree) / source).read_bytes()
        result[installed] = dict(bytes=len(data), sha256=digest(data))
    return result


def context_check(value):
    exact(value, CONTEXT_KEYS, 'active installer context fields differ')
    require(value['schema'] == 'arctic-installer-active-context-v1', 'active installer context schema differs')
    idle = {key: value[key] for key in C.CONTEXT_KEYS}
    idle['schema'] = 'arctic-installer-context-v1'
    C.context_check(idle)
    require(is_hash(value['active_checker_sha256']) and is_hash(value['installed_checker_sha256']) and type(value['disk_serial']) is str and
            re.fullmatch('arctic-a-[0-9a-f]{11}', value['disk_serial']) and
            type(value['disk_bytes']) is int and value['disk_bytes'] == 64 * 1024 ** 3 and
            value['disk_node'] == 'target0' and type(value['write_bps']) is int and value['write_bps'] == 8 * 1024 ** 2,
            'active installer owned target or write throttle differs')


def engine_check(value, completed=False):
    exact(value, ENGINE_KEYS, 'active engine projection contains missing or private fields')
    hello = value['hello']
    exact(hello, {'engine_version', 'protocol_version', 'mock', 'live', 'firmware', 'state'}, 'active Hello projection differs')
    phase = 'done' if completed else 'installing'
    require(hello['engine_version'] == '1.2.1' and type(hello['protocol_version']) is int and hello['protocol_version'] == 1 and
            hello['mock'] is False and hello['live'] is True and hello['firmware'] == 'uefi' and hello['state'] == phase,
            'actual active engine identity/state differs')
    exact(value['wizard'], {'current', 'state'}, 'active wizard projection contains private fields')
    require(value['wizard'] == {'current': 'done' if completed else 'install', 'state': phase}, 'active wizard page/state differs')
    exact(value['keyboard'], {'id', 'data'}, 'active keyboard projection differs')
    require(value['keyboard']['id'] == 'keyboard' and same(value['keyboard']['data'], KEYBOARD), 'active Hebrew choice changed')
    install = value['install']
    exact(install, {'id', 'options'}, 'active install projection contains private fields')
    require(install['id'] == 'install', 'active install step differs')
    options = install['options']
    exact(options, {'modules', 'progress', 'attention', 'failed'}, 'active install options contain private fields')
    require(options['attention'] is False and options['failed'] is False and type(options['modules']) is list,
            'active engine paused or failed')
    module_ids = []
    for module in options['modules']:
        exact(module, {'id', 'status', 'percent'}, 'active module projection contains private fields')
        require(type(module['id']) is str and re.fullmatch('[a-z0-9][a-z0-9_-]{0,63}', module['id']) and
                (module['status'] in ('installed', 'skipped', 'deferred') if completed else module['status'] == 'queued') and
                type(module['percent']) is int and (0 <= module['percent'] <= 100 if completed else module['percent'] == 0),
                'actual queued/completed application module proof differs')
        module_ids.append(module['id'])
    require(len(set(module_ids)) == len(module_ids), 'duplicate active queued module')
    progress = options['progress']
    exact(progress, {'event', 'percent', 'phase', 'apps_done', 'apps_total', 'paused'}, 'active progress projection contains private fields')
    require(progress['event'] == 'progress' and progress['paused'] is False and type(progress['percent']) is int and
            (progress['percent'] == 100 if completed else 0 < progress['percent'] < 100) and
            (progress['phase'] == 'finalize' if completed else progress['phase'] == 'copy') and
            all(type(progress[key]) is int and progress[key] >= 0 for key in ('apps_done', 'apps_total')) and
            progress['apps_done'] <= progress['apps_total'], 'active progress is idle, regressed, paused or failed')
    return progress['percent']


def identity_check(value, uid):
    C.identity_check(value, uid)
    for key in ('gui', 'bridge', 'daemon'):
        exact(value[key], PROCESS_KEYS, 'active process projection contains private fields: ' + key)
    exact(value['service'], {'MainPID', 'InvocationID', 'ExecMainStartTimestampMonotonic', 'ActiveState', 'NRestarts'},
          'active engine service contains private fields')


def target_check(value, context):
    exact(value, {'path', 'sysfs', 'serial', 'disk_bytes', 'major_minor'}, 'active disk projection differs')
    require(value['path'] == '/dev/vda' and value['sysfs'] == '/sys/class/block/vda' and
            value['serial'] == context['disk_serial'] and type(value['disk_bytes']) is int and value['disk_bytes'] == context['disk_bytes'] and
            type(value['major_minor']) is str and re.fullmatch('[1-9][0-9]{0,4}:[0-9]{1,5}', value['major_minor']),
            'active writer target is not the owned serial disk')


def writer_check(value, identities, target):
    exact(value, {'process', 'ancestor_pids', 'mount', 'target_serial'}, 'active writer projection differs')
    proc = value['process']
    exact(proc, PROCESS_KEYS, 'active writer process contains private fields')
    require(type(proc['pid']) is int and proc['pid'] > 1 and proc['uid'] == 0 and type(proc['uid']) is int and
            proc['ppid'] == identities['daemon']['pid'] and type(proc['ppid']) is int and
            type(proc['start_ticks']) is int and proc['start_ticks'] > 0 and proc['executable'] == '/usr/bin/rsync' and
            is_hash(proc['executable_sha256']) and proc['overrides_absent'] is True and
            type(proc['argv']) is list and len(proc['argv']) == len(RSYNC_ARGS) + 1 and
            proc['argv'][0] in ('rsync', '/usr/bin/rsync') and proc['argv'][1:] == RSYNC_ARGS and
            value['ancestor_pids'] == [proc['pid'], identities['daemon']['pid']] and value['target_serial'] == target['serial'],
            'writer is not the original root copy directly owned by this engine')
    mount = value['mount']
    exact(mount, {'target', 'source', 'block_source', 'fstype', 'major_minor'}, 'active writer mount projection differs')
    require(mount['target'] == '/mnt' and mount['fstype'] == 'btrfs' and type(mount['source']) is str and
            type(mount['block_source']) is str and re.fullmatch('/dev/vda[1-9][0-9]?', mount['block_source']) and
            (mount['source'] == mount['block_source'] or re.fullmatch(re.escape(mount['block_source']) + r'\[/[A-Za-z0-9_@/-]{1,128}\]', mount['source'])) and
            type(mount['major_minor']) is str and
            re.fullmatch('[1-9][0-9]{0,4}:[0-9]{1,5}', mount['major_minor']) and mount['major_minor'] != target['major_minor'],
            'active writer destination is not an owned target partition')


def visible_check(item, count=2):
    state = item['state']
    exact(state, GUI_KEYS, 'active GUI projection contains private fields')
    require(state['page'] == state['current'] == 'install' and state['keyboard'] == 'il' and state['view'] == 'step' and
            all(state[key] is True for key in ('valid', 'ready', 'connected')) and state['busy'] is False and
            state['failure'] == state['error'] == '' and state['fields'] == {} and type(state['percent']) is int and
            0 < state['percent'] < 100, 'active GUI page/readiness/progress differs')
    # Replay the same actual physical geometry and exactly-one-layer checks as
    # the independent idle contract after translating only its expected page.
    idle = dict(item, state=dict(state, page='keyboard', current='keyboard'))
    C.visible_check(idle, count)


def config_check(value):
    exact(value, {'network', 'disk', 'encryption', 'apps'}, 'active installer configuration contains private fields')
    require(value['disk'] == {'disk': '/dev/vda', 'mode': 'erase'} and
            value['encryption'] == {'enabled': False} and value['network'] == {'offline': True}, 'active installation target/mode or explicit offline choice differs')
    require(value['encryption']['enabled'] is False and value['network']['offline'] is True,
            'explicit offline and encryption choices must be real booleans')
    exact(value['apps'], {'selection'}, 'active apps configuration projection differs')
    selections = value['apps']['selection']
    require(type(selections) is dict and len(selections) <= 64 and all(type(key) is str and
            re.fullmatch('[a-z0-9_-]{1,64}', key) and type(modules) is list and len(modules) <= 64 and
            len(set(modules)) == len(modules) and all(type(module) is str and re.fullmatch('[a-z0-9_-]{1,64}', module)
            for module in modules) for key, modules in selections.items()), 'active app selection identifiers differ')


def keyboard_check(value, uid):
    require(type(value) is dict and set(value) == {'/etc/arctic/mango/keyboard.conf', '/home/liveuser/.config/arctic/live-keyboard.conf'},
            'active protected Hebrew config inventory differs')
    for path, owner in (('/etc/arctic/mango/keyboard.conf', 0), ('/home/liveuser/.config/arctic/live-keyboard.conf', uid)):
        item = value[path]
        exact(item, {'bytes', 'sha256', 'uid', 'mode'}, 'active Hebrew config projection differs')
        require(type(item['bytes']) is int and 0 < item['bytes'] <= 16384 and is_hash(item['sha256']) and
                type(item['uid']) is int and item['uid'] == owner and type(item['mode']) is int and
                0 <= item['mode'] <= 0o7777 and item['mode'] & 0o022 == 0, 'active protected Hebrew config proof differs')


def sample_check(value, baseline, uid, target, completed=False):
    for key in SAMPLE_KEYS - {'writer'} if completed else SAMPLE_KEYS:
        require(key in value, 'active sample is incomplete: ' + key)
    percent = engine_check(value['engine'], completed)
    identity_check(value['identities'], uid)
    keyboard_check(value['keyboard_files'], uid)
    config_check(value['config'])
    selections = value['config']['apps']['selection']
    selected = [module for category, modules in selections.items() if category != 'drivers' for module in modules]
    module_ids = [module['id'] for module in value['engine']['install']['options']['modules']]
    require(len(set(selected)) == len(selected) and set(module_ids) == set(selected), 'active queued module inventory differs from armed app choices')
    progress = value['engine']['install']['options']['progress']
    require(progress['apps_total'] == len(module_ids) and progress['apps_done'] == (len(module_ids) if completed else 0),
            'actual active/completed application counters differ from queued module inventory')
    require(type(value['elapsed_ns']) is int and 0 < value['elapsed_ns'] <= 3600 * 1_000_000_000,
            'active sample monotonic time differs')
    if not completed:
        writer_check(value['writer'], value['identities'], target)
    if baseline is not None:
        for key in ('identities', 'keyboard_files', 'config'):
            require(same(value[key], baseline[key]), 'in-flight installation identity/config changed: ' + key)
        require(same(value['engine']['hello'] | {'state': 'installing'}, baseline['engine']['hello']) and
                same(value['engine']['keyboard'], baseline['engine']['keyboard']), 'in-flight engine or keyboard changed')
        if not completed:
            require(same(value['writer'], baseline['writer']), 'original active writer was replaced')
            require(same(value['engine']['install']['options']['modules'], baseline['engine']['install']['options']['modules']),
                    'queued app module inventory/state changed during root copy')
        else:
            require(module_ids == [module['id'] for module in baseline['engine']['install']['options']['modules']],
                    'completed application module inventory differs from armed copy')
    return percent


def validate_catalog_selection(report, catalog_bytes):
    """Resolve only visible selected app IDs in the actual candidate catalog order."""
    require(type(catalog_bytes) is bytes and 0 < len(catalog_bytes) <= 1024 * 1024, 'candidate catalog bytes exceeded bounds')
    catalog = tomllib.loads(catalog_bytes.decode('utf-8'))
    categories = catalog['category']
    selected = report['baseline']['config']['apps']['selection']
    inventory = {category['id']: category for category in categories}
    require(len(inventory) == len(categories) and set(selected) <= set(inventory), 'armed active app category differs from candidate catalog')
    expected = []
    for category in categories:
        modules = selected.get(category['id'], [])
        require(set(modules) <= set(category['modules']), 'armed active module differs from candidate catalog category')
        if category.get('hardware', False):
            require(category['id'] == 'drivers', 'active source catalog has an unreviewed hardware category')
            continue
        expected.extend(module for module in category['modules'] if module in modules)
    require([module['id'] for module in report['baseline']['engine']['install']['options']['modules']] == expected and
            [module['id'] for module in report['completion']['engine']['install']['options']['modules']] == expected,
            'active queued/completed module order differs from the actual candidate catalog')
    return expected


def validate_report(report, expected_context, files, image_loader, source_hashes=None):
    context_check(expected_context)
    exact(report, {'schema', 'stage', 'status', 'context', 'boot_id', 'desktop_uid', 'active_desktop_session',
                  'original_vt', 'release_acceptance', 'evidence_root', 'baseline', 'cases', 'samples', 'completion',
                  'cleanup', 'security', 'errors', 'captures'}, 'active report contains missing or private fields')
    require(report['schema'] == 'arctic-live-installer-active-restoration-v1' and report['stage'] == 'live' and
            report['status'] == 'passed' and report['release_acceptance'] is False and same(report['context'], expected_context) and
            report['errors'] == [] and type(report['captures']) is int and report['captures'] == 4,
            'active installer report failed or differs from exact live context')
    require(type(report['desktop_uid']) is int and report['desktop_uid'] >= 1000 and
            type(report['boot_id']) is str and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', report['boot_id']) and
            type(report['active_desktop_session']) is str and re.fullmatch('[A-Za-z0-9_-]{1,64}', report['active_desktop_session']) and
            type(report['original_vt']) is int and 1 <= report['original_vt'] <= 63 and report['original_vt'] != 6 and
            type(report['evidence_root']) is str and re.fullmatch('/tmp/arctic-native-smoke-installer-[A-Za-z0-9_-]+', report['evidence_root']),
            'active real boot/session/VT or evidence identity differs')
    baseline = report['baseline']
    exact(baseline, SAMPLE_KEYS | {'target_disk', 'drm_heads', 'packaged_sources', 'state', 'outputs', 'visible', 'capture', 'rpc_peer', 'scope'},
          'active baseline contains missing or private fields')
    target_check(baseline['target_disk'], expected_context)
    sample_check(baseline, None, report['desktop_uid'], baseline['target_disk'])
    require(type(baseline['packaged_sources']) is dict and set(baseline['packaged_sources']) == set(PACKAGED_SOURCES) and
            all(type(item) is dict and set(item) == {'bytes', 'sha256'} and type(item['bytes']) is int and
                0 < item['bytes'] <= 4 * 1024 * 1024 and is_hash(item['sha256']) for item in baseline['packaged_sources'].values()) and
            (source_hashes is None or same(baseline['packaged_sources'], source_hashes)), 'active packaged GUI source bytes differ')
    peer = baseline['rpc_peer']
    exact(peer, {'uid', 'gid', 'pid_claim'}, 'active engine RPC peer projection contains private fields')
    require(type(peer['uid']) is int and peer['uid'] == 0 and type(peer['gid']) is int and peer['gid'] >= 0 and
            peer['pid_claim'] == 'none; socket activation can report systemd', 'active engine RPC peer is not the protected root socket')
    require(baseline['scope'] == 'Owned 64 GiB unencrypted offline UEFI install; original copy writer continues through disruptions',
            'active installation scope differs')
    drm = baseline['drm_heads']
    exact(drm, {'card', 'device', 'driver', 'pci_address', 'pci_vendor', 'pci_device', 'outputs', 'binding'},
          'active DRM projection contains private fields')
    exact(drm['outputs'], {'Virtual-1', 'Virtual-2'}, 'active DRM connector inventory differs')
    require(type(drm['card']) is str and re.fullmatch('card[0-9]+', drm['card']) and
            type(drm['device']) is str and drm['device'].startswith('/sys/devices/') and
            type(drm['pci_address']) is str and re.fullmatch(r'[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]', drm['pci_address']) and
            drm['binding'] == 'single Linux virtio_gpu scanout index order; Virtual-1=0, Virtual-2=1',
            'active physical DRM binding differs')
    for name, output in drm['outputs'].items():
        exact(output, {'head', 'connector', 'connector_id', 'sysfs_path'}, 'active DRM output projection contains private fields')
        require(output['connector'] == drm['card'] + '-' + name and type(output['sysfs_path']) is str and
                output['sysfs_path'].startswith('/sys/devices/') and Path(output['sysfs_path']).name == output['connector'],
                'active physical DRM connector path differs')
    require(drm['pci_vendor'] == '0x1af4' and drm['pci_device'] == '0x1050' and drm['driver'].endswith('/virtio_gpu') and
            set(drm['outputs']) == {'Virtual-1', 'Virtual-2'} and all(drm['outputs']['Virtual-' + str(n + 1)]['head'] == n and
            type(drm['outputs']['Virtual-' + str(n + 1)]['connector_id']) is int and drm['outputs']['Virtual-' + str(n + 1)]['connector_id'] > 0
            for n in (0, 1)), 'active actual single virtio head binding differs')
    visible_check(baseline)
    C.capture_check(baseline['capture'], 'baseline.png', baseline['visible'], files, image_loader)
    cases = report['cases']
    require(type(cases) is list and [(case['kind'], case['cycle']) for case in cases] == [('vt', 0), ('output', 0)],
            'active restoration transition matrix differs')
    observations = [baseline]
    requests = []
    for case in cases:
        exact(case, SAMPLE_KEYS | {'kind', 'cycle', 'status', 'disruption', 'state', 'outputs', 'visible', 'capture'},
              'active case contains missing or private fields')
        require(type(case['cycle']) is int and case['status'] == 'passed', 'active restoration case failed')
        if case['kind'] == 'vt':
            disruption = case['disruption']
            exact(disruption, {'away', 'request', 'prepared_state', 'returned_vt'}, 'active VT disruption projection differs')
            away = disruption['away']
            require(away == disruption['request']['away'] and away == dict(active=False, foreground='tty6', uid=report['desktop_uid'],
                    session=report['active_desktop_session'], vt=report['original_vt']) and disruption['returned_vt'] == report['original_vt'],
                    'active actual VT away/return differs')
            snapshot = disruption['prepared_state']
            exact(snapshot, SAMPLE_KEYS, 'active VT-away sample projection differs')
            observations.append(snapshot)
            requests.append(disruption['request'])
            request_snapshots = [(disruption['request'], snapshot)]
        else:
            disruption = case['disruption']
            exact(disruption, {'mode', 'hosting_output', 'hosting_head', 'disconnect_request', 'before', 'unavailable', 'restore_request'},
                  'active output disruption projection differs')
            require(disruption['mode'] == 'hosting-only' and disruption['hosting_output'] in drm['outputs'] and
                    disruption['hosting_head'] == drm['outputs'][disruption['hosting_output']]['head'], 'active lost hosting head differs')
            before, absent = disruption['before'], disruption['unavailable']
            exact(before, SAMPLE_KEYS, 'active output before sample projection differs')
            exact(absent, SAMPLE_KEYS | {'enabled_output_count', 'state', 'outputs', 'visible', 'capture'},
                  'active output absence projection differs')
            visible_check(absent, 1)
            require(absent['enabled_output_count'] == 1 and absent['visible']['window']['screen'] != disruption['hosting_output'],
                    'active installer did not relocate from lost hosting output')
            C.capture_check(absent['capture'], 'output-0-relocated.png', absent['visible'], files, image_loader)
            restore = disruption['restore_request']
            require(same(restore['outputs'], absent['outputs']) and restore['outputs_sha256'] == hash_value(absent['outputs']) and
                    restore['enabled_output_count'] == 1, 'active restore request does not bind output absence')
            observations.extend([before, absent])
            requests.extend([disruption['disconnect_request'], restore])
            request_snapshots = [(disruption['disconnect_request'], before), (restore, absent)]
        observations.append(case)
        visible_check(case)
        C.capture_check(case['capture'], case['kind'] + '-0.png', case['visible'], files, image_loader)
        for request, snapshot in request_snapshots:
            require(request['engine_sha256'] == hash_value(snapshot['engine']) and type(request.get('elapsed_ns')) is int and
                    request['elapsed_ns'] == snapshot['elapsed_ns'], 'active host request does not bind current writer engine')
    require([(request['kind'], request['cycle']) for request in requests] == [('vt-away', 0), ('output-disconnect', 0), ('output-restore', 0)] and
            all(request['schema'] == 'arctic-installer-request-v1' and request['binding_id'] == expected_context['binding_id'] and
                request['boot_id'] == report['boot_id'] for request in requests), 'active host requests differ from actual transitions')
    samples = report['samples']
    require(type(samples) is list and len(observations) <= len(samples) <= 512, 'active observation sample inventory differs')
    previous_ns, previous_percent = 0, 0
    for sample in samples:
        exact(sample, SAMPLE_KEYS, 'active observation sample projection contains private fields')
        percent = sample_check(sample, baseline, report['desktop_uid'], baseline['target_disk'])
        require(sample['elapsed_ns'] > previous_ns and percent >= previous_percent, 'active observer time/progress regressed')
        previous_ns, previous_percent = sample['elapsed_ns'], percent
    previous_ns, previous_percent, previous_gui_percent = 0, 0, 0
    for observation in observations:
        percent = sample_check(observation, baseline, report['desktop_uid'], baseline['target_disk'])
        require(observation['elapsed_ns'] > previous_ns and percent >= previous_percent and
                any(same(sample, {key: observation[key] for key in SAMPLE_KEYS}) for sample in samples),
                'active transition does not bind an ordered independent writer sample')
        gui_percent = observation.get('state', {}).get('percent', previous_gui_percent)
        require(gui_percent >= previous_gui_percent, 'active GUI progress regressed')
        previous_ns, previous_percent = observation['elapsed_ns'], percent
        previous_gui_percent = gui_percent
    completion = report['completion']
    exact(completion, (SAMPLE_KEYS - {'writer'}) | {'gui'}, 'active completion projection contains private fields')
    sample_check(completion, baseline, report['desktop_uid'], baseline['target_disk'], completed=True)
    require(completion['elapsed_ns'] > samples[-1]['elapsed_ns'] and completion['gui'] == {'page': 'done', 'current': 'done', 'percent': 100},
            'same installation did not complete after active restoration')
    security = report['security']
    exact(security, {'selinux', 'audit', 'observed_new_avcs', 'audit_enabled', 'scope'}, 'active security projection contains private fields')
    exact(security['audit'], {'enabled', 'lost'}, 'active audit projection contains private fields')
    require(type(security['audit']['enabled']) is int and security['audit']['enabled'] in (0, 1, 2) and
            type(security['audit']['lost']) is int and security['audit']['lost'] >= 0 and
            security['audit_enabled'] is (security['audit']['enabled'] in (1, 2)) and security['scope'] ==
            'journal cursor and available audit-file interval; disabled kernel audit is a recorded telemetry limit',
            'active security telemetry projection differs')
    require(security.get('selinux') == 'Enforcing' and type(security.get('observed_new_avcs')) is int and security['observed_new_avcs'] == 0 and
            type(security.get('audit_enabled')) is bool, 'active live installer security interval failed')
    cleanup = report['cleanup']
    exact(cleanup, {'original_vt_restored', 'engine_retained', 'errors'}, 'active cleanup projection differs')
    require(cleanup['errors'] == [] and all(cleanup[key] is True for key in ('original_vt_restored', 'engine_retained')),
            'active cleanup does not retain the completed engine')
    require({name for name in files if name.endswith('.png')} == set(GUEST_IMAGES), 'active guest physical image inventory differs')
    return dict(schema=report['schema'], status='passed_pending_manual_visual_review', cases=2, guest_images=list(GUEST_IMAGES),
                requests=requests, scope='Original root copy writer continued through VT-away and hosting-output loss; same unencrypted offline UEFI installation completed',
                release_acceptance=False)


def disk_io_check(value, context):
    exact(value, {'node_name', 'before', 'after', 'write_bps', 'target_file', 'target_serial', 'inserted_node_name', 'inserted_readonly'},
          'active QMP write-counter fields differ')
    require(value['node_name'] == context['disk_node'] and type(value['write_bps']) is int and value['write_bps'] == context['write_bps'],
            'active QMP writes target another disk or throttle')
    require(type(value['target_file']) is str and value['target_file'].startswith('/') and Path(value['target_file']).name == 'target.qcow2' and
            value['target_serial'] == context['disk_serial'] and value['inserted_node_name'] == context['disk_node'] and
            value['inserted_readonly'] is False, 'active QMP inserted block device differs from owned target')
    for key in ('before', 'after'):
        exact(value[key], {'wr_bytes', 'wr_operations', 'monotonic_ns'}, 'active QMP write sample fields differ')
        require(all(type(value[key][field]) is int and value[key][field] >= 0 for field in ('wr_bytes', 'wr_operations', 'monotonic_ns')),
                'active QMP write counters are not actual integers')
    require(value['after']['wr_bytes'] > value['before']['wr_bytes'] and
            value['after']['wr_operations'] > value['before']['wr_operations'] and
            value['after']['monotonic_ns'] > value['before']['monotonic_ns'],
            'owned target did not receive real writes during restoration')


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate active evidence JSON key')
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs, parse_constant=lambda _: require(False, 'nonfinite active evidence JSON'))


def installed_boot_check(value, context, live_report, live_pid, serial_bytes):
    exact(value, {'status', 'live_qemu_pid', 'installed_qemu_pid', 'qemu_argv', 'target', 'boot_id', 'parent_live_boot_id',
                  'selinux', 'root', 'keyboard', 'authentication', 'serial', 'receipt_sha256'}, 'active installed boot fields differ')
    require(value['status'] == 'passed' and type(value['live_qemu_pid']) is int and value['live_qemu_pid'] == live_pid and
            type(value['installed_qemu_pid']) is int and value['installed_qemu_pid'] > 1 and value['installed_qemu_pid'] != live_pid and
            type(value['boot_id']) is str and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', value['boot_id']) and
            value['boot_id'] != live_report['boot_id'] and value['parent_live_boot_id'] == live_report['boot_id'] and
            value['selinux'] == 'Enforcing', 'same active target did not receive a fresh enforcing installed boot')
    target = value['target']
    exact(target, {'path', 'virtual_bytes', 'serial', 'backing_file'}, 'active installed target fields differ')
    require(target['path'] == 'target.qcow2' and type(target['virtual_bytes']) is int and target['virtual_bytes'] == context['disk_bytes'] and
            target['serial'] == context['disk_serial'] and target['backing_file'] is False, 'installed boot uses a different or backed target disk')
    root = value['root']
    exact(root, {'source', 'block_source', 'fstype', 'serial'}, 'active installed root projection differs')
    require(root['block_source'] == live_report['baseline']['writer']['mount']['block_source'] and root['fstype'] == 'btrfs' and
            root['serial'] == context['disk_serial'] and (root['source'] == root['block_source'] or
            re.fullmatch(re.escape(root['block_source']) + r'\[/[A-Za-z0-9_@/-]{1,128}\]', root['source'])), 'installed root is not the original writer target')
    require(value['keyboard'] == {'xkb_layout': 'us,il', 'xkb_options': 'grp:alt_shift_toggle', 'vconsole_keymap': 'us'},
            'active installed Hebrew keyboard configuration changed')
    auth = value['authentication']
    exact(auth, {'nonce', 'username', 'uid', 'status'}, 'active installed authentication fields differ')
    require(is_hash(auth['nonce'], 32) and auth['username'] == 'arcticqual' and type(auth['uid']) is int and auth['uid'] == 1000 and
            auth['status'] == 'exact_installed_uid_response', 'actual installed account console response differs')
    exact(value['serial'], {'bytes', 'sha256'}, 'active installed serial identity fields differ')
    require(type(serial_bytes) is bytes and 0 < len(serial_bytes) <= 8 * 1024 * 1024 and type(value['serial']['bytes']) is int and
            len(serial_bytes) == value['serial']['bytes'] and digest(serial_bytes) == value['serial']['sha256'], 'active installed original serial bytes differ')
    rows = serial_bytes.decode('utf-8').splitlines()
    ready = 'ARCTIC-ACTIVE-INSTALLED-READY=' + auth['nonce'] + ' user=arcticqual uid=1000'
    require([line for line in rows if line.startswith('ARCTIC-ACTIVE-INSTALLED-READY=')] == [ready] and
            rows.index(ready) + 1 < len(rows) and rows[rows.index(ready) + 1].startswith('ARCTIC-ACTIVE-INSTALLED '),
            'actual installed UID response is absent, duplicated or separated from root helper report')
    records = [strict_json(line.removeprefix('ARCTIC-ACTIVE-INSTALLED ')) for line in rows if line.startswith('ARCTIC-ACTIVE-INSTALLED ')]
    require(len(records) == 1, 'active installed protected report absent or duplicated')
    report = records[0]
    exact(report, {'schema', 'context', 'boot_id', 'selinux', 'root', 'keyboard', 'authentication', 'release_acceptance'},
          'active installed report contains private fields')
    require(report['schema'] == 'arctic-active-installed-boot-v1' and report['release_acceptance'] is False and same(report['context'], context) and
            all(same(report[key], value[key]) for key in ('boot_id', 'selinux', 'root', 'keyboard', 'authentication')) and
            value['receipt_sha256'] == digest(json.dumps(report, sort_keys=True, allow_nan=False).encode('ascii')),
            'active installed protected report context/hash differs')
    return report


def vm_argv_check(argv, context, installed=False):
    require(type(argv) is list and all(type(arg) is str for arg in argv) and argv[:11] ==
            ['qemu-system-x86_64', '-machine', 'q35', '-accel', 'kvm', '-cpu', 'max', '-smp', '2', '-m', '4096'] and
            argv.count('-nic') == 1 and argv[argv.index('-nic') + 1] == 'none' and
            not any(arg in argv for arg in ('-fsdev', '-virtfs', '-kernel', '-initrd', '-append', '-hda', '-hdb', '-hdd', '-blockdev')),
            'active VM hardware or isolation differs')
    require(argv.count('-display') == 1 and re.fullmatch(r'dbus,addr=unix:path=/tmp/arctic-tb-display-[A-Za-z0-9_-]+/bus,gl=off',
            argv[argv.index('-display') + 1]) and argv.count('virtio-vga,id=arctic_taskbar_gpu,max_outputs=2') == 1,
            'active VM actual two-output display differs')
    drives = []
    for index, arg in enumerate(argv):
        if arg == '-drive':
            require(index + 1 < len(argv), 'active drive arguments are incomplete')
            options = {}
            for item in argv[index + 1].split(','):
                require('=' in item, 'active VM drive syntax differs')
                key, value = item.split('=', 1)
                require(key not in options, 'duplicate active VM drive option')
                options[key] = value
            drives.append(options)
    targets = [drive for drive in drives if drive.get('node-name') == context['disk_node']]
    require(len(targets) == 1, 'active VM requires exactly one pinned target node')
    target = targets[0]
    require(target.get('format') == 'qcow2' and target.get('if') == 'none' and target.get('bps_wr') == str(context['write_bps']) and
            target.get('file', '').startswith('/') and Path(target['file']).name == 'target.qcow2' and target.get('readonly', 'off') == 'off' and
            type(target.get('id')) is str and re.fullmatch('[A-Za-z0-9_-]+', target['id']), 'active VM target or write throttle differs')
    require(argv.count('virtio-blk-pci,drive=' + target['id'] + ',serial=' + context['disk_serial'] +
                       (',bootindex=0' if installed else '')) == 1, 'active VM target serial/boot device differs')
    variables = []
    for drive in drives:
        if drive is target:
            continue
        if drive.get('if') == 'pflash' and drive.get('unit') == '1':
            require(drive.get('format') == 'raw' and Path(drive.get('file', '')).name == 'OVMF_VARS.fd', 'active VM firmware variables differ')
            variables.append(drive['file'])
        else:
            require(drive.get('readonly') == 'on' and (drive.get('media') == 'cdrom' or
                    drive.get('if') == 'pflash' and drive.get('unit') == '0'), 'active VM exposes another writable disk')
    require(len(variables) == 1, 'active VM requires one owned UEFI variable file')
    if installed:
        require(not any(drive.get('file') == '/iso' or drive.get('id') == 'live' for drive in drives) and
                not any('drive=live' in arg for arg in argv), 'fresh installed boot still exposes the live ISO')
    else:
        require(sum(drive.get('file') == '/iso' and drive.get('readonly') == 'on' for drive in drives) == 1,
                'active live VM does not boot the exact read-only ISO')
    return target['file'], variables[0]


def password_prompts_check(value, build, required_images, image_loader):
    exact(value, {'schema', 'engine', 'getty', 'sudo', 'login_shell', 'private_input_policy'}, 'active password prompt fields differ')
    shell = value['login_shell']
    exact(shell, {'prompt_kind', 'observed_line_sha256', 'observed_ns'}, 'active authenticated shell proof fields differ')
    require(shell['prompt_kind'] == 'installed-user-shell' and
            shell['observed_line_sha256'] == digest(b'arcticqual@arctic-qual ~ >') and
            type(shell['observed_ns']) is int and shell['observed_ns'] > 0,
            'active authenticated shell observed-line proof differs')
    require(value['schema'] == 'arctic-active-password-prompts-v1' and
            value['private_input_policy'] == 'Only after exact last console line; no secret-bearing screenshots or command text',
            'active private input policy or authenticated login prompt differs')
    engine = value['engine']
    exact(engine, {'packages', 'program_sha256', 'traineddata_sha256', 'version'}, 'active prompt OCR provenance fields differ')
    require(type(engine['packages']) is list and 1 <= len(engine['packages']) <= 32 and
            all(type(package) is str and re.fullmatch('[A-Za-z0-9_.:+-]{1,256}', package) for package in engine['packages']) and
            any(package.startswith('tesseract-') for package in engine['packages']) and
            is_hash(engine['program_sha256']) and is_hash(engine['traineddata_sha256']) and
            type(engine['version']) is str and engine['version'].startswith('tesseract ') and len(engine['version']) <= 4096 and
            same(engine, build.get('ocr_host')), 'active actual prompt OCR engine/model differs from prepared build')
    previous_ns = 0
    from PIL import Image
    for key, kind, prompt in (('getty', 'getty-auth', 'Password:'), ('sudo', 'sudo-auth', '[sudo] password for arcticqual:')):
        cap = value[key]
        exact(cap, {'path', 'bytes', 'sha256', 'size', 'prompt_kind', 'observed_line_sha256', 'observed_ns'}, 'active pre-input prompt capture fields differ')
        expected_name = 'installed-' + key + '-password.png'
        path = 'host/' + expected_name
        data = image_loader(path)
        require(cap['path'] in (expected_name, path) and type(cap['bytes']) is int and 0 < cap['bytes'] <= 4 * 1024 * 1024 and
                len(data) == cap['bytes'] and digest(data) == cap['sha256'] == required_images[path] and cap['size'] == [1280, 720] and
                cap['prompt_kind'] == kind and cap['observed_line_sha256'] == digest(prompt.encode('utf-8')) and
                type(cap['observed_ns']) is int and cap['observed_ns'] > previous_ns and
                data.startswith(b'\x89PNG\r\n\x1a\n'), 'active secret input was not guarded by a bound pre-input console prompt')
        with Image.open(io.BytesIO(data)) as image:
            require(image.size == (1280, 720) and image.format == 'PNG' and getattr(image, 'n_frames', 1) == 1,
                    'active pre-input prompt physical image differs')
        previous_ns = cap['observed_ns']
    require(value['getty']['observed_ns'] < shell['observed_ns'] < value['sudo']['observed_ns'],
            'active observed shell did not follow getty authentication and precede sudo input')


def exported_inventories_check(state):
    """Reject undeclared payloads in every structured active export wrapper.

    These inventories mirror the pinned runner, host, capture builder and
    protected transport extractor. The original idle contract is unchanged.
    """
    exact(state, {'schema', 'status', 'release_acceptance', 'image', 'execution', 'source_inputs', 'errors',
                  'limitations', 'build', 'vm_tool_image_id', 'context', 'diagnostic_streams', 'guest', 'host',
                  'transport', 'required_images'}, 'active execution export contains missing or private fields')
    execution = state['execution']
    exact(execution, {'source_sha', 'run_id', 'manifest_sha256'}, 'active execution identity contains private fields')
    require(type(execution['run_id']) is int and execution['run_id'] > 0 and is_hash(execution['manifest_sha256']) and
            type(state['vm_tool_image_id']) is str and re.fullmatch('(sha256:)?[0-9a-f]{64}', state['vm_tool_image_id']) and
            type(state['limitations']) is list and state['limitations'] == [
                'Owned offline UEFI installation with encryption explicitly disabled through the shipped GUI',
                'QEMU target writes capped at 8 MiB/s to retain genuine copy across both disruptions; no performance claim',
                'All seven active restoration and pre-input console captures require independent manual review; original idle/native/CLI gates remain required'],
            'active execution identity or declared scope differs')
    image = state['image']
    image_keys = {'source_sha', 'run_id', 'artifact_id', 'name', 'bytes', 'sha256', 'archive_bytes', 'archive_sha256'}
    require(type(image) is dict, 'active image export differs')
    mode = image.get('producer_mode', 'in-producer-paired-v1')
    require(mode in ('in-producer-paired-v1', 'frozen-external-paired-v1'), 'active image producer mode differs')
    if 'producer_mode' in image:
        image_keys.add('producer_mode')
    if mode == 'frozen-external-paired-v1':
        image_keys.add('producer_receipt_sha256')
        require(is_hash(image.get('producer_receipt_sha256')), 'active external producer receipt is unbound')
    exact(image, image_keys, 'active image export contains missing or private fields')
    require(all(type(image[key]) is int and image[key] > 0 for key in ('run_id', 'artifact_id', 'archive_bytes')) and
            is_hash(image['archive_sha256']), 'active retained image artifact identity differs')
    build = state['build']
    exact(build, {'schema', 'release_acceptance', 'sources', 'binaries', 'compiler', 'packages', 'display_host', 'ocr_host'},
          'active build export contains missing or private fields')
    require(type(build['compiler']) is str and 0 < len(build['compiler']) <= 4096 and
            type(build['packages']) is list and 1 <= len(build['packages']) <= 32 and
            all(type(package) is str and re.fullmatch('[A-Za-z0-9_.:+-]{1,256}', package) for package in build['packages']),
            'active capture compiler/package provenance differs')
    display_host = build['display_host']
    exact(display_host, {'backend', 'gl', 'packages', 'capabilities_sha256', 'programs'},
          'active capture display build contains private fields')
    exact(display_host['programs'], {'/usr/bin/qemu-system-x86_64', '/usr/bin/dbus-daemon', '/usr/bin/gdbus'},
          'active capture display program inventory differs')
    require(display_host['backend'] == 'dbus' and display_host['gl'] is False and
            is_hash(display_host['capabilities_sha256']) and all(is_hash(value) for value in display_host['programs'].values()) and
            type(display_host['packages']) is list and 1 <= len(display_host['packages']) <= 32 and
            all(type(package) is str and re.fullmatch('[A-Za-z0-9_.:+-]{1,256}', package) for package in display_host['packages']),
            'active actual display build provenance differs')
    guest, host = state['guest'], state['host']
    identity = {'boot_id', 'desktop_uid', 'active_desktop_session'}
    exact(guest, {'schema', 'status', 'context', 'release_acceptance', 'begin', 'provenance', 'report', 'collector',
                  'port_end', 'requests', 'files', 'required_pngs', 'received_pngs', 'received_requests', 'errors', 'port',
                  'serial', 'scope'} | identity, 'active extraction export contains missing or private fields')
    require(guest['schema'] == 'arctic-installer-evidence-state-v1' and guest['release_acceptance'] is False and
            guest['errors'] == [] and type(guest['required_pngs']) is int and guest['required_pngs'] == 4 and
            type(guest['received_pngs']) is int and guest['received_pngs'] == 4 and
            type(guest['received_requests']) is int and guest['received_requests'] == 3 and
            guest['scope'] == 'transport identity, guest completeness and PNG arithmetic; independent behavior/security and manual review required',
            'active extraction completeness or scope differs')
    exact(guest['begin'], {'schema', 'stage', 'context', 'transport', 'release_acceptance'} | identity,
          'active protected BEGIN contains private fields')
    exact(guest['provenance'], {'schema', 'stage', 'context', 'transport', 'release_acceptance', 'cmdline', 'virtualization'} | identity,
          'active protected provenance contains private fields')
    exact(guest['collector'], {'binding_id', 'status', 'error', 'evidence_export_complete', 'release_acceptance'} | identity,
          'active protected collector contains private fields')
    exact(guest['port_end'], {'schema', 'binding_id', 'status', 'end_sha256', 'release_acceptance'} | identity,
          'active protected UART completion contains private fields')
    for record in (guest['begin'], guest['provenance']):
        context_check(record['context'])
        require(same(record['context'], state['context']), 'active protected context binding differs')
        exact(record['transport'], {'schema', 'name', 'device', 'major', 'minor', 'uid', 'mode'},
              'active protected port projection contains private fields')
    require(guest['collector']['binding_id'] == guest['port_end']['binding_id'] == state['context']['binding_id'],
            'active protected completion binding differs')
    exact(guest['files'], {*GUEST_IMAGES, 'installer-report.json'}, 'active extracted payload inventory differs')
    for item in guest['files'].values():
        exact(item, {'bytes', 'sha256'}, 'active extracted payload receipt contains private fields')
        require(type(item['bytes']) is int and 0 < item['bytes'] <= 4 * 1024 * 1024 and is_hash(item['sha256']),
                'active extracted payload receipt differs')
    exact(host, {'schema', 'status', 'context', 'firmware', 'release_acceptance', 'iso_booted', 'execution_inputs',
                 'qemu_argv', 'target_proof', 'display_preparation', 'console_authentication', 'host_transitions',
                 'output_cleanup', 'live_qemu_stopped_before_installed_boot', 'password_prompt_evidence', 'installed_boot',
                 'owned_qemu_stopped', 'owned_private_bus_closed', 'errors'},
          'active host export contains missing or private fields')
    require(host['schema'] == 'arctic-installer-host-execution-v1' and host['release_acceptance'] is False,
            'active host export scope differs')
    proof = host['display_preparation']
    exact(proof, {'schema', 'status', 'qemu_pid', 'qemu_uid', 'gpu_id', 'bus_pid', 'bus_owner', 'heads', 'display_backend',
                  'guest_monitor_verification_required', 'controller_sha256'}, 'active display preparation contains private fields')
    require(proof['schema'] == 'arctic-qemu-taskbar-display-v1' and type(proof['heads']) is list,
            'active actual display preparation schema differs')
    for head in proof['heads']:
        exact(head, {'console_id', 'head', 'device_address', 'width_mm', 'height_mm', 'xoff', 'yoff', 'width', 'height'},
              'active display head contains private fields')
        require(head['width_mm'] == 340 and head['height_mm'] == 190 and head['xoff'] == head['head'] * 1280 and head['yoff'] == 0,
                'active display head placement differs')
    exact(host['console_authentication'], {'nonce', 'status', 'capture'}, 'active live console authentication contains private fields')
    require(host['console_authentication']['capture'] == 'console-login.png', 'active live console authentication capture differs')
    require(type(host['host_transitions']) is list, 'active host transition export differs')
    display_records = []
    for row in host['host_transitions']:
        require(type(row) is dict and type(row.get('request')) is dict, 'active host transition projection differs')
        kind = row['request'].get('kind')
        exact(row, {'request', 'request_sha256', 'disk_io', 'capture' if kind == 'vt-away' else 'display'},
              'active host transition contains private fields')
        if kind == 'vt-away':
            exact(row['capture'], {'path', 'bytes', 'sha256', 'console_pixel_guard_passed', 'manual_console_review_required'},
                  'active away-VT capture receipt contains private fields')
        else:
            display_records.append(row['display'])
    if host['output_cleanup'] is not None:
        display_records.append(host['output_cleanup'])
    for record in display_records:
        exact(record, {'schema', 'qemu_pid', 'qemu_uid', 'gpu_id', 'bus_owner', 'applied', 'enabled_heads', 'observation'},
              'active display transition contains private fields')
        require(record['observation'] == 'supported QEMU UIInfo; actual guest output inventory required' and type(record['applied']) is list,
                'active display transition observation differs')
        for head in record['applied']:
            exact(head, {'head', 'width', 'height', 'xoff', 'yoff'}, 'active applied display head contains private fields')
    exact(state['transport'], {'status', 'report_path', 'report_sha256', 'port_sha256', 'serial_sha256'},
          'active transport export contains missing or private fields')
    streams = state['diagnostic_streams']
    bounds = {'serial.log': 8 * 1024 * 1024, 'installer-port.log': 64 * 1024 * 1024,
              'qemu-installer-live.log': 4 * 1024 * 1024, 'serial-installed.log': 8 * 1024 * 1024,
              'qemu-installer-installed.log': 4 * 1024 * 1024}
    exact(streams, bounds, 'active diagnostic stream inventory differs')
    for label, item, bound in [(name, streams[name], limit) for name, limit in bounds.items()] + [
            ('protected guest port', guest['port'], bounds['installer-port.log']), ('protected guest serial', guest['serial'], bounds['serial.log'])]:
        exact(item, {'bytes', 'sha256'}, 'active diagnostic receipt contains private fields: ' + label)
        require(type(item['bytes']) is int and (0 if label.startswith('qemu-') else 1) <= item['bytes'] <= bound and is_hash(item['sha256']),
                'active diagnostic receipt bounds differ: ' + label)
    require(same(streams['serial.log'], guest['serial']) and same(streams['installer-port.log'], guest['port']) and
            same(streams['serial-installed.log'], host['installed_boot']['serial']) and
            streams['installer-port.log']['sha256'] == state['transport']['port_sha256'],
            'active diagnostic receipts do not bind protected original streams')


def validate_execution(state, expected_image, execution_source, serial_bytes=None, image_loader=None):
    exported_inventories_check(state)
    require(state.get('schema') == 'arctic-installer-active-execution-v1' and state.get('status') ==
            'live_installer_active_restoration_completed_and_installed_boot_passed_pending_manual_visual_review' and
            state.get('release_acceptance') is False and same(state.get('image'), expected_image) and state.get('errors') == [] and
            state.get('execution', {}).get('source_sha') == execution_source and is_hash(execution_source, 40),
            'active installer execution identity/status differs')
    context = state['context']
    context_check(context)
    require(context['source_sha'] == expected_image['source_sha'] and context['iso_sha256'] == expected_image['sha256'] and
            context['iso_bytes'] == expected_image['bytes'] and context['execution_sha'] == execution_source,
            'active context is not exact candidate/execution')
    inputs = state['source_inputs']
    require(set(inputs) == set(EXECUTION_FILES) and all(is_hash(value) for value in inputs.values()) and
            all(context[key] == inputs[path] for key, path in (
                ('checker_sha256', 'tools/installer-qualification/guest.py'), ('active_checker_sha256', 'tools/installer-qualification/active-guest.py'),
                ('installed_checker_sha256', 'tools/installer-qualification/installed-guest.py'),
                ('runtime_sha256', 'tools/native-functional/taskbar-runtime.py'), ('native_sha256', 'tools/native-functional/native_smoke.py'))),
            'active installer source input inventory differs')
    build = state['build']
    require(build.get('schema') == 'arctic-taskbar-tools-v1' and build.get('release_acceptance') is False and
            build['binaries']['raw-screencopy'] == context['capture_sha256'] and set(build['binaries']) == {'raw-screencopy', 'virtual-pointer'} and
            set(build['sources']) == {'tools/native-functional/taskbar-screencopy.c', 'shell/dev/virtual-pointer.c', 'shell/dev/wlr-screencopy-unstable-v1.xml'} and
            all(build['sources'][name] == inputs[name] for name in build['sources']), 'active physical capture build/source identity differs')
    guest, host = state['guest'], state['host']
    require(guest.get('status') == 'passed' and same(guest.get('context'), context) and same(host.get('context'), context) and
            host.get('status') == 'host_completed_pending_guest_evidence_validation_and_visual_review' and host.get('iso_booted') is True and
            host.get('errors') == [] and host.get('owned_qemu_stopped') is True and host.get('owned_private_bus_closed') is True,
            'active guest/host execution or cleanup failed')
    require(host.get('live_qemu_stopped_before_installed_boot') is True, 'live QEMU was not stopped before fresh installed boot')
    require(set(host['execution_inputs']) == set(HOST_EXECUTION_FILES) and all(inputs[name] == value for name, value in host['execution_inputs'].items()) and
            type(host['host_transitions']) is list and len(host['host_transitions']) == 3 and set(state['required_images']) == set(REQUIRED_IMAGES) and
            all(is_hash(value) for value in state['required_images'].values()), 'active host source/capture inventory differs')
    proof = host['display_preparation']
    require(proof['controller_sha256'] == inputs['tools/native-functional/taskbar-display.py'] and
            proof['status'] == 'uiinfo_applied_pending_guest_two_output_evidence' and proof['gpu_id'] == 'arctic_taskbar_gpu' and
            proof['display_backend'] == 'dbus' and type(proof['qemu_uid']) is int and proof['qemu_uid'] == 0 and
            type(proof['qemu_pid']) is int and proof['qemu_pid'] > 1 and type(proof['bus_pid']) is int and proof['bus_pid'] > 1 and
            re.fullmatch(r':[0-9]+\.[0-9]+', proof['bus_owner']) and len(proof['heads']) == 2 and {head['head'] for head in proof['heads']} == {0, 1} and
            len({head['console_id'] for head in proof['heads']}) == 2 and len({head['device_address'] for head in proof['heads']}) == 1 and
            all(type(head['head']) is int and type(head['console_id']) is int and head['console_id'] >= 0 and head['width'] == 1280 and head['height'] == 720
                for head in proof['heads']) and proof['guest_monitor_verification_required'] is True, 'active owned two-head display preparation differs')
    target_path, variable_path = vm_argv_check(host['qemu_argv'], context)
    target = host['target_proof']
    exact(target, {'path', 'virtual_bytes', 'serial', 'backing_file', 'node_name', 'write_bps'}, 'active host target creation receipt differs')
    require(target == dict(path='target.qcow2', virtual_bytes=context['disk_bytes'], serial=context['disk_serial'], backing_file=False,
                          node_name=context['disk_node'], write_bps=context['write_bps']), 'active host target identity differs')
    report = guest['report']
    require(same(report['context'], context) and report['status'] == 'passed' and report['release_acceptance'] is False and
            all(guest['collector'][key] == report[key] for key in ('boot_id', 'desktop_uid', 'active_desktop_session')),
            'active actual collector report identity differs')
    requests = [report['cases'][0]['disruption']['request'], report['cases'][1]['disruption']['disconnect_request'], report['cases'][1]['disruption']['restore_request']]
    require(same(guest['requests'], requests) and same([row['request'] for row in host['host_transitions']], requests) and
            [(request['kind'], request['cycle']) for request in requests] == [('vt-away', 0), ('output-disconnect', 0), ('output-restore', 0)],
            'active host receipts do not match actual guest disruptions')
    previous = None
    for row in host['host_transitions']:
        request = row['request']
        require(row['request_sha256'] == hash_value(request) and request['binding_id'] == context['binding_id'] and request['boot_id'] == report['boot_id'],
                'active host UART request digest/boot differs')
        disk_io_check(row['disk_io'], context)
        require(row['disk_io']['target_file'] == target_path and (previous is None or
                all(row['disk_io']['before'][key] >= previous[key] for key in ('wr_bytes', 'wr_operations', 'monotonic_ns'))),
                'active host counters changed target or regressed between transitions')
        previous = row['disk_io']['after']
        if request['kind'] == 'vt-away':
            cap = row['capture']
            require(cap['path'] == 'installer-vt-away-0.png' and cap.get('console_pixel_guard_passed') is True and
                    cap.get('manual_console_review_required') is True and state['required_images']['host/' + cap['path']] == cap['sha256'] and
                    type(cap['bytes']) is int and 0 < cap['bytes'] <= 4 * 1024 * 1024, 'active host VT-away capture binding differs')
        else:
            transition = row['display']
            heads = {0, 1} if request['kind'] == 'output-restore' else {0, 1} - {request['hosting_head']}
            require(transition['schema'] == 'arctic-installer-host-output-v1' and transition['qemu_pid'] == proof['qemu_pid'] and
                    type(transition['qemu_uid']) is int and transition['qemu_uid'] == 0 and transition['gpu_id'] == proof['gpu_id'] and
                    transition['bus_owner'] == proof['bus_owner'] and transition['enabled_heads'] == sorted(heads) and transition['applied'] ==
                    [dict(head=n, width=1280 if n in heads else 0, height=720 if n in heads else 0, xoff=n * 1280, yoff=0) for n in (0, 1)],
                    'active actual output disconnect/reconnect operation differs')
    require(host['firmware'] == report['baseline']['engine']['hello']['firmware'] == 'uefi', 'active live firmware differs')
    auth = host['console_authentication']
    require(auth['status'] == 'exact_liveuser_uid_response' and is_hash(auth['nonce'], 32), 'active actual console authentication differs')
    require(type(serial_bytes) is bytes and 0 < len(serial_bytes) <= 8 * 1024 * 1024 and digest(serial_bytes) == guest['serial']['sha256'] == state['transport']['serial_sha256'] and
            len(serial_bytes) == guest['serial']['bytes'], 'active protected actual serial identity differs')
    require([line for line in serial_bytes.decode('utf-8').splitlines() if line.startswith('ARCTIC-CONSOLE-READY=')] ==
            ['ARCTIC-CONSOLE-READY=' + auth['nonce'] + ' user=liveuser uid=' + str(report['desktop_uid'])], 'active actual live UID response differs')
    require(image_loader is not None, 'active physical images and installed serial replay required')
    for path, expected in state['required_images'].items():
        data = image_loader(path)
        require(0 < len(data) <= 4 * 1024 * 1024 and digest(data) == expected and data.startswith(b'\x89PNG\r\n\x1a\n'),
                'active required physical image bytes differ: ' + path)
    from PIL import Image
    cap = host['host_transitions'][0]['capture']
    data = image_loader('host/' + cap['path'])
    require(len(data) == cap['bytes'] and digest(data) == cap['sha256'], 'active VT-away physical bytes differ')
    with Image.open(io.BytesIO(data)) as image:
        require(image.size == (1280, 720), 'active VT-away physical dimensions differ')
        histogram = image.convert('L').histogram()
        require(sum(histogram[:17]) / (image.width * image.height) > .90 and sum(histogram[160:]) >= 30,
                'active VT-away physical console pixels absent')
    require(state['transport']['status'] == 'passed' and state['transport']['report_path'] == 'installer/installer-report.json' and
            state['transport']['report_sha256'] == digest((json.dumps(report, sort_keys=True, allow_nan=False) + '\n').encode()),
            'active transported report bytes differ')
    installed = host['installed_boot']
    installed_report = installed_boot_check(installed, context, report, proof['qemu_pid'], image_loader('host/serial-installed.log'))
    installed_path, installed_variables = vm_argv_check(installed['qemu_argv'], context, installed=True)
    require(installed_path == target_path and installed_variables == variable_path, 'installed boot replaced target disk or UEFI variables')
    require(same(strict_json(image_loader('host/installed-boot.json')), installed_report), 'active installed receipt alias differs')
    password_prompts_check(host['password_prompt_evidence'], build, state['required_images'], image_loader)
    return dict(status='passed_pending_manual_visual_review', images=list(REQUIRED_IMAGES),
                installed_boot_id=installed['boot_id'], release_acceptance=False)
