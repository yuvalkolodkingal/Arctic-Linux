"""Independent Unix-socket fixture checks actual worker transport and timing bounds."""
import importlib.util
import json
import os
import pwd
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'performance_guest', Path(__file__).parents[1]/'performance/guest.py')
guest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guest)
controller_spec = importlib.util.spec_from_file_location(
    'performance_controller', Path(__file__).parents[1]/'performance/run-paired.py')
controller = importlib.util.module_from_spec(controller_spec)
controller_spec.loader.exec_module(controller)


class MangoFixture:
    """A test server implements the pinned get protocol, not the observer code."""
    def __init__(self, directory, response):
        self.path = str(Path(directory)/'mango.sock')
        self.response = response
        self.commands = []
        self.stopped = threading.Event()
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.path)
        self.server.listen()
        self.server.settimeout(.1)
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        while not self.stopped.is_set():
            try:
                peer, _ = self.server.accept()
            except socket.timeout:
                continue
            with peer:
                command = b''
                while not command.endswith(b'\n'):
                    chunk = peer.recv(4096)
                    if not chunk:
                        break
                    command += chunk
                self.commands.append(command)
                response = self.response()
                if response is None:
                    self.stopped.wait(3)
                else:
                    try:
                        for offset in range(0, len(response), 257):
                            peer.sendall(response[offset:offset+257])
                    except (BrokenPipeError, ConnectionResetError):
                        pass

    def close(self):
        self.stopped.set()
        self.thread.join(timeout=4)
        self.server.close()
        if self.thread.is_alive():
            raise RuntimeError('Fixture did not stop')


class NativeObserverTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def server(self, response):
        fixture = MangoFixture(self.directory.name, response)
        self.addCleanup(fixture.close)
        return fixture, ['env', 'MANGO_INSTANCE_SIGNATURE='+fixture.path]

    def test_fragmented_transport_repeated_queries_same_worker_and_uid(self):
        title = 'x' * 90_000
        fixture, prefix = self.server(lambda: json.dumps(
            dict(clients=[dict(id=7, appid='kitty', title=title)])).encode()+b'\n')
        with guest.NativeClientQuery(prefix) as observer:
            pid = observer.process.pid
            for _ in range(3):
                self.assertEqual(observer.query()['7']['title'], title)
                self.assertEqual(observer.process.pid, pid)
                self.assertEqual(observer.roundtrips[-1]['uid'], os.getuid())
                self.assertGreater(observer.roundtrips[-1]['parent_seconds'], 0)
                self.assertGreater(observer.roundtrips[-1]['socket_seconds'], 0)
            process = observer.process
        self.assertIsNotNone(process.poll())
        self.assertEqual(fixture.commands, [b'get all-clients\n'] * 3)

    def test_malformed_and_disconnected_streams_fail_without_cli_fallback(self):
        for response in (b'', b'{', b'{"error":"permission denied"}',
                         b'{"clients":{}}', b'{"clients":[{"appid":"kitty"}]}',
                         b'{"clients":[{"id":1},{"id":1}]}'):
            with self.subTest(response=response), tempfile.TemporaryDirectory() as tmp:
                fixture = MangoFixture(tmp, lambda: response)
                try:
                    with guest.NativeClientQuery(['env', 'MANGO_INSTANCE_SIGNATURE='+fixture.path]) as observer:
                        with patch.object(guest, 'run', side_effect=AssertionError('CLI fallback forbidden')):
                            with self.assertRaises((RuntimeError, ValueError, KeyError)):
                                observer.query()
                        process = observer.process
                    self.assertIsNotNone(process.poll())
                finally:
                    fixture.close()

    def test_absent_socket_fails_without_creating_or_changing_it(self):
        path = str(Path(self.directory.name)/'absent.sock')
        with guest.NativeClientQuery(['env', 'MANGO_INSTANCE_SIGNATURE='+path]) as observer:
            with self.assertRaisesRegex(RuntimeError, 'disconnected'):
                observer.query()
        self.assertFalse(Path(path).exists())

    def test_observer_uid_mismatch_is_rejected(self):
        _, prefix = self.server(lambda: b'{"clients":[]}\n')
        other = 'nobody' if os.getuid() == 0 else 'root'
        with guest.NativeClientQuery(prefix) as observer:
            # The real process started with our own uid; exercise the production
            # identity check without changing any host account or permission.
            observer.prefix = ['runuser', '-u', other]
            self.assertNotEqual(os.getuid(), pwd.getpwnam(other).pw_uid)
            with self.assertRaisesRegex(RuntimeError, 'desktop user'):
                observer.query()

    def test_socket_timeout_and_unbounded_response_are_terminal(self):
        for response in (None, b'x' * (4 * 1024 * 1024 + 1)):
            with self.subTest(size=None if response is None else len(response)), tempfile.TemporaryDirectory() as tmp:
                fixture = MangoFixture(tmp, lambda: response)
                try:
                    with guest.NativeClientQuery(['env', 'MANGO_INSTANCE_SIGNATURE='+fixture.path]) as observer:
                        started = time.monotonic()
                        with self.assertRaisesRegex(RuntimeError, 'disconnected'):
                            observer.query()
                        self.assertLess(time.monotonic()-started, 3.2)
                finally:
                    fixture.close()

    def assert_publication_bounds_overlap(self, observation, publication):
        # Atomic rename has a visibility instant between these independent
        # child clocks. Neither clock is claimed to be that exact instant.
        before, after = publication['before_ns'], publication['after_ns']
        self.assertIs(type(before), int)
        self.assertIs(type(after), int)
        self.assertGreater(before, 0)
        self.assertGreaterEqual(after, before)
        start = observation['launch_started_monotonic_ns']
        self.assertGreaterEqual(before, start)
        self.assertLessEqual(observation['lower_seconds'], observation['upper_seconds'])
        self.assertLessEqual(observation['lower_seconds'], (after-start)/1e9)
        self.assertGreaterEqual(observation['upper_seconds'], (before-start)/1e9)

    def publication_program(self, state, clock, before_signal, release, delayed):
        # Prepare privately, publish atomically, then record the enclosing
        # clocks. The fixture never parses a concurrently partial state file.
        program = """import json, os, pathlib, sys, time
state, clock, signal, release = map(pathlib.Path, sys.argv[1:5])
pending = state.with_suffix('.pending')
pending.write_text('mapped')
before = time.monotonic_ns()
if sys.argv[5] == 'delayed':
    signal.write_text('ready')
    deadline = time.monotonic() + 2
    while not release.exists():
        if time.monotonic() >= deadline:
            raise RuntimeError('Fixture publication release missing')
        time.sleep(.0005)
os.replace(pending, state)
after = time.monotonic_ns()
clock.write_text(json.dumps(dict(before_ns=before, after_ns=after)))
"""
        return [sys.executable, '-c', program, str(state), str(clock),
                str(before_signal), str(release), 'delayed' if delayed else 'normal']

    def observe_publication(self, delayed):
        state = Path(self.directory.name)/'mapped.marker'
        clock = Path(self.directory.name)/'publication.json'
        before_signal = Path(self.directory.name)/'before-publication'
        release = Path(self.directory.name)/'release-publication'
        delayed_negative_snapshots = []

        def current():
            if not state.exists():
                if delayed and before_signal.exists():
                    delayed_negative_snapshots.append(time.monotonic_ns())
                    # The first negative response proves the next query send
                    # is after the child's before clock. Release only at the
                    # second still-negative snapshot, without a sleep guess.
                    if len(delayed_negative_snapshots) == 2:
                        release.write_text('publish')
                return {}
            return {'9': dict(id=9, appid='kitty', title='fixture')}

        fixture, prefix = self.server(lambda: json.dumps(dict(clients=list(current().values()))).encode()+b'\n')
        bounds = []
        with patch.object(guest, 'clients', side_effect=lambda _: current()), \
                patch.object(guest, 'emit'), patch.object(guest, 'snapshot', return_value={}), \
                patch.object(guest.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)):
            measured = guest.startup(prefix, self.publication_program(
                state, clock, before_signal, release, delayed), 'kitty',
                timeout=3, hold_seconds=.02, observations=bounds)
        self.assertEqual(len(bounds), 1)
        observation = bounds[0]
        publication = json.loads(clock.read_text())
        self.assert_publication_bounds_overlap(observation, publication)
        self.assertEqual(measured, observation['upper_seconds'])
        self.assertEqual(observation['observer'], guest.MAPPING_OBSERVER)
        self.assertGreater(len(observation['query_roundtrips']), 2)
        self.assertTrue(all(command == b'get all-clients\n' for command in fixture.commands))
        return observation, publication, delayed_negative_snapshots

    def test_independent_publication_interval_overlaps_observation_bracket(self):
        self.observe_publication(delayed=False)

    def test_negative_snapshot_after_before_clock_does_not_make_it_a_map_instant(self):
        observation, publication, negatives = self.observe_publication(delayed=True)
        self.assertGreaterEqual(len(negatives), 2)
        self.assertLess(publication['before_ns'], negatives[0])
        self.assertLess(negatives[1], publication['after_ns'])
        before_seconds = (publication['before_ns']-observation['launch_started_monotonic_ns'])/1e9
        # Deliberately reproduce why the original point oracle is invalid:
        # a correct last-negative lower bound can follow the before clock.
        self.assertGreater(observation['lower_seconds'], before_seconds)
        self.assert_publication_bounds_overlap(observation, publication)

    def test_publication_interval_oracle_rejects_disjoint_and_reversed_bounds(self):
        start = 1_000_000_000
        publication = dict(before_ns=start+10_000_000, after_ns=start+30_000_000)
        # A before timestamp outside the bracket is allowed only while the
        # independently bounded publication interval still overlaps it.
        self.assert_publication_bounds_overlap(dict(launch_started_monotonic_ns=start,
            lower_seconds=.02, upper_seconds=.04), publication)
        for lower, upper in ((.04,.05), (.001,.005), (.04,.02)):
            with self.subTest(lower=lower, upper=upper), self.assertRaises(AssertionError):
                self.assert_publication_bounds_overlap(dict(launch_started_monotonic_ns=start,
                    lower_seconds=lower, upper_seconds=upper), publication)
        for before, after in ((start+30_000_000,start+10_000_000), (True,start+30_000_000),
                              (start+10_000_000,False), (-1,start+30_000_000)):
            with self.subTest(before=before, after=after), self.assertRaises(AssertionError):
                self.assert_publication_bounds_overlap(dict(launch_started_monotonic_ns=start,
                    lower_seconds=.02, upper_seconds=.04), dict(before_ns=before, after_ns=after))

    def test_initial_cli_native_disagreement_does_not_launch_app(self):
        _, prefix = self.server(lambda: b'{"clients":[{"id":99}]}\n')
        sentinel = Path(self.directory.name)/'unexpected-launch'
        with patch.object(guest, 'clients', return_value={}):
            with self.assertRaisesRegex(RuntimeError, 'initial client identities differ'):
                guest.startup(prefix, [sys.executable, '-c', f'open({str(sentinel)!r},"w").close()'], 'kitty')
        self.assertFalse(sentinel.exists())

    def test_cleanup_failure_propagates_and_reaps_only_started_processes(self):
        _, prefix = self.server(lambda: b'{"clients":[]}\n')
        original_popen = subprocess.Popen
        started_processes = []

        def record(*args, **kwargs):
            process = original_popen(*args, **kwargs)
            started_processes.append(process)
            return process

        with patch.object(guest.subprocess, 'Popen', side_effect=record), \
                patch.object(guest, 'clients', side_effect=[{}, RuntimeError('diagnostic IPC failed'),
                                                          RuntimeError('cleanup IPC failed')]), \
                patch.object(guest, 'emit'):
            with self.assertRaisesRegex(RuntimeError, 'cleanup IPC failed'):
                guest.startup(prefix, [sys.executable, '-c', 'import time; time.sleep(30)'], 'kitty', timeout=.02)
        self.assertEqual(len(started_processes), 2)
        self.assertTrue(all(process.poll() is not None for process in started_processes))

    def test_inventory_is_sorted_and_graphics_are_visible_without_file_scan(self):
        text = 'zlib-0:1.3.1-4.fc44.x86_64\nmesa-libEGL-0:26.2.1-1.fc44.x86_64\nkitty-0:0.47.1-1.fc44.x86_64'
        with patch.object(guest, 'run', return_value=text) as run:
            result = guest.rpm_inventory()
        self.assertEqual(result['nevra'], sorted(text.splitlines()))
        self.assertEqual(len(result['graphics_text_and_apps']), 2)
        self.assertEqual(run.call_args.args[0][:2], ['rpm', '-qa'])
        self.assertEqual(len(result['sha256']), 64)

    def test_counterbalanced_order_has_exact_three_unique_boots_each(self):
        actual = controller.paired_boot_order()
        self.assertEqual(actual, [(1, 'baseline'), (1, 'candidate'), (2, 'candidate'),
                                  (2, 'baseline'), (3, 'baseline'), (3, 'candidate')])
        self.assertEqual(len(set(actual)), 6)
        self.assertEqual([sum(name == image for _, name in actual) for image in ('baseline', 'candidate')], [3, 3])

    def test_cpu_counter_reset_frozen_and_impossible_idle_fail_instead_of_becoming_zero(self):
        result = guest.cpu_interval(100, 80, 300, 277)
        self.assertEqual(result['cpu_ticks_delta'], 200)
        self.assertEqual(result['cpu_idle_ticks_delta'], 197)
        self.assertEqual(result['cpu_busy_percent'], 1.5)
        self.assertEqual(result['cpu_resolution_percent'], .5)
        for counters in ((100, 80, 100, 80), (100, 80, 90, 70), (100, 80, 200, 79), (100, 80, 200, 181)):
            with self.subTest(counters=counters), self.assertRaisesRegex(RuntimeError, 'Invalid /proc/stat'):
                guest.cpu_interval(*counters)


if __name__ == '__main__':
    unittest.main()
