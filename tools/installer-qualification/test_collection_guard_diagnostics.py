"""Actual poll/target/capture guards stay fatal; source IDs carry no private data."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace, TracebackType
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).parent))
import runner as R
D=R._driver
spec=importlib.util.spec_from_file_location('owned_collection_controller',Path(__file__).with_name('controller.py'))
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
TOKEN='a'*32
PRIVATE='private-password-transcript-path'

class CollectionControls(unittest.TestCase):
    def controller(self,out,query=None):
        display=SimpleNamespace(proof={'gpu_id':'arctic_taskbar_gpu','guest_monitor_verification_required':True,
            'heads':[{'head':0},{'head':1}]},_query=query)
        vm=SimpleNamespace(proc=SimpleNamespace(pid=17,poll=lambda:None))
        context={'schema':'arctic-installer-active-context-v1','binding_id':'b'*32,
            'disk_serial':'arctic-a-aaaaaaaaaaa','write_bps':8388608}
        return C.InstallerController(vm,display,context,out)

    def code(self,error):return D.diagnostic_code('driver-collect',error,C)

    def test_actual_poll_pending_bound_and_request_identity_remain_fatal(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);serial=out/'serial.log';control=self.controller(out)
            serial.write_bytes(b'x'*16385)
            with self.assertRaises(RuntimeError) as caught:control.poll(serial)
            self.assertEqual(caught.exception.args,('installer serial pending line exceeds bound',))
            self.assertEqual(self.code(caught.exception),'installer-inner-driver-collect-guard-collection-017')
            serial.write_text('ARCTIC-INSTALLER-REQUEST {}\n')
            with self.assertRaises(RuntimeError) as caught:control.poll(serial)
            self.assertEqual(self.code(caught.exception),'installer-inner-driver-collect-guard-collection-020')
            self.assertEqual(control.position,0);self.assertEqual(control.receipts,[])

    def test_actual_nested_target_identity_and_counter_guards_remain_fatal(self):
        for bad in ('identity','counters'):
            with self.subTest(bad=bad),tempfile.TemporaryDirectory() as temp:
                out=Path(temp)
                def query(vm,name,*_):
                    if name=='query-block':return [{'inserted':{'node-name':'target0','file':PRIVATE if bad=='identity' else str(out/'target.qcow2'),'ro':False}}]
                    return [{'node-name':'target0','stats':{'wr_bytes':PRIVATE,'wr_operations':0}}]
                control=self.controller(out,query)
                with self.assertRaises(RuntimeError) as caught:control.active_write_proof()
                self.assertEqual(self.code(caught.exception),'installer-inner-driver-collect-guard-collection-'+('032'if bad=='identity'else'033'))
                self.assertEqual(control.receipts,[])

    def test_unchanged_bounded_target_progress_guard_is_observed_without_waiting(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)
            def query(vm,name,*_):
                if name=='query-block':return [{'inserted':{'node-name':'target0','file':str(out/'target.qcow2'),'ro':False}}]
                return [{'node-name':'target0','stats':{'wr_bytes':0,'wr_operations':0}}]
            control=self.controller(out,query)
            with patch.object(C.time,'monotonic',side_effect=(0,0,21)), \
                    self.assertRaises(RuntimeError) as caught:control.active_write_proof()
            self.assertEqual(caught.exception.args,('genuine target writes did not continue during disruption',))
            self.assertEqual(self.code(caught.exception),'installer-inner-driver-collect-guard-collection-034')

    def test_actual_console_capture_name_guard_stays_fatal(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);(out/'owned.png').write_bytes(b'private-owned-bytes');control=self.controller(out)
            with self.assertRaises(RuntimeError) as caught:control.capture('owned')
            self.assertEqual(self.code(caught.exception),'installer-inner-driver-collect-guard-collection-011')
            self.assertEqual((out/'owned.png').read_bytes(),b'private-owned-bytes')

    def test_deepest_actual_nested_runtimeerror_phase_keeps_exact_private_exception(self):
        primary=RuntimeError(PRIVATE)
        with tempfile.TemporaryDirectory() as temp:
            def query(*_):raise primary
            control=self.controller(Path(temp),query)
            try:
                control.active_write_proof()
            except RuntimeError as caught:
                self.assertIs(caught,primary)
                # assertRaises deliberately clears traceback after its context;
                # the actual driver projects while its exception is still live.
                code=self.code(caught)
            else:self.fail('original nested query failure must remain fatal')
        self.assertEqual(primary.args,(PRIVATE,))
        self.assertEqual(code,'installer-inner-driver-collect-phase-target-write-sample-runtime-error')

    def test_traceback_frame_budget_requires_complete_owned_phase_chain(self):
        self.assertEqual(D.MAX_COLLECTION_DIAGNOSTIC_FRAMES, 64)
        primary = RuntimeError(PRIVATE)
        with tempfile.TemporaryDirectory() as temp:
            def query(*_): raise primary
            control = self.controller(Path(temp), query)
            try:
                control.active_write_proof()
            except RuntimeError as caught:
                self.assertIs(caught, primary)
                original = caught.__traceback__
                owned = original
                while owned.tb_frame.f_code.co_qualname != 'InstallerController.active_write_proof.<locals>.sample':
                    owned = owned.tb_next
                for count in (64, 65, 4096):
                    chain = None
                    for _ in range(count):
                        chain = TracebackType(chain, owned.tb_frame, owned.tb_lasti, owned.tb_lineno)
                    caught.__traceback__ = chain
                    expected = ('installer-inner-driver-collect-phase-target-write-sample-runtime-error'
                        if count == 64 else 'installer-inner-driver-collect-runtime-error')
                    self.assertEqual(self.code(caught), expected)
                    self.assertIs(caught, primary)
                    self.assertEqual(caught.args, (PRIVATE,))
                caught.__traceback__ = original
            else:
                self.fail('the original nested operation must remain fatal')

    def test_foreign_callsite_or_forged_nonce_does_not_mint_source_identity(self):
        with self.assertRaises(RuntimeError) as caught:C.require(False,PRIVATE)
        self.assertNotIn('_arctic_installer_collection_guard',caught.exception.__dict__)
        self.assertEqual(self.code(caught.exception),'installer-inner-driver-collect-runtime-error')
        for proof in ((object(),'collection-032'),(C._COLLECTION_GUARD_TOKEN,PRIVATE),[C._COLLECTION_GUARD_TOKEN,'collection-032']):
            error=RuntimeError(PRIVATE);error._arctic_installer_collection_guard=proof
            self.assertEqual(self.code(error),'installer-inner-driver-collect-runtime-error')

    def test_hostile_subclass_attributes_are_never_read_by_guard_projector(self):
        class Hostile(RuntimeError):
            @property
            def args(self):raise AssertionError('private args read')
            @property
            def __dict__(self):raise AssertionError('private attributes read')
            @property
            def __traceback__(self):raise AssertionError('private traceback read')
        self.assertIsNone(D.collection_guard_code(Hostile(),C))
        self.assertIsNone(D.collection_guard_code(RuntimeError(PRIVATE),SimpleNamespace()))

    def test_source_id_nonce_relay_and_failed_stdout_keep_original_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            serial=Path(temp)/'serial.log';serial.write_bytes(b'x'*16385)
            with self.assertRaises(RuntimeError) as caught:self.controller(Path(temp)).poll(serial)
            error=caught.exception
            stream=io.StringIO()
            with patch.dict(os.environ,{'ARCTIC_INSTALLER_DIAGNOSTIC_TOKEN':TOKEN}),contextlib.redirect_stdout(stream):D.diagnose('driver-collect',error,C)
            self.assertEqual(R.inner_codes(stream.getvalue().encode(),TOKEN),('installer-inner-driver-collect-guard-collection-017',))
            self.assertNotIn(PRIVATE,stream.getvalue())
            for failure in (OSError(PRIVATE),RuntimeError(PRIVATE),TypeError(PRIVATE)):
                with patch.dict(os.environ,{'ARCTIC_INSTALLER_DIAGNOSTIC_TOKEN':TOKEN}),patch('builtins.print',side_effect=failure):
                    D.diagnose('driver-collect',error,C)
            self.assertEqual(error.args,('installer serial pending line exceeds bound',))

    def test_optional_minter_and_projector_failure_preserve_original_primary(self):
        for failure in (RuntimeError(PRIVATE),TypeError(PRIVATE),OSError(PRIVATE)):
            primary=RuntimeError('installer serial pending line exceeds bound')
            with patch.object(C,'RuntimeError',create=True,return_value=primary),patch.object(C,'_mint_collection_guard',side_effect=failure):
                with self.assertRaises(RuntimeError) as caught:C.require(False,'installer serial pending line exceeds bound')
            self.assertIs(caught.exception,primary)
            with patch.object(D,'collection_guard_code',side_effect=failure):
                self.assertEqual(self.code(primary),'installer-inner-driver-collect-runtime-error')

    def test_original_or_observer_cancellation_keeps_exact_identity(self):
        for cancellation in (KeyboardInterrupt(PRIVATE),SystemExit(PRIVATE)):
            with tempfile.TemporaryDirectory() as temp:
                def query(*_):raise cancellation
                with self.assertRaises(type(cancellation)) as caught:self.controller(Path(temp),query).active_write_proof()
                self.assertIs(caught.exception,cancellation)
            with patch.object(C,'_mint_collection_guard',side_effect=cancellation):
                with self.assertRaises(type(cancellation)) as caught:C.require(False,PRIVATE)
            self.assertIs(caught.exception,cancellation)

    def test_actual_driver_failure_gate_keeps_source_guard_and_owned_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);(out/'data').mkdir();context={'schema':'arctic-installer-active-context-v1',
                'binding_id':'b'*32,'disk_bytes':68719476736,'disk_serial':'arctic-a-aaaaaaaaaaa','write_bps':8388608}
            (out/'data/installer-context.json').write_text(json.dumps(context));(out/'serial.log').write_bytes(b'x'*16385)
            cleanup=[];saved=[]
            vm=SimpleNamespace(proc=SimpleNamespace(pid=17,poll=lambda:0 if 'host' in cleanup else None),alive=lambda:True,
                type_text=lambda *args,**kwargs:None,keys=lambda *_:None,close_handles=lambda:cleanup.append('handles'))
            control=self.controller(out);control.vm=vm
            display=SimpleNamespace(enable=lambda *_:{},closed=True)
            display_module=SimpleNamespace(TaskbarDisplay=lambda:display,qmp_query=lambda *_:{'running':True})
            persist=C.persist_cleanup_state
            def record_persist(path,state,errors,pending):
                persist(path,state,errors,pending)
                saved.append((dict(state),list(errors)))
            stream=io.StringIO()
            with contextlib.ExitStack() as stack:
                for obj,name,value in ((D.os,'geteuid',lambda:0),(Path,'is_char_device',lambda _:True),
                    (D,'load',lambda name,path:display_module if name=='installer_display_fixture' else C),
                    (D,'sha',lambda *_:'a'*64),(D.signal,'signal',lambda *_:None),
                    (D,'prepare_vm',lambda *_:['private-argv']),(D,'owned_vm_type',lambda *_:lambda *_:vm),
                    (D,'choose_install',lambda *_:None),(D,'authenticate_console',lambda *_:{}),
                    (D,'stop_owned',lambda *_:cleanup.append('host')),(C,'InstallerController',lambda *_:control),
                    (C,'persist_cleanup_state',record_persist)):
                    stack.enter_context(patch.object(obj,name,value))
                stack.enter_context(patch.dict(sys.modules,{'vmtest':SimpleNamespace(),'iso_startup':SimpleNamespace()}))
                stack.enter_context(patch.dict(os.environ,{'ARCTIC_INSTALLER_DIAGNOSTIC_TOKEN':TOKEN}))
                stack.enter_context(patch.object(sys,'argv',['driver','--out',str(out)]))
                stack.enter_context(contextlib.redirect_stdout(stream))
                status=D.main()
            self.assertEqual(status,1);self.assertEqual(cleanup,['host','handles']);self.assertEqual(len(saved),1)
            self.assertEqual(saved[0][0]['status'],'failed');self.assertIs(saved[0][0]['release_acceptance'],False)
            self.assertNotIn('host_transitions',saved[0][0]);self.assertNotIn('installed_boot',saved[0][0])
            self.assertEqual(saved[0][1],['RuntimeError: installer serial pending line exceeds bound'])
            self.assertEqual(R.inner_codes(stream.getvalue().encode(),TOKEN),('installer-inner-driver-collect-guard-collection-017',))

if __name__=='__main__':unittest.main()
