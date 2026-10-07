"""Pure owned fixture primitive. No CLI, startup hook, journal collector or VM."""
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent

def probe(root,exe,expected_exe_sha,uid,gid):
    if os.geteuid()!=0 or type(uid) is not int or type(gid) is not int or uid<=0 or gid<=0:
        raise RuntimeError('Requires exact root observer and positive selected-user identity')
    spec=importlib.util.spec_from_file_location('owned_credential_toolkit',HERE/'toolkit.py')
    T=importlib.util.module_from_spec(spec);spec.loader.exec_module(T)
    if T.sha(Path(exe).read_bytes())!=expected_exe_sha:raise RuntimeError('Fixture provider hash differs')
    code='import os\nchild=os.fork()\nif child==0:\n os.write(2,b"OTHER-CHILD\\n");os._exit(0)\nos.waitpid(child,0)\nos.write(2,b"OWNED-DIRECT\\n")\n'
    logger=T.OwnedLog(Path(root),max_raw=65536,max_seconds=5)
    result=logger.capture(exe,[exe,'-I','-S','-c',code],expected_exe_sha,Path(exe).stat().st_uid,
                          environment={b'PATH':b'/usr/bin:/bin',b'LANG':b'C.UTF-8'},execution_identity={'uid':uid,'gid':gid})
    raw=(logger.root/'stderr.raw').read_bytes()
    if raw!=b'OTHER-CHILD\nOWNED-DIRECT\n':raise RuntimeError('Credential fixture bytes differ')
    direct=[r for r in result['rows'] if r['pid']==result['child_pid']]
    other=[r for r in result['rows'] if r['pid']!=result['child_pid']]
    if len(direct)!=1 or len(other)!=1:raise RuntimeError('Credential range boundaries/identities unavailable')
    if any(r['uid']!=uid or r['gid']!=gid for r in direct+other):raise RuntimeError('Actual dropped kernel credentials differ')
    writer={'pid':result['child_pid'],'uid':uid,'gid':gid}
    lines=T.authenticated_lines(raw,result['rows'],writer)
    if [r['authenticated_writer'] for r in lines]!=[False,True]:raise RuntimeError('Inherited writer wrongly attributed')
    if not logger.reaped or logger.pidfd is not None:raise RuntimeError('Owned fixture cleanup incomplete')
    return {'status':'owned-fixture-credential-primitive-collected','provider_sha256':expected_exe_sha,
            'direct_pid':result['child_pid'],'direct_start_ticks':result['owned_child_start_ticks'],
            'selected_uid':uid,'selected_gid':gid,'rows':result['rows'],'raw_sha256':hashlib.sha256(raw).hexdigest(),
            'pidfd_before_release':True,'owned_pidfd_identity':result['owned_pidfd_identity'],'owned_child_reaped':True,'all_owned_FDs_closed':True,
            'actual_guest':False,'Mango_or_renderer_qualification':False,'release_acceptance':False}
