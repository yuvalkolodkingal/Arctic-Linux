"""Recording-control failures against owned children; no real VoxType/ISO proof."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

spec=importlib.util.spec_from_file_location('control_failure_subject',Path(__file__).with_name('dictation.py'))
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)


class RecordingControlFailures(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.shared=Path(self.tmp.name);self.private=self.shared/'dictation';self.private.mkdir(mode=0o700)
        for name, replacement in [('notify_refresh',mock.Mock()),
                ('snapshot',lambda runtime=None: {'ok':True,'state':'ready','ready':True,**(runtime or {})}),
                ('desired_profile',lambda:d.PROFILES['turbo-q5-v3'])]:
            patch=mock.patch.object(d,name,replacement);patch.start();self.addCleanup(patch.stop)
        self.broker=d.Broker(self.shared,self.private);self.addCleanup(self.broker.terminate)
        self.broker.cpu_variant='avx2'
        self.child=None

    def owned(self,*args,**kwargs):
        # Only this child's handles are handed to Broker. No audio/model loaded.
        self.child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        child=self.child
        def cleanup():
            if child.poll() is None:child.kill();child.wait(timeout=2)
            for stream in (child.stdout,child.stderr):stream.close()
        self.addCleanup(cleanup)
        (self.private/'voxtype-state').write_text('idle')
        return self.child

    def call(self,verb,backend='vulkan',fault=1,category='',cancel=False):
        self.broker.failure=category
        (self.private/'transcript').write_text('PRIVATE_TRANSCRIPT_SENTINEL')
        if verb=='stop':
            self.broker.process=self.owned();self.broker.runtime.update(state='recording',active_backend=backend)
        def record(_verb):
            self.broker.failure=category
            if cancel:d.mark_cancel(self.private)
            if isinstance(fault,Exception):raise fault
            return fault
        with mock.patch.object(self.broker,'record',side_effect=record), \
                mock.patch.object(self.broker,'locked',return_value=False), \
                mock.patch.object(d,'ready',return_value=True), \
                mock.patch.object(d,'preferences',return_value={'backend':backend,'language':'en'}), \
                mock.patch.object(d,'gpu_available',return_value=True), \
                mock.patch.object(d,'supervised',side_effect=self.owned) as spawn:
            result=self.broker.command(verb)
        self.assertIsNotNone(self.child);self.assertIsNotNone(self.child.poll())
        self.assertIsNone(self.broker.process);self.assertIsNone(self.broker.output_process)
        self.assertFalse((self.private/'transcript').exists())
        self.assertNotIn('PRIVATE_TRANSCRIPT_SENTINEL',(self.shared/'dictation.json').read_text())
        self.assertNotEqual(result['state'],'transcribing')
        return result,spawn.call_count

    def test_actual_start_and_stop_nonzero_or_expected_exception_select_explicit_cpu_retry(self):
        for verb in ('start','stop'):
            for fault in (1,OSError('PRIVATE_ERROR_SENTINEL'),subprocess.TimeoutExpired('PRIVATE_ARGV',3)):
                with self.subTest(verb=verb,fault=type(fault).__name__):
                    self.broker.fallback_cpu=False
                    result,spawns=self.call(verb,fault=fault,category='engine')
                    self.assertFalse(result['ok']);self.assertEqual(result['state'],'error')
                    self.assertEqual(result['active_backend'],'cpu');self.assertEqual(result['active_cpu_variant'],'avx2')
                    self.assertTrue(self.broker.fallback_cpu);self.assertIn('record again',result['error'])
                    self.assertNotIn('PRIVATE_',json.dumps(result));self.assertEqual(spawns,int(verb=='start'))

    def test_ordinary_cpu_control_failures_keep_existing_messages_without_gpu_retry(self):
        for verb in ('start','stop'):
            with self.subTest(verb=verb):
                self.broker.fallback_cpu=False
                result,_=self.call(verb,backend='cpu')
                self.assertFalse(self.broker.fallback_cpu);self.assertNotIn('GPU',result['error'])
                self.assertEqual(result['error'], 'Recording could not start. Check the microphone in Sound settings.'
                    if verb=='start' else 'Recording could not stop safely and was discarded. Record again.')

    def test_known_microphone_or_monitor_error_does_not_become_gpu_retry(self):
        for verb in ('start','stop'):
            for category in ('microphone','audio-monitor'):
                with self.subTest(verb=verb,category=category):
                    self.broker.fallback_cpu=False
                    result,_=self.call(verb,category=category)
                    self.assertFalse(self.broker.fallback_cpu);self.assertNotIn('GPU',result['error'])

    def test_cancel_arriving_during_control_failure_discards_without_new_backend_selection(self):
        for verb in ('start','stop'):
            with self.subTest(verb=verb):
                self.broker.cancel_generation=d.cancellation(self.private);self.broker.fallback_cpu=False
                result,_=self.call(verb,cancel=True)
                self.assertTrue(result['ok']);self.assertEqual(result['state'],'ready')
                self.assertEqual(result['error'],'');self.assertFalse(self.broker.fallback_cpu)


if __name__=='__main__':unittest.main()
