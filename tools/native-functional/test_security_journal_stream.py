"""Bounded journal streaming controls; no journal, guest, or network is used."""
import hashlib
import io
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('streaming_native_smoke', HERE / 'native_smoke.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
REAL_POPEN = subprocess.Popen
PRIVATE = 'password=private; Transcript: private-audio; תמלול: private-hebrew'


class JournalStreamControls(unittest.TestCase):
    def run_stream(self, program, *, timeout=5):
        calls = []
        def launch(argv, **kwargs):
            calls.append((argv, kwargs))
            return REAL_POPEN([sys.executable, '-c', program], **kwargs)
        with patch.object(s.subprocess, 'Popen', side_effect=launch):
            result = s.journal_avc_count('s=fixture;i=1;b=2;m=3;t=4;x=5', timeout=timeout)
        self.assertEqual(len(calls), 1)
        argv, kwargs = calls[0]
        self.assertEqual(argv, ['journalctl', '-b', '--no-pager', '--after-cursor',
            's=fixture;i=1;b=2;m=3;t=4;x=5', '-o', 'json', '--output-fields=MESSAGE', '--all'])
        self.assertNotIn('shell', kwargs)
        self.assertTrue(kwargs['start_new_session'])
        return result

    def assert_private_failure(self, program, *, timeout=5):
        with self.assertRaisesRegex(RuntimeError, '^journal stream validation failed$') as caught:
            self.run_stream(program, timeout=timeout)
        self.assertNotIn(PRIVATE, str(caught.exception))

    def test_streams_more_than_old_aggregate_bound_without_retaining_messages(self):
        count = 100000
        program = "import json,sys\nfor i in range(%d): print(json.dumps({'MESSAGE':'benign-'+'x'*48}))" % count
        result = self.run_stream(program, timeout=20)
        self.assertEqual(result, {'records': count, 'avcs': 0})
        self.assertGreater(count * len(json.dumps({'MESSAGE':'benign-'+'x'*48}) + '\n'), s.LIMIT)

    def test_scans_first_middle_last_and_binary_messages(self):
        messages = ['avc: denied first', 'benign', 'type=USER_AVC middle', 'benign', 'avc: denied last']
        lines = [json.dumps({'MESSAGE': value}) for value in messages]
        lines.append(json.dumps({'MESSAGE': list(b'type=AVC binary')}))
        program = 'import sys\nsys.stdout.write(' + repr('\n'.join(lines) + '\n') + ')'
        self.assertEqual(self.run_stream(program), {'records': 6, 'avcs': 4})

    def test_private_payload_is_never_returned_or_exported(self):
        line = json.dumps({'MESSAGE': PRIVATE})
        program = 'import sys\nsys.stdout.write(' + repr(line + '\n') + ')'
        self.assertEqual(self.run_stream(program), {'records': 1, 'avcs': 0})
        for raw in ('{"MESSAGE":"' + PRIVATE, '{"MESSAGE":"a","MESSAGE":"' + PRIVATE + '"}\n',
                    '{"MESSAGE":NaN,"private":"' + PRIVATE + '"}\n'):
            self.assert_private_failure('import sys\nsys.stdout.write(' + repr(raw) + ')')

    def test_line_record_stderr_nonzero_and_timeout_bounds_fail_closed(self):
        self.assert_private_failure(
            "import json;print(json.dumps({'MESSAGE':'x'*1048577,'private':'" + PRIVATE + "'}))")
        with patch.object(s, 'JOURNAL_RECORD_LIMIT', 2):
            self.assert_private_failure("import json\nfor i in range(3): print(json.dumps({'MESSAGE':'ok'}))")
        self.assert_private_failure('import sys\nsys.stderr.write(' + repr(PRIVATE + 'x' * 70000) + ')')
        self.assert_private_failure('import sys\nsys.stderr.write(' + repr(PRIVATE) + ');raise SystemExit(9)')
        self.assert_private_failure('import time;time.sleep(2)', timeout=.1)

    def test_exited_leader_cannot_leave_pipe_holding_descendant(self):
        with tempfile.TemporaryDirectory(prefix='arctic-journal-group-') as temp:
            identity = Path(temp) / 'identity'
            child = "import time;time.sleep(60)"
            program = (
                "import os,subprocess,sys\n"
                "child=subprocess.Popen([sys.executable,'-c'," + repr(child) + "])\n"
                "open(" + repr(str(identity)) + ",'w').write("
                "str(os.getpid())+' '+str(child.pid))\n")
            self.assert_private_failure(program, timeout=1)
            leader, descendant = (int(value) for value in identity.read_text().split())
            deadline = time.monotonic() + 5
            state = None
            while time.monotonic() < deadline:
                try:
                    status = Path('/proc', str(descendant), 'status').read_text()
                except FileNotFoundError:
                    state = None
                    break
                state = next(line for line in status.splitlines() if line.startswith('State:')).split(':', 1)[1].strip()
                if state.startswith('Z '):
                    break
                time.sleep(.05)
            else:
                self.fail('owned journal descendant remained live after cleanup')
            # An orphan can remain visible as an init-owned zombie in a
            # container. Zombie state is kernel proof it cannot run or hold fds.
            if state is not None:
                self.assertTrue(state.startswith('Z '))

    def test_invalid_cursor_and_projection_fail_closed(self):
        for cursor in ('', 'private\nvalue', 'x' * 4097, None):
            with self.subTest(cursor=repr(cursor)), self.assertRaisesRegex(
                    RuntimeError, '^journal stream validation failed$'):
                s.journal_avc_count(cursor, timeout=1)
        clean = {'selinux': 'Enforcing', 'audit': {'enabled': 1, 'lost': 0}}
        audit = {'bytes': 0, 'records': 0, 'sha256': hashlib.sha256(b'').hexdigest(), 'avcs': 0}
        for projection in (True, -1, PRIVATE, None):
            with self.subTest(projection=projection), self.assertRaises(RuntimeError):
                s.verify_security(clean, clean, projection, audit)

    def test_audit_file_stream_scans_more_than_old_bound_and_returns_fixed_summary(self):
        raw = (b'benign audit record\n' * 230000) + b'final unterminated record'
        self.assertGreater(len(raw), s.LIMIT)
        result = s.scan_audit_interval(io.BytesIO(raw), len(raw))
        self.assertEqual(result, {
            'bytes': len(raw), 'records': 230001,
            'sha256': hashlib.sha256(raw).hexdigest(), 'avcs': 0})
        public = s.verify_security(
            {'selinux': 'Enforcing', 'audit': {'enabled': 1, 'lost': 0}},
            {'selinux': 'Enforcing', 'audit': {'enabled': 1, 'lost': 0}}, 0, result)
        self.assertEqual(public['audit_interval'], {
            'bytes': len(raw), 'records': 230001, 'sha256': hashlib.sha256(raw).hexdigest()})
        self.assertNotIn('avcs', public['audit_interval'])

    def test_audit_file_stream_detects_first_middle_last_avcs(self):
        raw = b'avc: denied first\nbenign\ntype=USER_AVC middle\nbenign\ntype=AVC last'
        result = s.scan_audit_interval(io.BytesIO(raw), len(raw))
        self.assertEqual(result['avcs'], 3)
        self.assertEqual(result['records'], 5)
        clean = {'selinux': 'Enforcing', 'audit': {'enabled': 1, 'lost': 0}}
        with self.assertRaisesRegex(RuntimeError, 'new AVC'):
            s.verify_security(clean, clean, 0, result)

    def test_audit_file_stream_line_record_total_and_exact_length_fail_closed(self):
        with patch.object(s, 'AUDIT_LINE_LIMIT', 3):
            with self.assertRaisesRegex(RuntimeError, 'line bound'):
                s.scan_audit_interval(io.BytesIO(b'abcd\n'), 5)
        with patch.object(s, 'AUDIT_RECORD_LIMIT', 2):
            with self.assertRaisesRegex(RuntimeError, 'record count'):
                s.scan_audit_interval(io.BytesIO(b'a\nb\nc\n'), 6)
        with patch.object(s, 'AUDIT_TOTAL_LIMIT', 3):
            with self.assertRaisesRegex(RuntimeError, 'total byte'):
                s.scan_audit_interval(io.BytesIO(b'abcd'), 4)
        with self.assertRaisesRegex(RuntimeError, 'declared byte count'):
            s.scan_audit_interval(io.BytesIO(b'abc'), 4)


if __name__ == '__main__':
    unittest.main(verbosity=2)
