#!/usr/bin/env python3
"""Separate admission and transport around the exact original BIOS main code."""
import hashlib,json,os,sys,types
from pathlib import Path
import common as C

HERE=Path(__file__).resolve().parent
OBSERVER=C.ROOT/'tools/final-bios-failure-observer'
ORIGINAL=C.ROOT/'tools/final-bios-install'

def sha(raw):return hashlib.sha256(raw).hexdigest()

def load_exact(path,name,expected):
    raw=C.regular(path,1024*1024)
    C.require(sha(raw)==expected,'Observed runtime Source bytes differ')
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module,raw

def owned_modules(manifest):
    """Only import resolution is scoped; original module globals stay intact."""
    pins=manifest['execution_files'];prior={n:sys.modules.get(n) for n in ('common','compose','observer')}
    absent={n for n in prior if n not in sys.modules}
    try:
        old,craw=load_exact(ORIGINAL/'common.py','bios180_common',pins['tools/final-bios-install/common.py'])
        sys.modules['common']=old
        comp,_=load_exact(ORIGINAL/'compose.py','bios180_compose',pins['tools/final-bios-install/compose.py'])
        sys.modules['compose']=comp
        run,rraw=load_exact(ORIGINAL/'run.py','bios180_run',pins['tools/final-bios-install/run.py'])
        observer,_=load_exact(OBSERVER/'observer.py','bios5c74_observer',pins['tools/final-bios-failure-observer/observer.py'])
        sys.modules['observer']=observer
        adapter,_=load_exact(OBSERVER/'composition.py','bios5c74_composition',pins['tools/final-bios-failure-observer/composition.py'])
    finally:
        for name,value in prior.items():
            if name in absent:sys.modules.pop(name,None)
            else:sys.modules[name]=value
    sites=observer.SourceSites()
    sites.bind(old.__dict__,craw,sha(craw),old.__file__,'bios-common')
    sites.bind(run.__dict__,rraw,sha(rraw),run.__file__,'bios-host')
    return old,comp,run,observer,adapter,sites

def finite_failure(record,nonce,source_manifest,adapter):
    """Admission for closed Source dictionaries; arbitrary payloads cannot escape."""
    allowed=source_manifest['allowed_sites']
    if (type(record) is not dict or set(record)!={'schema','outer_source_site','finite_inner_source_records','release_acceptance'}
            or record['schema']!='arctic-bios-finite-host-cause-v1' or record['release_acceptance'] is not False
            or not adapter.finite_site(record['outer_source_site'],allowed)
            or type(record['finite_inner_source_records']) is not list or len(record['finite_inner_source_records'])>8):return None
    raw=b''.join(b'ARCTIC-BIOS-INNER-CAUSE '+json.dumps(row,sort_keys=True,separators=(',',':')).encode()+b'\n'
                 for row in record['finite_inner_source_records'])
    rows=adapter.finite_inner_rows(raw,nonce,allowed)
    if rows!=record['finite_inner_source_records']:return None
    data=json.dumps(record,sort_keys=True,separators=(',',':')).encode()
    return record if len(data)<=65536 else None

def main_adapter(manifest):
    """Keep original functions and main code; expose only explicit dependencies."""
    old,comp,run,observer,adapter,sites=owned_modules(manifest)
    for path in (ORIGINAL/'execution-manifest.json',OBSERVER/'execution-manifest.json'):
        C.require(C.digest_file(path)==manifest['execution_files'][path.relative_to(C.ROOT).as_posix()],
                  'Original or accepted observer manifest bytes differ')
    original_manifest=old.manifest(old.strict_json(old.regular(ORIGINAL/'execution-manifest.json',1024*1024)),True)
    source_manifest=old.strict_json(old.regular(OBSERVER/'execution-manifest.json',1024*1024))
    C.require(source_manifest['ready'] is False and source_manifest['release_acceptance'] is False
              and source_manifest['operational_cli'] is False,'Accepted observer preparation changed')
    channel={'nonce':None,'shell':None,'failure':[]}

    def guard(value,source,inputs=None):
        old.require(value==original_manifest,'Original main manifest projection differs')
        return C.guard(manifest,source,inputs)

    def compose(source,probe,security,context,output):
        result=comp.compose(source,probe,security,context,output)
        original=old.regular(output,1024*1024)
        old.require(sha(original)==result,'Original guest staging differs')
        derived=adapter.derive_guest(original,{'bios-probe':old.regular(probe,128*1024),
            'native-source':old.regular(source/'tools/native-functional/native_smoke.py',512*1024)},
            old.regular(OBSERVER/'observer.py',1024*1024),context,source_manifest['source_site_sha256'])
        pending=output.with_name('guest-observed.pending')
        old.exclusive(pending,derived);pending.replace(output)
        channel['nonce']=context['nonce']
        channel['shell']=adapter.stage_harness(C.ROOT,output.parent/'observed-harness',source_manifest,OBSERVER)
        return sha(derived)

    def argv(source,inputs,guest,vm,value):
        original=run.argv(source,inputs,guest,vm,value)
        old.require(channel['shell'] is not None and original[:2]==['bash',str(C.ROOT/'tools/test-install.sh')],
                    'Original harness transport differs')
        return [original[0],str(channel['shell']),*original[2:]]

    def execute(command,log,seconds,cwd,env):
        copied=env
        if channel['shell'] is not None and command[:2]==['bash',str(channel['shell'])]:
            copied=dict(env,ARCTIC_DICTATION_HOST_TOKEN=channel['nonce'])
        def retain(record):
            value=finite_failure(record,channel['nonce'],source_manifest,adapter)
            if value is not None and len(channel['failure'])<4:channel['failure'].append(value)
        return adapter.capture_failed_execute(run.execute,sites,retain,command,log,seconds,cwd,copied,
            channel['nonce'],source_manifest['allowed_sites'])

    def publish(out,files):
        # Original publication still admits failed status alone, or all strictly
        # screened success originals. Observer failure falls back to original bytes.
        changed=files
        try:
            status=old.strict_json(files['host-status.json'])
            if status['status']=='failed' and channel['failure']:
                extra=dict(status,finite_original_source_failure=channel['failure'])
                raw=(json.dumps(extra,sort_keys=True,indent=2)+'\n').encode()
                scanner=old.load(C.ROOT/'tools/native-functional/screen-evidence.py','bios_observed_host_screen',
                    manifest['execution_files']['tools/native-functional/screen-evidence.py'])
                if scanner.external_text(raw)==raw:changed=dict(files,**{'host-status.json':raw})
        except BaseException:pass
        return run.publish(out,changed)

    dependencies=run.__dict__.copy()
    admission=types.SimpleNamespace(**old.__dict__);admission.guard=guard
    dependencies.update(C=admission,compose=types.SimpleNamespace(compose=compose),argv=argv,execute=execute,publish=publish)
    exact=types.FunctionType(run.main.__code__,dependencies,run.main.__name__,run.main.__defaults__,run.main.__closure__)
    return exact,run,channel

def main():
    value=C.manifest(C.strict_json(C.regular(HERE/'execution-manifest.json',1024*1024)),True)
    exact,original,channel=main_adapter(value)
    return exact()

if __name__=='__main__':raise SystemExit(main())
