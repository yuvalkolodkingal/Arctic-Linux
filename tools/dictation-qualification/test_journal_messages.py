"""Every interval MESSAGE stays private and complete; unreadable values fail closed."""
import ast,hashlib,importlib.util,json,re,subprocess,unittest
from pathlib import Path
from unittest import mock
SPEC=importlib.util.spec_from_file_location('journal_messages_guest',Path(__file__).with_name('guest_check.py'))
guest=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(guest)
CFCC_SHA256='9eb689b71483dd31c71bb4419648737eff8b64a32600325947b24770f589fdcc'

def restore_journal_projection(text):
    node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name=='journal_messages')
    lines=text.splitlines(keepends=True);end=node.end_lineno
    assert lines[end]=='\n';del lines[node.lineno-1:end+1]
    restored=''.join(lines)
    assert restored.count(", '--output-fields=MESSAGE', '--all'")==2
    restored=restored.replace(", '--output-fields=MESSAGE', '--all'",'')
    original="rows = run(['journalctl', '-b', '--no-pager', '--after-cursor', self.cursor, '-o', 'json'], 60, output_role='interval-journal').stdout.decode()\n        journal = '\\n'.join(str(json.loads(line).get('MESSAGE', '')) for line in rows.splitlines() if line)"
    new="rows = run(['journalctl', '-b', '--no-pager', '--after-cursor', self.cursor, '-o', 'json'], 60, output_role='interval-journal').stdout\n        journal = journal_messages(rows)"
    assert restored.count(new)==2
    return restored.replace(new,original)

class JournalMessageSemantics(unittest.TestCase):
    def decode(self,value):
        return guest.journal_messages((json.dumps({'MESSAGE':value},ensure_ascii=True)+'\n').encode())
    def test_full_long_multiline_English_Hebrew_and_unicode_line_separator_are_retained(self):
        text='x'*8192+' LONG_TAIL_SENTINEL\nעברית\u2028full-message'
        self.assertEqual(self.decode(text),text)
    def test_binary_utf8_with_nonprintable_bytes_and_AVC_is_decoded_not_integer_text(self):
        text='prefix\x00עברית avc: denied synthetic'
        result=self.decode(list(text.encode('utf-8')))
        self.assertEqual(result,text);self.assertRegex(result,r'\bavc:\s*denied')
    def test_every_repeated_string_and_binary_value_is_retained(self):
        value=['first synthetic','עברית',list(b'last avc: denied synthetic')]
        self.assertEqual(self.decode(value),'first synthetic\nעברית\nlast avc: denied synthetic')
    def test_empty_or_missing_message_has_no_synthetic_content(self):
        for rows in (b'',b'\n',b'{}\n',b'{"__CURSOR":"private"}\n'):
            self.assertEqual(guest.journal_messages(rows),'')
        self.assertEqual(self.decode(''),'');self.assertEqual(self.decode([]),'')
    def test_truncation_null_unknown_types_and_ambiguous_nested_values_fail_closed(self):
        for value in (None,True,False,1,1.2,{},[True],[1.2],[256],[-1],['text',0],[[[65]]],['text',None]):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaisesRegex(guest.Invalid,'^journal-message-type$'):self.decode(value)
    def test_invalid_UTF8_raw_output_binary_message_and_surrogates_fail_closed(self):
        for rows in (b'\xff',b'{"MESSAGE":[255]}\n',b'{"MESSAGE":"\\ud800"}\n'):
            with self.assertRaisesRegex(guest.Invalid,'^journal-message-encoding$'):guest.journal_messages(rows)
    def test_duplicate_fields_nonfinite_bad_JSON_and_nonobject_entries_fail_closed(self):
        for rows,code in ((b'{"MESSAGE":"first","MESSAGE":"second"}','journal-json-duplicate-field'),(b'{"MESSAGE":NaN}','journal-json-nonfinite'),(b'{invalid','journal-json-invalid'),(b'[]','journal-json-entry-type')):
            with self.assertRaisesRegex(guest.Invalid,'^'+code+'$'):guest.journal_messages(rows)
    def test_arbitrary_output_objects_are_not_formatted_or_coerced(self):
        class Secret:
            def __str__(self):raise AssertionError('private value formatted')
            def __bytes__(self):raise AssertionError('private value converted')
        for rows in (Secret(),None,True,'private transcript'):
            with self.assertRaisesRegex(guest.Invalid,'^journal-output-byte-type$'):guest.journal_messages(rows)
    def test_failed_gate_never_exports_raw_MESSAGE_or_exception_text(self):
        checker=guest.Checker.__new__(guest.Checker);checker.gates={'transcript-log-notification-leak-scan'};checker.report={'gates':[]}
        checker.gate('transcript-log-notification-leak-scan',lambda:guest.journal_messages(b'{"MESSAGE":null,"PRIVATE":"transcript-canary"}'),'interval-log-scan')
        gate=checker.report['gates'][0]
        self.assertEqual(gate['status'],'failed');self.assertEqual(gate['code'],'journal-message-type');self.assertEqual(gate['observations'],{})
        self.assertNotIn('transcript-canary',json.dumps(gate));self.assertNotIn('PRIVATE',json.dumps(gate))
    def test_full_same_boot_after_cursor_commands_deadlines_roles_and_whole_rollback(self):
        text=Path(guest.__file__).read_text();restored=restore_journal_projection(text)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),CFCC_SHA256)
        before,after=ast.parse(restored),ast.parse(text)
        old={n.name:n for n in ast.walk(before) if isinstance(n,ast.FunctionDef)};new={n.name:n for n in ast.walk(after) if isinstance(n,ast.FunctionDef)}
        for name,node in old.items():
            if name not in ('leakage','avcs'):self.assertEqual(ast.dump(node),ast.dump(new[name]))
        for name in ('leakage','avcs'):
            calls=[n for n in ast.walk(new[name]) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='run' and any(k.arg=='output_role' for k in n.keywords)]
            self.assertEqual(len(calls),1);call=calls[0];argv=call.args[0].elts
            self.assertEqual([ast.literal_eval(x) for i,x in enumerate(argv) if i!=4],['journalctl','-b','--no-pager','--after-cursor','-o','json','--output-fields=MESSAGE','--all'])
            self.assertIsInstance(argv[4],ast.Attribute);self.assertEqual(argv[4].attr,'cursor');self.assertEqual(ast.literal_eval(call.args[1]),60)
            self.assertEqual({k.arg:ast.literal_eval(k.value) for k in call.keywords},{'output_role':'interval-journal'})
    def test_command_bound_remains_strict_at_sixteen_MiB_including_stderr(self):
        limit=16*1024*1024
        for out,err,passed in ((b' '*(limit-1),b'',True),(b' '*limit,b'',False),(b' '*(limit-1),b'e',False)):
            with mock.patch.object(guest.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout=out,stderr=err)):
                if passed:self.assertEqual(len(guest.run(['private'],60,output_role='interval-journal').stdout),limit-1)
                else:
                    with self.assertRaisesRegex(guest.Invalid,r'^command-output-bound-journal-o[0-9]+-e[0-9]+$'):guest.run(['private'],60,output_role='interval-journal')
    def test_real_journalctl_supports_projection_flags_without_journal_write(self):
        import shutil,tempfile
        if not shutil.which('journalctl'):self.skipTest('journalctl unavailable')
        with tempfile.TemporaryDirectory() as directory:
            result=subprocess.run(['journalctl','--directory',directory,'--no-pager','-o','json','--output-fields=MESSAGE','--all'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
        self.assertEqual(result.returncode,0);self.assertEqual(result.stdout,b'')

if __name__=='__main__':unittest.main()
