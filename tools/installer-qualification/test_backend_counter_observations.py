"""Real collector counter-source correction and fatal bounded observations."""
import contextlib
import io
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import test_collection_guard_diagnostics as Existing
C,D,R,PRIVATE,TOKEN=Existing.C,Existing.D,Existing.R,Existing.PRIVATE,Existing.TOKEN

class BackendCounterControls(unittest.TestCase):
    def fixture(self, out, growth=(0, 0), *, mutation=None, running=True, query_error=None, exited=False):
        requests=[]; samples=[]
        def query(vm, name, arguments=None):
            requests.append((name, arguments))
            if name=='query-status':
                if query_error is not None: raise query_error
                return {'running':running}
            if name=='query-block':
                rows=[{'device':'active_target','inserted':{'node-name':'target0','file':str(out/'target.qcow2'),'ro':False}}]
            elif name=='query-blockstats':
                # Official 10.2.2/11.0.0 behavior: node queries never fill the
                # two frontend accounting counters even while backend writes.
                current=len(samples);samples.append(current)
                amount=growth if current else (0,0)
                if arguments=={'query-nodes':True}: amount=(0,0)
                rows=[{'device':'active_target','node-name':'target0',
                       'stats':{'wr_bytes':amount[0],'wr_operations':amount[1]}}]
            else: raise AssertionError('Unexpected query')
            if mutation is not None: rows=mutation(name,rows)
            return rows
        control=Existing.CollectionControls().controller(out,query)
        control.vm.proc.poll=lambda:7 if exited else None
        return control,requests

    def run_gate(self, control, *, clock=(1,2), timed_out=False):
        with patch.object(C.time,'monotonic',side_effect=(0,0,0,21) if timed_out else (0,0,0)), \
                patch.object(C.time,'monotonic_ns',side_effect=clock), \
                patch.object(C.time,'sleep') as sleep:
            try:
                result=control.active_write_proof()
            except RuntimeError as error:
                return None,error,sleep.call_args_list
        return result,None,sleep.call_args_list

    def test_real_collector_uses_owned_backend_counters_under_same_deadlines(self):
        with tempfile.TemporaryDirectory() as temp:
            control,requests=self.fixture(Path(temp),(4096,1))
            result,error,sleeps=self.run_gate(control)
            self.assertIsNone(error)
            self.assertEqual(result['after']['wr_bytes'],4096)
            self.assertEqual(result['after']['wr_operations'],1)
            self.assertEqual(result['node_name'],'target0')
            self.assertEqual(result['write_bps'],8*1024**2)
            self.assertEqual(control.display.deadline,22)
            self.assertEqual([x.args for x in sleeps],[(.5,)])
            self.assertEqual([args for name,args in requests if name=='query-blockstats'],
                [{'query-nodes':False},{'query-nodes':False}])
            self.assertNotIn(('query-status',None),requests)

    def test_actual_sample_rejects_foreign_backend_duplicate_target_and_private_file(self):
        for name,field,value,expected in (
                ('query-block','device','foreign','032'),
                ('query-block','file',PRIVATE,'032'),
                ('query-block','ro',True,'032'),
                ('query-blockstats','device','foreign','033'),
                ('query-blockstats','wr_bytes',True,'033'),
                ('query-blockstats','wr_operations',-1,'033')):
            with self.subTest(name=name,field=field),tempfile.TemporaryDirectory() as temp:
                def mutate(command,rows):
                    if command==name:
                        node=rows[0]['inserted']if field in ('file','ro')else rows[0]['stats']if field in ('wr_bytes','wr_operations')else rows[0]
                        node[field]=value
                    return rows
                control,requests=self.fixture(Path(temp),(4096,1),mutation=mutate)
                result,error,_=self.run_gate(control)
                self.assertIsNone(result)
                self.assertEqual(D.diagnostic_code('driver-collect',error,C),
                    'installer-inner-driver-collect-guard-collection-'+expected)
                self.assertNotIn('_arctic_installer_write_observation',error.__dict__)
                self.assertEqual(control.receipts,[])
        for name in ('query-block','query-blockstats'):
            with self.subTest(duplicate=name),tempfile.TemporaryDirectory() as temp:
                def mutate(command,rows):return rows+rows if command==name else rows
                control,_=self.fixture(Path(temp),(4096,1),mutation=mutate)
                _,error,_=self.run_gate(control)
                self.assertIn('collection-'+('032'if name=='query-block'else'033'),D.diagnostic_code('driver-collect',error,C))
            for extra in ({'device':'active_target'}, {'device':'active_target','node-name':'foreign',
                    'inserted':{'node-name':'foreign','file':PRIVATE,'ro':False},
                    'stats':{'wr_bytes':0,'wr_operations':0}}):
                with self.subTest(extra=extra,name=name),tempfile.TemporaryDirectory() as temp:
                    def mutate(command,rows):return rows+[extra] if command==name else rows
                    control,_=self.fixture(Path(temp),(4096,1),mutation=mutate)
                    _,error,_=self.run_gate(control)
                    self.assertIn('collection-'+('032'if name=='query-block'else'033'),D.diagnostic_code('driver-collect',error,C))
                    self.assertEqual(control.receipts,[])

    def test_growth_failure_keeps_original_guard_and_each_closed_operand(self):
        for growth,clock,expected,timed_out in (
                ((0,0),(1,2),('false','false','true'),True),
                ((4096,0),(1,2),('true','false','true'),True),
                ((0,1),(1,2),('false','true','true'),True),
                ((4096,1),(1,1),('true','true','false'),False)):
            with self.subTest(growth=growth,clock=clock),tempfile.TemporaryDirectory() as temp:
                control,_=self.fixture(Path(temp),growth)
                result,error,sleeps=self.run_gate(control,clock=clock,timed_out=timed_out)
                self.assertIsNone(result)
                self.assertEqual(error.args,('genuine target writes did not continue during disruption',))
                self.assertEqual(D.diagnostic_code('driver-collect',error,C),'installer-inner-driver-collect-guard-collection-034')
                codes=D.write_observation_codes(error,C)
                self.assertEqual(tuple(code.rsplit('-',1)[1]for code in codes[:3]),expected)
                self.assertEqual(codes[3:],(
                    'installer-inner-driver-collect-write-vm-running',
                    'installer-inner-driver-collect-write-phase-vt-away',
                    'installer-inner-driver-collect-write-cycle-zero'))
                self.assertEqual(control.display.deadline,22)
                self.assertEqual([x.args for x in sleeps],[(.5,)])
                self.assertEqual(control.receipts,[])

    def test_status_failure_and_source_phase_are_bounded_without_private_values(self):
        for index,running,exited,query_error,status,phase in (
                (0,False,False,None,'not-running','vt-away'),
                (1,True,False,None,'running','output-disconnect'),
                (2,True,False,RuntimeError(PRIVATE),'unknown','output-restore'),
                (3,True,True,None,'process-exited','unknown')):
            with self.subTest(index=index),tempfile.TemporaryDirectory() as temp:
                control,requests=self.fixture(Path(temp),running=running,exited=exited,query_error=query_error)
                control.position=index
                _,error,_=self.run_gate(control,timed_out=True)
                codes=D.write_observation_codes(error,C)
                self.assertIn('installer-inner-driver-collect-write-vm-'+status,codes)
                self.assertIn('installer-inner-driver-collect-write-phase-'+phase,codes)
                self.assertIn('installer-inner-driver-collect-write-cycle-'+('unknown'if index==3 else'zero'),codes)
                stream=io.StringIO()
                with patch.dict(os.environ,{'ARCTIC_INSTALLER_DIAGNOSTIC_TOKEN':TOKEN}),contextlib.redirect_stdout(stream):
                    D.diagnose('driver-collect',error,C)
                self.assertNotIn(PRIVATE,stream.getvalue())
                self.assertEqual(R.inner_codes(stream.getvalue().encode(),TOKEN),
                    ('installer-inner-driver-collect-guard-collection-034',*codes))
                if exited:self.assertNotIn(('query-status',None),requests)

    def test_optional_observer_and_stdout_failures_preserve_original_primary(self):
        for failure in (RuntimeError(PRIVATE),TypeError(PRIVATE),OSError(PRIVATE)):
            with tempfile.TemporaryDirectory() as temp:
                control,_=self.fixture(Path(temp))
                with patch.object(C,'_observe_write_failure',side_effect=failure):
                    _,error,_=self.run_gate(control,timed_out=True)
                self.assertEqual(error.args,('genuine target writes did not continue during disruption',))
                self.assertEqual(D.diagnostic_code('driver-collect',error,C),'installer-inner-driver-collect-guard-collection-034')
                with patch.dict(os.environ,{'ARCTIC_INSTALLER_DIAGNOSTIC_TOKEN':TOKEN}),patch('builtins.print',side_effect=failure):
                    D.diagnose('driver-collect',error,C)
                self.assertEqual(error.args,('genuine target writes did not continue during disruption',))
        for cancellation in (KeyboardInterrupt(PRIVATE),SystemExit(PRIVATE)):
            with tempfile.TemporaryDirectory() as temp:
                control,_=self.fixture(Path(temp))
                with patch.object(C,'_observe_write_failure',side_effect=cancellation),self.assertRaises(type(cancellation)) as caught:
                    self.run_gate(control,timed_out=True)
                self.assertIs(caught.exception,cancellation)

    def test_forged_or_hostile_observations_never_read_or_export_private_values(self):
        class Hostile(str):
            def __eq__(self,*_):raise AssertionError('private comparison')
        error=RuntimeError(PRIVATE)
        error._arctic_installer_collection_guard=(C._COLLECTION_GUARD_TOKEN,Hostile('collection-034'))
        C._observe_write_failure(error,{}, {},None,None,[],0)
        self.assertNotIn('_arctic_installer_write_observation',error.__dict__)
        error._arctic_installer_collection_guard=(C._COLLECTION_GUARD_TOKEN,'collection-034')
        for observation in ((object(),'false','false','true','running','vt-away','zero'),
                (C._COLLECTION_GUARD_TOKEN,Hostile('false'),'false','true','running','vt-away','zero'),
                (C._COLLECTION_GUARD_TOKEN,'false','false','true',PRIVATE,'vt-away','zero'),
                (C._COLLECTION_GUARD_TOKEN,'false','false','true','running','vt-away')):
            error._arctic_installer_write_observation=observation
            self.assertEqual(D.write_observation_codes(error,C),())
        for label in D.DIAGNOSTIC_CODES:
            if '-collect-write-'in label:self.assertNotIn(PRIVATE,label)

if __name__=='__main__':unittest.main()
