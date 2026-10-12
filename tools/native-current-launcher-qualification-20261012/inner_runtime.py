"""Bind finite inner observations to the modules used by the original runner.

The accepted observer's preparation loader is never used in this runtime route.
An optional diagnostic write cannot replace the original exception or cleanup.
"""
import ast, contextlib, sys, types
from pathlib import Path
import inner_validation_observer as C

def bind_observer(F,observation):
    key=F.PREFIX+'inner_validation_observer.py'
    raw=observation.public[key]
    expected_path=Path(observation.registry.owners[0].module.__file__).parent/'inner_validation_observer.py'
    if Path(C.__file__)!=expected_path:
        raise ValueError('Closed Native observer module path differs')
    compiled={(code.co_qualname,code.co_firstlineno):code for code in F.codes(compile(raw,C.__file__,'exec',dont_inherit=True,optimize=0))}
    for node in ast.parse(raw).body:
        if type(node)is ast.FunctionDef:
            functions=[getattr(C,node.name)]
        elif type(node)is ast.ClassDef:
            cls=getattr(C,node.name)
            if type(cls)is not type or cls.__module__!=C.__name__:
                raise ValueError('Closed Native observer class differs')
            functions=[vars(cls)[n.name]for n in node.body if type(n)is ast.FunctionDef]
        else:continue
        for function in functions:
            if(type(function)is not types.FunctionType or function.__globals__ is not C.__dict__
               or function.__code__!=compiled.get((function.__code__.co_qualname,function.__code__.co_firstlineno))
               or function.__code__.co_filename!=C.__file__):
                raise ValueError('Closed Native observer actual Code globals differs')

@contextlib.contextmanager
def observe(F,observation,evidence):
    if(type(observation)is not F.Observation or observation.registry.owners[0].module.E is not observation.registry.owners[1].module):
        raise ValueError('Closed Native actual observer binding differs')
    bind_observer(F,observation)
    capture=C.Capture(F,observation.scanner,observation.registry,observation.public)
    primary=None
    try:
        with capture:yield capture
    except BaseException as error:
        primary=error
        raise
    finally:
        try:
            value=capture.result()
            C.closed(value,F)
            raw=F.encode_json(value)
            if type(raw)is not bytes or len(raw)>32*1024:
                raise ValueError('Closed Native inner diagnostic bound differs')
            F.write_exclusive(Path(evidence)/F.INNER,raw)
        except BaseException as secondary:
            if primary is None and isinstance(secondary,(KeyboardInterrupt,InterruptedError,SystemExit)):
                raise


_BOOTSTRAP_MODULE=sys.modules['native_bootstrap_observer']
_BOOTSTRAP_MEMBERS=dict(vars(_BOOTSTRAP_MODULE))
_BOOTSTRAP_BUILTIN_NAMESPACE=_BOOTSTRAP_MEMBERS['__builtins__']
_BOOTSTRAP_BUILTIN_NAMESPACE=vars(_BOOTSTRAP_BUILTIN_NAMESPACE)if type(_BOOTSTRAP_BUILTIN_NAMESPACE)is types.ModuleType else _BOOTSTRAP_BUILTIN_NAMESPACE
_BOOTSTRAP_BUILTIN_CELLS=dict(_BOOTSTRAP_BUILTIN_NAMESPACE)
_BOOTSTRAP_CLASSES=[(value,dict(vars(value)))for value in _BOOTSTRAP_MEMBERS.values()
    if type(value)is type and value.__module__==_BOOTSTRAP_MODULE.__name__]
_BOOTSTRAP_FUNCTIONS=[]
for _value in list(_BOOTSTRAP_MEMBERS.values())+[item for cls,attrs in _BOOTSTRAP_CLASSES for item in attrs.values()]:
    if type(_value)is types.FunctionType:
        _BOOTSTRAP_FUNCTIONS.append((_value,_value.__code__,_value.__globals__,_value.__builtins__,
            _value.__defaults__,_value.__kwdefaults__,getattr(_value,'__wrapped__',None)))

def bind_bootstrap(F,public):
    import builtins, importlib
    B=F.BOOTSTRAP_OBSERVER
    raw=public['tools/lib/native_bootstrap_observer.py']
    expected=F.HERE.parent/'lib/native_bootstrap_observer.py'
    if type(B)is not types.ModuleType or Path(B.__file__)!=expected:
        raise ValueError('Closed Native bootstrap actual module path differs')
    if B is not _BOOTSTRAP_MODULE or set(vars(B))!=set(_BOOTSTRAP_MEMBERS) \
        or any(vars(B)[key] is not value for key,value in _BOOTSTRAP_MEMBERS.items()):
        raise ValueError('Closed Native bootstrap actual module identity differs')
    for cls,attrs in _BOOTSTRAP_CLASSES:
        if set(vars(cls))!=set(attrs) or any(vars(cls)[key]is not value for key,value in attrs.items()):
            raise ValueError('Closed Native bootstrap actual class identity differs')
    for function,code,globals_,builtins_,defaults,kwdefaults,wrapped in _BOOTSTRAP_FUNCTIONS:
        if(function.__code__ is not code or function.__globals__ is not globals_
            or function.__builtins__ is not builtins_ or function.__defaults__ is not defaults
            or function.__kwdefaults__ is not kwdefaults or getattr(function,'__wrapped__',None)is not wrapped):
            raise ValueError('Closed Native bootstrap actual function identity differs')
    namespace=B.__dict__;tree=ast.parse(raw)
    compiled={(code.co_qualname,code.co_firstlineno):code
        for code in F.codes(compile(raw,B.__file__,'exec',dont_inherit=True,optimize=0))}
    supplied=namespace.get('__builtins__')
    builtin_namespace=vars(supplied) if type(supplied)is types.ModuleType else supplied
    if builtin_namespace is not vars(builtins):
        raise ValueError('Closed Native bootstrap builtin namespace differs')
    if set(builtin_namespace)!=set(_BOOTSTRAP_BUILTIN_CELLS) or any(builtin_namespace[key]is not value for key,value in _BOOTSTRAP_BUILTIN_CELLS.items()):
        raise ValueError('Closed Native bootstrap builtin cells differ')
    for node in tree.body:
        if type(node)is ast.Import:
            for item in node.names:
                if namespace[item.asname or item.name] is not importlib.import_module(item.name):
                    raise ValueError('Closed Native bootstrap import differs')
        elif type(node)is ast.ImportFrom:
            imported=importlib.import_module(node.module)
            for item in node.names:
                if namespace[item.asname or item.name] is not getattr(imported,item.name):
                    raise ValueError('Closed Native bootstrap import differs')
        elif type(node)is ast.Assign:
            name=node.targets[0].id
            wanted=type(Path()) if name=='PATH_TYPE' else ast.literal_eval(node.value)
            if type(namespace[name])is not type(wanted) or namespace[name]!=wanted:
                raise ValueError('Closed Native bootstrap constant differs')
        elif type(node)is ast.FunctionDef or type(node)is ast.ClassDef:
            if type(node)is ast.FunctionDef:
                functions=[(node,namespace[node.name])]
            else:
                cls=namespace[node.name]
                if type(cls)is not type or cls.__module__!=B.__name__:
                    raise ValueError('Closed Native bootstrap class differs')
                functions=[(item,vars(cls)[item.name])for item in node.body if type(item)is ast.FunctionDef]
            for source,function in functions:
                if source.decorator_list:
                    if (len(source.decorator_list)!=1 or source.decorator_list[0].id!='contextmanager'
                        or type(function)is not types.FunctionType
                        or function.__globals__ is not contextlib.__dict__
                        or function.__code__ is not contextlib.contextmanager(lambda:None).__code__):
                        raise ValueError('Closed Native bootstrap decorator differs')
                    function=function.__wrapped__
                if(type(function)is not types.FunctionType or function.__globals__ is not namespace
                    or function.__builtins__ is not builtin_namespace
                    or function.__code__!=compiled.get((function.__code__.co_qualname,function.__code__.co_firstlineno))
                    or function.__code__.co_filename!=B.__file__
                    or function.__defaults__!=(tuple(ast.literal_eval(v)for v in source.args.defaults)or None)
                    or function.__kwdefaults__ is not None):
                    raise ValueError('Closed Native bootstrap actual Code globals differs')

def project_bootstrap(F,observation,paths,owned_token,output,primary=None):
    try:
        bind_bootstrap(F,observation.public)
        F.BOOTSTRAP_OBSERVER.project(F,observation.scanner,paths,owned_token,output,primary)
    except BaseException as secondary:
        if primary is None and isinstance(secondary,(KeyboardInterrupt,InterruptedError,SystemExit)):
            raise
