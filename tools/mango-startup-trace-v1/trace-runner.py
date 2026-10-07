"""Separate source-gated one-ISO trace runner; normal Safe runner is untouched."""
import sys
sys.dont_write_bytecode=True
import argparse,datetime,hashlib,importlib.util,json,os,shutil,signal,subprocess,uuid
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE='5a30dd419bc7478c951ce11bb9f9227e59c18b16'
SOURCE='fe4742c8b9414c45f0bcbb0a4191f116383c60d1'
def require(v,m):
    if not v:raise RuntimeError(m)
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
S=load('unchanged_normal_safe',HERE.parent/'safe-visual-diagnostic/safe-runner-v1.py')
CORE={'README.md','candidate-wayland-session.fixture','controller.py','credential-units.py','native-handoff','native-handoff.c','owned-log.py','owned-logger.py','prepare.py','request-stop.py','runtime-pins.json','sealed_environment.py','test_trace_core.py','test_trace_setup.py','test_trace_transport.py','transport.py'}
OWN={'adapter-contract.json','candidate-boundary-pins.json','core-authority.json','normal-base-pins.json','stage.py','stop-driver.py','trace-runner.py','test_adapter.py','ADAPTER.md','normal-controls.py'}
FILES=S.EXECUTION_FILES|{'tools/safe-visual-diagnostic/execution-pins-safe-v1.json'}|{'tools/mango-startup-trace-v1/'+n for n in CORE|OWN}|{'tools/mango-startup-trace-v1/normal-control-sources/'+n for n in ('normal-test-iso.sh','normal-iso.yml','base-test-iso.sh','base-iso.yml','vm-only-recovery-v2.py')}
def flags(env,R):
    S.validate_ci(env,R)
    require(env.get('MANGO_STARTUP_TRACE_MODE')=='true','Trace flag must be explicitly selected')
    raw=json.loads(env.get('MANGO_TRACE_ALL_INPUTS','{}'))
    allowed={'mango_startup_trace','safe_visual_diagnostic','same_iso_recovery','release','tag','prerelease','draft','nix_acceptance','performance_acceptance','boot_test'}
    require(type(raw) is dict and set(raw)<=allowed and set(raw)>=allowed-{'tag'},'Missing/unknown trace workflow inputs')
    for k in allowed-{'tag'}:require(type(raw[k]) is bool,'Typed workflow boolean required')
    require(raw['mango_startup_trace'] is raw['safe_visual_diagnostic'] is True and all(raw[k] is False for k in ('same_iso_recovery','release','draft','nix_acceptance','performance_acceptance','boot_test')) and raw.get('tag','')=='','Trace cannot mix build/release/update/install modes')
def material(args):
    root=args.bundle.parents[1];manifest=json.loads((args.bundle/'execution-pins-trace-v1.json').read_text())
    require(manifest['schema']=='arctic-mango-trace-execution-v1' and manifest['candidate_source']==SOURCE and manifest['normal_base']==BASE and set(manifest['files'])==FILES,'Trace execution map identity/set differs')
    for rel,row in manifest['files'].items():
        p=root/rel;require(not p.is_symlink() and p.is_file() and digest(p)==row['sha256'] and p.stat().st_size==row['bytes'] and p.stat().st_mode&0o777==row['mode'],'Exact trace source/mode differs: '+rel)
    normal=json.loads((args.bundle/'normal-base-pins.json').read_text())
    require(set(normal)==S.EXECUTION_FILES|{'tools/safe-visual-diagnostic/execution-pins-safe-v1.json'},'Normal baseline set differs')
    for rel,h in normal.items():
        if rel not in ('tools/test-iso.sh','.github/workflows/iso.yml'):require(digest(root/rel)==h,'Normal Safe source/body changed: '+rel)
    authority=json.loads((args.bundle/'core-authority.json').read_text())
    require(authority['ready_sha256']=='e66c81f3778c75a91fa688cbdac8a5b091127e46a621ec05ce511f937cc75c8c' and authority['adapter_contract_sha256']=='696feff9fd040f0b186e0c9c415da96f6ef3d820710616b968c505925662ccf7','Core authority differs')
    require(set(authority['files'])==CORE,'Frozen core authority set differs')
    for n,h in authority['files'].items():require(digest(args.bundle/n)==h,'Frozen core changed: '+n)
    require(digest(args.bundle/'adapter-contract.json')==authority['adapter_contract_sha256'],'Core adapter contract changed')
    return manifest
def sources(args,R):
    R.verify_sources(args.source,args.recovery_bundle,S.BASE)
    root=args.bundle.parents[1]
    def git(*v):return subprocess.check_output(['git','--no-optional-locks','-C',str(root),*v],text=True).strip()
    head=git('rev-parse','HEAD');require(head==os.environ['GITHUB_SHA'] and head!=BASE and not git('status','--porcelain'),'Trace execution must be new clean committed head')
    subprocess.run(['git','--no-optional-locks','-C',str(root),'merge-base','--is-ancestor',BASE,head],check=True,timeout=30)
    changed=set(git('diff','--name-only',BASE,head).splitlines())
    allowed=FILES|{'tools/mango-startup-trace-v1/execution-pins-trace-v1.json','tools/mango-startup-trace-v1/independent-review.json'}
    require(changed<=allowed and {'tools/test-iso.sh','.github/workflows/iso.yml'}<=changed,'Trace branch scope exceeds reviewed adapter')
    manifest=material(args)
    modes={line.split('\t',1)[1]:line.split()[0] for line in git('ls-files','-s','--',*sorted(FILES)).splitlines()}
    require(set(modes)==FILES and all(modes[rel]==('100755' if row['mode']&0o111 else '100644') for rel,row in manifest['files'].items()),'Committed trace executable modes differ')
    reviewpath=args.bundle/'independent-review.json'
    require(reviewpath.is_file() and not reviewpath.is_symlink() and 0<reviewpath.stat().st_size<=1048576,'Independent review file unsafe/overbound')
    review=json.loads(reviewpath.read_text())
    require(review.get('status')=='SOURCE_AND_HOST_CONTROLS_PASS_VM_UNRUN' and review.get('all_controls_passed') is True and review.get('blocking_source_findings')==[] and review.get('execution_manifest_sha256')==digest(args.bundle/'execution-pins-trace-v1.json'),'Independent whole core+adapter review missing/mismatched')
    return manifest
def proof(args,R):
    return dict(schema='arctic-mango-trace-execution-v1',candidate_source=SOURCE,normal_base=BASE,execution_checker_head=os.environ['GITHUB_SHA'],execution_manifest_sha256=digest(args.bundle/'execution-pins-trace-v1.json'),independent_review_sha256=digest(args.bundle/'independent-review.json'),common_v2_sha256=S.COMMON_SHA,original_normal_source_unchanged=True,startup_perturbation=True,normal_session_fidelity=False,safe_visual_gate='OPEN',release_acceptance=False)
def preflight(args,R):
    flags(os.environ,R);sources(args,R)
    require(not args.inputs.exists() and not args.evidence.exists(),'Trace inputs/evidence must be unused')
    args.evidence.mkdir(parents=True)
    docker=R.require_docker();require(Path('/dev/kvm').is_char_device(),'KVM required; no fallback')
    require(shutil.disk_usage(args.evidence).free>=20_000_000_000,'Trace requires20GB free')
    run=R.api('actions/runs/'+str(R.ORIGINAL_RUN));pages=R.api('actions/runs/'+str(R.ORIGINAL_RUN)+'/jobs?filter=all&per_page=100',paginate=True);artifact=R.api('actions/artifacts/'+str(R.ARTIFACT_ID))
    value=proof(args,R);value.update(original_result=R.validate_original(run,[j for p in pages for j in p['jobs']],artifact),docker_server_version=docker,artifact=dict(id=R.ARTIFACT_ID,name=R.ARTIFACT_NAME,original_run=R.ORIGINAL_RUN,archive_bytes=R.ARCHIVE_BYTES,archive_digest=R.ARCHIVE_DIGEST))
    R.write_json(args.evidence/'preflight.json',value)
def verify(args,R):
    flags(os.environ,R);sources(args,R)
    value=json.loads((args.evidence/'preflight.json').read_text());require(all(value.get(k)==v for k,v in proof(args,R).items()),'Trace preflight belongs to another execution')
    value['iso']=R.verify_iso(args.inputs);R.write_json(args.evidence/'verified-input.json',value)
    for rel in R.METADATA_PINS:
        p=args.evidence/'input-metadata'/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(args.inputs/rel,p)
def run(args,R):
    verify(args,R);R.require_docker();require(Path('/dev/kvm').is_char_device(),'KVM disappeared')
    base=args.evidence.parent/'mango-trace-vm';require(not base.exists(),'Owned trace VM output must be unused')
    vm=base/'uefi-safe';container='arctic-paired-mango-trace-'+uuid.uuid4().hex
    env=dict(os.environ,CONTAINER_ENGINE='docker',ARCTIC_VM_CONTAINER_NAME=container)
    state=dict(**proof(args,R),status='running')
    def save():state['recorded_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();R.write_json(args.evidence/'execution.json',state)
    def interrupted(number,frame):raise InterruptedError('Owned trace interrupted: '+str(number))
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted);save()
    try:
        # Repeat actual source/ISO proof immediately before the only VM route.
        verify(args,R)
        argv=['bash',str(args.bundle.parents[1]/'tools/test-iso.sh'),'--iso',str(args.inputs/'iso'/R.ISO),'--kvm','--firmware','uefi','--mode','safe','--memory','4096','--smp','2','--timeout','600','--interval','60','--debug','--safe-diagnostic',str(args.bundle.parent/'safe-visual-diagnostic'),'--mango-startup-trace','--out',str(base)]
        try:R.execute(argv,args.evidence/'safe-harness.log',2100,args.bundle.parents[1],env,container)
        finally:state['evidence']=R.preserve_phase(vm,args.evidence,'boot');save()
        serial=(args.evidence/'boot/serial.log').read_text(errors='strict')
        state['guest']=S.extract(serial,args.evidence/'guest-telemetry',digest(args.bundle.parent/'safe-visual-diagnostic/guest-safe-collector-v1.py'))
        state['events']=S.validate_events(args.evidence/'boot/safe-events.log')
        require(len(state['events']['capture_names'])==34 and all(n in state['evidence'] for n in state['events']['capture_names']),'All original34 actual frames required')
        T=load('exact_trace_transport',args.bundle/'transport.py');report,bodies=T.decode(serial);T.validate_evidence(report,bodies)
        require(report['boot_id']==state['guest']['report']['boot_id'],'Trace and original34 collector boot differ')
        require(sum(len(b) for b in bodies.values())+sum(v['bytes'] for v in state['guest']['files'].values())<=S.MAX_TOTAL and len(bodies)+len(state['guest']['files'])<=128,'Combined original/trace telemetry exceeds original bounds')
        target=args.evidence/'trace-telemetry';require(not target.exists(),'Trace extracted target must be unused');target.mkdir()
        for name,body in bodies.items():(target/name).write_bytes(body)
        state.update(status='diagnostic_collected_visual_gate_open',trace_report=report,trace_files={n:dict(bytes=len(v),sha256=hashlib.sha256(v).hexdigest()) for n,v in bodies.items()});save()
    except BaseException as exc:state.update(status='failed_or_unrun',error=str(exc));save();raise
def main():
    p=argparse.ArgumentParser();p.add_argument('phase',choices=('preflight','verify','run'))
    for n in ('source','bundle','recovery-bundle','inputs','evidence'):p.add_argument('--'+n,type=Path,required=True)
    args=p.parse_args()
    for n in ('source','bundle','recovery_bundle','inputs','evidence'):setattr(args,n,getattr(args,n).resolve())
    R=S.recovery(args)
    try:globals()[args.phase](args,R)
    except BaseException as exc:
        if args.evidence.exists():R.write_json(args.evidence/('blocked-'+args.phase+'.json'),dict(error=str(exc),release_acceptance=False,safe_visual_gate='OPEN'))
        raise
if __name__=='__main__':main()
