"""Collect whole owned build RPMs and ELF/debug joins inside the disposable container."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import zlib

ROOT=Path('/build/arctic-accelerator-ab')
OUT=Path('/out')
PACKAGES=('epiphany','epiphany-runtime','epiphany-debuginfo','epiphany-runtime-debuginfo','epiphany-debugsource')
MAX_RPM=32*1024*1024
MAX_CPIO=128*1024*1024

def require(value,reason):
 if not value:raise RuntimeError(reason)

def read(path,limit):
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  before=os.fstat(fd)
  identity=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
  require(stat.S_ISREG(before.st_mode) and before.st_uid==0 and 0<before.st_size<=limit,'collect_owned_file')
  raw=os.pread(fd,before.st_size+1,0)
  require(len(raw)==before.st_size and identity(os.fstat(fd))==identity(before)==identity(path.lstat()),'collect_changed_file')
  return raw
 finally:os.close(fd)

def write(path,raw):
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
 try:
  view=memoryview(raw)
  while view:
   count=os.write(fd,view);require(count>0,'collect_short_write');view=view[count:]
 finally:os.close(fd)

def cpio(raw):
 result={};groups={};position=0
 while position<len(raw):
  require(raw[position:position+6] in (b'070701',b'070702'),'collect_cpio_header')
  fields=[int(raw[position+6+i*8:position+14+i*8],16) for i in range(13)]
  size,namesize=fields[6],fields[11]
  require(0<namesize<=4096 and size<=MAX_CPIO,'collect_cpio_bound')
  start=position+110;end=start+namesize
  require(raw[end-1:end]==b'\0','collect_cpio_name')
  name=raw[start:end-1].decode('utf-8');begin=(end+3)&~3;data=raw[begin:begin+size]
  require(len(data)==size,'collect_cpio_data');position=(begin+size+3)&~3
  if name=='TRAILER!!!':
   require(not any(raw[position:]),'collect_cpio_tail')
   for members in groups.values():
    contents={value for _,_,value in members if value}
    require(len(contents)<=1,'collect_hardlink_bytes')
    if contents:
     data=contents.pop()
     for name,mode,_ in members:result[name]=(mode,data)
   return result
  require(name not in result and name.startswith('./') and '..' not in name.split('/') and '\0' not in name,'collect_cpio_path')
  result[name]=(fields[1],data)
  if stat.S_ISREG(fields[1]) and fields[4]>1:
   groups.setdefault((fields[0],fields[7],fields[8]),[]).append((name,fields[1],data))
 raise RuntimeError('collect_cpio_trailer')

def payload(path):
 # No paths from the package are extracted. The entire bounded stream is parsed.
 process=subprocess.Popen(['rpm2cpio',str(path)],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
 data=bytearray()
 try:
  while True:
   part=process.stdout.read(65536)
   if not part:break
   require(len(data)+len(part)<=MAX_CPIO,'collect_cpio_limit');data.extend(part)
  require(process.wait(timeout=30)==0,'collect_rpm2cpio')
 finally:
  if process.poll() is None:process.kill()
  process.wait(timeout=30);process.stdout.close()
 return cpio(bytes(data))

def sections(raw):
 require(raw[:6]==b'\x7fELF\x02\x01' and len(raw)>=64,'collect_ELF64_LE')
 offset=struct.unpack_from('<Q',raw,40)[0];stride,count,strings=struct.unpack_from('<HHH',raw,58)
 require(stride==64 and 0<count<65536 and strings<count and offset+count*stride<=len(raw),'collect_ELF_sections')
 rows=[struct.unpack_from('<IIQQQQIIQQ',raw,offset+i*stride) for i in range(count)]
 names=rows[strings];table=raw[names[4]:names[4]+names[5]];require(len(table)==names[5],'collect_ELF_names')
 result={}
 for row in rows:
  require(row[0]<len(table),'collect_ELF_name_offset');end=table.find(b'\0',row[0]);require(end>=0,'collect_ELF_name_end')
  name=table[row[0]:end].decode('ascii')
  if row[1]!=8:
   value=raw[row[4]:row[4]+row[5]];require(len(value)==row[5],'collect_ELF_section_bound')
   require(name not in result,'collect_ELF_duplicate_section');result[name]=value
 return result

def build_id(raw):
 note=sections(raw).get('.note.gnu.build-id',b'');require(len(note)>=16,'collect_build_id')
 names,desc,kind=struct.unpack_from('<III',note)
 begin=(12+names+3)&~3
 require(kind==3 and note[12:12+names]==b'GNU\0' and desc==20 and begin+desc<=len(note),'collect_build_id_note')
 return note[begin:begin+desc].hex()

def debuglink(raw):
 link=sections(raw).get('.gnu_debuglink',b'');end=link.find(b'\0');require(end>0,'collect_debuglink')
 offset=(end+1+3)&~3;require(offset+4==len(link),'collect_debuglink_crc')
 return link[:end].decode('ascii'),struct.unpack_from('<I',link,offset)[0]

def collect(variant):
 require(variant in ('baseline','candidate'),'collect_variant')
 package_dir=ROOT/variant/'RPMS/x86_64';paths=sorted(package_dir.iterdir())
 expected={name+'-50.6-1.fc44.x86_64.rpm' for name in PACKAGES}
 require({p.name for p in paths}==expected,'collect_RPM_group')
 target=OUT/variant;target.mkdir(mode=0o700);elfdir=target/'ELF';elfdir.mkdir(mode=0o700)
 packages={};elfs={}
 for path in paths:
  raw=read(path,MAX_RPM);destination=target/path.name;write(destination,raw)
  require(read(destination,MAX_RPM)==raw,'collect_RPM_same_buffer')
  header=subprocess.check_output(['rpm','-qp','--qf','%{NAME}|%{EPOCHNUM}|%{VERSION}|%{RELEASE}|%{ARCH}',str(destination)],timeout=30).decode('ascii')
  require(header in {name+'|1|50.6|1.fc44|x86_64' for name in PACKAGES},'collect_RPM_header')
  members=payload(destination);require(read(destination,MAX_RPM)==raw,'collect_RPM_changed')
  packages[path.name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'header':header}
  for name,(mode,value) in members.items():
   if stat.S_ISREG(mode) and value.startswith(b'\x7fELF'):
    # Retain every ELF from the five exact built packages; closed flattened
    # names prevent arbitrary package filenames becoming host paths.
    require(name not in elfs,'collect_duplicate_ELF')
    file='elf-'+format(len(elfs),'03d')+'.bin';write(elfdir/file,value)
    elfs[name]={'file':file,'RPM':path.name,'bytes':len(value),'sha256':hashlib.sha256(value).hexdigest(),'build_id':build_id(value)}
 main='./usr/lib64/epiphany/libephymain.so';launcher='./usr/bin/epiphany'
 require(main in elfs and launcher in elfs,'collect_required_ELF')
 joins={}
 for role,name in (('main_library',main),('launcher',launcher)):
  raw=read(elfdir/elfs[name]['file'],MAX_CPIO);link,crc=debuglink(raw)
  matches=[(n,v) for n,v in elfs.items() if n.rsplit('/',1)[-1]==link]
  require(len(matches)==1,'collect_unique_debuglink');debugname,debug=matches[0]
  data=read(elfdir/debug['file'],MAX_CPIO)
  require(zlib.crc32(data)&0xffffffff==crc and debug['build_id']==elfs[name]['build_id'],'collect_debuglink_join')
  joins[role]={'runtime_member':name,'debug_member':debugname,'build_id':debug['build_id'],'debuglink_crc32':crc}
 return {'packages':packages,'ELFs':elfs,'joins':joins}

def main():
 require(os.geteuid()==0 and Path('/.dockerenv').is_file(),'collect_container_only')
 require(not (OUT/'custom-ELF-inventory.json').exists(),'collect_fresh')
 inventory={variant:collect(variant) for variant in ('baseline','candidate')}
 for name in ('original-packages.txt','original-macros.txt'):
  write(OUT/name,read(ROOT/name,16*1024*1024))
 value={'schema':'arctic-accelerator-ab-custom-build-inventory-v1','variants':inventory,
        'all_five_original_RPMs_per_variant':True,'all_package_ELFs_retained':True,
        'actual_runtime_mapping_admission':False,'performance_acceptance':False,'release_acceptance':False}
 write(OUT/'custom-ELF-inventory.json',(json.dumps(value,sort_keys=True,indent=2)+'\n').encode())

if __name__=='__main__':main()
