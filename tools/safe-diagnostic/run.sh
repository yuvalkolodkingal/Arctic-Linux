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
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
"$engine" run --name "$prep" --cidfile "$out/prep-container-id" --label "org.arctic.safe.invocation=$invocation" \
  "${ARCTIC_CONTAINER_ARGS[@]}" -v "$execution:/execution:ro" -v "$out:/out" "$image" bash -c "$ARCTIC_CONTAINER_PROLOGUE"'
dnf -y --setopt=timeout=30 --setopt=retries=2 --setopt=install_weak_deps=False install \
 qemu-system-x86-core qemu-img edk2-ovmf seabios-bin python3-pillow xorriso gcc wayland-devel \
 qemu-device-display-virtio-vga qemu-device-display-virtio-gpu qemu-device-display-virtio-gpu-pci
mkdir /out/generated
wayland-scanner client-header /execution/shell/dev/wlr-screencopy-unstable-v1.xml /out/generated/screencopy-client.h
wayland-scanner private-code /execution/shell/dev/wlr-screencopy-unstable-v1.xml /out/generated/screencopy-client.c
gcc -std=c11 -Wall -Wextra -Wno-unused-parameter -Werror /execution/tools/safe-diagnostic/screencopy.c \
 /out/generated/screencopy-client.c -I /out/generated -lwayland-client -o /out/data/raw-screencopy
python3 - <<"PY"
import hashlib,json,subprocess
from pathlib import Path
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
packages=subprocess.check_output(["rpm","-q","gcc","wayland-devel","libwayland-client","qemu-system-x86-core","edk2-ovmf","xorriso","python3-pillow"],text=True).splitlines()
value=dict(schema="arctic-safe-tools-v1",release_acceptance=False,
 sources={p:sha("/execution/"+p) for p in ("tools/safe-diagnostic/screencopy.c","shell/dev/wlr-screencopy-unstable-v1.xml")},
 binary_sha256=sha("/out/data/raw-screencopy"),packages=packages,
 compiler=subprocess.check_output(["gcc","--version"],text=True).splitlines()[0],
 dynamic_dependencies=subprocess.check_output(["ldd","/out/data/raw-screencopy"],text=True).splitlines())
Path("/out/build-provenance.json").write_text(json.dumps(value,sort_keys=True)+"\n")
PY
'
prepared=$("$engine" commit "$prep")
[[ "$prepared" =~ ^(sha256:)?[0-9a-f]{64}$ ]] || arctic_die 'prepared image ID differs'
python3 - "$execution" "$inputs" "$out" "$prepared" <<'PY'
import importlib.util,json,secrets,shutil,subprocess,sys
from pathlib import Path
execution,inputs,out=map(Path,sys.argv[1:4]);prepared=sys.argv[4]
spec=importlib.util.spec_from_file_location('safe_common',execution/'tools/safe-diagnostic/common.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
manifest=c.validate_manifest(c.strict((execution/'tools/safe-diagnostic/execution-manifest.json').read_bytes()))
assert not subprocess.check_output(['git','-C',str(execution),'status','--porcelain'])
iso=inputs/c.IMAGE['name'];c.regular(iso,2_000_000_000)
assert iso.stat().st_size==c.IMAGE['bytes'] and c.sha(iso)==c.IMAGE['sha256']
for name,path in {'common.py':execution/'tools/safe-diagnostic/common.py',
 'guest.py':execution/'tools/safe-diagnostic/guest.py',
 'taskbar-runtime.py':execution/'tools/native-functional/taskbar-runtime.py',
 'native_smoke.py':execution/'tools/native-functional/native_smoke.py',
 'screen-evidence.py':execution/'tools/native-functional/screen-evidence.py'}.items():
    shutil.copyfile(path,out/'data'/name)
assert (out/'data/raw-screencopy').read_bytes()[:4]==b'\x7fELF'
ctx=c.context(dict(schema='arctic-safe-guest-context-v1',image=c.IMAGE,
 execution_sha=subprocess.check_output(['git','-C',str(execution),'rev-parse','HEAD'],text=True).strip(),
 binding_id=secrets.token_hex(16),bundle={p.name:c.sha(p) for p in (out/'data').iterdir()}))
(out/'data/context.json').write_text(json.dumps(ctx,sort_keys=True)+'\n')
(out/'fixture-provenance.json').write_text(json.dumps(dict(schema='arctic-safe-fixture-v1',image=c.IMAGE,
 execution_sha=ctx['execution_sha'],prepared_image_id=prepared,release_acceptance=False),sort_keys=True)+'\n')
PY
cat > "$out/system-area.sh" <<'BOOTSTRAP'
#!/bin/sh
set -eu
[ "$(id -u)" = 0 ]
[ "$(blkid -s LABEL -o value /dev/sr1)" = ARCTICSAFE ]
mkdir -p /run/t
mountpoint -q /run/t && exit 1
mount -t iso9660 -o ro,nodev,nosuid /dev/sr1 /run/t
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
chmod 0755 "$out/data/raw-screencopy"
set +e
"$engine" run --name "$vm" --cidfile "$out/vm-container-id" --label "org.arctic.safe.invocation=$invocation" \
  --network none --device /dev/kvm -e OUT=/out -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$execution:/execution:ro" -v "$inputs/Arctic-Linux-1.2-candidate-38032256030-1-x86_64.iso:/iso:ro" \
  -v "$out:/out" "$prepared" bash -c '
set -euo pipefail
xorriso -as mkisofs -quiet -V ARCTICSAFE -J -R -uid 0 -gid 0 -G /out/system-area.sh -o /out/data.iso /out/data
timeout --signal=TERM --kill-after=10s 10m python3 -B /execution/tools/safe-diagnostic/host.py --out /out
'
status=$?
set -e
python3 - "$out" <<'PY'
import shutil,stat,sys
from pathlib import Path
out=Path(sys.argv[1]);evidence=out/'evidence';evidence.mkdir()
total=0
for path in out.iterdir():
    if path.name in ('build-provenance.json','fixture-provenance.json','host-report.json','guest-report.json','serial.log','qemu.log') or path.suffix=='.png' or '-wayland' in path.name:
        s=path.lstat();assert stat.S_ISREG(s.st_mode) and s.st_size<=32*1024**2
        total+=s.st_size;assert total<=128*1024**2
        shutil.copyfile(path,evidence/path.name)
assert len(list(evidence.iterdir()))<=40
PY
python3 -B "$execution/tools/native-functional/screen-evidence.py" --preserve-original \
  --source "$out/evidence" --out "$out/screened"
exit "$status"
