"""Typed transport fixtures only; no actual image or attestation is bound."""
import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zlib
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('startup_host',HERE/'attest-host-v1.py');H=importlib.util.module_from_spec(spec);spec.loader.exec_module(H)

def transport(change=None,message='fixture only',channel='kernel'):
    boot='12345678-1234-1234-1234-1234567890ab';journal=(json.dumps(dict(_BOOT_ID=boot.replace('-',''),_TRANSPORT=channel,MESSAGE=message))+'\n').encode()
    security=dict(selinux='Enforcing',avc_records=[],audit_status='enabled 1\nlost 0\n',journal_total_bytes=len(journal),journal_retained_bytes=len(journal),journal_retained_sha256=H.sha(journal),current_boot_journal_records=1)
    report=dict(schema='arctic-startup-attestation-v1',status='exact-startup-attestation-collected',candidate_source='fe4742c8b9414c45f0bcbb0a4191f116383c60d1',
                intended_iso_sha256='84c9c88ebcbcaf69dbabf56509a9ceb2db58e5dc41d7bae12093edba12f60718',mango_executable_sha256='ce11ee5cfd24b0393c933e22f7365910d498772e186bb078b9d63a2b42313866',
                source_files=dict(files=[dict(path='/fixture',status='read-raw',uid=0,gid=0,mode=0o644,bytes=3,sha256=H.sha(b'raw'),base64=base64.b64encode(b'raw').decode())],raw_source_bytes=3),
                begin_monotonic_ns=1,end_monotonic_ns=2,boot_id=boot,security_before=security.copy(),security_after=security.copy(),
                selected_startup_chain=dict(shell='/usr/bin/fish',actual_SHELL='/usr/bin/fish',uid=1000,home='/home/liveuser',independently_reviewed_complete_chain=False,unresolved_links_are_startup_binding_blockers=True),
                startup_binding_blockers=[dict(path='semantic-startup-chain',status='unreviewed')],
                release_acceptance=False,safe_visual_gate='open',startup_hook_executed=False,renderer='unobserved',active_scanout_pixels='unavailable')
    if change:change(report)
    files={'report.json':json.dumps(report).encode(),'system-journal-attest-before.log':journal,'system-journal-attest-after.log':journal}
    manifest=dict(schema='arctic-startup-attestation-files-v1',encoding='zlib+base64',files=[],bytes=sum(len(v) for v in files.values()));chunks=[]
    for name,data in files.items():
        packed=zlib.compress(data);manifest['files'].append(dict(path=name,bytes=len(data),sha256=H.sha(data),compressed_bytes=len(packed),chunks=1));chunks.append(('CHUNK',dict(path=name,index=0,data=base64.b64encode(packed).decode())))
    return [('BEGIN',dict(collector_sha256='a'*64,candidate_source=report['candidate_source'],release_acceptance=False)),('REPORT',report),('MANIFEST',manifest),*chunks,('END',dict(status='attestation-collected-unreviewed',error=None,release_acceptance=False))]
def serial(values):return ''.join('ARCTIC-ATTEST-'+name+' '+json.dumps(value)+'\n' for name,value in values)

class HostTests(unittest.TestCase):
    def test_positive_fixture_remains_unbound_and_unqualified(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'out';value=H.extract(serial(transport()),out,'a'*64)
            self.assertFalse(value['exact_startup_target_bound']);self.assertFalse(value['release_acceptance']);self.assertEqual(value['safe_visual_gate'],'open')
            self.assertEqual((out/'report.json').read_bytes(),json.dumps(transport()[1][1]).encode())
    def test_all_end_cuts_wait_live_reject_final_and_duplicate_completed_phase(self):
        values=transport();prefix=serial(values[:-1]);end=serial(values[-1:])
        for cut in range(len(end)):
            with self.subTest(cut=cut),tempfile.TemporaryDirectory() as temp:
                self.assertFalse(H.protocol(prefix+end[:cut],live=True)[1])
                with self.assertRaises(RuntimeError):H.extract(prefix+end[:cut],Path(temp)/'out','a'*64)
        for index in (0,1,2,len(values)-1):
            altered=list(values);altered.insert(index,values[index])
            with self.subTest(index=index),tempfile.TemporaryDirectory() as temp,self.assertRaises(RuntimeError):H.extract(serial(altered),Path(temp)/'out','a'*64)
    def test_malformed_primitive_key_collision_and_extra_record_reject(self):
        for text in ('ARCTIC-ATTEST-BEGIN {"x":1,"x":2}\n','ARCTIC-ATTEST-BEGIN false\n','ARCTIC-ATTEST-BEGIN {\n',serial(transport())+'ARCTIC-ATTEST-UNKNOWN {}\n'):
            with self.subTest(text=text[-60:]),tempfile.TemporaryDirectory() as temp,self.assertRaises((RuntimeError,ValueError)):H.extract(text,Path(temp)/'out','a'*64)
    def test_semantic_security_intervals_owners_hashes_and_truncation_reject(self):
        cases=[lambda r:r.update(release_acceptance=True),lambda r:r.update(startup_hook_executed=True),lambda r:r.update(end_monotonic_ns=False),lambda r:r['security_after'].update(selinux='Permissive'),
               lambda r:r['security_before'].update(audit_status='enabled 1\nlost 1\n'),lambda r:r['security_before'].update(journal_total_bytes=999999),lambda r:r['security_after'].update(current_boot_journal_records=2),
               lambda r:r['source_files']['files'][0].update(uid=False),lambda r:r['source_files']['files'][0].update(sha256='0'*64),lambda r:r['source_files']['files'].append(r['source_files']['files'][0].copy()),
               lambda r:r['selected_startup_chain'].update(independently_reviewed_complete_chain=0),lambda r:r['selected_startup_chain'].update(uid=True),
               lambda r:r['selected_startup_chain'].update(shell='/usr/bin/zsh'),lambda r:r.update(startup_binding_blockers=[])]
        for i,change in enumerate(cases):
            with self.subTest(i=i),tempfile.TemporaryDirectory() as temp:
                out=Path(temp)/'out'
                with self.assertRaises(RuntimeError):H.extract(serial(transport(change)),out,'a'*64)
                self.assertFalse(out.exists())
    def test_real_trusted_denial_not_sudo_command_literal(self):
        for channel,reject in [('kernel',True),('audit',True),('syslog',False)]:
            with self.subTest(channel=channel),tempfile.TemporaryDirectory() as temp:
                call=lambda:H.extract(serial(transport(message="COMMAND=grep 'avc: denied'",channel=channel)),Path(temp)/'out','a'*64)
                if reject:
                    with self.assertRaises(RuntimeError):call()
                else:call()
    def test_unsafe_payload_path_sha_index_and_existing_output_refuse(self):
        for mode in ('path','sha','bool-index','duplicate-chunk','existing'):
            values=transport()
            if mode=='path':values[2][1]['files'][0]['path']='../escape.json'
            elif mode=='sha':values[2][1]['files'][0]['sha256']='0'*64
            elif mode=='bool-index':values[3][1]['index']=False
            elif mode=='duplicate-chunk':values.insert(3,values[3])
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temp:
                out=Path(temp)/'out'
                if mode=='existing':out.mkdir()
                with self.assertRaises(RuntimeError):H.extract(serial(values),out,'a'*64)
    def test_boolean_release_numeric_aliases_and_incomplete_chain_refuse(self):
        for index in (0,-1):
            values=transport();values[index][1]['release_acceptance']=0
            with self.subTest(index=index),tempfile.TemporaryDirectory() as temp,self.assertRaises(RuntimeError):
                H.extract(serial(values),Path(temp)/'out','a'*64)
    def test_unterminated_late_duplicate_all_header_cuts_never_final_pass(self):
        original=serial(transport());duplicate=serial([transport()[0]])
        for cut in range(1,len(duplicate)):
            with self.subTest(cut=cut),tempfile.TemporaryDirectory() as temp,self.assertRaises(RuntimeError):
                H.extract(original+duplicate[:cut],Path(temp)/'out','a'*64)

if __name__=='__main__':unittest.main(verbosity=2)
