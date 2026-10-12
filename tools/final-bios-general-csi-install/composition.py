"""Explicit pinned scanner dependency selection; all original function Code stays exact."""
import builtins,hashlib,sys,types
from pathlib import Path

ABSENT=object()
ORIGINAL_PATH='tools/native-functional/screen-evidence.py'
ORIGINAL_SHA='8754ad7f3a97803ce1d84fd889667853dd5d407a8907adfb52afd6a7d41067be'
SELECTED_SHA='0c2176c4892e45e485eeac32f564fdfe9fb1619f142ac0b60babeed52924075f'

BINDING={'format_coverage': 'unchanged-privacy-rules-bounded-complete-CSI-separation-with-retained-ESC-display-branch', 'original_operand_observed': False, 'release_acceptance': False, 'requested_path': 'tools/native-functional/screen-evidence.py', 'requested_sha256': '8754ad7f3a97803ce1d84fd889667853dd5d407a8907adfb52afd6a7d41067be', 'runtime_cause_proven': False, 'schema': 'arctic-bios-reviewed-bounded-complete-csi-map-v1', 'selected_Source_commit': '338c0ed87f5b975623c63ca81439a84023266dc3', 'selected_Source_path': 'tools/bounded-complete-csi-source/scanner.py', 'selected_git_blob': 'f95aba37009b242c1226afb6a8a6e8ba02a9f1bd', 'selected_path': 'tools/bounded-complete-csi-source/scanner.py', 'selected_sha256': '0c2176c4892e45e485eeac32f564fdfe9fb1619f142ac0b60babeed52924075f', 'selected_Source_tree': 'cf32bc639e32a38955631915c819956f4b26f7e5', 'parent_scanner_sha256': '8b9fbbe3bb9241dca8232e7cee61e05fec10bfbb0bc1e9d0d62dbfb7bda8e8ea', 'source_author_receipt_sha256': 'd5c9535fc4f8bd96b9a1e8d5cd380d9ae113a22a16050c9d22953d236dbbc1b8', 'source_payload_sha256': '4666e5bdbc93ecd72ad4f9328a1b45fd2db8cc6185ea76927e2cd6e413b45bb5', 'source_independent_receipt_sha256': 'a3305b5495dbacee0ffb71437d5968ede524e9b8256a749ddeca179c6049a794', 'privacy_rules_preserved': True, 'raw_member_bytes_preserved': True, 'original_offsets_preserved': True, 'source_independent_supplement_sha256': '455d6fd33a2e0d49896153838752ccca6a93f3758e5940d61cf6b33b1542ec68', 'source_author_supplement_sha256': '317bf0006b32c79bbf81fdade8d6b6a7bb7b84e19236659000377b3c2c17eea3', 'source_prior_supplement_sha256': 'c931d6bef50603bf15cb4b1da0a12c07b07905229eb1e1bc8e24874d7ad9d5b1'}

PUBLIC_SHAPE_BINDING={'actual_operand_observed': False, 'author_receipt_sha256': 'c6ccebb21155233cf0144f548680f7e17a1783fb546d7ad32b25c36426087a58', 'independent_receipt_sha256': '72ecb9abbd82f43cba31f36fd23319d0e265f7fbfe0cabc42926332116883f7a', 'privacy_policy_changed': False, 'release_acceptance': False, 'requested_helper_path': 'tools/final-bios-strict-screen-observer/match-diagnostic.py', 'requested_helper_sha256': '93b3b5ea0a3dab1cb9d31d485c15495cde7315a05d3965caf02c39101e13e89f', 'requested_observer_path': 'tools/final-bios-strict-screen-observer/observer.py', 'requested_observer_sha256': '181aab4e9966c30c783be917d99aedf804185ce33be2648af4906e96f69521cb', 'runtime_cause_proven': False, 'schema': 'arctic-bios-same-match-public-shape-bounded-csi-dependency-map-v1', 'selected_helper_path': 'tools/bounded-complete-csi-source/match-diagnostic.py', 'selected_helper_sha256': '1de427723ec027da1cfac79bff7eada7b875f631c2fab26745b8cad2f71c851b', 'selected_observer_path': 'tools/final-bios-same-match-public-shape-source/observer.py', 'selected_observer_sha256': '144dfd018190701e8888a07e3e16f807de493f59a5b7aa2afffa36bbc8b1c3ee', 'source_payload_sha256': '6ce5b1c0d3819966a8fb4eaeb832484d93a0799f906295c8dcfcf9d1ad683774', 'source_sha': '4a884072e71354226b506f1057bb7f88f3934e24', 'source_tree': 'fe92ecef8cdfb93a321cd4e947d6a513f75ebb2d', 'alignment_Source_commit': '338c0ed87f5b975623c63ca81439a84023266dc3', 'alignment_Source_tree': 'cf32bc639e32a38955631915c819956f4b26f7e5', 'alignment_author_receipt_sha256': 'd5c9535fc4f8bd96b9a1e8d5cd380d9ae113a22a16050c9d22953d236dbbc1b8', 'alignment_payload_sha256': '4666e5bdbc93ecd72ad4f9328a1b45fd2db8cc6185ea76927e2cd6e413b45bb5', 'alignment_independent_receipt_sha256': 'a3305b5495dbacee0ffb71437d5968ede524e9b8256a749ddeca179c6049a794', 'parent_selected_helper_sha256': 'a92c57e53172efe8fbed8fce076341184e293ff9d525c1fda87678d6a9ba36c6', 'alignment_independent_supplement_sha256': '455d6fd33a2e0d49896153838752ccca6a93f3758e5940d61cf6b33b1542ec68', 'alignment_author_supplement_sha256': '317bf0006b32c79bbf81fdade8d6b6a7bb7b84e19236659000377b3c2c17eea3'}

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
    # Both historical dependencies stay pinned and acquired intact. Only these
    # two explicit selected whole Source buffers enter the attach-only adapter.
    shape=value['public_shape_binding']
    require(type(shape)is dict and shape==PUBLIC_SHAPE_BINDING
        and all(type(shape[k])is type(v)for k,v in PUBLIC_SHAPE_BINDING.items()))
    for role in ('observer','helper'):
        for choice in ('requested','selected'):
            name=shape[choice+'_'+role+'_path']
            require(sha(buffers[name])==shape[choice+'_'+role+'_sha256'])
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
    observer_path=shape['selected_observer_path']
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
    diagnostic_path=shape['selected_helper_path']
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
        'mapping':dict(binding),'public_shape_mapping':dict(shape),'original_operand_observed':False,'runtime_cause_proven':False,
        'release_acceptance':False,'Source_boundaries':(builder_boundary,staged_boundary,
            observed_boundary,publish_boundary,main_boundary)}
