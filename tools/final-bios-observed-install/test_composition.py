#!/usr/bin/env python3
"""Exact composition controls; synthetic metadata and owned Python children only."""
import hashlib,json,os,subprocess,sys,tempfile,types,unittest
from pathlib import Path
from unittest import mock
import common as C
import run as R

def manifest():return C.manifest(C.strict_json((R.HERE/'execution-manifest.json').read_bytes()))
def native():return subprocess.check_output(['git','-C',str(C.ROOT),'show','326690f173d4dc4f049f43e046c8380e66825a07:tools/native-functional/native_smoke.py'])

class Controls(unittest.TestCase):
    def test_disabled_main_refuses_before_owned_modules_or_api(self):
        with mock.patch.object(R,'owned_modules',side_effect=AssertionError('unexpected module execution')):
            with self.assertRaisesRegex(RuntimeError,'BIOS lane remains disabled'):R.main()

    def test_exact_original_code_globals_and_import_alias_restoration(self):
        prior={n:sys.modules.get(n) for n in ('common','compose','observer')}
        exact,old,channel=R.main_adapter(manifest())
        self.assertIs(exact.__code__,old.main.__code__)
        for name in ('recover_prepared_image','remove_owned_container','harness_environment','original_evidence'):
            self.assertIs(exact.__globals__[name],old.__dict__[name])
        self.assertIs(old.execute.__globals__,old.__dict__)
        self.assertIs(old.argv.__globals__,old.__dict__)
        self.assertIs(old.C.guard.__globals__,old.C.__dict__)
        self.assertEqual(prior,{n:sys.modules.get(n) for n in prior})
        self.assertIsNot(exact.__globals__['C'],old.C)

    def test_actual_child_failure_retained_before_original_owned_cleanup(self):
        value=manifest();exact,old,channel=R.main_adapter(value)
        task='a'*32;image='sha256:'+'b'*64;events=[];commands=[]
        source_raw=native();saved_popen=subprocess.Popen
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);source=base/'source';(source/'tools/native-functional').mkdir(parents=True)
            (source/'tools/native-functional/native_smoke.py').write_bytes(source_raw)
            inputs=base/'inputs';inputs.mkdir();out=base/'evidence'
            deps=exact.__globals__;deps['uuid']=types.SimpleNamespace(uuid4=lambda:types.SimpleNamespace(hex=task))
            deps['Path']=lambda path:types.SimpleNamespace(is_char_device=lambda:True) if path=='/dev/kvm' else Path(path)
            def spawn(argv,**kwargs):
                if argv[0]!='bash':return saved_popen(argv,**kwargs)
                commands.append(argv)
                if argv[1].endswith('prepare-vm-tools.sh'):
                    code='from pathlib import Path;Path('+repr(str(out/'private/vm-prepared-image-id.txt'))+').write_text('+repr(image)+'+"\\n")'
                else:
                    sites=C.strict_json((R.OBSERVER/'execution-manifest.json').read_bytes())['allowed_sites']
                    site=next(x for x in sites if x['source']=='install-driver' and x['function']=='stage_boot' and x['source_line']==794)
                    record={'schema':'arctic-bios-inner-source-cause-v1','nonce':task,'cause':{'event':'nonzero-original-stage-return','site':site,'executed_false_flag_sites':[]},'release_acceptance':False}
                    code='print('+repr('ARCTIC-BIOS-INNER-CAUSE '+json.dumps(record))+',flush=True);print("unknown private operand",flush=True);raise SystemExit(23)'
                return saved_popen([sys.executable,'-c',code],**kwargs)
            original_check=subprocess.check_output;original_run=subprocess.run
            def metadata(argv,**kwargs):
                if argv[0]!='docker':return original_run(argv,**kwargs)
                if argv[:3]==['docker','container','inspect']:
                    events.append('container-inspect')
                    row={'Name':'/'+argv[-1],'Image':image,'Id':'c'*64,'Mounts':[{'Source':str(out/'private/vm'),'Destination':str(out/'private/vm')}]}
                    return types.SimpleNamespace(returncode=0,stdout=json.dumps([row]).encode())
                if argv[:2] in (['docker','rm'],['docker','image']):
                    events.append('owned-cleanup');return types.SimpleNamespace(returncode=0,stdout=b'')
                raise AssertionError('unexpected synthetic metadata command')
            def inspected(argv,**kwargs):
                if argv[:3]==['docker','image','inspect']:
                    return json.dumps({'org.arctic.test.vm-tools.task':task,'org.arctic.test.vm-tools.container':'arctic-paired-'+task+'-'+task[:8],'org.arctic.test.vm-tools.scope':'paired-v1'}).encode()
                return original_check(argv,**kwargs)
            with mock.patch.object(C,'guard',lambda *a,**k:events.append('admission')),mock.patch.object(subprocess,'Popen',spawn),mock.patch.object(subprocess,'check_output',inspected),mock.patch.object(subprocess,'run',metadata),mock.patch.object(sys,'argv',['control','--source',str(source),'--inputs',str(inputs),'--out',str(out)]):
                self.assertEqual(exact(),1)
            status=C.strict_json((out/'public/host-status.json').read_bytes())
            self.assertEqual(status['status'],'failed');self.assertEqual(status['phase'],'install-and-boot')
            self.assertIsNone(status['result']);self.assertFalse(status['complete_UART_published'])
            self.assertEqual(set(p.name for p in (out/'public').iterdir()),{'host-status.json'})
            rows=status['finite_original_source_failure'];self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['outer_source_site']['fixed_assertion_label'],'BIOS host invocation failed')
            self.assertEqual(rows[0]['finite_inner_source_records'][0]['cause']['site']['source_line'],794)
            self.assertNotIn('unknown private operand',json.dumps(status))
            self.assertEqual(events.count('owned-cleanup'),2)
            self.assertEqual(len(commands),2);self.assertEqual(commands[1][0],'bash')
            self.assertEqual(commands[1][commands[1].index('--install-timeout')+1],'2400')
            self.assertEqual(commands[1][commands[1].index('--stage')+1],'all')
            self.assertEqual(commands[1][commands[1].index('--firmware')+1],'bios')
            self.assertEqual(channel['failure'],rows)
            staged=channel['shell'].read_bytes();original=(C.ROOT/'tools/test-install.sh').read_bytes()
            self.assertEqual(staged.replace(b'python3 /arctic-lib/driver-entry.py || rc=$?',b'python3 -c "$DRIVER" || rc=$?',1),original)

    def test_unknown_source_record_and_private_fields_are_rejected(self):
        value=manifest();_,_,_,_,adapter,_=R.owned_modules(value)
        sm=C.strict_json((R.OBSERVER/'execution-manifest.json').read_bytes())
        site=next(s for s in sm['allowed_sites'] if s['source']=='bios-host' and s['fixed_assertion_label']=='BIOS host invocation failed')
        row={'schema':'arctic-bios-finite-host-cause-v1','outer_source_site':site,'finite_inner_source_records':[],'release_acceptance':False}
        self.assertEqual(R.finite_failure(row,'a'*32,sm,adapter),row)
        self.assertIsNone(R.finite_failure(dict(row,private='unknown'), 'a'*32,sm,adapter))
        self.assertIsNone(R.finite_failure(dict(row,outer_source_site=dict(site,source_line=True)),'a'*32,sm,adapter))
        self.assertIsNone(R.finite_failure(dict(row,outer_source_site=dict(site,fixed_assertion_label='unknown')),'a'*32,sm,adapter))

    def test_changed_accepted_manifest_fails_before_main_or_cleanup(self):
        value=manifest();value['execution_files']=dict(value['execution_files'])
        value['execution_files']['tools/final-bios-failure-observer/execution-manifest.json']='0'*64
        with self.assertRaisesRegex(RuntimeError,'manifest bytes differ'):R.main_adapter(value)

    def test_success_publication_keeps_original_bytes_and_no_failure_field(self):
        exact,old,channel=R.main_adapter(manifest());seen=[]
        channel['failure'].append({'private':'must not publish'})
        original=b'{"status":"passed_pending_original_image_review"}\n'
        with mock.patch.object(old,'publish',lambda out,files:seen.append(files)):
            exact.__globals__['publish'](Path('/unused'),{'host-status.json':original})
        self.assertEqual(seen,[{'host-status.json':original}])

if __name__=='__main__':unittest.main()
