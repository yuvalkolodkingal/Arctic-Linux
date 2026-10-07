"""Owned fixture primitive, no startup CLI. Returns byte mappings or fails.

A future native carrier must seal its original envp before any Python startup.
This module never publishes raw environment values; caller output is scoped.
"""
import fcntl
import os
import stat
MAGIC=b'ARCTIC_ENV_V1\0'
MAX_BYTES=1048576
MAX_FIELDS=4096
# Linux v6.18 UAPI pinned alongside this source: base1024 +9/+10; bits1/2/4/8.
F_ADD_SEALS=getattr(fcntl,'F_ADD_SEALS',1033)
F_GET_SEALS=getattr(fcntl,'F_GET_SEALS',1034)
REQUIRED_SEALS=15

def require(value,message):
    if not value:raise RuntimeError(message)

def parse_payload(raw):
    require(type(raw) is bytes and len(raw)<=MAX_BYTES and raw.startswith(MAGIC),'Invalid environment payload bound/magic')
    body=raw[len(MAGIC):]
    require(body.endswith(b'\0'),'Truncated environment record')
    fields=body[:-1].split(b'\0') if body[:-1] else []
    require(len(fields)<=MAX_FIELDS,'Environment field bound')
    result={}
    for field in fields:
        require(0<len(field)<=65536 and b'=' in field,'Unsupported raw environment field')
        key,value=field.split(b'=',1)
        require(key and key not in result,'Empty/duplicate environment name; no guessed reconstruction')
        result[key]=value
    require(b'\0'.join(key+b'='+value for key,value in result.items())+b'\0'==body,'Environment byte/order reconstruction differs')
    return result

def consume(fd,expected_uid):
    require(type(fd) is int and fd>=3 and type(expected_uid) is int and expected_uid>=0,'Untyped owned FD/UID')
    primary=None
    try:
        info=os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid==expected_uid and 0<info.st_size<=MAX_BYTES,'Environment FD type/owner/bound differs')
        require(fcntl.fcntl(fd,F_GET_SEALS)&REQUIRED_SEALS==REQUIRED_SEALS,'Environment snapshot is not completely sealed')
        raw=os.pread(fd,info.st_size,0)
        require(len(raw)==info.st_size and os.pread(fd,1,info.st_size)==b'','Environment snapshot size differs')
        result=parse_payload(raw)
    except BaseException as error:
        primary=error
        raise
    finally:
        # Exact received owned FD is consumed once. A close error is fatal before
        # any target launch, and no retry can close a reused unrelated FD.
        try:os.close(fd)
        except BaseException as error:
            if primary is None:raise
            primary.add_note('Environment FD cleanup also failed: '+str(error))
    return result
