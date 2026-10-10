"""Replay synthetic active artifacts through the actual publisher guards."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


P = load('active_installer_publication', ROOT / 'tools/qualified-release/prepare.py')
F = load('active_installer_publisher_fixture', ROOT / 'tools/installer-qualification/test_active_contract.py')
S = load('active_installer_public_screening', ROOT / 'tools/native-functional/screen-evidence.py')


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, allow_nan=False) + '\n')


def archive_fixture(folder):
    report, state, files, media, serial = F.fixture()
    host = folder / 'host'
    for name, data in media.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(data)
    write_json(host / 'host-execution.json', state['host'])
    write_json(host / 'installer-host-transitions.json', dict(schema='arctic-installer-host-transitions-v1',
        context=state['context'], boot_id=report['boot_id'], receipts=state['host']['host_transitions'], release_acceptance=False))
    write_json(folder / 'execution.json', state)
    for name in ('provision.log', 'capture-build.log', 'installer-harness.log'):
        (folder / name).write_bytes(b'Owned synthetic fixture\n')
    for name in ('vm-base-image-id.txt', 'vm-prepared-image-id.txt'):
        (folder / name).write_bytes(('sha256:' + 'a' * 64 + '\n').encode())
    members = {path.relative_to(folder).as_posix(): path.read_bytes() for path in folder.rglob('*') if path.is_file()
               and path.name not in ('port', 'serial')}
    if set(members) != set(F.A.ARCHIVE_FILES) - {'upload-screening.json'}:
        raise AssertionError('Synthetic archive fixture inventory differs')
    screening = dict(scope='Owned synthetic QEMU VM only; no host desktop, VM disks or credentials',
                     files={name: dict(original_sha256=F.A.digest(data), uploaded_sha256=F.A.digest(data), bytes=len(data), redactions=0)
                            for name, data in members.items()})
    members['upload-screening.json'] = json.dumps(screening, sort_keys=True).encode()
    pin = dict(source_sha=state['context']['execution_sha'], run_id=101, archive_sha256='f' * 64)
    manifest = dict(image=state['image'], installer_active=pin,
                    installer_active_media_review=dict(visual_status='passed', image_sha256=state['image']['sha256'],
                        installer_archive_sha256=pin['archive_sha256'], images=state['required_images']))
    return members, state, manifest


def reseal_guest_report(members, state):
    """Build coherent invalid-report bytes with the real transport serializer.

    Declared pass status is intentionally retained: the publisher must reject
    private semantic fields even when every original byte/hash alias agrees.
    """
    guest, report = state['guest'], state['guest']['report']
    wire = F.T.Controls()
    wire.context = state['context']; wire.identity = {key: report[key] for key in F.T.e.IDENTITY}
    wire.root, wire.report, wire.requests = report['evidence_root'], report, guest['requests']
    wire.begin, wire.proof, wire.end = guest['begin'], guest['provenance'], guest['collector']
    wire.files = {name: members['installer/' + name] for name in F.A.GUEST_IMAGES}
    wire.files['installer-report.json'] = (json.dumps(report, sort_keys=True) + '\n').encode()
    rows = wire.rows(); port, uart = wire.wire(rows)
    auth = state['host']['console_authentication']
    serial = ('ARCTIC-CONSOLE-READY=' + auth['nonce'] + ' user=liveuser uid=' + str(report['desktop_uid']) + '\n').encode() + uart
    # Run the real framing/duplicate/context decoder without accepting behavior.
    decoded = F.T.e.block(port, serial, state['context'])
    if decoded[2] != report:
        raise AssertionError('Resealed protected report alias differs')
    guest['port'] = dict(bytes=len(port), sha256=F.A.digest(port))
    guest['serial'] = dict(bytes=len(serial), sha256=F.A.digest(serial))
    guest['files']['installer-report.json'] = dict(bytes=len(wire.files['installer-report.json']), sha256=F.A.digest(wire.files['installer-report.json']))
    state['diagnostic_streams'].update({'serial.log': guest['serial'], 'installer-port.log': guest['port']})
    state['transport'].update(report_sha256=guest['files']['installer-report.json']['sha256'],
                              port_sha256=guest['port']['sha256'], serial_sha256=guest['serial']['sha256'])
    members.update({'host/serial.log': serial, 'host/installer-port.log.bounded-prefix.bin': port[:64 * 1024],
                    'installer/installer-report.json': wire.files['installer-report.json'],
                    'installer/serial-installer-report.json': wire.files['installer-report.json'],
                    'installer/transport-manifest.json': (json.dumps(rows[-2][1], sort_keys=True) + '\n').encode(),
                    'installer/installer-state.json': (json.dumps(guest, sort_keys=True) + '\n').encode(),
                    'execution.json': (json.dumps(state, sort_keys=True) + '\n').encode()})
    screening = json.loads(members['upload-screening.json'])
    for name, data in members.items():
        if name != 'upload-screening.json':
            screening['files'][name] = dict(original_sha256=F.A.digest(data), uploaded_sha256=F.A.digest(data), bytes=len(data), redactions=0)
    members['upload-screening.json'] = json.dumps(screening, sort_keys=True).encode()


class Controls(unittest.TestCase):
    def replay(self, folder, members, state, manifest):
        path = folder / 'active.zip'
        with zipfile.ZipFile(path, 'w') as output:
            for name, data in sorted(members.items()): output.writestr(name, data)

        def source_hash(ref, name):
            self.assertEqual(ref, state['context']['execution_sha'])
            return state['source_inputs'].get(name, 'a' * 64)

        def source_sha(path):
            return state['source_inputs'].get(path.relative_to(ROOT).as_posix(), 'a' * 64)

        def source_bytes(argv, **kwargs):
            self.assertEqual(argv[:4], ['git', '-C', str(ROOT), 'show'])
            ref, name = argv[4].split(':', 1)
            self.assertEqual(ref, state['image']['source_sha'])
            return (ROOT / name).read_bytes()

        with (patch.object(P, 'source_hash', side_effect=source_hash), patch.object(P, 'sha', side_effect=source_sha),
                patch.object(P, 'git', return_value=''), patch.object(P.subprocess, 'check_output', side_effect=source_bytes),
                zipfile.ZipFile(path) as archive):
            return P.installer_proof(archive, manifest, active=True)

    def test_actual_publisher_replays_complete_transport_and_requires_seven_image_review(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); members, state, manifest = archive_fixture(folder)
            result = self.replay(folder, members, state, manifest)
            self.assertFalse(result['release_acceptance'])
            self.assertEqual(result['restoration']['cases'], 2)
            self.assertEqual(len(result['execution']['images']), 7)
            for change in ('pending', 'missing-image', 'wrong-image', 'wrong-archive'):
                wrong = copy.deepcopy(manifest)
                review = wrong['installer_active_media_review']
                if change == 'pending': review['visual_status'] = 'pending'
                elif change == 'missing-image': review['images'].pop('host/installer-vt-away-0.png')
                elif change == 'wrong-image': review['image_sha256'] = 'e' * 64
                else: review['installer_archive_sha256'] = 'e' * 64
                with self.subTest(change=change), self.assertRaisesRegex(RuntimeError, 'visual review is absent'):
                    self.replay(folder, members, state, wrong)

    def test_complete_public_export_passes_actual_scanner_and_publisher_without_changing_originals(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            fixture = folder / 'fixture'; fixture.mkdir()
            members, state, manifest = archive_fixture(fixture)
            original = folder / 'original'; original.mkdir()
            for name, data in members.items():
                if name == 'upload-screening.json':
                    continue
                path = original / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
            screened = folder / 'screened'
            S.screen_external(original, screened)
            exported = {path.relative_to(screened).as_posix(): path.read_bytes()
                        for path in screened.rglob('*') if path.is_file()}
            receipt = json.loads(exported['upload-screening.json'])
            self.assertEqual(set(exported), set(members))
            for name, data in members.items():
                if name != 'upload-screening.json':
                    self.assertEqual(exported[name], data, name)
                    self.assertEqual(receipt['files'][name]['redactions'], 0, name)
                    self.assertEqual(receipt['files'][name]['original_sha256'], receipt['files'][name]['uploaded_sha256'], name)
            result = self.replay(folder, exported, state, manifest)
            self.assertFalse(result['release_acceptance'])
            self.assertEqual(len(result['execution']['images']), 7)

    def test_publisher_rejects_changed_original_installed_serial_even_with_a_new_screening_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); members, state, manifest = archive_fixture(folder)
            members['host/serial-installed.log'] += b'changed-original\n'
            screening = json.loads(members['upload-screening.json'])
            data = members['host/serial-installed.log']
            screening['files']['host/serial-installed.log'] = dict(original_sha256=F.A.digest(data), uploaded_sha256=F.A.digest(data), bytes=len(data), redactions=0)
            members['upload-screening.json'] = json.dumps(screening).encode()
            with self.assertRaisesRegex(RuntimeError, 'original serial bytes differ'):
                self.replay(folder, members, state, manifest)

    def test_publisher_rejects_private_wrappers_after_aliases_and_screening_are_resealed(self):
        paths = [(), ('execution',), ('image',), ('host',), ('guest',), ('build',), ('build', 'display_host'),
                 ('host', 'display_preparation'), ('host', 'display_preparation', 'heads', 0),
                 ('host', 'console_authentication'), ('host', 'host_transitions', 0),
                 ('host', 'host_transitions', 1, 'display', 'applied', 0),
                 ('transport',), ('diagnostic_streams', 'qemu-installer-installed.log')]
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); original, original_state, manifest = archive_fixture(folder)
            for path in paths:
                for key in ('password', 'raw_account'):
                    members, state, pin = copy.deepcopy(original), copy.deepcopy(original_state), copy.deepcopy(manifest)
                    F.add_private_payload(state, path, key)
                    # All duplicate structured aliases and the public screening
                    # receipt bind the changed bytes. Failure must come from the
                    # semantic contract rather than an unrelated stale hash.
                    updates = {'execution.json': state, 'host/host-execution.json': state['host'],
                               'installer/installer-state.json': state['guest'],
                               'host/installer-host-transitions.json': dict(schema='arctic-installer-host-transitions-v1',
                                    context=state['context'], boot_id=state['guest']['report']['boot_id'],
                                    receipts=state['host']['host_transitions'], release_acceptance=False)}
                    for name, value in updates.items():
                        members[name] = (json.dumps(value, sort_keys=True, allow_nan=False) + '\n').encode()
                    pin['image'] = copy.deepcopy(state['image'])
                    screening = json.loads(members['upload-screening.json'])
                    for name, data in members.items():
                        if name != 'upload-screening.json':
                            screening['files'][name] = dict(original_sha256=F.A.digest(data), uploaded_sha256=F.A.digest(data),
                                                           bytes=len(data), redactions=0)
                    members['upload-screening.json'] = json.dumps(screening, sort_keys=True).encode()
                    self.assertEqual(json.loads(members['host/host-execution.json']), state['host'])
                    self.assertEqual(json.loads(members['installer/installer-state.json']), state['guest'])
                    for name, item in screening['files'].items():
                        self.assertEqual(item['uploaded_sha256'], F.A.digest(members[name]))
                    with self.subTest(path=path, key=key), self.assertRaisesRegex(RuntimeError, 'private fields'):
                        self.replay(folder, members, state, pin)

    def test_publisher_rejects_guest_private_fields_with_coherent_original_transport_and_aliases(self):
        paths = [('security',), ('security', 'audit'), ('baseline', 'rpc_peer'), ('baseline', 'drm_heads'),
                 ('baseline', 'drm_heads', 'outputs', 'Virtual-1'), ('baseline', 'identities', 'gui')]
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); original, original_state, manifest = archive_fixture(folder)
            positive, positive_state = copy.deepcopy(original), copy.deepcopy(original_state)
            reseal_guest_report(positive, positive_state)
            self.assertFalse(self.replay(folder, positive, positive_state, manifest)['release_acceptance'])
            for path in paths:
                for key in ('password', 'raw_account'):
                    members, state = copy.deepcopy(original), copy.deepcopy(original_state)
                    F.add_private_payload(state['guest']['report'], path, key)
                    reseal_guest_report(members, state)
                    self.assertEqual(json.loads(members['installer/installer-report.json']), state['guest']['report'])
                    self.assertEqual(json.loads(members['installer/installer-state.json']), state['guest'])
                    with self.subTest(path=path, key=key), self.assertRaisesRegex(RuntimeError, 'private fields'):
                        self.replay(folder, members, state, manifest)

    def test_publication_manifest_keeps_both_installer_lanes_disabled_and_mandatory(self):
        manifest = json.loads((ROOT / 'tools/qualified-release/manifest.json').read_text())
        self.assertFalse(manifest['ready'])
        for key in ('installer', 'installer_media_review', 'installer_active', 'installer_active_media_review'):
            self.assertIsNone(manifest[key])

    def test_active_lane_rejects_failed_or_retried_actions_before_artifact_lookup(self):
        pin = dict(source_sha='a' * 40, run_id=7)
        run = dict(head_sha='a' * 40, path='.github/workflows/installer-active-candidate-20261009.yml',
                   event='push', run_attempt=1, status='completed', conclusion='success')
        for changes in ({'run_attempt': 2}, {'conclusion': 'failure'}, {'head_sha': 'b' * 40}):
            with patch.object(P, 'api', return_value=run | changes), patch.object(P, 'validate_artifact') as artifact:
                with self.assertRaises(RuntimeError):
                    P.validate_lane(pin, run['path'], 'candidate-installer-active-restoration')
                artifact.assert_not_called()


if __name__ == '__main__': unittest.main()
