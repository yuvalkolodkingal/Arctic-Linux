"""Adversarial synthetic acceptance controls; never real ISO qualification."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image, ImageDraw
import io

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


A = load('active_contract_controls', HERE / 'active-contract.py')
F = load('active_contract_idle_fixture', HERE / 'test_contract.py')
T = load('active_contract_protected_transport_fixture', HERE / 'test_evidence.py')

# Every fixed structured export wrapper is exercised, including the protected
# extraction aliases that the publisher independently binds to original bytes.
EXPORT_WRAPPER_PATHS = [(), ('execution',), ('image',), ('context',), ('source_inputs',), ('required_images',),
    ('host',), ('guest',), ('build',), ('build', 'sources'), ('build', 'binaries'), ('build', 'display_host'),
    ('build', 'display_host', 'programs'), ('build', 'ocr_host'), ('transport',), ('diagnostic_streams',),
    ('host', 'display_preparation'), ('host', 'display_preparation', 'heads', 0), ('host', 'console_authentication'),
    ('host', 'host_transitions', 0), ('host', 'host_transitions', 0, 'capture'),
    ('host', 'host_transitions', 1), ('host', 'host_transitions', 1, 'display'),
    ('host', 'host_transitions', 1, 'display', 'applied', 0), ('host', 'target_proof'),
    ('host', 'installed_boot'), ('host', 'installed_boot', 'target'), ('host', 'installed_boot', 'root'),
    ('host', 'installed_boot', 'authentication'), ('host', 'installed_boot', 'serial'),
    ('host', 'password_prompt_evidence'), ('host', 'password_prompt_evidence', 'getty'),
    ('host', 'password_prompt_evidence', 'sudo'), ('host', 'password_prompt_evidence', 'engine'),
    ('guest', 'begin'), ('guest', 'begin', 'transport'), ('guest', 'provenance'),
    ('guest', 'provenance', 'transport'), ('guest', 'collector'), ('guest', 'port_end'),
    ('guest', 'files'), ('guest', 'files', 'baseline.png'), ('guest', 'port'), ('guest', 'serial')]
EXPORT_WRAPPER_PATHS += [('diagnostic_streams', name) for name in
    ('serial.log', 'installer-port.log', 'qemu-installer-live.log', 'serial-installed.log', 'qemu-installer-installed.log')]


def add_private_payload(state, path, key):
    target = state
    for part in path:
        target = target[part]
    target[key] = 'synthetic-private-password' if key == 'password' else {
        'full_name': 'Synthetic Private Account', 'password': 'synthetic-private-password'}


def fixture():
    old, state, files, media, serial = F.fixture()
    context = dict(state['context'], schema='arctic-installer-active-context-v1', active_checker_sha256='9' * 64,
                   installed_checker_sha256='0' * 64, disk_serial='arctic-a-0123456789a', disk_bytes=64 * 1024 ** 3,
                   disk_node='target0', write_bps=8 * 1024 ** 2)
    selected_apps = ['gnome-web', 'featherpad', 'foot', 'fish', 'bash', 'pcmanfm', 'celluloid']
    config = dict(network=dict(offline=True), disk=dict(disk='/dev/vda', mode='erase'), encryption=dict(enabled=False),
                  apps=dict(selection=dict(browser=['gnome-web'], editor=['featherpad'], terminal=['foot'],
                                           shell=['fish', 'bash'], files=['pcmanfm'], video=['celluloid'])))
    writer = dict(process=dict(pid=103, uid=0, ppid=102, start_ticks=226, executable='/usr/bin/rsync',
                              executable_sha256='e' * 64, argv=['rsync'] + A.RSYNC_ARGS, overrides_absent=True),
                  ancestor_pids=[103, 102], target_serial=context['disk_serial'],
                  mount=dict(target='/mnt', source='/dev/vda3[/@]', block_source='/dev/vda3', fstype='btrfs', major_minor='252:3'))

    def engine(percent, done=False):
        return dict(hello=dict(engine_version='1.2.1', protocol_version=1, mock=False, live=True, firmware='uefi',
                               state='done' if done else 'installing'),
                    wizard=dict(current='done' if done else 'install', state='done' if done else 'installing'),
                    keyboard=dict(id='keyboard', data=copy.deepcopy(A.KEYBOARD)),
                    install=dict(id='install', options=dict(modules=[dict(id=module, status='installed' if done else 'queued',
                                                                         percent=100 if done else 0) for module in selected_apps], attention=False, failed=False,
                        progress=dict(event='progress', percent=percent, phase='finalize' if done else 'copy',
                                      apps_done=len(selected_apps) if done else 0, apps_total=len(selected_apps), paused=False))))

    def sample(number):
        return dict(engine=engine(19 + number), identities=copy.deepcopy(old['baseline']['identities']),
                    keyboard_files=copy.deepcopy(old['baseline']['keyboard_files']), config=copy.deepcopy(config),
                    writer=copy.deepcopy(writer), elapsed_ns=number * 10_000_000)

    def observed(item, name, number):
        result = copy.deepcopy(item)
        result.pop('engine', None); result.pop('identities', None); result.pop('keyboard_files', None)
        result.pop('gui_log_counts', None)
        result.update(sample(number))
        result['state'].update(page='install', current='install', percent=19 + number)
        result['capture']['path'] = name
        return result

    baseline = observed(old['baseline'], 'baseline.png', 1)
    baseline.pop('initial_wizard', None)
    baseline['packaged_sources'] = A.packaged_source_hashes(HERE.parents[1])
    baseline['rpc_peer'] = dict(uid=0, gid=0, pid_claim='none; socket activation can report systemd')
    drm = baseline['drm_heads']
    drm.update(card='card0', device='/sys/devices/pci0000:00/0000:00:01.0/virtio0', pci_address='0000:00:01.0',
               binding='single Linux virtio_gpu scanout index order; Virtual-1=0, Virtual-2=1')
    for name, output in drm['outputs'].items():
        output.update(connector='card0-' + name,
                      sysfs_path='/sys/devices/pci0000:00/0000:00:01.0/virtio0/drm/card0/card0-' + name)
    baseline.update(target_disk=dict(path='/dev/vda', sysfs='/sys/class/block/vda', serial=context['disk_serial'],
                                    disk_bytes=context['disk_bytes'], major_minor='252:0'),
                    scope='Owned 64 GiB unencrypted offline UEFI install; original copy writer continues through disruptions')
    away = sample(2)
    vt = observed(old['cases'][0], 'vt-0.png', 3)
    vt['disruption']['prepared_state'] = away
    output = observed(old['cases'][3], 'output-0.png', 6)
    before = sample(4)
    absent = observed(old['cases'][3]['disruption']['unavailable'], 'output-0-relocated.png', 5)
    output['disruption'].update(before=before, unavailable=absent)
    requests = [vt['disruption']['request'], output['disruption']['disconnect_request'], output['disruption']['restore_request']]
    for request, snapshot in zip(requests, (away, before, absent)):
        request.update(engine_sha256=A.hash_value(snapshot['engine']), elapsed_ns=snapshot['elapsed_ns'])
    samples = [{key: value[key] for key in A.SAMPLE_KEYS} for value in (baseline, away, vt, before, absent, output)]
    completion = dict(engine=engine(100, True), identities=copy.deepcopy(baseline['identities']),
                      keyboard_files=copy.deepcopy(baseline['keyboard_files']), config=copy.deepcopy(config),
                      gui=dict(page='done', current='done', percent=100), elapsed_ns=70_000_000)
    report = {key: copy.deepcopy(value) for key, value in old.items() if key not in ('baseline', 'cases', 'cleanup')}
    report.update(schema='arctic-live-installer-active-restoration-v1', context=context, baseline=baseline,
                  cases=[vt, output], samples=samples, completion=completion, captures=4,
                  evidence_root='/tmp/arctic-native-smoke-installer-control',
                  cleanup=dict(original_vt_restored=True, engine_retained=True, errors=[]))
    report['security'] = dict(selinux='Enforcing', audit=dict(enabled=1, lost=0), observed_new_avcs=0, audit_enabled=True,
        scope='journal cursor and available audit-file interval; disabled kernel audit is a recorded telemetry limit')
    media = {name: value for name, value in media.items() if name in A.REQUIRED_IMAGES}
    files = {name: value for name, value in files.items() if name in A.GUEST_IMAGES}
    receipts = [copy.deepcopy(state['host']['host_transitions'][i]) for i in (0, 3, 4)]
    target_path = '/out/target.qcow2'
    for number, (receipt, request) in enumerate(zip(receipts, requests)):
        receipt.update(request=request, request_sha256=A.hash_value(request), disk_io=dict(node_name='target0', write_bps=context['write_bps'],
            target_file=target_path, target_serial=context['disk_serial'], inserted_node_name='target0', inserted_readonly=False,
            before=dict(wr_bytes=1000 + 100 * number, wr_operations=10 + 2 * number, monotonic_ns=1_000_000_000 + 100 * number),
            after=dict(wr_bytes=1050 + 100 * number, wr_operations=11 + 2 * number, monotonic_ns=1_000_000_050 + 100 * number)))
    argv = state['host']['qemu_argv'] + ['-drive', 'file=' + target_path + ',format=qcow2,if=none,id=target,node-name=target0,bps_wr=8388608',
                                          '-device', 'virtio-blk-pci,drive=target,serial=' + context['disk_serial']]
    installed_argv = []
    i = 0
    while i < len(argv):
        if argv[i] in ('-drive', '-device') and i + 1 < len(argv) and (argv[i + 1].startswith('file=/iso,') or 'drive=live' in argv[i + 1]):
            i += 2; continue
        installed_argv.append(argv[i]); i += 1
    installed_argv[-1] += ',bootindex=0'
    installed_report = dict(schema='arctic-active-installed-boot-v1', context=context, boot_id='22222222-2222-2222-2222-222222222222',
        selinux='Enforcing', root=dict(source='/dev/vda3[/@]', block_source='/dev/vda3', fstype='btrfs', serial=context['disk_serial']),
        keyboard=dict(xkb_layout='us,il', xkb_options='grp:alt_shift_toggle', vconsole_keymap='us'),
        authentication=dict(nonce='d' * 32, username='arcticqual', uid=1000, status='exact_installed_uid_response'), release_acceptance=False)
    installed_serial = ('ARCTIC-ACTIVE-INSTALLED-READY=' + 'd' * 32 + ' user=arcticqual uid=1000\nARCTIC-ACTIVE-INSTALLED ' +
                        json.dumps(installed_report, sort_keys=True) + '\n').encode()
    installed = dict(status='passed', live_qemu_pid=200, installed_qemu_pid=300, qemu_argv=installed_argv,
        target=dict(path='target.qcow2', virtual_bytes=context['disk_bytes'], serial=context['disk_serial'], backing_file=False),
        boot_id=installed_report['boot_id'], parent_live_boot_id=report['boot_id'], selinux=installed_report['selinux'],
        root=installed_report['root'], keyboard=installed_report['keyboard'], authentication=installed_report['authentication'],
        serial=dict(bytes=len(installed_serial), sha256=A.digest(installed_serial)),
        receipt_sha256=A.digest(json.dumps(installed_report, sort_keys=True).encode()))
    media['host/serial-installed.log'] = installed_serial
    media['host/installed-boot.json'] = json.dumps(installed_report, sort_keys=True).encode()
    inputs = {name: 'a' * 64 for name in A.EXECUTION_FILES}
    for key, path in (('checker_sha256', 'guest.py'), ('active_checker_sha256', 'active-guest.py'), ('installed_checker_sha256', 'installed-guest.py')):
        inputs['tools/installer-qualification/' + path] = context[key]
    inputs['tools/native-functional/taskbar-runtime.py'] = context['runtime_sha256']
    inputs['tools/native-functional/native_smoke.py'] = context['native_sha256']
    state.update(schema='arctic-installer-active-execution-v1', status='live_installer_active_restoration_completed_and_installed_boot_passed_pending_manual_visual_review',
                 errors=[], context=context, source_inputs=inputs, required_images={name: A.digest(data) for name, data in media.items() if name.endswith('.png')})
    state['build']['binaries']['virtual-pointer'] = '8' * 64
    ocr_engine = dict(packages=['tesseract-5.5.1-1.fc44.x86_64', 'tesseract-langpack-eng-4.1.0-4.fc44.noarch'],
                      program_sha256='c' * 64, traineddata_sha256='b' * 64, version='tesseract 5.5.1')
    state['build']['ocr_host'] = ocr_engine
    prompts = dict(schema='arctic-active-password-prompts-v1', engine=ocr_engine,
        login_shell=dict(prompt_kind='installed-user-shell', observed_line_sha256=A.digest(b'arcticqual@arctic-qual ~ >'), observed_ns=2),
        private_input_policy='Only after exact last console line; no secret-bearing screenshots or command text')
    for number, (key, text) in enumerate((('getty', 'Password:'), ('sudo', '[sudo] password for arcticqual:'))):
        image = Image.new('RGB', (1280, 720), 'black'); ImageDraw.Draw(image).text((20, 20), text, fill='white')
        stream = io.BytesIO(); image.save(stream, format='PNG'); data = stream.getvalue()
        name = 'installed-' + key + '-password.png'; media['host/' + name] = data
        prompts[key] = dict(path=name, bytes=len(data), sha256=A.digest(data), size=[1280, 720],
                           prompt_kind='getty-auth' if key=='getty' else 'sudo-auth',
                           observed_line_sha256=A.digest(text.encode('utf-8')), observed_ns=1 + 2*number)
        state['required_images']['host/' + name] = A.digest(data)
    state['guest'].update(context=context, report=report, requests=requests)
    state['host'].update(context=context, host_transitions=receipts, qemu_argv=argv, installed_boot=installed, live_qemu_stopped_before_installed_boot=True,
        password_prompt_evidence=prompts,
        target_proof=dict(path='target.qcow2', virtual_bytes=context['disk_bytes'], serial=context['disk_serial'], backing_file=False,
                          node_name=context['disk_node'], write_bps=context['write_bps']))
    state['transport']['report_sha256'] = A.digest((json.dumps(report, sort_keys=True) + '\n').encode())
    # Exercise the complete real producer schemas, not the minimal idle fixture.
    state['image'].update(run_id=77, artifact_id=88, archive_bytes=context['iso_bytes'] + 1000,
                          archive_sha256='e' * 64, name='Arctic-Linux-1.2-candidate-77-1-x86_64.iso')
    state['execution'].update(run_id=101, manifest_sha256='f' * 64)
    state.update(vm_tool_image_id='sha256:' + 'a' * 64, limitations=[
        'Owned offline UEFI installation with encryption explicitly disabled through the shipped GUI',
        'QEMU target writes capped at 8 MiB/s to retain genuine copy across both disruptions; no performance claim',
        'All seven active restoration and pre-input console captures require independent manual review; original idle/native/CLI gates remain required'])
    state['build'].update(compiler='gcc (GCC) 16.1.1', packages=['gcc-16.1.1-1.fc44.x86_64',
        'wayland-devel-1.24.0-1.fc44.x86_64', 'wayland-libs-1.24.0-1.fc44.x86_64'],
        display_host=dict(backend='dbus', gl=False,
            packages=['dbus-daemon-1.16.2-1.fc44.x86_64', 'glib2-2.88.0-1.fc44.x86_64',
                      'qemu-ui-dbus-11.0.0-1.fc44.x86_64', 'qemu-ui-opengl-11.0.0-1.fc44.x86_64'],
            capabilities_sha256='b' * 64,
            programs={name: 'c' * 64 for name in ('/usr/bin/qemu-system-x86_64', '/usr/bin/dbus-daemon', '/usr/bin/gdbus')}))
    state['host'].update(schema='arctic-installer-host-execution-v1', release_acceptance=False, output_cleanup=None)
    state['host']['console_authentication']['capture'] = 'console-login.png'
    state['host']['display_preparation']['schema'] = 'arctic-qemu-taskbar-display-v1'
    for head in state['host']['display_preparation']['heads']:
        head.update(width_mm=340, height_mm=190, xoff=head['head'] * 1280, yoff=0)
    for row in receipts[1:]:
        row['display']['observation'] = 'supported QEMU UIInfo; actual guest output inventory required'
    T.Controls.setUpClass()
    wire = T.Controls()
    wire.context = context
    wire.identity = {key: report[key] for key in T.e.IDENTITY}
    wire.root, wire.report, wire.requests = report['evidence_root'], report, requests
    wire.begin = dict(T.Controls.begin, context=context, **wire.identity)
    wire.proof = dict(T.Controls.proof, context=context, **wire.identity)
    wire.end = dict(T.Controls.end, binding_id=context['binding_id'], **wire.identity)
    wire.files = {name: media['installer/' + name] for name in A.GUEST_IMAGES}
    wire.files['installer-report.json'] = (json.dumps(report, sort_keys=True) + '\n').encode()
    port, uart = wire.wire(wire.rows())
    serial += uart
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary)
        (folder / 'port').write_bytes(port); (folder / 'serial').write_bytes(serial)
        result = T.e.extract(folder / 'port', folder / 'serial', folder / 'installer', context)
        for path in (folder / 'installer').iterdir():
            media['installer/' + path.name] = path.read_bytes()
    state['guest'], report, files = result['state'], result['report'], result['files']
    state['transport'].update(serial_sha256=A.digest(serial), port_sha256=A.digest(port))
    state['diagnostic_streams'] = {
        'serial.log': state['guest']['serial'], 'installer-port.log': state['guest']['port'],
        'qemu-installer-live.log': dict(bytes=0, sha256=A.digest(b'')),
        'serial-installed.log': installed['serial'], 'qemu-installer-installed.log': dict(bytes=0, sha256=A.digest(b''))}
    media.update({'host/serial.log': serial, 'host/installer-port.log.bounded-prefix.bin': port[:64 * 1024],
                  'host/qemu-installer-live.log.bounded-prefix.bin': b'', 'host/qemu-installer-installed.log.bounded-prefix.bin': b''})
    return report, state, files, media, serial


class Controls(unittest.TestCase):
    def check_report(self, report, state, files, media):
        return A.validate_report(report, state['context'], files, lambda name: media['installer/' + name], report['baseline']['packaged_sources'])

    def test_coherent_synthetic_active_copy_and_fresh_boot_still_need_manual_review(self):
        report, state, files, media, serial = fixture()
        self.assertEqual(self.check_report(report, state, files, media)['status'], 'passed_pending_manual_visual_review')
        result = A.validate_execution(state, state['image'], state['context']['execution_sha'], serial, media.__getitem__)
        self.assertFalse(result['release_acceptance'])
        self.assertEqual(len(result['images']), 7)

    def test_all_active_export_wrappers_reject_unknown_private_keys(self):
        report, original, files, media, serial = fixture()
        for path in EXPORT_WRAPPER_PATHS:
            for key in ('password', 'raw_account'):
                state = copy.deepcopy(original)
                add_private_payload(state, path, key)
                with self.subTest(path=path, key=key), self.assertRaises(RuntimeError):
                    A.validate_execution(state, state['image'], state['context']['execution_sha'], serial, media.__getitem__)

    def test_actual_guest_security_rpc_drm_and_process_wrappers_reject_private_keys(self):
        original, state, files, media, serial = fixture()
        paths = [('security',), ('security', 'audit'), ('baseline', 'rpc_peer'), ('baseline', 'drm_heads'),
                 ('baseline', 'drm_heads', 'outputs'), ('baseline', 'drm_heads', 'outputs', 'Virtual-1'),
                 ('baseline', 'identities'), ('baseline', 'identities', 'listener'),
                 ('baseline', 'identities', 'gui'), ('baseline', 'identities', 'service')]
        for path in paths:
            for key in ('password', 'raw_account'):
                report = copy.deepcopy(original)
                add_private_payload(report, path, key)
                with self.subTest(path=path, key=key), self.assertRaises(RuntimeError):
                    self.check_report(report, state, files, media)

    def test_actual_image_optional_producer_modes_are_explicit_and_safe(self):
        report, original, files, media, serial = fixture()
        for mode in (None, 'in-producer-paired-v1', 'frozen-external-paired-v1'):
            state = copy.deepcopy(original)
            if mode is not None:
                state['image']['producer_mode'] = mode
            if mode == 'frozen-external-paired-v1':
                state['image']['producer_receipt_sha256'] = 'a' * 64
            with self.subTest(mode=mode):
                self.assertFalse(A.validate_execution(state, state['image'], state['context']['execution_sha'], serial, media.__getitem__)['release_acceptance'])
        for extra in ({'producer_receipt_sha256': 'a' * 64}, {'producer_mode': 'unreviewed-mode'},
                      {'producer_mode': 'frozen-external-paired-v1'},
                      {'producer_mode': 'frozen-external-paired-v1', 'producer_receipt_sha256': 'not-a-hash'}):
            state = copy.deepcopy(original); state['image'].update(extra)
            with self.subTest(extra=extra), self.assertRaises(RuntimeError):
                A.validate_execution(state, state['image'], state['context']['execution_sha'], serial, media.__getitem__)

    def test_idle_fake_writer_wrong_target_and_process_replacement_are_rejected(self):
        mutations = [lambda r: r['baseline']['engine']['hello'].update(state='wizard'),
                     lambda r: r['baseline']['writer']['process'].update(ppid=1),
                     lambda r: r['baseline']['writer'].update(ancestor_pids=[103, 999]),
                     lambda r: r['baseline']['writer']['process'].update(executable='/usr/bin/sleep'),
                     lambda r: r['baseline']['writer']['process']['argv'].__setitem__(-1, '/foreign/'),
                     lambda r: r['baseline']['target_disk'].update(serial='arctic-a-aaaaaaaaaaa'),
                     lambda r: r['baseline']['writer']['mount'].update(block_source='/dev/vdb3'),
                     lambda r: r['baseline']['writer']['mount'].update(major_minor='252:0'),
                     lambda r: r['cases'][0]['identities']['daemon'].update(start_ticks=999),
                     lambda r: r['cases'][1]['writer']['process'].update(start_ticks=999)]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                report, state, files, media, serial = fixture(); mutate(report)
                with self.assertRaises(RuntimeError): self.check_report(report, state, files, media)

    def test_regressing_progress_missing_sample_and_replayed_request_digest_are_rejected(self):
        mutations = [lambda r: r['samples'][-1]['engine']['install']['options']['progress'].update(percent=1),
                     lambda r: r['cases'][1]['state'].update(percent=1),
                     lambda r: r['samples'].__delitem__(1),
                     lambda r: r['cases'][0]['disruption']['request'].update(engine_sha256=A.hash_value(r['baseline']['engine'])),
                     lambda r: r['cases'][0]['disruption']['request'].update(elapsed_ns=r['baseline']['elapsed_ns']),
                     lambda r: r['completion'].update(elapsed_ns=1),
                     lambda r: r['completion']['identities']['daemon'].update(pid=999),
                     lambda r: r['completion']['gui'].update(current='install')]
        for mutate in mutations:
            report, state, files, media, serial = fixture(); mutate(report)
            with self.assertRaises(RuntimeError): self.check_report(report, state, files, media)

    def test_private_payloads_are_not_accepted_even_when_other_evidence_is_coherent(self):
        for destination in ('top', 'engine', 'config', 'writer', 'completion', 'gui'):
            report, state, files, media, serial = fixture()
            target = {'top': report, 'engine': report['baseline']['engine'], 'config': report['baseline']['config'],
                      'writer': report['baseline']['writer'], 'completion': report['completion'], 'gui': report['baseline']['state']}[destination]
            target['password'] = 'must-not-appear'
            with self.subTest(destination=destination), self.assertRaises(RuntimeError): self.check_report(report, state, files, media)

    def test_real_write_growth_and_owned_qmp_target_are_required(self):
        mutations = [lambda s: s['host']['host_transitions'][0]['disk_io']['after'].update(wr_bytes=1000),
                     lambda s: s['host']['host_transitions'][0]['disk_io']['after'].update(wr_operations=10),
                     lambda s: s['host']['host_transitions'][1]['disk_io']['before'].update(wr_bytes=0),
                     lambda s: s['host']['host_transitions'][0]['disk_io'].update(node_name='other'),
                     lambda s: s['host']['host_transitions'][0]['disk_io'].update(target_file='/foreign/target.qcow2'),
                     lambda s: s['host']['host_transitions'][0]['disk_io'].update(inserted_readonly=True),
                     lambda s: s['host']['target_proof'].update(backing_file=True)]
        for mutate in mutations:
            report, state, files, media, serial = fixture(); mutate(state)
            with self.assertRaises(RuntimeError): A.validate_execution(state, state['image'], state['context']['execution_sha'], serial, media.__getitem__)

    def test_fresh_same_disk_installed_boot_security_and_console_auth_are_required(self):
        mutations = [lambda s: s['host']['installed_boot'].update(boot_id=s['guest']['report']['boot_id']),
                     lambda s: s['host']['installed_boot'].update(installed_qemu_pid=200),
                     lambda s: s['host']['installed_boot'].update(selinux='Permissive'),
                     lambda s: s['host']['installed_boot']['keyboard'].update(xkb_layout='us'),
                     lambda s: s['host']['installed_boot']['root'].update(block_source='/dev/vdb3'),
                     lambda s: s['host']['installed_boot']['authentication'].update(uid=0),
                     lambda s: s['host']['installed_boot'].update(receipt_sha256='f' * 64),
                     lambda s: s['host']['installed_boot']['qemu_argv'].extend(['-drive', 'file=/iso,media=cdrom,readonly=on']),
                     lambda s: s['host'].update(owned_qemu_stopped=False)]
        for mutate in mutations:
            report, state, files, media, serial = fixture(); mutate(state)
            with self.assertRaises(RuntimeError): A.validate_execution(state, state['image'], state['context']['execution_sha'], serial, media.__getitem__)

    def test_missing_or_changed_vt_restoration_image_is_rejected(self):
        report, state, files, media, serial = fixture()
        state['required_images'].pop('host/installer-vt-away-0.png')
        with self.assertRaises(RuntimeError): A.validate_execution(state, state['image'], state['context']['execution_sha'], serial, media.__getitem__)
        report, state, files, media, serial = fixture()
        media['host/installer-vt-away-0.png'] = media['installer/baseline.png']
        state['required_images']['host/installer-vt-away-0.png'] = A.digest(media['host/installer-vt-away-0.png'])
        state['host']['host_transitions'][0]['capture'].update(bytes=len(media['host/installer-vt-away-0.png']), sha256=A.digest(media['host/installer-vt-away-0.png']))
        with self.assertRaises(RuntimeError): A.validate_execution(state, state['image'], state['context']['execution_sha'], serial, media.__getitem__)

    def test_real_queued_modules_are_bound_to_selected_source_catalog_and_cannot_claim_active_download(self):
        report, state, files, media, serial = fixture()
        ids = A.validate_catalog_selection(report, (HERE.parents[1] / 'modules/catalog.toml').read_bytes())
        self.assertIn('gnome-web', ids)
        for mutate in (lambda r: r['baseline']['engine']['install']['options'].update(modules=[]),
                       lambda r: r['baseline']['engine']['install']['options']['modules'][0].update(status='downloading'),
                       lambda r: r['baseline']['engine']['install']['options']['modules'][0].update(percent=1),
                       lambda r: r['baseline']['config']['apps']['selection'].update(browser=['foreign-app'])):
            report, state, files, media, serial = fixture(); mutate(report)
            with self.assertRaises(RuntimeError): self.check_report(report, state, files, media)

    def test_pre_secret_password_prompts_and_seven_reviewable_images_are_required(self):
        mutations = [lambda s: s['host']['password_prompt_evidence']['getty'].update(observed_line_sha256=A.digest(b'login:')),
                     lambda s: s['host']['password_prompt_evidence']['sudo'].update(observed_line_sha256=A.digest(b'arcticqual@arctic-qual ~ >')),
                     lambda s: s['host']['password_prompt_evidence']['sudo'].update(observed_ns=1),
                     lambda s: s['host']['password_prompt_evidence']['engine'].update(program_sha256='f' * 64),
                     lambda s: s['required_images'].pop('host/installed-getty-password.png')]
        for mutate in mutations:
            report, state, files, media, serial = fixture(); mutate(state)
            # Separate host/build engine references to model a changed runtime receipt.
            state['build']['ocr_host'] = copy.deepcopy(state['build']['ocr_host'])
            if state['build']['ocr_host']['program_sha256'] == 'f' * 64: state['build']['ocr_host']['program_sha256'] = 'c' * 64
            with self.assertRaises(RuntimeError): A.validate_execution(state, state['image'], state['context']['execution_sha'], serial, media.__getitem__)


if __name__ == '__main__':
    unittest.main()
