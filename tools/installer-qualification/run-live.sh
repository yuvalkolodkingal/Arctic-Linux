#!/usr/bin/env bash
# Owned fresh installer live boot; the explicit active profile adds its private target.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/../lib/container.sh"
[[ $# == 7 ]] || arctic_die 'usage: run-live.sh SOURCE EXECUTION ISO PAYLOAD CONTEXT FIRMWARE OUT'
source_tree=$(realpath "$1")
execution_tree=$(realpath "$2")
iso=$(realpath "$3")
payload=$(realpath "$4")
context=$(realpath "$5")
firmware="$6"
out="$7"
[[ "$firmware" == uefi || "$firmware" == bios ]] || arctic_die 'unsupported installer firmware'
[[ ! -e "$out" ]] || arctic_die 'installer output must be unused'
mkdir -p "$out/data"
out=$(realpath "$out")
for path in "$source_tree" "$execution_tree" "$iso" "$payload" "$context" "$out"; do
  [[ "$path" =~ ^/[A-Za-z0-9_./-]+$ ]] || arctic_die 'fixture paths require simple absolute names'
done
python3 - "$source_tree" "$execution_tree" "$iso" "$payload" "$context" <<'PY'
import hashlib,importlib.util,json,subprocess,sys
from pathlib import Path
source,execution,iso,payload,context=map(Path,sys.argv[1:])
spec=importlib.util.spec_from_file_location('installer_context',execution/'tools/installer-qualification/guest.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
value=module.validate_context(json.loads(context.read_text()))
def sha(path):
    result=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):result.update(chunk)
    return result.hexdigest()
for tree,key in ((source,'source_sha'),(execution,'execution_sha')):
    assert subprocess.check_output(['git','-C',str(tree),'rev-parse','HEAD'],text=True).strip()==value[key]
    assert not subprocess.check_output(['git','-C',str(tree),'status','--porcelain'],text=True).strip()
assert iso.is_file() and not iso.is_symlink() and iso.stat().st_size==value['iso_bytes']
assert sha(iso)==value['iso_sha256']
for name,path in {'checker_sha256':execution/'tools/installer-qualification/guest.py',
                  'runtime_sha256':execution/'tools/native-functional/taskbar-runtime.py',
                  'native_sha256':execution/'tools/native-functional/native_smoke.py',
                  'capture_sha256':payload/'raw-screencopy'}.items():
    assert path.is_file() and not path.is_symlink() and sha(path)==value[name]
assert (payload/'raw-screencopy').read_bytes()[:4]==b'\x7fELF'
if value['schema']=='arctic-installer-active-context-v1':
    for name,key in (('active-guest.py','active_checker_sha256'),('installed-guest.py','installed_checker_sha256')):
        assert sha(execution/'tools/installer-qualification'/name)==value[key]
PY
cp "$execution_tree/tools/installer-qualification/guest.py" "$out/data/installer-guest.py"
cp "$execution_tree/tools/native-functional/taskbar-runtime.py" "$out/data/taskbar-runtime.py"
cp "$execution_tree/tools/native-functional/native_smoke.py" "$out/data/native_smoke.py"
cp "$payload/raw-screencopy" "$out/data/raw-screencopy"
cp "$context" "$out/data/installer-context.json"
python3 - "$execution_tree" "$out/data" <<'PY'
import json,os,secrets,shutil,sys
from pathlib import Path
execution,data=map(Path,sys.argv[1:])
context=json.loads((data/'installer-context.json').read_text())
if context['schema']=='arctic-installer-active-context-v1':
    shutil.copyfile(execution/'tools/installer-qualification/active-guest.py',data/'installer-active.py')
    shutil.copyfile(execution/'tools/installer-qualification/installed-guest.py',data/'installed-guest.py')
    fd=os.open(data/'active-credentials.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream:json.dump({'password':secrets.token_hex(16)},stream)
PY
chmod 0755 "$out/data/raw-screencopy"
cat > "$out/system-area.sh" <<'BOOTSTRAP'
#!/bin/sh
set -eu
[ "$(id -u)" = 0 ]
[ "$(blkid -s LABEL -o value /dev/sr0)" = ARCTICGUI ]
mkdir -p /run/t
mountpoint -q /run/t || mount -t iso9660 -o ro /dev/sr0 /run/t
if [ -f /run/t/installed-guest.py ] && ! grep -qw rd.live.image /proc/cmdline; then
  exec python3 -I /run/t/installed-guest.py "$@" </dev/null >/dev/ttyS0 2>&1
fi
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
exec python3 /run/t/installer-guest.py --disposable-guest </dev/null >/dev/ttyS0 2>&1
BOOTSTRAP
engine=$(arctic_engine)
arctic_container_args
image="${ARCTIC_FEDORA_IMAGE:?immutable prepared VM image required}"
[[ "$image" =~ ^(sha256:)?[0-9a-f]{64}$ ]] || arctic_die 'requires immutable prepared VM image ID'
container="${ARCTIC_VM_CONTAINER_NAME:?owned installer VM container required}"
[[ "$container" =~ ^arctic-paired-native-[0-9a-f]{32}$ ]] || arctic_die 'invalid owned installer container'
[[ -c /dev/kvm ]] || arctic_die 'installer runtime requires real KVM'
# --cidfile is created only for this invocation's new container. Never remove a
# pre-existing same-name container if acquisition fails.
[[ ! -e "$out/container-id" ]] || arctic_die 'owned container receipt already exists'
if "$engine" container inspect "$container" >/dev/null 2>&1; then
  arctic_die 'installer container name already exists'
fi
invocation=$(python3 -c 'import uuid; print(uuid.uuid4().hex)')
cleanup() {
  python3 - "$engine" "$out/container-id" "$container" "$invocation" <<'PY_CLEANUP'
import json,re,subprocess,sys
from pathlib import Path
engine,path,name,invocation=sys.argv[1:]
receipt=Path(path)
if receipt.is_file() and not receipt.is_symlink():
    identity=receipt.read_text().strip()
    if re.fullmatch('[0-9a-f]{64}',identity):
        try:
            rows=json.loads(subprocess.check_output([engine,'container','inspect',identity],timeout=20))
            if len(rows)==1 and rows[0]['Id']==identity and rows[0]['Name']=='/'+name and rows[0]['Config']['Labels'].get('org.arctic.installer.invocation')==invocation:
                subprocess.run([engine,'rm','-f',identity],timeout=20,check=True,stdout=subprocess.DEVNULL)
        except (OSError,ValueError,KeyError,subprocess.SubprocessError):
            raise SystemExit(1)
PY_CLEANUP
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
"$engine" run --name "$container" --cidfile "$out/container-id" --label "org.arctic.installer.invocation=$invocation" "${ARCTIC_CONTAINER_ARGS[@]}" --device /dev/kvm \
  -e OUT="$out" -e FIRMWARE="$firmware" -v "$execution_tree:/execution:ro" \
  -v "$iso:/iso:ro" -v "$out:$out" "$image" bash -c "$ARCTIC_CONTAINER_PROLOGUE"'
set -euo pipefail
rpm -q qemu-system-x86-core qemu-ui-dbus qemu-ui-opengl dbus-daemon glib2 xorriso python3-pillow >/dev/null
qemu-system-x86_64 -display help | grep -qx dbus
xorriso -as mkisofs -quiet -V ARCTICGUI -J -R -uid 0 -gid 0 -G "$OUT/system-area.sh" \
  -o "$OUT/data.iso" "$OUT/data"
python3 /execution/tools/installer-qualification/driver.py --out "$OUT" --firmware "$FIRMWARE"
'
