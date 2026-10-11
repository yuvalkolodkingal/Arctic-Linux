"""Fail-only loaded code observations; no target programs, VM or cause verdict."""
import ast
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import test_performance_failure_phase as P
import performance_loaded_failure_fixture as L

C = P.F.contract


class LoadedCodeHookTest(unittest.TestCase):
    def install(self, source, namespace=None):
        namespace = {} if namespace is None else namespace
        code = compile(source, 'guest-check.py', 'exec')
        exec(code, namespace)
        helper = {}; exec(C.FAILURE_OBSERVATION_HELPER, helper)
        self.original = sys.excepthook
        self.addCleanup(setattr, sys, 'excepthook', self.original)
        self.delegated = []
        sys.excepthook = lambda *args: self.delegated.append(args)
        class StoreProofError(RuntimeError): pass
        helper['install']((('guest', code),), StoreProofError, 'a'*64)
        return namespace, StoreProofError

    def observe(self, action, kind=None):
        try: action()
        except BaseException as error:
            original = error.__traceback__
            output = io.StringIO()
            with contextlib.redirect_stdout(output): sys.excepthook(type(error) if kind is None else kind, error, original)
            self.assertIs(self.delegated[-1][1], error)
            self.assertIs(self.delegated[-1][2], original)
        else: self.fail('Fixture must raise its real exception')
        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0].removeprefix('ARCTIC-PERFORMANCE '))
        self.assertEqual(set(record), {'stage', 'check', 'value'})
        self.assertEqual(record['check'], 'failure_observation')
        self.assertEqual(record['stage'], 'installed')
        self.assertEqual(record['value']['source_sha256'], 'a'*64)
        return record['value']

    def test_real_builtin_exceptions_have_exact_loaded_code_coordinates(self):
        for expression, name in (("1 + 'secret'", 'TypeError'), ('absent_private_name', 'NameError'),
                ('1 / 0', 'ZeroDivisionError'), ("{}['password']", 'KeyError')):
            namespace, _ = self.install('def fail():\n    return '+expression+'\n')
            result = self.observe(namespace['fail'])
            self.assertEqual(result, dict(schema='arctic-loaded-failure-observation-v1',
                exception_class=name, domain='guest', site='guest_2', phase='fail', relation='leaf', source_sha256='a'*64))
            self.assertNotIn('secret', json.dumps(result))

    def test_same_filename_name_and_lines_from_foreign_code_are_not_loaded_identity(self):
        source="def fail():\n    raise TypeError('private')\n"
        namespace, _ = self.install(source)
        foreign={};exec(compile(source, 'guest-check.py', 'exec'), foreign)
        result=self.observe(foreign['fail'])
        self.assertEqual((result['domain'],result['site'],result['phase'],result['relation']),
            ('none','none','unavailable','none'))
        clone=types.FunctionType(namespace['fail'].__code__.replace(), {})
        self.assertEqual(self.observe(clone)['domain'],'none')

    def test_foreign_leaf_is_explicit_ancestor_not_original_cause(self):
        def foreign(): raise NameError('private')
        namespace,_=self.install('def fail():\n    foreign()\n', dict(foreign=foreign))
        result=self.observe(namespace['fail'])
        self.assertEqual((result['site'],result['phase'],result['relation']),('guest_2','fail','ancestor'))

    def test_subclasses_and_hostile_rendering_are_never_read(self):
        class Hostile(TypeError):
            def __str__(self): raise AssertionError('rendering forbidden')
            def __repr__(self): raise AssertionError('rendering forbidden')
            @property
            def args(self): raise AssertionError('arguments forbidden')
        namespace,_=self.install('def fail():\n    raise problem\n',dict(problem=Hostile('secret')))
        self.assertEqual(self.observe(namespace['fail'])['exception_class'],'unsupported')
        namespace,_=self.install('def fail():\n    raise TypeError("secret")\n')
        self.assertEqual(self.observe(namespace['fail'],NameError)['exception_class'],'unsupported')

    def test_store_class_exact_identity_and_keyboard_interrupt_preserve_delegate(self):
        namespace,store=self.install('def fail():\n    raise problem\n')
        for error,label in ((store('private'),'StoreProofError'), (KeyboardInterrupt('private'),'KeyboardInterrupt')):
            namespace['problem']=error
            self.assertEqual(self.observe(namespace['fail'])['exception_class'],label)

    def test_emission_failure_still_delegates_original_exception(self):
        namespace,_=self.install('def fail():\n    raise NameError("private")\n')
        class Broken:
            def write(self, value): raise OSError('private')
            def flush(self): raise OSError('private')
        try: namespace['fail']()
        except NameError as error:
            tb=error.__traceback__
            with contextlib.redirect_stdout(Broken()): sys.excepthook(type(error),error,tb)
            self.assertEqual(len(self.delegated),1)
            self.assertIs(self.delegated[0][1],error);self.assertIs(self.delegated[0][2],tb)

    def test_bounded_traceback_clears_coordinate_instead_of_truncating_cause(self):
        namespace,_=self.install('def fail(n):\n    if n: return fail(n-1)\n    raise TypeError("private")\n')
        result=self.observe(lambda: namespace['fail'](130))
        self.assertEqual((result['domain'],result['site'],result['relation']),('none','none','none'))

    def test_real_current_source_function_code_is_observed_without_target_execution(self):
        raw=(P.ROOT/'tools/performance/causal.py').read_bytes(); code=compile(raw,'guest-check.py','exec')
        module=dict(__file__='guest-check.py',__name__='owned_static_causal');exec(code,module)
        helper={};exec(C.FAILURE_OBSERVATION_HELPER,helper)
        self.original=sys.excepthook;self.addCleanup(setattr,sys,'excepthook',self.original)
        self.delegated=[];sys.excepthook=lambda *args:self.delegated.append(args)
        helper['install']((('causal',code),),module['StoreProofError'],'a'*64)
        result=self.observe(lambda:module['mapping_profile'](types.SimpleNamespace(read_bytes=lambda:b'not ELF')))
        self.assertEqual((result['domain'],result['site'],result['phase']),('causal','causal_87','mapping_profile'))

    def test_composer_contract_and_original_entry_line_are_exact(self):
        guest=(P.ROOT/'tools/performance/guest.py').read_bytes();causal=(P.ROOT/'tools/performance/causal.py').read_bytes()
        content=C.frozen_observer_bytes(guest,causal)
        self.assertLessEqual(len(content),131072)
        self.assertEqual(content.splitlines()[10],b'    measurement["main"](preconditioned=True, causal_precision=True)')
        self.assertEqual(len(content.splitlines()),13)
        self.assertEqual(hashlib.sha256(content).hexdigest(),L.FROZEN.decode())
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'observer.py'
            subprocess.run([sys.executable,'-B',str(P.ROOT/'tools/performance/compose-paired-probe.py'),str(target)],check=True,timeout=8)
            self.assertEqual(target.read_bytes(),content)
        namespace={};exec(C.FAILURE_OBSERVATION_HELPER,namespace)
        self.assertNotIn('repr',C.FAILURE_OBSERVATION_HELPER);self.assertNotIn('.args',C.FAILURE_OBSERVATION_HELPER)

    def test_real_composed_success_and_systemexit_preserve_original_exit(self):
        causal=b'class StoreProofError(RuntimeError): pass\n'
        for body,code in (('print("WORKLOAD-ONCE")',0),('raise SystemExit(7)',7)):
            guest=('def emit(check,value): pass\ndef main(**kwargs):\n    '+body+'\n').encode()
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'observer.py';path.write_bytes(C.frozen_observer_bytes(guest,causal))
                result=subprocess.run([sys.executable,'-B',str(path),'installed'],capture_output=True,timeout=8)
            self.assertEqual(result.returncode,code)
            self.assertNotIn(b'failure_observation',result.stdout)
            self.assertEqual(result.stdout,b'WORKLOAD-ONCE\n' if code==0 else b'')

    def test_real_composed_failure_emits_after_original_cleanup_before_default_hook(self):
        causal=b'class StoreProofError(RuntimeError): pass\n'
        guest=(b'def emit(check,value): pass\ndef main(**kwargs):\n'
            b'    try: 1 + "private operand"\n    finally: print("OWNED-CLEANUP-ONCE",flush=True)\n')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'observer.py';path.write_bytes(C.frozen_observer_bytes(guest,causal))
            result=subprocess.run([sys.executable,'-B',str(path),'installed'],capture_output=True,timeout=8)
        self.assertEqual(result.returncode,1)
        self.assertTrue(result.stdout.startswith(b'OWNED-CLEANUP-ONCE\nARCTIC-PERFORMANCE '))
        self.assertEqual(result.stdout.count(b'failure_observation'),1)
        self.assertNotIn(b'private operand',result.stdout)
        record=json.loads(result.stdout.splitlines()[1].removeprefix(b'ARCTIC-PERFORMANCE '))['value']
        self.assertEqual((record['exception_class'],record['site'],record['phase'],record['relation']),
            ('TypeError','guest_3','main','leaf'))
        self.assertIn(b'Traceback (most recent call last):',result.stderr)
        self.assertIn(b'line 11, in <module>',result.stderr)


class LoadedFailureReaderTest(unittest.TestCase):
    def setUp(self):
        self.fixture=P.FixedFailurePhaseTest('runTest');self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.fixture.prepare_guest()
        self.observation=dict(schema='arctic-loaded-failure-observation-v1',exception_class='TypeError',
            domain='guest',site='guest_360',phase='desktop',relation='leaf',
            source_sha256=self.fixture.observer['source_sha256'])

    def trace(self, observation=None):
        trace=self.fixture.guest_trace().replace('RuntimeError: No unique non-root Mango session','PrivateError: secret')
        record=self.fixture.guest_record('failure_observation',self.observation if observation is None else observation)
        return trace.replace('Traceback (most recent call last):',record+'Traceback (most recent call last):')

    def summary(self, trace):
        path=self.fixture.work/'runs/baseline/1/serial-boot.log';path.write_bytes(trace.encode() if type(trace) is str else trace)
        return self.fixture.summary()

    def consumer(self,result):
        target=self.fixture.root/'screened'
        if target.exists(): shutil.rmtree(target)
        with patch.object(P.inner,'failure_phase_summary',return_value=result):self.fixture.export(target)
        return (target/'unqualified-failure-phase.json').read_bytes()

    def test_exact_record_is_separate_unqualified_projection_of_pinned_source(self):
        result=self.summary(self.trace());out=result['guest_envelope']['loaded_failure']
        self.assertEqual(out,dict(status='source_code_observed',exception_class='TypeError',domain='guest',
            site='guest_360',phase='desktop',relation='leaf'))
        self.assertEqual(result['guest_failure']['status'],'unknown')
        self.assertFalse(result['performance_acceptance']);self.assertFalse(result['release_acceptance'])
        raw=self.consumer(result);self.assertLessEqual(len(raw),4096)
        for private in (b'secret',b'private.invalid',b'guest-check.py',b'password='):self.assertNotIn(private,raw)

    def test_closed_class_without_loaded_source_is_label_only(self):
        observation=dict(self.observation,domain='none',site='none',phase='unavailable',relation='none',exception_class='unsupported')
        result=self.summary(self.trace(observation));self.assertEqual(result['guest_envelope']['loaded_failure']['status'],'class_observed')
        self.consumer(result);self.assertEqual(result['guest_failure']['status'],'unknown')

    def test_unknown_fields_types_classes_scopes_and_identities_fail_closed(self):
        for key, value in (('exception_class','private.TypeError'),('phase','private'),('phase','desktop\x07'),
                ('site','guest_0360'),('site','guest_9999'),('site','causal_360'),('source_sha256','a'*64),
                ('relation','cause'),('domain','private'),('site',True),('schema','other'),('private','secret')):
            result=self.summary(self.trace(dict(self.observation,**{key:value})))
            self.assertEqual(result['guest_envelope']['loaded_failure']['status'],'invalid')
            self.assertEqual(result['guest_failure']['status'],'unknown')
            self.consumer(result)

    def test_duplicate_order_outside_collector_and_missing_observer_are_not_observed(self):
        valid=self.trace();record=self.fixture.guest_record('failure_observation',self.observation)
        observer=self.fixture.guest_record('observer_source_sha256',self.fixture.observer['source_sha256'])
        for trace,status in ((valid.replace(record,record+record),'ambiguous'),
                (valid.replace(record,'').replace(observer,record+observer),'invalid'),
                (record+valid.replace(record,''),'unavailable'),(valid.replace(observer,''),'invalid')):
            self.assertEqual(self.summary(trace)['guest_envelope']['loaded_failure']['status'],status)

    def test_duplicate_json_oversize_and_truncated_records_cannot_export_source_projection(self):
        valid=self.trace();record=self.fixture.guest_record('failure_observation',self.observation)
        for malformed in (record.replace('"value": {','"value": {}, "value": {',1),
                record.replace('"TypeError"','"'+('x'*4096)+'"'),record[:-2]+'\n'):
            result=self.summary(valid.replace(record,malformed))
            self.assertNotIn(result['guest_envelope']['loaded_failure']['status'],
                {'source_code_observed','class_observed'})
            self.consumer(result)

    def test_original_owner_source_utf8_frozen_and_exit_gates_remain_strict(self):
        valid=self.trace();path=P.inner.ROOT/'tools/performance/guest.py';old=path.read_bytes()
        path.write_bytes(old+b'\n# change\n')
        try:self.assertEqual(self.summary(valid)['guest_envelope']['loaded_failure']['status'],'unavailable')
        finally:path.write_bytes(old)
        for trace in (valid.encode()+b'\xff\n',valid[:-1],valid.replace('SMOKE-EXIT=1','SMOKE-EXIT=0')):
            self.assertEqual(self.summary(trace)['guest_envelope']['loaded_failure']['status'],'unavailable')
        frozen=self.fixture.work/'frozen-observer.py';old=frozen.read_bytes();frozen.write_bytes(old+b'\n')
        self.assertEqual(self.summary(valid)['guest_envelope']['loaded_failure']['status'],'unavailable');frozen.write_bytes(old)
        real=P.os.fstat
        def wrong(fd):
            stat=real(fd);fields=list(stat);fields[4]=P.os.geteuid()+1;return P.os.stat_result(fields)
        with patch.object(P.inner.os,'fstat',side_effect=wrong):
            self.assertEqual(self.summary(valid)['guest_envelope']['loaded_failure']['status'],'unavailable')

    def test_consumer_rejects_open_fields_inconsistent_prerequisites_and_source_scope(self):
        original=self.summary(self.trace());self.consumer(original)
        for fault in ('class','site','phase','relation','extra','owner','observer','exit','order'):
            result=copy.deepcopy(original);out=result['guest_envelope']['loaded_failure']
            if fault=='class':out['exception_class']='PrivateError'
            elif fault=='site':out['site']='guest_9999'
            elif fault=='phase':out['phase']='private'
            elif fault=='relation':out['relation']='cause'
            elif fault=='extra':out['operand']='private'
            elif fault=='owner':result['private_owner_verified']=False
            elif fault=='observer':result['guest_envelope']['counts']['admitted_observer_records']='zero'
            elif fault=='exit':result['smoke_exit']='zero'
            else:result['guest_envelope']['collector_order']='invalid'
            with self.assertRaises(ValueError):self.consumer(result)

    def test_consumer_rejects_substituted_source_symlink_fifo_bytes_and_fd_race(self):
        result=self.summary(self.trace())
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);target=root/'tools/performance/guest.py';target.parent.mkdir(parents=True)
            original=(P.ROOT/'tools/performance/guest.py').read_bytes()
            private=root/'private';private.write_bytes(original)
            for fault in ('symlink','fifo','bytes','race'):
                if target.exists() or target.is_symlink():target.unlink()
                if fault=='symlink':target.symlink_to(private)
                elif fault=='fifo':os.mkfifo(target)
                else:target.write_bytes(original if fault=='race' else original+b'\n')
                with patch.object(P.outer,'ROOT',root):
                    if fault!='race':
                        with self.assertRaises(ValueError):self.consumer(result)
                    else:
                        real=P.outer.os.fstat;calls=[]
                        def changed(fd):
                            info=real(fd);calls.append(fd)
                            if len(calls)==2:
                                fields=list(info);fields[6]+=1;return os.stat_result(fields)
                            return info
                        with patch.object(P.outer.os,'fstat',side_effect=changed),self.assertRaises(ValueError):
                            self.consumer(result)
                self.assertFalse((self.fixture.root/'screened').exists())

    def test_original_reader_and_consumer_whole_bytes_are_exactly_reversible(self):
        L.reader_before_projection((P.ROOT/'tools/performance/run-paired.py').read_bytes())
        L.consumer_before_projection((P.ROOT/'tools/performance/qualification.py').read_bytes())
