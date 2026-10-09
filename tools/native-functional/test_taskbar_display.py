"""Identity, topology, timeout and interrupted-resource controls."""
import importlib.util
import json
from pathlib import Path
import signal
import socket
import struct
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('taskbar_display', Path(__file__).with_name('taskbar-display.py'))
display = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(display)


class Fixture(display.TaskbarDisplay):
    def __init__(self):
        self.proof = self.deadline = None
        self.bus = types.SimpleNamespace(pid=27)
        self.address = 'unix:path=/tmp/private-fixture/bus'
        self.calls = []; self.owner_pid = 456; self.owner_uid = 0
        self.owner_reads = 0; self.owner_changes_at = None
        self.consoles = {3: ('Graphic', 1, 'pci/0000/02.0'), 1: ('Text', 0, 'serial/0'),
                         2: ('Graphic', 0, 'pci/0000/02.0')}
        self.set_failure = False
        self.running = False
        self.gpu_type = 'child<virtio-vga>'
        self.max_outputs = 2
    def _private_root(self): pass
    def _query(self, vm, command, arguments=None):
        if command == 'query-status': return {'running': self.running, 'status': 'prelaunch'}
        if command == 'qom-list': return [{'name': display.GPU_ID, 'type': self.gpu_type}]
        if command == 'qom-get': return self.max_outputs
        if command == 'query-pci': return [{'bus': 0, 'devices': [{'bus': 0, 'slot': 2, 'function': 0, 'qdev_id': display.GPU_ID}]}]
        raise AssertionError(command)
    def _call(self, path, method, *arguments, destination='org.qemu'):
        self.calls.append((path, method, arguments, destination))
        if method.endswith('GetNameOwner'):
            self.owner_reads += 1
            changed = self.owner_changes_at is not None and self.owner_reads >= self.owner_changes_at
            return "(':1.9',)" if changed else "(':1.4',)"
        if method.endswith('GetConnectionUnixProcessID'): return '(uint32 ' + str(self.owner_pid) + ',)'
        if method.endswith('GetConnectionUnixUser'): return '(uint32 ' + str(self.owner_uid) + ',)'
        if arguments[-1:] == ('ConsoleIDs',):
            return '(<[uint32 ' + ', '.join(str(value) for value in self.consoles) + ']>,)'
        if method.endswith('SetUIInfo'):
            if self.set_failure: raise display.DisplayError('unsupported SetUIInfo')
            return '()\n'
        row = self.consoles[int(path.rsplit('_', 1)[1])]
        return {'Type': "(<'" + row[0] + "'>,)", 'Head': '(<uint32 ' + str(row[1]) + '>,)',
                'DeviceAddress': "(<'" + row[2] + "'>,)"}[arguments[-1]]


def vm():
    return types.SimpleNamespace(proc=types.SimpleNamespace(pid=456, poll=lambda: None), qmp_path='/tmp/owned-qmp',
                                 cmd=lambda *args: (_ for _ in ()).throw(AssertionError('frozen VM.cmd must not be called')))


class Child:
    pid = 27
    def __init__(self, interrupt=False, failure=False):
        self.alive = True; self.killed = False; self.interrupt = interrupt; self.failure = failure
    def poll(self): return None if self.alive else 0
    def terminate(self):
        if self.failure: raise OSError('terminate failed')
    def wait(self, timeout):
        if self.interrupt:
            self.interrupt = False
            raise KeyboardInterrupt('owned process interrupted')
        if self.alive: raise subprocess.TimeoutExpired('owned daemon', timeout)
    def kill(self): self.killed = True; self.alive = False


class Controls(unittest.TestCase):
    def enable(self, fixture):
        with patch.object(display.os, 'geteuid', return_value=0), \
             patch.object(display.subprocess, 'run', return_value=types.SimpleNamespace(returncode=0)):
            return fixture.enable(vm())

    def test_discovered_heads_bind_exact_process_gpu_and_unique_bus_owner(self):
        fixture = Fixture(); proof = self.enable(fixture)
        self.assertEqual([row['console_id'] for row in proof['heads']], [2, 3])
        self.assertEqual([row['xoff'] for row in proof['heads']], [0, 1280])
        self.assertTrue(proof['guest_monitor_verification_required'])
        self.assertEqual(proof['qemu_pid'], 456)
        self.assertEqual(proof['gpu_id'], display.GPU_ID)
        calls = [row for row in fixture.calls if row[1].endswith('SetUIInfo')]
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(row[-1] == ':1.4' for row in calls))
        self.assertEqual(calls[1][2], ('uint16 340', 'uint16 190', 'int32 1280', 'int32 0', 'uint32 1280', 'uint32 720'))
        with self.assertRaises(display.DisplayError): self.enable(fixture)

    def test_unowned_pid_uid_and_changed_owner_fail_before_uiinfo(self):
        for field, value in (('owner_pid', 457), ('owner_uid', 1000), ('owner_changes_at', 2)):
            with self.subTest(field=field):
                fixture = Fixture(); setattr(fixture, field, value)
                with self.assertRaises(display.DisplayError): self.enable(fixture)
                self.assertIsNone(fixture.proof)
                self.assertFalse(any(row[1].endswith('SetUIInfo') for row in fixture.calls))

    def test_running_vm_and_wrong_gpu_type_or_scanouts_fail_before_uiinfo(self):
        for field, value in (('running', True), ('gpu_type', 'child<bochs-display>'), ('max_outputs', 3), ('max_outputs', True)):
            fixture = Fixture(); setattr(fixture, field, value)
            with self.assertRaises(display.DisplayError): self.enable(fixture)
            self.assertEqual(fixture.calls, [])

    def test_wrong_head_count_duplicate_heads_and_different_gpu_fail(self):
        for rows in ({0: ('Graphic', 0, 'pci/0000/02.0')},
                     {0: ('Graphic', 0, 'pci/0000/02.0'), 1: ('Graphic', 0, 'pci/0000/02.0')},
                     {0: ('Graphic', 0, 'pci/0000/02.0'), 1: ('Graphic', 1, 'pci/0000/03.0')},
                     {0: ('Graphic', 0, 'pci/0000/02.0'), 1: ('Graphic', 1, 'pci/0000/02.0'), 2: ('Graphic', 2, 'pci/0000/02.0')}):
            fixture = Fixture(); fixture.consoles = rows
            with self.assertRaises(display.DisplayError): self.enable(fixture)
            self.assertFalse(any(row[1].endswith('SetUIInfo') for row in fixture.calls))

    def test_unsupported_uiinfo_has_no_success_receipt(self):
        fixture = Fixture(); fixture.set_failure = True
        with self.assertRaises(display.DisplayError): self.enable(fixture)
        self.assertIsNone(fixture.proof)

    def test_strict_gvariant_parser_rejects_untyped_escaping_overflow_duplicates(self):
        for text in ('(<0>,)', '(uint32 4294967296,)', '(uint32 -1,)', '(uint32 3,) extra'):
            with self.assertRaises(display.DisplayError): display.uint32_reply(text)
        for text in ('(<[0, 1]>,)', '(<[uint32 0, 0]>,)', '(<[uint32 0, 4294967296]>,)', '(<[uint32 0, 1]>,)\nextra'):
            with self.assertRaises(display.DisplayError): display.console_ids_reply(text)
        for text in ("('a\\n',)", "('a',) extra", "(<\"Graphic\">,)"):
            with self.assertRaises(display.DisplayError): display.string_reply(text)

    def test_qmp_stall_is_bounded_without_frozen_vm_cmd_and_restores_timeout(self):
        class Connection:
            def __init__(self): self.timeouts = []; self.timeout = 9
            def gettimeout(self): return self.timeout
            def settimeout(self, value): self.timeouts.append(value); self.timeout = value
            def getsockopt(self, *args): return struct.pack('3i', 456, 0, 0)
        class File:
            def write(self, data): pass
            def flush(self): pass
            def readline(self, limit): raise socket.timeout('stalled peer')
        machine = vm(); machine.s = Connection(); machine.f = File()
        old_handler = signal.getsignal(signal.SIGALRM)
        with patch.object(display.Path, 'lstat', return_value=types.SimpleNamespace(st_mode=0o140600, st_uid=0)):
            with self.assertRaises(socket.timeout): display.qmp_query(machine, 'query-status', seconds=.05)
        self.assertTrue(all(0 < value <= .05 for value in machine.s.timeouts[:-1]))
        self.assertEqual(machine.s.gettimeout(), 9)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
        self.assertEqual(signal.getsignal(signal.SIGALRM), old_handler)

    def test_absolute_alarm_interrupts_a_nonreturning_buffered_read(self):
        class File:
            def write(self, data): pass
            def flush(self): pass
            def readline(self, limit):
                display.time.sleep(.5)
                raise AssertionError('absolute deadline did not interrupt blocked read')
        machine = vm(); machine.f = File()
        machine.s = types.SimpleNamespace(getsockopt=lambda *args: struct.pack('3i', 456, 0, 0),
                                          gettimeout=lambda: None, settimeout=lambda value: None)
        started = display.time.monotonic()
        with patch.object(display.Path, 'lstat', return_value=types.SimpleNamespace(st_mode=0o140600, st_uid=0)):
            with self.assertRaises(display.DisplayError): display.qmp_query(machine, 'query-status', seconds=.02)
        self.assertLess(display.time.monotonic() - started, .25)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_qmp_existing_buffered_events_and_matching_response_are_used(self):
        class File:
            def write(self, text): self.request = json.loads(text); self.reads = 0
            def flush(self): pass
            def readline(self, limit):
                self.reads += 1
                if self.reads == 1: return json.dumps({'event': 'STOP'}) + '\n'
                return json.dumps({'id': self.request['id'], 'return': {'running': False}}) + '\n'
        machine = vm(); machine.f = File()
        machine.s = types.SimpleNamespace(getsockopt=lambda *args: struct.pack('3i', 456, 0, 0),
                                          gettimeout=lambda: None, settimeout=lambda value: None)
        with patch.object(display.Path, 'lstat', return_value=types.SimpleNamespace(st_mode=0o140600, st_uid=0)):
            self.assertEqual(display.qmp_query(machine, 'query-status'), {'running': False})
        self.assertEqual(machine.f.reads, 2)

    def test_qmp_exact_peer_rejects_different_process(self):
        machine = vm(); machine.s = types.SimpleNamespace(getsockopt=lambda *args: struct.pack('3i', 457, 0, 0))
        with patch.object(display.Path, 'lstat', return_value=types.SimpleNamespace(st_mode=0o140600, st_uid=0)):
            with self.assertRaises(display.DisplayError): display.qmp_query(machine, 'query-status')

    def test_cleanup_attempts_every_resource_after_interruption_or_error(self):
        for interrupt, failure in ((True, False), (False, True)):
            with tempfile.TemporaryDirectory() as directory:
                fixture = display.TaskbarDisplay.__new__(display.TaskbarDisplay)
                fixture.root = Path(directory) / 'owned'; fixture.root.mkdir()
                fixture.log = open(fixture.root / 'bus.log', 'w'); fixture.raw_fd = None; fixture.closed = False
                fixture.bus = Child(interrupt=interrupt, failure=failure)
                with self.assertRaises(KeyboardInterrupt if interrupt else display.DisplayError): fixture.close()
                self.assertTrue(fixture.bus.killed)
                self.assertTrue(fixture.log.closed)
                self.assertFalse(fixture.root.exists())
                self.assertTrue(fixture.closed)
                fixture.close()

    def test_interrupt_during_popen_handoff_preserves_ownership_and_cleans(self):
        child = Child()
        roots = []
        original = display.tempfile.mkdtemp
        def created(**kwargs):
            value = original(**kwargs); roots.append(Path(value)); return value
        def started(*args, **kwargs):
            # Parent handler defers, Popen returns and ownership is assigned.
            display.os.kill(display.os.getpid(), signal.SIGINT)
            return child
        with patch.object(display.os, 'geteuid', return_value=0), patch.object(display.shutil, 'which', return_value='/usr/bin/tool'), \
             patch.object(display.tempfile, 'mkdtemp', side_effect=created), patch.object(display.subprocess, 'Popen', side_effect=started):
            with self.assertRaises(KeyboardInterrupt): display.TaskbarDisplay()
        self.assertTrue(child.killed)
        self.assertTrue(roots and all(not value.exists() for value in roots))

    def test_early_directory_setup_failure_cleans_new_owned_directory(self):
        roots = []; original = display.tempfile.mkdtemp
        def created(**kwargs):
            value = original(**kwargs); roots.append(Path(value)); return value
        with patch.object(display.os, 'geteuid', return_value=0), patch.object(display.shutil, 'which', return_value='/usr/bin/tool'), \
             patch.object(display.tempfile, 'mkdtemp', side_effect=created), patch.object(display.os, 'chmod', side_effect=OSError('failure')):
            with self.assertRaises(OSError): display.TaskbarDisplay()
        self.assertTrue(roots and all(not value.exists() for value in roots))


if __name__ == '__main__': unittest.main()
