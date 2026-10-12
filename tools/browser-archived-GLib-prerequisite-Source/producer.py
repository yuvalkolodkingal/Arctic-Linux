"""Disabled matching-SRPM hosted A/B producer. Never import to execute a build."""
import argparse
from contextlib import contextmanager
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import signal
import shlex
import stat
import struct
import subprocess
import sys
import types

ROOT = Path('/build/arctic-accelerator-ab')
TOPDIR = ROOT/'rpmbuild'
SRPM_NAME = 'epiphany-50.6-1.fc44.src.rpm'
SRPM_SHA = 'f8ad7e58f40a0be422649a7e197854cee076b0168bcf09cea033747307d3d89a'
KEY_SHA = '93642aec521a1e5e96dd715f7ae0ec0850ebc9de09a94ce03cae5263f26cc18a'
CANDIDATE_BYTES = 2333
CANDIDATE_SHA = '7cee3ef2e4d3e998075bfb86e7febb4bf4e17ca6fbd097d9f55eb3b736694320'
WINDOW_BYTES = 200132
WINDOW_SHA = 'e89ce90f2df97f30e855e98723ee1040e1bbd71bbf05aada9a6898000bc1fa9a'
MEMBERS = {
 'epiphany.spec': (8598,'4e0f87ba947c53bc463d2f6ee38aee592c69b89f6a17f228a64f33c19bc18d51'),
 'epiphany-50.6.tar.xz': (4577640,'458222a8694cfc914e7a2d6de9879067001a8d65e00a907d96112059c67ad446'),
 'epiphany-default-bookmarks.patch': (1753,'62ae5bc0477cf5b0b3bc7908d1829d512cd85c098f4285f651eda7981499c1d7'),
}
EXPECTED_RUNTIME_DEVEL = {
 'glib2-devel':'glib2-devel-0:2.88.3-1.fc44.x86_64',
 'gtk4-devel':'gtk4-devel-0:4.22.5-2.fc44.x86_64',
 'libadwaita-devel':'libadwaita-devel-0:1.9.4-1.fc44.x86_64',
 'webkitgtk6.0-devel':'webkitgtk6.0-devel-0:2.54.1-1.fc44.x86_64',
 'libsecret-devel':'libsecret-devel-0:0.21.8.2-2.fc44.x86_64',
}
GTK_CONTROL_BYTES = 8219
GTK_CONTROL_SHA = '262768d49c70e0266f4981e0bda0dde214474fb1c43f94fc1f246a30df5d79ff'
MAX_SOURCE_CPIO = 64*1024*1024
MAX_COMMAND_OUTPUT = 16*1024*1024


def require(condition, reason):
 if not condition:raise RuntimeError(reason)


@contextmanager
def handoff():
 old=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM,signal.SIGALRM})
 try:yield
 finally:signal.pthread_sigmask(signal.SIG_SETMASK,old)


def identity(info):
 return (info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid,
         info.st_size,info.st_mtime_ns,info.st_ctime_ns)


def same_generation(fd, expected):
 try:return identity(os.fstat(fd))[:5]==expected[:5]
 except OSError:return False


def private_write(path, raw):
 """Exclusive owned output; timed work is not masked by ownership handoffs."""
 fd=None;expected=None
 try:
  with handoff():
   fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
   expected=identity(os.fstat(fd))
  view=memoryview(raw)
  while view:
   require(identity(os.fstat(fd))[:5]==expected[:5],'producer_output_generation')
   n=os.write(fd,view);require(n>0,'producer_output_short_write');view=view[n:]
  now=identity(os.fstat(fd))
  require(now[:5]==expected[:5] and now[5]==len(raw) and identity(path.lstat())==now
          and os.pread(fd,len(raw)+1,0)==raw,'producer_output_identity')
 finally:
  with handoff():
   # Size/timestamps change during our own write. Generation ownership is
   # dev/inode/mode/UID/GID, checked without closing a replacement descriptor.
   if fd is not None and expected is not None:
    try:now=identity(os.fstat(fd))
    except OSError:now=None
    if now is not None and now[:5]==expected[:5]:os.close(fd)


def read_bound(path, size, sha):
 fd=None;expected=None
 try:
  with handoff():
   fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
   expected=identity(os.fstat(fd))
  require(stat.S_ISREG(expected[2]) and expected[3]==0 and not expected[2]&0o022 and expected[5]==size,'producer_input_identity')
  raw=os.pread(fd,size+1,0)
  require(identity(os.fstat(fd))==expected and len(raw)==size and hashlib.sha256(raw).hexdigest()==sha,'producer_input_binding')
  require(identity(path.stat())==expected,'producer_input_path_changed')
  return raw
 finally:
  with handoff():
   if fd is not None and expected is not None and same_generation(fd,expected):os.close(fd)


def read_context(path):
 fd=None;expected=None
 try:
  with handoff():
   fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
   expected=identity(os.fstat(fd))
  require(stat.S_ISREG(expected[2]) and expected[3]==0 and not expected[2]&0o022
          and 0<expected[5]<=32768,'producer_context_file')
  raw=os.pread(fd,expected[5]+1,0)
  require(len(raw)==expected[5] and identity(os.fstat(fd))==expected
          and identity(path.lstat())==expected,'producer_context_changed')
  context=json.loads(raw);validate_context(context)
  return context
 finally:
  with handoff():
   if fd is not None and expected is not None and same_generation(fd,expected):os.close(fd)


def source_members(raw):
 require(len(raw)==4603759 and hashlib.sha256(raw).hexdigest()==SRPM_SHA,'producer_source_binding')
 require(raw[:4]==bytes.fromhex('edabeedb') and struct.unpack_from('>H',raw,6)[0]==1,'producer_source_lead')
 def header(offset):
  require(raw[offset:offset+4]==bytes.fromhex('8eade801'),'producer_header')
  count,size=struct.unpack_from('>II',raw,offset+8);require(count<10000 and size<len(raw),'producer_header')
  store=offset+16+count*16;end=store+size;require(end<=len(raw),'producer_header')
  result={}
  for i in range(count):
   tag,kind,start,number=struct.unpack_from('>IIII',raw,offset+16+i*16)
   pos=store+start;require(pos<=end and number<=100000 and tag not in result,'producer_header')
   if kind==3:
    require(pos+number*2<=end,'producer_header');value=list(struct.unpack_from('>'+'H'*number,raw,pos))
   elif kind==4:
    require(pos+number*4<=end,'producer_header');value=list(struct.unpack_from('>'+'I'*number,raw,pos))
   elif kind in (6,8,9):
    pieces=raw[pos:end].split(b'\0');require(len(pieces)>number,'producer_header');value=[x.decode('utf-8') for x in pieces[:number]]
   elif kind==7:
    require(pos+number<=end,'producer_header');value=raw[pos:pos+number]
   else:continue
   result[tag]=value
  return result,end
 _,end=header(96);meta,payload=header((end+7)&~7)
 require([meta[t][0] for t in (1000,1001,1002,1022)]==['epiphany','50.6','1.fc44','i686']
         and meta[1003]==[1] and meta[1125]==['gzip'] and meta[5011]==[8],'producer_source_header')
 with gzip.GzipFile(fileobj=io.BytesIO(raw[payload:])) as stream:
  data=stream.read(MAX_SOURCE_CPIO+1);require(len(data)<=MAX_SOURCE_CPIO and not stream.read(1),'producer_source_expansion')
 result={};position=0
 while position<len(data):
  require(data[position:position+6] in (b'070701',b'070702'),'producer_cpio')
  fields=[int(data[position+6+i*8:position+14+i*8],16) for i in range(13)]
  size,namesize=fields[6],fields[11];require(0<namesize<=128 and size<MAX_SOURCE_CPIO,'producer_cpio')
  start=position+110;require(data[start+namesize-1:start+namesize]==b'\0','producer_cpio')
  name=data[start:start+namesize-1].decode('ascii');begin=(start+namesize+3)&~3
  value=data[begin:begin+size];require(len(value)==size,'producer_cpio');position=(begin+size+3)&~3
  if name=='TRAILER!!!':break
  require(name in MEMBERS and name not in result and stat.S_ISREG(fields[1]),'producer_cpio_member')
  require(len(value)==MEMBERS[name][0] and hashlib.sha256(value).hexdigest()==MEMBERS[name][1],'producer_cpio_digest')
  result[name]=value
 else:raise RuntimeError('producer_cpio_trailer')
 require(set(result)==set(MEMBERS) and not any(data[position:]),'producer_cpio_group')
 names=[meta[1118][i]+base for i,base in zip(meta[1116],meta[1117])]
 require(len(names)==len(set(names))==len(meta[1035]) and set(names)==set(result),'producer_header_files')
 require(all(hashlib.sha256(result[n]).hexdigest()==d for n,d in zip(names,meta[1035])),'producer_header_digests')
 return result


def prepare(topdir, members, variant, candidate, window_raw):
 require(variant in ('baseline','candidate') and not topdir.exists(),'producer_variant')
 require(set(members)==set(MEMBERS),'producer_member_group')
 for name,value in members.items():
  require(len(value)==MEMBERS[name][0] and hashlib.sha256(value).hexdigest()==MEMBERS[name][1],'producer_member_binding')
 with handoff():
  topdir.mkdir(mode=0o700)
  for name in ('SOURCES','SPECS','BUILD','BUILDROOT','RPMS','SRPMS'): (topdir/name).mkdir(mode=0o700)
 for name,raw in members.items():
  target=topdir/('SPECS' if name=='epiphany.spec' else 'SOURCES')/name
  private_write(target,candidate.candidate_spec(raw) if variant=='candidate' and name=='epiphany.spec' else raw)
 if variant=='candidate':private_write(topdir/'SOURCES/arctic-accelerator-candidate.patch',candidate.window_patch(window_raw))


def package_census():
 raw=subprocess.check_output(['rpm','-qa','--qf','%{NAME}-%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}\n'],timeout=60)
 require(0<len(raw)<=MAX_COMMAND_OUTPUT,'producer_package_census')
 rows=raw.decode('ascii').splitlines()
 require(all(re.fullmatch(r'[A-Za-z0-9_.+\-]+-[0-9]+:[A-Za-z0-9._^+~\-]+\.[A-Za-z0-9_]+',x) or re.fullmatch(r'gpg-pubkey-0:(?:[0-9a-f]{8}|[0-9a-f]{40})-[0-9a-f]{1,8}\.\(none\)',x) for x in rows),'producer_package_shape')
 return ('\n'.join(sorted(rows))+'\n').encode()


def runtime_devel():
 for name,expected in EXPECTED_RUNTIME_DEVEL.items():
  value=subprocess.check_output(['rpm','-q','--qf','%{NAME}-%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}',name],timeout=30)
  require(value.decode('ascii')==expected,'producer_runtime_devel_mismatch')


def validate_context(context):
 require(type(context) is dict and set(context)=={'schema','ready','container','candidate','window_source','gtk_control','build_environment'},'producer_context_schema')
 require(context['schema']=='arctic-accelerator-ab-hosted-build-v1' and context['ready'] is True,'producer_disabled')
 require(re.fullmatch(r'registry\.fedoraproject\.org/fedora@sha256:[0-9a-f]{64}',context['container']) is not None,'producer_container')
 for name in ('candidate','window_source','gtk_control'):
  require(type(context[name]) is dict and set(context[name])=={'bytes','sha256'} and type(context[name]['bytes']) is int and context[name]['bytes']>0
          and re.fullmatch(r'[0-9a-f]{64}',context[name]['sha256']) is not None,'producer_source_context')
 require(context['candidate']=={'bytes':CANDIDATE_BYTES,'sha256':CANDIDATE_SHA}
         and context['window_source']=={'bytes':WINDOW_BYTES,'sha256':WINDOW_SHA}
         and context['gtk_control']=={'bytes':GTK_CONTROL_BYTES,'sha256':GTK_CONTROL_SHA},'producer_exact_source_context')
 require(context['build_environment']=='one_disposable_rootful_Fedora44_container_no_host_package_install','producer_environment')


def main():
 parser=argparse.ArgumentParser();parser.add_argument('--context',type=Path,required=True);args=parser.parse_args()
 # Full host workflow identity and original Git activation guard must authorize
 # this container before execution; this gate alone is not public admission.
 require(os.geteuid()==0 and Path('/.dockerenv').is_file() and Path('/etc/fedora-release').is_file(),'producer_container_only')
 require(args.context==Path('/inputs/producer-context.json'),'producer_context_path')
 context=read_context(args.context)
 require(not ROOT.exists() and not Path('/out/ab-build-receipt.json').exists(),'producer_fresh')
 srpm=read_bound(Path('/inputs')/SRPM_NAME,4603759,SRPM_SHA)
 key=read_bound(Path('/inputs/Fedora44-primary.gpg'),1672,KEY_SHA)
 candidate_raw=read_bound(Path('/inputs/candidate.py'),context['candidate']['bytes'],context['candidate']['sha256'])
 window=read_bound(Path('/inputs/ephy-window.c'),context['window_source']['bytes'],context['window_source']['sha256'])
 gtk_control=read_bound(Path('/inputs/gtk-control.c'),GTK_CONTROL_BYTES,GTK_CONTROL_SHA)
 candidate=types.ModuleType('reviewed_accelerator_candidate');exec(compile(candidate_raw,'/inputs/candidate.py','exec'),candidate.__dict__)
 require(candidate.WINDOW_SHA256=='e89ce90f2df97f30e855e98723ee1040e1bbd71bbf05aada9a6898000bc1fa9a','producer_candidate_contract')
 candidate.patched_window(window)
 with handoff():ROOT.mkdir(mode=0o700)
 source_file=ROOT/SRPM_NAME;key_file=ROOT/'Fedora44-primary.gpg'
 private_write(source_file,srpm);private_write(key_file,key)
 db=ROOT/'signature-db'
 with handoff():db.mkdir(mode=0o700)
 subprocess.run(['rpm','--dbpath',str(db),'--initdb'],check=True,timeout=30)
 subprocess.run(['rpm','--dbpath',str(db),'--import',str(key_file)],check=True,timeout=30)
 verification=subprocess.run(['rpmkeys','--dbpath',str(db),'--checksig','--verbose',str(source_file)],capture_output=True,timeout=60)
 require(verification.returncode==0 and b'key fingerprint: 36f612dcf27f7d1a48a835e4dbfcf71c6d9f90a6: OK' in verification.stdout
         and not any(x in verification.stdout+verification.stderr for x in (b'BAD',b'NOKEY',b'NOT OK')),'producer_source_signature')
 members=source_members(srpm)
 # Build dependency installation is inside this disposable container only.
 spec=ROOT/'original.spec';private_write(spec,members['epiphany.spec']);archived_glib_prerequisite(db)
 subprocess.run(['dnf5','install','--assumeyes',*EXPECTED_RUNTIME_DEVEL.values()],check=True,timeout=900)
 subprocess.run(['dnf5','builddep','--assumeyes',str(spec)],check=True,timeout=900)
 runtime_devel()
 sdk=ROOT/'gtk-control.c';private_write(sdk,gtk_control)
 flags=subprocess.check_output(['pkg-config','--cflags','--libs','gtk4'],timeout=30)
 require(0<len(flags)<=16384,'producer_SDK_flags')
 subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Werror',str(sdk),*shlex.split(flags.decode('ascii')),'-o',str(ROOT/'gtk-control')],check=True,timeout=120)
 subprocess.run(['dbus-run-session','--','xvfb-run','-a',str(ROOT/'gtk-control')],check=True,timeout=120)
 packages=package_census();private_write(ROOT/'original-packages.txt',packages)
 macros=subprocess.check_output(['rpm','--showrc'],timeout=60);require(0<len(macros)<=MAX_COMMAND_OUTPUT,'producer_macros')
 private_write(ROOT/'original-macros.txt',macros)
 receipts=[]
 for variant in ('baseline','candidate'):
  prepare(TOPDIR,members,variant,candidate,window)
  subprocess.run(['rpmbuild','-bb','--target','x86_64','--define','_topdir '+str(TOPDIR),str(TOPDIR/'SPECS/epiphany.spec')],check=True,timeout=2400)
  require(package_census()==packages and subprocess.check_output(['rpm','--showrc'],timeout=60)==macros,'producer_environment_changed')
  result=ROOT/variant
  with handoff():TOPDIR.rename(result)
  rpms=list((result/'RPMS/x86_64').glob('epiphany-runtime-50.6-1.fc44.x86_64.rpm'))
  require(len(rpms)==1 and rpms[0].is_file() and not rpms[0].is_symlink(),'producer_runtime_RPM')
  raw=rpms[0].read_bytes();require(64<len(raw)<=32*1024*1024,'producer_runtime_size')
  receipts.append(dict(variant=variant,RPM_bytes=len(raw),RPM_sha256=hashlib.sha256(raw).hexdigest(),
                      RPM_original_path=str(rpms[0]),full_checks=True))
 require(receipts[0]['RPM_sha256']!=receipts[1]['RPM_sha256'],'producer_identical_outputs')
 receipt=dict(schema=context['schema'],container=context['container'],source_sha256=SRPM_SHA,
     candidate_sha256=context['candidate']['sha256'],window_source_sha256=candidate.WINDOW_SHA256,
     source_signature_verified=True,key_sha256=KEY_SHA,hosted_real_GTK_semantic_control=True,gtk_control_sha256=GTK_CONTROL_SHA,dependency_census_sha256=hashlib.sha256(packages).hexdigest(),
     macro_census_sha256=hashlib.sha256(macros).hexdigest(),builds=receipts,
     runtime_overlay_ready=False,VM_runs=0,performance_acceptance=False,release_acceptance=False)
 private_write(Path('/out/ab-build-receipt.json'),(json.dumps(receipt,sort_keys=True,indent=2)+'\n').encode())
 # Original build trees/RPMs/logs remain private host-owned evidence. A strict
 # peer-reviewed host extractor/uploader is required before any public upload.



# Diagnostic observation only. The original main and ownership/deadline/build
# guards above remain unchanged except the exact trusted RPM6 fingerprint text.
ARCHIVED_GLIB_INPUTS = (('glib2', 'glib2-0:2.88.3-1.fc44.x86_64', 'glib2-2.88.3-1.fc44.x86_64.rpm', 3291840, '03e0c616f95cbcee3a076d4f235f0ce7ec4707926257e4ea73f5fa4f8e2bb888', '860f20c8badc0444c858e18637c852023a8f2791b2171285b9af06da635c2ce4', 'https://kojipkgs.fedoraproject.org/packages/glib2/2.88.3/1.fc44/data/signed/6d9f90a6/x86_64/glib2-2.88.3-1.fc44.x86_64.rpm'), ('glib2-devel', 'glib2-devel-0:2.88.3-1.fc44.x86_64', 'glib2-devel-2.88.3-1.fc44.x86_64.rpm', 1576151, '061b42408531714da5154f71db863ea57be82d98671f94d7fbfd6d0bdf2d9695', 'd82035b397443bf7db51f67bc858d6bf65ca3347072813565f534fbdf38ca0d1', 'https://kojipkgs.fedoraproject.org/packages/glib2/2.88.3/1.fc44/data/signed/6d9f90a6/x86_64/glib2-devel-2.88.3-1.fc44.x86_64.rpm'))

def archived_glib_prerequisite(db):
 # Only the original fresh rootful Fedora44 experiment container may install.
 require(os.geteuid()==0 and Path('/.dockerenv').is_file() and Path('/etc/fedora-release').is_file(), 'producer_container_only')
 require(type(db)is type(ROOT) and db==ROOT/'signature-db', 'producer_archived_scope')
 paths=[];originals=[]
 for name,nevra,filename,size,sha,header_sha,official_uri in ARCHIVED_GLIB_INPUTS:
  path=Path('/inputs')/filename
  raw=read_bound(path,size,sha)
  verification=subprocess.run(['rpmkeys','--dbpath',str(db),'--checksig','--verbose',str(path)],capture_output=True,timeout=60)
  require(verification.returncode==0 and b'key fingerprint: 36f612dcf27f7d1a48a835e4dbfcf71c6d9f90a6: OK' in verification.stdout
          and not any(x in verification.stdout+verification.stderr for x in (b'BAD',b'NOKEY',b'NOT OK')), 'producer_archived_signature')
  query=['rpm','--dbpath',str(db),'-qp','--qf','%{NAME}-%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}\n%{SHA256HEADER}\n',str(path)]
  require(subprocess.check_output(query,timeout=30)==(nevra+'\n'+header_sha+'\n').encode('ascii'), 'producer_archived_header')
  require(read_bound(path,size,sha)==raw, 'producer_archived_input_changed')
  paths.append(str(path));originals.append((path,size,sha,raw,nevra,header_sha,name))
 # Exact local RPM targets replace newer non-installonly versions in one goal.
 # No host/system install, package erasure option, version unpin or signature
 # configuration override is authorized by this Source-only preparation.
 subprocess.run(['dnf5','install','--assumeyes',*paths],check=True,timeout=900)
 for path,size,sha,raw,nevra,header_sha,name in originals:
  require(read_bound(path,size,sha)==raw, 'producer_archived_input_changed')
  installed=subprocess.check_output(['rpm','-q','--qf','%{NAME}-%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}\n%{SHA256HEADER}\n',name],timeout=30)
  require(installed==(nevra+'\n'+header_sha+'\n').encode('ascii'), 'producer_archived_installed_header')


FAILURE_PREFIX = b'ARCTIC-EPIPHANY-PRODUCER-FAILURE '
FAILURE_BODY_SHA256 = '3e35e6eb378f726743c9b3dfdd6a856237619deebd7b533ec9e501fbd914438b'
FAILURE_PHASES = frozenset(('archived_sdk_inputs', 'archived_sdk_signature', 'archived_sdk_header', 'archived_sdk_install', 'RPM_build', 'build_outputs', 'build_prepare', 'candidate_source', 'context', 'entry', 'environment_inventory', 'inputs', 'owned_output', 'sdk_build_dependencies', 'sdk_compile', 'sdk_control', 'sdk_dependencies', 'sdk_inventory', 'signature_database', 'signature_key_import', 'source_package', 'source_signature', 'unknown'))
FAILURE_REASONS = frozenset(('producer_archived_scope', 'producer_archived_signature', 'producer_archived_header', 'producer_archived_input_changed', 'producer_archived_installed_header', 'producer_SDK_flags', 'producer_candidate_contract', 'producer_container', 'producer_container_only', 'producer_context_changed', 'producer_context_file', 'producer_context_path', 'producer_context_schema', 'producer_cpio', 'producer_cpio_digest', 'producer_cpio_group', 'producer_cpio_member', 'producer_disabled', 'producer_environment', 'producer_environment_changed', 'producer_exact_source_context', 'producer_fresh', 'producer_header', 'producer_header_digests', 'producer_header_files', 'producer_identical_outputs', 'producer_input_binding', 'producer_input_identity', 'producer_input_path_changed', 'producer_macros', 'producer_member_binding', 'producer_member_group', 'producer_output_generation', 'producer_output_identity', 'producer_output_short_write', 'producer_package_census', 'producer_package_shape', 'producer_runtime_RPM', 'producer_runtime_devel_mismatch', 'producer_runtime_size', 'producer_source_binding', 'producer_source_context', 'producer_source_expansion', 'producer_source_header', 'producer_source_lead', 'producer_source_signature', 'producer_variant'))
FAILURE_CATEGORIES = frozenset(('unknown','command_failed','command_timeout','interrupted','os_error'))
FAILURE_REQUIRE_OWNER = (require.__code__, require.__globals__)
FAILURE_MODULE_CODE = sys._getframe().f_code
FAILURE_BODY_CODES = (archived_glib_prerequisite.__code__,require.__code__,handoff.__code__,identity.__code__,same_generation.__code__,private_write.__code__,read_bound.__code__,read_context.__code__,source_members.__code__,prepare.__code__,package_census.__code__,runtime_devel.__code__,validate_context.__code__,main.__code__)
FAILURE_REQUIRE_SITES = (
 (archived_glib_prerequisite.__code__,archived_glib_prerequisite.__globals__,{283: ('archived_sdk_inputs', 'producer_container_only'), 284: ('archived_sdk_inputs', 'producer_archived_scope'), 290: ('archived_sdk_signature', 'producer_archived_signature'), 291: ('archived_sdk_signature', 'producer_archived_signature'), 293: ('archived_sdk_header', 'producer_archived_header'), 294: ('archived_sdk_inputs', 'producer_archived_input_changed'), 301: ('archived_sdk_inputs', 'producer_archived_input_changed'), 303: ('archived_sdk_header', 'producer_archived_installed_header')}),
 (private_write.__code__,private_write.__globals__,{79: ('owned_output', 'producer_output_identity'), 80: ('owned_output', 'producer_output_identity'), 76: ('owned_output', 'producer_output_generation'), 77: ('owned_output', 'producer_output_short_write')}),
 (read_bound.__code__,read_bound.__globals__,{97: ('inputs', 'producer_input_identity'), 99: ('inputs', 'producer_input_binding'), 100: ('inputs', 'producer_input_path_changed')}),
 (read_context.__code__,read_context.__globals__,{113: ('context', 'producer_context_file'), 114: ('context', 'producer_context_file'), 116: ('context', 'producer_context_changed'), 117: ('context', 'producer_context_changed')}),
 (source_members.__code__,source_members.__globals__,{126: ('source_package', 'producer_source_binding'), 127: ('source_package', 'producer_source_lead'), 148: ('source_package', 'producer_source_header'), 149: ('source_package', 'producer_source_header'), 165: ('source_package', 'producer_cpio_group'), 167: ('source_package', 'producer_header_files'), 168: ('source_package', 'producer_header_digests'), 129: ('source_package', 'producer_header'), 130: ('source_package', 'producer_header'), 131: ('source_package', 'producer_header'), 151: ('source_package', 'producer_source_expansion'), 154: ('source_package', 'producer_cpio'), 156: ('source_package', 'producer_cpio'), 157: ('source_package', 'producer_cpio'), 159: ('source_package', 'producer_cpio'), 161: ('source_package', 'producer_cpio_member'), 162: ('source_package', 'producer_cpio_digest'), 135: ('source_package', 'producer_header'), 137: ('source_package', 'producer_header'), 139: ('source_package', 'producer_header'), 141: ('source_package', 'producer_header'), 143: ('source_package', 'producer_header')}),
 (prepare.__code__,prepare.__globals__,{173: ('build_prepare', 'producer_variant'), 174: ('build_prepare', 'producer_member_group'), 176: ('build_prepare', 'producer_member_binding')}),
 (package_census.__code__,package_census.__globals__,{188: ('environment_inventory', 'producer_package_census'), 190: ('environment_inventory', 'producer_package_shape')}),
 (runtime_devel.__code__,runtime_devel.__globals__,{197: ('sdk_inventory', 'producer_runtime_devel_mismatch')}),
 (validate_context.__code__,validate_context.__globals__,{201: ('context', 'producer_context_schema'), 202: ('context', 'producer_disabled'), 203: ('context', 'producer_container'), 207: ('context', 'producer_exact_source_context'), 208: ('context', 'producer_exact_source_context'), 209: ('context', 'producer_exact_source_context'), 210: ('context', 'producer_environment'), 205: ('context', 'producer_source_context'), 206: ('context', 'producer_source_context')}),
 (main.__code__,main.__globals__,{217: ('entry', 'producer_container_only'), 218: ('entry', 'producer_context_path'), 220: ('entry', 'producer_fresh'), 227: ('candidate_source', 'producer_candidate_contract'), 237: ('source_signature', 'producer_source_signature'), 238: ('source_signature', 'producer_source_signature'), 247: ('sdk_compile', 'producer_SDK_flags'), 251: ('environment_inventory', 'producer_macros'), 265: ('build_outputs', 'producer_identical_outputs'), 257: ('build_outputs', 'producer_environment_changed'), 261: ('build_outputs', 'producer_runtime_RPM'), 262: ('build_outputs', 'producer_runtime_size')}),
)
FAILURE_COMMAND_SITES = (
 (archived_glib_prerequisite.__code__,archived_glib_prerequisite.__globals__,{299: 'archived_sdk_install', 289: 'archived_sdk_signature', 302: 'archived_sdk_header', 293: 'archived_sdk_header'}),
 (package_census.__code__,package_census.__globals__,{187: 'environment_inventory'}),
 (runtime_devel.__code__,runtime_devel.__globals__,{196: 'environment_inventory'}),
 (main.__code__,main.__globals__,{234: 'signature_database', 235: 'signature_key_import', 236: 'source_signature', 242: 'sdk_dependencies', 243: 'sdk_build_dependencies', 246: 'sdk_compile', 248: 'sdk_compile', 249: 'sdk_control', 251: 'environment_inventory', 256: 'RPM_build', 257: 'environment_inventory'}),
)

def finite_producer_failure(error):
 trace=BaseException.__dict__['__traceback__'].__get__(error,type(error));frames=[]
 for _ in range(64):
  if trace is None:break
  frames.append((trace.tb_frame.f_code,trace.tb_frame.f_globals,trace.tb_lineno));trace=trace.tb_next
 if trace is not None:return 'unknown','unknown'
 for code,g,line in frames:
  if g is globals() and code is not FAILURE_MODULE_CODE and not any(code is owned for owned in FAILURE_BODY_CODES):return 'unknown','unknown'
  if g is not globals() and any(code is owned for owned in FAILURE_BODY_CODES):return 'unknown','unknown'
 if type(error)is RuntimeError:
  for i,(code,g,line) in enumerate(frames):
   if code is FAILURE_REQUIRE_OWNER[0] and g is FAILURE_REQUIRE_OWNER[1] and i:
    caller,cg,cl=frames[i-1]
    for owner,namespace,sites in FAILURE_REQUIRE_SITES:
     if caller is owner and cg is namespace and cl in sites:return sites[cl]
 category='unknown'
 if type(error)is subprocess.CalledProcessError:category='command_failed'
 elif type(error)is subprocess.TimeoutExpired:category='command_timeout'
 elif type(error)in(KeyboardInterrupt,InterruptedError,SystemExit):category='interrupted'
 elif type(error)in(OSError,PermissionError,FileNotFoundError,FileExistsError):category='os_error'
 if category!='unknown':
  for code,g,line in reversed(frames):
   for owner,namespace,sites in FAILURE_COMMAND_SITES:
    if code is owner and g is namespace and line in sites:return sites[line],category
 return 'unknown','unknown'

def validate_failure_record(record):
 require(type(record)is dict and set(record)=={'schema','status','source_body_sha256','phase','reason'},'producer_finite_schema')
 require(record['schema']=='arctic-epiphany-producer-finite-failure-v1' and record['status']=='failed_unqualified' and record['source_body_sha256']==FAILURE_BODY_SHA256,'producer_finite_context')
 require(type(record['phase'])is str and record['phase']in FAILURE_PHASES and type(record['reason'])is str and record['reason']in FAILURE_REASONS|FAILURE_CATEGORIES,'producer_finite_enums')
 return record

def failure_record(error):
 phase,reason=finite_producer_failure(error)
 return validate_failure_record({'schema':'arctic-epiphany-producer-finite-failure-v1','status':'failed_unqualified','source_body_sha256':FAILURE_BODY_SHA256,'phase':phase,'reason':reason})

def parse_failure_record(raw):
 require(type(raw)is bytes and len(raw)<=64*1024*1024,'producer_finite_log_bound')
 reserved_prefix=FAILURE_PREFIX.rstrip(b' ');reserved=raw.count(reserved_prefix);records=[]
 for line in raw.splitlines():
  if reserved_prefix in line:
   require(line.startswith(FAILURE_PREFIX) and line.count(reserved_prefix)==1 and len(line)<=2048,'producer_finite_marker')
   payload=line[len(FAILURE_PREFIX):];require(payload and all(32<=v<127 for v in payload),'producer_finite_ascii')
   def pairs(items):
    result={}
    for key,value in items:require(key not in result,'producer_finite_duplicate');result[key]=value
    return result
   record=json.loads(payload,object_pairs_hook=pairs);validate_failure_record(record)
   require(json.dumps(record,sort_keys=True,separators=(',',':')).encode()==payload,'producer_finite_encoding')
   records.append(record)
 require(reserved==len(records)==1,'producer_finite_single')
 return records[0]

if __name__=='__main__':
 try:main()
 except BaseException as error:
  try:
   record=failure_record(error)
   print((FAILURE_PREFIX+json.dumps(record,sort_keys=True,separators=(',',':')).encode()).decode('ascii'),flush=True)
  except BaseException:pass
  raise
