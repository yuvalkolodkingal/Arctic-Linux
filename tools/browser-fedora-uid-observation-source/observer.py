"""Disabled Source-only screen probe; preserve all original bytes and errors."""
import ast
import hashlib
import io
import types

SCANNER_SHA='0c2176c4892e45e485eeac32f564fdfe9fb1619f142ac0b60babeed52924075f'
OWNERSHIP_SHA='144dfd018190701e8888a07e3e16f807de493f59a5b7aa2afffa36bbc8b1c3ee'
MAX_ORIGINAL=64*1024*1024
MAX_DIAGNOSTIC=1024
MAX_FRAMES=64
FAMILIES=frozenset(('github-credential','aws-credential','authorization','email-shape',
    'queried-url','credential-url','named-secret','secret-option','disk-secret-input',
    'transcription-label','unknown'))
PHASES=frozenset(('source-view','terminal-view','terminal-payload','not-observed'))
ROLE_TABLE=(
 ('activation.json','activation'),('image-identity.json','image-identity'),
 ('container-identity.json','container-identity'),
 ('products/ab-build-receipt.json','build-receipt'),
 ('products/custom-ELF-inventory.json','ELF-inventory'),
 ('products/original-packages.txt','package-census'),
 ('products/original-macros.txt','macro-census'),
 *((('logs/'+name+'.log'),('command-'+name)) for name in (
    'key-import','image-pull','container-create','container-start','bootstrap',
    'input-directories','input-copy','input-ownership','input-readonly',
    'producer','collector','output-copy')),
)
ROLE_IDS=frozenset(value for _,value in ROLE_TABLE)|{'other-text'}

def require(value):
    if not value:raise RuntimeError('Disabled screen observer Source binding differs')

def module(raw,filename,name):
    result=types.ModuleType(name);result.__file__=filename
    exec(compile(raw,filename,'exec',optimize=0),result.__dict__)
    return result

def snapshot(module):
    namespace=dict(module.__dict__)
    classes={key:dict(value.__dict__) for key,value in namespace.items()
        if type(value)is type and value.__module__==module.__name__}
    functions=[]
    for value in (*namespace.values(),*(v for row in classes.values() for v in row.values())):
        if type(value)is types.FunctionType:
            kw=value.__kwdefaults__
            functions.append((value,value.__code__,value.__globals__,value.__defaults__,
                kw,None if kw is None else dict(kw),value.__closure__,
                tuple((cell,cell.cell_contents) for cell in value.__closure__ or ())))
    return module,namespace,classes,functions

def stable(record):
    module,namespace,classes,functions=record
    if set(module.__dict__)!=set(namespace) or any(module.__dict__[k]is not v for k,v in namespace.items()):return False
    for key,before in classes.items():
        now=namespace[key].__dict__
        if set(now)!=set(before) or any(now[k]is not v for k,v in before.items()):return False
    for function,code,globals_,defaults,kw,kw_values,closure,cells in functions:
        if (function.__code__ is not code or function.__globals__ is not globals_
            or function.__defaults__ is not defaults or function.__kwdefaults__ is not kw
            or function.__closure__ is not closure
            or any(cell.cell_contents is not value for cell,value in cells)):return False
        if kw is not None and (set(kw)!=set(kw_values) or any(kw[k]is not v for k,v in kw_values.items())):return False
    return True

class BoundedDiagnostic(io.TextIOBase):
    def __init__(self):
        self.parts=[];self.count=0;self.overflow=False
    def write(self,value):
        if type(value)is not str or self.count+len(value)>MAX_DIAGNOSTIC:
            self.parts=[];self.overflow=True
        elif not self.overflow:
            self.parts.append(value);self.count+=len(value)
        return len(value) if type(value)is str else 0
    def captured(self):
        return None if self.overflow else ''.join(self.parts)
    def reset(self):
        self.parts=[];self.count=0;self.overflow=False

class ScreenProbe:
    def __init__(self,scanner_raw,ownership_raw,filename):
        require(type(scanner_raw)is bytes and hashlib.sha256(scanner_raw).hexdigest()==SCANNER_SHA)
        require(type(ownership_raw)is bytes and hashlib.sha256(ownership_raw).hexdigest()==OWNERSHIP_SHA)
        require(type(filename)is str)
        self.module=module(scanner_raw,filename,'disabled_selected_build_scanner')
        sink=BoundedDiagnostic();printer=print
        def private_print(*values,sep=' ',end='\n',file=None,flush=False):
            require(file is None)
            return printer(*values,sep=sep,end=end,file=sink,flush=flush)
        self.module.__dict__['print']=private_print
        self.sink=sink
        self.ownership=module(ownership_raw,'tools/browser-screen-failure-source/ownership.py','disabled_screen_ownership')
        self.owner=self.ownership.OwnedSource(self.module.__dict__,scanner_raw,filename,'selected-scanner')
        self.scanner_state=snapshot(self.module);self.ownership_state=snapshot(self.ownership)
        self.roles=dict(ROLE_TABLE)
        external=self.module.external_text.__code__
        calls=tuple(code for code in external.co_consts if type(code)is types.CodeType
            and code.co_qualname==external.co_qualname+'.<locals>.require_safe')
        require(len(calls)==1)
        self.uid_call_codes=(external,calls[0],self.module.reject_sensitive_match.__code__)
        self.uid_call_binding=self.uid_call_codes
        self.phase_values=self.module.EXTERNAL_RULE_PHASES
        require(set(self.phase_values)==PHASES-{'not-observed'})
        require({name for name,_ in self.module.EXTERNAL_RULE_ALTERNATIVES}==FAMILIES-{'unknown'})
        tree=ast.parse(scanner_raw)
        external=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='external_text')
        decode=[n for n in ast.walk(external) if isinstance(n,ast.Call)
            and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name)
            and n.func.value.id=='content' and n.func.attr=='decode'
            and len(n.args)==1 and isinstance(n.args[0],ast.Constant) and n.args[0].value=='utf-8']
        require(len(decode)==1)
        self.decode_line=decode[0].lineno
        self.last_failure=None
        require(self.unchanged())

    def unchanged(self):
        return (stable(self.scanner_state) and stable(self.ownership_state)
            and self.owner.unchanged() and self.roles==dict(ROLE_TABLE)
            and self.uid_call_codes is self.uid_call_binding
            and self.uid_call_codes[0] is self.module.external_text.__code__
            and self.uid_call_codes[2] is self.module.reject_sensitive_match.__code__
            and any(code is self.uid_call_codes[1] for code in self.uid_call_codes[0].co_consts))

    def unknown(self,relative):
        role=self.roles.get(relative,'other-text') if type(relative)is str and type(self.roles)is dict else 'other-text'
        role=role if type(role)is str and role in ROLE_IDS else 'other-text'
        return {'schema':'arctic-accelerator-screen-finite-observation-v2',
            'member_role':role,
            'scanner_category':'unknown','scanner_phase':'not-observed','scanner_family':'unknown',
            'observer_owned_scanner_site':False,'original_exception_preserved':True,
            'known_public_Fedora44_UID_DNF_line':False,
            'privacy_admitted':False,'authenticated_runtime_frame_attribution':False,
            'build_performance_release_acceptance':False}

    def known_uid_line(self,rows,item,relative,content):
        """Only a fixed public equality bit from the same owned throwing chain."""
        if type(relative)is not str or relative!='logs/producer.log' or not self.unchanged():return False
        at=next((i for i,row in enumerate(rows) if row is item),None)
        if at is None or at<2:return False
        external,caller,throwing=(row.tb_frame for row in rows[at-2:at+1])
        if any(frame.f_code is not code or frame.f_globals is not self.module.__dict__
                for frame,code in zip((external,caller,throwing),self.uid_call_codes)):return False
        if not self.owner.owns(external) or not self.owner.owns(throwing):return False
        if any(frame.f_builtins is not throwing.f_builtins for frame in (external,caller)):return False
        match=throwing.f_locals.get('match');original=throwing.f_locals.get('original')
        boundaries=throwing.f_locals.get('boundaries');removed=throwing.f_locals.get('removed')
        if (type(match)is not self.module.re.Match or type(original)is not str
                or throwing.f_locals.get('phase')!='source-view'
                or caller.f_locals.get('phase')!='source-view'
                or external.f_locals.get('content')is not content
                or external.f_locals.get('value')is not original
                or caller.f_locals.get('value')is not original
                or caller.f_locals.get('rejected')is not match
                or external.f_locals.get('view')is not match.string
                or caller.f_locals.get('scanned')is not match.string
                or external.f_locals.get('boundaries')is not boundaries
                or caller.f_locals.get('boundaries')is not boundaries
                or external.f_locals.get('removed')is not removed
                or caller.f_locals.get('removed')is not removed):return False
        email='fedora-44-primary@fedoraproject.org'
        line=' UserID     : "Fedora (44) <fedora-44-primary@fedoraproject.org>"\n'
        if match.group(0)!=email:return False
        start,end=match.span()
        first,last=self.module.original_span(start,end,boundaries,removed)
        if last-first!=len(email) or original[first:last]!=email:return False
        line_start=first-line.index(email)
        line_end=line_start+len(line)
        return (line_start>=0 and line_end<=len(original)
            and (line_start==0 or original[line_start-1]=='\n')
            and original[line_start:line_end]==line and self.unchanged())

    def describe(self,error,relative,content,sink):
        result=self.unknown(relative)
        if not self.unchanged():return result
        if type(error)not in (RuntimeError,UnicodeDecodeError):return result
        rows=[];trace=BaseException.__dict__['__traceback__'].__get__(error,type(error))
        for _ in range(MAX_FRAMES):
            if trace is None:break
            rows.append(trace);trace=trace.tb_next
        if trace is not None:return result
        for item in reversed(rows):
            frame=item.tb_frame
            if not self.owner.owns(frame):continue
            if type(error)is UnicodeDecodeError:
                if (frame.f_code is self.module.external_text.__code__ and item.tb_lineno==self.decode_line
                    and frame.f_locals.get('content')is content):
                    return dict(result,scanner_category='invalid-utf8',observer_owned_scanner_site=True)
                continue
            site=self.owner.site(frame,item.tb_lasti,{'raise'})
            if site is None:continue
            if (frame.f_code is self.module.external_text.__code__
                and site['fixed_assertion_label']=='Incomplete terminal escape in external evidence'):
                return dict(result,scanner_category='incomplete-terminal',observer_owned_scanner_site=True)
            if (frame.f_code is not self.module.reject_sensitive_match.__code__
                or site['fixed_assertion_label']!='Sensitive text in external evidence'
                or frame.f_locals.get('error')is not error):continue
            phase=frame.f_locals.get('phase')
            phase=phase if type(phase)is str and phase in self.phase_values else 'not-observed'
            family='unknown'
            captured=sink.captured()
            if captured is not None and phase!='not-observed':
                lines=captured.splitlines()
                expected={('ARCTIC-EVIDENCE-RULE='+phase+'-'+name):name for name in FAMILIES-{'unknown'}}
                expected['ARCTIC-EVIDENCE-RULE='+phase+'-unknown-rule']='unknown'
                if lines and lines[0]in expected:
                    label=expected[lines[0]]
                    candidates={'ARCTIC-EVIDENCE-EMAIL-CANDIDATE='+phase+'-'+name
                        for name in ('unknown-unit',*(value for _,value in self.module.EXTERNAL_EMAIL_CANDIDATES))}
                    if len(lines)==1 or (len(lines)==2 and label=='email-shape' and lines[1]in candidates):family=label
            if not self.unchanged():return result
            return dict(result,scanner_category='sensitive-text',scanner_phase=phase,
                scanner_family=family,observer_owned_scanner_site=True,
                known_public_Fedora44_UID_DNF_line=(phase=='source-view' and family=='email-shape'
                    and self.known_uid_line(rows,item,relative,content)))
        return result

    def screen(self,content,relative):
        self.last_failure=None
        try:
            require(type(content)is bytes and len(content)<=MAX_ORIGINAL and self.unchanged())
            sink=self.sink;sink.reset()
            result=self.module.external_text(content)
            require(result is content and self.unchanged())
            return result
        except BaseException as error:
            try:
                self.last_failure=self.describe(error,relative,content,sink) if 'sink'in locals() else self.unknown(relative)
            except BaseException:
                self.last_failure=self.unknown(relative)
            raise
