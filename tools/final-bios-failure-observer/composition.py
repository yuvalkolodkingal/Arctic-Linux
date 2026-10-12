#!/usr/bin/env python3
"""Disabled Source adapters. Root must separately prepare an operational guard."""
import ast,base64,hashlib,json,os,pathlib,re,stat,sys,types
import observer

def sha(raw):return hashlib.sha256(raw).hexdigest()

def embedded_driver(raw):
    begin=b"read -r -d '' DRIVER <<'PY' || true\n";start=raw.index(begin)+len(begin)
    return raw[start:raw.index(b'\nPY\n',start)]

def stage_harness(execution,destination,manifest,source_dir):
    """One transport-only command substitution; original DRIVER stays byte exact."""
    if destination.exists():raise ValueError('Owned stage already exists')
    raw=(execution/'tools/test-install.sh').read_bytes()
    if sha(raw)!=manifest['original_execution_files']['tools/test-install.sh']:raise ValueError('Original shell differs')
    if sha(embedded_driver(raw))!=manifest['driver_sha256']:raise ValueError('Original driver differs')
    needle=b'python3 -c "$DRIVER" || rc=$?'
    if raw.count(needle)!=1:raise ValueError('Original driver launch differs')
    changed=raw.replace(needle,b'python3 /arctic-lib/driver-entry.py || rc=$?',1)
    (destination/'tools/lib').mkdir(parents=True,mode=0o700)
    (destination/'tools/test-install.sh').write_bytes(changed)
    for name in ('container.sh','vmtest.py'):
        source=execution/'tools/lib'/name;data=source.read_bytes()
        if sha(data)!=manifest['original_execution_files']['tools/lib/'+name]:raise ValueError('Original library differs')
        (destination/'tools/lib'/name).write_bytes(data)
    for name in ('observer.py','driver-entry.py'):
        data=(source_dir/name).read_bytes()
        if sha(data)!=manifest['observer_execution_files']['tools/final-bios-failure-observer/'+name]:raise ValueError('Observer source differs')
        (destination/'tools/lib'/name).write_bytes(data)
    (destination/'tools/lib/observer-manifest.json').write_text(json.dumps(manifest,sort_keys=True)+'\n')
    return destination/'tools/test-install.sh'

def derive_guest(original,source_raw,observer_raw,context,source_pins):
    """Retain every original decoded module/function and original failure handler."""
    text=original.decode();needle='    result=_modules["bios_probe"].main(sys.argv[1],_context,_modules["native_bios_source"],interval)'
    if text.count(needle)!=1:raise ValueError('Original guest invocation differs')
    bootstrap=['_observer_raw=base64.b64decode('+repr(base64.b64encode(observer_raw).decode())+',validate=True)',
               'assert hashlib.sha256(_observer_raw).hexdigest()=='+repr(sha(observer_raw)),
               '_observer=types.ModuleType("bios_finite_source_observer")',
               'exec(compile(_observer_raw,"/run/t/bios-source-observer.py","exec"),_observer.__dict__)',
               '_sites=_observer.SourceSites()',
               '_sites.bind(_modules["bios_probe"].__dict__,base64.b64decode('+repr(base64.b64encode(source_raw['bios-probe']).decode())+'),'+repr(source_pins['bios-probe'])+',"/run/t/guest-check.py","bios-probe")',
               '_sites.bind(_modules["native_bios_source"].__dict__,base64.b64decode('+repr(base64.b64encode(source_raw['native-source']).decode())+'),'+repr(source_pins['native-source'])+',"/run/t/guest-check.py","native-source")']
    marker='try:\n    assert len(sys.argv)==2'
    if text.count(marker)!=1:raise ValueError('Original guest execution envelope differs')
    text=text.replace(marker,'\n'.join(bootstrap)+'\n'+marker,1)
    replacement='    result=_sites.invoke(_modules["bios_probe"].main,lambda cause:_observer.emit_guest(cause,_context),sys.argv[1],_context,_modules["native_bios_source"],interval)'
    derived=text.replace(needle,replacement,1).encode()
    if len(derived)>1024*1024:raise ValueError('Original guest Source byte bound exceeded')
    return derived

def finite_site(value,allowed_sites):
    return (type(value) is dict and set(value)=={'source','source_sha256','function','source_line','site_kind','fixed_assertion_label'}
            and type(value['source_line']) is int and value['source_line']>0
            and all(type(value[k]) is str for k in value if k!='source_line')
            and value in allowed_sites)

def finite_inner_rows(raw,nonce,allowed_sites):
    """Retain closed Source records only; no raw log lines or operands escape."""
    if type(raw) is not bytes or len(raw)>256*1024*1024 or not re.fullmatch('[0-9a-f]{32}',nonce):return []
    rows=[]
    for line in raw.splitlines():
        if line.startswith(b'ARCTIC-BIOS-INNER-CAUSE '):
            if len(line)>8192:continue
            try:
                def fields(items):
                    value={}
                    for key,item in items:
                        if key in value:raise ValueError('Duplicate finite field')
                        value[key]=item
                    return value
                value=json.loads(line.split(b' ',1)[1],object_pairs_hook=fields)
                if type(value) is not dict or set(value)!={'schema','nonce','cause','release_acceptance'} or value['schema']!='arctic-bios-inner-source-cause-v1' or value['nonce']!=nonce or value['release_acceptance'] is not False:continue
                cause=value['cause']
                if type(cause) is not dict or not finite_site(cause.get('site'),allowed_sites):continue
                if cause.get('event')=='nonzero-original-stage-return':
                    flags=cause.get('executed_false_flag_sites')
                    valid=(set(cause)=={'event','site','executed_false_flag_sites'} and cause['site']['site_kind']=='return'
                           and cause['site']['source']=='install-driver' and cause['site']['function'] in ('stage_install','stage_boot')
                           and type(flags) is list and len(flags)<=16 and all(finite_site(x,allowed_sites) and x['site_kind']=='false-flag' and x['function']==cause['site']['function'] for x in flags))
                elif cause.get('event')=='escaping-source-exception':
                    prior=cause.get('retained_original_primary_site')
                    valid=(set(cause)=={'event','site','retained_original_primary_site'} and cause['site']['site_kind'] in ('raise','require')
                           and (prior is None or finite_site(prior,allowed_sites) and prior['site_kind'] in ('raise','require')))
                else:valid=False
                if valid and len(rows)<8:rows.append(value)
            except (ValueError,UnicodeError,RecursionError):pass
    return rows

def capture_failed_execute(original,sites,emit,argv,log,seconds,cwd,env,nonce,allowed_sites):
    """Retain finite original failure before main's owned image cleanup."""
    try:return sites.invoke(original,lambda ignored:None,argv,log,seconds,cwd,env)
    except BaseException as error:
        try:
            outer=sites.describe(error)
            inner=[];fd=None
            try:
                fd=os.open(log,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
                before=os.fstat(fd);limit=256*1024*1024
                if stat.S_ISREG(before.st_mode) and before.st_uid==os.geteuid() and before.st_nlink==1 and not before.st_mode&0o022 and 0<before.st_size<=limit:
                    with os.fdopen(fd,'rb',closefd=False) as stream:data=stream.read(limit+1)
                    after=os.fstat(fd)
                    fields=lambda x:(x.st_dev,x.st_ino,x.st_uid,x.st_mode,x.st_nlink,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
                    if fields(before)==fields(after) and len(data)==before.st_size:
                        inner=finite_inner_rows(data,nonce,allowed_sites)
            except (OSError,ValueError):pass
            finally:
                if fd is not None:os.close(fd)
            if outer is not None:emit({'schema':'arctic-bios-finite-host-cause-v1','outer_source_site':outer,
                                     'finite_inner_source_records':inner,'release_acceptance':False})
        except BaseException:pass
        raise

def main():
    # No activation path is shipped in this Source preparation. Even a copied
    # old ready marker must never dispatch the observed helper from this leaf.
    raise SystemExit('BIOS finite failure observer is disabled Source preparation')

if __name__=='__main__':main()
