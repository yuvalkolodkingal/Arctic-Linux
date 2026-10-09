"""Synthetic transport and negative controls; no VM or release acceptance."""
import base64
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zlib

from PIL import Image

spec = importlib.util.spec_from_file_location('installer_evidence_controls', Path(__file__).with_name('evidence.py'))
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)


class Controls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = dict(schema='arctic-installer-context-v1', source_sha='1' * 40, execution_sha='2' * 40,
            iso_sha256='3' * 64, iso_bytes=1_929_381_888, token='4' * 32,
            checker_sha256='5' * 64, runtime_sha256='6' * 64, native_sha256='7' * 64, capture_sha256='8' * 64)
        cls.identity = dict(boot_id='01234567-89ab-cdef-0123-456789abcdef', desktop_uid=1000,
                            active_desktop_session='2')
        cls.root = '/tmp/arctic-native-smoke-installer-control'
        cls.transport = dict(schema='arctic-installer-virtio-port-v1', name='arctic-installer-evidence',
                             device='/dev/vport1p1', major=241, minor=1, uid=0, mode=0o600)
        cls.begin = dict(schema='arctic-installer-runner-v1', stage='live', context=cls.context,
                         **cls.identity, transport=cls.transport, release_acceptance=False)
        cls.proof = dict(schema='arctic-installer-provenance-v1', stage='live', context=cls.context,
                         **cls.identity, transport=cls.transport, release_acceptance=False,
                         cmdline='ro rd.live.image arctic.mode=install', virtualization='qemu')
        cls.end = dict(token=cls.context['token'], **cls.identity, status='passed', error=None,
                       evidence_export_complete=True, release_acceptance=False)
        image = Image.new('RGB', (1280, 720), (32, 36, 40))
        stream = io.BytesIO()
        image.save(stream, format='PNG')
        cls.png = stream.getvalue()
        engine = {'wizard': {'current': 'keyboard', 'state': 'wizard'}}
        def output(name='Virtual-1', enabled=True):
            return dict(name=name, enabled=enabled, transform='normal', scale=1,
                        modes=[dict(current=True, width=1280, height=720)])
        def observation(name='Virtual-1', available=None, file='baseline.png'):
            outputs = available or [output(), output('Virtual-2')]
            state = dict(page='keyboard', current='keyboard', keyboard='il', view='step', connected=True,
                ready=True, valid=True, busy=False, failure='', error='', fields={},
                window=dict(visible=True, backing_visible=True, width=1280, height=720,
                            screen=name, background='#202428'))
            visible = e.guest.window_proof(state, [dict(name='arctic-installer', layer='top', monitor=name)],
                                          outputs, sum(o['enabled'] for o in outputs))
            capture = dict(path=file, bytes=len(cls.png), sha256=e.digest(cls.png), size=[1280, 720],
                           background=[32, 36, 40], pixels=[[32, 36, 40]] * 9,
                           region=[1269, 359, 1272, 362], tolerance=3)
            return dict(engine=engine, state=state, outputs=outputs, visible=visible, capture=capture)
        baseline = observation()
        cls.report = dict(schema=e.guest.SCHEMA, stage='live', status='passed', context=cls.context,
                          **cls.identity, original_vt=2, evidence_root=cls.root, release_acceptance=False,
                          baseline=baseline, cases=[], captures=9, errors=[])
        cls.requests = []
        def request(kind, cycle, **fields):
            value = dict(schema='arctic-installer-request-v1', kind=kind, cycle=cycle,
                         token=cls.context['token'], boot_id=cls.identity['boot_id'], **fields)
            cls.requests.append(value)
            return value
        for cycle in range(3):
            away = dict(session='2', uid=1000, vt=2, active=False, foreground='tty6')
            req = request('vt-away', cycle, away=away, original_vt=2, engine_sha256=e.digest(e.canonical(engine)))
            case = dict(kind='vt', cycle=cycle, status='passed', **observation(file='vt-' + str(cycle) + '.png'))
            case['disruption'] = dict(away=away, prepared_state={'engine': engine}, request=req, returned_vt=2)
            cls.report['cases'].append(case)
        for cycle in range(3):
            mode = 'all' if cycle == 1 else 'hosting-only'
            common = dict(mode=mode, hosting_output='Virtual-1', hosting_head=0,
                          enabled_outputs=['Virtual-1', 'Virtual-2'], engine_sha256=e.digest(e.canonical(engine)))
            disconnect = request('output-disconnect', cycle, **common)
            actual = [output(enabled=False), output('Virtual-2', enabled=cycle != 1)]
            if cycle == 1:
                unavailable = dict(engine=engine, outputs=actual, enabled_output_count=0, installer_layers=[])
            else:
                unavailable = observation('Virtual-2', actual, 'output-' + str(cycle) + '-relocated.png')
                unavailable['enabled_output_count'] = 1
            restore = request('output-restore', cycle, **common, enabled_output_count=unavailable['enabled_output_count'],
                              outputs=actual, outputs_sha256=e.digest(e.canonical(actual)))
            case = dict(kind='output', cycle=cycle, status='passed', **observation(file='output-' + str(cycle) + '.png'))
            case['disruption'] = dict(mode=mode, hosting_output='Virtual-1', hosting_head=0,
                                     disconnect_request=disconnect, unavailable=unavailable, restore_request=restore)
            cls.report['cases'].append(case)
        cls.files = {name: cls.png for name in e.PNG_NAMES}
        cls.files['installer-report.json'] = json.dumps(cls.report).encode()

    def rows(self, files=None, report=None, end=None):
        files = self.files if files is None else files
        report = self.report if report is None else report
        rows = [('BEGIN', copy.deepcopy(self.begin)), ('PROVENANCE', copy.deepcopy(self.proof)),
                ('REPORT', copy.deepcopy(report))]
        entries = []
        for name, data in sorted(files.items()):
            compressed = zlib.compress(data, 9)
            parts = [compressed[i:i + e.CHUNK] for i in range(0, len(compressed), e.CHUNK)]
            entries.append(dict(path=name, bytes=len(data), sha256=e.digest(data), compressed_bytes=len(compressed),
                                chunks=len(parts), encoding='zlib+base64'))
            rows.extend(('EVIDENCE-CHUNK', dict(token=self.context['token'], path=name, index=i,
                       data=base64.b64encode(part).decode())) for i, part in enumerate(parts))
        rows.extend((('EVIDENCE-MANIFEST', dict(schema='arctic-installer-evidence-v1', token=self.context['token'],
                      evidence_root=self.root, files=entries, bytes=sum(map(len, files.values())))),
                     ('END', copy.deepcopy(self.end if end is None else end))))
        return rows

    def wire(self, rows, requests=None, marker=None):
        end = rows[-1][1]
        marker = (dict(schema='arctic-installer-port-end-v1', token=self.context['token'], **self.identity,
                       status=end['status'], release_acceptance=False, end_sha256=e.digest(e.canonical(end)))
                  if marker is None else marker)
        port = ''.join(e.PREFIX + kind + ' ' + json.dumps(value) + '\n' for kind, value in rows).encode()
        uart = ('Linux diagnostic unrelated to evidence\n' + ''.join(e.PREFIX + 'REQUEST ' + json.dumps(value) + '\n'
                for value in (self.requests if requests is None else requests))
                + e.PREFIX + 'PORT-END ' + json.dumps(marker) + '\n' + 'ordinary unfinished login prompt').encode()
        return port, uart

    def check(self, rows=None, requests=None, marker=None):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            port, uart = self.wire(self.rows() if rows is None else rows, requests, marker)
            (root / 'port').write_bytes(port)
            (root / 'serial').write_bytes(uart)
            return e.extract(root / 'port', root / 'serial', root / 'installer', self.context)

    def test_complete_synthetic_transport_binds_state_and_keeps_release_scope_false(self):
        result = self.check()
        state = result['state']
        self.assertEqual(state['status'], 'passed')
        self.assertEqual(state['received_pngs'], 9)
        self.assertEqual(state['requests'], self.requests)
        self.assertEqual(state['report'], self.report)
        self.assertEqual(state['collector'], self.end)
        self.assertEqual(state['files'], result['files'])
        self.assertFalse(state['release_acceptance'])
        self.assertEqual(set(result['names']), e.PNG_NAMES | {'installer-report.json'})

    def test_missing_duplicate_unknown_reordered_port_records_fail(self):
        original = self.rows()
        for rows in (original[1:], original + [original[-1]], [original[1], original[0], *original[2:]],
                     original[:3] + [original[2]] + original[3:],
                     original[:3] + [('UNKNOWN', {})] + original[3:]):
            with self.assertRaises(RuntimeError):
                self.check(rows)

    def test_duplicate_keys_nonfinite_nonascii_and_incomplete_records_fail(self):
        port, uart = self.wire(self.rows())
        for changed in (port.replace(b'"stage": "live"', b'"stage":"live","stage":"live"', 1),
                        port.replace(b'"iso_bytes": 1929381888', b'"iso_bytes":NaN', 1),
                        port[:-1], port + b'\xff', port + b'\n'):
            with self.assertRaises((RuntimeError, ValueError, UnicodeError)):
                e.block(changed, uart, self.context)

    def test_boot_uid_session_image_token_and_named_port_are_bound(self):
        for index, key, value in ((0, 'desktop_uid', True), (1, 'boot_id', 'ffffffff-ffff-ffff-ffff-ffffffffffff'),
                                  (1, 'active_desktop_session', '3'), (1, 'desktop_uid', 1000.0)):
            rows = self.rows()
            rows[index][1][key] = value
            with self.assertRaises(RuntimeError):
                self.check(rows)
        for change in ('context', 'port', 'live'):
            rows = self.rows()
            if change == 'context':
                rows[0][1]['context']['token'] = '0' * 32
            elif change == 'port':
                rows[0][1]['transport']['name'] = 'arctic-taskbar-evidence'
            else:
                rows[1][1]['cmdline'] = 'ro rd.live.image arctic.mode=try'
            with self.assertRaises(RuntimeError):
                self.check(rows)

    def test_uart_end_digest_identity_duplicates_and_foreign_records_fail(self):
        port, uart = self.wire(self.rows())
        marker = dict(schema='arctic-installer-port-end-v1', token=self.context['token'], **self.identity,
                      status='passed', release_acceptance=False, end_sha256='0' * 64)
        with self.assertRaises(RuntimeError):
            self.check(marker=marker)
        for changed in (uart + b'\n' + e.PREFIX.encode() + b'PORT-END {}\n',
                        uart.replace(b'ARCTIC-INSTALLER-PORT-END ', b'ARCTIC-INSTALLER-REPORT ', 1),
                        uart.replace(b'ARCTIC-INSTALLER-REQUEST ', b'ARCTIC-INSTALLER-UNKNOWN ', 1)):
            with self.assertRaises(RuntimeError):
                e.block(port, changed, self.context)

    def test_duplicate_foreign_or_reordered_requests_fail(self):
        for requests in (self.requests[1:], self.requests + [self.requests[-1]],
                         [self.requests[1], self.requests[0], *self.requests[2:]]):
            with self.assertRaises(RuntimeError):
                self.check(requests=requests)
        for key, value in (('token', '0' * 32), ('cycle', True), ('boot_id', 'f' * 36)):
            requests = copy.deepcopy(self.requests)
            requests[0][key] = value
            with self.assertRaises(RuntimeError):
                self.check(requests=requests)

    def test_actual_uart_request_must_equal_embedded_case_receipt(self):
        requests = copy.deepcopy(self.requests)
        requests[0]['engine_sha256'] = '0' * 64
        result = self.check(requests=requests)
        self.assertEqual(result['state']['status'], 'failed')
        self.assertIn('requests differ', result['state']['errors'][0])

    def test_host_restore_requires_actual_missing_output_count_and_digest(self):
        for mutation in ('count', 'hosting', 'digest'):
            requests = copy.deepcopy(self.requests)
            restore = requests[4]
            if mutation == 'count':
                restore['enabled_output_count'] = 0
            elif mutation == 'hosting':
                restore['outputs'][0]['enabled'] = True
                restore['outputs'][1]['enabled'] = False
                restore['outputs_sha256'] = e.digest(e.canonical(restore['outputs']))
            else:
                restore['outputs_sha256'] = '0' * 64
            with self.assertRaises(RuntimeError):
                self.check(requests=requests)

    def test_archive_unsafe_reserved_duplicate_or_unsorted_paths_fail(self):
        for name in ('../outside.png', '/outside.png', 'nested/baseline.png', 'installer-state.json',
                     'baseline\\.png', 'private.json'):
            rows = self.rows()
            rows[-2][1]['files'][0]['path'] = name
            with self.assertRaises(RuntimeError):
                self.check(rows)
        for change in ('duplicate', 'order'):
            rows = self.rows()
            if change == 'duplicate':
                rows[-2][1]['files'].append(copy.deepcopy(rows[-2][1]['files'][0]))
            else:
                rows[-2][1]['files'].reverse()
            with self.assertRaises(RuntimeError):
                self.check(rows)

    def test_chunk_order_foreign_token_boolean_index_and_noncanonical_base64_fail(self):
        for mutation in ('swap', 'duplicate', 'token', 'index', 'data'):
            rows = self.rows()
            if mutation == 'swap':
                rows[3], rows[4] = rows[4], rows[3]
            elif mutation == 'duplicate':
                rows.insert(3, copy.deepcopy(rows[3]))
            elif mutation == 'token':
                rows[3][1]['token'] = '0' * 32
            elif mutation == 'index':
                rows[3][1]['index'] = True
            else:
                rows[3][1]['data'] += '\n'
            with self.assertRaises((RuntimeError, ValueError)):
                self.check(rows)

    def test_bounds_zlib_bomb_trailing_stream_and_wrong_hash_fail(self):
        for mutation in ('filebytes', 'aggregate', 'count', 'bomb', 'trailing', 'hash'):
            rows = self.rows()
            entry, chunk = rows[-2][1]['files'][0], rows[3][1]
            if mutation == 'filebytes':
                entry['bytes'] = e.MAX_FILE + 1
            elif mutation == 'aggregate':
                rows[-2][1]['bytes'] = e.MAX_TOTAL + 1
            elif mutation == 'count':
                entry['chunks'] = True
            elif mutation == 'hash':
                entry['sha256'] = '0' * 64
            else:
                compressed = (zlib.compress(b'x' * (e.MAX_FILE + 1)) if mutation == 'bomb' else
                              base64.b64decode(chunk['data']) + zlib.compress(b'ignored'))
                self.assertLess(len(compressed), e.CHUNK)
                chunk['data'] = base64.b64encode(compressed).decode()
                entry['compressed_bytes'] = len(compressed)
            with self.assertRaises(RuntimeError):
                self.check(rows)

    def test_report_archive_must_equal_authoritative_port_report(self):
        files = dict(self.files)
        files['installer-report.json'] = b'{}'
        with self.assertRaises(RuntimeError):
            self.check(self.rows(files=files))

    def test_report_json_type_changes_cannot_hide_behind_python_numeric_equality(self):
        changed = copy.deepcopy(self.report)
        changed['cases'][0]['cycle'] = False
        self.assertEqual(changed, self.report)  # Python equality coerces bool/int; the extractor must not.
        files = dict(self.files)
        files['installer-report.json'] = json.dumps(changed).encode()
        with self.assertRaises(RuntimeError):
            self.check(self.rows(files=files))

    def test_missing_png_fake_logged_pixels_and_incomplete_cases_preserve_failed_state(self):
        files = dict(self.files)
        files.pop('output-2-relocated.png')
        self.assertEqual(self.check(self.rows(files=files))['state']['status'], 'failed')
        for change in ('pixels', 'cases'):
            report = copy.deepcopy(self.report)
            if change == 'pixels':
                report['baseline']['capture']['pixels'][0] = [0, 0, 0]
            else:
                report['cases'].pop()
            files = dict(self.files)
            files['installer-report.json'] = json.dumps(report).encode()
            self.assertEqual(self.check(self.rows(files=files, report=report))['state']['status'], 'failed')

    def test_actual_wrong_png_pixels_cannot_pass_with_correct_content_hash(self):
        stream = io.BytesIO()
        Image.new('RGB', (1280, 720), (0, 0, 0)).save(stream, format='PNG')
        bad = stream.getvalue()
        files = dict(self.files)
        files['baseline.png'] = bad
        report = copy.deepcopy(self.report)
        report['baseline']['capture'].update(bytes=len(bad), sha256=e.digest(bad))
        files['installer-report.json'] = json.dumps(report).encode()
        result = self.check(self.rows(files=files, report=report))
        self.assertEqual(result['state']['status'], 'failed')
        self.assertIn('pixel gate', result['state']['errors'][0])

    def test_valid_failed_guest_archive_is_retained_without_manual_acceptance(self):
        report = copy.deepcopy(self.report)
        report.update(status='failed', cases=[], captures=0, errors=['synthetic guest failure'])
        files = {'installer-report.json': json.dumps(report).encode()}
        end = dict(self.end, status='failed', error='synthetic guest failure')
        result = self.check(self.rows(files=files, report=report, end=end), requests=[])
        self.assertEqual(result['state']['status'], 'failed')
        self.assertEqual(result['report'], report)
        self.assertEqual(result['names'], ['installer-report.json'])
        self.assertFalse(result['state']['release_acceptance'])

    def test_no_archive_is_written_before_transport_hash_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            rows = self.rows()
            rows[-2][1]['files'][0]['sha256'] = '0' * 64
            port, uart = self.wire(rows)
            (root / 'port').write_bytes(port)
            (root / 'serial').write_bytes(uart)
            with self.assertRaises(RuntimeError):
                e.extract(root / 'port', root / 'serial', root / 'installer', self.context)
            self.assertFalse((root / 'installer').exists())

    def test_unused_destination_and_symlink_parent_are_required(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            port, uart = self.wire(self.rows())
            (root / 'port').write_bytes(port)
            (root / 'serial').write_bytes(uart)
            (root / 'existing').mkdir()
            (root / 'link').symlink_to(root / 'existing', target_is_directory=True)
            for target in (root / 'existing', root / 'link/installer'):
                with self.assertRaises(RuntimeError):
                    e.extract(root / 'port', root / 'serial', target, self.context)


if __name__ == '__main__':
    unittest.main()
