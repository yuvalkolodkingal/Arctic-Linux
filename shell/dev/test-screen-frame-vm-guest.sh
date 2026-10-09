#!/usr/bin/env bash
# Private rendering fixture only; enforcing SELinux remains an independent ISO gate.
set -euo pipefail
[[ $$ -eq 1 ]] && grep -qw 'arctic.frame-test=1' /proc/cmdline || {
  echo 'This fixture only runs as init in the explicitly marked private test VM.' >&2; exit 2;
}
export HOME=/run/frame-home PATH=/usr/bin:/usr/sbin:/bin:/sbin
cleanup() {
  status=$?
  if [[ "$status" == 0 ]]; then printf 'ARCTIC-FRAME-VM-PASS\n'; else printf 'ARCTIC-FRAME-VM-FAIL status=%s\n' "$status"; fi
  sync
  /frame-tools/busybox poweroff -f
}
trap cleanup EXIT
mount -t tmpfs tmpfs /run
mount -t tmpfs tmpfs /tmp
# Grim uses POSIX shm_open, which requires the normal /dev/shm tmpfs. The
# minimal fixture's devtmpfs does not create it like a systemd OS boot does.
mkdir -p /dev/shm
mount -t tmpfs -o mode=1777,nosuid,nodev tmpfs /dev/shm
# A terminal needs the ordinary devpts mount. This minimal rendering VM boots
# without systemd's filesystem setup; provide it only inside this owned guest.
mkdir -p /dev/pts
mount -t devpts -o newinstance,ptmxmode=0666,mode=0620 devpts /dev/pts
ln -sfn pts/ptmx /dev/ptmx
python3 - <<'PY'
import os, pty
master, slave = pty.openpty()
print('Private terminal PTY:', os.ttyname(slave), flush=True)
os.close(slave)
os.close(master)
PY
mkdir -m 700 "$HOME"
modprobe udmabuf || test -c /dev/udmabuf
test -c /dev/udmabuf
cd /arctic
git config --global --add safe.directory /arctic
for compositor in mango sway; do
  python3 shell/dev/test-screen-frame.py --compositor "$compositor" \
    --baseline-ref 2d5ac68847a5feb541177aeaa5a9a00d5ad44815 --out "/evidence/$compositor"
done
