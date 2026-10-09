#!/usr/bin/env bash
# Compile test-only Wayland probes in Fedora; never add build tools to the ISO/guest.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/../lib/container.sh"
[[ $# == 2 && -d "$1" && -d "$2" ]] || arctic_die 'usage: prepare-taskbar-tools.sh EXECUTION_TREE PAYLOAD'
source_tree="$(cd "$1" && pwd)"
payload="$(cd "$2" && pwd)"
engine="$(arctic_engine)"
arctic_container_args
image="$(arctic_resolve_image "$engine" "$ARCTIC_FEDORA_IMAGE")"
container="${ARCTIC_VM_CONTAINER_NAME:?owned preparation container required}"
[[ "${ARCTIC_INSTALLER_ACTIVE:-0}" == 0 || "${ARCTIC_INSTALLER_ACTIVE:-0}" == 1 ]] || arctic_die 'invalid active installer host profile'
[[ "$container" =~ ^arctic-paired-native-[0-9a-f]{32}$ ]] || arctic_die 'invalid taskbar preparation container'
cleanup() { "$engine" rm --force "$container" >/dev/null 2>&1 || :; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
"$engine" run --name "$container" "${ARCTIC_CONTAINER_ARGS[@]}" \
  -e "ARCTIC_INSTALLER_ACTIVE=${ARCTIC_INSTALLER_ACTIVE:-0}" \
  -v "$source_tree:/source:ro" -v "$payload:/payload" "$image" bash -c "$ARCTIC_CONTAINER_PROLOGUE"'
dnf -y --setopt=timeout=30 --setopt=retries=2 --setopt=install_weak_deps=False install \
  gcc wayland-devel dbus-daemon glib2 qemu-ui-dbus qemu-ui-opengl
if [[ "$ARCTIC_INSTALLER_ACTIVE" == 1 ]]; then
  dnf -y --setopt=timeout=30 --setopt=retries=2 --setopt=install_weak_deps=False install tesseract tesseract-langpack-eng
fi
# QEMU loads ui-dbus through its official ui-opengl module dependency even with
# gl=off. These are host fixture packages; the image and installed OS are untouched.
display_help="$(qemu-system-x86_64 -display help)"
grep -qx dbus <<< "$display_help"
gdbus help >/dev/null
dbus-daemon --version >/dev/null
printf "%s\n" "$display_help" > /payload/taskbar-display-capabilities.txt
mkdir /payload/generated
wayland-scanner client-header /source/shell/dev/wlr-screencopy-unstable-v1.xml /payload/generated/screencopy-client.h
wayland-scanner private-code /source/shell/dev/wlr-screencopy-unstable-v1.xml /payload/generated/screencopy-client.c
gcc /source/shell/dev/virtual-pointer.c -lwayland-client -o /payload/virtual-pointer
gcc -std=c11 -Wall -Wextra -Wno-unused-parameter -Werror /source/tools/native-functional/taskbar-screencopy.c \
  /payload/generated/screencopy-client.c -I /payload/generated -lwayland-client -o /payload/raw-screencopy
python3 - <<"PY"
import hashlib,json,os,subprocess
from pathlib import Path
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
result = dict(schema="arctic-taskbar-tools-v1", release_acceptance=False,
    sources={name:sha("/source/"+name) for name in ("shell/dev/virtual-pointer.c", "tools/native-functional/taskbar-screencopy.c", "shell/dev/wlr-screencopy-unstable-v1.xml")},
    binaries={name:sha("/payload/"+name) for name in ("virtual-pointer", "raw-screencopy")},
    compiler=subprocess.check_output(["gcc","--version"],text=True).splitlines()[0],
    packages=subprocess.check_output(["rpm","-q","gcc","wayland-devel","wayland-libs"],text=True).splitlines(),
    display_host=dict(backend="dbus", gl=False,
        packages=subprocess.check_output(["rpm","-q","dbus-daemon","glib2","qemu-ui-dbus","qemu-ui-opengl"],text=True).splitlines(),
        capabilities_sha256=sha("/payload/taskbar-display-capabilities.txt"),
        programs={path:sha(path) for path in ("/usr/bin/qemu-system-x86_64","/usr/bin/dbus-daemon","/usr/bin/gdbus")}))
if os.environ.get("ARCTIC_INSTALLER_ACTIVE")=="1":
    trained=[path for path in subprocess.check_output(["rpm","-ql","tesseract-langpack-eng"],text=True).splitlines() if path.endswith("/eng.traineddata")]
    assert len(trained)==1
    result["ocr_host"]=dict(packages=subprocess.check_output(["rpm","-q","tesseract","tesseract-langpack-eng"],text=True).splitlines(),
        program_sha256=sha("/usr/bin/tesseract"),traineddata_sha256=sha(trained[0]),
        version=subprocess.check_output(["tesseract","--version"],text=True,stderr=subprocess.DEVNULL).splitlines()[0])
Path("/payload/build-provenance.json").write_text(json.dumps(result,sort_keys=True)+"\n")
PY
'
image_id="$("$engine" commit "$container")"
[[ "$image_id" =~ ^(sha256:)?[0-9a-f]{64}$ ]] || arctic_die 'invalid taskbar prepared VM image identity'
printf '%s\n' "$image_id" > "$payload/taskbar-vm-prepared-image-id.txt"
for name in virtual-pointer raw-screencopy; do
  [[ -x "$payload/$name" && ! -L "$payload/$name" ]] || arctic_die 'missing compiled taskbar probe'
done
