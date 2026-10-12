#!/usr/bin/env python3
"""Finite Source sites only; never consult exception arguments or input values."""
import ast
import builtins
import dis
import hashlib
import json
import re
import sys
import types

_ABSENT=object()
SAFE_LABEL=re.compile(r'[A-Za-z0-9][A-Za-z0-9 _./():=+-]{0,119}\Z')

def _codes(code):
    yield code
    for value in code.co_consts:
        if isinstance(value,types.CodeType):yield from _codes(value)

def _functions(namespace):
    for name,value in tuple(namespace.items()):
        if type(value) is types.FunctionType and value.__globals__ is namespace:
            yield value
        elif type(value) is type:
            for function in tuple(value.__dict__.values()):
                if type(function) is types.FunctionType and function.__globals__ is namespace:
                    yield function

def _inside(position,node):
    if position is None or position.lineno is None or position.col_offset is None:return False
    return ((node.lineno,node.col_offset)<=(position.lineno,position.col_offset)
            and (position.end_lineno or position.lineno,position.end_col_offset or position.col_offset)
                <=(node.end_lineno,node.end_col_offset))

def _label(node,prefix):
    value=None
    if isinstance(node,ast.Call) and node.args:
        at=1 if isinstance(node.func,ast.Name) and node.func.id=='require' or isinstance(node.func,ast.Attribute) and node.func.attr=='require' else 0
        if len(node.args)>at and isinstance(node.args[at],ast.Constant):value=node.args[at].value
    return value if type(value) is str and SAFE_LABEL.fullmatch(value) else prefix

def _return_label(node):
    value=node.value
    if isinstance(value,ast.Constant) and type(value.value) is int:
        return 'return-code-'+str(value.value)+'-site-'+str(node.lineno)
    if isinstance(value,ast.IfExp) and all(isinstance(x,ast.Constant) and type(x.value) is int for x in (value.body,value.orelse)):
        nonzero={value.body.value,value.orelse.value}-{0}
        if len(nonzero)==1:return 'nonzero-return-code-'+str(next(iter(nonzero)))+'-site-'+str(node.lineno)
    return 'return-site-'+str(node.lineno)

def site_inventory(raw,key):
    """Closed export vocabulary derived only from exact whole Source bytes."""
    parsed=ast.parse(raw);nodes=[]
    for node in ast.walk(parsed):
        if isinstance(node,ast.Call) and (isinstance(node.func,ast.Name) and node.func.id=='require'
                or isinstance(node.func,ast.Attribute) and node.func.attr=='require'):
            nodes.append(('require',node,_label(node,'require-site-'+str(node.lineno))))
        elif isinstance(node,ast.Raise) and isinstance(node.exc,ast.Call):
            nodes.append(('raise',node,_label(node.exc,'raise-site-'+str(node.lineno))))
        elif isinstance(node,ast.Return):nodes.append(('return',node,_return_label(node)))
        elif (isinstance(node,ast.Assign) and isinstance(node.value,ast.Constant) and node.value.value is False
              and any(isinstance(t,ast.Name) and t.id=='ok' for t in node.targets)):
            nodes.append(('false-flag',node,'ok-false-site-'+str(node.lineno)))
    rows=[];digest=hashlib.sha256(raw).hexdigest()
    for code in _codes(compile(raw,'<source-inventory>','exec')):
        if code.co_name=='<module>':continue
        for instruction in dis.get_instructions(code,show_caches=True):
            for kind,node,label in nodes:
                if _inside(instruction.positions,node):
                    value={'source':key,'source_sha256':digest,'function':code.co_qualname,
                           'source_line':node.lineno,'site_kind':kind,'fixed_assertion_label':label}
                    if value not in rows:rows.append(value)
    return rows

class SourceSites:
    def __init__(self):self.bound={};self.exceptions={}

    def bind(self,namespace,raw,expected_sha,filename,key):
        if type(namespace) is not dict or type(raw) is not bytes or hashlib.sha256(raw).hexdigest()!=expected_sha:
            raise ValueError('Source namespace or whole bytes differ')
        if not re.fullmatch('[a-z][a-z0-9-]{0,31}',key):raise ValueError('Source key differs')
        source=raw.decode('utf-8');parsed=ast.parse(source);compiled=compile(raw,filename,'exec')
        expected={(c.co_qualname,c.co_firstlineno):c for c in _codes(compiled)}
        nodes=list(ast.walk(parsed));count=0
        for function in _functions(namespace):
            code=function.__code__;wanted=expected.get((code.co_qualname,code.co_firstlineno))
            if wanted is None:continue
            if (code!=wanted or code.co_filename!=filename or tuple(code.co_lines())!=tuple(wanted.co_lines())
                    or namespace.get('RuntimeError',builtins.RuntimeError) is not builtins.RuntimeError):
                raise ValueError('Source code object or line table differs')
            # LOAD_GLOBAL resolves absent names through this exact builtins dict.
            # Bind absence too: a late global must never replace that resolution.
            refs={name:namespace.get(name,_ABSENT) for name in code.co_names}
            builtin_namespace=namespace.get('__builtins__',builtins.__dict__)
            if type(builtin_namespace) is types.ModuleType:builtin_namespace=builtin_namespace.__dict__
            if type(builtin_namespace) is not dict:raise ValueError('Source builtin namespace differs')
            builtin_refs={name:builtin_namespace.get(name,_ABSENT) for name,value in refs.items() if value is _ABSENT}
            if any(value is not builtins.__dict__.get(name,_ABSENT) for name,value in builtin_refs.items()):
                raise ValueError('Source builtin resolution differs')
            instructions={v.offset:v for v in dis.get_instructions(code,show_caches=True)}
            sites=[]
            for node in nodes:
                if isinstance(node,ast.Call):
                    func=node.func
                    require=(isinstance(func,ast.Name) and func.id=='require' or isinstance(func,ast.Attribute) and func.attr=='require')
                    if require:sites.append(('require',node,_label(node,'require-site-'+str(node.lineno))))
                elif isinstance(node,ast.Raise) and isinstance(node.exc,ast.Call):
                    sites.append(('raise',node,_label(node.exc,'raise-site-'+str(node.lineno))))
                elif isinstance(node,ast.Return):sites.append(('return',node,_return_label(node)))
                elif (isinstance(node,ast.Assign) and isinstance(node.value,ast.Constant) and node.value.value is False
                      and any(isinstance(t,ast.Name) and t.id=='ok' for t in node.targets)):
                    sites.append(('false-flag',node,'ok-false-site-'+str(node.lineno)))
            self.bound[code]={'function':function,'namespace':namespace,'refs':refs,'key':key,
                              'sha256':expected_sha,'instructions':instructions,'sites':sites,
                              'builtin_namespace':builtin_namespace,'builtin_refs':builtin_refs}
            count+=1
        if not count:raise ValueError('No exact Source code objects bound')
        return count

    def _owner(self,frame):
        value=self.bound.get(frame.f_code)
        if value is None or frame.f_globals is not value['namespace']:return None
        if any(frame.f_globals.get(n,_ABSENT) is not original for n,original in value['refs'].items()):return None
        if frame.f_builtins is not value['builtin_namespace']:return None
        if any(frame.f_builtins.get(n,_ABSENT) is not original for n,original in value['builtin_refs'].items()):return None
        if value['function'].__code__ is not frame.f_code:return None
        return value

    def _site(self,frame,offset,kinds):
        owner=self._owner(frame)
        if owner is None:return None
        instruction=owner['instructions'].get(offset)
        if instruction is None:return None
        line=next((n for start,stop,n in frame.f_code.co_lines() if start<=offset<stop),None)
        if line!=instruction.positions.lineno:return None
        found=[(kind,node,label) for kind,node,label in owner['sites'] if kind in kinds and _inside(instruction.positions,node)]
        if len(found)!=1:return None
        kind,node,label=found[0]
        return {'source':owner['key'],'source_sha256':owner['sha256'],'function':frame.f_code.co_qualname,
                'source_line':node.lineno,'site_kind':kind,'fixed_assertion_label':label}

    def describe(self,error):
        # No args, repr, str, traceback formatting, operand text or operand hash.
        if self.exceptions.get(id(error)) is not error:return None
        rows=[];tb=BaseException.__traceback__.__get__(error)
        for _ in range(64):
            if tb is None:break
            rows.append(tb);tb=tb.tb_next
        if tb is not None:return None
        for at in range(len(rows)-1,-1,-1):
            item=rows[at];frame=item.tb_frame;owner=self._owner(frame)
            if owner is None:continue
            if frame.f_code.co_name=='require' and at:
                caller=rows[at-1];site=self._site(caller.tb_frame,caller.tb_lasti,{'require'})
                if site is not None:
                    # The actual callee must be this exact Source-owned require.
                    caller_owner=self._owner(caller.tb_frame)
                    if caller_owner is None:continue
                    target=caller.tb_frame.f_globals.get('require')
                    if target is not owner['function']:
                        module=caller.tb_frame.f_globals.get('C')
                        if type(module) is not types.ModuleType or module.__dict__.get('require') is not owner['function']:continue
                    return site
            site=self._site(frame,item.tb_lasti,{'raise'})
            if site is not None:return site
        return None

    def invoke(self,function,emit,*args,**kwargs):
        # Only exact registered functions are observed; foreign calls keep their ABI.
        if (type(function) is not types.FunctionType or function.__code__ not in self.bound
                or self.bound[function.__code__]['function'] is not function or sys.gettrace() is not None):
            return function(*args,**kwargs)
        flags=[];returned=None;pending_return=None;prior=None
        def trace(frame,event,arg):
            nonlocal returned,pending_return,prior
            try:
                owner=self._owner(frame)
                if owner is None:return None
                frame.f_trace_lines=frame.f_code is function.__code__
                frame.f_trace_opcodes=frame.f_code is function.__code__
                if event=='exception' and len(self.exceptions)<64:
                    # Keep exact object identity, never a copyable attribute token.
                    # Only a real exception event in an owned Source frame mints it.
                    error=arg[1]
                    if self._site(frame,frame.f_lasti,{'raise','require'}) is not None:
                        self.exceptions[id(error)]=error
                if event in ('line','opcode') and frame.f_code is function.__code__:
                    candidate=self._site(frame,frame.f_lasti,{'return'})
                    if candidate is not None:pending_return=candidate
                    site=self._site(frame,frame.f_lasti,{'false-flag'})
                    if site is not None and site not in flags and len(flags)<16:flags.append(site)
                elif event=='return' and frame.f_code is function.__code__ and type(arg) is int and arg!=0:
                    returned=self._site(frame,frame.f_lasti,{'return'}) or pending_return
                elif event=='exception' and frame.f_code is function.__code__ and owner['key']=='bios-probe':
                    # Original main retains its original failed checker in `primary`.
                    # This is read only in that exact Source function, never serialized.
                    primary=frame.f_locals.get('primary')
                    if isinstance(primary,BaseException):prior=self.describe(primary)
            except BaseException:pass
            return trace
        previous=sys.gettrace();installed=False
        try:
            try:sys.settrace(trace);installed=True
            except BaseException:pass
            result=function(*args,**kwargs)
        except BaseException as error:
            try:
                site=self.describe(error)
                if site is not None:emit({'event':'escaping-source-exception','site':site,'retained_original_primary_site':prior})
            except BaseException:pass
            raise
        else:
            if returned is not None:
                try:emit({'event':'nonzero-original-stage-return','site':returned,'executed_false_flag_sites':flags})
                except BaseException:pass
            return result
        finally:
            if installed:
                try:sys.settrace(previous)
                except BaseException:pass

def emit_guest(record,context):
    value={'schema':'arctic-final-bios-finite-cause-v1','context':context,'cause':record,'release_acceptance':False}
    data=json.dumps(value,sort_keys=True,separators=(',',':'))
    if len(data.encode())<=8192:print('ARCTIC-FINAL-BIOS-CAUSE '+data,flush=True)

def run_original_driver(raw,namespace,vmtest,emit,driver_sha,vmtest_raw,vmtest_sha):
    """Execute the identical embedded module and functions; observe finite sites."""
    if hashlib.sha256(raw).hexdigest()!=driver_sha:raise ValueError('Whole original driver differs')
    parsed=ast.parse(raw);module=compile(raw,'<string>','exec')
    start=next(n.lineno for n in parsed.body if isinstance(n,ast.Assign)
               and any(isinstance(t,ast.Name) and t.id=='rc' for t in n.targets))
    sites=SourceSites();bound=False;flags={};pending_returns={};previous=sys.gettrace()
    # Existing tracing is never displaced. The original program still executes.
    if previous is not None:return exec(module,namespace)
    def trace(frame,event,arg):
        nonlocal bound
        try:
            if frame.f_code is module and frame.f_globals is namespace:
                if event=='line' and frame.f_lineno>=start and not bound:
                    sites.bind(namespace,raw,driver_sha,'<string>','install-driver')
                    sites.bind(vmtest.__dict__,vmtest_raw,vmtest_sha,vmtest.__file__,'vmtest')
                    bound=True
                return trace
            if not bound or sites._owner(frame) is None:return None
            stage=frame.f_code.co_name in ('stage_install','stage_boot') and frame.f_globals is namespace
            frame.f_trace_lines=stage
            frame.f_trace_opcodes=stage
            if event=='exception' and len(sites.exceptions)<64 and sites._site(frame,frame.f_lasti,{'raise','require'}) is not None:
                error=arg[1];sites.exceptions[id(error)]=error
            if stage and event in ('line','opcode'):
                candidate=sites._site(frame,frame.f_lasti,{'return'})
                if candidate is not None:pending_returns[frame.f_code]=candidate
                site=sites._site(frame,frame.f_lasti,{'false-flag'})
                if site is not None:
                    values=flags.setdefault(frame.f_code,[])
                    if site not in values and len(values)<16:values.append(site)
            elif stage and event=='return' and type(arg) is int and arg!=0:
                site=sites._site(frame,frame.f_lasti,{'return'}) or pending_returns.get(frame.f_code)
                if site is not None:emit({'event':'nonzero-original-stage-return','site':site,
                                         'executed_false_flag_sites':flags.get(frame.f_code,[])})
        except BaseException:pass
        return trace
    installed=False
    try:
        try:sys.settrace(trace);installed=True
        except BaseException:pass
        return exec(module,namespace)
    except BaseException as error:
        try:
            site=sites.describe(error)
            if site is not None:emit({'event':'escaping-source-exception','site':site,'retained_original_primary_site':None})
        except BaseException:pass
        raise
    finally:
        if installed:
            try:sys.settrace(previous)
            except BaseException:pass
