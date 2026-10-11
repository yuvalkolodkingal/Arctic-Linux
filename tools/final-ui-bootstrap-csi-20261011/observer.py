#!/usr/bin/env python3
"""Disabled exact current UI failure observation and private original snapshots.
No diagnostic member provides whole UART, PAM, UI or release qualification.
"""
import ast,base64,builtins,dis,hashlib,json,os,re,stat,subprocess,sys,types,zlib
from pathlib import Path
import originals as O
BASE='44c789f068a49d642b5122288ccccca767f1ddc0'
PREFIX='tools/final-installed-ui-settings-readiness/'
SCANNER='tools/native-functional/screen-evidence.py'
SCANNER_SHA='0c2176c4892e45e485eeac32f564fdfe9fb1619f142ac0b60babeed52924075f'
MATCH_SHA='ca9129f10813699883429be9481b8311468fa724d406714ad38578f3ed4acda7'
ORIGINALS_SHA='ece49eec8188355399561e6eda1acd6ee6edfd007fa7afb9f40c262be153cfdc'
ABSENT=object()
FAILED_TAIL='  if (( rc != 0 )); then tail -n 120 "$OUT"/serial-*.log || true; fi'
PRIVATE_TAIL='  : # Failed whole original UART remains private until strict screening.'
def require(value):
    if not value:raise ValueError('Closed UI Source evidence binding differs')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(raw,path,name):
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__);return module
def codes(code):
    yield code
    for value in code.co_consts:
        if type(value)is types.CodeType:yield from codes(value)

def inside(position,node):
    return(position.lineno is not None and position.col_offset is not None
        and(node.lineno,node.col_offset)<=(position.lineno,position.col_offset)
        and(position.end_lineno,position.end_col_offset)<=(node.end_lineno,node.end_col_offset))

class OwnedSource:
    def __init__(self,namespace,raw,filename,key):
        self.namespace=namespace;self.raw=raw;self.key=key;self.digest=sha(raw);self.bound={}
        parsed=ast.parse(raw);expected={(c.co_qualname,c.co_firstlineno):c for c in codes(compile(raw,filename,'exec'))}
        self.nodes=list(ast.walk(parsed))
        for name,function in tuple(namespace.items()):
            if type(function)is not types.FunctionType or function.__globals__ is not namespace:continue
            code=function.__code__;wanted=expected.get((code.co_qualname,code.co_firstlineno))
            if wanted is None:continue
            require(code==wanted and code.co_filename==filename and tuple(code.co_lines())==tuple(wanted.co_lines()))
            builtin_namespace=namespace.get('__builtins__',builtins.__dict__)
            if type(builtin_namespace)is types.ModuleType:builtin_namespace=builtin_namespace.__dict__
            require(type(builtin_namespace)is dict)
            refs={n:namespace.get(n,ABSENT)for n in code.co_names}
            builtin_refs={n:builtin_namespace.get(n,ABSENT)for n,v in refs.items()if v is ABSENT}
            require(all(v is builtins.__dict__.get(n,ABSENT)for n,v in builtin_refs.items()))
            self.bound[code]=(name,function,code,refs,builtin_namespace,builtin_refs,
                {i.offset:i for i in dis.get_instructions(code,show_caches=True)})
    def owns(self,frame):
        value=self.bound.get(frame.f_code)
        if value is None:return False
        name,function,code,refs,namespace,builtin_refs,_=value
        return(self.namespace.get(name,ABSENT)is function and frame.f_code is code and function.__code__ is code and function.__globals__ is frame.f_globals
            and frame.f_globals is self.namespace and frame.f_builtins is namespace
            and all(frame.f_globals.get(n,ABSENT)is v for n,v in refs.items())
            and all(frame.f_builtins.get(n,ABSENT)is v for n,v in builtin_refs.items()))
    def unchanged(self):
        for name,function,code,refs,namespace,builtin_refs,_ in self.bound.values():
            if(self.namespace.get(name,ABSENT)is not function or function.__code__ is not code or function.__globals__ is not self.namespace
                or any(self.namespace.get(n,ABSENT)is not v for n,v in refs.items())
                or any(namespace.get(n,ABSENT)is not v for n,v in builtin_refs.items())):return False
        return True
    def require_raise(self,frame,offset):
        if not self.owns(frame)or frame.f_code is not self.namespace.get('require').__code__:return False
        instruction=self.bound[frame.f_code][-1].get(offset)
        if instruction is None or instruction.opname!='RAISE_VARARGS':return False
        line=next((n for a,b,n in frame.f_code.co_lines()if a<=offset<b),None)
        if line!=instruction.positions.lineno:return False
        candidates=[n for n in self.nodes if isinstance(n,ast.Raise)and inside(instruction.positions,n)]
        return(len(candidates)==1 and isinstance(candidates[0].exc,ast.Call)
            and isinstance(candidates[0].exc.func,ast.Name)and candidates[0].exc.func.id=='RuntimeError'
            and len(candidates[0].exc.args)==1 and isinstance(candidates[0].exc.args[0],ast.Name)
            and candidates[0].exc.args[0].id=='message')
    def site(self,frame,offset,kinds):
        if not self.owns(frame):return None
        instruction=self.bound[frame.f_code][-1].get(offset)
        if instruction is None:return None
        line=next((n for a,b,n in frame.f_code.co_lines()if a<=offset<b),None)
        if line!=instruction.positions.lineno:return None
        found=[]
        for node in self.nodes:
            if not hasattr(node,'lineno')or not hasattr(node,'end_lineno')or not inside(instruction.positions,node):continue
            label=None;kind=None
            if isinstance(node,ast.Call)and isinstance(node.func,ast.Attribute)and node.func.attr=='require':
                kind='require';label=node.args[1].value if len(node.args)>1 and isinstance(node.args[1],ast.Constant)and type(node.args[1].value)is str else None
            elif isinstance(node,ast.Raise):
                if isinstance(node.exc,ast.Call)and isinstance(node.exc.func,ast.Name)and node.exc.func.id=='RuntimeError':
                    kind='raise';label=node.exc.args[0].value if node.exc.args and isinstance(node.exc.args[0],ast.Constant)and type(node.exc.args[0].value)is str else None
                elif isinstance(node.exc,ast.Name)and node.exc.id=='error'and frame.f_code.co_name=='reject_sensitive_match':
                    assignments=[n for n in self.nodes if isinstance(n,ast.Assign)and isinstance(n.value,ast.Call)and isinstance(n.value.func,ast.Name)and n.value.func.id=='RuntimeError'and any(isinstance(t,ast.Name)and t.id=='error'for t in n.targets)]
                    if len(assignments)==1 and assignments[0].value.args and isinstance(assignments[0].value.args[0],ast.Constant):
                        kind='raise';label=assignments[0].value.args[0].value
            if kind in kinds and type(label)is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _./():=+-]{0,119}',label):
                found.append({'source':self.key,'source_sha256':self.digest,'function':frame.f_code.co_qualname,
                    'source_line':node.lineno,'site_kind':kind,'fixed_assertion_label':label})
        return found[0]if len(found)==1 else None

def finite_match(helper,vocabulary,scanner,frame):
    """Same real rejected Match only; omit operand lengths, values and digests."""
    row=helper.annotated_match(scanner,frame.f_locals.get('match'),frame.f_locals.get('phase'),
        frame.f_locals.get('original'),frame.f_locals.get('boundaries'),frame.f_locals.get('removed'))
    diagnostic=row.get('source_match_diagnostic')
    keys=('regex','offsets','mapping','source_rule','candidate_reason','family_reason')
    require(type(diagnostic)is dict)
    result={k:diagnostic[k]for k in keys}
    require(all(type(v)is str and v in vocabulary for v in result.values()))
    return dict(result,privacy_admitted=False,runtime_cause_proven=False,operand_value_or_digest_exported=False)


def diagnostic_transport(common,raw_common):
    """Separate diagnostic parser. The original complete-UART gate is unchanged.
    Exact original framing/context/chunk/manifest/hash/report predicates remain;
    only this incomplete-evidence parser omits whole-wire admission and writes.
    """
    nodes=[n for n in ast.parse(raw_common).body if isinstance(n,ast.FunctionDef)and n.name=='decode']
    require(len(nodes)==1)
    node=nodes[0];text=''.join(raw_common.decode().splitlines(keepends=True)[node.lineno-1:node.end_lineno])
    replacements=(
        ('def decode(wire, context, scanner, output):','def diagnostic_transport(wire, context, scanner):'),
        ('    require(scanner.external_text(wire) == wire, \'Whole original screening altered bytes\')\n',''),
        ('    output.mkdir(mode=0o700)\n    for name,data in decoded.items(): exclusive(output/name,data)\n    return value, inventory\n','    return value, inventory, decoded\n'))
    for old,new in replacements:
        require(text.count(old)==1);text=text.replace(old,new,1)
    namespace=common.__dict__.copy();exec(compile(text,common.__file__+'::diagnostic-only-transport','exec'),namespace)
    return namespace['diagnostic_transport'],text,replacements

BOOTSTRAP_HELPER_SHA='6b5627a78cda5a3c94ff9ec3dae4c7af667a6add70cc78b69942f91586fbe40c'
BOOTSTRAP_VMTEST_SHA='e3e469bdfb3510c47aa51986cb09a3ef155c73b0496bc4a45dc2db07ebe670e6'
ORIGINAL_VMTEST_SHA='25ca7b0eba1a403c28b897edc80939aead976f5809f0865df3d21b44b1615df6'
BOOTSTRAP_MEMBER='host-ui-bootstrap-observation.json'
BOOTSTRAP_ENV='ARCTIC_NATIVE_BOOTSTRAP_TOKEN'

def bootstrap_module():
    raw,_=O.read_regular(Path(__file__).with_name('native_bootstrap_observer.py'),1024*1024)
    require(sha(raw)==BOOTSTRAP_HELPER_SHA)
    module=load(raw,Path(__file__).with_name('native_bootstrap_observer.py'),'ui_owned_native_bootstrap_helper')
    return module,OwnedSource(module.__dict__,raw,module.__file__,'ui-bootstrap-helper')

def write_setup_owned(path,raw,owned):
    """Register owned creation before deferred setup cancellation can arrive."""
    signals={O.signal.SIGINT,O.signal.SIGTERM}
    saved=O.signal.pthread_sigmask(O.signal.SIG_BLOCK,signals)
    try:
        require(type(raw)is bytes and 0<len(raw)<=1024*1024)
        with O.owned_fd(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)as fd:
            generation=os.fstat(fd)
            try:
                require(stat.S_ISREG(generation.st_mode)and generation.st_uid==os.geteuid()
                    and generation.st_nlink==1 and stat.S_IMODE(generation.st_mode)==0o600
                    and generation.st_size==0)
                at=0
                while at<len(raw):
                    count=os.write(fd,memoryview(raw)[at:]);require(type(count)is int and count>0);at+=count
                final=os.fstat(fd)
                require(final.st_size==len(raw)and O.same(final,path.lstat()))
                owned[path.name]=(raw,final)
            except BaseException:
                # Only the inode held by this exclusive creation may be removed.
                try:
                    current=path.lstat();held=os.fstat(fd)
                    require((current.st_dev,current.st_ino)==(generation.st_dev,generation.st_ino)
                        and O.same(current,held)and stat.S_ISREG(current.st_mode)
                        and current.st_uid==os.geteuid()and current.st_nlink==1
                        and stat.S_IMODE(current.st_mode)==0o600)
                    path.unlink()
                except BaseException:pass
                raise
    finally:O.signal.pthread_sigmask(O.signal.SIG_SETMASK,saved)

def bootstrap_library(private,common):
    # A private read-only container mount selects exact reviewed physical modules.
    canonical,_=O.read_regular(common.ROOT/'tools/lib/vmtest.py',1024*1024)
    require(sha(canonical)==ORIGINAL_VMTEST_SHA)
    directory(private);holder=private/'ui-bootstrap-lib';generation=None;files={}
    try:
        saved=O.signal.pthread_sigmask(O.signal.SIG_BLOCK,{O.signal.SIGINT,O.signal.SIGTERM})
        try:holder.mkdir(mode=0o700);generation=directory(holder)
        finally:O.signal.pthread_sigmask(O.signal.SIG_SETMASK,saved)
        for target,name,digest in (('vmtest.py','vmtest-observed.py',BOOTSTRAP_VMTEST_SHA),
                                  ('native_bootstrap_observer.py','native_bootstrap_observer.py',BOOTSTRAP_HELPER_SHA)):
            raw,source=O.read_regular(Path(__file__).with_name(name),1024*1024)
            require(sha(raw)==digest);write_setup_owned(holder/target,raw,files)
            checked,info=O.read_regular(holder/target,1024*1024)
            require(checked==raw and O.same(files[target][1],info))
        return holder,generation,files
    except BaseException:
        if generation is not None:
            try:remove_bootstrap_library(holder,generation,files)
            except BaseException:pass # Preserve the same original setup failure.
        raise

def remove_bootstrap_library(holder,generation,files):
    require((directory(holder).st_dev,directory(holder).st_ino)==(generation.st_dev,generation.st_ino)
        and {p.name for p in holder.iterdir()}==set(files))
    for name,(raw,prior) in files.items():
        checked,current=O.read_regular(holder/name,1024*1024)
        require(checked==raw and O.same(prior,current))
    for name in files:(holder/name).unlink()
    holder.rmdir()

def validate_bootstrap_observation(value,context,module):
    require(type(value)is dict and set(value)=={'schema','context','Source_harness_observation',
        'guest_launcher_observation_enabled','raw_UART_used','VM_input_or_PAM_ownership',
        'runtime_acceptance','release_acceptance'} and value['schema']=='arctic-ui-bootstrap-observation-v1'
        and type(value['context'])is dict and value['context']==context
        and all(value[k]is False for k in('guest_launcher_observation_enabled','raw_UART_used',
            'VM_input_or_PAM_ownership','runtime_acceptance','release_acceptance')))
    native=module.closed(value['Source_harness_observation'])
    require(native['input_states']['serial-install']==native['input_states']['serial-boot']=='not-observed'
        and all(row['role']=='input' for row in native['producer_categories']))
    return value

def project_ui_bootstrap(log,context,common,scanner_raw,primary=None):
    # Only the future owned harness is scanned; guest UARTs/CD/audio are unused.
    try:
        require(type(context)is dict and type(context.get('nonce'))is str
            and re.fullmatch('[0-9a-f]{32}',context['nonce']))
        guest=common.load(common.ROOT/PREFIX/'guest.py','ui_bootstrap_context')
        guest.validate_context(context);directory(log.parent)
        module,owner=bootstrap_module();require(owner.unchanged())
        host=set();rows=set();harness='rejected'
        try:harness=module.scan_owned(O,log,context['nonce'],host,rows)
        except (KeyboardInterrupt,SystemExit):raise
        except Exception:host=set();rows=set()
        require(owner.unchanged() and all(key[0]=='input' for key in rows))
        native=module.closed(dict(schema='arctic-native-bootstrap-observation-v1',
            input_states={'harness':harness,'serial-install':'not-observed','serial-boot':'not-observed'},
            host_stages=sorted(host),producer_categories=[dict(zip(('role','stage','error_class','guard_site'),key)) for key in sorted(rows)],
            **{key:False for key in module.FALSE_FIELDS}))
        value=validate_bootstrap_observation(dict(schema='arctic-ui-bootstrap-observation-v1',context=context,
            Source_harness_observation=native,guest_launcher_observation_enabled=False,raw_UART_used=False,
            VM_input_or_PAM_ownership=False,runtime_acceptance=False,release_acceptance=False),context,module)
        raw=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
        require(type(scanner_raw)is bytes and sha(scanner_raw)==SCANNER_SHA)
        scanner=load(scanner_raw,Path(__file__).with_name('scanner.py'),'ui_bootstrap_original_privacy')
        require(scanner.external_text(raw)==raw and owner.unchanged())
        O.write_exclusive(log.parent/BOOTSTRAP_MEMBER,raw)
        return log.parent/BOOTSTRAP_MEMBER
    except BaseException as secondary:
        if primary is None and isinstance(secondary,(KeyboardInterrupt,SystemExit,InterruptedError)):raise
        return None

def bootstrap_public_member(path,context,common,scanner):
    guest=common.load(common.ROOT/PREFIX/'guest.py','ui_bootstrap_public_context');guest.validate_context(context)
    module,owner=bootstrap_module();require(owner.unchanged())
    raw,prior=O.read_regular(path,256*1024);require(scanner.external_text(raw)==raw)
    validate_bootstrap_observation(O.strict_json(raw),context,module)
    require(O.same(prior,path.lstat()) and owner.unchanged())
    return raw

def invoke_bootstrap_harness(original_execute,argv,log,seconds,cwd,env,observation,
        context,common,raw_harness,raw_scanner,state):
    """Select owned modules before the exact original child, preserving its error."""
    require(type(env)is dict and env.get('ARCTIC_DICTATION_HOST_TOKEN')==context['nonce'])
    staged=common.ROOT/'tools'/('.test-install-private-uart-'+context['nonce']+'.sh')
    revised=private_harness(raw_harness);staged_owned={}
    library=None;primary=None;invoked=False
    try:
        write_setup_owned(staged,revised,staged_owned)
        saved=O.signal.pthread_sigmask(O.signal.SIG_BLOCK,{O.signal.SIGINT,O.signal.SIGTERM})
        try:library,library_generation,library_files=bootstrap_library(Path(log).parent,common)
        finally:O.signal.pthread_sigmask(O.signal.SIG_SETMASK,saved)
        selected_env=env.copy();selected_env[BOOTSTRAP_ENV]=context['nonce']
        selected_env['ARCTIC_UI_BOOTSTRAP_LIB']=str(library)
        changed=argv.copy();changed[1]=str(staged);invoked=True
        return original_execute(changed,log,seconds,cwd,selected_env,observation)
    except BaseException as error:primary=error;raise
    finally:
        secondary=None
        if invoked:
            try:state['bootstrap']=project_ui_bootstrap(Path(log),context,common,raw_scanner,primary)
            except BaseException as error:secondary=error
        if library is not None:
            try:remove_bootstrap_library(library,library_generation,library_files)
            except BaseException as error:
                if secondary is None:secondary=error
        if staged.name in staged_owned:
            try:
                checked,current=O.read_regular(staged,1024*1024)
                require(checked==revised and O.same(staged_owned[staged.name][1],current));staged.unlink()
            except BaseException as error:
                if secondary is None:secondary=error
        if primary is None and secondary is not None:raise secondary

def private_harness(raw):
    require(type(raw)is bytes)
    text=raw.decode('utf-8');require(text.count(FAILED_TAIL)==1 and PRIVATE_TAIL not in text)
    revised=text.replace(FAILED_TAIL,PRIVATE_TAIL,1)
    require(revised.replace(PRIVATE_TAIL,FAILED_TAIL,1)==text)
    forwarding='  -e ARCTIC_DICTATION_HOST_TOKEN="${ARCTIC_DICTATION_HOST_TOKEN:-}" '+chr(92)+chr(10)
    forwarded=forwarding+'  -e ARCTIC_NATIVE_BOOTSTRAP_TOKEN="${ARCTIC_NATIVE_BOOTSTRAP_TOKEN:-}" '+chr(92)+chr(10)
    original_mount='-v "$HERE/lib:/arctic-lib:ro"'
    selected_mount='-v "$ARCTIC_UI_BOOTSTRAP_LIB:/arctic-lib:ro"'
    require(revised.count(forwarding)==1 and revised.count(original_mount)==1)
    revised=revised.replace(forwarding,forwarded,1).replace(original_mount,selected_mount,1)
    require(revised.replace(forwarded,forwarding,1).replace(selected_mount,original_mount,1)
        .replace(PRIVATE_TAIL,FAILED_TAIL,1)==text)
    return revised.encode()

def write_snapshot(path,raw,limit):
    """Private raw originals only; fixed 16/128-MiB existing UART limits."""
    require(type(raw)is bytes and 0<len(raw)<=limit)
    with O.owned_fd(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)as fd:
        info=os.fstat(fd);require(stat.S_ISREG(info.st_mode)and info.st_uid==os.geteuid()
            and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600 and info.st_size==0)
        at=0
        while at<len(raw):
            count=os.write(fd,memoryview(raw)[at:]);require(type(count)is int and count>0);at+=count
        require(os.fstat(fd).st_size==len(raw)and O.same(os.fstat(fd),path.lstat()))

def directory(path):
    require(type(path)is Path or isinstance(path,Path))
    require(path.is_absolute()and path.resolve()==path)
    info=path.lstat();require(stat.S_ISDIR(info.st_mode)and info.st_uid==os.geteuid()
        and stat.S_IMODE(info.st_mode)==0o700)
    return info

def snapshot(private,context,finite):
    """Capture fixed full raw UARTs privately before the original VM cleanup."""
    prior=directory(private);holder=private/'ui-evidence-snapshot';holder.mkdir(mode=0o700)
    owned=directory(holder);files={}
    for name,limit in (('serial-install.log',16*1024*1024),('serial-boot.log',128*1024*1024)):
        try:raw,info=O.read_regular(private/'vm'/name,limit)
        except (OSError,ValueError):continue
        require((owned.st_dev,owned.st_ino)==(directory(holder).st_dev,directory(holder).st_ino))
        write_snapshot(holder/name,raw,limit);files[name]=len(raw)
        require(O.same(info,(private/'vm'/name).lstat()))
    record={'schema':'arctic-ui-private-snapshot-v1','context':context,'finite':finite,
        'members':files,'complete_uart_admitted':False,'actual_runtime_cause_proven':False,
        'release_acceptance':False}
    O.write_exclusive(holder/'snapshot.json',(json.dumps(record,sort_keys=True)+'\n').encode())
    require((prior.st_dev,prior.st_ino)==(directory(private).st_dev,directory(private).st_ino)
        and(owned.st_dev,owned.st_ino)==(directory(holder).st_dev,directory(holder).st_ino))
    return holder

def observed_failure(error,scanner,scanner_owner,run_owner,common_owner,helper,helper_owner,vocabulary,raw,caller):
    if(type(error)is not builtins.RuntimeError or not run_owner.unchanged()
            or not common_owner.unchanged()or not scanner_owner.unchanged()or not helper_owner.unchanged()):return None
    rows=[];tb=BaseException.__traceback__.__get__(error)
    for _ in range(64):
        if tb is None:break
        rows.append(tb);tb=tb.tb_next
    if tb is not None:return None
    # At this catch point the caller has not unwound into the exception's
    # traceback yet. Authenticate its still-active original Source stack.
    if not(run_owner.owns(caller)and caller.f_code is run_owner.namespace['main'].__code__
        or common_owner.owns(caller)and caller.f_code is common_owner.namespace['decode'].__code__):return None
    main=None;stage=None;frame=caller
    for _ in range(64):
        if frame is None:break
        if run_owner.owns(frame)and frame.f_code is run_owner.namespace['main'].__code__:
            if frame.f_locals.get('phase')!='original-screening':return None
            main=frame
            if frame.f_locals.get('live',ABSENT)is raw:stage='live'
            elif frame.f_locals.get('original_wire',ABSENT)is raw:stage='installed'
            break
        frame=frame.f_back
    if main is None or stage is None:return None
    for item in reversed(rows):
        frame=item.tb_frame
        if not scanner_owner.owns(frame):continue
        site=scanner_owner.site(frame,item.tb_lasti,{'raise'})
        if(site is None or frame.f_code is not scanner.reject_sensitive_match.__code__
                or frame.f_locals.get('error')is not error):continue
        match=finite_match(helper,vocabulary,scanner,frame)
        if not all(o.unchanged()for o in(run_owner,common_owner,scanner_owner,helper_owner)):return None
        finite={'schema':'arctic-ui-strict-original-source-failure-v1','original_source_site':site,
            'original_uart_stage':stage,'same_rejected_match':match,
            'actual_raising_Source_Code_globals_owned':True,'exception_unchanged':True,
            'actual_runtime_cause_proven':False,'complete_uart_admitted':False,'release_acceptance':False}
        return finite,main.f_locals.get('private'),main.f_locals.get('context')
    return None

def utilities_owner():
    raw=Path(O.__file__).read_bytes();require(sha(raw)==ORIGINALS_SHA)
    return OwnedSource(O.__dict__,raw,O.__file__,'reviewed-original-primitives')

def bind(published,raw_run,raw_common,raw_scanner,helper_raw,helper_path,raw_harness,admitted_guard=None):
    """Only explicit Source load/execute dependencies; all original Codes exact.
    The new lane must supply its separately reviewed sole-marker guard. This
    disabled component does not authorize executing the historical lane guard.
    """
    utils=utilities_owner();require(utils.unchanged())
    own_raw=Path(__file__).read_bytes();component_owner=OwnedSource(globals(),own_raw,__file__,'ui-evidence-component')
    common=published.C;common_owner=OwnedSource(common.__dict__,raw_common,common.__file__,'original-ui-common')
    require(sha(raw_scanner)==SCANNER_SHA and sha(helper_raw)==MATCH_SHA)
    helper=load(helper_raw,helper_path,'ui_same_rejected_match_219')
    helper_owner=OwnedSource(helper.__dict__,helper_raw,str(helper_path),'match-diagnostic')
    vocabulary=frozenset({n.value for n in ast.walk(ast.parse(helper_raw))if isinstance(n,ast.Constant)and type(n.value)is str}
        |{'external-rule-'+format(n,'03d')for n in range(1,11)})
    original_load=common.load;original_execute=published.execute;state={'finite':None,'snapshot':None,'attempted':False,'bootstrap':None}
    namespace=published.__dict__.copy();admission=types.SimpleNamespace(**common.__dict__);namespace['C']=admission
    for name,function in tuple(namespace.items()):
        if type(function)is types.FunctionType and function.__globals__ is published.__dict__:
            namespace[name]=types.FunctionType(function.__code__,namespace,function.__name__,function.__defaults__,function.__closure__)
    run_owner=OwnedSource(namespace,raw_run,published.__file__,'original-ui-host')
    # Explicit dependencies are installed before ownership is finally bound.
    def observed_load(path,name):
        caller=sys._getframe(1)
        if Path(path)!=common.ROOT/SCANNER:return original_load(path,name)
        if not run_owner.owns(caller):return original_load(path,name)
        acquired,_=O.read_regular(Path(__file__).with_name('scanner.py'),1024*1024)
        require(acquired==raw_scanner and sha(acquired)==SCANNER_SHA)
        module=load(acquired,path,name)
        scanner_owner=OwnedSource(module.__dict__,acquired,str(path),'original-scanner')
        proxy=types.ModuleType(name+'_observed');proxy.__dict__.update(module.__dict__)
        original_external=module.external_text
        def external_text(raw):
            source_caller=sys._getframe(1)
            try:return original_external(raw)
            except BaseException as error:
                try:
                    require(utils.unchanged()and component_owner.unchanged())
                    value=observed_failure(error,module,scanner_owner,run_owner,common_owner,helper,helper_owner,vocabulary,raw,source_caller)
                    if value is not None and not state['attempted']:
                        finite,private,context=value;state['attempted']=True;state['finite']=finite
                        guest=original_load(Path(published.__file__).with_name('guest.py'),'ui_snapshot_context')
                        guest.validate_context(context)
                        require(utils.unchanged()and component_owner.unchanged())
                        state['snapshot']=snapshot(private,dict(context),finite)
                        require(utils.unchanged()and component_owner.unchanged())
                except BaseException:pass # SAME original primary always wins.
                raise
        proxy.external_text=external_text;return proxy
    def execute(argv,log,seconds,cwd,env,observation=None):
        caller=sys._getframe(1);changed=argv
        original_path=common.ROOT/'tools/test-install.sh'
        if(type(argv)is list and len(argv)>1 and argv[:2]==['bash',str(original_path)]):
            require(run_owner.owns(caller)and caller.f_code is namespace['main'].__code__
                and caller.f_locals.get('phase')=='harness'and seconds==4200)
            require(type(raw_harness)is bytes and sha(original_path.read_bytes())==sha(raw_harness))
            context=caller.f_locals['context']
            require(type(context)is dict and type(context.get('nonce'))is str
                and re.fullmatch('[0-9a-f]{32}',context['nonce']))
            require(utils.unchanged() and component_owner.unchanged())
            return invoke_bootstrap_harness(original_execute,argv,log,seconds,cwd,env,observation,
                context,common,raw_harness,raw_scanner,state)
        return original_execute(changed,log,seconds,cwd,env,observation)
    admission.load=observed_load
    if admitted_guard is not None:admission.guard=admitted_guard
    namespace['execute']=execute
    run_owner=OwnedSource(namespace,raw_run,published.__file__,'original-ui-host')
    # The execute wrapper is intentionally excluded from original Source ownership.
    # All other helpers and main retain their exact original Code and globals.
    staged=types.ModuleType('ui_original_observed');staged.__dict__.update(namespace)
    return staged,state

def validate_finite(value,scanner_raw,helper_raw):
    require(type(value)is dict and set(value)=={'schema','original_source_site','original_uart_stage',
        'same_rejected_match','actual_raising_Source_Code_globals_owned','exception_unchanged',
        'actual_runtime_cause_proven','complete_uart_admitted','release_acceptance'}
        and value['schema']=='arctic-ui-strict-original-source-failure-v1'
        and value['original_uart_stage']in('live','installed')
        and value['actual_raising_Source_Code_globals_owned']is True and value['exception_unchanged']is True
        and all(value[k]is False for k in('actual_runtime_cause_proven','complete_uart_admitted','release_acceptance')))
    nodes=[n for n in ast.parse(scanner_raw).body if isinstance(n,ast.FunctionDef)and n.name=='reject_sensitive_match']
    require(len(nodes)==1)
    raises=[n for n in ast.walk(nodes[0])if isinstance(n,ast.Raise)]
    require(len(raises)==1)
    require(value['original_source_site']=={'source':'original-scanner','source_sha256':SCANNER_SHA,
        'function':'reject_sensitive_match','source_line':raises[0].lineno,'site_kind':'raise',
        'fixed_assertion_label':'Sensitive text in external evidence'})
    row=value['same_rejected_match'];keys=('regex','offsets','mapping','source_rule','candidate_reason','family_reason')
    vocabulary={n.value for n in ast.walk(ast.parse(helper_raw))if isinstance(n,ast.Constant)and type(n.value)is str}
    vocabulary|={'external-rule-'+format(n,'03d')for n in range(1,11)}
    require(type(row)is dict and set(row)==set(keys)|{'privacy_admitted','runtime_cause_proven','operand_value_or_digest_exported'}
        and all(type(row[k])is str and row[k]in vocabulary for k in keys)
        and all(row[k]is False for k in('privacy_admitted','runtime_cause_proven','operand_value_or_digest_exported')))
    return value

def snapshot_members(holder,common,raw_common,scanner,scanner_raw,helper_raw,ocr=O.ocr_original):
    utils=utilities_owner();require(utils.unchanged())
    generation=directory(holder);record_raw,prior=O.read_regular(holder/'snapshot.json',128*1024)
    require(scanner.external_text(record_raw)==record_raw)
    record=O.strict_json(record_raw)
    require(type(record)is dict and set(record)=={'schema','context','finite','members',
        'complete_uart_admitted','actual_runtime_cause_proven','release_acceptance'}
        and record['schema']=='arctic-ui-private-snapshot-v1'
        and all(record[k]is False for k in('complete_uart_admitted','actual_runtime_cause_proven','release_acceptance')))
    finite=validate_finite(record['finite'],scanner_raw,helper_raw)
    guest=common.load(common.ROOT/PREFIX/'guest.py','ui_partial_inventory')
    guest.validate_context(record['context'])
    require(type(record['members'])is dict and set(record['members'])<=set(('serial-install.log','serial-boot.log'))
        and all(type(n)is int and 0<n<=limit for name,n in record['members'].items()
            for limit in(16*1024*1024 if name=='serial-install.log'else 128*1024*1024,)))
    output={};denied=[]
    if 'serial-boot.log'in record['members']:
        raw,source=O.read_regular(holder/'serial-boot.log',128*1024*1024)
        require(len(raw)==record['members']['serial-boot.log'])
        parser,_,_=diagnostic_transport(common,raw_common)
        report,inventory,decoded=parser(raw,record['context'],scanner)
        for name,data in decoded.items():
            if name=='report.json':
                require(scanner.external_text(data)==data);output['original-ui/'+name]=data
            else:
                try:O.original_png(data);ocr(scanner,data)
                except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired):denied.append(name);continue
                output['original-ui/'+name]=data
        require(O.same(source,(holder/'serial-boot.log').lstat()))
    ledger={'schema':'arctic-ui-incomplete-originals-v1','context':record['context'],'finite':finite,
        'retained_members':sorted(output),'denied_fixed_png_members':sorted(denied),
        'complete_uart_admitted':False,'complete_ui_or_pam_proven':False,
        'actual_runtime_cause_proven':False,'release_acceptance':False}
    raw=(json.dumps(ledger,sort_keys=True,indent=2)+'\n').encode()
    require(scanner.external_text(raw)==raw);output['incomplete-evidence.json']=raw
    require(O.same(prior,(holder/'snapshot.json').lstat())
        and(generation.st_dev,generation.st_ino)==(directory(holder).st_dev,directory(holder).st_ino))
    require(utils.unchanged());return output

def stage_members(stage,files):
    stage.mkdir(mode=0o700);generation=directory(stage);retained={}
    require(type(files)is dict and 0<len(files)<=24)
    for name,raw in files.items():
        path=Path(name)
        require(type(name)is str and not path.is_absolute()and '..'not in path.parts
            and len(path.parts)<=2 and type(raw)is bytes and 0<len(raw)<=32*1024*1024)
        output=stage/path
        if output.parent!=stage:output.parent.mkdir(exist_ok=True,mode=0o700)
        write_snapshot(output,raw,32*1024*1024);retained[name]=(raw,output.lstat())
    validate_members(stage,retained,generation)
    return generation,retained

def validate_members(stage,retained,generation):
    info=directory(stage)
    require((info.st_dev,info.st_ino)==(generation.st_dev,generation.st_ino))
    expected_dirs={p.as_posix()for name in retained for p in Path(name).parents if p!=Path('.')}
    seen=set()
    for path in stage.rglob('*'):
        name=path.relative_to(stage).as_posix();info=path.lstat()
        require(not path.is_symlink()and info.st_uid==os.geteuid()and not info.st_mode&0o022)
        if stat.S_ISDIR(info.st_mode):require(name in expected_dirs)
        else:require(stat.S_ISREG(info.st_mode)and name in retained);seen.add(name)
    require(seen==set(retained))
    for name,(raw,prior)in retained.items():
        checked,current=O.read_regular(stage/name,32*1024*1024)
        require(checked==raw and O.same(prior,current)and stat.S_IMODE(current.st_mode)==0o600)

def publish_members(stage,target,files,on_ready=None):
    require(not target.exists()and not target.is_symlink()and target.is_absolute()and target.resolve()==target)
    generation,retained=stage_members(stage,files)
    # Practical scope: final held-directory and every member are rechecked after
    # rename, before admission. Arbitrary later same-UID changes are not claimed.
    os.rename(stage,target);validate_members(target,retained,generation)
    if on_ready is not None:on_ready()

def finite_snapshot_observation(holder,context,common,scanner,scanner_raw,helper_raw):
    """Only fixed bounded snapshot metadata; never open a raw UART member."""
    require(type(scanner_raw)is bytes and sha(scanner_raw)==SCANNER_SHA
        and type(helper_raw)is bytes and sha(helper_raw)==MATCH_SHA)
    guest=common.load(common.ROOT/PREFIX/'guest.py','ui_finite_snapshot_context')
    guest.validate_context(context)
    value={'schema':'arctic-ui-screened-finite-snapshot-v1','context':context,'status':'unavailable','finite':None,
        'serialized_Source_observation_reauthenticated_runtime_Code':False,
        'raw_private_exported':False,'complete_uart_admitted':False,'complete_ui_or_pam_proven':False,
        'actual_runtime_cause_proven':False,'release_acceptance':False}
    try:
        generation=directory(holder)
        record_raw,prior=O.read_regular(holder/'snapshot.json',128*1024)
        require(scanner.external_text(record_raw)==record_raw)
        record=O.strict_json(record_raw)
        require(type(record)is dict and set(record)=={'schema','context','finite','members',
            'complete_uart_admitted','actual_runtime_cause_proven','release_acceptance'}
            and record['schema']=='arctic-ui-private-snapshot-v1'and record['context']==context
            and all(record[k]is False for k in('complete_uart_admitted','actual_runtime_cause_proven','release_acceptance')))
        guest.validate_context(record['context'])
        require(type(record['members'])is dict and set(record['members'])<=set(('serial-install.log','serial-boot.log'))
            and all(type(n)is int and 0<n<=limit for name,n in record['members'].items()
                for limit in(16*1024*1024 if name=='serial-install.log'else 128*1024*1024,)))
        finite_value=record['finite'];require(type(finite_value)is dict)
        site=finite_value.get('original_source_site')
        require(type(site)is dict and type(site.get('source_line'))is int
            and all(type(site.get(k))is str for k in('source','source_sha256','function','site_kind','fixed_assertion_label')))
        finite=validate_finite(finite_value,scanner_raw,helper_raw)
        require(O.same(prior,(holder/'snapshot.json').lstat())
            and(generation.st_dev,generation.st_ino)==(directory(holder).st_dev,directory(holder).st_ino))
        value.update(status='validated',finite=finite)
    except FileNotFoundError:pass
    except (KeyboardInterrupt,SystemExit):raise
    except BaseException:value['status']='invalid'
    raw=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
    require(len(raw)<=128*1024 and scanner.external_text(raw)==raw)
    return raw

def screen(original_screen,source,target,snapshot_holder,common,raw_common,scanner,scanner_raw,helper_raw,
        ocr=O.ocr_original,on_ready=None):
    """Preserve original whole-screen primary; partial output never qualifies."""
    utils=utilities_owner();require(utils.unchanged())
    scanner_owner=OwnedSource(scanner.__dict__,scanner_raw,scanner.__file__,'publication-scanner')
    original_stage=target.with_name(target.name+'.whole-original.pending')
    publish_stage=target.with_name(target.name+'.admitted.pending')
    try:result=original_screen(source,original_stage)
    except BaseException as error:
        if isinstance(error,(KeyboardInterrupt,SystemExit)):raise
        try:
            files=snapshot_members(snapshot_holder,common,raw_common,scanner,scanner_raw,helper_raw,ocr)
            publish_members(publish_stage,target,files,on_ready)
        except BaseException:pass # Optional evidence never replaces SAME primary.
        raise
    files={}
    for path in original_stage.rglob('*'):
        if path.is_dir():continue
        name=path.relative_to(original_stage).as_posix();raw,prior=O.read_regular(path,32*1024*1024)
        if name.endswith('.png'):O.original_png(raw);ocr(scanner,raw)
        require(O.same(prior,path.lstat()));files[name]=raw
    host_raw=files.get('host-status.json')
    if host_raw is not None:
        host=O.strict_json(host_raw)
        if type(host)is dict and type(host.get('context'))is dict:
            try:
                files[BOOTSTRAP_MEMBER]=bootstrap_public_member(
                    snapshot_holder.parent/BOOTSTRAP_MEMBER,host['context'],common,scanner)
            except (KeyboardInterrupt,SystemExit):raise
            except Exception:pass # Optional diagnostics preserve original whole-screen result.
    if host_raw is not None:
        host=O.strict_json(host_raw)
        if type(host)is dict and host.get('status')=='failed'and host.get('phase')=='original-screening':
            context=host.get('context')
            guest=common.load(common.ROOT/PREFIX/'guest.py','ui_screened_failure_context')
            guest.validate_context(context)
            files['strict-original-failure-observation.json']=finite_snapshot_observation(
                snapshot_holder,context,common,scanner,scanner_raw,helper_raw)
    require(utils.unchanged()and scanner_owner.unchanged())
    publish_members(publish_stage,target,files,on_ready)
    return result

def build(manifest,root=None):
    """Compile only exact disabled public Source closure; no runtime acquisition."""
    here=Path(__file__).resolve().parent;root=here.parents[1]if root is None else Path(root)
    require(type(manifest)is dict and manifest.get('schema')=='arctic-ui-private-evidence-disabled-source-v1'
        and manifest.get('ready')is False and manifest.get('release_acceptance')is False
        and manifest.get('operational_cli')is False and manifest.get('base')==BASE)
    require(set(manifest)=={'schema','ready','release_acceptance','operational_cli','base',
        'original_manifest_sha256','published_execution_files','source_files','image','limits',
        'component_reuse','self_execution_files'})
    pins=manifest['published_execution_files'];require(type(pins)is dict)
    raw={}
    for name,digest in pins.items():
        require(type(name)is str and re.fullmatch(r'[.A-Za-z0-9_/-]+',name)
            and not name.startswith('/')and '..'not in Path(name).parts)
        raw[name]=(root/name).read_bytes();require(sha(raw[name])==digest)
    declared=O.strict_json(raw[PREFIX+'execution-manifest.json'])
    require(manifest['original_manifest_sha256']==sha(raw[PREFIX+'execution-manifest.json'])
        and pins==dict(declared['execution_files'],**{PREFIX+'execution-manifest.json':manifest['original_manifest_sha256']})
        and manifest['source_files']==declared['source_files']and manifest['image']==declared['image']
        and manifest['limits']=={'install_timeout':2400,'harness_seconds':4200,'ui_seconds':720,
            'max_png':16,'install_network':'offline','boot_network':'offline'}
        and declared['ui_seconds']==720 and declared['max_png']==16 and declared['release_acceptance']is False)
    own=manifest['self_execution_files']
    require(type(own)is dict and set(own)=={'tools/final-installed-ui-private-evidence/'+n
        for n in('observer.py','originals.py','match-diagnostic.py','test_observer.py','README.md')})
    for name,digest in own.items():require(sha((here/Path(name).name).read_bytes())==digest)
    previous={n:sys.modules.get(n,ABSENT)for n in('common','compose')}
    try:
        common=load(raw[PREFIX+'common.py'],root/PREFIX/'common.py','ui_original_common_44c');common.manifest(declared,True);sys.modules['common']=common
        compose=load(raw[PREFIX+'compose.py'],root/PREFIX/'compose.py','ui_original_compose_44c');sys.modules['compose']=compose
        published=load(raw[PREFIX+'run.py'],root/PREFIX/'run.py','ui_original_run_44c')
    finally:
        for n,value in previous.items():
            if value is ABSENT:sys.modules.pop(n,None)
            else:sys.modules[n]=value
    return bind(published,raw[PREFIX+'run.py'],raw[PREFIX+'common.py'],raw[SCANNER],
        (here/'match-diagnostic.py').read_bytes(),here/'match-diagnostic.py',raw['tools/test-install.sh']),published

def main():raise SystemExit('Current UI evidence adapter is disabled Source preparation')
if __name__=='__main__':main()
