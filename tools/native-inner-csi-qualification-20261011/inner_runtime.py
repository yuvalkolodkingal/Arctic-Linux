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
