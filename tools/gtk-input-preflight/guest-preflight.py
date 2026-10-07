#!/usr/bin/env python3
"""Reviewed-core adapter: finite GTK input preflight, separate bounded bulk export."""
import base64,hashlib,importlib.util,json,os,pwd,re,signal,sys,tempfile,traceback,zlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
def require(value,message):
 if not value:raise RuntimeError(message)
def load(name,path,digest):
 require(path.is_file() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest()==digest,'runtime dependency differs: '+path.name)
 spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
def export(root,writer):
 entries=[];encoded=[];total=0
 for path in sorted(root.rglob('*')):
  require(not path.is_symlink(),'preflight evidence symlink refused')
  if not path.is_file():continue
  relative=path.relative_to(root).as_posix()
  xkb=bool(re.fullmatch(r'sentinel-(?:warm|cold)/producer-turn-[012]/uploaded-map\.xkb',relative))
  require((path.suffix.lower() in ('.json','.png','.log','.txt','.tsv') or xkb)
          and len(entries)<128 and path.stat().st_size<=4*1024*1024,'unchanged evidence type/count/file bound failed')
  data=path.read_bytes();total+=len(data);require(total<=16*1024*1024,'unchanged total evidence bound exceeded')
  compressed=zlib.compress(data,9);chunks=[compressed[i:i+24576] for i in range(0,len(compressed),24576)]
  entry=dict(path=relative,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),compressed_bytes=len(compressed),chunks=len(chunks),encoding='zlib+base64')
  entries.append(entry);encoded.append((entry,chunks))
 for entry,chunks in encoded:
  for index,chunk in enumerate(chunks):writer.write('ARCTIC-NATIVE-EVIDENCE-CHUNK ',dict(path=entry['path'],index=index,data=base64.b64encode(chunk).decode()))
 writer.write('ARCTIC-NATIVE-EVIDENCE-MANIFEST ',dict(schema='arctic-native-evidence-v1',stage='live',files=entries,bytes=total,evidence_root=str(root)))
def main():
 writer=None;root=None;error=None;result=None;export_complete=False
 try:
  require(Path(__file__).resolve()==Path('/run/t/guest-check.py') and len(sys.argv)==1,'exact guarded read-only guest entry/no arguments required')
  pins=json.loads((HERE/'runtime-pins.json').read_text())
  require(set(pins)=={'guest-check.py','preflight-core.py','preflight-proof.py','native_smoke.py','native-launcher.py','gtk-entry-control.py','security-collector.py','bulk-channel.py','arctic-wtype-sentinel','build-payload-pins.json','candidate-input-libraries.json','bootstrap-diagnostic.sh','run.sh','input-collector.py','wire-input.py','candidate-data-mappings.json','data-mapping-proof.py'},'runtime file set differs')
  for name,digest in pins.items():require(hashlib.sha256((HERE/name).read_bytes()).hexdigest()==digest,'runtime bytes differ: '+name)
  N=load('finite_native',HERE/'native_smoke.py',pins['native_smoke.py']);N.guest_guard('live',True)
  B=load('finite_bulk',HERE/'bulk-channel.py',pins['bulk-channel.py']);writer=B.Writer()
  begin=dict(schema='arctic-gtk-input-preflight-begin-v1',checker_sha256=N.digest(Path(__file__)),native_source_sha256=pins['native_smoke.py'],release_acceptance=False,native_qualification=False)
  # Preserve the frozen bulk protocol prefixes; the payload schema declares finite GTK scope.
  writer.write('ARCTIC-PCMANFM-DIAG-BEGIN ',begin)
  print('ARCTIC-PCMANFM-DIAG-BEGIN '+json.dumps(begin,sort_keys=True),flush=True)
  L=load('finite_launcher',HERE/'native-launcher.py',pins['native-launcher.py']);launcher=L.verify_barrier('live',pins['native-launcher.py'])
  C=load('finite_core',HERE/'preflight-core.py',pins['preflight-core.py'])
  P=load('finite_proof',HERE/'preflight-proof.py',pins['preflight-proof.py'])
  S=load('finite_security',HERE/'security-collector.py',pins['security-collector.py'])
  prefix=N.discover_desktop();uid=pwd.getpwnam(prefix[2]).pw_uid;require(launcher['foot']['uid']==uid,'desktop/launcher UID differs')
  root=Path(tempfile.mkdtemp(prefix='arctic-gtk-input-preflight-',dir='/tmp'))
  (root/'provenance.json').write_text(json.dumps(dict(**begin,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),cmdline=Path('/proc/cmdline').read_text().strip(),desktop_uid=uid,desktop_user=prefix[2],desktop_home=pwd.getpwnam(prefix[2]).pw_dir,desktop_prefix=prefix,launcher=launcher,runtime_pins=pins,bulk_port=writer.identity),indent=2)+'\n')
  metadata=json.loads((HERE/'build-payload-pins.json').read_text())
  original=C.library_proof(['/usr/bin/wtype'],N)
  (root/'original-wtype-identity.json').write_text(json.dumps(original,indent=2)+'\n')
  signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('unchanged600-second guest deadline')))
  signal.setitimer(signal.ITIMER_REAL,600)
  result=C.run(prefix,root,N,P,S,metadata)
  require(C.library_proof(['/usr/bin/wtype'],N)==original,'original producer changed')
  (root/'report.json').write_text(json.dumps(result,indent=2)+'\n')
  writer.start_export();writer.write('ARCTIC-PCMANFM-DIAG-REPORT ',result)
  require(result['errors']==[],'finite preflight collection/security/cleanup failed')
 except BaseException as exc:error=type(exc).__name__+': '+str(exc);traceback.print_exc()
 finally:
  signal.setitimer(signal.ITIMER_REAL,0)
  try:
   if writer is not None and writer.export_deadline is None:writer.start_export()
   if root is not None:
    if result is None:
     (root/'primary-error.json').write_text(json.dumps(dict(error=error,release_acceptance=False))+'\n')
    export(root,writer);export_complete=True
  except BaseException as exc:error=(error+'; ' if error else '')+'export: '+str(exc);traceback.print_exc()
  end=dict(status='diagnostic-collected' if error is None and export_complete else 'failed',error=error,evidence_export_complete=export_complete,release_acceptance=False,native_qualification=False)
  try:
   if writer is not None:writer.write('ARCTIC-PCMANFM-DIAG-END ',end)
   print('ARCTIC-PCMANFM-DIAG-END '+json.dumps(end,sort_keys=True),flush=True)
  finally:
   if writer is not None:writer.close()
 return 0 if error is None and export_complete else 1
if __name__=='__main__':raise SystemExit(main())
