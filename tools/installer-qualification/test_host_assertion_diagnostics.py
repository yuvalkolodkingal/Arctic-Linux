"""Closed host assertion identities; original gates and error text stay intact."""
import ast
import copy
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).parent))
import runner as R
import test_contract as F
import test_active_contract as AF

PRIVATE='private-password Transcript: תמלול synthetic-private-value'


class HostAssertionControls(unittest.TestCase):
    def site(self,contract,error):
        code=R.contract_assertion_code(error,contract)
        self.assertIs(type(error),RuntimeError)
        self.assertIs(type(code),str)
        self.assertTrue(code.startswith('installer-report-validation-assertion-'))
        self.assertIn(code.removeprefix('installer-report-validation-assertion-'),contract.require.__globals__['_ASSERTION_SITES'].values())
        self.assertNotIn(PRIVATE,code)
        return code

    def test_closed_site_map_matches_all_current_contract_calls(self):
        expected={}
        for label,name in (('idle','contract.py'),('active','active-contract.py')):
            calls=[]
            def visit(node,owner=None):
                if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):owner=node
                if isinstance(node,ast.Call) and isinstance(node.func,(ast.Name,ast.Attribute)) and \
                        (node.func.id if isinstance(node.func,ast.Name) else node.func.attr) in ('require','exact') and owner is not None:
                    calls.append((owner,node))
                for child in ast.iter_child_nodes(node):visit(child,owner)
            visit(ast.parse(Path(__file__).with_name(name).read_text()))
            for index,(owner,call) in enumerate(sorted(calls,key=lambda x:(x[1].lineno,x[1].col_offset)),1):
                expected[(name,owner.name,call.lineno-owner.lineno)]=label+'-'+str(index).zfill(3)
        self.assertEqual(F.C._ASSERTION_SITES,expected)
        self.assertEqual(len(expected),288)
        self.assertEqual(len(set(expected.values())),288)

    def test_real_idle_assertions_keep_original_failure_and_precise_closed_site(self):
        changes=[lambda r:r['baseline']['engine']['hello'].update(live=False),
            lambda r:r['baseline']['identities']['gui'].update(executable=PRIVATE),
            lambda r:r['baseline']['identities']['gui']['argv'].append(PRIVATE),
            lambda r:r['baseline']['drm_heads'].update(pci_vendor='0x1234'),
            lambda r:r['cases'][1]['engine']['hello'].update(mock=True),
            lambda r:r['security'].update(selinux='Permissive')]
        codes=[]
        for mutate in changes:
            report,state,files,media,_=F.fixture();mutate(report)
            with self.assertRaises(RuntimeError) as caught:
                F.C.validate_report(report,state['context'],files,lambda name:media['installer/'+name],report['baseline']['packaged_sources'])
            codes.append(self.site(F.C,caught.exception))
            self.assertEqual(R.diagnostic_code('report-validation',caught.exception,F.C),codes[-1])
            self.assertNotEqual(R.diagnostic_code('cleanup',caught.exception,F.C),codes[-1])
        self.assertEqual(len(set(codes)),len(codes))

    def test_active_exact_wrapper_mints_callers_site_and_preserves_original_args(self):
        report,state,files,media,_=AF.fixture();report['private_field']=PRIVATE
        with self.assertRaises(RuntimeError) as caught:
            AF.A.validate_report(report,state['context'],files,lambda name:media['installer/'+name],report['baseline']['packaged_sources'])
        code=self.site(AF.A,caught.exception)
        self.assertEqual(caught.exception.args,('active report contains missing or private fields',))
        self.assertIn('active-',code)
        stream=io.StringIO()
        with patch('sys.stdout',stream):R.diagnose('report-validation',caught.exception,AF.A)
        self.assertEqual(stream.getvalue(),'ARCTIC-INSTALLER-DIAGNOSTIC='+code+'\n')
        self.assertNotIn(PRIVATE,stream.getvalue())

    def test_matching_arbitrary_strings_and_hostile_errors_cannot_mint_identity(self):
        class Hostile(RuntimeError):
            @property
            def args(self):raise AssertionError('private args accessed')
            @property
            def __dict__(self):raise AssertionError('private dict accessed')
            def __str__(self):raise AssertionError('private string accessed')
        for error in (RuntimeError('real engine identity differs'),RuntimeError(PRIVATE),Hostile(PRIVATE),
                      ValueError(PRIVATE),KeyboardInterrupt(PRIVATE),SystemExit(PRIVATE)):
            self.assertIsNone(R.contract_assertion_code(error,F.C))
        token=F.C._ASSERTION_TOKEN;code=next(iter(F.C._ASSERTION_SITES.values()))
        class PrivateString(str):
            def __hash__(self):raise AssertionError('private code hashed')
        for proof in ((object(),code),(token,PRIVATE),(token,PrivateString(code)),[token,code],
                      (token,code,PRIVATE),None):
            error=RuntimeError(PRIVATE);error._arctic_installer_assertion=proof
            self.assertIsNone(R.contract_assertion_code(error,F.C))
        # A test caller passing a matching literal is outside either contract.
        with self.assertRaises(RuntimeError) as caught:F.C.require(False,'real engine identity differs')
        self.assertIsNone(R.contract_assertion_code(caught.exception,F.C))

    def test_valid_full_report_and_private_message_semantics_are_unchanged(self):
        report,state,files,media,_=F.fixture();original=copy.deepcopy(report)
        result=F.C.validate_report(report,state['context'],files,lambda name:media['installer/'+name],report['baseline']['packaged_sources'])
        self.assertEqual(result['cases'],6);self.assertIs(result['release_acceptance'],False)
        self.assertEqual(report,original)
        with self.assertRaises(RuntimeError) as caught:F.C.require(False,PRIVATE)
        self.assertEqual(caught.exception.args,(PRIVATE,));self.assertIs(type(caught.exception),RuntimeError)
        self.assertIsNone(R.contract_assertion_code(caught.exception,F.C))


if __name__=='__main__':unittest.main()
