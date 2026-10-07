"""Synthetic protocol fixtures only; no native Mango/guest/renderer qualification."""
import copy,importlib.util,json
from pathlib import Path
import unittest
HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('trace_wire',HERE/'transport.py');H=importlib.util.module_from_spec(spec);spec.loader.exec_module(H)

def fixture():
    raw=b'GL renderer: synthetic-only\n';image=dict(pid=500,ppid=400,pgrp=400,session=400,start_ticks=2,uid=1000,cmdline=['mango','-d'],executable='/usr/bin/mango',executable_sha256='ce11ee5cfd24b0393c933e22f7365910d498772e186bb078b9d63a2b42313866',cwd='/home/liveuser',stdin='/dev/null',stdout='fixture')
    row=dict(pid=500,uid=1000,gid=1000,begin=0,end=len(raw),received_monotonic_ns=3,sha256=H.sha(raw),origin='owned-launch-process')
    full=dict(child_pid=500,status='owned-trace-collected',controlled_stop=True,cleanup='owned-child-reaped',unowned_inherited_writers_signalled=False,future_inherited_writer_tail_qualified=False,native_identity=image,rows=[row],raw_bytes=len(raw),raw_sha256=H.sha(raw),start_monotonic_ns=1,end_monotonic_ns=4,owned_child_start_ticks=2,owned_pidfd_identity={'pid':500,'kernel_fdinfo_bound':True,'signal0_permission_checked':True},expected_sender_uid_gid={'uid':1000,'gid':1000})
    fullraw=json.dumps(full,sort_keys=True).encode()+b'\n'
    terminal=dict(full);terminal.pop('rows');terminal.update(all_owned_FDs_closed=True,normal_session_fidelity=False,complete_chain=False,sender_ranges_body=dict(path='log-report.json',bytes=len(fullraw),sha256=H.sha(fullraw),rows=1))
    terminalraw=json.dumps(terminal,sort_keys=True).encode()+b'\n'
    line=dict(begin=0,end=len(raw),complete=True,authenticated_writer=True,status='owned-complete-line',sha256=H.sha(raw))
    state=dict(startup_perturbation=True,complete_chain=False,normal_fidelity=False,safe_visual_gate='OPEN')
    boot='00000000-0000-0000-0000-000000000001';journal=json.dumps({'_BOOT_ID':boot.replace('-',''),'_TRANSPORT':'kernel','MESSAGE':'entire synthetic fixture journal','PRIORITY':'4'},sort_keys=True).encode()+b'\n'
    security=dict(qualified=True,selinux='Enforcing',audit_status='enabled 1\nlost 0\n',full_unfiltered=True,avc_records=[],journal_total_bytes=len(journal),journal_retained_bytes=len(journal),current_boot_journal_records=1,journal_retained_sha256=H.sha(journal))
    report=dict(schema='arctic-one-mango-trace-v1',status='diagnostic-collected-visual-open',startup_perturbation=True,normal_session_fidelity=False,complete_chain=False,release_acceptance=False,safe_visual_gate='OPEN',active_scanout_pixels='UNAVAILABLE',native_report=terminal,logger_identity=dict(pid=400,start_ticks=1,uid=1000,executable_sha256='0d64bd6d66d68dac91cdadafc46e22d4f09f22bdc997aaae870f42865b024a3e',selected_helper_parent={'executable_sha256':'93ab003b0453179eb1f0e6a7a51a20ee322af4992300d095403c5f728b7a68e4'},**{k:image[k] for k in ['session','pgrp','cwd','stdin','stdout']}),security_before=security,security_after=copy.deepcopy(security),boot_id=boot,candidate_source='fe4742c8b9414c45f0bcbb0a4191f116383c60d1',intended_iso_sha256='84c9c88ebcbcaf69dbabf56509a9ceb2db58e5dc41d7bae12093edba12f60718',root_cleanup=dict(owned_runtime_config_removed=True,owned_generated_files_removed=True,owned_readonly_CD_unmounted=True,underlying_owned_mount_directory_removed=True,root_owned_descriptors_closed=True,normal_SDDM_cache_restored=False,normal_target_replacement=False))
    bodies={'terminal.json':terminalraw,'log-report.json':fullraw,'stderr.raw':raw,'line-proofs.json':json.dumps([line],sort_keys=True).encode()+b'\n','owned-state.json':json.dumps(state).encode()+b'\n','journal-before.log':journal,'journal-after.log':journal}
    return report,bodies

class Wire(unittest.TestCase):
    def validate(self,report,bodies):
        frames=H.export(report,bodies);decoded,files=H.decode(b''.join(frames).decode());return H.validate_evidence(decoded,files)
    def test_complete_same_channel_referenced_bodies(self):
        report,bodies=fixture();result=self.validate(report,bodies);self.assertEqual(result['safe_visual_gate'],'OPEN');self.assertFalse(result['normal_fidelity'])
    def test_all_final_END_cuts_fail(self):
        report,bodies=fixture();frames=H.export(report,bodies);prefix=b''.join(frames[:-1]);last=frames[-1]
        for cut in range(len(last)):
            with self.subTest(cut=cut),self.assertRaises(Exception):H.decode((prefix+last[:cut]).decode())
    def test_duplicate_unknown_malformed_completed_record_fail(self):
        report,bodies=fixture();frames=H.export(report,bodies)
        for extra in [frames[0],b'ARCTIC-RENDER-WHATEVER {}\n',b'ARCTIC-RENDER-CHUNK badjson\n']:
            with self.subTest(extra=extra),self.assertRaises(Exception):H.decode(b''.join(frames[:-1]+[extra,frames[-1]]).decode())
    def test_full_bodies_reference_mutations_fail_even_after_wire_rehash(self):
        for kind in ['uidfloat','pidalias','badkernelpid','lost','avc','rowgap','truncatedjournal','Falsepixels','cleanupinteger']:
            report,bodies=fixture()
            if kind=='uidfloat':report['native_report']['native_identity']['uid']=1000.0
            if kind=='pidalias':report['logger_identity']['pid']=500;report['native_report']['native_identity']['ppid']=500
            if kind=='badkernelpid':report['native_report']['owned_pidfd_identity']['pid']=True
            if kind=='lost':report['security_after']['audit_status']='enabled 1\nlost 1\n'
            if kind=='avc':
                j=H.strict_json(bodies['journal-after.log']);j['MESSAGE']='avc: denied { read }';raw=json.dumps(j).encode()+b'\n';bodies['journal-after.log']=raw;report['security_after'].update(journal_total_bytes=len(raw),journal_retained_bytes=len(raw),journal_retained_sha256=H.sha(raw))
            if kind=='rowgap':
                full=H.strict_json(bodies['log-report.json']);full['rows'][0]['begin']=1;bodies['log-report.json']=json.dumps(full).encode()+b'\n';report['native_report']['sender_ranges_body'].update(bytes=len(bodies['log-report.json']),sha256=H.sha(bodies['log-report.json']))
            if kind=='truncatedjournal':report['security_after']['journal_total_bytes']+=1
            if kind=='Falsepixels':report['active_scanout_pixels']='observed'
            if kind=='cleanupinteger':report['root_cleanup']['root_owned_descriptors_closed']=1
            bodies['terminal.json']=json.dumps(report['native_report'],sort_keys=True).encode()+b'\n'
            with self.subTest(kind=kind),self.assertRaises(Exception):self.validate(report,bodies)
    def test_332115_byte_report_fails_unchanged_marker_cap(self):
        report,bodies=fixture();report['padding']='x'*332115
        with self.assertRaisesRegex(RuntimeError,'marker cap'):H.export(report,bodies)
    def test_duplicate_JSON_keys_reject(self):
        with self.assertRaisesRegex(RuntimeError,'Duplicate'):H.strict_json('{"uid":1000,"uid":0}')
if __name__=='__main__':unittest.main()
