#!/usr/bin/env python3
"""Exact two read-only data origins; generated cache is not signed content."""
import hashlib,json,mmap,os,re,stat,time
from pathlib import Path
PATHS={'/usr/lib/locale/C.utf8/LC_CTYPE','/usr/lib64/gconv/gconv-modules.cache'}
HEADER='[%{FILENAMES}\t%{FILEDIGESTS}\t%{FILEMODES}\t%{FILEUSERNAME}\t%{FILEGROUPNAME}\t%{FILEFLAGS}\t%{FILEVERIFYFLAGS}\t%{FILESIZES}\n]'
def require(value,message):
 if not value:raise RuntimeError(message)
def configuration(root):
 value=json.loads((root/'candidate-data-mappings.json').read_text())
 require(value['schema']=='arctic-candidate-input-data-v1' and value['candidate_iso_sha256']=='84c9c88ebcbcaf69dbabf56509a9ceb2db58e5dc41d7bae12093edba12f60718'
         and set(value['files'])==PATHS,'exact two data receipts required')
 return value
def identity(info):
 return {key:getattr(info,'st_'+key) for key in ('dev','ino','size','mode','uid','gid','mtime_ns','ctime_ns')}
def check_maps(raw):
 require(type(raw) is bytes and 0<len(raw)<=262144 and raw.endswith(b'\n'),'complete bounded producer maps required')
 found={};previous_end=0
 for line in raw.decode('utf-8','strict').splitlines():
  fields=line.split(maxsplit=5)
  require(len(fields)>=5 and re.fullmatch('[0-9a-f]+-[0-9a-f]+',fields[0]) and re.fullmatch('[r-][w-][x-][ps]',fields[1])
          and re.fullmatch('[0-9a-f]+',fields[2]) and re.fullmatch('[0-9a-f]+:[0-9a-f]+',fields[3]) and re.fullmatch('[0-9]+',fields[4]),
          'malformed complete maps row')
  start,end=(int(x,16) for x in fields[0].split('-'));require(0<start<end<2**64 and start>=previous_end,'invalid or backwards/overlapping map region');previous_end=end
  if len(fields)!=6:continue
  text=fields[5];base=text.removesuffix(' (deleted)')
  if base not in PATHS:continue
  require(text==base and fields[1] in ('r--p','r--s'),'data mapping deleted or has write/execute permissions')
  major,minor=(int(x,16) for x in fields[3].split(':'));inode=int(fields[4])
  require(0<inode<2**64 and 0<major+minor and max(major,minor)<2**32,'data mapped object identity unavailable')
  found.setdefault(text,[]).append(dict(start=start,end=end,permissions=fields[1],offset=int(fields[2],16),device_major=major,device_minor=minor,inode=inode,path=text))
 return found
def snapshot(collector,held_mapping=None):
 # Explicit bounded multi-read observation; no atomic all-maps snapshot claim.
 fd=os.open('/proc/self/maps',os.O_RDONLY|os.O_CLOEXEC);start=time.monotonic_ns();parts=[];reads=[]
 held=held_mapping is not None
 try:
  if held:require(held_mapping.closed is False,'owned mmap is not held before walk')
  for _ in range(128):
   require(time.monotonic_ns()-start<=5_000_000_000,'controlled maps walk deadline')
   part=os.read(fd,16384);reads.append(len(part))
   if not part:break
   parts.append(part);require(sum(reads)<=262144,'controlled maps walk byte overflow')
  require(reads and reads[-1]==0,'controlled maps walk missing EOF/read bound')
  if held:require(held_mapping.closed is False,'owned mmap ceased during walk')
 finally:os.close(fd)
 raw=b''.join(parts);check_maps(raw)
 return dict(raw=raw.decode('utf-8','strict'),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),monotonic_start_ns=start,
             monotonic_end_ns=time.monotonic_ns(),atomic_all_maps_claim=False,controlled_multi_read_walk=True,
             read_lengths=reads,read_calls=len(reads),eof_observed=True,held_mapping_during_walk=held,
             collector=collector,mount_namespace=os.readlink('/proc/self/ns/mnt'))
def bridge(item,expected_collector=None):
 value=item.get('readonly_fd_mapping');require(isinstance(value,dict),'actual FD-backed data mapping proof required')
 collector=value['collector'];require(isinstance(collector,dict) and set(collector)=={'pid','start_ticks','uid','executable','executable_sha256'}
  and all(type(collector[k]) is int and collector[k]>1 for k in ('pid','start_ticks')) and type(collector['uid']) is int and collector['uid']==0
  and collector['executable']=='/usr/bin/python3.14' and re.fullmatch('[0-9a-f]{64}',collector['executable_sha256']), 'owned root collector identity differs')
 if expected_collector is not None:require(collector=={key:expected_collector[key] for key in collector},'same-boot owned collector/launcher identity differs')
 require(value['fd_identity_before']==item['identity_before'] and value['fd_identity_after']==item['identity_after']
  and type(value['fd']) is int and value['fd']>=3 and value['fd_hashes']==[item['sha256'],item['sha256']]
  and value['mmap_sha256']==item['sha256'] and value['readonly'] is True and value['closed'] is True
  and value.get('fd_closed') is True and value['cleanup_errors']==[],'same FD read/stat/mmap/hash or cleanup differs')
 snapshots=[value[key] for key in ('before','during','during_confirm','after_close')];parsed=[];previous=0;namespace=None
 for index,view in enumerate(snapshots):
  raw=view['raw'].encode('utf-8');require(type(view['bytes']) is int and len(raw)==view['bytes'] and hashlib.sha256(raw).hexdigest()==view['sha256']
   and view['atomic_all_maps_claim'] is False and view['controlled_multi_read_walk'] is True and view['eof_observed'] is True
   and view['held_mapping_during_walk'] is (index in (1,2)) and view['collector']==collector
   and all(type(view[k]) is int for k in ('monotonic_start_ns','monotonic_end_ns'))
   and previous<=view['monotonic_start_ns']<=view['monotonic_end_ns'] and view['monotonic_start_ns']>0
   and view['monotonic_end_ns']-view['monotonic_start_ns']<=5_000_000_000 and re.fullmatch(r'mnt:\[[0-9]+\]',view['mount_namespace']), 'bounded controlled maps walk provenance differs')
  lengths=view['read_lengths'];require(isinstance(lengths,list) and 1<=len(lengths)<=128 and type(view['read_calls']) is int and view['read_calls']==len(lengths)
   and type(lengths[-1]) is int and lengths[-1]==0 and all(type(n) is int and 0<n<=16384 for n in lengths[:-1]) and sum(lengths)==len(raw),'complete bounded multi-read framing differs')
  previous=view['monotonic_end_ns'];namespace=namespace or view['mount_namespace'];require(namespace==view['mount_namespace'],'collector mount namespace changed')
  parsed.append(check_maps(raw).get(item['path'],[]))
 before,during,confirmed,closed=parsed
 require(confirmed==during,'held target VMA changed between complete walks')
 require(all(row in during for row in before) and closed==before,'target maps changed/merged before or after owned close')
 added=[row for row in during if row not in before];require(len(added)==1 and len(during)==len(before)+1,'unique newly observed target mapping required')
 row=added[0];page=value['page_bytes'];require(type(page) is int and 0<page<=65536 and page&(page-1)==0
  and row['permissions']=='r--s' and row['offset']==0 and row['end']-row['start']==((item['bytes']+page-1)//page)*page
  and value['backing_object']==row,'actual same-FD read-only region/size/backing tuple differs')
 return row
def pair_producer(item,rows):
 backing=bridge(item);require(isinstance(rows,list) and rows and all(
  (row['device_major'],row['device_minor'],row['inode'])==(backing['device_major'],backing['device_minor'],backing['inode']) for row in rows),
  'producer data mapping differs from proved same-FD backing object')
 return item
def check_origin(item,metadata):
 require(isinstance(item,dict) and item.get('path') in PATHS,'unknown mapped data refused')
 expected=metadata['files'][item['path']]
 require(type(item.get('bytes')) is int and 0<item['bytes']<=expected['max_bytes'] and item.get('non_executable_data') is True
         and all(type(item.get(k)) is int for k in ('uid','gid','mode','inode','device'))
         and item['uid']==item['gid']==0 and item['mode']==expected['mode']==0o644 and item['inode']>0 and item['device']>=0
         and isinstance(item.get('sha256'),str) and re.fullmatch('[0-9a-f]{64}',item['sha256']), 'bounded root data identity differs')
 require(item.get('rpm_nevra')==expected['rpm_nevra'] and type(item.get('epoch')) is int and item['epoch']==expected['epoch']==0
         and item.get('file_header')==expected['signed_header'] and item.get('verification')==[0,'','']
         and type(item['verification'][0]) is int and item.get('signed_payload_sha256')==expected['signed_payload_sha256']
         and type(item.get('signed_content_allowlist')) is bool and item['signed_content_allowlist'] is expected['signed_content_allowlist'],
         'exact data RPM/header origin differs')
 before=item.get('identity_before');after=item.get('identity_after')
 require(isinstance(before,dict) and before==after and set(before)=={'dev','ino','size','mode','uid','gid','mtime_ns','ctime_ns'}
         and all(type(v) is int and v>=0 for v in before.values()) and before['mode']==0o100644
         and before['uid']==before['gid']==0 and before['dev']==item['device'] and before['ino']==item['inode']
         and before['size']==item['bytes'],'mapped data stat changed/typed identity differs')
 require(item.get('sha256_before')==item.get('sha256_after')==item['sha256'],'mapped data bytes changed')
 if expected['signed_content_allowlist']:
  require(item['sha256']==expected['signed_payload_sha256'] and item['bytes']==expected['signed_payload_bytes']
          and item.get('origin_kind')=='signed-locale-content','signed C locale content differs')
 else:
  require(expected['signed_payload_bytes']==0 and expected['signed_payload_sha256']==hashlib.sha256(b'').hexdigest()
          and item.get('origin_kind')=='generated-conversion-cache' and item['sha256']!=expected['signed_payload_sha256'],
          'generated cache misrepresented as signed payload')
 return item
def check_record(item,metadata,expected_collector=None):
 check_origin(item,metadata);bridge(item,expected_collector);return item
def collect(text,N,metadata,producer_maps):
 require(text in PATHS,'unknown mapped data refused')
 path=Path(text);before=path.lstat();expected=metadata['files'][text]
 require(stat.S_ISREG(before.st_mode) and before.st_uid==before.st_gid==0 and stat.S_IMODE(before.st_mode)==0o644
         and 0<before.st_size<=expected['max_bytes'],'mapped data file type/permissions/bound differs')
 current=N.identity(os.getpid(),0);require(current['pid']==os.getpid() and current['executable']=='/usr/bin/python3.14','root collector process differs')
 collector=dict(current,uid=0,executable_sha256=N.digest(Path(current['executable'])))
 fd=None;mapping=None;primary=None;cleanup=[];result=None
 try:
  fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
  fd_before=identity(os.fstat(fd));require(fd_before==identity(before),'mapped data changed before open')
  def read():
   os.lseek(fd,0,os.SEEK_SET)
   with os.fdopen(fd,'rb',closefd=False) as stream:data=stream.read(expected['max_bytes']+1)
   require(len(data)==before.st_size and not data.startswith(b'\x7fELF') and identity(os.fstat(fd))==identity(before),'mapped data bytes/type/stat changed')
   return hashlib.sha256(data).hexdigest()
  digest=read();view_before=snapshot(collector)
  mapping=mmap.mmap(fd,before.st_size,access=mmap.ACCESS_READ);view_during=snapshot(collector,mapping)
  map_digest=hashlib.sha256(mapping[:]).hexdigest()
  status,owner,err=N.execute(['rpm','-qf','--qf','%{NEVRA}\t%{EPOCHNUM}\n',text],timeout=15)
  require(status==0 and err=='' and owner==expected['rpm_nevra']+'\t0','data owner/epoch differs')
  status,header,err=N.execute(['rpm','-q','--qf',HEADER,expected['rpm_nevra']],timeout=15)
  require(status==0 and err=='' and len(header.encode())<=65536,'bounded data header unavailable')
  matches=[line for line in header.split('\n') if line.split('\t',1)[0]==text];require(matches==[expected['signed_header']],'data signed file header differs')
  verification=N.execute(['rpm','-V',expected['rpm_nevra']],timeout=15);require(verification==(0,'',''),'current data owner RPM verification differs')
  after_digest=read();fd_after=identity(os.fstat(fd));after=path.lstat();view_confirm=snapshot(collector,mapping)
  mapping.close();mapping=None;view_closed=snapshot(collector)
  require(N.identity(os.getpid(),0)==current and N.digest(Path(current['executable']))==collector['executable_sha256'],'collector process/ELF changed')
  result=dict(path=text,sha256=digest,sha256_before=digest,sha256_after=after_digest,bytes=before.st_size,uid=before.st_uid,gid=before.st_gid,
   mode=stat.S_IMODE(before.st_mode),inode=before.st_ino,device=before.st_dev,identity_before=identity(before),identity_after=identity(after),
   rpm_nevra=expected['rpm_nevra'],epoch=0,file_header=matches[0],verification=list(verification),signed_payload_sha256=expected['signed_payload_sha256'],
   signed_content_allowlist=expected['signed_content_allowlist'],non_executable_data=True,
   origin_kind='signed-locale-content' if expected['signed_content_allowlist'] else 'generated-conversion-cache',
   readonly_fd_mapping=dict(collector=collector,fd=fd,fd_identity_before=fd_before,fd_identity_after=fd_after,fd_hashes=[digest,after_digest],
    before=view_before,during=view_during,during_confirm=view_confirm,after_close=view_closed,mmap_sha256=map_digest,page_bytes=os.sysconf('SC_PAGE_SIZE'),
    backing_object={},readonly=True,closed=True,cleanup_errors=[]),
   scope='Explicit read-only collector mapping bridges merged-path and backing-file identity. Walks are explicitly sequential/bounded/multi-read/EOF-complete target observations, not atomic all-maps snapshots; held VMA is confirmed twice; producer namespace and original map endpoint remain unobserved. Cache runtime hash is not signed content or input-cause proof.')
  before_rows=check_maps(view_before['raw'].encode()).get(text,[]);during_rows=check_maps(view_during['raw'].encode()).get(text,[])
  added=[row for row in during_rows if row not in before_rows];require(len(added)==1,'unique added owned data mapping unavailable')
  result['readonly_fd_mapping']['backing_object']=added[0]
 except BaseException as exc:primary=exc
 finally:
  if mapping is not None:
   try:mapping.close()
   except BaseException as exc:cleanup.append('mmap close: '+type(exc).__name__+': '+str(exc))
  if fd is not None:
   try:os.close(fd)
   except BaseException as exc:cleanup.append('FD close: '+type(exc).__name__+': '+str(exc))
 if cleanup:raise RuntimeError('data collector failed: '+str(primary)+'; owned cleanup: '+'; '.join(cleanup))
 if primary is not None:raise primary
 result['readonly_fd_mapping']['fd_closed']=True
 check_record(result,metadata);pair_producer(result,check_maps(producer_maps).get(text,[]))
 return result
