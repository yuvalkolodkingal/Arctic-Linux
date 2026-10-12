#!/usr/bin/env python3
"""Disabled failure-only exact original BIOS broker-shape observations."""
import ast,builtins,dis,hashlib,json,re,sys,types
from pathlib import Path

BASE='e468d59ead8d742d86e6a17ac8f60df38c75f785'
MATCH_HELPER_SHA256='0d96f7bb82c9b38b64da494113fed52476b4af3c67f34b86566cfe3cdfa5206e'
CONFIGURED_DIAGNOSTIC_SHA256='d293bcbfb3accd5e093b2651fbff2aff407e7ad3c7b5dd04977f7b66af7dc8d3'
_CONFIGURED_GETFRAME=sys._getframe
ABSENT=object()
def require(value):
    if not value:raise ValueError('Exact BIOS Source observer binding differs')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(raw,path,name):
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module
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
    shape=helper.diagnostic_public_source_shape(scanner,frame.f_locals.get('match'),frame.f_locals.get('phase'),
        frame.f_locals.get('original'),frame.f_locals.get('boundaries'),frame.f_locals.get('removed'))
    require(type(shape)is dict and set(shape)==set(helper.DIAGNOSTIC_SHAPE_FLAGS)|{
        'schema','canonical_unit_id','privacy_admitted','runtime_cause_proven','operand_value_or_digest_exported'}
        and shape['schema']=='arctic-bios-same-match-public-source-shape-v1'
        and type(shape['canonical_unit_id'])is str
        and shape['canonical_unit_id']in('unknown',*(identifier for _,identifier in helper.DIAGNOSTIC_PUBLIC_UNITS))
        and all(type(shape[key])is bool for key in helper.DIAGNOSTIC_SHAPE_FLAGS)
        and all(shape[key]is False for key in('privacy_admitted','runtime_cause_proven','operand_value_or_digest_exported')))
    return dict(result,public_source_shape=shape,privacy_admitted=False,runtime_cause_proven=False,operand_value_or_digest_exported=False)

def broker_factory_observation(binding,scanner,scanner_owner,frame,error):
    """Optional same-owned-reject-frame metadata; no new IO or privacy admission."""
    if type(binding)is not tuple or len(binding)!=11:return None
    module,owner,function,attributes,observer_owner,helper,helper_owner,scanner_owners,common_owner,run_owners=binding[:-1]
    if not observer_owner.unchanged()or sys._getframe is not _CONFIGURED_GETFRAME:return None
    caller=_CONFIGURED_GETFRAME(1)
    try:
        if (not observer_owner.unchanged()or not observer_owner.owns(caller)
                or caller.f_code is not describe.__code__ or caller.f_locals.get('configured')is not binding
                or caller.f_locals.get('frame')is not frame or caller.f_locals.get('error')is not error
                or caller.f_locals.get('helper')is not helper or caller.f_locals.get('helper_owner')is not helper_owner
                or not common_owner.unchanged()or not all(held.unchanged()for held in run_owners)
                or not any(scanner is value and scanner_owner is held for value,held in scanner_owners)
                or not scanner_owner.unchanged()or not scanner_owner.owns(frame)
                or frame.f_code is not scanner.reject_sensitive_match.__code__ or frame.f_locals.get('error')is not error
                or type(error)is not builtins.RuntimeError or not owner.unchanged()or not helper_owner.unchanged()
                or module.diagnostic_broker_factory_shape is not function
                or any(current is not expected for current,expected in zip(
                    (module.re.Match,module.types.ModuleType,module.FACTORY,module.TARGETS),attributes))):return None
        result=function(scanner,helper,frame.f_locals.get('match'),frame.f_locals.get('phase'),
            frame.f_locals.get('original'),frame.f_locals.get('boundaries'),frame.f_locals.get('removed'),enabled=True)
        if (not observer_owner.unchanged()or not scanner_owner.unchanged()or not owner.unchanged()
                or not helper_owner.unchanged()or not common_owner.unchanged()or not all(held.unchanged()for held in run_owners)
                or sys._getframe is not _CONFIGURED_GETFRAME
                or module.diagnostic_broker_factory_shape is not function
                or any(current is not expected for current,expected in zip(
                    (module.re.Match,module.types.ModuleType,module.FACTORY,module.TARGETS),attributes))):return None
        if (type(result)is not dict or set(result)!={'schema','target_id','exact_broker_factory_shape',
                'privacy_admitted','runtime_cause_proven','operand_value_or_digest_exported','release_acceptance'}
                or type(result['schema'])is not str or result['schema']!='arctic-broker-factory-shape-source-diagnostic-v1'
                or type(result['target_id'])is not str or result['target_id']not in ('unknown',
                    'broker-source-target-001','broker-source-target-002','broker-source-target-003',
                    'broker-source-target-004','broker-source-target-005','broker-source-target-006',
                    'broker-source-target-007','broker-source-target-008','broker-source-target-009',
                    'broker-source-target-010')
                or type(result['exact_broker_factory_shape'])is not bool
                or any(type(result[key])is not bool or result[key]is not False for key in
                    ('privacy_admitted','runtime_cause_proven','operand_value_or_digest_exported','release_acceptance'))):return None
        return result
    finally:del caller

def describe(error,run_owners,common_owner,scanner_owners,helper,helper_owner,vocabulary,admissions,configured=None):
    """No exception args/string/repr; authenticate exact frame/code/global ABI."""
    if (type(error)is not builtins.RuntimeError or not helper_owner.unchanged()
            or not common_owner.unchanged()or not all(o.unchanged()for o in run_owners)):return None
    rows=[];tb=BaseException.__traceback__.__get__(error)
    for _ in range(64):
        if tb is None:break
        rows.append(tb);tb=tb.tb_next
    if tb is not None:return None
    stage='unknown'
    for item in rows:
        f=item.tb_frame
        if any(o.owns(f)and f.f_code is o.namespace['records'].__code__ for o in run_owners):
            if type(f.f_locals.get('stage'))is str and f.f_locals['stage']in('live','installed'):stage=f.f_locals['stage']
    for at in range(len(rows)-1,-1,-1):
        item=rows[at];frame=item.tb_frame
        if common_owner.require_raise(frame,item.tb_lasti)and at:
            caller=rows[at-1];owner=next((o for o in run_owners if o.owns(caller.tb_frame)),None)
            if owner is None:continue
            target=caller.tb_frame.f_globals.get('C')
            if not any(target is a for a in admissions)or target.__dict__.get('require')is not common_owner.namespace['require']:continue
            site=owner.site(caller.tb_frame,caller.tb_lasti,{'require'})
            if site is not None:return {'original_source_site':site,'original_records_stage':stage,'same_rejected_match':None}
        for module,owner in scanner_owners:
            if not owner.unchanged()or not owner.owns(frame):continue
            site=owner.site(frame,item.tb_lasti,{'raise'})
            if site is None:continue
            match=None
            if frame.f_code is module.reject_sensitive_match.__code__:
                if frame.f_locals.get('error')is not error:continue
                known=helper.diagnostic_known_public_Fedora44_UID_DNF_line(module,rows,at,owner,run_owners,error)
                require(type(known)is bool)
                match=dict(finite_match(helper,vocabulary,module,frame),known_public_Fedora44_UID_DNF_line=known)
                if configured is not None:
                    extra=None
                    try:
                        if type(configured)is tuple and len(configured)==11:
                            hook,hook_code,hook_globals=configured[-1]
                            hook_owner=configured[4]
                            if (hook_owner.unchanged()and type(hook)is types.FunctionType
                                    and hook.__code__ is hook_code and hook.__globals__ is hook_globals
                                    and hook_globals.get('broker_factory_observation',ABSENT)is hook):
                                extra=hook(configured,module,owner,frame,error)
                                if (not hook_owner.unchanged()or hook.__code__ is not hook_code
                                        or hook.__globals__ is not hook_globals
                                        or hook_globals.get('broker_factory_observation',ABSENT)is not hook):extra=None
                    except Exception:extra=None
                    if extra is not None:match=dict(match,broker_factory_shape=extra)
                if not owner.unchanged()or not helper_owner.unchanged():return None
            return {'original_source_site':site,'original_records_stage':stage,'same_rejected_match':match}
    return None

def attach(exact,raw_run,raw_common,raw_scanner,helper_raw,helper_path,*,configured_enabled=False,configured_raw=None,configured_path=None,configured_observer_raw=None):
    """Explicit evidence/load/publication dependencies; original code unchanged."""
    require(type(exact)is types.FunctionType)
    original_evidence=exact.__globals__['original_evidence'];original_publish=exact.__globals__['publish']
    namespace=original_evidence.__globals__;common=namespace['C']
    require(type(common)is types.ModuleType)
    run_owner=OwnedSource(namespace,raw_run,namespace['__file__'],'bios-host')
    common_owner=OwnedSource(common.__dict__,raw_common,common.__file__,'bios-common')
    helper=load(helper_raw,helper_path,'bios_exact_219_match_diagnostic')
    helper_owner=OwnedSource(helper.__dict__,helper_raw,str(helper_path),'match-diagnostic')
    vocabulary=frozenset({n.value for n in ast.walk(ast.parse(helper_raw))if isinstance(n,ast.Constant)and type(n.value)is str}
        |{'external-rule-'+format(n,'03d')for n in range(1,11)})
    scanner_owners=[];state={'finite':None,'context':None}
    require(type(configured_enabled)is bool)
    configured=None
    if configured_enabled:
        require(type(configured_raw)is bytes and sha(configured_raw)==CONFIGURED_DIAGNOSTIC_SHA256
            and type(configured_observer_raw)is bytes and type(configured_path)is type(Path('.')))
        configured_module=load(configured_raw,configured_path,'bios_configured_source_target')
        configured_owner=OwnedSource(configured_module.__dict__,configured_raw,str(configured_path),'configured-target')
        observer_owner=OwnedSource(globals(),configured_observer_raw,__file__,'configured-observer')
        configured_function=configured_module.diagnostic_broker_factory_shape
        attributes=(configured_module.re.Match,configured_module.types.ModuleType,
            configured_module.FACTORY,configured_module.TARGETS)
        configured=(configured_module,configured_owner,configured_function,attributes,
            observer_owner,helper,helper_owner,scanner_owners,common_owner,(run_owner,),
            (broker_factory_observation,broker_factory_observation.__code__,broker_factory_observation.__globals__))
    scanner_path=common.ROOT/'tools/native-functional/screen-evidence.py'
    original_load=common.load
    def observed_load(path,name,expected=None):
        module=original_load(path,name,expected)
        if Path(path)==scanner_path:
            # Original C.load already checked its acquired buffer against this
            # exact digest. Optional observation must never replace its result.
            try:
                require(expected==sha(raw_scanner))
                owner=OwnedSource(module.__dict__,raw_scanner,str(path),'original-scanner')
                scanner_owners.append((module,owner))
            except BaseException:pass
        return module
    admission=types.SimpleNamespace(**common.__dict__);admission.load=observed_load
    copied=namespace.copy();copied['C']=admission
    staged=types.FunctionType(original_evidence.__code__,copied,original_evidence.__name__,original_evidence.__defaults__,original_evidence.__closure__)
    copied['original_evidence']=staged
    staged_owner=OwnedSource(copied,raw_run,namespace['__file__'],'bios-host')
    if configured is not None:configured=(*configured[:9],(run_owner,staged_owner),configured[-1])
    def original_evidence_observed(vm,context,guest_sha):
        try:return staged(vm,context,guest_sha)
        except BaseException as error:
            try:
                value=describe(error,(run_owner,staged_owner),common_owner,scanner_owners,helper,helper_owner,vocabulary,(common,admission),configured)
                if value is not None:
                    state['finite']={'schema':'arctic-bios-strict-original-source-failure-v1',**value,
                        'actual_raising_Source_Code_globals_owned':True,'actual_runtime_cause_proven':False,
                        'exception_unchanged':True,'privacy_admitted':False,'release_acceptance':False}
                    state['context']=dict(context)
            except BaseException:pass
            raise
    def publish(out,files):
        changed=files
        try:
            value=common.strict_json(files['host-status.json'])
            if(value['status']=='failed'and value['phase']=='strict-original-evidence'and state['finite']is not None
                    and value['context']==state['context']):
                value=dict(value,strict_original_Source_failure=state['finite'])
                raw=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
                scanner=original_load(Path(namespace['__file__']).parents[1]/'native-functional/screen-evidence.py','bios_strict_failure_host_gate',sha(raw_scanner))
                if scanner.external_text(raw)==raw:changed=dict(files,**{'host-status.json':raw})
        except BaseException:pass
        return original_publish(out,changed)
    dependencies=exact.__globals__.copy();dependencies.update(original_evidence=original_evidence_observed,publish=publish)
    return types.FunctionType(exact.__code__,dependencies,exact.__name__,exact.__defaults__,exact.__closure__),state

def build(manifest):
    """Disabled composition only, on the exact complete e468 Source closure."""
    here=Path(__file__).resolve().parent;root=here.parents[1]
    require(type(manifest)is dict and set(manifest)=={'schema','ready','release_acceptance','operational_cli',
        'base','published_execution_files','source_files','image','limits','match_diagnostic_binding','self_execution_files'}
        and manifest['schema']=='arctic-bios-strict-screen-disabled-source-v1'
        and manifest['ready']is False and manifest['release_acceptance']is False
        and manifest['operational_cli']is False and manifest['base']==BASE)
    require(manifest['match_diagnostic_binding']=={
        'source_sha':'2199062dcd9cf64f64ce691b05eca62d46113c33',
        'independent_receipt_sha256':'0810fecb0ab2f492f391854fc6afa8da20d1c72629931f348809e8b865c45d37',
        'helper_sha256':MATCH_HELPER_SHA256}
        and sha((here/'match-diagnostic.py').read_bytes())==MATCH_HELPER_SHA256)
    own=manifest['self_execution_files']
    require(type(own)is dict and set(own)=={'tools/final-bios-strict-screen-observer/'+n
        for n in ('observer.py','match-diagnostic.py','test_observer.py','README.md')})
    pins=manifest['published_execution_files'];require(type(pins)is dict)
    for name,digest in {**pins,**own}.items():
        require(type(name)is str and re.fullmatch(r'[.A-Za-z0-9_/-]+',name)
            and not name.startswith('/')and '..'not in name.split('/')
            and type(digest)is str and re.fullmatch('[0-9a-f]{64}',digest)
            and sha((root/name).read_bytes())==digest)
    declared=json.loads((root/'tools/final-bios-retained-install/execution-manifest.json').read_bytes())
    expected=dict(declared['execution_files']);name='tools/final-bios-retained-install/execution-manifest.json'
    expected[name]=sha((root/name).read_bytes())
    require(pins==expected and manifest['source_files']==declared['source_files']and manifest['image']==declared['image'])
    require(manifest['limits']=={'install_timeout':declared['install_timeout'],'harness_seconds':declared['harness_seconds'],
        'firmware':declared['firmware'],'install_network':declared['install_network'],
        'boot_network':declared['boot_network'],'max_png':declared['max_png']}
        and manifest['limits']=={'install_timeout':2400,'harness_seconds':6600,'firmware':'bios',
            'install_network':'offline','boot_network':'offline','max_png':4})
    previous=sys.modules.get('common');absent='common'not in sys.modules
    try:
        common_path=root/'tools/final-bios-retained-install/common.py'
        common=load(common_path.read_bytes(),common_path,'bios_e468_retained_common')
        sys.modules['common']=common
        run_path=root/'tools/final-bios-retained-install/run.py'
        published=load(run_path.read_bytes(),run_path,'bios_e468_retained_run')
    finally:
        if absent:sys.modules.pop('common',None)
        else:sys.modules['common']=previous
    original,exact,retention=published.main_adapter(declared)
    observed,state=attach(original,(root/'tools/final-bios-install/run.py').read_bytes(),
        (root/'tools/final-bios-install/common.py').read_bytes(),
        (root/'tools/native-functional/screen-evidence.py').read_bytes(),
        (here/'match-diagnostic.py').read_bytes(),here/'match-diagnostic.py')
    return observed,original,state

def main():raise SystemExit('BIOS strict Source failure observer is disabled preparation')
if __name__=='__main__':main()
