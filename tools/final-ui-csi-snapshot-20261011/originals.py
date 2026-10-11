#!/usr/bin/env python3
"""Exact reviewed owned-FD, original PNG and three-mode OCR primitives."""
import contextlib,hashlib,io,json,os,re,signal,stat,struct,subprocess,zlib
from contextlib import contextmanager
from pathlib import Path
from PIL import Image
FIELDS=('st_dev','st_ino','st_uid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
def require(value,label=None):
    if not value:raise ValueError('Closed UI original evidence rejected')
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

def ocr_original(scanner,raw):
    require(os.environ.get('TESSDATA_PREFIX') is None
            and not any(os.environ.get(k) for k in ('LD_PRELOAD','LD_LIBRARY_PATH')))
    for mode in (3,6,11):
        result=subprocess.run(['/usr/bin/tesseract','stdin','stdout','-l','eng','--psm',str(mode)],
            input=raw,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20,check=False)
        require(result.returncode==0 and len(result.stdout)<=256*1024 and len(result.stderr)<=64*1024)
        ok,category=screen_ocr(scanner,result.stdout);require(ok)

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
