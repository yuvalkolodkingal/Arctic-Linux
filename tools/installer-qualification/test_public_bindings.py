"""Public installer bindings and prompt receipts; synthetic, never VM qualification."""
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


F = load('public_binding_fixture', HERE / 'test_active_contract.py')
G = load('public_binding_producer', HERE / 'guest.py')
E = load('public_binding_consumer', HERE / 'evidence.py')
H = load('public_binding_host', HERE / 'controller.py')
D = load('public_binding_driver', HERE / 'driver.py')
N = load('public_binding_shared_transport', HERE.parent / 'native-functional/taskbar-runtime.py')
S = load('public_binding_console_pixels', HERE.parent / 'lib/iso_startup.py')
A = F.A


def old_field(value, replace=False):
    value['token'] = value.pop('binding_id') if replace else value.get('binding_id', 'f' * 32)


def keys_recursive(value):
    if isinstance(value, dict):
        yield from value
        for child in value.values():
            yield from keys_recursive(child)
    elif isinstance(value, list):
        for child in value:
            yield from keys_recursive(child)


class Controls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report, cls.state, cls.files, cls.media, cls.serial = F.fixture()

    def builder(self):
        state = copy.deepcopy(self.state)
        guest = state['guest']
        builder = F.T.Controls()
        builder.context = state['context']
        builder.identity = {key: guest['report'][key] for key in E.IDENTITY}
        builder.root, builder.report, builder.requests = guest['report']['evidence_root'], guest['report'], guest['requests']
        builder.begin, builder.proof, builder.end = guest['begin'], guest['provenance'], guest['collector']
        builder.files = {name: self.media['installer/' + name] for name in A.GUEST_IMAGES}
        builder.files['installer-report.json'] = E.canonical(builder.report) + b'\n'
        return builder

    def decode(self, builder, rows=None, requests=None, marker=None, context=None):
        port, serial = builder.wire(builder.rows() if rows is None else rows, requests, marker)
        begin, proof, report, chunks, manifest, end, receipt, observed = E.block(
            port, serial, builder.context if context is None else context)
        return E.decode(chunks, manifest, begin['context'], report)

    def test_real_producer_exporter_and_decoder_use_binding_id_while_shared_protocol_keeps_token(self):
        builder = self.builder()
        with tempfile.TemporaryDirectory(prefix='arctic-native-smoke-installer-public-') as temporary:
            root = Path(temporary)
            builder.root = str(root); builder.report['evidence_root'] = str(root)
            builder.files['installer-report.json'] = E.canonical(builder.report) + b'\n'
            for name, data in builder.files.items():
                (root / name).write_bytes(data)
            output = io.StringIO()
            G.export(root, os.geteuid(), builder.context['binding_id'], N, output)
            exported = [E.record(line, {'EVIDENCE-CHUNK', 'EVIDENCE-MANIFEST'}, E.MAX_FILE + 512)
                        for line in output.getvalue().splitlines(keepends=True)]
            rows = [('BEGIN', builder.begin), ('PROVENANCE', builder.proof), ('REPORT', builder.report),
                    *exported, ('END', builder.end)]
            self.assertEqual(self.decode(builder, rows), builder.files)
            self.assertNotIn('token', set(keys_recursive([value for _, value in rows])))
            collector = object.__new__(G.Installer)
            collector.context, collector.boot_id = builder.context, builder.report['boot_id']
            emitted = []
            collector.request_emit = lambda kind, value: emitted.append((kind, value))
            request = copy.deepcopy(builder.requests[0])
            fields = {key: value for key, value in request.items()
                      if key not in {'schema', 'kind', 'binding_id', 'boot_id', 'cycle', 'elapsed_ns'}}
            value = collector.request(request['kind'], request['cycle'], **fields)
            self.assertEqual(value['binding_id'], builder.context['binding_id'])
            self.assertNotIn('token', value)
            self.assertEqual(emitted, [('REQUEST', value)])
        self.assertNotIn('token', set(keys_recursive(self.state)))
        self.assertNotIn('ocr', set(keys_recursive(self.state)))
        self.assertNotIn('login_shell_ocr', set(keys_recursive(self.state)))
        self.assertIn('token', N.FIELDS)
        self.assertNotIn('binding_id', N.FIELDS)

    def test_legacy_context_fields_are_rejected_in_both_profiles(self):
        for active in (False, True):
            context = copy.deepcopy(self.state['context'])
            if not active:
                context = {key: context[key] for key in A.C.CONTEXT_KEYS}
                context['schema'] = 'arctic-installer-context-v1'
            for replace in (False, True):
                wrong = copy.deepcopy(context); old_field(wrong, replace)
                for validate in (G.validate_context, A.context_check if active else A.C.context_check):
                    with self.subTest(active=active, replace=replace, validator=validate.__name__), self.assertRaises(RuntimeError):
                        validate(wrong)

    def test_legacy_fields_fail_even_when_surrounding_transport_and_end_hash_are_resealed(self):
        for location in ('context', 'request', 'chunk', 'manifest', 'collector', 'port_end'):
            for replace in (False, True):
                builder = self.builder()
                marker = None; expected_context = None
                if location == 'context':
                    expected_context = copy.deepcopy(builder.context)
                    old_field(expected_context, replace)
                    # All three protected context aliases carry the same change.
                    for record in (builder.begin, builder.proof, builder.report):
                        record['context'] = copy.deepcopy(expected_context)
                    builder.files['installer-report.json'] = E.canonical(builder.report) + b'\n'
                elif location == 'request':
                    old_field(builder.requests[0], replace)
                    builder.report['cases'][0]['disruption']['request'] = copy.deepcopy(builder.requests[0])
                    builder.files['installer-report.json'] = E.canonical(builder.report) + b'\n'
                rows = builder.rows()
                if location in ('chunk', 'manifest', 'collector'):
                    target = next(value for kind, value in rows if kind == {
                        'chunk': 'EVIDENCE-CHUNK', 'manifest': 'EVIDENCE-MANIFEST', 'collector': 'END'}[location])
                    old_field(target, replace)
                if location == 'port_end':
                    marker = dict(schema='arctic-installer-port-end-v1', binding_id=builder.context['binding_id'],
                                  **builder.identity, status=rows[-1][1]['status'], release_acceptance=False,
                                  end_sha256=E.digest(E.canonical(rows[-1][1])))
                    old_field(marker, replace)
                with self.subTest(location=location, replace=replace), self.assertRaises(RuntimeError):
                    self.decode(builder, rows, marker=marker, context=expected_context)

    def test_fresh_binding_rejects_replayed_boot_and_foreign_chunk_manifest_end_or_uart(self):
        builder = self.builder()
        fresh = dict(builder.context, binding_id='e' * 32)
        with self.assertRaises(RuntimeError):
            self.decode(builder, context=fresh)
        for location in ('request', 'chunk', 'manifest', 'collector', 'port_end'):
            builder = self.builder(); rows = builder.rows(); marker = None
            if location == 'request':
                builder.requests[0]['binding_id'] = 'e' * 32
            elif location == 'port_end':
                marker = dict(schema='arctic-installer-port-end-v1', binding_id='e' * 32,
                              **builder.identity, status=rows[-1][1]['status'], release_acceptance=False,
                              end_sha256=E.digest(E.canonical(rows[-1][1])))
            else:
                kind = {'chunk': 'EVIDENCE-CHUNK', 'manifest': 'EVIDENCE-MANIFEST', 'collector': 'END'}[location]
                next(value for name, value in rows if name == kind)['binding_id'] = 'e' * 32
            with self.subTest(location=location), self.assertRaises(RuntimeError):
                self.decode(builder, rows, marker=marker)

    def test_original_uart_boot_order_duplicate_and_end_digest_gates_remain_required(self):
        for alteration in ('wrong-boot', 'duplicate-request', 'reordered-requests', 'duplicate-end', 'stale-end-digest'):
            builder = self.builder(); rows = builder.rows(); requests = copy.deepcopy(builder.requests)
            if alteration == 'wrong-boot': requests[0]['boot_id'] = '33333333-3333-3333-3333-333333333333'
            elif alteration == 'duplicate-request': requests.insert(0, copy.deepcopy(requests[0]))
            elif alteration == 'reordered-requests': requests.reverse()
            port, serial = builder.wire(rows, requests)
            if alteration == 'duplicate-end':
                serial += b'\n' + next(line for line in serial.splitlines(keepends=True) if line.startswith(E.PREFIX.encode() + b'PORT-END '))
            elif alteration == 'stale-end-digest':
                lines = serial.splitlines(keepends=True)
                for index, line in enumerate(lines):
                    if line.startswith(E.PREFIX.encode() + b'PORT-END '):
                        kind, marker = E.record(line.decode(), {'PORT-END'}, 16448)
                        marker['end_sha256'] = '0' * 64
                        lines[index] = (E.PREFIX + kind + ' ' + json.dumps(marker) + '\n').encode()
                serial = b''.join(lines)
            with self.subTest(alteration=alteration), self.assertRaises(RuntimeError):
                E.block(port, serial, builder.context)

    def test_active_export_wrappers_and_report_reject_added_or_renamed_old_token(self):
        paths = [(), ('context',), ('host',), ('guest',), ('guest', 'context'), ('guest', 'collector'),
                 ('guest', 'port_end'), ('guest', 'begin', 'context'), ('guest', 'provenance', 'context'), ('transport',)]
        for path in paths:
            for replace in (False, True):
                state = copy.deepcopy(self.state); target = state
                for part in path: target = target[part]
                if replace and 'binding_id' not in target: continue
                old_field(target, replace)
                with self.subTest(path=path, replace=replace), self.assertRaises(RuntimeError):
                    A.validate_execution(state, state['image'], state['context']['execution_sha'], self.serial, self.media.__getitem__)
        report = copy.deepcopy(self.report); report['token'] = self.state['context']['binding_id']
        with self.assertRaises(RuntimeError):
            A.validate_report(report, self.state['context'], self.files,
                              lambda name: self.media['installer/' + name], self.report['baseline']['packaged_sources'])

    def test_foreign_binding_and_legacy_request_never_mutate_owned_outputs_or_query_target(self):
        for alteration in ('foreign-binding', 'add-token', 'rename-token'):
            request = copy.deepcopy(self.state['guest']['requests'][0])
            if alteration == 'foreign-binding': request['binding_id'] = 'e' * 32
            else: old_field(request, alteration == 'rename-token')
            display = types.SimpleNamespace(proof=self.state['host']['display_preparation'],
                                            _query=Mock(), _owner=Mock(), _call=Mock())
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); serial = root / 'serial.log'
                serial.write_text(H.REQUEST_PREFIX + json.dumps(request) + '\n')
                controller = H.InstallerController(object(), display, self.state['context'], root)
                with self.subTest(alteration=alteration), self.assertRaises(RuntimeError):
                    controller.poll(serial)
                display._query.assert_not_called(); display._owner.assert_not_called(); display._call.assert_not_called()
                self.assertEqual(controller.receipts, []); self.assertEqual(controller.position, 0)
                self.assertEqual(controller.disconnected, set())

    def test_active_protected_aliases_reject_foreign_bindings_with_coherent_uart_and_stream_hashes(self):
        for path in (('begin', 'context'), ('provenance', 'context'), ('collector',), ('port_end',)):
            state, media = copy.deepcopy(self.state), copy.deepcopy(self.media)
            guest = state['guest']; target = guest
            for part in path: target = target[part]
            target['binding_id'] = 'e' * 32
            guest['port_end']['end_sha256'] = E.digest(E.canonical(guest['collector']))
            builder = self.builder()
            builder.begin, builder.proof, builder.end = guest['begin'], guest['provenance'], guest['collector']
            port, uart = builder.wire(builder.rows(), marker=guest['port_end'])
            serial = ('ARCTIC-CONSOLE-READY=' + state['host']['console_authentication']['nonce'] +
                      ' user=liveuser uid=' + str(self.report['desktop_uid']) + '\n').encode() + uart
            guest['port'] = dict(bytes=len(port), sha256=E.digest(port))
            guest['serial'] = dict(bytes=len(serial), sha256=E.digest(serial))
            state['diagnostic_streams'].update({'installer-port.log': guest['port'], 'serial.log': guest['serial']})
            state['transport'].update(port_sha256=guest['port']['sha256'], serial_sha256=guest['serial']['sha256'])
            media.update({'host/serial.log': serial, 'host/installer-port.log.bounded-prefix.bin': port[:64 * 1024]})
            self.assertEqual(guest['port_end']['end_sha256'], E.digest(E.canonical(guest['collector'])))
            self.assertEqual(guest['serial'], state['diagnostic_streams']['serial.log'])
            with self.subTest(path=path), self.assertRaises(RuntimeError):
                A.validate_execution(state, state['image'], state['context']['execution_sha'], serial, media.__getitem__)

    def test_prompt_kind_hash_observation_order_and_capture_aliases_are_required(self):
        original = self.state['host']['password_prompt_evidence']
        def check(value):
            return A.password_prompts_check(value, self.state['build'], self.state['required_images'], self.media.__getitem__)
        check(original)
        for slot in ('getty', 'sudo'):
            safe = copy.deepcopy(original); safe[slot]['path'] = 'host/' + safe[slot]['path']; check(safe)
            for alteration in ('old-ocr-added', 'old-ocr-replaced', 'wrong-kind', 'wrong-line-hash', 'wrong-capture-alias'):
                wrong = copy.deepcopy(original); item = wrong[slot]
                if alteration == 'old-ocr-added': item['ocr'] = 'Password:'
                elif alteration == 'old-ocr-replaced': item['ocr'] = item.pop('observed_line_sha256')
                elif alteration == 'wrong-kind': item['prompt_kind'] = 'sudo-auth' if slot == 'getty' else 'getty-auth'
                elif alteration == 'wrong-line-hash': item['observed_line_sha256'] = '0' * 64
                else: item['path'] = 'installed-' + ('sudo' if slot == 'getty' else 'getty') + '-password.png'
                with self.subTest(slot=slot, alteration=alteration), self.assertRaises(RuntimeError): check(wrong)
        for alteration in ('old-shell-added', 'old-shell-replaced', 'wrong-shell-kind', 'wrong-shell-hash', 'before-getty', 'after-sudo'):
            wrong = copy.deepcopy(original)
            if alteration == 'old-shell-added': wrong['login_shell_ocr'] = 'arcticqual@arctic-qual ~ >'
            elif alteration == 'old-shell-replaced': wrong['login_shell_ocr'] = wrong.pop('login_shell')
            elif alteration == 'wrong-shell-kind': wrong['login_shell']['prompt_kind'] = 'getty-auth'
            elif alteration == 'wrong-shell-hash': wrong['login_shell']['observed_line_sha256'] = '0' * 64
            elif alteration == 'before-getty': wrong['login_shell']['observed_ns'] = wrong['getty']['observed_ns']
            else: wrong['login_shell']['observed_ns'] = wrong['sudo']['observed_ns']
            with self.subTest(alteration=alteration), self.assertRaises(RuntimeError): check(wrong)

    def test_actual_console_observer_hashes_only_the_verified_last_line_and_withholds_private_or_wrong_prompts(self):
        cases = [('installed-getty-password', 'Password:', 'getty-auth'),
                 ('installed-login-shell', 'arcticqual@arctic-qual ~ >', 'installed-user-shell'),
                 ('installed-sudo-password', '[sudo] password for arcticqual:', 'sudo-auth')]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for label, expected, kind in cases:
                probe = root / (label + '-probe.png')
                image = Image.new('RGB', (1280, 720), 'black'); ImageDraw.Draw(image).text((20, 20), expected, fill='white'); image.save(probe)
                vm = types.SimpleNamespace(alive=lambda: True, shot=lambda _: probe)
                observed = ('Unrelated earlier console line\n  ' + expected + '_|  \n').encode()
                with patch.object(D.subprocess, 'run', return_value=types.SimpleNamespace(stdout=observed)):
                    cap = D.console_prompt(vm, S, root, label, expected, 'a' * 32, archive=label != 'installed-login-shell')
                self.assertEqual(cap['prompt_kind'], kind)
                self.assertEqual(cap['observed_line_sha256'], A.digest(expected.encode()))
                self.assertNotIn('ocr', cap); self.assertNotIn(expected, cap.values())
            for number, observed in enumerate((b'Not the expected last line\n', b'a' * 32 + b'\nPassword:\n')):
                refusal = root / ('refusal-' + str(number)); refusal.mkdir()
                probe = refusal / 'refused-probe.png'; image.save(probe)
                vm = types.SimpleNamespace(alive=Mock(side_effect=[True, False]), shot=lambda _: probe)
                with patch.object(D.subprocess, 'run', return_value=types.SimpleNamespace(stdout=observed)), patch.object(D.time, 'sleep'):
                    reason = 'exact console prompt was not observed' if number == 0 else 'private input unexpectedly appeared'
                    with self.subTest(case=number), self.assertRaisesRegex(RuntimeError, reason):
                        D.console_prompt(vm, S, refusal, 'installed-getty-password', 'Password:', 'a' * 32)
                self.assertTrue(probe.exists())
                self.assertFalse((refusal / 'installed-getty-password.png').exists())

    def test_two_installed_authentications_get_distinct_nonces_and_original_uart_replay_is_rejected(self):
        reports = []
        for number in range(2):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); (root / 'data').mkdir()
                (root / 'data/active-credentials.json').write_text(json.dumps({'password': 'a' * 32}))
                helper = A.strict_json(self.media['host/installed-boot.json'])
                helper['boot_id'] = str(number + 4) * 8 + '-4444-4444-4444-444444444444'
                def type_text(value, gap=0):
                    if value.startswith('sudo sh /dev/sr0 '):
                        nonce = value.rsplit(' ', 1)[1]
                        self.assertRegex(nonce, r'^[0-9a-f]{32}$')
                        helper['authentication']['nonce'] = nonce
                        data = ('ARCTIC-ACTIVE-INSTALLED-READY=' + nonce + ' user=arcticqual uid=1000\nARCTIC-ACTIVE-INSTALLED ' +
                                json.dumps(helper, sort_keys=True) + '\n').encode()
                        (root / 'serial-installed.log').write_bytes(data)
                vm = types.SimpleNamespace(alive=lambda: True, shot=lambda _: root / 'synthetic-display.png',
                                           cmd=lambda *args, **kw: {}, keys=lambda *args: None, type_text=type_text)
                vmtest = types.SimpleNamespace(looks_like_boot_menu=lambda _: False, classify=lambda _: 'login')
                startup = types.SimpleNamespace(console_screen=lambda _: True)
                def prompt(vm, startup, out, label, expected, password, archive=True):
                    key = {'installed-getty-password': 'getty', 'installed-sudo-password': 'sudo', 'installed-login-shell': 'login_shell'}[label]
                    return copy.deepcopy(self.state['host']['password_prompt_evidence'][key])
                with patch.object(D, 'console_prompt', side_effect=prompt), patch.object(D, 'ocr_provenance', return_value=self.state['build']['ocr_host']), \
                        patch.object(D, 'load', return_value=G), patch.object(D.time, 'sleep'):
                    report, serial, prompts = D.boot_installed(vm, startup, vmtest, root, self.state['context'])
                reports.append(report)
                receipt = copy.deepcopy(self.state['host']['installed_boot'])
                receipt.update(boot_id=report['boot_id'], authentication=report['authentication'], serial=serial,
                               receipt_sha256=A.digest(E.canonical(report)))
                uart = (root / 'serial-installed.log').read_bytes()
                self.assertEqual(A.installed_boot_check(receipt, self.state['context'], self.report, 200, uart), report)
                for alteration in ('foreign-nonce', 'duplicate-ready', 'separated-ready', 'duplicate-report', 'foreign-binding'):
                    wrong = copy.deepcopy(receipt); changed = uart
                    if alteration == 'foreign-nonce': wrong['authentication']['nonce'] = 'f' * 32
                    elif alteration == 'duplicate-ready': changed += uart.splitlines(keepends=True)[0]
                    elif alteration == 'separated-ready': changed = changed.replace(b'\nARCTIC-ACTIVE-INSTALLED ', b'\nunrelated\nARCTIC-ACTIVE-INSTALLED ')
                    elif alteration == 'duplicate-report': changed += uart.splitlines(keepends=True)[1]
                    else:
                        foreign = copy.deepcopy(report); foreign['context']['binding_id'] = 'e' * 32
                        changed = uart.splitlines(keepends=True)[0] + b'ARCTIC-ACTIVE-INSTALLED ' + E.canonical(foreign) + b'\n'
                        wrong['receipt_sha256'] = A.digest(E.canonical(foreign))
                    wrong['serial'] = dict(bytes=len(changed), sha256=A.digest(changed))
                    with self.subTest(alteration=alteration), self.assertRaises(RuntimeError):
                        A.installed_boot_check(wrong, self.state['context'], self.report, 200, changed)
        self.assertNotEqual(reports[0]['authentication']['nonce'], reports[1]['authentication']['nonce'])
        self.assertNotEqual(reports[0]['authentication']['nonce'], self.state['context']['binding_id'])


if __name__ == '__main__':
    unittest.main()
