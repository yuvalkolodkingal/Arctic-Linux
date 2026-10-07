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
                selected_startup_chain=dict(shell='/bin/bash',actual_SHELL='/bin/bash',uid=1000,home='/home/liveuser',independently_reviewed_complete_chain=False,unresolved_links_are_startup_binding_blockers=True),
                startup_binding_blockers=[dict(path='semantic-startup-chain',status='unreviewed')],
                release_acceptance=False,safe_visual_gate='open',startup_hook_executed=False,renderer='unobserved',active_scanout_pixels='unavailable')
    unit=b'FragmentPath=/usr/lib/systemd/system/sddm.service\nDropInPaths=/usr/lib/systemd/system/service.d/10-timeout-abort.conf\nEnvironmentFiles=/etc/sysconfig/sddm (ignore_errors=yes)\nExecStart=HOST FIXTURE ONLY\n'
    sources=report['source_files']['files'];sources.extend(dict(path=p,status='absent') for p in H.FOLLOWUP_FILES)
    proofs=[]
    for index,(node,literal,target) in enumerate(H.PROFILE_TARGETS):
        ns=[1,index+2,0,0,0o120777,len(literal),1,1];ts=[1,index+100,0,0,0o100644,3,1,1]
        sources.append(dict(path=node,status='symlink-unread',target=literal,device=ns[0],inode=ns[1],uid=0,gid=0,mode=0o777,bytes=len(literal)))
        item=next(v for v in sources if v['path']==target);item.update(status='read-raw',device=ts[0],inode=ts[1],uid=0,gid=0,mode=0o644,bytes=3,sha256=H.sha(b'raw'),base64=base64.b64encode(b'raw').decode())
        proofs.append(dict(node=node,literal_target=literal,fixed_target=target,node_before=ns,node_after=ns.copy(),target_before=ts,target_after=ts.copy(),target_sha256=H.sha(b'raw'),target_alias_of=None))
    report['source_files'].update(raw_source_bytes=9,trees=[dict(path=p,status='absent') for p in H.FOLLOWUP_TREES])
    report['commands']={key:dict(argv=H.UNIT_ARGV,path=path,bytes=len(unit),sha256=H.sha(unit)) for key,path in [('sddm-effective-unit','sddm-effective-unit.txt'),('sddm-effective-unit-after','sddm-effective-unit-after.txt')]}
    report['missing_chain_followup']=dict(schema='arctic-missing-chain-raw-v1',actual_login_shell='/bin/bash',raw_file_inventory=sorted(H.FOLLOWUP_FILES),directory_inventory=sorted(H.FOLLOWUP_TREES),profile_target_proofs=proofs,effective_unit_before='sddm-effective-unit.txt',effective_unit_after='sddm-effective-unit-after.txt',effective_unit_sha256=H.sha(unit),non_atomic_observations=True,complete_startup_chain=False,unsupported_dynamic_chain=[dict(id=name,status='unreviewed',reason='HOST FIXTURE ONLY') for name in H.DYNAMIC_IDS])
    if change:change(report)
    files={'report.json':json.dumps(report).encode(),'system-journal-attest-before.log':journal,'system-journal-attest-after.log':journal,'sddm-effective-unit.txt':unit,'sddm-effective-unit-after.txt':unit}
    manifest=dict(schema='arctic-startup-attestation-files-v1',encoding='zlib+base64',files=[],bytes=sum(len(v) for v in files.values()));chunks=[]
    for name,data in files.items():
        packed=zlib.compress(data);manifest['files'].append(dict(path=name,bytes=len(data),sha256=H.sha(data),compressed_bytes=len(packed),chunks=1));chunks.append(('CHUNK',dict(path=name,index=0,data=base64.b64encode(packed).decode())))
    return [('BEGIN',dict(collector_sha256='a'*64,candidate_source=report['candidate_source'],release_acceptance=False)),('REPORT',report),('MANIFEST',manifest),*chunks,('END',dict(status='attestation-collected-unreviewed',error=None,release_acceptance=False))]
def serial(values):return ''.join('ARCTIC-ATTEST-'+name+' '+json.dumps(value)+'\n' for name,value in values)

class HostTests(unittest.TestCase):
    def test_absent_directories_at_every_boundary_reject_contradictory_metadata(self):
        for path in (*H.FOLLOWUP_TREES,'/etc/profile.d'):
            for field,value in [('children',[]),('children',['missing.sh']),('uid',0),('gid',0),('mode',0o700),('device',1),('inode',2),('mtime_ns',1),('ctime_ns',1)]:
                def mutate(report):
                    tree=next((v for v in report['source_files']['trees'] if v['path']==path),None)
                    if tree is None:tree=dict(path=path,status='absent');report['source_files']['trees'].append(tree)
                    tree[field]=value
                with self.subTest(path=path,field=field,value=value),tempfile.TemporaryDirectory() as temp:
                    out=Path(temp)/'out'
                    with self.assertRaisesRegex(RuntimeError,'Absent directory'):H.extract(serial(transport(mutate)),out,'a'*64)
                    self.assertFalse(out.exists())
    def test_hardlink_observation_is_explicit_and_matches_stat_identity(self):
        def linked(report):
            proofs=report['missing_chain_followup']['profile_target_proofs'];first,second=proofs
            second['target_before']=first['target_before'].copy();second['target_after']=first['target_after'].copy();second['target_alias_of']=first['fixed_target']
            item=next(v for v in report['source_files']['files'] if v['path']==second['fixed_target']);item['device'],item['inode']=first['target_before'][:2]
        with tempfile.TemporaryDirectory() as temp:H.extract(serial(transport(linked)),Path(temp)/'out','a'*64)
        for kind in ('hidden-hardlink','invented-alias','missing-field','boolean-alias'):
            def mutate(report):
                proofs=report['missing_chain_followup']['profile_target_proofs']
                if kind=='hidden-hardlink':linked(report);proofs[1]['target_alias_of']=None
                elif kind=='invented-alias':proofs[1]['target_alias_of']=proofs[0]['fixed_target']
                elif kind=='missing-field':proofs[0].pop('target_alias_of')
                else:proofs[0]['target_alias_of']=False
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp:
                out=Path(temp)/'out'
                with self.assertRaisesRegex(RuntimeError,'hardlink'):H.extract(serial(transport(mutate)),out,'a'*64)
                self.assertFalse(out.exists())
    def test_followup_cannot_hide_path_link_owner_stat_or_dynamic_gaps(self):
        mutations=[lambda r:r.pop('missing_chain_followup'),lambda r:r['missing_chain_followup'].update(complete_startup_chain=0),
          lambda r:r['missing_chain_followup'].update(non_atomic_observations=False),lambda r:r['missing_chain_followup']['raw_file_inventory'].pop(),
          lambda r:r['missing_chain_followup']['profile_target_proofs'][0].update(literal_target='../wrong'),
          lambda r:r['missing_chain_followup']['profile_target_proofs'][0]['node_after'].__setitem__(1,900),
          lambda r:r['missing_chain_followup']['profile_target_proofs'][0]['target_before'].__setitem__(2,False),
          lambda r:r['missing_chain_followup']['profile_target_proofs'][0].update(target_sha256='0'*64),
          lambda r:r['source_files']['trees'].pop(),lambda r:r['source_files']['files'].__setitem__(1,dict(path='/other',status='absent')),
          lambda r:r['missing_chain_followup']['unsupported_dynamic_chain'].pop(),lambda r:r['commands']['sddm-effective-unit'].update(bytes=True)]
        mutations.extend([lambda r:next(v for v in r['source_files']['files'] if v['path']=='/etc/locale.conf').update(uid=0),
            lambda r:next(v for v in r['source_files']['files'] if v['path']=='/etc/locale.conf').update(status='symlink-unread',target='../locale',device=1,inode=2,uid=False,gid=0,mode=0o777,bytes=9)])
        for i,change in enumerate(mutations):
            with self.subTest(i=i),tempfile.TemporaryDirectory() as temp:
                out=Path(temp)/'out'
                with self.assertRaises(RuntimeError):H.extract(serial(transport(change)),out,'a'*64)
                self.assertFalse(out.exists())
    def test_effective_unit_raw_difference_and_duplicate_properties_reject(self):
        for kind in ('raw-difference','duplicate-property'):
            values=transport();chunks=[v for n,v in values if n=='CHUNK' and v['path']=='sddm-effective-unit-after.txt']
            if kind=='raw-difference':data=b'CHANGED\n'
            else:
                data=zlib.decompress(base64.b64decode(chunks[0]['data']))+b'DropInPaths=/unreviewed\n'
            packed=zlib.compress(data);chunks[0]['data']=base64.b64encode(packed).decode()
            item=next(v for v in values[2][1]['files'] if v['path']=='sddm-effective-unit-after.txt');values[2][1]['bytes']+=len(data)-item['bytes']
            item.update(bytes=len(data),sha256=H.sha(data),compressed_bytes=len(packed))
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp,self.assertRaises(RuntimeError):
                H.extract(serial(values),Path(temp)/'out','a'*64)
    def test_listed_conditional_directory_is_typed_and_matches_raw_inventory(self):
        def listed(report):
            report['source_files']['trees'][0].update(status='listed',children=[],uid=1000,gid=1000,mode=0o700,device=1,inode=123,mtime_ns=1,ctime_ns=1)
        with tempfile.TemporaryDirectory() as temp:H.extract(serial(transport(listed)),Path(temp)/'out','a'*64)
        for field,value in [('uid',False),('mode',0o100644),('children',['../escape']),('children',['missing.sh']),('status','symlink-unread')]:
            def mutate(report):listed(report);report['source_files']['trees'][0][field]=value
            with self.subTest(field=field,value=value),tempfile.TemporaryDirectory() as temp,self.assertRaises(RuntimeError):
                H.extract(serial(transport(mutate)),Path(temp)/'out','a'*64)
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
