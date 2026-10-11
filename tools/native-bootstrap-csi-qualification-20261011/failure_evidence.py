#!/usr/bin/env python3
"""Failure-only finite Native observations and individually screened originals.
The original full screen and all original acceptance predicates remain authoritative.
Partial evidence is explicitly incomplete and never supplies qualification.
"""
import argparse,ast,builtins,contextlib,dis,hashlib,io,json,math,os,re,signal,stat,struct,subprocess,sys,tempfile,types,zlib
from contextlib import contextmanager
from pathlib import Path
from PIL import Image
HERE=Path(__file__).resolve().parent
FIELDS=('st_dev','st_ino','st_uid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
SCANNER_SHA='0c2176c4892e45e485eeac32f564fdfe9fb1619f142ac0b60babeed52924075f'
PHASES=('host-validation','host-provisioning','taskbar-compilation','payload-composition','harness-execution','harness-retention','guest-validation','taskbar-validation','audio-validation','source-run-passed','owned-image-cleanup')
MEMBERS=(('harness/native-stop-install.json','stop-install'),('harness/native-stop-boot.json','stop-boot'),('native-live/report.json','report-live'),('native-installed/report.json','report-installed'),('harness/install-20-live-desktop.png','screen-live-desktop'),('harness/boot-41-login.png','screen-installed-login'),('harness/boot-41-no-login-detected.png','screen-installed-no-login'),('harness/boot-51-desktop.png','screen-installed-desktop'))
HOST='host-native-observation.json'
INNER='host-native-inner-observation.json'
# The actual lane pins this physical helper before import/execution.
sys.path.insert(1,str(HERE.parent/'lib'))
import native_bootstrap_observer as BOOTSTRAP_OBSERVER
import inner_runtime as BOOTSTRAP_RUNTIME
BOOTSTRAP=BOOTSTRAP_OBSERVER.MEMBER
import inner_validation_observer as INNER_OBSERVER
EXECUTION_PATHS=('.github/workflows/native-bootstrap-csi-qualification-20261011.yml', '.github/workflows/native-candidate-20261008.yml', 'shell/dev/virtual-pointer.c', 'shell/dev/wlr-screencopy-unstable-v1.xml', 'tools/lib/container.sh', 'tools/lib/native_bootstrap_observer.py', 'tools/lib/vmtest.py', 'tools/native-bootstrap-csi-qualification-20261011/execution-context.json', 'tools/native-bootstrap-csi-qualification-20261011/failure_evidence.py', 'tools/native-bootstrap-csi-qualification-20261011/inner_runtime.py', 'tools/native-bootstrap-csi-qualification-20261011/inner_validation_observer.py', 'tools/native-bootstrap-csi-qualification-20261011/match-diagnostic.py', 'tools/native-bootstrap-csi-qualification-20261011/runner.py', 'tools/native-bootstrap-csi-qualification-20261011/screen-evidence.py', 'tools/native-bootstrap-csi-qualification-20261011/test_source.py', 'tools/native-functional/apps.py', 'tools/native-functional/compose-photo-probe.py', 'tools/native-functional/evidence.py', 'tools/native-functional/failure_evidence.py', 'tools/native-functional/fetch-image.py', 'tools/native-functional/guest-check-native-v6.py', 'tools/native-functional/native-launcher-v6.py', 'tools/native-functional/prepare-taskbar-tools.sh', 'tools/native-functional/runner.py', 'tools/native-functional/screen-evidence.py', 'tools/native-functional/source-provenance.json', 'tools/native-functional/taskbar-display.py', 'tools/native-functional/taskbar-evidence.py', 'tools/native-functional/taskbar-runtime.py', 'tools/native-functional/taskbar-screencopy.c', 'tools/native-functional/taskbar.py', 'tools/test-install.sh')
PREFIX='tools/native-bootstrap-csi-qualification-20261011/'
EXPECTED_CONTEXT={'Source_base_sha': '1b046bb4b7230c734c1a01ad8ce8b55efbacd449', 'canonical_bundle': 'tools/native-functional', 'execution_branch': 'codex/native-bootstrap-csi-qualification-20261011', 'execution_lane': 'tools/native-bootstrap-csi-qualification-20261011', 'finite_member': 'host-native-inner-observation.json', 'image_Source_sha': '326690f173d4dc4f049f43e046c8380e66825a07', 'observer_sha256': 'c63b44767e80a0aa47a3f942d7d361ab423754f3db0221a412e80f9c6f69fcda', 'original_evidence_guards': 113, 'original_harness_seconds': 10800, 'original_runner_guards': 50, 'original_taskbar_cases': 480, 'product_image_changed': False, 'release_acceptance': False, 'runtime_acceptance': False, 'scanner_companion_sha256': '1de427723ec027da1cfac79bff7eada7b875f631c2fab26745b8cad2f71c851b', 'scanner_sha256': '0c2176c4892e45e485eeac32f564fdfe9fb1619f142ac0b60babeed52924075f', 'schema': 'arctic-native-bootstrap-csi-execution-context-v1', 'selected_runner': 'tools/native-bootstrap-csi-qualification-20261011/runner.py', 'workflow_name': 'Native bootstrap and CSI image qualification', 'bootstrap_observer_sha256': '6b5627a78cda5a3c94ff9ec3dae4c7af667a6add70cc78b69942f91586fbe40c', 'bootstrap_finite_member': 'host-native-bootstrap-observation.json', 'execution_file_count': 32, 'direct_guest_roles': ['tools/native-functional/guest-check-native-v6.py', 'tools/native-functional/native-launcher-v6.py']}
HANDLED=('harness','taskbar-display','guest-validation','taskbar','audio-install','audio-boot')
# Exact Source AST inventory; these are finite public sites, never operands.
GUARD_COUNTS=(('native-runner',50),('native-evidence',113))
GUARD_SITES=frozenset(label+'-require-'+format(number,'03d')
    for label,count in GUARD_COUNTS for number in range(1,count+1))
def require(value,label=None):
    if not value:raise ValueError('Closed Native failure evidence rejected')
def sha(raw):return hashlib.sha256(raw).hexdigest()


def same(a,b):return all(getattr(a,k)==getattr(b,k) for k in FIELDS)


@contextmanager
def owned_fd(path,flags,mode=0o777):
 # Stable deferred handlers span acquisition, bounded IO and owned cleanup.
 # A repeated cancellation cannot interrupt the transition into close().
 signals=(signal.SIGINT,signal.SIGTERM)
 saved=signal.pthread_sigmask(signal.SIG_BLOCK,set(signals));fd=None;pending=[];handlers={}
 def deferred(signum,frame):pending.append(signum)
 try:
  for signum in signals:handlers[signum]=signal.signal(signum,deferred)
  signal.pthread_sigmask(signal.SIG_SETMASK,saved)
  fd=os.open(path,flags,mode)
  yield fd
 finally:
  signal.pthread_sigmask(signal.SIG_BLOCK,set(signals))
  try:
   if fd is not None:
    # Linux has released the number even on a close error; never retry it.
    try:os.close(fd)
    except OSError:pass
  finally:
   for signum,handler in handlers.items():signal.signal(signum,handler)
   # Queue each observed kind while blocked, then restore the caller's mask.
   for signum in signals:
    if signum in pending:os.kill(os.getpid(),signum)
   signal.pthread_sigmask(signal.SIG_SETMASK,saved)


def write_exclusive(output,data):
 require(type(data) is bytes and len(data)<=8*1024*1024)
 with owned_fd(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600) as fd:
  info=os.fstat(fd);require(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid() and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600 and info.st_size==0)
  at=0
  while at<len(data):
   count=os.write(fd,memoryview(data)[at:]);require(type(count) is int and count>0);at+=count
  final=os.fstat(fd);require(final.st_size==len(data) and same(final,output.lstat()))


def strict_json(raw):
    def pairs(items):
        value={}
        for key,item in items:
            if key in value:raise ValueError('closed-duplicate-JSON-key')
            value[key]=item
        return value
    def constant(value):raise ValueError('closed-nonfinite-JSON')
    return json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=constant)


def original_png(raw):
    require(type(raw) is bytes and 0<len(raw)<=8*1024*1024 and raw.startswith(b'\x89PNG\r\n\x1a\n'),'original-PNG-signature-bound')
    at=8;types=[]
    while at<len(raw):
        require(at+12<=len(raw),'original-PNG-chunk-header-bound')
        size=struct.unpack('>I',raw[at:at+4])[0];kind=raw[at+4:at+8];end=at+12+size
        require(end<=len(raw) and kind in (b'IHDR',b'PLTE',b'IDAT',b'IEND',b'tRNS',b'gAMA',b'sRGB',b'cHRM'),'original-PNG-chunk-type-bound-no-text-metadata')
        require(zlib.crc32(raw[at+4:at+8+size])&0xffffffff==struct.unpack('>I',raw[at+8+size:end])[0],'original-PNG-every-chunk-CRC')
        types.append(kind);at=end
        if kind==b'IEND':
            require(size==0 and at==len(raw),'original-PNG-end-no-trailing-bytes');break
    require(types[0]==b'IHDR' and types.count(b'IHDR')==types.count(b'IEND')==1 and types[-1]==b'IEND' and b'IDAT' in types,'original-PNG-structure')
    with Image.open(io.BytesIO(raw)) as image:
        require(image.format=='PNG' and 640<=image.width<=3840 and 480<=image.height<=2160,'original-PNG-format-geometry')
        image.verify()
    with Image.open(io.BytesIO(raw)) as image:
        image.load();dimensions=list(image.size)
        require(image.mode in ('RGB','RGBA','P'),'original-PNG-decode-color-mode')
    return dimensions


def screen_ocr(source,text):
    require(type(text) is bytes and len(text)<=256*1024,'OCR-private-text-bound')
    try:
        decoded=text.decode('utf-8',errors='strict')
        # The unchanged active Source generator uses private lowercase32 random
        # credentials. This conservative extra denial cannot admit any text.
        if re.search(r'(?<![a-z0-9])[a-z0-9]{32}(?![a-z0-9])',decoded,re.IGNORECASE):
            return False,'private-credential-shape-visible'
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            screened=source.external_text(text)
        return (True,'strict-Source-passed') if screened==text else (False,'strict-Source-original-text-equality-differs')
    except (ValueError,UnicodeError,RuntimeError):return False,'strict-Source-OCR-text-privacy-rejected'

def read_regular(path,limit):
    path=Path(path)
    require(path.is_absolute() and path.resolve()==path and type(limit) is int and limit>0)
    before=path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_uid==os.geteuid()
            and before.st_nlink==1 and not before.st_mode&0o022 and 0<before.st_size<=limit)
    with owned_fd(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK) as fd:
        held=os.fstat(fd);require(same(before,held));raw=bytearray()
        while len(raw)<=limit:
            part=os.read(fd,min(65536,limit+1-len(raw)))
            if not part:break
            raw.extend(part)
        require(same(held,os.fstat(fd)) and same(held,path.lstat()) and len(raw)==before.st_size)
    return bytes(raw),before

def source_context(manifest):
    raw,prior=read_regular(Path(manifest),1024*1024);value=strict_json(raw)
    require(type(value) is dict and set(value)=={'execution_files','image','ready','release_acceptance'}
            and value['ready'] is True and value['release_acceptance'] is False)
    root=HERE.parents[1];public={}
    require(type(value['execution_files']) is dict and tuple(sorted(value['execution_files']))==EXECUTION_PATHS)
    for name,digest in value['execution_files'].items():
        require(type(name) is str and name==Path(name).as_posix() and not Path(name).is_absolute()
                and '..' not in Path(name).parts and type(digest) is str and re.fullmatch('[0-9a-f]{64}',digest))
        content,generation=read_regular(root/name,4*1024*1024)
        require(sha(content)==digest);public[name]=content
    require(same(prior,Path(manifest).lstat()))
    for name in ('runner.py','failure_evidence.py','screen-evidence.py','inner_validation_observer.py','execution-context.json'):
        require(PREFIX+name in public)
    require('tools/native-functional/evidence.py' in public)
    context=strict_json(public[PREFIX+'execution-context.json'])
    require(type(context) is dict and set(context)==set(EXPECTED_CONTEXT)
            and all(type(context[k]) is type(v) and context[k]==v for k,v in EXPECTED_CONTEXT.items()))
    content=public[PREFIX+'screen-evidence.py'];require(sha(content)==SCANNER_SHA)
    scanner=types.ModuleType('Native_original_whole_scanner');scanner.__file__=str(HERE/'screen-evidence.py')
    exec(compile(content,scanner.__file__,'exec'),scanner.__dict__)
    BOOTSTRAP_RUNTIME.bind_bootstrap(sys.modules[__name__],public)
    return scanner,public

def encode_json(value):
    raw=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+"\n").encode()
    require(strict_json(raw)==value)
    return raw

def error_class(error):
    classes={RuntimeError:'runtime-error',ValueError:'value-error',OSError:'os-error',
             FileNotFoundError:'file-missing',PermissionError:'permission-error',
             TimeoutError:'timeout-error',subprocess.TimeoutExpired:'process-deadline',
             subprocess.CalledProcessError:'process-failed',InterruptedError:'interrupted',
             KeyboardInterrupt:'cancelled',SystemExit:'system-exit'}
    return classes.get(type(error),'other')

def closed_host(value):
    require(type(value) is dict and set(value)=={'schema','status','milestones','handled_failures','error_class','guard_site',
            'Source_Code_globals_direct_guard_binding','runtime_cause','VM_input_or_PAM_ownership',
            'runtime_acceptance','release_acceptance'})
    require(value['schema']=='arctic-native-host-observation-v1' and value['status'] in ('failed','completed')
            and type(value['milestones']) is list and len(value['milestones'])<=len(PHASES)
            and all(type(p) is str and p in PHASES for p in value['milestones'])
            and len(set(value['milestones']))==len(value['milestones'])
            and value['error_class'] in ('none','runtime-error','value-error','os-error','file-missing',
                'permission-error','timeout-error','process-deadline','process-failed','interrupted',
                'cancelled','system-exit','other')
            and type(value['guard_site']) is str
            and (value['guard_site']=='unknown' or value['guard_site'] in GUARD_SITES)
            and type(value['Source_Code_globals_direct_guard_binding']) is bool
            and value['Source_Code_globals_direct_guard_binding']==(value['guard_site']!='unknown')
            and all(value[k] is False for k in ('runtime_cause','VM_input_or_PAM_ownership','runtime_acceptance','release_acceptance')))
    require(type(value['handled_failures']) is list and len(value['handled_failures'])<=len(HANDLED)
            and all(type(row) is dict and set(row)=={'role','error_class','guard_site'}
                    and type(row['role']) is str and row['role'] in HANDLED
                    and type(row['error_class']) is str and row['error_class'] in (
                        'runtime-error','value-error','os-error','file-missing','permission-error','timeout-error',
                        'process-deadline','process-failed','interrupted','cancelled','system-exit','other')
                    and type(row['guard_site']) is str and (row['guard_site']=='unknown'
                        or row['guard_site'] in GUARD_SITES)
                    for row in value['handled_failures'])
            and len({row['role'] for row in value['handled_failures']})==len(value['handled_failures']))
    return value

ABSENT = object()

RUNTIME = builtins.RuntimeError

def codes(code):
    yield code
    for value in code.co_consts:
        if type(value) is types.CodeType:
            yield from codes(value)

def shape(value):
    if type(value) is dict:
        return tuple((shape(k), shape(v)) for k, v in value.items())
    if type(value) in (list, tuple):
        return (type(value), tuple(shape(v) for v in value))
    if type(value) in (set, frozenset):
        return (type(value), frozenset(shape(v) for v in value))
    return (type(value), value if type(value) in (str, int, float, bool, bytes, type(None)) else id(value))

def inside(position, node):
    return (position.lineno is not None and position.col_offset is not None
        and position.end_lineno is not None and position.end_col_offset is not None
        and (node.lineno, node.col_offset) <= (position.lineno, position.col_offset)
        and (position.end_lineno, position.end_col_offset) <= (node.end_lineno, node.end_col_offset))

class Owner:
    def __init__(self, module, raw, expected, label):
        require(type(module) is types.ModuleType and type(raw) is bytes
            and hashlib.sha256(raw).hexdigest() == expected and label in ('native-runner', 'native-evidence'))
        self.module, self.namespace, self.label = module, module.__dict__, label
        self.tree = ast.parse(raw)
        filename = module.__file__
        wanted = {(c.co_qualname, c.co_firstlineno): c for c in codes(compile(raw, filename, 'exec'))}
        self.functions, self.classes, self.bound = [], [], {}
        candidates = []
        for name, value in tuple(self.namespace.items()):
            if type(value) is types.FunctionType and value.__globals__ is self.namespace:
                candidates.append((self.namespace, name, value, value))
            elif type(value) is type and value.__module__ == module.__name__:
                self.classes.append((name, value, value.__bases__, dict(vars(value))))
                for attr, descriptor in tuple(vars(value).items()):
                    if type(descriptor) is staticmethod:
                        candidates.append((value, attr, descriptor.__func__, descriptor))
        self.builtins = self.namespace.get('__builtins__', ABSENT)
        if type(self.builtins) is types.ModuleType:
            self.builtins = self.builtins.__dict__
        require(type(self.builtins) is dict)
        self.builtin_cells, self.module_cells = {}, []
        for holder, name, function, descriptor in candidates:
            original = wanted.get((function.__code__.co_qualname, function.__code__.co_firstlineno))
            require(original is not None and function.__code__ == original and function.__code__.co_filename == filename
                and tuple(function.__code__.co_positions()) == tuple(original.co_positions()))
            self.functions.append((holder, name, function, descriptor, function.__code__))
            for code in codes(function.__code__):
                self.bound[code] = (function, code, {i.offset: i for i in dis.get_instructions(code, show_caches=True)})
                for name in code.co_names:
                    if name not in self.namespace:
                        self.builtin_cells[name] = self.builtins.get(name, ABSENT)
                        require(self.builtin_cells[name] is builtins.__dict__.get(name, ABSENT))
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                obj = self.namespace.get(node.value.id, ABSENT)
                if type(obj) is types.ModuleType:
                    value = vars(obj).get(node.attr, ABSENT)
                    self.module_cells.append((obj, node.attr, value, value.__code__ if type(value) is types.FunctionType else None))
        self.global_cells = dict(self.namespace)
        self.global_shapes = {k: shape(v) for k, v in self.global_cells.items() if k != '__builtins__'}
        # Original verify() rereads JSON and assigns these same public image
        # scalars before the VM. Bind their type/value, while class functions
        # and every other attribute retain exact identity.
        self.reassigned = set()
        if label == 'native-runner':
            verify = next(n for n in self.tree.body if isinstance(n, ast.FunctionDef) and n.name == 'verify')
            for node in ast.walk(verify):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        for item in ast.walk(target):
                            if isinstance(item, ast.Attribute) and isinstance(item.value, ast.Name) and item.value.id == 'R':
                                self.reassigned.add(item.attr)
            require(self.reassigned == {'SOURCE','ISO','ISO_BYTES','ISO_SHA256','ORIGINAL_RUN'})
        self.sites = [n for n in ast.walk(self.tree) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
            and n.func.value.id == 'R' and n.func.attr == 'require']
        self.sites.sort(key=lambda n: (n.lineno, n.col_offset))

    def unchanged(self):
        if set(self.namespace) != set(self.global_cells): return False
        if any(self.namespace[k] is not v for k, v in self.global_cells.items()): return False
        if any(shape(self.namespace[k]) != v for k, v in self.global_shapes.items()): return False
        if any(self.builtins.get(k, ABSENT) is not v for k, v in self.builtin_cells.items()): return False
        for name, cls, bases, attrs in self.classes:
            if self.namespace.get(name) is not cls or cls.__bases__ != bases or set(vars(cls)) != set(attrs): return False
            if any(vars(cls)[k] is not v and not (name=='R' and k in self.reassigned
                    and shape(vars(cls)[k])==shape(v)) for k, v in attrs.items()): return False
        for holder, name, function, descriptor, code in self.functions:
            current = holder.get(name, ABSENT) if type(holder) is dict else vars(holder).get(name, ABSENT)
            if current is not descriptor or function.__code__ is not code or function.__globals__ is not self.namespace: return False
        return all(vars(obj).get(name, ABSENT) is value and (code is None or value.__code__ is code)
            for obj, name, value, code in self.module_cells)

    def owns(self, frame):
        row = self.bound.get(frame.f_code)
        return row is not None and frame.f_code is row[1] and frame.f_globals is self.namespace and frame.f_builtins is self.builtins

    def site(self, frame, offset):
        if not self.owns(frame): return None
        instruction = self.bound[frame.f_code][2].get(offset)
        if instruction is None: return None
        found = [i for i, node in enumerate(self.sites, 1) if inside(instruction.positions, node)]
        return self.label + '-require-' + format(found[0], '03d') if len(found) == 1 else None

class Registry:
    def __init__(self, runner, runner_raw, runner_sha, evidence, evidence_raw, evidence_sha):
        self.owners = [Owner(runner, runner_raw, runner_sha, 'native-runner'), Owner(evidence, evidence_raw, evidence_sha, 'native-evidence')]
        require(runner.E is evidence and runner.R.__bases__ == (evidence.R,))
        descriptor = vars(evidence.R).get('require')
        require(type(descriptor) is staticmethod and runner.R.require is descriptor.__func__)
        self.guard = descriptor.__func__
        self.guard_code = self.guard.__code__
        self.guard_owner = self.owners[1]
        self.guard_raises = [n for n in ast.walk(self.guard_owner.tree) if isinstance(n, ast.Raise)
            and isinstance(n.exc, ast.Call) and isinstance(n.exc.func, ast.Name) and n.exc.func.id == 'RuntimeError'
            and len(n.exc.args) == 1 and isinstance(n.exc.args[0], ast.Name) and n.exc.args[0].id == 'message']
        self.observation = None

    def describe(self, error, tb=None):
        if type(error) is not RUNTIME or not all(o.unchanged() for o in self.owners): return None
        current = BaseException.__traceback__.__get__(error)
        if tb is not None and tb is not current: return None
        rows = []
        for _ in range(64):
            if current is None: break
            rows.append(current); current = current.tb_next
        if current is not None or len(rows) < 2: return None
        leaf, caller = rows[-1], rows[-2]
        if leaf.tb_frame.f_code is not self.guard_code or not self.guard_owner.owns(leaf.tb_frame): return None
        instruction = self.guard_owner.bound[self.guard_code][2].get(leaf.tb_lasti)
        if instruction is None or instruction.opname != 'RAISE_VARARGS': return None
        if sum(inside(instruction.positions, n) for n in self.guard_raises) != 1: return None
        owner = next((o for o in self.owners if o.owns(caller.tb_frame)), None)
        if owner is None or owner.namespace['R'].require is not self.guard: return None
        return owner.site(caller.tb_frame, caller.tb_lasti)

    def __enter__(self): return self
    def __exit__(self, kind, error, tb):
        self.observation = self.describe(error, tb) if error is not None else None
        return False

class Observation:
    def __init__(self,evidence,manifest,runner_namespace,evidence_namespace):
        self.target=Path(evidence)/HOST;self.milestones=[];self.handled_failures=[]
        self.scanner,public=source_context(manifest)
        runner=sys.modules[runner_namespace['__name__']];evidence_module=sys.modules[evidence_namespace['__name__']]
        require(runner.__dict__ is runner_namespace and evidence_module.__dict__ is evidence_namespace)
        self.public=public
        runner_raw=public[PREFIX+'runner.py'];evidence_raw=public['tools/native-functional/evidence.py']
        self.registry=Registry(runner,runner_raw,sha(runner_raw),evidence_module,evidence_raw,sha(evidence_raw))
    def __enter__(self):return self
    def milestone(self,label):
        # This owned literal-only update has no optional IO. Cancellation must
        # reach the original runner rather than disappear in instrumentation.
        require(type(label) is str and label in PHASES)
        if label not in self.milestones:self.milestones.append(label)
    def handled(self,role,error):
        try:
            require(type(role) is str and role in HANDLED and not any(row['role']==role for row in self.handled_failures))
            site=self.registry.describe(error)
            self.handled_failures.append(dict(role=role,error_class=error_class(error),guard_site=site or 'unknown'))
        except BaseException:pass
    def __exit__(self,kind,error,traceback):
        # Optional evidence may never replace the original failure or cleanup.
        try:
            site=self.registry.describe(error,traceback) if error is not None else None
            value=closed_host(dict(schema='arctic-native-host-observation-v1',
                status='failed' if error is not None else 'completed',milestones=self.milestones,
                handled_failures=self.handled_failures,
                error_class=error_class(error) if error is not None else 'none',
                guard_site=site if type(site) is str else 'unknown',
                Source_Code_globals_direct_guard_binding=type(site) is str,
                runtime_cause=False,VM_input_or_PAM_ownership=False,runtime_acceptance=False,release_acceptance=False))
            raw=encode_json(value);closed_host(strict_json(raw))
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                require(self.scanner.external_text(raw) is raw)
            write_exclusive(self.target,raw)
        except BaseException as secondary:
            if error is None and isinstance(secondary,(KeyboardInterrupt,InterruptedError,SystemExit)):raise
        return False

def stop_shape(raw,phase):
    value=strict_json(raw)
    require(type(value) is dict and set(value)=={'schema','phase','qemu_returncode','elapsed_seconds',
            'deadline_seconds','deadline_reached','exit_marker_present','reason','release_acceptance'})
    code=value['qemu_returncode'];elapsed=value['elapsed_seconds'];deadline=value['deadline_seconds']
    require((code is None or type(code) is int) and type(elapsed) in (int,float) and math.isfinite(elapsed)
            and elapsed>=0 and type(deadline) is int and deadline>0)
    reason='process-exited' if code is not None else 'deadline-expired' if elapsed>=deadline else 'exit-marker-missing'
    require(value['schema']=='arctic-native-harness-stop-v1' and value['phase']==phase
            and type(value['deadline_reached']) is bool and value['deadline_reached']==(elapsed>=deadline)
            and value['exit_marker_present'] is False and value['reason']==reason and value['release_acceptance'] is False)

def report_shape(raw,stage):
    value=strict_json(raw)
    required={'schema','stage','status','release_acceptance','gates','steps',
              'proven_new_processes','diagnostic_trace','evidence_root','remaining'}
    require(type(value) is dict and set(value) in (required,required|{'diagnostic_controls'})
            and value['schema']=='arctic-native-functional-smoke-v4'
            and value['stage']==stage and value['release_acceptance'] is False
            and value['status'] in ('failed','limited-smoke-passed')
            and type(value['gates']) is list and 0<len(value['gates'])<=32
            and type(value['steps']) is list and type(value['proven_new_processes']) is list
            and type(value['diagnostic_trace']) is dict and type(value['evidence_root']) is str
            and type(value['remaining']) is list and all(type(v) is str for v in value['remaining']))
    checks={'fresh-defaults-and-isolation','archive-content-roundtrips',
            'actual-role-file-manager-terminal-editor','open-codec-content-and-player-state',
            'portal-and-accessibility-reachability','owned-process-cleanup-config-preservation',
            'selinux-and-new-avcs'}
    require(all(type(row) is dict and type(row.get('check')) is str and row['check'] in checks
                and ((row.get('status')=='passed' and set(row)=={'check','status','value'})
                    or (row.get('status')=='failed' and set(row)=={'check','status','detail','diagnostic'}
                        and type(row['detail']) is str)) for row in value['gates'])
            and len({row['check'] for row in value['gates']})==len(value['gates']))
    if 'diagnostic_controls' in value:
        require(type(value['diagnostic_controls']) is dict
                and all(type(flag) is bool for flag in value['diagnostic_controls'].values())
                and value['diagnostic_controls']==dict(gui_v6=True,editor_physical_save=True,
                owned_player_fullscreen=True,accessibility_proof=False))

def ocr_original(scanner,raw):
    require(os.environ.get('TESSDATA_PREFIX') is None
            and not any(os.environ.get(k) for k in ('LD_PRELOAD','LD_LIBRARY_PATH')))
    for mode in (3,6,11):
        result=subprocess.run(['/usr/bin/tesseract','stdin','stdout','-l','eng','--psm',str(mode)],
            input=raw,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20,check=False)
        require(result.returncode==0 and len(result.stdout)<=256*1024 and len(result.stderr)<=64*1024)
        ok,category=screen_ocr(scanner,result.stdout);require(ok)

def private_member(scanner,path,relative,category,ocr=ocr_original):
    raw,prior=read_regular(path,8*1024*1024 if relative.endswith('.png') else 4*1024*1024)
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        if relative.endswith('.png'):
            original_png(raw);ocr(scanner,raw)
        else:
            require(scanner.external_text(raw) is raw)
            if category.startswith('stop-'):stop_shape(raw,category[len('stop-'):])
            elif category.startswith('report-'):report_shape(raw,'live' if category=='report-live' else 'installed')
            elif category=='inner-observation':INNER_OBSERVER.closed(strict_json(raw),sys.modules[__name__])
            elif category=='bootstrap-observation':BOOTSTRAP_OBSERVER.closed(strict_json(raw))
            else:closed_host(strict_json(raw))
    require(same(prior,path.lstat()) and path.resolve()==path)
    return raw,prior

def validate_staged(stage,retained,generation):
    require(stage.resolve()==stage and not stage.is_symlink()
            and (generation.st_dev,generation.st_ino,generation.st_uid,generation.st_mode)==
                tuple(getattr(stage.lstat(),key) for key in ('st_dev','st_ino','st_uid','st_mode')))
    directories={parent.as_posix() for name in retained for parent in Path(name).parents if parent!=Path('.')}
    observed=set()
    for path in stage.rglob('*'):
        relative=path.relative_to(stage).as_posix();info=path.lstat()
        require(not path.is_symlink() and info.st_uid==os.geteuid() and not info.st_mode&0o022)
        if stat.S_ISDIR(info.st_mode):require(relative in directories)
        else:require(stat.S_ISREG(info.st_mode) and relative in retained);observed.add(relative)
    require(observed==set(retained))
    for relative,(expected,prior) in retained.items():
        raw,info=read_regular(stage/relative,8*1024*1024)
        require(raw==expected and same(prior,info) and stat.S_IMODE(info.st_mode)==0o600)

def link_owned_original(pending,output,raw):
    # Hold the written inode continuously across link/unlink and compare its
    # complete bytes plus generation to the fixed staged destination.
    before=pending.lstat()
    with owned_fd(pending,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK) as fd:
        require(same(before,os.fstat(fd)))
        os.link(pending,output,follow_symlinks=False);pending.unlink()
        info=os.fstat(fd)
        require((before.st_dev,before.st_ino,before.st_uid,before.st_mode,before.st_size,before.st_mtime_ns)==
                tuple(getattr(info,key) for key in ('st_dev','st_ino','st_uid','st_mode','st_size','st_mtime_ns'))
                and info.st_nlink==1 and same(info,output.lstat()))
        checked=bytearray()
        while len(checked)<=len(raw):
            part=os.read(fd,min(65536,len(raw)+1-len(checked)))
            if not part:break
            checked.extend(part)
        require(bytes(checked)==raw and same(info,os.fstat(fd)) and same(info,output.lstat()))
    return info

def partial_screen(source,target,scanner,ocr=ocr_original):
    require(source.is_absolute() and source.resolve()==source and source.is_dir()
            and not source.is_symlink() and not target.exists() and not target.is_symlink())
    root=source.lstat();require(root.st_uid==os.geteuid() and not root.st_mode&0o022)
    files={};states={};retained={};total=0
    with tempfile.TemporaryDirectory(prefix='Native-incomplete-',dir=target.parent) as directory:
        stage=Path(directory);stage_generation=stage.lstat()
        for relative,category in ((HOST,'host-observation'),(INNER,'inner-observation'),(BOOTSTRAP,'bootstrap-observation'))+MEMBERS:
            path=source/relative
            if not path.exists():states[category]='not-observed';continue
            try:
                raw,prior=private_member(scanner,path,relative,category,ocr);total+=len(raw);require(total<=48*1024*1024)
                output=stage/relative;output.parent.mkdir(parents=True,exist_ok=True)
                with tempfile.TemporaryDirectory(prefix='member-private-',dir=stage) as private:
                    pending=Path(private)/'original';write_exclusive(pending,raw)
                    require(same(prior,path.lstat()) and path.resolve()==path)
                    generation=link_owned_original(pending,output,raw)
                retained[relative]=(raw,generation)
                files[relative]=dict(original_sha256=sha(raw),uploaded_sha256=sha(raw),bytes=len(raw),
                    crc32=zlib.crc32(raw)&0xffffffff,redactions=0,whole_original_privacy_passed=True)
                states[category]='whole-original-retained'
            except Exception:
                states[category]='rejected'
        require((root.st_dev,root.st_ino,root.st_uid,root.st_mode)==
                tuple(getattr(source.lstat(),k) for k in ('st_dev','st_ino','st_uid','st_mode')))
        status=dict(schema='arctic-native-incomplete-original-evidence-v1',complete=False,
            original_full_screen_succeeded=False,whole_original_transport_acceptance=False,
            fixed_member_states=states,host_observation_retained=states['host-observation']=='whole-original-retained',
            runtime_cause=False,runtime_acceptance=False,release_acceptance=False,
            OCR_limitations='English recognized text only; no complete glyph or Hebrew recall guarantee')
        raw=encode_json(status)
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):require(scanner.external_text(raw) is raw)
        write_exclusive(stage/'incomplete-evidence.json',raw)
        retained['incomplete-evidence.json']=(raw,(stage/'incomplete-evidence.json').lstat())
        ledger=encode_json(dict(schema='arctic-native-partial-original-ledger-v1',complete=False,
            files=files,unknown_or_rejected_member_value_size_hash_excerpt_exported=False,
            runtime_acceptance=False,release_acceptance=False))
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):require(scanner.external_text(ledger) is ledger)
        write_exclusive(stage/'upload-screening.json',ledger)
        retained['upload-screening.json']=(ledger,(stage/'upload-screening.json').lstat())
        require(set(retained)==set(files)|{'incomplete-evidence.json','upload-screening.json'})
        validate_staged(stage,retained,stage_generation)
        require(not target.exists() and not target.is_symlink())
        stage.rename(target)
        validate_staged(target,retained,stage_generation)
    return status

def publication_output(output):
    # A closed step output is emitted only after completed publication checks.
    # No content from the GitHub-provided output file is read or exported.
    output=Path(output);require(output.is_absolute() and output.resolve()==output)
    before=output.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_uid==os.geteuid()
            and before.st_nlink==1 and not before.st_mode&0o022 and before.st_size==0)
    raw=b'upload_admitted=true\n'
    with owned_fd(output,os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW|os.O_NONBLOCK) as fd:
        require(same(before,os.fstat(fd)));at=0
        while at<len(raw):
            count=os.write(fd,memoryview(raw)[at:]);require(type(count) is int and count>0);at+=count
        final=os.fstat(fd)
        require(final.st_size==len(raw) and same(final,output.lstat()))

def screen_with_partial(source,target,scanner,ocr=ocr_original,on_ready=None):
    try:result=scanner.screen_external(source,target)
    except Exception:
        try:
            partial_screen(source,target,scanner,ocr)
            if on_ready is not None:on_ready()
        except BaseException:pass
        raise
    else:
        if on_ready is not None:
            require(target.is_dir() and not target.is_symlink() and target.resolve()==target)
            on_ready()
        return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','out','manifest','github-output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();scanner,public=source_context(args.manifest)
    screen_with_partial(args.source.absolute(),args.out.absolute(),scanner,
                        on_ready=lambda:publication_output(args.github_output))

if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:
        sys.exit(130)
    except SystemExit:
        raise
    except Exception:
        print('Native full evidence screening failed; any retained diagnostics are explicitly incomplete.')
        sys.exit(1)
