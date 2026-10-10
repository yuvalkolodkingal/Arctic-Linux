"""Matching-version CLI and synthetic routing controls; no real audio or guests."""
import contextlib
import io
import json
from pathlib import Path
import shlex
import signal
from types import SimpleNamespace
import unittest
from unittest import mock

import test_session_diagnostics as diagnostics

guest = diagnostics.guest

# Complete long_options inventory from official PipeWire 1.6.9 pw-loopback.c,
# lines 99-114; SHA256 05169e172e496b72ee1ac7dce936d130bfbad7e43c82fb45c721190c07c99e54.
# https://github.com/PipeWire/pipewire/blob/1.6.9/src/tools/pw-loopback.c
# True means required_argument. Its default getopt branch exits before connecting.
LOOPBACK_1_6_9_OPTIONS = {
    'help': False, 'version': False, 'remote': True, 'group': True, 'name': True,
    'channels': True, 'channel-map': True, 'latency': True, 'delay': True,
    'capture': True, 'playback': True, 'capture-props': True, 'playback-props': True,
}
HELP = '\n'.join('--' + name for name in LOOPBACK_1_6_9_OPTIONS)


class LoopbackProcess:
    """Only a getopt option fixture, not a PipeWire/server or format emulator."""
    def __init__(self, arguments, dead=False):
        self.pid = 71001
        self.returncode = 255 if dead else None
        self.options = {}
        self.waits = []
        for argument in arguments:
            name, separator, value = argument[2:].partition('=')
            if (not argument.startswith('--') or name not in LOOPBACK_1_6_9_OPTIONS
                    or (LOOPBACK_1_6_9_OPTIONS[name] and (not separator or not value))
                    or (not LOOPBACK_1_6_9_OPTIONS[name] and separator)):
                self.returncode = 255
                break
            self.options[name] = value

    def poll(self):
        return self.returncode

    def wait(self, timeout):
        self.waits.append(timeout)
        self.returncode = 0
        return 0


class RouteFixture:
    def __init__(self, checker=None, old_source=37, dead=False, missing_help=None, graph='unique'):
        self.checker = checker or guest.Checker.__new__(guest.Checker)
        self.checker.prefix = ['synthetic-desktop-prefix']
        self.checker.loop = self.checker.player = self.checker.window = None
        self.checker.source = self.checker.old_source = None
        self.checker.root = Path('/synthetic-owned-dictation-fixture')
        self.old_source = old_source
        self.dead = dead
        self.help = HELP.replace('--' + missing_help, '') if missing_help else HELP
        self.graph = graph
        self.commands = []
        self.spawns = []
        self.process = None

    def spawn(self, argv, **kwargs):
        self.spawns.append((argv, kwargs))
        if argv[:2] != ['synthetic-desktop-prefix', '/usr/bin/pw-loopback']:
            raise AssertionError('unexpected fixture process')
        self.process = LoopbackProcess(argv[2:], dead=self.dead)
        return self.process

    def properties(self, direction):
        return dict(token.split('=', 1) for token in shlex.split(self.process.options[direction + '-props']))

    def command(self, argv, **kwargs):
        self.commands.append((argv, kwargs))
        if argv == ['/usr/bin/pw-loopback', '--help']:
            output = self.help.encode()
        elif argv == ['/usr/bin/wpctl', 'inspect', '@DEFAULT_AUDIO_SOURCE@']:
            output = (f'id {self.old_source}, type PipeWire:Interface:Node' if self.old_source is not None else '').encode()
        elif argv == ['/usr/bin/pw-dump']:
            capture = self.properties('capture')
            playback = self.properties('playback')
            objects = [{'id': 91, 'type': 'PipeWire:Interface:Node', 'info': {'props': capture}},
                       {'id': 92, 'type': 'PipeWire:Interface:Node', 'info': {'props': playback}}]
            if self.graph == 'duplicate':
                objects.append(dict(objects[1], id=93))
            elif self.graph == 'foreign':
                objects[1]['info']['props']['node.name'] = 'ForeignSource'
            output = json.dumps(objects).encode()
        elif argv[:2] in (['/usr/bin/wpctl', 'set-default'], ['/usr/bin/wpctl', 'clear-default']):
            output = b''
        else:
            raise AssertionError('unexpected fixture command')
        return SimpleNamespace(returncode=0, stdout=output, stderr=b'')

    @contextlib.contextmanager
    def installed(self):
        with mock.patch.object(guest.Path, 'is_file', return_value=True), \
                mock.patch.object(self.checker, 'cmd', side_effect=self.command), \
                mock.patch.object(guest.subprocess, 'Popen', side_effect=self.spawn), \
                mock.patch.object(guest.os, 'urandom', return_value=b'12345678'):
            yield self


class LoopbackRouteControls(unittest.TestCase):
    def test_actual_route_uses_supported_mono_stream_properties_and_private_process(self):
        fixture = RouteFixture()
        with fixture.installed():
            fixture.checker.route()
        self.assertIsNone(fixture.process.poll())
        self.assertEqual(fixture.process.options['channels'], '1')
        self.assertEqual(fixture.process.options['channel-map'], '[ MONO ]')
        self.assertNotIn('rate', fixture.process.options)
        capture, playback = fixture.properties('capture'), fixture.properties('playback')
        self.assertEqual(capture['audio.rate'], '16000')
        self.assertEqual(playback['audio.rate'], '16000')
        self.assertEqual(capture['media.class'], 'Audio/Sink')
        self.assertEqual(playback['media.class'], 'Audio/Source')
        self.assertEqual(capture['node.name'], fixture.checker.sink_name)
        self.assertEqual(playback['node.name'], fixture.checker.source_name)
        self.assertNotEqual(capture['node.name'], playback['node.name'])
        self.assertEqual(fixture.checker.source, 92)
        argv, kwargs = fixture.spawns[0]
        self.assertEqual(len(argv), 6)  # each property set and channel map remain one argument
        self.assertEqual(kwargs, {'stdout': guest.subprocess.DEVNULL, 'stderr': guest.subprocess.DEVNULL,
                                  'start_new_session': True})
        self.assertEqual(fixture.commands[-1][0], ['/usr/bin/wpctl', 'set-default', '92'])

    def test_matching_version_option_fixture_rejects_legacy_rate_and_missing_arguments(self):
        for arguments in (['--channels=1', '--rate=16000'], ['--channels'], ['--capture-props=']):
            with self.subTest(arguments=arguments):
                self.assertEqual(LoopbackProcess(arguments).poll(), 255)
        self.assertIsNone(LoopbackProcess(['--channels=1', '--channel-map=[ MONO ]',
                                         '--capture-props=audio.rate=16000', '--playback-props=audio.rate=16000']).poll())

    def test_missing_supported_help_options_fail_before_spawn_or_default_source_change(self):
        for option in ('channels', 'channel-map', 'capture-props', 'playback-props'):
            with self.subTest(option=option):
                fixture = RouteFixture(missing_help=option)
                with fixture.installed(), self.assertRaisesRegex(guest.Invalid, '^loopback-flags-unavailable$'):
                    fixture.checker.route()
                self.assertEqual(fixture.spawns, [])
                self.assertEqual(len(fixture.commands), 1)

    def test_owned_route_cleanup_restores_or_clears_default_and_disconnect_keeps_it_unrestored(self):
        for old_source, restore in ((37, True), (None, True), (37, False)):
            with self.subTest(old_source=old_source, restore=restore):
                fixture = RouteFixture(old_source=old_source)
                with fixture.installed(), mock.patch.object(guest.os, 'killpg') as kill:
                    fixture.checker.route()
                    fixture.checker.destroy_route(restore=restore)
                kill.assert_called_once_with(fixture.process.pid, signal.SIGTERM)
                self.assertEqual(fixture.process.waits, [3])
                self.assertIsNone(fixture.checker.loop)
                self.assertIsNone(fixture.checker.source)
                defaults = [argv for argv, _ in fixture.commands if argv[:2] in
                            (['/usr/bin/wpctl', 'set-default'], ['/usr/bin/wpctl', 'clear-default'])]
                expected = ([['/usr/bin/wpctl', 'set-default', '37']] if old_source is not None
                            else [['/usr/bin/wpctl', 'clear-default', '1']]) if restore else []
                self.assertEqual(defaults, [['/usr/bin/wpctl', 'set-default', '92']] + expected)

    def test_dead_route_keeps_actual_session_failed_unrun_private_and_closes_owned_state(self):
        controls = diagnostics.SessionDiagnosticControls()
        for phase in ('online-installed', 'recovered-offline'):
            for profile in diagnostics.c.PROFILES:
                with self.subTest(phase=phase, profile=profile):
                    checker = controls.checker(phase, profile)
                    checker.route = guest.Checker.route.__get__(checker)
                    fixture = RouteFixture(checker=checker, dead=True)
                    import_spec, module = controls.setup(checker)
                    stdout = io.StringIO()
                    with import_spec, module, fixture.installed(), contextlib.redirect_stdout(stdout):
                        checker.execute()
                    report = controls.failed_report(checker, 'session-virtual-microphone-route-loopback-process-died')
                    self.assertEqual(stdout.getvalue(), '')
                    self.assertEqual(report['samples'], [])
                    checker.window_start.assert_not_called()
                    self.assertNotIn('synthetic-desktop-prefix', json.dumps(report))
                    with fixture.installed(), mock.patch.object(guest.os, 'killpg') as kill, \
                            mock.patch.object(guest.shutil, 'rmtree') as remove:
                        checker.close()
                    kill.assert_not_called()  # already dead; no unrelated process group is targeted
                    remove.assert_called_once_with(checker.root)
                    self.assertIsNone(checker.loop)
                    self.assertIsNone(checker.source)
                    self.assertEqual(fixture.commands[-1][0], ['/usr/bin/wpctl', 'set-default', '37'])

    def test_duplicate_or_foreign_route_nodes_fail_without_changing_default_and_still_clean_up(self):
        for graph in ('duplicate', 'foreign'):
            with self.subTest(graph=graph):
                fixture = RouteFixture(graph=graph)
                def bounded_observation(fn):
                    self.assertIsNone(fn())
                    raise guest.Invalid('observation-timeout')
                with fixture.installed(), mock.patch.object(guest, 'wait', side_effect=bounded_observation), \
                        self.assertRaisesRegex(guest.Invalid, '^observation-timeout$'):
                    fixture.checker.route()
                self.assertFalse(any(argv[:2] == ['/usr/bin/wpctl', 'set-default'] for argv, _ in fixture.commands))
                with fixture.installed(), mock.patch.object(guest.os, 'killpg') as kill:
                    fixture.checker.destroy_route()
                kill.assert_called_once_with(fixture.process.pid, signal.SIGTERM)
                self.assertEqual(fixture.commands[-1][0], ['/usr/bin/wpctl', 'set-default', '37'])


if __name__ == '__main__':
    unittest.main()
