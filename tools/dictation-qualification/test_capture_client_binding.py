"""Collector ownership controls; these synthetic cases do not qualify an image."""
import ast
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest import mock

from test_contract import c

SPEC = importlib.util.spec_from_file_location('dictation_client_binding', Path(__file__).with_name('guest_check.py'))
guest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guest)
BASE = '000578344de56030689a57cc8d84812c13b41558'
REPO = Path(__file__).resolve().parents[2]

def client(identity=30, pid=41, uid=1000):
    return {'id': identity, 'type': 'PipeWire:Interface:Client', 'info': {
        'props': {'pipewire.protocol': 'protocol-native', 'pipewire.sec.pid': pid, 'pipewire.sec.uid': uid}}}

def node(identity=81, owner=30, media='Stream/Input/Audio', **extra):
    return {'id': identity, 'type': 'PipeWire:Interface:Node', 'info': {
        'props': {'client.id': owner, 'media.class': media, **extra}}}

def graph():
    return [client(), node(), node(77, 20, 'Audio/Source'),
            {'id': 82, 'type': 'PipeWire:Interface:Link', 'info': {
                'output-node-id': 77, 'input-node-id': 81}}]

class HostileString(str):
    def __eq__(self, other): raise AssertionError('private-value-touched')
    def __str__(self): raise AssertionError('private-value-touched')
    def __hash__(self): raise AssertionError('private-value-touched')

class HostileDict(dict):
    def get(self, *args): raise AssertionError('private-getter-touched')

class CaptureClientBindingControls(unittest.TestCase):
    def binding(self, objects):
        return guest.authenticated_capture_nodes(objects, 41, 1000)

    def checker(self, objects=None):
        value = guest.Checker.__new__(guest.Checker)
        value.account = SimpleNamespace(pw_uid=1000)
        value.source = 77
        value.engines = mock.Mock(return_value=[(41, 123, Path('/synthetic-owned-engine'))])
        value.cmd = mock.Mock(return_value=SimpleNamespace(stdout=json.dumps(graph() if objects is None else objects).encode()))
        return value

    def test_authenticated_client_binds_alsa_node_without_app_pid(self):
        self.assertNotIn('application.process.id', graph()[1]['info']['props'])
        self.assertEqual(self.binding(graph()), ({81}, {81}))
        checker = self.checker()
        self.assertIs(checker.capture_link(), True)
        self.assertEqual(checker._wait_last_graph, (True, True, True, True, True))
        self.assertEqual(checker._capture_engine,
                         (41, 123, Path('/synthetic-owned-engine')))
        self.assertEqual(checker.engines.call_count, 2)
        checker.cmd.assert_called_once_with(['/usr/bin/pw-dump'])

    def test_canonical_property_ints_and_decimal_strings(self):
        for pid in (41, '41'):
            for uid in (1000, '1000'):
                for owner in (30, '30'):
                    with self.subTest(pid=pid, uid=uid, owner=owner):
                        self.assertEqual(self.binding([client(pid=pid, uid=uid), node(owner=owner)]), ({81}, {81}))

    def test_app_pid_alone_cannot_authenticate_a_node(self):
        for pid in (41, '41'):
            value = node(**{'application.process.id': pid})
            self.assertEqual(self.binding([value]), (set(), set()))
            self.assertEqual(self.binding([client(pid=99), value]), (set(), set()))
            self.assertEqual(self.binding([client(uid=1001), value]), (set(), set()))

    def test_missing_wrong_and_ambiguous_peer_credentials_fail_closed(self):
        for key in ('pipewire.sec.pid', 'pipewire.sec.uid'):
            value = client(); del value['info']['props'][key]
            self.assertEqual(self.binding([value, node()]), (set(), set()))
        for value in (client(pid=99), client(uid=999), client(pid=0), client(uid=0)):
            self.assertEqual(self.binding([value, node()]), (set(), set()))
        self.assertEqual(self.binding([client(), client(31), node()]), (set(), set()))
        self.assertEqual(self.binding([client(), client(31, pid=99), node()]), ({81}, {81}))

    def test_forged_application_credentials_never_replace_security_keys(self):
        value = client(pid=99, uid=999)
        value['info']['props'].update({'application.process.id': 41, 'application.process.user': 1000})
        self.assertEqual(self.binding([value, node(**{'application.process.id': 41})]), (set(), set()))

    def test_only_authenticated_native_protocol_credentials_are_accepted(self):
        for protocol in (None, '', 'protocol-pulse', True, HostileString('protocol-native')):
            value = client(); value['info']['props']['pipewire.protocol'] = protocol
            self.assertEqual(self.binding([value, node()]), (set(), set()))
        value = client(); del value['info']['props']['pipewire.protocol']
        self.assertEqual(self.binding([value, node()]), (set(), set()))

    def test_node_requires_server_client_binding_and_capture_class(self):
        for owner in (31, None, True, '030', '30.0', -1):
            self.assertEqual(self.binding([client(), node(owner=owner)]), (set(), set()))
        for media in ('Stream/Output/Audio', 'Audio/Source', None, 1, HostileString('Stream/Input/Audio')):
            self.assertEqual(self.binding([client(), node(media=media)]), ({81}, set()))
        for pid in (41, '41'):
            self.assertEqual(self.binding([client(), node(**{'application.process.id': pid})]), ({81}, {81}))
        for pid in (99, None, True, '041', HostileString('41')):
            self.assertEqual(self.binding([client(), node(**{'application.process.id': pid})]), (set(), set()))

    def test_global_object_identity_is_unique_and_not_coerced(self):
        for bad in (True, '81', -1, 2**32, 81.0, None):
            value = node(); value['id'] = bad
            self.assertEqual(self.binding([client(), value]), (set(), set()))
        self.assertEqual(self.binding([client(), node(), node()]), (set(), set()))
        self.assertEqual(self.binding([client(), node(), {'id': 81, 'type': 'PipeWire:Interface:Link'}]), (set(), set()))
        self.assertEqual(self.binding([{'id': 0, 'type': 'PipeWire:Interface:Core'}, client(), node()]), ({81}, {81}))

    def test_numeric_security_values_reject_noncanonical_types_and_bounds(self):
        for bad in (True, False, 41.0, None, -1, 2**32, '041', '+41', '41 ', '4.1e1', '4294967296', '9'*100, HostileString('41')):
            for key in ('pipewire.sec.pid', 'pipewire.sec.uid'):
                value = client(); value['info']['props'][key] = bad
                with self.subTest(key=key, value_type=type(bad).__name__):
                    self.assertEqual(self.binding([value, node()]), (set(), set()))
        for pid, uid in ((True, 1000), (41, True), ('41', 1000), (41, '1000'), (0, 1000), (41, 0)):
            self.assertEqual(guest.authenticated_capture_nodes(graph(), pid, uid), (set(), set()))

    def test_hostile_objects_mappings_and_unknown_metadata_are_not_formatted(self):
        class HostileList(list):
            def __iter__(self): raise AssertionError('private-getter-touched')
        for value in (None, {}, HostileList(graph()), HostileString('private')):
            self.assertEqual(self.binding(value), (set(), set()))
        for value in (HostileDict(node()), {'id': 90, 'type': HostileString('PipeWire:Interface:Node')},
                      {'id': 90, 'type': 'PipeWire:Interface:Node', 'info': HostileDict()},
                      {'id': 90, 'type': 'PipeWire:Interface:Node', 'info': {'props': HostileDict()}}):
            self.assertEqual(self.binding([client(), value]), (set(), set()))
        value = node(); value['info']['props']['unrelated.private'] = HostileString('private')
        self.assertEqual(self.binding([client(), value]), ({81}, {81}))
        for location in ('object', 'info', 'props'):
            value = node(); target = value if location == 'object' else value['info'] if location == 'info' else value['info']['props']
            target[1] = 'unknown'
            self.assertEqual(self.binding([client(), value]), (set(), set()))

    def test_exact_source_direction_and_owned_capture_link_remain_required(self):
        for output, input_ in ((78, 81), (81, 77), (77, 99)):
            objects = graph(); objects[-1]['info'].update({'output-node-id': output, 'input-node-id': input_})
            self.assertIs(self.checker(objects).capture_link(), False)
        self.assertIs(self.checker(graph()[:-1]).capture_link(), False)
        objects = graph(); objects[1]['info']['props']['client.id'] = 31
        self.assertIs(self.checker(objects).capture_link(), False)

    def test_engine_identity_uid_and_start_ticks_are_rechecked_after_graph_read(self):
        before = [(41, 123, Path('/synthetic-owned-engine'))]
        for after in ([], [(41, 124, Path('/synthetic-owned-engine'))],
                      [(42, 123, Path('/synthetic-owned-engine'))],
                      [(41, 123, Path('/different-engine'))], before * 2):
            checker = self.checker(); checker.engines.side_effect = [before, after]
            self.assertIs(checker.capture_link(), False)
            self.assertEqual(checker._wait_last_graph[0], False)
            self.assertIsNone(checker._capture_engine)
        for value in ([], before * 2):
            checker = self.checker(); checker.engines.return_value = value
            self.assertIs(checker.capture_link(), False)
            self.assertEqual(checker._wait_last_graph,
                             (False, False, False, False, False))
            self.assertIsNone(checker._capture_engine)
            checker.cmd.assert_not_called()

    def test_observation_retries_transient_engine_snapshot_within_existing_boundary(self):
        before = [(41, 123, Path('/synthetic-owned-engine'))]
        changed = [(41, 124, Path('/synthetic-owned-engine'))]
        checker = self.checker()
        checker.engines.side_effect = [before, changed, before, before]

        def bounded(fn, seconds):
            self.assertEqual(seconds, 10)
            self.assertIs(fn(), False)
            return fn()

        with mock.patch.object(guest, 'wait', side_effect=bounded):
            self.assertIs(checker.observe('capture-link', checker.capture_link, 10), True)
        self.assertEqual(checker.engines.call_count, 4)

    def test_engine_profile_pins_captured_process_without_third_proc_scan(self):
        checker = self.checker()
        checker.profile_id = 'turbo-q5-v3'
        checker.names = {'avx2': 'synthetic-owned-engine'}
        checker.assets = {'avx2': {'sha256': 'a' * 64}}
        self.assertIs(checker.capture_link(), True)
        with mock.patch.object(guest, 'PAYLOAD', Path('/')), \
                mock.patch.object(guest, 'sha', return_value='a' * 64):
            self.assertEqual(checker.checked_engine_profile(), 'avx2')
        self.assertEqual(checker.engines.call_count, 2)

    def test_engine_profile_substages_distinguish_profile_count_path_and_sha(self):
        checker = self.checker()
        checker.profile_id = 'private-profile'
        checker.names = {}; checker.assets = {}
        cases = []
        try:
            checker.checked_engine_profile()
        except guest.TranscriptionStageFailure as error:
            cases.append(error.failure_substage)
        checker.profile_id = 'turbo-q5-v3'
        checker.names = {'avx2': 'voxtype-avx2'}
        checker.assets = {'avx2': {'sha256': 'a' * 64}}
        for engine, digest in ((None, 'a' * 64),
                               ((41, 123, Path('/wrong')), 'a' * 64),
                               ((41, 123, guest.PAYLOAD / 'voxtype-avx2'), 'b' * 64)):
            checker._capture_engine = engine
            try:
                with mock.patch.object(guest, 'sha', return_value=digest):
                    checker.checked_engine_profile()
            except guest.TranscriptionStageFailure as error:
                cases.append(error.failure_substage)
        self.assertEqual(cases, [701, 702, 703, 704])

if __name__ == '__main__':
    unittest.main()
