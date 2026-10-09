"""Independent kernel-format, ELF and causal interval failure controls."""
import copy
import importlib.util
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

C = load('causal_fixture', ROOT/'tools/performance/causal.py')
R = load('causal_roles', ROOT/'tools/tests/test_performance_roles.py')


class CausalControls(unittest.TestCase):
    def test_tracefs_command_uses_one_nontruncating_nonseeking_owned_write(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);events=root/'uprobe_events'
            original=b'unrelated global events must not be truncated'+b'X'*100
            events.write_bytes(original)
            command='-:owned/map_create\n';data=command.encode('ascii')
            actual_open,actual_write,actual_close=os.open,os.write,os.close
            with patch.object(C.os,'open',wraps=actual_open) as opened, \
                 patch.object(C.os,'write',wraps=actual_write) as written, \
                 patch.object(C.os,'close',wraps=actual_close) as closed, \
                 patch.object(C.os,'lseek',side_effect=AssertionError('tracefs must not seek')):
                C.write_uprobe_command(root,command)
            opened.assert_called_once_with(events,os.O_WRONLY|os.O_CLOEXEC)
            self.assertEqual(opened.call_args.args[1]&(os.O_APPEND|os.O_TRUNC|os.O_CREAT),0)
            written.assert_called_once()
            fd,payload=written.call_args.args
            self.assertEqual(payload,data)
            closed.assert_called_once_with(fd)
            with self.assertRaises(OSError):os.fstat(fd)
            # A regular fixture has byte-offset semantics; the real seq-file
            # parses commands. Its untouched suffix detects destructive flags.
            self.assertEqual(events.read_bytes(),data+original[len(data):])

    def test_tracefs_short_or_failed_write_closes_fd_and_never_retries(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'uprobe_events').touch()
            command='-:owned/map_create\n';actual_close=os.close
            for fault in (0,len(command)-1,OSError(22,'kernel rejected command')):
                with self.subTest(fault=fault), \
                     patch.object(C.os,'write',**({'side_effect':fault} if isinstance(fault,Exception) else {'return_value':fault})) as written, \
                     patch.object(C.os,'close',wraps=actual_close) as closed:
                    with self.assertRaises((OSError,RuntimeError)):
                        C.write_uprobe_command(root,command)
                    written.assert_called_once()
                    fd=written.call_args.args[0]
                    closed.assert_called_once_with(fd)
                    with self.assertRaises(OSError):os.fstat(fd)
            with patch.object(C.os,'open') as opened:
                for fault in ('', 'missing newline', 'two\ncommands\n','X'*4096+'\n'):
                    with self.subTest(fault=fault),self.assertRaises(RuntimeError):
                        C.write_uprobe_command(root,fault)
                opened.assert_not_called()

    def test_unregister_write_failure_still_closes_owned_fd_and_attempts_unmount(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);probe=C.LowerBoundProbe([]);probe.root=root
            (root/'events'/probe.group/'map_create').mkdir(parents=True)
            (root/'trace_pipe').touch()
            fd=os.open(root/'trace_pipe',os.O_RDONLY);probe.fd=fd
            probe.registration_requested=True;probe.mounted=True
            previous=signal.getsignal(signal.SIGTERM);probe.old_sigterm=previous
            with patch.object(C,'write_uprobe_command',side_effect=OSError(22,'unregister failed')) as written, \
                 patch.object(C.subprocess,'run') as run, \
                 patch.object(C.os.path,'ismount',return_value=True), \
                 self.assertRaisesRegex(RuntimeError,'cleanup failed.*unregister failed'):
                probe.__exit__(None,None,None)
            written.assert_called_once_with(root,'-:'+probe.group+'/map_create\n')
            run.assert_called_once_with(['umount',str(root)],check=True,timeout=15)
            self.assertIsNone(probe.fd)
            with self.assertRaises(OSError):os.fstat(fd)
            self.assertEqual(signal.getsignal(signal.SIGTERM),previous)
            self.assertFalse(hasattr(probe,'old_sigterm'))

    def test_kernel_timestamp_identity_and_precision_are_literal(self):
        ident = '0123456789abcdef'*2
        for fraction, expected, resolution in [('123456789', 123456789, 1), ('123456', 123456000, 1000)]:
            line = f' mango-234 [001] d... 99.{fraction}: map_create: (0x7ffff123 <- 0x7ffff456) foreign_id="{ident}"'
            event = C.trace_receipt(line, 234)
            self.assertEqual(event['foreign_toplevel_id'], ident)
            self.assertEqual(event['kernel_text_monotonic_ns'], 99_000_000_000+expected)
            self.assertEqual(event['kernel_timestamp_text'],'99.'+fraction)
            self.assertEqual(event['lower_monotonic_ns'], 99_000_000_000+expected-resolution)
            self.assertEqual(event['timestamp_rounding_allowance_ns'],resolution)
            self.assertEqual(event['timestamp_resolution_ns'], resolution)
        for fault in [line.replace('mango-234', 'mango-235'), line.replace(ident,'fault'),
                      line.replace('.123456:', '.1234567890:'), line.replace('map_create:', 'other:')]:
            with self.subTest(fault=fault), self.assertRaises(RuntimeError): C.trace_receipt(fault,234)

    def test_linux_rounded_microsecond_text_is_always_a_conservative_lower(self):
        ident='a'*32
        # Linux ns2usecs() adds500 then divides1000. Exercise both sides of
        # rounding and second rollover; direct parsed text is too late for the
        # first half of each unit and cannot be used as a causal lower bound.
        for base in (99_123_456_000,99_999_999_000,100_000_000_000):
            for offset in (-500,-499,-1,0,1,499,500):
                actual=base+offset
                printed=((actual+500)//1000)*1000
                seconds,fraction=divmod(printed,1_000_000_000)
                line=f'mango-234 [001] d... {seconds}.{fraction//1000:06d}: map_create: foreign_id="{ident}"'
                event=C.trace_receipt(line,234)
                self.assertEqual(event['kernel_text_monotonic_ns'],printed)
                self.assertEqual(event['lower_monotonic_ns'],printed-1000)
                self.assertLessEqual(event['lower_monotonic_ns'],actual)

    @unittest.skipUnless(shutil.which('gcc'), 'gcc required for independent ELF fixture')
    def test_exported_real_elf_function_has_file_offset_and_absent_symbol_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'fixture.c').write_text('void *wlr_ext_foreign_toplevel_handle_v1_create(void *a, void *b) { return a; }\n')
            subprocess.run(['gcc','-shared','-fPIC',str(root/'fixture.c'),'-o',str(root/'fixture.so')],check=True)
            offset=C.elf_symbol_offset(root/'fixture.so')
            self.assertGreater(offset,0)
            self.assertLess(offset,(root/'fixture.so').stat().st_size)
            with self.assertRaisesRegex(RuntimeError,'exported causal'):C.elf_symbol_offset(root/'fixture.so','absent')
            raw=bytearray((root/'fixture.so').read_bytes());raw[4]=1
            (root/'bad.so').write_bytes(raw)
            with self.assertRaisesRegex(RuntimeError,'ELF64'):C.elf_symbol_offset(root/'bad.so')

    def test_loss_accounting_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);stats=root/'per_cpu/cpu0/stats';stats.parent.mkdir(parents=True)
            good='entries: 12\noverrun: 0\ncommit overrun: 0\ndropped events: 0\n'
            stats.write_text(good)
            self.assertEqual(C.loss_counts(root)['cpu0']['dropped events'],0)
            for bad in [good.replace('overrun: 0','overrun: 1',1),good.replace('dropped events: 0\n','')]:
                stats.write_text(bad)
                with self.assertRaises(RuntimeError):C.loss_counts(root)

    def test_bound_uses_matched_kernel_identity_without_changing_upper(self):
        probe=C.LowerBoundProbe([]);probe.pid=234;probe.proof={'method':C.METHOD}
        ident='a'*32
        probe.events[ident]=dict(foreign_toplevel_id=ident,lower_monotonic_ns=40_000_000,
                                timestamp_resolution_ns=1,kernel_pid=234)
        with patch.object(C,'loss_counts',return_value={'cpu0':{'overrun':0,'commit overrun':0,'dropped events':0}}):
            lower,proof=probe.bound([{'foreign_toplevel_id':ident}],10_000_000,41_000_000)
            self.assertEqual(lower,40_000_000)
            self.assertEqual(proof['matched_events'][0]['lower_monotonic_ns'],lower)
            for windows,start,upper in [([{'foreign_toplevel_id':'b'*32}],10_000_000,41_000_000),
                                        ([{'foreign_toplevel_id':ident}],40_000_001,41_000_000),
                                        ([{'foreign_toplevel_id':ident}],10_000_000,39_999_999),
                                        ([{'foreign_toplevel_id':ident},{'foreign_toplevel_id':ident}],10_000_000,41_000_000)]:
                with self.subTest(windows=windows,start=start,upper=upper),self.assertRaises(RuntimeError):
                    probe.bound(windows,start,upper,timeout=.001)

    def test_causal_receipt_cannot_relax_original_precision_limit(self):
        runs=R.paired_roles()
        bound=runs['candidate'][0]['startup_role_terminal_cold_seconds']['observation_bounds'][0]
        bound.clear();bound.update(R.causal_bound(.0389,.04))
        report=R.comparison.compare(runs)
        self.assertEqual(report['status'],'measurement_precision_gate_failed')
        check=report['measurement_precision']['checks']['candidate'][0][0]
        self.assertTrue(check['causal_lower_bound_valid'])
        self.assertFalse(check['valid'])
        self.assertEqual(check['maximum_interval_seconds'],.001)

    def test_missing_forged_lossy_or_wrong_launch_receipts_fail_qualification(self):
        original=R.paired_roles()
        for fault in ['missing','method','clock','pid','library','version','layout','loss','old_event','future_event','boolean_resolution','forged_lower','missing_literal','missing_allowance','boolean_literal','boolean_allowance','zero_allowance','short_allowance','unsubtracted_display','missing_text','malformed_text','text_literal_mismatch']:
            runs=copy.deepcopy(original)
            bound=runs['candidate'][0]['startup_role_terminal_cold_seconds']['observation_bounds'][0]
            proof=bound['causal_lower_bound']
            if fault=='missing':bound.pop('causal_lower_bound')
            elif fault=='method':proof['method']='arrival-is-exact'
            elif fault=='clock':proof['clock']='local'
            elif fault=='pid':proof['matched_events'][0]['kernel_pid']+=1
            elif fault=='library':proof['library_sha256']='unknown'
            elif fault=='version':proof['library_rpm']='wlroots-0.20.3-1.fc44.x86_64'
            elif fault=='layout':proof['identifier_offset']=64
            elif fault=='loss':proof['loss_counts']['cpu0']['overrun']=1
            elif fault=='old_event':proof['matched_events'][0]['lower_monotonic_ns']=1
            elif fault=='future_event':proof['matched_events'][0]['lower_monotonic_ns']=2_000_000_000
            elif fault=='boolean_resolution':proof['matched_events'][0]['timestamp_resolution_ns']=True
            elif fault=='missing_literal':proof['matched_events'][0].pop('kernel_text_monotonic_ns')
            elif fault=='missing_allowance':proof['matched_events'][0].pop('timestamp_rounding_allowance_ns')
            elif fault=='boolean_literal':proof['matched_events'][0]['kernel_text_monotonic_ns']=True
            elif fault=='boolean_allowance':proof['matched_events'][0]['timestamp_rounding_allowance_ns']=True
            elif fault=='zero_allowance':proof['matched_events'][0]['timestamp_rounding_allowance_ns']=0
            elif fault=='short_allowance':proof['matched_events'][0]['timestamp_rounding_allowance_ns']=500
            elif fault=='unsubtracted_display':proof['matched_events'][0]['kernel_text_monotonic_ns']=proof['matched_events'][0]['lower_monotonic_ns']
            elif fault=='missing_text':proof['matched_events'][0].pop('kernel_timestamp_text')
            elif fault=='malformed_text':proof['matched_events'][0]['kernel_timestamp_text']='10.999e-3'
            elif fault=='text_literal_mismatch':proof['matched_events'][0]['kernel_timestamp_text']='10.999000'
            else:bound['lower_seconds']+=.0001;bound['interval_seconds']-=.0001
            with self.subTest(fault=fault):
                report=R.comparison.compare(runs)
                self.assertEqual(report['status'],'measurement_precision_gate_failed')
                self.assertFalse(report['measurement_precision']['valid'])

    def test_six_digit_kernel_text_cannot_claim_nanosecond_precision(self):
        runs=R.paired_roles()
        bound=runs['candidate'][0]['startup_role_terminal_cold_seconds']['observation_bounds'][0]
        event=bound['causal_lower_bound']['matched_events'][0]
        self.assertEqual(len(event['kernel_timestamp_text'].split('.')[1]),6)
        self.assertTrue(R.comparison.causal_precision(bound))
        event['timestamp_resolution_ns']=event['timestamp_rounding_allowance_ns']=1
        event['lower_monotonic_ns']=event['kernel_text_monotonic_ns']-1
        bound['lower_seconds']=(event['lower_monotonic_ns']-bound['launch_started_monotonic_ns'])/1e9
        bound['interval_seconds']=bound['upper_seconds']-bound['lower_seconds']
        self.assertFalse(R.comparison.causal_precision(bound))
        self.assertEqual(R.comparison.compare(runs)['status'],'measurement_precision_gate_failed')

    def test_old_sampler_remains_unqualified_in_new_role_lane(self):
        runs=R.paired_roles()
        for run in runs['candidate']:run['identity']['sampler']='cpu-30-pss-6-v8-autonomous-role-first-use'
        with self.assertRaises(ValueError):R.comparison.compare(runs)

    def test_mixed_adjusted_and_raw_clock_evidence_cannot_pass(self):
        for fault in ('timing','bound','kernel','userspace','observer'):
            runs=R.paired_roles()
            timing=runs['candidate'][0]['startup_role_terminal_cold_seconds']
            bound=timing['observation_bounds'][0]
            if fault=='timing':timing['clock']='CLOCK_MONOTONIC'
            elif fault=='bound':bound['clock']='CLOCK_MONOTONIC'
            elif fault=='kernel':bound['causal_lower_bound']['clock']='mono'
            elif fault=='userspace':bound['causal_lower_bound']['userspace_clock']='CLOCK_MONOTONIC'
            else:timing['observer']=bound['observer']='mango-socket-worker-v2-autonomous'
            with self.subTest(fault=fault):
                self.assertEqual(R.comparison.compare(runs)['status'],'measurement_precision_gate_failed')
        runs=R.paired_roles()
        for run in runs['candidate']:run['identity']['sampler']='cpu-30-pss-6-v9-causal-role-first-use'
        with self.assertRaises(ValueError):R.comparison.compare(runs)

    def test_host_cannot_activate_root_tracing(self):
        with self.assertRaisesRegex(RuntimeError,'disposable root collector'):
            with C.LowerBoundProbe([]):pass

    def test_cleanup_failure_still_disables_unregisters_and_attempts_owned_unmount(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            probe=C.LowerBoundProbe([]);probe.root=root;probe.instance=root/'owned';probe.instance.mkdir()
            (root/'uprobe_events').write_text('')
            (probe.instance/'tracing_on').write_text('1')
            event=probe.instance/'events'/probe.group/'map_create/enable';event.parent.mkdir(parents=True)
            event.write_text('1')
            stats=probe.instance/'per_cpu/cpu0/stats';stats.parent.mkdir(parents=True)
            stats.write_text('overrun: 0\ncommit overrun: 0\ndropped events: 0\n')
            (root/'events'/probe.group/'map_create').mkdir(parents=True)
            probe.instance_created=True;probe.registered=True;probe.mounted=True
            # Ordinary fixture directories deliberately cannot be removed while
            # nonempty, modeling failed instance cleanup without host tracing.
            with patch.object(C.subprocess,'run') as run, patch.object(C.os.path,'ismount',return_value=True), self.assertRaisesRegex(RuntimeError,'cleanup failed'):
                probe.__exit__(None,None,None)
            self.assertEqual((probe.instance/'tracing_on').read_text(),'0')
            self.assertEqual(event.read_text(),'0')
            self.assertEqual((root/'uprobe_events').read_text(),'-:'+probe.group+'/map_create\n')
            run.assert_called_once_with(['umount',str(root)],check=True,timeout=15)

    def test_cancellation_is_delivered_after_resource_ownership_handoff(self):
        state={}
        previous=signal.getsignal(signal.SIGTERM)
        def interrupted(signum,frame):
            self.assertTrue(state.get('owned'))
            raise InterruptedError('termination after handoff')
        signal.signal(signal.SIGTERM,interrupted)
        try:
            with self.assertRaisesRegex(InterruptedError,'after handoff'):
                with C.deferred_termination():
                    os.kill(os.getpid(),signal.SIGTERM)
                    state['owned']=True
        finally:
            signal.signal(signal.SIGTERM,previous)

    def test_collector_worker_inherits_blocked_process_cancellation(self):
        masks=[]
        def worker():masks.append(signal.pthread_sigmask(signal.SIG_BLOCK,set()))
        with C.deferred_termination():
            thread=threading.Thread(target=worker);thread.start()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertTrue({signal.SIGTERM,signal.SIGINT}<=masks[0])

    def test_repeat_termination_during_join_cannot_skip_owned_event_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);probe=C.LowerBoundProbe([]);probe.root=root
            (root/'events'/probe.group/'map_create').mkdir(parents=True)
            (root/'uprobe_events').write_text('')
            probe.registration_requested=True;probe.mount_requested=True
            class Reader:
                def join(self,timeout):os.kill(os.getpid(),signal.SIGTERM)
                def is_alive(self):return False
            probe.thread=Reader()
            previous=signal.getsignal(signal.SIGTERM)
            def interrupted(signum,frame):raise InterruptedError('repeat termination after unwind')
            signal.signal(signal.SIGTERM,interrupted);probe.old_sigterm=interrupted
            try:
                with patch.object(C.subprocess,'run') as run, patch.object(C.os.path,'ismount',return_value=True), self.assertRaisesRegex(InterruptedError,'after unwind'):
                    probe.__exit__(None,None,None)
                self.assertEqual((root/'uprobe_events').read_text(),'-:'+probe.group+'/map_create\n')
                run.assert_called_once_with(['umount',str(root)],check=True,timeout=15)
            finally:
                signal.signal(signal.SIGTERM,previous)


if __name__=='__main__':unittest.main()
