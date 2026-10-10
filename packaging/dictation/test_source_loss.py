"""Owned graph loss and recording epoch contracts; local runtime control is separate."""
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock
SPEC = importlib.util.spec_from_file_location("source_loss_dictation", Path(__file__).with_name("dictation.py"))
d = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(d)


def graph():
    def row(identity, kind, props, **info):
        return {"id": identity, "type": "PipeWire:Interface:" + kind,
                "info": {"props": {"object.serial": identity + 100, **props}, **info}}
    return [row(1,"Client",{"pipewire.protocol":"protocol-native","pipewire.sec.pid":123,"pipewire.sec.uid":1000}),
            row(2,"Node",{"client.id":1,"media.class":"Stream/Input/Audio"}),
            row(3,"Node",{"media.class":"Audio/Source"}),
            row(4,"Link",{}, **{"input-node-id":2,"output-node-id":3})]


class Routes(unittest.TestCase):
    def test_authenticated_client_route_without_app_pid(self):
        self.assertEqual(d.capture_routes(graph(),123,1000),frozenset({((1,101),(2,102),(3,103),(4,104))}))

    def test_unrelated_sources_do_not_mask_selected_loss(self):
        original=d.capture_routes(graph(),123,1000)
        for removed in (1,2,3,4):
            with self.subTest(removed=removed):
                altered=[o for o in graph() if o['id']!=removed]
                altered.append({'id':5,'type':'PipeWire:Interface:Node','info':{'props':{'object.serial':105,'media.class':'Audio/Source'}}})
                self.assertFalse(original <= d.capture_routes(altered,123,1000))

    def test_forged_and_ambiguous_owner_rejected(self):
        for key,value in [('pipewire.sec.pid',999),('pipewire.sec.uid',1001),('pipewire.protocol','other')]:
            with self.subTest(key=key):
                altered=graph();altered[0]['info']['props'][key]=value
                self.assertEqual(d.capture_routes(altered,123,1000),frozenset())
        altered=graph();duplicate=copy.deepcopy(altered[0]);duplicate['id']=9;altered.append(duplicate)
        self.assertIsNone(d.capture_routes(altered,123,1000))
        for props in ({'client.id':9},{'application.process.id':999},{'application.process.uid':1001},{'media.class':'Stream/Output/Audio'}):
            altered=graph();altered[1]['info']['props'].update(props)
            self.assertEqual(d.capture_routes(altered,123,1000),frozenset())

    def test_serial_reuse_changes_route_identity(self):
        original=d.capture_routes(graph(),123,1000)
        for index in range(4):
            altered=graph();altered[index]['info']['props']['object.serial']+=1000
            self.assertFalse(original <= d.capture_routes(altered,123,1000))

    def test_malformed_graph_is_unknown_and_private_values_never_formatted(self):
        class Secret:
            def __eq__(self,other):raise AssertionError('formatted private value')
            def __str__(self):raise AssertionError('formatted private value')
        for altered in (None,{},[{}],graph()+[graph()[0]],graph()*3000):
            self.assertIsNone(d.capture_routes(altered,123,1000))
        for index,key in ((0,'pipewire.protocol'),(1,'media.class'),(2,'media.class')):
            altered=graph();altered[index]['info']['props'][key]=Secret()
            self.assertEqual(d.capture_routes(altered,123,1000),frozenset())
        for value in (True,-1,'+1','01','1.0',Secret()):
            altered=graph();altered[0]['info']['props']['pipewire.sec.pid']=value
            self.assertEqual(d.capture_routes(altered,123,1000),frozenset())
        for index in range(4):
            altered=graph();del altered[index]['info']['props']['object.serial']
            self.assertIsNone(d.capture_routes(altered,123,1000))


class Watch(unittest.TestCase):
    def watcher(self):
        watch=d.RecordingInputWatch.__new__(d.RecordingInputWatch)
        watch.process=mock.Mock();watch.process.poll.return_value=None;watch.binary='/fixed/engine';watch.env={};watch.identity=(123,1000,'100')
        watch.stop=threading.Event();watch.lock=threading.Lock();watch.query=None;watch.failure='';watch.selected=None
        return watch

    def test_selected_loss_is_confirmed_after_identity_checks(self):
        watch=self.watcher(); routes=d.capture_routes(graph(),123,1000)
        with mock.patch.object(d,'audio_engine_identity',return_value=watch.identity),mock.patch.object(watch,'snapshot',side_effect=[routes,frozenset()]),mock.patch.object(watch.stop,'wait'):
            watch.watch()
        self.assertEqual(watch.failure,'microphone');self.assertEqual(watch.selected,routes)

    def test_engine_exit_remains_owned_by_existing_gpu_failure_handler(self):
        watch=self.watcher();watch.process.poll.return_value=1
        with mock.patch.object(watch,'snapshot') as snapshot:watch.watch()
        snapshot.assert_not_called();self.assertEqual(watch.failure,'')

    def test_changed_owned_engine_never_accepts_old_graph(self):
        watch=self.watcher()
        with mock.patch.object(d,'audio_engine_identity',side_effect=[watch.identity,(123,1000,'101')]),mock.patch.object(watch,'snapshot',return_value=d.capture_routes(graph(),123,1000)):
            watch.watch()
        self.assertEqual(watch.failure,'audio-monitor');self.assertIsNone(watch.selected)

    def test_unknown_is_not_confirmed_source_loss(self):
        watch=self.watcher()
        with mock.patch.object(d,'audio_engine_identity',return_value=watch.identity),mock.patch.object(watch,'snapshot',return_value=None),mock.patch.object(watch.stop,'wait'),mock.patch.object(d.time,'monotonic',side_effect=[0,0,1,3]):
            watch.watch()
        self.assertEqual(watch.failure,'audio-monitor')

    def test_cancelled_epoch_cannot_publish_loss(self):
        watch=self.watcher()
        def cancelled():watch.stop.set();return frozenset()
        with mock.patch.object(d,'audio_engine_identity',return_value=watch.identity),mock.patch.object(watch,'snapshot',side_effect=cancelled):watch.watch()
        self.assertEqual(watch.failure,'')

    def test_snapshot_bounds_and_duplicate_json_fail_closed(self):
        watch=self.watcher()
        for body in (b'[{"id":1,"id":2}]',b'NaN',b'"'+b'x'*(2*1024*1024)+b'"',b'{"secret":"private material"}'):
            with self.subTest(length=len(body)):
                query=subprocess.Popen(['/usr/bin/python3','-c','import sys;sys.stdout.buffer.write(sys.stdin.buffer.read())'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
                # Send in an owned thread so over-cap output cannot block this test.
                writer=threading.Thread(target=lambda: self.feed(query,body));writer.start()
                with mock.patch.object(d,'supervised',return_value=query):self.assertIsNone(watch.snapshot())
                writer.join(timeout=2);self.assertFalse(writer.is_alive());self.assertIsNotNone(query.poll());self.assertIsNone(watch.query)

    @staticmethod
    def feed(query,body):
        try:query.stdin.write(body)
        except BrokenPipeError:pass
        finally:query.stdin.close()

    def test_cancel_during_query_reaps_child_without_publishing_failure(self):
        watch=self.watcher()
        query=subprocess.Popen(['/usr/bin/python3','-c','import time;time.sleep(10)'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        with mock.patch.object(d,'supervised',return_value=query):
            worker=threading.Thread(target=watch.snapshot);worker.start()
            deadline=time.monotonic()+2
            while watch.query is None and time.monotonic()<deadline:time.sleep(.005)
            self.assertIs(watch.query,query);watch.close();worker.join(timeout=2)
        self.assertFalse(worker.is_alive());self.assertIsNotNone(query.poll());self.assertIsNone(watch.query);self.assertEqual(watch.failure,'')

    def test_close_kills_only_own_query_and_returns_without_join(self):
        watch=self.watcher();watch.query=mock.Mock();watch.query.poll.return_value=None
        watch.close();self.assertTrue(watch.stop.is_set());watch.query.kill.assert_called_once();watch.query.wait.assert_not_called()


class Epoch(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.shared=Path(self.tmp.name);self.private=self.shared/'dictation';self.private.mkdir()
        self.refresh=mock.patch.object(d,'notify_refresh');self.refresh.start();self.addCleanup(self.refresh.stop)
        self.snap=mock.patch.object(d,'snapshot',side_effect=lambda value=None:{'ok':True,'state':'ready',**(value or {})});self.snap.start();self.addCleanup(self.snap.stop)
        self.broker=d.Broker(self.shared,self.private)

    def test_stop_disarms_before_capture_teardown(self):
        old=mock.Mock();old.failure='';self.broker.input_watch=old;self.broker.runtime['state']='recording'
        def record(verb):self.assertIsNone(self.broker.input_watch);old.close.assert_called_once();return 0
        with mock.patch.object(self.broker,'record',side_effect=record):result=self.broker.command('stop')
        self.assertEqual(result['state'],'transcribing')

    def test_confirmed_loss_before_stop_cannot_insert(self):
        self.broker.input_watch=mock.Mock(failure='microphone');self.broker.process=mock.Mock();self.broker.process.poll.return_value=None
        self.broker.runtime.update(state='recording',active_backend='cpu')
        with mock.patch.object(self.broker,'locked',return_value=False),mock.patch.object(self.broker,'terminate') as terminate,mock.patch.object(self.broker,'record') as record:
            result=self.broker.command('stop')
        record.assert_not_called();terminate.assert_called_once();self.assertEqual(result['state'],'error')

    def test_stop_preserves_prior_gpu_failure_or_exited_gpu_engine(self):
        for prior,exit_code in (('engine',None),('',1)):
            with self.subTest(prior=prior,exit_code=exit_code):
                self.broker.input_watch=mock.Mock(failure='microphone');self.broker.process=mock.Mock();self.broker.process.poll.return_value=exit_code
                self.broker.failure=prior;self.broker.fallback_cpu=False;self.broker.runtime.update(state='recording',active_backend='vulkan')
                with mock.patch.object(self.broker,'locked',return_value=False),mock.patch.object(self.broker,'terminate') as terminate,mock.patch.object(self.broker,'record') as record:
                    result=self.broker.command('stop')
                record.assert_not_called();terminate.assert_called_once();self.assertTrue(self.broker.fallback_cpu)
                self.assertEqual(result['state'],'error');self.assertEqual(result['active_backend'],'cpu');self.assertIn('record again',result['error'])

    def test_cancel_disarms_before_record_cancel_and_cleanup(self):
        old=mock.Mock();self.broker.input_watch=old;self.broker.process=mock.Mock();self.broker.process.poll.return_value=None
        def record(verb):self.assertIsNone(self.broker.input_watch);return 0
        with mock.patch.object(self.broker,'record',side_effect=record),mock.patch.object(self.broker,'terminate'),mock.patch.object(d,'ready',return_value=True):self.broker.command('cancel')
        old.close.assert_called_once()

    def test_old_epoch_result_cannot_fail_new_recording(self):
        old=mock.Mock();old.failure='microphone';new=mock.Mock();new.failure=''
        self.broker.input_watch=old;self.broker.stop_input_watch();self.broker.input_watch=new
        self.broker.process=mock.Mock();self.broker.process.poll.return_value=None;self.broker.started=time.monotonic()
        self.broker.runtime.update(state='recording',active_backend='cpu')
        with mock.patch.object(self.broker,'locked',return_value=False),mock.patch.object(self.broker,'terminate') as terminate:self.broker.tick()
        terminate.assert_not_called();self.assertEqual(self.broker.runtime['state'],'recording')

    def test_lock_and_generation_cancellation_disarm_current_epoch(self):
        for locked,generation in ((True,''),(False,'new-generation')):
            self.broker.process=None;self.broker.input_watch=mock.Mock(failure='');watch=self.broker.input_watch
            self.broker.runtime.update(state='recording',active_backend='cpu');self.broker.process=mock.Mock();self.broker.process.poll.return_value=0
            with mock.patch.object(self.broker,'locked',return_value=locked),mock.patch.object(d,'cancellation',return_value=generation):
                self.broker.tick()
            watch.close.assert_called_once();self.assertIsNone(self.broker.input_watch);self.assertIsNone(self.broker.process)
            self.assertEqual(self.broker.runtime['state'],'ready')

    def test_exited_gpu_engine_retains_explicit_cpu_retry(self):
        self.broker.input_watch=mock.Mock(failure='audio-monitor');self.broker.process=mock.Mock();self.broker.process.poll.return_value=1
        self.broker.runtime.update(state='recording',active_backend='vulkan')
        with mock.patch.object(self.broker,'locked',return_value=False),mock.patch.object(self.broker,'terminate'):
            self.broker.tick()
        self.assertTrue(self.broker.fallback_cpu);self.assertEqual(self.broker.runtime['active_backend'],'cpu')
        self.assertIn('record again',self.broker.runtime['error'])

    def test_loss_error_has_no_gpu_retry_and_no_transcript(self):
        for failure in ('microphone','audio-monitor'):
            self.broker.input_watch=mock.Mock(failure=failure);self.broker.process=mock.Mock();self.broker.process.poll.return_value=None
            self.broker.runtime.update(state='recording',active_backend='vulkan')
            with mock.patch.object(self.broker,'locked',return_value=False),mock.patch.object(self.broker,'terminate') as terminate:self.broker.tick()
            terminate.assert_called_once();self.assertFalse(self.broker.fallback_cpu);self.assertFalse(self.broker.runtime['ok']);self.assertEqual(self.broker.runtime['state'],'error')
            self.assertNotIn('private',json.dumps(self.broker.runtime))

class SourceScope(unittest.TestCase):
    # Exact original 688c2d01 controller bytes, before Mic monitoring and the
    # accepted GPU recording-control fix. Source RPMs carry no Git history.
    ORIGINAL_CONTROLLER_SHA256 = 'bf11b3b1cf65cc66f21a21d7246f8ffd82f975762a99dba06137ad2e31a45290'

    def controller_rollback(self, current):
        # Reverse accepted 6482231 GPU changes before the original Mic reversal.
        gpu_changes = [
            ('    def record_control_failure(self, verb, backend):\n        # A failed owned recording command can precede the next engine tick.\n        # Preserve an observed microphone failure; otherwise a failed Vulkan\n        # recording selects CPU only for a later, explicitly started recording.\n        if cancellation(self.private) != self.cancel_generation or (self.shared / "dictation-locked").exists():\n            self.terminate()\n            return self.write(ok=True, state="ready", error="", message="Recording discarded.")\n        gpu_retry = backend == "vulkan" and self.failure not in ("microphone", "audio-monitor")\n        self.terminate()\n        if gpu_retry:\n            self.fallback_cpu = True\n            message = ("GPU initialization failed. CPU is selected for this session; record again."\n                       if verb == "start" else "GPU transcription failed. CPU is selected for this session; record again.")\n            return self.write(ok=False, state="error", error=message, active_backend="cpu",\n                              active_cpu_variant=desired_profile()["cpu_variant"])\n        message = ("Recording could not start. Check the microphone in Sound settings."\n                   if verb == "start" else "Recording could not stop safely and was discarded. Record again.")\n        return self.write(ok=False, state="error", error=message)\n\n', ''),
            ('        try:\n            result = self.record("start")\n        except (OSError, subprocess.TimeoutExpired):\n            return self.record_control_failure("start", backend)\n', '        result = self.record("start")\n'),
            ('        if result:\n            return self.record_control_failure("start", backend)\n', '        if result:\n            self.terminate()\n            return self.write(ok=False, state="error", error="Recording could not start. Check the microphone in Sound settings.")\n'),
            ('            try:\n                failed = self.record("stop")\n            except (OSError, subprocess.TimeoutExpired):\n                failed = True\n            if failed:\n                return self.record_control_failure("stop", self.runtime.get("active_backend"))\n', '            if self.record("stop"):\n                self.terminate()\n                return self.write(ok=False, state="error", error="Recording could not stop safely and was discarded. Record again.")\n'),
        ]
        for addition, original in gpu_changes:
            self.assertEqual(current.count(addition), 1)
            current = current.replace(addition, original, 1)
        current=current.replace('import re\n','',1)
        current=current.replace('Path("/usr/bin/wl-copy"), Path("/usr/bin/pw-dump")','Path("/usr/bin/wl-copy")',1)
        begin=current.index('\n\n\nINPUT_GRAPH_BYTES =');end=current.index('\n\nclass Broker:',begin)
        current=current[:begin]+current[end:]
        additions=[
            '        self.input_watch = None\n',
            '        self.stop_input_watch()\n',
            '    def stop_input_watch(self):\n        watch, self.input_watch = self.input_watch, None\n        if watch:\n            watch.close()\n\n',
            '        self.input_watch = RecordingInputWatch(self.process, self.binary, self.env)\n',
            '            self.stop_input_watch()\n',
            '            if self.input_watch and self.input_watch.failure:\n                # A confirmed loss observed before Stop must not be turned into\n                # intended transcription merely because IPC won the tick race.\n                if self.process and self.process.poll() is None and not self.failure:\n                    self.failure = self.input_watch.failure\n                self.tick()\n                return snapshot(self.runtime)\n            # Stop tears down the capture link normally. Disarm this epoch first,\n            # so a late result cannot discard intended transcription or a retry.\n            self.stop_input_watch()\n',
            '        if (self.input_watch and self.runtime.get("state") == "recording" and self.input_watch.failure\n                and self.process.poll() is None and not self.failure):\n            self.failure = self.input_watch.failure\n',
            '            elif category == "audio-monitor":\n                message = "The microphone connection could not be checked safely. Recording was discarded. Check Sound settings and record again."\n',
        ]
        # Remove complete longer blocks before their constituent shorter line.
        for addition in sorted(additions,key=len,reverse=True):
            self.assertEqual(current.count(addition),1);current=current.replace(addition,'',1)
        return current

    def test_controller_whole_byte_rollback_and_profile_receipts_unchanged(self):
        original = self.controller_rollback(Path(d.__file__).read_text())
        self.assertEqual(hashlib.sha256(original.encode('utf-8')).hexdigest(), self.ORIGINAL_CONTROLLER_SHA256)
        self.assertIn('Requires:       pipewire-utils',Path(__file__).parent.parent.joinpath('arctic-linux.spec').read_text())

    def test_controller_rollback_rejects_original_byte_and_unremoved_gpu_changes(self):
        current = Path(d.__file__).read_text()
        mutations = [
            ('original byte', 'VERSION = "1.1.0"', 'VERSION = "1.1.1"'),
            ('unremoved GPU change', '    def command(self, verb, generation=None):',
             '    # unremoved GPU control mutation\n    def command(self, verb, generation=None):'),
        ]
        for label, before, after in mutations:
            with self.subTest(mutation=label):
                self.assertEqual(current.count(before), 1)
                original = self.controller_rollback(current.replace(before, after, 1))
                with self.assertRaises(AssertionError):
                    self.assertEqual(hashlib.sha256(original.encode('utf-8')).hexdigest(), self.ORIGINAL_CONTROLLER_SHA256)

if __name__=='__main__':unittest.main()
