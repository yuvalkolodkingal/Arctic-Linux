"""Synthetic strict decoding controls only; no actual guest or startup target."""
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
spec=importlib.util.spec_from_file_location('runtime_host',HERE/'attest-host-v1.py');H=importlib.util.module_from_spec(spec);spec.loader.exec_module(H)
def b64(v):return base64.b64encode(v).decode()

def transport(change=None,message='fixture only',channel='kernel',context_change=None):
    boot='12345678-1234-1234-1234-1234567890ab';journal=(json.dumps(dict(_BOOT_ID=boot.replace('-',''),_TRANSPORT=channel,MESSAGE=message))+'\n').encode()
    security=dict(selinux='Enforcing',avc_records=[],audit_status='enabled 1\nlost 0\n',journal_total_bytes=len(journal),journal_retained_bytes=len(journal),journal_retained_sha256=H.sha(journal),current_boot_journal_records=1)
    status=b'Pid:\t700\nNSpid:\t700\nUid:\t0\t0\t0\t0\nGid:\t0\t0\t0\t0\n';mount=b'1 0 0:1 / /proc rw - proc proc rw\n'
    context=dict(observer_pid=700,pid_namespace='pid:[123]',init_pid_namespace='pid:[123]',NSpid=[700],proc_mount=dict(mount_id='1',parent_id='0',device='0:1',root='/',target='/proc',filesystem='proc'),
                 status_base64=b64(status),status_sha256=H.sha(status),mountinfo_base64=b64(mount),mountinfo_sha256=H.sha(mount),scope='HOST FIXTURE ONLY')
    if context_change:context_change(context)
    context_raw=json.dumps(dict(before=context,after=context.copy(),non_atomic=True)).encode()
    provider_hashes={'/usr/libexec/sddm-helper':'93ab003b0453179eb1f0e6a7a51a20ee322af4992300d095403c5f728b7a68e4','/usr/bin/bash':'379c1bfc53d08815975c647ad7da5d19d8e8a8566ce8097c50231c8b116e5e7b','/usr/bin/python3.14':'0d64bd6d66d68dac91cdadafc46e22d4f09f22bdc997aaae870f42865b024a3e'}
    providers=[dict(path=path,sha256=digest,uid=0,gid=0,mode=0o755,bytes=1024,stable_identity=[1,index+1,0,0,0o100755,1024,1,1]) for index,(path,digest) in enumerate(provider_hashes.items())]
    credential=dict(status='owned-fixture-credential-primitive-collected',provider_sha256=provider_hashes['/usr/bin/python3.14'],raw_sha256='28fc7f0fe284eabe5c08b3e9422ac51d9bd18372c859faf5b51a6f2f6d1a44b8',
        direct_pid=901,direct_start_ticks=1,selected_uid=1000,selected_gid=1000,pidfd_before_release=True,owned_child_reaped=True,all_owned_FDs_closed=True,
        actual_guest=False,Mango_or_renderer_qualification=False,release_acceptance=False,owned_pidfd_identity=dict(pid=901,kernel_fdinfo_bound=True,signal0_permission_checked=True),
        rows=[dict(pid=902,uid=1000,gid=1000,begin=0,end=12,received_monotonic_ns=3,sha256=H.sha(b'OTHER-CHILD\n'),origin='other-sender-unqualified'),
              dict(pid=901,uid=1000,gid=1000,begin=12,end=25,received_monotonic_ns=4,sha256=H.sha(b'OWNED-DIRECT\n'),origin='owned-launch-process')])
    seals=[dict(label=name,status='accepted-exact' if i==0 else 'rejected-expected',FD_closed=True,error=None if i==0 else 'HOST SYNTHETIC EXPECTED REJECTION') for i,name in enumerate(['valid','duplicate','unterminated','unsealed','wrong-owner'])]
    env=[dict(label=label,direct_sha256='1'*64,handoff_sha256='1'*64,bytes=10,byte_exact=True,boundary='owned-quoted-final-Bash-only' if i==3 else 'direct-native-only',actual_session_environment=False) for i,label in enumerate(['ordinary','locale','bytes','quoted-final-bash'])]
    cwd='/tmp/arctic-owned-runtime-fixture';arguments=['space value','line1\nline2','literal;$(touch '+cwd+'/must-not-be-created);`echo literal`'];raw=b''.join(v.encode()+b'\0' for v in arguments)
    argv=dict(status='owned-quoted-argv-byte-exact',arguments=arguments,bash_argv=['/usr/bin/bash','--noprofile','--norc','-c','exec "$@"','owned-final-exec-fixture','/run/arctic-safe/argv-native-v1',*arguments],cwd=cwd,HOME=cwd,BASH_ENV=cwd+'/never-source',absent_BASH_ENV=True,marker_absent=True,direct_sha256=H.sha(raw),quoted_sha256=H.sha(raw),bytes=len(raw),actual_session_argument_fidelity=False,carrier_argument_forwarding=False)
    report=dict(schema='arctic-runtime-prerequisite-report-v1',status='runtime-prerequisite-collected',candidate_source='fe4742c8b9414c45f0bcbb0a4191f116383c60d1',intended_iso_sha256='84c9c88ebcbcaf69dbabf56509a9ceb2db58e5dc41d7bae12093edba12f60718',mango_executable_sha256='ce11ee5cfd24b0393c933e22f7365910d498772e186bb078b9d63a2b42313866',
        boot_id=boot,cmdline='rd.live.image nomodeset',begin_monotonic_ns=1,added_probe_begin_ns=2,added_probe_end_ns=5,end_monotonic_ns=6,providers=providers,CD_pins_sha256=H.sha((HERE/'runtime-probe-pins-v1.json').read_bytes()),
        processes={'mango':dict(pid=800,uid=1000,start_ticks=1,cmdline=['mango'],executable_sha256='ce11ee5cfd24b0393c933e22f7365910d498772e186bb078b9d63a2b42313866'), 'quickshell':dict(pid=801,uid=1000,start_ticks=1,cmdline=['quickshell'],executable_sha256='2'*64)},
        namespace_context_sha256=H.sha(context_raw),observer_pid=700,selected_user=dict(uid=1000,gid=1000,shell='/bin/bash',home='/home/liveuser'),seal_controls=seals,credential_control=credential,environment_controls=env,quoted_argument_control=argv,
        security_before=security.copy(),security_after=security.copy(),own_fixture_attempts=11,own_fixture_processes=16,normal_environment_unchanged=True,normal_environment_sha256='3'*64,
        complete_startup_chain=False,exact_startup_target_bound=False,actual_final_startup_handoff_qualified=False,startup_hook_executed=False,Mango_launched_or_restarted=False,Mango_d=False,renderer='unobserved',active_scanout_pixels='unavailable',release_acceptance=False,safe_visual_gate='open',scope='HOST FIXTURE ONLY')
    if change:change(report)
    files={'report.json':json.dumps(report).encode(),'namespace-context.json':context_raw,'system-journal-prereq-before.log':journal,'system-journal-prereq-after.log':journal}
    manifest=dict(schema='arctic-startup-attestation-files-v1',encoding='zlib+base64',files=[],bytes=sum(len(v) for v in files.values()));chunks=[]
    for name,data in files.items():
        packed=zlib.compress(data);manifest['files'].append(dict(path=name,bytes=len(data),sha256=H.sha(data),compressed_bytes=len(packed),chunks=1));chunks.append(('CHUNK',dict(path=name,index=0,data=b64(packed))))
    return [('BEGIN',dict(collector_sha256='a'*64,candidate_source=report['candidate_source'],release_acceptance=False)),('REPORT',report),('MANIFEST',manifest),*chunks,('END',dict(status='attestation-collected-unreviewed',error=None,release_acceptance=False))]
def serial(values):return ''.join('ARCTIC-ATTEST-'+name+' '+json.dumps(value)+'\n' for name,value in values)

class HostTests(unittest.TestCase):
    def reject(self,change):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'out'
            with self.assertRaises((RuntimeError,ValueError,KeyError)):H.extract(serial(transport(change)),path,'a'*64)
            self.assertFalse(path.exists())
    def test_valid_fixture_decodes_only_limited_collection(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=H.extract(serial(transport()),Path(tmp)/'out','a'*64)
            self.assertFalse(result['exact_startup_target_bound']);self.assertFalse(result['release_acceptance']);self.assertEqual(len(result['files']),4)
    def test_every_unqualified_meaning_flag_rejects(self):
        for name in ['complete_startup_chain','exact_startup_target_bound','actual_final_startup_handoff_qualified','startup_hook_executed','Mango_launched_or_restarted','Mango_d','release_acceptance']:
            for value in (True,0,None):
                with self.subTest(name=name,value=value):self.reject(lambda r:r.update({name:value}))
    def test_provider_hash_owner_mode_type_count_negatives(self):
        for kind in ['hash','uid','gid','mode','bytes','float','stat','duplicate','missing']:
            def change(r):
                row=r['providers'][0]
                if kind=='hash':row['sha256']='0'*64
                elif kind=='uid':row['uid']=False
                elif kind=='gid':row['gid']=1
                elif kind=='mode':row['mode']=0o777
                elif kind=='bytes':row['bytes']=2097153
                elif kind=='float':row['bytes']=1024.0
                elif kind=='stat':row['stable_identity'][4]=0o120755
                elif kind=='duplicate':r['providers'][1]=row
                else:r['providers'].pop()
            with self.subTest(kind=kind):self.reject(change)
    def test_sender_attribution_types_overlap_and_lifecycle_negatives(self):
        cases=[lambda c:c.update(direct_pid=700),lambda c:c.update(direct_pid=901.0),lambda c:c.update(direct_start_ticks=True),lambda c:c.update(all_owned_FDs_closed=1),lambda c:c['owned_pidfd_identity'].update(pid=902),lambda c:c['owned_pidfd_identity'].update(kernel_fdinfo_bound=1),lambda c:c['rows'][0].update(pid=901),lambda c:c['rows'][0].update(uid=1000.0),lambda c:c['rows'][1].update(begin=11),lambda c:c['rows'][0].update(received_monotonic_ns=1),lambda c:c['rows'][0].update(origin='owned-launch-process')]
        for change in cases:self.reject(lambda r:change(r['credential_control']))
    def test_time_count_and_selected_user_types_reject(self):
        cases=[lambda r:r.update(own_fixture_attempts=13),lambda r:r.update(own_fixture_processes=16.0),lambda r:r.update(begin_monotonic_ns=False),lambda r:r.update(added_probe_end_ns=60*10**9+3),lambda r:r.update(end_monotonic_ns=110*10**9+2),lambda r:r['selected_user'].update(uid=1000.0),lambda r:r.update(observer_pid=800)]
        for change in cases:self.reject(change)
    def test_seal_and_environment_outcomes_reject(self):
        cases=[lambda r:r['seal_controls'][0].update(FD_closed=1),lambda r:r['seal_controls'][1].update(status='accepted-exact'),lambda r:r['seal_controls'].pop(),lambda r:r['environment_controls'][1].update(handoff_sha256='2'*64),lambda r:r['environment_controls'][3].update(boundary='direct-native-only'),lambda r:r['environment_controls'][0].update(actual_session_environment=0)]
        for change in cases:self.reject(change)
    def test_quoted_argv_cwd_and_meaning_controls_reject(self):
        cases=[lambda a:a['bash_argv'].__setitem__(4,'exec $@'),lambda a:a.update(cwd='/home/liveuser'),lambda a:a.update(HOME='/home/liveuser'),lambda a:a.update(BASH_ENV='/etc/profile'),lambda a:a.update(marker_absent=1),lambda a:a.update(quoted_sha256='0'*64),lambda a:a.update(actual_session_argument_fidelity=True),lambda a:a['arguments'].__setitem__(0,'split space value')]
        for change in cases:self.reject(lambda r:change(r['quoted_argument_control']))
    def test_trusted_denials_fail_but_sudo_literal_does_not(self):
        for channel,message,valid in [('kernel','avc: denied { read }',False),('audit','type=USER_AVC',False),('sudo','COMMAND=grep avc: denied',True)]:
            with self.subTest(channel=channel),tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp)/'out'
                if valid:H.extract(serial(transport(message=message,channel=channel)),out,'a'*64)
                else:
                    with self.assertRaises(RuntimeError):H.extract(serial(transport(message=message,channel=channel)),out,'a'*64)
                    self.assertFalse(out.exists())
    def test_full_journal_lost_or_count_truncation_fails(self):
        for mutate in [lambda s:s.update(journal_total_bytes=s['journal_total_bytes']+1),lambda s:s.update(current_boot_journal_records=2),lambda s:s.update(selinux='Permissive'),lambda s:s.update(audit_status='enabled 1\nlost 1\n')]:
            self.reject(lambda r:mutate(r['security_after']))
    def test_actual_namespace_raw_scope_and_types_reject(self):
        for mutation in [lambda c:c.update(observer_pid=700.0),lambda c:c.update(NSpid=[True]),lambda c:c.update(init_pid_namespace='pid:[124]'),lambda c:c.update(status_base64=b64(b'Pid:\t701\n')),lambda c:c['proc_mount'].update(target='/different'),lambda c:c.update(mountinfo_base64=b64(b'1 0 0:1 / /proc rw - proc proc rw\n2 0 0:2 / /proc rw - proc proc rw\n'))]:
            with tempfile.TemporaryDirectory() as tmp,self.assertRaises(RuntimeError):
                H.extract(serial(transport(context_change=mutation)),Path(tmp)/'out','a'*64)
    def test_duplicate_reorder_unknown_and_final_truncation_fail(self):
        original=transport()
        cases=[original[:1]+original,original[:2]+[original[3],original[2]]+original[4:],original[:-1]+[('OTHER',{})]+original[-1:]]
        for values in cases:
            with tempfile.TemporaryDirectory() as tmp,self.assertRaises(RuntimeError):H.extract(serial(values),Path(tmp)/'out','a'*64)
        end=serial(original)
        for cut in range(1,len(('ARCTIC-ATTEST-END '+json.dumps(original[-1][1])+'\n').encode())):
            with tempfile.TemporaryDirectory() as tmp,self.assertRaises(RuntimeError):H.extract(end[:-cut],Path(tmp)/'out','a'*64)
    def test_chunk_hash_bomb_path_reserved_and_duplicate_key_fail(self):
        for kind in ['hash','bytes','extra','path','reserved','duplicate']:
            values=transport();manifest=values[2][1];item=manifest['files'][0]
            if kind=='hash':item['sha256']='0'*64
            elif kind=='bytes':item['bytes']=True
            elif kind=='extra':values.insert(-1,values[3])
            elif kind=='path':item['path']='../report.json'
            elif kind=='reserved':item['path']='serial-report.json'
            else:values[1][1]['CD_pins_sha256']='0'*64
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp,self.assertRaises(RuntimeError):H.extract(serial(values),Path(tmp)/'out','a'*64)

if __name__=='__main__':unittest.main(verbosity=2)
