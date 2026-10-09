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

    def test_independent_transition_timestamp_is_inside_observation_bracket(self):
        state = Path(self.directory.name)/'mapped.json'
        transition = {}
        state_lock = threading.Lock()
        stopped = threading.Event()

        def current():
            with state_lock:
                return {'9': dict(id=9, appid='kitty', title='fixture')} if transition else {}

        def publish():
            # Model the compositor's authoritative state transition independently
            # of observer queries. Sampling a timestamp before write_text exposes
            # a gap where a later query correctly sees the window still absent.
            while not stopped.wait(.00025):
                if state.exists():
                    with state_lock:
                        transition['mapped_ns'] = time.monotonic_ns()
                    return

        publisher = threading.Thread(target=publish, daemon=True)
        publisher.start()

        def stop_publisher():
            stopped.set()
            publisher.join(timeout=2)
            self.assertFalse(publisher.is_alive())

        self.addCleanup(stop_publisher)

        fixture, prefix = self.server(lambda: json.dumps(dict(clients=list(current().values()))).encode()+b'\n')
        program = ('import pathlib,time; time.sleep(.04); '
                   f'path=pathlib.Path({str(state)!r}); '
                   'path.write_text("ready"); '
                   'time.sleep(10)')
        bounds = []
        with patch.object(guest, 'clients', side_effect=lambda _: current()), \
                patch.object(guest, 'emit'), patch.object(guest, 'snapshot', return_value={}), \
                patch.object(guest.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)):
            measured = guest.startup(prefix, [sys.executable, '-c', program], 'kitty',
                                     timeout=3, hold_seconds=.02, observations=bounds)
        self.assertEqual(len(bounds), 1)
        observation = bounds[0]
        mapped_seconds = (transition['mapped_ns']-observation['launch_started_monotonic_ns'])/1e9
        self.assertLessEqual(observation['lower_seconds'], mapped_seconds)
        self.assertGreaterEqual(observation['upper_seconds'], mapped_seconds)
        self.assertEqual(measured, observation['upper_seconds'])
        self.assertEqual(observation['observer'], guest.MAPPING_OBSERVER)
        self.assertGreater(len(observation['query_roundtrips']), 2)
        self.assertTrue(all(command == b'get all-clients\n' for command in fixture.commands))

    def test_initial_cli_native_disagreement_does_not_launch_app(self):
        _, prefix = self.server(lambda: b'{"clients":[{"id":99}]}\n')
        sentinel = Path(self.directory.name)/'unexpected-launch'
        with patch.object(guest, 'clients', return_value={}):
            with self.assertRaisesRegex(RuntimeError, 'initial client identities differ'):
                guest.startup(prefix, [sys.executable, '-c', f'open({str(sentinel)!r},"w").close()'], 'kitty')
        self.assertFalse(sentinel.exists())

    def test_parent_delay_does_not_inflate_worker_mapping_timestamp(self):
        transition = {}
        def response():
            clients = [dict(id=42, appid='foot')] if transition else []
            return json.dumps(dict(clients=clients)).encode()+b'\n'
        _, prefix = self.server(response)
        with guest.NativeClientQuery(prefix) as observer:
            observer.query()  # Worker startup is outside the measurement.
            started = time.monotonic_ns()
            observer.begin_observation(set(), ('foot',), started, 2, .00005)
            time.sleep(.02)
            transition['mapped_ns'] = time.monotonic_ns()
            # Deliberately postpone the parent read after the mapping event.
            time.sleep(.15)
            result = observer.finish_observation(None, started, 2)
            self.assertLessEqual(result['lower_ns'], transition['mapped_ns'])
            self.assertGreaterEqual(result['upper_ns'], transition['mapped_ns'])
            self.assertLess(result['upper_ns']-transition['mapped_ns'], 100_000_000)
            self.assertGreater(time.monotonic_ns()-result['upper_ns'], 100_000_000)
            self.assertEqual(result['windows'][0]['id'], 42)

    def test_timeout_is_explicit_and_cancellation_reaps_autonomous_worker(self):
        _, prefix = self.server(lambda: b'{"clients":[]}\n')
        with guest.NativeClientQuery(prefix) as observer:
            started = time.monotonic_ns()
            observer.begin_observation(set(), 'foot', started, .02, .00005)
            self.assertIsNone(observer.finish_observation(None, started, .02))
            # A completed timeout permits subsequent queries on the same worker.
            self.assertEqual(observer.query(), {})
            observer.begin_observation(set(), 'foot', time.monotonic_ns(), 300, .00005)
            process = observer.process
        self.assertIsNotNone(process.poll())

    def test_existing_and_unrelated_windows_do_not_satisfy_mapping(self):
        state = [dict(id=1, appid='foot'), dict(id=2, appid='unrelated', title='foot')]
        _, prefix = self.server(lambda: json.dumps(dict(clients=state)).encode()+b'\n')
        with guest.NativeClientQuery(prefix) as observer:
            observer.query()
            started = time.monotonic_ns()
            observer.begin_observation({'1'}, ('foot',), started, 2, .00005)
            time.sleep(.02)
            state.append(dict(id=3, appid='foot'))
            result = observer.finish_observation(None, started, 2)
            self.assertEqual([c['id'] for c in result['windows']], [3])

    def test_mapping_reply_does_not_duplicate_large_client_payload(self):
        title = 'x' * 3_500_000
        _, prefix = self.server(lambda: json.dumps(dict(clients=[dict(
            id=7, appid='foot', title=title)])).encode()+b'\n')
        with guest.NativeClientQuery(prefix) as observer:
            self.assertEqual(observer.query()['7']['title'], title)
            started = time.monotonic_ns()
            observer.begin_observation(set(), ('foot',), started, 2, .00005)
            result = observer.finish_observation(None, started, 2)
            self.assertEqual(result['windows'], [dict(id=7)])
            self.assertLess(len(json.dumps(result)), 2000)
            # Persistence still retrieves actual app/title metadata on demand.
            self.assertEqual(observer.query()['7']['title'], title)

    def test_combined_encoded_reply_budget_fails_before_worker_pipe_write(self):
        # A valid <4MiB raw JSON reply expands when Python renders 1e10 as a
        # decimal float. Exercise the total encoded envelope independently of
        # the Mango byte/count limits, without overriding a production ceiling.
        response = b'{"clients":[{"id":1,"values":[' + b'1e10,'*330_000 + b'1e10]}]}'
        self.assertLess(len(response), 4*1024*1024)
        _, prefix = self.server(lambda: response)
        with guest.NativeClientQuery(prefix) as observer:
            started = time.monotonic()
            with self.assertRaisesRegex(RuntimeError, 'Combined native observer reply exceeds transport budget'):
                observer.query()
            self.assertLess(time.monotonic()-started, 3)
            process = observer.process
        self.assertIsNotNone(process.poll())

    def test_cancellation_reaps_worker_blocked_writing_bounded_large_reply(self):
        _, prefix = self.server(lambda: json.dumps(dict(clients=[dict(
            id=7, appid='foot', title='x'*3_500_000)])).encode()+b'\n')
        started = time.monotonic()
        with guest.NativeClientQuery(prefix) as observer:
            observer._send(dict(kind='get'))
            # The parent intentionally does not drain the large reply.
            time.sleep(.25)
            self.assertIsNone(observer.process.poll())
            process = observer.process
        self.assertLess(time.monotonic()-started, 2)
        self.assertIsNotNone(process.poll())

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
