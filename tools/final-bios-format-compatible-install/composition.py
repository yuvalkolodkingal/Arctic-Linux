"""Explicit pinned scanner dependency selection; all original function Code stays exact."""
import builtins,hashlib,sys,types
from pathlib import Path

ABSENT=object()
ORIGINAL_PATH='tools/native-functional/screen-evidence.py'
ORIGINAL_SHA='8754ad7f3a97803ce1d84fd889667853dd5d407a8907adfb52afd6a7d41067be'
SELECTED_SHA='b3d56536397ff1c46caf082b97a070ff3eae383c2c277898c572cb34eb76f336'

BINDING={'schema': 'arctic-bios-reviewed-format-map-v1', 'requested_path': 'tools/native-functional/screen-evidence.py', 'requested_sha256': '8754ad7f3a97803ce1d84fd889667853dd5d407a8907adfb52afd6a7d41067be', 'selected_path': 'tools/final-bios-format-compatible-install/scanner.py', 'selected_sha256': 'b3d56536397ff1c46caf082b97a070ff3eae383c2c277898c572cb34eb76f336', 'selected_Source_commit': '5ca06e86f8582f09b94892b896963910215c2010', 'selected_Source_path': 'tools/native-functional/screen-evidence.py', 'selected_git_blob': '437822a7a825bed3a0aad64ea148bbe061431c75', 'format_coverage': 'systemd-v259-complete-bounded-OSC3008-root-agetty-serial-getty', 'original_operand_observed': False, 'runtime_cause_proven': False, 'release_acceptance': False}

def require(value):
    if not value:raise RuntimeError('BIOS reviewed Source scanner mapping differs')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def codes(code):
    yield code
    for value in code.co_consts:
        if type(value)is types.CodeType:yield from codes(value)
def clone(function,globals=None,cells=None):
    require(type(function)is types.FunctionType)
    closure=function.__closure__
    if cells:
        require(set(cells)<=set(function.__code__.co_freevars))
        closure=tuple(types.CellType(cells[n])if n in cells else cell
            for n,cell in zip(function.__code__.co_freevars,closure))
    return types.FunctionType(function.__code__,function.__globals__ if globals is None else globals,
        function.__name__,function.__defaults__,closure)
def cell(function,name):
    require(type(function)is types.FunctionType and name in function.__code__.co_freevars)
    return function.__closure__[function.__code__.co_freevars.index(name)].cell_contents

class Boundary:
    """Authenticate the exact expected original Code/globals at each mapped call."""
    def __init__(self,function,raw):
        self.function=function;self.code=function.__code__;self.namespace=function.__globals__
        expected=[c for c in codes(compile(raw,self.code.co_filename,'exec'))
            if(c.co_qualname,c.co_firstlineno)==(self.code.co_qualname,self.code.co_firstlineno)]
        require(len(expected)==1 and self.code==expected[0]
            and tuple(self.code.co_lines())==tuple(expected[0].co_lines()))
        self.refs={name:self.namespace.get(name,ABSENT)for name in self.code.co_names}
        self.builtins=self.namespace.get('__builtins__',builtins.__dict__)
        if type(self.builtins)is types.ModuleType:self.builtins=self.builtins.__dict__
        require(type(self.builtins)is dict)
        self.builtin_refs={n:self.builtins.get(n,ABSENT)for n,v in self.refs.items()if v is ABSENT}
        require(all(v is builtins.__dict__.get(n,ABSENT)for n,v in self.builtin_refs.items()))
    def owns(self,frame):
        return(self.function.__code__ is self.code and frame.f_code is self.code
            and frame.f_globals is self.namespace and frame.f_builtins is self.builtins
            and all(self.namespace.get(n,ABSENT)is v for n,v in self.refs.items())
            and all(self.builtins.get(n,ABSENT)is v for n,v in self.builtin_refs.items()))


def build(root,value,source_loader,new_guard):
    """Pure Source composition; no private input, producer request or VM operation."""
    root=Path(root);pins=value['execution_files'];binding=value['scanner_binding']
    require(type(binding)is dict and binding==BINDING and all(type(binding[k])is type(v)for k,v in BINDING.items()))
    buffers={name:source_loader(root/name,pins[name])for name in pins}
    require(sha(buffers[ORIGINAL_PATH])==ORIGINAL_SHA)
    selected=buffers[binding['selected_path']];require(sha(selected)==SELECTED_SHA)
    def load(raw,path,name):
        module=types.ModuleType(name);module.__file__=str(path)
        exec(compile(raw,str(path),'exec'),module.__dict__)
        return module
    def selected_module(name):
        # The recorded filename is the authenticated original request; actual
        # selected Source buffer/hash/path is explicit in scanner_binding.
        module=load(selected,root/ORIGINAL_PATH,name);sys.modules[name]=module
        return module
    retained_path='tools/final-bios-failure-evidence/evidence.py'
    observer_path='tools/final-bios-strict-screen-observer/observer.py'
    retained=load(buffers[retained_path],root/retained_path,'format_original_retention')
    observer=load(buffers[observer_path],root/observer_path,'format_original_strict_observer')
    original_retention_attach=retained.attach
    builder=None;builder_boundary=None
    def retention_attach(exact,old,channel,source_manifest,adapter,scanner,*args,**kwargs):
        require(builder_boundary.owns(sys._getframe(1)))
        # The unchanged original builder first verifies/loads its 8754 closure.
        # Only this explicit scanner argument is selected for partial privacy.
        observer.OwnedSource(scanner.__dict__,buffers[ORIGINAL_PATH],scanner.__file__,'original-scanner')
        return original_retention_attach(exact,old,channel,source_manifest,adapter,
            selected_module('format_retention_selected_scanner'),*args,**kwargs)
    builder_globals=retained.build.__globals__.copy();builder_globals['attach']=retention_attach
    builder=clone(retained.build,globals=builder_globals)
    builder_boundary=Boundary(builder,buffers[retained_path])
    retained_manifest=value['execution_files']['tools/final-bios-failure-evidence/execution-manifest.json']
    raw_manifest=buffers['tools/final-bios-failure-evidence/execution-manifest.json']
    require(sha(raw_manifest)==retained_manifest)
    import json
    exact,retention_state=builder(json.loads(raw_manifest))
    # Unchanged accepted strict adapter receives the actual selected buffer.
    run_path='tools/final-bios-install/run.py';common_path='tools/final-bios-install/common.py'
    diagnostic_path='tools/final-bios-strict-screen-observer/match-diagnostic.py'
    observed,state=observer.attach(exact,buffers[run_path],buffers[common_path],selected,
        buffers[diagnostic_path],root/diagnostic_path)
    evidence_observed=observed.__globals__['original_evidence']
    staged=cell(evidence_observed,'staged');admission=staged.__globals__['C']
    original_observed_load=admission.load;original_load=cell(original_observed_load,'original_load')
    original_publish=observed.__globals__['publish']
    mapped_observed=None;mapped_publish=None;observed_boundary=None;publish_boundary=None
    def selected_load(path,name,expected=None):
        if Path(path)!=root/ORIGINAL_PATH:return original_load(path,name,expected)
        frame=sys._getframe(1)
        require(expected==SELECTED_SHA and(
            (name=='bios_source_screen'and observed_boundary.owns(frame))or
            (name=='bios_strict_failure_host_gate'and publish_boundary.owns(frame))))
        return selected_module(name)
    mapped_observed=clone(original_observed_load,cells={'original_load':selected_load})
    mapped_publish=clone(original_publish,cells={'original_load':selected_load})
    observed_boundary=Boundary(mapped_observed,buffers[observer_path])
    publish_boundary=Boundary(mapped_publish,buffers[observer_path])
    staged_boundary=Boundary(staged,buffers[run_path])
    def observed_request(path,name,expected=None):
        if Path(path)!=root/ORIGINAL_PATH:return original_observed_load(path,name,expected)
        require(name=='bios_source_screen'and expected==ORIGINAL_SHA
            and staged_boundary.owns(sys._getframe(1)))
        return mapped_observed(path,name,SELECTED_SHA)
    admission.load=observed_request
    base_admission=observed.__globals__['C'];original_manifest=base_admission.manifest(
        base_admission.strict_json(buffers['tools/final-bios-install/execution-manifest.json']),True)
    wrapped=None;main_boundary=None
    def guard(projected,source,inputs=None):
        require(projected==original_manifest)
        return new_guard(value,source,inputs)
    def main_load(path,name,expected=None):
        if Path(path)!=root/ORIGINAL_PATH:return base_admission.load(path,name,expected)
        require(name=='bios_host_screen'and expected==ORIGINAL_SHA and main_boundary.owns(sys._getframe(1)))
        return selected_module(name)
    main_admission=types.SimpleNamespace(**base_admission.__dict__)
    main_admission.guard=guard;main_admission.load=main_load
    namespace=observed.__globals__.copy();namespace.update(C=main_admission,publish=mapped_publish)
    wrapped=clone(observed,globals=namespace);main_boundary=Boundary(wrapped,buffers[run_path])
    require(wrapped.__code__ is exact.__code__ and observed.__code__ is exact.__code__)
    return wrapped,observed,exact,{'strict':state,'retention':retention_state,
        'mapping':dict(binding),'original_operand_observed':False,'runtime_cause_proven':False,
        'release_acceptance':False,'Source_boundaries':(builder_boundary,staged_boundary,
            observed_boundary,publish_boundary,main_boundary)}
