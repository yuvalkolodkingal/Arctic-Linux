"""Closed byte diagnostics; original scan coverage and acceptance limits stay exact."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock
sys.path.insert(0,str(Path(__file__).parent))
import contract as c
from test_journal_messages import restore_journal_projection
SPEC=importlib.util.spec_from_file_location('command_bound_guest',Path(__file__).with_name('guest_check.py'))
guest=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(guest)
ORIGINAL_SHA256='cb25c6ea06a0d9db413a736cd58e87f46a72125566de889952daa2af31a114ce'
ORIGINAL_RUN="def run(argv, timeout=20, check=True):\n    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)\n    require(len(result.stdout) + len(result.stderr) < 16 * 1024 * 1024, 'command-output-bound')\n    if check:\n        require(result.returncode == 0, 'command-failed')\n    return result\n"

def restore_command_output_diagnostics(text):
    """Exact new function and two role literals reverse to the public S10 helper."""
    if 'def journal_messages(rows):\n' in text:
        text=restore_journal_projection(text)
    node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name=='run')
    lines=text.splitlines(keepends=True);lines[node.lineno-1:node.end_lineno]=ORIGINAL_RUN.splitlines(keepends=True)
    restored=''.join(lines)
    assert restored.count(", output_role='interval-journal'")==2
    return restored.replace(", output_role='interval-journal'",'',2)

class OutputBounds(unittest.TestCase):
    def invoke(self,out=b'',err=b'',code=0,role='interval-journal',check=True):
        response=subprocess.CompletedProcess([],code,stdout=out,stderr=err)
        argv=['journalctl','-b','--no-pager','--after-cursor','private-cursor','-o','json']
        with mock.patch.object(guest.subprocess,'run',return_value=response) as called:
            result=guest.run(argv,60,check,output_role=role)
        self.assertEqual(called.call_args.args[0],argv);self.assertEqual(called.call_args.kwargs,{'stdout':subprocess.PIPE,'stderr':subprocess.PIPE,'timeout':60})
        return result

    def test_exact_total_limit_and_existing_check_semantics(self):
        limit=16*1024*1024
        self.assertEqual(len(self.invoke(b'x'*(limit-1)).stdout),limit-1)
        for out,err in ((b'x'*limit,b''),(b'x'*(limit-1),b'e'),(b'',b'e'*limit)):
            with self.assertRaises(c.Invalid) as caught:self.invoke(out,err)
            self.assertEqual(caught.exception.args,('command-output-bound-journal-o'+str(len(out))+'-e'+str(len(err)),))
        self.assertEqual(self.invoke(code=1,check=False).returncode,1)
        with self.assertRaisesRegex(c.Invalid,'^command-failed$'):self.invoke(code=1)
        with self.assertRaisesRegex(c.Invalid,'^command-output-bound$'):self.invoke(b'x'*limit,role=None)

    def test_unknown_role_fails_without_launch_or_private_formatting(self):
        class Secret:
            def __eq__(self,other):raise AssertionError('private role compared')
            def __str__(self):raise AssertionError('private role formatted')
        for role in ('private-transcript',True,{},Secret()):
            with mock.patch.object(guest.subprocess,'run') as run:
                with self.assertRaisesRegex(c.Invalid,'^unknown-command-output-role$'):guest.run(['private argv'],output_role=role)
            run.assert_not_called()

    def test_role_diagnostics_reject_custom_bytes_without_getters_or_formatting(self):
        class Secret:
            def __len__(self):raise AssertionError('private getter invoked')
            def __str__(self):raise AssertionError('private output formatted')
        class ByteSubclass(bytes):
            def __len__(self):raise AssertionError('private getter invoked')
        for value in (None,False,'private-material',Secret(),ByteSubclass(b'private')):
            for out,err in ((value,b''),(b'',value)):
                with self.assertRaisesRegex(c.Invalid,'^command-output-byte-types$'):self.invoke(out,err)

    def test_failed_gate_exports_only_closed_role_and_builtin_byte_counts(self):
        checker=guest.Checker.__new__(guest.Checker);checker.gates={'transcript-log-notification-leak-scan'};checker.report={'gates':[]}
        response=subprocess.CompletedProcess([],0,stdout=b'private transcript audio password '*600000,stderr=b'private-error')
        with mock.patch.object(guest.subprocess,'run',return_value=response):
            checker.gate('transcript-log-notification-leak-scan',lambda:guest.run(['private argv'],output_role='interval-journal'),'interval-log-scan')
        result=checker.report['gates'][0];code=result['code']
        self.assertEqual(result['status'],'failed');self.assertEqual(result['observations'],{})
        self.assertRegex(code,r'^command-output-bound-journal-o[0-9]+-e[0-9]+$');self.assertLessEqual(len(code),80)
        self.assertNotIn('private',json.dumps(result));self.assertNotIn('argv',json.dumps(result))

    def test_public_whole_helper_rollback_and_only_two_full_interval_calls(self):
        text=Path(guest.__file__).read_text();restored=restore_command_output_diagnostics(restore_journal_projection(text))
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),ORIGINAL_SHA256)
        old,new=ast.parse(restored),ast.parse(restore_journal_projection(text))
        oldfn={n.name:n for n in ast.walk(old) if isinstance(n,ast.FunctionDef)};newfn={n.name:n for n in ast.walk(new) if isinstance(n,ast.FunctionDef)}
        for name,node in oldfn.items():
            if name not in ('run','leakage','avcs'):self.assertEqual(ast.dump(node),ast.dump(newfn[name]))
        roles=[]
        for name in ('leakage','avcs'):
            node=newfn[name];calls=[n for n in ast.walk(node) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='run' and any(k.arg=='output_role' for k in n.keywords)]
            self.assertEqual(len(calls),1);call=calls[0];roles.extend(call.keywords)
            argv=call.args[0].elts
            self.assertEqual([ast.literal_eval(x) for i,x in enumerate(argv) if i!=4],['journalctl','-b','--no-pager','--after-cursor','-o','json'])
            self.assertIsInstance(argv[4],ast.Attribute);self.assertEqual(argv[4].attr,'cursor');self.assertEqual(ast.literal_eval(call.args[1]),60)
        self.assertEqual(len(roles),2);self.assertTrue(all(ast.literal_eval(k.value)=='interval-journal' for k in roles))

if __name__=='__main__':unittest.main()
