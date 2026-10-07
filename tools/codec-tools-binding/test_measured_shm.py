"""Finite pure/actual-function-chain fixtures; no Docker/RPM/DNF/network work."""
from pathlib import Path
import copy
import json
import os
import sys
import types
from unittest import TestCase, mock
import unittest

HERE=Path(__file__).resolve().parent
SOURCE=Path(os.environ.get('CODEC_RECEIPT_SOURCE_DIR',str(HERE))).resolve()
sys.path[:0]=[str(SOURCE),str(SOURCE/'vendor')]
import prepare
import test_tools

PROOF=json.loads((SOURCE/'metadata-v4-state-integrity-failure.json').read_text())
RPM='usr/lib/sysimage/rpm'

class MeasuredTransitionControls(TestCase):
    def recognize(self,before=None,after=None,relative=RPM,stage='metadata',base=None,bd=None,ad=None):
        before=copy.deepcopy(PROOF['before_entries']) if before is None else before
        after=copy.deepcopy(PROOF['after_entries']) if after is None else after
        session=types.SimpleNamespace(ctx={'stage':stage},binding={'base':{'image_id':base or prepare.c.BASE_ID}})
        return prepare.measured_rpm_shm_transition(session,relative,
            prepare.manifest_digest(before) if bd is None else bd,
            prepare.manifest_digest(after) if ad is None else ad,before,after)

    def chain(self,before=None,after=None,stage='metadata',base=None,changed_headers=False,dnf_changed=False,write_error=False,change=None):
        original_root=prepare.prepare_root;original_scan=prepare.tree_manifest
        original_header=prepare.header_rows;original_write=prepare.write_json;original_cache=prepare.metadata_cache_receipts
        scans=[];records=[];headers=[]
        def root(session):
            session.ctx={'stage':stage}
            result=original_root(session)
            if base is not None:session.binding['base']['image_id']=base
            return result
        def scan(path):
            relative=str(path).split('/installroot/',1)[-1];scans.append(relative)
            actual=original_scan(path)
            if relative==RPM:
                rows=PROOF['before_entries'] if scans.count(RPM)==1 else PROOF['after_entries']
                if scans.count(RPM)==1 and before is not None:rows=before
                if scans.count(RPM)==2 and after is not None:rows=after
                return copy.deepcopy(rows)
            return actual
        def header(*args):
            rows=original_header(*args);headers.append(rows)
            return rows+[('unexpected','0:1-1','noarch','x.src.rpm','MIT')] if changed_headers and len(headers)==3 else rows
        def cache(work,*args):
            proof=original_cache(work,*args)
            if dnf_changed:(work/'installroot/usr/lib/sysimage/libdnf5/fixture-state').write_bytes(b'changed durable DNF state')
            return proof
        def write(path,data):
            if path.name in ('measured-rpm-shm-transition.json','state-integrity-failure.json'):
                records.append((path.name,copy.deepcopy(data)))
                if write_error and path.name=='measured-rpm-shm-transition.json':raise OSError('synthetic transition receipt write failure')
            return original_write(path,data)
        with mock.patch.object(prepare,'prepare_root',root),mock.patch.object(prepare,'tree_manifest',scan), \
                mock.patch.object(prepare,'header_rows',header),mock.patch.object(prepare,'metadata_cache_receipts',cache), \
                mock.patch.object(prepare,'write_json',write):
            result=test_tools.MetadataPrerequisiteControls().chain(change)
        return (*result,scans,records)

    def test_exact_saved_pair_recognized_without_file_reads(self):
        with mock.patch.object(Path,'open',side_effect=AssertionError('extra read')),mock.patch.object(Path,'stat',side_effect=AssertionError('extra stat')):
            result=self.recognize()
        self.assertEqual(result['only_changed_member'],'rpmdb.sqlite-shm')
        self.assertEqual(result['historical_run_remains'],'FAIL_STOP')
        self.assertTrue(result['database_WAL_lock_rows_equal'])

    def test_wrong_stage_base_relative_or_digest_refused(self):
        for kwargs in ({'stage':'closure'},{'stage':'image'},{'base':'sha256:'+'0'*64},{'relative':'usr/lib/sysimage/libdnf5'},
                       {'relative':'rpm'},{'bd':'0'*64},{'ad':'0'*64}):
            with self.subTest(kwargs=kwargs):self.assertIsNone(self.recognize(**kwargs))

    def test_other_hash_size_mode_type_path_and_extra_metadata_refused(self):
        for side in ('before','after'):
            for key,value in (('sha256','0'*64),('bytes',32769),('mode',384),('type','symlink'),('path','renamed-shm'),('uid',1000)):
                rows=copy.deepcopy(PROOF[side+'_entries']);rows[2][key]=value
                with self.subTest(side=side,key=key):self.assertIsNone(self.recognize(**{side:rows}))

    def test_every_durable_row_change_and_added_removed_or_duplicate_member_refused(self):
        for side in ('before','after'):
            for index in (0,1,3):
                for key,value in (('sha256','0'*64),('bytes',1),('mode',384),('type','directory')):
                    rows=copy.deepcopy(PROOF[side+'_entries']);rows[index][key]=value
                    with self.subTest(side=side,index=index,key=key):self.assertIsNone(self.recognize(**{side:rows}))
            for action in ('added','removed','duplicate','reorder'):
                rows=copy.deepcopy(PROOF[side+'_entries'])
                if action=='added':rows.append({'path':'new','type':'directory','mode':420})
                if action=='removed':rows.pop()
                if action=='duplicate':rows[-1]=copy.deepcopy(rows[0])
                if action=='reorder':rows.reverse()
                with self.subTest(side=side,action=action):self.assertIsNone(self.recognize(**{side:rows}))

    def test_forged_fixed_digest_does_not_admit_wrong_rows_or_integer_types(self):
        for side in ('before','after'):
            rows=copy.deepcopy(PROOF[side+'_entries']);rows[0]['bytes']=False
            self.assertIsNone(self.recognize(**{side:rows,'bd':PROOF['before_tree_sha256'][RPM],'ad':PROOF['observed_after_tree_sha256'][RPM]}))
            rows[0]['bytes']=0;rows[1]['sha256']='0'*64
            self.assertIsNone(self.recognize(**{side:rows,'bd':PROOF['before_tree_sha256'][RPM],'ad':PROOF['observed_after_tree_sha256'][RPM]}))
        session=types.SimpleNamespace(ctx={'stage':'metadata'},binding={'base':{'image_id':prepare.c.BASE_ID}})
        self.assertIsNone(prepare.measured_rpm_shm_transition(session,RPM,PROOF['before_tree_sha256'][RPM],PROOF['observed_after_tree_sha256'][RPM],None,PROOF['after_entries']))

    def test_real_function_chain_exact_pair_continues_original_dnf_guard_then_STOP(self):
        error,result,calls,scans,records=self.chain()
        self.assertIsNone(error);self.assertEqual(result['status'],'METADATA_CONFIG_EXTERNAL_REVIEW_STOP')
        self.assertEqual(scans,[RPM,'usr/lib/sysimage/libdnf5']*2)
        self.assertEqual([name for name,data in records],['measured-rpm-shm-transition.json'])
        integrity=result['private_state_integrity']
        self.assertFalse(integrity['all_tree_digests_equal']);self.assertTrue(integrity['all_other_state_entries_equal'])
        self.assertTrue(integrity['headers_equal']);self.assertEqual(len(integrity['recognized_fixed_RPM_SHM_transitions']),1)
        self.assertNotIn('private_state_before_and_after_equal',result)
        self.assertFalse(result['later_bootstrap_closure_bindings_automatically_written'])
        self.assertFalse(result['RPM_payload_downloads']);self.assertFalse(result['solve_store_transaction_scripts'])
        self.assertFalse(any('do' in argv or any('--store=' in item for item in argv) for argv,tag in calls))

    def test_real_chain_header_change_fails_before_state_classification(self):
        error,result,calls,scans,records=self.chain(changed_headers=True)
        self.assertEqual(str(error),'metadata-only work changed private RPM headers');self.assertIsNone(result)
        self.assertEqual(scans,[RPM,'usr/lib/sysimage/libdnf5']);self.assertEqual(records,[])

    def test_real_chain_dnf_change_still_fails_after_exact_rpm_transition(self):
        error,result,calls,scans,records=self.chain(dnf_changed=True)
        self.assertEqual(str(error),'metadata-only work changed copied state');self.assertIsNone(result)
        self.assertEqual(scans,[RPM,'usr/lib/sysimage/libdnf5']*2)
        self.assertEqual([name for name,data in records],['measured-rpm-shm-transition.json','state-integrity-failure.json'])
        self.assertEqual(records[1][1]['failing_relative_tree'],'usr/lib/sysimage/libdnf5')

    def test_real_chain_unknown_rpm_change_stops_before_next_tree(self):
        for side in ('before','after'):
            rows=copy.deepcopy(PROOF[side+'_entries']);rows[2]['sha256']='0'*64
            error,result,calls,scans,records=self.chain(**{side:rows})
            self.assertEqual(str(error),'metadata-only work changed copied state');self.assertIsNone(result)
            self.assertEqual(len(scans),3);self.assertEqual([name for name,data in records],['state-integrity-failure.json'])

    def test_real_chain_wrong_stage_base_no_receipt_or_missing_before_cannot_continue(self):
        for kwargs in ({'stage':'closure'},{'base':'sha256:'+'0'*64}):
            error,result,calls,scans,records=self.chain(**kwargs)
            self.assertEqual(str(error),'metadata-only work changed copied state');self.assertIsNone(result)
            self.assertEqual(len(scans),3);self.assertEqual([name for name,data in records],['state-integrity-failure.json'])

    def test_real_chain_config_goal_alias_and_receipt_write_failures_remain_failures(self):
        for change in ('after-config','goal','aliases'):
            error,result,calls,scans,records=self.chain(change=change)
            self.assertIsNotNone(error);self.assertIsNone(result)
        with self.assertRaisesRegex(OSError,'synthetic transition receipt write failure'):self.chain(write_error=True)

    def test_all_equal_original_chain_truthfully_reports_no_transition(self):
        error,result,calls=test_tools.MetadataPrerequisiteControls().chain()
        self.assertIsNone(error)
        self.assertTrue(result['private_state_integrity']['all_tree_digests_equal'])
        self.assertEqual(result['private_state_integrity']['recognized_fixed_RPM_SHM_transitions'],[])

if __name__=='__main__':unittest.main()
