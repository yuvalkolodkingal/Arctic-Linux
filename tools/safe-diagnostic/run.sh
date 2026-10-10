#!/usr/bin/env bash
# Test-only builder and one isolated Safe diagnostic. No product/image writes.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/../lib/container.sh"
[[ $# == 3 ]] || arctic_die 'usage: run.sh EXECUTION INPUTS OUT'
execution=$(realpath "$1")
inputs=$(realpath "$2")
[[ ! -e "$3" ]] || arctic_die 'diagnostic output must be unused'
mkdir -p "$3/data"
out=$(realpath "$3")
for path in "$execution" "$inputs" "$out"; do
  [[ "$path" =~ ^/[A-Za-z0-9_./-]+$ ]] || arctic_die 'simple fixture paths required'
done
[[ -c /dev/kvm ]] || arctic_die 'real KVM required; no TCG substitution'
engine=$(arctic_engine)
arctic_ensure_engine
arctic_container_args
image=$(arctic_resolve_image "$engine" "$ARCTIC_FEDORA_IMAGE")
invocation=$(python3 -c 'import uuid; print(uuid.uuid4().hex)')
prep="arctic-safe-prep-$invocation"
vm="arctic-safe-vm-$invocation"
for name in "$prep" "$vm"; do
  if "$engine" container inspect "$name" >/dev/null 2>&1; then arctic_die 'fixture container name already exists'; fi
done
cleanup() {
  local primary=$? secondary=0
  set +e
  python3 - "$engine" "$out" "$invocation" <<'PY'
import json,re,subprocess,sys
from pathlib import Path
engine,out,invocation=sys.argv[1:]
for phase in ('prep','vm'):
    receipt=Path(out)/(phase+'-container-id')
    if receipt.is_file() and not receipt.is_symlink():
        identity=receipt.read_text().strip()
        if re.fullmatch('[0-9a-f]{64}',identity):
            rows=json.loads(subprocess.check_output([engine,'container','inspect',identity],timeout=20))
            assert len(rows)==1 and rows[0]['Id']==identity
            assert rows[0]['Name']=='/arctic-safe-'+phase+'-'+invocation
            assert rows[0]['Config']['Labels'].get('org.arctic.safe.invocation')==invocation
            subprocess.run([engine,'rm','-f',identity],check=True,timeout=20,stdout=subprocess.DEVNULL)
PY
  secondary=$?
  [[ $primary != 0 ]] && exit "$primary"
  exit "$secondary"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
python3 -B "$HERE/common.py" docker-prep "$out" -- \
 "$engine" run --name "$prep" --cidfile "$out/prep-container-id" --label "org.arctic.safe.invocation=$invocation" \
  "${ARCTIC_CONTAINER_ARGS[@]}" -v "$execution:/execution:ro" -v "$out:/out" "$image" bash -c "$ARCTIC_CONTAINER_PROLOGUE"'
umask 022
dnf -y --setopt=timeout=30 --setopt=retries=2 --setopt=install_weak_deps=False install \
 qemu-system-x86-core qemu-img edk2-ovmf seabios-bin python3-pillow xorriso gcc wayland-devel \
 qemu-device-display-virtio-vga qemu-device-display-virtio-gpu qemu-device-display-virtio-gpu-pci
mkdir /out/generated
wayland-scanner client-header /execution/shell/dev/wlr-screencopy-unstable-v1.xml /out/generated/screencopy-client.h
wayland-scanner private-code /execution/shell/dev/wlr-screencopy-unstable-v1.xml /out/generated/screencopy-client.c
gcc -std=c11 -Wall -Wextra -Wno-unused-parameter -Werror /execution/tools/safe-diagnostic/screencopy.c \
 /out/generated/screencopy-client.c -I /out/generated -lwayland-client -o /out/data/raw-screencopy
chmod 0755 /out/data/raw-screencopy
python3 - <<"PY"
import hashlib,json,os,stat,subprocess
from pathlib import Path
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
binary=Path("/out/data/raw-screencopy");info=binary.lstat()
assert stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode)==0o755 and info.st_uid==os.geteuid()
binary_record=dict(bytes=info.st_size,uid=info.st_uid,gid=info.st_gid,mode=stat.S_IMODE(info.st_mode),sha256=sha(binary))
packages=subprocess.check_output(["rpm","-q","gcc","wayland-devel","libwayland-client","qemu-system-x86-core","edk2-ovmf","xorriso","python3-pillow"],text=True).splitlines()
value=dict(schema="arctic-safe-tools-v1",release_acceptance=False,
 sources={p:sha("/execution/"+p) for p in ("tools/safe-diagnostic/screencopy.c","shell/dev/wlr-screencopy-unstable-v1.xml")},
 binary_sha256=sha("/out/data/raw-screencopy"),binary=binary_record,packages=packages,
 compiler=subprocess.check_output(["gcc","--version"],text=True).splitlines()[0],
 dynamic_dependencies=subprocess.check_output(["ldd","/out/data/raw-screencopy"],text=True).splitlines())
report=Path("/out/build-provenance.json");report.write_text(json.dumps(value,sort_keys=True)+"\n");report.chmod(0o644)
PY
'
prepared=$("$engine" commit "$prep")
[[ "$prepared" =~ ^(sha256:)?[0-9a-f]{64}$ ]] || arctic_die 'prepared image ID differs'
python3 - "$execution" "$inputs" "$out" "$prepared" <<'PY'
import importlib.util,json,os,secrets,shutil,stat,subprocess,sys
from pathlib import Path
execution,inputs,out=map(Path,sys.argv[1:4]);prepared=sys.argv[4]
spec=importlib.util.spec_from_file_location('safe_common',execution/'tools/safe-diagnostic/common.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
manifest=c.validate_manifest(c.strict((execution/'tools/safe-diagnostic/execution-manifest.json').read_bytes()))
assert not subprocess.check_output(['git','-C',str(execution),'status','--porcelain'])
iso=inputs/'iso'/c.IMAGE['name'];c.regular(iso,2_000_000_000)
assert iso.stat().st_size==c.IMAGE['bytes'] and c.sha(iso)==c.IMAGE['sha256']
for name,path in {'common.py':execution/'tools/safe-diagnostic/common.py',
 'guest.py':execution/'tools/safe-diagnostic/guest.py',
 'taskbar-runtime.py':execution/'tools/native-functional/taskbar-runtime.py',
 'native_smoke.py':execution/'tools/native-functional/native_smoke.py',
 'screen-evidence.py':execution/'tools/native-functional/screen-evidence.py'}.items():
    shutil.copyfile(path,out/'data'/name)
build=c.strict(c.regular(out/'build-provenance.json',1024**2).read_bytes())
assert build['schema']=='arctic-safe-tools-v1' and build['release_acceptance'] is False
record=build['binary'];assert set(record)=={'bytes','uid','gid','mode','sha256'}
assert all(type(record[k]) is int and record[k]>=0 for k in ('bytes','uid','gid','mode'))
binary=c.regular(out/'data/raw-screencopy',owner=record['uid']);info=binary.stat()
assert (info.st_size,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(record['bytes'],record['uid'],record['gid'],0o755)
assert record['mode']==0o755 and os.access(binary,os.R_OK) and binary.read_bytes()[:4]==b'\x7fELF'
assert c.sha(binary)==record['sha256']==build['binary_sha256']
ctx=c.context(dict(schema='arctic-safe-guest-context-v1',image=c.IMAGE,
 execution_sha=subprocess.check_output(['git','-C',str(execution),'rev-parse','HEAD'],text=True).strip(),
 binding_id=secrets.token_hex(16),bundle={p.name:c.sha(p) for p in (out/'data').iterdir()}))
(out/'data/context.json').write_text(json.dumps(ctx,sort_keys=True)+'\n')
(out/'fixture-provenance.json').write_text(json.dumps(dict(schema='arctic-safe-fixture-v1',image=c.IMAGE,
 execution_sha=ctx['execution_sha'],prepared_image_id=prepared,binary=record,release_acceptance=False),sort_keys=True)+'\n')
PY
cat > "$out/system-area.sh" <<'BOOTSTRAP'
#!/bin/sh
set -eu
[ "$(id -u)" = 0 ]
device=$(blkid -t LABEL=ARCTICSAFE -o device)
[ -b "$device" ]
label=$(blkid -s LABEL -o value "$device")
[ "$label" = ARCTICSAFE ]
mkdir -p /run/t
mountpoint -q /run/t && exit 1
mount -t iso9660 -o ro,nodev,nosuid "$device" /run/t
python3 -I - "$1" <<'VERIFY'
import hashlib,json,os,stat,sys
from pathlib import Path
base=Path('/run/t');ctx=json.loads((base/'context.json').read_text())
assert ctx['binding_id']==sys.argv[1]
assert set(ctx['bundle'])=={'common.py','guest.py','taskbar-runtime.py','native_smoke.py','screen-evidence.py','raw-screencopy'}
for name,sha in ctx['bundle'].items():
    p=base/name;s=p.lstat()
    assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022
    assert hashlib.sha256(p.read_bytes()).hexdigest()==sha
VERIFY
session=
for candidate in $(loginctl list-sessions --no-legend | awk '$3=="liveuser" {print $1}'); do
  [ "$(loginctl show-session "$candidate" -p Type --value)" = wayland ] || continue
  [ -z "$session" ] || exit 1
  session=$candidate
done
[ -n "$session" ]
vt=$(loginctl show-session "$session" -p VTNr --value)
case "$vt" in ''|0|*[!0-9]*) exit 1;; esac
chvt "$vt"
exec python3 -I /run/t/guest.py --disposable-guest </dev/null >/dev/ttyS0 2>&1
BOOTSTRAP
set +e
python3 -B "$HERE/common.py" docker-vm "$out" -- \
 "$engine" run --name "$vm" --cidfile "$out/vm-container-id" --label "org.arctic.safe.invocation=$invocation" \
  --network none --device /dev/kvm -e OUT=/out -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$execution:/execution:ro" -v "$inputs/iso/Arctic-Linux-1.2-candidate-38032256030-1-x86_64.iso:/iso:ro" \
  -v "$out:/out" "$prepared" bash -c '
set -euo pipefail
umask 022
python3 -B /execution/tools/safe-diagnostic/common.py bootstrap-cd /out -- \
 xorriso -as mkisofs -quiet -V ARCTICSAFE -J -R -uid 0 -gid 0 -G /out/system-area.sh -o /out/data.iso /out/data
python3 -B /execution/tools/safe-diagnostic/common.py python-driver /out -- \
 timeout --signal=TERM --kill-after=10s 15m python3 -B /execution/tools/safe-diagnostic/host.py --out /out
'
status=$?
# Secondary export/screening failures preserve an existing primary failure.
# A zero primary still fails if either strict reporting stage rejects bytes.
python3 - "$out" "$execution" <<'PY'
import importlib.util,shutil,stat,sys
from pathlib import Path
out=Path(sys.argv[1]);execution=Path(sys.argv[2]);evidence=out/'evidence';evidence.mkdir()
spec=importlib.util.spec_from_file_location('safe_status_export',execution/'tools/safe-diagnostic/common.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
# Begin reviewed guest fixed-status projection; no raw errors or unvalidated JSON.
guest_context=None
guest_status_path=out/'guest-entry-status.json'
c.require(not guest_status_path.exists() and not guest_status_path.is_symlink(), 'Guest fixed export must be new')
if (out/'serial.log').exists():
    serial=c.regular(out/'serial.log').read_bytes()
    if c.GUEST_STATUS_PREFIX.encode() in serial:
        guest_context=c.context(c.strict(c.regular(out/'data/context.json').read_bytes()))
        guest_status=c.project_guest_status(serial,guest_context)
        if guest_status is not None:
            c.exclusive_json(guest_status_path,guest_status)
# End reviewed guest fixed-status projection.
# Three separately closed compartments retain the original per-export limits.
context_names={'build-provenance.json','fixture-provenance.json','host-report.json',
 'original-guest-observation.json','serial.log','qemu.log','host-entry-status.json',
 'guest-entry-status.json','boot-menu.png','safe-menu-selected.png','console-login.png',
 *('baseline-%03ds.png'%v for v in (35,80,125)),*('stage-'+v+'.json' for v in c.STAGES)}
arm_names={*c.GUEST_FILES,'arm-host-report.json',
 *('arm-baseline-%03ds.png'%v for v in (35,80,125)),
 *(v+'-qmp-'+side+'.png' for v in c.PAIRS for side in ('before','after')),
 *(v+'-wayland-derived.png' for v in c.PAIRS)}
context_out=evidence/'context';context_out.mkdir()
context_path=out/'data/context.json'
ctx=c.context(c.strict(c.regular(context_path).read_bytes())) if context_path.exists() else None
def copy_closed(source,target,allowed):
    total=0;count=0
    for path in source.iterdir():
        if path.name not in allowed:continue
        raw=c.read_regular(path)
        if path.name=='guest-entry-status.json':
            c.require(ctx is not None,'Guest fixed status requires original validated context')
            c.validate_guest_status(c.strict(raw),ctx)
        if path.name=='host-entry-status.json' or path.name.startswith('stage-'):
            value=c.validate_fixed_status(c.strict(raw))
            assert value['stage'] in c.HOST_PHASES if path.name=='host-entry-status.json' else path.name=='stage-'+value['stage']+'.json' and value['stage'] in c.STAGES
        if path.suffix in ('.json','.log'):
            # Preserve the original whole-text privacy oracle, including serial.
            spec=importlib.util.spec_from_file_location('safe_export_privacy',execution/'tools/native-functional/screen-evidence.py')
            screen=importlib.util.module_from_spec(spec);spec.loader.exec_module(screen)
            screen.external_text(raw)
        total+=len(raw);count+=1
        assert total<=128*1024**2 and count<=40
        with (target/path.name).open('xb') as destination:destination.write(raw)
    return total,count
copy_closed(out,context_out,context_names)
for arm in c.ARMS:
    source=out/arm
    if not source.exists():continue
    c.require(ctx is not None,'Restart evidence requires original validated context')
    assert source.is_dir() and not source.is_symlink()
    assert all(path.name in arm_names for path in source.iterdir())
    target=evidence/arm;target.mkdir()
    total,count=copy_closed(source,target,arm_names)
    binding=dict(schema='arctic-safe-arm-export-v1',arm=arm,context=ctx,
        release_acceptance=False,image_qualified=False,performance_acceptance=False,observer_profile_admitted=False)
    raw=(__import__('json').dumps(binding,sort_keys=True)+'\n').encode()
    assert len(raw)+total<=128*1024**2 and count+1<=40
    c.exclusive_json(target/'arm-binding.json',binding)

PY
export_status=$?
screen_status=0
if [[ $export_status == 0 ]]; then
  mkdir "$out/screened"
  for compartment in context default-restart rerender-restart; do
    [[ -d "$out/evidence/$compartment" ]] || continue
    python3 -B "$execution/tools/native-functional/screen-evidence.py" --preserve-original \
      --source "$out/evidence/$compartment" --out "$out/screened/$compartment"
    part_status=$?
    [[ $part_status == 0 ]] || screen_status=$part_status
  done
fi
if [[ $status == 0 ]]; then
  [[ $export_status == 0 ]] || status=$export_status
  [[ $screen_status == 0 ]] || status=$screen_status
fi
exit "$status"
