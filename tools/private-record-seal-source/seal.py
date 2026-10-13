#!/usr/bin/env python3
"""Encrypt one authenticated rejected serial-install record without disclosing it."""
import builtins,hashlib,json,os,re,stat,subprocess,types
from pathlib import Path

AGE_VERSION='v1.2.1'
AGE_ARCHIVE_SHA256='7df45a6cc87d4da11cc03a539a7470c15b1041ab2b396af088fe9990f7c79d50'
AGE_PROOF_SHA256='55b941732d9fc88b0db9f954f2de2bb5a8bacb6479063b2cf5f244ffbb9b3f3a'
AGE_BINARY_SHA256='aaec874ed903da4b02a9d503778ae05ee5005b2acc0f4a4cf10e5d0f17fd4384'
SCANNER_SHA256='0c2176c4892e45e485eeac32f564fdfe9fb1619f142ac0b60babeed52924075f'
DIAGNOSTIC_SHA256='cc521c0e7d4fe4c6b95b62b3a53a930b916ffa1dd607eac601d4c200740fb5cc'
ENVELOPE_BYTES=16384
MAGIC=b'ARCTIC-PRIVATE-RECORD-V1\x00'
BECH32=frozenset('qpzry9x8gf2tvdw0s3jn54khce6mua7l')
ABSENT=object()
SEAL_STAGE_UNKNOWN='private-seal-stage-unknown'
SEAL_STAGE_LABELS=frozenset({
    'private-seal-stage-finite-contract','private-seal-stage-traceback-binding',
    'private-seal-stage-scanner-frame','private-seal-stage-match-locals',
    'private-seal-stage-unit-family','private-seal-stage-source-replay',
    'private-seal-stage-record-boundary','private-seal-stage-record-roundtrip',
    'private-seal-stage-encryption',SEAL_STAGE_UNKNOWN})
SEAL_FAILURE_MESSAGE='Private record sealing failed closed'

class SealStageError(RuntimeError):
    """Carry one authenticated, closed label and no rejected-record detail."""
    def __init__(self,label):
        self.label=label if type(label)is str and label in SEAL_STAGE_LABELS else SEAL_STAGE_UNKNOWN
        super().__init__(SEAL_FAILURE_MESSAGE)

def staged(label,function):
    if type(label)is not str or label not in SEAL_STAGE_LABELS or label==SEAL_STAGE_UNKNOWN:
        raise SealStageError(SEAL_STAGE_UNKNOWN)
    try:return function()
    except BaseException:raise SealStageError(label) from None

def closed_failure_label(error):
    """Map any object to a fixed public label without reading foreign exception data."""
    if type(error)is SealStageError:
        try:
            label=object.__getattribute__(error,'label')
            args=BaseException.args.__get__(error,SealStageError)
        except BaseException:
            return SEAL_STAGE_UNKNOWN
        if (type(label)is str and label in SEAL_STAGE_LABELS and type(args)is tuple
                and len(args)==1 and type(args[0])is str and args[0]is SEAL_FAILURE_MESSAGE):
            return label
    return SEAL_STAGE_UNKNOWN

def require(value,message='Private record sealing contract differs'):
    if not value:raise RuntimeError(message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def codes(code):
    yield code
    for value in code.co_consts:
        if type(value)is types.CodeType:yield from codes(value)
def load(raw,path,name):
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module
def regular(path,limit):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode)and before.st_uid==os.getuid()and before.st_nlink==1
                and 0<before.st_size<=limit,'Pinned age executable differs')
        with os.fdopen(fd,'rb',closefd=False)as stream:raw=stream.read(limit+1)
        after=os.fstat(fd)
        require(len(raw)==before.st_size and (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==
                (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns),'Pinned age executable changed')
        return raw
    finally:os.close(fd)
def validate_recipient(recipient,expected):
    require(type(recipient)is str and len(recipient)==62 and recipient.startswith('age1')
            and all(c in BECH32 for c in recipient[4:]),'Pinned age recipient syntax differs')
    require(type(expected)is str and re.fullmatch('[0-9a-f]{64}',expected)is not None
            and sha((recipient+'\n').encode())==expected,'Pinned age recipient digest differs')
    return recipient
def owned_function(frame,name,raw):
    function=frame.f_globals.get(name,ABSENT)
    require(type(function)is types.FunctionType and function.__code__ is frame.f_code
            and function.__globals__ is frame.f_globals,'Exact scanner frame ownership differs')
    expected=[c for c in codes(compile(raw,frame.f_code.co_filename,'exec'))
              if(c.co_qualname,c.co_firstlineno)==(frame.f_code.co_qualname,frame.f_code.co_firstlineno)]
    require(len(expected)==1 and frame.f_code==expected[0]
            and tuple(frame.f_code.co_lines())==tuple(expected[0].co_lines()),'Exact scanner Source Code differs')
    refs={n:frame.f_globals.get(n,ABSENT)for n in frame.f_code.co_names}
    namespace=frame.f_builtins
    builtin_refs={n:namespace.get(n,ABSENT)for n,v in refs.items()if v is ABSENT}
    require(type(namespace)is dict and all(v is builtins.__dict__.get(n,ABSENT)
            for n,v in builtin_refs.items()),'Exact scanner globals differ')
    return function
def finite_contract(state):
    require(type(state)is dict and set(state)=={'finite','context'})
    value=state['finite'];require(type(value)is dict)
    require(value.get('schema')=='arctic-bios-strict-original-source-failure-v1'
            and value.get('original_records_stage')=='live'
            and value.get('actual_raising_Source_Code_globals_owned')is True
            and value.get('actual_runtime_cause_proven')is False
            and value.get('exception_unchanged')is True
            and value.get('privacy_admitted')is False
            and value.get('release_acceptance')is False)
    same=value.get('same_rejected_match');require(type(same)is dict)
    family=same.get('unit_record_family');require(family=={
        'schema':'arctic-unit-record-family-source-diagnostic-v1',
        'source_member_id':'serial-install-log','unit_family_id':'repo-xdg-autostart-unit',
        'record_family_id':'unknown','exact_repo_attested_unit_family':True,
        'exact_repo_attested_record_family':False,'privacy_admitted':False,
        'runtime_cause_proven':False,'operand_value_or_digest_exported':False,
        'release_acceptance':False})
    return family
def exact_record(error,state,scanner_raw,diagnostic_raw,diagnostic_path):
    """Return one mutable original record only after the existing closed proof agrees."""
    family=staged('private-seal-stage-finite-contract',lambda:finite_contract(state))
    def traceback_binding():
        require(type(error)is builtins.RuntimeError and sha(scanner_raw)==SCANNER_SHA256 and sha(diagnostic_raw)==DIAGNOSTIC_SHA256)
        rows=[];tb=BaseException.__traceback__.__get__(error)
        for _ in range(64):
            if tb is None:break
            rows.append(tb);tb=tb.tb_next
        require(tb is None)
        return rows
    rows=staged('private-seal-stage-traceback-binding',traceback_binding)
    def scanner_frame():
        matches=[row.tb_frame for row in rows if row.tb_frame.f_code.co_name=='reject_sensitive_match' and row.tb_frame.f_locals.get('error')is error]
        require(len(matches)==1,'Exact rejected scanner frame differs')
        frame=matches[0];owned_function(frame,'reject_sensitive_match',scanner_raw)
        return frame
    frame=staged('private-seal-stage-scanner-frame',scanner_frame)
    def match_locals():
        scanner=types.ModuleType('private_record_exact_scanner');scanner.__dict__.update(frame.f_globals)
        match=frame.f_locals.get('match');phase=frame.f_locals.get('phase')
        original=frame.f_locals.get('original');boundaries=frame.f_locals.get('boundaries');removed=frame.f_locals.get('removed')
        require(type(match)is re.Match and phase=='source-view'and type(original)is str and match.re is scanner.EXTERNAL_SENSITIVE and type(boundaries)is scanner.array and type(removed)is scanner.array and 0<match.end()-match.start()<=256)
        return scanner,match,phase,original,boundaries,removed
    scanner,match,phase,original,boundaries,removed=staged('private-seal-stage-match-locals',match_locals)
    def unit_family():
        diagnostic=load(diagnostic_raw,diagnostic_path,'private_record_exact_diagnostic')
        helper=types.ModuleType('private_record_exact_alignment')
        helper.diagnostic_view_alignment=lambda *unused:{'regex':'exact-scanner-regex','offsets':'exact-scanner-span','mapping':'exact-source-view'}
        observed=diagnostic.diagnostic_unit_record_family(scanner,helper,match,phase,original,boundaries,removed,stage='live',enabled=True)
        require(observed==family,'Closed unit/member proof no longer agrees')
    staged('private-seal-stage-unit-family',unit_family)
    def source_replay():
        view,check_boundaries,check_removed=scanner.classification_view(original)
        require(view==match.string and check_boundaries==boundaries and check_removed==removed)
        return view
    view=staged('private-seal-stage-source-replay',source_replay)
    def record_boundary():
        left=max(view.rfind('\n',0,match.start()),view.rfind('\r',0,match.start()))+1
        ends=[n for n in(view.find('\n',match.end()),view.find('\r',match.end()))if n>=0]
        right=min(ends)if ends else len(view)
        require(0<=left<=match.start()<match.end()<=right<=len(view)and right-left<=4096)
        first,last=scanner.original_span(left,right,boundaries,removed)
        require(0<=first<last<=len(original)and last-first<=8192)
        return left,right,first,last
    left,right,first,last=staged('private-seal-stage-record-boundary',record_boundary)
    def record_roundtrip():
        record=original[first:last];cleaned,_,_=scanner.classification_view(record)
        require(cleaned==view[left:right]and '\n'not in cleaned and '\r'not in cleaned)
        return bytearray(record.encode('utf-8'))
    return staged('private-seal-stage-record-roundtrip',record_roundtrip)
def envelope(record):
    require(type(record)is bytearray and 0<len(record)<=8192)
    head=MAGIC+len(record).to_bytes(4,'big')
    require(len(head)+len(record)<=ENVELOPE_BYTES)
    return bytearray(head)+record+bytearray(os.urandom(ENVELOPE_BYTES-len(head)-len(record)))
def wipe(value):
    if type(value)is bytearray:
        for index in range(len(value)):value[index]=0
def exclusive(path,data):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb',closefd=False)as stream:
            stream.write(data);stream.flush();os.fsync(fd)
    finally:os.close(fd)
def encrypt_record(age_binary,recipient,recipient_sha256,record,sealed_out,receipt_public):
    """Write only fixed-size age ciphertext and a closed non-sensitive receipt."""
    validate_recipient(recipient,recipient_sha256)
    age_binary=Path(age_binary);raw=regular(age_binary,16*1024*1024)
    require(sha(raw)==AGE_BINARY_SHA256 and os.access(age_binary,os.X_OK))
    version=subprocess.run([str(age_binary),'--version'],stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env={'PATH':'/usr/bin:/bin'},
        timeout=10,check=True).stdout.decode('ascii').strip()
    require(version==AGE_VERSION,'Pinned age version differs')
    sealed_out=Path(sealed_out);require(not sealed_out.exists()and sealed_out.parent.is_dir())
    sealed_out.mkdir(mode=0o700)
    cipher=sealed_out/'record.age';receipt=sealed_out/'receipt.json'
    payload=None;fd=None
    try:
        payload=envelope(record);wipe(record)
        fd=os.open(cipher,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        process=subprocess.Popen([str(age_binary),'--encrypt','--recipient',recipient],
            stdin=subprocess.PIPE,stdout=fd,stderr=subprocess.DEVNULL,
            env={'PATH':'/usr/bin:/bin'},close_fds=True)
        try:
            process.communicate(bytes(payload),timeout=30)
        except BaseException:
            process.kill();process.wait();raise
        finally:
            os.fsync(fd);os.close(fd);fd=None;wipe(payload)
        require(process.returncode==0 and cipher.is_file()and not cipher.is_symlink())
        public=dict(receipt_public)
        require(set(public)=={'execution_commit','source_commit','image_sha256'}
                and all(type(v)is str and re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}',v)for v in public.values()))
        public.update(schema='arctic-private-record-seal-receipt-v1',
            source_member_id='serial-install-log',records_encrypted=1,
            envelope_bytes=ENVELOPE_BYTES,ciphertext_sha256=sha(cipher.read_bytes()),
            recipient_sha256=recipient_sha256,age_version=AGE_VERSION,
            age_archive_sha256=AGE_ARCHIVE_SHA256,age_proof_sha256=AGE_PROOF_SHA256,
            age_binary_sha256=AGE_BINARY_SHA256,plaintext_written_by_observer=False,
            plaintext_stdout=False,plaintext_stderr=False,public_plaintext_artifact=False,
            scanner_changed=False,privacy_gate_changed=False,runtime_gate_changed=False,
            release_acceptance=False)
        exclusive(receipt,(json.dumps(public,sort_keys=True,indent=2)+'\n').encode())
        return public
    except BaseException:
        if fd is not None:
            try:os.close(fd)
            except OSError:pass
        wipe(record);wipe(payload)
        try:cipher.unlink()
        except FileNotFoundError:pass
        try:receipt.unlink()
        except FileNotFoundError:pass
        try:sealed_out.rmdir()
        except OSError:pass
        raise
def seal_failure(error,state,scanner_raw,diagnostic_raw,diagnostic_path,age_binary,
                 recipient,recipient_sha256,sealed_out,receipt_public):
    record=exact_record(error,state,scanner_raw,diagnostic_raw,diagnostic_path)
    try:
        return staged('private-seal-stage-encryption',lambda:encrypt_record(
            age_binary,recipient,recipient_sha256,record,sealed_out,receipt_public))
    finally:
        wipe(record)
